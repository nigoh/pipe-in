// ケーブルの抜き差し：つないだケーブルの先のプラグを、別のコンセントへ差し直す・抜く。純粋な関数だけ。
// 差し直しても種類（次の段・分岐・差し戻し）はそのままで、行き先だけ変わる。種類に合わない先は、理由を返して何も変えない。
import { END, frameOf, membersOf, orderStages } from './pipeModel.ts';
import type { FrameModel, PipeModel, StageModel } from './pipeModel.ts';
import type { Wire } from './pipeWires.ts';

export interface PlugResult {
  changed: boolean;
  message: string;
  /** 差し直した先（枠の中の段へ差したときは枠）。変わったときだけ */
  to?: string;
}

const no = (message: string): PlugResult => ({ changed: false, message });
const stageOf = (m: PipeModel, id: string): StageModel | undefined => m.stages.find((s) => s.id === id);
const frameById = (m: PipeModel, id: string): FrameModel | undefined => m.frames.find((f) => f.id === id);
const nameOf = (m: PipeModel, id: string): string =>
  id === END ? '終わり' : stageOf(m, id)?.label ?? (frameById(m, id) ? `並列の枠「${frameById(m, id)!.name}」` : id);

/** 並びの位置：段はその順番、枠は入口が中の最初の段・出口が中の最後の段、終わりはいちばん右 */
function places(m: PipeModel): { entry(id: string): number; exit(id: string): number } {
  const ord = orderStages(m), pos = (id: string): number => ord.findIndex((s) => s.id === id);
  const inside = (id: string): number[] => { const f = frameById(m, id); return f ? membersOf(m, f).map((s) => pos(s.id)) : [pos(id)]; };
  return {
    entry: (id) => (id === END ? Infinity : Math.min(...inside(id))),
    exit: (id) => Math.max(...inside(id)),
  };
}

/** ケーブルの先のプラグを to のコンセントへ差し直す */
export function replug(m: PipeModel, w: Wire, to: string): PlugResult {
  if (w.kind === 'start') return no('始まりから出るケーブルは、いちばん左の段へ自動でつながります');
  if (to === w.to) return { changed: false, message: '' };
  if (to === 'start') return no('始まりには差せません');
  if (to !== END && !stageOf(m, to) && !frameById(m, to)) return no('差す先が見つかりません');
  const toFrame = frameById(m, to);
  if (toFrame && membersOf(m, toFrame).length === 0) return no('中に段のない枠には差せません');
  const owner = w.owner ?? w.from, s = stageOf(m, owner), f = frameById(m, owner), at = places(m);

  if (w.kind === 'return') {
    if (!s) return { changed: false, message: '' };
    if (frameOf(m, s) && to !== s.id) return no('並列の枠の中の段は、自分をやり直すだけです');
    if (to === s.id) {
      s.onFail = null;
      s.check.on = true;
      return { changed: true, message: `${s.label}：判定に通らなければ、自分をやり直します`, to };
    }
    if (toFrame) return no('差し戻しは、枠ではなく段へ差してください');
    if (to === END || at.entry(to) >= at.exit(s.id)) return no('差し戻しは、前（左）の段へだけ差せます');
    s.onFail = to;
    s.check.on = true;
    return { changed: true, message: `${s.label}：判定に通らなければ「${nameOf(m, to)}」へ戻します`, to };
  }

  // 次の段・分岐：枠の中の段へ差したら、その枠へつなぐ
  const target = stageOf(m, to), tf = target ? frameOf(m, target) : null, dest = tf ? tf.id : to;
  if (dest === w.to) return { changed: false, message: '' };
  if (at.entry(dest) <= at.exit(owner)) return no('次の段や分岐のケーブルは、右にある段へだけ差せます（前へ戻すときは差し戻しにします）');
  if (w.kind === 'route' && s) {
    const r = s.routes.find((x) => x.key === w.label && x.to === w.to);
    if (!r) return { changed: false, message: '' };
    if (s.routes.some((x) => x !== r && x.to === dest)) return no('その行き先への分岐はもうあります');
    r.to = dest;
    return { changed: true, message: `${s.label}：分岐「${r.key}」→ ${nameOf(m, dest)}`, to: dest };
  }
  if (s) s.next = dest;
  else if (f) f.next = dest;
  else return { changed: false, message: '' };
  return { changed: true, message: `${nameOf(m, owner)} → ${nameOf(m, dest)}`, to: dest };
}

/** ケーブルの先のプラグを抜く（つなぎを外す。差し戻しは判定も切る） */
export function unplug(m: PipeModel, w: Wire): PlugResult {
  if (w.kind === 'start') return no('始まりから出るケーブルは、いちばん左の段へ自動でつながります');
  const owner = w.owner ?? w.from, s = stageOf(m, owner), f = frameById(m, owner);
  if (w.kind === 'route' && s) s.routes = s.routes.filter((r) => !(r.key === w.label && r.to === w.to));
  else if (w.kind === 'next' && s) s.next = null;
  else if (w.kind === 'next' && f) f.next = null;
  else if (w.kind === 'return' && s) { s.onFail = null; s.check.on = false; }
  else return { changed: false, message: '' };
  return { changed: true, message: `${nameOf(m, owner)} のプラグを抜きました` };
}
