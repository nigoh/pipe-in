"""D0066：流す前の費用の目安の入口（pipe-in estimate と、本流の確認前の 1 行）。SDK は呼ばない。

- runner を手書きの偽物に差し替える（偽物は tests/test_stage_budget.py の FakeRunner・PipeRunner と同じ形を、このファイルの中に小さく持つ。
  ほかのテストのファイルは import しない）。estimate の側は、段を流す口（asyncio.run）が呼ばれたら失敗にする。
- ファイルは tmp_path の中にだけ作る（pipeline.toml・パイプ（.pipe-in/pipes/pipe-in-<名前>/pipe.toml）・state.json）。
- 計算の数字は、本体の単価表（pipe_in.usage.prices.PRICES）の 1 ターンの費用から作るので、表の数字を直しても落ちない。
  出力のドルの書き方（小数 2〜4 桁・頭に $）だけ決めている。見出しの言葉は「少なめ」「多め」「実績」「モデル不明」「費用の目安」。
- 新しい部品（pipe_in.usage.prices・pipe_in.estimate_cmd）は、使うところで読み込む。無いあいだは「まだ作っていない」を理由に落とす。
"""

from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

import pytest

from pipe_in import cli
from pipe_in.dev import specs as st
from pipe_in.dev.pipeline import DevPipeline
from pipe_in.engine.pipeline import Exit
from pipe_in.engine.runner import StageRun
from pipe_in.pipe import definition as pd
from pipe_in.pipe.pipeline import LinearPipeline

PROMISE = "約束するものではありません"
ESTIMATE_WORD = "費用の目安"
OLD_STATE = {
    "usage_summary": {"by_model": {"claude-sonnet-4-5": {"tokens": {}, "cost_usd": 1.5}, "claude-opus-4-1": {"tokens": {}, "cost_usd": 0.25}}},
    "runs": [],
}


@pytest.fixture(autouse=True)
def no_env_pipes_dir(monkeypatch):
    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    monkeypatch.delenv("DEVPIPE_PIPES_DIR", raising=False)


# ---- 補助：新しい部品と、計算の数字 ------------------------------------------------------------------------


def price(family: str) -> int:
    try:
        mod = importlib.import_module("pipe_in.usage.prices")
    except ModuleNotFoundError as e:
        pytest.fail(f"pipe_in.usage.prices が無い（まだ作っていない）: {e}")
    return mod.PRICES["per_turn"][family]


def ceil_low(t: int) -> int:
    return (t * 20 + 99) // 100


def shows(out: str, units: int) -> bool:
    """出力のどこかに、units（1/10000 ドル）を「$」つきの小数 2〜4 桁で書いた数がある。"""
    v = units / 10000
    return any(f"${v:.{n}f}" in out for n in (2, 3, 4))


def assert_shows(out: str, units: int, what: str) -> None:
    assert shows(out, units), f"{what}（{units / 10000:.4f} ドル）が出力に無い:\n{out}"


# ---- 補助：プロジェクト・パイプ ----------------------------------------------------------------------------


def make_project(tmp_path: Path, name: str = "proj") -> Path:
    project = tmp_path / name
    project.mkdir()
    return project


def write_pipeline_toml(project: Path, text: str) -> None:
    (project / "pipeline.toml").write_text(text, encoding="utf-8")


def pipe_stage(name: str, extra: str = "") -> str:
    return f'\n[[stages]]\nname = "{name}"\nlabel = "{name}の段"\noutput = "{name}.md"\naccess = "read"\nprompt = "{name}をする"\n{extra}'


def make_pipe(project: Path, *stages: str, folder: str = ".pipe-in/pipes/pipe-in-p") -> Path:
    d = project / folder
    d.mkdir(parents=True)
    (d / "pipe.toml").write_text('[pipe]\nkind = "linear"\nlabel = "試し"\n' + "".join(stages), encoding="utf-8")
    return d


def write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


def tree(project: Path) -> dict[str, tuple[int, int, bytes]]:
    """プロジェクトの中のファイル → （大きさ, 更新の時刻, 中身）。"""
    return {
        p.relative_to(project).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns, p.read_bytes())
        for p in sorted(project.rglob("*"))
        if p.is_file()
    }


# ---- 補助：偽の runner（SDK は呼ばない） ---------------------------------------------------------------------


class PipeRunner:
    """パイプの段の偽物。成果物を書いて返す。"""

    def __init__(self, pipe: pd.PipeDef):
        self.outputs = {s.name: s.output for s in pipe.stages}
        self.calls: list[str] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append(spec.name)
        (cfg.work_dir / self.outputs[spec.name]).write_text(f"# {spec.name}\n", encoding="utf-8")
        return StageRun(stage=spec.name, session_id=f"s-{len(self.calls)}", cost_usd=0.01, num_turns=1)


class DevRunner:
    """開発フローの段の偽物。各段の代わりに文書を書き、すべて合格にする。"""

    def __init__(self):
        self.calls: list[str] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append(spec.name)
        w = cfg.work_dir
        run = StageRun(stage=spec.name, session_id=f"s-{len(self.calls)}", cost_usd=0.01, num_turns=3)
        if spec.name == "requirements":
            (w / st.REQUIREMENTS).write_text("# 要件定義書\nAC-01\n", encoding="utf-8")
        elif spec.name == "design":
            (w / st.DESIGN).write_text("# 設計書\n", encoding="utf-8")
        elif spec.name == "red":
            (w / st.RED).write_text("# テスト先行\n", encoding="utf-8")
            run.structured = {"status": "red", "summary": "red", "tests": [{"criterion": "AC-01", "test": "t"}], "commands": ["pytest -q"]}
        elif spec.name == "implement":
            (w / st.IMPLEMENTATION).write_text("## 実装\n", encoding="utf-8")
        elif spec.name == "test":
            run.structured = {"status": "pass", "summary": "pass", "failures": [], "commands": ["pytest -q"]}
        return run


@pytest.fixture
def fake_pipelines(monkeypatch):
    """cli.pipeline_for を、偽の runner の流し方に差し替える。"""

    def fake(cfg, pipe, *, test_cmd_given=False):
        if pipe is None:
            return DevPipeline(cfg, runner=DevRunner())
        return LinearPipeline(cfg.for_pipe(pipe.name, own_work_dir=True), pipe, runner=PipeRunner(pipe))

    monkeypatch.setattr(cli, "pipeline_for", fake)


@pytest.fixture
def no_stage_runs(monkeypatch):
    """estimate は段を流さない。段を流す口（asyncio.run）が呼ばれたら失敗にする。"""

    def boom(*args, **kwargs):
        pytest.fail("estimate が段を流す口（asyncio.run）を呼んだ（SDK を呼んではいけない）")

    monkeypatch.setattr(asyncio, "run", boom)


def run_estimate(capsys, *argv: str) -> str:
    """pipe-in estimate を流し、終了コード 0 を確かめて、標準出力を返す。"""
    try:
        code = cli.main(["estimate", *argv])
    except SystemExit as e:
        pytest.fail(f"pipe-in estimate が使えない（SystemExit: {e.code!r}）")
    assert code == 0, f"終了コードが 0 でない: {code!r}"
    return capsys.readouterr().out


# ---- AC-10：パイプの目安 ---------------------------------------------------------------------------------


def test_d0066_ac10_estimate_pipeは段ごとと全体を出して0で終わりSDKを呼ばない(tmp_path, capsys, no_stage_runs):
    """D0066-AC-10: pipe-in estimate --pipe <名前> は、段ごとの少なめ・多めと全体の幅を出し、終了コード 0 で終わる。段を流す口（SDK）は呼ばれない。
    sonnet・ターン上限 40 と 100・やり直し 0 の 2 段（draw・verify）で、全体の少なめは (8 + 20) ターン分、多めは (40 + 100) ターン分。"""
    p = price("sonnet")
    project = make_project(tmp_path)
    make_pipe(
        project,
        pipe_stage("draw", 'model = "sonnet"\nmax_turns = 40\n'),
        pipe_stage("verify", 'model = "sonnet"\nmax_turns = 100\n'),
    )
    out = run_estimate(capsys, "--pipe", "p", "--project", str(project))
    assert "draw" in out and "verify" in out
    assert "少なめ" in out and "多め" in out
    assert_shows(out, 100 * p, "verify の多め")
    assert_shows(out, (ceil_low(40) + ceil_low(100)) * p, "全体の少なめ")
    assert_shows(out, 140 * p, "全体の多め")
    assert "モデル不明" not in out


def test_d0066_ac03_パイプはcheckのある段だけにmax_retriesが効く(tmp_path, capsys, no_stage_runs):
    """D0066-AC-03: パイプでは、check のある段（verify。max_retries = 3）だけに多めの (1 + 3) 倍が掛かり、check の無い段（draw）は 1 回分。
    sonnet・ターン上限 10 の 2 段で、全体の多めは (10 + 10 × 4) ターン分、少なめは (2 + 2) ターン分。"""
    p = price("sonnet")
    project = make_project(tmp_path)
    check = '[stages.check]\nverdict = true\nmax_retries = 3\non_fail = "draw"\n'
    make_pipe(
        project,
        pipe_stage("draw", 'model = "sonnet"\nmax_turns = 10\n'),
        pipe_stage("verify", 'model = "sonnet"\nmax_turns = 10\n' + check),
    )
    out = run_estimate(capsys, "--pipe", "p", "--project", str(project))
    assert_shows(out, 50 * p, "全体の多め")
    assert_shows(out, 4 * p, "全体の少なめ")
    assert_shows(out, 40 * p, "verify の多め（1 + 3 倍）")


# ---- AC-11・03：開発フロー --------------------------------------------------------------------------------


def dev_stage_shown(out: str, stage: str) -> bool:
    return stage in out or st.STAGE_LABELS[stage] in out


def test_d0066_ac11_estimateはパイプ名なしで開発フロー5段をpipeline_tomlの上書きつきで出す(tmp_path, capsys, no_stage_runs):
    """D0066-AC-11: pipe-in estimate（パイプ名なし）は、組み込みの開発フローの 5 段で出す。pipeline.toml の [stages.implement] の model = opus・
    max_turns = 10 を反映する（実装は opus・10 ターン・やり直し 3、ほかは sonnet 扱いで既定のターン数）。"""
    ps, po = price("sonnet"), price("opus")
    project = make_project(tmp_path)
    write_pipeline_toml(project, '[stages.implement]\nmodel = "opus"\nmax_turns = 10\n')
    out = run_estimate(capsys, "--project", str(project))
    for stage in st.STAGES:
        assert dev_stage_shown(out, stage), f"開発フローの段 {stage} が出力に無い:\n{out}"
    high = (40 + 60 + 100) * ps + 10 * po * 4 + 100 * ps * 4
    low = (ceil_low(40) + ceil_low(60) + ceil_low(100) + ceil_low(100)) * ps + ceil_low(10) * po
    assert_shows(out, high, "全体の多め")
    assert_shows(out, low, "全体の少なめ")
    assert "モデル不明" in out, "モデルを書いていない段には印が付く"


def test_d0066_ac11_上書きが無ければ開発フローの既定のターン数で出る(tmp_path, capsys, no_stage_runs):
    """D0066-AC-11: pipeline.toml が無い開発フローは、DEFAULT_MAX_TURNS（40・60・100・150・100）で計算する。
    実装と検証だけやり直し 3（既定）なので、全体の多めは (40 + 60 + 100) ターン分 + (150 + 100) × 4 ターン分。"""
    ps = price("sonnet")
    project = make_project(tmp_path)
    out = run_estimate(capsys, "--project", str(project))
    assert_shows(out, (200 + 250 * 4) * ps, "全体の多め")
    assert_shows(out, 90 * ps, "全体の少なめ")


def test_d0066_ac03_開発フローは実装と検証だけにmax_retriesが効く(tmp_path, capsys, no_stage_runs):
    """D0066-AC-03: 開発フローでは、pipeline.toml の [pipeline] max_retries = 1 が、実装と検証の 2 段だけに効く（多めの (1 + 1) 倍）。
    ほかの 3 段は 1 回分。全体の多めは (40 + 60 + 100) ターン分 + (150 + 100) × 2 ターン分。"""
    ps = price("sonnet")
    project = make_project(tmp_path)
    write_pipeline_toml(project, "[pipeline]\nmax_retries = 1\n")
    out = run_estimate(capsys, "--project", str(project))
    assert_shows(out, (200 + 250 * 2) * ps, "全体の多め")


def test_d0066_ac11_config_で設定ファイルを選べる(tmp_path, capsys, no_stage_runs):
    """D0066-AC-11: --config <file> で、別の設定ファイルの [stages.<段>] を読む（開発フロー）。"""
    ps, po = price("sonnet"), price("opus")
    project = make_project(tmp_path)
    other = tmp_path / "other.toml"
    other.write_text('[stages.test]\nmodel = "opus"\nmax_turns = 20\n', encoding="utf-8")
    out = run_estimate(capsys, "--project", str(project), "--config", str(other))
    high = (40 + 60 + 100) * ps + 150 * ps * 4 + 20 * po * 4
    assert_shows(out, high, "全体の多め")


# ---- AC-08：実績の欄 --------------------------------------------------------------------------------------


def test_d0066_ac08_state_jsonがあると実績が別の欄で出る(tmp_path, capsys, no_stage_runs):
    """D0066-AC-08: パイプの work_dir の state.json に usage_summary があると、目安とは別の欄に実績の合計（1.75 ドル）が出る。"""
    project = make_project(tmp_path)
    make_pipe(project, pipe_stage("draw", 'model = "sonnet"\nmax_turns = 10\n'))
    write_state(project / "docs" / "pipeline" / "p" / "state.json", OLD_STATE)
    out = run_estimate(capsys, "--pipe", "p", "--project", str(project))
    assert "実績" in out
    assert "$1.75" in out


@pytest.mark.parametrize(
    "state_text",
    [None, "これは JSON ではない", json.dumps({"runs": [{"stage": "draw"}]}), json.dumps([1, 2]), json.dumps({"usage_summary": "x"})],
    ids=["無し", "壊れた", "metrics無し", "配列", "形が違う"],
)
def test_d0066_ac08_実績が無い_読めないときは実績の欄を出さず目安だけ出す(tmp_path, capsys, no_stage_runs, state_text):
    """D0066-AC-08: state.json が無い・壊れている・古い形・形が違うときは、実績の欄を出さず（「実績」の文字が無い）、目安だけを出して終了コード 0。"""
    project = make_project(tmp_path)
    make_pipe(project, pipe_stage("draw", 'model = "sonnet"\nmax_turns = 10\n'))
    if state_text is not None:
        state = project / "docs" / "pipeline" / "p" / "state.json"
        state.parent.mkdir(parents=True)
        state.write_text(state_text, encoding="utf-8")
    out = run_estimate(capsys, "--pipe", "p", "--project", str(project))
    assert "実績" not in out
    assert "少なめ" in out and "多め" in out


def test_d0066_ac08_開発フローの実績はwork_dir直下のstate_jsonを読む(tmp_path, capsys, no_stage_runs):
    """D0066-AC-08（FR-04）: 開発フローの実績は <work_dir>/state.json から読む（パイプは <work_dir>/<名前>/state.json）。"""
    project = make_project(tmp_path)
    write_state(project / "docs" / "pipeline" / "state.json", OLD_STATE)
    out = run_estimate(capsys, "--project", str(project))
    assert "実績" in out and "$1.75" in out


# ---- AC-12・27：書かない ----------------------------------------------------------------------------------


@pytest.mark.parametrize("flow", ["dev", "pipe"])
def test_d0066_ac12_estimateはwork_dirに何も作らずstate_jsonも触らない(tmp_path, capsys, no_stage_runs, flow):
    """D0066-AC-12: pipe-in estimate は、ファイルを作らず、state.json も触らない（プロジェクトの中の全ファイルの名前・大きさ・更新時刻・中身が
    流す前と同じ。work_dir（docs/pipeline）も作らない）。"""
    project = make_project(tmp_path)
    if flow == "pipe":
        make_pipe(project, pipe_stage("draw", 'model = "sonnet"\nmax_turns = 10\n'))
        write_state(project / "docs" / "pipeline" / "p" / "state.json", OLD_STATE)
        argv = ["--pipe", "p", "--project", str(project)]
    else:
        write_pipeline_toml(project, '[stages.red]\nmodel = "haiku"\n')
        write_state(project / "docs" / "pipeline" / "state.json", OLD_STATE)
        argv = ["--project", str(project)]
    before = tree(project)
    run_estimate(capsys, *argv)
    assert tree(project) == before


def test_d0066_ac12_記録の無いプロジェクトでもwork_dirを作らない(tmp_path, capsys, no_stage_runs):
    """D0066-AC-12: 記録（state.json）が無いプロジェクトに estimate を流しても、docs/pipeline を作らない（pipeline.toml だけがあるフォルダのまま）。"""
    project = make_project(tmp_path)
    write_pipeline_toml(project, "[pipeline]\nmax_retries = 2\n")
    before = tree(project)
    run_estimate(capsys, "--project", str(project))
    assert tree(project) == before
    assert not (project / "docs").exists()


def test_d0066_ac27_estimateのあとpipeline_tomlとpipe_tomlと記録の見本が1バイトも変わらない(tmp_path, capsys, no_stage_runs):
    """D0066-AC-27: pipeline.toml・pipe.toml・state.json・99_summary.md の形は変えず、estimate は読むだけ。これらを置いて estimate を流しても、
    1 バイトも変わらない（中身を比べる）。記録の形の既存のテスト（test_d0019_ac50_state_only_adds_keys など）は通り続ける。"""
    project = make_project(tmp_path)
    write_pipeline_toml(project, '[pipeline]\nmax_retries = 2\n[stages.draw]\nmodel = "opus"\n')
    pipe_dir = make_pipe(project, pipe_stage("draw"), pipe_stage("verify", '[stages.check]\nverdict = true\non_fail = "draw"\n'))
    work = project / "docs" / "pipeline" / "p"
    write_state(work / "state.json", OLD_STATE)
    (work / "99_summary.md").write_text("# まとめ\n", encoding="utf-8")
    before = {name: data for name, (_, _, data) in tree(project).items()}
    assert (pipe_dir / "pipe.toml").is_file()
    run_estimate(capsys, "--pipe", "p", "--project", str(project))
    run_estimate(capsys, "--project", str(project))
    assert {name: data for name, (_, _, data) in tree(project).items()} == before


# ---- AC-13：存在しないパイプ名 ---------------------------------------------------------------------------


def test_d0066_ac13_存在しないパイプ名はpipe_inのpipeと同じ文で止まる(tmp_path, capsys, no_stage_runs):
    """D0066-AC-13: 存在しないパイプ名を渡すと、pipe-in --pipe と同じ文（「パイプ「…」が見つかりません」）で止まり、終了コードは 0 でない
    （SystemExit の文）。何も作らない。"""
    project = make_project(tmp_path)
    with pytest.raises(SystemExit) as main_stop:
        cli.main(["--pipe", "nope", "--project", str(project), "--text", "メモ"])
    assert "見つかりません" in str(main_stop.value.code)
    before = tree(project)
    with pytest.raises(SystemExit) as estimate_stop:
        cli.main(["estimate", "--pipe", "nope", "--project", str(project)])
    assert estimate_stop.value.code == main_stop.value.code
    assert tree(project) == before


# ---- AC-14：本流の 1 行 ----------------------------------------------------------------------------------


def test_d0066_ac14_本流は確認の前に目安を出す(tmp_path, capsys, fake_pipelines):
    """D0066-AC-14: pipe-in --pipe <名前> --text …（流す本体）は、確認の前（最初の段の完了より前）に、目安を出す（「費用の目安」の行は 1 つ、
    出力が増えるのは 1〜3 行の範囲）。終了コードは今まで通り（合格は 0）。"""
    project = make_project(tmp_path)
    make_pipe(project, pipe_stage("draw", 'model = "sonnet"\nmax_turns = 10\n'))
    code = cli.main(["--project", str(project), "--pipe", "p", "--text", "メモ", "--yes"])
    out = capsys.readouterr().out
    assert code == int(Exit.PASSED)
    assert out.count(ESTIMATE_WORD) == 1, out
    assert "完了" in out
    assert out.index(ESTIMATE_WORD) < out.index("完了"), "目安が最初の段の完了より後に出ている"
    head = out[out.index(ESTIMATE_WORD):]
    assert len(head.split("約束するものではありません")[0].splitlines()) <= 3, "目安の行は 3 行までにする"


@pytest.mark.parametrize("flags", [["--yes"], ["--pause"]], ids=["yes", "pause"])
def test_d0066_ac14_開発フローの本流でも_yesと_pauseのどちらでも1回だけ出る(tmp_path, capsys, fake_pipelines, flags):
    """D0066-AC-14: 開発フローの本流でも、--yes・--pause のどちらでも目安は 1 回だけ（終了コードは変えない。--yes は 0、--pause は確認待ちの 5）。"""
    project = make_project(tmp_path)
    code = cli.main(["--project", str(project), "--text", "メモ", *flags])
    out = capsys.readouterr().out
    assert code == (int(Exit.PASSED) if flags == ["--yes"] else int(Exit.AWAITING_REVIEW))
    assert out.count(ESTIMATE_WORD) == 1, out


def test_d0066_ac14_reviewで続きを流すときは出さない(tmp_path, capsys, fake_pipelines):
    """D0066-AC-14: --pause で止めたあとの --review approve（続きを流す）では、目安を出さない（最初の流しでは 1 回出ている）。"""
    project = make_project(tmp_path)
    assert cli.main(["--project", str(project), "--text", "メモ", "--pause"]) == int(Exit.AWAITING_REVIEW)
    first = capsys.readouterr().out
    assert first.count(ESTIMATE_WORD) == 1, first
    assert cli.main(["--project", str(project), "--review", "approve"]) == int(Exit.AWAITING_REVIEW)
    assert ESTIMATE_WORD not in capsys.readouterr().out


def test_d0066_ac14_目安の計算が失敗しても流れは止まらない(tmp_path, capsys, fake_pipelines, monkeypatch):
    """D0066-AC-14: 目安を作る関数（estimate_cmd.line_for_run）が例外を出す・None を返しても、流すことは止まらず、終了コードも変わらない
    （目安の行は出ない）。"""
    try:
        mod = importlib.import_module("pipe_in.estimate_cmd")
    except ModuleNotFoundError as e:
        pytest.fail(f"pipe_in.estimate_cmd が無い（まだ作っていない）: {e}")
    project = make_project(tmp_path)
    make_pipe(project, pipe_stage("draw", 'model = "sonnet"\nmax_turns = 10\n'))

    def boom(*args, **kwargs):
        raise RuntimeError("目安が壊れた")

    monkeypatch.setattr(mod, "line_for_run", boom)
    assert cli.main(["--project", str(project), "--pipe", "p", "--text", "メモ", "--yes"]) == int(Exit.PASSED)
    assert ESTIMATE_WORD not in capsys.readouterr().out
    monkeypatch.setattr(mod, "line_for_run", lambda *a, **k: None)
    assert cli.main(["--project", str(project), "--pipe", "p", "--text", "メモ", "--yes"]) == int(Exit.PASSED)
    assert ESTIMATE_WORD not in capsys.readouterr().out


@pytest.mark.parametrize("sub", ["record", "skill", "worktree", "live"])
def test_d0066_ac14_estimate以外のサブコマンドでは出さない_守る(tmp_path, capsys, sub):
    """D0066-AC-14: estimate 以外のサブコマンド（record・skill・worktree・live）では目安を出さない（今のまま通る。守る）。
    record は start まで流し、ほかは --help だけ（使い方の文に目安が混ざらない）。"""
    if sub == "record":
        assert cli.main(["record", "start", "--project", str(tmp_path), "--text", "メモ"]) == 0
    else:
        try:
            cli.main([sub, "--help"])
        except SystemExit:
            pass  # --help は使い方を出して終わる
    assert ESTIMATE_WORD not in capsys.readouterr().out


# ---- AC-15：どの出力にも文 -------------------------------------------------------------------------------


def test_d0066_ac15_estimateのどちらの出力にも約束するものではありませんの文が付く(tmp_path, capsys, no_stage_runs):
    """D0066-AC-15: estimate（パイプ・開発フロー）の出力に、FR-09 の文（「約束するものではありません」を含む全文）が付く。実績の欄があるときも。"""
    project = make_project(tmp_path)
    make_pipe(project, pipe_stage("draw", 'model = "sonnet"\nmax_turns = 10\n'))
    write_state(project / "docs" / "pipeline" / "p" / "state.json", OLD_STATE)
    table = json.loads((Path(__file__).resolve().parent / "fixtures" / "cost_estimate.json").read_text(encoding="utf-8"))
    for argv in (["--pipe", "p", "--project", str(project)], ["--project", str(project)]):
        out = run_estimate(capsys, *argv)
        assert PROMISE in out
        assert table["disclaimer"] in out, "FR-09 の文が全文で付いていない"


def test_d0066_ac15_本流の出力にも約束するものではありませんの文が付く(tmp_path, capsys, fake_pipelines):
    """D0066-AC-15: 本流（流す本体）の確認前の目安にも、FR-09 の文（全文）が付く（2 行目）。"""
    project = make_project(tmp_path)
    make_pipe(project, pipe_stage("draw", 'model = "sonnet"\nmax_turns = 10\n'))
    cli.main(["--project", str(project), "--pipe", "p", "--text", "メモ", "--yes"])
    out = capsys.readouterr().out
    table = json.loads((Path(__file__).resolve().parent / "fixtures" / "cost_estimate.json").read_text(encoding="utf-8"))
    assert table["disclaimer"] in out


# ---- AC-26：古いパイプ・前の版の置き場所 ------------------------------------------------------------------


def test_d0066_ac26_modelとmax_turnsの無い古いパイプも目安が出て印が付く(tmp_path, capsys, no_stage_runs):
    """D0066-AC-26: pipe.toml に model・max_turns を書いていない古いパイプでも、目安が出る。既定（sonnet・パイプの既定のターン数 100）で計算し、
    「モデル不明」の印が付く。"""
    p = price("sonnet")
    project = make_project(tmp_path)
    make_pipe(project, pipe_stage("draw"))
    out = run_estimate(capsys, "--pipe", "p", "--project", str(project))
    assert "モデル不明" in out
    assert_shows(out, 100 * p, "全体の多め（100 ターン）")
    assert_shows(out, 20 * p, "全体の少なめ（20 ターン）")


def test_d0066_ac26_前の版の置き場所のパイプでも出る(tmp_path, capsys, no_stage_runs):
    """D0066-AC-26: 前の版の置き場所（.devpipe/pipes/devpipe-<名前>/）のパイプも、--pipe と同じ探し方で読んで、目安が出る。"""
    p = price("sonnet")
    project = make_project(tmp_path)
    make_pipe(project, pipe_stage("draw", 'model = "sonnet"\nmax_turns = 30\n'), folder=".devpipe/pipes/devpipe-old")
    out = run_estimate(capsys, "--pipe", "old", "--project", str(project))
    assert "draw" in out
    assert_shows(out, 30 * p, "全体の多め（30 ターン）")
