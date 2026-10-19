// 図の状態の時間の情報（D0017）：動いている段の経過・確認待ちの待ち時間・全体の経過・回ごとの時間。
// 「今の時刻」は引数（ViewClock）で渡す。時計は読まない。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPipelineView } from './pipelineView.ts';
import type { PipelineView } from './pipelineView.ts';
import { snapshot, stageRunEntry, stateJson, logText, promptLine, assistantText } from '../test/fixtures.ts';
import {
  BASE_AT,
  OVERALL_BEFORE_SEC,
  FINISHED_ELAPSED_SEC,
  RUNNING_UPDATED_AT,
  STARTED_AT,
  clockAt,
  finishedSnapshot,
  finishedView,
  fixtureSnapshot,
  runningSnapshot,
  runningView,
  viewAt,
  waitingSnapshot,
  waitingView,
} from '../test/liveFixtures.ts';

// 新しい項目は、テストの型のためにこの形で読む（PipelineNode に runningSec・waitingSec が増える）
interface TimedNode {
  id: string;
  status: string;
  runningSec: number | null;
  waitingSec: number | null;
}
const timed = (view: PipelineView): TimedNode[] => view.nodes as unknown as TimedNode[];
const nodeOf = (view: PipelineView, id: string): TimedNode => {
  const found = timed(view).find((n) => n.id === id);
  assert.ok(found, `節 ${id} があること`);
  return found;
};
const elapsedOf = (view: PipelineView): unknown => (view as unknown as { elapsed: unknown }).elapsed;
const stageTimesOf = (view: PipelineView): { stage: string; label: string; runs: unknown[]; totalSec: number }[] =>
  (view as unknown as { stageTimes: { stage: string; label: string; runs: unknown[]; totalSec: number }[] }).stageTimes;

// ---- AC-08：動いている段 ----

test('D0017-AC-08: 動いている段の節の runningSec が「今の時刻 − at」の秒になる（83 秒後なら 83）', () => {
  const view = runningView(83);
  assert.equal(view.runningStage, 'design');
  assert.equal(nodeOf(view, 'design').runningSec, 83);
  assert.equal(nodeOf(runningView(0), 'design').runningSec, 0);
  assert.equal(nodeOf(runningView(3725), 'design').runningSec, 3725);
});

test('D0017-AC-08: 動いていない段の節と確認の節の runningSec は null', () => {
  const view = runningView(83);
  for (const n of timed(view)) if (n.id !== 'design') assert.equal(n.runningSec, null, n.id);
});

test('D0017-AC-08: 時計を渡さないと runningSec は null（時計を内側で読まない）', () => {
  const view = buildPipelineView(runningSnapshot());
  assert.equal(view.runningStage, 'design');
  for (const n of timed(view)) assert.equal(n.runningSec, null, n.id);
});

test('D0017-AC-08: 動いている段のログに at が無いと runningSec は null（状態は「動いている」のまま）', () => {
  const view = viewAt(runningSnapshot({ omitAt: true }), 83);
  assert.equal(nodeOf(view, 'design').status, 'running');
  assert.equal(nodeOf(view, 'design').runningSec, null);
});

test('D0017-AC-08: 同じ入力（写しと時計）からは何度組み立てても同じ出力で、写しを書き換えない', () => {
  const snap = runningSnapshot();
  const before = JSON.parse(JSON.stringify(snap));
  const a = buildPipelineView(snap, clockAt(83));
  const b = buildPipelineView(snap, clockAt(83));
  assert.deepStrictEqual(a, b);
  assert.deepStrictEqual(snap, before);
  assert.notDeepStrictEqual(buildPipelineView(snap, clockAt(84)), a, '時計が違えば出力も違う');
});

// ---- AC-09：確認待ち ----

test('D0017-AC-09: 確認待ちのとき、その段の確認の節の waitingSec が「今の時刻 − since」になる', () => {
  const view = waitingView(40);
  assert.equal(nodeOf(view, 'review:requirements').waitingSec, 40);
  assert.equal(nodeOf(view, 'review:requirements').status, 'pending', '状態は今までどおり「まだ」');
});

test('D0017-AC-09: 確認待ちの段の確認の節以外には waitingSec が付かない', () => {
  const view = waitingView(40);
  for (const n of timed(view)) if (n.id !== 'review:requirements') assert.equal(n.waitingSec, null, n.id);
});

test('D0017-AC-09: 確認待ちでなければ（pending_review が無い）どの節にも waitingSec が付かない', () => {
  const view = viewAt(runningSnapshot(), 40);
  for (const n of timed(view)) assert.equal(n.waitingSec, null, n.id);
});

test('D0017-AC-09: 確認の結果（approved）がもう記録にある確認の節には付かない', () => {
  const snap = snapshot({
    stateJson: stateJson({
      runs: [stageRunEntry({ stage: 'requirements', seq: 1 }), { stage: 'requirements', review: 'approved' }],
      pendingReview: { stage: 'requirements', doc: 'docs/pipeline/01_requirements.md', session_id: 's', since: BASE_AT },
      startedAt: STARTED_AT,
    }),
  });
  const view = viewAt(snap, 40);
  assert.equal(nodeOf(view, 'review:requirements').status, 'done');
  assert.equal(nodeOf(view, 'review:requirements').waitingSec, null);
});

test('D0017-AC-09: 動いている段があるときは、確認の節に waitingSec を付けない', () => {
  const snap = snapshot({
    stateJson: stateJson({
      runs: [stageRunEntry({ stage: 'requirements', seq: 1 })],
      pendingReview: { stage: 'requirements', doc: 'docs/pipeline/01_requirements.md', session_id: 's', since: BASE_AT },
      startedAt: STARTED_AT,
    }),
    stageLogs: [{ fileName: '02_design.jsonl', text: logText([promptLine('design', BASE_AT), assistantText('x')]) }],
  });
  const view = viewAt(snap, 40);
  assert.equal(nodeOf(view, 'design').runningSec, 40);
  for (const n of timed(view)) assert.equal(n.waitingSec, null, n.id);
});

test('D0017-AC-09: since が無い確認待ち（古い記録）や時計が無いときは waitingSec が null', () => {
  for (const view of [viewAt(waitingSnapshot({ omitSince: true }), 40), buildPipelineView(waitingSnapshot())]) {
    for (const n of timed(view)) assert.equal(n.waitingSec, null, n.id);
  }
  assert.equal(viewAt(waitingSnapshot({ omitSince: true }), 40).pendingReview?.stage, 'requirements', '確認待ちの印は今までどおり');
});

// ---- AC-10：全体の経過 ----

test('D0017-AC-10: 動いている実行の全体の経過は「今の時刻 − started_at」で、数え上げる（live）', () => {
  assert.deepEqual(elapsedOf(runningView(83)), { seconds: OVERALL_BEFORE_SEC + 83, live: true });
});

test('D0017-AC-10: 確認待ちの実行の全体の経過も「今の時刻 − started_at」で、数え上げる（live）', () => {
  assert.deepEqual(elapsedOf(waitingView(40)), { seconds: OVERALL_BEFORE_SEC + 40, live: true });
});

test('D0017-AC-10: 終わった実行（final あり）は「updated_at − started_at」の固定で、今の時刻が違っても変わらない', () => {
  for (const sec of [0, 9999, 10 ** 7]) {
    assert.deepEqual(elapsedOf(viewAt(finishedSnapshot(), sec)), { seconds: FINISHED_ELAPSED_SEC, live: false }, `${sec}`);
  }
  assert.deepEqual(elapsedOf(finishedView()), { seconds: FINISHED_ELAPSED_SEC, live: false });
});

test('D0017-AC-10: 動いていない・確認待ちでもない実行（final なし）は updated_at までの固定で、数え上げない', () => {
  const snap = snapshot({
    stateJson: stateJson({
      runs: [stageRunEntry({ stage: 'requirements', seq: 1 })],
      startedAt: STARTED_AT,
      updatedAt: RUNNING_UPDATED_AT,
    }),
  });
  for (const sec of [0, 500]) assert.deepEqual(elapsedOf(viewAt(snap, sec)), { seconds: OVERALL_BEFORE_SEC + 30, live: false }, `${sec}`);
});

test('D0017-AC-10: 時計を渡さないと、動いている実行の全体の経過も updated_at までの固定（live でない）', () => {
  assert.deepEqual(elapsedOf(buildPipelineView(runningSnapshot())), { seconds: OVERALL_BEFORE_SEC + 30, live: false });
});

test('D0017-AC-10: started_at が無い・読めない記録の全体の経過は null', () => {
  for (const startedAt of [null, 'x', 5, {}, '']) {
    const view = viewAt(runningSnapshot({ startedAt }), 83);
    assert.equal(elapsedOf(view), null, JSON.stringify(startedAt));
  }
});

// ---- AC-11：未来の時刻・オフセット ----

test('D0017-AC-11: 時刻が今より後（未来）でも、runningSec・waitingSec・全体の経過は負にならず 0 になる', () => {
  assert.equal(nodeOf(runningView(-30), 'design').runningSec, 0);
  assert.equal(nodeOf(waitingView(-30), 'review:requirements').waitingSec, 0);
  const future = viewAt(runningSnapshot({ startedAt: '2026-10-17T10:10:00' }), 83);
  assert.deepEqual(elapsedOf(future), { seconds: 0, live: true });
});

// 同じ瞬間（10:00:00 UTC）の書き方と、手元のずれ（分）の組み合わせ。どれでも 83 秒後は 83
const SAME_INSTANT: [string, number][] = [
  ['2026-10-17T10:00:00+00:00', 0],
  ['2026-10-17T10:00:00Z', 540],
  ['2026-10-17T19:00:00+09:00', 0],
  ['2026-10-17T19:00:00+09:00', -300],
  ['2026-10-17T10:00:00', 0],
  ['2026-10-17T19:00:00', 540],
  ['2026-10-17T05:00:00', -300],
];
for (const [at, localOffsetMin] of SAME_INSTANT) {
  test(`D0017-AC-11: at が ${at}（手元のずれ ${localOffsetMin} 分）でも、同じ瞬間なら runningSec は同じ 83`, () => {
    const view = viewAt(runningSnapshot({ at }), 83, localOffsetMin);
    assert.equal(nodeOf(view, 'design').runningSec, 83);
  });
  test(`D0017-AC-11: since が ${at}（手元のずれ ${localOffsetMin} 分）でも、同じ瞬間なら waitingSec は同じ 40`, () => {
    const view = viewAt(waitingSnapshot({ since: at }), 40, localOffsetMin);
    assert.equal(nodeOf(view, 'review:requirements').waitingSec, 40);
  });
}

test('D0017-AC-11: started_at（オフセットなし）は手元の時刻として読む：手元が +09:00 なら 18:58 が 09:58 UTC', () => {
  const view = viewAt(runningSnapshot({ startedAt: '2026-10-17T18:58:00' }), 83, 540);
  assert.deepEqual(elapsedOf(view), { seconds: OVERALL_BEFORE_SEC + 83, live: true });
});

// ---- AC-12：回ごとの時間 ----

test('D0017-AC-12: 実装が3回の stageTimes に、回ごとの durationSec と、回の和（小数 1 桁）の合計が入る', () => {
  const entry = stageTimesOf(finishedView()).find((s) => s.stage === 'implement');
  assert.deepEqual(entry, {
    stage: 'implement',
    label: '実装',
    runs: [
      { seq: 2, attempt: 1, durationSec: 121.04 },
      { seq: 4, attempt: 2, durationSec: 78.02 },
      { seq: 6, attempt: 3, durationSec: 40.01 },
    ],
    totalSec: 239.1,
  });
});

test('D0017-AC-12: 実行が2回以上ある段（実装・検証）だけが入り、1回だけの段（要件定義）は入らない', () => {
  assert.deepEqual(
    stageTimesOf(finishedView()).map((s) => s.stage).sort(),
    ['implement', 'test'],
  );
  assert.equal(stageTimesOf(finishedView()).find((s) => s.stage === 'test')?.totalSec, 139);
});

test('D0017-AC-12: 段の実行が1回ずつの記録では stageTimes は空', () => {
  assert.deepEqual(stageTimesOf(runningView(83)), []);
  assert.deepEqual(stageTimesOf(buildPipelineView(snapshot())), []);
});

test('D0017-AC-12: 確認待ちの時間は stageTimes の合計に入らない（段の実行時間 duration_sec だけ）', () => {
  const snap = snapshot({
    stateJson: stateJson({
      runs: [
        stageRunEntry({ stage: 'requirements', seq: 1, durationSec: 30 }),
        { stage: 'requirements', review: 'revise', feedback: '直して' },
        stageRunEntry({ stage: 'requirements', seq: 2, durationSec: 20 }),
      ],
      pendingReview: { stage: 'requirements', doc: 'docs/pipeline/01_requirements.md', session_id: 's', since: BASE_AT },
      startedAt: STARTED_AT,
    }),
  });
  const entry = stageTimesOf(viewAt(snap, 600)).find((s) => s.stage === 'requirements');
  assert.equal(entry?.totalSec, 50);
});

test('D0017-AC-12: 節の metrics.durationSec（合計）は今までどおり（回の和の丸め）', () => {
  const impl = finishedView().nodes.find((n) => n.id === 'implement');
  assert.equal(impl?.metrics?.durationSec, 239.1);
});

// ---- AC-31：古い形 ----

const OLD_FIXTURES: string[][] = [
  ['pipe_dev', 'running'],
  ['pipe_dev', 'waiting'],
  ['pipe_dev', 'finished'],
  ['pipe_in', 'running'],
  ['pipe_in', 'waiting'],
  ['pipe_in', 'finished'],
];

/** 節の並び・状態・数（時間の項目を除く）。 */
const plainNodes = (view: PipelineView) =>
  view.nodes.map(({ id, label, status, reviseCount, sendBackCount, metrics }) => ({ id, label, status, reviseCount, sendBackCount, metrics }));

for (const parts of OLD_FIXTURES) {
  test(`D0017-AC-31: 古い形の見本（${parts.join('/')}）は、時計を渡しても節の数・状態・並びが同じで、waitingSec が出ない`, () => {
    const snap = fixtureSnapshot(...parts);
    const without = buildPipelineView(snap);
    const withClock = buildPipelineView(snap, clockAt(100));
    assert.deepEqual(plainNodes(withClock), plainNodes(without));
    for (const n of timed(withClock)) assert.equal(n.waitingSec, null, `${n.id} の waitingSec（since が無い）`);
  });
}

test('D0017-AC-31: Prompt に at が無い進行中の記録（パイプを持つ前の形）は、時計を渡しても runningSec が出ず、状態は同じ', () => {
  const snap = snapshot({
    stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }), // stages 無し（パイプを持つ前）
    stageLogs: [{ fileName: '02_design.jsonl', text: logText([promptLine('design'), assistantText('x')]) }],
  });
  const withClock = buildPipelineView(snap, clockAt(100));
  assert.deepEqual(plainNodes(withClock), plainNodes(buildPipelineView(snap)));
  assert.equal(withClock.runningStage, 'design');
  for (const n of timed(withClock)) assert.equal(n.runningSec, null, n.id);
});

test('D0017-AC-31: since が無い確認待ちの記録は、時計を渡しても確認待ちの表示（pendingReview）が同じで waitingSec は出ない', () => {
  const view = viewAt(waitingSnapshot({ omitSince: true }), 100);
  assert.deepEqual(view.pendingReview, buildPipelineView(waitingSnapshot({ omitSince: true })).pendingReview);
  assert.equal(nodeOf(view, 'review:requirements').waitingSec, null);
});
