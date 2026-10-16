"""Claude Code のプラグイン（.claude-plugin/ と plugin/）：パイプを作る・直すスキルとエージェントと、止めるフックの形。"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"


def frontmatter(path: Path) -> tuple[dict[str, str], str]:
    """--- で囲んだ頭の部分を、1行1項目の「名前: 値」として読む（このテストで使う範囲だけ）。"""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, f"{path} に frontmatter がない"
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields, m.group(2)


# ---- AC-01: マーケットプレイスとプラグイン ----------------------------------------------


def test_marketplace_points_to_plugin():
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    assert market["name"] == "devpipe"
    assert market["owner"]["name"]
    assert [(p["name"], p["source"]) for p in market["plugins"]] == [("devpipe", "./plugin")]
    manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "devpipe"


# ---- AC-02: スキル --------------------------------------------------------------------


def test_skill_frontmatter_and_sections():
    fields, body = frontmatter(PLUGIN / "skills/pipe-build/SKILL.md")
    assert fields["name"] == "pipe-build"
    assert fields["description"] and fields["argument-hint"]
    assert fields["disable-model-invocation"] == "true"
    for word in ["作る", "直す", "devpipe-gen", "pipe-builder", "前 → 後", "言われてから"]:
        assert word in body, word


# ---- AC-03: エージェント --------------------------------------------------------------


def test_agent_tools_and_ignored_fields():
    fields, body = frontmatter(PLUGIN / "agents/pipe-builder.md")
    assert fields["name"] == "pipe-builder"
    assert fields["description"]
    assert [t.strip() for t in fields["tools"].split(",")] == ["Read", "Glob", "Grep", "Write", "Edit", "Bash"]
    for ignored in ["hooks", "permissionMode", "mcpServers"]:  # プラグインのエージェントでは黙って無視される
        assert ignored not in fields, ignored
    for word in ["on_fail", "routes", "next", "prompts/", "差し戻", "devpipe-gen check", "--force"]:
        assert word in body, word


# ---- AC-04: フック --------------------------------------------------------------------


def test_hooks_call_guard_hook_without_shell():
    hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
    entries = hooks["PreToolUse"]
    commands = [h for e in entries for h in e["hooks"]]
    assert any(e.get("matcher") in ("*", None, "") for e in entries)  # どの道具でも動く
    assert {"type": "command", "command": "devpipe-gen", "args": ["guard-hook"]}.items() <= commands[0].items()


# ---- AC-05: /pipe-craft は残っていない -------------------------------------------------


def test_pipe_craft_is_gone():
    assert not (ROOT / ".claude/skills/pipe-craft").exists()
    skip = {".git", ".venv", "node_modules", "out", "__pycache__", "pipes", "docs"}
    found = []
    for p in ROOT.rglob("*"):
        if p.is_file() and not skip & set(p.relative_to(ROOT).parts) and p.suffix in {".md", ".py", ".ts", ".json", ".toml"}:
            if p.name == "test_plugin.py":
                continue
            if "/pipe-craft" in p.read_text(encoding="utf-8", errors="ignore"):
                found.append(p.relative_to(ROOT).as_posix())
    assert found == []
