// 段の費用と上限を比べる判断（D0051 の AC-26〜45・58）：1 回の実行の状態（budgetOfRun）と、節に出す回の選び方（pickStageBudget）。
// どちらも純粋な関数で、費用と上限は 1/1000 ドルの整数にそろえて比べる（浮動小数点の誤差で境目がずれない）。
// StageRun の新しい項目（maxBudgetUsd・resumed・subtype）は、実装の段で型に入るまで、型に頼らず渡す。
// 赤の理由は「まだ決めていない」：空の形の budgetOfRun・pickStageBudget は null を返し、節の budget は無い（undefined）。
// 期待が null のテスト（AC-34・43）は、空の形の null と区別できないので、印や上限が無いときに状態を持つ対照を先に確かめる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { budgetOfRun, pickStageBudget } from './stageBudget.ts';
import type { BudgetState, NodeBudget, RunBudget } from './stageBudget.ts';
import type { PipelineNode } from './pipelineView.ts';
import { budgetRun, budgetView, nodeById, plainRun, runningLogFile } from '../test/budgetFixtures.ts';
import { clockAt } from '../test/liveFixtures.ts';

const STOP = 'error_max_budget_usd';

/** budgetOfRun に渡す実行（型に入るまでは、型に頼らず渡す） */
interface RunInput {
  costUsd: number;
  maxBudgetUsd: number | null;
  resumed: boolean;
  subtype: string | null;
}
const budgetOf = budgetOfRun as unknown as (run: RunInput) => RunBudget | null;
const input = (costUsd: number, maxBudgetUsd: number | null, extra: { resumed?: boolean; subtype?: string | null } = {}): RunInput => ({
  costUsd,
  maxBudgetUsd,
  resumed: extra.resumed ?? false,
  subtype: extra.subtype === undefined ? 'success' : extra.subtype,
});
const budgetOfNode = (node: PipelineNode): NodeBudget | null | undefined => (node as unknown as { budget?: NodeBudget | null }).budget;

/** 1 回の実行の状態を確かめる（割合は ratio が number のときだけ見る）。 */
function expectState(run: RunInput, state: BudgetState, label: string): RunBudget {
  const got = budgetOf(run);
  assert.equal(got?.state, state, `${label}: 状態`);
  assert.ok(got !== null && got !== undefined);
  return got;
}

// ======== AC-26：割合と余裕 ========

test('D0051-AC-26: 費用 0.42・上限 1.0 の実行は、割合 0.42・状態「余裕」', () => {
  const got = expectState(input(0.42, 1.0), 'ok', '0.42 / 1.0');
  assert.equal(got.ratio, 0.42);
});

test('D0051-AC-26: 費用 0・上限 1.0 の実行は、割合 0・状態「余裕」（0 で割らない）', () => {
  const got = expectState(input(0, 1.0), 'ok', '0 / 1.0');
  assert.equal(got.ratio, 0);
});

test('D0051-AC-26: 判断は 1/1000 ドルの整数（costMilli・limitMilli）も持つ：0.42 / 1.0 は 420 と 1000', () => {
  const got = expectState(input(0.42, 1.0), 'ok', '0.42 / 1.0');
  assert.equal(got.costMilli, 420);
  assert.equal(got.limitMilli, 1000);
});

// ======== AC-27・28・29：近い・丸め・上限の前後 ========

for (const [cost, limit] of [
  [0.8, 1.0],
  [0.4, 0.5],
  [0.24, 0.3],
  [0.16, 0.2],
  [0.64, 0.8],
] as const) {
  test(`D0051-AC-27: 費用 ${cost} / 上限 ${limit}（上限の 8 割ちょうど）は「近い」`, () => {
    expectState(input(cost, limit), 'near', `${cost} / ${limit}`);
  });
}

test('D0051-AC-27: 素朴な割り算では 0.7999999999999999 になる 0.16 / 0.2 と 0.64 / 0.8 の割合は、0.8', () => {
  // 割り算の結果ではなく、1/1000 ドルの整数（160 / 200・640 / 800）で割る
  assert.equal(budgetOf(input(0.16, 0.2))?.ratio, 0.8);
  assert.equal(budgetOf(input(0.64, 0.8))?.ratio, 0.8);
});

test('D0051-AC-28: 0.799 / 1.0 は「余裕」（8 割に届かない）', () => {
  expectState(input(0.799, 1.0), 'ok', '0.799 / 1.0');
});

test('D0051-AC-28: 0.7996 / 1.0 は、1/1000 ドルに丸めると 0.800 になるので「近い」（表示 $0.80 / $1.00 と状態がそろう）', () => {
  expectState(input(0.7996, 1.0), 'near', '0.7996 / 1.0');
});

test('D0051-AC-29: 上限ちょうど（1.0 / 1.0）は「近い」', () => {
  expectState(input(1.0, 1.0), 'near', '1.0 / 1.0');
});

test('D0051-AC-29: 0.1 + 0.2 を費用、0.3 を上限にした実行は「近い」（浮動小数点の誤差で「超えた」にならない）', () => {
  const cost = 0.1 + 0.2;
  assert.notEqual(cost, 0.3, '前提：足し算の結果は 0.3 とずれる');
  expectState(input(cost, 0.3), 'near', `${cost} / 0.3`);
});

test('D0051-AC-29: 1.0004 / 1.0 は「近い」（1/1000 ドル未満の差は見ない）', () => {
  expectState(input(1.0004, 1.0), 'near', '1.0004 / 1.0');
});

for (const [cost, limit] of [
  [1.001, 1.0],
  [1.01, 1.0],
] as const) {
  test(`D0051-AC-29: ${cost} / ${limit} は「超えた」`, () => {
    expectState(input(cost, limit), 'over', `${cost} / ${limit}`);
  });
}

// ======== AC-30・31・32：止まった ========

for (const [cost, limit] of [
  [0.3, 1.0],
  [0.9, 1.0],
  [1.2, 1.0],
] as const) {
  test(`D0051-AC-30: subtype が error_max_budget_usd の実行は、費用が ${cost} / ${limit} でも「止まった」（割合は出せる）`, () => {
    const got = expectState(input(cost, limit, { subtype: STOP }), 'stopped', `${cost} / ${limit}`);
    assert.equal(got.ratio, cost / limit, '割合は費用 ÷ 上限');
  });
}

test('D0051-AC-31: 上限が記録に無い実行でも、subtype が error_max_budget_usd なら「止まった」（割合・金額は無い）', () => {
  const got = expectState(input(0.4, null, { subtype: STOP }), 'stopped', '上限なし 0.4');
  assert.equal(got.ratio, null);
  assert.equal(got.costMilli, null);
  assert.equal(got.limitMilli, null);
});

for (const [subtype, cost, limit, state] of [
  ['error_max_turns', 0.95, 1.0, 'near'],
  ['error_during_execution', 0.3, 1.0, 'ok'],
  ['error_max_buffer_size', 0.3, 1.0, 'ok'],
  ['success', 0.3, 1.0, 'ok'],
] as const) {
  test(`D0051-AC-32: 費用の上限以外の止まり方（${subtype}${subtype === 'success' ? '・is_error が真' : ''}）の ${cost} / ${limit} は、割合だけで「${state}」`, () => {
    // is_error が真かどうかは判断に使わない（budgetOfRun が受け取るのは費用・上限・印・結果の種類だけ）
    expectState(input(cost, limit, { subtype }), state, `${subtype} ${cost} / ${limit}`);
  });
}

// ======== AC-33・34：続きの会話の印のある実行 ========

for (const [cost, limit] of [
  [0.3, 1.0],
  [1.2, 1.0],
] as const) {
  test(`D0051-AC-33: 印のある実行が error_max_budget_usd なら、費用が ${cost} / ${limit} でも「止まった」（割合は無い）`, () => {
    const got = expectState(input(cost, limit, { resumed: true, subtype: STOP }), 'stopped', `${cost} / ${limit}`);
    assert.equal(got.ratio, null);
    assert.equal(got.costMilli, null);
    assert.equal(got.limitMilli, null);
  });
}

for (const [subtype, cost, limit, unmarked] of [
  ['success', 0.3, 1.0, 'ok'],
  ['success', 0.9, 1.0, 'near'],
  ['success', 1.2, 1.0, 'over'],
  ['error_max_turns', 0.95, 1.0, 'near'],
] as const) {
  test(`D0051-AC-34: 印のある実行（${subtype} の ${cost} / ${limit}）は状態を持たない。印が無ければ「${unmarked}」になる実行`, () => {
    // 対照：同じ実行でも印が無ければ状態を持つ（印が状態を消していることを確かめる）
    expectState(input(cost, limit, { subtype }), unmarked, `印なしの ${subtype} ${cost} / ${limit}`);
    assert.equal(budgetOf(input(cost, limit, { resumed: true, subtype })), null);
  });
}

// ======== 節に出す回の選び方（pickStageBudget）の準備 ========

/** 回の指定：[費用, 上限, 印・結果の種類]。seq は 1 から振る。 */
type Spec = readonly [number, number | null, { resumed?: boolean; subtype?: string }?];
function runsOf(...specs: Spec[]) {
  return specs.map(([costUsd, maxBudgetUsd, extra], i) =>
    plainRun({ seq: i + 1, costUsd, maxBudgetUsd, ...(extra?.resumed === undefined ? {} : { resumed: extra.resumed }), ...(extra?.subtype === undefined ? {} : { subtype: extra.subtype }) }),
  );
}
function picked(...specs: Spec[]): NodeBudget | null {
  return pickStageBudget(runsOf(...specs));
}

// ======== AC-35：N 回目 ========

test('D0051-AC-35: N 回目は runs[] に現れる順に 1 から数えた番号。上限の無い回・印のある回も数える（attempt が null の段でも）', () => {
  const runs = [
    budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.1 }), // 上限なし
    { stage: 'requirements', review: 'revise', feedback: '直して' }, // 確認は数えない
    budgetRun({ stage: 'requirements', seq: 2, costUsd: 0.5, maxBudgetUsd: 1.0, resumed: true }), // 印あり
    budgetRun({ stage: 'requirements', seq: 3, costUsd: 0.9, maxBudgetUsd: 1.0 }), // 近い
  ];
  const got = budgetOfNode(nodeById(budgetView(runs), 'requirements'));
  assert.equal(got?.state, 'near');
  assert.equal(got?.nth, 3);
  assert.equal(got?.runCount, 3);
});

test('D0051-AC-35: N 回目に attempt は使わない（attempt が 2・2・9 でも、3 回目は 3 回目）', () => {
  const runs = [
    budgetRun({ stage: 'implement', seq: 1, attempt: 2, costUsd: 0.1 }),
    budgetRun({ stage: 'implement', seq: 2, attempt: 2, costUsd: 0.2, maxBudgetUsd: 1.0 }),
    budgetRun({ stage: 'implement', seq: 3, attempt: 9, costUsd: 0.9, maxBudgetUsd: 1.0 }),
  ];
  const got = budgetOfNode(nodeById(budgetView(runs), 'implement'));
  assert.equal(got?.state, 'near');
  assert.equal(got?.nth, 3);
  assert.equal(got?.runCount, 3);
});

test('D0051-AC-35: N 回目は同じ段の実行だけを数える（ほかの段の実行は数えない）', () => {
  const runs = [
    budgetRun({ stage: 'design', seq: 1, costUsd: 0.3 }),
    budgetRun({ stage: 'requirements', seq: 2, costUsd: 0.9, maxBudgetUsd: 1.0 }),
  ];
  const got = budgetOfNode(nodeById(budgetView(runs), 'requirements'));
  assert.equal(got?.nth, 1);
  assert.equal(got?.runCount, 1);
});

// ======== AC-36〜38：状態の重い回・割合の高い回・後の回 ========

test('D0051-AC-36: 1回目 0.9 / 1.0（近い）・2回目 0.4 / 1.0（余裕）なら、1回目を選ぶ', () => {
  const got = picked([0.9, 1.0], [0.4, 1.0]);
  assert.equal(got?.nth, 1);
  assert.equal(got?.state, 'near');
  assert.equal(got?.runCount, 2);
});

test('D0051-AC-36: 近い（1回目 0.9 / 1.0）と超えた（2回目 1.2 / 1.0）なら、2回目を選ぶ', () => {
  const got = picked([0.9, 1.0], [1.2, 1.0]);
  assert.equal(got?.nth, 2);
  assert.equal(got?.state, 'over');
});

test('D0051-AC-36: 止まった（1回目）と超えた（2回目）なら、止まった（1回目）を選ぶ', () => {
  const got = picked([0.5, 1.0, { subtype: STOP }], [1.2, 1.0]);
  assert.equal(got?.nth, 1);
  assert.equal(got?.state, 'stopped');
});

test('D0051-AC-36: 超えた（1回目）と止まった（2回目）なら、止まった（2回目）を選ぶ', () => {
  const got = picked([1.2, 1.0], [0.5, 1.0, { subtype: STOP }]);
  assert.equal(got?.nth, 2);
  assert.equal(got?.state, 'stopped');
});

test('D0051-AC-37: 状態が同じなら、割合の高い回を選ぶ（後の回ではない）：1回目 0.5 / 0.5（割合 1.0）・2回目 0.9 / 1.0（割合 0.9）は 1回目', () => {
  const got = picked([0.5, 0.5], [0.9, 1.0]);
  assert.equal(got?.state, 'near');
  assert.equal(got?.nth, 1);
  assert.equal(got?.ratio, 1);
});

test('D0051-AC-38: 状態も割合も同じなら、後の回を選ぶ：1回目 0.5 / 1.0・2回目 0.25 / 0.5（どちらも割合 0.5・余裕）は 2回目', () => {
  const got = picked([0.5, 1.0], [0.25, 0.5]);
  assert.equal(got?.state, 'ok');
  assert.equal(got?.nth, 2);
});

// ======== AC-39・40：回ごとの上限・上限の無い回 ========

test('D0051-AC-39: 回ごとの上限で決める：0.4 / 0.5 の実行はどれも「近い」', () => {
  expectState(input(0.4, 0.5), 'near', '0.4 / 0.5');
});

test('D0051-AC-39: 段の合計の費用とは比べない：0.4 / 0.5 の回が 2 回（合計 0.8 は上限 0.5 より大きい）でも、選ぶ回は「近い」で「超えた」にならない', () => {
  const got = picked([0.4, 0.5], [0.4, 0.5]);
  assert.equal(got?.state, 'near');
  assert.equal(got?.nth, 2, '同じ状態・同じ割合なら後の回');
  assert.equal(got?.runCount, 2);
});

test('D0051-AC-40: 上限の無い回は選び方に入らない：1回目 上限なし（費用 0.9）・2回目 0.2 / 1.0 なら、2回目（余裕）', () => {
  const got = picked([0.9, null], [0.2, 1.0]);
  assert.equal(got?.nth, 2);
  assert.equal(got?.state, 'ok');
  assert.equal(got?.runCount, 2, '上限の無い回も回数には入る');
});

// ======== AC-41・42：上限なしの止まった回 ========

test('D0051-AC-41: 上限なしの止まった回（1回目）が、上限ありの近い回（2回目 0.9 / 1.0）に勝つ。金額は持たない（言葉だけを出す元）', () => {
  const got = picked([0.4, null, { subtype: STOP }], [0.9, 1.0]);
  assert.equal(got?.state, 'stopped');
  assert.equal(got?.nth, 1);
  assert.equal(got?.ratio, null);
  assert.equal(got?.costMilli, null);
  assert.equal(got?.limitMilli, null);
});

test('D0051-AC-41: 近い回（1回目）のあとの上限なしの止まった回（2回目）でも、止まった回（2回目）を選ぶ', () => {
  const got = picked([0.9, 1.0], [0.4, null, { subtype: STOP }]);
  assert.equal(got?.state, 'stopped');
  assert.equal(got?.nth, 2);
  assert.equal(got?.ratio, null);
});

test('D0051-AC-42: 止まった回が複数あれば、割合のある回を選ぶ：上限なしの止まった回（1回目）と割合のある止まった回（2回目）は 2回目', () => {
  const got = picked([0.4, null, { subtype: STOP }], [1.02, 1.0, { subtype: STOP }]);
  assert.equal(got?.state, 'stopped');
  assert.equal(got?.nth, 2);
  assert.notEqual(got?.ratio, null);
});

test('D0051-AC-42: 割合のある止まった回（1回目）と上限なしの止まった回（2回目）なら、後の回ではなく割合のある 1回目を選ぶ', () => {
  const got = picked([1.02, 1.0, { subtype: STOP }], [0.4, null, { subtype: STOP }]);
  assert.equal(got?.state, 'stopped');
  assert.equal(got?.nth, 1);
  assert.notEqual(got?.ratio, null);
});

// ======== AC-43・44・45：状態を持つ回が無いとき・印のある回 ========

test('D0051-AC-43: （a）印の無い回だけで、どれも上限が無く止まってもいない（0.9 と 0.2）なら、節は「上限なし」(null)', () => {
  // 対照：上限のある回が 1 つ加われば、節に出す回が決まる（空の形の null と区別するため）
  assert.equal(picked([0.9, null], [0.2, null], [0.3, 1.0])?.nth, 3);
  assert.equal(picked([0.9, null], [0.2, null]), null);
});

test('D0051-AC-43: （b）印のある回だけで、止まっていない（success の 1.2 / 1.0）なら、節は「上限なし」(null)', () => {
  assert.equal(picked([1.2, 1.0])?.state, 'over', '対照：印が無ければ超えた');
  assert.equal(picked([1.2, 1.0, { resumed: true }]), null);
});

test('D0051-AC-43: （c）上限の無い印の無い回（0.9）と、印のある止まっていない回（0.3 / 1.0）なら、節は「上限なし」(null)', () => {
  assert.equal(picked([0.9, null], [0.3, 1.0])?.nth, 2, '対照：印が無ければ 2回目の余裕');
  assert.equal(picked([0.9, null], [0.3, 1.0, { resumed: true }]), null);
});

test('D0051-AC-44: 印のある止まっていない回は選び方に入らない：1回目 0.9 / 1.0（近い）・2回目 印あり success 1.2 / 1.0 なら、1回目（近い）。2回目の「超えた」にならない', () => {
  const got = picked([0.9, 1.0], [1.2, 1.0, { resumed: true }]);
  assert.equal(got?.state, 'near');
  assert.equal(got?.nth, 1);
  assert.equal(got?.runCount, 2);
});

test('D0051-AC-45: 印のある止まった回は選び方に入る：1回目 0.4 / 1.0（余裕）・2回目 印あり・止まった なら、2回目（止まった。割合は無い）', () => {
  const got = picked([0.4, 1.0], [0.9, 1.0, { resumed: true, subtype: STOP }]);
  assert.equal(got?.state, 'stopped');
  assert.equal(got?.nth, 2);
  assert.equal(got?.ratio, null);
  assert.equal(got?.costMilli, null);
});

// ======== AC-58：動いている段の節は budget が null ========

test('D0051-AC-58: 動いている段の節の budget は null（前の回の上限と状態があっても）。動いていなければ同じ記録で「近い」を持つ', () => {
  const runs = [budgetRun({ stage: 'design', seq: 1, costUsd: 0.9, maxBudgetUsd: 1.0 })];
  const idle = budgetView(runs, { clock: clockAt(100) });
  assert.equal(budgetOfNode(nodeById(idle, 'design'))?.state, 'near', '対照：動いていない段の節は前の回の状態を持つ');
  const running = budgetView(runs, { stageLogs: [runningLogFile(2, 'design', 2)], clock: clockAt(100) });
  assert.equal(running.runningStage, 'design', '前提：設計が動いている');
  assert.equal(nodeById(running, 'design').status, 'running');
  assert.equal(budgetOfNode(nodeById(running, 'design')), null);
});
