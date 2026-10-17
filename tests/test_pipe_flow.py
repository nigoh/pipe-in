"""パイプの流れの強化（検証と差し戻し・分岐・並列・Web と MCP・場所で絞る書き込み）を、SDK を呼ばずに確かめる。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pipe_in.engine.checkpoint import Decision
from pipe_in.engine.config import load_config
from pipe_in.engine.guard import check_tool
from pipe_in.engine.pipeline import STATE, SUMMARY, Exit, ShellResult
from pipe_in.engine.runner import StageRun
from pipe_in.pipe import definition as pd
from pipe_in.pipe import specs as ps
from pipe_in.pipe.pipeline import LinearPipeline


def make_pipe(project: Path, toml: str, name: str = "p") -> pd.PipeDef:
    d = project / "pipes" / f"pipe-in-{name}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pipe.toml").write_text(toml, encoding="utf-8")
    return pd.load_pipe(d)


def stage_toml(name: str, extra: str = "", *, access: str = "read") -> str:
    return f'\n[[stages]]\nname = "{name}"\nlabel = "{name}の段"\noutput = "{name}.md"\naccess = "{access}"\nprompt = "{name}をする"\n{extra}'


def pipe_toml(*stages: str, head: str = "") -> str:
    return f'[pipe]\nkind = "linear"\nlabel = "試し"\n{head}' + "".join(stages)


class ScriptedRunner:
    """段ごとに、返す構造化出力を順に決めておける偽物。成果物は必ず書く（skip に入れた段は書かない）。

    並列に動いたかを見るため、同時に動いている段の数の最大を数える。
    """

    def __init__(self, pipe: pd.PipeDef, structured: dict[str, list] | None = None, skip: tuple[str, ...] = ()):
        self.outputs = {s.name: s.output for s in pipe.stages}
        self.structured = {k: list(v) for k, v in (structured or {}).items()}
        self.skip = skip
        self.calls: list[tuple[str, str | None, str]] = []
        self.active = 0
        self.max_active = 0

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append((spec.name, resume, prompt))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        for _ in range(3):
            await asyncio.sleep(0)
        self.active -= 1
        if spec.name not in self.skip:
            (cfg.work_dir / self.outputs[spec.name]).write_text(f"# {spec.name}\n", encoding="utf-8")
        queue = self.structured.get(spec.name)
        data = queue.pop(0) if queue else None
        return StageRun(stage=spec.name, session_id=f"s-{len(self.calls)}", structured=data, cost_usd=0.01, num_turns=1)

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]


def cfg_for(project: Path, pipe: pd.PipeDef, **kw):
    return load_config(project, None, auto_approve=kw.pop("auto_approve", True), **kw).for_pipe(pipe.name, own_work_dir=True)


def run(project: Path, pipe: pd.PipeDef, runner, *, text: str | None = "やること", **kw) -> Exit:
    shell = kw.pop("shell", None)
    ask = kw.pop("ask", None)
    extra = {"shell": shell} if shell else {}
    p = LinearPipeline(cfg_for(project, pipe, **kw), pipe, runner=runner, ask=ask, **extra)
    return asyncio.run(p.run(text))


def state(project: Path, pipe: pd.PipeDef) -> dict:
    return json.loads((project / "docs/pipeline" / pipe.name / STATE).read_text(encoding="utf-8"))


PASS = {"status": "pass", "summary": "よい", "problems": []}


def FAIL(msg: str = "図の矢印が逆") -> dict:
    return {"status": "fail", "summary": "直す点あり", "problems": [msg]}


# ---- FR-01 段の検証と差し戻し --------------------------------------------------


def test_load_check_settings(tmp_path):
    pipe = make_pipe(tmp_path, pipe_toml(
        stage_toml("draw"),
        stage_toml("verify", '[stages.check]\nverdict = true\ncommand = "python -m pytest -q"\non_fail = "draw"\nmax_retries = 3\ntimeout_sec = 60\n'),
    ))
    c = pipe.stages[1].check
    assert (c.verdict, c.command, c.on_fail, c.max_retries, c.timeout_sec) == (True, "python -m pytest -q", "draw", 3, 60)
    assert pipe.stages[0].check is None
    assert pd.check_pipe(pipe, tmp_path) == []


def test_ac01_verdict_fail_goes_back_with_problems(tmp_path):
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("draw"), stage_toml("verify", '[stages.check]\nverdict = true\non_fail = "draw"\n')))
    r = ScriptedRunner(pipe, {"verify": [FAIL("矢印が逆"), PASS]})
    assert run(tmp_path, pipe, r) == Exit.PASSED
    assert r.names() == ["draw", "verify", "draw", "verify"]
    redo = r.calls[2][2]
    assert "前回の検証" in redo and "矢印が逆" in redo
    assert r.calls[2][1] is None  # 差し戻しは新しい会話で
    checks = [h for h in state(tmp_path, pipe)["runs"] if "check" in h]
    assert [c["check"]["status"] for c in checks] == ["fail", "pass"]


def test_ac01_verdict_schema_is_requested(tmp_path):
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("verify", "[stages.check]\nverdict = true\n")))
    spec = ps.build_pipe_specs(cfg_for(tmp_path, pipe), pipe)["verify"]
    props = spec.output_format["schema"]["properties"]
    assert props["status"]["enum"] == ["pass", "fail"]
    assert "problems" in props


def test_ac01_command_check_fails_and_retries_self(tmp_path):
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("build", '[stages.check]\ncommand = "make check"\n')))
    results = iter([ShellResult(2, "E: lint error"), ShellResult(0, "ok")])
    calls: list[str] = []

    def shell(cmd, cwd, timeout):
        calls.append(cmd)
        return next(results)

    r = ScriptedRunner(pipe)
    assert run(tmp_path, pipe, r, shell=shell) == Exit.PASSED
    assert calls == ["make check", "make check"]
    assert r.names() == ["build", "build"]
    assert "lint error" in r.calls[1][2]


def test_ac01_retries_exhausted_is_failed(tmp_path):
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("draw"), stage_toml("verify", '[stages.check]\nverdict = true\non_fail = "draw"\nmax_retries = 1\n')))
    r = ScriptedRunner(pipe, {"verify": [FAIL(), FAIL()]})
    assert run(tmp_path, pipe, r) == Exit.TEST_FAILED
    assert r.names() == ["draw", "verify", "draw", "verify"]
    summary = (tmp_path / "docs/pipeline/p" / SUMMARY).read_text(encoding="utf-8")
    assert "## 検証" in summary and "検証に通りませんでした" in summary


def test_ac01_missing_verdict_counts_as_fail(tmp_path):
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("verify", "[stages.check]\nverdict = true\nmax_retries = 0\n")))
    assert run(tmp_path, pipe, ScriptedRunner(pipe, {"verify": [None]})) == Exit.TEST_FAILED


def test_ac01_check_runs_before_human_review(tmp_path):
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("draw", 'review = true\n[stages.check]\nverdict = true\n')))
    asked: list[str] = []

    def ask(stage, doc):
        asked.append(stage)
        return Decision("approve")

    r = ScriptedRunner(pipe, {"draw": [FAIL(), PASS]})
    assert run(tmp_path, pipe, r, ask=ask, auto_approve=False) == Exit.PASSED
    assert r.names() == ["draw", "draw"]
    assert asked == ["draw"]  # 不合格のものは人に見せない


@pytest.mark.parametrize(
    "extra,word",
    [
        ('[stages.check]\non_fail = "later"\nverdict = true\n', "前の段"),
        ('[stages.check]\non_fail = "nothing"\nverdict = true\n', "nothing"),
        ("[stages.check]\nmax_retries = 2\n", "verdict か command"),
        ('[stages.check]\ncommand = "curl https://example.com"\n', "外部への通信"),
        ("[stages.check]\nverdict = true\nmax_retries = -1\n", "max_retries"),
    ],
)
def test_ac01_check_settings_are_validated(tmp_path, extra, word):
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("first", extra), stage_toml("later")))
    errors = pd.check_pipe(pipe, tmp_path)
    assert any(word in e for e in errors), errors


# ---- FR-02 分岐・飛び先・ループの上限 -------------------------------------------


ROUTED = pipe_toml(
    stage_toml("classify", '[stages.routes]\napi = "api"\nui = "ui"\nnone = "end"\n'),
    stage_toml("api", 'next = "report"\n'),
    stage_toml("ui"),
    stage_toml("report"),
)


def test_ac02_routes_follow_choice(tmp_path):
    pipe = make_pipe(tmp_path, ROUTED)
    r = ScriptedRunner(pipe, {"classify": [{"choice": "api"}]})
    assert run(tmp_path, pipe, r) == Exit.PASSED
    assert r.names() == ["classify", "api", "report"]
    routes = [h for h in state(tmp_path, pipe)["runs"] if "route" in h]
    assert routes == [{"stage": "classify", "route": "api", "next": "api"}]


def test_ac02_route_to_end_stops(tmp_path):
    pipe = make_pipe(tmp_path, ROUTED)
    r = ScriptedRunner(pipe, {"classify": [{"choice": "none"}]})
    assert run(tmp_path, pipe, r) == Exit.PASSED
    assert r.names() == ["classify"]


def test_ac02_routes_schema_lists_choices(tmp_path):
    pipe = make_pipe(tmp_path, ROUTED)
    spec = ps.build_pipe_specs(cfg_for(tmp_path, pipe), pipe)["classify"]
    assert spec.output_format["schema"]["properties"]["choice"]["enum"] == ["api", "ui", "none"]


def test_ac02_bad_choice_is_stage_error(tmp_path):
    pipe = make_pipe(tmp_path, ROUTED)
    assert run(tmp_path, pipe, ScriptedRunner(pipe, {"classify": [{"choice": "db"}]})) == Exit.STAGE_ERROR


def test_ac02_next_end(tmp_path):
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("a", 'next = "end"\n'), stage_toml("b")))
    r = ScriptedRunner(pipe)
    assert run(tmp_path, pipe, r) == Exit.PASSED
    assert r.names() == ["a"]


def test_ac02_max_steps_stops_loops(tmp_path):
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("a", 'next = "b"\n'), stage_toml("b", 'next = "a"\n'), head="max_steps = 5\n"))
    r = ScriptedRunner(pipe)
    assert run(tmp_path, pipe, r) == Exit.STAGE_ERROR
    assert len(r.calls) == 5


def test_ac02_pause_keeps_routed_next(tmp_path):
    toml = ROUTED.replace('[stages.routes]', 'review = true\n[stages.routes]', 1)
    pipe = make_pipe(tmp_path, toml)
    cfg = cfg_for(tmp_path, pipe, auto_approve=False, pause_for_review=True)
    r = ScriptedRunner(pipe, {"classify": [{"choice": "ui"}]})
    assert asyncio.run(LinearPipeline(cfg, pipe, runner=r).run("x")) == Exit.AWAITING_REVIEW
    assert state(tmp_path, pipe)["pending_review"]["next"] == "ui"
    r2 = ScriptedRunner(pipe)
    p = LinearPipeline(cfg_for(tmp_path, pipe, auto_approve=False, pause_for_review=True), pipe, runner=r2)
    assert asyncio.run(p.review(Decision("approve"))) == Exit.PASSED
    assert r2.names() == ["ui", "report"]


@pytest.mark.parametrize(
    "toml,word",
    [
        (pipe_toml(stage_toml("a", 'next = "nothing"\n')), "nothing"),
        (pipe_toml(stage_toml("a", '[stages.routes]\nx = "nothing"\n')), "nothing"),
        (pipe_toml(stage_toml("a", 'next = "end"\n[stages.routes]\nx = "end"\n')), "next と routes"),
        (pipe_toml(stage_toml("a"), head="max_steps = 0\n"), "max_steps"),
    ],
)
def test_ac02_route_settings_are_validated(tmp_path, toml, word):
    errors = pd.check_pipe(make_pipe(tmp_path, toml), tmp_path)
    assert any(word in e for e in errors), errors


# ---- FR-03 並列 -----------------------------------------------------------------


PARALLEL = pipe_toml(
    stage_toml("survey"),
    stage_toml("flow", 'group = "draw"\n'),
    stage_toml("klass", 'group = "draw"\n'),
    stage_toml("report"),
)


def test_ac03_group_runs_together(tmp_path):
    pipe = make_pipe(tmp_path, PARALLEL)
    r = ScriptedRunner(pipe)
    assert run(tmp_path, pipe, r) == Exit.PASSED
    assert r.names()[0] == "survey" and r.names()[-1] == "report"
    assert sorted(r.names()[1:3]) == ["flow", "klass"]
    assert r.max_active == 2
    report_prompt = r.calls[3][2]
    assert "flow.md" in report_prompt and "klass.md" in report_prompt


def test_ac03_group_member_retries_itself(tmp_path):
    toml = PARALLEL.replace('group = "draw"\n', 'group = "draw"\n[stages.check]\nverdict = true\n', 1)
    pipe = make_pipe(tmp_path, toml)
    r = ScriptedRunner(pipe, {"flow": [FAIL(), PASS]})
    assert run(tmp_path, pipe, r) == Exit.PASSED
    assert r.names().count("flow") == 2 and r.names().count("klass") == 1


def test_ac03_group_failure_stops(tmp_path):
    pipe = make_pipe(tmp_path, PARALLEL)
    r = ScriptedRunner(pipe, skip=("klass",))
    assert run(tmp_path, pipe, r) == Exit.STAGE_ERROR
    assert "report" not in r.names()


@pytest.mark.parametrize(
    "toml,word",
    [
        (pipe_toml(stage_toml("a", 'group = "g"\nreview = true\n'), stage_toml("b", 'group = "g"\n')), "group"),
        (pipe_toml(stage_toml("a", 'group = "g"\n'), stage_toml("x"), stage_toml("b", 'group = "g"\n')), "続けて"),
        (pipe_toml(stage_toml("a", 'group = "g"\nnext = "end"\n'), stage_toml("b", 'group = "g"\n')), "group"),
        (pipe_toml(stage_toml("z"), stage_toml("a", 'group = "g"\n[stages.check]\nverdict = true\non_fail = "z"\n'), stage_toml("b", 'group = "g"\n')), "group"),
    ],
)
def test_ac03_group_settings_are_validated(tmp_path, toml, word):
    errors = pd.check_pipe(make_pipe(tmp_path, toml), tmp_path)
    assert any(word in e for e in errors), errors


# ---- FR-04 Web と MCP ------------------------------------------------------------


def guard_of(tmp_path: Path, extra: str, *, access: str = "read"):
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("s", extra, access=access)))
    cfg = cfg_for(tmp_path, pipe)
    spec = ps.build_pipe_specs(cfg, pipe)["s"]

    def check(tool, **inp):
        return check_tool(
            tool, inp, project_dir=cfg.project_dir, can_write=spec.can_write, allow_bash=spec.allow_bash,
            write_scope_hint=spec.write_scope_hint, allowed_tools=spec.allowed_tools, fetch_domains=spec.fetch_domains,
        )

    return check, spec


def test_ac04_web_is_off_by_default(tmp_path):
    check, spec = guard_of(tmp_path, "")
    assert check("WebFetch", url="https://example.com") is not None
    assert check("WebSearch", query="x") is not None
    assert "WebFetch" in spec.disallowed_tools


def test_ac04_web_true_allows_fetch_and_search(tmp_path):
    check, spec = guard_of(tmp_path, "web = true\n")
    assert check("WebFetch", url="https://example.com/a") is None
    assert check("WebSearch", query="x") is None
    assert "WebFetch" not in spec.disallowed_tools
    assert check("PowerShell", command="ls") is not None  # ほかの道は開かない
    assert check("Task", prompt="x") is not None


def test_ac04_web_domains_limit_fetch(tmp_path):
    check, _ = guard_of(tmp_path, 'web = ["docs.python.org"]\n')
    assert check("WebFetch", url="https://docs.python.org/3/library/") is None
    assert check("WebFetch", url="https://sub.docs.python.org/x") is None
    assert check("WebFetch", url="https://evil.example.com/?q=docs.python.org") is not None
    assert check("WebFetch", url="https://docs.python.org.evil.com/") is not None
    assert check("WebSearch", query="x") is not None


def test_ac04_mcp_allows_only_listed(tmp_path):
    check, spec = guard_of(tmp_path, 'mcp = ["mcp__jira__get_issue", "mcp__figma__*"]\n')
    assert check("mcp__jira__get_issue", key="A-1") is None
    assert check("mcp__jira__create_issue", key="A-1") is not None
    assert check("mcp__figma__get_screenshot") is None
    assert check("mcp__figmax__get") is not None
    assert check("mcp__vercel__create_deployment") is not None
    assert check("PowerShell", command="ls") is not None
    assert "mcp__figma" in spec.allowed_tools  # SDK にはサーバー単位で渡す


def test_ac04_mcp_off_by_default(tmp_path):
    check, _ = guard_of(tmp_path, "")
    assert check("mcp__jira__get_issue") is not None


@pytest.mark.parametrize(
    "extra,word",
    [
        ('mcp = ["*"]\n', "mcp"),
        ('mcp = ["mcp__*"]\n', "mcp"),
        ('mcp = ["Bash"]\n', "mcp"),
        ('web = ["https://example.com/path"]\n', "ドメイン"),
        ('web = "yes"\n', "web"),
    ],
)
def test_ac04_web_and_mcp_settings_are_validated(tmp_path, extra, word):
    errors = pd.check_pipe(make_pipe(tmp_path, pipe_toml(stage_toml("s", extra))), tmp_path)
    assert any(word in e for e in errors), errors


# ---- FR-05 場所で絞る書き込み -------------------------------------------------------


def test_ac05_writes_narrows_code_scope(tmp_path):
    check, _ = guard_of(tmp_path, 'writes = ["src/api/**"]\n', access="code")
    assert check("Edit", file_path="src/api/users.py") is None
    assert check("Edit", file_path="src/api/v1/items.py") is None
    assert check("Edit", file_path="src/web/page.py") is not None
    assert check("Edit", file_path="tests/test_api.py") is not None  # 型（code）の制限も残る
    assert check("Write", file_path="docs/pipeline/p/s.md") is None  # 自分の成果物はいつも書ける


def test_ac05_writes_narrows_docs_scope(tmp_path):
    check, _ = guard_of(tmp_path, 'docs_dir = "docs"\nwrites = ["docs/adr/*.md"]\n', access="docs")
    assert check("Write", file_path="docs/adr/0001.md") is None
    assert check("Write", file_path="docs/guide.md") is not None


@pytest.mark.parametrize(
    "extra,access,word",
    [
        ('writes = ["../x/**"]\n', "code", "writes"),
        ('writes = ["/etc/*"]\n', "code", "writes"),
        ('writes = ["src/**"]\n', "read", "read"),
    ],
)
def test_ac05_writes_settings_are_validated(tmp_path, extra, access, word):
    errors = pd.check_pipe(make_pipe(tmp_path, pipe_toml(stage_toml("s", extra, access=access))), tmp_path)
    assert any(word in e for e in errors), errors


# ---- 本物で流して見つかったこと：構造化出力の道具を止めない ----------------------------


def test_structured_output_tool_is_never_denied(tmp_path):
    """SDK は構造化出力を StructuredOutput という道具で返す。止めると判定・分岐・設計が返らない。"""
    check, _ = guard_of(tmp_path, "[stages.check]\nverdict = true\n")
    assert check("StructuredOutput", status="pass", summary="x", problems=[]) is None
    from pipe_in.dev import specs as dev_specs

    cfg = load_config(tmp_path, None, auto_approve=True)
    for name, spec in dev_specs.build_specs(cfg).items():
        reason = check_tool(
            "StructuredOutput", {"status": "red"}, project_dir=cfg.project_dir, can_write=spec.can_write,
            allow_bash=spec.allow_bash, write_scope_hint=spec.write_scope_hint, allowed_tools=spec.allowed_tools,
        )
        assert reason is None, name


# ---- D0001-AC-14: pipe-in --pipe は対象の .pipe-in/pipes/ から読む ---------------------------


def test_cli_loads_pipe_from_project(tmp_path, monkeypatch):
    """D0001-AC-14・D0006-AC-05: pipe-in --pipe は対象の .pipe-in/pipes/pipe-in-<名前>/ から読む。"""
    from pipe_in import cli

    monkeypatch.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "shared"))
    project = tmp_path / "app"
    d = project / ".pipe-in" / "pipes" / "pipe-in-local"
    d.mkdir(parents=True)
    (d / "pipe.toml").write_text(pipe_toml(stage_toml("only")), encoding="utf-8")
    pipe = cli._load_pipe("local", project)
    assert pipe.name == "local" and pipe.dir == d
    with pytest.raises(SystemExit):
        cli._load_pipe("nothing", project)
