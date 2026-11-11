"""コマンドラインの入口:  pipe-in --project ./myapp --input request.md

--pipe <名前かパス> で、<対象>/.pipe-in/pipes/pipe-in-<名前>/（前の版の置き場所・今までの pipes/ も探す）のパイプを流す（パイプを作るのは pipe-in-gen）。
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, TypeVar

from .dev.pipeline import DevPipeline
from .dev.specs import STAGES
from .engine.checkpoint import Decision
from .engine.config import Config, load_config
from .engine.spec import work_dir_conflict
from .engine.pipeline import BasePipeline
from .engine.session import normalize_name
from .pipe import after
from .pipe import definition as pd
from .pipe.pipeline import LinearPipeline

T = TypeVar("T")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="pipe-in",
        description="要件 → 要件定義 → 設計 → テスト先行 → 実装 → 検証 を順に実行します。"
        " --pipe で、pipe-in-gen で作ったパイプを流せます。",
    )
    p.add_argument("--project", type=Path, default=Path("."), help="対象プロジェクトのフォルダ（既定: 今のフォルダ）")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--input", type=Path, help="要件メモのファイル。- で標準入力から読む")
    src.add_argument("--text", help="要件メモを直接渡す")
    p.add_argument("--config", type=Path, help="設定ファイル（既定: プロジェクト直下の pipeline.toml）")
    p.add_argument(
        "--pipe",
        help="流すパイプの名前（<対象>/.pipe-in/pipes/pipe-in-<名前>/ を先に、次に前の版の置き場所、今までの pipes/ を探す）かフォルダのパス。省くと組み込みの開発フロー。一覧は pipe-in-gen list",
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
    p.add_argument(
        "--name",
        help="この実行のセッション名（state.json の name。VSCode の実行の一覧に出る）。省くと要件メモの最初の行から作る。始めるときだけ付けられる",
    )
    p.add_argument(
        "--after",
        action="append",
        metavar="前のパイプ名",
        help="前のパイプが PASSED で終わった記録を受けて、--pipe のパイプを流す（成果物の場所だけを渡す。始めるときだけ付けられる。1つだけ）",
    )
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


def _or_exit(fn: Callable[..., T], *args: Any) -> T:
    """断る文（AfterError）を、終了コード 1 の SystemExit に直す。"""
    try:
        return fn(*args)
    except after.AfterError as e:
        raise SystemExit(str(e)) from e


def _check_after_combination(args: argparse.Namespace) -> None:
    """--after と、ほかの引数の組み合わせを先に検める（記録には何も書いていない段で断る）。"""
    if args.review:
        raise SystemExit("--after は始めるときだけ付けられます（--review と一緒には使えません）")
    if args.from_stage is not None:
        raise SystemExit("--after と --from は一緒に使えません（続きは記録の受けた元を使います）")
    if args.pipe is None:
        raise SystemExit("--after は --pipe で名前のあるパイプと一緒に使ってください（組み込みの開発フローには付けられません）")
    if len(args.after) > 1:
        raise SystemExit("--after は1つだけ指定できます（前のパイプは1つだけ受けられます）")


def _load_pipe(name_or_path: str, project: Path) -> pd.PipeDef:
    path = pd.find_pipe(name_or_path, project=project.expanduser().resolve())
    if path is None:
        raise SystemExit(f"パイプ「{name_or_path}」が見つかりません（pipe-in-gen list で一覧を出せます）")
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
    cfg = _run_cfg(cfg, pipe)
    if pipe is None:
        return DevPipeline(cfg)
    if pipe.kind == "dev":
        if pipe.test_command and not test_cmd_given:
            cfg = replace(cfg, test_command=pipe.test_command)
        return DevPipeline(cfg)
    return LinearPipeline(cfg, pipe)


def _run_cfg(cfg: Config, pipe: pd.PipeDef | None) -> Config:
    """パイプの種類 → 記録の場所の設定。dev は work_dir のまま、linear は <work_dir>/<名前>/ に分ける（estimate も同じ決め方を使う）。"""
    if pipe is None:
        return cfg
    return cfg.for_pipe(pipe.name, own_work_dir=pipe.kind != "dev")


def _print_estimate(cfg: Config, pipe: pd.PipeDef | None) -> None:
    """確認の前に、費用の目安を 2 行で出す（D0066）。作れなくても、流すことは止めない。"""
    from . import estimate_cmd

    try:
        line = estimate_cmd.line_for_run(cfg, pipe)
    except Exception:
        return
    if line:
        print(line + "\n")


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "record":
        # 記録だけを書く（段は流さない）。Claude Code の /pipe-in が使う
        from .dev.record import main as record_main

        return record_main(argv[1:])
    if argv and argv[0] == "skill":
        # record・worktree・decision-number・spec-check を、今のフォルダだけを相手にする形で流す（allow に入れてよい入口）。Claude Code の /pipe-in が使う
        from .dev.skill_cmd import main as skill_main

        return skill_main(argv[1:])
    if argv and argv[0] == "worktree":
        # 機能ごとの worktree を切る・main に入ったものを片付ける。Claude Code の /pipe-in が使う
        from .dev.worktree import main as worktree_main

        return worktree_main(argv[1:])
    if argv and argv[0] == "decision-number":
        # 決定の記録の次の番号を出す（origin の main から。ファイルは作らない）。Claude Code の /pipe-in が使う
        from .dev.decision_number import main as decision_main

        return decision_main(argv[1:])
    if argv and argv[0] == "live":
        # 進み具合の写しとページを出す（記録は読むだけ）。Claude のアーティファクトで進み具合を見るのに使う
        from .engine.live_cmd import main as live_main

        return live_main(argv[1:])
    if argv and argv[0] == "estimate":
        # 流す前の費用の目安を出す（段は流さず、何も書かない）
        from .estimate_cmd import main as estimate_main

        return estimate_main(argv[1:], _load_pipe, _run_cfg)
    args = _parse_args(argv)
    if args.after is not None:
        _check_after_combination(args)
    if args.review:
        if args.input is not None or args.text is not None or args.from_stage is not None or args.yes:
            raise SystemExit("--review は --input・--text・--from・--yes と一緒には使えません")
        if args.name is not None:
            raise SystemExit("--name は始めるときだけ付けられます（--review では付け替えられません）")
        if args.review == "revise" and not (args.feedback or "").strip():
            raise SystemExit("--review revise には --feedback で直してほしい点を渡してください")
    elif args.feedback is not None:
        raise SystemExit("--feedback は --review revise と一緒に使ってください")
    if args.pause and args.yes:
        raise SystemExit("--pause と --yes は一緒には使えません")
    pause = args.pause or args.review is not None
    pipe = _load_pipe(args.pipe, args.project) if args.pipe else None
    after_name: str | None = None
    if pipe is not None and args.after is not None:
        after_name = _or_exit(after.check_after, args.after, pipe)
    cfg = load_config(
        args.project,
        args.config,
        max_retries=args.max_retries,
        test_command=args.test_cmd,
        auto_approve=args.yes,
        pause_for_review=pause,
    )
    conflict = work_dir_conflict(cfg)  # 段が成果物を書けない work_dir は、何も書く前に断る（D0084）
    if conflict is not None:
        raise SystemExit(conflict)
    # 前の記録は、この実行の作業フォルダ（pipeline_for で段の記録の場所に分ける前）から探す。断るならここで止まる（何も書いていない）
    previous = _or_exit(after.read_previous, after_name, cfg, cfg.work_dir) if after_name is not None else None
    pipeline = pipeline_for(cfg, pipe, test_cmd_given=args.test_cmd is not None)
    linear = isinstance(pipeline, LinearPipeline)
    cfg = pipeline.cfg
    if args.name is not None:
        pipeline.name = normalize_name(args.name)  # 空・空白だけは「付けなかった」と同じ
    if previous is not None:
        pipeline.receive(previous.record())
        print(after.intro_line(previous), flush=True)
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
    _print_estimate(cfg, pipe)
    try:
        result = asyncio.run(pipeline.run(text, from_stage))
    except KeyboardInterrupt:
        print("\n中断しました。続きは --from で途中の段から再開できます。")
        return 130
    return int(result)


