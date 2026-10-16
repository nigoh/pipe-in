// 実行の記録（state.json）の読み取り。AC-03〜AC-05。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseRunRecord } from './runRecord.ts';
import { stageRunEntry, stateJson } from '../test/fixtures.ts';

test('AC-03: state.json がないとき、例外が出ず、段の実行0件・final null・合計の費用 0', () => {
  const record = parseRunRecord(null);
  assert.deepEqual(record.stageRuns, []);
  assert.equal(record.final, null);
  assert.equal(record.totalCostUsd, 0);
});

test('AC-04: 途中で切れた JSON でも、例外が出ず AC-03 と同じ結果', () => {
  const record = parseRunRecord('{"runs": [');
  assert.deepEqual(record.stageRuns, []);
  assert.equal(record.final, null);
  assert.equal(record.totalCostUsd, 0);
});

test('AC-05: 段の実行・確認の結果・テスト先行の結果・判定を区別して1件ずつ取り出す', () => {
  const text = stateJson({
    runs: [
      stageRunEntry({ stage: 'red', seq: 3 }),
      { stage: 'red', review: 'approved', feedback: null },
      { stage: 'red', result: { status: 'red', summary: '落ちた', tests: [], commands: [] } },
      { stage: 'red', command_check: { command: 'npm test', returncode: 1 } },
      {
        stage: 'test',
        attempt: 1,
        verdict: { status: 'pass', summary: '通った', failures: [], commands: [], command_check: null },
      },
    ],
  });
  const record = parseRunRecord(text);

  assert.equal(record.stageRuns.length, 1);
  assert.equal(record.stageRuns[0].stage, 'red');
  assert.equal(record.stageRuns[0].seq, 3);

  assert.equal(record.reviews.length, 1);
  assert.equal(record.reviews[0].stage, 'red');
  assert.equal(record.reviews[0].action, 'approved');

  assert.equal(record.redResults.length, 1);
  assert.equal(record.redResults[0].status, 'red');

  assert.equal(record.verdicts.length, 1);
  assert.equal(record.verdicts[0].status, 'pass');
});
