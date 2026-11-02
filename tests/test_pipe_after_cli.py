"""コマンドラインの --after（D0069）を、SDK を呼ばずに確かめる。cli.main を呼び、runner を偽物に差し替える。

ファイルは tmp_path の中だけに作る。今までの置き場所（PIPE_IN_PIPES_DIR）も tmp_path に向ける。
断るときは SystemExit に文字列を渡す（終了コード 1）。その文字列の中身と、後ろの記録が作られないことを確かめる。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pipe_in import cli
from pipe_in.engine.pipeline import STATE, Exit
from pipe_in.engine.runner import StageRun
from pipe_in.pipe import definition as pd
from pipe_in.pipe.pipeline import LinearPipeline


@pytest.fixture(autouse=True)
def pipes_elsewhere(tmp_path, monkeypatch):
    """今までの置き場所を tmp_path に向ける（リポジトリの pipes/ を見ない）。"""
    monkeypatch.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "shared"))


class ScriptedRunner:
    """SDK の代わり。呼ばれた段を記録し、成果物を書く（tests/test_pipe_flow.py の形）。"""

    def __init__(self):
        self.calls: list[tuple[str, str | None, str]] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append((spec.name, resume, prompt))
        (cfg.work_dir / spec.output).write_text(f"# {spec.name}\n", encoding="utf-8")
        return StageRun(stage=spec.name, session_id=f"s-{len(self.calls)}", structured=None, cost_usd=0.01, num_turns=1)


def use_runner(monkeypatch, runner) -> None:
    """cli が作るパイプの runner を偽物に差し替える（それ以外は本物の組み立て）。"""
    real = cli.pipeline_for

    def fake(cfg, pipe, **kw):
        p = real(cfg, pipe, **kw)
        p.runner = runner
        return p

    monkeypatch.setattr(cli, "pipeline_for", fake)


@pytest.fixture
def fake_run(monkeypatch):
    """流れの本体（LinearPipeline.run）を偽にして、ここまで届いたことだけを見る。"""

    async def run(self, input_text, from_stage=None):
        print("流れ開始")
        return Exit.PASSED

    monkeypatch.setattr(LinearPipeline, "run", run)


def project_of(tmp_path: Path) -> Path:
    p = tmp_path / "app"
    p.mkdir(exist_ok=True)
    return p


def stage(name: str, label: str, output: str, extra: str = "") -> str:
    return f'\n[[stages]]\nname = "{name}"\nlabel = "{label}"\noutput = "{output}"\naccess = "read"\nprompt = "{label}をする"\n{extra}'


def pipe_toml(*stages: str, kind: str = "linear") -> str:
    return f'[pipe]\nkind = "{kind}"\nlabel = "試し"\ninput = "optional"\n' + "".join(stages)


PREV = pipe_toml(stage("survey", "仕様の調査", "01_survey.md"), stage("draw", "図を描く", "02_draw.md"))
LATER = pipe_toml(stage("report", "報告", "02_report.md"))


def write_pipe(project: Path, name: str, toml: str) -> None:
    d = project / ".pipe-in" / "pipes" / f"pipe-in-{name}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pipe.toml").write_text(toml, encoding="utf-8")


def write_record(
    folder: Path,
    pipe: str,
    *,
    final: str | None = "PASSED",
    files: bool = True,
    updated_at: str | None = "2026-10-30T10:00:00",
) -> Path:
    """前の記録（state.json と成果物）を手で書く。"""
    folder.mkdir(parents=True, exist_ok=True)
    stages = (("仕様の調査", "01_survey.md"), ("図を描く", "02_draw.md"))
    data: dict = {
        "pipe": pipe,
        "stages": [{"name": f"s{i}", "label": label, "output": out} for i, (label, out) in enumerate(stages)],
    }
    if updated_at is not None:
        data["updated_at"] = updated_at
    if final is not None:
        data["final"] = final
    path = folder / STATE
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if files:
        for _, out in stages:
            (folder / out).write_text("# 成果物\n", encoding="utf-8")
    return path


def argv(project: Path, *extra: str, pipe: bool = True) -> list[str]:
    """始めるときの引数（依頼メモは --text、確認は --yes）。"""
    head = ["--project", str(project)] + (["--pipe", "later"] if pipe else [])
    return head + ["--text", "依頼", "--yes", *extra]


# ---- D0069-AC-06：--after を2つ書くと断る ---------------------------------------------------


def test_d0069_ac06_after_を2つ書くと断る(tmp_path, monkeypatch):
    """D0069-AC-06: --after を2つ以上書いたとき断る（終了コード 1。runner を呼ばない）。"""
    project = project_of(tmp_path)
    write_pipe(project, "later", LATER)
    write_record(project / "docs/pipeline/diagrams", "diagrams")
    runner = ScriptedRunner()
    use_runner(monkeypatch, runner)
    with pytest.raises(SystemExit) as e:
        cli.main(argv(project, "--after", "diagrams", "--after", "diagrams"))
    assert isinstance(e.value.code, str) and "--after" in e.value.code, e.value.code
    assert runner.calls == []


# ---- D0069-AC-08：--pipe なし（組み込みの開発フロー）に --after を付けると断る ---------------


def test_d0069_ac08_pipe_なしで_after_を付けると断る(tmp_path, monkeypatch):
    """D0069-AC-08: --pipe なし（組み込みの開発フロー）に --after を付けたとき断る。"""
    project = project_of(tmp_path)
    write_pipe(project, "later", LATER)
    write_record(project / "docs/pipeline/diagrams", "diagrams")
    runner = ScriptedRunner()
    use_runner(monkeypatch, runner)
    with pytest.raises(SystemExit) as e:
        cli.main(argv(project, "--after", "diagrams", pipe=False))
    assert isinstance(e.value.code, str) and "--pipe" in e.value.code, e.value.code
    assert runner.calls == []


# ---- D0069-AC-14：--review・--from と一緒に --after は断る -----------------------------------


def test_d0069_ac14_review_と一緒に_after_は断る(tmp_path, monkeypatch):
    """D0069-AC-14: --review と一緒に --after を付けたとき断る（runner を呼ばない）。"""
    project = project_of(tmp_path)
    write_pipe(project, "later", LATER)
    write_record(project / "docs/pipeline/diagrams", "diagrams")
    runner = ScriptedRunner()
    use_runner(monkeypatch, runner)
    with pytest.raises(SystemExit) as e:
        cli.main(["--project", str(project), "--pipe", "later", "--after", "diagrams", "--review", "approve"])
    assert isinstance(e.value.code, str) and "始めるときだけ" in e.value.code, e.value.code
    assert runner.calls == []


def test_d0069_ac14_from_と一緒に_after_は断る(tmp_path, monkeypatch):
    """D0069-AC-14: --from と一緒に --after を付けたとき断る（続きは記録の受けた元を使うため）。"""
    project = project_of(tmp_path)
    write_pipe(project, "later", LATER)
    write_record(project / "docs/pipeline/diagrams", "diagrams")
    runner = ScriptedRunner()
    use_runner(monkeypatch, runner)
    with pytest.raises(SystemExit) as e:
        cli.main(argv(project, "--after", "diagrams", "--from", "report"))
    assert isinstance(e.value.code, str) and "--from" in e.value.code, e.value.code
    assert runner.calls == []


# ---- D0069-AC-09：流す前に、前の名前・結果・終わった日時を出す --------------------------------


def test_d0069_ac09_流す前に前の名前_PASSED_終わった日時を出す(tmp_path, monkeypatch, capsys, fake_run):
    """D0069-AC-09: 流す前に、前のパイプの名前・結果（PASSED）・終わった日時（updated_at）を画面に出す。"""
    project = project_of(tmp_path)
    write_pipe(project, "later", LATER)
    write_pipe(project, "diagrams", PREV)
    write_record(project / "docs/pipeline/diagrams", "diagrams", updated_at="2026-10-30T10:00:00")
    use_runner(monkeypatch, ScriptedRunner())
    assert cli.main(argv(project, "--after", "diagrams")) == 0
    out = capsys.readouterr().out
    assert "diagrams" in out and "PASSED" in out and "2026-10-30T10:00:00" in out, out
    assert out.index("PASSED") < out.index("流れ開始"), out


def test_d0069_ac09_updated_at_が無いと不明と出て断らない(tmp_path, monkeypatch, capsys, fake_run):
    """D0069-AC-09: updated_at が無い前の記録では「不明」と出て、断らない。"""
    project = project_of(tmp_path)
    write_pipe(project, "later", LATER)
    write_pipe(project, "diagrams", PREV)
    write_record(project / "docs/pipeline/diagrams", "diagrams", updated_at=None)
    use_runner(monkeypatch, ScriptedRunner())
    assert cli.main(argv(project, "--after", "diagrams")) == 0
    out = capsys.readouterr().out
    assert "不明" in out and "流れ開始" in out, out


def test_d0069_ac09_1年以上前でも断らず警告を出さない(tmp_path, monkeypatch, capsys, fake_run):
    """D0069-AC-09: updated_at が1年以上前の記録でも断らず、警告も出さない（古さは判定しない）。"""
    project = project_of(tmp_path)
    write_pipe(project, "later", LATER)
    write_pipe(project, "diagrams", PREV)
    write_record(project / "docs/pipeline/diagrams", "diagrams", updated_at="2024-01-01T09:00:00")
    use_runner(monkeypatch, ScriptedRunner())
    assert cli.main(argv(project, "--after", "diagrams")) == 0
    out = capsys.readouterr().out
    assert "流れ開始" in out, out
    assert "⚠" not in out and "古" not in out, out


# ---- D0069-AC-18：断るときは終了コード 1 で止まり、後ろの記録を作らず書き換えない -----------------

CASES = [
    # （名前, 前の記録の作り方, --after の値, --pipe を付けるか, 後ろが kind = dev か）
    ("前の記録が無い", "none", ["diagrams"], True, False),
    ("途中", "running", ["diagrams"], True, False),
    ("失敗", "failed", ["diagrams"], True, False),
    ("pipe なし", "passed", ["diagrams"], False, False),
    ("後ろが kind dev", "passed", ["diagrams"], True, True),
    ("同じ名前", "passed", ["later"], True, False),
    ("2つ書いた", "passed", ["diagrams", "diagrams"], True, False),
    ("名前でない値", "passed", ["a/b"], True, False),
]


@pytest.mark.parametrize("case,prev,values,with_pipe,later_dev", CASES, ids=[c[0] for c in CASES])
def test_d0069_ac18_断るときは終了コード1で止まり_後ろの記録を作らず書き換えない(tmp_path, monkeypatch, case, prev, values, with_pipe, later_dev):
    """D0069-AC-18: AC-02〜AC-08 で断るどの場合も、後ろの記録（<work_dir>/<後ろ>/）を作らず・書き換えず、runner を呼ばず、終了コード 1 で止まる。"""
    project = project_of(tmp_path)
    write_pipe(project, "diagrams", PREV)
    write_pipe(project, "later", pipe_toml(kind="dev") if later_dev else LATER)
    rec = project / "docs/pipeline/diagrams"
    if prev == "passed":
        write_record(rec, "diagrams")
    elif prev == "running":
        write_record(rec, "diagrams", final=None)
    elif prev == "failed":
        write_record(rec, "diagrams", final="STAGE_ERROR")
    later_dir = project / "docs/pipeline/later"
    later_dir.mkdir(parents=True)
    kept = later_dir / STATE
    kept.write_bytes(b'{"pipe": "later", "final": "PASSED"}\n')
    before = kept.read_bytes()
    runner = ScriptedRunner()
    use_runner(monkeypatch, runner)
    args = (["--project", str(project)] + (["--pipe", "later"] if with_pipe else []) + ["--text", "依頼", "--yes"])
    for v in values:
        args += ["--after", v]
    with pytest.raises(SystemExit) as e:
        cli.main(args)
    assert isinstance(e.value.code, str), e.value.code  # 文字を渡す SystemExit は終了コード 1
    assert kept.read_bytes() == before
    assert sorted(p.name for p in later_dir.iterdir()) == [STATE]
    assert runner.calls == []
