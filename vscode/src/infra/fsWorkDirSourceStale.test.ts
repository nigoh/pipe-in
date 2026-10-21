// 基盤：段のログの更新時刻（mtimeMs）を記録の写しに付ける（D0021・止まっているかもしれない実行の印の元）。AC-01・02・03・47。
// 一時フォルダに記録を作り、utimes で更新時刻を決めて読ませる。偽の fs は手で書く（モックのライブラリは使わない）。
// 偽の fs を渡せるのは listPlaceRuns の側だけ（createFsWorkDirSource は fs を受けない。どちらも readStageLogs 1 つを通る）。
// そのため、選んだ実行の道（createFsWorkDirSource().read()）の AC-02 は、偽物なしで実ファイルの更新時刻を 0 にして確かめる。
// 今のまま通るテスト（赤ではなく、守り続けるために置く。名前の末尾に「守る」と書いた）：AC-03 の 2 件（操作の種類・口が 6 つ）と AC-47 の 3 件。ほかは赤。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { utimes } from 'node:fs/promises';
import path from 'node:path';
import { createFsRunsSource, createFsWorkDirSource, listPlaceRuns } from './fsWorkDirSource.ts';
import { nodeReadOnlyFs } from './readOnlyFs.ts';
import type { ReadOnlyFs } from './readOnlyFs.ts';
import { assistantText, logText, promptLine, resultLine, stageRunEntry, stateJson } from '../test/fixtures.ts';
import { makeRepo, put } from '../test/gitFixtures.ts';
import { recordingFs } from '../test/recordingFs.ts';
import { withTempDir } from '../test/tempDir.ts';

const AT = '2026-10-17T10:00:00+00:00';
const REQ_LOG = logText([promptLine('requirements', AT), assistantText('書いた'), resultLine()]);
const DESIGN_LOG = logText([promptLine('design', AT), assistantText('設計します')]);
const RED_LOG = logText([promptLine('red', AT), assistantText('テストを書きます')]);
/** name を入れる：セッション名の元に 00_input.md の先頭を読ませない（readHead を呼ばせない） */
const RUN_STATE = stateJson({ name: '付けた名前', runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] });

// 更新時刻は整数の秒に置く（粗い時刻のファイルシステムでも同じ値になる）
const T_REQ = Date.UTC(2026, 9, 17, 9, 55, 0);
const T_DESIGN = Date.UTC(2026, 9, 17, 10, 1, 0);
const T_RED = Date.UTC(2026, 9, 17, 10, 2, 0);
const T_OTHER_REQ = Date.UTC(2026, 9, 17, 8, 30, 0);
const T_OTHER_DESIGN = Date.UTC(2026, 9, 17, 8, 40, 0);

async function setMtime(file: string, ms: number): Promise<void> {
  const when = new Date(ms);
  await utimes(file, when, when);
}

/** state.json と、logs/ の下のログを書く。 */
async function putRun(dir: string, state: string, logs: Readonly<Record<string, string>>): Promise<void> {
  await put(path.join(dir, 'state.json'), state);
  for (const [name, text] of Object.entries(logs)) await put(path.join(dir, 'logs', name), text);
}

/** mtimeMs は unknown として取る（テスト先行のときは型に無かった。実装後も読める）。 */
const mtimeOf = (log: object): unknown => (log as { mtimeMs?: unknown }).mtimeMs;

/** ［ファイル名, 更新時刻］の並び（ファイル名の順）。 */
function pairs(logs: readonly { fileName: string }[]): [string, unknown][] {
  return logs.map((l): [string, unknown] => [l.fileName, mtimeOf(l)]).sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
}

type CreateSource = (dir: string, display: string, options?: { previous?: boolean }) => { read(): Promise<object> };
/** 3 つ目の引数（previous）は、実装の段で型に入る。 */
const createSource = createFsWorkDirSource as unknown as CreateSource;

// ---- 偽の fs（手で書く）：logs/ の下のファイルの stat だけ差し替える。state.json などの stat は本物のまま ----

const THROW = Symbol('stat が失敗する');

/**
 * nodeReadOnlyFs を土台に、logsDir の直下のファイルのうち mtimes に名前があるものの stat だけを差し替える。
 * 値が THROW なら stat が失敗し（途中で消えた）、それ以外は mtimeMs にその値を入れた結果を返す。
 * 差し替えないのは readState が isFile()・size を使う state.json などの stat（本物のまま）。
 */
function fsWithLogMtimes(logsDir: string, mtimes: Readonly<Record<string, unknown>>): ReadOnlyFs {
  const realStat = nodeReadOnlyFs.stat as unknown as (...args: unknown[]) => Promise<unknown>;
  const stat = async (file: unknown, ...rest: unknown[]): Promise<unknown> => {
    const where = String(file);
    if (path.dirname(where) === logsDir && Object.hasOwn(mtimes, path.basename(where))) {
      const value = mtimes[path.basename(where)];
      if (value === THROW) throw Object.assign(new Error('ENOENT: 途中で消えた'), { code: 'ENOENT' });
      return { mtimeMs: value, size: 1, isFile: () => true, isDirectory: () => false };
    }
    return realStat(where, ...rest);
  };
  return { ...nodeReadOnlyFs, stat: stat as unknown as ReadOnlyFs['stat'] };
}

// ---- AC-01：段のログごとに、更新時刻（stat）を写しに付ける ----

test('D0021-AC-01: createFsWorkDirSource().read() は、段のログごとに stat の更新時刻を mtimeMs に入れる（utimes で決めた時刻と一致）', async () => {
  await withTempDir(async (dir) => {
    await putRun(dir, RUN_STATE, { '01_requirements.jsonl': REQ_LOG, '02_design.jsonl': DESIGN_LOG });
    await setMtime(path.join(dir, 'logs', '01_requirements.jsonl'), T_REQ);
    await setMtime(path.join(dir, 'logs', '02_design.jsonl'), T_DESIGN);

    const snap = (await createSource(dir, 'docs/pipeline').read()) as { stageLogs: { fileName: string; text: string }[] };
    assert.deepEqual(pairs(snap.stageLogs), [
      ['01_requirements.jsonl', T_REQ],
      ['02_design.jsonl', T_DESIGN],
    ]);
    assert.equal(snap.stageLogs.find((l) => l.fileName === '02_design.jsonl')?.text, DESIGN_LOG, '中身は今までどおり読めている');
  });
});

test('D0021-AC-01: createFsRunsSource().runs(place) は、いまの work_dir（here）と別の worktree の work_dir の両方で、同じ読み方で mtimeMs を付ける', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-x', branch: 'feat/x', state: RUN_STATE }], { mainState: RUN_STATE });
    const here = path.join(repo.mainRoot, 'docs', 'pipeline');
    const other = path.join(repo.roots['feat-x']!, 'docs', 'pipeline');
    for (const dir of [here, other]) {
      await put(path.join(dir, 'logs', '01_requirements.jsonl'), REQ_LOG);
      await put(path.join(dir, 'logs', '02_design.jsonl'), DESIGN_LOG);
    }
    // 場所ごとに違う時刻にして、それぞれのログの時刻が付くことを見る
    await setMtime(path.join(here, 'logs', '01_requirements.jsonl'), T_REQ);
    await setMtime(path.join(here, 'logs', '02_design.jsonl'), T_DESIGN);
    await setMtime(path.join(other, 'logs', '01_requirements.jsonl'), T_OTHER_REQ);
    await setMtime(path.join(other, 'logs', '02_design.jsonl'), T_OTHER_DESIGN);

    const source = createFsRunsSource(repo.mainRoot, here, 'docs/pipeline');
    const { places } = await source.places(true);
    assert.deepEqual(places.map((p) => p.key), ['here', 'wt.feat-x'], '別の worktree の場所が見つかる');
    const expected: Record<string, [string, unknown][]> = {
      here: [['01_requirements.jsonl', T_REQ], ['02_design.jsonl', T_DESIGN]],
      'wt.feat-x': [['01_requirements.jsonl', T_OTHER_REQ], ['02_design.jsonl', T_OTHER_DESIGN]],
    };
    for (const place of places) {
      const root = (await source.runs(place)).runs.find((r) => r.id === '');
      assert.ok(root, `${place.key} の直下の run が読める`);
      assert.deepEqual(pairs(root.stageLogs), expected[place.key], place.key);
    }
  });
});

test('D0021-AC-01: 更新時刻は、ログの中身を読んだあとに stat する（読んだ中身より古い時刻にならず、誤報の側に倒れない）', async () => {
  await withTempDir(async (dir) => {
    await putRun(dir, RUN_STATE, { '01_requirements.jsonl': REQ_LOG, '02_design.jsonl': DESIGN_LOG });
    const rec = recordingFs();
    await listPlaceRuns(dir, { archiveLimit: 10, fs: rec.fs });
    for (const name of ['01_requirements.jsonl', '02_design.jsonl']) {
      const file = path.join(dir, 'logs', name);
      const read = rec.calls.findIndex((c) => c.op === 'readFile' && c.path === file);
      const stat = rec.calls.findIndex((c) => c.op === 'stat' && c.path === file);
      assert.ok(read >= 0, `${name} の中身を読んでいる`);
      assert.ok(stat > read, `${name} の stat は、中身を読んだあと（readFile は ${read} 番目、stat は ${stat} 番目）`);
    }
  });
});

// ---- AC-02：更新時刻が読めないときは、時刻なしで写しに入る。読み取り全体は失敗しない ----

test('D0021-AC-02: stat が失敗するログ（途中で消えた）は mtimeMs: null で写しに入る。ほかのログは中身も時刻も読め、読み取り全体は失敗しない', async () => {
  await withTempDir(async (dir) => {
    await putRun(dir, RUN_STATE, { '01_requirements.jsonl': REQ_LOG, '02_design.jsonl': DESIGN_LOG });
    const fs = fsWithLogMtimes(path.join(dir, 'logs'), { '01_requirements.jsonl': THROW, '02_design.jsonl': T_DESIGN });

    const root = (await listPlaceRuns(dir, { archiveLimit: 10, fs })).runs.find((r) => r.id === '');
    assert.ok(root, '読み取りは失敗しない（run が返る）');
    const byName = Object.fromEntries(root.stageLogs.map((l) => [l.fileName, l]));
    assert.equal(byName['01_requirements.jsonl']?.text, REQ_LOG, 'stat が失敗したログも、中身は読めている');
    assert.equal(mtimeOf(byName['01_requirements.jsonl']!), null);
    assert.equal(byName['02_design.jsonl']?.text, DESIGN_LOG);
    assert.equal(mtimeOf(byName['02_design.jsonl']!), T_DESIGN, 'ほかのログの更新時刻は付く');
  });
});

/** stat が返す mtimeMs が、有限で 0 より大きい数でないもの。どれも null になる。 */
const BAD_MTIME_ROWS: readonly (readonly [string, unknown])[] = [
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

for (const [label, bad] of BAD_MTIME_ROWS) {
  test(`D0021-AC-02: stat の mtimeMs が ${label} のログは mtimeMs: null で写しに入る（中身は読めて、ほかのログの時刻は付く）`, async () => {
    await withTempDir(async (dir) => {
      await putRun(dir, RUN_STATE, { '01_requirements.jsonl': REQ_LOG, '02_design.jsonl': DESIGN_LOG });
      const fs = fsWithLogMtimes(path.join(dir, 'logs'), { '01_requirements.jsonl': bad, '02_design.jsonl': T_DESIGN });

      const root = (await listPlaceRuns(dir, { archiveLimit: 10, fs })).runs.find((r) => r.id === '');
      assert.ok(root, '読み取りは失敗しない（run が返る）');
      const byName = Object.fromEntries(root.stageLogs.map((l) => [l.fileName, l]));
      assert.equal(byName['01_requirements.jsonl']?.text, REQ_LOG, '中身は読めている');
      assert.equal(mtimeOf(byName['01_requirements.jsonl']!), null);
      assert.equal(mtimeOf(byName['02_design.jsonl']!), T_DESIGN, '対照：ほかのログ（正しい時刻）は数のまま付く');
    });
  });
}

test('D0021-AC-02: 選んだ実行の道でも、実ファイルの更新時刻が 0 のログは mtimeMs: null（createFsWorkDirSource().read()。対照：ほかのログは数）', async () => {
  await withTempDir(async (dir) => {
    await putRun(dir, RUN_STATE, { '01_requirements.jsonl': REQ_LOG, '02_design.jsonl': DESIGN_LOG });
    await setMtime(path.join(dir, 'logs', '01_requirements.jsonl'), 0);
    await setMtime(path.join(dir, 'logs', '02_design.jsonl'), T_DESIGN);

    const snap = (await createSource(dir, 'docs/pipeline').read()) as { stageLogs: { fileName: string; text: string }[] };
    const byName = Object.fromEntries(snap.stageLogs.map((l) => [l.fileName, l]));
    assert.equal(byName['01_requirements.jsonl']?.text, REQ_LOG, '更新時刻が 0 のログも、中身は読めている');
    assert.equal(mtimeOf(byName['01_requirements.jsonl']!), null);
    assert.equal(mtimeOf(byName['02_design.jsonl']!), T_DESIGN, '対照：ほかのログ（正しい時刻）は数のまま付く');
  });
});

// ---- AC-03：読み取りに足すのは stat だけ ----

test('D0021-AC-03: ログ n 個を読むと、stat がそのログのパスにちょうど n 回（1 つにつき 1 回）呼ばれる', async () => {
  await withTempDir(async (dir) => {
    const names = ['01_requirements.jsonl', '02_design.jsonl', '03_red.jsonl'];
    await putRun(dir, RUN_STATE, { [names[0]!]: REQ_LOG, [names[1]!]: DESIGN_LOG, [names[2]!]: RED_LOG });
    const rec = recordingFs();
    const found = await listPlaceRuns(dir, { archiveLimit: 10, fs: rec.fs });

    const root = found.runs.find((r) => r.id === '');
    assert.equal(root?.stageLogs.length, names.length, '前提：ログ n 個が読める');
    const logsDir = path.join(dir, 'logs');
    const statOnLogs = rec.paths('stat').filter((p) => path.dirname(p) === logsDir).sort();
    assert.deepEqual(statOnLogs, names.map((n) => path.join(logsDir, n)).sort());
  });
});

test('D0021-AC-03: 場所の中を読むときに記録された操作の種類は readFile・readdir・stat だけ（lstat・realpath・readHead は呼ばない）（今のまま通る。守る）', async () => {
  await withTempDir(async (dir) => {
    await putRun(dir, RUN_STATE, { '01_requirements.jsonl': REQ_LOG, '02_design.jsonl': DESIGN_LOG });
    const rec = recordingFs();
    await listPlaceRuns(dir, { archiveLimit: 10, fs: rec.fs });
    assert.deepEqual([...new Set(rec.calls.map((c) => c.op))].sort(), ['readFile', 'readdir', 'stat']);
  });
});

test('D0021-AC-03: 読み取りの口 ReadOnlyFs は 6 つのまま（stat は今ある口で、書き込みの関数を口に足さない）（今のまま通る。守る）', () => {
  assert.deepEqual(Object.keys(nodeReadOnlyFs).sort(), ['lstat', 'readFile', 'readHead', 'readdir', 'realpath', 'stat']);
});

// ---- AC-47：前の実行（archive/）の写しの印 ----

test('D0021-AC-47: createFsWorkDirSource(dir, 表示, { previous: true }) の写しは previous: true を持つ', async () => {
  await withTempDir(async (dir) => {
    await putRun(dir, RUN_STATE, { '02_design.jsonl': DESIGN_LOG });
    const snap = await createSource(dir, 'docs/pipeline', { previous: true }).read();
    assert.equal((snap as { previous?: unknown }).previous, true);
  });
});

const NOT_PREVIOUS: readonly (readonly [string, { previous?: boolean } | undefined])[] = [
  ['options を渡さない', undefined],
  ['空の options を渡す', {}],
  ['previous: false を渡す', { previous: false }],
];

for (const [label, options] of NOT_PREVIOUS) {
  test(`D0021-AC-47: ${label}と、写しは previous の項目ごと持たない（空の写しを deepEqual する既存のテストを壊さない）（今のまま通る。守る）`, async () => {
    await withTempDir(async (dir) => {
      await putRun(dir, RUN_STATE, { '02_design.jsonl': DESIGN_LOG });
      const snap = await createSource(dir, 'docs/pipeline', options).read();
      assert.equal(Object.hasOwn(snap, 'previous'), false);
      assert.deepEqual(Object.keys(snap).sort(), ['artifacts', 'stageLogs', 'stateJson', 'workDir']);
    });
  });
}
