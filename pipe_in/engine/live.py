"""進み具合の写し（Claude のアーティファクトに出す JSON）を作る。

state.json（と、動いている段のログの最初の行）から、ページに見せてよい項目だけを取り出す。
- ファイルを読むのは read_state と read_open_at だけ。build_snapshot は純粋（時計もファイルも触らない）。
- 項目は「許すものの一覧」で作る。知らないキー・自由な文（結果・エラー・差し戻しの理由）・
  session_id・パスは写しに入れない。
- 記録がどう壊れていても例外で落ちず、決まった形（キーの数と順は常に同じ）で返す。
標準ライブラリだけを使う（依存の向きは docs/development/design.md）。
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
import unicodedata
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any

SCHEMA = 1  # 写しの形の版。項目の意味を変える・消すときに上げる（足すだけなら上げない）
MAX_BYTES = 32768  # 写し全体の上限（dumps した UTF-8 のバイト数）
MAX_STATE_BYTES = 4 * 1024 * 1024  # state.json をこれより大きければ読まず「記録なし」にする
MAX_STAGES = 24
MAX_NAME = 60  # セッション名の長さ（見た目の1文字を1と数える）
MAX_LABEL = 40  # 段の名前・表示名の長さ
MAX_TIME_TEXT = 40
LOG_READ_BYTES = 64 * 1024  # ログは先頭のここまで
LOG_MAX_LINES = 50
LOG_MAX_LINE_BYTES = 16 * 1024
MAX_NUMBER = 1e9
MAX_ATTEMPT = 999
ELLIPSIS = "…"

# 最後の結果（Exit の名前から AWAITING_REVIEW を除いたもの。tests が列挙と一致を見張る）
FINALS = ("PASSED", "TEST_FAILED", "STOPPED_BY_HUMAN", "STAGE_ERROR", "BLOCKED")
VERDICTS = ("pass", "fail", "blocked")
VERDICT_STAGE = "test"

_UTC = timezone.utc
_TIME_RE = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})[T ]([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})?"
)
_WIN_PATH_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]\S*")
_POSIX_PATH_RE = re.compile(r"(?:^|(?<=\s))/[^\s/]+/\S*")


# ---- 時刻 -----------------------------------------------------------------------------------


def _to_utc_text(t: datetime) -> str | None:
    try:
        return t.astimezone(_UTC).isoformat(timespec="seconds")
    except (OverflowError, ValueError, OSError):
        return None


def _parse_time(value: Any, local_tz: tzinfo | None) -> str | None:
    """記録の時刻の文字を、UTC の `YYYY-MM-DDTHH:MM:SS+00:00` にする。読めなければ None。

    ずれなしは「手元の時刻帯」と見なす（local_tz。None ならその機械の時刻帯）。
    """
    if type(value) is not str or len(value) > MAX_TIME_TEXT:
        return None
    m = _TIME_RE.fullmatch(value)
    if not m:
        return None
    try:
        y, mo, d, h, mi, s = (int(m.group(i)) for i in range(1, 7))
        t = datetime(y, mo, d, h, mi, s)
        off = m.group(7)
        if off == "Z":
            t = t.replace(tzinfo=_UTC)
        elif off:
            hh, mm = int(off[1:3]), int(off[4:6])
            if hh > 23 or mm > 59:
                return None
            delta = timedelta(hours=hh, minutes=mm)
            t = t.replace(tzinfo=timezone(-delta if off[0] == "-" else delta))
        elif local_tz is not None:
            t = t.replace(tzinfo=local_tz)
        else:
            t = t.astimezone()
    except (ValueError, OverflowError, OSError):
        return None
    return _to_utc_text(t)


def _now_text(now: Any, local_tz: tzinfo | None) -> str:
    try:
        t = now
        if t.tzinfo is None:
            t = t.replace(tzinfo=local_tz) if local_tz is not None else t.astimezone()
        text = _to_utc_text(t)
    except (AttributeError, ValueError, OverflowError, OSError):
        text = None
    return text or datetime.now(_UTC).isoformat(timespec="seconds")


# ---- 文字の掃除 -------------------------------------------------------------------------------

_ZWJ = "‍"


def _is_attached(ch: str) -> bool:
    """直前の文字にくっつく文字（結合文字・異体字選択子・肌色の修飾・タグ文字）。"""
    cp = ord(ch)
    if 0x1F3FB <= cp <= 0x1F3FF or 0xE0020 <= cp <= 0xE007F or 0xFE00 <= cp <= 0xFE0F:
        return True
    return unicodedata.category(ch) in ("Mn", "Me", "Mc")


def _is_regional(ch: str) -> bool:
    return 0x1F1E6 <= ord(ch) <= 0x1F1FF


def _clusters(text: str, limit: int) -> list[str]:
    """見た目の1つ（基の文字＋つながる文字）ごとに分ける。limit 個を超えたら、そこで打ち切る（limit+1 個まで返す）。"""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n and len(out) <= limit:
        j = i + 1
        if _is_regional(text[i]) and j < n and _is_regional(text[j]):
            j += 1
        while j < n:
            ch = text[j]
            if ch == _ZWJ:
                j += 2 if j + 1 < n else 1
            elif _is_attached(ch):
                j += 1
            else:
                break
        out.append(text[i:j])
        i = j
    return out


def _hide_variants(hide: Any) -> list[str]:
    found: set[str] = set()
    try:
        items = list(hide)
    except TypeError:
        items = []
    for h in items:
        if type(h) is str and h:
            found.add(h)
            found.add(h.replace("\\", "/"))
            found.add(h.replace("/", "\\"))
    return sorted(found, key=len, reverse=True)


def _clean(value: Any, limit: int, hides: list[str]) -> str | None:
    """名前などの文字を掃除して長さを切る。文字列でない・掃除して空になるときは None。"""
    if type(value) is not str:
        return None
    kept: list[str] = []
    for ch in value:
        if ch.isspace():
            kept.append(" ")
        elif ch != _ZWJ and unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Zl", "Zp"):
            continue
        else:
            kept.append(ch)
    text = " ".join("".join(kept).split())
    if not text:
        return None
    for h in hides:
        if h in text:
            text = text.replace(h, ELLIPSIS)
    text = _WIN_PATH_RE.sub(ELLIPSIS, text)
    text = _POSIX_PATH_RE.sub(ELLIPSIS, text)
    parts = _clusters(text, limit)
    if len(parts) > limit:
        text = "".join(parts[: limit - 1]) + ELLIPSIS
    return text


# ---- 数 -----------------------------------------------------------------------------------------


def _number(value: Any) -> int | float | None:
    """0〜1e9 の有限の数だけ。真偽・NaN・Infinity・負・巨大は None。"""
    t = type(value)
    if t is int:
        return value if 0 <= value <= MAX_NUMBER else None
    if t is float:
        return value if math.isfinite(value) and 0 <= value <= MAX_NUMBER else None
    return None


def _int_number(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= MAX_NUMBER else None


def _attempt(value: Any) -> int | None:
    return value if type(value) is int and 1 <= value <= MAX_ATTEMPT else None


# ---- 読む(ファイル) -------------------------------------------------------------------------------


def read_state(work_dir: Path) -> dict[str, Any] | None:
    """work_dir/state.json を上限つきで読む。無い・読めない・大きすぎる・オブジェクトでないときは None。"""
    try:
        fd = os.open(os.path.join(os.fspath(work_dir), "state.json"), os.O_RDONLY)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return None
            raw = b""
            while len(raw) <= MAX_STATE_BYTES:
                chunk = os.read(fd, MAX_STATE_BYTES + 1 - len(raw))
                if not chunk:
                    break
                raw += chunk
        finally:
            os.close(fd)
        if len(raw) > MAX_STATE_BYTES:
            return None
        data = json.loads(raw.decode("utf-8"))
    except Exception:  # 壊れ方は何でも「記録なし」にする（権限・入れ子が深すぎる・文字化けなど）
        return None
    return data if isinstance(data, dict) else None


def _log_name_fits(log: str, stage: str) -> bool:
    """NN_<段>[_<回>].jsonl の形で、段の名前が open の段と合うログの名前だけを通す。"""
    if "/" in log or "\\" in log or "\x00" in log:
        return False
    head = re.match(r"[0-9]+_", log, re.ASCII)
    if not head:
        return False
    rest = log[head.end():]
    if rest == stage + ".jsonl":
        return True
    return re.fullmatch(re.escape(stage) + r"_[0-9]+\.jsonl", rest, re.ASCII) is not None


def read_open_at(work_dir: Path, state: Any) -> str | None:
    """動いている段のログの、最初の Prompt 行の at を文字のまま返す。読めなければ None。

    開くログは多くても1つ。先頭 64 KiB の中の完全な行を最大 50 行、1行 16 KiB 以内のものだけ見る。
    """
    if not isinstance(state, dict):
        return None
    op = state.get("open")
    if not isinstance(op, dict):
        return None
    stage, log = op.get("stage"), op.get("log")
    if type(stage) is not str or type(log) is not str or not _log_name_fits(log, stage):
        return None
    try:
        logs = os.path.join(os.fspath(work_dir), "logs")
        if os.path.islink(logs):
            return None
        path = os.path.join(logs, log)
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return None
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return None
            data = b""
            while len(data) <= LOG_READ_BYTES:
                chunk = os.read(fd, LOG_READ_BYTES + 1 - len(data))
                if not chunk:
                    break
                data += chunk
        finally:
            os.close(fd)
    except (OSError, ValueError):
        return None
    if len(data) > LOG_READ_BYTES:  # 64 KiB で切れた。最後の行は途中なので捨てる
        data = data[:LOG_READ_BYTES]
        data = data[: data.rfind(b"\n") + 1]
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    for line in lines[:LOG_MAX_LINES]:
        if len(line) > LOG_MAX_LINE_BYTES:
            continue
        try:
            obj = json.loads(line.decode("utf-8"))
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("_type") == "Prompt":
            at = obj.get("at")
            return at if type(at) is str else None
    return None


# ---- 組み立てる(純粋) -----------------------------------------------------------------------------


def _empty(generated_at: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "generated_at": generated_at, "empty": True, "name": None, "final": None, "stages": []}


class _Acc:
    """1つの段の、runs の読み取り結果。"""

    __slots__ = ("last", "attempt", "cost", "turns", "duration", "verdict")

    def __init__(self) -> None:
        self.last: dict[str, Any] | None = None  # 記録の順の最後の行（状態を決める）
        self.attempt: int | None = None  # 最後の実行の回
        self.cost: int | float | None = None
        self.turns: int | None = None
        self.duration: int | float | None = None
        self.verdict: Any = None


def _is_run_row(row: dict[str, Any]) -> bool:
    return "review" not in row and "verdict" not in row and not isinstance(row.get("result"), dict)


def _collect(runs: Any, accs: dict[str, _Acc]) -> None:
    if not isinstance(runs, list):
        return
    for row in runs:
        if not isinstance(row, dict):
            continue
        stage = row.get("stage")
        if type(stage) is not str:
            continue
        acc = accs.get(stage)
        if acc is None:
            continue
        acc.last = row
        if "verdict" in row:
            v = row["verdict"]
            status = v.get("status") if isinstance(v, dict) else None
            acc.verdict = status if type(status) is str and status in VERDICTS else None
        if not _is_run_row(row):
            continue
        acc.attempt = _attempt(row.get("attempt"))
        c = _number(row.get("cost_usd"))
        if c is not None:
            acc.cost = c if acc.cost is None else acc.cost + c
        t = _int_number(row.get("num_turns"))
        if t is not None:
            acc.turns = t if acc.turns is None else acc.turns + t
        d = _number(row.get("duration_sec"))
        if d is not None:
            acc.duration = d if acc.duration is None else acc.duration + d


def _status(name: str, acc: _Acc, op: Any, pending: Any) -> str:
    if isinstance(op, dict) and op.get("stage") == name:
        return "running"
    if isinstance(pending, dict) and pending.get("stage") == name:
        return "review"
    last = acc.last
    if last is None:
        return "waiting"
    if last.get("review") == "revise":
        return "revised"
    if _is_run_row(last) and last.get("is_error") is True:
        return "failed"
    return "done"


def build_snapshot(state: Any, open_at: Any, *, now: Any, local_tz: Any = None, hide: Any = ()) -> dict[str, Any]:
    """記録（state.json の中身）から写しを作る。時計・ファイルに触れず、例外を出さない。"""
    generated_at = _now_text(now, local_tz)
    if not isinstance(state, dict):
        return _empty(generated_at)
    hides = _hide_variants(hide)
    snap: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "empty": False,
        "name": _clean(state.get("name"), MAX_NAME, hides),
        "final": state["final"] if type(state.get("final")) is str and state["final"] in FINALS else None,
        "stages": [],
    }
    # 段の並び：stages の順。壊れた要素・重なった名前は飛ばし、24 まで
    chosen: list[tuple[str, str, str]] = []  # (元の名前, 掃除した名前, 表示名)
    seen: set[str] = set()
    entries = state.get("stages")
    if isinstance(entries, list):
        for entry in entries:
            if len(chosen) >= MAX_STAGES:
                break
            if not isinstance(entry, dict) or type(entry.get("name")) is not str:
                continue
            raw = entry["name"]
            if raw in seen:
                continue
            name = _clean(raw, MAX_LABEL, hides)
            if name is None:
                continue
            seen.add(raw)
            chosen.append((raw, name, _clean(entry.get("label"), MAX_LABEL, hides) or name))
    accs = {raw: _Acc() for raw, _n, _l in chosen}
    _collect(state.get("runs"), accs)
    op, pending = state.get("open"), state.get("pending_review")
    stages: list[dict[str, Any]] = []
    for raw, name, label in chosen:
        acc = accs[raw]
        status = _status(raw, acc, op, pending)
        attempt = acc.attempt
        started_at = pending_since = None
        if status == "running":
            attempt = _attempt(op.get("attempt"))
            started_at = _parse_time(open_at, local_tz)
        elif status == "review":
            pending_since = _parse_time(pending.get("since"), local_tz)
        stages.append({
            "name": name,
            "label": label,
            "status": status,
            "attempt": attempt,
            "started_at": started_at,
            "pending_since": pending_since,
            "verdict": acc.verdict if raw == VERDICT_STAGE else None,
            "cost_usd": None if acc.cost is None else round(acc.cost, 4),
            "turns": acc.turns,
            "duration_sec": None if acc.duration is None else round(acc.duration, 1),
        })
    snap["stages"] = stages
    # 念のため：全体が上限を超えるなら、末尾の段から落とす
    while stages and len(dumps(snap).encode("utf-8")) > MAX_BYTES:
        stages.pop()
    return snap


def dumps(snapshot: Any) -> str:
    """固定の書き方で JSON にする（ASCII だけ・隙間なし・キーの順はそのまま・< > & は \\u 形・末尾に改行）。"""
    text = json.dumps(snapshot, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return text + "\n"
