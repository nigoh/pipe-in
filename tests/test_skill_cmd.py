"""pipe-in skill：/pipe-in のスキルが打つ記録と worktree のコマンドを、確認なしで通してよい形に絞った入口（D0049）。

`python -m pipe_in skill record …`・`python -m pipe_in skill worktree …` は、今のフォルダだけを相手にし、
任意のファイルを読む旗（--input・--feedback-file）と別の場所を指す旗（--project・--config）を断る。
だから .claude/settings.json の allow に `Bash(python -m pipe_in skill:*)` を入れてよい。SDK は呼ばない。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from pipe_in import cli

ROOT = Path(__file__).resolve().parents[1]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    monkeypatch.chdir(root)
    return root


def test_skill_record_writes_records_in_current_folder(project: Path) -> None:
    """D0049-AC-06: skill record は record と同じに働き、今のフォルダの docs/pipeline/ に書く。"""
    assert cli.main(["skill", "record", "start", "--text", "足したい機能"]) == 0
    assert cli.main(["skill", "record", "begin", "requirements", "--agent", "pipe-in-analyst"]) == 0
    state = json.loads((project / "docs" / "pipeline" / "state.json").read_text(encoding="utf-8"))
    assert state["driver"] == "pipe-dev"


@pytest.mark.parametrize(
    "argv",
    [
        ["start", "--input", "memo.md"],
        ["start", "--inp", "memo.md"],
        ["start", "--text", "x", "--project", ".."],
        ["start", "--text", "x", "--proj=.."],
        ["start", "--text", "x", "--config", "other.toml"],
        ["review", "requirements", "revise", "--feedback-file", "f.txt"],
        ["review", "requirements", "revise", "--feedback-f", "f.txt"],
    ],
)
def test_skill_record_refuses_flags_that_read_files_or_point_elsewhere(project: Path, argv: list[str]) -> None:
    """D0049-AC-07: --input・--feedback-file・--project・--config は（短くした形・= の形も）断り、何も書かない。"""
    with pytest.raises(SystemExit, match="pipe-in skill"):
        cli.main(["skill", "record", *argv])
    assert not (project / "docs").exists()


def test_skill_worktree_refuses_project_and_runs_here(project: Path) -> None:
    """D0049-AC-08: skill worktree は --project を断る。付けなければ今のフォルダで働く。"""
    git(project, "init", "-q", "-b", "main")
    git(project, "config", "user.name", "test")
    git(project, "config", "user.email", "test@example.com")
    (project / "a.txt").write_text("a\n", encoding="utf-8")
    git(project, "add", ".")
    git(project, "commit", "-q", "-m", "init")
    for flag in (["--project", ".."], ["--proj=.."]):
        with pytest.raises(SystemExit, match="pipe-in skill"):
            cli.main(["skill", "worktree", "new", "x", *flag])
    assert cli.main(["skill", "worktree", "new", "x"]) == 0
    assert (project / ".claude" / "worktrees" / "x").is_dir()


def test_skill_refuses_other_commands(project: Path) -> None:
    """D0049-AC-09: skill の後ろは record と worktree だけ（live などは断る）。"""
    for argv in (["skill"], ["skill", "live", "page"], ["skill", "run"]):
        with pytest.raises(SystemExit, match="pipe-in skill"):
            cli.main(argv)


def test_settings_allow_skill_entry_and_two_exact_commands() -> None:
    """D0049-AC-10: settings.json の allow に Bash(python -m pipe_in skill:*)・Bash(python --version)・Bash(npm --prefix vscode ci) がある。
    record・worktree そのものの規則は足さない（--input などで任意のファイルを読めるため）。"""
    allow = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["allow"]
    for rule in ("Bash(python -m pipe_in skill:*)", "Bash(python --version)", "Bash(npm --prefix vscode ci)"):
        assert rule in allow
    assert not [r for r in allow if r.startswith(("Bash(python -m pipe_in record", "Bash(python -m pipe_in worktree"))]


def test_skill_md_tells_to_run_skill_entry() -> None:
    """D0049-AC-11: スキルは、記録と worktree のコマンドを skill の入口で流すよう書き、段の区切りの載せ直しに worktree sync を使う。"""
    skill = (ROOT / ".claude" / "skills" / "pipe-in" / "SKILL.md").read_text(encoding="utf-8")
    record = (ROOT / ".claude" / "skills" / "pipe-in" / "record.md").read_text(encoding="utf-8")
    assert "python -m pipe_in skill record" in record
    assert "python -m pipe_in skill worktree new <名前>" in skill
    assert "python -m pipe_in skill worktree clean" in skill
    assert "python -m pipe_in skill worktree sync" in skill
