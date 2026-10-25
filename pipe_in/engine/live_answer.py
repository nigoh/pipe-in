"""ページから送られる答えの文（承認・差し戻し・中止）を作る・読む・記録と照らす。

- 文の形、確認待ちの識別子、記録との照らし合わせ、コマンドの出力の形を、ここだけに持つ。
- 標準ライブラリだけを使う葉の部品（pipe_in のほかの部品を読まない）。ファイルには触れない。
- 文は厳しく読む。直したり推し量ったりせず、変な文字は取り除かずに断る。
  人が手で書いたコメントが動作になる道を作らないため。
- 読み取りは例外を出さない。断る理由は決まった一覧の文字だけで、入力の文字は入れない。
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, NamedTuple

SENTINEL = "pipe-in: "  # 1行目の頭（コロンの後ろに空白1個）
WIRE = {"approve": "approved", "revise": "revise", "quit": "quit"}  # 文の動作 → record review の言葉
ACTIONS = ("approved", "revise", "quit")  # build_answer・parse_answer が使う言葉（record review と同じ）
STAGE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}")  # fullmatch で使う
ID_RE = re.compile(r"[0-9a-f]{10}")  # fullmatch で使う
MAX_RAW = 4000  # 前後の空白を含む入力の上限（超えたら中を見ずに too_long。巨大な入力を走査しない）
MAX_TEXT = 2000  # 前後の空白を取った全体（コードポイント）
MAX_FEEDBACK = 1000  # 直してほしい点（前後の空白を取ったあと。コードポイント）
READ_LIMIT = 16384  # コマンドが入力ファイル・標準入力から読むバイト数の上限
MAX_SINCE = 64  # 識別子の元にする since の長さの上限

PARSE_REASONS = (
    "empty", "too_long", "bad_chars", "bad_format", "bad_action", "bad_stage", "bad_id",
    "extra_lines", "need_feedback", "feedback_too_long",
)  # fmt: skip
CHECK_REASONS = ("no_record", "finished", "not_pending", "stage_mismatch", "id_mismatch", "no_id")
IO_REASONS = ("unreadable", "input_too_large", "write_failed")  # コマンドだけが出す

_OUTER = " \t\n"  # 全体の前後で取る文字（ASCII の空白・タブ・改行だけ）
_BAD_CATEGORIES = frozenset(("Cc", "Cf", "Cs", "Zl", "Zp"))


class ParseResult(NamedTuple):
    ok: bool
    action: str | None  # "approved" | "revise" | "quit"
    stage: str | None
    id: str | None
    feedback: str | None  # revise だけ（前後の空白を取った人の言葉）。それ以外は None
    reason: str | None  # ok のときは None、そうでなければ PARSE_REASONS のどれか


def _refuse(reason: str) -> ParseResult:
    return ParseResult(False, None, None, None, None, reason)


def valid_stage(stage: Any) -> bool:
    """段の名前が答えの文の形に合うか。"""
    return type(stage) is str and STAGE_RE.fullmatch(stage) is not None


def _has_bad_char(text: str) -> bool:
    """制御・書式・孤立サロゲート・行区切りがあるか。例外は改行と、2行目以降のタブだけ。"""
    first_end = text.find("\n")
    if first_end < 0:
        first_end = len(text)
    for i, ch in enumerate(text):
        if ch == "\n":
            continue
        if ch == "\t" and i > first_end:
            continue
        if unicodedata.category(ch) in _BAD_CATEGORIES:
            return True
    return False


def parse_answer(text: Any) -> ParseResult:
    """答えの文を読む。例外を出さない。規則は設計 3.2 の順（上から最初に当たった理由で断る）。"""
    try:
        return _parse(text)
    except Exception:  # noqa: BLE001 - 想定外も「答えではない」にする
        return _refuse("bad_format")


def _parse(text: Any) -> ParseResult:
    if type(text) is not str:
        return _refuse("bad_format")
    if len(text) > MAX_RAW:
        return _refuse("too_long")
    body = text.replace("\r\n", "\n").strip(_OUTER)
    if not body:
        return _refuse("empty")
    if len(body) > MAX_TEXT:
        return _refuse("too_long")
    if _has_bad_char(body):
        return _refuse("bad_chars")
    lines = body.split("\n")
    head = lines[0].rstrip(" ")
    if not head.startswith(SENTINEL):
        return _refuse("bad_format")
    tokens = head[len(SENTINEL):].split(" ")
    if len(tokens) > 3:
        return _refuse("bad_format")
    if len(tokens) < 3:
        # 空白でない文字で語がつながっている形（全角空白・NBSP など）は bad_format
        if tokens[0] not in WIRE or (len(tokens) == 2 and STAGE_RE.fullmatch(tokens[1]) is None):
            return _refuse("bad_format")
        tokens += [""] * (3 - len(tokens))  # 段・識別子が無い形は bad_stage・bad_id で断る
    word, stage, answer_id = tokens
    if word not in WIRE:
        return _refuse("bad_action")
    if STAGE_RE.fullmatch(stage) is None:
        return _refuse("bad_stage")
    if ID_RE.fullmatch(answer_id) is None:
        return _refuse("bad_id")
    rest = lines[1:]
    if word != "revise":
        if rest:
            return _refuse("extra_lines")
        return ParseResult(True, WIRE[word], stage, answer_id, None, None)
    feedback = "\n".join(rest).strip()
    if not feedback:
        return _refuse("need_feedback")
    if len(feedback) > MAX_FEEDBACK:
        return _refuse("feedback_too_long")
    return ParseResult(True, "revise", stage, answer_id, feedback, None)


def build_answer(action: Any, stage: Any, id: Any, feedback: Any = None) -> str:
    """答えの文を作る。形に合わないときは ValueError。作った文は parse_answer に通して確かめる。"""
    if type(action) is not str or action not in ACTIONS:
        raise ValueError("action が違います")
    if not valid_stage(stage):
        raise ValueError("stage の形が違います")
    if type(id) is not str or ID_RE.fullmatch(id) is None:
        raise ValueError("id の形が違います")
    word = {v: k for k, v in WIRE.items()}[action]
    if action == "revise":
        if type(feedback) is not str:
            raise ValueError("revise には直してほしい点が要ります")
        text = f"{SENTINEL}{word} {stage} {id}\n{feedback}"
    else:
        if feedback is not None:
            raise ValueError("直してほしい点は revise だけです")
        text = f"{SENTINEL}{word} {stage} {id}"
    result = parse_answer(text)
    if not result.ok or result.action != action or result.stage != stage or result.id != id:
        raise ValueError("読み取りを通らない文になります")
    return text


def review_id(stage: Any, since: Any) -> str | None:
    """確認待ちの識別子（10 文字の 16 進）。段の名前と since（記録の文字のまま）から作る。作れなければ None。"""
    if not valid_stage(stage):
        return None
    if type(since) is not str or not since or len(since) > MAX_SINCE:
        return None
    try:
        data = ("pipe-in:review\n" + stage + "\n" + since).encode("utf-8")
    except UnicodeEncodeError:  # 孤立サロゲートなど
        return None
    return hashlib.sha256(data).hexdigest()[:10]


def check_answer(state: Any, stage: Any, answer_id: Any) -> str | None:
    """記録（state.json の中身）と照らす。合えば None、断るなら CHECK_REASONS のどれか。純粋。"""
    if not isinstance(state, dict):
        return "no_record"
    if state.get("final") is not None:
        return "finished"
    pending = state.get("pending_review")
    if not isinstance(pending, dict):
        return "not_pending"
    pending_stage = pending.get("stage")
    if type(pending_stage) is not str or type(stage) is not str or pending_stage != stage:
        return "stage_mismatch"
    expected = review_id(stage, pending.get("since"))
    if expected is None:
        return "no_id"
    if type(answer_id) is not str or expected != answer_id:
        return "id_mismatch"
    return None


def format_result(ok: Any, action: Any, stage: Any, id: Any, reason: Any) -> str:
    """標準出力の1行（キー5つ・順は固定・ASCII だけ・隙間なし・末尾に改行）。"""
    obj = {"ok": ok, "action": action, "stage": stage, "id": id, "reason": reason}
    return json.dumps(obj, ensure_ascii=True, separators=(",", ":")) + "\n"
