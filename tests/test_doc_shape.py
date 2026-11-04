"""D0075：夜の並列の作業でぶつかる文書とテストの形の検査。

- 決定の記録の一覧（docs/decisions/README.md）：番号の昇順・重ならない・リンク先が実在・各記録に行がある・.gitattributes の union
- design.md と CLAUDE.md の表の行の長さの上限と、割ったあとの形（層ごとの部品の表・確認用ページの行）・割る前の語が残ること
- screen-check.md が 1 行に頭を 1 つだけ書くこと・欠けたときのメッセージ
- workflow.md の「並列の作業でぶつからない書き方」の節と CLAUDE.md の入口
- 既存の D0002・D0039 のテスト関数の名前が消えないこと

読むだけで書かない（偽の文書は文字列で組み立てる）。SDK は呼ばない。
標準ライブラリと pytest と tests/ の中のファイルだけを import する（tests/test_architecture_doc_shape.py が見る）。
赤の段で今の作りのままで通ったテストは、名前の末尾を _守る にした（緑になったあとも名前は変えない）。
メールアドレスに見える文字・ユーザー名の入ったパスは書かない（tests/test_rules.py の検査は、このファイルを除かず、追跡していない新しいファイルも見る）。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from test_guide import heads_missing
from test_rules import records
from test_skill_tidy import need_section, read_doc
from test_skill_tidy_docs import SCREEN_CHECK, real_heads, screen_check_message, screen_check_problems

ROOT = Path(__file__).resolve().parents[1]
DECISIONS_README = ROOT / "docs" / "decisions" / "README.md"
GITATTRIBUTES = ROOT / ".gitattributes"
DESIGN_MD = ROOT / "docs" / "development" / "design.md"
WORKFLOW_MD = ROOT / "docs" / "development" / "workflow.md"
CLAUDE_MD = ROOT / "CLAUDE.md"
TESTS = ROOT / "tests"


# ---- 決定の記録の一覧の形（D0075-AC-01・02） -----------------------------------------------------------

ROW = re.compile(r"^\| \[(D\d{4})\]\((D\d{4}-[a-z0-9][a-z0-9-]*\.md)\) \| (.+) \|$")
CONFLICT_MARKS = ("<<<<<<<", "=======", ">>>>>>>")


def list_rows(text: str) -> list[tuple[int, str, str, str]]:
    """「| [」で始まる行を、(行番号, 番号, リンク先, 題) に分ける。形に合わない行は入れない。"""
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        if line.startswith("| ["):
            m = ROW.match(line)
            if m:
                out.append((no, m.group(1), m.group(2), m.group(3)))
    return out


def list_problems(text: str, record_names: list[str]) -> list[str]:
    """一覧の壊れ。形に合わない行・衝突の印・番号が前の行以下（重複と並び違い）・リンク先の番号違い・リンク先が無い・行が無い記録。"""
    problems: list[str] = []
    for no, line in enumerate(text.splitlines(), 1):
        if line.startswith(CONFLICT_MARKS):
            problems.append(f"{no} 行目：衝突の印が残っている")
        if line.startswith("| [D") and not ROW.match(line):
            problems.append(f"{no} 行目：一覧の行の形（| [Dnnnn](Dnnnn-名前.md) | 題 |）に合わない")
    previous = None
    rows = list_rows(text)
    for no, number, link, _ in rows:
        if previous is not None and number == previous:
            problems.append(f"{no} 行目：{number} の行が重なっている")
        elif previous is not None and number < previous:
            problems.append(f"{no} 行目：{number} が前の行 {previous} より小さい（番号の昇順でない）")
        previous = number
        if not link.startswith(f"{number}-"):
            problems.append(f"{no} 行目：{number} のリンク先 {link} の番号が行の番号と違う")
        if link not in record_names:
            problems.append(f"{no} 行目：{number} のリンク先 {link} が docs/decisions/ に無い")
    listed = {link for _, _, link, _ in rows}
    for name in sorted(record_names):
        if name not in listed:
            problems.append(f"{name} の行が一覧に無い")
    return problems


def test_D0075_AC_01_決定の記録の一覧は昇順で重ならず_リンク先が実在し_各記録に行がある_守る():
    """D0075-AC-01: docs/decisions/README.md の表の行が、番号の昇順で重ならず、リンク先が実在し、docs/decisions/ の各記録に 1 行ずつある。
    （今のまま通る。守る）"""
    problems = list_problems(read_doc(DECISIONS_README), [p.name for p in records()])
    assert problems == [], "\n".join(problems)


RECORDS = ["D0001-a.md", "D0002-b.md", "D0003-c.md"]
GOOD_TABLE = (
    "| 記録 | 題 |\n| --- | --- |\n"
    "| [D0001](D0001-a.md) | 一つ目 |\n"
    "| [D0002](D0002-b.md) | 二つ目 |\n"
    "| [D0003](D0003-c.md) | 三つ目 |\n"
)


def test_D0075_AC_02_見本_正しい表は見逃す_守る():
    """D0075-AC-02: 検査そのものの確かめ。正しい表は問題なし。（今のまま通る。守る）"""
    assert list_problems(GOOD_TABLE, RECORDS) == []
    assert [r[1] for r in list_rows(GOOD_TABLE)] == ["D0001", "D0002", "D0003"]


def test_D0075_AC_02_見本_重複の行を見つける_守る():
    """D0075-AC-02: 同じ番号の行が続くと「重なっている」を返す。（今のまま通る。守る）"""
    table = GOOD_TABLE.replace("| [D0003](D0003-c.md) | 三つ目 |\n", "| [D0002](D0002-b.md) | 二つ目の直し |\n| [D0003](D0003-c.md) | 三つ目 |\n")
    problems = list_problems(table, RECORDS)
    assert len(problems) == 1 and "重なっている" in problems[0], problems


def test_D0075_AC_02_見本_並び違いを見つける_守る():
    """D0075-AC-02: 番号が前の行より小さい行は「昇順でない」を返す（union が載せ直しで残した順の壊れ）。（今のまま通る。守る）"""
    table = "| [D0001](D0001-a.md) | 一 |\n| [D0003](D0003-c.md) | 三 |\n| [D0002](D0002-b.md) | 二 |\n"
    problems = list_problems(table, RECORDS)
    assert len(problems) == 1 and "昇順でない" in problems[0], problems


def test_D0075_AC_02_見本_リンク切れを見つける_守る():
    """D0075-AC-02: リンク先のファイルが docs/decisions/ に無い行と、行の番号とリンク先の番号が違う行を見つける。（今のまま通る。守る）"""
    problems = list_problems(GOOD_TABLE, ["D0001-a.md", "D0002-b.md"])
    assert len(problems) == 1 and "docs/decisions/ に無い" in problems[0] and "D0003-c.md" in problems[0], problems
    mismatch = GOOD_TABLE.replace("(D0002-b.md)", "(D0001-a.md)")
    assert any("番号が行の番号と違う" in p for p in list_problems(mismatch, RECORDS))


def test_D0075_AC_02_見本_行の欠けと形の崩れと衝突の印を見つける_守る():
    """D0075-AC-02: 記録があるのに行が無い・形の崩れた行・衝突の印の行を、それぞれ見つける。（今のまま通る。守る）"""
    lacking = GOOD_TABLE.replace("| [D0003](D0003-c.md) | 三つ目 |\n", "")
    assert list_problems(lacking, RECORDS) == ["D0003-c.md の行が一覧に無い"]
    broken = GOOD_TABLE.replace("| [D0002](D0002-b.md) | 二つ目 |", "| [D0002] | 二つ目 |")
    assert any("形" in p for p in list_problems(broken, RECORDS))
    conflict = GOOD_TABLE.replace("| [D0002]", "<<<<<<< HEAD\n| [D0002]")
    assert any("衝突の印" in p for p in list_problems(conflict, RECORDS))


# ---- .gitattributes の union（D0075-AC-03） ----------------------------------------------------------


def union_paths(text: str) -> list[str]:
    """merge=union を持つ行の先頭（パス）。# の行と空行は見ない。"""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if "merge=union" in parts[1:]:
            out.append(parts[0])
    return out


def test_D0075_AC_03_gitattributesが決定の記録の一覧だけをunionにしている():
    """D0075-AC-03: .gitattributes が docs/decisions/README.md を merge=union にしている。ほかのファイルには付けない（付けるのはこの 1 行だけ）。"""
    paths = union_paths(read_doc(GITATTRIBUTES))
    assert "docs/decisions/README.md" in paths, f".gitattributes に merge=union の行が無い（今ある行：{paths}）"
    assert paths == ["docs/decisions/README.md"], f"union にしてよいのは決定の記録の一覧だけ：{paths}"


def test_D0075_AC_03_見本_unionの行の拾い方はコメントと空行を見ない_守る():
    """D0075-AC-03: 検査そのものの確かめ。# の行・空行は見ず、merge=union でない属性の行は拾わない。（今のまま通る。守る）"""
    text = "# docs/other.md merge=union\n\ndocs/decisions/README.md merge=union\n*.png binary\ndocs/b.md -diff\n"
    assert union_paths(text) == ["docs/decisions/README.md"]
    assert union_paths("a.md merge=union\nb.md merge=union") == ["a.md", "b.md"]
    assert union_paths("") == []


# ---- 表の行の長さの上限（D0075-AC-04・05） -----------------------------------------------------------

ROW_LIMIT = 800


def long_rows(text: str, path: str, limit: int = ROW_LIMIT) -> list[str]:
    """「|」で始まる行（表の行）のうち、limit 字を超えるもの。本文の段落・箇条書きは見ない。"""
    return [
        f"{path} の {no} 行目の表の行が {len(line)} 字（上限 {limit}）。1 部品 1 行に割る（部品ごとに行を分け、先頭の言葉と、テストが読む語を持つ行は変えない）"
        for no, line in enumerate(text.splitlines(), 1)
        if line.startswith("|") and len(line) > limit
    ]


def test_D0075_AC_04_designの置き場所の表の行は上限を超えない():
    """D0075-AC-04: docs/development/design.md の表の行が 800 字（ROW_LIMIT）を超えない。超えたら、行の番号と字数を出して落ちる。"""
    problems = long_rows(read_doc(DESIGN_MD), "docs/development/design.md")
    assert problems == [], "\n".join(problems)


def test_D0075_AC_04_CLAUDEの表の行は上限を超えない_守る():
    """D0075-AC-04: CLAUDE.md の表の行が 800 字を超えない。（今のまま通る。守る）"""
    problems = long_rows(read_doc(CLAUDE_MD), "CLAUDE.md")
    assert problems == [], "\n".join(problems)


def test_D0075_AC_05_見本_上限を超える行を見つけ_上限内の行と本文は見逃す_守る():
    """D0075-AC-05: 検査そのものの確かめ。801 字の表の行は見つけ、800 字の行・長い本文の行・長い箇条書きは見逃す。
    メッセージは「1 部品 1 行に割る」と行の番号を伝える。（今のまま通る。守る）"""
    over = "|" + "あ" * 800  # 801 字
    exact = "|" + "あ" * 799  # 800 字
    text = f"見出し\n{over}\n{exact}\n{'本文' * 600}\n- {'箇条' * 600}\n| --- | --- |\n"
    problems = long_rows(text, "x.md")
    assert len(problems) == 1
    assert "1 部品 1 行に割る" in problems[0] and "2 行目" in problems[0] and "801 字" in problems[0] and "x.md" in problems[0]
    assert long_rows(exact, "x.md") == []
    assert len(long_rows(over, "x.md", limit=801)) == 0


# ---- 割ったあとの design.md の形（D0075-AC-06） ----------------------------------------------------------

LAYERS = ["ドメイン", "アプリケーション", "画面", "基盤", "入口"]


def cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def parts_table(md: str) -> tuple[int, list[str]]:
    """「層ごとの部品」の見出しの行の番号（0 始まり）と、その節の表の行（見出しの行・区切りの行を含む）。見出しが無ければこのテストだけを落とす。"""
    lines = md.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("#") and "層ごとの部品" in line), None)
    if start is None:
        pytest.fail("docs/development/design.md に見出し「層ごとの部品」の節が無い（拡張の部品は、この節の表に 1 部品 1 行で書く）", pytrace=False)
    rows = []
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        if line.startswith("|"):
            rows.append(line)
    return start, rows


def test_D0075_AC_06_designの層の行は最初の行に残り_部品は層ごとの部品の表に1部品1行である():
    """D0075-AC-06: 層の行（| ドメイン | など）は「層ごとの部品」の表より前にあり、その表の行は完全なパスで始まり（実在する）、第 2 列が層の名前で、
    「| ドメイン |」などでは始まらない（既存の design の行を読むテストが、今までどおり層の行に当たる）。"""
    md = read_doc(DESIGN_MD)
    start, rows = parts_table(md)
    data = rows[2:]
    assert len(data) >= 7, f"部品の行が少ない：{len(data)} 行"
    lines = md.splitlines()
    for layer in LAYERS:
        lead = f"| {layer} |"
        first = next((i for i, line in enumerate(lines) if line.startswith(lead)), None)
        assert first is not None, f"design.md に「{lead}」で始まる行が無い"
        assert first < start, f"「{lead}」の最初の行が「層ごとの部品」の表より後にある（層の行が最初の行でなければならない）"
    missing = []
    for row in data:
        assert not row.startswith(tuple(f"| {layer} |" for layer in LAYERS)), f"部品の行が層の行の形で始まっている：{row[:40]}"
        c = cells(row)
        assert len(c) >= 3, f"部品の行は 3 列：{row[:60]}"
        m = re.fullmatch(r"`([^`]+)`", c[0])
        assert m, f"第 1 列はバッククォートで囲んだ完全なパス：{c[0]}"
        if not (ROOT / m.group(1)).exists():
            missing.append(m.group(1))
        assert c[1] in LAYERS, f"第 2 列は層の名前：{c[1]}"
    assert missing == [], f"実在しないパス：{missing}"


def test_D0075_AC_06_designの画面の確認用のページは先頭の行と確認用ページの行に分かれる():
    """D0075-AC-06: 「| 画面の確認用のページ」で始まる行は 1 つだけで、ページごとの説明は「| 確認用ページ：」で始まる行に 1 行ずつ分かれる
    （D0039-AC-16 の `| 画面の確認用のページ` の探し方は今までどおり先頭の行に当たる）。"""
    lines = read_doc(DESIGN_MD).splitlines()
    heads = [line for line in lines if line.startswith("| 画面の確認用のページ")]
    parts = [line for line in lines if line.startswith("| 確認用ページ：")]
    assert len(heads) == 1, f"「| 画面の確認用のページ」で始まる行は 1 つ（今 {len(heads)} 行）"
    assert len(parts) >= 5, f"「| 確認用ページ：」の行が少ない（今 {len(parts)} 行。ページごとに 1 行に割る）"


# ---- 割る前の部品が残る（D0075-AC-07） -----------------------------------------------------------------

# 割る前の design.md の行（画面の確認用のページ・ドメイン・アプリケーション・画面・基盤・入口）のバッククォートで囲んだ語。
# 説明の言葉（バッククォートの外）は機械では見られないので、検証の段で人が前と後を見比べる。
PRE_SPLIT_TOKENS = (
    # 画面の確認用のページ
    "npm run preview", "docs/assets/README.md", ".claude/skills/pipe-in/screen-check.md", "tests/fixtures/", "state.json", "/pipe-in",
    "run-panel-budget-*", "run-panel-group-*", "group", "window.__previewExternal(kind)", "window.__previewEstimate({ today, actualUsd })",
    "vscode/scripts/preview.ts", "vscode/scripts/previewPages.ts", "vscode/scripts/artifactSamples.ts", "vscode/scripts/toolsSamples.ts",
    "vscode/scripts/budgetSamples.ts", "vscode/scripts/checkSamples.ts", "vscode/scripts/groupSamples.ts",
    # ドメイン
    "vscode/src/domain/", "driver", "hasDriver", "runRecord.ts", "calls", "stageLog.ts", "Agent", "Task", "Skill", "subagent_type", "skill",
    "defaultArtifactName", "artifacts.ts", "ViewClock", "timestamp.ts", "MM/DD HH:mm", "pipeModel.ts", "pipeWires.ts", "pipeLinks.ts",
    "pipeDrop.ts", "cableRope.ts", "pipeEdit.ts", "pipeCheck.ts", "pipeMenu.ts", "editHistory.ts", "pipeVersions.ts", "-external",
    "pipeExternal.ts", "pipeDiff.ts", "toml.ts", "archive", "runs.ts", "runList.ts", "worktrees.ts", "sessionName.ts", "session.py", "gantt.ts",
    "labelOf", "firstLogBySeq", "ownerOf", "export", "toolsTable.ts", "quiet.ts", "waitingNotice.ts", "stageBudget.ts", "stageCosts.ts",
    "costEstimate.ts", "PRICES", "DISCLAIMER", "pipe_in/usage/estimate.py", "exampleData.ts", "pipeExamples.ts", "node:path",
    # アプリケーション
    "vscode/src/app/", "WorkDirSource", "PipeStore", "VersionStore", "RunsSource", "MemoryStore", "refreshView", "resolveWorkDir",
    "externalReload.ts", "PIPE_WATCH_GLOB", "debounce.ts", "selection.ts", "refreshPolicy.ts", "staleness.ts", "names.ts", "costContext.ts",
    "notifyWaiting.ts", "workDirWatch.ts", "decideWatch", "finishStep", "createWatchHolder", "createWorkDirChecker", "vscode", "node:",
    "PRESENCE_CHECK_MS", "exampleFlow.ts", "saveTarget",
    # 画面
    "vscode/src/view/", "duration.ts", "timesHtml.ts", "runListHtml.ts", "shellHtml.ts", "ganttHtml.ts", "staleMark.ts", "rowStaleAttrs",
    "frameStyle.ts", "PAR_COLOR", "pipeEditorHtml.ts", "panelHtml.ts", "artifactsHtml.ts", "toolsHtml.ts", "markdownHtml.ts", "escapeHtml",
    "panelScript.ts", "is-stale", "money.ts", "usageHtml.ts", "costEstimateHtml.ts", "statusBar.ts", "waitNotice.ts", "externalHtml.ts",
    # 基盤
    "vscode/src/infra/", "fsWorkDirSource.ts", "fsPipes.ts", "fsVersions.ts", "stat", "lstat", ".git", "fsWorktrees.ts", "fsPresence.ts",
    "readFile", "readdir", "realpath", "readHead", "00_input.md", "readOnlyFs.ts", "node:fs", "node:fs/promises", "node:os",
    # 入口
    "vscode/src/extension.ts", "vscode.window.showInformationMessage", "render()", "notifyWaiting",
)  # fmt: skip


BACKTICKED = re.compile(r"`([^`\n]+)`")


def tokens_missing(text: str, tokens=PRE_SPLIT_TOKENS) -> list[str]:
    """text にバッククォートで囲んだ形で出てこない語。バッククォートで囲んだ完全なパスの末尾の名前
    （`vscode/src/domain/pipeWires.ts` の pipeWires.ts）も、出てきたとみなす（部品の表の第 1 列だけで足りるように。D0075 の監査 A-05）。"""
    tails = {s.rsplit("/", 1)[-1] for s in BACKTICKED.findall(text) if "/" in s.rstrip("/")}
    return [t for t in dict.fromkeys(tokens) if f"`{t}`" not in text and t not in tails]


def test_D0075_AC_07_割る前のdesignの部品の語が割ったあとにも全部ある_守る():
    """D0075-AC-07: 割る前の design.md の 6 つの行にあったバッククォートの語（パス・関数名・定数名・キー名）が、割ったあとの design.md にも全部ある。
    割る前は全部あるので今のまま通る（割ったあとに語が書き落とされたときだけ落ちる。守る）。"""
    assert len(PRE_SPLIT_TOKENS) > 100  # 見本の語が空に近くないことの確かめ（今は 144 語）
    missing = tokens_missing(read_doc(DESIGN_MD))
    assert missing == [], f"割ったあとの design.md に無い語：{missing}"


def test_D0075_AC_07_見本_書き落とした語を見つける_守る():
    """D0075-AC-07: 検査そのものの確かめ。バッククォートの外にしか無い語は、書き落としとして返す。（今のまま通る。守る）"""
    assert tokens_missing("`a.ts`・`b.ts`", ("a.ts", "b.ts")) == []
    assert tokens_missing("`a.ts`・b.ts", ("a.ts", "b.ts")) == ["b.ts"]
    assert tokens_missing("", ("x", "x")) == ["x"]
    # 完全なパスの末尾の名前は出てきたとみなす。途中の名前や、名前の一部だけでは見逃さない
    assert tokens_missing("| `vscode/src/domain/b.ts` | ドメイン | 説明 |", ("b.ts",)) == []
    assert tokens_missing("| `vscode/src/b.ts/c.ts` | 説明 |", ("b.ts",)) == ["b.ts"]
    assert tokens_missing("| `vscode/src/domain/ab.ts` | 説明 |", ("b.ts",)) == ["b.ts"]


# ---- screen-check.md は 1 行に頭を 1 つだけ書く（D0075-AC-10・11） ----------------------------------------


def crowded_heads(text: str, heads) -> list[str]:
    """1 行に、頭の形（頭のあとに -light・-dark・-*・-<…>・.html が続く形）で出る頭が 2 つ以上ある行。"""
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        found = [h for h in sorted(heads) if heads_missing(line, [h]) == []]
        if len(found) >= 2:
            out.append(f"{no} 行目に頭が {len(found)} 個並ぶ：{found}")
    return out


def test_D0075_AC_10_screen_checkは1行に頭を1つだけ書き_READMEを指す():
    """D0075-AC-10: screen-check.md が、ページの種類の頭を 1 行に 1 つだけ書き（1 行 1 頭）、頭を全部書いて docs/assets/README.md を指す
    （D0039-AC-17 の 5 つのテストは変えずに通る）。"""
    text = read_doc(SCREEN_CHECK)
    heads = real_heads()
    assert len(heads) >= 2, "previewPages.ts から PANEL_PAGES の頭が読めない"
    crowded = crowded_heads(text, heads)
    assert crowded == [], "\n".join([*crowded, "ページの種類の頭は 1 行に 1 つだけ書く（1 行 1 頭）"])
    assert screen_check_problems(text, heads) == []


def test_D0075_AC_10_見本_頭が2つ並んだ手順を見つけ_1行1頭の手順は見逃す_守る():
    """D0075-AC-10: 検査そのものの確かめ。頭が 2 つ並んだ行は見つけ、1 行 1 頭の手順・頭が無い行・完全なページ名の行は見逃す。（今のまま通る。守る）"""
    heads = {"pipe-editor", "run-panel", "run-panel-stale", "run-panel-stale-soon"}
    crowded = "`run-panel-stale-*`・`run-panel-stale-soon-*`：更新なし"
    one_each = "- `run-panel-stale-*`：更新なし\n- `run-panel-stale-soon-*`：手前\n- `pipe-editor-*`：作業台\n説明の行"
    assert len(crowded_heads(crowded, heads)) == 1
    assert crowded_heads(one_each, heads) == []
    assert [p.split(" ")[0] for p in crowded_heads("a\n" + crowded, heads)] == ["2"]
    assert crowded_heads("`run-panel-stale-soon-dark.html`", heads) == []


def test_D0075_AC_11_頭が欠けた手順のメッセージは欠けた頭と足す場所を出す_守る():
    """D0075-AC-11: 見本の手順（1 行 1 頭）から run-panel-artifacts の行を消すと、D0039-AC-17 のメッセージに、欠けた頭・
    screen-check.md の頭の一覧に 1 行足すこと・docs/assets/README.md も出る。問題が無い手順では空。（今のまま通る。守る）"""
    heads = {"pipe-editor", "run-panel", "run-panel-artifacts"}
    good = "- `pipe-editor-*`：作業台\n- `run-panel-*`：パネル\n- `run-panel-artifacts-*`：成果物\n一覧は `docs/assets/README.md`。"
    assert screen_check_message(screen_check_problems(good, heads)) == ""
    without = good.replace("- `run-panel-artifacts-*`：成果物\n", "")
    message = screen_check_message(screen_check_problems(without, heads))
    for word in ("run-panel-artifacts", "screen-check.md", "1 行", "docs/assets/README.md"):
        assert word in message, f"メッセージに「{word}」が無い：{message}"


# ---- workflow.md の節と CLAUDE.md の入口（D0075-AC-12） ----------------------------------------------------

PARALLEL_TITLE = "並列の作業でぶつからない書き方"
PARALLEL_WORDS = (
    "decision-number", "merge=union", "docs/guide/", "test_architecture_", "docs/assets/README.md", "screen-check.md", "1 部品 1 行", "800",
)  # fmt: skip


def test_D0075_AC_12_workflowに並列の作業でぶつからない書き方の節があり_足し先の決まりを書いている():
    """D0075-AC-12: workflow.md に見出し「並列の作業でぶつからない書き方」の節があり、一覧の行・節の足し先・テストを足す先・ページを足す件の手順
    （decision-number・merge=union・docs/guide/・test_architecture_・docs/assets/README.md・screen-check.md・1 部品 1 行・800）を書いている。"""
    body = need_section(read_doc(WORKFLOW_MD), PARALLEL_TITLE, where="docs/development/workflow.md")
    missing = [w for w in PARALLEL_WORDS if w not in body]
    assert missing == [], f"「{PARALLEL_TITLE}」の節に無い語：{missing}"


def test_D0075_AC_12_workflowのそろえるの節は新しい節への案内を持つ():
    """D0075-AC-12: workflow.md の「4. そろえる」の節に、足す場所は末尾でなく決まった所（「並列の作業でぶつからない書き方」の節）という案内がある。"""
    body = need_section(read_doc(WORKFLOW_MD), "そろえる", where="docs/development/workflow.md")
    assert PARALLEL_TITLE in body, f"「そろえる」の節から「{PARALLEL_TITLE}」を指していない"


def test_D0075_AC_12_CLAUDEに並列の作業でぶつからない書き方の入口の1行がある():
    """D0075-AC-12: CLAUDE.md に、「並列の作業でぶつからない書き方」を指す入口の行（workflow.md の節の名前つき）がある。"""
    lines = [line for line in read_doc(CLAUDE_MD).splitlines() if PARALLEL_TITLE in line]
    assert lines, f"CLAUDE.md に「{PARALLEL_TITLE}」の行が無い"
    assert any("docs/development/workflow.md" in line for line in lines)


# ---- 既存の D0002・D0039 の検査の関数の名前が消えない（D0075-AC-14） ---------------------------------------

D0002_TESTS = (
    "test_local_info_pattern", "test_no_local_info_in_tracked_files", "test_decision_records_have_sections", "test_ac_ids_in_tests_exist_in_records",
    "test_ac_id_pattern", "test_table_paths_pattern", "test_place_tables_point_to_real_paths", "test_watch_detects_changes", "test_watched_dirs",
    "test_watch_detects_new_place", "test_gitignore_has_both_places", "test_development_docs_exist", "test_workflow_documents_rebase",
    "test_pipe_in_rebases_when_main_moves",
)  # fmt: skip
D0039_TESTS = (
    "test_D0039_AC_15_作業台のページ名はpreview_tsのPAGESから3つ読める_守る",
    "test_D0039_AC_15_assetsのREADMEに作業台の3ページがhtml付きで出る",
    "test_D0039_AC_15_見本_食い違いを見つける検査そのものは_png_だけでは満たしたことにしない_守る",
    "test_D0039_AC_16_CLAUDEのnpm_run_previewの行は完全なページ名を並べず_種類の頭と_assets_README_を指す",
    "test_D0039_AC_16_designの画面の確認用のページの行は完全なページ名を並べず_README_を指し_作り方は残す",
    "test_D0039_AC_16_見本_完全なページ名を数える関数は2つ並んだ行を見つけ_頭は数えない_守る",
    "test_D0039_AC_17_screen_check_md_の1行に完全なページ名が2つ以上並ばない",
    "test_D0039_AC_17_screen_check_md_に出るページ名は実在するページか種類の頭に等しい",
    "test_D0039_AC_17_screen_check_md_にページの種類の頭が全部あり_一覧はREADMEを指す",
    "test_D0039_AC_17_見本_頭が1つ欠けた手順はその頭を返し_README_の指しが無い手順も見つける_守る",
    "test_D0039_AC_17_見本_実在しない名前と並びを見つけ_種類の頭は見逃さない_守る",
    "test_D0039_AC_24_決定の記録にフックで守らないと決めたことと代わりの手立てがある",
    "test_D0039_AC_32_決定の記録にallowを足した理由と受け入れたリスクがある",
    "test_D0039_AC_33_developの許可の規則の節にスキルの構成と許可の説明がある",
    "test_D0039_AC_34_workflowの進める節にスキルの構成を一文で書く",
    "test_D0039_AC_34_workflowの終える節の7にgit_mergeとmain向けのgit_pushがaskであることを書く",
    "test_D0039_AC_34_testingの画面の行の案内はscreen_check_mdを指す",
    "test_D0039_AC_35_designのスキルの行に補助ファイルのパスがある",
    "test_D0039_AC_36_CLAUDEのnpm_run_previewの行は一覧と手順の置き場所を指す",
    "test_D0039_AC_36_CLAUDEのコミットの決まりにaskで確認が出ることを足す",
    "test_D0039_AC_36_CLAUDEにスキルの構成を1文で足す",
    "test_D0039_AC_37_assetsのREADMEに作業台の3ページがhtml付きで書かれている",
    "test_D0039_AC_37_確認用のページの一覧の表で_どのページの種類の行にも画像に撮るかが書かれている",
    "test_D0039_AC_37_見本_撮るかの無い行を見つけ_表が無いREADMEは全部を欠けとして返す_守る",
    "test_D0039_AC_38_決定の記録は1つで_1行目が題_守る",
    "test_D0039_AC_38_決定の記録にAC_01から42の行がある_守る",
    "test_D0039_AC_38_決定の記録の表にD0039の行があり_前の行は小さい番号のうち最大_守る",
    "test_D0039_AC_38_決定の記録の本体に置き換えるACと残した課題の言葉がある",
    "test_D0039_AC_38_決定の記録のACの行にテストの名前か結果の言葉がある",
    "test_D0039_AC_38_見本_語の無い偽の記録はそのACを欠けとして返す_守る",
)  # fmt: skip


def defined_test_names(path: Path) -> set[str]:
    return {n.name for n in ast.parse(path.read_text(encoding="utf-8")).body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}


@pytest.mark.parametrize(
    "file,expected",
    [("test_rules.py", D0002_TESTS), ("test_skill_tidy_docs.py", D0039_TESTS)],
    ids=["D0002", "D0039"],
)
def test_D0075_AC_14_既存のD0002とD0039のテスト関数の名前が消えない_守る(file, expected):
    """D0075-AC-14: tests/test_rules.py（D0002）と tests/test_skill_tidy_docs.py（D0039）の既存のテスト関数が、名前を変えずに残る。
    （今のまま通る。守る）"""
    found = defined_test_names(TESTS / file)
    assert [n for n in expected if n not in found] == []
