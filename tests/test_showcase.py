"""画面用の見本の記録（tests/fixtures/showcase/）：今の本体で作り直したものと形が同じで、台本どおりで、手元の情報が無い。

見本は tests/showcase.py が、本物の開発フローを SDK を呼ばない runner で流して作る。
文の言い回しが変わっても落ちないよう、形（キー・並びの長さ・値の型・ログの各行の種類とキー・見出しの並び）を比べる。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import showcase
import test_rules

FIXTURE = showcase.FIXTURE
REMAKE = "見本の記録の形が今の本体とずれています。python tests/showcase.py で作り直してください"


def load_state(work: Path) -> dict:
    return json.loads((work / "state.json").read_text(encoding="utf-8"))


def log_shapes(work: Path) -> dict[str, list[tuple[str, tuple[str, ...]]]]:
    """logs/ のファイルごとに、各行の (_type, キーの集まり) の並び。"""
    out = {}
    for path in sorted((work / "logs").glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        out[path.name] = [(row.get("_type"), tuple(sorted(row))) for row in rows]
    return out


def top_files(work: Path) -> set[str]:
    return {p.name for p in work.iterdir() if p.is_file()}


def summary_headings(work: Path) -> list[str]:
    return [line for line in (work / "99_summary.md").read_text(encoding="utf-8").splitlines() if line.startswith("## ")]


def fixture_files() -> list[Path]:
    assert FIXTURE.is_dir(), f"見本の記録 {FIXTURE.as_posix()} がありません。python tests/showcase.py で作ってください"
    return sorted(p for p in FIXTURE.rglob("*") if p.is_file())


@pytest.fixture
def remade(tmp_path) -> Path:
    return showcase.build_showcase(tmp_path / "myapp")


def test_d0009_ac15_showcase_matches_engine_shape(remade):
    """D0009-AC-15: 置いてある見本は、今の本体で作り直したものと形が同じ（state.json・logs/・成果物・まとめの見出し）。"""
    fixture_files()
    assert showcase.shape(load_state(FIXTURE)) == showcase.shape(load_state(remade)), REMAKE
    assert log_shapes(FIXTURE) == log_shapes(remade), REMAKE
    assert top_files(FIXTURE) == top_files(remade), REMAKE
    assert summary_headings(FIXTURE) == summary_headings(remade), REMAKE


def test_d0009_ac15_shape_finds_difference():
    """D0009-AC-15: 形の比べ方そのものが、キー・型・並びの長さの違いを見つけ、値の違いは見逃す。"""
    shape = showcase.shape
    assert shape({"a": 1, "b": [1, "x"]}) == shape({"a": 2, "b": [3, "y"]})
    assert shape({"a": 1}) != shape({"b": 1})
    assert shape({"a": 1}) != shape({"a": "1"})
    assert shape({"a": None}) != shape({"a": 1})
    assert shape([1, 2]) != shape([1])
    assert shape({"a": {"x": 1}}) != shape({"a": {"x": 1, "y": 2}})


def test_d0009_ac15_showcase_scenario():
    """D0009-AC-15: 見本は台本どおり：最後は PASSED、要件定義で修正の依頼が1回、検証は fail のあと pass、実装は2回。"""
    fixture_files()
    state = load_state(FIXTURE)
    runs = state["runs"]
    assert state["final"] == "PASSED"
    reviews = [(h["stage"], h["review"]) for h in runs if "review" in h]
    assert reviews == [
        ("requirements", "revise"),
        ("requirements", "approved"),
        ("design", "approved"),
        ("red", "approved"),
    ]
    assert [h["verdict"]["status"] for h in runs if "verdict" in h] == ["fail", "pass"]
    assert [h["stage"] for h in runs if "seq" in h] == [
        "requirements", "requirements", "design", "red", "implement", "test", "implement", "test",
    ]
    # 段の実行（seq あり）の result は文。テスト先行の判定は seq の無い行の result
    reds = [h["result"] for h in runs if h.get("stage") == "red" and "result" in h and "seq" not in h]
    assert len(reds) == 1 and reds[0]["status"] == "red"
    assert {t["criterion"] for t in reds[0]["tests"]} == {"AC-01", "AC-02", "AC-03"}


def test_d0009_ac15_showcase_has_usage_and_no_session_id():
    """D0009-AC-15: 見本は使用量（usage_summary と段ごとの metrics）を持ち、session_id はどこも null。"""
    fixture_files()
    state = load_state(FIXTURE)
    usage = state["usage_summary"]
    assert usage["tokens"]["output"] > 0
    assert usage["by_model"], "モデル別の使用量が無い"
    assert {"five_hour", "seven_day"} <= set(usage["rate_limits"])
    assert state["total_cost_usd"] > 0
    assert state["pending_review"] is None
    stage_runs = [h for h in state["runs"] if "seq" in h]
    assert stage_runs
    for h in stage_runs:
        assert h["session_id"] is None, h["seq"]
        assert h["metrics"]["tokens"]["output"] > 0, h["seq"]
    for path in sorted((FIXTURE / "logs").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if "session_id" in row:
                assert row["session_id"] is None, path.name


# ---- D0017：動きと各段の時間（見本は 4 つ：完了・動いている ×2・確認待ち） ----

OFFSET_TEXT = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}"
# 見本の名前 → (止める段のログ名, 確認で止めるか)。台本の途中で止めた記録（表は showcase.py の1か所に置く）
PARTIALS = showcase.PARTIAL_FIXTURES
ALL_FIXTURES = ["showcase", *PARTIALS]


def fixture_dir(name: str) -> Path:
    return FIXTURE.parent / name


def prompt_lines(work: Path) -> list[tuple[str, dict]]:
    out = []
    for path in sorted((work / "logs").glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        out += [(path.name, row) for row in rows if row.get("_type") == "Prompt"]
    return out


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_d0017_showcase_prompt_lines_have_at_with_offset(name):
    """D0017-AC-34: どの見本でも、段のログの Prompt 行に at があり、オフセットつきの決まった時刻（+00:00）で、手元の時刻帯が入らない。"""
    import re

    work = fixture_dir(name)
    assert work.is_dir(), f"見本の記録 {work.as_posix()} がありません。python tests/showcase.py で作ってください"
    rows = prompt_lines(work)
    assert rows, name
    for log_name, row in rows:
        assert re.fullmatch(OFFSET_TEXT, row.get("at", "")), f"{name}/{log_name}: {row.get('at')!r}"
        assert row["at"].endswith("+00:00"), f"{name}/{log_name}"


def test_d0017_showcase_running_is_open_on_07_implement_2():
    """D0017-AC-34: showcase_running は 07_implement_2 が動いている（ResultMessage が無い）。差し戻しは 1 回あったが、実装の 2 回目はまだ終わっていない。"""
    work = fixture_dir("showcase_running")
    assert work.is_dir()
    state = load_state(work)
    assert state["final"] is None and state["pending_review"] is None
    stage_runs = [h for h in state["runs"] if "seq" in h]
    assert [h["stage"] for h in stage_runs][-2:] == ["implement", "test"]
    assert stage_runs[-1]["seq"] == 6
    log = work / "logs" / "07_implement_2.jsonl"
    types = [json.loads(line)["_type"] for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert types[0] == "Prompt" and "ResultMessage" not in types
    assert not (work / "99_summary.md").exists()


def test_d0017_showcase_running_next_is_open_on_08_test_2():
    """D0017-AC-37: showcase_running_next は 08_test_2 が動き、実装は 2 回終わっている（差し戻しの矢印の回数が 1 に増えた見本）。"""
    work = fixture_dir("showcase_running_next")
    assert work.is_dir()
    state = load_state(work)
    assert state["final"] is None
    implements = [h for h in state["runs"] if h.get("stage") == "implement" and "seq" in h]
    assert [h["attempt"] for h in implements] == [1, 2]
    log = work / "logs" / "08_test_2.jsonl"
    types = [json.loads(line)["_type"] for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert types[0] == "Prompt" and "ResultMessage" not in types


def test_d0017_showcase_waiting_stops_at_requirements_review_with_since():
    """D0017-AC-35: showcase_waiting は要件定義の確認で止まり、pending_review.since にオフセットつきの待ち始めの時刻がある。"""
    import re

    work = fixture_dir("showcase_waiting")
    assert work.is_dir()
    state = load_state(work)
    assert state["final"] is None
    pending = state["pending_review"]
    assert pending["stage"] == "requirements"
    assert re.fullmatch(OFFSET_TEXT, pending["since"]) and pending["since"].endswith("+00:00")
    assert [h["stage"] for h in state["runs"] if "seq" in h] == ["requirements"]


@pytest.mark.parametrize("name", list(PARTIALS))
def test_d0017_showcase_partial_matches_engine_shape(name, tmp_path):
    """D0017-AC-34: 台本の途中で止めた見本は、今の本体で止めて作り直したものと形が同じ（state.json・logs/・成果物）。"""
    stop_at, pause = PARTIALS[name]
    remade_work = showcase.build_showcase_partial(tmp_path / "myapp", stop_at, pause=pause)
    work = fixture_dir(name)
    assert work.is_dir(), f"見本の記録 {work.as_posix()} がありません。python tests/showcase.py で作ってください"
    assert showcase.shape(load_state(work)) == showcase.shape(load_state(remade_work)), REMAKE
    assert log_shapes(work) == log_shapes(remade_work), REMAKE
    assert top_files(work) == top_files(remade_work), REMAKE


@pytest.mark.parametrize("name", list(PARTIALS))
def test_d0017_showcase_partial_has_no_local_info(name, tmp_path):
    """D0017-AC-34: 台本の途中で止めた見本にも手元の情報が無く、作り直したものに一時フォルダのパスが入らない。"""
    work = fixture_dir(name)
    assert work.is_dir()
    found = []
    for path in sorted(p for p in work.rglob("*") if p.is_file()):
        found += [f"{path.relative_to(work).as_posix()}: {f}" for f in test_rules.local_info_in(path.read_text(encoding="utf-8"))]
    assert found == []
    stop_at, pause = PARTIALS[name]
    remade_work = showcase.build_showcase_partial(tmp_path / "myapp", stop_at, pause=pause)
    needles = {str(tmp_path), tmp_path.as_posix(), json.dumps(str(tmp_path))[1:-1]}
    leaked = [p.name for p in sorted(remade_work.rglob("*")) if p.is_file() and any(n in p.read_text(encoding="utf-8") for n in needles)]
    assert leaked == []


def test_d0017_showcase_runner_still_rejects_calls_outside_the_script(tmp_path):
    """D0017-AC-34: ShowcaseRunner は台本の外の呼び出しを今までどおり RuntimeError にする（stop_at を足しても緩めない）。"""
    import asyncio

    runner = showcase.ShowcaseRunner()
    with pytest.raises(RuntimeError):
        asyncio.run(runner(None, "x", None, resume=None, log_name="99_unknown"))


def test_d0009_ac15_showcase_has_no_local_info(remade, tmp_path):
    """D0009-AC-15: 見本のどのファイルにも手元の情報（ユーザー名の入ったパス・メールアドレス）が無く、作り直したものに一時フォルダのパスが入らない。"""
    found = []
    for path in fixture_files():
        text = path.read_text(encoding="utf-8")
        found += [f"{path.relative_to(FIXTURE).as_posix()}: {f}" for f in test_rules.local_info_in(text)]
    assert found == []
    needles = {str(tmp_path), tmp_path.as_posix(), json.dumps(str(tmp_path))[1:-1]}
    leaked = []
    for path in sorted(p for p in remade.rglob("*") if p.is_file()):
        text = path.read_text(encoding="utf-8")
        leaked += [path.relative_to(remade).as_posix() for n in needles if n in text]
    assert leaked == []
