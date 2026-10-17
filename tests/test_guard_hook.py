"""プラグインのフック（devpipe-gen guard-hook）：pipe-builder が触れる範囲を、パイプのフォルダと devpipe-gen だけに絞る。

フックはどのエージェントの道具の呼び出しでも動くので、pipe-builder 以外には何もしないことも確かめる。
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest


# 新しい部品はテストの中で読み込む（1件ずつ、何で落ちたかが見えるように）
def hook():
    from pipe_in_generator import guard_hook

    return guard_hook


BUILDER = "devpipe:pipe-builder"


def payload(tmp_path: Path, tool: str, tool_input: dict, agent_type: str | None = BUILDER) -> dict:
    p = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": str(tmp_path)}
    if agent_type is not None:
        p["agent_type"] = agent_type
    return p


def decide(tmp_path: Path, tool: str, tool_input: dict, agent_type: str | None = BUILDER, pipes_env: str | None = None):
    return hook().decide(payload(tmp_path, tool, tool_input, agent_type), pipes_env=pipes_env)


def pipe_file(tmp_path: Path, rel: str) -> str:
    return str(tmp_path / ".devpipe" / "pipes" / "devpipe-x" / rel)


# ---- D0001-AC-06: ほかのエージェントには何もしない -----------------------------------------


@pytest.mark.parametrize("agent_type", [None, "Explore", "general-purpose", "devpipe:other", "pipe-builder-x"])
def test_other_agents_pass(tmp_path, agent_type):
    assert decide(tmp_path, "Write", {"file_path": str(tmp_path / "src/app.py"), "content": "x"}, agent_type) is None
    assert decide(tmp_path, "Bash", {"command": "rm -rf build"}, agent_type) is None
    assert decide(tmp_path, "PowerShell", {"command": "Remove-Item x"}, agent_type) is None


# ---- D0001-AC-07: パイプのフォルダの決まったファイルには書ける ---------------------------------


@pytest.mark.parametrize("agent_type", ["devpipe:pipe-builder", "pipe-builder"])
@pytest.mark.parametrize("rel", ["pipe.toml", "README.md", "prompts/01_a.md"])
@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit"])
def test_builder_can_write_pipe_files(tmp_path, agent_type, rel, tool):
    assert decide(tmp_path, tool, {"file_path": pipe_file(tmp_path, rel)}, agent_type) is None


def test_builder_can_write_relative_and_legacy_paths(tmp_path):
    assert decide(tmp_path, "Write", {"file_path": ".devpipe/pipes/devpipe-x/pipe.toml"}) is None
    assert decide(tmp_path, "Write", {"file_path": str(tmp_path / "pipes/devpipe-x/prompts/02_b.md")}) is None


@pytest.mark.parametrize("tool", ["Read", "Glob", "Grep"])
def test_builder_can_read(tmp_path, tool):
    assert decide(tmp_path, tool, {"file_path": str(tmp_path / "src/app.py"), "pattern": "*"}) is None


# ---- D0001-AC-08: それ以外の場所には書けない ------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "src/app.py",
        ".devpipe/pipes/devpipe-x/layout.json",
        ".devpipe/pipes/devpipe-x/run.sh",
        ".devpipe/pipes/devpipe-x/prompts/a.py",
        ".devpipe/pipes/devpipe-x/prompts/sub/a.md",
        ".devpipe/pipes/devpipe-x/../../src/a.py",
        ".devpipe/pipes/devpipe-x/prompts/../../../src/a.md",
        ".devpipe/pipes/not-a-pipe/pipe.toml",
        ".devpipe/pipes/pipe.toml",
        "pipes/devpipe-X/pipe.toml",
        "CLAUDE.md",
        ".claude/settings.json",
    ],
)
def test_builder_cannot_write_outside(tmp_path, path):
    reason = decide(tmp_path, "Write", {"file_path": path, "content": "x"})
    assert reason, path
    assert decide(tmp_path, "Edit", {"file_path": str(tmp_path / path)}), path


def test_builder_write_without_path_is_denied(tmp_path):
    assert decide(tmp_path, "Write", {"content": "x"})


# ---- D0001-AC-09: Bash は devpipe-gen の list / new / check だけ -----------------------------


@pytest.mark.parametrize(
    "command",
    [
        "devpipe-gen list",
        "devpipe-gen list --project .",
        "devpipe-gen check x --project .",
        'devpipe-gen check x --project "C:/work/my app"',
        "devpipe-gen new x --from diagrams --project ../app",
    ],
)
def test_builder_bash_allows_devpipe_gen(tmp_path, command):
    assert decide(tmp_path, "Bash", {"command": command}) is None


@pytest.mark.parametrize(
    "command",
    [
        "devpipe-gen design x --purpose y",
        "devpipe-gen guard-hook",
        "devpipe-gen new x --from diagrams --force",
        "devpipe-gen check x && rm -rf /",
        "devpipe-gen check x; echo hi",
        "devpipe-gen check x | tee out.txt",
        "devpipe-gen check `whoami`",
        "devpipe-gen check $(whoami)",
        "devpipe-gen check x > src/app.py",
        "devpipe-gen check x < /etc/passwd",
        "devpipe-gen check x\nrm -rf /",
        "devpipe-gen check x & rm -rf /",
        "python -c 'open(\"a\",\"w\")'",
        "echo devpipe-gen list",
        "devpipe-genx list",
        "",
    ],
)
def test_builder_bash_denies_others(tmp_path, command):
    assert decide(tmp_path, "Bash", {"command": command}), command


# ---- D0001-AC-10: ほかの道具は止める（すり抜けの道） -------------------------------------------


@pytest.mark.parametrize(
    "tool,tool_input",
    [
        ("PowerShell", {"command": "devpipe-gen list"}),
        ("NotebookEdit", {"notebook_path": ".devpipe/pipes/devpipe-x/a.ipynb"}),
        ("WebFetch", {"url": "https://example.com"}),
        ("WebSearch", {"query": "x"}),
        ("mcp__github__create_issue", {}),
        ("Agent", {"prompt": "x", "subagent_type": "general-purpose"}),
        ("Task", {"prompt": "x"}),
        ("Skill", {"skill": "x"}),
    ],
)
def test_builder_other_tools_denied(tmp_path, tool, tool_input):
    assert decide(tmp_path, tool, tool_input), tool


# ---- D0001-AC-11: DEVPIPE_PIPES_DIR の下にも書ける -------------------------------------------


def test_builder_can_write_env_pipes_dir(tmp_path):
    shared = tmp_path / "shared-place"
    target = str(shared / "devpipe-x" / "pipe.toml")
    assert decide(tmp_path, "Write", {"file_path": target}) is not None  # 指定がなければ書けない
    assert decide(tmp_path, "Write", {"file_path": target}, pipes_env=str(shared)) is None
    assert decide(tmp_path, "Write", {"file_path": str(shared / "other.md")}, pipes_env=str(shared))


# ---- D0001-AC-12・入出力：壊れた入力は止める。止めるときは deny の JSON を出す ---------------------


def run_main(monkeypatch, text: str) -> tuple[int, str]:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    code = hook().main()
    return code, out.getvalue()


def test_broken_json_denies(monkeypatch):
    code, out = run_main(monkeypatch, "{not json")
    assert code == 0
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_main_prints_deny_json(tmp_path, monkeypatch):
    monkeypatch.delenv("DEVPIPE_PIPES_DIR", raising=False)
    code, out = run_main(monkeypatch, json.dumps(payload(tmp_path, "Write", {"file_path": "src/a.py"})))
    assert code == 0
    spec = json.loads(out)["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse"
    assert spec["permissionDecision"] == "deny"
    assert spec["permissionDecisionReason"]


def test_main_prints_nothing_when_allowed(tmp_path, monkeypatch):
    code, out = run_main(monkeypatch, json.dumps(payload(tmp_path, "Read", {"file_path": "src/a.py"})))
    assert (code, out) == (0, "")
    code, out = run_main(monkeypatch, json.dumps(payload(tmp_path, "Bash", {"command": "rm -rf /"}, agent_type=None)))
    assert (code, out) == (0, "")


def test_cli_dispatches_guard_hook(tmp_path, monkeypatch):
    from pipe_in_generator import cli

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload(tmp_path, "Write", {"file_path": "src/a.py"}))))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    assert cli.main(["guard-hook"]) == 0
    assert json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"] == "deny"
