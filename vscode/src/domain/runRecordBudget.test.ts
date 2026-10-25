// 記録の読み（D0051 の AC-21〜25）：runs[] の max_budget_usd・resumed・subtype・cost_usd と、前の版・今の形の見本の読み。
// 本体が書く鍵（max_budget_usd・resumed）と拡張が読む鍵は、共通の表 tests/fixtures/budget_record.json で結ぶ（本体のテストも同じ表を読む）。
// StageRun の新しい項目（maxBudgetUsd・resumed・subtype）と PipelineNode.budget は、実装の段で型に入るまで、型に頼らず読む。
// 赤の理由は「まだ読んでいない」：新しい項目が undefined になる（期待は null や false など。厳密に比べる）。
// 「今のまま通る。守る」と書いたものは、今の作りで通り、実装のあとも通り続けることを見張る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseRunRecord } from './runRecord.ts';
import type { StageRun } from './runRecord.ts';
import { buildPipelineView } from './pipelineView.ts';
import type { PipelineNode } from './pipelineView.ts';
import { stageRunEntry, stateJson } from '../test/fixtures.ts';
import { budgetRun, loadBudgetTable } from '../test/budgetFixtures.ts';
import { clockAt, fixtureSnapshot } from '../test/liveFixtures.ts';

/** StageRun の新しい項目（型に入るまでは、型に頼らず読む） */
interface BudgetFields {
  maxBudgetUsd: unknown;
  resumed: unknown;
  subtype: unknown;
}
const fieldsOf = (run: StageRun): BudgetFields => run as unknown as BudgetFields;
/** 節の上限の表示の元（型に入るまでは、型に頼らず読む） */
const budgetOfNode = (node: PipelineNode): unknown => (node as unknown as { budget?: unknown }).budget;

/** 要素 1 つだけの記録を読んで、その段の実行を返す。 */
function readOne(entry: object): StageRun {
  const run = parseRunRecord(stateJson({ runs: [entry] })).stageRuns[0];
  assert.ok(run !== undefined, '段の実行として読めている');
  return run;
}
const baseRun = (): Record<string, unknown> => budgetRun({ stage: 'requirements', seq: 1 });

// ======== AC-21：max_budget_usd は 0.001 以上 10000 以下の有限な数のときだけ上限として読む ========

const LIMIT_CASES: readonly (readonly [string, unknown, number | null])[] = [
  ['0.6', 0.6, 0.6],
  ['整数の 1', 1, 1],
  ['境目の 0.001', 0.001, 0.001],
  ['境目の 10000', 10000, 10000],
  ['9999.999', 9999.999, 9999.999],
  ['0（上限なし）', 0, null],
  ['負の数 -1', -1, null],
  ['負の数 -0.5', -0.5, null],
  ['0.001 に届かない 0.0009', 0.0009, null],
  ['10000 を超える 10000.001', 10000.001, null],
  ['範囲の外の 20000', 20000, null],
  ['文字 "1.0"', '1.0', null],
  ['空の文字', '', null],
  ['文字 "<script>"', '<script>', null],
  ['真偽の true', true, null],
  ['真偽の false', false, null],
  ['null', null, null],
  ['配列 [1]', [1], null],
  ['オブジェクト {}', {}, null],
];
for (const [label, value, expected] of LIMIT_CASES) {
  test(`D0051-AC-21: max_budget_usd が ${label} のとき、上限は ${expected === null ? '「上限なし」(null)' : expected}`, () => {
    const run = readOne({ ...baseRun(), max_budget_usd: value });
    assert.equal(fieldsOf(run).maxBudgetUsd, expected);
  });
}

test('D0051-AC-21: max_budget_usd の項目が無いとき、上限は「上限なし」(null)', () => {
  assert.equal(fieldsOf(readOne(baseRun())).maxBudgetUsd, null);
});

test('D0051-AC-21: max_budget_usd が有限でない数（JSON の 1e999＝Infinity・-1e999）のとき、上限は「上限なし」(null)。例外を出さない', () => {
  for (const raw of ['1e999', '-1e999']) {
    const text = stateJson({ runs: [{ ...baseRun(), max_budget_usd: '@NUMBER@' }] }).replace('"@NUMBER@"', raw);
    assert.ok(text.includes(raw), '記録の文字に 1e999 を入れられている');
    const run = parseRunRecord(text).stageRuns[0];
    assert.ok(run !== undefined, `${raw}: 段の実行として読めている`);
    assert.equal(fieldsOf(run).maxBudgetUsd, null, raw);
  }
});

test('D0051-AC-21: 共通の表の written が使う鍵は keys の中だけで、テスト補助 budgetRun が重ねる鍵と同じ。今のまま通る。守る', () => {
  const table = loadBudgetTable();
  assert.deepEqual([...table.keys].sort(), ['max_budget_usd', 'resumed']);
  for (const c of table.cases) {
    assert.deepEqual(Object.keys(c.written).filter((k) => !table.keys.includes(k)), [], c.memo);
  }
  const plain = Object.keys(stageRunEntry({ stage: 'requirements', seq: 1 }));
  const overlaid = Object.keys(budgetRun({ stage: 'requirements', seq: 1, maxBudgetUsd: 1, resumed: true }));
  assert.deepEqual(overlaid.filter((k) => !plain.includes(k)).sort(), [...table.keys].sort(), 'budgetRun が足す鍵は表の keys と同じ');
});

for (const c of loadBudgetTable().cases) {
  test(`D0051-AC-21: 共通の表のケース「${c.memo}」の written を足した要素を読むと、maxBudgetUsd は ${c.read.maxBudgetUsd === null ? 'null' : c.read.maxBudgetUsd}`, () => {
    const run = readOne({ ...baseRun(), ...c.written });
    assert.equal(fieldsOf(run).maxBudgetUsd, c.read.maxBudgetUsd);
  });
}

// ======== AC-22：続きの会話の印は true のときだけ「続きの会話」 ========

const RESUMED_CASES: readonly (readonly [string, unknown, boolean])[] = [
  ['true', true, true],
  ['false', false, false],
  ['文字 "true"', 'true', false],
  ['数 1', 1, false],
  ['文字 "yes"', 'yes', false],
  ['null', null, false],
  ['配列 [true]', [true], false],
  ['オブジェクト {}', {}, false],
];
for (const [label, value, expected] of RESUMED_CASES) {
  test(`D0051-AC-22: resumed が ${label} のとき、続きの会話は ${expected}`, () => {
    assert.equal(fieldsOf(readOne({ ...baseRun(), resumed: value })).resumed, expected);
  });
}

test('D0051-AC-22: resumed の項目が無いとき、続きの会話は false（「続きでない」）', () => {
  assert.equal(fieldsOf(readOne(baseRun())).resumed, false);
});

for (const c of loadBudgetTable().cases) {
  test(`D0051-AC-22: 共通の表のケース「${c.memo}」の written を足した要素を読むと、resumed は ${c.read.resumed}`, () => {
    const run = readOne({ ...baseRun(), ...c.written });
    assert.equal(fieldsOf(run).resumed, c.read.resumed);
  });
}

// ======== AC-23：cost_usd が負の数・数でないときは 0 ========

for (const [label, value] of [
  ['-0.5', -0.5],
  ['-1', -1],
  ['-0.0001', -0.0001],
  ['-100', -100],
] as const) {
  test(`D0051-AC-23: cost_usd が負の数（${label}）のとき、費用は 0 として読む`, () => {
    assert.equal(readOne(budgetRun({ stage: 'requirements', seq: 1, rawCostUsd: value })).costUsd, 0);
  });
}

test('D0051-AC-23: cost_usd が数でない（文字・null・項目なし・配列）か有限でない数のとき、費用は 0 として読む。今のまま通る。守る', () => {
  const cases: readonly (readonly [string, object])[] = [
    ['文字', budgetRun({ stage: 'requirements', seq: 1, rawCostUsd: '0.5' })],
    ['null', budgetRun({ stage: 'requirements', seq: 1, rawCostUsd: null })],
    ['項目なし', budgetRun({ stage: 'requirements', seq: 1, omit: ['cost_usd'] })],
    ['配列', budgetRun({ stage: 'requirements', seq: 1, rawCostUsd: [0.5] })],
  ];
  for (const [label, entry] of cases) assert.equal(readOne(entry).costUsd, 0, label);
  for (const raw of ['1e999', '-1e999']) {
    const text = stateJson({ runs: [{ ...baseRun(), cost_usd: '@NUMBER@' }] }).replace('"@NUMBER@"', raw);
    const run = parseRunRecord(text).stageRuns[0];
    assert.ok(run !== undefined);
    assert.equal(run.costUsd, 0, raw);
  }
});

test('D0051-AC-23: 0 以上の費用はそのまま読む。今のまま通る。守る', () => {
  assert.equal(readOne(budgetRun({ stage: 'requirements', seq: 1, costUsd: 0 })).costUsd, 0);
  assert.equal(readOne(budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.42 })).costUsd, 0.42);
  assert.equal(readOne(budgetRun({ stage: 'requirements', seq: 1, costUsd: 12.3456 })).costUsd, 12.3456);
});

// ======== AC-24：subtype は文字のときだけ読む ========

for (const subtype of ['success', 'error_max_budget_usd', 'error_max_turns', 'error_during_execution', 'error_max_buffer_size']) {
  test(`D0051-AC-24: subtype が文字 ${subtype} のとき、そのまま読む`, () => {
    assert.equal(fieldsOf(readOne(budgetRun({ stage: 'requirements', seq: 1, subtype }))).subtype, subtype);
  });
}

for (const [label, value] of [
  ['数 1', 1],
  ['null', null],
  ['真偽の true', true],
  ['配列 []', []],
  ['オブジェクト {}', {}],
] as const) {
  test(`D0051-AC-24: subtype が文字でない（${label}）とき、結果の種類は「不明」(null)`, () => {
    assert.equal(fieldsOf(readOne(budgetRun({ stage: 'requirements', seq: 1, subtype: value }))).subtype, null);
  });
}

test('D0051-AC-24: subtype の項目が無いとき、結果の種類は「不明」(null)', () => {
  assert.equal(fieldsOf(readOne(budgetRun({ stage: 'requirements', seq: 1, omit: ['subtype'] }))).subtype, null);
});

// ======== AC-25：前の版・今の形の記録を読んでも、例外が出ず、すべての節が「上限なし」 ========
// 前の版の形の記録（tests/fixtures/pipe_in/）と、上限と印を持たない今の形の記録（pipe_dev/・showcase*）

const FIXTURE_DIRS: readonly (readonly string[])[] = [
  ['pipe_in', 'finished'],
  ['pipe_in', 'running'],
  ['pipe_in', 'waiting'],
  ['pipe_dev', 'finished'],
  ['pipe_dev', 'running'],
  ['pipe_dev', 'waiting'],
  ['showcase'],
  ['showcase_running'],
  ['showcase_running_next'],
  ['showcase_waiting'],
];

for (const parts of FIXTURE_DIRS) {
  const name = parts.join('/');
  test(`D0051-AC-25: 見本 ${name} を読んでも例外が出ず、すべての節の budget は null（上限なし）`, () => {
    const view = buildPipelineView(fixtureSnapshot(...parts), clockAt(100));
    assert.ok(view.nodes.length > 0, '節がある');
    assert.deepEqual(
      view.nodes.filter((n) => budgetOfNode(n) !== null).map((n) => n.id),
      [],
      'budget が null でない節',
    );
  });

  const empty = parts[1] === 'running';
  test(`D0051-AC-25: 見本 ${name} の stageRuns は、すべて maxBudgetUsd が null・resumed が false${empty ? '（実行が空。今のまま通る。守る）' : ''}`, () => {
    const record = parseRunRecord(fixtureSnapshot(...parts).stateJson);
    // running の 2 つは、まだ終わった実行が無い（runs が空）。それ以外は実行がある。
    if (!empty) assert.ok(record.stageRuns.length > 0, '段の実行がある');
    assert.deepEqual(
      record.stageRuns.filter((r) => fieldsOf(r).maxBudgetUsd !== null || fieldsOf(r).resumed !== false).map((r) => r.seq),
      [],
      '上限か印が読まれた実行',
    );
  });
}
