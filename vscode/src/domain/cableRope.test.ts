// 引いている最中のケーブルを、ひもとして動かす：両端を固定し、長さは両端の最短の距離。手元を動かすと遅れてついてきて、止めるとまっすぐに戻る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { restRope, ropeSettled, stepRope } from './cableRope.ts';
import type { Rope } from './cableRope.ts';
import type { Point } from './pipeModel.ts';

const DT = 1 / 60;
const A = { x: 0, y: 0 }, B = { x: 100, y: 0 };
const N = 16;

/** 止まった形の途中の点を上下に 30px ずらしたもの（前の位置も同じにして、速さは 0 から） */
function shaken(): Rope {
  const r = restRope(A, B, N);
  assert.equal(r.pts.length, N, '止まった形は N 個の点');
  const pts = r.pts.map((p, i) => (i === 0 || i === N - 1 ? { ...p } : { x: p.x, y: p.y + 30 * Math.sin((i / (N - 1)) * Math.PI) }));
  return { pts, prev: pts.map((p) => ({ ...p })) };
}
function run(r: Rope, a: Point, b: Point, steps: number, dt = DT): Rope {
  for (let i = 0; i < steps; i++) r = stepRope(r, a, b, dt);
  assert.equal(r.pts.length, N, '進めても点の数は変わらない');
  return r;
}
const finite = (r: Rope): boolean => r.pts.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
/** 線分 a–b からの距離 */
function off(p: Point, a: Point, b: Point): number {
  const dx = b.x - a.x, dy = b.y - a.y, l = dx * dx + dy * dy;
  const t = l === 0 ? 0 : Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / l));
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}
const moved = (a: Rope, b: Rope): number => Math.max(...a.pts.map((p, i) => Math.hypot(p.x - b.pts[i]!.x, p.y - b.pts[i]!.y)));

test('D0007-AC-14: 両端は、何歩進めても渡した位置にちょうどある（手元を動かしながらでも）', () => {
  let r = shaken();
  for (let i = 0; i < 200; i++) {
    const hand = { x: 100 + 40 * Math.sin(i / 7), y: 30 * Math.cos(i / 5) };
    r = stepRope(r, A, hand, DT);
    assert.deepEqual(r.pts[0], A);
    assert.deepEqual(r.pts.at(-1), hand);
  }
  assert.equal(r.pts.length, N);
});

test('D0007-AC-15: 乱した形から 600 歩進めると、となりの点の間はどれも、両端の距離 ÷ 区間の数との差が 2% 以内（長さは最短の距離）', () => {
  const r = run(shaken(), A, B, 600), want = 100 / (N - 1);
  for (let i = 1; i < N; i++) {
    const d = Math.hypot(r.pts[i]!.x - r.pts[i - 1]!.x, r.pts[i]!.y - r.pts[i - 1]!.y);
    assert.ok(Math.abs(d - want) <= want * 0.02, `区間 ${i}: ${d}`);
  }
});

test('D0007-AC-16: 600 歩進めると、どの点も両端を結ぶ線分から 1px 以内（まっすぐな線に戻る）', () => {
  const r = run(shaken(), A, B, 600);
  for (const p of r.pts) assert.ok(off(p, A, B) <= 1, JSON.stringify(p));
});

test('D0007-AC-17: 静止に近づき、そのときは「静止した」と分かる。乱した直後の1歩目は静止していない', () => {
  const first = shaken(), one = stepRope(first, A, B, DT);
  assert.equal(ropeSettled(first, one), false);
  const r = run(first, A, B, 600), next = stepRope(r, A, B, DT);
  assert.ok(moved(r, next) < 0.05, `動き ${moved(r, next)}`);
  assert.equal(ropeSettled(r, next), true);
});

test('D0007-AC-18: 手元を一度に 50px 動かすと、まん中は手元ほどは動かない（遅れてついてくる）。止めればやがて静止する', () => {
  const r0 = restRope(A, B, N), hand = { x: 150, y: 0 }, mi = Math.floor(N / 2);
  assert.equal(r0.pts.length, N);
  const r1 = stepRope(r0, A, hand, DT);
  const dm = Math.hypot(r1.pts[mi]!.x - r0.pts[mi]!.x, r1.pts[mi]!.y - r0.pts[mi]!.y);
  assert.ok(dm < 50 * 0.5, `まん中の動き ${dm}`);
  assert.ok(dm > 0, 'まん中も少しは動く');
  const r = run(r1, A, hand, 600);
  assert.equal(ropeSettled(r, stepRope(r, A, hand, DT)), true);
  for (const p of r.pts) assert.ok(off(p, A, hand) <= 1);
});

test('D0007-AC-19: 刻みが 0 なら、点の並びは変わらない', () => {
  const r = shaken(), same = stepRope(r, A, B, 0);
  assert.deepEqual(same.pts, r.pts);
  assert.notEqual(same.pts, r.pts, '新しい並びを返す');
});

test('D0007-AC-20: 刻みが大きくても負でも、NaN・Infinity にならず、両端の決まりは守られる', () => {
  for (const dt of [1, 10, -1, -0.5]) {
    const r = run(shaken(), A, { x: 300, y: -80 }, 5, dt);
    assert.ok(finite(r), `dt=${dt}`);
    assert.deepEqual(r.pts[0], A);
    assert.deepEqual(r.pts.at(-1), { x: 300, y: -80 });
  }
});

test('D0007-AC-21: 同じ入力からは同じ出力。渡した並び（配列も中の点も）は書き換えない', () => {
  const r = shaken(), copy = JSON.parse(JSON.stringify(r)) as Rope;
  const x = stepRope(r, A, { x: 130, y: 20 }, DT), y = stepRope(r, A, { x: 130, y: 20 }, DT);
  assert.deepEqual(x, y);
  assert.deepEqual(r, copy);
  assert.notEqual(x.pts, r.pts);
});

test('D0007-AC-22: 手元を急に遠くへ動かしても NaN にならず、止めれば両端を結ぶ線分の近く（2px 以内）に並ぶ', () => {
  const far = { x: 1200, y: 700 };
  let r = run(shaken(), A, far, 3);
  assert.ok(finite(r));
  r = run(r, A, far, 900);
  for (const p of r.pts) assert.ok(off(p, A, far) <= 2, JSON.stringify(p));
});

test('D0007-AC-23: 両端が同じ点でも NaN にならない', () => {
  const r = run(restRope(A, A, N), A, A, 10);
  assert.ok(finite(r));
  const r2 = run(shaken(), { x: 50, y: 0 }, { x: 50, y: 0 }, 10);
  assert.ok(finite(r2));
});

test('D0007-AC-24: 止まった形は、両端を結ぶ線分を等しく分けた点の並び（前の位置も同じ）', () => {
  const b = { x: 90, y: 120 }, r = restRope(A, b, N);
  assert.equal(r.pts.length, N);
  assert.deepEqual(r.pts[0], A);
  assert.deepEqual(r.pts.at(-1), b);
  const step = Math.hypot(b.x, b.y) / (N - 1);
  for (let i = 1; i < N; i++) {
    assert.ok(Math.abs(Math.hypot(r.pts[i]!.x - r.pts[i - 1]!.x, r.pts[i]!.y - r.pts[i - 1]!.y) - step) < 1e-9);
    assert.ok(off(r.pts[i]!, A, b) < 1e-9);
  }
  assert.deepEqual(r.prev, r.pts);
  assert.notEqual(r.prev, r.pts);
});

test('D0007-AC-25: ひもの計算は、時計・画面の更新の予約・DOM に触れない', () => {
  const src = readFileSync(new URL('./cableRope.ts', import.meta.url), 'utf8').replace(/\/\/.*$/gm, '');
  for (const word of ['Date', 'performance', 'requestAnimationFrame', 'document', 'window']) {
    assert.doesNotMatch(src, new RegExp(`\\b${word}\\b`), word);
  }
});
