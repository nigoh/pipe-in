// VersionStore の実装：拡張の保存場所の中の pipe-in-<名前>/<版の id>.json だけを読み書きする。プロジェクトには書かない。
// 保存場所は拡張の ID ごとで、前の版の拡張から引き継がないので、前の版のフォルダ名は受け付けない。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createFsVersionStore } from './fsVersions.ts';

const T = 1760000000000;

test('AC-70: 版を書く・一覧にする・読む・消す（根の中の pipe-in-<名前>/ だけ）', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'versions-'));
  try {
    const store = createFsVersionStore(root);
    assert.deepEqual(await store.list('pipe-in-one'), []);
    await store.write('pipe-in-one', `${T}.json`, '{}');
    await store.write('pipe-in-one', `${T + 1}-draft.json`, '{"d":1}');
    assert.equal(await readFile(path.join(root, 'pipe-in-one', `${T}.json`), 'utf8'), '{}');
    assert.deepEqual((await store.list('pipe-in-one')).sort(), [`${T}.json`, `${T + 1}-draft.json`]);
    assert.equal(await store.read('pipe-in-one', `${T + 1}-draft.json`), '{"d":1}');
    assert.equal(await store.read('pipe-in-one', `${T + 9}.json`), null);
    await store.remove('pipe-in-one', `${T}.json`);
    assert.deepEqual(await store.list('pipe-in-one'), [`${T + 1}-draft.json`]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('D0065-AC-09: 実物の口でも <id>-external.json を書ける・一覧に出せる・読める・消せる', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'versions-'));
  try {
    const store = createFsVersionStore(root);
    await store.write('pipe-in-one', `${T}-external.json`, '{"e":1}');
    assert.equal(await readFile(path.join(root, 'pipe-in-one', `${T}-external.json`), 'utf8'), '{"e":1}');
    assert.deepEqual(await store.list('pipe-in-one'), [`${T}-external.json`]);
    assert.equal(await store.read('pipe-in-one', `${T}-external.json`), '{"e":1}');
    await store.remove('pipe-in-one', `${T}-external.json`);
    assert.deepEqual(await store.list('pipe-in-one'), []);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('D0065-AC-09: -external に似た形（二重の印・別の綴り・拡張子なし・パス）は、書かない・読まない・一覧に出さない', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'versions-'));
  try {
    const store = createFsVersionStore(root);
    for (const file of [`${T}-external-draft.json`, `${T}-draft-external.json`, `${T}-ext.json`, `${T}-externals.json`, `${T}-external`, `../${T}-external.json`, `..\\${T}-external.json`, '-external.json']) {
      await assert.rejects(store.write('pipe-in-one', file, 'x'), Error, file);
      assert.equal(await store.read('pipe-in-one', file), null, file);
    }
    assert.deepEqual(await readdir(root), []);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('AC-70: 形の違うフォルダ名・ファイル名・根の外へ出るパスは、読まず書かない', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'versions-'));
  try {
    const store = createFsVersionStore(root);
    for (const [pipe, file] of [['pipe-in-one', 'pipe.toml'], ['pipe-in-one', '../x.json'], ['../escape', `${T}.json`], ['pipe-in-one', `..\\${T}.json`], ['other', `${T}.json`], ['dev' + 'pipe-one', `${T}.json`]] as const) {
      await assert.rejects(store.write(pipe, file, 'x'), Error, `${pipe}/${file}`);
      assert.equal(await store.read(pipe, file), null);
    }
    assert.deepEqual(await readdir(root), []);
    // 版の形でないファイルは一覧に出さない
    await store.write('pipe-in-one', `${T}.json`, '{}');
    assert.deepEqual(await store.list('pipe-in-one'), [`${T}.json`]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
