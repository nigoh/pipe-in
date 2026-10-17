// 検証の段で足したテスト：基盤 createFsWorkDirSource（FR-02・FR-03・FR-11・非機能（読み取り専用））。
// 一時フォルダに記録を作って読ませる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readdir, rm, stat, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createFsWorkDirSource } from './fsWorkDirSource.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { assistantText, logText, promptLine, stageRunEntry, stateJson } from '../test/fixtures.ts';

async function listAll(dir: string): Promise<string[]> {
  const out: string[] = [];
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, e.name);
    out.push(full);
    if (e.isDirectory()) out.push(...(await listAll(full)));
  }
  return out.sort();
}

test('FR-02/03/11: state.json・名前の読めるログ・7つの成果物だけを写しに入れ、work_dir に書き込まない', async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'pipe-in-vscode-'));
  try {
    await mkdir(path.join(dir, 'logs'));
    await writeFile(path.join(dir, 'state.json'), stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }));
    await writeFile(path.join(dir, 'logs', '02_design.jsonl'), logText([promptLine('design'), assistantText('A')]));
    await writeFile(path.join(dir, 'logs', 'notes.jsonl'), 'x');
    await writeFile(path.join(dir, 'logs', 'README.md'), 'x');
    await writeFile(path.join(dir, '00_input.md'), 'メモ');
    await writeFile(path.join(dir, '01_requirements.md'), '要件');
    await writeFile(path.join(dir, 'other.md'), 'ほか');

    const before = await listAll(dir);
    const mtimes = await Promise.all(before.map(async (f) => (await stat(f)).mtimeMs));

    const snap = await createFsWorkDirSource(dir, '表示用').read();
    assert.equal(snap.workDir, '表示用');
    assert.ok(snap.stateJson?.includes('"requirements"'));
    assert.deepEqual(snap.stageLogs.map((l) => l.fileName), ['02_design.jsonl']);
    assert.deepEqual(Object.keys(snap.artifacts).sort(), ['00_input.md', '01_requirements.md']);

    const view = buildPipelineView(snap);
    assert.equal(view.runningStage, 'design');

    // 読み取り専用：ファイルが増えず、更新時刻も変わらない
    const after = await listAll(dir);
    assert.deepEqual(after, before);
    const mtimesAfter = await Promise.all(after.map(async (f) => (await stat(f)).mtimeMs));
    assert.deepEqual(mtimesAfter, mtimes);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('FR-14: work_dir が存在しなくても例外を出さず、空の写し（記録なしの表示）になる', async () => {
  const missing = path.join(os.tmpdir(), `pipe-in-vscode-missing-${process.pid}-${Date.now()}`);
  const snap = await createFsWorkDirSource(missing, missing).read();
  assert.deepEqual(snap, { workDir: missing, stateJson: null, stageLogs: [], artifacts: {} });
  assert.deepEqual(buildPipelineView(snap).noRecords, { message: '記録がありません', workDir: missing });
});
