"""D0030: ブランド（プラグ）とデザインの土台を docs/design/ に残す。

- docs/design/canvas/ は Claude のデザインのキャンバスの写し（canvas.json と各板の .dc.html）
- docs/design/README.md は、ページと板の一覧・色の決まり・直し方を書く
- キャンバスの URL や、手元のセッションの名前は載せない
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).parents[1]
DESIGN = REPO / "docs" / "design"
CANVAS = DESIGN / "canvas"
README = DESIGN / "README.md"
DECISIONS = REPO / "docs" / "decisions"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_d0030_ac01_canvas_index_matches_boards():
    """D0030-AC-01: canvas.json の boards と order が、canvas/ にある .dc.html とちょうど同じ。"""
    index = json.loads(read(CANVAS / "canvas.json"))
    files = sorted(p.name for p in CANVAS.glob("*.dc.html"))
    assert sorted(index["boards"]) == files
    assert sorted(index["order"]) == files


def test_d0030_ac02_readme_lists_every_board():
    """D0030-AC-02: README に、すべての板のファイル名とページの名前が載っている。"""
    text = read(README)
    index = json.loads(read(CANVAS / "canvas.json"))
    for name in index["boards"]:
        assert f"`{name}`" in text, name
    for page in index["pages"]:
        assert page["name"] in text, page["name"]


def test_d0030_ac03_readme_has_plug_tokens():
    """D0030-AC-03: README の色の表に、基礎の板（Foundations）と同じ主役の2色が明暗で載っている。"""
    text = read(README)
    foundations = read(CANVAS / "Foundations.dc.html")
    for hex_ in ("#c2471f", "#ff8a65", "#167d6b", "#5fc4ab", "#f6f6f4", "#161514"):
        assert hex_ in foundations, hex_
        assert hex_ in text, hex_


def test_d0030_ac04_no_private_info():
    """D0030-AC-04: docs/design/ に、キャンバスの URL・セッションの ID・claude/ のブランチ名を書かない。"""
    for p in DESIGN.rglob("*"):
        if not p.is_file():
            continue
        t = read(p)
        assert not re.search(r"claude\.ai/(?:code/)?artifact/[A-Za-z0-9-]{6,}", t), p
        assert not re.search(r"session_[A-Za-z0-9]{10,}", t), p
        assert not re.search(r"\bclaude/[a-z]+-[a-z]+", t), p


def test_d0030_ac05_boards_load_only_google_fonts():
    """D0030-AC-05: 板が外から読むのは Google Fonts だけ（スクリプトは ./support.js だけ）。"""
    for p in CANVAS.glob("*.dc.html"):
        t = read(p)
        hosts = set(re.findall(r'(?:href|src)="https://([^/"]+)', t))
        assert hosts <= {"fonts.googleapis.com"}, (p.name, hosts)
        assert re.findall(r'<script[^>]+src="([^"]+)"', t) == ["./support.js"], p.name


def test_d0030_ac06_decision_record_and_place():
    """D0030-AC-06: 決定の記録 D0030 が表にあり、置き場所の表に docs/design/ がある。"""
    assert list(DECISIONS.glob("D0030-*.md"))
    assert "D0030" in read(DECISIONS / "README.md")
    assert "`docs/design/`" in read(REPO / "docs" / "development" / "design.md")
