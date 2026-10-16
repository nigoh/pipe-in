// 実行の候補：work_dir 直下（開発フロー）と <work_dir>/<パイプ名>/（パイプ）の記録。どれを見るかを選ぶ。
import path from 'node:path';
import { isJsonObject } from './json.ts';
import { isStageName } from './stage.ts';

export interface RunCandidate {
  /** 直下なら ''、パイプならフォルダ名 */
  id: string;
  label: string;
  /** state.json の updated_at。読めなければ null */
  updatedAt: string | null;
}

export const ROOT_RUN_ID = '';
const DEV_LABEL = '開発フロー';
// 記録の置き場所の中で、パイプのフォルダにならない名前（devpipe の RESERVED_NAMES）
const RESERVED = new Set(['logs']);

/** パイプのフォルダ名として使えるか（パイプの名前と同じ規則。logs は除く）。 */
export function isRunFolderName(name: string): boolean {
  return isStageName(name) && !RESERVED.has(name);
}

/** 候補1つ。名前は記録の pipe から（開発フローは「開発フロー」）。読めない記録でも例外を投げない。 */
export function describeRun(id: string, stateJson: string | null): RunCandidate {
  let data: unknown = null;
  try {
    data = stateJson === null ? null : JSON.parse(stateJson);
  } catch {
    data = null;
  }
  const state = isJsonObject(data) ? data : {};
  const pipe = typeof state.pipe === 'string' && state.pipe !== '' ? state.pipe : null;
  const label = pipe === null || pipe === 'dev' ? (id === ROOT_RUN_ID ? DEV_LABEL : id) : pipe;
  return { id, label, updatedAt: typeof state.updated_at === 'string' ? state.updated_at : null };
}

/** 見る実行。選んだもの（selected）が候補にあればそれ、なければ updated_at のいちばん新しいもの（同じなら直下・前のもの）。 */
export function pickRun(candidates: readonly RunCandidate[], selected: string | null): string {
  if (selected !== null && candidates.some((c) => c.id === selected)) return selected;
  let best: RunCandidate | null = null;
  for (const c of candidates) {
    if (best === null) {
      best = c;
      continue;
    }
    // ISO 8601 の文字列は、そのまま比べれば時刻の順になる
    if (c.updatedAt !== null && (best.updatedAt === null || c.updatedAt > best.updatedAt)) best = c;
  }
  if (best === null) return ROOT_RUN_ID;
  const root = candidates.find((c) => c.id === ROOT_RUN_ID);
  return root !== undefined && root.updatedAt === best.updatedAt ? ROOT_RUN_ID : best.id;
}

/** 候補のフォルダの絶対パス。候補にない id、フォルダ名として正しくない id は null。 */
export function resolveRunDir(workDirAbs: string, id: string, candidates: readonly RunCandidate[]): string | null {
  if (!candidates.some((c) => c.id === id)) return null;
  if (id === ROOT_RUN_ID) return workDirAbs;
  return isRunFolderName(id) ? path.join(workDirAbs, id) : null;
}
