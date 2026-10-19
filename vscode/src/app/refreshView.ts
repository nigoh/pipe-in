// 図の状態を作り直すユースケースと、その口。
import path from 'node:path';
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { PipelineView, ViewClock, WorkDirSnapshot } from '../domain/pipelineView.ts';

/** ドメインが求める口：work_dir の記録の写しを返す。読めないものは「ない」として写しに入れ、例外を投げない。 */
export interface WorkDirSource {
  read(): Promise<WorkDirSnapshot>;
}

/** 写しを読んで図の状態を作る。口が例外を投げたら、空の写し（workDir だけ入れたもの）で組み立てる。clock は「今」（入口が作って渡す）。 */
export async function refreshView(source: WorkDirSource, workDirForDisplay: string, clock?: ViewClock): Promise<PipelineView> {
  let snapshot: WorkDirSnapshot;
  try {
    snapshot = await source.read();
  } catch {
    snapshot = { workDir: workDirForDisplay, stateJson: null, stageLogs: [], artifacts: {} };
  }
  return buildPipelineView(snapshot, clock);
}

export const DEFAULT_WORK_DIR = 'docs/pipeline';

/** 設定値を、ワークスペースの最初のフォルダからの絶対パスにする。設定が空なら既定の 'docs/pipeline'。 */
export function resolveWorkDir(workspaceRoot: string, setting: string | undefined): string {
  const value = setting?.trim() ? setting.trim() : DEFAULT_WORK_DIR;
  return path.resolve(workspaceRoot, value);
}
