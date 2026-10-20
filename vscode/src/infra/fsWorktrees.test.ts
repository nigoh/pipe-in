// 別の worktree を .git の登録（ファイル）から見つける基盤（D0019）。一時フォルダに、実物と同じ形の .git を作って読ませる。
// 子プロセス（git）は起こさない。読むだけで書かない。
// まだ無い部品（infra/fsWorktrees.ts）は、呼んだところで落ちるように、テストの中で読み込む。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, rm, symlink, utimes, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { makeRepo, put } from '../test/gitFixtures.ts';
import { recordingFs } from '../test/recordingFs.ts';
import { withTempDir } from '../test/tempDir.ts';
import { stateJson } from '../test/fixtures.ts';

interface Place {
  key: string;
  label: string | null;
  workDirAbs: string;
}
interface Found {
  places: Place[];
  omitted: number;
}
interface Opts {
  limit: number;
  ignoreCase: boolean;
  fs?: unknown;
}
type FindWorktrees = (workspaceRoot: string, setting: string, opts: Opts) => Promise<Found>;
const find: FindWorktrees = async (root, setting, opts) =>
  ((await import('./fsWorktrees.ts')) as unknown as { findWorktrees: FindWorktrees }).findWorktrees(root, setting, opts);

const SETTING = 'docs/pipeline';
const OPTS: Opts = { limit: 8, ignoreCase: false };
const keysOf = (f: Found): string[] => f.places.map((p) => p.key).sort();
const EMPTY: Found = { places: [], omitted: 0 };

// ---- 補助の確認（今の作りのままで通る）：テストが使う .git の木が、git が書く実物の形になっている ----

test('補助: makeRepo は 主の .git（フォルダ）・worktrees/<名>/{gitdir, HEAD, commondir}・worktree の .git（ファイル）を実物と同じ形で作る', async () => {
  const { readFile, lstat } = await import('node:fs/promises');
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-a', branch: 'feat/a' }, { name: 'det', branch: null }]);
    assert.ok((await lstat(path.join(repo.mainRoot, '.git'))).isDirectory());
    assert.ok((await lstat(path.join(repo.roots['feat-a']!, '.git'))).isFile());
    const reg = path.join(repo.commonDir, 'worktrees', 'feat-a');
    assert.equal(await readFile(path.join(reg, 'gitdir'), 'utf8'), `${path.join(repo.roots['feat-a']!, '.git')}\n`);
    assert.equal(await readFile(path.join(reg, 'HEAD'), 'utf8'), 'ref: refs/heads/feat/a\n');
    assert.equal(await readFile(path.join(reg, 'commondir'), 'utf8'), '../..\n');
    assert.equal(await readFile(path.join(repo.roots['feat-a']!, '.git'), 'utf8'), `gitdir: ${reg}\n`);
    assert.match(await readFile(path.join(repo.commonDir, 'worktrees', 'det', 'HEAD'), 'utf8'), /^[0-9a-f]{40}\n$/);
  });
});

// ---- AC-15：主の checkout から ----

test('D0019-AC-15: 主の checkout から、.git/worktrees/*/gitdir に登録された別の worktree の work_dir が場所になる。ブランチ名が付く', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-a', branch: 'feat/a' }, { name: 'fix-b', branch: 'fix/b' }]);
    const found = await find(repo.mainRoot, SETTING, OPTS);
    assert.deepEqual(keysOf(found), ['wt.feat-a', 'wt.fix-b']);
    assert.equal(found.omitted, 0);
    const a = found.places.find((p) => p.key === 'wt.feat-a')!;
    assert.equal(a.label, 'feat/a');
    assert.equal(a.workDirAbs, path.join(repo.roots['feat-a']!, 'docs', 'pipeline'));
    assert.equal(found.places.find((p) => p.key === 'wt.fix-b')!.label, 'fix/b');
  });
});

test('D0019-AC-15: detached HEAD の worktree は、ブランチ名の代わりに HEAD の先頭 7 文字の短い ID が付く（フォルダ名ではない）', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'det', dir: 'det-dir', branch: null }]);
    const found = await find(repo.mainRoot, SETTING, OPTS);
    assert.deepEqual(found.places.map((p) => [p.key, p.label]), [['wt.det', '0123456']]);
  });
});

test('D0019-AC-15: 登録の HEAD が読めない（消えた・壊れた）worktree は、見分けがつくよう worktree のフォルダ名を最後の手段にする（場所からは外さない）', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'nohead', dir: 'nohead-dir' }, { name: 'junk', dir: 'junk-dir' }]);
    await rm(path.join(repo.commonDir, 'worktrees', 'nohead', 'HEAD'));
    await writeFile(path.join(repo.commonDir, 'worktrees', 'junk', 'HEAD'), 'こわれた HEAD\n');
    const found = await find(repo.mainRoot, SETTING, OPTS);
    assert.deepEqual(found.places.map((p) => [p.key, p.label]).sort(), [['wt.junk', 'junk-dir'], ['wt.nohead', 'nohead-dir']]);
  });
});

test('D0019-AC-15: work_dir の設定は、その worktree の根に当てはめる（設定を変えると、その場所の work_dir になる）', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-a' }]);
    const root = repo.roots['feat-a']!;
    await put(path.join(root, 'records', 'state.json'), stateJson({}));
    const found = await find(repo.mainRoot, 'records', OPTS);
    assert.deepEqual(found.places.map((p) => p.workDirAbs), [path.join(root, 'records')]);
  });
});

test('D0019-AC-15: work_dir が無い（run が無い）worktree は場所にしない・数にも入れない', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'with' }, { name: 'without', workDir: false }]);
    const found = await find(repo.mainRoot, SETTING, { limit: 1, ignoreCase: false });
    assert.deepEqual(keysOf(found), ['wt.with']);
    assert.equal(found.omitted, 0, 'run の無い worktree は省いた数に入れない');
  });
});

// ---- AC-16：linked worktree から ----

test('D0019-AC-16: ワークスペースが linked worktree（.git がファイル）のとき、gitdir をたどって主の checkout とほかの worktree も出る。自分自身は出ない', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-a', branch: 'feat/a' }, { name: 'other', branch: 'other' }]);
    const found = await find(repo.roots['feat-a']!, SETTING, OPTS);
    assert.deepEqual(keysOf(found), ['main', 'wt.other']);
    const main = found.places.find((p) => p.key === 'main')!;
    assert.equal(main.label, 'main');
    assert.equal(main.workDirAbs, path.join(repo.mainRoot, 'docs', 'pipeline'));
    assert.ok(!found.places.some((p) => p.workDirAbs.startsWith(repo.roots['feat-a']!)), '自分自身は重ならない');
  });
});

test('D0019-AC-16: commondir が絶対パスで書かれていても解ける', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-a' }, { name: 'other' }]);
    await writeFile(path.join(repo.commonDir, 'worktrees', 'feat-a', 'commondir'), `${repo.commonDir}\n`);
    const found = await find(repo.roots['feat-a']!, SETTING, OPTS);
    assert.deepEqual(keysOf(found), ['main', 'wt.other']);
  });
});

test('D0019-AC-16: commondir が相対パス（../..）でも解ける（git が実際に書く形）', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-a' }]);
    const found = await find(repo.roots['feat-a']!, SETTING, OPTS);
    assert.deepEqual(keysOf(found), ['main']);
  });
});

// ---- AC-17：git の外・壊れた登録 ----

async function emptyFolder(base: string): Promise<string> {
  await mkdir(path.join(base, 'main'), { recursive: true });
  return path.join(base, 'main');
}

const NO_GIT_CASES: [string, (base: string) => Promise<string>][] = [
  ['.git が無い（git のリポジトリでない）', emptyFolder],
  [
    'worktrees/ が無い',
    async (base) => {
      const root = await emptyFolder(base);
      await put(path.join(root, '.git', 'HEAD'), 'ref: refs/heads/main\n');
      return root;
    },
  ],
  [
    'worktrees が（フォルダでなく）ファイル',
    async (base) => {
      const root = await emptyFolder(base);
      await put(path.join(root, '.git', 'worktrees'), 'x');
      return root;
    },
  ],
  [
    '.git ファイルが壊れている（gitdir: が無い）',
    async (base) => {
      const root = await emptyFolder(base);
      await put(path.join(root, '.git'), 'これは .git ファイルではない\n');
      return root;
    },
  ],
  [
    '.git ファイルの gitdir の先が無い',
    async (base) => {
      const root = await emptyFolder(base);
      await put(path.join(root, '.git'), `gitdir: ${path.join(base, 'nowhere', '.git', 'worktrees', 'x')}\n`);
      return root;
    },
  ],
  [
    '.git ファイルが空',
    async (base) => {
      const root = await emptyFolder(base);
      await put(path.join(root, '.git'), '');
      return root;
    },
  ],
  [
    '.git ファイルが大きすぎる（4 KiB 超）',
    async (base) => {
      const root = await emptyFolder(base);
      await put(path.join(root, '.git'), `gitdir: ${'a'.repeat(10_000)}\n`);
      return root;
    },
  ],
];

for (const [label, build] of NO_GIT_CASES) {
  test(`D0019-AC-17: ${label}とき、別の worktree は無いものとして扱い、例外を出さない`, async () => {
    await withTempDir(async (base) => {
      const root = await build(base);
      assert.deepEqual(await find(root, SETTING, OPTS), EMPTY);
    });
  });
}

const BROKEN_REGISTRATIONS: [string, string, string][] = [
  ['gitdir が空', 'gitdir', ''],
  ['gitdir が壊れている（制御文字）', 'gitdir', '\u0000\u0001\u0002 \n'],
  ['gitdir が大きすぎる（4 KiB 超）', 'gitdir', `${'a'.repeat(10_000)}\n`],
  ['gitdir の行が改行だけ', 'gitdir', '\n\n'],
];

for (const [label, file, content] of BROKEN_REGISTRATIONS) {
  test(`D0019-AC-17: 登録が壊れているとき（${label}）、その worktree は場所にならず、ほかの worktree には影響せず、例外を出さない`, async () => {
    await withTempDir(async (base) => {
      const repo = await makeRepo(base, [{ name: 'bad' }, { name: 'ok' }]);
      await writeFile(path.join(repo.commonDir, 'worktrees', 'bad', file), content);
      const found = await find(repo.mainRoot, SETTING, OPTS);
      assert.deepEqual(keysOf(found), ['wt.ok']);
    });
  });
}

test('D0019-AC-17: 読む口がどれも失敗しても（権限がない・途中で消えた）、空を返して例外を出さない', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-a' }]);
    const boom = async (): Promise<never> => {
      throw Object.assign(new Error('EACCES'), { code: 'EACCES' });
    };
    const fs = { readFile: boom, readdir: boom, stat: boom, lstat: boom, realpath: boom };
    assert.deepEqual(await find(repo.mainRoot, SETTING, { ...OPTS, fs }), EMPTY);
  });
});

test('D0019-AC-17: 登録名が安全でない（パスに化ける文字）ものは、読まずに外す', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'ok' }, { name: 'a b' }]);
    const found = await find(repo.mainRoot, SETTING, OPTS);
    assert.deepEqual(keysOf(found), ['wt.ok']);
  });
});

// ---- AC-18：受け入れの確かめ ----

type Break = (repo: Awaited<ReturnType<typeof makeRepo>>, base: string) => Promise<void>;
const REJECTED: [string, Break][] = [
  [
    '登録されたパスが実在しない（消した worktree）',
    async (repo) => {
      await rm(repo.roots.bad!, { recursive: true, force: true });
    },
  ],
  [
    '登録されたパスが相対パス',
    async (repo) => {
      await writeFile(path.join(repo.commonDir, 'worktrees', 'bad', 'gitdir'), '../bad/.git\n');
    },
  ],
  [
    '.git が別の登録を指している（指し返していない）',
    async (repo) => {
      await writeFile(path.join(repo.roots.bad!, '.git'), `gitdir: ${path.join(repo.commonDir, 'worktrees', 'ok')}\n`);
    },
  ],
  [
    '.git が存在しない登録を指している',
    async (repo) => {
      await writeFile(path.join(repo.roots.bad!, '.git'), `gitdir: ${path.join(repo.commonDir, 'worktrees', 'nothing')}\n`);
    },
  ],
  [
    'worktree に .git が無い',
    async (repo) => {
      await rm(path.join(repo.roots.bad!, '.git'));
    },
  ],
  [
    'worktree の .git がファイルでなくフォルダ',
    async (repo) => {
      await rm(path.join(repo.roots.bad!, '.git'));
      await mkdir(path.join(repo.roots.bad!, '.git'));
    },
  ],
  [
    '.git ファイルが壊れている',
    async (repo) => {
      await writeFile(path.join(repo.roots.bad!, '.git'), 'ゴミ\n');
    },
  ],
];

for (const [label, breakIt] of REJECTED) {
  test(`D0019-AC-18: 場所にしない：${label}`, async () => {
    await withTempDir(async (base) => {
      const repo = await makeRepo(base, [{ name: 'ok' }, { name: 'bad' }]);
      await breakIt(repo, base);
      const found = await find(repo.mainRoot, SETTING, OPTS);
      assert.deepEqual(keysOf(found), ['wt.ok']);
    });
  });
}

test('D0019-AC-18: 登録されたパスが別の worktree の根を指しているだけ（自分の登録を指し返さない）ものは場所にしない', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'ok' }, { name: 'bad' }]);
    // bad の登録が ok の根を指す（ok の .git は ok の登録を指すので、指し返しが合わない）
    await writeFile(path.join(repo.commonDir, 'worktrees', 'bad', 'gitdir'), `${path.join(repo.roots.ok!, '.git')}\n`);
    const found = await find(repo.mainRoot, SETTING, OPTS);
    assert.deepEqual(keysOf(found), ['wt.ok']);
  });
});

test('D0019-AC-18: work_dir が無い worktree は場所にしない', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'ok' }, { name: 'bad', workDir: false }]);
    assert.deepEqual(keysOf(await find(repo.mainRoot, SETTING, OPTS)), ['wt.ok']);
  });
});

for (const [label, setting] of [
  ['..', '..'],
  ['../x', '../x'],
  ['docs/../..', 'docs/../..'],
  ['絶対パス（worktree の外）', 'ABSOLUTE_OUTSIDE'],
] as const) {
  test(`D0019-AC-18: work_dir の設定が worktree の外を指すときは、どの worktree も場所にしない：${label}`, async () => {
    await withTempDir(async (base) => {
      const repo = await makeRepo(base, [{ name: 'feat-a' }, { name: 'feat-b' }]);
      const outside = path.join(base, 'elsewhere');
      await put(path.join(outside, 'state.json'), stateJson({}));
      await put(path.join(base, 'x', 'state.json'), stateJson({}));
      const use = setting === 'ABSOLUTE_OUTSIDE' ? outside : setting;
      assert.deepEqual(await find(repo.mainRoot, use, OPTS), EMPTY);
    });
  });
}

test('D0019-AC-18: work_dir が symlink で worktree の外へ出るものは場所にしない', async (t) => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'ok' }, { name: 'escape', workDir: false }]);
    const outside = path.join(base, 'outside');
    await put(path.join(outside, 'pipeline', 'state.json'), stateJson({}));
    try {
      await symlink(outside, path.join(repo.roots.escape!, 'docs'), 'dir');
    } catch {
      t.skip('この環境では symlink を作れない');
      return;
    }
    assert.deepEqual(keysOf(await find(repo.mainRoot, SETTING, OPTS)), ['wt.ok']);
  });
});

// ---- AC-19：上限 ----

async function pin(file: string, iso: string): Promise<void> {
  const when = new Date(iso);
  await utimes(file, when, when);
}

test('D0019-AC-19: worktree が 10 個あるとき、更新が新しい方から 8 個だけ読み、省いた数が 2 になる', async () => {
  await withTempDir(async (base) => {
    const names = Array.from({ length: 10 }, (_, i) => `w${String(i + 1).padStart(2, '0')}`);
    const repo = await makeRepo(base, names.map((name) => ({ name })));
    for (const [i, name] of names.entries()) {
      const work = path.join(repo.roots[name]!, 'docs', 'pipeline');
      const iso = `2026-10-${String(i + 1).padStart(2, '0')}T00:00:00Z`;
      await pin(path.join(work, 'state.json'), iso);
      await pin(work, iso);
    }
    const found = await find(repo.mainRoot, SETTING, { limit: 8, ignoreCase: false });
    assert.deepEqual(found.places.map((p) => p.key), ['w10', 'w09', 'w08', 'w07', 'w06', 'w05', 'w04', 'w03'].map((n) => `wt.${n}`), '更新の新しい順');
    assert.equal(found.omitted, 2);
  });
});

test('D0019-AC-19: 並びは work_dir と state.json の新しい方の更新時刻で決める（state.json だけが新しくても新しい扱い）', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'dir-new' }, { name: 'file-new' }, { name: 'old' }]);
    const stamp = async (name: string, dirIso: string, fileIso: string) => {
      const work = path.join(repo.roots[name]!, 'docs', 'pipeline');
      await pin(path.join(work, 'state.json'), fileIso);
      await pin(work, dirIso);
    };
    await stamp('old', '2026-10-01T00:00:00Z', '2026-10-01T00:00:00Z');
    await stamp('dir-new', '2026-10-05T00:00:00Z', '2026-10-02T00:00:00Z');
    await stamp('file-new', '2026-10-03T00:00:00Z', '2026-10-09T00:00:00Z');
    const found = await find(repo.mainRoot, SETTING, { limit: 2, ignoreCase: false });
    assert.deepEqual(found.places.map((p) => p.key), ['wt.file-new', 'wt.dir-new']);
    assert.equal(found.omitted, 1);
  });
});

test('D0019-AC-19: 8 個以下なら省かない', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, Array.from({ length: 8 }, (_, i) => ({ name: `w${i}` })));
    const found = await find(repo.mainRoot, SETTING, OPTS);
    assert.equal(found.places.length, 8);
    assert.equal(found.omitted, 0);
  });
});

// ---- 2版目：いまの checkout のブランチ名（findCurrentLabel）----
// 行の「ブランチ」は、いまの work_dir の行にも出す。ブランチ名か短い ID。git の外・読めないときは null（項目ごと省く）。

type FindCurrentLabel = (workspaceRoot: string, opts?: { fs?: unknown }) => Promise<string | null>;
const currentLabel: FindCurrentLabel = async (root, opts) =>
  ((await import('./fsWorktrees.ts')) as unknown as { findCurrentLabel: FindCurrentLabel }).findCurrentLabel(root, opts);

test('D0019-AC-03: 主の checkout（.git がフォルダ）のブランチ名が取れる。detached HEAD は先頭 7 文字の短い ID', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, []);
    assert.equal(await currentLabel(repo.mainRoot), 'main');
    await writeFile(path.join(repo.commonDir, 'HEAD'), '0123456789abcdef0123456789abcdef01234567\n');
    assert.equal(await currentLabel(repo.mainRoot), '0123456');
    await writeFile(path.join(repo.commonDir, 'HEAD'), 'ref: refs/heads/feat/export-csv\n');
    assert.equal(await currentLabel(repo.mainRoot), 'feat/export-csv');
  });
});

test('D0019-AC-03: linked worktree（.git がファイル）のブランチ名は、gitdir の先の HEAD から取れる。detached HEAD は短い ID', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-a', branch: 'feat/a' }, { name: 'det', branch: null }]);
    assert.equal(await currentLabel(repo.roots['feat-a']!), 'feat/a');
    assert.equal(await currentLabel(repo.roots.det!), '0123456');
  });
});

const NO_LABEL: [string, (base: string) => Promise<string>][] = [
  ['git の外（.git が無い）', async (base) => (await mkdir(path.join(base, 'plain'), { recursive: true }), path.join(base, 'plain'))],
  [
    '.git はあるが HEAD が無い',
    async (base) => {
      await mkdir(path.join(base, 'p', '.git'), { recursive: true });
      return path.join(base, 'p');
    },
  ],
  [
    'HEAD が壊れている',
    async (base) => {
      await put(path.join(base, 'p', '.git', 'HEAD'), 'こわれた\n');
      return path.join(base, 'p');
    },
  ],
  [
    'HEAD が大きすぎる（4 KiB 超）',
    async (base) => {
      await put(path.join(base, 'p', '.git', 'HEAD'), `ref: refs/heads/${'a'.repeat(10_000)}\n`);
      return path.join(base, 'p');
    },
  ],
  [
    '.git ファイルが壊れている',
    async (base) => {
      await put(path.join(base, 'p', '.git'), 'ゴミ\n');
      return path.join(base, 'p');
    },
  ],
  [
    '.git ファイルの gitdir の先が無い',
    async (base) => {
      await put(path.join(base, 'p', '.git'), `gitdir: ${path.join(base, 'nowhere')}\n`);
      return path.join(base, 'p');
    },
  ],
];

for (const [label, build] of NO_LABEL) {
  test(`D0019-AC-03: ${label}とき、ブランチ名は null（項目ごと省く）で、例外を出さない`, async () => {
    await withTempDir(async (base) => {
      assert.equal(await currentLabel(await build(base)), null);
    });
  });
}

test('D0019-AC-03: 読む口がどれも失敗しても（権限がない）、ブランチ名は null で、例外を出さない', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, []);
    const boom = async (): Promise<never> => {
      throw Object.assign(new Error('EACCES'), { code: 'EACCES' });
    };
    assert.equal(await currentLabel(repo.mainRoot, { fs: { readFile: boom, readdir: boom, stat: boom, lstat: boom, realpath: boom } }), null);
  });
});

test('D0019-AC-32: ブランチ名のために読むのは .git と HEAD だけ（git の設定・worktree の他のファイルは読まない）', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-a', branch: 'feat/a' }]);
    for (const root of [repo.mainRoot, repo.roots['feat-a']!]) {
      const rec = recordingFs();
      assert.ok((await currentLabel(root, { fs: rec.fs })) !== null);
      const reg = path.join(repo.commonDir, 'worktrees', 'feat-a');
      const allowed = new Set([path.join(root, '.git'), path.join(root, '.git', 'HEAD'), reg, path.join(reg, 'HEAD')]);
      assert.deepEqual(rec.paths().filter((p) => !allowed.has(path.normalize(p))), [], '許す一覧の外のパスを読んでいない');
      assert.ok(!rec.paths('readFile').some((p) => /config|README\.md|state\.json/.test(p)));
      assert.ok(rec.calls.every((c) => ['readFile', 'readdir', 'stat', 'lstat', 'realpath'].includes(c.op)));
    }
  });
});

// ---- AC-32：読むものを絞る ----

test('D0019-AC-32: 読むのは .git・gitdir・commondir・HEAD・worktrees/ の一覧・各 worktree の .git・work_dir の stat だけ（git の設定・worktree の他のファイルは読まない）', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-a', branch: 'feat/a' }, { name: 'feat-b', branch: null }]);
    const rec = recordingFs();
    const found = await find(repo.mainRoot, SETTING, { ...OPTS, fs: rec.fs });
    assert.equal(found.places.length, 2, '読めている');

    const allowed = new Set<string>([repo.commonDir, path.join(repo.commonDir, 'HEAD'), path.join(repo.commonDir, 'worktrees')]);
    const roots = [repo.mainRoot, ...Object.values(repo.roots)];
    for (const r of roots) {
      for (const rel of ['', '.git', 'docs/pipeline', 'docs/pipeline/state.json']) allowed.add(path.join(r, rel));
    }
    for (const n of Object.keys(repo.roots)) {
      for (const f of ['', 'gitdir', 'HEAD', 'commondir']) allowed.add(path.join(repo.commonDir, 'worktrees', n, f));
    }
    const outside = rec.paths().filter((p) => !allowed.has(path.normalize(p)));
    assert.deepEqual(outside, [], '許す一覧の外のパスを読んでいない');

    const reads = rec.paths('readFile').map((p) => path.relative(base, p).split(path.sep).join('/'));
    for (const must of ['main/.git/worktrees/feat-a/gitdir', 'main/.git/worktrees/feat-a/HEAD', 'feat-a/.git']) {
      assert.ok(reads.includes(must), `${must} を読む`);
    }
    for (const never of ['main/.git/config', 'feat-a/README.md', 'feat-a/docs/pipeline/other.md']) {
      assert.ok(!reads.includes(never), `${never} は読まない`);
    }
    assert.ok(rec.calls.every((c) => ['readFile', 'readdir', 'stat', 'lstat', 'realpath'].includes(c.op)));
  });
});

test('D0019-AC-32: linked worktree から始めても、読むのは同じ範囲だけ（commondir と登録の一覧、各 worktree の .git）', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-a' }, { name: 'other' }]);
    const rec = recordingFs();
    await find(repo.roots['feat-a']!, SETTING, { ...OPTS, fs: rec.fs });
    const reads = rec.paths('readFile').map((p) => path.relative(base, p).split(path.sep).join('/'));
    for (const never of ['main/.git/config', 'main/README.md', 'other/README.md', 'feat-a/README.md']) {
      assert.ok(!reads.includes(never), `${never} は読まない`);
    }
    assert.ok(reads.includes('main/.git/worktrees/feat-a/commondir'), 'commondir を読む');
    assert.ok(rec.paths('readdir').every((p) => p === path.join(repo.commonDir, 'worktrees')), 'フォルダの一覧を取るのは worktrees/ だけ');
  });
});
