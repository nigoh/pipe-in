// 図の節 → 左の列の流れ図（SVG の文字列、純粋）。本線は上から下、戻りの矢印は右（確認 → 同じ段）と左（判定 → 実装）。
// 色は CSS（panelHtml.ts の STYLE）でクラスに付ける。ここでは形と位置だけを決める。
import { NODE_STATUS_LABELS } from '../domain/pipelineView.ts';
import type { NodeId, PipelineNode } from '../domain/pipelineView.ts';
import { formatDuration } from './duration.ts';
import { escapeHtml } from './escape.ts';

type Shape = 'doc' | 'stage' | 'review' | 'verdict' | 'final';

const REVIEW_PREFIX = 'review:';

/** 節の形は id で決まる（依頼メモ・確認・判定・完了。ほかは段）。 */
function shapeOf(id: NodeId): Shape {
  if (id === 'input') return 'doc';
  if (id === 'verdict') return 'verdict';
  if (id === 'final') return 'final';
  return id.startsWith(REVIEW_PREFIX) ? 'review' : 'stage';
}

const HEIGHTS: Readonly<Record<Shape, number>> = { doc: 30, stage: 50, review: 30, verdict: 46, final: 32 };

const WIDTH = 320;
const CX = 150; // 本線の x
const NODE_W = 176;
const LEFT = CX - NODE_W / 2; // 62
const RIGHT = CX + NODE_W / 2; // 238
const REVIEW_W = 132;
const VERDICT_HALF_W = 62;
const GAP = 24;
const TOP = 8;
const LOOP_RIGHT_X = 266;
const LOOP_LEFT_X = 30;

interface Placed {
  node: PipelineNode;
  shape: Shape;
  y: number; // 上端
  h: number;
}

function place(nodes: PipelineNode[]): Placed[] {
  let y = TOP;
  return nodes.map((node) => {
    const shape = shapeOf(node.id);
    const h = HEIGHTS[shape];
    const placed = { node, shape, y, h };
    y += h + GAP;
    return placed;
  });
}

const mid = (p: Placed) => p.y + p.h / 2;
const WAITING_LABEL = '確認待ち';

function halfWidth(shape: Shape): number {
  if (shape === 'review' || shape === 'final' || shape === 'doc') return REVIEW_W / 2;
  if (shape === 'verdict') return VERDICT_HALF_W;
  return NODE_W / 2;
}

function outline(p: Placed): string {
  const { shape, y, h } = p;
  if (shape === 'verdict') {
    const m = mid(p);
    return `<path class="shape" d="M${CX},${y} L${CX + VERDICT_HALF_W},${m} L${CX},${y + h} L${CX - VERDICT_HALF_W},${m} Z"/>`;
  }
  const hw = halfWidth(shape);
  const rx = shape === 'stage' ? 6 : shape === 'doc' ? 3 : h / 2;
  const cls = shape === 'doc' ? 'shape is-doc' : 'shape';
  return `<rect class="${cls}" x="${CX - hw}" y="${y}" width="${hw * 2}" height="${h}" rx="${rx}"/>`;
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
  return id.startsWith(REVIEW_PREFIX) ? `revise:${id.slice(REVIEW_PREFIX.length)}` : 'send-back';
}

/** 選べる節の印（キーボードで届き、押した状態を伝える）。 */
function pickAttrs(id: NodeId): string {
  const e = escapeHtml(id);
  return ` data-reasons="${e}" data-reasons-loop="${escapeHtml(loopIdOf(id))}" tabindex="0" role="button" aria-pressed="false"`;
}

function renderNode(p: Placed, pickable: ReadonlySet<NodeId>): string {
  const { node, shape, y, h } = p;
  const status = NODE_STATUS_LABELS[node.status];
  const parts = [outline(p)];
  if (shape === 'stage') {
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
      const detail = m ? `${m.numTurns} ターン・$${m.costUsd.toFixed(3)}・${formatDuration(m.durationSec)}` : '';
      if (detail) parts.push(`<text class="node-detail" x="${LEFT + 12}" y="${y + 38}">${escapeHtml(detail)}</text>`);
    }
  } else if (shape === 'verdict') {
    parts.push(`<text class="node-label" x="${CX}" y="${mid(p) + 4}" text-anchor="middle">${escapeHtml(node.label)}</text>`);
    parts.push(`<text class="node-status" x="${CX + VERDICT_HALF_W + 8}" y="${mid(p) + 4}">${escapeHtml(`${MARKS[node.status]} ${status}`.trim())}</text>`);
  } else {
    const hw = halfWidth(shape);
    const strong = shape === 'final' ? ' is-strong' : '';
    // 確認待ちの確認の節：状態の文字を「確認待ち」にし、節の左に待ち時間を置く
    const waitingSec = node.waitingSec ?? null;
    const shown = waitingSec !== null ? `${MARKS[node.status]} ${WAITING_LABEL}` : `${MARKS[node.status]} ${status}`;
    parts.push(`<text class="node-label${strong}" x="${CX - hw + 12}" y="${y + h / 2 + 4}">${escapeHtml(node.label)}</text>`);
    parts.push(`<text class="node-status" x="${CX + hw - 10}" y="${y + h / 2 + 4}" text-anchor="end">${escapeHtml(shown.trim())}</text>`);
    if (waitingSec !== null) {
      const sec = Math.floor(waitingSec);
      parts.push(
        `<text class="node-wait" x="${CX - hw - 6}" y="${y + h / 2 + 4}" text-anchor="end" data-elapsed="${sec}">${formatDuration(sec)}</text>`,
      );
    }
  }
  const pick = pickable.has(node.id) ? pickAttrs(node.id) : '';
  const waitingMark = node.waitingSec != null ? ' is-waiting' : '';
  return `<g class="node is-${node.status}${waitingMark}" data-node="${escapeHtml(node.id)}"${pick}><title>${escapeHtml(`${node.label}：${status}`)}</title>${parts.join('')}</g>`;
}

function renderEdges(placed: Placed[]): string {
  const edges: string[] = [];
  for (let i = 1; i < placed.length; i++) {
    const from = placed[i - 1];
    const to = placed[i];
    // 動いている段へ入る矢印にだけ、流れる点の印を付ける（始まりの時刻が読めて経過が出ているとき）
    const flowing = to.node.runningSec != null ? ' is-flowing' : '';
    edges.push(`<line class="edge${flowing}" x1="${CX}" y1="${from.y + from.h}" x2="${CX}" y2="${to.y - 2}" marker-end="url(#mk-edge)"/>`);
  }
  const verdict = placed.find((p) => p.node.id === 'verdict');
  const label = verdict ? `<text class="edge-label" x="${CX + 8}" y="${verdict.y + verdict.h + GAP / 2 + 4}">合格</text>` : '';
  return edges.join('') + label;
}

function loop(id: string, count: number, d: string, label: string, labelAttrs: string, title: string): string {
  const hot = count > 0;
  const cls = hot ? 'loop is-hot' : 'loop';
  const marker = hot ? 'mk-hot' : 'mk-loop';
  // data-count は戻った回数。パネルのスクリプトが前の描き直しと比べ、増えたときに一度だけ光らせる
  return `<g class="${cls}" data-loop="${id}" data-count="${count}"><title>${escapeHtml(title)}</title><path class="loop-path" d="${d}" marker-end="url(#${marker})"/><text class="loop-label" ${labelAttrs}>${escapeHtml(label)}</text></g>`;
}

function renderLoops(placed: Placed[]): string {
  const at = (id: NodeId) => placed.find((p) => p.node.id === id);
  const loops: string[] = [];
  for (const review of placed.filter((p) => p.shape === 'review')) {
    const stage = review.node.id.slice(REVIEW_PREFIX.length);
    const target = at(stage);
    if (!target) continue;
    const n = review.node.reviseCount ?? 0;
    const y1 = mid(review);
    const y2 = mid(target);
    const d = `M${CX + REVIEW_W / 2},${y1} L${LOOP_RIGHT_X},${y1} L${LOOP_RIGHT_X},${y2} L${RIGHT + 2},${y2}`;
    const label = n > 0 ? `修正 ${n}回` : '修正';
    loops.push(loop(`revise:${stage}`, n, d, label, `x="${LOOP_RIGHT_X + 5}" y="${(y1 + y2) / 2 + 4}"`, `修正の依頼 ${n} 回`));
  }
  const verdict = at('verdict');
  const implement = at('implement');
  if (verdict && implement) {
    const n = implement.node.sendBackCount ?? 0;
    const y1 = mid(verdict);
    const y2 = mid(implement);
    const d = `M${CX - VERDICT_HALF_W},${y1} L${LOOP_LEFT_X},${y1} L${LOOP_LEFT_X},${y2} L${LEFT - 2},${y2}`;
    const label = n > 0 ? `差し戻し ${n}回` : '不合格：差し戻し';
    const ym = (y1 + y2) / 2;
    loops.push(
      loop('send-back', n, d, label, `x="${LOOP_LEFT_X - 8}" y="${ym}" text-anchor="middle" transform="rotate(-90 ${LOOP_LEFT_X - 8} ${ym})"`, `差し戻し ${n} 回`),
    );
  }
  return loops.join('');
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
 */
export function renderFlowSvg(nodes: PipelineNode[], pickable: ReadonlySet<NodeId> = new Set()): string {
  const placed = place(nodes);
  // role="img" の中身は読み上げの対象から外れるので、押せる節があるときは group にする
  const role = placed.some((p) => pickable.has(p.node.id)) ? 'group' : 'img';
  const last = placed.at(-1);
  const height = last ? last.y + last.h + TOP : TOP * 2;
  const summary = nodes.map((n) => `${n.label} ${NODE_STATUS_LABELS[n.status]}`).join('、');
  return `<svg class="flow" viewBox="0 0 ${WIDTH} ${height}" role="${role}" aria-label="${escapeHtml(`パイプラインの図：${summary}`)}">${DEFS}${renderEdges(placed)}${renderLoops(placed)}${placed.map((p) => renderNode(p, pickable)).join('')}</svg>`;
}
