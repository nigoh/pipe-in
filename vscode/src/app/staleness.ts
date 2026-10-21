// 設定 pipe-in.staleAfterMinutes（分）→ 「止まっているかも」の印を出す目安の秒（D0021）。
// 純粋（vscode・時計・ファイルに触れない）。設定を読むのは extension.ts で、ここは値を読み替えるだけ。
import { MAX_SPAN_SEC } from '../domain/timestamp.ts';

/** 設定が無い・合わない値のときの目安（分） */
export const DEFAULT_STALE_AFTER_MINUTES = 10;
/** 設定の上限（分）。最後の更新からの秒の上限（7 日）と同じ。これを超える目安は永遠に届かない。数は timestamp.ts の 1 つだけに置く */
export const MAX_STALE_AFTER_MINUTES = MAX_SPAN_SEC / 60;

/**
 * 設定の値（分）→ 目安の秒。
 * 整数の 0 → null（印を出さない）、1 以上の整数 → 分 × 60（上限は 10080 分）。
 * 無い・小数・文字・真偽・配列・オブジェクト・負・無限大・NaN・null は、既定の 10 分。
 */
export function staleAfterSeconds(setting: unknown): number | null {
  if (typeof setting !== 'number' || !Number.isInteger(setting) || setting < 0) return DEFAULT_STALE_AFTER_MINUTES * 60;
  if (setting === 0) return null;
  return Math.min(setting, MAX_STALE_AFTER_MINUTES) * 60;
}
