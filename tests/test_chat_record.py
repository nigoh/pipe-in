"""D0076-AC-22・23・25：会話の道の記録（state.json・logs/・99_summary.md）の形と、古い記録を今までどおり読めること。

記録は chat_cmd.main を通して作り、本体の読み手（record_order.check_dir・LinearPipeline.review・usage.estimate.actual_usd）で読む。
今の作りのままで通るもの（古い記録を読む検査）は、名前の末尾を _守る にし、説明の末尾に「（今のまま通る。守る）」と書く。
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path

import pytest
from chat_support import Run, no_sdk, pipe_toml, stage_toml  # noqa: F401

from pipe_in.dev.record_order import OrderReport, check_dir
from pipe_in.engine.checkpoint import Decision
from pipe_in.engine.config import load_config
from pipe_in.engine.runner import StageRun
from pipe_in.pipe import definition as pd
from pipe_in.pipe.pipeline import LinearPipeline
from pipe_in.usage.estimate import actual_usd

pytestmark = pytest.mark.usefixtures("no_sdk")

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def reviewed() -> str:
    return pipe_toml(stage_toml("a", extra="review = true\n"), stage_toml("b"))


class NeverRunner:
    """呼ばれたら落ちる runner（本体の --review がこの記録の続きを流さないことを見る）。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append(spec.name)
        return StageRun(stage=spec.name, session_id="x", cost_usd=0.0, num_turns=0)


# ---- AC-22 ----------------------------------------------------------------------------------


def test_d0076_ac22_記録はrecord_orderを通りdriverがpipe_chatになる(tmp_path):
    """D0076-AC-22: chat の記録は record check（record_order.check_dir）が通り（承認の前に次の段の begin が無い）、driver が pipe-chat、段のログの最初の行が Prompt 行になる。"""
    r = Run(tmp_path)
    r.ready(reviewed())
    r.run_and_finish("a")
    r.next("await_review")
    r.review("revise", "直して")
    r.run_next("a")
    r.finish("a")
    r.next("await_review")
    r.review("approved")
    r.run_and_finish("b")
    state = r.state()
    assert state["driver"] == "pipe-chat" and state["final"] == "PASSED"
    report = check_dir(r.run_dir)
    assert isinstance(report, OrderReport)
    assert report.violations == () and report.undecided == (), report
    assert report.checked >= 1
    for name in r.logs():
        first = json.loads((r.run_dir / "logs" / name).read_text(encoding="utf-8").splitlines()[0])
        assert first["_type"] == "Prompt" and first["driver"] == "pipe-chat" and first["stage"] in ("a", "b") and first.get("at"), first


def test_d0076_ac22_本体のreviewはこの記録の続きを流さない(tmp_path):
    """D0076-AC-22: pipe-in --review（LinearPipeline.review）は、確認待ちの chat の記録の続きを流さず、記録を変えない。"""
    r = Run(tmp_path)
    r.ready(reviewed())
    r.run_and_finish("a")
    r.next("await_review")
    before = r.state_text()
    pipe = pd.load_pipe(r.pipe_dir)
    cfg = load_config(tmp_path, None, auto_approve=False, pause_for_review=True).for_pipe(pipe.name, own_work_dir=True)
    runner = NeverRunner()
    pipeline = LinearPipeline(cfg, pipe, runner=runner)
    with pytest.raises(SystemExit):
        asyncio.run(pipeline.review(Decision("approve")))
    assert runner.calls == [], "段が流れた"
    assert r.state_text() == before


def test_d0076_ac22_本体のreviewの案内はchat_nextで続けると伝える(tmp_path):
    """D0076-AC-22（設計 2.2）: driver が pipe-chat の記録に pipe-in --review を向けると、断り方は「会話の中で流した記録です。pipe-in-gen chat next で続けてください」になる。"""
    pipe_dir = tmp_path / ".pipe-in" / "pipes" / "pipe-in-hp"
    pipe_dir.mkdir(parents=True)
    (pipe_dir / "pipe.toml").write_text(reviewed(), encoding="utf-8")
    work = tmp_path / "docs" / "pipeline" / "hp"
    work.mkdir(parents=True)
    (work / "state.json").write_text(
        json.dumps({"pipe": "hp", "driver": "pipe-chat", "stages": [], "final": None, "pending_review": {"stage": "a", "doc": "docs/pipeline/hp/a.md"}, "runs": []}),
        encoding="utf-8",
    )
    pipe = pd.load_pipe(pipe_dir)
    cfg = load_config(tmp_path, None, auto_approve=False, pause_for_review=True).for_pipe("hp", own_work_dir=True)
    with pytest.raises(SystemExit) as e:
        asyncio.run(LinearPipeline(cfg, pipe, runner=NeverRunner()).review(Decision("approve")))
    assert "chat next" in str(e.value), str(e.value)


# ---- AC-23 ----------------------------------------------------------------------------------


def test_d0076_ac23_usage_summaryはavailableがfalseで費用は無しになりまとめに合計が出ない(tmp_path):
    """D0076-AC-23: chat の記録の usage_summary は available: false と理由を持ち、段の実行の cost_usd は 0 ではなく無し（null）になる。
    99_summary.md に費用の合計は出ず、「使用量は取れない」と書かれる。"""
    r = Run(tmp_path)
    r.ready(reviewed())
    r.run_and_finish("a")
    mid = r.state()
    assert mid["usage_summary"]["available"] is False and mid["usage_summary"]["reason"], "途中の記録でも「取れない」と書く"
    r.next("await_review")
    r.review("approved")
    r.run_and_finish("b")
    state = r.state()
    summary = state["usage_summary"]
    assert summary["available"] is False and isinstance(summary["reason"], str) and summary["reason"]
    assert "by_model" not in summary or not summary["by_model"], "0 の表を作らない"
    assert state["total_cost_usd"] is None
    runs = [x for x in state["runs"] if "seq" in x]
    assert len(runs) == 2
    for run in runs:
        assert "cost_usd" in run and run["cost_usd"] is None, run
    text = (r.run_dir / "99_summary.md").read_text(encoding="utf-8")
    assert not re.search(r"\$\s?\d", text), "費用の金額が出ている"
    assert "合計（概算）" not in text
    assert "使用量は取れ" in text


def test_d0076_ac23_段のログは費用を数で書かない(tmp_path):
    """D0076-AC-23: 段のログの ResultMessage の total_cost_usd は null（数の 0 ではない）。"""
    r = Run(tmp_path)
    r.ready(pipe_toml(stage_toml("a")))
    r.run_and_finish("a", summary="要点です")
    lines = [json.loads(x) for x in (r.run_dir / "logs" / r.logs()[0]).read_text(encoding="utf-8").splitlines()]
    kinds = [x["_type"] for x in lines]
    assert kinds[0] == "Prompt" and "AssistantMessage" in kinds and "ResultMessage" in kinds, kinds
    result = next(x for x in lines if x["_type"] == "ResultMessage")
    assert result["total_cost_usd"] is None
    assert "要点です" in json.dumps(next(x for x in lines if x["_type"] == "AssistantMessage"), ensure_ascii=False)


# ---- AC-25 ----------------------------------------------------------------------------------

OLD_DIRS = [
    "pipe_dev/running",
    "pipe_dev/waiting",
    "pipe_dev/finished",
    "pipe_in/running",
    "pipe_in/waiting",
    "pipe_in/finished",
    "showcase",
    "showcase_running",
    "showcase_running_next",
    "showcase_waiting",
]


@pytest.mark.parametrize("rel", OLD_DIRS)
def test_d0076_ac25_古い記録は今までどおり読める_守る(rel):
    """D0076-AC-25: 古い記録（usage_summary が無い・cost_usd が数）は、record check（check_dir）と前の実績（actual_usd）で今までどおり読める（今のまま通る。守る）。"""
    d = FIXTURES / rel
    report = check_dir(d)
    assert isinstance(report, OrderReport)
    state = json.loads((d / "state.json").read_text(encoding="utf-8"))
    value = actual_usd(state)
    assert value is None or isinstance(value, float)


def test_d0076_ac25_availableがfalseの記録も読み手は落ちない_守る(tmp_path):
    """D0076-AC-25: usage_summary.available が false・total_cost_usd と cost_usd が null の記録も、actual_usd は例外なく None を返す（今のまま通る。守る）。"""
    state = {
        "pipe": "hp",
        "driver": "pipe-chat",
        "stages": [{"name": "a", "label": "a", "output": "a.md", "review": False}],
        "final": "PASSED",
        "total_cost_usd": None,
        "usage_summary": {"available": False, "reason": "会話の中で流したため、費用とトークンは取れません"},
        "runs": [{"stage": "a", "seq": 1, "cost_usd": None, "num_turns": 0, "duration_sec": 1.0, "is_error": False}],
    }
    assert actual_usd(state) is None
    d = tmp_path / "rec"
    d.mkdir()
    (d / "state.json").write_text(json.dumps(state), encoding="utf-8")
    assert isinstance(check_dir(d), OrderReport)


@pytest.mark.parametrize("rel", ["pipe_dev/running", "pipe_dev/finished", "pipe_in/waiting", "showcase"])
@pytest.mark.parametrize("sub", ["next", "probe", "status", "done", "review"])
def test_d0076_ac25_chatの各コマンドはdriverが違う記録を断り書き換えない(tmp_path, rel, sub):
    """D0076-AC-25: chat の各コマンドは、driver が pipe-chat でない記録（開発フロー・本体の実行）を「会話の道の記録ではありません」と断り、書き換えない。"""
    r = Run(tmp_path)
    r.make(pipe_toml(stage_toml("a")))
    r.run_dir.mkdir(parents=True)
    shutil.copyfile(FIXTURES / rel / "state.json", r.run_dir / "state.json")
    before = r.state_text()
    files = sorted(p.relative_to(tmp_path).as_posix() for p in (tmp_path / "docs").rglob("*"))
    args = {"done": ["--stage", "a", "--summary", "x"], "review": ["approved"]}.get(sub, [])
    out = r.cmd(sub, *args)
    assert r.code != 0 and out["ok"] is False, out
    assert "会話の道の記録ではありません" in json.dumps(out, ensure_ascii=False), out
    assert r.state_text() == before
    assert sorted(p.relative_to(tmp_path).as_posix() for p in (tmp_path / "docs").rglob("*")) == files, "ファイルが増えた"
