// 段の費用を上限と比べる（D0051）。純粋な関数だけ（時計・ファイルに触れない）。
import type { StageRun } from './runRecord.ts';

/** 「近い」の境目（上限の何 % 以上か）。しきい値はここの 1 か所だけ */
export const NEAR_BUDGET_PERCENT = 80;
/** 費用の上限で SDK が止めたときの結果の種類 */
export const BUDGET_STOP_SUBTYPE = 'error_max_budget_usd';

/** 余裕・近い・超えた・止まった */
export type BudgetState = 'ok' | 'near' | 'over' | 'stopped';
/** 1 回の実行の判断。割合を出せない「止まった」だけ ratio・costMilli・limitMilli が null */
export interface RunBudget { state: BudgetState; ratio: number | null; costMilli: number | null; limitMilli: number | null }
/** 節に出す回。nth は runs[] に現れる順の 1 から数えた番号（上限の無い回・印のある回も数える）、runCount はその段の実行の数 */
export interface NodeBudget extends RunBudget { nth: number; runCount: number }

/** ドルを 1/1000 ドルの整数にする（比べるときの浮動小数点の誤差を避ける） */
export function toMilli(usd: number): number {
  return Math.round(usd * 1000);
}

/** 1 回の実行の判断。状態を持たない回（続きの会話で止まっていない・上限なしで止まっていない）は null。 */
export function budgetOfRun(run: Pick<StageRun, 'costUsd' | 'maxBudgetUsd' | 'resumed' | 'subtype'>): RunBudget | null {
  const stopped = run.subtype === BUDGET_STOP_SUBTYPE;
  const stoppedOnly: RunBudget = { state: 'stopped', ratio: null, costMilli: null, limitMilli: null };
  // 続きの会話の回は費用が前の回からの累計（Claude Code v2.1.277 以降の動き。公式の文書 cost-tracking）なので、割合も余裕・近い・超えたも決めない
  if (run.resumed) return stopped ? stoppedOnly : null;
  if (run.maxBudgetUsd === null) return stopped ? stoppedOnly : null;
  const costMilli = toMilli(run.costUsd);
  const limitMilli = toMilli(run.maxBudgetUsd);
  const ratio = costMilli / limitMilli;
  let state: BudgetState;
  if (stopped) state = 'stopped';
  else if (costMilli > limitMilli) state = 'over';
  else if (costMilli * 100 >= limitMilli * NEAR_BUDGET_PERCENT) state = 'near';
  else state = 'ok';
  return { state, ratio, costMilli, limitMilli };
}

const WEIGHT: Readonly<Record<BudgetState, number>> = { ok: 0, near: 1, over: 2, stopped: 3 };

/** 節に出す回を選ぶ。状態が重い回、同じなら割合の高い回（null は最も低い）、同じなら後の回。候補が無ければ null。 */
export function pickStageBudget(runs: readonly StageRun[]): NodeBudget | null {
  let best: NodeBudget | null = null;
  runs.forEach((run, i) => {
    const b = budgetOfRun(run);
    if (b === null) return;
    const cand: NodeBudget = { ...b, nth: i + 1, runCount: runs.length };
    if (best === null || beats(cand, best)) best = cand;
  });
  return best;
}

/** cand が best より選ばれるか（同じなら後の回が勝つので、等しいときも true） */
function beats(cand: RunBudget, best: RunBudget): boolean {
  if (WEIGHT[cand.state] !== WEIGHT[best.state]) return WEIGHT[cand.state] > WEIGHT[best.state];
  return (cand.ratio ?? -1) >= (best.ratio ?? -1);
}
