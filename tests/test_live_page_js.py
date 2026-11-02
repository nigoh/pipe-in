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

from pipe_in.engine import live_page

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


def run_scene(node_path: str, page_html: str, tz: str = "UTC", **scene) -> dict:
    """tz は台の node の時刻帯（環境変数 TZ。子プロセスだけに足す）。手元の時刻帯で結果が変わらないよう、既定は UTC。"""
    scene["html"] = page_html
    proc = subprocess.run(
        [node_path, str(HARNESS)], input=json.dumps(scene).encode("utf-8"), capture_output=True, timeout=120, cwd=str(ROOT),
        env={**os.environ, "TZ": tz},
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


def go(node, html, steps=None, *, tz="UTC", **opts):
    r = run_scene(node, html, tz=tz, steps=steps or [], **opts)
    assert r["load_error"] is None, r["load_error"]
    assert r["uncaught"] == [] and r["unhandled"] == [], (r["uncaught"], r["unhandled"])
    return r


def call(node, html, fn, *args, tz="UTC"):
    r = run_scene(node, html, tz=tz, steps=[{"op": "call", "fn": fn, "args": list(args)}])
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
    """D0027-AC-56: まだ（waiting）・終わり・失敗・差し戻しの段は数えない（started_at が残っていても）。"""
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
    """D0027-AC-59・D0059-AC-07・AC-08: セッション名と段の表示名が出て、状態は言葉（まだ・作業中・確認待ち・完了・失敗・差し戻し）とアイコン（svg）で出る（色だけで伝えない）。
    D0059 で、記号の字形をアイコンに、「待ち」「実行中」を「まだ」「作業中」に直した。"""
    snap = snapshot([stage("a", "waiting"), stage("b", "running", started_at=iso(5)), stage("c", "review", pending_since=iso(5)), stage("d", "done"),
                     stage("e", "failed"), stage("f", "revised")])
    r = go(node, html, steps=[*sending(snap), {"op": "query", "selector": ".stage .mark svg"}])
    text = r["steps"][0]["view"]["text"]
    assert GOOD_MARK in text
    for name in "abcdef":
        assert f"LABEL-{name}" in text
    assert len(r["steps"][1]["result"]) == 6, "段ごとにアイコン（svg）が1つ"
    for glyph in "✓✕↩":
        assert glyph not in text, glyph
    for word in ("まだ", "作業中", "確認待ち", "完了", "失敗", "差し戻し"):
        assert word in text, word


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
    # D0059：状態のアイコンの svg と path は、状態から決まった固定のものだけ（createElementNS）。外から来た文字で増えないことは D0059-AC-14 で確かめる
    forbidden = {"script", "img", "iframe", "a", "style", "link", "object", "embed", "form", "input", "button"}
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

# D0059：状態の言葉とアイコン。アイコンの形（d）は docs/design/canvas/LiveProgress.dc.html の LI と同じ（undo-2 だけ板に無く、Lucide 1.61.0 から写す）
WORDS = {"waiting": "まだ", "running": "作業中", "review": "確認待ち", "done": "完了", "failed": "失敗", "revised": "差し戻し", "unknown": "不明"}
UNDO_2 = "M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"
DESIGN_BOARD = ROOT / "docs" / "design" / "canvas" / "LiveProgress.dc.html"


def design_icons() -> dict[str, str]:
    """状態 → d の文字列。板（LiveProgress.dc.html の LI）から、undo-2 だけは Lucide から写した値（読むだけ）。"""
    text = DESIGN_BOARD.read_text(encoding="utf-8")
    found = re.search(r"const LI = (\{.*?\});", text, re.S)
    assert found, "板の LI（アイコンの形）が読めない"
    li = json.loads(found.group(1))
    return {"done": li["ok"], "running": li["spin"], "review": li["hand"], "waiting": li["minus"], "failed": li["x"], "revised": UNDO_2, "unknown": li["todo"]}


def one_stage(status: str, **kw) -> dict:
    extra = {"started_at": iso(5)} if status == "running" else {"pending_since": iso(5)} if status == "review" else {}
    extra.update(kw)
    return snapshot([stage("only", status, **extra)])


def query(node, html, snap, selector, *, tz="UTC"):
    r = go(node, html, tz=tz, steps=[*sending(snap), {"op": "query", "selector": selector}])
    return r["steps"][-1]["result"]


@pytest.mark.parametrize("status,word", list(WORDS.items()))
def test_d0059_ac07_status_words(node, html, status, word):
    """D0059-AC-07: 状態の言葉は、まだ（waiting）・作業中（running）・確認待ち（review）・完了（done）・失敗（failed）・差し戻し（revised）・不明（unknown）。"""
    snap = one_stage("weird" if status == "unknown" else status)
    assert [w["text"] for w in query(node, html, snap, ".stage .word")] == [word]


def test_d0059_ac07_no_bare_machi_label(node, html):
    """D0059-AC-07: 「待ち」だけの札（確認待ち以外）と、古い言葉「実行中」が、どの状態の画面にも出ない（「待ち」は人の判断を待つときの「確認待ち」だけ）。"""
    for status in WORDS:
        text = go(node, html, steps=sending(one_stage("weird" if status == "unknown" else status)))["steps"][0]["view"]["text"]
        assert "実行中" not in text, status
        for line in text.split("\n"):
            assert line != "待ち", (status, line)
            assert "待ち" not in line.replace("確認待ち", ""), (status, line)


@pytest.mark.parametrize("status", list(WORDS))
def test_d0059_ac08_row_mark_has_one_svg_and_the_word(node, html, status):
    """D0059-AC-08: 行の印（.mark）の中に svg が1つ（path が1本）入り、印は文字を持たず aria-hidden、言葉の span に状態の言葉が入る。印は行の最初の子。"""
    snap = one_stage("weird" if status == "unknown" else status)
    r = go(node, html, steps=[*sending(snap), {"op": "query", "selector": ".stage .mark"}, {"op": "query", "selector": ".stage .mark svg"},
                              {"op": "query", "selector": ".stage .mark path"}, {"op": "query", "selector": ".stage .word"}, {"op": "query", "selector": ".stage > span"}])
    marks, svgs, paths, words, spans = (s["result"] for s in r["steps"][1:])
    assert len(marks) == 1 and marks[0]["text"] == "", f"印に字形が残っている: {marks[0]['text'] if marks else None!r}"
    assert marks[0]["attrs"].get("aria-hidden") == "true"
    assert len(svgs) == 1 and len(paths) == 1
    assert svgs[0]["attrs"].get("aria-hidden") == "true"
    assert [w["text"] for w in words] == [WORDS[status]]
    assert "mark" in spans[0]["attrs"].get("class", "").split()


def test_d0059_ac08_icons_match_the_design(node, html):
    """D0059-AC-08: 7つの状態のアイコンの d が、板（LiveProgress.dc.html）と同じ（完了＝circle-check・作業中＝refresh-cw・確認待ち＝hand・まだ＝minus・失敗＝circle-x・差し戻し＝undo-2・不明＝circle-dashed）。"""
    for status, expected in design_icons().items():
        snap = one_stage("weird" if status == "unknown" else status)
        paths = query(node, html, snap, ".stage .mark path")
        assert [p["attrs"].get("d") for p in paths] == [expected], status


def test_d0059_ac08_each_status_has_its_own_icon(node, html):
    """D0059-AC-08: 7つの状態のアイコンの形は、どれも違う（色だけでなく形でも見分けられる）。"""
    shapes = {}
    for status in WORDS:
        snap = one_stage("weird" if status == "unknown" else status)
        paths = query(node, html, snap, ".stage .mark path")
        assert len(paths) == 1, status
        shapes[status] = paths[0]["attrs"].get("d")
    assert all(shapes.values()) and len(set(shapes.values())) == 7, shapes


@pytest.mark.parametrize("status", ["done", "running", "unknown"])
def test_d0059_ac08_svg_attributes(node, html, status):
    """D0059-AC-08: アイコンの svg は viewBox 0 0 24 24・fill none・stroke currentColor・stroke-width 2・丸い端と角・aria-hidden=true。外から来た文字は属性に入らない。"""
    snap = one_stage("weird" if status == "unknown" else status, label="<img src=x onerror=alert(1)>")
    found = query(node, html, snap, ".stage .mark svg")
    assert len(found) == 1, "行の印の中に svg が1つ無い"
    svg = found[0]["attrs"]
    assert svg.get("viewBox") == "0 0 24 24" and svg.get("fill") == "none" and svg.get("stroke") == "currentColor", svg
    assert svg.get("stroke-width") == "2" and svg.get("stroke-linecap") == "round" and svg.get("stroke-linejoin") == "round"
    assert svg.get("aria-hidden") == "true"
    assert not any("img" in str(v) or "onerror" in str(v) for v in svg.values())


def test_d0059_ac08_icons_are_made_only_in_the_svg_namespace(node, html):
    """D0059-AC-08: アイコンは createElementNS で、SVG の名前空間の svg と path だけを作る（台は別の名前空間なら投げる）。createElement(\"svg\") では作らない。"""
    rows = [stage(f"s{i}", st) for i, st in enumerate(WORDS)]
    r = go(node, html, steps=[*sending(snapshot(rows)), {"op": "query", "selector": ".stage .mark svg"}])
    view = r["steps"][0]["view"]
    assert len(r["steps"][1]["result"]) == 7, "行ごとに印の中に svg が1つ"
    assert view["created_ns"] and {tuple(x) for x in view["created_ns"]} <= {("http://www.w3.org/2000/svg", "svg"), ("http://www.w3.org/2000/svg", "path")}
    names = [t for _, t in view["created_ns"]]
    assert view["created"].count("svg") == names.count("svg") and view["created"].count("path") == names.count("path"), "createElement(\"svg\") で作っている"
    assert names.count("svg") >= 7 and names.count("path") == names.count("svg")
    assert view["html_insertions"] == 0


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
    """D0027-AC-86・D0059-AC-08: 行の class が s-<状態> のまま（CSS の色が .s-<状態> .mark で当たる）。"""
    for status in ("waiting", "running", "review"):
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


# ---- D0059：頭・札・合計・帯・数 -------------------------------------------------------------------------------


def text_of(node, html, snap, selector, *, tz="UTC"):
    """写しを届けたあと、selector に合う最初の要素の文字（無ければ None）。"""
    found = query(node, html, snap, selector, tz=tz)
    return found[0]["text"] if found else None


def mixed_snapshot(**top) -> dict:
    """完了2・確認待ち1・まだ2。"""
    return snapshot([stage("a", "done"), stage("b", "done"), stage("c", "review", pending_since=iso(40)), stage("d"), stage("e")], **top)


def test_d0059_harness_creates_svg_elements_and_rejects_other_namespaces(node):
    """D0059-AC-08: 台の自己検査。createElementNS は SVG の名前空間だけ許し、種類を created と created_ns に積む。それ以外の名前空間は投げる。"""
    page = """<!doctype html><html><body><p id="msg"></p><script>
var SVG = "http://www.w3.org/2000/svg";
async function main() {
  var s = document.createElementNS(SVG, "svg"); var p = document.createElementNS(SVG, "path");
  s.setAttribute("viewBox", "0 0 24 24"); p.setAttribute("d", "M0 0"); s.appendChild(p); document.getElementById("msg").appendChild(s);
}
main();
function other() { return document.createElementNS("http://www.w3.org/1999/xhtml", "div"); }
</script></body></html>"""
    r = run_scene(node, page, steps=[{"op": "call", "fn": "other", "args": []}, {"op": "query", "selector": "p svg path"}])
    assert r["load_error"] is None and r["uncaught"] == []
    assert r["loaded"]["created_ns"] == [["http://www.w3.org/2000/svg", "svg"], ["http://www.w3.org/2000/svg", "path"]]
    assert r["loaded"]["created"] == ["svg", "path"] and r["loaded"]["tags"] == {"p": 1, "svg": 1, "path": 1}
    assert "NamespaceError" in r["steps"][0]["threw"]
    assert r["steps"][1]["result"][0]["attrs"] == {"d": "M0 0"}


def test_d0059_ac10_band_has_one_segment_per_stage_with_state_classes(node, html):
    """D0059-AC-10: 完了2・確認待ち1・まだ2 の写しで、帯が5つの区切りに分かれ、それぞれに状態の class（seg-done・seg-review・seg-waiting）が付く。順は段の順。"""
    segs = query(node, html, mixed_snapshot(), ".band .seg")
    classes = [s["attrs"]["class"].split() for s in segs]
    assert len(segs) == 5
    assert [next(c for c in cs if c.startswith("seg-")) for cs in classes] == ["seg-done", "seg-done", "seg-review", "seg-waiting", "seg-waiting"]
    assert all("seg" in cs for cs in classes)


@pytest.mark.parametrize("status", list(WORDS))
def test_d0059_ac10_every_status_has_a_segment_class(node, html, status):
    """D0059-AC-10: 7つの状態のどれも、帯の区切りに seg-<状態> の class が付く（不明は seg-unknown）。"""
    snap = one_stage("weird" if status == "unknown" else status)
    segs = query(node, html, snap, ".band .seg")
    assert len(segs) == 1 and f"seg-{status}" in segs[0]["attrs"]["class"].split()


def test_d0059_ac10_counts_text(node, html):
    """D0059-AC-10: 帯の下に「完了 2 ・ 確認待ち 1 ・ まだ 2」と出る（0 の状態は出さない）。"""
    assert text_of(node, html, mixed_snapshot(), ".counts") == "完了 2 ・ 確認待ち 1 ・ まだ 2", "数の入れ物（.counts）が骨組みに無い、または文が違う"


def test_d0059_ac10_counts_order_is_fixed(node, html):
    """D0059-AC-10: 数の並びは 完了・確認待ち・作業中・失敗・差し戻し・まだ・不明 の順（写しの段の順に関わらない）。"""
    stages = [stage("g", "weird"), stage("f"), stage("e", "revised"), stage("d", "failed"), stage("c", "running", started_at=iso(5)), stage("b", "review", pending_since=iso(5)), stage("a", "done")]
    assert text_of(node, html, snapshot(stages), ".counts") == "完了 1 ・ 確認待ち 1 ・ 作業中 1 ・ 失敗 1 ・ 差し戻し 1 ・ まだ 1 ・ 不明 1"


def test_d0059_ac10_count_text_function(node, html):
    """D0059-AC-10: countText(stages) は状態ごとの数の文字。段が無ければ空。"""
    assert call(node, html, "countText", [{"status": "done"}, {"status": "done"}, {"status": "waiting"}]) == "完了 2 ・ まだ 1"
    assert call(node, html, "countText", []) == ""


def test_d0059_ac10_no_stages_no_band(node, html):
    """D0059-AC-10: 段が 0 件の写しでは、帯の区切りも数も札も出ない。前の写しの帯は残らない。"""
    r = go(node, html, steps=[*sending(mixed_snapshot()), {"op": "query", "selector": ".band .seg"}, *sending(snapshot([])),
                              {"op": "query", "selector": ".band .seg"}, {"op": "query", "selector": ".counts"}, {"op": "query", "selector": ".chips"}])
    assert len(r["steps"][1]["result"]) == 5, "区切りが描かれていない（先に帯を描く）"
    assert r["steps"][3]["result"] == []
    assert r["steps"][4]["result"][0]["text"] == ""
    assert r["steps"][5]["result"][0]["text"] == ""


def test_d0059_ac10_band_is_aria_hidden(node, html):
    """D0059-AC-10: 帯は aria-hidden="true"（同じ内容を下の文字が伝える）。"""
    bands = query(node, html, mixed_snapshot(), ".band")
    assert len(bands) == 1 and bands[0]["attrs"].get("aria-hidden") == "true"


@pytest.mark.parametrize("bad", [snapshot([], empty=True), {"schema": 2, "stages": []}, None, {"schema": 1}], ids=["empty", "schema2", "none", "no_stages"])
def test_d0059_ac20_empty_unreadable_and_unsupported_clear_the_new_parts(node, html, bad):
    """D0059-AC-20: 空・版違い・読めない写しでは、帯・数・札・更新の時刻も空になる（前の写しの分が残らない）。"""
    r = go(node, html, steps=[*sending(mixed_snapshot()), {"op": "query", "selector": ".band .seg"}, *sending(bad), {"op": "query", "selector": ".band .seg"},
                              {"op": "query", "selector": ".counts"}, {"op": "query", "selector": ".chips"}, {"op": "query", "selector": ".updated"}])
    assert len(r["steps"][1]["result"]) == 5
    assert r["steps"][3]["result"] == []
    assert [x["text"] for x in r["steps"][4]["result"] + r["steps"][5]["result"] + r["steps"][6]["result"]] == ["", "", ""]


def test_d0059_ac11_head_chip_prefers_review_then_running(node, html):
    """D0059-AC-11: 確認待ちの段があれば「確認待ち：<段の表示名>」の札（hand のアイコンつき）、無くて作業中の段があれば「作業中：<段の表示名>」。確認待ちが先。"""
    def chips_of(snap: dict) -> str:
        found = text_of(node, html, snap, ".chips")
        assert found is not None, "札の入れ物（.chips）が骨組みに無い"
        return found

    chips = chips_of(counting_snapshot())
    assert "確認待ち：LABEL-red" in chips and "作業中" not in chips
    only_running = snapshot([stage("a", "done"), stage("b", "running", started_at=iso(5)), stage("c")])
    chips = chips_of(only_running)
    assert "作業中：LABEL-b" in chips and "確認待ち" not in chips
    first_review = snapshot([stage("a", "review", pending_since=iso(5)), stage("b", "review", pending_since=iso(5))])
    chips = chips_of(first_review)
    assert "確認待ち：LABEL-a" in chips and "LABEL-b" not in chips


def test_d0059_ac11_head_chip_has_an_icon(node, html):
    """D0059-AC-11: 状態の札には、その状態のアイコン（確認待ち＝hand、作業中＝refresh-cw）が付く（札の中に svg が1つ）。"""
    icons = design_icons()
    for snap, status in ((counting_snapshot(), "review"), (snapshot([stage("b", "running", started_at=iso(5))]), "running")):
        paths = query(node, html, snap, ".chips svg path")
        assert [p["attrs"].get("d") for p in paths] == [icons[status]], status


def test_d0059_ac11_no_chip_without_either(node, html):
    """D0059-AC-11: 確認待ちも作業中も無ければ、状態の札は出ない（完了・まだ・失敗だけの写し）。"""
    snap = snapshot([stage("a", "done"), stage("b", "failed"), stage("c")])
    chips = text_of(node, html, snap, ".chips")
    assert chips is not None, "札の入れ物（.chips）が無い"
    assert "確認待ち" not in chips and "作業中" not in chips
    assert query(node, html, snap, ".chips svg") == []


def test_d0059_ac11_pick_head_function(node, html):
    """D0059-AC-11: pickHead(stages) は確認待ちが先、なければ作業中の最初の段 → {status, label}。どちらも無ければ null。"""
    review, running = {"status": "review", "label": "R"}, {"status": "running", "label": "N"}
    assert call(node, html, "pickHead", [running, review])["label"] == "R"
    assert call(node, html, "pickHead", [{"status": "running", "label": "A"}, running])["label"] == "A"
    assert call(node, html, "pickHead", [{"status": "done", "label": "D"}, {"status": "waiting", "label": "W"}]) is None
    assert call(node, html, "pickHead", []) is None


@pytest.mark.parametrize("final,shown", [("PASSED", "合格"), ("TEST_FAILED", "検証で不合格"), ("STOPPED_BY_HUMAN", "人が止めた"), ("BLOCKED", "進められない")])
def test_d0059_ac11_final_text(node, html, final, shown):
    """D0059-AC-11: 写しの final があれば「結果：…」（今の #final の文字）を出す。無ければ空。今のままで通る（#final の文字は変えない）。"""
    text = text_of(node, html, done_snapshot() | {"final": final}, "#final")
    assert text is not None and re.fullmatch(r"結果[:：] ?%s" % re.escape(shown), text), text
    assert text_of(node, html, snapshot([stage("a", "done")]), "#final") == ""


@pytest.mark.parametrize(
    "stages,expected",
    [
        ([{"cost": 1.5, "turns": 10, "duration": 600}, {"cost": 0.25, "turns": 21, "duration": 484}], "合計 $1.75 · 31 ターン · 18:04"),
        ([{"cost": 0.5, "turns": None, "duration": None}], "合計 $0.5"),
        ([{"cost": None, "turns": 3, "duration": 12.5}, {"cost": None, "turns": None, "duration": 30}], "合計 3 ターン · 0:42"),
        ([{"cost": 0, "turns": 0, "duration": 69.4}], "合計 1:09"),
        ([{"cost": 0, "turns": 0, "duration": 0}, {"cost": NAN, "turns": INF, "duration": NINF}, {"cost": -1, "turns": "x", "duration": True}], ""),
        ([{"cost": None, "turns": None, "duration": None}], ""),
        ([], ""),
    ],
    ids=["all_three", "cost_only", "turns_and_time", "zero_cost_turns", "nothing_summable", "nulls", "no_stages"],
)
def test_d0059_ac11_total_text(node, html, stages, expected):
    """D0059-AC-11: 合計は段の費用・ターン・時間を足して「合計 $1.75 · 31 ターン · 18:04」の形（時間は経過と同じ書き方）。正の数だけを足し、合計できる値が1つも無ければ空。"""
    assert call(node, html, "totalText", stages) == expected


def test_d0059_ac11_total_is_shown_next_to_the_chips(node, html):
    """D0059-AC-11: 画面の頭に「合計 …」が出る（足せる値があるとき）。無ければ .total の要素は空か無い。"""
    snap = snapshot([stage("a", "done", cost_usd=1.5, turns=10, duration_sec=600), stage("b", "done", cost_usd=0.25, turns=21, duration_sec=484), stage("c")])
    assert [t["text"] for t in query(node, html, snap, ".total")] == ["合計 $1.75 · 31 ターン · 18:04"]
    assert [t["text"] for t in query(node, html, snapshot([stage("a", "done"), stage("b")]), ".total")] in ([], [""])


def test_d0060_ac03_updated_time_follows_the_viewer_timezone(node, html):
    """D0060-AC-03: 写しの generated_at（2026-07-01T12:40:05+09:00）を、見ているブラウザの時刻帯に直して「HH:MM 更新」を出す（D0059-AC-12 を置き換え）。"""
    snap = snapshot([stage("a", "done")], generated_at="2026-07-01T12:40:05+09:00")
    assert text_of(node, html, snap, ".updated", tz="UTC") == "03:40 更新"
    assert text_of(node, html, snap, ".updated", tz="Asia/Tokyo") == "12:40 更新"
    assert text_of(node, html, snap, ".updated", tz="America/New_York") == "23:40 更新"


def test_d0060_ac03_harness_timezone_switch_takes_effect(node, html):
    """D0060-AC-03: 台の自己検査。TZ を UTC と Asia/Tokyo で切り替えると updatedText の答えが 9 時間ずれる（ずれなければ TZ が台に効いていない）。"""
    utc = call(node, html, "updatedText", "2026-07-01T12:40:05Z", tz="UTC")
    tokyo = call(node, html, "updatedText", "2026-07-01T12:40:05Z", tz="Asia/Tokyo")
    assert utc == "12:40 更新", utc
    assert tokyo == "21:40 更新", f"TZ の切り替えが効いていない: UTC={utc!r} Tokyo={tokyo!r}"


@pytest.mark.parametrize(
    "value,expected",
    [("2026-07-01T12:40:05+09:00", "03:40 更新"), ("2026-07-01T12:40:05Z", "12:40 更新"), ("2026-07-01T00:00:00+00:00", "00:00 更新"), ("2026-07-01T23:59:59.123-05:00", "04:59 更新"),
     (None, ""), ("", ""), ("abc", ""), (5, ""), ([], ""), ({}, ""), ("2026-07-01T12:40:05", ""), ("2026-07-01", ""), ("12:40", ""), (NAN, ""), (True, "")],
    ids=lambda v: repr(v)[:30],
)
def test_d0060_ac04_updated_text_function(node, html, value, expected):
    """D0060-AC-04: updatedText(generatedAt) は、ずれつき ISO（Z・小数秒・マイナスのずれも）なら TZ=UTC の時分で「HH:MM 更新」、合わなければ空（D0059-AC-12 を置き換え）。"""
    assert call(node, html, "updatedText", value, tz="UTC") == expected


@pytest.mark.parametrize(
    "value,tz,expected",
    [("2026-07-01T12:40:05Z", "Asia/Kolkata", "18:10 更新"), ("2026-07-01T15:00:00Z", "Asia/Tokyo", "00:00 更新"), ("2026-07-01T04:05:00Z", "UTC", "04:05 更新")],
    ids=["kolkata_half_hour", "tokyo_midnight", "two_digits"],
)
def test_d0060_ac04_half_hour_and_midnight_timezones(node, html, value, tz, expected):
    """D0060-AC-04: 30 分ずれる時刻帯でも合い、0 時台は「00」、時・分は 2 桁、24 時間表記（24: や午前・午後の印は出ない）。"""
    got = call(node, html, "updatedText", value, tz=tz)
    assert got == expected
    assert re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d 更新", got)


@pytest.mark.parametrize("bad", ["drop", None, 5, "abc", "2026-07-01T12:40:05", "2026-02-30T12:00:00+09:00"], ids=repr)
def test_d0059_ac12_bad_or_missing_generated_at_is_not_shown(node, html, bad):
    """D0059-AC-12 / D0060-AC-05: generated_at が無い・形が違う・日付として読めない（2月30日）ときは時刻を出さず（.updated は空）、ほかの表示（名前・段・言葉・アイコン）は壊れない。"""
    snap = snapshot([stage("a", "done")])
    if bad == "drop":
        del snap["generated_at"]
    else:
        snap["generated_at"] = bad
    r = go(node, html, steps=[*sending(snap), {"op": "query", "selector": ".updated"}, {"op": "query", "selector": ".stage .mark svg"}])
    assert [u["text"] for u in r["steps"][1]["result"]] == [""], "更新の時刻の入れ物（.updated）が骨組みに無い、または空でない"
    assert GOOD_MARK in r["steps"][0]["view"]["text"] and "LABEL-a" in r["steps"][0]["view"]["text"] and "完了" in r["steps"][0]["view"]["text"]
    assert len(r["steps"][2]["result"]) == 1


def test_d0059_ac20_old_snapshot_without_generated_at_renders(node, html):
    """D0059-AC-20: generated_at を持たない古い写し（D0027 の最初の形）でも、描き直しが失敗せず、名前・段・言葉・アイコン・帯・数が出る。"""
    old = {"schema": 1, "empty": False, "name": GOOD_MARK, "final": None, "stages": [stage("a", "done"), stage("b", "running", started_at=iso(5))]}
    r = go(node, html, steps=[*sending(old), {"op": "query", "selector": ".band .seg"}, {"op": "query", "selector": ".counts"}, {"op": "query", "selector": ".stage .mark svg"}])
    assert r["steps"][0]["threw"] is None
    text = r["steps"][0]["view"]["text"]
    assert GOOD_MARK in text and "LABEL-a" in text and "作業中" in text
    assert len(r["steps"][1]["result"]) == 2 and r["steps"][2]["result"][0]["text"] == "完了 1 ・ 作業中 1" and len(r["steps"][3]["result"]) == 2


@pytest.mark.parametrize("status", ["weird", "", "RUNNING", "__proto__", "constructor", 5, None])
def test_d0059_ac20_unknown_status_uses_the_dashed_circle(node, html, status):
    """D0059-AC-20: 状態が知らない文字・型違いの段は「不明」と circle-dashed のアイコンで描かれ、帯は seg-unknown になる。"""
    snap = snapshot([stage("only", status)])
    icons = design_icons()
    r = go(node, html, steps=[*sending(snap), {"op": "query", "selector": ".stage .mark path"}, {"op": "query", "selector": ".stage .word"}, {"op": "query", "selector": ".band .seg"}])
    assert [p["attrs"].get("d") for p in r["steps"][1]["result"]] == [icons["unknown"]]
    assert [w["text"] for w in r["steps"][2]["result"]] == ["不明"]
    assert "seg-unknown" in r["steps"][3]["result"][0]["attrs"]["class"].split()


def test_d0059_ac20_unsupported_and_empty_messages(node, html):
    """D0059-AC-20: schema が 1 でない写しは「この写しの版には対応していません」、空の写しは「まだ記録がありません」（D0027-AC-59 と同じ文）。今のままで通る部分を含む。"""
    r = go(node, html, steps=[*sending({"schema": 2, "stages": [stage("g", "done")]}), *sending(snapshot([], empty=True, name=None)), *sending(None)])
    assert UNSUPPORTED_MSG in r["steps"][0]["view"]["text"] and "LABEL-g" not in r["steps"][0]["view"]["text"]
    assert EMPTY_MSG in r["steps"][1]["view"]["text"] and EMPTY_MSG in r["steps"][2]["view"]["text"]


def test_d0059_ac13_elapsed_format_unchanged(node, html):
    """D0059-AC-13: 経過・所要時間の書き方は変わらない：0:00・3:10・1:02:03・99:59:59。今のままで通る（守り続ける検査。境目は D0027-AC-58）。"""
    for sec, shown in ((0, "0:00"), (190, "3:10"), (3723, "1:02:03"), (10**9, "99:59:59")):
        assert call(node, html, "fmtElapsed", sec) == shown
    text = go(node, html, steps=sending(counting_snapshot(190, 3723)))["steps"][0]["view"]["text"]
    assert shows(text, "3:10") and shows(text, "1:02:03")


HOSTILE_IMG = "<img src=x onerror=alert(1)>"


def test_d0059_ac14_hostile_text_stays_text_and_adds_only_fixed_icons(node, html):
    """D0059-AC-14: 名前・表示名・実行の名前に <img src=x onerror=…> が入っていても、文字として出るだけで要素は増えない。
    増えるのは状態から決まった svg と path（固定のアイコン）だけで、同じ形の無害な写しと要素の種類・数・属性・アイコンの形が同じ。"""
    def build(text: str) -> dict:
        return snapshot([stage("a", "running", label=text, started_at=iso(5)), stage("b", "review", label=text, pending_since=iso(5)), stage("c", "done", label=text)], name=text)

    h = go(node, html, steps=[*sending(build(HOSTILE_IMG)), {"op": "query", "selector": ".mark path"}, {"op": "query", "selector": ".chips"}])
    p = go(node, html, steps=[*sending(build("AAAA")), {"op": "query", "selector": ".mark path"}, {"op": "query", "selector": ".chips"}])
    hv, pv = h["steps"][0]["view"], p["steps"][0]["view"]
    assert hv["tags"].get("svg", 0) >= 3, "アイコン（svg）が描かれていない"
    assert hv["tags"] == pv["tags"] and hv["created"] == pv["created"] and hv["created_ns"] == pv["created_ns"] and hv["attrs"] == pv["attrs"]
    assert "img" not in hv["created"] and not [a for a in hv["attrs"] if a.startswith("on")] and hv["html_insertions"] == 0
    assert [x["attrs"] for x in h["steps"][1]["result"]] == [x["attrs"] for x in p["steps"][1]["result"]]
    assert sum(HOSTILE_IMG in line for line in hv["lines"]) >= 3, "文字としては見える"
    assert HOSTILE_IMG in h["steps"][2]["result"][0]["text"], "札にも文字として出る"
    assert h["alerts"] == []


def test_d0059_ac14_icon_shapes_do_not_depend_on_snapshot_text(node, html):
    """D0059-AC-14: アイコンの d は固定の定数で、写しの文字（status に入れた d の文字列など）は入らない。未知の status の文字は不明のアイコンになる。"""
    evil = "M0 0L9 9<script>alert(1)</script>"
    snap = snapshot([stage("a", evil, label=evil), stage("b", "done")], name=evil)
    r = go(node, html, steps=[*sending(snap), {"op": "query", "selector": ".mark path"}])
    paths = [p["attrs"].get("d") for p in r["steps"][1]["result"]]
    icons = design_icons()
    assert paths == [icons["unknown"], icons["done"]]


def test_d0027_ac88_stage_time_does_not_change_the_running_elapsed(node, html):
    """D0027-AC-88: 動いている段の経過（m:ss）は今のまま。終わった段の時間と並んでも、どちらも m:ss。"""
    r = go(node, html, steps=sending(counting_snapshot(83, 40)))
    text = r["steps"][0]["view"]["text"]
    assert shows(text, "1:23") and shows(text, "0:40") and "0:12" in text and "秒" not in text


# ---- D0060：「N回目」は2回目から・札の表示名は80文字 ----------------------------------------------------------


@pytest.mark.parametrize("attempt,shown", [(2, "2回目"), (3, "3回目"), (999, "999回目")], ids=lambda v: str(v))
def test_d0060_ac01_attempt_two_and_up_is_shown(node, html, attempt, shown):
    """D0060-AC-01: attempt が 2 以上の段（上限 999 まで）は「N回目」が出る。今のままで通る（2 以上は元から出ている）。"""
    found = query(node, html, snapshot([stage("a", "done", attempt=attempt)]), ".stage .attempt")
    assert [x["text"] for x in found] == [shown]


@pytest.mark.parametrize(
    "bad", [1, None, 0, -1, 1.5, NAN, "2", True, 1000, 10**30, [2], INF, NINF], ids=lambda v: repr(v)[:20],
)
def test_d0060_ac02_attempt_one_null_and_odd_values_are_not_shown(node, html, bad):
    """D0060-AC-02: attempt が 1・null・0・負・小数・NaN・文字・真偽・1000 以上・巨大な数・配列の段は「回目」の要素が出ず、画面に NaN・undefined・null も出ない。"""
    r = go(node, html, steps=[*sending(snapshot([stage("a", "done", attempt=bad)])), {"op": "query", "selector": ".stage .attempt"}])
    assert r["steps"][1]["result"] == [], "「回目」が出ている"
    text = r["steps"][0]["view"]["text"]
    assert "回目" not in text and "LABEL-a" in text
    assert not any(w in text for w in ("NaN", "undefined", "null"))


@pytest.mark.parametrize(
    "value,expected",
    [(1, None), (2, 2), (3, 3), (998, 998), (999, 999), (1000, None), (0, None), (-2, None), (2.5, None), (None, None), ("2", None), (True, None), ([], None), ({}, None), (NAN, None), (INF, None)],
    ids=lambda v: repr(v)[:20],
)
def test_d0060_ac02_ok_attempt_function(node, html, value, expected):
    """D0060-AC-02: okAttempt(v) は 2〜999 の整数だけ数をそのまま返し、ほかは null。"""
    assert call(node, html, "okAttempt", value) == expected


def chip_label(text: str, prefix: str) -> str:
    assert text.startswith(prefix), (prefix, text)
    return text[len(prefix):]


@pytest.mark.parametrize("status,prefix", [("review", "確認待ち："), ("running", "作業中：")], ids=["review", "running"])
def test_d0060_ac06_chip_label_is_cut_at_80_characters(node, html, status, prefix):
    """D0060-AC-06: 札の表示名は 80 文字ちょうどならそのまま、81 文字なら先頭 79 文字 + 「…」（札の表示名の部分が 80 文字）。前置きは数えず、変わらない。今のままで通る（checkSnapshot の clip が効いている。守り続ける検査）。"""
    kw = {"pending_since": iso(5)} if status == "review" else {"started_at": iso(5)}
    exact, over = "あ" * 80, "あ" * 81
    t80 = text_of(node, html, snapshot([stage("a", status, label=exact, **kw)]), ".chips .chip-text")
    t81 = text_of(node, html, snapshot([stage("a", status, label=over, **kw)]), ".chips .chip-text")
    assert chip_label(t80, prefix) == exact
    cut = chip_label(t81, prefix)
    assert cut == "あ" * 79 + "…" and len(cut) == 80


def test_d0060_ac06_chip_label_does_not_split_a_surrogate_pair(node, html):
    """D0060-AC-06: 79 文字目に絵文字（サロゲートペア）がまたがる表示名でも、壊れた文字（孤立したサロゲート）が出ない。今のままで通る。"""
    label = "あ" * 78 + "😀" * 3
    t = text_of(node, html, snapshot([stage("a", "review", label=label, pending_since=iso(5))]), ".chips .chip-text")
    cut = chip_label(t, "確認待ち：")
    assert cut == "あ" * 78 + "😀" + "…" and len(cut) == 80
    t.encode("utf-8")  # 孤立したサロゲートがあれば UnicodeEncodeError


def test_d0060_ac06_row_label_is_unchanged(node, html):
    """D0060-AC-06: 段の行（カード）の表示名は今のまま（80 文字をこえれば同じ clip で切る）。今のままで通る。"""
    r = go(node, html, steps=[*sending(snapshot([stage("a", "done", label="い" * 81), stage("b", "done", label="う" * 80)])), {"op": "query", "selector": ".stage .label"}])
    texts = [x["text"] for x in r["steps"][1]["result"]]
    assert texts == ["い" * 79 + "…", "う" * 80]
