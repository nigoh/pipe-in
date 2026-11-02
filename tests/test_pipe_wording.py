"""D0071：本体に残る前の版の呼び名 /pipe-dev を、実際のスキルの名前 /pipe-in に直す（文言）。記録の driver の値 "pipe-dev" は変えない。

記録は tmp_path に、差し替えの時計をつけた Recorder で書く。リポジトリの実物には書かない。SDK も呼ばない。
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import live_support as ls
from pipe_in.dev import record
from pipe_in.dev.record import DRIVER, Recorder
from pipe_in.engine import live
from pipe_in.engine.config import load_config

ROOT = Path(__file__).resolve().parents[1]
FIXED = datetime(2026, 10, 17, 10, 0, 0)


def recorder(project: Path) -> Recorder:
    return Recorder(load_config(project), now=lambda: FIXED)


def first_line(project: Path, log: str) -> dict:
    path = project / "docs" / "pipeline" / "logs" / log
    return json.loads(path.read_text(encoding="utf-8").splitlines()[0])


# ---- AC-12：Prompt 行と 99_summary.md の文 ----------------------------------------------------------


def test_d0071_ac12_prompt_line_says_pipe_in(tmp_path):
    """D0071-AC-12: record begin が書く Prompt 行の prompt は「/pipe-in の<段>」（差し戻しは「（N 回目）」つき）。driver の値は pipe-dev のまま。"""
    r = recorder(tmp_path)
    r.start("メモ")
    r.begin("requirements")
    r.done("requirements")
    r.begin("implement", attempt=2)
    first = first_line(tmp_path, "01_requirements.jsonl")
    assert first["prompt"] == "/pipe-in の要件定義"
    assert first["driver"] == "pipe-dev"
    assert first_line(tmp_path, "02_implement_2.jsonl")["prompt"] == "/pipe-in の実装（2 回目）"


def test_d0071_ac12_summary_title_is_pipe_in(tmp_path):
    """D0071-AC-12: record finish が書く 99_summary.md の1行目は「# /pipe-in のまとめ」で、/pipe-dev はどこにも残らない。"""
    r = recorder(tmp_path)
    r.start("メモ")
    r.begin("requirements")
    r.done("requirements")
    r.finish("PASSED")
    text = (tmp_path / "docs" / "pipeline" / "99_summary.md").read_text(encoding="utf-8")
    assert text.splitlines()[0] == "# /pipe-in のまとめ"
    assert "/pipe-dev" not in text


# ---- AC-14：古い形の記録を読んでも動きが変わらない ----------------------------------------------------


def test_d0071_ac14_live_snapshot_ignores_review_at():
    """D0071-AC-14: review の要素に at があってもなくても、live の写し（進み具合）は同じ。今の作りでも通る（守り続ける検査）。"""
    state = ls.base_state(
        stages=[{**ls.stage_entry(n), "review": n in ("requirements", "design", "red")} for n in ls.STAGES],
        runs=[ls.run("requirements", seq=1), ls.review("requirements"), ls.run("design", seq=2)],
        pending_review=ls.pending("design"),
    )
    with_at = copy.deepcopy(state)
    with_at["runs"][1]["at"] = "2026-10-17T10:00:20+09:00"
    now = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)
    plain = live.build_snapshot(state, "2026-10-17T10:00:00+09:00", now=now)
    assert live.build_snapshot(with_at, "2026-10-17T10:00:00+09:00", now=now) == plain
    assert plain["review"] is not None


@pytest.mark.parametrize("name", ["running", "waiting", "finished"])
def test_d0071_ac14_fixture_review_entries_have_no_at(name):
    """D0071-AC-14: 見本（tests/fixtures/pipe_dev/・pipe_in/）の review の要素には at を足さない（古い形の見本として残す）。今のままで通る。"""
    for folder in ("pipe_dev", "pipe_in"):
        data = json.loads((ROOT / "tests" / "fixtures" / folder / name / "state.json").read_text(encoding="utf-8"))
        assert all("at" not in run for run in data["runs"] if "review" in run), (folder, name)


@pytest.mark.parametrize("name", ["running", "waiting", "finished"])
def test_d0071_ac14_fixtures_differ_only_in_driver(name):
    """D0071-AC-14: 見本 pipe_dev と pipe_in は、driver の値だけが違う形のまま（今のままで通る）。"""
    new = json.loads((ROOT / "tests" / "fixtures" / "pipe_dev" / name / "state.json").read_text(encoding="utf-8"))
    old = json.loads((ROOT / "tests" / "fixtures" / "pipe_in" / name / "state.json").read_text(encoding="utf-8"))
    assert (old.pop("driver"), new.pop("driver")) == ("pipe-in", "pipe-dev")
    assert old == new


# ---- AC-15：pipe_in/ に /pipe-dev の言い方が残らない -----------------------------------------------------


def pipe_dev_lines() -> list[str]:
    found: list[str] = []
    for path in sorted((ROOT / "pipe_in").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "pipe-dev" in line:
                found.append(f"{path.relative_to(ROOT).as_posix()}:{n}: {line.strip()}")
    return found


def test_d0071_ac15_no_pipe_dev_wording_in_package():
    """D0071-AC-15: pipe_in/ の .py に、DRIVER の値 "pipe-dev" の1行（record.py の DRIVER = "pipe-dev"）以外の pipe-dev が残らない。"""
    left = [x for x in pipe_dev_lines() if not (x.startswith("pipe_in/dev/record.py:") and x.endswith('DRIVER = "pipe-dev"'))]
    assert left == []
    assert len(pipe_dev_lines()) == 1  # DRIVER の1行は残る（値を変えない）


def test_d0071_ac15_driver_value_is_unchanged(tmp_path):
    """D0071-AC-15・FR-09: DRIVER の値は "pipe-dev" のまま。record start は driver にこの値を入れる（前の版 pipe-in の記録と見分けるため）。今のままで通る。"""
    assert DRIVER == "pipe-dev"
    recorder(tmp_path).start("メモ")
    state = json.loads((tmp_path / "docs" / "pipeline" / "state.json").read_text(encoding="utf-8"))
    assert state["driver"] == "pipe-dev"
    assert record.DRIVER == state["driver"]
