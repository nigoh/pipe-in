"""実行パネルの返事のファイル（reply.json）を読む・今の待ちと照らす・消す部品と、端末の行の元（D0079）。

確認の待ちの間、人は端末に答えるか、パネルのボタンで返事のファイルを置くかを選べる。
この部品は、返事のファイルの読み取り（中身の検査・今の待ちとの照合・消し方）と、端末の 1 行を
頼まれたときだけ読む行の元を持つ。返事を作るのは拡張だけで、本体は読んで消すだけ。

読んでよいのは標準ライブラリと live_answer の定数だけ（checkpoint などは読まない）。
返事の中の文字は、断る理由の文にも端末に出す文にも入れない（理由は決まった語だけ）。
"""

from __future__ import annotations

import json
import os
import queue
import secrets
import stat
import sys
import threading
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, Protocol

from .live_answer import ID_RE, MAX_FEEDBACK, READ_LIMIT, STAGE_RE

REPLY_FILE = "reply.json"  # 実行のフォルダ直下のファイル名
VERSION = 1
MAX_BYTES = READ_LIMIT  # ファイル全体の上限（バイト）
POLL_SEC = 0.5  # 待ちの繰り返しの間隔（秒）
ACTIONS: tuple[str, ...] = ("approve", "revise", "quit")

# 中身を読んで断る理由
PARSE_REASONS: tuple[str, ...] = (
    "not_utf8",
    "not_json",
    "not_object",
    "missing_key",
    "extra_key",
    "bad_version",
    "bad_type",
    "bad_action",
    "bad_stage",
    "bad_id",
    "feedback_not_allowed",
    "need_feedback",
    "feedback_too_long",
    "bad_chars",
)
# ファイルとして断る理由（too_large は parse_reply にバイト列が来たときも同じ名前）
FILE_REASONS: tuple[str, ...] = ("unreadable", "not_regular", "too_large")
# 今の待ちと合わない理由
MATCH_REASONS: tuple[str, ...] = ("stage_mismatch", "id_mismatch")
# 書きかけかもしれない理由（2 回続けて同じ中身が見えるまで断らない）
INCOMPLETE: tuple[str, ...] = ("not_utf8", "not_json")

# 端末に出す固定の文（入力の文字は入れない）
REASON_TEXT: dict[str, str] = {
    "not_utf8": "UTF-8 の文字として読めません",
    "not_json": "JSON として読めません",
    "not_object": "JSON のオブジェクトではありません",
    "missing_key": "必要な項目が足りません",
    "extra_key": "知らない項目があります",
    "bad_version": "版が合いません",
    "bad_type": "項目の型が合いません",
    "bad_action": "動作が承認・修正の依頼・中止のどれでもありません",
    "bad_stage": "段の名前の形が正しくありません",
    "bad_id": "識別子の形が正しくありません",
    "feedback_not_allowed": "承認と中止に直してほしい点は付けられません",
    "need_feedback": "修正の依頼には直してほしい点が要ります",
    "feedback_too_long": "直してほしい点が長すぎます",
    "bad_chars": "直してほしい点に使えない文字があります",
    "unreadable": "ファイルを読めません",
    "not_regular": "通常のファイルではありません",
    "too_large": "ファイルが大きすぎます",
    "stage_mismatch": "今の確認の段と合いません",
    "id_mismatch": "今の確認の待ちと合いません（前の待ちの返事かもしれません）",
}

_REQUIRED = ("version", "stage", "id", "action")
_BAD_CATEGORIES = ("Cc", "Cf", "Cs", "Zl", "Zp")


class ReplyResult(NamedTuple):
    ok: bool
    action: str | None  # "approve" | "revise" | "quit"
    stage: str | None
    id: str | None
    feedback: str | None  # revise だけ（前後の空白を取ってから返す）。ほかは None
    reason: str | None  # ok のとき None。ほかは PARSE_REASONS か FILE_REASONS の 1 つ


class FileRead(NamedTuple):
    kind: str  # "absent" | "ok" | "refused"
    data: bytes | None  # kind == "ok" のとき
    reason: str | None  # kind == "refused" のとき FILE_REASONS の 1 つ


def _refuse(reason: str) -> ReplyResult:
    return ReplyResult(False, None, None, None, None, reason)


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("鍵の重複")
        out[key] = value
    return out


def _check_feedback(value: object) -> tuple[str | None, str | None]:
    """修正の依頼の直してほしい点を検める。(前後の空白を取った文字, 断る理由)。順は拡張の checkReplyChoice と同じ
    （文字でないときの理由の語だけ違う：ここは bad_type、拡張は need_feedback）。"""
    if not isinstance(value, str):
        return None, "bad_type"
    for ch in value:
        if ch in "\n\t":
            continue
        if unicodedata.category(ch) in _BAD_CATEGORIES:
            return None, "bad_chars"
    text = value.strip()
    if not text:
        return None, "need_feedback"
    if len(text) > MAX_FEEDBACK:
        return None, "feedback_too_long"
    return text, None


def parse_reply(data: bytes) -> ReplyResult:
    """返事の中身を検める。例外を出さない。"""
    try:
        return _parse(data)
    except Exception:
        return _refuse("not_json")


def _parse(data: bytes) -> ReplyResult:
    if not isinstance(data, bytes):
        return _refuse("not_json")
    if len(data) > MAX_BYTES:
        return _refuse("too_large")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return _refuse("not_utf8")
    try:
        body = json.loads(text, object_pairs_hook=_no_duplicates)
    except (ValueError, RecursionError):
        return _refuse("not_json")
    if not isinstance(body, dict):
        return _refuse("not_object")
    if any(key not in body for key in _REQUIRED):
        return _refuse("missing_key")
    if any(key not in _REQUIRED and key != "feedback" for key in body):
        return _refuse("extra_key")
    version = body["version"]
    if type(version) is not int or version != VERSION:
        return _refuse("bad_version")
    action, stage, wait_id = body["action"], body["stage"], body["id"]
    if not (isinstance(action, str) and isinstance(stage, str) and isinstance(wait_id, str)):
        return _refuse("bad_type")
    if action not in ACTIONS:
        return _refuse("bad_action")
    if STAGE_RE.fullmatch(stage) is None:
        return _refuse("bad_stage")
    if ID_RE.fullmatch(wait_id) is None:
        return _refuse("bad_id")
    feedback: str | None = None
    if action == "revise":
        if "feedback" not in body:
            return _refuse("need_feedback")
        feedback, reason = _check_feedback(body["feedback"])
        if reason is not None:
            return _refuse(reason)
    elif "feedback" in body:
        return _refuse("feedback_not_allowed")
    return ReplyResult(True, action, stage, wait_id, feedback, None)


def match_wait(result: ReplyResult, stage: str, wait_id: str) -> str | None:
    """読めた返事を今の待ちと照らす。合えば None。段が先、識別子があと。"""
    if result.stage != stage:
        return "stage_mismatch"
    if result.id != wait_id:
        return "id_mismatch"
    return None


def read_reply_file(path: Path) -> FileRead:
    """返事のファイルを読む。リンクの先は読まない。例外を出さない。"""
    try:
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            return FileRead("absent", None, None)
        if not stat.S_ISREG(info.st_mode):
            return FileRead("refused", None, "not_regular")
        if info.st_size > MAX_BYTES:
            return FileRead("refused", None, "too_large")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(path, flags)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return FileRead("refused", None, "not_regular")
            chunks: list[bytes] = []
            total = 0
            while total <= MAX_BYTES:
                chunk = os.read(fd, MAX_BYTES + 1 - total)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
        finally:
            os.close(fd)
        data = b"".join(chunks)
        if len(data) > MAX_BYTES:
            return FileRead("refused", None, "too_large")
        return FileRead("ok", data, None)
    except FileNotFoundError:
        return FileRead("absent", None, None)
    except OSError:
        return FileRead("refused", None, "unreadable")
    except Exception:
        return FileRead("refused", None, "unreadable")


def remove_reply(path: Path) -> bool:
    """返事のファイルを消す。無ければ True。os.unlink だけで消す（フォルダは消さない）。消せなくても例外を出さない。"""
    try:
        os.lstat(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    try:
        os.unlink(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def new_wait_id(token_hex: Callable[[int], str] = secrets.token_hex) -> str:
    """待ちごとの識別子（40 ビットの乱数。10 文字の 16 進）。時計には頼らない。"""
    return token_hex(5)


class ReplyPoller:
    """返事のファイルの 1 回ごとの確かめ。前回の様子（書きかけの中身・直前に出した理由）を持つ。"""

    def __init__(
        self,
        path: Path,
        stage: str,
        wait_id: str,
        *,
        read_file: Callable[[Path], FileRead] = read_reply_file,
        remove: Callable[[Path], bool] = remove_reply,
        say: Callable[[str], None] = print,
    ) -> None:
        self.path = path
        self.stage = stage
        self.wait_id = wait_id
        self.read_file = read_file
        self.remove = remove
        self.say = say
        self._partial: bytes | None = None  # 書きかけかもしれない中身（前回見えたもの）
        self._last_reason: str | None = None  # 直前に出した理由

    def _reject(self, reason: str) -> None:
        if reason != self._last_reason:
            self.say(f"\n  返事のファイルを使いませんでした：{REASON_TEXT[reason]}（{reason}）。待ち続けます。")
            self._last_reason = reason
        self.remove(self.path)

    def check(self) -> ReplyResult | None:
        got = self.read_file(self.path)
        if got.kind == "absent":
            self._partial = None
            self._last_reason = None
            return None
        if got.kind == "refused":
            self._partial = None
            self._reject(got.reason or "unreadable")
            return None
        data = got.data if got.data is not None else b""
        result = parse_reply(data)
        if not result.ok:
            reason = result.reason or "not_json"
            if reason in INCOMPLETE and self._partial != data:
                self._partial = data  # 書いている途中かもしれない。覚えるだけ
                return None
            self._partial = None
            self._reject(reason)
            return None
        self._partial = None
        mismatch = match_wait(result, self.stage, self.wait_id)
        if mismatch is not None:
            self._reject(mismatch)
            return None
        self.remove(self.path)  # 消せなくても進む
        return result


def read_terminal_line() -> str:
    """端末から 1 行読む（input() は使わない）。EOF・読めない例外は EOFError。末尾の改行は 1 つ取る。"""
    try:
        raw = sys.stdin.buffer.raw.readline()
    except (OSError, ValueError, AttributeError):
        raise EOFError from None
    if not raw:
        raise EOFError
    encoding = getattr(sys.stdin, "encoding", None) or "utf-8"
    try:
        text = raw.decode(encoding, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    if text.endswith("\n"):
        text = text[:-1]
        if text.endswith("\r"):
            text = text[:-1]
    return text


def stdin_is_terminal() -> bool:
    """標準入力が端末で、生の読み（buffer.raw）を持つときだけ真。例外は偽。"""
    try:
        stdin = sys.stdin
        if stdin is None or not stdin.isatty():
            return False
        return getattr(getattr(stdin, "buffer", None), "raw", None) is not None
    except Exception:
        return False


class LineSource(Protocol):
    def drain(self) -> None: ...

    def get(self, timeout: float) -> str | None: ...


class ThreadLineSource:
    """別のスレッドで端末の 1 行を読む行の元。頼まれたときだけ 1 回読み、読み続けない。

    時間切れで読みが残ったときは、重ねて頼まない。待ちの外で届いた行は drain で捨てる。"""

    def __init__(self, read_line: Callable[[], str]) -> None:
        self._read_line = read_line
        self._requests: queue.Queue[int] = queue.Queue()
        self._results: queue.Queue[tuple[str, str]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._pending = False  # 頼んだ読みがまだ済んでいない
        self._eof = False

    def _work(self) -> None:
        while True:
            self._requests.get()
            try:
                line = self._read_line()
            except Exception:  # EOFError も、読めない例外も、EOF と同じ
                self._results.put(("eof", ""))
                continue
            self._results.put(("line", line))

    def _request(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._work, name="pipe-in-reply-stdin", daemon=True)
            self._thread.start()
        self._pending = True
        self._requests.put(1)

    def drain(self) -> None:
        """待ちの外で届いた行を捨てる。EOF の印は残す。"""
        while True:
            try:
                kind, _ = self._results.get_nowait()
            except queue.Empty:
                return
            self._pending = False
            if kind == "eof":
                self._eof = True

    def get(self, timeout: float) -> str | None:
        if self._eof:
            raise EOFError
        if not self._pending:
            self._request()
        try:
            kind, line = self._results.get(timeout=timeout)
        except queue.Empty:
            return None
        self._pending = False
        if kind == "eof":
            self._eof = True
            raise EOFError
        return line


@dataclass
class ReplyEnv:
    read_line: Callable[[], str] = read_terminal_line
    lines: LineSource | None = None  # None なら最初の使用で ThreadLineSource(read_line) を作って持つ
    interactive: Callable[[], bool] = stdin_is_terminal
    new_id: Callable[[], str] = new_wait_id
    read_file: Callable[[Path], FileRead] = read_reply_file
    remove: Callable[[Path], bool] = remove_reply
    say: Callable[[str], None] = print
    interval: float = POLL_SEC

    def usable(self) -> bool:
        """返事のファイルを受け付けてよいか。行の元が差し替えられているか、標準入力が端末のときだけ。"""
        return self.lines is not None or self.interactive()

    def line_source(self) -> LineSource:
        if self.lines is None:
            self.lines = ThreadLineSource(self.read_line)
        return self.lines


@dataclass
class ReplyWait:
    path: Path
    stage: str
    wait_id: str
    env: ReplyEnv
