// 知らせの対象の行の絞り込みと、設定の値の読み（D0045）。AC-10〜12・15。vscode を使わない純粋な関数。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { notifyEnabled, planWaitingNotice } from './notifyWaiting.ts';
import { makeRunKey } from '../domain/runs.ts';
import type { RunRow, RunState } from '../domain/runList.ts';

function row(id: string, state: RunState, over: Partial<RunRow> = {}): RunRow {
  return {
    key: makeRunKey('here', id),
    session: `s-${id}`,
    pipe: 'dev',
    branch: null,
    other: false,
    previous: false,
    stage: '設計',
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
const base = { selected: key('none'), panelVisible: false, enabled: true };

test('D0045-AC-10: 新しく確認待ちで設定が true なら、対象の行が残る', () => {
  const rows = [row('a', 'waiting')];
  const out = planWaitingNotice({ ...base, prev: [row('a', 'running')], rows });
  assert.deepEqual(out.map((x) => x.key), [key('a')]);
});

test('D0045-AC-10: 新しく確認待ちになった行が無ければ、空', () => {
  const rows = [row('a', 'waiting')];
  assert.deepEqual(planWaitingNotice({ ...base, prev: rows, rows }), []);
});

test('D0045-AC-11: enabled が false なら、新しく確認待ちになっても空', () => {
  const rows = [row('a', 'waiting')];
  assert.deepEqual(planWaitingNotice({ ...base, enabled: false, prev: [row('a', 'running')], rows }), []);
});

test('D0045-AC-11: notifyEnabled は false だけ false。未設定・null・"false"・0・オブジェクトなど型が違う値は true（既定）', () => {
  assert.equal(notifyEnabled(false), false);
  assert.equal(notifyEnabled(true), true);
  for (const v of [undefined, null, 'false', '', 0, 1, {}, [], [false]]) {
    assert.equal(notifyEnabled(v), true, String(JSON.stringify(v)));
  }
});

test('D0045-AC-12: パネルが見えていて selected と同じ key の行は外れ、ほかの行は残る', () => {
  const rows = [row('a', 'waiting'), row('b', 'waiting')];
  const out = planWaitingNotice({ ...base, panelVisible: true, selected: key('a'), prev: [], rows });
  assert.deepEqual(out.map((x) => x.key), [key('b')]);
});

test('D0045-AC-12: パネルが見えていて、対象が selected の1行だけなら空', () => {
  const rows = [row('a', 'waiting')];
  assert.deepEqual(planWaitingNotice({ ...base, panelVisible: true, selected: key('a'), prev: [], rows }), []);
});

test('D0045-AC-12: パネルが見えていなければ、selected の行も外さない', () => {
  const rows = [row('a', 'waiting')];
  const out = planWaitingNotice({ ...base, panelVisible: false, selected: key('a'), prev: [], rows });
  assert.deepEqual(out.map((x) => x.key), [key('a')]);
});

test('D0045-AC-12: パネルが見えていても、selected と違う行は外さない', () => {
  const rows = [row('a', 'waiting')];
  const out = planWaitingNotice({ ...base, panelVisible: true, selected: key('z'), prev: [], rows });
  assert.deepEqual(out.map((x) => x.key), [key('a')]);
});

test('D0045-AC-15: prev が null（基準が無い）なら、確認待ちの行があっても対象なし', () => {
  assert.deepEqual(planWaitingNotice({ ...base, prev: null, rows: [row('a', 'waiting')] }), []);
});

test('D0045-AC-06: 別の worktree の行も、いまの work_dir の行と同じに対象になる', () => {
  const other = row('x', 'waiting', { other: true, key: makeRunKey('main', 'x') });
  const out = planWaitingNotice({ ...base, prev: [], rows: [other] });
  assert.deepEqual(out.map((x) => x.key), [other.key]);
});

test('D0045-AC-19: 渡した配列を変えない', () => {
  const prev = [row('a', 'running')];
  const rows = [row('a', 'waiting')];
  const before = JSON.stringify([prev, rows]);
  planWaitingNotice({ ...base, prev, rows });
  assert.equal(JSON.stringify([prev, rows]), before);
});
