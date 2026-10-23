"""段の検証の審査（[stages.check.judge]）：審査役の点と must から、合否をエンジンが計算する。

審査役（LLM）には理由と点・must の違反だけを返させ、平均・丸め・合否はここで決まった計算で出す。
標準ライブラリだけを使う（definition.py などを読み込まない。値だけを受け取る）。
決まりは generator/judge_score.py と同じ：点は Fraction で足し、丸めは四捨五入（float の round は使わない）、
合否は丸めた平均としきい値を比べる。must が違反か確かめられなかったとき（null）は、安全側に倒して fail にする。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

DEFAULT_THRESHOLD = Fraction(7, 10)
LEVELS = (Fraction(0), Fraction(1, 4), Fraction(1, 2), Fraction(3, 4), Fraction(1))
INVALID_HEAD = "審査役の返りが決まりに合いませんでした"
_LEVEL_TEXT = "0.0・0.25・0.5・0.75・1.0 か null"


@dataclass(frozen=True)
class JudgeOutcome:
    """審査の結果。"""

    status: str  # "pass" | "fail"
    valid: bool  # False = 返りが決まりに合わない
    overall: float | None  # 小数2桁に丸めた平均。採点できなければ None
    threshold: float
    scores: dict[str, float | None]  # 項目名 → 点（valid=False のときは空）
    must: dict[str, dict]  # must名 → {"violated": bool|None, "evidence": str}
    problems: list[str]  # 不合格のときの直す点

    def to_record(self) -> dict:
        """state.json の check.judge に入れる形（理由は記録しない）。"""
        return {
            "status": self.status,
            "overall": self.overall,
            "threshold": self.threshold,
            "scores": dict(self.scores),
            "must": {k: dict(v) for k, v in self.must.items()},
            "valid": self.valid,
        }


def _round2(value: Fraction) -> Fraction:
    """小数 2 桁に四捨五入する（0.625 は 0.63）。"""
    return Fraction(math.floor(value * 100 + Fraction(1, 2)), 100)


def _threshold(value: Any) -> Fraction:
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        return DEFAULT_THRESHOLD


def _invalid(threshold: Fraction, details: list[str]) -> JudgeOutcome:
    return JudgeOutcome(
        status="fail",
        valid=False,
        overall=None,
        threshold=float(threshold),
        scores={},
        must={},
        problems=[INVALID_HEAD, *details],
    )


def _level(value: Any) -> tuple[Fraction | None, bool]:
    """点を (値, 正しいか) で返す。null は (None, True)。"""
    if value is None:
        return None, True
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, False
    try:
        f = Fraction(value)
    except (ValueError, OverflowError):
        return None, False
    return (f, True) if f in LEVELS else (None, False)


def _names_problems(kind: str, got: dict, expected: Sequence[str]) -> list[str]:
    out = [f"{kind}「{n}」がありません" for n in expected if n not in got]
    out += [f"{kind}「{n}」は定義にない名前です" for n in got if n not in expected]
    return out


def _fmt(value: float | Fraction) -> str:
    return repr(float(value))


def evaluate(data: object, criteria: Sequence[str], must: Sequence[str], threshold: float = 0.7) -> JudgeOutcome:
    """審査役の返り（judge の値）から合否を出す。例外は投げない。"""
    th = _threshold(threshold)
    if not isinstance(data, dict):
        return _invalid(th, ["judge（criteria と must を持つ表）が返りませんでした"])
    raw_c, raw_m = data.get("criteria"), data.get("must")
    details: list[str] = []
    if not isinstance(raw_c, dict):
        details.append("criteria が表ではありません")
    if not isinstance(raw_m, dict):
        details.append("must が表ではありません")
    if details:
        return _invalid(th, details)

    details += _names_problems("項目", raw_c, criteria)
    details += _names_problems("must", raw_m, must)

    levels: dict[str, Fraction | None] = {}
    reasons: dict[str, str] = {}
    for name in criteria:
        item = raw_c.get(name)
        if name not in raw_c:
            continue
        if not isinstance(item, dict):
            details.append(f"項目「{name}」が表ではありません")
            continue
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            details.append(f"項目「{name}」に理由（reason）がありません（点の前に理由を書きます）")
        else:
            reasons[name] = reason.strip()
        level, ok = _level(item.get("score"))
        if "score" not in item:
            details.append(f"項目「{name}」に点（score）がありません")
        elif not ok:
            details.append(f"項目「{name}」の点（score）は {_LEVEL_TEXT} だけです（{item.get('score')!r}）")
        else:
            levels[name] = level

    musts: dict[str, dict] = {}
    for name in must:
        item = raw_m.get(name)
        if name not in raw_m:
            continue
        if not isinstance(item, dict):
            details.append(f"must「{name}」が表ではありません")
            continue
        violated, evidence = item.get("violated"), item.get("evidence")
        bad = False
        if "violated" not in item:
            details.append(f"must「{name}」に violated がありません")
            bad = True
        elif violated is not None and not isinstance(violated, bool):
            details.append(f"must「{name}」の violated は true・false・null のどれかです")
            bad = True
        if not isinstance(evidence, str):
            details.append(f"must「{name}」の evidence は文字列です")
            bad = True
        elif violated is True and not evidence.strip():
            details.append(f"must「{name}」は違反なのに根拠（evidence）がありません")
            bad = True
        if not bad:
            musts[name] = {"violated": violated, "evidence": evidence}

    if details:
        return _invalid(th, details)

    # 点は Fraction で足し、平均を四捨五入する
    given = [v for v in levels.values() if v is not None]
    overall = _round2(sum(given, Fraction(0)) / len(given)) if given else None

    problems: list[str] = []
    bad_must = False
    for name, m in musts.items():
        if m["violated"] is True:
            bad_must = True
            problems.append(f"must「{name}」の違反：{m['evidence'].strip()}")
        elif m["violated"] is None:
            bad_must = True
            problems.append(f"must「{name}」を確かめられませんでした：{m['evidence'].strip() or '根拠なし'}")
    if overall is None:
        problems.append("採点できた項目がありません")
    elif overall < th:
        problems.append(f"審査の平均 {_fmt(overall)} がしきい値 {_fmt(th)} に届きませんでした")
        low = sorted((n for n, v in levels.items() if v is not None and v < 1), key=lambda n: (levels[n], criteria.index(n)))
        problems += [f"項目「{n}」（{_fmt(levels[n])}）：{reasons[n]}" for n in low]  # type: ignore[arg-type]

    passed = not bad_must and overall is not None and overall >= th
    return JudgeOutcome(
        status="pass" if passed else "fail",
        valid=True,
        overall=None if overall is None else float(overall),
        threshold=float(th),
        scores={n: (None if v is None else float(v)) for n, v in levels.items()},
        must=musts,
        problems=[] if passed else problems,
    )


def judge_schema(criteria: Sequence[Any], must: Sequence[Any]) -> dict:
    """構造化出力のスキーマの judge 部分。点の理由を先に書かせるため、reason を score より前に置く。

    criteria と must は name を持つ項目（definition.JudgeItem など）。
    """
    crit = {
        i.name: {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "点の理由（先に書く）"},
                "score": {"enum": [0.0, 0.25, 0.5, 0.75, 1.0, None], "description": "確かめられないときは null"},
            },
            "required": ["reason", "score"],
            "additionalProperties": False,
        }
        for i in criteria
    }
    musts = {
        i.name: {
            "type": "object",
            "properties": {
                "violated": {"type": ["boolean", "null"], "description": "違反なら true、違反でなければ false、確かめられなければ null"},
                "evidence": {"type": "string", "description": "違反の根拠（違反でないときは短くてよい）"},
            },
            "required": ["violated", "evidence"],
            "additionalProperties": False,
        }
        for i in must
    }
    return {
        "type": "object",
        "properties": {
            "criteria": {"type": "object", "properties": crit, "required": list(crit), "additionalProperties": False},
            "must": {"type": "object", "properties": musts, "required": list(musts), "additionalProperties": False},
        },
        "required": ["criteria", "must"],
    }
