// 時系列の確認待ちの言葉を、どこに置くかを決める（D0089）。純粋な関数。vscode は import しない。
// 帯の右端が 85% を超えると言葉は帯の左に置く（右に出ると枠の外へ出るため）。ただし待ちの帯が狭く、
// その左にある実行の帯が言葉の範囲にかかるときは、言葉が実行の帯の上に乗って読めないので、帯の下の行に出す。

export type WaitSide = 'right' | 'left' | 'below';

/** 帯の位置（トラックに対する %）。left が左端、end が右端、width が幅。 */
export interface PlaceBar {
  left: number;
  end: number;
  width: number;
}

export interface PlaceInput {
  /** 待ちの帯 */
  wait: PlaceBar;
  /** 同じ行の実行の帯。無ければ null */
  run: PlaceBar | null;
  /** 言葉が「● 待っている」つきで長いか */
  long: boolean;
}

/** 帯の右端がこの割合（%）を超えたら、言葉は帯の左に置く。 */
export const SIDE_LIMIT = 85;
/** 待ちの帯の幅がこの割合（%）未満なら「狭い待ち」。 */
export const WAIT_NARROW = 5;
/** 「確認待ち m:ss」の言葉の長さの目安（トラックに対する %）。 */
export const WAIT_TEXT_SHORT = 18;
/** 「確認待ち m:ss ● 待っている」の言葉の長さの目安（同）。 */
export const WAIT_TEXT_LONG = 32;

export function placeWaitText(input: PlaceInput): WaitSide {
  const { wait, run, long } = input;
  if (wait.end <= SIDE_LIMIT) return 'right';
  if (wait.width >= WAIT_NARROW || run === null) return 'left';
  const reach = wait.left - (long ? WAIT_TEXT_LONG : WAIT_TEXT_SHORT);
  return run.left < wait.left && run.end > reach ? 'below' : 'left';
}
