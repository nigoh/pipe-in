"""ページから送られる答えの文（承認・差し戻し・中止）を作る・読む。空の形（実装の段で中身を書く）。"""

from __future__ import annotations

from typing import Any, NamedTuple


class ParseResult(NamedTuple):
    ok: bool
    action: str | None
    stage: str | None
    id: str | None
    feedback: str | None
    reason: str | None


def build_answer(action: Any, stage: Any, id: Any, feedback: Any = None) -> str:
    return ""


def parse_answer(text: Any) -> ParseResult:
    return ParseResult(False, None, None, None, None, None)


def review_id(stage: Any, since: Any) -> str | None:
    return None


def valid_stage(stage: Any) -> bool:
    return False


def check_answer(state: Any, stage: Any, answer_id: Any) -> str | None:
    return None


def format_result(ok: Any, action: Any, stage: Any, id: Any, reason: Any) -> str:
    return ""
