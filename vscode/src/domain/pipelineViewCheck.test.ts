// 図の状態の判定の節（D0062 の AC-06〜08・AC-10 の選べる節・AC-12）：check:<段> の節の組み立て・状態・回数・理由の欄の元。
// 節の check（PipelineNode.check）は、実装の段で型に入るまで、型に頼らず読む（test/checkFixtures.ts の nodeCheckOf）。
// 赤の理由は「まだ組み立てていない」：check:<段> の節が図の状態に無い（nodeById が「節が図の状態に無い」で落とす）。
// 「今のまま通る。守る」と書いたものは、今の作りで通り、実装のあとも通り続けることを見張る（判定の節を出さない古い記録など）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { NODE_ORDER, buildPipelineView, nodeReasons, reasonNodeIds } from './pipelineView.ts';
import type { PipelineView } from './pipelineView.ts';
import { parseRunRecord } from './runRecord.ts';
import { nodeById, runningLogFile } from '../test/budgetFixtures.ts';
import { checkEntry, checkView, checksOf, nodeCheckOf, runEntry, stageDef } from '../test/checkFixtures.ts';
import type { CheckViewOptions } from '../test/checkFixtures.ts';
import { fixtureSnapshot } from '../test/liveFixtures.ts';

const BACK = { on_fail: 'draw', max_retries: 2 };
/** draw（判定なし）→ verify（前の段 draw へ戻す判定・上限 2 回） */
const BACK_STAGES = [stageDef({ name: 'draw' }), stageDef({ name: 'verify', check: BACK })];
const backOpts = (extra: CheckViewOptions = {}): CheckViewOptions => ({ pipe: 'p', stages: BACK_STAGES, ...extra });
const ids = (view: PipelineView): string[] => view.nodes.map((n) => n.id);
const fail = (attempt?: number) => checkEntry({ stage: 'verify', status: 'fail', ...(attempt === undefined ? {} : { attempt }) });
const pass = (attempt?: number) => checkEntry({ stage: 'verify', status: 'pass', ...(attempt === undefined ? {} : { attempt }) });

// ======== AC-06：判定のある段のあとに check:<段> の節が入る ========

test('D0062-AC-06: 判定のある段のあとに check:<段> の節が入る（確認の節の前）', () => {
  const stages = [
    stageDef({ name: 'draw' }),
    stageDef({ name: 'build', review: true, check: { on_fail: null, max_retries: 3 } }),
    stageDef({ name: 'ship' }),
  ];
  const view = checkView([runEntry('draw', 1)], { pipe: 'p', stages });
  assert.deepEqual(ids(view), ['input', 'draw', 'build', 'check:build', 'review:build', 'ship', 'final']);
});

test('D0062-AC-06: 判定のある段が 2 つあるとき、それぞれの直後に節が入る', () => {
  const stages = [stageDef({ name: 'draw', check: { on_fail: null, max_retries: 1 } }), stageDef({ name: 'verify', check: BACK })];
  assert.deepEqual(ids(checkView([], { pipe: 'p', stages })), ['input', 'draw', 'check:draw', 'verify', 'check:verify', 'final']);
});

test('D0062-AC-06: 判定のない段・stages[].check の無い記録では入らない（check の要素があっても）。今のまま通る。守る', () => {
  const stages = [stageDef({ name: 'draw' }), stageDef({ name: 'verify' })];
  const runs = [runEntry('draw', 1), runEntry('verify', 2), pass(1)];
  assert.deepEqual(ids(checkView(runs, { pipe: 'p', stages })), ['input', 'draw', 'verify', 'final']);
});

test('D0062-AC-06: 開発フローでは入らず、11 節は NODE_ORDER のまま（stages に check があっても）。今のまま通る。守る', () => {
  const dev = ['requirements', 'design', 'red', 'implement', 'test'].map((name) => stageDef({ name, check: BACK }));
  const stray = checkEntry({ stage: 'test', status: 'fail', attempt: 1 });
  assert.deepEqual(ids(checkView([stray])), [...NODE_ORDER], 'stages が無い記録');
  assert.deepEqual(ids(checkView([stray], { pipe: 'dev', stages: dev })), [...NODE_ORDER], '開発の 5 段の記録');
});

// ======== AC-07：節の状態 ========

test('D0062-AC-07: 最新の検証が pass なら done', () => {
  const view = checkView([runEntry('draw', 1), runEntry('verify', 2), pass(1)], backOpts());
  assert.equal(nodeById(view, 'check:verify').status, 'done');
});

test('D0062-AC-07: 最新の検証が fail なら failed（動いている段が無いとき）', () => {
  const view = checkView([runEntry('draw', 1), runEntry('verify', 2), fail(1)], backOpts());
  assert.equal(nodeById(view, 'check:verify').status, 'failed');
});

test('D0062-AC-07: 1 回目 fail → 2 回目 pass なら done、1 回目 pass → 2 回目 fail なら failed（最新の 1 件で決まる）', () => {
  const failThenPass = [runEntry('draw', 1), runEntry('verify', 2), fail(1), runEntry('draw', 3), runEntry('verify', 4), pass(2)];
  assert.equal(nodeById(checkView(failThenPass, backOpts()), 'check:verify').status, 'done');
  const passThenFail = [runEntry('verify', 1), pass(1), runEntry('verify', 2), fail(2)];
  assert.equal(nodeById(checkView(passThenFail, backOpts()), 'check:verify').status, 'failed');
});

test('D0062-AC-07: 検証がまだ無いときは pending', () => {
  assert.equal(nodeById(checkView([runEntry('draw', 1), runEntry('verify', 2)], backOpts()), 'check:verify').status, 'pending');
  assert.equal(nodeById(checkView([], backOpts()), 'check:verify').status, 'pending', '記録に実行が無いとき');
});

test('D0062-AC-07: その段が動いている間は、前の検証が pass でも fail でも pending', () => {
  for (const earlier of [pass(1), fail(1)]) {
    const view = checkView([runEntry('draw', 1), runEntry('verify', 2), earlier], backOpts({ stageLogs: [runningLogFile(3, 'verify', 2)] }));
    assert.equal(view.runningStage, 'verify');
    assert.equal(nodeById(view, 'check:verify').status, 'pending');
  }
});

test('D0062-AC-07: やり直したがまだ検証されていない（段の実行の数が検証の数より多い）間は pending', () => {
  const runs = [runEntry('draw', 1), runEntry('verify', 2), fail(1), runEntry('draw', 3), runEntry('verify', 4)];
  assert.equal(nodeById(checkView(runs, backOpts()), 'check:verify').status, 'pending');
});

test('D0062-AC-07: 最新が fail で、別の段（戻り先）が動いている間は pending', () => {
  const runs = [runEntry('draw', 1), runEntry('verify', 2), fail(1)];
  const view = checkView(runs, backOpts({ stageLogs: [runningLogFile(3, 'draw', 2)] }));
  assert.equal(view.runningStage, 'draw');
  assert.equal(nodeById(view, 'check:verify').status, 'pending');
});

// ======== AC-08：回数と上限 ========

test('D0062-AC-08: 1 回目 fail → 2 回目 pass は retries 1・上限は max_retries（前の段へ戻す）', () => {
  const runs = [runEntry('draw', 1), runEntry('verify', 2), fail(1), runEntry('draw', 3), runEntry('verify', 4), pass(2)];
  assert.deepEqual(nodeCheckOf(nodeById(checkView(runs, backOpts()), 'check:verify')), {
    kind: 'back',
    onFail: 'draw',
    retries: 1,
    maxRetries: 2,
    exhausted: false,
  });
});

test('D0062-AC-08: on_fail が null の判定は kind が self・onFail が null（上限 3 で 1 回やり直した）', () => {
  const stages = [stageDef({ name: 'verify', check: { on_fail: null, max_retries: 3 } })];
  const runs = [runEntry('verify', 1), fail(1), runEntry('verify', 2), pass(2)];
  assert.deepEqual(nodeCheckOf(nodeById(checkView(runs, { pipe: 'p', stages }), 'check:verify')), {
    kind: 'self',
    onFail: null,
    retries: 1,
    maxRetries: 3,
    exhausted: false,
  });
});

test('D0062-AC-08: 1 回目の検証だけなら retries 0、検証がまだ無ければ retries は null', () => {
  const first = nodeCheckOf(nodeById(checkView([runEntry('draw', 1), runEntry('verify', 2), pass(1)], backOpts()), 'check:verify'));
  assert.equal((first as { retries: unknown } | undefined)?.retries, 0);
  const none = nodeCheckOf(nodeById(checkView([runEntry('draw', 1)], backOpts()), 'check:verify'));
  assert.deepEqual(none, { kind: 'back', onFail: 'draw', retries: null, maxRetries: 2, exhausted: false });
});

test('D0062-AC-08: attempt の無い要素は並びの番号を使い、上限が記録に無ければ maxRetries は null', () => {
  const stages = [stageDef({ name: 'verify', check: { on_fail: null } })];
  const runs = [runEntry('verify', 1), fail(), runEntry('verify', 2), pass()];
  const node = nodeById(checkView(runs, { pipe: 'p', stages }), 'check:verify');
  assert.equal(node.status, 'done');
  assert.deepEqual(nodeCheckOf(node), { kind: 'self', onFail: null, retries: 1, maxRetries: null, exhausted: false });
});

test('D0062-AC-08: attempt の無い要素でも、attempt のある同じ記録と節の状態・回数が同じ', () => {
  const body = (withAttempt: boolean): object[] => [
    runEntry('draw', 1),
    runEntry('verify', 2),
    withAttempt ? fail(1) : fail(),
    runEntry('draw', 3),
    runEntry('verify', 4),
    withAttempt ? pass(2) : pass(),
  ];
  const a = nodeById(checkView(body(true), backOpts()), 'check:verify');
  const b = nodeById(checkView(body(false), backOpts()), 'check:verify');
  assert.deepEqual(b, a);
});

test('D0062-AC-08: 戻り先の段が stages に無い・自分自身のときは self に正す（onFail は null）', () => {
  for (const onFail of ['ghost', 'verify']) {
    const stages = [stageDef({ name: 'verify', check: { on_fail: onFail, max_retries: 2 } })];
    const check = nodeCheckOf(nodeById(checkView([runEntry('verify', 1), pass(1)], { pipe: 'p', stages }), 'check:verify'));
    assert.deepEqual(check, { kind: 'self', onFail: null, retries: 0, maxRetries: 2, exhausted: false }, onFail);
  }
});

test('D0062-AC-08: 上限 + 1 回目で fail なら exhausted（failed で retries は上限と同じ）', () => {
  const runs = [runEntry('draw', 1), runEntry('verify', 2), fail(1), runEntry('draw', 3), runEntry('verify', 4), fail(2), runEntry('draw', 5), runEntry('verify', 6), fail(3)];
  const node = nodeById(checkView(runs, backOpts()), 'check:verify');
  assert.equal(node.status, 'failed');
  assert.deepEqual(nodeCheckOf(node), { kind: 'back', onFail: 'draw', retries: 2, maxRetries: 2, exhausted: true });
});

test('D0062-AC-08: exhausted にならない場合：上限の手前の fail・上限 + 1 回目の pass・上限が記録に無い fail・上限 0 の 1 回目 fail は exhausted', () => {
  const exhaustedOf = (runs: object[], check: unknown = BACK): unknown => {
    const stages = [stageDef({ name: 'draw' }), stageDef({ name: 'verify', check })];
    return (nodeCheckOf(nodeById(checkView(runs, { pipe: 'p', stages }), 'check:verify')) as { exhausted: unknown } | undefined)?.exhausted;
  };
  const upTo = (n: number, last: 'pass' | 'fail'): object[] =>
    Array.from({ length: n }, (_, i) => [runEntry('verify', i + 1), i === n - 1 && last === 'pass' ? pass(i + 1) : fail(i + 1)]).flat();
  assert.equal(exhaustedOf(upTo(2, 'fail')), false, '上限の手前（2 回目）の fail');
  assert.equal(exhaustedOf(upTo(3, 'pass')), false, '上限 + 1 回目の pass');
  assert.equal(exhaustedOf(upTo(9, 'fail'), { on_fail: 'draw' }), false, '上限が記録に無い');
  assert.equal(exhaustedOf(upTo(1, 'fail'), { on_fail: 'draw', max_retries: 0 }), true, '上限 0 の 1 回目の fail');
});

// ======== AC-10：選べる節と理由の元 ========

test('D0062-AC-10: 検証が 1 件以上ある check 節だけ選べる', () => {
  const stages = [stageDef({ name: 'draw', check: { on_fail: null, max_retries: 1 } }), stageDef({ name: 'verify', check: BACK })];
  const view = checkView([runEntry('draw', 1), checkEntry({ stage: 'draw', status: 'pass', attempt: 1 })], { pipe: 'p', stages });
  assert.ok(ids(view).includes('check:verify'), '検証が無い節も図にはある');
  const selectable = reasonNodeIds(view);
  assert.ok(selectable.includes('check:draw'), '検証がある節は選べる');
  assert.ok(!selectable.includes('check:verify'), '検証がまだ無い節は選べない');
  assert.equal(nodeReasons(view, 'check:verify'), null);
});

test('D0062-AC-10: nodeReasons は、その段の検証を古い順に回・合否・要約・直す点で返す', () => {
  const runs = [
    runEntry('draw', 1),
    runEntry('verify', 2),
    checkEntry({ stage: 'verify', status: 'fail', attempt: 1, summary: '図が足りない', problems: ['矢印が逆', '凡例が無い'] }),
    runEntry('draw', 3),
    runEntry('verify', 4),
    checkEntry({ stage: 'verify', status: 'pass', attempt: 2, summary: 'よい', problems: [] }),
  ];
  const reasons = nodeReasons(checkView(runs, backOpts()), 'check:verify');
  assert.deepEqual(reasons, {
    kind: 'check',
    stage: 'verify',
    label: 'verifyの段',
    items: [
      { attempt: 1, status: 'fail', summary: '図が足りない', problems: ['矢印が逆', '凡例が無い'] },
      { attempt: 2, status: 'pass', summary: 'よい', problems: [] },
    ],
  });
});

test('D0062-AC-10: 別の段の検証は混ざらず、attempt の無い要素の回は並びの番号', () => {
  const stages = [stageDef({ name: 'draw', check: { on_fail: null, max_retries: 2 } }), stageDef({ name: 'verify', check: BACK })];
  const runs = [
    checkEntry({ stage: 'draw', status: 'fail', summary: 'draw の 1 回目' }),
    checkEntry({ stage: 'verify', status: 'fail', summary: 'verify の 1 回目' }),
    checkEntry({ stage: 'draw', status: 'pass', summary: 'draw の 2 回目' }),
  ];
  const reasons = nodeReasons(checkView(runs, { pipe: 'p', stages }), 'check:draw');
  assert.equal(reasons?.kind, 'check');
  assert.deepEqual(
    reasons?.kind === 'check' ? reasons.items.map((i) => [i.attempt, i.summary]) : null,
    [
      [1, 'draw の 1 回目'],
      [2, 'draw の 2 回目'],
    ],
  );
});

// ======== AC-12：古い記録は今までと同じ節・同じ状態 ========

const SAME_RUNS = [runEntry('draw', 1), runEntry('verify', 2), runEntry('draw', 3), runEntry('verify', 4)];

test('D0062-AC-12: (a) stages[].check の無い記録は、check の要素があっても、それを除いた同じ記録と節も状態も同じ。今のまま通る。守る', () => {
  const stages = [stageDef({ name: 'draw' }), stageDef({ name: 'verify' })];
  const withChecks = checkView([...SAME_RUNS, fail(1), pass(2)], { pipe: 'p', stages });
  const without = checkView(SAME_RUNS, { pipe: 'p', stages });
  assert.deepEqual(withChecks.nodes, without.nodes);
  assert.deepEqual(ids(withChecks), ['input', 'draw', 'verify', 'final']);
});

test('D0062-AC-12: (b) attempt の無い check の要素でも、判定の節が出て、attempt のある記録と同じ節・同じ状態', () => {
  const plain = checkView([...SAME_RUNS, fail(), pass()], backOpts());
  const numbered = checkView([...SAME_RUNS, fail(1), pass(2)], backOpts());
  assert.deepEqual(ids(plain), ['input', 'draw', 'verify', 'check:verify', 'final']);
  assert.deepEqual(plain.nodes, numbered.nodes);
});

test('D0062-AC-12: (c) 判定の無いパイプは、判定の節が無く、節の並びは今までと同じ。今のまま通る。守る', () => {
  const stages = [stageDef({ name: 'a' }), stageDef({ name: 'b', review: true }), stageDef({ name: 'c' })];
  const view = checkView([runEntry('a', 1), runEntry('b', 2)], { pipe: 'p', stages });
  assert.deepEqual(ids(view), ['input', 'a', 'b', 'review:b', 'c', 'final']);
});

test('D0062-AC-12: (d) 開発フローの記録は、check の要素が紛れても節が変わらない。今のまま通る。守る', () => {
  const dev = ['requirements', 'design', 'red', 'implement', 'test'].map((name, i) => runEntry(name, i + 1));
  const clean = checkView(dev);
  const noisy = checkView([...dev, checkEntry({ stage: 'test', status: 'fail', attempt: 1 })]);
  assert.deepEqual(noisy.nodes, clean.nodes);
  assert.deepEqual(ids(noisy), [...NODE_ORDER]);
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
  const name = parts.join('/');
  test(`D0062-AC-12: 見本 ${name} の図の状態に判定の節は無い。今のまま通る。守る`, () => {
    const view = buildPipelineView(fixtureSnapshot(...parts));
    assert.ok(view.nodes.length > 0, '節がある');
    assert.deepEqual(ids(view).filter((id) => id.startsWith('check:')), []);
  });
  test(`D0062-AC-12: 見本 ${name} を読むと checks は空（check の項目が無い記録でも例外が出ない）`, () => {
    assert.deepEqual(checksOf(parseRunRecord(fixtureSnapshot(...parts).stateJson)), []);
  });
}
