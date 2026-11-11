"""D0090：会話の道（pipe-in-gen chat）の回数を state.json の flow に寄せる（issue #140）。

会話の道も回数を flow: {steps, retries} に書き、SDK の道と同じ関数 read_flow で読む。chat.steps・chat.retries は同じ値を写して残す。
動き（止まる回・文・chat status の値）は変えない。SDK は呼ばない（SDK の道は偽の runner、会話の道は外の入口 chat_cmd.main）。
ファイルは tmp_path の中だけに作る。

新しい部品 pipe_in.engine.flow は、それを見るテストの関数の中で遅く読む（まだ無いうちは、それを見るテストだけが
ModuleNotFoundError で落ち、ほかは flow の鍵が無い・数が合わないなどの本当の理由で落ちる）。
今の作りのままで通るもの（守り続ける検査）は、説明の末尾に「（今のまま通る。守る）」と書く。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from chat_support import Run, no_sdk, pipe_toml, stage_toml  # noqa: F401
from test_pipe_flow import FAIL, PASS, ScriptedRunner
from test_pipe_flow import make_pipe as make_sdk_pipe
from test_pipe_flow import run as run_sdk
from test_pipe_flow_counts import flow_of as sdk_flow_of
from test_pipe_flow_counts import resume as sdk_resume
from test_pipe_flow_counts import start as sdk_start
from test_state_schema import TABLE, build_chat, check_against_table

from pipe_in.engine.checkpoint import Decision
from pipe_in.engine.pipeline import Exit

pytestmark = pytest.mark.usefixtures("no_sdk")

A_CHECK = "[stages.check]\nverdict = true\nmax_retries = 1\n"
DROP = object()  # flow の鍵ごと消す印（古い記録）


# ---- 道具 -------------------------------------------------------------------------------------------


def three(head: str = "") -> str:
    """a（検証あり・max_retries = 1）→ b（人の確認）→ c の3段。"""
    return pipe_toml(stage_toml("a", extra=A_CHECK), stage_toml("b", extra="review = true\n"), stage_toml("c"), head=head)


def plain(n: int, head: str = "") -> str:
    """検証も確認も無い n 段（s1 … sn）。"""
    return pipe_toml(*[stage_toml(f"s{i}") for i in range(1, n + 1)], head=head)


def chat_flow(r: Run) -> dict[str, Any]:
    state = r.state()
    assert "flow" in state, f"state.json に flow が無い（鍵: {list(state)}）"
    assert isinstance(state["flow"], dict), f"flow が辞書に書き直されていない: {state['flow']!r}"
    return state["flow"]


def rewrite(r: Run, change) -> None:
    data = r.state()
    change(data)
    (r.run_dir / "state.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def set_counts(r: Run, *, flow: Any = DROP, steps: Any = None, retries: Any = None) -> None:
    """記録の回数を書き換える。flow が DROP なら flow の鍵を消す（古い記録）。steps・retries は chat の節に書く。"""

    def change(d: dict[str, Any]) -> None:
        if flow is DROP:
            d.pop("flow", None)
        else:
            d["flow"] = flow
        if steps is not None:
            d["chat"]["steps"] = steps
        if retries is not None:
            d["chat"]["retries"] = dict(retries)

    rewrite(r, change)


def stages_run(r: Run) -> list[str]:
    return [x["stage"] for x in r.state()["runs"] if "seq" in x]


def drive_sdk(root: Path, toml: str, a_results: list[str], decisions: list[str]) -> list[tuple[str, dict[str, Any]]]:
    """SDK の道で台本を流し、止まるたびの (終わり方, flow) を返す。"""
    pipe = make_sdk_pipe(root, toml, "hp")
    runner = ScriptedRunner(pipe, {"a": [PASS if x == "pass" else FAIL() for x in a_results]})
    result = sdk_start(root, pipe, runner)
    points = [(result.name, sdk_flow_of(root, pipe))]
    for d in decisions:
        assert result == Exit.AWAITING_REVIEW, f"確認で止まっていないのに答えようとした: {result}"
        result = sdk_resume(root, pipe, runner, Decision("approve") if d == "approve" else Decision("revise", "直して"))
        points.append((result.name, sdk_flow_of(root, pipe)))
    return points


def advance_chat(r: Run, a_results: list[str]) -> str:
    """会話の道で、確認待ちか終わりまで進める。止まった所の名前（AWAITING_REVIEW か final）を返す。"""
    while True:
        out = r.next()
        if out["action"] == "run_stage":
            if out["stage"] == "a":
                res = a_results.pop(0)
                r.finish("a", status=res, problems=("直す点",) if res == "fail" else ())
            else:
                r.finish(out["stage"])
        elif out["action"] == "await_review":
            return "AWAITING_REVIEW"
        elif out["action"] == "finished":
            return str(out["final"])
        else:
            raise AssertionError(out)


def drive_chat(root: Path, toml: str, a_results: list[str], decisions: list[str]) -> list[tuple[str, dict[str, Any]]]:
    """会話の道で同じ台本を流し、止まるたびの (終わり方, flow) を返す。"""
    r = Run(root)
    r.ready(toml)
    left = list(a_results)
    where = advance_chat(r, left)
    points = [(where, chat_flow(r))]
    for d in decisions:
        assert where == "AWAITING_REVIEW", f"確認で止まっていないのに答えようとした: {where}"
        if d == "approve":
            r.review("approved")
        else:
            r.review("revise", "直して")
        where = advance_chat(r, left)
        points.append((where, chat_flow(r)))
    return points


# ---- AC-01：始めた記録の flow ----------------------------------------------------------------------------


def test_d0090_ac01_startはflowを0と空で書き鍵はwarningsの次でopenの前(tmp_path):
    """D0090-AC-01: chat start の記録に flow があり、steps が 0・retries が {}。鍵の並びは warnings → flow → open。chat.steps・chat.retries も 0 と {} を写す。"""
    r = Run(tmp_path)
    r.make(three())
    assert r.start()["ok"] is True
    state = r.state()
    assert "flow" in state, f"state.json に flow が無い（鍵: {list(state)}）"
    assert state["flow"] == {"steps": 0, "retries": {}}
    keys = list(state)
    assert keys.index("flow") == keys.index("warnings") + 1, keys
    assert keys.index("open") == keys.index("flow") + 1, keys
    assert state["chat"]["steps"] == 0 and state["chat"]["retries"] == {}


# ---- AC-02：2つの道で同じ台本 ----------------------------------------------------------------------------

SCRIPTS = [
    # (名前, a の結果の列, 確認への答えの列, 止まるたびの期待 (終わり方, steps, retries))
    ("通る_確認で止まる", ["pass"], [], [("AWAITING_REVIEW", 2, {})]),
    ("不合格で戻す", ["fail", "pass"], ["approve"], [("AWAITING_REVIEW", 3, {"a": 1}), ("PASSED", 4, {"a": 1})]),
    ("上限に達する", ["fail", "fail"], [], [("TEST_FAILED", 2, {"a": 1})]),
    ("確認で承認", ["pass"], ["approve"], [("AWAITING_REVIEW", 2, {}), ("PASSED", 3, {})]),
    ("確認でrevise", ["pass"], ["revise", "approve"], [("AWAITING_REVIEW", 2, {}), ("AWAITING_REVIEW", 2, {}), ("PASSED", 3, {})]),
]


@pytest.mark.parametrize("a_results,decisions,expected", [s[1:] for s in SCRIPTS], ids=[s[0] for s in SCRIPTS])
def test_d0090_ac02_二つの道で同じ台本を流すとflowが各時点で一致する(tmp_path, a_results, decisions, expected):
    """D0090-AC-02: 同じパイプ・同じ台本を SDK の道と会話の道で流し、止まるたび（確認待ち・終わり）の flow（steps・retries）が一致する。"""
    want = [(where, {"steps": steps, "retries": retries}) for where, steps, retries in expected]
    assert drive_sdk(tmp_path / "sdk", three(), a_results, decisions) == want, "SDK の道の期待（台本の誤りでなければ、本体の今の動きと違う）"
    assert drive_chat(tmp_path / "chat", three(), a_results, decisions) == want


def test_d0090_ac02_max_stepsで止まった時点のstepsはsdkがmax_steps足す1で会話の道がmax_steps(tmp_path):
    """D0090-AC-02: 違う1点を固定する。max_steps = 2 の3段で、止まった時点の flow.steps は、SDK の道が 3（増やしてから判定する）、
    会話の道が 2（判定してから増やす。chat status が止める前の値を見せているため）。どちらも3段目は流さない。"""
    root_sdk, root_chat = tmp_path / "sdk", tmp_path / "chat"
    pipe = make_sdk_pipe(root_sdk, plain(3, "max_steps = 2\n"), "hp")
    runner = ScriptedRunner(pipe)
    assert run_sdk(root_sdk, pipe, runner) == Exit.STAGE_ERROR
    assert runner.names() == ["s1", "s2"]
    assert sdk_flow_of(root_sdk, pipe)["steps"] == 3

    r = Run(root_chat)
    r.ready(plain(3, "max_steps = 2\n"))
    r.run_and_finish("s1")
    r.run_and_finish("s2")
    out = r.next()
    assert out["action"] == "finished" and out["final"] == "STAGE_ERROR", out
    assert stages_run(r) == ["s1", "s2"]
    assert chat_flow(r)["steps"] == 2


@pytest.mark.parametrize("n", [1, 2, 3])
def test_d0090_ac02_止まる回は二つの道で同じ(tmp_path, n):
    """D0090-AC-02: max_steps = n のとき、2つの道とも n 段目までは流せ、n + 1 段目で STAGE_ERROR で止まる（flow の値を見ない。今のまま通る。守る）。"""
    root_sdk, root_chat = tmp_path / "sdk", tmp_path / "chat"
    head = f"max_steps = {n}\n"
    names = [f"s{i}" for i in range(1, n + 2)]
    pipe = make_sdk_pipe(root_sdk, plain(n + 1, head), "hp")
    runner = ScriptedRunner(pipe)
    assert run_sdk(root_sdk, pipe, runner) == Exit.STAGE_ERROR
    assert runner.names() == names[:n]

    r = Run(root_chat)
    r.ready(plain(n + 1, head))
    for name in names[:n]:
        r.run_and_finish(name)
    out = r.next()
    assert out["action"] == "finished" and out["final"] == "STAGE_ERROR", out
    assert stages_run(r) == names[:n]


# ---- AC-03：flow の無い古い記録を続ける ----------------------------------------------------------------------


def test_d0090_ac03_flowの無い古い記録をnextで続けflowが足される(tmp_path):
    """D0090-AC-03: flow が無く chat.steps だけが 1 の古い記録を chat next で続けると、続きの数（2）が数えられ、flow が足されて chat.steps と同じ値になる。"""
    r = Run(tmp_path)
    r.ready(three())
    set_counts(r, flow=DROP, steps=1, retries={})
    r.run_next("a")
    assert chat_flow(r) == {"steps": 2, "retries": {}}
    assert r.state()["chat"]["steps"] == 2


def test_d0090_ac03_古い記録のsteps上限はnextで止まる(tmp_path):
    """D0090-AC-03: flow が無く chat.steps が max_steps の古い記録は、次の chat next で STAGE_ERROR で止まる（止まるところは今のまま通る）。続けた後の記録に flow が足され、steps は止める前の値のまま。"""
    r = Run(tmp_path)
    r.ready(three("max_steps = 2\n"))
    set_counts(r, flow=DROP, steps=2, retries={})
    out = r.next()
    assert out["action"] == "finished" and out["final"] == "STAGE_ERROR", out
    assert any("max_steps" in w for w in r.state()["warnings"])
    assert chat_flow(r) == {"steps": 2, "retries": {}}


def test_d0090_ac03_古い記録のretries上限は次の不合格で止まる(tmp_path):
    """D0090-AC-03: flow が無く chat.retries が {a: 1}（max_retries = 1）の古い記録は、次の不合格で TEST_FAILED で止まる（止まるところは今のまま通る）。続けた後の記録に flow が足され、続きの数と一致する。"""
    r = Run(tmp_path)
    r.ready(three())
    set_counts(r, flow=DROP, steps=0, retries={"a": 1})
    r.run_next("a")
    out = r.finish("a", status="fail", problems=("直す点",))
    assert out["result"] == "fail" and out["final"] == "TEST_FAILED", out
    assert chat_flow(r) == {"steps": 1, "retries": {"a": 1}}


def test_d0090_ac03_古い記録をreviewで続けflowが足される(tmp_path):
    """D0090-AC-03: 確認待ちで止まった古い記録（flow 無し・chat.steps = 2）を chat review approved で続けると、flow が足され、chat.steps と同じ値になる。"""
    r = Run(tmp_path)
    r.ready(three())
    r.run_and_finish("a", status="pass")
    r.run_and_finish("b")
    assert r.state()["pending_review"]
    set_counts(r, flow=DROP)
    assert r.review("approved")["answer"] == "approved"
    assert chat_flow(r) == {"steps": 2, "retries": {}}
    assert r.state()["chat"]["steps"] == 2


# ---- AC-04：止まる文と終わりの形 ----------------------------------------------------------------------------


def test_d0090_ac04_max_retriesで止まる文と終わりの形が今と同じ(tmp_path):
    """D0090-AC-04: max_retries = 1 で2回目の不合格のとき、TEST_FAILED で終わり、終わりの文・final・99_summary.md の結果の文は今のまま（今のまま通る。守る）。"""
    from pipe_in.pipe.pipeline import exit_message

    r = Run(tmp_path)
    r.ready(three())
    r.run_next("a")
    assert r.finish("a", status="fail", problems=("直す点",))["result"] == "fail"
    r.run_next("a")
    out = r.finish("a", status="fail", problems=("直す点",))
    assert out["final"] == "TEST_FAILED"
    assert "差し戻しの上限まで検証に通らなかったので、ここで終えました" in out["message"], out["message"]
    assert r.state()["final"] == "TEST_FAILED"
    summary = (r.run_dir / "99_summary.md").read_text(encoding="utf-8")
    assert exit_message(Exit.TEST_FAILED) in summary
    assert r.next()["action"] == "finished"


# ---- AC-05：chat status ---------------------------------------------------------------------------------------

STATUS_CASES = [
    # (名前, flow, chat.steps, chat.retries, 期待する steps, 期待する retries)
    ("新しい記録", {"steps": 3, "retries": {"a": 1}}, 3, {"a": 1}, 3, {"a": 1}),
    ("古い記録", DROP, 3, {"a": 1}, 3, {"a": 1}),
    ("食い違い_chatが大きい", {"steps": 1, "retries": {}}, 3, {"a": 1}, 3, {"a": 1}),
    ("食い違い_flowが大きい", {"steps": 5, "retries": {"a": 2, "b": 1}}, 2, {"a": 1}, 5, {"a": 2, "b": 1}),
    ("食い違い_段ごとに大きいほう", {"steps": 2, "retries": {"a": 1}}, 2, {"b": 2}, 2, {"a": 1, "b": 2}),
]


@pytest.mark.parametrize("flow,chat_steps,chat_retries,steps,retries", [c[1:] for c in STATUS_CASES], ids=[c[0] for c in STATUS_CASES])
def test_d0090_ac05_statusは新旧の記録で同じ値と文を返し記録を書き換えない(tmp_path, flow, chat_steps, chat_retries, steps, retries):
    """D0090-AC-05: chat status は、新しい記録でも古い記録でも同じ steps・retries（と文の「段を流した回数」）を返し、記録（state.json のバイト）を書き換えない。
    食い違う記録では大きいほう（retries は段ごとに大きいほう）を返す。"""
    r = Run(tmp_path)
    r.ready(three())
    set_counts(r, flow=flow, steps=chat_steps, retries=chat_retries)
    before = r.state_text()
    out = r.cmd("status")
    assert r.state_text() == before, "status が記録を書き換えた"
    assert out["steps"] == steps
    assert out["retries"] == retries
    assert f"段を流した回数: {steps}" in out["message"], out["message"]


# ---- AC-07：壊れた flow・食い違う記録 ---------------------------------------------------------------------------

GOOD = {"a": 2}
BROKEN = [
    # (名前, 書く flow, 壊れていない部分の steps, 壊れていない部分の retries)
    ("辞書でない_配列", [], 0, {}),
    ("辞書でない_文字", "x", 0, {}),
    ("辞書でない_数", 3, 0, {}),
    ("辞書でない_null", None, 0, {}),
    ("steps_負", {"steps": -1, "retries": GOOD}, 0, GOOD),
    ("steps_文字", {"steps": "x", "retries": GOOD}, 0, GOOD),
    ("steps_真偽", {"steps": True, "retries": GOOD}, 0, GOOD),
    ("steps_小数", {"steps": 1.5, "retries": GOOD}, 0, GOOD),
    ("retries_配列", {"steps": 4, "retries": ["a"]}, 4, {}),
    ("retries_文字", {"steps": 4, "retries": "x"}, 4, {}),
    ("retries_数", {"steps": 4, "retries": 3}, 4, {}),
    ("段の値_壊れたものだけ0", {"steps": 4, "retries": {"neg": -1, "str": "x", "bool": True, "float": 1.0, "ok": 2}}, 4, {"ok": 2}),
]


def merged(x: dict[str, int], y: dict[str, int]) -> dict[str, int]:
    return {k: max(x.get(k, 0), y.get(k, 0)) for k in set(x) | set(y) if max(x.get(k, 0), y.get(k, 0)) > 0}


@pytest.mark.parametrize("chat_counts", [(0, {}), (3, {"a": 1})], ids=["chatは0", "chatは正しい"])
@pytest.mark.parametrize("flow,valid_steps,valid_retries", [b[1:] for b in BROKEN], ids=[b[0] for b in BROKEN])
def test_d0090_ac07_壊れたflowは壊れた部分だけ0で読み落ちない(tmp_path, flow, valid_steps, valid_retries, chat_counts):
    """D0090-AC-07: flow が壊れた記録を chat next で続けても落ちず、壊れた部分だけ 0 として読む。chat.* が 0 なら 0 のまま、
    chat.* が正しければ大きいほうが効く。続けた後の flow は、読んだ数に 1 回分を足した値。"""
    chat_steps, chat_retries = chat_counts
    r = Run(tmp_path)
    r.ready(three())
    set_counts(r, flow=flow, steps=chat_steps, retries=chat_retries)
    r.run_next("a")
    got = chat_flow(r)
    assert type(got["steps"]) is int, f"flow.steps が整数に書き直されていない: {got['steps']!r}"
    assert got["steps"] == max(valid_steps, chat_steps) + 1
    assert {k: v for k, v in got["retries"].items() if v} == merged(valid_retries, chat_retries)


def test_d0090_ac07_食い違う記録は大きいほうを採り上限が甘くならない_steps(tmp_path):
    """D0090-AC-07: flow.steps と chat.steps が食い違う記録は、大きいほう（どちらも max_steps = 2 に達している側）が効き、次の chat next で止まる。
    flow が小さいほうは今のまま通る（守る）。flow が大きいほうは、flow を読んでいないうちは止まらない。"""
    for name, flow_steps, chat_steps in [("flowが小さい", 0, 2), ("flowが大きい", 2, 0)]:
        r = Run(tmp_path / name)
        r.ready(three("max_steps = 2\n"))
        set_counts(r, flow={"steps": flow_steps, "retries": {}}, steps=chat_steps, retries={})
        out = r.next()
        assert out["action"] == "finished" and out["final"] == "STAGE_ERROR", f"{name}: {out}"


def test_d0090_ac07_食い違う記録は大きいほうを採り上限が甘くならない_retries(tmp_path):
    """D0090-AC-07: flow.retries と chat.retries が食い違う記録は、段ごとに大きいほうが効き、max_retries = 1 の段は次の不合格で TEST_FAILED で止まる。
    flow が小さいほうは今のまま通る（守る）。flow が大きいほうは、flow を読んでいないうちは止まらない。"""
    for name, flow_retries, chat_retries in [("flowが小さい", {}, {"a": 1}), ("flowが大きい", {"a": 1}, {})]:
        r = Run(tmp_path / name)
        r.ready(three())
        set_counts(r, flow={"steps": 0, "retries": flow_retries}, steps=0, retries=chat_retries)
        r.run_next("a")
        out = r.finish("a", status="fail", problems=("直す点",))
        assert out.get("final") == "TEST_FAILED", f"{name}: {out}"


# ---- AC-08：read_flow の置き場所 ---------------------------------------------------------------------------------


def test_d0090_ac08_read_flowはpipelineからも同じ名前で読める():
    """D0090-AC-08: read_flow は pipe_in.engine.flow にあり、pipe_in.pipe.pipeline からも同じものを読める。"""
    from pipe_in.engine import flow as engine_flow
    from pipe_in.pipe import pipeline

    assert engine_flow.read_flow is pipeline.read_flow


# ---- AC-09：共通の表 ---------------------------------------------------------------------------------------------


def test_d0090_ac09_表のchat行はflowを任意の鍵として持ち新旧の記録が通る(tmp_path):
    """D0090-AC-09: 共通の表の chat の行は flow を任意の鍵に持ち（鍵の並びには入れない）、flow のある記録も、flow を消した古い記録も、表の検査が通る。"""
    row = TABLE["kinds"]["chat"]
    assert "flow" in row["optional_keys"] and "flow" not in row["keys"]
    state = build_chat(tmp_path)
    assert "flow" in state, f"state.json に flow が無い（鍵: {list(state)}）"
    check_against_table(state, "chat")
    check_against_table({k: v for k, v in state.items() if k != "flow"}, "chat")
