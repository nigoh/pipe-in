// 図の状態 PipelineView に、返事を受け付けている確認待ち（reply）が入る（D0079・AC-31・32・33・34・40・51 の支え）。
// buildPipelineView は canReply（domain/replyWait.ts）が真のときだけ view.reply を作る。項目 reply・hasDriver・pausePipe はまだ型に無いので、値を読んで比べる。
// 写しの項目 other（別の worktree）・replyFile（reply.json の有無と更新時刻）も、まだ型に無い（型を越えて足す）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { WAITING_MESSAGE } from './pipelineView.ts';
import { renderViewBody } from '../view/panelHtml.ts';
import { clockAt } from '../test/liveFixtures.ts';
import { MARK_ID, hasDriverOf, mark, pausePipeOf, pending, replyOf, replySnapshot, replyState, replyView, withKeys } from '../test/replyFixtures.ts';

const NOW = clockAt(40).nowMs;

// ---- AC-31：view.reply ができる条件 ----

test('D0079-AC-31: 開発フローで印のある記録は view.reply ができる：段・表示名・識別子・確認する文書・待ち始めからの秒', () => {
  assert.deepEqual(replyOf(replyView()), {
    stage: 'requirements',
    label: '要件定義',
    id: MARK_ID,
    doc: '01_requirements.md',
    waitingSec: 40,
    sent: false,
    stalled: false,
  });
});

test('D0079-AC-31: パイプで印のある記録は、パイプの段の表示名と成果物の名前になる', () => {
  assert.deepEqual(replyOf(replyView({ pipe: 'reply-pipe' })), {
    stage: 'survey',
    label: 'ソースの調査',
    id: MARK_ID,
    doc: '01_survey.md',
    waitingSec: 40,
    sent: false,
    stalled: false,
  });
});

const NO_REPLY: readonly (readonly [string, Parameters<typeof replyView>[0]])[] = [
  ['印なし（古い本体の記録）', { mark: null }],
  ['終わった', { final: 'PASSED' }],
  ['driver が pipe-dev（/pipe-in の記録）', { driver: 'pipe-dev' }],
  ['driver が pipe-chat（会話の道）', { driver: 'pipe-chat' }],
  ['pending_review あり（--pause の記録）', { pendingReview: pending() }],
  ['動いている段がある', { running: true }],
  ['archive/ の前の実行', { previous: true }],
  ['別の worktree の実行', { other: true }],
];
for (const [label, options] of NO_REPLY) {
  test(`D0079-AC-31: 条件を崩した記録は view.reply が無い（null）：${label}（今のまま通る。守る）`, () => {
    assert.equal(replyOf(replyView(options)), null);
  });
}

test('D0079-AC-31: 形の違う印（識別子が 9 文字）は印なしと同じで、view.reply が無い（今のまま通る。守る）', () => {
  assert.equal(replyOf(replyView({ mark: mark({ id: 'a1b2c3d4e' }) })), null);
});

// ---- AC-51 の元：「送りました」と 30 秒の案内（返事のファイルの写し） ----

test('D0079-AC-51: 返事のファイルが無い・写しに項目が無いとき sent は偽、有るとき真。30 秒たつと stalled が真になる（29 秒では偽）', () => {
  const read = (replyFile: { mtimeMs: number | null } | null | undefined) => replyOf(replyView(replyFile === undefined ? {} : { replyFile }));
  assert.deepEqual([read(undefined)?.sent, read(undefined)?.stalled], [false, false], '項目なし');
  assert.deepEqual([read(null)?.sent, read(null)?.stalled], [false, false], 'null（無い）');
  assert.deepEqual([read({ mtimeMs: NOW - 5_000 })?.sent, read({ mtimeMs: NOW - 5_000 })?.stalled], [true, false], '5 秒前');
  assert.deepEqual([read({ mtimeMs: NOW - 29_000 })?.sent, read({ mtimeMs: NOW - 29_000 })?.stalled], [true, false], '29 秒前');
  assert.deepEqual([read({ mtimeMs: NOW - 30_000 })?.sent, read({ mtimeMs: NOW - 30_000 })?.stalled], [true, true], '30 秒前');
  assert.deepEqual([read({ mtimeMs: NOW - 600_000 })?.sent, read({ mtimeMs: NOW - 600_000 })?.stalled], [true, true], '10 分前');
});

test('D0079-AC-51: 更新時刻が読めない（null）・「今」より先のときは、送った表示は出るが 30 秒の案内は出ない', () => {
  assert.deepEqual([replyOf(replyView({ replyFile: { mtimeMs: null } }))?.sent, replyOf(replyView({ replyFile: { mtimeMs: null } }))?.stalled], [true, false]);
  assert.deepEqual([replyOf(replyView({ replyFile: { mtimeMs: NOW + 60_000 } }))?.sent, replyOf(replyView({ replyFile: { mtimeMs: NOW + 60_000 } }))?.stalled], [true, false]);
});

test('D0079-AC-51: 条件を崩した記録では、返事のファイルが有っても view.reply は無い（送りましたを出さない）（今のまま通る。守る）', () => {
  assert.equal(replyOf(replyView({ final: 'PASSED', replyFile: { mtimeMs: NOW - 60_000 } })), null);
  assert.equal(replyOf(replyView({ mark: null, replyFile: { mtimeMs: NOW - 60_000 } })), null);
});

// ---- 節と経過：印も待ちとして数える（設計 2.3） ----

test('D0079-AC-34: 印のある記録は、確認の節に待ち始めからの秒が付き、全体の経過は数え上げ（live）になる', () => {
  const view = replyView();
  const node = view.nodes.find((n) => n.id === 'review:requirements');
  assert.equal(node?.waitingSec, 40);
  assert.equal(view.elapsed?.live, true);
});

test('D0079-AC-34: 印の始めた時刻が読めない記録は、待ち時間が出ない（null）：数え上げの元が無いので経過も固定のまま', () => {
  const view = replyView({ mark: mark({ since: 'いつか' }) });
  assert.equal(view.nodes.find((n) => n.id === 'review:requirements')?.waitingSec, null);
  assert.equal(replyOf(view)?.waitingSec, null);
});

test('D0079-AC-34: 印の無い記録は、確認の節に待ち時間が付かない（今までどおり。今のまま通る。守る）', () => {
  const view = replyView({ mark: null });
  assert.equal(view.nodes.find((n) => n.id === 'review:requirements')?.waitingSec, null);
  assert.equal(view.elapsed?.live, false);
});

// ---- AC-40 の元：帯の出し分けに要る値 ----

test('D0079-AC-40: view.hasDriver は driver の有無（pipe-dev・pipe-chat は真、無い・null は偽）', () => {
  assert.equal(hasDriverOf(replyView({ driver: 'pipe-dev' })), true);
  assert.equal(hasDriverOf(replyView({ driver: 'pipe-chat' })), true);
  assert.equal(hasDriverOf(replyView({ mark: null })), false);
  assert.equal(hasDriverOf(replyView({ mark: null, driver: null })), false);
});

test('D0079-AC-40: view.pausePipe は state.json の pipe がパイプ名のときだけその名前。dev・空・無い・文字でないときは null', () => {
  const pause = { mark: null, pendingReview: pending('survey', 'docs/pipeline/01_survey.md') };
  assert.equal(pausePipeOf(replyView({ ...pause, pipe: 'reply-pipe' })), 'reply-pipe');
  assert.equal(pausePipeOf(replyView({ ...pause, pipe: 'dev' })), null);
  const edited = (extra: Record<string, unknown>) => replySnapshot({ stateJson: withKeys(replyState({ ...pause, pipe: 'reply-pipe' }), extra) });
  for (const [label, extra] of [['pipe が空', { pipe: '' }], ['pipe が無い', { pipe: undefined }], ['pipe が数', { pipe: 5 }], ['pipe が null', { pipe: null }]] as const) {
    assert.equal(pausePipeOf(replyView({ stateJson: edited(extra).stateJson })), null, label);
  }
});

// ---- AC-32：印の無い記録の「次を待っている」 ----

test('D0079-AC-32: 古い本体の記録（印なし）で、確認ありの段が済んで答えが無いとき、ボタンは出ず「次を待っている（人の確認かもしれない）」が出る（今のまま通る。守る）', () => {
  const view = replyView({ mark: null });
  assert.equal(view.waiting, true);
  assert.equal(view.pendingReview, null);
  assert.equal(replyOf(view), null);
  const body = renderViewBody(view);
  assert.ok(body.includes(WAITING_MESSAGE), '「次を待っている」が出る');
  assert.doesNotMatch(body, /data-reply/);
  assert.doesNotMatch(body, />承認</);
});

test('D0079-AC-32: 同じ記録でも印が付くと、ボタンが出る側になる（対照）', () => {
  const body = renderViewBody(replyView());
  assert.match(body, /data-reply="approve"/);
  assert.ok(!body.includes(WAITING_MESSAGE), '「次を待っている」は出ない');
});

// ---- AC-33：印があっても waiting と pendingReview は変わらない ----

test('D0079-AC-33: 印があっても waiting（確認ありの段が済んで答えが無い）と pendingReview の判断は、印の無い記録と同じ結果（今のまま通る。守る）', () => {
  const cases = [{}, { pipe: 'reply-pipe' }, { pendingReview: pending() }, { driver: 'pipe-dev' }, { final: 'PASSED' }, { running: true }, { previous: true }];
  for (const options of cases) {
    const withMark = replyView(options);
    const without = replyView({ ...options, mark: null });
    assert.equal(withMark.waiting, without.waiting, `waiting ${JSON.stringify(options)}`);
    assert.deepEqual(withMark.pendingReview, without.pendingReview, `pendingReview ${JSON.stringify(options)}`);
    assert.equal(withMark.final, without.final);
    assert.equal(withMark.runningStage, without.runningStage);
  }
});

test('D0079-AC-33: 印だけで pending_review が無い記録は、pendingReview が null のまま（印を確認待ちの pending_review として表さない）（今のまま通る。守る）', () => {
  assert.equal(replyView().pendingReview, null);
});
