"""Claude Code のプラグイン（.claude-plugin/ と plugin/）：パイプを作る・直すスキルとエージェントと、止めるフックの形。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

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
    """D0006-AC-14・D0022-AC-03・D0031-AC-56: プラグインの版は 0.4.0（採点のスキルを足したので 0.2.0 から 0.3.0、進み具合を見るスキル pipe-live を足したので 0.4.0）。"""
    manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "0.4.0"


PLUGIN_TEXTS = [
    ".claude-plugin/marketplace.json",
    "plugin/.claude-plugin/plugin.json",
    "plugin/hooks/hooks.json",
    "plugin/skills/pipe-build/SKILL.md",
    "plugin/agents/pipe-builder.md",
    "plugin/skills/pipe-eval/SKILL.md",
    "plugin/skills/pipe-judge/SKILL.md",
    "plugin/agents/pipe-judge.md",
    "plugin/skills/pipe-live/SKILL.md",
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


# ---- D0031: 進み具合を見るスキル（pipe-live）--------------------------------------------------------------------------------


def _live_skill() -> tuple[dict[str, str], str]:
    return _skill("pipe-live")


def _commands(body: str) -> list[str]:
    """本文の中の、pipe-in を呼ぶ形のコマンド（バッククォートで囲んだもの・コードブロックの行）。"""
    spans = re.findall(r"`([^`\n]+)`", body)
    for block in re.findall(r"```[^\n]*\n(.*?)```", body, re.S):
        spans += [ln.strip() for ln in block.splitlines()]
    out = []
    for text in spans:
        t = text.strip().lstrip("$ ").strip()
        if re.match(r"(pipe-in|python -m pipe_in)\s+\S", t):  # 引数のない `pipe-in` は名前の言及で、コマンドではない
            out.append(t)
    return out


def test_d0031_ac56_pipe_live_skill_frontmatter_and_steps():
    """D0031-AC-56: pipe-live のスキルに、name（フォルダ名と同じ）・description・argument-hint があり、disable-model-invocation: true。見る手順の語がそろっている。"""
    fields, body = _live_skill()
    assert fields["name"] == "pipe-live"
    assert fields["description"] and fields["argument-hint"]
    assert fields["disable-model-invocation"] == "true"
    for word in ("pipe-in live watch", "見るだけ"):
        assert word in fields["description"], word
    assert _missing(body, ["pipe-in live page", "pipe-in live watch", "Artifact", "ArtifactData", "Monitor", "runs", "current", "if_version", "version"]) == []
    assert _missing(body, ["snapshot", "final", "timeout", "event", "seq", "empty"]) == []
    assert _missing(body, ["1回だけ", "公開し直さ", "人が呼んだとき"]) == []
    assert body.index("pipe-in live page") < body.index("pipe-in live watch"), "ページを公開してから見張りを起こす"
    assert body.index("pipe-in live watch") < body.index("if_version"), "見張りの行を受けてから ArtifactData に書く"


def test_d0031_ac56_pipe_live_skill_stops_without_tools_or_the_command():
    """D0031-AC-56: 始め（## 1. の前）に、Artifact・ArtifactData・Monitor が無い会話では伝えて何もせず止まること、claude.ai にログインした Claude Code だけで使えること、pipe-in live page --help を確かめ、無ければ入れ方（pip install -e .）を案内して止まることがある。"""
    _, body = _live_skill()
    first = body.split("## 1.")[0]
    assert "## 1." in body
    assert _missing(first, ["Artifact", "ArtifactData", "Monitor", "止まる", "何もせず", "claude.ai", "pipe-in live page --help", "pip install -e ."]) == []


def test_d0031_ac56_pipe_live_skill_stop_and_no_control_text():
    """D0031-AC-56: final・timeout の行での終わり方（124・Monitor の終わりを待つ）、見るだけでできないこと（止められない・承認や直してほしい点の送信はできない）、書くのは一時フォルダのファイルと ArtifactData だけ。"""
    _, body = _live_skill()
    assert _missing(body, ["124", "終わり", "止め", "承認", "直してほしい点", "一時", "書き換え"]) == []
    assert "リポジトリ" in body and "docs/pipeline/" in body, "一時フォルダはリポジトリや docs/pipeline/ の中に置かない旨"


FORBIDDEN_IN_SKILL = [
    (r"/home/", "手元のパス"), (r"/Users/", "手元のパス"), (r"[A-Za-z]:\\Users", "手元のパス"), (r"[A-Za-z]:/Users", "手元のパス"),
    (r"sk-[A-Za-z0-9_-]{8,}", "鍵"), (r"ANTHROPIC_API_KEY", "鍵の名前"), (r"ghp_[A-Za-z0-9]{10,}", "トークン"),
    (r"BEGIN [A-Z ]*PRIVATE KEY", "秘密鍵"), (r"[\w.+-]+@[\w-]+\.[\w.]+", "メールアドレス"),
]


def test_d0031_ac57_pipe_live_skill_has_no_paths_secrets_or_writing_commands():
    """D0031-AC-57: スキルに手元のパス・秘密を書かない。スキルが呼ぶ pipe-in は live page・live watch・live snapshot だけ（record・--review・--pause・--yes・段を流す形は呼ばない）。"""
    path = PLUGIN / "skills/pipe-live/SKILL.md"
    text = path.read_text(encoding="utf-8")
    for pattern, what in FORBIDDEN_IN_SKILL:
        assert not re.search(pattern, text), (what, pattern)
    commands = _commands(text)
    assert commands, "pipe-in を呼ぶ形のコマンドが1つも書かれていない"
    flags_ok = {"--out", "--interval", "--timeout", "--work-dir", "--project", "--config", "--help"}
    for cmd in commands:
        words = re.sub(r"^(python -m pipe_in|pipe-in)\s*", "", cmd).split()
        assert words[:1] == ["live"] and words[1:2] and words[1] in ("page", "watch", "snapshot"), cmd
        assert set(re.findall(r"--[a-z-]+", cmd)) <= flags_ok, cmd
    assert not re.search(r"(pipe-in|pipe_in)\s+record", text) and "pipe-in-gen" not in text
    kinds = {re.sub(r"^(python -m pipe_in|pipe-in)\s*live\s+", "", c).split()[0] for c in commands}
    assert {"page", "watch"} <= kinds


def test_d0031_ac57_pipe_live_skill_is_listed_with_the_other_plugin_texts():
    """D0031-AC-57: スキルは PLUGIN_TEXTS（devpipe の名前が残っていないかを見る一覧）に入っている。ほかのスキルと同じく disable-model-invocation: true。"""
    assert "plugin/skills/pipe-live/SKILL.md" in PLUGIN_TEXTS
    assert (ROOT / "plugin/skills/pipe-live/SKILL.md").is_file()
    for name in ["pipe-build", "pipe-eval", "pipe-judge", "pipe-live"]:
        assert _skill(name)[0]["disable-model-invocation"] == "true", name


def test_d0031_ac58_pipe_live_skill_flags_match_watch_parser():
    """D0031-AC-58: スキルの pipe-in live watch / page の引数（--out・--interval・--timeout・--work-dir）が、live_cmd の本当の引数と一致する。watch には --out が付き、値は範囲の中。"""
    import argparse

    from pipe_in.engine import live_cmd

    parser = live_cmd._parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    watch_opts = set(sub.choices["watch"]._option_string_actions) - {"-h", "--help"}
    page_opts = set(sub.choices["page"]._option_string_actions) - {"-h", "--help"}
    assert {"--out", "--interval", "--timeout", "--work-dir", "--project", "--config"} <= watch_opts
    _, body = _live_skill()
    seen_watch = False
    for cmd in _commands(body):
        words = re.sub(r"^(python -m pipe_in|pipe-in)\s*live\s+", "", cmd).split()
        flags = set(re.findall(r"--[a-z-]+", cmd)) - {"--help"}
        if words[0] == "watch":
            seen_watch = True
            assert flags <= watch_opts and "--out" in flags, cmd
            for name, lo, hi in (("--interval", 0.5, 60.0), ("--timeout", 1.0, 86400.0)):
                m = re.search(re.escape(name) + r"\s+([0-9.]+)", cmd)
                if m:
                    assert lo <= float(m.group(1)) <= hi, cmd
        elif words[0] == "page":
            assert flags <= page_opts, cmd
    assert seen_watch
    assert "--interval 2" in body and "--timeout 21600" in body, "既定と同じ値（2 秒・6 時間）を示す"


def test_d0031_ac58_pipe_live_skill_uses_the_documented_line_keys():
    """D0031-AC-58: スキルが読む行のキー（event・seq・final・empty）と event の値（snapshot・final・timeout）が、live_watch の行の形と同じ。"""
    _, body = _live_skill()
    for key in ("event", "seq", "final", "empty"):
        assert f"`{key}`" in body or f"{key}:" in body or key in body, key
    assert _missing(body, ["`snapshot`", "`final`", "`timeout`"]) == []


def test_d0031_ac59_guides_mention_watch_lines_and_exit_codes():
    """D0031-AC-59: ガイドと README に、pipe-in live watch の使い方・行の形・終了コード（0・124・130・143・1・2）・止まる条件・できないことが書かれ、新しいスキルの名前がある。内容は手で読む。"""
    usage = _read("docs/guide/usage.md")
    assert _missing(usage, ["pipe-in live watch", "--out", "--interval", "--timeout", "event", "seq", "snapshot", "final", "timeout", "124", "130", "143"]) == []
    plugin = _read("docs/guide/plugin.md")
    assert _missing(plugin, ["/pipe-in:pipe-live", "0.4.0", "Monitor", "ArtifactData", "人が呼んだとき"]) == []
    records = _read("docs/guide/records.md")
    assert _missing(records, ["live watch"]) == []
    safety = _read("docs/guide/safety.md")
    assert _missing(safety, ["live watch"]) == []
    assert "pipe-live" in _read("docs/guide/README.md") or "live watch" in _read("docs/guide/README.md")
    assert "pipe-live" in _read("README.md") or "live watch" in _read("README.md")
    design = _read("docs/development/design.md")
    row = next(line for line in design.splitlines() if line.startswith("|") and "`plugin/`" in line)
    assert "pipe-live" in row
    assert any(line.startswith("|") and "live_watch.py" in line for line in design.splitlines())


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


# ---- D0038-AC-13: パイプを作るときの教訓 -------------------------------------------------------------


def skill_section(heading_word: str) -> str:
    """pipe-build のスキルの「## …」の節（見出しに heading_word を含むもの）の本文。無ければ空。"""
    _, body = frontmatter(PLUGIN / "skills/pipe-build/SKILL.md")
    out: list[str] = []
    inside = False
    for line in body.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = heading_word in line
        if inside:
            out.append(line)
    return "\n".join(out)


# （pytest の id, 何を書くか, 探す言葉）。分かったこと 1〜5 は「段の決め方」、6 は「流すとき」
D0038_DECIDING_WORDS = [
    ("docs-for-scratch", "1：置き場所が要る段は access = \"docs\"（read で bash でも書けない）", 'access = "docs"'),
    ("docs-dir", "1：docs_dir を書く", "docs_dir"),
    ("agents-wait", "2：agents のある段は全部返ってから成果物を書く", "全部返"),
    ("tests-bash", "3：access = \"tests\" の段は bash = true であとの段と同じ検査を流す", 'access = "tests"'),
    ("check-command", "3：あとの段の check.command", "check.command"),
    ("code-no-rewrite", "4：access = \"code\" の段の指示文にテストを Bash でも書き換えないと書く", 'access = "code"'),
    ("rewrite", "4：書き換えない", "書き換え"),
    ("on-fail", "5：on_fail は直せる段にする", "on_fail"),
]
D0038_RUNNING_WORDS = [
    ("max-turns", "6：長い段は max_turns を足りるだけ", "max_turns"),
    ("setting-sources", "6：setting_sources を絞る", "setting_sources"),
]


@pytest.mark.parametrize("label,word", [(label, word) for _, label, word in D0038_DECIDING_WORDS], ids=[i for i, _, _ in D0038_DECIDING_WORDS])
def test_pipe_build_skill_has_lessons(label, word):
    """D0038-AC-13: スキル pipe-build の「段の決め方」に、分かったこと 1〜5 の要点（言葉の目印）が入っている。"""
    part = skill_section("段の決め方")
    assert part, "スキルに「段の決め方」の節が無い"
    found = word in part  # 節の本文を assert の失敗の表示に出さない
    assert found, f"「段の決め方」に、{label} が無い（探した言葉：{word}）"


@pytest.mark.parametrize("label,word", [(label, word) for _, label, word in D0038_RUNNING_WORDS], ids=[i for i, _, _ in D0038_RUNNING_WORDS])
def test_pipe_build_skill_has_running_section(label, word):
    """D0038-AC-13: スキル pipe-build の末尾に節「流すとき」があり、分かったこと 6 の要点（言葉の目印）が入っている。"""
    part = skill_section("流すとき")
    assert part, "スキルに「流すとき」の節が無い"
    found = word in part
    assert found, f"「流すとき」に、{label} が無い（探した言葉：{word}）"
    _, body = frontmatter(PLUGIN / "skills/pipe-build/SKILL.md")
    assert [l for l in body.splitlines() if l.startswith("## ")][-1].find("流すとき") >= 0, "「流すとき」は末尾の節にする"
