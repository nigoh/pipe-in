// 補助 test/externalFixtures.ts の確かめ（D0065 のテストの前提）。今の作りのままで通る（守る）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pipeFiles, targetName } from '../domain/pipeModel.ts';
import { baseModel, reread, renameIds } from './externalFixtures.ts';

test('D0065-AC-02: （前提）書き出して読み直した形は、同じファイルの組を書き出す。見本は 2 段で survey → write → 終わりとつながる（今のまま通る。守る）', () => {
  const m = baseModel();
  assert.deepEqual(m.stages.map((s) => s.name), ['survey', 'write']);
  assert.deepEqual(pipeFiles(reread(m)), pipeFiles(m));
  assert.equal(targetName(m, m.stages[0]!.next), 'write');
  assert.equal(targetName(m, m.stages[1]!.next), 'end');
});

test('D0065-AC-05: （前提）renameIds は id だけを付け替え、つなぎの行き先（段の name）は変えない。元は変えない（今のまま通る。守る）', () => {
  const m = baseModel();
  const r = renameIds(m, 'x');
  assert.notEqual(r.stages[0]!.id, m.stages[0]!.id);
  assert.equal(targetName(r, r.stages[0]!.next), 'write');
  assert.equal(m.stages[0]!.id, 's1');
  assert.deepEqual(pipeFiles(r), pipeFiles(m));
});
