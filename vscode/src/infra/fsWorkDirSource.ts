// WorkDirSource の実装：node:fs/promises で work_dir を読む。書き込みは一切しない。
// 場所（いまの work_dir・別の worktree の work_dir）の中の run の一覧（直下・パイプ・archive/）も、ここで読むだけで作る。
import path from 'node:path';
import type { PlaceRuns, RunsSource } from '../app/runList.ts';
import type { WorkDirSource } from '../app/refreshView.ts';
import { ARTIFACT_MAX_BYTES, ARTIFACT_TOTAL_MAX_BYTES, artifactNamesFor } from '../domain/artifacts.ts';
import type { ArtifactFile } from '../domain/artifacts.ts';
import type { StageLogFile, WorkDirSnapshot } from '../domain/pipelineView.ts';
import { validMtime } from '../domain/quiet.ts';
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

/**
 * ファイルの更新時刻（UTC のミリ秒）。stat で読むだけ（書き換えない）。
 * stat が失敗した・値が有限で 0 より大きい数でない（0・負・NaN・文字など）ときは null（止まっているかもの印の元にしない）。
 */
async function readMtime(file: string, fs: ReadOnlyFs): Promise<number | null> {
  try {
    return validMtime((await fs.stat(file)).mtimeMs);
  } catch {
    return null;
  }
}

/**
 * logs/ の段のログ。中身を読めたものだけ、そのあとで更新時刻を stat する（読んでから stat するので、読んだ中身より古い時刻にならない）。
 * いまの work_dir・別の worktree・パイプのフォルダ・選んだ実行の写しは、どれもこの 1 つを通る。
 */
async function readStageLogs(logsDir: string, fs: ReadOnlyFs = nodeReadOnlyFs): Promise<StageLogFile[]> {
  let names: string[];
  try {
    names = await fs.readdir(logsDir);
  } catch {
    return [];
  }
  const logs: StageLogFile[] = [];
  for (const fileName of names.filter((n) => parseStageLogName(n) !== null)) {
    const file = path.join(logsDir, fileName);
    const text = await readText(file, fs);
    if (text !== null) logs.push({ fileName, text, mtimeMs: await readMtime(file, fs) });
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

/**
 * text を UTF-8 で maxBytes バイト以下に切る。超えなければそのまま（cut: false）。
 * 超えるなら、maxBytes のところから、続きのバイト（10xxxxxx）のあいだ切れ目を戻して、文字の境目で切る（cut: true）。
 * 文字の途中で切れても末尾に U+FFFD が付かず、境目に合うときは 1 文字も落とさない。中ほどの本物の U+FFFD は変えない。
 */
export function cutToBytes(text: string, maxBytes: number): { text: string; cut: boolean } {
  const bytes = Buffer.from(text, 'utf8');
  const limit = Math.max(0, Math.floor(maxBytes));
  if (bytes.length <= limit) return { text, cut: false };
  let end = limit;
  while (end > 0 && (bytes[end]! & 0xc0) === 0x80) end -= 1;
  return { text: bytes.subarray(0, end).toString('utf8'), cut: true };
}

/**
 * 成果物 1 つの写し。lstat で通常のファイルかを確かめ（symlink・フォルダ・その他は読まない）、先頭を 1 回だけ読んで文字の境目で切る。
 * 更新時刻は同じ lstat の値。読めない・無い・通常のファイルでない → null（その成果物だけ「まだない」。ほかの読みは巻き込まない）。
 * readHead は上限より 1 バイト多く頼む。切れたかどうかは、読んだ文字の長さで決まる（ファイルの大きさは当てにしない）。
 * 限界：lstat で確かめてから readHead が開くまでのあいだに、通常のファイルが symlink に差し替えられると、リンク先を読む。
 * 差し替えるには作業フォルダに書ける別のプロセスが要り、見えるのは使う人自身の画面だけなので、受け入れる（口は 'r' だけで開く 6 つのまま変えない）。コミットされた symlink は lstat で止まる。
 */
async function readArtifact(file: string, fs: ReadOnlyFs): Promise<ArtifactFile | null> {
  try {
    const info = await fs.lstat(file);
    if (!info.isFile()) return null;
    const { text, cut } = cutToBytes(await fs.readHead(file, ARTIFACT_MAX_BYTES + 1), ARTIFACT_MAX_BYTES);
    return { text, mtimeMs: validMtime(info.mtimeMs), cut };
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
 * ログ（logs/*.jsonl）は final が無く archive でない run だけ読む（行の状態に要るため。中身を読んだあとに更新時刻の stat も 1 回）。
 * final のある run と archive の run は logs/ を開かない（stat もしない）。symlink のフォルダは辿らない。
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

/**
 * state.json、logs/ の中で parseStageLogName が null でない *.jsonl（中身と更新時刻）、記録から作った成果物の一覧のファイルを読む。
 * 成果物は 1 つにつき lstat 1 回と先頭の読み 1 回で、写しの項目は { text, mtimeMs, cut }（上限・切り方は readArtifact）。
 * 1 回の読みで写しに入れる文字の合計が上限に届いたら、残りは lstat もせず読まない（一覧の後ろの成果物から「まだない」になる）。
 * 項目の名前は外から来る（記録の output）ので、Object.defineProperty で自分のキーとして入れる（__proto__ でも原型が替わらない）。
 * options.previous が true のとき（archive/ の前の実行）だけ、写しに previous: true を入れる。持たせないときは項目ごと無い。
 * どの実行が前の実行かは、基盤は知らない。呼ぶ側（一覧の行）が渡す。
 * options.fs は読み取りの口（既定は本物）。state.json・段のログ・成果物の読みはすべてこの口を通る。
 */
export function createFsWorkDirSource(
  workDirAbs: string,
  workDirForDisplay: string,
  options: { previous?: boolean; fs?: ReadOnlyFs } = {},
): WorkDirSource {
  const fs = options.fs ?? nodeReadOnlyFs;
  return {
    async read(): Promise<WorkDirSnapshot> {
      const stateJson = await readText(path.join(workDirAbs, STATE), fs);
      const artifacts: WorkDirSnapshot['artifacts'] = {};
      let total = 0;
      for (const name of artifactNamesFor(parseRunRecord(stateJson))) {
        if (total >= ARTIFACT_TOTAL_MAX_BYTES) break;
        const file = await readArtifact(path.join(workDirAbs, name), fs);
        if (file === null) continue;
        total += Buffer.byteLength(file.text, 'utf8');
        Object.defineProperty(artifacts, name, { value: file, enumerable: true, writable: true, configurable: true });
      }
      return {
        workDir: workDirForDisplay,
        stateJson,
        stageLogs: await readStageLogs(path.join(workDirAbs, 'logs'), fs),
        artifacts,
        ...(options.previous === true ? { previous: true } : {}),
      };
    },
  };
}
