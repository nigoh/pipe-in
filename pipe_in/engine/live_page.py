"""進み具合のページの HTML（Claude のアーティファクトに出す、1枚で完結するページ）。

- build_page() は引数を取らない。記録・写し・パスなど外の文字は一切入らず、呼ぶたびに同じ HTML を返す。
- 写しは HTML に埋めず、ページの JS が `await claude.use("db")` で取り、runs/current を購読して描き直す。
- 値は textContent だけで画面に出す（HTML として差し込まない）。
- 外部の読み込みは、Google Fonts の <link> 2本（計画ボードと同じ文字）と、アイコンを作る createElementNS の SVG の名前空間 1 か所だけ（D0059）。
- 色は :root のトークンにだけ書く（ライトが既定。ダークは prefers-color-scheme と data-theme で切り替える）。
- D0059：デザイン「プラグ」（docs/design/）を入れた。状態はアイコン（SVG）と言葉、帯は模様で伝える。写しの項目は足さない。
- D0044：確認待ちの行に、承認・差し戻し・中止のボタンを出す（`claude.use("comments")` が使えて、写しの review が有効なときだけ）。
  押すと決まった形の文を `sendToClaude` でコメントとして送る。ボタンの部品は JS が確認待ちが現れたときに作る（_BODY は変えない）。
  画面に出す文は固定の定数だけで、段の表示名・セッション名・パスは使わない。
標準ライブラリだけを使う（依存の向きは docs/development/design.md）。
"""

from __future__ import annotations

# 計画ボード（.claude/skills/pipe-plan/board.html）の <head> と同じ2行。tests/test_live_page.py が文字を突き合わせる
_FONT_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700'
    '&family=JetBrains+Mono:wght@400;600&display=swap">\n'
)

_CSS = r"""
:root {
  --bg: #f6f6f4;
  --panel: #ffffff;
  --col: #ecebe7;
  --line: #e4ded8;
  --fg: #23201e;
  --muted: #6b625c;
  --coral: #c2471f;
  --coral-soft: #fde6dd;
  --coral-text: #a83a17;
  --on-coral: #ffffff;
  --teal: #167d6b;
  --teal-soft: #dcefe9;
  --teal-text: #0f5a4d;
  --blue: #3f6fb0;
  --bad: #b3261e;
  --bad-soft: #fbe2df;
  --bad-text: #9a1f18;
  --ok: #2e7d32;
  --ok-soft: #e3f1e3;
  --ok-text: #22652a;
  --shadow: 0 1px 2px rgba(35, 32, 30, .08);
  --f-body: "Zen Kaku Gothic New", "Hiragino Sans", "Yu Gothic UI", "Noto Sans JP", system-ui, sans-serif;
  --f-mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
  --r-tag: 6px;
  --r-card: 10px;
  --r-panel: 14px;
  --r-chip: 999px;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #161514;
    --panel: #211f1d;
    --col: #1d1b19;
    --line: #36322f;
    --fg: #f2ece6;
    --muted: #ada39b;
    --coral: #ff8a65;
    --coral-soft: #4a2316;
    --coral-text: #ffb59c;
    --on-coral: #2a140b;
    --teal: #5fc4ab;
    --teal-soft: #15392f;
    --teal-text: #8fe0c6;
    --blue: #8db4ee;
    --bad: #ff8a80;
    --bad-soft: #4a1f1c;
    --bad-text: #ffb4ab;
    --ok: #81c784;
    --ok-soft: #1e3a20;
    --ok-text: #a5d6a7;
    --shadow: 0 1px 2px rgba(0, 0, 0, .45);
    color-scheme: dark;
  }
}
:root[data-theme="light"] {
  --bg: #f6f6f4;
  --panel: #ffffff;
  --col: #ecebe7;
  --line: #e4ded8;
  --fg: #23201e;
  --muted: #6b625c;
  --coral: #c2471f;
  --coral-soft: #fde6dd;
  --coral-text: #a83a17;
  --on-coral: #ffffff;
  --teal: #167d6b;
  --teal-soft: #dcefe9;
  --teal-text: #0f5a4d;
  --blue: #3f6fb0;
  --bad: #b3261e;
  --bad-soft: #fbe2df;
  --bad-text: #9a1f18;
  --ok: #2e7d32;
  --ok-soft: #e3f1e3;
  --ok-text: #22652a;
  --shadow: 0 1px 2px rgba(35, 32, 30, .08);
  color-scheme: light;
}
:root[data-theme="dark"] {
  --bg: #161514;
  --panel: #211f1d;
  --col: #1d1b19;
  --line: #36322f;
  --fg: #f2ece6;
  --muted: #ada39b;
  --coral: #ff8a65;
  --coral-soft: #4a2316;
  --coral-text: #ffb59c;
  --on-coral: #2a140b;
  --teal: #5fc4ab;
  --teal-soft: #15392f;
  --teal-text: #8fe0c6;
  --blue: #8db4ee;
  --bad: #ff8a80;
  --bad-soft: #4a1f1c;
  --bad-text: #ffb4ab;
  --ok: #81c784;
  --ok-soft: #1e3a20;
  --ok-text: #a5d6a7;
  --shadow: 0 1px 2px rgba(0, 0, 0, .45);
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
  font: 16px/1.5 var(--f-body);
}
main {
  max-width: 44rem;
  margin: 0 auto;
}
.head {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.head::before {
  content: "";
  flex: none;
  width: 0.9rem;
  height: 0.9rem;
  border-radius: var(--r-tag);
  background: var(--coral);
}
h1 {
  margin: 0;
  font-size: 0.8rem;
  font-weight: 500;
  letter-spacing: 0.06em;
  color: var(--muted);
}
.updated,
.elapsed,
.usage,
.attempt,
.total {
  font-family: var(--f-mono);
}
.updated {
  margin-left: auto;
  font-size: 0.75rem;
  color: var(--muted);
}
#name {
  margin: 0.75rem 0 0.5rem;
  font-size: 1.25rem;
  font-weight: 700;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
.chips:empty {
  display: none;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.2rem 0.75rem;
  border-radius: var(--r-chip);
  background: var(--col);
  color: var(--fg);
  font-size: 0.9rem;
  font-weight: 700;
}
.chip svg {
  flex: none;
  width: 1rem;
  height: 1rem;
}
.chip-review {
  background: var(--coral-soft);
  color: var(--coral-text);
}
.chip-running {
  background: var(--teal-soft);
  color: var(--teal-text);
}
.total {
  font-size: 0.85rem;
  color: var(--muted);
}
#final,
#msg {
  margin: 0.5rem 0 0;
  color: var(--muted);
}
#final:empty {
  display: none;
}
.band {
  display: flex;
  gap: 4px;
  height: 8px;
  margin: 1rem 0 0.4rem;
}
.seg {
  flex: 1 1 0;
  border-radius: 2px;
}
.seg-done {
  background: var(--ok);
}
.seg-review {
  background: repeating-linear-gradient(135deg, var(--coral) 0 3px, var(--coral-soft) 3px 6px);
}
.seg-running {
  background: radial-gradient(circle, var(--teal) 1.5px, transparent 2px) 0 0 / 6px 6px, var(--teal-soft);
}
.seg-waiting {
  background: var(--col);
}
.seg-failed {
  background: var(--bad);
}
.seg-revised {
  border: 2px solid var(--coral);
}
.seg-unknown {
  border: 2px dotted var(--muted);
}
.counts {
  margin: 0;
  font-size: 0.85rem;
  color: var(--muted);
}
#stages {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 1rem 0 0;
  padding: 0;
}
.stage {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
  padding: 0.7rem 0.9rem;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--r-card);
  box-shadow: var(--shadow);
}
.s-review {
  background: var(--coral-soft);
  border: 2px solid var(--coral);
}
.s-waiting {
  background: transparent;
  border-style: dashed;
  box-shadow: none;
}
.mark {
  flex: 0 0 auto;
  width: 1.75rem;
  height: 1.75rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  border-radius: var(--r-chip);
  background: var(--col);
  color: var(--muted);
}
.mark svg {
  flex: none;
  width: 1rem;
  height: 1rem;
}
.label {
  flex: 1 1 8rem;
  font-weight: 700;
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
.s-done .mark {
  color: var(--ok-text);
  background: var(--ok-soft);
}
.s-running .mark {
  color: var(--teal-text);
  background: var(--teal-soft);
}
.s-review .mark {
  color: var(--coral-text);
  background: var(--coral-soft);
  border: 2px solid var(--coral);
}
.s-revised .mark {
  color: var(--coral-text);
  background: var(--coral-soft);
}
.s-failed .mark {
  color: var(--bad-text);
  background: var(--bad-soft);
}
.s-running .elapsed {
  color: var(--teal-text);
}
.s-review .elapsed {
  color: var(--coral-text);
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
  border-radius: var(--r-tag);
  color: var(--fg);
  background: var(--panel);
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
  border-radius: var(--r-tag);
  background: var(--panel);
  color: var(--fg);
  font: inherit;
  cursor: pointer;
}
.rv-approve {
  background: var(--coral);
  color: var(--on-coral);
  border-color: var(--coral);
}
.rv-quit {
  border-color: var(--bad);
}
.rv-go {
  border-width: 2px;
  border-color: var(--coral);
}
.rv-btn:disabled {
  border-style: dashed;
  background: var(--col);
  color: var(--muted);
  cursor: not-allowed;
}
.rv-btn:focus-visible,
.rv-input:focus-visible {
  outline: 2px solid var(--teal);
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
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  .s-running .mark {
    animation: pulse 1.6s ease-in-out infinite;
  }
  .s-running .mark svg {
    animation: spin 2s linear infinite;
  }
  .rv-btn,
  .rv-input {
    transition: border-color 0.15s ease, background-color 0.15s ease;
  }
}
"""

_BODY = r"""
<main>
<header class="head"><h1>pipe-in · 進み具合</h1><span class="updated"></span></header>
<p id="name"></p>
<div class="chips"></div>
<p id="final"></p>
<div class="band" aria-hidden="true"></div>
<p class="counts"></p>
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
  waiting: { word: "まだ" },
  running: { word: "作業中" },
  review: { word: "確認待ち" },
  done: { word: "完了" },
  failed: { word: "失敗" },
  revised: { word: "差し戻し" },
  unknown: { word: "不明" }
};
var SVG_NS = "http://www.w3.org/2000/svg";
var ICONS = {
  done: "M2 12a10 10 0 1 0 20 0a10 10 0 1 0 -20 0M16 9l-5.5 5.5L8 12",
  running: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8M21 3v5h-5M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16M8 16H3v5",
  review: "M18 11V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2M14 10V4a2 2 0 0 0-2-2a2 2 0 0 0-2 2v2M10 10.5V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2v8M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15",
  waiting: "M5 12h14",
  failed: "M2 12a10 10 0 1 0 20 0a10 10 0 1 0 -20 0M15 9l-6 6M9 9l6 6",
  revised: "M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11",
  unknown: "M10.1 2.182a10 10 0 0 1 3.8 0M13.9 21.818a10 10 0 0 1-3.8 0M17.609 3.721a10 10 0 0 1 2.69 2.7M2.182 13.9a10 10 0 0 1 0-3.8M20.279 17.609a10 10 0 0 1-2.7 2.69M21.818 10.1a10 10 0 0 1 0 3.8M3.721 6.391a10 10 0 0 1 2.7-2.69M6.391 20.279a10 10 0 0 1-2.69-2.7"
};
var COUNT_ORDER = ["done", "review", "running", "failed", "revised", "waiting", "unknown"];
var CHIP_SEP = "：";
var TOTAL_LABEL = "合計";
var TURN_LABEL = " ターン";
var UPDATED_SUFFIX = " 更新";
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
    generatedAt: typeof value.generated_at === "string" ? value.generated_at : null,
    stages: stages,
    review: final === null ? checkReview(value.review, stages) : null
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

function makeIcon(status) {
  var key = has(ICONS, status) ? status : "unknown";
  var svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  var path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", ICONS[key]);
  svg.appendChild(path);
  return svg;
}

function pickHead(stages) {
  var running = null;
  for (var i = 0; i < stages.length; i++) {
    if (stages[i].status === "review") return { status: "review", label: stages[i].label };
    if (running === null && stages[i].status === "running") running = { status: "running", label: stages[i].label };
  }
  return running;
}

function totalText(stages) {
  var cost = 0;
  var turns = 0;
  var sec = 0;
  for (var i = 0; i < stages.length; i++) {
    if (isPositive(stages[i].cost)) cost += stages[i].cost;
    if (isPositive(stages[i].turns)) turns += Math.floor(stages[i].turns);
    if (isPositive(stages[i].duration)) sec += stages[i].duration;
  }
  var parts = [];
  if (cost > 0) parts.push("$" + Number(cost.toFixed(4)));
  if (turns > 0) parts.push(turns + TURN_LABEL);
  if (sec > 0) parts.push(fmtElapsed(sec));
  return parts.length === 0 ? "" : TOTAL_LABEL + " " + parts.join(" · ");
}

function updatedText(generatedAt) {
  if (typeof generatedAt !== "string" || parseTime(generatedAt) === null) return "";
  var m = TIME_RE.exec(generatedAt);
  return m === null ? "" : m[4] + ":" + m[5] + UPDATED_SUFFIX;
}

function countText(stages) {
  var n = {};
  for (var i = 0; i < stages.length; i++) {
    var st = stages[i].status;
    if (!has(STATUS, st)) continue;
    n[st] = has(n, st) ? n[st] + 1 : 1;
  }
  var parts = [];
  for (var k = 0; k < COUNT_ORDER.length; k++) {
    if (has(n, COUNT_ORDER[k])) parts.push(STATUS[COUNT_ORDER[k]].word + " " + n[COUNT_ORDER[k]]);
  }
  return parts.join(" ・ ");
}

function buildBand(stages) {
  var segs = [];
  for (var i = 0; i < stages.length; i++) {
    segs.push(el("span", "seg seg-" + stages[i].status));
  }
  return segs;
}

function buildChips(stages) {
  var out = [];
  var head = pickHead(stages);
  if (head !== null) {
    var chip = el("span", "chip chip-" + head.status);
    chip.appendChild(makeIcon(head.status));
    chip.appendChild(el("span", "chip-text", STATUS[head.status].word + CHIP_SEP + head.label));
    out.push(chip);
  }
  var total = totalText(stages);
  if (total !== "") out.push(el("span", "total", total));
  return out;
}

function pick(selector) {
  return document.querySelector(selector);
}

function buildRow(stage, found) {
  var info = STATUS[stage.status];
  var li = el("li", "stage s-" + stage.status);
  var mark = el("span", "mark");
  mark.setAttribute("aria-hidden", "true");
  mark.appendChild(makeIcon(stage.status));
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

function clearHead() {
  pick(".updated").textContent = "";
  pick(".counts").textContent = "";
  pick(".chips").replaceChildren();
  pick(".band").replaceChildren();
}

function show(message) {
  counters = [];
  byId("name").textContent = "";
  byId("final").textContent = "";
  byId("stages").replaceChildren();
  clearHead();
  byId("msg").textContent = message;
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
      show(EMPTY_MSG);
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
    pick(".updated").textContent = updatedText(snap.generatedAt);
    pick(".counts").textContent = countText(snap.stages);
    pick(".chips").replaceChildren.apply(pick(".chips"), buildChips(snap.stages));
    pick(".band").replaceChildren.apply(pick(".band"), buildBand(snap.stages));
    byId("name").textContent = snap.name;
    byId("final").textContent = snap.final === null ? "" : "結果: " + FINALS[snap.final];
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
        f"{_FONT_LINKS}"
        f"<style>{_CSS}</style>\n"
        "</head>\n"
        f"<body>{_BODY}"
        f"<script>{_JS}</script>\n"
        "</body>\n"
        "</html>\n"
    )
