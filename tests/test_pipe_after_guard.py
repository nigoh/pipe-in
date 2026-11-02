"""後ろのパイプの段が、前の記録（前の state.json・00_input.md・logs/・成果物）を書けないことを、SDK を呼ばずに確かめる（D0069-FR-15）。

前の記録は LinearPipeline.receive で受けさせ、その後に段の書き込みの判定（check_tool）を通す。
ファイルは tmp_path の中だけに作り、今までの置き場所も tmp_path に向ける。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pipe_in.engine.checkpoint import Decision
from pipe_in.engine.config import load_config
from pipe_in.engine.guard import check_tool
from pipe_in.engine.pipeline import STATE, Exit
from pipe_in.engine.runner import StageRun
from pipe_in.pipe import definition as pd
from pipe_in.pipe.pipeline import LinearPipeline


@pytest.fixture(autouse=True)
def pipes_elsewhere(tmp_path, monkeypatch):
    """今までの置き場所を tmp_path に向ける（リポジトリの pipes/ を見ない）。"""
    monkeypatch.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "shared"))


class ScriptedRunner:
    """SDK の代わり。段の成果物を書き、構造化出力は返さない（tests/test_pipe_flow.py の形）。"""

    def __init__(self):
        self.calls: list[tuple[str, str | None, str]] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append((spec.name, resume, prompt))
        (cfg.work_dir / spec.output).write_text(f"# {spec.name}\n", encoding="utf-8")
        return StageRun(stage=spec.name, session_id=f"s-{len(self.calls)}", structured=None, cost_usd=0.01, num_turns=1)


async def no_sdk(spec, prompt, cfg, *, resume, log_name):
    raise AssertionError(f"SDK を呼ばないはずの場面で段「{spec.name}」が呼ばれました")


def project_of(tmp_path: Path) -> Path:
    p = tmp_path / "app"
    p.mkdir(exist_ok=True)
    return p


def stage(name: str, label: str, output: str, *, access: str = "read", extra: str = "") -> str:
    return f'\n[[stages]]\nname = "{name}"\nlabel = "{label}"\noutput = "{output}"\naccess = "{access}"\nprompt = "{label}をする"\n{extra}'


def pipe_toml(*stages: str) -> str:
    return '[pipe]\nkind = "linear"\nlabel = "試し"\ninput = "optional"\n' + "".join(stages)


# 型（read・docs・tests・code）を一通り並べる。docs の docs_dir は docs（記録を含む、いちばん広い場合）
GUARD = pipe_toml(
    stage("read", "読む", "01_read.md", access="read"),
    stage("docs", "文書", "02_docs.md", access="docs", extra='docs_dir = "docs"\n'),
    stage("tests", "テスト", "03_tests.md", access="tests"),
    stage("code", "実装", "04_code.md", access="code", extra="bash = true\n"),
)
# 確認で止まったあとの続き（--review）を確かめる用：最初の段で確認を取る
REVIEW = pipe_toml(
    stage("survey", "調査", "01_survey.md", access="read", extra="review = true\n"),
    stage("code", "実装", "04_code.md", access="code", extra="bash = true\n"),
)

# 前の記録（linear：<work_dir>/<前の名前>/）。dir は作業フォルダ（docs/pipeline）からの相対
RECORD = {
    "pipe": "diagrams",
    "kind": "linear",
    "updated_at": "2026-10-30T10:00:00",
    "dir": "diagrams",
    "artifacts": [{"stage": "仕様の調査", "path": "diagrams/01_survey.md"}],
}
# 前の記録（dev：記録は作業フォルダ直下）
DEV_RECORD = {
    "pipe": "spec",
    "kind": "dev",
    "updated_at": "2026-10-30T10:00:00",
    "dir": ".",
    "artifacts": [{"stage": "調査", "path": "01_survey.md"}],
}


def make_pipe(project: Path, toml: str, name: str) -> pd.PipeDef:
    d = project / ".pipe-in" / "pipes" / f"pipe-in-{name}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pipe.toml").write_text(toml, encoding="utf-8")
    return pd.load_pipe(d)


def guard_of(tmp_path: Path, stage_name: str, record: dict = RECORD, toml: str = GUARD):
    """前の記録を受けた後ろのパイプの、段の書き込みの判定。"""
    project = project_of(tmp_path)
    later = make_pipe(project, toml, "spec-qa")
    cfg = load_config(project, None, auto_approve=True).for_pipe("spec-qa", own_work_dir=True)
    p = LinearPipeline(cfg, later, runner=no_sdk)
    p.receive(dict(record))
    return cfg, p.specs[stage_name]


def check(cfg, spec, tool: str, tool_input: dict):
    return check_tool(
        tool,
        tool_input,
        project_dir=cfg.project_dir,
        can_write=spec.can_write,
        allow_bash=spec.allow_bash,
        write_scope_hint=spec.write_scope_hint,
        allowed_tools=spec.allowed_tools,
        fetch_domains=spec.fetch_domains,
    )


PREV_STATE = "docs/pipeline/diagrams/state.json"
TOOL_FIELD = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}


# ---- D0069-AC-15：前の記録は、どの段の Write・Edit でも書けない ---------------------------------


@pytest.mark.parametrize("stage_name", ["read", "docs", "tests", "code"])
@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit", "NotebookEdit"])
def test_d0069_ac15_code_tests_docs_read_段は前の記録へ_Write_Edit_で書けない(tmp_path, stage_name, tool):
    """D0069-AC-15: code・docs・tests・read の段が、前の記録（state.json）へ Write・Edit（MultiEdit・NotebookEdit も）で書こうとすると止まる。"""
    cfg, spec = guard_of(tmp_path, stage_name)
    reason = check(cfg, spec, tool, {TOOL_FIELD[tool]: PREV_STATE})
    assert reason is not None, f"{stage_name} 段が {tool} で前の記録に書けてしまいます"


@pytest.mark.parametrize(
    "path",
    [
        "docs/pipeline/diagrams/state.json",
        "docs/pipeline/diagrams/00_input.md",
        "docs/pipeline/diagrams/01_survey.md",
        "docs/pipeline/diagrams/logs/01_run.txt",
    ],
    ids=["state.json", "00_input.md", "成果物", "logs"],
)
def test_d0069_ac15_前の記録の中の全部を_code_段は書けない(tmp_path, path):
    """D0069-AC-15: 前の記録（state.json・00_input.md・成果物・logs/）は、code 段の Write では書けない。"""
    cfg, spec = guard_of(tmp_path, "code")
    assert check(cfg, spec, "Write", {"file_path": path}) is not None, path


def test_d0069_ac15_テスト段は記録の中のテストらしいファイルも書けない(tmp_path):
    """D0069-AC-15: tests 段は、前の記録の中のテストらしいファイル（test_*.py）も書けない。"""
    cfg, spec = guard_of(tmp_path, "tests")
    assert check(cfg, spec, "Write", {"file_path": "docs/pipeline/diagrams/test_survey.py"}) is not None


# ---- D0069-AC-15：Bash の書き込みの形でも、前の記録へ書けない -------------------------------------

BASH_WRITES = [
    "echo x > docs/pipeline/diagrams/state.json",
    "echo x | tee docs/pipeline/diagrams/01_survey.md",
    "cp notes.md docs/pipeline/diagrams/01_survey.md",
    "mv notes.md docs/pipeline/diagrams/01_survey.md",
    "rm docs/pipeline/diagrams/01_survey.md",
    "sed -i 's/a/b/' docs/pipeline/diagrams/state.json",
    "touch docs/pipeline/diagrams/00_input.md",
    "python -c \"open('docs/pipeline/diagrams/state.json', 'w').write('x')\"",
    "dd if=/dev/zero of=docs/pipeline/diagrams/state.json count=1",
    "node -e \"require('fs').writeFileSync('docs/pipeline/diagrams/state.json', 'x')\"",
    "bash -c \"echo x > docs/pipeline/diagrams/state.json\"",
]


@pytest.mark.parametrize("command", BASH_WRITES, ids=[
    "リダイレクト", "tee", "cp", "mv", "rm", "sed -i", "touch", "python -c", "dd", "node -e", "bash -c",
])
def test_d0069_ac15_Bash_の書き込みの形でも前の記録へ書けない(tmp_path, command):
    """D0069-AC-15: 同じ場所への Bash の書き込み（リダイレクト・tee・cp・mv など）も、code 段は止められる。"""
    cfg, spec = guard_of(tmp_path, "code")
    assert check(cfg, spec, "Bash", {"command": command}) is not None, command


# ---- D0069-AC-15：フォルダごと消す・動かす操作で前の記録を含むフォルダを消せない --------------------


@pytest.mark.parametrize(
    "command",
    ["find docs/pipeline -delete", "rmdir docs/pipeline/diagrams", "mv docs/pipeline/diagrams docs/old-diagrams"],
    ids=["find -delete", "rmdir", "mv フォルダ"],
)
def test_d0069_ac15_フォルダ操作で前の記録を含むフォルダを消せない(tmp_path, command):
    """D0069-AC-15: 前の記録のフォルダや、その中身を含むフォルダ（docs/pipeline）を、rmdir・mv・find -delete で消す・動かせない。"""
    cfg, spec = guard_of(tmp_path, "code")
    assert check(cfg, spec, "Bash", {"command": command}) is not None, command


# ---- D0069-AC-15：後ろ自身の成果物・製品コードは、今までどおり書ける ----------------------------


def test_d0069_ac15_後ろ自身の成果物と自分の記録への書き込みは止めない(tmp_path):
    """D0069-AC-15: 後ろ自身の成果物（<後ろ>/04_code.md）への書き込みは、前の記録を受けても止めない。"""
    cfg, spec = guard_of(tmp_path, "code")
    assert check(cfg, spec, "Write", {"file_path": "docs/pipeline/spec-qa/04_code.md"}) is None
    assert check(cfg, spec, "Bash", {"command": "echo x > docs/pipeline/spec-qa/04_code.md"}) is None
    cfg2, docs_spec = guard_of(tmp_path, "docs")
    assert check(cfg2, docs_spec, "Write", {"file_path": "docs/pipeline/spec-qa/02_docs.md"}) is None


def test_d0069_ac15_今までどおり製品コードは書ける(tmp_path):
    """D0069-AC-15: 前の記録を受けても、code 段は製品コード（src/）を今までどおり書ける。"""
    cfg, spec = guard_of(tmp_path, "code")
    assert check(cfg, spec, "Write", {"file_path": "src/app.py"}) is None
    assert check(cfg, spec, "Bash", {"command": "echo x > src/app.py"}) is None


# ---- D0069-AC-15：dev の記録（作業フォルダ直下）も、code 段は書けない --------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "docs/pipeline/state.json",
        "docs/pipeline/00_input.md",
        "docs/pipeline/99_summary.md",
        "docs/pipeline/01_survey.md",
        "docs/pipeline/logs/01_run.txt",
    ],
    ids=["state.json", "00_input.md", "99_summary.md", "成果物", "logs"],
)
def test_d0069_ac15_dev_の記録作業フォルダ直下を_code_段が書けない(tmp_path, path):
    """D0069-AC-15: 前が kind = dev のとき、作業フォルダ直下の記録（state.json・00_input.md・99_summary.md・成果物・logs/）は書けない。後ろ自身の記録は書ける。"""
    cfg, spec = guard_of(tmp_path, "code", record=DEV_RECORD)
    assert check(cfg, spec, "Write", {"file_path": path}) is not None, path
    assert check(cfg, spec, "Write", {"file_path": "docs/pipeline/spec-qa/04_code.md"}) is None


# ---- D0069-AC-15：再開（--review）でも、前の記録の守りが掛かる ---------------------------------


def test_d0069_ac15_再開_review_でも前の記録の守りは掛かる(tmp_path):
    """D0069-AC-15: 確認待ちから --review で続けるとき、受けた元（received_from）から守りを作り直し、前の記録は書けない。"""
    project = project_of(tmp_path)
    later = make_pipe(project, REVIEW, "spec-qa")
    rec = project / "docs/pipeline/spec-qa"
    rec.mkdir(parents=True)
    (rec / "01_survey.md").write_text("# 調査\n", encoding="utf-8")
    (rec / STATE).write_text(
        json.dumps(
            {
                "pipe": "spec-qa",
                "updated_at": "2026-10-30T10:00:00",
                "pending_review": {
                    "stage": "survey",
                    "session_id": "s-1",
                    "doc": "docs/pipeline/spec-qa/01_survey.md",
                    "since": "2026-10-30T10:00:00+09:00",
                },
                "received_from": dict(RECORD),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cfg = load_config(project, None, auto_approve=False, pause_for_review=True).for_pipe("spec-qa", own_work_dir=True)
    p = LinearPipeline(cfg, later, runner=ScriptedRunner())
    assert asyncio.run(p.review(Decision("approve"))) == Exit.PASSED
    assert check(cfg, p.specs["code"], "Write", {"file_path": PREV_STATE}) is not None
    assert check(cfg, p.specs["code"], "Write", {"file_path": "src/app.py"}) is None
