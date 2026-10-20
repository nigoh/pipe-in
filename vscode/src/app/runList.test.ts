// 実行の一覧のユースケース（D0019）：場所ごとに記録を読み、行にして並べ、選びを決める。口（RunsSource）は手で書いた偽物。
// 新しい部品（app/runList.ts）は、呼んだところで落ちるように、テストの中で読み込む。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { logText, promptLine, stateJson } from '../test/fixtures.ts';
import { clockAt } from '../test/liveFixtures.ts';

const app = () => import('./runList.ts');

interface Place {
  key: string;
  label: string | null;
  workDirAbs: string;
}
interface FakeRun {
  id: string;
  stateJson: string | null;
  stageLogs: { fileName: string; text: string }[];
  /** 00_input.md の先頭（名前が state.json に無い run だけ。2版目） */
  memoHead?: string | null;
}
interface FakePlaceRuns {
  runs: FakeRun[];
  archiveOmitted: number;
}

// 2版目：場所の label は「ブランチ名か短い ID」で、いまの work_dir にも入る（git の外は null）。別の worktree かどうかは場所の key で決まる
const HERE: Place = { key: 'here', label: 'main', workDirAbs: path.resolve('/ws/docs/pipeline') };
const WT: Place = { key: 'wt.feat-x', label: 'feat/x', workDirAbs: path.resolve('/wt/feat-x/docs/pipeline') };

const PENDING = { stage: 'requirements', doc: 'docs/pipeline/01_requirements.md', session_id: 's' };
const OPEN_LOG = [{ fileName: '01_requirements.jsonl', text: logText([promptLine('requirements')]) }];
const run = (id: string, state: string | null, stageLogs: FakeRun['stageLogs'] = []): FakeRun => ({ id, stateJson: state, stageLogs });

/** 偽の RunsSource。showOthers=false のときは、いまの work_dir の場所だけを返す（本物の createFsRunsSource と同じ約束）。 */
function fakeSource(spec: {
  places?: Place[];
  runs: Record<string, FakePlaceRuns | 'throw'>;
  omittedWorktrees?: number;
  placesThrows?: boolean;
}) {
  const calls = { places: [] as boolean[], runs: [] as string[] };
  return {
    calls,
    async places(showOthers: boolean) {
      calls.places.push(showOthers);
      if (spec.placesThrows) throw new Error('places が読めない');
      const all = spec.places ?? [HERE];
      return { places: showOthers ? all : all.filter((p) => p.key === 'here'), omittedWorktrees: showOthers ? (spec.omittedWorktrees ?? 0) : 0 };
    },
    async runs(place: Place): Promise<FakePlaceRuns> {
      calls.runs.push(place.key);
      const r = spec.runs[place.key];
      if (r === undefined || r === 'throw') throw new Error(`${place.key} が読めない`);
      return r;
    },
  };
}

/** 並びと選びを確かめるための見本。確認待ち 2・動いている 1・終わった 1・前の実行 1。 */
function sampleSpec(over: { archiveOmitted?: number; wtArchiveOmitted?: number; omittedWorktrees?: number } = {}) {
  return {
    places: [HERE, WT],
    omittedWorktrees: over.omittedWorktrees ?? 0,
    runs: {
      here: {
        runs: [
          run('', stateJson({ final: 'PASSED', updatedAt: '2026-10-17T09:00:00' })),
          run('diagrams', stateJson({ pipe: 'diagrams', updatedAt: '2026-10-17T11:00:00' }), OPEN_LOG),
          run('archive/20261016-090000', stateJson({ final: 'TEST_FAILED', updatedAt: '2026-10-16T08:00:00' })),
        ],
        archiveOmitted: over.archiveOmitted ?? 0,
      },
      'wt.feat-x': {
        runs: [
          run('', stateJson({ pipe: 'spec-qa', updatedAt: '2026-10-17T12:00:00', pendingReview: PENDING })),
          run('survey', stateJson({ pipe: 'survey', updatedAt: '2026-10-17T10:00:00', pendingReview: PENDING })),
        ],
        archiveOmitted: over.wtArchiveOmitted ?? 0,
      },
    } as Record<string, FakePlaceRuns>,
  };
}

const load = async (spec: Parameters<typeof fakeSource>[0], showOthers = true) => {
  const { loadRunList } = await app();
  const source = fakeSource(spec);
  const list = await loadRunList(source, { showOthers, clock: clockAt(0) });
  return { list, source };
};
const keysOf = (list: { entries: { row: { key: string } }[] }): string[] => list.entries.map((e) => e.row.key);

// ---- AC-43：一覧は run が 0・1・2 つ以上のどれでも出す（1回目の AC-02「1 つだけなら出さない」は廃止）----

const WORK_DIR_SETTING = 'docs/pipeline';

test('D0019-AC-43: toListView は run が 0 のときも 1 つのときも一覧を返す（null にしない）。記録なしの行は行に入れない', async () => {
  const { toListView } = await app();
  const { list: one } = await load({ runs: { here: { runs: [run('', stateJson({}))], archiveOmitted: 0 } } });
  assert.equal(one.entries.length, 1);
  const oneView = toListView(one, 'here|', WORK_DIR_SETTING);
  assert.ok(oneView !== null && oneView !== undefined);
  assert.equal(oneView.rows.length, 1);
  assert.equal(oneView.selected, 'here|');
  const { list: none } = await load({ runs: { here: { runs: [], archiveOmitted: 0 } } });
  assert.equal(none.entries.length, 0, '記録なしの行は一覧に入れない');
  const noneView = toListView(none, 'here|', WORK_DIR_SETTING);
  assert.ok(noneView !== null && noneView !== undefined, '0 件でも一覧の入れ物を返す（画面に「実行がありません」を出す）');
  assert.deepEqual(noneView.rows, []);
  assert.equal(noneView.selected, 'here|');
});

test('D0019-AC-43: run が 2 つ以上のとき、run の数だけ行が出て、選んでいる key と作業フォルダ（設定のまま）が入る', async () => {
  const { toListView } = await app();
  const { list } = await load(sampleSpec());
  assert.equal(list.entries.length, 5);
  const view = toListView(list, 'here|diagrams', WORK_DIR_SETTING);
  assert.ok(view);
  assert.equal(view.rows.length, 5);
  assert.equal(view.selected, 'here|diagrams');
  assert.equal(view.workDir, WORK_DIR_SETTING);
  assert.deepEqual(view.rows.map((r) => r.key), keysOf(list));
});

test('D0019-AC-43: 作業フォルダの表示は、設定の値のまま（相対パス。絶対パスにしない）', async () => {
  const { toListView } = await app();
  const { list } = await load(sampleSpec());
  assert.equal(toListView(list, 'here|', 'records/pipe')?.workDir, 'records/pipe');
});

test('D0019-AC-43: 直下の run が無く、パイプが 2 つなら一覧に 2 行（記録なしの行は数えない）', async () => {
  const { toListView } = await app();
  const { list } = await load({
    runs: { here: { runs: [run('a', stateJson({ pipe: 'a' })), run('b', stateJson({ pipe: 'b' }))], archiveOmitted: 0 } },
  });
  assert.equal(toListView(list, 'here|a', WORK_DIR_SETTING)?.rows.length, 2);
});

// ---- AC-09：並び ----

test('D0019-AC-09: loadRunList の並びは 確認待ち → 動いている → 終わった。同じ状態のなかは新しい順', async () => {
  const { list } = await load(sampleSpec());
  assert.deepEqual(keysOf(list), ['wt.feat-x|', 'wt.feat-x|survey', 'here|diagrams', 'here|', 'here|archive/20261016-090000']);
});

test('D0019-AC-09: 選びを変えても、一覧の並びは変わらない（chooseEntry も toListView も並べ替えない）', async () => {
  const { chooseEntry, toListView } = await app();
  const { list } = await load(sampleSpec());
  const before = keysOf(list);
  for (const selected of ['here|', 'wt.feat-x|survey', 'here|archive/20261016-090000', null, 'here|nothing']) {
    chooseEntry(list, selected, HERE);
    const view = toListView(list, selected ?? 'here|', WORK_DIR_SETTING);
    assert.deepEqual(view?.rows.map((r) => r.key), before);
  }
  assert.deepEqual(keysOf(list), before);
});

// ---- AC-15：別の worktree ----

test('D0019-AC-15: 別の worktree の行だけ other が真。ブランチ名（branch）は、別の worktree もいまの work_dir も場所の label から入る', async () => {
  const { list } = await load(sampleSpec());
  const byKey = Object.fromEntries(list.entries.map((e) => [e.row.key, [e.row.branch, e.row.other]]));
  assert.deepEqual(byKey['wt.feat-x|'], ['feat/x', true]);
  assert.deepEqual(byKey['wt.feat-x|survey'], ['feat/x', true]);
  assert.deepEqual(byKey['here|'], ['main', false]);
  assert.deepEqual(byKey['here|diagrams'], ['main', false]);
  assert.deepEqual(byKey['here|archive/20261016-090000'], ['main', false]);
});

test('D0019-AC-03: git の外（いまの work_dir の場所の label が null）の行は、branch が null で other が偽', async () => {
  const outside: Place = { ...HERE, label: null };
  const { list } = await load({ places: [outside], runs: { here: { runs: [run('', stateJson({}))], archiveOmitted: 0 } } });
  assert.deepEqual(list.entries.map((e) => [e.row.branch, e.row.other]), [[null, false]]);
});

test('D0019-AC-52: 場所の中の run が持つ memoHead（00_input.md の先頭）が、行のセッション名の元になる（name が無いとき）', async () => {
  const { list } = await load({
    runs: {
      here: {
        runs: [
          { ...run('', stateJson({})), memoHead: '# 仕様の QA を回す\n本文' },
          { ...run('named', stateJson({ pipe: 'named', name: '付けた名前' })), memoHead: null },
          { ...run('bare', stateJson({ pipe: 'bare' })), memoHead: null },
        ],
        archiveOmitted: 0,
      },
    },
  });
  const session = Object.fromEntries(list.entries.map((e) => [e.row.key, e.row.session]));
  assert.deepEqual(session, { 'here|': '仕様の QA を回す', 'here|named': '付けた名前', 'here|bare': 'bare' });
});

test('D0019-AC-15: 行のパイプ名は記録の pipe。別の worktree の同じ id の run も、場所が違えば別の行になる', async () => {
  const { list } = await load({
    places: [HERE, WT],
    runs: {
      here: { runs: [run('', stateJson({ pipe: 'dev', final: 'PASSED' }))], archiveOmitted: 0 },
      'wt.feat-x': { runs: [run('', stateJson({ pipe: 'spec-qa', final: 'PASSED' }))], archiveOmitted: 0 },
    },
  });
  assert.deepEqual(list.entries.map((e) => e.row.pipe).sort(), ['spec-qa', '開発フロー']);
  assert.equal(new Set(keysOf(list)).size, 2);
});

test('D0019-AC-15: showOthers=false で、別の worktree は出ない（口に false を渡し、いまの work_dir だけを読む）', async () => {
  const { list, source } = await load(sampleSpec(), false);
  assert.deepEqual(source.calls.places, [false]);
  assert.deepEqual(source.calls.runs, ['here']);
  assert.ok(keysOf(list).every((k) => k.startsWith('here|')));
  assert.equal(list.omittedWorktrees, 0);
});

test('D0019-AC-15: hasRemote は「別の場所の行か archive の行がある」とき真（5 秒ごとの読み直しの要否に使う）', async () => {
  const hasRemote = async (spec: Parameters<typeof fakeSource>[0]) => (await load(spec)).list.hasRemote;
  assert.equal(await hasRemote(sampleSpec()), true);
  assert.equal(
    await hasRemote({ places: [HERE, WT], runs: { here: { runs: [run('', stateJson({}))], archiveOmitted: 0 }, 'wt.feat-x': { runs: [run('', stateJson({}))], archiveOmitted: 0 } } }),
    true,
    '別の場所の行',
  );
  assert.equal(
    await hasRemote({ runs: { here: { runs: [run('', stateJson({})), run('archive/20261016-090000', stateJson({ final: 'PASSED' }))], archiveOmitted: 0 } } }),
    true,
    'archive の行',
  );
  assert.equal(
    await hasRemote({ runs: { here: { runs: [run('', stateJson({})), run('diagrams', stateJson({ pipe: 'diagrams' }))], archiveOmitted: 0 } } }),
    false,
    'いまの work_dir の直下とパイプだけ',
  );
});

// ---- AC-10・AC-19：省いた数 ----

test('D0019-AC-10: archive を省いた数は、場所ごとに omitted に入る（場所の名前つき。省いていない場所は入れない）', async () => {
  const { list } = await load(sampleSpec({ archiveOmitted: 2, wtArchiveOmitted: 4 }));
  const shown = list.omitted.filter((o) => o.count > 0);
  assert.deepEqual(shown.sort((a, b) => a.count - b.count), [{ place: null, count: 2 }, { place: 'feat/x', count: 4 }]);
  const none = (await load(sampleSpec())).list.omitted.filter((o) => o.count > 0);
  assert.deepEqual(none, []);
});

test('D0019-AC-19: 別の worktree を省いた数が RunList の omittedWorktrees に入る', async () => {
  const { list } = await load(sampleSpec({ omittedWorktrees: 3 }));
  assert.equal(list.omittedWorktrees, 3);
  assert.equal((await load(sampleSpec())).list.omittedWorktrees, 0);
});

test('D0019-AC-19: toListView は省いた数をそのまま一覧に渡す', async () => {
  const { toListView } = await app();
  const { list } = await load(sampleSpec({ archiveOmitted: 2, wtArchiveOmitted: 4, omittedWorktrees: 3 }));
  const view = toListView(list, 'here|', WORK_DIR_SETTING);
  assert.equal(view?.omittedWorktrees, 3);
  assert.deepEqual(view?.omitted.filter((o) => o.count > 0).map((o) => o.count).sort(), [2, 4]);
});

// ---- AC-17：場所が読めなくても、いまの work_dir の行は出る ----

test('D0019-AC-17: 別の worktree の読み取りが失敗しても、その場所だけ飛ばして、いまの work_dir の行は出る（例外を出さない）', async () => {
  const spec = sampleSpec();
  const { list } = await load({ places: spec.places, runs: { ...spec.runs, 'wt.feat-x': 'throw' } });
  assert.deepEqual(keysOf(list), ['here|diagrams', 'here|', 'here|archive/20261016-090000']);
});

test('D0019-AC-17: 場所の一覧（places）が失敗しても、loadRunList は例外を出さず、chooseEntry はいまの work_dir の直下を返す', async () => {
  const { chooseEntry, toListView } = await app();
  const { list } = await load({ placesThrows: true, runs: {} });
  assert.deepEqual(list.entries, []);
  assert.deepEqual(toListView(list, 'here|', WORK_DIR_SETTING)?.rows, [], '一覧の入れ物は返る（行は無い）');
  assert.deepEqual(chooseEntry(list, null, HERE), { key: 'here|', dirAbs: HERE.workDirAbs });
});

test('D0019-AC-17: 別の worktree が 1 つも無い（空）ときは、いまの work_dir の行だけが出る', async () => {
  const { list } = await load({ places: [HERE], runs: { here: { runs: [run('', stateJson({})), run('a', stateJson({ pipe: 'a' }))], archiveOmitted: 0 } } });
  assert.deepEqual(keysOf(list).sort(), ['here|', 'here|a']);
  assert.equal(list.omittedWorktrees, 0);
});

test('D0019-AC-17: 記録が読めない run（stateJson が null・壊れた JSON）も、行として出る（組み立てが止まらない）', async () => {
  const { list } = await load({
    runs: { here: { runs: [run('', '{壊れた'), run('a', null), run('archive/20261016-090000', '[1,2]')], archiveOmitted: 0 } },
  });
  assert.equal(list.entries.length, 3);
  assert.ok(list.entries.every((e) => e.row.costText === '—'));
});

// ---- AC-20：パネルから来た key は、一覧にあるものだけ ----

test('D0019-AC-20: findEntry は、一覧にある key だけ返し、dirAbs は場所の work_dir の中になる', async () => {
  const { findEntry } = await app();
  const { list } = await load(sampleSpec());
  const here = findEntry(list, 'here|');
  assert.equal(here?.dirAbs, HERE.workDirAbs);
  assert.equal(findEntry(list, 'here|diagrams')?.dirAbs, path.join(HERE.workDirAbs, 'diagrams'));
  assert.equal(findEntry(list, 'wt.feat-x|survey')?.dirAbs, path.join(WT.workDirAbs, 'survey'));
  assert.equal(findEntry(list, 'wt.feat-x|')?.dirAbs, WT.workDirAbs);
  assert.equal(findEntry(list, 'here|archive/20261016-090000')?.dirAbs, path.join(HERE.workDirAbs, 'archive', '20261016-090000'));
  for (const e of list.entries) {
    const place = e.row.key.startsWith('wt.') ? WT : HERE;
    const rel = path.relative(place.workDirAbs, e.dirAbs);
    assert.ok(!rel.startsWith('..') && !path.isAbsolute(rel), `${e.row.key} の dirAbs は場所の work_dir の中`);
  }
});

const NOT_IN_LIST: [string, unknown][] = [
  ['一覧に無い id', 'here|nothing'],
  ['別の場所', 'wt.other|'],
  ['場所が違う同じ id', 'main|diagrams'],
  ['..', 'here|..'],
  ['../x', 'here|../x'],
  ['絶対パス', 'here|/etc/passwd'],
  ['絶対パスだけ', '/etc/passwd'],
  ['archive の外へ出る', 'here|archive/../x'],
  ['archive の日時が壊れている', 'here|archive/2026'],
  ['昔の形（id だけ）', 'diagrams'],
  ['昔の形（空の id）', ''],
  ['数', 3],
  ['null', null],
  ['オブジェクト', { key: 'here|' }],
];

for (const [label, key] of NOT_IN_LIST) {
  test(`D0019-AC-20: 一覧に無い・形の違う key は何も返さない（何も読まない）：${label}`, async () => {
    const { findEntry } = await app();
    const { list, source } = await load(sampleSpec());
    const readsBefore = source.calls.runs.length;
    assert.equal(findEntry(list, key as string), null);
    assert.equal(source.calls.runs.length, readsBefore, 'findEntry は口を呼ばない（直前の一覧で確かめるだけ）');
  });
}

test('D0019-AC-20: 一覧に紛れ込んだ形の違う key（口が ../ を含む id を返した）も、findEntry は通さない', async () => {
  const { findEntry, loadRunList } = await app();
  const source = fakeSource({
    runs: { here: { runs: [run('', stateJson({})), run('../escape', stateJson({ pipe: 'evil' }))], archiveOmitted: 0 } },
  });
  const list = await loadRunList(source, { showOthers: true, clock: clockAt(0) });
  assert.equal(findEntry(list, 'here|../escape'), null);
  assert.ok(findEntry(list, 'here|'), '正しい key は通る');
});

// ---- AC-23・AC-24：覚えた選び ----

test('D0019-AC-23: chooseEntry は、覚えた key が一覧にあればそれを選ぶ（別の worktree・archive の run でも）', async () => {
  const { chooseEntry } = await app();
  const { list } = await load(sampleSpec());
  assert.deepEqual(chooseEntry(list, 'wt.feat-x|survey', HERE), { key: 'wt.feat-x|survey', dirAbs: path.join(WT.workDirAbs, 'survey') });
  assert.deepEqual(chooseEntry(list, 'here|archive/20261016-090000', HERE), {
    key: 'here|archive/20261016-090000',
    dirAbs: path.join(HERE.workDirAbs, 'archive', '20261016-090000'),
  });
  assert.equal(chooseEntry(list, 'here|', HERE).key, 'here|');
});

test('D0019-AC-23: 覚えた key が一覧に無い（消えた・移った・worktree が無い・壊れている）と、今までの既定（いまの work_dir の最新）になる。例外を出さない', async () => {
  const { chooseEntry } = await app();
  const { list } = await load(sampleSpec());
  const expected = { key: 'here|diagrams', dirAbs: path.join(HERE.workDirAbs, 'diagrams') };
  for (const gone of ['here|gone', 'wt.removed|', 'wt.removed|survey', 'main|', '../x', 'here|../x', '', null, 'x|y|z']) {
    assert.deepEqual(chooseEntry(list, gone, HERE), expected, String(gone));
  }
});

test('D0019-AC-23: 既定は「いまの work_dir の（archive を除く）最新」。別の worktree の新しい run・archive の run は勝手に選ばない', async () => {
  const { chooseEntry } = await app();
  const { list } = await load(sampleSpec());
  // 別の worktree（12:00）のほうが新しく、いまの work_dir は diagrams（11:00）・直下（09:00）・archive
  assert.equal(chooseEntry(list, null, HERE).key, 'here|diagrams');
  const { list: onlyArchive } = await load({
    runs: {
      here: {
        runs: [run('', stateJson({ final: 'PASSED', updatedAt: '2026-10-01T00:00:00' })), run('archive/20261020-090000', stateJson({ final: 'PASSED', updatedAt: '2026-10-20T00:00:00' }))],
        archiveOmitted: 0,
      },
    },
  });
  assert.equal(chooseEntry(onlyArchive, null, HERE).key, 'here|', 'archive の run が新しくても選ばない');
});

test('D0019-AC-23: 既定で updated_at が同じなら直下（開発フロー）。読めない updated_at は新しいものに負ける', async () => {
  const { chooseEntry } = await app();
  const same = '2026-10-17T10:00:00';
  const { list: tie } = await load({
    runs: { here: { runs: [run('diagrams', stateJson({ pipe: 'diagrams', updatedAt: same })), run('', stateJson({ updatedAt: same }))], archiveOmitted: 0 } },
  });
  assert.equal(chooseEntry(tie, null, HERE).key, 'here|');
  const { list: unreadable } = await load({
    runs: { here: { runs: [run('', stateJson({ updatedAt: 'いつか' })), run('diagrams', stateJson({ pipe: 'diagrams', updatedAt: same }))], archiveOmitted: 0 } },
  });
  assert.equal(chooseEntry(unreadable, null, HERE).key, 'here|diagrams');
});

test('D0019-AC-23: いまの work_dir に run が 1 つも無いとき、chooseEntry は直下（記録なしの表示）を返す', async () => {
  const { chooseEntry } = await app();
  const { list } = await load({ places: [HERE, WT], runs: { here: { runs: [], archiveOmitted: 0 }, 'wt.feat-x': { runs: [run('', stateJson({}))], archiveOmitted: 0 } } });
  assert.deepEqual(chooseEntry(list, null, HERE), { key: 'here|', dirAbs: HERE.workDirAbs });
});

test('D0019-AC-24: 設定 pipe-in.workDir を変えた後の一覧（別の work_dir）には、覚えた選びが当てはまらなければ使われない', async () => {
  const { chooseEntry } = await app();
  const other: Place = { key: 'here', label: null, workDirAbs: path.resolve('/ws/records') };
  const { loadRunList } = await app();
  const source = fakeSource({
    places: [other],
    runs: { here: { runs: [run('', stateJson({ updatedAt: '2026-10-17T09:00:00' })), run('review', stateJson({ pipe: 'review', updatedAt: '2026-10-17T10:00:00' }))], archiveOmitted: 0 } },
  });
  const list = await loadRunList(source, { showOthers: true, clock: clockAt(0) });
  // 前の work_dir で覚えた選び（diagrams と別の worktree の run）は、新しい work_dir の候補に無い
  assert.deepEqual(chooseEntry(list, 'here|diagrams', other), { key: 'here|review', dirAbs: path.join(other.workDirAbs, 'review') });
  assert.deepEqual(chooseEntry(list, 'wt.feat-x|survey', other), { key: 'here|review', dirAbs: path.join(other.workDirAbs, 'review') });
  // 新しい work_dir の候補にもある key なら、それを使う
  assert.deepEqual(chooseEntry(list, 'here|', other), { key: 'here|', dirAbs: other.workDirAbs });
});

test('D0019-AC-24: showOthers を切った直後、覚えた選びが別の worktree の run だったときは既定に戻る（覚えた値は消さない）', async () => {
  const { chooseEntry } = await app();
  const { list } = await load(sampleSpec(), false);
  assert.equal(chooseEntry(list, 'wt.feat-x|survey', HERE).key, 'here|diagrams');
});
