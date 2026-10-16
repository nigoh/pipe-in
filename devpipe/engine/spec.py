"""段の設定（使えるツール・書き込める範囲・指示文）の型と、どのパイプにも共通の決まり。"""

from __future__ import annotations

import fnmatch
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .config import Config

READ_TOOLS = ["Read", "Glob", "Grep"]
EDIT_TOOLS = ["Write", "Edit", "MultiEdit", "NotebookEdit"]
NO_WEB = ["WebFetch", "WebSearch"]
# Bash と同じことができるのにガードの判定を通らない道。ガードでも止めるが、最初から使えなくしておく。
NO_SHELL_BYPASS = ["PowerShell"]


@dataclass
class StageSpec:
    name: str
    label: str
    allowed_tools: list[str]
    disallowed_tools: list[str]
    allow_bash: bool
    can_write: Callable[[str], bool]
    write_scope_hint: str
    system_append: str
    output_format: dict[str, Any] | None = None
    # 段の成果物（記録の置き場所の中のファイル名）と、このあとに人の確認を取るか。
    # state.json の stages に残し、VSCode の拡張が図と成果物の一覧を作るのに使う。
    output: str | None = None
    review: bool = False
    # 段の既定。pipeline.toml の [stages.<段>] に書いたほうが優先される。
    model: str | None = None
    max_turns: int | None = None
    max_budget_usd: float | None = None


def protect(specs: dict[str, StageSpec], cfg: Config) -> dict[str, StageSpec]:
    """protected_paths を、どの段の書き込み範囲からも外す。"""
    if cfg.protected_paths:
        for spec in specs.values():
            spec.can_write = _unless_protected(spec.can_write, cfg.protected_paths)
            spec.write_scope_hint += f"（{', '.join(cfg.protected_paths)} はどの段も変更できません）"
    return specs


def _unless_protected(can_write: Callable[[str], bool], globs: list[str]) -> Callable[[str], bool]:
    def wrapped(rel: str) -> bool:
        return not any(fnmatch.fnmatch(rel, g) for g in globs) and can_write(rel)

    return wrapped
