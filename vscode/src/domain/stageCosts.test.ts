// 段ごとの費用の表の元（D0051 の AC-63〜65・67）：段ごとに費用を合算し、費用の多い順に並べ、全体に占める割合（四捨五入した整数 %）を付ける。
// 費用は 1/10000 ドルの整数にそろえて足す（図の節の metrics.costUsd と同じ式なので、行の費用は節の合計と必ず同じ）。
// 赤の理由は「まだ決めていない」：空の形の buildStageCosts は null を返し、図の状態に stageCosts は無い（undefined）。
// 期待が null のテスト（AC-67）は、空の形の null と区別できないので、費用のある記録なら表が決まる対照を先に確かめる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildStageCosts } from './stageCosts.ts';
import type { StageCostRow, StageCostsView } from './stageCosts.ts';
import type { PipelineView } from './pipelineView.ts';
import { STAGES, STAGE_LABELS } from './stage.ts';
import { budgetRun, budgetView, pipeStages, plainRun } from '../test/budgetFixtures.ts';

const ORDER = STAGES;
const costs = (runs: ReturnType<typeof plainRun>[], order: readonly string[] = ORDER, labels: Readonly<Record<string, string>> = STAGE_LABELS): StageCostsView | null =>
  buildStageCosts(runs, order, labels);
/** 行を段の名前で取る。無ければ落とす。 */
function rowOf(view: StageCostsView | null, stage: string): StageCostRow {
  assert.ok(view !== null && view !== undefined, '表が決まっている');
  const row = view.rows.find((r) => r.stage === stage);
  assert.ok(row !== undefined, `${stage} の行がある`);
  return row;
}
const stagesOf = (view: StageCostsView | null): string[] | undefined => view?.rows.map((r) => r.stage);
/** 図の状態の stageCosts（型に入るまでは、型に頼らず読む） */
const stageCostsOf = (view: PipelineView): StageCostsView | null | undefined => (view as unknown as { stageCosts?: StageCostsView | null }).stageCosts;

// ======== AC-63：行は段ごと。同じ段の複数回は合算して 1 行 ========

test('D0051-AC-63: 同じ段の複数回は合算して 1 行（実装 0.3 + 0.2 = 0.5・2 回）。1 回の段は 1 回', () => {
  const view = costs([plainRun({ stage: 'requirements', seq: 1, costUsd: 0.4 }), plainRun({ stage: 'implement', seq: 2, costUsd: 0.3 }), plainRun({ stage: 'implement', seq: 3, costUsd: 0.2 })]);
  assert.equal(view?.rows.length, 2);
  assert.equal(rowOf(view, 'implement').costUsd, 0.5);
  assert.equal(rowOf(view, 'implement').runs, 2);
  assert.equal(rowOf(view, 'requirements').costUsd, 0.4);
  assert.equal(rowOf(view, 'requirements').runs, 1);
});

test('D0051-AC-63: 行には段の表示の名前（labels）が入る', () => {
  const view = costs([plainRun({ stage: 'design', seq: 1, costUsd: 0.4 })]);
  assert.equal(rowOf(view, 'design').label, '設計');
});

test('D0051-AC-63: パイプの記録の段の並びと表示の名前（record.stages）で行を作る', () => {
  const runs = [
    budgetRun({ stage: 'draw', seq: 1, costUsd: 0.2 }),
    budgetRun({ stage: 'survey', seq: 2, costUsd: 0.2 }),
    budgetRun({ stage: 'survey', seq: 3, costUsd: 0.1 }),
  ];
  const view = stageCostsOf(
    budgetView(runs, { pipe: 'diagrams', stages: [{ name: 'survey', label: '調査', output: 's.md', review: false }, { name: 'draw', label: '図を描く', output: 'd.md', review: false }] }),
  );
  assert.deepEqual(
    view?.rows.map((r) => [r.stage, r.label, r.costUsd, r.runs]),
    [
      ['survey', '調査', 0.3, 2],
      ['draw', '図を描く', 0.2, 1],
    ],
  );
});

// ======== AC-64：費用の多い順（同額は段の並びの順） ========

test('D0051-AC-64: 段の並びが（0.396 の段、0.404 の段、0.2 の段）のとき、表は 0.404 の段・0.396 の段・0.2 の段の順（四捨五入した 40%・40%・20% では並べない）', () => {
  const view = costs([
    plainRun({ stage: 'requirements', seq: 1, costUsd: 0.396 }),
    plainRun({ stage: 'design', seq: 2, costUsd: 0.404 }),
    plainRun({ stage: 'red', seq: 3, costUsd: 0.2 }),
  ]);
  assert.deepEqual(stagesOf(view), ['design', 'requirements', 'red']);
  assert.deepEqual(view?.rows.map((r) => r.percent), [40, 40, 20]);
});

test('D0051-AC-64: 同額のときだけ段の並びの順：requirements 0.3・design 0.3・red 0.4 は red・requirements・design', () => {
  const view = costs([
    plainRun({ stage: 'requirements', seq: 1, costUsd: 0.3 }),
    plainRun({ stage: 'design', seq: 2, costUsd: 0.3 }),
    plainRun({ stage: 'red', seq: 3, costUsd: 0.4 }),
  ]);
  assert.deepEqual(stagesOf(view), ['red', 'requirements', 'design']);
});

test('D0051-AC-64: 記録に現れる順ではなく、段の並び（order）の順で同額を並べる：実行が test → design の順でも、同額なら design が先', () => {
  const view = costs([plainRun({ stage: 'test', seq: 1, costUsd: 0.5 }), plainRun({ stage: 'design', seq: 2, costUsd: 0.5 })]);
  assert.deepEqual(stagesOf(view), ['design', 'test']);
});

test('D0051-AC-64: パイプの記録では、record.stages の並びが同額のときの順になる', () => {
  const runs = [budgetRun({ stage: 'b', seq: 1, costUsd: 0.5 }), budgetRun({ stage: 'a', seq: 2, costUsd: 0.5 }), budgetRun({ stage: 'c', seq: 3, costUsd: 0.6 })];
  const view = stageCostsOf(budgetView(runs, { pipe: 'p', stages: pipeStages(['a', 'b', 'c']) }));
  assert.deepEqual(stagesOf(view ?? null), ['c', 'a', 'b']);
});

// ======== AC-65：割合は費用 ÷ 全段の合計の四捨五入した整数 % ========

test('D0051-AC-65: 合計が 1.0 のとき、0.125 の段は 13%、0.001 の段は 0%', () => {
  const view = costs([
    plainRun({ stage: 'requirements', seq: 1, costUsd: 0.125 }),
    plainRun({ stage: 'design', seq: 2, costUsd: 0.001 }),
    plainRun({ stage: 'red', seq: 3, costUsd: 0.874 }),
  ]);
  assert.equal(view?.totalUsd, 1);
  assert.equal(rowOf(view, 'requirements').percent, 13);
  assert.equal(rowOf(view, 'design').percent, 0);
  assert.equal(rowOf(view, 'red').percent, 87);
});

test('D0051-AC-65: 同額の 3 段は 33%・33%・33%（合計を 100% に合わせる補正はしない）', () => {
  const view = costs([
    plainRun({ stage: 'requirements', seq: 1, costUsd: 0.1 }),
    plainRun({ stage: 'design', seq: 2, costUsd: 0.1 }),
    plainRun({ stage: 'red', seq: 3, costUsd: 0.1 }),
  ]);
  assert.deepEqual(view?.rows.map((r) => r.percent), [33, 33, 33]);
});

test('D0051-AC-65: 合計 totalUsd は行の費用の合計（0.404 + 0.396 + 0.2 = 1）', () => {
  const view = costs([
    plainRun({ stage: 'requirements', seq: 1, costUsd: 0.396 }),
    plainRun({ stage: 'design', seq: 2, costUsd: 0.404 }),
    plainRun({ stage: 'red', seq: 3, costUsd: 0.2 }),
  ]);
  assert.equal(view?.totalUsd, 1);
});

// ======== AC-67：行の費用は節の合計と同じ。費用 0 の段は行に出ない。全部 0・記録なしは null ========

test('D0051-AC-67: 行の費用は、図の節の metrics.costUsd（全部の回の合計を 4 桁に丸めた値）と同じ', () => {
  const runs = [
    budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.1 }),
    budgetRun({ stage: 'requirements', seq: 2, costUsd: 0.2 }), // 0.1 + 0.2 = 0.30000000000000004
    budgetRun({ stage: 'design', seq: 3, costUsd: 1.70599 }),
    budgetRun({ stage: 'implement', seq: 4, attempt: 1, costUsd: 0.33333 }),
    budgetRun({ stage: 'implement', seq: 5, attempt: 2, costUsd: 0.33333 }),
  ];
  const view = budgetView(runs);
  const table = stageCostsOf(view);
  assert.ok(table !== null && table !== undefined, '表が決まっている');
  const byNode = view.nodes.filter((n) => n.metrics !== null).map((n) => [n.id, n.metrics?.costUsd] as const);
  assert.equal(byNode.length, 3, '前提：費用のある節は 3 つ');
  for (const [id, cost] of byNode) {
    assert.equal(rowOf(table, id).costUsd, cost, `${id} の行の費用は節の合計と同じ`);
  }
});

test('D0051-AC-67: 費用が 0 の段（まだ流れていない・1/10000 ドルに満たない）は行に出ない', () => {
  const view = costs([
    plainRun({ stage: 'requirements', seq: 1, costUsd: 0 }),
    plainRun({ stage: 'design', seq: 2, costUsd: 0.5 }),
    plainRun({ stage: 'red', seq: 3, costUsd: 0.00004 }),
  ]);
  assert.deepEqual(stagesOf(view), ['design']);
  assert.equal(view?.rows[0]?.percent, 100);
});

test('D0051-AC-67: 全部の段が 0、または実行が無い記録は null（表そのものを出さない）', () => {
  // 対照：費用のある実行が 1 つあれば表は決まる（空の形の null と区別するため）
  assert.notEqual(costs([plainRun({ stage: 'design', seq: 1, costUsd: 0.5 })]), null);
  assert.equal(costs([]), null);
  assert.equal(costs([plainRun({ stage: 'requirements', seq: 1, costUsd: 0 }), plainRun({ stage: 'design', seq: 2, costUsd: 0 })]), null);
});

test('D0051-AC-67: 段の並び（order）に無い段の実行は、行にも合計にも入らない', () => {
  const view = costs([plainRun({ stage: 'ghost', seq: 1, costUsd: 9 }), plainRun({ stage: 'design', seq: 2, costUsd: 0.5 })]);
  assert.deepEqual(stagesOf(view), ['design']);
  assert.equal(view?.totalUsd, 0.5);
  assert.equal(view?.rows[0]?.percent, 100);
});

test('D0051-AC-67: buildPipelineView の stageCosts は、記録の費用のない開発フローでは null、費用のある開発フローでは表を持つ', () => {
  assert.equal(stageCostsOf(budgetView([budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.5 })]))?.rows.length, 1, '対照：費用があれば表を持つ');
  assert.equal(stageCostsOf(budgetView([budgetRun({ stage: 'requirements', seq: 1, costUsd: 0 })])), null);
  assert.equal(stageCostsOf(budgetView([])), null);
});
