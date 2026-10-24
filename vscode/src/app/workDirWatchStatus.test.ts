// work_dir が無いあいだと、できたあとで、ステータスバーの文字が変わる（D0034-AC-27）：
// 偽の口（work_dir の有無・実行の一覧）から、確かめの手順 → 一覧を読む → ステータスバーの文字と説明まで通す。D0024-AC-45（app/runListCounts.test.ts）と同じ作り。
// 手順の部品（app/workDirWatch.ts）は、テスト先行のときまだ無かったので、テストの中で読み込む（今もその形のまま）。一覧・図の状態・ステータスバーの文字の部品は今あるものをそのまま使う。
// 補助（fakeSource・viewSource）は、承認された別のテストの中の関数で、そちらを書き換えないので、同じ作りでこの中に持つ。
// SDK・時計・子プロセスは使わない。ファイルは作らない（偽の口だけ）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { createGeneration } from './refreshPolicy.ts';
import { refreshView } from './refreshView.ts';
import type { WorkDirSource } from './refreshView.ts';
import { chooseEntry, isPreviousRun, loadRunList, toListView } from './runList.ts';
import { stateJson } from '../test/fixtures.ts';
import { clockAt } from '../test/liveFixtures.ts';
import { statusBarLabel } from '../view/statusBar.ts';

type Presence = 'present' | 'absent' | 'unknown';
interface WatchHandle {
  onDidCreate(listener: () => void): unknown;
  onDidChange(listener: () => void): unknown;
  onDidDelete(listener: () => void): unknown;
  dispose(): void;
}
interface WatchHolder {
  readonly active: boolean;
  attach(dir: string): boolean;
  detach(): void;
}
interface WorkDirChecker {
  check(dir: string): Promise<void>;
  reset(): void;
}
interface WorkDirWatchModule {
  createWatchHolder(options: { create: (dir: string) => WatchHandle; onEvent: () => void }): WatchHolder;
  createWorkDirChecker(options: { generation: ReturnType<typeof createGeneration>; holder: WatchHolder; probe: (dir: string) => Promise<Presence>; reload: () => Promise<void> }): WorkDirChecker;
}
const loadModule = async (): Promise<WorkDirWatchModule> => (await import('./workDirWatch.ts')) as unknown as WorkDirWatchModule;

const KEEP_NOTE = '（今のまま通る。守る）';

interface Place {
  key: string;
  label: string | null;
  workDirAbs: string;
}
interface FakeRun {
  id: string;
  stateJson: string | null;
  stageLogs: { fileName: string; text: string }[];
}

const HERE: Place = { key: 'here', label: null, workDirAbs: path.resolve('/ws/docs/pipeline') };
const WORK_DIR_SETTING = 'docs/pipeline';
const PENDING = { stage: 'requirements', doc: 'docs/pipeline/01_requirements.md', session_id: 's' };

/** work_dir の有無の旗。確かめ（probe）と実行の一覧（RunsSource）が同じ旗を見る。 */
interface Flag {
  exists: boolean;
}

/** state.json のある実行（確認待ち）。work_dir ができたら読めるようになる。 */
const WAITING_RUN: FakeRun = {
  id: '',
  stateJson: stateJson({ name: '最初の実行', pendingReview: PENDING, updatedAt: '2026-10-17T10:00:00' }),
  stageLogs: [],
};

/** 偽の RunsSource。work_dir が無いあいだは行が 1 つも無く（本物の listPlaceRuns と同じ約束）、できたら WAITING_RUN が読める。 */
function fakeSource(flag: Flag) {
  return {
    async places() {
      return { places: [HERE], omittedWorktrees: 0 };
    },
    async runs(_place: Place) {
      return { runs: flag.exists ? [WAITING_RUN] : [], archiveOmitted: 0 };
    },
  };
}

/** 見る run の写し。work_dir が無いあいだは中身が空（記録なし）。 */
const viewSource = (flag: Flag, dirAbs: string, previous: boolean): WorkDirSource => ({
  async read() {
    const run = flag.exists ? WAITING_RUN : undefined;
    return { workDir: dirAbs, stateJson: run?.stateJson ?? null, stageLogs: run?.stageLogs ?? [], artifacts: {}, ...(previous ? { previous: true } : {}) };
  },
});

/** extension.ts の currentView・render と同じ流れ：一覧を読み、見る run を選び、その写しから図の状態を作り、ステータスバーの文字を作る。 */
async function labelNow(flag: Flag) {
  const clock = clockAt(0);
  const list = await loadRunList(fakeSource(flag), { showOthers: true, clock });
  const choice = chooseEntry(list, null, HERE);
  const view = await refreshView(viewSource(flag, choice.dirAbs, isPreviousRun(list, choice.key)), choice.dirAbs, clock);
  const listView = toListView(list, choice.key, WORK_DIR_SETTING);
  // 一覧を渡す形（今の呼び出し）と、渡さない形（今の出し方）の両方を返す
  return { label: statusBarLabel(view, listView), today: statusBarLabel(view) };
}

const NO_RECORDS = {
  text: '$(circuit-board) pipe-in',
  tooltip: `pipe-in：記録がありません（${HERE.workDirAbs}）\nクリックでパネルを開く`,
};
const WAITING_TEXT = '$(comment-discussion) pipe-in: 要件定義の確認待ち';

// ---- 前提：偽の口を通した流れが、期待した文字になる（以降の確かめの土台。部品が無くても通る）----

test(`D0034-AC-27: 前提：work_dir が無い世界では、今の「記録なし」の出し方になる（一覧を渡しても渡さなくても同じ）${KEEP_NOTE}`, async () => {
  const { label, today } = await labelNow({ exists: false });
  assert.deepEqual(label, NO_RECORDS);
  assert.deepEqual(label, today, 'text も tooltip も 1 文字も変わらない');
});

test(`D0034-AC-27: 前提：state.json のある実行（確認待ち）が読める世界では、記録のある出し方（選んでいる実行の段）になる${KEEP_NOTE}`, async () => {
  const { label } = await labelNow({ exists: true });
  assert.equal(label.text, WAITING_TEXT);
  assert.ok(label.tooltip.startsWith('pipe-in：要件定義の確認を待っている（docs/pipeline/01_requirements.md）'), label.tooltip);
  assert.ok(label.tooltip.endsWith('\nクリックでパネルを開く'), label.tooltip);
});

// ---- 確かめの手順 → 一覧を読む → ステータスバー ----

/** 本物の手順の部品と見張りを持つ部品を組み、読み直しは上の流れ（一覧 → ステータスバーの文字）にした世界。見張りは偽。 */
async function world() {
  const mod = await loadModule();
  const flag: Flag = { exists: false };
  const statusItem = { text: '', tooltip: '' };
  const reads: { text: string; tooltip: string }[] = [];
  const holder = mod.createWatchHolder({
    create: () => ({ onDidCreate: () => undefined, onDidChange: () => undefined, onDidDelete: () => undefined, dispose: () => undefined }),
    onEvent: () => undefined,
  });
  const checker = mod.createWorkDirChecker({
    generation: createGeneration(),
    holder,
    probe: async () => (flag.exists ? 'present' : 'absent'),
    reload: async () => {
      const { label } = await labelNow(flag);
      statusItem.text = label.text;
      statusItem.tooltip = label.tooltip;
      reads.push(label);
    },
  });
  return { flag, statusItem, reads, check: () => checker.check(HERE.workDirAbs) };
}

test('D0034-AC-27: work_dir が無いあいだ、最初の確かめのあとも、2 回目以降の確かめのあとも、ステータスバーの文字と説明は今の「記録なし」の出し方と 1 文字も変わらない（2 回目以降は読み直さない）', async () => {
  const w = await world();
  await w.check();
  assert.deepEqual(w.statusItem, NO_RECORDS);
  for (let i = 0; i < 3; i++) await w.check();
  assert.deepEqual(w.statusItem, NO_RECORDS);
  assert.equal(w.reads.length, 1, '最初の 1 回だけ読む');
});

test('D0034-AC-27: state.json のある実行が読めるようになった確かめのあと、ステータスバーが記録のある出し方（選んでいる実行の段）に変わる', async () => {
  const w = await world();
  await w.check();
  assert.deepEqual(w.statusItem, NO_RECORDS);
  w.flag.exists = true;
  await w.check();
  assert.equal(w.statusItem.text, WAITING_TEXT);
  assert.ok(w.statusItem.tooltip.startsWith('pipe-in：要件定義の確認を待っている'), w.statusItem.tooltip);
  assert.equal(w.reads.length, 2);
});

test('D0034-AC-27: work_dir が消えたことを見つけた確かめのあと、ステータスバーが「記録なし」の出し方に戻る（最初と 1 文字も変わらない）', async () => {
  const w = await world();
  w.flag.exists = true;
  await w.check();
  assert.equal(w.statusItem.text, WAITING_TEXT);
  w.flag.exists = false;
  await w.check();
  assert.deepEqual(w.statusItem, NO_RECORDS);
});
