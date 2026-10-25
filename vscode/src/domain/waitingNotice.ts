// 新しく確認待ちになった行の判断（D0044）。vscode を使わない純粋な関数。
import type { RunRow } from './runList.ts';
import type { RunKey } from './runs.ts';

/**
 * 前の一覧の行と今の一覧の行から、新しく確認待ちになった行の key を返す（今の一覧の並び順・重複なし）。
 * 「前は確認待ちでなかった」と「前の一覧に無かった」は同じ扱い。
 * prev が null（基準が無い）なら空。archive/ の行（previous）と終わった行（done）は返さない。
 */
export function newlyWaitingKeys(prev: readonly RunRow[] | null, next: readonly RunRow[]): RunKey[] {
  if (prev === null) return [];
  const before = new Set<RunKey>();
  for (const row of prev) if (row.state === 'waiting') before.add(row.key);
  const out: RunKey[] = [];
  for (const row of next) {
    if (row.state !== 'waiting' || row.previous || before.has(row.key) || out.includes(row.key)) continue;
    out.push(row.key);
  }
  return out;
}
