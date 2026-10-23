"""D0028: 検証の審査の計算（pipe_in.pipe.judge）：合否と平均をエンジンが出す。SDK は呼ばず、ファイルも書かない。

generator/judge_score.py（D0022）とは決まりを二重に持つ。同じ入力で同じ合否と平均になることを AC-20 で確かめる。
"""

from __future__ import annotations

import copy
import json

import pytest

from pipe_in.pipe import judge

OK_MUST = {"m1": {"violated": False, "evidence": ""}}


def reply(scores: dict, must: dict | None = None) -> dict:
    """審査役の返り（judge の値）。採点した項目には理由を付ける。"""
    return {
        "criteria": {k: {"reason": f"{k} の理由", "score": v} for k, v in scores.items()},
        "must": copy.deepcopy(OK_MUST if must is None else must),
    }


def ev(scores: dict, must: dict | None = None, **kw) -> judge.JudgeOutcome:
    data = reply(scores, must)
    return judge.evaluate(data, list(data["criteria"]), list(data["must"]), **kw)


def quarters(n: int, total_quarters: int) -> dict:
    """n 個の項目で、点（0.25 刻み）の合計がちょうど total_quarters/4 になる並び。"""
    base, rem = divmod(total_quarters, n)
    return {f"i{k}": (base + (1 if k < rem else 0)) / 4 for k in range(n)}


# ---- AC-01・AC-02・AC-03・AC-04 --------------------------------------------------------


def test_ac01_no_violation_and_mean_over_threshold_passes():
    """D0028-AC-01: must の違反が無く、平均がしきい値以上なら合格。"""
    got = ev({"a": 1.0, "b": 0.75})
    assert (got.status, got.valid, got.overall, got.problems) == ("pass", True, 0.88, [])


def test_ac02_must_violation_fails_even_with_full_marks():
    """D0028-AC-02: must の違反が 1 つ（true）あれば、平均が 1.0 でも不合格。直す点に根拠が出る。"""
    must = {"m1": {"violated": True, "evidence": "out.md:3 に禁止語"}, "m2": {"violated": False, "evidence": ""}}
    got = ev({"a": 1.0, "b": 1.0}, must)
    assert (got.status, got.overall, got.valid) == ("fail", 1.0, True)
    text = "\n".join(got.problems)
    assert "m1" in text and "out.md:3 に禁止語" in text
    assert "m2" not in text


def test_ac03_must_null_fails():
    """D0028-AC-03: must が null（確かめられない）でも不合格。直す点に「確かめられなかった」と根拠が出る。"""
    must = {"m1": {"violated": None, "evidence": "ファイルが読めなかった"}}
    got = ev({"a": 1.0, "b": 1.0}, must)
    assert got.status == "fail"
    text = "\n".join(got.problems)
    assert "確かめられ" in text and "m1" in text and "ファイルが読めなかった" in text


def test_ac03_must_null_without_evidence_still_explained():
    """D0028-AC-03: 根拠が空の null でも不合格で、直す点が出る（根拠なし、と書く）。"""
    got = ev({"a": 1.0}, {"m1": {"violated": None, "evidence": ""}})
    assert got.status == "fail" and got.valid is True
    assert "確かめられ" in "\n".join(got.problems)


def test_ac04_null_scores_are_excluded():
    """D0028-AC-04: null の点は平均から外れる（0.5 と null と 1.0 → 平均 0.75）。"""
    got = ev({"a": 0.5, "b": None, "c": 1.0})
    assert got.overall == 0.75
    assert got.scores == {"a": 0.5, "b": None, "c": 1.0}
    assert got.status == "pass"


def test_ac04_all_null_fails():
    """D0028-AC-04: 点が全部 null なら不合格（採点できないものを通さない）。平均は None。"""
    got = ev({"a": None, "b": None})
    assert (got.status, got.overall) == ("fail", None)
    assert "採点できた項目がありません" in "\n".join(got.problems)


# ---- AC-05 丸め ---------------------------------------------------------------------


def test_ac05_rounds_half_up_at_boundary():
    """D0028-AC-05: 0.745 は 0.75 として比べ、しきい値 0.75 で合格。0.744 は 0.74 で不合格。浮動小数の誤差で逆にならない。"""
    up = ev(quarters(200, 596), threshold=0.75)  # 149/200 = 0.745
    assert (up.overall, up.status) == (0.75, "pass")
    down = ev(quarters(125, 372), threshold=0.75)  # 93/125 = 0.744
    assert (down.overall, down.status) == (0.74, "fail")
    assert ev(quarters(125, 372), threshold=0.74).status == "pass"


def test_ac05_rounds_half_up_small_cases():
    """D0028-AC-05: 0.625 は 0.63、0.375 は 0.38（四捨五入。float の round なら偶数丸めで 0.62 / 0.38 になりうる）。"""
    assert ev({"a": 1.0, "b": 0.5, "c": 0.5, "d": 0.5}).overall == 0.63
    assert ev({"a": 0.5, "b": 0.25, "c": 0.5, "d": 0.25}).overall == 0.38


# ---- AC-06 しきい値 ---------------------------------------------------------------------


def test_ac06_below_threshold_fails():
    """D0028-AC-06: 平均がしきい値に満たなければ不合格。直す点に平均としきい値と、点の低い項目の理由が出る。"""
    got = ev({"a": 0.75, "b": 0.25, "c": 1.0}, threshold=0.9)  # 2.0/3 = 0.67
    assert (got.status, got.overall, got.threshold) == ("fail", 0.67, 0.9)
    text = "\n".join(got.problems)
    assert "0.67" in text and "0.9" in text
    assert "b の理由" in text and "a の理由" in text  # 1.0 未満の項目の理由
    assert "c の理由" not in text  # 満点の項目は直す点ではない


def test_ac06_default_threshold_is_07():
    """D0028-AC-06: しきい値を渡さなければ 0.7。0.70 は合格、0.69 は不合格、0.695 は 0.70 に丸まって合格。"""
    at = ev({"a": 1.0, "b": 1.0, "c": 0.5, "d": 0.5, "e": 0.5})  # 3.5/5
    assert (at.overall, at.status, at.threshold) == (0.7, "pass", 0.7)
    below = ev({f"i{n}": 0.75 if n < 6 else 0.5 for n in range(8)})  # 5.5/8 = 0.6875
    assert (below.overall, below.status) == (0.69, "fail")
    edge = ev({f"i{n}": 1.0 if n < 34 else 0.75 if n == 34 else 0.0 for n in range(50)})  # 34.75/50 = 0.695
    assert (edge.overall, edge.status) == (0.7, "pass")


# ---- AC-07 審査役の合否・平均は使わない ----------------------------------------------------


def test_ac07_reviewer_verdict_and_overall_are_ignored():
    """D0028-AC-07: 返りに合否や平均が入っていても使わない（pass と言っても、点が低ければ不合格。must 違反でも不合格）。"""
    data = reply({"a": 0.5, "b": 0.5})
    data.update({"status": "pass", "verdict": "pass", "overall": 1.0})
    got = judge.evaluate(data, ["a", "b"], ["m1"])
    assert got.valid is True  # 余計なキーは捨てるだけで、返りが決まりに合わない扱いにはしない
    assert (got.status, got.overall) == ("fail", 0.5)

    data = reply({"a": 1.0, "b": 1.0}, {"m1": {"violated": True, "evidence": "禁止語"}})
    data.update({"status": "pass", "overall": 1.0})
    assert judge.evaluate(data, ["a", "b"], ["m1"]).status == "fail"


# ---- AC-08 決まりに合わない返り ----------------------------------------------------------


def _mut(fn):
    def make():
        data = reply({"a": 1.0, "b": 0.5})
        fn(data)
        return data

    return make


MALFORMED = {
    "点が5段階以外（0.3）": _mut(lambda d: d["criteria"]["a"].update(score=0.3)),
    "点が5段階以外（2）": _mut(lambda d: d["criteria"]["a"].update(score=2)),
    "点が文字列": _mut(lambda d: d["criteria"]["a"].update(score="1.0")),
    "点が真偽値": _mut(lambda d: d["criteria"]["a"].update(score=True)),
    "点のキーが無い": _mut(lambda d: d["criteria"]["a"].pop("score")),
    "理由なし（キーが無い）": _mut(lambda d: d["criteria"]["a"].pop("reason")),
    "理由が空": _mut(lambda d: d["criteria"]["a"].update(reason="  ")),
    "理由が文字列でない": _mut(lambda d: d["criteria"]["a"].update(reason=3)),
    "項目の欠け": _mut(lambda d: d["criteria"].pop("b")),
    "must の欠け": _mut(lambda d: d["must"].pop("m1")),
    "知らない項目名": _mut(lambda d: d["criteria"].update(zzz={"reason": "x", "score": 1.0})),
    "知らない must 名": _mut(lambda d: d["must"].update(zzz={"violated": False, "evidence": ""})),
    "違反なのに根拠なし": _mut(lambda d: d["must"]["m1"].update(violated=True, evidence="")),
    "違反なのに根拠が空白": _mut(lambda d: d["must"]["m1"].update(violated=True, evidence="  ")),
    "violated が文字列": _mut(lambda d: d["must"]["m1"].update(violated="yes")),
    "violated が数": _mut(lambda d: d["must"]["m1"].update(violated=0)),
    "evidence が文字列でない": _mut(lambda d: d["must"]["m1"].update(evidence=5)),
    "項目が辞書でない": _mut(lambda d: d["criteria"].update(a="1.0")),
    "must の中身が辞書でない": _mut(lambda d: d["must"].update(m1=True)),
    "criteria が辞書でない": _mut(lambda d: d.update(criteria=[])),
    "must が辞書でない": _mut(lambda d: d.update(must=None)),
    "criteria が無い": _mut(lambda d: d.pop("criteria")),
    "must が無い": _mut(lambda d: d.pop("must")),
}


@pytest.mark.parametrize("name", list(MALFORMED))
def test_ac08_malformed_returns_are_invalid(name):
    """D0028-AC-08: 返りが決まりに合わないときは、例外にせず valid=False の不合格。理由が problems に出る。"""
    got = judge.evaluate(MALFORMED[name](), ["a", "b"], ["m1"])
    assert (got.status, got.valid, got.overall) == ("fail", False, None), name
    assert got.scores == {}
    assert got.problems, name
    assert "審査役の返りが決まりに合いませんでした" in got.problems[0]
    assert len(got.problems) >= 2  # 先頭の見出しのほかに、どこがどう合わないかを書く


@pytest.mark.parametrize("data", [None, [], "pass", 3, {}, {"status": "pass"}], ids=repr)
def test_ac08_whole_reply_of_wrong_shape_is_invalid(data):
    """D0028-AC-08: 返り全体が辞書でない・中身が無いときも、例外にせず valid=False の不合格。"""
    got = judge.evaluate(data, ["a", "b"], ["m1"])
    assert (got.status, got.valid) == ("fail", False)
    assert "審査役の返りが決まりに合いませんでした" in got.problems[0]


def test_ac08_integer_levels_zero_and_one_are_valid():
    """D0028-AC-08: 点の 0 と 1（整数）は 0.0・1.0 と同じ段として受ける。"""
    got = judge.evaluate(reply({"a": 1, "b": 0}), ["a", "b"], ["m1"])
    assert (got.valid, got.overall) == (True, 0.5)


# ---- AC-15 記録の形（計算側） -----------------------------------------------------------------


def test_ac15_to_record_shape():
    """D0028-AC-15: to_record() は state.json の check.judge に入れる形。理由（reason）は入れない。"""
    must = {"m1": {"violated": True, "evidence": "禁止語"}}
    rec = judge.evaluate(reply({"a": 0.5, "b": None}, must), ["a", "b"], ["m1"]).to_record()
    assert rec == {
        "status": "fail",
        "overall": 0.5,
        "threshold": 0.7,
        "scores": {"a": 0.5, "b": None},
        "must": {"m1": {"violated": True, "evidence": "禁止語"}},
        "valid": True,
    }
    assert "の理由" not in json.dumps(rec, ensure_ascii=False)


def test_ac15_invalid_return_record():
    """D0028-AC-15: 決まりに合わない返りの記録は valid=False、status=fail、平均は null、点と must は空。"""
    rec = judge.evaluate(None, ["a"], ["m1"]).to_record()
    assert (rec["status"], rec["valid"], rec["overall"], rec["scores"], rec["must"]) == ("fail", False, None, {}, {})
    json.dumps(rec)  # JSON にできる


# ---- AC-20 judge_score（D0022）と同じ合否と平均 -------------------------------------------------

BAD_MUST = {"m1": {"violated": True, "evidence": "根拠"}}
NULL_MUST = {"m1": {"violated": None, "evidence": ""}}

SAME_CASES = {
    "満点": ({"a": 1.0, "b": 1.0}, None),
    "ちょうど 0.70": ({"a": 1.0, "b": 1.0, "c": 0.5, "d": 0.5, "e": 0.5}, None),
    "0.6875 → 0.69": ({f"i{n}": 0.75 if n < 6 else 0.5 for n in range(8)}, None),
    "0.695 → 0.70": ({f"i{n}": 1.0 if n < 34 else 0.75 if n == 34 else 0.0 for n in range(50)}, None),
    "0.745 → 0.75": (quarters(200, 596), None),
    "0.744 → 0.74": (quarters(125, 372), None),
    "0.625 → 0.63": ({"a": 1.0, "b": 0.5, "c": 0.5, "d": 0.5}, None),
    "0.375 → 0.38": ({"a": 0.5, "b": 0.25, "c": 0.5, "d": 0.25}, None),
    "null を外す": ({"a": 0.5, "b": None, "c": 1.0}, None),
    "全部 null": ({"a": None, "b": None}, None),
    "満点でも must 違反": ({"a": 1.0, "b": 1.0}, BAD_MUST),
    "must が null": ({"a": 1.0, "b": 1.0}, NULL_MUST),
    "must の違反と null が混ざる": ({"a": 1.0}, {"m1": BAD_MUST["m1"], "m2": NULL_MUST["m1"]}),
    "低い点": ({"a": 0.25, "b": 0.0, "c": 0.5}, None),
    "全部 0": ({"a": 0.0, "b": 0.0}, None),
}


def to_score_payload(data: dict) -> dict:
    """judge の値を、judge_score.score() の入力（runs が 1 回・rubric つき）に直す。"""
    return {
        "runs": [
            {
                "reasons": {k: v["reason"] for k, v in data["criteria"].items()},
                "scores": {k: v["score"] for k, v in data["criteria"].items()},
                "must": copy.deepcopy(data["must"]),
            }
        ],
        "rubric": [{"name": k, "must": False} for k in data["criteria"]] + [{"name": k, "must": True} for k in data["must"]],
    }


@pytest.mark.parametrize("name", list(SAME_CASES))
def test_ac20_matches_judge_score(name):
    """D0028-AC-20: 同じ入力を、本体の計算と generator/judge_score.py に通すと、合否と平均が一致する。"""
    from pipe_in_generator import judge_score

    scores, must = SAME_CASES[name]
    data = reply(scores, must)
    mine = judge.evaluate(data, list(data["criteria"]), list(data["must"]))  # しきい値は既定（0.7）
    theirs = judge_score.score(to_score_payload(data))
    assert mine.valid is True
    assert mine.status == theirs["verdict"], name
    assert mine.overall == theirs["overall"], name
    assert mine.threshold == theirs["threshold"] == 0.7


def test_ac20_default_threshold_constant_is_07():
    """D0028-AC-20: 既定のしきい値は judge_score と同じ 0.7。"""
    from fractions import Fraction

    from pipe_in_generator import judge_score

    assert judge.DEFAULT_THRESHOLD == judge_score.THRESHOLD == Fraction(7, 10)


INVALID_FOR_BOTH = {
    "点が 0.3": lambda d: d["criteria"]["a"].update(score=0.3),
    "理由なし": lambda d: d["criteria"]["a"].update(reason=""),
    "違反で根拠なし": lambda d: d["must"]["m1"].update(violated=True, evidence=""),
    "violated が文字列": lambda d: d["must"]["m1"].update(violated="yes"),
    "点が真偽値": lambda d: d["criteria"]["a"].update(score=True),
}


@pytest.mark.parametrize("name", list(INVALID_FOR_BOTH))
def test_ac20_inputs_judge_score_rejects_are_invalid_here(name):
    """D0028-AC-20: judge_score が ValueError にする入力は、evaluate では valid=False の不合格になる。"""
    from pipe_in_generator import judge_score

    data = reply({"a": 1.0, "b": 0.5})
    INVALID_FOR_BOTH[name](data)
    with pytest.raises(ValueError):
        judge_score.score(to_score_payload(data))
    got = judge.evaluate(data, ["a", "b"], ["m1"])
    assert (got.valid, got.status) == (False, "fail"), name
