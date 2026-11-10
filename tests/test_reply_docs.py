"""D0079-AC-68・69：返事のファイル（実行パネルのボタン）の決まりを、文書と決定の記録にそろえてあること。

文書の文は細かい言い回しで縛らず、決めた語（reply.json・fsReplies.ts・D0079）が出ることを見る。
行の長さの上限（800 字）・決定の記録の形・README の一覧の順は、既存の test_doc_shape.py・test_rules.py が見る（守る）。
決定の記録 docs/decisions/D0079-reply-from-panel.md は実装の段で書くので、今は無く、関係するテストは落ちる。
読むだけで、ファイルは書かない。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECORD = "docs/decisions/D0079-reply-from-panel.md"
AC_ID = re.compile(r"\bD0079-AC-\d{2,3}\b")


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def line_with(text: str, phrase: str) -> str | None:
    """phrase を含む最初の行。無ければ None。"""
    for line in text.splitlines():
        if phrase in line:
            return line
    return None


def ids_in(text: str) -> set[str]:
    return set(AC_ID.findall(text))


def test_検査そのものが_行と_ID_を見つける():
    """D0079-AC-68: 検査そのもの：行の探し方は語を含む最初の行を返し、無ければ None。ID の拾い方は 2 桁と 3 桁を拾い、1 桁は拾わない。"""
    assert line_with("あ\nい 語 う\nえ 語\n", "語") == "い 語 う"
    assert line_with("あ\n", "語") is None
    head = "D0079-AC-"  # ID そのものをテストの文に書くと、記録に無い ID として拾われるので、組み立てて作る
    sample = f"{head}01 と {head}100 と {head}1 と D0078-AC-01"
    assert ids_in(sample) == {f"{head}01", f"{head}100"}


@pytest.mark.parametrize(
    "rel,phrase",
    [
        ("CLAUDE.md", "拡張は work_dir を読むだけで書かない"),
        ("docs/development/design.md", "拡張は work_dir を読むだけで書きません"),
    ],
)
def test_拡張の書き込みの決まりに返事のファイルの例外がある(rel: str, phrase: str):
    """D0079-AC-68: CLAUDE.md と docs/development/design.md の「拡張は work_dir を読むだけで書かない」の決まりの箇条書きに、
    返事のファイル（reply.json）の例外・それを絞る口（fsReplies.ts）・決定の記録（D0079）が書かれている。"""
    line = line_with(read(rel), phrase)
    assert line is not None, f"{rel} に「{phrase}」の行が無い"
    for word in ("reply.json", "fsReplies.ts", "D0079"):
        assert word in line, f"{rel} の決まりの行に「{word}」が無い"


def test_決まりの文が指すソースが実在する():
    """D0079-AC-68: 決まりの文が書く書き込みの口 vscode/src/infra/fsReplies.ts がソースにある（決まりの文とソースが食い違わない）。"""
    assert (ROOT / "vscode/src/infra/fsReplies.ts").is_file()


def test_design_md_の置き場所の表に返事の部品と共通の表がある():
    """D0079-AC-68: docs/development/design.md の置き場所の表に、返事のファイルを読む部品（pipe_in/engine/reply.py）と
    共通の表（tests/fixtures/reply_file.json）の行がある。互換の項に state.json の reply_wait と予約名 reply.json の記述がある。"""
    text = read("docs/development/design.md")
    rows = [line for line in text.splitlines() if line.startswith("|")]
    assert any("pipe_in/engine/reply.py" in r for r in rows), "置き場所の表に pipe_in/engine/reply.py の行が無い"
    assert any("tests/fixtures/reply_file.json" in r for r in rows), "置き場所の表に tests/fixtures/reply_file.json の行が無い"
    assert "reply_wait" in text and "RESERVED_OUTPUTS" in text


def test_決定の記録が実在し_形と一覧の行がある():
    """D0079-AC-69: 決定の記録 docs/decisions/D0079-reply-from-panel.md があり、1 行目が「# D0079 …」で、reply.json・fsReplies.ts・
    approve と approved の違いを書いている。docs/decisions/README.md の一覧に D0079 の行が 1 つある。"""
    path = ROOT / RECORD
    assert path.is_file(), f"{RECORD} が無い"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# D0079 ")
    for word in ("reply.json", "fsReplies.ts", "approved", "approve"):
        assert word in text, f"決定の記録に「{word}」が無い"
    rows = [line for line in read("docs/decisions/README.md").splitlines() if re.match(r"\| \[D0079\]\(D0079-[a-z0-9-]+\.md\) \|", line)]
    assert len(rows) == 1, f"README の一覧の D0079 の行が {len(rows)} 個"
    assert "D0079-reply-from-panel.md" in rows[0]


def test_テストに書いた_D0079_の_ID_はすべて決定の記録の中にある():
    """D0079-AC-69: tests/ と vscode/src/ のテストに書いた D0079-AC-xx は、すべて決定の記録の中にある
    （記録が無いときは落ちる。既存の test_rules.py の検査と同じ見方を、この機能の ID に絞って先に見る）。"""
    path = ROOT / RECORD
    assert path.is_file(), f"{RECORD} が無い"
    defined = ids_in(path.read_text(encoding="utf-8"))
    sources = [*(ROOT / "tests").glob("test_*.py"), *(ROOT / "vscode" / "src").rglob("*.test.ts")]
    missing: list[str] = []
    for src in sources:
        for ac in ids_in(src.read_text(encoding="utf-8")) - defined:
            missing.append(f"{src.relative_to(ROOT).as_posix()}: {ac}")
    assert sorted(missing) == []
