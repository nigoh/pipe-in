"""進み具合のページの HTML（Claude のアーティファクトに出す、1枚で完結するページ）。

- build_page() は引数を取らない。記録・写し・パスなど外の文字は一切入らず、呼ぶたびに同じ HTML を返す。
- 写しは HTML に埋めず、ページの JS が `await claude.use("db")` で取り、runs/current を購読して描き直す。
- 値は textContent だけで画面に出す（HTML として差し込まない）。外部の読み込みは無い。
- 色は :root のトークンにだけ書く（ライトが既定。ダークは prefers-color-scheme と data-theme で切り替える）。
標準ライブラリだけを使う（依存の向きは docs/development/design.md）。
"""

from __future__ import annotations

_CSS = r"""
:root {
  --bg: #ffffff;
  --fg: #1f2328;
  --muted: #59636e;
  --line: #d1d9e0;
  --run: #0969da;
  --review: #9a6700;
  --ok: #1a7f37;
  --ng: #cf222e;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0d1117;
    --fg: #e6edf3;
    --muted: #8b949e;
    --line: #30363d;
    --run: #58a6ff;
    --review: #d29922;
    --ok: #3fb950;
    --ng: #f85149;
    color-scheme: dark;
  }
}
:root[data-theme="light"] {
  --bg: #ffffff;
  --fg: #1f2328;
  --muted: #59636e;
  --line: #d1d9e0;
  --run: #0969da;
  --review: #9a6700;
  --ok: #1a7f37;
  --ng: #cf222e;
  color-scheme: light;
}
:root[data-theme="dark"] {
  --bg: #0d1117;
  --fg: #e6edf3;
  --muted: #8b949e;
  --line: #30363d;
  --run: #58a6ff;
  --review: #d29922;
  --ok: #3fb950;
  --ng: #f85149;
  color-scheme: dark;
}
* {
  box-sizing: border-box;
  max-width: 100%;
  min-width: 0;
  overflow-wrap: anywhere;
}
html {
  background: var(--bg);
}
body {
  margin: 0;
  padding: 1rem;
  background: var(--bg);
  color: var(--fg);
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", "Hiragino Sans", "Noto Sans JP", sans-serif;
}
main {
  max-width: 44rem;
  margin: 0 auto;
}
h1 {
  margin: 0 0 0.5rem;
  font-size: 1.1rem;
  color: var(--muted);
}
#name {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
}
#final,
#msg {
  margin: 0.25rem 0 0;
  color: var(--muted);
}
#stages {
  list-style: none;
  margin: 1rem 0 0;
  padding: 0;
}
.stage {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.25rem 0.75rem;
  padding: 0.6rem 0;
  border-top: 1px solid var(--line);
}
.mark {
  flex: 0 0 auto;
  width: 1rem;
  height: 1rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  line-height: 1;
  font-weight: 700;
  color: var(--muted);
}
.label {
  flex: 1 1 8rem;
  font-weight: 600;
}
.word,
.attempt,
.verdict,
.usage {
  color: var(--muted);
  font-size: 0.9rem;
}
.elapsed {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.s-running .mark,
.s-running .elapsed {
  color: var(--run);
}
.s-review .mark,
.s-review .elapsed,
.s-revised .mark {
  color: var(--review);
}
.s-done .mark {
  color: var(--ok);
}
.s-failed .mark {
  color: var(--ng);
}
.s-waiting .mark,
.s-running .mark,
.s-review .mark {
  border-radius: 50%;
}
.s-waiting .mark {
  border: 2px solid var(--muted);
}
.s-running .mark {
  background: var(--run);
}
.s-review .mark {
  border: 2px solid var(--review);
  background: linear-gradient(90deg, var(--review) 50%, transparent 50%);
}
@media (prefers-reduced-motion: no-preference) {
  @keyframes pulse {
    50% {
      opacity: 0.35;
    }
  }
  .s-running .mark {
    animation: pulse 1.6s ease-in-out infinite;
  }
}
"""

_BODY = r"""
<main>
<h1>進み具合</h1>
<p id="name"></p>
<p id="final"></p>
<p id="msg" role="status" aria-live="polite"></p>
<ol id="stages"></ol>
</main>
"""

_JS = r"""
"use strict";

var MAX_STAGES = 24;
var MAX_TEXT = 80;
var MAX_ELAPSED = 359999;
var MAX_NUMBER = 1e9;
var EMPTY_MSG = "まだ記録がありません";
var UNREADABLE_MSG = "この画面では読めません";
var UNSUPPORTED_MSG = "この写しの版には対応していません";
var LOADING_MSG = "読み込み中…";
var NO_NAME = "（名前なし）";

var STATUS = {
  waiting: { mark: "", word: "待ち" },
  running: { mark: "", word: "実行中" },
  review: { mark: "", word: "確認待ち" },
  done: { mark: "✓", word: "完了" },
  failed: { mark: "✕", word: "失敗" },
  revised: { mark: "↩", word: "差し戻し" },
  unknown: { mark: "？", word: "不明" }
};
var FINALS = {
  PASSED: "合格",
  TEST_FAILED: "検証で不合格",
  STOPPED_BY_HUMAN: "人が止めた",
  STAGE_ERROR: "段でエラー",
  BLOCKED: "進められない"
};
var VERDICTS = { pass: "合格", fail: "不合格", blocked: "進められない" };
var TIME_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$/;

var counters = [];
var timerId = null;

function has(obj, key) {
  return Object.prototype.hasOwnProperty.call(obj, key);
}

function isObject(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function clip(v) {
  if (typeof v !== "string") return "";
  if (v.length <= MAX_TEXT) return v;
  var chars = Array.from(v.slice(0, MAX_TEXT * 2));
  return chars.length <= MAX_TEXT ? chars.join("") : chars.slice(0, MAX_TEXT - 1).join("") + "…";
}

function okNumber(v) {
  return typeof v === "number" && isFinite(v) && v >= 0 && v <= MAX_NUMBER ? v : null;
}

function okAttempt(v) {
  return typeof v === "number" && Number.isInteger(v) && v >= 1 && v <= 999 ? v : null;
}

function parseTime(text) {
  if (typeof text !== "string" || text.length > 40) return null;
  var m = TIME_RE.exec(text);
  if (m === null) return null;
  var y = Number(m[1]);
  var mo = Number(m[2]);
  var d = Number(m[3]);
  var h = Number(m[4]);
  var mi = Number(m[5]);
  var s = Number(m[6]);
  if (mo < 1 || mo > 12 || h > 23 || mi > 59 || s > 59) return null;
  var dt = new Date(0);
  dt.setUTCFullYear(y, mo - 1, d);
  if (dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) return null;
  dt.setUTCHours(h, mi, s, 0);
  var ms = dt.getTime();
  if (m[7] !== "Z") {
    var oh = Number(m[7].slice(1, 3));
    var om = Number(m[7].slice(4, 6));
    if (oh > 23 || om > 59) return null;
    var off = (oh * 60 + om) * 60000;
    ms -= m[7].charAt(0) === "-" ? -off : off;
  }
  return isFinite(ms) ? ms : null;
}

function elapsedSec(text, nowMs) {
  var t = parseTime(text);
  if (t === null || typeof nowMs !== "number" || !isFinite(nowMs)) return null;
  var sec = Math.floor((nowMs - t) / 1000);
  if (sec < 0) return 0;
  return sec > MAX_ELAPSED ? MAX_ELAPSED : sec;
}

function pad2(n) {
  return n < 10 ? "0" + n : String(n);
}

function fmtElapsed(sec) {
  if (typeof sec !== "number" || !isFinite(sec) || sec < 0) return "0:00";
  var total = Math.floor(sec);
  if (total > MAX_ELAPSED) total = MAX_ELAPSED;
  var h = Math.floor(total / 3600);
  var m = Math.floor((total % 3600) / 60);
  var s = total % 60;
  return h > 0 ? h + ":" + pad2(m) + ":" + pad2(s) : m + ":" + pad2(s);
}

function checkSnapshot(value) {
  if (!isObject(value) || value.schema !== 1 || !Array.isArray(value.stages)) return null;
  var stages = [];
  var list = value.stages;
  for (var i = 0; i < list.length && stages.length < MAX_STAGES; i++) {
    var e = list[i];
    if (!isObject(e)) continue;
    var status = typeof e.status === "string" && has(STATUS, e.status) ? e.status : "unknown";
    var name = clip(e.name);
    stages.push({
      label: clip(e.label) || name || NO_NAME,
      status: status,
      attempt: okAttempt(e.attempt),
      startedAt: typeof e.started_at === "string" ? e.started_at : null,
      pendingSince: typeof e.pending_since === "string" ? e.pending_since : null,
      verdict: typeof e.verdict === "string" && has(VERDICTS, e.verdict) ? e.verdict : null,
      cost: okNumber(e.cost_usd),
      turns: okNumber(e.turns),
      duration: okNumber(e.duration_sec)
    });
  }
  return {
    empty: value.empty === true,
    name: clip(value.name),
    final: typeof value.final === "string" && has(FINALS, value.final) ? value.final : null,
    stages: stages
  };
}

function el(tag, className, text) {
  var node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function isPositive(v) {
  return typeof v === "number" && isFinite(v) && v > 0;
}

function usageText(stage) {
  var parts = [];
  if (isPositive(stage.cost)) parts.push("$" + Number(stage.cost.toFixed(4)));
  if (isPositive(stage.turns)) parts.push(Math.floor(stage.turns) + "ターン");
  if (stage.duration !== null) parts.push(fmtElapsed(stage.duration));
  return parts.join(" ・ ");
}

function buildRow(stage, found) {
  var info = STATUS[stage.status];
  var li = el("li", "stage s-" + stage.status);
  var mark = el("span", "mark", info.mark);
  mark.setAttribute("aria-hidden", "true");
  li.appendChild(mark);
  li.appendChild(el("span", "label", stage.label));
  li.appendChild(el("span", "word", info.word));
  if (stage.attempt !== null) li.appendChild(el("span", "attempt", stage.attempt + "回目"));
  var since = stage.status === "running" ? stage.startedAt : stage.status === "review" ? stage.pendingSince : null;
  if (since !== null && parseTime(since) !== null) {
    var span = el("span", "elapsed", "0:00");
    li.appendChild(span);
    found.push({ el: span, since: since });
  }
  if (stage.verdict !== null) li.appendChild(el("span", "verdict", "判定: " + VERDICTS[stage.verdict]));
  var usage = usageText(stage);
  if (usage !== "") li.appendChild(el("span", "usage", usage));
  return li;
}

function byId(id) {
  return document.getElementById(id);
}

function show(message) {
  counters = [];
  byId("name").textContent = "";
  byId("final").textContent = "";
  byId("stages").replaceChildren();
  byId("msg").textContent = message;
  syncTimer();
}

function render(value) {
  try {
    var snap = checkSnapshot(value);
    if (snap === null) {
      var unsupported = isObject(value) && typeof value.schema === "number" && value.schema !== 1;
      show(unsupported ? UNSUPPORTED_MSG : EMPTY_MSG);
      return;
    }
    if (snap.empty) {
      show(EMPTY_MSG);
      return;
    }
    var found = [];
    var rows = [];
    for (var i = 0; i < snap.stages.length; i++) rows.push(buildRow(snap.stages[i], found));
    byId("stages").replaceChildren.apply(byId("stages"), rows);
    byId("name").textContent = snap.name;
    byId("final").textContent = snap.final === null ? "" : "結果: " + FINALS[snap.final];
    byId("msg").textContent = "";
    counters = found;
    tick();
    syncTimer();
  } catch (e) {
    /* 描き直しに失敗しても、直前の画面を残す */
  }
}

function tick() {
  var now = Date.now();
  for (var i = 0; i < counters.length; i++) {
    var sec = elapsedSec(counters[i].since, now);
    counters[i].el.textContent = fmtElapsed(sec === null ? 0 : sec);
  }
}

function syncTimer() {
  var want = counters.length > 0 && !document.hidden;
  if (want && timerId === null) {
    timerId = setInterval(tick, 1000);
  } else if (!want && timerId !== null) {
    clearInterval(timerId);
    timerId = null;
  }
}

function onVisibility() {
  try {
    if (!document.hidden) tick();
    syncTimer();
  } catch (e) {
    /* 何もしない */
  }
}

function readSnap(snap) {
  try {
    if (!isObject(snap) || snap.exists !== true || typeof snap.data !== "function") return null;
    return snap.data();
  } catch (e) {
    return null;
  }
}

function watch(db) {
  db.doc("runs/current").onSnapshot(
    (snap) => render(readSnap(snap)),
    () => {
      byId("msg").textContent = "更新を受け取れませんでした";
    }
  );
}

async function main() {
  document.addEventListener("visibilitychange", onVisibility);
  byId("msg").textContent = LOADING_MSG;
  var db = null;
  try {
    db = await claude.use("db");
  } catch (e) {
    db = null;
  }
  if (!db) {
    show(UNREADABLE_MSG);
    return;
  }
  try {
    watch(db);
  } catch (e) {
    show(UNREADABLE_MSG);
  }
}

main().catch(() => {});
"""


def build_page() -> str:
    """進み具合のページの HTML を返す。引数は取らない（外の文字を入れない）。"""
    return (
        "<!doctype html>\n"
        '<html lang="ja">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>進み具合</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n"
        f"<body>{_BODY}"
        f"<script>{_JS}</script>\n"
        "</body>\n"
        "</html>\n"
    )
