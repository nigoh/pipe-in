"""D0071：記録の順序の検査（pipe_in/dev/record_order.py）。承認（review approved）より前に次の段の begin が書かれていないかを、記録だけから読む。

テストは tmp_path に、差し替えの時計をつけた Recorder で記録を書く（順序を乱した記録も Recorder で書ける）。
古い形・壊れた形だけは state.json・段のログを手で書き換えて作る。リポジトリの実物（docs/pipeline/）には触れず、SDK も呼ばない。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from pipe_in.dev.record import Recorder
from pipe_in.dev.record_order import OrderReport, check_dir, check_order
from pipe_in.engine import clock
from pipe_in.engine.config import load_config

T0 = datetime(2026, 10, 17, 10, 0, 0)


def at(sec: int) -> str:
    """T0 から sec 秒あとの時刻を、記録と同じ書き方（ずれつき）の文字にする。"""
    return clock.with_offset(T0 + timedelta(seconds=sec))


def scenario(tmp_path: Path, steps: list[tuple[Any, ...]]) -> Path:
    """steps = (T0 からの秒, Recorder のメソッド名, 引数…) を、書かれた順に実行する。work_dir（docs/pipeline）を返す。"""
    now = [T0]
    r = Recorder(load_config(tmp_path), now=lambda: now[0])
    r.start("メモ")
    for sec, op, *args in steps:
        now[0] = T0 + timedelta(seconds=sec)
        getattr(r, op)(*args)
    return tmp_path / "docs" / "pipeline"


def approve_then_next(s: str, t: str, approved: int = 20, begin_next: int = 30) -> list[tuple[Any, ...]]:
    """S を始めて閉じ、確認待ち → 承認 → T を始める、正しい順。"""
    return [
        (0, "begin", s), (5, "done", s), (10, "wait", s),
        (approved, "review", s, "approved"),
        (begin_next, "begin", t),
    ]


def edit_state(work: Path, change) -> None:
    path = work / "state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def edit_first_line(work: Path, log: str, change) -> None:
    path = work / "logs" / log
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    change(first)
    lines[0] = json.dumps(first, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---- AC-02：承認のあとの begin は違反なし -----------------------------------------------------------


@pytest.mark.parametrize(
    "s,t", [("requirements", "design"), ("design", "red"), ("red", "implement")], ids=["req-design", "design-red", "red-implement"]
)
def test_d0071_ac02_begin_after_approval_is_ok(tmp_path, s, t):
    """D0071-AC-02: 確認のある段 S の approved を書いたあとに後ろの段 T を begin した記録は、違反も判定不能も無く、1組を比べた。"""
    work = scenario(tmp_path, approve_then_next(s, t))
    report = check_dir(work)
    assert isinstance(report, OrderReport)
    assert report.violations == ()
    assert report.undecided == ()
    assert report.checked == 1


# ---- AC-03：承認より前の begin は違反 -------------------------------------------------------------


def early_begin_steps() -> list[tuple[Any, ...]]:
    return [
        (0, "begin", "requirements"), (5, "done", "requirements"), (6, "wait", "requirements"),
        (10, "begin", "design"),
        (20, "review", "requirements", "approved"),
        (30, "done", "design"),
    ]


def test_d0071_ac03_begin_before_approval_is_a_violation(tmp_path):
    """D0071-AC-03: begin T → review S approved → done T の順に書いた記録は、違反を1件返す（S・T・T の begin の時刻・承認の時刻つき）。"""
    work = scenario(tmp_path, early_begin_steps())
    report = check_dir(work)
    assert report.undecided == ()
    assert len(report.violations) == 1
    v = report.violations[0]
    assert (v.stage, v.next_stage) == ("requirements", "design")
    assert v.begin_at == at(10)
    assert v.approved_at == at(20)
    assert v.log == "02_design.jsonl"
    assert v.seq == 2


def test_d0071_ac03_violation_is_found_even_if_runs_look_ordered(tmp_path):
    """D0071-AC-03: runs[] の並びは done(S) → review → done(T) で正しく見えても、at で見つかる。"""
    work = scenario(tmp_path, early_begin_steps())
    runs = json.loads((work / "state.json").read_text(encoding="utf-8"))["runs"]
    assert [("review" in r, r["stage"]) for r in runs] == [(False, "requirements"), (True, "requirements"), (False, "design")]
    assert len(check_dir(work).violations) == 1


def test_d0071_ac03_violations_are_ordered_by_stage_then_seq(tmp_path):
    """D0071-AC-03: 違反が複数あるときは、S の並び → T の順番の順に返す（requirements の違反が design の違反より先）。"""
    work = scenario(tmp_path, [
        (0, "begin", "requirements"), (2, "done", "requirements"),
        (4, "begin", "design"), (6, "done", "design"),
        (8, "begin", "red"), (10, "done", "red"),
        (20, "review", "requirements", "approved"),
        (30, "review", "design", "approved"),
    ])
    report = check_dir(work)
    assert [(v.stage, v.next_stage) for v in report.violations] == [
        ("requirements", "design"), ("requirements", "red"), ("design", "red"),
    ]


# ---- AC-04：差し戻し -------------------------------------------------------------------------------


def test_d0071_ac04_revise_then_approved_then_next_is_ok(tmp_path):
    """D0071-AC-04: S が revise のあと approved になり、承認のあとで T を begin した記録は、違反なし。"""
    work = scenario(tmp_path, [
        (0, "begin", "requirements"), (5, "done", "requirements"), (6, "wait", "requirements"),
        (10, "review", "requirements", "revise", "直して"),
        (15, "begin", "requirements"), (18, "done", "requirements"), (19, "wait", "requirements"),
        (25, "review", "requirements", "approved"),
        (30, "begin", "design"),
    ])
    report = check_dir(work)
    assert report.violations == ()
    assert report.undecided == ()


def test_d0071_ac04_second_begin_of_the_same_stage_is_not_a_violation(tmp_path):
    """D0071-AC-04: S を2回目に begin する（差し戻しのやり直し）ことは、承認の前でも違反にしない（後ろの段が無ければ比べる組は 0）。"""
    work = scenario(tmp_path, [
        (0, "begin", "requirements"), (5, "done", "requirements"), (6, "wait", "requirements"),
        (10, "review", "requirements", "revise", "直して"),
        (15, "begin", "requirements"), (18, "done", "requirements"),
    ])
    report = check_dir(work)
    assert report.violations == ()
    assert report.undecided == ()
    assert report.checked == 0


# ---- AC-05：承認が無いまま次へ ----------------------------------------------------------------------


@pytest.mark.parametrize("action,extra", [("revise", ("直して",)), ("quit", ())])
def test_d0071_ac05_revise_or_quit_then_next_begin_is_a_violation(tmp_path, action, extra):
    """D0071-AC-05: S が revise だけ（または quit）で approved が無いまま T が begin された記録は違反（approved_at は None・last_review は revise／quit）。"""
    work = scenario(tmp_path, [
        (0, "begin", "requirements"), (5, "done", "requirements"), (6, "wait", "requirements"),
        (10, "review", "requirements", action, *extra),
        (20, "begin", "design"),
    ])
    report = check_dir(work)
    assert len(report.violations) == 1
    v = report.violations[0]
    assert (v.stage, v.next_stage) == ("requirements", "design")
    assert v.approved_at is None
    assert v.last_review == action
    assert v.begin_at == at(20)


def test_d0071_ac05_no_review_at_all_is_a_violation(tmp_path):
    """D0071-AC-05: S の review が1つも無いまま T が begin された記録も違反（approved_at も last_review も None）。"""
    work = scenario(tmp_path, [(0, "begin", "requirements"), (5, "done", "requirements"), (10, "begin", "design")])
    report = check_dir(work)
    assert len(report.violations) == 1
    v = report.violations[0]
    assert (v.stage, v.next_stage, v.approved_at, v.last_review) == ("requirements", "design", None, None)


# ---- AC-06：同じ秒 ----------------------------------------------------------------------------------


@pytest.mark.parametrize("approve_first", [True, False], ids=["approved-written-first", "begin-written-first"])
def test_d0071_ac06_same_second_is_not_a_violation(tmp_path, approve_first):
    """D0071-AC-06: 承認と begin T が同じ時刻（同じ秒）の記録は、書いた順にかかわらず違反にしない。"""
    head = [(0, "begin", "requirements"), (5, "done", "requirements"), (6, "wait", "requirements")]
    pair = [(20, "review", "requirements", "approved"), (20, "begin", "design")]
    work = scenario(tmp_path, head + (pair if approve_first else pair[::-1]))
    report = check_dir(work)
    assert report.violations == ()
    assert report.undecided == ()
    assert report.checked == 1


# ---- AC-07：判定できなかった ------------------------------------------------------------------------


def _drop_review_at(data: dict) -> None:
    for run in data["runs"]:
        run.pop("at", None)


def _review_at(value: Any):
    def change(data: dict) -> None:
        for run in data["runs"]:
            if "review" in run:
                run["at"] = value

    return change


def _clean_work(tmp_path: Path) -> Path:
    return scenario(tmp_path, approve_then_next("requirements", "design"))


def test_d0071_ac07_review_without_at_is_undecided(tmp_path):
    """D0071-AC-07: at の無い review（この変更より前の古い形）は、違反にはならず「判定できなかった」に入る（S・T・理由つき）。"""
    work = _clean_work(tmp_path)
    edit_state(work, _drop_review_at)
    report = check_dir(work)
    assert report.violations == ()
    assert len(report.undecided) == 1
    u = report.undecided[0]
    assert (u.stage, u.next_stage) == ("requirements", "design")
    assert isinstance(u.reason, str) and u.reason


@pytest.mark.parametrize(
    "mutate,log",
    [
        (_review_at(12345), None),
        (_review_at(None), None),
        (_review_at("読めない文字"), None),
        (_review_at("2026-13-45T99:99:99+09:00"), None),
        (_review_at("2026-10-17T10:00:20"), None),  # ずれなし（古い書き方）と、Prompt 行のずれつきの組み合わせ
        (None, "prompt-at-missing"),
        (None, "prompt-at-garbage"),
        (None, "prompt-at-naive"),  # review の at はずれつき、Prompt 行の at はずれなし
    ],
    ids=["at-int", "at-null", "at-text", "at-bad-date", "review-naive", "prompt-at-missing", "prompt-at-garbage", "prompt-at-naive"],
)
def test_d0071_ac07_unreadable_or_mismatched_offset_is_undecided(tmp_path, mutate, log):
    """D0071-AC-07: at が文字でない・日付でない文字・ずれの有無が合わない組み合わせ・Prompt 行の at が無い／読めない記録は、違反にせず「判定できなかった」に入る。"""
    work = _clean_work(tmp_path)
    if mutate is not None:
        edit_state(work, mutate)
    else:
        def change(line: dict) -> None:
            if log == "prompt-at-missing":
                line.pop("at", None)
            elif log == "prompt-at-garbage":
                line["at"] = "いつか"
            else:
                line["at"] = "2026-10-17T10:00:30"

        edit_first_line(work, "02_design.jsonl", change)
    report = check_dir(work)
    assert report.violations == ()
    assert [(u.stage, u.next_stage) for u in report.undecided] == [("requirements", "design")]


def test_d0071_ac07_a_comparable_approval_is_enough(tmp_path):
    """D0071-AC-07: 承認が2つあり、1つが比べられなくても、もう1つが T の begin 以前なら適合（判定不能にも違反にもしない）。"""
    work = scenario(tmp_path, [
        (0, "begin", "requirements"), (5, "done", "requirements"), (6, "wait", "requirements"),
        (10, "review", "requirements", "approved"),
        (12, "review", "requirements", "approved"),
        (30, "begin", "design"),
    ])

    def drop_first(data: dict) -> None:
        next(r for r in data["runs"] if "review" in r).pop("at")  # 最初の承認だけ at を無くす

    edit_state(work, drop_first)
    report = check_dir(work)
    assert report.violations == ()
    assert report.undecided == ()


def test_d0071_ac07_no_later_comparable_approval_when_all_are_after_begin_is_a_violation(tmp_path):
    """D0071-AC-07: 比べられる承認がすべて T の begin より後なら、比べられない承認が無い限り違反（最初の承認の at を返す）。"""
    work = scenario(tmp_path, [
        (0, "begin", "requirements"), (5, "done", "requirements"), (6, "wait", "requirements"),
        (10, "begin", "design"),
        (20, "review", "requirements", "approved"),
        (25, "review", "requirements", "approved"),
    ])
    report = check_dir(work)
    assert [(v.stage, v.next_stage, v.approved_at) for v in report.violations] == [("requirements", "design", at(20))]


BROKEN_STATES: list[tuple[str, Any]] = [
    ("broken-json", "{ これは JSON ではない"),
    ("empty", ""),
    ("array", "[]"),
    ("string", '"state"'),
    ("null", "null"),
    ("stages-not-list", json.dumps({"stages": "x", "runs": []})),
    ("stages-items-not-dict", json.dumps({"stages": [1, "a", None], "runs": []})),
    ("runs-not-list", json.dumps({"stages": [{"name": "requirements", "review": True}], "runs": "x"})),
    ("runs-items-not-dict", json.dumps({"stages": [{"name": "requirements", "review": True}], "runs": [1, None, "a"]})),
    ("stage-without-name", json.dumps({"stages": [{"review": True}], "runs": [{"review": "approved"}]})),
]


@pytest.mark.parametrize("body", [b for _, b in BROKEN_STATES], ids=[n for n, _ in BROKEN_STATES])
def test_d0071_ac07_broken_state_json_does_not_raise(tmp_path, body):
    """D0071-AC-07: 壊れた state.json（壊れた JSON・配列・stages や runs の型違い）でも、check_dir は例外で落ちず OrderReport を返す。"""
    work = tmp_path / "docs" / "pipeline"
    work.mkdir(parents=True)
    (work / "state.json").write_text(body, encoding="utf-8")
    report = check_dir(work)
    assert isinstance(report, OrderReport)
    assert report.violations == ()  # 読めない記録を違反とは言わない


def test_d0071_ac07_unreadable_state_is_undecided(tmp_path):
    """D0071-AC-07: state.json が壊れた JSON・stages が配列でないときは、「判定できなかった」を返す（黙って「守られている」にしない）。"""
    for body in ("{ 壊れ", json.dumps({"stages": "x", "runs": []})):
        work = tmp_path / "docs" / "pipeline"
        work.mkdir(parents=True, exist_ok=True)
        (work / "state.json").write_text(body, encoding="utf-8")
        report = check_dir(work)
        assert report.violations == ()
        assert len(report.undecided) >= 1, body


def test_d0071_ac07_missing_state_and_logs_do_not_raise(tmp_path):
    """D0071-AC-07: state.json が無いフォルダ、logs/ が無い記録でも、例外で落ちない（logs/ が無ければ begin が無いので違反なし・検査した組は 0）。"""
    empty = tmp_path / "none"
    empty.mkdir()
    assert isinstance(check_dir(empty), OrderReport)
    assert isinstance(check_dir(tmp_path / "does-not-exist"), OrderReport)
    (tmp_path / "rec").mkdir()
    work = _clean_work(tmp_path / "rec")
    import shutil

    shutil.rmtree(work / "logs")
    report = check_dir(work)
    assert report.violations == ()
    assert report.checked == 0


@pytest.mark.parametrize(
    "first_line",
    ["{ 壊れた行", "", "[1, 2]", json.dumps({"_type": "AssistantMessage", "content": []})],
    ids=["broken-json", "empty-file", "array", "not-prompt"],
)
def test_d0071_ac07_broken_first_line_of_a_log_does_not_raise(tmp_path, first_line):
    """D0071-AC-07: 最初の行が読めない・Prompt でないログがあっても例外で落ちない（段が分からないログは違反にせず「判定できなかった」）。"""
    work = _clean_work(tmp_path)
    (work / "logs" / "09_extra.jsonl").write_text(first_line + "\n", encoding="utf-8")
    report = check_dir(work)
    assert report.violations == ()
    assert any(u.stage is None for u in report.undecided)


def test_d0071_ac07_check_order_is_pure_and_never_raises():
    """D0071-AC-07: check_order は、どんな入力でも例外を投げない（state が辞書でない・runs が壊れている・Prompt 行が空）。"""
    for state in (None, [], "x", 3, {}, {"stages": None}, {"stages": [{"name": "requirements", "review": True}], "runs": None}):
        report = check_order(state, [])
        assert isinstance(report, OrderReport)
        assert report.violations == ()


# ---- AC-08：調べない段 ------------------------------------------------------------------------------


def test_d0071_ac08_skipped_stage_is_not_checked(tmp_path):
    """D0071-AC-08: S の begin が無い（その段を飛ばした）記録では、S について違反を出さない（設計→テスト先行の組だけを調べる）。"""
    work = scenario(tmp_path, approve_then_next("design", "red"))
    report = check_dir(work)
    assert report.violations == ()
    assert report.undecided == ()
    assert report.checked == 1  # requirements は begin が無いので比べない


def test_d0071_ac08_stages_without_review_are_not_checked(tmp_path):
    """D0071-AC-08: 確認の無い段（implement・test）は調べない。承認の無いまま後ろの段が始まっても違反にしない。"""
    work = scenario(tmp_path, [
        (0, "begin", "implement", 1), (5, "done", "implement"),
        (10, "begin", "test", 1), (15, "done", "test"),
        (20, "begin", "implement", 2), (25, "done", "implement"),
    ])
    stages = json.loads((work / "state.json").read_text(encoding="utf-8"))["stages"]
    assert {s["name"]: s["review"] for s in stages}["implement"] is False
    report = check_dir(work)
    assert report.violations == ()
    assert report.undecided == ()
    assert report.checked == 0
