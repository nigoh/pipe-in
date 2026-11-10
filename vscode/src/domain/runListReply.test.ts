// 実行の一覧・ステータスバーの件数・知らせ・「先に開く」に、返事を受け付けている確認待ち（印のある実行）を数える（D0079・AC-34〜38）。
// 一覧の行の state は summarizeRun だけが決めるので、行が「確認待ち」になれば、件数（statusCounts）・知らせ（newlyWaitingKeys・planWaitingNotice）・
// 先に開く（frontWaitingKey）は行の state を見るだけで同じ数え方に変わる。この4つの部品の入力は、本物の summarizeRun が作った行を使う。
// 印の無い記録（今ある記録・見本）の行・件数・知らせ・先に開くは今までと同じ結果（AC-38）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { planWaitingNotice } from '../app/notifyWaiting.ts';
import { countStates, frontWaitingKey, hasOtherCounted, sortRows, statusCounts, summarizeRun } from './runList.ts';
import type { RunRow } from './runList.ts';
import { newlyWaitingKeys } from './waitingNotice.ts';
import { fixtureSnapshot } from '../test/liveFixtures.ts';
import { mark, pending, replyRow, replyState } from '../test/replyFixtures.ts';
import type { ReplySnapshotOptions } from '../test/replyFixtures.ts';

const keyed = (id: string, p: ReplySnapshotOptions = {}, sec = 40): RunRow => replyRow({ ...p, key: `here|${id}`, id }, sec);

// ---- AC-34：一覧の行 ----

test('D0079-AC-34: 条件を満たす印のある記録の行は waiting（確認待ち）で、段の表示は印の段の表示名、waitingSec は印の始めた時刻から数える', () => {
  const row = replyRow();
  assert.equal(row.state, 'waiting');
  assert.equal(row.stage, '要件定義');
  assert.equal(row.waitingSec, 40);
  assert.equal(replyRow({}, 100).waitingSec, 100, '「今」が進むと waitingSec も進む');
});

test('D0079-AC-34: パイプの記録の行は、パイプの段の表示名が段の表示になる', () => {
  const row = replyRow({ pipe: 'reply-pipe' });
  assert.equal(row.state, 'waiting');
  assert.equal(row.stage, 'ソースの調査');
  assert.equal(row.waitingSec, 40);
});

test('D0079-AC-34: 印の始めた時刻が読めない行は waiting のまま waitingSec が null', () => {
  const row = replyRow({ mark: mark({ since: 'いつか' }) });
  assert.equal(row.state, 'waiting');
  assert.equal(row.waitingSec, null);
});

const NOT_WAITING: readonly (readonly [string, ReplySnapshotOptions, string])[] = [
  ['driver あり（/pipe-in の記録）', { driver: 'pipe-dev' }, 'idle'],
  ['driver あり（会話の道）', { driver: 'pipe-chat' }, 'idle'],
  ['別の worktree の実行', { other: true }, 'idle'],
  ['archive/ の前の実行', { previous: true }, 'done'],
  ['終わった', { final: 'PASSED' }, 'done'],
  ['動いている段がある', { running: true }, 'running'],
  ['印なし（古い本体の記録）', { mark: null }, 'idle'],
];
for (const [label, options, state] of NOT_WAITING) {
  test(`D0079-AC-34: 条件を 1 つ崩した行は確認待ち（waiting）にならない：${label}（${state}）（今のまま通る。守る）`, () => {
    const row = replyRow(options);
    assert.notEqual(row.state, 'waiting');
    assert.equal(row.state, state);
  });
}

test('D0079-AC-34: 印と pending_review が両方ある行は 1 つの確認待ちで、段の表示は pending_review の段（今までどおり。今のまま通る。守る）', () => {
  const row = replyRow({ pendingReview: pending() });
  assert.equal(row.state, 'waiting');
  assert.equal(row.stage, '要件定義');
  assert.equal(row.waitingSec, 40);
});

test('D0079-AC-34: 別の worktree の行は、印があっても other のまま waiting にならない（今のまま通る。守る）', () => {
  const row = replyRow({ other: true, key: 'wt.feat-x|' });
  assert.equal(row.other, true);
  assert.equal(row.state, 'idle');
});

// ---- AC-35：ステータスバーの件数 ----

test('D0079-AC-35: statusCounts は印のある行を確認待ちに数える（top も確認待ち）', () => {
  assert.deepEqual(statusCounts([replyRow()]), { waiting: 1, active: 0, top: 'waiting' });
  assert.equal(countStates([replyRow()]).waiting, 1);
});

test('D0079-AC-35: pending_review もある行・条件を崩した行と並べても、1 実行は 1 件で二重に数えず、top は確認待ち', () => {
  const rows = [
    keyed('a'),
    keyed('b', { pendingReview: pending() }),
    keyed('c', { driver: 'pipe-dev' }),
    keyed('d', { other: true }),
    keyed('e', { final: 'PASSED' }),
    keyed('f', { running: true }),
  ];
  assert.deepEqual(
    rows.map((r) => r.state),
    ['waiting', 'waiting', 'idle', 'idle', 'done', 'running'],
  );
  assert.deepEqual(statusCounts(rows), { waiting: 2, active: 3, top: 'waiting' });
  assert.deepEqual(countStates(rows), { all: 6, waiting: 2, running: 3, done: 1 });
});

test('D0079-AC-35: 印のある行だけの一覧は top が確認待ち。条件を崩した行だけなら top は待ち（idle）で確認待ちに数えない', () => {
  assert.equal(statusCounts([keyed('a'), keyed('c', { driver: 'pipe-dev' })]).top, 'waiting');
  assert.deepEqual(statusCounts([keyed('c', { driver: 'pipe-dev' })]), { waiting: 0, active: 1, top: 'idle' });
});

test('D0079-AC-35: 選んでいる実行が印のある行 1 つだけなら、ほかに数える行は無い（件数の形にしない）。ほかに終わっていない行があれば件数の形になる', () => {
  const rows = [keyed('a', { final: 'PASSED' }), keyed('b')];
  assert.equal(rows[1]!.state, 'waiting', '印のある行は確認待ちの行');
  assert.equal(hasOtherCounted([rows[1]!], 'here|b'), false);
  assert.equal(hasOtherCounted(rows, 'here|a'), true);
  assert.equal(hasOtherCounted([rows[0]!, keyed('c', { final: 'PASSED' })], 'here|a'), false, '終わった行は数えない');
});

// ---- AC-36：知らせ ----

test('D0079-AC-36: 前の一覧で確認待ちでなかった実行に印が付くと（確認待ちの行になると）、新しく確認待ちになった行として返る', () => {
  const before = keyed('a', { mark: null });
  const after = keyed('a');
  assert.equal(before.state, 'idle');
  assert.deepEqual(newlyWaitingKeys([before], [after]), ['here|a']);
  assert.deepEqual(newlyWaitingKeys([], [after]), ['here|a'], '前の一覧に無かった行も同じ扱い');
});

test('D0079-AC-36: 続けて同じ印のままなら二度は知らせない（前の一覧も確認待ちの行）', () => {
  const rows = [keyed('a')];
  assert.equal(rows[0]!.state, 'waiting', '印のある行は確認待ちの行');
  assert.deepEqual(newlyWaitingKeys(rows, rows), []);
  assert.deepEqual(newlyWaitingKeys([keyed('a', {}, 40)], [keyed('a', {}, 45)]), []);
});

test('D0079-AC-36: 条件を崩した行（driver あり・別の worktree）に印が付いても、知らせの対象にならない（今のまま通る。守る）', () => {
  const before = [keyed('a', { mark: null, driver: 'pipe-dev' }), keyed('b', { mark: null, other: true })];
  const after = [keyed('a', { driver: 'pipe-dev' }), keyed('b', { other: true })];
  assert.deepEqual(newlyWaitingKeys(before, after), []);
});

test('D0079-AC-36: planWaitingNotice は印が付いた行を返し、設定が false なら出さず、パネルが見えていて選んでいる実行と同じ行は外す', () => {
  const prev = [keyed('a', { mark: null }), keyed('b', { mark: null })];
  const rows = [keyed('a'), keyed('b')];
  const base = { prev, rows, selected: 'here|zzz', panelVisible: false, enabled: true };
  assert.deepEqual(planWaitingNotice(base).map((r) => r.key), ['here|a', 'here|b']);
  assert.deepEqual(planWaitingNotice({ ...base, enabled: false }), []);
  assert.deepEqual(planWaitingNotice({ ...base, panelVisible: true, selected: 'here|a' }).map((r) => r.key), ['here|b']);
  assert.deepEqual(planWaitingNotice({ ...base, panelVisible: false, selected: 'here|a' }).map((r) => r.key), ['here|a', 'here|b']);
});

test('D0079-AC-36: 印のまま続く行は planWaitingNotice も二度出さない', () => {
  const rows = [keyed('a')];
  assert.equal(rows[0]!.state, 'waiting', '印のある行は確認待ちの行');
  assert.deepEqual(planWaitingNotice({ prev: rows, rows, selected: 'here|zzz', panelVisible: false, enabled: true }), []);
});

// ---- AC-37：先に開く ----

test('D0079-AC-37: 選んでいる実行が確認待ちでないとき、印のある行（確認待ちの行）が先に開く行として返る', () => {
  const rows = [keyed('done', { final: 'PASSED' }), keyed('a')];
  assert.equal(frontWaitingKey(rows, 'here|done'), 'here|a');
});

test('D0079-AC-37: 選んでいる実行がすでに確認待ち（印のある行）なら null', () => {
  const rows = [keyed('a'), keyed('b')];
  assert.deepEqual(rows.map((r) => r.state), ['waiting', 'waiting'], '印のある行は確認待ちの行');
  assert.equal(frontWaitingKey(rows, 'here|a'), null);
});

test('D0079-AC-37: 確認待ちの行が複数あるときは、一覧の並び（sortRows）で先に出る行。印のある行と pending_review の行が混ざっても同じ', () => {
  const older = '2026-10-17T10:00:30';
  const newer = '2026-10-17T10:09:30';
  const at = (stamp: string, over: ReplySnapshotOptions = {}) => ({ ...over, stateJson: JSON.stringify({ ...(JSON.parse(replyState(over)) as object), updated_at: stamp }) });
  const rows = [keyed('done', { final: 'PASSED' }), keyed('old', at(older)), keyed('new', at(newer, { mark: null, pendingReview: pending() }))];
  assert.deepEqual(sortRows(rows.filter((r) => r.state === 'waiting')).map((r) => r.key), ['here|new', 'here|old']);
  assert.equal(frontWaitingKey(rows, 'here|done'), 'here|new');
  assert.equal(frontWaitingKey(rows.slice(0, 2), 'here|done'), 'here|old');
});

test('D0079-AC-37: 条件を崩した行（印があっても driver あり・別の worktree）は先に開く行にならない（今のまま通る。守る）', () => {
  const rows = [keyed('done', { final: 'PASSED' }), keyed('c', { driver: 'pipe-dev' }), keyed('d', { other: true })];
  assert.equal(frontWaitingKey(rows, 'here|done'), null);
});

// ---- AC-38：印の無い記録は今までと同じ ----

const FIXTURES: readonly (readonly [string, string, RunRow['state']])[] = [
  ['showcase', 'showcase', 'done'],
  // 1 つ目は行の目印に使う名前（実行のフォルダ名に _ は使えないので - にする）、2 つ目は見本のフォルダ名
  ['showcase-running', 'showcase_running', 'running'],
  ['showcase-running-next', 'showcase_running_next', 'running'],
  ['showcase-waiting', 'showcase_waiting', 'waiting'],
];
const clock = { nowMs: Date.parse('2026-10-17T10:02:15+00:00') + 40_000, localOffsetMin: 0 };
const fixtureRow = (dir: string, key: string): RunRow => {
  const snap = fixtureSnapshot(dir);
  return summarizeRun({ key, id: '', branch: null, other: false, memoHead: null, previous: false, stateJson: snap.stateJson, stageLogs: snap.stageLogs }, clock);
};

test('D0079-AC-38: 印の無い見本の記録（tests/fixtures の 4 つ）の行は、今までと同じ状態になる（今のまま通る。守る）', () => {
  for (const [name, dir, state] of FIXTURES) {
    assert.equal(JSON.parse(fixtureSnapshot(dir).stateJson!).reply_wait, undefined, `${name} は印を持たない見本`);
    assert.equal(fixtureRow(dir, `here|${name}`).state, state, name);
  }
  const waiting = fixtureRow('showcase_waiting', 'here|w');
  assert.equal(waiting.stage, '要件定義');
  assert.equal(waiting.waitingSec, 40);
});

test('D0079-AC-38: 印の無い見本の行の件数・知らせ・先に開くは今までと同じ結果（今のまま通る。守る）', () => {
  const rows = FIXTURES.map(([name, dir]) => fixtureRow(dir, `here|${name}`));
  assert.deepEqual(statusCounts(rows), { waiting: 1, active: 2, top: 'waiting' });
  assert.deepEqual(newlyWaitingKeys(rows.map((r) => ({ ...r, state: 'running' as const })), rows), ['here|showcase-waiting']);
  assert.equal(frontWaitingKey(rows, 'here|showcase'), 'here|showcase-waiting');
  assert.equal(frontWaitingKey(rows, 'here|showcase-waiting'), null);
});

test('D0079-AC-38: 印の無い pending_review の記録（--pause・/pipe-in）の行は今までどおり確認待ち（今のまま通る。守る）', () => {
  for (const driver of [undefined, 'pipe-dev', 'pipe-chat']) {
    const row = replyRow({ mark: null, pendingReview: pending(), ...(driver === undefined ? {} : { driver }) });
    assert.equal(row.state, 'waiting', String(driver));
    assert.equal(row.waitingSec, 40);
  }
});
