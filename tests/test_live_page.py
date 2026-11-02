"""D0027：進み具合のページの HTML（pipe_in/engine/live_page.py の build_page）。

HTML は1枚で完結し、外部の読み込みが無く、外から来た文字を入れない。ここは文字の検査（構造・CSS・禁止語）。
ページの JS の動きは tests/test_live_page_js.py（Node で動かす）。

D0059：ブランド「プラグ」を入れた。外部の読み込みは、Google Fonts の <link> 2本（計画ボードと同じ文字）と、アイコンを作る
createElementNS の SVG の名前空間の文字列 1 か所だけ許す（without_allowed が、この許した文字だけを取り除く）。それ以外は今までどおり禁止。
"""

from __future__ import annotations

import inspect
import json
import os
import re
from pathlib import Path

import pytest

import live_support as ls
from pipe_in.engine import live, live_page

ROOT = Path(__file__).resolve().parents[1]
MAX_PAGE_BYTES = 40 * 1024
BOARD = ROOT / ".claude" / "skills" / "pipe-plan" / "board.html"
DESIGN_README = ROOT / "docs" / "design" / "README.md"
SVG_NS = "http://www.w3.org/2000/svg"


@pytest.fixture(scope="module")
def html() -> str:
    page = live_page.build_page()
    assert isinstance(page, str) and page.strip(), "build_page() が空（ページをまだ作っていない）"
    return page


def parts(page: str) -> tuple[str, str, str]:
    """（style の中身, script の中身, それ以外のマークアップ）。"""
    style = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", page, re.S | re.I))
    script = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", page, re.S | re.I))
    markup = re.sub(r"<style[^>]*>.*?</style>|<script[^>]*>.*?</script>", "", page, flags=re.S | re.I)
    return style, script, markup


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


MOTION_MEDIA = r"@media\s*\(\s*prefers-reduced-motion\s*:\s*no-preference\s*\)"
DARK_MEDIA = r"@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)"


def block_after(css: str, opener: str) -> str:
    """css の中の opener（正規表現。例 MOTION_MEDIA）の { } の中身（入れ子を数える）。無ければ空。"""
    found = re.search(opener, css)
    if not found:
        return ""
    start = css.find("{", found.start())
    depth, i = 0, start
    while i < len(css):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[start + 1 : i]
        i += 1
    return css[start + 1 :]


# ---- AC-46 引数なし・決まった出力 --------------------------------------------------------------------


def test_d0027_ac46_build_page_takes_no_arguments():
    """D0027-AC-46: ページを作る関数は、引数に外の文字（記録・写し・パス）を取らない。"""
    assert list(inspect.signature(live_page.build_page).parameters) == []
    with pytest.raises(TypeError):
        live_page.build_page("x")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        live_page.build_page(name="x")  # type: ignore[call-arg]


def test_d0027_ac46_same_call_same_html(html):
    """D0027-AC-46: 同じ呼び出しは同じ HTML（呼ぶたび・環境が変わっても）。"""
    assert live_page.build_page() == live_page.build_page() == html


def test_d0027_ac46_html_does_not_depend_on_environment(monkeypatch, tmp_path, html):
    """D0027-AC-46: 環境変数・今のフォルダが変わっても、HTML は変わらない。"""
    monkeypatch.setenv("PIPE_IN_LIVE_MARK", "ENV-LEAK-MARK")
    monkeypatch.setenv("USERNAME", "ENV-LEAK-MARK")
    monkeypatch.setenv("USER", "ENV-LEAK-MARK")
    monkeypatch.chdir(tmp_path)
    assert live_page.build_page() == html
    assert "ENV-LEAK-MARK" not in html and str(tmp_path) not in html and str(ROOT) not in html and os.getcwd() not in html


# ---- AC-47 外部の読み込みが無い ------------------------------------------------------------------------

EXTERNAL = [
    "<script src=", "<script  src=", "<link", "@import", "url(", "http://", "https://", "//cdn", "<iframe", "<frame", "<img", "<embed", "<object",
    "<video", "<audio", "<base", "<form", "<meta http-equiv", "fetch(", "XMLHttpRequest", "WebSocket", "EventSource",
    "sendBeacon", "importScripts", "import(", "navigator.serviceWorker", "localStorage", "sessionStorage", "indexedDB", "document.cookie",
    "window.open", "location.href", "location.assign", "location.replace", "window.location", "top.location", "src=", "srcset", "ping=",
]


def board_font_links() -> list[str]:
    """計画ボード（.claude/skills/pipe-plan/board.html）の <head> にある Google Fonts の <link> 2本の文字（読むだけ）。"""
    head = BOARD.read_text(encoding="utf-8").split("<style>", 1)[0]
    links = re.findall(r"<link\b[^>]*>", head)
    assert len(links) == 2 and all("fonts.googleapis.com" in x for x in links), links
    return links


def without_allowed(page: str) -> str:
    """D0059：許した外部の文字だけを取り除いた HTML を返す。許すのは次の2つだけ（広げない）。
    ・Google Fonts の <link> 2本（board.html と完全に同じ文字。1本ずつ最初の1か所だけ取り除く）
    ・JS の SVG の名前空間の文字列 1 か所（createElementNS の第1引数に使う定数の定義、か第1引数そのもの。最初の1か所だけ）
    取り除いたあとに、今までの禁止語（<link・http://・url( など）を全部かける。3本目の <link> や2か所目の URL は残るので、禁止語に当たる。"""
    out = page
    for link in board_font_links():
        out = out.replace(link, "", 1)
    definition = re.search(r"""\b(?:var|let|const)\s+SVG_NS\s*=\s*(["'])%s\1""" % re.escape(SVG_NS), out)
    literal = re.search(r"""createElementNS\(\s*(["'])%s\1""" % re.escape(SVG_NS), out)
    found = definition or literal
    if found:
        out = out[: found.start()] + found.group(0).replace(SVG_NS, "", 1) + out[found.end() :]
    return out


@pytest.fixture(scope="module")
def stripped(html) -> str:
    return without_allowed(html)


@pytest.mark.parametrize("token", EXTERNAL, ids=repr)
def test_d0027_ac47_page_has_no_external_loading(stripped, token):
    """D0027-AC-47・D0059-AC-06: 許した文字（Google Fonts の link 2本と SVG の名前空間 1 か所）を除いて、HTML に外部の読み込み（script src・link・@import・url()・http(s)・iframe・img・fetch・XHR・WebSocket など）が無い。"""
    assert token.lower() not in stripped.lower()


def test_d0027_ac47_no_url_like_text_anywhere(stripped):
    """D0027-AC-47・D0059-AC-06: 許した文字を除いて、スキーム付きの URL（http: ftp: data: javascript: blob: file: ws:）が、文字としても入っていない。"""
    assert not re.search(r"\b(?:https?|ftp|wss?|data|javascript|blob|file|mailto):", stripped, re.I)


def test_d0027_ac47_exactly_one_script_and_one_style(html):
    """D0027-AC-47: <script> は1つ、<style> は1つ（設計の「1枚で完結」）。type=module や外部指定が無い。"""
    assert len(re.findall(r"<script\b", html, re.I)) == 1
    assert len(re.findall(r"</script", html, re.I)) == 1
    assert len(re.findall(r"<style\b", html, re.I)) == 1
    assert not re.search(r"<script[^>]*\b(?:src|type|async|defer|nomodule|integrity|crossorigin)\b", html, re.I)


def test_d0059_ac06_only_the_allowed_external_text(html):
    """D0059-AC-06: 外部の文字は、board.html と同じ Google Fonts の <link> 2本（<head> の中）と、SVG の名前空間 1 か所（createElementNS の第1引数）だけ。"""
    links = board_font_links()
    for link in links:
        assert html.count(link) == 1, f"board.html と同じ link がページに1本ずつ無い: {link}"
    assert len(re.findall(r"<link\b", html, re.I)) == 2
    head = html.split("</head>", 1)[0]
    assert all(link in head for link in links), "link は <head> の中に置く"
    urls = re.findall(r"https?://[^\s\"'<>)]+", html)
    fonts = [u for u in urls if u.startswith("https://fonts.googleapis.com")]
    others = [u for u in urls if not u.startswith("https://fonts.googleapis.com")]
    assert others == [SVG_NS], f"許したもの以外の URL: {others}"
    assert len(fonts) == 2
    script = parts(html)[1]
    assert script.count(SVG_NS) == 1 and html.count(SVG_NS) == 1
    calls = re.findall(r"createElementNS\(\s*([^,)]+),", script)
    assert calls, "createElementNS を呼んでいない（アイコンを作っていない）"
    assert all(first.strip() in ("SVG_NS", f'"{SVG_NS}"') for first in calls), calls
    if "SVG_NS" in calls:
        assert re.search(r"""\b(?:var|let|const)\s+SVG_NS\s*=\s*"%s"\s*;""" % re.escape(SVG_NS), script)


def test_d0059_ac06_the_allowance_is_exact_and_does_not_widen(html):
    """D0059-AC-06: 許可の取り除きは厳密：3本目の link や、2か所目の名前空間・別の URL は取り除かれず、禁止語に当たる。"""
    extra_link = html + '<link rel="stylesheet" href="https://evil.example/x.css">'
    assert "<link" in without_allowed(extra_link).lower() and "https://" in without_allowed(extra_link)
    twice = html + f"<!-- {SVG_NS} -->"
    assert "http://" in without_allowed(twice)
    other_ns = html + "<!-- http://www.w3.org/1999/xhtml -->"
    assert "http://" in without_allowed(other_ns)
    changed = html.replace("display=swap", "display=block", 1) if "display=swap" in html else html + "<link>"
    assert "<link" in without_allowed(changed).lower(), "board.html と違う link は許さない"


def test_d0027_ac47_script_text_cannot_close_itself(html):
    """D0027-AC-47: JS の文字列の中に </script や <!-- が出ない（HTML の読み取りを壊さない）。"""
    _style, script, _markup = parts(html)
    assert script.strip()
    assert "</" not in script and "<!--" not in script and "-->" not in script


# ---- AC-48 HTML を差し込まない ----------------------------------------------------------------------------

HTML_INSERTION = [
    "innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "document.writeln", "eval(", "new Function", "Function(", ".srcdoc", "srcdoc",
    "createContextualFragment", "DOMParser", "execScript", "setHTMLUnsafe", "parseHTMLUnsafe", ".animate(", "javascript:", "dangerouslySet", "template.innerHTML",
]


@pytest.mark.parametrize("token", HTML_INSERTION, ids=repr)
def test_d0027_ac48_script_has_no_html_insertion(html, token):
    """D0027-AC-48: スクリプトに innerHTML・outerHTML・insertAdjacentHTML・document.write・eval・new Function などが無い。"""
    assert token.lower() not in html.lower()


@pytest.mark.parametrize("pattern", [r"set(?:Timeout|Interval)\(\s*[\"'`]", r"\.on[a-z]+\s*=\s*[\"'`]", r"setAttribute\(\s*[\"']on", r"setAttribute\(\s*[\"'](?:src|href)",
                                     r"\.style\.cssText"], ids=repr)
def test_d0027_ac48_script_has_no_indirect_code_or_html_paths(html, pattern):
    """D0027-AC-48: 文字列を実行する・on 属性を足す・属性で URL や style を差し込む・prototype をいじる道が無い。"""
    _style, script, _markup = parts(html)
    assert script.strip()
    assert not re.search(pattern, script)


def test_d0027_ac48_script_uses_text_content(html):
    """D0027-AC-48: db の値は textContent か createTextNode で出す（どちらかを使っている）。"""
    _style, script, _markup = parts(html)
    assert "textContent" in script or "createTextNode" in script


def test_d0027_ac48_markup_has_no_inline_handlers_or_style_attributes(html):
    """D0027-AC-48: マークアップに on…= の属性・style= の属性が無い（動きは script、見た目は style に置く）。"""
    _style, _script, markup = parts(html)
    assert not re.search(r"\son[a-z]+\s*=", markup, re.I)
    assert not re.search(r"\sstyle\s*=", markup, re.I)


# ---- AC-49 外の文字が入らない -------------------------------------------------------------------------------


def test_d0027_ac49_page_does_not_change_with_hostile_records(tmp_path, html):
    """D0027-AC-49: 悪意のある文字を入れた記録から写しを作っても、ページの HTML は変わらず、記録の文字も入らない。"""
    hostile = "<script>alert('HOSTILE-MARK')</script>"
    work = tmp_path / "w"
    ls.write_state(work, ls.base_state(name=hostile, stages=[ls.stage_entry("a", hostile)], runs=[ls.run("a", seq=1, result=hostile)]))
    (work / "00_input.md").write_text(hostile, encoding="utf-8")
    snapshot = live.build_snapshot(live.read_state(work), None, now=ls.NOW, local_tz=ls.JST)
    assert snapshot, "写しが空（写しをまだ作っていない）"
    live.dumps(snapshot)
    assert live_page.build_page() == html
    assert "HOSTILE-MARK" not in html and "alert(" not in html


def test_d0027_ac49_page_has_no_embedded_snapshot(html):
    """D0027-AC-49: ページに写しの JSON（schema・generated_at の値や、stages の一覧）が埋まっていない。写しは db から読む。"""
    assert not re.search(r'"?generated_at"?\s*:\s*["\']\d{4}-', html)
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", html)
    assert "application/json" not in html.lower()


def test_d0027_ac49_page_has_no_local_information(html):
    """D0027-AC-49: ページに手元の事情（ユーザー名の入ったパス・メールアドレス）が無い。"""
    assert not re.search(r"[A-Za-z]:[\\/]+Users", html)
    assert not re.search(r"(?<![A-Za-z0-9_.-])/(?:Users|home)/[A-Za-z0-9_.-]", html)
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]", html)


# ---- AC-50 db を await で取る・読めない旨 ------------------------------------------------------------------


def test_d0027_ac50_script_awaits_db_and_has_unreadable_message(html):
    """D0027-AC-50: スクリプトが claude.use("db") を await で呼び、null のときの「この画面では読めません」がある。"""
    _style, script, _markup = parts(html)
    assert re.search(r"""await\s+claude\s*\.\s*use\(\s*["']db["']\s*\)""", script)
    assert "この画面では読めません" in html


def test_d0027_ac50_script_reads_the_current_doc_and_never_writes(html):
    """D0027-AC-50: db は runs/current を onSnapshot で読むだけ（set・update・delete・add を呼ばない）。"""
    _style, script, _markup = parts(html)
    assert re.search(r"""\.doc\(\s*["']runs/current["']\s*\)""", script)
    assert "onSnapshot" in script


def test_d0027_ac50_script_has_the_other_designed_messages(html):
    """D0027-AC-50: 「まだ記録がありません」と「この写しの版には対応していません」の文字がある（設計）。"""
    assert "まだ記録がありません" in html
    assert "この写しの版には対応していません" in html


# ---- AC-51 骨組み -----------------------------------------------------------------------------------------


def test_d0027_ac51_page_has_doctype_lang_viewport_title(html):
    """D0027-AC-51: <!doctype html>・lang="ja"・viewport の meta・空でない title を持つ。"""
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert re.search(r"<html[^>]*\blang=[\"']ja[\"']", html, re.I)
    assert re.search(r"<meta\s+charset=[\"']?utf-8[\"']?", html, re.I)
    assert re.search(r"""<meta\s+name=["']viewport["']\s+content=["'][^"']*width=device-width""", html, re.I)
    assert re.search(r"<title>\s*[^<\s][^<]*</title>", html)


def test_d0027_ac51_style_before_body_and_script_after_it(html):
    """D0027-AC-51: <style> は <body> より前、<script> は <body> の後ろ（骨組みができてから動く）。"""
    low = html.lower()
    assert low.index("<style") < low.index("<body") < low.index("<script")


def test_d0027_ac51_markup_is_a_skeleton_without_content_text(html):
    """D0027-AC-51: マークアップは骨組みだけ（見出しと入れ物とメッセージ）。ここには段や記録の中身にあたる文字が無い。"""
    _style, _script, markup = parts(html)
    body = re.search(r"<body[^>]*>(.*?)(?:</body>|$)", markup, re.S | re.I)
    assert body
    text = re.sub(r"<[^>]+>", " ", body.group(1))
    assert len(" ".join(text.split())) <= 400


def test_d0027_ac51_ids_are_unique(html):
    """D0027-AC-51: id が重ならない（getElementById が迷わない）。"""
    ids = re.findall(r"\sid=[\"']([^\"']+)[\"']", html)
    assert len(ids) == len(set(ids))


# ---- AC-52 色のトークン ------------------------------------------------------------------------------------

# D0059：デザイン「プラグ」の 11 の役（docs/design/README.md の色の表）と、計画ボードと同じ補助のトークン
TOKENS = ["--bg", "--panel", "--col", "--line", "--fg", "--muted", "--coral", "--teal", "--blue", "--bad", "--ok"]
SUPPORT_TOKENS = ["--coral-soft", "--coral-text", "--on-coral", "--teal-soft", "--teal-text", "--ok-soft", "--ok-text", "--bad-soft", "--bad-text", "--shadow"]
OLD_TOKEN_NAMES = ["--run", "--review", "--ng"]


def css_of(page: str) -> str:
    return strip_comments(parts(page)[0])


def declarations(block: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;}]+)", block)}


def root_block(css: str) -> str:
    m = re.search(r":root\s*\{([^}]*)\}", css)
    return m.group(1) if m else ""


def dark_media_block(css: str) -> str:
    return block_after(css, DARK_MEDIA)


def data_theme_block(css: str, theme: str) -> str:
    m = re.search(r"\[data-theme=[\"']%s[\"']\]\s*\{([^}]*)\}" % theme, css)
    return m.group(1) if m else ""


def theme_blocks(css: str) -> dict[str, dict[str, str]]:
    """4つのブロックの宣言：light（:root 既定）・dark_auto（prefers-color-scheme: dark の :root:not([data-theme="light"])）・dark（強制）・light_forced。"""
    media = dark_media_block(css)
    assert ':root:not([data-theme="light"])' in media.replace("'", '"'), "prefers-color-scheme: dark の中に :root:not([data-theme=\"light\"]) が無い"
    return {
        "light": declarations(root_block(css)),
        "dark_auto": declarations(media),
        "dark": declarations(data_theme_block(css, "dark")),
        "light_forced": declarations(data_theme_block(css, "light")),
    }


def design_color_table() -> dict[str, tuple[str, str]]:
    """docs/design/README.md の色の表：{--名前: (明るい, 暗い)}（読むだけ）。"""
    text = DESIGN_README.read_text(encoding="utf-8")
    rows = re.findall(r"\|\s*[^|]*\|\s*`(--[\w-]+)`\s*\|\s*`(#[0-9a-fA-F]{6})`\s*\|\s*`(#[0-9a-fA-F]{6})`\s*\|", text)
    return {name: (light.lower(), dark.lower()) for name, light, dark in rows}


def test_d0059_ac01_color_tokens_light_and_dark(html):
    """D0059-AC-01: 11 の役が #rrggbb で :root（明るい既定）に定義され、暗い値は prefers-color-scheme: dark と [data-theme="dark"] で同じ、[data-theme="light"] は既定と同じ。"""
    blocks = theme_blocks(css_of(html))
    for name, block in blocks.items():
        assert set(TOKENS) <= set(block), f"{name} に無いトークン: {sorted(set(TOKENS) - set(block))}"
        for token in TOKENS:
            assert re.fullmatch(r"#[0-9a-fA-F]{6}", block[token]), (name, token, block[token])
    assert {k: blocks["dark_auto"][k] for k in TOKENS} == {k: blocks["dark"][k] for k in TOKENS}, "自動のダークと強制のダークで色が違う"
    assert {k: blocks["light_forced"][k] for k in TOKENS} == {k: blocks["light"][k] for k in TOKENS}, "強制のライトと既定のライトで色が違う"
    assert blocks["dark"]["--bg"] != blocks["light"]["--bg"] and blocks["dark"]["--fg"] != blocks["light"]["--fg"]


def test_d0059_ac01_values_match_the_design_table(html):
    """D0059-AC-01: 11 の役の値が、docs/design/README.md の色の表（明るい・暗い）と一致する。"""
    table = design_color_table()
    assert set(TOKENS) <= set(table), f"色の表が読めない: {sorted(set(TOKENS) - set(table))}"
    blocks = theme_blocks(css_of(html))
    for token in TOKENS:
        light, dark = table[token]
        assert blocks["light"][token].lower() == light, (token, blocks["light"][token], light)
        assert blocks["light_forced"][token].lower() == light, (token, "light_forced")
        assert blocks["dark"][token].lower() == dark, (token, blocks["dark"][token], dark)
        assert blocks["dark_auto"][token].lower() == dark, (token, "dark_auto")


def board_blocks() -> dict[str, dict[str, str]]:
    """計画ボード（board.html）の明るい・暗い（強制）のトークン（読むだけ）。"""
    css = strip_comments(parts(BOARD.read_text(encoding="utf-8"))[0])
    return {"light": declarations(root_block(css)), "dark": declarations(data_theme_block(css, "dark"))}


def test_d0059_ac02_support_tokens_match_board(html):
    """D0059-AC-02: 補助のトークン（coral-soft・coral-text・on-coral・teal-soft・teal-text・ok-soft・ok-text・bad-soft・bad-text・shadow）が明暗の4ブロックで定義され、値が board.html と一致する。--col は board の --panel-2。"""
    board = board_blocks()
    blocks = theme_blocks(css_of(html))
    norm = lambda v: " ".join(v.split()).lower()  # noqa: E731
    for name, block in blocks.items():
        assert set(SUPPORT_TOKENS) <= set(block), f"{name} に無い補助のトークン: {sorted(set(SUPPORT_TOKENS) - set(block))}"
        ref = board["dark"] if name.startswith("dark") else board["light"]
        for token in SUPPORT_TOKENS:
            assert norm(block[token]) == norm(ref[token]), (name, token, block[token], ref[token])
        assert norm(block["--col"]) == norm(ref["--panel-2"]), (name, "--col は board の --panel-2")


COLOR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch|color)\(")
NAMED_COLORS = {
    "red", "blue", "green", "black", "white", "gray", "grey", "orange", "yellow", "purple", "pink", "brown", "cyan", "magenta", "silver", "gold", "navy",
    "teal", "lime", "maroon", "olive", "aqua", "fuchsia", "crimson", "coral", "salmon", "tomato", "indigo", "violet", "ivory", "beige", "khaki",
}


def test_d0027_ac52_no_colors_outside_tokens(html):
    """D0027-AC-52: 色の指定は、トークンの定義（--名前: 値）以外では直接書かない（16進・rgb()・hsl()・色の名前が無い）。"""
    css = css_of(html)
    without_tokens = re.sub(r"(--[\w-]+)\s*:\s*[^;}]*;?", "", css)
    seen = 0
    for m in re.finditer(r"(?:^|[;{}\s])([a-z-]+)\s*:\s*([^;{}]*)", without_tokens):
        value = re.sub(r"var\([^)]*\)", "", m.group(2))
        assert not COLOR_LITERAL.search(value), (m.group(1), m.group(2))
        assert not (set(re.findall(r"[a-z]+", value.lower())) & NAMED_COLORS), (m.group(1), m.group(2))
        seen += 1
    assert seen > 5, "CSS の宣言がほとんど無い（ページをまだ作っていない）"


def test_d0027_ac52_colors_are_used_through_tokens(html):
    """D0027-AC-52: 文字の色と背景は、トークンを var() で使う。"""
    css = css_of(html)
    assert re.search(r"(?:^|[;{}\s])color\s*:\s*var\(--", css)
    assert re.search(r"(?:^|[;{}\s])background(?:-color)?\s*:\s*var\(--", css)


def _hex(value: str) -> tuple[float, float, float]:
    v = value.strip().lstrip("#")
    if len(v) in (3, 4):
        v = "".join(c * 2 for c in v[:3])
    assert re.fullmatch(r"[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", v), f"色のトークンは 16 進（#rrggbb）で書く: {value!r}"
    return tuple(int(v[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _luminance(rgb: tuple[float, float, float]) -> float:
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(_hex(a)), _luminance(_hex(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def contrast_failures(tokens: dict[str, str]) -> list[str]:
    """D0059-AC-04 の組を測り、足りないものの一覧を返す（足りなければ空）。"""
    bad = []
    for fg in ("--fg", "--muted"):
        for bg in ("--bg", "--panel"):
            if contrast(tokens[fg], tokens[bg]) < 4.5:
                bad.append(f"{fg} on {bg}")
    for kind in ("coral", "teal", "ok", "bad"):
        if contrast(tokens[f"--{kind}-text"], tokens[f"--{kind}-soft"]) < 4.5:
            bad.append(f"--{kind}-text on --{kind}-soft")
        if contrast(tokens[f"--{kind}"], tokens["--bg"]) < 3.0:
            bad.append(f"--{kind} on --bg")
    if contrast(tokens["--on-coral"], tokens["--coral"]) < 4.5:
        bad.append("--on-coral on --coral")
    return bad


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_d0059_ac04_contrast(html, theme):
    """D0059-AC-04: 明暗それぞれで、fg・muted は bg と panel に 4.5 以上、状態の文字（coral/teal/ok/bad-text）は soft の地に 4.5 以上、
    アイコンと枠の色（coral・teal・ok・bad）は bg に 3 以上、on-coral は coral に 4.5 以上（色トークンは 16 進で書く）。"""
    blocks = theme_blocks(css_of(html))
    tokens = blocks["light"] if theme == "light" else blocks["dark"]
    needed = [*TOKENS, *SUPPORT_TOKENS]
    assert set(needed) <= set(tokens), f"{theme} に無いトークン: {sorted(set(needed) - set(tokens))}"
    assert contrast_failures(tokens) == []


@pytest.mark.parametrize("theme", [0, 1], ids=["light", "dark"])
def test_d0059_ac04_the_design_values_themselves_pass_the_contrast(theme):
    """D0059-AC-04: 今のままで通る（設計の値そのものが基準を満たすことの確認。docs/design/README.md の表と board.html の値で測る。足りなければ、値は変えずに親へ知らせる）。"""
    table = design_color_table()
    board = board_blocks()["light" if theme == 0 else "dark"]
    tokens = {name: table[name][theme] for name in TOKENS}
    tokens.update({name: board[name] for name in SUPPORT_TOKENS})
    assert contrast_failures(tokens) == []


def test_d0059_ac04_contrast_check_catches_a_failure():
    """D0059-AC-04: 測る組の一覧そのものが、足りない組を見つける（検査の自己検査）。"""
    table = design_color_table()
    board = board_blocks()["light"]
    tokens = {name: table[name][0] for name in TOKENS}
    tokens.update({name: board[name] for name in SUPPORT_TOKENS})
    tokens["--muted"] = "#bbbbbb"
    assert "--muted on --bg" in contrast_failures(tokens)


def test_d0059_ac03_rgba_only_in_shadow_definition(html):
    """D0059-AC-03: --shadow が明暗の4ブロックにあり、rgba() は --shadow の定義の中だけ（ほかの所に rgb( rgba( が無い）。"""
    css = css_of(html)
    blocks = theme_blocks(css)
    for name, block in blocks.items():
        assert "--shadow" in block and "rgba(" in block["--shadow"], name
    rest = re.sub(r"--shadow\s*:\s*[^;}]*;?", "", css)
    assert not re.search(r"\brgba?\(", rest)


def test_d0059_ac03_used_vars_are_defined(html):
    """D0059-AC-03: 使う var(--…) は、4ブロックのすべてで定義したトークンだけ。新しい役（panel・coral・teal・書体・角・影）が実際に使われている。"""
    css = css_of(html)
    used = set(re.findall(r"var\(\s*(--[\w-]+)", css))
    blocks = theme_blocks(css)
    defined = set.intersection(*(set(b) for b in blocks.values())) | set(declarations(root_block(css)))
    assert used <= defined, sorted(used - defined)
    assert {"--panel", "--coral", "--teal", "--f-body", "--f-mono", "--shadow", "--r-card"} <= used, sorted({"--panel", "--coral", "--teal", "--f-body", "--f-mono", "--shadow", "--r-card"} - used)


def test_d0059_ac03_old_token_names_are_gone(html):
    """D0059-AC-03: 古い名前（--run・--review・--ng）が CSS にも JS にも残っていない。"""
    searched = css_of(html) + "\n" + parts(html)[1]
    for name in OLD_TOKEN_NAMES:
        assert not re.search(re.escape(name) + r"(?![\w-])", searched), name


def test_d0027_ac52_contrast_function_is_correct():
    """D0027-AC-52: コントラストを測る補助が正しい（白と黒は 21、同じ色は 1）。"""
    assert round(contrast("#000000", "#ffffff"), 2) == 21.0
    assert contrast("#123456", "#123456") == pytest.approx(1.0)
    assert contrast("#777", "#fff") < 4.5 < contrast("#595959", "#fff")


# ---- D0059-AC-05 書体 ---------------------------------------------------------------------------------------


def test_d0059_ac05_two_font_links_in_head(html):
    """D0059-AC-05: <head> に fonts.googleapis.com への preconnect と stylesheet の <link> がちょうど2本あり、Zen Kaku Gothic New と JetBrains Mono を指す。
    <title> の後・<style> の前に置く（board.html と同じ文字）。"""
    head = html.split("</head>", 1)[0]
    links = re.findall(r"<link\b[^>]*>", head)
    assert len(links) == 2 and len(re.findall(r"<link\b", html, re.I)) == 2, links
    pre = [x for x in links if 'rel="preconnect"' in x]
    sheet = [x for x in links if 'rel="stylesheet"' in x]
    assert len(pre) == 1 and 'href="https://fonts.googleapis.com"' in pre[0]
    assert len(sheet) == 1 and 'href="https://fonts.googleapis.com/css2?' in sheet[0]
    assert "Zen+Kaku+Gothic+New" in sheet[0] and "JetBrains+Mono" in sheet[0]
    assert head.index("</title>") < head.index(links[0]) < head.index(links[1]) < html.index("<style")


def test_d0059_ac05_font_stacks_have_fallbacks(html):
    """D0059-AC-05: --f-body と --f-mono に代わりの書体が並ぶ（読み込めなくても読める）。"""
    tokens = declarations(root_block(css_of(html)))
    body, mono = tokens.get("--f-body", ""), tokens.get("--f-mono", "")
    for name in ("Zen Kaku Gothic New", "Hiragino Sans", "Yu Gothic UI", "Noto Sans JP", "system-ui"):
        assert name in body, (name, body)
    for name in ("JetBrains Mono", "ui-monospace", "Menlo"):
        assert name in mono, (name, mono)
    assert body.rstrip().endswith("sans-serif") and mono.rstrip().endswith("monospace")


def test_d0059_ac05_body_and_numbers_use_the_font_tokens(html):
    """D0059-AC-05: 本文は --f-body、経過時間・費用・ターン・時刻（.elapsed .usage .attempt .updated .total）は --f-mono。"""
    css = css_of(html)
    body = decls_for(css, "body")
    assert "var(--f-body)" in body.get("font", "") + body.get("font-family", ""), body
    for selector in (".elapsed", ".usage", ".attempt", ".updated", ".total"):
        decl = rule(css, selector)
        assert "var(--f-mono)" in decl.get("font", "") + decl.get("font-family", ""), (selector, decl)


# ---- D0059-AC-10 進み具合の帯（CSS の形） ----------------------------------------------------------------------


def seg_rule(css: str, state: str) -> dict[str, str]:
    """セレクタの最後が .seg-<状態> の規則（.seg-done・.seg.seg-done など。疑似要素つきは含めない）の宣言を重ねて返す。"""
    merged: dict[str, str] = {}
    for selectors, decls in css_rules(css):
        if any(re.search(r"(?:^|[\s>.])seg-%s$" % state, s) or re.search(r"\.seg-%s$" % state, s) for s in selectors):
            merged.update(decls)
    return merged


def test_d0059_ac10_band_patterns_differ(html):
    """D0059-AC-10: 帯の区切りの模様が状態ごとに違う：完了＝塗り（--ok）、確認待ち＝斜めの縞（repeating-linear-gradient・coral）、作業中＝点（radial-gradient・teal）、まだ＝無地（--col）。
    失敗は --bad の塗り、差し戻しは coral の枠、不明は点線の枠。形は互いに違う。"""
    css = css_of(html)
    shapes = {}
    for state in ("done", "review", "running", "waiting", "failed", "revised", "unknown"):
        decl = seg_rule(css, state)
        shape = frozenset((k, v) for k, v in decl.items() if k.startswith(("background", "border", "outline")))
        assert shape, f".seg-{state} に模様（background / border）が無い: {decl}"
        shapes[state] = shape
    values = lambda state: " ".join(v for _, v in shapes[state])  # noqa: E731
    assert "var(--ok)" in values("done") and "gradient" not in values("done")
    assert "repeating-linear-gradient" in values("review") and "var(--coral)" in values("review")
    assert "radial-gradient" in values("running") and "var(--teal)" in values("running")
    assert "var(--col)" in values("waiting") and "gradient" not in values("waiting")
    assert "var(--bad)" in values("failed")
    assert "var(--coral)" in values("revised") and "dashed" not in values("revised")
    assert "dashed" in values("unknown") or "dotted" in values("unknown")
    assert len(set(shapes.values())) == 7, "模様が同じ状態がある"


def test_d0059_ac10_band_layout_has_gaps_and_no_inline_widths(html):
    """D0059-AC-10: 帯は横に並び（flex・gap）、区切りは同じ幅で分け合い（flex: 1 1 0）、幅は style 属性や JS の style に頼らない。"""
    css = css_of(html)
    band, seg = rule(css, ".band"), rule(css, ".seg")
    assert band.get("display") == "flex" and "gap" in band and band.get("height") == "8px", band
    assert seg.get("flex", "").startswith("1 1 0"), seg
    script = parts(html)[1]
    assert ".style." not in script and 'setAttribute("style"' not in script.replace("'", '"')
    band_tag = re.search(r'<div\b[^>]*\bclass="band"[^>]*>', html)
    assert band_tag, "骨組みに <div class=\"band\"> が無い"
    assert 'aria-hidden="true"' in band_tag.group(0), "帯は aria-hidden（下の文字の数が同じ内容を伝える）"


# ---- AC-53 動き -------------------------------------------------------------------------------------------


def test_d0059_ac17_spin_and_pulse_inside_no_preference(html):
    """D0059-AC-17: 作業中の印の回転（@keyframes spin を .s-running .mark svg にかける）と脈打ち（.s-running .mark）は、どちらも no-preference の中だけにある。"""
    css = css_of(html)
    inside = block_after(css, MOTION_MEDIA)
    assert re.search(r"@keyframes\s+spin\b", inside), "spin の @keyframes が no-preference の中に無い"
    assert re.search(r"\.s-running\s+\.mark\s+svg\s*\{[^}]*animation[^}]*spin", inside), "回転が .s-running .mark svg にかかっていない"
    assert re.search(r"\.s-running\s+\.mark\s*\{[^}]*animation[^}]*pulse", inside)
    outside = css.replace(inside, "")
    assert "spin" not in outside and "animation" not in outside


def test_d0059_ac18_radius_values(html):
    """D0059-AC-18: 角の丸みは札 6・カード 10・面 14・チップ 999（--r-tag・--r-card・--r-panel・--r-chip）。.stage はカード、.chip はチップを使う。"""
    css = css_of(html)
    root = declarations(root_block(css))
    assert [root.get(k) for k in ("--r-tag", "--r-card", "--r-panel", "--r-chip")] == ["6px", "10px", "14px", "999px"], root
    assert rule(css, ".stage").get("border-radius") == "var(--r-card)"
    assert rule(css, ".chip").get("border-radius") == "var(--r-chip)"



def test_d0027_ac53_motion_only_in_no_preference_media(html):
    """D0027-AC-53: animation・transition の指定は、すべて @media (prefers-reduced-motion: no-preference) の中にある。"""
    css = css_of(html)
    inside = block_after(css, MOTION_MEDIA)
    assert inside, "no-preference の @media が無い"
    outside = css.replace(inside, "")
    for word in ("animation", "transition", "@keyframes", "scroll-behavior", "will-change"):
        assert word not in outside, word
    assert "animation" in inside, "脈打ち（animation）が no-preference の中に無い"


def test_d0027_ac53_keyframes_are_inside_the_media_too(html):
    """D0027-AC-53: @keyframes を使うなら、それも no-preference の中（reduce のときに一切動かない）。"""
    css = css_of(html)
    if "@keyframes" in css:
        assert "@keyframes" in block_after(css, MOTION_MEDIA)


def test_d0027_ac53_script_starts_no_motion(html):
    """D0027-AC-53: JS は動きを起こさない（requestAnimationFrame・animate・scrollIntoView を使わない）。"""
    _style, script, _markup = parts(html)
    assert script.strip()
    for word in ("requestAnimationFrame", ".animate(", "scrollIntoView"):
        assert word not in script, word


# ---- AC-54 幅 ---------------------------------------------------------------------------------------------


def test_d0027_ac54_no_fixed_wide_width_and_has_overflow_wrap(html):
    """D0027-AC-54: 360px を超える固定の幅が無い。overflow-x を隠して逃げず、長い名前の折り返し（overflow-wrap）がある。"""
    css = css_of(html)
    for m in re.finditer(r"(?:^|[;{\s])(width|min-width)\s*:\s*([^;}]*)", css):
        for px in re.findall(r"(\d+(?:\.\d+)?)\s*px", m.group(2)):
            assert float(px) <= 360, (m.group(1), m.group(2))
        assert "vw" not in m.group(2) or float(re.findall(r"(\d+(?:\.\d+)?)\s*vw", m.group(2))[0]) <= 100
    assert not re.search(r"overflow-x\s*:\s*(?:hidden|clip)", css)
    assert re.search(r"overflow-wrap\s*:\s*(?:anywhere|break-word)", css) or re.search(r"word-break\s*:\s*(?:break-all|break-word)", css)


def test_d0027_ac54_designed_width_rules(html):
    """D0027-AC-54: 設計どおり、max-width: 100%・min-width: 0・overflow-wrap: anywhere を使う。"""
    css = css_of(html)
    assert re.search(r"max-width\s*:\s*100%", css)
    assert re.search(r"min-width\s*:\s*0\b", css)
    assert re.search(r"overflow-wrap\s*:\s*anywhere", css)


def test_d0027_ac54_no_wide_inline_sizes_in_the_markup(html):
    """D0027-AC-54: マークアップに width/height の属性（固定の大きさ）が無い。"""
    _style, _script, markup = parts(html)
    assert not re.search(r"\s(?:width|height)\s*=", markup, re.I)


def test_d0027_ac54_long_words_wrap_everywhere_text_is_shown(html):
    """D0027-AC-54: 文字を出す入れ物のどれでも折り返せる指定が body 側（全体）にかかっている。"""
    css = css_of(html)
    m = re.search(r"(?:^|[}\s])(?:html|body|\*|:root)[^{]*\{[^}]*overflow-wrap\s*:\s*anywhere", css)
    assert m, "html・body・* などの全体に overflow-wrap: anywhere がかかっていない"


# ---- AC-55 大きさ・状態の記号 -------------------------------------------------------------------------------


def test_d0027_ac55_page_size_under_the_limit(html):
    """D0027-AC-55: ページの HTML は 40 KB 以下で、空ではない。"""
    size = len(html.encode("utf-8"))
    assert 2_000 < size <= MAX_PAGE_BYTES, size


def test_d0027_ac55_page_is_valid_utf8_text_without_control_characters(html):
    """D0027-AC-55: 制御文字・孤立したサロゲートを含まない（そのまま UTF-8 で書ける）。"""
    html.encode("utf-8")
    assert not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", html)


@pytest.mark.parametrize("glyph", list("✓✕↩？○●◐"))
def test_d0059_ac08_script_has_no_glyph_marks(html, glyph):
    """D0059-AC-08: 状態の印は文字の字形でなくアイコン（SVG）で描くので、JS に ✓ ✕ ↩ ？ ○ ● ◐ の字形が無い（D0027-AC-55 の字形の検査を置き換え）。"""
    assert glyph not in parts(html)[1]


ICON_STATUSES = ["done", "running", "review", "waiting", "failed", "revised", "unknown"]


def test_d0059_ac08_icon_shapes_are_constants(html):
    """D0059-AC-08: アイコンの形（d の文字列）は ICONS という定数に、7つの状態ぶん、1本ずつの文字列で書かれ、組み立てる式（+ や テンプレート）が無い。
    setAttribute("d", …) の値は ICONS から取るだけで、外から来た文字は入らない。"""
    script = parts(html)[1]
    block = re.search(r"\b(?:var|let|const)\s+ICONS\s*=\s*\{(.*?)\}\s*;", script, re.S)
    assert block, "ICONS（状態 → d の文字列）の定数が無い"
    entries = re.findall(r"""["']?([A-Za-z_]\w*)["']?\s*:\s*"([^"\\]*)\"""", block.group(1))
    assert sorted(k for k, _ in entries) == sorted(ICON_STATUSES), entries
    assert all(re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz0-9 ,.\-]+", d) for _, d in entries)
    rest = re.sub(r"""["']?[A-Za-z_]\w*["']?\s*:\s*"[^"\\]*\"""", "", block.group(1))
    assert not re.search(r"[^\s,]", rest), f"ICONS に文字列1本ずつ以外が混ざっている: {rest!r}"
    sets = re.findall(r"""setAttribute\(\s*["']d["']\s*,\s*([^;]*?)\)\s*;""", script)
    assert len(sets) == 1, sets
    assert re.fullmatch(r"ICONS\[[\w.\[\]]+\]", sets[0].strip()), sets[0]


def test_d0059_ac08_designed_new_functions_exist_at_top_level(html):
    """D0059-AC-08: 設計の新しい関数（makeIcon・pickHead・totalText・updatedText・countText・buildBand）がトップレベルの関数宣言として JS にある（台が名前で呼ぶ）。"""
    script = parts(html)[1]
    for name in ("makeIcon", "pickHead", "totalText", "updatedText", "countText", "buildBand"):
        assert re.search(r"^\s*(?:async\s+)?function\s+%s\s*\(" % name, script, re.M), name


def test_d0059_ac08_icons_are_made_by_create_element_ns_and_never_by_inner_html(html):
    """D0059-AC-08: アイコンは createElementNS で作り（innerHTML などは使わない）、属性は setAttribute で付ける（fill none・stroke currentColor・aria-hidden）。"""
    script = parts(html)[1]
    body = function_body(script, "makeIcon")
    assert body, "makeIcon が無い"
    assert "createElementNS" in body and "innerHTML" not in body
    for token in ("viewBox", "currentColor", "stroke-width", "stroke-linecap", "stroke-linejoin", "aria-hidden", "none"):
        assert token in body, token


def test_d0027_ac55_designed_function_names_exist_at_top_level(html):
    """D0027-AC-55: 設計の関数名がトップレベルの関数宣言として JS にある（台が名前で呼ぶ）。"""
    _style, script, _markup = parts(html)
    for name in ("parseTime", "elapsedSec", "fmtElapsed", "checkSnapshot", "render", "tick", "syncTimer", "main"):
        assert re.search(r"^\s*(?:async\s+)?function\s+%s\s*\(" % name, script, re.M), name


# ---- AC-86 状態の印の幅と形（書体の字形に頼らない） ---------------------------------------------------------


def css_rules(css: str) -> list[tuple[list[str], dict[str, str]]]:
    """内側の規則を（セレクタの一覧, {プロパティ: 値}）にして順に返す。@media・@keyframes の外側の枠は含めない。"""
    rules = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        head = " ".join(m.group(1).split())
        if head.startswith("@") or re.fullmatch(r"[\d.%\s,]+|from|to", head):
            continue
        selectors = [" ".join(s.split()) for s in head.split(",") if s.strip()]
        decls = {}
        for item in m.group(2).split(";"):
            if ":" in item:
                key, value = item.split(":", 1)
                decls[key.strip().lower()] = " ".join(value.split())
        rules.append((selectors, decls))
    return rules


def decls_for(css: str, base: str) -> dict[str, str]:
    """セレクタが base そのもの（疑似要素・疑似クラスがついたものを含む）の規則の宣言を、順に重ねて返す。"""
    merged: dict[str, str] = {}
    for selectors, decls in css_rules(css):
        if any(re.fullmatch(re.escape(base) + r"(?::{1,2}[\w-]+(?:\([^)]*\))?)*", s) for s in selectors):
            merged.update(decls)
    return merged


FIXED_LENGTH = re.compile(r"(\d+(?:\.\d+)?)(px|rem|em|ch)")
SHAPE_PROPS = ("border", "background", "box-shadow", "clip-path", "mask", "outline")
CSS_DRAWN_STATES = ["waiting", "running", "review"]


def length_of(value: str | None) -> float | None:
    m = FIXED_LENGTH.fullmatch(value or "")
    return float(m.group(1)) if m else None


def test_d0027_ac86_mark_has_a_fixed_width_and_height(html):
    """D0027-AC-86・D0059-AC-09: .mark は固定の幅と高さを持ち（どの状態でも印の列の幅が同じ）、360px を超えない。"""
    base = decls_for(css_of(html), ".mark")
    for prop in ("width", "height"):
        size = length_of(base.get(prop))
        assert size is not None and 0 < size, f".mark の {prop} が固定の長さでない: {base.get(prop)!r}"
    assert length_of(base["width"]) <= 360 and length_of(base["height"]) <= 360
    assert not base.get("min-width") or length_of(base["min-width"]) is not None


def test_d0027_ac86_mark_is_centered(html):
    """D0027-AC-86・D0059-AC-09: 印は枠の中で中央に寄る（text-align か flex/grid の中央寄せ）。"""
    base = decls_for(css_of(html), ".mark")
    centered = (
        base.get("text-align") == "center"
        or base.get("justify-content") == "center"
        or base.get("place-items") in ("center", "center center")
        or base.get("place-content") in ("center", "center center")
    )
    assert centered, base


def test_d0027_ac86_mark_does_not_shrink(html):
    """D0027-AC-86・D0059-AC-09: 印の列は縮まない（flex の中で幅がつぶれて、表示名の位置がずれない）。"""
    base = decls_for(css_of(html), ".mark")
    assert base.get("flex-shrink") == "0" or base.get("flex", "").split()[:2] == ["0", "0"], f".mark が縮む: {base}"


@pytest.mark.parametrize("status", ["waiting", "running", "review", "done", "failed", "revised", "unknown"])
def test_d0027_ac86_states_do_not_change_the_mark_size(html, status):
    """D0027-AC-86・D0059-AC-09: 状態ごとの規則が、印の幅・高さを変えない（変えるなら基本と同じ値）。"""
    css = css_of(html)
    base = decls_for(css, ".mark")
    state = decls_for(css, f".s-{status} .mark")
    for prop in ("width", "min-width", "max-width", "height", "min-height", "max-height", "padding", "margin", "font-size", "flex", "flex-basis"):
        if prop in state:
            assert state[prop] == base.get(prop), (status, prop, state[prop], base.get(prop))


MARK_COLORS = {
    "done": ("--ok-text", "--ok-soft"),
    "running": ("--teal-text", "--teal-soft"),
    "review": ("--coral-text", "--coral-soft"),
    "revised": ("--coral-text", "--coral-soft"),
    "failed": ("--bad-text", "--bad-soft"),
}


@pytest.mark.parametrize("status", [*MARK_COLORS, "waiting", "unknown"])
def test_d0059_ac03_mark_colors_use_the_state_tokens(html, status):
    """D0059-AC-03・FR-04: 印の色と地は状態のトークンで書く（完了＝ok-text／ok-soft、作業中＝teal、確認待ち・差し戻し＝coral、失敗＝bad、まだ・不明＝muted）。16 進などの直書きをしない。
    D0027-AC-86 の「CSS の形で描く」3本（形・形の違い・形の色）を、アイコンで描く形（D0059-AC-08）に置き換えた分。"""
    css = css_of(html)
    state = decls_for(css, f".s-{status} .mark")
    for prop, value in state.items():
        assert not COLOR_LITERAL.search(value), (status, prop, value)
    if status in MARK_COLORS:
        text, soft = MARK_COLORS[status]
        assert state.get("color") == f"var({text})", (status, state)
        assert state.get("background") == f"var({soft})", (status, state)
    else:  # まだ・不明は控えめな色（基本の .mark の色でも、状態の規則でもよい）
        assert {**decls_for(css, ".mark"), **state}.get("color") == "var(--muted)", (status, state)


def test_d0059_ac09_icon_inside_the_mark_has_a_fixed_size(html):
    """D0059-AC-09: 印の中のアイコン（.mark svg）は 1rem の固定の大きさ（印は 1.75rem の円）。状態の規則はアイコンの大きさを変えない。"""
    css = css_of(html)
    svg = decls_for(css, ".mark svg")
    assert length_of(svg.get("width")) == 1 and length_of(svg.get("height")) == 1, svg
    base = decls_for(css, ".mark")
    assert length_of(base.get("width")) == 1.75 and length_of(base.get("height")) == 1.75, base
    assert base.get("border-radius") == "var(--r-chip)", "印は円（チップの角）"


def test_d0027_ac86_pulse_stays_on_the_running_mark(html):
    """D0027-AC-86: 動いている印の脈打ち（AC-53）は、形になっても .s-running .mark にかかる（no-preference の中だけ）。D0059-AC-17 も。"""
    inside = block_after(css_of(html), MOTION_MEDIA)
    assert re.search(r"\.s-running\s+\.mark(?:::?[\w-]+)?\s*\{[^}]*animation", inside)


# ---- D0044：答えのボタン（コメントの機能で、確認待ちの行から承認・差し戻し・中止を送る） --------------------------------------
#
# ページの動きは tests/test_live_page_comments.py（Node の台）。ここは HTML の文字・CSS の検査。

NEW_FIXED_STRINGS = [
    "確認待ちの答え",
    "直してほしい点（差し戻すときだけ）",
    "直してほしい点を書いて差し戻す",
    "実行する",
    "この段を承認しますか",
    "この直してほしい点で差し戻しますか",
    "この実行を中止しますか",
    "送っています…",
    "送りました（会話の返事を待っています）",
    "直してほしい点を書いてください",
    "1000 文字以内にしてください",
    "使えない文字（制御文字・見えない文字）が入っています",
    "この画面からは答えを送れません（アーティファクトの編集者だけが送れます）。会話で答えてください。",
    "答えを受け取れる Claude の会話が今ありません。会話で答えてください。",
    "この画面では答えを送る機能が使えません。会話で答えてください。",
    "この画面からは答えを送れません。会話で答えてください。",
    "この画面からは送れません（許可されていません）。会話で答えてください。",
    "同意が確認できなかったため、送られていません。もう一度押すか、会話で答えてください。",
    "続けて送りすぎです。少し待ってからやり直すか、会話で答えてください。",
    "送れませんでした。もう一度押すか、会話で答えてください。",
    "場所を取れませんでした。会話で答えてください。",
]
NEW_CLASSES = ["review", "rv-input", "rv-msg", "rv-btn", "rv-approve", "rv-revise", "rv-quit", "rv-go", "rv-back"]
NEW_FUNCTIONS = ["checkReview", "validateFeedback", "buildAnswerText", "setReview", "ensureComments", "startCheck", "buildPanel", "attachPanel", "syncPanel", "onAction", "onGo", "onBack"]


def function_body(script: str, name: str) -> str:
    """トップレベルの関数 name の { } の中身（入れ子を数える。文字列の中の { } は数えない簡易版）。無ければ空。"""
    found = re.search(r"^\s*(?:async\s+)?function\s+%s\s*\([^)]*\)\s*\{" % re.escape(name), script, re.M)
    if not found:
        return ""
    depth, i = 0, found.end() - 1
    quote = None
    while i < len(script):
        ch = script[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return script[found.end() : i]
        i += 1
    return script[found.end() :]


def test_d0044_ac36_script_has_no_native_dialogs(html):
    """D0044-AC-36: ページのスクリプトに window.confirm・alert(・prompt( が無い（アーティファクトの枠の中で使えるか確かめられていないため。確かめはページの中の2段で行う）。"""
    _style, script, _markup = parts(html)
    assert script.strip()
    assert not re.search(r"\b(?:window\.)?(?:confirm|alert|prompt)\s*\(", script)
    assert not re.search(r"\b(?:window\.)?(?:confirm|alert|prompt)\s*\(", html)


def test_d0044_ac36_dialog_check_finds_the_forbidden_calls():
    """D0044-AC-36: 禁止語の検査そのものが、window.confirm( などの呼び出しを見つけ、関数名の一部（confirmCheck の形）は見つけない。"""
    pattern = r"\b(?:window\.)?(?:confirm|alert|prompt)\s*\("
    for bad in ("window.confirm('x')", "confirm ('x')", "if (alert(1))", "x = prompt(", "window.alert("):
        assert re.search(pattern, bad), bad
    for ok in ("enterCheck()", "leaveCheck()", "confirmed = true", "var confirmText", "promptly(", "alerts.push("):
        assert not re.search(pattern, ok), ok


def test_d0044_ac41_new_words_use_text_content_only(html):
    """D0044-AC-41: 増えた分（ボタン・文・入力欄）も textContent だけで出す。固定の文の定義の行に HTML の形（<）が無く、文字を差し込む道（既存の禁止語）が増えていない。"""
    _style, script, _markup = parts(html)
    assert "textContent" in script
    for text in NEW_FIXED_STRINGS:
        lines = [ln for ln in script.splitlines() if text in ln]
        assert lines, f"固定の文が JS に無い: {text}"
        assert all("<" not in ln for ln in lines), (text, lines)
    for token in HTML_INSERTION:
        assert token.lower() not in html.lower(), token
    assert not re.search(r"\.(?:value|innerText|nodeValue|data)\s*=\s*[^=]*\bmessage\b", script), "reject の message を画面に出す形"


def test_d0044_ac41_input_value_is_never_written_into_the_screen_text(html):
    """D0044-AC-41: 入力欄の文（.value）は、送る文を作る関数と検査にだけ使い、textContent や文の欄に入れない。"""
    _style, script, _markup = parts(html)
    assert not re.search(r"textContent\s*=\s*[^;\n]*\.value\b", script), "入力欄の中身を画面に出している"
    assert not re.search(r"createTextNode\([^)]*\.value", script)


def test_d0044_ac43_page_has_the_comment_calls(html):
    """D0044-AC-43: HTML に claude.use("comments")（await）と sendToClaude・canSendToClaude・anchorFor の呼び出しがある。"""
    _style, script, _markup = parts(html)
    assert re.search(r"""await\s+claude\s*\.\s*use\(\s*["']comments["']\s*\)""", script)
    assert re.search(r"""await\s+claude\s*\.\s*use\(\s*["']db["']\s*\)""", script), "db の取り方は今のまま"
    assert re.search(r"\.canSendToClaude\(\s*\)", script)
    assert re.search(r"\.anchorFor\(", script)
    assert re.search(r"\.sendToClaude\(\s*\{[^}]*\banchor\b[^}]*\btext\b[^}]*\}\s*\)", script, re.S)


def test_d0044_ac43_comments_are_requested_in_one_place_only(html):
    """D0044-AC-43: claude.use("comments") を呼ぶ所は1つ（確認待ちが最初に現れたときに1回だけ取る。取る場所が散らばらない）。"""
    _style, script, _markup = parts(html)
    assert len(re.findall(r"""claude\s*\.\s*use\(\s*["']comments["']""", script)) == 1
    assert len(re.findall(r"""claude\s*\.\s*use\(""", script)) == 2
    body = function_body(script, "ensureComments")
    assert 'use("comments")' in body.replace("'", '"')


def test_d0044_ac43_send_is_called_without_await_in_the_run_handler(html):
    """D0044-AC-43: 実行するボタンの関数（onGo）は async でなく、中に await が無く、sendToClaude を呼ぶ（押した操作の中で呼ぶため。FR-19）。"""
    _style, script, _markup = parts(html)
    assert re.search(r"^\s*function\s+onGo\s*\(", script, re.M) and not re.search(r"async\s+function\s+onGo\b", script)
    body = function_body(script, "onGo")
    assert body and "sendToClaude" in body
    assert "await" not in body
    assert not re.search(r"\.then\(", body.split("sendToClaude", 1)[0]), "sendToClaude の前に非同期を挟んでいる"


def test_d0044_ac43_anchor_is_taken_at_the_first_click_and_passed_as_is(html):
    """D0044-AC-43: anchor は確かめに入る最初の操作（onAction）で anchorFor を await して取り、中身を読まず・作らず・JSON にせず・保存しない。"""
    _style, script, _markup = parts(html)
    body = function_body(script, "onAction")
    assert re.search(r"await\s+[\w.]+\.anchorFor\(", body), "onAction で anchorFor を await していない"
    assert re.search(r"^\s*async\s+function\s+onAction\b", script, re.M)
    assert not re.search(r"anchor\s*\.\s*(?:path|x|y|token)\b", script)
    assert not re.search(r"anchor\s*\[", script)
    assert "JSON." not in script and "Object.assign" not in script
    assert not re.search(r"anchor\s*=\s*\{", script), "anchor を自分で作っている"


@pytest.mark.parametrize("name", NEW_FUNCTIONS)
def test_d0044_ac43_designed_function_names_exist_at_top_level(html, name):
    """D0044-AC-43: 設計の関数名（checkReview・validateFeedback・buildAnswerText・setReview・ensureComments・startCheck・buildPanel・attachPanel・syncPanel・onAction・onGo・onBack）がトップレベルの関数宣言として JS にある（台が名前で呼ぶ）。"""
    _style, script, _markup = parts(html)
    assert re.search(r"^\s*(?:async\s+)?function\s+%s\s*\(" % name, script, re.M), name


def test_d0044_ac43_old_function_names_are_kept(html):
    """D0044-AC-43: 既存の関数（parseTime・elapsedSec・fmtElapsed・checkSnapshot・render・tick・syncTimer・main）の名前はそのまま残る。"""
    _style, script, _markup = parts(html)
    for name in ("parseTime", "elapsedSec", "fmtElapsed", "checkSnapshot", "render", "tick", "syncTimer", "main"):
        assert re.search(r"^\s*(?:async\s+)?function\s+%s\s*\(" % name, script, re.M), name


def test_d0044_ac43_names_avoid_words_the_forbidden_word_checks_would_match(html, stripped):
    """D0044-AC-43・D0059-AC-06: 関数名に confirm(・alert(・prompt( を含めず、キーの名前に data・file・blob を使わない（data: の形が URL と見なされるため）。
    許した SVG の名前空間の文字（http:）は取り除いてから調べる。"""
    _style, script, _markup = parts(stripped)
    assert not re.search(r"(?i)(?:confirm|alert|prompt)\s*\(", script)
    assert not re.search(r"\b(?:data|file|blob|javascript|mailto|ftp|https?|wss?)\s*:", script)


@pytest.mark.parametrize("token", NEW_CLASSES)
def test_d0044_ac43_designed_class_names_are_in_the_script(html, token):
    """D0044-AC-43: 設計のクラス名（div.review・textarea.rv-input・p.rv-msg・button.rv-btn と rv-approve・rv-revise・rv-quit・rv-go・rv-back）が JS で付けられている（台が選ぶ名前）。パネルは確認待ちが現れたとき JS が作る（静的な HTML には置かない）。"""
    _style, script, markup = parts(html)
    if token == "review":
        assert re.search(r"""(?:\bel\(\s*["']div["']\s*,\s*["'](?:[\w-]+\s+)*review["']|className\s*=\s*["'](?:[\w-]+\s+)*review["']|classList\.add\(\s*["']review["'])""", script)
    else:
        assert token in script
    assert not re.search(r"""class\s*=\s*["'][^"']*\b%s\b""" % re.escape(token), markup)


@pytest.mark.parametrize("token", ["review", "rv-input", "rv-btn", "rv-approve", "rv-quit", "rv-go"])
def test_d0044_ac43_designed_class_names_have_css(html, token):
    """D0044-AC-43: 設計のクラス名のうち、見た目を決めるもの（.review・.rv-input・.rv-btn・.rv-approve・.rv-quit・.rv-go）に CSS の規則がある。"""
    assert rule(css_of(html), "." + token), token


def test_d0044_ac43_markup_skeleton_is_unchanged(html):
    """D0044-AC-43: _BODY（骨組み）は変えない：ボタン・入力欄・パネルは静的な HTML に無い（確認待ちが無い描き方が今と同じになる）。"""
    _style, _script, markup = parts(html)
    for word in ("<button", "<textarea", "<input", "rv-", 'class="review"', "role=\"group\""):
        assert word not in markup, word
    body = re.search(r"<body[^>]*>(.*?)(?:</body>|$)", markup, re.S | re.I).group(1)
    assert sorted(re.findall(r'\sid="([^"]+)"', body)) == ["final", "msg", "name", "stages"]


def test_d0044_ac43_script_sets_the_aria_and_form_attributes(html):
    """D0044-AC-43: 入力欄と文の欄の属性（role・aria-label・aria-live・maxlength・rows）、ボタンの type が JS にある。"""
    _style, script, _markup = parts(html)
    for token in ("aria-label", "aria-live", "polite", "status", "group", "maxlength", "rows", "button", "textarea"):
        assert token in script, token
    assert re.search(r"""["']type["']\s*,\s*["']button["']|\.type\s*=\s*["']button["']""", script)
    assert re.search(r"\.hidden\s*=|toggleAttribute\(\s*[\"']hidden|setAttribute\(\s*[\"']hidden", script), "見える・見えないを hidden 属性で切り替える"


def test_d0044_ac43_page_size_under_the_limit(html):
    """D0044-AC-43: ページの HTML は上限（40 KB。上げたときは上げた値をここと D0027-AC-55 に書く）以下。ボタンの分は増える（14 KB より大きい）。"""
    size = len(html.encode("utf-8"))
    assert 14_000 < size <= MAX_PAGE_BYTES, size


def test_d0044_ac43_page_is_still_one_script_one_style_without_external_loading(html, stripped):
    """D0044-AC-43・D0059-AC-06: ボタンを足しても、<script> は1つ・<style> は1つで、許した文字（Google Fonts の link 2本と SVG の名前空間 1 か所）を除いて、外部の読み込みも URL の形も無い。"""
    assert len(re.findall(r"<script\b", html, re.I)) == 1 and len(re.findall(r"<style\b", html, re.I)) == 1
    for token in EXTERNAL:
        assert token.lower() not in stripped.lower(), token
    assert "</" not in parts(html)[1]


def rule(css: str, selector: str) -> dict[str, str]:
    """セレクタが selector そのもの（疑似クラス・疑似要素のつかないもの）の規則の宣言を、順に重ねて返す。"""
    merged: dict[str, str] = {}
    for selectors, decls in css_rules(css):
        if selector in selectors:
            merged.update(decls)
    return merged


def test_d0044_ac43_hidden_attribute_hides(html):
    """D0044-AC-43: CSS に [hidden] { display: none; } がある（hidden 属性で見える・見えないを切り替えるため）。"""
    assert rule(css_of(html), "[hidden]").get("display") == "none"
    assert re.search(r"\[hidden\]\s*\{\s*display\s*:\s*none\s*(?:!important)?\s*;?\s*\}", css_of(html))


def test_d0044_ac43_panel_wraps_below_the_row(html):
    """D0044-AC-43: パネル（.review）は行の下に回り込む（flex: 1 1 100%）。"""
    assert rule(css_of(html), ".review").get("flex") == "1 1 100%"


def border_values(decl: dict[str, str]) -> str:
    return " ".join(v for k, v in decl.items() if k.startswith("border") and k != "border-radius")


def test_d0059_ac16_button_styles(html):
    """D0059-AC-16: ボタン（.rv-btn）は面（--panel）の地・1px solid var(--line) の枠・角は札（--r-tag）・min-height 2.75rem・font: inherit・文字は --fg。
    承認は --coral の塗り（文字は --on-coral）、中止は --bad の枠、実行するは 2px の --coral の枠、差し戻す・戻るは --line の枠のまま。入力欄も面の地。
    （D0044-AC-43 のボタンの色の検査を、新しい配色に書き直したもの）"""
    css = css_of(html)
    btn = rule(css, ".rv-btn")
    assert btn.get("min-height") == "2.75rem" and btn.get("font") == "inherit"
    assert btn.get("border") == "1px solid var(--line)"
    assert btn.get("border-radius") == "var(--r-tag)"
    assert btn.get("background") == "var(--panel)" and btn.get("color") == "var(--fg)"
    approve, quit_, go = rule(css, ".rv-approve"), rule(css, ".rv-quit"), rule(css, ".rv-go")
    assert approve.get("background") == "var(--coral)" and approve.get("color") == "var(--on-coral)", approve
    assert "var(--bad)" in border_values(quit_), quit_
    assert "2px" in border_values(go) and "var(--coral)" in border_values(go), go
    for plain in (".rv-revise", ".rv-back"):
        assert not re.search(r"var\(--(?:coral|bad|ok|teal)\)", border_values(rule(css, plain))), plain
    inp = rule(css, ".rv-input")
    assert inp.get("width") == "100%" and inp.get("resize") == "vertical" and inp.get("font") == "inherit"
    assert inp.get("border") == "1px solid var(--line)"
    assert inp.get("color") == "var(--fg)" and inp.get("background") == "var(--panel)"


def test_d0059_ac16_focus_ring_is_teal(html):
    """D0059-AC-16: :focus-visible は outline: 2px solid var(--teal)・outline-offset: 2px（ボタンも入力欄も。outline: none にしない）。"""
    css = css_of(html)
    for selector in (".rv-btn:focus-visible", ".rv-input:focus-visible"):
        decl = rule(css, selector)
        assert decl.get("outline") == "2px solid var(--teal)" and decl.get("outline-offset") == "2px", (selector, decl)
    assert "outline: none" not in css and "outline:none" not in css.replace(" ", "")


def test_d0059_ac16_buttons_are_not_told_apart_by_color_alone(html):
    """D0059-AC-16: ボタンは枠か塗りと文字ラベルがあり、色だけで区別しない：どのボタンにも枠（1px 以上）と文字のラベルがあり、承認は塗り、実行するは太い枠で、中止の枠と形が違う。今のままで通る部分（ラベルの文字）を含む。"""
    css = css_of(html)
    script = parts(html)[1]
    for label in ("承認", "直してほしい点を書いて差し戻す", "中止", "実行する", "戻る"):
        assert re.search(r"""makeButton\([^)]*["']%s["']""" % re.escape(label), script), label
    assert re.fullmatch(r"\d+px solid .*", rule(css, ".rv-btn").get("border", "")), "ボタンに枠が無い"
    shapes = {name: (rule(css, f".{name}").get("background"), "2px" in border_values(rule(css, f".{name}"))) for name in ("rv-approve", "rv-quit", "rv-go")}
    assert len(set(shapes.values())) == 3, f"承認・中止・実行するの形（塗り・枠の太さ）が同じ: {shapes}"


def test_d0044_ac43_disabled_buttons_look_stopped(html):
    """D0044-AC-43: :disabled は点線の枠と cursor: not-allowed（止まっていることが色だけでなく形でも分かる）。"""
    decl = rule(css_of(html), ".rv-btn:disabled")
    assert "dashed" in " ".join(v for k, v in decl.items() if k.startswith("border")), decl
    assert decl.get("cursor") == "not-allowed"


def test_d0059_ac16_button_css_uses_only_defined_tokens(html):
    """D0059-AC-16: ボタン・入力欄・パネル・文の欄の規則が使う var(--…) は、定義済みのトークンだけ。色の直書きが無い
    （D0044-AC-43 の「既存のトークンだけ」を、新しいトークン名に書き直したもの）。"""
    css = css_of(html)
    defined = set(declarations(root_block(css))) | set(theme_blocks(css)["dark"])
    for sel in (".review", ".rv-btn", ".rv-approve", ".rv-quit", ".rv-go", ".rv-back", ".rv-input", ".rv-msg"):
        decl = rule(css, sel)
        assert decl or sel in (".rv-back", ".rv-revise"), f"{sel} の規則が無い"
        for prop, value in decl.items():
            assert not COLOR_LITERAL.search(value), (sel, prop, value)
            assert set(re.findall(r"var\(\s*(--[\w-]+)", value)) <= defined, (sel, prop, value)
    assert {"--panel", "--coral", "--on-coral", "--teal", "--bad"} <= set(re.findall(r"var\(\s*(--[\w-]+)", css))


def test_d0044_ac43_new_motion_stays_inside_the_no_preference_media(html):
    """D0044-AC-43: 動き（transition）を足すなら @media (prefers-reduced-motion: no-preference) の中だけ。外に animation・transition が無い。"""
    css = css_of(html)
    inside = block_after(css, MOTION_MEDIA)
    outside = css.replace(inside, "")
    for word in ("animation", "transition", "@keyframes"):
        assert word not in outside, word
    for sel in (".rv-btn", ".rv-input", ".rv-go", ".review"):
        assert "transition" not in " ".join(rule(outside, sel)), sel


def test_d0044_ac43_message_area_wraps_long_text(html):
    """D0044-AC-43: 360px で横にはみ出さない：固定の幅が 360px を超えず、全体の overflow-wrap: anywhere が新しい要素にもかかる（既存の指定を弱めない）。"""
    css = css_of(html)
    for sel in (".review", ".rv-btn", ".rv-input", ".rv-msg"):
        for prop in ("width", "min-width"):
            value = rule(css, sel).get(prop, "")
            for px in re.findall(r"(\d+(?:\.\d+)?)\s*px", value):
                assert float(px) <= 360, (sel, prop, value)
    assert re.search(r"(?:^|[}\s])\*[^{]*\{[^}]*overflow-wrap\s*:\s*anywhere", css)
    assert not re.search(r"overflow-x\s*:\s*(?:hidden|clip)", css)


def test_d0044_ac43_build_page_is_deterministic_and_takes_no_arguments(html):
    """D0044-AC-43: build_page() は引数を取らず、同じ呼び出しは同じ HTML を返す。外から来た文字（環境・記録）を含まない。今のままで通る（守り続ける検査）。"""
    assert list(inspect.signature(live_page.build_page).parameters) == []
    with pytest.raises(TypeError):
        live_page.build_page("x")  # type: ignore[call-arg]
    assert live_page.build_page() == live_page.build_page() == html
    assert "HOSTILE" not in html and str(ROOT) not in html


# ---- D0059：見た目だけの変更で、振る舞い・守りは変えない ---------------------------------------------------------


def test_d0059_ac14_build_page_is_unchanged_in_kind(html):
    """D0059-AC-14: build_page() は引数を取らず、同じ呼び出しで同じ HTML。HTML に記録の文字・手元のパス・メールアドレス・写しの日時が入らない。今のままで通る（守り続ける検査）。"""
    assert list(inspect.signature(live_page.build_page).parameters) == []
    assert live_page.build_page() == html
    assert not re.search(r"[A-Za-z]:[\\/]+Users", html) and str(ROOT) not in html and "HOSTILE" not in html
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]", html)
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", html)


def test_d0059_ac15_skeleton_ids_and_one_comments_call(html):
    """D0059-AC-15: _BODY の id は name・final・msg・stages の4つだけ（新しい入れ物は class で取る）。claude.use("comments") を呼ぶ場所は1つ、claude.use は db と comments の2回だけ、
    onGo に await が無く sendToClaude を呼ぶ、confirm・alert・prompt を使わない。今のままで通る（守り続ける検査）。"""
    _style, script, markup = parts(html)
    body = re.search(r"<body[^>]*>(.*?)(?:</body>|$)", markup, re.S | re.I).group(1)
    assert sorted(re.findall(r'\sid="([^"]+)"', body)) == ["final", "msg", "name", "stages"]
    assert sorted(re.findall(r'\sid="([^"]+)"', html)) == ["final", "msg", "name", "stages"]
    assert len(re.findall(r"""claude\s*\.\s*use\(\s*["']comments["']""", script)) == 1
    assert len(re.findall(r"""claude\s*\.\s*use\(""", script)) == 2
    on_go = function_body(script, "onGo")
    assert "sendToClaude" in on_go and "await" not in on_go
    assert not re.search(r"\b(?:window\.)?(?:confirm|alert|prompt)\s*\(", html)


def test_d0059_new_containers_exist_without_ids(html):
    """D0059-AC-10・AC-11・AC-12: 骨組みに、頭（header.head）・更新の時刻（.updated）・札（.chips）・帯（.band）・数（.counts）の入れ物がある（id は付けない。JS が class で取る）。"""
    markup = parts(html)[2]
    for token in (r"<header\b[^>]*\bclass=\"head\"", r"\bclass=\"updated\"", r"\bclass=\"chips\"", r"\bclass=\"band\"", r"\bclass=\"counts\""):
        assert re.search(token, markup), token
    assert "pipe-in · 進み具合" in markup
