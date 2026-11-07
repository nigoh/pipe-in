// D0077-AC-23・24・25（判断の部分）：会話の道で流した記録は、使用量が「取れない」（usage_summary.available === false）。
// 記録の読み・図の状態・一覧の費用の文が、「$0」を出さずに「取れない」と読めること。古い記録は今までどおり。
// 赤の理由は「まだ作っていない」：RunRecord.usageUnavailable・PipelineView.usageUnavailable が無く（undefined）、usageUnavailableReason は null を返す空の形、
// 費用は 0 や「—」のまま。新しい項目は型に頼らず読む（test/chatFixtures.ts の usageUnavailableOf）。
// 「今のまま通る。守る」と書いたものは、古い記録の読みを見張る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPipelineView } from './pipelineView.ts';
import { parseRunRecord, usageUnavailableReason } from './runRecord.ts';
import { summarizeRun } from './runList.ts';
import { UNAVAILABLE_REASON, chatSnapshot, chatStateJson, fullRuns, oldSnapshot, usageUnavailableOf } from '../test/chatFixtures.ts';
import { clockAt } from '../test/liveFixtures.ts';

const rowOf = (text: string | null) =>
  summarizeRun({ key: 'here|', id: '', branch: null, other: false, memoHead: null, previous: false, stageLogs: [], stateJson: text }, clockAt(0));

// ---- 記録の読み ----

test('D0077-AC-24: usage_summary.available が false の記録は usageUnavailable に理由を持ち、usage は null（零の表を作らない）', () => {
  const record = parseRunRecord(chatStateJson());
  assert.equal(usageUnavailableOf(record), UNAVAILABLE_REASON);
  assert.equal(record.usage, null);
  assert.equal(record.hasDriver, true, 'driver がある（外の会話が書いた記録）');
});

test('D0077-AC-24: 理由が無い・文字でない・空のときは、既定の文（空でない文字）になる', () => {
  for (const reason of [undefined, null, 3, ['x'], '']) {
    const summary = reason === undefined ? { available: false } : { available: false, reason };
    const value = usageUnavailableOf(parseRunRecord(chatStateJson({ usageSummary: summary })));
    assert.equal(typeof value, 'string', `reason=${JSON.stringify(reason)}`);
    assert.ok((value as string).length > 0, `reason=${JSON.stringify(reason)} の既定の文が空`);
  }
});

test('D0077-AC-24: 長い理由は 100 文字までに切る', () => {
  const value = usageUnavailableOf(parseRunRecord(chatStateJson({ usageSummary: { available: false, reason: 'あ'.repeat(300) } })));
  assert.equal(typeof value, 'string');
  assert.ok(Array.from(value as string).length <= 100, `長さ ${Array.from(value as string).length}`);
  assert.ok((value as string).startsWith('あ'));
});

test('D0077-AC-24: usageUnavailableReason は available === false の usage_summary だけ理由の文を返す', () => {
  assert.equal(usageUnavailableReason({ available: false, reason: '理由です' }), '理由です');
  const noReason = usageUnavailableReason({ available: false });
  assert.equal(typeof noReason, 'string');
  assert.ok((noReason as string).length > 0);
  assert.equal(usageUnavailableReason({ available: false, reason: 7 }) === null, false);
});

test('D0077-AC-25: usageUnavailableReason は取れる記録・古い記録・読めない値では null（今のまま通る。守る）', () => {
  for (const value of [null, undefined, 0, 'x', [], {}, { available: true }, { available: 'false' }, { available: 0 }, { tokens: {}, by_model: {} }]) {
    assert.equal(usageUnavailableReason(value), null, JSON.stringify(value));
  }
});

test('D0077-AC-25: usage_summary が無い・cost_usd が数の古い記録は、今までどおり読める（使用量・費用・段の実行の費用。今のまま通る。守る）', () => {
  const record = parseRunRecord(oldSnapshot().stateJson);
  assert.notEqual(record.usage, null);
  assert.equal(record.totalCostUsd, 1.234);
  assert.deepEqual(
    record.stageRuns.map((r) => r.costUsd),
    [0.01, 0.01, 0.01, 0.01, 0.01],
  );
  assert.equal(record.hasDriver, false);
  const noSummary = parseRunRecord(JSON.stringify({ final: 'PASSED', total_cost_usd: 0.5, runs: [] }));
  assert.equal(noSummary.usage, null);
  assert.equal(noSummary.totalCostUsd, 0.5);
});

test('D0077-AC-25: 古い記録は usageUnavailable が null（取れない印を持たない）', () => {
  assert.equal(usageUnavailableOf(parseRunRecord(oldSnapshot().stateJson)), null);
  assert.equal(usageUnavailableOf(parseRunRecord(JSON.stringify({ final: null, runs: [] }))), null);
  assert.equal(usageUnavailableOf(parseRunRecord(null)), null);
  assert.equal(usageUnavailableOf(parseRunRecord('{')), null);
});

// ---- 図の状態 ----

test('D0077-AC-24: 図の状態は usageUnavailable を持ち、使用量・段ごとの費用は null で、段の節の費用も null（0 ではない）', () => {
  const view = buildPipelineView(chatSnapshot({ final: 'PASSED' }));
  assert.equal(usageUnavailableOf(view), UNAVAILABLE_REASON);
  assert.equal(view.usage, null);
  assert.equal(view.stageCosts, null);
  const stages = view.nodes.filter((n) => n.metrics !== null);
  assert.ok(stages.length >= 2, '実行のある段の節がある');
  for (const node of stages) assert.equal(node.metrics?.costUsd, null, `${node.id} の費用は無し（null）`);
});

test('D0077-AC-25: 古い記録の図の状態は、段の節の費用が数・使用量あり・取れない印なし（今までどおり）', () => {
  const view = buildPipelineView(oldSnapshot());
  assert.notEqual(view.usage, null);
  assert.equal(view.nodes.find((n) => n.id === 'draft')?.metrics?.costUsd, 0.03, '下書きは 3 回 × 0.01');
  assert.equal(view.nodes.find((n) => n.id === 'verify')?.metrics?.costUsd, 0.02, '確かめは 2 回 × 0.01');
  assert.equal(usageUnavailableOf(view), null);
});

test('D0077-AC-25: 古い記録の図の状態は、段の節の費用が数で使用量ありのまま（取れない印の欄を足しても変わらない。今のまま通る。守る）', () => {
  const view = buildPipelineView(oldSnapshot());
  assert.notEqual(view.usage, null);
  assert.equal(view.nodes.find((n) => n.id === 'draft')?.metrics?.costUsd, 0.03);
  assert.equal(view.nodes.find((n) => n.id === 'verify')?.metrics?.costUsd, 0.02);
  assert.notEqual(view.stageCosts, null);
});

test('D0077-AC-25: 古い記録で総額が 0 のときは、今までどおり 0 として扱う（「取れない」にしない。今のまま通る。守る）', () => {
  const view = buildPipelineView(chatSnapshot({ runs: fullRuns(0), usageSummary: null, totalCostUsd: 0, driver: false }));
  assert.equal(view.totalCostUsd, 0);
  assert.equal(view.nodes.find((n) => n.id === 'draft')?.metrics?.costUsd, 0);
});

// ---- 一覧の行 ----

test('D0077-AC-24: 一覧の費用の文は、「取れない」記録で「取れない」になり、$ の数を出さない', () => {
  const row = rowOf(chatStateJson({ final: 'PASSED' }));
  assert.match(row.costText, /取れ/);
  assert.doesNotMatch(row.costText, /\$\d/);
});

test('D0077-AC-25: 一覧の費用の文は、古い記録で今までどおり（数なら $、読めなければ —。今のまま通る。守る）', () => {
  assert.equal(rowOf(oldSnapshot().stateJson).costText, '$1.234');
  assert.equal(rowOf(JSON.stringify({ final: null, total_cost_usd: null, runs: [] })).costText, '—');
  assert.equal(rowOf(JSON.stringify({ final: null, runs: [] })).costText, '—');
  assert.equal(rowOf('{').costText, '—');
});
