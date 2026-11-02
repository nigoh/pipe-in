"""前のパイプの成果物を受けて後ろのパイプを流す流れ（--after。D0069）を、SDK を呼ばずに確かめる。

runner は偽物に差し替える（ScriptedRunner・no_sdk）。ファイルは tmp_path の中だけに作り、今までの置き場所も tmp_path に向ける。
流れの入口（cli）は test_pipe_after_cli.py で確かめ、ここでは LinearPipeline の受け取り・続き・記録を確かめる。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pipe_in.engine.checkpoint import Decision
from pipe_in.engine.config import load_config
from pipe_in.engine.pipeline import STATE, Exit
from pipe_in.engine.runner import StageRun
from pipe_in.pipe import after
from pipe_in.pipe import definition as pd
from pipe_in.pipe.pipeline import LinearPipeline


@pytest.fixture(autouse=True)
def pipes_elsewhere(tmp_path, monkeypatch):
    """今までの置き場所を tmp_path に向ける（リポジトリの pipes/ を見ない）。"""
    monkeypatch.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "shared"))


class ScriptedRunner:
    """SDK の代わり。段の成果物を書き、構造化出力は決めた値を順に返す（tests/test_pipe_flow.py の形）。"""

    def __init__(self, structured: dict[str, list] | None = None):
        self.structured = {k: list(v) for k, v in (structured or {}).items()}
        self.calls: list[tuple[str, str | None, str]] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append((spec.name, resume, prompt))
        (cfg.work_dir / spec.output).write_text(f"# {spec.name}\n", encoding="utf-8")
        queue = self.structured.get(spec.name)
        data = queue.pop(0) if queue else None
        return StageRun(stage=spec.name, session_id=f"s-{len(self.calls)}", structured=data, cost_usd=0.01, num_turns=1)


async def no_sdk(spec, prompt, cfg, *, resume, log_name):
    raise AssertionError(f"SDK を呼ばないはずの場面で段「{spec.name}」が呼ばれました")


def project_of(tmp_path: Path) -> Path:
    p = tmp_path / "app"
    p.mkdir(exist_ok=True)
    return p


def stage(name: str, label: str, output: str, extra: str = "") -> str:
    return f'\n[[stages]]\nname = "{name}"\nlabel = "{label}"\noutput = "{output}"\naccess = "read"\nprompt = "{label}をする"\n{extra}'


def pipe_toml(*stages: str, input_mode: str = "optional") -> str:
    return f'[pipe]\nkind = "linear"\nlabel = "試し"\ninput = "{input_mode}"\n' + "".join(stages)


PREV = pipe_toml(stage("survey", "仕様の調査", "01_survey.md"), stage("draw", "図を描く", "02_draw.md"))
# 後ろのパイプ：最初の段で確認を取る（一時停止の続きを確かめるため）
LATER = pipe_toml(stage("check", "照合", "01_check.md", extra="review = true\n"), stage("report", "報告", "02_report.md"))


def make_pipe(project: Path, toml: str, name: str) -> pd.PipeDef:
    d = project / ".pipe-in" / "pipes" / f"pipe-in-{name}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pipe.toml").write_text(toml, encoding="utf-8")
    return pd.load_pipe(d)


def later_cfg(project: Path, pipe: pd.PipeDef, *, pause: bool = False, auto: bool = True):
    return load_config(project, None, auto_approve=auto, pause_for_review=pause).for_pipe(pipe.name, own_work_dir=True)


def run_pipe(project: Path, pipe: pd.PipeDef, runner=None, *, text: str | None = "やること", pause: bool = False, auto: bool = True) -> Exit:
    """前のパイプ（受けない）を流す。記録は docs/pipeline/<名前>/ に書かれる。"""
    p = LinearPipeline(later_cfg(project, pipe, pause=pause, auto=auto), pipe, runner=runner or ScriptedRunner())
    return asyncio.run(p.run(text))


def start_after(project: Path, later: pd.PipeDef, runner, *, text: str | None = "やること", pause: bool = False, auto: bool = True) -> Exit:
    """--after diagrams で後ろのパイプを始める流れ（cli が行う順番と同じ：前を読む → 受ける → 流す）。"""
    cfg = later_cfg(project, later, pause=pause, auto=auto)
    received = after.read_previous("diagrams", cfg, project / "docs" / "pipeline").record()
    p = LinearPipeline(cfg, later, runner=runner)
    p.receive(received)
    return asyncio.run(p.run(text))


def inject_received(project: Path, name: str) -> dict:
    """受けた元の記録を、後ろの state.json に手で入れる（始めるときの受け取りは別のテストで確かめる）。

    続き（--review・--from）が、この記録をそのまま使うことを確かめるための土台。形は設計どおり（pipe・kind・updated_at・dir・artifacts）。
    """
    prev_updated = state_of(project, "diagrams")["updated_at"]
    received = {
        "pipe": "diagrams",
        "kind": "linear",
        "updated_at": prev_updated,
        "dir": "diagrams",
        "artifacts": [{"stage": "仕様の調査", "path": "diagrams/01_survey.md"}, {"stage": "図を描く", "path": "diagrams/02_draw.md"}],
    }
    path = project / "docs/pipeline" / name / STATE
    data = json.loads(path.read_text(encoding="utf-8"))
    data["received_from"] = received
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return received


def review_later(project: Path, later: pd.PipeDef, decision: Decision, runner) -> Exit:
    cfg = later_cfg(project, later, pause=True, auto=False)
    return asyncio.run(LinearPipeline(cfg, later, runner=runner).review(decision))


def state_of(project: Path, name: str) -> dict:
    return json.loads((project / "docs/pipeline" / name / STATE).read_text(encoding="utf-8"))


def summary_of(project: Path, name: str) -> str:
    return (project / "docs/pipeline" / name / "99_summary.md").read_text(encoding="utf-8")


# ---- D0069-AC-01：受けると最初の段の指示文に前の成果物の場所が入る --------------------------------


def test_d0069_ac01_受けると最初の段の指示文に前の段の成果物の場所が入る(tmp_path):
    """D0069-AC-01: 前が PASSED の記録を受けて流すと、runner に渡る最初の段の指示文に、前の段の存在する成果物の場所（表示名つき）が入る。"""
    project = project_of(tmp_path)
    run_pipe(project, make_pipe(project, PREV, "diagrams"), text="前の依頼メモ")
    later = make_pipe(project, LATER, "spec-qa")
    runner = ScriptedRunner()
    assert start_after(project, later, runner) == Exit.PASSED
    assert runner.calls[0][0] == "check"
    first = runner.calls[0][2]
    lines = [line for line in first.splitlines() if "前のパイプ「diagrams」" in line]
    assert any("仕様の調査" in line and "docs/pipeline/diagrams/01_survey.md" in line for line in lines), first
    assert any("図を描く" in line and "docs/pipeline/diagrams/02_draw.md" in line for line in lines), first
    assert "docs/pipeline/diagrams/00_input.md" not in first, first


# ---- D0069-AC-11：依頼メモは引き継がない（input の決まりに従う） ----------------------------------


def test_d0069_ac11_依頼メモを省いても_optional_なら流れ_00_input_md_は作られない(tmp_path):
    """D0069-AC-11: --input・--text を省いても、後ろの input が optional なら依頼メモ無しで流れる。後ろの 00_input.md は前の依頼メモの写しにならず、作られない。"""
    project = project_of(tmp_path)
    run_pipe(project, make_pipe(project, PREV, "diagrams"), text="前の依頼メモ")
    later = make_pipe(project, LATER, "spec-qa")
    runner = ScriptedRunner()
    assert start_after(project, later, runner, text=None) == Exit.PASSED
    assert not (project / "docs/pipeline/spec-qa/00_input.md").exists()
    assert all("前の依頼メモ" not in prompt for _, _, prompt in runner.calls)


def test_d0069_ac11_required_なら依頼メモが要ると断る(tmp_path):
    """D0069-AC-11: 後ろの input が required なら、--after があっても今までどおり「依頼メモが要ります」で断る。"""
    project = project_of(tmp_path)
    run_pipe(project, make_pipe(project, PREV, "diagrams"), text="前の依頼メモ")
    later = make_pipe(project, pipe_toml(stage("check", "照合", "01_check.md"), input_mode="required"), "spec-qa")
    runner = ScriptedRunner()
    with pytest.raises(SystemExit) as e:
        start_after(project, later, runner, text=None)
    assert "依頼メモが要ります" in str(e.value.code), e.value.code
    assert runner.calls == []
    assert not (project / "docs/pipeline/spec-qa").exists()


# ---- D0069-AC-12：受けた元は received_from に書かれる ----------------------------------------


def test_d0069_ac12_受けた元は_received_from_に_pipe_updated_at_artifacts_で書かれる(tmp_path):
    """D0069-AC-12: 受けた元は後ろの state.json の received_from（pipe・updated_at・artifacts）に書かれる。artifacts は渡した成果物の場所（作業フォルダからの相対）を段の順に持つ。"""
    project = project_of(tmp_path)
    run_pipe(project, make_pipe(project, PREV, "diagrams"))
    later = make_pipe(project, LATER, "spec-qa")
    assert start_after(project, later, ScriptedRunner()) == Exit.PASSED
    st = state_of(project, "spec-qa")
    assert "received_from" in st, sorted(st)
    rf = st["received_from"]
    assert rf["pipe"] == "diagrams"
    assert rf["updated_at"] == state_of(project, "diagrams")["updated_at"]
    assert [a["path"] for a in rf["artifacts"]] == ["diagrams/01_survey.md", "diagrams/02_draw.md"]


def test_d0069_ac12_受けていない実行には_received_from_が無い(tmp_path):
    """D0069-AC-12: --after で受けていない実行の state.json には received_from が無い（項目を足すだけ）。"""
    project = project_of(tmp_path)
    later = make_pipe(project, LATER, "spec-qa")
    assert run_pipe(project, later) == Exit.PASSED
    assert "received_from" not in state_of(project, "spec-qa")


# ---- D0069-AC-13：続き（--review・--from）は received_from をそのまま使う -----------------------


@pytest.mark.parametrize(
    "decision",
    [Decision("approve"), Decision("revise", "図の矢印を直して"), Decision("quit")],
    ids=["approve", "revise", "quit"],
)
def test_d0069_ac13_review_の_approve_revise_quit_で_received_from_が残る(tmp_path, decision):
    """D0069-AC-13: received_from のある state.json で --review（approve・revise・quit のどれも）を流しても、received_from は消えずに残る。"""
    project = project_of(tmp_path)
    run_pipe(project, make_pipe(project, PREV, "diagrams"))
    later = make_pipe(project, LATER, "spec-qa")
    assert run_pipe(project, later, pause=True, auto=False) == Exit.AWAITING_REVIEW
    received = inject_received(project, "spec-qa")
    review_later(project, later, decision, ScriptedRunner())
    st2 = state_of(project, "spec-qa")
    assert st2.get("received_from") == received, sorted(st2)


def test_d0069_ac13_from_で続けても前を読み直さず同じ場所を渡す(tmp_path):
    """D0069-AC-13: --from で続けるとき、前の state.json を書き換えて final を消しても、続きは受けた元の成果物の場所を渡す（前を読み直さない）。"""
    project = project_of(tmp_path)
    run_pipe(project, make_pipe(project, PREV, "diagrams"))
    later = make_pipe(project, LATER, "spec-qa")
    assert run_pipe(project, later) == Exit.PASSED
    inject_received(project, "spec-qa")
    prev_state = project / "docs/pipeline/diagrams" / STATE
    data = json.loads(prev_state.read_text(encoding="utf-8"))
    data.pop("final", None)
    prev_state.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    runner = ScriptedRunner()
    cfg = later_cfg(project, later)
    assert asyncio.run(LinearPipeline(cfg, later, runner=runner).run(None, "report")) == Exit.PASSED
    assert runner.calls[0][0] == "report"
    assert "docs/pipeline/diagrams/01_survey.md" in runner.calls[0][2], runner.calls[0][2]


def test_d0069_ac13_続きを始めると画面に受けた元が1行出る(tmp_path, capsys):
    """D0069-AC-13: 続きを始めるとき、画面に記録の受けた元が1行出る。"""
    project = project_of(tmp_path)
    run_pipe(project, make_pipe(project, PREV, "diagrams"))
    later = make_pipe(project, LATER, "spec-qa")
    assert run_pipe(project, later) == Exit.PASSED
    inject_received(project, "spec-qa")
    capsys.readouterr()
    cfg = later_cfg(project, later)
    asyncio.run(LinearPipeline(cfg, later, runner=ScriptedRunner()).run(None, "report"))
    out = capsys.readouterr().out
    assert "受けた元" in out and "diagrams" in out, out


# ---- D0069-AC-16：received_from の無い古い state.json は、受けた元の無い実行として続く ----------


@pytest.mark.parametrize("mode", ["review", "from"])
def test_d0069_ac16_received_from_の無い古い_state_は受けた元なしで続く(tmp_path, mode):
    """D0069-AC-16: received_from の無い古い state.json は、受けた元の無い実行として読む。--review・--from で続けても、今までどおり流れる。"""
    project = project_of(tmp_path)
    later = make_pipe(project, LATER, "spec-qa")
    if mode == "review":
        assert run_pipe(project, later, pause=True, auto=False) == Exit.AWAITING_REVIEW
        assert review_later(project, later, Decision("approve"), ScriptedRunner()) == Exit.PASSED
    else:
        assert run_pipe(project, later) == Exit.PASSED
        runner = ScriptedRunner()
        assert asyncio.run(LinearPipeline(later_cfg(project, later), later, runner=runner).run(None, "report")) == Exit.PASSED
        assert runner.calls[0][0] == "report"
    assert "received_from" not in state_of(project, "spec-qa")


# ---- D0069-AC-17：まとめの「パイプ」の次に受けた元の1行 --------------------------------------


def test_d0069_ac17_99_summary_に受けた元の1行が出る(tmp_path):
    """D0069-AC-17: 後ろの 99_summary.md の「パイプ」の行の次に、受けた元（前の名前と終わった日時）が1行出る。"""
    project = project_of(tmp_path)
    run_pipe(project, make_pipe(project, PREV, "diagrams"))
    later = make_pipe(project, LATER, "spec-qa")
    assert start_after(project, later, ScriptedRunner()) == Exit.PASSED
    lines = summary_of(project, "spec-qa").splitlines()
    i = next(n for n, line in enumerate(lines) if line.startswith("- パイプ:"))
    assert lines[i + 1].startswith("- 受けた元:"), lines[i : i + 3]
    assert "diagrams" in lines[i + 1], lines[i + 1]


def test_d0069_ac17_受けていない実行では_受けた元の行が出ない(tmp_path):
    """D0069-AC-17: 受けていない実行では、受けた元の行は出ない。"""
    project = project_of(tmp_path)
    later = make_pipe(project, LATER, "spec-qa")
    assert run_pipe(project, later) == Exit.PASSED
    assert "受けた元" not in summary_of(project, "spec-qa")
