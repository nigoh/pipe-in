// 図（フロー図）と時系列を、元の大きさで描く CSS（D0019-AC-63・AC-77）。
// 図は枠の大きさに合わせて縮めない：viewBox の幅 320 を 320px で描き、収まらない分は枠の中でスクロールする。
// 時系列は HTML の並びで、枠の幅に合わせて伸び縮みする（帯と目盛りは %、文字は元の大きさ）。固定の幅は持たない。
// 幅は SVG の width 属性か、nonce つきの style 要素の CSS（px）のどちらで決めてもよい（test/shownWidth.ts が両方読む）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderPanelHtml } from './panelHtml.ts';
import { renderGantt } from './ganttHtml.ts';
import type { GanttModel } from '../domain/gantt.ts';
import { bootPanel } from '../test/fakeDom.ts';
import { extractCss, parseCss } from '../test/cssBlocks.ts';
import type { CssRule } from '../test/cssBlocks.ts';
import { finishedView } from '../test/liveFixtures.ts';
import { listView, sampleRows } from '../test/runListFixtures.ts';
import { shownWidth } from '../test/shownWidth.ts';

const html = renderPanelHtml(finishedView(), 'n', listView(sampleRows(), { selected: 'here|survey' }));
const css = extractCss(html);
const rules = parseCss(css).filter((r) => !r.keyframes);

/** 最後の部分に .<own> を持つ規則（その要素そのものに当たる規則。子孫の .flow text などは含めない） */
const rulesOf = (own: string): CssRule[] =>
  rules.filter((r) => r.selector.split(',').some((s) => new RegExp(`\\.${own}(?![\\w-])`).test(s.trim().split(/\s+/).pop() ?? '')));
const widthDecl = (r: CssRule): string | null => /(?<![-\w])width\s*:\s*([^;]+)/.exec(r.body)?.[1]?.trim() ?? null;

const SHRINKS = /^(100%|auto|fit-content|min-content|max-content|inherit|unset)$/;

test('D0019-AC-63: フロー図（.flow）の CSS に、枠に合わせて縮める width: 100% が無い。幅は元の大きさ（320px）か倍率を掛けた px で決まる', () => {
  const own = rulesOf('flow');
  assert.ok(own.length > 0, '.flow の規則がある');
  for (const r of own) {
    const w = widthDecl(r);
    assert.ok(w === null || !SHRINKS.test(w), `「${r.selector}」の width が枠に合わせて縮む形（${w}）`);
    assert.doesNotMatch(r.body, /(?<![-\w])max-width\s*:\s*100%/, `${r.selector} の max-width: 100% は縮める`);
  }
});

test('D0019-AC-63: 初めの図の表示上の幅は元の大きさ（viewBox の幅 320 を 320px）で、viewBox は 320 幅のまま', () => {
  const h = bootPanel(html);
  const svg = h.doc.querySelector('svg.flow');
  assert.ok(svg, '図がある');
  assert.match(html, /<svg class="flow" viewBox="0 0 320 \d+"/);
  assert.equal(shownWidth(css, svg, 'flow'), 320, '図は 320px で描く（width: 100% で枠に縮めない）');
});

test('D0019-AC-63: 図は縦に並ぶ枠（.pane-diagram は flex の列）の直下にあるとき、flex-shrink で縮まない（flex: none か flex-shrink: 0）', () => {
  const h = bootPanel(html);
  const svg = h.doc.querySelector('svg.flow')!;
  const parent = svg.parent!;
  const parentIsFlexColumn = parent.classList.contains('pane-diagram');
  if (!parentIsFlexColumn) return; // 包む要素を挟む作りなら、列の中で縮むのは包む要素の規則。ここでは見ない
  const noShrink = rulesOf('flow').some((r) => /(?<![-\w])flex\s*:\s*none\b|flex-shrink\s*:\s*0\b|flex\s*:\s*0\s+0\b/.test(r.body));
  assert.ok(noShrink, '縦の flex の列の中の図は、flex-shrink: 0 にしないと枠の高さに合わせて縮んで小さくなる');
});

test('D0019-AC-63: 図の枠（.pane-diagram）は、収まらない図を枠の中でスクロールする（overflow: auto か scroll。hidden や visible にしない）', () => {
  const own = rulesOf('pane-diagram').filter((r) => r.media === null);
  assert.ok(own.length > 0);
  const overflow = own.map((r) => /(?<![-\w])overflow(-x)?\s*:\s*([\w-]+)/.exec(r.body)?.[2]).filter((v): v is string => v !== undefined);
  assert.ok(overflow.length > 0 && overflow.every((v) => v === 'auto' || v === 'scroll'), `overflow は ${overflow.join(',')}`);
  assert.ok(own.some((r) => /(?<![-\w])overflow\s*:\s*(auto|scroll)/.test(r.body)), '縦も横もスクロール');
});

// ---- 時系列 ----

const GANTT: GanttModel = {
  rows: [{ seq: 1, label: '要件定義', agent: 'pipe-in-analyst', run: { startSec: 10, endSec: 40, failed: false, live: false }, wait: null }],
  omittedRows: 0,
  totalSec: 100,
  ticks: [20, 40, 60, 80, 100],
  live: false,
  hasTimes: true,
};

// 時系列は HTML の並びで描く：枠の幅に合わせて伸び縮みし（帯と目盛りは %）、文字は元の大きさ。固定の幅（740px）は持たない。
const ganttCss = `${css}\n${extractCss(renderGantt(GANTT))}`;
const ganttRules = parseCss(ganttCss).filter((r) => !r.keyframes);
const GANTT_SELECTOR = /\.(gantt|gantt-[\w-]+|g-[\w-]+|key-[\w-]+)(?![\w-])/;

test('D0019-AC-77: 時系列の枠（.gantt）の CSS に固定の px 幅・min-width が無い。枠の幅に合わせて伸び縮みする（width は 100% か auto か無指定）', () => {
  const own = rulesOf('gantt');
  assert.ok(own.length > 0, '.gantt の規則がある');
  for (const r of own) {
    const w = widthDecl(r);
    assert.ok(w === null || /^(100%|auto)$/.test(w), `「${r.selector}」の width が固定（${w}）`);
  }
  for (const r of ganttRules.filter((x) => x.selector.split(',').some((s) => GANTT_SELECTOR.test(s)))) {
    assert.doesNotMatch(r.body, /(?<![-\w])min-width\s*:\s*(?!0\b|auto\b)/, `「${r.selector}」に min-width`);
    for (const m of r.body.matchAll(/(?<![-\w])width\s*:\s*([\d.]+)px/g)) assert.ok(Number(m[1]) < 100, `「${r.selector}」に固定の幅 ${m[0]}`);
  }
  assert.ok(!ganttRules.some((r) => /\.gantt-svg/.test(r.selector)), '幅 740px の .gantt-svg は無い');
});

test('D0019-AC-77: パネルの中に置いた時系列（.gantt）は 740px の SVG を持たず、行・帯・目盛りが枠の幅の中に並ぶ', () => {
  const gantt = renderGantt(GANTT);
  const h = bootPanel(`<div class="root"><section class="pane-gantt">${gantt}</section></div><script nonce="x"></script>`);
  assert.ok(h.doc.querySelector('svg.gantt-svg') === null, '幅 740 の SVG は無い');
  assert.ok(h.doc.querySelector('.gantt'), '時系列の枠がある');
  assert.doesNotMatch(gantt, /viewBox="\s*0\s+0\s+740\b/);
});

test('D0019-AC-77: 時系列の枠（.pane-gantt）は、幅が 300px 未満のときの保険として、はみ出しを隠さない（overflow は auto か scroll）。いつもスクロール棒を出す scroll にはしない', () => {
  const own = rulesOf('pane-gantt').filter((r) => r.media === null);
  assert.ok(own.length > 0);
  assert.ok(own.some((r) => /(?<![-\w])overflow(-x)?\s*:\s*auto/.test(r.body)), '足りないときだけ横にスクロールできる（auto）');
  assert.ok(
    own.every((r) => !/(?<![-\w])overflow(-x)?\s*:\s*(hidden|visible|clip|scroll)/.test(r.body)),
    '横を隠さない・いつも出さない',
  );
});
