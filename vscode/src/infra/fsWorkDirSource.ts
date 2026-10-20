// WorkDirSource の実装：node:fs/promises で work_dir を読む。書き込みは一切しない。
// 場所（いまの work_dir・別の worktree の work_dir）の中の run の一覧（直下・パイプ・archive/）も、ここで読むだけで作る。
import path from 'node:path';
import type { PlaceRuns, RunsSource } from '../app/runList.ts';
import type { WorkDirSource } from '../app/refreshView.ts';
import { artifactNamesFor } from '../domain/artifacts.ts';
import type { WorkDirSnapshot } from '../domain/pipelineView.ts';
import { parseRunRecord } from '../domain/runRecord.ts';
import { ARCHIVE_LIMIT, WORKTREE_LIMIT } from '../domain/runList.ts';
import { ARCHIVE_DIR, HERE, ROOT_RUN_ID, describeRun, isRunFolderName } from '../domain/runs.ts';
import type { RunCandidate } from '../domain/runs.ts';
import { parseStageLogName } from '../domain/stageLog.ts';
import { findCurrentLabel, findWorktrees } from './fsWorktrees.ts';
import { nodeReadOnlyFs } from './readOnlyFs.ts';
import type { ReadOnlyFs } from './readOnlyFs.ts';

export type { ReadOnlyFs } from './readOnlyFs.ts';

const STATE = 'state.json';
/** セッション名の元にする要件メモ。先頭のこれだけのバイト数しか読まない */
const MEMO = '00_input.md';
const MEMO_HEAD_BYTES = 4096;
/** state.json はこれより大きければ読まない（壊れた・悪意のある巨大なファイルで固まらない） */
const STATE_MAX_BYTES = 4 * 1024 * 1024;
/** archive/ の下の run のフォルダ名（20261017-100000。重なると -2 が付く） */
const ARCHIVE_STAMP = /^(\d{8}-\d{6})(?:-(\d+))?$/;

/** 読めなければ null（ない・権限がない・途中で消えた）。 */
async function readText(file: string, fs: ReadOnlyFs = nodeReadOnlyFs): Promise<string | null> {
  try {
    return await fs.readFile(file, 'utf8');
  } catch {
    return null;
  }
}

async function readStageLogs(logsDir: string, fs: ReadOnlyFs = nodeReadOnlyFs): Promise<WorkDirSnapshot['stageLogs']> {
  let names: string[];
  try {
    names = await fs.readdir(logsDir);
  } catch {
    return [];
  }
  const logs: WorkDirSnapshot['stageLogs'] = [];
  for (const fileName of names.filter((n) => parseStageLogName(n) !== null)) {
    const text = await readText(path.join(logsDir, fileName), fs);
    if (text !== null) logs.push({ fileName, text });
  }
  return logs;
}

/** state.json を読む。無い・読めない → null（run にならない）。大きすぎる → { text: null }（run は残り、行は「—」になる）。 */
async function readState(file: string, fs: ReadOnlyFs): Promise<{ text: string | null } | null> {
  try {
    const info = await fs.stat(file);
    if (!info.isFile()) return null;
    if (info.size > STATE_MAX_BYTES) return { text: null };
    return { text: await fs.readFile(file, 'utf8') };
  } catch {
    return null;
  }
}

/** 要件メモの先頭。無い・読めない・フォルダなら null。 */
async function readMemoHead(file: string, fs: ReadOnlyFs): Promise<string | null> {
  try {
    return await fs.readHead(file, MEMO_HEAD_BYTES);
  } catch {
    return null;
  }
}

/** archive の日時の新しい順（日時の文字の降順。同じ日時は重なりの番号が大きい方が新しい）。 */
function newerArchiveFirst(a: string, b: string): number {
  const x = ARCHIVE_STAMP.exec(a);
  const y = ARCHIVE_STAMP.exec(b);
  const base = (y?.[1] ?? '').localeCompare(x?.[1] ?? '');
  return base !== 0 ? base : Number(y?.[2] ?? 1) - Number(x?.[2] ?? 1);
}

/**
 * 場所（work_dir）の中の run の記録の写し。直下の state.json（id ''）、直下のフォルダの中の state.json（パイプ）、
 * archive/<日時>/state.json（id archive/<日時>）。archive は新しい方から archiveLimit 件まで読み、超えた分は読まずに数だけ返す。
 * ログ（logs/*.jsonl）は final が無く archive でない run だけ読む（行の状態に要るため）。symlink のフォルダは辿らない。
 */
export async function listPlaceRuns(workDirAbs: string, options: { archiveLimit: number; fs?: ReadOnlyFs }): Promise<PlaceRuns> {
  const fs = options.fs ?? nodeReadOnlyFs;
  const runs: PlaceRuns['runs'] = [];

  const add = async (id: string, dir: string, withLogs: boolean): Promise<void> => {
    const state = await readState(path.join(dir, STATE), fs);
    if (state === null) return;
    const record = state.text === null ? null : parseRunRecord(state.text);
    const live = withLogs && record !== null && record.final === null;
    // 名前（state.json の name）が無い run だけ、要件メモ（00_input.md）の先頭を読む。run のフォルダの中のこの 1 つだけ
    const memoHead = record !== null && record.name !== null ? null : await readMemoHead(path.join(dir, MEMO), fs);
    runs.push({ id, stateJson: state.text, stageLogs: live ? await readStageLogs(path.join(dir, 'logs'), fs) : [], memoHead });
  };

  let entries: { name: string; isDirectory(): boolean }[] = [];
  try {
    entries = await fs.readdir(workDirAbs, { withFileTypes: true });
  } catch {
    return { runs, archiveOmitted: 0 };
  }
  await add(ROOT_RUN_ID, workDirAbs, true);
  const folders = entries
    .filter((e) => e.isDirectory() && isRunFolderName(e.name))
    .map((e) => e.name)
    .sort();
  for (const name of folders) await add(name, path.join(workDirAbs, name), true);

  let archiveOmitted = 0;
  if (entries.some((e) => e.isDirectory() && e.name === ARCHIVE_DIR)) {
    const archiveDir = path.join(workDirAbs, ARCHIVE_DIR);
    let stamps: string[] = [];
    try {
      stamps = (await fs.readdir(archiveDir, { withFileTypes: true }))
        .filter((e) => e.isDirectory() && ARCHIVE_STAMP.test(e.name))
        .map((e) => e.name)
        .sort(newerArchiveFirst);
    } catch {
      stamps = [];
    }
    for (const stamp of stamps.slice(0, options.archiveLimit)) await add(`${ARCHIVE_DIR}/${stamp}`, path.join(archiveDir, stamp), false);
    archiveOmitted = Math.max(0, stamps.length - options.archiveLimit);
  }
  return { runs, archiveOmitted };
}

/**
 * 実行の一覧の読み取りの口。places は、いまの work_dir を先頭に、（showOthers なら）同じリポジトリの別の worktree の work_dir。
 * runs(place) はその場所の run を読む。別の worktree も同じ読み方で、読む範囲は広がらない。
 */
export function createFsRunsSource(
  workspaceRoot: string,
  workDirAbs: string,
  workDirSetting: string,
  options: { fs?: ReadOnlyFs } = {},
): RunsSource {
  const fs = options.fs;
  return {
    async places(showOthers) {
      const here = { key: HERE, label: await findCurrentLabel(workspaceRoot, fs === undefined ? {} : { fs }), workDirAbs };
      if (!showOthers) return { places: [here], omittedWorktrees: 0 };
      const found = await findWorktrees(workspaceRoot, workDirSetting, {
        limit: WORKTREE_LIMIT,
        ignoreCase: process.platform === 'win32',
        ...(fs === undefined ? {} : { fs }),
      });
      return { places: [here, ...found.places], omittedWorktrees: found.omitted };
    },
    runs(place) {
      return listPlaceRuns(place.workDirAbs, { archiveLimit: ARCHIVE_LIMIT, ...(fs === undefined ? {} : { fs }) });
    },
  };
}

/**
 * work_dir の中の実行の候補：直下（state.json があるとき）と、state.json を持つ直下のフォルダ（パイプ）。
 * フォルダ名が規則に合わないもの・logs は候補にしない。1つもなければ直下だけ（記録なしの表示のため）。
 */
export async function listRunCandidates(workDirAbs: string): Promise<RunCandidate[]> {
  const found: RunCandidate[] = [];
  const rootState = await readText(path.join(workDirAbs, STATE));
  if (rootState !== null) found.push(describeRun(ROOT_RUN_ID, rootState));
  let entries: { name: string; isDirectory(): boolean }[] = [];
  try {
    entries = await nodeReadOnlyFs.readdir(workDirAbs, { withFileTypes: true });
  } catch {
    entries = [];
  }
  const folders = entries
    .filter((e) => e.isDirectory() && isRunFolderName(e.name))
    .map((e) => e.name)
    .sort();
  for (const name of folders) {
    const state = await readText(path.join(workDirAbs, name, STATE));
    if (state !== null) found.push(describeRun(name, state));
  }
  return found.length > 0 ? found : [describeRun(ROOT_RUN_ID, null)];
}

/** state.json、logs/ の中で parseStageLogName が null でない *.jsonl、記録から作った成果物の一覧のファイルを読む。 */
export function createFsWorkDirSource(workDirAbs: string, workDirForDisplay: string): WorkDirSource {
  return {
    async read(): Promise<WorkDirSnapshot> {
      const stateJson = await readText(path.join(workDirAbs, STATE));
      const artifacts: WorkDirSnapshot['artifacts'] = {};
      for (const name of artifactNamesFor(parseRunRecord(stateJson))) {
        const text = await readText(path.join(workDirAbs, name));
        if (text !== null) artifacts[name] = text;
      }
      return {
        workDir: workDirForDisplay,
        stateJson,
        stageLogs: await readStageLogs(path.join(workDirAbs, 'logs')),
        artifacts,
      };
    },
  };
}
