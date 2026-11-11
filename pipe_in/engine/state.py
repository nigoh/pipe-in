"""記録（state.json）の土台を作る。"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 1


def new_state(
    driver: str | None,
    *,
    started_at: str,
    updated_at: str,
    pipe: str,
    stages: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    name: str | None = None,
    session_id: str | None = None,
    received_from: dict[str, Any] | None = None,
    final: str | None = None,
    pending_review: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    with_open: bool = False,
    unavailable_reason: str | None = None,
    total_cost_usd: float | None = None,
    usage_summary: dict[str, Any] | None = None,
    with_schema: bool = True,
) -> dict[str, Any]:
    """記録の土台（鍵の並びと、費用・使用量の2通り）を作る。書き手は、ここに段ごとの値を足して書く。

    費用と使用量は2通りだけ。unavailable_reason を渡せば「取れない」記録（費用は None、
    使用量は available が False の辞書）、渡さなければ total_cost_usd と usage_summary の両方が要る。
    driver が None なら driver の鍵は書かない（SDK の道）。with_schema を False にすると schema を書かない
    （schema の無い古い記録を続けるとき）。
    """
    if unavailable_reason is not None:
        if not unavailable_reason:
            raise ValueError("取れない理由は空にできません")
        if total_cost_usd is not None or usage_summary is not None:
            raise ValueError("取れない記録に、費用や使用量の集計は渡せません")
        cost: float | None = None
        summary: dict[str, Any] | None = {"available": False, "reason": unavailable_reason}
    else:
        if total_cost_usd is None or usage_summary is None:
            raise ValueError("測れた記録には total_cost_usd と usage_summary の両方が要ります")
        cost, summary = total_cost_usd, usage_summary
    state: dict[str, Any] = {}
    if with_schema:
        state["schema"] = SCHEMA_VERSION
    state |= {"started_at": started_at, "updated_at": updated_at, "pipe": pipe}
    if name is not None:
        state["name"] = name
    if session_id is not None:
        state["session_id"] = session_id
    if received_from is not None:
        state["received_from"] = received_from
    if driver is not None:
        state["driver"] = driver
    state |= {
        "stages": stages,
        "final": final,
        "total_cost_usd": cost,
        "usage_summary": summary,
        "pending_review": pending_review,
        "warnings": warnings if warnings is not None else [],
    }
    if with_open:
        state["open"] = None
    state["runs"] = runs
    return state
