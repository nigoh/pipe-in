"""D0062：パイプの判定（check）の設定と、検証が何回目かを、state.json に残す（本体の記録）。FR-01・FR-02。

SDK は呼ばない。runner を手書きの偽物に差し替える（偽物は tests/test_stage_budget.py の PipeRunner と同じ形を、このファイルの中に小さく持つ。
ほかのテストのファイルは import しない）。ファイルは tmp_path の中にだけ作る。
本体が書く形は、拡張のテストと共通の表 tests/fixtures/check_record.json で結ぶ（budget_record.json と同じ作り）。

- 今の作りのままで通るテストは、名前の末尾を _守る にし、説明の末尾に「（今のまま通る。守る）」と書く。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pipe_in.dev.pipeline import DevPipeline
from pipe_in.engine.checkpoint import Decision
from pipe_in.engine.config import load_config
from pipe_in.engine.pipeline import Exit
from pipe_in.engine.runner import StageRun
from pipe_in.pipe import definition as pd
from pipe_in.pipe.pipeline import LinearPipeline

ROOT = Path(__file__).resolve().parents[1]
TABLE = json.loads((ROOT / "tests" / "fixtures" / "check_record.json").read_text(encoding="utf-8"))
FAIL = {"status": "fail", "summary": "直す点あり", "problems": ["矢印が逆"]}
PASS = {"status": "pass", "summary": "よい", "problems": []}
VERDICT = {"pass": PASS, "fail": FAIL}


# ---- 補助：偽の runner ----------------------------------------------------------------------------


class PipeRunner:
    """パイプの段の偽物。成果物を書き、段ごとに決めた構造化出力を順に返す。呼ばれた (段, resume, 指示) を calls に残す。"""

    def __init__(self, pipe: pd.PipeDef, structured: dict[str, list] | None = None):
        self.outputs = {s.name: s.output for s in pipe.stages}
        self.structured = {k: list(v) for k, v in (structured or {}).items()}
        self.calls: list[tuple[str, str | None, str]] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append((spec.name, resume, prompt))
        (cfg.work_dir / self.outputs[spec.name]).write_text(f"# {spec.name}\n", encoding="utf-8")
        queue = self.structured.get(spec.name)
        data = queue.pop(0) if queue else None
        return StageRun(stage=spec.name, session_id=f"s-{len(self.calls)}", structured=data, cost_usd=0.01, num_turns=1)


class DevRunner:
    """開発フローの偽物。各段の文書を書き、red と test には合格の構造化出力を返す。"""

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        w = cfg.work_dir
        run = StageRun(stage=spec.name, session_id=f"s-{spec.name}", cost_usd=0.01, num_turns=1)
        docs = {
            "requirements": ("01_requirements.md", "# 要件定義書\nAC-01\n"),
            "design": ("02_design.md", "# 設計書\n"),
            "red": ("03_red_tests.md", "# テスト先行\n"),
            "implement": ("04_implementation.md", "## 実装\n"),
        }
        if spec.name in docs:
            name, text = docs[spec.name]
            (w / name).write_text(text, encoding="utf-8")
        if spec.name == "red":
            run.structured = {
                "status": "red",
                "summary": "red です",
                "tests": [{"criterion": "AC-01", "test": "test_AC-01"}],
                "commands": ["pytest -q"],
            }
        if spec.name == "test":
            run.structured = {"status": "pass", "summary": "pass です", "failures": [], "commands": ["pytest -q"]}
        return run


# ---- 補助：パイプ・設定・記録 -----------------------------------------------------------------------


def pipe_stage(name: str, extra: str = "") -> str:
    """成果物が <段>.md の、読むだけの段。extra は段の表の最後に足す行（review = true や [stages.check] など）。"""
    return f'\n[[stages]]\nname = "{name}"\nlabel = "{name}の段"\noutput = "{name}.md"\naccess = "read"\nprompt = "{name}をする"\n{extra}'


def pipe_toml(*stages: str) -> str:
    return '[pipe]\nkind = "linear"\nlabel = "試し"\n' + "".join(stages)


def check_toml(check: dict) -> str:
    """共通の表の check（on_fail・max_retries）を [stages.check] に書く。on_fail が null のときは書かない（自分をやり直す）。"""
    on_fail = "" if check["on_fail"] is None else f'on_fail = "{check["on_fail"]}"\n'
    return f"[stages.check]\nverdict = true\nmax_retries = {check['max_retries']}\n{on_fail}"


def make_pipe(project: Path, toml: str) -> pd.PipeDef:
    d = project / "pipes" / "pipe-in-p"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pipe.toml").write_text(toml, encoding="utf-8")
    return pd.load_pipe(d)


def linear(project: Path, pipe: pd.PipeDef, runner, **kw) -> LinearPipeline:
    cfg = load_config(project, None, auto_approve=kw.pop("auto_approve", True), **kw).for_pipe(pipe.name, own_work_dir=True)
    return LinearPipeline(cfg, pipe, runner=runner)


def run_pipe(project: Path, pipe: pd.PipeDef, runner, **kw) -> Exit:
    return asyncio.run(linear(project, pipe, runner, **kw).run("やること"))


def pipe_state(project: Path) -> dict:
    return json.loads((project / "docs" / "pipeline" / "p" / "state.json").read_text(encoding="utf-8"))


def stage_entry(state: dict, name: str) -> dict:
    (entry,) = [s for s in state["stages"] if s["name"] == name]
    return entry


def checks_of(state: dict, stage: str) -> list[dict]:
    """その段の検証の要素（runs[] の check を持つ要素）を、runs[] に現れる順に。"""
    return [h["check"] for h in state["runs"] if h.get("stage") == stage and "check" in h]


def run_case(project: Path, case: dict) -> tuple[Exit, dict]:
    """共通の表の 1 件：draw → verify（verify に case の check）を、case の results の順に判定を返す偽物で流す。"""
    pipe = make_pipe(project, pipe_toml(pipe_stage("draw"), pipe_stage("verify", check_toml(case["check"]))))
    runner = PipeRunner(pipe, {"verify": [VERDICT[r] for r in case["results"]]})
    return run_pipe(project, pipe, runner), pipe_state(project)


CASES = [pytest.param(c, id=c["memo"]) for c in TABLE["cases"]]


# ---- 共通の表の形 ------------------------------------------------------------------------------------


def test_d0062_ac13_共通の表のkeysは本体が書く2つの鍵と同じ_守る():
    """D0062-AC-13: 共通の表 tests/fixtures/check_record.json の keys は、stages[] の check と runs[] の check の attempt の 2 つで、
    どのケースの written もその範囲に収まる。ケースは 3 つ以上で、自分をやり直す・前の段へ戻す・上限まで落ちたを含む。（今のまま通る。守る）"""
    assert TABLE["keys"] == ["check", "attempt"]
    assert len(TABLE["cases"]) >= 3
    for c in TABLE["cases"]:
        assert set(c) >= {"memo", "check", "results", "exit", "written", "read"}, c
        assert set(c["written"]) == set(TABLE["keys"]), c
    assert any(c["check"]["on_fail"] is None for c in TABLE["cases"])
    assert any(c["check"]["on_fail"] is not None for c in TABLE["cases"])
    assert any(c["exit"] == "TEST_FAILED" for c in TABLE["cases"])


# ---- FR-01：stages[] に check を書く ---------------------------------------------------------------------


@pytest.mark.parametrize("on_fail_text", ["", 'on_fail = "verify"\n'], ids=["省く", "自分の名前"])
def test_d0062_ac01_自分をやり直す判定のstagesにcheckが書かれる(tmp_path, on_fail_text):
    """D0062-AC-01: 判定のある段 verify の on_fail を省くか自分の名前にすると、state.json の stages[] の verify に
    check: {on_fail: null, max_retries: 3} が書かれる。判定の無い段 draw には check の項目が無い。"""
    check = f"[stages.check]\nverdict = true\nmax_retries = 3\n{on_fail_text}"
    pipe = make_pipe(tmp_path, pipe_toml(pipe_stage("draw"), pipe_stage("verify", check)))
    assert run_pipe(tmp_path, pipe, PipeRunner(pipe, {"verify": [PASS]})) == Exit.PASSED
    state = pipe_state(tmp_path)
    verify = stage_entry(state, "verify")
    assert "check" in verify, f"stages[] の verify に check が無い。今の鍵: {sorted(verify)}"
    assert verify["check"] == {"on_fail": None, "max_retries": 3}
    assert "check" not in stage_entry(state, "draw")


def test_d0062_ac01_前の段へ戻す判定のstagesにcheckが書かれる(tmp_path):
    """D0062-AC-01: 判定のある段 verify の on_fail が前の段 draw のとき、stages[] の verify に check: {on_fail: "draw", max_retries: 2} が
    書かれる（段の名前）。判定の無い段 draw には check の項目が無い。"""
    check = '[stages.check]\nverdict = true\nmax_retries = 2\non_fail = "draw"\n'
    pipe = make_pipe(tmp_path, pipe_toml(pipe_stage("draw"), pipe_stage("verify", check)))
    assert run_pipe(tmp_path, pipe, PipeRunner(pipe, {"verify": [PASS]})) == Exit.PASSED
    state = pipe_state(tmp_path)
    verify = stage_entry(state, "verify")
    assert "check" in verify, f"stages[] の verify に check が無い。今の鍵: {sorted(verify)}"
    assert verify["check"] == {"on_fail": "draw", "max_retries": 2}
    assert "check" not in stage_entry(state, "draw")


def test_d0062_ac01_既定のmax_retriesも書かれる(tmp_path):
    """D0062-AC-01: max_retries を書かない判定は、定義の既定（2）が max_retries に書かれる。"""
    pipe = make_pipe(tmp_path, pipe_toml(pipe_stage("draw", "[stages.check]\nverdict = true\n")))
    assert run_pipe(tmp_path, pipe, PipeRunner(pipe, {"draw": [PASS]})) == Exit.PASSED
    entry = stage_entry(pipe_state(tmp_path), "draw")
    assert "check" in entry, f"stages[] の draw に check が無い。今の鍵: {sorted(entry)}"
    assert entry["check"] == {"on_fail": None, "max_retries": 2}


def test_d0062_ac01_開発フローのstagesにcheckは書かれない_守る(tmp_path):
    """D0062-AC-01: 開発フロー（5 段）の state.json の stages[] には、どの段にも check の項目が無い（足すのはパイプだけ）。
    （今のまま通る。守る）"""
    cfg = load_config(tmp_path, None, auto_approve=True)
    assert asyncio.run(DevPipeline(cfg, runner=DevRunner()).run("ログイン画面を作る", "requirements")) == Exit.PASSED
    state = json.loads((tmp_path / "docs" / "pipeline" / "state.json").read_text(encoding="utf-8"))
    assert [s["name"] for s in state["stages"]] == ["requirements", "design", "red", "implement", "test"]
    assert [s["name"] for s in state["stages"] if "check" in s] == []


# ---- FR-02：検証が何回目か（attempt） ---------------------------------------------------------------------


def test_d0062_ac02_検証2回でattemptが1と2(tmp_path):
    """D0062-AC-02: verify の検証が 2 回あった（1 回目 fail → 2 回目 pass）とき、runs[] の check の要素の attempt が 1・2 で書かれる。
    status・problems など、ほかの鍵は今まで通り。"""
    check = '[stages.check]\nverdict = true\non_fail = "draw"\n'
    pipe = make_pipe(tmp_path, pipe_toml(pipe_stage("draw"), pipe_stage("verify", check)))
    assert run_pipe(tmp_path, pipe, PipeRunner(pipe, {"verify": [FAIL, PASS]})) == Exit.PASSED
    checks = checks_of(pipe_state(tmp_path), "verify")
    assert [c["status"] for c in checks] == ["fail", "pass"]
    assert [c.get("attempt") for c in checks] == [1, 2], f"attempt が書かれていない。今の鍵: {[sorted(c) for c in checks]}"
    assert checks[0]["problems"] == ["矢印が逆"] and checks[0]["summary"] == "直す点あり"


def test_d0062_ac02_段ごとにattemptを数える(tmp_path):
    """D0062-AC-02: 判定のある段が 2 つあるとき、attempt は段ごとに 1 から数える（draw が 1 回目 fail → 2 回目 pass、verify は 1 回目 pass なら、
    draw は 1・2、verify は 1）。"""
    pipe = make_pipe(
        tmp_path,
        pipe_toml(pipe_stage("draw", "[stages.check]\nverdict = true\n"), pipe_stage("verify", "[stages.check]\nverdict = true\n")),
    )
    assert run_pipe(tmp_path, pipe, PipeRunner(pipe, {"draw": [FAIL, PASS], "verify": [PASS]})) == Exit.PASSED
    state = pipe_state(tmp_path)
    assert [c.get("attempt") for c in checks_of(state, "draw")] == [1, 2], "draw の attempt"
    assert [c.get("attempt") for c in checks_of(state, "verify")] == [1], "verify の attempt"


def test_d0062_ac03_上限まで落ちるとattempt1から3がすべてfail(tmp_path):
    """D0062-AC-03: max_retries = 2 で、検証がずっと fail の実行は TEST_FAILED で終わり、同じ段の check の要素が 3 つ
    （attempt 1〜3）すべて status = fail で書かれる（上限 + 1 回目の検証で止まる）。"""
    check = '[stages.check]\nverdict = true\nmax_retries = 2\non_fail = "draw"\n'
    pipe = make_pipe(tmp_path, pipe_toml(pipe_stage("draw"), pipe_stage("verify", check)))
    runner = PipeRunner(pipe, {"verify": [FAIL, FAIL, FAIL]})
    assert run_pipe(tmp_path, pipe, runner) == Exit.TEST_FAILED
    state = pipe_state(tmp_path)
    assert state["final"] == "TEST_FAILED"
    checks = checks_of(state, "verify")
    assert [c["status"] for c in checks] == ["fail", "fail", "fail"]
    assert [c.get("attempt") for c in checks] == [1, 2, 3], f"attempt が書かれていない。今の鍵: {[sorted(c) for c in checks]}"


def test_d0062_ac04_確認で止めてreviewで再開してもattemptが続く(tmp_path):
    """D0062-AC-04: 判定と確認のある段 a を --pause で流し（1 回目の検証 pass で確認待ち）、設定を読み直した別のパイプラインで
    --review revise して続けると、a の check の要素の attempt は 1・2（再開で 1 に戻らない）。"""
    pipe = make_pipe(tmp_path, pipe_toml(pipe_stage("a", "review = true\n[stages.check]\nverdict = true\n")))
    first = PipeRunner(pipe, {"a": [PASS]})
    assert run_pipe(tmp_path, pipe, first, auto_approve=False, pause_for_review=True) == Exit.AWAITING_REVIEW
    assert [c.get("attempt") for c in checks_of(pipe_state(tmp_path), "a")] == [1], "止める前の attempt"
    resumed = linear(tmp_path, pipe, PipeRunner(pipe, {"a": [PASS]}), auto_approve=False, pause_for_review=True)
    assert asyncio.run(resumed.review(Decision("revise", "直して"))) == Exit.AWAITING_REVIEW
    checks = checks_of(pipe_state(tmp_path), "a")
    assert [c["status"] for c in checks] == ["pass", "pass"]
    assert [c.get("attempt") for c in checks] == [1, 2], f"再開のあとの attempt が続いていない: {[c.get('attempt') for c in checks]}"


# ---- AC-12：判定の無いパイプは今までと同じ形 --------------------------------------------------------------


def test_d0062_ac12_判定の無いパイプのstagesは今までと同じ形_守る(tmp_path):
    """D0062-AC-12: 判定の無い段だけのパイプの state.json は、stages[] の要素の鍵が name・label・output・review の 4 つのままで、
    runs[] に check の要素も無い。（今のまま通る。守る）"""
    pipe = make_pipe(tmp_path, pipe_toml(pipe_stage("a"), pipe_stage("b", "review = true\n")))
    assert run_pipe(tmp_path, pipe, PipeRunner(pipe)) == Exit.PASSED
    state = pipe_state(tmp_path)
    assert state["stages"] == [
        {"name": "a", "label": "aの段", "output": "a.md", "review": False},
        {"name": "b", "label": "bの段", "output": "b.md", "review": True},
    ]
    assert [h for h in state["runs"] if "check" in h] == []


def test_d0062_ac12_判定のある段でもcheck以外の鍵と値は変わらない(tmp_path):
    """D0062-AC-12: 判定のある段の stages[] の要素は、check を除くと name・label・output・review の 4 つのままで値も同じ。
    check を持つ runs[] の要素は stage と check の 2 つの鍵だけ（attempt は check の中）。"""
    pipe = make_pipe(tmp_path, pipe_toml(pipe_stage("a", "[stages.check]\nverdict = true\n")))
    assert run_pipe(tmp_path, pipe, PipeRunner(pipe, {"a": [PASS]})) == Exit.PASSED
    state = pipe_state(tmp_path)
    entry = stage_entry(state, "a")
    assert {k: v for k, v in entry.items() if k != "check"} == {"name": "a", "label": "aの段", "output": "a.md", "review": False}
    assert "check" in entry, f"stages[] の a に check が無い。今の鍵: {sorted(entry)}"
    assert [sorted(h) for h in state["runs"] if "check" in h] == [["check", "stage"]]


# ---- AC-13：本体が書く形は共通の表のとおり -----------------------------------------------------------------


@pytest.mark.parametrize("case", CASES)
def test_d0062_ac13_本体が書く形は共通の表のとおり(tmp_path, case):
    """D0062-AC-13: 共通の表の 1 件ずつ。case の check と results で流すと、終了コードが exit、stages[] の verify の check が
    written の check、runs[] の verify の check の要素の attempt が written の attempt と等しい（draw に check は無い）。"""
    code, state = run_case(tmp_path, case)
    assert code.name == case["exit"]
    verify = stage_entry(state, "verify")
    assert verify.get("check") == case["written"]["check"], f"stages[] の verify の check が表と違う（今の鍵: {sorted(verify)}）"
    assert "check" not in stage_entry(state, "draw")
    checks = checks_of(state, "verify")
    assert [c["status"] for c in checks] == case["results"]
    assert [c.get("attempt") for c in checks] == case["written"]["attempt"]
