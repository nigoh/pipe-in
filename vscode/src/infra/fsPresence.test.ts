// work_dir の有無の確かめ（D0034）：stat を 1 回呼ぶだけで「有る」「無い」「分からない」に分ける基盤。読むだけで書かない。
// 実物は一時フォルダ（test/tempDir.ts）で、失敗の理由は偽の stat（手で書いた口）が投げて確かめる。時計・ネットワーク・子プロセスは使わない。
// まだ無い部品（infra/fsPresence.ts）は、呼んだところで落ちるように、テストの中で読み込む（ファイルごと読めずに全部が落ちる形にしない）。
// 型は、この中で形を書いて受ける（部品の型に合わせた型検査は、部品ができてから実装の段が見る）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, symlink, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { makeRepo } from '../test/gitFixtures.ts';
import { recordingFs } from '../test/recordingFs.ts';
import { withTempDir } from '../test/tempDir.ts';
import { findWorktrees } from './fsWorktrees.ts';
import { nodeReadOnlyFs } from './readOnlyFs.ts';
import type { ReadOnlyFs } from './readOnlyFs.ts';

type Presence = 'present' | 'absent' | 'unknown';
type DirPresence = (dir: string, options?: { fs?: unknown }) => Promise<Presence>;
const loadModule = async (): Promise<{ dirPresence: DirPresence }> => (await import('./fsPresence.ts')) as unknown as { dirPresence: DirPresence };

/** 実物の node:fs/promises で確かめる（引数は work_dir の絶対パス 1 つだけ）。 */
const real = async (dir: string): Promise<Presence> => (await loadModule()).dirPresence(dir);
/** 偽の stat を渡して確かめる。 */
const faked = async (dir: string, stat: (p: string) => Promise<unknown>): Promise<Presence> => (await loadModule()).dirPresence(dir, { fs: { stat } });

const KEEP_NOTE = '（今のまま通る。守る）';
/** code つきの失敗（Node の失敗と同じ形） */
const withCode = (code: string): Error => Object.assign(new Error(`${code}: 偽の失敗`), { code });
const throws = (value: unknown) => async (): Promise<never> => {
  throw value;
};
const answers = (isDirectory: boolean) => async (): Promise<{ isDirectory(): boolean }> => ({ isDirectory: () => isDirectory });

// ---- AC-01：有る ----

test('D0034-AC-01: 実在するフォルダは「有る」', async () => {
  await withTempDir(async (base) => {
    const dir = path.join(base, 'docs', 'pipeline');
    await mkdir(dir, { recursive: true });
    assert.equal(await real(dir), 'present');
  });
});

test('D0034-AC-01: リンク先がフォルダのシンボリックリンクも「有る」', async (t) => {
  await withTempDir(async (base) => {
    const target = path.join(base, 'real-dir');
    const link = path.join(base, 'link-dir');
    await mkdir(target, { recursive: true });
    try {
      await symlink(target, link, 'dir');
    } catch (e) {
      t.skip(`シンボリックリンクを作れない環境（${String((e as { code?: unknown }).code)}）`);
      return;
    }
    assert.equal(await real(link), 'present');
  });
});

// ---- AC-02：無い ----

test('D0034-AC-02: work_dir が無い（親はある）なら「無い」', async () => {
  await withTempDir(async (base) => {
    await mkdir(path.join(base, 'docs'), { recursive: true });
    assert.equal(await real(path.join(base, 'docs', 'pipeline')), 'absent');
  });
});

test('D0034-AC-02: 親が 1 段無いなら「無い」', async () => {
  await withTempDir(async (base) => {
    assert.equal(await real(path.join(base, 'docs', 'pipeline')), 'absent');
  });
});

test('D0034-AC-02: 親が何段も無い（a から無い）なら「無い」', async () => {
  await withTempDir(async (base) => {
    assert.equal(await real(path.join(base, 'a', 'b', 'c', 'docs', 'pipeline')), 'absent');
  });
});

test('D0034-AC-02: 親がファイルなら「無い」（ENOTDIR）', async () => {
  await withTempDir(async (base) => {
    await writeFile(path.join(base, 'docs'), 'これはフォルダではない\n');
    assert.equal(await real(path.join(base, 'docs', 'pipeline')), 'absent');
  });
});

test('D0034-AC-02: work_dir がファイルなら「無い」', async () => {
  await withTempDir(async (base) => {
    await writeFile(path.join(base, 'pipeline'), 'これはフォルダではない\n');
    assert.equal(await real(path.join(base, 'pipeline')), 'absent');
  });
});

const ABSENT_FAILURES: readonly (readonly [string, unknown])[] = [
  ['Error に code: ENOENT', withCode('ENOENT')],
  ['Error に code: ENOTDIR', withCode('ENOTDIR')],
  ['素の object { code: ENOENT }（Error でなくても code で分ける）', { code: 'ENOENT' }],
  ['素の object { code: ENOTDIR }', { code: 'ENOTDIR' }],
];

for (const [label, failure] of ABSENT_FAILURES) {
  test(`D0034-AC-02: 偽の stat が ${label} を投げたら「無い」`, async () => {
    assert.equal(await faked('/ws/docs/pipeline', throws(failure)), 'absent');
  });
}

test('D0034-AC-02: 偽の stat がフォルダでないもの（ファイルなど）を返したら「無い」', async () => {
  assert.equal(await faked('/ws/docs/pipeline', answers(false)), 'absent');
});

test('D0034-AC-02: 偽の stat がフォルダを返したら「有る」（対の確かめ）', async () => {
  assert.equal(await faked('/ws/docs/pipeline', answers(true)), 'present');
});

// ---- AC-03：分からない（「無い」にしない） ----

const UNKNOWN_FAILURES: readonly (readonly [string, unknown])[] = [
  ['Error に code: EACCES（権限がない）', withCode('EACCES')],
  ['Error に code: EIO', withCode('EIO')],
  ['Error に code: ELOOP', withCode('ELOOP')],
  ['Error に code: EMFILE', withCode('EMFILE')],
  ['Error に code: ETIMEDOUT', withCode('ETIMEDOUT')],
  ['Error に code: ENAMETOOLONG', withCode('ENAMETOOLONG')],
  ['code の無い Error', new Error('理由の分からない失敗')],
  ['素の object {}', {}],
  ['素の object { code: EACCES }', { code: 'EACCES' }],
  ['code が数字の object { code: 2 }', { code: 2 }],
  ['文字列', 'ENOENT'],
  ['null', null],
  ['数字', 2],
  ['undefined', undefined],
];

for (const [label, failure] of UNKNOWN_FAILURES) {
  test(`D0034-AC-03: 偽の stat が ${label} を投げたら「分からない」（「無い」にせず、例外も出さない）`, async () => {
    assert.equal(await faked('/ws/docs/pipeline', throws(failure)), 'unknown');
  });
}

// ---- AC-04：ワークスペースの外の絶対パスも同じ確かめ方 ----

test('D0034-AC-04: ワークスペースの外の work_dir も、実物で「無い」→ できたら「有る」。ワークスペースの中の docs/pipeline の有無には左右されない', async () => {
  await withTempDir(async (workspace) => {
    await withTempDir(async (outside) => {
      // ワークスペースの側に docs/pipeline があっても、外の work_dir の答えには関わらない
      await mkdir(path.join(workspace, 'docs', 'pipeline'), { recursive: true });
      const dir = path.join(outside, 'p', 'docs', 'pipeline');
      assert.equal(await real(dir), 'absent');
      await mkdir(dir, { recursive: true });
      assert.equal(await real(dir), 'present');
    });
  });
});

test('D0034-AC-04: 渡した絶対パスがそのまま stat に渡り、触るのはそれ 1 つだけ（親もワークスペースも見ない）：有る', async () => {
  const seen: string[] = [];
  const dir = path.resolve('/outside/p/docs/pipeline');
  const result = await faked(dir, async (p) => {
    seen.push(p);
    return { isDirectory: () => true };
  });
  assert.equal(result, 'present');
  assert.deepEqual(seen, [dir]);
});

test('D0034-AC-04: 渡した絶対パスがそのまま stat に渡り、触るのはそれ 1 つだけ（親に上って探さない）：無い・分からない', async () => {
  const dir = path.resolve('/outside/p/docs/pipeline');
  for (const [failure, expected] of [[withCode('ENOENT'), 'absent'], [withCode('EACCES'), 'unknown']] as const) {
    const seen: string[] = [];
    const result = await faked(dir, async (p) => {
      seen.push(p);
      throw failure;
    });
    assert.equal(result, expected);
    assert.deepEqual(seen, [dir]);
  }
});

// ---- AC-05：呼ぶ読み取りの関数は stat の 1 回だけ ----

test('D0034-AC-05: 有る work_dir の確かめは、読んだパスの記録が stat の 1 件（work_dir の絶対パス）だけ', async () => {
  await withTempDir(async (base) => {
    const dir = path.join(base, 'docs', 'pipeline');
    await mkdir(dir, { recursive: true });
    const { fs, calls } = recordingFs();
    assert.equal(await (await loadModule()).dirPresence(dir, { fs }), 'present');
    assert.deepEqual(calls, [{ op: 'stat', path: dir }]);
  });
});

test('D0034-AC-05: 無い work_dir（親が何段も無い）の確かめも、stat の 1 件だけ。親に上らず、readdir・lstat・realpath などを呼ばない', async () => {
  await withTempDir(async (base) => {
    const dir = path.join(base, 'a', 'b', 'docs', 'pipeline');
    const { fs, calls } = recordingFs();
    assert.equal(await (await loadModule()).dirPresence(dir, { fs }), 'absent');
    assert.deepEqual(calls, [{ op: 'stat', path: dir }]);
  });
});

test('D0034-AC-05: work_dir がファイルでも、stat の 1 件だけ（readFile・readHead で中身を読まない）', async () => {
  await withTempDir(async (base) => {
    const file = path.join(base, 'pipeline');
    await writeFile(file, '中身\n');
    const { fs, calls } = recordingFs();
    assert.equal(await (await loadModule()).dirPresence(file, { fs }), 'absent');
    assert.deepEqual(calls, [{ op: 'stat', path: file }]);
  });
});

test(`D0034-AC-05: 読み取りの口の関数は 6 つのまま（readFile・readdir・stat・lstat・realpath・readHead）${KEEP_NOTE}`, () => {
  assert.deepEqual(Object.keys(nodeReadOnlyFs).sort(), ['lstat', 'readFile', 'readHead', 'readdir', 'realpath', 'stat']);
});

// ---- AC-06：別の worktree の work_dir の判定は、「分からない」も「無い」と同じに扱う（置き換えても結果が変わらない） ----

const WORKTREE_STAT_CASES: readonly (readonly [string, string | null, boolean])[] = [
  ['stat が成功する（対の確かめ）', null, true],
  ['stat が ENOENT で失敗する', 'ENOENT', false],
  ['stat が EACCES で失敗する（分からない）', 'EACCES', false],
  ['stat が EIO で失敗する（分からない）', 'EIO', false],
  ['stat が ELOOP で失敗する（分からない）', 'ELOOP', false],
];

for (const [label, code, listed] of WORKTREE_STAT_CASES) {
  test(`D0034-AC-06: 別の worktree の work_dir を ${label} とき、場所になるのは ${listed}（「分からない」は「無い」と同じ）${KEEP_NOTE}`, async () => {
    await withTempDir(async (base) => {
      const repo = await makeRepo(base, [{ name: 'feat-a' }]);
      const workDir = path.join(repo.roots['feat-a']!, 'docs', 'pipeline');
      const fs: ReadOnlyFs = {
        ...nodeReadOnlyFs,
        stat: (async (p: unknown, ...rest: unknown[]) => {
          if (code !== null && p === workDir) throw withCode(code);
          return (nodeReadOnlyFs.stat as unknown as (...args: unknown[]) => Promise<unknown>)(p, ...rest);
        }) as unknown as ReadOnlyFs['stat'],
      };
      const found = await findWorktrees(repo.mainRoot, 'docs/pipeline', { limit: 8, ignoreCase: false, fs });
      assert.deepEqual(found.places.map((place) => place.key), listed ? ['wt.feat-a'] : []);
    });
  });
}
