"""D0044：進み具合のページの「答えのボタン」の動き。Node 22 以上があるときだけ、build_page() の本物の JS を node:vm で動かして確かめる。

台は tests/fixtures/live_page_harness.mjs（D0027 の台に、偽の claude.use("comments") と、押す・書く・終わらせる操作を足したもの）。
comments の口は公式の型定義で確かめた形：const c = await claude.use("comments")（使えない画面では null）・await c.canSendToClaude()
（"available" | "writers_only" | "no_session" | "off"）・await c.anchorFor(el)（非同期。{path, x, y} を返す）・await c.sendToClaude({anchor, text})
（人の操作の直後からだけ呼べる。失敗は reject）。ページはコメントを読めない。

Node が無い環境では全部 skip する（skip は成功に見えるので、検証では pytest -rs で skip が 0 件なのを見る）。
先頭の「台の自己検査」は、台そのものが動くこと（ページの出来に関係なく通る）を確かめる。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pipe_in.engine import live_answer as la
from pipe_in.engine import live_page

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "fixtures" / "live_page_harness.mjs"
UTC = timezone.utc
T0 = datetime(2026, 10, 17, 2, 0, 0, tzinfo=UTC)
ID1 = "a1b2c3d4e5"
ID2 = "0123456789"
ID3 = "ffffffffff"

WRITERS = "この画面からは答えを送れません（アーティファクトの編集者だけが送れます）。会話で答えてください。"
NO_SESSION = "答えを受け取れる Claude の会話が今ありません。会話で答えてください。"
OFF = "この画面では答えを送る機能が使えません。会話で答えてください。"
GENERIC = "この画面からは答えを送れません。会話で答えてください。"
FORBIDDEN = "この画面からは送れません（許可されていません）。会話で答えてください。"
CONSENT = "同意が確認できなかったため、送られていません。もう一度押すか、会話で答えてください。"
RATE = "続けて送りすぎです。少し待ってからやり直すか、会話で答えてください。"
FAILED = "送れませんでした。もう一度押すか、会話で答えてください。"
ANCHOR_FAILED = "場所を取れませんでした。会話で答えてください。"
ASK = {"approve": "この段を承認しますか", "revise": "この直してほしい点で差し戻しますか", "quit": "この実行を中止しますか"}
SENDING = "送っています…"
SENT = "送りました（会話の返事を待っています）"
INVALID = {"empty": "直してほしい点を書いてください", "too_long": "1000 文字以内にしてください", "bad_chars": "使えない文字（制御文字・見えない文字）が入っています"}
LABELS = {"approve": "承認", "revise": "直してほしい点を書いて差し戻す", "quit": "中止", "go": "実行する", "back": "戻る"}
FIXED_OR_NONE = {None, "", SENDING, SENT, WRITERS, NO_SESSION, OFF, GENERIC, FORBIDDEN, CONSENT, RATE, FAILED, ANCHOR_FAILED, *ASK.values(), *INVALID.values()}
WIRE = {"approve": "approved", "revise": "revise", "quit": "quit"}


def sid(value) -> str:
    return ascii(value)[:44]


# ---- 台を流す --------------------------------------------------------------------------------------------


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


def run_scene(node_path: str, page_html: str, **scene) -> dict:
    scene["html"] = page_html
    proc = subprocess.run([node_path, str(HARNESS)], input=json.dumps(scene).encode("utf-8"), capture_output=True, timeout=120, cwd=str(ROOT))
    try:
        result = json.loads(proc.stdout.decode("utf-8"))
    except ValueError:
        pytest.fail(f"台の出力が JSON でない: {proc.stdout[:500]!r} / stderr={proc.stderr[:2000]!r}")
    if "harness_error" in result:
        pytest.fail(f"台の誤り: {result['harness_error']}\n{result.get('stack')}")
    return result


# ---- 写しの見本 --------------------------------------------------------------------------------------------


def iso(seconds_ago: float) -> str:
    return (T0 - timedelta(seconds=seconds_ago)).isoformat(timespec="seconds")


def stage(name: str, status: str = "waiting", label: str | None = None, **kw) -> dict:
    d = {"name": name, "label": label if label is not None else f"LABEL-{name}", "status": status, "attempt": None, "started_at": None,
         "pending_since": None, "verdict": None, "cost_usd": None, "turns": None, "duration_sec": None}
    d.update(kw)
    return d


NO_KEY = object()
DEFAULT = object()


def snapshot(stages=None, *, review=DEFAULT, **top) -> dict:
    """既定は、要件定義・設計が完了、テスト先行が確認待ち（review はテスト先行・識別子 ID1）、実装・検証が待ちの写し。"""
    if stages is None:
        stages = [stage("requirements", "done", cost_usd=0.5), stage("design", "done"), stage("red", "review"), stage("implement"), stage("test")]
    s = {"schema": 1, "generated_at": T0.isoformat(timespec="seconds"), "empty": False, "name": "SESSION-NAME-MARK", "final": None, "stages": stages}
    if review is DEFAULT:
        s["review"] = {"stage": "red", "id": ID1}
    elif review is not NO_KEY:
        s["review"] = review
    s.update(top)
    return s


def reviewing(name: str, ident: str = ID1, **top) -> dict:
    """name の段が確認待ち（review も同じ）の写し。前の段は完了、後ろは待ち。"""
    names = ["requirements", "design", "red", "implement", "test"]
    if name not in names:
        names = [*names[:2], name, *names[3:]]
    pos = names.index(name)
    rows = [stage(n, "done" if i < pos else "review" if i == pos else "waiting") for i, n in enumerate(names)]
    return snapshot(rows, review={"stage": name, "id": ident}, **top)


def after_approval() -> dict:
    """赤が承認されて、実装が動いている写し（review は null）。"""
    return snapshot([stage("requirements", "done"), stage("design", "done"), stage("red", "done"), stage("implement", "running", started_at=iso(30)), stage("test")], review=None)


# ---- 画面を読む -------------------------------------------------------------------------------------------

SEL = {
    "panel": "div.review", "msg": "p.rv-msg", "input": "textarea.rv-input", "approve": "button.rv-approve", "revise": "button.rv-revise",
    "quit": "button.rv-quit", "go": "button.rv-go", "back": "button.rv-back",
}
PROBES = [{"op": "query", "selector": s} for s in SEL.values()]
ACTIONS = ("approve", "revise", "quit")


class Frame:
    """ある時点の、パネルの部品の様子。"""

    def __init__(self, results: list, view: dict):
        self.els = {name: (res[0] if res else None) for name, res in zip(SEL, results)}
        self.counts = {name: len(res) for name, res in zip(SEL, results)}
        self.view = view

    def shown(self, name: str) -> bool:
        e = self.els[name]
        return bool(e and e["shown"])

    def disabled(self, name: str) -> bool:
        e = self.els[name]
        return bool(e and e["disabled"])

    def active(self, name: str) -> bool:
        """見えていて、押せる（disabled でない）。"""
        return self.shown(name) and not self.disabled(name)

    def inert(self, name: str) -> bool:
        """押せない（見えない・止まっている）。"""
        return not self.active(name)

    def text(self, name: str) -> str | None:
        e = self.els[name]
        return None if e is None else e["text"]

    def value(self, name: str):
        e = self.els[name]
        return None if e is None else e["value"]

    def message(self) -> str | None:
        """見えている文の欄の文（無い・見えないなら None）。"""
        return self.text("msg") if self.shown("msg") else None

    def attrs(self, name: str) -> dict:
        e = self.els[name]
        return {} if e is None else e["attrs"]

    def signature(self) -> tuple:
        return tuple((n, self.shown(n), self.disabled(n), self.text(n) if n == "msg" else None, self.value(n) if n == "input" else None) for n in SEL)


@dataclass
class Run:
    r: dict
    frames: list[Frame]
    n_user_steps: int

    @property
    def sends(self) -> list[dict]:
        return self.r["comments"]["sends"]

    @property
    def anchors(self) -> list[dict]:
        return self.r["comments"]["anchor_calls"]

    @property
    def can_calls(self) -> int:
        return self.r["comments"]["can_calls"]

    @property
    def use_calls(self) -> list[str]:
        return self.r["db"]["use_calls"]

    @property
    def last(self) -> Frame:
        return self.frames[-1]

    def result(self, i: int):
        """i 番目の利用者の操作（0 始まり）の result。"""
        return self.r["steps"][len(PROBES) + i * (len(PROBES) + 1)]["result"]

    def step(self, i: int) -> dict:
        return self.r["steps"][len(PROBES) + i * (len(PROBES) + 1)]


def play(node_path: str, page_html: str, steps=(), *, snap=None, comments=DEFAULT, strict: bool = True, **scene) -> Run:
    """写し snap を購読の直後に届け、steps を順に行う。始めと各操作のあとに、パネルの部品を調べる。
    comments は偽の comments の設定（DEFAULT は {} = 使えて available。None なら comments の口が無い画面）。"""
    expanded = list(PROBES)
    for s in steps:
        expanded.append(s)
        expanded.extend(PROBES)
    if snap is not None:
        scene["initial"] = {"value": snap}
    if comments is DEFAULT:
        scene["comments"] = {}
    elif comments is not None:
        scene["comments"] = comments
    r = run_scene(node_path, page_html, steps=expanded, **scene)
    assert r["load_error"] is None, r["load_error"]
    frames = []
    for k in range(len(steps) + 1):
        base = k * (len(PROBES) + 1) if k else 0
        start = 0 if k == 0 else len(PROBES) + (k - 1) * (len(PROBES) + 1) + 1
        results = [r["steps"][start + j]["result"] for j in range(len(PROBES))]
        frames.append(Frame(results, r["steps"][start + len(PROBES) - 1]["view"]))
    if strict:
        assert r["uncaught"] == [] and r["unhandled"] == [], (r["uncaught"], r["unhandled"])
        assert r["listener_errors"] == [], r["listener_errors"]
        assert r["steps"][-1]["view"]["html_insertions"] == 0 and r["dialogs"] == []
        for st in r["steps"]:
            if st["threw"] and "pending でない" in st["threw"]:
                pytest.fail(f"終わらせる対象の呼び出しがまだ起きていない（ボタンがまだ無く、送信・確かめが始まっていない）: {st['threw']}")
            assert st["threw"] is None, st["threw"]
    return Run(r, frames, len(steps))


def click(name_or_selector: str, times: int = 1, force: bool = False) -> dict:
    return {"op": "click", "selector": SEL.get(name_or_selector, name_or_selector), "times": times, "force": force}


def typing(value: str, force: bool = False) -> dict:
    return {"op": "input", "selector": SEL["input"], "value": value, "force": force}


def send(value) -> dict:
    return {"op": "send", "value": value}


def query(selector: str) -> dict:
    return {"op": "query", "selector": selector}


# ---- 画面の状態の確認 -------------------------------------------------------------------------------------


def assert_no_ui(f: Frame, where: str = "") -> None:
    """ボタンも入力欄も文の欄も出ていない（見るだけ）。"""
    for name in ("panel", "input", "approve", "revise", "quit", "go", "back"):
        assert not f.shown(name), f"{where}{name} が見えている"
    assert f.message() in (None, ""), f"{where}文の欄に文が出ている: {f.message()!r}"


def assert_idle(f: Frame, where: str = "", *, message: str = "") -> None:
    """3つのボタンと入力欄が出ていて押せる。実行・戻るは見えない。文の欄は message（既定は空）。"""
    assert f.shown("panel"), f"{where}パネルが見えない"
    for name in ("approve", "revise", "quit", "input"):
        assert f.active(name), f"{where}{name} が押せない（shown={f.shown(name)} disabled={f.disabled(name)}）"
    for name in ("go", "back"):
        assert not f.shown(name), f"{where}{name} が見えている"
    if message == "":
        assert f.message() in (None, ""), f"{where}文が出ている: {f.message()!r}"
    else:
        assert f.message() == message, f"{where}{f.message()!r} != {message!r}"


def assert_blocked(f: Frame, text: str, where: str = "") -> None:
    """理由の文だけ。ボタンも入力欄も出ない。"""
    for name in ("input", "approve", "revise", "quit", "go", "back"):
        assert not f.shown(name), f"{where}{name} が見えている"
    assert f.message() == text, f"{where}{f.message()!r} != {text!r}"


def assert_confirm(f: Frame, action: str, where: str = "") -> None:
    assert f.shown("panel"), where
    assert f.active("go") and f.active("back"), f"{where}実行・戻るが押せない"
    for name in ACTIONS:
        assert f.inert(name), f"{where}{name} がまだ押せる"
    assert f.message() == ASK[action], f"{where}{f.message()!r}"


def assert_stopped(f: Frame, message: str, where: str = "") -> None:
    """3つのボタンと入力欄が止まっている（disabled）。実行・戻るは押せない。"""
    assert f.shown("panel"), where
    for name in (*ACTIONS, "input"):
        assert f.disabled(name), f"{where}{name} が止まっていない"
    assert f.inert("go") and f.inert("back"), where
    assert f.message() == message, f"{where}{f.message()!r} != {message!r}"


# ================================================================================================
# 台の自己検査（ページの出来に関係なく通る）
# ================================================================================================

REFERENCE_PAGE = """<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>t</title></head><body>
<p id="msg"></p><button id="go" type="button">go</button><button id="off" type="button" disabled>off</button>
<div id="wrap" hidden><button id="inner" type="button">inner</button></div><div id="outer"><button id="deep" type="button">deep</button></div>
<textarea id="t" class="box" maxlength="5"></textarea><textarea id="u" class="box" disabled></textarea><div id="move"></div>
<script>
var c = null; var held = null; var log = [];
function show(t) { document.getElementById("msg").textContent = t; }
async function main() {
  try { c = await claude.use("comments"); } catch (e) { c = null; log.push("use-failed"); }
  show(c ? "have" : "none");
}
main();
function doCan() { c.canSendToClaude().then(function (v) { show("can:" + JSON.stringify(v) + ":" + typeof v); }, function () { show("can-rejected"); }); }
function doCanSync() { show("sync:" + String(c.canSendToClaude)); c.canSendToClaude(); }
function doAnchor() { c.anchorFor(document.getElementById("go")).then(function (a) { held = a; show("anchor:" + a.token); }, function (e) { show("anchor-rejected:" + (e && e.code)); }); }
function doAnchorThrow() { try { c.anchorFor(document.getElementById("go")); } catch (e) { show("anchor-threw"); } }
function doAnchorString() { c.anchorFor(document.getElementById("go")).then(function (a) { held = a; show("anchor:" + typeof a); }); }
function doSend(text) { return c.sendToClaude({ anchor: held, text: text }).then(function () { show("sent:" + text); }, function (e) { show("send-rejected:" + (e && e.code) + ":" + (e && e.message)); }); }
function doSendThrows() { try { c.sendToClaude({ anchor: held, text: "t" }); } catch (e) { show("send-threw"); } }
function doSendWrongAnchor() { c.sendToClaude({ anchor: { token: "ANCHOR-TOKEN-1", path: "forged" }, text: "forged" }); }
function doConfirm() { return confirm("sure?"); }
document.getElementById("go").addEventListener("click", function () { doSend("sync"); });
document.getElementById("deep").addEventListener("click", function () { show("deep-clicked"); });
document.getElementById("outer").addEventListener("click", function (ev) { log.push("outer:" + ev.target.id); });
document.getElementById("inner").addEventListener("click", function () { show("inner-clicked"); });
document.getElementById("off").addEventListener("click", function () { show("off-clicked"); });
document.getElementById("t").addEventListener("input", function (ev) { show("input:" + ev.target.value.length); });
document.addEventListener("click", function () { log.push("doc"); });
</script></body></html>"""


def test_d0044_harness_records_the_comments_calls(node):
    """D0044-AC-37: 台の自己検査。偽の comments が、canSendToClaude・anchorFor・sendToClaude の呼び出しを記録し、押した操作の中で呼ばれたか（in_gesture）、発行した anchor そのものか（anchor_issued）を区別する。"""
    r = run_scene(node, REFERENCE_PAGE, comments={}, steps=[
        {"op": "call", "fn": "doCan", "args": []},
        {"op": "call", "fn": "doAnchor", "args": []},
        {"op": "click", "selector": "#go"},
        {"op": "call", "fn": "doSendWrongAnchor", "args": []},
        {"op": "call", "fn": "doSend", "args": ["outside-gesture"]},
    ])
    assert r["load_error"] is None and r["uncaught"] == [] and r["unhandled"] == []
    c = r["comments"]
    assert r["db"]["use_calls"] == ["comments"] and c["use_calls"] == 1 and c["can_calls"] == 1
    assert "can:\"available\":string" in r["steps"][0]["view"]["text"]
    assert c["anchor_calls"] == [{"el_tag": "button", "el_class": "", "attached": True}]
    first, forged, plain = c["sends"]
    assert first["text"] == "sync" and first["in_gesture"] is True and first["anchor_issued"] is True and first["keys"] == ["anchor", "text"] and first["argc"] == 1
    assert first["anchor"]["token"] == "ANCHOR-TOKEN-1" and first["anchor"]["x"] == 1 and first["anchor"]["y"] == 2 and isinstance(first["anchor"]["path"], str)
    assert forged["text"] == "forged" and forged["anchor_issued"] is False and forged["in_gesture"] is False
    assert plain["text"] == "outside-gesture" and plain["in_gesture"] is False and plain["anchor_issued"] is True and [s["n"] for s in c["sends"]] == [0, 1, 2]


def test_d0044_harness_in_gesture_is_false_after_an_await(node):
    """D0044-AC-37: 台の自己検査。クリックの中で await を挟んでから sendToClaude を呼ぶと in_gesture が偽になり、挟まなければ真になる（ページの await の有無を台が見分ける）。"""
    page = REFERENCE_PAGE.replace('document.getElementById("go").addEventListener("click", function () { doSend("sync"); });', 'document.getElementById("go").addEventListener("click", async function () { await Promise.resolve(); doSend("after-await"); });')
    r = run_scene(node, page, comments={}, steps=[{"op": "click", "selector": "#go"}])
    assert r["comments"]["sends"][0]["text"] == "after-await" and r["comments"]["sends"][0]["in_gesture"] is False


def test_d0044_harness_use_modes(node):
    """D0044-AC-34: 台の自己検査。claude.use("comments") が null・reject・throw・undefined・設定なし（前の版の場面）を作れて、呼んだ回数を数える。"""
    for cfg, text in [({"use": "null"}, "none"), ({"use": "rejects"}, "none"), ({"use": "throws"}, "none"), ({"use": "undefined"}, "none"), ({"use": "ok"}, "have"), ({}, "have"), (None, "none")]:
        scene = {} if cfg is None else {"comments": cfg}
        r = run_scene(node, REFERENCE_PAGE, **scene)
        assert r["load_error"] is None and r["comments"]["use_calls"] == 1, cfg
        assert text in r["loaded"]["lines"], (cfg, r["loaded"]["lines"])
        assert r["db"]["use_calls"] == ["comments"]
    r = run_scene(node, REFERENCE_PAGE, claude="null", comments={})
    assert "none" in r["loaded"]["lines"], "claude.use が null を返す画面では comments も null"


@pytest.mark.parametrize(
    "can,expected",
    [
        ("available", 'can:"available":string'),
        ("writers_only", 'can:"writers_only":string'),
        ("no_session", 'can:"no_session":string'),
        ("off", 'can:"off":string'),
        ("whatever", 'can:"whatever":string'),
        (None, "can:null:object"),
        (5, "can:5:number"),
        (True, "can:true:boolean"),
        ({"a": 1}, 'can:{"a":1}:object'),
        ([1, 2], "can:[1,2]:object"),
        ({"$": "reject"}, "can-rejected"),
        ({"$": "undefined"}, "can:undefined:undefined"),
    ],
    ids=sid,
)
def test_d0044_harness_can_modes(node, can, expected):
    """D0044-AC-35: 台の自己検査。canSendToClaude の返す値（文字列・null・数・真偽・オブジェクト・undefined・reject）を作れる。"""
    r = run_scene(node, REFERENCE_PAGE, comments={"can": can}, steps=[{"op": "call", "fn": "doCan", "args": []}])
    assert expected in r["steps"][0]["view"]["lines"], r["steps"][0]["view"]["lines"]


def test_d0044_harness_can_throw_set_can_and_pending(node):
    """D0044-AC-35: 台の自己検査。canSendToClaude が同期で投げる場面・set_can で次の値を替える操作・pending（settle_can で終わらせる）を作れる。"""
    r = run_scene(node, REFERENCE_PAGE, comments={"can": {"$": "throw"}}, steps=[{"op": "call", "fn": "doCanSync", "args": []}])
    assert r["steps"][0]["threw"] and "canSendToClaude threw" in r["steps"][0]["threw"]
    r = run_scene(node, REFERENCE_PAGE, comments={"can": "off"}, steps=[
        {"op": "call", "fn": "doCan", "args": []}, {"op": "set_can", "value": "available"}, {"op": "call", "fn": "doCan", "args": []},
    ])
    assert 'can:"off":string' in r["steps"][0]["view"]["lines"] and 'can:"available":string' in r["steps"][2]["view"]["lines"]
    r = run_scene(node, REFERENCE_PAGE, comments={"can": "pending"}, steps=[
        {"op": "call", "fn": "doCan", "args": []}, {"op": "call", "fn": "doCan", "args": []},
        {"op": "settle_can", "call": 1, "value": "no_session"}, {"op": "settle_can", "call": 0, "value": {"$": "reject"}},
    ])
    assert r["comments"]["can_calls"] == 2 and r["comments"]["pending_can"] == 2
    assert 'can:"no_session":string' in r["steps"][2]["view"]["lines"] and "can-rejected" in r["steps"][3]["view"]["lines"]


def test_d0044_harness_anchor_modes(node):
    """D0044-AC-39: 台の自己検査。anchorFor が reject・同期で投げる・オブジェクトでない値を返す・pending（settle_anchor）を作れる。"""
    r = run_scene(node, REFERENCE_PAGE, comments={"anchor": "rejects"}, steps=[{"op": "call", "fn": "doAnchor", "args": []}])
    assert "anchor-rejected:invalid" in r["steps"][0]["view"]["lines"]
    r = run_scene(node, REFERENCE_PAGE, comments={"anchor": "throws"}, steps=[{"op": "call", "fn": "doAnchorThrow", "args": []}])
    assert "anchor-threw" in r["steps"][0]["view"]["lines"]
    r = run_scene(node, REFERENCE_PAGE, comments={"anchor": "not_an_object"}, steps=[{"op": "call", "fn": "doAnchorString", "args": []}])
    assert "anchor:string" in r["steps"][0]["view"]["lines"]
    r = run_scene(node, REFERENCE_PAGE, comments={"anchor": "pending"}, steps=[
        {"op": "call", "fn": "doAnchor", "args": []}, {"op": "call", "fn": "doAnchor", "args": []},
        {"op": "settle_anchor", "call": 1, "how": "resolve"}, {"op": "settle_anchor", "call": 0, "how": "reject"},
    ])
    assert r["comments"]["pending_anchor"] == 2
    assert "anchor:ANCHOR-TOKEN-1" in r["steps"][2]["view"]["lines"] and "anchor-rejected:invalid" in r["steps"][3]["view"]["lines"]


def test_d0044_harness_send_modes(node):
    """D0044-AC-39: 台の自己検査。sendToClaude が resolve・pending（settle で終わらせる）・reject（値／コード）・同期で投げる・呼ぶたびに替わる配列を作れる。"""
    steps = [{"op": "call", "fn": "doSend", "args": ["a"]}]
    assert "sent:a" in run_scene(node, REFERENCE_PAGE, comments={}, steps=steps)["steps"][0]["view"]["lines"]
    r = run_scene(node, REFERENCE_PAGE, comments={"send": {"reject_code": "claude_unavailable"}}, steps=steps)
    assert "send-rejected:claude_unavailable:REJECT-MESSAGE-SECRET" in r["steps"][0]["view"]["lines"]
    r = run_scene(node, REFERENCE_PAGE, comments={"send": {"reject": {"code": "x", "message": "m"}}}, steps=steps)
    assert "send-rejected:x:m" in r["steps"][0]["view"]["lines"]
    r = run_scene(node, REFERENCE_PAGE, comments={"send": {"reject": "plain"}}, steps=steps)
    assert "send-rejected:undefined:undefined" in r["steps"][0]["view"]["lines"]
    r = run_scene(node, REFERENCE_PAGE, comments={"send": {"reject": {"$": "undefined"}}}, steps=steps)
    assert "send-rejected:undefined:undefined" in r["steps"][0]["view"]["lines"] and r["uncaught"] == [] and r["unhandled"] == []
    r = run_scene(node, REFERENCE_PAGE, comments={"send": "throws"}, steps=[{"op": "call", "fn": "doSendThrows", "args": []}])
    assert "send-threw" in r["steps"][0]["view"]["lines"]
    r = run_scene(node, REFERENCE_PAGE, comments={"send": "pending"}, steps=[
        {"op": "call", "fn": "doSend", "args": ["p0"]}, {"op": "call", "fn": "doSend", "args": ["p1"]},
        {"op": "settle", "call": 1, "how": "resolve"}, {"op": "settle", "call": 0, "how": {"reject": {"code": "late"}}},
    ])
    assert r["comments"]["pending_sends"] == 2
    assert "sent:p1" in r["steps"][2]["view"]["lines"] and "send-rejected:late:undefined" in r["steps"][3]["view"]["lines"]
    r = run_scene(node, REFERENCE_PAGE, comments={"send": [{"reject_code": "rate_limited"}, "resolve"]}, steps=[
        {"op": "call", "fn": "doSend", "args": ["x"]}, {"op": "call", "fn": "doSend", "args": ["y"]}, {"op": "call", "fn": "doSend", "args": ["z"]},
    ])
    assert "send-rejected:rate_limited:REJECT-MESSAGE-SECRET" in r["steps"][0]["view"]["lines"] and "sent:y" in r["steps"][1]["view"]["lines"] and "sent:z" in r["steps"][2]["view"]["lines"]


def test_d0044_harness_click_rules(node):
    """D0044-AC-38: 台の自己検査。click は、disabled の要素・hidden の要素（自分か祖先）には（force が偽なら）押さず、times 回続けて押し、親へ伝わり、見つからなければ found が偽。"""
    r = run_scene(node, REFERENCE_PAGE, steps=[
        {"op": "click", "selector": "#off"},
        {"op": "click", "selector": "#inner"},
        {"op": "click", "selector": "#inner", "force": True},
        {"op": "click", "selector": "#deep", "times": 3},
        {"op": "click", "selector": "#nothing"},
        {"op": "click", "selector": "#off", "times": 2, "force": True},
    ])
    res = [s["result"] for s in r["steps"]]
    assert res[0] == {"found": True, "dispatched": 0, "skipped": 1}
    assert res[1] == {"found": True, "dispatched": 0, "skipped": 1}
    assert res[2] == {"found": True, "dispatched": 1, "skipped": 0}
    assert res[3] == {"found": True, "dispatched": 3, "skipped": 0}
    assert res[4] == {"found": False, "dispatched": 0, "skipped": 0}
    assert res[5] == {"found": True, "dispatched": 2, "skipped": 0}
    assert "inner-clicked" in r["steps"][2]["view"]["lines"] and "off-clicked" in r["steps"][5]["view"]["lines"]
    assert r["listener_errors"] == [] and r["uncaught"] == []


def test_d0044_harness_click_bubbles_and_flags_the_gesture(node):
    """D0044-AC-37: 台の自己検査。click は親・文書へ伝わる（イベントの委譲を使うページも動く）。押している間だけ gesture の旗が立つ。"""
    r = run_scene(node, REFERENCE_PAGE, comments={}, steps=[{"op": "click", "selector": "#deep"}, {"op": "call", "fn": "doSend", "args": ["x"]}])
    assert "deep-clicked" in r["steps"][0]["view"]["lines"]
    assert r["comments"]["sends"][0]["in_gesture"] is False
    r = run_scene(node, REFERENCE_PAGE, steps=[{"op": "click", "selector": "#deep", "times": 2}, {"op": "call", "fn": "eval", "args": ["log.join(',')"]}])
    assert r["steps"][1]["threw"] is None and r["steps"][1]["result"] == "outer:deep,doc,outer:deep,doc", "親・文書の順に伝わる"


def test_d0044_harness_input_focus_and_selection(node):
    """D0044-AC-40: 台の自己検査。input は .value を替えて input を送り（disabled・hidden には届かない）、focus は見える・押せる要素だけに効き、要素を動かすと focus が外れ、選択範囲を覚える。"""
    r = run_scene(node, REFERENCE_PAGE, steps=[
        {"op": "input", "selector": "#t", "value": "hello"},
        {"op": "input", "selector": "#u", "value": "x"},
        {"op": "input", "selector": "#u", "value": "forced", "force": True},
        {"op": "focus_state"},
        {"op": "focus", "selector": "#t"},
        {"op": "focus_state"},
        {"op": "select", "selector": "#t", "start": 1, "end": 3},
        {"op": "query", "selector": "#t"},
        {"op": "focus", "selector": "#u"},
        {"op": "focus_state"},
        {"op": "focus", "selector": "#inner"},
        {"op": "focus_state"},
        {"op": "call", "fn": "eval", "args": ["(document.getElementById('move').appendChild(document.getElementById('t')), 1)"]},
        {"op": "focus_state"},
        {"op": "query", "selector": "#t"},
    ])
    s = [x["result"] for x in r["steps"]]
    assert s[0] == {"found": True, "dispatched": 1, "skipped": 0} and "input:5" in r["steps"][0]["view"]["lines"]
    assert s[1] == {"found": True, "dispatched": 0, "skipped": 1} and s[2]["dispatched"] == 1
    assert s[3] == {"tag": "body", "class": ""}
    assert s[5] == {"tag": "textarea", "class": "box"}
    assert s[7][0]["value"] == "hello" and s[7][0]["selection"] == [1, 3] and s[7][0]["focused"] is True
    assert s[9] == {"tag": "textarea", "class": "box"}, "disabled には focus が移らない"
    assert s[11] == {"tag": "textarea", "class": "box"}, "hidden の中には focus が移らない"
    assert s[13] == {"tag": "body", "class": ""}, "動かした要素は focus を失う"
    assert s[14][0]["value"] == "hello" and s[14][0]["selection"] == [1, 3], "値と選択範囲は残る"


def test_d0044_harness_query_reports_shown_and_shown_text(node):
    """D0044-AC-33: 台の自己検査。query の shown（文書に付いていて hidden でない）・view の shown_text（hidden の中を除いた文字）が使える。"""
    r = run_scene(node, REFERENCE_PAGE, steps=[{"op": "query", "selector": "#inner"}, {"op": "query", "selector": "#go"}, {"op": "query", "selector": "#off"}])
    assert r["steps"][0]["result"][0]["shown"] is False and r["steps"][1]["result"][0]["shown"] is True
    assert r["steps"][2]["result"][0]["disabled"] is True and r["steps"][1]["result"][0]["disabled"] is False
    assert "inner" in r["loaded"]["text"] and "inner" not in r["loaded"]["shown_text"] and "go" in r["loaded"]["shown_text"]


def test_d0044_harness_records_native_dialogs(node):
    """D0044-AC-36: 台の自己検査。confirm・alert・prompt を呼んだページは、台が dialogs に記録する。"""
    r = run_scene(node, REFERENCE_PAGE, steps=[{"op": "call", "fn": "doConfirm", "args": []}])
    assert r["dialogs"] == ["confirm"] and r["steps"][0]["result"] is False


def test_d0044_harness_keeps_the_old_scene_working(node):
    """D0044-AC-34: 台の自己検査。comments を設定しない場面は、前の版のとおり（use("comments") は null）。偽の DOM の追加（value・disabled・focus）が前の版の動きを変えない。"""
    r = run_scene(node, REFERENCE_PAGE, steps=[{"op": "query", "selector": "#t"}])
    assert r["comments"] == {"use_calls": 1, "can_calls": 0, "anchor_calls": [], "sends": [], "pending_sends": 0, "pending_can": 0, "pending_anchor": 0}
    assert r["db"]["use_calls"] == ["comments"] and r["dialogs"] == [] and r["alerts"] == []
    assert r["steps"][0]["result"][0]["attrs"]["maxlength"] == "5"


# ================================================================================================
# ページの本物の JS
# ================================================================================================


def control_shows_buttons(node, html) -> None:
    """対にする確認：同じ画面で、有効な review ならボタンが出る（「出ない」の検査が、ボタンを作っていないせいで通ってしまわないように）。"""
    rows = [stage("requirements", "done"), stage("red", "review")]
    assert_idle(play(node, html, snap=snapshot(rows, review={"stage": "red", "id": ID1})).frames[0], "対の確認: ")


def baseline_text(node, html, snap) -> str:
    """同じ写しを、comments の口が無い画面（前の版と同じ）で描いた文字。"""
    return play(node, html, snap=snap, comments=None).frames[0].view["text"]


# ---- AC-33 ボタンが出る ----------------------------------------------------------------------------------


def test_d0044_ac33_buttons_and_input_appear_only_on_the_review_row(node, html):
    """D0044-AC-33: comments が取れて canSendToClaude が available、写しの review が有効で確認待ちの行があるとき、その行にだけ承認・差し戻し・中止のボタン3つと入力欄が出る。ほかの行には出ない。"""
    rows = [stage("requirements", "done"), stage("design", "running", started_at=iso(60)), stage("red", "review", pending_since=iso(30)), stage("implement"), stage("test", "revised")]
    run = play(node, html, [query("li.s-review > div.review"), query("li.s-running div.review"), query("li.s-done div.review"), query("li.s-waiting div.review"),
                            query("li.s-revised div.review"), query("li.s-review > *"), query("div.review"), query("button"), query("textarea")],
               snap=snapshot(rows))
    f = run.frames[0]
    assert_idle(f)
    assert [len(run.result(i)) for i in range(5)] == [1, 0, 0, 0, 0]
    children = run.result(5)
    assert children[-1]["attrs"]["class"] == "review", "パネルは確認待ちの行の最後の子"
    assert len(run.result(6)) == 1 and len(run.result(7)) == 5 and len(run.result(8)) == 1
    assert run.can_calls == 1 and run.use_calls == ["db", "comments"] and run.sends == []


def test_d0044_ac33_parts_have_the_designed_labels_and_attributes(node, html):
    """D0044-AC-33: 部品の文字と属性（パネルの role・aria-label、入力欄の maxlength・rows・aria-label、ボタンの type・文字、文の欄の role・aria-live）が設計どおり。"""
    f = play(node, html, snap=snapshot()).frames[0]
    assert f.attrs("panel")["role"] == "group" and f.attrs("panel")["aria-label"] == "確認待ちの答え"
    assert f.attrs("input")["maxlength"] == "1000" and f.attrs("input")["rows"] == "3" and f.attrs("input")["aria-label"] == "直してほしい点（差し戻すときだけ）"
    assert f.attrs("msg")["role"] == "status" and f.attrs("msg")["aria-live"] == "polite"
    for name in ("approve", "revise", "quit", "go", "back"):
        assert f.text(name) == LABELS[name], name
        assert f.attrs(name)["type"] == "button", name
        cls = f.attrs(name)["class"].split()
        assert "rv-btn" in cls and f"rv-{name}" in cls, (name, cls)
    assert "rv-input" in f.attrs("input")["class"].split() and "rv-msg" in f.attrs("msg")["class"].split() and f.attrs("panel")["class"].split() == ["review"]
    assert f.value("input") in (None, "")


def test_d0044_ac33_only_the_row_named_by_review_gets_the_panel(node, html):
    """D0044-AC-33: 確認待ちの行が2つあっても、review の段の行にだけ出る。行の突き合わせは段の名前（name）で、表示名（label）ではない。"""
    rows = [stage("x1", "review", label="LABEL-red"), stage("red", "review", label="LABEL-x1"), stage("tail")]
    run = play(node, html, [query("li.s-review")], snap=snapshot(rows, review={"stage": "red", "id": ID1}))
    with_panel = [x["text"] for x in run.result(0) if "承認" in x["text"]]
    assert len(run.result(0)) == 2 and len(with_panel) == 1
    assert "LABEL-x1" in with_panel[0] and "LABEL-red" not in with_panel[0]
    assert run.frames[0].counts["panel"] == 1


def test_d0044_ac33_panel_moves_with_the_review(node, html):
    """D0044-AC-33: 確認待ちが別の段に移ったら、パネルは新しい行にだけ出る（古い行には残らない）。パネルはいつも1つ。"""
    first = reviewing("design", ID1)
    second = reviewing("red", ID2)
    run = play(node, html, [send(second), query("li.s-review"), query("li.s-done div.review"), query("div.review")], snap=first)
    assert_idle(run.frames[0])
    assert_idle(run.frames[1])
    rows = run.result(1)
    assert len(rows) == 1 and "LABEL-red" in rows[0]["text"] and "承認" in rows[0]["text"]
    assert len(run.result(2)) == 0 and len(run.result(3)) == 1


def test_d0044_ac33_panel_is_not_in_the_static_markup(node, html):
    """D0044-AC-33: 確認待ちが現れるまで、ページにパネルもボタンも無い（骨組みは変えず、JS が確認待ちが最初に現れたときに作る）。"""
    assert_idle(play(node, html, snap=snapshot()).frames[0], "確認待ちが現れればパネルができる: ")
    run = play(node, html, [send(after_approval())], snap=snapshot(review=None))
    for f in run.frames:
        assert f.counts["panel"] == 0 and f.counts["approve"] == 0 and f.counts["input"] == 0
    assert "button" not in run.r["final"]["tags"] and "textarea" not in run.r["final"]["tags"]


# ---- AC-34 ボタンが出ない --------------------------------------------------------------------------------------


NO_BUTTON_CASES = {
    "review is null": dict(snap=snapshot(review=None), asks_comments=False),
    "review key is missing (old snapshot)": dict(snap=snapshot(review=NO_KEY), asks_comments=False),
    "review is for a stage that is not listed": dict(snap=snapshot(review={"stage": "ghost", "id": ID1}), asks_comments=False),
    "review stage row is not in review status": dict(snap=snapshot(review={"stage": "design", "id": ID1}), asks_comments=False),
    "review stage row is running": dict(snap=snapshot([stage("red", "running", started_at=iso(5))], review={"stage": "red", "id": ID1}), asks_comments=False),
    "no review row at all": dict(snap=snapshot([stage("requirements", "done"), stage("design", "done")]), asks_comments=False),
    "final is set": dict(snap=snapshot(final="PASSED"), asks_comments=None),
    "final STOPPED_BY_HUMAN": dict(snap=snapshot(final="STOPPED_BY_HUMAN"), asks_comments=None),
    "empty snapshot": dict(snap=snapshot([], empty=True), asks_comments=False),
    "schema is different": dict(snap=snapshot(schema=2), asks_comments=False),
    "schema is missing": dict(snap={k: v for k, v in snapshot().items() if k != "schema"}, asks_comments=False),
    "stages is not a list": dict(snap=snapshot(stages="x"), asks_comments=False),
    "comments is null": dict(snap=snapshot(), comments={"use": "null"}, asks_comments=True),
    "use comments rejects": dict(snap=snapshot(), comments={"use": "rejects"}, asks_comments=True),
    "use comments throws": dict(snap=snapshot(), comments={"use": "throws"}, asks_comments=True),
    "use comments undefined": dict(snap=snapshot(), comments={"use": "undefined"}, asks_comments=True),
    "no comments at all (old screen)": dict(snap=snapshot(), comments=None, asks_comments=True),
}


@pytest.mark.parametrize("name", list(NO_BUTTON_CASES))
def test_d0044_ac34_no_buttons_when_comments_or_review_are_unusable(node, html, name):
    """D0044-AC-34: comments が null・use の例外・review が null / 無い / 古い写し・final あり・記録なし・schema 違い・確認待ちの行なし、のどの場合も、ボタンも入力欄も出ず、今までの描き方（見るだけ）が変わらない。
    review が無効なら comments を取りにいかない。comments が使えないときは、文も出さず前の版と同じ画面になる。
    review が無効な場合は今の作りのままで通る（守り続ける検査）。comments が null などの場合は、comments を取りにいく旨で赤になる。"""
    case = NO_BUTTON_CASES[name]
    kwargs = {"comments": case["comments"]} if "comments" in case else {}
    run = play(node, html, [send(case["snap"])], snap=case["snap"], **kwargs)
    for i, f in enumerate(run.frames):
        assert_no_ui(f, f"フレーム{i}: ")
    assert run.sends == [] and run.anchors == []
    if case["asks_comments"] is not None:  # final が入った写しで comments を取りにいくかは決めない（ボタンが出ないことだけを見る）
        assert run.can_calls == 0
        assert run.use_calls == (["db", "comments"] if case["asks_comments"] else ["db"])
    assert run.last.view["text"] == baseline_text(node, html, case["snap"]), "見るだけの描き方が前の版と違う"


def test_d0044_ac34_no_buttons_when_the_db_cannot_be_read(node, html):
    """D0044-AC-34: db が取れない画面（claude.use("db") が null）では、comments も取りにいかない。見るだけの文（この画面では読めません）のまま。"""
    run = play(node, html, claude="null", comments={})
    assert run.use_calls == ["db"] and run.r["comments"]["use_calls"] == 0
    assert "この画面では読めません" in run.frames[0].view["text"]
    assert_no_ui(run.frames[0])


@pytest.mark.parametrize("mode", ["use_rejects", "use_throws", "use_undefined", "undefined"])
def test_d0044_ac34_no_buttons_when_the_claude_object_itself_is_unusable(node, html, mode):
    """D0044-AC-34: claude.use が使えない画面（reject・throw・undefined・claude が無い）でも、ボタンは出ず、例外を出さない。"""
    run = play(node, html, claude=mode, comments={}, strict=False)
    assert run.r["load_error"] is None and run.r["uncaught"] == []
    assert_no_ui(run.frames[0])


# ---- AC-35 canSendToClaude の値ごと ---------------------------------------------------------------------------


def test_d0044_ac35_available_shows_the_buttons(node, html):
    """D0044-AC-35: available はボタンが出る（3つのボタンと入力欄が見えて押せる）。呼ぶのは1回。"""
    run = play(node, html, snap=snapshot(), comments={"can": "available"})
    assert_idle(run.frames[0])
    assert run.can_calls == 1 and run.use_calls == ["db", "comments"]


@pytest.mark.parametrize("value,text", [("writers_only", WRITERS), ("no_session", NO_SESSION), ("off", OFF)])
def test_d0044_ac35_each_blocked_value_shows_its_own_message_and_no_buttons(node, html, value, text):
    """D0044-AC-35: writers_only・no_session・off は、それぞれ別の理由の文が出てボタン・入力欄が出ない。どの文にも「会話で答えてください」の案内がある。"""
    run = play(node, html, snap=snapshot(), comments={"can": value})
    assert_blocked(run.frames[0], text)
    assert "会話で答えてください" in text and run.can_calls == 1 and run.sends == []
    assert run.frames[0].shown("panel"), "理由の文を出す入れ物は見える"


GENERIC_VALUES = ["maybe", "", "AVAILABLE", "Available", "available ", " available", "available\n", "writers-only", "unknown", None, {"$": "undefined"}, 0, 1, -1, 1.5, True, False, {}, [], {"state": "available"}, ["available"], {"$": "reject"}, {"$": "throw"}, "😀", "a" * 5000]


@pytest.mark.parametrize("value", GENERIC_VALUES, ids=sid)
def test_d0044_ac35_unusable_values_show_the_generic_message(node, html, value):
    """D0044-AC-35: 知らない文字列・null・undefined・数・真偽・オブジェクト・reject（例外）は「使えない」の文が出てボタンが出ない。available に似た文字列（大文字・空白つき）も使えない。"""
    run = play(node, html, snap=snapshot(), comments={"can": value})
    assert_blocked(run.frames[0], GENERIC)
    assert run.can_calls == 1 and run.sends == []


def test_d0044_ac35_the_four_messages_differ(node, html):
    """D0044-AC-35: 理由ごとの4つの文（writers_only・no_session・off・ほか）は、どれも違う文。"""
    seen = []
    for value in ("writers_only", "no_session", "off", "other"):
        seen.append(play(node, html, snap=snapshot(), comments={"can": value}).frames[0].message())
    assert seen == [WRITERS, NO_SESSION, OFF, GENERIC] and len(set(seen)) == 4


def test_d0044_ac35_every_message_points_to_the_conversation(node, html):
    """D0044-AC-35: 使えないときの文は、どれも「会話で答えてください」の案内を含む。"""
    for value in ("writers_only", "no_session", "off", "other", None, {"$": "reject"}):
        message = play(node, html, snap=snapshot(), comments={"can": value}).frames[0].message()
        assert message and "会話で答えてください" in message, value


def test_d0044_ac35_can_send_is_called_once_per_new_id(node, html):
    """D0044-AC-35: 呼ぶのは確認待ちが現れた（識別子が替わった）ときで、同じ識別子の描き直しのたびには呼ばない。comments を取るのも1回。"""
    same = snapshot()
    other_time = snapshot(generated_at=iso(-10))
    cost = snapshot([stage("requirements", "done", cost_usd=9.5), stage("design", "done"), stage("red", "review"), stage("implement"), stage("test")])
    run = play(node, html, [send(same), send(other_time), send(cost), {"op": "advance", "ms": 5000}, send(snapshot(review={"stage": "red", "id": ID2}))], snap=same)
    assert run.can_calls == 2
    r = play(node, html, [send(same), send(other_time), send(cost)], snap=same)
    assert r.can_calls == 1 and r.r["comments"]["use_calls"] == 1
    assert_idle(run.last)
    assert run.use_calls.count("comments") == 1


def test_d0044_ac35_a_changed_stage_with_the_same_id_is_a_new_review(node, html):
    """D0044-AC-35: 識別子が同じでも段が替われば新しい確認待ち（識別は 段＋識別子）。もう一度 canSendToClaude を呼ぶ。"""
    run = play(node, html, [send(reviewing("red", ID1)), send(reviewing("design", ID1))], snap=reviewing("red", ID1), comments={"can": "available"})
    assert run.can_calls == 2


def test_d0044_ac35_review_going_away_and_coming_back_asks_again(node, html):
    """D0044-AC-35: 確認待ちが消えて同じ識別子でまた現れたら、新しい確認待ちとして呼び直す（前の状態は残らない）。"""
    run = play(node, html, [typing("書きかけ"), send(after_approval()), send(snapshot())], snap=snapshot())
    assert run.can_calls == 2
    assert_no_ui(run.frames[2])
    assert_idle(run.frames[3])
    assert run.frames[3].value("input") in (None, ""), "前の書きかけが残っていない"


def test_d0044_ac35_a_new_id_asks_again_and_a_changed_answer_applies(node, html):
    """D0044-AC-35: 新しい識別子では呼び直し、その時点の答えで出し分ける（前は writers_only でも、次が available ならボタンが出る）。"""
    run = play(node, html, [{"op": "set_can", "value": "available"}, send(snapshot(review={"stage": "red", "id": ID2}))], snap=snapshot(), comments={"can": "writers_only"})
    assert_blocked(run.frames[0], WRITERS)
    assert_blocked(run.frames[1], WRITERS), "同じ識別子のうちは呼び直さない（set_can だけでは替わらない）"
    assert_idle(run.frames[2])
    assert run.can_calls == 2


def test_d0044_ac35_comments_are_requested_once_even_if_they_were_unusable(node, html):
    """D0044-AC-35: claude.use("comments") は1回だけ（取れなかったときも null として覚えて、新しい確認待ちでも取り直さない）。"""
    run = play(node, html, [send(reviewing("red", ID2)), send(after_approval()), send(reviewing("red", ID3))], snap=snapshot(), comments={"use": "rejects"})
    assert run.use_calls.count("comments") == 1 and run.r["comments"]["use_calls"] == 1
    for f in run.frames:
        assert_no_ui(f)


def test_d0044_ac35_nothing_is_shown_while_checking(node, html):
    """D0044-AC-35: canSendToClaude の答えを待っている間（確かめ中）は、ボタンも入力欄も出さない。答えが来てから出す。"""
    run = play(node, html, [{"op": "settle_can", "call": 0, "value": "available"}], snap=snapshot(), comments={"can": "pending"})
    assert_no_ui(run.frames[0], "確かめ中: ")
    assert run.can_calls == 1 and run.r["comments"]["pending_can"] == 1
    assert_idle(run.frames[1])


def test_d0044_ac35_a_late_answer_for_an_old_id_is_discarded(node, html):
    """D0044-AC-35: 識別子が替わったあとに前の識別子の canSendToClaude の答えが遅れて来ても、画面を変えない（新しい識別子の答えだけで出し分ける）。"""
    run = play(node, html, [send(reviewing("red", ID2)), {"op": "settle_can", "call": 1, "value": "writers_only"}, {"op": "settle_can", "call": 0, "value": "available"}],
               snap=snapshot(), comments={"can": "pending"})
    assert run.can_calls == 2
    assert_no_ui(run.frames[1])
    assert_blocked(run.frames[2], WRITERS)
    assert_blocked(run.frames[3], WRITERS), "古い識別子の available が新しい識別子の画面を上書きした"


def test_d0044_ac35_a_late_answer_that_arrives_before_the_new_one_does_not_show_the_buttons(node, html):
    """D0044-AC-35: 前の識別子の答え（available）が、新しい識別子の答えより先に遅れて着いても、新しい識別子の答えが来るまでは、ボタンを出さない（古い答えで出し分けない）。"""
    run = play(node, html, [send(reviewing("red", ID2)), {"op": "settle_can", "call": 0, "value": "available"}, {"op": "settle_can", "call": 1, "value": "no_session"}],
               snap=snapshot(), comments={"can": "pending"})
    assert_no_ui(run.frames[1])
    assert_no_ui(run.frames[2], "古い識別子の available が先に着いた: ")
    assert_blocked(run.frames[3], NO_SESSION)


def test_d0044_ac35_a_rejecting_check_is_the_generic_message_and_is_not_retried(node, html):
    """D0044-AC-35: canSendToClaude が reject しても、例外を出さず「使えない」の文を出す。同じ識別子の描き直しでは呼び直さない。"""
    run = play(node, html, [send(snapshot()), send(snapshot(generated_at=iso(-1)))], snap=snapshot(), comments={"can": {"$": "reject"}})
    assert run.can_calls == 1
    for f in run.frames:
        assert_blocked(f, GENERIC)


# ---- AC-36 確かめ ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["approve", "quit"])
def test_d0044_ac36_approve_and_quit_go_through_a_check_step_first(node, html, action):
    """D0044-AC-36: 承認・中止を押すと、まだ sendToClaude は呼ばれず、確かめ（実行するボタンと戻るボタン）が出る。問いの文は固定。anchor はこの最初の操作で取る（パネルの要素に対して）。"""
    run = play(node, html, [click(action)], snap=snapshot())
    assert_idle(run.frames[0])
    f = run.frames[1]
    assert_confirm(f, action)
    assert run.sends == []
    assert len(run.anchors) == 1 and run.anchors[0]["el_tag"] == "div" and "review" in run.anchors[0]["el_class"].split() and run.anchors[0]["attached"] is True


def test_d0044_ac36_revise_goes_to_the_check_step_with_a_valid_feedback(node, html):
    """D0044-AC-36: 差し戻しも、直してほしい点が通れば確かめに進む（まだ sendToClaude は呼ばれない）。"""
    run = play(node, html, [typing("ここを直して"), click("revise")], snap=snapshot())
    assert_confirm(run.frames[2], "revise")
    assert run.sends == [] and len(run.anchors) == 1
    assert run.frames[2].value("input") == "ここを直して", "確かめの間も入力欄の中身は残る"


@pytest.mark.parametrize("action", ACTIONS)
def test_d0044_ac36_other_buttons_do_nothing_during_the_check_step(node, html, action):
    """D0044-AC-36: 確かめの間は、承認・差し戻し・中止のボタンは働かない（押されても、anchorFor も sendToClaude も呼ばず、確かめも替わらない）。"""
    run = play(node, html, [typing("直して"), click("approve"), click(action, force=True), click("quit", force=True), click("revise", force=True)], snap=snapshot())
    assert_confirm(run.frames[2], "approve")
    for f in run.frames[3:]:
        assert_confirm(f, "approve")
    assert len(run.anchors) == 1 and run.sends == []


@pytest.mark.parametrize("action", ACTIONS)
def test_d0044_ac36_back_returns_to_the_start(node, html, action):
    """D0044-AC-36: 戻るボタンで元に戻る（3つのボタンと入力欄が出て、確かめが消え、sendToClaude は呼ばれない）。入力欄の中身は残る。"""
    run = play(node, html, [typing("直して"), click(action), click("back")], snap=snapshot())
    assert_confirm(run.frames[2], action)
    f = run.frames[3]
    assert_idle(f)
    assert f.value("input") == "直して" and run.sends == []
    assert ASK[action] not in run.last.view["shown_text"]


@pytest.mark.parametrize("action", ACTIONS)
def test_d0044_ac36_after_back_the_same_or_another_action_can_be_checked_again(node, html, action):
    """D0044-AC-36: 戻ったあと、もう一度押すと、また確かめに進む。そのたびに anchor を取り直す（捨てた anchor を使い回さない）。"""
    run = play(node, html, [typing("直して"), click(action), click("back"), click("quit"), click("back"), click("approve")], snap=snapshot())
    assert_confirm(run.frames[4], "quit")
    assert_confirm(run.frames[6], "approve")
    assert len(run.anchors) == 3 and run.sends == []


INVALID_FEEDBACK = [
    ("", "empty"),
    (" ", "empty"),
    ("   \n\t  \n", "empty"),
    ("\u3000", "empty"),
    ("\u00a0\u3000\u2003", "empty"),
    ("\n\n\n", "empty"),
    ("あ" * 1001, "too_long"),
    ("😀" * 1001, "too_long"),
    ("x" * 5000, "too_long"),
    ("e\u0301" * 501, "too_long"),
    (" " * 50 + "x" * 1001 + " " * 50, "too_long"),
    ("a\x00b", "bad_chars"),
    ("\x07", "bad_chars"),
    ("a\x1bb", "bad_chars"),
    ("a\x7fb", "bad_chars"),
    ("a\x85b", "bad_chars"),
    ("a\x0bb", "bad_chars"),
    ("a\x0cb", "bad_chars"),
    ("a\rb", "bad_chars"),
    ("a\u200bb", "bad_chars"),
    ("a\u200cb", "bad_chars"),
    ("a\u200db", "bad_chars"),
    ("a\u2060b", "bad_chars"),
    ("\ufeffa", "bad_chars"),
    ("a\u202eb", "bad_chars"),
    ("a\u200fb", "bad_chars"),
    ("a\u2066b", "bad_chars"),
    ("a\u2028b", "bad_chars"),
    ("a\u2029b", "bad_chars"),
    ("a\u00adb", "bad_chars"),
    ("a\ud800b", "bad_chars"),
    ("\udc00", "bad_chars"),
    ("👨\u200d👩\u200d👧", "bad_chars"),
    ("\x00" + " " * 5, "bad_chars"),
    ("あ" * 1001 + "\x00", "bad_chars"),
]


@pytest.mark.parametrize("value,reason", INVALID_FEEDBACK, ids=lambda v: sid(v) if isinstance(v, str) and len(v) < 30 else None)
def test_d0044_ac36_revise_is_refused_before_the_check_step(node, html, value, reason):
    """D0044-AC-36: 差し戻しは、入力欄が空・空白だけ・1001 文字以上・断られる文字（制御文字・ゼロ幅・RTL・孤立サロゲート）を含むとき、確かめに進めず理由が出て、sendToClaude も anchorFor も呼ばれない。"""
    run = play(node, html, [typing(value), click("revise")], snap=snapshot())
    f = run.frames[2]
    assert_idle(f, message=INVALID[reason])
    assert run.sends == [] and run.anchors == []
    assert f.value("input") == value, "入力欄の中身は残る"


def test_d0044_ac36_revise_refusal_then_a_fixed_text_goes_on(node, html):
    """D0044-AC-36: 理由が出たあと、書き直して押すと確かめに進む（理由の文は消える）。"""
    run = play(node, html, [click("revise"), typing("書いた"), click("revise")], snap=snapshot())
    assert run.frames[1].message() == INVALID["empty"]
    assert_confirm(run.frames[3], "revise")


@pytest.mark.parametrize(
    "value",
    ["x", "あ" * 1000, "😀" * 1000, "e\u0301" * 500, "\U0001f1ef\U0001f1f5" * 500, " " * 30 + "x" * 1000 + "\n\n", "\u3000" + "あ" * 1000 + "\u3000", "a\tb", "a\nb", "a\n\nb", "a\r\nb", "tab\tand\nnewline", "全角\u3000空白", "❤️ 👍🏽 🇯🇵", "<script>alert(1)</script>", "`$(x)`; &&"],
    ids=sid,
)
def test_d0044_ac36_revise_that_passes_the_check_goes_on(node, html, value):
    """D0044-AC-36: 1000 文字ちょうど（コードポイントで数える。絵文字・結合文字・国旗も）・タブ・改行・全角空白・前後の空白つきは確かめに進める。"""
    run = play(node, html, [typing(value), click("revise")], snap=snapshot())
    assert_confirm(run.frames[2], "revise")
    assert run.sends == [] and len(run.anchors) == 1


@pytest.mark.parametrize("action", ACTIONS)
def test_d0044_ac36_focus_moves_to_the_run_button_in_the_check_step(node, html, action):
    """D0044-AC-36: 確かめに入ったら、押したボタンの次に使う実行するボタンに focus が移る（キーボードで続けられる）。"""
    run = play(node, html, [typing("直して"), {"op": "focus", "selector": SEL[action]}, click(action), {"op": "focus_state"}], snap=snapshot())
    assert run.result(3)["tag"] == "button" and "rv-go" in run.result(3)["class"].split(), run.result(3)


@pytest.mark.parametrize("action", ACTIONS)
def test_d0044_ac36_focus_returns_to_the_original_button_on_back(node, html, action):
    """D0044-AC-36: 戻るときは、もとの動作のボタンに focus が戻る（キーボードで続けられる）。"""
    run = play(node, html, [typing("直して"), click(action), click("back"), {"op": "focus_state"}], snap=snapshot())
    state = run.result(3)
    assert state["tag"] == "button" and f"rv-{action}" in state["class"].split(), state


def test_d0044_ac36_no_native_dialog_is_used_in_any_flow(node, html):
    """D0044-AC-36: 確かめも送信も、window.confirm・alert・prompt を使わない（台が呼び出しを記録する）。"""
    run = play(node, html, [typing("直して"), click("revise"), click("go"), click("back", force=True)], snap=snapshot())
    assert_stopped(run.frames[3], SENT)
    assert len(run.sends) == 1
    assert run.r["dialogs"] == [] and run.r["alerts"] == []


# ---- AC-37 送る文と呼び方 ----------------------------------------------------------------------------------------


def expected_text(action: str, stage_name: str, ident: str, feedback: str | None = None) -> str:
    word = {"approve": "approve", "revise": "revise", "quit": "quit"}[action]
    return f"pipe-in: {word} {stage_name} {ident}" + (f"\n{feedback}" if feedback is not None else "")


@pytest.mark.parametrize("action,feedback", [("approve", None), ("quit", None), ("revise", "ここを直してください")])
def test_d0044_ac37_one_send_per_go_with_the_expected_text(node, html, action, feedback):
    """D0044-AC-37: 実行するボタンの1回の操作で sendToClaude が1回呼ばれ、text が決まった形（承認・中止は1行、差し戻しは1行目＋直してほしい点）になり、段と識別子は写しの review と同じ。引数は {anchor, text} だけ。"""
    steps = ([typing(feedback)] if feedback else []) + [click(action), click("go")]
    run = play(node, html, steps, snap=snapshot(), comments={"send": "pending"})
    assert len(run.sends) == 1
    assert len(run.sends) >= 1, "sendToClaude が呼ばれていない（ボタンがまだ無い）"
    s = run.sends[0]
    assert s["text"] == expected_text(action, "red", ID1, feedback)
    assert s["keys"] == ["anchor", "text"] and s["argc"] == 1 and s["n"] == 0


@pytest.mark.parametrize("stage_name", ["requirements", "design", "red", "implement", "test", "make-diagram_2", "A", "a" * 40, "Z9-_x"])
@pytest.mark.parametrize("ident", [ID1, ID2, ID3, "0000000000", "abcdef0123"])
def test_d0044_ac37_stage_and_id_come_from_the_review(node, html, stage_name, ident):
    """D0044-AC-37: 段と識別子は写しの review から来る（段の名前に - _ 大文字・40 文字、識別子の 16 進のどの形でも、そのまま文に入る）。"""
    run = play(node, html, [click("approve"), click("go")], snap=reviewing(stage_name, ident))
    assert [s["text"] for s in run.sends] == [expected_text("approve", stage_name, ident)]


def test_d0044_ac37_stage_and_id_are_not_taken_from_labels_or_names_on_screen(node, html):
    """D0044-AC-37: 文の段・識別子は review のものだけ（表示名・セッション名・別の行の名前は使わない）。"""
    rows = [stage("design", "review", label="LABEL-MARK-A"), stage("red", "review", label="LABEL-MARK-B"), stage("tail", "waiting", label="LABEL-MARK-C")]
    run = play(node, html, [click("quit"), click("go")], snap=snapshot(rows, review={"stage": "red", "id": ID2}, name="SESSION-NAME-MARK"))
    assert [s["text"] for s in run.sends] == [expected_text("quit", "red", ID2)]
    assert len(run.sends) >= 1, "sendToClaude が呼ばれていない（ボタンがまだ無い）"
    assert "MARK" not in json.dumps(run.sends[0])


def test_d0044_ac37_send_is_called_inside_the_gesture_without_await(node, html):
    """D0044-AC-37: sendToClaude は実行するボタンの操作の中で、await を挟まずに呼ばれる（in_gesture が真）。承認・差し戻し・中止のどれでも。"""
    for action in ACTIONS:
        run = play(node, html, [typing("直して"), click(action), click("go")], snap=snapshot())
        assert len(run.sends) == 1 and run.sends[0]["in_gesture"] is True, action


def test_d0044_ac37_anchor_is_the_issued_one_and_has_no_outside_text(node, html):
    """D0044-AC-37: anchor は anchorFor が発行したものそのまま（作り直さない・書き換えない）で、外から来た文字（セッション名・段の表示名・入力欄の文）が入らない。"""
    rows = [stage("requirements", "done", label="LABEL-MARK"), stage("red", "review", label="LABEL-MARK-RED")]
    run = play(node, html, [typing("TYPED-INPUT-MARK"), click("revise"), click("go")], snap=snapshot(rows, review={"stage": "red", "id": ID1}, name="SESSION-NAME-MARK"))
    assert len(run.sends) == 1 and run.anchors == [{"el_tag": "div", "el_class": "review", "attached": True}]
    s = run.sends[0]
    assert s["anchor_issued"] is True
    assert s["anchor"]["token"] == "ANCHOR-TOKEN-1" and set(s["anchor"]) == {"path", "x", "y", "token"}
    blob = json.dumps(s["anchor"], ensure_ascii=False)
    for mark in ("MARK", "TYPED", "SESSION", "LABEL", ID1):
        assert mark not in blob, mark
    assert s["text"].endswith("\nTYPED-INPUT-MARK") and "MARK" not in s["text"].split("\n", 1)[0]


def test_d0044_ac37_anchor_is_fetched_again_after_going_back(node, html):
    """D0044-AC-37: 戻ると anchor を捨てる：もう一度確かめに入ったときに取り直した新しい anchor を、そのまま渡す（捨てた anchor を渡さない）。"""
    run = play(node, html, [click("approve"), click("back"), click("approve"), click("go")], snap=snapshot())
    assert len(run.anchors) == 2 and len(run.sends) == 1
    assert len(run.sends) >= 1, "sendToClaude が呼ばれていない（ボタンがまだ無い）"
    assert run.sends[0]["anchor"]["token"] == "ANCHOR-TOKEN-2" and run.sends[0]["anchor_issued"] is True


def test_d0044_ac37_the_text_uses_the_trimmed_feedback_with_lf(node, html):
    """D0044-AC-37: 差し戻しの文は、直してほしい点の前後の空白を取り、CRLF を LF にしたもの（Python の読み取りが返すものと同じ）。"""
    run = play(node, html, [typing("  \n 1行目\r\n\r\n3行目 \n\n"), click("revise"), click("go")], snap=snapshot())
    assert [s["text"] for s in run.sends] == [expected_text("revise", "red", ID1, "1行目\n\n3行目")]


def test_d0044_ac37_the_run_button_does_nothing_outside_the_check_step(node, html):
    """D0044-AC-37: 確かめに入る前に実行するボタンを（force で）押しても、何も送らない・anchorFor も呼ばない。"""
    run = play(node, html, [click("go", force=True), click("go", times=3, force=True)], snap=snapshot())
    assert run.sends == [] and run.anchors == []
    assert_idle(run.last)


def test_d0044_ac37_sending_does_not_start_timers_or_dialogs(node, html):
    """D0044-AC-37: 送ってもタイマーが増えず（setTimeout を使わない）、ダイアログも出ない。"""
    run = play(node, html, [click("approve"), click("go"), {"op": "advance", "ms": 600000}], snap=snapshot(), comments={"send": "pending"})
    assert run.last.view["timeouts"] == 0 and run.last.view["intervals"] == 0
    assert len(run.sends) >= 1, "sendToClaude が呼ばれていない（ボタンがまだ無い）"
    assert run.sends[0]["text"].startswith("pipe-in: approve red")


# ---- AC-38 送信中・送信後 ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("action", ACTIONS)
def test_d0044_ac38_controls_stop_while_sending_and_stay_stopped_after(node, html, action):
    """D0044-AC-38: sendToClaude が終わるまでの間、3つのボタンと入力欄が止まり、成功すると止まったまま「送りました（会話の返事を待っています）」が出る。入力欄の中身は残る。"""
    run = play(node, html, [typing("直して"), click(action), click("go"), {"op": "settle", "call": 0, "how": "resolve"}, {"op": "advance", "ms": 120000}], snap=snapshot(), comments={"send": "pending"})
    assert_confirm(run.frames[2], action)
    assert_stopped(run.frames[3], SENDING)
    assert_stopped(run.frames[4], SENT)
    assert_stopped(run.frames[5], SENT)
    assert run.frames[5].value("input") == "直して" and len(run.sends) == 1


def test_d0044_ac38_a_resolving_send_shows_the_sent_message_without_pending(node, html):
    """D0044-AC-38: すぐ終わる送信（resolve）でも、最後は「送りました」で止まったままになる。"""
    run = play(node, html, [click("approve"), click("go")], snap=snapshot(), comments={"send": "resolve"})
    assert_stopped(run.frames[2], SENT)


@pytest.mark.parametrize("second", ["go_twice", "go_force_thrice", "other_buttons", "approve_then_go", "quit_force", "back_force"])
def test_d0044_ac38_repeated_clicks_send_once(node, html, second):
    """D0044-AC-38: 実行するボタンを続けて2回（同じ操作の中で）押しても、別のボタンを続けて押しても、sendToClaude は合わせて1回。"""
    steps = {
        "go_twice": [click("approve"), click("go", times=2)],
        "go_force_thrice": [click("approve"), click("go", times=3, force=True), click("go", force=True)],
        "other_buttons": [click("approve"), click("go"), click("approve", force=True), click("quit", force=True), click("revise", force=True), click("go", force=True)],
        "approve_then_go": [click("approve", times=2), click("go"), click("go", force=True)],
        "quit_force": [click("quit"), click("go"), click("quit", force=True, times=2)],
        "back_force": [click("approve"), click("go"), click("back", force=True)],
    }[second]
    run = play(node, html, steps, snap=snapshot(), comments={"send": "pending"})
    assert len(run.sends) == 1
    assert len(run.anchors) == 1, "anchorFor も1回"


def test_d0044_ac38_repeated_clicks_after_the_send_finished_also_send_once(node, html):
    """D0044-AC-38: 送り終わったあと（送りました）に押しても、もう送らない（同じ確認に二度送らない）。"""
    run = play(node, html, [click("approve"), click("go"), {"op": "settle", "call": 0, "how": "resolve"}, click("go", force=True), click("approve", force=True), click("quit", force=True)],
               snap=snapshot(), comments={"send": "pending"})
    assert len(run.sends) == 1 and len(run.anchors) == 1
    assert_stopped(run.last, SENT)


def test_d0044_ac38_a_second_action_while_preparing_is_ignored(node, html):
    """D0044-AC-38: 場所（anchor）を取っている最中に別のボタンを押しても、無視される（anchorFor は1回・確かめは最初に押した動作のもの）。"""
    run = play(node, html, [click("approve"), click("quit", force=True), click("revise", force=True), click("approve", force=True), {"op": "settle_anchor", "call": 0, "how": "resolve"}, click("go")],
               snap=snapshot(), comments={"anchor": "pending"})
    assert len(run.anchors) == 1
    assert_confirm(run.frames[5], "approve")
    assert [s["text"] for s in run.sends] == [expected_text("approve", "red", ID1)]
    assert not run.frames[1].active("go"), "場所を取る最中に実行するボタンが押せるようになっている"


def test_d0044_ac38_rerender_during_sending_keeps_the_state(node, html):
    """D0044-AC-38: 送信中に写しが替わらずに描き直されても（時刻・別の行の経過・usage が替わる）、状態（止まった入力欄・送っています・送りました）が保たれる。"""
    base = snapshot()
    changed = snapshot([stage("requirements", "done", cost_usd=9.9, turns=7), stage("design", "done"), stage("red", "review", pending_since=iso(3)), stage("implement"), stage("test")], generated_at=iso(-30))
    run = play(node, html, [typing("直して"), click("revise"), click("go"), send(changed), send(base), {"op": "settle", "call": 0, "how": "resolve"}, send(changed), {"op": "advance", "ms": 20000}], snap=base, comments={"send": "pending"})
    assert_stopped(run.frames[3], SENDING)
    assert_stopped(run.frames[4], SENDING)
    assert_stopped(run.frames[5], SENDING)
    assert_stopped(run.frames[6], SENT)
    assert_stopped(run.frames[7], SENT)
    assert_stopped(run.frames[8], SENT)
    assert len(run.sends) == 1 and run.can_calls == 1 and run.frames[8].value("input") == "直して"


# ---- AC-39 失敗 ------------------------------------------------------------------------------------------------


RETRYABLE_REJECTS = [
    {"reject_code": "claude_unavailable"},
    {"reject_code": "unavailable"},
    {"reject_code": "upstream_error"},
    {"reject_code": "weird_code"},
    {"reject_code": ""},
    {"reject_code": "FORBIDDEN"},
    {"reject": "boom"},
    {"reject": None},
    {"reject": {"$": "undefined"}},
    {"reject": 5},
    {"reject": True},
    {"reject": []},
    {"reject": {}},
    {"reject": {"code": 123}},
    {"reject": {"code": None}},
    {"reject": {"code": ["forbidden"]}},
    {"reject": {"message": "M"}},
    {"reject": {"code": "claude_unavailable", "message": "M"}},
    "throws",
]


@pytest.mark.parametrize("send_mode", RETRYABLE_REJECTS, ids=sid)
def test_d0044_ac39_rejects_restore_the_controls(node, html, send_mode):
    """D0044-AC-39: sendToClaude が reject（claude_unavailable・知らないコード・文字列以外・undefined・同期の例外）しても、ページは例外を出さず、決まった失敗の文を出してボタンと入力欄を戻す。"""
    run = play(node, html, [typing("直して"), click("revise"), click("go")], snap=snapshot(), comments={"send": send_mode})
    f = run.last
    assert_idle(f, message=FAILED)
    assert f.value("input") == "直して" and len(run.sends) == 1


@pytest.mark.parametrize("code,text", [("consent_required", CONSENT), ("rate_limited", RATE)])
def test_d0044_ac39_known_codes_have_their_own_messages_and_allow_retry(node, html, code, text):
    """D0044-AC-39: consent_required・rate_limited は、それぞれの文を出して、やり直せる（ボタンが戻る）。"""
    run = play(node, html, [click("approve"), click("go")], snap=snapshot(), comments={"send": {"reject_code": code}})
    assert_idle(run.last, message=text)


def test_d0044_ac39_forbidden_hides_the_controls(node, html):
    """D0044-AC-39: forbidden（許可されていない）は、ボタンと入力欄を出さず、理由の文だけにする（押し直しても無駄なので）。"""
    run = play(node, html, [click("approve"), click("go")], snap=snapshot(), comments={"send": {"reject_code": "forbidden"}})
    assert_blocked(run.last, FORBIDDEN)
    assert len(run.sends) == 1


@pytest.mark.parametrize(
    "send_mode",
    [
        {"reject": {"code": "claude_unavailable", "message": "REJECT-SECRET-MARK"}},
        {"reject": "REJECT-SECRET-MARK"},
        {"reject": {"code": "REJECT-SECRET-MARK"}},
        {"reject": {"message": "REJECT-SECRET-MARK", "stack": "REJECT-SECRET-MARK"}},
        {"reject_code": "REJECT-SECRET-MARK"},
        {"reject": ["REJECT-SECRET-MARK"]},
    ],
    ids=sid,
)
def test_d0044_ac39_reject_text_never_reaches_the_screen(node, html, send_mode):
    """D0044-AC-39: reject の中の文字（message・code・文字列）は画面に出ない（固定の文だけ）。"""
    run = play(node, html, [typing("直して"), click("revise"), click("go")], snap=snapshot(), comments={"send": send_mode})
    assert len(run.sends) == 1 and run.last.message() in (FAILED, FORBIDDEN, CONSENT, RATE), "失敗の文が出ている"
    for f in run.frames:
        assert "REJECT" not in f.view["text"]
        assert f.message() in FIXED_OR_NONE
    assert run.r["console_errors"] == [] or all("REJECT" not in line for line in run.r["console_errors"])


def test_d0044_ac39_pressing_again_sends_again(node, html):
    """D0044-AC-39: 失敗のあと、もう一度押せば、もう一度送れる（確かめ → 実行を最初から。送る文は同じ）。"""
    run = play(node, html, [typing("直して"), click("revise"), click("go"), click("revise"), click("go")], snap=snapshot(), comments={"send": [{"reject_code": "claude_unavailable"}, "resolve"]})
    assert_idle(run.frames[3], message=FAILED)
    assert_stopped(run.last, SENT)
    assert len(run.sends) == 2 and [s["n"] for s in run.sends] == [0, 1]
    assert len(run.sends) >= 1, "sendToClaude が呼ばれていない（ボタンがまだ無い）"
    assert run.sends[0]["text"] == run.sends[1]["text"] == expected_text("revise", "red", ID1, "直して")
    assert all(s["anchor_issued"] and s["in_gesture"] for s in run.sends)


def test_d0044_ac39_repeated_failures_keep_the_buttons_usable(node, html):
    """D0044-AC-39: 失敗が続いても、何度でも押し直せる（ボタンが戻らなくなる・例外で固まる、ということがない）。"""
    steps = []
    for _ in range(4):
        steps += [click("approve"), click("go")]
    run = play(node, html, steps, snap=snapshot(), comments={"send": {"reject_code": "claude_unavailable"}})
    assert len(run.sends) == 4
    assert_idle(run.last, message=FAILED)


def test_d0044_ac39_a_late_failure_for_an_old_id_is_discarded(node, html):
    """D0044-AC-39: 識別子が替わったあとに、前の送信の失敗が遅れて来ても、新しい確認待ちの画面を変えない。"""
    run = play(node, html, [click("approve"), click("go"), send(reviewing("red", ID2)), {"op": "settle", "call": 0, "how": {"reject": {"code": "claude_unavailable"}}}], snap=snapshot(), comments={"send": "pending"})
    assert_stopped(run.frames[2], SENDING)
    assert_idle(run.frames[3])
    assert_idle(run.frames[4]), "古い失敗の文が新しい画面に出た"


@pytest.mark.parametrize("anchor_mode", ["rejects", "throws"])
@pytest.mark.parametrize("action", ACTIONS)
def test_d0044_ac39_anchor_failure_stays_at_the_start_with_its_message(node, html, anchor_mode, action):
    """D0044-AC-39: anchorFor が reject・同期で投げたときは、確かめに進まず「場所を取れませんでした」を出す。ボタンは元のまま（もう一度押せる）。sendToClaude は呼ばれない。入力欄の中身は残る。"""
    run = play(node, html, [typing("直して"), click(action), click(action)], snap=snapshot(), comments={"anchor": anchor_mode})
    for i in (2, 3):
        f = run.frames[i]
        assert_idle(f, message=ANCHOR_FAILED)
        assert f.value("input") == "直して"
    assert run.sends == [] and len(run.anchors) == 2


def test_d0044_ac39_a_late_anchor_for_an_old_id_is_discarded(node, html):
    """D0044-AC-39: 場所を取っている最中に識別子が替わったら、遅れて来た anchor の結果は新しい画面を変えない（新しい確認待ちが確かめに進まない）。"""
    run = play(node, html, [click("approve"), send(reviewing("red", ID2)), {"op": "settle_anchor", "call": 0, "how": "resolve"}], snap=snapshot(), comments={"anchor": "pending"})
    assert_idle(run.frames[2])
    assert_idle(run.frames[3]), "古い識別子の anchor が新しい画面を確かめにした"
    assert run.sends == []


def test_d0044_ac39_a_late_anchor_failure_for_an_old_id_is_discarded(node, html):
    """D0044-AC-39: 同じく、遅れて来た anchor の失敗も、新しい画面に失敗の文を出さない。"""
    run = play(node, html, [click("approve"), send(reviewing("red", ID2)), {"op": "settle_anchor", "call": 0, "how": "reject"}], snap=snapshot(), comments={"anchor": "pending"})
    assert_idle(run.frames[3])


# ---- AC-40 写しが替わったときの戻り ------------------------------------------------------------------------------


def drive_to(state: str) -> list[dict]:
    """ある状態まで進める操作。"""
    return {
        "typed": [typing("書きかけ")],
        "confirm": [typing("書きかけ"), click("revise")],
        "sending": [typing("書きかけ"), click("revise"), click("go")],
        "sent": [typing("書きかけ"), click("revise"), click("go"), {"op": "settle", "call": 0, "how": "resolve"}],
    }[state]


NEW_REVIEWS = {
    "same stage new id": reviewing("red", ID2),
    "other stage": reviewing("design", ID1),
    "other stage and id": reviewing("implement", ID3),
}
ENDED = {
    "approved (review null)": after_approval(),
    "final": snapshot(review=None, final="PASSED"),
    "review key gone": snapshot(review=NO_KEY),
}


@pytest.mark.parametrize("state", ["typed", "confirm", "sending", "sent"])
@pytest.mark.parametrize("name", list(NEW_REVIEWS))
def test_d0044_ac40_a_new_id_resets_everything_and_asks_again(node, html, state, name):
    """D0044-AC-40: 確認待ちの識別子が替わる（別の段・差し戻し後の新しい確認）と、「送りました」・確かめの途中・入力欄の中身が消えて元に戻り、新しい確認待ちでは canSendToClaude を呼び直す。"""
    new = NEW_REVIEWS[name]
    run = play(node, html, [*drive_to(state), send(new)], snap=snapshot(), comments={"send": "pending"})
    f = run.last
    assert_idle(f)
    assert f.value("input") in (None, ""), "入力欄の中身が残っている"
    assert run.can_calls == 2
    # 新しい確認待ちで、そのまま答えられる
    run2 = play(node, html, [*drive_to(state), send(new), click("approve"), click("go")], snap=snapshot(), comments={"send": "pending"})
    stage_name, ident = new["review"]["stage"], new["review"]["id"]
    assert len(run2.sends) >= 1, "sendToClaude が呼ばれていない（ボタンがまだ無い）"
    assert run2.sends[-1]["text"] == expected_text("approve", stage_name, ident)
    assert len(run2.sends) == (2 if state in ("sending", "sent") else 1)


@pytest.mark.parametrize("state", ["typed", "confirm", "sending", "sent"])
@pytest.mark.parametrize("name", list(ENDED))
def test_d0044_ac40_the_ended_review_removes_the_buttons(node, html, state, name):
    """D0044-AC-40: 確認待ちでなくなる（承認された・final）と、ボタンも入力欄も「送りました」も消える。呼び直しはしない。"""
    run = play(node, html, [*drive_to(state), send(ENDED[name])], snap=snapshot(), comments={"send": "pending"})
    assert_no_ui(run.last)
    assert run.can_calls == 1
    assert "送り" not in run.last.view["shown_text"]


@pytest.mark.parametrize("state", ["typed", "confirm", "sending", "sent"])
def test_d0044_ac40_the_same_id_keeps_input_check_sending_and_sent(node, html, state):
    """D0044-AC-40: 識別子が同じままの描き直し（別の行の経過が替わる・usage が替わる・時刻が替わる）では、入力欄の中身・確かめの途中・送信中・送信後の状態が保たれる。呼び直さない。"""
    base = snapshot()
    rerenders = [
        snapshot(generated_at=iso(-60)),
        snapshot([stage("requirements", "done", cost_usd=3.25, turns=9, duration_sec=99), stage("design", "done"), stage("red", "review"), stage("implement"), stage("test")]),
        snapshot([stage("requirements", "done"), stage("design", "done"), stage("red", "review", pending_since=iso(100)), stage("implement", "running", started_at=iso(5)), stage("test")]),
        snapshot(name="別のセッション名"),
    ]
    run = play(node, html, [*drive_to(state), *[send(s) for s in rerenders], {"op": "advance", "ms": 10000}], snap=base, comments={"send": "pending"})
    frames = run.frames
    start = len(drive_to(state))
    before = frames[start].signature()
    for i in range(start + 1, len(frames)):
        assert frames[i].signature() == before, f"描き直し{i - start}で状態が替わった"
    assert run.can_calls == 1 and len(run.sends) == (1 if state in ("sending", "sent") else 0)


def test_d0044_ac40_a_late_send_result_for_an_old_id_does_not_touch_the_new_screen(node, html):
    """D0044-AC-40: 識別子が替わったあとに、前の送信の結果（成功）が遅れて来ても、新しい確認待ちの画面を「送りました」にしない。"""
    run = play(node, html, [*drive_to("sending"), send(reviewing("red", ID2)), {"op": "settle", "call": 0, "how": "resolve"}], snap=snapshot(), comments={"send": "pending"})
    assert_idle(run.frames[-2])
    assert_idle(run.last), "古い送信の成功が新しい画面に出た"
    assert run.last.value("input") in (None, "")


def test_d0044_ac40_input_of_the_old_review_is_not_sent_for_the_new_one(node, html):
    """D0044-AC-40: 前の確認待ちで書いた入力は、新しい確認待ちの送信に混ざらない（新しい差し戻しは、新しく書いた文だけ）。"""
    run = play(node, html, [typing("OLD-TEXT"), send(reviewing("red", ID2)), typing("新しい指摘"), click("revise"), click("go")], snap=snapshot())
    assert [s["text"] for s in run.sends] == [expected_text("revise", "red", ID2, "新しい指摘")]


def test_d0044_ac40_ended_and_returned_review_starts_fresh(node, html):
    """D0044-AC-40: 確認待ちが終わって、同じ識別子でまた現れたら、新しい確認待ち：送信済みの状態は残らず、もう一度答えられる。"""
    run = play(node, html, [*drive_to("sent"), send(after_approval()), send(snapshot())], snap=snapshot(), comments={"send": "pending"})
    assert_no_ui(run.frames[5])
    assert_idle(run.last)
    assert run.can_calls == 2


def test_d0044_ac40_focus_survives_a_rerender(node, html):
    """D0044-AC-40: 入力欄にフォーカスがあるとき、同じ識別子の描き直し（行の作り直し）でフォーカスと選択範囲が外れない（書いている途中で止まらない）。"""
    run = play(node, html, [typing("あいうえお"), {"op": "focus", "selector": SEL["input"]}, {"op": "select", "selector": SEL["input"], "start": 1, "end": 3},
                            send(snapshot(generated_at=iso(-5))), {"op": "focus_state"}, query(SEL["input"])], snap=snapshot())
    assert run.result(4) == {"tag": "textarea", "class": "rv-input"}
    e = run.result(5)[0]
    assert e["value"] == "あいうえお" and e["selection"] == [1, 3] and e["focused"] is True


def test_d0044_ac40_focus_survives_many_rerenders(node, html):
    """D0044-AC-40: 描き直しが何度続いても、入力欄のフォーカスが保たれる。"""
    steps = [typing("abc"), {"op": "focus", "selector": SEL["input"]}]
    for i in range(5):
        steps.append(send(snapshot(generated_at=iso(-i - 1))))
    steps.append({"op": "focus_state"})
    run = play(node, html, steps, snap=snapshot())
    assert run.result(len(steps) - 1) == {"tag": "textarea", "class": "rv-input"}


def test_d0044_ac40_focus_is_not_stolen_by_a_rerender(node, html):
    """D0044-AC-40: フォーカスが入力欄に無いときの描き直しは、フォーカスを奪わない。"""
    run = play(node, html, [send(snapshot(generated_at=iso(-5))), {"op": "focus_state"}], snap=snapshot())
    assert_idle(run.frames[0])
    assert_idle(run.frames[1])
    assert run.result(1) == {"tag": "body", "class": ""}
    run = play(node, html, [{"op": "focus", "selector": SEL["approve"]}, send(snapshot(generated_at=iso(-5))), {"op": "focus_state"}], snap=snapshot())
    assert run.result(2)["tag"] in ("body", "button")
    assert run.result(2)["class"] != "rv-input"


# ---- AC-41 外の文字が入らない -----------------------------------------------------------------------------------


def test_d0044_ac41_outside_marks_never_reach_the_screen_or_the_text(node, html):
    """D0044-AC-41: ボタンの文・送る文・画面の文に、パス・セッション名・段の表示名（label）・自由な文が入らない。入るのは段と識別子と、人が入力欄に書いた文（送る文だけ）。値は textContent だけで出す。"""
    hostile = "<script>alert('HOSTILE-MARK')</script>"
    rows = [
        stage("requirements", "done", label="LABEL-MARK-1 /" + "home/someone/secret"),
        stage("design", "running", label=hostile, started_at=iso(10)),
        stage("red", "review", label="LABEL-MARK-2 " + "L" * 200, pending_since=iso(20)),
        stage("implement", label="LABEL-MARK-3"),
    ]
    snap = snapshot(rows, review={"stage": "red", "id": ID1}, name="SESSION-NAME-MARK D:/work/app")
    steps = [typing("TYPED-INPUT-MARK"), click("revise"), click("go"), {"op": "settle", "call": 0, "how": "resolve"}, query("div.review"), query("div.review *")]
    run = play(node, html, steps, snap=snap, comments={"send": "pending"})
    for i, f in enumerate(run.frames):
        assert f.message() in FIXED_OR_NONE, (i, f.message())
        for name in ("approve", "revise", "quit", "go", "back"):
            if f.els[name]:
                assert f.text(name) == LABELS[name]
    panel_text = run.result(4)[0]["text"]
    for mark in ("MARK", "SESSION", "/home", "D:/work", "TYPED", "script"):
        assert mark not in panel_text, mark
    assert [s["text"] for s in run.sends] == [expected_text("revise", "red", ID1, "TYPED-INPUT-MARK")]
    assert len(run.sends) >= 1, "sendToClaude が呼ばれていない（ボタンがまだ無い）"
    assert "HOSTILE" not in json.dumps(run.sends[0]["anchor"])
    assert run.r["final"]["html_insertions"] == 0
    assert "<script>alert('HOSTILE-MARK')</script>" in run.r["final"]["text"], "表示名は文字のまま（textContent）で出ている"


@pytest.mark.parametrize(
    "review",
    [
        {"stage": "<script>alert(1)</script>", "id": ID1},
        {"stage": "a" * 41, "id": ID1},
        {"stage": "", "id": ID1},
        {"stage": "-red", "id": ID1},
        {"stage": "_red", "id": ID1},
        {"stage": "re d", "id": ID1},
        {"stage": "red\n", "id": ID1},
        {"stage": "red ", "id": ID1},
        {"stage": "赤", "id": ID1},
        {"stage": "red", "id": ID1.upper() if ID1.upper() != ID1 else "A1B2C3D4E5"},
        {"stage": "red", "id": "A1B2C3D4E5"},
        {"stage": "red", "id": "a1b2c3d4e"},
        {"stage": "red", "id": "a1b2c3d4e5f"},
        {"stage": "red", "id": "g1b2c3d4e5"},
        {"stage": "red", "id": ""},
        {"stage": "red", "id": ID1 + "\n"},
        {"stage": "red", "id": " " + ID1},
        {"stage": "red", "id": "<script>"},
        {"stage": "red", "id": "０１２３４５６７８９"},
        {"stage": "red", "id": "x" * 10000},
    ],
    ids=sid,
)
def test_d0044_ac41_a_review_that_does_not_fit_makes_no_buttons(node, html, review):
    """D0044-AC-41: 写しの review の段・識別子が決まった形に合わない（<script>・長すぎ・大文字の16進・空・前後に空白や改行）ときは、ボタンを出さず、それで送る文を作らない。"""
    control_shows_buttons(node, html)
    rows = [stage("requirements", "done"), stage(review["stage"] if isinstance(review["stage"], str) and review["stage"] else "red", "review"), stage("tail")]
    run = play(node, html, [click("approve", force=True), click("go", force=True)], snap=snapshot(rows, review=review))
    for f in run.frames:
        assert_no_ui(f)
    assert run.sends == [] and run.anchors == [] and run.can_calls == 0


# ---- AC-42 壊れた入力 -------------------------------------------------------------------------------------------


BROKEN_REVIEWS = [
    [],
    [{"stage": "red", "id": ID1}],
    "red",
    f"red {ID1}",
    5,
    0,
    True,
    {},
    {"stage": "red"},
    {"id": ID1},
    {"stage": 5, "id": ID1},
    {"stage": "red", "id": 5},
    {"stage": None, "id": ID1},
    {"stage": "red", "id": None},
    {"stage": ["red"], "id": ID1},
    {"stage": "red", "id": [ID1]},
    {"stage": {"name": "red"}, "id": ID1},
    {"stage": "x" * 100000, "id": ID1},
    {"stage": "red", "id": "a" * 100000},
    {"stage": "red", "id": {"$": "NaN"}},
    {"stage": {"$": "Infinity"}, "id": ID1},
]


@pytest.mark.parametrize("review", BROKEN_REVIEWS, ids=sid)
def test_d0044_ac42_broken_review_values_do_not_throw_and_show_no_buttons(node, html, review):
    """D0044-AC-42: review が配列・文字列・キー欠け・型違い・巨大な文字列でも、例外を出さず、ボタンは出さない（見るだけに戻る）。タイマーは1つのまま。"""
    control_shows_buttons(node, html)
    run = play(node, html, [send(snapshot(review=review))], snap=snapshot(review=review))
    for f in run.frames:
        assert_no_ui(f)
    assert run.can_calls == 0 and run.use_calls == ["db"]
    assert run.last.view["intervals"] <= 1 and run.last.view["timeouts"] == 0


BROKEN_ROWS = {
    "status is unknown": [stage("red", "bogus")],
    "status is a number": [stage("red", 5)],
    "status is null": [stage("red", None)],
    "status is upper case": [stage("red", "REVIEW")],
    "status has a space": [stage("red", "review ")],
    "status is missing": [{k: v for k, v in stage("red", "review").items() if k != "status"}],
    "name is missing": [{k: v for k, v in stage("red", "review").items() if k != "name"}],
    "name is a number": [stage(5, "review")],
    "name differs by case": [stage("Red", "review")],
    "name is too long": [stage("red" + "x" * 200, "review")],
    "row is not an object": ["red", 5, None, ["red"]],
    "named row beyond the stage limit": [stage(f"s{i}") for i in range(30)] + [stage("red", "review")],
}


@pytest.mark.parametrize("name", list(BROKEN_ROWS))
def test_d0044_ac42_broken_rows_do_not_throw_and_show_no_buttons(node, html, name):
    """D0044-AC-42: stages の中の status が未知・名前が無い・型違い・上限の外でも、例外を出さず、ボタンは出さない。"""
    control_shows_buttons(node, html)
    snap = snapshot(BROKEN_ROWS[name], review={"stage": "red", "id": ID1})
    run = play(node, html, [send(snap)], snap=snap)
    for f in run.frames:
        assert_no_ui(f)
    assert run.can_calls == 0 and run.sends == []


def test_d0044_ac42_timer_stays_single(node, html):
    """D0044-AC-42: 動いている行・確認待ちの行・ボタンがあっても、タイマーは1つ（1000ms）のまま。確かめ・送信・戻り・失敗・描き直しでも増えない。"""
    snap = snapshot([stage("requirements", "done"), stage("design", "running", started_at=iso(30)), stage("red", "review", pending_since=iso(20)), stage("implement"), stage("test")])
    steps = [click("approve"), click("back"), typing("直して"), click("revise"), click("go"), send(snap), {"op": "advance", "ms": 3000}, {"op": "settle", "call": 0, "how": {"reject": "x"}},
             click("quit"), click("go"), send(reviewing("red", ID2)), {"op": "advance", "ms": 3000}, send(after_approval())]
    run = play(node, html, steps, snap=snap, comments={"send": "pending"})
    assert run.frames[0].view["intervals"] == 1
    for i, f in enumerate(run.frames):
        assert f.view["intervals"] <= 1 and f.view["interval_ms"] in ([], [1000]) and f.view["timeouts"] == 0, (i, f.view["intervals"], f.view["timeouts"])


def test_d0044_ac42_timer_count_is_the_same_with_and_without_buttons(node, html):
    """D0044-AC-42: ボタンがあってもなくても、タイマーの数は同じ（ボタンはタイマーを足さない）。"""
    snap = snapshot([stage("requirements", "done"), stage("design", "running", started_at=iso(30)), stage("red", "review", pending_since=iso(20))])
    with_comments_run = play(node, html, snap=snap)
    assert_idle(with_comments_run.frames[0])
    with_comments = with_comments_run.last.view
    without = play(node, html, snap=snap, comments=None).last.view
    assert (with_comments["intervals"], with_comments["interval_ms"], with_comments["timeouts"]) == (without["intervals"], without["interval_ms"], without["timeouts"]) == (1, [1000], 0)


@pytest.mark.parametrize(
    "value,stages,expected",
    [
        ({"stage": "red", "id": ID1}, [{"name": "red", "status": "review"}], {"stage": "red", "id": ID1}),
        ({"stage": "red", "id": ID1, "extra": "x"}, [{"name": "red", "status": "review"}], {"stage": "red", "id": ID1}),
        ({"stage": "make-diagram_2", "id": ID2}, [{"name": "a", "status": "done"}, {"name": "make-diagram_2", "status": "review"}], {"stage": "make-diagram_2", "id": ID2}),
        ({"stage": "red", "id": ID1}, [{"name": "red", "status": "done"}], None),
        ({"stage": "red", "id": ID1}, [{"name": "red", "status": "running"}], None),
        ({"stage": "red", "id": ID1}, [{"name": "red", "status": "unknown"}], None),
        ({"stage": "red", "id": ID1}, [{"name": "design", "status": "review"}], None),
        ({"stage": "red", "id": ID1}, [], None),
        ({"stage": "red", "id": ID1}, [{"name": "red"}], None),
        ({"stage": "red", "id": ID1}, [{"status": "review"}], None),
        ({"stage": "red", "id": "A1B2C3D4E5"}, [{"name": "red", "status": "review"}], None),
        ({"stage": "red\n", "id": ID1}, [{"name": "red\n", "status": "review"}], None),
        ({"stage": "<b>", "id": ID1}, [{"name": "<b>", "status": "review"}], None),
        ({"stage": "red", "id": ID1}, [{"name": "red", "status": "review"}, {"name": "red", "status": "done"}], {"stage": "red", "id": ID1}),
        (None, [{"name": "red", "status": "review"}], None),
        ([], [{"name": "red", "status": "review"}], None),
        ("red", [{"name": "red", "status": "review"}], None),
        (5, [{"name": "red", "status": "review"}], None),
    ],
    ids=sid,
)
def test_d0044_ac42_check_review_function(node, html, value, stages, expected):
    """D0044-AC-42: checkReview(value, stages) は、段と識別子が決まった形で、stages に同じ名前の確認待ち（status が review）の行があるときだけ {stage, id} を返す。そうでなければ null。例外を出さない。"""
    r = run_scene(node, html, steps=[{"op": "call", "fn": "checkReview", "args": [value, stages]}])
    step = r["steps"][0]
    assert step["threw"] is None, step["threw"]
    assert step["result"] == expected


# ---- AC-48 古い形の扱い ----------------------------------------------------------------------------------------


def test_d0044_ac48_a_snapshot_without_review_renders_view_only(node, html):
    """D0044-AC-48: review の無い写し（前の版が書いたもの）を新しいページが読んでも、見るだけで描ける（ボタンなし・comments を取りにいかない・前の版と同じ画面）。"""
    old = snapshot(review=NO_KEY)
    assert "review" not in old
    run = play(node, html, [send(old)], snap=old)
    for f in run.frames:
        assert_no_ui(f)
    assert run.use_calls == ["db"] and run.can_calls == 0
    assert run.last.view["text"] == baseline_text(node, html, old)
    assert "LABEL-red" in run.last.view["text"] and "SESSION-NAME-MARK" in run.last.view["text"]


def test_d0044_ac48_a_page_without_comments_ignores_review(node, html):
    """D0044-AC-48: use("comments") が null の画面は、review を足した写しでも、review 無しと同じ画面になる（review を無視する）。"""
    with_review = snapshot()
    without = snapshot(review=NO_KEY)
    a = play(node, html, snap=with_review, comments={"use": "null"}).last.view["text"]
    b = play(node, html, snap=without, comments={"use": "null"}).last.view["text"]
    c = play(node, html, snap=with_review, comments=None).last.view["text"]
    d = play(node, html, snap=without, comments=None).last.view["text"]
    assert a == b == c == d


def test_d0044_ac48_unknown_keys_in_the_snapshot_are_ignored(node, html):
    """D0044-AC-48: 写しに知らないキーが足されても（前の版のページが review を無視するのと同じ向きに）、新しいページは見た目を変えない。"""
    plain = snapshot()
    extended = snapshot(future_key={"a": 1}, other=[1, 2, 3])
    a = play(node, html, snap=plain)
    b = play(node, html, snap=extended)
    assert a.last.view["text"] == b.last.view["text"] and a.last.signature() == b.last.signature()
    assert_idle(b.last)


def test_d0044_ac48_the_page_still_renders_the_old_snapshot_text_exactly(node, html):
    """D0044-AC-48: 確認待ちの行の文字（待ち・確認待ち・経過・usage）は、ボタンがあっても前の版と同じ並びで出る（ボタンの文字は後ろに足されるだけ）。"""
    snap = snapshot([stage("requirements", "done", cost_usd=0.5, turns=3), stage("design", "running", started_at=iso(83)), stage("red", "review", pending_since=iso(40)), stage("implement"), stage("test")])
    plain = play(node, html, snap=snap, comments=None).last.view["lines"]
    with_buttons = play(node, html, snap=snap).last.view["lines"]
    assert "承認" in with_buttons and "承認" not in plain
    for ln in plain:
        assert ln in with_buttons, ln


# ================================================================================================
# AC-32 ページの JS が作る文と Python の読み取りの突き合わせ
# ================================================================================================

FEEDBACK_SAMPLES = [
    "ここを直してください",
    "日本語と English の混ざった文",
    "👍🎉🚀",
    "e\u0301 (結合文字)",
    "全角\u3000空白\u3000入り",
    "1行目\n\n3行目\n",
    "1行目\r\n2行目\r\n\r\n4行目",
    "x" * 1000,
    "😀" * 1000,
    "あ" * 1000,
    "e\u0301" * 500,
    "</script><script>alert(1)</script>",
    "`rm -rf /` $(whoami) ; a && b | c > d",
    "pipe-in: approve red a1b2c3d4e5",
    "  先頭と末尾に空白  ",
    "\t先頭がタブ\t",
    "\u3000全角で挟む\u3000",
    "tab\tinside",
    "❤️ と 🇯🇵 と 👍🏽",
    "C:/work/app/file と ../../x",
    "100% \\ \"q\" 'q'",
]


@pytest.mark.parametrize("stage_name,ident", [("red", ID1), ("design", ID2), ("make-diagram_2", ID3), ("a" * 40, "0000000000")])
@pytest.mark.parametrize("action", ACTIONS)
def test_d0044_ac32_js_text_is_read_by_the_python_parser(node, html, action, stage_name, ident):
    """D0044-AC-32: ページの JS が作る文（承認・差し戻し・中止のそれぞれ）が、Python の parse_answer でそのまま読める（動作・段・識別子・直してほしい点が一致する）。"""
    feedback = "ここを直してください\n二行目" if action == "revise" else None
    steps = ([typing(feedback)] if feedback else []) + [click(action), click("go")]
    run = play(node, html, steps, snap=reviewing(stage_name, ident))
    assert len(run.sends) == 1
    parsed = la.parse_answer(run.sends[0]["text"])
    assert parsed == la.ParseResult(True, WIRE[action], stage_name, ident, feedback, None)


@pytest.mark.parametrize("feedback", FEEDBACK_SAMPLES, ids=sid)
def test_d0044_ac32_js_feedback_is_read_back_by_the_python_parser(node, html, feedback):
    """D0044-AC-32: 直してほしい点が日本語・絵文字・結合文字・改行（空行を含む）・全角空白・1000 文字ちょうど・記号でも、JS が作る文を Python が同じ直してほしい点として読む。"""
    run = play(node, html, [typing(feedback), click("revise"), click("go")], snap=snapshot())
    assert len(run.sends) == 1, "JS の検査が通らなかった（Python が読めるのに JS が断った）"
    expected = feedback.replace("\r\n", "\n").strip()
    assert len(run.sends) >= 1, "sendToClaude が呼ばれていない（ボタンがまだ無い）"
    parsed = la.parse_answer(run.sends[0]["text"])
    assert parsed == la.ParseResult(True, "revise", "red", ID1, expected, None)


@pytest.mark.parametrize("feedback", FEEDBACK_SAMPLES, ids=sid)
def test_d0044_ac32_js_text_equals_build_answer(node, html, feedback):
    """D0044-AC-32: 逆に、JS が作る文は、同じ引数で Python の build_answer が作る文と（バイト列まで）一致する。"""
    run = play(node, html, [typing(feedback), click("revise"), click("go")], snap=snapshot())
    assert len(run.sends) >= 1, "sendToClaude が呼ばれていない（ボタンがまだ無い）"
    text = run.sends[0]["text"]
    expected = feedback.replace("\r\n", "\n").strip()
    assert text == la.build_answer("revise", "red", ID1, expected)
    assert text.encode("utf-8") == la.build_answer("revise", "red", ID1, expected).encode("utf-8")


@pytest.mark.parametrize("action", ["approve", "quit"])
def test_d0044_ac32_js_one_line_text_equals_build_answer(node, html, action):
    """D0044-AC-32: 承認・中止の1行の文も build_answer と一致する。"""
    run = play(node, html, [click(action), click("go")], snap=snapshot())
    assert len(run.sends) >= 1, "sendToClaude が呼ばれていない（ボタンがまだ無い）"
    assert run.sends[0]["text"] == la.build_answer(WIRE[action], "red", ID1)


def _validate(node_path: str, html: str, texts: list[str]) -> list[dict]:
    r = run_scene(node_path, html, steps=[{"op": "call", "fn": "validateFeedback", "args": [t]} for t in texts])
    assert r["load_error"] is None
    out = []
    for t, step in zip(texts, r["steps"]):
        assert step["threw"] is None, (t, step["threw"])
        out.append(step["result"])
    return out


def _chars_for_agreement() -> list[str]:
    stable = [*range(0x00, 0x180), *range(0x2000, 0x2070), *range(0x3000, 0x3004), *range(0xFE00, 0xFE10), *range(0xFFF0, 0x10000 - 1), 0xFEFF, 0x061C, 0x180E,
              0xE0000, 0xE0001, 0xE0020, 0xE007F, 0xE0100, 0x1F3FB, 0x1F1EF, 0x1F600, 0x10000, 0x110BD, 0xD800, 0xDBFF, 0xDC00, 0xDFFF, 0xE000, 0xF8FF, 0x0301, 0x3099, 0x1680]
    return [chr(c) for c in stable if c not in (0xFFFE, 0xFFFF) and not (0xFFF0 <= c <= 0xFFF8)]


def test_d0044_ac32_js_validation_is_not_looser_than_the_parser(node, html):
    """D0044-AC-32: ページの検査が ok と答えた文は、必ず Python の読み取りも ok で読める（ページの検査がゆるくならない。ゆるいと送ってから断られる）。文字を1つずつ前後に文字を付けて確かめる。"""
    chars = _chars_for_agreement()
    texts = [f"x{c}y" for c in chars] + [f"{c}" for c in chars] + [f"{c}x" for c in chars]
    results = _validate(node, html, texts)
    loose = []
    for text, res in zip(texts, results):
        if res["ok"]:
            parsed = la.parse_answer(f"pipe-in: revise design {ID1}\n{text}")
            if not (parsed.ok and parsed.feedback == res["text"]):
                loose.append((text, res, parsed.reason))
    assert loose == [], f"ページの検査が Python の読み取りよりゆるい: {loose[:5]}"
    assert any(r["ok"] for r in results) and any(not r["ok"] for r in results)


def test_d0044_ac32_js_and_python_agree_on_which_characters_are_bad(node, html):
    """D0044-AC-32: 文字の種類（Cc・Cf・Cs・Zl・Zp を、改行とタブを除いて断る）の判断が、JS と Python で一致する（安定した範囲の文字で）。"""
    chars = _chars_for_agreement()
    results = _validate(node, html, [f"x{c}y" for c in chars])
    wrong = []
    for c, res in zip(chars, results):
        py_bad = unicodedata.category(c) in ("Cc", "Cf", "Cs", "Zl", "Zp") and c not in "\n\t"
        if res["ok"] == py_bad or (py_bad and res["reason"] != "bad_chars"):
            wrong.append((hex(ord(c)), unicodedata.category(c), res))
    assert wrong == [], wrong[:10]


@pytest.mark.parametrize(
    "text",
    ["", " ", "\n", "\u3000", "x", "あ" * 1000, "あ" * 1001, "😀" * 1000, "😀" * 1001, " " * 20 + "x" * 1000 + " " * 20, "\r\n", "a\r\nb", "a\rb", "a\tb", "\ta\t", "a\u200bb", "👨\u200d👩", "e\u0301" * 500, "e\u0301" * 501],
    ids=sid,
)
def test_d0044_ac32_js_validation_results_match_the_parser_for_samples(node, html, text):
    """D0044-AC-32: 見本の文（空・空白だけ・上限・上限+1・CR・タブ・ゼロ幅・結合文字）で、ページの検査（ok・reason・text）と Python の読み取りの結果が一致する。"""
    (res,) = _validate(node, html, [text])
    parsed = la.parse_answer(f"pipe-in: revise design {ID1}\n{text}")
    if res["ok"]:
        assert parsed.ok and parsed.feedback == res["text"]
    else:
        assert not parsed.ok
        reason = {"empty": "need_feedback", "too_long": "feedback_too_long", "bad_chars": "bad_chars"}[res["reason"]]
        assert parsed.reason == reason, (res, parsed)


def test_d0044_ac32_js_validation_reports_the_designed_reasons_in_the_designed_order(node, html):
    """D0044-AC-32: 検査の順は 文字 → 空 → 長さ。制御文字だけの文は empty ではなく bad_chars、空白＋1001 文字は too_long。"""
    results = _validate(node, html, ["\x00", "\x00   ", "   ", "あ" * 1001 + "\x00", " " + "あ" * 1001, "", "\u200b"])
    assert [r["reason"] for r in results] == ["bad_chars", "bad_chars", "empty", "bad_chars", "too_long", "empty", "bad_chars"]
    assert [r["ok"] for r in results] == [False] * 7
    assert all(r["text"] in ("", None) for r in results)


def test_d0044_ac32_build_answer_text_matches_build_answer(node, html):
    """D0044-AC-32: ページの buildAnswerText(action, stage, id, feedback) を直接呼んでも、Python の build_answer と同じ文を返す。"""
    cases = [("approve", "design", ID1, ""), ("quit", "red", ID2, ""), ("revise", "make-diagram_2", ID3, "直して\n二行目"), ("revise", "a", "0123456789", "😀")]
    r = run_scene(node, html, steps=[{"op": "call", "fn": "buildAnswerText", "args": list(c)} for c in cases])
    for (action, stage_name, ident, feedback), step in zip(cases, r["steps"]):
        assert step["threw"] is None
        assert step["result"] == la.build_answer(WIRE[action], stage_name, ident, feedback if action == "revise" else None)


# ================================================================================================
# D0059：上の部品（札・合計・帯・更新の時刻）があっても、確認待ちの行の中は前の版と同じ
# ================================================================================================


def test_d0059_ac30_review_row_order_is_unchanged(node, html):
    """D0059-AC-30: 上に札・合計・帯・更新の時刻があっても、確認待ちの行の子の並びは 印・表示名・言葉・経過・使用量・答えのパネル のまま。上の部品は行の中に入らない。"""
    rows = [stage("requirements", "done", duration_sec=60), stage("red", "review", pending_since=iso(30), cost_usd=0.1), stage("implement")]
    run = play(node, html, [query("li.s-review > *"), query(".summary .badge"), query("li.stage .badge, li.stage .total, li.stage .bar, li.stage .updated")],
               snap=snapshot(rows, review={"stage": "red", "id": ID1}))
    assert_idle(run.frames[0])
    assert [e["attrs"]["class"] for e in run.result(0)] == ["mark", "label", "word", "elapsed", "usage", "review"]
    assert len(run.result(1)) == 1, "札が上（.summary の中）に出ていない"
    assert run.result(2) == []
