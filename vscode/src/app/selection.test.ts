// 選んだ実行を覚える（D0019）：口 MemoryStore（workspaceState がそのまま満たす）に、場所の目印と実行の目印だけを書く。
// 新しい部品（app/selection.ts）は、呼んだところで落ちるように、テストの中で読み込む。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { stateJson } from '../test/fixtures.ts';
import { withTempDir } from '../test/tempDir.ts';

const sel = () => import('./selection.ts');

const MEMORY_KEY = 'pipe-in.selectedRun';

/** 手で書いた偽の workspaceState。呼ばれた操作を全部記録する。 */
function fakeStore(initial: Record<string, unknown> = {}) {
  const data = new Map<string, unknown>(Object.entries(initial));
  const calls: [string, ...unknown[]][] = [];
  return {
    data,
    calls,
    get(key: string): unknown {
      calls.push(['get', key]);
      return data.get(key);
    },
    update(key: string, value: unknown): PromiseLike<void> {
      calls.push(['update', key, value]);
      data.set(key, value);
      return Promise.resolve();
    },
  };
}

test('D0019-AC-22: run を選ぶと、場所の目印と run の目印が workspaceState に残る', async () => {
  const { rememberRun } = await sel();
  const store = fakeStore();
  await rememberRun(store, 'wt.feat-x|survey');
  assert.deepEqual(store.data.get(MEMORY_KEY), { place: 'wt.feat-x', id: 'survey' });
});

test('D0019-AC-22: 直下の run（id が空）も、archive の run も残る', async () => {
  const { rememberRun } = await sel();
  const store = fakeStore();
  await rememberRun(store, 'here|');
  assert.deepEqual(store.data.get(MEMORY_KEY), { place: 'here', id: '' });
  await rememberRun(store, 'main|archive/20261017-100000-2');
  assert.deepEqual(store.data.get(MEMORY_KEY), { place: 'main', id: 'archive/20261017-100000-2' });
});

test('D0019-AC-22: パネルを閉じて開き直す（別の restoreRun）と、同じ run が選ばれている', async () => {
  const { rememberRun, restoreRun } = await sel();
  const first = fakeStore();
  await rememberRun(first, 'wt.feat-x|survey');
  // VSCode を開き直した：同じ保存場所（data）を別の口から読む
  const reopened = fakeStore(Object.fromEntries(first.data));
  assert.equal(restoreRun(reopened), 'wt.feat-x|survey');
  for (const key of ['here|', 'here|diagrams', 'main|archive/20261017-100000']) {
    await rememberRun(first, key);
    assert.equal(restoreRun(fakeStore(Object.fromEntries(first.data))), key);
  }
});

test('D0019-AC-22: 何も覚えていないときは null（今までの既定）', async () => {
  const { restoreRun } = await sel();
  assert.equal(restoreRun(fakeStore()), null);
});

test('D0019-AC-22: 覚える場所の鍵は pipe-in.selectedRun の1つだけ', async () => {
  const { rememberRun } = await sel();
  const store = fakeStore();
  await rememberRun(store, 'here|diagrams');
  assert.deepEqual([...store.data.keys()], [MEMORY_KEY]);
});

const BAD_VALUES: [string, unknown][] = [
  ['null', null],
  ['数', 3],
  ['文字', 'here|diagrams'],
  ['配列', ['here', 'x']],
  ['place が数', { place: 1, id: '' }],
  ['id が数', { place: 'here', id: 7 }],
  ['id が無い', { place: 'here' }],
  ['place が無い', { id: 'x' }],
  ['空のオブジェクト', {}],
  ['知らない place', { place: 'elsewhere', id: '' }],
  ['id が ..', { place: 'here', id: '..' }],
  ['id が ../x', { place: 'here', id: '../x' }],
  ['id が絶対パス', { place: 'here', id: '/etc/passwd' }],
  ['id が \\ を含む', { place: 'here', id: 'a\\b' }],
  ['id が archive/..', { place: 'here', id: 'archive/../x' }],
  ['id が長すぎる', { place: 'here', id: 'a'.repeat(5000) }],
  ['place が長すぎる', { place: `wt.${'a'.repeat(500)}`, id: '' }],
];

for (const [label, value] of BAD_VALUES) {
  test(`D0019-AC-23: 壊れた値は使わず（null）、例外を出さない：${label}`, async () => {
    const { restoreRun } = await sel();
    assert.equal(restoreRun(fakeStore({ [MEMORY_KEY]: value })), null);
  });
}

test('D0019-AC-23: 覚えた値から直接パスを作らない：restoreRun が返すのは 場所|id の目印だけ（パスではない）', async () => {
  const { restoreRun } = await sel();
  const key = restoreRun(fakeStore({ [MEMORY_KEY]: { place: 'wt.feat-x', id: 'survey' } }));
  assert.equal(key, 'wt.feat-x|survey');
  assert.ok(!path.isAbsolute(key!));
});

test('D0019-AC-25: 形の違う目印は覚えない（update を呼ばない）', async () => {
  const { rememberRun } = await sel();
  const store = fakeStore();
  for (const bad of ['', 'diagrams', 'here|../x', 'here|/etc', 'zzz|x', 'here|a\\b']) await rememberRun(store, bad);
  assert.deepEqual(store.calls, []);
  assert.equal(store.data.size, 0);
});

test('D0019-AC-25: 覚える処理は workspaceState の update だけを呼ぶ（それ以外の操作は無い）', async () => {
  const { rememberRun } = await sel();
  const store = fakeStore();
  await rememberRun(store, 'wt.feat-x|survey');
  assert.deepEqual(store.calls, [['update', MEMORY_KEY, { place: 'wt.feat-x', id: 'survey' }]]);
});

test('D0019-AC-25: 覚える処理の前後で、work_dir の中身（名前・内容）が変わらない', async () => {
  const { rememberRun } = await sel();
  await withTempDir(async (dir) => {
    const work = path.join(dir, 'docs', 'pipeline');
    await mkdir(path.join(work, 'diagrams'), { recursive: true });
    await writeFile(path.join(work, 'state.json'), stateJson({ final: 'PASSED' }));
    await writeFile(path.join(work, 'diagrams', 'state.json'), stateJson({ pipe: 'diagrams' }));
    const snapshot = async () => {
      const names = (await readdir(dir, { recursive: true })).sort();
      const texts = await Promise.all(names.map((n) => readFile(path.join(dir, n), 'utf8').catch(() => 'DIR')));
      return { names, texts };
    };
    const before = await snapshot();
    const store = fakeStore();
    await rememberRun(store, 'here|diagrams');
    await rememberRun(store, 'wt.feat-x|survey');
    assert.deepEqual(await snapshot(), before);
  });
});
