"""D0049：実行の詳細の「エージェント・スキル」のタブに合わせた文書の検査（AC-47〜51）。

文書は読むだけで書かない（偽の文書は文字列で組み立てる）。SDK は呼ばない。
補助の関数（節の取り出し・言葉の探し方・表の行・番号の取り出し・ページ名の頭）は tests/test_guide.py と tests/test_skill_tidy_docs.py のものを使う
（test_skill_tidy_docs.py が test_guide を import するのと同じ形）。
拡張のコードの検査は vscode/src/**/*.test.ts（node:test）にある。ここは文書の文字を読む検査だけ（D0025・D0039 の前例がすべて Python）。

探す言葉の表と古い文の一覧は、実装の段が文書を書く目標にする（言葉は決定の記録 docs/decisions/D0049-run-tools.md の AC-47 の列挙に合わせた。言い方は書く人が決める）。
検査そのもの（節の取り出し・言葉の探し方・古い文の見つけ方・文の行・番号の順）は、偽の文書で確かめる。そちらは今のまま通る（名前の末尾を _守る にし、説明の末尾に「（今のまま通る。守る）」と書いた）。
`.claude/skills/pipe-in/screen-check.md` の確認用ページの手順（AC-50）は、実装の段のあとにメインが足した。決定の記録の本体（AC-51 の「記録の本体」のテスト）は、文書係が書けない（docs/decisions/）ので、メインが書くまで赤のまま残る（既知の赤）。
`docs/decisions/README.md` の D0049 の行と決定の記録の骨組みは、テスト先行の前にメインが置いた（AC-51 の骨組みのテストは通る）。
"""

from __future__ import annotations

import re

import pytest

from test_guide import (
    DESIGN_DOC,
    GUIDE,
    ROOT,
    VSCODE_README,
    heading_part,
    heads_missing,
    leftover_sentences,
    lines_with,
    numbered_bullets,
    panel_page_heads,
    read_doc,
    row_starting,
    section,
    sentences_lacking,
    table_decision_ids,
    table_row,
    words_missing,
)
from test_skill_tidy_docs import crowded_lines, real_full_names

DECISIONS = ROOT / "docs" / "decisions"
DECISIONS_README = DECISIONS / "README.md"
ASSETS_README = ROOT / "docs" / "assets" / "README.md"
SCREEN_CHECK = ROOT / ".claude" / "skills" / "pipe-in" / "screen-check.md"
CLAUDE_MD = ROOT / "CLAUDE.md"
PAGES_TS = ROOT / "vscode" / "scripts" / "previewPages.ts"

TOOLS_TITLE = "エージェント・スキルのタブ"
TOOLS_HEAD = "run-panel-tools"
THREE_TABS = "「図と出力」「成果物」「使用量」"  # 詳細のタブが 3 つだった古い列挙（4 つの列挙は「成果物」と「使用量」のあいだにエージェント・スキルが入る）


def tools_part(md: str) -> str:
    """「実行を見る」の中の、見出しに「エージェント・スキルのタブ」を含む小見出し（### 以下）の節の本文。無ければ空。"""
    return heading_part(section(md, "実行を見る"), TOOLS_TITLE)


# ---- AC-47：ガイド（docs/guide/vscode.md）の新しい節の探す言葉 ------------------------------------------------

# （pytest の id, 何の説明か, 節の中を探す正規表現。すべてに合うこと）。言葉は決定の記録 D0049 の AC-47 の列挙に合わせる。
# 別々の項目を別の文の言葉で満たしてしまわないよう、2 つの言葉を結ぶものは 1 つの文の中で探す（[^。\n]* は句点と改行をまたがない）。
TOOLS_GUIDE_WORDS: list[tuple[str, str, tuple[str, ...]]] = [
    ("what", "何を数えるか：段のログの道具の呼び出しを、呼んだ回数で数える", (r"段のログ", r"呼び出し", r"呼んだ回数")),
    ("kinds", "3 つの種類：エージェント・スキル・道具", (r"種類", r"エージェント[^。\n]*スキル[^。\n]*道具")),
    ("nested", "サブエージェントの中の呼び出しは、同じ行に足す", (r"サブエージェントの中", r"同じ行")),
    ("blocked-failed", "止められた呼び出しも、失敗した呼び出しも数える（呼んだ回数）", (r"止められた", r"失敗した")),
    ("time-none", "道具ごとの時間はログに無い（時間とログの無さが同じ文にある）", (r"時間[^。\n]*ログ[^。\n]*(?:無い|ありません|残りません)",)),
    ("time-agent-row", "受け持ちの行だけ時間が出る", (r"受け持ち[^。\n]*時間|時間[^。\n]*受け持ち",)),
    ("agent-flag", "/pipe-in の記録：record begin --agent を付けた受け持ちだけが出て、付けないと出ない", (r"record begin --agent", r"付けない")),
    ("notice", "案内 A・B：呼び出しが記録に残らないこと、受け持ちも無いときは案内だけ", (r"案内", r"記録に残りません", r"出せるもの|案内だけ")),
    ("no-input", "入力の中身（コマンド・引数・ファイル名・プロンプト）は出さない", (r"入力の中身", r"出(?:ません|しません|さない)")),
    ("limits-rows", "表の 100 行の上限", (r"100 ?行",)),
    ("limits-stages", "使った段の 3 つの上限（使った段と 3 つが同じ文にある）", (r"使った段[^。\n]*3 ?つ",)),
    ("delay", "動いている SDK の段は、少し遅れて増える", (r"遅れ",)),
]
TOOLS_WORD = {sid: (sid, label, patterns) for sid, label, patterns in TOOLS_GUIDE_WORDS}

# ガイドの既存の文。（id, 文の頭の言葉, その文にある言葉）。頭の言葉は、今ある文の変えない前半
ALL_GUIDE_SENTENCES = [
    ("tabs-meta", "タブ「図と出力」", "エージェント・スキル"),
    ("tabs-detail", "下のタブは", "エージェント・スキル"),
    ("tabs-explain", "「成果物」は、左に成果物の一覧", "エージェント・スキル"),
    ("scroll-new", "それぞれ別にスクロール", "エージェント・スキル"),
    ("scroll-list", "それぞれ別にスクロール", "成果物の一覧"),
    ("scroll-preview", "それぞれ別にスクロール", "プレビュー"),
    ("keep-table", "描き直しがあっても、絞り込み", "表の枠"),
    ("hscroll-left", "横にスクロールした表やコードの位置は", "左端に戻"),
    ("hscroll-table", "横にスクロールした表やコードの位置は", "表の枠"),
]
# 既存の言葉を直したあとも残す文（今のまま通る。守る）。残りが、新しい言葉を足す文（今は無いので赤）
KEPT_SENTENCE_IDS = {"scroll-list", "scroll-preview", "hscroll-left"}
TOOLS_GUIDE_SENTENCES = [row for row in ALL_GUIDE_SENTENCES if row[0] not in KEPT_SENTENCE_IDS]
TOOLS_GUIDE_KEPT = [row for row in ALL_GUIDE_SENTENCES if row[0] in KEPT_SENTENCE_IDS]
# 古い文の全体：詳細のタブの 3 つの列挙
TOOLS_OLD_GUIDE = [("old-three-tabs", THREE_TABS)]
# 「横にスクロールした表やコードの位置は…左端に戻ります」の行に、この表の枠は戻らない、という区別
NOT_RETURN = r"戻(?:りません|らない|らず)"


def test_D0049_AC_47_ガイドの実行を見るの中にエージェントスキルのタブの節がある():
    """D0049-AC-47: docs/guide/vscode.md の「実行を見る」の中に、「エージェント・スキルのタブ」の見出し（### 以下）の節がある。"""
    md = read_doc(GUIDE / "vscode.md")
    titles = [title for depth, title in re.findall(r"^(#{3,6})\s+(.*)$", section(md, "実行を見る"), re.M)]
    assert tools_part(md), f"「実行を見る」の中に「{TOOLS_TITLE}」の節が無い（今ある小見出し：{titles}）"


@pytest.mark.parametrize("sid", [i for i, _, _ in TOOLS_GUIDE_WORDS])
def test_D0049_AC_47_ガイドのエージェントスキルのタブの節に説明がある(sid):
    """D0049-AC-47: 「エージェント・スキルのタブ」の節に、何を数えるか（段のログの道具の呼び出し・呼んだ回数）・3 つの種類・サブエージェントの中の呼び出しは同じ行に足すこと・
    止められた呼び出しと失敗した呼び出しも数えること・道具ごとの時間はログに無いこと・時間は受け持ちの行だけに出ること・record begin --agent を付けた受け持ちだけが出て付けないと出ないこと・
    案内 A と B・入力の中身は出さないこと・100 行の上限と使った段の 3 つの上限・動いている SDK の段は少し遅れて増えること、が書いてある（探す言葉の表の 1 項目ずつ）。"""
    part = tools_part(read_doc(GUIDE / "vscode.md"))
    _, label, patterns = TOOLS_WORD[sid]
    assert part, f"docs/guide/vscode.md に「{TOOLS_TITLE}」の節が無い"
    assert sid not in words_missing(part, [TOOLS_WORD[sid]]), f"「{TOOLS_TITLE}」の節に、{label} の説明が無い（探した形：{patterns}）"


@pytest.mark.parametrize("sid,lead,word", TOOLS_GUIDE_SENTENCES, ids=[i for i, _, _ in TOOLS_GUIDE_SENTENCES])
def test_D0049_AC_47_ガイドの既存の文にエージェントスキルのタブが書いてある(sid, lead, word):
    """D0049-AC-47: docs/guide/vscode.md の既存の文を直す：詳細のタブの列挙が 4 つ（「実行を見る」の右の詳細の行・「下のタブは」の行・「成果物」「使用量」の説明の行）、
    「それぞれ別にスクロール」の行にエージェント・スキル、「描き直しがあっても」の行に表の枠、「横にスクロールした表やコードの位置は」の行に表の枠。
    （既存の「成果物の一覧」「プレビュー」「左端に戻」を残すことは、次のテストが見る）"""
    md = read_doc(GUIDE / "vscode.md")
    assert lines_with(md, lead), f"docs/guide/vscode.md に「{lead}」を含む行が無い"
    assert sentences_lacking(md, [(sid, lead, word)]) == [], f"「{lead}」の行に「{word}」が無い"


@pytest.mark.parametrize("sid,lead,word", TOOLS_GUIDE_KEPT, ids=[i for i, _, _ in TOOLS_GUIDE_KEPT])
def test_D0049_AC_47_ガイドの既存の文は直したあとも残る_守る(sid, lead, word):
    """D0049-AC-47: docs/guide/vscode.md の既存の文を直しても、元の言葉を消さない：「それぞれ別にスクロール」の行に既存の「成果物の一覧」「プレビュー」、
    「横にスクロールした表やコードの位置は」の行に既存の「左端に戻」が残る。（今のまま通る。守る）"""
    md = read_doc(GUIDE / "vscode.md")
    assert lines_with(md, lead), f"docs/guide/vscode.md に「{lead}」を含む行が無い"
    assert sentences_lacking(md, [(sid, lead, word)]) == [], f"「{lead}」の行から既存の「{word}」が消えている"


@pytest.mark.parametrize("sid,sentence", TOOLS_OLD_GUIDE, ids=[i for i, _ in TOOLS_OLD_GUIDE])
def test_D0049_AC_47_ガイドに詳細のタブが3つだけの古い列挙が残っていない(sid, sentence):
    """D0049-AC-47: docs/guide/vscode.md に、詳細のタブが 3 つだけの古い列挙「図と出力」「成果物」「使用量」が残っていない（30・77・80 行の列挙は 4 つになる）。"""
    assert leftover_sentences(read_doc(GUIDE / "vscode.md"), [(sid, sentence)]) == [], f"古い列挙が残っている：{sentence}"


def test_D0049_AC_47_ガイドの横スクロールの行にこの表の枠は戻らないという区別がある():
    """D0049-AC-47: docs/guide/vscode.md の「横にスクロールした表やコードの位置は…左端に戻ります」の行に、エージェント・スキルの表の枠は戻らない（戻りません・戻らない）という区別がある
    （成果物のプレビューの表やコードは戻り、この表の枠は描き直しで位置が残る。AC-31）。"""
    md = read_doc(GUIDE / "vscode.md")
    lines = lines_with(md, "横にスクロールした表やコードの位置は")
    assert lines, "docs/guide/vscode.md に「横にスクロールした表やコードの位置は」の行が無い"
    assert any("左端に戻" in line and re.search(NOT_RETURN, line) for line in lines), f"その行に「戻りません」の区別が無い：{lines}"


def test_D0049_AC_47_ガイドの狭い幅のときの節にタブの折り返しがある():
    """D0049-AC-47: docs/guide/vscode.md の「狭い幅のとき」の節に、詳細のタブが折り返すこと（折り返）が書いてあり、既存の成果物のタブの並び（成果物）も残る。"""
    part = heading_part(read_doc(GUIDE / "vscode.md"), "狭い幅のとき")
    assert part, "docs/guide/vscode.md に「狭い幅のとき」の節が無い"
    assert "折り返" in part, "「狭い幅のとき」の節にタブの折り返しが無い"
    assert "成果物" in part, "「狭い幅のとき」の節の成果物のタブの並びが消えている"


# ---- AC-47 の検査そのものの確かめ（今のまま通る。守る） ----

# 探す言葉を 1 項目ずつ満たす 1 行の見本（ほかの項目の行では、その項目の言葉が満たされないようにしてある）
TOOLS_SAMPLE_LINES: dict[str, str] = {
    "what": "- 選んだ実行の段のログにある呼び出しを数え、呼んだ回数を出します。",
    "kinds": "- 種類は、エージェント・スキル・道具の 3 つです。MCP の道具は道具に入ります。",
    "nested": "- サブエージェントの中の呼び出しも数え、メインの呼び出しと同じ行に足します。",
    "blocked-failed": "- 本体の守りに止められた呼び出しも、失敗した呼び出しも数えます。",
    "time-none": "- 道具ごとの時間はログにありません。",
    "time-agent-row": "- 時間が出るのは受け持ちの行だけで、m:ss で書きます。",
    "agent-flag": "- /pipe-in の記録では、record begin --agent を付けた受け持ちだけが出て、付けないと受け持ちの行は出ません。",
    "notice": "- 案内を出します。「スキルや道具の呼び出しは記録に残りません」と伝え、受け持ちも無いときは案内だけです。",
    "no-input": "- 呼び出しの入力の中身（コマンド・ファイル名・プロンプト）は出しません。",
    "limits-rows": "- 表は 100 行までで、超えた種類は「ほか N 種類を省いています」と出ます。",
    "limits-stages": "- 使った段の欄は 3 つまで書き、超えた分は「ほか N 件」と出ます。",
    "delay": "- 動いている SDK の段は、段のログが出るまで少し遅れて増えます。",
}


def tools_guide_sample(skip: str | None = None, heading: str = f"### {TOOLS_TITLE}", after: str = "", replace: dict[str, str] | None = None) -> str:
    """見本のガイド。「実行を見る」の中の heading の節に、skip 以外の見本の行を並べる。after は次の節（### 狭い幅のとき）に足す文。
    replace は、見本の行を別の行に替える（項目の id → 替えの行）。"""
    lines = {**TOOLS_SAMPLE_LINES, **(replace or {})}
    body = "\n".join(line for sid, line in lines.items() if sid != skip)
    return (
        "# VSCode の拡張\n\n## 実行を見る\n\n### 実行の一覧\n\n本文\n\n"
        f"{heading}\n\n{body}\n\n### 狭い幅のとき\n\n別の節の本文\n{after}\n## パイプ作業台\n\n本文\n"
    )


def test_D0049_AC_47_検査そのものは見本の行がそろえば欠けなしにする_守る():
    """D0049-AC-47: 探す側（tools_part と words_missing）そのものの確かめ。見本の行が表の全項目にあり、そろった見本には欠けが無い。（今のまま通る。守る）"""
    assert set(TOOLS_SAMPLE_LINES) == {sid for sid, _, _ in TOOLS_GUIDE_WORDS}
    assert words_missing(tools_part(tools_guide_sample()), TOOLS_GUIDE_WORDS) == []


@pytest.mark.parametrize("sid", [i for i, _, _ in TOOLS_GUIDE_WORDS])
def test_D0049_AC_47_検査そのものは言葉が無い見本の欠けをその項目だけ見つける_守る(sid):
    """D0049-AC-47: 探す側そのものの確かめ。見本から 1 項目の行だけを抜くと、欠けとして見つかるのはその項目だけ（表の言葉が、ほかの項目の行では満たされない）。（今のまま通る。守る）"""
    assert words_missing(tools_part(tools_guide_sample(skip=sid)), TOOLS_GUIDE_WORDS) == [sid]


@pytest.mark.parametrize(
    "sid,line",
    [
        pytest.param("limits-stages", "- 表は 100 行までです。そのほかの上限はありません。", id="limits-stages-no-stage-limit"),
        pytest.param("limits-stages", "- 種類は 3 つです。使った段の欄については、ほか N 件と出ます。", id="limits-stages-split-sentences"),
        pytest.param("time-none", "- 時間が出るのは受け持ちの行だけです。/pipe-in の記録では、段のログに呼び出しの行は残りません。", id="time-none-split-sentences"),
    ],
)
def test_D0049_AC_47_検査そのものは項目の言葉を別々の文で満たさせない_守る(sid, line):
    """D0049-AC-47: 探す側そのものの確かめ。使った段の 3 つの上限と、道具ごとの時間はログに無いことは、2 つの言葉が同じ文にあるときだけ満たす。
    100 行の説明だけ・3 つの別の話（種類の 3 つ）だけ・時間とログを別の文に分けて書いた行では、その項目だけが欠けとして返る。（今のまま通る。守る）"""
    sample = tools_guide_sample(replace={sid: line})
    assert words_missing(tools_part(sample), TOOLS_GUIDE_WORDS) == [sid]


def test_D0049_AC_47_検査そのものは節が無い見本の全項目を欠けとして見つけ_節の外の言葉を拾わない_守る():
    """D0049-AC-47: 探す側そのものの確かめ。「エージェント・スキルのタブ」の見出しが無い見本・「実行を見る」の外にある見本は、言葉がそろっていても全項目が欠け。
    1 項目の行を次の節（### 狭い幅のとき）へ移すと、その項目は欠け。（今のまま通る。守る）"""
    all_ids = [sid for sid, _, _ in TOOLS_GUIDE_WORDS]
    other = tools_guide_sample(heading="### 時間と動き")
    assert tools_part(other) == ""
    assert words_missing(tools_part(other), TOOLS_GUIDE_WORDS) == all_ids
    body = "\n".join(TOOLS_SAMPLE_LINES.values())
    outside = f"## 実行を見る\n\n### 時間と動き\n\n本文\n\n## パイプ作業台\n\n### {TOOLS_TITLE}\n\n{body}\n"
    assert tools_part(outside) == ""
    moved = tools_guide_sample(skip="delay", after=TOOLS_SAMPLE_LINES["delay"] + "\n")
    assert words_missing(tools_part(moved), TOOLS_GUIDE_WORDS) == ["delay"]


def test_D0049_AC_47_検査そのものは文の表を取り違えず_古い列挙と区別を見つける_守る():
    """D0049-AC-47: 文の表そのものの確かめ。新しい言葉の無い見本はどの行も欠け、そろった見本には欠けが無く、1 つの文を消すとその文だけが欠ける（同じ頭の言葉を共有する行も取り違えない）。
    古い列挙は見つけ、4 つの列挙は見逃す。「戻りません」の区別は、「戻ります」だけの行では満たさない。（今のまま通る。守る）"""
    rows = ALL_GUIDE_SENTENCES
    ids = [sid for sid, _, _ in rows]
    bare = "\n".join(f"- {lead}。" for _, lead, _ in rows)
    full = "\n".join(f"- {lead}。{word}。" for _, lead, word in rows)
    assert sentences_lacking(bare, rows) == ids
    assert sentences_lacking(full, rows) == []
    for index, sid in enumerate(ids):
        without = "\n".join(f"- {lead}。{word}。" for i, (_, lead, word) in enumerate(rows) if i != index)
        assert sentences_lacking(without, rows) == [sid]
    assert leftover_sentences(f"タブ{THREE_TABS}。", TOOLS_OLD_GUIDE) == ["old-three-tabs"]
    assert leftover_sentences("タブ「図と出力」「成果物」「エージェント・スキル」「使用量」。", TOOLS_OLD_GUIDE) == []
    assert re.search(NOT_RETURN, "表の枠は戻りません。")
    assert re.search(NOT_RETURN, "表の枠は戻らない。")
    assert not re.search(NOT_RETURN, "横にスクロールした位置は、描き直しで左端に戻ります。")


# ---- AC-48：拡張の README（vscode/README.md） ----------------------------------------------------------------

README_SENTENCES = [
    ("tabs-detail", "タブ「図と出力」", "エージェント・スキル"),
]
README_LINK = re.compile(r"\]\(\.\./docs/guide/vscode\.md[^)]*\)")


def test_D0049_AC_48_拡張のREADMEの詳細のタブの列挙が4つになっている():
    """D0049-AC-48: vscode/README.md の詳細のタブの列挙（「右の詳細：…タブ「図と出力」…」の行）が 4 つ（エージェント・スキルを含む）で、3 つだけの古い列挙「図と出力」「成果物」「使用量」が残っていない。"""
    md = read_doc(VSCODE_README)
    assert lines_with(md, "タブ「図と出力」"), "vscode/README.md に「タブ「図と出力」」を含む行が無い"
    assert sentences_lacking(md, README_SENTENCES) == [], "詳細のタブの列挙の行に「エージェント・スキル」が無い"
    assert leftover_sentences(md, TOOLS_OLD_GUIDE) == [], "古い列挙が残っている"


def test_D0049_AC_48_拡張のREADMEに新しいタブの一言とガイドへのリンクがある():
    """D0049-AC-48: vscode/README.md に、新しいタブ「エージェント・スキル」の一言があり、同じ行に docs/guide/vscode.md へのリンクがある
    （見出し「エージェント・スキルのタブ」の中黒はアンカーが環境で違うので、リンク先のファイル名までを見る。節の名前は地の文にも書く）。"""
    md = read_doc(VSCODE_README)
    hits = [line for line in md.splitlines() if TOOLS_TITLE in line and README_LINK.search(line)]
    assert hits, "「エージェント・スキルのタブ」と ../docs/guide/vscode.md へのリンクが同じ行にある行が無い"


def test_D0049_AC_48_検査そのものはリンクの行と古い列挙を見つける_守る():
    """D0049-AC-48: 検査そのものの確かめ。ガイドへのリンクの正規表現は ../docs/guide/vscode.md（アンカーつきも）を見つけ、別の文書へのリンクは見逃す。（今のまま通る。守る）"""
    assert README_LINK.search("詳しくは [ガイド](../docs/guide/vscode.md#エージェント・スキルのタブ)。")
    assert README_LINK.search("[ガイド](../docs/guide/vscode.md)")
    assert not README_LINK.search("[別](../docs/guide/usage.md)")
    assert not README_LINK.search("../docs/guide/vscode.md だけ（リンクではない）")


# ---- AC-49：設計の文書（docs/development/design.md） ---------------------------------------------------------

DESIGN_LAYERS = [
    ("ドメイン", "toolsTable.ts"),
    ("画面", "toolsHtml.ts"),
]
DESIGN_PAGE_ROW = "| 画面の確認用のページ"


@pytest.mark.parametrize("layer,word", DESIGN_LAYERS, ids=[f"{layer}-{word}" for layer, word in DESIGN_LAYERS])
def test_D0049_AC_49_designの拡張の層の表の行に新しい部品が書いてある(layer, word):
    """D0049-AC-49: docs/development/design.md の拡張の層の表の、ドメインの行に表を作る部品（toolsTable.ts）、画面の行に表の HTML の部品（toolsHtml.ts）が書いてある。"""
    row = table_row(read_doc(DESIGN_DOC), layer)
    assert row is not None, f"design.md の拡張の層の表に「| {layer} |」で始まる行が無い"
    assert word in row, f"design.md の「{layer}」の行に「{word}」が無い"


def test_D0049_AC_49_designの互換の段落にD0049の行が番号順の位置にある():
    """D0049-AC-49: docs/development/design.md の「形を変えるとき（互換）」の箇条書きに、D0049 の行が番号の昇順の位置（D0035 の次）にある。"""
    ids = numbered_bullets(heading_part(read_doc(DESIGN_DOC), "形を変えるとき"))
    assert "D0049" in ids, f"互換の段落に D0049 の行が無い（今ある行：{ids}）"
    assert ids == sorted(ids), f"互換の行が番号の昇順でない：{ids}"
    at = ids.index("D0049")
    assert at > 0 and ids[at - 1] == "D0035", f"D0049 の行は D0035 の行の次にする（今の並び：{ids}）"


def test_D0049_AC_49_designの互換のD0049の行は記録の形を変えず写しの表とdriverとタブを足したと書く():
    """D0049-AC-49: 互換の D0049 の行に、記録の形を変えないこと、拡張の内側の写しに表の項目と RunRecord の driver を足したこと、HTML にタブとパネルを足しただけであることが書いてある
    （D0021・D0025 の書き方に合わせる）。"""
    part = heading_part(read_doc(DESIGN_DOC), "形を変えるとき")
    line = next((text for text in part.splitlines() if re.match(r"^- D0049(?!\d)", text)), None)
    assert line is not None, "互換の段落に D0049 の行が無い"
    missing = [w for w in ("記録の形", "写し", "表", "driver", "タブ") if w not in line]
    assert missing == [], f"D0049 の行に書かれていない言葉：{missing}"


def test_D0049_AC_49_designの確認用ページの行に見本の部品のパスがあり_完全なページ名を2つ以上並べない():
    """D0049-AC-49: docs/development/design.md の置き場所の表の「画面の確認用のページ」の行に、見本の部品 vscode/scripts/toolsSamples.ts がある
    （パスの実在は tests/test_rules.py が見る）。完全なページ名は 2 つ以上並べない（D0039-AC-16 が通ったまま）。"""
    md = read_doc(DESIGN_DOC)
    row = row_starting(md, DESIGN_PAGE_ROW)
    assert row is not None, f"design.md に「{DESIGN_PAGE_ROW}」で始まる行が無い"
    assert "vscode/scripts/toolsSamples.ts" in row, "確認用ページの行に toolsSamples.ts が無い"
    assert crowded_lines(md, real_full_names(), only=lambda line: line.startswith(DESIGN_PAGE_ROW)) == []


# ---- AC-50：確認用ページの持ち場（docs/assets/README.md の表・screen-check.md） ------------------------------------


def test_D0049_AC_50_assetsのREADMEの表にrun_panel_toolsの行があり撮らないと書いてある():
    """D0049-AC-50: docs/assets/README.md の確認用のページの表に、run-panel-tools の頭の形（-light・-dark・-*・.html のどれかが続く）の行があり、
    同じ行に「撮ら」（撮らない）がある。D0025-AC-79（PANEL_PAGES の各頭が README に出る）は通ったまま。"""
    md = read_doc(ASSETS_README)
    assert heads_missing(md, [TOOLS_HEAD]) == [], f"docs/assets/README.md に {TOOLS_HEAD}-* の頭の形が無い"
    rows = [line for line in md.splitlines() if line.startswith("|") and re.search(re.escape(TOOLS_HEAD) + r"(?:-(?:light|dark|\*|<[^>\n]*>)|\.html)", line)]
    assert rows, "docs/assets/README.md の表に run-panel-tools の行が無い"
    assert all("撮ら" in row for row in rows), f"run-panel-tools の行に「撮らない」が無い：{rows}"


def test_D0049_AC_50_screen_checkに頭run_panel_toolsとエージェントスキルのタブを開く手順がある():
    """D0049-AC-50: .claude/skills/pipe-in/screen-check.md に、ページの種類の頭 run-panel-tools（頭の形）と、「エージェント・スキル」のタブを開いて確かめる手順がある
    （.claude/ はメインが書く。実装の段のあと、検証の前に足した）。一覧は docs/assets/README.md を指す形のまま（D0039-AC-17）。"""
    md = read_doc(SCREEN_CHECK)
    assert heads_missing(md, [TOOLS_HEAD]) == [], f"screen-check.md に頭 {TOOLS_HEAD} が頭の形で出てこない"
    lines = [line for line in md.splitlines() if TOOLS_HEAD in line]
    assert any("「エージェント・スキル」" in line and "タブ" in line for line in lines), f"screen-check.md に「エージェント・スキル」のタブを開く手順が無い：{lines}"


def test_D0049_AC_50_CLAUDEとdesignに完全なページ名run_panel_tools_light_darkを足さない_守る():
    """D0049-AC-50: CLAUDE.md と docs/development/design.md に、完全なページ名（run-panel-tools-light・run-panel-tools-dark）が無い（D0039-AC-16：一覧の持ち場は docs/assets/README.md の 1 か所）。
    （今のまま通る。守る）"""
    for path in (CLAUDE_MD, DESIGN_DOC):
        text = read_doc(path)
        for name in (f"{TOOLS_HEAD}-light", f"{TOOLS_HEAD}-dark"):
            assert name not in text, f"{path.relative_to(ROOT).as_posix()} に完全なページ名 {name} がある"


def test_D0049_AC_50_検査そのものは頭の形を見つけ_名前の一部だけの出方は見逃さない_守る():
    """D0049-AC-50: 頭の形の検査そのものの確かめ。run-panel-tools-* ・ run-panel-tools-<テーマ>・.html つきは満たし、別のページ（run-panel-tools-extra の一部だけ）の出方は、頭のあとの形が無ければ満たさない。
    （今のまま通る。守る）"""
    assert heads_missing("`run-panel-tools-*`", [TOOLS_HEAD]) == []
    assert heads_missing("`run-panel-tools-<テーマ>`", [TOOLS_HEAD]) == []
    assert heads_missing("`run-panel-tools-light.html`・`run-panel-tools-dark.html`", [TOOLS_HEAD]) == []
    assert heads_missing("`run-panel-toolset-light.html`", [TOOLS_HEAD]) == [TOOLS_HEAD]
    assert heads_missing("", [TOOLS_HEAD]) == [TOOLS_HEAD]
    assert panel_page_heads("export const PANEL_PAGES = [\n  ['run-panel-tools-light', 'light'],\n  ['run-panel-tools-dark', 'dark'],\n];\n") == [TOOLS_HEAD]


# ---- AC-51：決定の記録の表（docs/decisions/README.md）と決定の記録 --------------------------------------------

AC_COUNT = 61
# 手で・実機で確かめる AC と、画面の確認の AC（行に結果の言葉が要る）。AC-39 は検証の段で差分を見る（手で）ので、テストの名前でも結果の言葉でもよい
RESULT_AC = set(range(52, 62))
EITHER_AC = {39}
RESULT_WORDS = ("確かめていない", "確かめた", "まだ")
TEST_MARKS = ("test_", "tests/", ".test.ts")
RECORD_BODY_WORDS = [
    "既存のテストを変えた理由",
    "view/shellHtml.test.ts",
    "view/artifactsPanel.test.ts",
    "view/panelScriptUi.test.ts",
    "previewPagesArtifacts.test.ts",
    "test/previewText.ts",
    "D0019-AC-62",
    "D0025-AC-70",
    "D0025-AC-73",
    "置き換える",
    "受け入れたリスク",
    "二重に数える",
]


def record_path():
    found = sorted(DECISIONS.glob("D0049-*.md"))
    return found


def ac_lines(text: str) -> dict[int, str]:
    """AC の行（先頭の - と空白を除いて D0049-AC-NN で始まる行。NN は 2 けた）を、番号 → 行にする。"""
    out: dict[int, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("- "):
            s = s[2:].lstrip()
        m = re.match(r"D0049-AC-(\d{2})(?!\d)", s)
        if m:
            out.setdefault(int(m.group(1)), s)
    return out


def ac_line_problems(text: str) -> list[str]:
    """画面・手で・実機の AC の行に結果の言葉が無い、それ以外の AC の行にテストの名前（test_・tests/・.test.ts）が無い、AC の行が無い、を返す
    （docs/development/specs.md の「AC には、確かめたテストの名前を添える」）。"""
    lines = ac_lines(text)
    problems = []
    for n in range(1, AC_COUNT + 1):
        line = lines.get(n)
        if line is None:
            problems.append(f"AC-{n:02d} の行が無い")
            continue
        has_result = any(w in line for w in RESULT_WORDS)
        has_test = any(m in line for m in TEST_MARKS)
        if n in RESULT_AC:
            if not has_result:
                problems.append(f"AC-{n:02d}（画面・手で・実機）の行に結果の言葉（{'・'.join(RESULT_WORDS)}）が無い")
        elif n in EITHER_AC:
            if not (has_result or has_test):
                problems.append(f"AC-{n:02d}（手で）の行に結果の言葉かテストの名前が無い")
        elif not has_test:
            problems.append(f"AC-{n:02d} の行にテストの名前（test_・tests/・.test.ts）が無い")
    return problems


def test_D0049_AC_51_決定の記録は1つで_1行目が題_守る():
    """D0049-AC-51: docs/decisions/ に D0049-<名前>.md が 1 つあり（D0049-run-tools.md）、1 行目が「# D0049 <題>」。形は tests/test_rules.py が見る。（骨組みで通る。守る）"""
    found = record_path()
    assert [p.name for p in found] == ["D0049-run-tools.md"]
    assert found[0].read_text(encoding="utf-8").startswith("# D0049 ")


def test_D0049_AC_51_決定の記録にAC_01から61の行が1つずつある_守る():
    """D0049-AC-51: 決定の記録に D0049-AC-01 から D0049-AC-61 の行が 1 つずつある。（骨組みで通る。守る）"""
    found = record_path()
    assert found, "決定の記録 D0049-*.md が無い"
    assert sorted(ac_lines(found[0].read_text(encoding="utf-8"))) == list(range(1, AC_COUNT + 1))


def test_D0049_AC_51_決定の記録の表にD0049の行があり_前の行は小さい番号のうち最大_守る():
    """D0049-AC-51: docs/decisions/README.md の表に D0049 の行があり、表の番号は昇順で、D0049 の行の前の行は D0049 より小さい番号のうち最大のもの
    （前の番号を決め打ちしない）。行はファイル D0049-run-tools.md を指し、題に「エージェント・スキル」がある。（骨組みで通る。守る）"""
    md = read_doc(DECISIONS_README)
    ids = [int(i[1:]) for i in table_decision_ids(md)]
    assert 49 in ids, f"決定の記録の表に D0049 の行が無い（今の行：{ids[-6:]}）"
    assert ids == sorted(ids), f"表の番号が昇順でない：{ids}"
    at = ids.index(49)
    smaller = [i for i in ids if i < 49]
    assert at > 0 and ids[at - 1] == max(smaller), f"D0049 の行の前の行が、49 より小さい番号のうち最大でない（今の並び：{ids[-6:]}）"
    row = next(line for line in md.splitlines() if line.startswith("| [D0049]"))
    assert "D0049-run-tools.md" in row, row
    assert "エージェント・スキル" in row, f"D0049 の行の題に「エージェント・スキル」が無い：{row}"


@pytest.mark.parametrize("word", [pytest.param(w, id=f"body-{i}") for i, w in enumerate(RECORD_BODY_WORDS)])
def test_D0049_AC_51_決定の記録の本体に既存のテストを変えた理由と受け入れたリスクの言葉がある(word):
    """D0049-AC-51（記録の本体）: 決定の記録に、「既存のテストを変えた理由」の節と、直した 5 つのテストのファイル名（view/shellHtml.test.ts・view/artifactsPanel.test.ts・
    view/panelScriptUi.test.ts・previewPagesArtifacts.test.ts・移し先の test/previewText.ts）、置き換える AC（D0019-AC-62・D0025-AC-70・D0025-AC-73 と「置き換える」）、
    受け入れたリスクと「二重に数える」が書いてある（検証のあとにメインが書く。骨組みには入れないので、本体を書くまで赤＝既知の赤）。"""
    found = record_path()
    assert found, "決定の記録 D0049-*.md が無い"
    text = found[0].read_text(encoding="utf-8")
    assert word in text, f"docs/decisions/D0049-run-tools.md に「{word}」が無い"


def test_D0049_AC_51_決定の記録の本体のACの行にテストの名前か結果の言葉がある():
    """D0049-AC-51（記録の本体）: AC の行のうち、画面・手で・実機の AC（52〜61）は確かめた・確かめていない・まだのどれかを含み、AC-39 は結果の言葉かテストの名前を含み、
    それ以外の AC の行はテストの名前（test_・tests/・.test.ts）を含む（骨組みは AC の ID と短い題だけなので、本体を書くまで赤＝既知の赤）。"""
    found = record_path()
    assert found, "決定の記録 D0049-*.md が無い"
    problems = ac_line_problems(found[0].read_text(encoding="utf-8"))
    assert problems == [], "\n" + "\n".join(problems)


def test_D0049_AC_51_検査そのものは語の無い偽の記録をそのACの欠けとして返す_守る():
    """D0049-AC-51: 検査そのもの（ac_line_problems と ac_lines）の確かめ。語の無い骨組みだけの記録は全部の AC を、結果の言葉の無い画面・手で・実機の AC の行・
    テストの名前の無い AC の行・行そのものが無い AC を欠けとして返し、AC-39 はどちらかがあれば満たし、そろった記録は欠け 0 件。（今のまま通る。守る）"""

    def fake(drop: set[int] = frozenset(), strip: set[int] = frozenset(), only39: str = "") -> str:
        rows = []
        for n in range(1, AC_COUNT + 1):
            if n in drop:
                continue
            if n in RESULT_AC:
                text = "（画面）まだ確かめていない"
            elif n == 39:
                text = only39 or "（手で）検証の段で差分を見て確かめた"
            else:
                text = "確かめたテスト：vscode/src/domain/x.test.ts"
            rows.append(f"  - D0049-AC-{n:02d} 題。" + ("" if n in strip else text))
        return "\n".join(rows) + "\n"

    assert ac_line_problems(fake()) == []
    skeleton = "\n".join(f"  - D0049-AC-{n:02d}" for n in range(1, AC_COUNT + 1))
    assert len(ac_line_problems(skeleton)) == AC_COUNT
    assert [p[:5] for p in ac_line_problems(fake(strip={1, 52}))] == ["AC-01", "AC-52"]
    assert ac_line_problems(fake(drop={61})) == ["AC-61 の行が無い"]
    assert ac_line_problems(fake(only39="tests/test_x.py::test_a")) == [], "AC-39 はテストの名前でもよい"
    assert ac_line_problems(fake(strip={39})) == ["AC-39（手で）の行に結果の言葉かテストの名前が無い"]
    assert ac_line_problems("") == [f"AC-{n:02d} の行が無い" for n in range(1, AC_COUNT + 1)]
