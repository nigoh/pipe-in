// work_dir の有無の確かめ。stat を 1 回呼ぶだけで「有る・無い・分からない」に分ける。読むだけで書かない。例外は外に出さない。
// 触るパスは渡された dir だけ（親やワークスペースのフォルダは見ない）。読み取りの口は ./readOnlyFs.ts の stat だけを通す。
import type { Presence } from '../app/workDirWatch.ts';
import { nodeReadOnlyFs } from './readOnlyFs.ts';
import type { ReadOnlyFs } from './readOnlyFs.ts';

/** 「無い」と分かる失敗の code（見つからない・途中がフォルダでない）。これ以外の失敗は「分からない」 */
const ABSENT_CODES: ReadonlySet<string> = new Set(['ENOENT', 'ENOTDIR']);

/** 投げられた値の code。object でなければ（文字列・null・数字など）undefined。Error かどうかは問わない */
function codeOf(failure: unknown): unknown {
  try {
    return typeof failure === 'object' && failure !== null ? (failure as { code?: unknown }).code : undefined;
  } catch {
    return undefined;
  }
}

/**
 * dir がフォルダとして実在するかを、stat を 1 回呼んで確かめる。リンク先がフォルダのシンボリックリンクも「有る」。
 * フォルダでないもの（ファイルなど）と、ENOENT・ENOTDIR は「無い」。それ以外の失敗（権限・EIO・ELOOP・理由の分からない失敗）は「分からない」で、「無い」にしない。
 */
export async function dirPresence(dir: string, options: { fs?: Pick<ReadOnlyFs, 'stat'> } = {}): Promise<Presence> {
  const fs = options.fs ?? nodeReadOnlyFs;
  try {
    return (await fs.stat(dir)).isDirectory() ? 'present' : 'absent';
  } catch (failure) {
    const code = codeOf(failure);
    return typeof code === 'string' && ABSENT_CODES.has(code) ? 'absent' : 'unknown';
  }
}
