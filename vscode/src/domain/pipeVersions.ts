// 保存した版：作業台で保存したときの形を、拡張の保存場所に残す。ここは id とファイル名の決まり・並び・残す数だけ（純粋な関数）。
// id は保存した時刻（ms・13桁）。パネルを閉じたときの、保存していない下書きには -draft をつける。

// 外で書き換わる前の形には -external をつける（D0065）。
export type VersionKind = 'saved' | 'draft' | 'external';
/** external は外の変更の版だけに付ける（無ければ付けない） */
export interface VersionEntry { id: string; savedAt: number; draft: boolean; external?: true }

export const VERSION_LIMIT = 50;
const ID_RE = /^(\d{13})(-draft|-external)?$/;

export const isVersionId = (id: string): boolean => ID_RE.test(id);
/** boolean は今まで通り（true = 下書き） */
export const versionId = (savedAt: number, kind: boolean | VersionKind): string => {
  const k: VersionKind = kind === true ? 'draft' : kind === false ? 'saved' : kind;
  return `${savedAt}${k === 'draft' ? '-draft' : k === 'external' ? '-external' : ''}`;
};
export const versionFile = (id: string): string => `${id}.json`;

/** ファイル名（<id>.json）から版を読む。形の違うファイルは null */
export function versionFromFile(file: string): VersionEntry | null {
  if (!file.endsWith('.json')) return null;
  const id = file.slice(0, -'.json'.length), hit = ID_RE.exec(id);
  if (!hit) return null;
  const base = { id, savedAt: Number(hit[1]), draft: hit[2] === '-draft' };
  return hit[2] === '-external' ? { ...base, external: true } : base;
}

// 同じ時刻の並び：下書き → 外 → 保存
const rank = (v: VersionEntry): number => (v.draft ? 0 : v.external ? 1 : 2);

/** 新しい順 */
export const sortVersions = (list: readonly VersionEntry[]): VersionEntry[] =>
  [...list].sort((a, b) => b.savedAt - a.savedAt || rank(a) - rank(b));

/** 残す数を超えた分（古いほうから）の id */
export const versionsToDrop = (list: readonly VersionEntry[], limit = VERSION_LIMIT): string[] => sortVersions(list).slice(limit).map((v) => v.id);
