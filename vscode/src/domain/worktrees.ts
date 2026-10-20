// 別の worktree の登録（.git の中のファイル）の読み方と、場所として受け入れてよいかの判断。純粋（ファイルに触れない）。
// 集めるのは infra/fsWorktrees.ts。ここは「集めた事実」から判断するだけ。
import path from 'node:path';

const REGISTRY_NAME = /^[A-Za-z0-9._-]{1,100}$/;

/** .git/worktrees/ の下の登録名として安全か（パスに化ける文字・長すぎる名前・. と .. は通さない）。 */
export function isRegistryName(name: string): boolean {
  return REGISTRY_NAME.test(name) && name !== '.' && name !== '..';
}

/** worktree の .git ファイルの形（gitdir: <パス> の1行）からパスを取り出す。ほかは null。 */
export function parseGitdirLine(text: string): string | null {
  const first = text.split(/\r?\n/)[0] ?? '';
  const m = /^gitdir:\s*(\S.*?)\s*$/.exec(first);
  return m === null ? null : m[1]!;
}

/** HEAD の「ref: refs/heads/<名>」から名を取り出す。detached HEAD などは null。 */
export function branchOf(headText: string): string | null {
  const first = (headText.split(/\r?\n/)[0] ?? '').trim();
  const m = /^ref:\s*refs\/heads\/(\S.*)$/.exec(first);
  return m === null ? null : m[1]!;
}

/** 同じパスか。整えてから比べる（ignoreCase のときは大文字小文字を無視。Windows 用）。 */
export function samePath(a: string, b: string, ignoreCase: boolean): boolean {
  const x = path.resolve(a);
  const y = path.resolve(b);
  return ignoreCase ? x.toLowerCase() === y.toLowerCase() : x === y;
}

const DETACHED_HEAD = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/;

/** HEAD の中身から出す名前：ref ならブランチ名、detached HEAD（40 桁か 64 桁の 16 進）なら先頭 7 文字の短い ID。ほかは null。 */
export function headLabel(headText: string): string | null {
  const branch = branchOf(headText);
  if (branch !== null) return branch;
  const first = (headText.split(/\r?\n/)[0] ?? '').trim();
  return DETACHED_HEAD.test(first) ? first.slice(0, 7) : null;
}

/** 別の worktree の名前：HEAD から読めるブランチ名か短い ID。何も読めなければ worktree のフォルダ名（見分けるための最後の手段）。 */
export function placeLabel(headText: string | null, root: string): string {
  return (headText === null ? null : headLabel(headText)) ?? path.basename(root);
}

/** worktree の根に work_dir の設定を当てはめる。根の中に収まるときだけ絶対パス、外（.. や外を指す絶対パス）なら null。 */
export function workDirIn(root: string, setting: string): string | null {
  const resolved = path.resolve(root, setting);
  const rel = path.relative(root, resolved);
  if (rel === '..' || rel.startsWith(`..${path.sep}`) || path.isAbsolute(rel)) return null;
  return resolved;
}

/** infra が集めた、worktree 1つの事実。 */
export interface WorktreeFacts {
  kind: 'main' | 'linked';
  /** 登録名（主の checkout は ''） */
  name: string;
  /** linked：登録の gitdir ファイルが指す <worktree>/.git のパス。main：主の根 */
  registeredPath: string | null;
  /** 根が実在するフォルダか */
  rootExists: boolean;
  /** 根の .git：ファイル（gitdir: の中身。読めなければ null）・フォルダ（実体のパス。読めなければ null）・無い */
  dotGit: { type: 'file'; gitdir: string | null } | { type: 'dir'; realPath: string | null } | { type: 'none' };
  /** 登録の HEAD の中身（読めなければ null） */
  head: string | null;
}

/**
 * 場所にしてよい worktree か（要件の確かめの (1)(2)）。
 * (1) 登録のパスが絶対パスで、実在するフォルダ。
 * (2) linked は根の .git ファイルが自分の登録（<commondir>/worktrees/<登録名>）を指し返している。主は .git がフォルダで、その実体が commondir。
 * (3) work_dir が根の中に収まること）は workDirIn で別に判断する。
 */
export function acceptWorktree(
  facts: WorktreeFacts,
  commonDir: string,
  ignoreCase: boolean,
): { root: string; label: string } | null {
  const registered = facts.registeredPath;
  if (registered === null || !path.isAbsolute(registered) || !facts.rootExists) return null;
  let root: string;
  if (facts.kind === 'linked') {
    if (path.basename(registered) !== '.git') return null;
    root = path.dirname(registered);
    const back = facts.dotGit;
    if (back.type !== 'file' || back.gitdir === null) return null;
    if (!samePath(path.resolve(root, back.gitdir), path.join(commonDir, 'worktrees', facts.name), ignoreCase)) return null;
  } else {
    root = registered;
    const dot = facts.dotGit;
    if (dot.type !== 'dir' || dot.realPath === null || !samePath(dot.realPath, commonDir, ignoreCase)) return null;
  }
  return { root, label: placeLabel(facts.head, root) };
}
