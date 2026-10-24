"""pipe-in live：進み具合の写しとページを出す（Claude のアーティファクト用）。

  pipe-in live snapshot [--project DIR] [--config FILE] [--work-dir DIR] [--out FILE]
  pipe-in live page [--out FILE]
  pipe-in live watch --out FILE [--project DIR] [--config FILE] [--work-dir DIR] [--interval 秒] [--timeout 秒]

- 記録は読むだけ。書くのは --out のファイルだけで、読み先のフォルダの中・シンボリックリンク・親のフォルダが無い所には書かない。
- 記録が無い・壊れているときも「記録なし」の形を出して終了コード 0。引数の誤りは終了コード 2、書けなかったときは 1。
- watch は記録を見張り、写しが変わったときだけ --out に写しを書いて標準出力に1行（JSON）を出す。final で 0、上限で 124 で止まる。
- 段は流さず、SDK も子プロセスも使わない。
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import live, live_page, live_watch
from .config import load_config


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pipe-in live",
        description="進み具合の写し（JSON）と、それを見せるページ（HTML）を出し、記録を見張って変わったときだけ1行を出します。記録は読むだけです。",
        allow_abbrev=False,
    )
    sub = p.add_subparsers(dest="action", required=True, metavar="{snapshot,page,watch}")
    s = sub.add_parser("snapshot", help="記録から写し（JSON）を作って出す", allow_abbrev=False)
    s.add_argument("--project", type=Path, default=Path("."), help="対象プロジェクトのフォルダ（既定: 今のフォルダ）")
    s.add_argument("--config", type=Path, help="設定ファイル（既定: プロジェクト直下の pipeline.toml）")
    s.add_argument(
        "--work-dir",
        type=Path,
        help="読む記録のフォルダ（既定: 設定の work_dir。パイプの記録は docs/pipeline/<パイプ名> を渡す）",
    )
    s.add_argument("--out", type=Path, help="書き出すファイル（省くと標準出力）")
    g = sub.add_parser("page", help="進み具合のページ（HTML）を出す", allow_abbrev=False)
    g.add_argument("--out", type=Path, help="書き出すファイル（省くと標準出力）")
    w = sub.add_parser("watch", help="記録を見張り、写しが変わったときだけ1行（JSON）を出す", allow_abbrev=False)
    w.add_argument("--project", type=Path, default=Path("."), help="対象プロジェクトのフォルダ（既定: 今のフォルダ）")
    w.add_argument("--config", type=Path, help="設定ファイル（既定: プロジェクト直下の pipeline.toml）")
    w.add_argument(
        "--work-dir",
        type=Path,
        help="読む記録のフォルダ（既定: 設定の work_dir。パイプの記録は docs/pipeline/<パイプ名> を渡す）",
    )
    w.add_argument("--out", type=Path, required=True, help="写し（JSON）を書き出すファイル（必須。標準出力は行の専用）")
    w.add_argument(
        "--interval",
        type=live_watch.parse_interval,
        default=live_watch.DEFAULT_INTERVAL,
        help=f"読む間隔（秒。{live_watch.MIN_INTERVAL:g}〜{live_watch.MAX_INTERVAL:g}、既定 {live_watch.DEFAULT_INTERVAL:g}）",
    )
    w.add_argument(
        "--timeout",
        type=live_watch.parse_timeout,
        default=live_watch.DEFAULT_TIMEOUT,
        help=f"見張る上限（秒。{live_watch.MIN_TIMEOUT:g}〜{live_watch.MAX_TIMEOUT:g}、既定 {live_watch.DEFAULT_TIMEOUT:g}）",
    )
    return p


def _hide_forms(given: Path) -> tuple[str, ...]:
    """写しの文字から消す、読み先の絶対パスの形（与えられた形・絶対にした形・resolve した形）。"""
    forms = {os.path.abspath(given), str(given.resolve())}
    if given.is_absolute():
        forms.add(str(given))
    return tuple(sorted(forms))


def _check_out(out: Path, work_dir: Path | None) -> str | None:
    """--out を断る理由（使い方の誤り）。書いてよければ None。"""
    if not out.parent.is_dir():
        return f"--out の親のフォルダがありません: {out.parent}"
    if os.path.islink(out):
        return "--out にシンボリックリンクは指定できません"
    if work_dir is not None:
        target = out.parent.resolve() / out.name
        root = work_dir.resolve()
        if target == root or root in target.parents:
            return "--out は読み先の記録のフォルダの中には指定できません"
    return None


def _emit(data: bytes, out: Path | None) -> int:
    if out is None:
        stream = getattr(sys.stdout, "buffer", None)
        if stream is not None:
            stream.write(data)
            stream.flush()
        else:
            sys.stdout.write(data.decode("utf-8"))
            sys.stdout.flush()
        return 0
    try:
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o666)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    except OSError as e:
        print(f"pipe-in live: 書き出せませんでした（{out}: {e.strerror or type(e).__name__}）", file=sys.stderr)
        return 1
    return 0


def _detach_stdout() -> None:
    """標準出力の受け側が閉じたあと、終了時の flush でまた落ちないよう、記述子を os.devnull に付け替える。

    付け替えられないときは sys.stdout を None にして、終了時の flush を止める。例外は出さない。
    os.devnull を開いた番号が標準出力の番号と同じなら（標準出力の記述子がもう閉じていた）、
    すでに捨て先を指しているので、付け替えも閉じもしない。
    """
    try:
        target = sys.stdout.fileno()
        sink = os.open(os.devnull, os.O_WRONLY)
        if sink != target:
            try:
                os.dup2(sink, target)
            finally:
                os.close(sink)
    except Exception:  # noqa: BLE001 - 付け替えられなくても止まり方は変えない
        try:
            sys.stdout = None  # type: ignore[assignment]
        except Exception:  # noqa: BLE001
            pass


def _watch(parser: argparse.ArgumentParser, args: argparse.Namespace, deps: dict[str, Any] | None) -> int:
    work_dir = args.work_dir if args.work_dir is not None else load_config(args.project, args.config).work_dir
    reason = _check_out(args.out, work_dir)
    if reason is None and args.out.is_dir():
        reason = "--out にフォルダは指定できません"
    if reason:
        parser.error(reason)
    hide = _hide_forms(work_dir)
    restore = live_watch.install_sigterm()
    try:
        code = live_watch.watch(work_dir, args.out, interval=args.interval, timeout=args.timeout, hide=hide, **(deps or {}))
    finally:
        restore()
    if code == live_watch.EXIT_WRITE_OR_PIPE and not (deps and "stdout" in deps):
        _detach_stdout()
    return code


def main(argv: list[str], *, now: datetime | None = None, watch_deps: dict[str, Any] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.action == "watch":
        return _watch(parser, args, watch_deps)
    if args.action == "page":
        if args.out is not None:
            reason = _check_out(args.out, None)
            if reason:
                parser.error(reason)
        return _emit(live_page.build_page().encode("utf-8"), args.out)

    work_dir = args.work_dir if args.work_dir is not None else load_config(args.project, args.config).work_dir
    if args.out is not None:
        reason = _check_out(args.out, work_dir)
        if reason:
            parser.error(reason)
    clock = now if now is not None else datetime.now(timezone.utc)
    state = live.read_state(work_dir)
    snapshot = live.build_snapshot(state, live.read_open_at(work_dir, state), now=clock, hide=_hide_forms(work_dir))
    return _emit(live.dumps(snapshot).encode("utf-8"), args.out)
