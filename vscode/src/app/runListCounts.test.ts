// ステータスバーの件数（D0024・イシュー #44）の組み合わせの確かめ：偽の RunsSource（手で書いた口）を通して、
// 一覧の旗（hasOtherWorktree）・件数・ボタンが選びを覚える形・ステータスバーの文字と説明を見る。
// SDK・時計・子プロセスは使わない。見る run の写しも、偽の口の中の同じ run から作る（extension.ts は createFsWorkDirSource で読む）。
// ファイルは、前の版の記録の見本（tests/fixtures/pipe_in/）を previousRun が読むだけ（読むだけで書かない）。
// 新しい部品（domain/runList.ts の statusCounts・frontWaitingKey、app/runList.ts の hasOtherWorktree、view/statusBar.ts の件数の形）は、
// テストの中で読み込む（テスト先行のとき、まだ無い部品が呼んだところで落ちるようにしたため）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import type { WorkDirSource } from './refreshView.ts';
import { DIAGRAMS_STAGES, logText, promptLine, stageRunEntry, stateJson, usageSummaryDict } from '../test/fixtures.ts';
import { clockAt, fixtureSnapshot } from '../test/liveFixtures.ts';

const app = () => import('./runList.ts');
const domain = () => import('../domain/runList.ts');
const policy = () => import('./refreshPolicy.ts');
const selection = () => import('./selection.ts');
const statusBar = () => import('../view/statusBar.ts');
const refresh = () => import('./refreshView.ts');

interface Place {
  key: string;
  label: string | null;
  workDirAbs: string;
}
interface FakeRun {
  id: string;
  stateJson: string | null;
  stageLogs: { fileName: string; text: string }[];
  /** 00_input.md の先頭（名前が state.json に無い run だけ） */
  memoHead?: string | null;
}
interface FakePlaceRuns {
  runs: FakeRun[];
  archiveOmitted: number;
}
interface Spec {
  places?: Place[];
  runs: Record<string, FakePlaceRuns | 'throw'>;
  omittedWorktrees?: number;
  placesThrows?: boolean;
}

// 場所の label は「ブランチ名か短い ID」。別の worktree かどうかは場所の key で決まる
const HERE: Place = { key: 'here', label: 'feat/status-counts', workDirAbs: path.resolve('/ws/docs/pipeline') };
const WT: Place = { key: 'wt.feat-other', label: 'feat/other', workDirAbs: path.resolve('/wt/feat-other/docs/pipeline') };
const MAIN: Place = { key: 'main', label: 'main', workDirAbs: path.resolve('/main/docs/pipeline') };
const WORK_DIR_SETTING = 'docs/pipeline';
const MEMORY_KEY = 'pipe-in.selectedRun';

/** 偽の RunsSource。showOthers=false のときは、いまの work_dir の場所だけを返す（本物の createFsRunsSource と同じ約束）。 */
function fakeSource(spec: Spec) {
  return {
    async places(showOthers: boolean) {
      if (spec.placesThrows) throw new Error('places が読めない');
      const all = spec.places ?? [HERE];
      return { places: showOthers ? all : all.filter((p) => p.key === 'here'), omittedWorktrees: showOthers ? (spec.omittedWorktrees ?? 0) : 0 };
    },
    async runs(place: Place): Promise<FakePlaceRuns> {
      const r = spec.runs[place.key];
      if (r === undefined || r === 'throw') throw new Error(`${place.key} が読めない`);
      return r;
    },
  };
}

// ---- 記録の見本（手で書く）----

const T = (hhmm: string): string => `2026-10-17T${hhmm}:00`;
const PENDING = { stage: 'requirements', doc: 'docs/pipeline/01_requirements.md', session_id: 's' };

const pr = (...runs: FakeRun[]): FakePlaceRuns => ({ runs, archiveOmitted: 0 });
const run = (id: string, state: string | null, stageLogs: FakeRun['stageLogs'] = [], memoHead?: string | null): FakeRun => ({
  id,
  stateJson: state,
  stageLogs,
  ...(memoHead === undefined ? {} : { memoHead }),
});
/** 段のログに Prompt だけがある（動いている段）。 */
const promptOnly = (stage: string, seq = 1): FakeRun['stageLogs'] => [{ fileName: `${String(seq).padStart(2, '0')}_${stage}.jsonl`, text: logText([promptLine(stage)]) }];

/** 確認待ち（pending_review。開発フローの要件定義の確認）。 */
const waitingRun = (id: string, name: string, at: string): FakeRun => run(id, stateJson({ name, pendingReview: PENDING, updatedAt: at }));
/** 動いている（開発フロー。段のログに Prompt だけ）。 */
const runningRun = (id: string, name: string, at: string, stage = 'requirements', seq = 1): FakeRun =>
  run(id, stateJson({ name, updatedAt: at }), promptOnly(stage, seq));
/** 待ち（段の合間。final も確認待ちも動いているログも無い）。 */
const idleRun = (id: string, name: string, at: string): FakeRun =>
  run(id, stateJson({ name, updatedAt: at, runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }));
/** 終わった（final あり。archive の id でも使う）。 */
const doneRun = (id: string, name: string, at: string, final = 'PASSED', extra: { usageSummary?: unknown } = {}): FakeRun =>
  run(id, stateJson({ name, final, updatedAt: at, ...extra }));
/** name の無い前の版の記録（tests/fixtures/pipe_in/ の形）。名前は 00_input.md の先頭（memoHead）から取る。 */
const previousRun = (id: string, fixture: 'waiting' | 'running' | 'finished', memoHead: string | null): FakeRun => {
  const snap = fixtureSnapshot('pipe_in', fixture);
  return { id, stateJson: snap.stateJson, stageLogs: snap.stageLogs, memoHead };
};
/** パイプ diagrams の動いている run（段 draw が動いている）。 */
const diagramsRun = (): FakeRun =>
  run('diagrams', stateJson({ pipe: 'diagrams', name: '図を作る', stages: DIAGRAMS_STAGES, updatedAt: T('11:00') }), promptOnly('draw', 2));

/**
 * 見本の世界。いまの work_dir（here）に 終わった（利用枠つき）・動いている（パイプ）・archive、
 * 別の worktree に 確認待ち（前の版）・動いている（前の版）。
 */
function world(over: { here?: FakeRun[]; wt?: FakeRun[]; omittedWorktrees?: number } = {}): Spec {
  return {
    places: [HERE, WT],
    omittedWorktrees: over.omittedWorktrees ?? 0,
    runs: {
      here: pr(
        ...(over.here ?? [
          doneRun('', 'CSV 出力を足す', T('09:00'), 'PASSED', { usageSummary: usageSummaryDict() }),
          diagramsRun(),
          doneRun('archive/20261016-090000', 'きのうの実行', '2026-10-16T08:00:00', 'TEST_FAILED'),
        ]),
      ),
      [WT.key]: pr(...(over.wt ?? [previousRun('', 'waiting', '# 画面を直す\n本文'), previousRun('survey', 'running', '# ログイン不具合を調べる\n本文')])),
    },
  };
}

const load = async (spec: Spec, showOthers = true) => {
  const { loadRunList } = await app();
  return loadRunList(fakeSource(spec), { showOthers, clock: clockAt(0) });
};

/** 手で書いた偽の workspaceState（MemoryStore）。呼ばれた操作を全部記録する。 */
function fakeStore(initial: Record<string, unknown> = {}) {
  const data = new Map<string, unknown>(Object.entries(initial));
  const calls: [string, ...unknown[]][] = [];
  return {
    data,
    calls,
    get(key: string): unknown {
      calls.push(['get', key]);
      return data.get(key);
    },
    update(key: string, value: unknown): PromiseLike<void> {
      calls.push(['update', key, value]);
      data.set(key, value);
      return Promise.resolve();
    },
  };
}

// ---- 前提：偽の口の run が、期待した行になる（以降の表の土台）----

test('D0024-AC-45: 前提：見本の世界の run が、期待した状態・名前・今の段・ブランチの行になる（今のまま通る。守る）', async () => {
  const list = await load(world());
  const seen = list.entries.map((e) => [e.row.key, e.row.state, e.row.session, e.row.stage, e.row.branch, e.row.other, e.row.result]);
  assert.deepEqual(seen, [
    ['wt.feat-other|', 'waiting', '画面を直す', 'テスト先行', 'feat/other', true, null],
    ['here|diagrams', 'running', '図を作る', '図を描く', 'feat/status-counts', false, null],
    ['wt.feat-other|survey', 'running', 'ログイン不具合を調べる', '要件定義', 'feat/other', true, null],
    ['here|', 'done', 'CSV 出力を足す', '—', 'feat/status-counts', false, '合格'],
    ['here|archive/20261016-090000', 'done', 'きのうの実行', '—', 'feat/status-counts', false, '不合格'],
  ]);
});

// ---- AC-04：showOthers を切った一覧と、省いた別の worktree は件数に入らない ----

/** いまの work_dir に 動いている 1・終わった 1、別の worktree に 確認待ち 1・動いている 1 の世界。省いた別の worktree は 3。 */
const spec04 = (): Spec => ({
  places: [HERE, WT],
  omittedWorktrees: 3,
  runs: {
    here: pr(runningRun('', 'ここの実行', T('10:00')), doneRun('old', 'ここの終わった実行', T('08:00'))),
    [WT.key]: pr(waitingRun('', '別の確認待ち', T('12:00')), runningRun('survey', '別の動いている実行', T('11:00'))),
  },
});

test('D0024-AC-04: showOthers を切った一覧（places がいまの work_dir だけを返す）では、別の worktree の確認待ち・動いている行は件数に入らない', async () => {
  const { statusCounts } = await domain();
  const list = await load(spec04(), false);
  const counts = statusCounts(list.entries.map((e) => e.row));
  assert.deepEqual([counts.waiting, counts.active], [0, 1], '数えるのはいまの work_dir の動いている 1 つだけ（別の worktree の分は 2 つ数えない）');
});

test('D0024-AC-04: showOthers を入れた一覧でも、省いた別の worktree（omittedWorktrees）の数は件数に入らない', async () => {
  const { statusCounts } = await domain();
  const list = await load(spec04(), true);
  assert.equal(list.omittedWorktrees, 3);
  const counts = statusCounts(list.entries.map((e) => e.row));
  assert.deepEqual([counts.waiting, counts.active], [1, 2], '数えるのは読んだ行だけ（省いた 3 個を足さない）');
});

test('D0024-AC-04: showOthers を切った一覧に別の worktree の行は無く、省いた別の worktree の数も 0（今のまま通る。守る）', async () => {
  const list = await load(spec04(), false);
  assert.equal(list.entries.filter((e) => e.row.other).length, 0);
  assert.equal(list.omittedWorktrees, 0);
});

// ---- AC-34：loadRunList の hasOtherWorktree ----

interface FlagCase {
  name: string;
  spec: Spec;
  showOthers?: boolean;
  /** hasOtherWorktree（別の worktree の行が 1 つでもあるか） */
  hasOther: boolean;
  /** hasRemote（別の場所の行か archive の行がある。意味は変えない） */
  hasRemote: boolean;
}

const FLAG_CASES: FlagCase[] = [
  {
    name: '別の worktree の動いている行がある',
    spec: { places: [HERE, WT], runs: { here: pr(doneRun('', 'a', T('09:00'))), [WT.key]: pr(runningRun('', 'b', T('10:00'))) } },
    hasOther: true,
    hasRemote: true,
  },
  {
    name: '別の worktree の終わった行がある',
    spec: { places: [HERE, WT], runs: { here: pr(runningRun('', 'a', T('09:00'))), [WT.key]: pr(doneRun('', 'b', T('10:00'))) } },
    hasOther: true,
    hasRemote: true,
  },
  {
    name: '別の worktree の archive の行だけがある',
    spec: { places: [HERE, WT], runs: { here: pr(runningRun('', 'a', T('09:00'))), [WT.key]: pr(doneRun('archive/20261016-090000', 'b', T('08:00'))) } },
    hasOther: true,
    hasRemote: true,
  },
  {
    name: 'main（主の checkout）の場所の行がある',
    spec: { places: [HERE, MAIN], runs: { here: pr(runningRun('', 'a', T('09:00'))), main: pr(runningRun('', 'b', T('10:00'))) } },
    hasOther: true,
    hasRemote: true,
  },
  {
    name: '設定 pipe-in.showOtherWorktrees を切った（places がいまの work_dir だけを返す）',
    spec: { places: [HERE, WT], runs: { here: pr(runningRun('', 'a', T('09:00'))), [WT.key]: pr(runningRun('', 'b', T('10:00'))) } },
    showOthers: false,
    hasOther: false,
    hasRemote: false,
  },
  {
    name: '別の worktree が無い',
    spec: { places: [HERE], runs: { here: pr(runningRun('', 'a', T('09:00'))) } },
    hasOther: false,
    hasRemote: false,
  },
  {
    name: 'git の外（いまの work_dir の場所の label が null）',
    spec: { places: [{ ...HERE, label: null }], runs: { here: pr(runningRun('', 'a', T('09:00'))) } },
    hasOther: false,
    hasRemote: false,
  },
  {
    name: 'いまの work_dir の archive の行だけがある',
    spec: { places: [HERE], runs: { here: pr(doneRun('archive/20261016-090000', 'a', T('08:00'))) } },
    hasOther: false,
    hasRemote: true,
  },
  {
    name: 'places が読めない（空の一覧）',
    spec: { placesThrows: true, runs: {} },
    hasOther: false,
    hasRemote: false,
  },
  {
    name: '別の worktree の runs が読めず飛ばされた（一時の読み損ね。旗が偽になる限界）',
    spec: { places: [HERE, WT], runs: { here: pr(runningRun('', 'a', T('09:00'))), [WT.key]: 'throw' } },
    hasOther: false,
    hasRemote: false,
  },
  {
    name: '別の worktree の runs が空（state.json が読めず行にならない。旗が偽になる限界）',
    spec: { places: [HERE, WT], runs: { here: pr(runningRun('', 'a', T('09:00'))), [WT.key]: pr() } },
    hasOther: false,
    hasRemote: false,
  },
  {
    name: '別の worktree の run の id の形が違い、行にならない',
    spec: { places: [HERE, WT], runs: { here: pr(runningRun('', 'a', T('09:00'))), [WT.key]: pr(runningRun('../escape', 'b', T('10:00'))) } },
    hasOther: false,
    hasRemote: false,
  },
];

for (const c of FLAG_CASES) {
  test(`D0024-AC-34: loadRunList の hasOtherWorktree は ${c.hasOther}：${c.name}`, async () => {
    const list = await load(c.spec, c.showOthers ?? true);
    assert.equal(list.hasOtherWorktree, c.hasOther);
  });
}

for (const c of FLAG_CASES) {
  test(`D0024-AC-34: hasRemote の意味は変わらず ${c.hasRemote}：${c.name}（今のまま通る。守る）`, async () => {
    const list = await load(c.spec, c.showOthers ?? true);
    assert.equal(list.hasRemote, c.hasRemote);
  });
}

// ---- AC-37：設定を切ると読み直しが止まり、入れると動く（loadRunList → shouldPoll。パネルが見えていない場合）----

/** いまの work_dir に終わった行と archive、別の worktree に動いている行がある世界。 */
const spec37 = (): Spec => ({
  places: [HERE, WT],
  runs: {
    here: pr(doneRun('', 'a', T('09:00')), doneRun('archive/20261016-090000', 'b', T('08:00'))),
    [WT.key]: pr(runningRun('', 'c', T('10:00'))),
  },
});

test('D0024-AC-37: showOthers を入れた一覧では旗が真になり、パネルが見えていなくても読み直しが動く（loadRunList → shouldPoll）', async () => {
  const { shouldPoll } = await policy();
  const list = await load(spec37(), true);
  assert.equal(list.hasOtherWorktree, true);
  assert.equal(shouldPoll({ visible: false, hasRemote: list.hasRemote, live: false, hasOtherWorktree: list.hasOtherWorktree === true }), true);
});

test('D0024-AC-37: showOthers を切った一覧では旗が立たず、パネルが見えていなければ読み直しが止まる（今のまま通る。守る）', async () => {
  const { shouldPoll } = await policy();
  const list = await load(spec37(), false);
  assert.equal(shouldPoll({ visible: false, hasRemote: list.hasRemote, live: false, hasOtherWorktree: list.hasOtherWorktree === true }), false);
});

// ---- AC-32：ボタンで先に出す確認待ちを、行を押したときと同じに覚える ----

interface ButtonCase {
  name: string;
  spec: Spec;
  selected: string | null;
  key: string;
  stored: { place: string; id: string };
}

const BUTTON_CASES: ButtonCase[] = [
  {
    name: '別の worktree の確認待ち（直下）',
    spec: world(),
    selected: 'here|diagrams',
    key: 'wt.feat-other|',
    stored: { place: 'wt.feat-other', id: '' },
  },
  {
    name: '選びが無い（null）でも、一覧の先頭の確認待ち',
    spec: world(),
    selected: null,
    key: 'wt.feat-other|',
    stored: { place: 'wt.feat-other', id: '' },
  },
  {
    name: 'いまの work_dir のパイプの確認待ち',
    spec: world({ here: [runningRun('', '開発フロー', T('10:00')), run('review', stateJson({ pipe: 'review', pendingReview: PENDING, updatedAt: T('12:00') }))], wt: [] }),
    selected: 'here|',
    key: 'here|review',
    stored: { place: 'here', id: 'review' },
  },
];

// 2 つに分ける：①ボタンが先に出す確認待ちの key（frontWaitingKey が決める）②その key を rememberRun に渡したときの書き方
// （rememberRun・restoreRun は前からある部品。同じ表の key をそのまま渡すので、①と②で「frontWaitingKey の key → 覚える」がつながる）。
for (const c of BUTTON_CASES) {
  test(`D0024-AC-32: ボタンが先に出す確認待ちの key は ${c.key}：${c.name}`, async () => {
    const { frontWaitingKey } = await domain();
    const list = await load(c.spec);
    assert.equal(frontWaitingKey(list.entries.map((e) => e.row), c.selected), c.key);
  });
}

for (const c of BUTTON_CASES) {
  test(`D0024-AC-32: その key（${c.key}）を rememberRun に渡すと、同じ鍵 pipe-in.selectedRun に { place, id } だけを 1 回書き、restoreRun で同じ key に戻る：${c.name}（今のまま通る。守る）`, async () => {
    const { rememberRun, restoreRun } = await selection();
    const store = fakeStore();
    await rememberRun(store, c.key);
    assert.deepEqual(store.calls, [['update', MEMORY_KEY, c.stored]], '書くのは workspaceState の同じ鍵への 1 回だけ（ほかの操作は無い）');
    assert.equal(restoreRun(fakeStore(Object.fromEntries(store.data))), c.key);
  });
}

// ---- AC-45：偽の RunsSource から loadRunList → chooseEntry → toListView → statusBarLabel を通す ----

const viewSource = (spec: Spec, key: string, dirAbs: string, previous: boolean): WorkDirSource => {
  const at = key.indexOf('|');
  const found = spec.runs[key.slice(0, at)];
  const r = found === undefined || found === 'throw' ? undefined : found.runs.find((x) => x.id === key.slice(at + 1));
  return {
    async read() {
      return { workDir: dirAbs, stateJson: r?.stateJson ?? null, stageLogs: r?.stageLogs ?? [], artifacts: {}, ...(previous ? { previous: true } : {}) };
    },
  };
};

/** extension.ts の currentView と同じ流れ：一覧を読み、見る run を選び、その写しから図の状態を作り、ステータスバーの文字を作る。 */
async function flow(spec: Spec, selected: string | null, showOthers = true) {
  const { loadRunList, chooseEntry, toListView, isPreviousRun } = await app();
  const { refreshView } = await refresh();
  const { statusBarLabel } = await statusBar();
  const clock = clockAt(0);
  const list = await loadRunList(fakeSource(spec), { showOthers, clock });
  const choice = chooseEntry(list, selected, HERE);
  const view = await refreshView(viewSource(spec, choice.key, choice.dirAbs, isPreviousRun(list, choice.key)), choice.dirAbs, clock);
  const listView = toListView(list, choice.key, WORK_DIR_SETTING);
  // 件数の形（第 2 引数あり）と、今の出し方（第 2 引数なし）の両方を返し、表で比べる
  return { label: statusBarLabel(view, listView), today: statusBarLabel(view) };
}

const L = (...lines: string[]): string => lines.join('\n');
const CLICK = 'クリックでパネルを開く';
const CLICK_FRONT = 'クリックでパネルを開く（確認待ちの実行を先に出す）';
const LINE = {
  waiting: '確認待ち：画面を直す（テスト先行・feat/other）',
  diagrams: '動いている：図を作る（図を描く・feat/status-counts）',
  survey: '動いている：ログイン不具合を調べる（要件定義・feat/other）',
};

interface CombinationCase {
  name: string;
  spec: Spec;
  selected: string | null;
  text: string;
  tooltip: string;
}

// 選びの取り方：①選びが無い（既定：いまの work_dir の最新）②覚えた選び③いまの work_dir に記録なし（直下）
const COMBINATIONS: CombinationCase[] = [
  {
    name: '①選びが無い（既定）：いまの work_dir の最新＝動いている図の生成。ほかに確認待ちがあれば「先に出す」の案内が付く',
    spec: world(),
    selected: null,
    text: '$(comment-discussion) pipe-in: 動き 2・確認待ち 1',
    tooltip: L('pipe-in：動き 2・確認待ち 1', LINE.waiting, LINE.diagrams, LINE.survey, '選んでいる実行：図を作る（動いている）', CLICK_FRONT),
  },
  {
    name: '①選びが無い（既定）：その実行が確認待ちなら、案内は付かない',
    spec: world({ here: [waitingRun('', 'ここで確認待ち', T('12:00'))], wt: [previousRun('survey', 'running', '# ログイン不具合を調べる\n本文')] }),
    selected: null,
    text: '$(comment-discussion) pipe-in: 動き 1・確認待ち 1',
    tooltip: L(
      'pipe-in：動き 1・確認待ち 1',
      '確認待ち：ここで確認待ち（要件定義・feat/status-counts）',
      LINE.survey,
      '選んでいる実行：ここで確認待ち（確認待ち）',
      CLICK,
    ),
  },
  {
    name: '①選びが無い（既定）：ほかが待ちだけなら、アイコンは時計で「動き 1」',
    spec: world({ here: [doneRun('', 'CSV 出力を足す', T('09:00'))], wt: [idleRun('quiet', '合間の実行', T('10:30'))] }),
    selected: null,
    text: '$(clock) pipe-in: 動き 1',
    tooltip: L('pipe-in：動き 1', '待ち：合間の実行（要件定義・feat/other）', '選んでいる実行：CSV 出力を足す（合格）', CLICK),
  },
  {
    name: '①選びが無い（既定）：省いた別の worktree があれば、その行が出る',
    spec: world({ omittedWorktrees: 2 }),
    selected: null,
    text: '$(comment-discussion) pipe-in: 動き 2・確認待ち 1',
    tooltip: L(
      'pipe-in：動き 2・確認待ち 1',
      LINE.waiting,
      LINE.diagrams,
      LINE.survey,
      '別の worktree を 2 個、省いています（件数に入っていません）',
      '選んでいる実行：図を作る（動いている）',
      CLICK_FRONT,
    ),
  },
  {
    name: '②覚えた選び（終わった run）：合格で隠さず、結果と利用枠が説明に残る',
    spec: world(),
    selected: 'here|',
    text: '$(comment-discussion) pipe-in: 動き 2・確認待ち 1',
    tooltip: L(
      'pipe-in：動き 2・確認待ち 1',
      LINE.waiting,
      LINE.diagrams,
      LINE.survey,
      '選んでいる実行：CSV 出力を足す（合格）',
      '利用枠：5時間枠 2%・7日枠 15%',
      CLICK_FRONT,
    ),
  },
  {
    name: '②覚えた選び（archive の終わった run）：結果の言葉が説明に残る',
    spec: world(),
    selected: 'here|archive/20261016-090000',
    text: '$(comment-discussion) pipe-in: 動き 2・確認待ち 1',
    tooltip: L('pipe-in：動き 2・確認待ち 1', LINE.waiting, LINE.diagrams, LINE.survey, '選んでいる実行：きのうの実行（不合格）', CLICK_FRONT),
  },
  {
    name: '②覚えた選び（別の worktree の確認待ち）：案内は付かない',
    spec: world(),
    selected: 'wt.feat-other|',
    text: '$(comment-discussion) pipe-in: 動き 2・確認待ち 1',
    tooltip: L('pipe-in：動き 2・確認待ち 1', LINE.waiting, LINE.diagrams, LINE.survey, '選んでいる実行：画面を直す（確認待ち）', CLICK),
  },
  {
    name: '③いまの work_dir に記録なし（直下）：「記録がありません」は出ず、「選んでいる実行：記録なし」が出る',
    spec: world({ here: [] }),
    selected: null,
    text: '$(comment-discussion) pipe-in: 動き 1・確認待ち 1',
    tooltip: L('pipe-in：動き 1・確認待ち 1', LINE.waiting, LINE.survey, '選んでいる実行：記録なし', CLICK_FRONT),
  },
];

for (const c of COMBINATIONS) {
  test(`D0024-AC-45: 偽の RunsSource から通した text：${c.name}`, async () => {
    const { label } = await flow(c.spec, c.selected);
    assert.equal(label.text, c.text);
  });
  test(`D0024-AC-45: 偽の RunsSource から通した tooltip：${c.name}`, async () => {
    const { label } = await flow(c.spec, c.selected);
    assert.equal(label.tooltip, c.tooltip);
  });
}

// 上の表（③）が説明の全文を比べる。これは AC-10 の言い方（「記録がありません（<work_dir>）」の文を出さない）だけを、原因が分かる形で見る
test('D0024-AC-45: ③記録なしのとき、説明に「記録がありません」の文（作業フォルダのパス入り。AC-10）が出ない', async () => {
  const { label } = await flow(world({ here: [] }), null);
  assert.doesNotMatch(label.tooltip, /記録がありません/);
});

interface UnchangedCase {
  name: string;
  spec: Spec;
  showOthers?: boolean;
  text: string;
}

// 選んでいる実行のほかに数える行が無いとき：今の出し方と 1 文字も変わらない（AC-07 を、一覧を通して確かめる）
const UNCHANGED: UnchangedCase[] = [
  {
    name: '実行が 1 つだけ（動いている）',
    spec: { runs: { here: pr(runningRun('', 'ひとつだけ', T('10:00'), 'design', 2)) } },
    text: '$(sync~spin) pipe-in: 設計',
  },
  {
    name: '選んでいる実行が動いていて、ほかは全部終わった（別の worktree の終わった行・archive もある）',
    spec: world({ wt: [doneRun('', 'ほかの実行', T('10:00'))] }),
    text: '$(sync~spin) pipe-in: 図を描く',
  },
  {
    name: 'archive だけ',
    spec: { runs: { here: pr(doneRun('archive/20261016-090000', 'きのうの実行', '2026-10-16T08:00:00', 'TEST_FAILED')) } },
    text: '$(circuit-board) pipe-in',
  },
  { name: '一覧が空', spec: { runs: { here: pr() } }, text: '$(circuit-board) pipe-in' },
  { name: '一覧を読めなかった（places が読めない）', spec: { placesThrows: true, runs: {} }, text: '$(circuit-board) pipe-in' },
  {
    name: '設定 pipe-in.showOtherWorktrees を切った（別の worktree の数える行が一覧に入らない）',
    spec: world(),
    showOthers: false,
    text: '$(sync~spin) pipe-in: 図を描く',
  },
];

for (const c of UNCHANGED) {
  test(`D0024-AC-45: 数える行が選んでいる実行のほかに無いときの text は、今の出し方の文字のまま：${c.name}（今のまま通る。守る）`, async () => {
    const { label } = await flow(c.spec, null, c.showOthers ?? true);
    assert.equal(label.text, c.text);
  });
  test(`D0024-AC-45: 数える行が選んでいる実行のほかに無いときの text も tooltip も、第 2 引数を渡さない今の出し方と同じ：${c.name}（今のまま通る。守る）`, async () => {
    const { label, today } = await flow(c.spec, null, c.showOthers ?? true);
    assert.deepEqual(label, today, 'text も tooltip も 1 文字も変わらない');
  });
}
