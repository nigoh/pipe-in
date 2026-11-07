// D0077-AC-24（図の形）：会話の道（pipe-in-gen chat）で流した記録も、段の流れ・確認待ち・差し戻しが本体の記録と同じ形で図に出る。
// driver が pipe-chat で、費用が null（取れない）でも、buildPipelineView は検証の戻り・確認待ち・revise を本体の記録と同じに出す。
// どれも今の作りで通る（図の形は変えず、費用の欄だけを「取れない」にするため）。守り続けるための検査として置く。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPipelineView, nodeReasons, reasonNodeIds } from './pipelineView.ts';
import type { PipelineNode, PipelineView } from './pipelineView.ts';
import { parseRunRecord } from './runRecord.ts';
import { chatSnapshot, fullRuns, waitingSnapshot } from '../test/chatFixtures.ts';
import { nodeById } from '../test/budgetFixtures.ts';
import { nodeCheckOf } from '../test/checkFixtures.ts';

/** 図の形だけ（費用・時間・使用量は除く）。 */
function shape(view: PipelineView): unknown {
  return view.nodes.map((n: PipelineNode) => ({ id: n.id, label: n.label, status: n.status, reviseCount: n.reviseCount, sendBackCount: n.sendBackCount, check: nodeCheckOf(n) ?? null }));
}

const done = (): PipelineView => buildPipelineView(chatSnapshot({ final: 'PASSED' }));

test('D0077-AC-24: chat の記録は、依頼メモ・段・判定・確認・完了の節が、段の並びの順に出る（今のまま通る。守る）', () => {
  assert.deepEqual(
    done().nodes.map((n) => n.id),
    ['input', 'draft', 'review:draft', 'verify', 'check:verify', 'final'],
  );
  assert.equal(parseRunRecord(chatSnapshot().stateJson).hasDriver, true);
});

test('D0077-AC-24: chat の記録の節の状態は、確認が承認済み・判定が合格・完了が完了（今のまま通る。守る）', () => {
  const view = done();
  for (const id of ['draft', 'review:draft', 'verify', 'check:verify', 'final']) assert.equal(nodeById(view, id).status, 'done', id);
  assert.equal(view.final, 'PASSED');
});

test('D0077-AC-24: 確認の差し戻し（revise）が、回数と直す点つきで図に出る（今のまま通る。守る）', () => {
  const view = done();
  assert.equal(nodeById(view, 'review:draft').reviseCount, 1);
  assert.deepEqual(
    view.revisions.map((r) => [r.stage, r.label, r.attempt, r.feedback]),
    [['draft', '下書き', 1, 'ここを直して']],
  );
  const reasons = nodeReasons(view, 'review:draft');
  assert.equal(reasons?.kind, 'revise');
  assert.ok(reasonNodeIds(view).includes('review:draft'));
});

test('D0077-AC-24: 検証の戻り（不合格 → 下書きへ戻す → 合格）が、判定の節に回数・戻り先・直す点つきで出る（今のまま通る。守る）', () => {
  const view = done();
  const check = nodeCheckOf(nodeById(view, 'check:verify')) as { kind: string; onFail: string | null; retries: number | null; maxRetries: number | null; exhausted: boolean };
  assert.deepEqual(check, { kind: 'back', onFail: 'draft', retries: 1, maxRetries: 2, exhausted: false });
  assert.deepEqual(
    view.checkResults?.verify?.map((c) => [c.attempt, c.status, c.problems]),
    [
      [1, 'fail', ['矢印が逆']],
      [2, 'pass', []],
    ],
  );
  const reasons = nodeReasons(view, 'check:verify');
  assert.equal(reasons?.kind, 'check');
});

test('D0077-AC-24: 確認待ち（pending_review）が図に出る（今のまま通る。守る）', () => {
  const view = buildPipelineView(waitingSnapshot());
  assert.deepEqual(view.pendingReview, { stage: 'draft', label: '下書き', doc: 'docs/pipeline/cp/01_draft.md' });
  assert.equal(nodeById(view, 'draft').status, 'done');
  assert.equal(nodeById(view, 'review:draft').status, 'pending');
  assert.equal(view.final, null);
});

test('D0077-AC-24: chat の記録の図の形は、同じ流れの本体の記録（driver なし・費用が数）と同じ（今のまま通る。守る）', () => {
  const twin = buildPipelineView(chatSnapshot({ runs: fullRuns(0.01), usageSummary: 'old', totalCostUsd: 1.234, final: 'PASSED', driver: false }));
  assert.deepEqual(shape(done()), shape(twin));
  assert.deepEqual(done().revisions, twin.revisions);
  assert.deepEqual(done().checkResults, twin.checkResults);
});
