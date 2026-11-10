// 実行中の記録（D0078。app/runActive.ts）。AC-19・29。メモリだけ。パイプのフォルダごと。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { createActiveRuns } from './runActive.ts';

const A = '/work/app/.pipe-in/pipes/pipe-in-a';
const B = '/work/app/.pipe-in/pipes/pipe-in-b';

test('D0078-AC-19: start した pipeDir は isRunning が true で、同じ pipeDir への2回目の start は false（記録は変わらない）', () => {
  const runs = createActiveRuns();
  assert.equal(runs.isRunning(A), false);
  assert.equal(runs.start(A, '1'), true);
  assert.equal(runs.isRunning(A), true);
  assert.equal(runs.start(A, '2'), false);
  assert.equal(runs.isRunning(A), true);
  assert.equal(runs.release('2'), null, '断られた id は記録に無い');
  assert.equal(runs.isRunning(A), true);
});

test('D0078-AC-19: 別のパイプのフォルダは別々に実行中になれる（同時に流せる）', () => {
  const runs = createActiveRuns();
  assert.equal(runs.start(A, '1'), true);
  assert.equal(runs.isRunning(B), false);
  assert.equal(runs.start(B, '2'), true);
  assert.equal(runs.isRunning(A), true);
  assert.equal(runs.isRunning(B), true);
});

test('D0078-AC-29: release は runId が合う記録だけを外してそのフォルダを返し、2回目は null。外れたあとは isRunning が false', () => {
  const runs = createActiveRuns();
  runs.start(A, '1');
  runs.start(B, '2');
  assert.equal(runs.release('1'), A);
  assert.equal(runs.isRunning(A), false);
  assert.equal(runs.isRunning(B), true, '別の記録は外れない');
  assert.equal(runs.release('1'), null, '2回目の知らせは何もしない');
  assert.equal(runs.isRunning(B), true);
  assert.equal(runs.release('2'), B);
  assert.equal(runs.isRunning(B), false);
});

test('D0078-AC-29: 知らない id の release は null で、何も外さない', () => {
  const runs = createActiveRuns();
  runs.start(A, '1');
  assert.equal(runs.release('99'), null);
  assert.equal(runs.release(''), null);
  assert.equal(runs.isRunning(A), true);
});

test('D0078-AC-29: 外れたあとは、同じ pipeDir をもう一度 start できる', () => {
  const runs = createActiveRuns();
  assert.equal(runs.start(A, '1'), true);
  assert.equal(runs.release('1'), A);
  assert.equal(runs.start(A, '3'), true);
  assert.equal(runs.release('1'), null, '古い id では新しい記録を外せない');
  assert.equal(runs.isRunning(A), true);
});

test('D0078-AC-19: 鍵は path.resolve(pipeDir)。末尾の区切りや ./ の付いた同じフォルダは同じ記録になる', () => {
  const runs = createActiveRuns();
  assert.equal(runs.start(A, '1'), true);
  assert.equal(runs.isRunning(`${A}/`), true);
  assert.equal(runs.isRunning(path.resolve(A, '..', 'pipe-in-a')), true);
  assert.equal(runs.start(`${A}/./`, '2'), false);
});

test('D0078-AC-19: createActiveRuns は呼ぶたびに別の記録（モジュールの共有の状態を持たない）', () => {
  const one = createActiveRuns();
  const two = createActiveRuns();
  one.start(A, '1');
  assert.equal(two.isRunning(A), false);
});
