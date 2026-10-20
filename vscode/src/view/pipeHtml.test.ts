// パイプの記録の画面：流れ図・帯・注意・実行を選ぶボタン・ステータスバー・パネルとの受け渡し。AC-03・AC-07・AC-08・AC-11。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { renderFlowSvg } from './flowSvg.ts';
import { parseWebviewMessage } from './messages.ts';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';
import { statusBarLabel } from './statusBar.ts';
import type { RunListView } from '../domain/runList.ts';
import { listView, row } from '../test/runListFixtures.ts';
import {
  DIAGRAMS_STAGES,
  logText,
  promptLine,
  snapshot,
  stageRunEntry,
  stateJson,
  usageSummaryDict,
} from '../test/fixtures.ts';

// D0019: 実行を選ぶボタン（RunPicker）は実行の一覧（RunListView）に置き換わった。期待する動き（候補だけ・エスケープ・1 つなら出さない）は変えない
const renderBody = renderViewBody as (view: ReturnType<typeof buildPipelineView>, list?: RunListView | null) => string;

function diagramsView(p: Parameters<typeof stateJson>[0] = {}, extra: Partial<Parameters<typeof snapshot>[0]> = {}) {
  return buildPipelineView(snapshot({ stateJson: stateJson({ pipe: 'diagrams', stages: DIAGRAMS_STAGES, ...p }), ...extra }));
}

const count = (s: string, re: RegExp) => (s.match(re) ?? []).length;

test('AC-03: linear の図に確認の戻り矢印だけを描き、判定と差し戻しは描かない', () => {
  const svg = renderFlowSvg(diagramsView().nodes);
  assert.equal(count(svg, /<g class="node is-/g), 7);
  assert.equal(count(svg, /<line class="edge"/g), 6);
  assert.match(svg, /data-loop="revise:survey"/);
  assert.match(svg, /data-loop="revise:draw"/);
  assert.doesNotMatch(svg, /data-loop="revise:verify"/);
  assert.doesNotMatch(svg, /data-loop="send-back"/);
  assert.doesNotMatch(svg, /data-node="verdict"/);
  assert.match(svg, /図とソースの突き合わせ/);
});

test('AC-03: 動いている段・出力の見出し・使用量の表は、段の label で出す', () => {
  const view = diagramsView(
    { usageSummary: usageSummaryDict(), runs: [stageRunEntry({ stage: 'survey', seq: 1 }), stageRunEntry({ stage: 'draw', seq: 2 })] },
    { stageLogs: [{ fileName: '03_verify.jsonl', text: logText([promptLine('verify')]) }] },
  );
  const body = renderBody(view);
  assert.match(body, /いま：図とソースの突き合わせ/);
  assert.match(body, /出力：図とソースの突き合わせ/);
  assert.match(body, /ソースの調査/);
  assert.doesNotMatch(body, /undefined/);
  assert.equal(statusBarLabel(view).text, '$(sync~spin) pipe-in: 図とソースの突き合わせ');
});

test('AC-07: 確認待ちを帯とステータスバーに出し、エスケープする', () => {
  const stages = DIAGRAMS_STAGES.map((s) => (s.name === 'draw' ? { ...s, label: '<b>図</b>' } : s));
  const view = diagramsView({
    stages,
    pendingReview: { stage: 'draw', doc: 'docs/pipeline/diagrams/<x>.md', session_id: 's' },
    runs: [stageRunEntry({ stage: 'survey', seq: 1 }), stageRunEntry({ stage: 'draw', seq: 2 })],
  });
  const body = renderBody(view);
  assert.match(body, /&lt;b&gt;図&lt;\/b&gt;の確認を待っている/);
  assert.match(body, /docs\/pipeline\/diagrams\/&lt;x&gt;\.md/);
  assert.doesNotMatch(body, /<b>図<\/b>/);
  assert.doesNotMatch(body, /人の確認かもしれない/);

  const label = statusBarLabel(view);
  assert.equal(label.text, '$(comment-discussion) pipe-in: <b>図</b>の確認待ち'); // ステータスバーは HTML ではない
  assert.match(label.tooltip, /docs\/pipeline\/diagrams\/<x>\.md/);
});

test('AC-08: warnings を注意の節にエスケープして出す', () => {
  const body = renderBody(diagramsView({ warnings: ['<script>alert(1)</script>', '赤になっていません'] }));
  assert.match(body, /注意/);
  assert.match(body, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(body, /赤になっていません/);
  assert.doesNotMatch(body, /<script>alert/);
  assert.doesNotMatch(renderBody(diagramsView()), /注意/);
});

test('AC-11: 実行を選ぶ一覧は候補だけで、エスケープする。候補が1つでも（0 でも）一覧は出る（D0019-AC-43：1回目の「1つなら出さない」は廃止）', () => {
  const view = diagramsView();
  const body = renderBody(
    view,
    listView([row({ key: 'here|', session: '開発フロー' }), row({ key: 'here|diagrams', session: '<i>diagrams</i>', pipe: '<i>diagrams</i>' })], { selected: 'here|diagrams' }),
  );
  assert.equal(count(body, /data-run="/g), 2);
  assert.match(body, /data-run="here\|"/);
  assert.match(body, /data-run="here\|diagrams"[^>]*aria-pressed="true"/);
  assert.match(body, /&lt;i&gt;diagrams&lt;\/i&gt;/);
  assert.doesNotMatch(body, /<i>diagrams<\/i>/);

  const one = renderBody(view, listView([row({ key: 'here|', session: '開発フロー' })]));
  assert.equal(count(one, /data-run="/g), 1, '1 行でも一覧に出る');
  assert.match(one, /class="run-list"/);
  const none = renderBody(view);
  assert.equal(count(none, /data-run="/g), 0);
  assert.match(none, /実行がありません/);
});

test('AC-11: selectRun の受け渡しを検め、パネルのスクリプトが送る', () => {
  // D0019: selectRun の id は「実行の目印（<場所>|<id>）」の形になった。従来の id だけの形は捨てる
  assert.deepEqual(parseWebviewMessage({ type: 'selectRun', id: 'here|diagrams' }), { type: 'selectRun', id: 'here|diagrams' });
  assert.deepEqual(parseWebviewMessage({ type: 'selectRun', id: 'here|' }), { type: 'selectRun', id: 'here|' });
  assert.equal(parseWebviewMessage({ type: 'selectRun', id: 3 }), null);
  assert.equal(parseWebviewMessage({ type: 'selectRun' }), null);
  assert.match(renderPanelHtml(diagramsView(), 'n'), /selectRun/);
});
