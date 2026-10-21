// 止まっているかもしれない実行の印（D0021）：実行の一覧の行の quietSec。
// 行の quietSec は、同じ写しから作った PipelineView.quietSec を元にそろう（動いている行だけ。ほかの状態は null）。
// 「出ない側」の確かめには、必ず対照（出る条件だけを足した同じ写し）を同じテストの中で確かめる（決定の記録 D0021）。
// quietSec はテスト先行のときは型に無かったので、読み取り用の関数で取り出す（無ければ undefined のまま返す）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { summarizeRun } from './runList.ts';
import type { RunRow } from './runList.ts';
import type { PipelineView, WorkDirSnapshot } from './pipelineView.ts';
import { logText, promptLine, resultLine, snapshot, stageRunEntry, stateJson } from '../test/fixtures.ts';
import { BASE_AT, RUNNING_UPDATED_AT, STARTED_AT, clockAt, waitingSnapshot } from '../test/liveFixtures.ts';
import {
  BROKEN_STATE_KINDS,
  FINAL_VALUES,
  NO_MTIME_KINDS,
  QUIET_OVER_SEC,
  RESUMED_NEW_AGO_SEC,
  abandonedSnapshot,
  ancientSnapshot,
  brokenStateSnapshot,
  futureSnapshot,
  hostileSnapshot,
  mtimeAgo,
  noMtimeOnRunningSnapshot,
  resumedSnapshot,
  staleParts,
  staleSnapshot,
  summarizeInput,
  unknownStageSnapshot,
  withAllMtimes,
} from '../test/staleFixtures.ts';

const quietOf = (x: object): unknown => (x as { quietSec?: unknown }).quietSec;

/** 動いている帯の quietSec（帯が無い・項目が無いときは null）。 */
function bandQuiet(view: PipelineView): unknown {
  const row = view.gantt.rows.find((r) => r.run?.live === true);
  return row?.run == null ? null : (quietOf(row.run) ?? null);
}

/** 同じ写し・同じ「今」から作った行と図の状態の quietSec。 */
function quietParts(snap: WorkDirSnapshot, nowSec = 0): { row: unknown; view: unknown; band: unknown; state: RunRow['state'] } {
  const { row, view } = staleParts(snap, nowSec);
  return { row: quietOf(row), view: quietOf(view), band: bandQuiet(view), state: row.state };
}

/** 1 行にする（「今」は BASE から nowSec 秒後）。 */
const rowOf = (snap: WorkDirSnapshot, nowSec = 0): RunRow => staleParts(snap, nowSec).row;

// ---- AC-04：動いている行の quietSec は、図の状態（view・節・帯）と同じ ----

const SAME_CASES: readonly (readonly [string, () => WorkDirSnapshot, number, number])[] = [
  ['83.9 秒前（切り捨てて 83）', () => staleSnapshot({ quietSec: 83.9 }), 0, 83],
  ['612 秒前', () => staleSnapshot(), 0, 612],
  ['83 秒前の記録を、30 秒後に見る（113）', () => staleSnapshot({ quietSec: 83 }), 30, 113],
  ['パイプ（diagrams）の動いている段', () => hostileSnapshot(), 0, 612],
  ['全ログが古い放置された実行（最新は 700 秒前）', () => abandonedSnapshot(), 0, 700],
  ['再開した実行（最新は 5 秒前）', resumedSnapshot, 0, 5],
];

for (const [label, make, nowSec, expected] of SAME_CASES) {
  test(`D0021-AC-04: 同じ写しから作った動いている行の quietSec は、view・動いている帯と同じ値になる：${label}`, () => {
    const parts = quietParts(make(), nowSec);
    assert.equal(parts.state, 'running');
    assert.deepEqual({ row: parts.row, view: parts.view, band: parts.band }, { row: expected, view: expected, band: expected });
  });
}

test('D0021-AC-04: 段の一覧に無い名前の動いているログ（節が作られない）でも、行・view・動いている帯の quietSec は同じ数になる', () => {
  const parts = quietParts(unknownStageSnapshot({ quietSec: 612 }));
  assert.equal(parts.state, 'running');
  assert.deepEqual({ row: parts.row, view: parts.view, band: parts.band }, { row: 612, view: 612, band: 612 });
});

test('D0021-AC-04: 行は「今」を進めると進んだ秒だけ quietSec が増える（記録の更新時刻は変わらない）', () => {
  const snap = staleSnapshot({ quietSec: 83 });
  assert.equal(quietOf(rowOf(snap, 0)), 83);
  assert.equal(quietOf(rowOf(snap, 30)), 113);
});

// ---- AC-05：時計のずれ ----

test('D0021-AC-05: 更新時刻が今の 5 分先でも、行の quietSec は 0（負にならない。対照：過去の時刻なら秒が出る）', () => {
  const row = rowOf(futureSnapshot());
  assert.equal(row.state, 'running');
  assert.equal(quietOf(rowOf(staleSnapshot({ quietSec: 5 }))), 5);
  assert.equal(quietOf(row), 0);
});

// ---- AC-06：動いているログの更新時刻が読めない ----

for (const kind of NO_MTIME_KINDS) {
  test(`D0021-AC-06: 動いているログの mtimeMs が「${kind}」なら、ほかのログの時刻・at・updated_at があっても、行の quietSec は null（対照：数なら数）`, () => {
    const row = rowOf(noMtimeOnRunningSnapshot(kind));
    assert.equal(row.state, 'running');
    // 対照：動いているログの mtimeMs が数なら、全ログの最新（ほかのログの 10 秒前）
    assert.equal(quietOf(rowOf(noMtimeOnRunningSnapshot('number'))), 10);
    assert.equal(quietOf(row), null);
  });
}

// ---- AC-07：動いている以外の行は null ----

/** 結果の行のあるログだけの「待ち（段の合間）」の写し。 */
function idleSnapshot(): WorkDirSnapshot {
  const snap = snapshot({
    stateJson: stateJson({
      runs: [stageRunEntry({ stage: 'requirements', seq: 1, durationSec: 30 })],
      startedAt: STARTED_AT,
      updatedAt: RUNNING_UPDATED_AT,
    }),
    stageLogs: [{ fileName: '01_requirements.jsonl', text: logText([promptLine('requirements', BASE_AT), resultLine()]) }],
    artifacts: { '00_input.md': 'メモ' },
  });
  return withAllMtimes(snap, mtimeAgo(QUIET_OVER_SEC));
}

const NOT_RUNNING: readonly (readonly [string, () => WorkDirSnapshot, RunRow['state']])[] = [
  ['確認待ち', () => withAllMtimes(waitingSnapshot(), mtimeAgo(QUIET_OVER_SEC)), 'waiting'],
  ['待ち（段の合間）', idleSnapshot, 'idle'],
  ['終わった（final あり・ログが残る）', () => staleSnapshot({ final: 'PASSED' }), 'done'],
  ['前の実行（archive/）', () => staleSnapshot({ previous: true }), 'done'],
];

for (const [label, make, state] of NOT_RUNNING) {
  test(`D0021-AC-07: ${label}の行の quietSec は null（対照：同じ作りで動いている行は数）`, () => {
    const row = rowOf(make());
    assert.equal(row.state, state);
    const control = rowOf(staleSnapshot());
    assert.equal(control.state, 'running');
    assert.equal(quietOf(control), QUIET_OVER_SEC);
    assert.equal(quietOf(row), null);
  });
}

test('D0021-AC-07: 記録なし（空の写し）の行の quietSec は null（対照：動いている写しは数）', () => {
  const row = rowOf(snapshot());
  assert.equal(row.state, 'idle');
  assert.equal(quietOf(rowOf(staleSnapshot())), QUIET_OVER_SEC);
  assert.equal(quietOf(row), null);
});

// ---- AC-08：「今」を引数で受ける純粋な関数 ----

test('D0021-AC-08: 行の quietSec は時計を読まない（Date.now を読むと投げる関数に替えても同じ結果）', () => {
  const snap = staleSnapshot();
  const expected = summarizeRun(summarizeInput(snap), clockAt(0));
  const realNow = Date.now;
  Date.now = () => {
    throw new Error('時計を読んだ');
  };
  try {
    assert.deepStrictEqual(summarizeRun(summarizeInput(snap), clockAt(0)), expected);
  } finally {
    Date.now = realNow;
  }
  assert.equal(quietOf(expected), QUIET_OVER_SEC);
});

test('D0021-AC-08: 同じ写しと同じ「今」からは何度組み立てても同じ行で、写しを書き換えない（quietSec が出ている前提）', () => {
  const snap = staleSnapshot();
  const before = JSON.parse(JSON.stringify(snap));
  const a = summarizeRun(summarizeInput(snap), clockAt(0));
  const b = summarizeRun(summarizeInput(snap), clockAt(0));
  assert.deepStrictEqual(a, b);
  assert.deepStrictEqual(snap, before);
  assert.equal(quietOf(a), QUIET_OVER_SEC);
  assert.equal(quietOf(summarizeRun(summarizeInput(snap), clockAt(1))), QUIET_OVER_SEC + 1, '「今」が違えば出力も違う');
});

for (const [label, nowMs] of [
  ['NaN', Number.NaN],
  ['正の無限大', Number.POSITIVE_INFINITY],
  ['負の無限大', Number.NEGATIVE_INFINITY],
] as const) {
  test(`D0021-AC-08: 時計の値が壊れていて（${label}）も行は例外を投げず、quietSec は null（対照：有限の時計なら数）`, () => {
    const snap = staleSnapshot();
    let row: RunRow | undefined;
    assert.doesNotThrow(() => {
      row = summarizeRun(summarizeInput(snap), { nowMs, localOffsetMin: 0 });
    });
    assert.equal(row!.state, 'running');
    assert.equal(quietOf(summarizeRun(summarizeInput(snap), clockAt(0))), QUIET_OVER_SEC);
    assert.equal(quietOf(row!), null);
  });
}

// ---- AC-44：中断した古い途中のログと、再開後の新しいログ ----

test('D0021-AC-44: 古い途中のログ（3 日前）と再開後の新しいログ（5 秒前）が並ぶ写しでは、行の動いている段は古い方のまま、quietSec は 5', () => {
  const row = rowOf(resumedSnapshot());
  assert.equal(row.state, 'running');
  assert.equal(row.stage, '実装（1 回目）', '動いている段の判定は今のまま（通し番号が大きい古い方）');
  assert.equal(quietOf(row), RESUMED_NEW_AGO_SEC);
  assert.equal(RESUMED_NEW_AGO_SEC, 5);
});

// ---- AC-45：放置された実行・1 つでも新しいログがある ----

const ABANDONED_CASES: readonly (readonly [string, Parameters<typeof abandonedSnapshot>[0], number])[] = [
  ['全ログが目安（600）より古く、終わったログが最新（700 秒前）', {}, 700],
  ['全ログが目安より古く、動いているログが最新（700 秒前）', { runningIsLatest: true }, 700],
  ['1 つだけ目安より新しいログがある（100 秒前）', { latestAgoSec: 100 }, 100],
];

for (const [label, params, expected] of ABANDONED_CASES) {
  test(`D0021-AC-45: ${label}と、行の quietSec はその最新の更新時刻から決まる（${expected}）`, () => {
    const row = rowOf(abandonedSnapshot(params));
    assert.equal(row.state, 'running');
    assert.equal(quietOf(row), expected);
  });
}

// ---- AC-46：final がある run の行には印を出さない ----

for (const final of FINAL_VALUES) {
  test(`D0021-AC-46: final=${final} の行は「終わった」で、動いているログが残っても quietSec は null（対照：final を外すと動いている行で数）`, () => {
    const row = rowOf(staleSnapshot({ final }));
    assert.equal(row.state, 'done');
    const control = rowOf(staleSnapshot());
    assert.equal(control.state, 'running');
    assert.equal(quietOf(control), QUIET_OVER_SEC);
    assert.equal(quietOf(row), null);
  });
}

// ---- AC-47：前の実行（archive/）の行には印を出さない ----

test('D0021-AC-47: 前の実行（previous: true）の行は「終わった」で、final が無く動いているログに更新時刻があっても quietSec は null（対照：previous を外すと数）', () => {
  const live = staleSnapshot();
  const row = rowOf(staleSnapshot({ previous: true }));
  assert.equal(row.previous, true);
  assert.equal(row.state, 'done');
  const control = rowOf(live);
  assert.equal(control.state, 'running');
  assert.equal(quietOf(control), QUIET_OVER_SEC);
  assert.equal(quietOf(row), null);
});

// ---- AC-48 ②：7 日の上限 ----

test('D0021-AC-48: 1980 年の更新時刻でも、行の quietSec は 604800（7 日）で頭打ち', () => {
  const row = rowOf(ancientSnapshot());
  assert.equal(row.state, 'running');
  assert.equal(quietOf(row), 604800);
});

for (const [ago, expected] of [
  [604_799, 604_799],
  [604_800, 604_800],
  [604_801, 604_800],
] as const) {
  test(`D0021-AC-48: 更新が ${ago} 秒前なら、行の quietSec は ${expected}（7 日が上限）`, () => {
    assert.equal(quietOf(rowOf(staleSnapshot({ quietSec: ago }))), expected);
  });
}

// ---- AC-49：state.json が読めない run には印を出さない ----

for (const kind of BROKEN_STATE_KINDS) {
  test(`D0021-AC-49: state.json が「${kind}」の run の行は、動いているログに更新時刻があっても quietSec が null（対照：正しい state.json なら数）`, () => {
    const row = rowOf(brokenStateSnapshot(kind));
    assert.equal(row.state, 'running', '動いているログは拾われるので、行は「動いている」のまま');
    assert.equal(quietOf(rowOf(staleSnapshot())), QUIET_OVER_SEC);
    assert.equal(quietOf(row), null);
  });
}
