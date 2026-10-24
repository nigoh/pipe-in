"""D0031：記録を見張って、写しが変わったときだけ1行を出す部品（pipe_in/engine/live_watch.py）。

入口は live_watch.watch(work_dir, out, *, interval, timeout, hide, clock, sleep, now, read_state, read_open_at, write, stdout, stderr)。
時計・眠り・今・読み・書き・出力は引数で差し替える。偽の部品は tests/live_watch_support.py（偽の時計と眠り、行を集める偽の標準出力、
record と同じ形で state.json を書く Recorder の包み）。本物の時間は待たず、SDK は呼ばず、記録は tmp_path の中に作る。
"""

from __future__ import annotations

import ast
import errno
import gc
import inspect
import json
import os
import signal
import subprocess
import sys
import threading
import time
import tracemalloc
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import live_support as ls
import live_watch_support as lw
from live_watch_support import NOW, FakeOut, Rec, drive, expected_bytes, listing, out_path, tree
from pipe_in.engine import live, live_cmd, live_watch

ROOT = Path(__file__).resolve().parents[1]
REAL_SLEEP = time.sleep  # 子プロセスの待ち合わせ（subprocess の中の待ち）は本物の sleep を使う
CAN_SYMLINK = hasattr(os, "symlink")
IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """D0031-AC-42: 差し替えていない本物の time.sleep が呼ばれたら、テストを失敗にする。"""

    def boom(*a, **k):
        raise AssertionError("本物の time.sleep が呼ばれた（sleep を差し替えていない）")

    monkeypatch.setattr(time, "sleep", boom)


def midway(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    return ls.dev_record_midway(tmp_path)


def snaps(res):
    return [x for x in res.lines if x["event"] != "timeout"]


def line(event, seq, final=None, empty=False):
    return {"event": event, "seq": seq, "final": final, "empty": empty}


def both(*fns):
    def run():
        for f in fns:
            f()

    return run


def finished_record(project: Path, final: str = "PASSED") -> Path:
    rec = Rec(project)
    rec.start("終わった記録", name="終わった実行")
    rec.begin("requirements")
    rec.done("requirements", "書いた")
    rec.finish(final)
    return rec.work


# ---- AC-42 本物の眠りを禁じる仕掛け・差し替えの口 ------------------------------------------------------------------


def test_d0031_ac42_real_sleep_is_forbidden():
    """D0031-AC-42: テストの中で本物の time.sleep を呼ぶと失敗になる（仕掛けそのものの確かめ。今のままで通る）。"""
    with pytest.raises(AssertionError, match="time.sleep"):
        time.sleep(0)


def test_d0031_ac42_watch_takes_every_dependency_as_keyword_argument():
    """D0031-AC-42: watch は時計・眠り・今・読み・書き・出力を、名前つきの引数で差し替えられる（FR-12）。"""
    params = inspect.signature(live_watch.watch).parameters
    for name in ("interval", "timeout", "hide", "clock", "sleep", "now", "read_state", "read_open_at", "write", "stdout", "stderr"):
        assert name in params, name
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY, name
    for name in ("hide", "clock", "sleep", "now", "read_state", "read_open_at", "write", "stdout", "stderr"):
        assert params[name].default is not inspect.Parameter.empty, name
    assert params["interval"].default is inspect.Parameter.empty and params["timeout"].default is inspect.Parameter.empty


# ---- AC-01・02 最初の1回 ---------------------------------------------------------------------------------------------


def test_d0031_ac01_first_read_emits_seq1_and_writes_out(tmp_path):
    """D0031-AC-01: 正常な記録で見張りを始めると、seq 1 の行が1つ出て、--out にその写しが書かれる。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    res = drive(work, out, timeout=6.0)
    assert res.lines[0] == line("snapshot", 1)
    assert res.events == ["snapshot", "timeout"]
    assert res.code == 124
    assert out.read_bytes() == expected_bytes(work, NOW)


@pytest.mark.parametrize("kind", ["no_state", "no_dir", "empty", "broken", "array", "null", "folder", "too_big", "bom", "binary"])
def test_d0031_ac02_first_read_emits_empty_for_broken_records(tmp_path, kind):
    """D0031-AC-02: 最初の1回は、state.json が無い・フォルダ自体が無い・空・壊れている記録でも、empty: true の行が1つ出る（落ちない）。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    if kind != "no_dir":
        work.mkdir()
    raw = {
        "empty": b"", "broken": b'{"name": ', "array": b"[]", "null": b"null", "bom": b"\xef\xbb\xbf{}", "binary": b"\xff\xfe\x00\x01",
        "too_big": b'{"pad": "' + b"a" * (live.MAX_STATE_BYTES + 16) + b'"}',
    }
    if kind in raw:
        (work / "state.json").write_bytes(raw[kind])
    elif kind == "folder":
        (work / "state.json").mkdir()
    res = drive(work, out, timeout=6.0)
    assert res.lines[0] == line("snapshot", 1, None, True)
    assert res.events == ["snapshot", "timeout"], "同じ読めない状態が続いても2つ目の行は出ない"
    assert res.code == 124
    assert out.read_bytes() == expected_bytes(work, NOW)
    assert json.loads(out.read_bytes())["empty"] is True


# ---- AC-03〜09 変わったときだけ出す -----------------------------------------------------------------------------------


def test_d0031_ac03_unchanged_record_emits_nothing_for_ten_ticks(tmp_path):
    """D0031-AC-03: 記録が替わらないまま10周期過ぎても、2つ目の行は出ない（書き込みも1回だけ）。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    res = drive(work, out, timeout=20.0)
    assert res.time.sleeps == pytest.approx([2.0] * 10)
    assert res.reads == 11
    assert res.events == ["snapshot", "timeout"]
    assert res.write_ok == 1 and res.write_attempts == 1


def test_d0031_ac04_generated_at_only_change_emits_nothing(tmp_path):
    """D0031-AC-04: 偽の now を1周期ごとに進めても、記録が同じなら行も書き込みも出ない。出た写しの generated_at は、書いた回の now。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    res = drive(work, out, timeout=20.0)
    assert res.events == ["snapshot", "timeout"] and res.write_ok == 1
    assert json.loads(out.read_bytes())["generated_at"] == ls.utc_text(NOW), "最後まで最初の回の now のまま（書き直していない）"
    # 記録が替わった回は、その回の now になる
    work2, out2 = midway(tmp_path / "again"), out_path(tmp_path / "again")
    rec = Rec(tmp_path / "again", datetime(2026, 10, 17, 11, 0, 0))
    res2 = drive(work2, out2, steps={2: lambda: rec.done("design", "設計した")}, timeout=10.0)
    assert res2.events == ["snapshot", "snapshot", "timeout"]
    assert json.loads(out2.read_bytes())["generated_at"] == ls.utc_text(NOW + timedelta(seconds=4))


def test_d0031_ac05_each_stage_change_emits_once_with_gapless_seq(tmp_path):
    """D0031-AC-05: 段の状態が替わる（begin → done → begin …）たびに、その回の周期で1回ずつ行が出る。seq は 1, 2, 3… と抜け番がない。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ", name="流れ")
    steps = {
        1: lambda: rec.begin("requirements"),
        2: lambda: rec.done("requirements", "書いた"),
        3: lambda: rec.begin("design"),
        4: lambda: rec.done("design", "設計した"),
        5: lambda: rec.finish("PASSED"),
    }
    res = drive(rec.work, out_path(tmp_path), steps=steps, timeout=100.0)
    assert res.events == ["snapshot"] * 5 + ["final"]
    assert res.seqs == [1, 2, 3, 4, 5, 6]
    assert res.out.times == pytest.approx([0.0, 2.0, 4.0, 6.0, 8.0, 10.0]), "替わった回の周期に出る"
    assert res.code == 0


def test_d0031_ac06_two_changes_in_one_tick_emit_once_with_latest(tmp_path):
    """D0031-AC-06: 1周期の間に記録が2回替わったときは、行は1つで、写しはその時点の最新の中身（途中の running は出ない）。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ", name="流れ")
    out = out_path(tmp_path)
    seen = []

    def on_line(text, ft):
        seen.append(json.loads(out.read_bytes()))

    res = drive(rec.work, out, steps={1: both(lambda: rec.begin("requirements"), lambda: rec.done("requirements", "書いた"))},
                timeout=6.0, stdout=FakeOut(on_line=on_line))
    assert res.events == ["snapshot", "snapshot", "timeout"] and res.seqs == [1, 2, 2]
    assert [s["status"] for s in seen[1]["stages"]][0] == "done"
    assert all(s["status"] != "running" for snap in seen for s in snap["stages"])
    assert out.read_bytes() == expected_bytes(rec.work, NOW + timedelta(seconds=2))


def test_d0031_ac07_elapsed_does_not_emit_but_open_log_appearing_does(tmp_path):
    """D0031-AC-07: 動いている段の経過時間が進むだけでは出ない。open の段のログの最初の行（started_at の元）が現れたときは出る。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    ls.write_state(work, ls.base_state(open=ls.opened("design", seq=2)))
    log = "02_design.jsonl"
    steps = {10: lambda: ls.write_log(work, log, [ls.prompt_line("2026-10-17T10:00:00+09:00")])}
    res = drive(work, out, steps=steps, timeout=40.0)
    assert res.events == ["snapshot", "snapshot", "timeout"], "経過では出ず、ログが現れた回（10 回目の眠りのあと）にだけ出る"
    assert res.out.times == pytest.approx([0.0, 20.0, 40.0])
    started = json.loads(out.read_bytes())["stages"][1]["started_at"]
    assert started == "2026-10-17T01:00:00+00:00"


def test_d0031_ac07_a_running_stage_stays_quiet(tmp_path):
    """D0031-AC-07: 動いている段のまま30周期たっても、行は最初の1つだけ。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    rec.begin("requirements")
    res = drive(rec.work, out_path(tmp_path), timeout=60.0)
    assert res.events == ["snapshot", "timeout"] and res.reads == 31


KEY_CHANGES = {
    "indent4": lambda s: json.dumps(s, indent=4, ensure_ascii=False),
    "compact": lambda s: json.dumps(s, separators=(",", ":"), ensure_ascii=False),
    "sorted": lambda s: json.dumps(s, sort_keys=True, indent=1),
    "reversed": lambda s: json.dumps(dict(reversed(list(s.items()))), indent=2, ensure_ascii=False),
    "ascii": lambda s: json.dumps(s, ensure_ascii=True),
    "crlf": lambda s: json.dumps(s, indent=2, ensure_ascii=False).replace("\n", "\r\n") + "\r\n",
    "tabs": lambda s: json.dumps(s, indent="\t", ensure_ascii=False) + "\n",
}


@pytest.mark.parametrize("how", sorted(KEY_CHANGES))
def test_d0031_ac08_key_order_and_spaces_do_not_emit(tmp_path, how):
    """D0031-AC-08: state.json の書き方（キーの順・空白・インデント・改行・\\u 形）だけが違っても、行も書き込みも出ない（中身で比べる）。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    state = ls.base_state(name="日本語の名前", runs=[ls.run("requirements", seq=1, cost=0.5, turns=3, duration=1.5)])
    ls.write_state(work, state)

    def rewrite():
        (work / "state.json").write_text(KEY_CHANGES[how](state), encoding="utf-8", newline="")

    res = drive(work, out, steps={2: rewrite}, timeout=10.0)
    assert res.events == ["snapshot", "timeout"] and res.write_ok == 1


def test_d0031_ac08_snapshot_key_ignores_generated_at_and_key_order():
    """D0031-AC-08: snapshot_key は generated_at を除き、キーの順（入れ子も）に依らない。文字列で返し、元の辞書を変えない。"""
    a = live.build_snapshot(ls.base_state(runs=[ls.run("requirements")]), None, now=NOW)
    b = json.loads(json.dumps(a))
    b["generated_at"] = "2030-01-01T00:00:00+00:00"
    b = dict(reversed(list(b.items())))
    b["stages"] = [dict(reversed(list(s.items()))) for s in b["stages"]]
    before = json.dumps(a)
    ka, kb = live_watch.snapshot_key(a), live_watch.snapshot_key(b)
    assert isinstance(ka, str) and ka == kb != ""
    assert json.dumps(a) == before, "引数を書き換えない"
    expect = json.dumps({k: v for k, v in a.items() if k != "generated_at"}, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    assert ka == expect
    assert "generated_at" not in ka and ka.isascii()


@pytest.mark.parametrize("change", ["final", "empty", "name", "stage_status", "stage_order", "stage_added", "number", "null_vs_text"])
def test_d0031_ac08_snapshot_key_differs_when_the_content_differs(change):
    """D0031-AC-08: 中身が違えば snapshot_key も違う（generated_at 以外のどの項目でも）。"""
    base = live.build_snapshot(ls.base_state(runs=[ls.run("requirements", cost=0.5)]), None, now=NOW)
    other = json.loads(json.dumps(base))
    if change == "final":
        other["final"] = "PASSED"
    elif change == "empty":
        other["empty"] = True
    elif change == "name":
        other["name"] = "別の名前"
    elif change == "stage_status":
        other["stages"][1]["status"] = "running"
    elif change == "stage_order":
        other["stages"].reverse()
    elif change == "stage_added":
        other["stages"].append(dict(other["stages"][0]))
    elif change == "number":
        other["stages"][0]["cost_usd"] = 0.5001
    else:
        other["stages"][0]["started_at"] = ""
    assert live_watch.snapshot_key(base) != live_watch.snapshot_key(other)


def test_d0031_ac09_out_bytes_equal_live_snapshot_dumps(tmp_path):
    """D0031-AC-09: --out の中身は、同じ記録・同じ今で live snapshot が出すバイト列（live.dumps）と同じ。替わったあとの写しも同じ。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ 日本語 😀 <b>&", name="名前 😀")
    rec.begin("requirements")
    out = out_path(tmp_path)
    hide = live_cmd._hide_forms(rec.work)
    res = drive(rec.work, out, hide=hide, steps={1: lambda: rec.done("requirements", "書いた")}, timeout=4.0)
    assert res.events == ["snapshot", "snapshot", "timeout"]
    data = out.read_bytes()
    assert data == expected_bytes(rec.work, NOW + timedelta(seconds=2), hide)
    assert data.isascii() and data.endswith(b"\n") and b"\r" not in data and data.count(b"\n") == 1


# ---- AC-10〜12 書く順番と壊れない書き方 ----------------------------------------------------------------------------------


def test_d0031_ac10_out_is_written_before_line(tmp_path):
    """D0031-AC-10: 先に --out に書いてから行を出す。行を出す瞬間に --out を開くと、その行の seq に対応する中身が読める。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    out = out_path(tmp_path)
    problems = []

    def on_line(text, ft):
        want = expected_bytes(rec.work, ft.now())
        got = out.read_bytes() if out.exists() else None
        if got != want:
            problems.append((text, got))

    steps = {1: lambda: rec.begin("requirements"), 2: lambda: rec.done("requirements", "書いた"), 3: lambda: rec.finish("PASSED")}
    res = drive(rec.work, out, steps=steps, timeout=100.0, stdout=FakeOut(on_line=on_line))
    assert res.seqs == [1, 2, 3, 4]
    assert problems == []


def test_d0031_ac11_reader_never_sees_partial_out(tmp_path, monkeypatch):
    """D0031-AC-11: os.replace の直前に --out を読むと、読めるのは前の完全な写しだけ（空でも半分でもない）。最初の1回では、まだ無い。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    rec.begin("requirements")
    out = out_path(tmp_path)
    first = expected_bytes(rec.work, NOW)
    seen = []
    real = os.replace

    def spy(src, dst, *a, **k):
        seen.append((Path(src), Path(dst), out.read_bytes() if out.exists() else None, Path(src).read_bytes() if Path(src).exists() else None))
        return real(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", spy)
    res = drive(rec.work, out, steps={1: lambda: rec.done("requirements", "書いた")}, timeout=4.0)
    assert res.events == ["snapshot", "snapshot", "timeout"]
    assert len(seen) == 2
    assert seen[0][2] is None
    assert seen[1][2] == first and first.endswith(b"\n")
    assert seen[1][3] == expected_bytes(rec.work, NOW + timedelta(seconds=2)), "置き換える一時ファイルには、新しい写しが全部書き終わっている"
    assert all(dst == out for _s, dst, _o, _t in seen)


def test_d0031_ac12_tmp_file_in_same_dir_and_gone_after_success_and_oserror(tmp_path, monkeypatch):
    """D0031-AC-12: 置き換えの一時ファイルは --out と同じフォルダにあり、書き終わると残らない。置き換えに失敗した（OSError）あとも残らない。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    where = []
    real = os.replace

    def spy(src, dst, *a, **k):
        where.append(Path(src))
        return real(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", spy)
    drive(work, out, timeout=4.0)
    assert len(where) == 1 and where[0].parent == out.parent and where[0].name != out.name
    assert where[0].name.startswith("." + out.name + ".") and where[0].name.endswith(".tmp")
    assert listing(out.parent) == [out.name]

    out2 = tmp_path / "out2" / "live.json"
    out2.parent.mkdir()

    def failing(src, dst, *a, **k):
        raise PermissionError(13, "Permission denied", str(dst))

    monkeypatch.setattr(os, "replace", failing)
    res = drive(work, out2, timeout=20.0)
    assert res.code == 1
    assert listing(out2.parent) == [], "失敗のあとも、一時ファイルも --out も残らない"


@pytest.mark.parametrize("exc", [OSError("boom"), KeyboardInterrupt(), live_watch.Terminated()], ids=["oserror", "keyboardinterrupt", "terminated"])
@pytest.mark.parametrize("where", ["fsync", "replace"])
def test_d0031_ac12_write_atomic_leaves_no_tmp_and_keeps_old_file(tmp_path, monkeypatch, where, exc):
    """D0031-AC-12: write_atomic は、fsync・置き換えのどこで OSError・KeyboardInterrupt・Terminated が来ても、一時ファイルを残さず、前の --out をそのまま残し、例外をそのまま通す。"""
    out = out_path(tmp_path)
    out.write_bytes(b"OLD\n")

    def raiser(*a, **k):
        raise exc

    monkeypatch.setattr(os, where, raiser)
    with pytest.raises(type(exc)):
        live_watch.write_atomic(out, b"NEW-DATA\n")
    assert out.read_bytes() == b"OLD\n"
    assert listing(out.parent) == [out.name]


def test_d0031_ac12_write_atomic_swallows_unlink_failure(tmp_path, monkeypatch):
    """D0031-AC-12: 一時ファイルを消せなくても、元の例外（置き換えの失敗）をそのまま出す（消す側の失敗で上書きしない）。"""
    out = out_path(tmp_path)

    def replace_fails(*a, **k):
        raise OSError("boom-replace")

    def unlink_fails(*a, **k):
        raise OSError("boom-unlink")

    monkeypatch.setattr(os, "replace", replace_fails)
    monkeypatch.setattr(os, "unlink", unlink_fails)
    with pytest.raises(OSError, match="boom-replace"):
        live_watch.write_atomic(out, b"x\n")


def test_d0031_ac12_write_atomic_writes_whole_file(tmp_path):
    """D0031-AC-12: write_atomic は渡したバイト列をそのまま書き、前の中身の尻尾を残さず、--out 以外のものを残さない。"""
    out = out_path(tmp_path)
    out.write_bytes(b"x" * 100000)
    live_watch.write_atomic(out, b'{"a":1}\n')
    assert out.read_bytes() == b'{"a":1}\n'
    assert listing(out.parent) == [out.name]
    live_watch.write_atomic(out, b"")
    assert out.read_bytes() == b""
    big = bytes(range(256)) * 200
    live_watch.write_atomic(out, big)
    assert out.read_bytes() == big and listing(out.parent) == [out.name]


@pytest.mark.skipif(not CAN_SYMLINK, reason="シンボリックリンクを作れない環境")
def test_d0031_ac12_write_atomic_replaces_a_symlink_not_its_target(tmp_path):
    """D0031-AC-12: --out があとからリンクに替えられても、置き換えはリンクの先でなくリンク自身を置き換える（FR-06）。"""
    out = out_path(tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_bytes("守る".encode("utf-8"))
    try:
        out.symlink_to(victim)
    except (OSError, NotImplementedError):
        pytest.skip("シンボリックリンクを作れない環境")
    live_watch.write_atomic(out, b"NEW\n")
    assert victim.read_bytes() == "守る".encode("utf-8")
    assert not out.is_symlink() and out.read_bytes() == b"NEW\n"


# ---- AC-16〜20 行の形と漏れ -------------------------------------------------------------------------------------------


def test_d0031_ac16_flush_after_every_line(tmp_path):
    """D0031-AC-16: 行を出すたびに flush する（最後の行のあとも。次の行の前に必ず）。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    steps = {1: lambda: rec.begin("requirements"), 2: lambda: rec.done("requirements", "書いた"), 3: lambda: rec.finish("PASSED")}
    res = drive(rec.work, out_path(tmp_path), steps=steps, timeout=100.0)
    assert res.events == ["snapshot", "snapshot", "snapshot", "final"]
    assert res.out.flush_calls >= 4
    assert res.out.flushed_after_every_line()
    res2 = drive(midway(tmp_path / "q"), out_path(tmp_path / "q"), timeout=4.0)
    assert res2.events == ["snapshot", "timeout"] and res2.out.flushed_after_every_line(), "timeout の行も flush する"


def test_d0031_ac16_flush_checker_notices_a_missing_flush():
    """D0031-AC-16: flush の検査そのものが、flush の抜けを見つけられること（今のままで通る）。"""
    o = FakeOut()
    o.write('{"a":1}\n')
    o.write('{"a":2}\n')
    o.flush()
    assert not o.flushed_after_every_line()
    ok = FakeOut()
    ok.write("x\n")
    ok.flush()
    assert ok.flushed_after_every_line()


def _scenario_with_every_event(tmp_path, kind):
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    rec.begin("requirements")
    if kind == "timeout":
        return drive(rec.work, out_path(tmp_path), steps={1: lambda: rec.done("requirements", "書いた")}, timeout=6.0)
    return drive(rec.work, out_path(tmp_path), steps={1: lambda: rec.done("requirements", "書いた"), 2: lambda: rec.finish("TEST_FAILED")}, timeout=100.0)


@pytest.mark.parametrize("kind", ["timeout", "final"])
def test_d0031_ac17_lines_are_strict_json_with_four_keys(tmp_path, kind):
    """D0031-AC-17: すべての行は1行の JSON で、厳格な読みで通り、キーは event・seq・final・empty だけ（この順）。型は固定。改行は行の終わりの1つだけ。"""
    res = _scenario_with_every_event(tmp_path, kind)
    assert res.lines, "行が1つも出ていない"
    text = res.text
    assert text.endswith("\n") and "\r" not in text and text.isascii()
    assert text.count("\n") == len(res.lines)
    for raw, obj in zip(text.splitlines(), res.lines):
        assert list(obj) == lw.LINE_KEYS
        assert obj["event"] in ("snapshot", "final", "timeout")
        assert type(obj["seq"]) is int and obj["seq"] >= 0
        assert obj["final"] is None or obj["final"] in live.FINALS
        assert type(obj["empty"]) is bool
        assert raw == json.dumps(obj, ensure_ascii=True, allow_nan=False, separators=(",", ":")), "隙間なし・ASCII"
    assert res.events[-1] == kind


def test_d0031_ac17_event_values_in_a_final_run(tmp_path):
    """D0031-AC-17: final で終わる実行の行の中身（snapshot が続き、最後に final の1行。timeout の行は出ない）。"""
    res = _scenario_with_every_event(tmp_path, "final")
    assert res.lines == [line("snapshot", 1), line("snapshot", 2), line("final", 3, "TEST_FAILED")]
    assert res.code == 0


def test_d0031_ac17_timeout_line_repeats_the_last_emitted_values(tmp_path):
    """D0031-AC-17: timeout の行の seq・final・empty は、最後に出した写しの値。"""
    res = _scenario_with_every_event(tmp_path, "timeout")
    assert res.lines == [line("snapshot", 1), line("snapshot", 2), line("timeout", 2)]


def test_d0031_ac17_timeout_line_when_nothing_was_emitted(tmp_path):
    """D0031-AC-17: 1つも出せていない（--out に書けない）まま上限になったら、timeout の行は seq 0・final null・empty true。"""
    res = drive(midway(tmp_path), out_path(tmp_path), interval=5.0, timeout=1.0, write_fault=lambda n: PermissionError(13, "x"))
    assert res.lines == [line("timeout", 0, None, True)]
    assert res.code == 124
    assert res.reads == 2


MARKS = ["NAME-MARK", "LABEL-MARK", "SESSIONID-MARK", "MEMO-MARK", "RESULT-MARK", "ERROR-MARK", "FEEDBACK-MARK", "STAGEKEY-MARK", "PENDING-MARK"]
# 手元のパスの検査（tests/test_rules.py）に掛からないよう、文字を分けて組み立てる
PATHS = ["/" + "ho" + "me/alice/secret/proj", "C:\\" + "Us" + "ers\\bob\\proj", "/" + "Us" + "ers/carol/x", "D:/work/private"]


def marked_state(**over):
    junk = " ".join(PATHS)
    return ls.base_state(
        name=f"NAME-MARK {junk}",
        session_id="SESSIONID-MARK",
        stages=[ls.stage_entry("STAGEKEY-MARK", f"LABEL-MARK {junk}"), ls.stage_entry("design", "設計")],
        runs=[
            ls.run("STAGEKEY-MARK", is_error=True, result=f"RESULT-MARK {junk}", errors=[f"ERROR-MARK {junk}"], session_id="SESSIONID-MARK"),
            ls.review("STAGEKEY-MARK", "revise", feedback=f"FEEDBACK-MARK {junk}"),
        ],
        pending_review={"stage": "design", "doc": "PENDING-MARK/x.md", "session_id": "SESSIONID-MARK", "since": "2026-10-17T10:00:00+09:00"},
        **over,
    )


def test_d0031_ac18_no_marker_or_path_in_stdout_or_stderr(tmp_path):
    """D0031-AC-18: セッション名・段の名前・session_id・要件メモ・result/errors/feedback に目印と手元のパスを入れても、標準出力にも標準エラーにも出ない。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    ls.write_state(work, marked_state())
    (work / "00_input.md").write_text("MEMO-MARK " + " ".join(PATHS), encoding="utf-8")
    forbidden = MARKS + PATHS + [str(tmp_path), str(work), str(out), "Users", "/home/"]
    steps = {1: lambda: ls.write_state(work, marked_state(final="STAGE_ERROR"))}
    res = drive(work, out, hide=live_cmd._hide_forms(work), steps=steps, timeout=100.0)
    assert res.events == ["snapshot", "final"], "変わったので2行が出て、final で止まる"
    for bad in forbidden:
        assert bad not in res.text and bad not in res.errtext, bad
    # 書けなかったとき・上限のときの標準エラーにも出ない
    res2 = drive(work, out_path(tmp_path / "x"), hide=live_cmd._hide_forms(work), write_fault=lambda n: PermissionError(13, "Permission denied", str(out)))
    assert res2.code == 1 and res2.errtext
    for bad in forbidden + ["Permission denied"]:
        assert bad not in res2.text and bad not in res2.errtext, bad


def test_d0031_ac18_hide_forms_are_passed_to_the_snapshot(tmp_path):
    """D0031-AC-18: hide に渡した読み先のパスの形が、名前に混じっていても --out の写しに出ない（短い見本のパスで確かめる。名前は 60 字で切れるため）。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    ls.write_state(work, ls.base_state(name="p=/zz/hidden/rec|end"))  # 直前が空白でないので、hide でしか消えない
    res = drive(work, out, hide=("/zz/hidden",), timeout=2.0)
    assert res.events == ["snapshot", "timeout"]
    text = out.read_text(encoding="utf-8")
    assert "/zz/hidden" not in text and "end" in text
    plain = tmp_path / "plain"
    ls.write_state(plain, ls.base_state(name="p=/zz/hidden/rec|end"))
    out2 = out_path(tmp_path / "o2")
    drive(plain, out2, timeout=2.0)
    assert "/zz/hidden" in out2.read_text(encoding="utf-8"), "hide を渡さなければ消えない（上の確かめが空振りでないこと）"


@pytest.mark.parametrize("bad", ["weird", "passed", "AWAITING_REVIEW", "", " PASSED", "PASSED\n", 5, True, ["PASSED"], {"a": 1}, 1.5, "PASSED\u0000"],
                         ids=["unknown", "lower", "awaiting", "empty", "space", "newline", "int", "true", "list", "dict", "float", "nul"])
def test_d0031_ac19_unknown_final_gives_snapshot_null(tmp_path, bad):
    """D0031-AC-19: 未知の文字・型違いの final では、final が null の snapshot の行になる（final の行にならず、止まらない）。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    ls.write_state(work, ls.base_state(final=bad))
    res = drive(work, out, timeout=6.0)
    assert res.lines[0] == line("snapshot", 1, None, False)
    assert res.events == ["snapshot", "timeout"] and res.code == 124
    assert res.reads == 4, "止まらずに見張り続ける"
    assert json.loads(out.read_bytes())["final"] is None


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999"])
def test_d0031_ac20_no_nan_or_infinity_in_lines(tmp_path, raw):
    """D0031-AC-20: 記録に NaN・Infinity が入っていても、行にも --out にも NaN・Infinity の文字が出ない。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    text = json.dumps(ls.base_state(runs=[ls.run("requirements", cost="@@", duration="@@", turns="@@")]), ensure_ascii=False)
    work.mkdir()
    (work / "state.json").write_text(text.replace('"@@"', raw), encoding="utf-8")
    res = drive(work, out, timeout=4.0)
    assert res.events == ["snapshot", "timeout"]
    for source in (res.text, out.read_text(encoding="utf-8")):
        assert "NaN" not in source and "Infinity" not in source


# ---- AC-21〜25 final と止まる条件 ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("final", list(live.FINALS))
def test_d0031_ac21_each_final_writes_out_emits_final_line_exit0(tmp_path, final):
    """D0031-AC-21: final が入った写しを --out に書き、event: final の行を1つ出し（snapshot の行は別に出さない）、終了コード 0 で止まる。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    rec.begin("requirements")
    out = out_path(tmp_path)
    res = drive(rec.work, out, steps={2: both(lambda: rec.done("requirements", "書いた"), lambda: rec.finish(final))}, timeout=100.0)
    assert res.lines == [line("snapshot", 1), line("final", 2, final)]
    assert res.code == 0 and res.errtext == ""
    assert out.read_bytes() == expected_bytes(rec.work, NOW + timedelta(seconds=4))
    assert json.loads(out.read_bytes())["final"] == final
    assert res.time.sleeps == pytest.approx([2.0, 2.0]) and res.reads == 3


@pytest.mark.parametrize("final", list(live.FINALS))
def test_d0031_ac22_already_final_at_start_emits_final_seq1_exit0(tmp_path, final):
    """D0031-AC-22: 起動したときにすでに final が入っている記録は、1回目で event: final・seq 1 を出して終了コード 0（読みは1回、眠らない）。"""
    work = finished_record(tmp_path / "p", final)
    out = out_path(tmp_path)
    res = drive(work, out, timeout=100.0)
    assert res.lines == [line("final", 1, final)]
    assert res.code == 0 and res.reads == 1 and res.time.sleeps == [] and res.errtext == ""
    assert out.read_bytes() == expected_bytes(work, NOW)


def test_d0031_ac23_after_final_no_read_no_sleep_no_line(tmp_path):
    """D0031-AC-23: final の行を出したあとは、記録を読まない・眠らない・何も出さない。記録を書き換える偽の書き手が続いても同じ。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    rec.begin("requirements")
    out = out_path(tmp_path)
    called = []
    steps = {
        1: both(lambda: rec.done("requirements", "書いた"), lambda: rec.finish("PASSED")),
        2: lambda: called.append(2),
        3: lambda: called.append(3),
    }
    res = drive(rec.work, out, steps=steps, timeout=100.0)
    assert res.events == ["snapshot", "final"]
    assert res.reads == 2 and len(res.time.sleeps) == 1
    assert called == [], "final のあと眠っていない"
    assert res.write_attempts == 2
    assert out.read_bytes() == expected_bytes(rec.work, NOW + timedelta(seconds=2))


def test_d0031_ac24_final_and_stage_change_same_tick_one_line(tmp_path):
    """D0031-AC-24: final が入る回に段の状態も変わっていても、行は final の1つで、--out はその最後の写し。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    rec = Rec(tmp_path, datetime(2026, 10, 17, 11, 0, 0))
    res = drive(work, out, steps={1: both(lambda: rec.done("design", "設計した"), lambda: rec.finish("BLOCKED"))}, timeout=100.0)
    assert res.lines == [line("snapshot", 1), line("final", 2, "BLOCKED")]
    snap = json.loads(out.read_bytes())
    assert snap["final"] == "BLOCKED" and [s["status"] for s in snap["stages"]][1] == "done"
    assert res.code == 0


def test_d0031_ac25_pending_review_does_not_stop_and_resumes_on_review(tmp_path):
    """D0031-AC-25: pending_review（final は null）では止まらず、review の状態の写しを1回出す。続いて review approved と次の段の begin を書くと、その回に出る。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    rec.begin("requirements")
    rec.done("requirements", "書いた")
    rec.wait("requirements")
    out = out_path(tmp_path)
    outs = []
    steps = {3: both(lambda: rec.review("requirements", "approved"), lambda: rec.begin("design"))}
    res = drive(rec.work, out, steps=steps, timeout=12.0, stdout=FakeOut(on_line=lambda t, ft: outs.append(json.loads(out.read_bytes()))))
    assert res.events == ["snapshot", "snapshot", "timeout"] and res.code == 124
    assert res.lines[0] == line("snapshot", 1, None, False)
    assert [s["status"] for s in outs[0]["stages"]][0] == "review"
    assert outs[0]["stages"][0]["pending_since"] is not None
    assert res.out.times == pytest.approx([0.0, 6.0, 12.0]), "止まらずに見張り、承認の回に出る"
    assert [s["status"] for s in outs[1]["stages"]][:2] == ["done", "running"]


# ---- AC-26〜30 上限・間隔 ---------------------------------------------------------------------------------------------


def test_d0031_ac26_timeout_line_exit124_out_unchanged(tmp_path):
    """D0031-AC-26: 上限に達した周期で event: timeout の行を1つ出して終了コード 124。--out は最後に出した写しから変わらない。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    stamps = []
    res = drive(work, out, interval=2.0, timeout=10.0,
                stdout=FakeOut(on_line=lambda t, ft: stamps.append((out.read_bytes(), out.stat().st_mtime_ns))))
    assert res.lines == [line("snapshot", 1), line("timeout", 1)]
    assert res.code == 124
    assert len(set(stamps)) == 1, "timeout の行のときも --out は書き換わっていない"
    assert res.out.times == pytest.approx([0.0, 10.0])


@pytest.mark.parametrize(
    "timeout,interval,sleeps",
    [(10.0, 2.0, [2.0] * 5), (9.0, 2.0, [2.0, 2.0, 2.0, 2.0, 1.0]), (10.0, 9.0, [9.0, 1.0]), (10.0, 10.0, [10.0]), (1.0, 0.5, [0.5, 0.5]),
     (1.0, 60.0, [1.0]), (86400.0, 60.0, [60.0] * 1440), (3.0, 60.0, [3.0])],
    ids=["even", "short_last", "one_second_before", "equal", "min_min", "interval_over", "max_timeout", "tiny"],
)
def test_d0031_ac26_timeout_boundary_stops_exactly_at_the_limit(tmp_path, timeout, interval, sleeps):
    """D0031-AC-26: ちょうど上限の回で止まる（1 秒前までは止まらない）。AC-28: 最後の眠りは残りの分だけ。"""
    res = drive(midway(tmp_path), out_path(tmp_path), interval=interval, timeout=timeout)
    assert res.code == 124
    assert res.time.sleeps == pytest.approx(sleeps)
    assert res.reads == len(sleeps) + 1
    assert res.time.elapsed == pytest.approx(timeout)
    assert res.events == ["snapshot", "timeout"]


def test_d0031_ac27_reads_once_before_checking_timeout(tmp_path):
    """D0031-AC-27: 上限に達する周期でも、先に記録を1回読み、変わっていれば写しを書いて行を出し、そのあとで上限を調べる。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    rec.begin("requirements")
    out = out_path(tmp_path)
    res = drive(rec.work, out, interval=5.0, timeout=10.0, steps={2: lambda: rec.done("requirements", "書いた")})
    assert res.events == ["snapshot", "snapshot", "timeout"] and res.seqs == [1, 2, 2]
    assert res.reads == 3 and res.time.elapsed == pytest.approx(10.0)
    assert out.read_bytes() == expected_bytes(rec.work, NOW + timedelta(seconds=10))


def test_d0031_ac27_final_at_the_timeout_tick_wins_over_timeout(tmp_path):
    """D0031-AC-27: 上限の周期に final が入っていたら、final の行で終了コード 0（timeout の行は出ない）。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    rec.begin("requirements")
    res = drive(rec.work, out_path(tmp_path), interval=5.0, timeout=10.0,
                steps={2: both(lambda: rec.done("requirements", "書いた"), lambda: rec.finish("PASSED"))})
    assert res.lines == [line("snapshot", 1), line("final", 2, "PASSED")]
    assert res.code == 0


def test_d0031_ac27_change_after_the_timeout_is_never_read(tmp_path):
    """D0031-AC-27: 上限のあとに起きる変わりは読まない（上限の周期の読みが最後）。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    rec.begin("requirements")
    later = []
    res = drive(rec.work, out_path(tmp_path), interval=5.0, timeout=10.0, steps={3: lambda: later.append(1)})
    assert res.events == ["snapshot", "timeout"] and later == [] and res.reads == 3


@pytest.mark.parametrize("interval,timeout,sleeps", [(60.0, 5.0, [5.0]), (2.0, 5.0, [2.0, 2.0, 1.0]), (0.75, 2.0, [0.75, 0.75, 0.5]), (3.0, 10.0, [3.0, 3.0, 3.0, 1.0])])
def test_d0031_ac28_sleep_never_exceeds_remaining(tmp_path, interval, timeout, sleeps):
    """D0031-AC-28: 眠る時間は --interval で、残り時間より長く眠らない（--interval 60 --timeout 5 なら 5 を超えない）。"""
    res = drive(midway(tmp_path), out_path(tmp_path), interval=interval, timeout=timeout)
    assert res.time.sleeps == pytest.approx(sleeps)
    remaining = timeout
    for s in res.time.sleeps:
        assert 0 < s <= interval + 1e-9 and s <= remaining + 1e-9
        remaining -= s


@pytest.mark.parametrize("interval,timeout,reads,sleeps", [(2.0, 10.0, 6, 5), (3.0, 10.0, 5, 4), (10.0, 10.0, 2, 1), (0.5, 1.0, 3, 2), (1.0, 1.0, 2, 1), (4.0, 9.0, 4, 3)])
def test_d0031_ac30_read_count_is_fixed(tmp_path, interval, timeout, reads, sleeps):
    """D0031-AC-30: 読みの回数は決まっている（最初の1回＋眠りごと）。--interval 2 --timeout 10 なら読み 6 回・眠り 5 回。"""
    res = drive(midway(tmp_path), out_path(tmp_path), interval=interval, timeout=timeout)
    assert (res.reads, len(res.time.sleeps)) == (reads, sleeps)
    assert res.lines[0] == line("snapshot", 1)


# ---- AC-29 間隔と上限の検査（純粋な部分。引数の通りは tests/test_live_watch_cli.py）-----------------------------------------


@pytest.mark.parametrize("text,value", [("0.5", 0.5), ("60", 60.0), ("2", 2.0), ("2.0", 2.0), ("0.50", 0.5), ("59.999", 59.999), ("1", 1.0), ("30.5", 30.5), ("6e1", 60.0)])
def test_d0031_ac29_parse_interval_accepts_the_range_including_both_ends(text, value):
    """D0031-AC-29: --interval は 0.5〜60 秒（両端を含む）を通し、float で返す。"""
    got = live_watch.parse_interval(text)
    assert type(got) is float and got == pytest.approx(value)


@pytest.mark.parametrize("text", ["0.49", "0.4999999", "60.01", "60.0000001", "0", "-1", "-0.5", "-0", "abc", "nan", "NaN", "inf", "-inf", "Infinity", "1e999", "", " ", "1,5", "0x10", "2 秒", "None", "true"])
def test_d0031_ac29_parse_interval_refuses_outside_nan_inf_and_text(text):
    """D0031-AC-29: 範囲の外・0・負・数でない・nan・inf は、argparse.ArgumentTypeError で断る。"""
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        live_watch.parse_interval(text)


@pytest.mark.parametrize("text,value", [("1", 1.0), ("86400", 86400.0), ("1.0", 1.0), ("21600", 21600.0), ("86399.999", 86399.999), ("10", 10.0), ("8.64e4", 86400.0)])
def test_d0031_ac29_parse_timeout_accepts_the_range_including_both_ends(text, value):
    """D0031-AC-29: --timeout は 1 秒〜24 時間（両端を含む）を通し、float で返す。"""
    got = live_watch.parse_timeout(text)
    assert type(got) is float and got == pytest.approx(value)


@pytest.mark.parametrize("text", ["0.99", "0.9999999", "86401", "86400.001", "0", "-1", "-86400", "abc", "nan", "NaN", "inf", "-inf", "Infinity", "1e999", "", " ", "1h", "6 * 3600", "0x10"])
def test_d0031_ac29_parse_timeout_refuses_outside_nan_inf_and_text(text):
    """D0031-AC-29: 範囲の外・0・負・数でない・nan・inf は、argparse.ArgumentTypeError で断る。"""
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        live_watch.parse_timeout(text)


def test_d0031_ac29_constants_are_defined_once():
    """D0031-AC-29: 既定値・範囲・閾値・終了コードは定数で1か所に持つ（live_watch.py）。"""
    assert (live_watch.DEFAULT_INTERVAL, live_watch.MIN_INTERVAL, live_watch.MAX_INTERVAL) == (2.0, 0.5, 60.0)
    assert (live_watch.DEFAULT_TIMEOUT, live_watch.MIN_TIMEOUT, live_watch.MAX_TIMEOUT) == (6 * 3600.0, 1.0, 24 * 3600.0)
    assert (live_watch.UNREADABLE_LIMIT, live_watch.WRITE_FAIL_LIMIT) == (3, 3)
    assert (live_watch.EXIT_OK, live_watch.EXIT_WRITE_OR_PIPE, live_watch.EXIT_USAGE) == (0, 1, 2)
    assert (live_watch.EXIT_TIMEOUT, live_watch.EXIT_SIGINT, live_watch.EXIT_SIGTERM) == (124, 130, 143)


# ---- decide（純粋な判定）-----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "last,key,readable,misses,expect",
    [
        (None, "A", True, 0, (True, 0)),
        (None, "E", False, 0, (True, 1)),
        ("A", "A", True, 0, (False, 0)),
        ("A", "A", True, 2, (False, 0)),
        ("A", "B", True, 0, (True, 0)),
        ("A", "B", True, 2, (True, 0)),
        ("A", "E", False, 0, (False, 1)),
        ("A", "E", False, 1, (False, 2)),
        ("A", "E", False, 2, (True, 3)),
        ("E", "A", True, 0, (True, 0)),
    ],
)
def test_d0031_ac31_decide_table(last, key, readable, misses, expect):
    """D0031-AC-31: decide の表（最初の1回は必ず出す／読めて違えば出す／読めないときは3回目で出す／読めたら数え直す）。"""
    assert live_watch.decide(last, key, readable=readable, misses=misses) == expect


@pytest.mark.parametrize("misses", [0, 1, 2, 5])
def test_d0031_ac33_decide_does_not_repeat_the_empty_snapshot(misses):
    """D0031-AC-33: すでに「記録なし」を出している（直前の key と同じ）なら、読めない状態が続いても出さない。"""
    emit, _ = live_watch.decide("E", "E", readable=False, misses=misses)
    assert emit is False
    assert live_watch.decide("A", "E", readable=False, misses=2)[0] is True, "直前が「記録なし」でなければ、3回目で出す（上が空振りでないこと）"


SIM = {
    "steady": (["A", "A", "A"], "TFF"),
    "blip1": (["A", "U", "A"], "TFF"),
    "blip2": (["A", "U", "U", "A"], "TFFF"),
    "gone3": (["A", "U", "U", "U"], "TFFT"),
    "gone5": (["A", "U", "U", "U", "U", "U"], "TFFTFF"),
    "gone3_back": (["A", "U", "U", "U", "A"], "TFFTT"),
    "reset": (["A", "U", "U", "A", "U", "U"], "TFFFFF"),
    "reset_then_gone": (["A", "U", "U", "A", "U", "U", "U"], "TFFFFFT"),
    "start_gone": (["U", "U", "U"], "TFF"),
    "start_gone_back": (["U", "A"], "TT"),
    "start_gone_back_gone": (["U", "A", "U", "U", "U"], "TTFFT"),
    "changes": (["A", "B", "A"], "TTT"),
    "change_in_gap": (["A", "U", "B"], "TFT"),
    "change_after_gap2": (["A", "U", "U", "B"], "TFFT"),
    "gone4_then_change": (["A", "U", "U", "U", "U", "B"], "TFFTFT"),
    "gone3_then_same_as_before": (["A", "U", "U", "U", "A", "A"], "TFFTTF"),
}


@pytest.mark.parametrize("name", sorted(SIM))
def test_d0031_ac31_decide_sequences(name):
    """D0031-AC-31・32・33: 読めた・読めなかったの並びに対する出す・出さないの並び（読めないのは3回連続で初めて「記録なし」を出す）。"""
    seq, expect = SIM[name]
    last, misses, got = None, 0, ""
    for item in seq:
        readable = item != "U"
        key = "E" if item == "U" else item
        emit, misses = live_watch.decide(last, key, readable=readable, misses=misses)
        assert type(emit) is bool and type(misses) is int
        got += "T" if emit else "F"
        if emit:
            last = key
    assert got == expect


# ---- AC-31〜39 記録が揺れるとき ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("gone_reads,empty_line", [(1, False), (2, False), (3, True), (4, True), (7, True)])
def test_d0031_ac31_state_gone_emits_empty_once_after_limit_and_not_before(tmp_path, gone_reads, empty_line):
    """D0031-AC-31: state.json が消えて、連続3回読めなかったあとに empty: true の行を1つだけ出す。3回に達する前に同じ中身で戻れば、何も出さない。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    saved = (work / "state.json").read_bytes()
    steps = {1: lambda: (work / "state.json").unlink(), 1 + gone_reads: lambda: (work / "state.json").write_bytes(saved)}
    res = drive(work, out, steps=steps, timeout=24.0)
    assert len([x for x in res.lines if x["empty"] is True]) == (1 if empty_line else 0)
    if empty_line:
        assert [(x["event"], x["empty"]) for x in res.lines] == [("snapshot", False), ("snapshot", True), ("snapshot", False), ("timeout", False)]
        assert res.out.times[:3] == pytest.approx([0.0, 6.0, 2.0 * (gone_reads + 1)])
    else:
        assert res.events == ["snapshot", "timeout"]


def test_d0031_ac31_empty_line_comes_on_the_third_unreadable_read(tmp_path):
    """D0031-AC-31: 「記録なし」の行は、3回目の読めなかった回（閾値の回）に出る。2回目までは出ない。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    res = drive(work, out, steps={2: lambda: (work / "state.json").unlink()}, timeout=20.0)
    assert res.lines[:2] == [line("snapshot", 1), line("snapshot", 2, None, True)]
    assert res.out.times[:2] == pytest.approx([0.0, 8.0]), "読めない回は 3(4s)・4(6s)・5(8s) → 8 秒の回に出る"
    assert json.loads(out.read_bytes())["empty"] is True
    assert res.events == ["snapshot", "snapshot", "timeout"]


UNREADABLE = {
    "empty": (lambda w: (w / "state.json").write_bytes(b""), None),
    "cut_json": (lambda w: (w / "state.json").write_bytes((w / "state.json").read_bytes()[:40]), None),
    "bom": (lambda w: (w / "state.json").write_bytes(b"\xef\xbb\xbf" + (w / "state.json").read_bytes()), None),
    "not_utf8": (lambda w: (w / "state.json").write_bytes(b"\xff\xfe\x00{"), None),
    "array": (lambda w: (w / "state.json").write_bytes(b"[]"), None),
    "null": (lambda w: (w / "state.json").write_bytes(b"null"), None),
    "garbage": (lambda w: (w / "state.json").write_bytes(b"\x00" * 64), None),
    "no_permission": (lambda w: os.chmod(w / "state.json", 0), lambda w: os.chmod(w / "state.json", 0o644)),
    "folder": (lambda w: ((w / "state.json").unlink(), (w / "state.json").mkdir()), lambda w: (w / "state.json").rmdir()),
    "dangling_link": (lambda w: ((w / "state.json").unlink(), (w / "state.json").symlink_to(w / "ghost.json")), lambda w: (w / "state.json").unlink()),
    "too_big": (lambda w: (w / "state.json").write_bytes(b'{"pad": "' + b"a" * (live.MAX_STATE_BYTES + 8) + b'"}'), None),
}


@pytest.mark.parametrize("kind", sorted(UNREADABLE))
def test_d0031_ac32_single_unreadable_read_emits_nothing(tmp_path, kind):
    """D0031-AC-32: 1回だけ読めない（空・途中で切れた JSON・BOM・UTF-8 でない・権限なし・フォルダ・切れたリンク・大きすぎ）あと、すぐに読めて前と同じ中身なら、行は出ない。"""
    if kind == "no_permission" and (IS_ROOT or os.name == "nt"):
        pytest.skip("root・Windows では権限なしを作れない")
    if kind == "dangling_link" and not CAN_SYMLINK:
        pytest.skip("シンボリックリンクを作れない環境")
    work, out = midway(tmp_path), out_path(tmp_path)
    saved = (work / "state.json").read_bytes()
    damage, undo = UNREADABLE[kind]

    def fix():
        if undo is not None:
            undo(work)
        (work / "state.json").write_bytes(saved)

    res = drive(work, out, steps={1: lambda: damage(work), 2: fix}, timeout=12.0)
    assert res.events == ["snapshot", "timeout"], "1回の読み損ないでは「記録なし」を出さない"
    assert res.write_ok == 1
    assert res.reads == 7


def test_d0031_ac33_no_second_empty_line_and_recovery_emits(tmp_path):
    """D0031-AC-33: 「記録なし」を出したあと、同じ読めない状態が続いても2つ目は出ない。読めるようになったら、その写しの行が出る。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    saved = (work / "state.json").read_bytes()
    steps = {1: lambda: (work / "state.json").unlink(), 10: lambda: (work / "state.json").write_bytes(saved)}
    res = drive(work, out, steps=steps, timeout=30.0)
    assert [(x["event"], x["empty"]) for x in res.lines] == [("snapshot", False), ("snapshot", True), ("snapshot", False), ("timeout", False)]
    assert res.seqs == [1, 2, 3, 3]
    assert res.out.times[:3] == pytest.approx([0.0, 6.0, 20.0])
    assert json.loads(out.read_bytes())["empty"] is False


def test_d0031_ac33_gone_then_a_different_record_emits_it(tmp_path):
    """D0031-AC-33: 「記録なし」のあとに別の中身の記録が現れたら、その写しが出る。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    ls.write_state(work, ls.base_state(name="一つ目"))
    steps = {1: lambda: (work / "state.json").unlink(), 8: lambda: ls.write_state(work, ls.base_state(name="二つ目"))}
    res = drive(work, out, steps=steps, timeout=30.0)
    assert [x["empty"] for x in res.lines[:3]] == [False, True, False]
    assert json.loads(out.read_bytes())["name"] == "二つ目"


def test_d0031_ac34_record_start_archive_flow_does_not_crash_or_stop_on_old_final(tmp_path):
    """D0031-AC-34: 同じ周期の間に前の実行が final で終わり、record start で archive に移って新しい実行が現れても、落ちず、前の final では止まらない。"""
    rec = Rec(tmp_path / "p")
    rec.start("一つ目", name="一つ目の実行")
    rec.begin("requirements")
    out = out_path(tmp_path)
    flow = both(lambda: rec.done("requirements", "書いた"), lambda: rec.finish("PASSED"), lambda: rec.start("二つ目", name="二つ目の実行"))
    res = drive(rec.work, out, steps={1: flow}, timeout=8.0)
    assert res.events == ["snapshot", "snapshot", "timeout"] and res.code == 124
    assert json.loads(out.read_bytes())["name"] == "二つ目の実行" and json.loads(out.read_bytes())["final"] is None
    assert (rec.work / "archive").is_dir()


@pytest.mark.parametrize("gone_reads", [1, 2, 3, 5])
def test_d0031_ac34_state_moves_to_archive_and_a_new_record_appears(tmp_path, gone_reads):
    """D0031-AC-34: archive に移って state.json が消える→新しい state.json が現れる流れで、落ちない。新しい中身が出る（3回以上消えていれば「記録なし」も先に出る）。"""
    rec = Rec(tmp_path / "p")
    rec.start("一つ目", name="一つ目の実行")
    rec.begin("requirements")
    rec.done("requirements", "書いた")
    rec.finish("STOPPED_BY_HUMAN")  # 起動時の final で止まらないよう、見張りを始める前に start で作り直す
    rec.start("二つ目", name="二つ目の実行")
    rec.begin("requirements")
    out = out_path(tmp_path)
    work = rec.work
    arch = work / "archive" / "x"

    def archive():
        arch.mkdir(parents=True)
        (work / "state.json").replace(arch / "state.json")

    def renew():
        ls.write_state(work, ls.base_state(name="三つ目の実行"))

    res = drive(work, out, steps={1: archive, 1 + gone_reads: renew}, timeout=30.0)
    empties = 1 if gone_reads >= 3 else 0
    assert res.events == ["snapshot"] + ["snapshot"] * (empties + 1) + ["timeout"]
    assert res.code == 124
    assert json.loads(out.read_bytes())["name"] == "三つ目の実行"
    assert [x["empty"] for x in snaps(res)] == [False] + ([True] if empties else []) + [False]


def test_d0031_ac34_final_stops_only_when_a_final_snapshot_is_emitted(tmp_path):
    """D0031-AC-34: 新しい実行がまた final で終われば、そのときは止まる（0）。止まるのは新しい実行の final。"""
    rec = Rec(tmp_path / "p")
    rec.start("一つ目", name="一つ目の実行")
    rec.begin("requirements")
    steps = {
        1: both(lambda: rec.done("requirements", "書いた"), lambda: rec.finish("PASSED"), lambda: rec.start("二つ目", name="二つ目の実行")),
        3: both(lambda: rec.begin("requirements"), lambda: rec.done("requirements", "また書いた"), lambda: rec.finish("TEST_FAILED")),
    }
    res = drive(rec.work, out_path(tmp_path), steps=steps, timeout=100.0)
    assert res.lines == [line("snapshot", 1), line("snapshot", 2), line("final", 3, "TEST_FAILED")]
    assert res.code == 0


def test_d0031_ac35_identical_after_rebuild_emits_nothing_different_emits(tmp_path):
    """D0031-AC-35: 作り直しで中身が前に出したものと完全に同じになった場合は出ない。違えば出る。比べるのは直前に出したものだけ（A → B → A は3回出る）。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    a, b = ls.base_state(name="A"), ls.base_state(name="B")
    ls.write_state(work, a)

    def gone():
        (work / "state.json").unlink()

    steps = {
        1: gone, 2: lambda: ls.write_state(work, a),   # 同じ中身で作り直し → 出ない
        3: gone, 4: lambda: ls.write_state(work, b),   # 違う中身 → 出る
        5: gone, 6: lambda: ls.write_state(work, a),   # A に戻る → 直前（B）と違うので出る
    }
    res = drive(work, out, steps=steps, timeout=20.0)
    assert res.events == ["snapshot", "snapshot", "snapshot", "timeout"]
    assert res.out.times == pytest.approx([0.0, 8.0, 12.0, 20.0])
    assert json.loads(out.read_bytes())["name"] == "A"


def test_d0031_ac36_dir_created_later_emits_on_appearance(tmp_path):
    """D0031-AC-36: 読み先のフォルダが最初は無く、あとで作られて state.json が現れると、その回に出る。それまでは最初の「記録なし」の1行だけ。"""
    work, out = tmp_path / "later" / "rec", out_path(tmp_path)
    steps = {5: lambda: ls.write_state(work, ls.base_state(name="現れた"))}
    res = drive(work, out, steps=steps, timeout=20.0)
    assert [(x["event"], x["seq"], x["empty"]) for x in res.lines] == [("snapshot", 1, True), ("snapshot", 2, False), ("timeout", 2, False)]
    assert res.out.times == pytest.approx([0.0, 10.0, 20.0])
    assert json.loads(out.read_bytes())["name"] == "現れた"


def test_d0031_ac37_huge_state_stays_bounded_and_memory_holds_one_key(tmp_path):
    """D0031-AC-37: runs が数万行ある記録でも、1回の読みが上限の中で終わり、落ちず、写しは 32 KiB 以内。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    work.mkdir()
    state = ls.base_state(runs=[{"stage": "design", "seq": i, "cost_usd": 0.001, "num_turns": 1} for i in range(50000)])
    (work / "state.json").write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    size = (work / "state.json").stat().st_size
    assert 1_000_000 < size < live.MAX_STATE_BYTES
    res = drive(work, out, timeout=6.0)
    assert res.events == ["snapshot", "timeout"] and res.lines[0]["empty"] is False
    assert len(out.read_bytes()) <= live.MAX_BYTES


def test_d0031_ac37_over_limit_state_is_empty_and_bounded(tmp_path):
    """D0031-AC-37: 4 MiB を超える state.json は読まず、「記録なし」になる（落ちない）。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    work.mkdir()
    (work / "state.json").write_bytes(b'{"pad": "' + b"a" * (live.MAX_STATE_BYTES + 100) + b'"}')
    res = drive(work, out, timeout=4.0)
    assert res.lines[0] == line("snapshot", 1, None, True) and res.code == 124


def test_d0031_ac37_memory_does_not_grow_over_many_ticks(tmp_path):
    """D0031-AC-37: 長く見張っても、覚えている量が増え続けない（周期を重ねても保持する写しの文字列は1つ）。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    ls.write_state(work, ls.base_state(stages=[ls.stage_entry(f"stage-{i:02d}-" + "x" * 20, "ラベル" * 8) for i in range(24)]))
    samples = {}

    def hook(n):
        if n in (20, 400):
            gc.collect()
            samples[n] = tracemalloc.get_traced_memory()[0]

    tracemalloc.start()
    try:
        res = drive(work, out, timeout=830.0, sleep_hook=hook)
    finally:
        tracemalloc.stop()
    assert res.events == ["snapshot", "timeout"] and res.reads == 416
    assert len(out.read_bytes()) > 4000, "写しがそれなりの大きさ（漏れれば目立つ）"
    assert samples[400] - samples[20] < 256 * 1024


BAD_LOGS = {
    "missing_log": lambda w: None,
    "garbage": lambda w: (w / "logs" / "02_design.jsonl").write_bytes(b"\xff\xff garbage\n{{{\n"),
    "giant_line": lambda w: (w / "logs" / "02_design.jsonl").write_text(json.dumps(ls.prompt_line("2026-10-17T10:00:00+09:00", pad="x" * 100_000)) + "\n", encoding="utf-8"),
    "giant_file": lambda w: (w / "logs" / "02_design.jsonl").write_bytes(b"{}\n" * 100_000),
    "log_is_dir": lambda w: (w / "logs" / "02_design.jsonl").mkdir(),
    "prompt_after_50_lines": lambda w: (w / "logs" / "02_design.jsonl").write_text(
        "".join(json.dumps({"_type": "Other", "n": i}) + "\n" for i in range(60)) + json.dumps(ls.prompt_line("2026-10-17T10:00:00+09:00")) + "\n", encoding="utf-8"),
}


@pytest.mark.parametrize("kind", sorted(BAD_LOGS))
def test_d0031_ac38_bad_open_log_is_safe_on_watch_path(tmp_path, kind):
    """D0031-AC-38: 動いている段のログが無い・壊れている・巨大でも、見張りは落ちず、started_at が null の写しを出して続ける（同じ中身なら増えて出さない）。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    ls.write_state(work, ls.base_state(open=ls.opened("design", seq=2)))
    (work / "logs").mkdir()
    BAD_LOGS[kind](work)
    res = drive(work, out, timeout=6.0)
    assert res.events == ["snapshot", "timeout"] and res.code == 124
    snap = json.loads(out.read_bytes())
    assert snap["empty"] is False and snap["stages"][1]["status"] == "running" and snap["stages"][1]["started_at"] is None


def test_d0031_ac38_log_name_with_dotdot_does_not_read_outside(tmp_path):
    """D0031-AC-38: open.log の名前が ../ を含んでも、work_dir の外のファイルは読まない（そこに正しい Prompt 行があっても started_at は null）。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    ls.write_state(work, ls.base_state(open=ls.opened("design", seq=2, log="../02_design.jsonl")))
    ls.write_log(tmp_path, "02_design.jsonl", [ls.prompt_line("2026-10-17T10:00:00+09:00")])
    ls.write_log(work, "02_design.jsonl", [ls.prompt_line("2026-10-17T10:00:00+09:00")])
    res = drive(work, out, timeout=4.0)
    assert res.events == ["snapshot", "timeout"]
    assert json.loads(out.read_bytes())["stages"][1]["started_at"] is None


@pytest.mark.skipif(not CAN_SYMLINK, reason="シンボリックリンクを作れない環境")
@pytest.mark.parametrize("what", ["logs_dir_link", "log_file_link"])
def test_d0031_ac38_symlinked_log_is_not_followed(tmp_path, what):
    """D0031-AC-38: logs フォルダやログのファイルがシンボリックリンクでも、リンクの先（読み先の外）は読まない。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    ls.write_state(work, ls.base_state(open=ls.opened("design", seq=2)))
    outside = tmp_path / "outside"
    ls.write_log(outside, "02_design.jsonl", [ls.prompt_line("2026-10-17T10:00:00+09:00")])
    try:
        if what == "logs_dir_link":
            (work / "logs").symlink_to(outside / "logs", target_is_directory=True)
        else:
            (work / "logs").mkdir()
            (work / "logs" / "02_design.jsonl").symlink_to(outside / "logs" / "02_design.jsonl")
    except (OSError, NotImplementedError):
        pytest.skip("シンボリックリンクを作れない環境")
    res = drive(work, out, timeout=4.0)
    assert res.events == ["snapshot", "timeout"]
    assert json.loads(out.read_bytes())["stages"][1]["started_at"] is None


FAULTS = [RuntimeError("boom"), ValueError("boom"), TypeError("boom"), KeyError("boom"), MemoryError(), RecursionError(), PermissionError(13, "x"), AttributeError("boom"), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")]


@pytest.mark.parametrize("exc", FAULTS, ids=lambda e: type(e).__name__)
@pytest.mark.parametrize("which", ["read_state", "read_open_at"])
def test_d0031_ac39_unexpected_exception_is_unreadable_but_keyboardinterrupt_passes(tmp_path, which, exc):
    """D0031-AC-39: read_state・read_open_at が予期しない例外を投げる偽でも、見張りは落ちず、読めなかった扱いで続ける（1回だけなら行は出ない）。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    fault = (lambda n: exc if n == 2 else None)
    kwargs = {"read_fault": fault} if which == "read_state" else {"open_fault": fault}
    res = drive(work, out, timeout=8.0, **kwargs)
    assert res.events == ["snapshot", "timeout"] and res.code == 124
    assert res.errtext == "" and res.reads == 5


@pytest.mark.parametrize("which", ["read_state", "read_open_at"])
def test_d0031_ac39_three_exceptions_in_a_row_emit_the_empty_snapshot(tmp_path, which):
    """D0031-AC-39: 予期しない例外が3回続けば、「記録なし」の行を1つだけ出す（読めなかった扱いと同じ）。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    fault = (lambda n: RuntimeError("boom") if n in (2, 3, 4, 5) else None)
    kwargs = {"read_fault": fault} if which == "read_state" else {"open_fault": fault}
    res = drive(work, out, timeout=12.0, **kwargs)
    assert [(x["event"], x["empty"]) for x in res.lines] == [("snapshot", False), ("snapshot", True), ("snapshot", False), ("timeout", False)]
    assert res.out.times[:3] == pytest.approx([0.0, 6.0, 10.0])


@pytest.mark.parametrize("which", ["read_state", "read_open_at"])
@pytest.mark.parametrize("exc,code,message", [(KeyboardInterrupt(), 130, "中断"), (live_watch.Terminated(), 143, "終了の合図")], ids=["keyboardinterrupt", "terminated"])
def test_d0031_ac39_keyboardinterrupt_and_terminated_are_not_swallowed(tmp_path, which, exc, code, message):
    """D0031-AC-39: KeyboardInterrupt・Terminated は「読めなかった」にせず通す（130・143で止まり、「記録なし」の行も出さない）。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    fault = (lambda n: exc if n >= 2 else None)
    kwargs = {"read_fault": fault} if which == "read_state" else {"open_fault": fault}
    res = drive(work, out, timeout=100.0, **kwargs)
    assert res.code == code and res.events == ["snapshot"]
    assert message in res.errtext and "Traceback" not in res.errtext


# ---- AC-40・41 時計 ----------------------------------------------------------------------------------------------------


CLOCK_CASES = {
    "back_big_once": (lambda n, s: -100.0 if n == 3 else s, 6),
    "back_at_first": (lambda n, s: -50.0 if n == 1 else s, 6),
    "back_tiny": (lambda n, s: -0.25 if n == 2 else s, 6),
    "alternating": (lambda n, s: s if n % 2 == 1 else -1.0, 9),
    "back_then_big_forward": (lambda n, s: -1000.0 if n == 2 else (1010.0 if n == 3 else s), 3),
}


@pytest.mark.parametrize("name", sorted(CLOCK_CASES))
def test_d0031_ac40_clock_going_back_never_negative_or_early(tmp_path, name):
    """D0031-AC-40: 時計が前より小さい値を返しても、経過は負にならず、例外を出さず、上限を早めも延ばしもしない（戻った分は進んでいない扱い、戻ったあとの進みは数える）。"""
    advance, n_sleeps = CLOCK_CASES[name]
    res = drive(midway(tmp_path), out_path(tmp_path), interval=2.0, timeout=10.0, advance=advance)
    assert res.code == 124 and res.events == ["snapshot", "timeout"]
    assert len(res.time.sleeps) == n_sleeps and res.reads == n_sleeps + 1
    assert all(0 < s <= 2.0 for s in res.time.sleeps), "眠りは負にも interval 超にもならない"


def test_d0031_ac40_clock_back_then_ordinary_progress_reaches_the_limit(tmp_path):
    """D0031-AC-40: 戻ったあとに通常の進みが続けば、上限に達して timeout の行を出す。"""
    res = drive(midway(tmp_path), out_path(tmp_path), interval=1.0, timeout=5.0, advance=lambda n, s: -30.0 if n == 2 else s)
    assert res.lines[-1] == line("timeout", 1) and res.code == 124 and len(res.time.sleeps) == 6


JUMPS = {
    "jump_no_change": (lambda rec: None, ["snapshot", "timeout"]),
    "jump_one_change": (lambda rec: rec.done("design", "設計した"), ["snapshot", "snapshot", "timeout"]),
    "jump_two_changes": (lambda rec: (rec.done("design", "設計した"), rec.begin("red")), ["snapshot", "snapshot", "timeout"]),
    "jump_with_final": (lambda rec: (rec.done("design", "設計した"), rec.finish("PASSED")), ["snapshot", "final"]),
}


@pytest.mark.parametrize("name", sorted(JUMPS))
def test_d0031_ac41_clock_jump_one_read_at_most_one_line(tmp_path, name):
    """D0031-AC-41: 時計が大きく飛んでも、1回の周期で読みは1回、行は多くても1つ。上限を越えていれば、その周期で timeout（先に final）。"""
    work = midway(tmp_path)
    rec = Rec(tmp_path, datetime(2026, 10, 17, 11, 0, 0))
    change, events = JUMPS[name]
    res = drive(work, out_path(tmp_path), interval=2.0, timeout=100.0,
                advance=lambda n, s: 10000.0 if n == 2 else s, steps={2: lambda: change(rec)})
    assert res.events == events
    assert res.reads == 3 and len(res.time.sleeps) == 2
    assert res.code == (0 if events[-1] == "final" else 124)


def test_d0031_ac41_clock_jump_on_the_first_sleep(tmp_path):
    """D0031-AC-41: 最初の眠りで飛んでも、読みは2回（最初と飛んだあと）で、timeout の行は1つ。"""
    res = drive(midway(tmp_path), out_path(tmp_path), interval=2.0, timeout=100.0, advance=lambda n, s: 1e9)
    assert res.events == ["snapshot", "timeout"] and res.reads == 2 and res.code == 124


# ---- AC-43・45・46 止め方 ---------------------------------------------------------------------------------------------


STOPS = [(KeyboardInterrupt, 130, "pipe-in live watch: 中断しました\n"), (live_watch.Terminated, 143, "pipe-in live watch: 終了の合図を受けました\n")]


@pytest.mark.parametrize("exc_type,code,message", STOPS, ids=["keyboardinterrupt", "terminated"])
@pytest.mark.parametrize("where", ["sleep", "read", "write", "replace", "fsync"])
def test_d0031_ac43_keyboardinterrupt_in_sleep_read_write_exit130(tmp_path, monkeypatch, where, exc_type, code, message):
    """D0031-AC-43: 眠り・読み・書き（置き換え・fsync を含む）のどこで KeyboardInterrupt・Terminated が来ても、130・143、短い文、一時ファイルなし、書いた --out は完全な写し、標準出力に行を足さない。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    rec.begin("requirements")
    out = out_path(tmp_path)
    first = expected_bytes(rec.work, NOW)
    steps = {1: lambda: rec.done("requirements", "書いた")}
    kwargs = {}
    if where == "sleep":
        kwargs["sleep_hook"] = lambda n: (_ for _ in ()).throw(exc_type())
    elif where == "read":
        kwargs["read_fault"] = lambda n: exc_type() if n == 2 else None
    elif where == "write":
        kwargs["write_fault"] = lambda n: exc_type() if n == 2 else None
    else:
        real = getattr(os, where)
        calls = []

        def faulty(*a, **k):
            calls.append(1)
            if len(calls) == 2:
                raise exc_type()
            return real(*a, **k)

        monkeypatch.setattr(os, where, faulty)
    res = drive(rec.work, out, steps=steps, timeout=100.0, **kwargs)
    assert res.code == code
    assert res.errtext == message
    assert "Traceback" not in res.errtext
    assert res.events == ["snapshot"], "標準出力に行を足さない"
    assert out.read_bytes() == first
    assert listing(out.parent) == [out.name]


def test_d0031_ac43_interrupt_before_the_first_write_leaves_nothing(tmp_path):
    """D0031-AC-43: 最初の書き込みの最中に止められても、--out も一時ファイルも残らず、行も出ない。"""
    out = out_path(tmp_path)
    res = drive(midway(tmp_path), out, timeout=10.0, write_fault=lambda n: KeyboardInterrupt())
    assert res.code == 130 and res.lines == [] and listing(out.parent) == []


def test_d0031_ac43_terminated_is_a_base_exception_not_exception():
    """D0031-AC-43: Terminated は BaseException で、Exception ではない（except Exception に飲まれない）。今のままで通る。"""
    assert issubclass(live_watch.Terminated, BaseException) and not issubclass(live_watch.Terminated, Exception)


def test_d0031_ac44_install_sigterm_raises_terminated_and_restores():
    """D0031-AC-44: install_sigterm は SIGTERM の取り扱いを取り付け、受けると Terminated を投げる。戻り値の関数で元に戻る。"""
    if not hasattr(signal, "SIGTERM"):
        pytest.skip("SIGTERM が無い環境")
    original = signal.getsignal(signal.SIGTERM)
    restore = live_watch.install_sigterm()
    try:
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler) and handler != original
        with pytest.raises(live_watch.Terminated):
            handler(signal.SIGTERM, None)
        restore()
        assert signal.getsignal(signal.SIGTERM) == original
    finally:
        if original is not None:
            signal.signal(signal.SIGTERM, original)


def test_d0031_ac44_install_sigterm_off_the_main_thread_does_nothing():
    """D0031-AC-44: 主スレッドでないところでは、取り付けに失敗しても落ちず、何もしない（戻り値は呼べる）。空の形でも通る（守り続ける検査）。"""
    result = {}

    def run():
        try:
            restore = live_watch.install_sigterm()
            result["callable"] = callable(restore)
            restore()
        except BaseException as e:  # noqa: BLE001
            result["error"] = repr(e)

    th = threading.Thread(target=run)
    th.start()
    th.join(10)
    assert result == {"callable": True}


@pytest.mark.parametrize("where,write_at,fail_at", [("write_first", 1, None), ("write_second", 2, None), ("flush_first", None, 1), ("flush_second", None, 2)])
@pytest.mark.parametrize("exc", [BrokenPipeError(32, "Broken pipe"), ValueError("I/O operation on closed file.")], ids=["brokenpipe", "closedfile"])
def test_d0031_ac45_broken_pipe_exit1_no_tmp_no_traceback(tmp_path, where, write_at, fail_at, exc):
    """D0031-AC-45: 標準出力が閉じられている（BrokenPipeError・閉じたストリームの ValueError）と、落ちずに一時ファイルを残さず終了コード 1。標準エラーにトレースバックを出さない。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    rec.begin("requirements")
    out = out_path(tmp_path)
    so = FakeOut(write_error=(lambda n: exc if n == write_at else None), flush_error=(lambda n: exc if n == fail_at else None))
    res = drive(rec.work, out, steps={1: lambda: rec.done("requirements", "書いた")}, timeout=100.0, stdout=so)
    assert res.code == 1
    assert res.errtext == "pipe-in live watch: 標準出力が閉じられました\n"
    assert listing(out.parent) == [out.name]
    assert json.loads(out.read_bytes())["schema"] == 1, "書いた --out は完全な写しのまま"


def test_d0031_ac45_broken_pipe_on_the_timeout_line_exits1(tmp_path):
    """D0031-AC-45: timeout の行を出すときに閉じられていても、124 でなく 1 で止まる（落ちない）。"""
    res = drive(midway(tmp_path), out_path(tmp_path), timeout=4.0, stdout=FakeOut(write_error=lambda n: BrokenPipeError(32, "x") if n == 2 else None))
    assert res.code == 1 and "標準出力が閉じられました" in res.errtext and "Traceback" not in res.errtext


def test_d0031_ac45_broken_pipe_on_the_final_line_exits1(tmp_path):
    """D0031-AC-45: final の行を出すときに閉じられていると、0 でなく 1 で止まる。"""
    res = drive(finished_record(tmp_path / "p"), out_path(tmp_path), timeout=4.0, stdout=FakeOut(write_error=lambda n: BrokenPipeError(32, "x")))
    assert res.code == 1 and res.errtext.startswith("pipe-in live watch: 標準出力が閉じられました")


WRITE_ERRORS = [PermissionError(13, "Permission denied", "/" + "ho" + "me/alice/secret/out.json"), OSError(28, "No space left on device", "D:/private/out.json"), IsADirectoryError(21, "Is a directory")]


@pytest.mark.parametrize("exc", WRITE_ERRORS, ids=lambda e: type(e).__name__)
def test_d0031_ac46_write_failures_retry_then_exit1(tmp_path, exc):
    """D0031-AC-46: --out に連続して書けない（OSError）と、行は出さず、周期ごとにやり直し、3回で標準エラーに種類だけの文（パス・strerror を含まない）を出して終了コード 1。"""
    work, out = midway(tmp_path), out_path(tmp_path)
    res = drive(work, out, timeout=100.0, write_fault=lambda n: exc)
    assert res.code == 1 and res.lines == []
    assert (res.write_attempts, res.reads, len(res.time.sleeps)) == (3, 3, 2)
    assert res.errtext == f"pipe-in live watch: --out に書けませんでした（{type(exc).__name__}）\n"
    for leak in ("/home", "alice", "D:/", "private", "Permission denied", "No space", "Is a directory", str(out)):
        assert leak not in res.errtext


@pytest.mark.parametrize("fails", [1, 2])
def test_d0031_ac46_success_after_failures_emits_on_that_tick(tmp_path, fails):
    """D0031-AC-46: 途中で1回成功すれば続く。成功した回に行が出る（seq は 1 から抜け番なし）。失敗した回には行も seq も進まない。"""
    res = drive(midway(tmp_path), out_path(tmp_path), timeout=12.0, write_fault=lambda n: PermissionError(13, "x") if n <= fails else None)
    assert res.lines[0] == line("snapshot", 1)
    assert res.out.times[0] == pytest.approx(2.0 * fails)
    assert res.events == ["snapshot", "timeout"] and res.code == 124
    assert res.write_attempts == fails + 1


def test_d0031_ac46_write_failure_count_resets_on_success(tmp_path):
    """D0031-AC-46: 成功したら数え直す（失敗 失敗 成功 失敗 失敗 成功 …と続いても止まらない。数えるのは「連続」した失敗だけ）。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    pattern = "FFTFFT"
    steps = {3: lambda: rec.begin("requirements"), 6: lambda: rec.done("requirements", "書いた")}
    res = drive(rec.work, out_path(tmp_path), steps=steps, timeout=40.0,
                write_fault=lambda n: PermissionError(13, "x") if n <= len(pattern) and pattern[n - 1] == "F" else None)
    assert res.code == 124
    assert res.events == ["snapshot", "snapshot", "snapshot", "timeout"] and res.seqs == [1, 2, 3, 3]
    assert res.out.times[:3] == pytest.approx([4.0, 10.0, 12.0])
    assert res.write_attempts == 7 and res.write_ok == 3


def test_d0031_ac46_three_failures_after_a_success_exit1_and_keep_the_last_out(tmp_path):
    """D0031-AC-46: 1つ出せたあとに3回連続で書けなければ止まる（1）。出した行と --out は最初のまま。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    rec.begin("requirements")
    out = out_path(tmp_path)
    first = expected_bytes(rec.work, NOW)
    res = drive(rec.work, out, steps={1: lambda: rec.done("requirements", "書いた")}, timeout=100.0,
                write_fault=lambda n: PermissionError(13, "x") if n >= 2 else None)
    assert res.code == 1 and res.events == ["snapshot"]
    assert out.read_bytes() == first
    assert res.write_attempts == 4 and res.reads == 4


def test_d0031_ac46_retry_writes_the_latest_snapshot(tmp_path):
    """D0031-AC-46: 書けなかった回のあとに記録が替わったら、やり直しでは最新の写しを書く。"""
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    rec.begin("requirements")
    out = out_path(tmp_path)
    res = drive(rec.work, out, steps={1: lambda: rec.done("requirements", "書いた")}, timeout=10.0,
                write_fault=lambda n: PermissionError(13, "x") if n == 1 else None)
    assert res.lines[0] == line("snapshot", 1) and res.out.times[0] == pytest.approx(2.0)
    assert out.read_bytes() == expected_bytes(rec.work, NOW + timedelta(seconds=2))


def test_d0031_ac46_real_write_failure_on_a_folder_out(tmp_path):
    """D0031-AC-46: --out が既存のフォルダ（本物の OSError）でも、3回で種類だけの文を出して 1 で止まり、一時ファイルを残さない。"""
    work = midway(tmp_path)
    folder = tmp_path / "out" / "isafolder"
    folder.mkdir(parents=True)
    res = drive(work, folder, timeout=100.0)
    assert res.code == 1 and res.lines == []
    assert res.errtext.startswith("pipe-in live watch: --out に書けませんでした（") and res.errtext.count("\n") == 1
    assert str(folder) not in res.errtext and "Is a directory" not in res.errtext
    assert listing(folder.parent) == ["isafolder"] and listing(folder) == []


# ---- AC-47・48・49・55 読むだけ・変えないもの --------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["running", "finished", "with_archive"])
def test_d0031_ac47_record_files_and_dir_listing_unchanged(tmp_path, kind):
    """D0031-AC-47: 見張りの前後で、state.json・logs/・99_summary.md のバイト列と更新時刻、読み先の中のファイルの一覧が同じ。--out と一時ファイル以外は何も作られない。"""
    if kind == "running":
        work = midway(tmp_path)
    else:
        work = finished_record(tmp_path / "p")
    if kind == "with_archive":
        rec = Rec(tmp_path / "p", datetime(2026, 10, 17, 12, 0, 0))
        rec.start("次", name="次")
        rec.begin("requirements")
    out = out_path(tmp_path)
    before = tree(work)
    res = drive(work, out, timeout=10.0)
    assert res.lines and out.is_file(), "見張りが動いている"
    assert tree(work) == before
    assert listing(out.parent) == [out.name]


def test_d0031_ac47_nothing_is_created_for_a_missing_work_dir(tmp_path):
    """D0031-AC-47: 読み先のフォルダが無くても、フォルダを作らない。"""
    work = tmp_path / "no" / "such"
    res = drive(work, out_path(tmp_path), timeout=4.0)
    assert res.lines[0]["empty"] is True and not (tmp_path / "no").exists()


def test_d0031_ac48_no_subprocess_or_sdk_in_source_and_at_runtime(tmp_path, monkeypatch):
    """D0031-AC-48: 見張りの経路で SDK が呼ばれず、子プロセスも起こされない（ソースの import と、偽に差し替えた実行の両方）。"""
    source = (ROOT / "pipe_in" / "engine" / "live_watch.py").read_text(encoding="utf-8")
    tree_ = ast.parse(source)
    imported = set()
    for node in ast.walk(tree_):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0] if not node.level else "." * node.level + (node.module or ""))
    assert not imported & {"subprocess", "claude_agent_sdk", "anyio", "mcp", "multiprocessing", "asyncio", "socket", "urllib", "http"}
    for call in ("os.system", "os.popen", "os.spawnl", "os.execv", "os.fork", "Popen"):
        assert call not in source, call

    def boom(*a, **k):
        raise AssertionError("子プロセスを起こそうとした")

    for target in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, target, boom)
    monkeypatch.setattr(os, "system", boom)
    monkeypatch.setattr(os, "popen", boom)
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    res = drive(rec.work, out_path(tmp_path), steps={1: lambda: rec.begin("requirements")}, timeout=6.0)
    assert res.events == ["snapshot", "snapshot", "timeout"]


PROBE = """
import io, sys
sys.path.insert(0, {root!r})
from pipe_in.engine import live_watch
t = [0.0]
def clock(): return t[0]
def sleep(s): t[0] += s
buf = io.StringIO()
rc = live_watch.watch({work!r}, {out!r}, interval=2.0, timeout=4.0, clock=clock, sleep=sleep, stdout=buf, stderr=io.StringIO())
mods = sorted(m for m in sys.modules if m.split('.')[0] in ('claude_agent_sdk', 'anyio', 'mcp', 'subprocess_sdk'))
print(repr((rc, buf.getvalue(), mods)))
"""


def test_d0031_ac48_watch_in_a_fresh_interpreter_does_not_import_the_sdk(tmp_path, monkeypatch):
    """D0031-AC-48: 新しい Python で live_watch を読み込んで見張りを流しても、claude_agent_sdk（とそれが引き込むもの）が増えない。"""
    monkeypatch.setattr(time, "sleep", REAL_SLEEP)
    work = midway(tmp_path)
    out = out_path(tmp_path)
    proc = subprocess.run([sys.executable, "-I", "-c", PROBE.format(root=str(ROOT), work=str(work), out=str(out))], capture_output=True, cwd=tmp_path, timeout=120)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    rc, text, mods = eval(proc.stdout.decode("utf-8").strip().splitlines()[-1])
    assert mods == []
    assert rc == 124
    assert [json.loads(x)["event"] for x in text.splitlines()] == ["snapshot", "timeout"]


def test_d0031_ac49_snapshot_and_schema_are_unchanged_by_watch(tmp_path):
    """D0031-AC-49: 写しの SCHEMA は 1 のまま、項目の一覧と順も変わらない。watch が書く写しは live snapshot と同じ形（今のままで通る部分を含む守りの検査）。"""
    assert live.SCHEMA == 1
    work, out = midway(tmp_path), out_path(tmp_path)
    res = drive(work, out, timeout=2.0)
    assert res.lines, "見張りが動いている"
    snap = json.loads(out.read_bytes())
    assert list(snap) == ls.KEYS and snap["schema"] == 1
    assert all(list(s) == ls.STAGE_KEYS for s in snap["stages"])


@pytest.mark.parametrize("kind", ["old_state", "pipe_record"])
def test_d0031_ac55_old_format_and_pipe_records_are_watched(tmp_path, kind):
    """D0031-AC-55: 古い形の記録（D0017 より前：since・at・name・session_id が無い）やパイプの state.json を読み先に渡しても、見張りが始まり、1つ目の行が出る。"""
    work, out = tmp_path / "w", out_path(tmp_path)
    if kind == "old_state":
        state = ls.base_state(open=None, pending_review={"stage": "design", "doc": "docs/pipeline/design.md", "session_id": None})
        state.pop("name")
        state["runs"] = [ls.run("requirements", seq=1)]
        ls.write_state(work, state)
    else:
        stages = [ls.stage_entry("collect", "集める"), ls.stage_entry("draw", "描く")]
        ls.write_state(work, ls.base_state(pipe="diagram", name="図のパイプ", stages=stages, runs=[ls.run("collect", seq=1)], open=ls.opened("draw", seq=2)))
        ls.write_log(work, "02_draw.jsonl", [{"_type": "Prompt", "stage": "draw", "prompt": "p"}])  # at の無い古い形
    res = drive(work, out, timeout=4.0)
    assert res.lines[0] == line("snapshot", 1) and res.code == 124
    snap = json.loads(out.read_bytes())
    assert snap["empty"] is False
    if kind == "old_state":
        assert snap["name"] is None and snap["stages"][1]["pending_since"] is None
    else:
        assert snap["name"] == "図のパイプ" and snap["stages"][1]["status"] == "running" and snap["stages"][1]["started_at"] is None


def test_d0031_ac55_archive_dir_as_work_dir_is_static_and_stops_at_final(tmp_path):
    """D0031-AC-55: archive/<日時>/ を読み先にすると静的な記録として扱われ、final があれば1回で止まる。archive の中は何も変わらない。"""
    work = finished_record(tmp_path / "p")
    rec = Rec(tmp_path / "p", datetime(2026, 10, 17, 12, 0, 0))
    rec.start("次", name="次")
    archived = sorted((work / "archive").iterdir())
    assert len(archived) == 1
    before = tree(archived[0])
    out = out_path(tmp_path)
    res = drive(archived[0], out, timeout=100.0)
    assert res.lines == [line("final", 1, "PASSED")] and res.code == 0 and res.reads == 1
    assert tree(archived[0]) == before
    assert json.loads(out.read_bytes())["name"] == "終わった実行"


# ---- D0040 Windows でも、標準出力が閉じた・書けないときは静かに 1 で止まる ------------------------------------------------------

CLOSED_TEXT = "pipe-in live watch: 標準出力が閉じられました\n"
COULD_NOT_WRITE_TEXT = "pipe-in live watch: 標準出力に書けませんでした（OSError）\n"


def einval() -> OSError:
    """Windows で、読み手のいないパイプへの書き込みが出す例外と同じ形。"""
    return OSError(errno.EINVAL, "Invalid argument")


def plain_oserror(code: int, text: str = "x") -> OSError:
    """errno を持つ素の OSError（OSError(errno.EPIPE, …) は BrokenPipeError に替わって作られるので、あとから errno を入れる）。"""
    e = OSError(text)
    e.errno = code
    return e


def started_record(tmp_path: Path) -> Rec:
    rec = Rec(tmp_path / "p")
    rec.start("メモ")
    rec.begin("requirements")
    return rec


@pytest.mark.parametrize("fail_at", [1, 2], ids=["first_line", "second_line"])
def test_d0040_ac01_einval_on_flush_exits1_quietly(tmp_path, fail_at):
    """D0040-AC-01: flush が OSError(EINVAL)（Windows の閉じたパイプ）を出すと、1つ目・2つ目の行のどちらでも、落ちずに終了コード 1。標準エラーは閉じた文の1行だけで、一時ファイルは残らず、--out は完全な写し。"""
    rec = started_record(tmp_path)
    out = out_path(tmp_path)
    so = FakeOut(flush_error=lambda n: einval() if n == fail_at else None)
    res = drive(rec.work, out, steps={1: lambda: rec.done("requirements", "書いた")}, timeout=100.0, stdout=so)
    assert res.code == 1
    assert res.errtext == CLOSED_TEXT
    assert "Traceback" not in res.errtext
    assert listing(out.parent) == [out.name]
    assert json.loads(out.read_bytes())["schema"] == 1, "書いた --out は完全な写しのまま"


@pytest.mark.parametrize("write_at", [1, 2], ids=["first_line", "second_line"])
def test_d0040_ac02_einval_on_write_exits1_quietly(tmp_path, write_at):
    """D0040-AC-02: write が OSError(EINVAL) を出しても、AC-01 と同じく終了コード 1・閉じた文の1行だけ・一時ファイルなし・--out は完全な写し。"""
    rec = started_record(tmp_path)
    out = out_path(tmp_path)
    so = FakeOut(write_error=lambda n: einval() if n == write_at else None)
    res = drive(rec.work, out, steps={1: lambda: rec.done("requirements", "書いた")}, timeout=100.0, stdout=so)
    assert res.code == 1
    assert res.errtext == CLOSED_TEXT
    assert "Traceback" not in res.errtext
    assert listing(out.parent) == [out.name]
    assert json.loads(out.read_bytes())["schema"] == 1, "書いた --out は完全な写しのまま"


def test_d0040_ac03_einval_on_the_timeout_line_exits1(tmp_path):
    """D0040-AC-03: timeout の行を出すときに flush が EINVAL を出すと、124 でなく 1。標準エラーは閉じた文の1行だけ。"""
    so = FakeOut(flush_error=lambda n: einval() if n == 2 else None)
    res = drive(midway(tmp_path), out_path(tmp_path), timeout=4.0, stdout=so)
    assert res.code == 1
    assert res.errtext == CLOSED_TEXT


def test_d0040_ac03_einval_on_the_final_line_exits1(tmp_path):
    """D0040-AC-03: final の行を出すときに flush が EINVAL を出すと、0 でなく 1。標準エラーは閉じた文の1行だけ。"""
    so = FakeOut(flush_error=lambda n: einval())
    res = drive(finished_record(tmp_path / "p"), out_path(tmp_path), timeout=4.0, stdout=so)
    assert res.code == 1
    assert res.errtext == CLOSED_TEXT


OTHER_OSERRORS = [
    OSError(errno.ENOSPC, "No space left on device", "D:/private/out.json"),
    OSError(errno.EIO, "SECRET-io"),
    OSError("SECRET-plain"),
]


@pytest.mark.parametrize("exc", OTHER_OSERRORS, ids=["enospc", "eio", "noerrno"])
def test_d0040_ac04_other_oserror_says_could_not_write(tmp_path, exc):
    """D0040-AC-04: 閉じた以外の OSError（ENOSPC・EIO・errno なし）を flush で出すと、終了コード 1。標準エラーは「標準出力に書けませんでした（OSError）」の1行で、例外の文・パスを含まない。一時ファイルは残らない。"""
    out = out_path(tmp_path)
    assert type(exc) is OSError, "素の OSError で確かめる"
    res = drive(midway(tmp_path), out, timeout=100.0, stdout=FakeOut(flush_error=lambda n: exc if n == 1 else None))
    assert res.code == 1
    assert res.errtext == COULD_NOT_WRITE_TEXT
    for leak in ("SECRET", "No space", "D:/", "private", "Traceback"):
        assert leak not in res.errtext
    assert listing(out.parent) == [out.name]


STDOUT_FAILURES = [
    (einval(), "標準出力が閉じられました"),
    (OSError(errno.ENOSPC, "No space left on device", "D:/private/out.json"), "標準出力に書けませんでした（OSError）"),
    (OSError(errno.EIO, "SECRET-io"), "標準出力に書けませんでした（OSError）"),
    (OSError("SECRET-plain"), "標準出力に書けませんでした（OSError）"),
    (OSError(errno.EPIPE, "Broken pipe"), "標準出力が閉じられました"),
    (plain_oserror(errno.EPIPE), "標準出力が閉じられました"),
    (plain_oserror(errno.EINVAL), "標準出力が閉じられました"),
    (BrokenPipeError(), "標準出力が閉じられました"),
    (ValueError("I/O operation on closed file."), "標準出力が閉じられました"),
    (ConnectionResetError(errno.ECONNRESET, "x"), "標準出力に書けませんでした（ConnectionResetError）"),
]


@pytest.mark.parametrize("exc,text", STDOUT_FAILURES,
                         ids=["einval", "enospc", "eio", "noerrno", "epipe_built", "epipe_plain", "einval_plain", "brokenpipe_noerrno", "closedfile", "connreset"])
def test_d0040_ac04_stdout_failure_text_by_error(exc, text):
    """D0040-AC-04: 標準出力の失敗から標準エラーの文を決める純粋な関数。閉じた（BrokenPipeError・EPIPE・EINVAL・ValueError）は閉じた文、そのほかは型の名前だけの「書けませんでした」。"""
    assert live_watch._stdout_failure_text(exc) == text


@pytest.mark.parametrize("how", ["built", "plain"])
def test_d0040_ac05_plain_oserror_with_epipe_is_closed(tmp_path, how):
    """D0040-AC-05: errno が EPIPE の OSError は閉じた扱い（BrokenPipeError と同じ）。OSError(EPIPE, …) は BrokenPipeError として作られ、errno をあとから入れた素の OSError でも閉じた文になる。"""
    if how == "built":
        exc = OSError(errno.EPIPE, "Broken pipe")
        assert type(exc) is BrokenPipeError, "Python は OSError(EPIPE, …) を BrokenPipeError に替えて作る"
    else:
        exc = plain_oserror(errno.EPIPE, "Broken pipe")
        assert type(exc) is OSError and exc.errno == errno.EPIPE
    out = out_path(tmp_path)
    res = drive(midway(tmp_path), out, timeout=100.0, stdout=FakeOut(flush_error=lambda n: exc if n == 1 else None))
    assert res.code == 1
    assert res.errtext == CLOSED_TEXT
    assert listing(out.parent) == [out.name]


@pytest.mark.parametrize("exc,code,message",
                         [(KeyboardInterrupt(), 130, "pipe-in live watch: 中断しました\n"),
                          (live_watch.Terminated(), 143, "pipe-in live watch: 終了の合図を受けました\n")],
                         ids=["keyboardinterrupt", "terminated"])
def test_d0040_ac06_interrupts_on_stdout_flush_are_not_swallowed(tmp_path, exc, code, message):
    """D0040-AC-06: 標準出力の flush の最中に KeyboardInterrupt・Terminated が来ると、1 でなく 130・143。標準出力の失敗の捕まえ方が止める合図を飲み込まない（今のままで通る。守り続ける検査）。"""
    res = drive(midway(tmp_path), out_path(tmp_path), timeout=100.0, stdout=FakeOut(flush_error=lambda n: exc if n == 1 else None))
    assert res.code == code
    assert res.errtext == message


def test_d0040_ac07_einval_on_out_write_is_not_stdout_closed(tmp_path):
    """D0040-AC-07: --out への書き込みが OSError(EINVAL) を出すときは、標準出力が閉じた扱いにならない。行を出さずにやり直し、3回で「--out に書けませんでした（OSError）」で 1（今のままで通る。守り続ける検査）。"""
    res = drive(midway(tmp_path), out_path(tmp_path), timeout=100.0, write_fault=lambda n: einval())
    assert res.code == 1 and res.lines == []
    assert res.write_attempts == 3
    assert res.errtext == "pipe-in live watch: --out に書けませんでした（OSError）\n"
    assert "標準出力" not in res.errtext
