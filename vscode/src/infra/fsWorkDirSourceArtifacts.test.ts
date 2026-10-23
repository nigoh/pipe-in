// 基盤：成果物の読み（D0025・イシュー #49）。lstat 1 回（通常のファイルか・更新時刻）＋ readHead 1 回（上限 262,145 バイト）で読み、
// 文字の境目で 262,144 バイトに切り、{ text, mtimeMs, cut } を写しに入れる。合計の読み上限（4 MiB）と、symlink・フォルダは読まない、を確かめる。
// 偽の口（makeFs）はこのファイルの頭に手で書く（モックのライブラリは使わない。recordingFs は本物に渡して記録するだけで、大きさを偽れない）。
// 本物の一時フォルダ（withTempDir）でも確かめる：本物の readHead で文字の途中の切れ目を見るため。
// 新しい部品（cutToBytes・ARTIFACT_MAX_BYTES・ARTIFACT_TOTAL_MAX_BYTES・options.fs）は、テストの中で読み込む・型を緩めて渡す
// （テスト先行のとき、まだ無い部品が「関数ではない」「値が undefined」で落ちるようにしたため）。
// テスト先行のときから通っていたテスト（赤ではなく、守り続けるために置く）は、名前の末尾に「（今のまま通る。守る）」と書いた。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { mkdir, readdir, symlink, utimes, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createFsRunsSource, createFsWorkDirSource, listPlaceRuns } from './fsWorkDirSource.ts';
import { nodeReadOnlyFs } from './readOnlyFs.ts';
import type { ReadOnlyFs } from './readOnlyFs.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { WorkDirSnapshot } from '../domain/pipelineView.ts';
import { assistantText, logText, promptLine, stageRunEntry, stateJson } from '../test/fixtures.ts';
import { makeRepo } from '../test/gitFixtures.ts';
import { recordingFs } from '../test/recordingFs.ts';
import { findLimitLiterals, findReadHeadAlloc, withoutComments } from '../test/sourceText.ts';
import { withTempDir } from '../test/tempDir.ts';

// ---- 型（実装の前でも後でも通るように、このファイルの中で緩く書く） ----

interface Item {
  text: string;
  mtimeMs?: number | null;
  cut?: boolean;
}
interface Snap {
  workDir: string;
  stateJson: string | null;
  stageLogs: { fileName: string; text: string; mtimeMs?: number | null }[];
  artifacts: Record<string, unknown>;
  previous?: boolean;
}
type CreateSource = (dir: string, display: string, options?: { previous?: boolean; fs?: ReadOnlyFs }) => { read(): Promise<Snap> };
/** テスト先行のとき options.fs はまだ型に無かったので、型を緩めて渡す */
const createSource = createFsWorkDirSource as unknown as CreateSource;

const fsw = async (): Promise<{ cutToBytes: (text: string, maxBytes: number) => { text: string; cut: boolean } }> =>
  (await import('./fsWorkDirSource.ts')) as unknown as { cutToBytes: (text: string, maxBytes: number) => { text: string; cut: boolean } };
const limits = async (): Promise<{ ARTIFACT_MAX_BYTES: unknown; ARTIFACT_TOTAL_MAX_BYTES: unknown }> =>
  (await import('../domain/artifacts.ts')) as unknown as { ARTIFACT_MAX_BYTES: unknown; ARTIFACT_TOTAL_MAX_BYTES: unknown };

const MAX = 262_144;
const HEAD = MAX + 1;
const TOTAL = 4_194_304;
const DEV_NAMES = ['00_input.md', '01_requirements.md', '02_design.md', '03_red_tests.md', '04_implementation.md', '05_test_report.md', '99_summary.md'];

/** 写しの 1 項目。オブジェクトでなければ失敗（旧形の文字のままだと、ここで落ちる） */
function itemOf(snap: Snap, name: string): Item {
  const value = snap.artifacts[name];
  assert.ok(typeof value === 'object' && value !== null, `${name} が { text, mtimeMs, cut } のオブジェクトで写しにある（いまは ${typeof value}）`);
  return value as Item;
}
const hasItem = (snap: Snap, name: string): boolean => Object.hasOwn(snap.artifacts, name);
const bytes = (text: string): number => Buffer.byteLength(text, 'utf8');
/** 写しから図の状態を作る（型は緩く渡す） */
const viewOf = (snap: Snap) => buildPipelineView(snap as unknown as WorkDirSnapshot);

// ---- 偽の口（手で書く）：ReadOnlyFs の 6 つの形を返し、呼びを記録する ----

const WORK = path.resolve('/virtual/pipe-in-fake-work');
const at = (rel: string): string => path.join(WORK, rel);

interface FileSpec {
  /** lstat の isFile()。既定 true */
  isFile?: boolean;
  /** lstat の isSymbolicLink()。symlink のつもりのとき */
  link?: boolean;
  /** lstat・stat が返す大きさ。既定は text のバイト数 */
  size?: number;
  /** lstat が返す更新時刻。項目ごと無ければ既定の正しい値。undefined を渡せば undefined を返す */
  mtimeMs?: unknown;
  /** stat が返す更新時刻（段のログ用。成果物では呼んではいけない）。無ければ mtimeMs と同じ */
  statMtimeMs?: unknown;
  /** ファイルの中身。readHead は先頭の maxBytes バイトを UTF-8 で文字にして返す（本物と同じく、文字の途中で切れると U+FFFD になる） */
  text?: string;
  /** lstat は通り、readHead が投げる（権限が無い・lstat と開くあいだに消えた） */
  failRead?: boolean;
  /** lstat が投げる */
  failLstat?: boolean;
}
type Op = 'readFile' | 'readdir' | 'stat' | 'lstat' | 'realpath' | 'readHead';
interface Call {
  op: Op;
  path: string;
  maxBytes?: number;
}

const GOOD_MTIME = Date.UTC(2026, 9, 17, 1, 5, 0);

function enoent(file: string): Error {
  return Object.assign(new Error(`ENOENT: ${file}`), { code: 'ENOENT' });
}

/** files のキーは WORK からの相対パス（'state.json'・'logs/01_requirements.jsonl'・'01_requirements.md'） */
function makeFs(files: Readonly<Record<string, FileSpec>>): { fs: ReadOnlyFs; calls: Call[]; paths: (op: Op) => string[]; count: (op: Op, rel: string) => number } {
  const specs = new Map<string, FileSpec>(Object.entries(files).map(([rel, spec]) => [at(rel), spec]));
  const calls: Call[] = [];
  const specOf = (file: unknown): FileSpec => {
    const spec = specs.get(String(file));
    if (spec === undefined) throw enoent(String(file));
    return spec;
  };
  const isRecordFile = (file: string): boolean => file === at('state.json') || path.dirname(file) === at('logs');
  const mtimeOf = (spec: FileSpec): unknown => (Object.hasOwn(spec, 'mtimeMs') ? spec.mtimeMs : GOOD_MTIME);
  const sizeOf = (spec: FileSpec): number => spec.size ?? bytes(spec.text ?? '');
  const fs = {
    async readFile(file: unknown): Promise<string> {
      calls.push({ op: 'readFile', path: String(file) });
      const spec = specOf(file);
      // 成果物の読みで readFile を呼んではいけない（state.json と段のログだけ返す）
      if (!isRecordFile(String(file))) throw new Error(`成果物の readFile は呼んではいけない：${String(file)}`);
      return spec.text ?? '';
    },
    async readdir(dir: unknown): Promise<string[]> {
      calls.push({ op: 'readdir', path: String(dir) });
      if (String(dir) !== at('logs')) throw enoent(String(dir));
      const names = [...specs.keys()].filter((p) => path.dirname(p) === at('logs')).map((p) => path.basename(p));
      if (names.length === 0) throw enoent(String(dir));
      return names;
    },
    async stat(file: unknown) {
      calls.push({ op: 'stat', path: String(file) });
      const spec = specOf(file);
      const mtimeMs = Object.hasOwn(spec, 'statMtimeMs') ? spec.statMtimeMs : mtimeOf(spec);
      return { isFile: () => spec.isFile ?? true, isDirectory: () => false, size: sizeOf(spec), mtimeMs };
    },
    async lstat(file: unknown) {
      calls.push({ op: 'lstat', path: String(file) });
      const spec = specOf(file);
      if (spec.failLstat === true) throw Object.assign(new Error('EACCES'), { code: 'EACCES' });
      return {
        isFile: () => spec.isFile ?? true,
        isDirectory: () => false,
        isSymbolicLink: () => spec.link === true,
        size: sizeOf(spec),
        mtimeMs: mtimeOf(spec),
      };
    },
    async realpath(file: unknown): Promise<string> {
      calls.push({ op: 'realpath', path: String(file) });
      throw enoent(String(file));
    },
    async readHead(file: string, maxBytes: number): Promise<string> {
      calls.push({ op: 'readHead', path: String(file), maxBytes });
      const spec = specOf(file);
      if (spec.failRead === true) throw Object.assign(new Error('EACCES'), { code: 'EACCES' });
      return Buffer.from(spec.text ?? '', 'utf8').subarray(0, Math.max(0, Math.floor(maxBytes))).toString('utf8');
    },
  };
  return {
    fs: fs as unknown as ReadOnlyFs,
    calls,
    paths: (op) => calls.filter((c) => c.op === op).map((c) => c.path),
    count: (op, rel) => calls.filter((c) => c.op === op && c.path === at(rel)).length,
  };
}

/** 偽の口で WORK を読む。state は state.json の中身（省けば無い＝開発フローの 7 つ） */
async function readFake(files: Record<string, FileSpec>, state?: string): Promise<{ snap: Snap; rec: ReturnType<typeof makeFs> }> {
  const all: Record<string, FileSpec> = state === undefined ? files : { ...files, 'state.json': { text: state } };
  const rec = makeFs(all);
  return { snap: await createSource(WORK, 'docs/pipeline', { fs: rec.fs }).read(), rec };
}

/** 段 s0, s1, … が output を順に持つパイプの state.json */
const pipeState = (outputs: readonly string[]): string =>
  stateJson({ pipe: 'p', stages: outputs.map((output, i) => ({ name: `s${i}`, label: `段${i}`, output, review: false })) });

// ---- 上限の定数 ----

test('D0025-AC-42: 1 つの上限 ARTIFACT_MAX_BYTES は 262,144（256 KiB）', async () => {
  assert.equal((await limits()).ARTIFACT_MAX_BYTES, MAX);
});

test('D0025-AC-37: 合計の読み上限 ARTIFACT_TOTAL_MAX_BYTES は 4,194,304（4 MiB）', async () => {
  assert.equal((await limits()).ARTIFACT_TOTAL_MAX_BYTES, TOTAL);
});

// ---- AC-42：読む大きさ ----

test('D0025-AC-42: 262,144 バイトちょうどは全部を読み、切れた印は付かない。頼む上限は 262,145 バイト', async () => {
  const text = 'a'.repeat(MAX);
  const { snap, rec } = await readFake({ '01_requirements.md': { text } });
  const item = itemOf(snap, '01_requirements.md');
  assert.equal(item.text, text);
  assert.equal(item.cut === true, false);
  assert.deepEqual(rec.calls.filter((c) => c.op === 'readHead').map((c) => c.maxBytes), [HEAD]);
});

test('D0025-AC-42: 262,145 バイトは先頭の 262,144 バイトまでを読み、切れた印が付く', async () => {
  const { snap } = await readFake({ '01_requirements.md': { text: 'a'.repeat(HEAD) } });
  const item = itemOf(snap, '01_requirements.md');
  assert.equal(item.text, 'a'.repeat(MAX));
  assert.equal(item.cut, true);
});

test('D0025-AC-42: ずっと大きいファイル（100 万バイト）も、頼む上限は 262,145 バイトのまま。先頭の 262,144 バイトまでを読み、切れた印が付く', async () => {
  const text = `${'x'.repeat(10)}${'y'.repeat(1_000_000)}`;
  const { snap, rec } = await readFake({ '01_requirements.md': { text } });
  const item = itemOf(snap, '01_requirements.md');
  assert.equal(item.text, text.slice(0, MAX));
  assert.equal(item.cut, true);
  assert.deepEqual(rec.calls.filter((c) => c.op === 'readHead').map((c) => c.maxBytes), [HEAD]);
});

test('D0025-AC-42: 切れたかどうかは lstat の大きさでなく、読んだ文字の UTF-8 の長さで決める（大きさ 10 と言いながら 262,145 バイト返せば切れ、大きさ 300 MiB と言いながら短ければ切れない）', async () => {
  const lies = await readFake({ '01_requirements.md': { text: 'a'.repeat(HEAD), size: 10 } });
  assert.equal(itemOf(lies.snap, '01_requirements.md').cut, true);
  assert.equal(itemOf(lies.snap, '01_requirements.md').text.length, MAX);
  const huge = await readFake({ '01_requirements.md': { text: '短い', size: 300 * 1024 * 1024 } });
  assert.equal(itemOf(huge.snap, '01_requirements.md').text, '短い');
  assert.equal(itemOf(huge.snap, '01_requirements.md').cut === true, false);
});

test('D0025-AC-42: UTF-8 として読めないバイト（Shift_JIS の 0x82 0xA0 の繰り返し）の約 100 KB は、上限より小さいのに切れた印が付き、出す文字は 262,144 バイト以下。例外は出ない', async () => {
  await withTempDir(async (dir) => {
    await writeFile(path.join(dir, '01_requirements.md'), Buffer.from(Array.from({ length: 100_000 }, (_, i) => (i % 2 === 0 ? 0x82 : 0xa0))));
    const item = itemOf(await createSource(dir, 'docs/pipeline').read(), '01_requirements.md');
    assert.equal(item.cut, true);
    assert.ok(bytes(item.text) <= MAX, `出す文字は ${bytes(item.text)} バイト`);
    assert.ok(item.text.length > 0);
  });
});

test('D0025-AC-42: 本物のファイル 1 つの写しは { text, mtimeMs（utimes で決めた時刻）, cut: false } になる', async () => {
  await withTempDir(async (dir) => {
    const file = path.join(dir, '01_requirements.md');
    await writeFile(file, '要件の本文\n');
    await utimes(file, new Date(GOOD_MTIME), new Date(GOOD_MTIME));
    const snap = await createSource(dir, 'docs/pipeline').read();
    assert.deepEqual(itemOf(snap, '01_requirements.md'), { text: '要件の本文\n', mtimeMs: GOOD_MTIME, cut: false });
  });
});

test('D0025-AC-42: 本物のファイル 262,145 バイトは、本物の readHead でも先頭の 262,144 バイトまでで切れた印が付く', async () => {
  await withTempDir(async (dir) => {
    await writeFile(path.join(dir, '01_requirements.md'), 'a'.repeat(HEAD));
    const item = itemOf(await createSource(dir, 'docs/pipeline').read(), '01_requirements.md');
    assert.deepEqual([item.text.length, item.cut], [MAX, true]);
  });
});

// ---- AC-43：読みの呼びを絞る ----

test('D0025-AC-43: lstat・stat が大きさ 300 MiB を返す偽の口でも、成果物 1 つにつき lstat 1 回・readHead 1 回（上限 262,145）で、readFile と stat は 0 回', async () => {
  const files: Record<string, FileSpec> = {};
  for (const name of DEV_NAMES) files[name] = { text: `${name} の中身`, size: 300 * 1024 * 1024 };
  const { snap, rec } = await readFake(files);
  for (const name of DEV_NAMES) {
    assert.equal(rec.count('lstat', name), 1, `${name} の lstat`);
    assert.equal(rec.count('readHead', name), 1, `${name} の readHead`);
    assert.equal(rec.count('readFile', name), 0, `${name} の readFile`);
    assert.equal(rec.count('stat', name), 0, `${name} の stat`);
    assert.equal(itemOf(snap, name).text, `${name} の中身`);
  }
  assert.deepEqual(new Set(rec.calls.filter((c) => c.op === 'readHead').map((c) => c.maxBytes)), new Set([HEAD]));
  assert.equal(rec.paths('realpath').length, 0);
});

test('D0025-AC-43: 成果物が無い（lstat が失敗する）ときは readHead を呼ばず、lstat は 1 回だけ', async () => {
  const { snap, rec } = await readFake({ '01_requirements.md': { text: '要件' } });
  assert.equal(rec.count('lstat', '02_design.md'), 1);
  assert.equal(rec.count('readHead', '02_design.md'), 0);
  assert.equal(hasItem(snap, '02_design.md'), false);
});

test('D0025-AC-43: 本物の readHead は、小さいファイル（10 バイト）なら、上限が 262,145 でも中身の 10 文字だけを返す（確保した領域の残りを漏らさない。今のまま通る。守る）', async () => {
  await withTempDir(async (dir) => {
    const file = path.join(dir, 'small.md');
    await writeFile(file, 'abcdefghij');
    assert.equal(await nodeReadOnlyFs.readHead(file, HEAD), 'abcdefghij');
    assert.equal(await nodeReadOnlyFs.readHead(file, 4), 'abcd');
    assert.equal(await nodeReadOnlyFs.readHead(file, 0), '');
  });
});

test('D0025-AC-43: readOnlyFs.ts の readHead は、Buffer.alloc( でなく Buffer.allocUnsafe( で確保し、読んだ分だけ .subarray(0, bytesRead) で返す（一方だけだと、軽くならないか、確保しただけの領域を漏らす。探す関数は STX で確かめる）', () => {
  const source = readFileSync(fileURLToPath(new URL('./readOnlyFs.ts', import.meta.url)), 'utf8');
  assert.deepEqual(findReadHeadAlloc(source), []);
});

// ---- AC-45：上限の数は domain/artifacts.ts の 1 か所だけ（画面の部品 view/ は artifactsHtml.test.ts が見る） ----

const SRC = fileURLToPath(new URL('../', import.meta.url));
/** 上限の数の直書きを許すファイルと、その書き方。既存の state.json の読みの上限（STATE_MAX_BYTES。成果物の上限ではない）の 1 行だけ */
const LIMIT_ALLOWED: Readonly<Record<string, readonly string[]>> = { 'infra/fsWorkDirSource.ts': ['4 * 1024 * 1024'] };

test('D0025-AC-45: 上限の数（262144・4194304・256 * 1024・4 * 1024 * 1024 など）を、domain/・infra/・app/ の製品のファイルに直書きしない（上限は domain/artifacts.ts の 1 か所。許すのは infra/fsWorkDirSource.ts の既存の STATE_MAX_BYTES の 1 行だけ）（今のまま通る。守る）', async () => {
  const checked: string[] = [];
  for (const dir of ['domain', 'infra', 'app']) {
    for (const file of (await readdir(path.join(SRC, dir))).filter((f) => f.endsWith('.ts') && !f.endsWith('.test.ts'))) {
      const rel = `${dir}/${file}`;
      if (rel === 'domain/artifacts.ts') continue;
      checked.push(rel);
      assert.deepEqual(findLimitLiterals(readFileSync(path.join(SRC, rel), 'utf8')), LIMIT_ALLOWED[rel] ?? [], `${rel} の上限の数の直書き`);
    }
  }
  for (const must of ['domain/pipelineView.ts', 'infra/fsWorkDirSource.ts', 'infra/readOnlyFs.ts', 'app/runList.ts']) assert.ok(checked.includes(must), `${must} を調べている`);
});

test('D0025-AC-45: 基盤の fsWorkDirSource.ts は、成果物の読む量と合計の上限を、domain/artifacts.ts の定数 ARTIFACT_MAX_BYTES・ARTIFACT_TOTAL_MAX_BYTES から作る（import のほかに、使っている所がある）', () => {
  const code = withoutComments(readFileSync(path.join(SRC, 'infra', 'fsWorkDirSource.ts'), 'utf8'));
  for (const name of ['ARTIFACT_MAX_BYTES', 'ARTIFACT_TOTAL_MAX_BYTES']) {
    const uses = code.match(new RegExp(`\\b${name}\\b`, 'g')) ?? [];
    assert.ok(uses.length >= 2, `${name} を import して使っている（コメントを除いて ${uses.length} 回出る）`);
  }
});

// ---- AC-44：切れ目が文字の途中のとき ----

const CUT_PATTERNS: readonly (readonly [string, string, string])[] = [
  ['『あ』（3 バイト）の繰り返し（切れ目が文字の途中になる）', 'あ'.repeat(100_000), 'あ'.repeat(87_381)],
  ['先頭に ASCII を 1 文字付けた『é』（2 バイト）の繰り返し', `a${'é'.repeat(200_000)}`, `a${'é'.repeat(131_071)}`],
  ['先頭に ASCII を 1 文字付けた『😀』（4 バイト）の繰り返し', `a${'😀'.repeat(100_000)}`, `a${'😀'.repeat(65_535)}`],
];

for (const [label, content, expected] of CUT_PATTERNS) {
  test(`D0025-AC-44: 本物のファイル：${label}は、末尾に U+FFFD が出ず、出す文字が 262,144 バイト以下で、文字の境目までをそのまま出す`, async () => {
    await withTempDir(async (dir) => {
      await writeFile(path.join(dir, '01_requirements.md'), content);
      const item = itemOf(await createSource(dir, 'docs/pipeline').read(), '01_requirements.md');
      assert.equal(item.cut, true);
      assert.equal(item.text.endsWith('\uFFFD'), false, '末尾に U+FFFD が無い');
      assert.ok(bytes(item.text) <= MAX, `${bytes(item.text)} バイト`);
      assert.equal(item.text, expected);
    });
  });

  test(`D0025-AC-44: 偽の口（文字にして返す readHead）：${label}も同じ結果`, async () => {
    const { snap } = await readFake({ '01_requirements.md': { text: content } });
    const item = itemOf(snap, '01_requirements.md');
    assert.deepEqual([item.text === expected, item.cut], [true, true]);
  });
}

test('D0025-AC-44: 切れ目が文字の境目に合うとき（ASCII の 262,145 文字）は、1 文字も落とさず 262,144 文字を出す', async () => {
  const { snap } = await readFake({ '01_requirements.md': { text: 'a'.repeat(HEAD) } });
  const item = itemOf(snap, '01_requirements.md');
  assert.equal(item.text, 'a'.repeat(MAX));
  assert.equal(item.cut, true);
});

test('D0025-AC-44: ファイルの中ほどにある本物の U+FFFD は変えない（切れた成果物でも、上限以下の成果物でも）', async () => {
  const long = `先頭\uFFFD中ほど${'a'.repeat(300_000)}`;
  const { snap } = await readFake({ '01_requirements.md': { text: long }, '02_design.md': { text: 'ab\uFFFDcd' } });
  const cutItem = itemOf(snap, '01_requirements.md');
  assert.equal(cutItem.cut, true);
  assert.ok(cutItem.text.startsWith('先頭\uFFFD中ほど'));
  assert.equal(itemOf(snap, '02_design.md').text, 'ab\uFFFDcd');
});

test('D0025-AC-44: 上限以下で、末尾が本物の U+FFFD のファイルは、そのまま出す（切れていないので落とさない）', async () => {
  const { snap } = await readFake({ '01_requirements.md': { text: 'ab\uFFFD' } });
  assert.equal(itemOf(snap, '01_requirements.md').text, 'ab\uFFFD');
  assert.equal(itemOf(snap, '01_requirements.md').cut === true, false);
});

test('D0025-AC-44: 偽の readHead が末尾に U+FFFD を返す場合（262,144 バイトの ASCII のあとに 3 バイト文字）も、末尾に U+FFFD は残らない', async () => {
  const text = `${'a'.repeat(MAX)}\uFFFD`;
  const files = { '01_requirements.md': { text } };
  const fake = makeFs(files);
  assert.ok((await fake.fs.readHead(at('01_requirements.md'), HEAD)).endsWith('\uFFFD'), '前提：口は末尾に U+FFFD を返す');
  const { snap } = await readFake(files);
  const item = itemOf(snap, '01_requirements.md');
  assert.equal(item.text, 'a'.repeat(MAX));
  assert.equal(item.cut, true);
});

const CUT_ROWS: readonly (readonly [string, string, number, string, boolean])[] = [
  ['上限以下はそのまま', 'abc', 3, 'abc', false],
  ['1 バイト超えたら切る', 'abcd', 3, 'abc', true],
  ['空の文字', '', 5, '', false],
  ['上限 0 の空でない文字', 'a', 0, '', true],
  ['上限 0 の空の文字', '', 0, '', false],
  ['3 バイト文字の境目で切れる', 'あい', 3, 'あ', true],
  ['3 バイト文字の 1 バイト目の後ろで切れる（文字の途中は戻す）', 'あい', 4, 'あ', true],
  ['3 バイト文字の 2 バイト目の後ろで切れる（文字の途中は戻す）', 'あい', 5, 'あ', true],
  ['ちょうど収まる', 'あい', 6, 'あい', false],
  ['4 バイト文字が 1 つも入らない', '😀', 3, '', true],
  ['4 バイト文字の境目', '😀a', 4, '😀', true],
  ['本物の U+FFFD は上限に収まれば変えない', 'a\uFFFDb', 4, 'a\uFFFD', true],
  ['本物の U+FFFD が上限以下で全部入るときは切れた印なし', 'a\uFFFD', 4, 'a\uFFFD', false],
  ['本物の U+FFFD が上限の途中に掛かるときは、その文字ごと落とす', 'a\uFFFDb', 3, 'a', true],
];

for (const [label, text, max, expected, cut] of CUT_ROWS) {
  test(`D0025-AC-44: cutToBytes：${label}（${JSON.stringify(text)} を ${max} バイトで）`, async () => {
    const { cutToBytes } = await fsw();
    assert.deepEqual(cutToBytes(text, max), { text: expected, cut });
  });
}

// ---- AC-44 の期待そのものの確かめ：切れ目の決め方を、別の書き方（バイト列を見る）で書き直した参照と突き合わせる ----

/** 参照の切り方：UTF-8 のバイト列で maxBytes を超えるなら、maxBytes のところから続きのバイト（10xxxxxx）のあいだ戻って切る */
function referenceCut(text: string, maxBytes: number): { text: string; cut: boolean } {
  const buffer = Buffer.from(text, 'utf8');
  if (buffer.length <= maxBytes) return { text, cut: false };
  let end = maxBytes;
  while (end > 0 && (buffer[end]! & 0xc0) === 0x80) end -= 1;
  return { text: buffer.subarray(0, end).toString('utf8'), cut: true };
}

for (const [label, content, expected] of CUT_PATTERNS) {
  test(`D0025-AC-44: 期待そのものの確かめ：${label}の期待の文字は、本物の readHead（262,145 バイト）の戻りを文字の境目で切った結果と一致する（今のまま通る。守る）`, async () => {
    await withTempDir(async (dir) => {
      const file = path.join(dir, 'content.md');
      await writeFile(file, content);
      const head = await nodeReadOnlyFs.readHead(file, HEAD);
      assert.deepEqual(referenceCut(head, MAX), { text: expected, cut: true });
      assert.ok(bytes(expected) <= MAX);
    });
  });
}

test('D0025-AC-44: 期待そのものの確かめ：cutToBytes の表の期待は、参照の切り方と一致する（今のまま通る。守る）', () => {
  for (const [label, text, max, expected, cut] of CUT_ROWS) {
    assert.deepEqual(referenceCut(text, max), { text: expected, cut }, label);
  }
});

// ---- AC-46：切れた成果物の「あるか」 ----

test('D0025-AC-46: 切れた成果物でも、先頭が空白だけでなければ図の状態で「ある」（text と切れた印が行に届く）', async () => {
  const { snap } = await readFake({ '01_requirements.md': { text: `# 題\n${'a'.repeat(HEAD)}` } });
  const row = viewOf(snap).artifacts.find((a) => a.name === '01_requirements.md') as unknown as { ready: boolean; cut: boolean; text: string };
  assert.deepEqual([row.ready, row.cut, bytes(row.text) <= MAX], [true, true, true]);
});

test('D0025-AC-46: 先頭の 262,144 バイトが空白だけで、そのあとに文字がある成果物は、図の状態で「まだない」', async () => {
  const { snap } = await readFake({ '01_requirements.md': { text: `${' '.repeat(MAX)}あとから文字` } });
  assert.equal(itemOf(snap, '01_requirements.md').text, ' '.repeat(MAX), '読んだ範囲は空白だけ（項目としては写しに入る）');
  const row = viewOf(snap).artifacts.find((a) => a.name === '01_requirements.md');
  assert.equal(row?.ready, false);
});

// ---- AC-47：読む名前は、記録から作った一覧にあるものだけ。その実行のフォルダの中だけ ----

/** すり抜けの道：記録の output が、実行のフォルダの外・隠しファイルを指す名前（1 つずつ並べる。新しい道に気づいたら 1 行足して赤を見てから直す） */
const EVIL_OUTPUTS: readonly (readonly [label: string, name: string])[] = [
  ['親のフォルダへ出る ../x.md', '../x.md'],
  ['絶対パス /etc/passwd', '/etc/passwd'],
  ['ドライブ名つき C:\\x.md', 'C:\\x.md'],
  ['隠しファイル .hidden.md', '.hidden.md'],
];
for (const [label, bad] of EVIL_OUTPUTS) {
  test(`D0025-AC-47: output が ${label} の記録でも、その名前の lstat・readHead は一度も呼ばれず、読むのは一覧にある名前だけ`, async () => {
    const { snap, rec } = await readFake({ 'good.md': { text: '良い中身' }, [bad]: { text: '読んではいけない中身' } }, pipeState([bad, 'good.md']));
    assert.deepEqual(rec.paths('lstat'), [at('00_input.md'), at('good.md'), at('99_summary.md')], '一覧にある 3 つの名前だけ');
    assert.deepEqual(rec.paths('readHead'), [at('good.md')]);
    assert.deepEqual(Object.keys(snap.artifacts), ['good.md']);
    assert.equal(JSON.stringify(snap).includes('読んではいけない中身'), false);
    assert.ok(rec.calls.every((c) => c.path === WORK || c.path.startsWith(WORK + path.sep)), '呼びはすべて work_dir の中');
  });
}

test('D0025-AC-47: 別の worktree の run を選んでも、読むのはその worktree の work_dir の中の一覧にある名前だけ（一覧の外のファイル・worktree の他のファイル・../ の出力は読まない）', async () => {
  await withTempDir(async (base) => {
    const evil = [{ name: 'a', label: '調査', output: '01_survey.md', review: false }, { name: 'evil', label: '外', output: '../secret.md', review: false }];
    const repo = await makeRepo(base, [{ name: 'feat-x', state: stateJson({ pipe: 'diagrams', stages: evil }) }]);
    const root = repo.roots['feat-x']!;
    const work = path.join(root, 'docs', 'pipeline');
    await writeFile(path.join(work, '00_input.md'), 'メモ');
    await writeFile(path.join(work, '01_survey.md'), '調査');
    await writeFile(path.join(root, 'docs', 'secret.md'), '外のファイル');
    const source = createFsRunsSource(repo.mainRoot, path.join(repo.mainRoot, 'docs', 'pipeline'), 'docs/pipeline');
    const wt = (await source.places(true)).places.find((p) => p.key === 'wt.feat-x');
    assert.ok(wt, '別の worktree の場所が見つかる');
    const rec = recordingFs();
    const snap = await createSource(wt.workDirAbs, wt.workDirAbs, { fs: rec.fs }).read();
    assert.deepEqual(rec.paths('lstat').sort(), [path.join(work, '00_input.md'), path.join(work, '01_survey.md'), path.join(work, '99_summary.md')].sort());
    assert.deepEqual(rec.paths('readHead').sort(), [path.join(work, '00_input.md'), path.join(work, '01_survey.md')].sort());
    assert.equal(rec.paths('readFile').some((p) => p.endsWith('00_input.md') || p.endsWith('01_survey.md') || p.endsWith('secret.md') || p.endsWith('other.md')), false);
    assert.ok(rec.calls.every((c) => c.path === work || c.path.startsWith(work + path.sep)), '呼びはすべて別の worktree の work_dir の中');
    assert.equal(itemOf(snap, '01_survey.md').text, '調査');
    assert.equal(JSON.stringify(snap).includes('外のファイル'), false);
  });
});

test('D0025-AC-47: archive/<日時> の run も、その run のフォルダの中だけを同じ読み方で読み、直下の同じ名前のファイルを読まない', async () => {
  await withTempDir(async (dir) => {
    const archived = path.join(dir, 'archive', '20261017-100000');
    await mkdir(archived, { recursive: true });
    await writeFile(path.join(dir, '01_requirements.md'), '直下の要件');
    await writeFile(path.join(archived, '01_requirements.md'), '前の実行の要件');
    const rec = recordingFs();
    const snap = await createSource(archived, 'docs/pipeline', { previous: true, fs: rec.fs }).read();
    assert.equal(itemOf(snap, '01_requirements.md').text, '前の実行の要件');
    assert.deepEqual(rec.paths('readHead'), [path.join(archived, '01_requirements.md')]);
    assert.ok(rec.calls.every((c) => c.path === archived || c.path.startsWith(archived + path.sep)), '呼びはすべて archive/<日時> の中');
    assert.equal(snap.previous, true);
  });
});

test('D0025-AC-47: 実行の一覧の見本の木（直下・パイプ・別の worktree・archive）の各行は、成果物の本文がその run のフォルダのファイルのもの', async () => {
  const pages = (await import('../../scripts/previewPages.ts')) as unknown as {
    buildRunsTree(dest: string): Promise<{ workspace: string }>;
    readRunsView(workspace: string, clock: unknown): Promise<{ key: string; view: { artifacts: { name: string; ready: boolean; text: string }[] } }[]>;
    startOfLiveness(dir: string): Promise<string | null>;
    previewClock(text: string, sec: number): { nowMs: number; localOffsetMin: number };
    WAITING_DIR: string;
    WAITING_SEC: number;
  };
  const { loadRunList } = await import('../app/runList.ts');
  const since = await pages.startOfLiveness(pages.WAITING_DIR);
  assert.ok(since !== null, '確認待ちの見本に待ち始めの時刻がある');
  const clock = pages.previewClock(since, pages.WAITING_SEC);
  await withTempDir(async (dest) => {
    const { workspace } = await pages.buildRunsTree(dest);
    const here = path.join(workspace, 'docs', 'pipeline');
    const list = await loadRunList(createFsRunsSource(workspace, here, 'docs/pipeline'), { showOthers: true, clock });
    const marker = (key: string, name: string): string => `これは ${key} の ${name} です`;
    for (const entry of list.entries) {
      for (const file of (await readdir(entry.dirAbs)).filter((f) => f.endsWith('.md'))) {
        await writeFile(path.join(entry.dirAbs, file), marker(entry.row.key, file));
      }
    }
    const entries = await pages.readRunsView(workspace, clock);
    assert.ok(entries.length >= 6, `行が出る（${entries.length} 行）`);
    let checked = 0;
    for (const e of entries) {
      const ready = e.view.artifacts.filter((a) => a.ready);
      assert.ok(ready.length > 0, `${e.key} に「ある」成果物がある`);
      for (const a of ready) {
        assert.equal(a.text, marker(e.key, a.name), `${e.key} の ${a.name} は、その run のフォルダのファイルの中身`);
        checked += 1;
      }
    }
    assert.ok(checked >= 10, `確かめた成果物は ${checked} 件`);
  });
});

// ---- AC-48：通常のファイルでないものは読まない ----

const NOT_REGULAR: readonly (readonly [string, FileSpec])[] = [
  ['フォルダ', { isFile: false, text: '中身' }],
  ['symlink（リンク先が実行のフォルダの中）', { isFile: false, link: true, text: '中のファイルの中身' }],
  ['symlink（リンク先が実行のフォルダの外）', { isFile: false, link: true, text: '外のファイルの中身' }],
  ['その他（FIFO・ソケットなど。isFile が偽）', { isFile: false, text: '中身' }],
];

for (const [label, spec] of NOT_REGULAR) {
  test(`D0025-AC-48: 成果物が ${label} のとき、読まず（readHead・readFile・stat を呼ばない）、写しに項目が無い。ほかの成果物は読め、例外は出ない`, async () => {
    const { snap, rec } = await readFake({ '00_input.md': { text: 'メモ' }, '01_requirements.md': spec, '02_design.md': { text: '設計' } });
    assert.equal(rec.count('lstat', '01_requirements.md'), 1, '種類を lstat で確かめている');
    assert.equal(rec.count('readHead', '01_requirements.md'), 0);
    assert.equal(rec.count('readFile', '01_requirements.md'), 0);
    assert.equal(rec.count('stat', '01_requirements.md'), 0, 'stat は symlink を辿るので呼ばない');
    assert.equal(hasItem(snap, '01_requirements.md'), false);
    assert.equal(itemOf(snap, '00_input.md').text, 'メモ');
    assert.equal(itemOf(snap, '02_design.md').text, '設計');
    assert.equal(JSON.stringify(snap).includes('中身'), false, 'リンク先・フォルダの中身は写しのどこにも出ない');
  });
}

test('D0025-AC-48: 00_input.md が symlink のときも読まない（図の依頼メモの節は「まだ」になる）。state.json があれば記録なしの表示は出ない', async () => {
  const { snap } = await readFake({ '00_input.md': { isFile: false, link: true, text: '外のメモ' }, '01_requirements.md': { text: '要件' } }, stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }));
  assert.equal(hasItem(snap, '00_input.md'), false);
  const view = viewOf(snap);
  assert.equal(view.nodes.find((n) => n.id === 'input')?.status, 'pending');
  assert.equal(view.noRecords, null);
});

test('D0025-AC-48: lstat は通るのに readHead が投げる成果物（failRead）があっても、read() は投げず、ほかの成果物・state.json・段のログは写しに残り、その成果物だけ項目が無い', async () => {
  const state = stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] });
  const log = logText([promptLine('requirements'), assistantText('書いた')]);
  const { snap, rec } = await readFake(
    {
      '00_input.md': { text: 'メモ' },
      '01_requirements.md': { text: '要件', failRead: true },
      '02_design.md': { text: '設計' },
      'logs/01_requirements.jsonl': { text: log },
    },
    state,
  );
  assert.equal(rec.count('lstat', '01_requirements.md'), 1);
  assert.equal(rec.count('readHead', '01_requirements.md'), 1, 'readHead は呼んだうえで失敗した');
  assert.equal(hasItem(snap, '01_requirements.md'), false);
  assert.equal(itemOf(snap, '00_input.md').text, 'メモ');
  assert.equal(itemOf(snap, '02_design.md').text, '設計');
  assert.equal(snap.stateJson, state);
  assert.deepEqual(snap.stageLogs.map((l) => l.fileName), ['01_requirements.jsonl']);
  assert.equal(viewOf(snap).noRecords, null, '図が「記録なし」にならない');
});

test('D0025-AC-48: lstat が投げる成果物（failLstat）も同じ。readHead は呼ばず、その成果物だけ項目が無く、ほかは残る', async () => {
  const state = stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] });
  const { snap, rec } = await readFake({ '00_input.md': { text: 'メモ' }, '01_requirements.md': { text: '要件', failLstat: true }, '02_design.md': { text: '設計' } }, state);
  assert.equal(rec.count('readHead', '01_requirements.md'), 0);
  assert.equal(hasItem(snap, '01_requirements.md'), false);
  assert.deepEqual(Object.keys(snap.artifacts).sort(), ['00_input.md', '02_design.md']);
  assert.equal(snap.stateJson, state);
  assert.equal(viewOf(snap).noRecords, null);
});

test('D0025-AC-48: 本物の symlink（リンク先が実行のフォルダの外・中）とフォルダの成果物は読まれず、写しに項目が無い。通常のファイルは読まれる', async (t) => {
  await withTempDir(async (base) => {
    const run = path.join(base, 'run');
    await mkdir(run);
    await writeFile(path.join(base, 'outside.md'), '外のファイルの中身');
    await writeFile(path.join(run, 'inside.md'), '中のファイルの中身');
    await writeFile(path.join(run, '00_input.md'), 'メモ');
    try {
      await symlink(path.join(base, 'outside.md'), path.join(run, '01_requirements.md'));
      await symlink(path.join(run, 'inside.md'), path.join(run, '02_design.md'));
    } catch {
      t.skip('この環境では symlink を作れない（偽の lstat のテストが道を塞ぐ）');
      return;
    }
    await mkdir(path.join(run, '03_red_tests.md'));
    const snap = await createSource(run, 'docs/pipeline').read();
    assert.deepEqual(Object.keys(snap.artifacts), ['00_input.md']);
    assert.equal(itemOf(snap, '00_input.md').text, 'メモ');
    assert.equal(JSON.stringify(snap).includes('ファイルの中身'), false);
  });
});

test('D0025-AC-48: 00_input.md の先頭（実行の一覧の名前づくり）と state.json は、今までどおり symlink を辿って読む（今のまま通る。守る）', async (t) => {
  await withTempDir(async (base) => {
    const work = path.join(base, 'work');
    await mkdir(work);
    const realState = stateJson({ pipe: 'dev', runs: [] });
    await writeFile(path.join(base, 'real-state.json'), realState);
    await writeFile(path.join(base, 'real-memo.md'), 'リンク先のメモ');
    try {
      await symlink(path.join(base, 'real-state.json'), path.join(work, 'state.json'));
      await symlink(path.join(base, 'real-memo.md'), path.join(work, '00_input.md'));
    } catch {
      t.skip('この環境では symlink を作れない');
      return;
    }
    const root = (await listPlaceRuns(work, { archiveLimit: 10 })).runs.find((r) => r.id === '');
    assert.ok(root, '直下の run が読める');
    assert.equal(root.stateJson, realState);
    assert.equal((root as { memoHead?: string | null }).memoHead, 'リンク先のメモ');
  });
});

// ---- AC-49・AC-05：更新時刻は lstat の値 ----

test('D0025-AC-49: 更新時刻は種類の確かめと同じ 1 回の lstat の値から読む（stat の値は使わず、stat は呼ばない）', async () => {
  const { snap, rec } = await readFake({ '01_requirements.md': { text: '要件', mtimeMs: GOOD_MTIME, statMtimeMs: GOOD_MTIME + 999_000 } });
  assert.equal(itemOf(snap, '01_requirements.md').mtimeMs, GOOD_MTIME);
  assert.equal(rec.count('lstat', '01_requirements.md'), 1);
  assert.equal(rec.count('stat', '01_requirements.md'), 0);
});

const BAD_LSTAT_MTIMES: readonly (readonly [string, unknown])[] = [
  ['0', 0],
  ['-1', -1],
  ['NaN', Number.NaN],
  ['Infinity', Number.POSITIVE_INFINITY],
  ['-Infinity', Number.NEGATIVE_INFINITY],
  ['数の文字', '1760000000000'],
  ['undefined（項目なし）', undefined],
  ['null', null],
  ['true', true],
];

for (const [label, bad] of BAD_LSTAT_MTIMES) {
  test(`D0025-AC-49: lstat の mtimeMs が ${label} の成果物は、mtimeMs なし（null）で、中身は写しに入る`, async () => {
    const { snap } = await readFake({ '01_requirements.md': { text: '要件の本文', mtimeMs: bad }, '02_design.md': { text: '設計', mtimeMs: GOOD_MTIME } });
    const item = itemOf(snap, '01_requirements.md');
    assert.equal(item.text, '要件の本文');
    assert.equal(item.mtimeMs ?? null, null);
    assert.equal(itemOf(snap, '02_design.md').mtimeMs, GOOD_MTIME, '対照：ほかの成果物の時刻は数のまま付く');
  });
}

test('D0025-AC-05: 更新時刻が読めない成果物でも、中身（text）は写しに入り、図の状態では「ある」で時刻の欄は「—」', async () => {
  const { snap } = await readFake({ '01_requirements.md': { text: '要件の本文', mtimeMs: Number.NaN } });
  const view = buildPipelineView(snap as unknown as WorkDirSnapshot, { nowMs: GOOD_MTIME, localOffsetMin: 540 });
  const row = view.artifacts.find((a) => a.name === '01_requirements.md') as unknown as { ready: boolean; text: string; updatedText: string };
  assert.deepEqual([row.ready, row.text, row.updatedText], [true, '要件の本文', '—']);
});

test('D0025-AC-05: 正しい更新時刻の成果物は、図の状態で手元の時刻の MM/DD HH:mm になる', async () => {
  const { snap } = await readFake({ '01_requirements.md': { text: '要件の本文', mtimeMs: GOOD_MTIME } });
  const view = buildPipelineView(snap as unknown as WorkDirSnapshot, { nowMs: GOOD_MTIME, localOffsetMin: 540 });
  const row = view.artifacts.find((a) => a.name === '01_requirements.md') as unknown as { updatedText: string };
  assert.equal(row.updatedText, '10/17 10:05');
});

test('D0025-AC-49: lstat が失敗したときは readHead を呼ばず、時刻も付けず、写しに項目が無い（「まだない」と同じ扱い）', async () => {
  const { snap, rec } = await readFake({ '01_requirements.md': { text: '要件', failLstat: true } });
  assert.equal(rec.count('lstat', '01_requirements.md'), 1);
  assert.equal(rec.count('readHead', '01_requirements.md'), 0);
  assert.equal(hasItem(snap, '01_requirements.md'), false);
});

// ---- AC-50：読み取りの口は 6 つのまま ----

test('D0025-AC-50: 読み取りの口 nodeReadOnlyFs は 6 つのまま（書き込みの関数を口に足さない。今のまま通る。守る）', () => {
  assert.deepEqual(Object.keys(nodeReadOnlyFs).sort(), ['lstat', 'readFile', 'readHead', 'readdir', 'realpath', 'stat']);
});

test('D0025-AC-50: 偽の口も 6 つの形だけで読める（書き込みの関数が無くても、成果物・state.json・段のログが読める）', async () => {
  const fake = makeFs({ '01_requirements.md': { text: '要件' } });
  assert.deepEqual(Object.keys(fake.fs).sort(), ['lstat', 'readFile', 'readHead', 'readdir', 'realpath', 'stat']);
  const snap = await createSource(WORK, 'docs/pipeline', { fs: fake.fs }).read();
  assert.equal(itemOf(snap, '01_requirements.md').text, '要件');
});

// ---- AC-51：options.fs ----

test('D0025-AC-51: options.fs を渡すと、成果物・state.json・段のログの読みが、渡した口だけを通る', async () => {
  const state = stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] });
  const log = logText([promptLine('requirements'), assistantText('書いた')]);
  const T_LOG = Date.UTC(2026, 9, 17, 2, 0, 0);
  const { snap, rec } = await readFake({ '01_requirements.md': { text: '要件' }, 'logs/01_requirements.jsonl': { text: log, mtimeMs: T_LOG } }, state);
  assert.equal(snap.workDir, 'docs/pipeline');
  assert.equal(snap.stateJson, state, 'state.json も渡した口から');
  assert.deepEqual(snap.stageLogs, [{ fileName: '01_requirements.jsonl', text: log, mtimeMs: T_LOG }], '段のログも渡した口から（更新時刻は stat）');
  assert.equal(itemOf(snap, '01_requirements.md').text, '要件');
  assert.ok(rec.calls.length > 0);
  assert.ok(rec.calls.every((c) => c.path === WORK || c.path.startsWith(WORK + path.sep)));
});

test('D0025-AC-51: options.fs を渡さない（または undefined）と、今までと同じに一時フォルダの本物を読む（成果物の鍵と state.json。今のまま通る。守る）', async () => {
  await withTempDir(async (dir) => {
    await writeFile(path.join(dir, 'state.json'), stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }));
    await writeFile(path.join(dir, '01_requirements.md'), '要件');
    for (const options of [undefined, {}, { fs: undefined }]) {
      const snap = await createSource(dir, 'docs/pipeline', options).read();
      assert.deepEqual(Object.keys(snap.artifacts), ['01_requirements.md']);
      assert.ok(snap.stateJson?.includes('requirements'));
    }
  });
});

test('D0025-AC-51: options.fs を渡さないときの成果物の写しは { text, mtimeMs, cut } の形（本物の一時フォルダ）', async () => {
  await withTempDir(async (dir) => {
    await writeFile(path.join(dir, '01_requirements.md'), '要件');
    const item = itemOf(await createSource(dir, 'docs/pipeline').read(), '01_requirements.md');
    assert.equal(item.text, '要件');
    assert.equal(typeof item.mtimeMs, 'number');
    assert.equal(item.cut === true, false);
  });
});

// ---- AC-37：合計の読み上限 ----

test('D0025-AC-37: 段が 58 のパイプ（成果物 60 個）で、どれも 262,145 バイト以上のとき、読まれるのは合計の上限まで（16 個）。17 個目以降は lstat もされず、readFile は 0 回', async () => {
  const outputs = Array.from({ length: 58 }, (_, i) => `o${String(i).padStart(2, '0')}.md`);
  const names = ['00_input.md', ...outputs, '99_summary.md'];
  assert.equal(names.length, 60);
  const big = 'a'.repeat(300_000);
  const { snap, rec } = await readFake(Object.fromEntries(names.map((n) => [n, { text: big }])), pipeState(outputs));
  assert.equal(rec.paths('lstat').length, 16);
  assert.equal(rec.paths('readHead').length, 16);
  assert.equal(rec.calls.filter((c) => c.op === 'readFile' && !c.path.endsWith('state.json')).length, 0);
  assert.deepEqual(rec.paths('lstat'), names.slice(0, 16).map(at));
  assert.deepEqual(Object.keys(snap.artifacts), names.slice(0, 16));
  const total = Object.values(snap.artifacts).reduce<number>((sum, v) => sum + bytes((v as Item).text), 0);
  assert.equal(total, 16 * MAX);
  assert.ok(total < TOTAL + MAX, `写しの文字の合計 ${total} は上限 + 256 KiB 未満`);
});

test('D0025-AC-37: 合計の上限に届かない 12 個（上限いっぱい × 12 ＝ 3 MiB）は全部読む', async () => {
  const outputs = Array.from({ length: 10 }, (_, i) => `o${i}.md`);
  const names = ['00_input.md', ...outputs, '99_summary.md'];
  const big = 'a'.repeat(300_000);
  const { snap, rec } = await readFake(Object.fromEntries(names.map((n) => [n, { text: big }])), pipeState(outputs));
  assert.equal(names.length, 12);
  assert.equal(rec.paths('lstat').length, 12);
  assert.equal(rec.paths('readHead').length, 12);
  assert.deepEqual(Object.keys(snap.artifacts), names);
  assert.equal(Object.values(snap.artifacts).reduce<number>((sum, v) => sum + bytes((v as Item).text), 0), 12 * MAX);
});

test('D0025-AC-37: 合計の確かめは読む前に行う：上限の直前まで読んだあとの 1 つは切らずに入れ、その次からは読まない（合計は上限 + 256 KiB 未満）', async () => {
  const each = MAX - 1;
  const outputs = Array.from({ length: 20 }, (_, i) => `o${String(i).padStart(2, '0')}.md`);
  const names = ['00_input.md', ...outputs, '99_summary.md'];
  const text = 'b'.repeat(each);
  const { snap, rec } = await readFake(Object.fromEntries(names.map((n) => [n, { text }])), pipeState(outputs));
  // 16 個で 4,194,288 バイト（上限未満）なので 17 個目も読む。17 個で 4,456,431 バイトになり、18 個目からは読まない
  assert.equal(rec.paths('readHead').length, 17);
  assert.equal(Object.keys(snap.artifacts).length, 17);
  const total = Object.values(snap.artifacts).reduce<number>((sum, v) => sum + bytes((v as Item).text), 0);
  assert.equal(total, 17 * each);
  assert.ok(total >= TOTAL && total < TOTAL + MAX);
  assert.equal(itemOf(snap, names[16]!).text, text, '上限を越えさせる 1 つは切らずに入れる');
  assert.equal(hasItem(snap, names[17]!), false);
});

test('D0025-AC-37: 合計は、写しに入れた文字だけを数える（無い・symlink・読めない成果物は数えず、読む個数を減らさない）', async () => {
  const outputs = Array.from({ length: 6 }, (_, i) => `o${i}.md`);
  const files: Record<string, FileSpec> = {
    '00_input.md': { text: 'メモ' },
    'o0.md': { isFile: false, link: true, text: 'x'.repeat(300_000) },
    'o1.md': { text: 'x'.repeat(300_000), failRead: true },
    'o2.md': { text: 'ふつう' },
  };
  const { snap, rec } = await readFake(files, pipeState(outputs));
  assert.equal(rec.paths('lstat').length, 8, '8 つの名前すべてを lstat する（数えた合計が小さいので打ち切らない）');
  assert.deepEqual(Object.keys(snap.artifacts), ['00_input.md', 'o2.md']);
});

// ---- AC-64：変な名前（constructor・__proto__ ほか） ----

test('D0025-AC-64: output が constructor・__proto__・toString・hasOwnProperty・valueOf・text でも、写しの項目は自分のキーとして入り、入れ物の原型が替わらず、ほかの成果物が「ある」のまま', async () => {
  const odd = ['constructor', '__proto__', 'toString', 'hasOwnProperty', 'valueOf', 'text'];
  // __proto__ という名前は、代入ではなく fromEntries で自分のキーにする（代入だと原型が替わってしまう）
  const entries: [string, FileSpec][] = [
    ['00_input.md', { text: 'メモ' }],
    ['99_summary.md', { text: 'まとめ' }],
    ...odd.map((name): [string, FileSpec] => [name, { text: `${name} の中身` }]),
  ];
  const files: Record<string, FileSpec> = Object.fromEntries(entries);
  const { snap } = await readFake(files, pipeState(odd));
  assert.equal(Object.getPrototypeOf(snap.artifacts), Object.prototype, '入れ物の原型が替わっていない');
  assert.deepEqual(Object.keys(snap.artifacts).sort(), ['00_input.md', '99_summary.md', ...odd].sort());
  for (const name of odd) {
    assert.equal(hasItem(snap, name), true, `${name} は自分のキー`);
    assert.equal(itemOf(snap, name).text, `${name} の中身`);
  }
  assert.equal(itemOf(snap, '00_input.md').text, 'メモ');
  assert.equal(itemOf(snap, '99_summary.md').text, 'まとめ');
  assert.equal(Object.hasOwn(Object.prototype, 'text'), false);
  const rows = viewOf(snap).artifacts as unknown as { name: string; ready: boolean; text: string }[];
  assert.deepEqual(rows.map((r) => [r.name, r.ready]), [['00_input.md', true], ...odd.map((n) => [n, true]), ['99_summary.md', true]]);
  for (const name of odd) assert.equal(rows.find((r) => r.name === name)?.text, `${name} の中身`);
});

test('D0025-AC-64: output が constructor などでも、ファイルが無ければ項目は入らず、図の状態は「まだない」になる（例外なし）', async () => {
  const odd = ['constructor', '__proto__', 'toString'];
  const { snap } = await readFake({ '00_input.md': { text: 'メモ' } }, pipeState(odd));
  assert.deepEqual(Object.keys(snap.artifacts), ['00_input.md']);
  const rows = viewOf(snap).artifacts;
  assert.deepEqual(rows.map((r) => [r.name, r.ready]), [['00_input.md', true], ...odd.map((n) => [n, false]), ['99_summary.md', false]]);
});

// ---- AC-71：state.json が無い・壊れていても、ファイルが読めれば中身が出る ----

const BROKEN_STATE_FILES: readonly (readonly [string, string | null])[] = [
  ['state.json が無い', null],
  ['壊れた JSON の state.json', '{壊れた'],
  ['JSON の配列の state.json', '[1,2]'],
];

for (const [label, state] of BROKEN_STATE_FILES) {
  test(`D0025-AC-71: ${label}の run でも、開発フローの 7 つの名前を読み、読めたファイルの中身が写しに入る`, async () => {
    await withTempDir(async (dir) => {
      if (state !== null) await writeFile(path.join(dir, 'state.json'), state);
      await writeFile(path.join(dir, '01_requirements.md'), '要件の本文');
      await writeFile(path.join(dir, '99_summary.md'), 'まとめの本文');
      await writeFile(path.join(dir, 'other.md'), '一覧の外');
      const snap = await createSource(dir, 'docs/pipeline').read();
      assert.deepEqual(Object.keys(snap.artifacts).sort(), ['01_requirements.md', '99_summary.md']);
      assert.equal(itemOf(snap, '01_requirements.md').text, '要件の本文');
      assert.equal(itemOf(snap, '99_summary.md').text, 'まとめの本文');
      const names = viewOf(snap).artifacts.map((a) => a.name);
      assert.deepEqual(names, DEV_NAMES);
    });
  });
}

test('D0025-AC-72: 空のファイルも写しに入り（text は空）、図の状態では「まだない」だが、記録なしの表示は出ない（今の「00_input.md が artifacts にある」と同じ）', async () => {
  const { snap } = await readFake({ '00_input.md': { text: '' }, '01_requirements.md': { text: '  \n' } });
  assert.equal(itemOf(snap, '00_input.md').text, '');
  assert.equal(itemOf(snap, '01_requirements.md').text, '  \n');
  const view = viewOf(snap);
  assert.equal(view.noRecords, null);
  assert.deepEqual(view.artifacts.filter((a) => a.ready).map((a) => a.name), []);
});

test('D0025-AC-71: work_dir が存在しなくても例外を出さず、成果物の項目は無い（今のまま通る。守る）', async () => {
  const snap = await createSource(path.join(WORK, 'missing'), 'docs/pipeline').read();
  assert.deepEqual(Object.keys(snap.artifacts), []);
});
