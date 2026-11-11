"""D0081：やり直しの回数（steps・retries）を state.json の flow に持たせ、確認をはさんでも max_steps・max_retries が効くことを、SDK を呼ばずに確かめる。

偽の runner（tests/test_pipe_flow.py の ScriptedRunner）で、確認で止める → --review で続ける、を最初から最後まで通す。
ファイルは tmp_path の中だけに作る。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from test_pipe_flow import FAIL, PASS, ScriptedRunner, cfg_for, make_pipe, pipe_toml, stage_toml
from test_state_schema import TABLE, build_sdk, check_against_table

from pipe_in.engine.checkpoint import Decision
from pipe_in.engine.pipeline import STATE, Exit
from pipe_in.pipe import definition as pd
from pipe_in.pipe.pipeline import LinearPipeline, read_flow

APPROVE = Decision("approve")


# ---- 道具 -------------------------------------------------------------------------------------------


def start(project: Path, pipe: pd.PipeDef, runner: ScriptedRunner, text: str | None = "やること", from_stage: str | None = None) -> Exit:
    """確認で止める組み立て（--pause）で流し始める。"""
    cfg = cfg_for(project, pipe, auto_approve=False, pause_for_review=True)
    return asyncio.run(LinearPipeline(cfg, pipe, runner=runner).run(text, from_stage))


def resume(project: Path, pipe: pd.PipeDef, runner: ScriptedRunner, decision: Decision = APPROVE) -> Exit:
    """止まった実行を --review で続ける（新しい LinearPipeline。回数は記録からしか引き継げない）。"""
    cfg = cfg_for(project, pipe, auto_approve=False, pause_for_review=True)
    return asyncio.run(LinearPipeline(cfg, pipe, runner=runner).review(decision))


def state_file(project: Path, pipe: pd.PipeDef) -> Path:
    return project / "docs/pipeline" / pipe.name / STATE


def read_state(project: Path, pipe: pd.PipeDef) -> dict[str, Any]:
    return json.loads(state_file(project, pipe).read_text(encoding="utf-8"))


def rewrite_state(project: Path, pipe: pd.PipeDef, change) -> None:
    data = read_state(project, pipe)
    change(data)
    state_file(project, pipe).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def flow_of(project: Path, pipe: pd.PipeDef) -> dict[str, Any]:
    data = read_state(project, pipe)
    assert "flow" in data, f"state.json に flow が無い（鍵: {list(data)}）"
    return data["flow"]


def reviewing(*names: str, tail: tuple[str, ...] = (), head: str = "") -> str:
    """名前の段を順に並べ、names の段には review を付ける。tail の段は確認なし。"""
    stages = [stage_toml(n, "review = true\n") for n in names] + [stage_toml(n) for n in tail]
    return pipe_toml(*stages, head=head)


# 検証で戻して確認で止める形：draw → verify（不合格なら draw へ）→ gate（確認。承認すると verify へ戻る）
LOOP = pipe_toml(
    stage_toml("draw"),
    stage_toml("verify", '[stages.check]\nverdict = true\non_fail = "draw"\nmax_retries = 1\n'),
    stage_toml("gate", 'review = true\nnext = "verify"\n'),
)


# ---- AC-01：確認をはさんでも差し戻しの上限が効く -------------------------------------------------------


def test_d0081_ac01_review_approve_keeps_retry_count_so_limit_holds(tmp_path):
    """D0081-AC-01: max_retries = 1 で、不合格 → 前の段へ戻る → 確認で止まる → approve → もう一度不合格 のとき、差し戻しの上限で終わる（もう 1 回戻らない）。"""
    pipe = make_pipe(tmp_path, LOOP)
    r1 = ScriptedRunner(pipe, {"verify": [FAIL("矢印が逆"), PASS, FAIL("まだ逆"), PASS]})
    assert start(tmp_path, pipe, r1) == Exit.AWAITING_REVIEW
    assert r1.names() == ["draw", "verify", "draw", "verify", "gate"]
    r2 = ScriptedRunner(pipe, {"verify": [FAIL("まだ逆"), PASS]})
    assert resume(tmp_path, pipe, r2) == Exit.TEST_FAILED
    assert r2.names() == ["verify"], "続きで、もう 1 回 draw へ戻している"
    assert read_state(tmp_path, pipe)["final"] == "TEST_FAILED"


# ---- AC-02：止めた時点の記録に回数がある -----------------------------------------------------------------


def test_d0081_ac02_paused_state_has_flow_steps_and_retries(tmp_path):
    """D0081-AC-02: 確認で止めた時点（final が空・pending_review あり）の state.json に、flow.steps（流した回数）と flow.retries（不合格になった段ごとの戻した回数）が入っている。"""
    pipe = make_pipe(tmp_path, LOOP)
    r = ScriptedRunner(pipe, {"verify": [FAIL(), PASS]})
    assert start(tmp_path, pipe, r) == Exit.AWAITING_REVIEW
    data = read_state(tmp_path, pipe)
    assert data["final"] is None and data["pending_review"]
    assert "flow" in data, f"state.json に flow が無い（鍵: {list(data)}）"
    assert data["flow"] == {"steps": 5, "retries": {"verify": 1}}  # draw・verify・draw・verify・gate
    assert "notes" not in data["flow"]


# ---- AC-03：止めて続けた回をまたいで steps を数える --------------------------------------------------------


def test_d0081_ac03_steps_count_across_review_and_max_steps_stops(tmp_path):
    """D0081-AC-03: 止めて続けた回をまたいで steps を数え、max_steps を超えたら STAGE_ERROR・warnings に max_steps を超えた旨が入る。"""
    pipe = make_pipe(tmp_path, reviewing("a", "b", "c", tail=("d",), head="max_steps = 3\n"))
    r = ScriptedRunner(pipe)
    assert start(tmp_path, pipe, r) == Exit.AWAITING_REVIEW
    assert resume(tmp_path, pipe, r) == Exit.AWAITING_REVIEW
    assert resume(tmp_path, pipe, r) == Exit.AWAITING_REVIEW
    assert flow_of(tmp_path, pipe)["steps"] == 3
    assert resume(tmp_path, pipe, r) == Exit.STAGE_ERROR
    assert r.names() == ["a", "b", "c"], "d を流している（回数が数え直しになっている）"
    assert any("max_steps" in w for w in read_state(tmp_path, pipe)["warnings"])


# ---- AC-04：revise は steps に数えない -----------------------------------------------------------------------


def test_d0081_ac04_revise_does_not_add_steps(tmp_path):
    """D0081-AC-04: revise で続けて確認で止まり直しても flow.steps は増えない。続けて approve して次の段を流すと 1 つ増える。"""
    pipe = make_pipe(tmp_path, reviewing("a", "b", tail=("c",)))
    r = ScriptedRunner(pipe)
    assert start(tmp_path, pipe, r) == Exit.AWAITING_REVIEW
    assert flow_of(tmp_path, pipe)["steps"] == 1
    assert resume(tmp_path, pipe, r, Decision("revise", "直して")) == Exit.AWAITING_REVIEW
    assert r.names() == ["a", "a"]
    assert flow_of(tmp_path, pipe)["steps"] == 1
    assert resume(tmp_path, pipe, r) == Exit.AWAITING_REVIEW
    assert flow_of(tmp_path, pipe)["steps"] == 2


def test_d0081_ac04_revise_at_max_steps_is_not_stopped(tmp_path):
    """D0081-AC-04: max_steps ちょうどまで流して止めた実行の revise は、max_steps を超えたことにならない（revise の 1 回は数えず、検査もしない）。"""
    pipe = make_pipe(tmp_path, reviewing("a", "b", head="max_steps = 1\n"))
    r = ScriptedRunner(pipe)
    assert start(tmp_path, pipe, r) == Exit.AWAITING_REVIEW
    assert resume(tmp_path, pipe, r, Decision("revise", "直して")) == Exit.AWAITING_REVIEW
    assert r.names() == ["a", "a"]
    assert flow_of(tmp_path, pipe)["steps"] == 1
    assert resume(tmp_path, pipe, r) == Exit.STAGE_ERROR  # 次の段 b は 2 つ目なので、ここで止まる
    assert r.names() == ["a", "a"]


# ---- AC-05：flow の無い古い記録 ----------------------------------------------------------------------------------


def test_d0081_ac05_record_without_flow_starts_from_zero(tmp_path):
    """D0081-AC-05: flow の鍵が無い記録を --review で続けると、今までと同じに 0 から流れ、終わりの記録には flow が入る。"""
    pipe = make_pipe(tmp_path, reviewing("a", tail=("b",), head="max_steps = 1\n"))
    r = ScriptedRunner(pipe)
    assert start(tmp_path, pipe, r) == Exit.AWAITING_REVIEW
    rewrite_state(tmp_path, pipe, lambda d: d.pop("flow", None))
    assert "flow" not in read_state(tmp_path, pipe)
    assert resume(tmp_path, pipe, r) == Exit.PASSED  # 0 から数えるので、b が 1 つ目になり max_steps = 1 に収まる
    assert r.names() == ["a", "b"]
    assert flow_of(tmp_path, pipe) == {"steps": 1, "retries": {}}


def test_d0081_ac05_old_record_without_schema_gets_flow_but_no_schema(tmp_path):
    """D0081-AC-05: schema の無い古い記録を続けても、schema は足さず、flow は書く。"""
    pipe = make_pipe(tmp_path, reviewing("a", tail=("b",)))
    r = ScriptedRunner(pipe)
    assert start(tmp_path, pipe, r) == Exit.AWAITING_REVIEW

    def old(d: dict[str, Any]) -> None:
        d.pop("flow", None)
        d.pop("schema", None)

    rewrite_state(tmp_path, pipe, old)
    assert resume(tmp_path, pipe, r) == Exit.PASSED
    data = read_state(tmp_path, pipe)
    assert "schema" not in data
    assert "flow" in data, f"state.json に flow が無い（鍵: {list(data)}）"
    assert data["flow"] == {"steps": 1, "retries": {}}


# ---- AC-06：壊れた flow ---------------------------------------------------------------------------------------------

GOOD_RETRIES = {"a": 2}
BROKEN = [
    # (名前, 書く flow, 続けたあとに期待する steps, 期待する retries の読み（段ごと。無い段は 0）)
    ("辞書でない_配列", [], 1, {}),
    ("辞書でない_文字", "x", 1, {}),
    ("辞書でない_数", 3, 1, {}),
    ("辞書でない_null", None, 1, {}),
    ("steps_負", {"steps": -1, "retries": GOOD_RETRIES}, 1, GOOD_RETRIES),
    ("steps_文字", {"steps": "x", "retries": GOOD_RETRIES}, 1, GOOD_RETRIES),
    ("steps_真偽", {"steps": True, "retries": GOOD_RETRIES}, 1, GOOD_RETRIES),
    ("steps_小数", {"steps": 1.5, "retries": GOOD_RETRIES}, 1, GOOD_RETRIES),
    ("retries_配列", {"steps": 4, "retries": ["a"]}, 5, {}),
    ("retries_文字", {"steps": 4, "retries": "x"}, 5, {}),
    ("retries_数", {"steps": 4, "retries": 3}, 5, {}),
    ("段の値_壊れたものだけ0", {"steps": 4, "retries": {"neg": -1, "str": "x", "bool": True, "float": 1.0, "ok": 2}}, 5, {"ok": 2}),
]


@pytest.mark.parametrize("flow,steps,retries", [b[1:] for b in BROKEN], ids=[b[0] for b in BROKEN])
def test_d0081_ac06_broken_flow_reads_broken_parts_as_zero(tmp_path, flow, steps, retries):
    """D0081-AC-06: flow が壊れている記録は、落ちずに --review で続き、壊れた部分を 0 として読む。壊れていない部分は使う。"""
    pipe = make_pipe(tmp_path, reviewing("a", "b", tail=("c",)))
    r = ScriptedRunner(pipe)
    assert start(tmp_path, pipe, r) == Exit.AWAITING_REVIEW
    rewrite_state(tmp_path, pipe, lambda d: d.__setitem__("flow", flow))
    assert resume(tmp_path, pipe, r) == Exit.AWAITING_REVIEW  # b で止まる（b を流して 1 つ増える）
    got = flow_of(tmp_path, pipe)
    assert got["steps"] == steps
    names = set(retries) | {"neg", "str", "bool", "float", "a"}
    assert {n: got["retries"].get(n, 0) for n in names} == {n: retries.get(n, 0) for n in names}


READ_FLOW_CASES = [
    (None, 0, {}),
    ([], 0, {}),
    ("x", 0, {}),
    ({}, 0, {}),
    ({"steps": 3, "retries": {"a": 1, "b": 0}}, 3, {"a": 1, "b": 0}),
    ({"steps": 0, "retries": {}}, 0, {}),
    ({"steps": -1}, 0, {}),
    ({"steps": "3"}, 0, {}),
    ({"steps": True}, 0, {}),
    ({"steps": 2.0}, 0, {}),
    ({"steps": 2, "retries": ["a"]}, 2, {}),
    ({"steps": 2, "retries": {"a": -1, "b": "1", "c": False, "d": 1.0, "e": 4}}, 2, {"e": 4}),
]


@pytest.mark.parametrize("raw,steps,retries", READ_FLOW_CASES)
def test_d0081_ac06_read_flow_is_pure(raw, steps, retries):
    """D0081-AC-06: read_flow は、辞書でなければ全部 0、steps は 0 以上の整数（真偽値・小数・文字を除く）だけ採り、retries は辞書のとき、段ごとに 0 以上の整数だけ採る。"""
    got_steps, got_retries = read_flow(raw)
    assert got_steps == steps
    names = set(retries) | set(got_retries) | {"a", "b", "c", "d"}
    assert {n: got_retries.get(n, 0) for n in names} == {n: retries.get(n, 0) for n in names}
    assert all(type(v) is int and v >= 0 for v in got_retries.values())


# ---- AC-07：--from は 0 から ---------------------------------------------------------------------------------------------


def test_d0081_ac07_from_restarts_counts_from_zero(tmp_path):
    """D0081-AC-07: --from で流し直すと、前の記録に flow が入っていても、新しい記録の flow は 0 から数え直した値になる。"""
    pipe = make_pipe(tmp_path, pipe_toml(stage_toml("a"), stage_toml("b"), stage_toml("c")))
    r1 = ScriptedRunner(pipe)
    cfg = cfg_for(tmp_path, pipe)
    assert asyncio.run(LinearPipeline(cfg, pipe, runner=r1).run("やること")) == Exit.PASSED
    rewrite_state(tmp_path, pipe, lambda d: d.__setitem__("flow", {"steps": 40, "retries": {"b": 5}}))
    r2 = ScriptedRunner(pipe)
    assert asyncio.run(LinearPipeline(cfg_for(tmp_path, pipe), pipe, runner=r2).run(None, "b")) == Exit.PASSED
    assert r2.names() == ["b", "c"]
    assert flow_of(tmp_path, pipe) == {"steps": 2, "retries": {}}


# ---- AC-08：確認をはさんでも検査のある段の attempt が N + 1 を超えない ---------------------------------------------------------


def test_d0081_ac08_check_attempt_never_exceeds_max_retries_plus_one_across_review(tmp_path):
    """D0081-AC-08: max_retries = N で、検査のある 1 つの段が不合格を繰り返すとき、確認をはさんで続けても、その段の check.attempt が N + 1 を超えない。"""
    n = 2
    pipe = make_pipe(
        tmp_path,
        pipe_toml(
            stage_toml("draw", "review = true\n"),
            stage_toml("verify", f'[stages.check]\nverdict = true\non_fail = "draw"\nmax_retries = {n}\n'),
        ),
    )
    r = ScriptedRunner(pipe, {"verify": [FAIL() for _ in range(20)]})
    result = start(tmp_path, pipe, r)
    for _ in range(8):  # 歯止め。上限が効かないと止まらずに回り続ける
        if result != Exit.AWAITING_REVIEW:
            break
        result = resume(tmp_path, pipe, r)
    attempts = [h["check"]["attempt"] for h in read_state(tmp_path, pipe)["runs"] if h.get("stage") == "verify" and "check" in h]
    assert attempts, "検査の記録が無い"
    assert max(attempts) <= n + 1, f"attempt が {max(attempts)} まで増えた（{attempts}）"
    assert result == Exit.TEST_FAILED


# ---- AC-09：記録の形 ---------------------------------------------------------------------------------------------------------


def test_d0081_ac09_linear_record_matches_sdk_row_with_flow(tmp_path):
    """D0081-AC-09: LinearPipeline が書く記録は、共通の表の sdk の行（flow を任意の鍵として）に合う。"""
    pipe = make_pipe(tmp_path, reviewing("a", tail=("b",)))
    assert start(tmp_path, pipe, ScriptedRunner(pipe)) == Exit.AWAITING_REVIEW
    data = read_state(tmp_path, pipe)
    assert "flow" in data, f"state.json に flow が無い（鍵: {list(data)}）"
    assert set(data["flow"]) == {"steps", "retries"}
    check_against_table(data, "sdk")


def test_d0081_ac09_dev_record_has_no_flow(tmp_path):
    """D0081-AC-09: DevPipeline の記録に flow は無い（今のまま通る。書き手を増やさない守り）。"""
    assert "flow" not in build_sdk(tmp_path)


def test_d0081_ac09_new_state_writes_flow_only_when_given():
    """D0081-AC-09: new_state は flow を渡したときだけ書く。位置は warnings の後ろ・runs の前。"""
    from pipe_in.engine.state import new_state

    base = {"started_at": "2026-11-11T10:00:00", "updated_at": "2026-11-11T10:00:00", "pipe": "p", "stages": [], "runs": []}
    flow = {"steps": 3, "retries": {"verify": 1}}
    with_flow = new_state(None, **base, total_cost_usd=0.0, usage_summary={"by_model": {}}, flow=flow)
    assert with_flow["flow"] == flow
    keys = list(with_flow)
    assert keys.index("warnings") < keys.index("flow") < keys.index("runs")


def test_d0081_ac09_new_state_without_flow_has_no_flow_key():
    """D0081-AC-09: new_state は flow を渡さなければ鍵を書かない（今のまま通る。DevPipeline・会話の道の記録を変えない守り）。"""
    from pipe_in.engine.state import new_state

    base = {"started_at": "2026-11-11T10:00:00", "updated_at": "2026-11-11T10:00:00", "pipe": "p", "stages": [], "runs": []}
    assert "flow" not in new_state(None, **base, total_cost_usd=0.0, usage_summary={"by_model": {}})


def test_d0081_ac09_table_sdk_row_lists_flow_as_optional_only_for_sdk():
    """D0081-AC-09: 共通の表の任意の鍵に flow があるのは sdk の行だけ（dev・chat には足さない）。"""
    kinds = TABLE["kinds"]
    assert "flow" in kinds["sdk"]["optional_keys"]
    assert "flow" not in kinds["dev"]["optional_keys"]
    assert "flow" not in kinds["chat"]["optional_keys"]
    assert "flow" not in kinds["sdk"]["keys"]


# ---- FR-07：枠（group）---------------------------------------------------------------------------------------------------


def test_d0081_fr07_group_steps_land_in_flow_steps(tmp_path):
    """D0081-AC-04: （FR-07）枠の段の数が flow.steps に載り、枠の中のやり直し（自分だけ）は steps にも retries にも足されない。"""
    pipe = make_pipe(
        tmp_path,
        pipe_toml(
            stage_toml("a"),
            stage_toml("b", 'group = "g"\n'),
            stage_toml("c", 'group = "g"\n[stages.check]\nverdict = true\nmax_retries = 1\n'),
            stage_toml("d"),
        ),
    )
    r = ScriptedRunner(pipe, {"c": [FAIL(), PASS]})
    cfg = cfg_for(tmp_path, pipe)
    assert asyncio.run(LinearPipeline(cfg, pipe, runner=r).run("やること")) == Exit.PASSED
    assert r.names().count("c") == 2
    assert flow_of(tmp_path, pipe) == {"steps": 4, "retries": {}}
