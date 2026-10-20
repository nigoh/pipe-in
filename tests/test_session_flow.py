"""D0019-AC-45：セッション名（state.json の name）が、開発フローとパイプの両方で、始めるとき・確認待ちからの再開・途中からの再開をまたいで残る。

SDK は呼ばない（FakeRunner・ScriptedRunner を使う）。pipe-in のコマンドは、流し方（runner）だけを差し替えて通す。
name の項目はまだ無いので、これらは「name が書かれない」ことで落ちる（--name は未知の引数で落ちる）。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pipe_in import cli
from pipe_in.dev import specs as st
from pipe_in.dev.pipeline import DevPipeline
from pipe_in.engine.checkpoint import Decision
from pipe_in.engine.config import load_config
from pipe_in.engine.pipeline import Exit
from pipe_in.pipe.pipeline import LinearPipeline
from test_pipe_flow import ScriptedRunner, cfg_for, make_pipe, pipe_toml, stage_toml
from test_pipeline import FakeRunner


def dev_state(project: Path) -> dict:
    return json.loads((project / "docs" / "pipeline" / st.STATE).read_text(encoding="utf-8"))


def pipe_state(project: Path) -> dict:
    return json.loads((project / "docs" / "pipeline" / "p" / "state.json").read_text(encoding="utf-8"))


def dev_cfg(project: Path, **kw):
    return load_config(project, None, auto_approve=kw.pop("auto_approve", True), **kw)


def dev_run(p: DevPipeline, text: str | None = "ログイン画面を作る", frm: str = "requirements") -> Exit:
    return asyncio.run(p.run(text, frm))


def dev_review(project: Path, decision: Decision) -> Exit:
    p = DevPipeline(load_config(project, None, pause_for_review=True), runner=FakeRunner([]))
    return asyncio.run(p.review(decision))


def drop_name(state_path: Path) -> None:
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data.pop("name", None)
    state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---- 開発フロー --------------------------------------------------------------------------------


def test_d0019_ac45_dev_pipeline_writes_the_given_name(tmp_path):
    """D0019-AC-45: 開発フローは、pipeline.name に入れた名前を state.json の name に書く（要件メモの最初の行より優先）。"""
    p = DevPipeline(dev_cfg(tmp_path), runner=FakeRunner(["pass"]))
    p.name = "X"
    assert dev_run(p, "# 別の題\n本文") == Exit.PASSED
    assert dev_state(tmp_path)["name"] == "X"


def test_d0019_ac45_dev_pipeline_name_from_memo_by_default(tmp_path):
    """D0019-AC-45: 名前を付けなければ、要件メモの最初の行から作る（見出しの印を取る）。"""
    p = DevPipeline(dev_cfg(tmp_path), runner=FakeRunner(["pass"]))
    assert dev_run(p, "\n## 仕様の QA を回す\n2行目") == Exit.PASSED
    assert dev_state(tmp_path)["name"] == "仕様の QA を回す"


def test_d0019_ac45_dev_pipeline_writes_no_name_when_nothing_to_make_it_from(tmp_path):
    """D0019-AC-45: 付けた名前も、取れる名前も無いとき（見出しの印だけのメモ）は、name を書かない。"""
    p = DevPipeline(dev_cfg(tmp_path), runner=FakeRunner(["pass"]))
    assert dev_run(p, "###") == Exit.PASSED
    assert "name" not in dev_state(tmp_path)


def test_d0019_ac45_dev_name_is_in_state_while_paused_too(tmp_path):
    """D0019-AC-45: 確認待ちで止まった記録（途中の保存）にも name が入っている。"""
    p = DevPipeline(dev_cfg(tmp_path, auto_approve=False, pause_for_review=True), runner=FakeRunner([]))
    p.name = "X"
    assert dev_run(p) == Exit.AWAITING_REVIEW
    assert dev_state(tmp_path)["name"] == "X"


def test_d0019_ac45_dev_pause_then_review_keeps_the_name(tmp_path):
    """D0019-AC-45: --pause で止めて --review で再開しても、name が変わらない（承認を重ねて最後まで）。"""
    p = DevPipeline(dev_cfg(tmp_path, auto_approve=False, pause_for_review=True), runner=FakeRunner([]))
    p.name = "X"
    assert dev_run(p, "# 別の題") == Exit.AWAITING_REVIEW
    assert dev_review(tmp_path, Decision("approve")) == Exit.AWAITING_REVIEW  # → 設計
    assert dev_state(tmp_path)["name"] == "X"
    assert dev_review(tmp_path, Decision("revise", "直して")) == Exit.AWAITING_REVIEW
    assert dev_state(tmp_path)["name"] == "X"
    assert dev_review(tmp_path, Decision("approve")) == Exit.AWAITING_REVIEW  # → テスト先行
    assert dev_state(tmp_path)["name"] == "X"
    p = DevPipeline(load_config(tmp_path, None, pause_for_review=True), runner=FakeRunner(["pass"]))
    assert asyncio.run(p.review(Decision("approve"))) == Exit.PASSED
    assert dev_state(tmp_path)["name"] == "X" and dev_state(tmp_path)["final"] == "PASSED"


def test_d0019_ac45_dev_quit_keeps_the_name(tmp_path):
    """D0019-AC-45: --review quit で記録が終わっても name が残る。"""
    p = DevPipeline(dev_cfg(tmp_path, auto_approve=False, pause_for_review=True), runner=FakeRunner([]))
    p.name = "X"
    dev_run(p)
    assert dev_review(tmp_path, Decision("quit")) == Exit.STOPPED_BY_HUMAN
    assert dev_state(tmp_path)["name"] == "X"


def test_d0019_ac45_dev_from_stage_keeps_the_name(tmp_path):
    """D0019-AC-45: --from で途中の段から再開しても（要件メモを渡さなくても）、name が変わらない。"""
    p = DevPipeline(dev_cfg(tmp_path), runner=FakeRunner(["pass"]))
    p.name = "X"
    dev_run(p)
    p2 = DevPipeline(dev_cfg(tmp_path), runner=FakeRunner(["pass"]))
    assert dev_run(p2, None, "test") == Exit.PASSED
    assert dev_state(tmp_path)["name"] == "X"


def test_d0019_ac45_dev_from_stage_makes_the_name_from_00_input_when_the_record_has_none(tmp_path):
    """D0019-AC-45: name の無い古い記録を --from で再開すると、00_input.md の最初の行から作る。"""
    dev_run(DevPipeline(dev_cfg(tmp_path), runner=FakeRunner(["pass"])), "# 題A\n本文")
    drop_name(tmp_path / "docs" / "pipeline" / "state.json")
    assert "name" not in dev_state(tmp_path)
    p2 = DevPipeline(dev_cfg(tmp_path), runner=FakeRunner(["pass"]))
    assert dev_run(p2, None, "test") == Exit.PASSED
    assert dev_state(tmp_path)["name"] == "題A"


def test_d0019_ac45_dev_from_stage_with_a_new_name_replaces_it(tmp_path):
    """D0019-AC-45: --from の再開でも、新しく --name を付ければその名前になる（付けなければ消えない、の裏）。"""
    p = DevPipeline(dev_cfg(tmp_path), runner=FakeRunner(["pass"]))
    p.name = "X"
    dev_run(p)
    p2 = DevPipeline(dev_cfg(tmp_path), runner=FakeRunner(["pass"]))
    p2.name = "Y"
    assert dev_run(p2, None, "test") == Exit.PASSED
    assert dev_state(tmp_path)["name"] == "Y"


def test_d0019_ac49_dev_review_of_an_old_record_without_name_writes_no_name(tmp_path):
    """D0019-AC-49: name の無い古い確認待ちの記録を --review で再開しても動き、name を勝手に足さない。"""
    p = DevPipeline(dev_cfg(tmp_path, auto_approve=False, pause_for_review=True), runner=FakeRunner([]))
    dev_run(p)
    drop_name(tmp_path / "docs" / "pipeline" / "state.json")
    assert dev_review(tmp_path, Decision("approve")) == Exit.AWAITING_REVIEW
    assert "name" not in dev_state(tmp_path)
    assert dev_state(tmp_path)["pending_review"]["stage"] == "design"


# ---- パイプ（kind = "linear"） -----------------------------------------------------------------


REVIEWED_PIPE = pipe_toml(stage_toml("a", "review = true\n"), stage_toml("b"))


def test_d0019_ac45_pipe_writes_the_given_name(tmp_path):
    """D0019-AC-45: パイプも、pipeline.name に入れた名前を state.json の name に書く。"""
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("a"), stage_toml("b")))
    p = LinearPipeline(cfg_for(tmp_path, pipe), pipe, runner=ScriptedRunner(pipe))
    p.name = "X"
    assert asyncio.run(p.run("# 別の題")) == Exit.PASSED
    assert pipe_state(tmp_path)["name"] == "X"


def test_d0019_ac45_pipe_name_from_memo_by_default(tmp_path):
    """D0019-AC-45: パイプも、名前を付けなければ要件メモの最初の行から作る。"""
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("a"), stage_toml("b")))
    p = LinearPipeline(cfg_for(tmp_path, pipe), pipe, runner=ScriptedRunner(pipe))
    assert asyncio.run(p.run("# 仕様の QA を回す\n本文")) == Exit.PASSED
    assert pipe_state(tmp_path)["name"] == "仕様の QA を回す"


def test_d0019_ac45_pipe_pause_then_review_keeps_the_name(tmp_path):
    """D0019-AC-45: パイプも、--pause → --review の再開で name が変わらない。"""
    pipe = make_pipe(tmp_path, REVIEWED_PIPE)
    cfg = cfg_for(tmp_path, pipe, auto_approve=False, pause_for_review=True)
    p = LinearPipeline(cfg, pipe, runner=ScriptedRunner(pipe))
    p.name = "X"
    assert asyncio.run(p.run("別の題")) == Exit.AWAITING_REVIEW
    assert pipe_state(tmp_path)["name"] == "X"
    p2 = LinearPipeline(cfg_for(tmp_path, pipe, auto_approve=False, pause_for_review=True), pipe, runner=ScriptedRunner(pipe))
    assert asyncio.run(p2.review(Decision("approve"))) == Exit.PASSED
    assert pipe_state(tmp_path)["name"] == "X"


def test_d0019_ac45_pipe_from_stage_keeps_the_name(tmp_path):
    """D0019-AC-45: パイプも、--from の再開（要件メモなし）で name が変わらない。"""
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("a"), stage_toml("b")))
    p = LinearPipeline(cfg_for(tmp_path, pipe), pipe, runner=ScriptedRunner(pipe))
    p.name = "X"
    asyncio.run(p.run("別の題"))
    p2 = LinearPipeline(cfg_for(tmp_path, pipe), pipe, runner=ScriptedRunner(pipe))
    assert asyncio.run(p2.run(None, "b")) == Exit.PASSED
    assert pipe_state(tmp_path)["name"] == "X"


def test_d0019_ac49_pipe_review_of_an_old_record_without_name_writes_no_name(tmp_path):
    """D0019-AC-49: name の無い古い確認待ちのパイプの記録も、--review で再開できて、name を勝手に足さない。"""
    pipe = make_pipe(tmp_path, REVIEWED_PIPE)
    cfg = cfg_for(tmp_path, pipe, auto_approve=False, pause_for_review=True)
    asyncio.run(LinearPipeline(cfg, pipe, runner=ScriptedRunner(pipe)).run("題"))
    drop_name(tmp_path / "docs" / "pipeline" / "p" / "state.json")
    p2 = LinearPipeline(cfg_for(tmp_path, pipe, auto_approve=False, pause_for_review=True), pipe, runner=ScriptedRunner(pipe))
    assert asyncio.run(p2.review(Decision("approve"))) == Exit.PASSED
    assert "name" not in pipe_state(tmp_path)


# ---- コマンド（pipe-in --name） -----------------------------------------------------------------


@pytest.fixture
def with_runner(monkeypatch):
    """pipe-in のコマンドが作る流れの runner だけを差し替える（SDK を呼ばない）。"""

    def install(make_runner):
        real = cli.pipeline_for

        def fake(cfg, pipe, *, test_cmd_given=False):
            p = real(cfg, pipe, test_cmd_given=test_cmd_given)
            p.runner = make_runner(pipe)
            return p

        monkeypatch.setattr(cli, "pipeline_for", fake)

    return install


def test_d0019_ac45_cli_name_for_the_dev_flow(tmp_path, with_runner):
    """D0019-AC-45: pipe-in --name "X"（開発フロー）で state.json の name が X になる（前後の空白は整える）。"""
    with_runner(lambda pipe: FakeRunner(["pass"]))
    assert cli.main(["--project", str(tmp_path), "--text", "# 別の題\n本文", "--yes", "--name", "  X  "]) == 0
    assert dev_state(tmp_path)["name"] == "X"


def test_d0019_ac45_cli_without_name_uses_the_first_line(tmp_path, with_runner):
    """D0019-AC-45: --name を付けなければ（空白だけの --name も同じ）、要件メモの最初の行から作る。"""
    with_runner(lambda pipe: FakeRunner(["pass"]))
    assert cli.main(["--project", str(tmp_path), "--text", "# 見出しの題\n本文", "--yes"]) == 0
    assert dev_state(tmp_path)["name"] == "見出しの題"
    assert cli.main(["--project", str(tmp_path), "--text", "# 二つ目の題\n本文", "--yes", "--name", "   "]) == 0
    assert dev_state(tmp_path)["name"] == "二つ目の題"


def test_d0019_ac45_cli_name_for_a_pipe(tmp_path, with_runner):
    """D0019-AC-45: pipe-in --pipe <パイプ> --name "X" で、パイプの state.json の name が X になる。"""
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("a"), stage_toml("b")))
    with_runner(lambda _pipe: ScriptedRunner(pipe))
    args = ["--project", str(tmp_path), "--pipe", str(tmp_path / "pipes" / "pipe-in-p"), "--text", "# 別の題", "--yes"]
    assert cli.main([*args, "--name", "X"]) == 0
    assert pipe_state(tmp_path)["name"] == "X"


def test_d0019_ac45_cli_pause_then_review_keeps_the_name(tmp_path, with_runner):
    """D0019-AC-45: pipe-in --pause --name "X" のあと pipe-in --review approve で再開しても name が X のまま。"""
    with_runner(lambda pipe: FakeRunner([]))
    p = str(tmp_path)
    assert cli.main(["--project", p, "--text", "題", "--pause", "--name", "X"]) == int(Exit.AWAITING_REVIEW)
    assert dev_state(tmp_path)["name"] == "X"
    assert cli.main(["--project", p, "--review", "approve"]) == int(Exit.AWAITING_REVIEW)
    assert dev_state(tmp_path)["name"] == "X"


def test_d0019_ac45_cli_from_keeps_the_name(tmp_path, with_runner):
    """D0019-AC-45: pipe-in --from <段> の再開で、--name を付けなくても name が変わらない。"""
    with_runner(lambda pipe: FakeRunner(["pass", "pass"]))
    p = str(tmp_path)
    assert cli.main(["--project", p, "--text", "題", "--yes", "--name", "X"]) == 0
    assert cli.main(["--project", p, "--from", "test", "--yes"]) == 0
    assert dev_state(tmp_path)["name"] == "X"


def test_d0019_ac45_cli_refuses_name_together_with_review(tmp_path):
    """D0019-AC-45: --review と --name の併用は、名前は始めるときだけ付けるので、文のあるエラーで断る。"""
    with pytest.raises(SystemExit) as e:
        cli.main(["--project", str(tmp_path), "--review", "approve", "--name", "X"])
    assert isinstance(e.value.code, str) and "--name" in e.value.code and "--review" in e.value.code
