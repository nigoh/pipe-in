// 更新の決まり：監視の対象・まとめる時間・読み直しの間隔と、その間隔で動く小さなタイマー。
// 時計は引数で受ける（テストは偽のタイマーを渡す）。vscode を import しない。

/** いまの work_dir の下で見るファイル。対象を狭めない（直下とパイプのフォルダの state.json・*.md・logs/*.jsonl） */
export const WATCH_GLOB = '{state.json,*.md,logs/*.jsonl,*/state.json,*/*.md,*/logs/*.jsonl}';
/** 監視の知らせをまとめる時間 */
export const DEBOUNCE_MS = 200;
/** 別の worktree と archive の読み直しの間隔（パネルが見えている間だけ） */
export const POLL_MS = 5000;

/**
 * 約 5 秒ごとの読み直しを続けるか。パネルが見えていて、別の場所／archive の行があるか、
 * 選んだ run が動いている・確認待ちのとき（時系列の帯を伸ばすため）に続ける。隠れていれば止める。
 */
export function shouldPoll(state: { visible: boolean; hasRemote: boolean; live: boolean }): boolean {
  return state.visible && (state.hasRemote || state.live);
}

export interface PollerOptions<Handle> {
  intervalMs: number;
  /** 読み直し。失敗しても次を仕掛ける（例外は外へ出さない） */
  run: () => Promise<void>;
  setTimer: (fn: () => void, ms: number) => Handle;
  clearTimer: (handle: Handle) => void;
}

export interface Poller {
  /** 動かし始める。すぐには run を呼ばず、intervalMs 後に呼ぶ。二重に呼んでも 1 本 */
  start(): void;
  /** 止める。仕掛け済みのタイマーを消し、run の途中でも次を仕掛けない */
  stop(): void;
  readonly running: boolean;
}

/** setTimeout を連ねる形の読み直し。run が終わってから次を仕掛けるので、遅いときに重ならない。 */
export function createPoller<Handle>(options: PollerOptions<Handle>): Poller {
  const { intervalMs, run, setTimer, clearTimer } = options;
  let active = false;
  /** start のたびに進める。止めて始め直したあとに、前の run の続きが次を仕掛けないようにする */
  let generation = 0;
  let handle: Handle | undefined;

  function arm(): void {
    const mine = generation;
    handle = setTimer(() => {
      handle = undefined;
      void (async () => {
        try {
          await run();
        } catch {
          // 読み直しの失敗では止めない
        }
        if (active && generation === mine) arm();
      })();
    }, intervalMs);
  }

  return {
    start(): void {
      if (active) return;
      active = true;
      generation++;
      arm();
    },
    stop(): void {
      active = false;
      generation++;
      if (handle !== undefined) clearTimer(handle);
      handle = undefined;
    },
    get running(): boolean {
      return active;
    },
  };
}
