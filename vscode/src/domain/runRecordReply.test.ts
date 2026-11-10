// 実行の記録の写し RunRecord の replyWait（D0079・AC-30・33）：state.json の reply_wait（端末の pipe-in が確認の段で人の入力を待っている間だけ書く印）。
// 印は { stage, id, since }。段は本体の STAGE_RE と同じ形（英数字で始まり、英数字・_・- の 40 文字まで）、識別子は 10 文字の小文字の 16 進。
// since は読める時刻だけ文字、そうでなければ null（印は有効のまま）。形が合わない・無い記録は null（印なし）。
// 項目 replyWait は実装の段で足される。いまは undefined が返るので、値があるかを先に確かめて落とす。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EMPTY_RUN_RECORD, parseRunRecord } from './runRecord.ts';
import { MARK_AT, MARK_ID, mark, pending, replyState, withKeys } from '../test/replyFixtures.ts';
import { stateJson } from '../test/fixtures.ts';

/** 写しの replyWait。項目が無ければ落とす（まだ作っていない）。印なしは null */
function replyWaitOf(text: string | null): unknown {
  const record = parseRunRecord(text) as unknown as { replyWait?: unknown };
  assert.notEqual(record.replyWait, undefined, 'RunRecord に replyWait がある（まだ作っていない）');
  return record.replyWait;
}

test('D0079-AC-30: 印のある state.json を読むと、段・識別子・時刻が取れる', () => {
  assert.deepEqual(replyWaitOf(replyState()), { stage: 'requirements', id: MARK_ID, since: MARK_AT });
  assert.deepEqual(replyWaitOf(replyState({ pipe: 'reply-pipe' })), { stage: 'survey', id: MARK_ID, since: MARK_AT });
});

test('D0079-AC-30: 段の名前は英数字で始まり英数字・_・- の 40 文字までを通す（大文字・_・- も）', () => {
  for (const stage of ['requirements', 'Stage_A-1', 'a', '0', `A${'b'.repeat(39)}`]) {
    assert.deepEqual(replyWaitOf(replyState({ mark: mark({ stage }) })), { stage, id: MARK_ID, since: MARK_AT }, stage);
  }
});

test('D0079-AC-30: 時刻が無い・読めない印は有効のまま since が null になる', () => {
  for (const since of [undefined, null, 'いつか', 5, {}, '2026-02-30T10:00:00+00:00']) {
    const value = mark();
    if (since === undefined) delete value.since;
    else value.since = since;
    assert.deepEqual(replyWaitOf(replyState({ mark: value })), { stage: 'requirements', id: MARK_ID, since: null }, JSON.stringify(since));
  }
});

test('D0079-AC-30: 印が無い古い記録（reply_wait の鍵が無い・null）は印なし（null）', () => {
  assert.equal(replyWaitOf(replyState({ mark: null })), null);
  assert.equal(replyWaitOf(withKeys(replyState({ mark: null }), { reply_wait: null })), null);
  assert.equal(replyWaitOf(stateJson({ runs: [] })), null);
});

const BAD_MARKS: readonly (readonly [string, unknown])[] = [
  ['段が空', mark({ stage: '' })],
  ['段が - で始まる', mark({ stage: '-a' })],
  ['段に空白', mark({ stage: 'a b' })],
  ['段が日本語', mark({ stage: '要件定義' })],
  ['段に区切り', mark({ stage: 'a/b' })],
  ['段の末尾に改行', mark({ stage: 'a\n' })],
  ['段が 41 文字', mark({ stage: `A${'b'.repeat(40)}` })],
  ['段が数', mark({ stage: 1 })],
  ['段が無い', { id: MARK_ID, since: MARK_AT }],
  ['識別子が 9 文字', mark({ id: 'a1b2c3d4e' })],
  ['識別子が 11 文字', mark({ id: 'a1b2c3d4e5f' })],
  ['識別子が大文字', mark({ id: 'A1B2C3D4E5' })],
  ['識別子が 16 進でない', mark({ id: 'g1b2c3d4e5' })],
  ['識別子の末尾に改行', mark({ id: 'a1b2c3d4e5\n' })],
  ['識別子が数', mark({ id: 1234567890 })],
  ['識別子が無い', { stage: 'requirements', since: MARK_AT }],
  ['文字', 'a1b2c3d4e5'],
  ['数', 5],
  ['true', true],
  ['配列', ['requirements', MARK_ID]],
  ['空のオブジェクト', {}],
];
for (const [label, value] of BAD_MARKS) {
  test(`D0079-AC-30: 形の違う印は印なし（null）になる：${label}`, () => {
    assert.equal(replyWaitOf(replyState({ mark: value })), null);
  });
}

test('D0079-AC-30: 読めない state.json（無い・壊れた JSON・配列・数）の写しは印なし', () => {
  for (const text of [null, '{"reply_wait": {"stage": "requirements", ', '[1]', '42', '""', 'null', '']) {
    assert.equal(replyWaitOf(text), null, String(text));
  }
});

test('D0079-AC-30: EMPTY_RUN_RECORD の replyWait は null で、何度読んでも書き換わらない', () => {
  assert.equal((EMPTY_RUN_RECORD as unknown as { replyWait?: unknown }).replyWait, null, 'EMPTY_RUN_RECORD.replyWait は null（まだ作っていない）');
  const before = JSON.stringify(EMPTY_RUN_RECORD);
  parseRunRecord(null);
  parseRunRecord(replyState());
  assert.equal(JSON.stringify(EMPTY_RUN_RECORD), before);
});

test('D0079-AC-30: runs が配列でない state.json でも、印は読める（runs を読む前に代入する）', () => {
  assert.deepEqual(replyWaitOf(JSON.stringify({ reply_wait: mark(), runs: 'oops' })), { stage: 'requirements', id: MARK_ID, since: MARK_AT });
});

// ---- AC-33：印があっても、pending_review の読みは変わらない ----

/** replyWait 以外の写し */
function withoutMark(text: string): Record<string, unknown> {
  const { replyWait: _ignored, ...rest } = parseRunRecord(text) as unknown as Record<string, unknown>;
  return rest;
}

test('D0079-AC-33: 印があっても、印を除いた写しは印の無い記録と同じ（pending_review・final・hasDriver・段の並び・実行の読み。今のまま通る。守る）', () => {
  for (const options of [{}, { pipe: 'reply-pipe' }, { driver: 'pipe-dev' }, { pendingReview: pending() }, { final: 'PASSED' }]) {
    assert.deepEqual(withoutMark(replyState(options)), withoutMark(replyState({ ...options, mark: null })), JSON.stringify(options));
  }
});

test('D0079-AC-33: 印と pending_review が両方ある記録でも、pending_review は今までどおり読め、印も読める', () => {
  const text = replyState({ pendingReview: pending() });
  const record = parseRunRecord(text);
  assert.deepEqual(record.pendingReview, { stage: 'requirements', doc: 'docs/pipeline/01_requirements.md', since: MARK_AT });
  assert.deepEqual(replyWaitOf(text), { stage: 'requirements', id: MARK_ID, since: MARK_AT });
});

test('D0079-AC-33: 印だけで pending_review が無い記録は、pending_review が null のまま（印を pending_review として読まない）', () => {
  const text = replyState();
  assert.equal(parseRunRecord(text).pendingReview, null);
  assert.deepEqual(replyWaitOf(text), { stage: 'requirements', id: MARK_ID, since: MARK_AT });
});

test('D0079-AC-33: driver の読みも印に左右されない：印があって driver が pipe-dev の記録は hasDriver が真、pipe-chat の記録は isChat が真', () => {
  assert.equal(parseRunRecord(replyState({ driver: 'pipe-dev' })).hasDriver, true);
  assert.equal(parseRunRecord(replyState()).hasDriver, false);
  const chat = parseRunRecord(replyState({ driver: 'pipe-chat' }));
  assert.equal(chat.isChat, true);
  assert.equal(chat.hasDriver, true);
  assert.deepEqual(replyWaitOf(replyState({ driver: 'pipe-dev' })), { stage: 'requirements', id: MARK_ID, since: MARK_AT });
});
