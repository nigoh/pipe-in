// ステータスバーのボタン（押すとパネルが開く）の文字と説明。いつも見えていて、実行の様子を一言で出す。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { statusBarLabel } from './statusBar.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { logText, promptLine, snapshot, stageRunEntry, stateJson } from '../test/fixtures.ts';

test('D0006-AC-21: ステータスバー：記録がないときは「pipe-in」だけ', () => {
  const label = statusBarLabel(buildPipelineView(snapshot()));
  assert.equal(label.text, '$(circuit-board) pipe-in');
  assert.match(label.tooltip, /記録がありません/);
});

test('D0006-AC-21: ステータスバーの文字にも説明にも、前の名前が出ない', () => {
  const views = [
    snapshot(),
    snapshot({ stageLogs: [{ fileName: '02_test_2.jsonl', text: logText([promptLine('test')]) }] }),
    snapshot({ stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }) }),
    snapshot({ stateJson: stateJson({ final: 'PASSED', totalCostUsd: 1 }) }),
  ];
  for (const s of views) {
    const label = statusBarLabel(buildPipelineView(s));
    assert.doesNotMatch(label.text + label.tooltip, new RegExp('dev' + 'pipe', 'i'), label.text);
  }
});

test('D0006-AC-21: ステータスバー：段が動いているときは段の名前と回を、回るアイコンつきで出す', () => {
  const view = buildPipelineView(snapshot({ stageLogs: [{ fileName: '02_test_2.jsonl', text: logText([promptLine('test')]) }] }));
  assert.equal(statusBarLabel(view).text, '$(sync~spin) pipe-in: 検証（2 回目）');
});

test('D0006-AC-21: ステータスバー：段と段の合間（人の確認かもしれない）は「待ち」', () => {
  const view = buildPipelineView(snapshot({ stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }) }));
  const label = statusBarLabel(view);
  assert.equal(label.text, '$(clock) pipe-in: 待ち');
  assert.match(label.tooltip, /人の確認かもしれない/);
});

test('D0006-AC-21: ステータスバー：終わったら最終の結果を出し、合計の費用を説明に入れる', () => {
  const cases: [string, string][] = [
    ['PASSED', '$(pass) pipe-in: 合格'],
    ['TEST_FAILED', '$(error) pipe-in: 不合格'],
    ['STOPPED_BY_HUMAN', '$(debug-stop) pipe-in: 中止'],
    ['STAGE_ERROR', '$(error) pipe-in: 段が失敗'],
    ['BLOCKED', '$(warning) pipe-in: 実行できず'],
  ];
  for (const [final, text] of cases) {
    const label = statusBarLabel(buildPipelineView(snapshot({ stateJson: stateJson({ final, totalCostUsd: 7.9894 }) })));
    assert.equal(label.text, text, final);
    assert.match(label.tooltip, /\$7\.989/);
  }
});

test('D0006-AC-21: ステータスバー：知らない最終の結果はそのまま出す', () => {
  const label = statusBarLabel(buildPipelineView(snapshot({ stateJson: stateJson({ final: 'SOMETHING' }) })));
  assert.equal(label.text, '$(info) pipe-in: SOMETHING');
});
