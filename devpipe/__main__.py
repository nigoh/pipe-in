"""コマンドラインの入口:  python -m devpipe --project ./myapp --input request.md"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

from .config import STAGES, load_config
from .orchestrator import Pipeline


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="devpipe",
        description="要件 → 要件定義 → 設計 → テスト先行 → 実装 → 検証 を順に実行します。",
    )
    p.add_argument("--project", type=Path, default=Path("."), help="対象プロジェクトのフォルダ（既定: 今のフォルダ）")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--input", type=Path, help="要件メモのファイル。- で標準入力から読む")
    src.add_argument("--text", help="要件メモを直接渡す")
    p.add_argument("--config", type=Path, help="設定ファイル（既定: プロジェクト直下の pipeline.toml）")
    p.add_argument("--from", dest="from_stage", choices=STAGES, default="requirements", help="途中の段から再開する")
    p.add_argument("--yes", action="store_true", help="要件定義・設計・テスト先行の確認を省いて最後まで流す")
    p.add_argument("--max-retries", type=int, help="テスト失敗時に実装へ差し戻す最大回数（既定: 3）")
    p.add_argument("--test-cmd", help="テストの段のあとに、判定の裏付けとして実行するコマンド（例: 'pytest -q'）")
    return p.parse_args(argv)


def _read_input(args: argparse.Namespace) -> str | None:
    if args.text is not None:
        return args.text
    if args.input is None:
        return None
    if str(args.input) == "-":
        return sys.stdin.read()
    return args.input.expanduser().read_text(encoding="utf-8")


def _warn_if_dirty(project: Path) -> None:
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"], cwd=project, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    if out.returncode == 0 and out.stdout.strip():
        print("⚠ 未コミットの変更があります。作業用のブランチで、コミットしてから実行するのがおすすめです。\n")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    cfg = load_config(
        args.project,
        args.config,
        max_retries=args.max_retries,
        test_command=args.test_cmd,
        auto_approve=args.yes,
    )
    text = _read_input(args)
    if args.from_stage == "requirements" and text is None and not (cfg.work_dir / "00_input.md").is_file():
        raise SystemExit("要件メモを --input か --text で渡してください")
    if not args.yes and str(args.input) == "-":
        raise SystemExit("標準入力から要件を読むときは確認ができないため、--yes を付けるかファイルで渡してください")
    if not args.yes and not sys.stdin.isatty():
        print("⚠ 対話できない環境です。確認の段で止まるので、確認を省くなら --yes を付けてください。\n")
    _warn_if_dirty(cfg.project_dir)
    try:
        result = asyncio.run(Pipeline(cfg).run(text, args.from_stage))
    except KeyboardInterrupt:
        print("\n中断しました。続きは --from で途中の段から再開できます。")
        return 130
    return int(result)


if __name__ == "__main__":
    sys.exit(main())
