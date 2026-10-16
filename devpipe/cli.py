"""コマンドラインの入口:  devpipe --project ./myapp --input request.md

--pipe <名前かパス> で、pipes/devpipe-<名前>/ のパイプを流す（パイプを作るのは devpipe-gen）。
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from .dev.pipeline import DevPipeline
from .dev.specs import STAGES
from .engine.checkpoint import Decision
from .engine.config import Config, load_config
from .engine.pipeline import BasePipeline
from .pipe import definition as pd
from .pipe.pipeline import LinearPipeline


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="devpipe",
        description="要件 → 要件定義 → 設計 → テスト先行 → 実装 → 検証 を順に実行します。"
        " --pipe で、devpipe-gen で作ったパイプを流せます。",
    )
    p.add_argument("--project", type=Path, default=Path("."), help="対象プロジェクトのフォルダ（既定: 今のフォルダ）")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--input", type=Path, help="要件メモのファイル。- で標準入力から読む")
    src.add_argument("--text", help="要件メモを直接渡す")
    p.add_argument("--config", type=Path, help="設定ファイル（既定: プロジェクト直下の pipeline.toml）")
    p.add_argument(
        "--pipe",
        help="流すパイプの名前（pipes/devpipe-<名前>/）かフォルダのパス。省くと組み込みの開発フロー。一覧は devpipe-gen list",
    )
    p.add_argument(
        "--from",
        dest="from_stage",
        help=f"途中の段から再開する（開発フローでは {' / '.join(STAGES)}。パイプではその段の名前）",
    )
    p.add_argument("--yes", action="store_true", help="要件定義・設計・テスト先行の確認を省いて最後まで流す")
    p.add_argument(
        "--pause",
        action="store_true",
        help="確認の段で入力を待たずに止まる（終了コード 5）。答えは --review で渡す。チャットから動かすとき用",
    )
    p.add_argument(
        "--review",
        choices=("approve", "revise", "quit"),
        help="--pause で止まった確認に答えて続きを流す（approve=承認・revise=修正を依頼・quit=中止）",
    )
    p.add_argument("--feedback", help="--review revise のときの、直してほしい点")
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


def _load_pipe(name_or_path: str, project: Path) -> pd.PipeDef:
    path = pd.find_pipe(name_or_path)
    if path is None:
        raise SystemExit(f"パイプ「{name_or_path}」が見つかりません（devpipe-gen list で一覧を出せます）")
    try:
        pipe = pd.load_pipe(path)
    except pd.PipeError as e:
        raise SystemExit(str(e)) from e
    errors = pd.check_pipe(pipe, project.expanduser().resolve())
    if errors:
        raise SystemExit(f"パイプ「{pipe.name}」に誤りがあります:\n" + "\n".join(f"  - {e}" for e in errors))
    return pipe


def pipeline_for(cfg: Config, pipe: pd.PipeDef | None, *, test_cmd_given: bool = False) -> BasePipeline:
    """パイプの種類に合わせて流し方を選ぶ。

    - パイプなし・kind = "dev"：組み込みの開発フロー。記録の場所は work_dir のまま（VSCode の拡張が読む所）。
      test_command は --test-cmd → パイプの定義 → pipeline.toml の順に優先する。
    - kind = "linear"：定義の順に段を流す。記録は <work_dir>/<名前>/ に分ける。
    """
    if pipe is None:
        return DevPipeline(cfg)
    if pipe.kind == "dev":
        cfg = cfg.for_pipe(pipe.name, own_work_dir=False)
        if pipe.test_command and not test_cmd_given:
            cfg = replace(cfg, test_command=pipe.test_command)
        return DevPipeline(cfg)
    return LinearPipeline(cfg.for_pipe(pipe.name, own_work_dir=True), pipe)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.review:
        if args.input is not None or args.text is not None or args.from_stage is not None or args.yes:
            raise SystemExit("--review は --input・--text・--from・--yes と一緒には使えません")
        if args.review == "revise" and not (args.feedback or "").strip():
            raise SystemExit("--review revise には --feedback で直してほしい点を渡してください")
    elif args.feedback is not None:
        raise SystemExit("--feedback は --review revise と一緒に使ってください")
    if args.pause and args.yes:
        raise SystemExit("--pause と --yes は一緒には使えません")
    pause = args.pause or args.review is not None
    pipe = _load_pipe(args.pipe, args.project) if args.pipe else None
    cfg = load_config(
        args.project,
        args.config,
        max_retries=args.max_retries,
        test_command=args.test_cmd,
        auto_approve=args.yes,
        pause_for_review=pause,
    )
    pipeline = pipeline_for(cfg, pipe, test_cmd_given=args.test_cmd is not None)
    linear = isinstance(pipeline, LinearPipeline)
    cfg = pipeline.cfg
    if args.review:
        _warn_if_dirty(cfg.project_dir)
        decision = Decision(args.review, (args.feedback or "").strip())
        try:
            return int(asyncio.run(pipeline.review(decision)))
        except KeyboardInterrupt:
            print("\n中断しました。続きは --from で途中の段から再開できます。")
            return 130
    text = _read_input(args)
    from_stage = args.from_stage if linear else (args.from_stage or "requirements")
    if not linear and from_stage == "requirements" and text is None and not (cfg.work_dir / "00_input.md").is_file():
        raise SystemExit("要件メモを --input か --text で渡してください")
    if not args.yes and str(args.input) == "-":
        raise SystemExit("標準入力から要件を読むときは確認ができないため、--yes を付けるかファイルで渡してください")
    if not args.yes and not pause and not sys.stdin.isatty():
        print("⚠ 対話できない環境です。確認の段で止まるので、確認を省くなら --yes を付けてください。\n")
    _warn_if_dirty(cfg.project_dir)
    try:
        result = asyncio.run(pipeline.run(text, from_stage))
    except KeyboardInterrupt:
        print("\n中断しました。続きは --from で途中の段から再開できます。")
        return 130
    return int(result)


