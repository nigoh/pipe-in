// ケーブルの通り道：段や枠をよけ、同じ通路を通るケーブルは高さをずらす。
// 差し込む側は、相手のブロックの縁から 16px 手前（コンセントの面）で止める。入ってくる本数だけコンセントを縦に並べる。
// 差し戻しは、段の下か上の、ほかの段に当たらない方を回る。純粋な関数だけ。
import { END, TERMINAL_SIZE, blockSize, frameOf, orderStages } from './pipeModel.ts';
import type { PipeModel, Point, Rect } from './pipeModel.ts';

export type WireKind = 'start' | 'next' | 'route' | 'return';
export interface Wire {
  kind: WireKind;
  from: string;
  to: string;
  label?: string;
  /** 自分をやり直す（差し戻しの先が自分） */
  self?: boolean;
  /** つなぎを持っている段か枠の id（消すときに使う） */
  owner?: string;
  points: Point[];
}

/** 段の id・枠の id・'start'・'end' の四角 */
export function blockRect(m: PipeModel, id: string): Rect {
  if (id === 'start' || id === END) {
    const t = id === 'start' ? m.start : m.end;
    return { x: t.x, y: t.y, w: TERMINAL_SIZE.w, h: TERMINAL_SIZE.h };
  }
  const f = m.frames.find((x) => x.id === id);
  if (f) return { x: f.x, y: f.y, w: f.w, h: f.h };
  const s = m.stages.find((x) => x.id === id);
  if (!s) return { x: 0, y: 0, w: 0, h: 0 };
  const z = blockSize(s.kind);
  return { x: s.x, y: s.y, w: z.w, h: z.h };
}

type Edge = Omit<Wire, 'points'> & { k?: number; oo?: number; io?: number };

function edges(m: PipeModel): Edge[] {
  const E: Edge[] = [];
  const first = orderStages(m)[0];
  if (first) { const f = frameOf(m, first); E.push({ kind: 'start', from: 'start', to: f ? f.id : first.id }); }
  for (const s of m.stages) {
    const inFrame = frameOf(m, s) !== null;
    if (!inFrame) {
      if (s.routes.length) s.routes.forEach((r, k) => E.push({ kind: 'route', from: s.id, to: r.to, label: r.key, k, owner: s.id }));
      else if (s.next) E.push({ kind: 'next', from: s.id, to: s.next, owner: s.id });
    }
    // 自分をやり直す判定は、差し替える先が無いのでケーブルにしない（カードの札で示す。D0005）
    if (s.check.on && s.onFail && s.onFail !== s.id) E.push({ kind: 'return', from: s.id, to: s.onFail, owner: s.id });
  }
  for (const f of m.frames) if (f.next) E.push({ kind: 'next', from: f.id, to: f.next, owner: f.id });
  const exists = (id: string): boolean => id === END || m.stages.some((s) => s.id === id) || m.frames.some((f) => f.id === id);
  return E.filter((e) => exists(e.to));
}

const inflate = (r: Rect, d: number): Rect => ({ x: r.x - d, y: r.y - d, w: r.w + 2 * d, h: r.h + 2 * d });

function hitsRect(a: Point, b: Point, r: Rect): boolean {
  const n = Math.max(2, Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / 8));
  for (let i = 0; i <= n; i++) {
    const x = a.x + ((b.x - a.x) * i) / n, y = a.y + ((b.y - a.y) * i) / n;
    if (x > r.x && x < r.x + r.w && y > r.y && y < r.y + r.h) return true;
  }
  return false;
}
const clear = (pts: Point[], obs: Rect[]): boolean => pts.every((p, i) => i === 0 || obs.every((r) => !hitsRect(pts[i - 1]!, p, r)));

interface Track { side: string; y: number; lo: number; hi: number }
/** 空いている通路の高さを探す（take なら、その高さを使うことにして覚える） */
function findTrack(tracks: Track[], side: string, x0: number, x1: number, base: number, dir: number, take: boolean): number {
  const lo = Math.min(x0, x1), hi = Math.max(x0, x1);
  for (let t = 0; t < 40; t++) {
    const y = base + dir * t * 12;
    // 近い高さ（10px 未満）で横の範囲が重なれば、同じ通路とみなして次の高さへ
    if (!tracks.some((k) => k.side === side && Math.abs(k.y - y) < 10 && k.hi > lo - 6 && k.lo < hi + 6)) {
      if (take) tracks.push({ side, y, lo, hi });
      return y;
    }
  }
  return base;
}
const takeTrack = (tracks: Track[], side: string, x0: number, x1: number, base: number, dir: number): number =>
  findTrack(tracks, side, x0, x1, base, dir, true);

/** ケーブルがよけるもの：枠の外の段・枠・始まり・終わり（つなぐ両端とその枠は除く） */
function obstacles(m: PipeModel, except: Set<string>): Rect[] {
  const list: Rect[] = [];
  for (const s of m.stages) if (!except.has(s.id) && !frameOf(m, s)) list.push(blockRect(m, s.id));
  for (const f of m.frames) if (!except.has(f.id)) list.push(blockRect(m, f.id));
  for (const t of ['start', END]) if (!except.has(t)) list.push(blockRect(m, t));
  return list.map((r) => inflate(r, 12));
}

/**
 * 決まった形の候補がどれも段に当たるときの道探し：段の縁に沿った格子の上で、曲がる回数を抑えた最短の道（縦横だけ）。
 * a から b へ、障害物の外だけを通る。見つからなければ null。
 */
function detour(a: Point, b: Point, obs: Rect[]): Point[] | null {
  const pad = 6, xs = new Set([a.x, b.x]), ys = new Set([a.y, b.y]);
  for (const r of obs) { xs.add(r.x - pad); xs.add(r.x + r.w + pad); ys.add(r.y - pad); ys.add(r.y + r.h + pad); }
  const all = [...obs, { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y) }];
  xs.add(Math.min(...all.map((r) => r.x)) - 40); xs.add(Math.max(...all.map((r) => r.x + r.w)) + 40);
  ys.add(Math.min(...all.map((r) => r.y)) - 40); ys.add(Math.max(...all.map((r) => r.y + r.h)) + 40);
  const X = [...xs].sort((p, q) => p - q), Y = [...ys].sort((p, q) => p - q), W = X.length;
  const inside = (x: number, y: number): boolean => obs.some((r) => x > r.x && x < r.x + r.w && y > r.y && y < r.y + r.h);
  const ok = (p: Point, q: Point): boolean => obs.every((r) => !hitsRect(p, q, r));
  const si = X.indexOf(a.x) + Y.indexOf(a.y) * W, ti = X.indexOf(b.x) + Y.indexOf(b.y) * W;
  const BEND = 60, DIRS: [number, number][] = [[1, 0], [-1, 0], [0, 1], [0, -1]];
  // 状態 = 格子の点 × 来た向き。小さな二分ヒープで距離の短い順に広げる
  const dist = new Map<number, number>(), prev = new Map<number, number>(), heap: [number, number][] = [];
  const push = (d: number, k: number): void => {
    heap.push([d, k]);
    for (let i = heap.length - 1; i > 0;) { const j = (i - 1) >> 1; if (heap[j]![0] <= heap[i]![0]) break; [heap[i], heap[j]] = [heap[j]!, heap[i]!]; i = j; }
  };
  const pop = (): [number, number] => {
    const top = heap[0]!, last = heap.pop()!;
    if (heap.length) {
      heap[0] = last;
      for (let i = 0; ;) {
        const l = 2 * i + 1, r = l + 1;
        let m = i;
        if (l < heap.length && heap[l]![0] < heap[m]![0]) m = l;
        if (r < heap.length && heap[r]![0] < heap[m]![0]) m = r;
        if (m === i) break;
        [heap[i], heap[m]] = [heap[m]!, heap[i]!];
        i = m;
      }
    }
    return top;
  };
  const start = si * 5 + 4;
  dist.set(start, 0);
  push(0, start);
  while (heap.length) {
    const [d, k] = pop();
    if (d > (dist.get(k) ?? Infinity)) continue;
    const node = Math.floor(k / 5), dir = k % 5;
    if (node === ti) {
      const pts: Point[] = [];
      for (let c: number | undefined = k; c !== undefined; c = prev.get(c)) { const n = Math.floor(c / 5); pts.unshift({ x: X[n % W]!, y: Y[Math.floor(n / W)]! }); }
      // 同じ向きに続く点をまとめる
      return pts.filter((p, i) => i === 0 || i === pts.length - 1 || !((pts[i - 1]!.x === p.x && p.x === pts[i + 1]!.x) || (pts[i - 1]!.y === p.y && p.y === pts[i + 1]!.y)));
    }
    const i = node % W, j = Math.floor(node / W);
    DIRS.forEach(([dx, dy], nd) => {
      const ni = i + dx, nj = j + dy;
      if (ni < 0 || nj < 0 || ni >= W || nj >= Y.length) return;
      const p = { x: X[i]!, y: Y[j]! }, q = { x: X[ni]!, y: Y[nj]! }, n = ni + nj * W;
      if ((n !== ti && inside(q.x, q.y)) || !ok(p, q)) return;
      const nk = n * 5 + nd, cost = d + Math.abs(q.x - p.x) + Math.abs(q.y - p.y) + (dir !== 4 && dir !== nd ? BEND : 0);
      if (cost < (dist.get(nk) ?? Infinity)) { dist.set(nk, cost); prev.set(nk, k); push(cost, nk); }
    });
  }
  return null;
}

function routeReturn(m: PipeModel, e: Edge, p1: Point, p2: Point, tracks: Track[]): Point[] {
  if (e.self) {
    const y0 = p1.y;
    return [{ x: p1.x + 26, y: y0 }, { x: p1.x + 26, y: y0 + 52 }, { x: p1.x - 26, y: y0 + 52 }, { x: p1.x - 26, y: y0 + 16 }];
  }
  const ra = blockRect(m, e.from), rb = blockRect(m, e.to);
  const lo = Math.min(p1.x, p2.x), hi = Math.max(p1.x, p2.x);
  const all = [...m.stages.map((s) => blockRect(m, s.id)), ...m.frames.map((f) => blockRect(m, f.id))].filter((r) => r.x + r.w > lo && r.x < hi);
  // 段（枠の中の段も）に当たらない方を回る
  const others = m.stages.filter((s) => s.id !== e.from && s.id !== e.to).map((s) => inflate(blockRect(m, s.id), 8))
    .concat([inflate(blockRect(m, END), 8), inflate(blockRect(m, 'start'), 8)]);
  // 上と下の通路は、前へ進むケーブルと同じ高さの割り当てを使う（差し戻しと重ならないように）
  const yb = takeTrack(tracks, 'down', lo, hi, Math.max(p1.y, rb.y + rb.h, ...all.map((r) => r.y + r.h)) + 30, 1);
  const below = [p1, { x: p1.x, y: yb }, { x: p2.x, y: yb }, { x: p2.x, y: rb.y + rb.h + 16 }];
  if (clear(below, others)) return below;
  const t1 = { x: p1.x, y: ra.y }, t2 = { x: p2.x, y: rb.y - 16 };
  const ya = takeTrack(tracks, 'up', lo, hi, Math.min(t1.y, rb.y, ...all.map((r) => r.y)) - 30, -1);
  const above = [t1, { x: t1.x, y: ya }, { x: t2.x, y: ya }, t2];
  if (clear(above, others)) return above;
  // どちらも当たるときは、段をよけて道を探す。出口は段の下か上、入口は戻す先の下か上のコンセント。いちばん短い道にする
  const walls = [...others, inflate(ra, 8), inflate(rb, 8)];
  const exits: [Point, Point][] = [[p1, { x: p1.x, y: ra.y + ra.h + 14 }], [t1, { x: p1.x, y: ra.y - 14 }]];
  const entries: [Point, Point][] = [[{ x: p2.x, y: rb.y + rb.h + 30 }, { x: p2.x, y: rb.y + rb.h + 16 }], [{ x: p2.x, y: rb.y - 30 }, t2]];
  const length = (pts: Point[]): number => pts.reduce((n, q, i) => (i ? n + Math.abs(q.x - pts[i - 1]!.x) + Math.abs(q.y - pts[i - 1]!.y) + 60 : 0), 0);
  let best: Point[] | null = null;
  for (const [from, out] of exits) {
    for (const [tip, end] of entries) {
      const path = detour(out, tip, walls);
      if (path && (!best || length([from, ...path, end]) < length(best))) best = [from, ...path, end];
    }
  }
  return best ?? below;
}

function routeForward(m: PipeModel, e: Edge, p1: Point, p2: Point, tracks: Track[]): Point[] {
  const except = new Set([e.from, e.to]);
  const src = m.stages.find((s) => s.id === e.from);
  const srcFrame = src ? frameOf(m, src) : null;
  if (srcFrame) except.add(srcFrame.id);
  const obs = obstacles(m, except);
  const dy = Math.abs(p2.y - p1.y);
  // 段のあいだに隙間があれば、路線図のように斜めに曲がってまっすぐつなぐ
  if (p2.x - p1.x > 40) {
    const xb = p2.x - 22, xa = xb - dy;
    if (xa >= p1.x + 14) {
      const pts = dy < 1 ? [p1, p2] : [p1, { x: xa, y: p1.y }, { x: xb, y: p2.y }, p2];
      if (clear(pts, obs)) return pts;
    }
  }
  // 通路：範囲にある物の上か下を通る
  const lo = Math.min(p1.x, p2.x), hi = Math.max(p1.x, p2.x);
  const inRange = obs.filter((r) => r.x + r.w > lo && r.x < hi);
  const top = Math.min(p1.y, p2.y, ...inRange.map((r) => r.y)) - 16;
  const bot = Math.max(p1.y, p2.y, ...inRange.map((r) => r.y + r.h)) + 16;
  const preferUp = Math.abs(p1.y - top) + Math.abs(p2.y - top) <= Math.abs(p1.y - bot) + Math.abs(p2.y - bot);
  const a = p1.x + 16, b = p2.x - 18;
  // 通路へは斜めに降りる（路線図らしく）。斜めの区間がほかの段に当たるなら、まっすぐ降りる。だめなら反対側の通路
  const shapes = (yc: number): Point[][] => {
    const d1 = Math.abs(p1.y - yc), d2 = Math.abs(p2.y - yc);
    const square = [p1, { x: a, y: p1.y }, { x: a, y: yc }, { x: b, y: yc }, { x: b, y: p2.y }, p2];
    return b - a > d1 + d2 + 10 ? [[p1, { x: a, y: p1.y }, { x: a + d1, y: yc }, { x: b - d2, y: yc }, { x: b, y: p2.y }, p2], square] : [square];
  };
  let fallback: Point[] | null = null;
  for (const up of preferUp ? [true, false] : [false, true]) {
    const side = up ? 'up' : 'down', base = up ? top : bot, dir = up ? -1 : 1;
    const yc = findTrack(tracks, side, lo, hi, base, dir, false);
    const found = shapes(yc).find((pts) => clear(pts, obs));
    if (found) { takeTrack(tracks, side, lo, hi, base, dir); return found; }
    fallback ??= shapes(yc).pop()!;
  }
  // どの形も段に当たるときは、段をよけて道を探す（出口は右へ、入口は左から）
  const path = detour({ x: a, y: p1.y }, { x: b, y: p2.y }, obs);
  if (path) return [p1, ...path, p2];
  takeTrack(tracks, preferUp ? 'up' : 'down', lo, hi, preferUp ? top : bot, preferUp ? -1 : 1);
  return fallback!;
}

export function layoutWires(m: PipeModel): Wire[] {
  const E = edges(m), tracks: Track[] = [];
  const midY = (id: string): number => { const r = blockRect(m, id); return r.y + r.h / 2; };
  const outs = new Map<string, Edge[]>(), ins = new Map<string, Edge[]>();
  for (const e of E) {
    if (e.kind === 'return') continue;
    outs.set(e.from, [...(outs.get(e.from) ?? []), e]);
    ins.set(e.to, [...(ins.get(e.to) ?? []), e]);
  }
  for (const list of outs.values()) {
    const gap = list.some((e) => e.kind === 'route') ? 22 : 12; // 分岐は名札が載るので広く
    list.sort((a, b) => midY(a.to) - midY(b.to)).forEach((e, i) => { e.oo = (i - (list.length - 1) / 2) * gap; });
  }
  // 入ってくる本数だけ、電源タップのようにコンセントを縦に並べる
  for (const list of ins.values()) list.sort((a, b) => midY(a.from) - midY(b.from)).forEach((e, i) => { e.io = (i - (list.length - 1) / 2) * 26; });
  const span = (e: Edge): number => Math.abs(blockRect(m, e.to).x - blockRect(m, e.from).x);
  // 短いケーブルから先に通路を取る（長いケーブルが外側を回る）。差し戻しは最後
  return [...E].sort((a, b) => Number(a.kind === 'return') - Number(b.kind === 'return') || span(a) - span(b)).map((e) => {
    const ra = blockRect(m, e.from), rb = blockRect(m, e.to);
    let points: Point[];
    if (e.kind === 'return') {
      points = routeReturn(m, e, { x: ra.x + ra.w / 2, y: ra.y + ra.h }, { x: rb.x + rb.w / 2, y: rb.y + rb.h + 16 }, tracks);
    } else {
      points = routeForward(m, e, { x: ra.x + ra.w, y: midY(e.from) + (e.oo ?? 0) }, { x: rb.x - 16, y: midY(e.to) + (e.io ?? 0) }, tracks);
    }
    const { oo: _oo, io: _io, k: _k, ...wire } = e;
    return { ...wire, points };
  });
}

/** 線を角の丸い SVG の path にする */
export function roundedPath(pts: Point[], r = 9): string {
  if (pts.length < 3) return `M ${pts[0]!.x} ${pts[0]!.y} L ${pts[pts.length - 1]!.x} ${pts[pts.length - 1]!.y}`;
  let d = `M ${pts[0]!.x} ${pts[0]!.y}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const p = pts[i]!, a = pts[i - 1]!, b = pts[i + 1]!;
    const la = Math.hypot(p.x - a.x, p.y - a.y), lb = Math.hypot(b.x - p.x, b.y - p.y);
    const k = Math.min(r, la / 2, lb / 2);
    const s = { x: p.x + ((a.x - p.x) * k) / (la || 1), y: p.y + ((a.y - p.y) * k) / (la || 1) };
    const t = { x: p.x + ((b.x - p.x) * k) / (lb || 1), y: p.y + ((b.y - p.y) * k) / (lb || 1) };
    d += ` L ${s.x} ${s.y} Q ${p.x} ${p.y} ${t.x} ${t.y}`;
  }
  const z = pts[pts.length - 1]!;
  return `${d} L ${z.x} ${z.y}`;
}

/** 点 p から tol 以内を通る「次の段」のケーブルのうち、いちばん近いものの番号（無ければ -1）。間に挟む先を探すのに使う */
export function nearestWire(wires: readonly Wire[], p: Point, tol: number): number {
  let best = -1, bestD = tol;
  wires.forEach((w, i) => {
    if (w.kind !== 'next') return;
    for (let k = 1; k < w.points.length; k++) {
      const d = segDist(p, w.points[k - 1]!, w.points[k]!);
      if (d <= bestD) { bestD = d; best = i; }
    }
  });
  return best;
}

function segDist(p: Point, a: Point, b: Point): number {
  const dx = b.x - a.x, dy = b.y - a.y, len = dx * dx + dy * dy;
  const t = len === 0 ? 0 : Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len));
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}
