"""初めての人向けの案内と英語の文書（D0072）：英語版 README の並置・食い違い検査・コマンドを打たない人向けの文書。

文書は読むだけで書かない（偽の英語版は tmp_path に作る）。SDK は呼ばない。
前の名前は、この文書に直接書かない（tests/test_rename.py の一覧に無いファイルなので）。要るときは test_readme.OLD を使う。
補助の関数は tests/test_readme.py のものを使う（tests/test_guide.py と同じ形）。
食い違い検査の関数（fences・shell_commands・mismatches・broken_links）は、このテストのファイルの中に置く（本番のコードではない）。
案内（walkthrough）の検査は vscode/src/manifest.test.ts にある。
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

import pytest

from test_readme import OLD, anchors, headings, pictures, text_outside_code, top_part

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "guide"
NEW_DOC = GUIDE / "start-without-commands.md"

# ROOT からの相対（日本語版, 英語版）
PAIRS = [("README.md", "README.en.md"), ("vscode/README.md", "vscode/README.en.md")]
SHELL_LANGS = {"bash", "sh", "shell", "console", "powershell"}


# ---- 食い違い検査（本番のコードではなく、このテストの中の関数） ----------------


def fences(md: str) -> list[tuple[str, list[str]]]:
    """``` の塊を順番どおりに（言語, 中の行）で返す。言語は開きの行の先頭の語（無ければ空）。"""
    out: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    lang = ""
    for line in md.splitlines():
        s = line.strip()
        if current is None:
            if s.startswith("```"):
                rest = s[3:].strip().split()
                lang = rest[0] if rest else ""
                current = []
        elif s.startswith("```"):
            out.append((lang, current))
            current = None
        else:
            current.append(line)
    return out


def shell_commands(lines: list[str]) -> list[str]:
    """比べるコマンドの行：空行・# で始まる行を捨て、行末のコメントを捨て、引用符の中を "" にし、空白を詰める。"""
    out = []
    for raw in lines:
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        buf = []
        quote = ""
        for i, ch in enumerate(raw):
            if quote:
                if ch == quote:
                    quote = ""
                    buf.append(ch)
                continue
            if ch in "\"'":
                quote = ch
                buf.append(ch)
                continue
            if ch == "#" and (i == 0 or raw[i - 1].isspace()):
                break
            buf.append(ch)
        line = re.sub(r"\s+", " ", "".join(buf)).strip()
        if line:
            out.append(line)
    return out


def _image_names(md: str) -> list[str]:
    names = []
    for p in pictures(md):
        for s in p["sources"]:
            names.append(Path(s["srcset"]).name)
        names.append(Path(p["src"]).name)
    return names


def mismatches(ja_path: Path, en_path: Path) -> list[str]:
    """日本語版と英語版の食い違いの文。空なら合う。文の頭は「見出し」「コードの塊」「コマンド」「画像」のどれか。"""
    ja = ja_path.read_text(encoding="utf-8")
    en = en_path.read_text(encoding="utf-8")
    out = []
    ja_h = [d for d, _ in headings(ja)]
    en_h = [d for d, _ in headings(en)]
    if ja_h != en_h:
        out.append(f"見出し：数と深さの並びが違う（日本語版 {ja_h}、英語版 {en_h}）")
    ja_f = fences(ja)
    en_f = fences(en)
    ja_l = [lang for lang, _ in ja_f]
    en_l = [lang for lang, _ in en_f]
    if ja_l != en_l:
        out.append(f"コードの塊：数か言語の並びが違う（日本語版 {ja_l}、英語版 {en_l}）")
    else:
        for i, ((lang, a), (_, b)) in enumerate(zip(ja_f, en_f)):
            if lang in SHELL_LANGS and shell_commands(a) != shell_commands(b):
                out.append(f"コマンド：{i + 1} つ目の塊のコマンドの行が違う（日本語版 {shell_commands(a)}、英語版 {shell_commands(b)}）")
    if _image_names(ja) != _image_names(en):
        out.append(f"画像：<picture> の画像のファイル名の並びが違う（日本語版 {_image_names(ja)}、英語版 {_image_names(en)}）")
    return out


def broken_links(path: Path) -> list[str]:
    """相対リンクと <picture> の画像のうち、行き先（ファイル・フォルダ・アンカー）が無いもの。"""
    md = path.read_text(encoding="utf-8")
    text = text_outside_code(md)
    bad = []
    for target in re.findall(r"\]\(([^)\s]+)", text):
        if re.match(r"(https?:|mailto:)", target):
            continue
        file_part, _, anchor = target.partition("#")
        dest = path if not file_part else path.parent / unquote(file_part)
        if not dest.exists():
            bad.append(f"{target}（行き先が無い）")
            continue
        if anchor and dest.is_file() and dest.suffix == ".md":
            if unquote(anchor) not in anchors(dest.read_text(encoding="utf-8")):
                bad.append(f"{target}（アンカーが無い）")
    for p in pictures(md):
        refs = [s["srcset"] for s in p["sources"]] + [p["src"]]
        for ref in refs:
            if ref and not ref.startswith("http") and not (path.parent / unquote(ref)).exists():
                bad.append(f"{ref}（画像が無い）")
    return bad


# ---- 補助 ------------------------------------------------------------------


def need(rel: str) -> Path:
    p = ROOT / rel
    if not p.is_file():
        pytest.fail(f"{rel} が無い")
    return p


def pair_paths(pair: tuple[str, str]) -> tuple[Path, Path]:
    return need(pair[0]), need(pair[1])


def only(items: list[str], *heads: str) -> list[str]:
    return [m for m in items if m.startswith(heads)]


pair_param = pytest.mark.parametrize("pair", PAIRS, ids=[p[1] for p in PAIRS])


# ---- 文書（コマンドを打たない人向け） -----------------------------------------


def test_D0072_AC_10_新しい文書がありリンクが切れていない():
    """D0072-AC-10: start-without-commands.md が実在し 1 行目が見出し。ガイドの目次・README・拡張の README から指され、リンクが切れていない。"""
    doc = need("docs/guide/start-without-commands.md")
    assert doc.read_text(encoding="utf-8").splitlines()[0].startswith("# ")
    for rel in ["docs/guide/README.md", "README.md", "vscode/README.md"]:
        p = need(rel)
        assert "start-without-commands.md" in p.read_text(encoding="utf-8"), f"{rel} から start-without-commands.md へのリンクが無い"
        assert broken_links(p) == [], f"{rel} のリンクが切れている"
    assert broken_links(doc) == []


def test_D0072_AC_11_端末の1行が要ると書き言い切りの語が無い():
    """D0072-AC-11: 端末で 1 行貼る手順が要ることが書いてあり、「何も打たなくてよい」と言い切っていない。"""
    text = need("docs/guide/start-without-commands.md").read_text(encoding="utf-8")
    assert "端末" in text, "端末で 1 行貼る手順が要ることが書いてない"
    assert "pipe-in" in text
    for phrase in ["何も打たなくて", "コマンドは不要", "一切打たなくて", "何も入力しなくて"]:
        assert phrase not in text, f"言い切りの語「{phrase}」がある"


def test_D0072_AC_12_ガイドの文書は11個():
    """D0072-AC-12: docs/guide/ の .md は 11 個で、start-without-commands.md を含む。"""
    names = sorted(p.name for p in GUIDE.glob("*.md"))
    assert "start-without-commands.md" in names
    assert len(names) == 11, names


# ---- 英語の並置 ------------------------------------------------------------


def test_D0072_AC_13_英語版が実在する():
    """D0072-AC-13: README.en.md と vscode/README.en.md が実在する。"""
    for _, en in PAIRS:
        need(en)


@pair_param
def test_D0072_AC_14_見出しの数と深さがそろう(pair):
    """D0072-AC-14: 日本語版と英語版の見出しの数と深さの並びが同じ。"""
    ja, en = pair_paths(pair)
    assert only(mismatches(ja, en), "見出し") == []


@pair_param
def test_D0072_AC_15_コードの塊とコマンドの行がそろう(pair):
    """D0072-AC-15: コードの塊の数・言語・順番と、塊の中のコマンドの行が同じ。"""
    ja, en = pair_paths(pair)
    assert only(mismatches(ja, en), "コードの塊", "コマンド") == []


@pair_param
def test_D0072_AC_16_pictureの画像の並びがそろう(pair):
    """D0072-AC-16: <picture> が指す画像のファイル名の並びが同じ。"""
    ja, en = pair_paths(pair)
    assert only(mismatches(ja, en), "画像") == []


@pair_param
def test_D0072_AC_17_英語版の相対リンクとアンカーが実在する(pair):
    """D0072-AC-17: 英語版の相対リンクが実在するファイルかフォルダを指し、アンカーが行き先の見出しに当たる。"""
    _, en = pair_paths(pair)
    assert broken_links(en) == []


@pair_param
def test_D0072_AC_14_実物が空でなく検査が何も見ずに通らない(pair):
    """D0072-AC-14: 実物の 2 組それぞれに、コードの塊が 1 つ以上・見出しが 3 つ以上ある（空の文書で通らない）。"""
    ja, en = pair_paths(pair)
    for p in (ja, en):
        md = p.read_text(encoding="utf-8")
        assert len(fences(md)) >= 1, p.name
        assert len(headings(md)) >= 3, p.name


@pair_param
def test_D0072_AC_19_相互のリンクが先頭にある(pair):
    """D0072-AC-19: 日本語版の先頭に英語版へのリンクがあり、英語版の先頭に日本語版へのリンクがある。"""
    ja, en = pair_paths(pair)
    assert f"({en.name})" in top_part(ja.read_text(encoding="utf-8")), f"{ja.name} の先頭に {en.name} へのリンクが無い"
    assert f"({ja.name})" in top_part(en.read_text(encoding="utf-8")), f"{en.name} の先頭に {ja.name} へのリンクが無い"


def test_D0072_AC_21_英語版に前の名前の綴りが無い():
    """D0072-AC-21: 英語の文書 2 つに前の名前の綴りが無い（綴りは test_readme.OLD でつなぐ）。"""
    for _, en in PAIRS:
        assert OLD not in need(en).read_text(encoding="utf-8").lower(), en


def test_D0072_AC_22_文書だけの足しで記録と設定の形に触れない():
    """D0072-AC-22: 本体とジェネレーターの .py に walkthrough が出ない（足すのは文書・宣言・テストだけ。今のまま通る。守る）。"""
    files = [p for d in ("pipe_in", "generator") for p in (ROOT / d).rglob("*.py")]
    assert files, "本体の .py が見つからない"
    assert [p.name for p in files if "walkthrough" in p.read_text(encoding="utf-8")] == []


# ---- 検査そのものの確かめ（偽の英語版は tmp_path） --------------------------------

FENCE = "`" * 3

SAMPLE_JA = f"""# タイトル

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/a-dark.png">
  <img src="docs/assets/a-light.png" alt="見本" width="600">
</picture>

## 入れる

{FENCE}bash
# 仮想環境を作る
pip install -e .                # 入れる
{FENCE}

## 流す

{FENCE}bash
pipe-in --project ~/src/myapp --text "ユーザー一覧に CSV 出力ボタンを追加したい"
{FENCE}
"""

SAMPLE_EN_SAME_SHAPE = f"""# Title

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/a-dark.png">
  <img src="docs/assets/a-light.png" alt="sample" width="600">
</picture>

## Install

{FENCE}bash
# Create a virtual environment
pip install -e .   # install it
{FENCE}

## Run

{FENCE}bash
pipe-in --project ~/src/myapp --text "Add a CSV export button to the user list"
{FENCE}
"""


def make_pair(tmp_path: Path, ja: str, en: str) -> tuple[Path, Path]:
    a = tmp_path / "doc.md"
    b = tmp_path / "doc.en.md"
    a.write_text(ja, encoding="utf-8")
    b.write_text(en, encoding="utf-8")
    return a, b


def _swap_images(s: str) -> str:
    return s.replace("a-dark.png", "@@").replace("a-light.png", "a-dark.png").replace("@@", "a-light.png")


BROKEN = [
    ("見出しを1つ足した", lambda s: s + "\n## Extra\n", "見出し"),
    ("見出しの深さを変えた", lambda s: s.replace("## Run", "### Run"), "見出し"),
    ("コードの塊を1つ減らした", lambda s: s[: s.rindex(f"{FENCE}bash")], "コードの塊"),
    ("塊の言語を変えた", lambda s: s.replace(f"{FENCE}bash\npipe-in", f"{FENCE}text\npipe-in"), "コードの塊"),
    ("コマンドの行を1つ変えた", lambda s: s.replace("pip install -e .", "pip install ."), "コマンド"),
    ("画像を入れ替えた", _swap_images, "画像"),
    ("画像の名前を変えた", lambda s: s.replace("a-light.png", "b-light.png"), "画像"),
]


def test_D0072_AC_18_見本の日本語版は見出し_塊_画像を持つ():
    """D0072-AC-18: 見本の日本語版が見出し・塊・画像を持つ（検査が何も見ずに通ることの防ぎ。今のまま通る）。"""
    assert len(headings(SAMPLE_JA)) == 3
    assert len(fences(SAMPLE_JA)) == 2
    assert len(pictures(SAMPLE_JA)) == 1


def test_D0072_AC_18_文だけが違う英語版は通る(tmp_path):
    """D0072-AC-18: コメントの文と引用符の中の文だけが違う英語版は、食い違いなしで通る（今のまま通る）。"""
    ja, en = make_pair(tmp_path, SAMPLE_JA, SAMPLE_EN_SAME_SHAPE)
    assert mismatches(ja, en) == []


@pytest.mark.parametrize("name, change, kind", BROKEN, ids=[b[0] for b in BROKEN])
def test_D0072_AC_18_検査そのものが食い違いを見つける(tmp_path, name, change, kind):
    """D0072-AC-18: 偽の英語版（見出し・塊・コマンド・画像のどれかを変えたもの）を、検査が見つけて、それぞれの種類で報告する。"""
    changed = change(SAMPLE_EN_SAME_SHAPE)
    assert changed != SAMPLE_EN_SAME_SHAPE, "偽の英語版が変わっていない（テストの誤り）"
    ja, en = make_pair(tmp_path, SAMPLE_JA, changed)
    found = mismatches(ja, en)
    assert only(found, kind), f"{name}のに「{kind}」の食い違いが出ない：{found}"


def test_D0072_AC_18_コマンド整形はコメントと引用符の中を比べない():
    """D0072-AC-18: shell_commands は # の行・行末のコメントを捨て、引用符の中を "" にし、空白を詰める（今のまま通る）。"""
    lines = ["# 説明", "", ". .venv/Scripts/activate        # Windows の Git Bash", 'pipe-in  --text "日本語の文 # not comment"']
    assert shell_commands(lines) == [". .venv/Scripts/activate", 'pipe-in --text ""']
