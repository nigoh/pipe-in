"""流す前の費用の目安を計算する（D0066）。ファイル・SDK・時計に触れない純粋な関数だけ（今日は引数で受ける）。

計算の決まり（単位は units = 1/10000 ドル。整数で計算し、最後にドルへ直す。拡張の costEstimate.ts と同じ式）：
- 少なめ ＝ 各段を1回だけ、ターンの上限の 20% を使ったとして足す（ターン数は切り上げ）。
- 多め ＝ やり直しの上限まで繰り返し、毎回ターンの上限まで使ったとして足す。
- 1ターンの費用は、モデルの系統ごとの表（prices.py）から引く。
- 段の費用の上限（max_budget_usd）があれば、1回分をそれで頭打ちにする（少なめにも掛ける）。
- 多めは厳密な上限ではなく、目安（差し戻しで別の段が流れ直す分などは足さない）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .prices import PRICES, family_of

DISCLAIMER = (
    "目安です。実際の費用は、会話の長さ・ツールの使い方・キャッシュで変わり、これより多くなることも少なくなることもあります。"
    "約束するものではありません。サブスクリプションでログインしている場合、請求額とは一致しません。"
)
STALE_DAYS = 180  # 単価表の as_of がこれより前なら「古いかもしれません」
LOW_PERCENT = 20  # 少なめ：ターンの上限のこの割合
UNITS_PER_USD = 10000

MARK_MODEL_UNKNOWN = "model_unknown"
MARK_TURNS_INVALID = "turns_invalid"
MARK_TEXT = {
    MARK_MODEL_UNKNOWN: "モデル不明（sonnet として計算）",
    MARK_TURNS_INVALID: "ターンの上限が読めないため既定で計算",
}
STALE_TEXT = "単価表が古いかもしれません"


@dataclass
class StageInput:
    """目安の入力の1段。max_turns・model などは、読んだままの値（形が悪くても受け付けて、印を付ける）。"""

    name: str
    model: Any
    max_turns: Any
    default_turns: int
    max_budget_usd: Any
    max_retries: Any


@dataclass
class StageEstimate:
    name: str
    low: int
    high: int
    marks: list[str] = field(default_factory=list)


@dataclass
class Estimate:
    stages: list[StageEstimate]
    low: int
    high: int
    stale: bool


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _turns(raw: Any, default: int) -> tuple[int, bool]:
    """（ターンの上限, 読めなかったか）。None は既定（印なし）。正の整数でないものは既定に戻して印。"""
    if raw is None:
        return default, False
    if _is_int(raw) and raw > 0:
        return raw, False
    return default, True


def _cap_units(budget: Any) -> int | None:
    """費用の上限（ドル）を units にする（四捨五入は 0.5 を切り上げ）。正の有限な数でなければ None。"""
    if isinstance(budget, bool) or not isinstance(budget, (int, float)):
        return None
    if not math.isfinite(budget) or budget <= 0:
        return None
    return math.floor(budget * UNITS_PER_USD + 0.5)


def _retries(raw: Any) -> int:
    return raw if _is_int(raw) and raw >= 0 else 0


def _is_stale(today: date) -> bool:
    year, month = PRICES["as_of"].split("-")
    return (today - date(int(year), int(month), 1)).days > STALE_DAYS


def estimate(stages: list[StageInput], today: date) -> Estimate:
    """段のリストから、段ごとと全体の少なめ・多め（units）を出す。"""
    out: list[StageEstimate] = []
    for s in stages:
        family, unknown = family_of(s.model)
        turns, invalid = _turns(s.max_turns, s.default_turns)
        per_turn = PRICES["per_turn"][family]
        once_low = ((turns * LOW_PERCENT + 99) // 100) * per_turn
        once_high = turns * per_turn
        cap = _cap_units(s.max_budget_usd)
        if cap is not None:
            once_low = min(once_low, cap)
            once_high = min(once_high, cap)
        marks = [m for m, on in ((MARK_MODEL_UNKNOWN, unknown), (MARK_TURNS_INVALID, invalid)) if on]
        out.append(StageEstimate(s.name, once_low, once_high * (1 + _retries(s.max_retries)), marks))
    return Estimate(out, sum(s.low for s in out), sum(s.high for s in out), _is_stale(today))


# ---- 実績（前に流した記録）-----------------------------------------------------------------------------------


def _cost(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _sum_by_model(by_model: Any) -> float | None:
    """by_model の cost_usd（数のもの）の合計。数が1つも無ければ None。"""
    if not isinstance(by_model, dict):
        return None
    costs = [c for c in (_cost(mu.get("cost_usd")) for mu in by_model.values() if isinstance(mu, dict)) if c is not None]
    return sum(costs) if costs else None


def actual_usd(state: Any) -> float | None:
    """state.json（読んだ dict）から、前の実績の合計（ドル）を出す。読めなければ None（例外は出さない）。

    1. usage_summary.by_model の cost_usd の合計。
    2. 無ければ、runs[] の各回の metrics.by_model の cost_usd の合計（古い記録）。
    """
    if not isinstance(state, dict):
        return None
    summary = state.get("usage_summary")
    if isinstance(summary, dict):
        total = _sum_by_model(summary.get("by_model"))
        if total is not None:
            return total
    runs = state.get("runs")
    if not isinstance(runs, list):
        return None
    parts = [
        c
        for c in (_sum_by_model(r["metrics"].get("by_model")) for r in runs if isinstance(r, dict) and isinstance(r.get("metrics"), dict))
        if c is not None
    ]
    return sum(parts) if parts else None


# ---- 文字にする --------------------------------------------------------------------------------------------


def usd(units: float) -> str:
    """units（1/10000 ドル）を「$1.40」のように書く（小数は 2〜4 桁。末尾の 0 は 2 桁まで落とす）。"""
    text = f"{units / UNITS_PER_USD:.4f}"
    while text.endswith("0") and len(text.split(".")[1]) > 2:
        text = text[:-1]
    return "$" + text


def usd_dollars(value: float) -> str:
    return usd(value * UNITS_PER_USD)


def _range(low: int, high: int) -> str:
    return f"{usd(low)}〜{usd(high)}"


def format_line(est: Estimate, actual: float | None) -> str:
    """本流の確認前に出す 2 行（1 行目は幅、2 行目は DISCLAIMER）。"""
    head = f"費用の目安：{len(est.stages)} 段で {_range(est.low, est.high)}"
    if actual is not None:
        head += f"（前の実績 {usd_dollars(actual)}）"
    head += "。内訳は pipe-in estimate"
    if est.stale:
        head += f"（{STALE_TEXT}）"
    return head + "\n" + DISCLAIMER


def format_table(est: Estimate, actual: float | None) -> str:
    """段ごとの内訳と全体の幅（pipe-in estimate の出力）。実績があれば別の欄に出す。"""
    lines = ["費用の目安（流す前の見積もり）", ""]
    for s in est.stages:
        note = "".join(f"  ※{MARK_TEXT[m]}" for m in s.marks)
        lines.append(f"  {s.name}：少なめ {usd(s.low)} 〜 多め {usd(s.high)}{note}")
    lines += ["", f"全体：少なめ {usd(est.low)} 〜 多め {usd(est.high)}"]
    if actual is not None:
        lines.append(f"前の実績：{usd_dollars(actual)}（目安には混ぜていません）")
    if est.stale:
        lines.append(f"※{STALE_TEXT}（単価表の as_of：{PRICES['as_of']}）")
    lines += ["", DISCLAIMER]
    return "\n".join(lines)
