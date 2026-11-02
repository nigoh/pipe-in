// 作業台に渡す「今日」と「前の実績」の選び方（D0066）。純粋な関数（今の時刻は引数 nowMs。時計を読むのは extension.ts だけ）。
// 実績は、既に読んだ実行の一覧（RunList）の写しから選ぶだけ。新しく読まない・書かない。
import type { RunList } from './runList.ts';

export interface EstimateContext {
  /** 今日（UTC の日付 YYYY-MM-DD）。単価表の古さを見るのに使う */
  today: string;
  /** ここで動いたパイプの前の実績（ドル）。無い・読めないときは null */
  actualUsd: number | null;
}

/** ここで動いた（別の worktree でも前の実行でもない）、同じ名前のパイプの行のうち、更新が新しいものの実績。 */
export function estimateContext(list: RunList | null, pipeName: string, nowMs: number): EstimateContext {
  let best: { updatedMs: number; costUsd: number | null } | null = null;
  for (const { row } of list?.entries ?? []) {
    if (row.other || row.previous || row.pipe !== pipeName) continue;
    const updatedMs = row.updatedMs ?? -Infinity;
    if (best === null || updatedMs > best.updatedMs) best = { updatedMs, costUsd: row.costUsd ?? null };
  }
  return { today: new Date(nowMs).toISOString().slice(0, 10), actualUsd: best?.costUsd ?? null };
}
