"""プラグインの審査の計算（pipe-in-gen judge-score）：審査役の採点から総合点・合否・ばらつきを出す。

審査役（LLM）には点と理由だけを返させ、平均・丸め・合否・ばらつきはここで決まった計算で出す。
標準ライブラリだけを使う（本体や SDK を読み込まない）。点は Fraction で足し、丸めは四捨五入（float の round は使わない）。
合否は丸めた総合点と 0.7 を比べる（見える数字と合否がずれないように）。
must が確かめられなかったとき（violated が null）は、安全側に倒して fail にし、must_unchecked に載せる。
"""

from __future__ import annotations

import json
import math
import sys
from fractions import Fraction
from typing import Any

THRESHOLD = Fraction(7, 10)
LEVELS = (Fraction(0), Fraction(1, 4), Fraction(1, 2), Fraction(3, 4), Fraction(1))
MIN_RUNS = 1
MAX_RUNS = 5


def _round2(value: Fraction) -> Fraction:
    """小数 2 桁に四捨五入する（0.625 は 0.63）。"""
    return Fraction(math.floor(value * 100 + Fraction(1, 2)), 100)


def _num(value: Fraction | None) -> float | None:
    return None if value is None else float(value)


def _mean(values: list[Fraction]) -> Fraction | None:
    return _round2(sum(values, Fraction(0)) / len(values)) if values else None


def _verdict(overall: Fraction | None, bad_must: bool) -> str:
    if bad_must or overall is None:
        return "fail"
    return "pass" if overall >= THRESHOLD else "fail"


def _as_level(value: Any, where: str) -> Fraction | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}: 点は 0.0・0.25・0.5・0.75・1.0 か null だけです（{value!r}）")
    f = Fraction(value)
    if f not in LEVELS:
        raise ValueError(f"{where}: 点は 0.0・0.25・0.5・0.75・1.0 か null だけです（{value!r}）")
    return f


def _check_run(run: Any, index: int) -> tuple[dict[str, Fraction | None], dict[str, dict[str, Any]]]:
    where = f"runs[{index}]"
    if not isinstance(run, dict):
        raise ValueError(f"{where} は辞書ではありません")
    reasons, scores, must = run.get("reasons"), run.get("scores"), run.get("must")
    if not isinstance(reasons, dict) or not isinstance(scores, dict) or not isinstance(must, dict):
        raise ValueError(f"{where} には reasons・scores・must（どれも辞書）が要ります")
    levels: dict[str, Fraction | None] = {}
    for name, value in scores.items():
        levels[name] = _as_level(value, f"{where}.scores[{name}]")
        reason = reasons.get(name)
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"{where}: 「{name}」に理由がありません（点の前に理由を書きます）")
    for name, item in must.items():
        if not isinstance(item, dict):
            raise ValueError(f"{where}.must[{name}] は辞書ではありません")
        violated, evidence = item.get("violated"), item.get("evidence")
        if violated is not None and not isinstance(violated, bool):
            raise ValueError(f"{where}.must[{name}].violated は true・false・null のどれかです")
        if evidence is not None and not isinstance(evidence, str):
            raise ValueError(f"{where}.must[{name}].evidence は文字列です")
        if violated is True and not (evidence or "").strip():
            raise ValueError(f"{where}.must[{name}]: 違反には根拠（evidence）が要ります")
    return levels, must


def _check_rubric(rubric: Any) -> tuple[set[str], set[str]]:
    if not isinstance(rubric, list):
        raise ValueError("rubric は配列です")
    scored: set[str] = set()
    musts: set[str] = set()
    for i, item in enumerate(rubric):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("must"), bool):
            raise ValueError(f"rubric[{i}] は {{name, must}} の形です")
        (musts if item["must"] else scored).add(item["name"])
    return scored, musts


def score(payload: dict[str, Any]) -> dict[str, Any]:
    """審査役の採点（1回か複数回）から結果の JSON を作る。入力が正しくなければ ValueError。"""
    if not isinstance(payload, dict):
        raise ValueError("入力は JSON の辞書で渡してください")
    runs = payload.get("runs")
    if not isinstance(runs, list):
        raise ValueError("runs は配列です")
    if not MIN_RUNS <= len(runs) <= MAX_RUNS:
        raise ValueError(f"runs は {MIN_RUNS}〜{MAX_RUNS} 件です（{len(runs)} 件）")

    checked = [_check_run(run, i) for i, run in enumerate(runs)]
    first_scores, first_must = checked[0]
    for i, (levels, must) in enumerate(checked):
        if set(levels) != set(first_scores):
            raise ValueError(f"runs[{i}] の採点項目の名前が、最初の回と合いません")
        if set(must) != set(first_must):
            raise ValueError(f"runs[{i}] の must の名前が、最初の回と合いません")
    if "rubric" in payload and payload["rubric"] is not None:
        scored, musts = _check_rubric(payload["rubric"])
        if set(first_scores) != scored:
            raise ValueError("採点項目の名前が rubric と合いません")
        if set(first_must) != musts:
            raise ValueError("must の名前が rubric と合いません")

    out_runs: list[dict[str, Any]] = []
    overalls: list[Fraction | None] = []
    verdicts: list[str] = []
    violations: list[dict[str, Any]] = []
    unchecked: list[str] = []
    for i, (run, (levels, must)) in enumerate(zip(runs, checked)):
        overall = _mean([v for v in levels.values() if v is not None])
        bad = False
        for name, item in must.items():
            if item.get("violated") is True:
                bad = True
                entry = {"name": name, "evidence": item["evidence"]}
                violations.append({"run": i + 1, **entry} if len(runs) > 1 else entry)
            elif item.get("violated") is None:
                bad = True
                if name not in unchecked:
                    unchecked.append(name)
        verdict = _verdict(overall, bad)
        overalls.append(overall)
        verdicts.append(verdict)
        out_runs.append(
            {
                "reasons": dict(run["reasons"]),
                "scores": {k: _num(v) for k, v in levels.items()},
                "must": {k: dict(v) for k, v in must.items()},
                "overall": _num(overall),
                "verdict": verdict,
            }
        )

    item_scores: dict[str, float | None] = {}
    for name in first_scores:
        item_scores[name] = _num(_mean([lv[name] for lv, _ in checked if lv[name] is not None]))
    usable = [o for o in overalls if o is not None]
    overall = _mean(usable)
    result: dict[str, Any] = {
        "runs": out_runs,
        "scores": item_scores,
        "must_violations": violations,
        "must_unchecked": unchecked,
        "overall": _num(overall),
        "threshold": float(THRESHOLD),
        "verdict": _verdict(overall, bool(violations or unchecked)),
    }
    if len(runs) >= 2:
        majority = max(verdicts.count("pass"), verdicts.count("fail"))
        result["variance"] = {
            "verdict_disagreement": float(_round2(Fraction(len(verdicts) - majority, len(verdicts)))),
            "overall_range": _num(max(usable) - min(usable)) if len(usable) >= 2 else None,
        }
    return result


def _read_stdin() -> str:
    # Windows でも UTF-8 のまま読む
    buffer = getattr(sys.stdin, "buffer", None)
    return buffer.read().decode("utf-8") if buffer is not None else sys.stdin.read()


def main() -> int:
    """標準入力の JSON を読み、結果の JSON を標準出力に出す。不正な入力は理由を標準エラーに出して終了コード 2。"""
    try:
        payload = json.loads(_read_stdin())
        result = score(payload)
    except (ValueError, UnicodeDecodeError) as e:  # json.JSONDecodeError は ValueError の仲間
        sys.stderr.write(f"judge-score: 入力を受け取れません: {e}\n")
        return 2
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError, OSError):
        pass
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0
