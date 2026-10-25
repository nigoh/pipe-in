"""D0031：コマンド pipe-in live watch（引数・--out の守り・終了コード・実際の起動）。

入口は pipe_in/engine/live_cmd.py の main(argv, *, now=None, watch_deps=None)。watch_deps は live_watch.watch へ渡す差し替え
（clock・sleep・now・read_state・write・stdout・stderr）の辞書で、偽の時計・眠り・標準出力を渡して本物の時間を待たない。
子プロセスで起動するのは、SIGTERM（1件）・python -m と cli.main の両方（1件）・閉じた標準出力（1件）だけ。記録は tmp_path の中に作る。
"""

from __future__ import annotations

import errno
import inspect
import io
import json
import os
import signal
import subprocess
import sys
import re
import threading
import time
from pathlib import Path

import pytest

import live_support as ls
import live_watch_support as lw
from live_watch_support import NOW, FakeOut, Rec, expected_bytes, listing, out_path, tree
from pipe_in.engine import live, live_cmd, live_page, live_watch

ROOT = Path(__file__).resolve().parents[1]
REAL_SLEEP = time.sleep  # 子プロセスの待ち合わせ（subprocess の中の待ち）は本物の sleep を使う
CAN_SYMLINK = hasattr(os, "symlink")
SNAPSHOT_LINE = '{"event":"snapshot","seq":1,"final":null,"empty":false}\n'
TIMEOUT_LINE = '{"event":"timeout","seq":1,"final":null,"empty":false}\n'


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """D0031-AC-42: 差し替えていない本物の time.sleep が呼ばれたら、テストを失敗にする。"""

    def boom(*a, **k):
        raise AssertionError("本物の time.sleep が呼ばれた（sleep を差し替えていない）")

    monkeypatch.setattr(time, "sleep", boom)


def midway(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    return ls.dev_record_midway(tmp_path)


def make_deps(steps=None, advance=None):
    ft = lw.FakeTime(steps, advance=advance)
    so = FakeOut()
    so.ft = ft
    se = io.StringIO()
    return {"clock": ft.clock, "sleep": ft.sleep, "now": ft.now, "stdout": so, "stderr": se}, ft, so, se


def run(argv, cap, deps=None):
    """live_cmd.main を呼ぶ。SystemExit（argparse の使い方の誤り・設定の誤り）も、終了コードとして返す。"""
    kw = {}
    if deps is not None and "watch_deps" in inspect.signature(live_cmd.main).parameters:
        kw["watch_deps"] = deps
    try:
        code = live_cmd.main(list(argv), **kw)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else f"exit:{e.code}"
    out, err = cap.readouterr()
    return code, out, err


def watch_argv(work, out, *extra):
    return ["watch", "--work-dir", str(work), "--out", str(out), *extra]


def events(so):
    return [json.loads(x)["event"] for x in so.complete]


# ---- AC-42 main の差し替えの口 -------------------------------------------------------------------------------------------


def test_d0031_ac42_main_accepts_watch_deps():
    """D0031-AC-42: main は watch_deps（watch へ渡す差し替え）を名前つきの引数で受け取れる。"""
    params = inspect.signature(live_cmd.main).parameters
    assert "watch_deps" in params and params["watch_deps"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["watch_deps"].default is None
    assert params["now"].default is None


def test_d0031_ac51_live_help_lists_watch(capfd):
    """D0031-AC-51: pipe-in live の使い方に、下位コマンド watch が出る（D0039 で answer が増え、{snapshot,page,watch,answer}）。"""
    with pytest.raises(SystemExit) as e:
        live_cmd.main(["--help"])
    out = capfd.readouterr().out
    assert e.value.code == 0
    assert "{snapshot,page,watch,answer}" in out and "watch" in out and "answer" in out


def test_d0031_ac51_watch_help_lists_every_option(capfd):
    """D0031-AC-51: watch --help に、引数（--project・--config・--work-dir・--out・--interval・--timeout）が出る。"""
    with pytest.raises(SystemExit) as e:
        live_cmd.main(["watch", "--help"])
    out = capfd.readouterr().out
    assert e.value.code == 0
    for flag in ("--project", "--config", "--work-dir", "--out", "--interval", "--timeout"):
        assert flag in out, flag


# ---- AC-13 --out の守り ----------------------------------------------------------------------------------------------------

INSIDE = "読み先の記録のフォルダの中"
LINK = "シンボリックリンク"
PARENT = "親のフォルダ"


def refusal_cases(tmp_path, work):
    """(名前, --out, 断る理由に含まれる語, 読み先)"""
    cases = {
        "inside": (work / "live.json", INSIDE),
        "in_logs": (work / "logs" / "live.json", INSIDE),
        "over_state": (work / "state.json", INSIDE),
        "over_input": (work / "00_input.md", INSIDE),
        "missing_sub_of_work": (work / "sub" / "live.json", PARENT),
        "dotdot_back_in": (work / ".." / work.name / "live.json", INSIDE),
        "missing_parent": (tmp_path / "no" / "such" / "live.json", PARENT),
        "existing_folder": (tmp_path / "adir", "--out"),
    }
    (tmp_path / "adir").mkdir(exist_ok=True)
    (work / "archive" / "20261017-100000").mkdir(parents=True, exist_ok=True)
    cases["inside_archive"] = (work / "archive" / "20261017-100000" / "live.json", INSIDE)
    return cases


@pytest.mark.parametrize("name", ["inside", "in_logs", "over_state", "over_input", "missing_sub_of_work", "dotdot_back_in", "missing_parent", "existing_folder", "inside_archive"])
def test_d0031_ac13_out_inside_record_symlink_missing_parent_or_dir_exits2_and_writes_nothing(tmp_path, capfd, name):
    """D0031-AC-13: --out が読み先の記録のフォルダの中（archive/… を含む）・親が無い所・既存のフォルダのときは、見張りを始めず使い方を出して終了コード 2。記録も --out も何も書かれない。"""
    work = midway(tmp_path)
    out, word = refusal_cases(tmp_path, work)[name]
    before = tree(work)
    deps, ft, so, se = make_deps()
    code, stdout, err = run(watch_argv(work, out), capfd, deps)
    assert code == 2, (code, err)
    assert "invalid choice" not in err and "usage" in err.lower() and word in err, err
    assert stdout == "" and so.complete == [] and ft.sleeps == [] and se.getvalue() == ""
    assert tree(work) == before
    assert not (tmp_path / "no").exists()
    assert not out.is_file() or out == work / "state.json" or out == work / "00_input.md"


@pytest.mark.skipif(not CAN_SYMLINK, reason="シンボリックリンクを作れない環境")
@pytest.mark.parametrize("kind", ["file_link", "dangling_link", "via_folder_link"])
def test_d0031_ac13_symlink_out_is_refused(tmp_path, capfd, kind):
    """D0031-AC-13: --out がシンボリックリンク（切れたリンクを含む）のときと、読み先へのリンクのフォルダ経由のときは、書かずに終了コード 2。リンク先は変わらない。"""
    work = midway(tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_text("守る", encoding="utf-8")
    try:
        if kind == "file_link":
            out = tmp_path / "out.json"
            out.symlink_to(victim)
        elif kind == "dangling_link":
            out = tmp_path / "out.json"
            out.symlink_to(tmp_path / "ghost.json")
        else:
            (tmp_path / "shortcut").symlink_to(work, target_is_directory=True)
            out = tmp_path / "shortcut" / "live.json"
    except (OSError, NotImplementedError):
        pytest.skip("シンボリックリンクを作れない環境")
    before = tree(work)
    deps, ft, so, se = make_deps()
    code, _stdout, err = run(watch_argv(work, out), capfd, deps)
    assert code == 2 and "invalid choice" not in err and ("--out" in err), err
    assert (LINK in err) if kind != "via_folder_link" else (INSIDE in err)
    assert so.complete == [] and ft.sleeps == []
    assert victim.read_text(encoding="utf-8") == "守る" and not (tmp_path / "ghost.json").exists()
    assert tree(work) == before


def test_d0031_ac13_archive_dir_as_work_dir_refuses_out_inside_it(tmp_path, capfd):
    """D0031-AC-13・55: archive/<日時>/ を読み先に渡したとき、その中への --out は断る（終了コード 2）。archive の中は変わらない。"""
    work = lw_finished_with_archive(tmp_path)
    archived = sorted((work / "archive").iterdir())[0]
    before = tree(archived)
    deps, ft, so, se = make_deps()
    code, _o, err = run(watch_argv(archived, archived / "live.json"), capfd, deps)
    assert code == 2 and INSIDE in err and "invalid choice" not in err
    assert tree(archived) == before and so.complete == []


def lw_finished_with_archive(tmp_path):
    rec = Rec(tmp_path / "p")
    rec.start("終わった記録", name="終わった実行")
    rec.begin("requirements")
    rec.done("requirements", "書いた")
    rec.finish("PASSED")
    rec.start("次の記録", name="次の実行")
    return rec.work


def test_d0031_ac55_archive_dir_as_work_dir_allows_out_in_the_pipe_record_folder(tmp_path, capfd):
    """D0031-AC-55: archive/<日時>/ を読み先にしたとき、パイプの記録のフォルダのほう（読み先の外）への --out は断らない。final があれば1回で止まる（0）。"""
    work = lw_finished_with_archive(tmp_path)
    archived = sorted((work / "archive").iterdir())[0]
    out = work / "live.json"
    before = tree(archived)
    deps, ft, so, se = make_deps()
    code, stdout, err = run(watch_argv(archived, out), capfd, deps)
    assert code == 0, err
    assert so.complete == ['{"event":"final","seq":1,"final":"PASSED","empty":false}'] and ft.sleeps == []
    assert out.read_bytes() == expected_bytes(archived, NOW)
    assert tree(archived) == before and listing(work).count("live.json") == 1 and not [n for n in listing(work) if n.endswith(".tmp")]


def test_d0031_ac13_out_next_to_but_outside_the_work_dir_is_allowed(tmp_path, capfd):
    """D0031-AC-13: 読み先の隣（同じ親のフォルダ）や、名前の頭だけが同じフォルダには書ける（頭の文字の比較で誤って断らない）。"""
    work = midway(tmp_path)
    twin = work.parent / (work.name + "-copy")
    twin.mkdir()
    for out in (twin / "live.json", work.parent / "next.json"):
        deps, ft, so, se = make_deps()
        code, _o, err = run(watch_argv(work, out, "--timeout", "2"), capfd, deps)
        assert code == 124, err
        assert out.is_file() and events(so) == ["snapshot", "timeout"]


# ---- AC-14 .. と相対・リンクへの差し替え -------------------------------------------------------------------------------------


@pytest.mark.parametrize("form", ["dotdot", "dot_dotdot", "relative", "relative_dotdot"])
def test_d0031_ac14_dotdot_and_relative_out_refused(tmp_path, monkeypatch, capfd, form):
    """D0031-AC-14: --out が .. を含む形や相対の形で読み先の中を指していても断る（resolve した形で比べる）。"""
    work = midway(tmp_path)
    (work / "sub").mkdir()
    monkeypatch.chdir(tmp_path)
    given = {
        "dotdot": str(work) + "/../" + work.name + "/live.json",
        "dot_dotdot": str(work) + "/./sub/../live.json",
        "relative": "docs/pipeline/live.json",
        "relative_dotdot": "./docs/pipeline/../pipeline/logs/live.json",
    }[form]
    argv = ["watch", "--work-dir", "docs/pipeline" if form.startswith("relative") else str(work), "--out", given]
    before = tree(work)
    deps, ft, so, se = make_deps()
    code, _o, err = run(argv, capfd, deps)
    assert code == 2 and INSIDE in err and "invalid choice" not in err, err
    assert so.complete == [] and tree(work) == before


@pytest.mark.skipif(not CAN_SYMLINK, reason="シンボリックリンクを作れない環境")
def test_d0031_ac14_symlink_swap_keeps_target(tmp_path, capfd):
    """D0031-AC-14: 実行中に --out がシンボリックリンクに替えられても、リンクの先は書き換わらない（リンク自身が置き換わる）。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    rec.begin("requirements")
    out = out_path(tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_text("守る", encoding="utf-8")

    def swap_and_change():
        out.unlink()
        try:
            out.symlink_to(victim)
        except (OSError, NotImplementedError):
            pytest.skip("シンボリックリンクを作れない環境")
        rec.done("requirements", "書いた")

    deps, ft, so, se = make_deps({1: swap_and_change})
    code, _o, err = run(watch_argv(rec.work, out, "--timeout", "4"), capfd, deps)
    assert code == 124, err
    assert events(so) == ["snapshot", "snapshot", "timeout"]
    assert victim.read_text(encoding="utf-8") == "守る"
    assert not out.is_symlink() and json.loads(out.read_bytes())["schema"] == 1
    assert listing(out.parent) == [out.name]


# ---- AC-15・51 使い方の誤り -------------------------------------------------------------------------------------------------


def test_d0031_ac15_missing_out_exits2(tmp_path, capfd):
    """D0031-AC-15: --out を付けない場合は使い方の誤り（終了コード 2）。--out が必須だと分かる文を出し、何も書かない。"""
    work = midway(tmp_path)
    before = tree(tmp_path)
    deps, ft, so, se = make_deps()
    code, out, err = run(["watch", "--work-dir", str(work)], capfd, deps)
    assert code == 2 and out == "" and so.complete == []
    assert "invalid choice" not in err and "--out" in err and "required" in err.lower(), err
    assert tree(tmp_path) == before


@pytest.mark.parametrize(
    "argv,word",
    [
        (["watch", "--bogus"], "required"),
        (["watch", "--out", "{out}", "--bogus"], "unrecognized"),
        (["watch", "--ou", "{out}"], "required"),
        (["watch", "--out", "{out}", "--inter", "1"], "unrecognized"),
        (["watch", "--out", "{out}", "--time", "1"], "unrecognized"),
        (["watch", "--out", "{out}", "--work", "x"], "unrecognized"),
        (["watch", "--out", "{out}", "extra"], "unrecognized"),
        (["watch", "--out"], "expected one argument"),
        (["watch", "--out", "{out}", "--interval"], "expected one argument"),
        (["watch", "--out", "{out}", "--timeout"], "expected one argument"),
        (["watch", "--out", "{out}", "--work-dir"], "expected one argument"),
        (["watch", "--out", "{out}", "--project"], "expected one argument"),
        (["watch", "--out", "{out}", "--config"], "expected one argument"),
        (["watch", "--out", "{out}", "--interval", "1", "--interval", "x"], "--interval"),
    ],
    ids=lambda v: v if isinstance(v, str) else " ".join(v),
)
def test_d0031_ac51_unknown_argument_or_abbrev_exits2(tmp_path, monkeypatch, capfd, argv, word):
    """D0031-AC-51: watch の知らない引数・省略形（--out を --ou など）・値の欠けは、使い方を出して終了コード 2。何も書かない。"""
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "live.json"
    argv = [a.format(out=out) for a in argv]
    deps, ft, so, se = make_deps()
    code, stdout, err = run(argv, capfd, deps)
    assert code == 2 and stdout == ""
    assert "usage" in err.lower() and "invalid choice" not in err and word in err, err
    assert so.complete == [] and ft.sleeps == []
    assert listing(tmp_path) == []


@pytest.mark.parametrize("argv", [["wat", "--out", "x.json"], ["Watch", "--out", "x.json"], ["watcher"], ["snapshot,page,watch"], ["watch,"], ["w"]])
def test_d0031_ac51_unknown_subcommand_exits2(tmp_path, monkeypatch, capfd, argv):
    """D0031-AC-51: 知らない下位コマンド（watch の省略形・大文字・綴り違い）は、選べるもの（snapshot・page・watch）を出して終了コード 2。"""
    monkeypatch.chdir(tmp_path)
    deps, ft, so, se = make_deps()
    code, stdout, err = run(argv, capfd, deps)
    assert code == 2 and stdout == ""
    assert "invalid choice" in err, err
    for name in ("snapshot", "page", "watch"):
        assert re.search(r"choose from.*\b" + name + r"\b", err, re.S), (name, err)
    assert listing(tmp_path) == []


def test_d0031_ac51_page_and_snapshot_refuse_watch_arguments(tmp_path, monkeypatch, capfd):
    """D0031-AC-51: page・snapshot に watch の引数（--interval・--timeout）を付けると使い方の誤り（終了コード 2）。watch にも page の引数は付けられない。"""
    monkeypatch.chdir(tmp_path)
    for argv in (["page", "--interval", "1"], ["snapshot", "--timeout", "1"], ["snapshot", "--interval", "1"]):
        code, _o, err = run(argv, capfd)
        assert code == 2 and "unrecognized" in err, argv


def test_d0031_ac51_cli_main_unknown_live_arguments_exit2(capfd):
    """D0031-AC-51: pipe_in.cli.main(["live", "watch", …]) の使い方の誤りも終了コード 2（live の使い方に watch が出る）。"""
    from pipe_in import cli

    for argv in (["live", "watch"], ["live", "watch", "--bogus"]):
        with pytest.raises(SystemExit) as e:
            cli.main(argv)
        err = capfd.readouterr().err
        assert e.value.code == 2 and "usage" in err.lower() and "invalid choice" not in err, argv
        assert "--out" in err or "unrecognized" in err


def test_d0031_ac51_config_errors_are_handled_like_snapshot(tmp_path, capfd):
    """D0031-AC-51: 設定が読めない・プロジェクトのフォルダが無い・work_dir がプロジェクトの外、は live snapshot と同じ扱い（FR-16）。見張りは始まらない。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "pipeline.toml").write_text("[[[", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "pipeline.toml").write_text('[pipeline]\nwork_dir = "../elsewhere"\n', encoding="utf-8")
    cases = {
        "missing_project": ["--project", str(tmp_path / "nope")],
        "missing_config": ["--project", str(proj), "--config", str(tmp_path / "ghost.toml")],
        "broken_toml": ["--project", str(broken)],
        "work_dir_outside_project": ["--project", str(outside)],
    }
    for name, extra in cases.items():
        def outcome(argv, deps=None):
            kw = {"watch_deps": deps} if deps is not None else {}
            try:
                return ("code", live_cmd.main(argv, **kw))
            except SystemExit as e:
                return ("exit", e.code)
            except Exception as e:  # noqa: BLE001
                return ("raise", type(e).__name__)

        want = outcome(["snapshot", *extra])
        deps, ft, so, se = make_deps()
        got = outcome(["watch", *extra, "--out", str(tmp_path / "live.json")], deps if "watch_deps" in inspect.signature(live_cmd.main).parameters else None)
        capfd.readouterr()
        assert got == want, (name, got, want)
        assert so.complete == [] and not (tmp_path / "live.json").exists(), name


@pytest.mark.parametrize("kind", ["missing_dir", "no_state", "state_is_folder", "broken_json", "work_dir_is_file", "array"])
def test_d0031_ac02_record_problems_do_not_exit2(tmp_path, capfd, kind):
    """D0031-AC-02: 記録の中身の問題（無い・壊れている・フォルダ・ファイル）では終了コード 2 にしない。「記録なし」の行を出して、上限まで見張る（124）。"""
    work = tmp_path / "w"
    if kind == "no_state":
        work.mkdir()
    elif kind == "state_is_folder":
        (work / "state.json").mkdir(parents=True)
    elif kind == "broken_json":
        work.mkdir()
        (work / "state.json").write_text("{broken", encoding="utf-8")
    elif kind == "array":
        work.mkdir()
        (work / "state.json").write_text("[]", encoding="utf-8")
    elif kind == "work_dir_is_file":
        work.write_text("x", encoding="utf-8")
    out = out_path(tmp_path)
    deps, ft, so, se = make_deps()
    code, _o, err = run(watch_argv(work, out, "--timeout", "6"), capfd, deps)
    assert code == 124, (code, err)
    assert so.complete[0] == '{"event":"snapshot","seq":1,"final":null,"empty":true}'
    assert events(so) == ["snapshot", "timeout"]
    assert json.loads(out.read_bytes())["empty"] is True


# ---- AC-29 間隔と上限 --------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra,sleeps",
    [
        (["--interval", "0.5", "--timeout", "1.5"], [0.5, 0.5, 0.5]),
        (["--interval", "60", "--timeout", "120"], [60.0, 60.0]),
        (["--interval", "60", "--timeout", "86400"], [60.0] * 1440),
        (["--timeout", "1"], [1.0]),
        (["--interval", "2", "--timeout", "1"], [1.0]),
        (["--interval", "1", "--timeout", "3"], [1.0, 1.0, 1.0]),
    ],
    ids=["interval_min", "interval_max", "timeout_max", "timeout_min", "timeout_min_default_interval", "plain"],
)
def test_d0031_ac29_interval_and_timeout_boundaries(tmp_path, capfd, extra, sleeps):
    """D0031-AC-29: --interval は 0.5 と 60、--timeout は 1 と 86400 が通る（両端を含む）。眠りはその間隔で、最後は残りの分だけ。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    deps, ft, so, se = make_deps()
    code, _o, err = run(watch_argv(work, out, *extra), capfd, deps)
    assert code == 124, (code, err)
    assert ft.sleeps == pytest.approx(sleeps)
    assert events(so) == ["snapshot", "timeout"]


@pytest.mark.parametrize("value", ["0.49", "0", "-1", "abc", "nan", "inf", "-inf", "NaN", "Infinity", "", "1e999", "0.4999"])
@pytest.mark.parametrize("flag", ["--interval", "--timeout"])
def test_d0031_ac29_out_of_range_interval_and_timeout_exit2(tmp_path, capfd, flag, value):
    """D0031-AC-29: 範囲外・0・負・数でない・nan・inf は終了コード 2（使い方）。理由に引数の名前が出る。何も書かず、見張りも始まらない。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    deps, ft, so, se = make_deps()
    code, stdout, err = run(watch_argv(work, out, flag, value), capfd, deps)
    assert code == 2 and stdout == "", (code, err)
    assert "usage" in err.lower() and "invalid choice" not in err and flag in err, err
    assert so.complete == [] and ft.sleeps == [] and not out.exists()


@pytest.mark.parametrize("flag,value", [("--timeout", "0.99"), ("--timeout", "86401"), ("--timeout", "86400.001"), ("--timeout", "0.9999"), ("--interval", "60.01"), ("--interval", "61"), ("--interval", "100")])
def test_d0031_ac29_range_edges_exit2(tmp_path, capfd, flag, value):
    """D0031-AC-29: --timeout は 0.99 と 86401、--interval は 61 が範囲外（終了コード 2）。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    deps, ft, so, se = make_deps()
    code, _o, err = run(watch_argv(work, out, flag, value), capfd, deps)
    assert code == 2 and flag in err and "invalid choice" not in err
    assert so.complete == [] and not out.exists()


def test_d0031_ac29_defaults_are_constants(tmp_path, monkeypatch, capfd):
    """D0031-AC-29: 省いたときの既定は定数（間隔 2 秒・上限 6 時間）。watch へそのまま渡る。"""
    seen = {}

    def spy(work, out, **kw):
        seen.update(kw, work=work, out=out)
        return 0

    monkeypatch.setattr(live_watch, "watch", spy)
    work = midway(tmp_path)
    code, _o, err = run(watch_argv(work, out_path(tmp_path)), capfd)
    assert code == 0, err
    assert seen["interval"] == 2.0 == live_watch.DEFAULT_INTERVAL
    assert seen["timeout"] == 21600.0 == live_watch.DEFAULT_TIMEOUT
    assert type(seen["interval"]) is float and type(seen["timeout"]) is float


def test_d0031_ac29_values_reach_watch_and_the_exit_code_comes_back(tmp_path, monkeypatch, capfd):
    """D0031-AC-29: --interval・--timeout・--out・読み先・hide（読み先のパスの形）が watch に渡り、watch の終了コードがそのまま main の戻り値になる。"""
    seen = {}

    def spy(work, out, **kw):
        seen.update(kw, work=work, out=out)
        return 7

    monkeypatch.setattr(live_watch, "watch", spy)
    work, out = midway(tmp_path), out_path(tmp_path)
    code, _o, err = run(watch_argv(work, out, "--interval", "3", "--timeout", "7.5"), capfd)
    assert code == 7, err
    assert seen["interval"] == 3.0 and seen["timeout"] == 7.5
    assert seen["work"] == work and seen["out"] == out
    assert tuple(seen["hide"]) == live_cmd._hide_forms(work)


def test_d0031_ac29_work_dir_is_decided_like_snapshot(tmp_path, monkeypatch, capfd):
    """D0031-AC-29: 読み先は live snapshot と同じに決まる（--work-dir が先／なければ --project と pipeline.toml の work_dir／--config）。"""
    seen = []

    def spy(work, out, **kw):
        seen.append(work)
        return 0

    monkeypatch.setattr(live_watch, "watch", spy)
    proj = tmp_path / "proj"
    proj.mkdir()
    out = out_path(tmp_path)
    (proj / "pipeline.toml").write_text('[pipeline]\nwork_dir = "custom/run"\n', encoding="utf-8")
    other = tmp_path / "other.toml"
    other.write_text('[pipeline]\nwork_dir = "elsewhere"\n', encoding="utf-8")
    explicit = tmp_path / "pick"
    explicit.mkdir()
    for argv in (
        ["watch", "--project", str(proj), "--out", str(out)],
        ["watch", "--project", str(proj), "--config", str(other), "--out", str(out)],
        ["watch", "--project", str(proj), "--work-dir", str(explicit), "--out", str(out)],
    ):
        assert run(argv, capfd)[0] == 0, argv
    assert seen == [proj.resolve() / "custom" / "run", proj.resolve() / "elsewhere", explicit]
    monkeypatch.chdir(proj)
    assert run(["watch", "--out", str(out)], capfd)[0] == 0
    assert seen[-1] == proj.resolve() / "custom" / "run"


def test_d0031_ac29_sigterm_handler_is_installed_and_restored(tmp_path, monkeypatch, capfd):
    """D0031-AC-44: main は watch の前に SIGTERM の取り付けをし、終わったら（watch が例外で終わっても）元に戻す。"""
    log = []
    monkeypatch.setattr(live_watch, "install_sigterm", lambda: (log.append("install"), lambda: log.append("restore"))[1])

    def ok(work, out, **kw):
        log.append("watch")
        return 0

    def bad(work, out, **kw):
        log.append("watch")
        raise RuntimeError("boom")

    work, out = midway(tmp_path), out_path(tmp_path)
    monkeypatch.setattr(live_watch, "watch", ok)
    assert run(watch_argv(work, out), capfd)[0] == 0
    assert log == ["install", "watch", "restore"]
    log.clear()
    monkeypatch.setattr(live_watch, "watch", bad)
    with pytest.raises(RuntimeError):
        live_cmd.main(watch_argv(work, out))
    assert log == ["install", "watch", "restore"]


def test_d0031_ac29_refused_out_does_not_install_sigterm(tmp_path, monkeypatch, capfd):
    """D0031-AC-13: --out を断るときは、SIGTERM の取り付けも watch の呼び出しもしない。"""
    called = []
    monkeypatch.setattr(live_watch, "install_sigterm", lambda: called.append("install") or (lambda: None))
    monkeypatch.setattr(live_watch, "watch", lambda *a, **k: called.append("watch") or 0)
    work = midway(tmp_path)
    code, _o, err = run(watch_argv(work, work / "live.json"), capfd)
    assert code == 2 and INSIDE in err and "invalid choice" not in err
    assert called == []


# ---- AC-49 ほかのコマンドは変わらない ------------------------------------------------------------------------------------------


def test_d0031_ac49_snapshot_page_outputs_and_schema_unchanged(tmp_path, capfdbinary):
    """D0031-AC-49: live snapshot・live page の出力（バイト列）と写しの SCHEMA・項目は変わらない。見張りを流したあとも同じで、見張りが書く写しは snapshot と同じバイト列。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    expected = expected_bytes(work, NOW)
    first = live_cmd.main(["snapshot", "--work-dir", str(work)], now=NOW)
    assert first == 0 and capfdbinary.readouterr().out == expected
    deps, ft, so, se = make_deps()
    deps["now"] = lambda: NOW
    code, _o, _e = run(watch_argv(work, out, "--timeout", "2"), capfdbinary, deps)
    assert code == 124
    assert out.read_bytes() == expected, "見張りが書く写しは live snapshot と同じバイト列"
    assert live_cmd.main(["snapshot", "--work-dir", str(work)], now=NOW) == 0 and capfdbinary.readouterr().out == expected
    assert live_cmd.main(["page"]) == 0 and capfdbinary.readouterr().out == live_page.build_page().encode("utf-8")
    assert live.SCHEMA == 1 and live.FINALS == ("PASSED", "TEST_FAILED", "STOPPED_BY_HUMAN", "STAGE_ERROR", "BLOCKED")
    assert list(json.loads(expected)) == ls.KEYS


# ---- 子プロセスで起動する（SIGTERM・python -m と cli.main・閉じた標準出力）------------------------------------------------------


def child_env():
    # D0040-AC-08: 子の標準エラーを UTF-8 で書かせる（Windows は UTF-8 モードでないと手元の文字コードで書き、日本語の文が読めない）
    return {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"}


def popen(argv, tmp_path):
    return subprocess.Popen([sys.executable, *argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=tmp_path, env=child_env(), text=True, encoding="utf-8")


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM を子プロセスに送れない（Windows）")
def test_d0031_ac44_sigterm_exit143_no_tmp_out_intact(tmp_path, monkeypatch):
    """D0031-AC-44: SIGTERM を受けたとき（実際に子プロセスで起動して送る）、終了コード 143、短い文、一時ファイルが残らず、--out は完全な写しのまま。"""
    monkeypatch.setattr(time, "sleep", REAL_SLEEP)
    work, out = midway(tmp_path), out_path(tmp_path)
    proc = popen(["-m", "pipe_in", "live", "watch", "--work-dir", str(work), "--out", str(out), "--interval", "0.5", "--timeout", "60"], tmp_path)
    killer = threading.Timer(60, proc.kill)
    killer.start()
    try:
        first = proc.stdout.readline()
        assert first == SNAPSHOT_LINE, (first, "")
        proc.send_signal(signal.SIGTERM)
        rest, err = proc.communicate(timeout=60)
    finally:
        killer.cancel()
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
    assert proc.returncode == 143, err
    assert rest == "", "標準出力に行を足さない"
    assert err == "pipe-in live watch: 終了の合図を受けました\n"
    assert listing(out.parent) == [out.name]
    snap = json.loads(out.read_bytes())
    assert snap["schema"] == 1 and snap["empty"] is False and snap["name"] == "途中のセッション"


def test_d0031_ac50_module_and_cli_main_give_timeout_124(tmp_path, monkeypatch):
    """D0031-AC-50: python -m pipe_in live watch … と pipe_in.cli.main(["live", "watch", …]) のどちらからも同じ動き。実際に子プロセスで起動して、--timeout 1 で timeout の行と終了コード 124 を確かめる。"""
    monkeypatch.setattr(time, "sleep", REAL_SLEEP)
    work = midway(tmp_path)
    results = []
    for i, how in enumerate(("module", "cli_main")):
        out = tmp_path / f"out{i}" / "live.json"
        out.parent.mkdir()
        argv = ["live", "watch", "--work-dir", str(work), "--out", str(out), "--interval", "0.5", "--timeout", "1"]
        if how == "module":
            proc = subprocess.run([sys.executable, "-m", "pipe_in", *argv], capture_output=True, cwd=tmp_path, env=child_env(), timeout=60, text=True, encoding="utf-8")
        else:
            code = "import sys, json; from pipe_in.cli import main; sys.exit(main(json.loads(sys.argv[1])))"
            proc = subprocess.run([sys.executable, "-c", code, json.dumps(argv)], capture_output=True, cwd=tmp_path, env=child_env(), timeout=60, text=True, encoding="utf-8")
        results.append((proc.returncode, proc.stdout, proc.stderr, out))
    for rc, stdout, stderr, out in results:
        assert rc == 124, stderr
        assert stdout == SNAPSHOT_LINE + TIMEOUT_LINE
        assert stderr == ""
        assert json.loads(out.read_bytes())["schema"] == 1 and listing(out.parent) == [out.name]
    assert results[0][1] == results[1][1]


def test_d0031_ac45_closed_stdout_in_a_real_process_exits1_quietly(tmp_path, monkeypatch):
    """D0031-AC-45・D0040-AC-08: 標準出力の受け側が閉じている実際の子プロセスでも、落ちずに一時ファイルを残さず終了コード 1。標準エラーは短い1文だけ（トレースバックも、終了時の「Exception ignored」も出ない）。Windows（閉じたパイプへの書き込みが EINVAL になる）でも同じ。"""
    monkeypatch.setattr(time, "sleep", REAL_SLEEP)
    work, out = midway(tmp_path), out_path(tmp_path)
    proc = popen(["-m", "pipe_in", "live", "watch", "--work-dir", str(work), "--out", str(out), "--interval", "0.5", "--timeout", "3"], tmp_path)
    killer = threading.Timer(60, proc.kill)
    killer.start()
    try:
        proc.stdout.close()
        err = proc.stderr.read()
        proc.wait(timeout=60)
    finally:
        killer.cancel()
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        proc.stderr.close()
    assert proc.returncode == 1, err
    assert err == "pipe-in live watch: 標準出力が閉じられました\n"
    assert listing(out.parent) == [out.name]


# ---- D0040 標準出力の付け替え（_detach_stdout）と、呼ぶ条件 ----------------------------------------------------------------------
#
# 本物の記述子と pytest の出力の取り込みには触らない。os モジュールそのものは差し替えず（pytest も os.dup2 を使うため）、
# live_cmd が見る名前 os だけを、呼ばれた引数を覚える偽物に替える。sys.stdout は FakeFdOut に替える（どちらも monkeypatch が戻す）。


class FakeFdOut:
    """fileno() が決まった番号を返すか、渡した例外を出す偽の標準出力。"""

    def __init__(self, fd: int = 1001, error: BaseException | None = None) -> None:
        self.fd = fd
        self.error = error

    def fileno(self) -> int:
        if self.error is not None:
            raise self.error
        return self.fd

    def write(self, s: str) -> int:
        return len(s)

    def flush(self) -> None:
        pass


class FakeOs:
    """_detach_stdout が使う os の口（open・dup2・close・devnull・O_WRONLY）の偽物。本物の記述子は開かない。"""

    devnull = os.devnull
    O_WRONLY = os.O_WRONLY

    def __init__(self, *, sink: int = 1002, open_error: BaseException | None = None, dup2_error: BaseException | None = None) -> None:
        self.sink = sink
        self.open_error = open_error
        self.dup2_error = dup2_error
        self.opened: list[tuple[str, int]] = []
        self.dup2s: list[tuple[int, int]] = []
        self.closed: list[int] = []

    def open(self, path, flags, *a, **k) -> int:
        self.opened.append((path, flags))
        if self.open_error is not None:
            raise self.open_error
        return self.sink

    def dup2(self, fd: int, fd2: int, *a, **k) -> int:
        self.dup2s.append((fd, fd2))
        if self.dup2_error is not None:
            raise self.dup2_error
        return fd2

    def close(self, fd: int) -> None:
        self.closed.append(fd)


def test_d0040_ac09_detach_stdout_redirects_to_devnull(monkeypatch):
    """D0040-AC-09: 付け替えられるときは、os.devnull を開いた番号から sys.stdout.fileno() へ1回付け替え、開いた番号を閉じる。sys.stdout は替えず、例外も出さない（今のままで通る。守り続ける検査）。"""
    fake_os = FakeOs(sink=1002)
    stdout = FakeFdOut(1001)
    monkeypatch.setattr(live_cmd, "os", fake_os)
    monkeypatch.setattr(sys, "stdout", stdout)
    live_cmd._detach_stdout()
    seen = sys.stdout
    assert seen is stdout
    assert [p for p, _f in fake_os.opened] == [os.devnull]
    assert fake_os.dup2s == [(1002, 1001)]
    assert fake_os.closed == [1002]


DETACH_FAILURES = ["dup2_fails", "open_fails", "fileno_fails", "stdout_is_none", "same_number"]


@pytest.mark.parametrize("case", DETACH_FAILURES)
def test_d0040_ac09_detach_stdout_falls_back_to_none(monkeypatch, case):
    """D0040-AC-09: 付け替えられない（dup2・open・fileno が失敗する、sys.stdout が None）ときは、例外を出さず sys.stdout を None にする。open が付け替え先と同じ番号を返したときは、dup2 も close もせず sys.stdout はそのまま。"""
    stdout = FakeFdOut(1001)
    if case == "dup2_fails":
        fake_os = FakeOs(sink=1002, dup2_error=OSError(errno.EBADF, "x"))
    elif case == "open_fails":
        fake_os = FakeOs(open_error=OSError(errno.ENOENT, "x"))
    elif case == "fileno_fails":
        fake_os = FakeOs(sink=1002)
        stdout = FakeFdOut(error=ValueError("I/O operation on closed file."))
    elif case == "same_number":
        fake_os = FakeOs(sink=1001)
    else:
        fake_os = FakeOs(sink=1002)
        stdout = None
    monkeypatch.setattr(live_cmd, "os", fake_os)
    monkeypatch.setattr(sys, "stdout", stdout)
    live_cmd._detach_stdout()  # 例外を出さない
    seen = sys.stdout
    if case == "same_number":
        assert seen is stdout, "同じ番号なら、もう捨て先を指しているので sys.stdout は替えない"
        assert fake_os.dup2s == [] and fake_os.closed == [], "同じ番号なら dup2 も close もしない（close すると標準出力の記述子を閉じてしまう）"
        return
    assert seen is None, "付け替えられないときは sys.stdout を None にして、終了時の flush を止める"
    if case == "dup2_fails":
        assert fake_os.dup2s == [(1002, 1001)] and fake_os.closed == [1002], "捨て先は閉じる"
    elif case == "open_fails":
        assert fake_os.dup2s == []
    elif case == "fileno_fails":
        assert fake_os.opened == [] and fake_os.dup2s == []


def test_d0040_ac10_injected_stdout_skips_detach(tmp_path, monkeypatch, capfd):
    """D0040-AC-10: watch_deps で stdout を差し替えたときは、終了コード 1 でも _detach_stdout を呼ばない（今のままで通る。守り続ける検査）。"""
    calls = []
    monkeypatch.setattr(live_cmd, "_detach_stdout", lambda: calls.append(1))
    deps, ft, so, se = make_deps()
    fake = FakeOut(write_error=lambda n: BrokenPipeError(32, "x"))
    fake.ft = ft
    deps["stdout"] = fake
    code, _o, _e = run(watch_argv(midway(tmp_path), out_path(tmp_path)), capfd, deps)
    assert code == 1
    assert se.getvalue() == "pipe-in live watch: 標準出力が閉じられました\n"
    assert calls == []


@pytest.mark.parametrize("watch_code,detached", [(1, 1), (0, 0), (124, 0)])
def test_d0040_ac10_real_stdout_detaches_once_on_exit1(tmp_path, monkeypatch, capfd, watch_code, detached):
    """D0040-AC-10: stdout を差し替えないときは、watch が 1 を返したときだけ _detach_stdout を1回呼ぶ（0・124 では呼ばない。呼ぶ条件を変えないことの対の検査。今のままで通る）。"""
    calls = []
    monkeypatch.setattr(live_cmd, "_detach_stdout", lambda: calls.append(1))
    monkeypatch.setattr(live_watch, "watch", lambda *a, **k: watch_code)
    code, _o, _e = run(watch_argv(midway(tmp_path), out_path(tmp_path)), capfd)
    assert code == watch_code
    assert len(calls) == detached
