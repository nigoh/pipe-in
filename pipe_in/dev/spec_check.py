"""要件定義・設計・決定の記録の ID のつながりを数える（D0085）。

python -m pipe_in skill spec-check が、今のフォルダの docs/pipeline/ の 01 と 02 を読んで、
要求 → 機能要件・非機能要件 → 受け入れ基準 のつながりを調べる。読むだけで、書かない。標準ライブラリだけ。
読み方（行の形・ID の形・問題の種類）はこのファイルの定数と正規表現に閉じ込める。
決定の記録（tests/test_rules.py が check_record をかける）では、01 と 02 の内容が1つの文書にある。
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# 問題の種類（文字列がそのまま出力に出る）
UNCONNECTED = "つながらない"
UNPOINTED_UR = "指されない要求"
BAD_TARGET = "基準の指し先が違う"
NO_CRITERIA = "基準の無い要件"
OVERLAP = "重なり"
NO_TABLE = "状態遷移の表が無い"
TABLE_BUT_NO = "いいえ なのに表がある"
NO_ANSWER = "答えが無い"
EMPTY_CELL = "基準の無いマス"

LEGACY_NOTE = "前の形のため、鎖は検査しない"
KINDS = ("UR", "FR", "NFR", "DS", "AC")

# ID の形。半角だけ。前後に英数字が続くものは拾わない。
_ID = r"(?:UR-\d{2,}|FR-\d{2,}|NFR-\d{2,}|DS-\d{2,}|D\d{4}-AC-\d{2,3})"
_ANY_ID = re.compile(r"(?<![0-9A-Za-z])" + _ID + r"(?![0-9A-Za-z])", re.ASCII)
_AC_ID = re.compile(r"(?<![0-9A-Za-z])D\d{4}-AC-\d{2,3}(?![0-9A-Za-z])", re.ASCII)
# 定義の行：行頭の空白と `- ` か `* ` のあとに ID。直後に（…）の並びがあれば指し先。
_DEFINITION = re.compile(r"^\s*(?:[-*]\s+)+(" + _ID + r")(?![0-9A-Za-z])(.*)$", re.ASCII)
_REFS = re.compile(r"^\s*((?:[(（][^)）]*[)）]\s*)+)")
_ANSWER = re.compile(r"^\s*(?:[-*]\s+)?答え[：:]\s*(はい|いいえ)")
_NONE_WORD = re.compile(r"^[\s。.]*(?:無し|なし)[\s。.]*$")
_DS_CELL = re.compile(r"^DS-\d{2,}$", re.ASCII)


@dataclass(frozen=True)
class Problem:
    kind: str
    target: str
    detail: str


@dataclass(frozen=True)
class Report:
    counts: dict[str, int]
    problems: tuple[Problem, ...]
    legacy: bool
    answer: str | None


@dataclass
class _Parsed:
    # 種類 → {ID: 指し先の ID の並び}（定義の順）
    defs: dict[str, dict[str, list[str]]]
    duplicates: list[str]
    answer: str | None
    # DS の行：ID → そのマスに書いた AC の ID
    cells: dict[str, list[str]]


def _lines(text: str) -> Iterator[str]:
    """コードの囲み（``` と ~~~）の中を除いた行。"""
    fence: str | None = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if fence is None:
            if stripped.startswith(("```", "~~~")):
                fence = stripped[:3]
                continue
            yield raw
        elif stripped.startswith(fence):
            fence = None


def _kind_of(identifier: str) -> str:
    if identifier.startswith("UR-"):
        return "UR"
    if identifier.startswith("NFR-"):
        return "NFR"
    if identifier.startswith("FR-"):
        return "FR"
    if identifier.startswith("DS-"):
        return "DS"
    return "AC"


def _parse_text(text: str, *, with_cells: bool) -> _Parsed:
    parsed = _Parsed(defs={k: {} for k in KINDS}, duplicates=[], answer=None, cells={})
    for line in _lines(text):
        if parsed.answer is None:
            found = _ANSWER.match(line)
            if found:
                parsed.answer = found.group(1)
        match = _DEFINITION.match(line)
        if match:
            identifier, rest = match.group(1), match.group(2)
            kind = _kind_of(identifier)
            if kind == "NFR" and _NONE_WORD.match(rest):
                continue
            refs: list[str] = []
            ref_match = _REFS.match(rest)
            if ref_match:
                refs = _ANY_ID.findall(ref_match.group(1))
            bucket = parsed.defs[kind]
            if identifier in bucket:
                if identifier not in parsed.duplicates:
                    parsed.duplicates.append(identifier)
                bucket[identifier] = bucket[identifier] + refs
            else:
                bucket[identifier] = refs
            continue
        if with_cells and line.lstrip().startswith("|"):
            first = line.strip().strip("|").split("|")[0].strip()
            if _DS_CELL.match(first):
                if first in parsed.cells and first not in parsed.duplicates:
                    parsed.duplicates.append(first)
                parsed.cells[first] = parsed.cells.get(first, []) + _AC_ID.findall(line)
    return parsed


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def check(requirements: str, design: str | None = None) -> Report:
    req = _parse_text(requirements, with_cells=False)
    if design is not None:
        cells = _parse_text(design, with_cells=True)
        ds_ids = list(cells.cells)
        duplicates = _unique(req.duplicates + cells.duplicates)
        cell_acs = cells.cells
    else:
        ds_ids = []
        duplicates = list(req.duplicates)
        cell_acs = {}
    urs, frs, nfrs, acs = req.defs["UR"], req.defs["FR"], req.defs["NFR"], req.defs["AC"]
    counts = {"UR": len(urs), "FR": len(frs), "NFR": len(nfrs), "DS": len(ds_ids), "AC": len(acs)}
    answer = req.answer
    if not urs:
        return Report(counts=counts, problems=(), legacy=True, answer=answer)

    problems: list[Problem] = []

    for identifier in duplicates:
        problems.append(Problem(OVERLAP, identifier, "同じ ID を2回以上定義している"))

    # 要件 → 要求
    for kind, bucket in (("FR", frs), ("NFR", nfrs)):
        for identifier, refs in bucket.items():
            ur_refs = [r for r in refs if r.startswith("UR-")]
            if not ur_refs:
                problems.append(Problem(UNCONNECTED, identifier, f"{kind} がどの要求（UR）も指していない"))
            elif any(r not in urs for r in ur_refs):
                problems.append(Problem(UNCONNECTED, identifier, "要件定義に無い要求を指している"))
            elif any(not r.startswith("UR-") for r in refs):
                problems.append(Problem(UNCONNECTED, identifier, "要求（UR）以外の ID を指している"))

    pointed_urs = {r for refs in list(frs.values()) + list(nfrs.values()) for r in refs}
    for identifier in urs:
        if identifier not in pointed_urs:
            problems.append(Problem(UNPOINTED_UR, identifier, "どの FR・NFR からも指されていない"))

    # 基準 → 要件・状態
    check_ds = design is not None and bool(ds_ids)
    ac_pointed: set[str] = set()
    for identifier, refs in acs.items():
        ac_pointed.update(refs)
        if not refs:
            problems.append(Problem(BAD_TARGET, identifier, "指し先（FR・NFR・DS）が無い"))
            continue
        bad = []
        for r in refs:
            kind = _kind_of(r)
            if kind in ("FR", "NFR"):
                ok = r in req.defs[kind]
            elif kind == "DS":
                ok = r in ds_ids if check_ds else True
            else:
                ok = False
            if not ok:
                bad.append(r)
        if bad:
            problems.append(Problem(BAD_TARGET, identifier, f"定義の無い、または指してはいけない ID を指している（{'・'.join(bad)}）"))

    for kind, bucket in (("FR", frs), ("NFR", nfrs)):
        for identifier in bucket:
            if identifier not in ac_pointed:
                problems.append(Problem(NO_CRITERIA, identifier, f"どの受け入れ基準からも指されていない {kind}"))

    # 状態の問い
    if answer is None:
        problems.append(Problem(NO_ANSWER, "", "状態の問い（答え：はい／いいえ）に答えていない"))
    if design is not None:
        if answer == "はい" and not ds_ids:
            problems.append(Problem(NO_TABLE, "", "答えは はい だが、設計に状態遷移の表（DS の行）が無い"))
        if answer == "いいえ" and ds_ids:
            problems.append(Problem(TABLE_BUT_NO, "", "答えは いいえ だが、設計に DS の行がある"))
        if answer != "いいえ":
            reported: set[str] = set()
            for identifier, row_acs in cell_acs.items():
                for a in row_acs:
                    if a not in acs and a not in reported:
                        reported.add(a)
                        problems.append(Problem(BAD_TARGET, a, f"{identifier} の行に書いた基準が要件定義に無い"))
                if not row_acs and identifier not in ac_pointed:
                    problems.append(Problem(EMPTY_CELL, identifier, "行にも受け入れ基準の（…）にも、このマスの基準が無い"))

    return Report(counts=counts, problems=tuple(problems), legacy=False, answer=answer)


def check_record(text: str) -> Report:
    return check(text, text)


def exit_code(report: Report) -> int:
    return 1 if report.problems else 0


def format_report(report: Report) -> list[str]:
    lines = ["・".join(f"{kind} {report.counts.get(kind, 0)}" for kind in KINDS)]
    if report.legacy:
        lines.append(LEGACY_NOTE)
    for p in report.problems:
        lines.append(f"{p.kind}：{p.target}　{p.detail}" if p.target else f"{p.kind}：{p.detail}")
    total = len(report.problems)
    if total:
        per_kind: dict[str, int] = {}
        for p in report.problems:
            per_kind[p.kind] = per_kind.get(p.kind, 0) + 1
        ordered = sorted(per_kind.items(), key=lambda item: -item[1])
        lines.append(f"問題 {total} 件（{'・'.join(f'{k} {n}' for k, n in ordered)}）")
    else:
        lines.append("問題 0 件")
    return lines


def _parse(argv: list[str]) -> argparse.Namespace:
    if argv:
        raise SystemExit(
            "pipe-in skill: spec-check は旗も引数も取りません（今のフォルダの docs/pipeline/ を読むだけです）"
        )
    return argparse.Namespace()


def run(args: argparse.Namespace) -> int:
    base = Path("docs") / "pipeline"
    req_path = base / "01_requirements.md"
    if not req_path.is_file():
        print("01 が無い。要件定義の段のあとで流す（docs/pipeline/01_requirements.md を読む）")
        return 1
    design_path = base / "02_design.md"
    design = design_path.read_text(encoding="utf-8") if design_path.is_file() else None
    report = check(req_path.read_text(encoding="utf-8"), design)
    for line in format_report(report):
        print(line)
    return exit_code(report)
