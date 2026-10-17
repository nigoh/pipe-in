// 保存した版：作業台で保存したときの形を、拡張の保存場所に残す。ここは id とファイル名の決まり・並び・残す数だけ（純粋な関数）。
// id は保存した時刻（ms・13桁）。パネルを閉じたときの、保存していない下書きには -draft をつける。

export interface VersionEntry { id: string; savedAt: number; draft: boolean }

export const VERSION_LIMIT = 50;
const ID_RE = /^(\d{13})(-draft)?$/;

export const isVersionId = (id: string): boolean => ID_RE.test(id);
export const versionId = (savedAt: number, draft: boolean): string => `${savedAt}${draft ? '-draft' : ''}`;
export const versionFile = (id: string): string => `${id}.json`;

/** ファイル名（<id>.json）から版を読む。形の違うファイルは null */
export function versionFromFile(file: string): VersionEntry | null {
  if (!file.endsWith('.json')) return null;
  const id = file.slice(0, -'.json'.length), hit = ID_RE.exec(id);
  return hit ? { id, savedAt: Number(hit[1]), draft: hit[2] !== undefined } : null;
}

/** 新しい順 */
export const sortVersions = (list: readonly VersionEntry[]): VersionEntry[] =>
  [...list].sort((a, b) => b.savedAt - a.savedAt || (a.draft === b.draft ? 0 : a.draft ? -1 : 1));

/** 残す数を超えた分（古いほうから）の id */
export const versionsToDrop = (list: readonly VersionEntry[], limit = VERSION_LIMIT): string[] => sortVersions(list).slice(limit).map((v) => v.id);
