"""D0074：pipe-in decision-number は、決定の記録の次の番号（D0073 の形）を 1 行で出す。

origin の main と、--branch で渡したまとめの枝（night/ で始まる枝だけ）の docs/decisions/D<4けた>-*.md の最大の番号の、大きいほうの次。
手元の作業フォルダの docs/decisions/ も見て、さらに大きければそれを使う。番号は出すだけで、ファイルを作らず、予約しない。

本物の git を一時フォルダで動かす（origin は一時の bare リポジトリ）。SDK も GitHub も呼ばず、ネットワークにも出ない。リポジトリの実物には書かない。
決定の記録のファイルは、中身の無い D0001-x.md のような名前だけを git add する。

- 新しいモジュール pipe_in/dev/decision_number.py がまだ無いときは、`need_module` が「まだ無い」で、そのテストだけを落とす
  （無いまま cli が引数を断って終わる形を、断ったテストの合格と取り違えないため）。
- 失敗（番号を出さず、理由を出して終了コード 0 でない）は、cli.main が SystemExit で止まる形で見る。
"""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest

from pipe_in import cli
from pipe_in.dev import skill_cmd


def need_module() -> None:
    """pipe_in/dev/decision_number.py が無ければ「まだ無い」で落とす。"""
    try:
        importlib.import_module("pipe_in.dev.decision_number")
    except ModuleNotFoundError as e:
        if e.name == "pipe_in.dev.decision_number":
            pytest.fail("pipe_in/dev/decision_number.py がまだ無い（新しい部品。メインが作る）", pytrace=False)
        raise


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def head(path: Path, ref: str = "HEAD") -> str:
    return git(path, "rev-parse", ref).strip()


def configure(path: Path) -> None:
    git(path, "config", "user.name", "test")
    git(path, "config", "user.email", "test@example.com")


def add_records(repo: Path, names: list[str], message: str = "records") -> None:
    """docs/decisions/ に、中身の無いファイルを名前だけ作って commit する。"""
    folder = repo / "docs" / "decisions"
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_text("", encoding="utf-8")
    git(repo, "add", "docs")
    git(repo, "commit", "-q", "-m", message)


def numbers(first: int, last: int) -> list[str]:
    return [f"D{n:04d}-x.md" for n in range(first, last + 1)]


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
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
    """手元。origin の main に、D0001〜D0060 の記録を push してある。"""
    root = tmp_path / "proj"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    configure(root)
    git(root, "remote", "add", "origin", str(origin))
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "init")
    add_records(root, numbers(1, 60))
    git(root, "push", "-q", "origin", "main")
    return root


@pytest.fixture
def other(tmp_path: Path, origin: Path, proj: Path) -> Path:
    root = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(origin), str(root))
    configure(root)
    return root


def push_main(other: Path, names: list[str]) -> None:
    add_records(other, names)
    git(other, "push", "-q", "origin", "HEAD:main")


def push_night(other: Path, branch: str, names: list[str]) -> None:
    git(other, "checkout", "-q", "-b", branch)
    add_records(other, names, "night")
    git(other, "push", "-q", "origin", branch)
    git(other, "checkout", "-q", "main")


def number_of(proj: Path, capsys: pytest.CaptureFixture[str], *args: str) -> str:
    """decision-number を流して、終了コード 0 と、出力が番号の 1 行だけであることを見て、その番号を返す。"""
    need_module()
    assert cli.main(["decision-number", "--project", str(proj), *args]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and out.strip() == out.rstrip("\n"), f"出力が番号の 1 行だけでない：{out!r}"
    return out.strip()


def failure_of(proj: Path, capsys: pytest.CaptureFixture[str], *args: str) -> str:
    """decision-number が、番号を出さず、理由を添えて終了コード 0 でなく止まることを見て、その文を返す。"""
    need_module()
    with pytest.raises(SystemExit) as e:
        cli.main(["decision-number", "--project", str(proj), *args])
    out = capsys.readouterr().out
    assert out.strip() == "", f"番号（か、ほかの文）を出している：{out!r}"
    code = e.value.code
    assert isinstance(code, str) and code.strip() or (isinstance(code, int) and code != 0), f"終了コードが失敗でない：{code!r}"
    # 一時フォルダの名前にテストの名前（取れない…・origin…）が入るので、パスは外してから文を見る
    return str(code).replace(str(proj.parent), "<tmp>")


# ---- D0074-AC-12：origin の main の最大の次 ------------------------------------------------------------------------------------------


def test_D0074_AC_12_originのmainが進んでいれば手元が古くてもD0073を出す(proj: Path, other: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D0074-AC-12: origin の main に D0001〜D0072 の記録があり、手元の main には D0060 までしか無いとき、decision-number は D0073 を出す。"""
    push_main(other, numbers(61, 72))
    assert not (proj / "docs" / "decisions" / "D0072-x.md").exists()
    assert number_of(proj, capsys) == "D0073"


def test_D0074_AC_12_手元の作業フォルダの方が大きければそれを使う(proj: Path, other: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D0074-AC-12（FR-10 の後半）: 手元の作業フォルダの docs/decisions/ に、origin の main より大きい番号（まだ commit していない D0090）があれば、その次を出す。"""
    push_main(other, numbers(61, 72))
    (proj / "docs" / "decisions" / "D0090-mine.md").write_text("", encoding="utf-8")
    assert number_of(proj, capsys) == "D0091"


# ---- D0074-AC-13：まとめの枝 ----------------------------------------------------------------------------------------------------------


def test_D0074_AC_13_branchのまとめの枝にだけある番号の次を出す(proj: Path, other: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D0074-AC-13: --branch night/<名前> を付け、まとめの枝にだけ D0075 の記録があるとき、D0076 を出す（origin の main は D0072 まで。両方を見る）。
    --branch を付けなければ、まとめの枝は見ず D0073 を出す。"""
    push_main(other, numbers(61, 72))
    push_night(other, "night/2026-11-04", ["D0075-night.md"])
    assert number_of(proj, capsys, "--branch", "night/2026-11-04") == "D0076"
    assert number_of(proj, capsys) == "D0073"


def test_D0074_AC_13_まとめの枝がoriginに無ければ失敗で止まる(proj: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D0074-AC-13: --branch に渡したまとめの枝が origin に無ければ、番号を出さず失敗で止まる。"""
    failure_of(proj, capsys, "--branch", "night/2026-11-04")


# ---- D0074-AC-14：--branch は night/ の形だけ -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "branch",
    ["main", "feat/x", "--upload-pack=touch {marker}", "night", "night/", "night/../x", "-x", ""],
    ids=["main", "feat", "旗の形", "night だけ", "night/ だけ", "night/..", "-x", "空"],
)
def test_D0074_AC_14_branchがnight以外や旗の形なら断る(
    proj: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], branch: str
) -> None:
    """D0074-AC-14: --branch に night/ で始まらない枝（main・feat/x・--upload-pack=… のような旗の形・night・night/・night/../x）を渡すと、断る。
    番号を出さず、取りに行かず（旗の中のコマンドが動かない。一時のフォルダにファイルができない）、断る文に night/ が入る。"""
    marker = tmp_path / "marker"
    message = failure_of(proj, capsys, f"--branch={branch.format(marker=marker)}")
    assert "night/" in message, f"断る文に night/ の形の話が無い：{message}"
    assert not marker.exists()


# ---- D0074-AC-15：取れないとき・--no-fetch ------------------------------------------------------------------------------------------------


def test_D0074_AC_15_remoteが無いとき番号を出さず理由とno_fetchを出して止まる(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D0074-AC-15: origin の remote が無いとき、番号を出さず、理由（origin）と --no-fetch が入った文で、失敗の終了コードで止まる
    （古い手元の main から黙って番号を出さない）。"""
    root = tmp_path / "local-only"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    configure(root)
    add_records(root, numbers(1, 5))
    message = failure_of(root, capsys)
    assert "origin" in message and "--no-fetch" in message, message


def test_D0074_AC_15_取れないとき番号を出さず理由とno_fetchを出して止まる(proj: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D0074-AC-15: remote はあるが取れない（origin のパスが無い）とき、番号を出さず、文に理由と --no-fetch が入り、失敗の終了コードで止まる。"""
    git(proj, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    message = failure_of(proj, capsys)
    assert "取れ" in message and "--no-fetch" in message, message


def test_D0074_AC_15_no_fetchなら取れているorigin_mainの版から出す(
    proj: Path, other: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """D0074-AC-15: --no-fetch なら、取らずに、手元に取れている origin/main の版から出す。一度取ってから origin を壊す（手元の main は D0060 のまま、
    取れている origin/main は D0072）。手元の main の版（D0061）からは出さない。"""
    push_main(other, numbers(61, 72))
    git(proj, "fetch", "-q", "origin")
    git(proj, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    assert number_of(proj, capsys, "--no-fetch") == "D0073"


def test_D0074_AC_15_no_fetchでもorigin_mainが取れていなければ止まる(tmp_path: Path, origin: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D0074-AC-15: --no-fetch でも、手元に origin/main が取れていなければ、「手元に origin/main が取れていません」で止まる（手元の main から黙って出さない）。"""
    root = tmp_path / "never-fetched"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    configure(root)
    git(root, "remote", "add", "origin", str(origin))
    add_records(root, numbers(1, 5))
    message = failure_of(root, capsys, "--no-fetch")
    assert "origin/main" in message, message


# ---- D0074-AC-16：何も変えない ----------------------------------------------------------------------------------------------------------


def test_D0074_AC_16_流す前後で作業フォルダ_手元の枝_HEAD_docsが変わらない(
    proj: Path, other: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """D0074-AC-16: decision-number はファイルを作らず・書き換えず、リポジトリの状態を変えない。流す前後で git status・手元の枝の一覧・HEAD・docs/ の一覧が同じ
    （未コミットの変更と、手元に無い origin の新しい記録がある状態で流す。.git の追跡の枝は fetch そのもので進んでよい）。"""
    push_main(other, numbers(61, 72))
    (proj / "docs" / "decisions" / "D0090-mine.md").write_text("", encoding="utf-8")
    (proj / "a.txt").write_text("changed\n", encoding="utf-8")

    def state() -> tuple[str, str, str, list[str], dict[str, str]]:
        docs = sorted(p.relative_to(proj).as_posix() for p in (proj / "docs").rglob("*"))
        contents = {p.name: p.read_text(encoding="utf-8") for p in proj.glob("*.txt")}
        return (git(proj, "status", "--porcelain"), git(proj, "branch", "--list"), head(proj), docs, contents)

    before = state()
    assert number_of(proj, capsys) == "D0091"
    assert state() == before


# ---- D0074-AC-17：数える名前 --------------------------------------------------------------------------------------------------------------


def test_D0074_AC_17_Dで始まらない名前や4けたでない名前は数えない(proj: Path, other: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D0074-AC-17: docs/decisions/ に D で始まらない名前（README.md）・4 けたでない名前（D12-x.md・D00100-x.md）・小文字（d0099-x.md）・- の無い名前（D0003.md）が
    あっても、数えずに最大（D0070）を出す。"""
    push_main(other, ["README.md", "D12-x.md", "D00100-x.md", "d0099-x.md", "D0003.md", "D0070-real.md"])
    assert number_of(proj, capsys) == "D0071"


def test_D0074_AC_17_決定の記録が1つも無ければD0001(tmp_path: Path, origin: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D0074-AC-17: 決定の記録が 1 つも無い（origin の main に docs/decisions/ そのものが無い）ときは D0001 を出す。"""
    root = tmp_path / "fresh"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    configure(root)
    git(root, "remote", "add", "origin", str(origin))
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "init")
    git(root, "push", "-q", "origin", "main")
    assert number_of(root, capsys) == "D0001"


# ---- D0074-AC-18：skill の入口 --------------------------------------------------------------------------------------------------------------


def test_D0074_AC_18_skill_decision_numberは元の形と同じに働きprojectを断る(
    proj: Path, other: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """D0074-AC-18: pipe-in skill decision-number が元の形と同じに働く（GUARDED に足してあり、今のフォルダの番号を出す）。--project は（短くした形・= の形も）断る。
    --branch の値が night/ の形でなければ、skill の入口でも断る。"""
    assert "decision-number" in skill_cmd.GUARDED, f"GUARDED に decision-number が無い：{list(skill_cmd.GUARDED)}"
    need_module()
    push_main(other, numbers(61, 72))
    push_night(other, "night/2026-11-04", ["D0075-night.md"])
    monkeypatch.chdir(proj)
    for extra, expected in (([], "D0073"), (["--branch", "night/2026-11-04"], "D0076")):
        assert cli.main(["decision-number", *extra]) == 0
        original = capsys.readouterr().out
        assert cli.main(["skill", "decision-number", *extra]) == 0
        assert capsys.readouterr().out == original == expected + "\n"
    for flag in (["--project", ".."], ["--proj=.."]):
        with pytest.raises(SystemExit, match="--project"):
            cli.main(["skill", "decision-number", *flag])
    with pytest.raises(SystemExit):
        cli.main(["skill", "decision-number", "--branch=main"])
    capsys.readouterr()
