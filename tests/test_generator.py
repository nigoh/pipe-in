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


TEMPLATES = ["dev", "diagrams", "spec-qa", "spec-review"]


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
             "review": True, "prompt": '`src/` を読み、API を洗い出してください。\n"""三重の引用符""" や \\ も書ける'},
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


# ---- D0037: 検査（command）と審査（judge）を組む ---------------------------------------------


def judge_design(**judge) -> dict:
    """judge だけの check（command も on_fail も無い）を持つ設計。judge の欄は引数で上書きする。"""
    j = {
        "threshold": 0.8,
        "criteria": [
            {"name": "網羅性", "description": "API が漏れなく挙がっている"},
            {"name": "分かりやすさ", "description": "使い方が読んで分かる"},
        ],
        "must": [{"name": "ソースにある", "description": "文書に、ソースに根拠のない API がありますか（ある＝違反）"}],
    }
    j.update(judge)
    d = good_design()
    d["stages"][2]["check"] = {"judge": j}
    return d


def write_rendered(tmp_path: Path, design_: dict) -> Path:
    """render_pipe の結果を tmp_path の中のパイプのフォルダに書く。"""
    folder = tmp_path / "rendered" / "pipe-in-apidoc"
    for rel, text in design_mod().render_pipe("apidoc", "目的", design_).items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_text(text, encoding="utf-8")
    return folder


def test_d0037_ac15_judge_only_design_renders(tmp_path):
    """D0037-AC-15: judge（threshold・criteria・must）だけの check を render_pipe に渡すと [stages.check] と [stages.check.judge] と criteria・must の表が書かれ、読んで check_pipe が誤りを返さない。design_pipe を通してもパイプが書かれる。"""
    files = design_mod().render_pipe("apidoc", "目的", judge_design())
    text = files["pipe.toml"]
    for word in ["[stages.check]", "[stages.check.judge]", "[[stages.check.judge.criteria]]", "[[stages.check.judge.must]]", "threshold = 0.8"]:
        assert word in text, word
    folder = write_rendered(tmp_path, judge_design())
    pipe = definition().load_pipe(folder)
    check = pipe.stages[2].check
    assert check is not None and check.judge is not None
    assert check.judge.threshold == 0.8
    assert [i.name for i in check.judge.criteria] == ["網羅性", "分かりやすさ"]
    assert [i.name for i in check.judge.must] == ["ソースにある"]
    assert definition().check_pipe(pipe, python_project(tmp_path / "check")) == []
    # design_pipe を通しても書かれる
    r = DesignRunner([judge_design()])
    assert design(tmp_path, r) == 0
    written = definition().load_pipe(tmp_path / "pipes/pipe-in-apidoc")
    assert written.stages[2].check is not None and written.stages[2].check.judge is not None
    assert written.stages[2].check.judge.must[0].name == "ソースにある"


def test_d0037_ac16_readme_check_column():
    """D0037-AC-16: judge だけの設計でも README の段の表の「検証」の欄が「あり」になる。check の無い段は「なし」。"""
    readme = design_mod().render_pipe("apidoc", "目的", judge_design())["README.md"]
    rows = [ln for ln in readme.splitlines() if ln.startswith("| ") and "`0" in ln]
    assert len(rows) == 3
    assert rows[0].endswith("| なし |") and rows[1].endswith("| なし |")
    assert rows[2].endswith("| あり |")


SMALL_BASE = {
    "label": "L",
    "description": "D",
    "input": "optional",
    "stages": [
        {"name": "a", "label": "A", "output": "01_a.md", "access": "read", "prompt": "P"},
        {"name": "b", "label": "B", "output": "02_b.md", "access": "read", "prompt": "Q"},
    ],
}
TOML_HEAD = (
    "# pipe-in-gen design で作ったパイプ。段の並び・書き込める範囲・確認の有無はここで、各段への指示は prompts/ で決めます。\n"
    '\n[pipe]\nkind = "linear"\nlabel = "L"\ndescription = "D"\ninput = "optional"\n'
    '\n[[stages]]\nname = "a"\nlabel = "A"\noutput = "01_a.md"\naccess = "read"\nprompt_file = "prompts/01_a.md"\n'
    '\n[[stages]]\nname = "b"\nlabel = "B"\noutput = "02_b.md"\naccess = "read"\nprompt_file = "prompts/02_b.md"\n'
)


def small_with(check):
    import copy

    d = copy.deepcopy(SMALL_BASE)
    if check is not None:
        d["stages"][1]["check"] = check
    return d


@pytest.mark.parametrize(
    "check,tail,mark",
    [
        ({"verdict": True, "on_fail": "a", "max_retries": 2}, '[stages.check]\nverdict = true\non_fail = "a"\nmax_retries = 2\n', "あり"),
        ({"command": "pytest -q", "on_fail": "a", "max_retries": 1}, '[stages.check]\ncommand = "pytest -q"\non_fail = "a"\nmax_retries = 1\n', "あり"),
        ({"on_fail": "a"}, "", "なし"),
        (None, "", "なし"),
    ],
    ids=["verdict", "command", "no-check-fields", "no-check"],
)
@pytest.mark.parametrize("judge", [None, {}, "absent"], ids=["judge-none", "judge-empty", "judge-absent"])
def test_d0037_ac17_render_without_judge_unchanged(check, tail, mark, judge):
    """D0037-AC-17: 今の作りのままで通る（変更前の出力を固定した検査）。verdict または command だけの設計は、judge が無くても None でも空でも、pipe.toml と README の表が文字まで同じ。"""
    if check is not None and judge != "absent":
        check = {**check, "judge": judge}
    files = design_mod().render_pipe("x", "目的", small_with(check))
    assert files["pipe.toml"] == TOML_HEAD + tail
    row = "| B | `02_b.md` | read | なし | " + mark + " |"
    assert row in files["README.md"].splitlines()
    assert "| A | `01_a.md` | read | なし | なし |" in files["README.md"].splitlines()


@pytest.mark.parametrize(
    "why,word,judge",
    [
        ("threshold", "threshold", {"threshold": 1.5}),
        ("criteria", "criteria", {"criteria": []}),
        ("dup", "重複", {"criteria": [{"name": "同じ", "description": "a"}, {"name": "同じ", "description": "b"}]}),
    ],
)
def test_d0037_ac18_bad_judge_asks_again(tmp_path, why, word, judge):
    """D0037-AC-18: threshold が範囲外・criteria が空・名前が重なる審査は check_pipe が止め、直しの依頼文に理由が入る。max_rounds 回通らなければ何も書かない。"""
    bad = judge_design(**judge)
    r = DesignRunner([bad, judge_design()])
    assert design(tmp_path, r) == 0
    assert len(r.calls) == 2
    _, prompt2, resume2 = r.calls[1]
    assert resume2 == "d-1" and word in prompt2
    # 通らないまま 3 回なら、何も書かない（別の一時フォルダで流す）
    again = tmp_path / "again"
    r2 = DesignRunner([bad, bad, bad])
    assert design(again, r2) != 0
    assert len(r2.calls) == 3
    assert not (again / "pipes/pipe-in-apidoc").exists()


def test_d0037_ac19_schema_has_judge():
    """D0037-AC-19: DESIGN_SCHEMA の check に judge があり、criteria・must の要素は name・description を持つ。judge は必須ではない。"""
    check = design_mod().DESIGN_SCHEMA["properties"]["stages"]["items"]["properties"]["check"]
    judge = check["properties"]["judge"]
    assert judge["properties"]["threshold"]["type"] == "number"
    for key in ["criteria", "must"]:
        item = judge["properties"][key]["items"]
        assert {"name", "description"} <= set(item["properties"]), key
        assert {"name", "description"} <= set(item["required"]), key
    assert "judge" not in check.get("required", [])
    assert "judge" not in judge.get("required", [])


def test_d0037_ac20_design_rules_words():
    """D0037-AC-20: design_rules.md に judge・must・「審査で差し戻すなら」・「command と組む」があり、designer_spec の system_append にそのまま入る。"""
    from importlib import resources

    rules = resources.files("pipe_in_generator").joinpath("design_rules.md").read_text(encoding="utf-8")
    missing = [w for w in ["judge", "must", "審査で差し戻すなら", "command と組む"] if w not in rules]
    assert missing == []
    assert rules in design_mod().designer_spec().system_append


def test_d0037_ac21_rules_example_design_passes_check(tmp_path):
    """D0037-AC-21: design_rules.md の中の設計の例（```json の囲み。judge と command を含む）を設計の段が返したものとして渡すと、design_pipe が 0 を返し check_pipe が通る。"""
    import re
    from importlib import resources

    rules = resources.files("pipe_in_generator").joinpath("design_rules.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)```", rules, re.S)
    assert blocks, "design_rules.md に ```json の設計の例が無い"
    example = json.loads(blocks[0])
    checks = [s.get("check") or {} for s in example["stages"]]
    assert any(c.get("command") for c in checks) and any(c.get("judge") for c in checks)
    r = DesignRunner([example])
    assert design(tmp_path, r) == 0
    assert len(r.calls) == 1  # 1回で通る＝例が検査に合っている
    pipe = definition().load_pipe(tmp_path / "pipes/pipe-in-apidoc")
    assert definition().check_pipe(pipe, tmp_path / "shop") == []
    assert any(s.check is not None and s.check.judge is not None for s in pipe.stages)


# ---- D0037: ひな形 diagrams の審査 -------------------------------------------------------


def new_pipe(tmp_path: Path, template: str):
    project = python_project(tmp_path)
    assert gen(tmp_path, "new", "pics", "--from", template, "--project", str(project)) == 0
    folder = tmp_path / "pipes/pipe-in-pics"
    return project, folder, definition().load_pipe(folder)


def verify_stage(pipe):
    return next(s for s in pipe.stages if s.name == "verify")


def test_d0037_ac23_diagrams_verify_has_judge(tmp_path):
    """D0037-AC-23: ひな形 diagrams の verify 段に judge（must 1つ以上・criteria 2つ以上・threshold が範囲内）があり、verdict = true・on_fail = draw・max_retries = 2 はそのまま。command は python -c で始まる。"""
    _, _, pipe = new_pipe(tmp_path, "diagrams")
    c = verify_stage(pipe).check
    assert c is not None
    assert c.verdict is True and c.on_fail == "draw" and c.max_retries == 2
    assert c.judge is not None
    assert len(c.judge.must) >= 1 and len(c.judge.criteria) >= 2
    assert 0 <= c.judge.threshold <= 1
    assert c.command and c.command.startswith("python -c")


def test_d0037_diagrams_command_text_is_quote_safe(tmp_path):
    """D0037-AC-23: command に、sh と cmd.exe で壊れる文字（バッククォート・$・%・!・\\）が無く、DANGEROUS_BASH に当たらない（check が通る）。"""
    project, _, pipe = new_pipe(tmp_path, "diagrams")
    command = verify_stage(pipe).check.command
    assert command, "verify 段に command が無い"
    assert [ch for ch in "`$%!\\" if ch in command] == []
    assert gen(tmp_path, "check", "pics", "--project", str(project)) == 0


def run_diagrams_command(tmp_path: Path, files: dict[str, str]) -> int:
    """ひな形 diagrams の command を、本体の run_shell で、tmp_path の中の対象で流して終了コードを返す。"""
    import sys

    from pipe_in.engine.pipeline import run_shell

    project, _, pipe = new_pipe(tmp_path, "diagrams")
    command = verify_stage(pipe).check.command
    assert command and command.startswith("python"), "verify 段に python -c の command が無い"
    command = f'"{sys.executable}"' + command[len("python"):]
    for rel, text in files.items():
        (project / rel).parent.mkdir(parents=True, exist_ok=True)
        (project / rel).write_text(text, encoding="utf-8")
    result = run_shell(command, project, 60)
    assert result.returncode is not None, result.output_tail
    return result.returncode


def test_d0037_diagrams_command_runs_on_shell_passes_with_mermaid(tmp_path):
    """D0037-AC-23: Mermaid のブロックがある *.md が図の置き場所にあれば、command は終了コード 0（合格）。"""
    fence = "`" * 3
    code = run_diagrams_command(tmp_path, {"docs/diagrams/flow.md": f"# 図\n\n{fence}mermaid\ngraph TD\n  A --> B\n{fence}\n"})
    assert code == 0


def test_d0037_diagrams_command_runs_on_shell_fails_without_mermaid(tmp_path):
    """D0037-AC-23: Mermaid のブロックが無い *.md だけなら終了コード 1（不合格）。"""
    assert run_diagrams_command(tmp_path, {"docs/diagrams/flow.md": "# 図は文字だけ\n"}) == 1


def test_d0037_diagrams_command_runs_on_shell_fails_without_folder(tmp_path):
    """D0037-AC-23: 図の置き場所のフォルダが無ければ終了コード 1（不合格）。"""
    assert run_diagrams_command(tmp_path, {}) == 1


@pytest.mark.parametrize("name", ["dev", "spec-qa"])
def test_d0037_ac12_old_templates_without_judge_load(tmp_path, name):
    """D0037-AC-12: 今の作りのままで通る。これまでのひな形（dev・spec-qa）から作った judge のない pipe.toml は、読み込み・検査が変わらず、どの段も check.judge は None。"""
    project, _, pipe = new_pipe(tmp_path, name)
    assert all(s.check is None or s.check.judge is None for s in pipe.stages)
    assert gen(tmp_path, "check", "pics", "--project", str(project)) == 0


@pytest.mark.parametrize("name", ["dev", "spec-qa"])
def test_d0037_ac25_dev_and_spec_qa_templates_unchanged(name):
    """D0037-AC-25: 今の作りのままで通る。dev・spec-qa のひな形の pipe.toml に judge も command の追加も無い。"""
    text = (gen_cli().templates_dir() / name / "pipe.toml").read_text(encoding="utf-8")
    assert "judge" not in text
    assert not [ln for ln in text.splitlines() if ln.strip().startswith("command")]
    assert "[stages.check" not in text


def test_d0037_ac26_diagrams_docs_mention_judge():
    """D0037-AC-26: diagrams の README の段の表と説明、prompts/03_verify.md に、審査と must の説明がある。README には python が無い環境の注意もある。"""
    tdir = gen_cli().templates_dir() / "diagrams"
    readme = (tdir / "README.md").read_text(encoding="utf-8")
    verify = (tdir / "prompts/03_verify.md").read_text(encoding="utf-8")
    assert [w for w in ["must", "審査", "python"] if w not in readme] == []
    assert [w for w in ["must", "審査"] if w not in verify] == []


OLD_DIAGRAMS = '''[pipe]
kind = "linear"
label = "ソースから図を作る"
description = "ソースを調べ、図を描き、確かめる"
input = "optional"

[[stages]]
name = "survey"
label = "ソースの調査"
output = "01_survey.md"
access = "read"
review = true
prompt_file = "prompts/01_survey.md"

[[stages]]
name = "draw"
label = "図を描く"
output = "02_diagrams.md"
access = "docs"
docs_dir = "docs/diagrams"
review = true
prompt_file = "prompts/02_draw.md"

[[stages]]
name = "verify"
label = "図とソースの突き合わせ"
output = "03_verify.md"
access = "read"
prompt_file = "prompts/03_verify.md"
[stages.check]
verdict = true
on_fail = "draw"
max_retries = 2
'''


def test_d0037_ac27_old_diagrams_shape_still_loads(tmp_path):
    """D0037-AC-27: 今の作りのままで通る。judge も command も無く verdict・on_fail・max_retries だけの、足す前の diagrams 形のパイプは、読み込みも検査もできる。"""
    folder = tmp_path / "pipes/pipe-in-old"
    (folder / "prompts").mkdir(parents=True)
    (folder / "pipe.toml").write_text(OLD_DIAGRAMS, encoding="utf-8")
    for n in ["01_survey", "02_draw", "03_verify"]:
        (folder / f"prompts/{n}.md").write_text("指示\n", encoding="utf-8")
    pipe = definition().load_pipe(folder)
    c = verify_stage(pipe).check
    assert c.verdict is True and c.command is None and c.judge is None
    assert definition().check_pipe(pipe, python_project(tmp_path)) == []


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


# ---- D0053: W6 の出力と、組み方の目安（design_rules.md） ----------------------------------------------

# W6 だけが出る定義（read の段・「指摘にします」・引用の言葉も findings-check も無い。bash なしなので W1 は出ない）
W6_ONLY_PIPE = (
    '[pipe]\nkind = "linear"\nlabel = "x"\n\n'
    '[[stages]]\nname = "find"\nlabel = "find"\noutput = "find.md"\naccess = "read"\n'
    'prompt = "仕様書を読んで、問題を1つずつ指摘にします。"\n'
)


def test_d0053_ac13_check_prints_w6_and_passes(tmp_path, capsys):
    """D0053-AC-13: pipe-in-gen check で W6 だけが出るとき、終了コード 0 で「誤りはありません（注意 1 件）」の行と、findings-check を含む ⚠ の行を1つ出す。"""
    project = python_project(tmp_path)
    d = tmp_path / "pipes" / "pipe-in-findy"
    d.mkdir(parents=True)
    (d / "pipe.toml").write_text(W6_ONLY_PIPE, encoding="utf-8")
    assert gen(tmp_path, "check", "findy", "--project", str(project)) == 0
    out = capsys.readouterr().out
    assert "✓ パイプ「findy」: 誤りはありません（注意 1 件）" in out.splitlines()
    marks = [x for x in out.splitlines() if "⚠" in x]
    assert len(marks) == 1 and "findings-check" in marks[0]
    assert "問題ありません" not in out and "✗" not in out


def test_d0053_ac14_legacy_named_pipe_gets_w6(tmp_path, capsys):
    """D0053-AC-14: 前の版の名前（.devpipe/pipes/devpipe-<名前>/）のパイプも、W6 の検査を同じに受け、終了コードは 0（⚠ の行が1つ）。"""
    project = python_project(tmp_path)
    d = project / ".devpipe" / "pipes" / "devpipe-oldfind"
    d.mkdir(parents=True)
    (d / "pipe.toml").write_text(W6_ONLY_PIPE, encoding="utf-8")
    assert gen_cli().main(["check", "oldfind", "--project", str(project)]) == 0
    out = capsys.readouterr().out
    marks = [x for x in out.splitlines() if "⚠" in x]
    assert len(marks) == 1 and "findings-check" in marks[0] and "find" in marks[0]


def md_section(text: str, heading_word: str) -> str:
    """「## …」の節（見出しに heading_word を含むもの）の本文。次の「## 」の前まで。無ければ空。"""
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = heading_word in line
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


# （pytest の id, 何を書くか, 探す言葉の正規表現）。分かったこと 1・2・3・5・7 と限界の目印（D0053 の設計で決めた）
D0053_LESSON_MARKS = [
    ("1-external-check", "1：土台は作る段1つと外の検査", "外の検査"),
    ("2-verbatim", "2：指摘ごとに原文を逐語で引用させる", "逐語"),
    ("3-only-one", "3：精度を上げる確かめは1つだけ", "1つだけ"),
    ("5-no-narrowing", "5：下見の点数で調べる範囲を絞らない", "範囲を絞らない"),
    ("7-separate-tests", "7：テストを書く段と実装の段を分ける", "テストを書く段と実装の段を分ける"),
    ("limit-haiku", "限界：Claude Haiku だけ", "Haiku"),
    ("limit-unchecked", "限界：ほかのモデルや実際のプロジェクトでは確かめていない", "確かめてい(ない|ません)"),
]


@pytest.mark.parametrize("label,pattern", [(label, p) for _, label, p in D0053_LESSON_MARKS], ids=[i for i, _, _ in D0053_LESSON_MARKS])
def test_d0053_ac16_design_rules_has_harness_lessons(label, pattern):
    """D0053-AC-16: generator/design_rules.md の、見出しに「組み方の目安」を含む節に、分かったこと 1・2・3・5・7 と限界の目印がある。"""
    import re
    from importlib import resources

    rules = resources.files("pipe_in_generator").joinpath("design_rules.md").read_text(encoding="utf-8")
    part = md_section(rules, "組み方の目安")
    assert part, "design_rules.md に「組み方の目安」の節が無い"
    found = re.search(pattern, part) is not None  # 節の本文を assert の失敗の表示に出さない
    assert found, f"「組み方の目安」に、{label} が無い（探した言葉：{pattern}）"
