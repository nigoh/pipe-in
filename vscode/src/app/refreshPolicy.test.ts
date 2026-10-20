// 更新の決まり（D0019）：監視の対象・まとめる時間・読み直しの間隔と、その間隔で動く小さなタイマー。
// 時計は引数で受ける（偽のタイマーを渡す）。本物の時間は使わない（sleep しない）。
// 新しい部品（app/refreshPolicy.ts）は、呼んだところで落ちるように、テストの中で読み込む。
import { test } from 'node:test';
import assert from 'node:assert/strict';

const policy = () => import('./refreshPolicy.ts');

test('D0019-AC-26: 監視の対象は今までと同じ（狭めない）。まとめる時間も 200ms のまま', async () => {
  const { WATCH_GLOB, DEBOUNCE_MS } = await policy();
  assert.equal(WATCH_GLOB, '{state.json,*.md,logs/*.jsonl,*/state.json,*/*.md,*/logs/*.jsonl}');
  assert.equal(DEBOUNCE_MS, 200);
});

test('D0019-AC-27: 別の worktree と archive の読み直しの間隔は 5 秒', async () => {
  const { POLL_MS } = await policy();
  assert.equal(POLL_MS, 5000);
});

// ---- 2版目：読み直しを続けるかどうか（shouldPoll）----
// 見えていて、別の場所／archive の行があるか、選んだ run が動いている・確認待ちのときに続ける。隠れていれば止める。

const POLL_CASES: [boolean, boolean, boolean, boolean][] = [
  // visible, hasRemote, live, 期待
  [false, false, false, false],
  [false, true, false, false],
  [false, false, true, false],
  [false, true, true, false],
  [true, false, false, false],
  [true, true, false, true],
  [true, false, true, true],
  [true, true, true, true],
];

for (const [visible, hasRemote, live, expected] of POLL_CASES) {
  test(`D0019-AC-27: shouldPoll（見えている=${visible}・別の場所か archive の行=${hasRemote}・選んだ run が動いている／確認待ち=${live}）は ${expected}`, async () => {
    const { shouldPoll } = await policy();
    assert.equal(shouldPoll({ visible, hasRemote, live }), expected);
  });
}

test('D0019-AC-69: 選んだ run が動いている・確認待ちのあいだは、別の worktree・archive が無くても読み直しが続く（時系列の帯を伸ばすため）。隠れたら止まる', async () => {
  const { shouldPoll } = await policy();
  assert.equal(shouldPoll({ visible: true, hasRemote: false, live: true }), true);
  assert.equal(shouldPoll({ visible: false, hasRemote: false, live: true }), false);
});

/** 手で書いた偽のタイマー。setTimer で仕掛けたものを溜め、fire で期限の来たものを 1 つ呼ぶ。 */
function fakeTimers() {
  let nextId = 1;
  const pending = new Map<number, { fn: () => void; ms: number }>();
  const log = { set: [] as number[], cleared: [] as number[] };
  return {
    pending,
    log,
    setTimer: (fn: () => void, ms: number): number => {
      const id = nextId++;
      pending.set(id, { fn, ms });
      log.set.push(ms);
      return id;
    },
    clearTimer: (id: number): void => {
      log.cleared.push(id);
      pending.delete(id);
    },
    /** 仕掛けてあるタイマーのうち、いちばん古いものを 1 つ呼ぶ（無ければ false） */
    fire(): boolean {
      const first = [...pending.entries()][0];
      if (first === undefined) return false;
      pending.delete(first[0]);
      first[1].fn();
      return true;
    },
  };
}

/** 非同期の後始末（Promise の続き）を流し切る。時間は使わない。 */
const settle = () => new Promise<void>((resolve) => setImmediate(resolve));

async function make() {
  const { createPoller, POLL_MS } = await policy();
  const timers = fakeTimers();
  let runs = 0;
  const gate: { open: (() => void) | null } = { open: null };
  let blocking = false;
  const poller = createPoller({
    intervalMs: POLL_MS,
    run: async () => {
      runs++;
      if (blocking) await new Promise<void>((resolve) => (gate.open = resolve));
    },
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
  });
  return {
    poller,
    timers,
    runs: () => runs,
    block: () => (blocking = true),
    release: () => {
      blocking = false;
      gate.open?.();
    },
  };
}

test('D0019-AC-27: start すると POLL_MS 後に run を呼ぶ（start の時点ではまだ呼ばない）。呼んだあと、また POLL_MS 後に仕掛ける', async () => {
  const t = await make();
  t.poller.start();
  assert.equal(t.runs(), 0);
  assert.deepEqual(t.timers.log.set, [5000]);
  t.timers.fire();
  await settle();
  assert.equal(t.runs(), 1);
  assert.deepEqual(t.timers.log.set, [5000, 5000], 'run が終わったら次を仕掛ける');
  t.timers.fire();
  await settle();
  assert.equal(t.runs(), 2);
});

test('D0019-AC-27: start を二重に呼んでも、タイマーは 1 本', async () => {
  const t = await make();
  t.poller.start();
  t.poller.start();
  t.poller.start();
  assert.equal(t.timers.pending.size, 1);
  assert.equal(t.timers.log.set.length, 1);
  t.timers.fire();
  await settle();
  assert.equal(t.timers.pending.size, 1);
});

test('D0019-AC-27: stop すると仕掛け済みのタイマーを消し、止めたあとは run が呼ばれない', async () => {
  const t = await make();
  t.poller.start();
  t.poller.stop();
  assert.equal(t.timers.pending.size, 0);
  assert.equal(t.timers.log.cleared.length, 1);
  assert.equal(t.timers.fire(), false);
  await settle();
  assert.equal(t.runs(), 0);
  t.poller.stop(); // 二重の stop も安全
});

test('D0019-AC-27: running は start のあと真、stop のあと偽（パネルが見えている間だけ動かす判断に使う）', async () => {
  const t = await make();
  assert.equal(t.poller.running, false);
  t.poller.start();
  assert.equal(t.poller.running, true);
  t.poller.stop();
  assert.equal(t.poller.running, false);
  t.poller.start();
  assert.equal(t.poller.running, true);
});

test('D0019-AC-27: run が終わるまで次を仕掛けない（遅いときに重ならない）', async () => {
  const t = await make();
  t.block();
  t.poller.start();
  t.timers.fire();
  await settle();
  assert.equal(t.runs(), 1);
  assert.equal(t.timers.pending.size, 0, 'run の途中は次を仕掛けない');
  t.release();
  await settle();
  assert.equal(t.timers.pending.size, 1, '終わったら次を仕掛ける');
});

test('D0019-AC-27: run の途中で stop すると、run が終わっても次を仕掛けない', async () => {
  const t = await make();
  t.block();
  t.poller.start();
  t.timers.fire();
  await settle();
  t.poller.stop();
  t.release();
  await settle();
  assert.equal(t.timers.pending.size, 0);
  assert.equal(t.runs(), 1);
});

test('D0019-AC-27: run が失敗しても、読み直しは止まらない（次を仕掛け、例外を外へ出さない）', async () => {
  const { createPoller } = await policy();
  const timers = fakeTimers();
  let runs = 0;
  const poller = createPoller({
    intervalMs: 5000,
    run: async () => {
      runs++;
      throw new Error('読めない');
    },
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
  });
  poller.start();
  timers.fire();
  await settle();
  assert.equal(runs, 1);
  assert.equal(timers.pending.size, 1);
  assert.equal(poller.running, true);
});

test('D0019-AC-27: stop したあとの start で、また動き出す（見えなくなって、また見えた）', async () => {
  const t = await make();
  t.poller.start();
  t.poller.stop();
  t.poller.start();
  t.timers.fire();
  await settle();
  assert.equal(t.runs(), 1);
});
