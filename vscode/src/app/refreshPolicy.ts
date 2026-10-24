// 更新の決まり：監視の対象・まとめる時間・読み直しの間隔・work_dir の有無を確かめる間隔と、その間隔で動く小さなタイマー、古い読み込みの結果を捨てる世代の番号。
// 時計は引数で受ける（テストは偽のタイマーを渡す）。vscode を import しない。

/** いまの work_dir の下で見るファイル。対象を狭めない（直下とパイプのフォルダの state.json・*.md・logs/*.jsonl） */
export const WATCH_GLOB = '{state.json,*.md,logs/*.jsonl,*/state.json,*/*.md,*/logs/*.jsonl}';
/** 監視の知らせをまとめる時間 */
export const DEBOUNCE_MS = 200;
/** 別の worktree と archive の読み直しの間隔（別の worktree の行があるあいだと、パネルが見えている間） */
export const POLL_MS = 5000;
/** いまの work_dir があるかを確かめる間隔（stat を 1 回呼ぶだけ。無いあいだは見張りを張らず、これで見つける。約 5 秒の読み直しとは別） */
export const PRESENCE_CHECK_MS = 3000;

/**
 * 約 5 秒ごとの読み直しを続けるか。次のどちらかのとき続ける：
 * ・別の worktree の行があるとき（hasOtherWorktree。パネルが隠れていても。ステータスバーの件数を新しく保つため）
 * ・パネルが見えていて、別の場所／archive の行があるか、選んだ run が動いている・確認待ちのとき（時系列の帯を伸ばすため）
 * 別の worktree の行が無く（hasOtherWorktree を省いたときも同じ）、パネルが隠れていれば止める。
 */
export function shouldPoll(state: { visible: boolean; hasRemote: boolean; live: boolean; hasOtherWorktree?: boolean }): boolean {
  return state.hasOtherWorktree === true || (state.visible && (state.hasRemote || state.live));
}

/** 世代の番号。読み込みを始めるたびに番号を進め、最後に始めた読み込みの結果だけを使う（古い結果を捨てる）。 */
export interface Generation {
  /** 番号を進めて返す（読み込みを始める時と、途中の結果を捨てたい時に呼ぶ） */
  next(): number;
  /** 渡した番号が、いま最後に進めた番号か */
  isCurrent(id: number): boolean;
}

/** 世代の番号を 1 つ作る。番号は作った部品ごとに持つ（別々に作った世代は、お互いの番号を捨てない）。 */
export function createGeneration(): Generation {
  let current = 0;
  return {
    next(): number {
      current++;
      return current;
    },
    isCurrent(id: number): boolean {
      return id === current;
    },
  };
}

export interface PollerOptions<Handle> {
  intervalMs: number;
  /** くり返す仕事（読み直しや、work_dir の有無の確かめ）。失敗しても次を仕掛ける（例外は外へ出さない） */
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

/** setTimeout を連ねる形のくり返し（読み直しや有無の確かめ）。run が終わってから次を仕掛けるので、遅いときに重ならない。 */
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
