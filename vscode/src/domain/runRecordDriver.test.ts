// 実行の記録の写し RunRecord の hasDriver（D0050）：state.json の driver が、項目として有り、null でないこと。
// 値は見ない（本体 pipeline.py の `data.get("driver") is not None` と同じ。空の文字・0・false・{} でも「あり」）。
// 無い・読めない写し（state.json が無い・壊れている・オブジェクトでない）は「なし」。
// 項目 hasDriver は実装の段で足される。いまは undefined が返るので、真偽値かどうかを先に確かめて落とす（undefined どうしが等しくなって赤にならないのを避ける）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EMPTY_RUN_RECORD, parseRunRecord } from './runRecord.ts';
import { stateJson } from '../test/fixtures.ts';

/** 写しの hasDriver。真偽値でなければ落とす（項目がまだ無い） */
function hasDriver(text: string | null): boolean {
  const value = (parseRunRecord(text) as unknown as { hasDriver?: unknown }).hasDriver;
  assert.equal(typeof value, 'boolean', 'RunRecord に hasDriver（真偽値）がある（まだ作っていない）');
  return value as boolean;
}

const PRESENT: [string, unknown][] = [
  ['pipe-dev（今の形）', 'pipe-dev'],
  ['pipe-in（前の版の形）', 'pipe-in'],
  ['空の文字', ''],
  ['数 0', 0],
  ['数 1', 1],
  ['false', false],
  ['true', true],
  ['空のオブジェクト', {}],
  ['空の配列', []],
  ['知らない文字', 'ほかの外の会話'],
];
for (const [label, driver] of PRESENT) {
  test(`D0050-AC-20: driver が ${label} のとき、hasDriver は真（値は見ない。null でなければ「あり」）`, () => {
    assert.equal(hasDriver(stateJson({ driver })), true);
  });
}

test('D0050-AC-20: driver が null のとき、hasDriver は偽', () => {
  assert.equal(hasDriver(stateJson({ driver: null })), false);
});

test('D0050-AC-20: driver の項目が無いとき、hasDriver は偽（前の版の記録・SDK の実行）', () => {
  assert.equal(hasDriver(stateJson({})), false);
});

const UNREADABLE: [string, string | null][] = [
  ['state.json が無い（null）', null],
  ['壊れた JSON', '{"driver": "pipe-dev", '],
  ['配列の JSON', '["pipe-dev"]'],
  ['数の JSON', '42'],
  ['文字の JSON', '"pipe-dev"'],
  ['null の JSON', 'null'],
  ['空のファイル', ''],
];
for (const [label, text] of UNREADABLE) {
  test(`D0050-AC-20: ${label}の写しは hasDriver が偽（driver が分からない）`, () => {
    assert.equal(hasDriver(text), false);
  });
}

test('D0050-AC-20: runs が配列でない state.json でも、driver は読める（runs を読む前に代入する）', () => {
  assert.equal(hasDriver(JSON.stringify({ driver: 'pipe-dev', runs: 'oops' })), true);
  assert.equal(hasDriver(JSON.stringify({ driver: '', runs: null })), true);
  assert.equal(hasDriver(JSON.stringify({ driver: null, runs: 'oops' })), false);
  assert.equal(hasDriver(JSON.stringify({ runs: {} })), false);
});

test('D0050-AC-20: driver 以外の項目の読みは変わらない（final・runs・stages は今までどおり）', () => {
  const text = stateJson({ driver: 'pipe-dev', final: 'PASSED', pipe: 'dev' });
  const record = parseRunRecord(text);
  assert.equal(record.final, 'PASSED');
  assert.equal(record.pipe, 'dev');
  assert.deepEqual(record.stageRuns, []);
  assert.equal(hasDriver(text), true);
});

test('D0050-AC-20: EMPTY_RUN_RECORD の hasDriver は偽', () => {
  const value = (EMPTY_RUN_RECORD as unknown as { hasDriver?: unknown }).hasDriver;
  assert.equal(value, false, 'EMPTY_RUN_RECORD.hasDriver は false（まだ作っていない）');
});

test('D0050-AC-20: 読めない写しを何度読んでも、EMPTY_RUN_RECORD は書き換わらない（今のまま通る。守る）', () => {
  const before = JSON.stringify(EMPTY_RUN_RECORD);
  parseRunRecord(null);
  parseRunRecord(stateJson({ driver: 'pipe-dev' }));
  assert.equal(JSON.stringify(EMPTY_RUN_RECORD), before);
});
