"""記録の順序の検査（D0071）。人の承認（review approved）より前に、次の段の begin が書かれていないかを読む。

state.json と段のログ（logs/*.jsonl）を読むだけで、何も書かない。SDK も呼ばない。
どんな入力でも例外を投げない（読めないものは「判定できなかった」にする）。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..engine.pipeline import STATE

LOGS = "logs"
_FIRST_LINE_LIMIT = 1_000_000  # 最初の行を読む上限（文字数）


@dataclass(frozen=True)
class Violation:
    """違反：段 S の承認より前に、後ろの段 T が始まっている。"""

    stage: str
    next_stage: str
    seq: int | None = None
    log: str | None = None
    begin_at: str | None = None
    approved_at: str | None = None
    last_review: str | None = None


@dataclass(frozen=True)
class Undecided:
    """判定できなかったもの（時刻が無い・読めない・ずれの有無が合わない など）。"""

    stage: str | None
    next_stage: str | None
    reason: str = ""


@dataclass(frozen=True)
class PromptLine:
    """段のログの最初の行（Prompt 行）から取った値。"""

    log: str
    seq: int | None = None
    stage: str | None = None
    at: str | None = None


@dataclass(frozen=True)
class OrderReport:
    violations: tuple[Violation, ...] = ()
    undecided: tuple[Undecided, ...] = ()
    checked: int = 0


def _parse_at(value: Any) -> tuple[datetime | None, str]:
    """時刻の文字を読む。返すのは (読めた時刻 または None, None のときの理由)。"""
    if value is None:
        return None, "at がありません"
    if not isinstance(value, str):
        return None, "at が読めません"
    try:
        return datetime.fromisoformat(value), ""
    except ValueError:
        return None, "at が読めません"


def _stage_list(state: Any) -> list[tuple[str, bool]] | None:
    if not isinstance(state, Mapping):
        return None
    stages = state.get("stages")
    if not isinstance(stages, list):
        return None
    out: list[tuple[str, bool]] = []
    for s in stages:
        if isinstance(s, Mapping) and isinstance(s.get("name"), str):
            out.append((s["name"], s.get("review") is True))
    return out


def _reviews(state: Mapping[str, Any], stage: str) -> list[Mapping[str, Any]]:
    runs = state.get("runs")
    if not isinstance(runs, list):
        return []
    return [r for r in runs if isinstance(r, Mapping) and r.get("stage") == stage and isinstance(r.get("review"), str)]


def _sort_key(p: PromptLine) -> tuple[int, int, str]:
    return (0 if p.seq is not None else 1, p.seq if p.seq is not None else 0, p.log)


def check_order(state: Any, prompts: Sequence[PromptLine]) -> OrderReport:
    """確認のある段 S の承認より前に、後ろの段 T が始まっていないかを調べる。純粋で、例外を投げない。"""
    try:
        return _check_order(state, prompts)
    except Exception as e:  # 想定外の形でも落とさない
        return OrderReport((), (Undecided(None, None, f"記録を読めませんでした（{type(e).__name__}）"),), 0)


def _check_order(state: Any, prompts: Sequence[PromptLine]) -> OrderReport:
    stages = _stage_list(state)
    if stages is None:
        return OrderReport((), (Undecided(None, None, "stages が読めません"),), 0)
    violations: list[Violation] = []
    undecided: list[Undecided] = []
    checked = 0
    names = [n for n, _ in stages]
    for i, (s, reviewed) in enumerate(stages):
        if not reviewed or not any(p.stage == s for p in prompts):
            continue
        reviews = _reviews(state, s)
        approved = [r for r in reviews if r.get("review") == "approved"]
        last_review = reviews[-1]["review"] if reviews else None
        for t in names[i + 1 :]:
            for p in sorted((p for p in prompts if p.stage == t), key=_sort_key):
                checked += 1
                begin, why = _parse_at(p.at)
                if begin is None:
                    undecided.append(Undecided(s, t, f"{t} の begin の{why}（ログ {p.log}）"))
                    continue
                verdict = _judge(approved, begin)
                if verdict == "ok":
                    continue
                if isinstance(verdict, str):
                    undecided.append(Undecided(s, t, verdict))
                    continue
                violations.append(Violation(s, t, p.seq, p.log, p.at, verdict[0], last_review if verdict[0] is None else None))
    return OrderReport(tuple(violations), tuple(undecided), checked)


def _judge(approved: list[Mapping[str, Any]], begin: datetime) -> str | tuple[str | None]:
    """"ok" なら適合、str なら判定できなかった理由、タプルなら違反（承認の at または None）。"""
    first_comparable: str | None = None
    problem: str | None = None
    for r in approved:
        dt, why = _parse_at(r.get("at"))
        if dt is None:
            problem = problem or ("review に at がありません（古い記録）" if why == "at がありません" else f"review の{why}")
            continue
        if (dt.tzinfo is None) != (begin.tzinfo is None) or dt.tzinfo is None:
            problem = problem or "ずれの有無が合いません（時刻を比べられません）"
            continue
        if dt <= begin:
            return "ok"
        first_comparable = first_comparable or r.get("at")
    if problem is not None:
        return problem
    return (first_comparable,)


def _read_prompts(logs_dir: Path) -> tuple[list[PromptLine], list[Undecided]]:
    prompts: list[PromptLine] = []
    undecided: list[Undecided] = []
    try:
        files = sorted(p for p in logs_dir.glob("*.jsonl") if p.is_file())
    except OSError:
        return prompts, [Undecided(None, None, "logs を読めません")]
    for path in files:
        try:
            with path.open("r", encoding="utf-8") as f:
                first = json.loads(f.readline(_FIRST_LINE_LIMIT))
        except (OSError, ValueError):  # JSONDecodeError と UnicodeDecodeError は ValueError
            first = None
        if not isinstance(first, dict) or first.get("_type") != "Prompt" or not isinstance(first.get("stage"), str):
            undecided.append(Undecided(None, None, f"ログ {path.name} の最初の行が読めません"))
            continue
        m = re.match(r"(\d+)_", path.name)
        at = first.get("at")
        prompts.append(PromptLine(path.name, int(m.group(1)) if m else None, first["stage"], at if isinstance(at, str) else None))
    return prompts, undecided


def check_dir(work_dir: Path) -> OrderReport:
    """work_dir の state.json と logs/*.jsonl を読んで調べる。何も書かない。"""
    try:
        state = json.loads((Path(work_dir) / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return OrderReport((), (Undecided(None, None, f"{STATE} を読めません"),), 0)
    prompts, bad_logs = _read_prompts(Path(work_dir) / LOGS)
    report = check_order(state, prompts)
    return OrderReport(report.violations, report.undecided + tuple(bad_logs), report.checked)


def format_report(report: OrderReport, state: Any = None) -> tuple[str, int]:
    """画面に出す文と終了コード（違反があれば 1、なければ 0）。段の表示名は state の stages[].label から。"""
    labels: dict[str, str] = {}
    if isinstance(state, Mapping) and isinstance(state.get("stages"), list):
        for s in state["stages"]:
            if isinstance(s, Mapping) and isinstance(s.get("name"), str) and isinstance(s.get("label"), str):
                labels[s["name"]] = s["label"]

    def name(stage: str | None) -> str:
        if stage is None:
            return "（段不明）"
        return f"{labels[stage]}（{stage}）" if stage in labels else stage

    lines: list[str] = []
    if report.violations:
        lines.append(f"順序の違反: {len(report.violations)} 件")
        for v in report.violations:
            if v.approved_at is not None:
                approval = f"承認 {v.approved_at}"
            else:
                approval = "承認なし" + (f"（最後の確認: {v.last_review}）" if v.last_review else "")
            lines.append(
                f"- {name(v.stage)}の承認より前に、{name(v.next_stage)}が始まっています"
                f"（ログ {v.log}・順番 {v.seq}・始まり {v.begin_at}・{approval}）"
            )
    else:
        lines.append(f"順序は守られています（確認のある段 {report.checked} 組を確かめました）")
    if report.undecided:
        lines.append(f"判定できなかったもの: {len(report.undecided)} 件")
        for u in report.undecided:
            where = f"{name(u.stage)}→{name(u.next_stage)}：" if u.stage is not None else ""
            lines.append(f"- {where}{u.reason}")
    return "\n".join(lines), (1 if report.violations else 0)
