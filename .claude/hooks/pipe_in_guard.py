"""/pipe-in の段を受け持つサブエージェントの PreToolUse フック：段ごとに、書ける場所と使える Bash を絞る。

.claude/settings.json から、どの道具の呼び出しでもここを呼ぶ。入力の agent_type が pipe-in- で始まるときだけ検査し、
メインエージェントやほかのサブエージェント（プラグインの pipe-in:pipe-builder・Explore など）には何もしない。
- pipe-in-analyst（要件定義・設計）：docs/pipeline/01_requirements.md・02_design.md だけ。Bash なし
- pipe-in-tester（テスト先行）：tests/・vscode/src の *.test.ts と vscode/src/test/・docs/pipeline/03_red_tests.md。Bash はテストを流すだけ
- pipe-in-coder（実装）：テスト・.claude/・.git/・.env・ほかの段の記録を除いた所と docs/pipeline/04_implementation.md。Bash はテスト・型検査・ビルド
- pipe-in-verifier（検証）：docs/pipeline/05_test_report.md だけ。Bash はテスト・型検査・ビルド・git の読むだけのコマンド
- pipe-in-documenter（文書をそろえる）：README.md・vscode/README.md・pipes/README.md・docs/assets/README.md と docs/guide/・docs/development/ の .md だけ。Bash なし。
  CLAUDE.md・.claude/・決定の記録（docs/decisions/）は書けず、案を親に返す
- pipe-in-auditor（矛盾監査）・pipe-in-advisor（助言）・pipe-in-judge（審査）：どこにも書けない・Bash なし。報告は SubagentHandback で返すだけ
- Web は pipe-in-advisor（WebFetch・WebSearch）と pipe-in-judge（WebFetch だけ）だけ、公式の文書の場所（DOC_HOSTS・GITHUB_HOSTS）だけ
- 表に無い pipe-in-* は、Read・Glob・Grep・SubagentHandback だけ（表に足し忘れても絞られるように）
PowerShell・MCP・Agent・Web（アドバイザーと審査役の公式の文書のほか）・ノートブックなど、上に挙げていない道具は止める（すり抜けの道を開けない）。
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
from urllib.parse import unquote, urlsplit

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

# アドバイザーと審査役が読んでよい公式の文書の場所。定義（.claude/agents/pipe-in-advisor.md・pipe-in-judge.md）はここを写す（D0008-AC-16・D0015-AC-06 で検査）
DOC_HOSTS = ("code.claude.com", "docs.claude.com", "docs.anthropic.com", "platform.claude.com")
# github は道の1つ目が anthropics のときだけ（WebFetch だけ。WebSearch の allowed_domains は道まで絞れないので入れない）
GITHUB_HOSTS = ("github.com", "raw.githubusercontent.com")
GITHUB_OWNER = "anthropics"
# Web を使える役と、使える道具。審査役は出典を確かめるだけなので WebFetch だけ（D0015）
WEB_AGENTS: dict[str, frozenset[str]] = {
    "pipe-in-advisor": frozenset({"WebFetch", "WebSearch"}),
    "pipe-in-judge": frozenset({"WebFetch"}),
}
# この名前で始まり、表に無いエージェントは読むだけにする
UNKNOWN_PREFIX = "pipe-in-"


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


# 文書係が書ける文書。CLAUDE.md・.claude/（/pipe-help を含む）・決定の記録は、メインが人の承認を得てから書く（D0020）
DOC_FILES = ("README.md", "vscode/README.md", "pipes/README.md", "docs/assets/README.md")
DOC_DIRS = ("docs/guide/", "docs/development/")


def _documenter(rel: str) -> bool:
    return rel in DOC_FILES or (rel.startswith(DOC_DIRS) and rel.endswith(".md"))


def _nowhere(rel: str) -> bool:
    return False


AGENTS: dict[str, tuple[Any, list[str], str]] = {
    "pipe-in-analyst": (_analyst, [], "docs/pipeline/01_requirements.md・02_design.md"),
    "pipe-in-tester": (_tester, TESTS, "テスト（tests/・*.test.ts）と docs/pipeline/03_red_tests.md"),
    "pipe-in-coder": (_coder, TESTS + BUILD, "製品コードと文書（テスト・.claude/・.git/・ほかの段の記録を除く）と docs/pipeline/04_implementation.md"),
    "pipe-in-verifier": (_verifier, TESTS + BUILD + GIT_READ, "docs/pipeline/05_test_report.md"),
    "pipe-in-documenter": (_documenter, [], "README.md・vscode/README.md・pipes/README.md・docs/assets/README.md と docs/guide/・docs/development/ の .md"),
    "pipe-in-auditor": (_nowhere, [], ""),
    "pipe-in-advisor": (_nowhere, [], ""),
    "pipe-in-judge": (_nowhere, [], ""),
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


def official_doc_url(url: Any) -> bool:
    """WebFetch の URL が、公式の文書の場所の https:// の URL のときだけ True。迷うものは止める。"""
    if not isinstance(url, str) or not url:
        return False
    # 空白・制御文字と、\ を / と読む作りへの見せかけを止める
    if any(ord(c) <= 0x20 or ord(c) == 0x7F or c == "\\" for c in url):
        return False
    if not url.lower().startswith("https://"):
        return False
    parts = urlsplit(url)
    # ユーザー情報（@）・ポート（:）で、ホストを見せかける道を止める
    if "@" in parts.netloc or ":" in parts.netloc:
        return False
    host = parts.netloc.lower()
    if host not in DOC_HOSTS and host not in GITHUB_HOSTS:
        return False
    segments = [unquote(s) for s in parts.path.split("/")[1:]]
    # 道の正規化（.. や %2f）で別の所へ行くのを止める
    if any(s in (".", "..") or "/" in s or "\\" in s for s in segments):
        return False
    if host in GITHUB_HOSTS and (not segments or segments[0].lower() != GITHUB_OWNER):
        return False
    return True


def official_search_domains(domains: Any) -> bool:
    """WebSearch の allowed_domains が、空でなく、すべて公式の文書のホストのときだけ True。"""
    if not isinstance(domains, list) or not domains:
        return False
    return all(isinstance(d, str) and d in DOC_HOSTS for d in domains)


def _places() -> str:
    return f"{'・'.join(DOC_HOSTS)} と、{'・'.join(GITHUB_HOSTS)} の {GITHUB_OWNER}/ の下"


def check_web(tool: str, tool_input: dict[str, Any], agent: str) -> str | None:
    if tool == "WebFetch":
        if official_doc_url(tool_input.get("url")):
            return None
        return f"{agent} の WebFetch で取れるのは、公式の文書の場所（{_places()}）の https:// の URL だけです（{tool_input.get('url')}）"
    if official_search_domains(tool_input.get("allowed_domains")):
        return None
    return f"{agent} の WebSearch は、allowed_domains に公式の文書の場所（{'・'.join(DOC_HOSTS)}）だけを付けたときだけ使えます（{tool_input.get('allowed_domains')}）"


def decide(payload: dict[str, Any], *, root: str) -> str | None:
    """止める理由を返す。止めないときは None。pipe-in- で始まらない呼び出しには何もしない。"""
    agent = payload.get("agent_type")
    unknown = False
    if agent in AGENTS:
        can_write, bash, where = AGENTS[agent]
    elif isinstance(agent, str) and agent.lower().startswith(UNKNOWN_PREFIX):
        # 表に足し忘れたエージェントも、読むことと報告のほかは止める
        can_write, bash, where = _nowhere, [], ""
        unknown = True
    else:
        return None
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if tool in READ_TOOLS or tool in REPORT_TOOLS:
        return None
    if unknown:
        return f"{agent} はフックの表（.claude/hooks/pipe_in_guard.py の AGENTS）に無いため、Read・Glob・Grep・SubagentHandback のほかは使えません（{tool}）"
    if tool in WRITE_TOOLS:
        rel = project_path(tool_input.get("file_path"), root)
        if not where:
            return f"{agent} はどこにも書けません（報告は SubagentHandback で親に返す）（{tool_input.get('file_path')}）"
        if rel is None or not can_write(rel):
            return f"{agent} が書けるのは {where} だけです（{tool_input.get('file_path')}）"
        return None
    if tool == "Bash":
        return check_bash(tool_input.get("command"), bash, agent)
    if tool in WEB_AGENTS.get(agent, frozenset()):
        return check_web(tool, tool_input, agent)
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
