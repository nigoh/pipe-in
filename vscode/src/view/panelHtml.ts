// 図の状態 → パネルの HTML の文字列（純粋）。色はすべて var(--vscode-*)、外部の読み込みはしない。
// CSS は id セレクタを使わずクラスだけ（色の直書きの検査に掛からないように）。
import { STAGE_LABELS } from '../domain/stage.ts';
import { WAITING_MESSAGE } from '../domain/pipelineView.ts';
import type { PipelineView, TerminalView } from '../domain/pipelineView.ts';
import type { ArtifactEntry } from '../domain/artifacts.ts';
import type { OutputItem } from '../domain/stageLog.ts';
import { escapeHtml } from './escape.ts';
import { renderFlowSvg } from './flowSvg.ts';
import { USAGE_STYLE, renderUsage } from './usageHtml.ts';

export { escapeHtml };

const STYLE = `
body { margin: 0; padding: 12px; color: var(--vscode-foreground); background: var(--vscode-editor-background); font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); }
.banner { display: flex; gap: 12px; align-items: baseline; justify-content: space-between; padding: 6px 8px; margin-bottom: 12px; border: 1px solid var(--vscode-panel-border); }
.banner-msg { margin: 0; }
.banner-msg.is-failed { color: var(--vscode-charts-red, var(--vscode-errorForeground)); }
.banner-msg.is-done { color: var(--vscode-charts-green); }
.banner-msg.is-running { color: var(--vscode-charts-blue); }
.cost { color: var(--vscode-descriptionForeground); white-space: nowrap; }
.layout { display: grid; grid-template-columns: minmax(240px, 320px) 1fr; gap: 16px; align-items: start; }
@media (max-width: 640px) { .layout { grid-template-columns: 1fr; } }
.flow { display: block; width: 100%; height: auto; }
.flow text { fill: var(--vscode-foreground); font-family: var(--vscode-font-family); font-size: 12px; }
.flow .is-strong { font-weight: 600; }
.flow .node-detail, .flow .edge-label { fill: var(--vscode-descriptionForeground); font-size: 10.5px; }
.flow .node-status { font-size: 11px; }
.flow .shape { fill: var(--vscode-editor-background); stroke: var(--vscode-descriptionForeground); stroke-width: 1.2; }
.flow .shape.is-doc { stroke-dasharray: 4 3; }
.flow .edge { stroke: var(--vscode-descriptionForeground); stroke-width: 1.2; }
.flow .head { fill: var(--vscode-descriptionForeground); }
.flow .head.is-hot { fill: var(--vscode-charts-blue); }
.flow .loop-path { fill: none; stroke: var(--vscode-descriptionForeground); stroke-width: 1.2; stroke-dasharray: 5 4; opacity: 0.7; }
.flow .loop-label { fill: var(--vscode-descriptionForeground); font-size: 10.5px; }
.flow .loop.is-hot .loop-path { stroke: var(--vscode-charts-blue); stroke-width: 2; opacity: 1; }
.flow .loop.is-hot .loop-label { fill: var(--vscode-charts-blue); font-weight: 600; }
.flow .is-pending .node-status { fill: var(--vscode-descriptionForeground); }
.flow .is-running .shape { stroke: var(--vscode-charts-blue); stroke-width: 2.4; }
.flow .is-running .node-status { fill: var(--vscode-charts-blue); }
.flow .is-done .shape { stroke: var(--vscode-charts-green); stroke-width: 1.6; }
.flow .is-done .node-status { fill: var(--vscode-charts-green); }
.flow .is-failed .shape { stroke: var(--vscode-charts-red, var(--vscode-errorForeground)); stroke-width: 2; }
.flow .is-failed .node-status { fill: var(--vscode-charts-red, var(--vscode-errorForeground)); }
.flow .is-skipped .shape { stroke-dasharray: 4 3; }
.flow .is-skipped text { opacity: 0.6; }
@media (prefers-reduced-motion: no-preference) {
  .flow .is-running .shape { animation: pulse 1.6s ease-in-out infinite; }
  @keyframes pulse { 50% { stroke-opacity: 0.35; } }
}
.right { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.terminal-title { margin: 0 0 4px; font-size: 0.9em; color: var(--vscode-descriptionForeground); }
.terminal { margin: 0; padding: 8px; height: 50vh; overflow: auto; background: var(--vscode-terminal-background, var(--vscode-editor-background)); color: var(--vscode-terminal-foreground, var(--vscode-foreground)); border: 1px solid var(--vscode-panel-border); font-family: var(--vscode-editor-font-family); }
.line { white-space: pre-wrap; word-break: break-word; }
.line-tool { color: var(--vscode-descriptionForeground); }
.artifacts { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.artifact { font: inherit; padding: 2px 6px; border: 1px solid var(--vscode-panel-border); background: transparent; color: var(--vscode-textLink-foreground); cursor: pointer; }
.artifact:disabled { color: var(--vscode-descriptionForeground); cursor: default; }
`;

// render を受けたら本体を差し替え、ターミナルが末尾近くなら末尾まで送る。ボタンで openArtifact、読み込み後に ready を送る。
const SCRIPT = `
(function () {
  const vscode = acquireVsCodeApi();
  const root = document.querySelector('.root');
  function nearBottom(el) { return !el || el.scrollHeight - el.scrollTop - el.clientHeight < 40; }
  function follow(wasNear) { const t = root.querySelector('.terminal'); if (t && wasNear) t.scrollTop = t.scrollHeight; }
  window.addEventListener('message', function (event) {
    const msg = event.data;
    if (!msg || msg.type !== 'render' || typeof msg.html !== 'string') return;
    const wasNear = nearBottom(root.querySelector('.terminal'));
    root.innerHTML = msg.html;
    follow(wasNear);
  });
  root.addEventListener('click', function (event) {
    const button = event.target.closest('button[data-artifact]');
    if (button && !button.disabled) vscode.postMessage({ type: 'openArtifact', name: button.getAttribute('data-artifact') });
  });
  follow(true);
  vscode.postMessage({ type: 'ready' });
})();
`;

/** パネルの HTML 全体。CSP・スタイル・小さなスクリプトと、renderViewBody(view) を本体に入れる。 */
export function renderPanelHtml(view: PipelineView, nonce: string): string {
  const n = escapeHtml(nonce);
  return `<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${n}'; script-src 'nonce-${n}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>devpipe</title>
<style nonce="${n}">${STYLE}${USAGE_STYLE}</style>
</head>
<body>
<div class="root">${renderViewBody(view)}</div>
<script nonce="${n}">${SCRIPT}</script>
</body>
</html>`;
}

/** 本体だけ（描き直しのとき、これをパネルに送って差し替える）。 */
export function renderViewBody(view: PipelineView): string {
  return `${renderBanner(view)}
<div class="layout">
${renderFlowSvg(view.nodes)}
<div class="right">
${renderTerminal(view.terminal)}
${renderArtifacts(view.artifacts)}
${renderUsage(view.usage)}
</div>
</div>`;
}

function formatCost(usd: number): string {
  return `$${usd.toFixed(3)}`;
}

function renderBanner(view: PipelineView): string {
  let msg = '';
  if (view.noRecords) {
    msg = `<p class="banner-msg">${escapeHtml(view.noRecords.message)}：${escapeHtml(view.noRecords.workDir)}</p>`;
  } else if (view.final !== null) {
    const cls = view.final === 'PASSED' ? 'is-done' : 'is-failed';
    msg = `<p class="banner-msg ${cls}">最終の結果：${escapeHtml(view.final)}</p>`;
  } else if (view.runningStage !== null && view.terminal.source !== null) {
    const src = view.terminal.source;
    const attempt = src.attempt === null ? '' : `（${src.attempt} 回目）`;
    msg = `<p class="banner-msg is-running">${escapeHtml(`いま：${STAGE_LABELS[src.stage]}${attempt}`)}</p>`;
  } else if (view.waiting) {
    msg = `<p class="banner-msg">${escapeHtml(WAITING_MESSAGE)}</p>`;
  } else {
    msg = '<p class="banner-msg"></p>';
  }
  return `<div class="banner">${msg}<span class="cost">合計 ${formatCost(view.totalCostUsd)}</span></div>`;
}

function renderItem(item: OutputItem): string {
  if (item.kind === 'tool') {
    const target = item.target === null ? '' : ` ${item.target}`;
    return `<div class="line line-tool">${escapeHtml(`· ${item.tool}${target}`)}</div>`;
  }
  return `<div class="line">${escapeHtml(item.text)}</div>`;
}

function renderTerminal(terminal: TerminalView): string {
  const source = terminal.source;
  const title =
    source === null
      ? '出力（ログなし）'
      : `出力：${STAGE_LABELS[source.stage]}${source.attempt === null ? '' : `（${source.attempt} 回目）`}`;
  return `<section><h2 class="terminal-title">${escapeHtml(title)}</h2><div class="terminal">${terminal.items.map(renderItem).join('')}</div></section>`;
}

function renderArtifacts(artifacts: ArtifactEntry[]): string {
  const items = artifacts.map((a) => {
    const label = escapeHtml(`${a.label}（${a.ready ? 'ある' : 'まだない'}）`);
    const attrs = a.ready ? `data-artifact="${escapeHtml(a.name)}"` : 'disabled';
    return `<li><button type="button" class="artifact" ${attrs} title="${escapeHtml(a.name)}">${label}</button></li>`;
  });
  return `<section><h2 class="terminal-title">成果物</h2><ul class="artifacts">${items.join('')}</ul></section>`;
}
