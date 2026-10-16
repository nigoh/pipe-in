// 図の節 → 左の列の流れ図（SVG の文字列、純粋）。本線は上から下、戻りの矢印は右（確認 → 同じ段）と左（判定 → 実装）。
// 色は CSS（panelHtml.ts の STYLE）でクラスに付ける。ここでは形と位置だけを決める。
import { NODE_STATUS_LABELS } from '../domain/pipelineView.ts';
import type { NodeId, PipelineNode } from '../domain/pipelineView.ts';
import { escapeHtml } from './escape.ts';

type Shape = 'doc' | 'stage' | 'review' | 'verdict' | 'final';

const SHAPES: Readonly<Record<NodeId, Shape>> = {
  input: 'doc',
  requirements: 'stage',
  'review:requirements': 'review',
  design: 'stage',
  'review:design': 'review',
  red: 'stage',
  'review:red': 'review',
  implement: 'stage',
  test: 'stage',
  verdict: 'verdict',
  final: 'final',
};

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
    const shape = SHAPES[node.id];
    const h = HEIGHTS[shape];
    const placed = { node, shape, y, h };
    y += h + GAP;
    return placed;
  });
}

const mid = (p: Placed) => p.y + p.h / 2;
const fmtSec = (s: number) => `${Math.round(s)}s`;

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

function renderNode(p: Placed): string {
  const { node, shape, y, h } = p;
  const status = NODE_STATUS_LABELS[node.status];
  const parts = [outline(p)];
  if (shape === 'stage') {
    parts.push(`<text class="node-label is-strong" x="${LEFT + 12}" y="${y + 20}">${escapeHtml(node.label)}</text>`);
    parts.push(`<text class="node-status" x="${RIGHT - 10}" y="${y + 20}" text-anchor="end">${escapeHtml(`${MARKS[node.status]} ${status}`.trim())}</text>`);
    const m = node.metrics;
    const detail = m ? `${m.numTurns} ターン・$${m.costUsd.toFixed(3)}・${fmtSec(m.durationSec)}` : '';
    if (detail) parts.push(`<text class="node-detail" x="${LEFT + 12}" y="${y + 38}">${escapeHtml(detail)}</text>`);
  } else if (shape === 'verdict') {
    parts.push(`<text class="node-label" x="${CX}" y="${mid(p) + 4}" text-anchor="middle">${escapeHtml(node.label)}</text>`);
    parts.push(`<text class="node-status" x="${CX + VERDICT_HALF_W + 8}" y="${mid(p) + 4}">${escapeHtml(`${MARKS[node.status]} ${status}`.trim())}</text>`);
  } else {
    const hw = halfWidth(shape);
    const strong = shape === 'final' ? ' is-strong' : '';
    parts.push(`<text class="node-label${strong}" x="${CX - hw + 12}" y="${y + h / 2 + 4}">${escapeHtml(node.label)}</text>`);
    parts.push(`<text class="node-status" x="${CX + hw - 10}" y="${y + h / 2 + 4}" text-anchor="end">${escapeHtml(`${MARKS[node.status]} ${status}`.trim())}</text>`);
  }
  return `<g class="node is-${node.status}" data-node="${escapeHtml(node.id)}"><title>${escapeHtml(`${node.label}：${status}`)}</title>${parts.join('')}</g>`;
}

function renderEdges(placed: Placed[]): string {
  const edges: string[] = [];
  for (let i = 1; i < placed.length; i++) {
    const from = placed[i - 1];
    const to = placed[i];
    edges.push(`<line class="edge" x1="${CX}" y1="${from.y + from.h}" x2="${CX}" y2="${to.y - 2}" marker-end="url(#mk-edge)"/>`);
  }
  const verdict = placed.find((p) => p.node.id === 'verdict');
  const label = verdict ? `<text class="edge-label" x="${CX + 8}" y="${verdict.y + verdict.h + GAP / 2 + 4}">合格</text>` : '';
  return edges.join('') + label;
}

function loop(id: string, hot: boolean, d: string, label: string, labelAttrs: string, title: string): string {
  const cls = hot ? 'loop is-hot' : 'loop';
  const marker = hot ? 'mk-hot' : 'mk-loop';
  return `<g class="${cls}" data-loop="${id}"><title>${escapeHtml(title)}</title><path class="loop-path" d="${d}" marker-end="url(#${marker})"/><text class="loop-label" ${labelAttrs}>${escapeHtml(label)}</text></g>`;
}

function renderLoops(placed: Placed[]): string {
  const at = (id: NodeId) => placed.find((p) => p.node.id === id);
  const loops: string[] = [];
  for (const stage of ['requirements', 'design', 'red'] as const) {
    const review = at(`review:${stage}`);
    const target = at(stage);
    if (!review || !target) continue;
    const n = review.node.reviseCount ?? 0;
    const y1 = mid(review);
    const y2 = mid(target);
    const d = `M${CX + REVIEW_W / 2},${y1} L${LOOP_RIGHT_X},${y1} L${LOOP_RIGHT_X},${y2} L${RIGHT + 2},${y2}`;
    const label = n > 0 ? `修正 ${n}回` : '修正';
    loops.push(loop(`revise:${stage}`, n > 0, d, label, `x="${LOOP_RIGHT_X + 5}" y="${(y1 + y2) / 2 + 4}"`, `修正の依頼 ${n} 回`));
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
      loop('send-back', n > 0, d, label, `x="${LOOP_LEFT_X - 8}" y="${ym}" text-anchor="middle" transform="rotate(-90 ${LOOP_LEFT_X - 8} ${ym})"`, `差し戻し ${n} 回`),
    );
  }
  return loops.join('');
}

const DEFS = `<defs>
<marker id="mk-edge" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="head" d="M0,0 L10,5 L0,10 z"/></marker>
<marker id="mk-loop" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="head" d="M0,0 L10,5 L0,10 z"/></marker>
<marker id="mk-hot" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="head is-hot" d="M0,0 L10,5 L0,10 z"/></marker>
</defs>`;

/** 11個の節（NODE_ORDER の順）を、縦の流れ図にする。 */
export function renderFlowSvg(nodes: PipelineNode[]): string {
  const placed = place(nodes);
  const last = placed.at(-1);
  const height = last ? last.y + last.h + TOP : TOP * 2;
  const summary = nodes.map((n) => `${n.label} ${NODE_STATUS_LABELS[n.status]}`).join('、');
  return `<svg class="flow" viewBox="0 0 ${WIDTH} ${height}" role="img" aria-label="${escapeHtml(`パイプラインの図：${summary}`)}">${DEFS}${renderEdges(placed)}${renderLoops(placed)}${placed.map(renderNode).join('')}</svg>`;
}
