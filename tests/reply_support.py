"""D0079 の返事のファイル（reply.json）のテストが使う補助。

- 共通の表 tests/fixtures/reply_file.json を読む・表の行から返事の中身（バイト列）を作る。
- 返事を作る補助は、ここで json.dumps する（本体は返事を作る関数を持たない。作るのは拡張だけ）。
- 偽の行の元：決めた順に 行・時間切れ・EOF を返し、受け取った待ち時間を覚える。眠らない。
- 止めておける偽の読み：本物の ThreadLineSource（頼まれたときだけ読むスレッド）の単体のテスト用。
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TABLE_PATH = ROOT / "tests" / "fixtures" / "reply_file.json"

STAGE = "requirements"
WAIT_ID = "a1b2c3d4e5"
OTHER_ID = "0f0f0f0f0f"


def load_table() -> dict[str, Any]:
    return json.loads(TABLE_PATH.read_text(encoding="utf-8"))


TABLE = load_table()


# ---- 表の行から中身を作る ------------------------------------------------------------------------------


def make_text(action: str, stage: str = STAGE, wait_id: str = WAIT_ID, feedback: str | None = None) -> str:
    """返事の中身（拡張が作る形：鍵の順 version, stage, id, action, feedback。隙間なし・末尾に改行なし・日本語はそのまま）。

    feedback は前後の空白を取ってから書く（拡張と同じ）。"""
    body: dict[str, Any] = {"version": 1, "stage": stage, "id": wait_id, "action": action}
    if feedback is not None:
        body["feedback"] = feedback.strip()
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def reply_bytes(action: str, stage: str = STAGE, wait_id: str = WAIT_ID, feedback: str | None = None) -> bytes:
    return make_text(action, stage, wait_id, feedback).encode("utf-8")


def write_reply(path: Path, action: str, stage: str = STAGE, wait_id: str = WAIT_ID, feedback: str | None = None) -> None:
    path.write_bytes(reply_bytes(action, stage, wait_id, feedback))


def long_feedback(row: dict[str, Any]) -> str:
    """valid_long・invalid_long・refused_build_long の行の、直してほしい点（pad があれば前後に付ける）。"""
    rep = row["feedback_repeat"]
    pad = row.get("pad", "")
    return pad + rep["unit"] * rep["count"] + pad


def hand_long_bytes(row: dict[str, Any]) -> bytes:
    """手で書かれた形（前後の空白を取らずに書く）で、valid_long・invalid_long の行から返事を作る。"""
    body = {
        "version": 1,
        "stage": row.get("stage", "design"),
        "id": row.get("id", WAIT_ID),
        "action": "revise",
        "feedback": long_feedback(row),
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def invalid_bytes(row: dict[str, Any]) -> bytes:
    """invalid の行（text か bytes_hex。prefix_hex・pad_to_bytes つき）のバイト列。"""
    if "bytes_hex" in row:
        return bytes.fromhex(row["bytes_hex"])
    data = bytes.fromhex(row.get("prefix_hex", "")) + row["text"].encode("utf-8")
    want = row.get("pad_to_bytes")
    if want is not None:
        assert len(data) <= want, "pad_to_bytes が中身より小さい"
        data += b" " * (want - len(data))
    return data


def feedback_bytes(fb_escaped: str) -> bytes:
    """invalid_feedback の行：fb（JSON の文字列の中身そのまま）を修正の依頼の feedback に入れた返事。"""
    text = f'{{"version":1,"stage":"{STAGE}","id":"{WAIT_ID}","action":"revise","feedback":"{fb_escaped}"}}'
    return text.encode("utf-8")


def strings_in(value: Any) -> list[str]:
    """JSON の値の中の文字（鍵も値も）を全部集める。返事の文字が端末の文に混ざっていないかの検査用。"""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in (strings_in(k) + strings_in(v))]
    if isinstance(value, list):
        return [s for v in value for s in strings_in(v)]
    return []


# ---- 偽の行の元 ----------------------------------------------------------------------------------------


class Do:
    """行の元の get が呼ばれたとき、fn を実行してから時間切れ（None）を返す。

    待ちの繰り返しは「get が時間切れ → 返事のファイルを 1 回確かめる」なので、
    fn の中で返事のファイルを置く・書き換える・state.json を読む、といった操作を差し込める。"""

    def __init__(self, fn: Callable[[], Any]) -> None:
        self.fn = fn


class ScriptLines:
    """決めた順に 行（文字）・時間切れ（None）・EOF（EOFError）・操作（Do）を返す行の元。眠らない。

    受け取った待ち時間（timeouts）と、drain/get の呼ばれた順（events）を覚える。
    用意した分が尽きたら AssertionError にする（待ちが終わらないまま回り続けるのを防ぐ）。"""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.timeouts: list[float] = []
        self.events: list[str] = []

    @property
    def drained(self) -> int:
        return self.events.count("drain")

    def drain(self) -> None:
        self.events.append("drain")

    def get(self, timeout: float) -> str | None:
        self.timeouts.append(timeout)
        self.events.append("get")
        if not self.script:
            raise AssertionError("偽の行の元：用意した分が尽きました（待ちが終わらずに回り続けている）")
        item = self.script.pop(0)
        if isinstance(item, Do):
            item.fn()
            return None
        if item is None:
            return None
        if isinstance(item, BaseException) or (isinstance(item, type) and issubclass(item, BaseException)):
            raise item
        return item


def id_source(prefix: str = "") -> Callable[[], str]:
    """呼ぶたびに別の 10 文字の 16 進を返す（待ちごとの識別子の偽物）。"""
    count = [0]

    def new_id() -> str:
        count[0] += 1
        return f"{prefix}{count[0]:010x}"[-10:]

    return new_id


class FlakyRemove:
    """最初の fail_times 回は消せない（False）。そのあとは本物の unlink で消す。呼ばれた回数を覚える。"""

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def __call__(self, path: Path) -> bool:
        self.calls += 1
        if self.calls <= self.fail_times:
            return False
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return True


# ---- 止めておける偽の読み（ThreadLineSource の単体のテスト用） --------------------------------------------


class BlockingReader:
    """ThreadLineSource に渡す read_line の偽物。put された行（や EOFError）が来るまで読みの中で止まる。

    読みが呼ばれた回数（calls）と、「n 回目の読みが始まった」を待つ道（wait_calls）を持つ。
    眠らない（待つのは条件変数）。put されないまま 10 秒たったら EOFError で抜ける（テストが止まり続けない）。"""

    def __init__(self) -> None:
        self.inbox: queue.Queue[Any] = queue.Queue()
        self.calls = 0
        self.returned = 0
        self._cv = threading.Condition()

    def __call__(self) -> str:
        with self._cv:
            self.calls += 1
            self._cv.notify_all()
        try:
            item = self.inbox.get(timeout=10)
        except queue.Empty:
            raise EOFError from None
        with self._cv:
            self.returned += 1
            self._cv.notify_all()
        if isinstance(item, BaseException):
            raise item
        return item

    def put(self, item: Any) -> None:
        self.inbox.put(item)

    def wait_calls(self, n: int, timeout: float = 2.0) -> bool:
        with self._cv:
            return self._cv.wait_for(lambda: self.calls >= n, timeout)

    def wait_returned(self, n: int, timeout: float = 2.0) -> bool:
        with self._cv:
            return self._cv.wait_for(lambda: self.returned >= n, timeout)

    def stays_at(self, n: int, window: float = 0.1) -> bool:
        """読みの回数が window 秒のあいだ n 回を超えないか（超えたら False）。"""
        with self._cv:
            return not self._cv.wait_for(lambda: self.calls > n, window)

    def settled(self, n: int, window: float = 0.05) -> bool:
        """n 回目の読みが返り、そのあと読むスレッドが行を渡し終えるだけの間（window 秒）、読みの回数が増えないこと。"""
        if not self.wait_returned(n):
            return False
        return self.stays_at(self.calls, window)

    def release(self) -> None:
        """テストの終わりに、止まっている読みを抜けさせる。"""
        self.inbox.put(EOFError())
