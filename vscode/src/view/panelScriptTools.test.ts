// 「エージェント・スキル」のタブのパネルのスクリプトの動き（D0047）：タブの切り替え（メッセージを送らない）と、描き直しをまたぐ保持
// （タブの選び・縦のスクロール位置（パネル）・横のスクロール位置（表の枠）・焦点）、見る実行が替わったときの先頭への戻り。
// panelScript.ts の PANEL_SCRIPT を node:vm で、偽の DOM（src/test/fakeDom.ts）の上で動かす。本物の時間は使わない（sleep しない）。
// 偽の DOM は、hidden の中では大きさが 0・スクロール位置は残らず、focus() も効かない。横のスクロールは範囲に収めないので、値を書いて読み戻すだけにする
// （枠が本当にあふれるかは、画面の確認 AC-56・58）。縦は layout（パネル 900/400）の範囲に収まる。
// 焦点の読み：表の枠は、見えている間は描き直しのあとも同じ枠（data-keep="tools-table"）に焦点が戻る。別のタブを見ていて隠れている間は、
// 枠そのものは焦点を持てない（隠れた要素は本物のブラウザでも焦点を失う）ので、「そのとき焦点があった要素（別のタブのボタンなど）が、描き直しのあとも同じ要素に戻る」。
// タブの切り替え・スクロールの記憶・焦点の復元は、既存の仕組みがそのまま働く。足すのは、見る実行が替わったときに消す一覧（panel-tools・tools-table）だけ。
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { PipelineView } from '../domain/pipelineView.ts';
import type { RunListView } from '../domain/runList.ts';
import { bootPanel } from '../test/fakeDom.ts';
import type { BootOptions, FakeNode, PanelHarness } from '../test/fakeDom.ts';
import { runningView } from '../test/liveFixtures.ts';
import { listView, row } from '../test/runListFixtures.ts';
import { callArgs, withoutComments } from '../test/sourceText.ts';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';

const NONCE = 'TESTNONCE';
const HERE_DIR = path.dirname(fileURLToPath(import.meta.url));

interface Row {
  kind: 'agent' | 'skill' | 'tool';
  name: string;
  count: number;
  stages: string[];
  durationSec: number | null;
}
const rowOf = (kind: Row['kind'], name: string, count: number): Row => ({ kind, name, count, stages: ['調査'], durationSec: null });
const tools = (rows: Row[]): object => ({ rows, kinds: rows.length, total: rows.reduce((s, r) => s + r.count, 0), omitted: 0, showTime: false, notice: null });
const THREE = tools([rowOf('agent', 'module-reader', 3), rowOf('skill', 'review', 2), rowOf('tool', 'Read', 5)]);
const FOUR = tools([rowOf('agent', 'module-reader', 3), rowOf('skill', 'review', 2), rowOf('tool', 'Read', 5), rowOf('tool', 'Grep', 9)]);
const viewWith = (t: object): PipelineView => ({ ...runningView(83), tools: t }) as unknown as PipelineView;

const RUN_ROWS = [row({ key: 'here|a', session: 'run-a' }), row({ key: 'here|b', session: 'run-b' })];
const listFor = (selected: 'a' | 'b'): RunListView => listView(RUN_ROWS, { selected: `here|${selected}` });

const LAYOUT: BootOptions['layout'] = (n) => {
  switch (n.getAttribute('data-scroll')) {
    case 'panel-tools':
      return { scrollHeight: 900, clientHeight: 400 };
    case 'list':
      return { scrollHeight: 1000, clientHeight: 200 };
    default:
      return null;
  }
};
const boot = (t: object = THREE, list: RunListView = listFor('a')): PanelHarness => bootPanel(renderPanelHtml(viewWith(t), NONCE, list), { layout: LAYOUT });
const send = (h: PanelHarness, t: object, list: RunListView = listFor('a')): void => h.send({ type: 'render', html: renderViewBody(viewWith(t), list) });

const one = (node: FakeNode, selector: string): FakeNode => {
  const found = node.querySelector(selector);
  assert.ok(found, `${selector} がある`);
  return found;
};
const detailTab = (h: PanelHarness, name: string): FakeNode => one(h.doc, `button[data-detail-tab="${name}"]`);
const selectedTabs = (h: PanelHarness): string[] => h.doc.querySelectorAll('button[data-detail-tab]').filter((b) => b.getAttribute('aria-selected') === 'true').map((b) => b.getAttribute('data-detail-tab')!);
const shownPanels = (h: PanelHarness): string[] =>
  h.doc
    .querySelectorAll('[role="tabpanel"]')
    .filter((p) => p.closest('[hidden]') === null)
    .map((p) => p.getAttribute('data-detail-panel') ?? '');
const scroller = (h: PanelHarness, name: string): FakeNode => one(h.doc, `[data-scroll="${name}"]`);
const types = (h: PanelHarness): string[] => h.posted.map((m) => (m as { type: string }).type);
const runBtn = (h: PanelHarness, key: string): FakeNode => {
  const found = h.doc.querySelectorAll('button[data-run]').find((b) => b.getAttribute('data-run') === key);
  assert.ok(found, `${key} の実行の行がある`);
  return found;
};
const hiddenNow = (node: FakeNode): boolean => node.closest('[hidden]') !== null;

/** tools のタブを開き、パネルの縦を 80、表の枠の横を 40 にする（範囲に収まって読み戻せることを確かめる） */
function openToolsAndScroll(h: PanelHarness): void {
  detailTab(h, 'tools').dispatch('click');
  scroller(h, 'panel-tools').scrollTop = 80;
  scroller(h, 'tools-table').scrollLeft = 40;
  assert.equal(scroller(h, 'panel-tools').scrollTop, 80, 'パネルは縦にスクロールできる（検査が空振りでない）');
  assert.equal(scroller(h, 'tools-table').scrollLeft, 40, '表の枠に横の位置を書いて読み戻せる（検査が空振りでない）');
}

// ---- AC-30：タブを押すと、そのパネルだけが見える。送るメッセージは増えない ----

test('D0047-AC-30: 「エージェント・スキル」のタブを押すと、選ばれているのは tools だけ、見えるパネルは tools だけ。ほかのタブへ移って「図と出力」へも戻せる', () => {
  const h = boot();
  assert.deepEqual(selectedTabs(h), ['diagram']);
  assert.deepEqual(shownPanels(h), ['diagram']);
  detailTab(h, 'tools').dispatch('click');
  assert.deepEqual(selectedTabs(h), ['tools']);
  assert.deepEqual(shownPanels(h), ['tools']);
  detailTab(h, 'usage').dispatch('click');
  assert.deepEqual(shownPanels(h), ['usage']);
  detailTab(h, 'tools').dispatch('click');
  assert.deepEqual(shownPanels(h), ['tools']);
  detailTab(h, 'diagram').dispatch('click');
  assert.deepEqual(selectedTabs(h), ['diagram']);
  assert.deepEqual(shownPanels(h), ['diagram']);
});

test('D0047-AC-30: タブを押しても、表の枠を押しても、描き直しを受けても、拡張へ送るのは ready だけ（切り替えでは何も送らない）', () => {
  const h = boot();
  detailTab(h, 'tools').dispatch('click');
  one(h.doc, '[data-keep="tools-table"]').dispatch('click');
  one(h.doc, '.tools-name').dispatch('click');
  send(h, FOUR);
  detailTab(h, 'artifacts').dispatch('click');
  detailTab(h, 'tools').dispatch('click');
  assert.deepEqual(h.posted, [{ type: 'ready' }]);
});

test('D0047-AC-30: PANEL_SCRIPT が postMessage で送る type は ready・openArtifact・selectRun の 3 つだけ（新しい種類を足さない）（今のまま通る。守る）', () => {
  const source = readFileSync(path.join(HERE_DIR, 'panelScript.ts'), 'utf8');
  const sent = callArgs(withoutComments(source), 'postMessage').map((args) => /\btype\s*:\s*'([^']+)'/.exec(args)?.[1] ?? null);
  assert.ok(sent.length >= 3, `postMessage の呼び出しが読めている（${sent.length} 件）`);
  assert.deepEqual([...new Set(sent)].sort(), ['openArtifact', 'ready', 'selectRun']);
});

// ---- AC-31：描き直しをまたぐ保持 ----

/** (a) 見えているとき：tools のタブで縦 80・横 40・枠に焦点を置き、同じ内容の描き直しを受けたあと。before は描き直し前の枠 */
function rerenderVisible(): { h: PanelHarness; before: FakeNode } {
  const h = boot();
  openToolsAndScroll(h);
  const before = scroller(h, 'tools-table');
  before.focus();
  assert.ok(h.doc.activeElement === before, '枠に焦点がある（検査が空振りでない）');
  send(h, THREE);
  return { h, before };
}

test('D0047-AC-31: (a) 見えているとき：描き直しのあとも、タブの選びと見えるパネルは tools のまま。表の枠は作り直されている', () => {
  const { h, before } = rerenderVisible();
  assert.deepEqual(selectedTabs(h), ['tools']);
  assert.deepEqual(shownPanels(h), ['tools']);
  assert.ok(scroller(h, 'tools-table') !== before, '枠は作り直されている');
});

test('D0047-AC-31: (a) 見えているとき：描き直しのあとも、縦の位置（パネル）80・横の位置（表の枠）40 が残る。中身が替わる描き直しを重ねても残る', () => {
  const { h } = rerenderVisible();
  assert.equal(scroller(h, 'panel-tools').scrollTop, 80);
  assert.equal(scroller(h, 'tools-table').scrollLeft, 40);
  send(h, FOUR);
  assert.equal(scroller(h, 'panel-tools').scrollTop, 80, '何度描き直しても残る（中身が替わっても）');
  assert.equal(scroller(h, 'tools-table').scrollLeft, 40);
});

test('D0047-AC-31: (a) 見えているとき：描き直しのあとも、焦点が新しい枠（同じ data-keep="tools-table"）に戻る', () => {
  const { h, before } = rerenderVisible();
  const after = scroller(h, 'tools-table');
  assert.ok(after !== before, '枠は作り直されている');
  assert.ok(h.doc.activeElement === after, '焦点が新しい枠に戻る');
  assert.equal(after.getAttribute('data-keep'), 'tools-table');
});

/** (b) 別のタブ（使用量）を見ていて tools のパネルが隠れているとき：使用量のタブのボタンに焦点を置き、中身が替わる描き直しを受けたあと */
function rerenderHidden(): { h: PanelHarness; usageButton: FakeNode } {
  const h = boot();
  openToolsAndScroll(h);
  detailTab(h, 'usage').dispatch('click');
  assert.ok(hiddenNow(scroller(h, 'panel-tools')), 'tools のパネルは隠れている');
  const usageButton = detailTab(h, 'usage');
  usageButton.focus();
  assert.ok(h.doc.activeElement === usageButton, '別のタブのボタンに焦点がある（検査が空振りでない）');
  send(h, FOUR);
  return { h, usageButton };
}

test('D0047-AC-31: (b) 隠れているとき：描き直しのあとも、タブの選びは別のタブ（使用量）のまま、見えるパネルも使用量だけで、tools は hidden のまま', () => {
  const { h } = rerenderHidden();
  assert.deepEqual(selectedTabs(h), ['usage']);
  assert.deepEqual(shownPanels(h), ['usage']);
  assert.ok(hiddenNow(scroller(h, 'panel-tools')), 'tools のパネルは hidden のまま');
});

test('D0047-AC-31: (b) 隠れているとき：描き直しのあとも、焦点があった要素（別のタブのボタン）が新しい同じ要素（data-keep="detail-tab:usage"）に戻る', () => {
  const { h, usageButton } = rerenderHidden();
  const active = h.doc.activeElement;
  assert.ok(active !== null && active !== usageButton, '焦点は新しい要素にある');
  assert.equal(active.getAttribute('data-keep'), 'detail-tab:usage');
  assert.ok(active === detailTab(h, 'usage'));
});

test('D0047-AC-31: (b) 隠れているとき：描き直しのあと tools のタブへ戻ると、縦の位置 80・横の位置 40 が戻る', () => {
  const { h } = rerenderHidden();
  detailTab(h, 'tools').dispatch('click');
  assert.deepEqual(shownPanels(h), ['tools']);
  assert.equal(scroller(h, 'panel-tools').scrollTop, 80, '縦の位置が戻る');
  assert.equal(scroller(h, 'tools-table').scrollLeft, 40, '横の位置が戻る');
});

for (const mode of ['render', 'click'] as const) {
  test(`D0047-AC-31: (c) 見る実行が替わる描き直し（${mode === 'render' ? 'aria-pressed が移った HTML だけが届く' : '実行の一覧の行を押して selectRun を送ったあと'}）で、panel-tools・tools-table の位置が 0 に戻る。タブの選び・実行の一覧の位置は残る`, () => {
    const h = boot();
    openToolsAndScroll(h);
    scroller(h, 'list').scrollTop = 150;
    assert.equal(scroller(h, 'list').scrollTop, 150, '一覧はスクロールできる（検査が空振りでない）');
    if (mode === 'click') {
      runBtn(h, 'here|b').dispatch('click');
      assert.deepEqual(h.posted.at(-1), { type: 'selectRun', id: 'here|b' });
    }
    send(h, THREE, listFor('b'));
    assert.equal(scroller(h, 'panel-tools').scrollTop, 0, 'パネルの縦は先頭に戻る');
    assert.equal(scroller(h, 'tools-table').scrollLeft, 0, '表の枠の横は左端に戻る');
    assert.deepEqual(selectedTabs(h), ['tools'], 'タブの選びは残る');
    assert.equal(scroller(h, 'list').scrollTop, 150, '一覧の位置は残る');
    assert.deepEqual(types(h).filter((t) => t !== 'selectRun'), ['ready']);
  });
}

test('D0047-AC-31: (c2) tools のタブを隠しているあいだに見る実行が替わっても、tools のタブへ戻ったとき縦・横の位置は 0（隠れた枠の位置は記憶にしか無いので、記憶を消し忘れると戻ってしまう）', () => {
  const h = boot();
  openToolsAndScroll(h);
  detailTab(h, 'usage').dispatch('click');
  send(h, THREE, listFor('b'));
  detailTab(h, 'tools').dispatch('click');
  assert.deepEqual(shownPanels(h), ['tools']);
  assert.equal(scroller(h, 'panel-tools').scrollTop, 0);
  assert.equal(scroller(h, 'tools-table').scrollLeft, 0);
});

test('D0047-AC-31: (d) 同じ実行のままの描き直し（行の選びが替わらない）では先頭に戻らない：何度描き直しても位置が残る', () => {
  const h = boot();
  openToolsAndScroll(h);
  for (let i = 0; i < 3; i++) send(h, i % 2 === 0 ? FOUR : THREE);
  assert.equal(scroller(h, 'panel-tools').scrollTop, 80);
  assert.equal(scroller(h, 'tools-table').scrollLeft, 40);
});

test('D0047-AC-31: (e) tools のパネルが隠れているあいだの描き直し（表が空になる描き直しも）で、例外が出ない', () => {
  const h = boot();
  openToolsAndScroll(h);
  scroller(h, 'tools-table').focus();
  detailTab(h, 'diagram').dispatch('click');
  assert.doesNotThrow(() => send(h, FOUR));
  assert.doesNotThrow(() => send(h, tools([])));
  assert.doesNotThrow(() => send(h, THREE));
  assert.deepEqual(selectedTabs(h), ['diagram']);
});

test('D0047-AC-31: (f) 表が空になる（枠が消える）描き直しで例外を出さず、枠が戻れば焦点・位置の復元がまた働く', () => {
  const h = boot();
  detailTab(h, 'tools').dispatch('click');
  scroller(h, 'tools-table').focus();
  assert.doesNotThrow(() => send(h, tools([])));
  assert.equal(h.doc.querySelector('[data-scroll="tools-table"]'), null, '空の表には枠が無い');
  send(h, THREE);
  scroller(h, 'tools-table').focus();
  const frame = scroller(h, 'tools-table');
  send(h, FOUR);
  assert.ok(h.doc.activeElement === scroller(h, 'tools-table') && h.doc.activeElement !== frame, '枠が戻ったあとの描き直しでは、また焦点が戻る');
});

test('D0047-AC-27: 表の枠は Tab で焦点を取れる枠（tabindex="0"）で、矢印キーなどのキー操作をスクリプトが横取りしない（キーボードだけで枠が自分で横にスクロールできる）', () => {
  const h = boot();
  detailTab(h, 'tools').dispatch('click');
  const frame = scroller(h, 'tools-table');
  assert.equal(frame.getAttribute('tabindex'), '0');
  for (const key of ['ArrowLeft', 'ArrowRight', 'ArrowDown', 'PageDown', 'Home', 'End', ' ', 'Enter']) {
    assert.equal(frame.dispatch('keydown', { key }).defaultPrevented, false, `${JSON.stringify(key)} を横取りしない`);
  }
  assert.deepEqual(h.posted, [{ type: 'ready' }]);
});
