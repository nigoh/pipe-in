// 基盤の読み口 readHead（infra/readOnlyFs.ts）：短く返る読みでも、いっぱいになるか、ファイルの終わりまで繰り返し読む（D0025-AC-42）。
// ネットワークや FUSE のファイルは、1 回の読みが頼んだ量より短く返ることがある。1 回しか読まないと、途中までの文字が「切れた」案内なしで出てしまう。
// readHead は node:fs/promises の open を直に使い、口（ReadOnlyFs）は readHead そのものなので、偽の口では短い読みを作れない。
// そこで、node:fs/promises の open だけを、このテストの間（try/finally で必ず戻す）、本物の open を包んだ手書きの偽物に替える：
//   開いたファイルの read を、頼んだ量にかかわらず step バイトまでしか返さないようにする（ほかは本物のまま）。
//   builtin の ESM の束縛へは syncBuiltinESMExports で届ける（readOnlyFs.ts の `import { open } from 'node:fs/promises'` は、この束縛を見る）。
// node:test は 1 つのテストファイルを 1 つのプロセスで流し、ファイルの中のテストは順に流れる。ほかのファイルには影響しない。
// 製品のコード（readOnlyFs.ts）の形は変えない前提で書いた。短い読みを起こせない（偽の open が束縛に届かない）ときは、readHead の検査の前に、
// 仕掛けの不具合として落ちる（readHead の誤りと取り違えない）。
import { createRequire, syncBuiltinESMExports } from 'node:module';
import path from 'node:path';
import { writeFile } from 'node:fs/promises';
import * as fsNamespace from 'node:fs/promises';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { FileHandle } from 'node:fs/promises';
import { withTempDir } from '../test/tempDir.ts';
import { nodeReadOnlyFs } from './readOnlyFs.ts';

type OpenFn = typeof import('node:fs/promises').open;

/** node:fs/promises の CommonJS の exports（ESM の default と同じ物）。ここを書き換えて、syncBuiltinESMExports で ESM の束縛に届ける */
const cjs = createRequire(import.meta.url)('node:fs/promises') as { open: OpenFn };
/** 本物の open（どのテストより前に控える。ESM の束縛は、替えたあと偽物を指すので使わない） */
const REAL_OPEN: OpenFn = cjs.open;

interface ShortReads {
  /** read が頼まれた量（length）の並び */
  asked: number[];
  /** read が実際に返した量（bytesRead）の並び */
  gave: number[];
}

/** run の間だけ、open が返すファイルの read を step バイトまでしか返さないものにする。終わったら（失敗しても）本物に戻す */
async function withShortReads<T>(step: number, run: (log: ShortReads) => Promise<T>): Promise<T> {
  const log: ShortReads = { asked: [], gave: [] };
  const fake = (async (...args: Parameters<OpenFn>): Promise<FileHandle> => {
    const handle = await REAL_OPEN(...args);
    return new Proxy(handle, {
      get(target, prop) {
        if (prop === 'read') {
          return async (buffer: Buffer, offset: number, length: number, position: number | null) => {
            log.asked.push(length);
            const result = await target.read(buffer, offset, Math.min(length, step), position);
            log.gave.push(result.bytesRead);
            return result;
          };
        }
        const value: unknown = Reflect.get(target, prop, target);
        return typeof value === 'function' ? value.bind(target) : value;
      },
    });
  }) as OpenFn;
  try {
    cjs.open = fake;
    syncBuiltinESMExports();
    assert.equal(fsNamespace.open, fake, '仕掛け：偽の open が node:fs/promises の ESM の束縛に届いている（届かないと readHead は本物の open を使い、検査にならない）');
    return await run(log);
  } finally {
    cjs.open = REAL_OPEN;
    syncBuiltinESMExports();
  }
}

/** 1 回の読みが step バイトまでしか返らない偽の open の下で、file の先頭 maxBytes バイトまでを readHead で読む */
async function headWithShortReads(file: string, maxBytes: number, step: number): Promise<{ head: string; log: ShortReads }> {
  return withShortReads(step, async (log) => ({ head: await nodeReadOnlyFs.readHead(file, maxBytes), log }));
}

test('D0025-AC-42: 検査の足場：偽の open の下で、1 回の read は step バイトまでしか返らない。終わったあとは本物の open に戻る（今のまま通る。守る）', async () => {
  await withTempDir(async (dir) => {
    const file = path.join(dir, 'a.txt');
    await writeFile(file, '0123456789'.repeat(10));
    await withShortReads(7, async (log) => {
      const handle = await fsNamespace.open(file, 'r');
      try {
        const buffer = Buffer.alloc(100);
        const { bytesRead } = await handle.read(buffer, 0, 100, 0);
        assert.equal(bytesRead, 7, '100 バイト頼んでも 7 バイトまで');
        assert.deepEqual(log.asked, [100]);
        assert.deepEqual(log.gave, [7]);
      } finally {
        await handle.close();
      }
    });
    assert.equal(fsNamespace.open, REAL_OPEN, '終わったあとは本物の open に戻っている');
  });
});

test('D0025-AC-42: 1 回の読みが 7 バイトずつしか返らなくても、readHead はファイルの終わりまで読んで全部返す（上限がファイルより大きいとき）', async () => {
  await withTempDir(async (dir) => {
    const file = path.join(dir, '00_input.md');
    const content = '0123456789'.repeat(100);
    await writeFile(file, content);
    const { head, log } = await headWithShortReads(file, 262_145, 7);
    assert.equal(head, content);
    assert.ok(log.asked.length >= Math.ceil(content.length / 7), `read を繰り返している（${log.asked.length} 回）`);
    assert.ok(log.gave.every((n) => n <= 7), '偽の open が短い読みを返した');
    assert.equal(log.gave.at(-1), 0, '最後はファイルの終わり（0 バイト）で止まる');
  });
});

test('D0025-AC-42: 短い読みでも、上限（maxBytes）までいっぱいになったら読むのをやめ、先頭の maxBytes バイトだけを返す（上限がファイルより小さいとき）', async () => {
  await withTempDir(async (dir) => {
    const file = path.join(dir, 'big.md');
    await writeFile(file, `${'a'.repeat(3000)}${'b'.repeat(3000)}`);
    const { head, log } = await headWithShortReads(file, 4096, 1000);
    assert.equal(head, `${'a'.repeat(3000)}${'b'.repeat(1096)}`);
    assert.ok(log.asked.length >= 5, `read を繰り返している（${log.asked.length} 回）`);
    assert.ok(Math.max(...log.asked) <= 4096, '頼む量は上限を超えない');
    assert.equal(
      log.gave.reduce((sum, n) => sum + n, 0),
      4096,
      '読んだ合計はちょうど上限',
    );
  });
});

test('D0025-AC-42: 読みの切れ目が 3 バイト文字の途中に来ても（4 バイトずつ）、全部を読んでから文字にするので、文字は壊れない', async () => {
  await withTempDir(async (dir) => {
    const file = path.join(dir, 'ja.md');
    const content = 'あいうえお'.repeat(50);
    await writeFile(file, content);
    const { head } = await headWithShortReads(file, 262_145, 4);
    assert.equal(head, content);
    assert.ok(!head.includes('�'), 'U+FFFD が入っていない');
  });
});

test('D0025-AC-42: 空のファイルは、短い読みの下でも空の文字を返して止まる（読みの繰り返しがファイルの終わりで終わる。1 回読んで終わる作りでも通る。守る）', async () => {
  await withTempDir(async (dir) => {
    const file = path.join(dir, 'empty.md');
    await writeFile(file, '');
    const { head, log } = await headWithShortReads(file, 262_145, 7);
    assert.equal(head, '');
    assert.deepEqual(log.gave, [0], '1 回読んで 0 バイトで止まる');
  });
});

test('D0025-AC-42: 読みが短くない（1 回で全部返る）ふつうの場合は、本物のファイルでも今までどおり全部返す（今のまま通る。守る）', async () => {
  await withTempDir(async (dir) => {
    const file = path.join(dir, 'plain.md');
    await writeFile(file, 'abcdefghij');
    assert.equal(await nodeReadOnlyFs.readHead(file, 262_145), 'abcdefghij');
    assert.equal(await nodeReadOnlyFs.readHead(file, 4), 'abcd');
  });
});
