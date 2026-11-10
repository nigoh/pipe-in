// 作業台から流した実行の「実行中の記録」（D0078。メモリだけ。パイプのフォルダごと）。持つのは入口で、作業台のパネルは持たない。
import path from 'node:path';

export interface ActiveRuns {
  isRunning(pipeDir: string): boolean;
  /** すでに実行中なら何もせず false */
  start(pipeDir: string, id: string): boolean;
  /** id が合う記録を外し、そのパイプのフォルダを返す。無ければ null（2回目の知らせは何もしない） */
  release(id: string): string | null;
}

/** 鍵は path.resolve(pipeDir)。呼ぶたびに別の記録を作る（モジュールの共有の状態を持たない） */
export function createActiveRuns(): ActiveRuns {
  const byDir = new Map<string, string>();
  return {
    isRunning(pipeDir) {
      return byDir.has(path.resolve(pipeDir));
    },
    start(pipeDir, id) {
      const key = path.resolve(pipeDir);
      if (byDir.has(key)) return false;
      byDir.set(key, id);
      return true;
    },
    release(id) {
      for (const [dir, runId] of byDir) {
        if (runId === id) {
          byDir.delete(dir);
          return dir;
        }
      }
      return null;
    },
  };
}
