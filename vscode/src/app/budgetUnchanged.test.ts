// 状態バー・実行の一覧の行・確認待ちの知らせは、上限の話を出さず今までどおり（D0051 の AC-108）。
// 上限・続きの会話の印・止まった実行（subtype が error_max_budget_usd）を持つ記録から作った出力は、
// 同じ記録から上限・印・subtype を除いたものから作った出力と等しい。図の節の色と言葉だけで見せる（Q-4）。
// 3 つの出力の元は、状態バーの文字とツールチップ（statusBarLabel）・実行の一覧の行（summarizeRun）・確認待ちの知らせの対象（planWaitingNotice）。
// 今の作りで通り、実装のあとも通り続けることを見張る（守る）。比べる 2 つが同じになるのが当たり前に見えないよう、
// 上限の鍵が実際に記録に入っていることと、比べる検査が違いを見つけることを、それぞれ確かめる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { planWaitingNotice } from './notifyWaiting.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { summarizeRun } from '../domain/runList.ts';
import type { RunRow } from '../domain/runList.ts';
import { HERE, makeRunKey } from '../domain/runs.ts';
import { statusBarLabel } from '../view/statusBar.ts';
import type { BudgetViewOptions } from '../test/budgetFixtures.ts';
import { budgetRun, budgetSnapshot, runningLogFile, withoutBudgetKeys } from '../test/budgetFixtures.ts';
import { BASE_AT, clockAt } from '../test/liveFixtures.ts';

const STOP = 'error_max_budget_usd';
const CLOCK = clockAt(100);
const KEY = makeRunKey(HERE, '');
const OTHER_KEY = makeRunKey(HERE, 'other');

/** 上限・続きの会話の印・止まった実行を一通り持つ実行の並び（余裕・続きの会話・超えた・止まった）。 */
const ALL_RUNS = [
  budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.2, maxBudgetUsd: 1.0 }),
  budgetRun({ stage: 'requirements', seq: 2, costUsd: 0.9, maxBudgetUsd: 1.0, resumed: true }),
  budgetRun({ stage: 'design', seq: 3, costUsd: 1.2, maxBudgetUsd: 1.0 }),
  budgetRun({ stage: 'red', seq: 4, costUsd: 1.02, maxBudgetUsd: 1.0, subtype: STOP, isError: true }),
];
const EARLY_RUNS = ALL_RUNS.slice(0, 2);

interface Scenario {
  name: string;
  runs: readonly object[];
  opts: BudgetViewOptions;
}
const SCENARIOS: readonly Scenario[] = [
  { name: '終わった（止まった段がある）', runs: ALL_RUNS, opts: { final: 'STAGE_ERROR', totalCostUsd: 3.32 } },
  {
    name: '確認待ち',
    runs: EARLY_RUNS,
    opts: { totalCostUsd: 1.1, pendingReview: { stage: 'requirements', doc: 'docs/pipeline/01_requirements.md', session_id: 's', since: BASE_AT } },
  },
  { name: '動いている', runs: EARLY_RUNS, opts: { totalCostUsd: 1.1, stageLogs: [runningLogFile(3, 'design', null)] } },
];

/** 同じ記録（strip なら上限・印・subtype を除いたもの）から作る、3 つの出力の元。 */
function build(s: Scenario, strip: boolean, key = KEY) {
  const runs = strip ? s.runs.map(withoutBudgetKeys) : s.runs;
  const snap = budgetSnapshot(runs, s.opts);
  const view = buildPipelineView(snap, CLOCK);
  const row: RunRow = summarizeRun(
    { key, id: key === KEY ? '' : 'other', branch: null, other: false, memoHead: null, previous: false, stateJson: snap.stateJson, stageLogs: snap.stageLogs },
    CLOCK,
  );
  return { snap, view, row };
}

test('D0051-AC-108: （前提）比べる記録には、上限・続きの会話の印・止まった実行の鍵が入っていて、除いた記録には入っていない。今のまま通る。守る', () => {
  const withKeys = build(SCENARIOS[0]!, false).snap.stateJson!;
  const without = build(SCENARIOS[0]!, true).snap.stateJson!;
  for (const word of ['"max_budget_usd"', '"resumed":true', `"subtype":"${STOP}"`]) {
    assert.ok(withKeys.includes(word), `上限つきの記録に ${word} が入っている`);
    assert.ok(!without.includes(word), `除いた記録に ${word} が入っていない`);
  }
});

for (const s of SCENARIOS) {
  test(`D0051-AC-108: 状態バーの文字とツールチップ（${s.name}）は、上限・印・subtype を除いた同じ記録のものと等しい。今のまま通る。守る`, () => {
    assert.deepEqual(statusBarLabel(build(s, false).view), statusBarLabel(build(s, true).view));
  });

  test(`D0051-AC-108: 実行の一覧の行（${s.name}）は、上限・印・subtype を除いた同じ記録のものと等しい。今のまま通る。守る`, () => {
    assert.deepEqual(build(s, false).row, build(s, true).row);
  });
}

test('D0051-AC-108: 件数の形の状態バー（別の確認待ちの実行がある）も、上限・印・subtype を除いた同じ記録のものと等しい。今のまま通る。守る', () => {
  const waiting = SCENARIOS[1]!;
  const label = (strip: boolean) => {
    const here = build(SCENARIOS[0]!, strip);
    const other = build(waiting, strip, OTHER_KEY);
    return statusBarLabel(here.view, { rows: [here.row, other.row], selected: KEY, omittedWorktrees: 0 });
  };
  const withKeys = label(false);
  assert.match(withKeys.text, /確認待ち/, '前提：件数の形になっている');
  assert.deepEqual(withKeys, label(true));
});

test('D0051-AC-108: 確認待ちの知らせの対象の行は、上限・印・subtype を除いた同じ記録のものと等しい。今のまま通る。守る', () => {
  const notice = (strip: boolean): RunRow[] => {
    const before = build(SCENARIOS[2]!, strip, OTHER_KEY).row; // 動いている
    const after = build(SCENARIOS[1]!, strip, OTHER_KEY).row; // 確認待ち（同じ行が動き → 確認待ちに変わった）
    return planWaitingNotice({ prev: [before], rows: [after], selected: KEY, panelVisible: true, enabled: true });
  };
  const withKeys = notice(false);
  assert.equal(withKeys.length, 1, '前提：新しく確認待ちになった行が知らせの対象になる');
  assert.deepEqual(withKeys, notice(true));
});

test('D0051-AC-108: 検査そのもの：費用の合計が違う記録からは、状態バー・実行の一覧の行が違う出力になる（比べる検査は違いを見つける）。今のまま通る。守る', () => {
  const s = SCENARIOS[0]!;
  const richer: Scenario = { ...s, opts: { ...s.opts, totalCostUsd: 9.99 } };
  assert.notDeepEqual(statusBarLabel(build(s, false).view), statusBarLabel(build(richer, false).view));
  assert.notDeepEqual(build(s, false).row, build(richer, false).row);
});
