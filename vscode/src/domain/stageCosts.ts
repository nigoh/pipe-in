// 段ごとの費用の表の元（D0051）。純粋な関数だけ。
import type { StageRun } from './runRecord.ts';
import type { Stage } from './stage.ts';

export interface StageCostRow { stage: Stage; label: string; costUsd: number; runs: number; percent: number }
export interface StageCostsView { rows: StageCostRow[]; totalUsd: number }

/** 段ごとの費用の表。費用の多い順（同額は order の順）。費用が 0 の段は行にしない。行が 0 個なら null。 */
export function buildStageCosts(runs: readonly StageRun[], order: readonly Stage[], labels: Readonly<Record<Stage, string>>): StageCostsView | null {
  const rows: { stage: Stage; units: number; runs: number }[] = [];
  for (const stage of order) {
    const mine = runs.filter((r) => r.stage === stage);
    // 図の節の metrics.costUsd と同じ式（1/10000 ドルの整数）。行と節の合計は必ず同じになる
    const units = Math.round(mine.reduce((sum, r) => sum + r.costUsd, 0) * 1e4);
    if (units > 0) rows.push({ stage, units, runs: mine.length });
  }
  if (rows.length === 0) return null;
  // Array.prototype.sort は安定なので、同額は order の順のまま残る
  rows.sort((a, b) => b.units - a.units);
  const totalUnits = rows.reduce((sum, r) => sum + r.units, 0);
  return {
    rows: rows.map((r) => ({
      stage: r.stage,
      label: labels[r.stage],
      costUsd: r.units / 1e4,
      runs: r.runs,
      percent: Math.round((r.units * 100) / totalUnits),
    })),
    totalUsd: totalUnits / 1e4,
  };
}
