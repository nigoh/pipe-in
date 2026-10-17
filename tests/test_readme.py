"""README（D0009）：冒頭の並び・節の順・切れたリンクが無い・情報を落とさない・アラート・画像・CLI の出力・撮り直しの手順。

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
MIGRATION_TITLE = f"{OLD} から移る"

IMAGES = ["run-panel-light.png", "run-panel-dark.png", "pipe-editor-light.png", "pipe-editor-dark.png"]

SECTIONS = [
    "すぐ試す",
    "使い方",
    "VSCode の拡張",
    "パイプ（目的に合わせた段の並び）",
    "安全のしくみ",
    "記録と使用量",
    "設定（pipeline.toml）",
    "終了コード",
    MIGRATION_TITLE,
    "中身を直したいとき",
    "注意",
    "ライセンス",
]


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


# ---- D0009-AC-01: 冒頭の並び ------------------------------------------------------


def test_d0009_ac01_top_order():
    """D0009-AC-01: 最初の ## の前に、ロゴの <picture> → 一文 → パネルの画像の <picture> → 要点の箇条書き → 目次、がこの順にある。"""
    top = top_part(readme())
    pics = pictures(top)
    logo = next((p for p in pics if "pipe-in-logo" in p["src"]), None)
    panel = next((p for p in pics if "run-panel-" in p["src"]), None)
    assert logo is not None, "冒頭にロゴの <picture> が無い"
    assert panel is not None, "冒頭にパネルの画像の <picture> が無い"
    sentence = re.search(r"^pipe-in は.*要件定義 → 設計 → テスト先行 → 実装 → 検証", top, re.M)
    assert sentence is not None, "冒頭に「pipe-in は、要件メモから 要件定義 → … → 検証 …」の一文が無い"
    bullet = re.search(r"^- .*\]\(#", top, re.M)
    assert bullet is not None, "冒頭に、節へのリンクのある要点の箇条書きが無い"
    toc = re.search(r"^\*\*目次\*\*", top, re.M)
    assert toc is not None, "冒頭に「**目次**」の行が無い"
    order = [logo["end"], sentence.start(), panel["start"], bullet.start(), toc.start()]
    assert order == sorted(order), "冒頭の並びが ロゴ → 一文 → パネルの画像 → 要点 → 目次 になっていない"
    assert logo["end"] <= sentence.start() < panel["start"]
    assert panel["end"] <= bullet.start()


# ---- D0009-AC-02: ## の順 ---------------------------------------------------------


def test_d0009_ac02_section_order():
    """D0009-AC-02: ## の見出しを上から並べると、決めた12の節の順と一致する。"""
    assert [t for d, t in headings(readme()) if d == 2] == SECTIONS


# ---- D0009-AC-03: 切れたリンクが無い ------------------------------------------------


def test_d0009_ac03_no_broken_links():
    """D0009-AC-03: README の ](#…) と href="#…" は、すべて見出しのアンカーか <a id> を指す。"""
    assert broken_links(readme()) == []


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


# ---- D0009-AC-04: 要点と目次のリンク ------------------------------------------------


def test_d0009_ac04_points_link_to_sections():
    """D0009-AC-04: 冒頭の要点の箇条書きは5〜7項目で、どの項目にも README の中の節へのリンクがある。"""
    top = top_part(readme())
    points = [line for line in top.splitlines() if line.startswith("- ")]
    assert 5 <= len(points) <= 7, points
    assert [p for p in points if "](#" not in p] == []


def test_d0009_ac04_toc_lists_all_sections():
    """D0009-AC-04: 目次のリンクは ## の節のアンカーの並びと同じで、移行の節へは #migrate、その見出しの直前に <a id="migrate"></a> がある。"""
    md = readme()
    toc = next((line for line in top_part(md).splitlines() if line.startswith("**目次**")), None)
    assert toc is not None, "冒頭に「**目次**」の行が無い"
    expected = ["migrate" if t == MIGRATION_TITLE else github_anchor(t) for t in SECTIONS]
    assert [unquote(a) for a in re.findall(r"\]\(#([^)\s]+)\)", toc)] == expected
    lines = md.splitlines()
    at = lines.index(f"## {MIGRATION_TITLE}")
    before = [line for line in lines[:at] if line.strip()]
    assert before and before[-1].strip() == '<a id="migrate"></a>'


# ---- D0009-AC-05: 他のファイルが名指しする見出し ------------------------------------------


def test_d0009_ac05_named_headings_exist():
    """D0009-AC-05: 「## 使い方」・「パイプ」で始まる ##・「### Claude Code のプラグイン」・移行の節の見出しがある。"""
    hs = headings(readme())
    assert (2, "使い方") in hs
    assert any(d == 2 and t.startswith("パイプ") for d, t in hs)
    assert (3, "Claude Code のプラグイン") in hs
    assert (2, MIGRATION_TITLE) in hs


# ---- D0009-AC-07: コマンドが残る -----------------------------------------------------

COMMANDS = [
    "pipe-in --project ~/src/myapp --input request.md",
    'pipe-in --project ~/src/myapp --text "ユーザー一覧に CSV 出力ボタンを追加したい"',
    "pipe-in --project ~/src/myapp --input request.md --yes",
    'pipe-in --project ~/src/myapp --input request.md --test-cmd "pytest -q"',
    "python -m pipe_in",
    "pipe-in --project ~/src/myapp --from design",
    "pipe-in --project ~/src/myapp --from red",
    "pipe-in --project ~/src/myapp --from implement",
    "pipe-in --project ~/src/myapp --from test",
    'pipe-in --project ~/src/myapp --input request.md --pause --test-cmd "pytest -q"',
    'pipe-in --project ~/src/myapp --review approve --test-cmd "pytest -q"',
    'pipe-in --project ~/src/myapp --review revise --feedback "AC-03 を分けて"',
    "pipe-in --project ~/src/myapp --review quit",
    'pipe-in record start --text "要件メモ"',
    "pipe-in record begin requirements",
    'pipe-in record done requirements --summary "…"',
    "pipe-in record wait requirements",
    "pipe-in record review requirements approved",
    'pipe-in record red red --summary "…"',
    'pipe-in record verdict pass --attempt 1 --summary "…"',
    "pipe-in record finish PASSED",
    "pipe-in-gen list --project ~/src/myapp",
    "pipe-in-gen new diagrams --from diagrams --project ~/src/myapp",
    'pipe-in-gen design apidoc --purpose "ソースから API の文書を作り、突き合わせたい" --project ~/src/myapp',
    "pipe-in-gen check diagrams --project ~/src/myapp",
    'pipe-in --pipe diagrams --project ~/src/myapp --text "注文の流れを中心に"',
    "/plugin marketplace add <pipe-in のリポジトリのフォルダか GitHub の nigoh/pipe-in>",
    "/plugin install pipe-in@pipe-in",
    "pip install -e .",
    "pip install -e '.[dev]' && pytest",
    f"pip uninstall {OLD}",
    "pip install -e '.[dev]'",
    f"/plugin marketplace remove {OLD}",
    "/plugin marketplace add nigoh/pipe-in",
    f"code --uninstall-extension nok.{OLD}-vscode",
    "mkdir -p .pipe-in/pipes",
    f"git mv .{OLD}/pipes/{OLD}-<名前> .pipe-in/pipes/pipe-in-<名前>",
    "git remote set-url origin https://github.com/nigoh/pipe-in.git",
]


@pytest.mark.parametrize("command", COMMANDS)
def test_d0009_ac07_commands_kept(command):
    """D0009-AC-07: 並べ直す前の README にあったコマンドの行が、README に残っている。"""
    assert command in readme()


# ---- D0009-AC-08: 表の項目が残る ----------------------------------------------------

TABLE_ITEMS = [
    # 作られるファイル
    "`00_input.md`", "`01_requirements.md`", "`02_design.md`", "`03_red_tests.md`", "`04_implementation.md`",
    "`05_test_report.md`", "`99_summary.md`", "`state.json`", "`logs/*.jsonl`",
    # 段ごとの役割と書き込める範囲
    "要件定義", "設計", "テスト先行", "実装", "検証",
    # access
    "`read`", "`docs`", "`tests`", "`code`",
    # pipeline.toml のほかの項目
    "`domain_dir`", "`setting_sources`", "`protected_paths`", "`extra_test_globs`",
    # 終了コード
    "0", "1", "2", "3", "4", "5", "130",
    # まとめに出る使用量
    "トークンの内訳", "モデル別", "環境", "利用枠",
    # プラグインで入るもの
    "スキル `/pipe-in:pipe-build`", "エージェント `pipe-builder`", "フック（`pipe-in-gen guard-hook`）",
    # ひな形
    "`dev`", "`diagrams`", "`spec-qa`",
    # 中身を直したいとき
    "開発フローの各段への指示（文書の構成、守ること）",
    "開発フローの段の順番、確認、差し戻しの流れ",
    "開発フローの段ごとのツールと書き込み範囲",
    "どのパイプにも共通の流れ（記録・確認・まとめ）",
    "止める操作",
    "SDK の呼び出し",
    "パイプの読み込み・検査・流れ・権限の型",
    "パイプの生成・環境の検出・ひな形",
]


@pytest.mark.parametrize("item", TABLE_ITEMS)
def test_d0009_ac08_table_items_kept(item):
    """D0009-AC-08: 並べ直す前の README の表の行（行の頭の項目）が、README の表に残っている。"""
    assert re.search(rf"^\|\s*{re.escape(item)}\s*\|", readme(), re.M), item


# ---- D0009-AC-09: アラート -----------------------------------------------------------


def test_d0009_ac09_alerts():
    """D0009-AC-09: GitHub のアラートが3つ以上あり、「概算」「.pipe-in/ をコミットの前に見る」「--yes」がそれぞれアラートの中にある。"""
    found = alerts(readme())
    assert len(found) >= 3, found
    bodies = [body for _, body in found]
    assert any("概算" in b for b in bodies), "費用が概算であることのアラートが無い"
    assert any(".pipe-in/" in b and "コミット" in b for b in bodies), ".pipe-in/ をコミットの前に見るアラートが無い"
    assert any("--yes" in b for b in bodies), "--yes のアラートが無い"


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
    """D0009-AC-10: 「すぐ試す」の中で git clone → venv → 両方の activate → pip install → pipe-in --project の順に出てくる。"""
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


# ---- D0009-AC-11: <picture> --------------------------------------------------------


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


def test_d0009_ac11_pictures():
    """D0009-AC-11: README の <picture> はどれも暗い表示の <source> と alt・width のある <img> を持ち、指すファイルが実在し、パネルと作業台の明暗4枚を使っている。"""
    pics = pictures(readme())
    resolve = lambda ref: ROOT / ref  # noqa: E731
    assert pics, "<picture> が無い"
    assert _picture_problems(pics, resolve) == []
    assert set(IMAGES) <= _used_names(pics, resolve), f"使われていない画像: {sorted(set(IMAGES) - _used_names(pics, resolve))}"


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
    """D0009-AC-13: vscode/README.md に、パネルと作業台の明暗の画像の <picture> があり、指すパス（../docs/assets/… か raw の URL）が実在する。"""
    pics = pictures(VSCODE_README.read_text(encoding="utf-8"))
    assert pics, "vscode/README.md に <picture> が無い"
    assert _picture_problems(pics, _vscode_resolve) == []
    assert set(IMAGES) <= _used_names(pics, _vscode_resolve)


# ---- D0009-AC-17: CLI の出力 -------------------------------------------------------


def python_project(tmp_path: Path) -> Path:
    project = tmp_path / "myapp"
    (project / "src").mkdir(parents=True)
    (project / "docs").mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "myapp"\n[project.optional-dependencies]\ndev = ["pytest>=8"]\n', encoding="utf-8"
    )
    return project


def _normalize(out: str, project: Path) -> list[str]:
    for p in {str(project), project.as_posix()}:
        out = out.replace(p, "<対象>")
    lines = [line.rstrip() for line in out.replace("\\", "/").splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def test_d0009_ac17_cli_output_matches(tmp_path, monkeypatch, capsys):
    """D0009-AC-17: README の pipe-in-gen new / check の出力は、tmp_path で流した本物の出力と（手元のパスの置き換えを除いて）一致する。"""
    import os

    from pipe_in.pipe import definition as pd
    from pipe_in_generator import cli

    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    monkeypatch.delenv("DEV" + "PIPE_PIPES_DIR", raising=False)

    def fake_default() -> Path:
        env = pd.env_pipes_dir(os.environ)
        return Path(env) if env else tmp_path / "repo-pipes"

    monkeypatch.setattr(pd, "default_pipes_dir", fake_default)
    project = python_project(tmp_path).resolve()
    monkeypatch.chdir(project)

    blocks = [b for b in code_blocks(readme(), "text") if b and b[0].startswith("$ pipe-in-gen ")]
    assert [b[0][len("$ pipe-in-gen "):].strip() for b in blocks] == ["new diagrams --from diagrams", "check diagrams"]
    for block in blocks:
        argv = block[0][len("$ pipe-in-gen "):].split()
        capsys.readouterr()
        assert cli.main(argv) == 0, argv
        got = _normalize(capsys.readouterr().out, project)
        want = [line.rstrip() for line in block[1:]]
        while want and not want[-1]:
            want.pop()
        assert got == want, argv


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
    """D0009-AC-19: design.md の表に見本の記録と docs/assets/ があり、CLAUDE.md の npm run preview の行と /pipe-in の SKILL.md にパネルのページの名前がある。"""
    design = (ROOT / "docs" / "development" / "design.md").read_text(encoding="utf-8")
    rows = [line for line in design.splitlines() if line.startswith("|")]
    assert any("`tests/fixtures/showcase/`" in r for r in rows), "design.md の表に tests/fixtures/showcase/ が無い"
    assert any("`docs/assets/`" in r for r in rows), "design.md の表に docs/assets/ が無い"
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    preview = [line for line in claude.splitlines() if "npm run preview" in line]
    assert preview and any("run-panel" in line for line in preview), "CLAUDE.md の npm run preview の行に run-panel が無い"
    skill = (ROOT / ".claude" / "skills" / "pipe-in" / "SKILL.md").read_text(encoding="utf-8")
    assert "run-panel-light.html" in skill and "run-panel-dark.html" in skill
