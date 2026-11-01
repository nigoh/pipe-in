"""D0027：進み具合のページの JS の動き。Node 22 以上があるときだけ、build_page() の本物の JS を node:vm で動かして確かめる。

台は tests/fixtures/live_page_harness.mjs（偽の document・仮想の時計とタイマー・偽の claude.use("db")）。
db の口は公式の型定義で確かめた形：const db = await claude.use("db")（使えない画面では null）・db.doc("runs/current")・
ref.onSnapshot(next, error?)（購読をやめる関数を返す）・snap.exists（boolean）・snap.data()（本文か undefined）。ページはまだ書き込まない。

Node が無い環境では全部 skip する（skip は成功に見えるので、検証では pytest -rs で skip が 0 件なのを見る）。
先頭の「台の自己検査」は、台そのものが動くこと（ページの出来に関係なく通る）を確かめる。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import live_support as ls
from pipe_in.engine import live, live_page

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "fixtures" / "live_page_harness.mjs"
UTC = timezone.utc
T0 = datetime(2026, 10, 17, 2, 0, 0, tzinfo=UTC)
NAN = {"$": "NaN"}
INF = {"$": "Infinity"}
NINF = {"$": "-Infinity"}
GOOD_MARK = "SESSION-NAME-MARK"
EMPTY_MSG = "まだ記録がありません"
UNREADABLE_MSG = "この画面では読めません"
UNSUPPORTED_MSG = "この写しの版には対応していません"


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node 22 以上が無い（node が見つからない）")
    out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    match = re.match(r"v(\d+)\.", out)
    if not match or int(match.group(1)) < 22:
        pytest.skip(f"Node 22 以上が無い（{out or '不明'}）")
    return node


@pytest.fixture(scope="module")
def node() -> str:
    return _node()


@pytest.fixture(scope="module")
def html() -> str:
    page = live_page.build_page()
    assert isinstance(page, str) and page.strip(), "build_page() が空（ページをまだ作っていない）"
    return page


def iso(seconds_ago: float) -> str:
    return (T0 - timedelta(seconds=seconds_ago)).isoformat(timespec="seconds")


def ms(text: str) -> int:
    return int(datetime.fromisoformat(text).timestamp() * 1000)


def run_scene(node_path: str, page_html: str, **scene) -> dict:
    scene["html"] = page_html
    # D0059：時刻帯の指定は、台の中の代入（process.env.TZ）と子プロセスの環境の両方に入れる（どちらかが効けばよい）
    env = {**os.environ, "TZ": scene["tz"]} if "tz" in scene else None
    proc = subprocess.run(
        [node_path, str(HARNESS)], input=json.dumps(scene).encode("utf-8"), capture_output=True, timeout=120, cwd=str(ROOT), env=env,
    )
    try:
        result = json.loads(proc.stdout.decode("utf-8"))
    except ValueError:
        pytest.fail(f"台の出力が JSON でない: {proc.stdout[:500]!r} / stderr={proc.stderr[:2000]!r}")
    if "harness_error" in result:
        pytest.fail(f"台の誤り: {result['harness_error']}\n{result.get('stack')}")
    return result


def stage(name: str, status: str = "waiting", **kw) -> dict:
    d = {"name": name, "label": f"LABEL-{name}", "status": status, "attempt": None, "started_at": None, "pending_since": None,
         "verdict": None, "cost_usd": None, "turns": None, "duration_sec": None}
    d.update(kw)
    return d


def snapshot(stages: list, **top) -> dict:
    s = {"schema": 1, "generated_at": T0.isoformat(timespec="seconds"), "empty": False, "name": GOOD_MARK, "final": None, "stages": stages}
    s.update(top)
    return s


def counting_snapshot(started: float = 83, pending: float = 40) -> dict:
    """動いている段（started 秒前から）と確認待ちの段（pending 秒前から）がある写し。"""
    return snapshot([
        stage("requirements", "done", attempt=1, cost_usd=0.5, turns=3, duration_sec=12.5),
        stage("design", "running", attempt=2, started_at=iso(started)),
        stage("red", "review", pending_since=iso(pending)),
        stage("implement"),
        stage("test"),
    ])


def done_snapshot() -> dict:
    return snapshot([stage(n, "done") for n in ("requirements", "design", "red")], final="PASSED")


def shows(text: str, shown: str) -> bool:
    return re.search(r"(?<![\d:.])%s(?![\d:])" % re.escape(shown), text) is not None


def sending(*values) -> list[dict]:
    return [{"op": "send", "value": v} for v in values]


# ---- 台の自己検査（ページの出来に関係なく通る） ------------------------------------------------------------

REFERENCE_PAGE = """<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>t</title></head><body>
<p id="msg"></p><ul id="list" class="a b"><li>first</li></ul><div data-x="1"><span class="k">in</span></div>
<script>
function bump(x) { return x + 1; }
function boom() { throw new Error("kaboom"); }
function same(x) { return x; }
let timer = null; let n = 0;
async function main() {
  const db = await claude.use("db");
  if (!db) { document.getElementById("msg").textContent = "none"; return; }
  db.doc("runs/current").onSnapshot(function (snap) {
    const v = snap.exists ? snap.data() : null;
    document.getElementById("msg").textContent = JSON.stringify(v);
    const li = document.createElement("li"); li.textContent = "x"; document.getElementById("list").appendChild(li);
    if (timer === null) { timer = setInterval(function () { n++; document.getElementById("msg").textContent = "tick " + n + " " + new Date(Date.now()).toISOString(); }, 1000); }
  }, function (e) { document.getElementById("msg").textContent = "err"; });
  document.addEventListener("visibilitychange", function () { if (document.hidden) { clearInterval(timer); timer = null; } });
}
main();
</script></body></html>"""

HOSTILE_PAGE = """<!doctype html><html><body><div id="d"></div><script>
async function main() { const db = await claude.use("db"); db.doc("runs/current").onSnapshot(function (s) { document.getElementById("d").innerHTML = "<b>x</b>"; }); }
main();
</script></body></html>"""


def test_d0027_harness_runs_a_reference_page(node):
    """D0027-AC-50: 台の自己検査。ページの JS が動き、db の購読・タイマー・表示・関数の呼び出しが台で確かめられる。"""
    r = run_scene(node, REFERENCE_PAGE, steps=[
        {"op": "send", "value": {"a": 1}},
        {"op": "advance", "ms": 3000},
        {"op": "hidden", "value": True},
        {"op": "call", "fn": "bump", "args": [41]},
        {"op": "call", "fn": "same", "args": [NAN]},
        {"op": "call", "fn": "same", "args": [{"a": [1, INF]}]},
        {"op": "call", "fn": "boom", "args": []},
        {"op": "call", "fn": "nope", "args": []},
        {"op": "query", "selector": "ul.a > li"},
        {"op": "query", "selector": "div[data-x='1'] .k, #msg"},
    ])
    assert r["load_error"] is None
    assert r["db"]["calls"] == [["doc", "runs/current"], ["onSnapshot", "runs/current"]]
    steps = r["steps"]
    assert '{"a":1}' in steps[0]["view"]["text"] and steps[0]["view"]["intervals"] == 1 and steps[0]["view"]["interval_ms"] == [1000]
    assert "tick 3 2026-10-17T02:00:03.000Z" in steps[1]["view"]["text"]
    assert steps[2]["view"]["intervals"] == 0 and steps[2]["view"]["hidden"] is True
    assert steps[3]["result"] == 42
    assert steps[4]["result"] == NAN
    assert steps[5]["result"] == {"a": [1, INF]}
    assert "kaboom" in steps[6]["threw"] and steps[7]["threw"]
    assert [x["text"] for x in steps[8]["result"]] == ["first", "x"]
    assert sorted(x["tag"] for x in steps[9]["result"]) == ["p", "span"]
    assert r["unhandled"] == [] and r["uncaught"] == [] and r["db"]["writes"] == []
    assert r["db"]["subscriptions"] == 1


def test_d0027_harness_reports_the_unreadable_modes(node):
    """D0027-AC-50: 台の自己検査。db が使えない場面（null・claude が無い・reject・throw）を作れる。"""
    for mode in ("null", "undefined", "use_rejects", "use_throws", "use_undefined"):
        r = run_scene(node, REFERENCE_PAGE, claude=mode)
        assert r["load_error"] is None
        assert r["db"]["subscriptions"] == 0, mode
    assert "none" in run_scene(node, REFERENCE_PAGE, claude="null")["loaded"]["lines"]
    assert any(u for u in run_scene(node, REFERENCE_PAGE, claude="use_rejects")["unhandled"]), "拒否された約束の記録"


def test_d0027_harness_catches_html_insertion(node):
    """D0027-AC-48: 台の自己検査。innerHTML に書くページは、台が数えて例外にする。"""
    r = run_scene(node, HOSTILE_PAGE, steps=[{"op": "send", "value": {}}])
    assert r["steps"][0]["view"]["html_insertions"] == 1
    assert r["steps"][0]["threw"] and "innerHTML" in r["steps"][0]["threw"]


def test_d0027_harness_initial_value_and_missing(node):
    """D0027-AC-50: 台の自己検査。購読の直後に届く値（initial）と、exists が false の届け方。"""
    r = run_scene(node, REFERENCE_PAGE, initial={"value": {"k": "v"}}, steps=[{"op": "send", "missing": True}])
    assert '{"k":"v"}' in r["loaded"]["text"] and r["steps"][0]["view"]["text"].startswith("null")


def test_d0027_harness_without_script_is_a_load_error(node):
    """D0027-AC-50: 台の自己検査。<script> の無い HTML は load_error になる（空のページが「通った」ことにならない）。"""
    assert run_scene(node, "<!doctype html><body><p>x</p></body>")["load_error"]
    assert run_scene(node, "")["load_error"]


# ---- ページの本物の JS ---------------------------------------------------------------------------------


def go(node, html, steps=None, **opts):
    r = run_scene(node, html, steps=steps or [], **opts)
    assert r["load_error"] is None, r["load_error"]
    assert r["uncaught"] == [] and r["unhandled"] == [], (r["uncaught"], r["unhandled"])
    return r


def call(node, html, fn, *args):
    r = run_scene(node, html, steps=[{"op": "call", "fn": fn, "args": list(args)}])
    assert r["load_error"] is None, r["load_error"]
    step = r["steps"][0]
    assert step["threw"] is None, f"{fn}({args}) が例外: {step['threw']}"
    return step["result"]


# ---- AC-56 経過 ------------------------------------------------------------------------------------------


def test_d0027_ac56_elapsed_for_running_and_for_review(node, html):
    """D0027-AC-56: 動いている段は「今 − started_at」、確認待ちは「今 − pending_since」で経過が出て、1秒ごとに増える。"""
    r = go(node, html, steps=[*sending(counting_snapshot(83, 40)), {"op": "advance", "ms": 1000}, {"op": "advance", "ms": 59000}])
    first, second, third = (s["view"]["text"] for s in r["steps"])
    assert shows(first, "1:23") and shows(first, "0:40")
    assert shows(second, "1:24") and shows(second, "0:41")
    assert shows(third, "2:23") and shows(third, "1:40")


def test_d0027_ac56_elapsed_uses_the_viewer_clock_not_generated_at(node, html):
    """D0027-AC-56: 写しが書かれた何分も後に開いても、経過は started_at からの本当の経過（generated_at を起点にしない）。"""
    snap = counting_snapshot(4567, 125)
    snap["generated_at"] = iso(3600)
    r = go(node, html, steps=sending(snap))
    text = r["steps"][0]["view"]["text"]
    assert shows(text, "1:16:07") and shows(text, "2:05")


def test_d0027_ac56_elapsed_is_counted_by_the_second_not_by_events(node, html):
    """D0027-AC-56: 1秒未満では増えず、1秒ごとに1ずつ増える（10秒進めて10増える）。"""
    r = go(node, html, steps=[*sending(counting_snapshot(10, 5)), {"op": "advance", "ms": 999}, {"op": "advance", "ms": 1}, {"op": "advance", "ms": 9000}])
    texts = [s["view"]["text"] for s in r["steps"]]
    assert shows(texts[0], "0:10") and shows(texts[1], "0:10") and shows(texts[2], "0:11") and shows(texts[3], "0:20")


def test_d0027_ac56_only_running_and_review_stages_count(node, html):
    """D0027-AC-56: 待ち・終わり・失敗・差し戻しの段は数えない（started_at が残っていても）。"""
    snap = snapshot([
        stage("a", "done", started_at=iso(83), pending_since=iso(40)), stage("b", "failed", started_at=iso(83)),
        stage("c", "revised", started_at=iso(83), pending_since=iso(40)), stage("d", "waiting", started_at=iso(83), pending_since=iso(40)),
    ])
    r = go(node, html, steps=sending(snap))
    view = r["steps"][0]["view"]
    assert view["intervals"] == 0
    assert not shows(view["text"], "1:23") and not shows(view["text"], "0:40")


def test_d0027_ac56_two_running_stages_both_count(node, html):
    """D0027-AC-56: 数える段が複数あっても、タイマーは1つで、全部が増える。"""
    snap = snapshot([stage("a", "running", started_at=iso(61)), stage("b", "review", pending_since=iso(7)), stage("c", "running", started_at=iso(3605))])
    r = go(node, html, steps=[*sending(snap), {"op": "advance", "ms": 2000}])
    assert r["steps"][0]["view"]["intervals"] == 1
    text = r["steps"][1]["view"]["text"]
    assert shows(text, "1:03") and shows(text, "0:09") and shows(text, "1:00:07")


# ---- AC-57 負にしない・時刻が無いとき --------------------------------------------------------------------


@pytest.mark.parametrize("ahead", [1, 59, 3600, 86400, 10**7], ids=lambda v: f"{v}s_ahead")
def test_d0027_ac57_elapsed_is_never_negative_for_future_times(node, html, ahead):
    """D0027-AC-57: 未来の時刻（閲覧側の時計が遅れている）でも、経過は 0:00 で、マイナスの文字が出ない。"""
    snap = snapshot([stage("a", "running", started_at=iso(-ahead)), stage("b", "review", pending_since=iso(-ahead))])
    r = go(node, html, steps=[*sending(snap), {"op": "advance", "ms": 1000}])
    for step in r["steps"]:
        text = step["view"]["text"]
        assert shows(text, "0:00"), text
        assert not re.search(r"-\s*\d", text), text
        assert "NaN" not in text and "undefined" not in text and "Infinity" not in text


def test_d0027_ac57_clock_going_back_does_not_go_negative(node, html):
    """D0027-AC-57: 時計が戻っても（始まりより前の時刻になっても）、経過は 0:00 のまま負にならない。"""
    r = go(node, html, steps=[*sending(counting_snapshot(83, 40)), {"op": "set_now", "at": iso(500)}, {"op": "advance", "ms": 1000}, {"op": "advance", "ms": 2000}])
    for step in r["steps"][2:]:
        text = step["view"]["text"]
        assert shows(text, "0:00") or shows(text, "0:01") or shows(text, "0:02") or shows(text, "0:03"), text
        assert not shows(text, "1:23") and not re.search(r"-\s*\d", text) and "NaN" not in text


def test_d0027_ac57_clock_going_back_a_little_keeps_counting_from_the_new_time(node, html):
    """D0027-AC-57: 時計が少し戻った後は、戻った時刻から改めて数える（古い時刻のまま固まらない）。"""
    r = go(node, html, steps=[*sending(counting_snapshot(83, 40)), {"op": "set_now", "at": (T0 - timedelta(seconds=30)).isoformat()}, {"op": "advance", "ms": 1000}])
    text = r["steps"][-1]["view"]["text"]
    assert shows(text, "0:54") and shows(text, "0:11")


@pytest.mark.parametrize(
    "bad",
    [None, "abc", "", " ", 123, 0, True, [], {}, ["2026-10-17T01:00:00+00:00"], "2026-10-17T10:00:00", "2026-10-17", "2026-13-45T25:61:61+00:00",
     "2026-10-17T01:00:00+00:00 extra", "x2026-10-17T01:00:00+00:00", "a" * 100000, NAN, INF],
    ids=lambda v: repr(v)[:30],
)
def test_d0027_ac57_null_or_broken_time_is_not_counted(node, html, bad):
    """D0027-AC-57: 時刻が null・壊れた文字・型違い・ずれなしのときは、数え上げない（タイマーも回さない）。例外も出さない。"""
    snap = snapshot([stage("a", "running", started_at=bad), stage("b", "review", pending_since=bad), stage("c", "waiting")])
    r = go(node, html, steps=[*sending(snap), {"op": "advance", "ms": 5000}])
    for step in r["steps"]:
        assert step["threw"] is None
        assert step["view"]["intervals"] == 0, "数える要素が無いのにタイマーが回っている"
        assert "NaN" not in step["view"]["text"] and "Infinity" not in step["view"]["text"] and "undefined" not in step["view"]["text"]
    assert "LABEL-a" in r["steps"][0]["view"]["text"]


def test_d0027_ac57_very_old_time_is_capped(node, html):
    """D0027-AC-57: 10 日以上前の時刻は 99:59:59 で頭打ちになる（桁があふれない）。"""
    snap = snapshot([stage("a", "running", started_at=iso(864000)), stage("b", "review", pending_since=iso(86400 * 400))])
    text = go(node, html, steps=sending(snap))["steps"][0]["view"]["text"]
    assert len(re.findall(r"99:59:59", text)) == 2


# ---- AC-58 書き方 ------------------------------------------------------------------------------------------

FORMATS = [
    (0, "0:00"), (1, "0:01"), (9, "0:09"), (10, "0:10"), (59, "0:59"), (60, "1:00"), (61, "1:01"), (599, "9:59"), (600, "10:00"), (3599, "59:59"),
    (3600, "1:00:00"), (3601, "1:00:01"), (3661, "1:01:01"), (36000, "10:00:00"), (86399, "23:59:59"), (86400, "24:00:00"), (359999, "99:59:59"),
]


@pytest.mark.parametrize("sec,expected", FORMATS, ids=[f"{s}s" for s, _ in FORMATS])
def test_d0027_ac58_format_boundaries(node, html, sec, expected):
    """D0027-AC-58: m:ss（1時間以上は h:mm:ss）の境目（0・59・60・599・600・3599・3600・巨大）。"""
    assert call(node, html, "fmtElapsed", sec) == expected


@pytest.mark.parametrize("bad", [NAN, -1, -0.5, -3600, NINF, None, "abc", "", [], {}, True], ids=lambda v: repr(v)[:20])
def test_d0027_ac58_format_of_non_numbers_and_negatives_is_zero(node, html, bad):
    """D0027-AC-58: 数でない・負の値は 0:00。"""
    assert call(node, html, "fmtElapsed", bad) == "0:00"


def test_d0027_ac58_format_ignores_fractions_by_flooring(node, html):
    """D0027-AC-58: 小数は切り捨てる（59.9 は 0:59）。"""
    assert call(node, html, "fmtElapsed", 59.9) == "0:59"
    assert call(node, html, "fmtElapsed", 60.2) == "1:00"


@pytest.mark.parametrize(
    "text,expected",
    [("2026-10-17T01:00:00+00:00", ms("2026-10-17T01:00:00+00:00")), ("2026-10-17T01:00:00Z", ms("2026-10-17T01:00:00+00:00")),
     ("2026-10-17T10:00:00+09:00", ms("2026-10-17T01:00:00+00:00")), ("2026-10-16T20:00:00-05:00", ms("2026-10-17T01:00:00+00:00")),
     ("2026-10-17T10:30:00+09:30", ms("2026-10-17T01:00:00+00:00")), ("1970-01-01T00:00:00+00:00", 0)],
)
def test_d0027_ac56_parse_time_accepts_offset_iso(node, html, text, expected):
    """D0027-AC-56: parseTime はずれつき ISO（+09:00・Z・-05:00・+09:30）を ms にする。"""
    assert call(node, html, "parseTime", text) == expected


@pytest.mark.parametrize(
    "bad",
    ["", "abc", "2026-10-17T10:00:00", "2026-10-17", "10:00:00", "2026-13-01T00:00:00+00:00", "2026-10-17T25:00:00+00:00", "2026-10-17T01:00:00+00:00 extra",
     "x2026-10-17T01:00:00+00:00", "a" * 100000, None, 123, 0, True, [], {}, ["2026-10-17T01:00:00+00:00"], {"at": "2026-10-17T01:00:00+00:00"}],
    ids=lambda v: repr(v)[:30],
)
def test_d0027_ac57_parse_time_rejects_everything_else(node, html, bad):
    """D0027-AC-57: parseTime は、ずれつき ISO の形だけ通す。ずれなし・日付だけ・壊れた・型違いは null。"""
    assert call(node, html, "parseTime", bad) is None


@pytest.mark.parametrize(
    "text,now_offset_ms,expected",
    [(iso(83), 0, 83), (iso(83), 999, 83), (iso(83), 1000, 84), (iso(0), 0, 0), (iso(-5), 0, 0), (iso(-86400), 0, 0), (iso(359999), 0, 359999),
     (iso(360000), 0, 359999), (iso(10**8), 0, 359999)],
    ids=["83s", "83.999s_floor", "84s", "zero", "future_5s", "future_1d", "cap_exact", "cap_plus_1", "huge"],
)
def test_d0027_ac56_elapsed_sec_function(node, html, text, now_offset_ms, expected):
    """D0027-AC-56: elapsedSec(text, nowMs) は max(0, floor((今 − 時刻)/1000))。未来は 0、上限 359999。"""
    assert call(node, html, "elapsedSec", text, ms(T0.isoformat()) + now_offset_ms) == expected


@pytest.mark.parametrize("bad", [None, "abc", "", 5, [], {}, "2026-10-17T10:00:00"], ids=lambda v: repr(v)[:20])
def test_d0027_ac57_elapsed_sec_is_null_without_a_usable_time(node, html, bad):
    """D0027-AC-57: 時刻が無い・壊れているときの elapsedSec は null（0 にして数え上げない）。"""
    assert call(node, html, "elapsedSec", bad, ms(T0.isoformat())) is None


# ---- checkSnapshot ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [None, 5, 1.5, "text", True, False, [], [1, 2], {}, {"stages": []}, {"schema": 2, "stages": []}, {"schema": "1", "stages": []}, {"schema": 1},
     {"schema": 1, "stages": "x"}, {"schema": 1, "stages": {}}, {"schema": 1, "stages": None}, {"schema": 1, "stages": 5}, {"schema": NAN, "stages": []},
     {"schema": True, "stages": []}],
    ids=lambda v: repr(v)[:40],
)
def test_d0027_ac59_check_snapshot_rejects_unusable_values(node, html, bad):
    """D0027-AC-59: checkSnapshot は、使えない値（null・型違い・schema が 1 でない・stages が配列でない）を null にする。"""
    assert call(node, html, "checkSnapshot", bad) is None


@pytest.mark.parametrize("good", [{"schema": 1, "stages": []}, counting_snapshot(), done_snapshot(), snapshot([])], ids=["minimal", "counting", "done", "empty_stages"])
def test_d0027_ac59_check_snapshot_accepts_usable_values(node, html, good):
    """D0027-AC-59: checkSnapshot は、使える写し（schema 1・stages が配列）を null にしない。"""
    assert call(node, html, "checkSnapshot", good) is not None


@pytest.mark.parametrize("entry", [None, 1, "x", [], {}, {"name": 5}, {"status": {}}, {"label": [], "name": []}, {"name": "x" * 1000, "status": "x" * 1000}], ids=lambda v: repr(v)[:30])
def test_d0027_ac59_check_snapshot_does_not_throw_on_bad_stage_entries(node, html, entry):
    """D0027-AC-59: stages の要素が壊れていても、checkSnapshot は例外を出さない。"""
    call(node, html, "checkSnapshot", snapshot([stage("ok", "done"), entry]))


# ---- AC-59 描き直し ---------------------------------------------------------------------------------------

BAD_VALUES = [
    None, 5, 1.5, "text", "", True, False, [], [1, 2, 3], [counting_snapshot()], {}, {"schema": 1}, {"stages": []}, {"schema": 1, "stages": "x"},
    {"schema": 1, "stages": {"0": stage("a")}}, {"schema": 1, "stages": None, "name": "BAD-MARK"},
    snapshot([None, 1, "x", [], {}, {"name": 5}, stage("z", "done")], name="BAD-MARK"),
    snapshot([stage("a", "weird")], name="BAD-MARK"), snapshot([stage("a", 5)], name="BAD-MARK"), snapshot([stage("a", {"x": 1})], name="BAD-MARK"),
    snapshot([stage("a", None)], name="BAD-MARK"), snapshot([{"name": "a"}], name="BAD-MARK"), snapshot([{"status": "done"}], name="BAD-MARK"),
    snapshot([stage("a", "running", attempt=NAN, cost_usd=INF, turns=NINF, duration_sec=NAN)], name="BAD-MARK"),
    snapshot([stage("a", "running", attempt="x", cost_usd="y", turns=[], duration_sec={}, verdict=5, started_at=5)], name="BAD-MARK"),
    snapshot([stage("a", "done", attempt=10**30, cost_usd=1e308, turns=-1, duration_sec=-1e308)], name="BAD-MARK"),
    snapshot([stage("a", label=5)], name="BAD-MARK"), snapshot([stage("a", label=None)], name="BAD-MARK"), snapshot([stage("a", label=["x"])], name="BAD-MARK"),
    snapshot([stage("a")], name=5), snapshot([stage("a")], name=None), snapshot([stage("a")], name={"x": 1}), snapshot([stage("a")], name=["x"]),
    snapshot([stage("a")], final=5), snapshot([stage("a")], final={"x": 1}), snapshot([stage("a")], final="BOGUS"),
    snapshot([stage("a")], generated_at=5), snapshot([stage("a")], generated_at=None),
    snapshot([stage(f"s{i}") for i in range(500)], name="BAD-MARK"),
    snapshot([stage("a")], name="BAD-MARK" + "x" * 100000),
    {"schema": 1, "stages": [stage("a")], "__proto__": {"x": 1}, "constructor": {"prototype": 1}},
]


@pytest.mark.parametrize("bad", BAD_VALUES, ids=lambda v: repr(v)[:50])
def test_d0027_ac59_render_survives_bad_values_and_keeps_the_screen(node, html, bad):
    """D0027-AC-59: 写しが null・配列・文字列・stages が無い・要素が壊れている・未知の status などでも、例外を出さず、直前の画面か「まだ記録がありません」が残る。次の正しい写しで元に戻る。"""
    good, second = snapshot([stage("g", "done")], name="GOODNAME-MARK"), snapshot([stage("g", "done")], name="SECOND-MARK")
    r = go(node, html, steps=sending(good, bad, second))
    bad_step = r["steps"][1]
    assert bad_step["threw"] is None, bad_step["threw"]
    text = bad_step["view"]["text"]
    assert text.strip()
    assert any(m in text for m in ("GOODNAME-MARK", EMPTY_MSG, UNSUPPORTED_MSG, "BAD-MARK", "LABEL-")), text
    assert r["steps"][2]["threw"] is None and "SECOND-MARK" in r["steps"][2]["view"]["text"]
    assert bad_step["view"]["html_insertions"] == 0 and r["alerts"] == []


@pytest.mark.parametrize("bad", BAD_VALUES, ids=lambda v: repr(v)[:50])
def test_d0027_ac59_render_function_does_not_throw(node, html, bad):
    """D0027-AC-59: render を直接呼んでも、壊れた値で例外を出さない（try/catch で包んでいる）。"""
    call(node, html, "render", bad)


@pytest.mark.parametrize("what", ["null", "undefined", "no_data", "data_throws", "data_function", "number", "string", "exists_string"])
def test_d0027_ac59_odd_snapshots_from_the_db_do_not_throw(node, html, what):
    """D0027-AC-59: db の snap そのものが変（null・data が無い・data が例外・数・文字）でも、受け口から例外を出さない。"""
    good = snapshot([stage("g", "done")], name="GOODNAME-MARK")
    r = go(node, html, steps=[*sending(good), {"op": "send_raw", "what": what}, *sending(snapshot([stage("g", "done")], name="SECOND-MARK"))])
    assert r["steps"][1]["threw"] is None, r["steps"][1]["threw"]
    assert "SECOND-MARK" in r["steps"][2]["view"]["text"]


def test_d0027_ac59_empty_value_shows_no_record_message(node, html):
    """D0027-AC-59: 記録なしの形（empty が true）や、ドキュメントが無い（exists が false）ときは「まだ記録がありません」を出す。"""
    empty = {"schema": 1, "generated_at": T0.isoformat(), "empty": True, "name": None, "final": None, "stages": []}
    r = go(node, html, steps=[*sending(empty), *sending(counting_snapshot()), {"op": "send", "missing": True}, *sending(empty)])
    assert EMPTY_MSG in r["steps"][0]["view"]["text"]
    assert EMPTY_MSG not in r["steps"][1]["view"]["text"] and GOOD_MARK in r["steps"][1]["view"]["text"]
    assert r["steps"][2]["threw"] is None and r["steps"][2]["view"]["text"].strip()
    assert EMPTY_MSG in r["steps"][3]["view"]["text"] and GOOD_MARK not in r["steps"][3]["view"]["text"]


def test_d0027_ac59_missing_document_at_the_start_shows_no_record_message(node, html):
    """D0027-AC-59: ドキュメントがまだ無い（exists が false）まま始まったときは「まだ記録がありません」。"""
    r = go(node, html, initial={"missing": True})
    assert EMPTY_MSG in r["loaded"]["text"]


def test_d0027_ac59_initial_value_is_rendered(node, html):
    """D0027-AC-59: 購読した直後に届く値も描かれる（購読と同時に来る最初の値）。"""
    r = go(node, html, initial={"value": counting_snapshot()})
    assert GOOD_MARK in r["loaded"]["text"] and r["loaded"]["intervals"] == 1


def test_d0027_ac59_db_error_callback_keeps_the_screen_and_does_not_throw(node, html):
    """D0027-AC-59: onSnapshot の error が呼ばれても、例外を出さず、直前の画面を残す。その後の値は描ける。"""
    r = go(node, html, steps=[*sending(counting_snapshot()), {"op": "error", "message": "permission-denied"}, *sending(snapshot([stage("g")], name="SECOND-MARK"))])
    assert r["steps"][1]["threw"] is None and r["steps"][1]["view"]["text"].strip()
    assert "SECOND-MARK" in r["steps"][2]["view"]["text"]


def test_d0027_ac59_unsupported_schema_is_named_and_not_drawn(node, html):
    """D0027-AC-59: schema が 1 でない写しは「この写しの版には対応していません」を出し、中身は描かない。"""
    snap = snapshot([stage("g", "done")], name="NEWER-MARK", schema=2)
    r = go(node, html, steps=sending(snap))
    text = r["steps"][0]["view"]["text"]
    assert UNSUPPORTED_MSG in text
    assert "NEWER-MARK" not in text and "LABEL-g" not in text


def test_d0027_ac59_renders_name_labels_and_status_marks(node, html):
    """D0027-AC-59: セッション名と段の表示名が出て、状態は記号つきの文字で出る（色だけで伝えない）。"""
    snap = snapshot([stage("a", "waiting"), stage("b", "running", started_at=iso(5)), stage("c", "review", pending_since=iso(5)), stage("d", "done"),
                     stage("e", "failed"), stage("f", "revised")])
    text = go(node, html, steps=sending(snap))["steps"][0]["view"]["text"]
    assert GOOD_MARK in text
    for name in "abcdef":
        assert f"LABEL-{name}" in text
    for mark in "✓✕↩":  # まだ・動いている・確認待ちの印は CSS の形（文字を持たない。AC-86）
        assert mark in text, mark
    for word in ("まだ", "実行中", "確認待ち"):  # D0059：まだ始まっていない段の語は「待ち」から「まだ」に変えた（FR-05）
        assert word in text, word


@pytest.mark.parametrize("status,mark", [("done", "✓"), ("failed", "✕"), ("revised", "↩")])
def test_d0027_ac59_each_status_has_its_own_mark(node, html, status, mark):
    """D0027-AC-59: 文字の印を持つ状態（終わり・失敗・差し戻し）は、自分の記号が出る（1段だけの写しで）。"""
    text = go(node, html, steps=sending(snapshot([stage("only", status)])))["steps"][0]["view"]["text"]
    assert mark in text


def test_d0027_ac59_six_statuses_look_different(node, html):
    """D0027-AC-59: 6つの状態は、画面の文字でも区別できる（同じ見た目の状態が無い）。"""
    texts = set()
    for status in ("waiting", "running", "review", "done", "failed", "revised"):
        extra = {"started_at": iso(5)} if status == "running" else {"pending_since": iso(5)} if status == "review" else {}
        texts.add(go(node, html, steps=sending(snapshot([stage("only", status, **extra)])))["steps"][0]["view"]["text"])
    assert len(texts) == 6


@pytest.mark.parametrize("status", ["__proto__", "constructor", "toString", "hasOwnProperty", "valueOf", "prototype", "unknown", "", "RUNNING", " running"])
def test_d0027_ac59_unknown_status_does_not_look_up_object_prototype(node, html, status):
    """D0027-AC-59: 未知の status（Object の名前を含む）は unknown として扱い、[object Object] や関数の文字を出さない。表示名は出る。"""
    text = go(node, html, steps=sending(snapshot([stage("only", status)])))["steps"][0]["view"]["text"]
    assert "LABEL-only" in text
    assert "[object" not in text and "function" not in text and "undefined" not in text and "NaN" not in text


def test_d0027_ac59_stage_limit_is_24_and_text_limit_is_80(node, html):
    """D0027-AC-59: 段は 24 まで、文字は 80 文字までしか描かない（多すぎる写しで画面を壊さない）。"""
    many = snapshot([stage(f"S{i:02d}", "done") for i in range(1, 31)], name="N" + "x" * 500)
    text = go(node, html, steps=sending(many))["steps"][0]["view"]["text"]
    assert "LABEL-S24" in text and "LABEL-S25" not in text and "LABEL-S30" not in text
    assert "x" * 81 not in text and "x" * 10 in text


def test_d0027_ac59_unknown_keys_are_not_shown(node, html):
    """D0027-AC-59: 写しの知らないキー（secretKey など）の値は、画面に出さない（許すものだけを描く）。"""
    snap = snapshot([stage("a", "done", secretKey="LEAK-MARK", extra={"x": "LEAK-MARK"})], secretTop="LEAK-MARK", session_id="LEAK-MARK")
    r = go(node, html, steps=sending(snap))
    assert "LEAK-MARK" not in r["steps"][0]["view"]["text"]


def test_d0027_ac59_numbers_from_the_snapshot_do_not_leak_odd_text(node, html):
    """D0027-AC-59: 費用・ターンなどの数が NaN・巨大でも、画面に NaN・Infinity・undefined・null の文字が出ない。"""
    snap = snapshot([
        stage("a", "done", attempt=3, cost_usd=NAN, turns=INF, duration_sec=NINF),
        stage("b", "done", attempt=10**20, cost_usd=1e300, turns=10**20, duration_sec=1e300),
        stage("c", "done", attempt=None, cost_usd=None, turns=None, duration_sec=None),
    ])
    text = go(node, html, steps=sending(snap))["steps"][0]["view"]["text"]
    for word in ("NaN", "Infinity", "undefined", "null", "[object"):
        assert word not in text, word


def test_d0027_ac59_final_and_verdict_values_do_not_break_rendering(node, html):
    """D0027-AC-59: final と verdict の値（正しいもの・未知のもの）で、描き直しが壊れない。"""
    for final, verdict in (("PASSED", "pass"), ("TEST_FAILED", "fail"), ("BLOCKED", "blocked"), ("STOPPED_BY_HUMAN", "pass"), ("STAGE_ERROR", None), (None, None)):
        r = go(node, html, steps=sending(snapshot([stage("test", "done", verdict=verdict)], final=final, name="OK-MARK")))
        assert r["steps"][0]["threw"] is None and "OK-MARK" in r["steps"][0]["view"]["text"], (final, verdict)
    for final, verdict in (("BOGUS", "bogus"), (5, 5), ({"x": 1}, [])):
        r = go(node, html, steps=sending(snapshot([stage("test", "done", verdict=verdict)], final=final, name="OK-MARK")))
        text = r["steps"][0]["view"]["text"]
        assert r["steps"][0]["threw"] is None and ("OK-MARK" in text or EMPTY_MSG in text), (final, verdict)


# ---- AC-60 タイマーは1つ ---------------------------------------------------------------------------------


def test_d0027_ac60_one_timer_across_renders(node, html):
    """D0027-AC-60: 描き直しのたびにタイマーは1つのまま（1000ms 間隔）。"""
    r = go(node, html, steps=sending(*[counting_snapshot(83 + i, 40 + i) for i in range(6)]))
    for step in r["steps"]:
        assert step["view"]["intervals"] == 1 and step["view"]["interval_ms"] == [1000]
        assert step["view"]["timeouts"] == 0


def test_d0027_ac60_same_snapshot_many_times_keeps_one_timer(node, html):
    """D0027-AC-60: 同じ写しを何十回受けても、タイマーは増えない。"""
    r = go(node, html, steps=sending(*[counting_snapshot()] * 40))
    assert [s["view"]["intervals"] for s in r["steps"]] == [1] * 40


def test_d0027_ac60_no_timer_without_counting_elements(node, html):
    """D0027-AC-60: 数える要素が無い写し（終わり・待ちだけ・時刻なし）では、タイマーを回さない。始める前も回さない。"""
    r = go(node, html, steps=sending(done_snapshot(), snapshot([stage("a")]), snapshot([]), snapshot([stage("a", "running"), stage("b", "review")])))
    assert r["loaded"]["intervals"] == 0 and r["loaded"]["timeouts"] == 0
    assert [s["view"]["intervals"] for s in r["steps"]] == [0, 0, 0, 0]


def test_d0027_ac60_timer_follows_the_counting_elements(node, html):
    """D0027-AC-60: 数える要素が無くなればタイマーを止め、また現れれば1つ回す。"""
    r = go(node, html, steps=sending(counting_snapshot(), done_snapshot(), counting_snapshot(), snapshot([stage("a", "running", started_at=iso(5))]), done_snapshot()))
    assert [s["view"]["intervals"] for s in r["steps"]] == [1, 0, 1, 1, 0]


def test_d0027_ac60_bad_values_do_not_start_or_multiply_timers(node, html):
    """D0027-AC-60: 壊れた値を受けても、タイマーは増えない（始めからも、動いている途中でも）。"""
    r = go(node, html, steps=[*sending(None, "x", [], {}), *sending(counting_snapshot()), *sending(None, 5, {"schema": 1, "stages": "x"}, counting_snapshot())])
    assert [s["view"]["intervals"] for s in r["steps"][:4]] == [0, 0, 0, 0]
    assert all(s["view"]["intervals"] <= 1 for s in r["steps"][4:])
    assert r["steps"][-1]["view"]["intervals"] == 1


def test_d0027_ac60_no_timer_when_the_db_is_unavailable(node, html):
    """D0027-AC-60: db が使えない画面では、タイマーを回さない。"""
    for mode in ("null", "undefined", "use_rejects"):
        r = run_scene(node, html, claude=mode)
        assert r["loaded"]["intervals"] == 0 and r["loaded"]["timeouts"] == 0, mode


def test_d0027_ac60_timer_ticks_update_the_text_without_new_elements(node, html):
    """D0027-AC-60: 1秒ごとの更新は文字だけを書き換える（要素を作り直さない）。"""
    r = go(node, html, steps=[*sending(counting_snapshot()), {"op": "advance", "ms": 1000}, {"op": "advance", "ms": 30000}])
    created = [len(s["view"]["created"]) for s in r["steps"]]
    assert created[0] == created[1] == created[2]
    assert r["steps"][0]["view"]["tags"] == r["steps"][2]["view"]["tags"]


# ---- AC-61 隠れる・戻る ---------------------------------------------------------------------------------


def test_d0027_ac61_hidden_stops_timer_and_visible_recomputes(node, html):
    """D0027-AC-61: 隠れるとタイマーが止まり、隠れている間は増えない。戻ると、今の時刻から求め直して数え直す。"""
    r = go(node, html, steps=[
        *sending(counting_snapshot(83, 40)), {"op": "hidden", "value": True}, {"op": "advance", "ms": 600000},
        {"op": "hidden", "value": False}, {"op": "advance", "ms": 1000},
    ])
    shown, hid, later, back, tick = r["steps"]
    assert shown["view"]["intervals"] == 1
    assert hid["view"]["intervals"] == 0 and hid["view"]["hidden"] is True
    assert later["view"]["intervals"] == 0 and shows(later["view"]["text"], "1:23") and not shows(later["view"]["text"], "11:23")
    assert back["view"]["intervals"] == 1 and shows(back["view"]["text"], "11:23") and shows(back["view"]["text"], "10:40")
    assert shows(tick["view"]["text"], "11:24") and shows(tick["view"]["text"], "10:41")


def test_d0027_ac61_returns_exactly_after_a_short_hide(node, html):
    """D0027-AC-61: 59 秒隠れて戻ると、その分を足した値（83+59=142 秒＝2:22）になり、1秒後に 2:23。"""
    r = go(node, html, steps=[*sending(counting_snapshot(83, 40)), {"op": "hidden", "value": True}, {"op": "advance", "ms": 59000}, {"op": "hidden", "value": False},
                              {"op": "advance", "ms": 1000}])
    assert shows(r["steps"][3]["view"]["text"], "2:22") and shows(r["steps"][4]["view"]["text"], "2:23")


def test_d0027_ac61_repeated_hide_and_show_never_stacks_timers(node, html):
    """D0027-AC-61: 隠れる・戻るを何度繰り返しても、動いているタイマーは多くても1つ。隠れている間は0。"""
    steps = [*sending(counting_snapshot())]
    for _ in range(5):
        steps += [{"op": "hidden", "value": True}, {"op": "hidden", "value": True}, {"op": "hidden", "value": False}, {"op": "hidden", "value": False}]
    r = go(node, html, steps=steps)
    got = [(s["view"]["hidden"], s["view"]["intervals"]) for s in r["steps"][1:]]
    assert all(n == (0 if h else 1) for h, n in got), got


def test_d0027_ac61_visibility_event_while_visible_does_not_add_a_timer(node, html):
    """D0027-AC-61: 見えているまま visibilitychange が来ても、タイマーは1つのまま。"""
    r = go(node, html, steps=[*sending(counting_snapshot()), {"op": "hidden", "value": False}, {"op": "hidden", "value": False}])
    assert [s["view"]["intervals"] for s in r["steps"]] == [1, 1, 1]


def test_d0027_ac61_starting_hidden_does_not_start_the_timer(node, html):
    """D0027-AC-61: 隠れた状態で写しを受けても、タイマーは回さない。見えるようになってから回し、正しい経過を出す。"""
    r = go(node, html, hidden=True, steps=[*sending(counting_snapshot(83, 40)), {"op": "advance", "ms": 17000}, {"op": "hidden", "value": False}])
    assert r["steps"][0]["view"]["intervals"] == 0 and r["steps"][1]["view"]["intervals"] == 0
    assert r["steps"][2]["view"]["intervals"] == 1 and shows(r["steps"][2]["view"]["text"], "1:40") and shows(r["steps"][2]["view"]["text"], "0:57")


def test_d0027_ac61_new_snapshot_while_hidden_starts_no_timer_until_visible(node, html):
    """D0027-AC-61: 隠れている間に新しい写しを受けても、タイマーは回さない。戻ったら回す。"""
    r = go(node, html, steps=[*sending(counting_snapshot()), {"op": "hidden", "value": True}, *sending(counting_snapshot(10, 5)), {"op": "hidden", "value": False}])
    assert [s["view"]["intervals"] for s in r["steps"]] == [1, 0, 0, 1]
    assert shows(r["steps"][3]["view"]["text"], "0:10")


def test_d0027_ac61_hide_without_counting_elements_then_show_runs_no_timer(node, html):
    """D0027-AC-61: 数える要素が無いとき、隠れて戻ってもタイマーは回さない。"""
    r = go(node, html, steps=[*sending(done_snapshot()), {"op": "hidden", "value": True}, {"op": "hidden", "value": False}])
    assert [s["view"]["intervals"] for s in r["steps"]] == [0, 0, 0]


def test_d0027_ac61_counting_ends_while_hidden_then_show_runs_no_timer(node, html):
    """D0027-AC-61: 隠れている間に数える要素が無くなったら、戻ってもタイマーは回さない。"""
    r = go(node, html, steps=[*sending(counting_snapshot()), {"op": "hidden", "value": True}, *sending(done_snapshot()), {"op": "hidden", "value": False}])
    assert r["steps"][-1]["view"]["intervals"] == 0


# ---- AC-62 文字として出す --------------------------------------------------------------------------------

HOSTILE_TEXTS = [
    "<script>alert(1)</script>", "<img src=x onerror=alert(1)>", '"><svg onload=alert(1)>', "</script><script>alert(2)</script>", "&lt;b&gt;bold&lt;/b&gt;",
    "<b>bold</b>", "javascript:alert(1)", "'-alert(1)-'", "<iframe src=//evil></iframe>", "<style>*{display:none}</style>", "{{constructor.constructor('alert(1)')()}}",
    "${alert(1)}", "`${alert(1)}`", "‮⁧rtl⁩", "\ud800lone", "😀👨‍👩‍👧", "e" + "́" * 40,
]


@pytest.mark.parametrize("text", HOSTILE_TEXTS, ids=lambda v: repr(v)[:30])
def test_d0027_ac62_db_values_become_text_not_elements(node, html, text):
    """D0027-AC-62: db の値に <script> や HTML の文字があっても、DOM に要素が増えない（同じ形の無害な写しと、要素の種類・数・属性が同じ）。文字としては見える。"""
    short = text[:60]
    hostile = snapshot([stage("a", "running", label=short, started_at=iso(5)), stage("b", "done", label=short)], name=short)
    plain = snapshot([stage("a", "running", label="AAAA", started_at=iso(5)), stage("b", "done", label="AAAA")], name="AAAA")
    h = go(node, html, steps=sending(hostile))["steps"][0]
    p = go(node, html, steps=sending(plain))["steps"][0]
    assert h["threw"] is None
    assert h["view"]["tags"] == p["view"]["tags"], (h["view"]["tags"], p["view"]["tags"])
    assert h["view"]["created"] == p["view"]["created"]
    assert h["view"]["attrs"] == p["view"]["attrs"] and not [a for a in h["view"]["attrs"] if a.startswith("on")]
    assert h["view"]["html_insertions"] == 0


def test_d0027_ac62_script_markup_is_visible_as_literal_text(node, html):
    """D0027-AC-62: <script>alert(1)</script> を名前に入れた写しは、文字としてそのまま見える。警告も出ない。"""
    name = "<script>alert(1)</script>"
    r = go(node, html, steps=sending(snapshot([stage("a", "done", label=name)], name=name)))
    lines = r["steps"][0]["view"]["lines"]
    assert sum(name in line for line in lines) >= 2
    assert r["alerts"] == []
    forbidden = {"script", "img", "iframe", "a", "style", "link", "object", "embed", "svg", "form", "input", "button"}
    assert not forbidden & set(r["steps"][0]["view"]["created"])


def test_d0027_ac62_entities_are_not_decoded(node, html):
    """D0027-AC-62: &lt;b&gt; のような文字は、そのまま &lt;b&gt; と見える（解釈しない）。"""
    r = go(node, html, steps=sending(snapshot([stage("a", "done", label="&lt;b&gt;&amp;")], name="&lt;i&gt;")))
    text = r["steps"][0]["view"]["text"]
    assert "&lt;b&gt;&amp;" in text and "&lt;i&gt;" in text


def test_d0027_ac62_no_page_script_runs_from_values(node, html):
    """D0027-AC-62: 値の中の alert(…) が実行されない。"""
    r = go(node, html, steps=sending(*[snapshot([stage("a", "done", label=t[:60])], name=t[:60]) for t in HOSTILE_TEXTS]))
    assert r["alerts"] == [] and r["unhandled"] == [] and r["uncaught"] == []
    assert r["final"]["html_insertions"] == 0


# ---- AC-50（動き）db の取り方 ---------------------------------------------------------------------------------


def test_d0027_ac50_null_db_shows_the_unreadable_message_without_error(node, html):
    """D0027-AC-50: claude.use("db") が null のとき、「この画面では読めません」を出し、コンソールにもエラーを出さず、購読もしない。"""
    r = go(node, html, claude="null")
    assert UNREADABLE_MSG in r["loaded"]["text"]
    assert r["console_errors"] == [] and r["listener_errors"] == []
    assert r["db"]["subscriptions"] == 0 and r["db"]["use_calls"] == ["db"]


@pytest.mark.parametrize("mode", ["undefined", "use_rejects", "use_throws", "use_undefined"])
def test_d0027_ac50_db_that_cannot_be_taken_shows_the_unreadable_message(node, html, mode):
    """D0027-AC-50: claude が無い・use が拒否や例外・undefined を返すときも、「この画面では読めません」を出す（未処理の例外を出さない）。"""
    r = go(node, html, claude=mode)
    assert UNREADABLE_MSG in r["loaded"]["text"], mode


@pytest.mark.parametrize("mode", ["doc_throws", "onsnapshot_throws"])
def test_d0027_ac50_db_that_fails_midway_does_not_crash(node, html, mode):
    """D0027-AC-50: db.doc や onSnapshot が例外を出しても、未処理の例外を出さず、何か画面に書く。"""
    r = go(node, html, claude=mode)
    assert r["loaded"]["text"].strip()


def test_d0027_ac50_page_subscribes_once_to_runs_current_and_never_writes(node, html):
    """D0027-AC-50: db.doc("runs/current") を1回だけ購読する（何度値が来ても増やさない）。ページは書き込まない。"""
    r = go(node, html, steps=sending(*[counting_snapshot()] * 10))
    assert r["db"]["calls"] == [["doc", "runs/current"], ["onSnapshot", "runs/current"]]
    assert r["db"]["subscriptions"] == 1 and r["db"]["active_subscriptions"] == 1
    assert r["db"]["writes"] == [] and r["db"]["use_calls"] == ["db"]


def test_d0027_ac50_nothing_is_written_even_on_errors(node, html):
    """D0027-AC-50: 値が壊れていても、エラーが来ても、ページは db に書かない。"""
    r = go(node, html, steps=[*sending(None, {}, counting_snapshot()), {"op": "error", "message": "x"}, {"op": "send", "missing": True}])
    assert r["db"]["writes"] == []


def test_d0027_ac50_script_runs_cleanly_when_loaded(node, html):
    """D0027-AC-50: 読み込みだけで、例外・未処理の拒否・コンソールのエラーが出ない（db が使える場合）。"""
    r = go(node, html)
    assert r["console_errors"] == [] and r["listener_errors"] == [] and r["loaded"]["html_insertions"] == 0


def test_d0027_ac50_body_skeleton_is_found_by_the_script(node, html):
    """D0027-AC-50: 骨組み（見出し・入れ物）が画面にあり、写しを受ける前でも何か（読み込み中・記録なし）が書いてあるか、空である。"""
    r = go(node, html)
    assert r["loaded"]["tags"], "骨組みの要素が無い"


# ---- AC-86 状態の印（文字を持つ・持たない） -----------------------------------------------------------------

CSS_DRAWN = {"waiting": "まだ", "running": "実行中", "review": "確認待ち"}  # D0059：waiting の語は「まだ」（FR-05）
TEXT_MARKS = {"done": "✓", "failed": "✕", "revised": "↩", "unknown": "？"}


def one_stage(status: str, **kw) -> dict:
    extra = {"started_at": iso(5)} if status == "running" else {"pending_since": iso(5)} if status == "review" else {}
    extra.update(kw)
    return snapshot([stage("only", status, **extra)])


def query(node, html, snap, selector):
    r = go(node, html, steps=[*sending(snap), {"op": "query", "selector": selector}])
    return r["steps"][-1]["result"]


@pytest.mark.parametrize("status,word", list(CSS_DRAWN.items()))
def test_d0027_ac86_css_drawn_marks_have_no_text_but_the_word_stays(node, html, status, word):
    """D0027-AC-86: まだ・動いている・確認待ちの印の要素は文字を持たず（textContent が空）、aria-hidden のまま。意味は隣の言葉が伝える。"""
    marks = query(node, html, one_stage(status), ".mark")
    assert len(marks) == 1
    assert marks[0]["text"] == "", f"印に字形が残っている: {marks[0]['text']!r}"
    assert marks[0]["attrs"].get("aria-hidden") == "true"
    words = query(node, html, one_stage(status), ".word")
    assert [w["text"] for w in words] == [word]


@pytest.mark.parametrize("status,glyph", list(TEXT_MARKS.items()))
def test_d0027_ac86_other_marks_stay_one_character_and_hidden_from_readers(node, html, status, glyph):
    """D0027-AC-86: 終わり・失敗・差し戻し（と未知）の印は今の文字のまま、1文字で、aria-hidden のまま（同じ固定の幅に収まる）。"""
    marks = query(node, html, one_stage(status), ".mark")
    assert len(marks) == 1
    assert marks[0]["text"] == glyph
    assert len(marks[0]["text"]) == 1
    assert marks[0]["attrs"].get("aria-hidden") == "true"


def test_d0027_ac86_every_row_has_exactly_one_mark_first(node, html):
    """D0027-AC-86: どの行にも印が1つあり、行の最初の要素（表示名の位置が行ごとにずれない）。"""
    snap = snapshot([stage(f"s{i}", st, **({"started_at": iso(5)} if st == "running" else {"pending_since": iso(5)} if st == "review" else {}))
                     for i, st in enumerate(["waiting", "running", "review", "done", "failed", "revised"])])
    rows = query(node, html, snap, ".stage")
    marks = query(node, html, snap, ".stage > .mark")
    assert len(rows) == 6 and len(marks) == 6
    firsts = query(node, html, snap, ".stage > span")
    assert firsts, "行に span が無い"
    assert "mark" in firsts[0]["attrs"].get("class", "")


def test_d0027_ac86_drawn_marks_keep_their_status_class_for_the_css(node, html):
    """D0027-AC-86: 行の class が s-<状態> のまま（CSS の形が .s-<状態> .mark で当たる）。"""
    for status in CSS_DRAWN:
        rows = query(node, html, one_stage(status), ".stage")
        assert len(rows) == 1 and f"s-{status}" in rows[0]["attrs"]["class"].split()


# ---- AC-87 0 の費用・ターンは出さない ----------------------------------------------------------------------


def usage(node, html, cost=None, turns=None, duration=None):
    return call(node, html, "usageText", {"cost": cost, "turns": turns, "duration": duration})


@pytest.mark.parametrize("bad", [0, -0.0, -1, -0.5, NAN, INF, NINF, None, "abc", "", "5", True, [], {}], ids=lambda v: repr(v)[:20])
def test_d0027_ac87_cost_that_is_not_a_positive_number_is_not_shown(node, html, bad):
    """D0027-AC-87: 費用が 0・負・NaN・Infinity・null・文字・真偽・配列のときは、費用を出さない。"""
    assert usage(node, html, cost=bad) == ""


@pytest.mark.parametrize("bad", [0, -0.0, -1, -0.5, NAN, INF, NINF, None, "abc", "", "5", True, [], {}], ids=lambda v: repr(v)[:20])
def test_d0027_ac87_turns_that_are_not_a_positive_number_are_not_shown(node, html, bad):
    """D0027-AC-87: ターンが 0・負・NaN・Infinity・null・文字・真偽・配列のときは、ターンを出さない。"""
    assert usage(node, html, turns=bad) == ""


@pytest.mark.parametrize("cost,expected", [(0.0001, "$0.0001"), (0.5, "$0.5"), (1, "$1"), (1.23456, "$1.2346"), (12.5, "$12.5")], ids=lambda v: str(v))
def test_d0027_ac87_positive_cost_is_shown_as_before(node, html, cost, expected):
    """D0027-AC-87: 費用が正の数なら今どおり出す（$ と、小数 4 桁までの数）。"""
    assert usage(node, html, cost=cost) == expected


@pytest.mark.parametrize("turns,expected", [(1, "1ターン"), (3, "3ターン"), (120, "120ターン")], ids=lambda v: str(v))
def test_d0027_ac87_positive_turns_are_shown_as_before(node, html, turns, expected):
    """D0027-AC-87: ターンが正の数なら今どおり出す。"""
    assert usage(node, html, turns=turns) == expected


def test_d0027_ac87_zero_cost_and_zero_turns_leave_only_the_time(node, html):
    """D0027-AC-87: 費用 0・ターン 0・時間あり（record の記録）は、時間だけが出る（「$0 ・ 0ターン」の雑音が無い）。"""
    assert usage(node, html, cost=0, turns=0, duration=69.4) == "1:09"


def test_d0027_ac87_parts_are_joined_in_order(node, html):
    """D0027-AC-87: 出すものは 費用・ターン・時間 の順に「 ・ 」でつなぐ。"""
    assert usage(node, html, cost=0.5, turns=3, duration=12.5) == "$0.5 ・ 3ターン ・ 0:12"
    assert usage(node, html, cost=0.5, turns=0, duration=12.5) == "$0.5 ・ 0:12"
    assert usage(node, html, cost=0, turns=3, duration=12.5) == "3ターン ・ 0:12"
    assert usage(node, html, cost=0.5, turns=3) == "$0.5 ・ 3ターン"


def test_d0027_ac87_nothing_to_show_gives_empty_text(node, html):
    """D0027-AC-87: 何も出すものが無いときは空文字（行に usage の要素を作らない）。"""
    assert usage(node, html) == ""
    assert usage(node, html, cost=0, turns=0) == ""


def test_d0027_ac87_row_without_anything_to_show_has_no_usage_element(node, html):
    """D0027-AC-87: 費用 0・ターン 0・時間 null、または全部 null の段には、usage の要素を作らない。"""
    for kw in ({"cost_usd": 0, "turns": 0, "duration_sec": None}, {"cost_usd": None, "turns": None, "duration_sec": None},
               {"cost_usd": 0, "turns": 0}):
        assert query(node, html, one_stage("done", **kw), ".usage") == [], kw


def test_d0027_ac87_row_with_zero_cost_and_turns_shows_only_the_time(node, html):
    """D0027-AC-87: 画面の行でも、費用 0・ターン 0・時間 69.4 は usage が「1:09」だけ。"""
    items = query(node, html, one_stage("done", cost_usd=0, turns=0, duration_sec=69.4), ".usage")
    assert [i["text"] for i in items] == ["1:09"]


def test_d0027_ac87_row_text_has_no_dollar_zero_noise(node, html):
    """D0027-AC-87: 行の文字に「$0」「0ターン」が出ない（費用 0・ターン 0 のとき）。"""
    r = go(node, html, steps=sending(one_stage("done", cost_usd=0, turns=0, duration_sec=69.4)))
    text = r["steps"][0]["view"]["text"]
    assert "$0" not in text and "0ターン" not in text and "ターン" not in text and "$" not in text


# ---- AC-88 段の時間は経過と同じ書き方 -----------------------------------------------------------------------

DURATIONS = [
    (0, "0:00"), (0.0001, "0:00"), (0.2, "0:00"), (0.99, "0:00"), (1, "0:01"), (1.5, "0:01"), (9.99, "0:09"), (10, "0:10"), (12.5, "0:12"),
    (59, "0:59"), (59.9, "0:59"), (60, "1:00"), (60.9, "1:00"), (69, "1:09"), (599, "9:59"), (600, "10:00"), (3599, "59:59"), (3599.9, "59:59"),
    (3600, "1:00:00"), (3601, "1:00:01"), (3661, "1:01:01"), (86399, "23:59:59"), (359999, "99:59:59"), (359999.9, "99:59:59"),
    (360000, "99:59:59"), (1e9, "99:59:59"), (1e300, "99:59:59"),
]


@pytest.mark.parametrize("sec,expected", DURATIONS, ids=[f"{s}s" for s, _ in DURATIONS])
def test_d0027_ac88_stage_time_uses_the_elapsed_format(node, html, sec, expected):
    """D0027-AC-88: 終わった段の時間は、経過（fmtElapsed）と同じ書き方：m:ss、1時間以上は h:mm:ss、小数は切り捨て、0 以上 1 未満は 0:00、上限は 99:59:59。"""
    assert usage(node, html, duration=sec) == expected


@pytest.mark.parametrize("sec,expected", DURATIONS, ids=[f"{s}s" for s, _ in DURATIONS])
def test_d0027_ac88_stage_time_equals_fmt_elapsed(node, html, sec, expected):
    """D0027-AC-88: 段の時間の文字は fmtElapsed の結果そのもの（別の書き方を持たない）。"""
    assert usage(node, html, duration=sec) == call(node, html, "fmtElapsed", sec)


@pytest.mark.parametrize("bad", [-1, -0.5, -3600, NAN, INF, NINF, "abc", "", "12", True, [], {}], ids=lambda v: repr(v)[:20])
def test_d0027_ac88_bad_stage_time_is_handled_like_the_elapsed(node, html, bad):
    """D0027-AC-88: 負・NaN・Infinity・文字・真偽などの時間は、経過と同じに 0:00 になる（秒の文字や NaN・例外にならない）。"""
    assert usage(node, html, duration=bad) == "0:00"


def test_d0027_ac88_null_time_is_not_shown(node, html):
    """D0027-AC-88: 時間が null なら、時間を出さない。"""
    assert usage(node, html, cost=0.5, duration=None) == "$0.5"


def test_d0027_ac88_row_shows_the_time_in_the_elapsed_format_without_seconds_unit(node, html):
    """D0027-AC-88: 画面の行：69 秒は「1:09」、0.2 秒は「0:00」。「秒」の文字は出ない。"""
    for sec, shown in ((69, "1:09"), (0.2, "0:00"), (3725, "1:02:05")):
        items = query(node, html, one_stage("done", cost_usd=None, turns=None, duration_sec=sec), ".usage")
        assert [i["text"] for i in items] == [shown], sec
        assert "秒" not in items[0]["text"]


def test_d0027_ac88_row_with_all_three_values(node, html):
    """D0027-AC-88: 費用・ターン・時間がそろった行：「$0.5 ・ 3ターン ・ 1:09」。経過（動いている段）と同じ書き方で並ぶ。"""
    items = query(node, html, one_stage("done", cost_usd=0.5, turns=3, duration_sec=69), ".usage")
    assert [i["text"] for i in items] == ["$0.5 ・ 3ターン ・ 1:09"]


def test_d0027_ac88_stage_time_does_not_change_the_running_elapsed(node, html):
    """D0027-AC-88: 動いている段の経過（m:ss）は今のまま。終わった段の時間と並んでも、どちらも m:ss。"""
    r = go(node, html, steps=sending(counting_snapshot(83, 40)))
    text = r["steps"][0]["view"]["text"]
    assert shows(text, "1:23") and shows(text, "0:40") and "0:12" in text and "秒" not in text


# ================================================================================================
# D0059：上に更新の時刻・確認待ちの札・合計・進みの帯を出す。まだの語・回数の出し方
# ================================================================================================

AT_0340 = "2026-10-17T03:40:00+00:00"
UPDATED_WORD = "更新"
TOTAL_WORD = "合計"
BADGE_WORD = "確認待ち："
BAR_KINDS = {"bar-done", "bar-gap", "bar-pending"}
REMOVE = object()


def q(selector: str) -> dict:
    return {"op": "query", "selector": selector}


def look(node, html, snap, *selectors, steps=(), **opts):
    """写し snap を届け、steps を行ってから selectors の要素を調べる。（台の結果, {selector: 要素の一覧}）。"""
    r = go(node, html, steps=[*sending(snap), *steps, *[q(s) for s in selectors]], **opts)
    n = 1 + len(steps)
    for st in r["steps"]:
        assert st["threw"] is None, st["threw"]
    return r, {s: r["steps"][n + i]["result"] for i, s in enumerate(selectors)}


def texts(items: list) -> list[str]:
    return [i["text"] for i in items]


def classes(items: list) -> list[str]:
    return [i["attrs"].get("class", "") for i in items]


def widths(items: list) -> list[str]:
    return [i["style"].get("width", "") for i in items]


def with_review(*statuses: str, **kw) -> dict:
    """statuses の順に段を並べた写し（review の段には pending_since、running の段には started_at を入れる）。"""
    rows = []
    for i, st in enumerate(statuses):
        extra = {"started_at": iso(5)} if st == "running" else {"pending_since": iso(5)} if st == "review" else {}
        rows.append(stage(f"s{i}", st, **extra))
    return snapshot(rows, **kw)


# ---- 台の自己検査（台を直したあとは、ページの出来に関係なく通る） --------------------------------------------------

STYLE_PAGE = """<!doctype html><html><body><div id="d"></div><script>
document.getElementById("d").style.width = "20%";
</script></body></html>"""


@pytest.mark.parametrize("tz,offset", [("Asia/Tokyo", -540), ("UTC", 0), (None, 0)], ids=["Asia/Tokyo", "UTC", "omitted"])
def test_d0059_harness_sets_the_time_zone(node, tz, offset):
    """D0059: 台の自己検査。場面の tz（省くと UTC）が Date の時刻帯になり、結果の tz.offset_min で確かめられる。"""
    scene = {} if tz is None else {"tz": tz}
    r = run_scene(node, REFERENCE_PAGE, **scene)
    assert r["tz"]["name"] == (tz or "UTC")
    assert r["tz"]["offset_min"] == offset


def test_d0059_harness_reports_inline_style_set_by_the_script(node):
    """D0059: 台の自己検査。JS が el.style.width = "20%" で入れた値は query の style に出て、attrs には style の属性ができない。"""
    r = run_scene(node, STYLE_PAGE, steps=[q("#d")])
    assert r["load_error"] is None
    found = r["steps"][0]["result"]
    assert len(found) == 1 and found[0]["style"] == {"width": "20%"}
    assert "style" not in found[0]["attrs"]


# ---- AC-01〜05 更新の時刻 -------------------------------------------------------------------------------------


@pytest.mark.parametrize("tz,shown", [("Asia/Tokyo", "12:40 更新"), ("UTC", "03:40 更新")])
def test_d0059_ac01_updated_time_is_shown_in_the_viewer_time_zone(node, html, tz, shown):
    """D0059-AC-01: generated_at が 2026-10-17T03:40:00+00:00 の写しは、Asia/Tokyo で「12:40 更新」、UTC で「03:40 更新」になる（見ている人の時刻帯）。"""
    r, got = look(node, html, snapshot([stage("a", "done")], generated_at=AT_0340), ".updated", tz=tz)
    assert r["tz"]["name"] == tz, "台の時刻帯が効いていない"
    assert texts(got[".updated"]) == [shown]


def test_d0059_ac02_updated_time_is_zero_padded(node, html):
    """D0059-AC-02: 時と分が1桁のとき（UTC で 09:05）は「09:05 更新」と0で埋める。updatedText を直接呼んでも同じ。"""
    _r, got = look(node, html, snapshot([stage("a", "done")], generated_at="2026-10-17T09:05:00+00:00"), ".updated", tz="UTC")
    assert texts(got[".updated"]) == ["09:05 更新"]
    assert call(node, html, "updatedText", "2026-10-17T09:05:00+00:00") == "09:05 更新"


@pytest.mark.parametrize(
    "bad",
    [REMOVE, 5, None, "2026-13-01T00:00:00Z", "2026-10-17T03:40:00", "2026-10-17T03:40:00." + "0" * 15 + "+00:00"],
    ids=["no_key", "number", "null", "month_13", "no_offset", "41_chars"],
)
def test_d0059_ac03_unreadable_generated_at_shows_no_time(node, html, bad):
    """D0059-AC-03: generated_at が無い・数・null・読めない形（13月・ずれなし・41 文字）のときは、更新の時刻（「更新」の語も）を出さず、段の行は描く。NaN・Invalid・undefined が出ない。"""
    _ctl, control = look(node, html, snapshot([stage("a", "done")], generated_at=AT_0340), ".updated")
    assert texts(control[".updated"]) == ["03:40 更新"], "対の確認：読める generated_at なら時刻が出る"
    snap = snapshot([stage("a", "done")])
    if bad is REMOVE:
        del snap["generated_at"]
    else:
        snap["generated_at"] = bad
    r, got = look(node, html, snap, ".updated")
    text = r["steps"][0]["view"]["text"]
    assert UPDATED_WORD not in text, text
    assert all(t == "" for t in texts(got[".updated"]))
    assert "LABEL-a" in text
    for word in ("NaN", "Invalid", "undefined"):
        assert word not in text, word


def test_d0059_ac03_41_characters_is_really_41(node, html):
    """D0059-AC-03: 上の「41 文字」の見本がちょうど 41 文字で、40 文字の同じ形は時刻として読める（上限の境目を確かめる）。"""
    long_text = "2026-10-17T03:40:00." + "0" * 15 + "+00:00"
    assert len(long_text) == 41
    assert call(node, html, "parseTime", long_text) is None
    assert call(node, html, "parseTime", "2026-10-17T03:40:00." + "0" * 14 + "+00:00") is not None


def test_d0059_ac04_empty_snapshot_shows_the_time_with_the_message(node, html):
    """D0059-AC-04: empty が true の写しでは「まだ記録がありません」と並んで、読める generated_at の「HH:MM 更新」が出る。"""
    empty = {"schema": 1, "generated_at": AT_0340, "empty": True, "name": None, "final": None, "stages": []}
    r, got = look(node, html, empty, ".updated", tz="UTC")
    text = r["steps"][0]["view"]["text"]
    assert EMPTY_MSG in text
    assert texts(got[".updated"]) == ["03:40 更新"]


def test_d0059_ac04_time_is_cleared_when_there_is_no_usable_snapshot(node, html):
    """D0059-AC-04: schema が 1 でない写し・写しが無い（exists が false）・壊れた値を受けると、前に出ていた更新の時刻が消える。db が使えないときも出ない。"""
    empty = {"schema": 1, "generated_at": AT_0340, "empty": True, "name": None, "final": None, "stages": []}
    newer = snapshot([stage("a", "done")], generated_at=AT_0340, schema=2)
    r = go(node, html, steps=[
        *sending(empty), *sending(newer),
        *sending(empty), {"op": "send", "missing": True},
        *sending(empty), *sending(None),
    ])
    shown = [UPDATED_WORD in s["view"]["text"] for s in r["steps"]]
    assert shown == [True, False, True, False, True, False], shown
    off = go(node, html, claude="null")
    assert UNREADABLE_MSG in off["loaded"]["text"] and UPDATED_WORD not in off["loaded"]["text"]


def test_d0059_ac05_updated_time_changes_only_with_a_new_snapshot(node, html):
    """D0059-AC-05: 更新の時刻は写しが届いたときだけ変わる。1秒ごとの tick（10 秒進める）では変わらず、新しい写しで新しい時刻になる。"""
    first = counting_snapshot()
    first["generated_at"] = AT_0340
    second = counting_snapshot()
    second["generated_at"] = "2026-10-17T03:41:00+00:00"
    r = go(node, html, steps=[*sending(first), q(".updated"), {"op": "advance", "ms": 10000}, q(".updated"), *sending(second), q(".updated")])
    assert texts(r["steps"][1]["result"]) == ["03:40 更新"]
    assert texts(r["steps"][3]["result"]) == ["03:40 更新"]
    assert texts(r["steps"][5]["result"]) == ["03:41 更新"]


# ---- AC-06〜10 合計 -------------------------------------------------------------------------------------------


def test_d0059_ac06_total_adds_cost_turns_and_time(node, html):
    """D0059-AC-06: 「0.42・9 ターン・190 秒」「0.38・7 ターン・168 秒」「どれも null」の3段で「合計 $0.8 ・ 16ターン ・ 5:58」。"""
    snap = snapshot([stage("a", "done", cost_usd=0.42, turns=9, duration_sec=190), stage("b", "done", cost_usd=0.38, turns=7, duration_sec=168), stage("c")])
    _r, got = look(node, html, snap, ".total")
    assert texts(got[".total"]) == ["合計 $0.8 ・ 16ターン ・ 5:58"]


def test_d0059_ac07_total_of_a_record_run_shows_only_the_time(node, html):
    """D0059-AC-07: 費用とターンがどの段も 0 か null で時間だけがある写し（/pipe-in の記録）は「合計 1:09」だけ。「$0」「0ターン」が出ない。"""
    snap = snapshot([stage("a", "done", cost_usd=0, turns=0, duration_sec=40), stage("b", "done", cost_usd=None, turns=None, duration_sec=29.4), stage("c")])
    r, got = look(node, html, snap, ".total")
    assert texts(got[".total"]) == ["合計 1:09"]
    text = r["steps"][0]["view"]["text"]
    assert "$0" not in text and "0ターン" not in text


@pytest.mark.parametrize(
    "rows",
    [
        [stage("a"), stage("b"), stage("c")],
        [stage("a", "done", cost_usd=0, turns=0, duration_sec=0), stage("b", "done", cost_usd=None, turns=None, duration_sec=None)],
    ],
    ids=["all_waiting", "all_zero_or_null"],
)
def test_d0059_ac08_no_total_element_without_anything_to_add(node, html, rows):
    """D0059-AC-08: どの段も費用・ターン・時間が 0 か null のとき（全部まだを含む）は、合計の要素を作らない（「合計」の語が出ない）。"""
    _ctl, control = look(node, html, snapshot([stage("a", "done", duration_sec=60)]), ".total")
    assert texts(control[".total"]) == ["合計 1:00"], "対の確認：足すものがあれば合計が出る"
    r, got = look(node, html, snapshot(rows), ".total")
    assert got[".total"] == []
    assert TOTAL_WORD not in r["steps"][0]["view"]["text"]


@pytest.mark.parametrize("bad", [-1, NAN, INF, 1e9 + 1, "5", True], ids=["negative", "NaN", "Infinity", "over_1e9", "string", "bool"])
def test_d0059_ac09_bad_numbers_are_not_added(node, html, bad):
    """D0059-AC-09: 段の値が負・NaN・Infinity・1e9 を超える・文字・真偽のときは足さない。合計に NaN・Infinity・undefined・null が出ない。"""
    snap = snapshot([stage("a", "done", cost_usd=bad, turns=bad, duration_sec=bad), stage("b", "done", cost_usd=0.5, turns=3, duration_sec=60)])
    _r, got = look(node, html, snap, ".total")
    assert texts(got[".total"]) == ["合計 $0.5 ・ 3ターン ・ 1:00"]
    for word in ("NaN", "Infinity", "undefined", "null"):
        assert word not in got[".total"][0]["text"], word


def test_d0059_ac09_total_time_is_capped(node, html):
    """D0059-AC-09: 合計の時間が 99:59:59 を超えるとき（300000 秒 × 2）は 99:59:59 で止まる。"""
    snap = snapshot([stage("a", "done", duration_sec=300000), stage("b", "done", duration_sec=300000)])
    _r, got = look(node, html, snap, ".total")
    assert texts(got[".total"]) == ["合計 99:59:59"]


def test_d0059_ac10_total_does_not_count_the_running_elapsed(node, html):
    """D0059-AC-10: 合計は写しの duration_sec の和だけ。完了 60 秒・動いている（30 秒前から）・確認待ち（45 秒前から）で「合計 1:00」、10 秒進めても同じ（行の経過は進む）。"""
    snap = snapshot([stage("a", "done", duration_sec=60), stage("b", "running", started_at=iso(30)), stage("c", "review", pending_since=iso(45))])
    r = go(node, html, steps=[*sending(snap), q(".total"), q(".elapsed"), {"op": "advance", "ms": 10000}, q(".total"), q(".elapsed")])
    assert texts(r["steps"][1]["result"]) == ["合計 1:00"]
    assert texts(r["steps"][2]["result"]) == ["0:30", "0:45"]
    assert texts(r["steps"][4]["result"]) == ["合計 1:00"]
    assert texts(r["steps"][5]["result"]) == ["0:40", "0:55"]


# ---- AC-11〜15・AC-40 進みの帯 -----------------------------------------------------------------------------------


def test_d0059_ac11_bar_widths_for_done_and_review(node, html):
    """D0059-AC-11: 5段のうち完了1・確認待ち1・まだ3では、帯の部分が順に 完了（20%）・すき間・確認待ち（20%）。"""
    _r, got = look(node, html, with_review("done", "review", "waiting", "waiting", "waiting"), ".bar > span")
    parts = got[".bar > span"]
    assert classes(parts) == ["bar-done", "bar-gap", "bar-pending"]
    assert parts[0]["style"].get("width") == "20%" and parts[2]["style"].get("width") == "20%"
    assert parts[1]["style"].get("width", "") == "", "すき間の幅は CSS（2px）で決め、JS で入れない"


@pytest.mark.parametrize(
    "statuses,expected",
    [
        (("done", "waiting", "waiting", "waiting", "waiting"), [("bar-done", "20%")]),
        (("review", "waiting", "waiting", "waiting", "waiting"), [("bar-pending", "20%")]),
        (("waiting", "waiting", "waiting", "waiting", "waiting"), []),
    ],
    ids=["done_only", "review_only", "neither"],
)
def test_d0059_ac12_bar_parts_are_made_only_when_needed(node, html, statuses, expected):
    """D0059-AC-12: 完了が0段なら完了の部分を、確認待ちが0段なら確認待ちの部分を作らない。片方だけならすき間も無い。どちらも無ければ地の帯だけ。"""
    _r, got = look(node, html, with_review(*statuses), ".bar", ".bar > span")
    assert len(got[".bar"]) == 1, "帯（地）がある"
    parts = got[".bar > span"]
    assert list(zip(classes(parts), widths(parts))) == expected


def test_d0059_ac13_other_statuses_are_counted_but_not_painted(node, html):
    """D0059-AC-13: 動いている・失敗・差し戻し・不明の段は分母に入り（6 段なら 1 段が 16.6667%）、塗る部分には入らない。"""
    _r, got = look(node, html, with_review("done", "review", "running", "failed", "revised", "weird"), ".bar > span", ".bar *")
    parts = got[".bar > span"]
    assert classes(parts) == ["bar-done", "bar-gap", "bar-pending"]
    assert widths(parts) == ["16.6667%", "", "16.6667%"]
    assert len(got[".bar *"]) == 3


def test_d0059_ac40_running_stage_is_not_in_the_bar(node, html):
    """D0059-AC-40: 完了1・動いている1・まだ3では、帯の中は完了の1つだけ（20%）。すき間・動いている段の部分・模様を作らない。部分の種類は3つだけ。"""
    _r, got = look(node, html, with_review("done", "running", "waiting", "waiting", "waiting"), ".bar > span", ".bar *")
    parts = got[".bar > span"]
    assert list(zip(classes(parts), widths(parts))) == [("bar-done", "20%")]
    assert len(got[".bar *"]) == 1
    assert set(classes(got[".bar *"])) <= BAR_KINDS


def test_d0059_ac14_bar_is_hidden_from_readers(node, html):
    """D0059-AC-14: 帯は aria-hidden="true"（同じことは行の言葉と札で伝わる）。"""
    _r, got = look(node, html, with_review("done", "review", "waiting"), ".bar")
    assert len(got[".bar"]) == 1 and got[".bar"][0]["attrs"].get("aria-hidden") == "true"


def test_d0059_ac15_bar_uses_the_drawn_stages_as_denominator(node, html):
    """D0059-AC-15: 段の幅の分母は、ページが描く段（24 まで）の数。30 段（S01〜S06 と S25〜S30 が完了）なら、描く 24 段のうち完了 6 段で 25%。"""
    rows = [stage(f"S{i:02d}", "done" if i <= 6 or i >= 25 else "waiting") for i in range(1, 31)]
    _r, got = look(node, html, snapshot(rows), ".bar > span")
    assert list(zip(classes(got[".bar > span"]), widths(got[".bar > span"]))) == [("bar-done", "25%")]


def test_d0059_ac15_bar_is_cleared_without_stages(node, html):
    """D0059-AC-15: 段が 0 の写し・empty・schema が 1 でない写しを受けると、前に出ていた帯が消える。db が使えないときも帯は無い。"""
    good = with_review("done", "review", "waiting")
    empty = {"schema": 1, "generated_at": AT_0340, "empty": True, "name": None, "final": None, "stages": []}
    newer = with_review("done", schema=2)
    r = go(node, html, steps=[
        *sending(good), q(".bar"), *sending(snapshot([])), q(".bar"),
        *sending(good), q(".bar"), *sending(empty), q(".bar"),
        *sending(good), q(".bar"), *sending(newer), q(".bar"),
    ])
    counts = [len(r["steps"][i]["result"]) for i in (1, 3, 5, 7, 9, 11)]
    assert counts == [1, 0, 1, 0, 1, 0], counts
    off = go(node, html, claude="null", steps=[q(".bar")])
    assert off["steps"][0]["result"] == []


# ---- AC-16〜20・AC-41 確認待ちの札 ----------------------------------------------------------------------------


def test_d0059_ac16_badge_names_the_review_stage(node, html):
    """D0059-AC-16: 設計の段（表示名「設計」）が確認待ちの写しでは、札が1つ出て「確認待ち：設計」。"""
    snap = snapshot([stage("requirements", "done", label="要件定義"), stage("design", "review", label="設計", pending_since=iso(5)), stage("red", label="テスト先行")])
    _r, got = look(node, html, snap, ".badge")
    assert texts(got[".badge"]) == ["確認待ち：設計"]


@pytest.mark.parametrize("review", [None, REMOVE], ids=["review_null", "no_review_key"])
def test_d0059_ac17_badge_comes_from_the_status_not_the_review_key(node, html, review):
    """D0059-AC-17: 札は段の status が review であることで決める。写しの review が null・キーが無いときでも出る。"""
    snap = snapshot([stage("a", "done"), stage("b", "review", label="設計")])
    if review is REMOVE:
        snap.pop("review", None)
    else:
        snap["review"] = review
    _r, got = look(node, html, snap, ".badge")
    assert texts(got[".badge"]) == ["確認待ち：設計"]


def test_d0059_ac17_badge_shows_only_the_first_review_stage(node, html):
    """D0059-AC-17: 確認待ちの段が2つあるときは、並びの最初の段だけを出す。"""
    snap = snapshot([stage("a", "done"), stage("b", "review", label="FIRST"), stage("c", "review", label="SECOND")])
    _r, got = look(node, html, snap, ".badge")
    assert texts(got[".badge"]) == ["確認待ち：FIRST"]


def test_d0059_ac18_badge_is_removed_without_review_or_with_final(node, html):
    """D0059-AC-18: 確認待ちの段の無い写し・final の入った写しを受けると、前に出ていた札が消える。最後の結果は今の「結果: 合格」のまま。"""
    waiting = snapshot([stage("a", "done"), stage("b", "review", label="設計")])
    running = snapshot([stage("a", "done"), stage("b", "running", started_at=iso(5))])
    final = snapshot([stage("a", "done"), stage("b", "review", label="設計")], final="PASSED")
    r = go(node, html, steps=[*sending(waiting), q(".badge"), *sending(running), q(".badge"), *sending(waiting), q(".badge"), *sending(final), q(".badge")])
    assert [len(r["steps"][i]["result"]) for i in (1, 3, 5, 7)] == [1, 0, 1, 0]
    assert "結果: 合格" in r["steps"][6]["view"]["text"]


def test_d0059_ac41_no_badge_while_only_running(node, html):
    """D0059-AC-41: 確認待ちの段が無く動いている段があるとき（完了・まだ・失敗・差し戻しもある）、札を作らず「実行中：」「結果：」も出ない。上に出るのは時刻・合計・帯だけ。"""
    snap = snapshot([stage("a", "done", duration_sec=60), stage("b", "running", started_at=iso(5)), stage("c"), stage("d", "failed"), stage("e", "revised")])
    r, got = look(node, html, snap, ".badge", ".summary > *", ".updated")
    assert got[".badge"] == []
    text = r["steps"][0]["view"]["text"]
    assert "実行中：" not in text and "結果：" not in text
    assert classes(got[".summary > *"]) == ["total", "bar"]
    assert texts(got[".updated"]) == ["02:00 更新"]


@pytest.mark.parametrize("label", ["<b>X</b>", "<img src=x onerror=alert(1)>"])
def test_d0059_ac19_badge_text_is_plain_text(node, html, label):
    """D0059-AC-19: 表示名に HTML の形を入れても、札にその文字がそのまま出て、札の中に b・img の要素ができない（textContent で出す）。"""
    r, got = look(node, html, snapshot([stage("a", "review", label=label)]), ".badge", ".badge *")
    assert texts(got[".badge"]) == [BADGE_WORD + label]
    assert got[".badge *"] == []
    tags = r["steps"][0]["view"]["tags"]
    assert "b" not in tags and "img" not in tags
    assert r["steps"][0]["view"]["html_insertions"] == 0 and r["alerts"] == []


def test_d0059_ac19_badge_label_is_cut_at_80(node, html):
    """D0059-AC-19: 札の表示名は段の行と同じく 80 文字で切る（100 文字なら 79 文字＋…）。"""
    label = "あ" * 100
    _r, got = look(node, html, snapshot([stage("a", "review", label=label)]), ".badge", ".stage .label")
    assert texts(got[".badge"]) == [BADGE_WORD + "あ" * 79 + "…"]
    assert texts(got[".stage .label"]) == ["あ" * 79 + "…"]


# ---- AC-21 まだの語 ---------------------------------------------------------------------------------------------


def test_d0059_ac21_waiting_word_is_mada(node, html):
    """D0059-AC-21: status が waiting の段の語は「まだ」。「待ち」だけの語の行が無い。確認待ちは「確認待ち」、ほかの状態の語も今のまま。"""
    _r, got = look(node, html, with_review("waiting", "running", "review", "done", "failed", "revised"), ".word", ".s-waiting .word", ".s-review .word")
    words = texts(got[".word"])
    assert "待ち" not in words, words
    assert texts(got[".s-waiting .word"]) == ["まだ"]
    assert texts(got[".s-review .word"]) == ["確認待ち"]
    assert words == ["まだ", "実行中", "確認待ち", "完了", "失敗", "差し戻し"]


# ---- AC-23〜26 回数 ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["done", "running", "review"])
def test_d0059_ac23_first_attempt_is_not_shown(node, html, status):
    """D0059-AC-23: attempt が 1 の段（完了・動いている・確認待ち）の行に「回目」が出ない（.attempt の要素を作らない）。"""
    r, got = look(node, html, one_stage(status, attempt=1), ".attempt")
    assert got[".attempt"] == []
    assert "回目" not in r["steps"][0]["view"]["text"]


@pytest.mark.parametrize("attempt,shown", [(2, "2回目"), (999, "999回目")])
def test_d0059_ac24_second_attempt_and_later_are_shown(node, html, attempt, shown):
    """D0059-AC-24: attempt が 2 の段に「2回目」、999 の段に「999回目」が出る。"""
    _r, got = look(node, html, one_stage("done", attempt=attempt), ".attempt")
    assert texts(got[".attempt"]) == [shown]


@pytest.mark.parametrize("attempt", [None, 0, -1, 1000, 1.5, "2", True], ids=lambda v: repr(v))
def test_d0059_ac25_odd_attempts_are_not_shown(node, html, attempt):
    """D0059-AC-25: attempt が null・0・負・1000 以上・小数・文字・真偽の段では「回目」を出さない（okAttempt の扱いのまま）。"""
    r, got = look(node, html, one_stage("done", attempt=attempt), ".attempt")
    assert got[".attempt"] == []
    assert "回目" not in r["steps"][0]["view"]["text"]


def _approve_upto_red(rec) -> None:
    rec.start("足したい機能のメモ", name="回数のセッション")
    for name in ("requirements", "design", "red"):
        rec.begin(name, agent="pipe-in-analyst")
        rec.done(name, summary="段を終えた")
        rec.wait(name)
        rec.review(name, "approved")


def _snapshot_of(work: Path) -> dict:
    state = live.read_state(work)
    assert state is not None, "記録が読めない"
    return live.build_snapshot(state, live.read_open_at(work, state), now=ls.NOW, local_tz=ls.UTC)


def test_d0059_ac26_real_recorder_attempt_one_shows_no_count(node, html, tmp_path):
    """D0059-AC-26: 本物の Recorder で実装を --attempt 1 で始めて閉じ、検証を --attempt 1 で動かしている記録の写しを描くと、どの行にも「1回目」が出ない。"""
    rec = ls.recorder(tmp_path, datetime(2026, 10, 17, 10, 0, 0))
    _approve_upto_red(rec)
    rec.begin("implement", attempt=1, agent="pipe-in-implementer")
    rec.done("implement", summary="実装した")
    rec.begin("test", attempt=1, agent="pipe-in-verifier")
    snap = _snapshot_of(ls.work_of(tmp_path))
    by_name = {s["name"]: s for s in snap["stages"]}
    assert by_name["implement"]["attempt"] == 1 and by_name["test"]["attempt"] == 1, "前提：写しの attempt が 1"
    assert by_name["test"]["status"] == "running"
    r, got = look(node, html, snap, ".attempt")
    assert got[".attempt"] == []
    assert "1回目" not in r["steps"][0]["view"]["text"]


def test_d0059_ac26_real_recorder_second_attempt_shows_two(node, html, tmp_path):
    """D0059-AC-26: 同じ記録で実装を --attempt 2 でやり直すと、実装の行に「2回目」が出る（ほかの行には回数が出ない）。"""
    rec = ls.recorder(tmp_path, datetime(2026, 10, 17, 10, 0, 0))
    _approve_upto_red(rec)
    rec.begin("implement", attempt=1, agent="pipe-in-implementer")
    rec.done("implement", summary="実装した")
    rec.begin("implement", attempt=2, agent="pipe-in-implementer")
    snap = _snapshot_of(ls.work_of(tmp_path))
    assert {s["name"]: s for s in snap["stages"]}["implement"]["attempt"] == 2, "前提：写しの attempt が 2"
    _r, got = look(node, html, snap, ".attempt", ".s-running .attempt")
    assert texts(got[".attempt"]) == ["2回目"]
    assert texts(got[".s-running .attempt"]) == ["2回目"]


# ---- AC-27・29 守りと前の版 -----------------------------------------------------------------------------------


def test_d0059_ac27_new_parts_add_no_style_attribute_or_html(node, html):
    """D0059-AC-27: 新しい部品（時刻・札・合計・帯）を描いたあとも、style の属性ができず（幅は CSSOM の style.width だけ）、HTML の差し込みが 0。"""
    r, got = look(node, html, with_review("done", "review", "waiting"), ".bar > span", ".summary > *", ".updated")
    view = r["steps"][0]["view"]
    assert "style" not in view["attrs"], view["attrs"]
    assert view["html_insertions"] == 0
    assert widths(got[".bar > span"]) == ["33.3333%", "", "33.3333%"], "幅は style.width で入っている"
    assert len(got[".summary > *"]) >= 2 and len(got[".updated"]) == 1


@pytest.mark.parametrize("shape", ["no_review_key", "minimal"])
def test_d0059_ac29_old_snapshots_render_with_the_new_parts(node, html, shape):
    """D0059-AC-29: 前の版の写し（review のキーが無い・attempt が 1 の段・empty/name/final の無い最小の形）でも例外が無く、札・合計・帯・時刻が決まりどおりに出る。"""
    rows = [stage("requirements", "done", attempt=1, duration_sec=60), stage("design", "review", label="設計", attempt=1, pending_since=iso(5)), stage("red")]
    snap = snapshot(rows, generated_at=AT_0340)
    snap.pop("review", None)
    if shape == "minimal":
        snap = {"schema": 1, "generated_at": AT_0340, "stages": rows}
    r, got = look(node, html, snap, ".badge", ".total", ".bar > span", ".updated", ".attempt")
    assert r["listener_errors"] == [] and r["console_errors"] == []
    assert texts(got[".badge"]) == ["確認待ち：設計"]
    assert texts(got[".total"]) == ["合計 1:00"]
    assert list(zip(classes(got[".bar > span"]), widths(got[".bar > span"]))) == [("bar-done", "33.3333%"), ("bar-gap", ""), ("bar-pending", "33.3333%")]
    assert texts(got[".updated"]) == ["03:40 更新"]
    assert got[".attempt"] == []


# ---- 並び・tick の守り ----------------------------------------------------------------------------------------


def _ident(e: dict) -> str:
    a = e["attrs"]
    if a.get("id"):
        return f"{e['tag']}#{a['id']}"
    return f"{e['tag']}.{a['class']}" if a.get("class") else e["tag"]


def test_d0059_page_order_after_render(node, html):
    """D0059: 描いたあとの並びは h1 → p.updated → #name → #final → #msg → div.summary → #stages。.summary の子は badge・total・bar の順。"""
    snap = snapshot([stage("a", "done", duration_sec=60), stage("b", "review", label="設計", pending_since=iso(5)), stage("c")])
    _r, got = look(node, html, snap, "main > *", ".summary > *")
    assert [_ident(e) for e in got["main > *"]] == ["h1", "p.updated", "p#name", "p#final", "p#msg", "div.summary", "ol#stages"]
    assert classes(got[".summary > *"]) == ["badge", "total", "bar"]


def test_d0059_tick_does_not_rebuild_the_top(node, html):
    """D0059: 1秒ごとの tick では、上の部品を作り直さない（作った要素の数が増えない。D0027-AC-60 の形）。合計と時刻の文字も変わらない。"""
    r = go(node, html, steps=[*sending(counting_snapshot()), q(".summary > *"), q(".total"), {"op": "advance", "ms": 1000}, {"op": "advance", "ms": 30000},
                              q(".total"), q(".updated")])
    assert classes(r["steps"][1]["result"]) == ["badge", "total", "bar"]
    created = [len(r["steps"][i]["view"]["created"]) for i in (0, 3, 4)]
    assert created[0] == created[1] == created[2], created
    assert texts(r["steps"][5]["result"]) == texts(r["steps"][2]["result"]) == ["合計 $0.5 ・ 3ターン ・ 0:12"]
    assert texts(r["steps"][6]["result"]) == ["02:00 更新"]
