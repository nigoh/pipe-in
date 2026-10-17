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
