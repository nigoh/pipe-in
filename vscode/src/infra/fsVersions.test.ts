// VersionStore の実装：拡張の保存場所の中の devpipe-<名前>/<版の id>.json だけを読み書きする。プロジェクトには書かない。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createFsVersionStore } from './fsVersions.ts';

const T = 1760000000000;

test('AC-70: 版を書く・一覧にする・読む・消す（根の中の devpipe-<名前>/ だけ）', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'versions-'));
  try {
    const store = createFsVersionStore(root);
    assert.deepEqual(await store.list('devpipe-one'), []);
    await store.write('devpipe-one', `${T}.json`, '{}');
    await store.write('devpipe-one', `${T + 1}-draft.json`, '{"d":1}');
    assert.equal(await readFile(path.join(root, 'devpipe-one', `${T}.json`), 'utf8'), '{}');
    assert.deepEqual((await store.list('devpipe-one')).sort(), [`${T}.json`, `${T + 1}-draft.json`]);
    assert.equal(await store.read('devpipe-one', `${T + 1}-draft.json`), '{"d":1}');
    assert.equal(await store.read('devpipe-one', `${T + 9}.json`), null);
    await store.remove('devpipe-one', `${T}.json`);
    assert.deepEqual(await store.list('devpipe-one'), [`${T + 1}-draft.json`]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('AC-70: 形の違うフォルダ名・ファイル名・根の外へ出るパスは、読まず書かない', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'versions-'));
  try {
    const store = createFsVersionStore(root);
    for (const [pipe, file] of [['devpipe-one', 'pipe.toml'], ['devpipe-one', '../x.json'], ['../escape', `${T}.json`], ['devpipe-one', `..\\${T}.json`], ['other', `${T}.json`]] as const) {
      await assert.rejects(store.write(pipe, file, 'x'), Error, `${pipe}/${file}`);
      assert.equal(await store.read(pipe, file), null);
    }
    assert.deepEqual(await readdir(root), []);
    // 版の形でないファイルは一覧に出さない
    await store.write('devpipe-one', `${T}.json`, '{}');
    assert.deepEqual(await store.list('devpipe-one'), [`${T}.json`]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
