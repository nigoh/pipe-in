// パイプの記録の画面：流れ図・帯・注意・実行を選ぶボタン・ステータスバー・パネルとの受け渡し。AC-03・AC-07・AC-08・AC-11。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { renderFlowSvg } from './flowSvg.ts';
import { parseWebviewMessage } from './messages.ts';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';
import { statusBarLabel } from './statusBar.ts';
import {
  DIAGRAMS_STAGES,
  logText,
  promptLine,
  snapshot,
  stageRunEntry,
  stateJson,
  usageSummaryDict,
} from '../test/fixtures.ts';

// 拡張して足す引数：実行を選ぶボタン
type RunPicker = { choices: { id: string; label: string }[]; selected: string };
const renderBody = renderViewBody as (view: ReturnType<typeof buildPipelineView>, picker?: RunPicker) => string;

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

test('AC-11: 実行を選ぶボタンは候補だけで、エスケープする。候補が1つなら出さない', () => {
  const view = diagramsView();
  const body = renderBody(view, {
    choices: [
      { id: '', label: '開発フロー' },
      { id: 'diagrams', label: '<i>diagrams</i>' },
    ],
    selected: 'diagrams',
  });
  assert.equal(count(body, /data-run="/g), 2);
  assert.match(body, /data-run=""/);
  assert.match(body, /data-run="diagrams"[^>]*aria-pressed="true"/);
  assert.match(body, /&lt;i&gt;diagrams&lt;\/i&gt;/);
  assert.doesNotMatch(body, /<i>diagrams<\/i>/);

  assert.equal(count(renderBody(view, { choices: [{ id: '', label: '開発フロー' }], selected: '' }), /data-run="/g), 0);
  assert.equal(count(renderBody(view), /data-run="/g), 0);
});

test('AC-11: selectRun の受け渡しを検め、パネルのスクリプトが送る', () => {
  assert.deepEqual(parseWebviewMessage({ type: 'selectRun', id: 'diagrams' }), { type: 'selectRun', id: 'diagrams' });
  assert.deepEqual(parseWebviewMessage({ type: 'selectRun', id: '' }), { type: 'selectRun', id: '' });
  assert.equal(parseWebviewMessage({ type: 'selectRun', id: 3 }), null);
  assert.equal(parseWebviewMessage({ type: 'selectRun' }), null);
  assert.match(renderPanelHtml(diagramsView(), 'n'), /selectRun/);
});
