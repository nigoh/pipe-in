// 元に戻す・やり直し：1手ごとにモデルの写し（文字列）を積む。同じ欄に続けて打った分は1手にまとめる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { canRedo, canUndo, createHistory, jump, record, redo, undo } from './editHistory.ts';

test('AC-63: 戻してやり直すと、同じ形になる', () => {
  const h = createHistory('s0');
  assert.equal(canUndo(h), false);
  record(h, 'A を置いた', 's1');
  record(h, 'B を置いた', 's2');
  assert.equal(undo(h), 's1');
  assert.equal(undo(h), 's0');
  assert.equal(undo(h), null);
  assert.equal(canRedo(h), true);
  assert.equal(redo(h), 's1');
  assert.equal(redo(h), 's2');
  assert.equal(redo(h), null);
});

test('AC-63: 戻したあとに新しく操作すると、やり直しの分は消える', () => {
  const h = createHistory('s0');
  record(h, 'A', 's1');
  record(h, 'B', 's2');
  undo(h);
  record(h, 'C', 's3');
  assert.equal(canRedo(h), false);
  assert.deepEqual(h.entries.map((e) => e.snap), ['s0', 's1', 's3']);
});

test('AC-63: 同じ欄に続けて打った分は1手にまとまる。別の操作をはさむと分かれる', () => {
  const h = createHistory('s0');
  record(h, '頼むことを書き換えた', 'p1', 'stage:a:b-prompt');
  record(h, '頼むことを書き換えた', 'p2', 'stage:a:b-prompt');
  record(h, '頼むことを書き換えた', 'p3', 'stage:a:b-prompt');
  assert.equal(h.entries.length, 2);
  assert.equal(undo(h), 's0');
  redo(h);
  record(h, 'A を動かした', 'm1');
  record(h, '頼むことを書き換えた', 'p4', 'stage:a:b-prompt');
  assert.equal(h.entries.length, 4);
});

test('AC-63: 形が変わらない操作は積まない', () => {
  const h = createHistory('s0');
  assert.equal(record(h, '押しただけ', 's0'), false);
  assert.equal(h.entries.length, 1);
});

test('AC-63: 手の数には上限があり、古いほうから捨てる', () => {
  const h = createHistory('s0', '開いたとき', 3);
  for (let i = 1; i <= 5; i++) record(h, `${i}`, `s${i}`);
  assert.equal(h.entries.length, 3);
  assert.deepEqual(h.entries.map((e) => e.snap), ['s3', 's4', 's5']);
  assert.equal(undo(h), 's4');
  assert.equal(undo(h), 's3');
  assert.equal(undo(h), null);
});

test('AC-64: 操作の一覧の時点を選ぶとその形になり、そのあとでもやり直しで先に戻れる', () => {
  const h = createHistory('s0', '開いたとき');
  record(h, 'A', 's1');
  record(h, 'B', 's2');
  record(h, 'C', 's3');
  assert.equal(jump(h, 1), 's1');
  assert.equal(h.at, 1);
  assert.equal(redo(h), 's2');
  assert.equal(jump(h, 3), 's3');
  assert.equal(jump(h, 9), null);
  assert.equal(h.entries[0]!.label, '開いたとき');
});
