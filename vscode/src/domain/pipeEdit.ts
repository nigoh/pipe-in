// 作業台の編集：複製・コピー・貼り付け・まとめて消す・枠に入れる/出す・つなぎをすべて外す・囲んで選ぶ。純粋な関数だけ。
// 枠に入っているかは位置で決まる（段の中心が枠の中）ので、枠に入れる・出すは段を動かすことで行う。
import { blockSize, frameOf, freeSpot, membersOf } from './pipeModel.ts';
import type { FrameModel, PipeModel, Point, Rect, StageModel } from './pipeModel.ts';

/** 写したもの（モデルとは切り離した写し） */
export interface Clip { stages: StageModel[]; frames: FrameModel[] }
export interface EditResult { changed: boolean; message: string }

const snap = (v: number): number => Math.round(v / 10) * 10;
const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;
const stageOf = (m: PipeModel, id: string): StageModel | undefined => m.stages.find((s) => s.id === id);
const frameById = (m: PipeModel, id: string): FrameModel | undefined => m.frames.find((f) => f.id === id);

/** ids の段・枠を写す。枠を写すときは中の段も一緒に写す */
export function copyItems(m: PipeModel, ids: readonly string[]): Clip {
  const frames = m.frames.filter((f) => ids.includes(f.id));
  const kids = new Set(frames.flatMap((f) => membersOf(m, f).map((s) => s.id)));
  const stages = m.stages.filter((s) => ids.includes(s.id) || kids.has(s.id));
  return clone({ stages, frames });
}

/** 重ならない名前：base が使われていれば base-2, base-3 … */
function uniqueName(base: string, taken: Set<string>): string {
  const root = base.replace(/-\d+$/, '');
  if (!taken.has(base)) return base;
  let n = 2;
  while (taken.has(`${root}-${n}`)) n++;
  return `${root}-${n}`;
}

/**
 * 写したものを offset だけずらして貼る。id は newId で新しくし、name・成果物・枠の名前は重ならないよう番号をつける。
 * 写したもの同士のつながりは貼った先どうしにつけ替え、外へのつながり（終わりも含む）は外す。貼った id を返す。
 */
export function pasteClip(m: PipeModel, clip: Clip, offset: Point, newId: (prefix: string) => string): string[] {
  const c = clone(clip);
  const map = new Map<string, string>();
  c.stages.forEach((s) => map.set(s.id, newId('s')));
  c.frames.forEach((f) => map.set(f.id, newId('f')));
  const to = (id: string | null): string | null => (id !== null && map.has(id) ? map.get(id)! : null);
  const names = new Set(m.stages.map((s) => s.name)), outputs = new Set(m.stages.map((s) => s.output)), groups = new Set(m.frames.map((f) => f.name));
  const added: string[] = [];
  for (const s of c.stages) {
    const old = s.name;
    s.id = map.get(s.id)!;
    s.name = uniqueName(old, names);
    names.add(s.name);
    if (outputs.has(s.output)) {
      const stems = new Set([...outputs].map((o) => o.replace(/\.md$/, '')));
      s.output = `${uniqueName(s.name, stems)}.md`;
    }
    outputs.add(s.output);
    s.next = to(s.next);
    s.onFail = to(s.onFail);
    s.routes = s.routes.filter((r) => map.has(r.to)).map((r) => ({ ...r, to: map.get(r.to)! }));
    s.x = snap(s.x + offset.x);
    s.y = snap(s.y + offset.y);
    m.stages.push(s);
    added.push(s.id);
  }
  for (const f of c.frames) {
    f.id = map.get(f.id)!;
    f.name = uniqueName(f.name, groups);
    groups.add(f.name);
    f.next = to(f.next);
    f.x = snap(f.x + offset.x);
    f.y = snap(f.y + offset.y);
    m.frames.push(f);
    added.push(f.id);
  }
  return added;
}

/** 段・枠を消し、消したものへのつながりをすべて外す（枠だけを消したときは、中の段は残る） */
export function deleteItems(m: PipeModel, ids: readonly string[]): { stages: number; frames: number } {
  const gone = new Set(ids);
  const before = { stages: m.stages.length, frames: m.frames.length };
  m.stages = m.stages.filter((s) => !gone.has(s.id));
  m.frames = m.frames.filter((f) => !gone.has(f.id));
  for (const s of m.stages) {
    if (s.next !== null && gone.has(s.next)) s.next = null;
    if (s.onFail !== null && gone.has(s.onFail)) s.onFail = null;
    s.routes = s.routes.filter((r) => !gone.has(r.to));
  }
  for (const f of m.frames) if (f.next !== null && gone.has(f.next)) f.next = null;
  return { stages: before.stages - m.stages.length, frames: before.frames - m.frames.length };
}

/** 段に入ってくるつなぎ（ほかの段の next・分岐・差し戻し、枠の next）があるか */
function hasIncoming(m: PipeModel, id: string): boolean {
  return m.stages.some((s) => s.id !== id && (s.next === id || s.onFail === id || s.routes.some((r) => r.to === id))) || m.frames.some((f) => f.next === id);
}

/** どことも、つながっていない段か（枠の外にあり、出るつなぎも入るつなぎも無い） */
export function isLoose(m: PipeModel, id: string): boolean {
  const s = stageOf(m, id);
  if (!s || frameOf(m, s)) return false;
  return s.next === null && s.onFail === null && s.routes.length === 0 && !hasIncoming(m, id);
}

/** 段に出入りするつなぎがあるか（ケーブルをすべて抜く、を使えるか） */
export function hasLinks(m: PipeModel, id: string): boolean {
  const s = stageOf(m, id);
  if (!s) return false;
  return s.next !== null || s.onFail !== null || s.routes.length > 0 || hasIncoming(m, id);
}

/** 段に出入りするつなぎを、すべて外す（差し戻しを外しても判定は残し、その段をやり直すにする。判定を切るのはスイッチだけ） */
export function unplugAll(m: PipeModel, id: string): boolean {
  const s = stageOf(m, id);
  if (!s || !hasLinks(m, id)) return false;
  s.next = null;
  s.routes = [];
  s.onFail = null;
  for (const x of m.stages) {
    if (x === s) continue;
    if (x.next === id) x.next = null;
    if (x.onFail === id) x.onFail = null;
    x.routes = x.routes.filter((r) => r.to !== id);
  }
  for (const f of m.frames) if (f.next === id) f.next = null;
  return true;
}

/** 枠に入れられない理由（入れられるなら null） */
export function frameInBlocker(s: StageModel): string | null {
  if (s.routes.length) return '分岐を持つ段は、並列の枠に入れられません';
  if (s.review) return '人の確認がある段は、並列の枠に入れられません';
  return null;
}

/** 段を枠の中（中の段のさらに下）へ動かす。入りきらなければ枠を広げる。next と差し戻しは外す */
export function putInFrame(m: PipeModel, ids: readonly string[], frameId: string): EditResult {
  const f = frameById(m, frameId);
  if (!f) return { changed: false, message: '枠が見つかりません' };
  const stages = ids.map((id) => stageOf(m, id)).filter((s): s is StageModel => !!s);
  if (!stages.length) return { changed: false, message: '枠に入れる段がありません' };
  for (const s of stages) {
    const why = frameInBlocker(s);
    if (why) return { changed: false, message: `${s.label}：${why}` };
  }
  let cut = false;
  for (const s of stages) {
    const z = blockSize(s.kind);
    const inside = membersOf(m, f).filter((x) => x !== s);
    const y = inside.length ? Math.max(...inside.map((x) => x.y + blockSize(x.kind).h)) + 30 : f.y + 40;
    if (f.w < z.w + 40) f.w = snap(z.w + 40);
    s.x = snap(f.x + (f.w - z.w) / 2);
    s.y = snap(y);
    if (s.y + z.h + 30 > f.y + f.h) f.h = snap(s.y + z.h + 30 - f.y + 5);
    if (s.next !== null || s.onFail !== null) cut = true;
    s.next = null;
    s.onFail = null;
  }
  const names = stages.map((s) => `「${s.label}」`).join('');
  return { changed: true, message: `${names}を並列の枠「${f.name}」に入れました${cut ? '（枠の中の段は次の段・差し戻しを持てないので、外しました）' : ''}` };
}

/** 段を枠の外（枠の右の空いた場所）へ出す */
export function takeOutOfFrame(m: PipeModel, id: string): EditResult {
  const s = stageOf(m, id), f = s ? frameOf(m, s) : null;
  if (!s || !f) return { changed: false, message: '枠の中の段ではありません' };
  const z = blockSize(s.kind);
  const p = freeSpot(m, z, { x: f.x + f.w + 60 + z.w / 2, y: s.y + z.h / 2 });
  s.x = p.x;
  s.y = p.y;
  return { changed: true, message: `「${s.label}」を並列の枠「${f.name}」から出しました` };
}

const norm = (r: Rect): Rect => ({ x: Math.min(r.x, r.x + r.w), y: Math.min(r.y, r.y + r.h), w: Math.abs(r.w), h: Math.abs(r.h) });
const inside = (a: Rect, r: Rect): boolean => a.x >= r.x && a.y >= r.y && a.x + a.w <= r.x + r.w && a.y + a.h <= r.y + r.h;

/** 囲んだ四角にまるごと入る段と枠の id（段が先、それぞれモデルの順） */
export function itemsInRect(m: PipeModel, rect: Rect): string[] {
  const r = norm(rect);
  return [
    ...m.stages.filter((s) => inside({ x: s.x, y: s.y, ...blockSize(s.kind) }, r)).map((s) => s.id),
    ...m.frames.filter((f) => inside(f, r)).map((f) => f.id),
  ];
}

/**
 * n 回目に貼るときのずらし方。段だけなら少しずつ（40 ずつ）ずらす。
 * 枠を含むときは、写したものの高さ＋60 ずつ下へずらす（枠どうしが重なると、写した段の中心が元の枠に入り、元の枠の段になってしまうため）。
 */
export function pasteOffset(clip: Clip, n: number): Point {
  if (!clip.frames.length) return { x: 40 * n, y: 40 * n };
  const tops = [...clip.frames.map((f) => f.y), ...clip.stages.map((s) => s.y)];
  const bottoms = [...clip.frames.map((f) => f.y + f.h), ...clip.stages.map((s) => s.y + blockSize(s.kind).h)];
  return { x: 0, y: snap(Math.max(...bottoms) - Math.min(...tops) + 60) * n };
}
