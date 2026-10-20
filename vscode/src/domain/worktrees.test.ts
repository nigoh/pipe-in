// 別の worktree の登録の読み方と受け入れの判断（D0019）。純粋な関数だけ（ファイルに触れない）。
// 新しい部品（domain/worktrees.ts）は、呼んだところで落ちるように、テストの中で読み込む。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';

const wt = () => import('./worktrees.ts');

test('D0019-AC-16: parseGitdirLine は「gitdir: <パス>」の1行（.git ファイルの形）から、パスを取り出す', async () => {
  const { parseGitdirLine } = await wt();
  assert.equal(parseGitdirLine('gitdir: /w/main/.git/worktrees/feat-x\n'), '/w/main/.git/worktrees/feat-x');
  assert.equal(parseGitdirLine('gitdir: /w/main/.git/worktrees/feat-x'), '/w/main/.git/worktrees/feat-x');
  assert.equal(parseGitdirLine('gitdir: C:/w/main/.git/worktrees/feat-x\r\n'), 'C:/w/main/.git/worktrees/feat-x');
  assert.equal(parseGitdirLine('gitdir: ../main/.git/worktrees/x\n'), '../main/.git/worktrees/x', '相対パスもそのまま返す（受け入れは別で判断する）');
});

for (const [label, text] of [
  ['空', ''],
  ['改行だけ', '\n'],
  ['gitdir: だけ', 'gitdir:'],
  ['gitdir: のあとが空白だけ', 'gitdir:   \n'],
  ['別の書き出し', 'hello world'],
  ['大文字', 'GITDIR: /w/x'],
  ['ref の行', 'ref: refs/heads/main'],
  ['gitdir の前に別の行', 'x\ngitdir: /w/x'],
] as const) {
  test(`D0019-AC-16: 壊れた .git ファイルの行は null：${label}`, async () => {
    const { parseGitdirLine } = await wt();
    assert.equal(parseGitdirLine(text), null);
  });
}

test('D0019-AC-15: branchOf は HEAD の「ref: refs/heads/<名>」から名を取り出す。detached などは null', async () => {
  const { branchOf } = await wt();
  assert.equal(branchOf('ref: refs/heads/main\n'), 'main');
  assert.equal(branchOf('ref: refs/heads/feat/export-csv\n'), 'feat/export-csv');
  assert.equal(branchOf('ref: refs/heads/feat/x'), 'feat/x');
  for (const text of ['0123456789abcdef0123456789abcdef01234567\n', '', 'ref: refs/remotes/origin/main', 'ref: refs/heads/', 'ref:']) {
    assert.equal(branchOf(text), null, text);
  }
});

const SHA1 = '0123456789abcdef0123456789abcdef01234567';
const SHA256 = '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

test('D0019-AC-15: headLabel は、ref なら ブランチ名、detached HEAD（40 桁か 64 桁の 16 進）なら先頭 7 文字の短い ID、ほかは null', async () => {
  const { headLabel } = await wt();
  assert.equal(headLabel('ref: refs/heads/feat/export-csv\n'), 'feat/export-csv');
  assert.equal(headLabel('ref: refs/heads/main'), 'main');
  assert.equal(headLabel(`${SHA1}\n`), '0123456');
  assert.equal(headLabel(SHA1), '0123456');
  assert.equal(headLabel(`${SHA256}\n`), '0123456');
  for (const text of ['', '\n', 'ref: refs/remotes/origin/main', 'ref: refs/heads/', 'ref:', SHA1.slice(0, 39), `${SHA1}0`, SHA1.replace('0', 'g'), 'hello', `${SHA1.toUpperCase()}x`]) {
    assert.equal(headLabel(text), null, JSON.stringify(text));
  }
});

test('D0019-AC-15: placeLabel は、HEAD から読めるブランチ名か短い ID があればそれ、何も読めなければ worktree のフォルダ名（最後の手段）', async () => {
  const { placeLabel } = await wt();
  assert.equal(placeLabel('ref: refs/heads/feat/export-csv\n', path.resolve('/w/wt-a')), 'feat/export-csv');
  assert.equal(placeLabel(`${SHA1}\n`, path.resolve('/w/wt-a')), '0123456', 'detached HEAD はフォルダ名でなく短い ID');
  assert.equal(placeLabel(null, path.resolve('/w/wt-a')), 'wt-a');
  assert.equal(placeLabel('こわれた', path.resolve('/w/wt-a')), 'wt-a');
});

test('D0019-AC-18: isRegistryName は 登録名として安全な名前だけ（パスに化ける文字・長すぎる名前・. と .. は通さない）', async () => {
  const { isRegistryName } = await wt();
  for (const name of ['feat-x', 'a.b', 'A_1', 'x', 'a'.repeat(100), 'feat-x1']) assert.equal(isRegistryName(name), true, name);
  for (const name of ['', '.', '..', 'a/b', 'a\\b', 'a b', '../x', 'a'.repeat(101), 'a:b', 'あ']) assert.equal(isRegistryName(name), false, name);
});

test('D0019-AC-18: samePath は整えてから比べる。大文字小文字の無視は指定したときだけ', async () => {
  const { samePath } = await wt();
  assert.equal(samePath('/a/b/../c', '/a/c', false), true);
  assert.equal(samePath('/a/c/', '/a/c', false), true);
  assert.equal(samePath('/a/c', '/a/d', false), false);
  assert.equal(samePath('/a/C', '/a/c', false), false);
  assert.equal(samePath('/a/C', '/a/c', true), true);
  assert.equal(samePath('/a/C', '/a/d', true), false);
});

test('D0019-AC-18: workDirIn は、work_dir の設定が worktree の中に収まるときだけ絶対パスを返す', async () => {
  const { workDirIn } = await wt();
  const root = path.resolve('/w/app');
  assert.equal(workDirIn(root, 'docs/pipeline'), path.join(root, 'docs', 'pipeline'));
  assert.equal(workDirIn(root, 'docs/../ok'), path.join(root, 'ok'));
  assert.equal(workDirIn(root, path.join(root, 'docs', 'pipeline')), path.join(root, 'docs', 'pipeline'), '中を指す絶対パスは収まる');
});

for (const setting of ['..', '../x', '../../etc', 'docs/../..', 'docs/../../x', path.resolve('/etc'), path.resolve('/w/other/docs'), path.resolve('/w/app-evil/docs')]) {
  test(`D0019-AC-18: work_dir の設定が worktree の外を指すなら null：${setting}`, async () => {
    const { workDirIn } = await wt();
    assert.equal(workDirIn(path.resolve('/w/app'), setting), null);
  });
}
