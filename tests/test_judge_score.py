"""pipe-in-gen judge-score：審査役の採点から総合点・合否・ばらつきを出す計算と、入力の検め（D0022）。

SDK は呼ばず、ファイルも書かない。標準入力と標準出力は偽物に差し替える。
"""

from __future__ import annotations

import copy
import io
import json

import pytest


def js():
    from pipe_in_generator import judge_score

    return judge_score


MUST_OK = {"m1": {"violated": False, "evidence": ""}}


def run(scores: dict, must: dict | None = None) -> dict:
    """審査役の返事1回ぶん。採点した項目には理由を付ける（点の前に理由）。"""
    return {
        "reasons": {k: f"{k} の理由" for k in scores},
        "scores": dict(scores),
        "must": copy.deepcopy(MUST_OK if must is None else must),
    }


def one(scores: dict, must: dict | None = None) -> dict:
    return js().score({"runs": [run(scores, must)]})


# ---- D0022-AC-13: 総合点は null でない採点項目の平均 --------------------------------------------


def test_overall_is_mean_of_non_null_scores():
    """D0022-AC-13: 総合点は null でない採点項目の平均（null は数えない）。"""
    assert one({"a": 1.0, "b": 0.5, "c": None})["overall"] == 0.75
    assert one({"a": 1.0, "b": 0.0, "c": 0.25})["overall"] == 0.42  # 0.4166... は小数 2 桁


def test_overall_rounds_half_up():
    """D0022-AC-13: 小数 2 桁の丸めは四捨五入（0.625 は 0.63、0.375 は 0.38）。"""
    assert one({"a": 1.0, "b": 0.5, "c": 0.5, "d": 0.5})["overall"] == 0.63  # 2.5/4 = 0.625
    assert one({"a": 0.5, "b": 0.25, "c": 0.5, "d": 0.25})["overall"] == 0.38  # 1.5/4 = 0.375


def test_verdict_pass_at_threshold_and_fail_below():
    """D0022-AC-13: 0.70 は pass、0.69 は fail（しきい値 0.7）。"""
    at = one({"a": 1.0, "b": 1.0, "c": 0.5, "d": 0.5, "e": 0.5})  # 3.5/5 = 0.70
    assert (at["overall"], at["verdict"], at["threshold"]) == (0.7, "pass", 0.7)
    below = one({f"i{n}": 0.75 if n < 6 else 0.5 for n in range(8)})  # 5.5/8 = 0.6875 -> 0.69
    assert (below["overall"], below["verdict"]) == (0.69, "fail")


def test_verdict_compares_the_rounded_overall():
    """D0022-AC-13: 合否は丸めた overall と 0.7 を比べる（0.695 は 0.70 に丸まり pass。見える数字と合否をそろえる）。"""
    scores = {f"i{n}": 1.0 if n < 34 else 0.75 if n == 34 else 0.0 for n in range(50)}  # 34.75/50 = 0.695
    got = one(scores)
    assert (got["overall"], got["verdict"]) == (0.7, "pass")


def test_must_violation_fails_even_with_perfect_scores():
    """D0022-AC-13・AC-17: must の違反が 1 つでもあれば、採点項目が満点でも fail。違反と根拠が must_violations に出る。"""
    must = {"m1": {"violated": True, "evidence": "out.md:3 に禁止語"}, "m2": {"violated": False, "evidence": ""}}
    got = one({"a": 1.0, "b": 1.0}, must)
    assert got["overall"] == 1.0
    assert got["verdict"] == "fail"
    assert len(got["must_violations"]) == 1
    text = json.dumps(got["must_violations"], ensure_ascii=False)
    assert "m1" in text and "out.md:3 に禁止語" in text
    assert "m2" not in text


def test_all_null_scores_gives_null_overall_and_fail():
    """D0022-AC-13: 採点項目が全部 null なら overall は null で fail。"""
    got = one({"a": None, "b": None})
    assert got["overall"] is None
    assert got["verdict"] == "fail"


def test_unchecked_must_fails_and_is_listed():
    """D0022-AC-13: must が確かめられない（violated が null）なら fail にして must_unchecked に載せる。違反には数えない。"""
    got = one({"a": 1.0}, {"m1": {"violated": None, "evidence": "資料が読めない"}, "m2": {"violated": False, "evidence": ""}})
    assert got["verdict"] == "fail"
    assert got["must_unchecked"] == ["m1"]
    assert got["must_violations"] == []


def test_no_violation_no_unchecked_gives_empty_lists():
    """D0022-AC-14: 違反も未確認も無ければ、must_violations・must_unchecked は空の配列。"""
    got = one({"a": 1.0})
    assert got["must_violations"] == [] and got["must_unchecked"] == []


def test_single_run_scores_are_the_items():
    """D0022-AC-14: 1回なら、項目ごとの scores はその回の点（null は null のまま）。"""
    got = one({"a": 1.0, "b": None})
    assert got["scores"] == {"a": 1.0, "b": None}
    assert got["runs"][0]["overall"] == 1.0 and got["runs"][0]["verdict"] == "pass"


# ---- D0022-AC-14: --runs の平均とばらつき -------------------------------------------------------


def test_runs_average_and_variance():
    """D0022-AC-14: 項目ごとの平均は null を除く。総合点は回の overall の平均。合否が割れた割合と、overall の最大と最小の差が出る。"""
    got = js().score({"runs": [run({"a": 1.0, "b": 1.0}), run({"a": 0.5, "b": None})]})
    assert got["scores"] == {"a": 0.75, "b": 1.0}
    assert [r["overall"] for r in got["runs"]] == [1.0, 0.5]
    assert [r["verdict"] for r in got["runs"]] == ["pass", "fail"]
    assert got["overall"] == 0.75
    assert got["verdict"] == "pass"  # 平均 0.75 で決まる（must の違反が無い）
    assert got["variance"]["verdict_disagreement"] == 0.5
    assert got["variance"]["overall_range"] == pytest.approx(0.5)


def test_verdict_disagreement_is_share_outside_the_majority():
    """D0022-AC-14: 合否の食い違いは、多いほうに入らなかった回の割合（3 回中 1 回なら 0.33、そろえば 0）。"""
    odd = js().score({"runs": [run({"a": 1.0}), run({"a": 1.0}), run({"a": 0.0})]})
    assert odd["variance"]["verdict_disagreement"] == 0.33
    same = js().score({"runs": [run({"a": 1.0}), run({"a": 0.75})]})
    assert same["variance"]["verdict_disagreement"] == 0
    assert same["variance"]["overall_range"] == pytest.approx(0.25)


def test_average_below_threshold_fails_when_no_must_violation():
    """D0022-AC-14: must の違反が無ければ、総合点の平均が 0.7 に届かないと fail。"""
    got = js().score({"runs": [run({"a": 1.0}), run({"a": 0.25}), run({"a": 0.25})]})  # 平均 0.5
    assert (got["overall"], got["verdict"]) == (0.5, "fail")


def test_any_must_violation_in_any_run_fails():
    """D0022-AC-14: 1 回でも must の違反があれば、平均が高くても最終は fail。違反は must_violations に出る。"""
    bad = {"m1": {"violated": True, "evidence": "a.md:1"}}
    got = js().score({"runs": [run({"a": 1.0}), run({"a": 1.0}), run({"a": 1.0}, bad)]})
    assert got["overall"] == 1.0
    assert got["verdict"] == "fail"
    assert "a.md:1" in json.dumps(got["must_violations"], ensure_ascii=False)


def test_unchecked_must_in_any_run_fails():
    """D0022-AC-14: 1 回でも must が確かめられなければ、最終は fail。"""
    unknown = {"m1": {"violated": None, "evidence": "読めない"}}
    got = js().score({"runs": [run({"a": 1.0}), run({"a": 1.0}, unknown)]})
    assert got["verdict"] == "fail" and got["must_unchecked"] == ["m1"]


def test_overall_range_is_null_with_one_usable_run():
    """D0022-AC-14: overall が null でない回が 1 つ以下なら overall_range は null。全部 null なら総合点の平均も null で fail。"""
    got = js().score({"runs": [run({"a": 1.0}), run({"a": None})]})
    assert got["variance"]["overall_range"] is None
    assert got["overall"] == 1.0
    empty = js().score({"runs": [run({"a": None}), run({"a": None})]})
    assert empty["overall"] is None and empty["verdict"] == "fail"


def test_single_run_has_no_variance():
    """D0022-AC-14: variance は --runs が 2 以上のときだけ。"""
    assert "variance" not in one({"a": 1.0})
    assert "variance" in js().score({"runs": [run({"a": 1.0}), run({"a": 1.0})]})


@pytest.mark.parametrize("count", [0, 6, 7])
def test_runs_out_of_range_is_rejected(count):
    """D0022-AC-14: 回の数が 0 件・6 件以上は受け取らない（1〜5 件だけ）。"""
    with pytest.raises(ValueError):
        js().score({"runs": [run({"a": 1.0}) for _ in range(count)]})


@pytest.mark.parametrize("count", [1, 5])
def test_runs_edges_are_accepted(count):
    """D0022-AC-14: 1 件と 5 件は受け取る。"""
    assert js().score({"runs": [run({"a": 1.0}) for _ in range(count)]})["verdict"] == "pass"


def test_output_keys_match_spec():
    """D0022-AC-14: 結果のキー（runs・scores・must_violations・must_unchecked・overall・threshold・verdict、2 回以上は variance）。"""
    single = one({"a": 1.0})
    assert set(single) == {"runs", "scores", "must_violations", "must_unchecked", "overall", "threshold", "verdict"}
    assert set(single["runs"][0]) == {"reasons", "scores", "must", "overall", "verdict"}
    multi = js().score({"runs": [run({"a": 1.0}), run({"a": 1.0})]})
    assert set(multi) == set(single) | {"variance"}
    assert set(multi["variance"]) == {"verdict_disagreement", "overall_range"}


def test_score_does_not_change_its_input():
    """D0022-AC-14: 入力の辞書を書き換えない。"""
    payload = {"runs": [run({"a": 1.0, "b": None})]}
    before = copy.deepcopy(payload)
    js().score(payload)
    assert payload == before


# ---- 入力の検め：不正は ValueError ---------------------------------------------------------------


def _bad_score(value):
    return {"runs": [run({"a": value})]}


def _no_reason():
    r = run({"a": 1.0})
    r["reasons"] = {}
    return {"runs": [r]}


def _names_differ():
    return {"runs": [run({"a": 1.0}), run({"b": 1.0})]}


def _must_names_differ():
    return {"runs": [run({"a": 1.0}, MUST_OK), run({"a": 1.0}, {"m9": {"violated": False, "evidence": ""}})]}


def _rubric_scores_differ():
    return {"rubric": [{"name": "a", "must": False}, {"name": "z", "must": False}], "runs": [run({"a": 1.0})]}


def _rubric_must_differ():
    return {"rubric": [{"name": "a", "must": False}, {"name": "m2", "must": True}], "runs": [run({"a": 1.0})]}


def _violated_not_bool():
    return {"runs": [run({"a": 1.0}, {"m1": {"violated": "yes", "evidence": "x"}})]}


def _violated_without_evidence():
    return {"runs": [run({"a": 1.0}, {"m1": {"violated": True, "evidence": ""}})]}


@pytest.mark.parametrize(
    "make",
    [
        lambda: _bad_score(0.6),
        lambda: _bad_score(0.8),
        lambda: _bad_score(1.5),
        lambda: _bad_score(-0.25),
        lambda: _bad_score(True),
        lambda: _bad_score("1.0"),
        _no_reason,
        _names_differ,
        _must_names_differ,
        _rubric_scores_differ,
        _rubric_must_differ,
        _violated_not_bool,
        _violated_without_evidence,
        lambda: [],
        lambda: {},
        lambda: {"runs": "x"},
        lambda: {"runs": [[]]},
    ],
    ids=[
        "0.6", "0.8", "1.5", "-0.25", "true", "string", "no-reason", "names-differ", "must-names-differ",
        "rubric-scores-differ", "rubric-must-differ", "violated-not-bool", "violated-no-evidence",
        "not-dict", "no-runs", "runs-not-list", "run-not-dict",
    ],
)
def test_invalid_input_is_rejected(make):
    """D0022-AC-14: 5段階以外・真偽値や文字列の点・理由なし・項目名の食い違い・rubric とのずれ・根拠の無い違反は、受け取らずに止める。"""
    with pytest.raises(ValueError):
        js().score(make())


@pytest.mark.parametrize("value", [0.0, 0.25, 0.5, 0.75, 1.0, None])
def test_five_levels_and_null_are_accepted(value):
    """D0022-AC-10: 点は 0.0・0.25・0.5・0.75・1.0 と null だけ受け取る（null も理由を付ければ受け取る）。"""
    assert js().score(_bad_score(value))["runs"][0]["scores"] == {"a": value}


def test_rubric_matching_names_is_accepted():
    """D0022-AC-12: rubric の項目名と各回の scores・must の名前がちょうど合えば受け取る。"""
    rubric = [{"name": "a", "must": False}, {"name": "m1", "must": True}]
    assert js().score({"rubric": rubric, "runs": [run({"a": 1.0})]})["verdict"] == "pass"


# ---- 入出力：標準入力 -> 標準出力 ----------------------------------------------------------------


def _stdin(monkeypatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(text.encode("utf-8")), encoding="utf-8"))


def test_main_reads_stdin_and_prints_json(monkeypatch, capsys):
    """D0022-AC-14: main は標準入力の JSON を読み、結果の JSON を標準出力に 1 つ出す（終了コード 0）。"""
    _stdin(monkeypatch, json.dumps({"runs": [run({"a": 1.0})]}))
    assert js().main() == 0
    out = capsys.readouterr().out
    assert json.loads(out)["verdict"] == "pass"


def test_main_prints_fail_result_with_exit_code_zero(monkeypatch, capsys):
    """D0022-AC-13: 結果が fail でも終了コードは 0（審査は合否を決めない）。"""
    bad = {"m1": {"violated": True, "evidence": "a:1"}}
    _stdin(monkeypatch, json.dumps({"runs": [run({"a": 1.0}, bad)]}))
    assert js().main() == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "fail"


@pytest.mark.parametrize("text", ["{not json", "[]", "", json.dumps({"runs": [run({"a": 0.6})]})])
def test_main_rejects_bad_input_with_exit_code_2(monkeypatch, capsys, text):
    """D0022-AC-14: 不正な入力は終了コード 2。理由は標準エラーに出し、標準出力は空。"""
    _stdin(monkeypatch, text)
    assert js().main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip()


def test_cli_dispatches_judge_score(monkeypatch, capsys):
    """D0022-AC-14: pipe-in-gen judge-score は judge_score.main を呼ぶ（guard-hook と同じ作り。--project は要らない）。"""
    from pipe_in_generator import cli

    _stdin(monkeypatch, json.dumps({"runs": [run({"a": 1.0})]}))
    assert cli.main(["judge-score"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "pass"


def test_cli_help_lists_judge_score(capsys):
    """D0022-AC-29: pipe-in-gen --help の一覧に judge-score がある（スキルはこれを見て、古い pipe-in-gen を見分ける）。"""
    from pipe_in_generator import cli

    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "judge-score" in capsys.readouterr().out
