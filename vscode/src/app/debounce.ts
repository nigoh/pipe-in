// 短い間の知らせを1回にまとめる（D0065）。時計（タイマー）は呼ぶ側が渡す。
export interface Debouncer { poke(): void; cancel(): void }

/** poke を何度呼んでも、最後の poke から wait ms 後に run を 1 回だけ呼ぶ */
export function createDebouncer<H>(o: { wait: number; setTimer: (fn: () => void, ms: number) => H; clearTimer: (h: H) => void; run: () => void }): Debouncer {
  let handle: { h: H } | null = null;
  const cancel = (): void => {
    if (handle) o.clearTimer(handle.h);
    handle = null;
  };
  return {
    poke() {
      cancel();
      handle = { h: o.setTimer(() => { handle = null; o.run(); }, o.wait) };
    },
    cancel,
  };
}
