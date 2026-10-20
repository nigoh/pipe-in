"""pipe-in record：開発用のスキルが、SDK を呼ばずに開発フローと同じ形の記録（docs/pipeline/）を書く。

VSCode の拡張がそのまま図にできるように、本体が書く state.json と同じ形にする。
見本は tests/fixtures/pipe_dev/（今の形。driver = "pipe-dev"）にあり、拡張のテスト（vscode/src/domain/pipeInRecord.test.ts）も同じ見本を読む。
tests/fixtures/pipe_in/ は前の版の記録（driver = "pipe-in"）の見本として残す。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from pipe_in import cli
from pipe_in.dev.pipeline import DevPipeline
from pipe_in.dev.record import RecordError, Recorder
from pipe_in.engine.checkpoint import Decision
from pipe_in.engine.config import load_config

FIXTURES = Path(__file__).parent / "fixtures" / "pipe_dev"
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
    """D0006-AC-22: 始めた段の記録とログの1行目が見本と同じ（driver は pipe-dev、prompt は /pipe-dev の<段>）。"""
    r = recorder(tmp_path)
    r.start("足したい機能のメモ")
    r.begin("requirements")
    # D0019: state.json に name（要件メモの最初の行から作る）が足された（見本は古い形のまま残す）。name は D0019-AC-44 が確かめる
    got_state = state(tmp_path)
    got_state.pop("name", None)
    assert got_state == fixture_state("running")
    log = tmp_path / "docs" / "pipeline" / "logs" / "01_requirements.jsonl"
    want = (FIXTURES / "running" / "logs" / "01_requirements.jsonl").read_text(encoding="utf-8")
    # D0017: Prompt 行の at は、UTC からのずれつきの書き方に替わった（見本は古い書き方のまま残す）。at の書き方は D0017-AC-02 が確かめる
    got_lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    want_lines = [json.loads(x) for x in want.splitlines()]
    for line in (*got_lines, *want_lines):
        line.pop("at", None)
    assert got_lines == want_lines
    assert (tmp_path / "docs" / "pipeline" / "00_input.md").read_text(encoding="utf-8").strip() == "足したい機能のメモ"


def test_ac01_waiting_matches_fixture(tmp_path):
    """D0006-AC-22: 確認待ちの記録が見本と同じ（driver のほかは今と同じ形）。"""
    up_to_waiting(recorder(tmp_path))
    # D0017: pending_review に since（待ち始めの時刻）が足された（見本は古い形のまま残す）。since は D0017-AC-01 が確かめる
    got = state(tmp_path)
    got["pending_review"].pop("since", None)
    got.pop("name", None)  # D0019: 見本は name の無い古い形のまま残す
    assert got == fixture_state("waiting")


def test_ac01_finished_matches_fixture(tmp_path):
    """D0006-AC-22: 終わった記録が見本と同じ。"""
    r = recorder(tmp_path)
    up_to_waiting(r)
    to_finish(r)
    got = state(tmp_path)
    got.pop("name", None)  # D0019: 見本は name の無い古い形のまま残す
    assert got == fixture_state("finished")
    summary = (tmp_path / "docs" / "pipeline" / "99_summary.md").read_text(encoding="utf-8")
    assert "PASSED" in summary or "終わりました" in summary


def test_summary_title_is_pipe_dev(tmp_path):
    """D0006-AC-22: finish が書く 99_summary.md の1行目は「# /pipe-dev のまとめ」。"""
    r = recorder(tmp_path)
    up_to_waiting(r)
    to_finish(r)
    summary = (tmp_path / "docs" / "pipeline" / "99_summary.md").read_text(encoding="utf-8")
    assert summary.splitlines()[0] == "# /pipe-dev のまとめ"


def test_old_fixture_differs_only_in_driver():
    """D0006-AC-24: 前の版の見本（pipe_in）と今の見本（pipe_dev）は driver の値だけが違う（ほかの形は変えない）。"""
    old_dir = Path(__file__).parent / "fixtures" / "pipe_in"
    for name in ("running", "waiting", "finished"):
        old = json.loads((old_dir / name / "state.json").read_text(encoding="utf-8"))
        new = fixture_state(name)
        assert (old.pop("driver"), new.pop("driver")) == ("pipe-in", "pipe-dev")
        assert old == new


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


def set_driver(project: Path, driver: str | None) -> None:
    path = project / "docs" / "pipeline" / "state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if driver is None:
        data.pop("driver", None)
    else:
        data["driver"] = driver
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize("driver", ["pipe-dev", "pipe-in", "other"])
def test_review_refuses_records_with_a_driver(tmp_path, driver):
    """D0006-AC-23: driver の入った記録（今の pipe-dev・前の版の pipe-in・ほか）の続きを、pipe-in --review が SDK で流さない。文に /pipe-dev を含む。"""
    up_to_waiting(recorder(tmp_path))
    set_driver(tmp_path, driver)
    called = []

    async def runner(*a, **k):
        called.append(a)
        raise AssertionError("SDK を呼んではいけない")

    cfg = load_config(tmp_path, pause_for_review=True)
    with pytest.raises(SystemExit) as e:
        asyncio.run(DevPipeline(cfg, runner=runner).review(Decision("approve", "")))
    assert "/pipe-dev" in str(e.value.code)
    assert "pipe-in --review" in str(e.value.code)
    assert not called


def test_review_continues_a_record_without_driver(tmp_path):
    """D0006-AC-23: driver の無い確認待ちの記録は、今までどおり続きを流す。"""
    from pipe_in.engine.runner import StageRun

    up_to_waiting(recorder(tmp_path))
    set_driver(tmp_path, None)
    called: list[str] = []

    async def runner(spec, prompt, cfg, *, resume, log_name):
        called.append(spec.name)
        return StageRun(stage=spec.name, session_id="s-1", is_error=True)

    cfg = load_config(tmp_path, pause_for_review=True)
    asyncio.run(DevPipeline(cfg, runner=runner).review(Decision("approve", "")))
    assert called and called[0] == "implement"


# ---- コマンド（pipe-in record …） ----------------------------------------------


def test_ac03_cli_writes_the_same_record(tmp_path):
    """D0006-AC-22: コマンドで書いた記録の driver は pipe-dev。"""
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
    assert s["driver"] == "pipe-dev" and s["final"] == "TEST_FAILED"
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
    import pipe_in.engine.runner as runner

    def boom(*a, **k):
        raise AssertionError("SDK を呼んではいけない")

    monkeypatch.setattr(runner, "run_stage_sdk", boom)
    r = recorder(tmp_path)
    up_to_waiting(r)
    to_finish(r)


# ---- D0017：確認待ちの時刻（since）と Prompt 行の at --------------------------------

OFFSET_TEXT = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)"


def test_d0017_ac01_wait_writes_since_with_offset(tmp_path):
    """D0017-AC-01: record wait が pending_review.since にオフセットつきの ISO 8601 の時刻を書く（stage・doc は従来どおり）。"""
    import re

    r = recorder(tmp_path)
    r.start("メモ")
    r.begin("requirements")
    r.done("requirements")
    r.wait("requirements")
    pending = state(tmp_path)["pending_review"]
    assert pending["stage"] == "requirements"
    assert pending["doc"] == "docs/pipeline/01_requirements.md"
    assert re.fullmatch(OFFSET_TEXT, pending["since"]), pending.get("since")
    assert datetime.fromisoformat(pending["since"]) == FIXED.astimezone()  # 呼んだ時刻と同じ瞬間


def test_d0017_ac02_begin_prompt_at_has_offset(tmp_path):
    """D0017-AC-02: record begin が書く Prompt 行の at がオフセットつき。began_at は従来どおり（オフセットなし）で、done の秒数は変わらない。"""
    import re

    clock = [FIXED]
    r = recorder(tmp_path, now=lambda: clock[0])
    r.start("メモ")
    r.begin("requirements")
    log = tmp_path / "docs/pipeline/logs/01_requirements.jsonl"
    first = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert re.fullmatch(OFFSET_TEXT, first["at"]), first.get("at")
    assert datetime.fromisoformat(first["at"]) == FIXED.astimezone()
    assert state(tmp_path)["open"]["began_at"] == "2026-10-17T10:00:00"
    clock[0] = FIXED + timedelta(seconds=90)
    r.done("requirements")
    assert state(tmp_path)["runs"][-1]["duration_sec"] == 90.0


def test_d0017_ac05_record_commands_work_without_since(tmp_path):
    """D0017-AC-05: since の無い古い pending_review でも、record の review・begin・done・finish が今までどおり動く（今の作りで通る：守り続ける検査）。"""
    r = recorder(tmp_path)
    r.start("メモ")
    r.begin("requirements")
    r.done("requirements")
    r.wait("requirements")
    path = tmp_path / "docs" / "pipeline" / "state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["pending_review"].pop("since", None)  # 古い形（stage・doc・session_id だけ）
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    r.wait("requirements")  # 古い印があっても、もう一度付けられる
    data = json.loads(path.read_text(encoding="utf-8"))
    data["pending_review"].pop("since", None)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    r.review("requirements", "approved")
    r.begin("design")
    r.done("design")
    r.finish("PASSED")
    assert state(tmp_path)["final"] == "PASSED" and state(tmp_path)["pending_review"] is None


# ---- D0019：名前・セッション ID・受け持ち（足すだけ） ------------------------------------------------


def pipeline_dir(project: Path) -> Path:
    return project / "docs" / "pipeline"


def test_d0019_ac44_start_name_from_flag(tmp_path):
    """D0019-AC-44: start に名前を渡すと、state.json の name がその名前になる（要件メモの最初の行より優先）。"""
    recorder(tmp_path).start("# 別の題\n本文", name="X")
    assert state(tmp_path)["name"] == "X"


def test_d0019_ac44_start_name_from_memo(tmp_path):
    """D0019-AC-44: 名前を渡さないと、00_input.md の最初の行（見出しの印を取る）から作った名前になる。"""
    recorder(tmp_path).start("\n## 仕様の QA を回す\n2行目は使わない")
    assert state(tmp_path)["name"] == "仕様の QA を回す"


def test_d0019_ac44_start_no_name_when_memo_has_none(tmp_path):
    """D0019-AC-44: 名前を渡さず、メモが空・見出しの印だけなら、name を書かない。"""
    recorder(tmp_path).start("")
    assert "name" not in state(tmp_path)
    recorder(tmp_path).start("###")
    assert "name" not in state(tmp_path)


def test_d0019_ac44_start_name_is_normalized(tmp_path):
    """D0019-AC-44: 付けた名前も同じ整え（前後の空白・連続空白・60 文字）をし、空の名前は「付けなかった」と同じ。"""
    recorder(tmp_path).start("メモ", name="  A   B  ")
    assert state(tmp_path)["name"] == "A B"
    recorder(tmp_path).start("メモ", name="あ" * 61)
    assert state(tmp_path)["name"] == "あ" * 59 + "…"
    recorder(tmp_path).start("題のメモ", name="   ")
    assert state(tmp_path)["name"] == "題のメモ"


def test_d0019_ac44_cli_start_name(tmp_path):
    """D0019-AC-44: pipe-in record start --name "X" で state.json の name が X になり、--name なしでは最初の行から作る。"""
    p = str(tmp_path)
    assert cli.main(["record", "start", "--project", p, "--text", "# 見出しの題\n本文", "--name", "X"]) == 0
    assert state(tmp_path)["name"] == "X"
    assert cli.main(["record", "start", "--project", p, "--text", "# 見出しの題\n本文"]) == 0
    assert state(tmp_path)["name"] == "見出しの題"


def test_d0019_ac47_session_id_is_written(tmp_path):
    """D0019-AC-47: start に session_id を渡すと state.json の session_id になる。"""
    recorder(tmp_path).start("メモ", session_id="7f3a9c01-2b4d-4e5f-8a6b-0c1d2e3f4a5b")
    assert state(tmp_path)["session_id"] == "7f3a9c01-2b4d-4e5f-8a6b-0c1d2e3f4a5b"


def test_d0019_ac47_no_session_id_key_without_it(tmp_path):
    """D0019-AC-47: session_id を付けなければ項目を書かない。"""
    recorder(tmp_path).start("メモ")
    assert "session_id" not in state(tmp_path)


def test_d0019_ac47_cli_start_session_id(tmp_path):
    """D0019-AC-47: pipe-in record start --session-id ID で session_id が残る。"""
    p = str(tmp_path)
    assert cli.main(["record", "start", "--project", p, "--text", "メモ", "--session-id", "abc-123"]) == 0
    assert state(tmp_path)["session_id"] == "abc-123"


BAD_IDS = [" ", "   ", "a b", "a\nb", "a\tb", "a" * 101, " abc", "abc "]


@pytest.mark.parametrize("bad", BAD_IDS, ids=["space", "spaces", "inner-space", "newline", "tab", "101", "lead-space", "trail-space"])
def test_d0019_ac47_bad_session_id_is_refused_and_nothing_is_made(tmp_path, bad):
    """D0019-AC-47: 空白だけ・空白や改行を含む・100 文字超の session_id は RecordError で断り、記録（state.json・archive/）を作らない。"""
    with pytest.raises(RecordError):
        recorder(tmp_path).start("メモ", session_id=bad)
    assert not (pipeline_dir(tmp_path) / "state.json").exists()
    assert not (pipeline_dir(tmp_path) / "archive").exists()
    assert not (pipeline_dir(tmp_path) / "00_input.md").exists()


@pytest.mark.parametrize("bad", [" ", "a b", "a\nb", "x" * 101])
def test_d0019_ac47_bad_session_id_leaves_a_finished_record_where_it_is(tmp_path, bad):
    """D0019-AC-47: 終わった記録があるとき、誤った session_id で start しても、記録を archive/ へ移さず、今の記録もそのまま。"""
    r = recorder(tmp_path)
    up_to_waiting(r)
    to_finish(r)
    before = (pipeline_dir(tmp_path) / "state.json").read_text(encoding="utf-8")
    with pytest.raises(RecordError):
        recorder(tmp_path).start("次のメモ", session_id=bad)
    assert (pipeline_dir(tmp_path) / "state.json").read_text(encoding="utf-8") == before
    assert not (pipeline_dir(tmp_path) / "archive").exists()
    assert (pipeline_dir(tmp_path) / "00_input.md").read_text(encoding="utf-8").strip() == "足したい機能のメモ"


def test_d0019_ac47_cli_refuses_a_bad_session_id(tmp_path):
    """D0019-AC-47: コマンドでも、誤った --session-id はエラー終了で、記録を作らない。"""
    with pytest.raises(SystemExit) as e:
        cli.main(["record", "start", "--project", str(tmp_path), "--text", "メモ", "--session-id", "a b"])
    assert e.value.code not in (0, None)
    assert isinstance(e.value.code, str) and "pipe-in record" in e.value.code  # argparse の未知の引数（終了コード 2）ではなく、記録のエラー
    assert not (pipeline_dir(tmp_path) / "state.json").exists()


def test_d0019_ac48_agent_in_prompt_and_run(tmp_path):
    """D0019-AC-48: begin に agent を渡すと、Prompt 行と open と、続く done の runs[] の要素に agent が入る。"""
    r = recorder(tmp_path)
    r.start("メモ")
    r.begin("requirements", agent="pipe-in-analyst")
    log = pipeline_dir(tmp_path) / "logs" / "01_requirements.jsonl"
    first = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert first["_type"] == "Prompt" and first["agent"] == "pipe-in-analyst"
    assert state(tmp_path)["open"]["agent"] == "pipe-in-analyst"
    r.done("requirements", summary="書いた")
    run = state(tmp_path)["runs"][-1]
    assert run["agent"] == "pipe-in-analyst" and run["stage"] == "requirements"


def test_d0019_ac48_no_agent_key_without_it(tmp_path):
    """D0019-AC-48: agent を付けなければ、Prompt 行にも open にも runs[] にも書かない。"""
    r = recorder(tmp_path)
    r.start("メモ")
    r.begin("requirements")
    log = pipeline_dir(tmp_path) / "logs" / "01_requirements.jsonl"
    assert "agent" not in json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert "agent" not in state(tmp_path)["open"]
    r.done("requirements")
    assert "agent" not in state(tmp_path)["runs"][-1]


@pytest.mark.parametrize("bad", [" ", "a b", "a\nb", "x" * 101])
def test_d0019_ac48_bad_agent_is_refused_and_nothing_is_started(tmp_path, bad):
    """D0019-AC-48: 誤った agent（空白だけ・空白や改行を含む・100 文字超）は RecordError で断り、段を始めない（ログも open も作らない）。"""
    r = recorder(tmp_path)
    r.start("メモ")
    with pytest.raises(RecordError):
        r.begin("requirements", agent=bad)
    assert state(tmp_path)["open"] is None
    assert not (pipeline_dir(tmp_path) / "logs").exists()


def test_d0019_ac48_cli_begin_agent(tmp_path):
    """D0019-AC-48: pipe-in record begin <段> --agent A で、Prompt 行と runs[] に agent が残る。"""
    p = str(tmp_path)
    assert cli.main(["record", "start", "--project", p, "--text", "メモ"]) == 0
    assert cli.main(["record", "begin", "design", "--project", p, "--agent", "pipe-in-analyst"]) == 0
    assert cli.main(["record", "done", "design", "--project", p, "--summary", "書いた"]) == 0
    assert state(tmp_path)["runs"][-1]["agent"] == "pipe-in-analyst"


def test_d0019_ac48_agent_is_only_text_never_a_path(tmp_path):
    """D0019-AC-48・AC-50: agent に ../ や / を含む文字を入れても、ログのファイル名には使われず、文字として書かれるだけ（logs/ の外にファイルを作らない）。"""
    r = recorder(tmp_path)
    r.start("メモ")
    r.begin("requirements", agent="../../evil")
    assert sorted(p.name for p in (pipeline_dir(tmp_path) / "logs").iterdir()) == ["01_requirements.jsonl"]
    assert not (tmp_path / "evil").exists() and not (tmp_path / "docs" / "evil").exists()
    assert state(tmp_path)["open"]["agent"] == "../../evil"


def test_d0019_ac49_old_state_without_new_keys(tmp_path):
    """D0019-AC-49: name・session_id・agent の無い古い state.json で、record の各コマンドが今までどおり動く。今の作りで通る（守り続ける検査）。"""
    r = recorder(tmp_path)
    up_to_waiting(r)
    path = pipeline_dir(tmp_path) / "state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("name", "session_id"):
        data.pop(key, None)
    for run in data["runs"]:
        run.pop("agent", None)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    to_finish(recorder(tmp_path))
    s = state(tmp_path)
    assert s["final"] == "PASSED" and "name" not in s and "session_id" not in s
    assert all("agent" not in run for run in s["runs"])


def test_d0019_ac49_archive_carries_name_and_session_id(tmp_path):
    """D0019-AC-49: start が終わった記録を archive/ へ移すと、name と session_id も state.json ごと一緒に移る。"""
    r = recorder(tmp_path)
    r.start("最初のメモ", name="最初の実行", session_id="sess-1")
    r.begin("requirements", agent="pipe-in-analyst")
    r.done("requirements")
    r.finish("STOPPED_BY_HUMAN")
    recorder(tmp_path).start("次のメモ", name="次の実行")
    archived = [p for p in (pipeline_dir(tmp_path) / "archive").iterdir() if p.is_dir()]
    assert len(archived) == 1
    old = json.loads((archived[0] / "state.json").read_text(encoding="utf-8"))
    assert old["name"] == "最初の実行" and old["session_id"] == "sess-1"
    assert old["runs"][0]["agent"] == "pipe-in-analyst"
    now = state(tmp_path)
    assert now["name"] == "次の実行" and "session_id" not in now


def test_ac02_record_module_does_not_import_the_sdk():
    src = (Path(__file__).parents[1] / "pipe_in" / "dev" / "record.py").read_text(encoding="utf-8")
    assert "claude_agent_sdk" not in src
    assert "runner" not in src
