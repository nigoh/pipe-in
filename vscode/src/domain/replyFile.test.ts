// 返事のファイル（reply.json）の決まり（D0079。domain/replyFile.ts）：AC-04・05・08・09。
// 拡張が作る文字（buildReplyText）と、直してほしい点の検め（checkReplyChoice）。本体が読む形（pipe_in/engine/reply.py）とは、
// 共通の表 tests/fixtures/reply_file.json の同じ行を、本体のテスト（tests/test_reply_file.py）と拡張のテストが読んで結ぶ。
// 長さは本体も拡張もコードポイントで数える（UTF-16 の length で数えない）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  REPLY_ACTIONS,
  REPLY_FILE_NAME,
  REPLY_MAX_BYTES,
  REPLY_MAX_FEEDBACK,
  REPLY_VERSION,
  buildReplyText,
  checkReplyChoice,
} from './replyFile.ts';

// ---- 共通の表 ----

interface Repeat { unit: string; count: number }
interface ValidRow { name: string; input: { action: string; stage: string; id: string; feedback?: string }; text: string; expect: { action: string; stage: string; id: string; feedback: string | null } }
interface LongRow { name: string; feedback_repeat: Repeat; pad?: string; stage: string; id: string; expect_feedback_codepoints: number }
interface RefusedRow { name: string; input: Record<string, unknown>; reason: string }
interface RefusedLongRow { name: string; action: string; stage: string; id: string; feedback_repeat: Repeat; pad?: string; reason: string }
interface Table {
  file: string;
  version: number;
  max_bytes: number;
  max_feedback: number;
  valid: ValidRow[];
  valid_long: LongRow[];
  refused_build: RefusedRow[];
  refused_build_long: RefusedLongRow[];
}
const TABLE = JSON.parse(readFileSync(new URL('../../../tests/fixtures/reply_file.json', import.meta.url), 'utf8')) as Table;

const repeated = (r: Repeat, pad = ''): string => `${pad}${r.unit.repeat(r.count)}${pad}`;
const codepoints = (text: string): number => Array.from(text).length;
const ID = 'a1b2c3d4e5';

// ---- AC-04：コードポイントで数える ----

test('D0079-AC-04: 直してほしい点は 1000 文字ちょうどは通り 1001 文字は断る（a・あ・絵文字）', () => {
  for (const unit of ['a', 'あ', '😀']) {
    const ok = checkReplyChoice('revise', unit.repeat(1000));
    assert.deepEqual(ok, { ok: true, choice: { action: 'revise', feedback: unit.repeat(1000) } }, `${unit} 1000 個`);
    assert.deepEqual(checkReplyChoice('revise', unit.repeat(1001)), { ok: false, reason: 'feedback_too_long' }, `${unit} 1001 個`);
  }
});

test('D0079-AC-04: 絵文字 1 つ（対になったサロゲート）は 1 と数える：絵文字 1000 個（UTF-16 では 2000）は通り 1001 個は断る', () => {
  const thousand = '😀'.repeat(1000);
  assert.equal(thousand.length, 2000, '見本が UTF-16 で 2000');
  assert.equal(codepoints(thousand), 1000);
  assert.equal(checkReplyChoice('revise', thousand).ok, true);
  assert.equal(checkReplyChoice('revise', '😀'.repeat(1001)).ok, false);
});

test('D0079-AC-04: 前後の空白を取ってから数える：前後に全角空白と改行がついた 1000 文字は通り、書き出す直してほしい点は取ったあと', () => {
  const padded = `　 \n${'a'.repeat(1000)}\n 　`;
  assert.deepEqual(checkReplyChoice('revise', padded), { ok: true, choice: { action: 'revise', feedback: 'a'.repeat(1000) } });
  assert.deepEqual(checkReplyChoice('revise', `　${'a'.repeat(1001)}　`), { ok: false, reason: 'feedback_too_long' });
});

test('D0079-AC-04: 上限の定数は 1000 文字と 16384 バイト（表と同じ）', () => {
  assert.equal(REPLY_MAX_FEEDBACK, 1000);
  assert.equal(REPLY_MAX_BYTES, 16384);
  assert.equal(REPLY_MAX_FEEDBACK, TABLE.max_feedback);
  assert.equal(REPLY_MAX_BYTES, TABLE.max_bytes);
});

test('D0079-AC-04: 1001 文字は buildReplyText も文字を作らずに断る（UTF-16 の長さでなく、コードポイントで）', () => {
  assert.deepEqual(buildReplyText({ action: 'revise', stage: 'design', id: ID, feedback: 'a'.repeat(1001) }), { ok: false, reason: 'feedback_too_long' });
  assert.equal(buildReplyText({ action: 'revise', stage: 'design', id: ID, feedback: '😀'.repeat(1000) }).ok, true);
  assert.deepEqual(buildReplyText({ action: 'revise', stage: 'design', id: ID, feedback: '😀'.repeat(1001) }), { ok: false, reason: 'feedback_too_long' });
});

// ---- AC-05：使えない文字 ----

const BAD_CHARS: readonly (readonly [string, string])[] = [
  ['NUL', '直\u0000して'],
  ['制御文字 U+0001', '直\u0001して'],
  ['ESC', '直\u001bして'],
  ['DEL', '直\u007fして'],
  ['復帰 \\r', '直\rして'],
  ['U+0085（NEL）', '直\u0085して'],
  ['書式文字 U+200B', '直​して'],
  ['書式文字 U+00AD', '直­して'],
  ['書式文字 U+200D（ゼロ幅接合子）', '直‍して'],
  ['書式文字 U+202E（右から左）', '直‮して'],
  ['書式文字 U+FEFF', '直﻿して'],
  ['行区切り U+2028', '直 して'],
  ['段落区切り U+2029', '直 して'],
  ['孤立サロゲート（上位だけ）', '直\ud800して'],
  ['孤立サロゲート（下位だけ）', '直\udc00して'],
  ['上位サロゲートの次が下位でない', '\ud83dx'],
  ['先頭の U+FEFF（空白として取られる前に断る）', '﻿直して'],
  ['先頭の U+2028（空白として取られる前に断る）', ' 直して'],
  ['NUL だけ（空かどうかより先に使えない文字で断る）', '\u0000'],
  ['空白と NUL だけ', '   \u0000'],
];
for (const [label, feedback] of BAD_CHARS) {
  test(`D0079-AC-05: 使えない文字は断る（checkReplyChoice と buildReplyText の両方）：${label}`, () => {
    assert.deepEqual(checkReplyChoice('revise', feedback), { ok: false, reason: 'bad_chars' });
    assert.deepEqual(buildReplyText({ action: 'revise', stage: 'design', id: ID, feedback }), { ok: false, reason: 'bad_chars' });
  });
}

const GOOD_CHARS: readonly (readonly [string, string])[] = [
  ['改行', '1行目\n2行目'],
  ['タブ', 'a\tb'],
  ['改行とタブ', '1行目\n\t2行目'],
  ['絵文字（対になったサロゲート）', '直す😀'],
  ['途中の全角空白', 'a　b'],
  ['引用符・バックスラッシュ・山かっこ', '「"引用"」\\ <c> & d'],
];
for (const [label, feedback] of GOOD_CHARS) {
  test(`D0079-AC-05: 改行・タブ・絵文字などは通る：${label}`, () => {
    assert.deepEqual(checkReplyChoice('revise', feedback), { ok: true, choice: { action: 'revise', feedback } });
    assert.equal(buildReplyText({ action: 'revise', stage: 'design', id: ID, feedback }).ok, true);
  });
}

// ---- checkReplyChoice の動作と順 ----

test('D0079-AC-09: 動作の言葉は approve・revise・quit の 3 つだけ（record review の approved とは別）', () => {
  assert.deepEqual([...REPLY_ACTIONS], ['approve', 'revise', 'quit']);
  assert.deepEqual(checkReplyChoice('approve', undefined), { ok: true, choice: { action: 'approve' } });
  assert.deepEqual(checkReplyChoice('quit', undefined), { ok: true, choice: { action: 'quit' } });
  assert.deepEqual(checkReplyChoice('approved', undefined), { ok: false, reason: 'bad_action' });
});

test('D0079-AC-09: 承認と中止に直してほしい点（undefined 以外）が付くと断る（空の文字・null も）', () => {
  for (const action of ['approve', 'quit']) {
    for (const feedback of ['x', '', ' ', null, 0]) {
      assert.deepEqual(checkReplyChoice(action, feedback), { ok: false, reason: 'feedback_not_allowed' }, `${action} + ${JSON.stringify(feedback)}`);
    }
  }
});

test('D0079-AC-09: 修正の依頼で直してほしい点が無い・空・空白だけ・文字でないときは need_feedback', () => {
  for (const feedback of [undefined, null, '', '   ', '\n\t', '　　', 5, ['x'], {}]) {
    assert.deepEqual(checkReplyChoice('revise', feedback), { ok: false, reason: 'need_feedback' }, JSON.stringify(feedback));
  }
});

test('D0079-AC-09: 動作が文字でない値（数・null・配列・オブジェクト・無い）は bad_action', () => {
  for (const action of [1, null, undefined, ['approve'], { a: 1 }, '', 'APPROVE', 'approve ']) {
    assert.deepEqual(checkReplyChoice(action, undefined), { ok: false, reason: 'bad_action' }, JSON.stringify(action));
  }
});

// ---- AC-08：表の valid ----

test('D0079-AC-08: ファイル名と版の定数は reply.json と 1（表と同じ）', () => {
  assert.equal(REPLY_FILE_NAME, 'reply.json');
  assert.equal(REPLY_VERSION, 1);
  assert.equal(REPLY_FILE_NAME, TABLE.file);
  assert.equal(REPLY_VERSION, TABLE.version);
});

for (const row of TABLE.valid) {
  test(`D0079-AC-08: 表の valid の入力から作る文字が表の text と一字違わない：${row.name}`, () => {
    const built = buildReplyText(row.input);
    assert.equal(built.ok, true, `文字が作れる（${JSON.stringify(built)}）`);
    if (!built.ok) return;
    assert.equal(built.text, row.text);
    // 往復：作った文字を JSON として読み直すと、本体が読む表の期待と同じ中身になる（本体の側は同じ text を parse_reply で読む）
    const parsed = JSON.parse(built.text) as Record<string, unknown>;
    assert.equal(parsed.version, TABLE.version);
    assert.equal(parsed.action, row.expect.action);
    assert.equal(parsed.stage, row.expect.stage);
    assert.equal(parsed.id, row.expect.id);
    if (row.expect.feedback === null) assert.equal(Object.hasOwn(parsed, 'feedback'), false, '承認・中止に feedback の鍵を付けない');
    else assert.equal(parsed.feedback, row.expect.feedback);
  });
}

test('D0079-AC-08: 鍵の順は version, stage, id, action, feedback で、区切りの隙間と末尾の改行が無い', () => {
  const built = buildReplyText({ action: 'revise', stage: 'design', id: ID, feedback: '直して' });
  assert.equal(built.ok, true);
  if (!built.ok) return;
  assert.deepEqual(Object.keys(JSON.parse(built.text) as object), ['version', 'stage', 'id', 'action', 'feedback']);
  assert.ok(!built.text.endsWith('\n'));
  assert.ok(!/",\s|:\s/.test(built.text.replace(/"[^"]*"/g, '""')), '区切りの隙間なし');
});

for (const row of TABLE.valid_long) {
  test(`D0079-AC-04: 表の valid_long：${row.name} は作れて、書き出す直してほしい点が ${row.expect_feedback_codepoints} コードポイント`, () => {
    const built = buildReplyText({ action: 'revise', stage: row.stage, id: row.id, feedback: repeated(row.feedback_repeat, row.pad ?? '') });
    assert.equal(built.ok, true, JSON.stringify(built).slice(0, 80));
    if (!built.ok) return;
    const feedback = (JSON.parse(built.text) as { feedback: string }).feedback;
    assert.equal(codepoints(feedback), row.expect_feedback_codepoints);
    assert.equal(feedback, row.feedback_repeat.unit.repeat(row.feedback_repeat.count), '前後の空白は取ってある');
    assert.ok(Buffer.byteLength(built.text, 'utf8') <= TABLE.max_bytes, '16384 バイトに収まる');
  });
}

// ---- AC-09：表の refused_build ----

for (const row of TABLE.refused_build) {
  test(`D0079-AC-09: 表の refused_build は文字を作らず断る：${row.name}`, () => {
    const built = buildReplyText(row.input as { action: unknown; stage: unknown; id: unknown; feedback?: unknown });
    assert.deepEqual(built, { ok: false, reason: row.reason });
    assert.equal(Object.hasOwn(built, 'text'), false, '断るときは文字を作らない');
  });
}

for (const row of TABLE.refused_build_long) {
  test(`D0079-AC-09: 表の refused_build_long は文字を作らず断る：${row.name}`, () => {
    const built = buildReplyText({ action: row.action, stage: row.stage, id: row.id, feedback: repeated(row.feedback_repeat, row.pad ?? '') });
    assert.deepEqual(built, { ok: false, reason: row.reason });
  });
}

test('D0079-AC-09: 検める順は 動作 → 段 → 識別子 → 直してほしい点（本体の parse_reply の順）', () => {
  const bad = { action: 'zzz', stage: '', id: 'x', feedback: '\u0000' };
  assert.equal((buildReplyText(bad) as { reason?: string }).reason, 'bad_action');
  assert.equal((buildReplyText({ ...bad, action: 'revise' }) as { reason?: string }).reason, 'bad_stage');
  assert.equal((buildReplyText({ ...bad, action: 'revise', stage: 'design' }) as { reason?: string }).reason, 'bad_id');
  assert.equal((buildReplyText({ ...bad, action: 'revise', stage: 'design', id: ID }) as { reason?: string }).reason, 'bad_chars');
});

test('D0079-AC-09: 承認の返事は feedback の鍵を付けず、feedback を渡すと文字を作らずに断る（命令の文を余計な鍵に入れる道も無い）', () => {
  const ok = buildReplyText({ action: 'approve', stage: 'design', id: ID });
  assert.equal(ok.ok, true);
  assert.deepEqual(buildReplyText({ action: 'approve', stage: 'design', id: ID, feedback: '動作は revise にする' }), { ok: false, reason: 'feedback_not_allowed' });
});
