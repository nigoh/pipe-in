// 右クリックのメニュー：押したもの（ブロック・枠・何もないところ・複数選択）で項目を決め、使えない項目には理由を添える。
// キー操作（↑↓・→←・Enter・Esc）と、面からはみ出さない置き場所も、ここで決める。純粋な関数だけ。
import { BLOCK_KINDS, KIND_LABEL, frameOf } from './pipeModel.ts';
import type { PipeModel, Point } from './pipeModel.ts';
import { frameInBlocker, hasLinks } from './pipeEdit.ts';

export type MenuTarget =
  | { type: 'stage'; id: string }
  | { type: 'frame'; id: string }
  | { type: 'canvas'; at: Point }
  | { type: 'multi'; ids: string[] }
  | { type: 'wire' };
export interface MenuContext {
  /** 写したもの（貼り付けられるもの）があるか */
  hasClip: boolean;
  /** 保存済みの段の name（指示文のファイルがあるもの） */
  savedNames: readonly string[];
}
export interface MenuItem {
  id: string;
  label: string;
  /** 使えないときの理由（使えるなら無し） */
  disabled?: string;
  children?: MenuItem[];
  sep?: boolean;
}

const SEP: MenuItem = { id: '-', label: '', sep: true };
const it = (id: string, label: string, disabled?: string | null, children?: MenuItem[]): MenuItem => ({
  id, label, ...(disabled ? { disabled } : {}), ...(children ? { children } : {}),
});

/** 枠に入れる ▸（枠ごとのサブメニュー）。入れられないときは理由をつける */
function frameIn(m: PipeModel, ids: readonly string[]): MenuItem {
  const stages = m.stages.filter((s) => ids.includes(s.id));
  const children = m.frames.map((f) => it(`frame-in:${f.id}`, `並列の枠「${f.name}」`));
  let why: string | null = null;
  if (!m.frames.length) why = 'まだ並列の枠がありません（棚か、何もないところの右クリックで作れます）';
  else if (!stages.length) why = '枠に入れられる段を選んでいません';
  else for (const s of stages) { why = frameInBlocker(s); if (why) break; }
  return it('frame-in', '枠に入れる', why, children);
}

export function menuFor(m: PipeModel, target: MenuTarget, ctx: MenuContext): MenuItem[] {
  if (target.type === 'stage') {
    const s = m.stages.find((x) => x.id === target.id);
    if (!s) return [];
    const inFrame = frameOf(m, s) !== null;
    return [
      it('rename', '名前を変える'),
      it('open-prompt', '指示文を開く', ctx.savedNames.includes(s.name) ? null : 'まだ保存していない段です（保存すると開けます）'),
      it('show-prompt', '渡される指示を見る'),
      SEP,
      it('duplicate', '複製する'),
      it('review', s.review ? '人の確認を外す' : '人の確認をつける', inFrame ? '並列の枠の中の段は、人の確認を持てません' : null),
      inFrame ? it('frame-out', '枠から出す') : frameIn(m, [s.id]),
      it('unplug-all', 'ケーブルをすべて抜く', hasLinks(m, s.id) ? null : 'つながっているケーブルがありません'),
      SEP,
      it('delete', '消す'),
    ];
  }
  if (target.type === 'frame') {
    return [it('rename-frame', '名前を変える'), SEP, it('delete-frame', '枠だけ消す（中の段は残す）'), it('delete-frame-all', '中の段ごと消す')];
  }
  if (target.type === 'canvas') {
    return [
      it('add', 'ここに段を足す', null, BLOCK_KINDS.map((k) => it(`add:${k}`, KIND_LABEL[k]))),
      it('add-frame', 'ここに並列の枠を作る'),
      it('paste', '貼り付け', ctx.hasClip ? null : '写したものがありません（Ctrl+C で写せます）'),
      SEP,
      it('arrange', '自動で並べる'),
      it('fit', '全体を見る'),
    ];
  }
  if (target.type === 'multi') {
    const n = target.ids.length;
    return [it('duplicate', `${n} 個を複製する`), frameIn(m, target.ids), SEP, it('delete', `${n} 個を消す`)];
  }
  return [];
}

/** メニューの中の位置。[上の段の番号] か [上の段の番号, サブメニューの番号] */
export type MenuPath = number[];
export interface MenuKeyResult { path: MenuPath; run?: string; close?: boolean }

const levelOf = (items: MenuItem[], path: MenuPath): MenuItem[] => (path.length > 1 ? items[path[0]!]?.children ?? [] : items);

function step(list: MenuItem[], i: number, d: 1 | -1): number {
  for (let k = 1; k <= list.length; k++) {
    const j = (i + d * k + list.length * k) % list.length;
    if (!list[j]!.sep) return j;
  }
  return i;
}

/** キーを押したあとの位置と、実行する項目（run）・閉じるか（close） */
export function menuKey(items: MenuItem[], path: MenuPath, key: string): MenuKeyResult {
  const list = levelOf(items, path), i = path[path.length - 1]!, cur = list[i];
  const up = path.slice(0, -1);
  switch (key) {
    case 'ArrowDown': return { path: [...up, step(list, i, 1)] };
    case 'ArrowUp': return { path: [...up, step(list, i, -1)] };
    case 'ArrowRight':
      return cur?.children?.length && !cur.disabled ? { path: [...path, 0] } : { path };
    case 'ArrowLeft': return { path: path.length > 1 ? up : path };
    case 'Escape': return path.length > 1 ? { path: up } : { path, close: true };
    case 'Enter':
    case ' ':
      if (!cur || cur.disabled || cur.sep) return { path };
      if (cur.children?.length) return { path: [...path, 0] };
      return { path, run: cur.id };
    default: return { path };
  }
}

/** メニューの左上：右端・下端では、押した点の左・上へ折り返して面の中に収める */
export function placeMenu(at: Point, size: { w: number; h: number }, box: { w: number; h: number }): Point {
  const x = at.x + size.w > box.w ? at.x - size.w : at.x;
  const y = at.y + size.h > box.h ? at.y - size.h : at.y;
  return { x: Math.max(0, Math.min(x, box.w - size.w)), y: Math.max(0, Math.min(y, box.h - size.h)) };
}
