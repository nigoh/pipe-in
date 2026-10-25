// 新しく確認待ちになった行の判断（D0046）。AC-01〜07。純粋な関数なので、行を作って渡すだけ。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { newlyWaitingKeys } from './waitingNotice.ts';
import { makeRunKey } from './runs.ts';
import type { RunRow, RunState } from './runList.ts';

function row(id: string, state: RunState, over: Partial<RunRow> = {}): RunRow {
  return {
    key: makeRunKey('here', id),
    session: `s-${id}`,
    pipe: 'dev',
    branch: null,
    other: false,
    previous: false,
    stage: '要件定義',
    state,
    result: null,
    sessionId: null,
    costText: '—',
    updatedText: '—',
    updatedDate: '—',
    updatedMs: null,
    elapsed: null,
    waitingSec: null,
    ...over,
  };
}

const key = (id: string): string => makeRunKey('here', id);

test('D0046-AC-01: 前の一覧に無かった行が今は確認待ちなら key を返す', () => {
  assert.deepEqual(newlyWaitingKeys([], [row('a', 'waiting')]), [key('a')]);
  assert.deepEqual(newlyWaitingKeys([row('b', 'running')], [row('b', 'running'), row('a', 'waiting')]), [key('a')]);
});

test('D0046-AC-01: 前は確認待ちでなかった行（動いている・待ち）が今は確認待ちなら key を返す', () => {
  assert.deepEqual(newlyWaitingKeys([row('a', 'running')], [row('a', 'waiting')]), [key('a')]);
  assert.deepEqual(newlyWaitingKeys([row('a', 'idle')], [row('a', 'waiting')]), [key('a')]);
});

test('D0046-AC-01: 複数あるときは今の一覧の並び順で返す', () => {
  const next = [row('b', 'waiting'), row('a', 'waiting')];
  assert.deepEqual(newlyWaitingKeys([], next), [key('b'), key('a')]);
});

test('D0046-AC-02: 前も今も確認待ちの行は返さない', () => {
  assert.deepEqual(newlyWaitingKeys([row('a', 'waiting')], [row('a', 'waiting')]), []);
});

test('D0046-AC-02: 確認待ちから動く・待ち・終わるに変わった行は返さない', () => {
  for (const to of ['running', 'idle', 'done'] as const) {
    assert.deepEqual(newlyWaitingKeys([row('a', 'waiting')], [row('a', to)]), [], to);
  }
});

test('D0046-AC-03: 確認待ち → 動く → 確認待ちと順に渡すと、2回目の確認待ちで返す', () => {
  const w = [row('a', 'waiting')];
  const r = [row('a', 'running')];
  assert.deepEqual(newlyWaitingKeys(null, w), []);
  assert.deepEqual(newlyWaitingKeys(w, r), []);
  assert.deepEqual(newlyWaitingKeys(r, w), [key('a')]);
  assert.deepEqual(newlyWaitingKeys(w, w), []);
});

test('D0046-AC-04: previous（archive/）の行は、確認待ちに見えても返さない', () => {
  assert.deepEqual(newlyWaitingKeys([], [row('a', 'waiting', { previous: true })]), []);
  assert.deepEqual(newlyWaitingKeys([row('a', 'running', { previous: true })], [row('a', 'waiting', { previous: true })]), []);
});

test('D0046-AC-04: done の行は、previous でなくても返さない。ほかの確認待ちの行は返す', () => {
  assert.deepEqual(newlyWaitingKeys([], [row('a', 'done')]), []);
  assert.deepEqual(newlyWaitingKeys([], [row('a', 'done'), row('b', 'waiting')]), [key('b')]);
});

test('D0046-AC-05: prev が null（基準が無い）のとき、確認待ちの行があっても何も返さない', () => {
  assert.deepEqual(newlyWaitingKeys(null, [row('a', 'waiting'), row('b', 'waiting')]), []);
  assert.deepEqual(newlyWaitingKeys(null, []), []);
});

test('D0046-AC-06: 別の worktree の行（other）も、いまの work_dir の行と同じに返す', () => {
  const other = row('x', 'waiting', { other: true, key: makeRunKey('main', 'x') });
  assert.deepEqual(newlyWaitingKeys([], [other]), [other.key]);
  assert.deepEqual(newlyWaitingKeys([{ ...other, state: 'running' }], [other]), [other.key]);
  assert.deepEqual(newlyWaitingKeys([other], [other]), []);
});

test('D0046-AC-06: 別の worktree の行が一覧に無い（showOtherWorktrees が false）ときは、返さない', () => {
  const here = row('a', 'running');
  assert.deepEqual(newlyWaitingKeys([here], [here]), []);
});

test('D0046-AC-07: 空の一覧でも例外を出さない', () => {
  assert.deepEqual(newlyWaitingKeys([], []), []);
  assert.deepEqual(newlyWaitingKeys([row('a', 'waiting')], []), []);
});

test('D0046-AC-07: 行の key が重複しても、返す key は重複しない', () => {
  const next = [row('a', 'waiting'), row('a', 'waiting'), row('b', 'waiting')];
  assert.deepEqual(newlyWaitingKeys([], next), [key('a'), key('b')]);
});

test('D0046-AC-07: stage・session が空でも例外を出さず、返す', () => {
  assert.deepEqual(newlyWaitingKeys([], [row('a', 'waiting', { stage: '', session: '' })]), [key('a')]);
});

test('D0046-AC-07: 渡した配列を変えない', () => {
  const prev = [row('a', 'running')];
  const next = [row('a', 'waiting')];
  const before = JSON.stringify([prev, next]);
  newlyWaitingKeys(prev, next);
  assert.equal(JSON.stringify([prev, next]), before);
});
