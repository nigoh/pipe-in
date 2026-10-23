// 読み取りだけのファイルの口。work_dir と .git の登録を読む部品は、型でこの6つに絞る（書き込みの関数を型に入れない）。
// readHead は、大きいかもしれないファイルの先頭だけを読む（00_input.md の最初の行から名前を作るため、成果物の先頭を上限まで読むため）。開き方は 'r'（読み取り）だけ。
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
    // 小さいファイルでも上限いっぱいを確保するので、0 で埋めない確保にする。読んだ分（bytesRead）だけを使うので、確保しただけの領域は出ていかない
    const buffer = Buffer.allocUnsafe(Math.max(0, Math.floor(maxBytes)));
    // 1 回の読みは頼んだ量より短く返ることがある（ネットワークや FUSE のファイル）ので、いっぱいになるか、ファイルの終わりまで読む
    let bytesRead = 0;
    while (bytesRead < buffer.length) {
      const chunk = await handle.read(buffer, bytesRead, buffer.length - bytesRead, bytesRead);
      if (chunk.bytesRead === 0) break;
      bytesRead += chunk.bytesRead;
    }
    return buffer.subarray(0, bytesRead).toString('utf8');
  } finally {
    await handle.close();
  }
}

/** 既定：node:fs/promises から読む6つだけを束ねたもの */
export const nodeReadOnlyFs: ReadOnlyFs = { readFile, readdir, stat, lstat, realpath, readHead };
