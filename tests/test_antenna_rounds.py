"""antenna の回（D0101）：購読 `.antenna.json` と、main に自動で入れてよい範囲の決まり。

購読の形そのものは antenna 側の道具が見る。ここでは、このリポジトリの側で守りたいこと
（守りの仕組みと本体が、自動で変えてよい範囲に入らない・CLAUDE.md の決まりと食い違わない）を見る。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUB = json.loads((ROOT / ".antenna.json").read_text(encoding="utf-8"))

# 自動で変えてよい範囲は、この一覧と同じでなければならない（足すときは、決定の記録を書いてから）
AUTO_ALLOW = [
    "plugin/skills/pipe-build/SKILL.md",
    "plugin/skills/pipe-eval/SKILL.md",
    "plugin/skills/pipe-judge/SKILL.md",
    "plugin/skills/pipe-live/SKILL.md",
    "plugin/.claude-plugin/plugin.json",
    "tests/**",
]

# 守りの仕組み・本体・人が決める物の代表。どれも、自動で変えてよい範囲に入ってはいけない
MUST_STAY_HUMAN = [
    "pipe_in/engine/guard.py",
    "generator/guard_hook.py",
    "generator/chat_hook.py",
    "pipe_in/engine/runner.py",
    "pipe_in/pipe/cli.py",
    "generator/cli.py",
    "plugin/hooks/hooks.json",
    "plugin/agents/pipe-stage.md",
    "plugin/agents/pipe-judge.md",
    "plugin/agents/pipe-probe.md",
    "plugin/skills/pipe-run/SKILL.md",
    "plugin/skills/pipe-build/references/stage-rules.md",
    "plugin/evals/cases.json",
    ".claude/settings.json",
    ".claude/hooks/pipe_in_guard.py",
    ".github/workflows/ci.yml",
    ".antenna.json",
    "CLAUDE.md",
    "docs/decisions/D0101-antenna-rounds.md",
    "docs/development/workflow.md",
    "vscode/package.json",
    "pyproject.toml",
    "tests/conftest.py",
    "tests/fixtures/budget_record.json",
]


def to_re(glob: str) -> re.Pattern:
    """`**` は階層をまたぎ、`*` は階層をまたがない照合（antenna の道具と同じ読み方）。"""
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?"); i += 3
        elif glob.startswith("**", i):
            out.append(".*"); i += 2
        elif glob[i] == "*":
            out.append("[^/]*"); i += 1
        else:
            out.append(re.escape(glob[i])); i += 1
    return re.compile("^" + "".join(out) + "$")


def hit(path: str, globs: list[str]) -> bool:
    return any(to_re(g).match(path) for g in globs)


def auto_editable(path: str) -> bool:
    return hit(path, SUB["apply"]["allow"]) and not hit(path, SUB["apply"]["deny"])


def test_D0101_AC_01_購読は読めて_検査はこのリポジトリのテスト():
    """D0101-AC-01: `.antenna.json` が JSON として読め、version が 1、plugin が pipe-in、検査の命令が `python3 -m pytest -q`。"""
    assert SUB["version"] == 1 and SUB["plugin"] == "pipe-in"
    assert SUB["check"] == ["python3", "-m", "pytest", "-q"]


def test_D0101_AC_02_自動で変えてよい範囲は決まった一覧と同じ():
    """D0101-AC-02: `apply.allow` が、プラグインの4つのスキルの SKILL.md・plugin.json・tests/ の一覧とちょうど同じ。行数の上限は 60 以下で、版のファイルは plugin.json。"""
    assert SUB["apply"]["allow"] == AUTO_ALLOW
    assert SUB["apply"]["max_lines"] <= 60
    assert SUB["apply"]["version_file"] == "plugin/.claude-plugin/plugin.json"
    assert SUB["apply"]["tests"] == ["tests/**"]


def test_D0101_AC_03_守りの仕組みと本体は自動で変えてよい範囲に入らない():
    """D0101-AC-03: 守りの仕組み（guard.py・guard_hook.py・フック・エージェントの定義・pipe-run のスキル・設定）と、本体・拡張・決定の記録・CI・テストの土台は、どれも自動で変えてよい範囲に入らない。"""
    wrong = [p for p in MUST_STAY_HUMAN if auto_editable(p)]
    assert wrong == [], f"自動で変えられる側にある: {wrong}"


def test_D0101_AC_03_照合そのものが働く():
    """D0101-AC-03: 照合の道具が、範囲の中を当て、範囲の外を当てない（上の検査が、何も当てずに通っていないこと）。"""
    assert auto_editable("plugin/skills/pipe-build/SKILL.md")
    assert auto_editable("tests/test_new.py")
    assert not hit("plugin/skills/pipe-run/SKILL.md", ["plugin/skills/pipe-build/SKILL.md"])
    assert hit("plugin/skills/x/SKILL.md", ["plugin/skills/*/SKILL.md"])
    assert not hit("plugin/skills/x/y/SKILL.md", ["plugin/skills/*/SKILL.md"])
    wide = {"apply": {"allow": ["plugin/**"], "deny": []}}
    assert hit("plugin/hooks/hooks.json", wide["apply"]["allow"]), "広い範囲なら当たる形であること"


def test_D0101_AC_04_守りと本体のカテゴリはいつも人が見る():
    """D0101-AC-04: 購読のカテゴリのうち、自動で入るのは claude-code-harness だけ。エージェントの定義・pipe-run・本体を指すカテゴリは `mode` が pr。"""
    modes = {c["id"]: c.get("mode", "auto") for c in SUB["categories"]}
    assert modes == {"claude-code-harness": "auto", "plugin-guards": "pr", "agent-sdk": "pr"}
    auto_targets = [t for c in SUB["categories"] if c.get("mode", "auto") == "auto" for t in c["targets"]]
    assert all(auto_editable(t) for t in auto_targets), auto_targets


def test_D0101_AC_05_カテゴリが指す部品は実在する():
    """D0101-AC-05: 購読のカテゴリの targets のどれも、リポジトリに当たるファイルがある。"""
    files = [str(p.relative_to(ROOT)).replace("\\", "/") for d in ("plugin", "pipe_in") for p in (ROOT / d).rglob("*") if p.is_file()]
    files.append("pyproject.toml")
    for cat in SUB["categories"]:
        for target in cat["targets"]:
            assert any(to_re(target).match(f) for f in files), f"{cat['id']}: {target}"


def test_D0101_AC_06_CLAUDE_md_に例外の文があり_今までの決まりの文も残る():
    """D0101-AC-06: CLAUDE.md に antenna の回の例外（D0101・判定の道具が merge と言ったときだけ・自動で変えてよい範囲）があり、「無人でも、開始の指示に書かれていても、しない」の行は今までどおり残る。"""
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    line = next((l for l in text.splitlines() if l.startswith("  - antenna の回（D0101）")), "")
    assert line, "antenna の回の例外の行が無い"
    for word in ("`VERDICT: merge`", "`.antenna.json`", "この回で自分が作った PR", "GitHub の道具", "守りの仕組み"):
        assert word in line, word
    assert "  - 無人でも、開始の指示に書かれていても、しない：main に入れること" in text
    workflow = (ROOT / "docs" / "development" / "workflow.md").read_text(encoding="utf-8")
    assert "antenna の回（D0101）" in workflow
