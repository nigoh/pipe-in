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


# ---- D0001-AC-01: マーケットプレイスとプラグイン ----------------------------------------------


def test_marketplace_points_to_plugin():
    """D0006-AC-14: マーケットプレイスの名前・持ち主・プラグインの名前が pipe-in。"""
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    assert market["name"] == "pipe-in"
    assert market["owner"]["name"] == "pipe-in"
    assert [(p["name"], p["source"]) for p in market["plugins"]] == [("pipe-in", "./plugin")]
    manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "pipe-in"


def test_plugin_version():
    """D0006-AC-14: プラグインの版は 0.2.0。"""
    manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "0.2.0"


PLUGIN_TEXTS = [
    ".claude-plugin/marketplace.json",
    "plugin/.claude-plugin/plugin.json",
    "plugin/hooks/hooks.json",
    "plugin/skills/pipe-build/SKILL.md",
    "plugin/agents/pipe-builder.md",
]


def test_plugin_texts_use_new_names():
    """D0006-AC-14: スキルとエージェントの文に pipe-in-gen・/pipe-in:pipe-build があり、プラグインのどのファイルにも devpipe が無い。"""
    skill = (PLUGIN / "skills/pipe-build/SKILL.md").read_text(encoding="utf-8")
    agent = (PLUGIN / "agents/pipe-builder.md").read_text(encoding="utf-8")
    assert "/pipe-in:pipe-build" in skill and "pipe-in-gen" in skill
    assert "pipe-in-gen" in agent
    left = [rel for rel in PLUGIN_TEXTS if "devpipe" in (ROOT / rel).read_text(encoding="utf-8").lower()]
    assert left == []


def test_skill_stops_without_pipe_in_gen():
    """D0006-AC-14: スキルは始めに pipe-in-gen --help を確かめ、動かなければ入れ方を案内して止まる。"""
    _, body = frontmatter(PLUGIN / "skills/pipe-build/SKILL.md")
    first = body.split("## 1.")[0]
    assert "`pipe-in-gen --help`" in first
    assert "pip install -e ." in first
    assert "止まる" in first


# ---- D0001-AC-02: スキル --------------------------------------------------------------------


def test_skill_frontmatter_and_sections():
    """D0001-AC-02・D0006-AC-14: スキルの頭と、進め方の言葉（pipe-in-gen を使う）。"""
    fields, body = frontmatter(PLUGIN / "skills/pipe-build/SKILL.md")
    assert fields["name"] == "pipe-build"
    assert fields["description"] and fields["argument-hint"]
    assert fields["disable-model-invocation"] == "true"
    for word in ["作る", "直す", "pipe-in-gen", "pipe-builder", "前 → 後", "言われてから"]:
        assert word in body, word


# ---- D0001-AC-03: エージェント --------------------------------------------------------------


def test_agent_tools_and_ignored_fields():
    """D0001-AC-03・D0006-AC-14: エージェントの道具と、指示の言葉（pipe-in-gen check を使う）。"""
    fields, body = frontmatter(PLUGIN / "agents/pipe-builder.md")
    assert fields["name"] == "pipe-builder"
    assert fields["description"]
    assert [t.strip() for t in fields["tools"].split(",")] == ["Read", "Glob", "Grep", "Write", "Edit", "Bash"]
    for ignored in ["hooks", "permissionMode", "mcpServers"]:  # プラグインのエージェントでは黙って無視される
        assert ignored not in fields, ignored
    for word in ["on_fail", "routes", "next", "prompts/", "差し戻", "pipe-in-gen check", "--force"]:
        assert word in body, word


# ---- D0001-AC-04: フック --------------------------------------------------------------------


def test_hooks_call_guard_hook_without_shell():
    """D0001-AC-04・D0006-AC-14: フックはシェルを通さずに pipe-in-gen guard-hook を呼ぶ（どの道具でも動く）。"""
    hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
    entries = hooks["PreToolUse"]
    commands = [h for e in entries for h in e["hooks"]]
    assert any(e.get("matcher") == "*" for e in entries)  # どの道具でも動く
    assert {"type": "command", "command": "pipe-in-gen", "args": ["guard-hook"]}.items() <= commands[0].items()


# ---- D0001-AC-05: /pipe-craft は残っていない -------------------------------------------------


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
