"""D0074：pipe-in worktree は、土台を origin から取ってから使う（--no-fetch で手元の枝）。夜のまとめの枝 night/<名前> も切れる。

本物の git を一時フォルダで動かす（origin は一時の bare リポジトリ、手元は clone）。SDK も GitHub も呼ばず、ネットワークにも出ない
（取れない場合の確かめは、存在しないパスと、閉じているローカルのポートだけ）。リポジトリの実物には書かない。

- `proj` は手元（clone）、`other` は origin を進める道具（もう 1 つの clone）、`origin` は bare、`local_only` は remote の無いリポジトリ。
- 今の作りのままで通るテストは、名前の末尾を _守る にし、説明の末尾に「（今のまま通る。守る）」と書く
  （remote の無い形・旗の形を断ること・主の checkout で断ることなど。実装のあとも壊れないための検査）。
- tests/test_worktree.py（remote の無い一時のリポジトリ。取らない前提）は、変えずに通ること（D0074-AC-11 の後半）。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipe_in import cli
from pipe_in.dev.worktree import WorktreeError, clean, new, sync

NIGHT = "night/2026-11-02"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def git_status(cwd: Path, *args: str) -> int:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).returncode


def head(path: Path, ref: str = "HEAD") -> str:
    return git(path, "rev-parse", ref).strip()


def configure(path: Path) -> None:
    git(path, "config", "user.name", "test")
    git(path, "config", "user.email", "test@example.com")


def commit_in(path: Path, name: str) -> None:
    (path / name).write_text("x\n", encoding="utf-8")
    git(path, "add", name)
    git(path, "commit", "-q", "-m", name)


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """ネットワークに出ない：プロキシを外し、認証の入力待ちもしない（取れない形はローカルのパス・閉じたポートだけで作る）。"""
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    path = tmp_path / "origin.git"
    path.mkdir()
    git(path, "init", "-q", "--bare", "-b", "main")
    return path


@pytest.fixture
def proj(tmp_path: Path, origin: Path) -> Path:
    """手元。origin の main に初期コミットを push してある。"""
    root = tmp_path / "proj"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    configure(root)
    git(root, "remote", "add", "origin", str(origin))
    (root / ".gitignore").write_text("/.claude/worktrees/\n", encoding="utf-8")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "init")
    git(root, "push", "-q", "origin", "main")
    return root


@pytest.fixture
def other(tmp_path: Path, origin: Path, proj: Path) -> Path:
    """origin を進める道具（もう 1 つの clone）。proj が初期コミットを push したあとに clone する。"""
    root = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(origin), str(root))
    configure(root)
    return root


@pytest.fixture
def local_only(tmp_path: Path) -> Path:
    """remote の無い一時のリポジトリ（tests/test_worktree.py の repo と同じ形）。"""
    root = tmp_path / "local-only"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    configure(root)
    (root / ".gitignore").write_text("/.claude/worktrees/\n", encoding="utf-8")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "init")
    return root


def advance_origin_main(other: Path, name: str = "theirs.txt") -> str:
    """other から origin の main に 1 コミット push する。そのコミットを返す。proj の main・origin/main の追跡はそのまま（古いまま）。"""
    commit_in(other, name)
    git(other, "push", "-q", "origin", "HEAD:main")
    return head(other)


def push_night(other: Path, branch: str = NIGHT, name: str = "night.txt") -> str:
    """other から origin に night/… の枝を作り、1 コミット載せて push する。その先頭を返す。"""
    git(other, "checkout", "-q", "-b", branch)
    commit_in(other, name)
    git(other, "push", "-q", "origin", branch)
    tip = head(other)
    git(other, "checkout", "-q", "main")
    return tip


def break_origin(proj: Path, tmp_path: Path) -> None:
    """origin の場所を、存在しないパスに替える（remote はあるが取れない形）。"""
    git(proj, "remote", "set-url", "origin", str(tmp_path / "gone.git"))


def merged_to_origin(proj: Path, name: str) -> Path:
    """worktree を切って 1 コミットし、origin の main へ push する（手元の main は古いまま）。"""
    path = new(proj, name)
    commit_in(path, f"{name}.txt")
    git(path, "push", "-q", "origin", "HEAD:main")
    return path


def assert_fetch_failure(message: str, tmp_path: Path) -> None:
    """取れなかった文：取れなかったことと、手元の枝で進めたいときの旗 --no-fetch を示す（設計では「取れませんでした」）。
    一時フォルダの名前にテストの名前（取れない…）が入るので、パスは外してから見る。"""
    message = message.replace(str(tmp_path), "<tmp>")
    assert "取れ" in message, f"取れなかったことが文に無い：{message}"
    assert "--no-fetch" in message, f"--no-fetch が文に無い：{message}"


# ---- D0074-AC-01・02：origin から取ってその先頭から切る ------------------------------------------------------------------


def test_D0074_AC_01_newはoriginのmainの先頭から切る_手元のmainが古くても(proj: Path, other: Path) -> None:
    """D0074-AC-01: origin の main が手元の main より進んでいても、worktree new X の枝の先頭は origin の main の先頭と同じになる。"""
    tip = advance_origin_main(other)
    assert head(proj, "main") != tip  # 手元の main は古いまま
    path = new(proj, "x")
    assert head(path) == tip
    assert git(path, "branch", "--show-current").strip() == "feat/x"


def test_D0074_AC_01_newで切った枝に上流を付けない_守る(proj: Path) -> None:
    """D0074-AC-01: 設計の --no-track。切った枝に上流（origin/main）を結ばない（素の git push が main へ向かわないため。今までの手元の main から切る形と同じ）。
    （今のまま通る。守る）"""
    path = new(proj, "x")
    assert git_status(path, "config", "--get", "branch.feat/x.remote") != 0
    assert git_status(path, "rev-parse", "--abbrev-ref", "feat/x@{upstream}") != 0


def test_D0074_AC_02_base_night枝はoriginから取ってその先頭から切る_手元に枝が無くても(proj: Path, other: Path) -> None:
    """D0074-AC-02: new X --base night/2026-11-02 は、origin の night/2026-11-02 を取って、その先頭から切る（手元にその枝は無い）。"""
    tip = push_night(other)
    assert git_status(proj, "rev-parse", "--verify", "--quiet", f"refs/heads/{NIGHT}") != 0
    path = new(proj, "x", base=NIGHT)
    assert head(path) == tip


def test_D0074_AC_02_base_origin_mainも取ってからそのまま使う(proj: Path, other: Path) -> None:
    """D0074-AC-02: new X --base origin/main は、origin の main を取ってから、その origin/main をそのまま土台にする
    （proj の origin/main の追跡は古いまま。取らないと古い先頭から切ってしまう）。"""
    tip = advance_origin_main(other)
    assert head(proj, "origin/main") != tip
    path = new(proj, "x", base="origin/main")
    assert head(path) == tip


# ---- D0074-AC-03：remote が無いリポジトリ ---------------------------------------------------------------------------------


def test_D0074_AC_03_originの無いリポジトリでは手元のmainから切る_取らず失敗しない_守る(local_only: Path) -> None:
    """D0074-AC-03: origin の remote が無い一時のリポジトリでは、new X は今までどおり手元の main から切る（取らず、失敗しない）。（今のまま通る。守る）"""
    path = new(local_only, "x")
    assert head(path) == head(local_only, "main")
    assert git(path, "branch", "--show-current").strip() == "feat/x"


# ---- D0074-AC-04：取れないときは手元の枝へ切り替えず止まる -------------------------------------------------------------------


@pytest.mark.parametrize("how", ["origin のパスが無い", "その枝が origin に無い"])
def test_D0074_AC_04_取れないときnewは手元の枝へ切り替えず止まり枝もworktreeも作らない(proj: Path, tmp_path: Path, how: str) -> None:
    """D0074-AC-04: remote はあるが取れない（origin のパスが無い・その枝が origin に無い）とき、new は手元の枝へ切り替えずに WorktreeError で止まる。
    文に取れなかったことと --no-fetch が入り、枝も worktree も作られない。"""
    kwargs = {}
    if how == "origin のパスが無い":
        break_origin(proj, tmp_path)
    else:
        kwargs["base"] = "night/none"
    with pytest.raises(WorktreeError) as e:
        new(proj, "x", **kwargs)
    assert_fetch_failure(str(e.value), tmp_path)
    assert not (proj / ".claude" / "worktrees" / "x").exists()
    assert "feat/x" not in git(proj, "branch", "--list")


@pytest.mark.parametrize("how", ["origin のパスが無い", "その枝が origin に無い"])
def test_D0074_AC_04_取れないときsyncは手元の枝へ切り替えず止まり何も変えない(proj: Path, tmp_path: Path, how: str) -> None:
    """D0074-AC-04: 取れないとき、sync は手元の枝（main）へ切り替えずに止まり、文に取れなかったことと --no-fetch が入る。載せ直しは起きない。"""
    wt = new(proj, "w")
    commit_in(wt, "mine.txt")
    commit_in(proj, "local-only.txt")  # 手元の main だけ進んでいる（黙って手元の main に載せ直すと、これが入ってしまう）
    before = head(wt)
    kwargs = {}
    if how == "origin のパスが無い":
        break_origin(proj, tmp_path)
    else:
        kwargs["base"] = "night/none"
    with pytest.raises(WorktreeError) as e:
        sync(wt, **kwargs)
    assert_fetch_failure(str(e.value), tmp_path)
    assert head(wt) == before
    assert not (wt / "local-only.txt").exists()


@pytest.mark.parametrize("how", ["origin のパスが無い", "その枝が origin に無い"])
def test_D0074_AC_04_取れないときcleanは手元の枝へ切り替えず止まり何も消さない(proj: Path, tmp_path: Path, how: str) -> None:
    """D0074-AC-04: 取れないとき、clean は止まり、文に取れなかったことと --no-fetch が入る。何も消さない（worktree もブランチも残る）。"""
    wt = merged_to_origin(proj, "done")
    git(proj, "merge", "-q", "--ff-only", "feat/done")  # 手元の main にも入れる（黙って手元の main で判断すると消えてしまう形）
    kwargs = {}
    if how == "origin のパスが無い":
        break_origin(proj, tmp_path)
    else:
        kwargs["base"] = "night/none"
    with pytest.raises(WorktreeError) as e:
        clean(proj, **kwargs)
    assert_fetch_failure(str(e.value), tmp_path)
    assert wt.exists()
    assert "feat/done" in git(proj, "branch", "--list")


def test_D0074_AC_04_取れなかった文に秘密を出さない(proj: Path, tmp_path: Path) -> None:
    """D0074-AC-04: origin の URL に user:token@ が入っていても、取れなかった文に token が出ない（公開前提。git の失敗の文に URL が入ることがあるため）。
    取れない形は、閉じているローカルのポート（ネットワークには出ない）。"""
    secret = "token123"  # 偽の値。URL を組み立てて書くのは、ファイルの文字がメールアドレスの検査（test_rules.py）に見えないため
    git(proj, "remote", "set-url", "origin", f"http://user:{secret}@127.0.0.1:1/x.git")
    with pytest.raises(WorktreeError) as e:
        new(proj, "x")
    assert secret not in str(e.value)
    assert_fetch_failure(str(e.value), tmp_path)


@pytest.mark.parametrize("value", ["--upload-pack=touch {marker}", "-x"])
def test_D0074_AC_04_baseが旗の形なら断り旗の中のコマンドは動かない_守る(proj: Path, tmp_path: Path, value: str) -> None:
    """D0074-AC-04: --base が - で始まる値（git fetch の旗 --upload-pack=… は任意のコマンドを起こせる）は断る。旗の中のコマンドが動かないこと
    （一時のフォルダにファイルができない）と、枝が作られないことを見る。skill の入口でも同じに断る（D0074-AC-09）。
    今は git が旗として断るので通る。実装のあとは、取る前に断る形になる（どちらでも壊れない見張り）。（今のまま通る。守る）"""
    marker = tmp_path / "marker"
    base = value.format(marker=marker)
    with pytest.raises(WorktreeError):
        new(proj, "f", base=base)
    with pytest.raises((SystemExit, WorktreeError)):
        cli.main(["worktree", "new", "f2", f"--base={base}", "--project", str(proj)])
    assert not marker.exists()
    assert "feat/f" not in git(proj, "branch", "--list") and "feat/f2" not in git(proj, "branch", "--list")


@pytest.mark.parametrize("value", ["--upload-pack=touch {marker}", "-x"])
def test_D0074_AC_04_skill_worktreeでもbaseが旗の形なら断り旗の中のコマンドは動かない_守る(
    proj: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """D0074-AC-04・09: pipe-in skill worktree new でも、--base が旗の形なら断る（allow に入っている入口から旗が通らない）。（今のまま通る。守る）"""
    marker = tmp_path / "marker"
    monkeypatch.chdir(proj)
    with pytest.raises((SystemExit, WorktreeError)):
        cli.main(["skill", "worktree", "new", "f", f"--base={value.format(marker=marker)}"])
    assert not marker.exists()
    assert "feat/f" not in git(proj, "branch", "--list")


# ---- D0074-AC-05：--no-fetch ------------------------------------------------------------------------------------------------


def test_D0074_AC_05_no_fetchならnewは取れなくても手元のmainを土台に動く(proj: Path, tmp_path: Path) -> None:
    """D0074-AC-05: 取れない条件のままでも、--no-fetch を付けると、new は手元の main を土台にして今までどおり切る。"""
    break_origin(proj, tmp_path)
    path = new(proj, "x", no_fetch=True)
    assert head(path) == head(proj, "main")


def test_D0074_AC_05_no_fetchならsyncは取れなくても手元のmainに載せる(proj: Path, tmp_path: Path) -> None:
    """D0074-AC-05: 取れない条件のまま、--no-fetch を付けると、sync は手元の main に載せ直す（今までの動き）。"""
    wt = new(proj, "w")
    commit_in(wt, "mine.txt")
    commit_in(proj, "theirs.txt")
    break_origin(proj, tmp_path)
    result = sync(wt, no_fetch=True)
    assert [c.split(" ", 1)[1] for c in result.commits] == ["theirs.txt"]
    assert (wt / "theirs.txt").exists() and (wt / "mine.txt").exists()


def test_D0074_AC_05_no_fetchならcleanは取れなくても手元のmainに入った枝を消す(proj: Path, tmp_path: Path) -> None:
    """D0074-AC-05: 取れない条件のまま、--no-fetch を付けると、clean は手元の main に入った枝を消す（今までの動き）。"""
    wt = new(proj, "done")
    commit_in(wt, "done.txt")
    git(proj, "merge", "-q", "--ff-only", "feat/done")
    break_origin(proj, tmp_path)
    result = clean(proj, no_fetch=True)
    assert [r.branch for r in result.removed] == ["feat/done"]
    assert not wt.exists()


def test_D0074_AC_05_cliのno_fetchは3つのコマンドで受け付ける(proj: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D0074-AC-05: pipe-in worktree の new・sync・clean が --no-fetch を受け付ける（取れない条件のまま、終了コード 0）。"""
    break_origin(proj, tmp_path)
    assert cli.main(["worktree", "new", "n", "--no-fetch", "--project", str(proj)]) == 0
    wt = proj / ".claude" / "worktrees" / "n"
    assert cli.main(["worktree", "sync", "--no-fetch", "--project", str(wt)]) == 0
    assert cli.main(["worktree", "clean", "--no-fetch", "--project", str(proj)]) == 0
    capsys.readouterr()


# ---- D0074-AC-06・07：sync ----------------------------------------------------------------------------------------------------


def test_D0074_AC_06_syncはoriginのmainに載せコミットの行が出て変更は残る(
    proj: Path, other: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """D0074-AC-06: origin の main に新しいコミットが 1 つ入っているとき、sync は worktree の枝をそれに載せ（git log に入る）、入ったコミットの行を出す。
    手元の main は動いていなくてよい。コミットされていない変更は残る。"""
    wt = new(proj, "moving")
    commit_in(wt, "mine.txt")
    (wt / "a.txt").write_text("wip\n", encoding="utf-8")
    tip = advance_origin_main(other)
    assert head(proj, "main") != tip
    assert cli.main(["worktree", "sync", "--project", str(wt)]) == 0
    out = capsys.readouterr().out
    assert "theirs.txt" in out, out
    assert git(wt, "merge-base", "--is-ancestor", tip, "HEAD") == ""
    assert "theirs.txt" in git(wt, "log", "--oneline")
    assert (wt / "mine.txt").exists() and (wt / "theirs.txt").exists()
    assert (wt / "a.txt").read_text(encoding="utf-8") == "wip\n"


def test_D0074_AC_07_syncはoriginが進んでいなければ進んでいませんと出して何も変えない_守る(
    proj: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """D0074-AC-07: origin の main が進んでいなければ「進んでいません」と出して、何も変えない（HEAD もファイルもそのまま）。
    （今のまま通る。守る。手元の main も進んでいない形なので。進んでいるのが手元の main だけの形は次のテストが赤で見る）"""
    wt = new(proj, "calm")
    commit_in(wt, "calm.txt")
    before = head(wt)
    assert cli.main(["worktree", "sync", "--project", str(wt)]) == 0
    assert "進んでいません" in capsys.readouterr().out
    assert head(wt) == before


def test_D0074_AC_07_手元のmainだけ進んでいてoriginが進んでいなければsyncは何もしない(
    proj: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """D0074-AC-07: 載せ直す先は origin の main。手元の main にだけコミットがあり、origin の main が進んでいなければ、何もしない
    （手元の main に載せ直さない。FR-07）。"""
    wt = new(proj, "calm")
    commit_in(wt, "mine.txt")
    commit_in(proj, "local-only.txt")
    before = head(wt)
    assert cli.main(["worktree", "sync", "--project", str(wt)]) == 0
    assert "進んでいません" in capsys.readouterr().out
    assert head(wt) == before
    assert not (wt / "local-only.txt").exists()


def test_D0074_AC_07_syncはぶつかると今までの文で止まる(proj: Path, other: Path) -> None:
    """D0074-AC-07: origin の main の変更と自分の変更がぶつかるときは、今までどおりの文（git rebase --continue を含む）で WorktreeError で止まり、
    載せ直しの途中のまま残す。"""
    wt = new(proj, "clash")
    (wt / "a.txt").write_text("mine\n", encoding="utf-8")
    git(wt, "commit", "-q", "-am", "mine")
    (other / "a.txt").write_text("theirs\n", encoding="utf-8")
    git(other, "commit", "-q", "-am", "theirs")
    git(other, "push", "-q", "origin", "HEAD:main")
    with pytest.raises(WorktreeError, match="rebase --continue"):
        sync(wt)
    assert "rebase" in git(wt, "status")


def test_D0074_AC_07_syncは主のcheckoutでは取る前に断る_守る(proj: Path, tmp_path: Path) -> None:
    """D0074-AC-07: 主の checkout では今までどおり断る。取る前に断る（origin が取れない形でも、断る文は取れなかった話にならない。ネットワークを使わない）。
    （今のまま通る。守る）"""
    break_origin(proj, tmp_path)
    with pytest.raises(WorktreeError) as e:
        sync(proj)
    assert "worktree" in str(e.value) and "--no-fetch" not in str(e.value)


# ---- D0074-AC-08：clean --------------------------------------------------------------------------------------------------------


def test_D0074_AC_08_cleanはoriginのmainに入った枝を手元のmainが古くても消す(proj: Path) -> None:
    """D0074-AC-08: 枝が origin の main に入っている（origin の main へ push して取れる）とき、手元の main が古いままでも、その worktree とブランチを消す
    （git branch -d は手元の main に入っていないと断るので -D で消す。入ったかは先に確かめる）。origin/main の追跡も古くして、取らないと判断できない形にする。"""
    wt = merged_to_origin(proj, "done")
    init = head(proj, "main")
    git(proj, "update-ref", "refs/remotes/origin/main", init)  # 追跡を古い位置に戻す（clean が取る必要がある）
    result = clean(proj)
    assert [r.branch for r in result.removed] == ["feat/done"]
    assert not wt.exists()
    assert "feat/done" not in git(proj, "branch", "--list")
    assert head(proj, "main") == init  # 手元の main は動かさない


def test_D0074_AC_08_cleanはoriginのmainに入っていない枝を残し理由にorigin_mainを出す(proj: Path) -> None:
    """D0074-AC-08: origin の main に入っていない枝（コミットしたが push していない）は残し、理由に origin/main が入る。"""
    wt = new(proj, "wip")
    commit_in(wt, "c.txt")
    result = clean(proj)
    assert result.removed == []
    assert [k.branch for k in result.kept] == ["feat/wip"]
    assert "origin/main" in result.kept[0].reason, result.kept[0].reason
    assert wt.exists()


# ---- D0074-AC-09：skill の入口 --------------------------------------------------------------------------------------------------


def test_D0074_AC_09_skill_worktree_newはoriginのmainの先頭から切り土台を出す(
    proj: Path, other: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """D0074-AC-09: pipe-in skill worktree new X が AC-01 と同じに働く（origin の main の先頭から切る）。出力に土台の名前（origin/main）が入る。"""
    tip = advance_origin_main(other)
    monkeypatch.chdir(proj)
    assert cli.main(["skill", "worktree", "new", "x"]) == 0
    out = capsys.readouterr().out
    assert head(proj / ".claude" / "worktrees" / "x") == tip
    assert "origin/main" in out, out


def test_D0074_AC_09_skill_worktree_syncはAC06と同じに働く(
    proj: Path, other: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """D0074-AC-09: pipe-in skill worktree sync が AC-06 と同じに働く（origin の main に載せ、入ったコミットの行を出す）。"""
    wt = new(proj, "moving")
    tip = advance_origin_main(other)
    monkeypatch.chdir(wt)
    assert cli.main(["skill", "worktree", "sync"]) == 0
    assert "theirs.txt" in capsys.readouterr().out
    assert git(wt, "merge-base", "--is-ancestor", tip, "HEAD") == ""


def test_D0074_AC_09_skill_worktree_cleanはAC08と同じに働く(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """D0074-AC-09: pipe-in skill worktree clean が AC-08 と同じに働く（手元の main が古くても、origin の main に入った枝を消す）。"""
    wt = merged_to_origin(proj, "done")
    git(proj, "update-ref", "refs/remotes/origin/main", head(proj, "main"))
    monkeypatch.chdir(proj)
    assert cli.main(["skill", "worktree", "clean"]) == 0
    assert not wt.exists()
    assert "feat/done" not in git(proj, "branch", "--list")


def test_D0074_AC_09_skill_worktreeはno_fetchを通す(proj: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """D0074-AC-09: pipe-in skill worktree の new・sync・clean が --no-fetch を通す（取れない条件でも、手元の main で動く）。"""
    break_origin(proj, tmp_path)
    monkeypatch.chdir(proj)
    assert cli.main(["skill", "worktree", "new", "n", "--no-fetch"]) == 0
    wt = proj / ".claude" / "worktrees" / "n"
    monkeypatch.chdir(wt)
    assert cli.main(["skill", "worktree", "sync", "--no-fetch"]) == 0
    monkeypatch.chdir(proj)
    assert cli.main(["skill", "worktree", "clean", "--no-fetch"]) == 0


@pytest.mark.parametrize("action", ["new", "sync", "clean"])
def test_D0074_AC_09_skill_worktreeはprojectを今までどおり断る_守る(
    proj: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    """D0074-AC-09: --project は今までどおり断る（短くした形・= の形も）。何も作らない。（今のまま通る。守る）"""
    monkeypatch.chdir(proj)
    extra = ["x"] if action == "new" else []
    for flag in (["--project", ".."], ["--proj=.."]):
        with pytest.raises(SystemExit, match="pipe-in skill"):
            cli.main(["skill", "worktree", action, *extra, *flag])
    assert not (proj / ".claude" / "worktrees").exists()


# ---- D0074-AC-10：night ---------------------------------------------------------------------------------------------------------


def test_D0074_AC_10_kind_nightはnight名の枝をoriginのmainから切る(proj: Path, other: Path) -> None:
    """D0074-AC-10: new X --kind night は night/X の枝を origin の main から切る（手元の main が古くても）。"""
    tip = advance_origin_main(other)
    path = new(proj, "2026-11-04", kind="night")
    assert git(path, "branch", "--show-current").strip() == "night/2026-11-04"
    assert head(path) == tip
    assert path == proj / ".claude" / "worktrees" / "2026-11-04"


def test_D0074_AC_10_kindの一覧に無い値は断る_守る(proj: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D0074-AC-10: --kind の一覧（feat・fix・docs・night）にない値は断る（今までどおり）。（今のまま通る。守る）"""
    with pytest.raises(WorktreeError, match="kind"):
        new(proj, "x", kind="hack")
    with pytest.raises(SystemExit):
        cli.main(["worktree", "new", "x", "--kind", "hack", "--project", str(proj)])
    capsys.readouterr()
    assert not (proj / ".claude" / "worktrees" / "x").exists()


def test_D0074_AC_10_同名のnight枝がoriginにあれば断る(proj: Path, other: Path) -> None:
    """D0074-AC-10（設計で足した確かめ）: --kind night で、origin に同名の night/X がもうあれば断る（同じ日の 2 回目は -2 を付ける）。worktree は作らない。"""
    push_night(other, "night/2026-11-04")
    with pytest.raises(WorktreeError, match="origin"):
        new(proj, "2026-11-04", kind="night")
    assert not (proj / ".claude" / "worktrees" / "2026-11-04").exists()
    path = new(proj, "2026-11-04-2", kind="night")  # -2 を付ければ切れる
    assert git(path, "branch", "--show-current").strip() == "night/2026-11-04-2"


# ---- D0074-AC-11：互換 ------------------------------------------------------------------------------------------------------------


def test_D0074_AC_11_base_mainの明示はbaseを省くのと同じ(proj: Path, other: Path) -> None:
    """D0074-AC-11: --base main を明示した古い呼び方は、--base を省いたのと同じに動く（origin の main から取る）。"""
    tip = advance_origin_main(other)
    explicit = new(proj, "a", base="main")
    omitted = new(proj, "b")
    assert head(explicit) == tip == head(omitted)


def _bases(proj: Path) -> list[str]:
    return ["HEAD", "HEAD~0", head(proj)[:7], head(proj)]


@pytest.mark.parametrize("which", [0, 1, 2, 3], ids=["HEAD", "HEAD~0", "略号", "全体"])
def test_D0074_AC_11_base_HEADなど枝名でない形は取らずそのまま使う_守る(proj: Path, tmp_path: Path, which: int) -> None:
    """D0074-AC-11（設計 Q8-2）: --base が枝の名前に見えない形（HEAD・HEAD~0・コミットの略号・全体）は、取らずにそのまま使う（人が指した形だから）。
    origin が取れない形でも失敗しない。（今のまま通る。守る）"""
    base = _bases(proj)[which]
    expected = head(proj)
    break_origin(proj, tmp_path)
    path = new(proj, "x", base=base)
    assert head(path) == expected
