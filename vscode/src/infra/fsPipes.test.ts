// PipeStore の実装：pipes/ の中の devpipe-<名前>/ だけを読み書きする。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createFsPipeStore } from './fsPipes.ts';

async function tempPipes(): Promise<string> {
  const root = await mkdtemp(path.join(tmpdir(), 'pipes-'));
  await mkdir(path.join(root, 'devpipe-one', 'prompts'), { recursive: true });
  await writeFile(path.join(root, 'devpipe-one', 'pipe.toml'), '[pipe]\n', 'utf8');
  await writeFile(path.join(root, 'devpipe-one', 'prompts', '01_a.md'), 'A\n', 'utf8');
  await mkdir(path.join(root, 'not-a-pipe'));
  return root;
}

test('AC-31: 一覧・読む・書く・消す（devpipe-<名前>/ の中だけ）', async () => {
  const root = await tempPipes();
  try {
    const store = createFsPipeStore(root);
    assert.deepEqual(await store.listPipes(), ['devpipe-one']);
    assert.equal(await store.read('devpipe-one', 'pipe.toml'), '[pipe]\n');
    assert.equal(await store.read('devpipe-one', 'layout.json'), null);
    assert.deepEqual(await store.listPrompts('devpipe-one'), ['prompts/01_a.md']);
    await store.write('devpipe-two', 'prompts/01_b.md', 'B\n');
    assert.equal(await readFile(path.join(root, 'devpipe-two', 'prompts', '01_b.md'), 'utf8'), 'B\n');
    await store.remove('devpipe-one', 'prompts/01_a.md');
    assert.deepEqual(await store.listPrompts('devpipe-one'), []);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('AC-31: pipes/ の外や、決まった名前以外には書かない', async () => {
  const root = await tempPipes();
  try {
    const store = createFsPipeStore(root);
    await assert.rejects(() => store.write('devpipe-one', '../../escape.md', 'x'));
    await assert.rejects(() => store.write('../outside', 'pipe.toml', 'x'));
    await assert.rejects(() => store.write('devpipe-one', 'src/app.py', 'x'));
    await assert.rejects(() => store.write('devpipe-one', 'prompts/../pipe.toml', 'x'));
    await assert.rejects(() => store.remove('devpipe-one', 'pipe.toml'));
    assert.equal(await store.read('devpipe-one', '../../etc/passwd'), null);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('D0001-AC-18: .devpipe/pipes を根にしても、決まったファイルだけを読み書きする', async () => {
  const project = await mkdtemp(path.join(tmpdir(), 'app-'));
  try {
    const root = path.join(project, '.devpipe', 'pipes');
    const store = createFsPipeStore(root);
    assert.deepEqual(await store.listPipes(), []);
    await store.write('devpipe-x', 'pipe.toml', '[pipe]\n');
    await store.write('devpipe-x', 'prompts/01_a.md', 'A\n');
    assert.equal(await readFile(path.join(root, 'devpipe-x', 'pipe.toml'), 'utf8'), '[pipe]\n');
    assert.deepEqual(await store.listPipes(), ['devpipe-x']);
    await assert.rejects(() => store.write('devpipe-x', '../../../src/app.py', 'x'));
    await assert.rejects(() => store.write('devpipe-x', 'src/app.py', 'x'));
    await assert.rejects(() => store.write('..', 'pipe.toml', 'x'));
  } finally {
    await rm(project, { recursive: true, force: true });
  }
});
