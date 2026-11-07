// 図の節 → 左の列の流れ図（SVG の文字列、純粋）。本線は上から下、戻りの矢印は右（確認 → 同じ段）と左（判定 → 実装）。
// 色は CSS（panelHtml.ts の STYLE）でクラスに付ける。ここでは形と位置だけを決める。
// 動いている段で段のログが目安の時間動かないとき（D0021）は、節と、その段へ入る流れる矢印に印の属性（data-quiet・data-stale-after）を持たせ、
// 節の 2 行目に「⚠ 更新なし」の文字を足す。パネルのスクリプトが is-stale を付けると、CSS が点線の枠にし、脈打ちと点の流れを止める。
// 並列の枠（D0063）は、枠の中の段の節を細い形にして横に並べ（3 つまで 1 行、4 つ目から次の行）、枠の線と名前の札で囲む。
// 枠の中の段の節は押してログを選べる（data-logpick）。枠があるときは、本線の位置を右へずらして図の幅を広げる（座標は常に図の中の絶対位置）。
import { checkChipText } from '../domain/pipeCheck.ts';
import { CHECK_NODE_PREFIX, NODE_STATUS_LABELS } from '../domain/pipelineView.ts';
import type { FrameView, NodeId, PipelineNode } from '../domain/pipelineView.ts';
import { formatDuration } from './duration.ts';
import { escapeHtml } from './escape.ts';
import { formatMilli } from './money.ts';
import { STALE_WORD, staleAttrs, staleTime } from './staleMark.ts';

type Shape = 'doc' | 'stage' | 'review' | 'verdict' | 'final' | 'check';

const REVIEW_PREFIX = 'review:';

/** 節の形は id で決まる（依頼メモ・確認・判定（開発フロー）・パイプの判定・完了。ほかは段）。 */
function shapeOf(id: NodeId): Shape {
  if (id === 'input') return 'doc';
  if (id === 'verdict') return 'verdict';
  if (id === 'final') return 'final';
  if (id.startsWith(CHECK_NODE_PREFIX)) return 'check';
  return id.startsWith(REVIEW_PREFIX) ? 'review' : 'stage';
}

const HEIGHTS: Readonly<Record<Shape, number>> = { doc: 30, stage: 50, review: 30, verdict: 46, final: 32, check: 46 };

const EXHAUSTED_WORD = '上限まで';

/** 判定の節の 2 行目の文字：やり直した回数と上限（「2 / 3 回」。上限が無ければ「2 回」）。検証がまだ無ければ null。 */
function checkCountText(node: PipelineNode): string | null {
  const c = node.check;
  if (c == null || c.retries === null) return null;
  return c.maxRetries === null ? `${c.retries} 回` : `${c.retries} / ${c.maxRetries} 回`;
}

// 段の節の上限の表示（D0051）。2 行目（y+38）の下に、金額の対・棒・言葉と「N 回目」の順に足す。
const BAR_W = 152; // 棒の枠の幅（節の幅 176 から左右の余白を引いた値）
const BAR_H = 6;
const BUDGET_WORDS: Readonly<Record<'near' | 'over' | 'stopped', string>> = {
  near: '上限に近い',
  over: '上限を超えた',
  stopped: '上限で止まった',
};
// 節の高さ：表示なし 50／金額の対と棒だけ 74／金額の対と棒と言葉（か「N 回目」）の行 88／言葉だけ（割合の無い「止まった」）64
const STAGE_H = { plain: 50, pair: 74, pairWord: 88, wordOnly: 64 } as const;

/** 節に出す言葉。余裕・状態なしには無い。 */
function budgetWord(node: PipelineNode): string | null {
  const b = node.budget;
  return b == null || b.state === 'ok' ? null : BUDGET_WORDS[b.state];
}

/** 「N 回目」の文字。1 回だけの段・状態なしには無い。 */
function nthText(node: PipelineNode): string | null {
  const b = node.budget;
  return b != null && b.runCount >= 2 ? `${b.nth} 回目` : null;
}

/** 金額の対（$0.42 / $1.00）。割合の無い「止まった」には無い。 */
function budgetPair(node: PipelineNode): string | null {
  const b = node.budget;
  return b != null && b.ratio !== null && b.costMilli !== null && b.limitMilli !== null
    ? `${formatMilli(b.costMilli)} / ${formatMilli(b.limitMilli)}`
    : null;
}

function heightOf(node: PipelineNode): number {
  if (shapeOf(node.id) !== 'stage' || node.budget == null) return HEIGHTS.stage;
  if (budgetPair(node) === null) return STAGE_H.wordOnly;
  return budgetWord(node) !== null || nthText(node) !== null ? STAGE_H.pairWord : STAGE_H.pair;
}

/** 上限の表示の SVG 部品（金額の対・棒・言葉・「N 回目」）。外から来た文字は出さない（数字と固定の言葉だけ）。left・right は節の左右の端。 */
function renderBudget(node: PipelineNode, y: number, left: number, right: number): string[] {
  const parts: string[] = [];
  const b = node.budget;
  if (b == null) return parts;
  const pair = budgetPair(node);
  const x = left + 12;
  let wordY = y + 54;
  if (pair !== null && b.ratio !== null) {
    const fill = Number((BAR_W * Math.min(Math.max(b.ratio, 0), 1)).toFixed(2));
    parts.push(`<text class="node-detail" x="${x}" y="${y + 53}">${escapeHtml(pair)}</text>`);
    parts.push(`<rect class="budget-track" x="${x}" y="${y + 59}" width="${BAR_W}" height="${BAR_H}" rx="2"/>`);
    parts.push(`<rect class="budget-fill" x="${x}" y="${y + 59}" width="${fill}" height="${BAR_H}" rx="2"/>`);
    wordY = y + 80;
  }
  const word = budgetWord(node);
  if (word !== null) parts.push(`<text class="budget-word" x="${x}" y="${wordY}">${escapeHtml(word)}</text>`);
  const nth = nthText(node);
  if (nth !== null) parts.push(`<text class="node-detail" x="${right - 10}" y="${wordY}" text-anchor="end">${escapeHtml(nth)}</text>`);
  return parts;
}

/** 節の <title> の足し書き：（費用 $0.90 / 上限 $1.00・上限に近い・1 回目）。出るものが無ければ空。 */
function budgetTitle(node: PipelineNode): string {
  const b = node.budget;
  if (b == null) return '';
  const items: string[] = [];
  if (b.ratio !== null && b.costMilli !== null && b.limitMilli !== null) {
    items.push(`費用 ${formatMilli(b.costMilli)} / 上限 ${formatMilli(b.limitMilli)}`);
  }
  const word = budgetWord(node);
  if (word !== null) items.push(word);
  const nth = nthText(node);
  if (nth !== null) items.push(nth);
  return items.length === 0 ? '' : `（${items.join('・')}）`;
}

const WIDTH = 320;
const CX = 150; // 本線の x（枠が無いとき）
const NODE_W = 176;
const REVIEW_W = 132;
const VERDICT_HALF_W = 62;
const GAP = 24;
const TOP = 8;
const LOOP_RIGHT_X = 266;
const LOOP_LEFT_X = 30;
const CHECK_LOOP_STEP = 6; // 判定の戻りの矢印が複数あるとき、通り道を左へずらす幅
const CHECK_LOOP_MIN_X = 10;

// 並列の枠（D0063）
const PER_ROW = 3; // 枠の中の 1 行の段の数
const MEMBER_W = 104; // 枠の中の節の幅
const MEMBER_GAP = 8;
const FRAME_PAD = 12;
const FRAME_TOP = 22; // 枠の上辺から最初の行まで（名前の札の分）
const ROW_GAP = 14;
const IN_GAP = 10; // 段と、その段の判定の節の間
const MEMBER_H = 46; // 枠の中の段の節の高さ
const MEMBER_LABEL_MAX = 8; // 枠の中の節の表示名を切る文字数
const TAB_LABEL_MAX = 16; // 枠の名前の札を切る文字数
const TAB_H = 20;
/** 枠が広いとき、本線を右へずらす基準（枠の幅の半分がこれを超えた分だけずらす）。 */
const FRAME_FIT_HALF_W = 106;

interface Placed {
  node: PipelineNode;
  shape: Shape;
  y: number; // 上端
  h: number;
  cx: number; // 中心の x
  w: number; // 段・判定の節の幅（ほかの形は halfWidth で決まる）
  compact: boolean; // 枠の中の細い節か
}

/** 枠の外形。 */
interface FrameBox {
  frame: FrameView;
  x: number;
  y: number;
  w: number;
  h: number;
  cx: number;
}

/** 本線に並ぶ単位：枠の外の節 1 つか、枠 1 つ（中の節は単位に数えない）。 */
type Unit = { kind: 'node'; p: Placed } | { kind: 'frame'; box: FrameBox; members: Placed[] };

/** 枠の中の 1 つ分：段の節と、あればその段の判定の節。 */
interface Member {
  stage: PipelineNode;
  check: PipelineNode | null;
}

function halfWidth(shape: Shape): number {
  if (shape === 'review' || shape === 'final' || shape === 'doc') return REVIEW_W / 2;
  if (shape === 'verdict') return VERDICT_HALF_W;
  return NODE_W / 2;
}

/** 枠の中の段を PER_ROW ずつの行にする。図に節が無い段は飛ばす。 */
function frameRows(frame: FrameView, byId: ReadonlyMap<NodeId, PipelineNode>): Member[][] {
  const members: Member[] = [];
  for (const name of frame.members) {
    const stage = byId.get(name);
    if (stage === undefined) continue;
    const checkId = `${CHECK_NODE_PREFIX}${name}`;
    members.push({ stage, check: frame.nodeIds.includes(checkId) ? (byId.get(checkId) ?? null) : null });
  }
  const rows: Member[][] = [];
  for (let i = 0; i < members.length; i += PER_ROW) rows.push(members.slice(i, i + PER_ROW));
  return rows;
}

const rowWidth = (k: number): number => k * MEMBER_W + (k - 1) * MEMBER_GAP;
const innerWidth = (rows: Member[][]): number => Math.max(...rows.map((r) => rowWidth(r.length)));

/** 枠を置く：枠の外形と、中の節の位置。y は枠の上端。 */
function layoutFrame(frame: FrameView, rows: Member[][], cx: number, y: number): { box: FrameBox; members: Placed[] } {
  const inner = innerWidth(rows);
  const x0 = cx - inner / 2;
  const members: Placed[] = [];
  let ry = y + FRAME_TOP;
  for (const row of rows) {
    let rowH = MEMBER_H;
    row.forEach((m, i) => {
      const mcx = x0 + i * (MEMBER_W + MEMBER_GAP) + MEMBER_W / 2;
      members.push({ node: m.stage, shape: 'stage', y: ry, h: MEMBER_H, cx: mcx, w: MEMBER_W, compact: true });
      if (m.check !== null) {
        members.push({ node: m.check, shape: 'check', y: ry + MEMBER_H + IN_GAP, h: HEIGHTS.check, cx: mcx, w: MEMBER_W, compact: true });
        rowH = Math.max(rowH, MEMBER_H + IN_GAP + HEIGHTS.check);
      }
    });
    ry += rowH + ROW_GAP;
  }
  const w = inner + 2 * FRAME_PAD;
  return { box: { frame, x: cx - w / 2, y, w, h: ry - ROW_GAP - y + FRAME_PAD, cx }, members };
}

interface Layout {
  placed: Placed[];
  units: Unit[];
  dx: number;
  height: number;
}

function place(nodes: PipelineNode[], frames: readonly FrameView[]): Layout {
  const byId = new Map(nodes.map((n) => [n.id, n] as const));
  // 枠ごとの行。節がひとつも無い枠は描かない。1 つの節は 1 つの枠にだけ入れる
  const owner = new Map<NodeId, number>();
  const laid: { frame: FrameView; rows: Member[][]; done: boolean }[] = [];
  for (const frame of frames) {
    const rows = frameRows(frame, byId).map((row) => row.filter((m) => !owner.has(m.stage.id)));
    const kept = rows.filter((r) => r.length > 0);
    if (kept.length === 0) continue;
    for (const row of kept) for (const m of row) for (const n of [m.stage, m.check]) if (n !== null) owner.set(n.id, laid.length);
    laid.push({ frame, rows: kept, done: false });
  }
  // 広い枠があるときだけ本線を右へずらし、図の幅を広げる
  const widest = laid.reduce((max, l) => Math.max(max, innerWidth(l.rows) + 2 * FRAME_PAD), 0);
  const dx = Math.max(0, widest / 2 - FRAME_FIT_HALF_W);
  const cx = CX + dx;

  const byNode = new Map<NodeId, Placed>();
  const units: Unit[] = [];
  let y = TOP;
  let bottom = TOP;
  for (const node of nodes) {
    const fi = owner.get(node.id);
    if (fi === undefined) {
      const shape = shapeOf(node.id);
      const h = shape === 'stage' ? heightOf(node) : HEIGHTS[shape];
      const p: Placed = { node, shape, y, h, cx, w: shape === 'stage' || shape === 'check' ? NODE_W : halfWidth(shape) * 2, compact: false };
      byNode.set(node.id, p);
      units.push({ kind: 'node', p });
      bottom = y + h;
      y += h + GAP;
      continue;
    }
    const entry = laid[fi];
    if (entry === undefined || entry.done) continue;
    entry.done = true;
    const { box, members } = layoutFrame(entry.frame, entry.rows, cx, y);
    for (const m of members) byNode.set(m.node.id, m);
    units.push({ kind: 'frame', box, members });
    bottom = y + box.h;
    y += box.h + GAP;
  }
  const placed = nodes.flatMap((n) => {
    const p = byNode.get(n.id);
    return p === undefined ? [] : [p];
  });
  return { placed, units, dx, height: units.length === 0 ? TOP * 2 : bottom + TOP };
}

const mid = (p: Placed) => p.y + p.h / 2;
const WAITING_LABEL = '確認待ち';

const leftOf = (p: Placed): number => p.cx - p.w / 2;
const rightOf = (p: Placed): number => p.cx + p.w / 2;

function outline(p: Placed): string {
  const { shape, y, h, cx } = p;
  if (shape === 'verdict') {
    const m = mid(p);
    return `<path class="shape" d="M${cx},${y} L${cx + VERDICT_HALF_W},${m} L${cx},${y + h} L${cx - VERDICT_HALF_W},${m} Z"/>`;
  }
  const hw = shape === 'stage' || shape === 'check' ? p.w / 2 : halfWidth(shape);
  const rx = shape === 'stage' || shape === 'check' ? 6 : shape === 'doc' ? 3 : h / 2;
  const cls = shape === 'doc' ? 'shape is-doc' : 'shape';
  return `<rect class="${cls}" x="${cx - hw}" y="${y}" width="${hw * 2}" height="${h}" rx="${rx}"/>`;
}

const MARKS: Readonly<Record<PipelineNode['status'], string>> = {
  pending: '',
  running: '●',
  done: '✓',
  failed: '✗',
  skipped: '–',
};

/** 節に対応する矢印の id（renderLoops の data-loop と同じ値）。 */
function loopIdOf(id: NodeId): string {
  if (id.startsWith(CHECK_NODE_PREFIX)) return id;
  return id.startsWith(REVIEW_PREFIX) ? `revise:${id.slice(REVIEW_PREFIX.length)}` : 'send-back';
}

/** 選べる節の印（キーボードで届き、押した状態を伝える）。 */
function pickAttrs(id: NodeId): string {
  const e = escapeHtml(id);
  return ` data-reasons="${e}" data-reasons-loop="${escapeHtml(loopIdOf(id))}" tabindex="0" role="button" aria-pressed="false"`;
}

/** 枠の中の段の節の印：押すと右の欄がその段のログに替わる（理由の選びとは別）。 */
function logPickAttrs(id: NodeId): string {
  return ` data-logpick="${escapeHtml(id)}" tabindex="0" role="button" aria-pressed="false"`;
}

/** 判定の節の <title> の足し書き：（やり直し 1 / 3 回・上限まで）。出るものが無ければ空。 */
function checkNodeTitle(node: PipelineNode): string {
  const items: string[] = [];
  const count = checkCountText(node);
  if (count !== null) items.push(`やり直し ${count}`);
  if (node.check?.exhausted === true) items.push(EXHAUSTED_WORD);
  return items.length === 0 ? '' : `（${items.join('・')}）`;
}

/** 文字数（コードポイント）で切る。長ければ末尾に「…」。 */
function clip(text: string, max: number): string {
  const chars = [...text];
  return chars.length <= max ? text : `${chars.slice(0, max).join('')}…`;
}

/** 枠の中の細い節：1 行目は表示名と状態の印、2 行目は経過／時間（と「N 回目」）。判定の節は札と印、回数と「上限まで」。 */
function compactParts(p: Placed, staleAfterSec: number | null): { parts: string[]; stale: string } {
  const { node, shape, y } = p;
  const left = leftOf(p) + 8;
  const right = rightOf(p) - 8;
  const parts = [outline(p)];
  const mark = MARKS[node.status];
  let stale = '';
  if (shape === 'check') {
    const chip = node.check == null ? node.label : checkChipText(node.check.kind);
    parts.push(`<text class="node-label is-strong" x="${left}" y="${y + 19}">${escapeHtml(chip)}</text>`);
    parts.push(`<text class="node-status" x="${right}" y="${y + 19}" text-anchor="end">${escapeHtml(mark)}</text>`);
    const count = checkCountText(node);
    if (count !== null) parts.push(`<text class="node-detail" x="${left}" y="${y + 36}">${escapeHtml(count)}</text>`);
    if (node.check?.exhausted === true) {
      parts.push(`<text class="check-word" x="${right}" y="${y + 36}" text-anchor="end">${EXHAUSTED_WORD}</text>`);
    }
    return { parts, stale };
  }
  stale = node.status === 'running' ? staleAttrs(node.quietSec, staleAfterSec) : '';
  parts.push(`<text class="node-label is-strong" x="${left}" y="${y + 19}">${escapeHtml(clip(node.label, MEMBER_LABEL_MAX))}</text>`);
  parts.push(`<text class="node-status" x="${right}" y="${y + 19}" text-anchor="end">${escapeHtml(mark)}</text>`);
  const nth = nthText(node);
  if (node.runningSec != null) {
    const sec = Math.floor(node.runningSec);
    parts.push(`<text class="node-detail" x="${left}" y="${y + 36}">経過 <tspan class="elapsed" data-elapsed="${sec}">${formatDuration(sec)}</tspan></text>`);
  } else if (node.metrics) {
    parts.push(`<text class="node-detail" x="${left}" y="${y + 36}">${escapeHtml(formatDuration(node.metrics.durationSec))}</text>`);
  }
  if (stale !== '') {
    parts.push(`<text class="node-stale" x="${left}" y="${y + 36}">${STALE_WORD} ${staleTime(node.quietSec, 'tspan')}</text>`);
  }
  if (nth !== null) parts.push(`<text class="node-detail" x="${right}" y="${y + 36}" text-anchor="end">${escapeHtml(nth)}</text>`);
  return { parts, stale };
}

function renderNode(p: Placed, pickable: ReadonlySet<NodeId>, logPickable: ReadonlySet<NodeId>, staleAfterSec: number | null): string {
  const { node, shape, y, h, cx } = p;
  const status = NODE_STATUS_LABELS[node.status];
  const LEFT = leftOf(p);
  const RIGHT = rightOf(p);
  let parts: string[];
  let stale = '';
  if (p.compact) {
    ({ parts, stale } = compactParts(p, staleAfterSec));
  } else {
    parts = [outline(p)];
    // 動いている段の節で、最後の更新からの秒と目安がそろうときだけ、印の属性と印の文字を足す（目安なしなら今までの図のまま）
    stale = shape === 'stage' && node.status === 'running' ? staleAttrs(node.quietSec, staleAfterSec) : '';
  }
  if (p.compact) {
    // 細い節の部品は compactParts で作ってある
  } else if (shape === 'stage') {
    parts.push(`<text class="node-label is-strong" x="${LEFT + 12}" y="${y + 20}">${escapeHtml(node.label)}</text>`);
    parts.push(`<text class="node-status" x="${RIGHT - 10}" y="${y + 20}" text-anchor="end">${escapeHtml(`${MARKS[node.status]} ${status}`.trim())}</text>`);
    const m = node.metrics;
    if (node.runningSec != null) {
      // 動いている段：2行目は経過だけ（前の回の詳細は幅が足りない。回ごとは右の欄の「時間」）。基準の秒はパネルのスクリプトが数え上げる
      const sec = Math.floor(node.runningSec);
      parts.push(
        `<text class="node-detail" x="${LEFT + 12}" y="${y + 38}">経過 <tspan class="elapsed" data-elapsed="${sec}">${formatDuration(sec)}</tspan></text>`,
      );
    } else {
      // 費用が null（使用量が取れない記録）のときは、ターン数も 0 になるので、$ もターンも外して時間だけにする
      const detail = !m
        ? ''
        : m.costUsd == null
          ? formatDuration(m.durationSec)
          : `${m.numTurns} ターン・$${m.costUsd.toFixed(3)}・${formatDuration(m.durationSec)}`;
      if (detail) parts.push(`<text class="node-detail" x="${LEFT + 12}" y="${y + 38}">${escapeHtml(detail)}</text>`);
    }
    // 印の文字は 2 行目の同じ位置に置く。is-stale が付くまで CSS で隠し、付くと経過の文字と入れ替わる
    if (stale !== '') {
      parts.push(`<text class="node-stale" x="${LEFT + 12}" y="${y + 38}">${STALE_WORD} ${staleTime(node.quietSec, 'tspan')}</text>`);
    }
    parts.push(...renderBudget(node, y, LEFT, RIGHT));
  } else if (shape === 'check') {
    // 1 行目：札（作業台と同じ文字）と状態。2 行目：やり直した回数と上限（上限まで落ちたら言葉も）。数字と固定の言葉だけ
    const chip = node.check == null ? node.label : checkChipText(node.check.kind);
    parts.push(`<text class="node-label is-strong" x="${LEFT + 12}" y="${y + 20}">${escapeHtml(chip)}</text>`);
    parts.push(`<text class="node-status" x="${RIGHT - 10}" y="${y + 20}" text-anchor="end">${escapeHtml(`${MARKS[node.status]} ${status}`.trim())}</text>`);
    const count = checkCountText(node);
    if (count !== null) parts.push(`<text class="node-detail" x="${LEFT + 12}" y="${y + 38}">${escapeHtml(count)}</text>`);
    if (node.check?.exhausted === true) {
      parts.push(`<text class="check-word" x="${RIGHT - 10}" y="${y + 38}" text-anchor="end">${EXHAUSTED_WORD}</text>`);
    }
  } else if (shape === 'verdict') {
    parts.push(`<text class="node-label" x="${cx}" y="${mid(p) + 4}" text-anchor="middle">${escapeHtml(node.label)}</text>`);
    parts.push(`<text class="node-status" x="${cx + VERDICT_HALF_W + 8}" y="${mid(p) + 4}">${escapeHtml(`${MARKS[node.status]} ${status}`.trim())}</text>`);
  } else {
    const hw = halfWidth(shape);
    const strong = shape === 'final' ? ' is-strong' : '';
    // 確認待ちの確認の節：状態の文字を「確認待ち」にし、節の左に待ち時間を置く
    const waitingSec = node.waitingSec ?? null;
    const shown = waitingSec !== null ? `${MARKS[node.status]} ${WAITING_LABEL}` : `${MARKS[node.status]} ${status}`;
    parts.push(`<text class="node-label${strong}" x="${cx - hw + 12}" y="${y + h / 2 + 4}">${escapeHtml(node.label)}</text>`);
    parts.push(`<text class="node-status" x="${cx + hw - 10}" y="${y + h / 2 + 4}" text-anchor="end">${escapeHtml(shown.trim())}</text>`);
    if (waitingSec !== null) {
      const sec = Math.floor(waitingSec);
      parts.push(
        `<text class="node-wait" x="${cx - hw - 6}" y="${y + h / 2 + 4}" text-anchor="end" data-elapsed="${sec}">${formatDuration(sec)}</text>`,
      );
    }
  }
  const pick = logPickable.has(node.id) ? logPickAttrs(node.id) : pickable.has(node.id) ? pickAttrs(node.id) : '';
  const waitingMark = node.waitingSec != null ? ' is-waiting' : '';
  const budgetMark = shape === 'stage' && node.budget != null ? ` is-budget-${node.budget.state}` : '';
  const checkTitle = shape === 'check' ? checkNodeTitle(node) : '';
  const title = `${node.label}：${status}${shape === 'stage' ? budgetTitle(node) : ''}${checkTitle}`;
  return `<g class="node is-${node.status}${waitingMark}${budgetMark}" data-node="${escapeHtml(node.id)}"${stale}${pick}><title>${escapeHtml(title)}</title>${parts.join('')}</g>`;
}

/** 名前の札の幅：文字数から見積もる（ASCII は 7px、それ以外は 11px、左右に 10px ずつ）。 */
function tabWidth(text: string): number {
  return [...text].reduce((sum, ch) => sum + ((ch.codePointAt(0) ?? 0) < 0x80 ? 7 : 11), 20);
}

/** 枠の線と名前の札。外から来た名前は escapeHtml を 1 回だけ通す。押せない。 */
function renderFrame(box: FrameBox): string {
  const { frame, x, y, w, h } = box;
  // 札は枠の中に収める（長い名前は札の幅に合うまで切る）
  let max = TAB_LABEL_MAX;
  let label = clip(frame.name, max);
  while (max > 1 && tabWidth(label) > w - 36) label = clip(frame.name, --max);
  const tw = Math.min(tabWidth(label), Math.max(40, w - 36));
  const tx = x + 18;
  const ty = y - TAB_H / 2;
  const status = NODE_STATUS_LABELS[frame.status];
  return (
    `<g class="frame is-${frame.status}" data-frame="${escapeHtml(frame.name)}"><title>${escapeHtml(`枠 ${frame.name}：${status}`)}</title>` +
    `<rect class="frame-box" x="${x}" y="${y}" width="${w}" height="${h}" rx="24"/>` +
    `<rect class="frame-tab" x="${tx}" y="${ty}" width="${tw}" height="${TAB_H}" rx="${TAB_H / 2}"/>` +
    `<text class="frame-tab-text" x="${tx + 10}" y="${ty + 14}">${escapeHtml(label)}</text></g>`
  );
}

const unitTop = (u: Unit): number => (u.kind === 'node' ? u.p.y : u.box.y);
const unitBottom = (u: Unit): number => (u.kind === 'node' ? u.p.y + u.p.h : u.box.y + u.box.h);
/** 単位の中で動いている段の節（枠は中の段のうち経過が出ているもの）。無ければ null。 */
function runningNodeOf(u: Unit): PipelineNode | null {
  if (u.kind === 'node') return u.p.node.runningSec != null ? u.p.node : null;
  return u.members.find((m) => m.shape === 'stage' && m.node.runningSec != null)?.node ?? null;
}

function renderEdges(layout: Layout, staleAfterSec: number | null): string {
  const { units, placed, dx } = layout;
  const cx = CX + dx;
  const edges: string[] = [];
  for (let i = 1; i < units.length; i++) {
    const from = units[i - 1]!;
    const to = units[i]!;
    // 動いている段（枠なら中の動いている段）へ入る矢印にだけ、流れる点の印を付ける（始まりの時刻が読めて経過が出ているとき）
    const running = runningNodeOf(to);
    const flowing = running !== null;
    // 矢印は節の外の別の要素なので、節の is-stale は届かない。流れる点を止めるため、節と同じ値の属性を自分で持つ
    const stale = flowing ? staleAttrs(running.quietSec, staleAfterSec) : '';
    edges.push(`<line class="edge${flowing ? ' is-flowing' : ''}"${stale} x1="${cx}" y1="${unitBottom(from)}" x2="${cx}" y2="${unitTop(to) - 2}" marker-end="url(#mk-edge)"/>`);
  }
  // 枠の中：段 → その段の判定の節の短い矢印（段どうしには引かない）
  for (const u of units) {
    if (u.kind !== 'frame') continue;
    for (const c of u.members.filter((m) => m.shape === 'check')) {
      const stage = u.members.find((m) => m.shape === 'stage' && m.cx === c.cx && m.y < c.y && m.node.id === c.node.id.slice(CHECK_NODE_PREFIX.length));
      if (stage === undefined) continue;
      edges.push(`<line class="edge" x1="${c.cx}" y1="${stage.y + stage.h}" x2="${c.cx}" y2="${c.y - 2}" marker-end="url(#mk-edge)"/>`);
    }
  }
  const verdict = placed.find((p) => p.node.id === 'verdict');
  const label = verdict ? `<text class="edge-label" x="${verdict.cx + 8}" y="${verdict.y + verdict.h + GAP / 2 + 4}">合格</text>` : '';
  return edges.join('') + label;
}

function loop(id: string, count: number, d: string, label: string, labelAttrs: string, title: string): string {
  const hot = count > 0;
  const cls = hot ? 'loop is-hot' : 'loop';
  const marker = hot ? 'mk-hot' : 'mk-loop';
  // data-count は戻った回数。パネルのスクリプトが前の描き直しと比べ、増えたときに一度だけ光らせる
  return `<g class="${cls}" data-loop="${id}" data-count="${count}"><title>${escapeHtml(title)}</title><path class="loop-path" d="${d}" marker-end="url(#${marker})"/><text class="loop-label" ${labelAttrs}>${escapeHtml(label)}</text></g>`;
}

function renderLoops(placed: Placed[], dx: number): string {
  const at = (id: NodeId) => placed.find((p) => p.node.id === id);
  const loopRightX = LOOP_RIGHT_X + dx;
  const loopLeftX = LOOP_LEFT_X + dx;
  const loops: string[] = [];
  for (const review of placed.filter((p) => p.shape === 'review')) {
    const stage = review.node.id.slice(REVIEW_PREFIX.length);
    const target = at(stage);
    if (!target) continue;
    const n = review.node.reviseCount ?? 0;
    const y1 = mid(review);
    const y2 = mid(target);
    const d = `M${review.cx + REVIEW_W / 2},${y1} L${loopRightX},${y1} L${loopRightX},${y2} L${rightOf(target) + 2},${y2}`;
    const label = n > 0 ? `修正 ${n}回` : '修正';
    loops.push(loop(`revise:${stage}`, n, d, label, `x="${loopRightX + 5}" y="${(y1 + y2) / 2 + 4}"`, `修正の依頼 ${n} 回`));
  }
  const verdict = at('verdict');
  const implement = at('implement');
  if (verdict && implement) {
    const n = implement.node.sendBackCount ?? 0;
    const y1 = mid(verdict);
    const y2 = mid(implement);
    const d = `M${verdict.cx - VERDICT_HALF_W},${y1} L${loopLeftX},${y1} L${loopLeftX},${y2} L${leftOf(implement) - 2},${y2}`;
    const label = n > 0 ? `差し戻し ${n}回` : '不合格：差し戻し';
    const ym = (y1 + y2) / 2;
    loops.push(
      loop('send-back', n, d, label, `x="${loopLeftX - 8}" y="${ym}" text-anchor="middle" transform="rotate(-90 ${loopLeftX - 8} ${ym})"`, `差し戻し ${n} 回`),
    );
  }
  loops.push(...renderCheckLoops(placed, dx));
  return loops.join('');
}

/** 前の段へ戻す判定の戻りの矢印：判定の節の左から、左の通り道を通って、戻り先の段の節へ。自分をやり直す判定は描かない。 */
function renderCheckLoops(placed: Placed[], dx: number): string[] {
  const loops: string[] = [];
  let k = 0;
  for (const p of placed.filter((q) => q.shape === 'check')) {
    const c = p.node.check;
    const target = c?.onFail == null ? undefined : placed.find((q) => q.node.id === c.onFail);
    if (c == null || target === undefined) continue;
    const x = Math.max(CHECK_LOOP_MIN_X, LOOP_LEFT_X - k * CHECK_LOOP_STEP) + dx;
    const n = c.retries ?? 0;
    const y1 = mid(p);
    const y2 = mid(target);
    const d = `M${leftOf(p)},${y1} L${x},${y1} L${x},${y2} L${leftOf(target) - 2},${y2}`;
    // 文字が重ならないよう、ラベルは最初の 1 本だけ（ほかは <title> で読める）
    const label = k === 0 && n > 0 ? `戻し ${n}回` : '';
    const ym = (y1 + y2) / 2;
    const labelAttrs = `x="${x - 8}" y="${ym}" text-anchor="middle" transform="rotate(-90 ${x - 8} ${ym})"`;
    loops.push(loop(p.node.id, n, d, label, labelAttrs, `${target.node.label}へ戻す ${n} 回`));
    k += 1;
  }
  return loops;
}

const DEFS = `<defs>
<marker id="mk-edge" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="head" d="M0,0 L10,5 L0,10 z"/></marker>
<marker id="mk-loop" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="head" d="M0,0 L10,5 L0,10 z"/></marker>
<marker id="mk-hot" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="head is-hot" d="M0,0 L10,5 L0,10 z"/></marker>
<marker id="mk-pick" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="head is-pick" d="M0,0 L10,5 L0,10 z"/></marker>
</defs>`;

/**
 * 節（開発フローは NODE_ORDER の11個、パイプは段の並び）を、縦の流れ図にする。
 * pickable は理由を持つ（押して選べる）節の id。空なら印を付けない。
 * staleAfterSec は「止まっているかも」の目安の秒（D0021）。null なら更新なしの印は出さない。
 * frames は並列の枠（PipelineView.frames。D0063）。省く・空なら枠なしの今までの図。枠の中の段の節は押してログを選べる印（data-logpick）を持つ。
 */
export function renderFlowSvg(
  nodes: PipelineNode[],
  pickable: ReadonlySet<NodeId> = new Set(),
  staleAfterSec: number | null = null,
  frames: readonly FrameView[] = [],
): string {
  const layout = place(nodes, frames);
  const { placed, units, dx, height } = layout;
  // 枠の中の段の節（図に出たもの）だけ、ログを選ぶ印を付ける
  const logPickable = new Set<NodeId>(
    units.flatMap((u) => (u.kind === 'frame' ? u.members.filter((m) => m.shape === 'stage').map((m) => m.node.id) : [])),
  );
  // role="img" の中身は読み上げの対象から外れるので、押せる節があるときは group にする
  const role = placed.some((p) => pickable.has(p.node.id) || logPickable.has(p.node.id)) ? 'group' : 'img';
  // 近い・超えた・止まった節だけ、言葉を足す（余裕と状態なしは今のまま）。枠は中の最初の節の前に差し込む
  const frameAt = new Map<NodeId, FrameView>();
  for (const u of units) {
    const first = u.kind === 'frame' ? u.members[0] : undefined;
    if (u.kind === 'frame' && first !== undefined) frameAt.set(first.node.id, u.box.frame);
  }
  const summary = nodes
    .map((n) => {
      const word = shapeOf(n.id) === 'stage' ? budgetWord(n) : null;
      const frame = frameAt.get(n.id);
      const head = frame === undefined ? '' : `枠 ${frame.name} ${NODE_STATUS_LABELS[frame.status]}、`;
      return `${head}${n.label} ${NODE_STATUS_LABELS[n.status]}${word === null ? '' : `（${word}）`}`;
    })
    .join('、');
  const boxes = units.map((u) => (u.kind === 'frame' ? renderFrame(u.box) : '')).join('');
  // 枠は節より前に描き、節が上に重なる
  return `<svg class="flow" viewBox="0 0 ${WIDTH + 2 * dx} ${height}" role="${role}" aria-label="${escapeHtml(`パイプラインの図：${summary}`)}">${DEFS}${boxes}${renderEdges(layout, staleAfterSec)}${renderLoops(placed, dx)}${placed.map((p) => renderNode(p, pickable, logPickable, staleAfterSec)).join('')}</svg>`;
}
