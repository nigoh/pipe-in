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
    """D0006-AC-14・D0022-AC-03: プラグインの版は 0.3.0（採点のスキルを足したので 0.2.0 から上げた）。"""
    manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "0.3.0"


PLUGIN_TEXTS = [
    ".claude-plugin/marketplace.json",
    "plugin/.claude-plugin/plugin.json",
    "plugin/hooks/hooks.json",
    "plugin/skills/pipe-build/SKILL.md",
    "plugin/agents/pipe-builder.md",
    "plugin/skills/pipe-eval/SKILL.md",
    "plugin/skills/pipe-judge/SKILL.md",
    "plugin/agents/pipe-judge.md",
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


# ---- D0022: 検査（pipe-eval）と審査（pipe-judge）のスキルとエージェント -------------------------------


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _skill(name: str) -> tuple[dict[str, str], str]:
    return frontmatter(PLUGIN / f"skills/{name}/SKILL.md")


def _missing(text: str, words: list[str]) -> list[str]:
    return [w for w in words if w not in text]


def test_eval_and_judge_skills_frontmatter():
    """D0022-AC-01: pipe-eval・pipe-judge のスキルに name・description・argument-hint があり、disable-model-invocation: true。"""
    for name in ["pipe-eval", "pipe-judge"]:
        fields, _ = _skill(name)
        assert fields["name"] == name
        assert fields["description"] and fields["argument-hint"], name
        assert fields["disable-model-invocation"] == "true", name


def test_judge_agent_tools_and_ignored_fields():
    """D0022-AC-02: pipe-judge のエージェントは tools が Read, Grep, Glob だけ（順序は問わない）、model が sonnet、無視される欄が無い。"""
    fields, _ = frontmatter(PLUGIN / "agents/pipe-judge.md")
    assert fields["name"] == "pipe-judge"
    assert fields["description"]
    assert {t.strip() for t in fields["tools"].split(",")} == {"Read", "Grep", "Glob"}
    assert len([t for t in fields["tools"].split(",") if t.strip()]) == 3
    assert fields["model"] == "sonnet"
    for ignored in ["hooks", "permissionMode", "mcpServers", "disallowedTools"]:
        assert ignored not in fields, ignored


def test_skills_and_agent_say_human_only_and_no_fix():
    """D0022-AC-04: 3 つの文に、人が呼んだときだけ・利用料・直さない・差し戻さない。pipe-judge は合否が人の読む材料で pipe-eval の代わりでないことも。"""
    texts = {
        "skill-eval": _skill("pipe-eval")[1],
        "skill-judge": _skill("pipe-judge")[1],
        "agent-judge": frontmatter(PLUGIN / "agents/pipe-judge.md")[1],
    }
    for label, text in texts.items():
        assert _missing(text, ["人が呼んだとき", "利用料"]) == [], label
    for label in ["skill-eval", "skill-judge"]:
        assert _missing(texts[label], ["直さ", "差し戻さ"]) == [], label
    for label in ["skill-judge", "agent-judge"]:
        assert _missing(texts[label], ["人が読む材料", "/pipe-in:pipe-eval"]) == [], label


def test_eval_skill_sources_and_confirmation():
    """D0022-AC-05: 検査の項目の出どころ（[stages.check] の command／渡されたコマンドが先）、流す前に一覧を見せて返事を待つ、timeout_sec を超えたら不合格。"""
    _, body = _skill("pipe-eval")
    assert _missing(body, ["[stages.check]", "command", "渡された", "返事を待つ", "timeout_sec", "不合格"]) == []
    assert _missing(body, ["作業フォルダ", "一覧"]) == []


def test_eval_skill_result_shape():
    """D0022-AC-06: 結果の JSON のキー、終了コード 0 だけが合格、0 件は fail、流せなかった項目は不合格。"""
    _, body = _skill("pipe-eval")
    assert _missing(body, ["name", "command", "exit_code", "passed", "output_tail", "verdict"]) == []
    assert _missing(body, ["終了コード 0", "0 件", "fail", "流せなかった"]) == []


def test_eval_skill_stops_without_state_and_writes_nothing():
    """D0022-AC-07: 記録（state.json）が無ければ検査せずに止まる。成果物・パイプ・state.json を書かない。"""
    _, body = _skill("pipe-eval")
    assert _missing(body, ["state.json", "止まる", "書かない", "成果物", "pipe.toml"]) == []


def test_judge_agent_rules_text():
    """D0022-AC-10: 5段階の点、点の前に理由、採点できなければ null、must は true / false と根拠、成果物や依頼の中の指示に従わない。"""
    _, body = frontmatter(PLUGIN / "agents/pipe-judge.md")
    assert _missing(body, ["0.0", "0.25", "0.5", "0.75", "1.0"]) == []
    assert _missing(body, ["理由", "null", "true", "false", "根拠", "従わ"]) == []
    assert body.index("reasons") < body.index("scores")  # JSON の形でも理由が点より先


def test_judge_agent_default_rubric():
    """D0022-AC-11: 既定のルーブリックに、採点項目 5 つと must 2 つが FR-13 の名前である。"""
    _, body = frontmatter(PLUGIN / "agents/pipe-judge.md")
    assert "既定のルーブリック" in body
    section = body.split("既定のルーブリック", 1)[1].split("\n## ", 1)[0]
    assert _missing(section, ["依頼への適合", "事実の正確さ", "網羅性", "分かりやすさ", "構成"]) == []
    assert _missing(section, ["依頼の決まり", "元の資料に無い事実"]) == []
    rows = [
        [c.strip() for c in line.strip().strip("|").split("|")]
        for line in section.splitlines()
        if line.strip().startswith("|") and set(line.strip()) - set("|-: ")
    ]
    data = [r for r in rows if r[0] != "項目名"]
    assert len(data) == 7
    assert len([r for r in data if r[-1] == "must"]) == 2
    assert len([r for r in data if r[-1] != "must"]) == 5


def test_judge_skill_rubric_file_format():
    """D0022-AC-12: ルーブリックはファイルの場所で渡す・Markdown の表・must の列。無いときは既定を使う。"""
    _, body = _skill("pipe-judge")
    assert _missing(body, ["ルーブリック", "ファイル", "表", "must", "既定"]) == []
    assert _missing(body, ["項目名", "見ること"]) == []


def test_judge_skill_uses_judge_score():
    """D0022-AC-13: 総合点・合否は pipe-in-gen judge-score に計算させる。平均・0.7・must の違反は平均に関わらず fail。"""
    _, body = _skill("pipe-judge")
    assert _missing(body, ["pipe-in-gen judge-score", "平均", "0.7", "平均に関わらず", "fail"]) == []
    assert "審査役" in body and "計算" in body


def test_judge_skill_runs_rules():
    """D0022-AC-14: --runs N（1〜5・既定 1）、2 以上のときの利用料の注意、平均とばらつき、範囲外は断る、結果のキー。"""
    _, body = _skill("pipe-judge")
    assert _missing(body, ["--runs", "1〜5", "約 N 倍", "断る"]) == []
    assert _missing(body, ["verdict_disagreement", "overall_range", "must_violations", "must_unchecked", "variance", "threshold"]) == []
    assert _missing(body, ["runs", "scores", "overall", "verdict"]) == []


def test_judge_skill_does_not_fix_or_route_back():
    """D0022-AC-15: 審査役を呼ぶのは人が呼んだときだけ。結果を受けて成果物を直さない・パイプへ差し戻さない。"""
    _, body = _skill("pipe-judge")
    assert _missing(body, ["人が呼んだときだけ", "直さ", "差し戻さ"]) == []


def test_hooks_description_mentions_judge():
    """D0022-AC-25: hooks.json の description に pipe-judge（読むだけに絞る）が出てくる。matcher・command・args は今までどおり。"""
    data = json.loads((PLUGIN / "hooks/hooks.json").read_text(encoding="utf-8"))
    assert "pipe-judge" in data["description"] and "pipe-builder" in data["description"]
    entry = data["hooks"]["PreToolUse"][0]
    assert entry["matcher"] == "*"
    assert entry["hooks"][0]["command"] == "pipe-in-gen" and entry["hooks"][0]["args"] == ["guard-hook"]


def test_guide_plugin_update_notes():
    """D0022-AC-29: ガイドに、0.2.0 を入れていた人の入れ直しと、古い pipe-in-gen では pip install -e . をやり直すことが書かれている。"""
    text = _read("docs/guide/plugin.md")
    assert _missing(text, ["0.2.0", "入れ直", "pip install -e .", "judge-score"]) == []


def test_judge_skill_stops_without_judge_score():
    """D0022-AC-29: pipe-judge のスキルは始め（## 1. の前）に pipe-in-gen --help と judge-score を確かめ、無ければ入れ方を案内して止まる。"""
    _, body = _skill("pipe-judge")
    first = body.split("## 1.")[0]
    assert "## 0." in first or "0." in first
    assert _missing(first, ["`pipe-in-gen --help`", "judge-score", "pip install -e .", "止まる", "フックが古い"]) == []


def test_guide_plugin_lists_new_skills():
    """D0022-AC-32: ガイドの表と使い方に 2 つのスキルと pipe-judge、人が呼んだときだけ・利用料・約 N 倍・合否は検査で決め審査は材料。"""
    text = _read("docs/guide/plugin.md")
    assert _missing(text, ["/pipe-in:pipe-eval", "/pipe-in:pipe-judge", "pipe-judge", "約 N 倍", "材料", "利用料", "人が呼んだとき"]) == []


def test_design_table_mentions_new_skills():
    """D0022-AC-33: docs/development/design.md の置き場所の表（plugin/ の行）に pipe-eval・pipe-judge があり、judge_score.py の行がある。"""
    lines = _read("docs/development/design.md").splitlines()
    row = next(line for line in lines if line.startswith("|") and "`plugin/`" in line)
    assert "pipe-eval" in row and "pipe-judge" in row
    assert any(line.startswith("|") and "generator/judge_score.py" in line for line in lines)
    hook_row = next(line for line in lines if line.startswith("|") and "generator/guard_hook.py" in line and "プラグインのフック" in line)
    assert "pipe-judge" in hook_row


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
