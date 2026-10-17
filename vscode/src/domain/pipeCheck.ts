// 段の判定：スイッチのオン・オフと、不合格のときの行き先。純粋な関数だけ。
// 判定を切るのはスイッチだけ。ケーブルを抜いても判定は残し、その段をやり直すにする（D0005）。
import { frameOf, orderStages } from './pipeModel.ts';
import type { PipeModel, StageModel } from './pipeModel.ts';

/** 判定を入れる。すぐ保存できるよう、Claude が判定する・この段をやり直すで始める */
export function turnCheckOn(s: StageModel): void {
  s.check.on = true;
  s.check.verdict = true;
  s.onFail = null;
}

export function turnCheckOff(s: StageModel): void {
  s.check.on = false;
  s.onFail = null;
}

/** スイッチの入口。すでに同じ向きなら何も変えない（オンのまま押し直しても設定を消さない） */
export function setCheck(s: StageModel, on: boolean): void {
  if (s.check.on === on) return;
  if (on) turnCheckOn(s);
  else turnCheckOff(s);
}

/** 不合格のときの行き先：この段をやり直す（self）か、前の段へ戻す（back） */
export function failKind(m: PipeModel, s: StageModel): 'self' | 'back' {
  return s.onFail && s.onFail !== s.id && m.stages.some((x) => x.id === s.onFail) ? 'back' : 'self';
}

/**
 * 「不合格のとき」に選べる前の段（並びで自分より前の段。並列の枠の中の段へも、ケーブルの差し直しと同じく戻せる）。
 * 枠の中の段は自分をやり直すだけ
 */
export function failTargets(m: PipeModel, s: StageModel): StageModel[] {
  if (frameOf(m, s)) return [];
  const ord = orderStages(m);
  return ord.slice(0, ord.indexOf(s));
}
