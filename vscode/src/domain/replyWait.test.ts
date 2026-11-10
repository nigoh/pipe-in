// 返事を受け付けている確認待ちの判断（D0079。domain/replyWait.ts）：AC-31・51。純粋な関数だけ（ファイル・時計・vscode に触れない）。
// canReply は 7 つの条件がすべて真のときだけ真。isReplyStalled は返事のファイルの更新時刻と「今」（引数）から 30 秒の案内を決める。
// isLive は、読み直しを続けるか（動いている・確認待ちの図、または印のある図）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { REPLY_STALL_MS, canReply, isLive, isReplyStalled } from './replyWait.ts';
import type { ReplyOfferInput } from './replyWait.ts';
import { finishedView, runningView, waitingView } from '../test/liveFixtures.ts';
import { MARK_AT, MARK_ID, replyView } from '../test/replyFixtures.ts';

const GOOD: ReplyOfferInput = {
  mark: { stage: 'requirements', id: MARK_ID, since: MARK_AT },
  final: null,
  hasDriver: false,
  hasPendingReview: false,
  running: false,
  previous: false,
  other: false,
};

// ---- AC-31：ボタンを出す判断 ----

test('D0079-AC-31: 印があり、終わっておらず、driver が無く、pending_review が無く、動いている段が無く、いまの work_dir の実行なら真', () => {
  assert.equal(canReply(GOOD), true);
});

test('D0079-AC-31: 時刻の読めない印（since が null）でも、ほかの条件が合えば真', () => {
  assert.equal(canReply({ ...GOOD, mark: { stage: 'requirements', id: MARK_ID, since: null } }), true);
});

const BROKEN: readonly (readonly [string, Partial<ReplyOfferInput>])[] = [
  ['印なし（古い本体の記録）', { mark: null }],
  ['終わった（PASSED）', { final: 'PASSED' }],
  ['終わった（中止 STOPPED_BY_HUMAN）', { final: 'STOPPED_BY_HUMAN' }],
  ['終わった（知らない文字）', { final: 'WHATEVER' }],
  ['driver あり（pipe-dev や pipe-chat の記録）', { hasDriver: true }],
  ['pending_review あり（--pause や /pipe-in の記録）', { hasPendingReview: true }],
  ['動いている段がある', { running: true }],
  ['archive/ の前の実行', { previous: true }],
  ['別の worktree の実行', { other: true }],
];
for (const [label, broken] of BROKEN) {
  test(`D0079-AC-31: 7 つの条件を 1 つ崩すと偽になる：${label}（今のまま通る。守る）`, () => {
    assert.equal(canReply({ ...GOOD, ...broken }), false);
  });
}

test('D0079-AC-31: 条件を全部崩しても偽（偽の側に倒れる）（今のまま通る。守る）', () => {
  const all: ReplyOfferInput = { mark: null, final: 'PASSED', hasDriver: true, hasPendingReview: true, running: true, previous: true, other: true };
  assert.equal(canReply(all), false);
});

test('D0079-AC-31: 判断は渡した入力を変えない（今のまま通る。守る）', () => {
  const input = { ...GOOD, mark: { ...GOOD.mark! } };
  const before = JSON.stringify(input);
  canReply(input);
  assert.equal(JSON.stringify(input), before);
});

// ---- AC-51：30 秒の案内 ----

test('D0079-AC-51: 30 秒の案内の長さは 30 秒', () => {
  assert.equal(REPLY_STALL_MS, 30_000);
});

const T0 = 1_760_000_000_000;

test('D0079-AC-51: 29 秒では出さず、30 秒で出し、それより後も出す', () => {
  assert.equal(isReplyStalled(T0, T0 + 29_000), false);
  assert.equal(isReplyStalled(T0, T0 + 29_999), false);
  assert.equal(isReplyStalled(T0, T0 + 30_000), true);
  assert.equal(isReplyStalled(T0, T0 + 31_000), true);
  assert.equal(isReplyStalled(T0, T0 + 3_600_000), true);
});

test('D0079-AC-51: 返事のファイルが無い（更新時刻が null）・更新時刻が「今」より先・時計が無い（undefined）・数でない値は出さない（今のまま通る。守る）', () => {
  assert.equal(isReplyStalled(null, T0 + 60_000), false);
  assert.equal(isReplyStalled(T0 + 60_000, T0), false);
  assert.equal(isReplyStalled(T0, undefined), false);
  assert.equal(isReplyStalled(T0, Number.NaN), false);
  assert.equal(isReplyStalled(Number.NaN, T0 + 60_000), false);
});

test('D0079-AC-51: 「今」と同じ時刻（0 秒）は出さない（今のまま通る。守る）', () => {
  assert.equal(isReplyStalled(T0, T0), false);
});

// ---- AC-51 の支え：読み直しを続けるか ----

test('D0079-AC-51: isLive は印のある実行の図で真（確認待ちの pending_review が無くても、約 5 秒ごとの読み直しを続ける）', () => {
  assert.equal(isLive(replyView()), true);
});

test('D0079-AC-51: isLive は動いている図・pending_review の確認待ちの図でも真、終わった図で偽', () => {
  assert.equal(isLive(runningView(83)), true);
  assert.equal(isLive(waitingView(40)), true);
  assert.equal(isLive(finishedView()), false);
});

test('D0079-AC-51: isLive は、印があっても条件を満たさない図（終わった・driver あり・印なし）では、動いていなければ偽（今のまま通る。守る）', () => {
  assert.equal(isLive(replyView({ final: 'PASSED' })), false);
  assert.equal(isLive(replyView({ mark: null })), false);
});
