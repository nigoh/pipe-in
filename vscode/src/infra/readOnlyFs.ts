// 読み取りだけのファイルの口。work_dir と .git の登録を読む部品は、型でこの6つに絞る（書き込みの関数を型に入れない）。
// readHead は、大きいかもしれないファイルの先頭だけを読む（00_input.md の最初の行から名前を作るため）。開き方は 'r'（読み取り）だけ。
// テストは、読んだパスを記録する偽物を渡せる。
import { lstat, open, readFile, readdir, realpath, stat } from 'node:fs/promises';

export interface ReadOnlyFs {
  readFile: typeof readFile;
  readdir: typeof readdir;
  stat: typeof stat;
  lstat: typeof lstat;
  realpath: typeof realpath;
  /** ファイルの先頭の maxBytes バイトまでを文字にして返す。読めなければ throw */
  readHead: (file: string, maxBytes: number) => Promise<string>;
}

async function readHead(file: string, maxBytes: number): Promise<string> {
  const handle = await open(file, 'r');
  try {
    const buffer = Buffer.alloc(Math.max(0, Math.floor(maxBytes)));
    const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0);
    return buffer.subarray(0, bytesRead).toString('utf8');
  } finally {
    await handle.close();
  }
}

/** 既定：node:fs/promises から読む6つだけを束ねたもの */
export const nodeReadOnlyFs: ReadOnlyFs = { readFile, readdir, stat, lstat, realpath, readHead };
