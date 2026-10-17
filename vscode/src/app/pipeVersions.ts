// 保存した版の記録・一覧・読み込み。置き場所は口 VersionStore の向こう（infra/fsVersions.ts。拡張の保存場所の中だけ）。
// プロジェクトには何も書かない。パネルから来た id は、一覧にあるときだけ読む。
import { isPipeModel } from '../domain/pipeModel.ts';
import type { PipeModel } from '../domain/pipeModel.ts';
import { isVersionId, sortVersions, versionFile, versionFromFile, versionId, versionsToDrop } from '../domain/pipeVersions.ts';
import type { VersionEntry } from '../domain/pipeVersions.ts';

/** 版の置き場所の中の pipe-in-<名前>/ を読み書きする口。pipe はフォルダの名前、file は <id>.json */
export interface VersionStore {
  list(pipe: string): Promise<string[]>;
  read(pipe: string, file: string): Promise<string | null>;
  write(pipe: string, file: string, text: string): Promise<void>;
  remove(pipe: string, file: string): Promise<void>;
}

// 版のフォルダは名前ごとに1つ（パイプが前の版のフォルダ名でも、版は新しい名前で残す。拡張の保存場所は前の版から引き継がない）
const folder = (name: string): string => `pipe-in-${name}`;

export async function listVersions(store: VersionStore, name: string): Promise<VersionEntry[]> {
  const files = await store.list(folder(name));
  return sortVersions(files.map(versionFromFile).filter((v): v is VersionEntry => v !== null));
}

/** 版を1つ足し、残す数を超えた古い版を消して、新しい順の一覧を返す（savedAt は呼んだ側の時計） */
export async function recordVersion(store: VersionStore, m: PipeModel, savedAt: number, draft = false): Promise<VersionEntry[]> {
  await store.write(folder(m.name), versionFile(versionId(savedAt, draft)), JSON.stringify(m));
  const list = await listVersions(store, m.name);
  const drop = new Set(versionsToDrop(list));
  for (const id of drop) await store.remove(folder(m.name), versionFile(id));
  return list.filter((v) => !drop.has(v.id));
}

/** 一覧にある版だけを読み、形を確かめて、名前はこのパイプに直す。読めなければ null */
export async function readVersion(store: VersionStore, name: string, id: string): Promise<PipeModel | null> {
  if (!isVersionId(id) || !(await listVersions(store, name)).some((v) => v.id === id)) return null;
  const text = await store.read(folder(name), versionFile(id));
  if (text === null) return null;
  try {
    const v: unknown = JSON.parse(text);
    return isPipeModel(v) ? { ...v, name } : null;
  } catch {
    return null;
  }
}
