"""各段が触ってよい範囲を強制する PreToolUse フック。

PreToolUse フックは許可設定より先に動くので、allowed_tools で自動承認した
ツールでも、ここで deny すれば実行されません。
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Callable, Collection
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

# どの段でも使ってよい、読むだけ・手元の整理だけの道具。
# StructuredOutput は、SDK が構造化出力（段の判定・分岐の選択など）を返すのに使う道具で、何も書かない。
ALWAYS_ALLOWED = {"Read", "Glob", "Grep", "Skill", "ToolSearch", "TodoWrite", "StructuredOutput"}

# どの段でも実行させない Bash コマンド
DANGEROUS_BASH: list[tuple[str, str]] = [
    (r"\bgit\s+push\b", "git push はパイプラインの外で人が行ってください"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard は禁止です"),
    (r"\bgit\s+clean\s+-\w*f", "git clean -f は禁止です"),
    (r"\bgit\s+(checkout|switch)\b", "ブランチの切り替えはパイプラインの外で行ってください"),
    (r"\brm\s+(-\w*[rR]\w*|--recursive)\b", "再帰的な削除は禁止です"),
    (r"\bsudo\b", "sudo は禁止です"),
    (r"\b(curl|wget|ssh|scp|rsync|nc)\b", "外部への通信コマンドは禁止です"),
    (r"\b(npm|pnpm|yarn|cargo)\s+publish\b|\btwine\s+upload\b", "パッケージの公開は禁止です"),
    (r"\bchmod\s+-R\b|\bchown\b", "権限の一括変更は禁止です"),
]

TEST_DIR_NAMES = {"tests", "test", "__tests__", "spec", "specs"}
TEST_FILE_GLOBS = ["test_*.py", "*_test.py", "*_test.go", "*.test.*", "*.spec.*", "*_spec.rb", "conftest.py"]


def is_test_path(rel: str, extra_globs: list[str] | None = None) -> bool:
    """テスト用のファイルかどうか（ディレクトリ名とファイル名で判定）。"""
    p = PurePosixPath(rel)
    if any(part in TEST_DIR_NAMES for part in p.parts[:-1]):
        return True
    if any(fnmatch.fnmatch(p.name, g) for g in TEST_FILE_GLOBS):
        return True
    return any(fnmatch.fnmatch(rel, g) for g in (extra_globs or []))


def _listed(tool_name: str, allowed_tools: Collection[str]) -> bool:
    """allowed_tools にあるか。MCP の道具だけは、サーバー単位の指定（mcp__<サーバー>）でも許す。"""
    if tool_name in ALWAYS_ALLOWED or tool_name in allowed_tools:
        return True
    if tool_name.startswith("mcp__"):
        return any(a.startswith("mcp__") and a.count("__") == 1 and tool_name.startswith(a + "__") for a in allowed_tools)
    return False


def _host_allowed(url: str, domains: Collection[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def check_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    project_dir: Path,
    can_write: Callable[[str], bool],
    allow_bash: bool,
    write_scope_hint: str,
    allowed_tools: Collection[str] | None = None,
    fetch_domains: Collection[str] | None = None,
) -> str | None:
    """拒否する場合はその理由を返す。許可なら None。

    allowed_tools を渡すと、そこと ALWAYS_ALLOWED にないツール（PowerShell・MCP・サブエージェントなど）は
    すべて止める。書き込みの範囲や危ない操作の判定は Bash と書き込み系のツールにしか掛けていないため、
    それ以外の道から同じことをされないようにする。MCP は、段が明示したサーバー（mcp__<サーバー>）の道具だけを通す。
    fetch_domains を渡すと、WebFetch はそのドメイン（とその下）だけに限る。
    """
    if allowed_tools is not None and not _listed(tool_name, allowed_tools):
        return f"この段では {tool_name} を使えません"
    if tool_name == "WebFetch" and fetch_domains is not None:
        url = str(tool_input.get("url", ""))
        if not _host_allowed(url, fetch_domains):
            return f"この段で取得できるのは {', '.join(fetch_domains)} だけです（{url} は対象外）"
    if tool_name == "Bash":
        if not allow_bash:
            return "この段では Bash を使えません"
        cmd = str(tool_input.get("command", ""))
        for pattern, reason in DANGEROUS_BASH:
            if re.search(pattern, cmd):
                return reason
        return None

    if tool_name in WRITE_TOOLS:
        raw = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if not raw:
            return "書き込み先のパスがありません"
        target = Path(raw)
        if not target.is_absolute():
            target = project_dir / target
        target = target.resolve()
        try:
            rel = target.relative_to(project_dir).as_posix()
        except ValueError:
            return "プロジェクトの外には書き込めません"
        if not can_write(rel):
            return f"この段で書き込めるのは {write_scope_hint} だけです（{rel} は対象外）"
    return None


def make_guard_hook(
    *,
    project_dir: Path,
    can_write: Callable[[str], bool],
    allow_bash: bool,
    write_scope_hint: str,
    allowed_tools: Collection[str] | None = None,
    fetch_domains: Collection[str] | None = None,
    on_deny: Callable[[str, str], None] | None = None,
):
    async def guard(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {}) or {}
        reason = check_tool(
            tool_name,
            tool_input,
            project_dir=project_dir,
            can_write=can_write,
            allow_bash=allow_bash,
            write_scope_hint=write_scope_hint,
            allowed_tools=allowed_tools,
            fetch_domains=fetch_domains,
        )
        if reason:
            if on_deny:
                on_deny(tool_name, reason)
            return _deny(reason)
        return {}

    return guard
