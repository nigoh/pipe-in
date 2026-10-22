// ステータスバーの件数（D0024）：数える行の数え方・並べ方・先に出す確認待ちの判断。RunRow だけを受ける純粋な関数を確かめる。
// 新しい部品（domain/runList.ts の isCounted・statusCounts・countedRows・hasOtherCounted・frontWaitingKey）は、
// テストの中で読み込む（テスト先行のとき、まだ無い部品が「関数ではない」で落ちるようにしたため）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { countStates, sortRows, summarizeRun } from './runList.ts';
import type { RunRow, RunState } from './runList.ts';
import { parseRunKey } from './runs.ts';
import { logText, promptLine, stageRunEntry, stateJson } from '../test/fixtures.ts';
import { BASE_AT, clockAt, waitingSnapshot } from '../test/liveFixtures.ts';
import { row, sampleRows } from '../test/runListFixtures.ts';

const rl = () => import('./runList.ts');

/** 「今」より minAgo 分前（大きいほど古い）。並びを決めるための更新時刻。 */
const t = (minAgo: number): number => Date.UTC(2026, 9, 17, 10, 0, 0) - minAgo * 60_000;

type Top = 'waiting' | 'running' | 'idle' | null;
const ZERO = { waiting: 0, active: 0, top: null as Top };

const REQ = stageRunEntry({ stage: 'requirements', seq: 1 });
const RUNNING_LOG = { fileName: '02_design.jsonl', text: logText([promptLine('design', BASE_AT)]) };
const PENDING = { stage: 'requirements', doc: 'a.md', session_id: 's' };

/** 記録の写しから 1 行を作る（既定はいまの work_dir の直下。「今」は BASE から 40 秒後）。 */
function summarize(p: {
  stateJson: string | null;
  stageLogs?: { fileName: string; text: string }[];
  key?: string;
  id?: string;
  other?: boolean;
  previous?: boolean;
}): RunRow {
  return summarizeRun(
    { key: 'here|', id: '', branch: null, other: false, memoHead: null, previous: false, stageLogs: [], ...p },
    clockAt(40),
  );
}

// ---- AC-01：数え方 ----

const STATE_TABLE: readonly (readonly [RunState, { waiting: number; active: number; top: Top }])[] = [
  ['waiting', { waiting: 1, active: 0, top: 'waiting' }],
  ['running', { waiting: 0, active: 1, top: 'running' }],
  ['idle', { waiting: 0, active: 1, top: 'idle' }],
  ['done', ZERO],
];

test('D0024-AC-01: 数え方：確認待ちは「確認待ち」に、動いている行と待ちの行は「動き」に数え、終わった行は数えない（状態ごとに 1 行の表）', async () => {
  const { statusCounts } = await rl();
  for (const [state, expected] of STATE_TABLE) {
    assert.deepEqual(statusCounts([row({ state })]), expected, state);
  }
});

test('D0024-AC-01: isCounted は 確認待ち・動いている・待ちの行で真、終わった行で偽（状態ごとの表）', async () => {
  const { isCounted } = await rl();
  const expected: Record<RunState, boolean> = { waiting: true, running: true, idle: true, done: false };
  for (const state of ['waiting', 'running', 'idle', 'done'] as const) {
    assert.equal(isCounted(row({ state })), expected[state], state);
  }
});

const MIXED: readonly (readonly [string, readonly RunState[]])[] = [
  ['空', []],
  ['確認待ち 2・動いている 1', ['waiting', 'waiting', 'running']],
  ['待ちと終わった', ['idle', 'done', 'idle', 'done']],
  ['4 つの状態が 1 つずつ', ['waiting', 'running', 'idle', 'done']],
  ['終わったものだけ', ['done', 'done']],
  ['動いている 3・待ち 2', ['running', 'running', 'running', 'idle', 'idle']],
];

test('D0024-AC-01: statusCounts は countStates と同じ数え方：waiting は同じ・active は running と同じ・waiting + active は isCounted の行数（混ぜた組の表）', async () => {
  const { statusCounts, isCounted } = await rl();
  const sets: (readonly [string, RunRow[]])[] = [
    ...MIXED.map(([name, states]) => [name, states.map((state, i) => row({ key: `here|r${i}`, state }))] as const),
    ['見本の一覧（8 行）', sampleRows()],
  ];
  for (const [name, rows] of sets) {
    const c = statusCounts(rows);
    const s = countStates(rows);
    assert.equal(c.waiting, s.waiting, `${name}：確認待ち`);
    assert.equal(c.active, s.running, `${name}：動き（待ちを含む。タブの「動いている」と同じ）`);
    assert.equal(c.waiting + c.active, rows.filter((r) => isCounted(r)).length, `${name}：数える行の数`);
  }
});

// ---- AC-02：数えない行 ----

test('D0024-AC-02: archive の行（previous）と final のある行は数えない（summarizeRun で作った行でも）。動いている行を足すと数える（対照）', async () => {
  const { statusCounts, isCounted } = await rl();
  const archiveId = 'archive/20261016-090000';
  const cases: readonly (readonly [string, RunRow])[] = [
    ['archive の行（final あり）', summarize({ key: `here|${archiveId}`, id: archiveId, previous: true, stateJson: stateJson({ final: 'PASSED', runs: [REQ] }) })],
    ['archive の行（final の無い古い記録）', summarize({ key: `here|${archiveId}`, id: archiveId, previous: true, stateJson: stateJson({ runs: [REQ] }) })],
    ['archive の行（確認待ちの印と動いているログが残っている）', summarize({ key: `here|${archiveId}`, id: archiveId, previous: true, stateJson: stateJson({ runs: [REQ], pendingReview: PENDING }), stageLogs: [RUNNING_LOG] })],
    ['final のある直下の行（合格）', summarize({ stateJson: stateJson({ final: 'PASSED', runs: [REQ] }) })],
    ['final のある別の worktree の行', summarize({ key: 'wt.feat-x|', other: true, stateJson: stateJson({ final: 'TEST_FAILED', runs: [REQ] }) })],
    ['final があり、動いているログもある行（final が先）', summarize({ stateJson: stateJson({ final: 'STOPPED_BY_HUMAN', runs: [REQ] }), stageLogs: [RUNNING_LOG] })],
  ];
  for (const [name, r] of cases) {
    assert.equal(r.state, 'done', `${name}：行は終わった`);
    assert.equal(isCounted(r), false, `${name}：数える行でない`);
    assert.deepEqual(statusCounts([r]), ZERO, name);
  }
  const running = summarize({ key: 'here|diagrams', id: 'diagrams', stateJson: stateJson({ runs: [REQ] }), stageLogs: [RUNNING_LOG] });
  assert.equal(running.state, 'running', '対照：動いている行は');
  assert.deepEqual(statusCounts([...cases.map(([, r]) => r), running]), { waiting: 0, active: 1, top: 'running' }, '終わった行を何件足しても、動いている 1 行だけを数える');
});

// ---- AC-03：いまの work_dir と別の worktree ----

test('D0024-AC-03: いまの work_dir の行と別の worktree の行（other が真）を同じに数える', async () => {
  const { statusCounts } = await rl();
  const expected: Record<RunState, { waiting: number; active: number; top: Top }> = {
    waiting: { waiting: 1, active: 0, top: 'waiting' },
    running: { waiting: 0, active: 1, top: 'running' },
    idle: { waiting: 0, active: 1, top: 'idle' },
    done: ZERO,
  };
  for (const state of ['waiting', 'running', 'idle', 'done'] as const) {
    assert.deepEqual(statusCounts([row({ key: 'here|a', state, other: false })]), expected[state], `いまの work_dir の ${state}`);
    assert.deepEqual(statusCounts([row({ key: 'wt.feat-x|a', state, other: true })]), expected[state], `別の worktree の ${state}`);
  }
  const mixed = [
    row({ key: 'here|a', state: 'waiting' }),
    row({ key: 'wt.feat-x|', state: 'waiting', other: true }),
    row({ key: 'here|b', state: 'running' }),
    row({ key: 'wt.feat-x|c', state: 'idle', other: true }),
    row({ key: 'wt.fix-login|', state: 'done', other: true }),
  ];
  assert.deepEqual(statusCounts(mixed), { waiting: 2, active: 2, top: 'waiting' });
});

// ---- AC-05：動いている段と確認待ちの印が同じ記録にある行 ----

/** 動いている段と確認待ちの印（pending_review）が同じ記録にある行。summarizeRun は「動いている」にする。 */
function runningWithPending(): RunRow {
  return summarize({ stateJson: stateJson({ runs: [REQ], pendingReview: PENDING }), stageLogs: [RUNNING_LOG] });
}

/** 確認待ちだけの行（動いている段は無い）。 */
function waitingOnly(): RunRow {
  const snap = waitingSnapshot();
  return summarize({ key: 'here|spec-qa', id: 'spec-qa', stateJson: snap.stateJson, stageLogs: snap.stageLogs });
}

test('D0024-AC-05: 動いている段と確認待ちの印が同じ記録にある行は「動き」にだけ数え、「確認待ち」には数えない（summarizeRun の結果で）', async () => {
  const { statusCounts } = await rl();
  const both = runningWithPending();
  assert.equal(both.state, 'running', '行の状態は動いている');
  assert.deepEqual(statusCounts([both]), { waiting: 0, active: 1, top: 'running' });
  const waiting = waitingOnly();
  assert.equal(waiting.state, 'waiting', '対照：動いている段が無い記録は確認待ち');
  assert.deepEqual(statusCounts([waiting]), { waiting: 1, active: 0, top: 'waiting' });
});

test('D0024-AC-05: 動いている段と確認待ちの印が同じ記録にある行は、先に出す確認待ちにも拾わない（summarizeRun の結果で）', async () => {
  const { frontWaitingKey } = await rl();
  const both = runningWithPending();
  const waiting = waitingOnly();
  assert.equal(both.state, 'running');
  assert.equal(frontWaitingKey([both], null), null, 'その行だけなら、先に出す確認待ちは無い');
  assert.equal(frontWaitingKey([both, waiting], null), waiting.key, '対照：確認待ちだけの行があれば、そちらを返す');
  assert.equal(frontWaitingKey([both, waiting], both.key), waiting.key, 'その行を見ていても同じ');
});

// ---- AC-06：止まっているかもしれない行 ----

test('D0024-AC-06: 止まっているかもしれない行（quietSec が目安以上）も「動き」に数える。quietSec が違っても件数は同じ', async () => {
  const { statusCounts } = await rl();
  for (const quietSec of [undefined, null, 0, 59, 600, 612, 100_000]) {
    const r = quietSec === undefined ? row({ state: 'running' }) : row({ state: 'running', quietSec });
    assert.deepEqual(statusCounts([r]), { waiting: 0, active: 1, top: 'running' }, `quietSec=${String(quietSec)}`);
  }
  const quiet = [
    row({ key: 'here|a', state: 'running', quietSec: 612 }),
    row({ key: 'here|b', state: 'running', quietSec: 5 }),
    row({ key: 'wt.feat-x|', state: 'running', quietSec: 100_000, other: true }),
    row({ key: 'here|c', state: 'waiting' }),
  ];
  const calm = quiet.map((r) => ({ ...r, quietSec: null }));
  assert.deepEqual(statusCounts(quiet), { waiting: 1, active: 3, top: 'waiting' });
  assert.deepEqual(statusCounts(quiet), statusCounts(calm), 'quietSec を全部 null にしても同じ');
});

test('D0024-AC-06: 件数を作る関数は目安（staleAfterSec）を引数に取らない（statusCounts は 1 つ、hasOtherCounted は rows と選びの 2 つ）', async () => {
  const fns = await rl();
  const { isCounted, statusCounts, countedRows, hasOtherCounted } = fns;
  for (const name of ['isCounted', 'statusCounts', 'countedRows', 'hasOtherCounted'] as const) {
    assert.equal(typeof fns[name], 'function', `${name} は関数`);
  }
  assert.equal(isCounted.length, 1);
  assert.equal(statusCounts.length, 1);
  assert.equal(countedRows.length, 1);
  assert.equal(hasOtherCounted.length, 2);
});

// ---- AC-11：選んでいる実行は一覧の行（key）で決める ----

test('D0024-AC-11: hasOtherCounted：選んでいる実行のほかに数える行があるか。選んでいる実行は一覧の行（key）で決める', async () => {
  const { hasOtherCounted } = await rl();
  const a = (state: RunState, p: Partial<RunRow> = {}) => row({ key: 'here|a', state, ...p });
  const b = (state: RunState, p: Partial<RunRow> = {}) => row({ key: 'wt.feat-x|b', state, other: true, ...p });
  const cases: readonly (readonly [string, RunRow[], string, boolean])[] = [
    ['動いている 1 件だけ', [a('running')], 'here|a', false],
    ['動いている実行と、別の確認待ち', [a('running'), b('waiting')], 'here|a', true],
    ['動いている実行と、別の終わった行', [a('running'), b('done', { result: '合格' })], 'here|a', false],
    ['終わった（合格）実行と、別の確認待ち', [a('done', { result: '合格' }), b('waiting')], 'here|a', true],
    ['終わった実行と、別の終わった行', [a('done', { result: '合格' }), b('done', { result: '不合格' })], 'here|a', false],
    ['待ちの実行と、別の待ち', [a('idle'), b('idle')], 'here|a', true],
    ['確認待ちの実行と、別の動いている行', [a('waiting'), b('running')], 'here|a', true],
    ['確認待ちの実行が 1 件だけ', [a('waiting')], 'here|a', false],
    ['別の行を選んでいる（選んでいない方が数える行）', [a('running'), b('done', { result: '合格' })], 'wt.feat-x|b', true],
    ['archive の行だけ（終わった）', [row({ key: 'here|archive/20261016-090000', state: 'done', previous: true })], 'here|archive/20261016-090000', false],
    ['行が空', [], 'here|', false],
    ['一覧に無い選び（記録なしの直下）と、別の確認待ち', [b('waiting')], 'here|', true],
    ['一覧に無い選び（記録なしの直下）と、別の待ち', [b('idle')], 'here|', true],
    ['一覧に無い選び（記録なしの直下）と、終わった行だけ', [b('done', { result: '合格' })], 'here|', false],
  ];
  for (const [name, rows, selected, expected] of cases) {
    assert.equal(hasOtherCounted(rows, selected), expected, name);
  }
});

// ---- AC-12：top ----

test('D0024-AC-12: statusCounts の top は 確認待ち ＞ 動いている ＞ 待ち。数える行が無ければ null（入れる順を替えても同じ）', async () => {
  const { statusCounts } = await rl();
  const cases: readonly (readonly [string, readonly RunState[], Top])[] = [
    ['行が空', [], null],
    ['終わった行だけ', ['done', 'done'], null],
    ['待ちだけ', ['idle'], 'idle'],
    ['待ちと終わった', ['idle', 'done'], 'idle'],
    ['動いている', ['running'], 'running'],
    ['動いているものと待ち', ['idle', 'running'], 'running'],
    ['確認待ち', ['waiting'], 'waiting'],
    ['確認待ち・動いている・待ち', ['idle', 'running', 'waiting'], 'waiting'],
    ['確認待ちと終わった', ['done', 'waiting'], 'waiting'],
  ];
  for (const [name, states, top] of cases) {
    const rows = states.map((state, i) => row({ key: `here|r${i}`, state }));
    assert.equal(statusCounts(rows).top, top, name);
    assert.equal(statusCounts([...rows].reverse()).top, top, `${name}（逆順）`);
  }
});

// ---- AC-16：数えた実行の並び（countedRows） ----

/** 並びを確かめる行：終わった行 2 つ（合格・archive）と、数える行 5 つ。入れる順は並びの順ではない。 */
const COUNTED_ROWS = (): RunRow[] => [
  row({ key: 'here|done', state: 'done', result: '合格', updatedMs: t(0) }),
  row({ key: 'here|idle', state: 'idle', updatedMs: t(1) }),
  row({ key: 'here|run-old', state: 'running', updatedMs: t(9) }),
  row({ key: 'wt.feat-x|', state: 'waiting', other: true, updatedMs: t(8) }),
  row({ key: 'here|run-new', state: 'running', updatedMs: t(2) }),
  row({ key: 'here|archive/20261016-090000', state: 'done', previous: true, updatedMs: t(3) }),
  row({ key: 'here|wait-new', state: 'waiting', updatedMs: t(4) }),
];
const COUNTED_ORDER = ['here|wait-new', 'wt.feat-x|', 'here|run-new', 'here|run-old', 'here|idle'];

test('D0024-AC-16: countedRows は数える行だけを、確認待ち → 動いている → 待ち、同じ状態の中は新しい順で返す（終わった行は入れない）', async () => {
  const { countedRows } = await rl();
  assert.deepEqual(countedRows(COUNTED_ROWS()).map((r) => r.key), COUNTED_ORDER);
});

test('D0024-AC-16: countedRows は、行を入れる順を替えても同じ並びで返し、一覧の並び（sortRows）と同じ', async () => {
  const { countedRows } = await rl();
  const rows = COUNTED_ROWS();
  const orders: readonly (readonly [string, RunRow[]])[] = [
    ['逆順', [...rows].reverse()],
    ['並べ替えた順', [rows[3]!, rows[0]!, rows[6]!, rows[1]!, rows[5]!, rows[2]!, rows[4]!]],
  ];
  for (const [name, input] of orders) {
    assert.deepEqual(countedRows(input).map((r) => r.key), COUNTED_ORDER, name);
  }
  const sorted = sortRows(rows.filter((r) => r.state !== 'done')).map((r) => r.key);
  assert.deepEqual(countedRows(rows).map((r) => r.key), sorted, '一覧の並び（sortRows）と同じ');
});

test('D0024-AC-16: countedRows は、渡した配列の順も中身も変えない（並びの順でない配列を渡して確かめる）', async () => {
  const { countedRows } = await rl();
  const rows = COUNTED_ROWS();
  const before = rows.map((r) => r.key);
  assert.notDeepEqual(before.filter((k) => COUNTED_ORDER.includes(k)), COUNTED_ORDER, '前提：渡す配列は並びの順になっていない');
  countedRows(rows);
  assert.deepEqual(rows.map((r) => r.key), before);
});

test('D0024-AC-16: countedRows は、数える行が無いとき（行が空・終わった行だけ）は空の配列を返す', async () => {
  const { countedRows } = await rl();
  assert.deepEqual(countedRows([]), []);
  assert.deepEqual(countedRows([row({ state: 'done' }), row({ key: 'here|archive/20261016-090000', state: 'done', previous: true })]), []);
});

// ---- AC-28：先に出す確認待ちの行の目印 ----

const WAITING_ROWS = (): RunRow[] => [
  row({ key: 'here|run', state: 'running', updatedMs: t(1) }),
  row({ key: 'here|w-old', state: 'waiting', updatedMs: t(5) }),
  row({ key: 'wt.feat-x|w-new', state: 'waiting', other: true, updatedMs: t(2) }),
  row({ key: 'here|done', state: 'done', result: '合格', updatedMs: t(0) }),
  row({ key: 'here|idle', state: 'idle', updatedMs: t(3) }),
];

test('D0024-AC-28: frontWaitingKey：確認待ちがあり選んでいる実行が確認待ちでないとき、並びで先の確認待ちの key を返す（行を入れる順を替えても同じ）', async () => {
  const { frontWaitingKey } = await rl();
  const base = WAITING_ROWS();
  const orders: readonly (readonly [string, RunRow[]])[] = [
    ['そのままの順', base],
    ['逆順', [...base].reverse()],
    ['並べ替えた順', [base[3]!, base[1]!, base[4]!, base[2]!, base[0]!]],
    ['確認待ちを先頭に', [base[1]!, base[2]!, base[0]!, base[3]!, base[4]!]],
  ];
  for (const selected of ['here|run', 'here|done', 'here|idle']) {
    for (const [order, rows] of orders) {
      assert.equal(frontWaitingKey(rows, selected), 'wt.feat-x|w-new', `${selected}・${order}：新しい方の確認待ち`);
    }
  }
});

test('D0024-AC-28: frontWaitingKey：確認待ちが同じ時刻なら、一覧と同じく key の小さい方を先に返す', async () => {
  const { frontWaitingKey } = await rl();
  const rows = [
    row({ key: 'here|bb', state: 'waiting', updatedMs: t(2) }),
    row({ key: 'here|aa', state: 'waiting', updatedMs: t(2) }),
    row({ key: 'here|run', state: 'running', updatedMs: t(0) }),
  ];
  assert.equal(frontWaitingKey(rows, 'here|run'), 'here|aa');
  assert.equal(frontWaitingKey([...rows].reverse(), 'here|run'), 'here|aa');
});

test('D0024-AC-28: frontWaitingKey：選んでいる実行がすでに確認待ちのとき（ほかにも確認待ちがあっても）・確認待ちが無いとき・行が空のときは null', async () => {
  const { frontWaitingKey } = await rl();
  const cases: readonly (readonly [string, RunRow[], string | null])[] = [
    ['選んでいる実行が確認待ち（ほかにも確認待ちがある）', WAITING_ROWS(), 'here|w-old'],
    ['選んでいる実行が一覧で先の確認待ち（ほかにも確認待ちがある）', WAITING_ROWS(), 'wt.feat-x|w-new'],
    ['選んでいる実行が確認待ちの 1 件だけ', [row({ key: 'here|w', state: 'waiting' })], 'here|w'],
    ['確認待ちが無い（動いている・待ち・終わった）', [row({ key: 'here|a', state: 'running' }), row({ key: 'here|b', state: 'idle' }), row({ key: 'here|c', state: 'done', result: '合格' })], 'here|a'],
    ['確認待ちが無く、選びが無い', [row({ key: 'here|a', state: 'running' })], null],
    ['行が空（選びあり）', [], 'here|'],
    ['行が空（選びが無い）', [], null],
  ];
  for (const [name, rows, selected] of cases) {
    assert.equal(frontWaitingKey(rows, selected), null, name);
  }
});

test('D0024-AC-28: frontWaitingKey：選びが無い（null）・一覧に無い選びのときは、先頭の確認待ちを返す', async () => {
  const { frontWaitingKey } = await rl();
  const rows = WAITING_ROWS();
  assert.equal(frontWaitingKey(rows, null), 'wt.feat-x|w-new', '選びが無い');
  assert.equal(frontWaitingKey(rows, 'here|'), 'wt.feat-x|w-new', '一覧に無い選び（記録なしの直下）');
  assert.equal(frontWaitingKey(rows, 'wt.gone|'), 'wt.feat-x|w-new', '一覧に無い選び（消えた worktree）');
});

// ---- AC-29：案内が付くのは件数の形のときだけ ----

test('D0024-AC-29: frontWaitingKey が空でなければ hasOtherCounted は真（案内が付くのは件数の形のときだけ）', async () => {
  const { frontWaitingKey, hasOtherCounted } = await rl();
  const STATES: readonly RunState[] = ['waiting', 'running', 'idle', 'done'];
  let pointed = 0;
  for (const s0 of STATES) {
    for (const s1 of STATES) {
      for (const s2 of STATES) {
        const rows = [
          row({ key: 'here|a', state: s0, updatedMs: t(1) }),
          row({ key: 'wt.feat-x|b', state: s1, other: true, updatedMs: t(2) }),
          row({ key: 'here|c', state: s2, updatedMs: t(3) }),
        ];
        for (const selected of ['here|a', 'wt.feat-x|b', 'here|c', 'here|', null]) {
          const front = frontWaitingKey(rows, selected);
          if (front === null) continue;
          pointed += 1;
          assert.equal(hasOtherCounted(rows, selected ?? 'here|'), true, `${[s0, s1, s2].join('/')}・選び ${String(selected)}`);
        }
      }
    }
  }
  assert.ok(pointed > 0, '先に出す確認待ちがある入力を 1 つ以上確かめた');
});

// ---- AC-31：返すのは渡した行の key で、実行の目印の形に合うものだけ ----

test('D0024-AC-31: frontWaitingKey が返すのは渡した行の key で、実行の目印の形に合うものだけ（形の違う key の行は飛ばす）', async () => {
  const { frontWaitingKey } = await rl();
  const badKeys = ['bogus', '', 'here', 'other|x', 'here|../x', 'here|A B', 'wt.|', '../x', 'here|archive/x'];
  for (const bad of badKeys) {
    assert.equal(parseRunKey(bad), null, `前提：${JSON.stringify(bad)} は実行の目印の形でない`);
    const onlyBad = [row({ key: bad, state: 'waiting', updatedMs: t(0) }), row({ key: 'here|run', state: 'running' })];
    assert.equal(frontWaitingKey(onlyBad, 'here|run'), null, `${JSON.stringify(bad)} だけが確認待ちなら返すものが無い`);
    const withGood = [
      row({ key: bad, state: 'waiting', updatedMs: t(0) }),
      row({ key: 'here|ok', state: 'waiting', updatedMs: t(9) }),
      row({ key: 'here|run', state: 'running' }),
    ];
    const key = frontWaitingKey(withGood, 'here|run');
    assert.equal(key, 'here|ok', `${JSON.stringify(bad)} の行は、新しくても飛ばす`);
    assert.notEqual(parseRunKey(key), null);
  }
});

test('D0024-AC-31: frontWaitingKey は選んでいる実行の引数が壊れた値（null・数・../x ほか）でも、その値を返さない（返すのは渡した行の key）', async () => {
  const { frontWaitingKey } = await rl();
  const rows = [row({ key: 'here|run', state: 'running', updatedMs: t(0) }), row({ key: 'wt.feat-x|w', state: 'waiting', other: true, updatedMs: t(1) })];
  const broken: readonly unknown[] = [null, 5, 0, '../x', '', 'here|../x', 'bogus', {}, [], true, undefined];
  for (const selected of broken) {
    const key = frontWaitingKey(rows, selected as string | null);
    assert.equal(key, 'wt.feat-x|w', `選び ${JSON.stringify(selected) ?? String(selected)}`);
    assert.ok(rows.some((r) => r.key === key), '渡した行の key');
    assert.notEqual(key, selected);
  }
});
