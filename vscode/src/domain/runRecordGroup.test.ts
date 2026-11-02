// 記録の読み（D0063 の AC-03・AC-13）：stages[].group（並列の枠の名前）を StageDef.group に読む。
// 本体が書く形と拡張が読む形は、共通の表 tests/fixtures/group_record.json で結ぶ（本体のテストも同じ表を読む）。
// StageDef.group は、実装の段で型に入るまで、型に頼らず読む（test/groupFixtures.ts の stageGroupOf）。
// 赤の理由は「まだ読んでいない」：StageDef.group が undefined になる（期待は null や文字。厳密に比べる）。
// 「今のまま通る。守る」と書いたものは、今の作りで通り、実装のあとも通り続けることを見張る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseRunRecord } from './runRecord.ts';
import { stateJson } from '../test/fixtures.ts';
import { stageDef } from '../test/checkFixtures.ts';
import { gStage, groupRecord, loadGroupTable, runEntry, stageGroupOf } from '../test/groupFixtures.ts';

// ======== AC-03：stages[].group を読む ========

test('D0063-AC-03: stages[].group を StageDef.group に読む（枠の外の段は null）', () => {
  const record = groupRecord([runEntry('survey', 1)]);
  assert.equal(stageGroupOf(record, 'survey'), null, '枠の外の段');
  assert.equal(stageGroupOf(record, 'flow'), 'draw');
  assert.equal(stageGroupOf(record, 'klass'), 'draw');
  assert.equal(stageGroupOf(record, 'report'), null, '枠の外の段');
});

test('D0063-AC-03: group の項目が無い古い記録では、どの段も group は null で、例外を出さない', () => {
  const record = groupRecord([], { stages: [stageDef({ name: 'a' }), stageDef({ name: 'b', check: { on_fail: null, max_retries: 2 } })] });
  assert.equal(stageGroupOf(record, 'a'), null);
  assert.equal(stageGroupOf(record, 'b'), null);
});

const LONG_OK = 'a'.repeat(64);
const LONG_NG = 'a'.repeat(65);
const BROKEN_GROUPS: readonly (readonly [string, unknown, unknown])[] = [
  ['文字（ふつうの名前）', 'draw', 'draw'],
  ['文字（64 文字ちょうど）', LONG_OK, LONG_OK],
  ['数', 5, null],
  ['0', 0, null],
  ['真偽', true, null],
  ['null', null, null],
  ['配列', ['draw'], null],
  ['空の配列', [], null],
  ['オブジェクト', { name: 'draw' }, null],
  ['空の文字', '', null],
  ['空白だけ', '  ', null],
  ['長すぎる文字（65 文字）', LONG_NG, null],
  ['パスの区切りを含む文字（/）', 'a/b', null],
  ['パスの区切りを含む文字（\\）', 'a\\b', null],
  ['親のフォルダへ上る文字', '../x', null],
  ['HTML の記号を含む文字', '<b>x</b>', null],
];
for (const [label, value, expected] of BROKEN_GROUPS) {
  test(`D0063-AC-03: 壊れた値は null にして例外を出さない：stages[].group が ${label}`, () => {
    const record = groupRecord([], { stages: [gStage('a', value), gStage('b')] });
    assert.equal(stageGroupOf(record, 'a'), expected);
    assert.equal(stageGroupOf(record, 'b'), null, '隣の段は影響を受けない');
  });
}

test('D0063-AC-03: group を読んでも、段の名前・表示の名前・成果物・確認・判定の読みは変わらない。今のまま通る。守る', () => {
  const check = { on_fail: null, max_retries: 3 };
  const record = groupRecord([], { stages: [gStage('flow', 'draw', { review: false, check, label: 'フロー' })] });
  const def = record.stages?.[0];
  assert.equal(def?.name, 'flow');
  assert.equal(def?.label, 'フロー');
  assert.equal(def?.output, 'flow.md');
  assert.equal(def?.review, false);
  assert.deepEqual(def?.check, { onFail: null, maxRetries: 3 });
});

test('D0063-AC-03: 記録が空・壊れた JSON・形の違う JSON でも例外を出さない（stages は null か空）。今のまま通る。守る', () => {
  for (const text of [null, '{', '[]', '"x"', '{}', stateJson({})]) {
    const record = parseRunRecord(text);
    assert.ok(record.stages === null || record.stages.length === 0, String(text));
  }
});

// ======== AC-13：共通の表 ========

test('D0063-AC-13: 共通の表の keys が拡張の読む鍵と同じ（テスト補助が足す鍵と同じ）。今のまま通る。守る', () => {
  const table = loadGroupTable();
  assert.deepEqual([...table.keys].sort(), ['group']);
  const plain = Object.keys(gStage('a'));
  const grouped = Object.keys(gStage('a', 'g')).filter((k) => !plain.includes(k));
  assert.deepEqual(grouped, [...table.keys], 'gStage が足す鍵は表の keys と同じ');
  for (const c of table.cases) {
    assert.deepEqual(Object.keys(c.written), [...table.keys], c.memo);
    assert.deepEqual(Object.keys(c.read), [...table.keys], c.memo);
  }
  assert.ok(table.cases.length >= 3, 'ケースは 3 つ以上');
});

for (const c of loadGroupTable().cases) {
  test(`D0063-AC-13: 共通の表の written を読むと read になる：${c.memo}`, () => {
    // written の group が null の段は、本体が鍵を書かない（stages[] の要素に group を持たない）
    const stages = c.stages.map((s) => gStage(s.name, c.written.group[s.name] ?? undefined));
    const record = groupRecord([], { stages });
    const got = Object.fromEntries(c.stages.map((s) => [s.name, stageGroupOf(record, s.name)]));
    assert.deepEqual(got, c.read.group);
  });
}
