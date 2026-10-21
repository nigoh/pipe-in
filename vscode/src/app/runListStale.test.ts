// 実行の一覧のユースケース：止まっているかもしれない印の元（行の quietSec）が、別の worktree の行にも入ること、
// 前の実行（archive/）を見分ける isPreviousRun（D0021）。AC-30・47。口（RunsSource）は手で書いた偽物。
// 新しい部品（isPreviousRun）は、テスト先行のときに「まだ無い」ことで落ちるように、テストの中で動的に読み込む（実装後も同じ）。
// 省かれた分の確かめは新しく置かない：件数を超えた archive は fsRuns.test.ts の D0019-AC-10 が「読まない（stat も readdir もしない）」を、
// 8 個を超えた別の worktree は fsWorktrees.test.ts の D0019-AC-19 が「省いた数だけ返し行にしない」を確かめている。読まないので印も付かない。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import type { WorkDirSnapshot } from '../domain/pipelineView.ts';
import type { RunRow } from '../domain/runList.ts';
import { stateJson } from '../test/fixtures.ts';
import { clockAt } from '../test/liveFixtures.ts';
import { staleSnapshot } from '../test/staleFixtures.ts';

const app = () => import('./runList.ts');
/** isPreviousRun は、無いときは呼んだところで落ちるように、取り出すだけにする（テスト先行のときは型に無かった）。 */
const previousRunOf = async () => ((await app()) as unknown as { isPreviousRun: (list: unknown, key: unknown) => boolean }).isPreviousRun;

interface Place {
  key: string;
  label: string | null;
  workDirAbs: string;
}
interface FakeRun {
  id: string;
  stateJson: string | null;
  stageLogs: { fileName: string; text: string; mtimeMs?: number | null }[];
}

const HERE: Place = { key: 'here', label: 'main', workDirAbs: path.resolve('/ws/docs/pipeline') };
const WT: Place = { key: 'wt.feat-x', label: 'feat/x', workDirAbs: path.resolve('/wt/feat-x/docs/pipeline') };

/** 記録の写しを、口が返す run にする。 */
const runOf = (id: string, snap: Pick<WorkDirSnapshot, 'stateJson' | 'stageLogs'>): FakeRun => ({
  id,
  stateJson: snap.stateJson,
  stageLogs: snap.stageLogs,
});
const done = (id: string): FakeRun => ({ id, stateJson: stateJson({ final: 'PASSED', updatedAt: '2026-10-16T09:00:00' }), stageLogs: [] });

/** 偽の RunsSource。runsOf は呼ばれるたびに今の中身を返す（読み直しで記録が動いた様子を作れる）。 */
function fakeSource(runsOf: () => Record<string, FakeRun[]>, places: Place[] = [HERE, WT]) {
  return {
    async places(showOthers: boolean) {
      return { places: showOthers ? places : places.filter((p) => p.key === 'here'), omittedWorktrees: 0 };
    },
    async runs(place: Place) {
      return { runs: runsOf()[place.key] ?? [], archiveOmitted: 0 };
    },
  };
}

const load = async (source: ReturnType<typeof fakeSource>) => {
  const { loadRunList } = await app();
  return loadRunList(source, { showOthers: true, clock: clockAt(0) });
};

/** 行の quietSec（テスト先行のときは型に無かった項目）。 */
const quietOf = (row: object | undefined): unknown => (row as { quietSec?: unknown } | undefined)?.quietSec;
const rowOf = (list: { entries: { row: RunRow }[] }, key: string): RunRow | undefined => list.entries.find((e) => e.row.key === key)?.row;

// ---- AC-30：別の worktree の動いている行にも、同じ印の元が入る ----

test('D0021-AC-30: 別の worktree の動いている行にも、いまの work_dir の行と同じ quietSec が入る（口の偽物が mtimeMs つきのログを返す）', async () => {
  const snap = staleSnapshot({ quietSec: 612 });
  const list = await load(fakeSource(() => ({ here: [runOf('', snap)], 'wt.feat-x': [runOf('', snap)] })));
  const other = rowOf(list, 'wt.feat-x|');
  assert.equal(other?.state, 'running', '前提：別の worktree の行が動いている');
  assert.equal(quietOf(other), 612);
  assert.equal(quietOf(rowOf(list, 'here|')), 612, 'いまの work_dir の同じ写しの行も同じ値');
});

test('D0021-AC-30: 別の worktree の行は、新しい更新時刻で読み直した一覧では quietSec が小さくなる（記録が動くと、描き直しで印が消える元）', async () => {
  let snap = staleSnapshot({ quietSec: 612 });
  const source = fakeSource(() => ({ 'wt.feat-x': [runOf('', snap)] }));
  const before = await load(source);
  snap = staleSnapshot({ quietSec: 3 });
  const after = await load(source);
  assert.equal(quietOf(rowOf(before, 'wt.feat-x|')), 612);
  assert.equal(quietOf(rowOf(after, 'wt.feat-x|')), 3);
});

// ---- AC-47：前の実行（archive/）----

const ARCHIVE_ID = 'archive/20261016-090000';

async function sampleList() {
  const snap = staleSnapshot({ quietSec: 612 });
  return load(
    fakeSource(() => ({
      here: [done(''), runOf('diagrams', snap), done(ARCHIVE_ID)],
      'wt.feat-x': [runOf('', snap), done('archive/20261016-080000')],
    })),
  );
}

test('D0021-AC-47: isPreviousRun は archive/ の行の key だけ真（いまの work_dir も別の worktree も）', async () => {
  const isPreviousRun = await previousRunOf();
  const list = await sampleList();
  assert.equal(isPreviousRun(list, 'here|archive/20261016-090000'), true);
  assert.equal(isPreviousRun(list, 'wt.feat-x|archive/20261016-080000'), true);
});

/** archive の行でないもの・一覧に無いもの・形の違う値。どれも偽。 */
const NOT_PREVIOUS: readonly (readonly [string, unknown])[] = [
  ['直下の行', 'here|'],
  ['パイプの行（動いている）', 'here|diagrams'],
  ['別の worktree の直下の行', 'wt.feat-x|'],
  ['一覧に無い archive', 'here|archive/20261015-090000'],
  ['一覧に無い場所', 'wt.gone|'],
  ['archive の外へ出る', 'here|archive/../x'],
  ['昔の形（id だけ）', 'archive/20261016-090000'],
  ['数', 3],
  ['null', null],
  ['undefined', undefined],
  ['オブジェクト', { key: 'here|' }],
];

for (const [label, key] of NOT_PREVIOUS) {
  test(`D0021-AC-47: isPreviousRun は偽：${label}`, async () => {
    const isPreviousRun = await previousRunOf();
    const list = await sampleList();
    assert.equal(isPreviousRun(list, 'here|archive/20261016-090000'), true, '対照：archive の行は真');
    assert.equal(isPreviousRun(list, key), false);
  });
}

test('D0021-AC-47: 前の実行（archive/）の行は、ログに更新時刻があっても quietSec が null（対照：同じ写しの通常の行は数）', async () => {
  const snap = staleSnapshot({ quietSec: 612 });
  const list = await load(fakeSource(() => ({ here: [runOf('', snap), runOf(ARCHIVE_ID, snap)] })));
  assert.equal(quietOf(rowOf(list, 'here|')), 612, '対照：同じ写しの通常の行');
  const old = rowOf(list, `here|${ARCHIVE_ID}`);
  assert.equal(old?.state, 'done', '前提：archive の行は元から「終わった」');
  assert.equal(quietOf(old), null);
});
