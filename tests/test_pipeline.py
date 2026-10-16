"""SDK を呼ばずに、段の順番・人の確認・差し戻し・書き込み制限を確かめる。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from devpipe.dev import specs as st
from devpipe.engine.checkpoint import Decision, ask_human
from devpipe.engine.config import load_config
from devpipe.engine.guard import check_tool, is_test_path
from devpipe.dev.pipeline import DevPipeline
from devpipe.engine.pipeline import Exit, ShellResult
from devpipe.engine.runner import StageRun


class FakeRunner:
    """各段の代わりに文書を書き、決められた判定を返す。"""

    def __init__(self, verdicts: list[str], reds: list[dict] | None = None):
        self.verdicts = list(verdicts)
        self.reds = list(reds or [])
        self.calls: list[tuple[str, str | None, str]] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append((spec.name, resume, prompt))
        w = cfg.work_dir
        run = StageRun(stage=spec.name, session_id=f"s-{len(self.calls)}", cost_usd=0.01, num_turns=3)
        if spec.name == "requirements":
            (w / st.REQUIREMENTS).write_text("# 要件定義書\nAC-01\n", encoding="utf-8")
        elif spec.name == "design":
            (w / st.DESIGN).write_text("# 設計書\n", encoding="utf-8")
        elif spec.name == "red":
            (w / st.RED).write_text("# テスト先行\n", encoding="utf-8")
            run.structured = self.reds.pop(0) if self.reds else red_verdict("AC-01")
        elif spec.name == "implement":
            (w / st.IMPLEMENTATION).write_text("## 実装\n", encoding="utf-8")
        elif spec.name == "test":
            status = self.verdicts.pop(0)
            run.structured = {
                "status": status,
                "summary": f"{status} です",
                "failures": [] if status == "pass" else [{"criterion": "AC-01", "detail": "期待と違う"}],
                "commands": ["pytest -q"],
            }
        return run

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]


def red_verdict(*acs: str, status: str = "red") -> dict:
    return {
        "status": status,
        "summary": f"{status} です",
        "tests": [{"criterion": a, "test": f"test_{a}"} for a in acs],
        "commands": ["pytest -q"],
    }


FLOW = ["requirements", "design", "red"]


def make_cfg(tmp_path: Path, **kw):
    return load_config(tmp_path, None, auto_approve=kw.pop("auto_approve", True), **kw)


def run(p: Pipeline, text: str | None = "ログイン画面を作る", frm: str = "requirements") -> Exit:
    return asyncio.run(p.run(text, frm))


def test_all_pass(tmp_path):
    r = FakeRunner(["pass"])
    res = run(DevPipeline(make_cfg(tmp_path), runner=r))
    assert res == Exit.PASSED
    assert r.names() == FLOW + ["implement", "test"]
    summary = (tmp_path / "docs/pipeline" / st.SUMMARY).read_text(encoding="utf-8")
    assert "テストまで合格しました" in summary


def test_retry_then_pass(tmp_path):
    r = FakeRunner(["fail", "fail", "pass"])
    res = run(DevPipeline(make_cfg(tmp_path), runner=r))
    assert res == Exit.PASSED
    assert r.names() == FLOW + ["implement", "test"] * 3
    # 2回目以降の実装には不合格の内容が渡る
    second_impl = [c for c in r.calls if c[0] == "implement"][1][2]
    assert "AC-01" in second_impl and "2 回目" in second_impl


def test_retry_limit(tmp_path):
    r = FakeRunner(["fail"] * 4)
    res = run(DevPipeline(make_cfg(tmp_path), runner=r))
    assert res == Exit.TEST_FAILED
    assert r.names().count("implement") == 4  # 初回 + 差し戻し3回


def test_blocked_stops_without_retry(tmp_path):
    r = FakeRunner(["blocked"])
    res = run(DevPipeline(make_cfg(tmp_path), runner=r))
    assert res == Exit.BLOCKED
    assert r.names().count("implement") == 1


def test_human_revise_then_approve(tmp_path):
    answers = iter([Decision("revise", "未確定事項を減らして"), Decision("approve"), Decision("approve"), Decision("approve")])
    r = FakeRunner(["pass"])
    p = DevPipeline(make_cfg(tmp_path, auto_approve=False), runner=r, ask=lambda s, d: next(answers))
    assert run(p) == Exit.PASSED
    assert r.names()[:3] == ["requirements", "requirements", "design"]
    # 修正の依頼は同じ会話を再開して渡す
    assert r.calls[1][1] == "s-1" and "未確定事項を減らして" in r.calls[1][2]


def test_human_quit(tmp_path):
    r = FakeRunner([])
    p = DevPipeline(make_cfg(tmp_path, auto_approve=False), runner=r, ask=lambda s, d: Decision("quit"))
    assert run(p) == Exit.STOPPED_BY_HUMAN
    assert r.names() == ["requirements"]


def test_command_check_overrides_pass(tmp_path):
    r = FakeRunner(["pass", "pass"])
    # 1つ目はテスト先行のあとの「赤」の確認
    results = iter([ShellResult(1, "1 failed"), ShellResult(1, "1 failed"), ShellResult(0, "ok")])
    p = DevPipeline(make_cfg(tmp_path, test_command="pytest -q"), runner=r, shell=lambda c, d, t: next(results))
    assert run(p) == Exit.PASSED
    assert r.names().count("implement") == 2


def test_resume_from_test(tmp_path):
    w = tmp_path / "docs/pipeline"
    w.mkdir(parents=True)
    (w / st.REQUIREMENTS).write_text("x", encoding="utf-8")
    (w / st.DESIGN).write_text("x", encoding="utf-8")
    (w / st.RED).write_text("x", encoding="utf-8")
    r = FakeRunner(["fail", "pass"])
    assert run(DevPipeline(make_cfg(tmp_path), runner=r), None, "test") == Exit.PASSED
    assert r.names() == ["test", "implement", "test"]


def test_resume_needs_docs(tmp_path):
    with pytest.raises(SystemExit):
        run(DevPipeline(make_cfg(tmp_path), runner=FakeRunner([])), None, "implement")


def test_missing_verdict_is_blocked(tmp_path):
    class NoVerdict(FakeRunner):
        async def __call__(self, spec, prompt, cfg, *, resume, log_name):
            r = await super().__call__(spec, prompt, cfg, resume=resume, log_name=log_name)
            if spec.name == "test":
                r.structured = None
                r.is_error = True
                r.subtype = "error_max_turns"
            return r

    assert run(DevPipeline(make_cfg(tmp_path), runner=NoVerdict(["pass"]))) == Exit.BLOCKED


# ---- 書き込み制限 ----------------------------------------------------------


def guard_for(tmp_path, stage):
    cfg = make_cfg(tmp_path)
    spec = st.build_specs(cfg)[stage]

    def check(tool, **inp):
        return check_tool(
            tool, inp, project_dir=cfg.project_dir, can_write=spec.can_write,
            allow_bash=spec.allow_bash, write_scope_hint=spec.write_scope_hint,
            allowed_tools=spec.allowed_tools,
        )

    return check


def test_requirements_can_only_write_its_doc(tmp_path):
    check = guard_for(tmp_path, "requirements")
    assert check("Write", file_path="docs/pipeline/01_requirements.md") is None
    assert check("Write", file_path=str(tmp_path / "docs/pipeline/01_requirements.md")) is None
    assert check("Edit", file_path="src/app.py") is not None
    assert check("Write", file_path="docs/pipeline/02_design.md") is not None
    assert check("Bash", command="ls") is not None


def test_implement_cannot_touch_tests(tmp_path):
    check = guard_for(tmp_path, "implement")
    assert check("Edit", file_path="src/app.py") is None
    assert check("Write", file_path="docs/pipeline/04_implementation.md") is None
    assert check("Edit", file_path="tests/test_app.py") is not None
    assert check("Edit", file_path="src/app.test.ts") is not None
    assert check("Edit", file_path="docs/pipeline/05_test_report.md") is not None
    assert check("Edit", file_path="docs/pipeline/03_red_tests.md") is not None
    assert check("Write", file_path="/etc/passwd") is not None
    assert check("Write", file_path="../outside.py") is not None


def test_test_stage_cannot_touch_product_code(tmp_path):
    check = guard_for(tmp_path, "test")
    assert check("Write", file_path="tests/test_login.py") is None
    assert check("Write", file_path="docs/pipeline/05_test_report.md") is None
    assert check("Edit", file_path="src/login.py") is not None


@pytest.mark.parametrize(
    "cmd",
    ["git push origin main", "rm -rf build", "sudo apt install x", "curl https://example.com", "git checkout main"],
)
def test_dangerous_bash_denied(tmp_path, cmd):
    assert guard_for(tmp_path, "implement")("Bash", command=cmd) is not None


@pytest.mark.parametrize("cmd", ["pytest -q", "npm test", "rm build/tmp.txt", "git status", "pip install pytest"])
def test_normal_bash_allowed(tmp_path, cmd):
    assert guard_for(tmp_path, "implement")("Bash", command=cmd) is None


def test_is_test_path():
    assert is_test_path("tests/unit/test_a.py")
    assert is_test_path("src/login.spec.ts")
    assert is_test_path("pkg/conftest.py")
    assert not is_test_path("src/latest_news.py")
    assert not is_test_path("src/contest.py")


def test_checkpoint_reads_feedback(tmp_path):
    doc = tmp_path / "d.md"
    doc.write_text("# 要件\n", encoding="utf-8")
    inputs = iter(["r", "AC-02 を追加", "", ])
    d = ask_human("requirements", doc, read=lambda prompt: next(inputs))
    assert d.action == "revise" and d.feedback == "AC-02 を追加"


def test_checkpoint_eof_quits(tmp_path):
    def eof(prompt):
        raise EOFError

    assert ask_human("design", tmp_path / "x.md", read=eof).action == "quit"


# ---- テスト先行（TDD の赤） --------------------------------------------------


class TwoAcRunner(FakeRunner):
    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        r = await super().__call__(spec, prompt, cfg, resume=resume, log_name=log_name)
        if spec.name == "requirements":
            (cfg.work_dir / st.REQUIREMENTS).write_text("| AC-01 | ... |\n| AC-02 | ... |\n", encoding="utf-8")
        return r


def test_red_comes_before_implement(tmp_path):
    r = FakeRunner(["pass"])
    run(DevPipeline(make_cfg(tmp_path), runner=r))
    assert r.names().index("red") < r.names().index("implement")
    impl_prompt = [c for c in r.calls if c[0] == "implement"][0][2]
    assert st.RED in impl_prompt


def test_red_blocked_stops(tmp_path):
    r = FakeRunner([], reds=[red_verdict("AC-01", status="blocked")])
    assert run(DevPipeline(make_cfg(tmp_path), runner=r)) == Exit.BLOCKED
    assert "implement" not in r.names()


def test_red_missing_ac_is_asked_again(tmp_path):
    r = TwoAcRunner(["pass"], reds=[red_verdict("AC-01"), red_verdict("AC-01", "AC-02")])
    assert run(DevPipeline(make_cfg(tmp_path), runner=r)) == Exit.PASSED
    reds = [c for c in r.calls if c[0] == "red"]
    assert len(reds) == 2
    assert reds[1][1] is not None and "AC-02" in reds[1][2]  # 同じ会話で、抜けた AC を伝える


def test_red_missing_ac_twice_is_error(tmp_path):
    r = TwoAcRunner([], reds=[red_verdict("AC-01"), red_verdict("AC-01")])
    assert run(DevPipeline(make_cfg(tmp_path), runner=r)) == Exit.STAGE_ERROR
    assert "implement" not in r.names()


def test_red_already_green_is_warned(tmp_path):
    r = FakeRunner(["pass"])
    p = DevPipeline(make_cfg(tmp_path, test_command="pytest -q"), runner=r, shell=lambda c, d, t: ShellResult(0, "ok"))
    assert run(p) == Exit.PASSED
    summary = (tmp_path / "docs/pipeline" / st.SUMMARY).read_text(encoding="utf-8")
    assert "赤になっていません" in summary


def test_red_is_reviewed_by_human(tmp_path):
    seen: list[str] = []

    def ask(stage, doc):
        seen.append(stage)
        return Decision("approve")

    run(DevPipeline(make_cfg(tmp_path, auto_approve=False), runner=FakeRunner(["pass"]), ask=ask))
    assert seen == ["requirements", "design", "red"]


def test_resume_from_implement_needs_red(tmp_path):
    w = tmp_path / "docs/pipeline"
    w.mkdir(parents=True)
    (w / st.REQUIREMENTS).write_text("x", encoding="utf-8")
    (w / st.DESIGN).write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        run(DevPipeline(make_cfg(tmp_path), runner=FakeRunner([])), None, "implement")


def test_red_stage_writes_only_tests(tmp_path):
    check = guard_for(tmp_path, "red")
    assert check("Write", file_path="tests/test_login.py") is None
    assert check("Write", file_path="src/login.test.ts") is None
    assert check("Write", file_path="docs/pipeline/03_red_tests.md") is None
    assert check("Edit", file_path="src/login.py") is not None
    assert check("Edit", file_path="docs/pipeline/04_implementation.md") is not None


# ---- ドメインの文書・設定 ---------------------------------------------------


def test_design_can_write_domain_docs(tmp_path):
    (tmp_path / "pipeline.toml").write_text('[pipeline]\ndomain_dir = "docs/domain"\n', encoding="utf-8")
    cfg = load_config(tmp_path)
    specs = st.build_specs(cfg)
    assert specs["design"].can_write("docs/domain/用語集.md")
    assert not specs["requirements"].can_write("docs/domain/用語集.md")
    assert not specs["implement"].can_write("docs/domain/用語集.md")
    assert "docs/domain" in st.design_prompt(cfg) and "docs/domain" in st.requirements_prompt(cfg)


def test_no_domain_dir_by_default(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.domain_dir is None
    assert not st.build_specs(cfg)["design"].can_write("docs/domain/用語集.md")


def test_setting_sources(tmp_path):
    (tmp_path / "pipeline.toml").write_text('[pipeline]\nsetting_sources = ["project"]\n', encoding="utf-8")
    assert load_config(tmp_path).setting_sources == ["project"]
    assert load_config(tmp_path.parent).setting_sources is None


def test_protected_paths_are_read_only_for_every_stage(tmp_path):
    (tmp_path / "pipeline.toml").write_text(
        '[pipeline]\nprotected_paths = ["src/architecture.test.ts", "rules/**"]\n', encoding="utf-8"
    )
    specs = st.build_specs(load_config(tmp_path))
    for name, spec in specs.items():
        assert not spec.can_write("src/architecture.test.ts"), name
        assert not spec.can_write("rules/a/b.md"), name
    assert specs["red"].can_write("src/other.test.ts")


# ---- 段ごとに許したツール以外は止める ------------------------------------------

ALL_STAGES = ["requirements", "design", "red", "implement", "test"]


@pytest.mark.parametrize("stage", ALL_STAGES)
@pytest.mark.parametrize(
    "tool",
    ["PowerShell", "mcp__vercel__create_deployment", "mcp__playwright__browser_navigate", "Task", "Agent",
     "Workflow", "CronCreate", "RemoteTrigger", "SendMessage", "EnterWorktree", "WebFetch", "WebSearch"],
)
def test_unlisted_tools_are_denied(tmp_path, stage, tool):
    assert guard_for(tmp_path, stage)(tool, command="git push") is not None


@pytest.mark.parametrize("stage", ALL_STAGES)
@pytest.mark.parametrize("tool", ["Read", "Glob", "Grep", "Skill", "ToolSearch", "TodoWrite"])
def test_read_only_helpers_are_allowed(tmp_path, stage, tool):
    assert guard_for(tmp_path, stage)(tool, file_path="src/app.py", pattern="x") is None


@pytest.mark.parametrize("stage", ALL_STAGES)
def test_powershell_is_disallowed_up_front(tmp_path, stage):
    assert "PowerShell" in st.build_specs(make_cfg(tmp_path))[stage].disallowed_tools


def test_guard_hook_denies_powershell(tmp_path):
    from devpipe.engine.guard import make_guard_hook

    cfg = make_cfg(tmp_path)
    spec = st.build_specs(cfg)["implement"]
    denied: list[str] = []
    hook = make_guard_hook(
        project_dir=cfg.project_dir, can_write=spec.can_write, allow_bash=spec.allow_bash,
        write_scope_hint=spec.write_scope_hint, allowed_tools=spec.allowed_tools,
        on_deny=lambda t, r: denied.append(t),
    )
    out = asyncio.run(hook({"tool_name": "PowerShell", "tool_input": {"command": "git push"}}, None, None))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert denied == ["PowerShell"]


# ---- まとめに費用・トークン・環境・利用枠を出す --------------------------------


def test_summary_has_usage_sections(tmp_path):
    from devpipe.usage.metrics import StageMetrics

    class WithMetrics(FakeRunner):
        async def __call__(self, spec, prompt, cfg, *, resume, log_name):
            r = await super().__call__(spec, prompt, cfg, resume=resume, log_name=log_name)
            m = StageMetrics()
            m.feed({"_type": "SystemMessage", "subtype": "init",
                    "data": {"model": "claude-opus-5-5", "claude_code_version": "2.1.301", "apiKeySource": "none"}})
            m.feed({"_type": "RateLimitEvent", "rate_limit_info": {"raw": {"unifiedWindows": {
                "five_hour": {"utilization": 0.01 * len(self.calls), "resetsAt": 1792170000}}}}})
            m.feed({"_type": "ResultMessage", "duration_api_ms": 1000, "usage": {
                "input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 900,
                "output_tokens": 50, "output_tokens_details": {"thinking_tokens": 5}},
                "model_usage": {"claude-opus-5-5": {"inputTokens": 10, "outputTokens": 50, "costUSD": 0.01}}})
            r.metrics = m
            return r

    assert run(DevPipeline(make_cfg(tmp_path), runner=WithMetrics(["pass"]))) == Exit.PASSED
    summary = (tmp_path / "docs/pipeline" / st.SUMMARY).read_text(encoding="utf-8")
    for heading in ("## トークンの内訳", "## モデル別", "## 環境", "## 利用枠"):
        assert heading in summary, heading
    assert "claude-opus-5-5" in summary and "2.1.301" in summary
    assert "89.1%" in summary  # キャッシュの再利用率 900 / (10 + 100 + 900)
    assert "1% → 5%" in summary  # 5時間枠の使用率の推移（1段目の始め → 最後の段の終わり）
    state = (tmp_path / "docs/pipeline" / st.STATE).read_text(encoding="utf-8")
    assert '"metrics"' in state and '"usage_summary"' in state


def test_summary_without_metrics_still_works(tmp_path):
    assert run(DevPipeline(make_cfg(tmp_path), runner=FakeRunner(["pass"]))) == Exit.PASSED
    summary = (tmp_path / "docs/pipeline" / st.SUMMARY).read_text(encoding="utf-8")
    assert "テストまで合格しました" in summary and "## トークンの内訳" not in summary


def test_usage_report_mentions_reset():
    from devpipe.dev.specs import STAGE_LABELS
    from devpipe.usage.report import usage_sections

    metrics = {"tokens": {"output": 1}, "rate_limits": {
        "five_hour": {"first": 0.12, "last": 0.02, "peak": 0.13, "reset_seen": True, "resets_at": None}}}
    text = "\n".join(usage_sections([{"seq": 1, "stage": "design", "metrics": metrics}], STAGE_LABELS))
    assert "12% → 2%" in text and "途中で枠が戻りました" in text and "最大 13%" in text


# ---- 確認で止めて、あとから答える（チャットから動かすとき） ---------------


def paused_cfg(tmp_path: Path, **kw):
    return load_config(tmp_path, None, pause_for_review=True, **kw)


def state_of(tmp_path: Path) -> dict:
    import json

    return json.loads((tmp_path / "docs/pipeline" / st.STATE).read_text(encoding="utf-8"))


def review(tmp_path: Path, runner, decision: Decision, **kw) -> Exit:
    return asyncio.run(DevPipeline(paused_cfg(tmp_path, **kw), runner=runner).review(decision))


def test_pause_stops_at_first_review(tmp_path):
    r = FakeRunner([])
    assert run(DevPipeline(paused_cfg(tmp_path), runner=r)) == Exit.AWAITING_REVIEW
    assert r.names() == ["requirements"]
    s = state_of(tmp_path)
    assert s["final"] is None  # 終わってはいない（VSCode のパネルでは「次を待っている」）
    assert s["pending_review"]["stage"] == "requirements"
    assert s["pending_review"]["session_id"] == "s-1"
    assert s["pending_review"]["doc"].endswith(st.REQUIREMENTS)


def test_review_approve_goes_to_next_review(tmp_path):
    run(DevPipeline(paused_cfg(tmp_path), runner=FakeRunner([])))
    r = FakeRunner([])
    assert review(tmp_path, r, Decision("approve")) == Exit.AWAITING_REVIEW
    assert r.names() == ["design"]
    s = state_of(tmp_path)
    assert s["pending_review"]["stage"] == "design"
    # 前の呼び出しの記録は消えずに続く
    assert [h["stage"] for h in s["runs"] if "seq" in h] == ["requirements", "design"]
    assert [h["seq"] for h in s["runs"] if "seq" in h] == [1, 2]
    assert {"stage": "requirements", "review": "approved"} in s["runs"]


def test_review_revise_resumes_same_session(tmp_path):
    run(DevPipeline(paused_cfg(tmp_path), runner=FakeRunner([])))
    r = FakeRunner([])
    assert review(tmp_path, r, Decision("revise", "AC を細かくして")) == Exit.AWAITING_REVIEW
    assert r.names() == ["requirements"]
    assert r.calls[0][1] == "s-1" and "AC を細かくして" in r.calls[0][2]
    s = state_of(tmp_path)
    assert s["pending_review"]["stage"] == "requirements"
    assert {"stage": "requirements", "review": "revise", "feedback": "AC を細かくして"} in s["runs"]


def test_review_quit_stops(tmp_path):
    run(DevPipeline(paused_cfg(tmp_path), runner=FakeRunner([])))
    r = FakeRunner([])
    assert review(tmp_path, r, Decision("quit")) == Exit.STOPPED_BY_HUMAN
    assert r.names() == []
    s = state_of(tmp_path)
    assert s["final"] == "STOPPED_BY_HUMAN"
    assert s.get("pending_review") is None


def test_review_through_to_pass(tmp_path):
    run(DevPipeline(paused_cfg(tmp_path), runner=FakeRunner([])))
    assert review(tmp_path, FakeRunner([]), Decision("approve")) == Exit.AWAITING_REVIEW  # → 設計
    assert review(tmp_path, FakeRunner([]), Decision("approve")) == Exit.AWAITING_REVIEW  # → テスト先行
    assert state_of(tmp_path)["pending_review"]["stage"] == "red"
    r = FakeRunner(["fail", "pass"])
    assert review(tmp_path, r, Decision("approve")) == Exit.PASSED
    assert r.names() == ["implement", "test", "implement", "test"]
    s = state_of(tmp_path)
    assert s["final"] == "PASSED" and s.get("pending_review") is None
    assert round(s["total_cost_usd"], 2) == 0.07  # 3 回の呼び出しをまたいだ合計
    summary = (tmp_path / "docs/pipeline" / st.SUMMARY).read_text(encoding="utf-8")
    assert "| 7 | 検証" in summary


def test_red_warning_survives_pause(tmp_path):
    shell = lambda c, d, t: ShellResult(0, "ok")  # noqa: E731
    run(DevPipeline(paused_cfg(tmp_path, test_command="pytest -q"), runner=FakeRunner([]), shell=shell))
    review(tmp_path, FakeRunner([]), Decision("approve"))
    p = DevPipeline(paused_cfg(tmp_path, test_command="pytest -q"), runner=FakeRunner([]), shell=shell)
    assert asyncio.run(p.review(Decision("approve"))) == Exit.AWAITING_REVIEW  # テスト先行で止まる
    assert any("赤になっていません" in w for w in state_of(tmp_path)["warnings"])


def test_review_without_pending_is_error(tmp_path):
    with pytest.raises(SystemExit):
        review(tmp_path, FakeRunner([]), Decision("approve"))
    run(DevPipeline(make_cfg(tmp_path), runner=FakeRunner(["pass"])))  # 最後まで流れた記録
    with pytest.raises(SystemExit):
        review(tmp_path, FakeRunner([]), Decision("approve"))


def test_cli_review_needs_feedback_for_revise(tmp_path):
    from devpipe.cli import main

    with pytest.raises(SystemExit):
        main(["--project", str(tmp_path), "--review", "revise"])


@pytest.mark.parametrize(
    "argv",
    [
        ["--review", "approve", "--from", "design"],
        ["--review", "approve", "--yes"],
        ["--feedback", "x"],
        ["--pause", "--yes", "--text", "x"],
    ],
)
def test_cli_rejects_mixed_review_args(tmp_path, argv):
    from devpipe.cli import main

    with pytest.raises(SystemExit) as e:
        main(["--project", str(tmp_path), *argv])
    assert isinstance(e.value.code, str)  # 引数の誤りの説明（argparse の 2 ではない）


def test_cli_review_without_pending_explains(tmp_path):
    from devpipe.cli import main

    with pytest.raises(SystemExit) as e:
        main(["--project", str(tmp_path), "--review", "approve"])
    assert "確認待ち" in str(e.value.code)
