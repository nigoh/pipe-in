// 図の状態の並列の枠（D0063 の AC-04〜07・AC-11・AC-12・AC-14）：枠のまとめ方・段ごとの状態・動いている段が複数・枠の状態・段のログの選び。
// 新しい項目（PipelineView.frames・runningStages・groupLogs、PipelineNode.group）と新しい関数（terminalFor・pickableLogStages）は、
// 実装の段で入るまで、型に頼らず読む（test/groupFixtures.ts の *Of 関数、名前空間 import から needFunction で取る）。
// 赤の理由は「まだ組み立てていない」：frames が undefined／動いている段が 1 つだけ（先に済んだ段の通し番号が大きいと落ちる）／terminalFor が無い。
// 「今のまま通る。守る」と書いたものは、今の作りで通り、実装のあとも通り続けることを見張る（枠の無い記録・開発フローなど）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as pipelineView from './pipelineView.ts';
import { NODE_ORDER, buildPipelineView } from './pipelineView.ts';
import type { PipelineNode, PipelineView, TerminalView } from './pipelineView.ts';
import { needFunction } from '../test/needModule.ts';
import { budgetRun, nodeById } from '../test/budgetFixtures.ts';
import { checkView, stageDef } from '../test/checkFixtures.ts';
import { fixtureSnapshot } from '../test/liveFixtures.ts';
import {
  GROUP_STAGES,
  GROUP_STAGES_4,
  doneLog,
  failedRun,
  frameShapes,
  frameStatuses,
  framesOf,
  gStage,
  groupLogsOf,
  groupView,
  liveLog,
  nodeGroupOf,
  runEntry,
  runningStagesOf,
  textsOfItems,
} from '../test/groupFixtures.ts';

const ids = (view: PipelineView): string[] => view.nodes.map((n) => n.id);

type TerminalFor = (view: PipelineView, picked: string | null) => { terminal: TerminalView; stage: string | null };
const terminalFor = (view: PipelineView, picked: string | null) =>
  needFunction<TerminalFor>(pipelineView, 'terminalFor', 'domain/pipelineView.ts')(view, picked);
const pickableLogStages = (view: PipelineView): string[] =>
  needFunction<(v: PipelineView) => string[]>(pipelineView, 'pickableLogStages', 'domain/pipelineView.ts')(view);

/** 節から group の鍵を除いたもの（「group を足しても、ほかは変わらない」を比べるため） */
const withoutGroup = (n: PipelineNode): object => {
  const { group: _group, ...rest } = n as PipelineNode & { group?: unknown };
  return rest;
};

// 見本の実行：前の段 survey が済んだあと、枠 draw の flow・klass が動く
const SURVEY_DONE = [runEntry('survey', 1)];
/** flow・klass が同時に動いている（どちらも Prompt があり、終わりの行が無い。state.json には survey だけ） */
const BOTH_RUNNING = () => groupView(SURVEY_DONE, { stageLogs: [doneLog(1, 'survey', null), liveLog(2, 'flow'), liveLog(3, 'klass')] });
/** klass が先に済み（通し番号 3 が記録に載った）、flow（通し番号 2）がまだ動いている */
const LATE_RUNNING = () =>
  groupView([...SURVEY_DONE, runEntry('klass', 3)], { stageLogs: [doneLog(1, 'survey', null), liveLog(2, 'flow'), doneLog(3, 'klass', null)] });

// ======== AC-04：同じ group の続いた段が 1 つの枠にまとまる ========

test('D0063-AC-04: 同じ group の続いた段が 1 つの枠にまとまる（名前・中の段・中の節の id の並び）', () => {
  const view = groupView([]);
  assert.deepEqual(frameShapes(view), [{ name: 'draw', members: ['flow', 'klass'], nodeIds: ['flow', 'klass'] }]);
});

test('D0063-AC-04: 節の並び・id は枠があっても変わらない（平らなまま）。枠の中の段の節だけ group を持つ', () => {
  const view = groupView([]);
  assert.deepEqual(ids(view), ['input', 'survey', 'flow', 'klass', 'report', 'final']);
  assert.deepEqual(
    view.nodes.map((n) => nodeGroupOf(n) ?? null),
    [null, null, 'draw', 'draw', null, null],
    '節ごとの group（枠の外は null か無し）',
  );
});

test('D0063-AC-04: 間に別の段が入って分かれた同名の group は 2 つの枠として扱う', () => {
  const stages = [gStage('a', 'g'), gStage('x'), gStage('b', 'g')];
  const view = groupView([], { stages });
  assert.deepEqual(frameShapes(view), [
    { name: 'g', members: ['a'], nodeIds: ['a'] },
    { name: 'g', members: ['b'], nodeIds: ['b'] },
  ]);
});

test('D0063-AC-04: 名前の違う group が続くときは、名前ごとの 2 つの枠', () => {
  const stages = [gStage('a', 'g1'), gStage('b', 'g1'), gStage('c', 'g2'), gStage('d', 'g2')];
  assert.deepEqual(frameShapes(groupView([], { stages })), [
    { name: 'g1', members: ['a', 'b'], nodeIds: ['a', 'b'] },
    { name: 'g2', members: ['c', 'd'], nodeIds: ['c', 'd'] },
  ]);
});

test('D0063-AC-04: 段が 1 つだけの枠も枠にする（作業台と同じ）', () => {
  const stages = [gStage('a'), gStage('b', 'solo'), gStage('c')];
  assert.deepEqual(frameShapes(groupView([], { stages })), [{ name: 'solo', members: ['b'], nodeIds: ['b'] }]);
});

test('D0063-AC-04: 枠が 2 つ・段が前後にある記録で、枠は出る順に並ぶ', () => {
  const stages = [gStage('a'), gStage('b', 'g1'), gStage('c', 'g1'), gStage('d'), gStage('e', 'g2'), gStage('f')];
  assert.deepEqual(
    framesOf(groupView([], { stages }))?.map((f) => f.name),
    ['g1', 'g2'],
  );
});

test('D0063-AC-04: 枠の中の段に判定があるとき、その段の節のあとに check:<段> が続く', () => {
  const stages = [gStage('survey'), gStage('flow', 'draw', { check: { on_fail: null, max_retries: 2 } }), gStage('klass', 'draw'), gStage('report')];
  const view = groupView([], { stages });
  assert.deepEqual(ids(view), ['input', 'survey', 'flow', 'check:flow', 'klass', 'report', 'final'], '節の並び（D0062 のまま）');
  assert.deepEqual(frameShapes(view), [{ name: 'draw', members: ['flow', 'klass'], nodeIds: ['flow', 'check:flow', 'klass'] }]);
});

test('D0063-AC-04: 枠の中の段の確認の節は枠の中に入れない（本体は許さないが、記録に来ても壊れない）', () => {
  const stages = [gStage('a', 'g', { review: true }), gStage('b', 'g')];
  const view = groupView([], { stages });
  assert.ok(ids(view).includes('review:a'), '確認の節は図に残る');
  const frames = framesOf(view);
  assert.ok(frames !== undefined, 'frames がある（まだ作っていない）');
  assert.ok(!frames.some((f) => f.nodeIds.includes('review:a')), `枠の中に確認の節が入っている: ${JSON.stringify(frames)}`);
  assert.deepEqual(frames[0]?.members, ['a', 'b']);
});

test('D0063-AC-04: group の無い記録は frames が空で、節も今までと同じ', () => {
  const stages = [gStage('survey'), gStage('flow'), gStage('klass'), gStage('report')];
  const view = groupView([], { stages });
  assert.deepEqual(framesOf(view), []);
  assert.deepEqual(ids(view), ['input', 'survey', 'flow', 'klass', 'report', 'final']);
});

test('D0063-AC-04: 開発フローの記録（stages が無い・開発の 5 段）は frames が空で、11 節は NODE_ORDER のまま', () => {
  const dev = ['requirements', 'design', 'red', 'implement', 'test'].map((name) => stageDef({ name }));
  const noStages = checkView([runEntry('requirements', 1)]);
  const fiveStages = checkView([runEntry('requirements', 1)], { pipe: 'dev', stages: dev });
  assert.deepEqual(framesOf(noStages), [], 'stages が無い記録');
  assert.deepEqual(framesOf(fiveStages), [], '開発の 5 段の記録');
  assert.deepEqual(ids(noStages), [...NODE_ORDER]);
  assert.deepEqual(ids(fiveStages), [...NODE_ORDER]);
});

test('D0063-AC-04: 記録が空（state.json が無い）でも frames は空で、例外を出さない', () => {
  const view = buildPipelineView({ workDir: '/w', stateJson: null, stageLogs: [], artifacts: {} });
  assert.deepEqual(framesOf(view), []);
});

test('D0063-AC-04: group を足しても、節の順・id・状態・回数は group を除いた同じ記録と変わらない。今のまま通る。守る', () => {
  const plain = GROUP_STAGES.map((s) => {
    const { group: _g, ...rest } = s as Record<string, unknown>;
    return rest;
  });
  const runs = [...SURVEY_DONE, runEntry('flow', 2), failedRun('klass', 3)];
  const withGroup = groupView(runs);
  const without = groupView(runs, { stages: plain });
  assert.deepEqual(withGroup.nodes.map(withoutGroup), without.nodes.map(withoutGroup));
});

// ======== AC-05：枠の中の段の状態が段ごとに決まる ========

test('D0063-AC-05: 枠の中の段の状態が段ごとに決まる（flow は完了・klass は失敗・report はまだ）。今のまま通る。守る', () => {
  const view = groupView([...SURVEY_DONE, runEntry('flow', 2), failedRun('klass', 3)]);
  assert.equal(nodeById(view, 'flow').status, 'done');
  assert.equal(nodeById(view, 'klass').status, 'failed');
  assert.equal(nodeById(view, 'report').status, 'pending');
});

test('D0063-AC-05: 同時に 2 つの段が動いている記録で、2 つとも running（動いている段の一覧にも 2 つ入る）', () => {
  const view = BOTH_RUNNING();
  assert.equal(nodeById(view, 'flow').status, 'running');
  assert.equal(nodeById(view, 'klass').status, 'running');
  assert.equal(nodeById(view, 'survey').status, 'done');
  assert.deepEqual([...(runningStagesOf(view) ?? ['（無い）'])].sort(), ['flow', 'klass']);
});

test('D0063-AC-05: 同時に動いているとき、既定のログは通し番号がいちばん大きい動いているログ（今までと同じ決め方）。今のまま通る。守る', () => {
  const view = BOTH_RUNNING();
  assert.equal(view.runningStage, 'klass');
  assert.equal(view.terminal.source?.stage, 'klass');
  assert.equal(view.terminal.source?.seq, 3);
});

test('D0063-AC-05: 枠の中の 4 段のうち 3 段が同時に動いていても、3 つとも running で残りは pending', () => {
  const view = groupView(SURVEY_DONE, {
    stages: GROUP_STAGES_4,
    stageLogs: [liveLog(2, 'a'), liveLog(3, 'b'), liveLog(4, 'c')],
  });
  assert.deepEqual(
    ['a', 'b', 'c', 'd'].map((id) => nodeById(view, id).status),
    ['running', 'running', 'running', 'pending'],
  );
});

test('D0063-AC-05: 枠の中の段が判定でやり直した回は、その段の節が「N 回目」の元（budget の runCount・nth）を持ち、判定の節は段のすぐあと。今のまま通る。守る', () => {
  // 上限のある段の実行は、段の実行が 2 回以上ある段と同じ扱い（budget は上限のある実行があるときだけ持つ）
  const stages = [gStage('survey'), gStage('flow', 'draw', { check: { on_fail: null, max_retries: 2 } }), gStage('klass', 'draw'), gStage('report')];
  const runs = [
    runEntry('survey', 1),
    budgetRun({ stage: 'flow', seq: 2, maxBudgetUsd: 1, costUsd: 0.1 }),
    budgetRun({ stage: 'klass', seq: 3, maxBudgetUsd: 1, costUsd: 0.1 }),
    budgetRun({ stage: 'flow', seq: 4, maxBudgetUsd: 1, costUsd: 0.1 }),
  ];
  const view = groupView(runs, { stages });
  const budget = nodeById(view, 'flow').budget;
  assert.equal(budget?.runCount, 2, '段の実行が 2 回ある');
  assert.equal(budget?.nth, 2);
  assert.equal(nodeById(view, 'klass').budget?.runCount, 1);
  assert.deepEqual(ids(view).slice(2, 5), ['flow', 'check:flow', 'klass'], '判定の節は枠の中の段のすぐあと');
});

// ======== AC-06：動いている段の判定 ========

test('D0063-AC-06: 先に済んだ段の通し番号のほうが大きくても、まだ動いている段が落ちない', () => {
  const view = LATE_RUNNING();
  assert.equal(view.runningStage, 'flow', '既定のログの段');
  assert.deepEqual(runningStagesOf(view), ['flow']);
  assert.equal(nodeById(view, 'flow').status, 'running');
  assert.equal(nodeById(view, 'klass').status, 'done');
  assert.equal(view.terminal.source?.stage, 'flow', '右の欄は動いている段のログ');
});

test('D0063-AC-06: 先に済んだ段のログに終わりの行が無くても、記録に実行が載った通し番号のログは動いていると数えない', () => {
  // 強制終了などで klass のログは終わりの行が無いまま残った。state.json には klass（通し番号 3）の実行が載っている
  const view = groupView([...SURVEY_DONE, runEntry('klass', 3)], { stageLogs: [liveLog(2, 'flow'), liveLog(3, 'klass')] });
  assert.deepEqual(runningStagesOf(view), ['flow']);
  assert.equal(nodeById(view, 'klass').status, 'done');
  assert.equal(nodeById(view, 'flow').status, 'running');
});

test('D0063-AC-06: 枠の無い記録では、先に済んだ段の通し番号が大きいとき、古いログを動いているとは数えない。今のまま通る。守る', () => {
  const plain = GROUP_STAGES.map((s) => {
    const { group: _g, ...rest } = s as Record<string, unknown>;
    return rest;
  });
  const view = groupView([...SURVEY_DONE, runEntry('klass', 3)], { stages: plain, stageLogs: [liveLog(2, 'flow'), doneLog(3, 'klass', null)] });
  assert.equal(view.runningStage, null);
  assert.equal(nodeById(view, 'flow').status, 'pending');
  assert.equal(nodeById(view, 'klass').status, 'done');
});

test('D0063-AC-06: 開発フローは、記録の最大の通し番号より後ろのログだけが動いている。今のまま通る。守る', () => {
  const runs = [runEntry('requirements', 1), runEntry('design', 2)];
  // 通し番号 1 の古いログ（終わりの行が無い）は動いていると数えず、3 の red だけが動いている
  const view = checkView(runs, { stageLogs: [liveLog(1, 'requirements'), liveLog(3, 'red')] });
  assert.equal(view.runningStage, 'red');
  assert.equal(nodeById(view, 'red').status, 'running');
  assert.equal(nodeById(view, 'requirements').status, 'done');
  const none = checkView(runs, { stageLogs: [liveLog(1, 'requirements')] });
  assert.equal(none.runningStage, null);
});

test('D0063-AC-06: 枠の中の段が動いていないとき（全部済み）は、動いている段は空', () => {
  const view = groupView([...SURVEY_DONE, runEntry('flow', 2), runEntry('klass', 3)], {
    stageLogs: [doneLog(1, 'survey', null), doneLog(2, 'flow', null), doneLog(3, 'klass', null)],
  });
  assert.equal(view.runningStage, null);
  assert.deepEqual(runningStagesOf(view), []);
});

// ======== AC-07：枠の状態 ========

const FRAME_CASES: readonly (readonly [string, () => PipelineView, string])[] = [
  ['どれも始まっていない', () => groupView(SURVEY_DONE), 'pending'],
  ['1 つ完了・1 つまだ', () => groupView([...SURVEY_DONE, runEntry('flow', 2)]), 'pending'],
  ['すべて完了', () => groupView([...SURVEY_DONE, runEntry('flow', 2), runEntry('klass', 3)]), 'done'],
  ['1 つ失敗・1 つ完了', () => groupView([...SURVEY_DONE, failedRun('flow', 2), runEntry('klass', 3)]), 'failed'],
  ['1 つ失敗・1 つまだ（動いている段は無い）', () => groupView([...SURVEY_DONE, failedRun('flow', 2)]), 'failed'],
  ['1 つ失敗・1 つ動いている（動いているが勝つ）', () => groupView([...SURVEY_DONE, failedRun('flow', 2)], { stageLogs: [liveLog(3, 'klass')] }), 'running'],
  ['1 つ完了・1 つ動いている', () => groupView([...SURVEY_DONE, runEntry('flow', 2)], { stageLogs: [liveLog(3, 'klass')] }), 'running'],
  ['2 つとも動いている', BOTH_RUNNING, 'running'],
  ['先に済んだ段の通し番号が大きくて、もう 1 つが動いている', LATE_RUNNING, 'running'],
];
for (const [label, make, expected] of FRAME_CASES) {
  test(`D0063-AC-07: 枠の状態は running > failed > done > pending の順で決まる：${label}`, () => {
    const statuses = frameStatuses(make());
    assert.ok(statuses !== undefined && statuses.length === 1, `枠が 1 つある（まだ作っていない）: ${JSON.stringify(statuses)}`);
    assert.equal(statuses[0], expected);
  });
}

test('D0063-AC-07: 枠が 2 つあるとき、枠ごとに状態が決まる（出る順）', () => {
  const stages = [gStage('a', 'g1'), gStage('b', 'g1'), gStage('c', 'g2'), gStage('d', 'g2')];
  const view = groupView([runEntry('a', 1), runEntry('b', 2)], { stages });
  assert.deepEqual(frameStatuses(view), ['done', 'pending']);
});

// ======== AC-11：段のログを選ぶ（純粋な関数） ========

/** flow が 2 回（1 回目 02・2 回目 04）、klass が 1 回（03）流れた実行 */
const TWO_RUNS_OF_FLOW = () =>
  groupView([...SURVEY_DONE, runEntry('flow', 2), runEntry('klass', 3), runEntry('flow', 4)], {
    stageLogs: [doneLog(1, 'survey', null, 'surveyの出力'), doneLog(2, 'flow', null, 'flow 1回目'), doneLog(3, 'klass', null, 'klass 出力'), doneLog(4, 'flow', 2, 'flow 2回目')],
  });

test('D0063-AC-11: terminalFor は選んだ段のいちばん新しい実行のログを返す', () => {
  const picked = terminalFor(TWO_RUNS_OF_FLOW(), 'flow');
  assert.equal(picked.stage, 'flow');
  assert.deepEqual(picked.terminal.source, { seq: 4, stage: 'flow', attempt: 2 });
  assert.deepEqual(textsOfItems(picked.terminal.items), ['flow 2回目']);
  const klass = terminalFor(TWO_RUNS_OF_FLOW(), 'klass');
  assert.equal(klass.stage, 'klass');
  assert.deepEqual(klass.terminal.source, { seq: 3, stage: 'klass', attempt: null });
  assert.deepEqual(textsOfItems(klass.terminal.items), ['klass 出力']);
});

test('D0063-AC-11: 選んだ段が動いているときは、その動いているログ（いちばん新しい実行）を返す', () => {
  const view = BOTH_RUNNING();
  const flow = terminalFor(view, 'flow');
  assert.deepEqual(flow.terminal.source, { seq: 2, stage: 'flow', attempt: null });
  assert.deepEqual(textsOfItems(flow.terminal.items), ['flowを作業中']);
});

test('D0063-AC-11: ログが無い段は source が null で items が空（「ログなし」の元）', () => {
  const view = groupView(SURVEY_DONE, { stageLogs: [doneLog(1, 'survey', null)] });
  const picked = terminalFor(view, 'klass');
  assert.equal(picked.stage, 'klass', '枠の中の段なので、選びは通る');
  assert.deepEqual(picked.terminal, { source: null, items: [] });
});

test('D0063-AC-11: groupLogs は枠の中の段ごとに、いちばん新しいログの出力を持つ（ログが無い段は空）', () => {
  const logs = groupLogsOf(TWO_RUNS_OF_FLOW());
  assert.ok(logs !== undefined, 'groupLogs がある（まだ作っていない）');
  assert.deepEqual(Object.keys(logs).sort(), ['flow', 'klass'], '枠の中の段だけ（枠の外の survey・report は入らない）');
  assert.deepEqual(logs.flow?.source, { seq: 4, stage: 'flow', attempt: 2 });
  const empty = groupLogsOf(groupView(SURVEY_DONE, { stageLogs: [doneLog(1, 'survey', null)] }));
  assert.deepEqual(empty?.klass, { source: null, items: [] });
});

test('D0063-AC-11: pickableLogStages は全部の枠の中の段（押して選べる節の段）', () => {
  assert.deepEqual(pickableLogStages(groupView([])), ['flow', 'klass']);
  const stages = [gStage('a', 'g1'), gStage('x'), gStage('b', 'g2'), gStage('c', 'g2')];
  assert.deepEqual(pickableLogStages(groupView([], { stages })), ['a', 'b', 'c']);
});

// ======== AC-12：選んだ段が枠の中にない・記録に無いとき ========

test('D0063-AC-12: 枠の外の段・記録に無い段・選びなしは、選びを無視して既定のログを返す', () => {
  const view = TWO_RUNS_OF_FLOW();
  for (const picked of ['survey', 'report', 'ghost', 'input', 'final', '', null]) {
    const got = terminalFor(view, picked);
    assert.equal(got.stage, null, `選び ${JSON.stringify(picked)} は無視される`);
    assert.deepEqual(got.terminal, view.terminal, `選び ${JSON.stringify(picked)} は既定のログ`);
  }
});

test('D0063-AC-12: 枠の無い記録・開発フローでは、どの名前を選んでも既定のログを返し、選べる段は空', () => {
  const plain = [gStage('survey'), gStage('flow'), gStage('klass')];
  const view = groupView([...SURVEY_DONE, runEntry('flow', 2)], { stages: plain, stageLogs: [doneLog(2, 'flow', null)] });
  assert.equal(terminalFor(view, 'flow').stage, null);
  assert.deepEqual(terminalFor(view, 'flow').terminal, view.terminal);
  assert.deepEqual(pickableLogStages(view), []);
  const dev = checkView([runEntry('requirements', 1)], { stageLogs: [doneLog(1, 'requirements', null)] });
  assert.equal(terminalFor(dev, 'requirements').stage, null);
  assert.deepEqual(pickableLogStages(dev), []);
});

// ======== AC-14：古い記録は今までと同じ節・同じ図 ========

test('D0063-AC-14: group の無い古い記録は、節も状態も今までと同じ（frames は無いか空）。今のまま通る。守る', () => {
  const stages = [stageDef({ name: 'draw' }), stageDef({ name: 'verify' })];
  const view = checkView([runEntry('draw', 1), runEntry('verify', 2)], { pipe: 'p', stages });
  assert.deepEqual(ids(view), ['input', 'draw', 'verify', 'final']);
  assert.deepEqual(
    view.nodes.map((n) => n.status),
    ['done', 'done', 'done', 'pending'],
  );
  assert.deepEqual(framesOf(view) ?? [], []);
});

test('D0063-AC-14: 判定の記録は、check:<段> が今までの位置に出る。今のまま通る。守る', () => {
  const stages = [stageDef({ name: 'draw' }), stageDef({ name: 'build', review: true, check: { on_fail: null, max_retries: 3 } }), stageDef({ name: 'ship' })];
  const view = checkView([runEntry('draw', 1)], { pipe: 'p', stages });
  assert.deepEqual(ids(view), ['input', 'draw', 'build', 'check:build', 'review:build', 'ship', 'final']);
  assert.deepEqual(framesOf(view) ?? [], []);
});

// 前の版の形（pipe_in/）・今の形（pipe_dev/・showcase*）の見本
const FIXTURE_DIRS: readonly (readonly string[])[] = [
  ['pipe_in', 'finished'],
  ['pipe_in', 'running'],
  ['pipe_in', 'waiting'],
  ['pipe_dev', 'finished'],
  ['pipe_dev', 'running'],
  ['pipe_dev', 'waiting'],
  ['showcase'],
  ['showcase_running'],
  ['showcase_running_next'],
  ['showcase_waiting'],
];
for (const parts of FIXTURE_DIRS) {
  test(`D0063-AC-14: 見本 ${parts.join('/')} の図の状態に枠は無い（frames は無いか空）。今のまま通る。守る`, () => {
    const view = buildPipelineView(fixtureSnapshot(...parts));
    assert.ok(view.nodes.length > 0, '節がある');
    assert.deepEqual(framesOf(view) ?? [], []);
  });
}
