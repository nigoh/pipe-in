"""pipe-in worktree：機能ごとの worktree を .claude/worktrees/ に切る・main に入ったものを片付ける（D0048）。

/pipe-in のスキルが、始めるときに new で切り、main に入れたあとに clean で片付ける。
置き場所を .claude/worktrees/ にするのは、Claude Code の EnterWorktree が承認なしで移れる場所だから。
消すのは、.claude/worktrees/ の下にあり、main に入っていて、変更が残っておらず、一度はコミットしたブランチだけ（安全側に倒す）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

WORKTREES = Path(".claude") / "worktrees"
KINDS = ("feat", "fix", "docs")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class WorktreeError(Exception):
    """worktree を切れない・片付けられない（名前の誤り・同じ名前がある・git が断った など）。"""


@dataclass(frozen=True)
class Entry:
    path: Path
    branch: str
    reason: str = ""


@dataclass
class CleanResult:
    removed: list[Entry] = field(default_factory=list)
    kept: list[Entry] = field(default_factory=list)


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and done.returncode != 0:
        raise WorktreeError(f"git {' '.join(args)} が失敗しました: {done.stderr.strip()}")
    return done


def main_checkout(where: Path) -> Path:
    """主の checkout（.git がフォルダの作業フォルダ）。worktree の中から呼んでも同じ場所を返す。"""
    common = _git(where, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    return Path(common).resolve().parent


def new(where: Path, name: str, kind: str = "feat", base: str = "main") -> Path:
    """<主の checkout>/.claude/worktrees/<名前> に、<種類>/<名前> のブランチを base から切る。切った場所を返す。"""
    if kind not in KINDS:
        raise WorktreeError(f"kind は {'・'.join(KINDS)} のどれかにしてください（{kind}）")
    if not NAME.fullmatch(name):
        raise WorktreeError(f"名前は英数字と . _ - だけ（先頭は英数字、64 字まで）にしてください（{name!r}）")
    root = main_checkout(where)
    path = root / WORKTREES / name
    branch = f"{kind}/{name}"
    if path.exists():
        raise WorktreeError(f"{path} はもうあります（{name}）")
    if _git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0:
        raise WorktreeError(f"ブランチ {branch} はもうあります")
    _git(root, "worktree", "add", "-q", str(path), "-b", branch, base)
    return path


def _worktrees(root: Path) -> list[tuple[Path, str]]:
    """git worktree list --porcelain の (場所, ブランチ名)。ブランチの無いもの（detached）は除く。"""
    out = _git(root, "worktree", "list", "--porcelain").stdout
    found: list[tuple[Path, str]] = []
    for block in out.strip().split("\n\n"):
        lines = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
        ref = lines.get("branch", "")
        if "worktree" in lines and ref.startswith("refs/heads/"):
            found.append((Path(lines["worktree"]).resolve(), ref.removeprefix("refs/heads/")))
    return found


def _why_keep(root: Path, path: Path, branch: str, base: str, here: Path) -> str:
    """残す理由。空なら消してよい。"""
    if path == here or path in here.parents:
        return "いまいる worktree です"
    if _git(root, "merge-base", "--is-ancestor", branch, base, check=False).returncode != 0:
        return f"{base} にまだ入っていません"
    if _git(path, "status", "--porcelain").stdout.strip():
        return "まだコミットしていない変更があります"
    if len(_git(root, "reflog", "show", "--format=%H", f"refs/heads/{branch}").stdout.split()) < 2:
        return "切ってから一度もコミットしていません（始めたばかりかもしれません）"
    return ""


def clean(where: Path, base: str = "main", dry_run: bool = False) -> CleanResult:
    """.claude/worktrees/ の下の worktree のうち、base に入ったものを、ブランチごと消す。"""
    root = main_checkout(where)
    here = Path(where).resolve()
    under = (root / WORKTREES).resolve()
    result = CleanResult()
    for path, branch in _worktrees(root):
        if under not in path.parents:
            continue
        reason = _why_keep(root, path, branch, base, here)
        if reason:
            result.kept.append(Entry(path, branch, reason))
            continue
        if not dry_run:
            _git(root, "worktree", "remove", str(path))
            _git(root, "branch", "-d", branch)
        result.removed.append(Entry(path, branch))
    return result


@dataclass
class SyncResult:
    commits: list[str] = field(default_factory=list)


def sync(where: Path, base: str = "main") -> SyncResult:
    """worktree を base に載せ直す（git rebase --autostash）。base が進んでいなければ何もしない。入ったコミット（1行ずつ）を返す。"""
    top = Path(_git(where, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if top == main_checkout(where):
        raise WorktreeError("主の checkout では載せ直しません。worktree の中で流してください")
    commits = _git(top, "log", "--oneline", f"HEAD..{base}").stdout.splitlines()
    if commits and _git(top, "rebase", "--autostash", base, check=False).returncode != 0:
        raise WorktreeError(
            f"{base} に載せ直す途中でぶつかりました。git status でぶつかったファイルを見て、両方の意図を残すように合わせ、"
            "git add してから git rebase --continue で続けてください"
        )
    return SyncResult(commits)


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="pipe-in worktree", description="機能ごとの worktree を切る・片付ける")
    sub = p.add_subparsers(dest="action", required=True)
    n = sub.add_parser("new", help=".claude/worktrees/<名前> に <種類>/<名前> のブランチを切る")
    n.add_argument("name")
    n.add_argument("--kind", default="feat", choices=KINDS)
    n.add_argument("--base", default="main")
    c = sub.add_parser("clean", help="main に入った worktree をブランチごと消す")
    c.add_argument("--base", default="main")
    c.add_argument("--dry-run", action="store_true")
    y = sub.add_parser("sync", help="いまの worktree を main に載せ直す（main が進んでいなければ何もしない）")
    y.add_argument("--base", default="main")
    for s in (n, c, y):
        s.add_argument("--project", type=Path, default=Path("."))
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    return run(_parse(argv))


def run(args: argparse.Namespace) -> int:
    """読んだ引数で切る・片付ける・載せ直す（pipe-in skill worktree も、旗を検めてからここを呼ぶ）。"""
    try:
        if args.action == "sync":
            commits = sync(args.project, base=args.base).commits
            if not commits:
                print(f"{args.base} は進んでいません")
                return 0
            print(f"{args.base} に入ったコミット:")
            for line in commits:
                print(f"  {line}")
            print(f"載せ直しました（{args.base}）")
            return 0
        if args.action == "new":
            path = new(args.project, args.name, kind=args.kind, base=args.base)
            print(f"切りました: {path}（ブランチ {args.kind}/{args.name}）")
            return 0
        result = clean(args.project, base=args.base, dry_run=args.dry_run)
    except WorktreeError as e:
        raise SystemExit(f"pipe-in worktree: {e}") from e
    done = "消す予定" if args.dry_run else "消しました"
    for e in result.removed:
        print(f"{done}: {e.path}（ブランチ {e.branch}）")
    for e in result.kept:
        print(f"残しました: {e.path}（ブランチ {e.branch}。{e.reason}）")
    if not result.removed and not result.kept:
        print("片付ける worktree はありません")
    return 0
