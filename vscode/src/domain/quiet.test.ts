// 最後の更新からの秒（D0021）：純粋な関数 validMtime・latestMtime・quietSecAt と、上限の定数 MAX_SPAN_SEC。
// 新しい部品（domain/quiet.ts と、timestamp.ts の MAX_SPAN_SEC）は、テスト先行のときに
// 呼んだところで「まだ無い」ことで落ちるように、テストの中で読み込む（ファイルごと import で落ちない。実装後も同じ読み方で通る）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BASE_MS } from '../test/liveFixtures.ts';
import { ANCIENT_MS } from '../test/staleFixtures.ts';

const quiet = () => import('./quiet.ts');
const timestamp = () => import('./timestamp.ts');

/** 7 日（秒）。 */
const WEEK_SEC = 7 * 24 * 3600;

// ---- AC-48：上限の定数 ----
// ここで確かめるのは定数の値だけ。時系列の長さの上限（7 日）は gantt.test.ts、設定の目安の上限は manifest.test.ts が確かめる。

test('D0021-AC-48: 上限の定数 MAX_SPAN_SEC は 7 日（604800 秒）', async () => {
  const { MAX_SPAN_SEC } = await timestamp();
  assert.equal(MAX_SPAN_SEC, 604800);
  assert.equal(MAX_SPAN_SEC, WEEK_SEC);
});

// ---- AC-04：今 − 最後の更新（秒、切り捨て） ----

const FLOOR_CASES: readonly (readonly [number, number])[] = [
  [0, 0],
  [1, 0],
  [999, 0],
  [1000, 1],
  [83_000, 83],
  [83_900, 83],
  [83_999, 83],
  [84_000, 84],
  [600_000, 600],
];

for (const [agoMs, expected] of FLOOR_CASES) {
  test(`D0021-AC-04: quietSecAt は「今 − 最後の更新」を秒にして切り捨てる（${agoMs}ms 前 → ${expected} 秒）`, async () => {
    const { quietSecAt } = await quiet();
    assert.equal(quietSecAt(BASE_MS - agoMs, BASE_MS), expected);
  });
}

test('D0021-AC-04: 同じ最後の更新でも「今」が進めば、進んだ秒だけ quietSecAt が増える', async () => {
  const { quietSecAt } = await quiet();
  const last = BASE_MS - 83_000;
  assert.equal(quietSecAt(last, BASE_MS), 83);
  assert.equal(quietSecAt(last, BASE_MS + 30_000), 113);
});

// ---- AC-05：時計のずれ（更新時刻が今より先） ----

for (const aheadMs of [1, 999, 1000, 300_000, 86_400_000]) {
  test(`D0021-AC-05: 更新時刻が今より ${aheadMs}ms 先（時計のずれ）でも、quietSecAt は負にならず 0`, async () => {
    const { quietSecAt } = await quiet();
    assert.equal(quietSecAt(BASE_MS + aheadMs, BASE_MS), 0);
  });
}

// ---- AC-48：7 日の上限 ----

const CAP_CASES: readonly (readonly [number, number])[] = [
  [WEEK_SEC - 1, WEEK_SEC - 1],
  [WEEK_SEC, WEEK_SEC],
  [WEEK_SEC + 1, WEEK_SEC],
  [WEEK_SEC * 10, WEEK_SEC],
];

for (const [agoSec, expected] of CAP_CASES) {
  test(`D0021-AC-48: quietSecAt は MAX_SPAN_SEC（604800）を上限にする（${agoSec} 秒前 → ${expected}）`, async () => {
    const { quietSecAt } = await quiet();
    assert.equal(quietSecAt(BASE_MS - agoSec * 1000, BASE_MS), expected);
  });
}

test('D0021-AC-48: 1980 年の更新時刻でも、quietSecAt は 604800 で頭打ち（表示が桁あふれしない）', async () => {
  const { quietSecAt } = await quiet();
  assert.equal(quietSecAt(ANCIENT_MS, BASE_MS), 604800);
});

// ---- AC-06・AC-08：読めない値は null ----

const UNREADABLE: readonly (readonly [string, number | null])[] = [
  ['null', null],
  ['NaN', Number.NaN],
  ['正の無限大', Number.POSITIVE_INFINITY],
  ['負の無限大', Number.NEGATIVE_INFINITY],
];

for (const [label, last] of UNREADABLE) {
  test(`D0021-AC-06: 最後の更新が${label}（読めない）なら、quietSecAt は null（対照：数なら秒が出る）`, async () => {
    const { quietSecAt } = await quiet();
    assert.equal(quietSecAt(BASE_MS - 5000, BASE_MS), 5);
    assert.equal(quietSecAt(last, BASE_MS), null);
  });
}

for (const [label, now] of UNREADABLE.filter(([, v]) => v !== null)) {
  test(`D0021-AC-08: 「今」が${label}（壊れた時計）なら、quietSecAt は null（対照：有限の「今」なら秒が出る）`, async () => {
    const { quietSecAt } = await quiet();
    assert.equal(quietSecAt(BASE_MS - 5000, BASE_MS), 5);
    assert.equal(quietSecAt(BASE_MS - 5000, now as number), null);
  });
}

// ---- AC-08：純粋 ----

test('D0021-AC-08: quietSecAt は引数だけで決まり、時計を読まない（Date.now を読むと投げる関数に替えても同じ結果）', async () => {
  const { quietSecAt } = await quiet();
  const expected = quietSecAt(BASE_MS - 83_900, BASE_MS);
  assert.equal(expected, 83);
  const realNow = Date.now;
  Date.now = () => {
    throw new Error('時計を読んだ');
  };
  try {
    assert.equal(quietSecAt(BASE_MS - 83_900, BASE_MS), expected);
  } finally {
    Date.now = realNow;
  }
});

test('D0021-AC-08: 同じ引数なら、何度呼んでも quietSecAt は同じ結果', async () => {
  const { quietSecAt } = await quiet();
  const results = [0, 1, 2, 3].map(() => quietSecAt(BASE_MS - 612_000, BASE_MS));
  assert.deepEqual(results, [612, 612, 612, 612]);
});

// ---- AC-02・AC-36：更新時刻の検め（validMtime） ----

for (const ok of [1, BASE_MS, ANCIENT_MS]) {
  test(`D0021-AC-02: validMtime は有限で 0 より大きい数（${ok}）をそのまま通す`, async () => {
    const { validMtime } = await quiet();
    assert.equal(validMtime(ok), ok);
  });
}

test('D0021-AC-02: validMtime は小数のミリ秒（stat の mtimeMs は小数になりうる）も通す', async () => {
  const { validMtime } = await quiet();
  const fractional = BASE_MS + 0.5;
  const got = validMtime(fractional);
  assert.equal(typeof got, 'number');
  assert.ok(Math.abs((got as number) - fractional) < 1, `${String(got)}`);
});

const NOT_POSITIVE_OR_FINITE: readonly (readonly [string, number])[] = [
  ['0', 0],
  ['-0', -0],
  ['-1', -1],
  ['-0.5', -0.5],
  ['NaN', Number.NaN],
  ['正の無限大', Number.POSITIVE_INFINITY],
  ['負の無限大', Number.NEGATIVE_INFINITY],
];

for (const [label, value] of NOT_POSITIVE_OR_FINITE) {
  test(`D0021-AC-02: validMtime は 0 以下・有限でない値（${label}）を null にする（対照：正の数は通る）`, async () => {
    const { validMtime } = await quiet();
    assert.equal(validMtime(BASE_MS), BASE_MS);
    assert.equal(validMtime(value), null);
  });
}

const NOT_A_NUMBER: readonly (readonly [string, unknown])[] = [
  ['文字', 'abc'],
  ['数の文字', '1760000000000'],
  ['空の文字', ''],
  ['真', true],
  ['偽', false],
  ['null', null],
  ['undefined', undefined],
  ['オブジェクト', { ms: BASE_MS }],
  ['空のオブジェクト', {}],
  ['空の配列', []],
  ['数の配列', [BASE_MS]],
];

for (const [label, value] of NOT_A_NUMBER) {
  test(`D0021-AC-36: validMtime は数でない値（${label}）を null にする（例外を投げない。対照：正の数は通る）`, async () => {
    const { validMtime } = await quiet();
    assert.equal(validMtime(BASE_MS), BASE_MS);
    assert.doesNotThrow(() => validMtime(value));
    assert.equal(validMtime(value), null);
  });
}

// ---- AC-44・AC-06・AC-08：全ログの最新（latestMtime。FR-13） ----

const LATEST_CASES: readonly (readonly [string, (number | null)[], number])[] = [
  ['昇順', [1, 3, 5], 5],
  ['降順', [5, 3, 1], 5],
  ['順不同', [3, 5, 1], 5],
  ['1 つだけ', [7], 7],
  ['読めないもの（null）が混じる', [null, 7, null, 4], 7],
  ['同じ値', [4, 4], 4],
];

for (const [label, times, expected] of LATEST_CASES) {
  test(`D0021-AC-44: latestMtime は読めるものの最新（最大）を選ぶ：${label}`, async () => {
    const { latestMtime } = await quiet();
    assert.equal(latestMtime(times), expected);
  });
}

test('D0021-AC-44: latestMtime は、最新が古い途中のログでも新しいログでも、読める時刻の最大を返す（3 日前と 5 秒前なら 5 秒前）', async () => {
  const { latestMtime } = await quiet();
  const old = BASE_MS - 3 * 24 * 3600 * 1000;
  const fresh = BASE_MS - 5000;
  assert.equal(latestMtime([old, fresh]), fresh);
  assert.equal(latestMtime([fresh, old]), fresh);
});

for (const [label, times] of [
  ['空', []],
  ['null だけ', [null]],
  ['null が複数', [null, null, null]],
] as const) {
  test(`D0021-AC-06: latestMtime は読める時刻が 1 つも無い（${label}）なら null（FR-13。基準が決まらないので、quietSec は null になる元）`, async () => {
    const { latestMtime } = await quiet();
    assert.equal(latestMtime([5, 6]), 6);
    assert.equal(latestMtime(times), null);
  });
}

test('D0021-AC-08: latestMtime は純粋な関数で、渡された配列を書き換えない', async () => {
  const { latestMtime } = await quiet();
  const times: (number | null)[] = [3, null, 9, 1];
  latestMtime(times);
  assert.deepEqual(times, [3, null, 9, 1]);
});
