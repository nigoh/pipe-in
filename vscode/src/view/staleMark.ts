// 止まっているかもしれない実行の印の共通部品（D0021・純粋）。節・矢印・一覧の行・詳細のバッジと知らせ・時系列の帯が同じ言葉と同じ属性を使う。
// 印の要素の中身は、ここにある固定の言葉と数字だけ。外から来た文字（セッション名・段の名前・ログの文字）は入れない。
// 属性 data-quiet（基準の秒）と data-stale-after（目安の秒）は数字だけの文字。パネルのスクリプトが、基準＋差が目安に届いた要素に is-stale を付ける。
import type { RunRow } from '../domain/runList.ts';
import { formatDuration } from './duration.ts';

/** 図の節・一覧の行の印。 */
export const STALE_WORD = '⚠ 更新なし';
/** 詳細のバッジ。 */
export const STALE_BADGE_WORD = '⚠ 止まっているかも';
/** 詳細の知らせの文。時間（要素）をはさんで「頭 時間 尾」と読む。 */
export const STALE_NOTICE_HEAD = 'この段のログが';
export const STALE_NOTICE_TAIL = '更新されていません。';
export const STALE_NOTICE_SUB = 'プロセスは調べていません。長い段では、動いていてもログが更新されないことがあります。';

/** 枠・点線の色（CSS の文字に埋める。色の直書きはしない）。文字の色は読みやすさのため前景色のままにする。 */
export const STALE_COLOR = 'var(--vscode-charts-orange, var(--vscode-foreground))';

// 属性の値は数字だけにしたいので、安全な整数に収まる数だけ使う（収まらないと 1e+21 のような文字になる）。
/** 基準の秒として使える値：数で、有限で、0 以上。 */
export function usableQuiet(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= Number.MAX_SAFE_INTEGER;
}

/** 目安の秒として使える値：数で、有限で、1 以上（0 は「印を出さない」）。 */
export function usableStaleAfter(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 1 && value <= Number.MAX_SAFE_INTEGER;
}

/**
 * 印の元の属性。基準の秒と目安の秒の両方が使えるときだけ、先頭に空白を置いて返す（そのまま開きタグに続けられる）。
 * どちらかが使えなければ空の文字（片方だけは出さない）。どちらも整数部を出す。
 */
export function staleAttrs(quietSec: unknown, staleAfterSec: unknown): string {
  if (!usableQuiet(quietSec) || !usableStaleAfter(staleAfterSec)) return '';
  return ` data-quiet="${Math.floor(quietSec)}" data-stale-after="${Math.floor(staleAfterSec)}"`;
}

/**
 * 一覧の行・選んだ行の印の属性。動いている行（state が running）だけが印の対象で、確認待ち・待ち・終わった・前の実行の行には出さない。
 * 行が無い（null）ときも空の文字。印を出すかどうかの判断は、一覧の行と詳細で同じこの 1 つを使う。
 */
export function rowStaleAttrs(row: RunRow | null, staleAfterSec: unknown): string {
  return row !== null && row.state === 'running' ? staleAttrs(row.quietSec, staleAfterSec) : '';
}

/**
 * 印の中の時間の要素。data-elapsed に基準の秒を入れ、パネルのスクリプトが 1 秒ごとに数え上げる。
 * 図の中（SVG の文字）では tag を 'tspan' にする。基準の秒が使えなければ空の文字。
 */
export function staleTime(quietSec: unknown, tag: 'span' | 'tspan' = 'span'): string {
  if (!usableQuiet(quietSec)) return '';
  const sec = Math.floor(quietSec);
  return `<${tag} class="elapsed" data-elapsed="${sec}">${formatDuration(sec)}</${tag}>`;
}
