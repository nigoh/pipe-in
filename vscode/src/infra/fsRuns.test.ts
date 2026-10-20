// 基盤：work_dir の中の実行の候補を見つけ、パイプの記録の成果物を読む。AC-01・AC-06。
// 一時フォルダに記録を作って読ませる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import * as fsSource from './fsWorkDirSource.ts';
import { DIAGRAMS_STAGES, stateJson } from '../test/fixtures.ts';

type ListRunCandidates = (workDirAbs: string) => Promise<{ id: string; label: string; updatedAt: string | null }[]>;
const listRunCandidates = (dir: string) =>
  (fsSource as unknown as { listRunCandidates: ListRunCandidates }).listRunCandidates(dir);

async function withTempDir(fn: (dir: string) => Promise<void>): Promise<void> {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'pipe-in-vscode-runs-'));
  try {
    await fn(dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

test('AC-01: 直下とサブフォルダの state.json を候補にし、logs は候補にしない', async () => {
  await withTempDir(async (dir) => {
    await writeFile(path.join(dir, 'state.json'), stateJson({ pipe: 'dev', updatedAt: '2026-10-16T10:00:00' }));
    for (const sub of ['diagrams', 'logs', 'Bad_Name', 'empty']) await mkdir(path.join(dir, sub));
    await writeFile(path.join(dir, 'diagrams', 'state.json'), stateJson({ pipe: 'diagrams', updatedAt: '2026-10-16T11:00:00' }));
    await writeFile(path.join(dir, 'logs', 'state.json'), stateJson({}));
    await writeFile(path.join(dir, 'Bad_Name', 'state.json'), stateJson({}));
    await writeFile(path.join(dir, 'state.json.md'), 'x');

    const found = await listRunCandidates(dir);
    assert.deepEqual(found, [
      { id: '', label: '開発フロー', updatedAt: '2026-10-16T10:00:00' },
      { id: 'diagrams', label: 'diagrams', updatedAt: '2026-10-16T11:00:00' },
    ]);
  });
});

test('AC-01: 直下に記録がなければパイプだけ、何もなければ直下だけ（記録なしの表示のため）', async () => {
  await withTempDir(async (dir) => {
    assert.deepEqual(await listRunCandidates(dir), [{ id: '', label: '開発フロー', updatedAt: null }]);
    await mkdir(path.join(dir, 'spec-qa'));
    await writeFile(path.join(dir, 'spec-qa', 'state.json'), stateJson({ pipe: 'spec-qa' }));
    assert.deepEqual((await listRunCandidates(dir)).map((c) => c.id), ['spec-qa']);
  });
  const missing = path.join(os.tmpdir(), `pipe-in-vscode-missing-${process.pid}-${Date.now()}`);
  assert.deepEqual(await listRunCandidates(missing), [{ id: '', label: '開発フロー', updatedAt: null }]);
});

test('AC-06: パイプの記録では、依頼メモ・段の成果物・まとめだけを読む（一覧の外や work_dir の外は読まない）', async () => {
  await withTempDir(async (dir) => {
    const run = path.join(dir, 'diagrams');
    await mkdir(run);
    const stages = [...DIAGRAMS_STAGES, { name: 'evil', label: '外', output: '../secret.md', review: false }];
    await writeFile(path.join(run, 'state.json'), stateJson({ pipe: 'diagrams', stages }));
    for (const name of ['00_input.md', '01_survey.md', '02_diagrams.md', 'other.md', '01_requirements.md']) {
      await writeFile(path.join(run, name), name);
    }
    await writeFile(path.join(dir, 'secret.md'), '外のファイル');

    const snap = await fsSource.createFsWorkDirSource(run, run).read();
    assert.deepEqual(Object.keys(snap.artifacts).sort(), ['00_input.md', '01_survey.md', '02_diagrams.md']);
  });
});

// ---- D0019：場所の中の実行（直下・パイプ・archive）の読み取り ----
// まだ無い部品（listPlaceRuns・createFsRunsSource）は、呼んだところで落ちるように、名前空間 import から取り出す。

import { stat, symlink, utimes } from 'node:fs/promises';
import { assistantText, logText, promptLine, resultLine, stageRunEntry } from '../test/fixtures.ts';
import { makeRepo } from '../test/gitFixtures.ts';
import { recordingFs } from '../test/recordingFs.ts';
import { withTempDir as withRealTempDir } from '../test/tempDir.ts';

interface PlaceRun {
  id: string;
  stateJson: string | null;
  stageLogs: { fileName: string; text: string }[];
}
interface PlaceRuns {
  runs: PlaceRun[];
  archiveOmitted: number;
}
type ListPlaceRuns = (workDirAbs: string, opts: { archiveLimit: number; fs?: unknown }) => Promise<PlaceRuns>;
const listPlaceRuns: ListPlaceRuns = (dir, opts) =>
  (fsSource as unknown as { listPlaceRuns: ListPlaceRuns }).listPlaceRuns(dir, opts);

const idsOf = (r: PlaceRuns): string[] => r.runs.map((x) => x.id);
const archiveIdsOf = (r: PlaceRuns): string[] => idsOf(r).filter((id) => id.startsWith('archive/'));

async function putRun(dir: string, rel: string, state: string): Promise<void> {
  await mkdir(path.join(dir, rel), { recursive: true });
  await writeFile(path.join(dir, rel, 'state.json'), state);
}

test('D0019-AC-01: 直下の state.json・*/state.json・archive/*/state.json が、それぞれ別の run になる', async () => {
  await withRealTempDir(async (dir) => {
    await putRun(dir, '', stateJson({ pipe: 'dev', updatedAt: '2026-10-16T10:00:00' }));
    await putRun(dir, 'diagrams', stateJson({ pipe: 'diagrams' }));
    await putRun(dir, 'survey', stateJson({ pipe: 'survey' }));
    await putRun(dir, 'archive/20261016-090000', stateJson({ final: 'TEST_FAILED' }));
    await putRun(dir, 'archive/20261015-090000', stateJson({ final: 'PASSED' }));

    const found = await listPlaceRuns(dir, { archiveLimit: 10 });
    assert.deepEqual(idsOf(found).sort(), ['', 'archive/20261015-090000', 'archive/20261016-090000', 'diagrams', 'survey']);
    assert.equal(found.archiveOmitted, 0);
    const root = found.runs.find((r) => r.id === '')!;
    assert.equal(root.stateJson, stateJson({ pipe: 'dev', updatedAt: '2026-10-16T10:00:00' }));
    const old = found.runs.find((r) => r.id === 'archive/20261016-090000')!;
    assert.match(old.stateJson ?? '', /TEST_FAILED/);
  });
});

test('D0019-AC-01: logs・名前の規則に合わないフォルダ・state.json の無いフォルダ・archive/state.json（パイプとして）は run にならない', async () => {
  await withRealTempDir(async (dir) => {
    await putRun(dir, 'diagrams', stateJson({ pipe: 'diagrams' }));
    await putRun(dir, 'logs', stateJson({}));
    await putRun(dir, 'Bad_Name', stateJson({}));
    await mkdir(path.join(dir, 'empty'));
    // archive は開発フローの記録の移し先で、パイプのフォルダではない
    await putRun(dir, 'archive', stateJson({ pipe: 'archive' }));
    await putRun(dir, 'archive/not-a-stamp', stateJson({}));
    await putRun(dir, 'archive/2026', stateJson({}));
    await mkdir(path.join(dir, 'archive', '20261016-090000')); // state.json が無い

    const found = await listPlaceRuns(dir, { archiveLimit: 10 });
    assert.deepEqual(idsOf(found), ['diagrams']);
    assert.equal(found.archiveOmitted, 0);
  });
});

test('D0019-AC-01: 直下の state.json が無くても、パイプとアーカイブは出る（直下の run は作らない）', async () => {
  await withRealTempDir(async (dir) => {
    await putRun(dir, 'spec-qa', stateJson({ pipe: 'spec-qa' }));
    await putRun(dir, 'archive/20261016-090000', stateJson({ final: 'PASSED' }));
    const found = await listPlaceRuns(dir, { archiveLimit: 10 });
    assert.deepEqual(idsOf(found).sort(), ['archive/20261016-090000', 'spec-qa']);
  });
});

test('D0019-AC-01: symlink のフォルダは辿らない（work_dir の外の記録を run にしない）', async (t) => {
  await withRealTempDir(async (dir) => {
    const outside = path.join(dir, 'outside');
    const work = path.join(dir, 'work');
    await putRun(outside, '', stateJson({ pipe: 'evil' }));
    await putRun(work, 'real', stateJson({ pipe: 'real' }));
    try {
      await symlink(outside, path.join(work, 'linked'), 'dir');
    } catch {
      t.skip('この環境では symlink を作れない');
      return;
    }
    const found = await listPlaceRuns(work, { archiveLimit: 10 });
    assert.deepEqual(idsOf(found), ['real']);
  });
});

function stampName(i: number): string {
  return `202610${String(i).padStart(2, '0')}-090000`;
}

test('D0019-AC-10: archive が 12 件のとき、新しい方から 10 件だけ読み、超えた 2 件は読まずに数だけ返す', async () => {
  await withRealTempDir(async (dir) => {
    await putRun(dir, '', stateJson({ pipe: 'dev' }));
    for (let i = 1; i <= 12; i++) await putRun(dir, `archive/${stampName(i)}`, stateJson({ final: 'PASSED' }));
    const rec = recordingFs();

    const found = await listPlaceRuns(dir, { archiveLimit: 10, fs: rec.fs });
    assert.deepEqual(archiveIdsOf(found), Array.from({ length: 10 }, (_, k) => `archive/${stampName(12 - k)}`), '新しい方から 10 件（新しい順）');
    assert.equal(found.archiveOmitted, 2);
    assert.ok(idsOf(found).includes(''), 'archive の外の run は影響を受けない');

    const stateReads = rec.paths('readFile').filter((p) => p.includes(`${path.sep}archive${path.sep}`));
    assert.equal(stateReads.length, 10, '読んだ archive の state.json は 10 件');
    for (const old of [stampName(1), stampName(2)]) {
      assert.ok(!rec.paths().some((p) => p.includes(old)), `${old} は読まない（stat も readdir もしない）`);
    }
  });
});

test('D0019-AC-10: archive が 10 件以下なら、省いた数は 0', async () => {
  await withRealTempDir(async (dir) => {
    for (let i = 1; i <= 10; i++) await putRun(dir, `archive/${stampName(i)}`, stateJson({ final: 'PASSED' }));
    assert.equal((await listPlaceRuns(dir, { archiveLimit: 10 })).archiveOmitted, 0);
    await rm(path.join(dir, 'archive', stampName(1)), { recursive: true });
    const nine = await listPlaceRuns(dir, { archiveLimit: 10 });
    assert.equal(nine.archiveOmitted, 0);
    assert.equal(archiveIdsOf(nine).length, 9);
  });
});

test('D0019-AC-10: 省く件数は引数で決まる（archiveLimit=3 なら 3 件読み、残りを数える）。archive の外の run は変わらない', async () => {
  await withRealTempDir(async (dir) => {
    await putRun(dir, 'diagrams', stateJson({ pipe: 'diagrams' }));
    for (let i = 1; i <= 5; i++) await putRun(dir, `archive/${stampName(i)}`, stateJson({ final: 'PASSED' }));
    const found = await listPlaceRuns(dir, { archiveLimit: 3 });
    assert.deepEqual(archiveIdsOf(found), [`archive/${stampName(5)}`, `archive/${stampName(4)}`, `archive/${stampName(3)}`]);
    assert.equal(found.archiveOmitted, 2);
    assert.ok(idsOf(found).includes('diagrams'));
  });
});

test('D0019-AC-33: 前の版の archive の名前（20261017-100000 と、重なって付く -2）も run になる。-2 のほうが新しい', async () => {
  await withRealTempDir(async (dir) => {
    await putRun(dir, 'archive/20261017-100000', stateJson({ final: 'PASSED' }));
    await putRun(dir, 'archive/20261017-100000-2', stateJson({ final: 'TEST_FAILED' }));
    const found = await listPlaceRuns(dir, { archiveLimit: 10 });
    assert.deepEqual(archiveIdsOf(found), ['archive/20261017-100000-2', 'archive/20261017-100000']);
  });
});

test('D0019-AC-01: state.json は 4 MiB を超えたら読まず、null として扱う（run は残る）', async () => {
  await withRealTempDir(async (dir) => {
    await putRun(dir, 'big', 'x'.repeat(4 * 1024 * 1024 + 1));
    await putRun(dir, 'small', stateJson({ pipe: 'small' }));
    const rec = recordingFs();
    const found = await listPlaceRuns(dir, { archiveLimit: 10, fs: rec.fs });
    assert.equal(found.runs.find((r) => r.id === 'big')?.stateJson, null);
    assert.ok(found.runs.find((r) => r.id === 'small')?.stateJson?.includes('small'));
    assert.ok(!rec.paths('readFile').some((p) => p.endsWith(path.join('big', 'state.json'))), '大きすぎるものは readFile しない');
  });
});

test('D0019-AC-01: ログは「final が無く、archive でない run」だけ読む（行の状態に要るため）。final のある run と archive は state.json だけ', async () => {
  await withRealTempDir(async (dir) => {
    const log = logText([promptLine('requirements'), assistantText('書く')]);
    const finishedLog = logText([promptLine('requirements'), resultLine()]);
    await putRun(dir, 'live', stateJson({ pipe: 'live', runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }));
    await putRun(dir, 'done', stateJson({ pipe: 'done', final: 'PASSED' }));
    await putRun(dir, 'archive/20261016-090000', stateJson({ runs: [] }));
    for (const rel of ['live', 'done', 'archive/20261016-090000']) {
      await mkdir(path.join(dir, rel, 'logs'));
      await writeFile(path.join(dir, rel, 'logs', '01_requirements.jsonl'), rel === 'live' ? log : finishedLog);
      await writeFile(path.join(dir, rel, 'logs', 'notes.jsonl'), 'x');
    }
    const rec = recordingFs();
    const found = await listPlaceRuns(dir, { archiveLimit: 10, fs: rec.fs });
    const live = found.runs.find((r) => r.id === 'live')!;
    assert.deepEqual(live.stageLogs.map((l) => l.fileName), ['01_requirements.jsonl'], '名前の読めるログだけ（notes.jsonl は読まない）');
    assert.equal(live.stageLogs[0]!.text, log);
    assert.deepEqual(found.runs.find((r) => r.id === 'done')!.stageLogs, []);
    assert.deepEqual(found.runs.find((r) => r.id === 'archive/20261016-090000')!.stageLogs, []);
    assert.ok(!rec.paths().some((p) => p.includes(`${path.sep}done${path.sep}logs`)), 'final のある run の logs/ は開かない');
    assert.ok(!rec.paths().some((p) => p.includes(`${path.sep}archive${path.sep}`) && p.includes(`${path.sep}logs`)), 'archive の logs/ は開かない');
  });
});

test('D0019-AC-32: 場所の中を読むときに触れるのは work_dir の下だけで、書き込みの関数は呼ばない（偽の fs には読む 5 つしか無い）', async () => {
  await withRealTempDir(async (dir) => {
    const work = path.join(dir, 'work');
    await putRun(work, '', stateJson({ pipe: 'dev', runs: [] }));
    await putRun(work, 'diagrams', stateJson({ pipe: 'diagrams' }));
    await putRun(work, 'archive/20261016-090000', stateJson({ final: 'PASSED' }));
    await writeFile(path.join(dir, 'outside.txt'), 'x');
    const rec = recordingFs();
    await listPlaceRuns(work, { archiveLimit: 10, fs: rec.fs });
    assert.ok(rec.calls.length > 0, '偽の fs を通して読んでいる');
    assert.deepEqual(rec.paths().filter((p) => p !== work && !p.startsWith(work + path.sep)), []);
  });
});

test('D0019-AC-11: archive/<日時> を開くと、図・出力・成果物が、直下の記録と同じ形で読める', async () => {
  await withRealTempDir(async (dir) => {
    const record = stateJson({ final: 'PASSED', runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] });
    const log = logText([promptLine('requirements'), assistantText('書いた'), resultLine()]);
    const archived = path.join(dir, 'archive', '20261017-100000');
    for (const home of [dir, archived]) {
      await mkdir(path.join(home, 'logs'), { recursive: true });
      await writeFile(path.join(home, 'state.json'), record);
      await writeFile(path.join(home, 'logs', '01_requirements.jsonl'), log);
      await writeFile(path.join(home, '00_input.md'), 'メモ');
      await writeFile(path.join(home, '01_requirements.md'), '要件');
      await writeFile(path.join(home, 'other.md'), '一覧の外');
    }
    const here = await fsSource.createFsWorkDirSource(dir, 'docs/pipeline').read();
    const old = await fsSource.createFsWorkDirSource(archived, 'docs/pipeline').read();
    assert.deepEqual(old, here, 'archive/<日時> の写しは、直下の写しと同じ形');
    assert.deepEqual(Object.keys(old.artifacts).sort(), ['00_input.md', '01_requirements.md']);
    assert.equal(old.stageLogs.length, 1);
  });
});

test('D0019-AC-11: archive/<日時> を選ぶと logs/ も読め、時系列（gantt）が直下の記録と同じ形で出る（時刻の入った段のログから）', async () => {
  const { buildPipelineView } = await import('../domain/pipelineView.ts');
  const { clockAt } = await import('../test/liveFixtures.ts');
  await withRealTempDir(async (dir) => {
    const record = stateJson({
      final: 'PASSED',
      startedAt: '2026-10-17T10:00:00',
      updatedAt: '2026-10-17T10:01:00',
      runs: [stageRunEntry({ stage: 'requirements', seq: 1, durationSec: 30 })],
    });
    const log = logText([promptLine('requirements', '2026-10-17T10:00:05+00:00'), assistantText('書いた'), resultLine()]);
    const archived = path.join(dir, 'archive', '20261017-100000');
    for (const home of [dir, archived]) {
      await mkdir(path.join(home, 'logs'), { recursive: true });
      await writeFile(path.join(home, 'state.json'), record);
      await writeFile(path.join(home, 'logs', '01_requirements.jsonl'), log);
    }
    const clock = clockAt(300);
    const here = buildPipelineView(await fsSource.createFsWorkDirSource(dir, 'docs/pipeline').read(), clock).gantt;
    const old = buildPipelineView(await fsSource.createFsWorkDirSource(archived, 'docs/pipeline').read(), clock).gantt;
    assert.equal(here.rows.length, 1);
    assert.equal(here.hasTimes, true);
    assert.deepEqual(old, here, 'archive/<日時> の時系列は、直下と同じ形');
  });
});

// ---- 2版目：名前の無い記録だけ、00_input.md の先頭を読む（AC-52・AC-54）----

type RunWithMemo = PlaceRun & { memoHead: string | null };
const memoOf = (r: PlaceRuns, id: string): string | null | undefined => (r.runs.find((x) => x.id === id) as RunWithMemo | undefined)?.memoHead;

async function writeInput(dir: string, rel: string, text: string): Promise<void> {
  await mkdir(path.join(dir, rel), { recursive: true });
  await writeFile(path.join(dir, rel, '00_input.md'), text);
}

test('D0019-AC-54: 名前（name）の無い run だけ、その run のフォルダの 00_input.md の先頭を memoHead に入れる（直下・パイプ・archive/<日時>）', async () => {
  await withRealTempDir(async (dir) => {
    await putRun(dir, '', stateJson({ pipe: 'dev' }));
    await putRun(dir, 'survey', stateJson({ pipe: 'survey' }));
    await putRun(dir, 'archive/20261016-090000', stateJson({ final: 'PASSED' }));
    await writeInput(dir, '', '# 仕様の QA を回す\n本文\n');
    await writeInput(dir, 'survey', '調べる\n');
    await writeInput(dir, 'archive/20261016-090000', '# 前の題\n');
    const found = await listPlaceRuns(dir, { archiveLimit: 10 });
    assert.equal(memoOf(found, ''), '# 仕様の QA を回す\n本文\n');
    assert.equal(memoOf(found, 'survey'), '調べる\n');
    assert.equal(memoOf(found, 'archive/20261016-090000'), '# 前の題\n');
  });
});

test('D0019-AC-54: name が state.json にある run では 00_input.md を読まない（memoHead は null）。読んだパスは名前の無い run のものだけ', async () => {
  await withRealTempDir(async (dir) => {
    await putRun(dir, '', stateJson({ pipe: 'dev', name: '付けた名前' }));
    await putRun(dir, 'survey', stateJson({ pipe: 'survey' }));
    await putRun(dir, 'archive/20261016-090000', stateJson({ final: 'PASSED', name: '前の名前' }));
    for (const rel of ['', 'survey', 'archive/20261016-090000']) await writeInput(dir, rel, '# 題\n');
    const rec = recordingFs();
    const found = await listPlaceRuns(dir, { archiveLimit: 10, fs: rec.fs });
    assert.equal(memoOf(found, ''), null);
    assert.equal(memoOf(found, 'archive/20261016-090000'), null);
    assert.equal(memoOf(found, 'survey'), '# 題\n');
    assert.deepEqual(rec.paths('readHead'), [path.join(dir, 'survey', '00_input.md')]);
  });
});

test('D0019-AC-54: 00_input.md を読む口は、run のフォルダの中の 00_input.md の 1 つだけで、先頭の 4096 バイトまで。全部を readFile で読まない', async () => {
  await withRealTempDir(async (dir) => {
    await putRun(dir, '', stateJson({}));
    await putRun(dir, 'big', stateJson({ pipe: 'big' }));
    await putRun(dir, 'archive/20261016-090000', stateJson({ final: 'PASSED' }));
    await writeInput(dir, '', 'x');
    await writeInput(dir, 'big', 'a'.repeat(10_000));
    await writeInput(dir, 'archive/20261016-090000', 'y');
    await writeFile(path.join(dir, 'other.md'), '読まない');
    const rec = recordingFs();
    const found = await listPlaceRuns(dir, { archiveLimit: 10, fs: rec.fs });
    assert.equal(memoOf(found, 'big'), 'a'.repeat(4096), '先頭の 4096 バイトだけ');
    assert.deepEqual(rec.paths('readHead').sort(), [
      path.join(dir, '00_input.md'),
      path.join(dir, 'archive', '20261016-090000', '00_input.md'),
      path.join(dir, 'big', '00_input.md'),
    ].sort());
    for (const call of rec.calls.filter((c) => c.op === 'readHead')) {
      assert.ok(call.maxBytes !== undefined && call.maxBytes > 0 && call.maxBytes <= 4096, `maxBytes ${String(call.maxBytes)}`);
    }
    assert.ok(!rec.paths('readFile').some((p) => p.endsWith('00_input.md')), '00_input.md を全部は読まない');
    assert.ok(!rec.paths().some((p) => p.endsWith('other.md')), 'ほかのファイルは読まない');
    assert.deepEqual(rec.paths().filter((p) => p !== dir && !p.startsWith(dir + path.sep)), [], 'work_dir の外は読まない');
  });
});

test('D0019-AC-52: 00_input.md が無い・フォルダ・読めないときも、memoHead は null で例外を出さず、run は残る', async () => {
  await withRealTempDir(async (dir) => {
    await putRun(dir, '', stateJson({}));
    await putRun(dir, 'isdir', stateJson({ pipe: 'isdir' }));
    await mkdir(path.join(dir, 'isdir', '00_input.md'));
    await putRun(dir, 'missing', stateJson({ pipe: 'missing' }));
    const found = await listPlaceRuns(dir, { archiveLimit: 10 });
    assert.deepEqual(idsOf(found).sort(), ['', 'isdir', 'missing']);
    for (const id of ['', 'isdir', 'missing']) assert.equal(memoOf(found, id), null, id);
  });
});

test('D0019-AC-54: 読む口 readHead は 先頭の maxBytes バイトだけ返し、ファイルを変えず、無いファイルを作らない（開き方は読み取りだけ）', async () => {
  const { nodeReadOnlyFs } = await import('./readOnlyFs.ts');
  const { readFile: read, stat: statFile } = await import('node:fs/promises');
  await withRealTempDir(async (dir) => {
    const file = path.join(dir, '00_input.md');
    await writeFile(file, `${'a'.repeat(5000)}${'b'.repeat(5000)}`);
    const before = await statFile(file);
    const head = await nodeReadOnlyFs.readHead(file, 4096);
    assert.equal(head, 'a'.repeat(4096));
    assert.equal(await nodeReadOnlyFs.readHead(file, 10_000_000), `${'a'.repeat(5000)}${'b'.repeat(5000)}`, '上限より短いファイルは全部');
    const after = await statFile(file);
    assert.equal(after.mtimeMs, before.mtimeMs);
    assert.equal(after.size, before.size);
    assert.equal(await read(file, 'utf8'), `${'a'.repeat(5000)}${'b'.repeat(5000)}`);
    const missing = path.join(dir, 'nothing.md');
    await assert.rejects(nodeReadOnlyFs.readHead(missing, 100));
    assert.equal(existsSync(missing), false, '無いファイルを作らない');
  });
});

// ---- 場所（いまの work_dir と別の worktree）を RunsSource にする ----

interface PlaceInfo {
  key: string;
  label: string | null;
  workDirAbs: string;
}
interface RunsSourceLike {
  places(showOthers: boolean): Promise<{ places: PlaceInfo[]; omittedWorktrees: number }>;
  runs(place: PlaceInfo): Promise<PlaceRuns>;
}
type CreateFsRunsSource = (workspaceRoot: string, workDirAbs: string, setting: string, opts?: { fs?: unknown }) => RunsSourceLike;
const createFsRunsSource: CreateFsRunsSource = (...args) =>
  (fsSource as unknown as { createFsRunsSource: CreateFsRunsSource }).createFsRunsSource(...args);

test('D0019-AC-15: createFsRunsSource は、いまの work_dir を先頭に、別の worktree の場所を並べる。showOthers=false なら、いまの work_dir だけ', async () => {
  await withRealTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-x', branch: 'feat/x' }]);
    const here = path.join(repo.mainRoot, 'docs', 'pipeline');
    const source = createFsRunsSource(repo.mainRoot, here, 'docs/pipeline');

    const all = await source.places(true);
    // 2版目：いまの work_dir の場所にも、いまの checkout のブランチ名（主の checkout の HEAD は main）が入る
    assert.deepEqual(all.places.map((p) => [p.key, p.label, p.workDirAbs]), [
      ['here', 'main', here],
      ['wt.feat-x', 'feat/x', path.join(repo.roots['feat-x']!, 'docs', 'pipeline')],
    ]);
    assert.equal(all.omittedWorktrees, 0);

    const only = await source.places(false);
    assert.deepEqual(only.places.map((p) => p.key), ['here']);
    assert.equal(only.omittedWorktrees, 0);
  });
});

test('D0019-AC-03: git の外のワークスペースでは、いまの work_dir の場所のブランチ名が null（項目ごと省く）。showOthers=false でも同じ', async () => {
  await withRealTempDir(async (base) => {
    const work = path.join(base, 'plain', 'docs', 'pipeline');
    await putRun(work, '', stateJson({ pipe: 'dev' }));
    const source = createFsRunsSource(path.join(base, 'plain'), work, 'docs/pipeline');
    for (const showOthers of [true, false]) {
      const found = await source.places(showOthers);
      assert.deepEqual(found.places.map((p) => [p.key, p.label]), [['here', null]]);
    }
  });
});

test('D0019-AC-03: ワークスペースが linked worktree のとき、いまの work_dir の場所のブランチ名は、その worktree のブランチ', async () => {
  await withRealTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-x', branch: 'feat/x' }]);
    const root = repo.roots['feat-x']!;
    const here = path.join(root, 'docs', 'pipeline');
    const found = await createFsRunsSource(root, here, 'docs/pipeline').places(true);
    assert.deepEqual(found.places.map((p) => [p.key, p.label]), [['here', 'feat/x'], ['main', 'main']]);
  });
});

test('D0019-AC-15: runs(place) はその場所の work_dir の run を読む（別の worktree の run がいまの work_dir の run と別に出る）', async () => {
  await withRealTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-x', branch: 'feat/x', state: stateJson({ pipe: 'spec-qa', updatedAt: '2026-10-17T12:00:00' }) }]);
    const here = path.join(repo.mainRoot, 'docs', 'pipeline');
    const source = createFsRunsSource(repo.mainRoot, here, 'docs/pipeline');
    const { places } = await source.places(true);
    const mine = await source.runs(places[0]!);
    const theirs = await source.runs(places[1]!);
    assert.deepEqual(idsOf(mine), ['']);
    assert.deepEqual(idsOf(theirs), ['']);
    assert.match(theirs.runs[0]!.stateJson ?? '', /spec-qa/);
    assert.match(mine.runs[0]!.stateJson ?? '', /PASSED/);
  });
});

test('D0019-AC-20: 別の worktree の run を選ぶと、記録から作った成果物の一覧のものだけ読む（一覧の外のファイル・../ の出力は読まない）', async () => {
  await withRealTempDir(async (base) => {
    const evil = [...DIAGRAMS_STAGES, { name: 'evil', label: '外', output: '../secret.md', review: false }];
    const repo = await makeRepo(base, [{ name: 'feat-x', state: stateJson({ pipe: 'diagrams', stages: evil }) }]);
    const root = repo.roots['feat-x']!;
    const work = path.join(root, 'docs', 'pipeline');
    await writeFile(path.join(work, '00_input.md'), 'メモ');
    await writeFile(path.join(work, '01_survey.md'), '調査');
    await writeFile(path.join(root, 'docs', 'secret.md'), '外のファイル');

    const source = createFsRunsSource(repo.mainRoot, path.join(repo.mainRoot, 'docs', 'pipeline'), 'docs/pipeline');
    const wt = (await source.places(true)).places.find((p) => p.key === 'wt.feat-x');
    assert.ok(wt, '別の worktree の場所が見つかる');
    const snap = await fsSource.createFsWorkDirSource(wt.workDirAbs, wt.workDirAbs).read();
    assert.deepEqual(Object.keys(snap.artifacts).sort(), ['00_input.md', '01_survey.md']);
    assert.ok(!JSON.stringify(snap).includes('外のファイル'));
    assert.ok(!JSON.stringify(snap).includes('worktree の他のファイル'), 'README など worktree の他のファイルは読まない');
  });
});

test('D0019-AC-15: 読み取りは変更を起こさない（場所の中を読んだあとも、work_dir の更新時刻が変わらない）', async () => {
  await withRealTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-x' }]);
    const here = path.join(repo.mainRoot, 'docs', 'pipeline');
    const pinned = new Date('2026-10-01T00:00:00Z');
    for (const d of [here, path.join(here, 'state.json')]) await utimes(d, pinned, pinned);
    const before = (await stat(here)).mtimeMs;
    const source = createFsRunsSource(repo.mainRoot, here, 'docs/pipeline');
    for (const p of (await source.places(true)).places) await source.runs(p);
    assert.equal((await stat(here)).mtimeMs, before);
  });
});
