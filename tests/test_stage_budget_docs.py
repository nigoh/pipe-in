"""D0051：文書をそろえる（FR-19・FR-20）。利用者向けの文書（記録・拡張・設定・パイプの書き方）と、開発の決まりの文書に、決まった語や行があるかを見る。

読むだけで書かない（偽の文は文字列で組み立てる）。SDK は呼ばない。tests/test_guide.py・tests/test_skill_tidy_docs.py と同じ流儀の小さな補助をこのファイルの中に持つ
（ほかのテストのファイルは import しない）。

- 語は、要件定義の AC に書いた言い回しから取る。文書のほうは、その語を使って書く（言い換えるなら、このテストの語を直す）。
- 「説明の行」は、``` で囲んだコードの外の行で max_budget_usd を含むもの（見本のコードブロックの行は、説明に数えない）。
- 見本のコードブロックの行（config.md と pipes.md にある max_budget_usd = 1.0 の行）は、tests/test_guide.py が固定している。変えない。
- 文書ができるまでは、語が無いことで落ちる。決定の記録（docs/decisions/D0051-*.md）と索引の行は、検証の段でメインが書くまで赤のまま残る。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOT_SHOWN = re.compile(r"出(ない|ません|しません)")  # 「出ない」「出ません」「出しません」
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
PAGE_FORM = r"(?:-(?:light|dark|\*|<[^>\n]*>)|\.html)"  # 頭のあとに -light・-dark・-*・-<…>・.html が続く形（tests/test_guide.py の heads_missing と同じ）


# ---- 補助：読む・行や節を切り出す ----------------------------------------------------------------


def read_doc(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        pytest.fail(f"{rel} が無い", pytrace=False)
    return path.read_text(encoding="utf-8")


def outside_code(md: str) -> list[str]:
    """``` で囲んだコードの外の行（囲みの線の行も含めない）。"""
    out: list[str] = []
    in_code = False
    for line in md.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        elif not in_code:
            out.append(line)
    return out


def lines_with(md: str, needle: str) -> list[str]:
    return [line for line in outside_code(md) if needle in line]


def lacking(text: str, words) -> list[str]:
    """text に無い語（文字列は部分文字列、正規表現は検索）。正規表現の欠けは、その式の文字で返す。"""
    out = []
    for w in words:
        found = w.search(text) if isinstance(w, re.Pattern) else (w in text)
        if not found:
            out.append(w.pattern if isinstance(w, re.Pattern) else w)
    return out


def line_lacking(md: str, words) -> bool:
    """words がぜんぶ 1 つの行（コードの外）に入っている行が無ければ True。"""
    return not any(not lacking(line, words) for line in outside_code(md))


def sections(md: str, part: str, *, exact: bool = False) -> list[str]:
    """見出しの文字に part を含む（exact なら等しい）節の本文を、上から全部。節の終わりは、次の同じか浅い見出しの前（小見出しは含む）。
    ``` で囲んだコードの中の # は見出しにしない。"""
    heads: list[tuple[int, str, int, int]] = []  # (深さ, 題, 見出しの行の始まり, 次の行の始まり)
    pos = 0
    in_code = False
    for line in md.splitlines(keepends=True):
        text = line.rstrip("\r\n")
        if text.lstrip().startswith("```"):
            in_code = not in_code
        elif not in_code:
            m = HEADING.match(text)
            if m:
                heads.append((len(m.group(1)), m.group(2), pos, pos + len(line)))
        pos += len(line)
    out = []
    for i, (depth, title, _start, body) in enumerate(heads):
        if (title != part) if exact else (part not in title):
            continue
        end = next((h[2] for h in heads[i + 1 :] if h[0] <= depth), len(md))
        out.append(md[body:end])
    return out


def row_starting(md: str, lead: str) -> str | None:
    return next((line for line in outside_code(md) if line.startswith(lead)), None)


def need_row(md: str, lead: str, where: str) -> str:
    row = row_starting(md, lead)
    if row is None:
        pytest.fail(f"{where} に「{lead}」で始まる表の行が無い", pytrace=False)
    return row


# ---- 検査の補助そのものの確かめ -------------------------------------------------------------------------


def test_d0051_ac85_見本_補助はコードの囲みの中を説明に数えず_節を小見出しまで切り_語の欠けを返す_守る():
    """D0051-AC-85: 検査そのものの確かめ。説明の行（コードの外で max_budget_usd を含む行）は、``` の囲みの中の見本の行を数えない。節は次の同じか浅い見出しの前まで
    （小見出しは含み、囲みの中の # は見出しにしない）。語の欠けは、文字列は部分文字列、正規表現は検索で見て、欠けた語を返す。（今のまま通る。守る）"""
    md = "説明 max_budget_usd\n```toml\nmax_budget_usd = 1.0\n```\n| `max_budget_usd` | 行 |\n"
    assert lines_with(md, "max_budget_usd") == ["説明 max_budget_usd", "| `max_budget_usd` | 行 |"]
    doc = "# 題\n## 節A\n本文A\n```\n## 囲みの中\n```\n### 小\n小の本文\n## 節B\nB の本文\n"
    (a,) = sections(doc, "節A")
    assert "本文A" in a and "囲みの中" in a and "小の本文" in a and "B の本文" not in a
    assert sections(doc, "小", exact=True) == ["小の本文\n"] and sections(doc, "無い見出し") == []
    assert lacking("あいう", ["あ", re.compile("え"), "う", "お"]) == ["え", "お"]
    assert line_lacking("あ い\nう\n", ["あ", "い"]) is False and line_lacking("あ\nい\n", ["あ", "い"]) is True


# ---- AC-83：docs/guide/records.md ----------------------------------------------------------------


def test_d0051_ac83_recordsにmax_budget_usdとresumedの項目がある():
    """D0051-AC-83: docs/guide/records.md の runs[] の項目の表に、max_budget_usd と resumed（続きの会話の印）の行があり、上限が効いた実行にだけ書くこと・
    印は resume を渡した実行にだけ true を書くこと・無い記録は上限なしとして読むこと・null は書かないことが書いてある。"""
    md = read_doc("docs/guide/records.md")
    rows = [line for line in outside_code(md) if line.startswith("|")]
    budget = [r for r in rows if "`max_budget_usd`" in r]
    resumed = [r for r in rows if "`resumed`" in r]
    assert budget, "records.md の表に `max_budget_usd` の行が無い"
    assert resumed, "records.md の表に `resumed` の行が無い"
    missing = lacking(
        "\n".join(budget + resumed),
        [
            "runs[]",
            re.compile(r"上限が効いた[^|。]{0,12}実行にだけ"),  # 「上限が効いた実行にだけ」「上限が効いた SDK の段の実行にだけ」のどちらでも
            re.compile("を渡した実行にだけ"),
            "`true`",
            "上限なしとして読",
            re.compile(r"`null`[^|。]{0,20}書(かない|きません)"),
        ],
    )
    assert missing == [], f"max_budget_usd・resumed の行に無い語: {missing}"


# ---- AC-84：docs/guide/vscode.md -----------------------------------------------------------------


def budget_text(md: str) -> str:
    """見出しに「上限」か「費用」を含む節の本文を全部つなげたもの（図の上限の見方と費用の表の説明は、1 つの節でも 2 つの節でもよい）。"""
    return "\n".join(sections(md, "上限") + sections(md, "費用"))


def test_d0051_ac84_vscodeに図の上限の見方がある():
    """D0051-AC-84: docs/guide/vscode.md に、見出しに「上限」を含む節があり、図の上限の見方（金額の対・棒・4 つの状態と言葉・「近い」は上限の 8 割以上・N 回目・
    動いている段には出ない・上限の無い段は今までどおり・続きの会話の回は金額の対を出さず止まったときだけ言葉・状態バー／実行の一覧／知らせには出ない）が書いてある。"""
    md = read_doc("docs/guide/vscode.md")
    assert sections(md, "上限"), "vscode.md に見出しに「上限」を含む節が無い"
    text = budget_text(md)
    missing = lacking(
        text,
        [
            "金額の対",
            "棒",
            "余裕",
            "近い",
            "超えた",
            "止まった",
            "上限に近い",
            "上限を超えた",
            "上限で止まった",
            re.compile(r"8\s*割"),
            re.compile(r"N\s*回目"),
            "状態バー",
            "実行の一覧",
            "知らせ",
        ],
    )
    assert missing == [], f"図の上限の見方に無い語: {missing}"
    sentences = {
        "動いている段には出ない": ["動いている段", NOT_SHOWN],
        "上限の無い段は今までどおり": [re.compile(r"上限(の|が)(無い|ない)"), "今までどおり"],
        "続きの会話の回は金額の対を出さず止まったときだけ言葉": ["続きの会話", "金額の対", "止まった"],
        "状態バー・実行の一覧・知らせには出ない": ["状態バー", NOT_SHOWN],
        "4 つの状態と言葉": ["余裕", "上限に近い", "上限を超えた", "上限で止まった"],
        "「近い」は上限の 8 割以上": ["近い", re.compile(r"8\s*割")],
        "N 回目の説明": [re.compile(r"N\s*回目"), "上限"],
    }
    lacking_lines = [what for what, words in sentences.items() if line_lacking(text, words)]
    assert lacking_lines == [], f"1 つの行にそろっていない文: {lacking_lines}"


def test_d0051_ac84_vscodeに費用の表の説明がある():
    """D0051-AC-84: docs/guide/vscode.md に、費用の表の説明（段ごとの費用・使用量のタブに出ること・費用の多い順の並び・割合・費用 0 の段は出ない）が書いてある。"""
    md = read_doc("docs/guide/vscode.md")
    assert sections(md, "費用"), "vscode.md に見出しに「費用」を含む節が無い"
    text = budget_text(md)
    missing = lacking(text, ["段ごとの費用", "使用量", re.compile("費用の多い順"), "割合"])
    assert missing == [], f"費用の表の説明に無い語: {missing}"
    assert not line_lacking(text, [re.compile(r"費用\s*0"), NOT_SHOWN]), "「費用 0 の段は出ない」の行が無い"


# ---- AC-85：docs/guide/config.md -----------------------------------------------------------------


def test_d0051_ac85_configのmax_budget_usdの説明():
    """D0051-AC-85: docs/guide/config.md の max_budget_usd の説明（コードの外の行）に、記録に残り図に出ること・目安で超えることがある（サブエージェントの費用も数える）・
    pipeline.toml の 0 は未設定として読むこと・0 より大きい数でない値（負の数・文字・真偽など）は SDK を呼ぶ前に止まり直し方が出ること・
    pipe-in record／pipe-in live（--work-dir を渡さないとき）も同じ文で止まることが書いてある。見本の 1 行（max_budget_usd = 1.0 ＋ 段ごとの費用の上限（概算））は変えない。"""
    md = read_doc("docs/guide/config.md")
    rows = lines_with(md, "max_budget_usd")
    assert rows, "config.md に max_budget_usd の説明の行（コードの外）が無い"
    sentences = {  # 1 つの文として成り立つ語の組は、同じ行にそろっていること
        "記録に残り図に出る": [re.compile(r"記録に残り[^。]{0,12}図に出")],
        "目安で超えることがある（サブエージェントの費用も数える）": ["目安", "超えること", "サブエージェント"],
        "pipeline.toml の 0 は未設定として読む": ["pipeline.toml", re.compile(r"(?<![\d.])0(?![\d.])"), "未設定"],
        "0 より大きい数でない値は SDK を呼ぶ前に止まり直し方が出る": ["0 より大きい数", "負の数", "真偽", "SDK を呼ぶ前", "直し方"],
        "pipe-in record／live も --work-dir なしで同じ文で止まる": ["pipe-in record", "pipe-in live", "--work-dir", "同じ文"],
    }
    rows_text = "\n".join(rows)
    lacking_lines = [what for what, words in sentences.items() if line_lacking(rows_text, words)]
    assert lacking_lines == [], f"max_budget_usd の説明に、1 つの行にそろっていない文: {lacking_lines}"
    assert "max_budget_usd = 1.0            # 段ごとの費用の上限（概算）" in md, "見本の 1 行が変わっている"


# ---- AC-86：vscode/README.md ---------------------------------------------------------------------


def test_d0051_ac86_vscode_readmeの使用量の節が費用の表の出方に合う():
    """D0051-AC-86: vscode/README.md の「### 使用量」から「古い記録では節を出さない（今までどおり）」が消え、usage_summary の無い古い記録でも runs[] に費用があれば
    費用の表（段ごとの費用）が出ることが 1 つの行に書かれている。ステータスバーの説明の利用枠の文（頭と「件数の形」。D0024-AC-47）は残る。"""
    md = read_doc("vscode/README.md")
    (usage,) = sections(md, "使用量", exact=True) or pytest.fail("vscode/README.md に「使用量」の節が無い", pytrace=False)
    assert "古い記録では節を出さない" not in usage, "「古い記録では節を出さない（今までどおり）」が残っている"
    assert not line_lacking(usage, ["段ごとの費用", "usage_summary", "古い記録", "runs[]"]), (
        "「usage_summary の無い古い記録でも、runs[] に費用があれば段ごとの費用が出る」の行が使用量の節に無い"
    )
    assert not line_lacking(usage, ["ステータスバーの説明にも、利用枠の今の使用率が出る", "件数の形"]), "D0024-AC-47 の文が変わっている"


# ---- AC-87：docs/development/design.md -----------------------------------------------------------


def test_d0051_ac87_designの互換の節にD0051の1行がある():
    """D0051-AC-87: docs/development/design.md の「形を変えるとき（互換）」に D0051 の 1 行がある（runs[] に足す 2 項目 max_budget_usd・resumed・足すだけ・
    無い古い記録は上限なしとして読む・鍵は共通の表 budget_record.json を本体と拡張のテストが読んで結ぶ）。"""
    md = read_doc("docs/development/design.md")
    found = sections(md, "形を変えるとき", exact=False)
    assert found, "design.md に「形を変えるとき（互換）」の節が無い"
    lines = [line for line in outside_code(found[0]) if "D0051" in line]
    assert lines, "「形を変えるとき（互換）」の節に D0051 の行が無い"
    missing = lacking("\n".join(lines), ["max_budget_usd", "resumed", "足す", "上限なし", "budget_record.json"])
    assert missing == [], f"D0051 の互換の行に無い語: {missing}"


def test_d0051_ac87_designの拡張の層の表に新しい部品がある():
    """D0051-AC-87: design.md の「拡張の層」の表で、ドメインの行に stageBudget.ts・stageCosts.ts、画面の行に money.ts と usageHtml.ts（段ごとの費用）がある。"""
    md = read_doc("docs/development/design.md")
    domain = need_row(md, "| ドメイン |", "design.md の拡張の層の表")
    view = need_row(md, "| 画面 |", "design.md の拡張の層の表")
    assert lacking(domain, ["stageBudget.ts", "stageCosts.ts"]) == [], "ドメインの行に新しい部品が無い"
    assert lacking(view, ["money.ts", "usageHtml.ts", "段ごとの費用"]) == [], "画面の行に新しい部品が無い"


def test_d0051_ac87_designの置き場所の表に確認用ページの見本と共通の表がある():
    """D0051-AC-87: design.md の置き場所の表で、画面の確認用のページの行に vscode/scripts/budgetSamples.ts（見本の記録の中身）があり、
    共通の表 tests/fixtures/budget_record.json の行がある。"""
    md = read_doc("docs/development/design.md")
    page = need_row(md, "| 画面の確認用のページ", "design.md の置き場所の表")
    assert "vscode/scripts/budgetSamples.ts" in page, "確認用ページの行に budgetSamples.ts が無い"
    table = [line for line in outside_code(md) if line.startswith("|") and "tests/fixtures/budget_record.json" in line]
    assert table, "置き場所の表に tests/fixtures/budget_record.json の行が無い"


# ---- AC-88：docs/assets/README.md・screen-check.md・決定の記録の索引 ----------------------------------


def test_d0051_ac88_assetsのREADMEの確認用ページの一覧に上限のページの行がある():
    """D0051-AC-88: docs/assets/README.md の確認用ページの一覧の表に、新しいページの種類 run-panel-budget の行があり、その行に画像に撮るかどうか（撮）が書いてある
    （tests/test_skill_tidy_docs.py の D0039-AC-37 と同じ決まり）。"""
    md = read_doc("docs/assets/README.md")
    rows = [line for line in outside_code(md) if line.startswith("|") and "run-panel-budget" in line]
    assert rows, "確認用ページの一覧に run-panel-budget の行が無い"
    assert [r for r in rows if "撮" not in r] == [], "run-panel-budget の行に画像に撮るかが書かれていない"


def test_d0051_ac88_screen_checkにページの種類の頭run_panel_budgetがある():
    """D0051-AC-88: .claude/skills/pipe-in/screen-check.md に、ページの種類の頭 run-panel-budget が頭の形（run-panel-budget-*・run-panel-budget-<テーマ>・.html など）で出る
    （tests/test_skill_tidy_docs.py の D0039-AC-17 が PANEL_PAGES から拾う頭と同じ形）。"""
    md = read_doc(".claude/skills/pipe-in/screen-check.md")
    assert re.search("run-panel-budget" + PAGE_FORM, md), "screen-check.md に run-panel-budget が頭の形で出てこない"


def test_d0051_ac88_決定の記録の索引にD0051の行がある():
    """D0051-AC-88: docs/decisions/README.md の索引の表に D0051 の行があり、その行がさす決定の記録のファイル（D0051-<名前>.md）が実在する。"""
    md = read_doc("docs/decisions/README.md")
    row = next((line for line in outside_code(md) if line.startswith("| [D0051](")), None)
    assert row is not None, "決定の記録の索引に D0051 の行が無い"
    m = re.match(r"\| \[D0051\]\((D0051-[a-z0-9-]+\.md)\)", row)
    assert m is not None, f"D0051 の行がファイルを指していない: {row!r}"
    assert (ROOT / "docs" / "decisions" / m.group(1)).is_file(), f"索引がさす {m.group(1)} が無い"


# ---- AC-106：docs/guide/pipes.md -----------------------------------------------------------------


def test_d0051_ac106_pipesにpipe_tomlのmax_budget_usdの説明がある():
    """D0051-AC-106: docs/guide/pipes.md の pipe.toml の max_budget_usd の説明（コードの外の行）に、0 より大きい数で書くこと・0（pipeline.toml と違い未設定にならない）・
    負の数・文字・真偽は流す前に止まり直し方が出ること・書かなければ上限なしのこと・効いた上限が記録に残り図に出ること（config.md を指す）が書いてある。
    見本のコードブロックの行（# model = "sonnet" / max_turns = 100 / max_budget_usd = 1.0）は変えない。"""
    md = read_doc("docs/guide/pipes.md")
    rows = lines_with(md, "max_budget_usd")
    assert rows, "pipes.md に max_budget_usd の説明の行（コードの外）が無い"
    sentences = {  # 1 つの文として成り立つ語の組は、同じ行にそろっていること
        "0 より大きい数で書く": ["0 より大きい数"],
        "0 は pipeline.toml と違い未設定にならない": ["pipeline.toml", re.compile(r"(?<![\d.])0(?![\d.])"), "未設定"],
        "負の数・文字・真偽は流す前に止まり直し方が出る": ["負の数", "真偽", "流す前", "直し方"],
        "書かなければ上限なし": ["書かな", "上限なし"],
        "効いた上限が記録に残り図に出る（config.md を指す）": [re.compile(r"記録に残り[^。]{0,12}図に出"), "config.md"],
    }
    rows_text = "\n".join(rows)
    lacking_lines = [what for what, words in sentences.items() if line_lacking(rows_text, words)]
    assert lacking_lines == [], f"pipe.toml の max_budget_usd の説明に、1 つの行にそろっていない文: {lacking_lines}"
    assert '# model = "sonnet" / max_turns = 100 / max_budget_usd = 1.0' in md, "見本のコードブロックの行が変わっている"
