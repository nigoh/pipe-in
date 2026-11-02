// デバウンス（D0065）：知らせが何度来ても、最後から wait ms 後に 1 回だけ run を呼ぶ。時計（タイマー）は呼ぶ側が渡す。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createDebouncer } from './debounce.ts';

/** 手で進めるタイマーの偽物。fireAll は、いま残っているタイマーを全部（登録順に）鳴らす */
function fakeTimers() {
  let n = 0;
  const live = new Map<number, { fn: () => void; ms: number }>();
  return {
    live,
    setTimer: (fn: () => void, ms: number): number => { live.set(++n, { fn, ms }); return n; },
    clearTimer: (h: number): void => { live.delete(h); },
    fireAll(): void {
      for (const [h, t] of [...live]) { live.delete(h); t.fn(); }
    },
  };
}

test('D0065-AC-07: 短い間に poke を 5 回呼んでも、run は 1 回だけ（待つ長さは wait）', () => {
  const t = fakeTimers();
  let runs = 0;
  const d = createDebouncer({ wait: 300, setTimer: t.setTimer, clearTimer: t.clearTimer, run: () => { runs++; } });
  for (let i = 0; i < 5; i++) d.poke();
  assert.equal(runs, 0, 'まだ待っている');
  for (const x of t.live.values()) assert.equal(x.ms, 300);
  t.fireAll();
  assert.equal(runs, 1);
  t.fireAll();
  assert.equal(runs, 1, '鳴らす物はもう残っていない');
});

test('D0065-AC-07: run のあとの poke は、また 1 回の run になる', () => {
  const t = fakeTimers();
  let runs = 0;
  const d = createDebouncer({ wait: 50, setTimer: t.setTimer, clearTimer: t.clearTimer, run: () => { runs++; } });
  d.poke();
  t.fireAll();
  d.poke();
  d.poke();
  t.fireAll();
  assert.equal(runs, 2);
});

test('D0065-AC-07: cancel すると run しない（poke を呼んだあとでも）', () => {
  const t = fakeTimers();
  let runs = 0;
  const d = createDebouncer({ wait: 300, setTimer: t.setTimer, clearTimer: t.clearTimer, run: () => { runs++; } });
  d.poke();
  d.poke();
  d.cancel();
  t.fireAll();
  assert.equal(runs, 0);
  d.cancel(); // 二重に呼んでも安全
});

test('D0065-AC-07: cancel のあとでも、次の poke は効く', () => {
  const t = fakeTimers();
  let runs = 0;
  const d = createDebouncer({ wait: 300, setTimer: t.setTimer, clearTimer: t.clearTimer, run: () => { runs++; } });
  d.poke();
  d.cancel();
  d.poke();
  t.fireAll();
  assert.equal(runs, 1);
});

test('D0065-AC-07: 時計は渡したものだけを使う（poke のたびに渡した setTimer が呼ばれる）', () => {
  const calls: number[] = [];
  const d = createDebouncer({ wait: 123, setTimer: (_fn, ms) => { calls.push(ms); return calls.length; }, clearTimer: () => {}, run: () => {} });
  d.poke();
  assert.deepEqual(calls, [123]);
});
