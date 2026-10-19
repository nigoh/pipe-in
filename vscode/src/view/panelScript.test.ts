// パネルのスクリプト（panelHtml.ts の SCRIPT）のふるまい（D0016）。renderPanelHtml の出力から <script nonce> の中身を取り出し、
// node:vm で、手で書いた小さな偽物の DOM（src/test/fakeDom.ts）の上で動かす。
// 選びはスクリプトの中だけで持ち、拡張へはメッセージを送らない。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';
import type { RunPicker } from './panelHtml.ts';
import { bootPanel } from '../test/fakeDom.ts';
import type { FakeNode, PanelHarness } from '../test/fakeDom.ts';
import { snapshot } from '../test/fixtures.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { oneSendBackView, showcaseView } from '../test/reasonFixtures.ts';

const NONCE = 'TESTNONCE';
const boot = (view: PipelineView, picker?: RunPicker): PanelHarness => bootPanel(renderPanelHtml(view, NONCE, picker));
const body = (view: PipelineView): string => renderViewBody(view);

const SECTION_IDS = ['implement', 'verdict', 'review:requirements'];
const openIds = (h: PanelHarness): string[] =>
  h.doc
    .querySelectorAll('[data-reasons-for]')
    .filter((s) => !s.hidden)
    .map((s) => s.getAttribute('data-reasons-for')!);
const pickedNodeIds = (h: PanelHarness): string[] =>
  h.doc
    .querySelectorAll('[data-reasons]')
    .filter((g) => g.classList.contains('is-picked'))
    .map((g) => g.getAttribute('data-reasons')!);
const pickedLoopIds = (h: PanelHarness): string[] =>
  h.doc
    .querySelectorAll('[data-loop]')
    .filter((l) => l.classList.contains('is-picked'))
    .map((l) => l.getAttribute('data-loop')!);
const pressed = (g: FakeNode): string | null => g.getAttribute('aria-pressed');
/** 節の中の文字（<text>）を押したことにする。target が子でも、節に着く */
const clickNode = (h: PanelHarness, id: string): void => {
  const g = h.node(id);
  const child = g.children.find((c): c is FakeNode => 'tagName' in c && c.tagName === 'text') ?? g;
  child.dispatch('click');
};
const key = (g: FakeNode, k: string) => g.dispatch('keydown', { key: k });

test('D0016-AC-21: 読み込み直後は、理由の欄が全部閉じていて、節は押されていない状態（aria-pressed が false）', () => {
  const h = boot(showcaseView());
  assert.deepEqual(
    h.doc.querySelectorAll('[data-reasons-for]').map((s) => s.getAttribute('data-reasons-for')).sort(),
    [...SECTION_IDS].sort(),
  );
  assert.deepEqual(openIds(h), []);
  for (const id of SECTION_IDS) assert.equal(pressed(h.node(id)), 'false', id);
  assert.deepEqual(pickedNodeIds(h), []);
  assert.deepEqual(pickedLoopIds(h), []);
});

test('D0016-AC-21: 実装を押すと実装の欄だけが開き、実装が選ばれた状態になり、判定から実装への矢印が強調される', () => {
  const h = boot(showcaseView());
  clickNode(h, 'implement');
  assert.deepEqual(openIds(h), ['implement']);
  assert.equal(pressed(h.node('implement')), 'true');
  assert.deepEqual(pickedNodeIds(h), ['implement']);
  assert.deepEqual(pickedLoopIds(h), ['send-back']);
  assert.equal(pressed(h.node('verdict')), 'false');
});

test('D0016-AC-21: 判定を押すと判定の欄が開き、同じ矢印（send-back）が強調される', () => {
  const h = boot(showcaseView());
  clickNode(h, 'verdict');
  assert.deepEqual(openIds(h), ['verdict']);
  assert.deepEqual(pickedLoopIds(h), ['send-back']);
});

test('D0016-AC-21: 確認を押すと確認の欄が開き、その段の修正の矢印が強調される', () => {
  const h = boot(showcaseView());
  clickNode(h, 'review:requirements');
  assert.deepEqual(openIds(h), ['review:requirements']);
  assert.deepEqual(pickedLoopIds(h), ['revise:requirements']);
  assert.equal(pressed(h.node('review:requirements')), 'true');
});

test('D0016-AC-21: 別の節を押すと選びが替わる（前の欄は閉じ、前の矢印の強調は消える）', () => {
  const h = boot(showcaseView());
  clickNode(h, 'implement');
  clickNode(h, 'review:requirements');
  assert.deepEqual(openIds(h), ['review:requirements']);
  assert.deepEqual(pickedNodeIds(h), ['review:requirements']);
  assert.deepEqual(pickedLoopIds(h), ['revise:requirements']);
  assert.equal(pressed(h.node('implement')), 'false');
});

test('D0016-AC-21: 同じ節をもう一度押すと閉じる（欄も強調も消える）', () => {
  const h = boot(showcaseView());
  clickNode(h, 'implement');
  clickNode(h, 'implement');
  assert.deepEqual(openIds(h), []);
  assert.deepEqual(pickedNodeIds(h), []);
  assert.deepEqual(pickedLoopIds(h), []);
  assert.equal(pressed(h.node('implement')), 'false');
});

test('D0016-AC-19: 履歴の無い節を押しても何も起きない（選ぶ前も、選んだあとも、選びは変わらない）', () => {
  const h = boot(showcaseView());
  const noHistory = h.doc.querySelectorAll('[data-node]').filter((g) => !g.hasAttribute('data-reasons'));
  assert.ok(noHistory.length >= 8, '履歴の無い節がある');
  for (const g of noHistory) g.dispatch('click');
  assert.deepEqual(openIds(h), []);
  assert.deepEqual(pickedNodeIds(h), []);
  clickNode(h, 'implement');
  for (const g of noHistory) g.dispatch('click');
  assert.deepEqual(openIds(h), ['implement']);
  assert.deepEqual(pickedLoopIds(h), ['send-back']);
});

test('D0016-AC-21: 選べる節にフォーカスして Enter で開き閉じでき、ページのスクロールを止める（preventDefault）', () => {
  const h = boot(showcaseView());
  const g = h.node('implement');
  const open = key(g, 'Enter');
  assert.deepEqual(openIds(h), ['implement']);
  assert.equal(open.defaultPrevented, true);
  key(g, 'Enter');
  assert.deepEqual(openIds(h), []);
});

test('D0016-AC-21: Space（" "）でも開き閉じでき、スクロールを止める', () => {
  const h = boot(showcaseView());
  const g = h.node('review:requirements');
  const first = key(g, ' ');
  assert.deepEqual(openIds(h), ['review:requirements']);
  assert.equal(first.defaultPrevented, true);
  key(g, ' ');
  assert.deepEqual(openIds(h), []);
});

// すり抜けの道：Enter・Space 以外のキー、選べない節での Enter・Space は何も起こさない
for (const k of ['Tab', 'a', 'Escape', 'ArrowDown', 'Shift']) {
  test(`D0016-AC-21: ${k} キーでは選べる節も開かない`, () => {
    const h = boot(showcaseView());
    const ev = key(h.node('implement'), k);
    assert.deepEqual(openIds(h), []);
    assert.equal(ev.defaultPrevented, false);
  });
}
for (const k of ['Enter', ' ']) {
  test(`D0016-AC-19: 履歴の無い節で ${k === ' ' ? 'Space' : k} を押しても何も起きず、スクロールも止めない`, () => {
    const h = boot(showcaseView());
    clickNode(h, 'implement');
    const input = h.doc.querySelectorAll('[data-node]').find((g) => g.getAttribute('data-node') === 'input')!;
    const ev = key(input, k);
    assert.deepEqual(openIds(h), ['implement']);
    assert.equal(ev.defaultPrevented, false);
  });
}

test('D0016-AC-21: 記録が更新（render）されても、選びが残り、新しい記録の理由に差し替わる', () => {
  const h = boot(oneSendBackView({ summary: '古い要約', failures: [{ criterion: 'AC-01', detail: '古い詳細' }], feedback: 'f' }));
  clickNode(h, 'implement');
  assert.ok(h.section('implement').textContent.includes('古い詳細'));
  const next = oneSendBackView({ summary: '新しい要約', failures: [{ criterion: 'AC-01', detail: '新しい詳細' }, { criterion: 'AC-09', detail: '足された件' }], feedback: 'f' });
  h.send({ type: 'render', html: body(next) });
  assert.deepEqual(openIds(h), ['implement']);
  assert.equal(pressed(h.node('implement')), 'true');
  assert.deepEqual(pickedNodeIds(h), ['implement']);
  assert.deepEqual(pickedLoopIds(h), ['send-back']);
  const text = h.section('implement').textContent;
  assert.ok(text.includes('新しい詳細') && text.includes('足された件'));
  assert.ok(!text.includes('古い詳細'));
});

test('D0016-AC-21: 選んでいなければ、render のあとも欄は全部閉じたまま', () => {
  const h = boot(showcaseView());
  h.send({ type: 'render', html: body(showcaseView()) });
  assert.deepEqual(openIds(h), []);
  assert.deepEqual(pickedNodeIds(h), []);
  assert.deepEqual(pickedLoopIds(h), []);
});

test('D0016-AC-21: render のあとの新しい節も、押して開き閉じできる', () => {
  const h = boot(showcaseView());
  h.send({ type: 'render', html: body(showcaseView()) });
  clickNode(h, 'implement');
  assert.deepEqual(openIds(h), ['implement']);
});

test('D0016-AC-21: 選んでいた節の履歴が無くなると、選びが閉じ、履歴が戻っても閉じたまま', () => {
  const h = boot(showcaseView());
  clickNode(h, 'implement');
  h.send({ type: 'render', html: body(buildPipelineView(snapshot())) });
  assert.deepEqual(openIds(h), []);
  assert.deepEqual(pickedNodeIds(h), []);
  h.send({ type: 'render', html: body(showcaseView()) });
  assert.deepEqual(openIds(h), []);
  assert.deepEqual(pickedLoopIds(h), []);
});

test('D0016-AC-21: 選んでいた節とは別の節の履歴だけが無くなっても、選びは残る', () => {
  const h = boot(showcaseView());
  clickNode(h, 'review:requirements');
  h.send({ type: 'render', html: body(oneSendBackView({})) }); // 確認の直しの履歴は無くなる（差し戻しだけ残る）
  assert.deepEqual(openIds(h), []);
  clickNode(h, 'implement');
  h.send({ type: 'render', html: body(oneSendBackView({ feedback: 'x' })) });
  assert.deepEqual(openIds(h), ['implement']);
});

test('D0016-AC-21: 選べる節にフォーカスがあるとき render で節が作り直されても、フォーカスが同じ節に戻る', () => {
  const h = boot(showcaseView());
  const before = h.node('implement');
  before.focus();
  key(before, 'Enter');
  h.send({ type: 'render', html: body(showcaseView()) });
  const after = h.node('implement');
  assert.notEqual(after, before, '節は作り直されている');
  assert.equal(h.doc.activeElement, after);
});

test('D0016-AC-21: フォーカスが選べる節に無いとき、render でフォーカスを奪わない', () => {
  const h = boot(showcaseView());
  h.send({ type: 'render', html: body(showcaseView()) });
  assert.equal(h.doc.activeElement, null);
});

// ---- メッセージ（守り続ける検査を含む）----

const MESSAGE_TYPES = ['ready', 'openArtifact', 'selectRun'];
const picker: RunPicker = { choices: [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }], selected: 'a' };

test('D0016-AC-13: 読み込み時は ready だけを送る（守り続ける検査）', () => {
  const h = boot(showcaseView());
  assert.deepEqual(h.posted, [{ type: 'ready' }]);
});

test('D0016-AC-13: 節を押す・キーを押す・render を受けても、送るメッセージは増えない（選びは拡張へ送らない）', () => {
  const h = boot(showcaseView());
  const dataNode = (id: string) => h.doc.querySelectorAll('[data-node]').find((g) => g.getAttribute('data-node') === id)!;
  for (const id of ['implement', 'verdict', 'review:requirements', 'input']) {
    dataNode(id).dispatch('click');
    key(dataNode(id), 'Enter');
    key(dataNode(id), ' ');
  }
  h.send({ type: 'render', html: body(showcaseView()) });
  assert.deepEqual(h.posted, [{ type: 'ready' }]);
});

test('D0016-AC-13: 成果物のボタンは openArtifact、実行のボタンは selectRun を送る。送る type は ready・openArtifact・selectRun だけ', () => {
  const view = buildPipelineView(snapshot({ artifacts: { '00_input.md': 'メモ' } }));
  const h = boot(view, picker);
  const artifact = h.doc.querySelectorAll('button[data-artifact]')[0];
  const run = h.doc.querySelectorAll('button[data-run]')[1];
  assert.ok(artifact && run, 'ボタンがある');
  artifact.dispatch('click');
  run.dispatch('click');
  assert.deepEqual(h.posted, [
    { type: 'ready' },
    { type: 'openArtifact', name: '00_input.md' },
    { type: 'selectRun', id: 'b' },
  ]);
  for (const m of h.posted) assert.ok(MESSAGE_TYPES.includes((m as { type: string }).type));
});

test('D0016-AC-13: 節を押したあとも、成果物のボタンは今までどおり openArtifact を送る', () => {
  const h = boot(showcaseView());
  clickNode(h, 'implement');
  const artifact = h.doc.querySelectorAll('button[data-artifact]')[0];
  assert.ok(artifact, '成果物のボタンがある');
  artifact.dispatch('click');
  const types = h.posted.map((m) => (m as { type: string }).type);
  assert.deepEqual(types, ['ready', 'openArtifact']);
});
