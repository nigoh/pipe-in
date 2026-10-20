// パネルから来るメッセージの検め（D0019-AC-31）。種類は ready・openArtifact・selectRun の3つのまま。
// selectRun の id は「実行の目印（<場所>|<id>）」の形だけを通し、形の違う値は捨てる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseWebviewMessage } from './messages.ts';

test('D0019-AC-31: selectRun は正しい実行の目印（場所|id）を通す', () => {
  for (const id of ['here|', 'here|diagrams', 'main|archive/20261017-100000', 'main|archive/20261017-100000-2', 'wt.feat-x|spec-qa', 'wt.feat-x|']) {
    assert.deepEqual(parseWebviewMessage({ type: 'selectRun', id }), { type: 'selectRun', id }, id);
  }
});

const BAD_IDS: [string, unknown][] = [
  ['数', 3],
  ['null', null],
  ['id が無い', undefined],
  ['空文字', ''],
  ['昔の形（パイプ名だけ）', 'diagrams'],
  ['昔の形（logs）', 'logs'],
  ['場所だけ', 'here'],
  ['知らない場所', 'elsewhere|x'],
  ['..', 'here|..'],
  ['../x', 'here|../x'],
  ['archive の外へ', 'here|archive/../x'],
  ['/ を含む', 'here|a/b'],
  ['\\ を含む', 'here|a\\b'],
  ['絶対パス', 'here|/etc/passwd'],
  ['Windows の絶対パス', 'here|C:\\Windows'],
  ['長すぎる', `here|${'a'.repeat(5000)}`],
  ['オブジェクト', { place: 'here', id: '' }],
  ['配列', ['here|']],
];

for (const [label, id] of BAD_IDS) {
  test(`D0019-AC-31: 形の違う selectRun の id は捨てる（null）：${label}`, () => {
    assert.equal(parseWebviewMessage({ type: 'selectRun', id }), null);
  });
}

test('D0019-AC-31: メッセージの種類は増えない：ready・openArtifact は今までどおり、ほかの type は捨てる', () => {
  assert.deepEqual(parseWebviewMessage({ type: 'ready' }), { type: 'ready' });
  assert.deepEqual(parseWebviewMessage({ type: 'openArtifact', name: '01_requirements.md' }), { type: 'openArtifact', name: '01_requirements.md' });
  assert.equal(parseWebviewMessage({ type: 'openArtifact' }), null);
  for (const type of ['selectRuns', 'select', 'openWorktree', 'remember', 'save', '']) {
    assert.equal(parseWebviewMessage({ type, id: 'here|', name: 'x' }), null, type);
  }
  for (const value of [null, undefined, 3, 'ready', []] as unknown[]) assert.equal(parseWebviewMessage(value), null);
});

test('D0019-AC-31: 余計な項目が付いていても、通すのは type と id だけ', () => {
  const parsed = parseWebviewMessage({ type: 'selectRun', id: 'here|diagrams', path: '/etc/passwd', dir: '../x' });
  assert.deepEqual(parsed, { type: 'selectRun', id: 'here|diagrams' });
});
