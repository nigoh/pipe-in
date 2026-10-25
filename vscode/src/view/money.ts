// 金額の書き方（D0051）。図の節と費用の表の両方で使う。数字だけで作り、指数表記や NaN の文字は出さない。
import { toMilli } from '../domain/stageBudget.ts';

/** 10000 ドルを超える額は $10000+ と書く（1/1000 ドル単位で） */
const MILLI_CAP = 10_000_000;

/** 1/1000 ドル単位の整数から金額の文字を作る。小数が 2 桁で足りるときは 2 桁（$0.42・$1.00）、そうでなければ 3 桁（$0.004）。 */
export function formatMilli(milli: number): string {
  if (Number.isNaN(milli) || milli < 0) return '$0.00';
  if (milli > MILLI_CAP) return '$10000+';
  const three = (milli / 1000).toFixed(3);
  return `$${three.endsWith('0') ? three.slice(0, -1) : three}`;
}

export function formatUsd(usd: number): string {
  return formatMilli(toMilli(usd));
}
