// ReplyStore の実装（D0079・AC-52〜56。infra/fsReplies.ts）：いまの work_dir の中の実行のフォルダ（直下か <work_dir>/<パイプ名>/）の reply.json 1 つだけを、
// 排他で新しく作る。すでに有れば断り、リンクを辿らず、一時ファイルを作らない。fsPipes.ts・fsVersions.ts と同じ考え方（書き込みの口を絞る）。
// 実物は一時フォルダ（os.tmpdir() の下。終わったら消す）。リンクを作れない環境は、飛ばしたことが分かる形（t.skip）にする。
// 書く途中の失敗は、失敗する偽の open を口の 2 つ目の引数 { open } に渡して確かめる（本物の open で作ったファイルに、書く操作だけ失敗するハンドルを返す）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { lstat, mkdir, open, readFile, readdir, realpath, symlink, writeFile } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { createFsReplyStore } from './fsReplies.ts';
import type { ReplyText } from '../domain/replyFile.ts';
import { withoutComments } from '../test/sourceText.ts';
import { withTempDir } from '../test/tempDir.ts';

const TEXT = '{"version":1,"stage":"requirements","id":"a1b2c3d4e5","action":"approve"}' as ReplyText;
const asText = (s: string): ReplyText => s as ReplyText;

/** base/work（work_dir）と base/outside（外のフォルダ）を作る。work には state.json（直下）と pipe-a/state.json（パイプ）と archive/20261016-090000/ を置く */
async function setup(base: string): Promise<{ work: string; outside: string }> {
  const work = path.join(base, 'work');
  const outside = path.join(base, 'outside');
  await mkdir(path.join(work, 'pipe-a'), { recursive: true });
  await mkdir(path.join(work, 'archive', '20261016-090000'), { recursive: true });
  await mkdir(outside);
  await writeFile(path.join(work, 'state.json'), '{}');
  await writeFile(path.join(work, 'pipe-a', 'state.json'), '{}');
  await writeFile(path.join(work, 'archive', '20261016-090000', 'state.json'), '{}');
  return { work, outside };
}

/** dir の下の全部（フォルダは末尾に /）。リンクは辿らず 1 件。並べ替えて返す */
async function tree(dir: string, rel = ''): Promise<string[]> {
  const out: string[] = [];
  for (const e of await readdir(path.join(dir, rel), { withFileTypes: true })) {
    const r = rel === '' ? e.name : `${rel}/${e.name}`;
    out.push(e.isDirectory() ? `${r}/` : r);
    if (e.isDirectory()) out.push(...(await tree(dir, r)));
  }
  return out.sort();
}

const skipLinks = (t: { skip: (reason: string) => void }, e: unknown): void => t.skip(`シンボリックリンクを作れない環境（${String((e as { code?: unknown }).code)}）`);

// ---- AC-52：新しく作る ----

test('D0079-AC-52: 直下の実行のフォルダに reply.json が新しく作られ、渡した文字がそのまま（一字違わず）入る。増えるのはそのファイル 1 つだけ（一時ファイルは作らない）', async () => {
  await withTempDir(async (base) => {
    const { work } = await setup(base);
    const before = await tree(base);
    const result = await createFsReplyStore(work).create('', TEXT);
    assert.deepEqual(result, { ok: true });
    assert.equal(await readFile(path.join(work, 'reply.json'), 'utf8'), TEXT);
    assert.deepEqual(await tree(base), [...before, 'work/reply.json'].sort());
  });
});

test('D0079-AC-52: パイプのフォルダ（<work_dir>/<パイプ名>/）にも reply.json が新しく作られ、そこに 1 つ増えるだけ', async () => {
  await withTempDir(async (base) => {
    const { work } = await setup(base);
    const before = await tree(base);
    assert.deepEqual(await createFsReplyStore(work).create('pipe-a', TEXT), { ok: true });
    assert.equal(await readFile(path.join(work, 'pipe-a', 'reply.json'), 'utf8'), TEXT);
    assert.deepEqual(await tree(base), [...before, 'work/pipe-a/reply.json'].sort());
    assert.equal(await lstat(path.join(work, 'reply.json')).then(() => true, () => false), false, '直下には作らない');
  });
});

test('D0079-AC-52: 日本語・絵文字・改行を含む文字も、UTF-8 のバイト列がそのまま入る（変換・末尾の改行の付け足しをしない）', async () => {
  await withTempDir(async (base) => {
    const { work } = await setup(base);
    const text = asText('{"version":1,"stage":"design","id":"a1b2c3d4e5","action":"revise","feedback":"直す😀\\n次"}');
    assert.deepEqual(await createFsReplyStore(work).create('', text), { ok: true });
    const raw = await readFile(path.join(work, 'reply.json'));
    assert.equal(Buffer.compare(raw, Buffer.from(text, 'utf8')), 0);
  });
});

test('D0079-AC-52: 開く操作は 1 回だけ、<実行のフォルダ>/reply.json を排他（wx）で開く', async () => {
  await withTempDir(async (base) => {
    const { work } = await setup(base);
    const calls: { file: string; flags: unknown }[] = [];
    const spy = (async (file: string, flags?: unknown) => {
      calls.push({ file: String(file), flags });
      return open(file, flags as string);
    }) as unknown as typeof open;
    const store = (createFsReplyStore as unknown as (root: string, deps: { open: typeof open }) => ReturnType<typeof createFsReplyStore>)(work, { open: spy });
    assert.deepEqual(await store.create('pipe-a', TEXT), { ok: true });
    assert.equal(calls.length, 1);
    assert.equal(path.basename(calls[0]!.file), 'reply.json');
    assert.equal(await realpath(path.dirname(calls[0]!.file)), await realpath(path.join(work, 'pipe-a')));
    assert.equal(calls[0]!.flags, 'wx');
  });
});

test('D0079-AC-52: 大きさの上限は 16384 バイト（文字数でなくバイト数）：ちょうどは書け、1 バイト超えると bad_text で何も作らない', async () => {
  await withTempDir(async (base) => {
    const { work } = await setup(base);
    const before = await tree(base);
    const store = createFsReplyStore(work);
    assert.deepEqual(await store.create('', asText('a'.repeat(16385))), { ok: false, reason: 'bad_text' });
    assert.deepEqual(await store.create('', asText('あ'.repeat(5462))), { ok: false, reason: 'bad_text' }, '16386 バイト');
    assert.deepEqual(await tree(base), before, '何も作らない');
    assert.deepEqual(await store.create('', asText('a'.repeat(16384))), { ok: true });
  });
});

// ---- AC-53：すでにあるものは断る ----

test('D0079-AC-53: すでに reply.json（通常のファイル）があるときは exists で断り、中身を変えない。二度送ると 2 回目は断る', async () => {
  await withTempDir(async (base) => {
    const { work } = await setup(base);
    await writeFile(path.join(work, 'reply.json'), 'OLD');
    const store = createFsReplyStore(work);
    assert.deepEqual(await store.create('', TEXT), { ok: false, reason: 'exists' });
    assert.equal(await readFile(path.join(work, 'reply.json'), 'utf8'), 'OLD');
    assert.deepEqual(await store.create('pipe-a', TEXT), { ok: true });
    assert.deepEqual(await store.create('pipe-a', asText('{"version":1,"stage":"x","id":"a1b2c3d4e5","action":"quit"}')), { ok: false, reason: 'exists' });
    assert.equal(await readFile(path.join(work, 'pipe-a', 'reply.json'), 'utf8'), TEXT, '1 回目の中身のまま');
  });
});

test('D0079-AC-53: reply.json がフォルダのときは exists で断り、フォルダのまま変えない', async () => {
  await withTempDir(async (base) => {
    const { work } = await setup(base);
    await mkdir(path.join(work, 'reply.json'));
    const before = await tree(base);
    assert.deepEqual(await createFsReplyStore(work).create('', TEXT), { ok: false, reason: 'exists' });
    assert.deepEqual(await tree(base), before);
    assert.equal((await lstat(path.join(work, 'reply.json'))).isDirectory(), true);
  });
});

test('D0079-AC-53: reply.json がリンク（通常のファイルへ）のときは exists で断り、リンクのまま変えず、リンク先の中身も変えない', async (t) => {
  await withTempDir(async (base) => {
    const { work, outside } = await setup(base);
    await writeFile(path.join(outside, 'target.json'), 'TARGET');
    try {
      await symlink(path.join(outside, 'target.json'), path.join(work, 'reply.json'), 'file');
    } catch (e) {
      skipLinks(t, e);
      return;
    }
    assert.deepEqual(await createFsReplyStore(work).create('', TEXT), { ok: false, reason: 'exists' });
    assert.equal((await lstat(path.join(work, 'reply.json'))).isSymbolicLink(), true);
    assert.equal(await readFile(path.join(outside, 'target.json'), 'utf8'), 'TARGET');
  });
});

// ---- AC-54：すり抜けの道を塞ぐ ----

const BAD_RUNS: readonly (readonly [string, string])[] = [
  ['..', '..'],
  ['../x', '../x'],
  ['../outside', '../outside'],
  ['絶対パス（POSIX）', '/etc'],
  ['絶対パス（Windows）', 'C:\\Windows'],
  ['絶対パス（UNC）', '\\\\server\\share'],
  ['2 段（a/b）', 'a/b'],
  ['2 段（pipe-a/x）', 'pipe-a/x'],
  ['2 段（Windows の区切り）', 'pipe-a\\x'],
  ['末尾の区切り', 'pipe-a/'],
  ['先頭の区切り', '/pipe-a'],
  ['archive', 'archive'],
  ['archive/<日時>', 'archive/20261016-090000'],
  ['archive の日時だけ', '20261016-090000/..'],
  ['logs', 'logs'],
  ['. で始まる名前', '.hidden'],
  ['.', '.'],
  ['.git', '.git'],
  ['x/..', 'x/..'],
  ['大文字を含む名前', 'PipeA'],
  ['空白を含む名前', 'pipe a'],
  ['長すぎる名前', 'a'.repeat(101)],
  ['改行を含む名前', 'pipe-a\n'],
  ['NUL を含む名前', 'pipe-a\u0000x'],
  ['URL の形', 'file:///etc'],
  ['空以外の区切りだけ', '/'],
];
for (const [label, runId] of BAD_RUNS) {
  test(`D0079-AC-54: 実行のフォルダの指定が「${label}」のときは、書かず何も作らず bad_run で断る`, async () => {
    await withTempDir(async (base) => {
      const { work } = await setup(base);
      const before = await tree(base);
      assert.deepEqual(await createFsReplyStore(work).create(runId, TEXT), { ok: false, reason: 'bad_run' });
      assert.deepEqual(await tree(base), before);
    });
  });
}

test('D0079-AC-54: 文字でない指定（数・null・undefined・配列・オブジェクト）も bad_run で断り、何も作らない', async () => {
  await withTempDir(async (base) => {
    const { work } = await setup(base);
    const before = await tree(base);
    for (const bad of [1, null, undefined, ['pipe-a'], { id: 'pipe-a' }]) {
      const store = createFsReplyStore(work) as unknown as { create(runId: unknown, text: unknown): Promise<{ ok: boolean; reason?: string }> };
      assert.deepEqual(await store.create(bad, TEXT), { ok: false, reason: 'bad_run' }, JSON.stringify(bad));
    }
    assert.deepEqual(await tree(base), before);
  });
});

test('D0079-AC-54: 検める順は、実行のフォルダの指定が先、文字の大きさが後（指定が悪ければ bad_run）', async () => {
  await withTempDir(async (base) => {
    const { work } = await setup(base);
    assert.deepEqual(await createFsReplyStore(work).create('..', asText('a'.repeat(20000))), { ok: false, reason: 'bad_run' });
  });
});

test('D0079-AC-54: 無いフォルダ・フォルダでない名前（通常のファイル）の指定は、書かず何も作らずに断る（空の形でも断るので、今のまま通る。守る）', async () => {
  await withTempDir(async (base) => {
    const { work } = await setup(base);
    await writeFile(path.join(work, 'plainfile'), 'x');
    const before = await tree(base);
    for (const runId of ['ghost', 'plainfile']) {
      const result = await createFsReplyStore(work).create(runId, TEXT);
      assert.equal(result.ok, false, runId);
    }
    assert.deepEqual(await tree(base), before);
  });
});

test('D0079-AC-54: 口の型に reply.json 以外のファイル名を渡す道が無い：create の引数は実行のフォルダ（runId）と中身（text）の 2 つだけで、ほかの .json・.md の名前を書かない', () => {
  const store = createFsReplyStore('/work/app/docs/pipeline');
  assert.equal(store.create.length, 2, 'create は 2 引数');
  const flow = withoutComments(readFileSync(new URL('../app/replyFlow.ts', import.meta.url), 'utf8'));
  const sig = /\bcreate\(([^)]*)\)\s*:/.exec(flow)?.[1];
  assert.ok(sig !== undefined, 'ReplyStore の create の宣言が読める');
  assert.deepEqual(sig.split(',').map((p) => p.trim().split(':')[0]!.trim()), ['runId', 'text']);
  const source = withoutComments(readFileSync(new URL('./fsReplies.ts', import.meta.url), 'utf8'));
  const names = [...source.matchAll(/['"`]([^'"`\n]*\.(?:json|md|toml|txt|tmp|bak)[^'"`\n]*)['"`]/g)].map((m) => m[1]!);
  assert.ok(source.length > 200 && /\bwx\b|O_EXCL/.test(source), 'fsReplies.ts が実装されている（排他で開く）');
  assert.deepEqual([...new Set(names)].filter((n) => n !== 'reply.json'), [], 'reply.json 以外のファイル名の文字を持たない');
});

// ---- AC-55：リンクを辿らない ----

test('D0079-AC-55: 実行のフォルダが work_dir の外を指すリンクのとき、リンクの先に何も作らず outside で断る', async (t) => {
  await withTempDir(async (base) => {
    const { work, outside } = await setup(base);
    try {
      await symlink(outside, path.join(work, 'pipe-link'), 'dir');
    } catch (e) {
      skipLinks(t, e);
      return;
    }
    const before = await tree(base);
    assert.deepEqual(await createFsReplyStore(work).create('pipe-link', TEXT), { ok: false, reason: 'outside' });
    assert.deepEqual(await readdir(outside), [], '外のフォルダに何も作らない');
    assert.deepEqual(await tree(base), before);
  });
});

test('D0079-AC-55: 実行のフォルダが work_dir の中の別のフォルダを指すリンクのときも、辿らず断る（リンクの先に作らない）（空の形でも断るので、今のまま通る。守る）', async (t) => {
  await withTempDir(async (base) => {
    const { work } = await setup(base);
    try {
      await symlink(path.join(work, 'pipe-a'), path.join(work, 'pipe-link'), 'dir');
    } catch (e) {
      skipLinks(t, e);
      return;
    }
    const before = await tree(base);
    const result = await createFsReplyStore(work).create('pipe-link', TEXT);
    assert.equal(result.ok, false);
    assert.deepEqual(await tree(base), before);
  });
});

test('D0079-AC-55: 返事の場所がダングリングリンク（先が無いリンク）のとき、先に何も作らず exists で断る', async (t) => {
  await withTempDir(async (base) => {
    const { work, outside } = await setup(base);
    try {
      await symlink(path.join(outside, 'not-yet.json'), path.join(work, 'reply.json'), 'file');
    } catch (e) {
      skipLinks(t, e);
      return;
    }
    assert.deepEqual(await createFsReplyStore(work).create('', TEXT), { ok: false, reason: 'exists' });
    assert.deepEqual(await readdir(outside), [], '先に何も作らない');
    assert.equal((await lstat(path.join(work, 'reply.json'))).isSymbolicLink(), true);
  });
});

test('D0079-AC-55: 返事の場所のリンクが work_dir の外の「フォルダ」の中の名前を指していても、何も作らない', async (t) => {
  await withTempDir(async (base) => {
    const { work, outside } = await setup(base);
    try {
      await symlink(path.join(outside, 'sub', 'x.json'), path.join(work, 'pipe-a', 'reply.json'), 'file');
    } catch (e) {
      skipLinks(t, e);
      return;
    }
    assert.deepEqual(await createFsReplyStore(work).create('pipe-a', TEXT), { ok: false, reason: 'exists' });
    assert.deepEqual(await readdir(outside), []);
  });
});

// ---- AC-56：書く途中の失敗 ----

/** open を、本物で作ったファイルに「書く操作だけが半分書いて失敗する」ハンドルを返すものにする */
function failingOpen(failAt: 'open' | 'write'): typeof open {
  return (async (file: string, flags?: unknown) => {
    if (failAt === 'open') throw Object.assign(new Error('EACCES: permission denied'), { code: 'EACCES' });
    const real = await open(file, flags as string);
    return new Proxy(real, {
      get(target, prop) {
        if (prop === 'write' || prop === 'writeFile' || prop === 'appendFile') {
          return async (data: unknown) => {
            await target.writeFile(String(data).slice(0, 10));
            throw Object.assign(new Error('ENOSPC: no space left on device'), { code: 'ENOSPC' });
          };
        }
        const value = Reflect.get(target, prop) as unknown;
        return typeof value === 'function' ? (value as (...args: unknown[]) => unknown).bind(target) : value;
      },
    });
  }) as unknown as typeof open;
}
const storeWith = (work: string, deps: { open: typeof open }): ReturnType<typeof createFsReplyStore> =>
  (createFsReplyStore as unknown as (root: string, d: { open: typeof open }) => ReturnType<typeof createFsReplyStore>)(work, deps);

test('D0079-AC-56: 書く途中で失敗したとき、自分が作った半端な reply.json は残さず failed で断る（直下・パイプ）', async () => {
  await withTempDir(async (base) => {
    const { work } = await setup(base);
    const before = await tree(base);
    const store = storeWith(work, { open: failingOpen('write') });
    assert.deepEqual(await store.create('', TEXT), { ok: false, reason: 'failed' });
    assert.deepEqual(await store.create('pipe-a', TEXT), { ok: false, reason: 'failed' });
    assert.deepEqual(await tree(base), before, '半端なファイルが残らない');
  });
});

test('D0079-AC-56: 失敗したときも、ほかのもの（state.json・ほかのフォルダ・外のフォルダ）は消さず、中身も変えない（空の形では何もしないので、今のまま通る。守る）', async () => {
  await withTempDir(async (base) => {
    const { work, outside } = await setup(base);
    await writeFile(path.join(outside, 'keep.txt'), 'KEEP');
    await writeFile(path.join(work, 'pipe-a', 'state.json'), '{"keep":true}');
    await storeWith(work, { open: failingOpen('write') }).create('pipe-a', TEXT);
    assert.equal(await readFile(path.join(work, 'pipe-a', 'state.json'), 'utf8'), '{"keep":true}');
    assert.equal(await readFile(path.join(outside, 'keep.txt'), 'utf8'), 'KEEP');
    assert.equal(await readFile(path.join(work, 'state.json'), 'utf8'), '{}');
  });
});

test('D0079-AC-56: 開く操作そのものが失敗したとき（権限など）も failed で断り、何も作らない', async () => {
  await withTempDir(async (base) => {
    const { work } = await setup(base);
    const before = await tree(base);
    assert.deepEqual(await storeWith(work, { open: failingOpen('open') }).create('', TEXT), { ok: false, reason: 'failed' });
    assert.deepEqual(await tree(base), before);
  });
});

test('D0079-AC-56: 失敗のあとに、普通の口でもう一度送れる（失敗が半端なファイルを残さないので exists にならない）', async () => {
  await withTempDir(async (base) => {
    const { work } = await setup(base);
    await storeWith(work, { open: failingOpen('write') }).create('', TEXT);
    assert.deepEqual(await createFsReplyStore(work).create('', TEXT), { ok: true });
    assert.equal(await readFile(path.join(work, 'reply.json'), 'utf8'), TEXT);
  });
});
