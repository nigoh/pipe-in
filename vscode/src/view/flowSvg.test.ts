// 左の列のパイプライン図（SVG の流れ図）。本線の矢印・戻りの矢印（修正・差し戻し）・節の状態。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderFlowSvg } from './flowSvg.ts';
import { renderViewBody } from './panelHtml.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { snapshot, stageRunEntry, stateJson } from '../test/fixtures.ts';

const count = (text: string, re: RegExp) => (text.match(re) ?? []).length;

test('流れ図：11個の節と、それをつなぐ10本の本線の矢印を描く', () => {
  const svg = renderFlowSvg(buildPipelineView(snapshot()).nodes);
  assert.match(svg, /^<svg class="flow"/);
  assert.match(svg, /role="img"/);
  assert.equal(count(svg, /<g class="node is-/g), 11);
  assert.equal(count(svg, /class="edge"/g), 10);
  for (const label of ['要件メモ', '要件定義', '設計', 'テスト先行', '実装', '検証', '判定', '完了']) {
    assert.match(svg, new RegExp(`>${label}<`), label);
  }
});

test('流れ図：戻りの矢印は4本（確認から同じ段へ3本、判定から実装へ1本）。何も起きていなければ強調しない', () => {
  const svg = renderFlowSvg(buildPipelineView(snapshot()).nodes);
  assert.equal(count(svg, /<g class="loop[ "]/g), 4);
  assert.equal(count(svg, /class="loop is-hot"/g), 0);
  assert.match(svg, /data-loop="revise:requirements"/);
  assert.match(svg, /data-loop="revise:design"/);
  assert.match(svg, /data-loop="revise:red"/);
  assert.match(svg, /data-loop="send-back"/);
});

test('流れ図：修正の依頼・差し戻しが起きた戻りの矢印は強調し、回数を添える', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [
          stageRunEntry({ stage: 'requirements', seq: 1 }),
          { stage: 'requirements', review: 'revise', feedback: 'a' },
          stageRunEntry({ stage: 'requirements', seq: 2 }),
          { stage: 'requirements', review: 'approved' },
          stageRunEntry({ stage: 'implement', seq: 3, attempt: 1 }),
          stageRunEntry({ stage: 'implement', seq: 4, attempt: 2 }),
        ],
      }),
    }),
  );
  const svg = renderFlowSvg(view.nodes);
  assert.equal(count(svg, /class="loop is-hot"/g), 2);
  assert.match(svg, /<g class="loop is-hot" data-loop="revise:requirements">/);
  assert.match(svg, /<g class="loop is-hot" data-loop="send-back">/);
  assert.match(svg, />修正 1回</);
  assert.match(svg, />差し戻し 1回</);
});

test('流れ図：段の節にはターン・費用・時間を出す', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [stageRunEntry({ stage: 'design', seq: 1, numTurns: 23, costUsd: 1.706, durationSec: 336.7 })],
      }),
    }),
  );
  assert.match(renderFlowSvg(view.nodes), />23 ターン・\$1\.706・337s</);
});

test('流れ図：省略した確認は is-skipped と「省略」で出す', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [stageRunEntry({ stage: 'requirements', seq: 1 }), stageRunEntry({ stage: 'design', seq: 2 })],
      }),
    }),
  );
  const svg = renderFlowSvg(view.nodes);
  assert.match(svg, /<g class="node is-skipped" data-node="review:requirements">/);
  assert.match(svg, /class="node-status"[^>]*>[^<]*省略</);
});

test('流れ図：ログから来た文字はないが、節の名前も含めて文字は必ずエスケープされる形で入る', () => {
  const svg = renderFlowSvg(buildPipelineView(snapshot()).nodes);
  assert.doesNotMatch(svg, /<script/i);
  assert.doesNotMatch(svg, /#[0-9a-fA-F]{3,8}\b/);
});

test('パネルの本体は左の列に流れ図を入れる', () => {
  const body = renderViewBody(buildPipelineView(snapshot()));
  assert.match(body, /<svg class="flow"/);
  assert.doesNotMatch(body, /<ol class="nodes">/);
});

test('上の帯：段が動いている間は「いま：段の名前（回）」を出す', () => {
  const body = renderViewBody(
    buildPipelineView(
      snapshot({ stageLogs: [{ fileName: '02_test_2.jsonl', text: '{"_type":"Prompt","stage":"test","resume":null,"prompt":"p"}\n' }] }),
    ),
  );
  assert.match(body, /いま：検証（2 回目）/);
});
