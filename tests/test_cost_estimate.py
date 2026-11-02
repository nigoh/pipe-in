"""D0066：流す前の費用の目安の計算（pipe_in/usage/estimate.py・prices.py）。純粋な関数だけを確かめる（ファイル・SDK・時計に触れない）。

- 新しい部品（pipe_in.usage.prices・pipe_in.usage.estimate）は、使うところで読み込む。無いあいだは「まだ作っていない」を理由に落とす。
- 部品の形（このファイルが決める。実装はこれに合わせる）：
  - prices.PRICES = {"as_of": "YYYY-MM", "per_turn": {"haiku": int, "sonnet": int, "opus": int}, "note": str}（単位は units = 1/10000 ドル）
  - prices.family_of(model) -> (系統, 不明か)
  - estimate.StageInput(name, model, max_turns, default_turns, max_budget_usd, max_retries)（キーワードで渡す）
  - estimate.estimate(stages, today: date) -> Estimate（.stages の各要素は .name・.low・.high・.marks（印の文字列の並び）、全体は .low・.high・.stale）
  - estimate.actual_usd(state) -> float | None、estimate.format_table(est, actual) -> str、estimate.DISCLAIMER・STALE_DAYS・LOW_PERCENT
- 本体と拡張が同じ数字を出すことは、共通の表 tests/fixtures/cost_estimate.json で結ぶ（拡張側は vscode/src/domain/costEstimate.test.ts）。
"""

from __future__ import annotations

import importlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TABLE = json.loads((ROOT / "tests" / "fixtures" / "cost_estimate.json").read_text(encoding="utf-8"))
TODAY = date(2026, 11, 2)


# ---- 補助：新しい部品 ------------------------------------------------------------------------------


def part(name: str):
    """pipe_in.usage.<name>（無ければ、無いことを理由に落とす）。"""
    try:
        return importlib.import_module(f"pipe_in.usage.{name}")
    except ModuleNotFoundError as e:
        pytest.fail(f"pipe_in.usage.{name} が無い（まだ作っていない）: {e}")


def stage(name="a", model="sonnet", max_turns=10, default_turns=100, max_budget_usd=None, max_retries=0):
    return part("estimate").StageInput(
        name=name,
        model=model,
        max_turns=max_turns,
        default_turns=default_turns,
        max_budget_usd=max_budget_usd,
        max_retries=max_retries,
    )


def run(stages, today=TODAY):
    return part("estimate").estimate(stages, today)


def per_turn(family: str) -> int:
    return part("prices").PRICES["per_turn"][family]


def only(est):
    (s,) = est.stages
    return s


def ceil_low_turns(t: int) -> int:
    return (t * 20 + 99) // 100


# ---- AC-01：少なめ < 多め、多めは上限ターン × 1 ターンの費用の合計 ------------------------------------------


def test_d0066_ac01_少なめは多めより小さく多めは上限ターン掛ける1ターンの合計():
    """D0066-AC-01: sonnet・ターン上限 40 と 100・やり直し 0 の 2 段で、少なめ < 多め。多めは各段「ターン上限 × 1 ターンの費用」の合計に等しい。
    少なめは各段 1 回だけ、ターン上限の 20% を使ったとして足した値。"""
    p = per_turn("sonnet")
    est = run([stage("a", max_turns=40), stage("b", max_turns=100)])
    assert est.low < est.high
    assert [s.high for s in est.stages] == [40 * p, 100 * p]
    assert est.high == 140 * p
    assert [s.low for s in est.stages] == [ceil_low_turns(40) * p, ceil_low_turns(100) * p]
    assert est.low == (ceil_low_turns(40) + ceil_low_turns(100)) * p


# ---- AC-02：費用の上限で 1 回分が頭打ち ------------------------------------------------------------------


def test_d0066_ac02_費用の上限があると1回分が頭打ちで多めは上限掛ける1足すやり直し以下():
    """D0066-AC-02: 段に max_budget_usd があると、その段の多めは 上限 ×（1 + やり直し回数）以下。上限が効く入力（上限 = 10 ターン分）では
    ちょうど 10 ターン分 × 3 になり、少なめも 1 回分の上限を超えない。上限が大きすぎて効かないときは、頭打ちにならない。"""
    p = per_turn("sonnet")
    budget = 10 * p / 10000  # ドル（10 ターン分）
    s = only(run([stage(max_turns=100, max_budget_usd=budget, max_retries=2)]))
    assert s.high <= budget * 10000 * 3 + 1e-6
    assert s.high == 10 * p * 3
    assert s.low == min(ceil_low_turns(100) * p, 10 * p)
    big = only(run([stage(max_turns=100, max_budget_usd=1000.0, max_retries=2)]))
    assert big.high == 100 * p * 3
    assert big.low == ceil_low_turns(100) * p


# ---- AC-03：やり直しの上限 ------------------------------------------------------------------------------


def test_d0066_ac03_やり直し3の多めはやり直し0の4倍():
    """D0066-AC-03: やり直しの上限が 3 のとき、多めはやり直し 0 のときの (1 + 3) 倍。少なめは 1 回分のままで変わらない。"""
    zero = only(run([stage(model="opus", max_turns=20, max_retries=0)]))
    three = only(run([stage(model="opus", max_turns=20, max_retries=3)]))
    assert three.high == zero.high * 4
    assert three.low == zero.low


# ---- AC-04：系統は名前の語で決まる ------------------------------------------------------------------------

FAMILIES = [
    ("claude-opus-4-1", "opus"),
    ("claude-sonnet-4-5", "sonnet"),
    ("claude-haiku-4-5", "haiku"),
    ("opus", "opus"),
    ("sonnet", "sonnet"),
    ("haiku", "haiku"),
    ("OPUS", "opus"),
    ("Claude-Haiku-4-5", "haiku"),
    ("Claude-SONNET-4", "sonnet"),
]


@pytest.mark.parametrize(("model", "family"), FAMILIES)
def test_d0066_ac04_系統は名前の語で決まり大文字小文字を区別しない(model, family):
    """D0066-AC-04: claude-opus-…・claude-sonnet-…・claude-haiku-…・エイリアス（opus・sonnet・haiku）で、系統ごとの 1 ターンの費用が使われる
    （大文字小文字は区別しない）。印（モデル不明）は付かず、family_of は（系統, 不明でない）を返す。"""
    assert part("prices").family_of(model) == (family, False)
    s = only(run([stage(model=model, max_turns=10)]))
    assert s.high == 10 * per_turn(family)
    assert "model_unknown" not in s.marks


# ---- AC-05：モデル不明は sonnet で計算して印 ---------------------------------------------------------------


@pytest.mark.parametrize("model", [None, "", "gpt-4", "本物のモデル", 5, ["opus"]], ids=["none", "empty", "gpt4", "japanese", "int", "list"])
def test_d0066_ac05_モデルなしと知らない名前はsonnetでモデル不明の印(model):
    """D0066-AC-05: モデルを書いていない（None・空）・知らない名前・文字列でない値の段は、sonnet で計算し、その段に model_unknown の印が付く
    （落ちない）。"""
    s = only(run([stage(model=model, max_turns=10)]))
    assert s.high == 10 * per_turn("sonnet")
    assert "model_unknown" in s.marks
    assert part("prices").family_of(model) == ("sonnet", True)


# ---- AC-06：ターン上限の既定と、読めない値 ----------------------------------------------------------------


@pytest.mark.parametrize("default", [40, 60, 100, 150])
def test_d0066_ac06_ターン上限なしは呼ぶ側の既定で計算し印は付かない(default):
    """D0066-AC-06: ターンの上限が None の段は、呼ぶ側が渡す既定（開発フローは DEFAULT_MAX_TURNS、パイプは 100）で計算する。印は付かない。"""
    s = only(run([stage(max_turns=None, default_turns=default)]))
    assert s.high == default * per_turn("sonnet")
    assert "turns_invalid" not in s.marks


@pytest.mark.parametrize("bad", [0, -1, -100, "50", "", True, False, 2.5, [], {}], ids=repr)
def test_d0066_ac06_0と負と文字列と真偽と小数は既定に戻して印(bad):
    """D0066-AC-06: ターンの上限が 0・負・文字列・真偽・小数などのときは、読み飛ばさず既定に戻して計算し、turns_invalid の印を付ける（落ちない）。"""
    s = only(run([stage(max_turns=bad, default_turns=40)]))
    assert s.high == 40 * per_turn("sonnet")
    assert "turns_invalid" in s.marks


# ---- AC-07：単価表の古さ ---------------------------------------------------------------------------------


def as_of_day() -> date:
    year, month = part("prices").PRICES["as_of"].split("-")
    return date(int(year), int(month), 1)


def test_d0066_ac07_単価表は180日を超えると古い印_180日ちょうどは出ない():
    """D0066-AC-07: as_of（その月の 1 日）が今日から 180 日より前なら stale が真で、表に「単価表が古いかもしれません」が出る。
    ちょうど 180 日は古くない（出ない）。今日は引数で渡す。"""
    assert part("estimate").STALE_DAYS == 180
    exact = as_of_day() + timedelta(days=180)
    fresh = run([stage()], exact)
    old = run([stage()], exact + timedelta(days=1))
    assert fresh.stale is False
    assert old.stale is True
    assert "単価表が古いかもしれません" not in part("estimate").format_table(fresh, None)
    assert "単価表が古いかもしれません" in part("estimate").format_table(old, None)


# ---- AC-08・09・16：実績 ---------------------------------------------------------------------------------


def summary(**costs: float) -> dict:
    return {"by_model": {k: {"tokens": {}, "cost_usd": v} for k, v in costs.items()}}


def test_d0066_ac08_usage_summaryの合計が実績():
    """D0066-AC-08: state.json に usage_summary があると、実績（by_model の cost_usd の合計）が出る。runs[] に別の値があっても usage_summary が先。"""
    actual = part("estimate").actual_usd
    assert actual({"usage_summary": summary(a=1.5, b=0.25)}) == pytest.approx(1.75)
    both = {"usage_summary": summary(a=2.0), "runs": [{"metrics": {"by_model": {"m": {"cost_usd": 9.0}}}}]}
    assert actual(both) == pytest.approx(2.0)


BAD_STATES = [
    None,
    42,
    "x",
    [],
    {},
    {"usage_summary": None},
    {"usage_summary": "x"},
    {"usage_summary": []},
    {"usage_summary": {}},
    {"usage_summary": {"by_model": []}},
    {"usage_summary": {"by_model": {}}},
    {"usage_summary": {"by_model": {"a": "x"}}},
    {"usage_summary": {"by_model": {"a": {"cost_usd": "x"}}}},
    {"usage_summary": {"by_model": {"a": {"cost_usd": None}}}},
]


@pytest.mark.parametrize("state", BAD_STATES, ids=repr)
def test_d0066_ac08_usage_summaryが無い_形が違うときは実績なしで例外を出さない(state):
    """D0066-AC-08: usage_summary が無い・形が違う（dict でない・by_model が dict でない・cost_usd が数でない）state は、実績なし（None）で、
    例外を出さない。state が dict でないもの（None・数・文字列・list）も同じ。"""
    assert part("estimate").actual_usd(state) is None


def test_d0066_ac09_usage_summaryが無くてもrunsの費用の合計が実績になる():
    """D0066-AC-09: usage_summary が無い記録でも、runs[] の各回の metrics（by_model の cost_usd）の合計が実績になる。
    同じ段を差し戻しで何度も流した回（複数の回）も全部足す（FR-04b）。"""
    runs = [
        {"stage": "a", "seq": 1, "metrics": {"by_model": {"claude-sonnet-4-5": {"tokens": {}, "cost_usd": 0.5}}}},
        {"stage": "a", "seq": 2, "metrics": {"by_model": {"claude-sonnet-4-5": {"tokens": {}, "cost_usd": 0.25}}}},
        {"stage": "b", "seq": 3, "metrics": {"by_model": {"claude-opus-4-1": {"tokens": {}, "cost_usd": 1.0}}}},
    ]
    assert part("estimate").actual_usd({"runs": runs}) == pytest.approx(1.75)


OLD_RUNS = [
    [{"stage": "a", "seq": 1, "cost_usd": 0.3}],
    [{"stage": "a"}, {"stage": "b", "metrics": None}, {"stage": "c", "metrics": {}}],
    [{"stage": "a", "metrics": "x"}, {"stage": "b", "metrics": {"by_model": "x"}}],
    ["x", 3, None],
    "runs",
    {"a": 1},
    None,
]


@pytest.mark.parametrize("runs", OLD_RUNS, ids=repr)
def test_d0066_ac16_runsにmetricsが無い古い記録でも落ちない(runs):
    """D0066-AC-16: runs[] の各回に metrics が無い・形が違う古い state.json（usage_summary も無い）を実績として読んでも、落ちない。
    返すのは None か数（読めた分があるとき）で、例外は出さない。"""
    got = part("estimate").actual_usd({"runs": runs})
    assert got is None or isinstance(got, float)


# ---- AC-15・17・18：共通の表 -----------------------------------------------------------------------------


def test_d0066_ac15_DISCLAIMERは共通の表の文と同じ():
    """D0066-AC-15: 本体の DISCLAIMER は、共通の表 tests/fixtures/cost_estimate.json の文と一字一句同じ（「約束するものではありません」を含む）。"""
    text = part("estimate").DISCLAIMER
    assert text == TABLE["disclaimer"]
    assert "約束するものではありません" in text


def inputs_of(case):
    return [
        stage(s["name"], s["model"], s["max_turns"], s["default_turns"], s["max_budget_usd"], s["max_retries"])
        for s in case["stages"]
    ]


@pytest.mark.parametrize("case", TABLE["cases"], ids=lambda c: c["memo"][:30])
def test_d0066_ac17_共通の表のケースと一致する(case):
    """D0066-AC-17: 共通の表の 1 件ずつ。段ごとと全体の少なめ・多め（units）・印・古さが、表の期待と同じ（拡張の costEstimate.ts も同じ表を読む）。"""
    est = run(inputs_of(case), date.fromisoformat(case["today"]))
    want = case["expect"]
    got = [{"name": s.name, "low": s.low, "high": s.high, "marks": sorted(s.marks)} for s in est.stages]
    assert got == [{**w, "marks": sorted(w["marks"])} for w in want["stages"]]
    assert (est.low, est.high, est.stale) == (want["low"], want["high"], want["stale"])


def test_d0066_ac18_PRICESは共通の表と同じ():
    """D0066-AC-18: 本体の単価表（系統・1 ターンの費用・as_of）が、共通の表と同じ（食い違うと落ちる）。表には「公式の価格表を見て手で直す」ことの注意がある。"""
    prices = part("prices").PRICES
    assert prices["as_of"] == TABLE["prices"]["as_of"]
    assert prices["per_turn"] == TABLE["prices"]["per_turn"]
    assert "公式の価格表" in prices["note"] and "手で" in prices["note"]
    assert part("estimate").LOW_PERCENT == 20
