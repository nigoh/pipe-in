// 選んだ実行を覚える。覚える場所は口 MemoryStore（workspaceState がそのまま満たす）で、場所の目印と実行の目印だけを書く。
// work_dir・プロジェクト・worktree には書かない。覚えた値から直接パスを作らず、候補にあるかは app/runList.ts の chooseEntry が確かめる。
import { parseRemembered } from '../domain/runList.ts';
import { makeRunKey, parseRunKey } from '../domain/runs.ts';
import type { RunKey } from '../domain/runs.ts';

/** 覚える場所の口。get は同期、update は書き込み（workspaceState の Memento と同じ形） */
export interface MemoryStore {
  get(key: string): unknown;
  update(key: string, value: unknown): PromiseLike<void>;
}

/** 覚える鍵（これ1つだけ） */
export const MEMORY_KEY = 'pipe-in.selectedRun';

/** 選んだ実行を覚える。形の違う目印は覚えない（書かない）。書き込みはこの1か所だけ。 */
export async function rememberRun(store: MemoryStore, key: RunKey): Promise<void> {
  const parsed = parseRunKey(key);
  if (parsed === null) return;
  await store.update(MEMORY_KEY, { place: parsed.place, id: parsed.id });
}

/** 覚えた選びを実行の目印にして返す。無い・壊れている値は null（例外を出さない）。 */
export function restoreRun(store: MemoryStore): RunKey | null {
  const remembered = parseRemembered(store.get(MEMORY_KEY));
  return remembered === null ? null : makeRunKey(remembered.place, remembered.id);
}
