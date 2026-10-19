// 右の欄の「時間」の節 → HTML の文字列（純粋）。D0017。
// 実行が2回以上ある段の、回ごとの時間と合計。常に見える（理由の欄のように開け閉めしない）。固定の表示で数え上げない。
// 色は var(--vscode-*)、CSS はクラスだけ。外から来た文字（段の名前）は escapeHtml を通す。
import type { PipelineView, StageTimes } from '../domain/pipelineView.ts';
import { formatDuration } from './duration.ts';
import { escapeHtml } from './escape.ts';

export const TIMES_STYLE = `
.times-list { list-style: none; margin: 0; padding: 0; }
.times-item { margin-bottom: 8px; }
.times-head { margin: 0; font-weight: 600; }
.times-runs { margin: 2px 0 0; padding-left: 1.4em; color: var(--vscode-descriptionForeground); }
`;

function renderStage(item: StageTimes): string {
  const head = `${item.label}（合計 ${formatDuration(item.totalSec)}）`;
  const runs = item.runs.map((r, i) => `<li>${i + 1} 回目 ${formatDuration(r.durationSec)}</li>`);
  return `<li class="times-item"><p class="times-head">${escapeHtml(head)}</p><ol class="times-runs">${runs.join('')}</ol></li>`;
}

/** 回ごとの時間の節。2回以上の段がひとつも無ければ空の文字（節そのものを出さない）。 */
export function renderTimes(view: PipelineView): string {
  if (view.stageTimes.length === 0) return '';
  return `<section class="times"><h2 class="terminal-title">時間</h2><ul class="times-list">${view.stageTimes.map(renderStage).join('')}</ul></section>`;
}
