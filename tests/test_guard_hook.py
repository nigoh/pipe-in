"""プラグインのフック（pipe-in-gen guard-hook）：pipe-builder が触れる範囲を、パイプのフォルダと pipe-in-gen だけに絞る。

フックはどのエージェントの道具の呼び出しでも動くので、pipe-builder 以外には何もしないことも確かめる。
前の版の置き場所・フォルダ名（.devpipe/pipes/devpipe-<名前>/）・環境変数（DEVPIPE_PIPES_DIR）と、
古いプラグインのエージェント（devpipe:pipe-builder）も同じに守る。
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


BUILDER = "pipe-in:pipe-builder"
BUILDERS = ["pipe-in:pipe-builder", "devpipe:pipe-builder", "pipe-builder"]
# （置き場所, フォルダ名）の組。新旧どちらの組み合わせでも同じに扱う
PLACES = [
    (".pipe-in/pipes", "pipe-in-x"),
    (".devpipe/pipes", "devpipe-x"),
    (".pipe-in/pipes", "devpipe-x"),
    (".devpipe/pipes", "pipe-in-x"),
    ("pipes", "pipe-in-x"),
    ("pipes", "devpipe-x"),
]


def payload(tmp_path: Path, tool: str, tool_input: dict, agent_type: str | None = BUILDER) -> dict:
    p = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": str(tmp_path)}
    if agent_type is not None:
        p["agent_type"] = agent_type
    return p


def decide(tmp_path: Path, tool: str, tool_input: dict, agent_type: str | None = BUILDER, pipes_env=None):
    return hook().decide(payload(tmp_path, tool, tool_input, agent_type), pipes_env=pipes_env)


# ---- D0006-AC-12: ほかのエージェントには何もしない -----------------------------------------


@pytest.mark.parametrize("agent_type", [None, "Explore", "general-purpose", "pipe-in:other", "devpipe:other", "pipe-builder-x"])
def test_other_agents_pass(tmp_path, agent_type):
    """D0006-AC-12: pipe-builder でないエージェント（無し・ほかの名前・プラグインのほかのエージェント）には何もしない。"""
    assert decide(tmp_path, "Write", {"file_path": str(tmp_path / "src/app.py"), "content": "x"}, agent_type) is None
    assert decide(tmp_path, "Bash", {"command": "rm -rf build"}, agent_type) is None
    assert decide(tmp_path, "PowerShell", {"command": "Remove-Item x"}, agent_type) is None


# ---- D0006-AC-11: パイプのフォルダの決まったファイルには書ける ---------------------------------


@pytest.mark.parametrize("agent_type", BUILDERS)
@pytest.mark.parametrize("place,folder", PLACES)
@pytest.mark.parametrize("rel", ["pipe.toml", "README.md", "prompts/01_a.md"])
@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit"])
def test_builder_can_write_pipe_files(tmp_path, agent_type, place, folder, rel, tool):
    """D0006-AC-11: 新旧どちらの置き場所・フォルダ名でも、pipe.toml・README.md・prompts/*.md には書ける。"""
    path = str(tmp_path / place / folder / rel)
    assert decide(tmp_path, tool, {"file_path": path}, agent_type) is None


@pytest.mark.parametrize(
    "path",
    [
        ".pipe-in/pipes/pipe-in-x/pipe.toml",
        ".pipe-in/pipes/pipe-in-x/prompts/a.md",
        ".devpipe/pipes/devpipe-x/README.md",
        "pipes/pipe-in-x/prompts/02_b.md",
        "pipes/devpipe-x/prompts/02_b.md",
    ],
)
def test_builder_can_write_relative_and_legacy_paths(tmp_path, path):
    """D0006-AC-11: 相対パスでも、前の版の置き場所（pipes/）でも書ける。"""
    assert decide(tmp_path, "Write", {"file_path": path}) is None


@pytest.mark.parametrize("tool", ["Read", "Glob", "Grep"])
def test_builder_can_read(tmp_path, tool):
    assert decide(tmp_path, tool, {"file_path": str(tmp_path / "src/app.py"), "pattern": "*"}) is None


# ---- D0006-AC-11: それ以外の場所には書けない ------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "src/a.py",
        "src/app.py",
        ".pipe-in/a.md",
        ".pipe-in/pipes/pipe-in-x/run.sh",
        ".pipe-in/pipes/pipe-in-x/layout.json",
        ".pipe-in/pipes/pipe-in-x/prompts/sub/a.md",
        ".pipe-in/pipes/pipe-in-x/prompts/a.py",
        ".pipe-in/pipes/pipe-in-x/../../src/a.py",
        ".pipe-in/pipes/pipe-in-x/prompts/../../../src/a.md",
        ".pipe-in/pipes/x/pipe.toml",
        ".pipe-in/pipes/pipe-in/pipe.toml",
        ".pipe-in/pipes/pipe-in-/pipe.toml",
        ".pipe-in/pipes/pipe.toml",
        ".devpipe/pipes/devpipe-x/layout.json",
        ".devpipe/pipes/devpipe-x/run.sh",
        ".devpipe/pipes/devpipe-x/prompts/a.py",
        ".devpipe/pipes/devpipe-x/prompts/sub/a.md",
        ".devpipe/pipes/devpipe-x/../../src/a.py",
        ".devpipe/pipes/not-a-pipe/pipe.toml",
        ".devpipe/pipes/devpipe/pipe.toml",
        ".devpipe/pipes/pipe.toml",
        "pipes/devpipe-X/pipe.toml",
        "pipes/pipe-in-X/pipe.toml",
        "pipes/pipe-inx/pipe.toml",
        "CLAUDE.md",
        ".claude/settings.json",
    ],
)
def test_builder_cannot_write_outside(tmp_path, path):
    """D0006-AC-11: 決まったファイルのほか・頭や名前の無いフォルダ・置き場所の直下・.. を含むパスには書けない。"""
    reason = decide(tmp_path, "Write", {"file_path": path, "content": "x"})
    assert reason, path
    assert decide(tmp_path, "Edit", {"file_path": str(tmp_path / path)}), path


def test_builder_write_without_path_is_denied(tmp_path):
    assert decide(tmp_path, "Write", {"content": "x"})


def test_deny_message_shows_new_folder_name(tmp_path):
    """D0006-AC-11: 止める文が示す書ける場所は、新しいフォルダ名（pipe-in-<名前>/）。"""
    reason = decide(tmp_path, "Write", {"file_path": "src/a.py"})
    assert "pipe-in-<名前>" in reason


# ---- D0006-AC-12: Bash は pipe-in-gen の list / new / check だけ -----------------------------


@pytest.mark.parametrize(
    "command",
    [
        "pipe-in-gen list",
        "pipe-in-gen list --project p",
        "pipe-in-gen list --project .",
        "pipe-in-gen check x",
        "pipe-in-gen check x --project .",
        'pipe-in-gen check x --project "C:/work/my app"',
        "pipe-in-gen new x --from diagrams",
        "pipe-in-gen new x --from diagrams --project ../app",
    ],
)
def test_builder_bash_allows_pipe_in_gen(tmp_path, command):
    """D0006-AC-12: pipe-in-gen list / new / check を許す。"""
    assert decide(tmp_path, "Bash", {"command": command}) is None


@pytest.mark.parametrize(
    "command",
    [
        "devpipe-gen new x",
        "devpipe-gen list",
        "devpipe-gen check x",
        "pipe-in --pipe x",
        "pipe-in-gen design x",
        "pipe-in-gen design x --purpose y",
        "pipe-in-gen guard-hook",
        "pipe-in-gen new x --force",
        "pipe-in-gen new x --from diagrams --force",
        "pipe-in-gen list; rm -rf .",
        "pipe-in-gen list | sh",
        "pipe-in-gen check x && rm -rf /",
        "pipe-in-gen check x; echo hi",
        "pipe-in-gen check x | tee out.txt",
        "pipe-in-gen check `whoami`",
        "pipe-in-gen check $(whoami)",
        "pipe-in-gen check x > src/app.py",
        "pipe-in-gen check x < /etc/passwd",
        "pipe-in-gen check x\nrm -rf /",
        "pipe-in-gen check x & rm -rf /",
        "python -c 'open(\"a\",\"w\")'",
        "echo pipe-in-gen list",
        "pipe-in-genx list",
        "",
    ],
)
def test_builder_bash_denies_others(tmp_path, command):
    """D0006-AC-12: 古い名前の devpipe-gen・ほかのコマンド・つなぐ記号・design・guard-hook・--force は止める。"""
    assert decide(tmp_path, "Bash", {"command": command}), command


def test_bash_deny_message_names_pipe_in_gen(tmp_path):
    """D0006-AC-12: 止める文は、使えるコマンドを pipe-in-gen と示す。"""
    reason = decide(tmp_path, "Bash", {"command": "devpipe-gen list"})
    assert reason is not None, "devpipe-gen が止められていない"
    assert "pipe-in-gen list / new / check" in reason


# ---- D0006-AC-12: ほかの道具は止める（すり抜けの道） -------------------------------------------


@pytest.mark.parametrize("agent_type", BUILDERS)
@pytest.mark.parametrize(
    "tool,tool_input",
    [
        ("PowerShell", {"command": "pipe-in-gen list"}),
        ("NotebookEdit", {"notebook_path": ".pipe-in/pipes/pipe-in-x/a.ipynb"}),
        ("WebFetch", {"url": "https://example.com"}),
        ("WebSearch", {"query": "x"}),
        ("mcp__x__y", {}),
        ("mcp__github__create_issue", {}),
        ("Agent", {"prompt": "x", "subagent_type": "general-purpose"}),
        ("Task", {"prompt": "x"}),
        ("Skill", {"skill": "x"}),
    ],
)
def test_builder_other_tools_denied(tmp_path, agent_type, tool, tool_input):
    """D0006-AC-12: PowerShell・MCP・Agent・Task・Web・NotebookEdit・Skill は、どの pipe-builder の名前でも止める。"""
    assert decide(tmp_path, tool, tool_input, agent_type), tool


CASES = [
    ("Write", {"file_path": ".pipe-in/pipes/pipe-in-x/pipe.toml"}),
    ("Write", {"file_path": ".devpipe/pipes/devpipe-x/prompts/a.md"}),
    ("Write", {"file_path": "src/a.py"}),
    ("Edit", {"file_path": ".pipe-in/pipes/pipe-in-x/run.sh"}),
    ("Bash", {"command": "pipe-in-gen list"}),
    ("Bash", {"command": "devpipe-gen list"}),
    ("Bash", {"command": "pipe-in-gen new x --force"}),
    ("PowerShell", {"command": "pipe-in-gen list"}),
    ("mcp__x__y", {}),
    ("Read", {"file_path": "src/a.py"}),
]


def test_every_builder_name_is_checked(tmp_path):
    """D0006-AC-12: agent_type が pipe-builder・pipe-in:pipe-builder・devpipe:pipe-builder のどれでも、結果が同じ。"""
    results = {a: [decide(tmp_path, t, i, a) is None for t, i in CASES] for a in BUILDERS}
    assert results["pipe-in:pipe-builder"] == [True, True, False, False, True, False, False, False, False, True]
    assert results["devpipe:pipe-builder"] == results["pipe-in:pipe-builder"]
    assert results["pipe-builder"] == results["pipe-in:pipe-builder"]


# ---- D0006-AC-11・AC-13: 環境変数で指した置き場所の下にも書ける -------------------------------------


@pytest.mark.parametrize("folder", ["pipe-in-x", "devpipe-x"])
def test_builder_can_write_env_pipes_dir(tmp_path, folder):
    """D0006-AC-11: 環境変数で指した置き場所の下の pipe-in-x/・devpipe-x/ の決まったファイルに書ける。ほかのファイルには書けない。"""
    shared = tmp_path / "shared-place"
    target = str(shared / folder / "pipe.toml")
    assert decide(tmp_path, "Write", {"file_path": target}) is not None  # 指定がなければ書けない
    assert decide(tmp_path, "Write", {"file_path": target}, pipes_env=str(shared)) is None
    assert decide(tmp_path, "Write", {"file_path": target}, pipes_env=[str(shared)]) is None
    assert decide(tmp_path, "Write", {"file_path": str(shared / "other.md")}, pipes_env=str(shared))
    assert decide(tmp_path, "Write", {"file_path": str(shared / folder / "run.sh")}, pipes_env=[str(shared)])


def test_builder_can_write_under_both_env_places(tmp_path):
    """D0006-AC-13: 置き場所を2つ渡せば、どちらの下にも書ける。どちらの下でも決まったファイル以外は止める。"""
    new, old = tmp_path / "new-place", tmp_path / "old-place"
    both = [str(new), str(old)]
    assert decide(tmp_path, "Write", {"file_path": str(new / "pipe-in-x" / "pipe.toml")}, pipes_env=both) is None
    assert decide(tmp_path, "Write", {"file_path": str(old / "devpipe-x" / "README.md")}, pipes_env=both) is None
    assert decide(tmp_path, "Write", {"file_path": str(old / "other.md")}, pipes_env=both)
    assert decide(tmp_path, "Write", {"file_path": str(new / "pipe-in-x" / "layout.json")}, pipes_env=both)


@pytest.mark.parametrize(
    "environ,want",
    [
        ({}, []),
        ({"PIPE_IN_PIPES_DIR": "new"}, ["new"]),
        ({"DEVPIPE_PIPES_DIR": "old"}, ["old"]),
        ({"PIPE_IN_PIPES_DIR": "new", "DEVPIPE_PIPES_DIR": "old"}, ["new", "old"]),
        ({"PIPE_IN_PIPES_DIR": "", "DEVPIPE_PIPES_DIR": "old"}, ["old"]),
        ({"OTHER": "x"}, []),
    ],
)
def test_env_pipes_dirs_reads_both_names(environ, want):
    """D0006-AC-13: env_pipes_dirs は PIPE_IN_PIPES_DIR・DEVPIPE_PIPES_DIR のうち空でないものを、この順に返す。"""
    assert hook().env_pipes_dirs(environ) == want


# ---- 入出力：壊れた入力は止める。止めるときは deny の JSON を出す ---------------------------------


def run_main(monkeypatch, text: str) -> tuple[int, str]:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    code = hook().main()
    return code, out.getvalue()


@pytest.fixture
def no_env(monkeypatch):
    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    monkeypatch.delenv("DEVPIPE_PIPES_DIR", raising=False)
    return monkeypatch


def test_broken_json_denies(monkeypatch):
    code, out = run_main(monkeypatch, "{not json")
    assert code == 0
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_main_prints_deny_json(tmp_path, no_env):
    """D0006-AC-13: 環境変数が無いとき、外への書き込みには deny の JSON を出す。"""
    code, out = run_main(no_env, json.dumps(payload(tmp_path, "Write", {"file_path": "src/a.py"})))
    assert code == 0
    spec = json.loads(out)["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse"
    assert spec["permissionDecision"] == "deny"
    assert spec["permissionDecisionReason"]


@pytest.mark.parametrize("env_name,folder", [("PIPE_IN_PIPES_DIR", "pipe-in-x"), ("DEVPIPE_PIPES_DIR", "devpipe-x")])
def test_main_allows_env_place(tmp_path, no_env, env_name, folder):
    """D0006-AC-13: main は PIPE_IN_PIPES_DIR・DEVPIPE_PIPES_DIR のどちらで指した置き場所の下への書き込みも許す。"""
    shared = tmp_path / "shared"
    no_env.setenv(env_name, str(shared))
    code, out = run_main(no_env, json.dumps(payload(tmp_path, "Write", {"file_path": str(shared / folder / "pipe.toml")})))
    assert (code, out) == (0, "")


def test_main_allows_both_env_places(tmp_path, no_env):
    """D0006-AC-13: 両方の環境変数があれば、両方の置き場所の下を許す。"""
    new, old = tmp_path / "new-place", tmp_path / "old-place"
    no_env.setenv("PIPE_IN_PIPES_DIR", str(new))
    no_env.setenv("DEVPIPE_PIPES_DIR", str(old))
    for target in (new / "pipe-in-x" / "pipe.toml", old / "devpipe-x" / "pipe.toml"):
        code, out = run_main(no_env, json.dumps(payload(tmp_path, "Write", {"file_path": str(target)})))
        assert (code, out) == (0, ""), target
    code, out = run_main(no_env, json.dumps(payload(tmp_path, "Write", {"file_path": str(old / "other.md")})))
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


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
