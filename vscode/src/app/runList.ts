// 実行の一覧のユースケース：場所ごとに記録の写しを読み、行にして並べ、見る実行を決める。
// 読み取りは口（RunsSource）の向こう。パネルや覚えた値から来る key は、ここで作った一覧にあるものだけを通す（パスを作らない）。
import path from 'node:path';
import { summarizeRun, sortRows } from '../domain/runList.ts';
import type { RunListView, RunRow } from '../domain/runList.ts';
import type { ViewClock } from '../domain/pipelineView.ts';
import { ARCHIVE_DIR, HERE, ROOT_RUN_ID, archiveStamp, isArchiveId, isRunKey, makeRunKey } from '../domain/runs.ts';
import type { PlaceKey, RunKey } from '../domain/runs.ts';

/** run を探す場所：いまの work_dir（here）と、同じリポジトリの別の worktree の work_dir */
export interface Place {
  key: PlaceKey;
  /** ブランチ名か短い ID（いまの work_dir も入る）。別の worktree の HEAD が読めないときだけフォルダ名。git の外は null */
  label: string | null;
  workDirAbs: string;
}

/** 場所の中の run 1つ分の記録の写し */
export interface PlaceRun {
  /** 直下は ''、パイプはフォルダ名、archive は archive/<日時> */
  id: string;
  stateJson: string | null;
  stageLogs: { fileName: string; text: string }[];
  /** 00_input.md の先頭（state.json に name が無い run だけ読む）。読まなかった・読めなかったときは null（口が足さない場合は無し） */
  memoHead?: string | null;
}

export interface PlaceRuns {
  runs: PlaceRun[];
  /** 読まずに省いた archive の数 */
  archiveOmitted: number;
}

/** 読み取りの口。places はいまの work_dir を先頭に。runs は読めなければ throw してよい（呼ぶ側が場所ごとに握る） */
export interface RunsSource {
  places(showOthers: boolean): Promise<{ places: Place[]; omittedWorktrees: number }>;
  runs(place: Place): Promise<PlaceRuns>;
}

export interface RunEntry {
  row: RunRow;
  /** その run のフォルダの絶対パス。場所の work_dir の中 */
  dirAbs: string;
}

export interface RunList {
  /** 並んだ順（確認待ち → 動いている → 待ち → 終わった） */
  entries: RunEntry[];
  /** 場所ごとの archive の省略（省いた場所だけ） */
  omitted: { place: string | null; count: number }[];
  omittedWorktrees: number;
  /** 別の場所の行か archive の行がある（5 秒ごとの読み直しが要る） */
  hasRemote: boolean;
}

const emptyList = (): RunList => ({ entries: [], omitted: [], omittedWorktrees: 0, hasRemote: false });

/** run のフォルダの絶対パス（場所の work_dir の中だけ） */
function dirOf(place: Place, id: string): string {
  if (id === ROOT_RUN_ID) return place.workDirAbs;
  const stamp = archiveStamp(id);
  return stamp === null ? path.join(place.workDirAbs, id) : path.join(place.workDirAbs, ARCHIVE_DIR, stamp);
}

/**
 * 場所ごとに読んで一覧にする。例外は出さない：places が読めなければ空の一覧、場所の runs が読めなければその場所だけ飛ばす。
 * いまの work_dir に run が1つも無いときの「記録なし」の行は一覧に入れない（chooseEntry が直下を返す）。
 */
export async function loadRunList(source: RunsSource, options: { showOthers: boolean; clock: ViewClock }): Promise<RunList> {
  let found: { places: Place[]; omittedWorktrees: number };
  try {
    found = await source.places(options.showOthers);
  } catch {
    return emptyList();
  }
  const entries: RunEntry[] = [];
  const omitted: RunList['omitted'] = [];
  let hasRemote = false;
  for (const place of found.places) {
    let read: PlaceRuns;
    try {
      read = await source.runs(place);
    } catch {
      continue;
    }
    if (read.archiveOmitted > 0) omitted.push({ place: place.key === HERE ? null : place.label, count: read.archiveOmitted });
    for (const run of read.runs) {
      const key = makeRunKey(place.key, run.id);
      if (!isRunKey(key)) continue;
      const previous = isArchiveId(run.id);
      if (previous || place.key !== HERE) hasRemote = true;
      const row = summarizeRun(
        {
          key,
          id: run.id,
          branch: place.label,
          other: place.key !== HERE,
          memoHead: run.memoHead ?? null,
          previous,
          stateJson: run.stateJson,
          stageLogs: run.stageLogs,
        },
        options.clock,
      );
      entries.push({ row, dirAbs: dirOf(place, run.id) });
    }
  }
  const order = new Map(sortRows(entries.map((e) => e.row)).map((row, i) => [row.key, i]));
  entries.sort((a, b) => (order.get(a.row.key) ?? 0) - (order.get(b.row.key) ?? 0));
  return { entries, omitted, omittedWorktrees: found.omittedWorktrees, hasRemote };
}

/** 一覧にある key だけ返す。形の違う値・一覧に無い値は null（口は呼ばない）。 */
export function findEntry(list: RunList, key: unknown): RunEntry | null {
  if (!isRunKey(key)) return null;
  return list.entries.find((e) => e.row.key === key) ?? null;
}

/**
 * 見る run を決める。選び（覚えた値やパネルで選んだもの）が一覧にあればそれ。無ければ今までの既定：
 * いまの work_dir の（archive を除く）最新（updated_at が同じなら直下）。それも無ければ直下（記録なしの表示）。
 */
export function chooseEntry(list: RunList, selected: string | null, here: Place): { key: RunKey; dirAbs: string } {
  const picked = findEntry(list, selected);
  if (picked !== null) return { key: picked.row.key, dirAbs: picked.dirAbs };

  const rootKey = makeRunKey(here.key, ROOT_RUN_ID);
  let best: RunEntry | null = null;
  for (const e of list.entries) {
    if (e.row.previous || !e.row.key.startsWith(`${here.key}|`)) continue;
    if (best === null) {
      best = e;
      continue;
    }
    const a = e.row.updatedMs ?? -Infinity;
    const b = best.row.updatedMs ?? -Infinity;
    if (a > b || (a === b && e.row.key === rootKey)) best = e;
  }
  return best === null ? { key: rootKey, dirAbs: here.workDirAbs } : { key: best.row.key, dirAbs: best.dirAbs };
}

/** パネルに渡す一覧。行が 0・1 つでも返す（一覧は常に出る）。workDir は上のバーに出す設定の値（相対パスのまま）。 */
export function toListView(list: RunList, selected: RunKey, workDir: string): RunListView {
  return {
    rows: list.entries.map((e) => e.row),
    selected,
    omitted: list.omitted,
    omittedWorktrees: list.omittedWorktrees,
    workDir,
  };
}
