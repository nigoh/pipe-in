// 図の拡大・縮小（D0019-AC-79）。Ctrl（mac では ⌘ も）＋マウスホイールと、図の枠の右上のボタン（−・倍率・＋）で 50%〜200%（10% 刻み）。
// panelScript.ts の PANEL_SCRIPT を node:vm で、偽の DOM（src/test/fakeDom.ts）の上で動かす。倍率はパネルのスクリプトの中だけで持つ：拡張へメッセージを送らない。
// 表示上の幅は、SVG の width 属性か、CSS（nonce つきの style 要素）のクラスの px の幅で決まる。どちらの作りでも通るように、幅を読む補助（shownWidth）で見る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import type { RunListView } from '../domain/runList.ts';
import { bootPanel, FakeNode } from '../test/fakeDom.ts';
import type { PanelHarness } from '../test/fakeDom.ts';
import { extractCss } from '../test/cssBlocks.ts';
import { finishedView } from '../test/liveFixtures.ts';
import { listView, sampleRows } from '../test/runListFixtures.ts';
import { shownWidth } from '../test/shownWidth.ts';

const NONCE = 'TESTNONCE';
const LIST = listView(sampleRows(), { selected: 'here|survey' });
/** フロー図の元の幅（flowSvg.ts の viewBox の幅） */
const BASE = 320;

interface Page {
  h: PanelHarness;
  css: string;
}
function boot(view: PipelineView = finishedView(), list: RunListView = LIST): Page {
  const html = renderPanelHtml(view, NONCE, list);
  return { h: bootPanel(html), css: extractCss(html) };
}
const render = (h: PanelHarness, view: PipelineView, list: RunListView): void => h.send({ type: 'render', html: renderViewBody(view, list) });

const svgOf = (h: PanelHarness): FakeNode => {
  const el = h.doc.querySelector('svg.flow');
  assert.ok(el, '図（svg.flow）がある');
  return el;
};
const paneOf = (h: PanelHarness): FakeNode => {
  const el = h.doc.querySelector('.pane-diagram');
  assert.ok(el, '図の枠（.pane-diagram）がある');
  return el;
};
const btn = (h: PanelHarness, kind: 'in' | 'out' | 'reset'): FakeNode => {
  const el = paneOf(h).querySelector(`button[data-zoom="${kind}"]`);
  assert.ok(el, `図の枠の中に button[data-zoom="${kind}"] がある`);
  return el;
};
const label = (h: PanelHarness): string => h.text(btn(h, 'reset')).trim();
/** 倍率 pct のとき、表示上の幅は元の幅の pct% に比例する */
function assertZoom(page: Page, pct: number, note = ''): void {
  assert.equal(label(page.h), `${pct}%`, `倍率の表示 ${note}`);
  const width = shownWidth(page.css, svgOf(page.h), 'flow');
  assert.ok(width !== null, `図の表示上の幅が読める（width 属性か、.flow の px の幅）${note}`);
  assert.ok(Math.abs(width - (BASE * pct) / 100) < 1, `倍率 ${pct}% の幅は ${(BASE * pct) / 100}px のはず（今は ${width}px）${note}`);
}
const wheel = (node: FakeNode, deltaY: number, mods: { ctrlKey?: boolean; metaKey?: boolean } = { ctrlKey: true }) => node.dispatch('wheel', { deltaY, ...mods });

test('D0019-AC-79: 図の枠の中に、「−」「倍率（初めは 100%）」「＋」のボタンがある。type="button"・aria-label つきで、キーボードで使える（tabindex を -1 にしない）', () => {
  const { h } = boot();
  const out = btn(h, 'out');
  const reset = btn(h, 'reset');
  const inn = btn(h, 'in');
  for (const b of [out, reset, inn]) {
    assert.equal(b.tagName, 'button');
    assert.equal(b.getAttribute('type'), 'button');
    assert.ok((b.getAttribute('aria-label') ?? '').trim().length > 0, 'aria-label がある');
    assert.notEqual(b.getAttribute('tabindex'), '-1');
    assert.equal(b.disabled, false, '初めは押せる');
  }
  assert.match(out.getAttribute('aria-label')!, /縮小|小さく/);
  assert.match(inn.getAttribute('aria-label')!, /拡大|大きく/);
  assert.match(reset.getAttribute('aria-label')!, /100\s*%|元の大きさ/);
  assert.match(h.text(out), /[−－–-]/, '「−」');
  assert.match(h.text(inn), /[＋+]/, '「＋」');
  assert.equal(h.text(reset).trim(), '100%');
  const order = paneOf(h)
    .querySelectorAll('button[data-zoom]')
    .map((b) => b.getAttribute('data-zoom'));
  assert.deepEqual(order, ['out', 'reset', 'in'], '並びは − 倍率 ＋');
});

test('D0019-AC-79: 初めは 100%：図は元の大きさ（viewBox の幅 320 を 320px）で描く', () => {
  const page = boot();
  assertZoom(page, 100);
});

test('D0019-AC-79: Ctrl＋ホイールを上へ回すと 10% ずつ拡大し、下へ回すと縮小する。表示上の幅は倍率に比例する。preventDefault する', () => {
  const page = boot();
  const target = svgOf(page.h);
  const up = wheel(target, -100);
  assert.equal(up.defaultPrevented, true, 'Ctrl つきは preventDefault（ブラウザの拡大を止める）');
  assertZoom(page, 110);
  wheel(target, -100);
  wheel(target, -100);
  assertZoom(page, 130);
  const down = wheel(target, 100);
  assert.equal(down.defaultPrevented, true);
  assertZoom(page, 120);
  for (let i = 0; i < 4; i++) wheel(target, 100);
  assertZoom(page, 80);
});

test('D0019-AC-79: 1 回のホイールで動くのは 10% だけ（回す量 deltaY の大きさに関わらない）', () => {
  const page = boot();
  wheel(svgOf(page.h), -4000);
  assertZoom(page, 110);
  wheel(svgOf(page.h), 1);
  assertZoom(page, 100);
});

test('D0019-AC-79: mac の ⌘（metaKey）＋ホイールでも拡大縮小する', () => {
  const page = boot();
  const event = wheel(svgOf(page.h), -100, { metaKey: true });
  assert.equal(event.defaultPrevented, true);
  assertZoom(page, 110);
  wheel(svgOf(page.h), 100, { metaKey: true });
  assertZoom(page, 100);
});

test('D0019-AC-79: Ctrl（⌘）なしのホイールは今までどおりスクロール：preventDefault せず、倍率も変えない', () => {
  const page = boot();
  for (const deltaY of [-120, 120, 5]) {
    const event = wheel(svgOf(page.h), deltaY, {});
    assert.equal(event.defaultPrevented, false, `deltaY=${deltaY}`);
  }
  const onPane = wheel(paneOf(page.h), -120, { ctrlKey: false, metaKey: false });
  assert.equal(onPane.defaultPrevented, false);
  assertZoom(page, 100);
});

test('D0019-AC-79: 図の枠の外（出力・時系列・一覧）での Ctrl＋ホイールは、図を動かさず、preventDefault もしない', () => {
  const page = boot();
  for (const selector of ['.terminal', '.pane-gantt', '.run-scroll']) {
    const el = page.h.doc.querySelector(selector);
    assert.ok(el, selector);
    const event = wheel(el, -100);
    assert.equal(event.defaultPrevented, false, selector);
  }
  assertZoom(page, 100);
});

test('D0019-AC-79: 倍率は 50%〜200%。上限・下限を超えない。端でも Ctrl＋ホイールは preventDefault する（ブラウザの拡大に渡さない）', () => {
  const page = boot();
  const target = svgOf(page.h);
  for (let i = 0; i < 10; i++) wheel(target, -100);
  assertZoom(page, 200);
  const atMax = wheel(target, -100);
  assert.equal(atMax.defaultPrevented, true, '上限でも止める');
  assertZoom(page, 200, '（上限を超えない）');
  for (let i = 0; i < 15; i++) wheel(target, 100);
  assertZoom(page, 50);
  const atMin = wheel(target, 100);
  assert.equal(atMin.defaultPrevented, true, '下限でも止める');
  assertZoom(page, 50, '（下限を超えない）');
  btn(page.h, 'out').dispatch('click');
  assertZoom(page, 50, '（ボタンでも下限を超えない）');
  for (let i = 0; i < 20; i++) btn(page.h, 'in').dispatch('click');
  assertZoom(page, 200, '（ボタンでも上限を超えない）');
});

test('D0019-AC-79: 「−」「＋」のボタンは 10% ずつ。倍率のボタンは 100% に戻す（どの倍率からでも）', () => {
  const page = boot();
  btn(page.h, 'in').dispatch('click');
  btn(page.h, 'in').dispatch('click');
  assertZoom(page, 120);
  btn(page.h, 'out').dispatch('click');
  assertZoom(page, 110);
  for (let i = 0; i < 6; i++) btn(page.h, 'in').dispatch('click');
  assertZoom(page, 170);
  btn(page.h, 'reset').dispatch('click');
  assertZoom(page, 100);
  for (let i = 0; i < 4; i++) btn(page.h, 'out').dispatch('click');
  assertZoom(page, 60);
  btn(page.h, 'reset').dispatch('click');
  assertZoom(page, 100);
});

test('D0019-AC-79: ボタンとホイールは同じ倍率を持つ（ホイールで 130% にしたあとボタンの − は 120%）', () => {
  const page = boot();
  for (let i = 0; i < 3; i++) wheel(svgOf(page.h), -100);
  btn(page.h, 'out').dispatch('click');
  assertZoom(page, 120);
});

test('D0019-AC-79: 描き直し（render）のあとも倍率が残る：図の幅も倍率の表示も同じ', () => {
  const page = boot();
  for (let i = 0; i < 5; i++) wheel(svgOf(page.h), -100);
  assertZoom(page, 150);
  render(page.h, finishedView(), LIST);
  assertZoom(page, 150, '（描き直しのあと）');
  render(page.h, finishedView(), LIST);
  assertZoom(page, 150, '（2 回目の描き直しのあと）');
  wheel(svgOf(page.h), 100);
  assertZoom(page, 140, '（描き直しのあとも操作できる）');
  btn(page.h, 'reset').dispatch('click');
  render(page.h, finishedView(), LIST);
  assertZoom(page, 100, '（100% に戻したあとの描き直し）');
});

test('D0019-AC-79: 実行を選び替えても（選んだ run が変わる描き直し）倍率は残る', () => {
  const page = boot();
  for (let i = 0; i < 3; i++) wheel(svgOf(page.h), 100);
  assertZoom(page, 70);
  render(page.h, finishedView(), listView(sampleRows(), { selected: 'here|diagrams' }));
  assertZoom(page, 70, '（別の run を選んだあと）');
  render(page.h, finishedView(), listView(sampleRows(), { selected: 'wt.feat-x|' }));
  assertZoom(page, 70, '（さらに別の run）');
});

test('D0019-AC-79: 倍率を替えても、拡張へメッセージを送らない（ready のあと増えない）', () => {
  const page = boot();
  const before = JSON.stringify(page.h.posted);
  for (let i = 0; i < 3; i++) wheel(svgOf(page.h), -100);
  btn(page.h, 'out').dispatch('click');
  btn(page.h, 'in').dispatch('click');
  btn(page.h, 'reset').dispatch('click');
  render(page.h, finishedView(), LIST);
  assert.equal(JSON.stringify(page.h.posted), before);
});

test('D0019-AC-79: ホイールの受け口は passive: false（passive のままだと preventDefault が効かず、ブラウザの拡大が出る）。CSP は変えない（style= もインラインの style も使わない）', async () => {
  const { PANEL_SCRIPT } = await import('./panelScript.ts');
  assert.match(PANEL_SCRIPT, /'wheel'/);
  assert.match(PANEL_SCRIPT, /passive\s*:\s*false/);
  assert.doesNotMatch(PANEL_SCRIPT, /setAttribute\(\s*['"]style['"]|\.cssText|insertAdjacentHTML\s*\(\s*['"][^'"]*style=/);
  const html = renderPanelHtml(finishedView(), NONCE, LIST);
  assert.match(html, /style-src 'nonce-TESTNONCE';/);
  assert.doesNotMatch(html, /unsafe-inline|unsafe-eval/);
  assert.doesNotMatch(html.replace(/<script[\s\S]*?<\/script>/g, ''), /\sstyle\s*=/i, 'style 属性を使わない');
});
