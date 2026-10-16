"""ジェネレーター（generator/ = devpipe_generator）：環境の検出・ひな形の穴埋め・パイプのフォルダの生成と検査。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# 新しい部品はテストの中で読み込む（1件ずつ、何で落ちたかが見えるように）
def detect_mod():
    from devpipe_generator import detect

    return detect


def gen_cli():
    from devpipe_generator import cli

    return cli


def definition():
    from devpipe.pipe import definition

    return definition


TEMPLATES = ["dev", "diagrams", "spec-qa"]


def python_project(tmp_path: Path) -> Path:
    project = tmp_path / "shop"
    (project / "src").mkdir(parents=True)
    (project / "docs").mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "shop"\n[project.optional-dependencies]\ndev = ["pytest>=8"]\n', encoding="utf-8"
    )
    return project


def gen(tmp_path: Path, *args: str) -> int:
    return gen_cli().main([*args, "--pipes-dir", str(tmp_path / "pipes")])


# ---- AC-10: 環境の検出 ------------------------------------------------------------


def test_detect_python_pytest(tmp_path):
    env = detect_mod().detect(python_project(tmp_path))
    assert env.test_command == "pytest -q"
    assert "src" in env.source_dirs
    assert "docs" in env.docs_dirs


def test_detect_npm_test(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
    assert detect_mod().detect(tmp_path).test_command == "npm test"


def test_detect_ignores_npm_placeholder(tmp_path):
    placeholder = 'echo "Error: no test specified" && exit 1'
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": placeholder}}), encoding="utf-8")
    env = detect_mod().detect(tmp_path)
    assert env.test_command is None
    assert env.source_dirs == ["."]


# ---- AC-11〜AC-13: 生成・一覧・ひな形 -------------------------------------------------


def test_new_makes_pipe_folder(tmp_path):
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project)) == 0
    d = tmp_path / "pipes/devpipe-pics"
    assert (d / "pipe.toml").is_file() and (d / "README.md").is_file()
    assert sorted(p.name for p in (d / "prompts").glob("*.md"))  # 段の指示文が prompts/ に入る
    pipe = definition().load_pipe(d)
    assert pipe.name == "pics"
    assert definition().check_pipe(pipe, project) == []
    texts = [p.read_text(encoding="utf-8") for p in d.rglob("*") if p.is_file()]
    assert not any("{{" in t for t in texts)  # 穴は全部埋まっている
    assert any("`src/`" in t for t in texts)  # 見つけたソースの場所が入る
    readme = (d / "README.md").read_text(encoding="utf-8")
    assert "devpipe --pipe pics" in readme


def test_new_does_not_write_local_paths(tmp_path):
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project)) == 0
    for p in (tmp_path / "pipes/devpipe-pics").rglob("*"):
        if p.is_file():
            text = p.read_text(encoding="utf-8")
            assert str(project) not in text and project.as_posix() not in text, p


def test_new_does_not_overwrite(tmp_path):
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project)) == 0
    toml = tmp_path / "pipes/devpipe-pics/pipe.toml"
    toml.write_text(toml.read_text(encoding="utf-8") + "\n# 手で直した\n", encoding="utf-8")
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project)) != 0
    assert "# 手で直した" in toml.read_text(encoding="utf-8")


def test_new_force_overwrites(tmp_path):
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project)) == 0
    d = tmp_path / "pipes/devpipe-pics"
    (d / "pipe.toml").write_text("# 壊れた\n", encoding="utf-8")
    (d / "prompts/old.md").write_text("古い指示", encoding="utf-8")
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project), "--force") == 0
    assert definition().check_pipe(definition().load_pipe(d), project) == []
    assert not (d / "prompts/old.md").exists()  # ひな形にないファイルは残さない


def test_new_fills_detected_test_command(tmp_path):
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", "mydev", "--from", "dev", "--project", str(project)) == 0
    pipe = definition().load_pipe(tmp_path / "pipes/devpipe-mydev")
    assert pipe.kind == "dev" and pipe.test_command == "pytest -q"


def test_new_without_test_command_leaves_it_out(tmp_path):
    (tmp_path / "bare").mkdir()
    assert gen(tmp_path, "new", "mydev", "--from", "dev", "--project", str(tmp_path / "bare")) == 0
    pipe = definition().load_pipe(tmp_path / "pipes/devpipe-mydev")
    assert pipe.test_command is None
    assert definition().check_pipe(pipe, tmp_path / "bare") == []


@pytest.mark.parametrize("bad", ["Bad Name", "logs", "../x", ""])
def test_new_rejects_bad_names(tmp_path, bad):
    assert gen(tmp_path, "new", bad, "--from", "diagrams", "--project", str(tmp_path)) != 0
    assert not (tmp_path / "pipes").exists() or not any((tmp_path / "pipes").iterdir())


def test_new_rejects_unknown_template(tmp_path):
    assert gen(tmp_path, "new", "pics", "--from", "nothing", "--project", str(tmp_path)) != 0


def test_list_shows_templates_and_pipes(tmp_path, capsys):
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project)) == 0
    capsys.readouterr()
    assert gen(tmp_path, "list") == 0
    out = capsys.readouterr().out
    for name in TEMPLATES:
        assert name in out
    assert "pics" in out


@pytest.mark.parametrize("name", TEMPLATES)
def test_templates_make_valid_pipes(tmp_path, name):
    tdir = gen_cli().templates_dir() / name
    assert (tdir / "pipe.toml").is_file() and (tdir / "README.md").is_file()
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", f"my-{name}", "--from", name, "--project", str(project)) == 0
    assert gen(tmp_path, "check", f"my-{name}", "--project", str(project)) == 0


def test_check_reports_errors(tmp_path, capsys):
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project)) == 0
    toml = tmp_path / "pipes/devpipe-pics/pipe.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace('name = "draw"', 'name = "survey"'), encoding="utf-8")
    capsys.readouterr()
    assert gen(tmp_path, "check", "pics", "--project", str(project)) != 0
    assert "重複" in capsys.readouterr().out
    assert gen(tmp_path, "check", "nothing", "--project", str(project)) != 0


def test_render_template_comments_out_missing_values():
    from devpipe_generator.render import render_template

    text = 'test_command = "{{test_command}}"\nprompt = "{{source_dirs}} を読む"\n'
    out = render_template(text, {"test_command": None, "source_dirs": '`src/` と "lib"'})
    assert out.splitlines()[0].startswith("#")
    assert 'prompt = "`src/` と \\"lib\\" を読む"' in out  # TOML の文字列として壊れない
