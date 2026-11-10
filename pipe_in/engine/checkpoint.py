"""確認ありの段のあとに、人が内容を確認する（承認 / 修正を依頼 / 中止）。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .reply import ReplyPoller, ReplyResult, ReplyWait


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


class _Replied(Exception):
    """返事のファイルで答えが来たことを、入力の待ちから上へ知らせる。"""

    def __init__(self, result: ReplyResult) -> None:
        super().__init__("返事のファイル")
        self.result = result


_REPLIED_TEXT = {"approve": "承認", "revise": "修正の依頼", "quit": "中止"}


def ask_human(
    stage: str,
    doc: Path,
    *,
    read: Callable[[str], str] = input,
    label: str | None = None,
    reply: ReplyWait | None = None,
) -> Decision:
    """reply を渡すと、端末の入力と返事のファイル（D0079）の両方を待つ。渡さなければ read だけを使う。"""
    if reply is None:
        try:
            return _ask(stage, doc, read, label or stage)
        except EOFError:
            print("\n  入力を読めなかったため中止します（確認を省くなら --yes）。")
            return Decision("quit")
    try:
        return _ask_with_reply(stage, doc, label or stage, reply)
    finally:
        try:
            reply.env.remove(reply.path)
        except Exception:
            pass  # 消せなくても止めない


def _ask_with_reply(stage: str, doc: Path, label: str, reply: ReplyWait) -> Decision:
    env = reply.env
    source = env.line_source()
    poller = ReplyPoller(reply.path, reply.stage, reply.wait_id, read_file=env.read_file, remove=env.remove, say=env.say)

    def read_line(prompt: str) -> str:
        print(prompt, end="", flush=True)
        while True:
            line = source.get(env.interval)  # EOFError はそのまま上へ
            if line is not None:
                return line  # 端末の答えを先に見る
            got = poller.check()
            if got is not None:
                raise _Replied(got)

    source.drain()
    try:
        return _ask(stage, doc, read_line, label)
    except EOFError:
        print("\n  入力を読めなかったため中止します（確認を省くなら --yes）。")
        return Decision("quit")
    except _Replied as replied:
        action = replied.result.action or "quit"
        print(f"\n  返事のファイルで{_REPLIED_TEXT.get(action, action)}を受け取りました。")
        if action == "revise":
            return Decision("revise", replied.result.feedback or "")
        return Decision("approve" if action == "approve" else "quit")


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
