// 実行の一覧の行の「⚠ 更新なし」の印（D0021・AC-27・28・29。目安なしの見え方は AC-11 の一覧の分）。純粋な文字列の検査。
// 行（RunRow）に quietSec を入れて renderRunList に目安の秒を渡し、印の出る行・出ない行を確かめる。記録の写しから quietSec を作る側は domain/runListStale.test.ts。
// 「出ない側」の確かめには、同じ行に出る条件だけを足した対照を付ける（空振りを防ぐ）。印が出ない行・目安なしの HTML は今までと同じ（守る）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { RunListView, RunRow } from '../domain/runList.ts';
import { motionOutsideNoPreference, parseCss } from '../test/cssBlocks.ts';
import { SID, listView, row, sampleRows } from '../test/runListFixtures.ts';
import { STALE_AFTER_SEC, staleRow } from '../test/staleFixtures.ts';
import { RUN_LIST_STYLE, renderRunList } from './runListHtml.ts';

const AFTER = STALE_AFTER_SEC;
const plain = (text: string): string => text.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();

/** 一覧の行（<li …>…</li>）を並びの順に取り出す */
const rowsOf = (out: string): string[] => [...out.matchAll(/<li\b[^>]*>[\s\S]*?<\/li>/g)].map((m) => m[0]);
function rowOf(out: string, key: string): string {
  const found = rowsOf(out).find((r) => r.includes(`data-run="${key}"`));
  assert.ok(found, `${key} の行がある`);
  return found;
}
const buttonTag = (r: string): string => /<button\b[^>]*>/.exec(r)?.[0] ?? '';

// ---- 入れ子の要素を取り出す・取り除く（<span> の入れ子を数える） ----

interface Found {
  start: number;
  end: number;
  open: string;
  inner: string;
}
function findEl(text: string, tag: string, token: string, from = 0): Found | null {
  const open = new RegExp(`<${tag}\\b[^>]*class="[^"]*\\b${token}\\b[^"]*"[^>]*>`, 'g');
  open.lastIndex = from;
  const m = open.exec(text);
  if (m === null) return null;
  const innerStart = m.index + m[0].length;
  const re = new RegExp(`<${tag}\\b|</${tag}>`, 'g');
  re.lastIndex = innerStart;
  let depth = 1;
  for (let t = re.exec(text); t !== null; t = re.exec(text)) {
    depth += t[0].startsWith('</') ? -1 : 1;
    if (depth === 0) return { start: m.index, end: t.index + t[0].length, open: m[0], inner: text.slice(innerStart, t.index) };
  }
  return null;
}
function allEl(text: string, tag: string, token: string): Found[] {
  const found: Found[] = [];
  for (let f = findEl(text, tag, token); f !== null; f = findEl(text, tag, token, f.end)) found.push(f);
  return found;
}
function removeAll(text: string, tag: string, token: string): string {
  let out = text;
  for (let f = findEl(out, tag, token); f !== null; f = findEl(out, tag, token)) out = out.slice(0, f.start) + out.slice(f.end);
  return out;
}
function unwrapAll(text: string, tag: string, token: string): string {
  let out = text;
  for (let f = findEl(out, tag, token); f !== null; f = findEl(out, tag, token)) out = out.slice(0, f.start) + f.inner + out.slice(f.end);
  return out;
}
/** 印の属性・run-stale・run-foot の包みを取り除く（残るのは、印のない一覧と同じはずのもの） */
function stripMarks(out: string): string {
  const noAttrs = out.replace(/ data-quiet="[^"]*"/g, '').replace(/ data-stale-after="[^"]*"/g, '');
  return unwrapAll(removeAll(noAttrs, 'span', 'run-stale'), 'span', 'run-foot');
}

// ---- 一覧の例 ----

/** 動いている行（印の対象になる行）。sampleRows では diagrams と fix-login */
const RUNNING_KEYS = ['here|diagrams', 'wt.fix-login|'];
/** 見本の一覧の全部の行に quietSec（612）を入れた一覧（動いていない行に入っていても出ないことを見る） */
const withQuiet = (): RunRow[] => sampleRows().map((r) => ({ ...r, quietSec: 612 }) as RunRow);
const list = (rows: RunRow[], p: Partial<RunListView> = {}): RunListView => listView(rows, p);

// ---- AC-27：動いている行の印 ----

test('D0021-AC-27: quietSec のある動いている行に、data-quiet・data-stale-after と、「⚠ 更新なし」と時間の印（span.run-stale）が出る', () => {
  const out = renderRunList(list([staleRow(612, { key: 'here|a', sessionId: SID.here }), row({ key: 'here|b' })]), AFTER);
  const r = rowOf(out, 'here|a');
  assert.match(buttonTag(r), /\sdata-quiet="612"/);
  assert.match(buttonTag(r), /\sdata-stale-after="600"/);
  const marks = allEl(r, 'span', 'run-stale');
  assert.equal(marks.length, 1, '印の要素が 1 つ');
  assert.equal(plain(marks[0]!.inner), '⚠ 更新なし 10:12');
  assert.match(marks[0]!.inner, /<span class="elapsed" data-elapsed="612">10:12<\/span>/, '時間は data-elapsed（基準の秒）つきの要素');
  assert.doesNotMatch(rowOf(out, 'here|b'), /data-quiet|run-stale/, '印の無い行には出ない');
});

test('D0021-AC-27: 基準の秒は整数部（83.9 → data-quiet="83"・data-elapsed="83"・1:23）', () => {
  const r = rowOf(renderRunList(list([staleRow(83.9, { key: 'here|a' })]), AFTER), 'here|a');
  assert.match(buttonTag(r), /\sdata-quiet="83"/);
  assert.equal(plain(allEl(r, 'span', 'run-stale')[0]?.inner ?? ''), '⚠ 更新なし 1:23');
});

test('D0021-AC-27: 印は 3 行目（run-foot の中、run-id の右）にあり、1 行目（run-top）には無い。run-id は ID だけのまま', () => {
  const r = rowOf(renderRunList(list([staleRow(612, { key: 'here|a', sessionId: SID.here })]), AFTER), 'here|a');
  const foot = allEl(r, 'span', 'run-foot');
  assert.equal(foot.length, 1, '前提：印の行は run-foot を持つ');
  const idAt = foot[0]!.inner.indexOf('class="run-id"');
  const staleAt = foot[0]!.inner.indexOf('class="run-stale"');
  assert.ok(idAt >= 0 && staleAt > idAt, 'run-foot の中で、印は run-id の右');
  assert.equal(plain(allEl(r, 'span', 'run-id')[0]!.inner), 'aaaa1111', 'run-id は ID の先頭 8 文字だけ');
  assert.doesNotMatch(allEl(r, 'span', 'run-top')[0]!.inner, /run-stale|更新なし/, '1 行目（セッション名の行）には入れない');
  assert.ok(
    r.indexOf('class="run-top"') < r.indexOf('class="run-sub"') && r.indexOf('class="run-sub"') < r.indexOf('class="run-foot"'),
    '1 行目 → 2 行目 → 3 行目の順',
  );
});

test('D0021-AC-27: HTML は最初は is-stale を持たない（付けるのはパネルのスクリプト。付くまで見えない）', () => {
  const out = renderRunList(list([staleRow(612, { key: 'here|a' })]), AFTER);
  assert.match(out, /run-stale/, '前提：印の要素がある');
  assert.doesNotMatch(out, /is-stale/);
});

test('D0021-AC-27: CSS：印（.run-stale）は is-stale が付くまで見えず（display: none）、.run-row.is-stale の下では見える', () => {
  const rules = flatRules(RUN_LIST_STYLE).filter((r) => r.media === null && hasToken(lastCompound(r.selector), 'run-stale'));
  const hide = rules.find((r) => !hasToken(r.selector, 'is-stale') && decl(r.body, 'display') === 'none');
  const show = rules.find((r) => hasToken(r.selector, 'is-stale') && hasToken(r.selector, 'run-row') && ![null, 'none'].includes(decl(r.body, 'display')));
  assert.ok(hide, '.run-stale は display: none の規則がある');
  assert.ok(show, '.run-row.is-stale .run-stale は見える規則がある');
  assert.ok(classCount(show.selector) > classCount(hide.selector), '見える規則の方が強い');
});

test('D0021-AC-27: quietSec が null・項目なしの動いている行には、属性も印も出ない（対照：数なら出る）', () => {
  assert.match(renderRunList(list([staleRow(612, { key: 'here|a' })]), AFTER), /data-quiet="612"/, '対照：数なら出る');
  for (const quiet of [null, undefined]) {
    const out = renderRunList(list([staleRow(quiet, { key: 'here|a' })]), AFTER);
    assert.doesNotMatch(out, /data-quiet|data-stale-after|run-stale|run-foot/, String(quiet));
  }
});

test('D0021-AC-27: 目安を渡さない・null のときは、quietSec が入っていても今までと同じ HTML（印も run-foot も無い。対照：目安を渡すと印が出る）', () => {
  assert.match(renderRunList(list(withQuiet()), AFTER), /run-stale/, '対照：目安を渡すと印が出る');
  const without = renderRunList(list(sampleRows()));
  for (const out of [renderRunList(list(withQuiet())), renderRunList(list(withQuiet()), null)]) {
    assert.doesNotMatch(out, /data-quiet|data-stale-after|run-stale|run-foot/);
    assert.equal(out, without);
  }
});

test('D0021-AC-27: 目安ありで印が出る行は、印の属性と run-stale と run-foot の包みを取り除くと、目安なしの一覧と同じ（状態の言葉・見出し・タブの件数・並びは変わらない）', () => {
  const out = renderRunList(list(withQuiet()), AFTER);
  assert.equal(allEl(out, 'span', 'run-stale').length, RUNNING_KEYS.length, '前提：動いている行（2 つ）にだけ印がある');
  assert.equal(stripMarks(out), renderRunList(list(sampleRows())));
});

test('D0021-AC-27: 印が出ない行（確認待ち・待ち・終わった・前の実行）は、目安ありでも 1 文字も変わらない', () => {
  const out = renderRunList(list(withQuiet()), AFTER);
  for (const key of RUNNING_KEYS) assert.match(rowOf(out, key), /run-stale/, `前提：${key} には印がある`);
  const base = renderRunList(list(withQuiet()));
  for (const r of sampleRows().filter((x) => !RUNNING_KEYS.includes(x.key))) {
    assert.equal(rowOf(out, r.key), rowOf(base, r.key), r.key);
  }
});

// ---- AC-28：CSS ----

/** 規則を 1 つずつに分ける（「,」で並べたセレクタも別々に） */
function flatRules(css: string): { selector: string; body: string; media: string | null }[] {
  return parseCss(css)
    .filter((r) => !r.keyframes)
    .flatMap((r) => r.selector.split(',').map((sel) => ({ selector: sel.trim().replace(/\s+/g, ' '), body: r.body, media: r.media })));
}
const hasToken = (selector: string, token: string): boolean => new RegExp(`\\.${token}(?![\\w-])`).test(selector);
const lastCompound = (selector: string): string => selector.trim().split(/\s+/).pop() ?? '';
const decl = (body: string, prop: string): string | null => new RegExp(`(?<![-\\w])${prop}\\s*:\\s*([^;]+)`).exec(body)?.[1]?.trim() ?? null;
const classCount = (selector: string): number => (selector.match(/\.[\w-]+|\[[^\]]+\]|:[\w-]+/g) ?? []).length;
/** 子孫・属性の無い、1 つだけのセレクタ（例 .run-row.is-stale） */
const single = (selector: string): boolean => !/[\s[:]/.test(selector);

test('D0021-AC-28: CSS：.run-row.is-stale は border-style: dashed（点線の枠）で、枠の色は見える色（transparent でない）', () => {
  const rule = flatRules(RUN_LIST_STYLE).find(
    (r) => r.media === null && single(r.selector) && hasToken(r.selector, 'run-row') && hasToken(r.selector, 'is-stale') && decl(r.body, 'border-style') === 'dashed',
  );
  assert.ok(rule, '.run-row.is-stale { border-style: dashed } がある');
  const color = decl(rule.body, 'border-color');
  assert.ok(color !== null && /var\(--vscode-/.test(color) && !/transparent/.test(color), `枠の色 ${String(color)}`);
  assert.ok(classCount(rule.selector) > 1, '基本の .run-row（transparent の枠）より強い');
});

test('D0021-AC-28: CSS：確認待ちの行（.run-row.is-waiting）の枠は今までどおり実線（solid）のまま（守る）', () => {
  const rules = flatRules(RUN_LIST_STYLE).filter((r) => r.media === null && single(r.selector) && hasToken(r.selector, 'run-row') && hasToken(r.selector, 'is-waiting'));
  assert.ok(rules.some((r) => /border\s*:\s*2px\s+solid\b/.test(r.body)), '.run-row.is-waiting は border: 2px solid');
  for (const r of rules) assert.doesNotMatch(r.body, /dashed/, r.selector);
});

test('D0021-AC-28: CSS：is-stale の規則に animation が無い（脈打たせない。前提：.run-row.is-stale の規則がある）', () => {
  const staleRules = flatRules(RUN_LIST_STYLE).filter((x) => hasToken(x.selector, 'is-stale'));
  assert.ok(
    staleRules.some((r) => hasToken(r.selector, 'run-row')),
    '前提：.run-row.is-stale の規則がある（規則が 1 つも無いと、下の検査は何も見ない）',
  );
  for (const r of staleRules) {
    assert.doesNotMatch(r.body, /\banimation(-name)?\s*:/, `${r.selector} に animation がある`);
  }
});

test('D0021-AC-28: CSS：一覧の動き（animation・@keyframes）は、足したあとも no-preference の中だけのまま（守る）', () => {
  assert.deepEqual(motionOutsideNoPreference(RUN_LIST_STYLE), []);
});

test('D0021-AC-28: 確認待ちの行に data-quiet が出ず、is-stale は付かない（対照：動いている行は出る）。確認待ちの目立たせ方は今のまま', () => {
  const waiting = staleRow(612, { key: 'here|w', state: 'waiting', waitingSec: 42 });
  const running = staleRow(612, { key: 'here|r' });
  const out = renderRunList(list([waiting, running]), AFTER);
  assert.match(rowOf(out, 'here|r'), /data-quiet="612"/, '対照：動いている行は出る');
  const w = rowOf(out, 'here|w');
  assert.doesNotMatch(w, /data-quiet|data-stale-after|run-stale|run-foot|is-stale/);
  assert.match(w, /\bis-waiting\b/);
  assert.match(w, /待ち <span class="elapsed" data-elapsed="42">0:42<\/span>/);
});

// ---- AC-29：印が出ない行の表 ----

const NOT_RUNNING: readonly (readonly [string, Partial<RunRow>])[] = [
  ['確認待ち', { state: 'waiting', waitingSec: 7 }],
  ['待ち（idle）', { state: 'idle' }],
  ['終わった（合格）', { state: 'done', result: '合格' }],
  ['終わった（不合格）', { state: 'done', result: '不合格' }],
  ['前の実行（archive/）', { state: 'done', result: '合格', previous: true }],
];

/** 同じ行を「動いている行」の形にする上書き。state だけでなく、動いている行は持たない項目（前の実行・結果・待ち時間）も外す（実際に作られる形） */
const AS_RUNNING: Partial<RunRow> = { state: 'running', previous: false, result: null, waitingSec: null };

for (const [label, over] of NOT_RUNNING) {
  test(`D0021-AC-29: ${label}の行には、quietSec が入っていても data-quiet も印の要素も出ない（対照：同じ行を動いている行の形にすると出る）`, () => {
    const mk = (p: Partial<RunRow>): RunRow => staleRow(612, { key: 'here|a', sessionId: SID.here, ...over, ...p });
    const on = renderRunList(list([mk(AS_RUNNING)]), AFTER);
    assert.match(rowOf(on, 'here|a'), /data-quiet="612"/, '対照：running なら出る');
    assert.match(rowOf(on, 'here|a'), /run-stale/, '対照：running なら出る');
    const out = renderRunList(list([mk({})]), AFTER);
    assert.doesNotMatch(out, /data-quiet|data-stale-after|run-stale|run-foot/);
  });
}
