"""確認ありの段のあとに、人が内容を確認する（承認 / 修正を依頼 / 中止）。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class Decision:
    action: Literal["approve", "revise", "quit"]
    feedback: str = ""


PREVIEW_LINES = 60


def _read_feedback(read: Callable[[str], str]) -> str:
    print("  修正してほしい点を書いてください（空行で終わり）:")
    lines: list[str] = []
    while True:
        line = read("  > ")
        if not line.strip():
            break
        lines.append(line)
    return "\n".join(lines)


def ask_human(stage: str, doc: Path, *, read: Callable[[str], str] = input, label: str | None = None) -> Decision:
    try:
        return _ask(stage, doc, read, label or stage)
    except EOFError:
        print("\n  入力を読めなかったため中止します（確認を省くなら --yes）。")
        return Decision("quit")


def _ask(stage: str, doc: Path, read: Callable[[str], str], label: str) -> Decision:
    text = doc.read_text(encoding="utf-8") if doc.exists() else ""
    lines = text.splitlines()
    print()
    print(f"━━━ {label}の確認 ━━━ {doc}")
    for line in lines[:PREVIEW_LINES]:
        print(f"  │ {line}")
    if len(lines) > PREVIEW_LINES:
        print(f"  │ …（ほか {len(lines) - PREVIEW_LINES} 行。全文はファイルを開いてください）")
    print()
    while True:
        answer = read(f"  {label}をこの内容で進めますか？ [Enter]=承認 / r=修正を依頼 / q=中止 : ").strip().lower()
        if answer in ("", "y", "yes", "ok"):
            return Decision("approve")
        if answer in ("q", "quit"):
            return Decision("quit")
        if answer in ("r", "revise"):
            feedback = _read_feedback(read)
            if feedback:
                return Decision("revise", feedback)
            print("  指摘が空だったので、もう一度選んでください。")
