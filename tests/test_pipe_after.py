"""前のパイプの記録を読んで受けるか決める部分（--after。D0069）を、SDK を呼ばずに確かめる。

ファイルは tmp_path の中だけに作る。今までの置き場所（PIPE_IN_PIPES_DIR）も tmp_path に向けて、リポジトリの pipes/ を読まない。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipe_in.engine.config import load_config
from pipe_in.engine.pipeline import STATE
from pipe_in.pipe import after
from pipe_in.pipe import definition as pd


@pytest.fixture(autouse=True)
def pipes_elsewhere(tmp_path, monkeypatch):
    """今までの置き場所を tmp_path に向ける（リポジトリの pipes/ を見ない）。"""
    monkeypatch.setenv("PIPE_IN_PIPES_DIR", str(tmp_path / "shared"))


def project_of(tmp_path: Path) -> Path:
    p = tmp_path / "app"
    p.mkdir(exist_ok=True)
    return p


def stage(name: str, label: str, output: str, extra: str = "", access: str = "read") -> str:
    return f'\n[[stages]]\nname = "{name}"\nlabel = "{label}"\noutput = "{output}"\naccess = "{access}"\nprompt = "{label}をする"\n{extra}'


def pipe_toml(*stages: str, kind: str = "linear", input_mode: str = "optional") -> str:
    return f'[pipe]\nkind = "{kind}"\nlabel = "試し"\ninput = "{input_mode}"\n' + "".join(stages)


PREV = pipe_toml(stage("survey", "仕様の調査", "01_survey.md"), stage("draw", "図を描く", "02_draw.md"))
LATER = pipe_toml(stage("code", "実装", "04_code.md"))


def pipes_root(project: Path) -> Path:
    return project / ".pipe-in" / "pipes"


def write_pipe(root: Path, name: str, toml: str) -> Path:
    d = root / f"pipe-in-{name}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pipe.toml").write_text(toml, encoding="utf-8")
    return d


def load(project: Path, name: str, toml: str) -> pd.PipeDef:
    return pd.load_pipe(write_pipe(pipes_root(project), name, toml))


def write_record(
    folder: Path,
    pipe: str,
    *,
    final: str | None = "PASSED",
    stages: tuple[tuple[str, str], ...] = (("仕様の調査", "01_survey.md"), ("図を描く", "02_draw.md")),
    files: bool = True,
    updated_at: str | None = "2026-10-30T10:00:00",
    extra: dict | None = None,
) -> Path:
    """前の記録（state.json と成果物）を手で書く。実際の実行が書く形のうち、読むのに要る項目だけ。"""
    folder.mkdir(parents=True, exist_ok=True)
    data: dict = {
        "pipe": pipe,
        "stages": [{"name": f"s{i}", "label": label, "output": out} for i, (label, out) in enumerate(stages)],
    }
    if updated_at is not None:
        data["updated_at"] = updated_at
    if final is not None:
        data["final"] = final
    data.update(extra or {})
    path = folder / STATE
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if files:
        for _, out in stages:
            (folder / out).write_text("# 成果物\n", encoding="utf-8")
    return path


def read(project: Path, name: str = "diagrams") -> after.Previous:
    return after.read_previous(name, load_config(project, None), project / "docs" / "pipeline")


# ---- D0069-AC-02：途中・確認待ち・失敗は、種類と直し方つきで断る --------------------------


@pytest.mark.parametrize(
    "fields,words",
    [
        ({"final": None}, ["途中", "流し直"]),
        (
            {"final": None, "extra": {"pending_review": {"stage": "survey", "session_id": "s-1", "doc": "docs/pipeline/diagrams/01_survey.md"}}},
            ["確認待ち", "--review"],
        ),
        ({"final": "STAGE_ERROR"}, ["失敗", "流し直", "STAGE_ERROR"]),
    ],
    ids=["途中", "確認待ち", "失敗"],
)
def test_d0069_ac02_途中_確認待ち_失敗は種類と直し方つきで断る(tmp_path, fields, words):
    """D0069-AC-02: 前の記録が途中（final が無い）・確認待ち（pending_review がある）・失敗（final が PASSED 以外）のとき断る。文に理由の種類と直し方が入る。"""
    project = project_of(tmp_path)
    load(project, "diagrams", PREV)
    write_record(project / "docs/pipeline/diagrams", "diagrams", **fields)
    with pytest.raises(after.AfterError) as e:
        read(project)
    msg = str(e.value)
    for word in words:
        assert word in msg, msg


# ---- D0069-AC-03：この実行に前の記録が無いと、見た場所と直し方を出して断る ----------------------


def test_d0069_ac03_この実行に前の記録が無いと見た場所と直し方を出して断る(tmp_path):
    """D0069-AC-03: この実行の work_dir に前の state.json が無いとき断る。文に見た場所（作業フォルダからの相対）と、直し方（--project・--config を揃える、または前のパイプを先に流す）が入る。"""
    project = project_of(tmp_path)
    load(project, "diagrams", PREV)
    with pytest.raises(after.AfterError) as e:
        read(project)
    msg = str(e.value)
    assert "diagrams/state.json" in msg, msg
    assert "--project" in msg and "--config" in msg, msg
    assert "先に流" in msg, msg


# ---- D0069-AC-04：定義・記録が読めない、名前が違う、開発用の記録のときは断る -------------------


@pytest.mark.parametrize("case,word", [("pipe.toml", "pipe.toml"), ("json", "state.json"), ("name", "state.json"), ("driver", None)])
def test_d0069_ac04_pipe_toml_state_json_が読めない_名前が違う_driver_があると断る(tmp_path, case, word):
    """D0069-AC-04: 前の pipe.toml が読めない・state.json が JSON でない・state.json の pipe が前の名前と違う・開発用スキルの記録（driver）のとき、断る。文に何が読めなかったかと直し方が入る。"""
    project = project_of(tmp_path)
    folder = write_pipe(pipes_root(project), "diagrams", PREV)
    rec = project / "docs/pipeline/diagrams"
    if case == "pipe.toml":
        (folder / "pipe.toml").write_text("[pipe\nkind = ", encoding="utf-8")
    elif case == "json":
        write_record(rec, "diagrams")
        (rec / STATE).write_text("{ここはJSONではない", encoding="utf-8")
    elif case == "name":
        write_record(rec, "dev")
    else:
        write_record(rec, "diagrams", extra={"driver": "pipe-in"})
    with pytest.raises(after.AfterError) as e:
        read(project)
    msg = str(e.value)
    if word is not None:
        assert word in msg, msg
    assert "直し" in msg, msg


# ---- D0069-AC-05：前の成果物が1つも無ければ、PASSED でも断る -----------------------------------


def test_d0069_ac05_前の成果物が1つも無いと_PASSED_でも断る(tmp_path):
    """D0069-AC-05: 前の段の成果物が1つも存在しないとき、final が PASSED でも断る。"""
    project = project_of(tmp_path)
    load(project, "diagrams", PREV)
    write_record(project / "docs/pipeline/diagrams", "diagrams", files=False)
    with pytest.raises(after.AfterError) as e:
        read(project)
    assert "成果物" in str(e.value), str(e.value)


# ---- D0069-AC-06：名前でない値・2つ以上は断る -----------------------------------------------


@pytest.mark.parametrize("value", ["a/b", "..\\x", "", "Diagrams", "a_b", "a b", "logs", "end"])
def test_d0069_ac06_名前でない値は断る(tmp_path, value):
    """D0069-AC-06: --after に名前でない値（/ や \\ を含むパス・空・英小文字・数字・- 以外を含む値・予約の名前）を渡したとき断る。"""
    project = project_of(tmp_path)
    later = load(project, "later", LATER)
    with pytest.raises(after.AfterError):
        after.check_after([value], later)


def test_d0069_ac06_名前ならそのまま返し_書かなければ_None(tmp_path):
    """D0069-AC-06: 名前を1つ書けばその名前を返し、書かなければ None を返す。"""
    project = project_of(tmp_path)
    later = load(project, "later", LATER)
    assert after.check_after(["diagrams"], later) == "diagrams"
    assert after.check_after(None, later) is None


def test_d0069_ac06_after_を2つ渡すと断る_check_after(tmp_path):
    """D0069-AC-06: --after を2つ以上書いたとき断る（check_after の段）。"""
    project = project_of(tmp_path)
    later = load(project, "later", LATER)
    with pytest.raises(after.AfterError):
        after.check_after(["diagrams", "other"], later)


# ---- D0069-AC-07：後ろのパイプと同じ名前は断る ------------------------------------------------


def test_d0069_ac07_後ろのパイプと同じ名前は断る(tmp_path):
    """D0069-AC-07: --after の名前が後ろのパイプの名前と同じとき（自分自身を指すとき）断る。"""
    project = project_of(tmp_path)
    later = load(project, "later", LATER)
    with pytest.raises(after.AfterError):
        after.check_after(["later"], later)


# ---- D0069-AC-08：組み込みの開発フロー（名前 dev・後ろが kind = dev）は断る ----------------------


def test_d0069_ac08_後ろが_kind_dev_のパイプは断る(tmp_path):
    """D0069-AC-08: 後ろのパイプが kind = "dev" のとき、--after を断る（記録の場所が前と同じ work_dir になるため）。"""
    project = project_of(tmp_path)
    later = load(project, "later", pipe_toml(kind="dev"))
    with pytest.raises(after.AfterError):
        after.check_after(["diagrams"], later)


def test_d0069_ac08_名前_dev_は断る(tmp_path):
    """D0069-AC-08: --after の名前 dev（組み込みの開発フロー）は断る。"""
    project = project_of(tmp_path)
    later = load(project, "later", LATER)
    with pytest.raises(after.AfterError):
        after.check_after(["dev"], later)


# ---- D0069-AC-10：渡す成果物の場所（linear と dev） -----------------------------------------


def test_d0069_ac10_linear_の前の成果物は_work_前名_成果物と指す(tmp_path):
    """D0069-AC-10: 前が kind = linear のとき、渡す成果物の場所は <work_dir>/<前の名前>/<成果物> になる。"""
    project = project_of(tmp_path)
    load(project, "diagrams", PREV)
    write_record(project / "docs/pipeline/diagrams", "diagrams")
    cfg = load_config(project, None)
    base = project / "docs" / "pipeline"
    prev = after.read_previous("diagrams", cfg, base)
    assert prev.kind == "linear"
    assert [cfg.rel(base / path) for _, path in prev.artifacts] == [
        "docs/pipeline/diagrams/01_survey.md",
        "docs/pipeline/diagrams/02_draw.md",
    ]


def test_d0069_ac10_ファイルが無い段の成果物は渡す一覧に入らない(tmp_path):
    """D0069-FR-08・D0069-AC-10: 渡す成果物は、ファイルが存在するものだけを段の順に並べる。無い段は入らない。"""
    project = project_of(tmp_path)
    load(project, "diagrams", PREV)
    rec = project / "docs/pipeline/diagrams"
    write_record(rec, "diagrams", files=False)
    (rec / "02_draw.md").write_text("# 図\n", encoding="utf-8")
    cfg = load_config(project, None)
    base = project / "docs" / "pipeline"
    prev = after.read_previous("diagrams", cfg, base)
    assert [cfg.rel(base / path) for _, path in prev.artifacts] == ["docs/pipeline/diagrams/02_draw.md"]


def test_d0069_ac10_dev_の前の成果物は_work_成果物と指す(tmp_path):
    """D0069-AC-10: 前が kind = dev のとき、渡す成果物の場所は <work_dir>/<成果物> になる（記録は work_dir 直下）。"""
    project = project_of(tmp_path)
    load(project, "spec", pipe_toml(kind="dev"))
    base = project / "docs" / "pipeline"
    write_record(base, "spec", stages=(("調査", "01_survey.md"),))
    cfg = load_config(project, None)
    prev = after.read_previous("spec", cfg, base)
    assert prev.kind == "dev"
    assert [cfg.rel(base / path) for _, path in prev.artifacts] == ["docs/pipeline/01_survey.md"]


# ---- D0069-FR-02：前のパイプは --pipe と同じ順番で探す --------------------------------------


@pytest.mark.parametrize(
    "linear_at,dev_at",
    [("project", ["old", "shared"]), ("old", ["shared"])],
    ids=["対象の .pipe-in が先", "前の版の置き場所が次"],
)
def test_d0069_fr02_前のパイプは_pipe_と同じ順番で探す(tmp_path, linear_at, dev_at):
    """D0069-FR-02: 前のパイプは --pipe と同じ探す順番（対象の .pipe-in/pipes/ → 前の版の置き場所 → 今までの場所）で探す。先に見つかったものを使う。"""
    project = project_of(tmp_path)
    # 置き場所の名前は設定の定数から取る（古い名前を文字で書かない）
    roots = {
        "project": project / pd.PROJECT_PIPES_DIR,
        "old": project / pd.LEGACY_PROJECT_PIPES_DIR,
        "shared": tmp_path / "shared",
    }
    write_pipe(roots[linear_at], "diagrams", PREV)
    for where in dev_at:
        write_pipe(roots[where], "diagrams", pipe_toml(kind="dev"))
    write_record(project / "docs/pipeline/diagrams", "diagrams")
    assert read(project).kind == "linear"
