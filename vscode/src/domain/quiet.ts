// 最後の更新からの秒（D0021）：段のログの更新時刻（mtime）と「今」から、止まっているかもしれない印の元を決める。
// 純粋（時計・ファイル・vscode に触れない）。「今」は引数で受ける。
import { MAX_SPAN_SEC, elapsedSec } from './timestamp.ts';

/** 更新時刻（UTC のミリ秒）として読める値だけ通す。有限で 0 より大きい数。ほかは null（例外は投げない）。 */
export function validMtime(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null;
}

/** 読める更新時刻のうち最新（最大）のもの。読めるものが無ければ null。渡された配列は書き換えない。 */
export function latestMtime(times: readonly (number | null)[]): number | null {
  let latest: number | null = null;
  for (const t of times) {
    if (t !== null && (latest === null || t > latest)) latest = t;
  }
  return latest;
}

/**
 * 最後の更新からの秒（切り捨て）。今より先の時刻（時計のずれ）は 0、上限は MAX_SPAN_SEC（7 日）。
 * 最後の更新か「今」が有限の数でなければ null（壊れた時計を、0 秒の「更新したて」に見せない）。
 */
export function quietSecAt(lastMs: number | null, nowMs: number): number | null {
  if (lastMs === null || !Number.isFinite(lastMs) || !Number.isFinite(nowMs)) return null;
  return Math.min(elapsedSec(lastMs, nowMs), MAX_SPAN_SEC);
}
