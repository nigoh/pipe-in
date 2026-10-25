// 知らせの対象の行の絞り込みと、設定の値の読み（D0044）。vscode を使わない純粋な関数。
import { newlyWaitingKeys } from '../domain/waitingNotice.ts';
import type { RunRow } from '../domain/runList.ts';
import type { RunKey } from '../domain/runs.ts';

export interface NoticeInput {
  /** 前の一覧の行。基準が無ければ null */
  prev: readonly RunRow[] | null;
  rows: readonly RunRow[];
  /** 選んでいる実行の目印 */
  selected: RunKey;
  /** パネルが見えているか */
  panelVisible: boolean;
  /** 設定 pipe-in.notifyWhenWaiting（notifyEnabled を通したもの） */
  enabled: boolean;
}

/** 知らせの対象の行。設定が false なら空。パネルが見えていて選んでいる実行と同じ行は、もう見えているので外す。 */
export function planWaitingNotice(input: NoticeInput): RunRow[] {
  if (!input.enabled) return [];
  const fresh = new Set<RunKey>(newlyWaitingKeys(input.prev, input.rows));
  return input.rows.filter((row, i) => {
    if (!fresh.has(row.key)) return false;
    if (input.rows.findIndex((r) => r.key === row.key) !== i) return false;
    return !(input.panelVisible && row.key === input.selected);
  });
}

/** 設定の値 → 出すか。false のときだけ false。未設定・型違い・null は既定の true。 */
export function notifyEnabled(value: unknown): boolean {
  return value !== false;
}
