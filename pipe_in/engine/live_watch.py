"""進み具合の記録を見張って、写しが変わったときだけ1行を出す（pipe-in live watch）。

- 記録は読むだけ（読み方は live.py のまま）。書くのは --out の写しと、その一時ファイルだけ。
- 純粋な部分（写しの比べ方・出すかの判定・行の組み立て・間隔と上限の検査）と、回し役 watch に分ける。
  watch は時計・眠り・今・読み・書き・出力を引数で差し替えられるので、テストは本物の時間を待たない。
- SDK も子プロセスも使わない。標準ライブラリと pipe_in.engine.live だけを読む。
"""

from __future__ import annotations

import argparse
import errno
import json
import math
import os
import signal
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import live

DEFAULT_INTERVAL = 2.0  # 秒
MIN_INTERVAL, MAX_INTERVAL = 0.5, 60.0
DEFAULT_TIMEOUT = 6 * 3600.0  # 秒
MIN_TIMEOUT, MAX_TIMEOUT = 1.0, 24 * 3600.0
UNREADABLE_LIMIT = 3  # 連続して読めなかったら「記録なし」を出す回数
WRITE_FAIL_LIMIT = 3  # 連続して書けなかったら止まる回数
EXIT_OK, EXIT_WRITE_OR_PIPE, EXIT_USAGE = 0, 1, 2
EXIT_TIMEOUT, EXIT_SIGINT, EXIT_SIGTERM = 124, 130, 143


class Terminated(BaseException):
    """終了の合図（SIGTERM）を受けた。"""


class _StdoutClosed(Exception):
    """標準出力が使えなくなった（閉じた・書けない）。message は標準エラーに出す文（パスや strerror を含まない）。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# 閉じた出力として扱う errno。EINVAL は Windows で、読み手のいないパイプに書いたときに出る。
_CLOSED_ERRNOS = frozenset({errno.EPIPE, errno.EINVAL})


# ---- 純粋な部分 -----------------------------------------------------------------------------------------------------------


def _parse_number(text: str, lo: float, hi: float, what: str) -> float:
    try:
        value = float(text)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"{what}は数で指定してください: {text!r}") from None
    if math.isnan(value) or math.isinf(value) or not lo <= value <= hi:
        raise argparse.ArgumentTypeError(f"{what}は {lo:g} 秒から {hi:g} 秒の間で指定してください: {text!r}")
    return value


def parse_interval(text: str) -> float:
    """--interval の値（秒）。範囲は両端を含む。範囲外・数でない・nan・inf は使い方の誤り。"""
    return _parse_number(text, MIN_INTERVAL, MAX_INTERVAL, "--interval")


def parse_timeout(text: str) -> float:
    """--timeout の値（秒）。範囲は両端を含む。範囲外・数でない・nan・inf は使い方の誤り。"""
    return _parse_number(text, MIN_TIMEOUT, MAX_TIMEOUT, "--timeout")


def snapshot_key(snapshot: Any) -> str:
    """写しの比べ用の文字列。generated_at を除いた中身で、キーの順や空白の違いは出ない。"""
    body = {k: v for k, v in snapshot.items() if k != "generated_at"}
    return json.dumps(body, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


def decide(last_key: str | None, key: str, *, readable: bool, misses: int) -> tuple[bool, int]:
    """(出すか, 数え直した連続の読み損ない回数)。時計にもファイルにも触れない。"""
    if last_key is None:
        return True, (0 if readable else 1)
    if readable:
        return key != last_key, 0
    misses += 1
    if key == last_key:
        return False, misses
    return misses >= UNREADABLE_LIMIT, misses


def format_line(event: str, seq: int, final: Any, empty: Any) -> str:
    """標準出力の1行（JSON。キーは event・seq・final・empty の順）。"""
    obj = {"event": event, "seq": seq, "final": final, "empty": empty}
    return json.dumps(obj, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"


# ---- 書き込みと信号 -----------------------------------------------------------------------------------------------------


def write_atomic(out: Path, data: bytes) -> None:
    """同じフォルダの一時ファイルに全部書いてから置き換える。置き換えられなかったときは一時ファイルを消す。"""
    out = Path(out)
    fd, tmp = tempfile.mkstemp(dir=out.parent, prefix="." + out.name + ".", suffix=".tmp")
    replaced = False
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, out)
        replaced = True
    finally:
        if not replaced:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def install_sigterm() -> Callable[[], None]:
    """SIGTERM を受けたら Terminated を投げる。取り付けられない環境では何もしない。戻り値は元に戻す関数。"""

    def handler(signum: int, frame: Any) -> None:
        raise Terminated()

    try:
        previous = signal.signal(signal.SIGTERM, handler)
    except (AttributeError, ValueError, OSError):
        return lambda: None

    def restore() -> None:
        try:
            signal.signal(signal.SIGTERM, previous if previous is not None else signal.SIG_DFL)
        except (AttributeError, ValueError, OSError):
            pass

    return restore


# ---- 回し役 -------------------------------------------------------------------------------------------------------------


def _say(stderr: Any, text: str) -> None:
    try:
        stderr.write(f"pipe-in live watch: {text}\n")
        stderr.flush()
    except Exception:  # noqa: BLE001 - 標準エラーが閉じていても、止まり方は変えない
        pass


def _stdout_failure_text(e: BaseException) -> str:
    """標準出力の write・flush の失敗から、標準エラーの文（"pipe-in live watch: " の後ろ）を決める。

    閉じた出力（BrokenPipeError・errno が EPIPE か EINVAL の OSError・閉じたストリームの ValueError）は
    「閉じられました」。そのほかの OSError は型の名前だけを添える（パスや strerror は入れない）。
    """
    if isinstance(e, (BrokenPipeError, ValueError)):
        return "標準出力が閉じられました"
    if isinstance(e, OSError) and e.errno in _CLOSED_ERRNOS:
        return "標準出力が閉じられました"
    return f"標準出力に書けませんでした（{type(e).__name__}）"


def _emit(stdout: Any, line: str) -> None:
    try:
        stdout.write(line)
        stdout.flush()
    except (OSError, ValueError) as e:  # OSError は BrokenPipeError を含む。errno は問わない
        raise _StdoutClosed(_stdout_failure_text(e)) from e


def watch(
    work_dir: Path,
    out: Path,
    *,
    interval: float,
    timeout: float,
    hide: Any = (),
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Any] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    read_state: Callable[[Path], Any] = live.read_state,
    read_open_at: Callable[[Path, Any], Any] = live.read_open_at,
    write: Callable[[Path, bytes], Any] = write_atomic,
    stdout: Any = None,
    stderr: Any = None,
) -> int:
    """記録を見張る。終了コードを返す（0: final、124: 上限、130: Ctrl+C、143: SIGTERM、1: 書けない・出力が閉じた）。"""
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    last_key: str | None = None
    seq = 0
    misses = 0
    write_fails = 0
    last_final: Any = None
    last_empty: Any = True
    elapsed = 0.0
    prev = clock()
    try:
        while True:
            try:
                state = read_state(work_dir)
                open_at = read_open_at(work_dir, state) if isinstance(state, dict) else None
            except Exception:  # noqa: BLE001 - 予期しない失敗も「読めなかった」にする
                state, open_at = None, None
            readable = isinstance(state, dict)
            snapshot = live.build_snapshot(state if readable else None, open_at, now=now(), hide=hide)
            key = snapshot_key(snapshot)
            emit, misses = decide(last_key, key, readable=readable, misses=misses)
            if emit:
                try:
                    write(out, live.dumps(snapshot).encode("utf-8"))
                except OSError as e:
                    write_fails += 1
                    if write_fails >= WRITE_FAIL_LIMIT:
                        _say(stderr, f"--out に書けませんでした（{type(e).__name__}）")
                        return EXIT_WRITE_OR_PIPE
                else:
                    write_fails = 0
                    seq += 1
                    last_key = key
                    last_final, last_empty = snapshot["final"], snapshot["empty"]
                    is_final = last_final is not None
                    _emit(stdout, format_line("final" if is_final else "snapshot", seq, last_final, last_empty))
                    if is_final:
                        return EXIT_OK
            cur = clock()
            if cur > prev:
                elapsed += cur - prev
            prev = cur
            if elapsed >= timeout:
                _emit(stdout, format_line("timeout", seq, last_final, last_empty))
                return EXIT_TIMEOUT
            sleep(min(interval, timeout - elapsed))
            cur = clock()
            if cur > prev:
                elapsed += cur - prev
            prev = cur
    except KeyboardInterrupt:
        _say(stderr, "中断しました")
        return EXIT_SIGINT
    except Terminated:
        _say(stderr, "終了の合図を受けました")
        return EXIT_SIGTERM
    except _StdoutClosed as e:
        _say(stderr, e.message)
        return EXIT_WRITE_OR_PIPE
