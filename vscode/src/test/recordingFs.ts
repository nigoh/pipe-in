// テストの補助：読んだパスを記録する偽の fs（D0019）。本物の node:fs/promises に渡すだけで、書き込みの関数は持たない。
// 製品コードが書き込みの関数（writeFile など）を呼べば、この偽物には無いので TypeError で落ちる。
// 2版目で readHead（先頭の maxBytes バイトだけ読む）を足した：読む口は 6 つ。開き方は 'r' だけ。
import { lstat, open, readdir, readFile, realpath, stat } from 'node:fs/promises';

export type ReadOp = 'readFile' | 'readdir' | 'stat' | 'lstat' | 'realpath' | 'readHead';
export interface ReadCall {
  op: ReadOp;
  path: string;
  /** readHead のときだけ、頼まれた上限のバイト数 */
  maxBytes?: number;
}

export interface RecordingFs {
  fs: {
    readFile: typeof readFile;
    readdir: typeof readdir;
    stat: typeof stat;
    lstat: typeof lstat;
    realpath: typeof realpath;
    readHead: (file: string, maxBytes: number) => Promise<string>;
  };
  calls: ReadCall[];
  /** 記録したパス（op を渡すとその操作だけ） */
  paths(op?: ReadOp): string[];
}

export function recordingFs(): RecordingFs {
  const calls: ReadCall[] = [];
  const wrap = <F extends (...args: any[]) => any>(op: ReadOp, fn: F): F =>
    ((p: unknown, ...rest: unknown[]) => {
      calls.push({ op, path: String(p) });
      return (fn as (...a: unknown[]) => unknown)(p, ...rest);
    }) as unknown as F;
  const readHead = async (file: string, maxBytes: number): Promise<string> => {
    calls.push({ op: 'readHead', path: String(file), maxBytes });
    const handle = await open(file, 'r');
    try {
      const buffer = Buffer.alloc(Math.max(0, maxBytes));
      const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0);
      return buffer.subarray(0, bytesRead).toString('utf8');
    } finally {
      await handle.close();
    }
  };
  return {
    fs: {
      readFile: wrap('readFile', readFile),
      readdir: wrap('readdir', readdir),
      stat: wrap('stat', stat),
      lstat: wrap('lstat', lstat),
      realpath: wrap('realpath', realpath),
      readHead,
    },
    calls,
    paths: (op) => calls.filter((c) => op === undefined || c.op === op).map((c) => c.path),
  };
}
