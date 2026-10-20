"""セッション名の取り方と、セッション ID・受け持ちの検査。標準ライブラリだけを使う。

名前の取り方は拡張（vscode/src/domain/sessionName.ts）と同じ規則で、同じ表（tests/fixtures/session_names.json）で確かめる。
空白は Python の isspace や JS の \\s に頼らず、次の字に決めて両側でそろえる。
"""

from __future__ import annotations

import re

NAME_LIMIT = 60
TOKEN_LIMIT = 100

# 空白として扱う字（半角空白・タブ・改行・改ページ・垂直タブ・全角空白）
_WS = " \t\r\n\f\v　"
_WS_RUN = re.compile(f"[{_WS}]+")
_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_HEADING_MARK = re.compile(f"^#{{1,6}}(?:[{_WS}]+|$)")
_BAD_TOKEN_CHAR = re.compile(f"[\x00-\x1f\x7f{_WS}]")


def normalize_name(text: str) -> str | None:
    """前後の空白を落とし、中の連続する空白を 1 つにし、60 文字を超えるときは 59 文字＋「…」にする。空なら None。"""
    s = _WS_RUN.sub(" ", text.strip(_WS)).strip(_WS)
    if not s:
        return None
    return s if len(s) <= NAME_LIMIT else s[: NAME_LIMIT - 1] + "…"


def name_from_memo(memo: str) -> str | None:
    """要件メモの最初の「空白だけでない行」から名前を作る。先頭の見出しの印（# を 1〜6 個と空白）は 1 回だけ取る。"""
    for line in _LINE_BREAK.split(memo):
        line = line.strip(_WS)
        if not line:
            continue
        return normalize_name(_HEADING_MARK.sub("", line, count=1))
    return None


def check_token(value: str, what: str) -> str:
    """セッション ID・受け持ちの検査。空・空白や制御文字を含む・100 文字超は ValueError（前後の空白も取らず断る）。"""
    if not value:
        raise ValueError(f"{what}が空です")
    if _BAD_TOKEN_CHAR.search(value):
        raise ValueError(f"{what}に空白や制御文字は使えません")
    if len(value) > TOKEN_LIMIT:
        raise ValueError(f"{what}は {TOKEN_LIMIT} 文字までです")
    return value
