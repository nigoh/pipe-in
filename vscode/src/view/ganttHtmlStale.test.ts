// 時系列の動いている帯の「⚠ 更新なし」の印（D0021・AC-34 ①②③。目安なしの見え方は AC-11 の時系列の分）。
// モデル（GanttModel）を手で作り、動いている帯（run.quietSec）と目安の秒を renderGantt に渡して、描かれ方を文字列で確かめる（純粋）。
// モデルの quietSec を作る側は domain/pipelineViewStale.test.ts。「出ない側」の確かめには、同じ入力に出る条件だけを足した対照を付ける。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { GanttModel, GanttRow } from '../domain/gantt.ts';
import { parseCss } from '../test/cssBlocks.ts';
import { STALE_AFTER_SEC } from '../test/staleFixtures.ts';
import { GANTT_STYLE, renderGantt } from './ganttHtml.ts';

const AFTER = STALE_AFTER_SEC;

const gRow = (p: Partial<GanttRow> & { seq: number; label: string }): GanttRow => ({ agent: null, run: null, wait: null, ...p });
const gModel = (rows: GanttRow[], p: Partial<GanttModel> = {}): GanttModel => ({
  rows,
  omittedRows: 0,
  totalSec: 100,
  ticks: [20, 40, 60, 80, 100],
  live: false,
  hasTimes: true,
  ...p,
});
const runBar = (startSec: number, endSec: number, p: { failed?: boolean; live?: boolean } = {}) => ({ startSec, endSec, failed: p.failed ?? false, live: p.live ?? false });
/** 動いている帯。quietSec は省ける（省くと項目ごと無い） */
const liveBar = (startSec: number, endSec: number, quietSec?: number) => ({ ...runBar(startSec, endSec, { live: true }), ...(quietSec === undefined ? {} : { quietSec }) });

const plain = (text: string): string => text.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
const visible = (text: string): string => plain(text.replace(/<title>[\s\S]*?<\/title>/g, ''));

// ---- 要素を取り出す小さな補助（ganttHtml.test.ts と同じ形） ----

interface El {
  name: string;
  attrs: string;
  index: number;
  inner: string;
}
const attrOf = (attrs: string, name: string): string | undefined => new RegExp(`(?:^|\\s)${name}="([^"]*)"`).exec(attrs)?.[1];
function elements(out: string, want: (name: string, attrs: string) => boolean): El[] {
  const found: El[] = [];
  for (const m of out.matchAll(/<([a-zA-Z][\w-]*)\b([^>]*?)(\/?)>/g)) {
    const name = m[1]!;
    const attrs = m[2]!;
    if (!want(name, attrs)) continue;
    let inner = '';
    if (m[3] !== '/') {
      const from = m.index! + m[0].length;
      const re = new RegExp(`<(/?)${name}\\b[^>]*?(/?)>`, 'g');
      re.lastIndex = from;
      let depth = 1;
      let end = out.length;
      for (let n = re.exec(out); n !== null; n = re.exec(out)) {
        if (n[2] === '/') continue;
        depth += n[1] === '/' ? -1 : 1;
        if (depth === 0) {
          end = n.index;
          break;
        }
      }
      inner = out.slice(from, end);
    }
    found.push({ name, attrs, index: m.index!, inner });
  }
  return found;
}
const classesOf = (attrs: string): string[] => (attrOf(attrs, 'class') ?? '').split(/\s+/).filter(Boolean);
const hasClass = (attrs: string, token: string): boolean => classesOf(attrs).includes(token);
const byClass = (out: string, token: string): El[] => elements(out, (_n, a) => hasClass(a, token));

// ---- モデル ----

/** 要件定義（終わった）と設計（動いている。10〜100 秒。全体 100 秒の 90%）。quietSec と目安を渡せる */
const MODEL = (quietSec?: number): GanttModel =>
  gModel([gRow({ seq: 1, label: '要件定義', run: runBar(0, 10) }), gRow({ seq: 2, label: '設計', run: liveBar(10, 100, quietSec) })], { live: true });
const STALE = (): string => renderGantt(MODEL(612), AFTER);
/** 動いている行（2 行目）の g-row */
const liveRow = (out: string): El => byClass(out, 'g-row')[1]!;

// ---- AC-34 ①：動いている帯の行 ----

test('D0021-AC-34: 動いている帯の行（g-row）に data-quiet・data-stale-after が付く。終わった帯の行には付かない', () => {
  const out = STALE();
  const rows = byClass(out, 'g-row');
  assert.equal(rows.length, 2);
  assert.equal(attrOf(rows[1]!.attrs, 'data-quiet'), '612');
  assert.equal(attrOf(rows[1]!.attrs, 'data-stale-after'), '600');
  assert.equal(attrOf(rows[0]!.attrs, 'data-quiet'), undefined);
  assert.equal(attrOf(rows[0]!.attrs, 'data-stale-after'), undefined);
});

test('D0021-AC-34: 基準の秒は整数部（83.9 → data-quiet="83"）', () => {
  const rows = byClass(renderGantt(gModel([gRow({ seq: 1, label: '設計', run: liveBar(10, 100, 83.9) })], { live: true }), AFTER), 'g-row');
  assert.equal(attrOf(rows[0]!.attrs, 'data-quiet'), '83');
});

test('D0021-AC-34: 印つきの文字（g-stalled）は「● 動いている」のあとに「⚠ 更新なし」が添い、普段の文字（g-calm）も残る', () => {
  const row = liveRow(STALE());
  const stalled = byClass(row.inner, 'g-stalled');
  const calm = byClass(row.inner, 'g-calm');
  assert.equal(stalled.length, 1, '印つきの文字が 1 つ');
  assert.equal(calm.length, 1, '普段の文字が 1 つ');
  assert.match(visible(stalled[0]!.inner), /^1:30 ● 動いている ⚠ 更新なし$/);
  assert.match(visible(calm[0]!.inner), /^1:30 ● 動いている$/);
  assert.ok(hasClass(stalled[0]!.attrs, 'g-text') && hasClass(calm[0]!.attrs, 'g-text'), 'どちらも帯の文字（g-text）');
});

test('D0021-AC-34: 普段の文字（g-calm）は、印のない帯の文字と同じ文字・同じ位置（目安の手前の見え方は D0019-AC-69 のまま）', () => {
  const base = byClass(byClass(renderGantt(MODEL()), 'g-row')[1]!.inner, 'g-text');
  assert.equal(base.length, 1, '印のない帯の文字は 1 つ');
  const calm = byClass(liveRow(STALE()).inner, 'g-calm');
  assert.equal(calm.length, 1, '前提：印のある行に普段の文字がある');
  assert.deepEqual(
    classesOf(calm[0]!.attrs).filter((c) => c !== 'g-calm'),
    classesOf(base[0]!.attrs),
    '位置のクラスと帯の中・外の指定が同じ',
  );
  assert.equal(attrOf(calm[0]!.attrs, 'data-side'), attrOf(base[0]!.attrs, 'data-side'));
  assert.equal(visible(calm[0]!.inner), visible(base[0]!.inner));
});

test('D0021-AC-34: 帯の形（rect の x と width）や輪・色のクラスは、印が付いても変わらない（帯は今までどおり「今」まで伸び、不合格の赤にしない）', () => {
  const marked = STALE();
  assert.match(marked, /data-quiet=/, '前提：印がある');
  /** 行ごとの帯の SVG（g-bars）の中身。rect の位置・幅・クラスがそのまま入っている */
  const barsOf = (out: string): string[] => byClass(out, 'g-bars').map((e) => e.inner);
  assert.equal(barsOf(marked).length, 2, '前提：行ごとに帯の SVG がある');
  assert.deepEqual(barsOf(marked), barsOf(renderGantt(MODEL())), '印つきでも、目安なしと帯の SVG が 1 文字も違わない');
  const run = byClass(barsOf(marked)[1]!, 'g-run')[0];
  assert.ok(run, '動いている帯の rect がある');
  assert.equal(attrOf(run.attrs, 'x'), '10', '帯の左端は始まりのまま');
  assert.equal(attrOf(run.attrs, 'width'), '90', '帯の幅は「今」（全体の右端）まで伸びたまま');
  assert.equal(byClass(marked, 'g-fail').length, 0);
  assert.equal(byClass(marked, 'g-ring').length, 1);
});

test('D0021-AC-34: 印つきの文字は長いので、帯が狭いと帯の中に入れず帯の外（data-side）へ、帯が広いと帯の中（g-in）に入れる', () => {
  const narrow = renderGantt(gModel([gRow({ seq: 1, label: '設計', run: liveBar(10, 40, 612) })], { live: true }), AFTER);
  const narrowCalm = byClass(narrow, 'g-calm')[0];
  const narrowStalled = byClass(narrow, 'g-stalled')[0];
  assert.ok(narrowCalm && narrowStalled, '前提：2 つの文字がある');
  assert.ok(hasClass(narrowCalm.attrs, 'g-in'), '普段の文字は帯の中（幅 30% は 28% 以上）');
  assert.ok(!hasClass(narrowStalled.attrs, 'g-in'), '狭い帯では、長い印つきの文字は帯の中に入れない');
  assert.ok(attrOf(narrowStalled.attrs, 'data-side') !== undefined, '帯の外（左か右）に置く');
  const wide = renderGantt(gModel([gRow({ seq: 1, label: '設計', run: liveBar(5, 95, 612) })], { live: true }), AFTER);
  assert.ok(hasClass(byClass(wide, 'g-stalled')[0]!.attrs, 'g-in'), '広い帯（幅 90%）では帯の中に入れる');
});

// ---- AC-34 ②：CSS ----

const flatRules = (css: string): { selector: string; body: string; media: string | null }[] =>
  parseCss(css)
    .filter((r) => !r.keyframes)
    .flatMap((r) => r.selector.split(',').map((sel) => ({ selector: sel.trim().replace(/\s+/g, ' '), body: r.body, media: r.media })));
const hasToken = (selector: string, token: string): boolean => new RegExp(`\\.${token}(?![\\w-])`).test(selector);
const lastCompound = (selector: string): string => selector.trim().split(/\s+/).pop() ?? '';
const decl = (body: string, prop: string): string | null => new RegExp(`(?<![-\\w])${prop}\\s*:\\s*([^;]+)`).exec(body)?.[1]?.trim() ?? null;
const classCount = (selector: string): number => (selector.match(/\.[\w-]+|\[[^\]]+\]|:[\w-]+/g) ?? []).length;

test('D0021-AC-34: CSS：.g-row.is-stale の輪（.g-ring）が点線になる（stroke-dasharray。@media の外）', () => {
  const rule = flatRules(GANTT_STYLE).find(
    (r) => r.media === null && hasToken(lastCompound(r.selector), 'g-ring') && hasToken(r.selector, 'g-row') && hasToken(r.selector, 'is-stale') && ![null, 'none'].includes(decl(r.body, 'stroke-dasharray')),
  );
  assert.ok(rule, '.g-row.is-stale .g-ring { stroke-dasharray: … } がある');
});

test('D0021-AC-34: CSS：印つきの文字（.g-stalled）は is-stale が付くまで見えず、付くと見える。普段の文字（.g-calm）は付くと隠れる', () => {
  const rules = flatRules(GANTT_STYLE).filter((r) => r.media === null);
  const stalled = rules.filter((r) => hasToken(lastCompound(r.selector), 'g-stalled'));
  const hide = stalled.find((r) => !hasToken(r.selector, 'is-stale') && decl(r.body, 'display') === 'none');
  const show = stalled.find((r) => hasToken(r.selector, 'is-stale') && hasToken(r.selector, 'g-row') && ![null, 'none'].includes(decl(r.body, 'display')));
  assert.ok(hide, '.g-stalled は display: none の規則がある');
  assert.ok(show, '.g-row.is-stale .g-stalled は見える規則がある');
  assert.ok(classCount(show.selector) > classCount(hide.selector), '見える規則の方が強い');
  const calm = rules.find((r) => hasToken(lastCompound(r.selector), 'g-calm') && hasToken(r.selector, 'is-stale') && decl(r.body, 'display') === 'none');
  assert.ok(calm, '.g-row.is-stale .g-calm は display: none');
});

test('D0021-AC-34: CSS：is-stale の規則は帯を不合格の赤にしない（赤の色・帯の塗りを変えない）', () => {
  const staleRules = flatRules(GANTT_STYLE).filter((r) => hasToken(r.selector, 'is-stale'));
  assert.ok(staleRules.length > 0, '前提：is-stale の規則がある');
  for (const r of staleRules) {
    assert.doesNotMatch(r.body, /charts-red|errorForeground/, r.selector);
    assert.ok(!hasToken(lastCompound(r.selector), 'g-run') && !hasToken(lastCompound(r.selector), 'g-fail'), `${r.selector} は帯の塗りを変えない`);
  }
});

// ---- AC-34 ③：出ない側（対照つき） ----

const NO_MARK: readonly (readonly [string, () => GanttModel])[] = [
  ['帯の無い行（時刻の記録なし）', () => gModel([gRow({ seq: 1, label: '設計', run: null })], { live: true })],
  ['終わった帯（live でない帯に quietSec が入っていても）', () => gModel([gRow({ seq: 1, label: '設計', run: { ...runBar(10, 60), quietSec: 612 } })])],
  ['動いている帯だが quietSec が無い（項目なし）', () => gModel([gRow({ seq: 1, label: '設計', run: liveBar(10, 100) })], { live: true })],
];

for (const [label, model] of NO_MARK) {
  test(`D0021-AC-34: ${label}には、data-quiet も印つきの文字も出ず、目安なしの HTML と同じ（対照：動いていて quietSec のある行には出る）`, () => {
    const contrast = renderGantt(gModel([gRow({ seq: 1, label: '設計', run: liveBar(10, 100, 612) })], { live: true }), AFTER);
    assert.match(contrast, /data-quiet=/, '対照：出る');
    assert.equal(byClass(contrast, 'g-stalled').length, 1, '対照：出る');
    const out = renderGantt(model(), AFTER);
    assert.doesNotMatch(out, /data-quiet|data-stale-after/);
    assert.equal(byClass(out, 'g-stalled').length + byClass(out, 'g-calm').length, 0);
    assert.equal(out, renderGantt(model()), '目安を渡さないときと同じ HTML');
  });
}

test('D0021-AC-11: 目安が「印なし」（null・渡さない）のときは、quietSec があっても、属性も印つきの文字も出ず、今までの HTML と同じ', () => {
  assert.match(STALE(), /data-quiet=/, '対照：目安があれば出る');
  const without = renderGantt(MODEL());
  for (const out of [renderGantt(MODEL(612), null), renderGantt(MODEL(612))]) {
    assert.doesNotMatch(out, /data-quiet|data-stale-after/);
    assert.equal(byClass(out, 'g-stalled').length + byClass(out, 'g-calm').length, 0);
    assert.equal(out, without);
  }
});
