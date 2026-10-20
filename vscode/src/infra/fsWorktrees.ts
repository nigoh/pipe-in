// 別の worktree を、.git の中の登録（ファイル）を読んで見つける。読むだけで書かない。外のプログラムは起こさない。
// 読むもの（これ以外は読まない）：ワークスペースの .git、gitdir、commondir、worktrees/ の一覧、各登録の gitdir と HEAD、
// 各 worktree の .git ファイル、work_dir の stat。git の設定ファイルは読まない・実行しない。
import path from 'node:path';
import type { Place } from '../app/runList.ts';
import { MAIN } from '../domain/runs.ts';
import { acceptWorktree, headLabel, isRegistryName, parseGitdirLine, samePath, workDirIn } from '../domain/worktrees.ts';
import type { WorktreeFacts } from '../domain/worktrees.ts';
import { nodeReadOnlyFs } from './readOnlyFs.ts';
import type { ReadOnlyFs } from './readOnlyFs.ts';

/** 登録のファイルは小さい。これより大きいものは読まない */
const MAX_SMALL_BYTES = 4096;
/** 登録の数の上限（壊れたリポジトリで際限なく読まない） */
const MAX_REGISTRATIONS = 200;

export interface FindOptions {
  /** 読む worktree の個数の上限（更新の新しい方から） */
  limit: number;
  /** Windows のように大文字小文字を区別しないパスか */
  ignoreCase: boolean;
  fs?: ReadOnlyFs;
}

export interface FoundWorktrees {
  places: Place[];
  /** 上限を超えて読まなかった数 */
  omitted: number;
}

/** 小さなファイルの中身。ない・大きすぎる・ファイルでない・読めないなら null。 */
async function readSmall(fs: ReadOnlyFs, file: string): Promise<string | null> {
  try {
    const info = await fs.stat(file);
    if (!info.isFile() || info.size > MAX_SMALL_BYTES) return null;
    return await fs.readFile(file, 'utf8');
  } catch {
    return null;
  }
}

async function isDirectory(fs: ReadOnlyFs, dir: string): Promise<boolean> {
  try {
    return (await fs.stat(dir)).isDirectory();
  } catch {
    return false;
  }
}

async function realOr(fs: ReadOnlyFs, p: string): Promise<string> {
  try {
    return await fs.realpath(p);
  } catch {
    return path.resolve(p);
  }
}

const firstLine = (text: string | null): string => (text === null ? '' : (text.split(/\r?\n/)[0] ?? '').trim());

/** 共通の .git の場所。ワークスペースの .git がフォルダならそれ、ファイル（linked worktree）なら gitdir の commondir をたどる。 */
async function findCommonDir(fs: ReadOnlyFs, workspaceRoot: string): Promise<string | null> {
  const dotGit = path.join(workspaceRoot, '.git');
  const info = await fs.lstat(dotGit);
  if (info.isDirectory()) return dotGit;
  if (!info.isFile()) return null;
  const text = await readSmall(fs, dotGit);
  const pointed = text === null ? null : parseGitdirLine(text);
  if (pointed === null) return null;
  const gitdir = path.resolve(workspaceRoot, pointed);
  const line = firstLine(await readSmall(fs, path.join(gitdir, 'commondir')));
  return line === '' ? null : path.resolve(gitdir, line);
}

/** 根と .git の事実を集める。 */
async function dotGitOf(fs: ReadOnlyFs, root: string): Promise<WorktreeFacts['dotGit']> {
  const dotGit = path.join(root, '.git');
  const info = await fs.lstat(dotGit).catch(() => null);
  if (info === null) return { type: 'none' };
  if (info.isFile()) {
    const text = await readSmall(fs, dotGit);
    return { type: 'file', gitdir: text === null ? null : parseGitdirLine(text) };
  }
  if (info.isDirectory()) {
    try {
      return { type: 'dir', realPath: await fs.realpath(dotGit) };
    } catch {
      return { type: 'dir', realPath: null };
    }
  }
  return { type: 'none' };
}

interface Candidate {
  key: string;
  facts: WorktreeFacts;
}

/** 登録（.git/worktrees/<名前>）1つの事実。 */
async function linkedFacts(fs: ReadOnlyFs, commonDir: string, name: string): Promise<Candidate> {
  const reg = path.join(commonDir, 'worktrees', name);
  const registered = firstLine(await readSmall(fs, path.join(reg, 'gitdir')));
  const head = await readSmall(fs, path.join(reg, 'HEAD'));
  const usable = registered !== '' && path.isAbsolute(registered) && path.basename(registered) === '.git';
  const root = usable ? path.dirname(registered) : null;
  const rootExists = root !== null && (await isDirectory(fs, root));
  const dotGit = root !== null && rootExists ? await dotGitOf(fs, root) : ({ type: 'none' } as const);
  return {
    key: `wt.${name}`,
    facts: { kind: 'linked', name, registeredPath: registered === '' ? null : registered, rootExists, dotGit, head },
  };
}

/** 主の checkout の事実（共通の .git が <主>/.git のとき）。 */
async function mainFacts(fs: ReadOnlyFs, commonDir: string): Promise<Candidate | null> {
  if (path.basename(commonDir) !== '.git') return null;
  const root = path.dirname(commonDir);
  const rootExists = await isDirectory(fs, root);
  return {
    key: MAIN,
    facts: {
      kind: 'main',
      name: '',
      registeredPath: root,
      rootExists,
      dotGit: rootExists ? await dotGitOf(fs, root) : { type: 'none' },
      head: await readSmall(fs, path.join(commonDir, 'HEAD')),
    },
  };
}

async function updatedMs(fs: ReadOnlyFs, workDir: string): Promise<number> {
  let latest = 0;
  for (const target of [workDir, path.join(workDir, 'state.json')]) {
    try {
      latest = Math.max(latest, (await fs.stat(target)).mtimeMs);
    } catch {
      // 無ければ 0 のまま
    }
  }
  return latest;
}

/**
 * いまの checkout のブランチ名か短い ID。.git がフォルダなら .git/HEAD、ファイル（linked worktree）なら gitdir の先の HEAD を読む。
 * git の外・読めない・形が違うときは null（行のブランチの項目ごと省く）。例外を出さない。
 */
export async function findCurrentLabel(workspaceRoot: string, options: { fs?: ReadOnlyFs } = {}): Promise<string | null> {
  const fs = options.fs ?? nodeReadOnlyFs;
  try {
    const dotGit = path.join(workspaceRoot, '.git');
    const info = await fs.lstat(dotGit);
    let headFile: string;
    if (info.isDirectory()) {
      headFile = path.join(dotGit, 'HEAD');
    } else if (info.isFile()) {
      const text = await readSmall(fs, dotGit);
      const pointed = text === null ? null : parseGitdirLine(text);
      if (pointed === null) return null;
      headFile = path.join(path.resolve(workspaceRoot, pointed), 'HEAD');
    } else {
      return null;
    }
    const head = await readSmall(fs, headFile);
    return head === null ? null : headLabel(head);
  } catch {
    return null;
  }
}

/**
 * ワークスペースの最初のフォルダから、同じ git リポジトリの別の worktree を見つける。
 * 場所にするのは、登録のパスが絶対パスで実在し、その worktree の .git が自分の登録を指し返し、work_dir が worktree の中に収まるものだけ。
 * work_dir の無い worktree は場所にも省いた数にも入れない。更新の新しい方から limit 個まで。読めなければ空（例外を出さない）。
 */
export async function findWorktrees(workspaceRoot: string, workDirSetting: string, options: FindOptions): Promise<FoundWorktrees> {
  const fs = options.fs ?? nodeReadOnlyFs;
  const none: FoundWorktrees = { places: [], omitted: 0 };
  try {
    const commonDir = await findCommonDir(fs, workspaceRoot);
    if (commonDir === null) return none;
    const names = (await fs.readdir(path.join(commonDir, 'worktrees')))
      .filter(isRegistryName)
      .sort()
      .slice(0, MAX_REGISTRATIONS);
    const commonReal = await realOr(fs, commonDir);
    const selfReal = await realOr(fs, workspaceRoot);

    const candidates: Candidate[] = [];
    const main = await mainFacts(fs, commonDir);
    if (main !== null) candidates.push(main);
    for (const name of names) candidates.push(await linkedFacts(fs, commonDir, name));

    const found: { place: Place; updated: number }[] = [];
    for (const { key, facts } of candidates) {
      const accepted = acceptWorktree(facts, commonReal, options.ignoreCase);
      if (accepted === null) continue;
      const rootReal = await realOr(fs, accepted.root);
      if (samePath(rootReal, selfReal, options.ignoreCase)) continue;
      const workDir = workDirIn(accepted.root, workDirSetting);
      if (workDir === null || !(await isDirectory(fs, workDir))) continue;
      // work_dir が symlink で worktree の外へ出る道を塞ぐ
      if (workDirIn(rootReal, await realOr(fs, workDir)) === null) continue;
      found.push({ place: { key, label: accepted.label, workDirAbs: workDir }, updated: await updatedMs(fs, workDir) });
    }
    found.sort((a, b) => b.updated - a.updated || (a.place.key < b.place.key ? -1 : a.place.key > b.place.key ? 1 : 0));
    return {
      places: found.slice(0, options.limit).map((f) => f.place),
      omitted: Math.max(0, found.length - options.limit),
    };
  } catch {
    return none;
  }
}
