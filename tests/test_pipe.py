"""パイプ（pipes/pipe-in-<名前>/ のフォルダ。前の版の devpipe-<名前>/ も読む）の読み込み・検査・実行を、SDK を呼ばずに確かめる。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pipe_in.dev.specs import STAGES
from pipe_in.engine.checkpoint import Decision
from pipe_in.engine.config import load_config
from pipe_in.engine.guard import check_tool
from pipe_in.engine.pipeline import STATE, SUMMARY, Exit
from pipe_in.engine.runner import StageRun


# 新しい部品はテストの中で読み込む（1件ずつ、何で落ちたかが見えるように）
def definition():
    from pipe_in.pipe import definition

    return definition


def pipe_specs():
    from pipe_in.pipe import specs

    return specs


def linear_cls():
    from pipe_in.pipe.pipeline import LinearPipeline

    return LinearPipeline


PICS = '''
[pipe]
kind = "linear"
label = "図を作る"
input = "optional"

[[stages]]
name = "survey"
label = "調査"
output = "01_survey.md"
access = "read"
review = true
prompt_file = "prompts/01_survey.md"

[[stages]]
name = "draw"
label = "図を描く"
output = "02_draw.md"
access = "docs"
docs_dir = "docs/diagrams"
prompt = "図を描いてください"
'''


def make_pipe(
    pipes_dir: Path, name: str = "pics", toml: str = PICS, prompts: dict[str, str] | None = None, prefix: str = "pipe-in-"
) -> Path:
    d = pipes_dir / f"{prefix}{name}"
    (d / "prompts").mkdir(parents=True, exist_ok=True)
    (d / "pipe.toml").write_text(toml, encoding="utf-8")
    for fname, text in (prompts if prompts is not None else {"01_survey.md": "ソースを調べてください\n"}).items():
        (d / "prompts" / fname).write_text(text, encoding="utf-8")
    return d


def load(tmp_path: Path, name: str = "pics", toml: str = PICS, **kw):
    return definition().load_pipe(make_pipe(tmp_path / "pipes", name, toml, **kw))


class FakePipeRunner:
    """パイプの段の代わりに成果物を書く。skip に入れた段は何も書かない。"""

    def __init__(self, pipe, skip: tuple[str, ...] = ()):
        self.outputs = {s.name: s.output for s in pipe.stages}
        self.skip = skip
        self.calls: list[tuple[str, str | None, str]] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append((spec.name, resume, prompt))
        if spec.name not in self.skip:
            (cfg.work_dir / self.outputs[spec.name]).write_text(f"# {spec.name}\n", encoding="utf-8")
        return StageRun(stage=spec.name, session_id=f"s-{len(self.calls)}", cost_usd=0.01, num_turns=2)

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]


def pipe_cfg(project: Path, pipe, **kw):
    cfg = load_config(project, None, auto_approve=kw.pop("auto_approve", True), **kw)
    return cfg.for_pipe(pipe.name, own_work_dir=True)


def run_pipe(p, text: str | None = "src/ の図を作る", frm: str | None = None) -> Exit:
    return asyncio.run(p.run(text, frm))


def state_at(cfg) -> dict:
    return json.loads((cfg.work_dir / STATE).read_text(encoding="utf-8"))


# ---- AC-01: パイプなしは今と同じ（記録に pipe と stages が増えるだけ） ------------------


def test_dev_state_has_pipe_fields(tmp_path):
    from pipe_in.dev.pipeline import DevPipeline
    from test_pipeline import FakeRunner

    cfg = load_config(tmp_path, None, auto_approve=True)
    assert asyncio.run(DevPipeline(cfg, runner=FakeRunner(["pass"])).run("ログイン画面", "requirements")) == Exit.PASSED
    s = json.loads((tmp_path / "docs/pipeline" / STATE).read_text(encoding="utf-8"))
    assert s["pipe"] == "dev"
    assert [x["name"] for x in s["stages"]] == list(STAGES)
    assert s["stages"][0]["label"] == "要件定義"


# ---- AC-02・AC-03: 定義の読み込み・検査・探す -----------------------------------


def test_load_pipe_reads_folder(tmp_path):
    pipe = load(tmp_path)
    assert pipe.name == "pics" and pipe.kind == "linear" and pipe.label == "図を作る"
    assert pipe.dir == (tmp_path / "pipes/pipe-in-pics")
    assert [s.name for s in pipe.stages] == ["survey", "draw"]
    survey, draw = pipe.stages
    assert (survey.access, survey.review, survey.bash, survey.output) == ("read", True, False, "01_survey.md")
    assert survey.prompt_text() == "ソースを調べてください"  # prompts/ のファイルから
    assert draw.prompt_text() == "図を描いてください"  # 定義に直接
    assert draw.access == "docs" and draw.docs_dir == "docs/diagrams" and draw.review is False
    assert definition().check_pipe(pipe, tmp_path) == []


BROKEN = {
    "duplicate": (PICS.replace('name = "draw"', 'name = "survey"'), "重複"),
    "unknown_access": (PICS.replace('access = "read"', 'access = "root"'), "root"),
    "outside_docs_dir": (PICS.replace('docs_dir = "docs/diagrams"', 'docs_dir = "../outside"'), "プロジェクトの外"),
    "missing_prompt_file": (PICS.replace("prompts/01_survey.md", "prompts/nothing.md"), "見つかりません"),
    "prompt_outside_pipe": (PICS.replace("prompts/01_survey.md", "../outside.md"), "パイプのフォルダの外"),
    "no_stages": ('[pipe]\nkind = "linear"\nlabel = "空"\n', "段がありません"),
}


@pytest.mark.parametrize("case", list(BROKEN))
def test_check_pipe_errors(tmp_path, case):
    text, word = BROKEN[case]
    (tmp_path / "pipes").mkdir()
    (tmp_path / "pipes/outside.md").write_text("外の指示", encoding="utf-8")
    errors = definition().check_pipe(load(tmp_path, toml=text), tmp_path)
    assert errors, case
    assert any(word in e for e in errors), errors


@pytest.fixture
def no_env(monkeypatch):
    """手元の環境変数に左右されないよう、置き場所の環境変数を新旧とも消す。"""
    monkeypatch.delenv("PIPE_IN_PIPES_DIR", raising=False)
    monkeypatch.delenv("DEVPIPE_PIPES_DIR", raising=False)
    return monkeypatch


def test_find_pipe_by_name_or_path(tmp_path):
    """D0006-AC-05: 名前でもパスでも探せ、名前は pipe-in-<名前>/ から読む。"""
    pipes = tmp_path / "pipes"
    d = make_pipe(pipes)
    assert definition().find_pipe("pics", pipes) == d
    assert definition().find_pipe(str(d), pipes) == d
    assert definition().find_pipe("nothing", pipes) is None
    assert definition().find_pipe("../pics", pipes) is None
    other = make_pipe(tmp_path / "elsewhere", "mine")
    assert definition().find_pipe(str(other), pipes) == other
    assert definition().load_pipe(other).name == "mine"


def test_find_pipe_prefers_project_pipes(tmp_path, no_env):
    """D0001-AC-13・D0006-AC-06: 対象の .pipe-in/pipes/ → .devpipe/pipes/ → 今までの場所の順に見る。"""
    shared = tmp_path / "shared"
    no_env.setenv("PIPE_IN_PIPES_DIR", str(shared))
    project = tmp_path / "app"
    mine = make_pipe(project / ".pipe-in" / "pipes", "pics")
    make_pipe(shared, "pics")
    only_shared = make_pipe(shared, "old")
    assert definition().find_pipe("pics", project=project) == mine
    assert definition().find_pipe("old", project=project) == only_shared
    assert definition().find_pipe("nothing", project=project) is None
    assert definition().pipes_dirs(project=project) == [project / ".pipe-in" / "pipes", project / ".devpipe" / "pipes", shared]


def test_find_pipe_explicit_dir_only(tmp_path, no_env):
    """D0001-AC-13・D0006-AC-05: --pipes-dir を指定したときは、その中の pipe-in-<名前>/ → devpipe-<名前>/ だけを見る。"""
    project = tmp_path / "app"
    make_pipe(project / ".pipe-in" / "pipes", "pics")
    make_pipe(project / ".devpipe" / "pipes", "pics", prefix="devpipe-")
    explicit = tmp_path / "explicit"
    assert definition().find_pipe("pics", explicit, project=project) is None
    old = make_pipe(explicit, "pics", prefix="devpipe-")
    assert definition().find_pipe("pics", explicit, project=project) == old
    new = make_pipe(explicit, "pics")
    assert definition().find_pipe("pics", explicit, project=project) == new
    assert definition().pipes_dirs(project=project, pipes_dir=explicit) == [explicit]


def test_find_pipe_prefers_new_place_then_old(tmp_path, no_env):
    """D0006-AC-05: 対象の .pipe-in/pipes/pipe-in-x/ があればそれ、無くて .devpipe/pipes/devpipe-x/ があればそれ。"""
    no_env.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "shared"))
    project = tmp_path / "app"
    old = make_pipe(project / ".devpipe" / "pipes", "pics", prefix="devpipe-")
    assert definition().find_pipe("pics", project=project) == old
    new = make_pipe(project / ".pipe-in" / "pipes", "pics")
    assert definition().find_pipe("pics", project=project) == new


def test_find_pipe_prefers_new_folder_name_in_same_place(tmp_path, no_env):
    """D0006-AC-05: 同じ置き場所に pipe-in-x/ と devpipe-x/ があれば pipe-in-x/。"""
    no_env.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "shared"))
    project = tmp_path / "app"
    base = project / ".pipe-in" / "pipes"
    old = make_pipe(base, "pics", prefix="devpipe-")
    assert definition().find_pipe("pics", project=project) == old
    new = make_pipe(base, "pics")
    assert definition().find_pipe("pics", project=project) == new


def test_load_pipe_name_from_old_folder(tmp_path):
    """D0006-AC-05: devpipe-<名前>/ のパイプも、pipe-in-<名前>/ のパイプも、名前は頭を除いたもの。"""
    assert definition().load_pipe(make_pipe(tmp_path / "a", "pics", prefix="devpipe-")).name == "pics"
    assert definition().load_pipe(make_pipe(tmp_path / "b", "pics")).name == "pics"
    assert definition().load_pipe(make_pipe(tmp_path / "c", "pics", prefix="")).name == "pics"  # 頭が無いフォルダはそのまま


def test_pipes_dirs_order(tmp_path, no_env):
    """D0006-AC-06: 探す順は 対象の .pipe-in/pipes → 対象の .devpipe/pipes → 今までの場所。"""
    no_env.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "shared"))
    project = tmp_path / "app"
    assert definition().pipes_dirs(project) == [project / ".pipe-in" / "pipes", project / ".devpipe" / "pipes", tmp_path / "shared"]
    assert definition().pipes_dirs() == [tmp_path / "shared"]


def test_folder_names_and_prefixes():
    """D0006-AC-05: フォルダ名の頭は pipe-in- が先、devpipe- が後。名前の読み替えは両方の頭に効く。"""
    d = definition()
    assert d.PREFIX == "pipe-in-" and d.LEGACY_PREFIX == "devpipe-"
    assert d.PREFIXES == ("pipe-in-", "devpipe-")
    assert d.pipe_folders("x") == ["pipe-in-x", "devpipe-x"]
    assert d.name_of("pipe-in-x") == "x" and d.name_of("devpipe-x") == "x"
    assert d.name_of("x") is None and d.name_of("pipe-in-") is None and d.name_of("pipe-in-Bad") is None


def test_is_legacy(tmp_path):
    """D0006-AC-09: devpipe- で始まるフォルダか、.devpipe/pipes の中のフォルダは古い名前。"""
    d = definition()
    assert d.is_legacy(tmp_path / "pipes" / "devpipe-x")
    assert d.is_legacy(tmp_path / ".devpipe" / "pipes" / "pipe-in-x")
    assert not d.is_legacy(tmp_path / ".pipe-in" / "pipes" / "pipe-in-x")
    assert not d.is_legacy(tmp_path / "pipes" / "pipe-in-x")


def test_new_pipes_dir_order(tmp_path, no_env):
    """D0001-AC-15・D0006-AC-07: 作る場所は --pipes-dir → PIPE_IN_PIPES_DIR → DEVPIPE_PIPES_DIR → 対象の .pipe-in/pipes/。"""
    project = tmp_path / "app"
    assert definition().new_pipes_dir(project) == project / ".pipe-in" / "pipes"
    no_env.setenv("DEVPIPE_PIPES_DIR", str(tmp_path / "old-env"))
    assert definition().new_pipes_dir(project) == tmp_path / "old-env"
    no_env.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "env"))
    assert definition().new_pipes_dir(project) == tmp_path / "env"
    assert definition().new_pipes_dir(project, tmp_path / "given") == tmp_path / "given"


def test_new_pipes_dir_prefers_new_env(tmp_path, no_env):
    """D0006-AC-07: 両方の環境変数があれば PIPE_IN_PIPES_DIR に作る。"""
    no_env.setenv("DEVPIPE_PIPES_DIR", str(tmp_path / "old-env"))
    no_env.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "env"))
    assert definition().new_pipes_dir(tmp_path / "app") == tmp_path / "env"


def test_default_pipes_dir_can_be_overridden(tmp_path, no_env):
    """D0006-AC-10: PIPE_IN_PIPES_DIR → DEVPIPE_PIPES_DIR → リポジトリの pipes/。"""
    no_env.setenv("DEVPIPE_PIPES_DIR", str(tmp_path / "old-pipes"))
    assert definition().default_pipes_dir() == tmp_path / "old-pipes"
    no_env.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "my-pipes"))
    assert definition().default_pipes_dir() == tmp_path / "my-pipes"
    no_env.delenv("PIPE_IN_PIPES_DIR")
    no_env.delenv("DEVPIPE_PIPES_DIR")
    assert definition().default_pipes_dir().name == "pipes"
    assert (definition().default_pipes_dir() / "README.md").is_file()  # リポジトリの pipes/


@pytest.mark.parametrize(
    "environ,want",
    [
        ({}, None),
        ({"PIPE_IN_PIPES_DIR": "new"}, "new"),
        ({"DEVPIPE_PIPES_DIR": "old"}, "old"),
        ({"PIPE_IN_PIPES_DIR": "new", "DEVPIPE_PIPES_DIR": "old"}, "new"),
        ({"PIPE_IN_PIPES_DIR": "", "DEVPIPE_PIPES_DIR": "old"}, "old"),  # 空の値は無いものとする
    ],
)
def test_env_pipes_dir_prefers_new_name(environ, want):
    """D0006-AC-10: env_pipes_dir は PIPE_IN_PIPES_DIR → DEVPIPE_PIPES_DIR の順（辞書で渡す）。"""
    got = definition().env_pipes_dir(environ)
    assert got == (Path(want) if want else None)


# ---- AC-04〜AC-07: パイプの実行 ---------------------------------------------------


def test_linear_runs_in_order_with_previous_outputs(tmp_path):
    pipe = load(tmp_path)
    cfg = pipe_cfg(tmp_path, pipe)
    r = FakePipeRunner(pipe)
    assert run_pipe(linear_cls()(cfg, pipe, runner=r)) == Exit.PASSED
    assert r.names() == ["survey", "draw"]
    assert cfg.work_dir == (tmp_path / "docs/pipeline/pics").resolve()
    first, second = r.calls[0][2], r.calls[1][2]
    assert "ソースを調べてください" in first
    assert "docs/pipeline/pics/00_input.md" in first
    assert "docs/pipeline/pics/01_survey.md" in second
    assert "docs/pipeline/pics/02_draw.md" in second
    assert "docs/diagrams/" in second


def test_linear_review_approve_revise_quit(tmp_path):
    pipe = load(tmp_path)
    answers = iter([Decision("revise", "入口を足して"), Decision("approve")])
    asked: list[str] = []

    def ask(stage, doc):
        asked.append(stage)
        return next(answers)

    r = FakePipeRunner(pipe)
    cfg = pipe_cfg(tmp_path, pipe, auto_approve=False)
    assert run_pipe(linear_cls()(cfg, pipe, runner=r, ask=ask)) == Exit.PASSED
    assert asked == ["survey", "survey"]  # review = true の段だけ
    assert r.names() == ["survey", "survey", "draw"]
    assert r.calls[1][1] == "s-1"  # 同じ会話のまま直す
    assert "入口を足して" in r.calls[1][2]

    quitter = FakePipeRunner(pipe)
    p = linear_cls()(pipe_cfg(tmp_path, pipe, auto_approve=False), pipe, runner=quitter, ask=lambda s, d: Decision("quit"))
    assert run_pipe(p) == Exit.STOPPED_BY_HUMAN
    assert quitter.names() == ["survey"]


def test_linear_pause_and_review(tmp_path):
    pipe = load(tmp_path)
    cfg = pipe_cfg(tmp_path, pipe, auto_approve=False, pause_for_review=True)
    assert run_pipe(linear_cls()(cfg, pipe, runner=FakePipeRunner(pipe))) == Exit.AWAITING_REVIEW
    s = state_at(cfg)
    assert s["pending_review"]["stage"] == "survey"
    assert s["pending_review"]["doc"].endswith("01_survey.md")

    r = FakePipeRunner(pipe)
    p = linear_cls()(pipe_cfg(tmp_path, pipe, auto_approve=False, pause_for_review=True), pipe, runner=r)
    assert asyncio.run(p.review(Decision("approve"))) == Exit.PASSED
    assert r.names() == ["draw"]
    s = state_at(cfg)
    assert s["final"] == "PASSED" and s.get("pending_review") is None
    assert {"stage": "survey", "review": "approved"} in s["runs"]


def test_linear_missing_output_is_stage_error(tmp_path):
    pipe = load(tmp_path)
    r = FakePipeRunner(pipe, skip=("survey",))
    assert run_pipe(linear_cls()(pipe_cfg(tmp_path, pipe), pipe, runner=r)) == Exit.STAGE_ERROR
    assert r.names() == ["survey"]


def test_linear_from_stage_and_required_input(tmp_path):
    pipe = load(tmp_path)
    with pytest.raises(SystemExit):
        run_pipe(linear_cls()(pipe_cfg(tmp_path, pipe), pipe, runner=FakePipeRunner(pipe)), None, "draw")
    with pytest.raises(SystemExit):
        run_pipe(linear_cls()(pipe_cfg(tmp_path, pipe), pipe, runner=FakePipeRunner(pipe)), None, "nothing")
    needs_input = load(tmp_path, "qa", PICS.replace('input = "optional"', 'input = "required"'))
    cfg = pipe_cfg(tmp_path, needs_input)
    with pytest.raises(SystemExit) as e:
        run_pipe(linear_cls()(cfg, needs_input, runner=FakePipeRunner(needs_input)), None)
    assert "依頼メモ" in str(e.value.code)
    assert not cfg.work_dir.exists()  # 止まるときに空のフォルダを残さない


# ---- AC-08・AC-09: 権限の型と書き込みの範囲 ---------------------------------------

SCOPES = '''
[pipe]
kind = "linear"
label = "権限"

[[stages]]
name = "r"
label = "読む"
output = "01_r.md"
access = "read"
prompt = "x"

[[stages]]
name = "d"
label = "文書"
output = "02_d.md"
access = "docs"
docs_dir = "docs/diagrams"
prompt = "x"

[[stages]]
name = "t"
label = "テスト"
output = "03_t.md"
access = "tests"
bash = true
prompt = "x"

[[stages]]
name = "c"
label = "コード"
output = "04_c.md"
access = "code"
bash = true
prompt = "x"
'''


def scope_guard(tmp_path: Path, stage: str):
    pipe = load(tmp_path, "scopes", SCOPES)
    cfg = pipe_cfg(tmp_path, pipe)
    spec = pipe_specs().build_pipe_specs(cfg, pipe)[stage]

    def check(tool, **inp):
        return check_tool(
            tool, inp, project_dir=cfg.project_dir, can_write=spec.can_write,
            allow_bash=spec.allow_bash, write_scope_hint=spec.write_scope_hint,
            allowed_tools=spec.allowed_tools,
        )

    return check


W = "docs/pipeline/scopes"


def test_access_read_scope(tmp_path):
    check = scope_guard(tmp_path, "r")
    assert check("Write", file_path=f"{W}/01_r.md") is None
    assert check("Write", file_path=f"{W}/02_d.md") is not None
    assert check("Edit", file_path="src/app.py") is not None
    assert check("Write", file_path="docs/diagrams/class.md") is not None


def test_access_docs_scope(tmp_path):
    check = scope_guard(tmp_path, "d")
    assert check("Write", file_path=f"{W}/02_d.md") is None
    assert check("Write", file_path="docs/diagrams/class.md") is None
    assert check("Edit", file_path="src/app.py") is not None
    assert check("Write", file_path="docs/other.md") is not None
    assert check("Write", file_path="../outside.md") is not None


def test_access_tests_and_code_scope(tmp_path):
    t = scope_guard(tmp_path, "t")
    assert t("Write", file_path="tests/test_app.py") is None
    assert t("Write", file_path=f"{W}/03_t.md") is None
    assert t("Edit", file_path="src/app.py") is not None
    c = scope_guard(tmp_path, "c")
    assert c("Edit", file_path="src/app.py") is None
    assert c("Write", file_path=f"{W}/04_c.md") is None
    assert c("Edit", file_path="tests/test_app.py") is not None
    assert c("Write", file_path=f"{W}/01_r.md") is not None


def test_pipe_folder_is_never_writable(tmp_path):
    for stage in ("r", "d", "t", "c"):
        assert scope_guard(tmp_path, stage)("Write", file_path=str(tmp_path / "pipes/pipe-in-scopes/pipe.toml")) is not None


def test_bash_denied_when_not_allowed(tmp_path):
    assert scope_guard(tmp_path, "r")("Bash", command="ls") is not None
    assert scope_guard(tmp_path, "d")("Bash", command="ls") is not None
    assert scope_guard(tmp_path, "t")("Bash", command="pytest -q") is None
    assert scope_guard(tmp_path, "t")("Bash", command="git push origin main") is not None
    assert scope_guard(tmp_path, "c")("Bash", command="curl https://example.com") is not None


def test_protected_paths_apply_to_pipes(tmp_path):
    (tmp_path / "pipeline.toml").write_text('[pipeline]\nprotected_paths = ["src/core/*"]\n', encoding="utf-8")
    c = scope_guard(tmp_path, "c")
    assert c("Edit", file_path="src/core/rules.py") is not None
    assert c("Edit", file_path="src/app.py") is None


@pytest.mark.parametrize("stage", ["r", "d", "t", "c"])
@pytest.mark.parametrize("tool", ["PowerShell", "WebFetch", "WebSearch", "mcp__vercel__create_deployment", "Task", "Agent"])
def test_pipe_stage_disallows_powershell_web_mcp(tmp_path, stage, tool):
    assert scope_guard(tmp_path, stage)(tool, command="ls") is not None
    pipe = load(tmp_path, "scopes", SCOPES)
    spec = pipe_specs().build_pipe_specs(pipe_cfg(tmp_path, pipe), pipe)[stage]
    for name in ("PowerShell", "WebFetch", "WebSearch"):
        assert name in spec.disallowed_tools


def test_stage_settings_reach_spec(tmp_path):
    toml = PICS.replace('access = "read"\n', 'access = "read"\nmodel = "haiku"\nmax_turns = 7\n', 1)
    pipe = load(tmp_path, toml=toml)
    specs = pipe_specs().build_pipe_specs(pipe_cfg(tmp_path, pipe), pipe)
    assert (specs["survey"].model, specs["survey"].max_turns, specs["survey"].label) == ("haiku", 7, "調査")
    assert specs["draw"].max_turns == 100


# ---- AC-14・AC-15: 記録とまとめ ----------------------------------------------------


def test_linear_state_has_pipe_and_stages(tmp_path):
    pipe = load(tmp_path)
    cfg = pipe_cfg(tmp_path, pipe)
    run_pipe(linear_cls()(cfg, pipe, runner=FakePipeRunner(pipe)))
    s = state_at(cfg)
    assert s["pipe"] == "pics"
    assert [(x["name"], x["label"]) for x in s["stages"]] == [("survey", "調査"), ("draw", "図を描く")]
    assert [h["stage"] for h in s["runs"] if "seq" in h] == ["survey", "draw"]
    assert not (tmp_path / "docs/pipeline" / STATE).exists()  # 開発フローの記録の場所には書かない


# ---- 拡張が記録だけで図と成果物の一覧を作れるように、段の成果物と確認の有無も残す（拡張の AC-10） ----


def test_linear_state_stages_have_output_and_review(tmp_path):
    pipe = load(tmp_path)
    cfg = pipe_cfg(tmp_path, pipe)
    run_pipe(linear_cls()(cfg, pipe, runner=FakePipeRunner(pipe)))
    assert state_at(cfg)["stages"] == [
        {"name": "survey", "label": "調査", "output": "01_survey.md", "review": True},
        {"name": "draw", "label": "図を描く", "output": "02_draw.md", "review": False},
    ]


def test_dev_state_stages_have_output_and_review(tmp_path):
    from pipe_in.dev.pipeline import DevPipeline
    from test_pipeline import FakeRunner

    cfg = load_config(tmp_path, None, auto_approve=True)
    asyncio.run(DevPipeline(cfg, runner=FakeRunner(["pass"])).run("ログイン画面", "requirements"))
    s = json.loads((tmp_path / "docs/pipeline" / STATE).read_text(encoding="utf-8"))
    assert [(x["name"], x["output"], x["review"]) for x in s["stages"]] == [
        ("requirements", "01_requirements.md", True),
        ("design", "02_design.md", True),
        ("red", "03_red_tests.md", True),
        ("implement", "04_implementation.md", False),
        ("test", "05_test_report.md", False),
    ]


def test_linear_summary_lists_stage_results(tmp_path):
    pipe = load(tmp_path)
    cfg = pipe_cfg(tmp_path, pipe)
    run_pipe(linear_cls()(cfg, pipe, runner=FakePipeRunner(pipe)))
    text = (cfg.work_dir / SUMMARY).read_text(encoding="utf-8")
    assert "パイプ: pics" in text
    assert "調査" in text and "図を描く" in text
    assert "docs/pipeline/pics/01_survey.md" in text and "docs/pipeline/pics/02_draw.md" in text
    assert "最後の段まで終わりました" in text


# ---- コマンド（pipe-in --pipe） ----------------------------------------------------


def cli_main(*argv: str):
    from pipe_in.cli import main

    return main(list(argv))


def test_cli_pipe_not_found(tmp_path, no_env):
    no_env.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "pipes"))
    with pytest.raises(SystemExit) as e:
        cli_main("--project", str(tmp_path), "--pipe", "nothing")
    assert "見つかりません" in str(e.value.code)
    assert "pipe-in-gen list" in str(e.value.code)


def test_cli_pipe_with_errors_is_refused(tmp_path, no_env):
    no_env.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "pipes"))
    make_pipe(tmp_path / "pipes", "broken", BROKEN["duplicate"][0])
    with pytest.raises(SystemExit) as e:
        cli_main("--project", str(tmp_path), "--pipe", "broken", "--yes")
    assert "重複" in str(e.value.code)


def test_cli_pipe_requires_input(tmp_path, no_env):
    no_env.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "pipes"))
    make_pipe(tmp_path / "pipes", "qa", PICS.replace('input = "optional"', 'input = "required"'))
    with pytest.raises(SystemExit) as e:
        cli_main("--project", str(tmp_path), "--pipe", "qa", "--yes")
    assert "依頼メモ" in str(e.value.code)


def test_pipeline_for_picks_kind_and_settings(tmp_path):
    from pipe_in.cli import pipeline_for
    from pipe_in.dev.pipeline import DevPipeline

    (tmp_path / "pipeline.toml").write_text('[pipeline]\ntest_command = "make test"\n', encoding="utf-8")
    base = load_config(tmp_path, None, auto_approve=True)
    assert isinstance(pipeline_for(base, None), DevPipeline)
    assert pipeline_for(base, None).cfg.test_command == "make test"

    mydev = load(tmp_path, "mydev", '[pipe]\nkind = "dev"\nlabel = "開発"\ntest_command = "pytest -q"\n')
    p = pipeline_for(base, mydev)
    assert isinstance(p, DevPipeline)
    assert p.cfg.test_command == "pytest -q"  # パイプの定義が pipeline.toml より優先
    assert p.cfg.work_dir == base.work_dir  # 開発フローの記録の場所はそのまま
    with_arg = load_config(tmp_path, None, auto_approve=True, test_command="npm test")
    assert pipeline_for(with_arg, mydev, test_cmd_given=True).cfg.test_command == "npm test"  # 引数がいちばん優先

    pics = load(tmp_path)
    lp = pipeline_for(base, pics)
    assert isinstance(lp, linear_cls())
    assert lp.cfg.work_dir == base.work_dir / "pics" and lp.cfg.pipe == "pics"
