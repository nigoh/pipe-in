"""README（D0009）：アンカーの作り方・アラートの見つけ方・すぐ試すの順・画像の上限・拡張の README の画像・撮り直しの手順。

D0014 で、README の形の検査（冒頭の並び・節の順・切れたリンク・要点と目次・名指しの見出し・コマンドと表の項目・アラート・画像・CLI の出力）は
tests/test_guide.py へ移した（README は入口だけになり、くわしい説明は docs/guide/ に移ったため）。ここに残すのは、今も成り立つ検査と、
test_guide.py が使う補助の関数。
古い名前は、この文書に直接書かない（tests/test_rename.py の一覧に無いファイルなので）。要るときは OLD で文字をつないで作る。
"""

from __future__ import annotations

import re
import struct
import unicodedata
import zlib
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
VSCODE_README = ROOT / "vscode" / "README.md"
ASSETS = ROOT / "docs" / "assets"
RAW_PREFIX = "https://raw.githubusercontent.com/nigoh/pipe-in/main/"

OLD = "dev" + "pipe"

IMAGES = ["run-panel-light.png", "run-panel-dark.png", "pipe-editor-light.png", "pipe-editor-dark.png"]


def readme() -> str:
    return README.read_text(encoding="utf-8")


# ---- 補助 ------------------------------------------------------------------


def github_anchor(text: str) -> str:
    """GitHub の見出しのアンカー（重なりの -1 は付けない）：タグを除き、リンクは文だけ、小文字、句読点と記号（- と _ のほか）を消し、空白を - に。"""
    t = re.sub(r"<[^>]+>", "", text)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = t.strip().lower()
    kept = "".join(c for c in t if c in "-_" or unicodedata.category(c)[0] not in "PS")
    return kept.replace(" ", "-")


def _outside_code(md: str) -> list[tuple[bool, str]]:
    """各行と、それが ``` で囲まれたコードの中か。"""
    out = []
    in_code = False
    for line in md.splitlines():
        if line.lstrip().startswith("```"):
            out.append((True, line))
            in_code = not in_code
            continue
        out.append((in_code, line))
    return out


def text_outside_code(md: str) -> str:
    return "\n".join(line for code, line in _outside_code(md) if not code)


HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def headings(md: str) -> list[tuple[int, str]]:
    """（深さ, 見出しの文）。コードの中の # は見出しにしない。"""
    out = []
    for code, line in _outside_code(md):
        if code:
            continue
        m = HEADING.match(line)
        if m:
            out.append((len(m.group(1)), m.group(2)))
    return out


def heading_anchors(md: str) -> list[str]:
    """見出しのアンカーを上から。同じものは2回目に -1、3回目に -2 を付ける。"""
    seen: dict[str, int] = {}
    out = []
    for _, title in headings(md):
        base = github_anchor(title)
        n = seen.get(base, 0)
        out.append(base if n == 0 else f"{base}-{n}")
        seen[base] = n + 1
    return out


def anchors(md: str) -> set[str]:
    ids = re.findall(r"<a\s+(?:id|name)=\"([^\"]+)\"", text_outside_code(md))
    return set(heading_anchors(md)) | set(ids)


def broken_links(md: str) -> list[str]:
    """](#…) と href="#…" のうち、README の中に行き先が無いもの（コードの中は見ない）。"""
    text = text_outside_code(md)
    targets = re.findall(r"\]\(#([^)\s]*)\)", text) + re.findall(r"href=\"#([^\"]*)\"", text)
    have = anchors(md)
    return [t for t in targets if unquote(t) not in have]


def section(md: str, title: str) -> str:
    """その ## の見出しから、次の ## の見出しの前まで。無ければ空。"""
    lines = _outside_code(md)
    start = None
    for i, (code, line) in enumerate(lines):
        if code:
            continue
        if start is None and line.strip() == f"## {title}":
            start = i
        elif start is not None and line.startswith("## "):
            return "\n".join(l for _, l in lines[start:i])
    return "" if start is None else "\n".join(l for _, l in lines[start:])


def top_part(md: str) -> str:
    """先頭から最初の ## の見出しの前まで。"""
    lines = _outside_code(md)
    for i, (code, line) in enumerate(lines):
        if not code and line.startswith("## "):
            return "\n".join(l for _, l in lines[:i])
    return md


def _attrs(tag: str) -> dict[str, str]:
    return dict(re.findall(r"([\w-]+)=\"([^\"]*)\"", tag))


def pictures(md: str) -> list[dict]:
    """<picture> ごとに、<source> の media・srcset の並びと、<img> の src・alt・width。"""
    out = []
    for m in re.finditer(r"<picture>(.*?)</picture>", md, re.S):
        body = m.group(1)
        sources = [_attrs(s) for s in re.findall(r"<source\b[^>]*>", body)]
        imgs = [_attrs(s) for s in re.findall(r"<img\b[^>]*>", body)]
        img = imgs[0] if imgs else {}
        out.append(
            {
                "start": m.start(),
                "end": m.end(),
                "sources": [{"media": s.get("media", ""), "srcset": s.get("srcset", "")} for s in sources],
                "src": img.get("src", ""),
                "alt": img.get("alt", ""),
                "width": img.get("width", ""),
            }
        )
    return out


ALERT_START = re.compile(r"^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$")


def alerts(md: str) -> list[tuple[str, str]]:
    """> [!NOTE] などで始まり、> の続いた行のかたまりの（種類, 中身）。"""
    out = []
    lines = [line for code, line in _outside_code(md) if not code]
    i = 0
    while i < len(lines):
        m = ALERT_START.match(lines[i].strip())
        if not m:
            i += 1
            continue
        body = []
        i += 1
        while i < len(lines) and lines[i].lstrip().startswith(">"):
            body.append(lines[i].lstrip()[1:].strip())
            i += 1
        out.append((m.group(1), "\n".join(body)))
    return out


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_size(path: Path) -> tuple[int, int]:
    """PNG の（幅, 高さ）を IHDR から読む。PNG でなければ ValueError。"""
    data = path.read_bytes()[:24]
    if len(data) < 24 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise ValueError(f"PNG ではありません: {path.name}")
    return struct.unpack(">II", data[16:24])


def code_blocks(md: str, lang: str) -> list[list[str]]:
    """```<lang> のコードブロックの中の行。"""
    out = []
    current: list[str] | None = None
    for line in md.splitlines():
        s = line.strip()
        if current is None:
            if s == f"```{lang}":
                current = []
        elif s == "```":
            out.append(current)
            current = None
        else:
            current.append(line)
    return out


# ---- D0009-AC-03: アンカーの作り方（D0014 のリンクの検査も使う） ----------------------------


@pytest.mark.parametrize(
    "title,anchor",
    [
        ("パイプ（目的に合わせた段の並び）", "パイプ目的に合わせた段の並び"),
        ("設定（pipeline.toml）", "設定pipelinetoml"),
        ("VSCode の拡張", "vscode-の拡張"),
        ("記録だけを書く（`pipe-in record`）", "記録だけを書くpipe-in-record"),
        ("分岐・飛び先・並列", "分岐飛び先並列"),
        ("確認で止めて、あとから答える（チャットから動かすとき）", "確認で止めてあとから答えるチャットから動かすとき"),
        ("[リンク](https://example.com) の <b>見出し</b>", "リンク-の-見出し"),
    ],
)
def test_d0009_ac03_github_anchor(title, anchor):
    """D0009-AC-03: アンカーの作り方そのものが、GitHub と同じアンカーを作る。"""
    assert github_anchor(title) == anchor


def test_d0009_ac03_github_anchor_duplicates():
    """D0009-AC-03: 同じ見出しが続くと、2回目に -1、3回目に -2 が付く。"""
    assert heading_anchors("## 例\n\n### 例\n\n## 例\n") == ["例", "例-1", "例-2"]


def test_d0009_ac03_broken_link_finder():
    """D0009-AC-03: 切れたリンクの見つけ方そのものが、無いアンカーへのリンクを見つけ、コードの中の # を見出しにしない。"""
    md = (
        "## 使い方\n\n"
        "[ok](#使い方) [ng](#無い)\n\n"
        "```bash\n# コメント\n[code](#コードの中は見ない)\n```\n\n"
        "[c](#コメント)\n"
        '<a id="migrate"></a>\n'
        '[m](#migrate) <a href="#x">x</a>\n'
    )
    assert broken_links(md) == ["無い", "コメント", "x"]


# ---- D0009-AC-09: アラートの見つけ方（D0014 のアラートの検査も使う） ---------------------------


def test_d0009_ac09_alert_finder():
    """D0009-AC-09: アラートの見つけ方そのものが、> の続いたかたまりを1つと数え、ただの引用とコードの中は数えない。"""
    md = (
        "> [!NOTE]\n> 費用は概算です。\n> 2行目\n\n"
        "> ただの引用\n\n"
        "```\n> [!WARNING]\n> コードの中\n```\n\n"
        "> [!WARNING]\n> `--yes` は確認なしで流す\n"
    )
    assert alerts(md) == [("NOTE", "費用は概算です。\n2行目"), ("WARNING", "`--yes` は確認なしで流す")]


# ---- D0009-AC-10: すぐ試すの順 ------------------------------------------------------


def test_d0009_ac10_quick_start_order():
    """D0009-AC-10・D0014-AC-05: 「すぐ試す」の中で git clone → venv → 両方の activate → pip install → pipe-in --project の順に出てくる。"""
    sec = section(readme(), "すぐ試す")
    assert sec, "## すぐ試す が無い"
    clone = sec.find("git clone")
    assert clone >= 0, "git clone が無い"
    venv = sec.find("venv", clone)
    assert venv > clone, "git clone のあとに venv が無い"
    win = sec.find(".venv/Scripts/activate", venv)
    unix = sec.find(".venv/bin/activate", venv)
    assert win > venv and unix > venv, "venv のあとに .venv/Scripts/activate と .venv/bin/activate の両方が無い"
    pip = sec.find("pip install", max(win, unix))
    assert pip > 0, "activate のあとに pip install が無い"
    assert sec.find("pipe-in --project", pip) > pip, "pip install のあとに最初の pipe-in --project が無い"


# ---- <picture> の検査の補助（D0009-AC-13 と D0014-AC-19 が使う） -------------------------------


def _picture_problems(pics: list[dict], resolve) -> list[str]:
    problems = []
    for i, p in enumerate(pics):
        if not any("prefers-color-scheme: dark" in s["media"] for s in p["sources"]):
            problems.append(f"{i}: 暗い表示の <source> が無い")
        if not p["alt"].strip():
            problems.append(f"{i}: alt が空")
        if not p["width"].strip():
            problems.append(f"{i}: width が無い")
        for ref in [s["srcset"] for s in p["sources"]] + [p["src"]]:
            if not ref or not resolve(ref).is_file():
                problems.append(f"{i}: 指すファイルが無い {ref!r}")
    return problems


def _used_names(pics: list[dict], resolve) -> set[str]:
    out = set()
    for p in pics:
        for ref in [s["srcset"] for s in p["sources"]] + [p["src"]]:
            if ref and resolve(ref).resolve() == (ASSETS / Path(ref).name).resolve():
                out.add(Path(ref).name)
    return out


# ---- D0009-AC-12: PNG の上限 --------------------------------------------------------


def test_d0009_ac12_png_limits():
    """D0009-AC-12: docs/assets/ の PNG は4枚以上で、どれも横 1600px 以下・600KB 以下。"""
    pngs = sorted(ASSETS.glob("*.png"))
    assert len(pngs) >= 4, [p.name for p in pngs]
    too_big = []
    for p in pngs:
        width, _ = png_size(p)
        if width > 1600:
            too_big.append(f"{p.name}: 横 {width}px")
        if p.stat().st_size > 600 * 1024:
            too_big.append(f"{p.name}: {p.stat().st_size} バイト")
    assert too_big == []


def _tiny_png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return PNG_SIGNATURE + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def test_d0009_ac12_png_size_reader(tmp_path):
    """D0009-AC-12: PNG の大きさの読み方そのものが、幅と高さを読み、PNG でないものは断る。"""
    png = tmp_path / "a.png"
    png.write_bytes(_tiny_png(3, 2))
    assert png_size(png) == (3, 2)
    bad = tmp_path / "b.png"
    bad.write_bytes(b"GIF89a" + b"\x00" * 30)
    with pytest.raises(ValueError):
        png_size(bad)


# ---- D0009-AC-13: 拡張の README の画像 ------------------------------------------------


def _vscode_resolve(ref: str) -> Path:
    if ref.startswith(RAW_PREFIX):
        return ROOT / ref[len(RAW_PREFIX):]
    return (ROOT / "vscode" / ref).resolve()


def test_d0009_ac13_vscode_readme_pictures():
    """D0009-AC-13・D0014-AC-20: vscode/README.md に、パネルと作業台の明暗の画像の <picture> があり、指すパス（../docs/assets/… か raw の URL）が実在する。"""
    pics = pictures(VSCODE_README.read_text(encoding="utf-8"))
    assert pics, "vscode/README.md に <picture> が無い"
    assert _picture_problems(pics, _vscode_resolve) == []
    assert set(IMAGES) <= _used_names(pics, _vscode_resolve)


# ---- D0009-AC-18: 撮り直しの手順 -----------------------------------------------------


def test_d0009_ac18_retake_doc():
    """D0009-AC-18: docs/assets/README.md に npm run preview と4つの画像の名前があり、その4つが実在する。"""
    doc = ASSETS / "README.md"
    assert doc.is_file(), "docs/assets/README.md が無い"
    text = doc.read_text(encoding="utf-8")
    assert "npm run preview" in text
    assert [n for n in IMAGES if n not in text] == []
    assert [n for n in IMAGES if not (ASSETS / n).is_file()] == []


# ---- D0009-AC-19: 置き場所の表・CLAUDE.md・SKILL.md ----------------------------------------


def test_d0009_ac19_docs_mention_panel_pages():
    """D0009-AC-19: design.md の表に見本の記録と docs/assets/ があり、CLAUDE.md の npm run preview の行にパネルのページの名前がある。
    （/pipe-in の SKILL.md の部分は、D0039-AC-18 で、補助ファイル screen-check.md の検査 D0039-AC-17 に置き換わった。）"""
    design = (ROOT / "docs" / "development" / "design.md").read_text(encoding="utf-8")
    rows = [line for line in design.splitlines() if line.startswith("|")]
    assert any("`tests/fixtures/showcase/`" in r for r in rows), "design.md の表に tests/fixtures/showcase/ が無い"
    assert any("`docs/assets/`" in r for r in rows), "design.md の表に docs/assets/ が無い"
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    preview = [line for line in claude.splitlines() if "npm run preview" in line]
    assert preview and any("run-panel" in line for line in preview), "CLAUDE.md の npm run preview の行に run-panel が無い"
