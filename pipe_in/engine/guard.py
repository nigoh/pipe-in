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

# サブエージェントを任せる道具（D0035）。段の1回の実行で通すのは、合わせて max_agent_calls 回まで。
AGENT_TOOLS = frozenset({"Agent", "Task"})
DEFAULT_MAX_AGENT_CALLS = 20
# 裏で動かす形の印。段は応答が終わると裏の作業の結果を待てないので、Agent・Task・Bash では止める。
# Bash は書かなければ待つ形なので書かないものを通し、Agent・Task は false を書いたものだけを通す。
BACKGROUND_KEY = "run_in_background"
# Agent・Task の isolation（別の作業場所で動かす印）。書いたものは値によらず止める。
ISOLATION_KEY = "isolation"
# PreToolUse の入力で、サブエージェントの中からの呼び出しにだけ入る印（SDK の型の説明による。値は問わない）。
# agent_type はメインのスレッドでも入ることがあるので、印にしない。
SUBAGENT_MARK = "agent_id"

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


def _foreground(tool_input: Any) -> bool:
    """Bash が待つ形の呼び出しか。許すのは「run_in_background を書かない」か「false（真偽値）を書く」の2つだけ。
    "false" のような文字・0・None・表でない入力（読めない入力）は、どれも裏で動かす形とみなして止める。
    Agent・Task はこれより厳しく、false を書いたものだけを通す（check_tool）。"""
    if not isinstance(tool_input, dict):
        return False
    return BACKGROUND_KEY not in tool_input or tool_input[BACKGROUND_KEY] is False


def check_agent_call(tool_name: str, input_data: dict[str, Any], *, used: int, limit: int) -> str | None:
    """check_tool を通った Agent・Task にだけ掛ける。入れ子と、上限を超えた呼び出しを止める。止めるなら理由を返す。"""
    if SUBAGENT_MARK in input_data:
        return f"サブエージェントの中から {tool_name} は呼べません（入れ子の呼び出しは止めます）"
    if used >= limit:
        return (
            f"この段の1回の実行で呼べるサブエージェントは {limit} 回までです。"
            "これまでに返った結果で成果物を書いてください"
        )
    return None


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
    if tool_name in AGENT_TOOLS:
        # Agent・Task は、書かないとメインからは裏で動くので、false を書いたときだけ通す。
        if not isinstance(tool_input, dict) or tool_input.get(BACKGROUND_KEY) is not False:
            return (
                f"{tool_name} は裏で動かす形（run_in_background）か、その印が無い形では呼べません。"
                "run_in_background: false を付けて呼び直してください（段は裏の作業の結果を待てません）"
            )
        # isolation（worktree・remote など）は、書かないときだけ通す。値は問わない。
        if ISOLATION_KEY in tool_input:
            return f"{tool_name} に isolation は付けられません。isolation を付けずに呼び直してください"
    raw_input = tool_input
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if tool_name == "WebFetch" and fetch_domains is not None:
        url = str(tool_input.get("url", ""))
        if not _host_allowed(url, fetch_domains):
            return f"この段で取得できるのは {', '.join(fetch_domains)} だけです（{url} は対象外）"
    if tool_name == "Bash":
        if not allow_bash:
            return "この段では Bash を使えません"
        if not _foreground(raw_input):
            return (
                "Bash は裏で動かす形（run_in_background）では呼べません。"
                "run_in_background を付けずに呼び直してください（段は裏の作業の結果を待てません）"
            )
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
    max_agent_calls: int = DEFAULT_MAX_AGENT_CALLS,
    on_deny: Callable[[str, str], None] | None = None,
):
    """段の1回の実行のガードを作る。Agent・Task の数は、ここで作るたびに 0 から数える（作る単位 ＝ 数える単位）。

    上限の無いガードは作れない：max_agent_calls は 1 以上の整数だけを受け、ほかは ValueError にする。
    """
    if not isinstance(max_agent_calls, int) or isinstance(max_agent_calls, bool) or max_agent_calls < 1:
        raise ValueError(f"max_agent_calls は 1 以上の整数で渡してください（{max_agent_calls!r}）")
    used = 0

    async def guard(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
        nonlocal used
        tool_name = input_data.get("tool_name", "")
        # 表でない値（[]・""・None など）は空の表に直さずそのまま渡す。Agent・Task・Bash はそこで止まる。
        # キーそのものが無いときだけ空の表（Agent・Task は run_in_background が無いので止まる）。
        tool_input = input_data.get("tool_input", {})
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
        # 確かめてから数えるまでのあいだに await を置かない。1つの応答で並べて呼ばれても、
        # 割り込まれずに数えるので、上限を超えて通ることは無い。数えるのは通した呼び出しだけ。
        if reason is None and tool_name in AGENT_TOOLS:
            reason = check_agent_call(tool_name, input_data, used=used, limit=max_agent_calls)
            if reason is None:
                used += 1
        if reason:
            if on_deny:
                on_deny(tool_name, reason)
            return _deny(reason)
        return {}

    return guard
