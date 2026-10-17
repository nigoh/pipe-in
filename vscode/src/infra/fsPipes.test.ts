// PipeStore の実装：置き場所の中の pipe-in-<名前>/（前の版の devpipe-<名前>/ も）だけを読み書きする。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, readdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createFsPipeStore } from './fsPipes.ts';

async function tempPipes(): Promise<string> {
  const root = await mkdtemp(path.join(tmpdir(), 'pipes-'));
  await mkdir(path.join(root, 'pipe-in-one', 'prompts'), { recursive: true });
  await writeFile(path.join(root, 'pipe-in-one', 'pipe.toml'), '[pipe]\n', 'utf8');
  await writeFile(path.join(root, 'pipe-in-one', 'prompts', '01_a.md'), 'A\n', 'utf8');
  await mkdir(path.join(root, 'devpipe-old', 'prompts'), { recursive: true });
  await writeFile(path.join(root, 'devpipe-old', 'pipe.toml'), '[pipe]\n# 前の版\n', 'utf8');
  await mkdir(path.join(root, 'not-a-pipe'));
  await mkdir(path.join(root, 'other'));
  await writeFile(path.join(root, 'other', 'pipe.toml'), '[pipe]\n', 'utf8');
  await mkdir(path.join(root, 'pipe-in'));
  await writeFile(path.join(root, 'pipe-in', 'pipe.toml'), '[pipe]\n', 'utf8');
  return root;
}

test('AC-31・D0006-AC-19: 一覧・読む・書く・消す（pipe-in-<名前>/ の中だけ）', async () => {
  const root = await tempPipes();
  try {
    const store = createFsPipeStore(root);
    assert.deepEqual(await store.listPipes(), ['devpipe-old', 'pipe-in-one']);
    assert.equal(await store.read('pipe-in-one', 'pipe.toml'), '[pipe]\n');
    assert.equal(await store.read('pipe-in-one', 'layout.json'), null);
    assert.deepEqual(await store.listPrompts('pipe-in-one'), ['prompts/01_a.md']);
    await store.write('pipe-in-two', 'prompts/01_b.md', 'B\n');
    assert.equal(await readFile(path.join(root, 'pipe-in-two', 'prompts', '01_b.md'), 'utf8'), 'B\n');
    await store.remove('pipe-in-one', 'prompts/01_a.md');
    assert.deepEqual(await store.listPrompts('pipe-in-one'), []);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('D0006-AC-19: 前の版のフォルダ（devpipe-<名前>/）も読み書きでき、書いても pipe-in-<名前>/ は作らない', async () => {
  const root = await tempPipes();
  try {
    const store = createFsPipeStore(root);
    assert.equal(await store.read('devpipe-old', 'pipe.toml'), '[pipe]\n# 前の版\n');
    await store.write('devpipe-old', 'prompts/01_a.md', 'A\n');
    assert.equal(await readFile(path.join(root, 'devpipe-old', 'prompts', '01_a.md'), 'utf8'), 'A\n');
    assert.deepEqual(await store.listPrompts('devpipe-old'), ['prompts/01_a.md']);
    assert.ok(!(await readdir(root)).includes('pipe-in-old'));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('AC-31・D0006-AC-19: 置き場所の外や、決まった名前以外のフォルダ（other/・../escape・pipe-in/）は読まず書かない', async () => {
  const root = await tempPipes();
  try {
    const store = createFsPipeStore(root);
    await assert.rejects(() => store.write('pipe-in-one', '../../escape.md', 'x'));
    await assert.rejects(() => store.write('../outside', 'pipe.toml', 'x'));
    await assert.rejects(() => store.write('../escape', 'pipe.toml', 'x'));
    await assert.rejects(() => store.write('other', 'pipe.toml', 'x'));
    await assert.rejects(() => store.write('pipe-in', 'pipe.toml', 'x'));
    await assert.rejects(() => store.write('pipe-in-', 'pipe.toml', 'x'));
    await assert.rejects(() => store.write('devpipe', 'pipe.toml', 'x'));
    await assert.rejects(() => store.write('pipe-in-one', 'src/app.py', 'x'));
    await assert.rejects(() => store.write('pipe-in-one', 'prompts/../pipe.toml', 'x'));
    await assert.rejects(() => store.remove('pipe-in-one', 'pipe.toml'));
    assert.equal(await store.read('pipe-in-one', '../../etc/passwd'), null);
    assert.equal(await store.read('other', 'pipe.toml'), null);
    assert.equal(await store.read('pipe-in', 'pipe.toml'), null);
    assert.equal(await store.read('../escape', 'pipe.toml'), null);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('D0001-AC-18・D0006-AC-19: .pipe-in/pipes を根にしても、決まったファイルだけを読み書きする', async () => {
  const project = await mkdtemp(path.join(tmpdir(), 'app-'));
  try {
    const root = path.join(project, '.pipe-in', 'pipes');
    const store = createFsPipeStore(root);
    assert.deepEqual(await store.listPipes(), []);
    await store.write('pipe-in-x', 'pipe.toml', '[pipe]\n');
    await store.write('pipe-in-x', 'prompts/01_a.md', 'A\n');
    assert.equal(await readFile(path.join(root, 'pipe-in-x', 'pipe.toml'), 'utf8'), '[pipe]\n');
    assert.deepEqual(await store.listPipes(), ['pipe-in-x']);
    await assert.rejects(() => store.write('pipe-in-x', '../../../src/app.py', 'x'));
    await assert.rejects(() => store.write('pipe-in-x', 'src/app.py', 'x'));
    await assert.rejects(() => store.write('..', 'pipe.toml', 'x'));
  } finally {
    await rm(project, { recursive: true, force: true });
  }
});
