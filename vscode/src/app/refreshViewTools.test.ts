// 選んだ実行の写し → 図の状態（refreshView）で、表（エージェント・スキル・道具）が同じ作りでできる（D0050）。
//   AC-03：表のために、読むファイルも読み取りの口も増やさない（写しのキーは workDir・stateJson・stageLogs・artifacts のまま。previous は渡したときだけ）。
//   AC-04：別の worktree・archive/ の実行を選んだときも、いまの work_dir の実行と同じ作り方で、同じ段のログの写しからは同じ表になる。
//   AC-41：選んだ実行の描き直し（refreshView）で作った図の状態には表がある（一覧の行のための図の状態には無い。それは pipelineViewTools.test.ts）。
// 一時フォルダ（makeRepo の木）の中だけに書く。リポジトリの実物には書かない。git のコマンドは使わない。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { chooseEntry, loadRunList } from './runList.ts';
import { refreshView } from './refreshView.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { HERE, makeRunKey } from '../domain/runs.ts';
import { createFsRunsSource, createFsWorkDirSource } from '../infra/fsWorkDirSource.ts';
import { assistantTool, stageRunEntry, stateJson } from '../test/fixtures.ts';
import { makeRepo, put } from '../test/gitFixtures.ts';
import { clockAt } from '../test/liveFixtures.ts';
import { withTempDir } from '../test/tempDir.ts';
import { logOf, uniqueCalls } from '../test/toolsFixtures.ts';

interface Tools {
  rows: { kind: string; name: string; count: number; stages: string[]; durationSec: number | null }[];
  kinds: number;
  total: number;
}
const toolsOf = (view: PipelineView): Tools => {
  const tools = (view as unknown as { tools?: Tools | null }).tools;
  assert.ok(tools !== undefined && tools !== null, 'view.tools（エージェント・スキル・道具の表）がある（まだ作っていない）');
  return tools;
};
const brief = (t: Tools): string[] => t.rows.map((r) => `${r.kind}:${r.name}:${r.count}`);

const STATE = stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 }), stageRunEntry({ stage: 'design', seq: 2 })] });
const REQ_CALLS = uniqueCalls([
  { name: 'Agent', input: { subagent_type: 'module-reader' } },
  { name: 'Skill', input: { skill: 'review' } },
  { name: 'Read', input: { file_path: 'a.py' }, count: 2 },
]);
const DESIGN_CALLS = [
  ...uniqueCalls([{ name: 'Read', input: { file_path: 'b.py' }, count: 3, parent: 'toolu_nested' }], 'n'),
  assistantTool('Agent', { subagent_type: 'module-reader' }, 'a9'),
];
const EXPECTED = ['agent:module-reader:2', 'skill:review:1', 'tool:Read:5'];

/** dir に state.json と段のログ 2 つを書く */
async function putRun(dir: string): Promise<void> {
  await put(path.join(dir, 'state.json'), STATE);
  await put(path.join(dir, 'logs', '01_requirements.jsonl'), logOf('requirements', REQ_CALLS));
  await put(path.join(dir, 'logs', '02_design.jsonl'), logOf('design', DESIGN_CALLS));
}

// ---- AC-03：読むファイル・口を増やさない ----

test('D0050-AC-03: createFsWorkDirSource().read() の写しのキーは workDir・stateJson・stageLogs・artifacts のまま。previous は渡したときだけ増える（表のために項目を足さない。今のまま通る。守る）', async () => {
  await withTempDir(async (dir) => {
    await putRun(dir);
    const plain = await createFsWorkDirSource(dir, 'docs/pipeline').read();
    assert.deepEqual(Object.keys(plain).sort(), ['artifacts', 'stageLogs', 'stateJson', 'workDir']);
    const previous = await createFsWorkDirSource(dir, 'docs/pipeline', { previous: true }).read();
    assert.deepEqual(Object.keys(previous).sort(), ['artifacts', 'previous', 'stageLogs', 'stateJson', 'workDir']);
  });
});

test('D0050-AC-03: 表は、写しにすでにある段のログの中身から作る：同じ写しを何度 refreshView しても同じ表で、写しの口（read）は 1 回ずつしか呼ばない', async () => {
  await withTempDir(async (dir) => {
    await putRun(dir);
    const real = createFsWorkDirSource(dir, 'docs/pipeline');
    let reads = 0;
    const counting = {
      read: () => {
        reads += 1;
        return real.read();
      },
    };
    const first = toolsOf(await refreshView(counting, 'docs/pipeline', clockAt(0)));
    assert.equal(reads, 1, '1 回の描き直しで写しを読むのは 1 回（表のために読み直さない）');
    const second = toolsOf(await refreshView(counting, 'docs/pipeline', clockAt(0)));
    assert.equal(reads, 2);
    assert.deepEqual(second, first);
    assert.deepEqual(brief(first), EXPECTED);
  });
});

// ---- AC-04：いまの work_dir・archive/・別の worktree で同じ表 ----

test('D0050-AC-04: いまの work_dir・archive/<日時>（previous）・別の worktree に置いた同じ段のログの写しからは、同じ表になる', async () => {
  await withTempDir(async (base) => {
    const repo = await makeRepo(base, [{ name: 'feat-x', branch: 'feat/x', state: STATE }], { mainState: STATE });
    const here = path.join(repo.mainRoot, 'docs', 'pipeline');
    const archive = path.join(here, 'archive', '20261016-090000');
    const other = path.join(repo.roots['feat-x']!, 'docs', 'pipeline');
    await putRun(here);
    await put(path.join(archive, 'state.json'), STATE);
    await put(path.join(archive, 'logs', '01_requirements.jsonl'), logOf('requirements', REQ_CALLS));
    await put(path.join(archive, 'logs', '02_design.jsonl'), logOf('design', DESIGN_CALLS));
    await putRun(other);

    // (1) いまの work_dir
    const hereView = await refreshView(createFsWorkDirSource(here, 'docs/pipeline'), 'docs/pipeline', clockAt(0));
    const expected = toolsOf(hereView);
    assert.ok(expected.rows.length > 0, '行を持つ（先に確かめる。undefined どうしが等しくなって通らないように）');
    assert.deepEqual(brief(expected), EXPECTED);

    // (2) archive/<日時>（前の実行。入口は previous: true で読む）
    const archiveView = await refreshView(createFsWorkDirSource(archive, 'docs/pipeline', { previous: true }), 'docs/pipeline', clockAt(0));
    assert.deepEqual(toolsOf(archiveView), expected);

    // (3) 別の worktree：本番と同じ道（createFsRunsSource → loadRunList → chooseEntry → createFsWorkDirSource → refreshView）
    const source = createFsRunsSource(repo.mainRoot, here, 'docs/pipeline');
    const list = await loadRunList(source, { showOthers: true, clock: clockAt(0) });
    const wtKey = makeRunKey('wt.feat-x', '');
    assert.ok(list.entries.some((e) => e.row.key === wtKey), '別の worktree の行が一覧にある');
    const chosen = chooseEntry(list, wtKey, { key: HERE, label: null, workDirAbs: here });
    assert.equal(chosen.key, wtKey);
    const otherView = await refreshView(createFsWorkDirSource(chosen.dirAbs, 'docs/pipeline'), 'docs/pipeline', clockAt(0));
    assert.deepEqual(toolsOf(otherView), expected);
  });
});

// ---- AC-41：選んだ実行の描き直しで作った図の状態には表がある ----

test('D0050-AC-41: refreshView で作った図の状態の tools は null でなく、行を持つ（一覧の行のための図の状態とは違う）', async () => {
  await withTempDir(async (dir) => {
    await putRun(dir);
    const view = await refreshView(createFsWorkDirSource(dir, 'docs/pipeline'), 'docs/pipeline', clockAt(0));
    assert.ok(toolsOf(view).rows.length > 0);
  });
});

test('D0050-AC-41: 口が例外を投げて空の写しで組み立てても、表は null でなく、行 0 で例外なし（記録なしの表示）', async () => {
  const view = await refreshView({ read: () => Promise.reject(new Error('boom')) }, '/ws/docs/pipeline');
  const t = toolsOf(view);
  assert.deepEqual(t.rows, []);
});
