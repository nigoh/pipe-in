// 金額の書き方（D0051 の AC-46）：1/1000 ドル単位に四捨五入して書く。小数第 3 位が 0 なら小数 2 桁、そうでなければ 3 桁。
// 10000 ドル（丸めて 10000.000）を超える費用は $10000+。指数表記・NaN・Infinity の文字は出ない。
// 赤の理由は「まだ書き方が無い」：空の形の formatUsd・formatMilli は空の文字を返す。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatMilli, formatUsd } from './money.ts';

const FORMS: readonly (readonly [number, string])[] = [
  [0.42, '$0.42'],
  [1.0, '$1.00'],
  [0.004, '$0.004'],
  [0.125, '$0.125'],
  [12.3456, '$12.346'],
  [10000.5, '$10000+'],
  [1e21, '$10000+'],
  [0, '$0.00'],
  [0.1, '$0.10'],
  [1.5, '$1.50'],
  [123.456, '$123.456'],
  [200, '$200.00'],
  [9999.999, '$9999.999'],
  [10000, '$10000.00'],
  [10000.001, '$10000+'],
  [0.0004, '$0.00'],
];
for (const [usd, text] of FORMS) {
  test(`D0051-AC-46: 金額の書き方 ${usd} → ${text}`, () => {
    assert.equal(formatUsd(usd), text);
  });
}

for (const [milli, text] of [
  [420, '$0.42'],
  [1000, '$1.00'],
  [4, '$0.004'],
  [125, '$0.125'],
  [12346, '$12.346'],
  [123456, '$123.456'],
  [200000, '$200.00'],
  [10_000_000, '$10000.00'],
  [10_000_001, '$10000+'],
  [0, '$0.00'],
] as const) {
  test(`D0051-AC-46: 1/1000 ドルの整数 ${milli} → ${text}（formatMilli）`, () => {
    assert.equal(formatMilli(milli), text);
  });
}

test('D0051-AC-46: 割合のある小数は 1/1000 ドル単位に四捨五入してから書く（0.7996 → $0.80、0.1 + 0.2 → $0.30）', () => {
  assert.equal(formatUsd(0.7996), '$0.80');
  assert.equal(formatUsd(0.1 + 0.2), '$0.30');
});

test('D0051-AC-46: NaN・Infinity・指数表記の文字が出ない（極端な値でも「$数字.小数」か「$10000+」の形）', () => {
  const shapes = /^\$(?:\d{1,5}\.\d{2,3}|10000\+)$/;
  for (const usd of [1e21, 1e-7, 5e-324, 1e300, Number.MAX_VALUE, -1e21, -1, -0.0001, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
    const text = formatUsd(usd);
    assert.match(text, shapes, `${usd} → ${text}`);
    assert.doesNotMatch(text, /e|NaN|Infinity/i, `${usd} → ${text}`);
  }
});

test('D0051-AC-46: 負の数・NaN は $0.00、+Infinity は $10000+', () => {
  assert.equal(formatUsd(-1), '$0.00');
  assert.equal(formatUsd(Number.NaN), '$0.00');
  assert.equal(formatUsd(Number.NEGATIVE_INFINITY), '$0.00');
  assert.equal(formatUsd(Number.POSITIVE_INFINITY), '$10000+');
});
