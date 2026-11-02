// 外で書き換わったパイプの判断（D0065）：見るべきファイルか・同じ形か・何もしない／読み直す／選ばせる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isWatchedRel, judgeExternal, sameFiles } from './pipeExternal.ts';
import { pipeFiles, pipeFromFiles } from './pipeModel.ts';
import { BASE_PROMPTS, BASE_TOML, baseModel, reread } from '../test/externalFixtures.ts';

const WATCHED = ['pipe.toml', 'layout.json', 'prompts/01_a.md', 'prompts/x.md', 'prompts\\02_b.md'];
const NOT_WATCHED = ['README.md', 'prompts/sub/x.md', 'prompts/x.txt', 'other.md', '../pipe.toml', 'prompts', 'prompts/', 'pipe.toml.bak', 'sub/pipe.toml', 'prompts/.md.txt', ''];

for (const rel of WATCHED) {
  test(`D0065-AC-01: ${JSON.stringify(rel)} は見るべきファイル（pipe.toml・layout.json・prompts/ 直下の .md。\\ は / に直して比べる）`, () => {
    assert.equal(isWatchedRel(rel), true);
  });
}
for (const rel of NOT_WATCHED) {
  test(`D0065-AC-01: ${JSON.stringify(rel)} は見るべきファイルではない`, () => {
    assert.equal(isWatchedRel(rel), false);
  });
}

test('D0065-AC-02: sameFiles は、キーと中身が同じファイルの組だけを同じとする（順番は問わない）', () => {
  assert.equal(sameFiles({ a: '1', b: '2' }, { b: '2', a: '1' }), true);
  assert.equal(sameFiles({ a: '1' }, { a: '2' }), false);
  assert.equal(sameFiles({ a: '1' }, { a: '1', b: '' }), false);
  assert.equal(sameFiles({ a: '1', b: '' }, { a: '1' }), false);
  assert.equal(sameFiles({}, {}), true);
});

for (const dirty of [false, true]) {
  test(`D0065-AC-02: 同じ形（保存の直後・書き出して読み直した形）は、保存していない変更が${dirty ? 'あっ' : 'なく'}ても 'none'`, () => {
    const saved = baseModel();
    assert.equal(judgeExternal(saved, reread(saved), dirty), 'none');
    assert.equal(judgeExternal(saved, baseModel(), dirty), 'none');
  });

  test(`D0065-AC-02: 作業台が書き出さない項目（max_agent_calls など）だけを外で書き換えても 'none'（保存で落ちる今の決まりと同じ。dirty=${dirty}）`, () => {
    const saved = baseModel();
    const disk = pipeFromFiles('one', BASE_TOML.replace('access = "read"', 'access = "read"\nmax_agent_calls = 7'), BASE_PROMPTS, null);
    assert.deepEqual(pipeFiles(disk), pipeFiles(saved), '前提：書き出すファイルの組は同じ');
    assert.equal(judgeExternal(saved, disk, dirty), 'none');
  });
}

test("D0065-AC-03: 違う形 × 保存していない変更なし → 'reload'", () => {
  const saved = baseModel();
  const other = baseModel();
  other.label = '外で書き換えた';
  assert.equal(judgeExternal(saved, reread(other), false), 'reload');
});

test("D0065-AC-03: 指示文だけが違っても（prompts/ のファイルの差）'reload'", () => {
  const saved = baseModel();
  const other = baseModel();
  other.stages[0]!.prompt = '外で書き換えた指示';
  assert.equal(judgeExternal(saved, reread(other), false), 'reload');
});

test("D0065-AC-04: 違う形 × 保存していない変更あり → 'choose'（'reload' ではない）", () => {
  const saved = baseModel();
  const other = baseModel();
  other.label = '外で書き換えた';
  const verdict = judgeExternal(saved, reread(other), true);
  assert.equal(verdict, 'choose');
  assert.notEqual(verdict, 'reload');
});

test("D0065-AC-04: 位置（layout.json）だけが違っても、保存していない変更があれば 'choose'", () => {
  const saved = baseModel();
  const other = baseModel();
  other.stages[0]!.x += 40;
  assert.equal(judgeExternal(saved, reread(other), true), 'choose');
  assert.equal(judgeExternal(saved, reread(other), false), 'reload');
});
