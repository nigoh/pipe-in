// 通常のファイルかの確かめ（D0078。infra/fsFileProbe.ts）。AC-09。stat を 1 回呼ぶだけで、読むだけで書かない。
// 実物は一時フォルダ（test/tempDir.ts）で、失敗は偽の stat（手で書いた口）が投げて確かめる。時計・ネットワーク・子プロセスは使わない。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, symlink, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { recordingFs } from '../test/recordingFs.ts';
import { withTempDir } from '../test/tempDir.ts';
import { isRegularFile } from './fsFileProbe.ts';

test('D0078-AC-09: isRegularFile：通常のファイルは true', async () => {
  await withTempDir(async (base) => {
    const file = path.join(base, 'pipe-in');
    await writeFile(file, '#!/bin/sh\n');
    assert.equal(await isRegularFile(file), true);
  });
});

test('D0078-AC-09: isRegularFile：ディレクトリは false（pipe-in という名前のフォルダを起こさない）', async () => {
  await withTempDir(async (base) => {
    const dir = path.join(base, 'pipe-in');
    await mkdir(dir);
    assert.equal(await isRegularFile(dir), false);
  });
});

test('D0078-AC-09: isRegularFile：無いパス・親が無いパス・親がファイルのパスは false（例外を出さない）', async () => {
  await withTempDir(async (base) => {
    assert.equal(await isRegularFile(path.join(base, 'none')), false);
    assert.equal(await isRegularFile(path.join(base, 'a', 'b', 'pipe-in')), false);
    await writeFile(path.join(base, 'plain'), '中身\n');
    assert.equal(await isRegularFile(path.join(base, 'plain', 'pipe-in')), false);
  });
});

test('D0078-AC-09: isRegularFile：リンク先が通常のファイルならリンクも true（venv の bin/pipe-in はリンクのことがある）', async (t) => {
  await withTempDir(async (base) => {
    const target = path.join(base, 'real-pipe-in');
    const link = path.join(base, 'pipe-in');
    await writeFile(target, '#!/bin/sh\n');
    try {
      await symlink(target, link, 'file');
    } catch (e) {
      t.skip(`シンボリックリンクを作れない環境（${String((e as { code?: unknown }).code)}）`);
      return;
    }
    assert.equal(await isRegularFile(link), true);
  });
});

test('D0078-AC-09: isRegularFile：リンク先がフォルダのリンク・切れたリンクは false', async (t) => {
  await withTempDir(async (base) => {
    const dir = path.join(base, 'real-dir');
    await mkdir(dir);
    const toDir = path.join(base, 'link-to-dir');
    const broken = path.join(base, 'broken');
    try {
      await symlink(dir, toDir, 'dir');
      await symlink(path.join(base, 'missing'), broken, 'file');
    } catch (e) {
      t.skip(`シンボリックリンクを作れない環境（${String((e as { code?: unknown }).code)}）`);
      return;
    }
    assert.equal(await isRegularFile(toDir), false);
    assert.equal(await isRegularFile(broken), false);
  });
});

test('D0078-AC-09: isRegularFile は stat を1回だけ呼ぶ（読んだパスの記録が stat の1件。readFile・readdir・readHead・realpath を呼ばない）', async () => {
  await withTempDir(async (base) => {
    const file = path.join(base, 'pipe-in');
    await writeFile(file, '#!/bin/sh\n');
    for (const target of [file, path.join(base, 'none'), base]) {
      const { fs, calls } = recordingFs();
      await isRegularFile(target, { fs });
      assert.deepEqual(calls, [{ op: 'stat', path: target }], target);
    }
  });
});

const throws = (value: unknown) => async (): Promise<never> => {
  throw value;
};

test('D0078-AC-09: 偽の stat がどんな失敗（code つき・code なし・文字・null）を投げても false で、例外を外に出さない', async () => {
  const failures: unknown[] = [
    Object.assign(new Error('ENOENT'), { code: 'ENOENT' }),
    Object.assign(new Error('EACCES'), { code: 'EACCES' }),
    Object.assign(new Error('ELOOP'), { code: 'ELOOP' }),
    new Error('理由の分からない失敗'),
    'ENOENT',
    null,
    undefined,
    42,
  ];
  for (const failure of failures) {
    assert.equal(await isRegularFile('/work/bin/pipe-in', { fs: { stat: throws(failure) as never } }), false, String(failure));
  }
});

test('D0078-AC-09: 偽の stat の isFile() が真なら true、偽なら false（渡したパスがそのまま stat に渡る）', async () => {
  const seen: string[] = [];
  const answers = (isFile: boolean) => async (p: unknown): Promise<{ isFile(): boolean }> => {
    seen.push(String(p));
    return { isFile: () => isFile };
  };
  assert.equal(await isRegularFile('/work/bin/pipe-in', { fs: { stat: answers(true) as never } }), true);
  assert.equal(await isRegularFile('/work/bin/other', { fs: { stat: answers(false) as never } }), false);
  assert.deepEqual(seen, ['/work/bin/pipe-in', '/work/bin/other']);
});
