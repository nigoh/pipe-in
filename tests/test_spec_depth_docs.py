"""要件定義と設計を厚くする変更（D0085）が、指示文と文書に書かれているかの、文の有無の検査。

`.claude/` と `docs/` を読むだけ（書かない）。語は、設計書の案 A・B・C と文書の変更に書かれた、要になるものを見る。
一字一句には寄らず、要の語が節の中にそろっていることを確かめる。
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = ROOT / ".claude"
ANALYST = CLAUDE / "agents" / "pipe-in-analyst.md"
VERIFIER = CLAUDE / "agents" / "pipe-in-verifier.md"
SKILL = CLAUDE / "skills" / "pipe-in" / "SKILL.md"
HOOK = CLAUDE / "hooks" / "pipe_in_guard.py"
SETTINGS = CLAUDE / "settings.json"
SPECS = ROOT / "docs" / "development" / "specs.md"
DESIGN = ROOT / "docs" / "development" / "design.md"
DECISIONS_README = ROOT / "docs" / "decisions" / "README.md"

COMMAND = "python -m pipe_in skill spec-check"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def between(text: str, start: str, end: str | None) -> str:
    """start の行から end の行の手前まで。start が無ければ空。"""
    at = text.find(start)
    if at < 0:
        return ""
    rest = text[at:]
    if end is None:
        return rest
    stop = rest.find(end, len(start))
    return rest if stop < 0 else rest[:stop]


def missing(text: str, words: list[str]) -> list[str]:
    return [w for w in words if w not in text]


def analyst_requirements() -> str:
    return between(read(ANALYST), "要件定義に書くもの", "設計に書くもの")


def analyst_design() -> str:
    return between(read(ANALYST), "設計に書くもの", "終わったら")


def skill_section(start: str, end: str) -> str:
    return between(read(SKILL), start, end)


# ---- D0085-AC-14〜16: pipe-in-analyst の指示文 -------------------------------------------------


def test_D0085_AC_14_analystの要件定義の節にUR_前提_NFR_状態の問い_小さな直しの省き方がある():
    """D0085-AC-14: pipe-in-analyst.md の要件定義の節に、要求 UR-xx・前提・非機能要件 NFR-xx（きっかけ・状況・応答・測り方・無ければ「無し」）・
    FR の（UR-xx）・状態の問い（答えと理由・はい のときは設計で表を書く提案）・小さな直しの省き方がある。"""
    section = analyst_requirements()
    assert section, "「要件定義に書くもの」の節が見つからない"
    words = [
        "UR-01",
        "前提",
        "非機能要件",
        "NFR-01",
        "きっかけ",
        "状況",
        "応答",
        "測り方",
        "- 無し",
        "FR-01（UR-01）",
        "状態を持ち、操作や出来事で移り変わるか",
        "答え：はい",
        "答え：いいえ",
        "理由",
        "状態遷移の表",
        "小さな直し",
    ]
    assert missing(section, words) == []
    small = between(section, "小さな直し", None)
    assert missing(small, ["UR は1つ", "前提", "非機能要件", "状態遷移の表"]) == []


def test_D0085_AC_15_analystの設計の節に状態遷移の表_閉じ込め先_対応表の形がある():
    """D0085-AC-15: pipe-in-analyst.md の設計の節に、状態遷移の表（はい のときだけ・全マス・起きないマスも・DS-xx・AC をつなぐ）、
    「何が変わりそうで、どこに閉じ込めるか」の1〜2行、対応表の形（UR → FR・NFR → DS → AC → テスト）がある。"""
    section = analyst_design()
    assert section, "「設計に書くもの」の節が見つからない"
    words = [
        "状態遷移の表",
        "はい のときだけ",
        "全マス",
        "起きないマス",
        "DS-01",
        "受け入れ基準の ID",
        "状態：いいえ",
        "何が変わりそうで、どこに閉じ込めるか",
        "1〜2行",
        "対応表",
        "UR → FR・NFR → DS → AC",
    ]
    assert missing(section, words) == []


def test_D0085_AC_16_analystにIDの決まりがある():
    """D0085-AC-16: pipe-in-analyst.md に、ID の決まり（番号を付け直さず欠番にする・Dnnnn は記録の外に出る AC だけ・UR・FR・NFR・DS は短いまま・製品コードに ID を書かない・検査 spec-check が読める形）がある。"""
    text = read(ANALYST)
    assert missing(text, ["ID の決まり", "付け直さ", "欠番", "記録の外", "UR・FR・NFR・DS", "短い", "製品コードには ID を書かない", COMMAND]) == []


# ---- D0085-AC-17〜19: SKILL.md と pipe-in-verifier.md ---------------------------------------------


def test_D0085_AC_17_SKILLの要件定義の要点にUR_前提_NFR_状態の問いが入っている():
    """D0085-AC-17: SKILL.md の「1. 要件定義」の、成果物の要点を会話に書く行に、UR・前提・NFR・状態の問いが入っている。"""
    section = skill_section("### 1. 要件定義", "### 2. 設計")
    assert section, "「1. 要件定義」の節が見つからない"
    lines = [line for line in section.splitlines() if "要点を会話に書く" in line]
    assert lines, "「成果物の要点を会話に書く」の行が無い"
    assert missing(lines[0], ["要求 UR", "前提", "NFR", "状態の問い"]) == []


def test_D0085_AC_18_SKILLに見てほしい問いを2から3個添える文が3つの段にある():
    """D0085-AC-18: SKILL.md に、段の区切りで「見てほしい問い」を2〜3個添える文が、要件定義・設計・テスト先行のそれぞれにある。
    問いは成果物の中身に合わせて親が作り、人に聞く前に会話へ書く。"""
    text = read(SKILL)
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if "見てほしい問い" in p]
    assert paragraphs, "「見てほしい問い」の文が無い"
    joined = "\n".join(paragraphs)
    assert "2〜3個" in joined
    assert missing(joined, ["要件定義", "設計", "テスト先行", "親が作り", "会話"]) == []
    # 3つの段それぞれの例（段ごとに、見てほしい問いが書かれている）
    for stage, probe in (("要件定義", "前提"), ("設計", "閉じ込め"), ("テスト先行", "赤の理由")):
        assert f"{stage}は「" in joined, f"{stage} の見てほしい問いの例が無い"
        assert probe in joined, f"{stage} の見てほしい問い（{probe}）が無い"


def test_D0085_AC_19_SKILLの設計と検証にspec_checkを流す文があり_verifierは渡された結果を写す():
    """D0085-AC-19: SKILL.md に、設計の終わりと検証の段で `python -m pipe_in skill spec-check` を流し、結果を会話に書く（検証では 05 にも写す）文がある。
    検証では、検証役に任せる前（record begin test の前）に親が流し、出力を指示に入れる。pipe-in-verifier.md に、渡された結果を 05_test_report.md に写す文がある。"""
    design = skill_section("### 2. 設計", "### 3. テスト先行")
    assert COMMAND in design, "設計の節に spec-check を流す文が無い"
    assert "会話" in design.split(COMMAND, 1)[1].split("\n", 1)[0], "結果を会話に書く文が同じ行に無い"

    verify = skill_section("### 5. 検証", "### 文書をそろえる")
    assert COMMAND in verify, "検証の節に spec-check を流す文が無い"
    run_line = next(line for line in verify.splitlines() if COMMAND in line)
    assert missing(run_line, ["pipe-in-verifier", "指示", "05_test_report.md"]) == [], "出力を検証役への指示に入れ、検証役が 05 に写す"
    assert "会話" in run_line

    verifier = read(VERIFIER)
    assert missing(verifier, ["spec-check", "05_test_report.md", "渡"]) == []
    assert "自分では流さない" in verifier


# ---- D0085-AC-20: 守りの仕組みは変えない（今の作りでも通る） --------------------------------------------


@pytest.fixture(scope="module")
def guard():
    spec = importlib.util.spec_from_file_location("pipe_in_guard", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tools_line(path: Path) -> str:
    return next(line for line in read(path).splitlines() if line.startswith("tools:"))


def test_D0085_AC_20_analystとverifierのtoolsとsettingsのallowは変わらず_フックはspec_checkを許す表に足さない(guard):
    """D0085-AC-20: pipe-in-analyst の tools は Read, Grep, Glob, Write, Edit のまま、pipe-in-verifier の tools も変わらない。
    settings.json の allow に Bash(python -m pipe_in skill:*) は今もあり、spec-check の規則は足さない。
    pipe_in_guard.py は spec-check を許す表に足さず、段のサブエージェントは skill spec-check を Bash で流せない（親が流して渡す）。
    今の作りのままで通る（守り続けるための検査）。既存のフックのテスト（tests/test_pipe_in_guard.py）も流す。"""
    assert tools_line(ANALYST) == "tools: Read, Grep, Glob, Write, Edit"
    assert tools_line(VERIFIER) == "tools: Read, Grep, Glob, Write, Bash"

    allow = json.loads(read(SETTINGS))["permissions"]["allow"]
    assert "Bash(python -m pipe_in skill:*)" in allow
    assert not [rule for rule in allow if "spec-check" in rule or "spec_check" in rule]

    hook_source = read(HOOK)
    assert "spec-check" not in hook_source and "spec_check" not in hook_source

    payload_base = {"tool_name": "Bash", "cwd": str(ROOT)}
    for agent in ("pipe-in-analyst", "pipe-in-tester", "pipe-in-coder", "pipe-in-verifier"):
        for command in (COMMAND, "pipe-in skill spec-check", "python -m pipe_in spec-check"):
            payload = {**payload_base, "tool_input": {"command": command}, "agent_type": agent}
            assert guard.decide(payload, root=str(ROOT)) is not None, f"{agent} が `{command}` を流せてしまう"


# ---- D0085-AC-22: 文書 ---------------------------------------------------------------------------


def test_D0085_AC_22_specsにUR_前提_NFR_状態の問いとIDの決まりがある():
    """D0085-AC-22: docs/development/specs.md の「要件定義の形」の表に UR・前提・NFR・状態の問いが入り、
    「決定の記録」に `### 要求と前提`・`### 非機能要件` と、ID の決まり（欠番・Dnnnn は AC だけ）が入る。"""
    text = read(SPECS)
    shape = between(text, "## 要件定義の形", "## 決定の記録")
    assert missing(shape, ["要求 `UR-xx`", "前提", "非機能要件 `NFR-xx`", "状態を持ち、操作や出来事で移り変わるか", "（UR-xx）"]) == []
    record = between(text, "## 決定の記録", "## 受け入れ基準の ID")
    assert missing(record, ["### 要求と前提", "### 非機能要件"]) == []
    assert missing(text, ["ID の決まり", "欠番", "付け直さ", "Dnnnn", "短い", "記録の外"]) == []
    assert "確かめたこと" in record and "差し戻し" in record


def table_row(text: str, key: str) -> str | None:
    return next((line for line in text.splitlines() if line.startswith("|") and key in line), None)


def test_D0085_AC_22_decisionsのひな形とdesignの置き場所の表がそろう():
    """D0085-AC-22: docs/decisions/README.md のひな形に `### 要求と前提`・`### 非機能要件`・AC の（FR-xx）・`答え：` があり、
    docs/development/design.md の置き場所の表に pipe_in/dev/spec_check.py の行がある（spec-check・標準ライブラリだけ・D0085 の語。1 行 800 字まで）。
    skill_cmd.py の行は decision-number を残して spec-check を足す。"""
    readme = read(DECISIONS_README)
    template = between(readme, "## ひな形", None)
    assert missing(template, ["### 要求と前提", "### 非機能要件", "（FR-", "答え："]) == []

    design = read(DESIGN)
    row = table_row(design, "`pipe_in/dev/spec_check.py`")
    assert row is not None, "置き場所の表に pipe_in/dev/spec_check.py の行が無い"
    assert missing(row, ["spec-check", "標準ライブラリだけ", "D0085"]) == []
    assert len(row) <= 800

    skill_row = table_row(design, "`pipe_in/dev/skill_cmd.py`")
    assert skill_row is not None
    assert missing(skill_row, ["decision-number", "spec-check"]) == []
    assert len(skill_row) <= 800
