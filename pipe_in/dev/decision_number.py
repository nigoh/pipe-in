"""pipe-in decision-number：決定の記録（docs/decisions/D<4けた>-<名前>.md）の次の番号を、1 行で出す（D0074）。

origin の main と、--branch で渡した夜のまとめの枝（night/<名前> の形だけ）の、記録の最大の番号を取り、
手元の作業フォルダの docs/decisions/ も見て、いちばん大きいものの次を出す。
番号を出すだけで、ファイルは作らず、予約もしない。書き換わるのは .git の中の追跡の枝（refs/remotes/origin/*）と FETCH_HEAD だけ。
origin から取れないときは、古い手元の main から黙って出さず、理由を添えて止まる。取れている origin/main から出すなら --no-fetch。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from . import worktree

NUMBER = re.compile(r"D(\d{4})-.+\.md")
NIGHT = re.compile("night/" + worktree.NAME.pattern)
DECISIONS = "docs/decisions/"
NO_FETCH_HINT = "取れている origin/main の版から出すときは --no-fetch を付けてください"


def _largest(names: list[str]) -> int:
    found = [int(m.group(1)) for n in names if (m := NUMBER.fullmatch(n))]
    return max(found, default=0)


def _in_ref(root: Path, ref: str) -> int:
    """参照の docs/decisions/ にある記録の最大の番号（フォルダが無ければ 0）。"""
    out = worktree._git(root, "ls-tree", "--name-only", "-z", ref, "--", DECISIONS).stdout
    return _largest([Path(x).name for x in out.split("\0") if x])


def next_number(where: Path, branch: str | None = None, no_fetch: bool = False) -> str:
    if branch is not None and not NIGHT.fullmatch(branch):
        raise worktree.WorktreeError(f"--branch は night/<名前> の形だけです（{branch!r}）")
    top = Path(worktree._git(where, "rev-parse", "--show-toplevel").stdout.strip())
    branches = ["main", *([branch] if branch else [])]
    if not no_fetch:
        if not worktree.has_origin(top):
            raise worktree.WorktreeError(f"origin という remote がありません。{NO_FETCH_HINT}")
        for b in branches:
            worktree.fetch_origin(top, b, NO_FETCH_HINT)
    best = 0
    for b in branches:
        ref = f"refs/remotes/origin/{b}"
        if worktree._git(top, "rev-parse", "--verify", "--quiet", ref, check=False).returncode != 0:
            raise worktree.WorktreeError(f"手元に origin/{b} が取れていません。--no-fetch を外して取ってください")
        best = max(best, _in_ref(top, ref))
    folder = top / "docs" / "decisions"
    if folder.is_dir():
        best = max(best, _largest([p.name for p in folder.iterdir()]))
    if best + 1 > 9999:
        raise worktree.WorktreeError("決定の記録の番号が 9999 を超えます")
    return f"D{best + 1:04d}"


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="pipe-in decision-number", description="決定の記録の次の番号を出す（ファイルは作らない）")
    p.add_argument("--branch", default=None, help="夜のまとめの枝（night/<名前>）。その枝の記録も見る")
    p.add_argument("--no-fetch", action="store_true", help="origin から取らず、手元に取れている origin/main を使う")
    p.add_argument("--project", type=Path, default=Path("."))
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    return run(_parse(argv))


def run(args: argparse.Namespace) -> int:
    try:
        print(next_number(args.project, branch=args.branch, no_fetch=args.no_fetch))
    except worktree.WorktreeError as e:
        raise SystemExit(f"pipe-in decision-number: {e}") from e
    return 0
