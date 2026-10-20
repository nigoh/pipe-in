// 一覧つきのパネルのスクリプトのふるまい（D0019）。panelScript.ts の PANEL_SCRIPT を node:vm で、偽の DOM と偽の時計の上で動かす。
// スクリプトの数え上げは D0017 のまま：行の待ち時間・経過は [data-elapsed]（基準の秒）に乗り、行を押すと selectRun を送る。
// 2版目：行の構造（3 行・run-right・run-sub）に合わせて直した。数え上げ・焦点を戻す・選びの保持の検査は残す。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';
import type { RunListView } from '../domain/runList.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { bootPanel } from '../test/fakeDom.ts';
import type { FakeNode, PanelHarness } from '../test/fakeDom.ts';
import { finishedView, runningView } from '../test/liveFixtures.ts';
import { showcaseView } from '../test/reasonFixtures.ts';
import { listView, row, sampleRows } from '../test/runListFixtures.ts';

const NONCE = 'TESTNONCE';
const boot = (view: PipelineView, list: RunListView): PanelHarness => bootPanel(renderPanelHtml(view, NONCE, list));
const render = (h: PanelHarness, view: PipelineView, list: RunListView): void => h.send({ type: 'render', html: renderViewBody(view, list) });

const rowButtons = (h: PanelHarness): FakeNode[] => h.doc.querySelectorAll('button[data-run]');
const rowButton = (h: PanelHarness, key: string): FakeNode => {
  const found = rowButtons(h).find((b) => b.getAttribute('data-run') === key);
  assert.ok(found, `${key} の行がある`);
  return found;
};
/** 一覧の行ごとの、数え上げる要素（data-elapsed を持つ待ち時間・経過）の今の文字。持たない行（固定の文字だけの行を含む）は入らない。 */
function elapsedByRow(h: PanelHarness): Record<string, string> {
  const out: Record<string, string> = {};
  for (const b of rowButtons(h)) {
    const el = b.querySelector('[data-elapsed]');
    if (el !== null) out[b.getAttribute('data-run')!] = h.text(el);
  }
  return out;
}
const pressedKeys = (h: PanelHarness): string[] =>
  rowButtons(h)
    .filter((b) => b.getAttribute('aria-pressed') === 'true')
    .map((b) => b.getAttribute('data-run')!);

// 終わった実行を選んでいる一覧（詳細に数え上げる要素が無い）。数え上げるのは行の待ち時間・経過だけ。
const LIST = listView(sampleRows(), { selected: 'here|survey' });
const FIRST = { 'here|': '0:42', 'wt.feat-x|': '0:07', 'here|diagrams': '2:05', 'wt.fix-login|': '1:01' };
const AFTER_1S = { 'here|': '0:43', 'wt.feat-x|': '0:08', 'here|diagrams': '2:06', 'wt.fix-login|': '1:02' };

// ---- AC-12・AC-66：待ち時間・経過の数え上げ ----

test('D0019-AC-12: 確認待ちの行の待ち時間と、動いている行の経過は、読み込み直後は基準の秒の表示で、偽の時計を進めると 1 秒ごとに増える。終わった行は増えない', () => {
  const h = boot(finishedView(), LIST);
  const doneText = h.text(rowButton(h, 'here|survey'));
  assert.deepEqual(elapsedByRow(h), FIRST);
  h.advance(999);
  assert.deepEqual(elapsedByRow(h), FIRST);
  h.advance(1);
  assert.deepEqual(elapsedByRow(h), AFTER_1S);
  h.advance(4000);
  assert.deepEqual(elapsedByRow(h), { 'here|': '0:47', 'wt.feat-x|': '0:12', 'here|diagrams': '2:10', 'wt.fix-login|': '1:06' });
  assert.equal(h.activeIntervals(), 1, 'タイマーは 1 つだけ');
  assert.equal(h.text(rowButton(h, 'here|survey')), doneText, '終わった行は固定の文字');
});

test('D0019-AC-66: 動いている行の経過も 1 秒ごとに増える（60 秒をまたいで m:ss が繰り上がる）。確認待ち以外の行には「待ち」の文字は出ない', () => {
  const h = boot(finishedView(), listView([row({ key: 'here|a', state: 'running', elapsed: { seconds: 59, live: true } }), row({ key: 'here|b', state: 'done', result: '合格', elapsed: { seconds: 59, live: false } })]));
  assert.deepEqual(elapsedByRow(h), { 'here|a': '0:59' });
  h.advance(2000);
  assert.deepEqual(elapsedByRow(h), { 'here|a': '1:01' });
  assert.doesNotMatch(h.text(rowButton(h, 'here|a')), /待ち /);
});

test('D0019-AC-12: パネルが隠れると数え上げが止まり、また見えると続きから数える', () => {
  const h = boot(finishedView(), LIST);
  h.advance(2000);
  assert.deepEqual(elapsedByRow(h)['here|'], '0:44');
  h.setVisibility('hidden');
  assert.equal(h.activeIntervals(), 0);
  h.advance(60_000);
  assert.deepEqual(elapsedByRow(h)['here|'], '0:44', '隠れている間は増えない');
  h.setVisibility('visible');
  assert.equal(h.activeIntervals(), 1);
});

test('D0019-AC-12: 確認待ちの行も動いている行も無い一覧（かつ図にも数える要素が無い）ならタイマーを回さない', () => {
  const h = boot(finishedView(), listView([row({ key: 'here|a', state: 'idle' }), row({ key: 'here|b', state: 'done', result: '合格', elapsed: { seconds: 30, live: false } })]));
  assert.equal(h.activeIntervals(), 0);
  assert.deepEqual(elapsedByRow(h), {});
});

test('D0019-AC-12: 待ち時間が読めない行（waitingSec が null）は数えず、ほかの行は数える', () => {
  const h = boot(finishedView(), listView([row({ key: 'here|a', state: 'waiting', waitingSec: null }), row({ key: 'here|b', state: 'waiting', waitingSec: 10 })]));
  assert.deepEqual(elapsedByRow(h), { 'here|b': '0:10' });
  h.advance(3000);
  assert.deepEqual(elapsedByRow(h), { 'here|b': '0:13' });
});

test('D0019-AC-12: render で描き直すと、基準の秒に数え直す（古い増分を足さない）', () => {
  const h = boot(finishedView(), LIST);
  h.advance(10_000);
  render(h, finishedView(), LIST);
  assert.deepEqual(elapsedByRow(h), FIRST);
  h.advance(1000);
  assert.deepEqual(elapsedByRow(h), AFTER_1S);
});

// ---- 行を押す ----

test('D0019-AC-57: 行を押すと selectRun を、その行の key で送る（増えるメッセージの種類は無い）。行の中の文字を押しても行に着く', () => {
  const h = boot(runningView(83), LIST);
  rowButton(h, 'wt.feat-x|').dispatch('click');
  assert.deepEqual(h.posted, [{ type: 'ready' }, { type: 'selectRun', id: 'wt.feat-x|' }]);
  const inner = rowButton(h, 'wt.feat-x|').children.find((c): c is FakeNode => 'tagName' in c && c.tagName === 'span')!;
  inner.dispatch('click');
  assert.deepEqual(h.posted.map((m) => (m as { type: string }).type), ['ready', 'selectRun', 'selectRun']);
  for (const m of h.posted) assert.ok(['ready', 'openArtifact', 'selectRun'].includes((m as { type: string }).type));
});

test('D0019-AC-57: 行は <button> なので、Tab で移り Enter・Space で押せる（本物のブラウザが click にする）。スクリプトは行の keydown を独自に扱わない', () => {
  const h = boot(runningView(83), LIST);
  const target = rowButton(h, 'here|diagrams');
  assert.equal(target.tagName, 'button');
  const enter = target.dispatch('keydown', { key: 'Enter' });
  const space = target.dispatch('keydown', { key: ' ' });
  assert.equal(enter.defaultPrevented, false, 'Enter を横取りしない（button の既定の動きに任せる）');
  assert.equal(space.defaultPrevented, false);
  assert.deepEqual(h.posted, [{ type: 'ready' }], 'keydown だけでは何も送らない（click で送る）');
});

test('D0019-AC-57: 見ている行は aria-pressed="true"（ちょうど 1 つ）。render で選びが移る', () => {
  const h = boot(finishedView(), LIST);
  assert.deepEqual(pressedKeys(h), ['here|survey']);
  render(h, finishedView(), listView(sampleRows(), { selected: 'wt.feat-x|' }));
  assert.deepEqual(pressedKeys(h), ['wt.feat-x|']);
});

// ---- AC-28：描き直しで選びが消えない ----

test('D0019-AC-28: 一覧つきで描き直しを送っても、理由の欄の選びと開閉（D0016）が消えない', () => {
  const view = showcaseView();
  const h = boot(view, LIST);
  const g = h.node('implement');
  (g.children.find((c): c is FakeNode => 'tagName' in c && c.tagName === 'text') ?? g).dispatch('click');
  const open = () => h.doc.querySelectorAll('[data-reasons-for]').filter((s) => !s.hidden).map((s) => s.getAttribute('data-reasons-for'));
  assert.deepEqual(open(), ['implement']);
  render(h, view, LIST);
  render(h, view, listView(sampleRows(), { selected: 'here|' }));
  assert.deepEqual(open(), ['implement'], '描き直しても理由の欄は開いたまま');
  assert.equal(h.node('implement').classList.contains('is-picked'), true);
});

test('D0019-AC-28: 一覧つきで描き直しても、数え上げ（D0017）が続く', () => {
  const h = boot(finishedView(), LIST);
  h.advance(3000);
  render(h, finishedView(), LIST);
  h.advance(2000);
  assert.deepEqual(elapsedByRow(h), { 'here|': '0:44', 'wt.feat-x|': '0:09', 'here|diagrams': '2:07', 'wt.fix-login|': '1:03' });
  assert.equal(h.activeIntervals(), 1);
});

test('D0019-AC-28: 数える要素の有無でタイマーが入れ替わる（余計なタイマーを残さない）', () => {
  const quiet = listView([row({ key: 'here|a', state: 'done', result: '合格' }), row({ key: 'here|b', state: 'done', result: '合格' })]);
  const h = boot(finishedView(), quiet);
  assert.equal(h.activeIntervals(), 0);
  render(h, finishedView(), LIST);
  assert.equal(h.activeIntervals(), 1);
  render(h, finishedView(), quiet);
  assert.equal(h.activeIntervals(), 0);
});

test('D0019-AC-28: 一覧の行の描き直しは、戻る矢印の光り（D0017）に影響しない：実行を選び替えた直後は光らない', () => {
  const h = boot(finishedView(), LIST);
  render(h, finishedView(), listView(sampleRows(), { selected: 'here|' }));
  assert.deepEqual(h.doc.querySelectorAll('[data-loop]').filter((l) => l.classList.contains('is-new')), []);
});

// ---- AC-36：選んだあとのフォーカス ----

test('D0019-AC-36: 行にフォーカスがあるとき render で行が作り直されても、フォーカスが同じ data-run の行に戻る', () => {
  const h = boot(finishedView(), LIST);
  const before = rowButton(h, 'wt.feat-x|');
  before.focus();
  before.dispatch('keydown', { key: 'Enter' });
  render(h, finishedView(), listView(sampleRows(), { selected: 'wt.feat-x|' }));
  const after = rowButton(h, 'wt.feat-x|');
  assert.notEqual(after, before, '行は作り直されている');
  // 失敗時に偽の DOM 全体を比べて固まらないよう、assert.ok で見る
  assert.ok(h.doc.activeElement === after, 'render のあと、フォーカスが同じ data-run の新しい行に戻っていない');
});

test('D0019-AC-36: フォーカスが行に無いとき、render でフォーカスを動かさない', () => {
  const h = boot(finishedView(), LIST);
  render(h, finishedView(), LIST);
  assert.ok(h.doc.activeElement === null, 'フォーカスが動いている');
});

test('D0019-AC-36: フォーカスしていた行が render のあと無くなっていたら、フォーカスを戻さない（別の行にも移さない）', () => {
  const h = boot(finishedView(), LIST);
  rowButton(h, 'wt.feat-x|').focus();
  render(h, finishedView(), listView([row({ key: 'here|a', state: 'done', result: '合格' })], { selected: 'here|a' }));
  // 偽の DOM は、消えた節のフォーカスを自動では外さない。今ある行のどれにもフォーカスが移っていなければよい
  const active = h.doc.activeElement;
  assert.ok(!rowButtons(h).some((b) => b === active), '今ある行にフォーカスが移っている');
});
