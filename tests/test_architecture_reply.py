"""D0079-AC-02：返事のファイルを読む部品（pipe_in/engine/reply.py）は、標準ライブラリと live_answer だけを読む葉の部品。

読み取りの規則を 1 つの部品に持たせ、checkpoint・pipeline・runner・SDK などへ依存させない（依存の向きは engine の中でも下向きだけ）。
新しいアーキテクチャの検査は、並列の作業でぶつからないよう、別のファイル（これ）に置く（docs/development/testing.md）。
空の形のファイルは今は標準ライブラリしか import しないので、本物の検査は今のまま通る（守り続けるための検査）。
実装が checkpoint や SDK を読んだら落ちる。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILE = "pipe_in/engine/reply.py"
MODULE = "pipe_in.engine.reply"
ALLOWED = ("pipe_in.engine.live_answer",)
# live_answer へ着くまでの親のパッケージ（from . import live_answer の形で一緒に出てくる）
ANCESTORS = ("pipe_in", "pipe_in.engine")


def imports_of(source: str, module: str) -> list[str]:
    """import している名前（相対 import は絶対の名前に直す）。tests/test_architecture.py の読み方と同じ。"""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = module.split(".")[:-1]
                base = base[: len(base) - (node.level - 1)]
                target = ".".join([*base, node.module] if node.module else base)
            else:
                target = node.module or ""
            found.append(target)
            found += [f"{target}.{a.name}" for a in node.names]
    return found


def violations(source: str, module: str = MODULE, allowed: tuple[str, ...] = ALLOWED) -> list[str]:
    """標準ライブラリでも許した部品でもない import を、文の一覧で返す。"""
    out: list[str] = []
    for target in imports_of(source, module):
        top = target.split(".")[0]
        if target in ANCESTORS:
            continue
        if any(target == a or target.startswith(a + ".") for a in allowed):
            continue
        if top in sys.stdlib_module_names:
            continue
        out.append(f"読んではいけない部品: {target}")
    return out


def test_reply_は標準ライブラリと_live_answer_だけを読む():
    """D0079-AC-02: pipe_in/engine/reply.py が import するのは、標準ライブラリと pipe_in.engine.live_answer だけ
    （checkpoint・pipeline・runner・dev・pipe・cli・usage・SDK は読まない。今のまま通る。守る）。"""
    path = ROOT / FILE
    assert path.is_file(), FILE
    assert violations(path.read_text(encoding="utf-8")) == []


def test_live_answer_は_reply_を読まない():
    """D0079-AC-02: 葉の部品 live_answer.py は reply.py を読まない（向きは reply → live_answer だけ。今のまま通る。守る）。"""
    source = (ROOT / "pipe_in/engine/live_answer.py").read_text(encoding="utf-8")
    assert not any(t == "pipe_in.engine.reply" or t.startswith("pipe_in.engine.reply.") for t in imports_of(source, "pipe_in.engine.live_answer"))


def test_検査そのものが違反を見つけられる():
    """D0079-AC-02: 検査そのものが、checkpoint・pipeline・runner・SDK・dev・pipe・cli・usage への import（相対の形を含む）を見つけ、
    標準ライブラリと live_answer（相対の形を含む）は通す。"""
    bad = (
        "from .checkpoint import Decision\n"
        "from . import pipeline\n"
        "from ..usage.metrics import summarize_runs\n"
        "import claude_agent_sdk\n"
        "from pipe_in.engine.runner import run_stage_sdk\n"
        "from pipe_in.dev import record\n"
        "from pipe_in.pipe.definition import load_pipe\n"
        "from pipe_in import cli\n"
        "import requests\n"
    )
    text = "\n".join(violations(bad))
    for word in ["pipe_in.engine.checkpoint", "pipe_in.engine.pipeline", "pipe_in.usage", "claude_agent_sdk", "pipe_in.engine.runner", "pipe_in.dev", "pipe_in.pipe", "pipe_in.cli", "requests"]:
        assert word in text, f"{word} を見つけられない: {text}"
    good = (
        "from __future__ import annotations\n"
        "import json, os, queue, threading\n"
        "from collections.abc import Callable\n"
        "from dataclasses import dataclass\n"
        "from pathlib import Path\n"
        "from .live_answer import ID_RE, MAX_FEEDBACK, READ_LIMIT, STAGE_RE\n"
        "from pipe_in.engine.live_answer import ID_RE as OTHER\n"
    )
    assert violations(good) == []
    nested = "def f():\n    import subprocess\n    from .checkpoint import Decision\n"
    assert any("checkpoint" in v for v in violations(nested)), "関数の中の import を見つけられない"
