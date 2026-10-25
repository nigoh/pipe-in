// 図の節 → 左の列の流れ図（SVG の文字列、純粋）。本線は上から下、戻りの矢印は右（確認 → 同じ段）と左（判定 → 実装）。
// 色は CSS（panelHtml.ts の STYLE）でクラスに付ける。ここでは形と位置だけを決める。
// 動いている段で段のログが目安の時間動かないとき（D0021）は、節と、その段へ入る流れる矢印に印の属性（data-quiet・data-stale-after）を持たせ、
// 節の 2 行目に「⚠ 更新なし」の文字を足す。パネルのスクリプトが is-stale を付けると、CSS が点線の枠にし、脈打ちと点の流れを止める。
import { NODE_STATUS_LABELS } from '../domain/pipelineView.ts';
import type { NodeId, PipelineNode } from '../domain/pipelineView.ts';
import { formatDuration } from './duration.ts';
import { escapeHtml } from './escape.ts';
import { formatMilli } from './money.ts';
import { STALE_WORD, staleAttrs, staleTime } from './staleMark.ts';

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

/** 上限の表示の SVG 部品（金額の対・棒・言葉・「N 回目」）。外から来た文字は出さない（数字と固定の言葉だけ）。 */
function renderBudget(node: PipelineNode, y: number): string[] {
  const parts: string[] = [];
  const b = node.budget;
  if (b == null) return parts;
  const pair = budgetPair(node);
  const x = LEFT + 12;
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
  if (nth !== null) parts.push(`<text class="node-detail" x="${RIGHT - 10}" y="${wordY}" text-anchor="end">${escapeHtml(nth)}</text>`);
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
    const h = shape === 'stage' ? heightOf(node) : HEIGHTS[shape];
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

function renderNode(p: Placed, pickable: ReadonlySet<NodeId>, staleAfterSec: number | null): string {
  const { node, shape, y, h } = p;
  const status = NODE_STATUS_LABELS[node.status];
  const parts = [outline(p)];
  // 動いている段の節で、最後の更新からの秒と目安がそろうときだけ、印の属性と印の文字を足す（目安なしなら今までの図のまま）
  const stale = shape === 'stage' && node.status === 'running' ? staleAttrs(node.quietSec, staleAfterSec) : '';
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
    // 印の文字は 2 行目の同じ位置に置く。is-stale が付くまで CSS で隠し、付くと経過の文字と入れ替わる
    if (stale !== '') {
      parts.push(`<text class="node-stale" x="${LEFT + 12}" y="${y + 38}">${STALE_WORD} ${staleTime(node.quietSec, 'tspan')}</text>`);
    }
    parts.push(...renderBudget(node, y));
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
  const budgetMark = shape === 'stage' && node.budget != null ? ` is-budget-${node.budget.state}` : '';
  const title = `${node.label}：${status}${shape === 'stage' ? budgetTitle(node) : ''}`;
  return `<g class="node is-${node.status}${waitingMark}${budgetMark}" data-node="${escapeHtml(node.id)}"${stale}${pick}><title>${escapeHtml(title)}</title>${parts.join('')}</g>`;
}

function renderEdges(placed: Placed[], staleAfterSec: number | null): string {
  const edges: string[] = [];
  for (let i = 1; i < placed.length; i++) {
    const from = placed[i - 1];
    const to = placed[i];
    // 動いている段へ入る矢印にだけ、流れる点の印を付ける（始まりの時刻が読めて経過が出ているとき）
    const flowing = to.node.runningSec != null;
    // 矢印は節の外の別の要素なので、節の is-stale は届かない。流れる点を止めるため、節と同じ値の属性を自分で持つ
    const stale = flowing ? staleAttrs(to.node.quietSec, staleAfterSec) : '';
    edges.push(`<line class="edge${flowing ? ' is-flowing' : ''}"${stale} x1="${CX}" y1="${from.y + from.h}" x2="${CX}" y2="${to.y - 2}" marker-end="url(#mk-edge)"/>`);
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
 * staleAfterSec は「止まっているかも」の目安の秒（D0021）。null なら更新なしの印は出さない。
 */
export function renderFlowSvg(nodes: PipelineNode[], pickable: ReadonlySet<NodeId> = new Set(), staleAfterSec: number | null = null): string {
  const placed = place(nodes);
  // role="img" の中身は読み上げの対象から外れるので、押せる節があるときは group にする
  const role = placed.some((p) => pickable.has(p.node.id)) ? 'group' : 'img';
  const last = placed.at(-1);
  const height = last ? last.y + last.h + TOP : TOP * 2;
  // 近い・超えた・止まった節だけ、言葉を足す（余裕と状態なしは今のまま）
  const summary = nodes
    .map((n) => {
      const word = shapeOf(n.id) === 'stage' ? budgetWord(n) : null;
      return `${n.label} ${NODE_STATUS_LABELS[n.status]}${word === null ? '' : `（${word}）`}`;
    })
    .join('、');
  return `<svg class="flow" viewBox="0 0 ${WIDTH} ${height}" role="${role}" aria-label="${escapeHtml(`パイプラインの図：${summary}`)}">${DEFS}${renderEdges(placed, staleAfterSec)}${renderLoops(placed)}${placed.map((p) => renderNode(p, pickable, staleAfterSec)).join('')}</svg>`;
}
