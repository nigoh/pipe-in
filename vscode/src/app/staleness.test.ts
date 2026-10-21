// アプリケーション：設定 pipe-in.staleAfterMinutes（分）→ 「止まっているかも」の目安の秒（D0021）。AC-10。
// 新しい部品（app/staleness.ts）は、テスト先行のときに「まだ無い」ことで落ちるように、テストの中で動的に読み込む。
import { test } from 'node:test';
import assert from 'node:assert/strict';

const staleness = () => import('./staleness.ts');
/** MAX_SPAN_SEC（7 日）は domain/timestamp.ts に足される定数。テスト先行のときは型に無かったので unknown で取る。 */
const timestamp = async () => (await import('../domain/timestamp.ts')) as unknown as { MAX_SPAN_SEC?: number };

/** ［見出し, 設定の値, 目安の秒（null は印なし）］ */
const TABLE: readonly (readonly [string, unknown, number | null])[] = [
  ['10', 10, 600],
  ['1', 1, 60],
  ['0（印なし）', 0, null],
  ['無し（undefined）', undefined, 600],
  ['1.5（小数）', 1.5, 600],
  ["'10'（文字）", '10', 600],
  ["'0'（文字）", '0', 600],
  ['true', true, 600],
  ['false', false, 600],
  ["''（空の文字）", '', 600],
  ['[]', [], 600],
  ['[10]（数を 1 つ持つ配列）', [10], 600],
  ['{}', {}, 600],
  ['-1（負）', -1, 600],
  ['Infinity', Number.POSITIVE_INFINITY, 600],
  ['-Infinity', Number.NEGATIVE_INFINITY, 600],
  ['NaN', Number.NaN, 600],
  ['null', null, 600],
  ['10080（上限の 7 日）', 10080, 604800],
  ['10081（上限を超える）', 10081, 604800],
  ['1000000（大きな整数）', 1_000_000, 604800],
];

for (const [label, setting, expected] of TABLE) {
  test(`D0021-AC-10: staleAfterSeconds(${label}) は ${expected === null ? '印なし（null）' : `${expected} 秒`}`, async () => {
    const { staleAfterSeconds } = await staleness();
    assert.equal(staleAfterSeconds(setting), expected);
  });
}

// 設定が無いとき 600、上限のとき 604800 になることは、上の表が見ている。ここでは定数そのものだけを確かめる。
// （manifest.test.ts の D0021-AC-09 は、宣言の maximum が定数とずれないことを見る。ここは定数どうしの関係。）
test('D0021-AC-10: 既定は 10 分、上限は 10080 分（定数 DEFAULT_STALE_AFTER_MINUTES・MAX_STALE_AFTER_MINUTES）', async () => {
  const { DEFAULT_STALE_AFTER_MINUTES, MAX_STALE_AFTER_MINUTES } = await staleness();
  assert.equal(DEFAULT_STALE_AFTER_MINUTES, 10);
  assert.equal(MAX_STALE_AFTER_MINUTES, 10080);
});

test('D0021-AC-10: 上限の分 × 60 は、7 日の秒 MAX_SPAN_SEC（timestamp.ts の 1 つの定数。604800）と等しい（数を二重に書いてずらさない）', async () => {
  const { MAX_SPAN_SEC } = await timestamp();
  assert.equal(MAX_SPAN_SEC, 604800, '前提：7 日の秒は timestamp.ts の 1 つの定数');
  const { MAX_STALE_AFTER_MINUTES } = await staleness();
  assert.equal(MAX_STALE_AFTER_MINUTES * 60, MAX_SPAN_SEC);
});
