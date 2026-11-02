"""D0063：並列の枠（stage の group）を、state.json の stages[] に残す（本体の記録）。AC-01・AC-02・AC-13。

SDK は呼ばない。runner を手書きの偽物に差し替える（偽物は tests/test_pipe_check_record.py の PipeRunner と同じ形を、このファイルの中に小さく持つ。
ほかのテストのファイルは import しない）。ファイルは tmp_path の中にだけ作る。
本体が書く形は、拡張のテストと共通の表 tests/fixtures/group_record.json で結ぶ（check_record.json と同じ作り）。

- 今の作りのままで通るテストは、名前の末尾を _守る にし、説明の末尾に「（今のまま通る。守る）」と書く。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pipe_in.dev.pipeline import DevPipeline
from pipe_in.engine.config import load_config
from pipe_in.engine.pipeline import Exit
from pipe_in.engine.runner import StageRun
from pipe_in.pipe import definition as pd
from pipe_in.pipe.pipeline import LinearPipeline

ROOT = Path(__file__).resolve().parents[1]
TABLE = json.loads((ROOT / "tests" / "fixtures" / "group_record.json").read_text(encoding="utf-8"))
FAIL = {"status": "fail", "summary": "直す点あり", "problems": ["矢印が逆"]}
PASS = {"status": "pass", "summary": "よい", "problems": []}


# ---- 補助：偽の runner ----------------------------------------------------------------------------


class PipeRunner:
    """パイプの段の偽物。成果物を書き、段ごとに決めた構造化出力を順に返す。呼ばれた段の名前を calls に残す。"""

    def __init__(self, pipe: pd.PipeDef, structured: dict[str, list] | None = None):
        self.outputs = {s.name: s.output for s in pipe.stages}
        self.structured = {k: list(v) for k, v in (structured or {}).items()}
        self.calls: list[str] = []

    async def __call__(self, spec, prompt, cfg, *, resume, log_name):
        self.calls.append(spec.name)
        for _ in range(3):  # 枠の中の段が同時に動くのを、順番を譲って真似る
            await asyncio.sleep(0)
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
    """成果物が <段>.md の、読むだけの段。extra は段の表の最後に足す行（group = "…" や [stages.check] など）。"""
    return f'\n[[stages]]\nname = "{name}"\nlabel = "{name}の段"\noutput = "{name}.md"\naccess = "read"\nprompt = "{name}をする"\n{extra}'


def pipe_toml(*stages: str) -> str:
    return '[pipe]\nkind = "linear"\nlabel = "試し"\n' + "".join(stages)


def make_pipe(project: Path, toml: str) -> pd.PipeDef:
    d = project / "pipes" / "pipe-in-p"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pipe.toml").write_text(toml, encoding="utf-8")
    return pd.load_pipe(d)


def run_pipe(project: Path, pipe: pd.PipeDef, runner) -> Exit:
    cfg = load_config(project, None, auto_approve=True).for_pipe(pipe.name, own_work_dir=True)
    return asyncio.run(LinearPipeline(cfg, pipe, runner=runner).run("やること"))


def pipe_state(project: Path) -> dict:
    return json.loads((project / "docs" / "pipeline" / "p" / "state.json").read_text(encoding="utf-8"))


def stage_entry(state: dict, name: str) -> dict:
    (entry,) = [s for s in state["stages"] if s["name"] == name]
    return entry


def toml_of_case(case: dict) -> str:
    """共通の表の stages（name と、あれば group）をパイプの定義にする。"""
    return pipe_toml(*(pipe_stage(s["name"], f'group = "{s["group"]}"\n' if "group" in s else "") for s in case["stages"]))


CASES = [pytest.param(c, id=c["memo"]) for c in TABLE["cases"]]
GROUPED = pipe_toml(pipe_stage("survey"), pipe_stage("flow", 'group = "draw"\n'), pipe_stage("klass", 'group = "draw"\n'), pipe_stage("report"))


# ---- 共通の表の形 ------------------------------------------------------------------------------------


def test_d0063_ac13_共通の表のkeysは本体が書く1つの鍵と同じ_守る():
    """D0063-AC-13: 共通の表 tests/fixtures/group_record.json の keys は stages[] の group の 1 つで、どのケースの written もその範囲に収まる。
    ケースは 3 つ以上で、枠の無い・枠が 1 段だけ・枠が 2 つ続くを含む。（今のまま通る。守る）"""
    assert TABLE["keys"] == ["group"]
    assert len(TABLE["cases"]) >= 3
    for c in TABLE["cases"]:
        assert set(c) >= {"memo", "stages", "written", "read"}, c
        assert set(c["written"]) == set(TABLE["keys"]), c
        assert set(c["written"]["group"]) == {s["name"] for s in c["stages"]}, c
    assert any(all("group" not in s for s in c["stages"]) for c in TABLE["cases"]), "枠の無いケース"
    assert any(len({s["group"] for s in c["stages"] if "group" in s}) >= 2 for c in TABLE["cases"]), "枠が 2 つ続くケース"
    assert any(len([s for s in c["stages"] if "group" in s]) == 1 for c in TABLE["cases"]), "枠が 1 段だけのケース"


# ---- AC-01：stages[] に group を書く -------------------------------------------------------------------


def test_d0063_ac01_group_を持つ段のstagesにgroupが書かれる(tmp_path):
    """D0063-AC-01: group = "draw" の続いた 2 段 flow・klass のパイプを流すと、state.json の stages[] のその 2 段に
    group: "draw" が書かれる。"""
    pipe = make_pipe(tmp_path, GROUPED)
    assert run_pipe(tmp_path, pipe, PipeRunner(pipe)) == Exit.PASSED
    state = pipe_state(tmp_path)
    for name in ("flow", "klass"):
        entry = stage_entry(state, name)
        assert "group" in entry, f"stages[] の {name} に group が無い。今の鍵: {sorted(entry)}"
        assert entry["group"] == "draw"


def test_d0063_ac01_group_の無い段のstagesには項目が無い(tmp_path):
    """D0063-AC-01: 同じパイプで、group を持たない段 survey・report には group の鍵が無い（枠の中の段は group を持つ）。"""
    pipe = make_pipe(tmp_path, GROUPED)
    assert run_pipe(tmp_path, pipe, PipeRunner(pipe)) == Exit.PASSED
    state = pipe_state(tmp_path)
    assert "group" in stage_entry(state, "flow"), "枠の中の段に group が書かれていない（まだ作っていない）"
    assert "group" not in stage_entry(state, "survey")
    assert "group" not in stage_entry(state, "report")


def test_d0063_ac01_group_の無いパイプのstagesは今までと同じ形_守る(tmp_path):
    """D0063-AC-01: group の無い段だけのパイプの state.json は、stages[] の要素の鍵が name・label・output・review の 4 つのまま。
    （今のまま通る。守る）"""
    pipe = make_pipe(tmp_path, pipe_toml(pipe_stage("a"), pipe_stage("b", "review = true\n")))
    assert run_pipe(tmp_path, pipe, PipeRunner(pipe)) == Exit.PASSED
    assert pipe_state(tmp_path)["stages"] == [
        {"name": "a", "label": "aの段", "output": "a.md", "review": False},
        {"name": "b", "label": "bの段", "output": "b.md", "review": True},
    ]


def test_d0063_ac01_group_の鍵は判定の鍵の後ろに並ぶ(tmp_path):
    """D0063-AC-01: 枠の中の段が判定（check）も持つとき、stages[] の鍵の順は name・label・output・review・check・group
    （check を足した D0062 の書き方に group を続ける）。"""
    toml = pipe_toml(pipe_stage("flow", 'group = "draw"\n[stages.check]\nverdict = true\n'), pipe_stage("klass", 'group = "draw"\n'))
    pipe = make_pipe(tmp_path, toml)
    assert run_pipe(tmp_path, pipe, PipeRunner(pipe, {"flow": [PASS]})) == Exit.PASSED
    entry = stage_entry(pipe_state(tmp_path), "flow")
    assert list(entry) == ["name", "label", "output", "review", "check", "group"], f"鍵の並び: {list(entry)}"


def test_d0063_ac01_開発フローのstagesにgroupは書かれない_守る(tmp_path):
    """D0063-AC-01: 開発フロー（5 段）の state.json の stages[] には、どの段にも group の項目が無い（足すのはパイプだけ）。
    （今のまま通る。守る）"""
    cfg = load_config(tmp_path, None, auto_approve=True)
    assert asyncio.run(DevPipeline(cfg, runner=DevRunner()).run("ログイン画面を作る", "requirements")) == Exit.PASSED
    state = json.loads((tmp_path / "docs" / "pipeline" / "state.json").read_text(encoding="utf-8"))
    assert [s["name"] for s in state["stages"]] == ["requirements", "design", "red", "implement", "test"]
    assert [s["name"] for s in state["stages"] if "group" in s] == []


# ---- AC-02：枠の中の段が自分をやり直しても group は変わらない --------------------------------------------


def test_d0063_ac02_枠の中の段が自分をやり直してもgroupは変わらずrunsに2回書かれる(tmp_path):
    """D0063-AC-02: 枠の中の flow が判定で 1 回 fail → pass（自分をやり直す）。stages[] の flow の group は "draw" のまま、
    runs[] に flow の段の実行（seq を持つ要素）が 2 つ、klass は 1 つ書かれる。"""
    toml = GROUPED.replace('group = "draw"\n', 'group = "draw"\n[stages.check]\nverdict = true\n', 1)
    pipe = make_pipe(tmp_path, toml)
    runner = PipeRunner(pipe, {"flow": [FAIL, PASS]})
    assert run_pipe(tmp_path, pipe, runner) == Exit.PASSED
    assert runner.calls.count("flow") == 2 and runner.calls.count("klass") == 1
    state = pipe_state(tmp_path)
    flow = stage_entry(state, "flow")
    assert "group" in flow, f"stages[] の flow に group が無い。今の鍵: {sorted(flow)}"
    assert flow["group"] == "draw"
    assert stage_entry(state, "klass").get("group") == "draw"
    runs = [h for h in state["runs"] if "seq" in h]
    assert [h["stage"] for h in runs].count("flow") == 2
    assert [h["stage"] for h in runs].count("klass") == 1


# ---- AC-13：本体が書く形は共通の表のとおり -----------------------------------------------------------------


@pytest.mark.parametrize("case", CASES)
def test_d0063_ac13_本体が書く形は共通の表のとおり(tmp_path, case):
    """D0063-AC-13: 共通の表の 1 件ずつ。case の stages（name と group）をパイプにして流すと、state.json の stages[] の各段の
    group が written の group と等しい（null の段は鍵が無い）。"""
    pipe = make_pipe(tmp_path, toml_of_case(case))
    assert run_pipe(tmp_path, pipe, PipeRunner(pipe)) == Exit.PASSED
    state = pipe_state(tmp_path)
    got = {s["name"]: s.get("group") for s in state["stages"]}
    assert got == case["written"]["group"], f"stages[] の group が表と違う: {got}"
    for s in state["stages"]:
        assert ("group" in s) == (case["written"]["group"][s["name"]] is not None), f"{s['name']} の鍵の有無"
