// 実行の候補：work_dir 直下（開発フロー）と <work_dir>/<パイプ名>/（パイプ）の記録。どれを見るかを選ぶ。
// 実行の目印（RunKey）：<場所>|<id>。場所は here（いまの work_dir）・main（主の checkout）・wt.<登録名>（別の worktree）。
// id は ''（直下）・パイプ名・archive/<日時>。パネルや覚えた値から来る文字は、ここで形を検めてから使う。
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
/** 前の開発フローの記録の移し先（本体の pipe-in record start が作る） */
export const ARCHIVE_DIR = 'archive';
// 記録の置き場所の中で、パイプのフォルダにならない名前。logs は本体の RESERVED_NAMES と同じ。
// archive は拡張の側だけで予約する（本体の変更は対象外。パイプ名 archive を本体が止めていないのは残る課題）
const RESERVED = new Set(['logs', ARCHIVE_DIR]);
/** フォルダ名・登録名の長さの上限（長すぎる値をパスに使わない） */
const MAX_NAME = 100;

/** パイプのフォルダ名として使えるか（パイプの名前と同じ規則。logs・archive は除く）。 */
export function isRunFolderName(name: string): boolean {
  return isStageName(name) && name.length <= MAX_NAME && !RESERVED.has(name);
}

const ARCHIVE_ID = /^archive\/(\d{8}-\d{6}(?:-\d+)?)$/;

/** archive の run の id（archive/<日時>。重なると -2 が付く）か。 */
export function isArchiveId(id: unknown): id is string {
  return typeof id === 'string' && ARCHIVE_ID.test(id);
}

/** archive の id から日時（20261017-100000 や 20261017-100000-2）。archive の id でなければ null。 */
export function archiveStamp(id: unknown): string | null {
  return typeof id === 'string' ? (ARCHIVE_ID.exec(id)?.[1] ?? null) : null;
}

/** 場所の目印。'here'・'main'・'wt.<登録名>' */
export type PlaceKey = string;
export const HERE: PlaceKey = 'here';
export const MAIN: PlaceKey = 'main';
const PLACE_KEY = /^(?:here|main|wt\.[A-Za-z0-9._-]{1,100})$/;

/** 実行の目印。<場所>|<id> */
export type RunKey = string;

export function makeRunKey(place: PlaceKey, id: string): RunKey {
  return `${place}|${id}`;
}

function isRunId(id: string): boolean {
  return id === ROOT_RUN_ID || isRunFolderName(id) || isArchiveId(id);
}

/** 実行の目印を場所と id に分ける。形が違えば（文字でない・区切りが無い・場所や id が規則に合わない）null。 */
export function parseRunKey(key: unknown): { place: PlaceKey; id: string } | null {
  if (typeof key !== 'string') return null;
  const at = key.indexOf('|');
  if (at === -1) return null;
  const place = key.slice(0, at);
  const id = key.slice(at + 1);
  return PLACE_KEY.test(place) && isRunId(id) ? { place, id } : null;
}

export function isRunKey(key: unknown): key is RunKey {
  return parseRunKey(key) !== null;
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
