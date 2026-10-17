// 元に戻す・やり直し：1手ごとにモデルの写し（JSON の文字列）を積む。純粋な関数だけ（h は呼んだ側の持ち物で、ここで書き換える）。
// 同じ key（同じ欄に続けて打った分など）が続けば1手にまとめる。形が変わらない操作は積まない。上限を超えたら古いほうから捨てる。

export interface HistoryEntry { label: string; snap: string; key?: string }
export interface History {
  entries: HistoryEntry[];
  /** いまの形が entries のどれか */
  at: number;
  limit: number;
}

export function createHistory(snap: string, label = '開いたとき', limit = 200): History {
  return { entries: [{ label, snap }], at: 0, limit };
}

/** 1手を積む。積んだ（まとめた）ら true、形が変わっていなければ false */
export function record(h: History, label: string, snap: string, key?: string): boolean {
  const cur = h.entries[h.at]!;
  if (cur.snap === snap) return false;
  if (key !== undefined && cur.key === key && h.at === h.entries.length - 1 && h.at > 0) {
    cur.snap = snap;
    return true;
  }
  h.entries.splice(h.at + 1);
  h.entries.push({ label, snap, ...(key !== undefined ? { key } : {}) });
  h.at = h.entries.length - 1;
  while (h.entries.length > h.limit) {
    h.entries.shift();
    h.at--;
  }
  return true;
}

export const canUndo = (h: History): boolean => h.at > 0;
export const canRedo = (h: History): boolean => h.at < h.entries.length - 1;

/** 1手戻した形（戻せなければ null）。戻したあとに同じ欄へ打っても、前の手にはまとめない */
export function undo(h: History): string | null {
  if (!canUndo(h)) return null;
  h.at--;
  return seal(h);
}

export function redo(h: History): string | null {
  if (!canRedo(h)) return null;
  h.at++;
  return seal(h);
}

/** 一覧の i 番目の時点へ飛ぶ（あとの手は残るので、やり直しで先へ戻れる） */
export function jump(h: History, i: number): string | null {
  if (!Number.isInteger(i) || i < 0 || i >= h.entries.length) return null;
  h.at = i;
  return seal(h);
}

function seal(h: History): string {
  const e = h.entries[h.at]!;
  delete e.key;
  return e.snap;
}
