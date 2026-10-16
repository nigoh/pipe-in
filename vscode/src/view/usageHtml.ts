// 使用量の図の状態 → パネルの「使用量」の節の HTML（純粋）。ログから来た文字は escapeHtml を通す。
import type { UsageRow, UsageView } from '../domain/pipelineView.ts';
import type { RateWindow, TokenCounts } from '../domain/runRecord.ts';
import { escapeHtml } from './escape.ts';

export const USAGE_STYLE = `
.usage-summary { margin: 0 0 6px; color: var(--vscode-descriptionForeground); }
.usage-table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; font-size: 0.92em; }
.usage-table th, .usage-table td { padding: 2px 6px; border-bottom: 1px solid var(--vscode-panel-border); text-align: right; white-space: nowrap; }
.usage-table th:first-child, .usage-table td:first-child { text-align: left; }
.usage-table th { font-weight: 600; color: var(--vscode-descriptionForeground); }
.usage-table .is-total td { font-weight: 600; }
.usage-scroll { overflow-x: auto; }
.usage-list { margin: 6px 0 0; padding-left: 1.2em; }
.usage-reset { color: var(--vscode-charts-yellow, var(--vscode-descriptionForeground)); }
`;

/** 桁区切りの整数（ロケールに左右されないよう en-US に固定）。 */
export function formatCount(n: number): string {
  return Math.round(n).toLocaleString('en-US');
}

/** 0〜1 の割合を % に。digits は小数の桁。 */
export function formatPercent(rate: number | null, digits = 0): string {
  return rate === null ? '—' : `${(rate * 100).toFixed(digits)}%`;
}

/** 利用枠の推移（開始 → 終了。途中で枠が戻ったら最大値も）。 */
export function formatRateSpan(w: RateWindow): string {
  const span = `${formatPercent(w.first)} → ${formatPercent(w.last)}`;
  return w.resetSeen ? `${span}（途中で枠が戻った。最大 ${formatPercent(w.peak)}）` : span;
}

function tokenCells(t: TokenCounts | null): string {
  if (t === null) return '<td>—</td>'.repeat(5);
  return [t.input, t.cacheWrite, t.cacheRead, t.output, t.thinking].map((n) => `<td>${formatCount(n)}</td>`).join('');
}

function stageLabel(row: UsageRow): string {
  return `${row.label}${row.attempt === null ? '' : `（${row.attempt} 回目）`}`;
}

const TOKEN_HEAD = '<th>入力</th><th>キャッシュ書込</th><th>キャッシュ読込</th><th>出力</th><th>うち thinking</th>';

function renderStageTable(usage: UsageView): string {
  const rows = usage.rows.map(
    (r) =>
      `<tr><td>${escapeHtml(`${r.seq}. ${stageLabel(r)}`)}</td>${tokenCells(r.tokens)}<td>${formatPercent(r.cacheReuseRate, 1)}</td></tr>`,
  );
  const s = usage.summary;
  rows.push(`<tr class="is-total"><td>合計</td>${tokenCells(s.tokens)}<td>${formatPercent(s.cacheReuseRate, 1)}</td></tr>`);
  return `<div class="usage-scroll"><table class="usage-table"><thead><tr><th>段</th>${TOKEN_HEAD}<th>再利用率</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}

function renderModels(usage: UsageView): string {
  if (usage.summary.byModel.length === 0) return '';
  const items = usage.summary.byModel.map(
    (m) => `<li>${escapeHtml(m.model)}：出力 ${formatCount(m.tokens.output)}・$${m.costUsd.toFixed(3)}</li>`,
  );
  return `<h3 class="terminal-title">モデル別</h3><ul class="usage-list">${items.join('')}</ul>`;
}

function renderRateLimits(usage: UsageView): string {
  if (usage.summary.rateLimits.length === 0) return '';
  const items = usage.summary.rateLimits.map((w) => {
    const cls = w.resetSeen ? ' class="usage-reset"' : '';
    return `<li${cls}>${escapeHtml(`${w.label}：${formatRateSpan(w)}`)}</li>`;
  });
  return `<h3 class="terminal-title">利用枠</h3><ul class="usage-list">${items.join('')}</ul>`;
}

/** 使用量の節。usage が null なら何も出さない。 */
export function renderUsage(usage: UsageView | null): string {
  if (usage === null) return '';
  const s = usage.summary;
  const apiSec = s.durationApiMs > 0 ? `・API 待ち ${Math.round(s.durationApiMs / 1000)}s` : '';
  const lead = `出力 ${formatCount(s.tokens.output)}・キャッシュ再利用率 ${formatPercent(s.cacheReuseRate, 1)}${apiSec}`;
  return `<section><h2 class="terminal-title">使用量</h2><p class="usage-summary">${escapeHtml(lead)}</p>${renderStageTable(usage)}${renderModels(usage)}${renderRateLimits(usage)}</section>`;
}
