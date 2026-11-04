"""pipe-in skill：/pipe-in のスキルが打つ記録・worktree・決定の番号のコマンドを、確認なしで通してよい形に絞った入口（D0049）。

python -m pipe_in skill record …・skill worktree …・skill decision-number … は、元のコマンドと同じに働くが、
今のフォルダだけを相手にし、任意のファイルを読む旗（--input・--feedback-file）と別の場所を指す旗（--project・--config）を断る。
だから .claude/settings.json の allow に Bash(python -m pipe_in skill:*) を入れてよい。断った旗が要るときは元の形で流す（確認が出る）。
旗は読んだあとの値で検める（短くした形・= の形でも、argparse が読んだ先で見つかる）。
worktree と decision-number は git fetch origin を流す（origin の追跡の枝と FETCH_HEAD だけが書き換わる。D0074）。
git の旗として読まれうる値（--base・--branch）は、worktree の resolve_base と decision_number の NIGHT が、取りに行く前に検めて断る。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import decision_number, record, worktree

# 既定のまま（付けていない）でなければ断る旗：引数の名前 → 既定の値
GUARDED = {
    "record": {"project": Path("."), "config": None, "input": None, "feedback_file": None},
    "worktree": {"project": Path(".")},
    "decision-number": {"project": Path(".")},
}

# 種類 → (引数を読む関数, 流す関数)
COMMANDS = {
    "record": (record._parse, record.run),
    "worktree": (worktree._parse, worktree.run),
    "decision-number": (decision_number._parse, decision_number.run),
}


def _refused(args: argparse.Namespace, kind: str) -> list[str]:
    return [f"--{name.replace('_', '-')}" for name, default in GUARDED[kind].items() if getattr(args, name, default) != default]


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in GUARDED:
        raise SystemExit("pipe-in skill: 後ろに record・worktree・decision-number を続けてください（ほかのコマンドは元の形で流します）")
    kind, rest = argv[0], argv[1:]
    parse, run = COMMANDS[kind]
    args = parse(rest)
    refused = _refused(args, kind)
    if refused:
        raise SystemExit(
            f"pipe-in skill: {'・'.join(refused)} は使えません（今のフォルダだけを相手にする入口です）。"
            f"要るときは python -m pipe_in {kind} … で流してください"
        )
    return run(args)
