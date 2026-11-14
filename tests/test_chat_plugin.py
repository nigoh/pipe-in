"""D0077-AC-33・34：プラグインの pipe-stage・pipe-probe（エージェント）と、スキル /pipe-in:pipe-run と、フックの形。

読むのはプラグインのファイル（plugin/）だけ。書かない。新しいファイル（agents/pipe-stage.md・agents/pipe-probe.md・skills/pipe-run/SKILL.md）は
まだ無いので、読めずに落ちるのが赤。hooks.json の形（matcher・command・args）が変わらないことは、今のまま通る検査として置く。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"

OLD_NAME = "dev" + "pipe"  # 前の版の名前（名前替えの検査 tests/test_rename.py に掛からないよう、つなげて書く）
STAGE_TOOLS = {"Read", "Glob", "Grep", "Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"}
PROBE_TOOLS = {"Write", "Read"}
FORBIDDEN = {"Agent", "Task", "PowerShell", "WebFetch", "WebSearch", "Skill", "ToolSearch"}


def frontmatter(path: Path) -> tuple[dict[str, str], str]:
    """--- で囲んだ頭の部分を、1行1項目の「名前: 値」として読む（tests/test_plugin.py と同じ読み方）。"""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, f"{path} に frontmatter がない"
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields, m.group(2)


def tools_of(fields: dict[str, str]) -> list[str]:
    return [t.strip() for t in fields["tools"].split(",") if t.strip()]


# ---- AC-33 ----------------------------------------------------------------------------------


def test_d0077_ac33_pipe_stageのtoolsはFR13のとおりでAgentなどを含まない():
    """D0077-AC-33: plugin/agents/pipe-stage.md の tools が、読む道具・Write・Edit・MultiEdit・NotebookEdit・Bash で、Agent・Task・PowerShell・Web・MCP・Skill を含まない。"""
    fields, body = frontmatter(PLUGIN / "agents" / "pipe-stage.md")
    assert fields["name"] == "pipe-stage"
    assert fields["description"]
    tools = tools_of(fields)
    assert set(tools) == STAGE_TOOLS and len(tools) == len(STAGE_TOOLS), tools
    assert not (set(tools) & FORBIDDEN)
    assert not [t for t in tools if t.startswith("mcp__")]
    for ignored in ["hooks", "permissionMode", "mcpServers"]:  # プラグインのエージェントでは黙って無視される
        assert ignored not in fields, ignored
    assert fields.get("model") == "inherit"
    assert OLD_NAME not in body.lower()


def test_d0077_ac33_pipe_stageの本文は渡された指示だけに従うと書く():
    """D0077-AC-33: pipe-stage の本文に、渡された指示だけに従う・範囲外は止められる（回避しない）・サブエージェントは呼べない・最後に短い要約を返す、が書かれている。"""
    _, body = frontmatter(PLUGIN / "agents" / "pipe-stage.md")
    for word in ["渡された指示", "範囲", "回避", "STATUS:", "PROBLEM:"]:
        assert word in body, word


def test_d0077_ac33_pipe_probeのtoolsはWriteとReadだけ():
    """D0077-AC-33: plugin/agents/pipe-probe.md の tools は Write と Read だけで、model が haiku。"""
    fields, body = frontmatter(PLUGIN / "agents" / "pipe-probe.md")
    assert fields["name"] == "pipe-probe"
    assert fields["description"]
    tools = tools_of(fields)
    assert set(tools) == PROBE_TOOLS and len(tools) == 2, tools
    assert fields.get("model") == "haiku"
    for ignored in ["hooks", "permissionMode", "mcpServers"]:
        assert ignored not in fields, ignored
    for word in ["1回", "止められた", "書けてしまった"]:
        assert word in body, word


AGENT_KEYS = {"name", "description", "tools", "model"}


def unknown_keys(fields: dict[str, str]) -> set[str]:
    """プラグインのエージェントの前書きで、決めた鍵の外にあるもの（未知の鍵は Claude Code が黙って無視するので、ここで見つける）。"""
    return set(fields) - AGENT_KEYS


@pytest.mark.parametrize("name", ["pipe-stage.md", "pipe-probe.md"])
def test_d0077_ac33_エージェントの前書きの鍵は決めたものだけ(name):
    """D0077-AC-33: pipe-stage・pipe-probe の前書きの鍵は name・description・tools・model だけ（綴りの誤りや、プラグインで効かない鍵を入れない。助言 V-05）。"""
    fields, _ = frontmatter(PLUGIN / "agents" / name)
    assert unknown_keys(fields) == set()
    assert {"name", "description", "tools"} <= set(fields)


def test_d0077_ac33_前書きの鍵の検査は知らない鍵を見つける():
    """D0077-AC-33: 検査そのものが、綴りの誤った鍵（tool）や、プラグインのエージェントで無視される鍵（hooks・permissionMode）を見つける。"""
    assert unknown_keys({"name": "x", "tool": "Read"}) == {"tool"}
    assert unknown_keys({"name": "x", "hooks": "{}", "permissionMode": "plan"}) == {"hooks", "permissionMode"}


# ---- AC-34 ----------------------------------------------------------------------------------


def hooks_entries() -> list[dict]:
    return json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]


def test_d0077_ac34_hooks_jsonの形は変わらない_守る():
    """D0077-AC-34: plugin/hooks/hooks.json の PreToolUse が pipe-in-gen guard-hook を呼ぶ形のまま、matcher は * （今のまま通る。守る）。"""
    entries = hooks_entries()
    assert [e["matcher"] for e in entries] == ["*"]
    assert [h["command"] for e in entries for h in e["hooks"]] == ["pipe-in-gen"]
    assert [h["args"] for e in entries for h in e["hooks"]] == [["guard-hook"]]


def test_d0077_ac34_hooks_jsonの説明にpipe_stageとpipe_probeが出る():
    """D0077-AC-34（設計 2.2）: hooks.json の description に、pipe-stage と pipe-probe を絞ることが出てくる（pipe-builder・pipe-judge の説明は残る）。"""
    data = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    for word in ["pipe-stage", "pipe-probe", "pipe-builder", "pipe-judge"]:
        assert word in data["description"], word


def test_d0077_ac34_plugin_jsonの説明に会話の中でパイプを流すが出る():
    """D0077-AC-34（設計 2.2）: plugin.json の description に「会話の中でパイプを流す」が出る。version は変えない（公開は人）。D0095 でプラグインの README・アイコン・項目を足したので 0.6.0 に上げた。
    D0096 で pipe-judge の断り方と返し方・pipe-builder の名前の決まりを直したので 0.6.1 に上げた。
    D0097-AC-17: スキルとエージェントの文を縮めたので 0.6.2（D0096 の 0.6.1 の決め打ちを置き換えた）。"""
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert "会話の中でパイプを流す" in manifest["description"]
    assert manifest["version"] == "0.6.2"


def test_d0077_ac34_スキルのfrontmatter():
    """D0077-AC-34: skills/pipe-run/SKILL.md の頭が、name・description・argument-hint を持ち、人が呼んだときだけ動く（disable-model-invocation）。"""
    fields, _ = frontmatter(PLUGIN / "skills" / "pipe-run" / "SKILL.md")
    assert fields["name"] == "pipe-run"
    assert fields["description"] and fields["argument-hint"]
    assert fields["disable-model-invocation"] == "true"


def test_d0077_ac34_スキルがchatの順と人の確認を先に取ることを書いている():
    """D0077-AC-34: スキルが chat start → probe → next の順と、開始の確認を先に取ること（--dry-run で見せてから）、確認は質問欄（AskUserQuestion）で聞くことを書いている。"""
    _, body = frontmatter(PLUGIN / "skills" / "pipe-run" / "SKILL.md")
    dry = body.index("--dry-run")
    start = body.index("chat start", dry)
    probe = body.index("chat probe", start)
    nxt = body.index("chat next", probe)
    assert dry < start < probe < nxt, "見せる（--dry-run）→ 始める → 確かめる → 次へ の順"
    assert body.index("開始の確認") < start, "開始の確認は、始める（chat start）より先に取る"
    assert "AskUserQuestion" in body
    for word in ["chat done", "chat review", "chat status", "agent_prompt", "pipe-in:pipe-stage", "pipe-in:pipe-probe", "probe_failed"]:
        assert word in body, word


def test_d0077_ac34_スキルは順番を自分で決めず記録に触らず守りなしでは流さない():
    """D0077-AC-34: スキルは、順番を自分で決めない・指示を変えずに渡す・記録を直接書かない・確かめに失敗したら止まる（守りなしで流す道を作らない）と書いている。"""
    _, body = frontmatter(PLUGIN / "skills" / "pipe-run" / "SKILL.md")
    for word in ["変えずに", "自分で決めない", "直接", "止まる", "守りなし", "pipe-in-gen --help"]:
        assert word in body, word
    assert OLD_NAME not in body.lower()
    assert "使用量は取れません" in body, "終わりに「使用量は取れません」を伝える"


def test_d0077_ac34_新しいファイルにpipe_in_genの名前が使われている():
    """D0077-AC-34: スキルとエージェントの文は新しい名前（pipe-in-gen）で書かれ、前の版の名前が無い。"""
    for rel in ["skills/pipe-run/SKILL.md", "agents/pipe-stage.md", "agents/pipe-probe.md"]:
        text = (PLUGIN / rel).read_text(encoding="utf-8")
        assert OLD_NAME not in text.lower(), rel
    assert "pipe-in-gen" in (PLUGIN / "skills" / "pipe-run" / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", ["agents/pipe-builder.md", "agents/pipe-judge.md"])
def test_d0077_ac34_既存のエージェントは変わらない_守る(rel):
    """D0077-AC-34: 既存のエージェント（pipe-builder・pipe-judge）の道具は変わらない（今のまま通る。守る）。"""
    fields, _ = frontmatter(PLUGIN / rel)
    want = {"agents/pipe-builder.md": ["Read", "Glob", "Grep", "Write", "Edit", "Bash"], "agents/pipe-judge.md": ["Read", "Grep", "Glob"]}[rel]
    assert sorted(tools_of(fields)) == sorted(want)
