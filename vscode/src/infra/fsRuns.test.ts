// 基盤：work_dir の中の実行の候補を見つけ、パイプの記録の成果物を読む。AC-01・AC-06。
// 一時フォルダに記録を作って読ませる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
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
