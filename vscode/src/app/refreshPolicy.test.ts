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

test('D0019-AC-27: running は start のあと真、stop のあと偽（読み直しが動いているかを表す）', async () => {
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

// ---- D0024：別の worktree の行があるあいだは、パネルが見えていなくても読み直す（shouldPoll の新しい入力 hasOtherWorktree）----
// 真なら、見えているか・別の場所／archive の行（hasRemote）・選んだ run が動いている（live）に関わらず続ける。
// 偽にした・省いた呼び出しは、上の表（D0019-AC-27）のまま。

for (const [visible, hasRemote, live, today] of POLL_CASES) {
  // 今の表で既に続く組は、旗を無視する今の作りでも通る
  const suffix = today ? '（今のまま通る。守る）' : '';
  test(`D0024-AC-35: shouldPoll：別の worktree の行がある（hasOtherWorktree=true）なら、見えている=${visible}・別の場所か archive の行=${hasRemote}・選んだ run が動いている／確認待ち=${live} でも true${suffix}`, async () => {
    const { shouldPoll } = await policy();
    assert.equal(shouldPoll({ visible, hasRemote, live, hasOtherWorktree: true }), true);
  });
}

const WITHOUT_FLAG: [string, { hasOtherWorktree?: boolean }][] = [
  ['省いた', {}],
  ['偽にした', { hasOtherWorktree: false }],
  ['undefined を渡した', { hasOtherWorktree: undefined }],
];

for (const [how, extra] of WITHOUT_FLAG) {
  for (const [visible, hasRemote, live, expected] of POLL_CASES) {
    test(`D0024-AC-36: shouldPoll：hasOtherWorktree を${how}呼び出しは、今の表と同じ（見えている=${visible}・別の場所か archive の行=${hasRemote}・選んだ run が動いている／確認待ち=${live}）で ${expected}（今のまま通る。守る）`, async () => {
      const { shouldPoll } = await policy();
      assert.equal(shouldPoll({ visible, hasRemote, live, ...extra }), expected);
    });
  }
}

// ---- D0024-AC-40：古い読み込みの結果が、新しい結果を上書きしない（世代の番号。createPoller の generation と同じ考え方）----

test('D0024-AC-40: createGeneration：next() は増え続ける番号を返し、いま最後に進めた番号だけが isCurrent になる', async () => {
  const { createGeneration } = await policy();
  const generation = createGeneration();
  const numbers = Array.from({ length: 5 }, () => generation.next());
  for (let i = 1; i < numbers.length; i++) assert.ok(numbers[i]! > numbers[i - 1]!, `${numbers.join(',')} は増え続ける`);
  assert.deepEqual(numbers.map((n) => generation.isCurrent(n)), [false, false, false, false, true]);
});

test('D0024-AC-40: createGeneration：まだ進めていない先の番号・壊れた値は isCurrent にならない', async () => {
  const { createGeneration } = await policy();
  const generation = createGeneration();
  const mine = generation.next();
  for (const other of [mine + 1, mine - 1, Number.NaN, -1]) assert.equal(generation.isCurrent(other), false, String(other));
  assert.equal(generation.isCurrent(mine), true);
});

test('D0024-AC-40: createGeneration：別々に作った世代は、お互いの番号を捨てない', async () => {
  const { createGeneration } = await policy();
  const first = createGeneration();
  const second = createGeneration();
  const mine = first.next();
  second.next();
  second.next();
  assert.equal(first.isCurrent(mine), true);
});

type Step = 'start A' | 'start B' | 'end A' | 'end B' | 'discard';

/**
 * 読み込み A・B の始まりと終わりを並べた通りに起こして、結果が反映された読み込みの名前を返す。
 * 読み込みは「始めに next() → 待つ → 終わったとき isCurrent なら反映」（extension.ts の loadLatest と同じ形）。待ちは手で開ける（時間は使わない）。
 */
async function simulate(steps: Step[]): Promise<string[]> {
  const { createGeneration } = await policy();
  const generation = createGeneration();
  const applied: string[] = [];
  const gates = new Map<string, () => void>();
  const loads = new Map<string, Promise<void>>();
  for (const step of steps) {
    if (step === 'discard') {
      generation.next();
      continue;
    }
    const [verb, name] = step.split(' ') as ['start' | 'end', string];
    if (verb === 'start') {
      loads.set(
        name,
        (async () => {
          const mine = generation.next();
          await new Promise<void>((resolve) => gates.set(name, resolve));
          if (generation.isCurrent(mine)) applied.push(name);
        })(),
      );
    } else {
      gates.get(name)!();
      await loads.get(name);
    }
  }
  return applied;
}

const TIMELINES: [string, Step[], string[]][] = [
  ['読み込みが 1 つだけなら、反映される', ['start A', 'end A'], ['A']],
  ['終わってから次を始める（重ならない）なら、両方反映される', ['start A', 'end A', 'start B', 'end B'], ['A', 'B']],
  ['先に始めた方があとに終わっても、反映されない（後に始めた方が先に終わって、反映される）', ['start A', 'start B', 'end B', 'end A'], ['B']],
  ['後が始まっていれば、先に始めた方が先に終わっても反映されない', ['start A', 'start B', 'end A', 'end B'], ['B']],
  ['next() で捨てると、始めていた読み込みは終わっても反映されない', ['start A', 'discard', 'end A'], []],
];

for (const [name, steps, expected] of TIMELINES) {
  test(`D0024-AC-40: 古い結果を世代の番号で捨てる：${name}`, async () => {
    assert.deepEqual(await simulate(steps), expected);
  });
}
