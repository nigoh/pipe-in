// 実行の一覧の行の costUsd（D0066）：domain/runList.ts の summarizeRun が、costText の元の数（state.json の total_cost_usd）を数のまま持つ。
// 作業台の「前の実績」の元になる。読めなければ null。既存の項目（costText など）は変えない。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { summarizeRun } from './runList.ts';
import { clockAt } from '../test/liveFixtures.ts';
import { stateJson } from '../test/fixtures.ts';

const rowOf = (text: string | null) =>
  summarizeRun({ key: 'here|', id: '', branch: null, other: false, memoHead: null, previous: false, stageLogs: [], stateJson: text }, clockAt(0)) as unknown as {
    costText: string;
    costUsd?: number | null;
  };

test('D0066-AC-22: 行に costUsd が入る（total_cost_usd を数のまま。costText と同じ元）', () => {
  const r = rowOf(stateJson({ totalCostUsd: 1.234 }));
  assert.equal(r.costText, '$1.234');
  assert.equal(r.costUsd, 1.234);
  assert.equal(rowOf(stateJson({ totalCostUsd: 0 })).costUsd, 0);
});

const UNREADABLE: [string, string | null][] = [
  ['total_cost_usd が無い', JSON.stringify({ final: null, runs: [] })],
  ['文字', JSON.stringify({ total_cost_usd: 'x', runs: [] })],
  ['null', JSON.stringify({ total_cost_usd: null, runs: [] })],
  ['壊れた JSON', '{'],
  ['記録なし', null],
];
for (const [label, text] of UNREADABLE) {
  test(`D0066-AC-22: ${label} のときの costUsd は null（読めない。例外を出さず、costText は今のまま「—」）`, () => {
    const r = rowOf(text);
    assert.equal(r.costUsd, null);
    assert.equal(r.costText, '—');
  });
}
