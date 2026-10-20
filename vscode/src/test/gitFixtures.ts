// テストの補助：一時フォルダの中に、git の worktree の登録（.git の中）を実物と同じ形で作る（D0019）。
// 主の checkout は <base>/main。.git はフォルダで、worktrees/<登録名>/{gitdir, HEAD, commondir} を持つ。
// 別の worktree は <base>/<dir>。.git はファイルで「gitdir: <主>/.git/worktrees/<登録名>」と書く。
// git のコマンドは使わない（子プロセスを起こさない）。
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { stateJson } from './fixtures.ts';

export interface WtSpec {
  /** 登録名（.git/worktrees/<name>） */
  name: string;
  /** worktree のフォルダ名（既定は name） */
  dir?: string;
  /** ブランチ名。null なら detached HEAD。既定は feat/<name> */
  branch?: string | null;
  /** work_dir（docs/pipeline）と state.json を作るか（既定 true） */
  workDir?: boolean;
  /** state.json の中身（既定は終わった開発フロー） */
  state?: string;
}

export interface RepoFixture {
  mainRoot: string;
  commonDir: string;
  /** 登録名 → worktree の根 */
  roots: Record<string, string>;
}

export const WORK_DIR_SETTING = 'docs/pipeline';
const SHA = '0123456789abcdef0123456789abcdef01234567';

export async function put(file: string, text: string): Promise<void> {
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, text);
}

export async function makeRepo(base: string, worktrees: WtSpec[], opts: { mainState?: string } = {}): Promise<RepoFixture> {
  const mainRoot = path.join(base, 'main');
  const commonDir = path.join(mainRoot, '.git');
  await put(path.join(commonDir, 'HEAD'), 'ref: refs/heads/main\n');
  // git の設定。拡張はこれを読んではいけない（fsmonitor は git が別のプログラムを動かす道）
  await put(path.join(commonDir, 'config'), '[core]\n\tfsmonitor = ./evil-hook\n');
  await put(path.join(mainRoot, 'docs', 'pipeline', 'state.json'), opts.mainState ?? stateJson({ final: 'PASSED' }));
  const roots: Record<string, string> = {};
  for (const wt of worktrees) {
    const root = path.join(base, wt.dir ?? wt.name);
    roots[wt.name] = root;
    const reg = path.join(commonDir, 'worktrees', wt.name);
    await put(path.join(reg, 'gitdir'), `${path.join(root, '.git')}\n`);
    const branch = wt.branch === undefined ? `feat/${wt.name}` : wt.branch;
    await put(path.join(reg, 'HEAD'), branch === null ? `${SHA}\n` : `ref: refs/heads/${branch}\n`);
    await put(path.join(reg, 'commondir'), '../..\n');
    await put(path.join(root, '.git'), `gitdir: ${reg}\n`);
    await put(path.join(root, 'README.md'), 'worktree の他のファイル（読んではいけない）\n');
    if (wt.workDir !== false) {
      await put(path.join(root, 'docs', 'pipeline', 'state.json'), wt.state ?? stateJson({ final: 'PASSED' }));
      await put(path.join(root, 'docs', 'pipeline', 'other.md'), '成果物の一覧にないファイル\n');
    }
  }
  return { mainRoot, commonDir, roots };
}
