// 作業台から流したパイプの実行の目印 pipeRunKey（D0078。domain/runs.ts）。AC-28。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { HERE, isRunFolderName, makeRunKey, parseRunKey, pipeRunKey } from './runs.ts';

test('D0078-AC-28: pipeRunKey は here|<パイプ名>（makeRunKey(HERE, 名前) と同じ）', () => {
  assert.equal(pipeRunKey('design-review'), 'here|design-review');
  assert.equal(pipeRunKey('design-review'), makeRunKey(HERE, 'design-review'));
  assert.equal(pipeRunKey('a'), 'here|a');
  assert.equal(pipeRunKey('p1-2'), 'here|p1-2');
});

test('D0078-AC-28: 返した目印は parseRunKey で場所 here と id に戻せる（実行の候補の目印と同じ形）', () => {
  const key = pipeRunKey('design-review');
  assert.notEqual(key, null);
  assert.deepEqual(parseRunKey(key), { place: 'here', id: 'design-review' });
});

const NOT_FOLDER_NAMES: readonly (readonly [string, string])[] = [
  ['logs（予約）', 'logs'],
  ['archive（予約）', 'archive'],
  ['空', ''],
  ['スラッシュを含む', 'a/b'],
  ['archive の id の形', 'archive/20261017-100000'],
  ['.. で始まる', '../x'],
  ['大文字を含む', 'Design'],
  ['空白を含む', 'a b'],
  ['_ で始まる', '_x'],
  ['- で始まる', '-x'],
  ['| を含む（目印の区切り）', 'a|b'],
  ['101 文字（長すぎる）', 'a'.repeat(101)],
  ['改行を含む', 'a\nb'],
];

for (const [label, name] of NOT_FOLDER_NAMES) {
  test(`D0078-AC-28: isRunFolderName が偽の名前（${label}）は null`, () => {
    assert.equal(isRunFolderName(name), false, '前提：フォルダ名にならない');
    assert.equal(pipeRunKey(name), null);
  });
}

test('D0078-AC-28: 100 文字ちょうどの名前は目印にできる', () => {
  assert.equal(pipeRunKey('a'.repeat(100)), `here|${'a'.repeat(100)}`);
});
