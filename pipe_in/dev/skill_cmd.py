"""pipe-in skill：/pipe-in のスキルが打つ記録と worktree のコマンドを、確認なしで通してよい形に絞った入口（D0049）。

python -m pipe_in skill record …・python -m pipe_in skill worktree … は、record・worktree と同じに働くが、
今のフォルダだけを相手にし、任意のファイルを読む旗（--input・--feedback-file）と別の場所を指す旗（--project・--config）を断る。
だから .claude/settings.json の allow に Bash(python -m pipe_in skill:*) を入れてよい。断った旗が要るときは元の形で流す（確認が出る）。
旗は読んだあとの値で検める（短くした形・= の形でも、argparse が読んだ先で見つかる）。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import record, worktree

# 既定のまま（付けていない）でなければ断る旗：引数の名前 → 既定の値
GUARDED = {
    "record": {"project": Path("."), "config": None, "input": None, "feedback_file": None},
    "worktree": {"project": Path(".")},
}


def _refused(args: argparse.Namespace, kind: str) -> list[str]:
    return [f"--{name.replace('_', '-')}" for name, default in GUARDED[kind].items() if getattr(args, name, default) != default]


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in GUARDED:
        raise SystemExit("pipe-in skill: 後ろに record か worktree を続けてください（ほかのコマンドは元の形で流します）")
    kind, rest = argv[0], argv[1:]
    args = record._parse(rest) if kind == "record" else worktree._parse(rest)
    refused = _refused(args, kind)
    if refused:
        raise SystemExit(
            f"pipe-in skill: {'・'.join(refused)} は使えません（今のフォルダだけを相手にする入口です）。"
            f"要るときは python -m pipe_in {kind} … で流してください"
        )
    return record.run(args) if kind == "record" else worktree.run(args)
