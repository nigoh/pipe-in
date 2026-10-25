"""D0027（進み具合の写し）のテストが共有する補助。記録の組み立てだけ（テストの補助で、本体には入らない）。

state.json の辞書は、本体と同じ形（pipe_in/dev/record.py が書くもの）で組む。
壊れた記録は、このうちの1つを書き換えて作る（リポジトリの実物には触れない）。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pipe_in.dev.record import Recorder
from pipe_in.engine.config import load_config

JST = timezone(timedelta(hours=9))
UTC = timezone.utc
NOW = datetime(2026, 10, 17, 12, 0, 0, tzinfo=UTC)
STAGES = ("requirements", "design", "red", "implement", "test")
LABELS = {"requirements": "要件定義", "design": "設計", "red": "テスト先行", "implement": "実装", "test": "検証"}
KEYS = ["schema", "generated_at", "empty", "name", "final", "stages", "review"]
STAGE_KEYS = [
    "name", "label", "status", "attempt", "started_at", "pending_since", "verdict", "cost_usd", "turns", "duration_sec",
]


def stage_entry(name: str, label: str | None = None) -> dict[str, Any]:
    return {"name": name, "label": label if label is not None else LABELS.get(name, name), "output": f"{name}.md", "review": False}


def base_state(**over: Any) -> dict[str, Any]:
    """開発フローの、始めたばかりの記録（本体が書くキーを全部持つ）。"""
    state: dict[str, Any] = {
        "started_at": "2026-10-17T10:00:00",
        "updated_at": "2026-10-17T10:00:00",
        "pipe": "dev",
        "name": "テスト用のセッション",
        "driver": "pipe-dev",
        "stages": [stage_entry(n) for n in STAGES],
        "final": None,
        "total_cost_usd": 0.0,
        "usage_summary": None,
        "pending_review": None,
        "warnings": [],
        "open": None,
        "runs": [],
    }
    state.update(over)
    return state


def run(stage: str, *, seq: int = 1, attempt: Any = None, is_error: Any = False, cost: Any = 0.0, turns: Any = 0,
        duration: Any = 0.0, **extra: Any) -> dict[str, Any]:
    """段の実行（seq を持つ）。"""
    r = {
        "stage": stage, "session_id": None, "is_error": is_error, "subtype": "error" if is_error is True else "success",
        "result": None, "cost_usd": cost, "num_turns": turns, "duration_sec": duration, "denials": [], "errors": [],
        "metrics": {}, "seq": seq, "attempt": attempt, "note": "",
    }
    r.update(extra)
    return r


def review(stage: str, action: str = "approved", feedback: str | None = None) -> dict[str, Any]:
    r: dict[str, Any] = {"stage": stage, "review": action}
    if feedback is not None:
        r["feedback"] = feedback
    return r


def verdict(status: Any, attempt: Any = 1, *, stage: str = "test", **extra: Any) -> dict[str, Any]:
    v = {"status": status, "summary": "", "failures": [], "commands": [], "command_check": None}
    v.update(extra)
    return {"stage": stage, "attempt": attempt, "verdict": v}


def red_result(status: str = "red") -> dict[str, Any]:
    return {"stage": "red", "result": {"status": status, "summary": "", "tests": [], "commands": []}}


def opened(stage: str, *, seq: int = 1, attempt: Any = None, log: str | None = None) -> dict[str, Any]:
    name = log if log is not None else f"{seq:02d}_{stage}" + (f"_{attempt}" if attempt else "") + ".jsonl"
    return {"stage": stage, "seq": seq, "attempt": attempt, "note": "", "log": name, "began_at": "2026-10-17T10:00:00"}


def pending(stage: str, since: Any = "2026-10-17T10:00:00+09:00") -> dict[str, Any]:
    p: dict[str, Any] = {"stage": stage, "doc": f"docs/pipeline/{stage}.md", "session_id": None}
    if since is not ...:
        p["since"] = since
    return p


def write_state(work: Path, state: Any) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    path = work / "state.json"
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_log(work: Path, name: str, lines: list[Any]) -> Path:
    """段のログ。lines の文字列はそのまま、辞書は JSON にして1行ずつ書く。"""
    logs = work / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / name
    body = "".join((ln if isinstance(ln, str) else json.dumps(ln, ensure_ascii=False)) + "\n" for ln in lines)
    path.write_text(body, encoding="utf-8")
    return path


def prompt_line(at: Any, **extra: Any) -> dict[str, Any]:
    line: dict[str, Any] = {"_type": "Prompt", "stage": "x", "resume": None, "prompt": "p", "at": at}
    line.update(extra)
    return line


def recorder(project: Path, clock: datetime) -> Recorder:
    return Recorder(load_config(project), now=lambda: clock)


def work_of(project: Path) -> Path:
    return project / "docs" / "pipeline"


def dev_record_midway(project: Path, clock: datetime = datetime(2026, 10, 17, 10, 0, 0)) -> Path:
    """本物の Recorder で作る、設計の段が動いている途中の記録。work_dir を返す。"""
    r = recorder(project, clock)
    r.start("足したい機能のメモ MEMO-BODY-MARK", name="途中のセッション", session_id="SESSION-ID-MARK")
    r.begin("requirements", agent="pipe-in-analyst")
    r.done("requirements", summary="要件定義を書いた")
    r.wait("requirements")
    r.review("requirements", "approved")
    r.begin("design", agent="pipe-in-analyst")
    return work_of(project)


def utc_text(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="seconds")


# ---- D0044：確認待ちの答え（テストの補助。本体の関数ではなく、設計 4 節の式をそのまま書く） ----------------------------------------


def expected_review_id(stage: str, since: str) -> str:
    """設計 4 節の識別子：SHA-256("pipe-in:review\\n" + 段 + "\\n" + since) の先頭 10 文字。本体の review_id と突き合わせる基準。"""
    import hashlib

    return hashlib.sha256(("pipe-in:review\n" + stage + "\n" + since).encode("utf-8")).hexdigest()[:10]


def pending_project(project: Path, stage: str = "requirements", clock: datetime = datetime(2026, 10, 17, 10, 0, 0)) -> Path:
    """本物の Recorder で作る、指定の段が確認待ちの記録（その前の段は承認済み）。work_dir を返す。"""
    r = recorder(project, clock)
    r.start("足したい機能のメモ MEMO-BODY-MARK", name="確認待ちのセッション", session_id="SESSION-ID-MARK")
    for name in STAGES:
        r.begin(name, agent="pipe-in-analyst")
        r.done(name, summary="段を終えた")
        if name == stage:
            r.wait(name)
            return work_of(project)
        if name in ("requirements", "design", "red"):
            r.wait(name)
            r.review(name, "approved")
    raise AssertionError(f"確認待ちにできない段: {stage}")


def pending_of(work: Path) -> dict[str, Any]:
    """state.json の pending_review（辞書）。"""
    value = json.loads((work / "state.json").read_text(encoding="utf-8"))["pending_review"]
    assert isinstance(value, dict), "確認待ちになっていない"
    return value
