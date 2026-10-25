// 確認待ちの知らせの文（D0046）。vscode を使わない。外から来た文字（セッション名・段）は plainLine で整える。
import type { RunRow } from '../domain/runList.ts';
import { plainLine } from './statusBar.ts';

/** 知らせに付けるボタンの文字。押すと既存のコマンド pipe-in.showRun と同じ動きになる */
export const SHOW_RUN_LABEL = '実行を見る';

/** 1件は「<セッション名>（<段>）が確認待ちです」、2件以上は件数だけ（名前は並べない）、0件は null。 */
export function waitingNoticeText(rows: readonly Pick<RunRow, 'session' | 'stage'>[]): string | null {
  const first = rows[0];
  if (first === undefined) return null;
  if (rows.length === 1) return `${plainLine(first.session)}（${plainLine(first.stage)}）が確認待ちです`;
  return `確認待ちの実行が ${rows.length} 件になりました`;
}
