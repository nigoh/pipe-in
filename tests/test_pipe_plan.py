"""D0029: 計画ボード（/pipe-plan）。

- /pipe-plan は、Claude のアーティファクトの計画ボードを開く・GitHub と決定の記録に合わせる・項目を足す
- ボードのページのひな形は .claude/skills/pipe-plan/board.html に置く。項目はページに書かず、アーティファクトのデータに入れる
- ボードの URL は手元の事情なのでリポジトリに書かない（題で探す）
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).parents[1]
SKILL_DIR = REPO / ".claude" / "skills" / "pipe-plan"
SKILL = SKILL_DIR / "SKILL.md"
BOARD = SKILL_DIR / "board.html"
HELP = REPO / ".claude" / "skills" / "pipe-help" / "SKILL.md"
DECISIONS = REPO / "docs" / "decisions"
BOARD_TITLE = "pipe-in 計画ボード"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "前置き（---）が無い"
    out = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def test_d0029_ac01_skill_frontmatter():
    """D0029-AC-01: /pipe-plan の SKILL.md があり、名前・説明・引数の案内を持ち、人が呼んだときだけ動く。"""
    fm = frontmatter(read(SKILL))
    assert fm.get("name") == "pipe-plan"
    assert fm.get("description")
    assert fm.get("argument-hint")
    assert fm.get("disable-model-invocation") == "true"


def test_d0029_ac02_skill_names_actions():
    """D0029-AC-02: スキルに、開く（引数なし）・sync・add の3つの使い方と、ボードを探す題がある。"""
    text = read(SKILL)
    for word in ("sync", "add", BOARD_TITLE, "board.html"):
        assert word in text, f"{word} が SKILL.md に無い"


def test_d0029_ac03_board_template_title_and_db():
    """D0029-AC-03: ボードのひな形があり、題がスキルの探す題と同じで、項目をアーティファクトのデータ（items）から読む。"""
    html = read(BOARD)
    assert f"<title>{BOARD_TITLE}</title>" in html
    assert 'use?.("db")' in html or 'use("db")' in html
    assert 'collection("items")' in html


def test_d0029_ac04_board_escapes_text():
    """D0029-AC-04: ボードは外から来た文字を HTML として入れない（innerHTML・outerHTML・insertAdjacentHTML・document.write を使わない）。"""
    html = read(BOARD)
    for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert bad not in html, f"{bad} を使っている"


def test_d0029_ac05_board_loads_only_allowed_hosts():
    """D0029-AC-05: ボードが読み込む外のものは Google Fonts だけ（スクリプトは外から読まない）。"""
    html = read(BOARD)
    assert not re.search(r"<script[^>]+src=", html), "外のスクリプトを読んでいる"
    hosts = set(re.findall(r'(?:href|src)="https://([^/"]+)', html))
    assert hosts <= {"fonts.googleapis.com", "github.com"}, hosts


def test_d0029_ac06_no_artifact_url_in_repo():
    """D0029-AC-06: ボードの URL（claude.ai/artifact/…）をスキルとひな形に書かない。"""
    for path in (SKILL, BOARD):
        assert not re.search(r"claude\.ai/(?:code/)?artifact/[A-Za-z0-9-]{6,}", read(path)), path


def test_d0029_ac07_listed_in_help():
    """D0029-AC-07: /pipe-help の一覧に /pipe-plan がある。"""
    assert "`/pipe-plan" in read(HELP)


def test_d0029_ac08_decision_record_listed():
    """D0029-AC-08: 決定の記録 D0029 があり、決定の記録の表に載っている。"""
    assert list(DECISIONS.glob("D0029-*.md")), "D0029 の記録が無い"
    assert "D0029" in read(DECISIONS / "README.md")
