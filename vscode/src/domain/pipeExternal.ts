// 外で書き換わったパイプを読み直すかの判断（D0065）。純粋な関数と、拡張 → パネルの知らせの型だけ。
import { pipeFiles } from './pipeModel.ts';
import type { PipeModel } from './pipeModel.ts';
import type { DiffItem } from './pipeDiff.ts';
import type { VersionEntry } from './pipeVersions.ts';

export type ExternalVerdict = 'none' | 'reload' | 'choose';
export type ExternalNotice =
  | { type: 'externalReloaded'; model: PipeModel; savedNames: string[]; cause: 'auto' | 'chosen'; versions: VersionEntry[] | null }
  | { type: 'externalConflict'; diff: DiffItem[] }
  | { type: 'externalKept'; savedNames: string[] }
  | { type: 'externalUnreadable'; reason: string }
  | { type: 'externalResolved' };

/** パイプのフォルダの中の相対パスが、見るべきファイルか（pipe.toml・layout.json・prompts/ 直下の .md） */
export function isWatchedRel(rel: string): boolean {
  const p = rel.replace(/\\/g, '/');
  if (p === 'pipe.toml' || p === 'layout.json') return true;
  return /^prompts\/[^/]+\.md$/.test(p) && p !== 'prompts/.md';
}

/** ファイルの組が同じか（キーと中身。順番は問わない） */
export function sameFiles(a: Record<string, string>, b: Record<string, string>): boolean {
  const ka = Object.keys(a), kb = Object.keys(b);
  return ka.length === kb.length && ka.every((k) => Object.hasOwn(b, k) && a[k] === b[k]);
}

/** 読んで作り直したファイルの組どうしを比べる。同じ → none、違って dirty でない → reload、違って dirty → choose */
export function judgeExternal(saved: PipeModel, disk: PipeModel, dirty: boolean): ExternalVerdict {
  if (sameFiles(pipeFiles(saved), pipeFiles(disk))) return 'none';
  return dirty ? 'choose' : 'reload';
}
