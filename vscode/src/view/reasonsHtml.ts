// 理由の欄（差し戻し・修正の依頼の理由）→ HTML の文字列（純粋）。D0016。
// 欄は節ごとに全部入れておき、選ぶまでは hidden にする。開け閉めはパネルのスクリプトがする。
// 色は var(--vscode-*)、CSS はクラスだけ。外から来た文字は escapeHtml を通す。
import { nodeReasons, reasonNodeIds } from '../domain/pipelineView.ts';
import type { NodeReasons, PipelineView, ReviseNote, SendBack } from '../domain/pipelineView.ts';
import { escapeHtml } from './escape.ts';

export const REASONS_STYLE = `
.reasons[hidden] { display: none; }
.reason-list { margin: 0; padding-left: 1.4em; }
.reason { margin-bottom: 8px; }
.reason-head { margin: 0; font-weight: 600; }
.reason-summary, .reason-none { margin: 2px 0 0; }
.reason-failures { margin: 2px 0 0; padding-left: 1.2em; }
.reason-detail, .reason-summary { white-space: pre-wrap; overflow-wrap: anywhere; }
.reason-crit { font-weight: 600; color: var(--vscode-charts-red, var(--vscode-errorForeground)); }
.reason-none { color: var(--vscode-descriptionForeground); }
`;

const NO_REASON = '<p class="reason-none">理由は記録されていません</p>';

function renderSendBack(item: SendBack): string {
  const head = item.sentBack
    ? `検証 ${item.attempt} 回目で不合格 → ${item.targetLabel}へ戻した`
    : `検証 ${item.attempt} 回目で不合格（差し戻されていない）`;
  const summary = item.summary === '' ? '' : `<p class="reason-summary">${escapeHtml(item.summary)}</p>`;
  const failures = item.failures.map((f) => {
    const crit = f.criterion === '' ? '' : `<span class="reason-crit">${escapeHtml(f.criterion)}</span>：`;
    return `<li>${crit}<span class="reason-detail">${escapeHtml(f.detail)}</span></li>`;
  });
  const list = failures.length === 0 ? '' : `<ul class="reason-failures">${failures.join('')}</ul>`;
  const none = summary === '' && list === '' ? NO_REASON : '';
  return `<li class="reason"><p class="reason-head">${escapeHtml(head)}</p>${summary}${list}${none}</li>`;
}

function renderRevise(item: ReviseNote): string {
  const hasText = item.feedback !== null && item.feedback !== '';
  const head = `${item.attempt} 回目の修正の依頼${hasText ? `：${item.feedback}` : ''}`;
  return `<li class="reason"><p class="reason-head reason-detail">${escapeHtml(head)}</p>${hasText ? '' : NO_REASON}</li>`;
}

function renderSection(view: PipelineView, nodeId: string, reasons: NodeReasons): string {
  const label = view.nodes.find((n) => n.id === nodeId)?.label ?? nodeId;
  const name = reasons.kind === 'revise' ? `${label}（${reasons.label}）` : label;
  const items = reasons.kind === 'sendBack' ? reasons.items.map(renderSendBack) : reasons.items.map(renderRevise);
  return `<section class="reasons" data-reasons-for="${escapeHtml(nodeId)}" hidden><h2 class="terminal-title">${escapeHtml(`理由：${name}`)}</h2><ol class="reason-list">${items.join('')}</ol></section>`;
}

/** 理由を持つ節ごとの欄。履歴がひとつも無ければ空の文字（欄そのものを出さない）。 */
export function renderReasons(view: PipelineView): string {
  const sections: string[] = [];
  for (const id of reasonNodeIds(view)) {
    const reasons = nodeReasons(view, id);
    if (reasons !== null) sections.push(renderSection(view, id, reasons));
  }
  return sections.length === 0 ? '' : `<div class="reasons-set">${sections.join('')}</div>`;
}
