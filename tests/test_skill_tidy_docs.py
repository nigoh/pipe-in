"""D0039：/pipe-in のスキルの整理に合わせた文書（CLAUDE.md・docs/）と決定の記録の検査。

読むだけで書かない（偽の文書は、文字列で組み立てる）。SDK は呼ばない。
定義・設定（.claude/）の検査は tests/test_skill_tidy.py、フックの判断が変わらないことの総当たりは tests/test_pipe_in_guard.py の末尾にある。

- 補助の関数（読む・見出しで節を切り出す）は tests/test_skill_tidy.py のものを使う（test_showcase.py が test_rules を import するのと同じ形）。
- 確認用のページの名前は、vscode/ を変えないので、vscode/scripts/previewPages.ts の PANEL_PAGES と preview.ts の PAGES を正規表現で読む。
- 今の作りのままで通るテストは、名前の末尾を _守る にし、説明の末尾に「（今のまま通る。守る）」と書く。
- 前の名前は、この文書に直接書かない（tests/test_rename.py の一覧に無いファイルなので）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from test_guide import heads_missing, panel_page_heads, table_decision_ids
from test_skill_tidy import SKILL_REL, lacking, need_section, read_doc, section_text

ROOT = Path(__file__).resolve().parents[1]
PREVIEW_TS = ROOT / "vscode" / "scripts" / "preview.ts"
PAGES_TS = ROOT / "vscode" / "scripts" / "previewPages.ts"
ASSETS_README = ROOT / "docs" / "assets" / "README.md"
CLAUDE_MD = ROOT / "CLAUDE.md"
DESIGN_MD = ROOT / "docs" / "development" / "design.md"
WORKFLOW_MD = ROOT / "docs" / "development" / "workflow.md"
TESTING_MD = ROOT / "docs" / "development" / "testing.md"
DEVELOP_MD = ROOT / "docs" / "guide" / "develop.md"
DECISIONS = ROOT / "docs" / "decisions"
DECISIONS_README = DECISIONS / "README.md"
RECORD = DECISIONS / "D0039-skill-tidy.md"
SCREEN_CHECK = ROOT / ".claude" / "skills" / "pipe-in" / "screen-check.md"


# ---- 確認用のページの名前（previewPages.ts と preview.ts から読む） ----------------------------------------


def panel_page_names(ts: str) -> list[str]:
    """previewPages.ts の PANEL_PAGES のページ名（完全な名前）。無ければ空。"""
    m = re.search(r"export const PANEL_PAGES\b[^=]*=\s*\[(.*?)\n\];", ts, re.S)
    return re.findall(r"\[\s*'(run-panel[\w-]*)'\s*,\s*'(?:light|dark)'\s*\]", m.group(1)) if m else []


def editor_page_names(ts: str) -> list[str]:
    """preview.ts の PAGES（作業台のページ。export されない）のページ名。無ければ空。"""
    m = re.search(r"\bconst PAGES\b[^=]*=\s*\[(.*?)\n\];", ts, re.S)
    return re.findall(r"\[\s*'(pipe-editor[\w-]*)'", m.group(1)) if m else []


def real_full_names() -> set[str]:
    """実在するページの完全な名前（PANEL_PAGES と PAGES の名前そのもの）。"""
    return set(panel_page_names(read_doc(PAGES_TS))) | set(editor_page_names(read_doc(PREVIEW_TS)))


def real_heads() -> set[str]:
    """ページの種類の頭（panel_page_heads の戻りと pipe-editor）。"""
    return set(panel_page_heads(read_doc(PAGES_TS))) | {"pipe-editor"}


PAGE_TOKEN = re.compile(r"(?:run-panel|pipe-editor)(?:-[a-z]+)*")


def page_tokens(text: str) -> list[str]:
    """文から取り出したページ名らしい語。run-panel-stale-* は run-panel-stale（頭）、run-panel-light.html は run-panel-light（完全な名前）。"""
    return PAGE_TOKEN.findall(text)


def full_names_in(line: str, full: set[str]) -> list[str]:
    return [t for t in page_tokens(line) if t in full]


def crowded_lines(text: str, full: set[str], *, only=None) -> list[str]:
    """1 行に完全なページ名が 2 つ以上並ぶ行（行の番号つき）。only があれば、それが真を返す行だけを見る（番号は text 全体の行の番号のまま）。"""
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        if only is not None and not only(line):
            continue
        names = full_names_in(line, full)
        if len(names) >= 2:
            out.append(f"{no} 行目に完全なページ名が {len(names)} 個並ぶ：{names}")
    return out


def unknown_tokens(text: str, full: set[str], heads: set[str]) -> list[str]:
    """完全な名前にも頭にも「等しくない」語（頭 ＋ - で始まる、とは見ない。run-panel-old-light のような実在しない名前まで通ってしまうため）。"""
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        out += [f"{no} 行目の {t}" for t in page_tokens(line) if t not in full and t not in heads]
    return out


def row_starting(md: str, lead: str) -> str | None:
    return next((line for line in md.splitlines() if line.startswith(lead)), None)


def need_row(md: str, lead: str, where: str) -> str:
    row = row_starting(md, lead)
    if row is None:
        pytest.fail(f"{where} に「{lead}」で始まる行が無い", pytrace=False)
    return row


def must_contain(text: str, word: str, where: str) -> None:
    """語が無ければ、長い本文を出さずに「無い」でそのテストだけを落とす。"""
    if word not in text:
        pytest.fail(f"{where} に「{word}」が無い", pytrace=False)


# ---- AC-15：一覧の持ち場は docs/assets/README.md（作業台のページも） ----------------------------------------

EDITOR_PAGES = ["pipe-editor-dark", "pipe-editor-light", "pipe-editor-diagrams"]


def editor_names_missing(readme: str, names: list[str]) -> list[str]:
    """README に <名前>.html の形で出てこない作業台のページ。.png の名前だけでは満たしたことにしない。"""
    return [n for n in names if f"{n}.html" not in readme]


def test_D0039_AC_15_作業台のページ名はpreview_tsのPAGESから3つ読める_守る():
    """D0039-AC-15: 作業台のページ名は export されない PAGES にあり、正規表現で読むと pipe-editor-dark・pipe-editor-light・pipe-editor-diagrams の 3 つ。
    （vscode/ は変えないので、ここで見張る。今のまま通る。守る）"""
    assert editor_page_names(read_doc(PREVIEW_TS)) == EDITOR_PAGES


def test_D0039_AC_15_assetsのREADMEに作業台の3ページがhtml付きで出る():
    """D0039-AC-15: docs/assets/README.md に、preview.ts の PAGES の作業台のページ（pipe-editor-diagrams を含む 3 つ）が <名前>.html の形で全部書かれている
    （D0025-AC-79 のテストは通ったまま）。"""
    names = editor_page_names(read_doc(PREVIEW_TS))
    assert names, "preview.ts から PAGES のページ名が読めない"
    assert editor_names_missing(read_doc(ASSETS_README), names) == []


def test_D0039_AC_15_見本_食い違いを見つける検査そのものは_png_だけでは満たしたことにしない_守る():
    """D0039-AC-15: 検査そのものの確かめ。PAGES に 4 つ目を足した見本は 4 つ目を欠けとして返し、README に .png の名前だけがあるページは満たしたことにしない。
    PAGES が読めない（名前が 0 件）ときは空を返す。（今のまま通る。守る）"""
    ts = (
        "const PAGES: [string, X, Theme][] = [\n"
        "  ['pipe-editor-dark', f('a', 1, {}, null), 'dark'],\n"
        "  ['pipe-editor-light', f('a', 1, {}, null), 'light'],\n"
        "  ['pipe-editor-diagrams', f('b', g(h('x'), 'u'), p, null), 'dark'],\n"
        "  ['pipe-editor-new', f('c', 1, {}, null), 'dark'],\n"
        "];\nfor (const [page] of PANEL_PAGES) {}\n"
    )
    names = editor_page_names(ts)
    assert names == [*EDITOR_PAGES, "pipe-editor-new"]
    readme = "`pipe-editor-dark.html`・`pipe-editor-light.html`・`pipe-editor-diagrams.png`"
    assert editor_names_missing(readme, names) == ["pipe-editor-diagrams", "pipe-editor-new"]
    assert editor_names_missing(readme + "・`pipe-editor-diagrams.html`・`pipe-editor-new.html`", names) == []
    assert editor_page_names("const X = 1;") == []


# ---- AC-16：CLAUDE.md と design.md の行は、個々のページ名を並べない ------------------------------------------


def test_D0039_AC_16_CLAUDEのnpm_run_previewの行は完全なページ名を並べず_種類の頭と_assets_README_を指す():
    """D0039-AC-16: CLAUDE.md の npm run preview の行は、完全なページ名を 2 つ以上並べず、種類の頭 run-panel-* が残り、docs/assets/README.md を指す
    （D0009-AC-19 の CLAUDE.md の部分が通ったまま）。"""
    md = read_doc(CLAUDE_MD)
    is_preview = lambda line: "npm run preview" in line  # noqa: E731
    lines = [line for line in md.splitlines() if is_preview(line)]
    assert lines, "CLAUDE.md に「npm run preview」の行が無い"
    problems = [f"CLAUDE.md の {p}" for p in crowded_lines(md, real_full_names(), only=is_preview)]
    problems += [f"「{w}」が無い" for w in lacking("\n".join(lines), ("run-panel-*", "docs/assets/README.md"))]
    assert problems == []


def test_D0039_AC_16_designの画面の確認用のページの行は完全なページ名を並べず_README_を指し_作り方は残す():
    """D0039-AC-16: docs/development/design.md の置き場所の表の「画面の確認用のページ」の行は、完全なページ名を 2 つ以上並べず、docs/assets/README.md を指し、
    ページを作るコードの場所（vscode/scripts/preview.ts・previewPages.ts・artifactSamples.ts）は残す。"""
    md = read_doc(DESIGN_MD)
    row = need_row(md, "| 画面の確認用のページ", "docs/development/design.md")
    problems = [f"docs/development/design.md の {p}" for p in crowded_lines(md, real_full_names(), only=lambda line: line.startswith("| 画面の確認用のページ"))]
    problems += [f"「{w}」が無い" for w in lacking(row, ("docs/assets/README.md", "vscode/scripts/preview.ts", "previewPages.ts", "artifactSamples.ts"))]
    assert problems == []


def test_D0039_AC_16_見本_完全なページ名を数える関数は2つ並んだ行を見つけ_頭は数えない_守る():
    """D0039-AC-16: 検査そのものの確かめ。完全なページ名が 2 つ並んだ行は見つけ、run-panel-*・run-panel-stale-*・pipe-editor-* のような頭と、
    1 つだけの行は数えない。（今のまま通る。守る）"""
    full = {"run-panel-light", "run-panel-dark", "pipe-editor-dark"}
    assert len(crowded_lines("`run-panel-light.html`・`run-panel-dark.html`", full)) == 1
    assert crowded_lines("`run-panel-light.html` と `pipe-editor-dark.html`", full) != []
    assert crowded_lines("`run-panel-*`・`run-panel-stale-*`・`pipe-editor-*`・`run-panel-artifacts-<テーマ>`", full) == []
    assert crowded_lines("`run-panel-light.html` だけ\n`run-panel-dark.html` だけ", full) == []
    assert full_names_in("run-panel-stale-*.html", full) == []
    # 行の番号は文書全体の番号で出る（only で絞っても 1 行目にならない）
    doc = "見出し\n`run-panel-light.html`・`run-panel-dark.html`\n別の行\n`run-panel-light.html`・`pipe-editor-dark.html`\n"
    assert [p.split(" ")[0] for p in crowded_lines(doc, full)] == ["2", "4"]
    assert [p.split(" ")[0] for p in crowded_lines(doc, full, only=lambda line: "pipe-editor" in line)] == ["4"]


# ---- AC-17：screen-check.md は、ページの完全な名前を一覧にして並べない -----------------------------------------


def test_D0039_AC_17_screen_check_md_の1行に完全なページ名が2つ以上並ばない():
    """D0039-AC-17: screen-check.md は、ページの完全な名前（PANEL_PAGES と PAGES の名前そのもの）を一覧にして並べない
    （1 行に 2 つ以上並ばない。ページの種類は頭の形で書き、一覧は docs/assets/README.md と指す）。"""
    assert crowded_lines(read_doc(SCREEN_CHECK), real_full_names()) == []


def test_D0039_AC_17_screen_check_md_に出るページ名は実在するページか種類の頭に等しい():
    """D0039-AC-17: screen-check.md に出る run-panel-… と pipe-editor-… の名前は、実在するページ（PANEL_PAGES か PAGES）か、その種類の頭に等しい
    （ページを足したり名前を変えたりして手順が古くなったときに落ちる）。"""
    assert unknown_tokens(read_doc(SCREEN_CHECK), real_full_names(), real_heads()) == []


README_POINTER = "docs/assets/README.md"


def screen_check_problems(text: str, heads) -> list[str]:
    """screen-check.md が、ページの種類の頭を全部（頭の形で）書き、一覧の持ち場を指しているかの問題。
    頭の形とは、頭のあとに -light・-dark・-*・-<…>・.html が続く形（test_guide.heads_missing と同じ。run-panel-stale が run-panel-stale-soon-* だけで通らないように）。"""
    problems = [f"ページの種類の頭「{h}」が頭の形で出てこない" for h in heads_missing(text, sorted(heads))]
    if README_POINTER not in text:
        problems.append(f"一覧の持ち場「{README_POINTER}」を指していない")
    return problems


def test_D0039_AC_17_screen_check_md_にページの種類の頭が全部あり_一覧はREADMEを指す():
    """D0039-AC-17: screen-check.md に、ページの種類の頭（panel_page_heads() の戻りの 8 つと pipe-editor。件数は固定しない）が、それぞれ頭の形で 1 回以上出て、
    一覧は docs/assets/README.md と指す（完全な名前を並べない代わりに、種類を書き落とさない。成果物のタブの run-panel-artifacts を確かめる手順も、ここで守る）。"""
    heads = real_heads()
    assert len(heads) >= 2, "previewPages.ts から PANEL_PAGES の頭が読めない"
    assert screen_check_problems(read_doc(SCREEN_CHECK), heads) == []


def test_D0039_AC_17_見本_頭が1つ欠けた手順はその頭を返し_README_の指しが無い手順も見つける_守る():
    """D0039-AC-17: 検査そのものの確かめ。頭がそろい README を指す手順は問題なし。run-panel-artifacts の頭を消した手順はその頭だけを欠けとして返す。
    run-panel-stale-* を消して run-panel-stale-soon-* だけが残る手順は run-panel-stale を欠けとして返す（頭を部分文字列で探すと隠れる）。
    README の指しが無い手順も見つける。（今のまま通る。守る）"""
    heads = {"pipe-editor", "run-panel", "run-panel-stale", "run-panel-stale-soon", "run-panel-artifacts"}
    good = "`pipe-editor-*`・`run-panel-*`・`run-panel-stale-*`・`run-panel-stale-soon-*`・`run-panel-artifacts-<テーマ>`。一覧は `docs/assets/README.md`。"
    assert screen_check_problems(good, heads) == []
    assert screen_check_problems(good.replace("・`run-panel-artifacts-<テーマ>`", ""), heads) == ["ページの種類の頭「run-panel-artifacts」が頭の形で出てこない"]
    assert screen_check_problems(good.replace("`run-panel-stale-*`・", ""), heads) == ["ページの種類の頭「run-panel-stale」が頭の形で出てこない"]
    assert screen_check_problems(good.replace("`docs/assets/README.md`", "README"), heads) == [f"一覧の持ち場「{README_POINTER}」を指していない"]
    assert len(screen_check_problems("", heads)) == len(heads) + 1


def test_D0039_AC_17_見本_実在しない名前と並びを見つけ_種類の頭は見逃さない_守る():
    """D0039-AC-17: 検査そのものの確かめ。run-panel-old-light・run-panel-old-*・頭に - を足しただけの名前は実在しないと見つけ、1 行に 2 つ並んだ行も見つける。
    run-panel-stale-*・run-panel-artifacts-<テーマ>・pipe-editor-*・実在する完全な名前は見逃す。（今のまま通る。守る）"""
    full = {"run-panel-light", "run-panel-stale-light", "run-panel-artifacts-light", "pipe-editor-dark"}
    heads = {"run-panel", "run-panel-stale", "run-panel-artifacts", "pipe-editor"}
    assert len(unknown_tokens("`run-panel-old-light`・`run-panel-old-*`", full, heads)) == 2
    assert unknown_tokens("`run-panel-stale-light-old`", full, heads) != []
    assert unknown_tokens("`run-panel-stale-*`・`run-panel-artifacts-<テーマ>`・`pipe-editor-*`・`run-panel-light.html`", full, heads) == []
    assert crowded_lines("`run-panel-light`・`run-panel-stale-light`", full) != []
    assert crowded_lines("`run-panel-stale-*`・`run-panel-artifacts-*`", full) == []


# ---- AC-24・AC-32：決定の記録の本体（検証の前に、メインが書く） --------------------------------------------------


@pytest.mark.parametrize(
    "word",
    [
        pytest.param("フックで守らない", id="not-by-hook"),
        pytest.param("hooks:", id="skill-front-matter-hooks"),
        pytest.param("別のイシュー", id="another-issue"),
    ],
)
def test_D0039_AC_24_決定の記録にフックで守らないと決めたことと代わりの手立てがある(word):
    """D0039-AC-24: 決定の記録 D0039 に、フックで守らないと決めたこと（フックで守らない）・スキルの前置きのフックでも同じこと（hooks:）・
    代わりの手立て（記録の順序の検査は別のイシュー）が書いてある。"""
    must_contain(read_doc(RECORD), word, "docs/decisions/D0039-skill-tidy.md")


@pytest.mark.parametrize(
    "word",
    [
        pytest.param("settings.local.json", id="settings-local-json"),
        pytest.param("受け入れたリスク", id="accepted-risk"),
        pytest.param("record:*", id="record-wide-rule"),
        pytest.param("--input", id="input-flag"),
        pytest.param("--project", id="project-flag"),
        pytest.param("読み忘れ", id="risk-forget-to-read"),
        pytest.param("つないだ", id="risk-chained-command"),
        pytest.param("3 か所", id="risk-three-places"),
    ],
)
def test_D0039_AC_32_決定の記録にallowを足した理由と受け入れたリスクがある(word):
    """D0039-AC-32: 決定の記録 D0039 に、足した理由・受け入れたリスク（settings.local.json・受け入れたリスク・record:*・--input・--project）と、
    受け入れたリスク 4 種の書き忘れを見る言葉（読み忘れ・つないだ・3 か所）が書いてある。"""
    must_contain(read_doc(RECORD), word, "docs/decisions/D0039-skill-tidy.md")


# ---- AC-33〜36：文書をそろえる -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "word",
    [
        pytest.param("補助ファイル", id="helper-files"),
        pytest.param("必ず守ること", id="must-section"),
        pytest.param("読み直", id="reread"),
        pytest.param("`ask`", id="ask"),
        pytest.param("settings.local.json", id="settings-local-json"),
        pytest.param("新しい worktree", id="new-worktree"),
    ],
)
def test_D0039_AC_33_developの許可の規則の節にスキルの構成と許可の説明がある(word):
    """D0039-AC-33: docs/guide/develop.md の「Claude Code で開発するとき」に、見出しに「許可の規則」を含む節があり、スキルの構成（補助ファイル・必ず守ること・読み直）と
    許可の規則（`ask`・個人の許可は settings.local.json・新しい worktree では allow が効かないことがある）が書いてある。「フックが働く条件」の節は変えない。
    `ask` はバッククォートつきで探す（task・basket の中の ask で満たさない。AC-34・36 と同じ）。"""
    body = need_section(read_doc(DEVELOP_MD), "許可の規則", where="docs/guide/develop.md")
    must_contain(body, word, "docs/guide/develop.md の「許可の規則」の節")


def test_D0039_AC_34_workflowの進める節にスキルの構成を一文で書く():
    """D0039-AC-34: docs/development/workflow.md の「2. 進める」に、スキルが「決まりを冒頭・長い手順を補助ファイル」にしていることを書く（補助ファイル）。"""
    body = need_section(read_doc(WORKFLOW_MD), "2. 進める", where="docs/development/workflow.md", depth=2)
    must_contain(body, "補助ファイル", "docs/development/workflow.md の「2. 進める」の節")


def test_D0039_AC_34_workflowの終える節の7にgit_commit_merge_pushがaskであることを書く():
    """D0039-AC-34: docs/development/workflow.md の「5. 終える」の 7 の行に、git commit・git merge・git push が `ask` であること（個人の設定で許可していても確認が出る）を書く。"""
    body = need_section(read_doc(WORKFLOW_MD), "5. 終える", where="docs/development/workflow.md", depth=2)
    sevens = [line for line in body.splitlines() if line.startswith("7. ")]
    assert sevens, "「5. 終える」に 7 で始まる行が無い"
    assert lacking(sevens[0], ("`ask`", "git commit", "git merge", "git push")) == [], sevens[0]


def test_D0039_AC_34_testingの画面の行の案内はscreen_check_mdを指す():
    """D0039-AC-34: docs/development/testing.md の画面の行の「`/pipe-in` の「5. 検証」」が screen-check.md を指す形に直る。"""
    row = need_row(read_doc(TESTING_MD), "| 画面 |", "docs/development/testing.md")
    assert "screen-check.md" in row, row
    assert "「5. 検証」" not in row, row


def test_D0039_AC_35_designのスキルの行に補助ファイルのパスがある():
    """D0039-AC-35: docs/development/design.md の置き場所の表の「このリポジトリを開発する Claude Code のスキル」の行に、
    .claude/skills/pipe-in/ の補助ファイル（record.md・artifact.md・screen-check.md）のパスを書く（パスが実在するかは tests/test_rules.py が見る）。"""
    row = need_row(read_doc(DESIGN_MD), "| このリポジトリを開発する Claude Code のスキル", "docs/development/design.md")
    assert lacking(row, (f"{SKILL_REL}record.md", f"{SKILL_REL}artifact.md", f"{SKILL_REL}screen-check.md")) == [], row[:120]


def test_D0039_AC_36_CLAUDEのnpm_run_previewの行は一覧と手順の置き場所を指す():
    """D0039-AC-36: CLAUDE.md の「コマンド」の npm run preview の行は短くなり、一覧と撮り直しは docs/assets/README.md、手順は screen-check.md を指す。"""
    lines = [line for line in read_doc(CLAUDE_MD).splitlines() if "npm run preview" in line]
    assert lines, "CLAUDE.md に「npm run preview」の行が無い"
    assert lacking("\n".join(lines), ("docs/assets/README.md", "screen-check.md")) == []


def test_D0039_AC_36_CLAUDEのコミットの決まりにaskで確認が出ることを足す():
    """D0039-AC-36: CLAUDE.md の「必ず守ること」の「コミット・push は人に言われるまでしない」の行に、`ask` で確認が出ることを足す。"""
    lines = [line for line in read_doc(CLAUDE_MD).splitlines() if "人に言われるまで" in line]
    assert lines, "CLAUDE.md に「人に言われるまで」の行が無い"
    assert any("`ask`" in line for line in lines), lines


def test_D0039_AC_36_CLAUDEにスキルの構成を1文で足す():
    """D0039-AC-36: CLAUDE.md に、スキルの構成（決まりを冒頭・長い手順を補助ファイル）を 1 文で足す（補助ファイルを含む行に record.md と screen-check.md）。"""
    lines = [line for line in read_doc(CLAUDE_MD).splitlines() if "補助ファイル" in line]
    assert lines, "CLAUDE.md に「補助ファイル」を含む行が無い"
    assert any(not lacking(line, ("record.md", "screen-check.md")) for line in lines), lines


# ---- AC-37：assets の README を、確認用のページの一覧の持ち場にする ---------------------------------------------

LIST_TITLE = "確認用のページの一覧"
PAGE_FORM = r"(?:-(?:light|dark|\*|<[^>\n]*>)|\.html)"  # test_guide.heads_missing と同じ：頭のあとに -light・-dark・-*・-<…>・.html が続く形


def marks_missing(readme: str, names: list[str]) -> list[str]:
    """見出し「確認用のページの一覧」の節の表（| で始まる行）で、名前が出る行が無い、または、出る行のどれかに「撮」（撮る・撮らない）が無い名前。
    頭を部分文字列で探すと、run-panel-stale が run-panel-stale-soon-dark.html の中に出るだけで隠れてしまうので、頭のあとの形で探す。"""
    table = section_text(readme, LIST_TITLE, depth=2) or ""
    rows = [line for line in table.splitlines() if line.startswith("|")]
    out = []
    for name in names:
        pattern = re.compile(re.escape(name) + PAGE_FORM)
        hits = [row for row in rows if pattern.search(row)]
        if not hits or any("撮" not in row for row in hits):
            out.append(name)
    return out


def test_D0039_AC_37_assetsのREADMEに作業台の3ページがhtml付きで書かれている():
    """D0039-AC-37: docs/assets/README.md に、作業台の 3 ページ（pipe-editor-dark・pipe-editor-light・pipe-editor-diagrams）が .html つきで書かれている。"""
    assert editor_names_missing(read_doc(ASSETS_README), EDITOR_PAGES) == []


def test_D0039_AC_37_確認用のページの一覧の表で_どのページの種類の行にも画像に撮るかが書かれている():
    """D0039-AC-37: docs/assets/README.md の見出し「確認用のページの一覧」の節の表に、PANEL_PAGES の各ページの種類の頭（件数は固定しない）と作業台の 3 ページが出る行が
    1 つ以上あり、そのすべての行に、画像に撮るか（撮）が書かれている。D0025-AC-78 の「画像には撮らない」の一言（run-panel-artifacts と 撮ら が同じ行）は残る。"""
    heads = panel_page_heads(read_doc(PAGES_TS))
    assert heads, "previewPages.ts から PANEL_PAGES のページ名が読めない"
    assert marks_missing(read_doc(ASSETS_README), [*heads, *EDITOR_PAGES]) == []


def test_D0039_AC_37_見本_撮るかの無い行を見つけ_表が無いREADMEは全部を欠けとして返す_守る():
    """D0039-AC-37: 検査そのものの確かめ。run-panel-stale の行に「撮」が無く、run-panel-stale-soon の行にだけある README は run-panel-stale を欠けとして返す
    （頭を部分文字列で探すと隠れる）。表が無い README・節だけで表が無い README は全部の名前を欠けとして返し、全部の行に「撮」がある README は欠け 0 件。
    （今のまま通る。守る）"""
    names = ["run-panel-stale", "run-panel-stale-soon", "pipe-editor-dark"]
    good = (
        f"## {LIST_TITLE}\n\n| ページ | 見るもの | 画像に撮るか |\n| --- | --- | --- |\n"
        "| `run-panel-stale-light.html` | 印 | 撮らない |\n"
        "| `run-panel-stale-soon-dark.html` | 目安の手前の印 | 撮らない |\n"
        "| `pipe-editor-dark.html` | 作業台 | 撮る：`pipe-editor-dark.png` |\n"
    )
    assert marks_missing(good, names) == []
    bad = good.replace("| `run-panel-stale-light.html` | 印 | 撮らない |", "| `run-panel-stale-light.html` | 印 | 写さない |")
    assert marks_missing(bad, names) == ["run-panel-stale"]
    assert marks_missing("", names) == names
    assert marks_missing(f"## {LIST_TITLE}\n\n本文だけ\n", names) == names
    elsewhere = good.replace(f"## {LIST_TITLE}", "## 別の節")
    assert marks_missing(elsewhere, names) == names


# ---- AC-38：決定の記録の形と、AC の行 ------------------------------------------------------------------------

AC_COUNT = 42
# 手で・実機で確かめる AC（行に結果の言葉が要る）
HAND_OR_REAL = {26, 30, 31, 39, 40, 41, 42}
RESULT_WORDS = ("確かめていない", "確かめた", "まだ", "未起票")
AC30_WORDS = ("入れたまま", "残す", "外す")


def ac_lines(text: str) -> dict[int, str]:
    """AC の行（先頭の - と空白を除いて D0039-AC-NN で始まる行。NN は 2 けた）を、番号 → 行にする。"""
    out: dict[int, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("- "):
            s = s[2:].lstrip()
        m = re.match(r"D0039-AC-(\d{2})(?!\d)", s)
        if m:
            out.setdefault(int(m.group(1)), s)
    return out


def ac_line_problems(text: str) -> list[str]:
    """手で・実機の AC の行に結果の言葉（AC-30 はさらに入れたまま・残す・外す）が無い、それ以外の AC の行にテストの名前（test_ か tests/）が無い、
    AC の行が無い、を返す（docs/development/specs.md の「AC には、確かめたテストの名前を添える」）。"""
    lines = ac_lines(text)
    problems = []
    for n in range(1, AC_COUNT + 1):
        line = lines.get(n)
        if line is None:
            problems.append(f"AC-{n:02d} の行が無い")
        elif n in HAND_OR_REAL:
            if not any(w in line for w in RESULT_WORDS):
                problems.append(f"AC-{n:02d}（手で・実機）の行に結果の言葉（{'・'.join(RESULT_WORDS)}）が無い")
            if n == 30 and not any(w in line for w in AC30_WORDS):
                problems.append("AC-30 の行に 入れたまま・残す・外す のどれかが無い")
        elif "test_" not in line and "tests/" not in line:
            problems.append(f"AC-{n:02d} の行にテストの名前（test_ か tests/）が無い")
    return problems


def test_D0039_AC_38_決定の記録は1つで_1行目が題_守る():
    """D0039-AC-38: docs/decisions/ に D0039-<名前>.md が 1 つあり、1 行目が「# D0039 <題>」。形は tests/test_rules.py が見る。（骨組みで通る。守る）"""
    found = sorted(DECISIONS.glob("D0039-*.md"))
    assert [p.name for p in found] == ["D0039-skill-tidy.md"]
    assert found[0].read_text(encoding="utf-8").startswith("# D0039 ")


def test_D0039_AC_38_決定の記録にAC_01から42の行がある_守る():
    """D0039-AC-38: 決定の記録に D0039-AC-01 から D0039-AC-42 の行が 1 つずつある。（骨組みで通る。守る）"""
    assert sorted(ac_lines(read_doc(RECORD))) == list(range(1, AC_COUNT + 1))


def test_D0039_AC_38_決定の記録の表にD0039の行があり_前の行は小さい番号のうち最大_守る():
    """D0039-AC-38: docs/decisions/README.md の表に D0039 の行があり、表の番号は昇順で、D0039 の行の前の行は D0039 より小さい番号のうち最大のもの
    （前の番号を決め打ちしない。D0034 の記録の検査と同じ考え方）。行はファイルを指す。（骨組みで通る。守る）"""
    md = read_doc(DECISIONS_README)
    ids = [int(i[1:]) for i in table_decision_ids(md)]
    assert 39 in ids, f"決定の記録の表に D0039 の行が無い（今の行：{ids[-6:]}）"
    assert ids == sorted(ids), f"表の番号が昇順でない：{ids}"
    at = ids.index(39)
    smaller = [i for i in ids if i < 39]
    assert at > 0 and ids[at - 1] == max(smaller), f"D0039 の行の前の行が、39 より小さい番号のうち最大でない（今の並び：{ids[-6:]}）"
    row = next(line for line in md.splitlines() if line.startswith("| [D0039]"))
    assert "D0039-skill-tidy.md" in row, row


@pytest.mark.parametrize(
    "word",
    [
        pytest.param("D0025-AC-77", id="replaced-d0025-ac77"),
        pytest.param("D0025-AC-78", id="replaced-d0025-ac78"),
        pytest.param("D0009-AC-19", id="replaced-d0009-ac19"),
        pytest.param("D0027-AC-76", id="replaced-d0027-ac76"),
        pytest.param("置き換える", id="word-replace"),
        pytest.param("受け入れたリスク", id="word-accepted-risk"),
        pytest.param("別のイシュー", id="word-another-issue"),
        pytest.param("isolation", id="issue-isolation-deny"),
        pytest.param("exec 形", id="issue-exec-form"),
        pytest.param("onFailure", id="issue-front-matter-onfailure"),
        pytest.param("記録の順序", id="issue-record-order-check"),
        pytest.param("/pipe-dev", id="issue-pipe-dev-wording"),
        pytest.param("止めた理由", id="issue-guard-reason-sentence"),
        pytest.param("確かめていない", id="word-not-checked"),
        pytest.param("D0033", id="base-red-d0033"),
    ],
)
def test_D0039_AC_38_決定の記録の本体に置き換えるACと残した課題の言葉がある(word):
    """D0039-AC-38: 決定の記録に、置き換える AC（D0025-AC-77・D0025-AC-78・D0009-AC-19・D0027-AC-76 と「置き換える」）・受け入れたリスク・別のイシューにした項目
    （Agent の 8 行と isolation の deny・exec 形・前置きの onFailure・record の幅広い規則は AC-32 の record:*・記録の順序の検査・本体の /pipe-dev の文言・pipe_in_guard.py の止めた理由の文。
    AC-39 で人にイシューに立てるかを聞く材料）・確かめていないこと・ベースの赤（D0033）の扱いが書いてある。"""
    must_contain(read_doc(RECORD), word, "docs/decisions/D0039-skill-tidy.md")


def test_D0039_AC_38_決定の記録のACの行にテストの名前か結果の言葉がある():
    """D0039-AC-38: AC の行のうち、手で・実機の AC（26・30・31・39・40・41・42）は確かめていない・確かめた・まだ・未起票のどれかを含み（AC-30 はさらに入れたまま・残す・外すのどれか）、
    それ以外の AC の行はテストの名前（test_ か tests/）を含む（骨組みは AC の ID だけなので、本体を書くまで赤）。"""
    problems = ac_line_problems(read_doc(RECORD))
    assert problems == [], "\n" + "\n".join(problems)


def test_D0039_AC_38_見本_語の無い偽の記録はそのACを欠けとして返す_守る():
    """D0039-AC-38: 検査そのものの確かめ。語の無い骨組みだけの記録は全部の AC を、結果の言葉の無い手で・実機の AC の行・入れたまま・残す・外すの無い AC-30 の行・
    テストの名前の無い AC の行・行そのものが無い AC を欠けとして返し、そろった記録は欠け 0 件。（今のまま通る。守る）"""

    def fake(drop: set[int] = frozenset(), strip: set[int] = frozenset()) -> str:
        rows = []
        for n in range(1, AC_COUNT + 1):
            if n in drop:
                continue
            if n in HAND_OR_REAL:
                text = "（手で）まだ確かめていない" + ("。規則は入れたまま" if n == 30 else "")
            else:
                text = "確かめたテスト：tests/test_x.py::test_D0039_AC_01"
            rows.append(f"  - D0039-AC-{n:02d} 題。" + ("" if n in strip else text))
        return "\n".join(rows) + "\n"

    assert ac_line_problems(fake()) == []
    skeleton = "\n".join(f"  - D0039-AC-{n:02d}" for n in range(1, AC_COUNT + 1))
    assert len(ac_line_problems(skeleton)) == AC_COUNT + 1  # 全部の AC と、AC-30 の追加の言葉
    assert [p[:5] for p in ac_line_problems(fake(strip={1, 26}))] == ["AC-01", "AC-26"]
    only_checked = fake().replace("。規則は入れたまま", "")
    assert ac_line_problems(only_checked) == ["AC-30 の行に 入れたまま・残す・外す のどれかが無い"]
    assert ac_line_problems(fake(drop={42})) == ["AC-42 の行が無い"]
    assert ac_line_problems("") == [f"AC-{n:02d} の行が無い" for n in range(1, AC_COUNT + 1)]
