"""D0080：state.json の空の値の決まり（「測れた」「取れない」の2通り）と、版の鍵 schema。

3つの書き手（SDK の道の _save_state・開発用の pipe-in record・会話の道の pipe-in-gen chat）が書く鍵と値の種類を、
拡張のテストと共通の表 tests/fixtures/state_record.json で結ぶ（budget_record.json と同じ作り）。
SDK は呼ばない（runner を差し替える・no_sdk）。記録は tmp_path の下にだけ作る。
新しい部品 pipe_in.engine.state.new_state は、テストの中で遅く読む（まだ無いうちは、それを使うテストだけが落ちる）。

今の作りのままで通るもの（守り続ける検査）は、説明の末尾に「（今のまま通る。守る）」と書く。
"""

from __future__ import annotations

import asyncio
import ast
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from chat_support import Run, no_sdk, pipe_toml, stage_toml  # noqa: F401

from pipe_in.dev import specs as st
from pipe_in.dev.pipeline import DevPipeline
from pipe_in.dev.record import Recorder
from pipe_in.engine import live
from pipe_in.engine.checkpoint import Decision
from pipe_in.engine.config import load_config
from pipe_in.engine.pipeline import Exit
from pipe_in.engine.runner import StageRun
from pipe_in.pipe.chat_record import USAGE_UNAVAILABLE
from pipe_in.usage.estimate import actual_usd

pytestmark = pytest.mark.usefixtures("no_sdk")

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
TABLE = json.loads((FIXTURES / "state_record.json").read_text(encoding="utf-8"))
FIXED = datetime(2026, 11, 11, 10, 0, 0)


# ---- 書き手を動かす（どれも tmp_path の下） ------------------------------------------------------


class DocRunner:
    """段の代わりに文書を書く（SDK を呼ばない）。確認で止める（--pause）ので、要件定義・設計・テスト先行までを流す。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append(spec.name)
        docs = {"requirements": st.REQUIREMENTS, "design": st.DESIGN, "red": st.RED}
        (cfg.work_dir / docs[spec.name]).write_text(f"# {spec.name}\n", encoding="utf-8")
        run = StageRun(stage=spec.name, session_id=f"s-{len(self.calls)}", cost_usd=0.01, num_turns=3)
        if spec.name == "red":
            run.structured = {
                "status": "red", "summary": "赤です", "tests": [{"criterion": "AC-01", "test": "test_a"}], "commands": ["pytest -q"],
            }
        return run


def sdk_cfg(root: Path):
    return load_config(root, None, pause_for_review=True)


def state_path(root: Path) -> Path:
    return root / "docs" / "pipeline" / st.STATE


def read_state(root: Path) -> dict[str, Any]:
    return json.loads(state_path(root).read_text(encoding="utf-8"))


def sdk_review(root: Path, decision: Decision) -> Exit:
    return asyncio.run(DevPipeline(sdk_cfg(root), runner=DocRunner()).review(decision))


def build_sdk(root: Path) -> dict[str, Any]:
    """SDK の道：要件定義を流して確認で止め（--pause）、承認して設計で止まった記録。"""
    assert asyncio.run(DevPipeline(sdk_cfg(root), runner=DocRunner()).run("メモ", "requirements")) == Exit.AWAITING_REVIEW
    assert sdk_review(root, Decision("approve")) == Exit.AWAITING_REVIEW
    return read_state(root)


def recorder(root: Path) -> Recorder:
    return Recorder(load_config(root), now=lambda: FIXED)


def build_dev(root: Path) -> dict[str, Any]:
    """開発用の道：start → begin → done。"""
    r = recorder(root)
    r.start("足したい機能のメモ")
    r.begin("requirements")
    r.done("requirements", summary="要件定義を書いた")
    return read_state(root)


def build_chat(root: Path) -> dict[str, Any]:
    """会話の道：始めて、確かめを済ませ、段を1つ流して閉じた記録。"""
    r = Run(root)
    r.ready(pipe_toml(stage_toml("a")))
    r.run_and_finish("a")
    return r.state()


BUILDERS = {"sdk": build_sdk, "dev": build_dev, "chat": build_chat}


# ---- 共通の表を読む ------------------------------------------------------------------------------


def value_is(kind: str, value: Any) -> bool:
    """表の「値の種類」の言葉で、値を確かめる。"""
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "null":
        return value is None
    if kind == "summary":
        return isinstance(value, dict) and "available" not in value
    if kind == "unavailable":
        return isinstance(value, dict) and value.get("available") is False and isinstance(value.get("reason"), str) and value["reason"] != ""
    raise AssertionError(f"表の値の種類が分からない: {kind}")


def check_against_table(state: dict[str, Any], kind: str) -> None:
    """記録の鍵の並び（任意の鍵を除く）と値の種類が、表の kind のとおりであることを確かめる。違えば AssertionError。"""
    row = TABLE["kinds"][kind]
    keys = [k for k in state if k not in row["optional_keys"]]
    assert keys == row["keys"], f"{kind}: 鍵の並びが表と違う: {keys}"
    if row["driver"] is None:
        assert "driver" not in state, f"{kind}: driver の鍵がある"
    else:
        assert state["driver"] == row["driver"]
    assert state["schema"] == TABLE["schema"]
    assert value_is(row["total_cost_usd"], state["total_cost_usd"]), f"{kind}: total_cost_usd {state['total_cost_usd']!r}"
    assert value_is(row["usage_summary"], state["usage_summary"]), f"{kind}: usage_summary {state['usage_summary']!r}"
    runs = [x for x in state["runs"] if "seq" in x]
    assert runs, f"{kind}: 段の実行が無く、runs[] の値を確かめられない"
    for run in runs:
        assert value_is(row["run_cost_usd"], run["cost_usd"]), f"{kind}: runs[].cost_usd {run['cost_usd']!r}"
        if row["run_metrics"] == "present":
            assert isinstance(run.get("metrics"), dict), f"{kind}: runs[].metrics が無い"
        else:
            assert "metrics" not in run, f"{kind}: runs[].metrics の鍵がある"


# ---- AC-01：SDK の記録の schema ------------------------------------------------------------------


def test_d0080_ac01_sdk_state_has_schema_first(tmp_path):
    """D0080-AC-01: SDK で流した記録は schema が 1 で、schema が最初の鍵。"""
    state = build_sdk(tmp_path)
    assert list(state)[:1] == ["schema"], f"最初の鍵が schema でない: {list(state)[:3]}"
    assert state["schema"] == 1 and type(state["schema"]) is int


def test_d0080_ac01_schema_stays_after_review(tmp_path):
    """D0080-AC-01: schema のある SDK の記録を --review で続けても、schema は最初の鍵のまま残る。"""
    build_sdk(tmp_path)
    assert sdk_review(tmp_path, Decision("approve")) == Exit.AWAITING_REVIEW
    state = read_state(tmp_path)
    assert list(state)[:1] == ["schema"] and state["schema"] == 1


# ---- AC-02：driver の鍵が無い・--review で続けられる ------------------------------------------------


def test_d0080_ac02_sdk_state_has_no_driver_and_review_continues(tmp_path):
    """D0080-AC-02: SDK の記録に driver の鍵が無い（null も書かない）。確認で止めた記録を --review で続けられる（今のまま通る。守る）。"""
    state = build_sdk(tmp_path)
    assert "driver" not in state
    assert state["pending_review"]["stage"] == "design"
    assert sdk_review(tmp_path, Decision("approve")) == Exit.AWAITING_REVIEW  # 設計の承認 → テスト先行で止まる
    after = read_state(tmp_path)
    assert "driver" not in after and after["pending_review"]["stage"] == "red"


# ---- AC-03・04：開発用の record ------------------------------------------------------------------


def test_d0080_ac03_record_start_is_unavailable(tmp_path):
    """D0080-AC-03: pipe-in record start の直後、total_cost_usd は null、usage_summary.available は false（reason は空でない文字）。"""
    recorder(tmp_path).start("足したい機能のメモ")
    state = read_state(tmp_path)
    assert state["total_cost_usd"] is None
    summary = state["usage_summary"]
    assert isinstance(summary, dict), f"usage_summary が辞書でない: {summary!r}"
    assert summary["available"] is False
    assert isinstance(summary["reason"], str) and summary["reason"].strip() != ""


def test_d0080_ac04_record_done_run_has_null_cost_and_no_metrics(tmp_path):
    """D0080-AC-04: pipe-in record done が足す runs[] の要素は、cost_usd が null で、metrics の鍵が無い。
    段のログの ResultMessage の total_cost_usd は今のまま 0.0。"""
    state = build_dev(tmp_path)
    (run,) = [x for x in state["runs"] if "seq" in x]
    assert run["cost_usd"] is None
    assert "metrics" not in run
    log = tmp_path / "docs" / "pipeline" / "logs" / "01_requirements.jsonl"
    lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    result = next(x for x in lines if x["_type"] == "ResultMessage")
    assert result["total_cost_usd"] == 0.0


# ---- AC-05：会話の道は schema が足されるほかは今と同じ ----------------------------------------------


def test_d0080_ac05_chat_state_unchanged_but_schema(tmp_path):
    """D0080-AC-05: 会話の道の記録は、schema を除けば今と同じ値と鍵の並び（driver は pipe-chat、費用 null、使用量 {available: false, reason}、
    chat の節の名前もそのまま）（今のまま通る。守る）。"""
    state = build_chat(tmp_path)
    rest = {k: v for k, v in state.items() if k != "schema"}
    assert rest["name"] and "session_id" not in rest  # 名前は依頼メモの最初の行から作られる
    del rest["name"]
    assert list(rest) == [
        "started_at", "updated_at", "pipe", "driver", "stages", "final", "total_cost_usd", "usage_summary",
        "pending_review", "warnings", "flow", "open", "runs", "chat",  # flow は D0090 で足された（warnings の次・open の前）
    ]
    assert rest["driver"] == "pipe-chat"
    assert rest["total_cost_usd"] is None
    assert rest["usage_summary"] == dict(USAGE_UNAVAILABLE)
    assert rest["usage_summary"]["available"] is False and rest["usage_summary"]["reason"]
    assert list(rest["chat"]) == ["pipe_dir", "fingerprint", "probe", "steps", "retries", "notes", "next_stage", "revise"]
    (run,) = [x for x in rest["runs"] if "seq" in x]
    assert run["cost_usd"] is None and "metrics" not in run


# ---- AC-06：SDK の記録は測れた形（段を流す前の最初の保存でも） ---------------------------------------


def test_d0080_ac06_sdk_state_is_measured_before_any_stage(tmp_path):
    """D0080-AC-06: SDK の記録は、段を1つも流していない最初の保存でも、total_cost_usd が数、usage_summary が集計の辞書（今のまま通る。守る）。"""
    p = DevPipeline(sdk_cfg(tmp_path), runner=DocRunner())
    p.cfg.work_dir.mkdir(parents=True, exist_ok=True)
    p._save_state()
    state = read_state(tmp_path)
    assert state["runs"] == []
    assert value_is("number", state["total_cost_usd"])
    assert value_is("summary", state["usage_summary"])


def new_state_fn():
    from pipe_in.engine.state import new_state  # まだ無いうちは、使うテストだけが落ちる

    return new_state


BASE = {"started_at": "2026-11-11T10:00:00", "updated_at": "2026-11-11T10:00:00", "pipe": "p", "stages": [], "runs": []}


def test_d0080_ac06_new_state_rejects_empty_reason():
    """D0080-AC-06: 取れない記録の reason が空の文字列なら、new_state は ValueError（AC-03 の「空でない」を関数で守る）。"""
    new_state = new_state_fn()
    with pytest.raises(ValueError):
        new_state("pipe-dev", **BASE, unavailable_reason="")


@pytest.mark.parametrize(
    "cost,summary",
    [(None, {"by_model": {}}), (0.0, None), (None, None)],
    ids=["費用が無い", "集計が無い", "どちらも無い"],
)
def test_d0080_ac06_new_state_rejects_measured_without_both_values(cost, summary):
    """D0080-AC-06: 測れた記録（unavailable_reason なし）は、数と集計の辞書の両方が要る。どちらかが None なら ValueError。"""
    new_state = new_state_fn()
    with pytest.raises(ValueError):
        new_state(None, **BASE, total_cost_usd=cost, usage_summary=summary)


def test_d0080_ac06_new_state_rejects_both_forms_at_once():
    """D0080-AC-06: 「取れない」の理由と、測れた値（費用と集計）を同時に渡したら ValueError。"""
    new_state = new_state_fn()
    with pytest.raises(ValueError):
        new_state("pipe-dev", **BASE, unavailable_reason="理由", total_cost_usd=0.0, usage_summary={"by_model": {}})


def test_d0080_ac02_new_state_without_driver_writes_no_driver_key():
    """D0080-AC-02: new_state の driver が None なら、driver の鍵を書かない（null も書かない）。文字なら書く。"""
    new_state = new_state_fn()
    sdk = new_state(None, **BASE, total_cost_usd=0.0, usage_summary={"by_model": {}})
    assert "driver" not in sdk
    dev = new_state("pipe-dev", **BASE, unavailable_reason="理由")
    assert dev["driver"] == "pipe-dev"


def test_d0080_ac09_new_state_key_order_and_values():
    """D0080-AC-09: new_state の鍵の並びは、schema を先頭に、今の3つの書き手の並びを保つ。取れない記録は費用 null・使用量 {available: false, reason}。"""
    new_state = new_state_fn()
    chat = new_state("pipe-chat", **BASE, name="N", session_id="S", with_open=True, unavailable_reason="理由")
    assert list(chat) == [
        "schema", "started_at", "updated_at", "pipe", "name", "session_id", "driver", "stages", "final",
        "total_cost_usd", "usage_summary", "pending_review", "warnings", "open", "runs",
    ]
    assert chat["schema"] == 1 and chat["total_cost_usd"] is None
    assert chat["usage_summary"] == {"available": False, "reason": "理由"}
    assert chat["open"] is None and chat["final"] is None and chat["pending_review"] is None and chat["warnings"] == []
    sdk = new_state(None, **BASE, name="N", received_from={"pipe": "x"}, total_cost_usd=0.5, usage_summary={"by_model": {}})
    assert list(sdk) == [
        "schema", "started_at", "updated_at", "pipe", "name", "received_from", "stages", "final",
        "total_cost_usd", "usage_summary", "pending_review", "warnings", "runs",
    ]
    assert sdk["total_cost_usd"] == 0.5 and sdk["usage_summary"] == {"by_model": {}}


def non_stdlib_imports(source: str) -> list[str]:
    """ソースの import のうち、標準ライブラリ（と __future__）でないもの。"""
    bad = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = ["." * node.level + (node.module or "")]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if name.startswith(".") or top not in sys.stdlib_module_names:
                bad.append(name)
    return bad


def test_d0080_non_stdlib_import_check_finds_violation():
    """D0080-AC-09: 標準ライブラリだけを守る検査そのものが、違反（pipe_in の import・相対 import・外の部品）を見つける。"""
    assert non_stdlib_imports("from __future__ import annotations\nimport json\nfrom typing import Any\n") == []
    assert non_stdlib_imports("from pipe_in.usage import metrics\n") == ["pipe_in.usage"]
    assert non_stdlib_imports("from ..usage import metrics\n") == ["..usage"]
    assert non_stdlib_imports("import yaml\n") == ["yaml"]


def test_d0080_state_module_uses_only_stdlib():
    """D0080-AC-09: pipe_in/engine/state.py は標準ライブラリだけを読む（pipe_in.usage も読まない。集計は呼ぶ側が渡す）。"""
    source = (ROOT / "pipe_in" / "engine" / "state.py").read_text(encoding="utf-8")
    assert non_stdlib_imports(source) == []


# ---- AC-08：schema の無い古い記録は書き換えない --------------------------------------------------


def test_d0080_ac08_legacy_state_stays_without_schema_on_review(tmp_path):
    """D0080-AC-08: schema の無い SDK の記録を --review で続けても、schema は足されない（今のまま通る。守る）。"""
    build_sdk(tmp_path)
    data = read_state(tmp_path)
    data.pop("schema", None)  # 古い記録に戻す
    state_path(tmp_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    assert sdk_review(tmp_path, Decision("approve")) == Exit.AWAITING_REVIEW
    after = read_state(tmp_path)
    assert "schema" not in after
    assert [h["seq"] for h in after["runs"] if "seq" in h][:2] == [1, 2]  # 続きは読めている


def test_d0080_ac08_legacy_dev_state_stays_as_it_was_with_record_commands(tmp_path):
    """D0080-AC-08: schema の無い古い開発用の記録を record の各コマンドで続けても、schema は足されず、0.0・None・{} はそのまま残る（今のまま通る。守る）。"""
    work = tmp_path / "docs" / "pipeline"
    work.mkdir(parents=True)
    shutil.copy(FIXTURES / "pipe_dev" / "waiting" / "state.json", work / st.STATE)
    before = json.loads((work / st.STATE).read_text(encoding="utf-8"))
    r = recorder(tmp_path)
    r.review("red", "approved")
    r.begin("implement", attempt=1)
    r.done("implement", summary="実装した")
    r.begin("test", attempt=1)
    r.done("test", summary="検証した")
    r.verdict("pass", 1, "合格")
    r.finish("PASSED")
    after = read_state(tmp_path)
    assert "schema" not in after
    assert after["total_cost_usd"] == 0.0 and after["usage_summary"] is None
    assert after["runs"][: len(before["runs"])] == before["runs"], "もとの runs[] が書き換わった"


def test_d0080_ac08_legacy_state_in_archive_is_not_rewritten(tmp_path):
    """D0080-AC-08: 新しく始めて古い記録を archive/ に移しても、その中の state.json は書き換わらない。もとからある archive/ の記録も同じ（今のまま通る。守る）。"""
    work = tmp_path / "docs" / "pipeline"
    old_archived = work / "archive" / "2026-10-01_000000"
    old_archived.mkdir(parents=True)
    (old_archived / st.STATE).write_text((FIXTURES / "pipe_dev" / "finished" / "state.json").read_text(encoding="utf-8"), encoding="utf-8")
    before_archived = (old_archived / st.STATE).read_bytes()
    original = (FIXTURES / "pipe_dev" / "finished" / "state.json").read_bytes()
    (work / st.STATE).write_bytes(original)
    recorder(tmp_path).start("次のメモ")
    assert (old_archived / st.STATE).read_bytes() == before_archived
    moved = [p for p in (work / "archive").rglob(st.STATE) if p != old_archived / st.STATE]
    assert len(moved) == 1, [p.as_posix() for p in moved]
    assert moved[0].read_bytes() == original


# ---- AC-09：3つの書き手が共通の表のとおり --------------------------------------------------------


def test_d0080_ac09_table_has_the_three_writers_and_schema_one():
    """D0080-AC-09: 共通の表 state_record.json は、sdk・dev・chat の3つと schema 1 を持ち、拡張のテストと同じファイルを読む。"""
    assert TABLE["schema"] == 1
    assert sorted(TABLE["kinds"]) == ["chat", "dev", "sdk"]
    for row in TABLE["kinds"].values():
        assert row["keys"][0] == "schema"


@pytest.mark.parametrize("kind", ["sdk", "dev", "chat"])
def test_d0080_ac09_writers_match_table(tmp_path, kind):
    """D0080-AC-09: 3つの書き手が書く鍵の並び（任意の鍵を除く）と値の種類が、共通の表 tests/fixtures/state_record.json のとおり。"""
    check_against_table(BUILDERS[kind](tmp_path), kind)


def test_d0080_ac09_table_check_finds_violation(tmp_path):
    """D0080-AC-09: 表と比べる検査そのものが、schema の欠け・取れない値の違い・driver の違いを見つける。"""
    good = build_dev(tmp_path)
    legacy = TABLE["legacy_dev"]
    old = {k: v for k, v in good.items() if k != "schema"}
    with pytest.raises(AssertionError):
        check_against_table(old, "dev")
    zero = {**good, "total_cost_usd": legacy["total_cost_usd"], "usage_summary": legacy["usage_summary"]}
    with pytest.raises(AssertionError):
        check_against_table(zero, "dev")
    with pytest.raises(AssertionError):
        check_against_table({**good, "driver": "pipe-chat"}, "dev")


# ---- AC-10：取れない記録の前の実績は None ---------------------------------------------------------


@pytest.mark.parametrize("kind", ["dev", "chat"])
def test_d0080_ac10_actual_usd_is_none_for_unavailable(tmp_path, kind):
    """D0080-AC-10: 取れない記録（開発用の新しい記録・会話の道）で、estimate.actual_usd は None を返す（今のまま通る。守る）。"""
    assert actual_usd(BUILDERS[kind](tmp_path)) is None


# ---- AC-12：schema が変な値でも落ちずに読む -------------------------------------------------------

ODD_SCHEMA = ["1", None, True, [], 2, 1.5, {"a": 1}, "x"]
ODD_IDS = ["文字の1", "null", "真偽", "配列", "2", "小数", "辞書", "文字"]


@pytest.mark.parametrize("value", ODD_SCHEMA, ids=ODD_IDS)
def test_d0080_ac12_odd_schema_values_still_read(tmp_path, value):
    """D0080-AC-12: schema が数でない（文字・null・真偽・配列・辞書）・2 以上の記録も、--review・actual_usd・live の写しの組み立てが落ちずに今までどおり読む（今のまま通る。守る）。"""
    build_sdk(tmp_path)
    data = read_state(tmp_path)
    data["schema"] = value
    state_path(tmp_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    assert actual_usd(data) is None or isinstance(actual_usd(data), float)
    snap = live.build_snapshot(data, None, now=datetime(2026, 11, 11, 10, 0, 0, tzinfo=timezone.utc))
    assert snap["empty"] is False and [s["name"] for s in snap["stages"]][:2] == ["requirements", "design"]
    assert sdk_review(tmp_path, Decision("approve")) == Exit.AWAITING_REVIEW


# ---- AC-13（手で）の自動で確かめられる部分：進み具合の写しに零の費用が出ない ----------------------------


def test_d0080_ac13_live_snapshot_of_new_dev_record_has_no_zero_cost(tmp_path):
    """D0080-AC-13: 開発用の新しい記録を進み具合の写し（pipe-in live）にすると、段の費用は 0 でなく無し（null）になり、費用の欄が出ない。"""
    state = build_dev(tmp_path)
    snap = live.build_snapshot(state, None, now=datetime(2026, 11, 11, 10, 0, 0, tzinfo=timezone.utc))
    done = [s for s in snap["stages"] if s["name"] == "requirements"]
    assert len(done) == 1 and done[0]["status"] == "done"
    assert done[0]["cost_usd"] is None, f"零の費用が出ている: {done[0]['cost_usd']!r}"
