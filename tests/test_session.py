"""D0019：セッション名の取り方（pipe_in/engine/session.py）と、ID・受け持ちの検査。

名前の取り方の表は tests/fixtures/session_names.json。拡張のテスト（vscode/src/domain/sessionName.test.ts）も同じファイルを読む。
pipe_in.engine.session はまだ無いので、関数の中で import する（呼んだところで落ちる）。SDK は呼ばない。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TABLE_PATH = Path(__file__).parent / "fixtures" / "session_names.json"
TABLE = json.loads(TABLE_PATH.read_text(encoding="utf-8"))


def session():
    from pipe_in.engine import session as module

    return module


def cp(text: str) -> int:
    """コードポイントの数（絵文字も 1）。"""
    return len(text)


# ---- 表そのものの確認（今の作りで通る：表の誤りを先に見つける） -------------------------------


def test_d0019_ac46_the_shared_table_is_not_empty_and_well_formed():
    """D0019-AC-46: 共通の表は空でなく、どの要素も memo（文字）と name（文字か null）を持ち、name は 60 文字以内。今の作りで通る（表の確認）。"""
    assert len(TABLE) >= 25
    for row in TABLE:
        assert set(row) == {"memo", "name"}
        assert isinstance(row["memo"], str)
        assert row["name"] is None or (isinstance(row["name"], str) and 1 <= cp(row["name"]) <= 60)


def test_d0019_ac46_the_table_covers_the_edges():
    """D0019-AC-46: 表に、60 文字ちょうど・61 文字・絵文字・空・見出しの印だけ・7 個の # が入っている。今の作りで通る（表の確認）。"""
    names = [r["name"] for r in TABLE]
    assert any(n and cp(n) == 60 and not n.endswith("…") for n in names)
    assert any(n and cp(n) == 60 and n.endswith("…") for n in names)
    assert any(n and "😀" in n for n in names)
    assert any(n is None and r["memo"].strip() == "" for n, r in zip(names, TABLE))
    assert any(n is None and r["memo"].startswith("#") for n, r in zip(names, TABLE))
    assert any(n and n.startswith("####### ") for n in names)
    assert sum(1 for n in names if n is None) >= 4


# ---- AC-46：本体と拡張が同じ表で同じ結果を返す --------------------------------------------------


@pytest.mark.parametrize("row", TABLE, ids=[f"row{i:02d}" for i in range(len(TABLE))])
def test_d0019_ac46_name_from_memo_matches_the_shared_table(row):
    """D0019-AC-46: name_from_memo が共通の表（tests/fixtures/session_names.json）の全件と一致する。拡張の nameFromMemo も同じ表を読む。"""
    assert session().name_from_memo(row["memo"]) == row["name"]


def test_d0019_ac46_the_table_row_count_is_what_the_extension_counts():
    """D0019-AC-46: 表の件数を数える（拡張のテストも同じ件数を数え、両側が同じ表を読んでいることを示す）。"""
    assert session().name_from_memo(TABLE[0]["memo"]) == TABLE[0]["name"]  # モジュールが無いうちは、ここで落ちる
    assert len(TABLE) == 32


@pytest.mark.parametrize(
    "text,want",
    [
        ("  前後と  中の   空白 ", "前後と 中の 空白"),
        ("a\t\tb　c", "a b c"),
        ("a b", "a b"),
        ("", None),
        ("   \t　 ", None),
        ("あ" * 60, "あ" * 60),
        ("あ" * 61, "あ" * 59 + "…"),
        ("😀" * 61, "😀" * 59 + "…"),
    ],
)
def test_d0019_ac46_normalize_name(text, want):
    """D0019-AC-46: normalize_name は前後の空白を落とし、連続する空白を 1 つにし、60 文字（コードポイント）を超えれば 59 文字＋…、空なら None。"""
    assert session().normalize_name(text) == want


# ---- ID・受け持ちの検査（check_token）---------------------------------------------------------------


@pytest.mark.parametrize("value", ["abc-123_DEF", "a" * 100, "7f3a9c01-2b4d-4e5f-8a6b-0c1d2e3f4a5b", "pipe-in-analyst", "日本語の受け持ち"])
def test_d0019_ac47_check_token_accepts_plain_tokens(value):
    """D0019-AC-47: 空白・制御文字を含まない 100 文字までの値は、そのまま返る。"""
    assert session().check_token(value, "セッション ID") == value


@pytest.mark.parametrize(
    "value",
    ["", " ", "   ", "a b", " abc", "abc ", "a\nb", "a\r\nb", "a\tb", "a\x00b", "a\x1fb", "a\x7fb", "a　b", "a\fb", "a\u000bb", "a" * 101, "あ" * 101],
    ids=["empty", "space", "spaces", "inner-space", "lead-space", "trail-space", "newline", "crlf", "tab", "nul", "us", "del", "ideographic-space", "formfeed", "vtab", "101-ascii", "101-cp"],
)
def test_d0019_ac47_check_token_rejects(value):
    """D0019-AC-47: 空・空白や制御文字を含む・前後の空白つき・100 文字超は ValueError（前後の空白も取らず断る）。"""
    with pytest.raises(ValueError):
        session().check_token(value, "セッション ID")


def test_d0019_ac47_check_token_error_names_what_was_checked():
    """D0019-AC-47: 断るときの文に、何を検査したか（what）が入る。"""
    with pytest.raises(ValueError, match="受け持ち"):
        session().check_token("a b", "受け持ち")


# ---- AC-50：標準ライブラリだけ ---------------------------------------------------------------


def test_d0019_ac50_session_module_uses_only_the_standard_library():
    """D0019-AC-50: pipe_in/engine/session.py は標準ライブラリだけを import する（pipe_in の他の部品にも頼らない）。"""
    import sys

    path = ROOT / "pipe_in" / "engine" / "session.py"
    assert path.is_file(), "pipe_in/engine/session.py が無い"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "相対 import（pipe_in の他の部品）は使わない"
            targets.append(node.module or "")
    outside = sorted({t.split(".")[0] for t in targets if t.split(".")[0] not in sys.stdlib_module_names and t != "__future__"})
    assert outside == []
