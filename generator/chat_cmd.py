"""pipe-in-gen chat …：会話の中でパイプを流す司会役の入口（D0076）。

start / probe / next / done / review / status を受け、司会役（pipe_in.pipe.chat）を呼び、
1つの JSON（ok・action・message ほか）を標準出力に書く。終了コードは ok なら 0、断り・誤りなら 1。
判断は持たない（引数の解釈と出力だけ）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pipe_in.pipe.chat import Chat, ChatError


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pipe-in-gen chat",
        description="会話の中でパイプを流す司会役。段の順番・確認・差し戻し・記録を持ち、結果を JSON で返す。",
    )
    sub = p.add_subparsers(dest="action", required=True)

    def common(sp: argparse.ArgumentParser, *, pipe: bool) -> None:
        if pipe:
            sp.add_argument("--pipe", required=True, help="パイプの名前")
        sp.add_argument("--project", type=Path, default=Path("."), help="対象プロジェクトのフォルダ（既定: 今のフォルダ）")

    s = sub.add_parser("start", help="記録を作って始める（--dry-run なら何も書かず、段の表と効かない設定を返す）")
    s.add_argument("pipe", help="パイプの名前かフォルダのパス")
    s.add_argument("--memo", help="依頼メモ")
    s.add_argument("--memo-file", type=Path, dest="memo_file", help="依頼メモのファイル")
    s.add_argument("--name", help="セッション名")
    s.add_argument("--session-id", dest="session_id", help="Claude Code の会話の ID")
    s.add_argument("--after", help="（会話の中では使えません。断るために受ける）")
    s.add_argument("--dry-run", action="store_true", dest="dry_run", help="何も書かずに、段の表と効かない設定を返す")
    s.add_argument("--pipes-dir", type=Path, dest="pipes_dir", help="パイプを探すフォルダ")
    common(s, pipe=False)

    for name, text in (("probe", "守りの確かめ（1回目で確かめ役への指示を出し、2回目で読んで確かめる）"), ("next", "次にすることを返す"), ("status", "今どこかを返す（読むだけ）")):
        common(sub.add_parser(name, help=text), pipe=True)

    d = sub.add_parser("done", help="段を閉じる（検査して、次を決める）")
    common(d, pipe=True)
    d.add_argument("--stage", required=True)
    d.add_argument("--summary", default="", help="段の返事の要点")
    d.add_argument("--status", help="判定のある段の判定（pass / fail）")
    d.add_argument("--problems", action="append", help="fail のときの直す点（何度でも）")
    d.add_argument("--error", action="store_true", help="段が失敗した")

    r = sub.add_parser("review", help="人の確認の答えを記録する")
    common(r, pipe=True)
    r.add_argument("answer", help="approved / revise / quit")
    r.add_argument("--feedback", help="revise のときの、直してほしい点")
    return p


def _run(args: argparse.Namespace) -> dict[str, Any]:
    chat = Chat(args.project)
    if args.action == "start":
        memo = args.memo
        if args.memo_file is not None:
            try:
                memo = args.memo_file.expanduser().read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                raise ChatError(f"--memo-file を読めません（{type(e).__name__}）") from e
        chat.pipes_dir = args.pipes_dir.expanduser() if args.pipes_dir else None
        return chat.start(
            args.pipe, memo=memo, name=args.name, session_id=args.session_id, after=args.after, dry_run=args.dry_run
        )
    if args.action == "probe":
        return chat.probe(args.pipe)
    if args.action == "next":
        return chat.next(args.pipe)
    if args.action == "status":
        return chat.status(args.pipe)
    if args.action == "done":
        return chat.done(args.pipe, args.stage, args.summary, status=args.status, problems=args.problems, error=args.error)
    return chat.review(args.pipe, args.answer, args.feedback)


def main(argv: list[str] | None = None) -> int:
    """引数を読み、司会役を呼び、1つの JSON を標準出力に書く。"""
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        out = _run(args)
    except ChatError as e:
        out = {"ok": False, "message": str(e)}
    except SystemExit as e:  # 設定やフォルダの誤り（load_config など）は文だけを返す
        out = {"ok": False, "message": str(e.code) if e.code else "設定を読めませんでした"}
    except Exception as e:  # noqa: BLE001 - 想定外でも JSON で返す
        out = {"ok": False, "message": f"想定外の誤りです（{type(e).__name__}: {e}）"}
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    return 0 if out.get("ok") else 1
