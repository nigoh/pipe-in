// いまの work_dir の見張りの判断・手順・持ち方。vscode にも node: にも触れない（見張りを作る口・有無を確かめる口・読み直しの口は、呼ぶ側が渡す）。
// work_dir が無いあいだは見張りを張らず、決まった間隔で有無だけを確かめる。できたのを見つけたら見張りを張って読み直し、消えたら外す。
// 判断は 2 つの純粋な関数に集める：decideWatch（張る・外す・そのまま）と finishStep（読み直すか、次の追い読みの番か）。
// 手順の createWorkDirChecker は、この 2 つの答えのとおりに効果（張る・外す・読む）を並べるだけで、読むかどうかを自分では決めない。
// 時計は読まない（間隔は呼ぶ側のタイマーの仕事）。
import type { Generation } from './refreshPolicy.ts';

/** work_dir の有無。分からない（権限・EIO など、無いとも有るとも言えない失敗）のときは、見張りにも表示にも触れない */
export type Presence = 'present' | 'absent' | 'unknown';

/** 見張りをどうするか */
export type WatchAction = 'attach' | 'detach' | 'keep';

/** 見張り 1 つ。vscode の FileSystemWatcher がそのまま満たす形（知らせの登録の戻り値は使わない） */
export interface WatchHandle {
  onDidCreate(listener: () => void): unknown;
  onDidChange(listener: () => void): unknown;
  onDidDelete(listener: () => void): unknown;
  dispose(): void;
}

/** 見張りを持つ部品。持つのは 0 個か 1 個。「見張っているか」を知っているのはここだけ */
export interface WatchHolder {
  /** いま見張りを持っているか */
  readonly active: boolean;
  /** 古い見張りを片付けてから新しく作る。張れたら true。例外は出さず、失敗なら false で「見張っていない」のまま */
  attach(dir: string): boolean;
  /** 見張りを片付ける。二重に呼んでも安全で、片付けが例外でも例外を出さず持ち越さない */
  detach(): void;
}

/** 有無の確かめの手順 */
export interface WorkDirChecker {
  /** 有無を確かめ、張る・外す・そのまま、のあとで、必要なら読み直す。例外で終わらない */
  check(dir: string): Promise<void>;
  /** 見張りを片付け、「最初の確かめ」に戻し、追い読みの番を消す。世代は進めない（進めるのは呼ぶ側） */
  reset(): void;
}

/**
 * 見張りをどうするかを決める。
 * （見張っていない × 有る）→ 張る。（見張っている × 無い）→ 外す。（見張っている × 有る）・（見張っていない × 無い）→ そのまま。
 * 「分からない」は、見張っているかに関わらず、いつもそのまま（一時的な失敗で、生きている見張りを外さない）。
 */
export function decideWatch(watching: boolean, presence: Presence): WatchAction {
  if (presence === 'unknown') return 'keep';
  if (!watching && presence === 'present') return 'attach';
  if (watching && presence === 'absent') return 'detach';
  return 'keep';
}

export interface FinishInput {
  /** decideWatch の答え */
  action: WatchAction;
  /** 張れたか。action が 'attach' のときだけ意味を持つ（ほかでは false を渡す） */
  attached: boolean;
  /** 見る先が決まってから最初の確かめか */
  first: boolean;
  /** 追い読みの番か（前の確かめで張れていた） */
  followUp: boolean;
}

/**
 * 手順の終わりで、読み直すかと、次の確かめが追い読みの番かを決める。読むかどうかの判断はここ 1 か所に置く。
 * 読み直す：最初の確かめ（結果が何でも 1 回）・張れた・外した・追い読みの番。
 * 次の追い読みの番：最初でない確かめで張れたとき（張った直後の取りこぼしを、次の確かめで 1 回だけ拾う）。最初に張ったときはしない。
 */
export function finishStep(input: FinishInput): { read: boolean; followUp: boolean } {
  const attachedNow = input.action === 'attach' && input.attached;
  return {
    read: input.first || attachedNow || input.action === 'detach' || input.followUp,
    followUp: attachedNow && !input.first,
  };
}

/**
 * 見張りを持つ部品を作る。create は見張りを 1 つ作る口、onEvent は 3 つの知らせ（作られた・変わった・消えた）を受ける 1 つの口。
 * 片付けた見張りからの知らせは、onEvent を呼ばない（いま持っているものの知らせだけを流す）。
 */
export function createWatchHolder(options: { create: (dir: string) => WatchHandle; onEvent: () => void }): WatchHolder {
  const { create, onEvent } = options;
  let current: WatchHandle | null = null;

  /** 片付ける。失敗しても外へ出さない */
  function release(handle: WatchHandle): void {
    try {
      handle.dispose();
    } catch {
      // 片付けに失敗しても、持ち越して繰り返さない
    }
  }

  function detach(): void {
    const old = current;
    current = null;
    if (old !== null) release(old);
  }

  return {
    get active(): boolean {
      return current !== null;
    },
    attach(dir: string): boolean {
      detach();
      let made: WatchHandle | null = null;
      try {
        const handle = create(dir);
        made = handle;
        const notify = (): void => {
          if (current === handle) onEvent();
        };
        handle.onDidCreate(notify);
        handle.onDidChange(notify);
        handle.onDidDelete(notify);
        current = handle;
        return true;
      } catch {
        // 作りかけは片付けて、「見張っていない」のままにする（次の確かめでまた試す）
        if (made !== null) release(made);
        return false;
      }
    },
    detach,
  };
}

export interface WorkDirCheckerOptions {
  /** 確かめ用の世代。呼ぶ側のもの（読み込みの世代とは別）。確かめを始めるたびに進め、結果が出たとき現役でなければ捨てる */
  generation: Generation;
  holder: WatchHolder;
  /** 有無を確かめる口（stat 1 回）。例外なら「分からない」と同じに扱う */
  probe: (dir: string) => Promise<Presence>;
  /** 読み直しの口。例外でも握りつぶす */
  reload: () => Promise<void>;
}

/**
 * 有無の確かめの手順を作る。確かめる → 世代が現役か見る → 張る・外す・そのまま → 状態を更新 → 必要なら読み直す、の順。
 * 状態は「最初の確かめか」「追い読みの番か」の 2 つだけ（見張っているかは holder が持つ）。読み直しを待つ前に更新するので、
 * 読み直しが長引いても、次の確かめや reset() が前の状態を見ない。
 */
export function createWorkDirChecker(options: WorkDirCheckerOptions): WorkDirChecker {
  const { generation, holder, probe, reload } = options;
  let first = true;
  let followUp = false;

  return {
    async check(dir: string): Promise<void> {
      const mine = generation.next();
      let presence: Presence;
      try {
        presence = await probe(dir);
      } catch {
        presence = 'unknown';
      }
      // 見る先が変わった・片付けられたあとの結果は捨てる（張らず・外さず・読まず・状態にも触れない）
      if (!generation.isCurrent(mine)) return;
      const action = decideWatch(holder.active, presence);
      let attached = false;
      if (action === 'attach') attached = holder.attach(dir);
      else if (action === 'detach') holder.detach();
      const step = finishStep({ action, attached, first, followUp });
      first = false;
      followUp = step.followUp;
      if (!step.read) return;
      try {
        await reload();
      } catch {
        // 読み直しの失敗では止めない（次の確かめは続く）
      }
    },
    reset(): void {
      holder.detach();
      first = true;
      followUp = false;
    },
  };
}
