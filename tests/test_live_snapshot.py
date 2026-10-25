"""D0027：進み具合の写し（pipe_in/engine/live.py）。state.json などから、Claude のアーティファクトに出す JSON を作る。

写しを組み立てる build_snapshot は純粋な関数（時計・ファイルに触れない）。ファイルを読むのは read_state・read_open_at。
壊れた記録・欠けた項目・型違い・NaN/Infinity・巨大値・未来の時刻・ずれあり/なし・悪意のある文字・上限の境目を細かく確かめる。
記録は tmp_path の中に作る（リポジトリの実物には書かない）。手元のパスやユーザー名は、実行時に組み立てる。
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import live_support as ls
from live_support import JST, NOW, STAGE_KEYS, KEYS, UTC
from pipe_in.engine import live
from pipe_in.engine.pipeline import Exit

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
MAX_BYTES = 32768
MAX_STATE_BYTES = 4 * 1024 * 1024
SEP = chr(92)  # バックスラッシュ（Windows のパスの区切り）

# 手元のパスの形（テストの外に実在する名前を書かないよう、実行時に組み立てる）
POSIX_HOME_PATH = "/" + "ho" + "me/alice/secret-project/src"
WIN_PATH_BACK = "C:" + SEP + "Us" + "ers" + SEP + "alice" + SEP + "secret-project"
WIN_PATH_SLASH = "C:/" + "Us" + "ers/alice/secret-project"


# ---- 補助 ------------------------------------------------------------------------------------


def snap(state, open_at=None, *, now=NOW, local_tz=JST, hide=()):
    s = live.build_snapshot(state, open_at, now=now, local_tz=local_tz, hide=hide)
    assert isinstance(s, dict) and s, "build_snapshot が空の辞書を返した（写しをまだ作っていない）"
    return s


def st(s, name):
    found = [x for x in s["stages"] if x["name"] == name]
    assert len(found) == 1, f"段 {name} が写しに {len(found)} 個ある: {[x['name'] for x in s['stages']]}"
    return found[0]


def blob(s) -> str:
    """写しの全部の文字（辞書の中身と dumps の出力）。漏れの検査はこれ全体に対して行う。"""
    out = live.dumps(s)
    assert out, "dumps が空（まだ作っていない）"
    return json.dumps(s, ensure_ascii=False) + "\n" + out


def strict_loads(text: str):
    def bad(token):
        raise ValueError(f"JSON に {token} が出た")

    return json.loads(text, parse_constant=bad)


def only_clean_chars(text: str) -> bool:
    return all(unicodedata.category(c) not in ("Cc", "Cf", "Zl", "Zp", "Cs") or c == "\u200d" for c in text)


def with_runs(runs, **over):
    return ls.base_state(runs=runs, **over)


EMPTY_FORM = {"schema": 1, "generated_at": "2026-10-17T12:00:00+00:00", "empty": True, "name": None, "final": None, "stages": [], "review": None}

_OPENED: list[str] = []
_WATCH = {"on": False}


def _audit(event, args):
    if _WATCH["on"] and event == "open":
        _OPENED.append(os.fsdecode(args[0]) if isinstance(args[0], (str, bytes, os.PathLike)) else "")


sys.addaudithook(_audit)


class watch_opens:
    """with の間に open されたファイルの名前を集める（sys.addaudithook。ファイルを開く道は全部ここに出る）。"""

    def __enter__(self):
        _OPENED.clear()
        _WATCH["on"] = True
        return _OPENED

    def __exit__(self, *exc):
        _WATCH["on"] = False


# ---- AC-01 形 --------------------------------------------------------------------------------


def test_d0027_ac01_snapshot_has_exactly_the_top_level_keys(tmp_path):
    """D0027-AC-01: 開発フローの途中の記録から作った写しは、決まったキーだけを、決まった順で持つ。"""
    work = ls.dev_record_midway(tmp_path)
    state = live.read_state(work)
    assert isinstance(state, dict)
    s = snap(state, live.read_open_at(work, state))
    assert list(s) == KEYS
    assert s["schema"] == 1 and type(s["schema"]) is int
    assert s["generated_at"] == "2026-10-17T12:00:00+00:00"
    assert s["empty"] is False
    assert s["name"] == "途中のセッション"
    assert s["final"] is None
    assert isinstance(s["stages"], list)


def test_d0027_ac01_stage_has_exactly_the_stage_keys(tmp_path):
    """D0027-AC-01: 段の要素は、決まったキーだけを、決まった順で持つ（本物の記録から）。"""
    work = ls.dev_record_midway(tmp_path)
    state = live.read_state(work)
    s = snap(state, live.read_open_at(work, state))
    assert [x["name"] for x in s["stages"]] == list(ls.STAGES)
    for x in s["stages"]:
        assert list(x) == STAGE_KEYS, x["name"]


def test_d0027_ac01_real_record_midway_states_and_start_time(tmp_path):
    """D0027-AC-01: 本物の記録（要件定義が済み、設計が動いている）の段の状態と、動いている段の始まりの時刻。"""
    work = ls.dev_record_midway(tmp_path)
    state = live.read_state(work)
    s = snap(state, live.read_open_at(work, state))
    assert [x["status"] for x in s["stages"]] == ["done", "running", "waiting", "waiting", "waiting"]
    expected = datetime(2026, 10, 17, 10, 0, 0).astimezone(UTC).isoformat(timespec="seconds")
    assert st(s, "design")["started_at"] == expected
    assert all(x["started_at"] is None for x in s["stages"] if x["name"] != "design")


def test_d0027_ac01_stage_values_have_the_designed_types():
    """D0027-AC-01: 段の値の型（attempt は int か null、数は number か null、時刻は文字か null）。"""
    state = ls.base_state(
        open=ls.opened("red", seq=3, attempt=2),
        pending_review=ls.pending("design", "2026-10-17T10:00:00+09:00"),
        runs=[ls.run("requirements", seq=1, attempt=1, cost=0.25, turns=4, duration=3.5), ls.verdict("pass", 1)],
    )
    s = snap(state, "2026-10-17T10:30:00+09:00")
    for x in s["stages"]:
        assert type(x["name"]) is str and type(x["label"]) is str and type(x["status"]) is str
        assert x["attempt"] is None or type(x["attempt"]) is int
        assert x["started_at"] is None or type(x["started_at"]) is str
        assert x["pending_since"] is None or type(x["pending_since"]) is str
        assert x["verdict"] is None or type(x["verdict"]) is str
        assert x["cost_usd"] is None or type(x["cost_usd"]) in (int, float)
        assert x["turns"] is None or type(x["turns"]) is int
        assert x["duration_sec"] is None or type(x["duration_sec"]) in (int, float)
    assert st(s, "red")["started_at"] == "2026-10-17T01:30:00+00:00"
    assert st(s, "design")["pending_since"] == "2026-10-17T01:00:00+00:00"


# ---- AC-02 段の並びと回 ---------------------------------------------------------------------------


def test_d0027_ac02_stages_follow_state_order_one_per_stage():
    """D0027-AC-02: 段の並びは state.json の stages の順。同じ段が何度動いても1つにまとまる。"""
    state = ls.base_state(
        stages=[ls.stage_entry("test"), ls.stage_entry("requirements"), ls.stage_entry("implement")],
        runs=[
            ls.run("implement", seq=1, attempt=1),
            ls.run("requirements", seq=2),
            ls.run("implement", seq=3, attempt=2),
            ls.run("implement", seq=4, attempt=3),
        ],
    )
    s = snap(state)
    assert [x["name"] for x in s["stages"]] == ["test", "requirements", "implement"]


def test_d0027_ac02_attempt_is_the_last_run():
    """D0027-AC-02: attempt は、同じ段の最後の回。"""
    state = with_runs([ls.run("implement", seq=1, attempt=1), ls.run("implement", seq=2, attempt=2), ls.run("implement", seq=3, attempt=3)])
    assert st(snap(state), "implement")["attempt"] == 3


def test_d0027_ac02_attempt_of_a_running_stage_is_the_open_attempt():
    """D0027-AC-02: 動いている段の attempt は open の回（前の回の記録が残っていても）。"""
    state = ls.base_state(open=ls.opened("implement", seq=2, attempt=2), runs=[ls.run("implement", seq=1, attempt=1)])
    x = st(snap(state), "implement")
    assert x["status"] == "running" and x["attempt"] == 2


def test_d0027_ac02_attempt_is_null_when_the_stage_never_ran():
    """D0027-AC-02: まだ動いていない段の attempt は null。"""
    assert st(snap(ls.base_state()), "design")["attempt"] is None


# ---- AC-03 段の状態 -------------------------------------------------------------------------------

STATUS_CASES = [
    ("waiting_no_runs", "design", {}, "waiting"),
    ("running_open", "design", {"open": ls.opened("design", seq=2)}, "running"),
    ("review_pending", "design", {"pending_review": ls.pending("design")}, "review"),
    ("done_run", "design", {"runs": [ls.run("design", seq=2)]}, "done"),
    ("done_approved", "design", {"runs": [ls.run("design", seq=2), ls.review("design", "approved")]}, "done"),
    ("done_quit", "design", {"runs": [ls.run("design", seq=2), ls.review("design", "quit")]}, "done"),
    ("done_red_result", "red", {"runs": [ls.run("red", seq=3), ls.red_result("red")]}, "done"),
    ("done_verdict_fail_stays_done", "test", {"runs": [ls.run("test", seq=5, attempt=1), ls.verdict("fail", 1)]}, "done"),
    ("failed_run", "design", {"runs": [ls.run("design", seq=2, is_error=True)]}, "failed"),
    ("revised", "design", {"runs": [ls.run("design", seq=2), ls.review("design", "revise", "直して")]}, "revised"),
    ("revise_then_run_is_done", "design", {"runs": [ls.run("design", seq=2), ls.review("design", "revise", "x"), ls.run("design", seq=3)]}, "done"),
    ("failed_then_ok_is_done", "design", {"runs": [ls.run("design", seq=2, is_error=True), ls.run("design", seq=3)]}, "done"),
    ("ok_then_failed", "design", {"runs": [ls.run("design", seq=2), ls.run("design", seq=3, is_error=True)]}, "failed"),
    ("failed_then_approved_is_done", "design", {"runs": [ls.run("design", seq=2, is_error=True), ls.review("design", "approved")]}, "done"),
    ("running_beats_pending", "design", {"open": ls.opened("design", seq=2), "pending_review": ls.pending("design")}, "running"),
    ("running_beats_failed_run", "design", {"open": ls.opened("design", seq=3), "runs": [ls.run("design", seq=2, is_error=True)]}, "running"),
    ("running_beats_revised", "design", {"open": ls.opened("design", seq=3), "runs": [ls.run("design", seq=2), ls.review("design", "revise", "x")]}, "running"),
    ("review_beats_failed_run", "design", {"pending_review": ls.pending("design"), "runs": [ls.run("design", seq=2, is_error=True)]}, "review"),
    ("other_stage_open_does_not_touch", "design", {"open": ls.opened("red", seq=2)}, "waiting"),
    ("other_stage_pending_does_not_touch", "design", {"pending_review": ls.pending("red")}, "waiting"),
    ("string_true_is_not_failed", "design", {"runs": [ls.run("design", seq=2, is_error="true")]}, "done"),
    ("null_is_error_is_not_failed", "design", {"runs": [ls.run("design", seq=2, is_error=None)]}, "done"),
]


@pytest.mark.parametrize("stage,over,expected", [c[1:] for c in STATUS_CASES], ids=[c[0] for c in STATUS_CASES])
def test_d0027_ac03_status_table(stage, over, expected):
    """D0027-AC-03: 段の状態の決め方（open → pending_review → runs の最後の要素 → waiting の順）。"""
    assert st(snap(ls.base_state(**over)), stage)["status"] == expected


def test_d0027_ac03_every_status_value_is_one_of_the_six():
    """D0027-AC-03: 状態の値は6つのどれかだけ。"""
    allowed = {"waiting", "running", "review", "done", "failed", "revised"}
    for _id, stage, over, _exp in STATUS_CASES:
        for x in snap(ls.base_state(**over))["stages"]:
            assert x["status"] in allowed, (_id, x)


# ---- AC-04 検証の判定 -----------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["pass", "fail", "blocked"])
def test_d0027_ac04_verdict_known_values_on_test_stage(status):
    """D0027-AC-04: 検証（test）の段の verdict に、pass / fail / blocked が入る。"""
    state = with_runs([ls.run("test", seq=5, attempt=1), ls.verdict(status, 1)])
    assert st(snap(state), "test")["verdict"] == status


def test_d0027_ac04_the_last_verdict_wins():
    """D0027-AC-04: 判定が複数あるときは最後のもの。"""
    state = with_runs([ls.verdict("fail", 1), ls.run("test", seq=6, attempt=2), ls.verdict("pass", 2)])
    assert st(snap(state), "test")["verdict"] == "pass"


@pytest.mark.parametrize(
    "bad",
    ["PASS", "passed", "", " pass", "pass ", "pass\n", "ok", None, 1, 0, True, False, 1.5, [], ["pass"], {}, {"status": "pass"}],
    ids=repr,
)
def test_d0027_ac04_verdict_unknown_or_wrong_type_is_null(bad):
    """D0027-AC-04: 未知の文字・型違いの判定は null（段の状態は done のまま）。"""
    state = with_runs([ls.run("test", seq=5, attempt=1), ls.verdict(bad, 1)])
    x = st(snap(state), "test")
    assert x["verdict"] is None
    assert x["status"] == "done"


@pytest.mark.parametrize("bad", ["pass", 5, None, [], True], ids=repr)
def test_d0027_ac04_verdict_that_is_not_an_object_is_null(bad):
    """D0027-AC-04: runs の verdict が辞書でないとき（文字・数・null・配列・真偽）は null で、例外を出さない。"""
    state = with_runs([ls.run("test", seq=5, attempt=1), {"stage": "test", "attempt": 1, "verdict": bad}])
    assert st(snap(state), "test")["verdict"] is None


def test_d0027_ac04_verdict_without_status_key_is_null():
    """D0027-AC-04: status の無い判定は null。"""
    state = with_runs([{"stage": "test", "attempt": 1, "verdict": {"summary": "x"}}])
    assert st(snap(state), "test")["verdict"] is None


def test_d0027_ac04_verdict_only_on_test_stage():
    """D0027-AC-04: test 以外の段に判定の行があっても、その段の verdict は null。パイプの段 check も同じ。"""
    state = ls.base_state(
        stages=[ls.stage_entry("implement"), ls.stage_entry("check"), ls.stage_entry("test")],
        runs=[ls.verdict("pass", 1, stage="implement"), ls.verdict("fail", 1, stage="check"), ls.verdict("blocked", 1, stage="test")],
    )
    s = snap(state)
    assert [x["verdict"] for x in s["stages"]] == [None, None, "blocked"]


def test_d0027_ac04_verdict_is_null_without_any_verdict():
    """D0027-AC-04: 判定の行が無ければ null。"""
    assert st(snap(with_runs([ls.run("test", seq=5, attempt=1)])), "test")["verdict"] is None


# ---- AC-05 最後の結果 -----------------------------------------------------------------------------

FINAL_NAMES = [e.name for e in Exit if e != Exit.AWAITING_REVIEW]


@pytest.mark.parametrize("final", ["PASSED", "TEST_FAILED", "STOPPED_BY_HUMAN", "STAGE_ERROR", "BLOCKED"])
def test_d0027_ac05_final_accepts_exit_names(final):
    """D0027-AC-05: Exit の名前（AWAITING_REVIEW 以外）は final に入る。"""
    assert snap(ls.base_state(final=final))["final"] == final


@pytest.mark.parametrize(
    "bad",
    ["AWAITING_REVIEW", "passed", "Passed", " PASSED", "PASSED ", "PASSED\n", "FOO", "", 0, 5, 1.0, True, False, [], ["PASSED"], {}, {"x": 1}],
    ids=repr,
)
def test_d0027_ac05_final_unknown_or_wrong_type_is_null(bad):
    """D0027-AC-05: 未知の文字・AWAITING_REVIEW・型違いは null。ほかの項目は読む。"""
    s = snap(ls.base_state(final=bad))
    assert s["final"] is None
    assert s["name"] == "テスト用のセッション"


def test_d0027_ac05_final_null_when_unfinished():
    """D0027-AC-05: 終わっていない記録（final が null）では null。"""
    assert snap(ls.base_state(final=None))["final"] is None


def test_d0027_ac05_final_null_when_key_is_missing():
    """D0027-AC-05: final のキーが無い古い記録でも null。"""
    state = ls.base_state()
    del state["final"]
    assert snap(state)["final"] is None


def test_d0027_ac05_finals_match_exit_enum():
    """D0027-AC-05: 受ける名前は Exit の列挙（AWAITING_REVIEW を除く）と同じ。列挙が増えたら、ここで気づく。"""
    assert FINAL_NAMES == ["PASSED", "TEST_FAILED", "STOPPED_BY_HUMAN", "STAGE_ERROR", "BLOCKED"]
    for name in FINAL_NAMES:
        assert snap(ls.base_state(final=name))["final"] == name


# ---- AC-06 版・形を固定 ---------------------------------------------------------------------------


def test_d0027_ac06_schema_constant_is_one_place():
    """D0027-AC-06: 写しの形の版 SCHEMA は定数で1か所に持ち、写しの schema はそこから出る。"""
    import inspect
    import re

    source = inspect.getsource(live)
    assert len(re.findall(r"^SCHEMA\s*=", source, re.M)) == 1, "live.py に SCHEMA = が1つだけ要る"
    assert live.SCHEMA == 1
    assert snap(ls.base_state())["schema"] == live.SCHEMA
    assert not re.search(r"""["']schema["']\s*:\s*\d""", source), "schema の数をキーの横に直接書かない（SCHEMA を使う）"


def test_d0027_ac06_limit_constants_have_the_designed_values():
    """D0027-AC-06: 上限（写し全体 32 KiB・state.json 4 MiB）は定数で、設計の値。"""
    assert live.MAX_BYTES == MAX_BYTES
    assert live.MAX_STATE_BYTES == MAX_STATE_BYTES


def test_d0027_ac06_shape_is_frozen():
    """D0027-AC-06: 写しの形（キーの一覧・順・型）を固定する。キーを変えるとここが落ちる（schema を上げる合図）。"""
    state = ls.base_state(
        open=ls.opened("red", seq=2),
        pending_review=ls.pending("design"),
        runs=[ls.run("requirements", seq=1, attempt=1, cost=0.5, turns=3, duration=2.5), ls.verdict("pass", 1)],
    )
    s = snap(state, "2026-10-17T10:00:00+09:00")
    assert [(k, type(v).__name__) for k, v in s.items()] == [
        ("schema", "int"), ("generated_at", "str"), ("empty", "bool"), ("name", "str"), ("final", "NoneType"), ("stages", "list"),
        ("review", "dict"),
    ]
    shape = {x["name"]: [(k, type(v).__name__) for k, v in x.items()] for x in s["stages"]}
    assert shape["requirements"] == [
        ("name", "str"), ("label", "str"), ("status", "str"), ("attempt", "int"), ("started_at", "NoneType"),
        ("pending_since", "NoneType"), ("verdict", "NoneType"), ("cost_usd", "float"), ("turns", "int"), ("duration_sec", "float"),
    ]
    assert shape["red"][4] == ("started_at", "str")
    assert shape["design"][5] == ("pending_since", "str")
    assert [k for k, _ in shape["design"]] == STAGE_KEYS


def test_d0027_ac06_empty_form_has_the_same_keys_in_the_same_order():
    """D0027-AC-06: 記録なしの形も、キーの数と順は同じ（ページが場合分けしない）。"""
    assert list(snap(None)) == KEYS == list(snap(ls.base_state()))


# ---- AC-07 パイプの記録 ---------------------------------------------------------------------------


def test_d0027_ac07_pipe_record_takes_stage_names_and_labels_from_record():
    """D0027-AC-07: 段の並びが開発フローと違うパイプの記録でも、name・label を記録から取る。"""
    state = {
        "started_at": "2026-10-17T10:00:00+09:00", "updated_at": "2026-10-17T10:00:00+09:00", "pipe": "diagram", "name": "図を作る",
        "stages": [
            {"name": "collect", "label": "集める", "output": "a.md", "review": False},
            {"name": "draw_figure", "label": "図にする", "output": "b.md", "review": True},
            {"name": "check-2", "label": "確かめる", "output": "c.md", "review": False},
        ],
        "final": None, "pending_review": None, "warnings": [], "open": ls.opened("draw_figure", seq=2), "runs": [ls.run("collect", seq=1)],
    }
    s = snap(state, "2026-10-17T10:05:00+09:00")
    assert list(s) == KEYS
    assert [(x["name"], x["label"], x["status"]) for x in s["stages"]] == [
        ("collect", "集める", "done"), ("draw_figure", "図にする", "running"), ("check-2", "確かめる", "waiting"),
    ]
    assert all(list(x) == STAGE_KEYS for x in s["stages"])
    assert s["name"] == "図を作る"


def test_d0027_ac07_pipe_record_is_read_from_a_pipe_folder(tmp_path):
    """D0027-AC-07: <work_dir>/<パイプ名>/ のフォルダを読み先にしても同じ形。"""
    work = tmp_path / "docs" / "pipeline" / "diagram"
    state = ls.base_state(stages=[ls.stage_entry("collect", "集める")], pipe="diagram")
    ls.write_state(work, state)
    loaded = live.read_state(work)
    assert loaded == state
    assert [x["label"] for x in snap(loaded)["stages"]] == ["集める"]


def test_d0027_ac07_missing_label_falls_back_to_the_name():
    """D0027-AC-07: label が無い段は、表示名に name を使う。"""
    state = ls.base_state(stages=[{"name": "collect"}, {"name": "draw", "label": None}, {"name": "x", "label": ""}])
    assert [x["label"] for x in snap(state)["stages"]] == ["collect", "draw", "x"]


# ---- AC-08 同じ入力は同じバイト列 -----------------------------------------------------------------


def test_d0027_ac08_same_input_same_bytes():
    """D0027-AC-08: 同じ記録・同じ今で2回作ると、バイト列まで同じ。"""
    state = ls.base_state(open=ls.opened("design", seq=2), runs=[ls.run("requirements", seq=1, cost=0.1, turns=1, duration=1.5)])
    a = live.dumps(snap(copy.deepcopy(state), "2026-10-17T10:00:00+09:00")).encode("utf-8")
    b = live.dumps(snap(copy.deepcopy(state), "2026-10-17T10:00:00+09:00")).encode("utf-8")
    assert a == b and a


def test_d0027_ac08_input_key_order_does_not_change_the_bytes():
    """D0027-AC-08: 入力の辞書のキーの順が違っても、出力のキーの順は決まっている。"""
    state = ls.base_state(runs=[ls.run("requirements", seq=1, cost=0.1)], open=ls.opened("design", seq=2))
    reordered = {k: state[k] for k in reversed(list(state))}
    reordered["stages"] = [{k: e[k] for k in reversed(list(e))} for e in state["stages"]]
    assert live.dumps(snap(state)) == live.dumps(snap(reordered))


def test_d0027_ac08_state_is_not_modified():
    """D0027-AC-08: 作るときに、渡した記録を書き換えない。"""
    state = ls.base_state(
        name="  名前  ", open=ls.opened("design", seq=2), pending_review=ls.pending("red"),
        runs=[ls.run("requirements", seq=1, cost=0.1), ls.verdict("pass", 1)],
    )
    before = copy.deepcopy(state)
    snap(state, "2026-10-17T10:00:00")
    assert state == before


def test_d0027_ac08_different_now_changes_only_generated_at():
    """D0027-AC-08: 今だけが違うと、generated_at だけが変わる（時計を読まず、今は引数）。"""
    state = ls.base_state(open=ls.opened("design", seq=2))
    a = snap(state, "2026-10-17T10:00:00+09:00", now=NOW)
    b = snap(state, "2026-10-17T10:00:00+09:00", now=NOW + timedelta(hours=5))
    assert a["generated_at"] != b["generated_at"]
    a["generated_at"] = b["generated_at"] = None
    assert a == b


# ---- AC-09 費用・ターン・時間 ---------------------------------------------------------------------


def test_d0027_ac09_usage_summed_per_stage():
    """D0027-AC-09: 費用・ターン・時間は、同じ段の回で合計する（段ごと）。"""
    state = with_runs([
        ls.run("design", seq=1, attempt=None, cost=0.1, turns=3, duration=1.0),
        ls.review("design", "revise", "x"),
        ls.run("design", seq=2, attempt=None, cost=0.2, turns=4, duration=2.04),
        ls.run("requirements", seq=3, cost=1.5, turns=10, duration=20.0),
    ])
    s = snap(state)
    d = st(s, "design")
    assert (d["cost_usd"], d["turns"], d["duration_sec"]) == (0.3, 7, 3.0)
    r = st(s, "requirements")
    assert (r["cost_usd"], r["turns"], r["duration_sec"]) == (1.5, 10, 20.0)


def test_d0027_ac09_only_runs_with_numbers_count_not_reviews_or_verdicts():
    """D0027-AC-09: 確認・判定・テスト先行の結果の行は、合計に影響しない。"""
    state = with_runs([
        ls.run("red", seq=1, cost=0.5, turns=2, duration=1.0), ls.red_result("red"), ls.review("red", "approved"),
    ])
    x = st(snap(state), "red")
    assert (x["cost_usd"], x["turns"], x["duration_sec"]) == (0.5, 2, 1.0)


def test_d0027_ac09_usage_null_without_runs():
    """D0027-AC-09: 回が無い段（待ち・動き始め）は、費用・ターン・時間が null。"""
    s = snap(ls.base_state(open=ls.opened("design", seq=1)))
    for x in s["stages"]:
        assert (x["cost_usd"], x["turns"], x["duration_sec"]) == (None, None, None), x["name"]


@pytest.mark.parametrize(
    "cost,turns,duration,expected",
    [
        (0.123456, 5, 12.34, (0.1235, 5, 12.3)),
        (0.00004, 0, 0.04, (0.0, 0, 0.0)),
        (0.00005, 1, 0.06, (0.0001, 1, 0.1)),
        (0, 0, 0, (0, 0, 0)),
        (12, 7, 3, (12, 7, 3)),
    ],
)
def test_d0027_ac09_numbers_are_rounded(cost, turns, duration, expected):
    """D0027-AC-09: 費用は小数4桁、時間は小数1桁に丸める（0 と整数もそのまま入る）。"""
    x = st(snap(with_runs([ls.run("design", seq=1, cost=cost, turns=turns, duration=duration)])), "design")
    assert (x["cost_usd"], x["turns"], x["duration_sec"]) == expected


# ---- AC-10〜15 入れないもの（漏れ止め） ----------------------------------------------------------------


def test_d0027_ac10_memo_text_is_not_in_snapshot(tmp_path):
    """D0027-AC-10: 要件メモ（00_input.md）の本文が、写しに出ない。"""
    work = ls.dev_record_midway(tmp_path)
    assert "MEMO-BODY-MARK" in (work / "00_input.md").read_text(encoding="utf-8")
    state = live.read_state(work)
    s = snap(state, live.read_open_at(work, state))
    assert "MEMO-BODY-MARK" not in blob(s)
    assert st(s, "design")["status"] == "running"


def test_d0027_ac10_memo_text_is_not_read_from_the_state_either(tmp_path):
    """D0027-AC-10: state.json に（昔の書き方で）メモの本文が混じっていても出ない。"""
    work = tmp_path / "w"
    ls.write_state(work, ls.base_state(input="MEMO-BODY-MARK", memo="MEMO-BODY-MARK", text="MEMO-BODY-MARK"))
    (work / "00_input.md").write_text("MEMO-BODY-MARK\n", encoding="utf-8")
    assert "MEMO-BODY-MARK" not in blob(snap(live.read_state(work)))


def test_d0027_ac11_session_ids_are_not_in_snapshot(tmp_path):
    """D0027-AC-11: session_id（最上位・runs[]・pending_review の中）が写しに出ない。"""
    work = ls.dev_record_midway(tmp_path)
    state = live.read_state(work)
    assert state["session_id"] == "SESSION-ID-MARK"
    state["runs"][0]["session_id"] = "RUN-SESSION-MARK"
    state["pending_review"] = ls.pending("design") | {"session_id": "PENDING-SESSION-MARK"}
    s = snap(state, live.read_open_at(work, state))
    text = blob(s)
    for mark in ("SESSION-ID-MARK", "RUN-SESSION-MARK", "PENDING-SESSION-MARK"):
        assert mark not in text
    assert "session" not in text.lower().replace("セッション", "")


FREE_TEXT_MARKS = ["RESULT-MARK", "ERRORS-MARK", "FEEDBACK-MARK", "SUMMARY-MARK", "FAILURE-MARK", "DOC-MARK", "WARNING-MARK", "NOTE-MARK", "AGENT-MARK", "DENIAL-MARK", "METRICS-MARK", "USAGE-MARK", "CMD-MARK", "OUTPUT-MARK"]


@pytest.mark.parametrize("mark", FREE_TEXT_MARKS)
def test_d0027_ac12_free_text_fields_are_not_in_snapshot(mark):
    """D0027-AC-12: runs の result・errors・feedback・verdict の summary/failures、pending_review.doc、warnings などの自由な文が出ない。"""
    state = ls.base_state(
        warnings=["WARNING-MARK"],
        usage_summary={"models": ["USAGE-MARK"]},
        open=ls.opened("red", seq=3) | {"note": "NOTE-MARK", "agent": "AGENT-MARK"},
        pending_review=ls.pending("design") | {"doc": "DOC-MARK"},
        stages=[ls.stage_entry(n) | {"output": "OUTPUT-MARK"} for n in ls.STAGES],
        runs=[
            ls.run("requirements", seq=1, result="RESULT-MARK", errors=["ERRORS-MARK"], note="NOTE-MARK", agent="AGENT-MARK",
                   denials=["DENIAL-MARK"], metrics={"x": "METRICS-MARK"}),
            ls.review("requirements", "revise", "FEEDBACK-MARK"),
            ls.verdict("fail", 1, summary="SUMMARY-MARK", failures=[{"criterion": "AC-01", "detail": "FAILURE-MARK"}], commands=["CMD-MARK"]),
            ls.red_result("red") | {"result": {"status": "red", "summary": "SUMMARY-MARK", "tests": [{"criterion": "AC-01", "test": "FAILURE-MARK"}], "commands": ["CMD-MARK"]}},
        ],
    )
    assert mark not in blob(snap(state))


def test_d0027_ac12_marks_cover_every_free_text_field():
    """D0027-AC-12: 上の目印が、設計の挙げた自由な文の入れ物（result・errors・feedback・summary・failures・doc・warnings）を全部含む。"""
    assert {"RESULT-MARK", "ERRORS-MARK", "FEEDBACK-MARK", "SUMMARY-MARK", "FAILURE-MARK", "DOC-MARK", "WARNING-MARK"} <= set(FREE_TEXT_MARKS)


@pytest.mark.parametrize(
    "name",
    [POSIX_HOME_PATH, WIN_PATH_BACK, WIN_PATH_SLASH, "作業は " + POSIX_HOME_PATH + " で", "see " + WIN_PATH_BACK + SEP + "x here", "x " + WIN_PATH_SLASH + "/y z"],
    ids=["posix", "win_back", "win_slash", "posix_in_text", "win_back_in_text", "win_slash_in_text"],
)
def test_d0027_ac13_absolute_paths_in_names_do_not_remain(name):
    """D0027-AC-13: 名前・表示名・段の名前に手元の絶対パスが混じっていても、写しに出ない。"""
    state = ls.base_state(name=name, stages=[ls.stage_entry("a", name), ls.stage_entry(name, "ok")])
    text = blob(snap(state))
    assert "alice" not in text
    assert "secret-project" not in text
    assert "…" in snap(state)["name"]


def test_d0027_ac13_work_dir_path_is_not_in_snapshot(tmp_path):
    """D0027-AC-13: 読み先のフォルダのパス（hide に渡したもの）が、名前に混じっていても写しに出ない。"""
    work = tmp_path / "proj" / "docs" / "pipeline"
    state = ls.base_state(name=f"メモ {work} と {work}/logs", stages=[ls.stage_entry("a", f"{work}/x")])
    s = snap(state, hide=(str(work),))
    assert str(work) not in blob(s)
    assert "メモ" in s["name"] and "…" in s["name"]


@pytest.mark.parametrize("given", ["docs/pipeline/run-7", "docs" + SEP + "pipeline" + SEP + "run-7"], ids=["slash", "back"])
@pytest.mark.parametrize("seen", ["docs/pipeline/run-7", "docs" + SEP + "pipeline" + SEP + "run-7"], ids=["seen_slash", "seen_back"])
def test_d0027_ac13_hide_matches_both_separator_forms(given, seen):
    """D0027-AC-13: hide の文字は、/ 形でも \\ 形でも消える（与えられた形に関わらず）。"""
    state = ls.base_state(name=f"work in {seen} now")
    name = snap(state, hide=(given,))["name"]
    assert "run-7" not in name
    assert name == "work in … now"


def test_d0027_ac13_empty_hide_string_is_ignored():
    """D0027-AC-13: hide に空の文字があっても、名前が壊れない（空の文字で置き換えて、間に … を挟まない）。"""
    assert snap(ls.base_state(name="abc"), hide=("",))["name"] == "abc"


def test_d0027_ac13_relative_looking_text_is_kept():
    """D0027-AC-13: 絶対パスの形でない文（feat/add/csv など）は消さない。"""
    for text in ("feat/add/csv", "src/app", "a/b", "100% / 200%", "v1.0/rc"):
        assert snap(ls.base_state(name=text))["name"] == text


def test_d0027_ac13_paths_in_free_text_fields_are_not_in_snapshot(tmp_path):
    """D0027-AC-13: 自由な文（result・doc・warnings）の中のパスも、写しに出ない（そもそも入れない）。"""
    state = ls.base_state(
        warnings=[POSIX_HOME_PATH], pending_review=ls.pending("design") | {"doc": WIN_PATH_BACK},
        runs=[ls.run("design", seq=1, result=WIN_PATH_SLASH, errors=[POSIX_HOME_PATH])],
    )
    text = blob(snap(state))
    assert "alice" not in text and "secret-project" not in text


def test_d0027_ac14_log_contents_are_not_in_snapshot(tmp_path):
    """D0027-AC-14: ログの Prompt 行の prompt・ほかの行の中身が、写しに出ない（読むのは at だけ）。"""
    work = tmp_path / "w"
    state = ls.base_state(open=ls.opened("design", seq=2))
    ls.write_state(work, state)
    ls.write_log(work, "02_design.jsonl", [
        ls.prompt_line("2026-10-17T10:00:00+09:00", prompt="PROMPT-MARK", agent="AGENT-LOG-MARK"),
        {"_type": "AssistantMessage", "content": [{"text": "ASSISTANT-MARK"}]},
        {"_type": "ResultMessage", "result": "RESULT-LOG-MARK"},
    ])
    at = live.read_open_at(work, live.read_state(work))
    assert at == "2026-10-17T10:00:00+09:00"
    text = blob(snap(live.read_state(work), at))
    for mark in ("PROMPT-MARK", "AGENT-LOG-MARK", "ASSISTANT-MARK", "RESULT-LOG-MARK"):
        assert mark not in text
    assert st(snap(live.read_state(work), at), "design")["started_at"] == "2026-10-17T01:00:00+00:00"


def test_d0027_ac15_unknown_keys_are_not_in_snapshot():
    """D0027-AC-15: 知らないキー（secret）は、最上位・段・runs・open・pending_review・判定のどこにあっても写しに出ない。"""
    state = ls.base_state(
        secret="SECRET-MARK", token="SECRET-MARK",
        stages=[ls.stage_entry(n) | {"secret": "SECRET-MARK", "extra": {"secret": "SECRET-MARK"}} for n in ls.STAGES],
        open=ls.opened("design", seq=2) | {"secret": "SECRET-MARK"},
        pending_review=ls.pending("red") | {"secret": "SECRET-MARK"},
        runs=[ls.run("requirements", seq=1, secret="SECRET-MARK"), ls.verdict("pass", 1, secret="SECRET-MARK") | {"secret": "SECRET-MARK"}],
    )
    s = snap(state)
    assert "SECRET-MARK" not in blob(s) and "secret" not in blob(s)
    assert list(s) == KEYS and all(list(x) == STAGE_KEYS for x in s["stages"])


# ---- AC-16〜21 時刻 -------------------------------------------------------------------------------

SAME_INSTANT = [
    "2026-10-17T10:00:00+09:00", "2026-10-17T01:00:00Z", "2026-10-17T01:00:00+00:00", "2026-10-17T10:00:00",
    "2026-10-17 10:00:00+09:00", "2026-10-17T10:00:00.123456+09:00", "2026-10-17T01:00:00.9Z", "2026-10-16T20:00:00-05:00",
]


@pytest.mark.parametrize("at", SAME_INSTANT, ids=lambda t: t)
def test_d0027_ac16_prompt_at_forms_give_the_same_instant(at):
    """D0027-AC-16: at が +09:00・Z・-05:00・小数つき・空白区切り・ずれなし（local_tz=+09:00）でも、同じ瞬間なら同じ書き方になる。"""
    state = ls.base_state(open=ls.opened("design", seq=2))
    assert st(snap(state, at), "design")["started_at"] == "2026-10-17T01:00:00+00:00"


def test_d0027_ac16_output_is_utc_with_offset_and_seconds_only():
    """D0027-AC-16: 出力は常に …+00:00（秒まで。小数・Z・ほかのずれにならない）。"""
    state = ls.base_state(open=ls.opened("design", seq=2), pending_review=None)
    for at in ("2026-10-17T10:00:00.999999+09:00", "2026-10-17T10:00:00Z", "2026-10-17T10:00:00-12:00", "2026-10-17T10:00:00+14:00"):
        value = st(snap(state, at), "design")["started_at"]
        assert value.endswith("+00:00") and "." not in value and "Z" not in value and len(value) == 25, (at, value)


def test_d0027_ac16_half_hour_offset():
    """D0027-AC-16: 30分・45分のずれも直す。"""
    state = ls.base_state(open=ls.opened("design", seq=2))
    assert st(snap(state, "2026-10-17T10:30:00+09:30"), "design")["started_at"] == "2026-10-17T01:00:00+00:00"
    assert st(snap(state, "2026-10-17T06:45:00+05:45"), "design")["started_at"] == "2026-10-17T01:00:00+00:00"


def test_d0027_ac16_date_rolls_over_when_converted():
    """D0027-AC-16: UTC に直して日付をまたぐ場合も正しい。"""
    state = ls.base_state(open=ls.opened("design", seq=2))
    assert st(snap(state, "2026-01-01T03:00:00+09:00"), "design")["started_at"] == "2025-12-31T18:00:00+00:00"
    assert st(snap(state, "2026-12-31T23:30:00-05:00"), "design")["started_at"] == "2027-01-01T04:30:00+00:00"


def test_d0027_ac16_pending_since_forms():
    """D0027-AC-16: pending_review.since も同じ書き方になる。"""
    for since in ("2026-10-17T10:00:00+09:00", "2026-10-17T01:00:00Z", "2026-10-17T10:00:00"):
        state = ls.base_state(pending_review=ls.pending("design", since))
        assert st(snap(state), "design")["pending_since"] == "2026-10-17T01:00:00+00:00"


BAD_TIMES = [
    "abc", "", " ", 123, 1.5, 0, True, False, None, [], ["2026-10-17T10:00:00+09:00"], {}, {"at": "x"},
    "2026-13-45T25:61:61+00:00", "2026-10-17", "2026-10-17T10:00", "10:00:00", "2026-02-30T10:00:00+00:00",
    "2026-10-17T10:00:00+99:00", "2026-10-17T10:00:00+0900x", "0000-00-00T00:00:00", "２０２６-10-17T10:00:00",
    "0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00", "x" * 41, "2026-10-17T10:00:00" + "9" * 30, "\x00",
    "2026-10-17T10:00:00+09:00\x00", "NaN", "1e999",
]


@pytest.mark.parametrize("bad", BAD_TIMES, ids=lambda v: repr(v)[:40])
def test_d0027_ac17_bad_at_gives_null_started_at(bad):
    """D0027-AC-17: 壊れた時刻（abc・空・数・null・型違い・存在しない日・範囲外・長すぎ）は started_at が null で、例外を出さない。"""
    state = ls.base_state(open=ls.opened("design", seq=2))
    x = st(snap(state, bad), "design")
    assert x["started_at"] is None
    assert x["status"] == "running"


def test_d0027_ac17_running_stays_running_without_at():
    """D0027-AC-17: at が無い（ログが無い・Prompt 行が無い）古い記録でも、動いている段は running のまま。"""
    state = ls.base_state(open=ls.opened("design", seq=2))
    x = st(snap(state, None), "design")
    assert (x["status"], x["started_at"]) == ("running", None)


def test_d0027_ac17_time_length_boundary_is_forty_characters():
    """D0027-AC-17: 受ける時刻の文字は40文字まで。40文字ちょうどは読み、41文字は null。"""
    state = ls.base_state(open=ls.opened("design", seq=2))
    ok40 = "2026-10-17T01:00:00." + "1" * 19 + "Z"
    assert len(ok40) == 40
    assert st(snap(state, ok40), "design")["started_at"] == "2026-10-17T01:00:00+00:00"
    assert st(snap(state, "2026-10-17T01:00:00." + "1" * 20 + "Z"), "design")["started_at"] is None


@pytest.mark.parametrize("bad", BAD_TIMES, ids=lambda v: repr(v)[:40])
def test_d0027_ac18_bad_or_missing_since_gives_null_pending_since(bad):
    """D0027-AC-18: 壊れた since は pending_since が null で、状態は review のまま。"""
    state = ls.base_state(pending_review=ls.pending("design", bad))
    x = st(snap(state), "design")
    assert x["pending_since"] is None
    assert x["status"] == "review"


def test_d0027_ac18_review_stays_review_without_since():
    """D0027-AC-18: since のキーが無い古い記録でも review のまま、pending_since は null。"""
    state = ls.base_state(pending_review=ls.pending("design", ...))
    assert "since" not in state["pending_review"]
    x = st(snap(state), "design")
    assert (x["status"], x["pending_since"]) == ("review", None)


def test_d0027_ac18_pending_since_only_on_the_review_stage():
    """D0027-AC-18: pending_since は確認待ちの段だけ。ほかの段は null（started_at も動いている段だけ）。"""
    state = ls.base_state(pending_review=ls.pending("design", "2026-10-17T10:00:00+09:00"), open=ls.opened("red", seq=3))
    s = snap(state, "2026-10-17T10:10:00+09:00")
    assert [(x["name"], x["pending_since"] is not None, x["started_at"] is not None) for x in s["stages"]] == [
        ("requirements", False, False), ("design", True, False), ("red", False, True), ("implement", False, False), ("test", False, False),
    ]


def test_d0027_ac18_started_at_is_null_when_nothing_is_open():
    """D0027-AC-18: 動いている段が無ければ、open_at を渡しても started_at はどこにも出ない。"""
    s = snap(ls.base_state(), "2026-10-17T10:00:00+09:00")
    assert all(x["started_at"] is None for x in s["stages"])


def test_d0027_ac19_future_times_are_kept_as_is():
    """D0027-AC-19: 今より後の時刻も、そのまま写しに入れる（直さない）。"""
    state = ls.base_state(open=ls.opened("design", seq=2), pending_review=ls.pending("red", "2099-01-01T00:00:00+00:00"))
    s = snap(state, "2030-05-05T10:00:00+09:00")
    assert st(s, "design")["started_at"] == "2030-05-05T01:00:00+00:00"
    assert st(s, "red")["pending_since"] == "2099-01-01T00:00:00+00:00"


def test_d0027_ac19_times_before_now_and_far_past_are_kept():
    """D0027-AC-19: ずっと昔の時刻もそのまま。"""
    state = ls.base_state(open=ls.opened("design", seq=2))
    assert st(snap(state, "1970-01-01T09:00:00+09:00"), "design")["started_at"] == "1970-01-01T00:00:00+00:00"
    assert st(snap(state, "0001-01-01T00:00:00+00:00"), "design")["started_at"] == "0001-01-01T00:00:00+00:00"


@pytest.mark.parametrize(
    "tz,expected",
    [
        (JST, "2026-10-17T01:00:00+00:00"),
        (UTC, "2026-10-17T10:00:00+00:00"),
        (timezone(timedelta(hours=-5)), "2026-10-17T15:00:00+00:00"),
        (timezone(timedelta(hours=14)), "2026-10-16T20:00:00+00:00"),
        (timezone(timedelta(hours=5, minutes=45)), "2026-10-17T04:15:00+00:00"),
    ],
    ids=["jst", "utc", "minus5", "plus14", "nepal"],
)
def test_d0027_ac20_naive_time_is_read_in_the_given_timezone(tz, expected):
    """D0027-AC-20: ずれなしの時刻は local_tz の時刻と見なして UTC に直す（時刻帯ごとに結果が変わる）。"""
    state = ls.base_state(open=ls.opened("design", seq=2), pending_review=None)
    assert st(snap(state, "2026-10-17T10:00:00", local_tz=tz), "design")["started_at"] == expected
    state = ls.base_state(pending_review=ls.pending("design", "2026-10-17T10:00:00"))
    assert st(snap(state, local_tz=tz), "design")["pending_since"] == expected


def test_d0027_ac20_naive_time_without_local_tz_uses_the_machine_zone():
    """D0027-AC-20: local_tz を渡さない（None）と、その機械の時刻帯で読む。"""
    state = ls.base_state(open=ls.opened("design", seq=2))
    expected = datetime(2026, 10, 17, 10, 0, 0).astimezone().astimezone(UTC).isoformat(timespec="seconds")
    assert st(live.build_snapshot(state, "2026-10-17T10:00:00", now=NOW), "design")["started_at"] == expected


def test_d0027_ac20_offset_time_ignores_local_tz():
    """D0027-AC-20: ずれつきの時刻は local_tz に左右されない。"""
    state = ls.base_state(open=ls.opened("design", seq=2))
    values = {st(snap(state, "2026-10-17T10:00:00+09:00", local_tz=tz), "design")["started_at"] for tz in (JST, UTC, timezone(timedelta(hours=-8)))}
    assert values == {"2026-10-17T01:00:00+00:00"}


def test_d0027_ac20_mixed_offset_and_naive_do_not_raise():
    """D0027-AC-20: ずれつきとずれなしが混ざった記録でも、例外なく作れて、どちらも直る。"""
    state = ls.base_state(open=ls.opened("design", seq=2), pending_review=ls.pending("red", "2026-10-17T10:00:00"))
    s = snap(state, "2026-10-17T10:00:00+09:00")
    assert st(s, "design")["started_at"] == st(s, "red")["pending_since"] == "2026-10-17T01:00:00+00:00"


def test_d0027_ac21_generated_at_comes_from_now_in_utc():
    """D0027-AC-21: generated_at は引数の今から作り、UTC のずれつき ISO 8601（秒まで）になる。"""
    s = snap(ls.base_state(), now=datetime(2026, 10, 17, 21, 5, 9, 999999, tzinfo=JST))
    assert s["generated_at"] == "2026-10-17T12:05:09+00:00"


@pytest.mark.parametrize(
    "now,expected",
    [
        (datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC), "2026-01-01T00:00:00+00:00"),
        (datetime(2026, 1, 1, 0, 30, 0, tzinfo=timezone(timedelta(hours=9))), "2025-12-31T15:30:00+00:00"),
        (datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone(timedelta(hours=-8))), "2027-01-01T07:59:59+00:00"),
        (datetime(2024, 2, 29, 12, 0, 0, 5, tzinfo=UTC), "2024-02-29T12:00:00+00:00"),
    ],
    ids=["utc", "jst_prev_day", "us_next_year", "leap_day"],
)
def test_d0027_ac21_generated_at_conversions(now, expected):
    """D0027-AC-21: 今のずれ・日付またぎ・うるう日・マイクロ秒を正しく扱う。"""
    assert snap(ls.base_state(), now=now)["generated_at"] == expected


def test_d0027_ac21_naive_now_is_read_in_local_tz():
    """D0027-AC-21: ずれなしの今は local_tz の時刻として読む。"""
    s = snap(ls.base_state(), now=datetime(2026, 10, 17, 21, 0, 0), local_tz=JST)
    assert s["generated_at"] == "2026-10-17T12:00:00+00:00"


def test_d0027_ac21_generated_at_is_the_same_in_the_empty_form():
    """D0027-AC-21: 記録なしの形の generated_at も、今から作る。"""
    assert snap(None, now=datetime(2026, 10, 17, 21, 0, 0, tzinfo=JST))["generated_at"] == "2026-10-17T12:00:00+00:00"


# ---- AC-22〜25 記録なし・壊れた state.json（ファイルを読む部分） ------------------------------------


def test_d0027_ac22_missing_state_gives_the_empty_form(tmp_path):
    """D0027-AC-22: state.json が無い（フォルダはある）とき、記録なしの決まった形になる。"""
    (tmp_path / "logs").mkdir()
    assert live.read_state(tmp_path) is None
    assert snap(live.read_state(tmp_path)) == EMPTY_FORM


def test_d0027_ac22_empty_form_is_exactly_this(tmp_path):
    """D0027-AC-22: 記録なしの形は、empty が true・name と final が null・stages が空。キーの順も固定。"""
    s = snap(None)
    assert s == EMPTY_FORM
    assert list(s) == KEYS
    assert s["empty"] is True
    assert json.loads(live.dumps(s)) == EMPTY_FORM


def test_d0027_ac22_normal_snapshot_says_empty_false():
    """D0027-AC-22: 普通の写しは empty が false。"""
    assert snap(ls.base_state())["empty"] is False


def test_d0027_ac23_missing_dir_gives_the_empty_form(tmp_path):
    """D0027-AC-23: 読み先のフォルダ自体が無くても、記録なしの形（例外で落ちない）。"""
    assert live.read_state(tmp_path / "nope" / "deeper") is None
    assert live.read_open_at(tmp_path / "nope", ls.base_state(open=ls.opened("design", seq=1))) is None
    assert snap(live.read_state(tmp_path / "nope")) == EMPTY_FORM


def test_d0027_ac23_a_file_in_place_of_the_dir_gives_the_empty_form(tmp_path):
    """D0027-AC-23: 読み先がフォルダでなくファイルでも、記録なしの形。"""
    f = tmp_path / "afile"
    f.write_text("{}", encoding="utf-8")
    assert live.read_state(f) is None


def test_d0027_ac23_path_with_nul_does_not_raise(tmp_path):
    """D0027-AC-23: 名前に NUL の入った読み先でも、例外を出さず記録なしになる。"""
    assert live.read_state(Path(str(tmp_path) + "/a\x00b")) is None


def _valid_state_bytes() -> bytes:
    return json.dumps(ls.base_state(), ensure_ascii=False).encode("utf-8")


@pytest.mark.parametrize(
    "raw",
    [
        b"", b" \n\t ", b"{", b'{"stages": [', b'{"name": "x"', b'{"name": "x",}', b"\xef\xbb\xbf" + _valid_state_bytes(),
        b"\xff\xfe{\x00}\x00", b"\xff\xff\xff", b"\x80abc", b'{"name": "\xff\xfe"}', _valid_state_bytes()[:40], b"\x00" * 64,
        b"{'name': 'x'}", b"name: x", b"<html></html>", b"[" * 100000, b'{"a":' * 50000, b"{" * 100000,
        b'{"a": 1} trailing', b"{} {}",
    ],
    ids=["empty", "blank", "open_brace", "cut_stages", "cut_name", "trailing_comma", "bom", "utf16", "invalid_bytes", "latin1",
         "bad_utf8_in_string", "cut_in_half", "nuls", "single_quotes", "yaml", "html", "deep_array", "deep_object_a", "deep_braces",
         "trailing_garbage", "two_documents"],
)
def test_d0027_ac24_unreadable_state_gives_the_empty_form(tmp_path, raw):
    """D0027-AC-24: 空・途中で切れた・BOM つき・UTF-8 でない・深すぎる入れ子の state.json は、記録なしの形になる。"""
    (tmp_path / "state.json").write_bytes(raw)
    assert live.read_state(tmp_path) is None
    assert snap(live.read_state(tmp_path)) == EMPTY_FORM


def test_d0027_ac24_valid_state_is_read_back_as_is(tmp_path):
    """D0027-AC-24: 正しい state.json は、そのまま辞書として読める（上の「読めない」が何でも None にしているのではない）。"""
    state = ls.base_state(name="日本語の名前 😀")
    ls.write_state(tmp_path, state)
    assert live.read_state(tmp_path) == state


@pytest.mark.parametrize("raw", [b"[]", b"[1, 2]", b"null", b"123", b"-1.5", b'"text"', b'"{}"', b"true", b"false", b"1e999", b"NaN", b"Infinity"],
                         ids=["array", "array_n", "null", "int", "float", "string", "string_obj", "true", "false", "inf_number", "nan", "infinity"])
def test_d0027_ac25_non_object_top_level_gives_the_empty_form(tmp_path, raw):
    """D0027-AC-25: 最上位が配列・null・数・文字・真偽のとき、記録なしの形になる。"""
    (tmp_path / "state.json").write_bytes(raw)
    assert live.read_state(tmp_path) is None
    assert snap(live.read_state(tmp_path)) == EMPTY_FORM


@pytest.mark.parametrize("value", [[], [1], None, 5, 1.5, "text", True, False, ()], ids=repr)
def test_d0027_ac25_non_object_state_gives_the_empty_form_in_build(value):
    """D0027-AC-25: 組み立てる関数に辞書でない値が渡されても、記録なしの形（open_at が何でも）。"""
    assert snap(value, "2026-10-17T10:00:00+09:00") == EMPTY_FORM


# ---- AC-26〜30 壊れた項目 -------------------------------------------------------------------------


@pytest.mark.parametrize("stages", [..., None, "abc", 5, 1.5, True, {}, {"a": 1}, {"name": "x"}, [], "requirements"], ids=lambda v: "missing" if v is ... else repr(v))
def test_d0027_ac26_missing_or_bad_stages_give_empty_stages_but_keep_name_and_final(stages):
    """D0027-AC-26: stages が無い・null・配列でない・空のとき、stages は空の配列。name と final は読める。"""
    state = ls.base_state(final="PASSED", runs=[ls.run("design", seq=1)])
    if stages is ...:
        del state["stages"]
    else:
        state["stages"] = stages
    s = snap(state)
    assert s["stages"] == []
    assert (s["name"], s["final"], s["empty"]) == ("テスト用のセッション", "PASSED", False)


GOOD_A = ls.stage_entry("requirements")
GOOD_B = ls.stage_entry("design")


@pytest.mark.parametrize(
    "bad",
    [1, 1.5, None, "text", "design", True, [], [GOOD_B], (), {}, {"label": "x"}, {"name": None}, {"name": 5}, {"name": True}, {"name": []}, {"name": {}},
     {"name": ["design"]}, {"name": 1.5}],
    ids=repr,
)
def test_d0027_ac27_bad_stage_entries_are_skipped(bad):
    """D0027-AC-27: stages の要素が辞書でない・name が無い・name が文字でないとき、その要素を飛ばして残りで作る。"""
    state = ls.base_state(stages=[GOOD_A, bad, GOOD_B])
    s = snap(state)
    assert [x["name"] for x in s["stages"]] == ["requirements", "design"]


def test_d0027_ac27_all_stage_entries_bad_gives_empty_stages():
    """D0027-AC-27: 全部が壊れていれば stages は空で、ほかの項目は読む。"""
    s = snap(ls.base_state(stages=[1, None, "x", [], {}]))
    assert s["stages"] == [] and s["name"] == "テスト用のセッション"


def test_d0027_ac28_duplicate_stage_name_uses_the_first():
    """D0027-AC-28: 同じ name の段が重なるとき、最初の1つだけを使う。"""
    state = ls.base_state(stages=[ls.stage_entry("a", "最初"), ls.stage_entry("b"), ls.stage_entry("a", "二つ目"), ls.stage_entry("a", "三つ目")],
                          runs=[ls.run("a", seq=1)])
    s = snap(state)
    assert [(x["name"], x["label"]) for x in s["stages"]] == [("a", "最初"), ("b", "b")]
    assert s["stages"][0]["status"] == "done"


def test_d0027_ac28_names_that_clean_to_the_same_text_are_not_merged_wrongly():
    """D0027-AC-28: 重なりの判定は元の name で行う（違う名前は、別の段として残す）。"""
    state = ls.base_state(stages=[ls.stage_entry("a"), ls.stage_entry("A"), ls.stage_entry("a ")])
    names = [x["name"] for x in snap(state)["stages"]]
    assert names[:2] == ["a", "A"]


def test_d0027_ac29_unknown_stage_in_runs_is_ignored():
    """D0027-AC-29: stages に無い段の runs の行は無視する（段を足さない）。"""
    state = with_runs([ls.run("ghost", seq=1, cost=9.0, turns=9, duration=9.0, is_error=True), ls.run("design", seq=2, cost=1.0)])
    s = snap(state)
    assert [x["name"] for x in s["stages"]] == list(ls.STAGES)
    assert (st(s, "design")["cost_usd"], st(s, "requirements")["cost_usd"]) == (1.0, None)
    assert "ghost" not in blob(s)


@pytest.mark.parametrize("stage_value", [None, 5, [], {}, True, 1.5, ["design"], {"a": 1}, ""], ids=repr)
def test_d0027_ac29_runs_with_bad_stage_values_are_ignored(stage_value):
    """D0027-AC-29: runs の行の stage が文字でない（辞書や配列の値も）とき、例外を出さず無視する。"""
    state = with_runs([{"stage": stage_value, "is_error": True, "seq": 1, "cost_usd": 5.0}, ls.run("design", seq=2, cost=1.0)])
    s = snap(state)
    assert st(s, "design")["cost_usd"] == 1.0
    assert sum(x["cost_usd"] or 0 for x in s["stages"]) == 1.0


def test_d0027_ac29_unknown_stage_in_open_and_pending_is_ignored():
    """D0027-AC-29: open・pending_review が未知の段を指すときも、無視する。"""
    s = snap(ls.base_state(open=ls.opened("ghost", seq=1), pending_review=ls.pending("phantom")), "2026-10-17T10:00:00+09:00")
    assert [x["status"] for x in s["stages"]] == ["waiting"] * 5
    assert all(x["started_at"] is None and x["pending_since"] is None for x in s["stages"])


@pytest.mark.parametrize("stage_value", [None, 5, [], {}, True, ["design"], {"a": 1}, ""], ids=repr)
def test_d0027_ac29_open_and_pending_with_bad_stage_values(stage_value):
    """D0027-AC-29: open.stage・pending_review.stage が文字でない（辞書や配列を含む）とき、例外を出さない。"""
    state = ls.base_state(open={"stage": stage_value, "seq": 1}, pending_review={"stage": stage_value, "since": "2026-10-17T10:00:00+09:00"})
    s = snap(state, "2026-10-17T10:00:00+09:00")
    assert [x["status"] for x in s["stages"]] == ["waiting"] * 5


TYPE_CASES = [
    ("attempt_is_string", {"runs": [ls.run("design", seq=1, attempt="2", cost=0.5, turns=2, duration=3.0)]}, "design", {"attempt": None, "cost_usd": 0.5, "turns": 2, "duration_sec": 3.0, "status": "done"}),
    ("num_turns_is_bool", {"runs": [ls.run("design", seq=1, attempt=1, cost=0.5, turns=True, duration=3.0)]}, "design", {"attempt": 1, "cost_usd": 0.5, "duration_sec": 3.0, "status": "done"}),
    ("cost_is_string", {"runs": [ls.run("design", seq=1, attempt=1, cost="0.5", turns=2, duration=3.0)]}, "design", {"attempt": 1, "turns": 2, "duration_sec": 3.0, "status": "done"}),
    ("duration_is_list", {"runs": [ls.run("design", seq=1, attempt=1, cost=0.5, turns=2, duration=[3.0])]}, "design", {"attempt": 1, "cost_usd": 0.5, "turns": 2, "status": "done"}),
    ("label_is_number", {"stages": [ls.stage_entry("design") | {"label": 5}]}, "design", {"label": "design", "status": "waiting"}),
    ("label_is_list", {"stages": [ls.stage_entry("design") | {"label": ["設計"]}]}, "design", {"label": "design"}),
    ("runs_is_dict", {"runs": {"stage": "design", "seq": 1}}, "design", {"status": "waiting", "attempt": None, "cost_usd": None}),
    ("runs_is_string", {"runs": "design"}, "design", {"status": "waiting"}),
    ("runs_is_null", {"runs": None}, "design", {"status": "waiting"}),
    ("open_is_string", {"open": "design", "runs": [ls.run("design", seq=1)]}, "design", {"status": "done"}),
    ("open_is_list", {"open": ["design"]}, "design", {"status": "waiting"}),
    ("open_is_number", {"open": 5}, "design", {"status": "waiting"}),
    ("open_stage_missing", {"open": {"seq": 1}}, "design", {"status": "waiting"}),
    ("pending_is_list", {"pending_review": ["design"], "runs": [ls.run("design", seq=1)]}, "design", {"status": "done"}),
    ("pending_is_string", {"pending_review": "design"}, "design", {"status": "waiting"}),
    ("pending_stage_missing", {"pending_review": {"since": "2026-10-17T10:00:00+09:00"}}, "design", {"status": "waiting"}),
    ("run_row_is_not_dict", {"runs": [5, None, "x", [], ls.run("design", seq=1, cost=0.5)]}, "design", {"status": "done", "cost_usd": 0.5}),
    ("run_row_is_a_list_of_dicts", {"runs": [[ls.run("design", seq=1)]]}, "design", {"status": "waiting"}),
    ("is_error_is_list", {"runs": [ls.run("design", seq=1, is_error=[True])]}, "design", {"status": "done"}),
    ("review_is_number", {"runs": [ls.run("design", seq=1), {"stage": "design", "review": 5}]}, "design", {"status": "done"}),
    ("review_is_list", {"runs": [ls.run("design", seq=1), {"stage": "design", "review": ["revise"]}]}, "design", {"status": "done"}),
    ("review_unknown_word", {"runs": [ls.run("design", seq=1), {"stage": "design", "review": "reject"}]}, "design", {"status": "done"}),
    ("stage_entry_review_is_string", {"stages": [ls.stage_entry("design") | {"review": "yes", "output": 5}]}, "design", {"status": "waiting"}),
    ("seq_is_string", {"runs": [ls.run("design", seq="1", is_error=True)]}, "design", {"status": "failed"}),
]


@pytest.mark.parametrize("over,stage,expected", [c[1:] for c in TYPE_CASES], ids=[c[0] for c in TYPE_CASES])
def test_d0027_ac30_wrong_typed_fields_become_null_and_the_rest_is_read(over, stage, expected):
    """D0027-AC-30: 項目の型違いでは、その項目だけを null か省いて、ほかは読む（例外を出さない）。"""
    s = snap(ls.base_state(**over))
    assert s["name"] == "テスト用のセッション" and s["empty"] is False
    x = st(s, stage)
    for key, value in expected.items():
        assert x[key] == value, key


@pytest.mark.parametrize("name", [5, 1.5, True, [], ["名前"], {}, {"a": 1}, None], ids=repr)
def test_d0027_ac30_wrong_typed_name_becomes_null(name):
    """D0027-AC-30: セッション名が文字でないときは null。段は読む。"""
    s = snap(ls.base_state(name=name))
    assert s["name"] is None and len(s["stages"]) == 5


# ---- AC-31 数 --------------------------------------------------------------------------------------

BAD_NUMBERS = [float("nan"), float("inf"), float("-inf"), -1, -0.01, -1e-9, 1e308, 10**30, 10**400, -(10**400), 1e9 + 1, True, "1", None, [], {}, [1]]


def _sum_of(field, bad, good):
    runs = [ls.run("design", seq=1, **{field: good}), ls.run("design", seq=2, **{field: bad})]
    return st(snap(with_runs(runs)), "design")


@pytest.mark.parametrize("bad", BAD_NUMBERS, ids=lambda v: repr(v)[:30])
def test_d0027_ac31_bad_numbers_are_dropped_cost(bad):
    """D0027-AC-31: 費用の NaN・Infinity・負・巨大・真偽・文字は、合計に足さない（良い方の 0.5 だけ残る）。"""
    assert _sum_of("cost", bad, 0.5)["cost_usd"] == 0.5


@pytest.mark.parametrize("bad", BAD_NUMBERS + [1.5, 2.0], ids=lambda v: repr(v)[:30])
def test_d0027_ac31_bad_numbers_are_dropped_turns(bad):
    """D0027-AC-31: ターンの NaN・負・巨大・小数・真偽・文字は、合計に足さない（int だけ）。"""
    assert _sum_of("turns", bad, 2)["turns"] == 2


@pytest.mark.parametrize("bad", BAD_NUMBERS, ids=lambda v: repr(v)[:30])
def test_d0027_ac31_bad_numbers_are_dropped_duration(bad):
    """D0027-AC-31: 時間の NaN・Infinity・負・巨大・真偽・文字は、合計に足さない。"""
    assert _sum_of("duration", bad, 1.5)["duration_sec"] == 1.5


@pytest.mark.parametrize("field,key", [("cost", "cost_usd"), ("turns", "turns"), ("duration", "duration_sec")])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, 10**400, True, "7", None], ids=lambda v: repr(v)[:20])
def test_d0027_ac31_only_bad_numbers_give_null_or_zero(field, key, bad):
    """D0027-AC-31: 数が全部壊れているときは、null か 0（NaN・Infinity・負にはならない）。"""
    value = st(snap(with_runs([ls.run("design", seq=1, **{field: bad})])), "design")[key]
    assert value is None or value == 0


@pytest.mark.parametrize(
    "field,key,value",
    [("cost", "cost_usd", 1e9), ("cost", "cost_usd", 0), ("turns", "turns", 10**9), ("turns", "turns", 0), ("duration", "duration_sec", 1e9), ("duration", "duration_sec", 0)],
)
def test_d0027_ac31_upper_and_lower_bounds_are_accepted(field, key, value):
    """D0027-AC-31: 上限ちょうど（1e9）と 0 は受ける。"""
    assert st(snap(with_runs([ls.run("design", seq=1, **{field: value})])), "design")[key] == value


def test_d0027_ac31_output_is_strict_json():
    """D0027-AC-31: NaN・Infinity だらけの記録から作っても、写しの JSON は厳格な読みで通り、NaN・Infinity の文字が出ない。"""
    nasty = {"cost": float("nan"), "turns": float("inf"), "duration": float("-inf")}
    state = ls.base_state(total_cost_usd=float("nan"), runs=[ls.run(n, seq=i, attempt=float("nan"), **nasty) for i, n in enumerate(ls.STAGES, 1)])
    out = live.dumps(snap(state))
    assert out
    strict_loads(out)
    for token in ("NaN", "Infinity"):
        assert token not in out


def test_d0027_ac31_nan_survives_a_file_round_trip(tmp_path):
    """D0027-AC-31: ファイルの中に NaN・Infinity（Python の json が書いてしまう形）があっても、読んで作れて、写しは厳格な JSON。"""
    text = '{"name": "x", "stages": [{"name": "design", "label": "設計"}], "runs": [{"stage": "design", "seq": 1, "cost_usd": NaN, "num_turns": Infinity, "duration_sec": -Infinity, "attempt": NaN}]}'
    (tmp_path / "state.json").write_text(text, encoding="utf-8")
    state = live.read_state(tmp_path)
    assert isinstance(state, dict)
    out = live.dumps(snap(state))
    assert out
    strict_loads(out)


def test_d0027_ac31_dumps_refuses_nan():
    """D0027-AC-31: dumps は NaN を黙って書かない（allow_nan=False）。"""
    with pytest.raises(ValueError):
        live.dumps({"x": float("nan")})
    with pytest.raises(ValueError):
        live.dumps({"x": [float("inf")]})


# ---- AC-32 attempt ---------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [0, -1, -(10**30), 1.5, 2.0, 1000, 10**9, 10**30, 10**400, True, False, "3", "", None, [], [1], {}, float("nan"), float("inf")], ids=lambda v: repr(v)[:20])
def test_d0027_ac32_attempt_needs_a_positive_int(bad):
    """D0027-AC-32: attempt は 1〜999 の int だけ。0・負・小数・巨大・真偽・文字は null。"""
    assert st(snap(with_runs([ls.run("implement", seq=1, attempt=bad)])), "implement")["attempt"] is None


@pytest.mark.parametrize("good", [1, 2, 10, 998, 999])
def test_d0027_ac32_attempt_accepts_1_to_999(good):
    """D0027-AC-32: 1〜999 の int は受ける（上限ちょうどの 999 まで）。"""
    assert st(snap(with_runs([ls.run("implement", seq=1, attempt=good)])), "implement")["attempt"] == good


def test_d0027_ac32_open_attempt_of_a_running_stage_is_checked_too():
    """D0027-AC-32: 動いている段の open.attempt が 1〜999 でなければ、attempt は 0・負・巨大にならない。"""
    for bad in (0, -3, 1000, 10**30, 10**400, True, "2", 1.5, None, []):
        state = ls.base_state(open=ls.opened("implement", seq=2) | {"attempt": bad})
        x = st(snap(state), "implement")
        assert (x["status"], x["attempt"]) == ("running", None), bad


# ---- AC-33 巨大な記録 -----------------------------------------------------------------------------


def _padded_state_bytes(total: int) -> bytes:
    base = json.dumps(ls.base_state(name="大きい記録"), ensure_ascii=False)
    head = base[:-1] + ', "pad": "'
    tail = '"}'
    body = len(head.encode("utf-8")) + len(tail)
    return (head + "x" * (total - body) + tail).encode("utf-8")


def test_d0027_ac33_state_of_exactly_the_limit_is_read(tmp_path):
    """D0027-AC-33: state.json が上限（4 MiB）ちょうどなら読む。"""
    raw = _padded_state_bytes(MAX_STATE_BYTES)
    assert len(raw) == MAX_STATE_BYTES
    (tmp_path / "state.json").write_bytes(raw)
    state = live.read_state(tmp_path)
    assert isinstance(state, dict) and state["name"] == "大きい記録"
    assert snap(state)["name"] == "大きい記録"


def test_d0027_ac33_oversized_state_gives_the_empty_form(tmp_path):
    """D0027-AC-33: state.json が上限を1バイトでも超えたら、読まずに記録なしの形（決めきれない点 4 は A）。"""
    raw = _padded_state_bytes(MAX_STATE_BYTES + 1)
    assert len(raw) == MAX_STATE_BYTES + 1
    (tmp_path / "state.json").write_bytes(raw)
    assert live.read_state(tmp_path) is None
    assert snap(live.read_state(tmp_path)) == EMPTY_FORM


def test_d0027_ac33_far_oversized_state_gives_the_empty_form(tmp_path):
    """D0027-AC-33: 数十 MB の state.json でも、記録なしの形（メモリを守る）。"""
    (tmp_path / "state.json").write_bytes(b" " * (MAX_STATE_BYTES * 8) + b"{}")
    assert live.read_state(tmp_path) is None


def test_d0027_ac33_many_runs_build_within_the_size_limit():
    """D0027-AC-33: runs が数万行あっても、例外なく作れて、写しは上限以内。"""
    runs = [ls.run(ls.STAGES[i % 5], seq=i + 1, attempt=(i % 7) + 1, cost=0.01, turns=1, duration=0.5, result="x" * 50, errors=["e"] * 3) for i in range(30000)]
    s = snap(with_runs(runs))
    out = live.dumps(s)
    assert 0 < len(out.encode("utf-8")) <= MAX_BYTES
    assert [x["name"] for x in s["stages"]] == list(ls.STAGES)
    assert st(s, "design")["turns"] == 6000


def test_d0027_ac33_huge_session_name_is_cut(tmp_path):
    """D0027-AC-33: 3 MB を超える名前でも（state.json は上限以内）、切って作れる。"""
    ls.write_state(tmp_path, ls.base_state(name="あ" * 1_100_000))
    assert (tmp_path / "state.json").stat().st_size < MAX_STATE_BYTES
    s = snap(live.read_state(tmp_path))
    assert s["name"] == "あ" * 59 + "…"
    assert len(live.dumps(s).encode("utf-8")) <= MAX_BYTES


def test_d0027_ac33_huge_stage_name_and_label_are_cut(tmp_path):
    """D0027-AC-33: 数 MB の段の名前・表示名でも、切って作れて、その段の runs と結びつく。"""
    big = "い" * 300_000
    ls.write_state(tmp_path, ls.base_state(stages=[ls.stage_entry(big, big), ls.stage_entry("b", "b")], runs=[ls.run(big, seq=1, cost=0.5)]))
    assert (tmp_path / "state.json").stat().st_size < MAX_STATE_BYTES
    s = snap(live.read_state(tmp_path))
    assert s["stages"][0]["name"] == "い" * 39 + "…" and s["stages"][0]["label"] == "い" * 39 + "…"
    assert (s["stages"][0]["status"], s["stages"][0]["cost_usd"]) == ("done", 0.5)
    assert len(live.dumps(s).encode("utf-8")) <= MAX_BYTES


def test_d0027_ac33_huge_numbers_of_stage_entries_are_capped():
    """D0027-AC-33: 段が数万あっても、24 に収まる。"""
    state = ls.base_state(stages=[ls.stage_entry(f"s{i}") for i in range(50000)])
    s = snap(state)
    assert len(s["stages"]) == 24
    assert [x["name"] for x in s["stages"]] == [f"s{i}" for i in range(24)]


# ---- AC-34 古い記録 -------------------------------------------------------------------------------


def test_d0027_ac34_old_record_without_optional_keys_is_read():
    """D0027-AC-34: since・at・name・usage_summary・pipe・driver が無い古い記録でも、読めた項目だけで写しができる。"""
    old = {
        "started_at": "2026-10-17T10:00:00", "updated_at": "2026-10-17T10:00:00",
        "stages": [{"name": "requirements", "label": "要件定義"}, {"name": "design", "label": "設計"}],
        "final": None, "pending_review": {"stage": "design", "doc": "x.md"}, "open": None,
        "runs": [{"stage": "requirements", "is_error": False, "cost_usd": 0.2, "num_turns": 2, "duration_sec": 4.0, "seq": 1, "attempt": None}],
    }
    s = snap(old)
    assert s["name"] is None and s["empty"] is False
    assert [(x["name"], x["status"]) for x in s["stages"]] == [("requirements", "done"), ("design", "review")]
    assert st(s, "requirements")["cost_usd"] == 0.2
    assert st(s, "design")["pending_since"] is None


def test_d0027_ac34_minimal_object_is_not_the_empty_form():
    """D0027-AC-34: 空の辞書 {} でも「記録なし」ではなく、stages 空・empty false の写しになる（オブジェクトではある）。"""
    s = snap({})
    assert s["stages"] == [] and s["name"] is None and s["final"] is None
    assert s["empty"] is False


def test_d0027_ac34_runs_row_without_seq_or_attempt():
    """D0027-AC-34: seq・attempt・note の無い行（もっと古い書き方）でも読む。"""
    state = ls.base_state(runs=[{"stage": "design", "is_error": False, "cost_usd": 0.1}])
    x = st(snap(state), "design")
    assert x["status"] == "done" and x["attempt"] is None and x["cost_usd"] == 0.1


# ---- AC-35 読みで例外が出る種類 --------------------------------------------------------------------


def test_d0027_ac35_state_that_is_a_folder_gives_the_empty_form(tmp_path):
    """D0027-AC-35: state.json という名前のフォルダがあっても、記録なしの形。"""
    (tmp_path / "state.json").mkdir()
    assert live.read_state(tmp_path) is None
    assert snap(live.read_state(tmp_path)) == EMPTY_FORM


def test_d0027_ac35_broken_symlink_gives_the_empty_form(tmp_path):
    """D0027-AC-35: シンボリックリンクの切れた state.json でも、記録なしの形。"""
    try:
        (tmp_path / "state.json").symlink_to(tmp_path / "missing-target.json")
    except (OSError, NotImplementedError):
        pytest.skip("シンボリックリンクを作れない環境（Windows の権限など）")
    assert live.read_state(tmp_path) is None


def test_d0027_ac35_symlink_loop_gives_the_empty_form(tmp_path):
    """D0027-AC-35: 輪になったシンボリックリンクでも、落ちずに記録なしの形。"""
    try:
        (tmp_path / "a").symlink_to(tmp_path / "b")
        (tmp_path / "b").symlink_to(tmp_path / "a")
        (tmp_path / "state.json").symlink_to(tmp_path / "a")
    except (OSError, NotImplementedError):
        pytest.skip("シンボリックリンクを作れない環境")
    assert live.read_state(tmp_path) is None


def test_d0027_ac35_unreadable_permission_gives_the_empty_form(tmp_path):
    """D0027-AC-35: 読む権限の無い state.json でも、記録なしの形（権限を無視する実行者の環境では skip）。"""
    path = ls.write_state(tmp_path, ls.base_state())
    try:
        path.chmod(0)
        try:
            path.read_bytes()
        except OSError:
            pass
        else:
            pytest.skip("権限を無視して読める実行者（root など）や、権限の無い環境")
        assert live.read_state(tmp_path) is None
    finally:
        path.chmod(0o644)


def test_d0027_ac35_unreadable_work_dir_permission_gives_the_empty_form(tmp_path):
    """D0027-AC-35: 読み先のフォルダを開く権限が無くても、記録なしの形（権限を無視できる実行者では skip）。"""
    work = tmp_path / "w"
    ls.write_state(work, ls.base_state())
    try:
        work.chmod(0)
        if os.access(work, os.R_OK | os.X_OK):
            pytest.skip("権限を無視して読める実行者（root など）や、権限の無い環境")
        assert live.read_state(work) is None
    finally:
        work.chmod(0o755)


# ---- AC-36〜40 ログ --------------------------------------------------------------------------------

PROMPT_OK = ls.prompt_line("2026-10-17T10:00:00+09:00")


def _open_state(stage="design", seq=2, attempt=None, log=None):
    return ls.base_state(open=ls.opened(stage, seq=seq, attempt=attempt, log=log))


def test_d0027_ac36_no_logs_gives_null_started_at(tmp_path):
    """D0027-AC-36: logs/ が無いとき、started_at は null で、状態は state.json から決まる。"""
    state = _open_state()
    ls.write_state(tmp_path, state)
    at = live.read_open_at(tmp_path, live.read_state(tmp_path))
    assert at is None
    s = snap(live.read_state(tmp_path), at)
    assert all(x["started_at"] is None for x in s["stages"]) and st(s, "design")["status"] == "running"


def test_d0027_ac36_empty_logs_dir_gives_none(tmp_path):
    """D0027-AC-36: logs/ が空のとき None。"""
    (tmp_path / "logs").mkdir()
    assert live.read_open_at(tmp_path, _open_state()) is None


def test_d0027_ac36_empty_log_file_gives_none(tmp_path):
    """D0027-AC-36: ログのファイルが空でも None。"""
    ls.write_log(tmp_path, "02_design.jsonl", [])
    (tmp_path / "logs" / "02_design.jsonl").write_bytes(b"")
    assert live.read_open_at(tmp_path, _open_state()) is None


def test_d0027_ac36_log_that_is_a_folder_gives_none(tmp_path):
    """D0027-AC-36: ログの名前のフォルダがあっても、例外を出さず None。"""
    (tmp_path / "logs" / "02_design.jsonl").mkdir(parents=True)
    assert live.read_open_at(tmp_path, _open_state()) is None


@pytest.mark.parametrize("state", [None, [], "x", 5, {}, {"open": None}, {"open": "02_design.jsonl"}, {"open": []}, {"open": {}}, {"open": {"stage": "design"}},
                                   {"open": {"stage": "design", "log": None}}, {"open": {"stage": "design", "log": 5}}], ids=repr)
def test_d0027_ac36_state_without_a_usable_open_gives_none(tmp_path, state):
    """D0027-AC-36: 動いている段が無い・open が壊れているとき、ログは読まず None（例外なし）。"""
    ls.write_log(tmp_path, "02_design.jsonl", [PROMPT_OK])
    assert live.read_open_at(tmp_path, state) is None


def test_d0027_ac36_reads_the_open_log_and_returns_at_as_written(tmp_path):
    """D0027-AC-36: 動いている段のログの最初の Prompt 行の at を、文字のまま返す。"""
    ls.write_log(tmp_path, "02_design.jsonl", [ls.prompt_line("2026-10-17T10:00:00.5+09:00")])
    assert live.read_open_at(tmp_path, _open_state()) == "2026-10-17T10:00:00.5+09:00"


@pytest.mark.parametrize(
    "stage,seq,attempt,log",
    [("requirements", 1, None, "01_requirements.jsonl"), ("implement", 5, 2, "05_implement_2.jsonl"), ("fetch_data", 12, None, "12_fetch_data.jsonl"),
     ("check-2", 3, 10, "03_check-2_10.jsonl"), ("検証", 3, None, "03_検証.jsonl"), ("design", 100, None, "100_design.jsonl")],
)
def test_d0027_ac36_normal_log_names_are_read(tmp_path, stage, seq, attempt, log):
    """D0027-AC-36: 本体の付ける名前（NN_段[_回].jsonl）のログは、段の名前に - _ や日本語が入っていても読む。"""
    ls.write_log(tmp_path, log, [ls.prompt_line("2026-10-17T10:00:00+09:00")])
    state = ls.base_state(stages=[ls.stage_entry(stage)], open=ls.opened(stage, seq=seq, attempt=attempt, log=log))
    assert live.read_open_at(tmp_path, state) == "2026-10-17T10:00:00+09:00"


def test_d0027_ac37_bad_log_lines_are_skipped(tmp_path):
    """D0027-AC-37: 空行・壊れた JSON・最上位が配列や数の行・Prompt でない行を飛ばして、最初の Prompt 行の at を取る。"""
    ls.write_log(tmp_path, "02_design.jsonl", ["", "   ", "not json", "{", "[]", "[1,2]", "123", "null", '"x"', "true", '{"_type": 5}', '{"_type": ["Prompt"]}',
                                                 '{"_type": "prompt", "at": "WRONG-CASE"}', '{"_type": "SystemMessage", "at": "WRONG-TYPE"}', PROMPT_OK])
    assert live.read_open_at(tmp_path, _open_state()) == "2026-10-17T10:00:00+09:00"


def test_d0027_ac37_only_bad_lines_give_none(tmp_path):
    """D0027-AC-37: Prompt 行が1つも無い（壊れた行・ほかの種類の行だけ）ログは None。"""
    ls.write_log(tmp_path, "02_design.jsonl", ["", "not json", "[]", {"_type": "SystemMessage"}, {"_type": "ResultMessage", "at": "2026-10-17T10:00:00+09:00"}])
    assert live.read_open_at(tmp_path, _open_state()) is None


def test_d0027_ac37_first_prompt_line_wins(tmp_path):
    """D0027-AC-37: Prompt 行が複数あるときは、最初の行の at。"""
    ls.write_log(tmp_path, "02_design.jsonl", [{"_type": "SystemMessage"}, ls.prompt_line("2026-10-17T10:00:00+09:00"), ls.prompt_line("2026-10-17T11:00:00+09:00")])
    assert live.read_open_at(tmp_path, _open_state()) == "2026-10-17T10:00:00+09:00"


@pytest.mark.parametrize("at", [123, 1.5, None, True, [], {}, ["2026-10-17T10:00:00+09:00"]], ids=repr)
def test_d0027_ac37_prompt_without_a_text_at_gives_none(tmp_path, at):
    """D0027-AC-37: Prompt 行の at が文字でない（無いものを含む）とき、None。"""
    ls.write_log(tmp_path, "02_design.jsonl", [ls.prompt_line(at)])
    assert live.read_open_at(tmp_path, _open_state()) is None


def test_d0027_ac37_prompt_without_at_key_gives_none(tmp_path):
    """D0027-AC-37: at のキーが無い古い Prompt 行（D0017 より前）は None。"""
    line = ls.prompt_line("x")
    del line["at"]
    ls.write_log(tmp_path, "02_design.jsonl", [line])
    assert live.read_open_at(tmp_path, _open_state()) is None


def test_d0027_ac37_invalid_utf8_line_is_skipped(tmp_path):
    """D0027-AC-37: UTF-8 として読めない行があっても、次の Prompt 行を読む。"""
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "02_design.jsonl").write_bytes(b"\xff\xfe\xfd garbage\n" + json.dumps(PROMPT_OK).encode("utf-8") + b"\n")
    assert live.read_open_at(tmp_path, _open_state()) == "2026-10-17T10:00:00+09:00"


def test_d0027_ac37_crlf_lines_are_read(tmp_path):
    """D0027-AC-37: 改行が CRLF のログも読める。"""
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "02_design.jsonl").write_bytes(b'{"_type": "SystemMessage"}\r\n' + json.dumps(PROMPT_OK).encode("utf-8") + b"\r\n")
    assert live.read_open_at(tmp_path, _open_state()) == "2026-10-17T10:00:00+09:00"


def test_d0027_ac37_last_line_without_newline_is_read(tmp_path):
    """D0027-AC-37: 最後の行に改行が無くても、その行が完全な JSON なら読む（先頭 64 KiB に収まる場合）。"""
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "02_design.jsonl").write_bytes(json.dumps(PROMPT_OK).encode("utf-8"))
    assert live.read_open_at(tmp_path, _open_state()) == "2026-10-17T10:00:00+09:00"


def test_d0027_ac37_line_count_boundary_is_fifty(tmp_path):
    """D0027-AC-37: 読むのは最大 50 行。50 行目の Prompt は読み、51 行目の Prompt は読まない。"""
    ls.write_log(tmp_path, "02_design.jsonl", ["x"] * 49 + [PROMPT_OK])
    assert live.read_open_at(tmp_path, _open_state()) == "2026-10-17T10:00:00+09:00"
    ls.write_log(tmp_path, "02_design.jsonl", ["x"] * 50 + [PROMPT_OK])
    assert live.read_open_at(tmp_path, _open_state()) is None


def test_d0027_ac37_real_recorder_log_is_read(tmp_path):
    """D0027-AC-37: 本物の Recorder が書いたログの at を読める（本体の書き方とずれていない）。"""
    work = ls.dev_record_midway(tmp_path)
    state = live.read_state(work)
    raw = json.loads((work / "logs" / state["open"]["log"]).read_text(encoding="utf-8").splitlines()[0])
    assert live.read_open_at(work, state) == raw["at"]


def test_d0027_ac38_huge_log_line_is_skipped(tmp_path):
    """D0027-AC-38: 数 MB の1行は読まずに飛ばし、例外を出さない（先頭 64 KiB を超えた Prompt は読まない）。"""
    huge = json.dumps(ls.prompt_line("2026-10-17T10:00:00+09:00", prompt="x" * 5_000_000))
    ls.write_log(tmp_path, "02_design.jsonl", [huge, PROMPT_OK])
    assert live.read_open_at(tmp_path, _open_state()) is None


def test_d0027_ac38_huge_line_without_newline_does_not_raise(tmp_path):
    """D0027-AC-38: 改行の無い数 MB のログでも、例外を出さず None。"""
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "02_design.jsonl").write_bytes(b"x" * 5_000_000)
    assert live.read_open_at(tmp_path, _open_state()) is None


def test_d0027_ac38_prompt_line_over_16kib_is_skipped_and_under_is_read(tmp_path):
    """D0027-AC-38: 1行が 16 KiB を超える Prompt 行は飛ばし、16 KiB 以内の長い行は読む。"""
    ls.write_log(tmp_path, "02_design.jsonl", [ls.prompt_line("2026-10-17T10:00:00+09:00", prompt="x" * 10_000)])
    assert live.read_open_at(tmp_path, _open_state()) == "2026-10-17T10:00:00+09:00"
    ls.write_log(tmp_path, "02_design.jsonl", [ls.prompt_line("2026-10-17T10:00:00+09:00", prompt="x" * 16_500)])
    assert live.read_open_at(tmp_path, _open_state()) is None


def test_d0027_ac38_a_huge_line_in_the_middle_is_skipped_but_later_lines_in_range_are_read(tmp_path):
    """D0027-AC-38: 16 KiB を超える行を飛ばしても、その後ろの（先頭 64 KiB に入る）Prompt 行は読む。"""
    ls.write_log(tmp_path, "02_design.jsonl", ["y" * 20_000, PROMPT_OK])
    assert live.read_open_at(tmp_path, _open_state()) == "2026-10-17T10:00:00+09:00"


def test_d0027_ac38_read_size_boundary_is_64_kib(tmp_path):
    """D0027-AC-38: 読むのは先頭 64 KiB。その中に終わる Prompt 行は読み、外にある行は読まない。"""
    filler = ["z" * 15_000] * 4  # 60,004 バイト
    ls.write_log(tmp_path, "02_design.jsonl", filler + [PROMPT_OK])
    assert live.read_open_at(tmp_path, _open_state()) == "2026-10-17T10:00:00+09:00"
    ls.write_log(tmp_path, "02_design.jsonl", ["z" * 15_000] * 5 + [PROMPT_OK])  # 75,005 バイト目から
    assert live.read_open_at(tmp_path, _open_state()) is None


# ---- AC-39 数千のログ ------------------------------------------------------------------------------


def test_d0027_ac39_only_the_open_log_is_opened(tmp_path):
    """D0027-AC-39: ログが数千あっても、写しのために開くログは動いている段の1つだけ。"""
    logs = tmp_path / "logs"
    logs.mkdir()
    for i in range(3000):
        (logs / f"{i + 10:02d}_design.jsonl").write_text(json.dumps(PROMPT_OK) + "\n", encoding="utf-8")
    ls.write_log(tmp_path, "02_design.jsonl", [ls.prompt_line("2026-10-17T11:00:00+09:00")])
    state = _open_state()
    ls.write_state(tmp_path, state)
    with watch_opens() as opened:
        loaded = live.read_state(tmp_path)
        at = live.read_open_at(tmp_path, loaded)
        s = live.build_snapshot(loaded, at, now=NOW, local_tz=JST)
    assert at == "2026-10-17T11:00:00+09:00"
    log_opens = [p for p in opened if p.endswith(".jsonl")]
    assert len(log_opens) <= 1, log_opens
    assert st(s, "design")["started_at"] == "2026-10-17T02:00:00+00:00"


def test_d0027_ac39_no_log_is_opened_when_nothing_is_running(tmp_path):
    """D0027-AC-39: 動いている段が無いときは、ログを1つも開かない。"""
    ls.write_log(tmp_path, "01_requirements.jsonl", [PROMPT_OK])
    state = ls.base_state(runs=[ls.run("requirements", seq=1)])
    with watch_opens() as opened:
        assert live.read_open_at(tmp_path, state) is None
    assert [p for p in opened if p.endswith(".jsonl")] == []


def test_d0027_ac39_build_snapshot_touches_no_files(tmp_path):
    """D0027-AC-39: 組み立てる関数は、ファイルを1つも開かない（純粋）。"""
    state = ls.base_state(open=ls.opened("design", seq=2), runs=[ls.run("requirements", seq=1)])
    with watch_opens() as opened:
        s = live.build_snapshot(state, "2026-10-17T10:00:00+09:00", now=NOW, local_tz=JST)
        live.dumps(s)
    assert s
    assert opened == []


# ---- AC-40 ログの名前 ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "log",
    ["../outside.jsonl", "..\\outside.jsonl", "./../outside.jsonl", "logs/../outside.jsonl", "sub/../../outside.jsonl", "../../outside.jsonl",
     "/ABS/outside.jsonl", "", ".", "..", "x\x00.jsonl", "02_design.jsonl\x00", 5, None, ["02_design.jsonl"], {"a": 1}, True],
    ids=lambda v: repr(v)[:30],
)
def test_d0027_ac40_log_name_with_separator_is_not_read(tmp_path, log):
    """D0027-AC-40: ログの名前に区切り（../ など）が入る・名前が壊れているとき、work_dir の外のファイルを読まず None。"""
    work = tmp_path / "w"
    inside = work / "outside.jsonl"  # logs/ の1つ上（work_dir の中だが logs/ の外）
    inside.parent.mkdir(parents=True)
    inside.write_text(json.dumps(PROMPT_OK) + "\n", encoding="utf-8")
    (work / "logs").mkdir()
    secret = tmp_path / "outside.jsonl"  # work_dir の外
    secret.write_text(json.dumps(ls.prompt_line("2000-01-01T00:00:00+00:00")) + "\n", encoding="utf-8")
    if isinstance(log, str) and log.startswith("/ABS/"):
        log = str(secret)
    with watch_opens() as opened:
        result = live.read_open_at(work, _open_state(log=log))
    assert result is None
    assert not [p for p in opened if p.endswith("outside.jsonl")], opened


def test_d0027_ac40_log_name_for_another_stage_is_not_read(tmp_path):
    """D0027-AC-40: open の段と違う段のログの名前を指していても、そのログは読まない。"""
    ls.write_log(tmp_path, "01_requirements.jsonl", [ls.prompt_line("2000-01-01T00:00:00+00:00")])
    state = ls.base_state(open=ls.opened("design", seq=2, log="01_requirements.jsonl"))
    with watch_opens() as opened:
        assert live.read_open_at(tmp_path, state) is None
    assert not [p for p in opened if p.endswith("01_requirements.jsonl")]


def test_d0027_ac40_log_name_without_the_jsonl_extension_is_not_read(tmp_path):
    """D0027-AC-40: .jsonl でないファイル（state.json など）は、ログとして読まない。"""
    ls.write_state(tmp_path, ls.base_state())
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "02_design.txt").write_text(json.dumps(PROMPT_OK), encoding="utf-8")
    for log in ("02_design.txt", "state.json", "../state.json", "02_design"):
        assert live.read_open_at(tmp_path, _open_state(log=log)) is None, log


def test_d0027_ac40_symlinked_log_is_not_read(tmp_path):
    """D0027-AC-40: シンボリックリンクのログは読まない（work_dir の外を読まない）。"""
    target = tmp_path / "elsewhere.jsonl"
    target.write_text(json.dumps(PROMPT_OK) + "\n", encoding="utf-8")
    work = tmp_path / "w"
    (work / "logs").mkdir(parents=True)
    try:
        (work / "logs" / "02_design.jsonl").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("シンボリックリンクを作れない環境")
    with watch_opens() as opened:
        assert live.read_open_at(work, _open_state()) is None
    assert not [p for p in opened if p.endswith("elsewhere.jsonl")]


def test_d0027_ac40_symlinked_logs_dir_is_not_read(tmp_path):
    """D0027-AC-40: logs フォルダがシンボリックリンクで外を指すときも、読まない。"""
    outside = tmp_path / "outside_logs"
    outside.mkdir()
    (outside / "02_design.jsonl").write_text(json.dumps(PROMPT_OK) + "\n", encoding="utf-8")
    work = tmp_path / "w"
    work.mkdir()
    try:
        (work / "logs").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("シンボリックリンクを作れない環境")
    assert live.read_open_at(work, _open_state()) is None


# ---- AC-41〜45 悪意のある文字・長さ・書き出し ----------------------------------------------------------

HOSTILE = [
    "<script>alert(1)</script>", "</script>", "<!--", "]]>", '"', "'", "`", "\\", "\\u003c", "${7*7}", "{{7*7}}", "javascript:alert(1)", "%s%n", "&lt;&amp;",
    "\u2028", "\u2029", "\x00\x01\x02\x1f\x7f\x80\x9f", "\x1b[31mred\x1b[0m", "\u202e", "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069",
    "\u200b\u200c\u200d\u200e\u200f", "\u2060\ufeff\u00ad\u061c", "🚀", "👨\u200d👩\u200d👧", "e" + "\u0301" * 50, "\ud800", "\udfff", "a\ud800\udc00b", "\ud83d",
    "\u0000" * 1000, "שלום עולם", "مرحبا", "\U0001f600" * 100, "\U0010ffff", "\ufffd", "<img src=x onerror=alert(1)>", "' OR '1'='1",
]


@pytest.mark.parametrize("text", HOSTILE, ids=lambda v: repr(v)[:30])
def test_d0027_ac41_hostile_text_does_not_raise(text):
    """D0027-AC-41: セッション名・段の名前・表示名に悪意のある文字が入っても、例外なく作れて、dumps が UTF-8 で書ける。"""
    state = ls.base_state(name=text, stages=[ls.stage_entry(text, text), ls.stage_entry("ok", text)])
    s = snap(state)
    out = live.dumps(s)
    out.encode("utf-8")
    assert json.loads(out) == s
    for value in [s["name"], *[x["name"] for x in s["stages"]], *[x["label"] for x in s["stages"]]]:
        assert value is None or (isinstance(value, str) and only_clean_chars(value))


CLEANED_AWAY = [
    "\x00", "\x01", "\x07", "\x08", "\x0e", "\x1b", "\x7f", "\x80", "\x9f", "\u200b", "\u200c", "\u200e", "\u200f", "\u202a",
    "\u202b", "\u202c", "\u202d", "\u202e", "\u2060", "\u2066", "\u2067", "\u2068", "\u2069", "\ufeff", "\u00ad", "\u061c", "\ud800", "\udbff", "\udc00", "\udfff",
]


@pytest.mark.parametrize("ch", CLEANED_AWAY, ids=lambda c: f"U+{ord(c):04X}")
def test_d0027_ac41_control_and_direction_characters_are_removed(ch):
    """D0027-AC-41: 制御文字・C1・行区切り・方向を変える記号・ゼロ幅の文字・孤立したサロゲートは、名前・段の名前・表示名から取り除かれる。"""
    state = ls.base_state(name=f"a{ch}b", stages=[ls.stage_entry(f"x{ch}y", f"p{ch}q")])
    s = snap(state)
    assert s["name"] == "ab"
    assert s["stages"][0]["name"] == "xy" and s["stages"][0]["label"] == "pq"


@pytest.mark.parametrize("ch", ["\t", "\n", "\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x1f", "\x85", " ", " "], ids=lambda c: f"U+{ord(c):04X}")
def test_d0027_ac41_whitespace_controls_never_remain(ch):
    """D0027-AC-41: タブ・改行・行区切りなど「空白でもある」制御文字は、残らない（除くか、空白1つにする）。"""
    s = snap(ls.base_state(name=f"a{ch}b"))
    assert s["name"] in ("ab", "a b")


def test_d0027_ac41_zero_width_joiner_is_kept_inside_emoji_sequences():
    """D0027-AC-41: 絵文字をつなぐ U+200D は残す（家族の絵文字が壊れない）。"""
    family = "👨\u200d👩\u200d👧\u200d👦"
    assert snap(ls.base_state(name=family))["name"] == family
    assert snap(ls.base_state(name="x" + family + "y"))["name"] == "x" + family + "y"


@pytest.mark.parametrize("text", ["🚀テスト", "日本語のなまえ", "שלום", "مرحبا", "e\u0301", "ｱｲｳ", "❤\ufe0f", "👍🏽", "🇯🇵", "A-Z_0-9.()[]{}"], ids=repr)
def test_d0027_ac41_ordinary_text_is_kept_as_is(text):
    """D0027-AC-41: 普通の文字（日本語・絵文字・結合文字・RTL の文字そのもの・記号）は、そのまま残す。"""
    assert snap(ls.base_state(name=text))["name"] == text


def test_d0027_ac41_script_text_is_kept_as_text_and_escaped_only_in_dumps():
    """D0027-AC-41: <script> は取り除かず文字としてそのまま持つ（表示側が textContent で出す）。dumps の出力では生で出ない。"""
    s = snap(ls.base_state(name="<script>alert(1)</script>"))
    assert s["name"] == "<script>alert(1)</script>"
    assert "<" not in live.dumps(s)


def test_d0027_ac41_whitespace_is_collapsed_and_trimmed():
    """D0027-AC-41: 空白の連続は1つにし、前後の空白は落とす（全角の空白も）。"""
    assert snap(ls.base_state(name="  a   b \u3000 c  "))["name"] == "a b c"


@pytest.mark.parametrize("text", ["", " ", "   \u3000 ", "\x00", "\u202e\u200b", "\ud800", "\x00 \ud800 \u2028"], ids=repr)
def test_d0027_ac41_empty_after_cleaning_gives_null_and_label_falls_back(text):
    """D0027-AC-41: 掃除して空になったら、セッション名は null。段の表示名は name で代える。"""
    s = snap(ls.base_state(name=text, stages=[ls.stage_entry("design", text)]))
    assert s["name"] is None
    assert s["stages"][0]["label"] == "design"


def test_d0027_ac41_stage_name_that_cleans_to_empty_is_handled():
    """D0027-AC-41: 段の name が掃除して空になるとき、例外を出さない（その段は飛ばすか、空でない名前にする）。"""
    s = snap(ls.base_state(stages=[ls.stage_entry("\x00\u202e"), ls.stage_entry("ok")]))
    assert "ok" in [x["name"] for x in s["stages"]]
    assert all(x["name"] for x in s["stages"])


def test_d0027_ac42_lone_surrogate_can_be_written_as_utf8():
    """D0027-AC-42: 孤立したサロゲートが入っていても、写しを UTF-8 で書き出せる（UnicodeEncodeError を出さない）。"""
    s = snap(ls.base_state(name="a\ud800b\udfff", stages=[ls.stage_entry("d\ud83d", "l\ude00")]))
    live.dumps(s).encode("utf-8")
    assert s["name"] == "ab"


def test_d0027_ac42_dumps_alone_survives_a_lone_surrogate():
    """D0027-AC-42: 掃除を通らない値に孤立サロゲートが残っていても、dumps は UTF-8 で書ける形にする（\\u エスケープ）。"""
    out = live.dumps({"x": "a\ud800b"})
    out.encode("utf-8")
    assert json.loads(out) == {"x": "a\ud800b"}


def test_d0027_ac42_lone_surrogate_from_a_json_escape_in_the_file(tmp_path):
    """D0027-AC-42: ファイルの中の \\ud800（孤立）も、読んで作って UTF-8 で書き出せる。対になった \\ud83d\\ude00 は絵文字として残る。"""
    text = r'{"name": "\ud800x\ud83d\ude00", "stages": [{"name": "d", "label": "\udc00\ud83d\ude00"}]}'
    (tmp_path / "state.json").write_text(text, encoding="utf-8")
    s = snap(live.read_state(tmp_path))
    live.dumps(s).encode("utf-8")
    assert s["name"] == "x😀"
    assert s["stages"][0]["label"] == "😀"


def test_d0027_ac43_session_name_is_cut_at_60_with_ellipsis():
    """D0027-AC-43: セッション名は 60 文字まで。61 文字なら 59 文字＋…。ちょうど 60 と 59 はそのまま。"""
    for n, expected in ((1, "あ"), (59, "あ" * 59), (60, "あ" * 60), (61, "あ" * 59 + "…"), (200, "あ" * 59 + "…")):
        assert snap(ls.base_state(name="あ" * n))["name"] == expected, n
    assert len(snap(ls.base_state(name="あ" * 61))["name"]) == 60


def test_d0027_ac43_label_is_cut_at_40():
    """D0027-AC-43: 段の名前と表示名は 40 文字まで。41 文字なら 39 文字＋…。"""
    for n in (1, 39, 40, 41, 300):
        keep = "{}" if n <= 40 else None
        name_expected = "い" * n if n <= 40 else "い" * 39 + "…"
        label_expected = "う" * n if n <= 40 else "う" * 39 + "…"
        s = snap(ls.base_state(stages=[ls.stage_entry("い" * n, "う" * n)]))
        assert s["stages"][0]["name"] == name_expected, n
        assert s["stages"][0]["label"] == label_expected, n
        assert keep is None or keep


def test_d0027_ac43_a_cut_stage_name_still_matches_its_runs():
    """D0027-AC-43: 長い段の名前を切っても、その段の runs（元の name で引く）が結びつく。"""
    long_name = "stage_" + "x" * 80
    state = ls.base_state(stages=[ls.stage_entry(long_name, "ラベル")], runs=[ls.run(long_name, seq=1, cost=0.5)])
    x = snap(state)["stages"][0]
    assert (x["status"], x["cost_usd"]) == ("done", 0.5)
    assert x["name"].endswith("…") and len(x["name"]) == 40


def test_d0027_ac43_cleaning_happens_before_cutting():
    """D0027-AC-43: 掃除（空白を詰める・制御文字を除く）をしてから長さを数える。"""
    assert snap(ls.base_state(name="  " + "a" * 60 + "\x00  "))["name"] == "a" * 60
    assert snap(ls.base_state(name="a" + "\u200b" * 500 + "b"))["name"] == "ab"
    assert snap(ls.base_state(name="a    " * 30))["name"] == " ".join(["a"] * 30)


EMOJI_UNITS = {
    "family": "👨\u200d👩\u200d👧\u200d👦", "combining": "e\u0301", "many_combining": "e" + "\u0301\u0323" * 5, "flag": "🇯🇵", "skin_tone": "👍🏽",
    "variation_selector": "❤\ufe0f", "keycap": "1\ufe0f\u20e3", "plain_emoji": "😀",
}


@pytest.mark.parametrize("unit", list(EMOJI_UNITS.values()), ids=list(EMOJI_UNITS))
def test_d0027_ac43_cut_does_not_split_emoji_or_combining_marks(unit):
    """D0027-AC-43: 絵文字・結合文字・異体字選択子・国旗・肌色の途中で割らない（60 個目までの数え方は「見た目の1つ」）。"""
    # 59 + 単位 + x で 61 個 → 59 個＋…（単位は丸ごと落ちる）
    assert snap(ls.base_state(name="a" * 59 + unit + "x"))["name"] == "a" * 59 + "…"
    # 58 + 単位 + xy で 61 個 → 58 個＋単位（59 個目）＋…
    assert snap(ls.base_state(name="a" * 58 + unit + "xy"))["name"] == "a" * 58 + unit + "…"
    # 58 + 単位 + x でちょうど 60 個 → そのまま（文字数は 60 を超えていても切らない）
    assert snap(ls.base_state(name="a" * 58 + unit + "x"))["name"] == "a" * 58 + unit + "x"
    # 表示名（40）も同じ数え方
    s = snap(ls.base_state(stages=[ls.stage_entry("s", "a" * 38 + unit + "xy")]))
    assert s["stages"][0]["label"] == "a" * 38 + unit + "…"


def test_d0027_ac43_flags_count_as_pairs():
    """D0027-AC-43: 国旗は2つの記号で1個と数える（2つの国旗は2個）。"""
    flags = "🇯🇵🇺🇸"
    assert snap(ls.base_state(name="a" * 57 + flags + "x"))["name"] == "a" * 57 + flags + "x"
    assert snap(ls.base_state(name="a" * 58 + flags + "x"))["name"] == "a" * 58 + "🇯🇵…"


def test_d0027_ac43_emoji_beyond_bmp_are_counted_per_character_not_per_surrogate():
    """D0027-AC-43: BMP の外の文字を1個と数える（サロゲート2つ分とは数えない）。"""
    assert snap(ls.base_state(name="😀" * 60))["name"] == "😀" * 60
    assert snap(ls.base_state(name="😀" * 61))["name"] == "😀" * 59 + "…"


def test_d0027_ac43_cut_result_never_ends_inside_a_cluster_for_long_marks():
    """D0027-AC-43: 結合文字の長い列を切っても、結合文字だけが先頭や末尾に孤立しない。"""
    name = snap(ls.base_state(name="e" + "\u0301" * 30 + "f" * 100))["name"]
    assert name.startswith("e\u0301") and name.endswith("…") and not name.endswith("\u0301…")


# ---- AC-44 全体の大きさ -----------------------------------------------------------------------------

CLUSTER = "👨\u200d👩\u200d👧\u200d👦"


def test_d0027_ac44_worst_case_stays_under_the_byte_limit():
    """D0027-AC-44: 段 24・文字の上限いっぱいの非 ASCII（エスケープで大きくなる絵文字）でも、写しは 32 KiB 以内。収まらない分は末尾の段から落とす。"""
    stages = [ls.stage_entry(f"{i:02d}" + CLUSTER * 50, f"{i:02d}" + CLUSTER * 50) for i in range(30)]
    s = snap(ls.base_state(name=CLUSTER * 100, stages=stages))
    out = live.dumps(s)
    assert 0 < len(out.encode("utf-8")) <= MAX_BYTES
    assert 1 <= len(s["stages"]) <= 24
    assert [x["name"][:2] for x in s["stages"]] == [f"{i:02d}" for i in range(len(s["stages"]))]
    json.loads(out)


def test_d0027_ac44_worst_case_with_all_numbers_and_times_filled():
    """D0027-AC-44: 数・時刻・判定が全部入った最悪の形でも 32 KiB 以内で、JSON として読める。"""
    names = [f"s{i:02d}" for i in range(24)]
    state = ls.base_state(
        name="あ" * 100, stages=[ls.stage_entry(n, "😀" * 80) for n in names], open=ls.opened(names[3], seq=9, attempt=999),
        pending_review=ls.pending(names[5], "2026-10-17T10:00:00+09:00"),
        runs=[ls.run(n, seq=i + 1, attempt=999, cost=123456.7891, turns=999999999, duration=123456.7) for i, n in enumerate(names)] + [ls.verdict("blocked", 999, stage="test")],
        final="STOPPED_BY_HUMAN",
    )
    out = live.dumps(snap(state, "2026-10-17T10:00:00+09:00"))
    assert 0 < len(out.encode("utf-8")) <= MAX_BYTES
    assert json.loads(out)["final"] == "STOPPED_BY_HUMAN"


@pytest.mark.parametrize("count,expected", [(0, 0), (1, 1), (23, 23), (24, 24), (25, 24), (26, 24), (1000, 24)])
def test_d0027_ac44_stage_count_is_capped(count, expected):
    """D0027-AC-44: 段の数は 24 まで。超えた分は捨てる（24 ちょうどは残す）。"""
    s = snap(ls.base_state(stages=[ls.stage_entry(f"s{i}") for i in range(count)]))
    assert [x["name"] for x in s["stages"]] == [f"s{i}" for i in range(expected)]


def test_d0027_ac44_dropped_stages_do_not_change_the_rest():
    """D0027-AC-44: 段を落としても、残る段の状態は変わらず、name・final も読める。"""
    state = ls.base_state(final="PASSED", stages=[ls.stage_entry(f"s{i}") for i in range(30)], runs=[ls.run("s0", seq=1, cost=1.0), ls.run("s29", seq=2)])
    s = snap(state)
    assert s["final"] == "PASSED" and s["name"] == "テスト用のセッション"
    assert s["stages"][0]["status"] == "done" and s["stages"][0]["cost_usd"] == 1.0


def test_d0027_ac44_ascii_worst_case_is_under_20kb():
    """D0027-AC-44: 設計の見積もり（最悪でも 20 KB 弱）が、通常の長さの記録で成り立つ。"""
    names = [f"stage_{i:02d}_" + "n" * 30 for i in range(24)]
    s = snap(ls.base_state(name="N" * 60, stages=[ls.stage_entry(n, "L" * 40) for n in names], runs=[ls.run(n, seq=i + 1, attempt=3, cost=1.2345, turns=99, duration=12.3) for i, n in enumerate(names)]))
    assert len(live.dumps(s).encode("utf-8")) < 20_000


# ---- AC-45 dumps -----------------------------------------------------------------------------------


def test_d0027_ac45_dumps_exact_format():
    """D0027-AC-45: 書き方が固定（ASCII だけ・隙間なし・キーの順そのまま・< > & を \\u 形・末尾に改行1つ）。"""
    assert live.dumps({"b": 1, "a": ["<>&", "あ", None, True, 1.5]}) == '{"b":1,"a":["\\u003c\\u003e\\u0026","\\u3042",null,true,1.5]}\n'


@pytest.mark.parametrize("text", HOSTILE, ids=lambda v: repr(v)[:30])
def test_d0027_ac45_dumps_has_no_raw_script_close_and_is_ascii(text):
    """D0027-AC-45: 出力に </script> が生で出ない。< > & は \\u エスケープで、全体が ASCII。1行で、末尾が改行。"""
    out = live.dumps(snap(ls.base_state(name=text, stages=[ls.stage_entry("a", text)])))
    assert out.isascii()
    assert "</" not in out and "<" not in out and ">" not in out and "&" not in out
    assert out.endswith("\n") and "\n" not in out[:-1] and "\r" not in out
    assert "\u2028" not in out and "\u2029" not in out


@pytest.mark.parametrize("text", HOSTILE, ids=lambda v: repr(v)[:30])
def test_d0027_ac45_dumps_can_be_loaded_back(text):
    """D0027-AC-45: dumps の出力は、厳格な読みで json に読み直せて、元の写しと等しい。"""
    s = snap(ls.base_state(name=text, stages=[ls.stage_entry("a", text)]))
    assert strict_loads(live.dumps(s)) == s


def test_d0027_ac45_dumps_is_stable_for_the_same_snapshot():
    """D0027-AC-45: 同じ写しは同じ文字列（キーを並べ替えない）。"""
    s = snap(ls.base_state(open=ls.opened("design", seq=2)))
    assert live.dumps(s) == live.dumps(copy.deepcopy(s))
    assert list(json.loads(live.dumps(s))) == KEYS


def test_d0027_ac45_dumps_returns_text_not_bytes():
    """D0027-AC-45: dumps は str を返す。"""
    assert type(live.dumps(snap(None))) is str


# ---- AC-74・75 古い記録・将来のキー ----------------------------------------------------------------------

OLD_FIXTURES = sorted(p for group in ("pipe_dev", "pipe_in") for p in (FIXTURES / group).iterdir() if p.is_dir()) + [
    FIXTURES / "showcase", FIXTURES / "showcase_running", FIXTURES / "showcase_waiting", FIXTURES / "showcase_running_next",
]


@pytest.mark.parametrize("src", OLD_FIXTURES, ids=lambda p: f"{p.parent.name}-{p.name}")
def test_d0027_ac74_old_fixture_records_make_snapshots(tmp_path, src):
    """D0027-AC-74: 古い版の記録（D0017 より前・パイプの記録・見本の記録）を読み先にしても、写しが作れる。"""
    work = tmp_path / "rec"
    shutil.copytree(src, work)
    state = live.read_state(work)
    assert isinstance(state, dict), src
    s = snap(state, live.read_open_at(work, state))
    assert s["empty"] is False
    assert [x["name"] for x in s["stages"]] == [e["name"] for e in state["stages"]]
    assert s["final"] == (state["final"] if state["final"] in FINAL_NAMES else None)
    assert all(x["status"] in {"waiting", "running", "review", "done", "failed", "revised"} for x in s["stages"])
    strict_loads(live.dumps(s))
    assert len(live.dumps(s).encode("utf-8")) <= MAX_BYTES


def test_d0027_ac74_old_fixture_states():
    """D0027-AC-74: 見本の記録の段の状態（動いている・確認待ち・終わり）が、記録の通りに出る。"""
    pairs = []
    for group in ("pipe_dev", "pipe_in"):
        running = json.loads((FIXTURES / group / "running" / "state.json").read_text(encoding="utf-8"))
        waiting = json.loads((FIXTURES / group / "waiting" / "state.json").read_text(encoding="utf-8"))
        finished = json.loads((FIXTURES / group / "finished" / "state.json").read_text(encoding="utf-8"))
        pairs.append((running, waiting, finished))
    for running, waiting, finished in pairs:
        assert st(snap(running), running["open"]["stage"])["status"] == "running"
        assert st(snap(waiting), waiting["pending_review"]["stage"])["status"] == "review"
        assert st(snap(waiting), waiting["pending_review"]["stage"])["pending_since"] is None  # since の無い古い形
        f = snap(finished)
        assert f["final"] == "PASSED" and all(x["status"] == "done" for x in f["stages"])
        assert st(f, "test")["verdict"] == "pass"
        assert st(f, "test")["attempt"] == 2 and st(f, "implement")["attempt"] == 2


def test_d0027_ac74_archived_record_makes_a_snapshot(tmp_path):
    """D0027-AC-74: archive/<日時>/ に移された記録を読み先にしても、写しが作れる。"""
    r = ls.recorder(tmp_path, datetime(2026, 10, 17, 10, 0, 0))
    r.start("最初のメモ", name="古い実行")
    r.begin("requirements")
    r.done("requirements", summary="失敗した", error=True)
    r.finish("STAGE_ERROR")
    r.start("次のメモ", name="新しい実行")
    work = ls.work_of(tmp_path)
    archived = [p for p in (work / "archive").iterdir() if p.is_dir()]
    assert len(archived) == 1
    state = live.read_state(archived[0])
    assert isinstance(state, dict)
    s = snap(state, live.read_open_at(archived[0], state))
    assert (s["name"], s["final"]) == ("古い実行", "STAGE_ERROR")
    assert st(s, "requirements")["status"] == "failed"
    assert snap(live.read_state(work))["name"] == "新しい実行"


def test_d0027_ac75_future_keys_do_not_change_the_snapshot():
    """D0027-AC-75: 本体が将来 state.json にキーを足しても、写しは変わらない（schema も中身も）。"""
    plain = ls.base_state(open=ls.opened("design", seq=2), runs=[ls.run("requirements", seq=1, cost=0.1), ls.verdict("pass", 1)],
                          pending_review=ls.pending("red"))
    future = copy.deepcopy(plain)
    future |= {"schema": 99, "version": 3, "new_top": {"a": [1, 2]}, "live": "LEAK-MARK"}
    for e in future["stages"]:
        e |= {"new_stage_key": 1, "status": "failed"}
    future["open"] |= {"new_open_key": 1, "status": "done"}
    future["pending_review"] |= {"new_pending_key": 1}
    for r in future["runs"]:
        r |= {"new_run_key": "LEAK-MARK", "status": "done"}
    a = live.dumps(snap(plain, "2026-10-17T10:00:00+09:00"))
    b = live.dumps(snap(future, "2026-10-17T10:00:00+09:00"))
    assert a == b
    assert '"schema":1' in a and "LEAK-MARK" not in b
