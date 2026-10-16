// 図の状態 → パネルの HTML の文字列（純粋）。色はすべて var(--vscode-*)、外部の読み込みはしない。
// CSS は id セレクタを使わずクラスだけ（色の直書きの検査に掛からないように）。
import { STAGE_LABELS } from '../domain/stage.ts';
import { NODE_STATUS_LABELS, WAITING_MESSAGE } from '../domain/pipelineView.ts';
import type { PipelineNode, PipelineView, TerminalView } from '../domain/pipelineView.ts';
import type { ArtifactEntry } from '../domain/artifacts.ts';
import type { OutputItem } from '../domain/stageLog.ts';

const ESCAPES: Readonly<Record<string, string>> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&apos;',
};

/** & < > " ' を名前の文字参照にする（数値の文字参照 &#..; は使わない）。 */
export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

const STYLE = `
body { margin: 0; padding: 12px; color: var(--vscode-foreground); background: var(--vscode-editor-background); font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); }
.banner { display: flex; gap: 12px; align-items: baseline; justify-content: space-between; padding: 6px 8px; margin-bottom: 12px; border: 1px solid var(--vscode-panel-border); }
.banner-msg { margin: 0; }
.banner-msg.is-failed { color: var(--vscode-charts-red, var(--vscode-errorForeground)); }
.banner-msg.is-done { color: var(--vscode-charts-green); }
.cost { color: var(--vscode-descriptionForeground); white-space: nowrap; }
.layout { display: grid; grid-template-columns: minmax(180px, 240px) 1fr; gap: 12px; }
.nodes { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.node { padding: 6px 8px; border: 1px solid var(--vscode-panel-border); border-left-width: 4px; }
.node-head { display: flex; justify-content: space-between; gap: 8px; }
.node-status { font-size: 0.9em; }
.node-detail { margin-top: 2px; font-size: 0.85em; color: var(--vscode-descriptionForeground); }
.is-pending { border-left-color: var(--vscode-descriptionForeground); }
.is-pending .node-status { color: var(--vscode-descriptionForeground); }
.is-running { border-left-color: var(--vscode-charts-blue); }
.is-running .node-status { color: var(--vscode-charts-blue); }
.is-done { border-left-color: var(--vscode-charts-green); }
.is-done .node-status { color: var(--vscode-charts-green); }
.is-failed { border-left-color: var(--vscode-charts-red, var(--vscode-errorForeground)); }
.is-failed .node-status { color: var(--vscode-charts-red, var(--vscode-errorForeground)); }
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
<style nonce="${n}">${STYLE}</style>
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
<ol class="nodes">${view.nodes.map(renderNode).join('')}</ol>
<div class="right">
${renderTerminal(view.terminal)}
${renderArtifacts(view.artifacts)}
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
  } else if (view.waiting) {
    msg = `<p class="banner-msg">${escapeHtml(WAITING_MESSAGE)}</p>`;
  } else {
    msg = '<p class="banner-msg"></p>';
  }
  return `<div class="banner">${msg}<span class="cost">合計 ${formatCost(view.totalCostUsd)}</span></div>`;
}

function renderNode(node: PipelineNode): string {
  const details: string[] = [];
  if (node.reviseCount !== null && node.reviseCount > 0) details.push(`修正の依頼 ${node.reviseCount} 回`);
  if (node.sendBackCount !== null && node.sendBackCount > 0) details.push(`差し戻し ${node.sendBackCount} 回`);
  if (node.metrics) {
    const m = node.metrics;
    details.push(`${m.numTurns} ターン・${formatCost(m.costUsd)}・${m.durationSec}s`);
  }
  const detail = details.length > 0 ? `<div class="node-detail">${escapeHtml(details.join(' / '))}</div>` : '';
  return `<li class="node is-${node.status}"><div class="node-head"><span class="node-label">${escapeHtml(node.label)}</span><span class="node-status">${escapeHtml(NODE_STATUS_LABELS[node.status])}</span></div>${detail}</li>`;
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
