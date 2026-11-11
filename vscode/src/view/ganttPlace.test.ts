// 時系列の確認待ちの字の置き場所（D0090・AC-06〜08）：view/ganttPlace.ts の純粋な関数 placeWaitText と、境目の定数。
// 帯の位置は割合（%）。待ちの帯が字より狭く、同じ行の左に字の範囲へかかる実行の帯があるときだけ、字を行の下（below）へ出す。
// 空の形（placeWaitText は例外を投げる）を置いてあるので、置き場所を返すテストは「まだ実装していません」で赤になる。
// 定数のテストは今の作りのままで通る（境目を固定する守り）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SIDE_LIMIT, WAIT_NARROW, WAIT_TEXT_LONG, WAIT_TEXT_SHORT, placeWaitText } from './ganttPlace.ts';
import type { PlaceBar } from './ganttPlace.ts';

const bar = (left: number, end: number): PlaceBar => ({ left, end, width: Math.round((end - left) * 1000) / 1000 });
/** 再現の待ちの帯：長さ 0（幅は下限の 0.3%）で右端 100% */
const ZERO_WAIT: PlaceBar = { left: 100, end: 100, width: 0.3 };

// ---- 境目の定数（今の作りで通る） ----

test('D0090-AC-07: 境目の定数：右に出す限りは 85%（今の規則のまま）・狭い待ちは 5%・字の長さの目安は短い 18%・長い 32%', () => {
  assert.equal(SIDE_LIMIT, 85);
  assert.equal(WAIT_NARROW, 5);
  assert.equal(WAIT_TEXT_SHORT, 18);
  assert.equal(WAIT_TEXT_LONG, 32);
  assert.ok(WAIT_TEXT_SHORT < WAIT_TEXT_LONG, '印つきの長い字のほうが範囲が広い');
});

// ---- AC-06：実行の帯の上に乗らない置き場所 ----

test('D0090-AC-06: 再現の値（待ちの帯 幅 0.3%・右端 100%・左の実行の帯 幅 100%）：印つきの字は below', () => {
  assert.equal(placeWaitText({ wait: ZERO_WAIT, run: bar(0, 100), long: true }), 'below');
});

test('D0090-AC-06: 再現の値：印のない短い字（確認待ち m:ss だけ）でも below', () => {
  assert.equal(placeWaitText({ wait: ZERO_WAIT, run: bar(0, 100), long: false }), 'below');
});

test('D0090-AC-06: 長さ 0 の待ちが右端より少し内側（左 99.7%・右端 100%・幅 0.3%）で、実行の帯がその手前まで続くときも below', () => {
  assert.equal(placeWaitText({ wait: { left: 99.7, end: 100, width: 0.3 }, run: bar(0, 99.7), long: true }), 'below');
});

test('D0090-AC-06: 待ちの帯が字より狭く（幅 4.99%）、左の実行の帯が字の範囲にかかるときは below（狭いの境目は 5% 未満）', () => {
  assert.equal(placeWaitText({ wait: { left: 95.01, end: 100, width: 4.99 }, run: bar(0, 95.01), long: true }), 'below');
});

// ---- AC-07：今と同じ置き場所を返す（守る） ----

test('D0090-AC-07: 右端が 85% 以下の待ちは、今のまま right（右端ちょうど 85% を含む）', () => {
  assert.equal(placeWaitText({ wait: bar(40, 60), run: bar(0, 35), long: true }), 'right');
  assert.equal(placeWaitText({ wait: bar(70, 85), run: bar(0, 65), long: true }), 'right');
});

test('D0090-AC-07: 右端が 85% 以下なら、幅が狭くても（長さ 0 に近い待ち）right。実行の帯が左に広くても変えない', () => {
  assert.equal(placeWaitText({ wait: { left: 40, end: 40, width: 0.3 }, run: bar(0, 40), long: true }), 'right');
});

test('D0090-AC-07: 右端が 85% を超え、幅が 5% 以上の待ちは、今のまま left（幅 6%・5% ちょうど・10%）', () => {
  assert.equal(placeWaitText({ wait: bar(90, 96), run: bar(0, 85), long: true }), 'left');
  assert.equal(placeWaitText({ wait: bar(95, 100), run: bar(0, 95), long: true }), 'left', '幅ちょうど 5% は狭くない');
  assert.equal(placeWaitText({ wait: bar(90, 100), run: bar(0, 85), long: true }), 'left');
});

test('D0090-AC-07: 右端が 86% の待ち（幅 16%）と、待ち中でない 60〜95%（実行は 0〜50%）は、今のまま left', () => {
  assert.equal(placeWaitText({ wait: bar(70, 86), run: bar(0, 65), long: true }), 'left');
  assert.equal(placeWaitText({ wait: bar(60, 95), run: bar(0, 50), long: false }), 'left');
});

test('D0090-AC-07: 狭い待ちでも、左の実行の帯が字の範囲の外（短い 18%・長い 32% より手前で終わる）なら left', () => {
  assert.equal(placeWaitText({ wait: ZERO_WAIT, run: bar(0, 50), long: true }), 'left');
  assert.equal(placeWaitText({ wait: ZERO_WAIT, run: bar(0, 50), long: false }), 'left');
});

test('D0090-AC-07: 狭い待ちでも、同じ行に実行の帯が無い（null）なら left', () => {
  assert.equal(placeWaitText({ wait: ZERO_WAIT, run: null, long: true }), 'left');
});

test('D0090-AC-07: 狭い待ちでも、実行の帯が待ちの帯の右にある（run.left が待ちの左端以上）なら、左は空いているので left', () => {
  assert.equal(placeWaitText({ wait: { left: 90, end: 90.3, width: 0.3 }, run: bar(90, 100), long: true }), 'left');
});

// ---- AC-08：字の長さで分ける ----

test('D0090-AC-08: 実行の帯の右端が待ちの左端の手前 18% と 32% の間（70%）：印つきの長い字は below、印のない短い字は left', () => {
  assert.equal(placeWaitText({ wait: ZERO_WAIT, run: bar(0, 70), long: true }), 'below');
  assert.equal(placeWaitText({ wait: ZERO_WAIT, run: bar(0, 70), long: false }), 'left');
});

test('D0090-AC-08: 長い字の境目は 32%：実行の帯の右端が 68% ちょうどは left、68.01% は below', () => {
  assert.equal(placeWaitText({ wait: ZERO_WAIT, run: bar(0, 68), long: true }), 'left');
  assert.equal(placeWaitText({ wait: ZERO_WAIT, run: bar(0, 68.01), long: true }), 'below');
});

test('D0090-AC-08: 短い字の境目は 18%：実行の帯の右端が 82% ちょうどは left、82.01% は below', () => {
  assert.equal(placeWaitText({ wait: ZERO_WAIT, run: bar(0, 82), long: false }), 'left');
  assert.equal(placeWaitText({ wait: ZERO_WAIT, run: bar(0, 82.01), long: false }), 'below');
});

test('D0090-AC-08: どちらの長さでも、実行の帯が十分広ければ（0〜100%）below。長い字のほうが below にかかりやすい（短い字が below なら長い字も below）', () => {
  for (const end of [60, 68.01, 70, 82.01, 90, 100]) {
    const short = placeWaitText({ wait: ZERO_WAIT, run: bar(0, end), long: false });
    const long = placeWaitText({ wait: ZERO_WAIT, run: bar(0, end), long: true });
    if (short === 'below') assert.equal(long, 'below', `実行の帯の右端 ${end}%`);
  }
});
