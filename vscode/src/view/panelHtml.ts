// 図の状態 → パネルの HTML の文字列（純粋）。色はすべて var(--vscode-*)、外部の読み込みはしない。
// CSS は id セレクタを使わずクラスだけ（色の直書きの検査に掛からないように）。
// このファイルは CSP・style・script の束ねと、図（.flow）・動きの基本の CSS を持つ。パネルの本体（上のバー・左の一覧・右の詳細）は shellHtml.ts、
// 左の一覧は runListHtml.ts、時系列は ganttHtml.ts、パネルの中のスクリプトは panelScript.ts。
import type { PipelineView } from '../domain/pipelineView.ts';
import type { RunListView } from '../domain/runList.ts';
import { escapeHtml } from './escape.ts';
import { GANTT_STYLE } from './ganttHtml.ts';
import { PANEL_SCRIPT } from './panelScript.ts';
import { REASONS_STYLE } from './reasonsHtml.ts';
import { RUN_LIST_STYLE } from './runListHtml.ts';
import { SHELL_STYLE, emptyListFor, renderShell } from './shellHtml.ts';
import { TIMES_STYLE } from './timesHtml.ts';
import { USAGE_STYLE } from './usageHtml.ts';

export { escapeHtml };

const STYLE = `
body { margin: 0; padding: 0; color: var(--vscode-foreground); background: var(--vscode-editor-background); font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); }
.banner-msg { margin: 0; }
.banner-msg.is-failed { color: var(--vscode-charts-red, var(--vscode-errorForeground)); }
.banner-msg.is-done { color: var(--vscode-charts-green); }
.banner-msg.is-running { color: var(--vscode-charts-blue); }
.flow { display: block; flex: none; height: auto; }
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
.flow .is-waiting .shape { stroke: var(--vscode-charts-yellow, var(--vscode-foreground)); stroke-width: 2.4; }
.flow .is-waiting .node-status { fill: var(--vscode-charts-yellow, var(--vscode-foreground)); }
.flow .node-wait { fill: var(--vscode-charts-yellow, var(--vscode-foreground)); font-size: 10.5px; font-variant-numeric: tabular-nums; }
.flow .elapsed { fill: var(--vscode-charts-blue); font-variant-numeric: tabular-nums; }
.elapsed { color: var(--vscode-foreground); font-variant-numeric: tabular-nums; }
@media (prefers-reduced-motion: no-preference) {
  .flow .is-running .shape { animation: pulse 1.6s ease-in-out infinite; }
  @keyframes pulse { 50% { stroke-opacity: 0.35; } }
  .flow .edge.is-flowing { stroke-width: 2; stroke-dasharray: 2 8; stroke-linecap: round; animation: flow 0.9s linear infinite; }
  @keyframes flow { to { stroke-dashoffset: -10; } }
  .flow .is-waiting .shape { animation: attention 2.4s ease-in-out infinite; }
  @keyframes attention { 50% { stroke-opacity: 0.3; } }
  .flow .loop.is-new .loop-path { animation: flash 1.4s ease-out 1; }
  @keyframes flash { from { stroke-width: 6; } }
}
.terminal-title { margin: 0 0 4px; font-size: 0.9em; color: var(--vscode-descriptionForeground); }
.terminal { margin: 0; padding: 8px; flex: 1 1 auto; min-height: 0; overflow: auto; background: var(--vscode-terminal-background, var(--vscode-editor-background)); color: var(--vscode-terminal-foreground, var(--vscode-foreground)); border: 1px solid var(--vscode-panel-border); font-family: var(--vscode-editor-font-family); }
.line { white-space: pre-wrap; word-break: break-word; }
.line-tool { color: var(--vscode-descriptionForeground); }
.artifacts { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.artifact { font: inherit; padding: 2px 6px; border: 1px solid var(--vscode-panel-border); background: transparent; color: var(--vscode-textLink-foreground); cursor: pointer; }
.artifact:disabled { color: var(--vscode-descriptionForeground); cursor: default; }
.banner-msg.is-waiting { color: var(--vscode-charts-yellow, var(--vscode-foreground)); }
.warnings { margin: 0; padding-left: 1.2em; color: var(--vscode-charts-yellow, var(--vscode-foreground)); }
.flow .node[data-reasons] { cursor: pointer; }
.flow .node[data-reasons]:focus-visible .shape { outline: 2px solid var(--vscode-focusBorder); }
.flow .node.is-picked .shape { stroke: var(--vscode-focusBorder, var(--vscode-charts-blue)); stroke-width: 3; }
.flow .loop.is-picked .loop-path { stroke: var(--vscode-focusBorder, var(--vscode-charts-blue)); stroke-width: 3.2; stroke-dasharray: none; opacity: 1; marker-end: url(#mk-pick); }
.flow .loop.is-picked .loop-label { fill: var(--vscode-focusBorder, var(--vscode-charts-blue)); font-weight: 700; }
.flow .head.is-pick { fill: var(--vscode-focusBorder, var(--vscode-charts-blue)); }
`;

/** パネルの HTML 全体。CSP・スタイル・小さなスクリプトと、renderViewBody(view, list) を本体に入れる。 */
export function renderPanelHtml(view: PipelineView, nonce: string, list?: RunListView | null): string {
  const n = escapeHtml(nonce);
  return `<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${n}'; script-src 'nonce-${n}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>pipe-in</title>
<style nonce="${n}">${STYLE}${REASONS_STYLE}${TIMES_STYLE}${USAGE_STYLE}${RUN_LIST_STYLE}${GANTT_STYLE}${SHELL_STYLE}</style>
</head>
<body>
<div class="root">${renderViewBody(view, list)}</div>
<script nonce="${n}">${PANEL_SCRIPT}</script>
</body>
</html>`;
}

/** 本体だけ（描き直しのとき、これをパネルに送って差し替える）。一覧は無い・null のときも、行が 0 の一覧で出す。 */
export function renderViewBody(view: PipelineView, list?: RunListView | null): string {
  return renderShell(view, list ?? emptyListFor(view));
}
