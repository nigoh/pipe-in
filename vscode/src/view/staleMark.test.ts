// 止まっているかもしれない実行の印の共通部品（D0021・view/staleMark.ts）。純粋な文字列の検査。
// 印の属性（data-quiet・data-stale-after）と印の時間の要素を作る関数に、出す値・出さない値の表を通す。
// 新しい部品（view/staleMark.ts）は、呼んだところで落ちるように、テストの中で読み込む。
import { test } from 'node:test';
import assert from 'node:assert/strict';

const mod = () => import('./staleMark.ts');

/** [ラベル, 値, 期待する文字]。期待が '' のものは「何も出さない」。 */
type Case = readonly [string, unknown, string];

// ---- AC-50 ②：staleAttrs の表（基準の秒・目安の秒を数として使えるときだけ、2 つの属性をそろえて出す） ----

const QUIET_CASES: readonly Case[] = [
  ['0（出す）', 0, ' data-quiet="0" data-stale-after="600"'],
  ['83.9（整数部の 83 を出す）', 83.9, ' data-quiet="83" data-stale-after="600"'],
  ['604800（7 日。出す）', 604800, ' data-quiet="604800" data-stale-after="600"'],
  ['-1', -1, ''],
  ['-0.5', -0.5, ''],
  ['NaN', Number.NaN, ''],
  ['Infinity', Number.POSITIVE_INFINITY, ''],
  ["文字 '12'", '12', ''],
  ['null', null, ''],
  ['undefined', undefined, ''],
];

for (const [label, quiet, expected] of QUIET_CASES) {
  test(`D0021-AC-50: staleAttrs：基準の秒が ${label} のとき、${expected === '' ? '何も出さない' : '2 つの属性を出す'}`, async () => {
    const { staleAttrs } = await mod();
    assert.equal(staleAttrs(quiet as number, 600), expected);
  });
}

const AFTER_CASES: readonly Case[] = [
  ['600（出す）', 600, ' data-quiet="100" data-stale-after="600"'],
  ['1（出す）', 1, ' data-quiet="100" data-stale-after="1"'],
  ['1.9（整数部の 1 を出す）', 1.9, ' data-quiet="100" data-stale-after="1"'],
  ['0（印なし）', 0, ''],
  ['0.5', 0.5, ''],
  ['-5', -5, ''],
  ['NaN', Number.NaN, ''],
  ['Infinity', Number.POSITIVE_INFINITY, ''],
  ["文字 '600'", '600', ''],
  ['null（印なし）', null, ''],
  ['undefined', undefined, ''],
];

for (const [label, after, expected] of AFTER_CASES) {
  test(`D0021-AC-50: staleAttrs：目安の秒が ${label} のとき、${expected === '' ? '何も出さない' : '2 つの属性を出す'}`, async () => {
    const { staleAttrs } = await mod();
    assert.equal(staleAttrs(100, after as number), expected);
  });
}

test('D0021-AC-50: staleAttrs：片方だけが使えないときは、使える方の属性も出さない（2 つそろって出るか、どちらも出ない）', async () => {
  const { staleAttrs } = await mod();
  assert.notEqual(staleAttrs(100, 600), '', '対照：両方使えるなら出る');
  assert.equal(staleAttrs(Number.NaN, 600), '');
  assert.equal(staleAttrs(100, Number.NaN), '');
  assert.equal(staleAttrs(100, 0), '');
});

// ---- AC-50 ③：staleTime の表 ----

const TIME_CASES: readonly (readonly [string, unknown, string])[] = [
  ['83', 83, '<span class="elapsed" data-elapsed="83">1:23</span>'],
  ['0', 0, '<span class="elapsed" data-elapsed="0">0:00</span>'],
  ['83.9（整数部の 83）', 83.9, '<span class="elapsed" data-elapsed="83">1:23</span>'],
  ['612', 612, '<span class="elapsed" data-elapsed="612">10:12</span>'],
  ['3725（1 時間を超える）', 3725, '<span class="elapsed" data-elapsed="3725">1:02:05</span>'],
  ['604800（7 日。桁あふれしない）', 604800, '<span class="elapsed" data-elapsed="604800">168:00:00</span>'],
  ['NaN', Number.NaN, ''],
  ['Infinity', Number.POSITIVE_INFINITY, ''],
  ['-1', -1, ''],
  ["文字 '12'", '12', ''],
];

for (const [label, quiet, expected] of TIME_CASES) {
  test(`D0021-AC-50: staleTime：${label} のとき、${expected === '' ? '空の文字' : '経過の要素（data-elapsed と m:ss）を出す'}`, async () => {
    const { staleTime } = await mod();
    assert.equal(staleTime(quiet as number), expected);
  });
}

test('D0021-AC-50: staleTime：図の中（SVG の文字）では tspan にできる。要素の名前以外は span と同じ', async () => {
  const { staleTime } = await mod();
  assert.equal(staleTime(612, 'tspan'), '<tspan class="elapsed" data-elapsed="612">10:12</tspan>');
  assert.equal(staleTime(Number.NaN, 'tspan'), '');
});

// ---- 数として使える値の見分け（staleAttrs・staleTime の土台） ----

test('D0021-AC-50: usableQuiet：有限で 0 以上の数だけ true', async () => {
  const { usableQuiet } = await mod();
  const table: readonly (readonly [unknown, boolean])[] = [
    [0, true],
    [1, true],
    [83.9, true],
    [604800, true],
    [-1, false],
    [-0.5, false],
    [Number.NaN, false],
    [Number.POSITIVE_INFINITY, false],
    [Number.NEGATIVE_INFINITY, false],
    ['12', false],
    [true, false],
    [null, false],
    [undefined, false],
  ];
  for (const [value, expected] of table) assert.equal(usableQuiet(value), expected, String(value));
});

test('D0021-AC-50: usableStaleAfter：有限で 1 以上の数だけ true（0 は印なし）', async () => {
  const { usableStaleAfter } = await mod();
  const table: readonly (readonly [unknown, boolean])[] = [
    [1, true],
    [1.9, true],
    [600, true],
    [0, false],
    [0.5, false],
    [-5, false],
    [Number.NaN, false],
    [Number.POSITIVE_INFINITY, false],
    ['600', false],
    [true, false],
    [null, false],
    [undefined, false],
  ];
  for (const [value, expected] of table) assert.equal(usableStaleAfter(value), expected, String(value));
});

// ---- 印の言葉 ----

test('D0021-AC-50: 印の言葉は固定の文字で、HTML の特殊文字（< > " & \'）を含まない（外から来た文字を入れる場所が無い）', async () => {
  const m = await mod();
  assert.equal(m.STALE_WORD, '⚠ 更新なし');
  assert.equal(m.STALE_BADGE_WORD, '⚠ 止まっているかも');
  assert.equal(m.STALE_NOTICE_HEAD, 'この段のログが');
  assert.equal(m.STALE_NOTICE_TAIL, '更新されていません。');
  assert.equal(m.STALE_NOTICE_SUB, 'プロセスは調べていません。長い段では、動いていてもログが更新されないことがあります。');
  for (const word of [m.STALE_WORD, m.STALE_BADGE_WORD, m.STALE_NOTICE_HEAD, m.STALE_NOTICE_TAIL, m.STALE_NOTICE_SUB]) {
    assert.doesNotMatch(word, /[<>"&']/, word);
  }
});
