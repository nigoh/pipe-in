// WorkDirSource の実装：node:fs/promises で work_dir を読む。書き込みは一切しない。
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import type { WorkDirSource } from '../app/refreshView.ts';
import { artifactNamesFor } from '../domain/artifacts.ts';
import type { WorkDirSnapshot } from '../domain/pipelineView.ts';
import { parseRunRecord } from '../domain/runRecord.ts';
import { ROOT_RUN_ID, describeRun, isRunFolderName } from '../domain/runs.ts';
import type { RunCandidate } from '../domain/runs.ts';
import { parseStageLogName } from '../domain/stageLog.ts';

const STATE = 'state.json';

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

/**
 * work_dir の中の実行の候補：直下（state.json があるとき）と、state.json を持つ直下のフォルダ（パイプ）。
 * フォルダ名が規則に合わないもの・logs は候補にしない。1つもなければ直下だけ（記録なしの表示のため）。
 */
export async function listRunCandidates(workDirAbs: string): Promise<RunCandidate[]> {
  const found: RunCandidate[] = [];
  const rootState = await readText(path.join(workDirAbs, STATE));
  if (rootState !== null) found.push(describeRun(ROOT_RUN_ID, rootState));
  let entries: { name: string; isDirectory(): boolean }[] = [];
  try {
    entries = await readdir(workDirAbs, { withFileTypes: true });
  } catch {
    entries = [];
  }
  const folders = entries
    .filter((e) => e.isDirectory() && isRunFolderName(e.name))
    .map((e) => e.name)
    .sort();
  for (const name of folders) {
    const state = await readText(path.join(workDirAbs, name, STATE));
    if (state !== null) found.push(describeRun(name, state));
  }
  return found.length > 0 ? found : [describeRun(ROOT_RUN_ID, null)];
}

/** state.json、logs/ の中で parseStageLogName が null でない *.jsonl、記録から作った成果物の一覧のファイルを読む。 */
export function createFsWorkDirSource(workDirAbs: string, workDirForDisplay: string): WorkDirSource {
  return {
    async read(): Promise<WorkDirSnapshot> {
      const stateJson = await readText(path.join(workDirAbs, STATE));
      const artifacts: WorkDirSnapshot['artifacts'] = {};
      for (const name of artifactNamesFor(parseRunRecord(stateJson))) {
        const text = await readText(path.join(workDirAbs, name));
        if (text !== null) artifacts[name] = text;
      }
      return {
        workDir: workDirForDisplay,
        stateJson,
        stageLogs: await readStageLogs(path.join(workDirAbs, 'logs')),
        artifacts,
      };
    },
  };
}
