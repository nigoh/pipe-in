"""進み具合のページの HTML（Claude のアーティファクトに出す、1枚で完結するページ）。

- build_page() は引数を取らない。記録・写し・パスなど外の文字は一切入らず、呼ぶたびに同じ HTML を返す。
- 写しは HTML に埋めず、ページの JS が `await claude.use("db")` で取り、runs/current を購読して描き直す。
- 値は textContent だけで画面に出す（HTML として差し込まない）。外部の読み込みは無い。
- 色は :root のトークンにだけ書く（ライトが既定。ダークは prefers-color-scheme と data-theme で切り替える）。
- D0044：確認待ちの行に、承認・差し戻し・中止のボタンを出す（`claude.use("comments")` が使えて、写しの review が有効なときだけ）。
  押すと決まった形の文を `sendToClaude` でコメントとして送る。ボタンの部品は JS が確認待ちが現れたときに作る（_BODY は変えない）。
  画面に出す文は固定の定数だけで、段の表示名・セッション名・パスは使わない。
- D0059：上に更新の時刻・確認待ちの札・合計・進みの帯を出す。部品は JS が作る（_BODY は変えない）。色は既存のトークンだけ。
  帯の幅だけは CSSOM の style.width で入れる（写しの文字ではなく、段の数から計算した割合）。
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
  --review: #c2471f;
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
    --review: #ff8a65;
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
  --review: #c2471f;
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
  --review: #ff8a65;
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
.updated {
  margin: 0 0 0.25rem;
  color: var(--muted);
  font-size: 0.85rem;
  font-variant-numeric: tabular-nums;
}
.updated:empty {
  display: none;
}
.summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  margin: 0.75rem 0 0;
}
.summary:empty {
  display: none;
}
.badge {
  padding: 0.15rem 0.6rem;
  border: 1px solid var(--review);
  border-radius: 6px;
  color: var(--review);
  font-weight: 600;
}
.total {
  color: var(--muted);
  font-size: 0.9rem;
  font-variant-numeric: tabular-nums;
}
.bar {
  flex: 1 1 100%;
  display: flex;
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
  background: var(--line);
}
.bar > span {
  flex: 0 1 auto;
}
.bar-gap {
  flex: 0 0 2px;
  width: 2px;
}
.bar-done {
  background: var(--ok);
}
.bar-pending {
  background: var(--review);
}
[hidden] {
  display: none;
}
.review {
  flex: 1 1 100%;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.25rem;
}
.rv-input {
  width: 100%;
  resize: vertical;
  font: inherit;
  padding: 0.5rem;
  border: 1px solid var(--line);
  color: var(--fg);
  background: var(--bg);
}
.rv-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.rv-btn {
  min-height: 2.75rem;
  padding: 0.4rem 0.9rem;
  border: 1px solid var(--line);
  border-radius: 0.375rem;
  background: var(--bg);
  color: var(--fg);
  font: inherit;
  cursor: pointer;
}
.rv-approve {
  border-color: var(--ok);
}
.rv-quit {
  border-color: var(--ng);
}
.rv-go {
  border-width: 2px;
  border-color: var(--run);
}
.rv-btn:disabled {
  border-style: dashed;
  color: var(--muted);
  cursor: not-allowed;
}
.rv-btn:focus-visible,
.rv-input:focus-visible {
  outline: 2px solid var(--run);
  outline-offset: 2px;
}
.rv-msg {
  margin: 0;
  color: var(--fg);
}
.rv-msg:empty {
  display: none;
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
  .rv-btn,
  .rv-input {
    transition: border-color 0.15s ease, background-color 0.15s ease;
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
var UPDATED_WORD = " 更新";
var TOTAL_WORD = "合計 ";
var BADGE_WORD = "確認待ち：";

var MAX_FEEDBACK = 1000;
var STAGE_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$/;
var ID_RE = /^[0-9a-f]{10}$/;
var BAD_CHARS = /[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u;
var ASK = {
  approve: "この段を承認しますか",
  revise: "この直してほしい点で差し戻しますか",
  quit: "この実行を中止しますか"
};
var SENDING_MSG = "送っています…";
var SENT_MSG = "送りました（会話の返事を待っています）";
var INVALID = {
  empty: "直してほしい点を書いてください",
  too_long: "1000 文字以内にしてください",
  bad_chars: "使えない文字（制御文字・見えない文字）が入っています"
};
var BLOCKED = {
  writers_only: "この画面からは答えを送れません（アーティファクトの編集者だけが送れます）。会話で答えてください。",
  no_session: "答えを受け取れる Claude の会話が今ありません。会話で答えてください。",
  off: "この画面では答えを送る機能が使えません。会話で答えてください。"
};
var GENERIC_MSG = "この画面からは答えを送れません。会話で答えてください。";
var FORBIDDEN_MSG = "この画面からは送れません（許可されていません）。会話で答えてください。";
var CONSENT_MSG = "同意が確認できなかったため、送られていません。もう一度押すか、会話で答えてください。";
var RATE_MSG = "続けて送りすぎです。少し待ってからやり直すか、会話で答えてください。";
var FAILED_MSG = "送れませんでした。もう一度押すか、会話で答えてください。";
var ANCHOR_FAILED = "場所を取れませんでした。会話で答えてください。";

var STATUS = {
  waiting: { mark: "", word: "まだ" },
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

var rv = {
  key: null,
  review: null,
  gen: 0,
  can: "none",
  blockText: "",
  phase: "idle",
  action: null,
  anchor: null,
  notice: ""
};
var commentsPromise = null;
var commentsApi = null;
var ui = null;
var reviewRow = null;

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
      name: name,
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
  var final = typeof value.final === "string" && has(FINALS, value.final) ? value.final : null;
  return {
    empty: value.empty === true,
    name: clip(value.name),
    final: final,
    stages: stages,
    review: final === null ? checkReview(value.review, stages) : null,
    generatedAt: typeof value.generated_at === "string" ? value.generated_at : null
  };
}

function checkReview(value, stages) {
  try {
    if (!isObject(value) || !Array.isArray(stages)) return null;
    var stage = value.stage;
    var id = value.id;
    if (typeof stage !== "string" || typeof id !== "string") return null;
    if (stage.length > 40 || id.length !== 10 || !STAGE_RE.test(stage) || !ID_RE.test(id)) return null;
    for (var i = 0; i < stages.length; i++) {
      var row = stages[i];
      if (isObject(row) && row.name === stage && row.status === "review") return { stage: stage, id: id };
    }
    return null;
  } catch (e) {
    return null;
  }
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
  if (stage.attempt !== null && stage.attempt >= 2) li.appendChild(el("span", "attempt", stage.attempt + "回目"));
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

function updatedText(text) {
  try {
    var ms = parseTime(text);
    if (ms === null) return "";
    var dt = new Date(ms);
    var h = dt.getHours();
    var m = dt.getMinutes();
    if (!isFinite(h) || !isFinite(m)) return "";
    return pad2(h) + ":" + pad2(m) + UPDATED_WORD;
  } catch (e) {
    return "";
  }
}

function totalText(stages) {
  if (!Array.isArray(stages)) return "";
  var cost = 0;
  var turns = 0;
  var sec = 0;
  for (var i = 0; i < stages.length; i++) {
    var s = stages[i];
    if (isPositive(s.cost)) cost += s.cost;
    if (isPositive(s.turns)) turns += Math.floor(s.turns);
    if (s.duration !== null) sec += s.duration;
  }
  var parts = [];
  if (isPositive(cost)) parts.push("$" + Number(cost.toFixed(4)));
  if (isPositive(turns)) parts.push(turns + "ターン");
  if (isPositive(sec)) parts.push(fmtElapsed(sec));
  return parts.length === 0 ? "" : TOTAL_WORD + parts.join(" ・ ");
}

function pct(k, n) {
  return Number((k * 100 / n).toFixed(4)) + "%";
}

function barParts(stages) {
  var n = Array.isArray(stages) ? stages.length : 0;
  if (n === 0) return [];
  var done = 0;
  var pend = 0;
  for (var i = 0; i < n; i++) {
    if (stages[i].status === "done") done += 1;
    else if (stages[i].status === "review") pend += 1;
  }
  var list = [];
  if (done > 0) list.push({ kind: "done", width: pct(done, n) });
  if (done > 0 && pend > 0) list.push({ kind: "gap", width: null });
  if (pend > 0) list.push({ kind: "pending", width: pct(pend, n) });
  return list;
}

function badgeText(snap) {
  if (!isObject(snap) || snap.final !== null || !Array.isArray(snap.stages)) return "";
  for (var i = 0; i < snap.stages.length; i++) {
    if (snap.stages[i].status === "review") return BADGE_WORD + snap.stages[i].label;
  }
  return "";
}

var topParts = null;

function ensureTop() {
  if (topParts !== null) return topParts;
  var name = byId("name");
  var list = byId("stages");
  if (!name || !list) return null;
  topParts = { updated: el("p", "updated"), summary: el("div", "summary") };
  name.before(topParts.updated);
  list.before(topParts.summary);
  return topParts;
}

function drawTop(snap, generatedAt) {
  try {
    var parts = ensureTop();
    if (parts === null) return;
    parts.updated.textContent = updatedText(generatedAt);
    var items = [];
    if (snap !== null && snap.stages.length > 0) {
      var badge = badgeText(snap);
      if (badge !== "") items.push(el("span", "badge", badge));
      var total = totalText(snap.stages);
      if (total !== "") items.push(el("span", "total", total));
      var bar = el("div", "bar");
      bar.setAttribute("aria-hidden", "true");
      var pieces = barParts(snap.stages);
      for (var i = 0; i < pieces.length; i++) {
        var node = el("span", "bar-" + pieces[i].kind);
        if (pieces[i].width !== null) node.style.width = pieces[i].width;
        bar.appendChild(node);
      }
      items.push(bar);
    }
    parts.summary.replaceChildren.apply(parts.summary, items);
  } catch (e) {
    /* 上の部品を描けなくても、段の行は残す */
  }
}

function show(message, generatedAt) {
  counters = [];
  byId("name").textContent = "";
  byId("final").textContent = "";
  byId("stages").replaceChildren();
  byId("msg").textContent = message;
  drawTop(null, generatedAt);
  reviewRow = null;
  setReview(null);
  syncPanel();
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
      show(EMPTY_MSG, snap.generatedAt);
      return;
    }
    var found = [];
    var rows = [];
    var mine = null;
    for (var i = 0; i < snap.stages.length; i++) {
      var row = buildRow(snap.stages[i], found);
      rows.push(row);
      var s = snap.stages[i];
      if (mine === null && snap.review !== null && s.name === snap.review.stage && s.status === "review") mine = row;
    }
    var memo = rememberFocus();
    byId("stages").replaceChildren.apply(byId("stages"), rows);
    byId("name").textContent = snap.name;
    byId("final").textContent = snap.final === null ? "" : "結果: " + FINALS[snap.final];
    drawTop(snap, snap.generatedAt);
    byId("msg").textContent = "";
    counters = found;
    reviewRow = mine;
    setReview(snap.review);
    syncPanel();
    restoreFocus(memo);
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

function noop() {}

function validateFeedback(text) {
  var s = typeof text === "string" ? text.replace(/\r\n/g, "\n") : "";
  if (BAD_CHARS.test(s.replace(/[\n\t]/g, ""))) return { ok: false, reason: "bad_chars", text: "" };
  s = s.trim();
  if (s === "") return { ok: false, reason: "empty", text: "" };
  if (Array.from(s).length > MAX_FEEDBACK) return { ok: false, reason: "too_long", text: "" };
  return { ok: true, reason: null, text: s };
}

function buildAnswerText(action, stage, id, feedback) {
  if (action !== "approve" && action !== "revise" && action !== "quit") throw new Error("action");
  if (typeof stage !== "string" || !STAGE_RE.test(stage) || typeof id !== "string" || !ID_RE.test(id)) throw new Error("review");
  var head = "pipe-in: " + action + " " + stage + " " + id;
  return action === "revise" ? head + "\n" + feedback : head;
}

function ensureComments() {
  if (commentsPromise === null) {
    commentsPromise = (async () => {
      try {
        var c = await claude.use("comments");
        return c ? c : null;
      } catch (e) {
        return null;
      }
    })();
  }
  return commentsPromise;
}

function setReview(review) {
  var key = review === null ? null : review.stage + "\n" + review.id;
  if (key === rv.key) {
    rv.review = review;
    return;
  }
  rv.gen += 1;
  rv.key = key;
  rv.review = review;
  rv.can = "none";
  rv.blockText = "";
  rv.phase = "idle";
  rv.action = null;
  rv.anchor = null;
  rv.notice = "";
  if (ui !== null) ui.input.value = "";
  if (key !== null) startCheck();
}

function startCheck() {
  var gen = rv.gen;
  rv.can = "checking";
  ensureComments()
    .then((c) => {
      if (gen !== rv.gen) return null;
      if (c === null) {
        rv.can = "none";
        syncPanel();
        return null;
      }
      commentsApi = c;
      var asked;
      try {
        asked = Promise.resolve(c.canSendToClaude());
      } catch (e) {
        asked = Promise.reject(e);
      }
      return asked.then(
        (v) => settleCheck(gen, v),
        () => settleCheck(gen, null)
      );
    })
    .catch(noop);
}

function settleCheck(gen, answer) {
  if (gen !== rv.gen) return;
  if (answer === "available") {
    rv.can = "available";
  } else {
    rv.can = "blocked";
    rv.blockText = typeof answer === "string" && has(BLOCKED, answer) ? BLOCKED[answer] : GENERIC_MSG;
  }
  syncPanel();
}

function makeButton(cls, label, handler) {
  var b = el("button", "rv-btn " + cls, label);
  b.setAttribute("type", "button");
  b.addEventListener("click", handler);
  return b;
}

function buildPanel() {
  var box = el("div", "review");
  box.setAttribute("role", "group");
  box.setAttribute("aria-label", "確認待ちの答え");
  var input = el("textarea", "rv-input");
  input.setAttribute("maxlength", "1000");
  input.setAttribute("rows", "3");
  input.setAttribute("aria-label", "直してほしい点（差し戻すときだけ）");
  var msg = el("p", "rv-msg");
  msg.setAttribute("role", "status");
  msg.setAttribute("aria-live", "polite");
  var row = el("div", "rv-row");
  var parts = {
    box: box,
    input: input,
    msg: msg,
    row: row,
    approve: makeButton("rv-approve", "承認", () => onAction("approve").catch(noop)),
    revise: makeButton("rv-revise", "直してほしい点を書いて差し戻す", () => onAction("revise").catch(noop)),
    quit: makeButton("rv-quit", "中止", () => onAction("quit").catch(noop)),
    go: makeButton("rv-go", "実行する", () => onGo()),
    back: makeButton("rv-back", "戻る", () => onBack())
  };
  row.appendChild(parts.approve);
  row.appendChild(parts.revise);
  row.appendChild(parts.quit);
  row.appendChild(parts.go);
  row.appendChild(parts.back);
  box.appendChild(input);
  box.appendChild(msg);
  box.appendChild(row);
  return parts;
}

function attachPanel(li) {
  if (ui.box.parentNode !== li) li.appendChild(ui.box);
}

function currentMessage() {
  if (rv.can === "blocked") return rv.blockText;
  if (rv.phase === "confirm") return has(ASK, rv.action) ? ASK[rv.action] : "";
  if (rv.phase === "sending") return SENDING_MSG;
  if (rv.phase === "sent") return SENT_MSG;
  if (rv.phase === "preparing") return "";
  return rv.notice;
}

function syncPanel() {
  try {
    var visible = (rv.can === "available" || rv.can === "blocked") && rv.key !== null && reviewRow !== null;
    if (!visible) {
      if (ui !== null && ui.box.parentNode) ui.box.remove();
      return;
    }
    if (ui === null) ui = buildPanel();
    attachPanel(reviewRow);
    var blocked = rv.can === "blocked";
    var idle = rv.phase === "idle";
    var checking = rv.phase === "confirm";
    ui.row.hidden = blocked;
    ui.input.hidden = blocked;
    ui.input.disabled = !idle;
    var names = ["approve", "revise", "quit"];
    for (var i = 0; i < names.length; i++) {
      ui[names[i]].hidden = blocked || checking;
      ui[names[i]].disabled = !idle;
    }
    ui.go.hidden = !checking;
    ui.go.disabled = !checking;
    ui.back.hidden = !checking;
    ui.back.disabled = !checking;
    ui.msg.textContent = currentMessage();
  } catch (e) {
    /* 画面を作れなくても、見るだけの表示は残す */
  }
}

function rememberFocus() {
  try {
    if (ui === null) return null;
    var active = document.activeElement;
    if (!active || !ui.box.contains(active)) return null;
    return { node: active, from: active.selectionStart, to: active.selectionEnd };
  } catch (e) {
    return null;
  }
}

function restoreFocus(memo) {
  try {
    if (memo === null || ui === null || !ui.box.contains(memo.node)) return;
    memo.node.focus();
    if (memo.node === ui.input && typeof memo.from === "number" && typeof memo.to === "number") ui.input.setSelectionRange(memo.from, memo.to);
  } catch (e) {
    /* 戻せなくても何もしない */
  }
}

async function onAction(action) {
  if (rv.phase !== "idle" || rv.can !== "available" || ui === null || commentsApi === null) return;
  if (action !== "approve" && action !== "revise" && action !== "quit") return;
  if (action === "revise") {
    var checked = validateFeedback(ui.input.value);
    if (!checked.ok) {
      rv.notice = INVALID[checked.reason];
      syncPanel();
      return;
    }
  }
  var gen = rv.gen;
  rv.phase = "preparing";
  rv.action = action;
  rv.notice = "";
  syncPanel();
  var anchor = null;
  var failed = false;
  try {
    anchor = await commentsApi.anchorFor(ui.box);
  } catch (e) {
    failed = true;
  }
  if (gen !== rv.gen) return;
  if (failed || anchor === null || typeof anchor !== "object") {
    rv.phase = "idle";
    rv.notice = ANCHOR_FAILED;
    syncPanel();
    return;
  }
  rv.anchor = anchor;
  rv.phase = "confirm";
  syncPanel();
  ui.go.focus();
}

function onBack() {
  if (rv.phase !== "confirm" || ui === null) return;
  var action = rv.action;
  rv.phase = "idle";
  rv.anchor = null;
  rv.notice = "";
  syncPanel();
  if (action !== null && ui[action]) ui[action].focus();
}

function onGo() {
  if (rv.phase !== "confirm" || rv.anchor === null || rv.review === null || ui === null || commentsApi === null) return;
  var gen = rv.gen;
  var anchor = rv.anchor;
  var text = "";
  try {
    var feedback = "";
    if (rv.action === "revise") {
      var checked = validateFeedback(ui.input.value);
      if (!checked.ok) throw new Error("feedback");
      feedback = checked.text;
    }
    text = buildAnswerText(rv.action, rv.review.stage, rv.review.id, feedback);
  } catch (e) {
    rv.phase = "idle";
    rv.anchor = null;
    rv.notice = FAILED_MSG;
    syncPanel();
    return;
  }
  rv.phase = "sending";
  rv.anchor = null;
  rv.notice = "";
  var sent;
  try {
    sent = commentsApi.sendToClaude({ anchor: anchor, text: text });
  } catch (e) {
    sent = Promise.reject(e);
  }
  syncPanel();
  Promise.resolve(sent).then(
    () => afterSend(gen, true, null),
    (err) => afterSend(gen, false, err)
  );
}

function failureCode(err) {
  try {
    return isObject(err) && typeof err.code === "string" ? err.code : "";
  } catch (e) {
    return "";
  }
}

function afterSend(gen, succeeded, err) {
  if (gen !== rv.gen) return;
  if (succeeded) {
    rv.phase = "sent";
    syncPanel();
    return;
  }
  var code = failureCode(err);
  rv.phase = "idle";
  if (code === "forbidden") {
    rv.can = "blocked";
    rv.blockText = FORBIDDEN_MSG;
  } else if (code === "consent_required") {
    rv.notice = CONSENT_MSG;
  } else if (code === "rate_limited") {
    rv.notice = RATE_MSG;
  } else {
    rv.notice = FAILED_MSG;
  }
  syncPanel();
  if (rv.can === "available" && ui !== null && rv.action !== null && ui[rv.action]) ui[rv.action].focus();
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
