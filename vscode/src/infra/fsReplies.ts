// 返事のファイル（reply.json）だけを書く口（D0079）。ReplyStore の実装。
// 書くのは、いまの work_dir の実行のフォルダ（直下か直下 1 段のパイプのフォルダ）の reply.json 1 つだけ。新しく作るときだけで、上書きはしない。
// ファイル名は定数だけ（口の型にファイル名の引数は無い）。リンクは辿らず、一時ファイルは作らない。fsPipes.ts・fsVersions.ts と同じ考え方（書き込みの口を絞る）。
import { lstat, open, realpath, unlink } from 'node:fs/promises';
import path from 'node:path';
import type { ReplyStore } from '../app/replyFlow.ts';
import { REPLY_FILE_NAME, REPLY_MAX_BYTES } from '../domain/replyFile.ts';
import type { ReplyText } from '../domain/replyFile.ts';
import { ROOT_RUN_ID, isRunFolderName } from '../domain/runs.ts';

/** 試験で差し替える部品（失敗する open など） */
export interface FsReplyDeps {
  open?: typeof open;
}

export function createFsReplyStore(workDirAbs: string, deps: FsReplyDeps = {}): ReplyStore {
  const openFile = deps.open ?? open;
  return {
    async create(runId: string, text: ReplyText) {
      // 1. 実行のフォルダの指定：直下（''）かパイプのフォルダ名だけ（archive・logs・区切り・.. などは通らない）
      if (typeof runId !== 'string' || (runId !== ROOT_RUN_ID && !isRunFolderName(runId))) return { ok: false, reason: 'bad_run' };
      // 2. 大きさ（文字数でなくバイト数）
      if (typeof text !== 'string' || Buffer.byteLength(text, 'utf8') > REPLY_MAX_BYTES) return { ok: false, reason: 'bad_text' };
      // 3. 実行のフォルダが、リンクでない本物のフォルダで、work_dir の中に実在するか
      const base = path.resolve(workDirAbs);
      const dir = runId === ROOT_RUN_ID ? base : path.join(base, runId);
      try {
        if (runId !== ROOT_RUN_ID) {
          const info = await lstat(dir);
          if (info.isSymbolicLink() || !info.isDirectory()) return { ok: false, reason: 'outside' };
        }
        const root = await realpath(base);
        const expected = runId === ROOT_RUN_ID ? root : path.join(root, runId);
        if ((await realpath(dir)) !== expected) return { ok: false, reason: 'outside' };
      } catch {
        return { ok: false, reason: 'failed' };
      }
      // 4. 排他で新しく作る（すでにある通常のファイル・フォルダ・リンクは、先が無いリンクも含めて失敗する）
      const file = path.join(dir, REPLY_FILE_NAME);
      let handle;
      try {
        handle = await openFile(file, 'wx');
      } catch (e) {
        return { ok: false, reason: (e as { code?: unknown } | null)?.code === 'EEXIST' ? 'exists' : 'failed' };
      }
      // 5. 書いて閉じる。途中で失敗したら、自分が作ったファイルだけ消す
      try {
        await handle.writeFile(text, 'utf8');
        await handle.close();
        return { ok: true };
      } catch {
        await handle.close().catch(() => undefined);
        await unlink(file).catch(() => undefined);
        return { ok: false, reason: 'failed' };
      }
    },
  };
}
