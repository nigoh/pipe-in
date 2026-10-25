"""D0051：段ごとの費用の上限を、runs[] の要素に残す（本体の記録）。FR-01〜FR-04。

SDK は呼ばない。runner を手書きの偽物に差し替える（偽物は tests/test_pipeline.py の FakeRunner・tests/test_pipe_flow.py の ScriptedRunner と
同じ形を、このファイルの中に小さく持つ。ほかのテストのファイルは import しない）。ファイルは tmp_path の中にだけ作る。
本体が書く鍵（max_budget_usd・resumed）の名前と値は、拡張のテストと共通の表 tests/fixtures/budget_record.json で結ぶ。

- 新しい部品 stage_budget_usd（pipe_in/engine/spec.py）は、使うところで取る。名前が消えたらその理由で落とす。
- 上限を決めるのは stage_budget_usd 1 つ。SDK に渡す値（runner.sdk_options）と、runs[] に残す値（BasePipeline._run）は、同じ関数から取る。
- 今の作りのままで通るテストは、名前の末尾を _守る にし、説明の末尾に「（今のまま通る。守る）」と書く。
  パラメータ化したテストのうち、今のまま通る入力は、id の末尾を -keep にする。
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipe_in.dev import specs as st
from pipe_in.dev.pipeline import DevPipeline
from pipe_in.dev.record import Recorder
from pipe_in.engine import live
from pipe_in.engine import spec as spec_mod
from pipe_in.engine.checkpoint import Decision
from pipe_in.engine.config import load_config
from pipe_in.engine.pipeline import Exit, ShellResult
from pipe_in.engine.runner import StageRun, sdk_options
from pipe_in.pipe import definition as pd
from pipe_in.pipe.pipeline import LinearPipeline

ROOT = Path(__file__).resolve().parents[1]
TABLE = json.loads((ROOT / "tests" / "fixtures" / "budget_record.json").read_text(encoding="utf-8"))
KEYS = ("max_budget_usd", "resumed")
STOPPED = "error_max_budget_usd"
FIXED_START = "2026-10-17T10:00:00"
FIXED_NOW = datetime(2026, 10, 17, 10, 0, 0, tzinfo=timezone.utc)
FAIL = {"status": "fail", "summary": "直す点あり", "problems": ["矢印が逆"]}
PASS = {"status": "pass", "summary": "よい", "problems": []}


# ---- 補助：新しい部品 ----------------------------------------------------------------------------


def stage_budget_usd(spec, cfg):
    """pipe_in.engine.spec.stage_budget_usd（無ければ、無いことを理由に落とす）。"""
    fn = getattr(spec_mod, "stage_budget_usd", None)
    if fn is None:
        pytest.fail("pipe_in.engine.spec.stage_budget_usd が無い（まだ作っていない）")
    return fn(spec, cfg)


# ---- 補助：設定・記録の読み書き --------------------------------------------------------------------


def make_project(tmp_path: Path, name: str) -> Path:
    project = tmp_path / name
    project.mkdir()
    return project


def write_toml(project: Path, text: str) -> None:
    (project / "pipeline.toml").write_text(text, encoding="utf-8")


def budget_toml(**limits) -> str:
    """[stages.<段>] max_budget_usd = <値> を並べた pipeline.toml。値は Python の repr のまま TOML の数として書く（0・0.0・-0.0 も）。"""
    return "".join(f"[stages.{stage}]\nmax_budget_usd = {value!r}\n" for stage, value in limits.items())


def dev_cfg(project: Path, limits: dict | None = None, **kw):
    """limits があれば pipeline.toml に書いてから、設定を読む。"""
    if limits is not None:
        write_toml(project, budget_toml(**limits))
    return load_config(project, None, auto_approve=kw.pop("auto_approve", True), **kw)


def dev_state(project: Path) -> dict:
    return json.loads((project / "docs" / "pipeline" / "state.json").read_text(encoding="utf-8"))


def pipe_state(project: Path) -> dict:
    return json.loads((project / "docs" / "pipeline" / "p" / "state.json").read_text(encoding="utf-8"))


def stage_runs(state: dict, stage: str) -> list[dict]:
    """段の実行（seq を持つ要素）だけを、runs[] に現れる順に。"""
    return [h for h in state["runs"] if "seq" in h and h["stage"] == stage]


def run_dev(p: DevPipeline, text: str | None = "ログイン画面を作る", frm: str = "requirements") -> Exit:
    return asyncio.run(p.run(text, frm))


def red_verdict(*acs: str) -> dict:
    return {
        "status": "red",
        "summary": "red です",
        "tests": [{"criterion": a, "test": f"test_{a}"} for a in acs],
        "commands": ["pytest -q"],
    }


# ---- 補助：偽の runner -----------------------------------------------------------------------------


class FakeRunner:
    """各段の代わりに文書を書き、決めた判定を返す偽物（SDK は呼ばない）。stop_stage の段だけ、費用の上限で止まった結果
    （is_error・subtype = error_max_budget_usd）を返す。その段は文書も判定も返さない。"""

    def __init__(self, verdicts=None, reds=None, *, two_acs=False, stop_stage=None, cost=0.01, duration=0.0):
        self.verdicts = list(verdicts or ["pass"])
        self.reds = list(reds or [])
        self.two_acs = two_acs
        self.stop_stage = stop_stage
        self.cost = cost
        self.duration = duration
        self.calls: list[tuple[str, str | None, str]] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append((spec.name, resume, prompt))
        w = cfg.work_dir
        run = StageRun(
            stage=spec.name, session_id=f"s-{len(self.calls)}", cost_usd=self.cost, num_turns=3, duration_sec=self.duration
        )
        if spec.name == self.stop_stage:
            run.is_error = True
            run.subtype = STOPPED
            run.errors = ["費用の上限に達しました"]
            return run
        if spec.name == "requirements":
            ac = "AC-01\nAC-02\n" if self.two_acs else "AC-01\n"
            (w / st.REQUIREMENTS).write_text(f"# 要件定義書\n{ac}", encoding="utf-8")
        elif spec.name == "design":
            (w / st.DESIGN).write_text("# 設計書\n", encoding="utf-8")
        elif spec.name == "red":
            (w / st.RED).write_text("# テスト先行\n", encoding="utf-8")
            run.structured = self.reds.pop(0) if self.reds else red_verdict("AC-01")
        elif spec.name == "implement":
            (w / st.IMPLEMENTATION).write_text("## 実装\n", encoding="utf-8")
        elif spec.name == "test":
            status = self.verdicts.pop(0) if self.verdicts else "pass"
            run.structured = {
                "status": status,
                "summary": f"{status} です",
                "failures": [] if status == "pass" else [{"criterion": "AC-01", "detail": "期待と違う"}],
                "commands": ["pytest -q"],
            }
        return run


class PipeRunner:
    """パイプの段の偽物。成果物を書き、段ごとに決めた構造化出力を順に返す。呼ばれた (段, resume, 指示) を calls に残す。"""

    def __init__(self, pipe: pd.PipeDef, structured: dict[str, list] | None = None):
        self.outputs = {s.name: s.output for s in pipe.stages}
        self.structured = {k: list(v) for k, v in (structured or {}).items()}
        self.calls: list[tuple[str, str | None, str]] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append((spec.name, resume, prompt))
        (cfg.work_dir / self.outputs[spec.name]).write_text(f"# {spec.name}\n", encoding="utf-8")
        queue = self.structured.get(spec.name)
        data = queue.pop(0) if queue else None
        return StageRun(stage=spec.name, session_id=f"s-{len(self.calls)}", structured=data, cost_usd=0.01, num_turns=1)


def pipe_stage(name: str, extra: str = "") -> str:
    """成果物が <段>.md の、読むだけの段。extra は段の表の最後に足す行（max_budget_usd = … や [stages.check] など）。"""
    return f'\n[[stages]]\nname = "{name}"\nlabel = "{name}の段"\noutput = "{name}.md"\naccess = "read"\nprompt = "{name}をする"\n{extra}'


def pipe_toml(*stages: str) -> str:
    return '[pipe]\nkind = "linear"\nlabel = "試し"\n' + "".join(stages)


def make_pipe(project: Path, toml: str) -> pd.PipeDef:
    d = project / "pipes" / "pipe-in-p"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pipe.toml").write_text(toml, encoding="utf-8")
    return pd.load_pipe(d)


def run_pipe(project: Path, pipe: pd.PipeDef, runner, *, ask=None, **kw) -> Exit:
    cfg = load_config(project, None, auto_approve=kw.pop("auto_approve", True), **kw).for_pipe(pipe.name, own_work_dir=True)
    return asyncio.run(LinearPipeline(cfg, pipe, runner=runner, ask=ask).run("やること"))


def record_with_spec(cfg, pipe_value) -> dict:
    """要件定義の段を 1 回だけ _run し、runs[] に足された要素を返す。段の定義の上限（pipe.toml 相当）は pipe_value に替える。"""
    cfg.work_dir.mkdir(parents=True, exist_ok=True)
    p = DevPipeline(cfg, runner=FakeRunner(["pass"]))
    p.specs["requirements"] = dataclasses.replace(p.specs["requirements"], max_budget_usd=pipe_value)
    asyncio.run(p._run("requirements", "指示"))
    return p.history[-1]


# ---- 補助：共通の表 -------------------------------------------------------------------------------


def table_params(key: str) -> list:
    """共通の表の cases を 1 件ずつ。key を書かないケースは今のまま通るので、id の末尾を -keep にする。"""
    out = []
    for c in TABLE["cases"]:
        name = f"limit{c['limit']}-resume{c['resume']}" + ("" if key in c["written"] else "-keep")
        out.append(pytest.param(c, id=name))
    return out


def entry_of_case(project: Path, case: dict) -> dict:
    """共通の表の 1 件：limit を pipeline.toml に書き（null は書かない）、_run を 1 回流して、足された要素を返す。"""
    cfg = dev_cfg(project, None if case["limit"] is None else {"requirements": case["limit"]})
    cfg.work_dir.mkdir(parents=True, exist_ok=True)
    p = DevPipeline(cfg, runner=FakeRunner(["pass"]))
    asyncio.run(p._run("requirements", "指示", resume="s-prev" if case["resume"] else None))
    return p.history[-1]


def assert_key_as_written(entry: dict, case: dict, key: str) -> None:
    written = case["written"]
    if key in written:
        assert key in entry, f"runs[] の要素に {key} が無い（書くはずの値 {written[key]!r}）。今の鍵: {sorted(entry)}"
        assert entry[key] == written[key], f"{key} が {entry[key]!r}（表では {written[key]!r}）"
        if written[key] is True:
            assert entry[key] is True
    else:
        assert key not in entry, f"{key} は書かないはずなのに要素にある: {entry[key]!r}"


def test_d0051_ac01_共通の表のkeysは本体が書く2つの鍵と同じ_守る():
    """D0051-AC-01: 共通の表 tests/fixtures/budget_record.json の keys は、本体が書く max_budget_usd・resumed の 2 つで、
    どのケースの written もその範囲に収まる（表の鍵が増えたら、このファイルのテストも増やす気づきになる）。（今のまま通る。守る）"""
    assert TABLE["keys"] == list(KEYS)
    for c in TABLE["cases"]:
        assert set(c) >= {"memo", "limit", "resume", "written", "read"}, c
        assert set(c["written"]) <= set(KEYS), c


# ---- FR-01：上限が効いた実行に、効いた上限を残す -------------------------------------------------------


def test_d0051_ac01_上限が開発フローのruns要素に残る(tmp_path):
    """D0051-AC-01: [stages.requirements] max_budget_usd = 0.6 で開発フローを最後まで流すと、requirements の runs[] の要素に
    max_budget_usd が 0.6 で残り、上限を書かなかった design・red・implement・test の要素には鍵が無い。"""
    cfg = dev_cfg(tmp_path, {"requirements": 0.6})
    assert run_dev(DevPipeline(cfg, runner=FakeRunner(["pass"]))) == Exit.PASSED
    runs = [h for h in dev_state(tmp_path)["runs"] if "seq" in h]
    assert runs[0]["stage"] == "requirements"
    assert runs[0].get("max_budget_usd") == 0.6, f"requirements の要素に max_budget_usd が無い。今の鍵: {sorted(runs[0])}"
    others = runs[1:]
    assert [h["stage"] for h in others] == ["design", "red", "implement", "test"]
    assert [h["stage"] for h in others if "max_budget_usd" in h] == []


@pytest.mark.parametrize("case", table_params("max_budget_usd"))
def test_d0051_ac01_本体が書く上限の鍵と値は共通の表のとおり(tmp_path, case):
    """D0051-AC-01: 共通の表の 1 件ずつ。limit を pipeline.toml に書いて _run を 1 回流すと、runs[] の要素の max_budget_usd の有る無しと値が
    written と等しい（0・上限なし・resume の有無によらず、上限が無ければ鍵は付かない）。id の末尾が -keep のケースは今のまま通る。"""
    assert_key_as_written(entry_of_case(tmp_path, case), case, "max_budget_usd")


def test_d0051_ac02_パイプの上限が残りpipeline_tomlがあればそちらが優先(tmp_path):
    """D0051-AC-02: pipe.toml の段 a に max_budget_usd = 1.5 を書いたパイプを流すと、a の要素に 1.5 が残る（上限を書かない段 b には鍵が無い）。
    同じプロジェクトに [stages.a] max_budget_usd = 0.6 の pipeline.toml を書いて流し直すと、pipeline.toml が優先で、記録も 0.6。"""
    pipe = make_pipe(tmp_path, pipe_toml(pipe_stage("a", "max_budget_usd = 1.5\n"), pipe_stage("b")))
    assert run_pipe(tmp_path, pipe, PipeRunner(pipe)) == Exit.PASSED
    state = pipe_state(tmp_path)
    (a,) = stage_runs(state, "a")
    assert a.get("max_budget_usd") == 1.5, f"a の要素に max_budget_usd が無い。今の鍵: {sorted(a)}"
    assert "max_budget_usd" not in stage_runs(state, "b")[0]
    write_toml(tmp_path, budget_toml(a=0.6))
    assert run_pipe(tmp_path, pipe, PipeRunner(pipe)) == Exit.PASSED
    (a2,) = stage_runs(pipe_state(tmp_path), "a")
    assert a2.get("max_budget_usd") == 0.6, f"pipeline.toml が優先されていない: {a2.get('max_budget_usd')!r}"


def test_d0051_ac03_上限が無い実行には項目も印も書かない_守る(tmp_path):
    """D0051-AC-03: 上限が無い（pipeline.toml にも段の定義にも無い）開発フロー（差し戻しあり）とパイプを流すと、runs[] のどの要素にも
    max_budget_usd・resumed の鍵が無い（null も書かない）。（今のまま通る。守る）"""
    dev = make_project(tmp_path, "dev")
    assert run_dev(DevPipeline(dev_cfg(dev), runner=FakeRunner(["fail", "pass"]))) == Exit.PASSED
    pipe_project = make_project(tmp_path, "pipe")
    pipe = make_pipe(pipe_project, pipe_toml(pipe_stage("a"), pipe_stage("b")))
    assert run_pipe(pipe_project, pipe, PipeRunner(pipe)) == Exit.PASSED
    runs = dev_state(dev)["runs"] + pipe_state(pipe_project)["runs"]
    assert any("seq" in h for h in runs)
    assert [h for h in runs if any(k in h for k in KEYS)] == []


def test_d0051_ac04_上限が無くresumeを渡した実行にも印は無い_守る(tmp_path):
    """D0051-AC-04: 上限が無く、要件定義の確認で「修正」と答えて resume を渡した再実行の要素にも、続きの会話の印（resumed）は無い。
    再実行が本当に resume を渡していることも確かめる。（今のまま通る。守る）"""
    answers = iter([Decision("revise", "未確定事項を減らして"), Decision("approve"), Decision("approve"), Decision("approve")])
    r = FakeRunner(["pass"])
    p = DevPipeline(dev_cfg(tmp_path, auto_approve=False), runner=r, ask=lambda s, d: next(answers))
    assert run_dev(p) == Exit.PASSED
    assert r.calls[1][0] == "requirements" and r.calls[1][1] == "s-1"
    second = stage_runs(dev_state(tmp_path), "requirements")[1]
    assert second["note"] == "指摘を反映"
    assert not any(k in second for k in KEYS)


def test_d0051_ac06_seqの無い要素に項目が入らない(tmp_path):
    """D0051-AC-06: [stages.requirements] max_budget_usd = 0.6 で、確認つき（ask が approve を返す）・確認用コマンドつきで検証まで流すと、
    seq を持つ requirements の要素には max_budget_usd があり、seq を持たない要素（review・verdict・result・command_check）には
    max_budget_usd も resumed も入らない。"""
    cfg = dev_cfg(tmp_path, {"requirements": 0.6}, auto_approve=False, test_command="pytest -q")
    shells = iter([ShellResult(1, "1 failed"), ShellResult(0, "ok")])  # 1 つ目はテスト先行のあとの「赤」の確認
    p = DevPipeline(
        cfg, runner=FakeRunner(["pass"]), ask=lambda s, d: Decision("approve"), shell=lambda c, d, t: next(shells)
    )
    assert run_dev(p) == Exit.PASSED
    runs = dev_state(tmp_path)["runs"]
    plain = [h for h in runs if "seq" not in h]
    kinds = {k for h in plain for k in ("review", "verdict", "result", "command_check") if k in h}
    assert kinds == {"review", "verdict", "result", "command_check"}, kinds
    first = [h for h in runs if "seq" in h][0]
    assert first.get("max_budget_usd") == 0.6, f"requirements の要素に max_budget_usd が無い。今の鍵: {sorted(first)}"
    assert [h for h in plain if any(k in h for k in KEYS)] == []


def test_d0051_ac06_record_doneの要素に項目が入らない_守る(tmp_path):
    """D0051-AC-06: pipeline.toml に上限 0.6 があっても、pipe-in record done が書く要素には max_budget_usd も resumed も入らない。
    （今のまま通る。守る）"""
    write_toml(tmp_path, budget_toml(requirements=0.6))
    r = Recorder(load_config(tmp_path), now=lambda: datetime(2026, 10, 17, 10, 0, 0))
    r.start("足したい機能のメモ")
    r.begin("requirements")
    r.done("requirements", summary="要件定義を書いた")
    (entry,) = dev_state(tmp_path)["runs"]
    assert not any(k in entry for k in KEYS)


# ---- FR-02：SDK に渡す上限と、記録する上限は、1 つの関数が決めた同じ値 ---------------------------------------


ZEROS = pytest.mark.parametrize("zero", [0, 0.0, -0.0], ids=["int0", "float0", "negzero"])


@ZEROS
def test_d0051_ac07_pipeline_tomlの0は未設定でpipe_tomlの上限が効く(tmp_path, zero):
    """D0051-AC-07: pipeline.toml の上限が 0・0.0・-0.0 のときは止まらず（load_config が通る）、未設定として扱う。
    段の定義（pipe.toml 相当）の上限が 1.5 なら、stage_budget_usd も sdk_options の値も 1.5 で、記録も 1.5。"""
    cfg = dev_cfg(tmp_path, {"requirements": zero})
    spec = dataclasses.replace(st.build_specs(cfg)["requirements"], max_budget_usd=1.5)
    assert stage_budget_usd(spec, cfg) == 1.5
    assert sdk_options(spec, cfg, resume=None)["max_budget_usd"] == 1.5
    entry = record_with_spec(cfg, 1.5)
    assert entry.get("max_budget_usd") == 1.5, f"記録の上限が {entry.get('max_budget_usd')!r}"


@ZEROS
def test_d0051_ac07_pipeline_tomlの0でpipe_tomlも無ければ上限なし_守る(tmp_path, zero):
    """D0051-AC-07: pipeline.toml の上限が 0・0.0・-0.0 で、段の定義にも上限が無いときは、stage_budget_usd も sdk_options の値も None で、
    記録に max_budget_usd の鍵は無い。（今のまま通る。守る）"""
    cfg = dev_cfg(tmp_path, {"requirements": zero})
    spec = st.build_specs(cfg)["requirements"]
    assert stage_budget_usd(spec, cfg) is None
    assert sdk_options(spec, cfg, resume=None)["max_budget_usd"] is None
    assert "max_budget_usd" not in record_with_spec(cfg, None)


@pytest.mark.parametrize("zero", [0.0, -0.0], ids=["float0", "negzero"])
def test_d0051_ac07_StageSpecを直に組んだ0_0と負の0_0も未設定(tmp_path, zero):
    """D0051-AC-07: load_pipe を通らずに StageSpec(max_budget_usd=0.0 か -0.0) を組んでも、stage_budget_usd は None、sdk_options の値も None
    （今は 0.0 がそのまま SDK に渡る）、記録に max_budget_usd の鍵は無い。SDK に渡す値と記録の値がずれない。"""
    cfg = dev_cfg(tmp_path)
    spec = dataclasses.replace(st.build_specs(cfg)["requirements"], max_budget_usd=zero)
    assert stage_budget_usd(spec, cfg) is None
    assert sdk_options(spec, cfg, resume=None)["max_budget_usd"] is None, "0.0 が SDK にそのまま渡る"
    assert "max_budget_usd" not in record_with_spec(cfg, zero)


COMBOS = [
    pytest.param(0.6, 1.5, 0.6, id="0.6-1.5"),
    pytest.param(None, 1.5, 1.5, id="none-1.5"),
    pytest.param(0.6, None, 0.6, id="0.6-none"),
    pytest.param(None, None, None, id="none-none-keep"),
    pytest.param(0, 1.5, 1.5, id="0-1.5"),
    pytest.param(0, None, None, id="0-none-keep"),
]


@pytest.mark.parametrize(("pipeline_value", "pipe_value", "expected"), COMBOS)
def test_d0051_ac08_sdk_optionsと記録の上限が同じ(tmp_path, pipeline_value, pipe_value, expected):
    """D0051-AC-08: （pipeline.toml, pipe.toml）＝（0.6, 1.5）→0.6、（なし, 1.5）→1.5、（0.6, なし）→0.6、（なし, なし）→なし、（0, 1.5）→1.5、
    （0, なし）→なし の 6 通りで、stage_budget_usd・sdk_options が SDK に渡す値・記録される値（鍵が無ければ None）が同じ。
    id の末尾が -keep の 2 通り（上限なし）は今のまま通る。"""
    cfg = dev_cfg(tmp_path, None if pipeline_value is None else {"requirements": pipeline_value})
    spec = dataclasses.replace(st.build_specs(cfg)["requirements"], max_budget_usd=pipe_value)
    assert sdk_options(spec, cfg, resume=None)["max_budget_usd"] == expected
    assert stage_budget_usd(spec, cfg) == expected
    entry = record_with_spec(cfg, pipe_value)
    assert entry.get("max_budget_usd") == expected, f"記録の上限が {entry.get('max_budget_usd')!r}（SDK に渡す値は {expected!r}）"


# ---- 確認待ち（--pause・--review）をまたぐとき：流したときの値が残る --------------------------------------


def paused_dev(project: Path) -> DevPipeline:
    """設定を読み直して作った、確認待ちで止める開発フロー（_load_pending が history を state.json から読む）。"""
    return DevPipeline(load_config(project, None, pause_for_review=True), runner=FakeRunner([]))


def test_d0051_ac09_pauseのあとで上限を変えてreviseすると流したときの値が残る(tmp_path):
    """D0051-AC-09: --pause で止めたあと、pipeline.toml の上限を 0.6 から 1.0 に変えて --review revise で続けると、
    前の回の要素は 0.6、続きの回の要素は 1.0 を持つ（流したときの値を残す）。"""
    write_toml(tmp_path, budget_toml(requirements=0.6))
    assert run_dev(paused_dev(tmp_path)) == Exit.AWAITING_REVIEW
    write_toml(tmp_path, budget_toml(requirements=1.0))
    assert asyncio.run(paused_dev(tmp_path).review(Decision("revise", "直して"))) == Exit.AWAITING_REVIEW
    reqs = stage_runs(dev_state(tmp_path), "requirements")
    assert [h.get("max_budget_usd") for h in reqs] == [0.6, 1.0]


def test_d0051_ac10_approveで続けても前の回の上限は残る(tmp_path):
    """D0051-AC-10: --pause で止めたあと、pipeline.toml の上限を 1.0 に変えて --review approve で続けても、前の回（requirements）の要素の
    上限は 0.6 のまま残り、次に流れた design の要素は 1.0。"""
    write_toml(tmp_path, budget_toml(requirements=0.6))
    assert run_dev(paused_dev(tmp_path)) == Exit.AWAITING_REVIEW
    write_toml(tmp_path, budget_toml(requirements=1.0, design=1.0))
    assert asyncio.run(paused_dev(tmp_path).review(Decision("approve"))) == Exit.AWAITING_REVIEW
    state = dev_state(tmp_path)
    assert [h.get("max_budget_usd") for h in stage_runs(state, "requirements")] == [0.6]
    assert [h.get("max_budget_usd") for h in stage_runs(state, "design")] == [1.0]


# ---- FR-03：resume を渡した実行に、続きの会話の印を残す ---------------------------------------------------


def test_d0051_ac11_resumeを渡した回にだけ印が付く(tmp_path):
    """D0051-AC-11: 上限 1.0 で、1 回目（resume を渡さない・会話 s-1）のあと、2 回目（resume = s-1）を流すと、2 回目の要素にだけ
    resumed が true で付き、1 回目の要素には付かない（どちらも max_budget_usd は 1.0）。"""
    cfg = dev_cfg(tmp_path, {"requirements": 1.0})
    cfg.work_dir.mkdir(parents=True)
    p = DevPipeline(cfg, runner=FakeRunner(["pass"]))
    first = asyncio.run(p._run("requirements", "指示"))
    asyncio.run(p._run("requirements", "直して", resume=first.session_id))
    one, two = p.history
    assert first.session_id == "s-1"
    assert (one.get("max_budget_usd"), two.get("max_budget_usd")) == (1.0, 1.0)
    assert "resumed" not in one
    assert two.get("resumed") is True, f"2 回目の要素に resumed が無い。今の鍵: {sorted(two)}"


@pytest.mark.parametrize("case", table_params("resumed"))
def test_d0051_ac11_本体が書く続きの会話の印は共通の表のとおり(tmp_path, case):
    """D0051-AC-11: 共通の表の 1 件ずつ。limit を pipeline.toml に書いて resume の有無で _run を 1 回流すと、runs[] の要素の resumed の
    有る無しと値が written と等しい（印は true だけ。上限が無い実行・resume を渡さない実行には付かない）。id の末尾が -keep のケースは今のまま通る。"""
    assert_key_as_written(entry_of_case(tmp_path, case), case, "resumed")


def test_d0051_ac12_pauseのあとのreviseの回にだけ印が付く(tmp_path):
    """D0051-AC-12: 上限 1.0 で --pause のあと、設定を変えずに --review revise で続けた回（会話の続きを渡す）の要素にだけ resumed が付き、
    前の回の要素には付かない（上限は両方 1.0）。"""
    write_toml(tmp_path, budget_toml(requirements=1.0))
    assert run_dev(paused_dev(tmp_path)) == Exit.AWAITING_REVIEW
    assert asyncio.run(paused_dev(tmp_path).review(Decision("revise", "直して"))) == Exit.AWAITING_REVIEW
    one, two = stage_runs(dev_state(tmp_path), "requirements")
    assert (one.get("max_budget_usd"), two.get("max_budget_usd")) == (1.0, 1.0)
    assert "resumed" not in one
    assert two.get("resumed") is True, f"revise の回の要素に resumed が無い。今の鍵: {sorted(two)}"


def test_d0051_ac13_要件定義の確認で修正と答えた再実行に印が付く(tmp_path):
    """D0051-AC-13: 上限 1.0 の開発フローで、要件定義の確認に端末で「修正」と答えて流れる再実行（人の指摘を反映。resume を渡す）の要素
    （note が「指摘を反映」）にだけ resumed が付き、1 つ目には付かない。"""
    answers = iter([Decision("revise", "未確定事項を減らして"), Decision("approve"), Decision("approve"), Decision("approve")])
    r = FakeRunner(["pass"])
    p = DevPipeline(dev_cfg(tmp_path, {"requirements": 1.0}, auto_approve=False), runner=r, ask=lambda s, d: next(answers))
    assert run_dev(p) == Exit.PASSED
    assert r.calls[1][1] == "s-1"  # 再実行は会話の続きを渡している
    one, two = stage_runs(dev_state(tmp_path), "requirements")
    assert two["note"] == "指摘を反映"
    assert (one.get("max_budget_usd"), two.get("max_budget_usd")) == (1.0, 1.0)
    assert "resumed" not in one
    assert two.get("resumed") is True, f"再実行の要素に resumed が無い。今の鍵: {sorted(two)}"


@pytest.mark.parametrize("kind", ["human", "missing_ac"])
def test_d0051_ac14_テスト先行の再実行2通りに印が付く(tmp_path, kind):
    """D0051-AC-14: 上限 1.0 のテスト先行の再実行 2 通り（red の確認で人が revise を返す回と、テストの無い AC を補う回。どちらも resume を渡す）で、
    red の 2 つ目の要素にだけ resumed が付き、1 つ目には付かない（上限は両方 1.0）。"""
    cfg = dev_cfg(tmp_path, {"red": 1.0}, auto_approve=(kind == "missing_ac"))
    if kind == "human":
        answers = iter([Decision("approve"), Decision("approve"), Decision("revise", "直して"), Decision("approve")])
        p = DevPipeline(cfg, runner=FakeRunner(["pass"]), ask=lambda s, d: next(answers))
        want = "指摘を反映"
    else:
        reds = [red_verdict("AC-01"), red_verdict("AC-01", "AC-02")]
        p = DevPipeline(cfg, runner=FakeRunner(["pass"], reds, two_acs=True))
        want = "抜けた受け入れ基準を補う"
    assert run_dev(p) == Exit.PASSED
    one, two = stage_runs(dev_state(tmp_path), "red")
    assert two["note"] == want
    assert (one.get("max_budget_usd"), two.get("max_budget_usd")) == (1.0, 1.0)
    assert "resumed" not in one
    assert two.get("resumed") is True, f"red の再実行の要素に resumed が無い。今の鍵: {sorted(two)}"


def test_d0051_ac15_パイプの指摘を反映する再実行に印が付く(tmp_path):
    """D0051-AC-15: pipe.toml の段 a に review = true と max_budget_usd = 1.5 を書いたパイプで、確認に revise を返した再実行（resume を渡す）の
    要素にだけ resumed が付き、1 つ目には付かない（上限は両方 1.5）。"""
    pipe = make_pipe(tmp_path, pipe_toml(pipe_stage("a", "review = true\nmax_budget_usd = 1.5\n")))
    answers = iter([Decision("revise", "直して"), Decision("approve")])
    runner = PipeRunner(pipe)
    assert run_pipe(tmp_path, pipe, runner, ask=lambda s, d: next(answers), auto_approve=False) == Exit.PASSED
    assert runner.calls[1][1] == "s-1"  # 再実行は会話の続きを渡している
    one, two = stage_runs(pipe_state(tmp_path), "a")
    assert two["note"] == "指摘を反映"
    assert (one.get("max_budget_usd"), two.get("max_budget_usd")) == (1.5, 1.5)
    assert "resumed" not in one
    assert two.get("resumed") is True, f"再実行の要素に resumed が無い。今の鍵: {sorted(two)}"


@pytest.mark.parametrize("kind", ["implement", "pipe"])
def test_d0051_ac16_resumeを渡さない再実行には印が付かない(tmp_path, kind):
    """D0051-AC-16: resume を渡さない再実行（開発フローの実装の差し戻し、パイプの検証の指摘を反映する再実行）の 2 つ目の要素は、
    上限が効いているので max_budget_usd を持つが、resumed は付かない。"""
    if kind == "implement":
        runner = FakeRunner(["fail", "pass"])
        assert run_dev(DevPipeline(dev_cfg(tmp_path, {"implement": 1.0}), runner=runner)) == Exit.PASSED
        state, stage, limit = dev_state(tmp_path), "implement", 1.0
        assert [c[1] for c in runner.calls if c[0] == "implement"] == [None, None]
    else:
        check = '[stages.check]\nverdict = true\non_fail = "draw"\n'
        pipe = make_pipe(tmp_path, pipe_toml(pipe_stage("draw", "max_budget_usd = 1.5\n"), pipe_stage("verify", check)))
        runner = PipeRunner(pipe, {"verify": [FAIL, PASS]})
        assert run_pipe(tmp_path, pipe, runner) == Exit.PASSED
        state, stage, limit = pipe_state(tmp_path), "draw", 1.5
        assert [c[1] for c in runner.calls if c[0] == "draw"] == [None, None]
    one, two = stage_runs(state, stage)
    assert (one.get("max_budget_usd"), two.get("max_budget_usd")) == (limit, limit), f"{stage} の 2 回目の要素に上限が無い: {sorted(two)}"
    assert not any("resumed" in h for h in (one, two))


# ---- FR-04：ほかの出力は変えない ---------------------------------------------------------------------


def fixed_pipeline(project: Path, limits: dict | None, runner) -> DevPipeline:
    p = DevPipeline(dev_cfg(project, limits), runner=runner)
    p.started_at = FIXED_START  # 99_summary.md と state.json の「開始」は秒まで入る。流すたびに変わらないように固定する
    return p


ALL_LIMITS = {stage: 0.6 for stage in st.STAGES}


def without_budget_keys(runs: list[dict]) -> list[dict]:
    return [{k: v for k, v in h.items() if k not in KEYS} for h in runs]


def test_d0051_ac17_上限の有無で出力が変わらない(tmp_path):
    """D0051-AC-17: 同じ偽の runner（実装の差し戻しを 1 回含む）で、上限あり（全部の段に 0.6）・なしを別の場所に流すと、終了コード・99_summary.md の全文・
    total_cost_usd・state.json の updated_at と runs[] の上限と印のほかの項目が同じ。上限ありの runs[] には max_budget_usd がある。"""
    plain, limited = make_project(tmp_path, "plain"), make_project(tmp_path, "limited")
    code_a = run_dev(fixed_pipeline(plain, None, FakeRunner(["fail", "pass"])))
    code_b = run_dev(fixed_pipeline(limited, ALL_LIMITS, FakeRunner(["fail", "pass"])))
    assert code_a == code_b == Exit.PASSED
    a, b = dev_state(plain), dev_state(limited)
    assert any("max_budget_usd" in h for h in b["runs"]), "上限ありの runs[] に max_budget_usd が無い"
    assert (limited / "docs/pipeline/99_summary.md").read_text(encoding="utf-8") == (plain / "docs/pipeline/99_summary.md").read_text(encoding="utf-8")
    assert a["total_cost_usd"] == b["total_cost_usd"]
    for state in (a, b):
        state.pop("updated_at")
        state["runs"] = without_budget_keys(state["runs"])
    assert a == b


@pytest.mark.parametrize("limit", [None, 1.0, 0], ids=["none", "1.0", "0"])
def test_d0051_ac18_record_doneの要素の項目は変わらない_守る(tmp_path, limit):
    """D0051-AC-18: pipe-in record done が書く要素の項目（cost_usd 0.0・num_turns 0・subtype success・metrics {}）は、pipeline.toml の
    max_budget_usd が無い・1.0・0 のどれでも今までと同じで、鍵の一覧も増えない。（今のまま通る。守る）"""
    want_keys = {
        "stage", "session_id", "is_error", "subtype", "result", "cost_usd", "num_turns", "duration_sec", "denials", "errors", "metrics",
        "seq", "attempt", "note",
    }
    if limit is not None:
        write_toml(tmp_path, budget_toml(requirements=limit))
    r = Recorder(load_config(tmp_path), now=lambda: datetime(2026, 10, 17, 10, 0, 0))
    r.start("足したい機能のメモ")
    r.begin("requirements")
    r.done("requirements", summary="要件定義を書いた")
    (entry,) = dev_state(tmp_path)["runs"]
    assert set(entry) == want_keys
    assert (entry["cost_usd"], entry["num_turns"], entry["subtype"], entry["metrics"]) == (0.0, 0, "success", {})


def test_d0051_ac19_開発フローの検証の段が上限で止まっても終了コード4のまま_守る(tmp_path):
    """D0051-AC-19: 開発フローの検証（test）の段（上限 0.6）の runner が、判定を返さず is_error が真で subtype が error_max_budget_usd の結果を返して
    終わるとき、判定は blocked になり、終了コードは今のまま 4（BLOCKED）。99_summary.md の文言（テストを実行できませんでした（環境などの問題））も今のまま。
    （今のまま通る。守る）"""
    cfg = dev_cfg(tmp_path, {"test": 0.6})
    assert run_dev(DevPipeline(cfg, runner=FakeRunner(["pass"], stop_stage="test"))) == Exit.BLOCKED
    state = dev_state(tmp_path)
    assert state["final"] == "BLOCKED"
    (verdict,) = [h["verdict"] for h in state["runs"] if "verdict" in h]
    assert verdict["status"] == "blocked" and verdict["summary"].startswith("テストの段から判定が返りませんでした")
    assert any(h.get("subtype") == STOPPED for h in stage_runs(state, "test"))
    summary = (tmp_path / "docs/pipeline/99_summary.md").read_text(encoding="utf-8")
    assert "テストを実行できませんでした（環境などの問題）" in summary


def test_d0051_ac19_パイプの段が上限で止まっても終了コード3のまま_守る(tmp_path):
    """D0051-AC-19: パイプの段（上限 1.5）が同じ終わり方（判定なし・is_error が真・subtype が error_max_budget_usd）をしたときは、
    今のまま 3（STAGE_ERROR）のまま（対象外）。（今のまま通る。守る）"""

    class StoppedRunner(PipeRunner):
        async def __call__(self, spec, prompt, cfg, *, resume, log_name):
            self.calls.append((spec.name, resume, prompt))
            return StageRun(stage=spec.name, session_id="s-1", is_error=True, subtype=STOPPED, cost_usd=1.5, num_turns=2)

    pipe = make_pipe(tmp_path, pipe_toml(pipe_stage("a", "max_budget_usd = 1.5\n"), pipe_stage("b")))
    runner = StoppedRunner(pipe)
    assert run_pipe(tmp_path, pipe, runner) == Exit.STAGE_ERROR
    assert [c[0] for c in runner.calls] == ["a"]
    assert pipe_state(tmp_path)["final"] == "STAGE_ERROR"


@pytest.mark.parametrize("subtype", ["success", STOPPED], ids=["success", "stopped"])
def test_d0051_ac107_完了行とliveの写しの段ごとの値が同じ(tmp_path, capsys, subtype):
    """D0051-AC-107: 同じ結果を返す runner で、上限を付けて流した実行と付けずに流した実行を比べると、端末に出る段の完了行（「<段> 完了／失敗・N ターン・$費用・時間」を
    含む全部の出力）と、pipe-in live の写しが作る段ごとの値（費用・ターン数など）が同じ。結果が error_max_budget_usd（is_error が真）で終わる
    ものも同じ。上限ありの state.json には max_budget_usd がある。"""
    stop = None if subtype == "success" else "requirements"
    plain, limited = make_project(tmp_path, "plain"), make_project(tmp_path, "limited")
    outs, snaps = [], []
    for project, limits in ((plain, None), (limited, ALL_LIMITS)):
        p = fixed_pipeline(project, limits, FakeRunner(["pass"], stop_stage=stop, cost=0.42, duration=1.5))
        run_dev(p)
        outs.append(capsys.readouterr().out)
        work = project / "docs" / "pipeline"
        snaps.append(live.build_snapshot(live.read_state(work), None, now=FIXED_NOW)["stages"])
    assert any("max_budget_usd" in h for h in dev_state(limited)["runs"]), "上限ありの runs[] に max_budget_usd が無い"
    assert ("失敗" if stop else "完了") in outs[0] and "$0.420" in outs[0]
    assert outs[0] == outs[1]
    assert snaps[0] == snaps[1]
    assert snaps[0][0]["cost_usd"] == 0.42
