// 外で書き換わったパイプの読み直しの手順（D0065）：読む → 判断 → 何もしない／読み直す／選ばせる。
// ファイルにも vscode にも触れない。口（読み直し・版の置き場所・時計・パネルへの知らせ）は呼ぶ側が渡す。
// 作業台自身の保存かどうかは、旗や時計でなく、ディスクから作ったファイルの組と saved の比較で決める（domain/pipeExternal.ts）。
import { PipeLoadError } from '../domain/pipeModel.ts';
import type { PipeModel } from '../domain/pipeModel.ts';
import { diffPipes } from '../domain/pipeDiff.ts';
import { judgeExternal } from '../domain/pipeExternal.ts';
import type { ExternalNotice } from '../domain/pipeExternal.ts';
import type { VersionEntry } from '../domain/pipeVersions.ts';
import { recordVersion } from './pipeVersions.ts';
import { createWatchHolder } from './workDirWatch.ts';
import type { WatchHandle, WatchHolder } from './workDirWatch.ts';
import type { VersionStore } from './pipeVersions.ts';

/** パイプのフォルダの中で見張るファイル（domain/pipeExternal.ts の isWatchedRel と同じ 3 つ） */
export const PIPE_WATCH_GLOB = '{pipe.toml,layout.json,prompts/*.md}';
export const EXTERNAL_DEBOUNCE_MS = 300;

/** パイプのフォルダの見張りを持つ部品（作る口は extension.ts が渡す。仕組みは app/workDirWatch.ts の createWatchHolder と同じ） */
export const createPipeWatch = (o: { create: (dir: string) => WatchHandle; onEvent: () => void }): WatchHolder => createWatchHolder(o);

/**
 * 取り込む前に残す。saved を -external で、unsaved があれば -draft でも。
 * 残せなくても例外にしない。最後の一覧（版の置き場所が無い・全部失敗なら null）を返す。
 */
export async function recordBeforeTaking(versions: VersionStore | null, saved: PipeModel, unsaved: PipeModel | null, now: number): Promise<VersionEntry[] | null> {
  if (versions === null) return null;
  let list: VersionEntry[] | null = null;
  try {
    list = await recordVersion(versions, saved, now, 'external');
  } catch {
    // 版を残せなくても取り込みは止めない（保存のときと同じ）
  }
  if (unsaved !== null) {
    try {
      list = await recordVersion(versions, unsaved, now, 'draft');
    } catch {
      // 同上
    }
  }
  return list;
}

export interface ExternalDeps {
  /** ディスクから読み直す。読めなければ例外 */
  load: () => Promise<PipeModel>;
  versions: VersionStore | null;
  now: () => number;
  saved: () => PipeModel;
  /** 保存していない今の形。null なら保存していない変更なし */
  unsaved: () => PipeModel | null;
  /** 保存済みの形を差し替える（savedNames も作り直す）。unsaved は触らない */
  setSaved: (m: PipeModel) => void;
  clearUnsaved: () => void;
  post: (n: ExternalNotice) => void;
}
export interface ExternalReload {
  /** デバウンスのあとに呼ぶ */
  onDiskChanged(): Promise<void>;
  /** パネルの選び。待たせている外の形が無ければ何もしない */
  choose(choice: 'load' | 'keep'): Promise<void>;
  /** 作業台の保存が済んだ。待たせている外の形と、途中の読み直しの結果を捨てる */
  onSaved(): void;
  dispose(): void;
}

export function createExternalReload(deps: ExternalDeps): ExternalReload {
  let generation = 0; // 保存・閉じたときに進める。進んでいたら、途中の読み直しの結果は捨てる
  let pending: PipeModel | null = null; // 選ばせている外の形
  let bannerShown = false;
  const names = (m: PipeModel): string[] => m.stages.map((s) => s.name);

  async function take(disk: PipeModel, unsaved: PipeModel | null, cause: 'auto' | 'chosen'): Promise<void> {
    const versions = await recordBeforeTaking(deps.versions, deps.saved(), unsaved, deps.now());
    deps.setSaved(disk);
    if (cause === 'chosen') deps.clearUnsaved();
    pending = null;
    bannerShown = false;
    deps.post({ type: 'externalReloaded', model: disk, savedNames: names(disk), cause, versions });
  }

  return {
    async onDiskChanged() {
      const gen = generation;
      let disk: PipeModel;
      try {
        disk = await deps.load();
      } catch (e) {
        if (gen !== generation) return;
        const reason = e instanceof PipeLoadError ? e.message : `読めませんでした（${e instanceof Error ? e.message : String(e)}）`;
        bannerShown = true;
        deps.post({ type: 'externalUnreadable', reason });
        return;
      }
      if (gen !== generation) return;
      const verdict = judgeExternal(deps.saved(), disk, deps.unsaved() !== null);
      if (verdict === 'none') {
        pending = null;
        if (bannerShown) {
          bannerShown = false;
          deps.post({ type: 'externalResolved' });
        }
      } else if (verdict === 'reload') {
        await take(disk, null, 'auto');
      } else {
        pending = disk;
        bannerShown = true;
        deps.post({ type: 'externalConflict', diff: diffPipes(deps.saved(), disk) });
      }
    },
    async choose(choice) {
      const disk = pending;
      if (disk === null) return;
      if (choice === 'load') {
        await take(disk, deps.unsaved(), 'chosen');
      } else {
        deps.setSaved(disk);
        pending = null;
        bannerShown = false;
        deps.post({ type: 'externalKept', savedNames: names(disk) });
      }
    },
    onSaved() {
      generation++;
      pending = null;
      bannerShown = false;
    },
    dispose() {
      generation++;
      pending = null;
      bannerShown = false;
    },
  };
}
