"""/pipe-in の段を受け持つサブエージェントの PreToolUse フック：段ごとに、書ける場所と使える Bash を絞る。

.claude/settings.json から、どの道具の呼び出しでもここを呼ぶ。入力の agent_type が pipe-in-* のときだけ検査し、
メインエージェントやほかのサブエージェントには何もしない。
- pipe-in-analyst（要件定義・設計）：docs/pipeline/01_requirements.md・02_design.md だけ。Bash なし
- pipe-in-tester（テスト先行）：tests/・vscode/src の *.test.ts と vscode/src/test/・docs/pipeline/03_red_tests.md。Bash はテストを流すだけ
- pipe-in-coder（実装）：テスト・.claude/・.git/・.env・ほかの段の記録を除いた所と docs/pipeline/04_implementation.md。Bash はテスト・型検査・ビルド
- pipe-in-verifier（検証）：docs/pipeline/05_test_report.md だけ。Bash はテスト・型検査・ビルド・git の読むだけのコマンド
PowerShell・MCP・Agent・Web・ノートブックなど、上に挙げていない道具は止める（すり抜けの道を開けない）。
報告を親に渡す SubagentHandback は止めない。書いてよい場所の基準は、サブエージェントがいる git の作業フォルダ
（worktree ならその worktree。見つからなければ CLAUDE_PROJECT_DIR）。

道具を呼ぶたびに動くので、標準ライブラリだけを使う。入力が読めないときは止める。
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

READ_TOOLS = {"Read", "Glob", "Grep"}
# 報告を親に渡すだけの道具。止めると、どの段も報告を返せずに終わる（ファイルにも外にも書かない）
REPORT_TOOLS = {"SubagentHandback"}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}
WORK = "docs/pipeline/"

# 別のコマンドをつなぐ・書き出す・置き換える記号
SHELL_META = set(";&|`$<>(){}\n\r")
TESTS = [r"python -m pytest(\s.*)?", r"pytest(\s.*)?", r"npm --prefix vscode test"]
BUILD = [r"npm --prefix vscode run (typecheck|build)"]
GIT_READ = [r"git (diff|status|log|show)(\s.*)?"]


def _analyst(rel: str) -> bool:
    return rel in (WORK + "01_requirements.md", WORK + "02_design.md")


def _is_test(rel: str) -> bool:
    return rel.startswith("tests/") or rel.startswith("vscode/src/test/") or (rel.startswith("vscode/") and rel.endswith(".test.ts"))


def _tester(rel: str) -> bool:
    return _is_test(rel) or rel == WORK + "03_red_tests.md"


def _coder(rel: str) -> bool:
    if rel == WORK + "04_implementation.md":
        return True
    if _is_test(rel) or rel.startswith((".claude/", ".git/", WORK)):
        return False
    return not Path(rel).name.startswith(".env")


def _verifier(rel: str) -> bool:
    return rel == WORK + "05_test_report.md"


AGENTS: dict[str, tuple[Any, list[str], str]] = {
    "pipe-in-analyst": (_analyst, [], "docs/pipeline/01_requirements.md・02_design.md"),
    "pipe-in-tester": (_tester, TESTS, "テスト（tests/・*.test.ts）と docs/pipeline/03_red_tests.md"),
    "pipe-in-coder": (_coder, TESTS + BUILD, "製品コードと文書（テスト・.claude/・.git/・ほかの段の記録を除く）と docs/pipeline/04_implementation.md"),
    "pipe-in-verifier": (_verifier, TESTS + BUILD + GIT_READ, "docs/pipeline/05_test_report.md"),
}


def project_root(cwd: str, project_dir: str | None) -> str:
    """書いてよい場所の基準：サブエージェントがいる git の作業フォルダ（.git のあるいちばん近い上のフォルダ）。

    worktree（.git がファイル）で作業しているとき、会話を始めた場所（CLAUDE_PROJECT_DIR）を基準にすると、
    worktree の下がすべて「プロジェクトの外」になって書けない。基準を worktree にしても、範囲はその中の
    決まった場所だけで、会話を始めた場所やほかの worktree には書けない。見つからなければ今までどおり。
    """
    here = os.path.normpath(os.path.abspath(cwd)) if cwd else ""
    while here:
        if os.path.exists(os.path.join(here, ".git")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return project_dir or cwd or os.getcwd()


def project_path(file_path: Any, root: str) -> str | None:
    """プロジェクトの中の相対パス（/ 区切り）。外や .. を含むときは None。"""
    if not isinstance(file_path, str) or not file_path.strip():
        return None
    if ".." in re.split(r"[\\/]", file_path):
        return None
    base = os.path.normpath(os.path.abspath(root))
    full = os.path.normpath(file_path if os.path.isabs(file_path) else os.path.join(base, file_path))
    if not os.path.normcase(full).startswith(os.path.normcase(base) + os.sep):
        return None
    return Path(os.path.relpath(full, base)).as_posix()


def check_bash(command: Any, allowed: list[str], agent: str) -> str | None:
    if not allowed:
        return f"{agent} は Bash を使えません"
    if not isinstance(command, str) or not command.strip():
        return "空のコマンドは実行できません"
    if SHELL_META & set(command):
        return f"{agent} の Bash では、コマンドをつなぐ・書き出す記号（; & | ` $ < > など）は使えません"
    if any(t.startswith("--output") for t in command.split()):
        return f"{agent} の Bash では、ファイルに書き出すオプション（--output）は使えません"
    if not any(re.fullmatch(p, command.strip()) for p in allowed):
        return f"{agent} の Bash で使えるのは、テスト・型検査・ビルドなど決まったコマンドだけです（{command.strip()}）"
    return None


def decide(payload: dict[str, Any], *, root: str) -> str | None:
    """止める理由を返す。止めないときは None。pipe-in-* 以外の呼び出しには何もしない。"""
    agent = payload.get("agent_type")
    if agent not in AGENTS:
        return None
    can_write, bash, where = AGENTS[agent]
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if tool in READ_TOOLS or tool in REPORT_TOOLS:
        return None
    if tool in WRITE_TOOLS:
        rel = project_path(tool_input.get("file_path"), root)
        if rel is None or not can_write(rel):
            return f"{agent} が書けるのは {where} だけです（{tool_input.get('file_path')}）"
        return None
    if tool == "Bash":
        return check_bash(tool_input.get("command"), bash, agent)
    return f"{agent} は {tool} を使えません（使えるのは Read・Glob・Grep と、段ごとに決めた書き込みと Bash だけ）"


def _deny(reason: str) -> str:
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}},
        ensure_ascii=False,
    )


def _write(text: str) -> None:
    # Claude Code は UTF-8 で読む。Windows の標準出力（cp932）のまま書くと理由が文字化けするので、バイトで書く
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        sys.stdout.flush()
        buffer.write(text.encode("utf-8"))
        buffer.flush()
    else:
        sys.stdout.write(text)


def _read_stdin() -> str:
    # Windows でも、Claude Code が渡す UTF-8 をそのまま読む
    buffer = getattr(sys.stdin, "buffer", None)
    return buffer.read().decode("utf-8") if buffer is not None else sys.stdin.read()


def main() -> int:
    """標準入力の JSON を見て、止めるときだけ deny の JSON を出す。終了コードはいつも 0。"""
    try:
        payload = json.loads(_read_stdin())
    except (ValueError, UnicodeDecodeError):
        payload = None
    if not isinstance(payload, dict):
        # だれの呼び出しか分からないので、安全側に倒して止める
        _write(_deny("フックへの入力が読めないため止めました"))
        return 0
    root = project_root(str(payload.get("cwd") or ""), os.environ.get("CLAUDE_PROJECT_DIR"))
    reason = decide(payload, root=root)
    if reason:
        _write(_deny(reason))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
