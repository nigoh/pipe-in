"""名前替え（devpipe → pipe-in）：パッケージ・コマンド・古いコマンドの別名・古い名前の残り。

古い名前が出てよいのは、下の ALLOWED に理由を添えて書いたファイルだけ。
開発フローのクラス名 DevPipeline は製品名と関係がないので、検査の対象にしない（devpipe(?!line) で探す）。
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OLD_NAME = re.compile(r"devpipe(?!line)", re.IGNORECASE)


def pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


# ---- D0006-AC-01: パッケージの名前・版・コマンド -----------------------------------------


def test_pyproject_names_version_and_scripts():
    """D0006-AC-01: pyproject の名前が pipe-in・版が 0.3.0 で、pipe-in と pipe-in-gen のコマンドがあり、パッケージの名前も新しい。"""
    data = pyproject()
    project = data["project"]
    assert project["name"] == "pipe-in"
    assert project["version"] == "0.3.0"
    scripts = project["scripts"]
    assert scripts["pipe-in"] == "pipe_in.cli:main"
    assert scripts["pipe-in-gen"] == "pipe_in_generator.cli:main"
    tool = data["tool"]["setuptools"]
    assert tool["packages"] and all(p == "pipe_in" or p.startswith(("pipe_in.", "pipe_in_generator")) for p in tool["packages"])
    assert tool["package-dir"] == {"pipe_in_generator": "generator"}
    keys = list(data["tool"]["setuptools"]["package-data"])
    assert keys and all(k == "pipe_in" or k.startswith(("pipe_in.", "pipe_in_generator")) for k in keys)


# ---- D0006-AC-02: 古いフォルダが無く、コマンドの名前が新しい --------------------------------


def test_old_package_folder_is_gone():
    """D0006-AC-02: 古いパッケージのフォルダが無く、pipe_in/__main__.py がある。"""
    assert not (ROOT / "devpipe").exists()
    assert (ROOT / "pipe_in" / "__main__.py").is_file()


def usage_line(main, argv: list[str], capsys) -> str:
    with pytest.raises(SystemExit) as e:
        main(argv)
    assert e.value.code == 0
    out = capsys.readouterr().out
    return next(line for line in out.splitlines() if line.startswith("usage:"))


def test_help_shows_new_command_names(capsys):
    """D0006-AC-02: ヘルプの usage の行が pipe-in・pipe-in-gen・pipe-in record になる。"""
    from pipe_in import cli
    from pipe_in_generator import cli as gen_cli

    assert usage_line(cli.main, ["--help"], capsys).startswith("usage: pipe-in ")
    assert usage_line(gen_cli.main, ["--help"], capsys).startswith("usage: pipe-in-gen ")
    assert usage_line(cli.main, ["record", "--help"], capsys).startswith("usage: pipe-in record ")


def test_python_m_pipe_in_help():
    """D0006-AC-02: python -m pipe_in --help が終了コード 0 で、出力に古い名前が無い。"""
    # 子のプロセスの出力を UTF-8 にそろえる（Windows の既定の文字コードに左右されないように）
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    out = subprocess.run(
        [sys.executable, "-m", "pipe_in", "--help"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env, timeout=60
    )
    assert out.returncode == 0, out.stderr
    assert "usage: pipe-in " in out.stdout
    assert not OLD_NAME.search(out.stdout + out.stderr), out.stdout


# ---- D0006-AC-04: 古いコマンドの別名（0.3 の間だけ） ----------------------------------------


def test_pyproject_keeps_old_aliases():
    """D0006-AC-04: pyproject に古いコマンド devpipe・devpipe-gen の別名があり、別名の入口を指す。"""
    scripts = pyproject()["project"]["scripts"]
    assert scripts["devpipe"] == "pipe_in.legacy:devpipe_main"
    assert scripts["devpipe-gen"] == "pipe_in_generator.legacy:devpipe_gen_main"


def outcome(main, argv: list[str], capsys) -> tuple[object, str, str]:
    """終わり方（戻り値か SystemExit の code）と、標準出力・標準エラー。"""
    try:
        result: object = ("return", main(argv))
    except SystemExit as e:
        result = ("exit", e.code)
    captured = capsys.readouterr()
    return result, captured.out, captured.err


def assert_one_notice(err: str, notice: str) -> None:
    assert notice.strip(), "案内の文が空"
    assert "pipe-in" in notice
    assert err.splitlines() == [notice.strip()]


@pytest.mark.parametrize("argv", [["--help"], ["--pause", "--yes"]], ids=["help", "pause-yes"])
def test_devpipe_alias_runs_same_and_warns(argv, capsys):
    """D0006-AC-04: 別名 devpipe は新しい入口と同じ終わり方・同じ標準出力で、標準エラーに案内をちょうど1行出す。"""
    from pipe_in import cli, legacy

    new = outcome(cli.main, list(argv), capsys)
    old = outcome(legacy.devpipe_main, list(argv), capsys)
    assert old[0] == new[0]
    assert old[1] == new[1]
    assert new[2] == ""
    assert_one_notice(old[2], legacy.NOTICE)


def test_devpipe_gen_alias_runs_same_and_warns(tmp_path, monkeypatch, capsys):
    """D0006-AC-04: 別名 devpipe-gen は新しい入口と同じ終わり方・同じ標準出力で、標準エラーに案内をちょうど1行出す。"""
    from pipe_in_generator import cli, legacy

    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    monkeypatch.delenv("DEVPIPE_PIPES_DIR", raising=False)
    argv = ["list", "--project", str(tmp_path), "--pipes-dir", str(tmp_path / "pipes")]
    new = outcome(cli.main, list(argv), capsys)
    old = outcome(legacy.devpipe_gen_main, list(argv), capsys)
    assert new[0] == ("return", 0)
    assert old[0] == new[0]
    assert old[1] == new[1]
    assert_one_notice(old[2], legacy.NOTICE)


GUARD_INPUTS = {
    # pipe-builder がパイプのフォルダの外に書く → 止める
    "deny": {"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {"file_path": "src/a.py"}, "agent_type": "devpipe:pipe-builder"},
    # ほかのエージェント → 何もしない
    "pass": {"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {"file_path": "src/a.py"}, "agent_type": "Explore"},
}


def hook_stdout(main, payload: dict, tmp_path: Path, monkeypatch) -> tuple[int, str]:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({**payload, "cwd": str(tmp_path)})))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    code = main(["guard-hook"])
    return code, out.getvalue()


@pytest.mark.parametrize("case", list(GUARD_INPUTS))
def test_devpipe_gen_guard_hook_stdout_is_identical(tmp_path, monkeypatch, case):
    """D0006-AC-04: devpipe-gen guard-hook の標準出力は pipe-in-gen guard-hook とバイト単位で同じ（止めるときは deny の JSON だけ、止めないときは空）。"""
    from pipe_in_generator import cli, legacy

    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    monkeypatch.delenv("DEVPIPE_PIPES_DIR", raising=False)
    new = hook_stdout(cli.main, GUARD_INPUTS[case], tmp_path, monkeypatch)
    old = hook_stdout(legacy.devpipe_gen_main, GUARD_INPUTS[case], tmp_path, monkeypatch)
    assert old == new
    if case == "deny":
        assert json.loads(old[1])["hookSpecificOutput"]["permissionDecision"] == "deny"
    else:
        assert old == (0, "")


# ---- D0006-AC-26: 古い名前は、決まったファイルにしか残っていない --------------------------------

# 古い名前（devpipe）が出てよいファイル → 理由。多くても少なくても失敗にする（一覧が古くならないように）
ALLOWED: dict[str, str] = {
    ".gitignore": "古い置き場所 /.devpipe/ を引き続き無視する",
    "pyproject.toml": "別名のコマンド devpipe・devpipe-gen（0.4 で消す）",
    "pipe_in/legacy.py": "別名 devpipe の入口",
    "generator/legacy.py": "別名 devpipe-gen の入口",
    "pipe_in/pipe/definition.py": "古い置き場所・フォルダ名・環境変数を読む",
    "generator/guard_hook.py": "古いフォルダ名・環境変数の下も守る",
    "vscode/src/app/names.ts": "古い設定・コマンド ID の読み替え",
    "vscode/src/app/pipeEditor.ts": "古い置き場所・フォルダ名を読む",
    "vscode/src/infra/fsPipes.ts": "古いフォルダ名を受け付ける",
    "README.md": "「devpipe から移る」の節（test_readme_old_name_only_in_migration_section で節の中だけに絞る）",
    "docs/decisions/D0001-plugin-pipe-build.md": "歴史。書き換えない",
    "docs/decisions/D0002-dev-rules.md": "歴史。書き換えない",
    "docs/decisions/D0003-rebase-on-main-change.md": "歴史。書き換えない",
    "docs/decisions/README.md": "D0001 の題（歴史）",
    "docs/decisions/D0006-rename-pipe-in.md": "この名前替えの記録",
    "docs/development/design.md": "「形を変えるとき（互換）」の古い名前の読み替えの行",
    "tests/conftest.py": "古い置き場所も見張る",
    "tests/test_rename.py": "この検査と別名のテスト",
    "tests/test_architecture.py": "古い名前を import していないことの検査",
    "tests/test_rules.py": "表のパスから古い置き場所を除く・見張りのテスト",
    "tests/test_pipe.py": "古い置き場所・フォルダ名・環境変数を読むことのテスト",
    "tests/test_generator.py": "古い置き場所・フォルダ名・環境変数を読むことのテスト",
    "tests/test_guard_hook.py": "古いフォルダ名・環境変数・古いプラグインのエージェントのテスト",
    "tests/test_plugin.py": "プラグインの文に古い名前が無いことのテスト",
    "vscode/src/app/names.test.ts": "古い設定・コマンド ID のテスト",
    "vscode/src/app/pipeEditor.test.ts": "古い置き場所・フォルダ名のテスト",
    "vscode/src/infra/fsPipes.test.ts": "古いフォルダ名を受け付けることのテスト",
    "vscode/src/manifest.test.ts": "宣言に古い名前が無いことのテスト",
    # 開発用の名前替え（後半）で直す。それまでの間だけ。後半でこの5行を消す
    ".claude/skills/pipe-in/SKILL.md": "開発用の名前替え（後半）まで",
    ".claude/agents/pipe-in-analyst.md": "開発用の名前替え（後半）まで",
    ".claude/agents/pipe-in-tester.md": "開発用の名前替え（後半）まで",
    ".claude/agents/pipe-in-coder.md": "開発用の名前替え（後半）まで",
    ".claude/agents/pipe-in-verifier.md": "開発用の名前替え（後半）まで",
}


def repo_files() -> list[Path]:
    """追跡しているファイルと、まだ追跡していないが無視もしていないファイル（コミット前の新しいファイルも見るため）。"""
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("git が無い・リポジトリではないため、ファイルの一覧を出せない")
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    names = sorted({p for p in out.decode("utf-8").split("\0") if p})
    return [ROOT / p for p in names if (ROOT / p).is_file()]


def text_of(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:4096]:
        return None  # 画像などの中身は見ない
    return data.decode("utf-8", errors="ignore")


def files_with_old_name() -> set[str]:
    found = set()
    for path in repo_files():
        text = text_of(path)
        if text is not None and OLD_NAME.search(text):
            found.add(path.relative_to(ROOT).as_posix())
    return found


@pytest.mark.parametrize(
    "text,found",
    [
        ("devpipe-gen list", True),
        ("DEVPIPE_PIPES_DIR", True),
        ("from devpipe import cli", True),
        ("nok.DevPipe-vscode", True),
        ("class DevPipeline:", False),
        ("from pipe_in.dev.pipeline import DevPipeline", False),
        ("pipe-in-gen list", False),
    ],
)
def test_old_name_pattern(text, found):
    """D0006-AC-26: 探し方そのものが古い名前を見つけ、開発フローのクラス名 DevPipeline は見逃す。"""
    assert bool(OLD_NAME.search(text)) is found


def test_old_name_only_in_allowed_files():
    """D0006-AC-26: 古い名前を含むファイルの集まりが、ALLOWED とちょうど一致する。"""
    found = files_with_old_name()
    unexpected = sorted(found - ALLOWED.keys())
    gone = sorted(ALLOWED.keys() - found)
    # 左：古い名前が残っているファイル（一覧に無い）。右：一覧にあるのに古い名前が出なくなったファイル（一覧から消す）
    assert {"unexpected": unexpected, "gone": gone} == {"unexpected": [], "gone": []}


MIGRATION = re.compile(r"^## devpipe から移る", re.MULTILINE)


def outside_migration_section(text: str) -> str:
    """README から「devpipe から移る」の節（見出しから次の ## の見出しの前まで）を除いた文。節が無ければ全体。"""
    m = MIGRATION.search(text)
    if not m:
        return text
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, re.MULTILINE)
    end = m.end() + (nxt.start() if nxt else len(rest))
    return text[: m.start()] + text[end:]


def test_migration_section_finder():
    """D0006-AC-26: 節の切り出し方そのものが、節の外の古い名前を見つけ、節の中は見逃す。"""
    inside = "# pipe-in\n\n## 使い方\n\npipe-in\n\n## devpipe から移る\n\npip uninstall devpipe\n\n## ライセンス\n\nMIT\n"
    assert not OLD_NAME.search(outside_migration_section(inside))
    outside = inside.replace("## 使い方\n\npipe-in", "## 使い方\n\ndevpipe-gen list")
    assert OLD_NAME.search(outside_migration_section(outside))
    assert OLD_NAME.search(outside_migration_section("devpipe だけ"))  # 節が無ければ全体を見る


def test_readme_old_name_only_in_migration_section():
    """D0006-AC-26: README には「devpipe から移る」の節があり、古い名前はその節の中にしか出ない。"""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert MIGRATION.search(text), "README に「## devpipe から移る」の節が無い"
    left = [line for line in outside_migration_section(text).splitlines() if OLD_NAME.search(line)]
    assert left == []
