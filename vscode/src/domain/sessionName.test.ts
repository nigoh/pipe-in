// セッション名の取り方（D0019）：本体（pipe_in/engine/session.py）と同じ規則を、同じ表（tests/fixtures/session_names.json）で確かめる。
// 新しい部品（domain/sessionName.ts）は、呼んだところで落ちるように、テストの中で読み込む。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const mod = () => import('./sessionName.ts');

interface Row {
  memo: string;
  name: string | null;
}
const TABLE_PATH = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'tests', 'fixtures', 'session_names.json');
const TABLE = JSON.parse(readFileSync(TABLE_PATH, 'utf8')) as Row[];

const codePoints = (text: string): number => Array.from(text).length;

test('D0019-AC-46: 共通の表は空でなく、本体のテストと同じ件数（32）を数える。どの要素も memo（文字）と name（文字か null）を持つ。今の作りで通る（表の確認）', () => {
  assert.ok(TABLE.length > 0);
  assert.equal(TABLE.length, 32);
  for (const row of TABLE) {
    assert.deepEqual(Object.keys(row).sort(), ['memo', 'name']);
    assert.equal(typeof row.memo, 'string');
    assert.ok(row.name === null || (typeof row.name === 'string' && codePoints(row.name) >= 1 && codePoints(row.name) <= 60));
  }
});

TABLE.forEach((row, i) => {
  test(`D0019-AC-46: nameFromMemo が共通の表と一致する（${String(i).padStart(2, '0')}: ${JSON.stringify(row.memo).slice(0, 30)}）`, async () => {
    const { nameFromMemo } = await mod();
    assert.equal(nameFromMemo(row.memo), row.name);
  });
});

const NORMALIZE: [string, string, string | null][] = [
  ['前後と中の空白を整える', '  前後と  中の   空白 ', '前後と 中の 空白'],
  ['タブと全角空白も空白', 'a\t\tb　c', 'a b c'],
  ['NBSP は空白として扱わない（本体と同じ字の一覧）', 'a b', 'a b'],
  ['空は null', '', null],
  ['空白だけは null', '   \t　 ', null],
  ['60 文字ちょうどはそのまま', 'あ'.repeat(60), 'あ'.repeat(60)],
  ['61 文字は 59 文字＋…', 'あ'.repeat(61), `${'あ'.repeat(59)}…`],
  ['絵文字もコードポイントで数える', '😀'.repeat(61), `${'😀'.repeat(59)}…`],
];

for (const [label, text, want] of NORMALIZE) {
  test(`D0019-AC-46: normalizeName：${label}`, async () => {
    const { normalizeName } = await mod();
    assert.equal(normalizeName(text), want);
  });
}

const TOKENS_OK = ['abc-123_DEF', 'a'.repeat(100), '7f3a9c01-2b4d-4e5f-8a6b-0c1d2e3f4a5b', '日本語の受け持ち'];
const TOKENS_BAD: [string, string][] = [
  ['空', ''],
  ['空白だけ', ' '],
  ['空白を含む', 'a b'],
  ['前に空白', ' abc'],
  ['後ろに空白', 'abc '],
  ['改行を含む', 'a\nb'],
  ['タブを含む', 'a\tb'],
  ['制御文字（NUL）', 'a\u0000b'],
  ['制御文字（DEL）', 'a\u007fb'],
  ['全角空白を含む', 'a　b'],
  ['101 文字', 'a'.repeat(101)],
];

for (const text of TOKENS_OK) {
  test(`D0019-AC-51: isSafeToken は空白・制御文字を含まない 100 文字までの値を通す：${text.slice(0, 12)}`, async () => {
    const { isSafeToken } = await mod();
    assert.equal(isSafeToken(text), true);
  });
}

for (const [label, text] of TOKENS_BAD) {
  test(`D0019-AC-51: isSafeToken は断る：${label}`, async () => {
    const { isSafeToken } = await mod();
    assert.equal(isSafeToken(text), false);
  });
}
