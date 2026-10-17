// プラグを離した点から差す先を決める：コンセント（タップ）の上でも差さる。コンセントを先に見て、次にブロックの四角。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { END, blockSize, newPipe, newStage } from './pipeModel.ts';
import type { BlockKind, PipeModel, StageModel } from './pipeModel.ts';
import { blockRect, layoutWires } from './pipeWires.ts';
import { dropTarget } from './pipeDrop.ts';

function stage(id: string, kind: BlockKind, x: number, y: number, over: Partial<StageModel> = {}): StageModel {
  return { ...newStage(id, kind, id), x, y, ...over };
}

/**
 * a → b ← z（b には2本入る）、c には何も入らない、e → 並列の枠 F（f1）。d は判定に通らなければ a へ戻す。
 */
function sample(): PipeModel {
  const m = newPipe('drop');
  m.stages = [
    stage('a', 'research', 100, 100, { next: 'b' }),
    stage('z', 'research', 100, 400, { next: 'b' }),
    stage('b', 'research', 500, 250, { next: END }),
    stage('c', 'research', 900, 600),
    stage('e', 'research', 500, 800, { next: 'F' }),
    stage('f1', 'docs', 950, 840),
    stage('d', 'verify', 1400, 100, { next: END, check: { on: true, verdict: true, command: '', maxRetries: 2 }, onFail: 'a' }),
  ];
  m.frames = [{ id: 'F', name: 'g', x: 900, y: 800, w: 320, h: 220, next: null }];
  m.start = { x: -200, y: 110 };
  m.end = { x: 1900, y: 300 };
  return m;
}
const at = (m: PipeModel, p: { x: number; y: number }, tol = 0): string | null => dropTarget(m, layoutWires(m), p, tol);
const mid = (m: PipeModel, id: string): number => { const r = blockRect(m, id); return r.y + r.h / 2; };

test('D0007-AC-01: 何も差さっていないコンセントの上で離すと、そのブロックに差さる（ブロックの四角の外でも）', () => {
  const m = sample(), r = blockRect(m, 'c');
  // コンセントの外形は、ブロックの左の縁の 16px 手前から（x −1〜14・y −12〜12）
  const p = { x: r.x - 16 + 7, y: mid(m, 'c') };
  assert.ok(p.x < r.x, 'ブロックの四角の外の点');
  assert.equal(at(m, p), 'c');
  assert.equal(at(m, { x: r.x - 16 + 1, y: mid(m, 'c') + 10 }), 'c');
});

test('D0007-AC-02: 2本差さっているタップの、上のコンセント・下のコンセント・そのあいだのどこで離しても差さる', () => {
  const m = sample(), r = blockRect(m, 'b');
  const ins = layoutWires(m).filter((w) => w.to === 'b' && w.kind !== 'return');
  assert.equal(ins.length, 2);
  const ys = ins.map((w) => w.points.at(-1)!.y).sort((p, q) => p - q);
  for (const y of [ys[0]!, ys[1]!, (ys[0]! + ys[1]!) / 2, ys[0]! - 10, ys[1]! + 10]) {
    assert.equal(at(m, { x: r.x - 16 + 6, y }), 'b', `y=${y}`);
  }
});

test('D0007-AC-03: ブロックの四角の中で離すと、今までどおりそのブロック（段・並列の枠・終わり）', () => {
  const m = sample();
  for (const id of ['a', 'c', END]) {
    const r = blockRect(m, id);
    assert.equal(at(m, { x: r.x + r.w / 2, y: r.y + r.h / 2 }), id, id);
  }
  // 枠の中でも、段の無い所なら枠
  const f = blockRect(m, 'F');
  assert.equal(at(m, { x: f.x + f.w - 10, y: f.y + f.h - 10 }), 'F');
});

test('D0007-AC-04: 並列の枠のコンセントの上で離すと、その枠に差さる', () => {
  const m = sample(), f = blockRect(m, 'F');
  assert.equal(at(m, { x: f.x - 16 + 7, y: mid(m, 'F') }), 'F');
});

test('D0007-AC-05: 差し戻しのコンセント（ブロックの下か上にあって縦向き）の上で離すと、そのブロックに差さる', () => {
  const m = sample(), r = blockRect(m, 'a');
  const back = layoutWires(m).find((w) => w.kind === 'return' && w.to === 'a')!;
  const tip = back.points.at(-1)!, before = back.points.at(-2)!;
  assert.ok(tip.y > r.y + r.h || tip.y < r.y, 'コンセントはブロックの下か上（四角の外）');
  // 外形は、ケーブルが入ってくる向きを +x にとる（縦向き）。入ってくる向きに 6px・横に 10px の点は外形の中
  const len = Math.hypot(tip.x - before.x, tip.y - before.y), dx = (tip.x - before.x) / len, dy = (tip.y - before.y) / len;
  assert.ok(Math.abs(dx) < 1e-9, '縦向き');
  assert.equal(at(m, { x: tip.x + dx * 6 - dy * 10, y: tip.y + dy * 6 + dx * 10 }), 'a');
  assert.equal(at(m, { x: tip.x + dx * 13, y: tip.y + dy * 13 }), 'a');
});

test('D0007-AC-06: どのブロックにも、どのコンセント（＋ゆとり）にも入らない所では null。ゆとりの 1px 外でも null', () => {
  const m = sample(), r = blockRect(m, 'c');
  assert.equal(at(m, { x: 700, y: 1500 }), null);
  // c の空きのコンセントの左の縁は r.x − 17。ゆとり 8 の 1px 外
  assert.equal(at(m, { x: r.x - 17 - 9, y: mid(m, 'c') }, 8), null);
});

test('D0007-AC-07: コンセントのまわりのゆとりの中なら差さる。ゆとりが 0 なら外形の中だけ', () => {
  const m = sample(), r = blockRect(m, 'c');
  const p = { x: r.x - 17 - 5, y: mid(m, 'c') };
  assert.equal(at(m, p, 8), 'c');
  assert.equal(at(m, p, 0), null);
  assert.equal(at(m, { x: r.x - 16 + 7, y: mid(m, 'c') + 12 + 6 }, 8), 'c');
  assert.equal(at(m, { x: r.x - 16 + 7, y: mid(m, 'c') + 12 + 6 }, 0), null);
});

test('D0007-AC-08: 抜いて持ち上げたケーブルの、元のコンセントで離すと元のブロック（差し直しは起きない）', () => {
  const m = sample();
  const w = layoutWires(m).find((x) => x.from === 'a' && x.to === 'b')!;
  const tip = w.points.at(-1)!;
  assert.equal(at(m, { x: tip.x + 5, y: tip.y }), 'b');
});

test('D0007-AC-09: ほかのブロックの四角とコンセントが重なる所では、コンセントのブロックに差す', () => {
  const m = sample();
  // g を c のすぐ左に置き、g の四角が c のコンセントにかぶさるようにする
  m.stages.push(stage('g', 'research', 900 - blockSize('research').w + 10, 600));
  const r = blockRect(m, 'c'), p = { x: r.x - 16 + 4, y: mid(m, 'c') };
  const g = blockRect(m, 'g');
  assert.ok(p.x > g.x && p.x < g.x + g.w && p.y > g.y && p.y < g.y + g.h, 'g の四角の中の点');
  assert.equal(at(m, p), 'c');
});

test('D0007-AC-10: 始まりにはコンセントが無い（左で離しても始まりにならない）。四角の中なら今までどおり始まり', () => {
  const m = sample(), r = blockRect(m, 'start');
  assert.equal(at(m, { x: r.x - 16 + 7, y: r.y + r.h / 2 }), null);
  assert.equal(at(m, { x: r.x + r.w / 2, y: r.y + r.h / 2 }), 'start');
});
