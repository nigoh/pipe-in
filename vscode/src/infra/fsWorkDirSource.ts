// WorkDirSource の実装：node:fs/promises で work_dir を読む。書き込みは一切しない。
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import type { WorkDirSource } from '../app/refreshView.ts';
import { ARTIFACT_NAMES } from '../domain/artifacts.ts';
import type { ArtifactName } from '../domain/artifacts.ts';
import type { WorkDirSnapshot } from '../domain/pipelineView.ts';
import { parseStageLogName } from '../domain/stageLog.ts';

/** 読めなければ null（ない・権限がない・途中で消えた）。 */
async function readText(file: string): Promise<string | null> {
  try {
    return await readFile(file, 'utf8');
  } catch {
    return null;
  }
}

async function readStageLogs(logsDir: string): Promise<WorkDirSnapshot['stageLogs']> {
  let names: string[];
  try {
    names = await readdir(logsDir);
  } catch {
    return [];
  }
  const logs: WorkDirSnapshot['stageLogs'] = [];
  for (const fileName of names.filter((n) => parseStageLogName(n) !== null)) {
    const text = await readText(path.join(logsDir, fileName));
    if (text !== null) logs.push({ fileName, text });
  }
  return logs;
}

/** state.json、logs/ の中で parseStageLogName が null でない *.jsonl、ARTIFACT_NAMES の7つを読む。 */
export function createFsWorkDirSource(workDirAbs: string, workDirForDisplay: string): WorkDirSource {
  return {
    async read(): Promise<WorkDirSnapshot> {
      const artifacts: Partial<Record<ArtifactName, string>> = {};
      for (const name of ARTIFACT_NAMES) {
        const text = await readText(path.join(workDirAbs, name));
        if (text !== null) artifacts[name] = text;
      }
      return {
        workDir: workDirForDisplay,
        stateJson: await readText(path.join(workDirAbs, 'state.json')),
        stageLogs: await readStageLogs(path.join(workDirAbs, 'logs')),
        artifacts,
      };
    },
  };
}
