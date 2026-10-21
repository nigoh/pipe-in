"""README の動くロゴと、VSCode の中の画面（D0023）の検査。SDK は呼ばない。

動きそのものと写りは画面で確かめる（決定の記録 D0023 の「確かめたこと」）。
ここでは、README がどの画像をどの条件で出すか・画像の大きさ・置き場所の説明があるかだけを見る。
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from test_readme import ASSETS, README, pictures, png_size

LOGO_GIF = "docs/assets/pipe-in-plug-logo.gif"
LOGO_GIF_DARK = "docs/assets/pipe-in-plug-logo-dark.gif"
LOGO_SVG = "docs/assets/pipe-in-logo.svg"
LOGO_SVG_DARK = "docs/assets/pipe-in-logo-dark.svg"
VSCODE_SHOTS = ["vscode-run-light.png", "vscode-run-dark.png", "vscode-editor-light.png", "vscode-editor-dark.png"]
USAGE_GIFS = ["vscode-usage-light.gif", "vscode-usage-dark.gif"]
USAGE_MAX_WIDTH = 960
USAGE_MAX_BYTES = 2_621_440   # 2.5 MiB


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _logo_picture() -> dict:
    """README の <h1> の中の <picture>。"""
    md = _readme()
    h1 = re.search(r"<h1>(.*?)</h1>", md, re.S)
    assert h1 is not None, "README に <h1> が無い"
    pics = pictures(h1.group(1))
    assert len(pics) == 1, "README の <h1> の中に <picture> が1つでない"
    return pics[0]


def _chosen(pic: dict, *, dark: bool, reduce: bool) -> str:
    """ブラウザと同じく、合う <source> のうち先のものを選ぶ。どれも合わなければ <img> の src。"""
    for s in pic["sources"]:
        media = s["media"]
        if "prefers-color-scheme: dark" in media and not dark:
            continue
        if "prefers-reduced-motion: reduce" in media and not reduce:
            continue
        return s["srcset"]
    return pic["src"]


def _skip_sub_blocks(data: bytes, i: int) -> int:
    """長さ付きの小さなブロックの並びを、終わり（長さ 0）の次まで読み飛ばす。"""
    while data[i]:
        i += data[i] + 1
    return i + 1


def _gif_info(path: Path) -> tuple[int, int, int, bool]:
    """GIF の幅・高さ・コマの数・くり返すか（NETSCAPE2.0 の拡張があるか）を、ブロックを順に読んで数える。"""
    data = path.read_bytes()
    assert data[:6] in (b"GIF87a", b"GIF89a"), f"{path.name} は GIF でない"
    width, height, flags = struct.unpack("<HHB", data[6:11])
    i = 13 + (3 * 2 ** ((flags & 7) + 1) if flags & 0x80 else 0)
    frames, loops = 0, False
    while data[i] != 0x3B:   # 終わりの印
        if data[i] == 0x21:   # 拡張：種類の1バイトのあとに小さなブロックの並び
            if data[i + 1] == 0xFF and data[i + 3 : i + 14] == b"NETSCAPE2.0":   # くり返しの指定
                loops = True
            i = _skip_sub_blocks(data, i + 2)
        elif data[i] == 0x2C:   # 1コマ：10バイトの説明、あれば色の表、LZW の1バイト、小さなブロックの並び
            frames += 1
            local = data[i + 9]
            i += 10 + (3 * 2 ** ((local & 7) + 1) if local & 0x80 else 0)
            i = _skip_sub_blocks(data, i + 1)
        else:
            raise AssertionError(f"{path.name} の {i} バイト目が読めない")
    return width, height, frames, loops


# ---- D0023-AC-01: 冒頭のロゴは動くロゴ ----------------------------------------------


def test_d0023_ac01_readme_logo_is_animated():
    """D0023-AC-01: README の冒頭のロゴは、明るい表示では動くロゴ（GIF）、暗い表示では暗い表示の動くロゴを出す。"""
    pic = _logo_picture()
    assert _chosen(pic, dark=False, reduce=False) == LOGO_GIF
    assert _chosen(pic, dark=True, reduce=False) == LOGO_GIF_DARK
    assert pic["alt"] == "pipe-in"
    assert pic["width"].strip()


# ---- D0023-AC-02: 動きを減らす設定では止まったロゴ ------------------------------------


def test_d0023_ac02_reduced_motion_shows_still_logo():
    """D0023-AC-02: 動きを減らす設定（prefers-reduced-motion: reduce）では、止まったロゴ（SVG）を明暗で出す。"""
    pic = _logo_picture()
    assert _chosen(pic, dark=False, reduce=True) == LOGO_SVG
    assert _chosen(pic, dark=True, reduce=True) == LOGO_SVG_DARK


def test_d0023_ac02_choose_follows_source_order():
    """D0023-AC-02: 選び方の補助そのものが、先に合った <source> を選び、どれも合わなければ <img> にする。"""
    pic = {
        "sources": [
            {"media": "(prefers-reduced-motion: reduce)", "srcset": "still.svg"},
            {"media": "(prefers-color-scheme: dark)", "srcset": "dark.gif"},
        ],
        "src": "light.gif",
    }
    assert _chosen(pic, dark=False, reduce=False) == "light.gif"
    assert _chosen(pic, dark=True, reduce=False) == "dark.gif"
    assert _chosen(pic, dark=True, reduce=True) == "still.svg"


# ---- D0023-AC-03: 暗い表示の GIF の大きさ ---------------------------------------------


def test_d0023_ac03_dark_gif_limits():
    """D0023-AC-03: 暗い表示の動くロゴの GIF は、幅 800 以下・900KB 以下で、2コマ以上あり、くり返す。"""
    path = ASSETS / Path(LOGO_GIF_DARK).name
    assert path.is_file(), f"{path.name} が無い"
    width, _, frames, loops = _gif_info(path)
    assert width <= 800
    assert path.stat().st_size <= 900 * 1024
    assert frames >= 2
    assert loops


# ---- D0023-AC-04: 置き場所の説明 ------------------------------------------------------


def test_d0023_ac04_assets_readme_rows():
    """D0023-AC-04: docs/assets/README.md の表に、暗い表示の GIF・VSCode の中の画面4枚・使い方の動画2本の行があり、撮り方の節がある。"""
    text = (ASSETS / "README.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| `")]
    names = [Path(LOGO_GIF_DARK).name, *VSCODE_SHOTS, *USAGE_GIFS]
    missing = [n for n in names if not any(f"`{n}`" in row.split("|")[1] for row in rows)]
    assert missing == []
    assert re.search(r"^## VSCode の中の画面を撮る", text, re.M), "VSCode の中の画面の撮り方の節が無い"
    assert re.search(r"^## 使い方の動画を撮る", text, re.M), "使い方の動画の撮り方の節が無い"


# ---- D0023-AC-05・06: VSCode の中の画面と使い方の動画 ------------------------------------


def _vscode_section_pictures() -> list[dict]:
    """README の「すぐ試す」の中の「### VSCode で見る」から下の <picture>。"""
    md = _readme()
    start = md.index("\n## すぐ試す")
    end = md.index("\n## ", start + 1)
    part = md[start:end]
    assert re.search(r"^### VSCode で見る$", part, re.M), "「### VSCode で見る」が無い"
    return pictures(part[part.index("### VSCode で見る"):])


def test_d0023_ac05_readme_shows_vscode_shots():
    """D0023-AC-05: README の「すぐ試す」に「### VSCode で見る」があり、VSCode の中の作業台を明暗で出す（実行パネルの画面は AC-06 の止まった画面）。"""
    pic = next((p for p in _vscode_section_pictures() if p["src"] == "docs/assets/vscode-editor-light.png"), None)
    assert pic is not None, "vscode-editor-light.png の <picture> が無い"
    assert _chosen(pic, dark=True, reduce=False) == "docs/assets/vscode-editor-dark.png"


def test_d0023_ac06_readme_shows_usage_video():
    """D0023-AC-06: 「### VSCode で見る」の最初の <picture> は使い方の動画（明暗の GIF）で、動きを減らす設定では VSCode の中の実行パネルの止まった画面を出す。"""
    pics = _vscode_section_pictures()
    assert pics, "「### VSCode で見る」に <picture> が無い"
    pic = pics[0]
    assert _chosen(pic, dark=False, reduce=False) == "docs/assets/vscode-usage-light.gif"
    assert _chosen(pic, dark=True, reduce=False) == "docs/assets/vscode-usage-dark.gif"
    assert _chosen(pic, dark=False, reduce=True) == "docs/assets/vscode-run-light.png"
    assert _chosen(pic, dark=True, reduce=True) == "docs/assets/vscode-run-dark.png"
    assert pic["alt"].strip() and pic["width"].strip()


def test_d0023_ac07_usage_gif_limits():
    """D0023-AC-07: 使い方の動画の GIF は、どちらも幅 960 以下・2.5 MiB 以下で、2コマ以上あり、くり返す。"""
    problems = []
    for name in USAGE_GIFS:
        path = ASSETS / name
        if not path.is_file():
            problems.append(f"{name} が無い")
            continue
        width, _, frames, loops = _gif_info(path)
        if width > USAGE_MAX_WIDTH:
            problems.append(f"{name}: 幅 {width}")
        if path.stat().st_size > USAGE_MAX_BYTES:
            problems.append(f"{name}: {path.stat().st_size} バイト")
        if frames < 2 or not loops:
            problems.append(f"{name}: コマ {frames}・くり返し {loops}")
    assert problems == []


def test_d0023_ac05_vscode_shots_size():
    """D0023-AC-05: VSCode の中の画面4枚は、どれも 1280×800。"""
    sizes = {n: png_size(ASSETS / n) for n in VSCODE_SHOTS}
    assert sizes == {n: (1280, 800) for n in VSCODE_SHOTS}
