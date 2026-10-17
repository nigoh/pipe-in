// プラグを離した点から、差す先のブロックを決める。純粋な関数だけ。
// コンセント（タップ）を先に見て、次にブロックの四角を見る。コンセントはブロックの左の外にあるので、
// その上で離しても差さるようにする（前は、離した点の下のブロックだけを見ていた）。
import { END, frameOf } from './pipeModel.ts';
import type { PipeModel, Point } from './pipeModel.ts';
import { SOCKET_BOX, blockRect, emptySockets } from './pipeWires.ts';
import type { Wire } from './pipeWires.ts';

/** コンセント1つ：差し込む点と、ケーブルが入ってくる向き（単位ベクトル） */
interface Socket { id: string; x: number; y: number; dx: number; dy: number }

function sockets(m: PipeModel, wires: readonly Wire[]): Socket[] {
  const out: Socket[] = [];
  for (const w of wires) {
    const tip = w.points[w.points.length - 1], before = w.points[w.points.length - 2];
    if (!tip || !before) continue;
    const len = Math.hypot(tip.x - before.x, tip.y - before.y) || 1;
    out.push({ id: w.to, x: tip.x, y: tip.y, dx: (tip.x - before.x) / len, dy: (tip.y - before.y) / len });
  }
  for (const e of emptySockets(m, wires)) out.push({ ...e, dx: 1, dy: 0 });
  return out;
}

/** 点 p の、コンセントの向きでの位置（入ってくる向きが +x） */
const local = (s: Socket, p: Point): Point => {
  const vx = p.x - s.x, vy = p.y - s.y;
  return { x: vx * s.dx + vy * s.dy, y: -vx * s.dy + vy * s.dx };
};
const within = (v: number, lo: number, hi: number, tol: number): boolean => v >= lo - tol && v <= hi + tol;

/** 点 p で離したときに差す先（段・枠・始まり・終わりの id）。どこにも当たらなければ null。tol はコンセントのまわりのゆとり（図の座標） */
export function dropTarget(m: PipeModel, wires: readonly Wire[], p: Point, tol: number): string | null {
  const all = sockets(m, wires), B = SOCKET_BOX;
  // 1. コンセント（向きを回した外形＋ゆとり）
  for (const s of all) {
    const q = local(s, p);
    if (within(q.x, B.x, B.x + B.w, tol) && within(q.y, B.y, B.y + B.h, tol)) return s.id;
  }
  // 2. 横向きに並んだコンセント（タップ）の、あいだのすき間も同じブロック
  const taps = new Map<string, Socket[]>();
  for (const s of all) if (Math.abs(s.dy) < 1e-9 && s.dx > 0) taps.set(s.id, [...(taps.get(s.id) ?? []), s]);
  for (const [id, list] of taps) {
    const x = list[0]!.x, ys = list.map((s) => s.y);
    if (list.some((s) => s.x !== x)) continue;
    if (within(p.x - x, B.x, B.x + B.w, tol) && within(p.y, Math.min(...ys) + B.y, Math.max(...ys) + B.y + B.h, tol)) return id;
  }
  // 3. ブロックの四角（段が先。枠の中の段もその段。次に枠、始まり・終わり）
  const inRect = (id: string): boolean => {
    const r = blockRect(m, id);
    return p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h;
  };
  const stages = [...m.stages].sort((a, b) => Number(!frameOf(m, a)) - Number(!frameOf(m, b)));
  for (const s of stages) if (inRect(s.id)) return s.id;
  for (const f of m.frames) if (inRect(f.id)) return f.id;
  for (const id of ['start', END]) if (inRect(id)) return id;
  return null;
}
