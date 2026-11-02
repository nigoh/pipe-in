// 作業台に渡す「今日」と「前の実績」の選び方（D0066）：app/costContext.ts の estimateContext。純粋な関数（今の時刻は引数 nowMs）。
// 新しい部品は、呼んだところで落ちるように、テストの中で読み込む。
// 部品の形（このファイルが決める。実装はこれに合わせる）：
//   estimateContext(list: RunList | null, pipeName: string, nowMs: number) → { today: 'YYYY-MM-DD'（UTC）; actualUsd: number | null }
//   実績は、list.entries の中で !row.other && !row.previous && row.pipe === pipeName の行の costUsd。複数なら updatedMs が大きい（新しい）行。
//   RunRow.costUsd は D0066 で足す項目（domain/runList.ts）。テストでは、型に入るまで、行に足して渡す。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { RunList } from './runList.ts';
import type { RunRow } from '../domain/runList.ts';
import { row } from '../test/runListFixtures.ts';

interface Ctx {
  today: string;
  actualUsd: number | null;
}
type Fn = (list: RunList | null, pipe: string, nowMs: number) => Ctx;

async function fn(): Promise<Fn> {
  try {
    return ((await import('./costContext.ts')) as unknown as { estimateContext: Fn }).estimateContext;
  } catch (e) {
    return assert.fail(`app/costContext.ts が無い（まだ作っていない）: ${String(e)}`);
  }
}

const NOW = Date.UTC(2026, 10, 2, 12, 0, 0);
type Cost = { costUsd?: number | null };
const entry = (over: Partial<RunRow>, cost: number | null | undefined) => ({
  row: { ...row(over), ...(cost === undefined ? {} : { costUsd: cost }) } as ReturnType<typeof row> & Cost,
  dirAbs: '/w/docs/pipeline',
});
const listOf = (...entries: ReturnType<typeof entry>[]): RunList =>
  ({ entries, omitted: [], omittedWorktrees: 0, hasRemote: false, hasOtherWorktree: false }) as unknown as RunList;

test('D0066-AC-22: ここで動いたパイプの実績を選ぶ（today は nowMs の UTC の日付）', async () => {
  const ctx = (await fn())(listOf(entry({ pipe: 'p' }, 1.5)), 'p', NOW);
  assert.deepEqual(ctx, { today: '2026-11-02', actualUsd: 1.5 });
});

test('D0066-AC-22: 別の worktree の行・前の実行（archive）・別のパイプの行は実績にしない（null）', async () => {
  const f = await fn();
  const list = listOf(entry({ pipe: 'p', other: true }, 9), entry({ pipe: 'p', previous: true }, 8), entry({ pipe: 'q' }, 7));
  assert.equal(f(list, 'p', NOW).actualUsd, null);
  assert.equal(f(list, 'q', NOW).actualUsd, 7, '別のパイプ q の行は、q を開いたときの実績');
});

test('D0066-AC-22: 行が無い・一覧が null・costUsd が無い・null のときは、実績なし（null）。today は出る', async () => {
  const f = await fn();
  assert.deepEqual(f(null, 'p', NOW), { today: '2026-11-02', actualUsd: null });
  assert.deepEqual(f(listOf(), 'p', NOW), { today: '2026-11-02', actualUsd: null });
  assert.equal(f(listOf(entry({ pipe: 'p' }, undefined)), 'p', NOW).actualUsd, null);
  assert.equal(f(listOf(entry({ pipe: 'p' }, null)), 'p', NOW).actualUsd, null);
});

test('D0066-AC-22: 同じパイプの行が複数あるときは、更新の新しい行（updatedMs が大きい）の実績', async () => {
  const f = await fn();
  const list = listOf(entry({ pipe: 'p', updatedMs: 1000 }, 1), entry({ pipe: 'p', updatedMs: 5000 }, 5), entry({ pipe: 'p', updatedMs: 3000 }, 3));
  assert.equal(f(list, 'p', NOW).actualUsd, 5);
});

test('D0066-AC-22: today は UTC の日付（日付の境の直前・直後）', async () => {
  const f = await fn();
  assert.equal(f(null, 'p', Date.UTC(2026, 11, 31, 23, 59, 59)).today, '2026-12-31');
  assert.equal(f(null, 'p', Date.UTC(2027, 0, 1, 0, 0, 0)).today, '2027-01-01');
});
