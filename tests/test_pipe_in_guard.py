"""/pipe-in の段を受け持つサブエージェントの書ける範囲を、PreToolUse フック（.claude/hooks/pipe_in_guard.py）で絞る。

メインエージェント（agent_type なし）には何もしない。サブエージェントは段ごとに、
書けるファイル・使える Bash のコマンドだけを許し、PowerShell・MCP・Agent・Web などのすり抜けの道は止める。
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parents[1]
HOOK = REPO / ".claude" / "hooks" / "pipe_in_guard.py"
AGENTS = ("pipe-in-analyst", "pipe-in-tester", "pipe-in-coder", "pipe-in-verifier")


def load():
    spec = importlib.util.spec_from_file_location("pipe_in_guard", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def guard():
    return load()


ROOT = str(REPO)


def call(guard, agent, tool, **tool_input):
    payload = {"tool_name": tool, "tool_input": tool_input, "cwd": ROOT}
    if agent:
        payload["agent_type"] = agent
    return guard.decide(payload, root=ROOT)


def write(guard, agent, path):
    return call(guard, agent, "Write", file_path=path, content="x")


def bash(guard, agent, command):
    return call(guard, agent, "Bash", command=command)


# ---- メインエージェントには何もしない --------------------------------------------


def test_ac04_main_agent_is_not_restricted(guard):
    assert write(guard, None, "devpipe/cli.py") is None
    assert call(guard, None, "PowerShell", command="Remove-Item x") is None
    assert bash(guard, None, "git commit -m x") is None
    assert call(guard, "Explore", "Write", file_path="x.py") is None  # ほかのサブエージェントにも何もしない


# ---- 段ごとの書ける場所 -----------------------------------------------------------


@pytest.mark.parametrize(
    "agent,path,ok",
    [
        ("pipe-in-analyst", "docs/pipeline/01_requirements.md", True),
        ("pipe-in-analyst", "docs/pipeline/02_design.md", True),
        ("pipe-in-analyst", "docs/pipeline/03_red_tests.md", False),
        ("pipe-in-analyst", "docs/pipeline/state.json", False),
        ("pipe-in-analyst", "devpipe/cli.py", False),
        ("pipe-in-tester", "tests/test_x.py", True),
        ("pipe-in-tester", "tests/fixtures/a/state.json", True),
        ("pipe-in-tester", "vscode/src/domain/a.test.ts", True),
        ("pipe-in-tester", "docs/pipeline/03_red_tests.md", True),
        ("pipe-in-tester", "vscode/src/domain/a.ts", False),
        ("pipe-in-tester", "devpipe/cli.py", False),
        ("pipe-in-tester", "tests/../devpipe/cli.py", False),
        ("pipe-in-tester", "docs/pipeline/04_implementation.md", False),
        ("pipe-in-coder", "devpipe/dev/record.py", True),
        ("pipe-in-coder", "vscode/src/domain/a.ts", True),
        ("pipe-in-coder", "README.md", True),
        ("pipe-in-coder", "docs/pipeline/04_implementation.md", True),
        ("pipe-in-coder", "tests/test_x.py", False),
        ("pipe-in-coder", "tests/fixtures/a/state.json", False),
        ("pipe-in-coder", "vscode/src/domain/a.test.ts", False),
        ("pipe-in-coder", ".claude/settings.json", False),
        ("pipe-in-coder", ".claude/hooks/pipe_in_guard.py", False),
        ("pipe-in-coder", ".git/config", False),
        ("pipe-in-coder", "docs/pipeline/state.json", False),
        ("pipe-in-coder", "docs/pipeline/03_red_tests.md", False),
        ("pipe-in-coder", ".env", False),
        ("pipe-in-verifier", "docs/pipeline/05_test_report.md", True),
        ("pipe-in-verifier", "docs/pipeline/04_implementation.md", False),
        ("pipe-in-verifier", "devpipe/cli.py", False),
        ("pipe-in-verifier", "tests/test_x.py", False),
    ],
)
def test_ac04_write_scope(guard, agent, path, ok):
    for tool in ("Write", "Edit", "MultiEdit"):
        reason = call(guard, agent, tool, file_path=path, old_string="a", new_string="b")
        assert (reason is None) == ok, f"{agent} {tool} {path}: {reason}"


def test_ac04_absolute_paths_inside_and_outside_the_project(guard):
    inside = str(REPO / "tests" / "test_x.py")
    assert write(guard, "pipe-in-tester", inside) is None
    outside = str(REPO.parent / "elsewhere" / "tests" / "test_x.py")
    assert write(guard, "pipe-in-tester", outside) is not None
    assert write(guard, "pipe-in-coder", str(Path.home() / "x.py")) is not None


def test_ac04_missing_path_is_denied(guard):
    assert call(guard, "pipe-in-coder", "Write", content="x") is not None


# ---- Bash：決まったコマンドだけ。つなぐ・書き出す記号は止める -------------------------


@pytest.mark.parametrize(
    "agent,command,ok",
    [
        ("pipe-in-analyst", "python -m pytest -q", False),
        ("pipe-in-analyst", "git status", False),
        ("pipe-in-tester", "python -m pytest -q", True),
        ("pipe-in-tester", "python -m pytest tests/test_record.py -q", True),
        ("pipe-in-tester", "pytest -q", True),
        ("pipe-in-tester", "npm --prefix vscode test", True),
        ("pipe-in-tester", "npm --prefix vscode run build", False),
        ("pipe-in-tester", "python -m pytest -q; rm -rf .", False),
        ("pipe-in-tester", "python -m pytest -q && git commit -m x", False),
        ("pipe-in-tester", "python -m pytest -q > out.txt", False),
        ("pipe-in-tester", "python -m pytest $(rm x)", False),
        ("pipe-in-tester", "python -c 'open(\"devpipe/cli.py\",\"w\")'", False),
        ("pipe-in-coder", "python -m pytest -q", True),
        ("pipe-in-coder", "npm --prefix vscode test", True),
        ("pipe-in-coder", "npm --prefix vscode run typecheck", True),
        ("pipe-in-coder", "npm --prefix vscode run build", True),
        ("pipe-in-coder", "pip install requests", False),
        ("pipe-in-coder", "npm --prefix vscode install left-pad", False),
        ("pipe-in-coder", "git checkout -- tests", False),
        ("pipe-in-coder", "devpipe record finish PASSED", False),
        ("pipe-in-verifier", "python -m pytest -q", True),
        ("pipe-in-verifier", "npm --prefix vscode run typecheck", True),
        ("pipe-in-verifier", "git diff", True),
        ("pipe-in-verifier", "git diff --stat", True),
        ("pipe-in-verifier", "git status --short", True),
        ("pipe-in-verifier", "git commit -m x", False),
        ("pipe-in-verifier", "git push", False),
        ("pipe-in-verifier", "git diff | sh", False),
    ],
)
def test_ac04_bash_scope(guard, agent, command, ok):
    reason = bash(guard, agent, command)
    assert (reason is None) == ok, f"{agent} `{command}`: {reason}"


# ---- すり抜けの道：PowerShell・MCP・Agent・Web・ノートブック ------------------------------


@pytest.mark.parametrize("agent", AGENTS)
@pytest.mark.parametrize(
    "tool,tool_input",
    [
        ("PowerShell", {"command": "Set-Content devpipe/cli.py x"}),
        ("mcp__plugin_playwright_playwright__browser_navigate", {"url": "http://example.com"}),
        ("mcp__claude_ai_Gmail__send_message", {}),
        ("Agent", {"prompt": "write devpipe/cli.py"}),
        ("WebFetch", {"url": "http://example.com"}),
        ("WebSearch", {"query": "x"}),
        ("NotebookEdit", {"notebook_path": "tests/a.ipynb"}),
        ("Artifact", {}),
    ],
)
def test_ac04_bypass_routes_are_denied(guard, agent, tool, tool_input):
    assert call(guard, agent, tool, **tool_input) is not None


@pytest.mark.parametrize("agent", AGENTS)
def test_ac04_reading_is_allowed(guard, agent):
    for tool in ("Read", "Glob", "Grep"):
        assert call(guard, agent, tool, file_path="devpipe/cli.py", pattern="x") is None


# ---- フックの入口：壊れた入力は止める。出すのは deny の JSON だけ ------------------------------


def run_main(guard, monkeypatch, text: str) -> str:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(text.encode("utf-8")), encoding="utf-8"))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    assert guard.main() == 0
    return out.getvalue()


def test_ac04_main_denies_unreadable_input(guard, monkeypatch):
    out = run_main(guard, monkeypatch, "not json")
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_ac04_main_denies_out_of_scope_and_passes_the_rest(guard, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", ROOT)
    deny = run_main(guard, monkeypatch, json.dumps({"agent_type": "pipe-in-tester", "tool_name": "Write", "tool_input": {"file_path": "devpipe/cli.py"}, "cwd": ROOT}))
    assert json.loads(deny)["hookSpecificOutput"]["permissionDecision"] == "deny"
    ok = run_main(guard, monkeypatch, json.dumps({"agent_type": "pipe-in-tester", "tool_name": "Write", "tool_input": {"file_path": "tests/test_x.py"}, "cwd": ROOT}))
    assert ok == ""


def test_ac04_main_writes_utf8_even_if_the_console_is_not(guard, monkeypatch):
    """検証で見つけたこと：Windows の標準出力（cp932）のまま書くと、Claude Code に届く理由が文字化けする。"""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", ROOT)
    payload = json.dumps({"agent_type": "pipe-in-tester", "tool_name": "Write", "tool_input": {"file_path": "devpipe/cli.py"}, "cwd": ROOT})
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload.encode("utf-8")), encoding="utf-8"))
    raw = io.BytesIO()
    out = io.TextIOWrapper(raw, encoding="cp932")
    monkeypatch.setattr(sys, "stdout", out)
    assert guard.main() == 0
    out.flush()
    reason = json.loads(raw.getvalue().decode("utf-8"))["hookSpecificOutput"]["permissionDecisionReason"]
    assert "書けるのは" in reason


def test_ac04_hook_uses_only_the_standard_library():
    src = HOOK.read_text(encoding="utf-8")
    imports = set(re.findall(r"^(?:from|import) ([a-zA-Z_]+)", src, re.M))
    assert imports <= {"__future__", "json", "os", "re", "sys", "pathlib", "typing"}


# ---- 設定：フックが登録され、4つのサブエージェントの定義が道具を絞っている -----------------------


def test_ac04_hook_is_registered_for_every_tool():
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    entries = settings["hooks"]["PreToolUse"]
    assert any(e.get("matcher") == "*" and any("pipe_in_guard.py" in h.get("command", "") for h in e["hooks"]) for e in entries)


@pytest.mark.parametrize("agent", AGENTS)
def test_ac04_agent_definitions_limit_tools(agent):
    text = (REPO / ".claude" / "agents" / f"{agent}.md").read_text(encoding="utf-8")
    front = text.split("---")[1]
    assert re.search(rf"^name:\s*{agent}\s*$", front, re.M)
    tools = re.search(r"^tools:\s*(.+)$", front, re.M).group(1)
    names = {t.strip() for t in tools.split(",")}
    assert names and not names & {"PowerShell", "Agent", "WebFetch", "WebSearch", "NotebookEdit"}
    assert not any(n.startswith("mcp__") for n in names)
    if agent == "pipe-in-analyst":
        assert "Bash" not in names


def test_ac04_skill_uses_the_agents_and_writes_records():
    skill = (REPO / ".claude" / "skills" / "pipe-in" / "SKILL.md").read_text(encoding="utf-8")
    for agent in AGENTS:
        assert agent in skill
    for op in ("record start", "record begin", "record done", "record wait", "record review", "record red", "record verdict", "record finish"):
        assert op in skill
    assert "docs/pipeline/ も作らない" not in skill


# ---- D0004：報告を返せるようにし、worktree の中でも書けるようにする ------------------------------


@pytest.mark.parametrize("agent", AGENTS)
def test_d0004_ac01_subagents_can_hand_back_their_report(guard, agent):
    """D0004-AC-01: 報告を親に渡す道具（SubagentHandback）は止めない（止めると、どの段も報告を返せない）。"""
    assert call(guard, agent, "SubagentHandback", message="報告") is None


def make_checkout(base: Path, name: str, git_is_file: bool) -> Path:
    """git の作業フォルダの形（.git がフォルダ＝ふつうの clone、.git がファイル＝worktree）を一時フォルダに作る。"""
    top = base / name
    (top / "tests" / "sub").mkdir(parents=True)
    if git_is_file:
        (top / ".git").write_text("gitdir: ../main/.git/worktrees/x\n", encoding="utf-8")
    else:
        (top / ".git").mkdir()
    return top


def test_d0004_ac02_root_is_the_checkout_the_agent_works_in(guard, tmp_path):
    """D0004-AC-02: 書いてよい場所の基準は、サブエージェントがいる git の作業フォルダ（worktree なら worktree）。"""
    main = make_checkout(tmp_path, "main", git_is_file=False)
    wt = make_checkout(tmp_path, "wt", git_is_file=True)
    assert Path(guard.project_root(str(wt), str(main))) == wt
    assert Path(guard.project_root(str(wt / "tests" / "sub"), str(main))) == wt
    assert Path(guard.project_root(str(main / "tests"), None)) == main


def test_d0004_ac03_without_git_falls_back_to_project_dir(guard, tmp_path):
    """D0004-AC-03: git の作業フォルダが見つからなければ、今までどおり CLAUDE_PROJECT_DIR を基準にする。"""
    lone = tmp_path / "lone"
    lone.mkdir()
    main = make_checkout(tmp_path, "main", git_is_file=False)
    assert Path(guard.project_root(str(lone), str(main))) == main
    assert Path(guard.project_root(str(lone), None)) == lone


def test_d0004_ac04_worktree_agent_writes_only_inside_its_worktree(guard, monkeypatch, tmp_path):
    """D0004-AC-04: worktree にいるサブエージェントは、その worktree の中の決まった場所にだけ書ける。
    会話を始めた場所（CLAUDE_PROJECT_DIR）やほかの worktree には書けない（基準を変えても、すり抜けの道を開けない）。"""
    main = make_checkout(tmp_path, "main", git_is_file=False)
    wt = make_checkout(tmp_path, "wt", git_is_file=True)
    other = make_checkout(tmp_path, "other", git_is_file=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main))

    def decision(path: str) -> str:
        payload = {"agent_type": "pipe-in-tester", "tool_name": "Write", "tool_input": {"file_path": path}, "cwd": str(wt)}
        return run_main(guard, monkeypatch, json.dumps(payload))

    assert decision(str(wt / "tests" / "test_x.py")) == ""
    assert decision("tests/test_y.py") == ""  # 相対パスは worktree からとして見る
    for denied in (str(wt / "pipe_in" / "cli.py"), str(main / "tests" / "test_x.py"), str(other / "tests" / "test_x.py")):
        assert json.loads(decision(denied))["hookSpecificOutput"]["permissionDecision"] == "deny", denied
