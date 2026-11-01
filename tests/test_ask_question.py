"""D0057：人に聞くときは質問欄（AskUserQuestion）で聞く決まり。CLAUDE.md と 7 つの SKILL.md の検査。

読むだけで書かない（偽の文は、文字列で組み立てる）。SDK は呼ばない。
- CLAUDE.md の項目や SKILL.md の行がまだ無いときは、「が無い」で落ちる（ファイルごと読めずに落ちることはない）。
- 今の作りのままで通るテストは、名前の末尾を _守る にし、説明の末尾に「（今のまま通る。守る）」と書く。
- AC-06（既存のテストが緑のまま）と AC-09（pipe_in/・plugin/ に差分なし）は、検証の段で流す。単体テストにしない。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MD = ROOT / "CLAUDE.md"
SKILLS_DIR = ROOT / ".claude" / "skills"

SKILL_NAMES = [
    "pipe-in",
    "pipe-talk",
    "pipe-plan",
    "pipe-docs",
    "pipe-audit",
    "pipe-advise",
    "pipe-judge",
]

# 既存の 9 項目の頭の語（AC-05）
EXISTING_HEADS = [
    "テストを先に",
    "テストは SDK を呼ばず",
    "`pipe_in/engine/guard.py`",
    "依存の向き",
    "拡張は work_dir",
    "依存を足す",
    "機能ごとに決定の記録",
    "1つの機能を1つのコミット",
    "文書・コメント・コミットの文",
]

LINE_LIMIT = 100
COPIED_WORDS = ["1〜4", "2〜4", "その他", "番号つき"]


def _read(path: Path) -> str:
    if not path.exists():
        raise AssertionError(f"{path.relative_to(ROOT)} が無い")
    return path.read_text(encoding="utf-8")


def must_section_items(text: str) -> list[str]:
    """CLAUDE.md の「## 必ず守ること」から次の「## 」までの箇条書きを、1項目ずつ（続きの行は連結）返す。"""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == "## 必ず守ること":
            start = i + 1
            break
    if start is None:
        raise AssertionError("CLAUDE.md に「## 必ず守ること」の節が無い")
    items: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.startswith("- "):
            items.append(line)
        elif items and line.strip() and line.startswith(" "):
            items[-1] += line.strip()
    return items


def ask_items(text: str) -> list[str]:
    return [it for it in must_section_items(text) if "AskUserQuestion" in it and "質問欄" in it]


def the_ask_item() -> str:
    found = ask_items(_read(CLAUDE_MD))
    if not found:
        raise AssertionError("CLAUDE.md の「必ず守ること」に AskUserQuestion と質問欄を含む項目がない")
    return found[0]


def strip_front_matter(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1 :])
    return text


def ask_line_problems(text: str) -> list[str]:
    """SKILL.md の文を受けて、質問欄の行の問題の一覧を返す（空なら問題なし）。"""
    body = strip_front_matter(text)
    lines = [ln for ln in body.splitlines() if "質問欄" in ln]
    if not lines:
        return ["質問欄を含む行が無い"]
    problems: list[str] = []
    for ln in lines:
        if "CLAUDE.md" not in ln:
            problems.append(f"質問欄の行に CLAUDE.md が無い: {ln.strip()[:30]}")
        if len(ln) > LINE_LIMIT:
            problems.append(f"質問欄の行が {len(ln)} 字で {LINE_LIMIT} 字を超える")
        for w in COPIED_WORDS:
            if w in ln:
                problems.append(f"質問欄の行に決まりの本文「{w}」を写している")
    return problems


# --- CLAUDE.md（AC-01〜05） ---


def test_D0057_AC_01_必ず守ることにAskUserQuestionと質問欄の項目が1つある():
    """D0057-AC-01: 「必ず守ること」に AskUserQuestion と質問欄を含む箇条書きがちょうど 1 つある。"""
    items = ask_items(_read(CLAUDE_MD))
    assert len(items) == 1, f"AskUserQuestion と質問欄を含む項目が {len(items)} 個（1 個のはず）"


def test_D0057_AC_02_その項目に会話の文だけで聞かないとある():
    """D0057-AC-02: その項目に「会話の文だけ」がある。"""
    assert "会話の文だけ" in the_ask_item()


def test_D0057_AC_03_その項目に質問欄が使えない会話での扱いがある():
    """D0057-AC-03: その項目に「使えない」または「ツールが無い」がある。"""
    item = the_ask_item()
    assert "使えない" in item or "ツールが無い" in item


def test_D0057_AC_04_その項目にpipe_in本体の段の確認は対象外とある():
    """D0057-AC-04: その項目に「端末」または「`pipe_in/`」がある（本体の段の確認は対象外）。"""
    item = the_ask_item()
    assert "端末" in item or "`pipe_in/`" in item


def test_D0057_AC_05_既存の9項目が消えていない_守る():
    """D0057-AC-05: 既存の 9 項目の頭の語がそろっている（今のまま通る。守る）。"""
    items = must_section_items(_read(CLAUDE_MD))
    missing = [h for h in EXISTING_HEADS if not any(it.startswith("- " + h) for it in items)]
    assert not missing, f"消えた項目: {missing}"


# --- 7 つの SKILL.md（AC-07・08） ---


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_D0057_AC_07_7つのSKILLに質問欄とCLAUDE_mdを含む行がある(name):
    """D0057-AC-07: 各 SKILL.md に、質問欄と CLAUDE.md を同じ行に含む行がある。"""
    text = strip_front_matter(_read(SKILLS_DIR / name / "SKILL.md"))
    assert any("質問欄" in ln and "CLAUDE.md" in ln for ln in text.splitlines()), (
        f"{name}/SKILL.md に「質問欄」と「CLAUDE.md」を含む行が無い"
    )


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_D0057_AC_08_質問欄の行は1行で決まりの本文を写していない(name):
    """D0057-AC-08: 質問欄の行は 100 字以下で、決まりの本文を写さず、その行だけで CLAUDE.md を指す。"""
    problems = ask_line_problems(_read(SKILLS_DIR / name / "SKILL.md"))
    assert not problems, f"{name}/SKILL.md: {problems}"


# --- AC-08 の判定そのものが効いていること（見本） ---

GOOD = "---\nname: x\n---\n# x\n\n- 聞くときは質問欄で聞く（CLAUDE.md の「必ず守ること」）。\n"


def test_D0057_AC_08_判定は質問欄の行が無い文を落とす_守る():
    """D0057-AC-08: 質問欄の行が無い文は問題になる（今のまま通る。守る）。"""
    assert ask_line_problems("# x\n\n人に聞く。\n")


def test_D0057_AC_08_判定は前置きの中の質問欄を数えない_守る():
    """D0057-AC-08: 前置き --- の中だけの質問欄は数えない（今のまま通る。守る）。"""
    assert ask_line_problems("---\ndescription: 質問欄 CLAUDE.md\n---\n# x\n")


@pytest.mark.parametrize("word", COPIED_WORDS)
def test_D0057_AC_08_判定は決まりの本文を写した行を落とす_守る(word):
    """D0057-AC-08: 決まりの本文の語を写した行は問題になる（今のまま通る。守る）。"""
    text = f"# x\n\n- 質問欄で聞く（CLAUDE.md）。{word}で聞く。\n"
    assert ask_line_problems(text)


def test_D0057_AC_08_判定は100字を超える行を落とす_守る():
    """D0057-AC-08: 100 字を超える行は問題になる（今のまま通る。守る）。"""
    text = "# x\n\n- 質問欄で聞く（CLAUDE.md）。" + "あ" * 100 + "\n"
    assert ask_line_problems(text)


def test_D0057_AC_08_判定はCLAUDE_mdが無い行を落とす_守る():
    """D0057-AC-08: 質問欄の行に CLAUDE.md が無ければ問題になる（今のまま通る。守る）。"""
    assert ask_line_problems("# x\n\n- 質問欄で聞く。\n")


def test_D0057_AC_08_判定は正しい1行を通す_守る():
    """D0057-AC-08: 正しい 1 行は問題にならない（今のまま通る。守る）。"""
    assert ask_line_problems(GOOD) == []
