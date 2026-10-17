// パイプ作業台のパネルの中で動くスクリプト（esbuild で out/pipeEditor.js に束ねる）。
// ブロックを置く・動かす・プラグをコンセントに差してつなぐ・ブロック（1回分の依頼）を組み立てる・検査・書き出しの下見。
// 右クリックのメニュー・元に戻す/やり直し・履歴・複数選択・コピー/貼り付け・ケーブルに落として間に挟む。
// 判断（並び・つなぎ・検査・書き出し・ケーブルの通り道・メニューの項目・編集・履歴）は domain の関数に任せ、ここは画面の出し入れだけ。
// vscode は import しない（acquireVsCodeApi でやり取りする）。外から来た文字は esc を通す。
import {
  BLOCK_KINDS,
  END,
  KIND_LABEL,
  TERMINAL_SIZE,
  autoLayout,
  blockSize,
  frameOf,
  freeSpot,
  membersOf,
  newStage,
  orderStages,
  pipeFiles,
  promptFileText,
  validatePipe,
} from '../domain/pipeModel.ts';
import type { BlockKind, FrameModel, PipeModel, Point, StageModel } from '../domain/pipeModel.ts';
import { blockRect, cablePath, emptySockets, layoutWires, nearestWire, smoothPath } from '../domain/pipeWires.ts';
import { dropTarget as blockAt } from '../domain/pipeDrop.ts';
import { restRope, ropeSettled, stepRope } from '../domain/cableRope.ts';
import type { Rope } from '../domain/cableRope.ts';
import type { Wire } from '../domain/pipeWires.ts';
import { insertBetween, replug, unplug } from '../domain/pipeLinks.ts';
import { copyItems, deleteItems, isLoose, itemsInRect, pasteClip, pasteOffset, putInFrame, takeOutOfFrame, unplugAll } from '../domain/pipeEdit.ts';
import type { Clip } from '../domain/pipeEdit.ts';
import { setCheck } from '../domain/pipeCheck.ts';
import { checkBoxHtml, checkChipHtml } from '../view/checkHtml.ts';
import { menuFor, menuKey, placeMenu } from '../domain/pipeMenu.ts';
import type { MenuItem, MenuPath, MenuTarget } from '../domain/pipeMenu.ts';
import { createHistory, jump, record, redo, undo } from '../domain/editHistory.ts';
import type { History } from '../domain/editHistory.ts';
import { VERSION_LIMIT } from '../domain/pipeVersions.ts';
import type { VersionEntry } from '../domain/pipeVersions.ts';
import { plugSvg, socketSvg } from '../view/plugSvg.ts';

declare function acquireVsCodeApi(): { postMessage(message: unknown): void };
const vscode = acquireVsCodeApi();

// ---- 形とアイコン ----------------------------------------------------------------

type ShapeName = 'process' | 'predefined' | 'document' | 'subroutine' | 'chamfer' | 'hexagon' | 'diamond' | 'parallelogram' | 'terminal';
const SHAPE_OF: Record<BlockKind, ShapeName> = {
  research: 'process', agent: 'predefined', docs: 'document', tests: 'subroutine', code: 'chamfer', verify: 'hexagon', branch: 'diamond', outside: 'parallelogram',
};
const KIND_HINT: Record<BlockKind, string> = {
  research: '読んでまとめる', agent: 'サブエージェントを使う', docs: '文書や図を書く', tests: 'テストを書く', code: '製品コードを書く',
  verify: '判定して戻す', branch: '行き先を選ぶ', outside: 'Web・MCP を使う',
};
const INSET: Record<ShapeName, [number, number, number, number]> = {
  process: [8, 12, 8, 14], predefined: [9, 16, 9, 18], document: [8, 12, 22, 14], subroutine: [8, 20, 8, 22], chamfer: [8, 16, 8, 18],
  hexagon: [8, 26, 8, 28], diamond: [26, 40, 26, 40], parallelogram: [8, 26, 8, 30], terminal: [6, 14, 6, 14],
};
function shapePath(shape: ShapeName, w: number, h: number): { outer: string; inner?: string } {
  switch (shape) {
    case 'predefined': return { outer: `M0 0H${w}V${h}H0Z`, inner: `M6 6H${w - 6}V${h - 6}H6Z` };
    case 'document': return { outer: `M0 0H${w}V${h - 12}Q${w * 0.75} ${h - 26} ${w / 2} ${h - 12}T0 ${h - 12}Z` };
    case 'subroutine': return { outer: `M0 0H${w}V${h}H0Z`, inner: `M10 0V${h}M${w - 10} 0V${h}` };
    case 'chamfer': return { outer: `M14 0H${w - 14}L${w} 14V${h - 14}L${w - 14} ${h}H14L0 ${h - 14}V14Z` };
    case 'hexagon': return { outer: `M22 0H${w - 22}L${w} ${h / 2}L${w - 22} ${h}H22L0 ${h / 2}Z` };
    case 'diamond': return { outer: `M${w / 2} 0L${w} ${h / 2}L${w / 2} ${h}L0 ${h / 2}Z` };
    case 'parallelogram': return { outer: `M20 0H${w}L${w - 20} ${h}H0Z` };
    case 'terminal': return { outer: `M${h / 2} 0H${w - h / 2}A${h / 2} ${h / 2} 0 0 1 ${w - h / 2} ${h}H${h / 2}A${h / 2} ${h / 2} 0 0 1 ${h / 2} 0Z` };
    default: return { outer: `M6 0H${w - 6}Q${w} 0 ${w} 6V${h - 6}Q${w} ${h} ${w - 6} ${h}H6Q0 ${h} 0 ${h - 6}V6Q0 0 6 0Z` };
  }
}
function shapeSvg(shape: ShapeName, w: number, h: number, cls = 'shape'): string {
  const p = shapePath(shape, w, h);
  return `<svg class="${cls}" viewBox="-2 -2 ${w + 4} ${h + 4}" width="${w}" height="${h}" preserveAspectRatio="none"><path class="sh" d="${p.outer}"/>${p.inner ? `<path class="sh2" d="${p.inner}"/>` : ''}</svg>`;
}
const ICON: Record<BlockKind | 'frame', string> = {
  research: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5.5 5.5"/></svg>',
  agent: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="8" cy="8" r="3"/><circle cx="16.5" cy="9.5" r="2.4"/><path d="M3 19c0-3 2.3-5 5-5s5 2 5 5M13.5 18c.3-2.2 1.6-3.6 3.3-3.6 1.9 0 3.2 1.5 3.2 3.6"/></svg>',
  docs: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M6 3h9l4 4v14H6z"/><path d="M9 11h7M9 15h7M9 19h4"/></svg>',
  tests: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 12.5l3 3 5-6"/></svg>',
  code: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M8.5 7L3.5 12l5 5M15.5 7l5 5-5 5"/></svg>',
  verify: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 3l7 3v5c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/></svg>',
  branch: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><circle cx="6" cy="6" r="2.3"/><circle cx="18" cy="6" r="2.3"/><circle cx="12" cy="19" r="2.3"/><path d="M12 16.7V13L6 8.3M12 13l6-4.7"/></svg>',
  outside: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.6 2.6 3.6 5.6 3.6 8.5s-1 5.9-3.6 8.5c-2.6-2.6-3.6-5.6-3.6-8.5s1-5.9 3.6-8.5z"/></svg>',
  frame: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><rect x="3" y="4" width="18" height="16" rx="5"/><path d="M8 9.5h8M8 14.5h8"/></svg>',
};
const PLUG = '<svg viewBox="0 0 30 22" aria-hidden="true"><rect class="pb" x="1" y="3" width="17" height="16" rx="4"/><rect class="pp" x="18" y="6" width="10" height="3"/><rect class="pp" x="18" y="13" width="10" height="3"/></svg>';
const THINKING: [string, string][] = [['', '既定'], ['4000', '少なめ（4,000）'], ['16000', '多め（16,000）'], ['32000', '最大（32,000）']];

// ---- 状態 ------------------------------------------------------------------

type Selection = { type: 'stage'; id: string } | { type: 'frame'; id: string } | { type: 'edge'; wire: Wire } | { type: 'pipe' };
const st: {
  m: PipeModel | null; sel: Selection; view: { x: number; y: number; z: number }; tab: 'block' | 'check' | 'files' | 'history'; dirty: boolean; viewMoved: boolean;
  /** 抜いて手に持っているケーブル（wireKey）。そのケーブルは描かず、コンセントは空きにする */
  lifted: string | null;
  /** 差したばかりのケーブル（元と先）。次に描くとき、プラグを押し込む動きを付ける */
  snapped: { from: string; to: string } | null;
  /** 選んでいる段・枠の id（2つ以上なら複数選択） */
  picked: string[];
  /** 写したもの（Ctrl+C）と、それを貼った回数（貼るたびに少しずつずらす） */
  clip: Clip | null;
  pasted: number;
  /** 保存済みの段の name（指示文を開けるもの） */
  savedNames: string[];
  versions: VersionEntry[];
  /** 間に挟む先として目立たせているケーブル（wireKey） */
  dropWire: string | null;
  /** 保存先のフォルダ名（拡張が知らせてくる。見せるだけ） */
  folder: string;
} = {
  m: null, sel: { type: 'pipe' }, view: { x: 30, y: 30, z: 0.8 }, tab: 'block', dirty: false, viewMoved: false, lifted: null, snapped: null,
  picked: [], clip: null, pasted: 0, savedNames: [], versions: [], dropWire: null, folder: '',
};
const $ = (id: string): HTMLElement => document.getElementById(id) as HTMLElement;
const esc = (t: unknown): string => String(t ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);
const model = (): PipeModel => st.m as PipeModel;
const stageById = (id: string): StageModel | undefined => model().stages.find((s) => s.id === id);
const frameById = (id: string): FrameModel | undefined => model().frames.find((f) => f.id === id);
const isTerm = (id: string): boolean => id === 'start' || id === END;
const toast = (t: string): void => { $('toast').textContent = t; };
let uid = 0;
const nid = (p: string): string => `${p}${Date.now().toString(36)}${++uid}`;

// ---- 元に戻す・やり直し・保存していない印 ----------------------------------------------

let hist: History = createHistory('');
/** 保存したとき（開いたとき）の形。今の形と違えば、保存していない変更がある */
let savedSnap = '';
/** 保存を押したときの形（保存できたら savedSnap にする） */
let savingSnap = '';
let stateTimer: ReturnType<typeof setTimeout> | undefined;
const snapNow = (): string => JSON.stringify(st.m);

/** 保存していない印を付け直し、拡張に知らせる（タブ名の ● と、閉じたときの下書きのため。続けて打つ間は 300ms まとめる） */
function syncDirty(): void {
  const dirty = st.m !== null && snapNow() !== savedSnap;
  st.dirty = dirty;
  ($('save') as HTMLButtonElement).textContent = dirty ? '保存 ●' : '保存';
  if (stateTimer !== undefined) clearTimeout(stateTimer);
  stateTimer = setTimeout(() => vscode.postMessage(dirty ? { type: 'state', dirty, model: st.m } : { type: 'state', dirty }), 300);
}

/** 1手として積む。label は履歴の一覧に出す文。key が同じ手が続けば（同じ欄に続けて打つなど）1手にまとめる */
function changed(label: string, key?: string): void {
  if (!st.m) return;
  record(hist, label, snapNow(), key);
  syncDirty();
  if (st.tab === 'history') renderPane();
}

/** 写しの形に戻す（元に戻す・やり直し・履歴の時点）。選んでいたものが無くなっていれば外す */
function restore(snap: string | null): void {
  if (snap === null) return;
  st.m = JSON.parse(snap) as PipeModel;
  const m = model(), has = (id: string): boolean => m.stages.some((s) => s.id === id) || m.frames.some((f) => f.id === id);
  if ((st.sel.type === 'stage' || st.sel.type === 'frame') && !has(st.sel.id)) st.sel = { type: 'pipe' };
  if (st.sel.type === 'edge') st.sel = { type: 'pipe' };
  st.picked = st.picked.filter(has);
  syncDirty();
  render();
}
const picks = (): string[] => (st.picked.length ? st.picked : st.sel.type === 'stage' || st.sel.type === 'frame' ? [st.sel.id] : []);
const isPicked = (id: string): boolean => st.picked.includes(id) || ((st.sel.type === 'stage' || st.sel.type === 'frame') && st.sel.id === id);
/** 1つだけ選ぶ（複数選択はやめる） */
function selectOne(sel: Selection): void {
  st.sel = sel;
  st.picked = sel.type === 'stage' || sel.type === 'frame' ? [sel.id] : [];
  if (sel.type !== 'pipe') st.tab = st.tab === 'history' ? 'history' : 'block';
}

// ---- 路線図 ------------------------------------------------------------------

function chips(s: StageModel): string {
  const c = [`<span class="chip">${s.access}</span>`];
  if (s.review) c.push('<span class="chip">人の確認</span>');
  const judge = checkChipHtml(model(), s);
  if (judge) c.push(judge);
  if (s.routes.length) c.push(`<span class="chip rt">分岐${s.routes.length}</span>`);
  if (s.web !== 'off') c.push('<span class="chip warn">web</span>');
  if (s.bash) c.push('<span class="chip warn">bash</span>');
  const sdk: string[] = [];
  if (s.permissionMode) sdk.push(s.permissionMode === 'plan' ? 'plan' : 'edits');
  if (s.thinking) sdk.push('think');
  if (s.agents.length) sdk.push(`agents ${s.agents.length}`);
  if (s.mcpServers.length || s.mcp.length) sdk.push('mcp');
  if (s.fallbackModel) sdk.push('fallback');
  if (s.addDirs.length) sdk.push('dirs');
  if (s.systemAppend.trim()) sdk.push('rules');
  return c.join('') + sdk.map((t) => `<span class="chip sdk">${t}</span>`).join('');
}

function stageHtml(s: StageModel, n: number): string {
  const m = model(), shape = SHAPE_OF[s.kind], z = blockSize(s.kind);
  const inFrame = frameOf(m, s) !== null;
  const cls = [shape, isPicked(s.id) ? 'sel' : '', inFrame ? 'in-frame' : '', !inFrame && !s.next && !s.routes.length ? 'free' : ''].join(' ');
  return `<div class="node ${cls}" data-id="${esc(s.id)}" tabindex="0" role="button" aria-label="${esc(s.label)}（${KIND_LABEL[s.kind]}）">
    ${shapeSvg(shape, z.w, z.h)}
    <div class="body">
      <span class="ico k-${s.kind}">${ICON[s.kind]}</span>
      <div class="head"><span class="no">${String(n).padStart(2, '0')}</span><span class="nm">${esc(s.name)}</span></div>
      <span class="lb">${esc(s.label)}</span>
      <div class="chips">${chips(s)}</div>
    </div>
    ${inFrame ? '' : `<span class="port" data-port="${esc(s.id)}" title="引っぱって、ほかのブロックのコンセントに差す">${PLUG}</span>`}</div>`;
}

function termHtml(id: 'start' | 'end'): string {
  const m = model(), { w, h } = TERMINAL_SIZE;
  const sub = id === 'start' ? (m.input === 'none' ? '依頼メモなし' : '00_input.md') : 'end';
  return `<div class="node term" data-id="${id}">${shapeSvg('terminal', w, h)}
    <div class="body"><span class="lb">${id === 'start' ? '始まり' : '終わり'}</span><span class="nm">${sub}</span></div></div>`;
}

function renderWorld(): void {
  const m = model(), ord = orderStages(m);
  let html = '';
  for (const f of m.frames) {
    const sel = isPicked(f.id) ? ' sel' : '';
    html += `<div class="frame${sel}${f.next ? '' : ' free'}" data-id="${esc(f.id)}">
      <span class="ftab" data-drag="frame">並列 · ${esc(f.name)}</span><span class="resize" data-drag="resize" aria-label="大きさを変える"></span>
      <span class="port" data-port="${esc(f.id)}" title="引っぱって、枠のあとの段のコンセントに差す">${PLUG}</span></div>`;
  }
  m.stages.forEach((s) => { html += stageHtml(s, ord.indexOf(s) + 1); });
  html += termHtml('start') + termHtml('end');
  html += '<svg class="wires" id="wires" width="1" height="1"></svg>';
  $('world').innerHTML = html;
  place();
  drawWires();
  applyView();
}

/** 位置・大きさ・中の余白は、描いたあとに CSSOM で入れる（パネルの CSP は HTML に書いたインラインの style 属性を捨てるため） */
function place(): void {
  const m = model(), px = (v: number): string => `${v}px`;
  document.querySelectorAll<HTMLElement>('#world > [data-id]').forEach((el) => {
    const id = el.dataset.id!, r = blockRect(m, id);
    Object.assign(el.style, { left: px(r.x), top: px(r.y), width: px(r.w), height: px(r.h) });
    const s = stageById(id), body = el.querySelector<HTMLElement>(':scope > .body');
    if (s && body) {
      const [t, rt, b, l] = INSET[SHAPE_OF[s.kind]];
      Object.assign(body.style, { top: px(t), right: px(rt), bottom: px(b), left: px(l) });
    }
  });
}

const angleOf = (pts: Point[]): number => {
  const a = pts[pts.length - 2]!, b = pts[pts.length - 1]!;
  return (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI;
};
function backOff(pts: Point[], d: number): Point[] {
  const out = pts.map((p) => ({ ...p })), a = out[out.length - 2]!, b = out[out.length - 1]!;
  const len = Math.hypot(b.x - a.x, b.y - a.y);
  if (len > d) { b.x -= ((b.x - a.x) * d) / len; b.y -= ((b.y - a.y) * d) / len; }
  return out;
}
const wireKey = (w: Wire): string => `${w.kind}:${w.from}:${w.to}:${w.label ?? ''}`;
let wires: Wire[] = [];

function drawWires(): void {
  const svg = document.getElementById('wires');
  if (!svg) return;
  const m = model();
  // つながっていない段を引いている間は、その段をよけない（ケーブルが逃げると、間に挟めなくなるため）
  wires = layoutWires(m, act?.type === 'move' && act.loose ? { ignore: act.id } : {});
  let cables = '', hits = '', tags = '', sockets = '', plugs = '';
  wires.forEach((w, i) => {
    if (wireKey(w) === st.lifted) return;
    const sel = (st.sel.type === 'edge' && wireKey(st.sel.wire) === wireKey(w) ? ' sel' : '') + (st.dropWire === wireKey(w) ? ' drop' : '');
    // 通り道の角を大きく回る、流線型の曲線で描く
    const d = cablePath(backOff(w.points, 20));
    if (w.kind !== 'return') cables += `<path class="cable-out${st.dropWire === wireKey(w) ? ' drop' : ''}" d="${d}"/>`;
    cables += `<path class="wire ${w.kind}${sel}" d="${d}"/>`;
    if (w.kind !== 'start') {
      // 当たり判定はプラグの手前で止める（プラグは掴んで抜き差しするため）
      hits += `<path class="wire-hit" data-edge="${i}" d="${cablePath(backOff(w.points, 16))}"/>`;
      cables += `<circle class="bush" cx="${w.points[0]!.x}" cy="${w.points[0]!.y}" r="4"/>`;
    }
    const end = w.points[w.points.length - 1]!, ang = angleOf(w.points);
    sockets += socketSvg(end.x, end.y, ang, true);
    const snapped = st.snapped !== null && st.snapped.from === (w.owner ?? w.from) && st.snapped.to === w.to;
    plugs += plugSvg(end.x, end.y, ang, w.kind, 'in', { grab: w.kind === 'start' ? undefined : i, snap: snapped });
    if (w.kind === 'route' && w.label) {
      const p = w.points[0]!, wd = w.label.length * 7 + 10;
      tags += `<g class="tag" transform="translate(${p.x + 12} ${p.y - 8})"><rect width="${wd}" height="16" rx="3"/><text x="5" y="11.5">${esc(w.label)}</text></g>`;
    }
  });
  // まだ何も差さっていないコンセントも出しておく（どこに差せばいいかがわかるように）
  for (const e of emptySockets(m, wires.filter((w) => wireKey(w) !== st.lifted))) sockets += socketSvg(e.x, e.y, 0, false);
  // ケーブルの当たり判定（透明）の上にプラグを置いて、近くを通るケーブルがあってもプラグを掴めるようにする。
  // プラグのあとにコンセントを描いて、差さったプラグの刃をコンセントの中に隠す。手に持っているケーブルはいちばん上（中は drawRope が描く）
  svg.innerHTML = cables + hits + plugs + sockets + tags + '<g class="in-hand" id="in-hand"></g>';
  drawRope();
}

// ---- 手に持っているケーブル：ひもとして動かす（D0007） --------------------------------

const ROPE_N = 16;
/** 手に持っているケーブル。a は元の点、hand は手元。raf は予約している画面の更新（0 なら予約なし） */
let rope: { r: Rope; a: Point; hand: Point; last: number; raf: number } | null = null;
const reduceMotion = (): boolean => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

/** 手に持っているケーブルだけを描き直す（置いたケーブルの通り道は計算し直さない） */
function drawRope(): void {
  const g = document.getElementById('in-hand');
  if (!g) return;
  if (!rope) { g.innerHTML = ''; return; }
  const pts = rope.r.pts, d = smoothPath(backOff(pts, 20));
  // プラグの向きは、ひもの先の向き（先が縮んで向きが決まらないときは、元の点から手元への向き）
  const n = pts.length, tail = n > 2 && Math.hypot(pts[n - 1]!.x - pts[n - 2]!.x, pts[n - 1]!.y - pts[n - 2]!.y) > 0.5 ? pts : [rope.a, rope.hand];
  g.innerHTML = `<path class="cable-out" d="${d}"/><path class="wire temp" d="${d}"/>${plugSvg(rope.hand.x, rope.hand.y, angleOf(tail), 'temp', 'loose')}`;
}
function startRope(a: Point, hand: Point): void {
  stopRope();
  rope = { r: restRope(a, hand, ROPE_N), a, hand, last: 0, raf: 0 };
  drawRope();
}
/** 手元が動いた。動きを減らす設定なら、まっすぐな形をその場で描く。そうでなければ、ひもを進める予約をする */
function moveRope(hand: Point): void {
  if (!rope) return;
  rope.hand = hand;
  if (reduceMotion()) { rope.r = restRope(rope.a, hand, ROPE_N); drawRope(); return; }
  if (!rope.raf) { rope.last = 0; rope.raf = requestAnimationFrame(tickRope); }
}
function tickRope(t: number): void {
  if (!rope) return;
  const dt = rope.last ? (t - rope.last) / 1000 : 1 / 60;
  rope.last = t;
  rope.raf = 0;
  const next = stepRope(rope.r, rope.a, rope.hand, dt), still = ropeSettled(rope.r, next);
  rope.r = next;
  drawRope();
  // 揺れが収まったら予約をやめる（動いていないときに更新を回し続けない）。手元がまた動けば moveRope が予約し直す
  if (!still) rope.raf = requestAnimationFrame(tickRope);
}
function stopRope(): void {
  if (rope?.raf) cancelAnimationFrame(rope.raf);
  rope = null;
  drawRope();
}
/** 離した点・重ねている点から、差す先を決める（コンセントの上でも差さる。ゆとりは画面の 8px） */
const dropAt = (p: Point): string | null => blockAt(model(), wires, p, 8 / st.view.z);

function applyView(): void {
  $('world').style.transform = `translate(${st.view.x}px, ${st.view.y}px) scale(${st.view.z})`;
  $('zoom').textContent = `${Math.round(st.view.z * 100)}%`;
}

// ---- 右のパネル --------------------------------------------------------------

const opt = (list: [string, string][], v: string): string =>
  list.map(([a, b]) => `<option value="${esc(a)}"${a === v ? ' selected' : ''}>${esc(b)}</option>`).join('');
const current = (): StageModel | undefined => (st.sel.type === 'stage' ? stageById(st.sel.id) : undefined);

function delivered(s: StageModel): string {
  // 本体の pipe/specs.py の stage_prompt と同じ組み立て
  const m = model(), ord = orderStages(m), i = ord.indexOf(s), w = `docs/pipeline/${m.name}`, f = frameOf(m, s);
  const given = [...(m.input !== 'none' ? [`- 依頼メモ: \`${w}/00_input.md\``] : []),
    ...ord.slice(0, i).filter((x) => !f || frameOf(m, x) !== f).map((x) => `- ${x.label}の成果物: \`${w}/${x.output}\``)];
  const L = [promptFileText(s).trim(), ''];
  if (given.length) L.push('## 渡すもの', '', '先に読んでください。', '', ...given, '');
  L.push('## 書くもの', '', `成果物を \`${w}/${s.output}\` に書いてください。`);
  if (s.access === 'docs' && s.docsDir) L.push(`図や文書のファイルは \`${s.docsDir}/\` の下に置き、成果物からリンクしてください。`);
  if (s.check.on && s.check.verdict) L.push('最後に、判定（status: pass / fail・summary・problems）を構造化出力で返してください。');
  if (s.routes.length) L.push(`最後に、次に進む先を choice（${s.routes.map((r) => r.key).join(' / ')} のどれか）で返してください。`);
  if (s.systemAppend.trim()) L.push('', '（この段の決まり）', s.systemAppend.trim());
  return L.join('\n');
}

function sdkPane(s: StageModel): string {
  const open = s.permissionMode || s.thinking || s.agents.length || s.mcpServers.length || s.systemAppend || s.addDirs.length || s.fallbackModel;
  return `<details class="box"${open ? ' open' : ''}><summary>Agent SDK の設定</summary>
    <div class="row2">
      <label class="field">許可のモード permission_mode<select id="b-perm">${opt([['', '既定（default）'], ['acceptEdits', '書き込みを自動で許す'], ['plan', '計画だけ（何も変えない）']], s.permissionMode)}</select></label>
      <label class="field">考える量 max_thinking_tokens<select id="b-think">${opt(THINKING, s.thinking ? String(s.thinking) : '')}</select></label>
      <label class="field">予備のモデル fallback_model<select id="b-fallback">${opt([['', 'なし'], ['sonnet', 'sonnet'], ['haiku', 'haiku']], s.fallbackModel)}</select></label>
      <label class="field">費用の上限（USD）max_budget_usd<input type="number" id="b-budget" min="0" step="0.1" value="${s.maxBudget ?? ''}" placeholder="なし"></label>
    </div>
    <label class="field">この段の決まり system_append<textarea id="b-sysappend" rows="2" placeholder="例：日本語で、表を使って書く">${esc(s.systemAppend)}</textarea></label>
    <label class="field">追加で読めるフォルダ add_dirs（1行に1つ。プロジェクトからの相対パス）<textarea id="b-adddirs" rows="2">${esc(s.addDirs.join('\n'))}</textarea></label>
    <div class="field">サブエージェント agents
      ${s.agents.map((a, j) => `<div class="card">
        <div class="row"><label class="field">名前<input class="mono" data-agent="${j}" data-f="name" value="${esc(a.name)}"></label>
          <label class="field">使える道具（, 区切り）<input class="mono" data-agent="${j}" data-f="tools" value="${esc(a.tools.join(', '))}"></label>
          <button type="button" class="x" data-agentdel="${j}" aria-label="消す">×</button></div>
        <label class="field">いつ任せるか description<input data-agent="${j}" data-f="description" value="${esc(a.description)}"></label>
        <label class="field">サブエージェントへの指示 prompt<textarea rows="2" data-agent="${j}" data-f="prompt">${esc(a.prompt)}</textarea></label>
        <label class="field">モデル model<select data-agent="${j}" data-f="model">${opt([['', '段と同じ'], ['opus', 'opus'], ['sonnet', 'sonnet'], ['haiku', 'haiku']], a.model)}</select></label></div>`).join('')}
      <button type="button" class="btn small" id="agent-add">＋ サブエージェントを足す</button>
    </div>
    <div class="field">MCP サーバー mcp_servers
      ${s.mcpServers.map((srv, j) => `<div class="card"><div class="row">
        <label class="field">名前<input class="mono" data-mcps="${j}" data-f="name" value="${esc(srv.name)}"></label>
        <label class="field">つなぎ方<select data-mcps="${j}" data-f="type">${opt([['stdio', 'stdio（コマンド）'], ['http', 'http'], ['sse', 'sse']], srv.type)}</select></label>
        <button type="button" class="x" data-mcpsdel="${j}" aria-label="消す">×</button></div>
        ${srv.type === 'stdio'
          ? `<label class="field">起動するコマンド<input class="mono" data-mcps="${j}" data-f="command" value="${esc(srv.command)}"></label>
             <label class="field">引数（空白区切り）<input class="mono" data-mcps="${j}" data-f="args" value="${esc(srv.args.join(' '))}"></label>`
          : `<label class="field">URL<input class="mono" data-mcps="${j}" data-f="url" value="${esc(srv.url)}"></label>`}</div>`).join('')}
      <button type="button" class="btn small" id="mcps-add">＋ MCP サーバーを足す</button>
    </div>
    <label class="field">使う MCP の道具 mcp（1行に1つ。mcp__<サーバー>__<道具>）<textarea id="b-mcp" rows="2">${esc(s.mcp.join('\n'))}</textarea></label>
  </details>`;
}

function blockPane(): string {
  const m = model();
  if (st.picked.length > 1) {
    const names = st.picked.map((id) => stageById(id)?.label ?? (frameById(id) ? `並列の枠「${frameById(id)!.name}」` : '')).filter(Boolean);
    return `<p class="note">${st.picked.length} 個を選んでいます：${names.map(esc).join('、')}</p>
      <p class="note">どれかを引くと、まとめて動きます。右クリックで、まとめて複製・枠に入れる・消すができます。Shift+クリックで足したり外したりできます。</p>
      <button type="button" class="btn" id="del-sel">${st.picked.length} 個を消す</button>`;
  }
  if (st.sel.type === 'frame') {
    const f = frameById(st.sel.id)!;
    return `<div class="bhead"><svg class="mini" viewBox="0 0 64 40"><rect class="sh" x="2" y="2" width="60" height="36" rx="10"/></svg><div class="t"><input id="fr-name" class="mono" value="${esc(f.name)}" aria-label="枠の名前（group）"></div></div>
      <p class="note">枠の中に置いた段は、同時に流れます（group = "${esc(f.name)}"）。枠の中の段は、人の確認・分岐・ほかへのつなぎを持てません。判定に通らなければ、その段だけをやり直します。</p>
      <p class="note">中の段：${membersOf(m, f).map((s) => esc(s.label)).join('、') || 'まだありません'}</p>
      <button type="button" class="btn" id="del-sel">枠を消す（中の段は残す）</button>`;
  }
  if (st.sel.type === 'edge') return '<p class="note">ケーブルを選んでいます。抜くときは Delete キーか、下のボタンを押してください。</p><button type="button" class="btn" id="del-sel">このケーブルを抜く</button>';
  const s = current();
  if (!s) return pipePane();
  const ord = orderStages(m), i = ord.indexOf(s), f = frameOf(m, s), shape = SHAPE_OF[s.kind], z = blockSize(s.kind);
  const prev = ord.slice(0, i).filter((x) => !f || frameOf(m, x) !== f);
  const mini = shapePath(shape, z.w, z.h);
  return `
    <div class="bhead"><svg class="mini" viewBox="-2 -2 ${z.w + 4} ${z.h + 4}"><path class="sh" d="${mini.outer}"/>${mini.inner ? `<path class="sh hollow" d="${mini.inner}"/>` : ''}</svg>
      <div class="t"><input id="b-label" value="${esc(s.label)}" aria-label="ブロックの名前"><input id="b-name" class="mono" value="${esc(s.name)}" aria-label="name（英小文字）"></div>
      <select id="b-kind" aria-label="ブロックの種類">${opt(BLOCK_KINDS.map((k) => [k, KIND_LABEL[k]]), s.kind)}</select></div>
    <div class="composer">
      <div class="lane"><span class="k">渡すもの</span>
        ${m.input !== 'none' ? '<span class="ref auto">@依頼メモ</span>' : ''}
        ${prev.map((x) => `<span class="ref auto">@${esc(x.output)}</span>`).join('')}
        ${s.refs.map((r, j) => `<span class="ref">@${esc(r)}<button type="button" data-unref="${j}" aria-label="外す">×</button></span>`).join('')}
        <input class="ref-add" id="b-ref" placeholder="＋ ファイルやフォルダ（Enter）" aria-label="渡すファイルを足す">
      </div>
      <textarea id="b-prompt" aria-label="このブロックで頼むこと" placeholder="このブロックで Claude に頼むことを書きます">${esc(s.prompt)}</textarea>
      <div class="bar">
        <label class="pill">モデル<select id="b-model">${opt([['', '既定'], ['opus', 'opus'], ['sonnet', 'sonnet'], ['haiku', 'haiku']], s.model)}</select></label>
        <label class="pill">書ける<select id="b-access">${opt([['read', 'read（成果物だけ）'], ['docs', 'docs（文書のフォルダ）'], ['tests', 'tests（テスト）'], ['code', 'code（製品コード）']], s.access)}</select></label>
        <label class="pill toggle${s.bash ? ' on' : ''}"><input type="checkbox" id="b-bash"${s.bash ? ' checked' : ''}>Bash</label>
        <label class="pill">Web<select id="b-web">${opt([['off', '使わない'], ['domains', '決めた所だけ'], ['all', '取得と検索']], s.web)}</select></label>
        <label class="pill">ターン<input type="number" id="b-turns" min="1" max="500" value="${s.maxTurns}"></label>
      </div>
    </div>
    <div class="box"><h3>返すもの</h3>
      <div class="rgrid">
        <label class="field">成果物<input id="b-output" class="mono" value="${esc(s.output)}"></label>
        ${f ? '' : `<label class="pill toggle${s.review ? ' on' : ''}"><input type="checkbox" id="b-review"${s.review ? ' checked' : ''}>このあと人が確認</label>`}
      </div>
      ${s.routes.length || s.kind === 'branch' ? `<div class="field">分岐の選択肢（choice）<div class="choices">${s.routes.map((r, j) => `<span class="choice"><input data-rkey="${j}" value="${esc(r.key)}" aria-label="選択肢の名前"><span>→ ${esc(r.to === END ? '終わり' : stageById(r.to)?.label ?? frameById(r.to)?.name ?? '')}</span><button type="button" data-rdel="${j}" aria-label="消す">×</button></span>`).join('') || '<span class="note">右のプラグを行き先に差すと、選択肢が増えます</span>'}</div></div>` : ''}
    </div>
    ${checkBoxHtml(m, s)}
    ${s.access !== 'read' || s.web === 'domains' ? `<div class="box"><h3>書き込みと取得の範囲</h3>
      ${s.access === 'docs' ? `<label class="field">文書のフォルダ docs_dir<input id="b-docs" class="mono" value="${esc(s.docsDir)}"></label>` : ''}
      ${s.access !== 'read' ? `<label class="field">さらに絞る場所 writes（1行に1つ）<textarea id="b-writes" rows="2">${esc(s.writes.join('\n'))}</textarea></label>` : ''}
      ${s.web === 'domains' ? `<label class="field">取得してよいドメイン（1行に1つ）<textarea id="b-domains" rows="2">${esc(s.domains.join('\n'))}</textarea></label>` : ''}
    </div>` : ''}
    ${sdkPane(s)}
    <details class="preview"><summary>Claude に届く指示を見る</summary><pre id="delivered">${esc(delivered(s))}</pre></details>
    <button type="button" class="btn" id="del-sel">このブロックを消す</button>`;
}

function pipePane(): string {
  const m = model();
  return `<div class="bhead"><svg class="mini" viewBox="-2 -2 136 60"><path class="sh ink" d="${shapePath('terminal', 132, 56).outer}"/></svg>
      <div class="t"><input id="p-label" value="${esc(m.label)}" aria-label="パイプの表示名"><input id="p-desc" value="${esc(m.description)}" placeholder="何をするパイプか（1文）" aria-label="説明"></div></div>
    <div class="row2"><label class="field">依頼メモ<select id="p-input">${opt([['required', '必須'], ['optional', '任意'], ['none', '使わない']], m.input)}</select></label>
      <label class="field">段を流す回数の上限<input type="number" id="p-steps" min="1" value="${m.maxSteps}"></label></div>
    <p class="note">ブロックを押すと、そのブロックで Claude に頼むこと（1回分の依頼）を組み立てられます。形でブロックの役割を見分けます：長方形は調べる、二重枠は任せる、波の紙は文書と図、両端に線はテスト、角を落とした形はコード、六角形は確かめる、ひし形は仕分け、平行四辺形は外を見る。</p>`;
}

function badge(): void {
  const { errors } = validatePipe(model());
  $('badge').textContent = errors.length ? String(errors.length) : 'OK';
  $('badge').className = errors.length ? 'badge' : 'badge ok';
}

function renderPane(): void {
  document.querySelectorAll<HTMLButtonElement>('.tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === st.tab)));
  badge();
  const m = model(), pane = $('pane');
  // 作り直しても、手で開いた折りたたみとスクロールの位置はそのままにする（同じ見出しのものを開き直す）
  const opened = new Set([...pane.querySelectorAll('details[open] > summary')].map((x) => x.textContent ?? ''));
  const top = pane.scrollTop, same = pane.dataset.sel === selKey();
  if (st.tab === 'block') {
    pane.innerHTML = blockPane();
    if (same) pane.querySelectorAll('details').forEach((d) => { if (opened.has(d.querySelector('summary')?.textContent ?? '')) d.open = true; });
  } else if (st.tab === 'check') {
    const { errors } = validatePipe(m);
    pane.innerHTML = `<ul class="result">${errors.length ? errors.map((e) => `<li>${esc(e)}</li>`).join('') : `<li class="ok">パイプ「${esc(m.name)}」: 問題ありません</li>`}</ul>
      <p class="note">pipe-in-gen check と同じ決まりに、作業台で起きやすいこと（つなぎ忘れ・並列の枠の出口）を足しています。誤りがあっても保存はできますが、pipe-in で流す前に直してください。</p>`;
  } else if (st.tab === 'history') {
    pane.innerHTML = historyPane();
  } else {
    const files = pipeFiles(m);
    pane.innerHTML = `<p class="note">保存すると pipes/${esc(st.folder)}/ に、次のファイルを書きます（README.md は無いときだけ作ります）。</p>
      ${Object.entries(files).map(([rel, text]) => `<div class="file"><h3>${esc(rel)}</h3><pre>${esc(text)}</pre></div>`).join('')}`;
  }
  pane.dataset.sel = selKey();
  if (same) pane.scrollTop = top;
}
function historyPane(): string {
  const ops = hist.entries.map((e, i) => ({ e, i })).reverse().map(({ e, i }) =>
    `<li><button type="button" class="hrow${i === hist.at ? ' cur' : ''}${i > hist.at ? ' later' : ''}" data-hist="${i}"${i === hist.at ? ' aria-current="step"' : ''}>${esc(e.label)}</button></li>`).join('');
  const vers = st.versions.map((v) =>
    `<li><button type="button" class="hrow" data-ver="${esc(v.id)}">${esc(when(v.savedAt))}${v.draft ? '<span class="chip warn">下書き（保存していない）</span>' : ''}</button></li>`).join('');
  return `<div class="box"><h3>操作（新しい順）</h3>
      <p class="note">押すと、その時点の形に戻ります。戻したあとでも Ctrl+Y で先へ進めます。Ctrl+Z で1手戻ります。</p>
      <ol class="hist">${ops}</ol></div>
    <div class="box"><h3>保存した版</h3>
      <p class="note">保存のたびに残します（新しい方から ${VERSION_LIMIT} 版まで）。押すと読み込み、保存を押すまでファイルは書きません。</p>
      ${vers ? `<ul class="hist">${vers}</ul>` : '<p class="note">まだありません</p>'}</div>`;
}
const selKey = (): string => `${st.tab}:${st.sel.type}:${'id' in st.sel ? st.sel.id : ''}`;

function render(): void { renderWorld(); renderPane(); }

// ---- 入力 -----------------------------------------------------------------

const lines = (t: string): string[] => t.split('\n').map((x) => x.trim()).filter(Boolean);
$('pane').addEventListener('input', (ev) => {
  const t = ev.target as HTMLInputElement, m = model(), s = current();
  const v: string | boolean = t.type === 'checkbox' ? t.checked : t.value;
  const sv = String(v);
  let full = false;
  if (st.sel.type === 'frame' && t.id === 'fr-name') { frameById(st.sel.id)!.name = sv.trim() || 'group'; changed('枠の名前を変えた', `${selKey()}:fr-name`); renderWorld(); badge(); return; }
  if (t.id === 'p-label') m.label = sv;
  else if (t.id === 'p-desc') m.description = sv;
  else if (t.id === 'p-input') { m.input = sv as PipeModel['input']; full = true; }
  else if (t.id === 'p-steps') m.maxSteps = parseInt(sv, 10) || 1;
  else if (s) {
    if (t.dataset.agent !== undefined) {
      const a = s.agents[+t.dataset.agent]!, f = t.dataset.f!;
      if (f === 'tools') a.tools = sv.split(',').map((x) => x.trim()).filter(Boolean);
      else (a as unknown as Record<string, string>)[f] = sv;
    } else if (t.dataset.mcps !== undefined) {
      const srv = s.mcpServers[+t.dataset.mcps]!, f = t.dataset.f!;
      if (f === 'args') srv.args = sv.split(/\s+/).filter(Boolean);
      else if (f === 'type') { srv.type = sv as typeof srv.type; full = true; }
      else (srv as unknown as Record<string, string>)[f] = sv;
    } else if (t.dataset.rkey !== undefined) s.routes[+t.dataset.rkey]!.key = sv.trim();
    else switch (t.id) {
      case 'b-label': s.label = sv; break;
      case 'b-name': s.name = sv.trim(); break;
      case 'b-kind': s.kind = sv as BlockKind; if (sv === 'verify') setCheck(s, true); full = true; break;
      case 'b-prompt': s.prompt = sv; break;
      case 'b-model': s.model = sv; break;
      case 'b-access': s.access = sv as StageModel['access']; if (sv === 'read') s.writes = []; full = true; break;
      case 'b-bash': s.bash = v === true; full = true; break;
      case 'b-web': s.web = sv as StageModel['web']; full = true; break;
      case 'b-turns': s.maxTurns = parseInt(sv, 10) || 100; break;
      case 'b-output': s.output = sv.trim(); break;
      case 'b-check': setCheck(s, v === true); full = true; break;
      case 'b-verdict': s.check.verdict = v === true; full = true; break;
      case 'b-review': s.review = v === true; full = true; break;
      case 'b-onfail': s.onFail = sv || null; break;
      case 'b-retries': s.check.maxRetries = parseInt(sv, 10); break;
      case 'b-command': s.check.command = sv.trim(); break;
      case 'b-docs': s.docsDir = sv.trim(); break;
      case 'b-writes': s.writes = lines(sv); break;
      case 'b-domains': s.domains = lines(sv); break;
      case 'b-mcp': s.mcp = lines(sv); break;
      case 'b-perm': s.permissionMode = sv; break;
      case 'b-think': s.thinking = sv ? parseInt(sv, 10) : null; break;
      case 'b-fallback': s.fallbackModel = sv; break;
      case 'b-budget': s.maxBudget = sv === '' ? null : Number(sv); break;
      case 'b-sysappend': s.systemAppend = sv; break;
      case 'b-adddirs': s.addDirs = lines(sv); break;
      default: return;
    }
  } else return;
  // 文字を打つ欄は、同じ欄に続けて打った分を1手にまとめる（選ぶ・入り切りは1回ずつ1手）
  const typing = t.tagName === 'TEXTAREA' || (t.tagName === 'INPUT' && t.type !== 'checkbox');
  const field = t.id || `${t.dataset.agent ?? t.dataset.mcps ?? t.dataset.rkey ?? ''}:${t.dataset.f ?? ''}`;
  changed(s ? `「${s.label}」を書き換えた` : 'パイプの設定を書き換えた', typing ? `${selKey()}:${field}` : undefined);
  renderWorld();
  if (full) renderPane();
  else {
    badge();
    const pre = document.getElementById('delivered');
    if (pre && s) pre.textContent = delivered(s);
  }
});
$('pane').addEventListener('change', (ev) => {
  const t = ev.target as HTMLElement;
  if (t.matches('select, input[type=checkbox]')) t.dispatchEvent(new Event('input', { bubbles: true }));
});
$('pane').addEventListener('keydown', (ev) => {
  const t = ev.target as HTMLInputElement, s = current();
  if (t.id === 'b-ref' && ev.key === 'Enter' && t.value.trim() && s) {
    s.refs.push(t.value.trim());
    changed(`「${s.label}」に渡すファイルを足した`);
    renderPane();
    document.getElementById('b-ref')?.focus();
  }
});
$('pane').addEventListener('click', (ev) => {
  const t = (ev.target as HTMLElement).closest('button');
  if (!t) return;
  if (t.dataset.hist !== undefined) { restore(jump(hist, +t.dataset.hist)); return; }
  if (t.dataset.ver !== undefined) { vscode.postMessage({ type: 'loadVersion', id: t.dataset.ver }); return; }
  const s = current();
  if (t.dataset.unref !== undefined && s) s.refs.splice(+t.dataset.unref, 1);
  else if (t.dataset.rdel !== undefined && s) s.routes.splice(+t.dataset.rdel, 1);
  else if (t.dataset.agentdel !== undefined && s) s.agents.splice(+t.dataset.agentdel, 1);
  else if (t.dataset.mcpsdel !== undefined && s) s.mcpServers.splice(+t.dataset.mcpsdel, 1);
  else if (t.id === 'agent-add' && s) s.agents.push({ name: `helper-${s.agents.length + 1}`, description: '', prompt: '', tools: ['Read', 'Grep', 'Glob'], model: '' });
  else if (t.id === 'mcps-add' && s) s.mcpServers.push({ name: `server${s.mcpServers.length + 1}`, type: 'stdio', command: '', args: [], url: '' });
  else if (t.id === 'del-sel') { deleteSelection(); return; }
  else return;
  changed(`「${s?.label ?? ''}」の設定を変えた`);
  render();
});
document.querySelectorAll<HTMLButtonElement>('.tabs button').forEach((b) => b.addEventListener('click', () => { st.tab = b.dataset.tab as typeof st.tab; renderPane(); }));

// ---- 面の操作：選ぶ・動かす・囲む・差す・見る範囲 ---------------------------------------

const area = $('area');
const toWorld = (cx: number, cy: number): Point => {
  const r = area.getBoundingClientRect();
  return { x: (cx - r.left - st.view.x) / st.view.z, y: (cy - r.top - st.view.y) / st.view.z };
};
const snap = (v: number): number => Math.round(v / 10) * 10;
type Act =
  | { type: 'pan'; sx: number; sy: number; vx: number; vy: number }
  | { type: 'move'; id: string; sx: number; sy: number; ox: number; oy: number; moved: boolean; before: Map<string, string>; loose: boolean }
  | { type: 'many'; sx: number; sy: number; items: { o: { x: number; y: number }; x: number; y: number }[]; moved: boolean; before: Map<string, string> }
  | { type: 'frame'; f: FrameModel; sx: number; sy: number; ox: number; oy: number; kids: { s: StageModel; x: number; y: number }[]; before: Map<string, string>; moved: boolean }
  | { type: 'resize'; f: FrameModel; sx: number; sy: number; ow: number; oh: number; before: Map<string, string>; moved: boolean }
  | { type: 'box'; a: Point; b: Point }
  | { type: 'link'; from: string; a: Point }
  | { type: 'replug'; wire: Wire; a: Point };
let act: Act | null = null;

// 段がどの並列の枠に入っているか。動かして枠に入った・出たときは、知らせる（中心が枠に入ると並列の段になるため）
const groupsNow = (): Map<string, string> => new Map(model().stages.map((s) => [s.id, frameOf(model(), s)?.name ?? '']));
function tellGroups(before: Map<string, string>): void {
  const said: string[] = [];
  for (const s of model().stages) {
    const was = before.get(s.id) ?? '', now = frameOf(model(), s)?.name ?? '';
    if (was !== now) said.push(now ? `「${s.label}」が並列の枠「${now}」に入りました` : `「${s.label}」が並列の枠から出ました`);
  }
  if (said.length) toast(said.join('／'));
}

/** 選んでいるものをまとめて動かす準備（枠を選んでいれば、中の段も一緒に動かす） */
function manyAct(sx: number, sy: number): Act {
  const m = model(), objs = new Set<{ x: number; y: number }>();
  for (const id of st.picked) {
    const s = stageById(id), f = frameById(id);
    if (s) objs.add(s);
    if (f) { objs.add(f); membersOf(m, f).forEach((k) => objs.add(k)); }
  }
  return { type: 'many', sx, sy, items: [...objs].map((o) => ({ o, x: o.x, y: o.y })), moved: false, before: groupsNow() };
}

/** 間に挟む先として、点の近くの「次の段」のケーブルを目立たせる（無ければ消す） */
function hoverDrop(p: Point | null): void {
  const i = p ? nearestWire(wires, p, 16 / st.view.z) : -1;
  const key = i >= 0 ? wireKey(wires[i]!) : null;
  if (key !== st.dropWire) { st.dropWire = key; drawWires(); }
}
const dropTarget = (): Wire | null => (st.dropWire ? wires.find((w) => wireKey(w) === st.dropWire) ?? null : null);

/** ケーブルに落とした段を間に挟む（挟めなければ理由を出す）。挟めたら true */
function dropInto(id: string): boolean {
  const w = dropTarget();
  st.dropWire = null;
  if (!w) return false;
  const r = insertBetween(model(), w, id);
  toast(r.message || '挟めませんでした');
  return r.changed;
}

area.addEventListener('pointerdown', (ev) => {
  if (!st.m || menuEl) return;
  // 中ボタンは、どこを押しても図を動かす
  if (ev.button === 1) {
    ev.preventDefault();
    act = { type: 'pan', sx: ev.clientX, sy: ev.clientY, vx: st.view.x, vy: st.view.y };
    area.setPointerCapture(ev.pointerId);
    return;
  }
  if (ev.button !== 0) return;
  // 文字を選ぶ・ブラウザのドラッグが始まると pointercancel になり、離した操作が届かなくなるので止める
  ev.preventDefault();
  // 止めるとフォーカスが右の欄の入力に残り、Delete が入力に取られるので外す
  (document.activeElement as HTMLElement | null)?.blur();
  const target = ev.target as HTMLElement;
  const port = target.closest<HTMLElement>('[data-port]'), hit = target.closest<SVGPathElement>('.wire-hit');
  const plug = target.closest<SVGGElement>('[data-plug]');
  const node = target.closest<HTMLElement>('.node'), frame = target.closest<HTMLElement>('.frame');
  const w = toWorld(ev.clientX, ev.clientY), m = model();
  if (plug) {
    // 差さっているプラグを掴んで抜く。ケーブルは元の側から手元までついてくる
    const wire = wires[+plug.dataset.plug!]!;
    act = { type: 'replug', wire, a: wire.points[0]! };
    st.lifted = wireKey(wire);
    drawWires();
    startRope(act.a, w);
  } else if (port) {
    const r = blockRect(m, port.dataset.port!);
    act = { type: 'link', from: port.dataset.port!, a: { x: r.x + r.w, y: r.y + r.h / 2 } };
    startRope(act.a, w);
  } else if (hit) {
    selectOne({ type: 'edge', wire: wires[+hit.dataset.edge!]! });
    st.tab = 'block';
    render();
    return;
  } else if (node || (frame && target.dataset.drag)) {
    const id = (node ?? frame)!.dataset.id!;
    if (ev.shiftKey && !isTerm(id)) {
      // Shift+クリック：選んでいるものに足す・外す
      const now = picks();
      st.picked = now.includes(id) ? now.filter((x) => x !== id) : [...now, id];
      st.sel = st.picked.length === 1 ? (stageById(st.picked[0]!) ? { type: 'stage', id: st.picked[0]! } : { type: 'frame', id: st.picked[0]! }) : { type: 'pipe' };
      render();
      return;
    }
    if (st.picked.length > 1 && st.picked.includes(id)) {
      act = manyAct(w.x, w.y);
    } else if (node) {
      const o = id === 'start' ? m.start : id === END ? m.end : stageById(id)!;
      if (!isTerm(id)) selectOne({ type: 'stage', id });
      act = { type: 'move', id, sx: w.x, sy: w.y, ox: o.x, oy: o.y, moved: false, before: groupsNow(), loose: !isTerm(id) && isLoose(m, id) };
    } else {
      const f = frameById(id)!;
      selectOne({ type: 'frame', id: f.id });
      act = target.dataset.drag === 'resize'
        ? { type: 'resize', f, sx: w.x, sy: w.y, ow: f.w, oh: f.h, before: groupsNow(), moved: false }
        : { type: 'frame', f, sx: w.x, sy: w.y, ox: f.x, oy: f.y, kids: membersOf(m, f).map((s) => ({ s, x: s.x, y: s.y })), before: groupsNow(), moved: false };
    }
    render();
  } else if (ev.shiftKey) {
    // Shift+ドラッグ：囲んで選ぶ
    act = { type: 'box', a: w, b: w };
  } else {
    selectOne({ type: 'pipe' });
    act = { type: 'pan', sx: ev.clientX, sy: ev.clientY, vx: st.view.x, vy: st.view.y };
    renderWorld();
    renderPane();
  }
  area.setPointerCapture(ev.pointerId);
});
area.addEventListener('pointermove', (ev) => {
  if (!act || !st.m) return;
  const w = toWorld(ev.clientX, ev.clientY), m = model();
  if (act.type === 'pan') { st.view.x = act.vx + ev.clientX - act.sx; st.view.y = act.vy + ev.clientY - act.sy; st.viewMoved = true; applyView(); }
  else if (act.type === 'move') {
    const o = act.id === 'start' ? m.start : act.id === END ? m.end : stageById(act.id)!;
    o.x = snap(act.ox + w.x - act.sx);
    o.y = snap(act.oy + w.y - act.sy);
    act.moved = true;
    const el = document.querySelector<HTMLElement>(`.node[data-id="${CSS.escape(act.id)}"]`);
    if (el) { el.style.left = `${o.x}px`; el.style.top = `${o.y}px`; }
    drawWires();
    // つながっていない段は、ケーブルの上に落とすと間に挟める
    if (act.loose) hoverDrop(w);
  } else if (act.type === 'many') {
    const dx = snap(w.x - act.sx), dy = snap(w.y - act.sy);
    act.items.forEach((it) => { it.o.x = it.x + dx; it.o.y = it.y + dy; });
    act.moved = true;
    renderWorld();
  } else if (act.type === 'frame') {
    const dx = snap(w.x - act.sx), dy = snap(w.y - act.sy);
    act.f.x = act.ox + dx;
    act.f.y = act.oy + dy;
    act.kids.forEach((k) => { k.s.x = k.x + dx; k.s.y = k.y + dy; });
    act.moved = true;
    renderWorld();
  } else if (act.type === 'resize') {
    act.f.w = Math.max(240, snap(act.ow + w.x - act.sx));
    act.f.h = Math.max(120, snap(act.oh + w.y - act.sy));
    act.moved = true;
    renderWorld();
  } else if (act.type === 'box') {
    act.b = w;
    drawBox(act.a, act.b);
  } else if (act.type === 'link' || act.type === 'replug') {
    moveRope(w);
    // 差す先（ブロックの上か、そのコンセントの上）を目立たせる
    document.querySelectorAll('.node.drop, .frame.drop').forEach((n) => n.classList.remove('drop'));
    const id = dropAt(w), from = act.type === 'link' ? act.from : null;
    if (id && id !== from) document.querySelector(`#world > [data-id="${CSS.escape(id)}"]`)?.classList.add('drop');
  }
});
area.addEventListener('pointerup', (ev) => {
  if (!act) return;
  const a = act;
  act = null;
  if (a.type === 'link') {
    const to = dropAt(toWorld(ev.clientX, ev.clientY));
    stopRope();
    if (to) link(a.from, to);
    else toast('差すのをやめました（ブロックかコンセントの上で離すと差さります）');
    render();
    st.snapped = null;
    return;
  }
  if (a.type === 'replug') {
    // ブロックかコンセントの上で離せば差し直し、何もない所なら抜いたまま
    const to = dropAt(toWorld(ev.clientX, ev.clientY));
    stopRope();
    const wire = a.wire, m = model();
    const r = to ? replug(m, wire, to) : unplug(m, wire);
    if (r.changed) {
      if (st.sel.type === 'edge') st.sel = { type: 'pipe' };
      if (r.to) st.snapped = { from: wire.owner ?? wire.from, to: r.to };
      changed(r.message || 'ケーブルを差し直した');
    } else if (to === wire.to) st.snapped = { from: wire.owner ?? wire.from, to: wire.to };
    if (r.message) toast(r.message);
    st.lifted = null;
    render();
    st.snapped = null;
    return;
  }
  if (a.type === 'box') {
    document.getElementById('box')?.remove();
    const ids = itemsInRect(model(), { x: a.a.x, y: a.a.y, w: a.b.x - a.a.x, h: a.b.y - a.a.y });
    st.picked = ids;
    st.sel = ids.length === 1 ? (stageById(ids[0]!) ? { type: 'stage', id: ids[0]! } : { type: 'frame', id: ids[0]! }) : { type: 'pipe' };
    if (ids.length) toast(`${ids.length} 個を選びました`);
    render();
    return;
  }
  if (a.type === 'move' && a.moved) {
    const label = stageById(a.id)?.label ?? (a.id === END ? '終わり' : '始まり');
    if (a.loose && dropInto(a.id)) changed(`「${label}」を間に挟んだ`);
    else changed(`「${label}」を動かした`);
    render();
    tellGroups(a.before);
    return;
  }
  if (a.type === 'many' && a.moved) { changed(`${st.picked.length} 個を動かした`); render(); tellGroups(a.before); return; }
  if ((a.type === 'frame' || a.type === 'resize') && a.moved) {
    changed(a.type === 'frame' ? `並列の枠「${a.f.name}」を動かした` : `並列の枠「${a.f.name}」の大きさを変えた`);
    tellGroups(a.before);
  }
  renderPane();
});
// ブラウザが操作を取り上げたとき（pointercancel）は、引きかけのケーブルなどを残さずに描き直す
area.addEventListener('pointercancel', () => {
  if (!act) return;
  act = null;
  stopRope();
  st.lifted = null;
  st.dropWire = null;
  document.getElementById('box')?.remove();
  render();
});
area.addEventListener('wheel', (ev) => {
  ev.preventDefault();
  if (ev.ctrlKey || ev.metaKey) {
    const r = area.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
    const z = Math.min(2, Math.max(0.3, st.view.z * Math.exp(-ev.deltaY * 0.0022)));
    st.view.x = mx - ((mx - st.view.x) * z) / st.view.z;
    st.view.y = my - ((my - st.view.y) * z) / st.view.z;
    st.view.z = z;
  } else { st.view.x -= ev.deltaX; st.view.y -= ev.deltaY; }
  st.viewMoved = true;
  applyView();
}, { passive: false });
// 面の大きさが変わったら（読み込み直後にパネルの幅が決まったときも）、見る範囲を自分で動かしていなければ全体を見直す
new ResizeObserver(() => { if (st.m && !st.viewMoved) fit(); }).observe(area);
area.addEventListener('keydown', (ev) => {
  const node = (ev.target as HTMLElement).closest<HTMLElement>('.node');
  if (node && (ev.key === 'Enter' || ev.key === ' ') && !isTerm(node.dataset.id!)) {
    ev.preventDefault();
    selectOne({ type: 'stage', id: node.dataset.id! });
    render();
  }
});

/** 囲んでいる四角（world の中に置き、位置と大きさは CSSOM で入れる） */
function drawBox(a: Point, b: Point): void {
  let el = document.getElementById('box');
  if (!el) {
    el = document.createElement('div');
    el.id = 'box';
    el.className = 'marquee';
    $('world').appendChild(el);
  }
  Object.assign(el.style, { left: `${Math.min(a.x, b.x)}px`, top: `${Math.min(a.y, b.y)}px`, width: `${Math.abs(b.x - a.x)}px`, height: `${Math.abs(b.y - a.y)}px` });
}

/** プラグを差す：右のブロックなら次の段、仕分けなら分岐、左（前）のブロックなら差し戻し、自分ならやり直し */
function link(from: string, to: string): void {
  const m = model();
  if (!to || from === 'start') return;
  if (to === 'start') { toast('始まりには差せません（始まりからは、いちばん左の段へ自動でつながります）'); return; }
  const fromFrame = frameById(from);
  const src = stageById(from);
  if (src && frameOf(m, src)) { toast('並列の枠の中の段からはつなげません。枠の右のプラグを差してください'); return; }
  const ord = orderStages(m);
  const pos = (id: string): number => ord.findIndex((s) => s.id === id);
  const firstOf = (id: string): string | undefined => { const f = frameById(id); return f ? membersOf(m, f)[0]?.id : id; };
  const pf = fromFrame ? Math.max(...membersOf(m, fromFrame).map((s) => pos(s.id))) : pos(from);
  const pt = to === END ? Infinity : pos(firstOf(to) ?? '');
  const nameTo = to === END ? '終わり' : stageById(to)?.label ?? frameById(to)?.name ?? to;
  let said = '';
  if (fromFrame) {
    if (pt <= pf) { toast('並列の枠からは、右にある段へだけつなげます'); return; }
    fromFrame.next = to;
    said = `並列の枠 → ${nameTo}`;
  } else if (src) {
    if (to === from) { src.check.on = true; src.onFail = null; said = `${src.label}：判定に通らなければ、自分をやり直します`; }
    else if (pt <= pf) {
      if (frameById(to)) { toast('差し戻しは、枠ではなく段へ差してください'); return; }
      src.check.on = true;
      src.check.verdict = true;
      src.onFail = to;
      said = `${src.label}：判定に通らなければ「${nameTo}」へ戻します`;
    } else if (src.routes.length || src.kind === 'branch') {
      src.next = null;
      if (src.routes.some((r) => r.to === to)) { toast('その行き先への分岐はもうあります'); return; }
      src.routes.push({ key: `choice${src.routes.length + 1}`, to });
      said = `${src.label}：分岐を1本足しました。右で選択肢の名前を決めてください`;
    } else {
      src.next = to;
      said = `${src.label} → ${nameTo}`;
    }
  } else return;
  toast(said);
  changed(`ケーブルを差した（${said}）`);
}

/** 選んでいるもの（ids を渡せばそれ）を消す。ケーブルを選んでいれば抜く */
function deleteSelection(ids = picks()): void {
  const m = model();
  if (!ids.length && st.sel.type === 'edge') {
    const r = unplug(m, st.sel.wire);
    if (r.message) toast(r.message);
    if (!r.changed) return;
    st.sel = { type: 'pipe' };
    changed(r.message || 'ケーブルを抜いた');
    render();
    return;
  }
  if (!ids.length) return;
  const one = ids.length === 1 ? stageById(ids[0]!)?.label ?? (frameById(ids[0]!) ? `並列の枠「${frameById(ids[0]!)!.name}」` : '') : '';
  const r = deleteItems(m, ids);
  if (!r.stages && !r.frames) return;
  const said = one ? `「${one}」を消しました` : `${r.stages + r.frames} 個を消しました`;
  toast(r.frames && !r.stages ? `${said}（枠の中の段は残っています）` : said);
  selectOne({ type: 'pipe' });
  changed(said.replace('しました', 'した'));
  render();
}

// ---- 棚：形のブロックをドラッグして置く（押すだけでも置ける） ----------------------

function tileSvg(kind: BlockKind): string {
  const shape = SHAPE_OF[kind], z = blockSize(kind), p = shapePath(shape, z.w, z.h);
  const icon = `<g transform="translate(${z.w / 2 - 34} ${z.h / 2 - 34}) scale(2.8)">${ICON[kind].replace('<svg', '<svg width="24" height="24"')}</g>`;
  return `<svg viewBox="-3 -3 ${z.w + 6} ${z.h + 6}" preserveAspectRatio="xMidYMid meet"><path class="sh thick" d="${p.outer}"/>${p.inner ? `<path class="sh hollow" d="${p.inner}"/>` : ''}${icon}</svg>`;
}
const shelf = $('shelf');
[...BLOCK_KINDS, 'frame' as const].forEach((k) => {
  const t = document.createElement('div');
  t.className = 'tile';
  t.tabIndex = 0;
  t.setAttribute('role', 'button');
  t.dataset.kind = k;
  t.title = k === 'frame' ? '同時に流す' : KIND_HINT[k];
  t.innerHTML = k === 'frame'
    ? '<svg viewBox="0 0 64 38"><rect class="par" x="3" y="3" width="58" height="32" rx="11" stroke-width="2.4"/><rect class="sh" x="12" y="10" width="40" height="7"/><rect class="sh" x="12" y="21" width="40" height="7"/></svg>並列の枠'
    : `${tileSvg(k)}${KIND_LABEL[k]}`;
  shelf.appendChild(t);
});
/**
 * 棚から置く。exact でなければ（押した・Enter）、at の近くの空いた場所に置く。ドラッグで置いたときは離した場所に置く。
 * ケーブルの上に落としたとき（st.dropWire）は、その間に挟む。
 */
function addBlock(kind: BlockKind | 'frame', at: Point, exact: boolean): void {
  const m = model();
  const size = kind === 'frame' ? { w: 280, h: 220 } : blockSize(kind);
  const p = exact ? { x: snap(at.x - size.w / 2), y: snap(at.y - size.h / 2) } : freeSpot(m, size, at);
  if (kind === 'frame') {
    let n = m.frames.length + 1;
    while (m.frames.some((f) => f.name === `group${n}`)) n++;
    const f: FrameModel = { id: nid('f'), name: `group${n}`, x: p.x, y: p.y, w: size.w, h: size.h, next: null };
    m.frames.push(f);
    selectOne({ type: 'frame', id: f.id });
    st.dropWire = null;
    toast('並列の枠を置きました。段をこの中に動かすと、同時に流れます');
    changed(`並列の枠「${f.name}」を置いた`);
  } else {
    let n = m.stages.length + 1, name: string;
    do { name = `${kind}-${n++}`; } while (m.stages.some((s) => s.name === name));
    const s = newStage(nid('s'), kind, name);
    s.label = `新しい${KIND_LABEL[kind]}`;
    s.x = p.x;
    s.y = p.y;
    m.stages.push(s);
    selectOne({ type: 'stage', id: s.id });
    st.tab = 'block';
    if (dropInto(s.id)) changed(`「${s.label}」を間に挟んだ`);
    else {
      toast(`「${s.label}」を置きました。右で頼むことを書き、右のプラグをほかのブロックに差してください`);
      changed(`「${s.label}」を置いた`);
    }
  }
  render();
  // 空きを探して見えている範囲の外に置いたときは、全体を見直して置いたものが見えるようにする
  const a = area.getBoundingClientRect(), v = st.view;
  const sx = p.x * v.z + v.x, sy = p.y * v.z + v.y;
  if (sx < 0 || sy < 0 || sx + size.w * v.z > a.width || sy + size.h * v.z > a.height) fit();
}
const inArea = (cx: number, cy: number): boolean => {
  const r = area.getBoundingClientRect();
  return cx > r.left && cx < r.right && cy > r.top && cy < r.bottom;
};
let drag: { kind: BlockKind | 'frame'; el: HTMLElement; sx: number; sy: number; moved: boolean; ghost: HTMLElement | null } | null = null;
shelf.addEventListener('pointerdown', (ev) => {
  const t = (ev.target as HTMLElement).closest<HTMLElement>('.tile');
  if (!t || !st.m) return;
  ev.preventDefault();
  drag = { kind: t.dataset.kind as BlockKind | 'frame', el: t, sx: ev.clientX, sy: ev.clientY, moved: false, ghost: null };
  shelf.setPointerCapture(ev.pointerId);
});
shelf.addEventListener('pointercancel', () => {
  drag?.ghost?.remove();
  drag = null;
  hoverDrop(null);
});
shelf.addEventListener('pointermove', (ev) => {
  if (!drag) return;
  if (!drag.moved && Math.hypot(ev.clientX - drag.sx, ev.clientY - drag.sy) > 5) {
    drag.moved = true;
    drag.ghost = drag.el.cloneNode(true) as HTMLElement;
    drag.ghost.classList.add('ghost');
    document.body.appendChild(drag.ghost);
  }
  if (drag.ghost) { drag.ghost.style.left = `${ev.clientX - 40}px`; drag.ghost.style.top = `${ev.clientY - 30}px`; }
  // 段を棚から引いてケーブルの上に来たら、間に挟めることを見せる（枠は挟めない）
  if (drag.moved && drag.kind !== 'frame') hoverDrop(inArea(ev.clientX, ev.clientY) ? toWorld(ev.clientX, ev.clientY) : null);
});
shelf.addEventListener('pointerup', (ev) => {
  if (!drag) return;
  drag.ghost?.remove();
  const r = area.getBoundingClientRect();
  if (!drag.moved) addBlock(drag.kind, toWorld(r.left + r.width / 2, r.top + r.height / 2), false);
  else if (inArea(ev.clientX, ev.clientY)) addBlock(drag.kind, toWorld(ev.clientX, ev.clientY), true);
  else hoverDrop(null);
  drag = null;
});
shelf.addEventListener('keydown', (ev) => {
  const t = (ev.target as HTMLElement).closest<HTMLElement>('.tile');
  if (t && (ev.key === 'Enter' || ev.key === ' ') && st.m) {
    ev.preventDefault();
    const r = area.getBoundingClientRect();
    addBlock(t.dataset.kind as BlockKind | 'frame', toWorld(r.left + r.width / 2, r.top + r.height / 2), false);
  }
});

// ---- 複製・コピー・貼り付け --------------------------------------------------------

/** ids を写して少しずらして貼り、貼ったものを選ぶ */
function duplicate(ids: string[]): void {
  if (!ids.length) return;
  const clip = copyItems(model(), ids);
  const added = pasteClip(model(), clip, pasteOffset(clip, 1), nid);
  pickAll(added);
  toast(`${added.length === 1 ? '1 個' : `${added.length} 個`}を複製しました`);
  changed(`${added.length} 個を複製した`);
  render();
}
function copySelection(): void {
  const ids = picks();
  if (!ids.length) return;
  st.clip = copyItems(model(), ids);
  st.pasted = 0;
  toast(`${ids.length} 個を写しました（Ctrl+V で貼れます）`);
}
/** 写したものを貼る。at を渡せば、写したものの左上をそこに合わせる。渡さなければ、貼るたびに少しずつずらす */
function paste(at?: Point): void {
  if (!st.clip) { toast('写したものがありません（Ctrl+C で写せます）'); return; }
  let offset: Point;
  if (at) {
    const xs = [...st.clip.stages.map((s) => s.x), ...st.clip.frames.map((f) => f.x)], ys = [...st.clip.stages.map((s) => s.y), ...st.clip.frames.map((f) => f.y)];
    offset = { x: at.x - Math.min(...xs), y: at.y - Math.min(...ys) };
  } else {
    st.pasted++;
    offset = pasteOffset(st.clip, st.pasted);
  }
  const added = pasteClip(model(), st.clip, offset, nid);
  pickAll(added);
  toast(`${added.length} 個を貼りました`);
  changed(`${added.length} 個を貼り付けた`);
  render();
}
/** ids をまとめて選ぶ（1つなら、それを右の欄に出す） */
function pickAll(ids: string[]): void {
  st.picked = ids;
  st.sel = ids.length === 1 ? (stageById(ids[0]!) ? { type: 'stage', id: ids[0]! } : { type: 'frame', id: ids[0]! }) : { type: 'pipe' };
}

// ---- 右クリックのメニュー --------------------------------------------------------

let menuEl: HTMLElement | null = null;
let menu: { items: MenuItem[]; path: MenuPath; target: MenuTarget; at: Point } | null = null;

/** 押したもの（ブロック・枠・何もないところ・複数選択）のメニューを、画面の (cx, cy) に出す */
function openMenu(target: MenuTarget, cx: number, cy: number, at: Point): void {
  const items = menuFor(model(), target, { hasClip: st.clip !== null, savedNames: st.savedNames });
  closeMenu();
  if (!items.length) return;
  menu = { items, path: [items.findIndex((i) => !i.sep)], target, at };
  menuEl = document.createElement('div');
  menuEl.className = 'menus';
  document.body.appendChild(menuEl);
  drawMenu({ x: cx, y: cy });
}
function closeMenu(): void {
  menuEl?.remove();
  menuEl = null;
  menu = null;
}
const menuItemsHtml = (items: MenuItem[], level: number, cur: MenuPath): string => items.map((it, i) => it.sep
  ? '<div class="msep" role="separator"></div>'
  : `<button type="button" class="mitem${cur[level] === i ? ' on' : ''}" role="menuitem" tabindex="-1" data-level="${level}" data-i="${i}"${it.disabled ? ` aria-disabled="true" title="${esc(it.disabled)}"` : ''}${it.children ? ' aria-haspopup="menu"' : ''}>
      <span>${esc(it.label)}</span>${it.children ? '<span class="msub" aria-hidden="true">▸</span>' : ''}${it.disabled ? `<small>${esc(it.disabled)}</small>` : ''}</button>`).join('');
/** メニュー（と開いているサブメニュー）を描き、面からはみ出さない所に置いて、今の項目にフォーカスを移す */
function drawMenu(at?: Point): void {
  if (!menu || !menuEl) return;
  const box = { w: window.innerWidth, h: window.innerHeight };
  const top = menuEl.querySelector<HTMLElement>('.menu.l0');
  const origin = at ?? (top ? { x: top.offsetLeft, y: top.offsetTop } : { x: 0, y: 0 });
  menuEl.innerHTML = `<div class="menu l0" role="menu">${menuItemsHtml(menu.items, 0, menu.path)}</div>`;
  const l0 = menuEl.querySelector<HTMLElement>('.menu.l0')!;
  const p0 = at ? placeMenu(origin, { w: l0.offsetWidth, h: l0.offsetHeight }, box) : origin;
  Object.assign(l0.style, { left: `${p0.x}px`, top: `${p0.y}px` });
  const parent = menu.items[menu.path[0]!];
  if (menu.path.length > 1 && parent?.children) {
    const sub = document.createElement('div');
    sub.className = 'menu l1';
    sub.setAttribute('role', 'menu');
    sub.innerHTML = menuItemsHtml(parent.children, 1, menu.path);
    menuEl.appendChild(sub);
    const row = l0.querySelector<HTMLElement>(`[data-i="${menu.path[0]}"]`)!;
    const r = row.getBoundingClientRect();
    // 右に出し、入らなければ左に出す
    let x = r.right;
    if (x + sub.offsetWidth > box.w) x = r.left - sub.offsetWidth;
    const p1 = placeMenu({ x: Math.max(0, x), y: r.top }, { w: sub.offsetWidth, h: sub.offsetHeight }, box);
    Object.assign(sub.style, { left: `${p1.x}px`, top: `${p1.y}px` });
  }
  menuEl.querySelector<HTMLElement>(`.menu.l${menu.path.length - 1} .mitem.on`)?.focus();
}
/** 選んでいるものから、メニューの対象を決める（キーボードで開くとき） */
function selectionTarget(): MenuTarget {
  if (st.picked.length > 1) return { type: 'multi', ids: [...st.picked] };
  if (st.sel.type === 'stage') return { type: 'stage', id: st.sel.id };
  if (st.sel.type === 'frame') return { type: 'frame', id: st.sel.id };
  const r = area.getBoundingClientRect();
  return { type: 'canvas', at: toWorld(r.left + r.width / 2, r.top + r.height / 2) };
}
function openMenuFromKeyboard(): void {
  if (!st.m) return;
  const target = selectionTarget(), a = area.getBoundingClientRect();
  let cx = a.left + a.width / 2, cy = a.top + a.height / 2;
  const id = target.type === 'stage' || target.type === 'frame' ? target.id : target.type === 'multi' ? target.ids[0]! : null;
  if (id) {
    const el = document.querySelector<HTMLElement>(`#world > [data-id="${CSS.escape(id)}"]`)?.getBoundingClientRect();
    if (el) { cx = el.left + el.width / 2; cy = el.top + el.height / 2; }
  }
  openMenu(target, cx, cy, target.type === 'canvas' ? target.at : toWorld(cx, cy));
}

area.addEventListener('contextmenu', (ev) => {
  ev.preventDefault();
  if (!st.m || act) return;
  const target = ev.target as HTMLElement;
  // ケーブル・プラグにはメニューを出さない（抜き差しはドラッグで）
  if (target.closest('.wire-hit, [data-plug], [data-port]')) { closeMenu(); return; }
  const node = target.closest<HTMLElement>('.node'), frame = target.closest<HTMLElement>('.frame');
  const at = toWorld(ev.clientX, ev.clientY);
  let t: MenuTarget;
  const id = node && !isTerm(node.dataset.id!) ? node.dataset.id! : !node && frame ? frame.dataset.id! : null;
  if (id && st.picked.length > 1 && st.picked.includes(id)) t = { type: 'multi', ids: [...st.picked] };
  else if (id && node) { selectOne({ type: 'stage', id }); render(); t = { type: 'stage', id }; }
  else if (id) { selectOne({ type: 'frame', id }); render(); t = { type: 'frame', id }; }
  else t = { type: 'canvas', at };
  openMenu(t, ev.clientX, ev.clientY, at);
});
// メニューの外を押したら閉じる（メニューの中の押下は、下の click で受ける）
document.addEventListener('pointerdown', (ev) => {
  if (menuEl && !menuEl.contains(ev.target as Node)) closeMenu();
}, true);
document.addEventListener('click', (ev) => {
  if (!menu || !menuEl) return;
  const b = (ev.target as HTMLElement).closest<HTMLElement>('.mitem');
  if (!b || !menuEl.contains(b)) return;
  const level = +b.dataset.level!, i = +b.dataset.i!;
  const path = level === 0 ? [i] : [menu.path[0]!, i];
  const it = level === 0 ? menu.items[i]! : menu.items[menu.path[0]!]!.children![i]!;
  if (it.disabled) return;
  if (it.children) { menu.path = [i, 0]; drawMenu(); return; }
  menu.path = path;
  runMenu(it.id);
});
document.addEventListener('pointerover', (ev) => {
  if (!menu || !menuEl) return;
  const b = (ev.target as HTMLElement).closest<HTMLElement>('.mitem');
  if (!b || !menuEl.contains(b)) return;
  const level = +b.dataset.level!, i = +b.dataset.i!;
  const next = level === 0 ? (menu.items[i]!.children && !menu.items[i]!.disabled ? [i, 0] : [i]) : [menu.path[0]!, i];
  if (next.join() !== menu.path.join()) { menu.path = next; drawMenu(); }
});

/** メニューの項目を実行する */
function runMenu(id: string): void {
  if (!menu) return;
  const { target, at } = menu;
  closeMenu();
  const m = model();
  const ids = target.type === 'multi' ? target.ids : target.type === 'stage' || target.type === 'frame' ? [target.id] : [];
  const s = target.type === 'stage' ? stageById(target.id) : undefined;
  if (id.startsWith('add:')) { addBlock(id.slice(4) as BlockKind, at, true); return; }
  if (id.startsWith('frame-in:')) {
    const r = putInFrame(m, ids, id.slice('frame-in:'.length));
    toast(r.message);
    if (r.changed) { changed(r.message.replace(/。.*$/, '')); render(); }
    return;
  }
  switch (id) {
    case 'rename':
    case 'show-prompt':
      if (!s) return;
      selectOne({ type: 'stage', id: s.id });
      st.tab = 'block';
      render();
      if (id === 'rename') { const el = document.getElementById('b-label') as HTMLInputElement | null; el?.focus(); el?.select(); }
      else { const d = document.querySelector<HTMLDetailsElement>('details.preview'); if (d) { d.open = true; d.scrollIntoView({ block: 'nearest' }); } }
      return;
    case 'open-prompt': if (s) vscode.postMessage({ type: 'openPrompt', name: s.name }); return;
    case 'duplicate': duplicate(ids); return;
    case 'review':
      if (!s) return;
      s.review = !s.review;
      changed(s.review ? `「${s.label}」に人の確認をつけた` : `「${s.label}」の人の確認を外した`);
      render();
      return;
    case 'frame-out': {
      if (!s) return;
      const r = takeOutOfFrame(m, s.id);
      toast(r.message);
      if (r.changed) { changed(r.message.replace('しました', 'した')); render(); }
      return;
    }
    case 'unplug-all':
      if (s && unplugAll(m, s.id)) { toast(`「${s.label}」のケーブルをすべて抜きました`); changed(`「${s.label}」のケーブルをすべて抜いた`); render(); }
      return;
    case 'delete': deleteSelection(ids); return;
    case 'rename-frame': {
      if (target.type !== 'frame') return;
      selectOne({ type: 'frame', id: target.id });
      st.tab = 'block';
      render();
      const el = document.getElementById('fr-name') as HTMLInputElement | null;
      el?.focus();
      el?.select();
      return;
    }
    case 'delete-frame': deleteSelection(ids); return;
    case 'delete-frame-all': {
      const f = target.type === 'frame' ? frameById(target.id) : undefined;
      if (f) deleteSelection([f.id, ...membersOf(m, f).map((x) => x.id)]);
      return;
    }
    case 'add-frame': addBlock('frame', at, true); return;
    case 'paste': paste(at); return;
    case 'arrange': arrange(); return;
    case 'fit': st.viewMoved = false; fit(); return;
  }
}

// ---- キーボード ---------------------------------------------------------------

const typingIn = (t: EventTarget | null): boolean => t instanceof HTMLElement && t.matches('input, textarea, select, [contenteditable="true"]');
document.addEventListener('keydown', (ev) => {
  // メニューを開いているあいだは、キーはメニューが受ける
  if (menu) {
    if (['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight', 'Enter', ' ', 'Escape', 'Tab'].includes(ev.key)) ev.preventDefault();
    if (ev.key === 'Tab') { closeMenu(); return; }
    const r = menuKey(menu.items, menu.path, ev.key);
    if (r.close) { closeMenu(); return; }
    menu.path = r.path;
    if (r.run) runMenu(r.run);
    else drawMenu();
    return;
  }
  const mod = ev.ctrlKey || ev.metaKey, key = ev.key.toLowerCase();
  if (mod && key === 's') { ev.preventDefault(); save(); return; }
  // 入力欄の中では、元に戻す・コピーなどはブラウザの元からの動きに任せる
  if (typingIn(ev.target) || !st.m) return;
  if ((ev.shiftKey && ev.key === 'F10') || ev.key === 'ContextMenu') { ev.preventDefault(); openMenuFromKeyboard(); return; }
  if (mod && key === 'z' && !ev.shiftKey) { ev.preventDefault(); restore(undo(hist)); return; }
  if (mod && (key === 'y' || (key === 'z' && ev.shiftKey))) { ev.preventDefault(); restore(redo(hist)); return; }
  if (mod && key === 'c') { ev.preventDefault(); copySelection(); return; }
  if (mod && key === 'v') { ev.preventDefault(); paste(); return; }
  if (mod && key === 'd') { ev.preventDefault(); duplicate(picks()); return; }
  if (ev.key === 'Delete' || ev.key === 'Backspace') { ev.preventDefault(); deleteSelection(); return; }
  if (ev.key === 'Escape' && st.picked.length > 1) { selectOne({ type: 'pipe' }); render(); }
});

// ---- 上の帯 ---------------------------------------------------------------

function fit(): void {
  const m = model();
  const rs = [...m.stages.map((s) => blockRect(m, s.id)), ...m.frames.map((f) => blockRect(m, f.id)), blockRect(m, END), blockRect(m, 'start')];
  const x0 = Math.min(...rs.map((r) => r.x)) - 30, y0 = Math.min(...rs.map((r) => r.y)) - 40;
  const x1 = Math.max(...rs.map((r) => r.x + r.w)) + 30, y1 = Math.max(...rs.map((r) => r.y + r.h)) + 90;
  const a = area.getBoundingClientRect();
  const z = Math.min(1.2, Math.max(0.3, Math.min(a.width / (x1 - x0), a.height / (y1 - y0))));
  st.view = { z, x: (a.width - (x1 - x0) * z) / 2 - x0 * z, y: (a.height - (y1 - y0) * z) / 2 - y0 * z };
  applyView();
}
function zoomBy(f: number): void {
  const a = area.getBoundingClientRect(), mx = a.width / 2, my = a.height / 2, z = Math.min(2, Math.max(0.3, st.view.z * f));
  st.view.x = mx - ((mx - st.view.x) * z) / st.view.z;
  st.view.y = my - ((my - st.view.y) * z) / st.view.z;
  st.view.z = z;
  st.viewMoved = true;
  applyView();
}
function arrange(): void {
  if (!st.m) return;
  autoLayout(model());
  changed('自動で並べた');
  render();
  fit();
  toast('並びの順に、左から右へ並べ直しました');
}
function save(): void {
  if (!st.m) return;
  ($('save') as HTMLButtonElement).disabled = true;
  savingSnap = snapNow();
  vscode.postMessage({ type: 'save', model: st.m });
}
$('zoom-in').addEventListener('click', () => zoomBy(1.2));
$('zoom-out').addEventListener('click', () => zoomBy(1 / 1.2));
$('fit').addEventListener('click', () => { if (st.m) { st.viewMoved = false; fit(); } });
$('arrange').addEventListener('click', arrange);
$('save').addEventListener('click', save);

// ---- 拡張とのやり取り ------------------------------------------------------------

/** 保存した版の日時（パネルの中だけで使う表示の書式） */
const when = (t: number): string => new Date(t).toLocaleString('ja-JP', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
window.addEventListener('message', (ev: MessageEvent) => {
  const msg = ev.data as {
    type?: string; model?: PipeModel; written?: string[]; errors?: string[]; message?: string;
    savedNames?: string[]; dirty?: boolean; list?: VersionEntry[]; id?: string; folder?: string;
  };
  if (msg.type === 'load' && msg.model) {
    st.m = msg.model;
    st.folder = typeof msg.folder === 'string' ? msg.folder : '';
    selectOne({ type: 'pipe' });
    st.viewMoved = false;
    st.savedNames = msg.savedNames ?? [];
    hist = createHistory(snapNow(), msg.dirty ? '保存していない下書きを開いた' : '開いたとき');
    // 下書きを開き直したときは、保存したときの形が分からないので、保存するまで印を付けたままにする
    savedSnap = msg.dirty ? '' : snapNow();
    $('pipe-path').textContent = `pipes/${st.folder}/`;
    syncDirty();
    render();
    requestAnimationFrame(fit);
    toast(msg.dirty ? '保存していない下書きを開きました。保存を押すとファイルに書きます' : 'ブロックの右のプラグを引っぱって、ほかのブロックの左のコンセントに差します');
  } else if (msg.type === 'saved') {
    savedSnap = savingSnap;
    st.savedNames = msg.savedNames ?? st.savedNames;
    ($('save') as HTMLButtonElement).disabled = false;
    syncDirty();
    const n = msg.errors?.length ?? 0;
    toast(n ? `保存しました（検査で ${n} 件の誤りがあります。流す前に直してください）` : '保存しました。検査にも通っています');
  } else if (msg.type === 'failed') {
    ($('save') as HTMLButtonElement).disabled = false;
    toast(`保存できませんでした：${msg.message ?? ''}`);
  } else if (msg.type === 'versions' && Array.isArray(msg.list)) {
    st.versions = msg.list;
    if (st.tab === 'history') renderPane();
  } else if (msg.type === 'version' && msg.model && st.m) {
    const v = st.versions.find((x) => x.id === msg.id);
    st.m = { ...msg.model, name: st.m.name };
    selectOne({ type: 'pipe' });
    changed(`保存した版（${v ? when(v.savedAt) : msg.id}${v?.draft ? '・下書き' : ''}）を読み込んだ`);
    render();
    fit();
    toast('保存した版を読み込みました。保存を押すまでファイルは書きません（Ctrl+Z で読み込む前に戻せます）');
  }
});
vscode.postMessage({ type: 'ready' });
