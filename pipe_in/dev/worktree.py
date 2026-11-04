"""pipe-in worktree：機能ごとの worktree を .claude/worktrees/ に切る・main に入ったものを片付ける（D0048）。

/pipe-in のスキルが、始めるときに new で切り、main に入れたあとに clean で片付ける。
置き場所を .claude/worktrees/ にするのは、Claude Code の EnterWorktree が承認なしで移れる場所だから。
消すのは、.claude/worktrees/ の下にあり、main に入っていて、変更が残っておらず、一度はコミットしたブランチだけ（安全側に倒す）。
土台（既定は main）は、origin があれば origin から取った origin/<枝> を使う（D0074）。取れなければ止まる。
手元の枝で進めたいときは --no-fetch。origin が無いリポジトリでは、取らず手元の枝を使う。
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

WORKTREES = Path(".claude") / "worktrees"
KINDS = ("feat", "fix", "docs", "night")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
# 枝の名前に見える形（先頭は英数字、/ を含んでよい）。HEAD・HEAD~2・コミットの略号などは枝の名前とみなさず、取らずにそのまま使う
BRANCHISH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}")
HEX_ID = re.compile(r"[0-9a-fA-F]{7,40}")
# git の失敗の文に入ることがある URL の「ユーザー:秘密@」を出さない（公開前提）
URL_SECRET = re.compile(r"://[^\s/@]+@")
NO_FETCH_HINT = "手元の枝で進めるときは --no-fetch を付けてください"


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


def has_origin(root: Path) -> bool:
    """origin という remote があるか（remote の名前は origin に決めてある）。"""
    return _git(root, "remote", "get-url", "origin", check=False).returncode == 0


def _first_line(text: str) -> str:
    line = next((x for x in text.splitlines() if x.strip()), "").strip()
    return URL_SECRET.sub("://***@", line)


def fetch_origin(root: Path, branch: str, hint: str) -> None:
    """origin から <枝> を取り、refs/remotes/origin/<枝> を更新する。取れなければ WorktreeError（hint を添える）。
    + 始まりの refspec を渡すので、枝の名前が git の旗として読まれない。"""
    done = _git(root, "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}", check=False)
    if done.returncode != 0:
        raise WorktreeError(f"origin から {branch} を取れませんでした（{_first_line(done.stderr)}）。{hint}")


def resolve_base(root: Path, base: str, no_fetch: bool = False) -> tuple[str, str]:
    """(git に渡す参照, 表示名)。origin があり、枝の名前に見える base なら、origin から取って refs/remotes/origin/<枝> を使う。"""
    if not base or base.startswith("-") or ".." in base or re.search(r"\s", base):
        raise WorktreeError(f"--base の値が正しくありません（{base!r}）")
    if no_fetch or not has_origin(root):
        return base, base
    if not BRANCHISH.fullmatch(base) or base == "HEAD" or HEX_ID.fullmatch(base):
        return base, base
    branch = base.removeprefix("origin/")
    fetch_origin(root, branch, NO_FETCH_HINT)
    return f"refs/remotes/origin/{branch}", f"origin/{branch}"


def _new(where: Path, name: str, kind: str, base: str, no_fetch: bool) -> tuple[Path, str]:
    """new の本体。(切った場所, 土台の表示名) を返す。"""
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
    if kind == "night" and not no_fetch and has_origin(root):
        found = _git(root, "ls-remote", "--exit-code", "--heads", "origin", f"refs/heads/{branch}", check=False)
        if found.returncode == 0:
            raise WorktreeError(f"ブランチ {branch} はもう origin にあります（同じ日の2回目は名前に -2 を付けてください）")
        if found.returncode != 2:
            raise WorktreeError(f"origin の {branch} を取れませんでした（{_first_line(found.stderr)}）。{NO_FETCH_HINT}")
    ref, shown = resolve_base(root, base, no_fetch)
    _git(root, "worktree", "add", "--no-track", "-q", str(path), "-b", branch, ref)
    return path, shown


def new(where: Path, name: str, kind: str = "feat", base: str = "main", no_fetch: bool = False) -> Path:
    """<主の checkout>/.claude/worktrees/<名前> に、<種類>/<名前> のブランチを base から切る。切った場所を返す。"""
    return _new(where, name, kind, base, no_fetch)[0]


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


def _why_keep(root: Path, path: Path, branch: str, ref: str, shown: str, here: Path) -> str:
    """残す理由。空なら消してよい。ref は git に渡す参照、shown は文に出す名前。"""
    if path == here or path in here.parents:
        return "いまいる worktree です"
    if _git(root, "merge-base", "--is-ancestor", branch, ref, check=False).returncode != 0:
        return f"{shown} にまだ入っていません"
    if _git(path, "status", "--porcelain").stdout.strip():
        return "まだコミットしていない変更があります"
    if len(_git(root, "reflog", "show", "--format=%H", f"refs/heads/{branch}").stdout.split()) < 2:
        return "切ってから一度もコミットしていません（始めたばかりかもしれません）"
    return ""


def clean(where: Path, base: str = "main", dry_run: bool = False, no_fetch: bool = False) -> CleanResult:
    """.claude/worktrees/ の下の worktree のうち、base に入ったものを、ブランチごと消す。"""
    root = main_checkout(where)
    ref, shown = resolve_base(root, base, no_fetch)
    here = Path(where).resolve()
    under = (root / WORKTREES).resolve()
    result = CleanResult()
    for path, branch in _worktrees(root):
        if under not in path.parents:
            continue
        reason = _why_keep(root, path, branch, ref, shown, here)
        if reason:
            result.kept.append(Entry(path, branch, reason))
            continue
        if not dry_run:
            _git(root, "worktree", "remove", str(path))
            # 入ったかどうかは _why_keep が ref で確かめ済み。手元の main が古いと -d は断るので -D で消す
            _git(root, "branch", "-D", branch)
        result.removed.append(Entry(path, branch))
    return result


@dataclass
class SyncResult:
    commits: list[str] = field(default_factory=list)
    base: str = ""  # 載せた先の表示名（origin/main など）


def sync(where: Path, base: str = "main", no_fetch: bool = False) -> SyncResult:
    """worktree を base に載せ直す（git rebase --autostash）。base が進んでいなければ何もしない。入ったコミット（1行ずつ）を返す。"""
    top = Path(_git(where, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if top == main_checkout(where):
        raise WorktreeError("主の checkout では載せ直しません。worktree の中で流してください")
    ref, shown = resolve_base(top, base, no_fetch)
    commits = _git(top, "log", "--oneline", f"HEAD..{ref}").stdout.splitlines()
    if commits and _git(top, "rebase", "--autostash", ref, check=False).returncode != 0:
        raise WorktreeError(
            f"{shown} に載せ直す途中でぶつかりました。git status でぶつかったファイルを見て、両方の意図を残すように合わせ、"
            "git add してから git rebase --continue で続けてください"
        )
    return SyncResult(commits, shown)


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="pipe-in worktree", description="機能ごとの worktree を切る・片付ける")
    sub = p.add_subparsers(dest="action", required=True)
    n = sub.add_parser("new", help=".claude/worktrees/<名前> に <種類>/<名前> のブランチを origin の main から切る")
    n.add_argument("name")
    n.add_argument("--kind", default="feat", choices=KINDS)
    n.add_argument("--base", default="main")
    c = sub.add_parser("clean", help="main に入った worktree をブランチごと消す")
    c.add_argument("--base", default="main")
    c.add_argument("--dry-run", action="store_true")
    y = sub.add_parser("sync", help="いまの worktree を origin の main に載せ直す（進んでいなければ何もしない）")
    y.add_argument("--base", default="main")
    for s in (n, c, y):
        s.add_argument("--project", type=Path, default=Path("."))
        s.add_argument("--no-fetch", action="store_true", help="origin から取らず、手元に取れている枝を使う")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    return run(_parse(argv))


def run(args: argparse.Namespace) -> int:
    """読んだ引数で切る・片付ける・載せ直す（pipe-in skill worktree も、旗を検めてからここを呼ぶ）。"""
    try:
        if args.action == "sync":
            done = sync(args.project, base=args.base, no_fetch=args.no_fetch)
            if not done.commits:
                print(f"{done.base} は進んでいません")
                return 0
            print(f"{done.base} に入ったコミット:")
            for line in done.commits:
                print(f"  {line}")
            print(f"載せ直しました（{done.base}）")
            return 0
        if args.action == "new":
            path, shown = _new(args.project, args.name, args.kind, args.base, args.no_fetch)
            print(f"切りました: {path}（ブランチ {args.kind}/{args.name}。土台 {shown}）")
            return 0
        result = clean(args.project, base=args.base, dry_run=args.dry_run, no_fetch=args.no_fetch)
    except WorktreeError as e:
        raise SystemExit(f"pipe-in worktree: {e}") from e
    done_word = "消す予定" if args.dry_run else "消しました"
    for e in result.removed:
        print(f"{done_word}: {e.path}（ブランチ {e.branch}）")
    for e in result.kept:
        print(f"残しました: {e.path}（ブランチ {e.branch}。{e.reason}）")
    if not result.removed and not result.kept:
        print("片付ける worktree はありません")
    return 0
