"""D0027：進み具合のページの HTML（pipe_in/engine/live_page.py の build_page）。

HTML は1枚で完結し、外部の読み込みが無く、外から来た文字を入れない。ここは文字の検査（構造・CSS・禁止語）。
ページの JS の動きは tests/test_live_page_js.py（Node で動かす）。
"""

from __future__ import annotations

import inspect
import os
import re
from pathlib import Path

import pytest

import live_support as ls
from pipe_in.engine import live, live_page

ROOT = Path(__file__).resolve().parents[1]
MAX_PAGE_BYTES = 40 * 1024


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


@pytest.mark.parametrize("token", EXTERNAL, ids=repr)
def test_d0027_ac47_page_has_no_external_loading(html, token):
    """D0027-AC-47: HTML に外部の読み込み（script src・link・@import・url()・http(s)・iframe・img・fetch・XHR・WebSocket など）が無い。"""
    assert token.lower() not in html.lower()


def test_d0027_ac47_no_url_like_text_anywhere(html):
    """D0027-AC-47: スキーム付きの URL（http: ftp: data: javascript: blob: file: ws:）が、文字としても入っていない。"""
    assert not re.search(r"\b(?:https?|ftp|wss?|data|javascript|blob|file|mailto):", html, re.I)


def test_d0027_ac47_exactly_one_script_and_one_style(html):
    """D0027-AC-47: <script> は1つ、<style> は1つ（設計の「1枚で完結」）。type=module や外部指定が無い。"""
    assert len(re.findall(r"<script\b", html, re.I)) == 1
    assert len(re.findall(r"</script", html, re.I)) == 1
    assert len(re.findall(r"<style\b", html, re.I)) == 1
    assert not re.search(r"<script[^>]*\b(?:src|type|async|defer|nomodule|integrity|crossorigin)\b", html, re.I)


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

TOKENS = ["--bg", "--fg", "--muted", "--line", "--run", "--review", "--ok", "--ng"]


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


def test_d0027_ac52_color_tokens_light_and_dark(html):
    """D0027-AC-52: ライトの色は :root のトークン、ダークは prefers-color-scheme: dark と [data-theme="dark"]、ライトの強制は [data-theme="light"]。"""
    css = css_of(html)
    light = declarations(root_block(css))
    assert set(TOKENS) <= set(light), f"ライトに無いトークン: {set(TOKENS) - set(light)}"
    media = dark_media_block(css)
    assert ':root:not([data-theme="light"])' in media.replace("'", '"')
    dark_auto = declarations(media)
    dark_forced = declarations(data_theme_block(css, "dark"))
    light_forced = declarations(data_theme_block(css, "light"))
    for name, block in (("dark(media)", dark_auto), ("dark(forced)", dark_forced), ("light(forced)", light_forced)):
        assert set(TOKENS) <= set(block), f"{name} に無いトークン: {set(TOKENS) - set(block)}"
    assert {k: dark_auto[k] for k in TOKENS} == {k: dark_forced[k] for k in TOKENS}, "自動のダークと強制のダークで色が違う"
    assert {k: light_forced[k] for k in TOKENS} == {k: light[k] for k in TOKENS}, "強制のライトと既定のライトで色が違う"
    assert dark_forced["--bg"] != light["--bg"] and dark_forced["--fg"] != light["--fg"]


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


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_d0027_ac52_text_colors_are_readable_on_the_background(html, theme):
    """D0027-AC-52: 本文と補助の文字は、背景に対して WCAG の 4.5 以上、状態の色は 3 以上のコントラスト（色トークンは 16 進で書く）。"""
    css = css_of(html)
    tokens = declarations(root_block(css)) if theme == "light" else declarations(data_theme_block(css, "dark"))
    assert contrast(tokens["--fg"], tokens["--bg"]) >= 4.5
    assert contrast(tokens["--muted"], tokens["--bg"]) >= 4.5
    for name in ("--run", "--review", "--ok", "--ng"):
        assert contrast(tokens[name], tokens["--bg"]) >= 3.0, name


def test_d0027_ac52_contrast_function_is_correct():
    """D0027-AC-52: コントラストを測る補助が正しい（白と黒は 21、同じ色は 1）。"""
    assert round(contrast("#000000", "#ffffff"), 2) == 21.0
    assert contrast("#123456", "#123456") == pytest.approx(1.0)
    assert contrast("#777", "#fff") < 4.5 < contrast("#595959", "#fff")


# ---- AC-53 動き -------------------------------------------------------------------------------------------


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


@pytest.mark.parametrize("symbol", ["✓", "✕", "↩"])
def test_d0027_ac55_status_symbols_are_in_the_script(html, symbol):
    """D0027-AC-55: 状態は色だけで伝えない。文字の記号（終わり ✓・失敗 ✕・差し戻し ↩）が JS にある。
    まだ・動いている・確認待ちの印は書体の字形に頼らず CSS の形で描く（AC-86）ので、○ ● ◐ は JS に無い。"""
    assert symbol in parts(html)[1]


def test_d0027_ac55_status_symbols_are_distinct_per_status(html):
    """D0027-AC-55: 6つの状態の記号は、どれも違う。"""
    assert len({"○", "●", "◐", "✓", "✕", "↩"}) == 6
    _style, script, _markup = parts(html)
    for status in ("waiting", "running", "review", "done", "failed", "revised"):
        assert status in script, status


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
    """D0027-AC-86: .mark は固定の幅と高さを持ち（どの状態でも印の列の幅が同じ）、360px を超えない。"""
    base = decls_for(css_of(html), ".mark")
    for prop in ("width", "height"):
        size = length_of(base.get(prop))
        assert size is not None and 0 < size, f".mark の {prop} が固定の長さでない: {base.get(prop)!r}"
    assert length_of(base["width"]) <= 360 and length_of(base["height"]) <= 360
    assert not base.get("min-width") or length_of(base["min-width"]) is not None


def test_d0027_ac86_mark_is_centered(html):
    """D0027-AC-86: 印は枠の中で中央に寄る（text-align か flex/grid の中央寄せ）。"""
    base = decls_for(css_of(html), ".mark")
    centered = (
        base.get("text-align") == "center"
        or base.get("justify-content") == "center"
        or base.get("place-items") in ("center", "center center")
        or base.get("place-content") in ("center", "center center")
    )
    assert centered, base


def test_d0027_ac86_mark_does_not_shrink(html):
    """D0027-AC-86: 印の列は縮まない（flex の中で幅がつぶれて、表示名の位置がずれない）。"""
    base = decls_for(css_of(html), ".mark")
    assert base.get("flex-shrink") == "0" or base.get("flex", "").split()[:2] == ["0", "0"], f".mark が縮む: {base}"


@pytest.mark.parametrize("status", ["waiting", "running", "review", "done", "failed", "revised", "unknown"])
def test_d0027_ac86_states_do_not_change_the_mark_size(html, status):
    """D0027-AC-86: 状態ごとの規則が、印の幅・高さを変えない（変えるなら基本と同じ値）。"""
    css = css_of(html)
    base = decls_for(css, ".mark")
    state = decls_for(css, f".s-{status} .mark")
    for prop in ("width", "min-width", "max-width", "height", "min-height", "max-height", "padding", "margin", "font-size", "flex", "flex-basis"):
        if prop in state:
            assert state[prop] == base.get(prop), (status, prop, state[prop], base.get(prop))


@pytest.mark.parametrize("status", CSS_DRAWN_STATES)
def test_d0027_ac86_waiting_running_review_marks_are_drawn_by_css_shapes(html, status):
    """D0027-AC-86: まだ・動いている・確認待ちの印は、書体の字形に頼らず CSS の形（枠線・塗り・半分の塗りなど）で描く。
    .s-<状態> .mark（に疑似要素がついたもの）が border・background・box-shadow・clip-path などを持つ。content に字形（空でない文字）を入れない。"""
    css = css_of(html)
    state = decls_for(css, f".s-{status} .mark")
    shape = {k: v for k, v in state.items() if k.startswith(SHAPE_PROPS)}
    assert shape, f".s-{status} .mark に CSS の形が無い: {state}"
    content = state.get("content", '""').strip()
    assert content in ('""', "''", "none", "normal"), f"content に字形を入れている: {content!r}"


def test_d0027_ac86_waiting_running_review_shapes_differ(html):
    """D0027-AC-86: まだ・動いている・確認待ちの形は、互いに違う（色だけでなく形でも見分けられる）。"""
    css = css_of(html)
    shapes = []
    for status in CSS_DRAWN_STATES:
        state = decls_for(css, f".s-{status} .mark")
        shapes.append(frozenset((k, v) for k, v in state.items() if k.startswith(SHAPE_PROPS)))
    assert all(shapes), shapes
    assert len(set(shapes)) == 3, shapes


def test_d0027_ac86_shapes_use_color_tokens(html):
    """D0027-AC-86: 形の色もトークン（var(--…)）で書く。16 進などの直書きをしない（AC-52 と同じ決め）。"""
    css = css_of(html)
    for status in CSS_DRAWN_STATES:
        for prop, value in decls_for(css, f".s-{status} .mark").items():
            if prop.startswith(("border", "background", "box-shadow")):
                assert not COLOR_LITERAL.search(value), (status, prop, value)


def test_d0027_ac86_pulse_stays_on_the_running_mark(html):
    """D0027-AC-86: 動いている印の脈打ち（AC-53）は、形になっても .s-running .mark にかかる（no-preference の中だけ）。"""
    inside = block_after(css_of(html), MOTION_MEDIA)
    assert re.search(r"\.s-running\s+\.mark(?:::?[\w-]+)?\s*\{[^}]*animation", inside)


def test_d0027_ac86_script_does_not_use_glyph_marks_for_css_drawn_states(html):
    """D0027-AC-86: JS の STATUS に、まだ・動いている・確認待ちの字形（○ ● ◐）を置かない。"""
    script = parts(html)[1]
    for glyph in "○●◐":
        assert glyph not in script, glyph


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


def test_d0044_ac43_names_avoid_words_the_forbidden_word_checks_would_match(html):
    """D0044-AC-43: 関数名に confirm(・alert(・prompt( を含めず、キーの名前に data・file・blob を使わない（data: の形が URL と見なされるため）。"""
    _style, script, _markup = parts(html)
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


def test_d0044_ac43_page_is_still_one_script_one_style_without_external_loading(html):
    """D0044-AC-43: ボタンを足しても、<script> は1つ・<style> は1つで、外部の読み込みも URL の形も無い。"""
    assert len(re.findall(r"<script\b", html, re.I)) == 1 and len(re.findall(r"<style\b", html, re.I)) == 1
    for token in EXTERNAL:
        assert token.lower() not in html.lower(), token
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


def test_d0044_ac43_buttons_are_tall_enough_and_use_tokens(html):
    """D0044-AC-43: ボタン（.rv-btn）は min-height: 2.75rem・枠線 1px solid var(--line)・背景 var(--bg)・色 var(--fg)・font: inherit。"""
    decl = rule(css_of(html), ".rv-btn")
    assert decl.get("min-height") == "2.75rem"
    assert decl.get("border") == "1px solid var(--line)"
    assert decl.get("background") == "var(--bg)"
    assert decl.get("color") == "var(--fg)"
    assert decl.get("font") == "inherit"


def test_d0044_ac43_approve_quit_and_go_are_told_apart_by_the_frame_not_by_color_alone(html):
    """D0044-AC-43: 承認は枠線に var(--ok)、中止は枠線に var(--ng)、実行は枠線 2px。ボタンは枠線と文字ラベルがあるので、押せることは色だけに頼らない。"""
    css = css_of(html)
    approve, quit_, go = rule(css, ".rv-approve"), rule(css, ".rv-quit"), rule(css, ".rv-go")
    assert any("var(--ok)" in v for k, v in approve.items() if k.startswith("border")), approve
    assert any("var(--ng)" in v for k, v in quit_.items() if k.startswith("border")), quit_
    assert any("2px" in v for k, v in go.items() if k.startswith("border")), go
    assert not any("var(--ng)" in v for k, v in approve.items() if k.startswith("border"))


def test_d0044_ac43_disabled_buttons_look_stopped(html):
    """D0044-AC-43: :disabled は点線の枠と cursor: not-allowed（止まっていることが色だけでなく形でも分かる）。"""
    decl = rule(css_of(html), ".rv-btn:disabled")
    assert "dashed" in " ".join(v for k, v in decl.items() if k.startswith("border")), decl
    assert decl.get("cursor") == "not-allowed"


def test_d0044_ac43_focus_mark_is_visible(html):
    """D0044-AC-43: :focus-visible は outline: 2px solid var(--run)・outline-offset: 2px（キーボードで操作でき、フォーカスの印が見える）。"""
    decl = rule(css_of(html), ".rv-btn:focus-visible")
    assert decl.get("outline") == "2px solid var(--run)" and decl.get("outline-offset") == "2px", decl
    assert "outline: none" not in css_of(html) and "outline:none" not in css_of(html).replace(" ", "")


def test_d0044_ac43_input_fits_the_width(html):
    """D0044-AC-43: 入力欄（.rv-input）は width: 100%・resize: vertical・font: inherit・枠線 1px solid var(--line)・色と背景はトークン。"""
    decl = rule(css_of(html), ".rv-input")
    assert decl.get("width") == "100%" and decl.get("resize") == "vertical" and decl.get("font") == "inherit"
    assert decl.get("border") == "1px solid var(--line)"
    assert decl.get("color") == "var(--fg)" and decl.get("background") == "var(--bg)"


def test_d0044_ac43_new_css_uses_only_the_existing_color_tokens(html):
    """D0044-AC-43: 増えた規則が使う var(--…) は既存のトークンだけ（--bg・--fg・--muted・--line・--run・--review・--ok・--ng）。色の直書きが無い。"""
    css = css_of(html)
    used = set(re.findall(r"var\(\s*(--[\w-]+)", css))
    assert used <= set(TOKENS), used - set(TOKENS)
    for sel in (".review", ".rv-btn", ".rv-approve", ".rv-quit", ".rv-go", ".rv-back", ".rv-input", ".rv-msg"):
        for prop, value in rule(css, sel).items():
            assert not COLOR_LITERAL.search(value), (sel, prop, value)


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


# ---- D0059：上の部品（更新の時刻・確認待ちの札・合計・進みの帯）と確認待ちの色 ------------------------------------------
#
# 部品の動きは tests/test_live_page_js.py（Node の台）。ここは CSS と HTML の文字の検査。

NEW_TOP_SELECTORS = [".updated", ".summary", ".badge", ".total", ".bar", ".bar-gap", ".bar-done", ".bar-pending"]
NEW_TOP_CLASSES = ["updated", "summary", "badge", "total", "bar", "bar-gap", "bar-done", "bar-pending"]
REVIEW_LIGHT = "#c2471f"
REVIEW_DARK = "#ff8a65"


def vars_in(value: str) -> set[str]:
    return set(re.findall(r"var\(\s*(--[\w-]+)", value))


def test_d0059_new_parts_are_not_in_the_static_markup(html):
    """D0059: 新しい部品は _BODY に置かず JS が作る（1.1）。マークアップにそのクラスが無く、JS に el(…, "<クラス>") で付ける形がある。"""
    _style, script, markup = parts(html)
    for cls in NEW_TOP_CLASSES:
        assert not re.search(r"""class\s*=\s*["'][^"']*\b%s\b""" % re.escape(cls), markup), cls
    for cls in ("updated", "summary", "badge", "total", "bar"):
        assert re.search(r"""\bel\(\s*["'][a-z]+["']\s*,\s*["']%s["']""" % re.escape(cls), script), f"JS で {cls} の要素を作っていない"


def test_d0059_ac11_bar_is_8px_high_and_gap_is_2px(html):
    """D0059-AC-11: 帯（.bar）の高さは 8px、すき間（.bar-gap）の幅は 2px。"""
    css = css_of(html)
    assert rule(css, ".bar").get("height") == "8px", rule(css, ".bar")
    assert rule(css, ".bar-gap").get("width") == "2px", rule(css, ".bar-gap")


def test_d0059_ac13_bar_colors_use_tokens(html):
    """D0059-AC-13: 帯の完了は var(--ok)、確認待ちは var(--review)、地は線の色 var(--line) で塗る（色をじかに書かない）。"""
    css = css_of(html)
    assert rule(css, ".bar-done").get("background") == "var(--ok)"
    assert rule(css, ".bar-pending").get("background") == "var(--review)"
    assert rule(css, ".bar").get("background") == "var(--line)"


def test_d0059_ac40_bar_css_has_no_running_pattern(html):
    """D0059-AC-40: 帯に動いている段の模様を作らない：CSS に radial-gradient が無く、帯の規則（.bar で始まるセレクタ）に --run が無い。"""
    css = css_of(html)
    assert rule(css, ".bar"), "帯の規則が無い"
    assert "radial-gradient" not in css
    for selectors, decls in css_rules(css):
        if any(s.startswith(".bar") for s in selectors):
            assert not any("--run" in v for v in decls.values()), (selectors, decls)


def test_d0059_ac20_badge_uses_the_review_color(html):
    """D0059-AC-20: 札（.badge）の文字の色と枠線は var(--review)。"""
    decl = rule(css_of(html), ".badge")
    assert decl.get("color") == "var(--review)", decl
    assert "var(--review)" in decl.get("border", ""), decl


def test_d0059_ac27_script_sets_style_only_through_style_width(html):
    """D0059-AC-27: スクリプトがスタイルに触れるのは .style.width = だけ（帯の幅）。setAttribute("style"・cssText・setProperty が無い。"""
    _style, script, _markup = parts(html)
    assert re.search(r"\.style\.width\s*=", script), "帯の幅を .style.width で入れていない"
    assert len(re.findall(r"\.style\b", script)) == len(re.findall(r"\.style\.width\s*=", script)), re.findall(r"\.style\S{0,20}", script)
    assert not re.search(r"""setAttribute\(\s*["']style""", script)
    assert "cssText" not in script and "setProperty" not in script


def test_d0059_ac27_style_check_finds_the_forbidden_forms():
    """D0059-AC-27: 上の検査そのものが、.style.cssText・.style.setProperty・.style.color = を見つける（.style.width = だけが通る）。"""
    def ok(script: str) -> bool:
        return len(re.findall(r"\.style\b", script)) == len(re.findall(r"\.style\.width\s*=", script)) and "cssText" not in script and "setProperty" not in script
    assert ok('node.style.width = part.width;')
    for bad in ('node.style.cssText = "x";', 'node.style.setProperty("width", "1px");', 'node.style.color = "red";', 'node.style["width"] = "1px";'):
        assert not ok(bad), bad


def test_d0059_ac31_new_rules_use_only_tokens(html):
    """D0059-AC-31: 新しいセレクタ（.updated・.summary・.badge・.total・.bar・.bar-gap・.bar-done・.bar-pending）の規則があり、値に色の直書きが無く、var() は既存のトークンだけ。"""
    css = css_of(html)
    for sel in NEW_TOP_SELECTORS:
        decl = rule(css, sel)
        assert decl, f"{sel} の規則が無い"
        for prop, value in decl.items():
            assert not COLOR_LITERAL.search(value), (sel, prop, value)
            assert not (set(re.findall(r"[a-z]+", re.sub(r"var\([^)]*\)", "", value).lower())) & NAMED_COLORS), (sel, prop, value)
            assert vars_in(value) <= set(TOKENS), (sel, prop, value)


def test_d0059_ac32_new_rules_have_no_wide_fixed_width(html):
    """D0059-AC-32: 新しいセレクタの width・min-width の px が 360 以下。全体の overflow-wrap: anywhere が残り、overflow-x を隠さない。"""
    css = css_of(html)
    assert rule(css, ".summary") and rule(css, ".bar"), "上の部品の規則が無い"
    for sel in NEW_TOP_SELECTORS:
        for prop in ("width", "min-width", "flex", "flex-basis"):
            value = rule(css, sel).get(prop, "")
            for px in re.findall(r"(\d+(?:\.\d+)?)\s*px", value):
                assert float(px) <= 360, (sel, prop, value)
    assert re.search(r"(?:^|[}\s])\*[^{]*\{[^}]*overflow-wrap\s*:\s*anywhere", css)
    assert not re.search(r"overflow-x\s*:\s*(?:hidden|clip)", css)


def test_d0059_ac36_review_token_is_coral_in_all_four_places(html):
    """D0059-AC-36: --review は :root と [data-theme="light"] で #c2471f、prefers-color-scheme: dark の中と [data-theme="dark"] で #ff8a65（4 か所すべて）。#9a6700・#d29922 がページに無い。"""
    css = css_of(html)
    places = {
        ":root": declarations(root_block(css)),
        "light(forced)": declarations(data_theme_block(css, "light")),
        "dark(media)": declarations(dark_media_block(css)),
        "dark(forced)": declarations(data_theme_block(css, "dark")),
    }
    got = {name: block.get("--review", "").lower() for name, block in places.items()}
    assert got == {":root": REVIEW_LIGHT, "light(forced)": REVIEW_LIGHT, "dark(media)": REVIEW_DARK, "dark(forced)": REVIEW_DARK}, got
    low = html.lower()
    assert "#9a6700" not in low and "#d29922" not in low


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_d0059_ac37_review_color_is_readable_as_text(html, theme):
    """D0059-AC-37: --review は、その画面の地 --bg に対してコントラスト 4.5 以上（確認待ちの経過は文字なので、文字の基準で見る）。"""
    css = css_of(html)
    tokens = declarations(root_block(css)) if theme == "light" else declarations(data_theme_block(css, "dark"))
    assert contrast(tokens["--review"], tokens["--bg"]) >= 4.5, (tokens["--review"], tokens["--bg"])


def test_d0059_ac37_coral_values_pass_the_text_contrast():
    """D0059-AC-37: 設計の板のコーラルそのものが、明るい地 #ffffff と暗い地 #0d1117 に対して 4.5 以上（測る補助の確かめ）。"""
    assert contrast(REVIEW_LIGHT, "#ffffff") >= 4.5
    assert contrast(REVIEW_DARK, "#0d1117") >= 4.5


def test_d0059_ac38_token_names_are_unchanged(html):
    """D0059-AC-38: 4 か所それぞれの色のトークンの名前の集まりが、前と同じ 8 つ（--review を消さず、--coral などを足さない）。var() の集まりもその中。"""
    css = css_of(html)
    for name, block in (
        (":root", root_block(css)),
        ("light(forced)", data_theme_block(css, "light")),
        ("dark(media)", dark_media_block(css)),
        ("dark(forced)", data_theme_block(css, "dark")),
    ):
        assert set(declarations(block)) == set(TOKENS), (name, set(declarations(block)) ^ set(TOKENS))
    assert vars_in(css) <= set(TOKENS)


def test_d0059_ac39_review_is_painted_only_with_the_review_token(html):
    """D0059-AC-39: 確認待ちの行の印と経過・印の半分の塗り・差し戻しの印・帯の確認待ち・札は var(--review) で塗り、確認待ちを塗る規則にほかのトークンが無い。"""
    css = css_of(html)
    assert decls_for(css, ".s-review .mark").get("color") == "var(--review)"
    assert decls_for(css, ".s-review .elapsed").get("color") == "var(--review)"
    assert decls_for(css, ".s-revised .mark").get("color") == "var(--review)"
    review_mark = decls_for(css, ".s-review .mark")
    assert "var(--review)" in review_mark.get("border", "")
    half = review_mark.get("background", "")
    assert "linear-gradient" in half and vars_in(half) == {"--review"} and "transparent" in half, half
    assert rule(css, ".badge").get("color") == "var(--review)"
    assert rule(css, ".bar-pending").get("background") == "var(--review)"
    for selectors, decls in css_rules(css):
        if any(re.search(r"\.s-review\b|\.badge\b|\.bar-pending\b", s) for s in selectors):
            used = set().union(*(vars_in(v) for v in decls.values())) if decls else set()
            assert used <= {"--review"}, (selectors, decls)
