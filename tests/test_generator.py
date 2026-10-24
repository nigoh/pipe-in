"""ジェネレーター（generator/ = pipe_in_generator）：環境の検出・ひな形の穴埋め・パイプのフォルダの生成と検査。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# 新しい部品はテストの中で読み込む（1件ずつ、何で落ちたかが見えるように）
def detect_mod():
    from pipe_in_generator import detect

    return detect


def gen_cli():
    from pipe_in_generator import cli

    return cli


def definition():
    from pipe_in.pipe import definition

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


@pytest.fixture(autouse=True)
def no_repo_pipes(tmp_path, monkeypatch):
    """どのテストも、リポジトリの本物の pipes/ には書かない（今までの場所を仮のフォルダに向ける）。

    手元に置き場所の環境変数があっても左右されないよう、新旧とも消してから始める。
    """
    import os

    from pipe_in.pipe import definition as pd

    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    monkeypatch.delenv("DEVPIPE_PIPES_DIR", raising=False)

    def fake_default() -> Path:
        env = pd.env_pipes_dir(os.environ)
        return Path(env) if env else tmp_path / "repo-pipes"

    monkeypatch.setattr(pd, "default_pipes_dir", fake_default)


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
    """D0006-AC-07: new は pipe-in-<名前>/ を作り、README の流し方は pipe-in のコマンド。"""
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project)) == 0
    d = tmp_path / "pipes/pipe-in-pics"
    assert (d / "pipe.toml").is_file() and (d / "README.md").is_file()
    assert sorted(p.name for p in (d / "prompts").glob("*.md"))  # 段の指示文が prompts/ に入る
    pipe = definition().load_pipe(d)
    assert pipe.name == "pics"
    assert definition().check_pipe(pipe, project) == []
    texts = [p.read_text(encoding="utf-8") for p in d.rglob("*") if p.is_file()]
    assert not any("{{" in t for t in texts)  # 穴は全部埋まっている
    assert any("`src/`" in t for t in texts)  # 見つけたソースの場所が入る
    readme = (d / "README.md").read_text(encoding="utf-8")
    assert "pipe-in --pipe pics" in readme
    assert "pipe-in-gen check" in readme
    assert not any("devpipe" in t.lower() for t in texts)


def test_new_does_not_write_local_paths(tmp_path):
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project)) == 0
    for p in (tmp_path / "pipes/pipe-in-pics").rglob("*"):
        if p.is_file():
            text = p.read_text(encoding="utf-8")
            assert str(project) not in text and project.as_posix() not in text, p


def test_new_does_not_overwrite(tmp_path):
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project)) == 0
    toml = tmp_path / "pipes/pipe-in-pics/pipe.toml"
    toml.write_text(toml.read_text(encoding="utf-8") + "\n# 手で直した\n", encoding="utf-8")
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project)) != 0
    assert "# 手で直した" in toml.read_text(encoding="utf-8")


def test_new_force_overwrites(tmp_path):
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project)) == 0
    d = tmp_path / "pipes/pipe-in-pics"
    (d / "pipe.toml").write_text("# 壊れた\n", encoding="utf-8")
    (d / "prompts/old.md").write_text("古い指示", encoding="utf-8")
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project), "--force") == 0
    assert definition().check_pipe(definition().load_pipe(d), project) == []
    assert not (d / "prompts/old.md").exists()  # ひな形にないファイルは残さない


def test_new_fills_detected_test_command(tmp_path):
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", "mydev", "--from", "dev", "--project", str(project)) == 0
    pipe = definition().load_pipe(tmp_path / "pipes/pipe-in-mydev")
    assert pipe.kind == "dev" and pipe.test_command == "pytest -q"


def test_new_without_test_command_leaves_it_out(tmp_path):
    (tmp_path / "bare").mkdir()
    assert gen(tmp_path, "new", "mydev", "--from", "dev", "--project", str(tmp_path / "bare")) == 0
    pipe = definition().load_pipe(tmp_path / "pipes/pipe-in-mydev")
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


def test_new_defaults_to_project_pipes(tmp_path):
    """D0001-AC-15・D0006-AC-07: 置き場所の指定がなければ、対象の .pipe-in/pipes/pipe-in-<名前>/ に作り、.devpipe は作らない。check もそこから探す。"""
    project = python_project(tmp_path)
    assert gen_cli().main(["new", "pics", "--from", "diagrams", "--project", str(project)]) == 0
    assert (project / ".pipe-in/pipes/pipe-in-pics/pipe.toml").is_file()
    assert not (project / ".devpipe").exists()
    assert gen_cli().main(["check", "pics", "--project", str(project)]) == 0


@pytest.mark.parametrize("env_name", ["PIPE_IN_PIPES_DIR", "DEVPIPE_PIPES_DIR"])
def test_new_respects_pipes_dir_and_env(tmp_path, monkeypatch, env_name):
    """D0001-AC-15・D0006-AC-07: --pipes-dir か PIPE_IN_PIPES_DIR（無ければ DEVPIPE_PIPES_DIR）があれば、そちらに作る。"""
    project = python_project(tmp_path)
    monkeypatch.setenv(env_name, str(tmp_path / "env"))
    assert gen_cli().main(["new", "a", "--from", "diagrams", "--project", str(project)]) == 0
    assert (tmp_path / "env/pipe-in-a/pipe.toml").is_file()
    assert gen(tmp_path, "new", "b", "--from", "diagrams", "--project", str(project)) == 0
    assert (tmp_path / "pipes/pipe-in-b/pipe.toml").is_file()
    assert not (project / ".pipe-in").exists()
    assert not (project / ".devpipe").exists()


def test_list_shows_project_and_shared_pipes(tmp_path, monkeypatch, capsys):
    """D0001-AC-16・D0006-AC-09: list --project は、対象の .pipe-in/pipes/ と今までの場所の両方を出す。"""
    project = python_project(tmp_path)
    monkeypatch.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "shared"))
    assert gen_cli().main(["new", "old", "--from", "diagrams", "--project", str(project)]) == 0
    monkeypatch.delenv("PIPE_IN_PIPES_DIR")
    assert gen_cli().main(["new", "mine", "--from", "diagrams", "--project", str(project)]) == 0
    monkeypatch.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "shared"))
    capsys.readouterr()
    assert gen_cli().main(["list", "--project", str(project)]) == 0
    out = capsys.readouterr().out
    assert "mine" in out and "old" in out
    assert ".pipe-in" in out
    assert "pipe-in-gen new" in out and "pipe-in --pipe" in out


def make_old_pipe(base: Path, folder: str, label: str = "古い置き場所のパイプ") -> Path:
    d = base / folder
    (d / "prompts").mkdir(parents=True)
    (d / "pipe.toml").write_text(
        f'[pipe]\nkind = "linear"\nlabel = "{label}"\n\n[[stages]]\nname = "a"\nlabel = "a"\noutput = "01_a.md"\naccess = "read"\nprompt = "x"\n',
        encoding="utf-8",
    )
    return d


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("force", [False, True], ids=["plain", "force"])
def test_new_refuses_name_in_old_place(tmp_path, capsys, force):
    """D0006-AC-08: 古い置き場所に同じ名前のパイプがあれば、new は場所を示して断り、何も書かない（--force でも）。"""
    project = python_project(tmp_path)
    old = make_old_pipe(project / ".devpipe" / "pipes", "devpipe-pics")
    before = snapshot(tmp_path)
    capsys.readouterr()
    argv = ["new", "pics", "--from", "diagrams", "--project", str(project), *(["--force"] if force else [])]
    assert gen_cli().main(argv) != 0
    out = capsys.readouterr().out
    assert str(old) in out
    assert snapshot(tmp_path) == before
    assert not (project / ".pipe-in").exists()


def test_new_refuses_old_folder_name_in_new_place(tmp_path, capsys):
    """D0006-AC-08: 作る置き場所に古いフォルダ名（devpipe-<名前>/）があっても断り、何も書かない。"""
    project = python_project(tmp_path)
    old = make_old_pipe(tmp_path / "pipes", "devpipe-pics")
    before = snapshot(tmp_path)
    capsys.readouterr()
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project), "--force") != 0
    assert str(old) in capsys.readouterr().out
    assert snapshot(tmp_path) == before


def test_list_marks_old_names(tmp_path, capsys):
    """D0006-AC-09: list は新旧の置き場所のパイプを両方出し、古いもの（.devpipe/pipes にある・devpipe- で始まる）に「古い名前」と添える。"""
    project = python_project(tmp_path)
    make_old_pipe(project / ".pipe-in" / "pipes", "pipe-in-fresh", "新しいパイプ")
    make_old_pipe(project / ".devpipe" / "pipes", "devpipe-aged", "古いパイプ")
    make_old_pipe(project / ".pipe-in" / "pipes", "devpipe-mixed", "古いフォルダ名")
    capsys.readouterr()
    assert gen_cli().main(["list", "--project", str(project)]) == 0
    lines = capsys.readouterr().out.splitlines()

    def line_of(label: str) -> str:
        found = [x for x in lines if label in x]
        assert len(found) == 1, (label, lines)
        return found[0]

    assert "古い名前" not in line_of("新しいパイプ")
    assert "古い名前" in line_of("古いパイプ")
    assert "古い名前" in line_of("古いフォルダ名")
    assert "aged" in line_of("古いパイプ") and "devpipe-aged" not in line_of("古いパイプ")  # 名前は頭を除いたもの
    assert any(str(project / ".devpipe" / "pipes") in x for x in lines)


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
    toml = tmp_path / "pipes/pipe-in-pics/pipe.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace('name = "draw"', 'name = "survey"'), encoding="utf-8")
    capsys.readouterr()
    assert gen(tmp_path, "check", "pics", "--project", str(project)) != 0
    assert "重複" in capsys.readouterr().out
    assert gen(tmp_path, "check", "nothing", "--project", str(project)) != 0


def test_render_template_comments_out_missing_values():
    from pipe_in_generator.render import render_template

    text = 'test_command = "{{test_command}}"\nprompt = "{{source_dirs}} を読む"\n'
    out = render_template(text, {"test_command": None, "source_dirs": '`src/` と "lib"'})
    assert out.splitlines()[0].startswith("#")
    assert 'prompt = "`src/` と \\"lib\\" を読む"' in out  # TOML の文字列として壊れない


# ---- FR-06 環境の検出を広げる ------------------------------------------------------


DETECT_CASES = {
    "maven": ({"pom.xml": "<project/>"}, "mvn -q test", "java"),
    "gradle-wrapper": ({"build.gradle": "", "gradlew": ""}, "./gradlew test", "java"),
    "gradle-kts": ({"build.gradle.kts": ""}, "gradle test", "java"),
    "rspec": ({"Gemfile": "source 'https://rubygems.org'", "spec/a_spec.rb": ""}, "bundle exec rspec", "ruby"),
    "rake": ({"Gemfile": ""}, "bundle exec rake test", "ruby"),
    "composer": ({"composer.json": json.dumps({"scripts": {"test": "phpunit"}})}, "composer test", "php"),
    "phpunit": ({"composer.json": "{}", "phpunit.xml": ""}, "vendor/bin/phpunit", "php"),
    "dotnet": ({"App.csproj": "<Project/>"}, "dotnet test", "dotnet"),
    "deno": ({"deno.json": "{}"}, "deno test", "deno"),
    "pnpm": ({"package.json": json.dumps({"scripts": {"test": "vitest"}}), "pnpm-lock.yaml": ""}, "pnpm test", "node"),
    "yarn": ({"package.json": json.dumps({"scripts": {"test": "jest"}}), "yarn.lock": ""}, "yarn test", "node"),
    "bun": ({"package.json": json.dumps({"scripts": {"test": "bun test"}}), "bun.lockb": ""}, "bun test", "node"),
    "uv": ({"pyproject.toml": '[project]\nname="x"\ndependencies=["pytest"]\n', "uv.lock": ""}, "uv run pytest -q", "python"),
    "poetry": ({"pyproject.toml": '[tool.poetry]\nname="x"\n[tool.poetry.group.dev.dependencies]\npytest="*"\n', "poetry.lock": ""}, "poetry run pytest -q", "python"),
    "make": ({"Makefile": "build:\n\tcc main.c\ntest:\n\t./run_tests\n"}, "make test", None),
}


@pytest.mark.parametrize("case", list(DETECT_CASES))
def test_detect_more_environments(tmp_path, case):
    files, command, language = DETECT_CASES[case]
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    env = detect_mod().detect(tmp_path)
    assert env.test_command == command
    if language:
        assert language in env.languages


def test_detect_makefile_without_test_target(tmp_path):
    (tmp_path / "Makefile").write_text("build:\n\tcc main.c\n", encoding="utf-8")
    assert detect_mod().detect(tmp_path).test_command is None


# ---- FR-07 目的から段を組む（pipe-in-gen design） -------------------------------------


def design_mod():
    from pipe_in_generator import design

    return design


def good_design() -> dict:
    return {
        "label": "API の \"仕様\" を書く",
        "description": "ソースから API の一覧と使い方を書く",
        "input": "optional",
        "stages": [
            {"name": "survey", "label": "API の洗い出し", "output": "01_survey.md", "access": "read",
             "review": True, "prompt": '`src/` を読み、API を洗い出してください。\n"""三重の引用符""" や \ も書ける'},
            {"name": "write", "label": "API の文書", "output": "02_api.md", "access": "docs", "docs_dir": "docs/api",
             "writes": ["docs/api/*.md"], "prompt": "API の文書を書いてください。"},
            {"name": "check", "label": "突き合わせ", "output": "03_check.md", "access": "read",
             "prompt": "文書とソースを突き合わせてください。",
             "check": {"verdict": True, "on_fail": "write", "max_retries": 2}},
        ],
    }


class DesignRunner:
    def __init__(self, designs: list):
        self.designs = list(designs)
        self.calls: list[tuple[object, str, str | None]] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        from pipe_in.engine.runner import StageRun

        self.calls.append((spec, prompt, resume))
        return StageRun(stage=spec.name, session_id="d-1", structured=self.designs.pop(0), cost_usd=0.05, num_turns=3)


def design(tmp_path: Path, runner, *, name: str = "apidoc", force: bool = False) -> int:
    project = python_project(tmp_path)
    return design_mod().design_pipe(
        project, name, "API の文書を作りたい", pipes_dir=tmp_path / "pipes", runner=runner, force=force
    )


def test_design_writes_valid_pipe(tmp_path):
    r = DesignRunner([good_design()])
    assert design(tmp_path, r) == 0
    d = tmp_path / "pipes/pipe-in-apidoc"
    pipe = definition().load_pipe(d)
    assert [s.name for s in pipe.stages] == ["survey", "write", "check"]
    assert pipe.label == 'API の "仕様" を書く'
    assert '"""三重の引用符"""' in pipe.stages[0].prompt_text()
    assert pipe.stages[0].prompt_file is not None  # 指示は prompts/ のファイルに分ける
    assert pipe.stages[1].writes == ["docs/api/*.md"]
    assert pipe.stages[2].check.verdict and pipe.stages[2].check.on_fail == "write"
    assert definition().check_pipe(pipe, tmp_path / "shop") == []
    readme = (d / "README.md").read_text(encoding="utf-8")
    assert "pipe-in --pipe apidoc" in readme and "pipe-in-gen check apidoc" in readme
    assert "devpipe" not in readme.lower() and "devpipe" not in (d / "pipe.toml").read_text(encoding="utf-8").lower()
    spec, prompt, resume = r.calls[0]
    assert spec.can_write("docs/x.md") is False and "Write" not in spec.allowed_tools and not spec.allow_bash
    assert spec.output_format["type"] == "json_schema"
    assert "API の文書を作りたい" in prompt and "pytest -q" in prompt and resume is None


def test_design_asks_again_when_invalid(tmp_path):
    bad = good_design()
    bad["stages"][1]["name"] = "survey"
    r = DesignRunner([bad, good_design()])
    assert design(tmp_path, r) == 0
    assert len(r.calls) == 2
    _, prompt2, resume2 = r.calls[1]
    assert resume2 == "d-1" and "重複" in prompt2


def test_design_gives_up_without_writing(tmp_path):
    bad = good_design()
    bad["stages"] = []
    r = DesignRunner([bad, bad, bad])
    assert design(tmp_path, r) != 0
    assert len(r.calls) == 3
    assert not (tmp_path / "pipes/pipe-in-apidoc").exists()


def test_design_refuses_existing_pipe(tmp_path):
    """D0006-AC-08: 作る先（pipe-in-<名前>/）にもうあれば、設計を始めずに断る。"""
    (tmp_path / "pipes/pipe-in-apidoc").mkdir(parents=True)
    (tmp_path / "pipes/pipe-in-apidoc/pipe.toml").write_text("# 手で作った\n", encoding="utf-8")
    r = DesignRunner([good_design()])
    assert design(tmp_path, r) != 0
    assert r.calls == []
    assert "手で作った" in (tmp_path / "pipes/pipe-in-apidoc/pipe.toml").read_text(encoding="utf-8")


@pytest.mark.parametrize("force", [False, True], ids=["plain", "force"])
def test_design_refuses_name_in_old_place(tmp_path, capsys, force):
    """D0006-AC-08: 古い置き場所に同じ名前のパイプがあれば、design は設計を始めずに、場所を示して断る（--force でも）。"""
    project = tmp_path / "shop"
    old = make_old_pipe(project / ".devpipe" / "pipes", "devpipe-apidoc")
    r = DesignRunner([good_design()])
    capsys.readouterr()
    assert design(tmp_path, r, force=force) != 0
    assert r.calls == []
    assert str(old) in capsys.readouterr().out
    assert not (tmp_path / "pipes" / "pipe-in-apidoc").exists()


def test_design_cli_needs_purpose(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        gen(tmp_path, "design", "--help")
    assert e.value.code == 0 and "--purpose" in capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        gen(tmp_path, "design", "apidoc", "--project", str(tmp_path))
    assert e.value.code == 2  # --purpose がない


# ---- D0038: 警告の出力 -------------------------------------------------------------------


def write_warning_pipe(tmp_path: Path, *, with_error: bool = False) -> None:
    """W1 が1件出る定義（read・bash・指示に「保存」）を pipes/ に置く。with_error なら docs_dir 抜けの誤りも足す。"""
    d = tmp_path / "pipes" / "pipe-in-warny"
    d.mkdir(parents=True)
    text = (
        '[pipe]\nkind = "linear"\nlabel = "x"\n\n'
        '[[stages]]\nname = "probe"\nlabel = "probe"\noutput = "probe.md"\naccess = "read"\nbash = true\n'
        'prompt = "結果を保存する"\n'
    )
    if with_error:
        text += '\n[[stages]]\nname = "doc"\nlabel = "doc"\noutput = "doc.md"\naccess = "docs"\nprompt = "書く"\n'
    (d / "pipe.toml").write_text(text, encoding="utf-8")


def test_check_prints_warnings_and_passes(tmp_path, capsys):
    """D0038-AC-06: 警告だけのとき check は終了コード 0 で、「⚠」つきで警告を1行ずつ出す。"""
    project = python_project(tmp_path)
    write_warning_pipe(tmp_path)
    assert gen(tmp_path, "check", "warny", "--project", str(project)) == 0
    out = capsys.readouterr().out
    lines = [x for x in out.splitlines() if "⚠" in x]
    assert len(lines) == 1 and "probe" in lines[0] and 'access = "docs"' in lines[0]
    assert "問題ありません" not in out and "✗" not in out


def test_check_prints_errors_and_warnings(tmp_path, capsys):
    """D0038-AC-06: 誤りと警告の両方があるとき、終了コードは 1 で、誤りも警告も出す。"""
    project = python_project(tmp_path)
    write_warning_pipe(tmp_path, with_error=True)
    assert gen(tmp_path, "check", "warny", "--project", str(project)) == 1
    out = capsys.readouterr().out
    assert "✗" in out and "docs_dir" in out
    assert len([x for x in out.splitlines() if "⚠" in x]) == 1


def test_check_clean_pipe_prints_no_problem_line(tmp_path, capsys):
    """D0038-AC-07: 警告も誤りも無いときは、今までどおり「問題ありません」の1行だけ（⚠ は出ない）。"""
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", "pics", "--from", "diagrams", "--project", str(project)) == 0
    capsys.readouterr()
    assert gen(tmp_path, "check", "pics", "--project", str(project)) == 0
    out = capsys.readouterr().out
    assert out.strip().splitlines() == ["✓ パイプ「pics」: 問題ありません"]


def test_new_prints_warnings(tmp_path, capsys, monkeypatch):
    """D0038-AC-08: new でも、警告があれば同じ形で出し、終了コードは 0。"""
    cli = gen_cli()
    monkeypatch.setattr(cli, "templates_dir", lambda: _warning_template(tmp_path))
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", "warny", "--from", "warny", "--project", str(project)) == 0
    out = capsys.readouterr().out
    assert len([x for x in out.splitlines() if "⚠" in x]) == 1
    assert "問題ありません" not in out


def _warning_template(tmp_path: Path) -> Path:
    t = tmp_path / "tpl" / "warny"
    t.mkdir(parents=True)
    (t / "pipe.toml").write_text(
        '[pipe]\nkind = "linear"\nlabel = "x"\n\n'
        '[[stages]]\nname = "probe"\nlabel = "probe"\noutput = "probe.md"\naccess = "read"\nbash = true\n'
        'prompt = "結果を保存する"\n',
        encoding="utf-8",
    )
    (t / "README.md").write_text("# warny\n", encoding="utf-8")
    return tmp_path / "tpl"


def test_legacy_named_pipe_gets_same_warnings(tmp_path, capsys):
    """D0038-AC-11: 前の版の名前（.devpipe/pipes/devpipe-<名前>/）のパイプも、check で同じ警告を受け、終了コードは 0。"""
    project = python_project(tmp_path)
    d = project / ".devpipe" / "pipes" / "devpipe-oldwarn"
    d.mkdir(parents=True)
    (d / "pipe.toml").write_text(
        '[pipe]\nkind = "linear"\nlabel = "x"\n\n'
        '[[stages]]\nname = "probe"\nlabel = "probe"\noutput = "probe.md"\naccess = "read"\nbash = true\n'
        'prompt = "結果を保存する"\n',
        encoding="utf-8",
    )
    assert gen_cli().main(["check", "oldwarn", "--project", str(project)]) == 0
    out = capsys.readouterr().out
    assert len([x for x in out.splitlines() if "⚠" in x]) == 1 and "probe" in out
