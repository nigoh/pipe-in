"""D0071：pipe-in record check（記録の順序を読むだけで検べるコマンド）。

record.main・cli.main（record／skill record）から流す。記録は tmp_path に、差し替えの時計をつけた Recorder で書く。
リポジトリの実物（docs/pipeline/）には触れず、SDK も呼ばない。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from pipe_in import cli
from pipe_in.dev import record
from pipe_in.dev.record import Recorder
from pipe_in.engine import clock
from pipe_in.engine.config import load_config

T0 = datetime(2026, 10, 17, 10, 0, 0)
OK_TEXT = "順序は守られています"


def at(sec: int) -> str:
    return clock.with_offset(T0 + timedelta(seconds=sec))


def write_record(project: Path, steps: list[tuple[Any, ...]]) -> Path:
    now = [T0]
    r = Recorder(load_config(project), now=lambda: now[0])
    r.start("メモ")
    for sec, op, *args in steps:
        now[0] = T0 + timedelta(seconds=sec)
        getattr(r, op)(*args)
    return project / "docs" / "pipeline"


GOOD = [
    (0, "begin", "requirements"), (5, "done", "requirements"), (6, "wait", "requirements"),
    (20, "review", "requirements", "approved"),
    (30, "begin", "design"), (35, "done", "design"),
]
BAD = [
    (0, "begin", "requirements"), (5, "done", "requirements"), (6, "wait", "requirements"),
    (10, "begin", "design"),
    (20, "review", "requirements", "approved"),
    (30, "done", "design"),
]


def snapshot(work: Path) -> dict[str, bytes]:
    return {p.relative_to(work).as_posix(): p.read_bytes() for p in sorted(work.rglob("*")) if p.is_file()}


ENTRANCES = ["record.main", "cli record", "cli skill record"]


def run_check(entrance: str, project: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    """3 つの入口から record check を流す（skill は今のフォルダだけを相手にするので chdir する）。"""
    if entrance == "record.main":
        return record.main(["check", "--project", str(project)])
    if entrance == "cli record":
        return cli.main(["record", "check", "--project", str(project)])
    monkeypatch.chdir(project)
    return cli.main(["skill", "record", "check"])


# ---- AC-09：順序が守られていれば 0、違反なら 1。何も書かない ---------------------------------------------


@pytest.mark.parametrize("entrance", ENTRANCES)
def test_d0071_ac09_check_ok_exit_0(tmp_path, capsys, monkeypatch, entrance):
    """D0071-AC-09: 順序が守られた記録では「順序は守られています」を出して終了コード 0（record・cli record・skill record のどこからでも同じ）。"""
    write_record(tmp_path, GOOD)
    capsys.readouterr()
    assert run_check(entrance, tmp_path, monkeypatch) == 0
    out = capsys.readouterr().out
    assert OK_TEXT in out
    assert "記録しました" not in out


@pytest.mark.parametrize("entrance", ENTRANCES)
def test_d0071_ac09_check_violation_exit_1(tmp_path, capsys, monkeypatch, entrance):
    """D0071-AC-09: 違反のある記録では、違反を並べ（段の名前・順番・時刻）、終了コード 1。"""
    write_record(tmp_path, BAD)
    capsys.readouterr()
    assert run_check(entrance, tmp_path, monkeypatch) == 1
    out = capsys.readouterr().out
    assert OK_TEXT not in out
    assert "違反" in out
    assert "要件定義" in out and "設計" in out  # 段の表示名
    assert "02_design.jsonl" in out and "順番" in out
    assert at(10) in out and at(20) in out  # begin と承認の時刻
    assert "記録しました" not in out


@pytest.mark.parametrize("steps", [GOOD, BAD], ids=["ok", "violation"])
def test_d0071_ac09_check_does_not_write(tmp_path, capsys, steps):
    """D0071-AC-09: record check は state.json・段のログ・00_input.md を書き換えない（前後で全ファイルの中身が同じ）。「記録しました」も出さない。"""
    work = write_record(tmp_path, steps)
    before = snapshot(work)
    assert "state.json" in before and "00_input.md" in before and any(k.startswith("logs/") for k in before)
    capsys.readouterr()
    record.main(["check", "--project", str(tmp_path)])
    assert snapshot(work) == before
    assert "記録しました" not in capsys.readouterr().out


def test_d0071_ac09_undecided_is_reported_but_exit_code_stays(tmp_path, capsys):
    """D0071-AC-09: 判定できなかったもの（at の無い古い review）があれば、そのことも出す。終了コードは違反が無ければ 0 のまま。"""
    work = write_record(tmp_path, GOOD)
    path = work / "state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for run in data["runs"]:
        run.pop("at", None)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    capsys.readouterr()
    assert record.main(["check", "--project", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "判定できなかった" in out
    assert "順序の違反" not in out  # 違反として並べない
    assert OK_TEXT in out  # 違反が無いので、守られている旨は出す


def test_d0071_ac09_undecided_does_not_hide_a_violation(tmp_path, capsys):
    """D0071-AC-09: 違反と判定できなかったものが両方あれば、両方を出し、終了コードは 1。"""
    work = write_record(tmp_path, [
        (0, "begin", "requirements"), (2, "done", "requirements"), (3, "wait", "requirements"),
        (4, "begin", "design"), (6, "done", "design"), (7, "wait", "design"),
        (20, "review", "requirements", "approved"),
        (30, "review", "design", "approved"),
        (40, "begin", "red"),
    ])
    path = work / "state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for run in data["runs"]:
        if run.get("stage") == "design" and "review" in run:
            run.pop("at", None)  # design の承認だけ古い形
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    capsys.readouterr()
    assert record.main(["check", "--project", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "判定できなかった" in out and "違反" in out


# ---- AC-10：記録がまだ無い -------------------------------------------------------------------------


def test_d0071_ac10_check_without_record_says_start_and_exits_1(tmp_path, capsys):
    """D0071-AC-10: 記録がまだ無いところで record check を流すと、start を促す文で終了コード 1（他のサブコマンドと同じ文）。何も作らない。"""
    with pytest.raises(SystemExit) as check:
        record.main(["check", "--project", str(tmp_path)])
    with pytest.raises(SystemExit) as begin:
        record.main(["begin", "requirements", "--project", str(tmp_path)])
    assert isinstance(check.value.code, str) and "記録がありません" in check.value.code
    assert "pipe-in record start" in check.value.code
    assert check.value.code == begin.value.code  # begin と同じ文
    assert not (tmp_path / "docs").exists()
    assert "記録しました" not in capsys.readouterr().out


# ---- AC-11：python -m pipe_in skill record check ------------------------------------------------------


def test_d0071_ac11_skill_record_check_runs(tmp_path, capsys, monkeypatch):
    """D0071-AC-11: python -m pipe_in skill record check が流せる（今のフォルダの記録を読み、旗は増やさない）。"""
    write_record(tmp_path, BAD)
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    assert cli.main(["skill", "record", "check"]) == 1
    assert "違反" in capsys.readouterr().out


@pytest.mark.parametrize(
    "flags",
    [["--project", ".."], ["--project=x"], ["--proj", "x"], ["--proj=.."], ["--config", "other.toml"], ["--conf=other.toml"]],
    ids=["project", "project-eq", "project-short", "project-short-eq", "config", "config-short-eq"],
)
def test_d0071_ac11_skill_record_check_still_refuses_project_and_config(tmp_path, monkeypatch, flags):
    """D0071-AC-11: skill record check に --project・--config を付けると（短くした形・= の形も）今までどおり断られ、何も書かない。"""
    write_record(tmp_path, BAD)
    monkeypatch.chdir(tmp_path)
    before = snapshot(tmp_path / "docs" / "pipeline")
    with pytest.raises(SystemExit, match="pipe-in skill"):
        cli.main(["skill", "record", "check", *flags])
    assert snapshot(tmp_path / "docs" / "pipeline") == before


# ---- AC-14(a)：古い言い方の記録を読める ----------------------------------------------------------------


def test_d0071_ac14_old_wording_records_are_readable_by_check(tmp_path, capsys):
    """D0071-AC-14: 「/pipe-dev の…」の Prompt 行・「# /pipe-dev のまとめ」の古い記録を、record check が例外なく読める（Prompt 行の prompt は見ない）。"""
    work = write_record(tmp_path, GOOD)
    for log in (work / "logs").glob("*.jsonl"):
        lines = log.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["prompt"] = "/pipe-dev の" + {"requirements": "要件定義", "design": "設計"}[first["stage"]]
        lines[0] = json.dumps(first, ensure_ascii=False)
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (work / "99_summary.md").write_text("# /pipe-dev のまとめ\n\n- 結果: PASSED\n", encoding="utf-8")
    before = snapshot(work)
    capsys.readouterr()
    code = record.main(["check", "--project", str(tmp_path)])
    assert code in (0, 1)
    assert code == 0 and OK_TEXT in capsys.readouterr().out
    assert snapshot(work) == before
