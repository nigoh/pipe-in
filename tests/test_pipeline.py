"""SDK を呼ばずに、段の順番・人の確認・差し戻し・書き込み制限を確かめる。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from devpipe import stages as st
from devpipe.checkpoint import Decision, ask_human
from devpipe.config import load_config
from devpipe.guard import check_tool, is_test_path
from devpipe.orchestrator import Exit, Pipeline, ShellResult
from devpipe.runner import StageRun


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
    res = run(Pipeline(make_cfg(tmp_path), runner=r))
    assert res == Exit.PASSED
    assert r.names() == FLOW + ["implement", "test"]
    summary = (tmp_path / "docs/pipeline" / st.SUMMARY).read_text(encoding="utf-8")
    assert "テストまで合格しました" in summary


def test_retry_then_pass(tmp_path):
    r = FakeRunner(["fail", "fail", "pass"])
    res = run(Pipeline(make_cfg(tmp_path), runner=r))
    assert res == Exit.PASSED
    assert r.names() == FLOW + ["implement", "test"] * 3
    # 2回目以降の実装には不合格の内容が渡る
    second_impl = [c for c in r.calls if c[0] == "implement"][1][2]
    assert "AC-01" in second_impl and "2 回目" in second_impl


def test_retry_limit(tmp_path):
    r = FakeRunner(["fail"] * 4)
    res = run(Pipeline(make_cfg(tmp_path), runner=r))
    assert res == Exit.TEST_FAILED
    assert r.names().count("implement") == 4  # 初回 + 差し戻し3回


def test_blocked_stops_without_retry(tmp_path):
    r = FakeRunner(["blocked"])
    res = run(Pipeline(make_cfg(tmp_path), runner=r))
    assert res == Exit.BLOCKED
    assert r.names().count("implement") == 1


def test_human_revise_then_approve(tmp_path):
    answers = iter([Decision("revise", "未確定事項を減らして"), Decision("approve"), Decision("approve"), Decision("approve")])
    r = FakeRunner(["pass"])
    p = Pipeline(make_cfg(tmp_path, auto_approve=False), runner=r, ask=lambda s, d: next(answers))
    assert run(p) == Exit.PASSED
    assert r.names()[:3] == ["requirements", "requirements", "design"]
    # 修正の依頼は同じ会話を再開して渡す
    assert r.calls[1][1] == "s-1" and "未確定事項を減らして" in r.calls[1][2]


def test_human_quit(tmp_path):
    r = FakeRunner([])
    p = Pipeline(make_cfg(tmp_path, auto_approve=False), runner=r, ask=lambda s, d: Decision("quit"))
    assert run(p) == Exit.STOPPED_BY_HUMAN
    assert r.names() == ["requirements"]


def test_command_check_overrides_pass(tmp_path):
    r = FakeRunner(["pass", "pass"])
    # 1つ目はテスト先行のあとの「赤」の確認
    results = iter([ShellResult(1, "1 failed"), ShellResult(1, "1 failed"), ShellResult(0, "ok")])
    p = Pipeline(make_cfg(tmp_path, test_command="pytest -q"), runner=r, shell=lambda c, d, t: next(results))
    assert run(p) == Exit.PASSED
    assert r.names().count("implement") == 2


def test_resume_from_test(tmp_path):
    w = tmp_path / "docs/pipeline"
    w.mkdir(parents=True)
    (w / st.REQUIREMENTS).write_text("x", encoding="utf-8")
    (w / st.DESIGN).write_text("x", encoding="utf-8")
    (w / st.RED).write_text("x", encoding="utf-8")
    r = FakeRunner(["fail", "pass"])
    assert run(Pipeline(make_cfg(tmp_path), runner=r), None, "test") == Exit.PASSED
    assert r.names() == ["test", "implement", "test"]


def test_resume_needs_docs(tmp_path):
    with pytest.raises(SystemExit):
        run(Pipeline(make_cfg(tmp_path), runner=FakeRunner([])), None, "implement")


def test_missing_verdict_is_blocked(tmp_path):
    class NoVerdict(FakeRunner):
        async def __call__(self, spec, prompt, cfg, *, resume, log_name):
            r = await super().__call__(spec, prompt, cfg, resume=resume, log_name=log_name)
            if spec.name == "test":
                r.structured = None
                r.is_error = True
                r.subtype = "error_max_turns"
            return r

    assert run(Pipeline(make_cfg(tmp_path), runner=NoVerdict(["pass"]))) == Exit.BLOCKED


# ---- 書き込み制限 ----------------------------------------------------------


def guard_for(tmp_path, stage):
    cfg = make_cfg(tmp_path)
    spec = st.build_specs(cfg)[stage]

    def check(tool, **inp):
        return check_tool(
            tool, inp, project_dir=cfg.project_dir, can_write=spec.can_write,
            allow_bash=spec.allow_bash, write_scope_hint=spec.write_scope_hint,
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
    run(Pipeline(make_cfg(tmp_path), runner=r))
    assert r.names().index("red") < r.names().index("implement")
    impl_prompt = [c for c in r.calls if c[0] == "implement"][0][2]
    assert st.RED in impl_prompt


def test_red_blocked_stops(tmp_path):
    r = FakeRunner([], reds=[red_verdict("AC-01", status="blocked")])
    assert run(Pipeline(make_cfg(tmp_path), runner=r)) == Exit.BLOCKED
    assert "implement" not in r.names()


def test_red_missing_ac_is_asked_again(tmp_path):
    r = TwoAcRunner(["pass"], reds=[red_verdict("AC-01"), red_verdict("AC-01", "AC-02")])
    assert run(Pipeline(make_cfg(tmp_path), runner=r)) == Exit.PASSED
    reds = [c for c in r.calls if c[0] == "red"]
    assert len(reds) == 2
    assert reds[1][1] is not None and "AC-02" in reds[1][2]  # 同じ会話で、抜けた AC を伝える


def test_red_missing_ac_twice_is_error(tmp_path):
    r = TwoAcRunner([], reds=[red_verdict("AC-01"), red_verdict("AC-01")])
    assert run(Pipeline(make_cfg(tmp_path), runner=r)) == Exit.STAGE_ERROR
    assert "implement" not in r.names()


def test_red_already_green_is_warned(tmp_path):
    r = FakeRunner(["pass"])
    p = Pipeline(make_cfg(tmp_path, test_command="pytest -q"), runner=r, shell=lambda c, d, t: ShellResult(0, "ok"))
    assert run(p) == Exit.PASSED
    summary = (tmp_path / "docs/pipeline" / st.SUMMARY).read_text(encoding="utf-8")
    assert "赤になっていません" in summary


def test_red_is_reviewed_by_human(tmp_path):
    seen: list[str] = []

    def ask(stage, doc):
        seen.append(stage)
        return Decision("approve")

    run(Pipeline(make_cfg(tmp_path, auto_approve=False), runner=FakeRunner(["pass"]), ask=ask))
    assert seen == ["requirements", "design", "red"]


def test_resume_from_implement_needs_red(tmp_path):
    w = tmp_path / "docs/pipeline"
    w.mkdir(parents=True)
    (w / st.REQUIREMENTS).write_text("x", encoding="utf-8")
    (w / st.DESIGN).write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        run(Pipeline(make_cfg(tmp_path), runner=FakeRunner([])), None, "implement")


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
