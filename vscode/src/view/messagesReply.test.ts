// パネルから来る知らせ { type: 'reply', action, feedback? } の検め（D0079・AC-45・46。view/messages.ts の parseWebviewMessage）。
// 読む値は動作（approve・revise・quit）と、修正の依頼のときだけ直してほしい点の文字。場所・段・識別子はパネルから受け取らない。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseWebviewMessage } from './messages.ts';

const parse = (value: unknown): unknown => parseWebviewMessage(value);

// ---- AC-45：読む形 ----

test('D0079-AC-45: 動作が approve・quit で直してほしい点が無い知らせは読める（type と action だけ）', () => {
  assert.deepEqual(parse({ type: 'reply', action: 'approve' }), { type: 'reply', action: 'approve' });
  assert.deepEqual(parse({ type: 'reply', action: 'quit' }), { type: 'reply', action: 'quit' });
});

test('D0079-AC-45: 修正の依頼は直してほしい点の文字つきで読める（改行・タブ・絵文字も）', () => {
  for (const feedback of ['ここを直して', '1行目\n\t2行目', '直す😀', 'a'.repeat(1000)]) {
    assert.deepEqual(parse({ type: 'reply', action: 'revise', feedback }), { type: 'reply', action: 'revise', feedback }, feedback.slice(0, 10));
  }
});

test('D0079-AC-45: 絵文字 1000 個（UTF-16 では 2000）の直してほしい点は読める。1001 個・a の 1001 個は null', () => {
  const thousand = '😀'.repeat(1000);
  assert.deepEqual(parse({ type: 'reply', action: 'revise', feedback: thousand }), { type: 'reply', action: 'revise', feedback: thousand });
  assert.equal(parse({ type: 'reply', action: 'revise', feedback: '😀'.repeat(1001) }), null);
  assert.equal(parse({ type: 'reply', action: 'revise', feedback: 'a'.repeat(1001) }), null);
});

test('D0079-AC-45: 前後に空白のある直してほしい点は読める（取ったあとの長さで数える）', () => {
  const parsed = parse({ type: 'reply', action: 'revise', feedback: `  ${'a'.repeat(1000)}\n` }) as { feedback?: string } | null;
  assert.notEqual(parsed, null);
  assert.equal(parsed?.feedback?.trim(), 'a'.repeat(1000));
});

const BAD: readonly (readonly [string, unknown])[] = [
  ['動作が approved（record review の言葉）', { type: 'reply', action: 'approved' }],
  ['動作が大文字', { type: 'reply', action: 'APPROVE' }],
  ['動作の後ろに空白', { type: 'reply', action: 'quit ' }],
  ['動作が無い', { type: 'reply' }],
  ['動作が数', { type: 'reply', action: 1 }],
  ['動作が null', { type: 'reply', action: null }],
  ['動作が配列', { type: 'reply', action: ['approve'] }],
  ['動作が知らない言葉', { type: 'reply', action: 'delete' }],
  ['承認に直してほしい点', { type: 'reply', action: 'approve', feedback: '直して' }],
  ['承認に空の直してほしい点', { type: 'reply', action: 'approve', feedback: '' }],
  ['承認に null の直してほしい点', { type: 'reply', action: 'approve', feedback: null }],
  ['中止に直してほしい点', { type: 'reply', action: 'quit', feedback: '直して' }],
  ['修正の依頼で直してほしい点が無い', { type: 'reply', action: 'revise' }],
  ['修正の依頼で直してほしい点が空', { type: 'reply', action: 'revise', feedback: '' }],
  ['修正の依頼で直してほしい点が空白だけ', { type: 'reply', action: 'revise', feedback: '  \n\t ' }],
  ['修正の依頼で直してほしい点が全角空白だけ', { type: 'reply', action: 'revise', feedback: '　　' }],
  ['修正の依頼で直してほしい点が数', { type: 'reply', action: 'revise', feedback: 5 }],
  ['修正の依頼で直してほしい点が null', { type: 'reply', action: 'revise', feedback: null }],
  ['修正の依頼で直してほしい点が配列', { type: 'reply', action: 'revise', feedback: ['x'] }],
  ['修正の依頼で直してほしい点が 1001 文字', { type: 'reply', action: 'revise', feedback: 'a'.repeat(1001) }],
  ['使えない文字 NUL', { type: 'reply', action: 'revise', feedback: '直\u0000して' }],
  ['使えない文字 制御文字', { type: 'reply', action: 'revise', feedback: '直\u0001して' }],
  ['使えない文字 復帰', { type: 'reply', action: 'revise', feedback: '直\rして' }],
  ['使えない文字 書式文字 U+200B', { type: 'reply', action: 'revise', feedback: '直​して' }],
  ['使えない文字 U+FEFF', { type: 'reply', action: 'revise', feedback: '﻿直して' }],
  ['使えない文字 行区切り U+2028', { type: 'reply', action: 'revise', feedback: '直 して' }],
  ['使えない文字 孤立サロゲート', { type: 'reply', action: 'revise', feedback: '直\ud800して' }],
];
for (const [label, value] of BAD) {
  test(`D0079-AC-45: 形の違う reply の知らせは捨てる（null）：${label}（今のまま通る。守る）`, () => {
    assert.equal(parse(value), null);
  });
}

test('D0079-AC-45: reply に似た type（reply2・Reply・replyRefused）は捨てる。ほかの type は今までどおり（今のまま通る。守る）', () => {
  for (const type of ['reply2', 'Reply', 'replyRefused', 'replies']) assert.equal(parse({ type, action: 'approve' }), null, type);
  assert.deepEqual(parse({ type: 'ready' }), { type: 'ready' });
  assert.deepEqual(parse({ type: 'selectRun', id: 'here|' }), { type: 'selectRun', id: 'here|' });
  for (const value of [null, undefined, 3, 'reply', [], ['reply']] as unknown[]) assert.equal(parse(value), null);
});

// ---- AC-46：ほかの鍵は使わない ----

const EXTRA = { stage: 'design', id: 'f0e1d2c3b4', path: '/etc/passwd', dir: '../x', pipe: 'evil', name: 'x', version: 2, key: 'here|', runId: 'x', file: 'reply.json' };

test('D0079-AC-46: 承認・中止にほかの鍵（stage・id・path・dir・pipe・name・version）が付いても、読んだ結果の鍵は type と action だけ', () => {
  for (const action of ['approve', 'quit']) {
    const parsed = parse({ type: 'reply', action, ...EXTRA }) as Record<string, unknown> | null;
    assert.notEqual(parsed, null, action);
    assert.deepEqual(Object.keys(parsed!).sort(), ['action', 'type'], action);
    assert.deepEqual(parsed, { type: 'reply', action });
  }
});

test('D0079-AC-46: 修正の依頼にほかの鍵が付いても、読んだ結果の鍵は type・action・feedback だけで、付いた値は使われない', () => {
  const parsed = parse({ type: 'reply', action: 'revise', feedback: '直して', ...EXTRA }) as Record<string, unknown> | null;
  assert.notEqual(parsed, null);
  assert.deepEqual(Object.keys(parsed!).sort(), ['action', 'feedback', 'type']);
  assert.deepEqual(parsed, { type: 'reply', action: 'revise', feedback: '直して' });
  assert.ok(!JSON.stringify(parsed).includes('/etc/passwd') && !JSON.stringify(parsed).includes('evil') && !JSON.stringify(parsed).includes('f0e1d2c3b4'));
});

test('D0079-AC-46: 読んだ結果は新しいオブジェクトで、渡した値と同じ参照ではない（付いた鍵を持ち越さない）', () => {
  const input = { type: 'reply', action: 'approve', stage: 'design', id: 'f0e1d2c3b4' };
  const parsed = parse(input);
  assert.notEqual(parsed, null, '読める知らせ');
  assert.notEqual(parsed, input);
  assert.deepEqual(input, { type: 'reply', action: 'approve', stage: 'design', id: 'f0e1d2c3b4' }, '渡した値を変えない');
});
