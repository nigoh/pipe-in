// パネルの枠組み（Web アプリの形）→ HTML の文字列（純粋）。D0019。
// 上のバー・左の一覧・右の詳細（パンくず・見出し・メタ・知らせ・タブ・「図と出力」の枠）を組み立てる。
// 色は var(--vscode-*)、CSS はクラスだけ（style= は使わない）。外から来た文字はすべて escapeHtml を通す。
// 選んでいる run の行（一覧の rows のうち selected）があればそこから、無ければ図の状態（view）から詳細の上の部分を作る。
// 選んだ行が動いていて段のログが目安の時間動かないとき（D0021）は、見出しに「⚠ 止まっているかも」のバッジ、メタの下に知らせを足す（どちらも行の quietSec から作る）。
// 「成果物」のタブの中身（一覧＋プレビュー、D0025）は artifactsHtml.ts。その幅の規則は、ここの既存の 2 つの @media（1100px・800px）の中に書く。
// 実際にスクロールする外側の枠（<main class="detail">・「成果物」のタブパネル）は data-scroll を持ち、パネルのスクリプトが描き直しのあとも位置を覚える。
import { WAITING_MESSAGE, reasonNodeIds } from '../domain/pipelineView.ts';
import type { Elapsed, PipelineView, TerminalView } from '../domain/pipelineView.ts';
import { stateWord } from '../domain/runList.ts';
import type { RunListView, RunRow } from '../domain/runList.ts';
import type { OutputItem } from '../domain/stageLog.ts';
import { renderArtifacts } from './artifactsHtml.ts';
import { formatDuration } from './duration.ts';
import { escapeHtml } from './escape.ts';
import { renderFlowSvg } from './flowSvg.ts';
import { renderGantt } from './ganttHtml.ts';
import { renderReasons } from './reasonsHtml.ts';
import { renderRunList } from './runListHtml.ts';
import {
  STALE_BADGE_WORD,
  STALE_COLOR,
  STALE_NOTICE_HEAD,
  STALE_NOTICE_SUB,
  STALE_NOTICE_TAIL,
  rowStaleAttrs,
  staleTime,
} from './staleMark.ts';
import { renderTimes } from './timesHtml.ts';
import { renderUsage } from './usageHtml.ts';

export const SHELL_STYLE = `
.app { display: flex; flex-direction: column; height: 100vh; min-width: 0; }
.topbar { flex: none; display: flex; align-items: center; flex-wrap: wrap; gap: 4px 12px; min-height: 40px; padding: 4px 16px; box-sizing: border-box; border-bottom: 1px solid var(--vscode-panel-border); background: var(--vscode-editorWidget-background); }
.topbar-name { font-weight: 700; letter-spacing: 0.02em; }
.topbar-dim { font-size: 12px; color: var(--vscode-descriptionForeground); }
.topbar-spacer { flex: 1; }
.topbar-wt { padding: 1px 10px; border: 1px solid var(--vscode-charts-blue); border-radius: 999px; font-size: 12px; font-weight: 600; color: var(--vscode-charts-blue); }
.app code { font-family: var(--vscode-editor-font-family, monospace); font-size: 11.5px; }
.app-body { flex: 1 1 auto; min-height: 0; display: grid; grid-template-columns: clamp(240px, 24vw, 320px) minmax(0, 1fr); }
.sidebar { min-width: 0; min-height: 0; display: flex; flex-direction: column; box-sizing: border-box; padding: 12px; overflow: hidden; border-right: 1px solid var(--vscode-panel-border); background: var(--vscode-editorWidget-background); }
.detail { min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: 12px; box-sizing: border-box; padding: 16px 20px; overflow: hidden; }
.crumbs { flex: none; min-height: 1em; font-size: 12px; color: var(--vscode-descriptionForeground); }
.head { flex: none; display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; }
.head-title { margin: 0; min-width: 0; font-size: 20px; font-weight: 600; overflow-wrap: anywhere; }
.head-spacer { flex: 1; }
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border: 1px solid var(--vscode-descriptionForeground); border-radius: 999px; font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; color: var(--vscode-descriptionForeground); }
.badge-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.badge.is-waiting { border-color: var(--vscode-charts-yellow, var(--vscode-foreground)); color: var(--vscode-charts-yellow, var(--vscode-foreground)); }
.badge.is-running { border-color: var(--vscode-charts-blue); color: var(--vscode-charts-blue); }
.badge.is-done { border-color: var(--vscode-charts-green); color: var(--vscode-charts-green); }
.badge.is-failed { border-color: var(--vscode-charts-red, var(--vscode-errorForeground)); color: var(--vscode-charts-red, var(--vscode-errorForeground)); }
.badge .elapsed { color: inherit; }
.secondary { min-height: 28px; padding: 4px 12px; border: 1px solid var(--vscode-panel-border); border-radius: 6px; background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); font: inherit; font-size: 12px; cursor: pointer; }
.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
.secondary:focus-visible { outline: 2px solid var(--vscode-focusBorder); outline-offset: 1px; }
.detail-meta { flex: none; display: flex; flex-wrap: wrap; align-items: center; gap: 6px 20px; font-size: 12px; color: var(--vscode-descriptionForeground); }
.detail-meta strong { font-weight: 600; font-variant-numeric: tabular-nums; color: var(--vscode-foreground); overflow-wrap: anywhere; }
.detail-meta code { padding: 1px 6px; border-radius: 4px; background: var(--vscode-textCodeBlock-background); color: var(--vscode-foreground); overflow-wrap: anywhere; }
.notice { flex: none; display: flex; flex-direction: column; gap: 2px; padding: 10px 14px; border: 1px solid var(--vscode-charts-yellow, var(--vscode-foreground)); border-radius: 6px; background: var(--vscode-inputValidation-warningBackground, transparent); color: var(--vscode-foreground); }
.notice-sub { font-size: 12px; color: var(--vscode-descriptionForeground); }
.badge.stale-badge { display: none; color: var(--vscode-foreground); }
.badge.stale-badge.is-stale { display: inline-flex; border-style: dashed; border-color: ${STALE_COLOR}; }
.notice.stale-notice { display: none; border-style: dashed; border-color: ${STALE_COLOR}; background: transparent; }
.notice.stale-notice.is-stale { display: flex; }
.detail-tabs { flex: none; display: flex; gap: 4px; border-bottom: 1px solid var(--vscode-panel-border); }
.detail-tabs button { min-height: 28px; padding: 8px 12px; margin-bottom: -1px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--vscode-descriptionForeground); font: inherit; cursor: pointer; }
.detail-tabs button[aria-selected="true"] { border-bottom-color: var(--vscode-focusBorder); color: var(--vscode-foreground); font-weight: 600; }
.detail-tabs button:focus-visible { outline: 2px solid var(--vscode-focusBorder); outline-offset: -2px; }
.tabpanel { flex: 1 1 auto; min-height: 0; min-width: 0; display: flex; flex-direction: column; overflow: auto; }
[hidden] { display: none !important; }
.split { flex: 1 1 auto; min-height: 0; min-width: 0; display: grid; grid-template-columns: clamp(260px, 26vw, 340px) minmax(0, 1fr); grid-template-rows: minmax(0, 1fr); gap: 16px; }
.pane-diagram { min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: 12px; overflow: auto; border: 1px solid var(--vscode-panel-border); border-radius: 6px; padding: 8px; box-sizing: border-box; }
.zoom-bar { position: sticky; top: 0; z-index: 1; flex: none; align-self: flex-end; display: flex; gap: 2px; background: var(--vscode-editor-background); }
.zoom-bar button { min-width: 28px; min-height: 24px; padding: 2px 6px; border: 1px solid var(--vscode-panel-border); border-radius: 4px; background: transparent; color: var(--vscode-foreground); font: inherit; font-variant-numeric: tabular-nums; cursor: pointer; }
.zoom-bar button:focus-visible { outline: 2px solid var(--vscode-focusBorder); outline-offset: -2px; }
.pane-right { min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: 12px; }
.pane-output { flex: 0 0 34%; min-height: 0; display: flex; flex-direction: column; }
.pane-gantt { flex: 1 1 auto; min-height: 0; overflow: auto; border: 1px solid var(--vscode-panel-border); border-radius: 6px; padding: 8px; box-sizing: border-box; }
@media (max-width: 1100px) {
  .detail { overflow: auto; }
  .tabpanel { flex: none; overflow: visible; }
  .split { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto; }
  .pane-diagram { max-height: 60vh; }
  .pane-right { display: flex; flex-direction: column; }
  .pane-output { flex: none; height: 40vh; }
  .pane-gantt { flex: none; max-height: 50vh; }
  .art { grid-template-rows: auto; }
  .art-list { max-height: 60vh; }
  .art-body { max-height: 70vh; }
}
@media (max-width: 800px) {
  .app { height: auto; }
  .app-body { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto auto; }
  .sidebar { max-height: 35vh; border-right: 0; border-bottom: 1px solid var(--vscode-panel-border); }
  .detail { overflow: visible; }
  .art { grid-template-columns: minmax(0, 1fr); }
  .art-list { max-height: 30vh; }
  .art-body { max-height: 60vh; }
}
`;

const DASH = '—';

/** 一覧の行が無いときの、空の一覧（作業フォルダは図の状態の記録なしの表示から）。 */
export function emptyListFor(view: PipelineView): RunListView {
  return { rows: [], selected: 'here|', omitted: [], omittedWorktrees: 0, workDir: view.noRecords?.workDir ?? '' };
}

function stageLabel(view: PipelineView, stage: string): string {
  return view.stageLabels[stage] ?? stage;
}

// ---- 上のバー ----

function renderTopbar(list: RunListView, row: RunRow | null): string {
  const dir = list.workDir === '' ? '' : `<span class="topbar-dim">作業フォルダ <code>${escapeHtml(list.workDir)}</code></span>`;
  const wt =
    row !== null && row.other
      ? `<span class="topbar-wt">別の worktree を表示中${row.branch === null ? '' : `：${escapeHtml(row.branch)}`}</span>`
      : '';
  return `<header class="topbar"><span class="topbar-name">pipe-in</span><span class="topbar-dim">実行を見る</span><span class="topbar-spacer"></span>${dir}${wt}</header>`;
}

// ---- 詳細の上の部分 ----

function renderBadge(row: RunRow): string {
  const cls = row.state === 'done' ? (row.result !== null && row.result !== '合格' ? 'is-failed' : 'is-done') : `is-${row.state}`;
  const wait =
    row.state === 'waiting' && row.waitingSec !== null
      ? ` <span class="elapsed" data-elapsed="${Math.floor(row.waitingSec)}">${formatDuration(row.waitingSec)}</span>`
      : '';
  return `<span class="badge ${cls}"><span class="badge-dot" aria-hidden="true"></span>${escapeHtml(stateWord(row))}${wait}</span>`;
}

/** 「⚠ 止まっているかも」のバッジ。is-stale が付くまで CSS で隠す。 */
function renderStaleBadge(stale: string): string {
  return stale === '' ? '' : `<span class="badge stale-badge"${stale}>${STALE_BADGE_WORD}</span>`;
}

/** 全体の経過の要素。数え上げる（live）ときだけ基準の秒（data-elapsed）を持たせる。無ければ「—」（要素を出さない）。 */
function renderElapsed(elapsed: Elapsed | null): string {
  if (elapsed === null) return DASH;
  const attr = elapsed.live ? ` data-elapsed="${Math.floor(elapsed.seconds)}"` : '';
  return `<span class="elapsed"${attr}>${formatDuration(elapsed.seconds)}</span>`;
}

function renderMeta(view: PipelineView, row: RunRow | null): string {
  const item = (label: string, body: string): string => `<span>${label} ${body}</span>`;
  const strong = (text: string): string => `<strong>${escapeHtml(text)}</strong>`;
  if (row === null) {
    return `<div class="detail-meta">${item('経過', `<strong>${renderElapsed(view.elapsed)}</strong>`)}${item('費用', strong(`$${view.totalCostUsd.toFixed(3)}`))}</div>`;
  }
  const sid = row.sessionId === null ? DASH : `<code>${escapeHtml(row.sessionId)}</code>`;
  return (
    '<div class="detail-meta">' +
    item('パイプ', strong(row.pipe)) +
    item('セッション ID', sid) +
    item('今の段', strong(row.stage)) +
    item('経過', `<strong>${renderElapsed(row.elapsed)}</strong>`) +
    item('費用', strong(row.costText)) +
    item('最後に動いた', strong(row.updatedText)) +
    '</div>'
  );
}

/** 1回目のバナーの文言：最終の結果・いま動いている段・次を待っている・記録なし。 */
function renderStatusLine(view: PipelineView): string {
  if (view.noRecords) {
    return `<p class="banner-msg">${escapeHtml(view.noRecords.message)}：${escapeHtml(view.noRecords.workDir)}</p>`;
  }
  if (view.final !== null) {
    const cls = view.final === 'PASSED' ? 'is-done' : 'is-failed';
    return `<p class="banner-msg ${cls}">最終の結果：${escapeHtml(view.final)}</p>`;
  }
  if (view.runningStage !== null && view.terminal.source !== null) {
    const src = view.terminal.source;
    const attempt = src.attempt === null ? '' : `（${src.attempt} 回目）`;
    return `<p class="banner-msg is-running">${escapeHtml(`いま：${stageLabel(view, src.stage)}${attempt}`)}</p>`;
  }
  if (view.pendingReview === null && view.waiting) return `<p class="banner-msg">${escapeHtml(WAITING_MESSAGE)}</p>`;
  return '';
}

/** 確認待ちの黄の知らせ。動いている段があるあいだ・終わったあとは出さない。 */
function renderNotice(view: PipelineView): string {
  if (view.noRecords || view.final !== null || view.runningStage !== null || view.pendingReview === null) return '';
  const { label, doc } = view.pendingReview;
  return (
    '<div class="notice" role="status">' +
    `<strong>${escapeHtml(`${label}の確認を待っている：${doc}`)}</strong>` +
    '<span class="notice-sub">読んで、承認か修正の依頼を返してください</span>' +
    '</div>'
  );
}

/**
 * 「この段のログが（時間）更新されていません。」の知らせ。プロセスは調べていないことと、長い段では動いていても更新されないことを添える。
 * 確認待ちの黄の知らせ（renderNotice）とは別の要素。is-stale が付くまで CSS で隠す。
 */
function renderStaleNotice(row: RunRow | null, stale: string): string {
  if (row === null || stale === '') return '';
  return (
    `<div class="notice stale-notice" role="status"${stale}>` +
    `<strong>${STALE_NOTICE_HEAD} ${staleTime(row.quietSec)} ${STALE_NOTICE_TAIL}</strong>` +
    `<span class="notice-sub">${STALE_NOTICE_SUB}</span>` +
    '</div>'
  );
}

function renderCrumbs(row: RunRow | null): string {
  if (row === null) return '<div class="crumbs"></div>';
  const parts = row.branch === null ? [row.pipe] : [row.branch, row.pipe];
  return `<div class="crumbs">${parts.map(escapeHtml).join(' › ')}</div>`;
}

function renderHead(row: RunRow | null, stale: string): string {
  const title = row === null ? '実行の記録' : row.session;
  const badge = row === null ? '' : renderBadge(row) + renderStaleBadge(stale);
  return (
    `<div class="head"><h1 class="head-title">${escapeHtml(title)}</h1>${badge}<span class="head-spacer"></span>` +
    '<button type="button" class="secondary" data-open-artifacts>成果物を開く</button></div>'
  );
}

// ---- 詳細のタブとパネル ----

// 詳細のタブ（図と出力・成果物・使用量）。
const DETAIL_TABS: readonly [string, string][] = [
  ['diagram', '図と出力'],
  ['artifacts', '成果物'],
  ['usage', '使用量'],
];

function renderTabs(): string {
  const buttons = DETAIL_TABS.map(
    ([key, label]) =>
      `<button type="button" role="tab" aria-selected="${key === 'diagram' ? 'true' : 'false'}" data-detail-tab="${key}" data-keep="detail-tab:${key}">${label}</button>`,
  );
  return `<div class="detail-tabs" role="tablist" aria-label="表示の切り替え">${buttons.join('')}</div>`;
}

/** タブパネル。scroll は、このパネル自身が実際にスクロールするとき、その位置を覚える印（data-scroll の値）。 */
function panel(key: string, body: string, scroll?: string): string {
  const hide = key === 'diagram' ? '' : ' hidden';
  const mark = scroll === undefined ? '' : ` data-scroll="${scroll}"`;
  return `<div class="tabpanel" role="tabpanel" data-detail-panel="${key}"${hide}${mark}>${body}</div>`;
}

function renderWarnings(warnings: string[]): string {
  if (warnings.length === 0) return '';
  const items = warnings.map((w) => `<li>${escapeHtml(w)}</li>`);
  return `<section><h2 class="terminal-title">注意</h2><ul class="warnings">${items.join('')}</ul></section>`;
}

function renderItem(item: OutputItem): string {
  if (item.kind === 'tool') {
    const target = item.target === null ? '' : ` ${item.target}`;
    return `<div class="line line-tool">${escapeHtml(`· ${item.tool}${target}`)}</div>`;
  }
  return `<div class="line">${escapeHtml(item.text)}</div>`;
}

function renderTerminal(view: PipelineView, terminal: TerminalView): string {
  const source = terminal.source;
  const title =
    source === null
      ? '出力（ログなし）'
      : `出力：${stageLabel(view, source.stage)}${source.attempt === null ? '' : `（${source.attempt} 回目）`}`;
  return (
    `<section class="pane-output"><h2 class="terminal-title">${escapeHtml(title)}</h2>` +
    `<div class="terminal" data-scroll="output">${terminal.items.map(renderItem).join('')}</div></section>`
  );
}

// 図の拡大縮小のボタン（D0019-AC-79）。倍率の文字と aria-label は panelScript.ts が倍率に合わせて書き換える。
const ZOOM_BAR =
  '<div class="zoom-bar" role="group" aria-label="図の大きさ">' +
  '<button type="button" data-zoom="out" data-keep="zoom:out" aria-label="図を小さく">−</button>' +
  '<button type="button" data-zoom="reset" data-keep="zoom:reset" aria-label="図の大きさを 100% に戻す（今 100%）">100%</button>' +
  '<button type="button" data-zoom="in" data-keep="zoom:in" aria-label="図を大きく">＋</button>' +
  '</div>';

function renderDiagramPanel(view: PipelineView, staleAfterSec: number | null): string {
  return (
    '<div class="split">' +
    `<div class="pane-diagram" data-scroll="diagram">${ZOOM_BAR}${renderFlowSvg(view.nodes, new Set(reasonNodeIds(view)), staleAfterSec)}` +
    `${renderWarnings(view.warnings)}${renderReasons(view)}${renderTimes(view)}</div>` +
    `<div class="pane-right">${renderTerminal(view, view.terminal)}` +
    `<section class="pane-gantt" data-scroll="gantt">${renderGantt(view.gantt, staleAfterSec)}</section></div>` +
    '</div>'
  );
}

/**
 * パネルの本体：上のバー・左の一覧・右の詳細。一覧は行が 0・1 つでも出す。
 * staleAfterSec は「止まっているかも」の目安の秒（D0021）。null なら更新なしの印は出さない。
 */
export function renderShell(view: PipelineView, list: RunListView, staleAfterSec: number | null = null): string {
  const row = list.rows.find((r) => r.key === list.selected) ?? null;
  // 選んだ行が動いていて、最後の更新からの秒と目安がそろうときの印の属性。バッジと知らせは、この有る無しでどちらも出すか、どちらも出さないかが決まる
  const stale = rowStaleAttrs(row, staleAfterSec);
  return (
    '<div class="app">' +
    renderTopbar(list, row) +
    '<div class="app-body">' +
    `<nav class="sidebar" aria-label="実行の一覧">${renderRunList(list, staleAfterSec)}</nav>` +
    '<main class="detail" data-scroll="detail">' +
    renderCrumbs(row) +
    renderHead(row, stale) +
    renderMeta(view, row) +
    renderStatusLine(view) +
    renderNotice(view) +
    renderStaleNotice(row, stale) +
    renderTabs() +
    panel('diagram', renderDiagramPanel(view, staleAfterSec)) +
    panel('artifacts', renderArtifacts(view), 'panel-artifacts') +
    panel('usage', renderUsage(view.usage)) +
    '</main></div></div>'
  );
}
