// 止まっているかもしれない実行の印（D0021）：図の状態の quietSec（動いている段の節・PipelineView・時系列の動いている帯）。
// 印の元は PipelineView.quietSec の 1 つで、節・帯・行はどれもそこから取る（決定の記録 D0021）。
// 「出ない側」の確かめには、必ず対照（出る条件だけを足した同じ写し）を同じテストの中で確かめる（決定の記録 D0021）。
// 新しい項目（quietSec・isReadableState）は、テスト先行のときに「まだ無い」ことで落ちるように、読み取り用の関数と動的 import で読む（実装後は型に入っている）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPipelineView } from './pipelineView.ts';
import type { PipelineNode, PipelineView, WorkDirSnapshot } from './pipelineView.ts';
import { logText, promptLine, resultLine, snapshot, stageRunEntry, stateJson } from '../test/fixtures.ts';
import { BASE_AT, RUNNING_UPDATED_AT, STARTED_AT, clockAt, viewAt, waitingSnapshot } from '../test/liveFixtures.ts';
import {
  BAD_MTIME_VALUES,
  BROKEN_STATE_KINDS,
  FINAL_VALUES,
  LOG_REQUIREMENTS,
  NO_MTIME_KINDS,
  QUIET_OVER_SEC,
  RESUMED_NEW_AGO_SEC,
  RESUMED_OLD_AGO_SEC,
  abandonedSnapshot,
  ancientSnapshot,
  brokenStateSnapshot,
  futureSnapshot,
  hostileSnapshot,
  mtimeAgo,
  noMtimeOnRunningSnapshot,
  resumedSnapshot,
  staleGanttSnapshot,
  staleSnapshot,
  unknownStageSnapshot,
  withAllMtimes,
  withMtimes,
  withPrevious,
} from '../test/staleFixtures.ts';

const runRecord = () => import('./runRecord.ts');

// ---- 読み取り用の道具（テスト先行のときは quietSec が型に無かった。無ければ undefined のまま返す） ----

const quietOf = (x: object): unknown => (x as { quietSec?: unknown }).quietSec;

function nodeOf(view: PipelineView, id: string): PipelineNode {
  const found = view.nodes.find((n) => n.id === id);
  assert.ok(found, `節 ${id} があること`);
  return found;
}

/** 時系列の、動いている帯を持つ行。 */
const liveRow = (view: PipelineView) => view.gantt.rows.find((r) => r.run?.live === true);

interface Surfaces {
  view: unknown;
  node: unknown;
  /** 動いている帯の quietSec（帯が無い・項目が無いときは null）。動いている行そのものが無いときは 'no-row' */
  gantt: unknown;
}

/** 印の元を取る 3 つの面（view・節・帯）の quietSec。 */
function surfaces(view: PipelineView, nodeId = 'design'): Surfaces {
  const row = liveRow(view);
  return {
    view: quietOf(view),
    node: quietOf(nodeOf(view, nodeId)),
    gantt: row === undefined || row.run === null ? 'no-row' : (quietOf(row.run) ?? null),
  };
}

/** 3 つの面が同じ値になる。 */
const same = (n: number | null): Surfaces => ({ view: n, node: n, gantt: n });

// ---- AC-04：動いている段の節・view・帯の quietSec ----

const QUIET_CASES: readonly (readonly [number, number])[] = [
  [83.9, 83],
  [0, 0],
  [1, 1],
  [599, 599],
  [612, 612],
  [3600, 3600],
];

for (const [ago, expected] of QUIET_CASES) {
  test(`D0021-AC-04: 動いている段の節・view・帯の quietSec は「今 − 全ログの最新の更新時刻」の秒（切り捨て）で同じ値（${ago} 秒前 → ${expected}）`, () => {
    const view = viewAt(staleSnapshot({ quietSec: ago }), 0);
    assert.equal(view.runningStage, 'design');
    assert.equal(nodeOf(view, 'design').status, 'running');
    assert.deepEqual(surfaces(view), same(expected));
  });
}

test('D0021-AC-04: 「今」が進むと quietSec は進んだ秒だけ増える（記録の更新時刻は変わらない）', () => {
  const snap = staleSnapshot({ quietSec: 83 });
  assert.deepEqual(surfaces(viewAt(snap, 0)), same(83));
  assert.deepEqual(surfaces(viewAt(snap, 30)), same(113));
});

for (const offset of [540, -300]) {
  test(`D0021-AC-04: 手元のずれ（${offset} 分）が違っても quietSec は同じ（更新時刻は UTC の絶対の時刻）`, () => {
    assert.deepEqual(surfaces(viewAt(staleSnapshot(), 0)), same(QUIET_OVER_SEC));
    assert.deepEqual(surfaces(viewAt(staleSnapshot(), 0, offset)), same(QUIET_OVER_SEC));
  });
}

test('D0021-AC-04: パイプ（diagrams）の動いている段の節にも quietSec が入り、view・帯と同じ値', () => {
  const view = viewAt(hostileSnapshot({ quietSec: 612 }), 0);
  assert.equal(nodeOf(view, 'draw').status, 'running');
  assert.deepEqual(surfaces(view, 'draw'), same(612));
});

test('D0021-AC-04: 段の一覧に無い名前の動いているログ（節が作られない）でも、view と動いている帯の quietSec は同じ数になる', () => {
  const view = viewAt(unknownStageSnapshot({ quietSec: 612 }), 0);
  assert.equal(view.runningStage, 'mystery');
  assert.ok(view.nodes.every((n) => n.status !== 'running'), '動いている節は作られない');
  assert.equal(quietOf(view), 612);
  const row = liveRow(view);
  assert.ok(row?.run, '動いている帯はある');
  assert.equal(quietOf(row.run), 612);
});

// ---- AC-05：時計のずれ（更新時刻が今より先） ----

const FUTURE_CASES: readonly (readonly [string, () => WorkDirSnapshot])[] = [
  ['今の 5 分先', futureSnapshot],
  ['今の 1 秒先', () => staleSnapshot({ quietSec: -1 })],
  ['今の 1 日先', () => staleSnapshot({ quietSec: -86_400 })],
];

for (const [label, make] of FUTURE_CASES) {
  test(`D0021-AC-05: 更新時刻が${label}でも、節・view・帯の quietSec は負にならず 0（対照：過去の時刻なら秒が出る）`, () => {
    assert.deepEqual(surfaces(viewAt(staleSnapshot({ quietSec: 5 }), 0)), same(5));
    assert.deepEqual(surfaces(viewAt(make(), 0)), same(0));
  });
}

test('D0021-AC-05: 時系列の帯も、更新時刻が今より先なら quietSec は 0（負にならない）', () => {
  const view = viewAt(staleGanttSnapshot({ quietSec: -300 }), 1000);
  const row = liveRow(view);
  assert.ok(row?.run, '動いている帯はある');
  assert.equal(quietOf(row.run), 0);
});

// ---- AC-06：動いているログの更新時刻が読めない ----

for (const kind of NO_MTIME_KINDS) {
  test(`D0021-AC-06: 動いているログの mtimeMs が「${kind}」なら、ほかのログの時刻・Prompt の at・updated_at があっても、節・view・帯の quietSec は null`, () => {
    const view = viewAt(noMtimeOnRunningSnapshot(kind), 0);
    assert.equal(view.runningStage, 'design');
    assert.equal(nodeOf(view, 'design').runningSec, 0, 'Prompt の at は読める（代わりにはしない）');
    assert.equal(view.elapsed?.live, true, 'started_at・updated_at も読める（代わりにはしない）');
    // 対照：動いているログの mtimeMs が数なら、quietSec は数（全ログの最新＝ほかのログの 10 秒）
    assert.deepEqual(surfaces(viewAt(noMtimeOnRunningSnapshot('number'), 0)), same(10));
    assert.deepEqual(surfaces(view), same(null));
  });
}

// ---- AC-02：読めない更新時刻は「時刻なし」で写しに入り、ほかのログの時刻を巻き込まない ----
// AC-06 の逆の向き：動いているログの時刻は読める（612 秒前）。終わったログの時刻だけが読めない（本来は 10 秒前）。

type Break = (snap: WorkDirSnapshot) => WorkDirSnapshot;

/** 終わったログ（01_requirements）の mtimeMs を value にする。 */
const setFinishedMtime =
  (value: unknown): Break =>
  (snap) =>
    withMtimes(snap, { [LOG_REQUIREMENTS]: value });

/** 終わったログ（01_requirements）の mtimeMs の項目を無くす（古い写し・手で作った写し）。 */
const dropFinishedMtime: Break = (snap) => ({
  ...snap,
  stageLogs: snap.stageLogs.map((log) => {
    if (log.fileName !== LOG_REQUIREMENTS) return log;
    const copy: Record<string, unknown> = { ...log };
    delete copy.mtimeMs;
    return copy as WorkDirSnapshot['stageLogs'][number];
  }),
});

const UNREADABLE_ON_FINISHED: readonly (readonly [string, Break])[] = [
  ...BAD_MTIME_VALUES.map(([label, value]): readonly [string, Break] => [label, setFinishedMtime(value)]),
  ['null（stat が失敗したログ）', setFinishedMtime(null)],
  ['項目なし', dropFinishedMtime],
];

for (const [label, breakFinished] of UNREADABLE_ON_FINISHED) {
  test(`D0021-AC-02: 終わったログの mtimeMs が「${label}」でも時刻なしの扱いで、動いているログの時刻を巻き込まず、節・view・帯の quietSec は動いているログ自身の ${QUIET_OVER_SEC}（対照：読める値なら全ログの最新の 10）`, () => {
    const control = noMtimeOnRunningSnapshot('number'); // 動いているログ 612 秒前・終わったログ 10 秒前
    const broken = breakFinished(control);
    assert.notDeepEqual(broken.stageLogs, control.stageLogs, '終わったログの時刻が、実際に読めない形に変わっている');
    const view = viewAt(broken, 0);
    assert.equal(view.runningStage, 'design');
    assert.deepEqual(surfaces(viewAt(control, 0)), same(10));
    assert.deepEqual(surfaces(view), same(QUIET_OVER_SEC));
  });
}

// ---- AC-04：基準は「名前の読めるログ」の最新（決定の記録 D0021） ----

/** 写しに、更新が agoSec 秒前のログ fileName を足す。 */
function withLog(snap: WorkDirSnapshot, fileName: string, agoSec: number): WorkDirSnapshot {
  const text = logText([promptLine('requirements', BASE_AT), resultLine()]);
  return withMtimes({ ...snap, stageLogs: [...snap.stageLogs, { fileName, text }] }, { [fileName]: mtimeAgo(agoSec) });
}

// 段のログの名前（NN_段.jsonl）に合わないもの
for (const name of ['notes.jsonl', '01_Design.jsonl', 'design.jsonl']) {
  test(`D0021-AC-04: 名前の読めないファイル（${name}）の新しい更新時刻は、全ログの最新に入らない（対照：読める名前の同じログなら入る）`, () => {
    const base = staleSnapshot(); // 動いているログ 612 秒前
    const view = viewAt(withLog(base, name, 1), 0);
    assert.equal(view.runningStage, 'design');
    assert.deepEqual(surfaces(viewAt(withLog(base, LOG_REQUIREMENTS, 1), 0)), same(1));
    assert.deepEqual(surfaces(view), same(QUIET_OVER_SEC));
  });
}

// ---- AC-07：動いている以外では null ----

test('D0021-AC-07: 動いている段以外の節の quietSec は null（対照：動いている段の節は数）', () => {
  const view = viewAt(staleSnapshot(), 0);
  assert.equal(nodeOf(view, 'design').status, 'running');
  assert.equal(quietOf(nodeOf(view, 'design')), QUIET_OVER_SEC);
  for (const n of view.nodes) if (n.id !== 'design') assert.equal(quietOf(n), null, n.id);
});

test('D0021-AC-07: 節が作られない段名の動いているログのとき、どの節の quietSec も null（対照：view は数）', () => {
  const view = viewAt(unknownStageSnapshot(), 0);
  assert.equal(view.runningStage, 'mystery');
  assert.ok(view.nodes.every((n) => n.status !== 'running'), '動いている節は作られない');
  assert.equal(quietOf(view), QUIET_OVER_SEC);
  for (const n of view.nodes) assert.equal(quietOf(n), null, n.id);
});

test('D0021-AC-07: 記録なし（空の写し）では、view と節の quietSec は null（対照：動いている写しは数）', () => {
  const view = viewAt(snapshot(), 0);
  assert.notEqual(view.noRecords, null, '記録なしの表示になる');
  assert.equal(view.runningStage, null);
  assert.deepEqual(surfaces(viewAt(staleSnapshot(), 0)), same(QUIET_OVER_SEC));
  assert.equal(quietOf(view), null);
  for (const n of view.nodes) assert.equal(quietOf(n), null, n.id);
});

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

// 「終わった」（final あり）は、ログが残る写しで AC-46 の表が確かめる。ログの無い写しは下の「記録なし」が確かめる。
const NOT_RUNNING: readonly (readonly [string, () => WorkDirSnapshot])[] = [
  ['確認待ち', () => withAllMtimes(waitingSnapshot(), mtimeAgo(QUIET_OVER_SEC))],
  ['待ち（段の合間）', idleSnapshot],
];

for (const [label, make] of NOT_RUNNING) {
  test(`D0021-AC-07: ${label}の run では、view と節の quietSec は null（対照：動いている run は数）`, () => {
    const view = viewAt(make(), 0);
    assert.equal(view.runningStage, null);
    assert.equal(quietOf(viewAt(staleSnapshot(), 0)), QUIET_OVER_SEC);
    assert.equal(quietOf(view), null);
    for (const n of view.nodes) assert.equal(quietOf(n), null, n.id);
  });
}

// ---- AC-08：「今」を引数で受ける純粋な関数 ----

test('D0021-AC-08: 時計を渡さない buildPipelineView の quietSec（節・view）は null（対照：時計を渡すと数）', () => {
  const snap = staleSnapshot();
  const withoutClock = buildPipelineView(snap);
  assert.equal(withoutClock.runningStage, 'design');
  assert.equal(nodeOf(withoutClock, 'design').runningSec, null, '時計を渡さないので経過も出ない（D0017）');
  const withClock = buildPipelineView(snap, clockAt(0));
  assert.equal(quietOf(withClock), QUIET_OVER_SEC);
  assert.equal(quietOf(nodeOf(withClock, 'design')), QUIET_OVER_SEC);
  assert.equal(quietOf(withoutClock), null);
  assert.equal(quietOf(nodeOf(withoutClock, 'design')), null);
});

for (const [label, nowMs] of [
  ['NaN', Number.NaN],
  ['正の無限大', Number.POSITIVE_INFINITY],
  ['負の無限大', Number.NEGATIVE_INFINITY],
] as const) {
  test(`D0021-AC-08: 時計の値が壊れていて（${label}）も例外を投げず、quietSec は null（対照：有限の時計なら数）`, () => {
    const snap = staleSnapshot();
    let view: PipelineView | undefined;
    assert.doesNotThrow(() => {
      view = buildPipelineView(snap, { nowMs, localOffsetMin: 0 });
    });
    assert.equal(view!.runningStage, 'design');
    assert.equal(quietOf(buildPipelineView(snap, clockAt(0))), QUIET_OVER_SEC);
    assert.equal(quietOf(view!), null);
    assert.equal(quietOf(nodeOf(view!, 'design')), null);
  });
}

test('D0021-AC-08: 同じ写しと同じ「今」からは何度組み立てても同じ出力で、写しを書き換えない（quietSec が出ている前提）', () => {
  const snap = staleSnapshot();
  const before = JSON.parse(JSON.stringify(snap));
  const a = buildPipelineView(snap, clockAt(0));
  const b = buildPipelineView(snap, clockAt(0));
  assert.deepStrictEqual(a, b);
  assert.deepStrictEqual(snap, before);
  assert.equal(quietOf(a), QUIET_OVER_SEC, 'quietSec が出ている');
  assert.equal(quietOf(buildPipelineView(snap, clockAt(1))), QUIET_OVER_SEC + 1, '「今」が違えば出力も違う');
});

test('D0021-AC-08: 図の状態の組み立ては時計を読まない（Date.now を読むと投げる関数に替えても同じ結果）', () => {
  const snap = staleSnapshot();
  const expected = buildPipelineView(snap, clockAt(0));
  const realNow = Date.now;
  Date.now = () => {
    throw new Error('時計を読んだ');
  };
  try {
    assert.deepStrictEqual(buildPipelineView(snap, clockAt(0)), expected);
  } finally {
    Date.now = realNow;
  }
  assert.equal(quietOf(expected), QUIET_OVER_SEC, 'quietSec が出ている');
});

// ---- AC-34 ④：時系列の動いている帯 ----

const GANTT_NOW_SEC = 1000;

test('D0021-AC-34: 動いている帯（GanttRow.run）の quietSec は、view・動いている段の節と同じ値', () => {
  const view = viewAt(staleGanttSnapshot(), GANTT_NOW_SEC);
  const row = liveRow(view);
  assert.ok(row?.run, '動いている帯はある');
  assert.equal(quietOf(row.run), QUIET_OVER_SEC);
  assert.equal(quietOf(view), QUIET_OVER_SEC);
  assert.equal(quietOf(nodeOf(view, 'red')), QUIET_OVER_SEC);
});

test('D0021-AC-34: 終わった帯には quietSec の項目が付かない（対照：動いている帯には付く）', () => {
  const view = viewAt(staleGanttSnapshot(), GANTT_NOW_SEC);
  const done = view.gantt.rows.filter((r) => r.run !== null && !r.run.live);
  assert.equal(done.length, 2, '終わった帯は 2 つ');
  for (const r of done) assert.equal(Object.hasOwn(r.run!, 'quietSec'), false, r.label);
  assert.equal(quietOf(liveRow(view)!.run!), QUIET_OVER_SEC, '対照：動いている帯には付く');
});

test('D0021-AC-34: 時刻の読めない行（run が null の動いている行）には付かない（対照：始まりが読める行には付く）', () => {
  const view = viewAt(staleGanttSnapshot({ runningStartSec: null }), GANTT_NOW_SEC);
  assert.equal(view.gantt.rows.at(-1)?.run, null, '動いている行は帯の無い行');
  for (const r of view.gantt.rows) {
    if (r.run !== null) assert.equal(Object.hasOwn(r.run, 'quietSec'), false, r.label);
  }
  assert.equal(quietOf(liveRow(viewAt(staleGanttSnapshot(), GANTT_NOW_SEC))!.run!), QUIET_OVER_SEC, '対照：始まりが読める行には付く');
  assert.equal(quietOf(view), QUIET_OVER_SEC, '印の元（view）は数のまま。帯が無いので帯には出ない');
});

// ---- AC-44：中断した古い途中のログと、再開後の新しいログ ----

test('D0021-AC-44: 古い途中のログ（3 日前・通し番号が大きい）と再開後の新しいログ（5 秒前）が並ぶと、動いている段の判定は古い方のまま、quietSec は 5', () => {
  const view = viewAt(resumedSnapshot(), 0);
  assert.equal(view.runningStage, 'implement', '動いている段の判定は今のまま（通し番号が大きい古い方）');
  assert.deepEqual(surfaces(view, 'implement'), same(RESUMED_NEW_AGO_SEC));
  assert.equal(RESUMED_NEW_AGO_SEC, 5);
});

test('D0021-AC-44: 新しいログが無ければ（対照）、古い途中のログの古さ（3 日）が quietSec になる', () => {
  const resumed = resumedSnapshot();
  const onlyOld: WorkDirSnapshot = { ...resumed, stageLogs: resumed.stageLogs.filter((l) => l.fileName === '05_implement_1.jsonl') };
  assert.equal(onlyOld.stageLogs.length, 1);
  const view = viewAt(onlyOld, 0);
  assert.equal(view.runningStage, 'implement');
  assert.deepEqual(surfaces(view, 'implement'), same(RESUMED_OLD_AGO_SEC));
});

// ---- AC-45：放置された実行・1 つでも新しいログがある ----

const ABANDONED_CASES: readonly (readonly [string, Parameters<typeof abandonedSnapshot>[0], number])[] = [
  ['全ログが目安（600）より古い：終わったログが最新（700 秒前）', {}, 700],
  ['全ログが目安より古い：動いているログが最新（700 秒前）', { runningIsLatest: true }, 700],
  ['1 つだけ目安より新しいログがある（100 秒前）', { latestAgoSec: 100 }, 100],
];

for (const [label, params, expected] of ABANDONED_CASES) {
  test(`D0021-AC-45: ${label}と、quietSec はその最新の更新時刻から決まる（${expected}）`, () => {
    const view = viewAt(abandonedSnapshot(params), 0);
    assert.equal(view.runningStage, 'design');
    assert.deepEqual(surfaces(view, 'design'), same(expected));
  });
}

// ---- AC-46：final がある run には印を出さない ----

for (const final of FINAL_VALUES) {
  test(`D0021-AC-46: final=${final} の run に結果の行が無い途中のログが残っても、節・view・帯の quietSec は null（対照：final を外すと数）`, () => {
    const view = viewAt(staleSnapshot({ final }), 0);
    assert.equal(view.final, final);
    assert.equal(view.runningStage, 'design', '動いているログは今の判定のまま残る');
    assert.deepEqual(surfaces(viewAt(staleSnapshot(), 0)), same(QUIET_OVER_SEC));
    assert.deepEqual(surfaces(view), same(null));
  });
}

// ---- AC-47：前の実行（archive/）には印を出さない ----

test('D0021-AC-47: previous: true の写し（archive/ の前の実行）は、final が無く動いているログに更新時刻があっても、節・view・帯の quietSec は null（対照：previous を外すと数）', () => {
  const live = staleSnapshot();
  const view = viewAt(withPrevious(live), 0);
  assert.equal(view.final, null);
  assert.equal(view.runningStage, 'design');
  assert.deepEqual(surfaces(viewAt(live, 0)), same(QUIET_OVER_SEC));
  assert.deepEqual(surfaces(view), same(null));
});

test('D0021-AC-47: previous: false の写しは前の実行ではないので、quietSec は数のまま', () => {
  const snap = { ...staleSnapshot(), previous: false } as WorkDirSnapshot;
  assert.deepEqual(surfaces(viewAt(snap, 0)), same(QUIET_OVER_SEC));
});

// ---- AC-48 ②：7 日の上限 ----

test('D0021-AC-48: 1980 年の更新時刻でも、節・view・帯の quietSec は 604800（7 日）で頭打ち', () => {
  assert.deepEqual(surfaces(viewAt(ancientSnapshot(), 0)), same(604800));
});

for (const [ago, expected] of [
  [604_799, 604_799],
  [604_800, 604_800],
  [604_801, 604_800],
] as const) {
  test(`D0021-AC-48: 更新が ${ago} 秒前なら、節・view・帯の quietSec は ${expected}（7 日が上限）`, () => {
    assert.deepEqual(surfaces(viewAt(staleSnapshot({ quietSec: ago }), 0)), same(expected));
  });
}

// ---- AC-49：state.json が読めない run には印を出さない ----

for (const kind of BROKEN_STATE_KINDS) {
  test(`D0021-AC-49: state.json が「${kind}」の run は、動いているログに更新時刻があっても、節・view・帯の quietSec は null（対照：正しい state.json なら数）`, () => {
    const view = viewAt(brokenStateSnapshot(kind), 0);
    assert.equal(view.runningStage, 'design', '動いているログは拾われる（通し番号の基準が 0 になる）');
    assert.deepEqual(surfaces(viewAt(staleSnapshot(), 0)), same(QUIET_OVER_SEC));
    assert.deepEqual(surfaces(view), same(null));
  });
}

test('D0021-AC-49: オブジェクトとして読める state.json なら、中身が空の {} でも印の対象（対照：読めない JSON は null）', () => {
  const snap: WorkDirSnapshot = { ...staleSnapshot(), stateJson: '{}' };
  assert.equal(viewAt(snap, 0).runningStage, 'design');
  assert.equal(viewAt(brokenStateSnapshot('broken'), 0).runningStage, 'design');
  assert.deepEqual(surfaces(viewAt(snap, 0)), same(QUIET_OVER_SEC));
  assert.deepEqual(surfaces(viewAt(brokenStateSnapshot('broken'), 0)), same(null));
});

/** runRecord.ts の isReadableState。まだ無ければ、ここで「まだ無い」と落ちる。 */
async function isReadableState(): Promise<(text: string | null) => boolean> {
  const mod = (await runRecord()) as unknown as { isReadableState?: (text: string | null) => boolean };
  assert.equal(typeof mod.isReadableState, 'function', 'runRecord.ts に isReadableState がまだ無い');
  return mod.isReadableState!;
}

const UNREADABLE_STATES: readonly (readonly [string, string | null])[] = [
  ['null（ファイルなし）', null],
  ['空の文字', ''],
  ['壊れた JSON', '{壊れた'],
  ['JSON の配列', '[]'],
  ['JSON の数', '42'],
  ['JSON の文字', '"abc"'],
  ['JSON の null', 'null'],
  ['JSON の真偽', 'true'],
];

for (const [label, text] of UNREADABLE_STATES) {
  test(`D0021-AC-49: isReadableState は ${label} を false にする（対照：{} は true）`, async () => {
    const fn = await isReadableState();
    assert.equal(fn('{}'), true);
    assert.equal(fn(text), false);
  });
}

test('D0021-AC-49: isReadableState は、オブジェクトの記録（{} と実際の記録）を true にする', async () => {
  const fn = await isReadableState();
  assert.equal(fn('{}'), true);
  assert.equal(fn(stateJson({ runs: [] })), true);
  assert.equal(fn(staleSnapshot().stateJson), true);
});
