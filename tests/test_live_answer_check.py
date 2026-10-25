"""D0039：確認待ちの識別子（review_id）と、読み取り結果を記録と照らし合わせる関数（check_answer）。

check_answer は純粋（ファイルに触れない）。通るのは「記録が読めて・final が無く・pending_review が辞書で・段が同じで・識別子が同じ」ときだけ。
二重の答え・古い識別子・中止と承認の取り違えは、本物の Recorder で記録を作って確かめる（tmp_path の中だけ）。
識別子の基準は tests/live_support.py の expected_review_id（設計 4 節の式）。本体の review_id と check_answer の両方がそれに合う。
"""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timedelta

import pytest

import live_support as ls
from pipe_in.engine import live, live_answer as la

SINCE = "2026-10-17T10:00:00+09:00"
T0 = datetime(2026, 10, 17, 10, 0, 0)
HEX10 = re.compile(r"[0-9a-f]{10}")


def sid(value) -> str:
    return ascii(value)[:48]


def rid(stage: str = "design", since: str = SINCE) -> str:
    return ls.expected_review_id(stage, since)


def state_for(stage: str = "design", since=SINCE, **over) -> dict:
    return ls.base_state(pending_review=ls.pending(stage, since), **over)


def check(state, stage="design", answer_id=None):
    return la.check_answer(state, stage, rid(stage) if answer_id is None else answer_id)


# ---- AC-14 通る -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("stage", ["requirements", "design", "red", "implement", "test"])
def test_d0039_ac14_matching_answer_passes(stage):
    """D0039-AC-14: 記録が読めて・final が無く・pending_review が入っていて・段と識別子が確認待ちと同じなら通る（None）。違う識別子は同じ記録で断られる。"""
    state = state_for(stage)
    answer_id = la.review_id(stage, SINCE)
    assert answer_id == rid(stage)
    assert la.check_answer(state, stage, answer_id) is None
    assert la.check_answer(state, stage, "0" * 10) == "id_mismatch"


@pytest.mark.parametrize("since", [SINCE, "2026-10-17T10:00:00+00:00", "2026-10-17T10:00:00", "2026-10-17T10:00:00.123456+09:00", "x", "日本語の時刻", "a" * 64, "z", " 2026 "], ids=sid)
def test_d0039_ac14_any_usable_since_text_passes(since):
    """D0039-AC-14: since は文字のまま使う（時刻の形でなくても、1〜64文字の文字列なら識別子ができて通る）。"""
    state = state_for("design", since)
    answer_id = la.review_id("design", since)
    assert answer_id == rid("design", since)
    assert la.check_answer(state, "design", answer_id) is None


@pytest.mark.parametrize("stage,extra", [("design", {}), ("design", {"warnings": ["w"], "usage_summary": {"x": 1}}), ("design", {"open": None, "runs": [ls.run("requirements", seq=1)]}), ("design", {"total_cost_usd": 12.5, "session_id": "S-1"})])
def test_d0039_ac14_other_keys_of_the_record_do_not_matter(stage, extra):
    """D0039-AC-14: 照らし合わせるのは final・pending_review だけ（ほかのキーが何でも、通るものは通る）。"""
    state = state_for(stage, **extra)
    assert la.review_id(stage, SINCE) == rid(stage)
    assert la.check_answer(state, stage, rid(stage)) is None
    assert la.check_answer(state, stage, "0" * 10) == "id_mismatch"


def test_d0039_ac14_every_field_survives_a_pass():
    """D0039-AC-14: 読み取りと照らし合わせを続けて通ったとき、（動作・段・識別子・直してほしい点）がそのまま残る。"""
    state = state_for("design")
    for text, action, feedback in [
        (f"pipe-in: approve design {rid()}", "approved", None),
        (f"pipe-in: quit design {rid()}", "quit", None),
        (f"pipe-in: revise design {rid()}\n日本語の直してほしい点\n二行目 `x` $(y)", "revise", "日本語の直してほしい点\n二行目 `x` $(y)"),
    ]:
        r = la.parse_answer(text)
        assert r == la.ParseResult(True, action, "design", rid(), feedback, None)
        assert la.check_answer(state, r.stage, r.id) is None
        assert (r.action, r.stage, r.id, r.feedback) == (action, "design", rid(), feedback)


# ---- AC-15 断る -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("pending", [None, "missing", "design", "", 0, 5, 1.5, True, False, [], ["design"], [{"stage": "design"}], ("design",)], ids=sid)
def test_d0039_ac15_no_pending_review_is_not_pending(pending):
    """D0039-AC-15: pending_review が null・無い・辞書でない（文字・数・リスト・真偽）なら not_pending。"""
    state = ls.base_state()
    if pending == "missing":
        del state["pending_review"]
    else:
        state["pending_review"] = pending
    assert la.check_answer(state, "design", rid()) == "not_pending"


@pytest.mark.parametrize(
    "answer_stage",
    ["requirements", "Design", "DESIGN", "desig", "designs", "design ", " design", "design\n", "", "red", "日本語", "design​", "d" * 40],
    ids=sid,
)
def test_d0039_ac15_another_stage_is_stage_mismatch(answer_stage):
    """D0039-AC-15: 確認待ちの段と違う段（大文字小文字・前後の空白・前方一致・空も）は stage_mismatch。"""
    state = state_for("design")
    assert la.check_answer(state, answer_stage, rid("design")) == "stage_mismatch"
    assert la.check_answer(state, answer_stage, rid(answer_stage) if answer_stage else "a1b2c3d4e5") == "stage_mismatch"


@pytest.mark.parametrize("answer_stage", [None, 5, 1.5, True, ["design"], ("design",), {"design": 1}, b"design", object()], ids=lambda v: type(v).__name__)
def test_d0039_ac15_stage_of_another_type_is_stage_mismatch(answer_stage):
    """D0039-AC-15: 段が文字列でない（型が違う）ときも、例外を出さず stage_mismatch。"""
    assert la.check_answer(state_for("design"), answer_stage, rid()) == "stage_mismatch"


@pytest.mark.parametrize("pending_stage", [None, 5, ["design"], {"stage": "design"}, True, b"design"], ids=lambda v: type(v).__name__)
def test_d0039_ac15_pending_stage_of_another_type_is_stage_mismatch(pending_stage):
    """D0039-AC-15: 記録の確認待ちの段が文字列でない壊れた記録でも、例外を出さず stage_mismatch。"""
    state = ls.base_state(pending_review={"stage": pending_stage, "doc": "x", "session_id": None, "since": SINCE})
    assert la.check_answer(state, "design", rid()) == "stage_mismatch"


@pytest.mark.parametrize("pending", [{}, {"since": SINCE}, {"doc": "x", "session_id": None}])
def test_d0039_ac15_pending_without_a_stage_is_stage_mismatch(pending):
    """D0039-AC-15: 確認待ちの辞書に段が無い壊れた記録は、KeyError にせず stage_mismatch。"""
    assert la.check_answer(ls.base_state(pending_review=pending), "design", rid()) == "stage_mismatch"


@pytest.mark.parametrize(
    "answer_id",
    ["0" * 10, "a1b2c3d4e5", rid().upper(), rid()[:9], rid() + "0", " " + rid(), rid() + "\n", "", "x", None, 5, 1.5, True, [rid()], (rid(),), {"id": rid()}, b"abcdef0123", rid("requirements")],
    ids=sid,
)
def test_d0039_ac15_another_or_malformed_id_is_id_mismatch(answer_id):
    """D0039-AC-15: 古い・別の識別子（大文字・桁違い・空白つき・型違いも）は id_mismatch。"""
    if answer_id == rid():  # 偶然一致した場合の保険（この値の組では起きない）
        pytest.skip("偶然一致")
    assert la.check_answer(state_for("design"), "design", answer_id) == "id_mismatch"


@pytest.mark.parametrize("final", ["PASSED", "TEST_FAILED", "STOPPED_BY_HUMAN", "STAGE_ERROR", "BLOCKED", "WHATEVER", "", 0, False, [], {}, 5], ids=sid)
def test_d0039_ac15_finished_records_are_refused_even_with_pending_review_left(final):
    """D0039-AC-15: final が入っている（None 以外）記録は、pending_review が残っていても finished（正しい終わりの名前かは見ない。安全側）。"""
    state = state_for("design", final=final)
    assert la.check_answer(state, "design", rid()) == "finished"


@pytest.mark.parametrize("pending", [None, {}, "x", 5])
def test_d0039_ac15_finished_comes_before_not_pending(pending):
    """D0039-AC-15: 規則の順：finished は not_pending より先（終わった記録で確認待ちが無くても finished）。"""
    state = ls.base_state(final="PASSED", pending_review=pending)
    assert la.check_answer(state, "design", rid()) == "finished"


@pytest.mark.parametrize("state", [None, [], "state", 5, 1.5, True, (), ["pending_review"], object()], ids=lambda v: type(v).__name__)
def test_d0039_ac15_non_dict_state_is_no_record(state):
    """D0039-AC-15: 記録が辞書でない（読めなかった None・リスト・文字・数）なら no_record。例外を出さない。"""
    assert la.check_answer(state, "design", rid()) == "no_record"


@pytest.mark.parametrize(
    "content",
    [b"", b"   \n", b"not json", b"{", b'{"a":', b"[]", b"5", b"null", b'"text"', b"true", b"\xff\xfe\x00{", b"\xef\xbb\xbf{}", b"[" * 100000, b'{"a":' * 50000],
    ids=lambda b: repr(b[:14]),
)
def test_d0039_ac15_unreadable_state_files_are_no_record(tmp_path, content):
    """D0039-AC-15: state.json が空・壊れている・最上位が辞書でない・文字化け・入れ子が深すぎるときは、read_state を通して落ちずに no_record。"""
    work = tmp_path / "w"
    work.mkdir()
    (work / "state.json").write_bytes(content)
    assert la.check_answer(live.read_state(work), "design", rid()) == "no_record"


def test_d0039_ac15_missing_directory_or_file_is_no_record(tmp_path):
    """D0039-AC-15: 記録が無い（フォルダも state.json も無い）ときは no_record。"""
    assert la.check_answer(live.read_state(tmp_path / "nope"), "design", rid()) == "no_record"
    (tmp_path / "w").mkdir()
    assert la.check_answer(live.read_state(tmp_path / "w"), "design", rid()) == "no_record"


def test_d0039_ac15_state_json_as_a_directory_is_no_record(tmp_path):
    """D0039-AC-15: state.json がフォルダでも no_record。"""
    work = tmp_path / "w"
    (work / "state.json").mkdir(parents=True)
    assert la.check_answer(live.read_state(work), "design", rid()) == "no_record"


def test_d0039_ac15_too_large_state_is_no_record(tmp_path):
    """D0039-AC-15: 大きすぎる state.json（4 MiB 超）は読まずに no_record。"""
    work = tmp_path / "w"
    work.mkdir()
    big = json.dumps({**state_for("design"), "pad": "x" * (live.MAX_STATE_BYTES + 10)})
    (work / "state.json").write_text(big, encoding="utf-8")
    assert la.check_answer(live.read_state(work), "design", rid()) == "no_record"


@pytest.mark.parametrize("since", [..., None, "", 5, 1.5, True, [], ["a"], {"a": 1}, "x" * 65, "x" * 200, "\ud800", "a\udfffb", b"2026"], ids=sid)
def test_d0039_ac15_missing_or_broken_since_is_no_id(since):
    """D0039-AC-15: since が無い・文字列でない・空・65文字以上・孤立サロゲートの古い・壊れた記録は no_id（識別子を作れない）。"""
    state = ls.base_state(pending_review=ls.pending("design", since))
    assert la.check_answer(state, "design", rid()) == "no_id"
    assert la.check_answer(state, "design", "0" * 10) == "no_id"  # どの識別子でも同じ（作れない記録には何も合わない）


@pytest.mark.parametrize("stage", ["bad stage", "日本語", "-x", "a" * 41, "a/b", "", "x\n"], ids=sid)
def test_d0039_ac15_pending_stage_that_breaks_the_form_is_no_id(stage):
    """D0039-AC-15: 確認待ちの段の名前が形に合わない記録は、同じ名前で答えても no_id（識別子を作れない）。"""
    state = ls.base_state(pending_review=ls.pending(stage, SINCE))
    assert la.check_answer(state, stage, "a1b2c3d4e5") == "no_id"


def test_d0039_ac15_since_text_boundaries():
    """D0039-AC-15: since の長さの境目：1文字・64文字は識別子ができて通り、0文字・65文字は no_id。"""
    for since, expected in [("a", None), ("a" * 64, None), ("", "no_id"), ("a" * 65, "no_id")]:
        assert la.check_answer(state_for("design", since), "design", rid("design", since)) == expected, len(since)


def test_d0039_ac15_check_refusals_have_reasons():
    """D0039-AC-15: 断る理由が決まった一覧のどれかになる（6つの理由がすべて出る）。"""
    seen = {
        la.check_answer(None, "design", rid()),
        la.check_answer(state_for("design", final="PASSED"), "design", rid()),
        la.check_answer(ls.base_state(), "design", rid()),
        la.check_answer(state_for("design"), "red", rid()),
        la.check_answer(state_for("design"), "design", "0" * 10),
        la.check_answer(state_for("design", since=...), "design", rid()),
    }
    assert seen == set(la.CHECK_REASONS)


def test_d0039_ac15_rules_are_evaluated_in_the_designed_order():
    """D0039-AC-15: 規則の順：no_record → finished → not_pending → stage_mismatch → no_id → id_mismatch。"""
    broken = ls.base_state(final="PASSED", pending_review=ls.pending("other", ...))
    assert la.check_answer(broken, "design", "zz") == "finished"
    no_pending = ls.base_state(pending_review=None)
    assert la.check_answer(no_pending, "design", "zz") == "not_pending"
    wrong_stage_no_since = ls.base_state(pending_review=ls.pending("other", ...))
    assert la.check_answer(wrong_stage_no_since, "design", "zz") == "stage_mismatch"
    right_stage_no_since = ls.base_state(pending_review=ls.pending("design", ...))
    assert la.check_answer(right_stage_no_since, "design", "zz") == "no_id"
    right_stage_wrong_id = state_for("design")
    assert la.check_answer(right_stage_wrong_id, "design", "zz") == "id_mismatch"
    assert la.check_answer(None, "design", "zz") == "no_record"


def test_d0039_ac15_check_is_pure():
    """D0039-AC-15: check_answer は記録を書き換えず、何度呼んでも同じ（純粋）。"""
    state = state_for("design", runs=[ls.run("requirements", seq=1)])
    before = copy.deepcopy(state)
    results = [la.check_answer(state, "design", rid()) for _ in range(3)] + [la.check_answer(state, "red", rid()) for _ in range(3)]
    assert state == before
    assert results == [None, None, None, "stage_mismatch", "stage_mismatch", "stage_mismatch"]


# ---- AC-03 段は大文字と小文字を区別する -------------------------------------------------------------------------


def test_d0039_ac03_stage_comparison_is_case_sensitive():
    """D0039-AC-03: 照らし合わせは段の大文字小文字を区別する（読み取りは段をそのまま保ち、記録の Design と答えの design は合わない）。"""
    state = state_for("Design")
    assert la.parse_answer(f"pipe-in: approve Design {rid('Design')}").stage == "Design"
    assert la.check_answer(state, "Design", rid("Design")) is None
    assert la.check_answer(state, "design", rid("Design")) == "stage_mismatch"
    assert la.check_answer(state, "design", rid("design")) == "stage_mismatch"
    assert la.check_answer(state_for("design"), "Design", rid("Design")) == "stage_mismatch"
    assert rid("Design") != rid("design")


# ---- AC-16 二重の答え ------------------------------------------------------------------------------------------


def _text(action: str, stage: str, ident: str) -> str:
    return f"pipe-in: {action} {stage} {ident}" + ("\n直して" if action == "revise" else "")


def _answer(work, action: str, stage: str = "requirements"):
    """work の今の確認待ちに宛てた答えを読み取り、(読み取り結果, 照らし合わせの結果) を返す。"""
    since = ls.pending_of(work)["since"] if isinstance(live.read_state(work).get("pending_review"), dict) else "2026-10-17T00:00:00+00:00"
    parsed = la.parse_answer(_text(action, stage, ls.expected_review_id(stage, since)))
    assert parsed.ok is True, parsed
    return parsed, la.check_answer(live.read_state(work), parsed.stage, parsed.id)


def test_d0039_ac16_the_same_approve_twice_is_not_pending(tmp_path):
    """D0039-AC-16: approve が通って record review で pending_review が消えたあと、同じ文をもう一度読むと not_pending。"""
    work = ls.pending_project(tmp_path, "requirements")
    parsed, first = _answer(work, "approve")
    assert first is None and parsed.action == "approved"
    ls.recorder(tmp_path, T0).review("requirements", parsed.action)
    assert live.read_state(work)["pending_review"] is None
    assert la.check_answer(live.read_state(work), parsed.stage, parsed.id) == "not_pending"
    assert la.check_answer(live.read_state(work), parsed.stage, parsed.id) == "not_pending"


def test_d0039_ac16_approve_after_quit_is_not_pending(tmp_path):
    """D0039-AC-16: quit が通ったあとの approve は not_pending（中止のあとに承認が通らない）。finish のあとは finished。"""
    work = ls.pending_project(tmp_path, "requirements")
    quit_, first = _answer(work, "quit")
    approve, also = _answer(work, "approve")
    assert first is None and also is None  # 同じ確認待ちには、どちらの答えも（まだ）通る
    ls.recorder(tmp_path, T0).review("requirements", quit_.action)
    assert la.check_answer(live.read_state(work), approve.stage, approve.id) == "not_pending"
    ls.recorder(tmp_path, T0).finish("STOPPED_BY_HUMAN")
    assert la.check_answer(live.read_state(work), approve.stage, approve.id) == "finished"
    assert la.check_answer(live.read_state(work), quit_.stage, quit_.id) == "finished"


def test_d0039_ac16_quit_after_approve_is_not_pending(tmp_path):
    """D0039-AC-16: approve が通ったあとの quit は not_pending（承認のあとに中止が通らない）。"""
    work = ls.pending_project(tmp_path, "requirements")
    approve, _ = _answer(work, "approve")
    quit_, _ = _answer(work, "quit")
    ls.recorder(tmp_path, T0).review("requirements", approve.action)
    assert la.check_answer(live.read_state(work), quit_.stage, quit_.id) == "not_pending"
    assert la.check_answer(live.read_state(work), approve.stage, approve.id) == "not_pending"


def test_d0039_ac16_revise_then_the_same_text_is_not_pending(tmp_path):
    """D0039-AC-16: revise が通って差し戻しが記録されたあと（まだ次の確認待ちが無いうち）、同じ文は not_pending。"""
    work = ls.pending_project(tmp_path, "requirements")
    revise, first = _answer(work, "revise")
    assert first is None and revise.feedback == "直して"
    ls.recorder(tmp_path, T0).review("requirements", revise.action, feedback=revise.feedback)
    assert la.check_answer(live.read_state(work), revise.stage, revise.id) == "not_pending"


def test_d0039_ac16_an_answer_for_the_next_stage_does_not_work_before_it_is_pending(tmp_path):
    """D0039-AC-16: 承認で次の段が始まっても、次の段が確認待ちになるまでは、その段への答えは not_pending。"""
    work = ls.pending_project(tmp_path, "requirements")
    ls.recorder(tmp_path, T0).review("requirements", "approved")
    ls.recorder(tmp_path, T0).begin("design")
    ident = ls.expected_review_id("design", "2026-10-17T10:00:00+00:00")
    assert la.check_answer(live.read_state(work), "design", ident) == "not_pending"


# ---- AC-17 古い識別子 -----------------------------------------------------------------------------------------


def test_d0039_ac17_old_id_is_refused_after_a_revise(tmp_path):
    """D0039-AC-17: 差し戻して同じ段がまた確認待ちになる（since が替わる）と、前の識別子の答えは id_mismatch、新しい識別子は通る。"""
    work = ls.pending_project(tmp_path, "requirements")
    old_since = ls.pending_of(work)["since"]
    old_id = ls.expected_review_id("requirements", old_since)
    later = ls.recorder(tmp_path, T0 + timedelta(hours=1))
    later.review("requirements", "revise", feedback="直して")
    later.begin("requirements", note="指摘を反映")
    later.done("requirements", summary="直した")
    later.wait("requirements")
    new_since = ls.pending_of(work)["since"]
    assert new_since != old_since
    new_id = ls.expected_review_id("requirements", new_since)
    state = live.read_state(work)
    assert la.check_answer(state, "requirements", old_id) == "id_mismatch"
    assert la.check_answer(state, "requirements", new_id) is None
    assert la.review_id("requirements", new_since) == new_id and la.review_id("requirements", old_since) == old_id


def test_d0039_ac17_one_second_later_is_a_new_id(tmp_path):
    """D0039-AC-17: 差し戻しのあとの確認待ちが1秒後でも、前の識別子は通らない。"""
    work = ls.pending_project(tmp_path, "requirements")
    old_id = ls.expected_review_id("requirements", ls.pending_of(work)["since"])
    later = ls.recorder(tmp_path, T0 + timedelta(seconds=1))
    later.review("requirements", "revise", feedback="直して")
    later.begin("requirements")
    later.done("requirements")
    later.wait("requirements")
    state = live.read_state(work)
    assert la.check_answer(state, "requirements", old_id) == "id_mismatch"
    assert la.check_answer(state, "requirements", ls.expected_review_id("requirements", ls.pending_of(work)["since"])) is None


def test_d0039_ac17_the_old_id_stays_refused_through_several_rounds(tmp_path):
    """D0039-AC-17: 差し戻しを何度も繰り返しても、前のどの識別子も通らず、今の識別子だけが通る。"""
    work = ls.pending_project(tmp_path, "requirements")
    ids = [ls.expected_review_id("requirements", ls.pending_of(work)["since"])]
    for n in range(1, 4):
        r = ls.recorder(tmp_path, T0 + timedelta(minutes=n))
        r.review("requirements", "revise", feedback=f"直して {n}")
        r.begin("requirements", note="指摘を反映")
        r.done("requirements")
        r.wait("requirements")
        ids.append(ls.expected_review_id("requirements", ls.pending_of(work)["since"]))
    assert len(set(ids)) == 4
    state = live.read_state(work)
    assert [la.check_answer(state, "requirements", i) for i in ids] == ["id_mismatch"] * 3 + [None]


def test_d0039_ac17_same_since_other_stage_is_refused():
    """D0039-AC-17: since が同じで段だけ替わった確認待ちでは、前の段への答えは stage_mismatch（識別子だけ前の段のものなら id_mismatch）。"""
    state = state_for("design", SINCE)
    assert la.check_answer(state, "requirements", rid("requirements", SINCE)) == "stage_mismatch"
    assert la.check_answer(state, "design", rid("requirements", SINCE)) == "id_mismatch"
    assert la.check_answer(state, "design", rid("design", SINCE)) is None


# ---- AC-18 識別子 ---------------------------------------------------------------------------------------------


def test_d0039_ac18_id_is_stable_and_changes_with_stage_or_since():
    """D0039-AC-18: 識別子は、段と since が同じなら同じ値、どちらかが違えば（since の1秒の違いでも）別の値。"""
    a = la.review_id("design", SINCE)
    assert HEX10.fullmatch(a)
    assert a == la.review_id("design", SINCE) == la.review_id("design", str(SINCE))
    assert la.review_id("red", SINCE) != a
    assert la.review_id("Design", SINCE) != a
    assert la.review_id("design", "2026-10-17T10:00:01+09:00") != a
    assert la.review_id("design", "2026-10-17T10:00:00+09:01") != a
    assert la.review_id("design", SINCE + " ") != a
    assert la.review_id("design", "2026-10-17T01:00:00+00:00") != a  # 同じ時刻でも文字が違えば別（時刻に直さない）
    assert la.review_id("design", "2026-10-17T10:00:00+0900") != a


def test_d0039_ac18_ids_do_not_collide_over_many_inputs():
    """D0039-AC-18: 段 × 1分間の秒（0〜59）× 時刻帯 の 5×60×2 通りが、すべて別の値になる。"""
    ids = {}
    for stage in ("requirements", "design", "red", "implement", "test"):
        for sec in range(60):
            for tz in ("+09:00", "+00:00"):
                since = f"2026-10-17T10:00:{sec:02d}{tz}"
                ids[(stage, since)] = la.review_id(stage, since)
    assert len(ids) == 600 and len(set(ids.values())) == 600
    assert all(HEX10.fullmatch(v) for v in ids.values())


@pytest.mark.parametrize("since", [..., None, "", 5, 1.5, True, False, [], ["a"], {"a": 1}, b"abc", "x" * 65, "x" * 1000, "\ud800", "a\udfffb"], ids=sid)
def test_d0039_ac18_id_is_none_without_a_usable_since(since):
    """D0039-AC-18: since が無い・文字列でない・空・65文字以上・孤立サロゲートのときは None（例外を出さない）。"""
    assert la.review_id("design", "ok-since") is not None  # 作れる場合の基準
    assert la.review_id("design", None if since is ... else since) is None


@pytest.mark.parametrize("stage", [None, 5, "", "-a", "_a", "a" * 41, "a b", "日本語", "x\n", b"design", ["design"], True], ids=sid)
def test_d0039_ac18_id_is_none_without_a_usable_stage(stage):
    """D0039-AC-18: 段の名前が形に合わない・文字列でないときも None。"""
    assert la.review_id("design", SINCE) is not None
    assert la.review_id(stage, SINCE) is None


def test_d0039_ac18_since_length_boundaries():
    """D0039-AC-18: since の長さの境目：1文字・64文字は作れ、0文字・65文字は None。段は1文字・40文字は作れ、41文字は None。"""
    assert HEX10.fullmatch(la.review_id("design", "a"))
    assert HEX10.fullmatch(la.review_id("design", "a" * 64))
    assert la.review_id("design", "") is None
    assert la.review_id("design", "a" * 65) is None
    assert HEX10.fullmatch(la.review_id("a", SINCE)) and HEX10.fullmatch(la.review_id("a" * 40, SINCE))
    assert la.review_id("a" * 41, SINCE) is None


@pytest.mark.parametrize("since", [SINCE, "2026-10-17T10:00:00+00:00", "日本語", "x"], ids=sid)
@pytest.mark.parametrize("stage", ["design", "requirements", "a", "make-diagram_2"])
def test_d0039_ac18_id_is_ten_hex_and_hides_its_inputs(stage, since):
    """D0039-AC-18: 識別子は10文字の16進で、設計 4 節の式（前置き pipe-in:review を付けた SHA-256 の先頭10文字）に合う。段の名前・時刻の文字は読み取れない。"""
    value = la.review_id(stage, since)
    assert value == rid(stage, since) and HEX10.fullmatch(value)
    import hashlib

    assert value != hashlib.sha256((stage + "\n" + since).encode("utf-8")).hexdigest()[:10]  # 前置きなしの式ではない
    assert value != hashlib.sha256(since.encode("utf-8")).hexdigest()[:10]
    assert stage not in value or len(stage) < 3
    assert re.sub(r"[0-9a-f]", "", value) == ""


# ---- AC-19 パイプの記録・古い記録 -----------------------------------------------------------------------------------


def _pipe_state(pending_stage: str, since=SINCE, stages=("collect", "draw", "make-diagram_2")) -> dict:
    return ls.base_state(pipe="diagram", name="図のパイプ", stages=[ls.stage_entry(n, n) for n in stages], pending_review=ls.pending(pending_stage, since))


@pytest.mark.parametrize("stage", ["collect", "draw", "make-diagram_2"])
def test_d0039_ac19_pipe_record_pending_review_passes_and_refuses_like_the_dev_flow(tmp_path, stage):
    """D0039-AC-19: パイプの記録（docs/pipeline/<パイプ名>/。段の並びが開発フローと違う）の確認待ちでも、同じ規則で通り、断る。"""
    work = tmp_path / "docs" / "pipeline" / "diagram"
    ls.write_state(work, _pipe_state(stage))
    state = live.read_state(work)
    assert la.check_answer(state, stage, rid(stage)) is None
    assert la.check_answer(state, stage, "0" * 10) == "id_mismatch"
    assert la.check_answer(state, "design", rid("design")) == "stage_mismatch"  # 開発フローの段の名前は合わない
    other = next(s for s in ("collect", "draw", "make-diagram_2") if s != stage)
    assert la.check_answer(state, other, rid(other)) == "stage_mismatch"


def test_d0039_ac19_pipe_record_finished_or_without_pending(tmp_path):
    """D0039-AC-19: パイプの記録でも、final が入れば finished、確認待ちが無ければ not_pending。"""
    work = tmp_path / "docs" / "pipeline" / "diagram"
    state = _pipe_state("draw")
    state["final"] = "PASSED"
    ls.write_state(work, state)
    assert la.check_answer(live.read_state(work), "draw", rid("draw")) == "finished"
    state["final"] = None
    state["pending_review"] = None
    ls.write_state(work, state)
    assert la.check_answer(live.read_state(work), "draw", rid("draw")) == "not_pending"


def test_d0039_ac19_archive_record_is_refused_without_error(tmp_path):
    """D0039-AC-19: archive/<日時>/ の中の古い記録（since が無い）を渡すと、no_id か finished で断り、落ちない。"""
    work = ls.pending_project(tmp_path, "requirements")
    state = json.loads((work / "state.json").read_text(encoding="utf-8"))
    del state["pending_review"]["since"]
    old = work / "archive" / "20261017-100000"
    ls.write_state(old, state)
    assert la.check_answer(live.read_state(old), "requirements", rid("requirements")) == "no_id"
    state["final"] = "STOPPED_BY_HUMAN"
    ls.write_state(old, state)
    assert la.check_answer(live.read_state(old), "requirements", rid("requirements")) == "finished"
    state["pending_review"] = None
    ls.write_state(old, state)
    assert la.check_answer(live.read_state(old), "requirements", rid("requirements")) == "finished"


def test_d0039_ac19_a_record_made_by_the_recorder_passes(tmp_path):
    """D0039-AC-19: 本物の Recorder が書いた確認待ちの記録は、段ごとに通る（開発フローの全部の段で）。"""
    for stage in ("requirements", "design", "red"):
        project = tmp_path / stage
        project.mkdir()
        work = ls.pending_project(project, stage)
        since = ls.pending_of(work)["since"]
        assert HEX10.fullmatch(la.review_id(stage, since))
        assert la.check_answer(live.read_state(work), stage, la.review_id(stage, since)) is None
