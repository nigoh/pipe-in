"""プラグのロゴの動き（docs/assets/pipe-in-plug-logo.html と GIF）の検査。SDK は呼ばない。

動きそのものは画面で確かめる（決定の記録 D0013 の「画面」の項目）。
ここでは、ページの中に「入っているべき短い語」があるか・無いはずのものが無いかだけを見る（書き方は変えてよい）。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
PAGE = ASSETS / "pipe-in-plug-logo.html"
GIF = ASSETS / "pipe-in-plug-logo.gif"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_d0013_ac01_page_loads_nothing_from_outside() -> None:
    """D0013-AC-01: ページは外から何も読み込まない（script・link・画像・fetch・@import）。"""
    html = _page()
    assert not re.search(r"""(src|href)\s*=\s*["']?(https?:)?//""", html)
    assert not re.search(r"url\(\s*['\"]?(https?:)?//", html)
    assert "@import" not in html
    assert "fetch(" not in html
    assert "XMLHttpRequest" not in html


def test_d0013_ac02_camera_presets_and_default() -> None:
    """D0013-AC-02: カメラの型を5つから選べ、はじめは「全体から寄る」。全体図にカメラの枠を出す。"""
    html = _page()
    values = re.findall(r'<input type="radio" name="cam" id="cam-(\w+)" value="(\w+)"', html)
    assert sorted(v for _, v in values) == ["dolly", "fixed", "hand", "intro", "push"]
    assert re.search(r'value="intro" checked', html)
    assert re.search(r'cam:\s*"intro"', html)
    assert 'id="overview"' in html and 'id="camrect"' in html


def test_d0013_ac03_pause_before_start() -> None:
    """D0013-AC-03: 動き出す前に、止まったロゴを見せる間がある（はじめは 1.2 秒・つまみで 0〜3 秒）。"""
    html = _page()
    assert re.search(r"pre:\s*1\.2\b", html)
    assert re.search(r'<input type="range" id="pre" min="0" max="3"[^>]*value="1\.2"', html)


def test_d0013_ac04_plug_goes_in_from_above() -> None:
    """D0013-AC-04: プラグは立体として手前から降りて差す。横から差すための切り抜き（面の線で刃を消す）は無い。"""
    html = _page()
    assert "function drawPlug(" in html
    assert 'id="pshadow"' in html and 'id="pside"' in html
    assert 'clip-path="url(#face)"' not in html


def test_d0013_ac05_no_grain_texture() -> None:
    """D0013-AC-05: ざらざらの紙の模様を重ねない。"""
    html = _page()
    assert "grain" not in html


def _gif_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:10]
    assert head[:6] in (b"GIF87a", b"GIF89a")
    return int.from_bytes(head[6:8], "little"), int.from_bytes(head[8:10], "little")


def test_d0013_ac06_gif_size() -> None:
    """D0013-AC-06: GIF は幅 800 以下・900KB 以下。"""
    width, _ = _gif_size(GIF)
    assert width <= 800
    assert GIF.stat().st_size <= 900 * 1024


def test_d0013_ac07_assets_readme_describes_motion() -> None:
    """D0013-AC-07: 置き場所の説明（docs/assets/README.md）に、カメラと上から差すことが書いてある。"""
    text = (ASSETS / "README.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| `pipe-in-plug-logo.html`"))
    assert "カメラ" in row and "上から" in row
