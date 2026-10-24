"""D0029・D0042: 計画ボード（/pipe-plan）。

- /pipe-plan は、Claude のアーティファクトの計画ボードを開く・GitHub と決定の記録に合わせる・項目を足す
- ボードのページのひな形は .claude/skills/pipe-plan/board.html に置く。項目はページに書かず、アーティファクトのデータに入れる
- ボードの URL は手元の事情なのでリポジトリに書かない（題で探す）
- D0042: カードの「実行」から、確認を経て新しいセッションを作り /pipe-in を始める（道具は3つ）。
  ひな形と SKILL.md の文字列を読んで確かめる（JS は動かさない・ネットワークは使わない）
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
TOOLS3 = '{server: "Claude Code Remote", tools: ["list_sessions", "create_session", "list_environments"]}'


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def block_after(text: str, marker: str) -> str:
    """marker の位置から、最初の { に対応する } までを返す（文字列の中の波括弧は数えない）。"""
    start = text.find(marker)
    assert start >= 0, f"{marker} が見つからない"
    i = text.find("{", start)
    assert i >= 0, f"{marker} の後ろに波括弧が無い"
    depth, quote, j = 0, "", i
    while j < len(text):
        c = text[j]
        if quote:
            if c == "\\":
                j += 1
            elif c == quote:
                quote = ""
        elif c in "\"'`":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : j + 1]
        j += 1
    raise AssertionError(f"{marker} の波括弧が閉じない")


def fn(html: str, name: str) -> str:
    """function <name>( の本文（async function も含む）。"""
    return block_after(html, f"function {name}(")


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


def test_d0029_ac07_listed_in_help():
    """D0029-AC-07: /pipe-help の一覧に /pipe-plan がある。"""
    assert "`/pipe-plan" in read(HELP)


def test_d0029_ac08_decision_record_listed():
    """D0029-AC-08: 決定の記録 D0029 があり、決定の記録の表に載っている。"""
    assert list(DECISIONS.glob("D0029-*.md")), "D0029 の記録が無い"
    assert "D0029" in read(DECISIONS / "README.md")


def test_d0029_ac13_board_moves_cards_without_dialog():
    """D0029-AC-13: ボードは、カードを引いて別の列に落とす・次の状態へ進めるボタンで、状態だけを書き換える（update）。"""
    html = read(BOARD)
    assert 'draggable = true' in html and '"drop"' in html
    assert ".update({ status" in html


# ---- D0042: カードから新しいセッションで /pipe-in を始める ----
# D0029-AC-11・12・06 は仕様の変更（読むだけ → 確認を経て作る）なので、下の
# D0042-AC-01・03・11 に置き換えた。


def test_d0040_block_after_finds_nested_braces():
    """検査の補助（AC ではない）：block_after は、入れ子の波括弧と、文字列の中の波括弧を正しく扱う。"""
    text = 'x f() { if (a) { "}" } else { b } } tail { z }'
    assert block_after(text, "f()") == 'f() { if (a) { "}" } else { b } }'


def test_d0040_ac01_board_calls_three_tools():
    """D0042-AC-01（D0029-AC-11 を新しい3道具に合わせた）: ボードが SESSION_SERVER に呼ぶ道具は list_sessions・create_session・list_environments の3つ。"""
    html = read(BOARD)
    tools = set(re.findall(r'(?:callTool|watchTool)\(\s*SESSION_SERVER\s*,\s*"([a-z_]+)"', html))
    assert tools == {"list_sessions", "create_session", "list_environments"}, tools
    assert 'const SESSION_SERVER = "Claude Code Remote";' in html


def test_d0040_ac02_board_has_no_other_tools():
    """D0042-AC-02: ボードに send_message・archive_session・interrupt_session の語が無い。（今の作りでも通る。守り続けるための検査）"""
    html = read(BOARD)
    assert re.search(r"\b(?:send_message|archive_session|interrupt_session)\b", html) is None


def test_d0040_ac03_skill_declares_three_tools():
    """D0042-AC-03（D0029-AC-12 を3道具に合わせた）: スキルの公開の宣言は3道具で、list_sessions だけの古い宣言が残っていない。"""
    text = read(SKILL)
    assert TOOLS3 in text
    assert 'tools: ["list_sessions"]}' not in text


def test_d0040_ac04_create_session_only_from_confirm_submit():
    """D0042-AC-04: create_session を呼ぶ createSession は、確認フォームの submit の処理からだけ呼ばれる。"""
    html = read(BOARD)
    assert html.count('"create_session"') == 1
    assert "function createSession(" in html
    assert html.count("createSession(") - html.count("function createSession(") == 1
    submit = block_after(html, '$("run-form").addEventListener("submit"')
    assert "createSession(" in submit


def test_d0040_ac05_environment_id_always_passed():
    """D0042-AC-05: create_session の入力に environment_id が入り、環境が空なら呼ぶ前に戻る。"""
    body = fn(read(BOARD), "createSession")
    assert "environment_id: envId" in body
    assert "if (!envId" in body
    assert body.index("if (!envId") < body.index("callTool")


def test_d0040_ac06_run_needs_can_write():
    """D0042-AC-06: 「実行」を出す条件 canRun に canWrite があり、書けない人で canWrite を落とす既存の結びが残る。"""
    html = read(BOARD)
    assert "canWrite" in fn(html, "canRun")
    assert "canWrite = false" in html


def test_d0040_ac07_run_hidden_while_session_running():
    """D0042-AC-07: canRun は一覧を読み終えたこと（sessionsLoaded）と isRunning を見る。isRunning は ARCHIVED・COMPLETED・FAILED を終わりとして扱う。"""
    html = read(BOARD)
    can = fn(html, "canRun")
    assert "sessionsLoaded" in can and "isRunning(" in can
    running = fn(html, "isRunning")
    for word in ("ARCHIVED", "COMPLETED", "FAILED"):
        assert word in running, word


def test_d0040_ac08_prompt_built_from_title_and_note():
    """D0042-AC-08: 最初の言葉は「/pipe-in 」に題とメモを付けて作り、題が空のカードでは canRun が偽になる。"""
    html = read(BOARD)
    build = fn(html, "buildPrompt")
    assert '"/pipe-in "' in build and ".title" in build and ".note" in build
    assert ".title" in fn(html, "canRun")


def test_d0040_ac09_run_dialog_uses_text_content():
    """D0042-AC-09: 確認の画面の動的な文（環境の選び・失敗の理由・環境の説明・送る言葉）は el()・textContent・value で入れる。"""
    html = read(BOARD)
    assert 'id="run-dlg"' in html
    assert re.search(r'\$\("run-msg"\)\.textContent', html)
    assert re.search(r'\$\("run-env-note"\)\.textContent', html)
    assert re.search(r'\$\("run-prompt"\)\.value', html)
    load = fn(html, "loadEnvironments")
    assert "el(" in load or "textContent" in load
    for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert bad not in html, bad


def test_d0040_ac10_session_id_checked_before_update():
    """D0042-AC-10: 返事から取った ID が ^session_[A-Za-z0-9]+$ に合うときだけ、カードの session を update で書く。"""
    html = read(BOARD)
    ext = fn(html, "extractSessionId")
    assert "^session_[A-Za-z0-9]+$" in ext
    assert "session_id" in ext and "session.id" in ext
    body = fn(html, "createSession")
    i_ext = body.index("extractSessionId(")
    i_throw = body.index("throw", i_ext)
    i_upd = body.index(".update({ session:")
    assert i_ext < i_throw < i_upd


def test_d0040_ac11_no_url_id_or_local_path():
    """D0042-AC-11（D0029-AC-06 を広げた）: スキル・ひな形・D0042 の記録に、ボードの URL・実際のセッション ID・手元のパスが無い。"""
    records = list(DECISIONS.glob("D0042-*.md"))
    assert records, "D0042 の記録が無い"
    for path in (SKILL, BOARD, *records):
        text = read(path)
        assert not re.search(r"claude\.ai/(?:code/)?artifact/[A-Za-z0-9-]{6,}", text), path
        assert not re.search(r"session_[A-Za-z0-9]{10,}", text), path
        for local in ("/home/", "/Users/", "C:\\Users"):
            assert local not in text, (path, local)


def test_d0040_ac12_listed_in_help_and_decisions():
    """D0042-AC-12: /pipe-help の /pipe-plan の行に「新しいセッション」があり、決定の記録の表と記録に D0042 がある。"""
    lines = [ln for ln in read(HELP).splitlines() if "`/pipe-plan" in ln]
    assert lines and any("新しいセッション" in ln for ln in lines), lines
    assert "D0042" in read(DECISIONS / "README.md")
    assert list(DECISIONS.glob("D0042-*.md")), "D0042 の記録が無い"


def test_d0040_ac13_old_board_asks_republish():
    """D0042-AC-13: 古いボード（list_sessions だけの宣言）では、ページが not_in_manifest で「公開し直す」と出し、スキルの「開く」が宣言の古さを見つけて公開し直しを勧める。"""
    err = fn(read(BOARD), "runError")
    assert "not_in_manifest" in err and "公開し直す" in err
    text = read(SKILL)
    start = text.index("## 2. 開く")
    section = text[start : text.index("## 3.", start)]
    for word in ("create_session", "list_environments", "公開し直"):
        assert word in section, word


def test_d0040_ac19_environment_choice_and_remember():
    """D0042-AC-19: 環境は state が active のものだけ選べ、1件なら自動で使い、選んだ環境を settings/run に覚える。items には混ぜない。"""
    html = read(BOARD)
    ext = fn(html, "extractEnvironments")
    assert '"active"' in ext and "environment_id" in ext
    assert "length === 1" in fn(html, "pickEnvironment")
    assert 'collection("settings")' in html and 'doc("run")' in html and "environmentId" in html
    for line in html.splitlines():
        if "environmentId" in line:
            assert "col." not in line and 'collection("items")' not in line, line


def test_d0040_ac20_prompt_prefix_checked():
    """D0042-AC-20: 送る言葉の先頭が「/pipe-in 」でなければ create_session を呼ばない。送る言葉は textarea で編集できる。"""
    html = read(BOARD)
    assert 'startsWith("/pipe-in ")' in fn(html, "promptOk")
    body = fn(html, "createSession")
    assert body.index("promptOk(") < body.index("callTool")
    assert re.search(r'<textarea[^>]*id="run-prompt"', html)


def test_d0040_ac21_create_input_fixed():
    """D0042-AC-21: create_session の入力は prompt・source_url（REPO）・environment_id・title で、permission_mode・model・--auto・--artifact はボードのどこにも無い。"""
    html = read(BOARD)
    body = fn(html, "createSession")
    for word in ("prompt", "source_url: REPO", "environment_id", "title"):
        assert word in body, word
    assert re.search(r"\b(?:permission_mode|model)\b", html) is None
    assert "--auto" not in html and "--artifact" not in html


def test_d0040_ac22_double_press_guarded():
    """D0042-AC-22: submit は creating で二重を止め、#run-go を無効にする。作った直後は justStarted、結果不明は uncertain で「実行」を止める。"""
    html = read(BOARD)
    submit = block_after(html, '$("run-form").addEventListener("submit"')
    assert "creating" in submit and "run-go" in submit and "disabled" in submit
    assert "justStarted" in html and "uncertain" in html
    assert "justStarted" in fn(html, "isRunning")
