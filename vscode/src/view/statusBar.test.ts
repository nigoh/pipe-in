// ステータスバーのボタン（押すとパネルが開く）の文字と説明。いつも見えていて、実行の様子を一言で出す。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { statusBarLabel } from './statusBar.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { logText, promptLine, snapshot, stageRunEntry, stateJson } from '../test/fixtures.ts';

test('ステータスバー：記録がないときは「devpipe」だけ', () => {
  const label = statusBarLabel(buildPipelineView(snapshot()));
  assert.equal(label.text, '$(circuit-board) devpipe');
  assert.match(label.tooltip, /記録がありません/);
});

test('ステータスバー：段が動いているときは段の名前と回を、回るアイコンつきで出す', () => {
  const view = buildPipelineView(snapshot({ stageLogs: [{ fileName: '02_test_2.jsonl', text: logText([promptLine('test')]) }] }));
  assert.equal(statusBarLabel(view).text, '$(sync~spin) devpipe: 検証（2 回目）');
});

test('ステータスバー：段と段の合間（人の確認かもしれない）は「待ち」', () => {
  const view = buildPipelineView(snapshot({ stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }) }));
  const label = statusBarLabel(view);
  assert.equal(label.text, '$(clock) devpipe: 待ち');
  assert.match(label.tooltip, /人の確認かもしれない/);
});

test('ステータスバー：終わったら最終の結果を出し、合計の費用を説明に入れる', () => {
  const cases: [string, string][] = [
    ['PASSED', '$(pass) devpipe: 合格'],
    ['TEST_FAILED', '$(error) devpipe: 不合格'],
    ['STOPPED_BY_HUMAN', '$(debug-stop) devpipe: 中止'],
    ['STAGE_ERROR', '$(error) devpipe: 段が失敗'],
    ['BLOCKED', '$(warning) devpipe: 実行できず'],
  ];
  for (const [final, text] of cases) {
    const label = statusBarLabel(buildPipelineView(snapshot({ stateJson: stateJson({ final, totalCostUsd: 7.9894 }) })));
    assert.equal(label.text, text, final);
    assert.match(label.tooltip, /\$7\.989/);
  }
});

test('ステータスバー：知らない最終の結果はそのまま出す', () => {
  const label = statusBarLabel(buildPipelineView(snapshot({ stateJson: stateJson({ final: 'SOMETHING' }) })));
  assert.equal(label.text, '$(info) devpipe: SOMETHING');
});
