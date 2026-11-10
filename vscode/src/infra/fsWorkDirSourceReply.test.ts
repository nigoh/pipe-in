// 基盤：返事のファイル（reply.json）が「有るか」と「更新時刻」だけを読む（D0079・AC-50。infra/fsWorkDirSource.ts の readReplyFile）。
// 読み取りの口（ReadOnlyFs）の lstat を 1 回だけ呼ぶ。通常のファイルだけを「有る」に数え（リンク・フォルダは数えない）、中身は読まない。
// 実物は一時フォルダ（test/tempDir.ts）、読んだ道は記録する偽の口（test/recordingFs.ts）、失敗は手で書いた偽の lstat で確かめる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, symlink, utimes, writeFile } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { createFsWorkDirSource, readReplyFile } from './fsWorkDirSource.ts';
import { nodeReadOnlyFs } from './readOnlyFs.ts';
import type { ReadOnlyFs } from './readOnlyFs.ts';
import { withoutComments } from '../test/sourceText.ts';
import { recordingFs } from '../test/recordingFs.ts';
import { withTempDir } from '../test/tempDir.ts';
import { replyState } from '../test/replyFixtures.ts';

const T = Date.UTC(2026, 9, 17, 10, 0, 10);
const FILE = 'reply.json';

async function putReply(dir: string, when: number = T): Promise<string> {
  const file = path.join(dir, FILE);
  await writeFile(file, '{"version":1}');
  await utimes(file, new Date(when), new Date(when));
  return file;
}

const skipLinks = (t: { skip: (reason: string) => void }, e: unknown): void => t.skip(`シンボリックリンクを作れない環境（${String((e as { code?: unknown }).code)}）`);

// ---- 通常のファイル・無い・リンク・フォルダ ----

test('D0079-AC-50: 通常のファイルは「有る」で、更新時刻（ミリ秒）が付く', async () => {
  await withTempDir(async (dir) => {
    await putReply(dir);
    assert.deepEqual(await readReplyFile(dir), { mtimeMs: T });
  });
});

test('D0079-AC-50: 更新時刻は、ファイルを書き換えると読み直した値が変わる（キャッシュしない）', async () => {
  await withTempDir(async (dir) => {
    await putReply(dir, T);
    await putReply(dir, T + 7_000);
    assert.deepEqual(await readReplyFile(dir), { mtimeMs: T + 7_000 });
  });
});

test('D0079-AC-50: 返事のファイルが無い・実行のフォルダが無いときは「無い」（null。例外を出さない）（空の形でも null なので、今のまま通る。守る）', async () => {
  await withTempDir(async (dir) => {
    assert.equal(await readReplyFile(dir), null);
    assert.equal(await readReplyFile(path.join(dir, 'missing')), null);
  });
});

test('D0079-AC-50: reply.json がフォルダのときは「有る」に数えない（空の形でも null なので、今のまま通る。守る）', async () => {
  await withTempDir(async (dir) => {
    await mkdir(path.join(dir, FILE));
    assert.equal(await readReplyFile(dir), null);
  });
});

test('D0079-AC-50: reply.json がリンク（通常のファイルへ・フォルダへ・先が無い）のときは「有る」に数えない（空の形でも null なので、今のまま通る。守る）', async (t) => {
  await withTempDir(async (dir) => {
    await writeFile(path.join(dir, 'real.json'), '{}');
    await mkdir(path.join(dir, 'real-dir'));
    const cases = [['通常のファイルへ', 'real.json', 'file'], ['フォルダへ', 'real-dir', 'dir'], ['先が無い', 'missing.json', 'file']] as const;
    for (const [i, [label, target, type]] of cases.entries()) {
      const run = path.join(dir, `run-${i}`);
      await mkdir(run);
      try {
        await symlink(path.join(dir, target), path.join(run, FILE), type);
      } catch (e) {
        skipLinks(t, e);
        return;
      }
      assert.equal(await readReplyFile(run), null, label);
    }
  });
});

test('D0079-AC-50: 更新時刻が読めない（0・負・NaN・文字）ときは、有るが時刻は null（偽の lstat）', async () => {
  for (const mtimeMs of [0, -5, Number.NaN, '1760000000000', null, undefined]) {
    const fs = fakeLstat(() => ({ isFile: () => true, mtimeMs }));
    assert.deepEqual(await readReplyFile('/work/app', fs), { mtimeMs: null }, String(mtimeMs));
  }
});

test('D0079-AC-50: lstat が失敗したとき（権限・途中で消えた）は「無い」（null。例外を出さない）（空の形でも null なので、今のまま通る。守る）', async () => {
  const fs = fakeLstat(() => {
    throw Object.assign(new Error('EACCES'), { code: 'EACCES' });
  });
  assert.equal(await readReplyFile('/work/app', fs), null);
});

/** lstat だけ差し替えた偽の口。ほかの口は呼ばれたら落とす */
function fakeLstat(make: (file: string) => unknown): ReadOnlyFs {
  const refuse = (name: string) => () => {
    throw new Error(`${name} を呼んではいけない`);
  };
  return {
    readFile: refuse('readFile'),
    readdir: refuse('readdir'),
    stat: refuse('stat'),
    realpath: refuse('realpath'),
    readHead: refuse('readHead'),
    lstat: (async (file: unknown) => make(String(file))) as unknown as ReadOnlyFs['lstat'],
  } as unknown as ReadOnlyFs;
}

// ---- 読んだ道：lstat を 1 回だけ ----

test('D0079-AC-50: 読み取りの口の lstat を、<実行のフォルダ>/reply.json に 1 回だけ呼び、ほかの口（readFile・readHead・stat・readdir・realpath）は呼ばない', async () => {
  await withTempDir(async (dir) => {
    for (const make of [async () => undefined, () => putReply(dir)]) {
      await make();
      const { fs, calls } = recordingFs();
      await readReplyFile(dir, fs);
      assert.deepEqual(calls, [{ op: 'lstat', path: path.join(dir, FILE) }]);
    }
  });
});

test('D0079-AC-50: 偽の lstat（中身を読む口は呼ぶと落ちる）でも、有る・更新時刻が分かる：中身を読まない', async () => {
  const fs = fakeLstat(() => ({ isFile: () => true, mtimeMs: T }));
  assert.deepEqual(await readReplyFile('/work/app', fs), { mtimeMs: T });
  const dirFs = fakeLstat(() => ({ isFile: () => false, mtimeMs: T }));
  assert.equal(await readReplyFile('/work/app', dirFs), null);
});

// ---- ソースの文字：読み取りの道に中身を読む呼び出しが無い ----

const SOURCE = readFileSync(new URL('./fsWorkDirSource.ts', import.meta.url), 'utf8');

/** 行頭の function name(…) から、行頭の } まで（戻り値の型に { } を書いても読める）。無ければ null */
function topLevel(code: string, name: string): string | null {
  const text = `\n${code}`;
  const head = new RegExp(`\\n(?:export )?(?:async )?function ${name}\\b`).exec(text);
  if (head === null) return null;
  const end = text.indexOf('\n}', head.index + 1);
  return end === -1 ? null : text.slice(head.index, end + 2);
}

/** readReplyFile の本体に、中身を読む・開く・一覧する呼び出しがあるか（lstat 以外の口の呼び出し） */
function contentReaders(source: string): string[] {
  const body = topLevel(withoutComments(source), 'readReplyFile');
  if (body === null) return ['readReplyFile の宣言が読めない'];
  const found = [...body.matchAll(/\b(readFile|readFileSync|readHead|readdir|stat|fstat|realpath|open|openSync|createReadStream|read)\s*\(/g)].map((m) => m[1]!);
  if (!/\blstat\s*\(/.test(body)) found.push('lstat を呼んでいない');
  return found;
}

test('D0079-AC-50: readReplyFile の道に readFile・readHead・open などの中身を読む呼び出しが無く、lstat を呼んでいる（ソースの文字）', () => {
  assert.deepEqual(contentReaders(SOURCE), []);
});

test('D0079-AC-50: 検査そのもの：中身を読む呼び出しを見つけ、lstat だけの本体は見逃す（今のまま通る。守る）', () => {
  const lstatOnly = 'export async function readReplyFile(dir: string, fs: ReadOnlyFs = nodeReadOnlyFs) {\n  const info = await fs.lstat(path.join(dir, "reply.json"));\n  return info.isFile() ? { mtimeMs: 1 } : null;\n}';
  assert.deepEqual(contentReaders(lstatOnly), []);
  const reads = lstatOnly.replace('const info', 'await fs.readFile(path.join(dir, "reply.json"), "utf8");\n  const info');
  assert.deepEqual(contentReaders(reads), ['readFile']);
  const opens = lstatOnly.replace('const info', 'const h = await open(path.join(dir, "reply.json"), "r");\n  const info');
  assert.deepEqual(contentReaders(opens), ['open']);
  const stats = lstatOnly.replace('fs.lstat(', 'fs.stat(');
  assert.deepEqual(contentReaders(stats), ['stat', 'lstat を呼んでいない']);
  assert.deepEqual(contentReaders('// readReplyFile はまだ\nconst x = 1;'), ['readReplyFile の宣言が読めない']);
});

// ---- 選んだ実行の写しに入る ----

test('D0079-AC-50: createFsWorkDirSource().read() は、返事のファイルが有れば写しの replyFile に { mtimeMs } を入れ、無ければ null（か項目なし）', async () => {
  await withTempDir(async (dir) => {
    await writeFile(path.join(dir, 'state.json'), replyState());
    const none = (await createFsWorkDirSource(dir, 'docs/pipeline').read()) as unknown as { replyFile?: unknown };
    assert.equal(none.replyFile ?? null, null);
    await putReply(dir);
    const some = (await createFsWorkDirSource(dir, 'docs/pipeline').read()) as unknown as { replyFile?: unknown };
    assert.deepEqual(some.replyFile, { mtimeMs: T });
  });
});

test('D0079-AC-50: 写しを読む道で、reply.json は lstat だけ（中身を読む readFile・readHead・stat の対象にならない）', async () => {
  await withTempDir(async (dir) => {
    await writeFile(path.join(dir, 'state.json'), replyState());
    await putReply(dir);
    const { fs, calls } = recordingFs();
    await createFsWorkDirSource(dir, 'docs/pipeline', { fs }).read();
    const mine = calls.filter((c) => path.basename(c.path) === FILE);
    assert.deepEqual(mine, [{ op: 'lstat', path: path.join(dir, FILE) }]);
  });
});

test('D0079-AC-50: archive/ の前の実行（previous）と別の worktree（other）の写しは、reply.json を lstat もせず、写しに replyFile を入れない（今のまま通る。守る）', async () => {
  await withTempDir(async (dir) => {
    await writeFile(path.join(dir, 'state.json'), replyState());
    await putReply(dir);
    for (const options of [{ previous: true }, { other: true }] as const) {
      const { fs, calls } = recordingFs();
      const snap = await (createFsWorkDirSource as unknown as (a: string, b: string, o: object) => { read(): Promise<object> })(dir, 'docs/pipeline', { ...options, fs }).read();
      assert.deepEqual(calls.filter((c) => path.basename(c.path) === FILE), [], JSON.stringify(options));
      assert.equal(Object.hasOwn(snap, 'replyFile'), false, JSON.stringify(options));
    }
  });
});

test('D0079-AC-50: 古い読み方（reply.json の無い実行の写し）は今までと同じ項目のまま：state.json・stageLogs・artifacts（今のまま通る。守る）', async () => {
  await withTempDir(async (dir) => {
    await writeFile(path.join(dir, 'state.json'), replyState({ mark: null }));
    const snap = await createFsWorkDirSource(dir, 'docs/pipeline', { fs: nodeReadOnlyFs }).read();
    assert.equal(snap.workDir, 'docs/pipeline');
    assert.equal(snap.stateJson, replyState({ mark: null }));
    assert.deepEqual(snap.stageLogs, []);
  });
});
