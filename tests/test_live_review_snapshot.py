"""D0039：進み具合の写しに足す `review`（確認待ちの段と識別子）。

写し（schema 1）の最後のキーとして `review`（{"stage", "id"} か null）を足す。`SCHEMA` は 1 のまま。
値は、確認待ちの段が写しに入っていて、状態が review で、段の名前が形に合い、since から識別子が作れ、上限で落ちていないときだけ入れる。
入れるのは段と識別子の2つだけ（since の文字・時刻・doc のパス・session_id は入れない）。

build_snapshot は純粋（時計もファイルも触らない）。記録は tmp_path の中に作るか、辞書で組む。
"""

from __future__ import annotations

import copy
import inspect
import json
import re
from pathlib import Path

import pytest

import live_support as ls
from pipe_in.engine import live, live_answer as la, live_watch

ROOT = Path(__file__).resolve().parents[1]
SINCE = "2026-10-17T10:02:15+09:00"
HEX10 = re.compile(r"[0-9a-f]{10}")
REVIEW_KEYS = ["schema", "generated_at", "empty", "name", "final", "stages", "review"]


def sid(value) -> str:
    return ascii(value)[:48]


def snap(state, open_at=None, **kw):
    kw.setdefault("local_tz", ls.JST)
    return live.build_snapshot(state, open_at, now=ls.NOW, **kw)


def pending_state(stage: str = "design", since=SINCE, **over) -> dict:
    return ls.base_state(pending_review=ls.pending(stage, since), **over)


def expected(stage: str = "design", since: str = SINCE) -> dict:
    return {"stage": stage, "id": ls.expected_review_id(stage, since)}


# ---- AC-20 確認待ちの写しに review が入る ---------------------------------------------------------------------------


@pytest.mark.parametrize("stage", ls.STAGES)
def test_d0039_ac20_pending_snapshot_has_review(stage):
    """D0039-AC-20: 確認待ちの記録の写しに review（段と識別子）が入る。キーの順は stage → id、識別子は check_answer が使うものと同じ式。"""
    s = snap(pending_state(stage))
    assert s["review"] == expected(stage)
    assert list(s["review"]) == ["stage", "id"]
    assert HEX10.fullmatch(s["review"]["id"])
    rows = {x["name"]: x["status"] for x in s["stages"]}
    assert rows[stage] == "review" and list(s)[-1] == "review"


def test_d0039_ac20_pending_snapshot_from_a_real_record_has_review(tmp_path):
    """D0039-AC-20: 本物の Recorder が書いた確認待ちの記録（state.json を読んで）の写しに、review が入る。"""
    work = ls.pending_project(tmp_path, "design")
    state = live.read_state(work)
    s = snap(state, live.read_open_at(work, state))
    since = ls.pending_of(work)["since"]
    assert s["review"] == {"stage": "design", "id": ls.expected_review_id("design", since)}
    assert list(s) == ls.KEYS


def test_d0039_ac20_review_is_for_the_stage_that_is_pending_even_in_the_middle_of_the_list():
    """D0039-AC-20: review の段は確認待ちの段（並びの途中でも）。ほかの段の状態は影響しない。"""
    state = pending_state("red", runs=[ls.run("requirements", seq=1), ls.review("requirements"), ls.run("design", seq=2), ls.review("design")])
    s = snap(state)
    assert s["review"] == expected("red")
    assert [x["status"] for x in s["stages"]] == ["done", "done", "review", "waiting", "waiting"]


def _mut(fn):
    def apply(state):
        fn(state)
        return state

    return apply


NULL_CASES = {
    "no pending": _mut(lambda s: s.update(pending_review=None)),
    "pending key missing": _mut(lambda s: s.pop("pending_review")),
    "pending is a string": _mut(lambda s: s.update(pending_review="design")),
    "pending is a list": _mut(lambda s: s.update(pending_review=[{"stage": "design"}])),
    "pending is a number": _mut(lambda s: s.update(pending_review=5)),
    "final PASSED": _mut(lambda s: s.update(final="PASSED")),
    "final TEST_FAILED": _mut(lambda s: s.update(final="TEST_FAILED")),
    "final STOPPED_BY_HUMAN": _mut(lambda s: s.update(final="STOPPED_BY_HUMAN")),
    "final STAGE_ERROR": _mut(lambda s: s.update(final="STAGE_ERROR")),
    "final BLOCKED": _mut(lambda s: s.update(final="BLOCKED")),
    "stage not in the list": _mut(lambda s: s.update(pending_review=ls.pending("ghost"))),
    "stage differs by case": _mut(lambda s: s.update(pending_review=ls.pending("Design"))),
    "pending stage not a string": _mut(lambda s: s.update(pending_review={"stage": 5, "since": SINCE})),
    "pending stage missing": _mut(lambda s: s.update(pending_review={"since": SINCE})),
    "since missing": _mut(lambda s: s.update(pending_review=ls.pending("design", ...))),
    "since None": _mut(lambda s: s.update(pending_review=ls.pending("design", None))),
    "since number": _mut(lambda s: s.update(pending_review=ls.pending("design", 20261017))),
    "since empty": _mut(lambda s: s.update(pending_review=ls.pending("design", ""))),
    "since 65 chars": _mut(lambda s: s.update(pending_review=ls.pending("design", "x" * 65))),
    "since list": _mut(lambda s: s.update(pending_review=ls.pending("design", [SINCE]))),
    "same stage is open (running)": _mut(lambda s: s.update(open=ls.opened("design", seq=2))),
    "stage is the 25th (cut by the stage limit)": _mut(
        lambda s: s.update(stages=[ls.stage_entry(f"s{i:02d}") for i in range(30)], pending_review=ls.pending("s26"))
    ),
}


@pytest.mark.parametrize("name", list(NULL_CASES))
def test_d0039_ac20_review_is_null_when_it_cannot_be_trusted(name):
    """D0039-AC-20: 確認待ちが無い・final が入った・段が一覧に無い・since が読めない・同じ段が動いている・段の数の上限で落ちた、ときは review が null（キーは残る）。"""
    state = NULL_CASES[name](pending_state("design"))
    s = snap(state)
    assert "review" in s and s["review"] is None
    assert list(s) == REVIEW_KEYS


@pytest.mark.parametrize(
    "stage",
    ["bad stage", "設計", "-design", "_design", "a" * 41, "a/b", "a.b", "a:b", "a\\b", "design!", "x\ty"],
    ids=sid,
)
def test_d0039_ac20_stage_name_that_breaks_the_form_gives_null(stage):
    """D0039-AC-20: 段の名前が FR-01 の形に合わない記録（一覧にはその名前で入っている）では、review は null（ボタンを出さない）。"""
    state = ls.base_state(stages=[ls.stage_entry("requirements"), ls.stage_entry(stage)], pending_review=ls.pending(stage))
    s = snap(state)
    assert s["review"] is None


def test_d0039_ac20_stage_that_the_snapshot_cleaning_changes_gives_null():
    """D0039-AC-20: 写しの掃除で名前が変わる段（手元のパスの形を消す hide に当たる）は、review は null（掃除した名前と元の名前が違う）。"""
    state = pending_state("design")
    assert snap(state, hide=("/work/elsewhere",))["review"] == expected("design")
    s = snap(state, hide=("design",))
    assert s["review"] is None
    assert any(x["name"] != "design" for x in s["stages"])  # 実際に名前が掃除されている


def test_d0039_ac20_a_stage_listed_twice_keeps_one_row_and_the_review():
    """D0039-AC-20: 同じ名前の段が2度並んでいても、写しの行は1つで、review は入る。"""
    state = pending_state("design", stages=[ls.stage_entry(n) for n in ("requirements", "design", "design", "red")])
    s = snap(state)
    assert [x["name"] for x in s["stages"]].count("design") == 1 and s["review"] == expected("design")


def test_d0039_ac20_stage_dropped_by_the_size_limit_gives_null(monkeypatch):
    """D0039-AC-20: 写し全体の上限（MAX_BYTES）で末尾の段が落ちたとき、その段が確認待ちなら review は null、前の段が残るなら review も残る。"""
    names = ["requirements", "design", "red", "implement", "test"]
    last = pending_state("test")
    first = pending_state("requirements")
    full_last = len(live.dumps(snap(last)).encode("utf-8"))
    full_first = len(live.dumps(snap(first)).encode("utf-8"))
    assert snap(last)["review"] == expected("test") and snap(first)["review"] == expected("requirements")
    monkeypatch.setattr(live, "MAX_BYTES", full_last - 1)
    s = snap(last)
    assert [x["name"] for x in s["stages"]] == names[:4] and s["review"] is None
    monkeypatch.setattr(live, "MAX_BYTES", full_first - 1)
    s = snap(first)
    assert [x["name"] for x in s["stages"]] == names[:4] and s["review"] == expected("requirements")
    monkeypatch.setattr(live, "MAX_BYTES", 10)
    s = snap(first)
    assert s["stages"] == [] and s["review"] is None


def test_d0039_ac20_review_stays_when_the_size_is_exactly_at_the_limit(monkeypatch):
    """D0039-AC-20: 上限ちょうどのときは何も落とさず、review も残る（境目の +0）。"""
    state = pending_state("test")
    size = len(live.dumps(snap(state)).encode("utf-8"))
    monkeypatch.setattr(live, "MAX_BYTES", size)
    s = snap(state)
    assert len(s["stages"]) == 5 and s["review"] == expected("test")


def test_d0039_ac20_empty_snapshot_has_a_null_review():
    """D0039-AC-20: 記録なしの写しにも review（null）が入る。キーの数と順は常に同じ。"""
    for value in (None, [], "x", 5, {}, {"stages": "x"}):
        s = snap(value)
        assert s["review"] is None and list(s) == REVIEW_KEYS, value
    assert list(snap(None)) == list(snap(pending_state()))


# ---- AC-21 schema 1 のまま・前のキーは変わらない ---------------------------------------------------------------------


GOLDEN_OLD = {
    "schema": 1,
    "generated_at": "2026-10-17T12:00:00+00:00",
    "empty": False,
    "name": "テスト用のセッション",
    "final": None,
    "stages": [
        {"name": "requirements", "label": "要件定義", "status": "done", "attempt": None, "started_at": None, "pending_since": None, "verdict": None, "cost_usd": 0.5, "turns": 3, "duration_sec": 12.5},
        {"name": "design", "label": "設計", "status": "review", "attempt": None, "started_at": None, "pending_since": "2026-10-17T01:02:15+00:00", "verdict": None, "cost_usd": 1.25, "turns": 7, "duration_sec": 40.0},
        {"name": "red", "label": "テスト先行", "status": "waiting", "attempt": None, "started_at": None, "pending_since": None, "verdict": None, "cost_usd": None, "turns": None, "duration_sec": None},
        {"name": "implement", "label": "実装", "status": "waiting", "attempt": None, "started_at": None, "pending_since": None, "verdict": None, "cost_usd": None, "turns": None, "duration_sec": None},
        {"name": "test", "label": "検証", "status": "waiting", "attempt": None, "started_at": None, "pending_since": None, "verdict": None, "cost_usd": None, "turns": None, "duration_sec": None},
    ],
}
GOLDEN_FINISHED = {
    "schema": 1, "generated_at": "2026-10-17T12:00:00+00:00", "empty": False, "name": "テスト用のセッション", "final": "PASSED",
    "stages": [
        {"name": "requirements", "label": "要件定義", "status": "done", "attempt": None, "started_at": None, "pending_since": None, "verdict": None, "cost_usd": 0.0, "turns": 0, "duration_sec": 0.0},
        {"name": "design", "label": "設計", "status": "waiting", "attempt": None, "started_at": None, "pending_since": None, "verdict": None, "cost_usd": None, "turns": None, "duration_sec": None},
        {"name": "red", "label": "テスト先行", "status": "waiting", "attempt": None, "started_at": None, "pending_since": None, "verdict": None, "cost_usd": None, "turns": None, "duration_sec": None},
        {"name": "implement", "label": "実装", "status": "waiting", "attempt": None, "started_at": None, "pending_since": None, "verdict": None, "cost_usd": None, "turns": None, "duration_sec": None},
        {"name": "test", "label": "検証", "status": "waiting", "attempt": None, "started_at": None, "pending_since": None, "verdict": None, "cost_usd": None, "turns": None, "duration_sec": None},
    ],
}


def golden_state() -> dict:
    runs = [ls.run("requirements", seq=1, cost=0.5, turns=3, duration=12.5), ls.review("requirements", "approved"), ls.run("design", seq=2, cost=1.25, turns=7, duration=40.0)]
    return ls.base_state(runs=runs, pending_review=ls.pending("design", SINCE))


def test_d0039_ac21_schema_is_still_1_and_old_keys_are_unchanged():
    """D0039-AC-21: SCHEMA は 1 のまま。写しの前からのキーと中身は変わらず（D0039 の前の版が出していた写しと同じ）、review だけが増える。"""
    assert live.SCHEMA == 1
    s = snap(golden_state())
    assert s["schema"] == 1 and list(s) == REVIEW_KEYS
    assert s["review"] == expected("design")
    assert {k: v for k, v in s.items() if k != "review"} == GOLDEN_OLD
    finished = ls.base_state(final="PASSED", runs=[ls.run("requirements", seq=1), ls.review("requirements", "approved")])
    f = snap(finished)
    assert f["review"] is None and {k: v for k, v in f.items() if k != "review"} == GOLDEN_FINISHED


def test_d0039_ac21_empty_snapshot_old_keys_are_unchanged():
    """D0039-AC-21: 記録なしの写しは、前のキーと値のまま（review の null が増えるだけ）。"""
    assert snap(None) == {"schema": 1, "generated_at": "2026-10-17T12:00:00+00:00", "empty": True, "name": None, "final": None, "stages": [], "review": None}


def test_d0039_ac21_same_input_gives_the_same_bytes():
    """D0039-AC-21: 同じ記録・同じ「今」で2回作ると、バイト列まで同じ。review はキーの最後に出る。"""
    a, b = golden_state(), copy.deepcopy(golden_state())
    first, second = live.dumps(snap(a)), live.dumps(snap(b))
    assert first == second
    assert first.endswith(',"review":{"stage":"design","id":"%s"}}\n' % ls.expected_review_id("design", SINCE))
    assert json.loads(first)["review"] == expected("design")
    assert live.dumps(snap(None)).endswith(',"stages":[],"review":null}\n')


def test_d0039_ac21_snapshot_does_not_change_the_record():
    """D0039-AC-21: 写しを作っても、元の記録の辞書は変わらない（純粋）。"""
    state = golden_state()
    before = copy.deepcopy(state)
    assert snap(state)["review"] == expected("design")
    assert state == before


def test_d0039_ac21_review_id_does_not_depend_on_the_clock_or_timezone_of_the_snapshot():
    """D0039-AC-21: 識別子は since の文字から作る（今の時刻・手元の時刻帯に左右されない）。"""
    state = pending_state("design", "2026-10-17T10:02:15")
    ids = {
        snap(state, local_tz=ls.JST)["review"]["id"],
        snap(state, local_tz=ls.UTC)["review"]["id"],
        live.build_snapshot(state, None, now=ls.NOW.replace(year=2030), local_tz=None)["review"]["id"],
    }
    assert ids == {ls.expected_review_id("design", "2026-10-17T10:02:15")}


# ---- AC-22 写しの識別子は照らし合わせと同じ ---------------------------------------------------------------------------


@pytest.mark.parametrize("since", [SINCE, "2026-10-17T10:00:00+00:00", "2026-10-17T10:00:00", "a", "x" * 64], ids=sid)
@pytest.mark.parametrize("stage", ["requirements", "design", "red"])
def test_d0039_ac22_snapshot_id_is_the_one_check_answer_uses(stage, since):
    """D0039-AC-22: 写しの review の識別子の答えは、同じ記録で check_answer が通す（写しと照らし合わせが同じ値）。"""
    state = pending_state(stage, since)
    review = snap(state)["review"]
    assert review == expected(stage, since)
    assert la.check_answer(state, review["stage"], review["id"]) is None
    assert la.review_id(stage, since) == review["id"]
    text = f"pipe-in: approve {review['stage']} {review['id']}"
    parsed = la.parse_answer(text)
    assert parsed.ok is True and la.check_answer(state, parsed.stage, parsed.id) is None


def test_d0039_ac22_a_changed_record_changes_both_sides_together():
    """D0039-AC-22: 記録の since が替われば、写しの識別子と check_answer の基準が一緒に替わる（古い写しの識別子の答えは断られる）。"""
    old_state, new_state = pending_state("design", SINCE), pending_state("design", "2026-10-17T11:02:15+09:00")
    old_review, new_review = snap(old_state)["review"], snap(new_state)["review"]
    assert old_review["id"] != new_review["id"]
    assert la.check_answer(new_state, old_review["stage"], old_review["id"]) == "id_mismatch"
    assert la.check_answer(new_state, new_review["stage"], new_review["id"]) is None


def test_d0039_ac22_both_call_the_same_function():
    """D0039-AC-22: live.py は識別子を live_answer.review_id で作り（自分では hashlib を使わない）、check_answer も同じ review_id を呼ぶ。"""
    source = inspect.getsource(live)
    assert "live_answer" in source and "review_id" in source
    assert "hashlib" not in source and "sha256" not in source
    assert getattr(live, "live_answer", None) is la or getattr(live, "review_id", None) is la.review_id
    check = inspect.getsource(la.check_answer)
    assert "review_id(" in check and "sha256" not in check


# ---- AC-23 写しに入れないもの -----------------------------------------------------------------------------------------


def blob(snapshot) -> str:
    return live.dumps(snapshot)


FREE_TEXT_MARKS = ["RESULT-MARK", "ERRORS-MARK", "FEEDBACK-MARK", "SUMMARY-MARK", "FAILURE-MARK", "DOC-MARK", "WARNING-MARK", "NOTE-MARK", "AGENT-MARK", "DENIAL-MARK", "METRICS-MARK", "USAGE-MARK", "CMD-MARK", "OUTPUT-MARK", "SESSION-ID-MARK", "PENDING-SESSION-MARK", "RUN-SESSION-MARK", "MEMO-BODY-MARK"]


def marked_state() -> dict:
    return ls.base_state(
        session_id="SESSION-ID-MARK",
        warnings=["WARNING-MARK"],
        usage_summary={"models": ["USAGE-MARK"]},
        pending_review=ls.pending("design", SINCE) | {"doc": "DOC-MARK", "session_id": "PENDING-SESSION-MARK"},
        stages=[ls.stage_entry(n) | {"output": "OUTPUT-MARK"} for n in ls.STAGES],
        runs=[
            ls.run("requirements", seq=1, result="RESULT-MARK", errors=["ERRORS-MARK"], note="NOTE-MARK", agent="AGENT-MARK", session_id="RUN-SESSION-MARK",
                   denials=["DENIAL-MARK"], metrics={"x": "METRICS-MARK"}),
            ls.review("requirements", "revise", "FEEDBACK-MARK"),
            ls.verdict("fail", 1, summary="SUMMARY-MARK", failures=[{"criterion": "AC-01", "detail": "FAILURE-MARK"}], commands=["CMD-MARK"]),
        ],
        input="MEMO-BODY-MARK",
        memo="MEMO-BODY-MARK",
    )


@pytest.mark.parametrize("mark", FREE_TEXT_MARKS)
def test_d0039_ac23_free_text_marks_stay_out_with_a_review(mark):
    """D0039-AC-23: 自由な文・session_id・パス・要件メモの目印は、review のある記録（確認待ちがある）でも写しに出ない（D0027-AC-10〜14 と同じ目印）。"""
    s = snap(marked_state())
    assert s["review"] == expected("design"), "review のある記録で確かめる"
    assert mark not in blob(s)


def test_d0039_ac23_since_text_is_not_in_review():
    """D0039-AC-23: since の文字そのもの（時刻）は review に出ない。review は段と識別子の2つだけ。"""
    s = snap(pending_state("design", SINCE))
    review = s["review"]
    assert set(review) == {"stage", "id"} and list(review) == ["stage", "id"]
    assert SINCE not in blob(s) and "10:02:15" not in json.dumps(review)
    assert SINCE not in json.dumps(review) and "+09:00" not in blob(s)
    assert "docs/pipeline" not in blob(s) and "02_design" not in blob(s)


@pytest.mark.parametrize("since", ["2026-10-17T10:02:15+09:00", "SINCE-FREE-TEXT-MARK", "2099-12-31T23:59:59+09:00"], ids=sid)
def test_d0039_ac23_any_since_text_stays_out_of_the_snapshot_except_as_the_id(since):
    """D0039-AC-23: since がどんな文字でも、その文字は写しに出ない（識別子の元になるだけ）。"""
    s = snap(pending_state("design", since))
    assert s["review"] == expected("design", since)
    assert since not in blob(s)


def test_d0039_ac23_work_dir_path_is_not_in_the_snapshot(tmp_path):
    """D0039-AC-23: 読み先のパスは review のある写しにも出ない（hide に渡した形が消える）。"""
    work = ls.pending_project(tmp_path, "design")
    state = live.read_state(work)
    s = snap(state, hide=(str(work), str(tmp_path)))
    assert s["review"] is not None
    assert str(tmp_path) not in blob(s)


# ---- AC-24 大きさ・見張り -------------------------------------------------------------------------------------------


def test_d0039_ac24_snapshot_with_review_stays_under_32_kib():
    """D0039-AC-24: review を足しても、写し全体の上限（32 KiB）は守られる。24 の段・長い名前・review つきの最大の形でも収まる。"""
    assert live.MAX_BYTES == 32768
    names = [f"stage-{i:02d}-" + "x" * 30 for i in range(30)]
    state = ls.base_state(
        name="名" * 60,
        stages=[ls.stage_entry(n, "ラ" * 40) for n in names],
        pending_review=ls.pending(names[20], SINCE),
        runs=[ls.run(n, seq=i + 1, cost=123456.789, turns=999999, duration=99999.9) for i, n in enumerate(names[:20])],
    )
    s = snap(state)
    assert len(live.dumps(s).encode("utf-8")) <= 32768
    assert s["review"] == expected(names[20])
    assert len(s["stages"]) == 24


def test_d0039_ac24_watch_sees_a_changed_id_as_a_change():
    """D0039-AC-24: 見張りは、識別子が替わった写しを「変わった」と見る（review の違いだけで snapshot_key が替わり、decide が出すと答える）。"""
    # 同じ時刻の別の書き方：写しの pending_since は同じで、識別子（の元の文字）だけ違う
    a = snap(pending_state("design", "2026-10-17T10:02:15+09:00"))
    b = snap(pending_state("design", "2026-10-17T01:02:15+00:00"))
    assert a["stages"] == b["stages"] and a["review"]["id"] != b["review"]["id"]
    ka, kb = live_watch.snapshot_key(a), live_watch.snapshot_key(b)
    assert ka != kb
    assert live_watch.decide(ka, kb, readable=True, misses=0) == (True, 0)
    assert live_watch.decide(ka, ka, readable=True, misses=0) == (False, 0)


def test_d0039_ac24_generated_at_alone_is_still_not_a_change():
    """D0039-AC-24: generated_at だけの違いは、review があっても変わった扱いにしない（今までどおり）。"""
    state = pending_state("design")
    a = live.build_snapshot(state, None, now=ls.NOW, local_tz=ls.JST)
    b = live.build_snapshot(state, None, now=ls.NOW.replace(hour=13), local_tz=ls.JST)
    assert a["generated_at"] != b["generated_at"] and a["review"] == b["review"] == expected("design")
    assert live_watch.snapshot_key(a) == live_watch.snapshot_key(b)


def test_d0039_ac24_review_going_away_is_a_change():
    """D0039-AC-24: 確認待ちが終わって review が null になった写しは、変わった扱い。"""
    a = snap(pending_state("design"))
    b = snap(ls.base_state(runs=[ls.review("design")]))
    assert b["review"] is None
    assert live_watch.snapshot_key(a) != live_watch.snapshot_key(b)


def test_d0039_ac24_watch_line_keys_are_unchanged():
    """D0039-AC-24: 見張りの1行の形（キー4つ：event・seq・final・empty）は変わらない。今のままで通る（守り続ける検査）。"""
    line = live_watch.format_line("snapshot", 3, None, False)
    assert list(json.loads(line)) == ["event", "seq", "final", "empty"]
    assert line == '{"event":"snapshot","seq":3,"final":null,"empty":false}\n'
    assert list(json.loads(live_watch.format_line("snapshot", 4, "PASSED", True))) == ["event", "seq", "final", "empty"]


# ---- AC-48 古い記録 --------------------------------------------------------------------------------------------------


def test_d0039_ac48_old_records_have_a_null_review_and_are_refused_by_answer(tmp_path):
    """D0039-AC-48: since の無い古い記録・archive/<日時>/ の記録は、review が null で、照らし合わせは no_id か finished で断る（落ちない）。"""
    for name in ("pipe_dev", "pipe_in"):
        state = json.loads((ROOT / "tests" / "fixtures" / name / "waiting" / "state.json").read_text(encoding="utf-8"))
        assert isinstance(state["pending_review"], dict) and "since" not in state["pending_review"]
        s = snap(state)
        assert s["review"] is None and s["stages"], name
        assert la.check_answer(state, "red", ls.expected_review_id("red", "2026-10-17T10:00:00+09:00")) == "no_id"
    work = ls.pending_project(tmp_path, "requirements")
    state = json.loads((work / "state.json").read_text(encoding="utf-8"))
    del state["pending_review"]["since"]
    archive = work / "archive" / "20261017-100000"
    ls.write_state(archive, state)
    old = live.read_state(archive)
    assert snap(old)["review"] is None
    assert la.check_answer(old, "requirements", "a1b2c3d4e5") == "no_id"
    state["final"] = "STOPPED_BY_HUMAN"
    ls.write_state(archive, state)
    assert snap(live.read_state(archive))["review"] is None
    assert la.check_answer(live.read_state(archive), "requirements", "a1b2c3d4e5") == "finished"


def test_d0039_ac48_a_new_record_with_since_gets_a_review():
    """D0039-AC-48: since のある見本（showcase_waiting）は review が入る（古い見本との差）。"""
    state = json.loads((ROOT / "tests" / "fixtures" / "showcase_waiting" / "state.json").read_text(encoding="utf-8"))
    s = snap(state)
    assert s["review"] == {"stage": "requirements", "id": ls.expected_review_id("requirements", state["pending_review"]["since"])}


@pytest.mark.parametrize("name", ["showcase", "showcase_running", "showcase_running_next", "pipe_dev/finished", "pipe_dev/running", "pipe_in/finished", "pipe_in/running"])
def test_d0039_ac48_records_without_a_pending_review_have_a_null_review(name):
    """D0039-AC-48: 確認待ちの無い見本の記録（終わった・動いている）は review が null。"""
    state = json.loads((ROOT / "tests" / "fixtures" / name / "state.json").read_text(encoding="utf-8"))
    s = snap(state)
    assert s["review"] is None and list(s) == REVIEW_KEYS


# ---- AC-49 変えるのは review だけ -------------------------------------------------------------------------------------


def test_d0039_ac49_only_review_is_added_to_the_snapshot():
    """D0039-AC-49: 写しのうち変わるのは review だけ（前の版の出力そのままの見本に、review を足した形になる）。"""
    s = snap(golden_state())
    assert s["review"] == expected("design")
    old = {k: v for k, v in s.items() if k != "review"}
    assert old == GOLDEN_OLD
    assert list(old) == REVIEW_KEYS[:-1]
    assert [list(x) for x in old["stages"]] == [ls.STAGE_KEYS] * 5


@pytest.mark.parametrize("name", ["showcase", "showcase_waiting", "showcase_running", "pipe_dev/waiting", "pipe_dev/finished"])
def test_d0039_ac49_fixture_snapshots_only_gain_the_review_key(name):
    """D0039-AC-49: 見本の記録の写しは、review を除けば、review を持たない記録（確認待ちを外したもの）の写しと同じ形（段の行にも余計なキーが増えない）。"""
    state = json.loads((ROOT / "tests" / "fixtures" / name / "state.json").read_text(encoding="utf-8"))
    s = snap(state)
    assert list(s) == REVIEW_KEYS
    assert all(list(x) == ls.STAGE_KEYS for x in s["stages"])
    without = copy.deepcopy(state)
    without["pending_review"] = None
    t = snap(without)
    assert {k: v for k, v in s.items() if k not in ("review", "stages")} == {k: v for k, v in t.items() if k not in ("review", "stages")}
