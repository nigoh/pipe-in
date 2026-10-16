"""devpipe record：/pipe-in が、SDK を呼ばずに開発フローと同じ形の記録（docs/pipeline/）を書く。

VSCode の拡張がそのまま図にできるように、devpipe 本体が書く state.json と同じ形にする。
見本は tests/fixtures/pipe_in/ にあり、拡張のテスト（vscode/src/domain/pipeInRecord.test.ts）も同じ見本を読む。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from devpipe import cli
from devpipe.dev.pipeline import DevPipeline
from devpipe.dev.record import RecordError, Recorder
from devpipe.engine.checkpoint import Decision
from devpipe.engine.config import load_config

FIXTURES = Path(__file__).parent / "fixtures" / "pipe_in"
FIXED = datetime(2026, 10, 17, 10, 0, 0)


def recorder(project: Path, now=lambda: FIXED) -> Recorder:
    return Recorder(load_config(project), now=now)


def state(project: Path) -> dict:
    return json.loads((project / "docs" / "pipeline" / "state.json").read_text(encoding="utf-8"))


def up_to_waiting(r: Recorder) -> None:
    """要件定義（直してもらって承認）→ 設計 → テスト先行（赤）→ 確認待ち。"""
    r.start("足したい機能のメモ")
    r.begin("requirements")
    r.done("requirements", summary="要件定義を書いた")
    r.wait("requirements")
    r.review("requirements", "revise", feedback="AC を分けて")
    r.begin("requirements", note="指摘を反映")
    r.done("requirements", summary="直した")
    r.wait("requirements")
    r.review("requirements", "approved")
    r.begin("design")
    r.done("design", summary="設計を書いた")
    r.wait("design")
    r.review("design", "approved")
    r.begin("red")
    r.done("red", summary="テストを書いた")
    r.red("red", "AC-01 が赤", tests=[("AC-01", "tests/test_a.py::test_a")], commands=["python -m pytest -q"])
    r.wait("red")


def to_finish(r: Recorder) -> None:
    r.review("red", "approved")
    r.begin("implement", attempt=1)
    r.done("implement", summary="実装した")
    r.begin("test", attempt=1)
    r.done("test", summary="検証した")
    r.verdict("fail", 1, "AC-01 不合格", failures=[("AC-01", "期待と違う")], commands=["python -m pytest -q"])
    r.begin("implement", attempt=2, note="差し戻し")
    r.done("implement", summary="直した")
    r.begin("test", attempt=2)
    r.done("test", summary="検証した")
    r.verdict("pass", 2, "すべて合格", commands=["python -m pytest -q"])
    r.finish("PASSED")


def fixture_state(name: str) -> dict:
    return json.loads((FIXTURES / name / "state.json").read_text(encoding="utf-8"))


# ---- AC-01・AC-03：本体と同じ形（拡張が読む見本と同じ） -------------------------


def test_ac01_running_matches_fixture(tmp_path):
    r = recorder(tmp_path)
    r.start("足したい機能のメモ")
    r.begin("requirements")
    assert state(tmp_path) == fixture_state("running")
    log = tmp_path / "docs" / "pipeline" / "logs" / "01_requirements.jsonl"
    want = (FIXTURES / "running" / "logs" / "01_requirements.jsonl").read_text(encoding="utf-8")
    assert [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] == [json.loads(x) for x in want.splitlines()]
    assert (tmp_path / "docs" / "pipeline" / "00_input.md").read_text(encoding="utf-8").strip() == "足したい機能のメモ"


def test_ac01_waiting_matches_fixture(tmp_path):
    up_to_waiting(recorder(tmp_path))
    assert state(tmp_path) == fixture_state("waiting")


def test_ac01_finished_matches_fixture(tmp_path):
    r = recorder(tmp_path)
    up_to_waiting(r)
    to_finish(r)
    assert state(tmp_path) == fixture_state("finished")
    summary = (tmp_path / "docs" / "pipeline" / "99_summary.md").read_text(encoding="utf-8")
    assert "PASSED" in summary or "終わりました" in summary


def test_ac03_done_closes_log_and_measures_time(tmp_path):
    clock = [FIXED]
    r = recorder(tmp_path, now=lambda: clock[0])
    r.start("メモ")
    r.begin("requirements")
    clock[0] = FIXED + timedelta(seconds=90)
    r.done("requirements", summary="書いた")
    runs = state(tmp_path)["runs"]
    assert runs[-1]["duration_sec"] == 90.0
    lines = [json.loads(x) for x in (tmp_path / "docs/pipeline/logs/01_requirements.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines[0]["_type"] == "Prompt"
    assert lines[-1]["_type"] == "ResultMessage"
    assert any(x["_type"] == "AssistantMessage" and x["content"][0]["text"] == "書いた" for x in lines)


def test_ac03_attempt_goes_into_log_name(tmp_path):
    r = recorder(tmp_path)
    r.start("メモ")
    r.begin("implement", attempt=2)
    assert (tmp_path / "docs/pipeline/logs/01_implement_2.jsonl").is_file()


def test_ac03_error_run(tmp_path):
    r = recorder(tmp_path)
    r.start("メモ")
    r.begin("design")
    r.done("design", summary="止まった", error=True)
    run = state(tmp_path)["runs"][-1]
    assert run["is_error"] is True and run["subtype"] == "error"


def test_ac03_begin_clears_pending_review(tmp_path):
    r = recorder(tmp_path)
    r.start("メモ")
    r.begin("requirements")
    r.done("requirements")
    r.wait("requirements")
    assert state(tmp_path)["pending_review"]["stage"] == "requirements"
    r.review("requirements", "approved")
    assert state(tmp_path)["pending_review"] is None


@pytest.mark.parametrize(
    "call",
    [
        lambda r: r.begin("deploy"),
        lambda r: r.done("design"),  # 始めていない段は閉じられない
        lambda r: r.review("design", "maybe"),
        lambda r: r.review("design", "revise"),  # 直してほしい点がない
        lambda r: r.red("green", "x"),
        lambda r: r.verdict("ok", 1, "x"),
        lambda r: r.finish("DONE"),
    ],
)
def test_ac03_rejects_wrong_input(tmp_path, call):
    r = recorder(tmp_path)
    r.start("メモ")
    with pytest.raises(RecordError):
        call(r)


def test_ac03_refuses_to_start_over_a_run_in_progress(tmp_path):
    r = recorder(tmp_path)
    r.start("メモ")
    r.begin("requirements")
    r.done("requirements")
    with pytest.raises(RecordError, match="途中"):
        recorder(tmp_path).start("別のメモ")
    assert state(tmp_path)["runs"]  # 消えていない


def test_ac03_archives_a_finished_run_before_starting(tmp_path):
    r = recorder(tmp_path)
    up_to_waiting(r)
    to_finish(r)
    recorder(tmp_path).start("次のメモ")
    w = tmp_path / "docs" / "pipeline"
    archived = [p for p in (w / "archive").iterdir() if p.is_dir()]
    assert len(archived) == 1
    assert json.loads((archived[0] / "state.json").read_text(encoding="utf-8"))["final"] == "PASSED"
    assert (archived[0] / "99_summary.md").is_file()
    assert state(tmp_path)["runs"] == [] and state(tmp_path)["final"] is None
    assert not (w / "99_summary.md").exists()
    assert (w / "00_input.md").read_text(encoding="utf-8").strip() == "次のメモ"


def test_ac03_devpipe_review_refuses_a_pipe_in_record(tmp_path):
    """/pipe-in の記録の続きを、devpipe --review が SDK で流してしまわない。"""
    up_to_waiting(recorder(tmp_path))
    called = []

    async def runner(*a, **k):
        called.append(a)
        raise AssertionError("SDK を呼んではいけない")

    cfg = load_config(tmp_path, pause_for_review=True)
    with pytest.raises(SystemExit, match="pipe-in"):
        asyncio.run(DevPipeline(cfg, runner=runner).review(Decision("approve", "")))
    assert not called


# ---- コマンド（devpipe record …） ----------------------------------------------


def test_ac03_cli_writes_the_same_record(tmp_path):
    p = str(tmp_path)
    assert cli.main(["record", "start", "--project", p, "--text", "メモ"]) == 0
    assert cli.main(["record", "begin", "requirements", "--project", p]) == 0
    assert cli.main(["record", "done", "requirements", "--project", p, "--summary", "書いた"]) == 0
    assert cli.main(["record", "wait", "requirements", "--project", p]) == 0
    assert state(tmp_path)["pending_review"]["doc"] == "docs/pipeline/01_requirements.md"
    assert cli.main(["record", "review", "requirements", "approved", "--project", p]) == 0
    assert cli.main(["record", "begin", "red", "--project", p]) == 0
    assert cli.main(["record", "done", "red", "--project", p]) == 0
    assert cli.main(["record", "red", "red", "--project", p, "--summary", "赤", "--test", "AC-01=tests/test_a.py::test_a", "--command", "python -m pytest -q"]) == 0
    assert cli.main(["record", "verdict", "fail", "--project", p, "--attempt", "1", "--summary", "だめ", "--failure", "AC-01=違う"]) == 0
    assert cli.main(["record", "finish", "TEST_FAILED", "--project", p]) == 0
    s = state(tmp_path)
    assert s["driver"] == "pipe-in" and s["final"] == "TEST_FAILED"
    assert s["runs"][-2]["result"]["tests"] == [{"criterion": "AC-01", "test": "tests/test_a.py::test_a"}]
    assert s["runs"][-1]["verdict"]["failures"] == [{"criterion": "AC-01", "detail": "違う"}]


def test_ac03_cli_reports_mistakes_without_traceback(tmp_path, capsys):
    p = str(tmp_path)
    cli.main(["record", "start", "--project", p, "--text", "メモ"])
    with pytest.raises(SystemExit) as e:
        cli.main(["record", "review", "design", "revise", "--project", p])
    assert e.value.code not in (0, None)


# ---- AC-02：SDK を呼ばない --------------------------------------------------------


def test_ac02_record_never_calls_the_sdk(tmp_path, monkeypatch):
    import devpipe.engine.runner as runner

    def boom(*a, **k):
        raise AssertionError("SDK を呼んではいけない")

    monkeypatch.setattr(runner, "run_stage_sdk", boom)
    r = recorder(tmp_path)
    up_to_waiting(r)
    to_finish(r)


def test_ac02_record_module_does_not_import_the_sdk():
    src = (Path(__file__).parents[1] / "devpipe" / "dev" / "record.py").read_text(encoding="utf-8")
    assert "claude_agent_sdk" not in src
    assert "runner" not in src
