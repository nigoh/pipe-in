"""pipe-in worktree：機能ごとの worktree を .claude/worktrees/ に切る・main に入ったものを片付ける（D0048）。

本物の git を一時フォルダで動かす（リポジトリの実物には触れない）。SDK は呼ばない。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipe_in import cli
from pipe_in.dev.worktree import WorktreeError, clean, new, sync


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "test")
    git(root, "config", "user.email", "test@example.com")
    (root / ".gitignore").write_text("/.claude/worktrees/\n", encoding="utf-8")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "init")
    return root


def commit_in(path: Path, name: str) -> None:
    (path / name).write_text("x\n", encoding="utf-8")
    git(path, "add", name)
    git(path, "commit", "-q", "-m", name)


def merged(repo: Path, name: str) -> Path:
    """worktree を切って1つコミットし、main に早送りで入れる。"""
    path = new(repo, name)
    commit_in(path, f"{name}.txt")
    git(repo, "merge", "-q", "--ff-only", f"feat/{name}")
    return path


def test_new_makes_worktree_under_claude_worktrees_on_feat_branch(repo: Path) -> None:
    """D0048-AC-01: 置き場所は .claude/worktrees/<名前>、ブランチは feat/<名前>（--kind で fix・docs）、main から切る。"""
    path = new(repo, "wait-notify")
    assert path == repo / ".claude" / "worktrees" / "wait-notify"
    assert git(path, "branch", "--show-current").strip() == "feat/wait-notify"
    assert git(path, "rev-parse", "HEAD") == git(repo, "rev-parse", "main")
    fix = new(repo, "typo", kind="fix")
    assert git(fix, "branch", "--show-current").strip() == "fix/typo"


def test_new_from_inside_a_worktree_still_uses_main_checkout(repo: Path) -> None:
    """D0048-AC-02: worktree の中から呼んでも、置き場所は主の checkout の .claude/worktrees/（入れ子にしない）。"""
    first = new(repo, "one")
    second = new(first, "two")
    assert second == repo / ".claude" / "worktrees" / "two"


@pytest.mark.parametrize("name", ["", "a/b", "../x", "-x", "x y", "あ", "a" * 65])
def test_new_rejects_bad_names(repo: Path, name: str) -> None:
    """D0048-AC-03: 名前は英数字・. _ - だけ（先頭は英数字、64 字まで）。それ以外は断る。"""
    with pytest.raises(WorktreeError):
        new(repo, name)


def test_new_rejects_existing_name_and_unknown_kind(repo: Path) -> None:
    """D0048-AC-04: 同じ名前の worktree・ブランチがあれば断る。種類は feat・fix・docs だけ。"""
    new(repo, "dup")
    with pytest.raises(WorktreeError, match="dup"):
        new(repo, "dup")
    git(repo, "branch", "feat/taken")
    with pytest.raises(WorktreeError, match="feat/taken"):
        new(repo, "taken")
    with pytest.raises(WorktreeError, match="kind"):
        new(repo, "x", kind="hack")


def test_clean_removes_merged_worktree_and_branch(repo: Path) -> None:
    """D0048-AC-05: main に入ったブランチの worktree を消し、ブランチも消す。"""
    path = merged(repo, "done")
    result = clean(repo)
    assert [r.branch for r in result.removed] == ["feat/done"]
    assert not path.exists()
    assert "feat/done" not in git(repo, "branch", "--list")


def test_clean_keeps_unmerged_dirty_and_outside_worktrees(repo: Path, tmp_path: Path) -> None:
    """D0048-AC-06: main に入っていない・まだコミットしていない変更がある・.claude/worktrees/ の外の worktree は残す（理由を返す）。"""
    unmerged = new(repo, "wip")
    commit_in(unmerged, "c.txt")
    dirty = merged(repo, "dirty")
    (dirty / "a.txt").write_text("changed\n", encoding="utf-8")
    untracked = merged(repo, "untracked")
    (untracked / "new.txt").write_text("n\n", encoding="utf-8")
    outside = tmp_path / "outside"
    git(repo, "worktree", "add", "-q", str(outside), "-b", "feat/outside")
    result = clean(repo)
    assert result.removed == []
    kept = {k.branch: k.reason for k in result.kept}
    assert set(kept) == {"feat/wip", "feat/dirty", "feat/untracked"}
    assert "main" in kept["feat/wip"] and "変更" in kept["feat/dirty"] and "変更" in kept["feat/untracked"]
    for p in (unmerged, dirty, untracked, outside):
        assert p.exists()


def test_clean_keeps_worktree_never_committed_on(repo: Path) -> None:
    """D0048-AC-12: 切ってから一度もコミットしていないブランチは残す（始めたばかりで、ほかの会話が使っているかもしれない）。"""
    path = new(repo, "fresh")
    result = clean(repo)
    assert result.removed == []
    assert [k.branch for k in result.kept] == ["feat/fresh"]
    assert "コミット" in result.kept[0].reason
    assert path.exists()


def test_clean_keeps_the_worktree_it_is_called_from(repo: Path) -> None:
    """D0048-AC-07: 呼んだ場所の worktree は消さない（会話がまだその中にいる）。"""
    path = merged(repo, "here")
    result = clean(path)
    assert result.removed == []
    assert [k.branch for k in result.kept] == ["feat/here"]
    assert path.exists()


def test_clean_dry_run_changes_nothing(repo: Path) -> None:
    """D0048-AC-08: --dry-run では消す予定を返すだけで、何も消さない。"""
    path = merged(repo, "done")
    result = clean(repo, dry_run=True)
    assert [r.branch for r in result.removed] == ["feat/done"]
    assert path.exists()
    assert "feat/done" in git(repo, "branch", "--list")


def test_clean_ignores_ignored_files(repo: Path) -> None:
    """D0048-AC-09: 無視しているファイル（docs/pipeline/・node_modules/ など）だけなら、変更とみなさず消す。"""
    (repo / ".gitignore").write_text("/.claude/worktrees/\n/docs/pipeline/\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "ignore")
    path = merged(repo, "rec")
    (path / "docs" / "pipeline").mkdir(parents=True)
    (path / "docs" / "pipeline" / "state.json").write_text("{}", encoding="utf-8")
    result = clean(repo)
    assert [r.branch for r in result.removed] == ["feat/rec"]
    assert not path.exists()


def test_cli_new_and_clean(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D0048-AC-10: python -m pipe_in worktree new <名前> は切った絶対パスを出す。clean は消したもの・残したものを出す。"""
    assert cli.main(["worktree", "new", "cli", "--project", str(repo)]) == 0
    out = capsys.readouterr().out
    path = repo / ".claude" / "worktrees" / "cli"
    assert str(path) in out and "feat/cli" in out
    commit_in(path, "cli.txt")
    git(repo, "merge", "-q", "--ff-only", "feat/cli")
    assert cli.main(["worktree", "clean", "--project", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "feat/cli" in out and "消しました" in out
    assert not path.exists()
    with pytest.raises(SystemExit, match="pipe-in worktree"):
        cli.main(["worktree", "new", "../bad", "--project", str(repo)])


def test_repository_ignores_claude_worktrees() -> None:
    """D0048-AC-11: このリポジトリの .gitignore が .claude/worktrees/ を載せない。"""
    root = Path(__file__).resolve().parents[1]
    lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/.claude/worktrees/" in lines


# ---- D0049：段の区切りの載せ直しを1つのコマンドに（worktree sync） ----


def test_sync_does_nothing_when_main_has_not_moved(repo: Path) -> None:
    """D0049-AC-01: main が進んでいなければ、何もしないで「進んでいない」を返す。"""
    path = new(repo, "calm")
    commit_in(path, "calm.txt")
    before = git(path, "rev-parse", "HEAD")
    assert sync(path).commits == []
    assert git(path, "rev-parse", "HEAD") == before


def test_sync_rebases_onto_main_and_keeps_uncommitted_changes(repo: Path) -> None:
    """D0049-AC-02: main が進んでいれば、入ったコミットの一覧を返し、--autostash で載せ直す（まだコミットしていない変更も残る）。"""
    path = new(repo, "moving")
    commit_in(path, "mine.txt")
    commit_in(repo, "theirs.txt")
    (path / "a.txt").write_text("wip\n", encoding="utf-8")
    result = sync(path)
    assert [c.split(" ", 1)[1] for c in result.commits] == ["theirs.txt"]
    assert (path / "theirs.txt").exists() and (path / "mine.txt").exists()
    assert (path / "a.txt").read_text(encoding="utf-8") == "wip\n"
    assert git(path, "merge-base", "--is-ancestor", "main", "HEAD") == ""


def test_sync_stops_on_conflict_and_leaves_rebase_for_a_person(repo: Path) -> None:
    """D0049-AC-03: ぶつかったら、合わせ方を書いた WorktreeError で止まる（載せ直しの途中のまま残し、人かメインが合わせる）。"""
    path = new(repo, "clash")
    (path / "a.txt").write_text("mine\n", encoding="utf-8")
    git(path, "commit", "-q", "-am", "mine")
    (repo / "a.txt").write_text("theirs\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "theirs")
    with pytest.raises(WorktreeError, match="rebase --continue"):
        sync(path)
    assert "rebase" in git(path, "status")


def test_sync_refuses_main_checkout(repo: Path) -> None:
    """D0049-AC-04: 主の checkout では載せ直さない（main を main に載せ直すことになる）。"""
    with pytest.raises(WorktreeError, match="worktree"):
        sync(repo)


def test_cli_sync(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D0049-AC-05: python -m pipe_in worktree sync は、入ったコミットと載せ直したことを出す。"""
    path = new(repo, "cli-sync")
    commit_in(repo, "theirs.txt")
    assert cli.main(["worktree", "sync", "--project", str(path)]) == 0
    out = capsys.readouterr().out
    assert "theirs.txt" in out and "載せ直しました" in out
    assert cli.main(["worktree", "sync", "--project", str(path)]) == 0
    assert "進んでいません" in capsys.readouterr().out
