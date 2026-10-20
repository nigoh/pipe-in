// テストの補助：一時フォルダの中で作業して、終わったら消す。リポジトリの実物には書かない。
// 一時フォルダは realpath にそろえる（macOS の /var → /private/var のような別名で、パスの比べが食い違わないように）。
import { mkdtemp, realpath, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

export async function withTempDir<T>(fn: (dir: string) => Promise<T>): Promise<T> {
  const dir = await realpath(await mkdtemp(path.join(os.tmpdir(), 'pipe-in-vscode-runlist-')));
  try {
    return await fn(dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}
