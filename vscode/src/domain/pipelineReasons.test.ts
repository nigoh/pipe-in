// 差し戻し・確認の直しの一覧と、理由を持つ節（D0016）。図の状態の組み立て（純粋）。
// nodeReasons・reasonNodeIds は名前空間（pv）から呼ぶ。テスト先行のとき、関数が無くても import では落ちず、
// 呼んだところで落ちるようにした名残り。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as pv from './pipelineView.ts';
import { buildPipelineView } from './pipelineView.ts';
import { snapshot, stageRunEntry, stateJson } from '../test/fixtures.ts';
import {
  failVerdict,
  implementAndTest,
  oneSendBackView,
  passVerdict,
  pipeView,
  readFixtureState,
  reviseEntry,
  showcaseView,
  unresolvedView,
  viewOf,
} from '../test/reasonFixtures.ts';

const BOM_DETAIL = '出力の先頭に BOM が無く、Excel で開くと文字化けする';
const node = (view: pv.PipelineView, id: string) => view.nodes.find((n) => n.id === id)!;

test('D0016-AC-03: showcase の差し戻し一覧が1件で、戻り先・要約・直す点を持ち、実装の sendBackCount と一致する', () => {
  const view = showcaseView();
  assert.deepEqual(view.sendBacks, [
    {
      attempt: 1,
      target: 'implement',
      targetLabel: '実装',
      summary: 'AC-02 が不合格（BOM が無い）',
      failures: [{ criterion: 'AC-02', detail: BOM_DETAIL }],
      sentBack: true,
    },
  ]);
  assert.equal(node(view, 'implement').sendBackCount, 1);
  assert.equal(view.sendBacks.length, node(view, 'implement').sendBackCount);
});

test('D0016-AC-03: 開発フローの見本（pipe_in/finished）でも、差し戻しの数が実装の sendBackCount と一致する', () => {
  const view = viewOf(readFixtureState('pipe_in', 'finished'));
  assert.deepEqual(
    view.sendBacks.map((s) => [s.attempt, s.sentBack, s.failures]),
    [[1, true, [{ criterion: 'AC-01', detail: '期待と違う' }]]],
  );
  assert.equal(view.sendBacks.length, node(view, 'implement').sendBackCount);
});

test('D0016-AC-04: 不合格が2回なら古い順に2件で、合格の判定は入らない', () => {
  const view = viewOf(
    stateJson({
      runs: [
        ...implementAndTest(1),
        failVerdict({ attempt: 1, summary: '1回目', failures: [{ criterion: 'AC-01', detail: 'a' }] }),
        ...implementAndTest(2),
        failVerdict({ attempt: 2, summary: '2回目', failures: [{ criterion: 'AC-02', detail: 'b' }] }),
        ...implementAndTest(3),
        passVerdict(3),
      ],
    }),
  );
  assert.deepEqual(
    view.sendBacks.map((s) => [s.attempt, s.summary, s.sentBack]),
    [
      [1, '1回目', true],
      [2, '2回目', true],
    ],
  );
  assert.equal(node(view, 'implement').sendBackCount, 2);
});

test('D0016-AC-04: 合格だけの記録では差し戻し一覧が空', () => {
  const view = viewOf(stateJson({ runs: [...implementAndTest(1), passVerdict(1)] }));
  assert.deepEqual(view.sendBacks, []);
});

test('D0016-AC-04: blocked の判定は差し戻し一覧に入らない', () => {
  const blocked = { stage: 'test', attempt: 1, verdict: { status: 'blocked', summary: '動かせない', failures: [] } };
  const view = viewOf(stateJson({ runs: [...implementAndTest(1), blocked] }));
  assert.deepEqual(view.sendBacks, []);
});

test('D0016-AC-05: やり直しの実装が無いまま終わった不合格は sentBack が false', () => {
  const view = unresolvedView();
  assert.deepEqual(
    view.sendBacks.map((s) => [s.attempt, s.sentBack]),
    [[1, false]],
  );
});

test('D0016-AC-05: 不合格のあとに実装のやり直しがあれば sentBack が true', () => {
  const view = viewOf(
    stateJson({ runs: [...implementAndTest(1), failVerdict({ attempt: 1 }), stageRunEntry({ stage: 'implement', seq: 3, attempt: 2 })] }),
  );
  assert.deepEqual(
    view.sendBacks.map((s) => s.sentBack),
    [true],
  );
});

test('D0016-AC-05: 最後の不合格だけが sentBack false（前の不合格はやり直しがあったので true）', () => {
  const view = viewOf(
    stateJson({
      runs: [
        ...implementAndTest(1),
        failVerdict({ attempt: 1 }),
        ...implementAndTest(2),
        failVerdict({ attempt: 2 }),
      ],
    }),
  );
  assert.deepEqual(
    view.sendBacks.map((s) => [s.attempt, s.sentBack]),
    [
      [1, true],
      [2, false],
    ],
  );
});

test('D0016-AC-05: attempt の無い判定の sentBack は、後ろに判定があるかで決まる（回数は不合格の並びの番号）', () => {
  const view = viewOf(
    stateJson({
      runs: [
        ...implementAndTest(1),
        failVerdict({ attempt: null, summary: '前' }),
        ...implementAndTest(2),
        failVerdict({ attempt: null, summary: '後' }),
      ],
    }),
  );
  assert.deepEqual(
    view.sendBacks.map((s) => [s.attempt, s.summary, s.sentBack]),
    [
      [1, '前', true],
      [2, '後', false],
    ],
  );
});

test('D0016-AC-05: attempt の無い不合格のあとに合格の判定があれば sentBack は true', () => {
  const view = viewOf(stateJson({ runs: [...implementAndTest(1), failVerdict({ attempt: null }), ...implementAndTest(2), passVerdict(null)] }));
  assert.deepEqual(
    view.sendBacks.map((s) => s.sentBack),
    [true],
  );
});

test('D0016-AC-06: showcase の確認の直しが requirements の1件（1回目・feedback つき）', () => {
  assert.deepEqual(showcaseView().revisions, [
    { stage: 'requirements', label: '要件定義', attempt: 1, feedback: "AC-02 を『文字コード』と『列の順』に分けて" },
  ]);
});

test('D0016-AC-06: feedback が null の revise は理由なしの1件になる', () => {
  const view = viewOf(stateJson({ runs: [stageRunEntry({ stage: 'design', seq: 1 }), reviseEntry('design', null)] }));
  assert.deepEqual(view.revisions, [{ stage: 'design', label: '設計', attempt: 1, feedback: null }]);
});

test('D0016-AC-06: 同じ段の revise は段ごとに 1, 2 と数え、古い順に並ぶ。approved は入らない', () => {
  const view = viewOf(
    stateJson({
      runs: [
        reviseEntry('requirements', 'a'),
        reviseEntry('design', 'x'),
        reviseEntry('requirements', 'b'),
        { stage: 'requirements', review: 'approved' },
        { stage: 'design', review: 'quit' },
      ],
    }),
  );
  assert.deepEqual(
    view.revisions.map((r) => [r.stage, r.attempt, r.feedback]),
    [
      ['requirements', 1, 'a'],
      ['design', 1, 'x'],
      ['requirements', 2, 'b'],
    ],
  );
});

test('D0016-AC-07: パイプの記録では差し戻し一覧が空で、確認の直しは読める（check と判定の形の要素は読み捨てる）', () => {
  const view = pipeView();
  assert.deepEqual(view.sendBacks, []);
  assert.deepEqual(view.revisions, [{ stage: 'survey', label: 'ソースの調査', attempt: 1, feedback: '範囲を絞って' }]);
});

test('D0016-AC-07: パイプでは確認の節だけが理由を持つ（実装・判定の節は無い）', () => {
  const view = pipeView();
  assert.deepEqual(pv.reasonNodeIds(view), ['review:survey']);
  assert.equal(pv.nodeReasons(view, 'review:survey')?.kind, 'revise');
});

test('D0016-AC-08: 古い記録（stages も failures も無い）は節の数・状態・回数が今までと同じで、一覧は空', () => {
  const old = stateJson({
    runs: [
      stageRunEntry({ stage: 'requirements', seq: 1 }),
      { stage: 'requirements', review: 'approved' },
      ...implementAndTest(1),
      ...implementAndTest(2),
    ],
  });
  const view = buildPipelineView(snapshot({ stateJson: old }));
  assert.equal(view.nodes.length, 11);
  assert.equal(node(view, 'implement').sendBackCount, 1);
  assert.equal(node(view, 'review:requirements').reviseCount, 0);
  assert.equal(node(view, 'review:requirements').status, 'done');
  assert.equal(node(view, 'verdict').status, 'pending');
  assert.deepEqual(view.sendBacks, []);
  assert.deepEqual(view.revisions, []);
});

test('D0016-AC-14: failures の無い古い不合格の判定も1件として一覧に入る（直す点は空。無かったことにしない）', () => {
  const old = stateJson({
    runs: [...implementAndTest(1), { stage: 'test', attempt: 1, verdict: { status: 'fail', summary: '古い形' } }, ...implementAndTest(2)],
  });
  const view = buildPipelineView(snapshot({ stateJson: old }));
  assert.deepEqual(view.sendBacks, [{ attempt: 1, target: 'implement', targetLabel: '実装', summary: '古い形', failures: [], sentBack: true }]);
});

test('D0016-AC-08: 記録が無い・verdict が無い記録でも、一覧は空で節は11個のまま', () => {
  for (const text of [null, '{"runs": [', stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] })]) {
    const view = buildPipelineView(snapshot({ stateJson: text }));
    assert.equal(view.nodes.length, 11);
    assert.deepEqual(view.sendBacks, []);
    assert.deepEqual(view.revisions, []);
    assert.deepEqual(pv.reasonNodeIds(view), []);
  }
});

test('D0016-AC-14: 理由を持つ節は、差し戻しなら実装・判定、確認の直しなら その段の確認だけ', () => {
  const ids = pv.reasonNodeIds(showcaseView());
  assert.deepEqual([...ids].sort(), ['implement', 'review:requirements', 'verdict']);
});

test('D0016-AC-14: 履歴の無い記録では理由を持つ節が無く、nodeReasons はどの節でも null', () => {
  const view = buildPipelineView(snapshot());
  assert.deepEqual(pv.reasonNodeIds(view), []);
  for (const n of view.nodes) assert.equal(pv.nodeReasons(view, n.id), null, n.id);
});

test('D0016-AC-14: nodeReasons は実装・判定で差し戻しの一覧、確認でその段の直しの一覧、ほかは null', () => {
  const view = showcaseView();
  const implement = pv.nodeReasons(view, 'implement');
  assert.equal(implement?.kind, 'sendBack');
  assert.deepEqual(implement?.kind === 'sendBack' ? implement.items : null, view.sendBacks);
  assert.deepEqual(pv.nodeReasons(view, 'verdict'), implement);
  const review = pv.nodeReasons(view, 'review:requirements');
  assert.deepEqual(review, { kind: 'revise', stage: 'requirements', label: '要件定義', items: view.revisions });
  for (const id of ['input', 'requirements', 'design', 'review:design', 'red', 'review:red', 'test', 'final', 'no-such-node']) {
    assert.equal(pv.nodeReasons(view, id), null, id);
  }
});

test('D0016-AC-14: 履歴が無いのに確認の節がある段は、nodeReasons が null（revise は別の段にだけある）', () => {
  const view = viewOf(stateJson({ runs: [reviseEntry('design', 'x')] }));
  assert.equal(pv.nodeReasons(view, 'review:requirements'), null);
  assert.equal(pv.nodeReasons(view, 'implement'), null);
  assert.deepEqual(pv.reasonNodeIds(view), ['review:design']);
});

test('D0016-AC-14: 確認の節が無い段の revise は、節が無いので選べる節に入らない（パイプで review が false の段）', () => {
  const view = viewOf(
    stateJson({
      pipe: 'p',
      stages: [
        { name: 'a', label: '調べる', output: '01_a.md', review: false },
        { name: 'b', label: '書く', output: '02_b.md', review: true },
      ],
      runs: [stageRunEntry({ stage: 'a', seq: 1 }), reviseEntry('a', 'どこにも出ない')],
    }),
  );
  assert.deepEqual(pv.reasonNodeIds(view), []);
  assert.equal(pv.nodeReasons(view, 'review:a'), null);
});

test('D0016-AC-15: failures が100件・detail が1万文字でも組み立てが終わり、節の並びは変わらない', () => {
  const base = oneSendBackView({});
  const failures = Array.from({ length: 100 }, (_, i) => ({ criterion: `AC-${i}`, detail: 'あ'.repeat(10000) }));
  const big = oneSendBackView({ summary: 'い'.repeat(10000), failures });
  assert.equal(big.sendBacks.length, 1);
  assert.equal(big.sendBacks[0].failures.length, 100);
  assert.equal(big.sendBacks[0].failures[99].detail.length, 10000);
  assert.deepEqual(
    big.nodes,
    base.nodes,
    '直す点の数・長さで、節の並び・状態・回数が変わらない',
  );
  assert.deepEqual(pv.reasonNodeIds(big), pv.reasonNodeIds(base));
});
