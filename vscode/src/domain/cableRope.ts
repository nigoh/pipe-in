// 引いている最中のケーブルを、ひもとして動かす。純粋な関数だけ（時刻の刻みは引数で受け取り、時計・画面に触れない）。
// 点の位置と1歩前の位置で進め（Verlet 積分）、となりの点の間の長さを保つ直しを繰り返す。
// ひもの長さは両端の最短の距離（たるませない）。手元を動かすと間の点が慣性で遅れてついてきて曲がり、止めると揺れが収まってまっすぐに戻る。
import type { Point } from './pipeModel.ts';

/** ひもの点（両端を含む）と、1歩前の位置 */
export interface Rope { pts: Point[]; prev: Point[] }

/** 小さな歩の長さ（秒）。渡された刻みを、この長さの歩に分けて進める */
const SUB = 1 / 120;
/** 1回に進める刻みの上限（秒）。重い描画で刻みが飛んでも、ひもが暴れないように */
const MAX_DT = 1 / 30;
/** 1つの小さな歩での、速さの残り方（1 に近いほど長く揺れる） */
const DAMP = 0.93;
/** 長さを保つ直しの、1つの小さな歩での回数と強さ（弱いほど、手元に遅れてついてくる） */
const ITER = 2;
const STIFF = 0.5;
/** となりの点の真ん中へ寄せる強さ（曲がりを戻して、まっすぐな線に落ち着かせる） */
const SMOOTH = 0.12;

const copy = (ps: readonly Point[]): Point[] => ps.map((p) => ({ x: p.x, y: p.y }));

/** 両端を結ぶ線分を等しく分けた、止まった形（引き始めと、動きを減らす設定のとき） */
export function restRope(a: Point, b: Point, n: number): Rope {
  const k = Math.max(2, Math.floor(n));
  const pts = Array.from({ length: k }, (_, i) => ({ x: a.x + ((b.x - a.x) * i) / (k - 1), y: a.y + ((b.y - a.y) * i) / (k - 1) }));
  return { pts, prev: copy(pts) };
}

/** ひもを dt 秒進めた新しい形を返す（渡した形は書き換えない）。両端はいつも a・b に置く。dt が 0 以下なら途中の点は動かさない */
export function stepRope(r: Rope, a: Point, b: Point, dt: number): Rope {
  const n = r.pts.length;
  const pts = copy(r.pts), prev = copy(r.prev.length === n ? r.prev : r.pts);
  const pin = (): void => { pts[0] = { x: a.x, y: a.y }; pts[n - 1] = { x: b.x, y: b.y }; };
  if (n < 2 || !(dt > 0) || !Number.isFinite(dt)) {
    if (n >= 2) pin();
    return { pts, prev };
  }
  const steps = Math.max(1, Math.round(Math.min(dt, MAX_DT) / SUB));
  const L = Math.hypot(b.x - a.x, b.y - a.y) / (n - 1);
  for (let s = 0; s < steps; s++) {
    // 慣性：前の歩からの動きを、減らしながら続ける
    for (let i = 1; i < n - 1; i++) {
      const p = pts[i]!, q = prev[i]!;
      const vx = (p.x - q.x) * DAMP, vy = (p.y - q.y) * DAMP;
      prev[i] = { x: p.x, y: p.y };
      pts[i] = { x: p.x + vx, y: p.y + vy };
    }
    prev[0] = pts[0]!;
    prev[n - 1] = pts[n - 1]!;
    pin();
    // 長さを保つ直し（両端は動かさない）
    for (let it = 0; it < ITER; it++) {
      for (let i = 0; i < n - 1; i++) {
        const p = pts[i]!, q = pts[i + 1]!, dx = q.x - p.x, dy = q.y - p.y, len = Math.hypot(dx, dy);
        if (len < 1e-9) continue;
        const k = ((len - L) / len) * STIFF, fixP = i === 0, fixQ = i + 1 === n - 1;
        if (fixP && fixQ) continue;
        const wp = fixP ? 0 : fixQ ? 1 : 0.5, wq = 1 - wp;
        pts[i] = { x: p.x + dx * k * wp, y: p.y + dy * k * wp };
        pts[i + 1] = { x: q.x - dx * k * wq, y: q.y - dy * k * wq };
      }
    }
    // 曲がりを戻す：となりの点の真ん中へ少し寄せる
    const before = copy(pts);
    for (let i = 1; i < n - 1; i++) {
      const m = { x: (before[i - 1]!.x + before[i + 1]!.x) / 2, y: (before[i - 1]!.y + before[i + 1]!.y) / 2 };
      pts[i] = { x: pts[i]!.x + (m.x - pts[i]!.x) * SMOOTH, y: pts[i]!.y + (m.y - pts[i]!.y) * SMOOTH };
    }
    pin();
  }
  return { pts, prev };
}

/** 2つの形のあいだで、どの点の動きも eps 未満なら true（静止した） */
export function ropeSettled(a: Rope, b: Rope, eps = 0.05): boolean {
  if (a.pts.length !== b.pts.length) return false;
  return a.pts.every((p, i) => Math.hypot(p.x - b.pts[i]!.x, p.y - b.pts[i]!.y) < eps);
}
