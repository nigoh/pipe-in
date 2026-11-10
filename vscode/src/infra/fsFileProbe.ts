// 通常のファイルかの確かめ（D0078。作業台から流す実行ファイルを探すのに使う）。読むだけで書かない。
// 読み取りの口は ./readOnlyFs.ts の stat だけを通す。失敗はすべて false で、例外は外に出さない。
import { nodeReadOnlyFs } from './readOnlyFs.ts';
import type { ReadOnlyFs } from './readOnlyFs.ts';

/**
 * file が通常のファイルかを、stat を 1 回呼んで確かめる。リンク先が通常のファイルならリンクも true（venv の bin/pipe-in はリンクのことがある）。
 * フォルダ・無いパス・切れたリンク・権限などの失敗は false。
 */
export async function isRegularFile(file: string, options: { fs?: Pick<ReadOnlyFs, 'stat'> } = {}): Promise<boolean> {
  const fs = options.fs ?? nodeReadOnlyFs;
  try {
    return (await fs.stat(file)).isFile();
  } catch {
    return false;
  }
}
