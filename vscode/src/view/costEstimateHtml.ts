// 作業台の「費用の目安」の節（HTML の文字列、純粋）。D0066。
// 外から来た文字（段の名前・モデルの名前）は escapeHtml を通す。インラインの style 属性・スクリプト・外部の読み込みは書かない（CSP）。
import { DEFAULT_TURNS, DISCLAIMER } from '../domain/costEstimate.ts';
import type { CostEstimate, CostMark } from '../domain/costEstimate.ts';
import { escapeHtml as esc } from './escape.ts';

const MARK_TEXT: Record<CostMark, string> = {
  model_unknown: 'モデル不明（sonnet として計算）',
  turns_invalid: `ターンの上限が読めない（${DEFAULT_TURNS} として計算）`,
};
const STALE_TEXT = '単価表が古いかもしれません';

/** units（1/10000 ドル）を「$1.40」のように書く（小数は 2〜4 桁。末尾の 0 は 2 桁まで落とす） */
function usd(units: number): string {
  let text = (units / 10000).toFixed(4);
  while (text.endsWith('0') && text.split('.')[1]!.length > 2) text = text.slice(0, -1);
  return `$${text}`;
}

const range = (low: number, high: number): string => `${usd(low)}〜${usd(high)}`;

/** 閉じられる節。見出し行に幅、中に段ごとの内訳・前の実績（あるときだけ）・印・DISCLAIMER。 */
export function costEstimateHtml(est: CostEstimate, actualUsd: number | null): string {
  const rows = est.stages
    .map((s) => {
      const model = typeof s.model === 'string' && s.model !== '' ? ` <span class="cost-model">${esc(s.model)}</span>` : '';
      const marks = s.marks.map((m) => `<span class="cost-mark">${esc(MARK_TEXT[m])}</span>`).join('');
      return `<tr><th scope="row">${esc(s.name)}${model}${marks}</th><td>${usd(s.low)}</td><td>${usd(s.high)}</td></tr>`;
    })
    .join('');
  const table = est.stages.length
    ? `<table class="cost-table"><thead><tr><th scope="col">段</th><th scope="col">少なめ</th><th scope="col">多め</th></tr></thead><tbody>${rows}</tbody></table>`
    : '<p class="note">段がまだありません</p>';
  const actual = actualUsd === null ? '' : `<p class="cost-actual">前の実績　${usd(actualUsd * 10000)}<span class="note">（目安には混ぜていません）</span></p>`;
  const stale = est.stale ? `<p class="cost-mark">${STALE_TEXT}</p>` : '';
  return (
    `<details class="box cost-estimate" id="cost-estimate"><summary>費用の目安　${range(est.low, est.high)}</summary>` +
    `<p class="cost-total">全体　少なめ ${usd(est.low)}　〜　多め ${usd(est.high)}</p>` +
    actual +
    table +
    stale +
    `<p class="note">${esc(DISCLAIMER)}</p></details>`
  );
}
