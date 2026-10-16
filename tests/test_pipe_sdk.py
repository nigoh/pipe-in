"""パイプの段に書いた Agent SDK の設定（許可のモード・考える量・予備のモデル・段の決まり・追加のフォルダ・
サブエージェント・MCP サーバー）を読み、検査し、SDK に渡す形にする。SDK は呼ばない。"""

from __future__ import annotations

from pathlib import Path

import pytest

from devpipe.engine.config import load_config
from devpipe.engine.guard import check_tool
from devpipe.pipe import definition as pd
from devpipe.pipe import specs as ps

FULL = '''
[pipe]
kind = "linear"
label = "SDK の設定"

[[stages]]
name = "survey"
label = "調査"
output = "01_survey.md"
access = "read"
prompt = "調べる"
permission_mode = "plan"
max_thinking_tokens = 16000
fallback_model = "sonnet"
system_append = "表を使って書く"
add_dirs = ["../shared-docs"]
mcp = ["mcp__jira__get_issue"]
[stages.agents.module-reader]
description = "1つのモジュールを読んで要点を返す"
prompt = "渡されたモジュールだけを読む"
tools = ["Read", "Grep"]
model = "haiku"
[stages.mcp_servers.jira]
type = "http"
url = "https://mcp.example.com/jira"
[stages.mcp_servers.local]
type = "stdio"
command = "node"
args = ["server.js", "--quiet"]
'''


def make(project: Path, toml: str, name: str = "p") -> pd.PipeDef:
    d = project / "pipes" / f"devpipe-{name}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pipe.toml").write_text(toml, encoding="utf-8")
    return pd.load_pipe(d)


def cfg_for(project: Path, pipe: pd.PipeDef):
    return load_config(project, None, auto_approve=True).for_pipe(pipe.name, own_work_dir=True)


def survey_spec(project: Path, toml: str = FULL):
    pipe = make(project, toml)
    return ps.build_pipe_specs(cfg_for(project, pipe), pipe)["survey"], cfg_for(project, pipe)


# ---- 読み込み ------------------------------------------------------------------


def test_load_sdk_settings(tmp_path):
    s = make(tmp_path, FULL).stages[0]
    assert (s.permission_mode, s.max_thinking_tokens, s.fallback_model) == ("plan", 16000, "sonnet")
    assert s.system_append == "表を使って書く"
    assert s.add_dirs == ["../shared-docs"]
    a = s.agents["module-reader"]
    assert (a.description, a.prompt, a.tools, a.model) == ("1つのモジュールを読んで要点を返す", "渡されたモジュールだけを読む", ["Read", "Grep"], "haiku")
    assert s.mcp_servers["jira"].type == "http" and s.mcp_servers["jira"].url == "https://mcp.example.com/jira"
    assert s.mcp_servers["local"].command == "node" and s.mcp_servers["local"].args == ["server.js", "--quiet"]
    assert pd.check_pipe(make(tmp_path, FULL), tmp_path) == []


def test_sdk_settings_are_optional(tmp_path):
    s = make(tmp_path, '[pipe]\nkind = "linear"\nlabel = "x"\n[[stages]]\nname = "a"\nlabel = "a"\noutput = "a.md"\nprompt = "x"\n').stages[0]
    assert (s.permission_mode, s.max_thinking_tokens, s.fallback_model, s.system_append) == (None, None, None, None)
    assert s.add_dirs == [] and s.agents == {} and s.mcp_servers == {}


# ---- 検査 ------------------------------------------------------------------


BAD = {
    "bypass": (FULL.replace('permission_mode = "plan"', 'permission_mode = "bypassPermissions"'), "permission_mode"),
    "unknown_mode": (FULL.replace('permission_mode = "plan"', 'permission_mode = "yolo"'), "permission_mode"),
    "thinking_zero": (FULL.replace("max_thinking_tokens = 16000", "max_thinking_tokens = 0"), "max_thinking_tokens"),
    "add_dir_absolute": (FULL.replace('add_dirs = ["../shared-docs"]', 'add_dirs = ["/etc"]'), "add_dirs"),
    "agent_bad_name": (FULL.replace("[stages.agents.module-reader]", "[stages.agents.Bad_Name]"), "サブエージェントの名前"),
    "agent_no_description": (FULL.replace('description = "1つのモジュールを読んで要点を返す"\n', ""), "description"),
    "agent_powershell": (FULL.replace('tools = ["Read", "Grep"]', 'tools = ["Read", "PowerShell"]'), "PowerShell"),
    "agent_nested": (FULL.replace('tools = ["Read", "Grep"]', 'tools = ["Read", "Task"]'), "Task"),
    "agent_beyond_stage": (FULL.replace('tools = ["Read", "Grep"]', 'tools = ["Read", "Bash"]'), "Bash"),
    "mcp_stdio_no_command": (FULL.replace('command = "node"\n', ""), "command"),
    "mcp_http_no_url": (FULL.replace('url = "https://mcp.example.com/jira"\n', ""), "url"),
    "mcp_unknown_type": (FULL.replace('type = "http"', 'type = "ws"'), "type"),
    "mcp_server_without_tools": (FULL.replace('mcp = ["mcp__jira__get_issue"]', "mcp = []"), "mcp__jira__"),
}


@pytest.mark.parametrize("case", list(BAD))
def test_sdk_settings_are_validated(tmp_path, case):
    text, word = BAD[case]
    errors = pd.check_pipe(make(tmp_path, text), tmp_path)
    assert any(word in e for e in errors), errors


def test_agent_tools_within_stage_tools_are_ok(tmp_path):
    text = FULL.replace('access = "read"', 'access = "code"\nbash = true').replace('tools = ["Read", "Grep"]', 'tools = ["Read", "Edit", "Bash"]')
    assert pd.check_pipe(make(tmp_path, text), tmp_path) == []


# ---- 段の設定（StageSpec） ---------------------------------------------------------


def test_spec_carries_sdk_settings(tmp_path):
    spec, cfg = survey_spec(tmp_path)
    assert (spec.permission_mode, spec.max_thinking_tokens, spec.fallback_model) == ("plan", 16000, "sonnet")
    assert "表を使って書く" in spec.system_append and "この段の決まり" in spec.system_append
    assert spec.add_dirs == [str((tmp_path / "../shared-docs").resolve())]
    assert spec.agents["module-reader"]["tools"] == ["Read", "Grep"]
    assert spec.mcp_servers["jira"] == {"type": "http", "url": "https://mcp.example.com/jira"}
    assert spec.mcp_servers["local"] == {"type": "stdio", "command": "node", "args": ["server.js", "--quiet"]}


def test_subagent_tools_are_allowed_only_with_agents(tmp_path):
    spec, cfg = survey_spec(tmp_path)

    def check(s, tool, **inp):
        return check_tool(tool, inp, project_dir=cfg.project_dir, can_write=s.can_write, allow_bash=s.allow_bash,
                          write_scope_hint=s.write_scope_hint, allowed_tools=s.allowed_tools, fetch_domains=s.fetch_domains)

    assert check(spec, "Task", prompt="x") is None
    assert check(spec, "Agent", prompt="x") is None
    assert check(spec, "PowerShell", command="ls") is not None  # ほかの道は開かない
    assert check(spec, "Write", file_path="src/a.py") is not None  # 書き込みの範囲はそのまま
    assert check(spec, "Write", file_path="../shared-docs/a.md") is not None  # 追加のフォルダは読むだけ

    plain, cfg2 = survey_spec(tmp_path / "plain", FULL.split("[stages.agents.module-reader]")[0])
    assert check(plain, "Task", prompt="x") is not None
    assert check(plain, "Agent", prompt="x") is not None


# ---- SDK に渡す形 -----------------------------------------------------------------


def test_sdk_options_from_spec(tmp_path):
    from devpipe.engine.runner import sdk_options

    spec, cfg = survey_spec(tmp_path)
    opts = sdk_options(spec, cfg, resume="s-1")
    assert opts["permission_mode"] == "plan"
    assert opts["max_thinking_tokens"] == 16000
    assert opts["fallback_model"] == "sonnet"
    assert opts["add_dirs"] == spec.add_dirs
    assert opts["agents"]["module-reader"] == {"description": "1つのモジュールを読んで要点を返す", "prompt": "渡されたモジュールだけを読む", "tools": ["Read", "Grep"], "model": "haiku"}
    assert opts["mcp_servers"]["local"] == {"type": "stdio", "command": "node", "args": ["server.js", "--quiet"]}
    assert opts["resume"] == "s-1"
    assert opts["system_prompt"]["append"] == spec.system_append
    assert "Task" in opts["allowed_tools"]


def test_sdk_options_defaults_for_dev_flow(tmp_path):
    from devpipe.dev import specs as dev_specs
    from devpipe.engine.runner import sdk_options

    cfg = load_config(tmp_path, None, auto_approve=True)
    opts = sdk_options(dev_specs.build_specs(cfg)["requirements"], cfg, resume=None)
    assert opts["permission_mode"] == "default"
    assert "agents" not in opts and "mcp_servers" not in opts and "add_dirs" not in opts
    assert "max_thinking_tokens" not in opts and "fallback_model" not in opts
    assert opts["max_turns"] == 40
