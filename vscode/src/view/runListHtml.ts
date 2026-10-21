// 実行の一覧（左の欄）→ HTML の文字列（純粋）。D0019。
// 上から、絞り込みの入力・状態のタブ・状態ごとの見出し・行・省いた件数の文字。行は 3 行（セッション名と日付／パイプ名 · ブランチ · 状態 · 今の段／セッション ID）。
// 色は var(--vscode-*)、CSS はクラスだけ。外から来た文字（セッション名・パイプ名・段の名前・結果・ブランチ名・セッション ID・key）はすべて escapeHtml を通す。
// 確認待ちの行は、黄の枠と「確認待ち」の文字と待ち時間で目立たせる（色だけに頼らない）。待ち時間・経過は D0017 の数え上げ（data-elapsed）に乗せる。
// 点滅は prefers-reduced-motion: no-preference の中だけ。動きを減らす設定では、枠・色・文字で分かり、待ち時間は数え続ける。
// 動いている行で段のログが目安の時間動かないときは、3 行目の右に「⚠ 更新なし」と時間を出し、枠を点線にする（D0021。staleMark.ts）。
// 印は最初は隠れていて、パネルのスクリプトが行に is-stale を付けると見える。状態の言葉・見出し・タブ・並びは替えない。
// 絞り込みとタブの出し分けはパネルのスクリプトがする（拡張へは送らない）。ここは全部の行を出し、出し分けの印（data-*）だけ持たせる。
import { countStates, omittedText, stateWord } from '../domain/runList.ts';
import type { RunListView, RunRow, RunState } from '../domain/runList.ts';
import { formatDuration } from './duration.ts';
import { escapeHtml } from './escape.ts';
import { STALE_COLOR, STALE_WORD, rowStaleAttrs, staleTime } from './staleMark.ts';

export const RUN_LIST_STYLE = `
.sr-only { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
.run-list { display: flex; flex-direction: column; gap: 10px; min-height: 0; height: 100%; }
.run-search { display: flex; align-items: center; height: 32px; box-sizing: border-box; padding: 0 10px; border: 1px solid var(--vscode-panel-border); border-radius: 6px; background: var(--vscode-input-background); color: var(--vscode-descriptionForeground); flex: none; }
.run-search:focus-within { border-color: var(--vscode-focusBorder); }
.run-search input { flex: 1; min-width: 0; border: 0; outline: none; background: transparent; color: var(--vscode-input-foreground, var(--vscode-foreground)); font: inherit; }
.run-tabs { display: flex; flex-wrap: wrap; gap: 4px; flex: none; }
.run-tabs button { display: inline-flex; align-items: center; gap: 6px; min-height: 28px; padding: 2px 10px; border: 1px solid var(--vscode-panel-border); border-radius: 999px; background: transparent; color: var(--vscode-foreground); font: inherit; font-size: 12px; cursor: pointer; }
.run-tabs button[aria-selected="true"] { background: var(--vscode-button-background); border-color: var(--vscode-button-background); color: var(--vscode-button-foreground); }
.run-tabs button:focus-visible { outline: 2px solid var(--vscode-focusBorder); outline-offset: 1px; }
.run-tabs .count { font-size: 11px; font-variant-numeric: tabular-nums; opacity: 0.85; }
.run-scroll { flex: 1 1 auto; min-height: 0; overflow: auto; display: flex; flex-direction: column; gap: 14px; }
.run-group { display: flex; flex-direction: column; gap: 2px; }
.run-group-head { margin: 0; padding: 0 8px 4px; font-size: 11px; font-weight: 600; letter-spacing: 0.04em; color: var(--vscode-descriptionForeground); }
.run-rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.run-row { display: flex; flex-direction: column; gap: 2px; width: 100%; min-height: 44px; box-sizing: border-box; padding: 6px 8px; font: inherit; text-align: left; color: var(--vscode-foreground); background: transparent; border: 1px solid transparent; border-radius: 6px; cursor: pointer; }
.run-row:hover { background: var(--vscode-list-hoverBackground); }
.run-row[aria-pressed="true"] { background: var(--vscode-list-activeSelectionBackground); color: var(--vscode-list-activeSelectionForeground, var(--vscode-foreground)); outline: 2px solid var(--vscode-focusBorder); outline-offset: -2px; }
.run-row:focus-visible { outline: 2px solid var(--vscode-focusBorder); outline-offset: -2px; }
.run-row.is-waiting { border: 2px solid var(--vscode-charts-yellow, var(--vscode-foreground)); }
.run-top { display: flex; align-items: center; gap: 8px; min-width: 0; }
.run-dot { width: 8px; height: 8px; border-radius: 50%; flex: none; background: var(--vscode-descriptionForeground); }
.run-row.is-waiting .run-dot { background: var(--vscode-charts-yellow, var(--vscode-foreground)); }
.run-row.is-running .run-dot { background: var(--vscode-charts-blue); }
.run-row.is-done .run-dot { background: var(--vscode-charts-green); }
.run-row.is-failed .run-dot { background: var(--vscode-charts-red, var(--vscode-errorForeground)); }
.run-session { flex: 1; min-width: 0; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.run-right { display: inline-flex; align-items: baseline; gap: 8px; flex: none; font-size: 12px; font-variant-numeric: tabular-nums; color: var(--vscode-descriptionForeground); }
.run-wait { color: var(--vscode-charts-yellow, var(--vscode-foreground)); font-weight: 700; }
.run-wait .elapsed, .run-right .elapsed { color: inherit; }
.run-sub { padding-left: 16px; font-size: 12px; color: var(--vscode-descriptionForeground); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.run-id { padding-left: 16px; font-size: 11px; color: var(--vscode-descriptionForeground); font-family: var(--vscode-editor-font-family, monospace); }
.run-foot { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0 8px; }
.run-stale { display: none; margin-left: auto; font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; color: var(--vscode-foreground); }
.run-row.is-stale { border-style: dashed; border-color: ${STALE_COLOR}; }
.run-row.is-stale .run-stale { display: inline; }
.run-row.is-stale[aria-pressed="true"] { outline-style: dashed; }
.run-empty, .run-none { margin: 0; padding: 0 8px; color: var(--vscode-descriptionForeground); }
.run-omitted { margin: 0; padding: 0 8px; color: var(--vscode-descriptionForeground); font-size: 12px; }
@media (prefers-reduced-motion: no-preference) {
  .run-row.is-waiting { animation: run-attention 2.4s ease-in-out infinite; }
  @keyframes run-attention { 50% { box-shadow: 0 0 0 2px var(--vscode-charts-yellow, var(--vscode-foreground)); } }
}
`;

// 状態のタブ。
const TABS: readonly [string, string][] = [
  ['all', 'すべて'],
  ['waiting', '確認待ち'],
  ['running', '動いている'],
  ['done', '終わった'],
];

const GROUPS: readonly [string, string][] = [
  ['waiting', '確認待ち'],
  ['running', '動いている'],
  ['done', '終わった'],
];

/** 見出し・タブの区分。待ち（idle）は「動いている」に入れる。 */
function groupOf(state: RunState): string {
  return state === 'idle' ? 'running' : state;
}

function rowClass(row: RunRow): string {
  const classes = ['run-row', `is-${row.state}`];
  if (row.state === 'done' && row.result !== null && row.result !== '合格') classes.push('is-failed');
  if (row.other) classes.push('is-other');
  return classes.join(' ');
}

/** 1 行目の右側：確認待ちは待ち時間、動いている・終わった行は経過。最後に動いた日付。 */
function renderRight(row: RunRow): string {
  let first = '';
  if (row.state === 'waiting') {
    if (row.waitingSec !== null) {
      first = `<span class="run-wait">待ち <span class="elapsed" data-elapsed="${Math.floor(row.waitingSec)}">${formatDuration(row.waitingSec)}</span></span>`;
    }
  } else if (row.elapsed !== null) {
    const inner = row.elapsed.live
      ? `<span class="elapsed" data-elapsed="${Math.floor(row.elapsed.seconds)}">${formatDuration(row.elapsed.seconds)}</span>`
      : formatDuration(row.elapsed.seconds);
    first = `<span class="run-elapsed">${inner}</span>`;
  }
  return `<span class="run-right">${first}<span class="run-date">${escapeHtml(row.updatedDate)}</span></span>`;
}

/** 2 行目：パイプ名 · ブランチ · 別の worktree · 前の実行 · 状態 · 今の段。 */
function renderSub(row: RunRow): string {
  const parts = [row.pipe];
  if (row.branch !== null) parts.push(row.branch);
  if (row.other) parts.push('別の worktree');
  if (row.previous) parts.push('前の実行');
  parts.push(stateWord(row), row.stage);
  return `<span class="run-sub">${parts.map(escapeHtml).join(' · ')}</span>`;
}

/**
 * 3 行目（セッション ID の行）。印が出る行だけ run-foot で包み、ID の右に印を置く（1 行目のセッション名は詰めない）。
 * 印が出ない行は今までと 1 文字も変えない。
 */
function renderFoot(row: RunRow, id: string, stale: string): string {
  const idEl = `<span class="run-id">${id}</span>`;
  if (stale === '') return idEl;
  return `<span class="run-foot">${idEl}<span class="run-stale">${STALE_WORD} ${staleTime(row.quietSec)}</span></span>`;
}

function renderRow(row: RunRow, selected: string, staleAfterSec: number | null): string {
  const marks =
    `data-group="${groupOf(row.state)}" data-sid="${escapeHtml(row.sessionId ?? '')}" data-branch="${escapeHtml(row.branch ?? '')}" data-name="${escapeHtml(row.session)}"`;
  const id = row.sessionId === null ? '—' : escapeHtml(Array.from(row.sessionId).slice(0, 8).join(''));
  // 動いている行だけが印の対象（確認待ち・待ち・終わった・前の実行には出さない）
  const stale = rowStaleAttrs(row, staleAfterSec);
  return (
    `<li ${marks}><button type="button" class="${rowClass(row)}" data-run="${escapeHtml(row.key)}" aria-pressed="${row.key === selected ? 'true' : 'false'}"${stale}>` +
    `<span class="run-top"><span class="run-dot" aria-hidden="true"></span><span class="run-session">${escapeHtml(row.session)}</span>${renderRight(row)}</span>` +
    `${renderSub(row)}${renderFoot(row, id, stale)}` +
    '</button></li>'
  );
}

function renderGroup(key: string, title: string, rows: readonly RunRow[], selected: string, staleAfterSec: number | null): string {
  const mine = rows.filter((r) => groupOf(r.state) === key);
  if (mine.length === 0) return '';
  const items = mine.map((r) => renderRow(r, selected, staleAfterSec)).join('');
  return `<section class="run-group" data-group="${key}"><h2 class="run-group-head">${title}</h2><ul class="run-rows">${items}</ul></section>`;
}

function renderOmitted(list: RunListView): string {
  const notes: string[] = [];
  for (const { place, count } of list.omitted) {
    const text = omittedText(count);
    if (text === '') continue;
    const where = place === null ? '' : `<span>${escapeHtml(place)}：</span>`;
    notes.push(`<p class="run-omitted">${where}${text}</p>`);
  }
  if (list.omittedWorktrees > 0) notes.push(`<p class="run-omitted">別の worktree を ${Math.floor(list.omittedWorktrees)} 個、省いています</p>`);
  return notes.join('');
}

function renderTabs(rows: readonly RunRow[]): string {
  const counts = countStates(rows);
  const buttons = TABS.map(([key, label]) => {
    const n = counts[key as keyof typeof counts];
    return `<button type="button" role="tab" aria-selected="${key === 'all' ? 'true' : 'false'}" data-list-tab="${key}" data-keep="list-tab:${key}">${label}<span class="count">${n}</span></button>`;
  });
  return `<div class="run-tabs" role="tablist" aria-label="状態で絞り込む">${buttons.join('')}</div>`;
}

/**
 * 実行の一覧。行を並べ替えない（渡された順のまま）。選んでいる行だけ aria-pressed="true"。行が 0 でも出す。
 * staleAfterSec は「止まっているかも」の目安の秒（D0021）。null なら更新なしの印は出さない。
 */
export function renderRunList(list: RunListView, staleAfterSec: number | null = null): string {
  const search =
    '<label class="run-search"><span class="sr-only">実行を絞り込む</span>' +
    '<input type="search" data-keep="filter" placeholder="セッション名・ID・ブランチで絞り込む" autocomplete="off"></label>';
  const groups = GROUPS.map(([key, title]) => renderGroup(key, title, list.rows, list.selected, staleAfterSec)).join('');
  const empty = list.rows.length === 0 ? '<p class="run-none">実行がありません</p>' : '<p class="run-empty" hidden>該当する実行がありません</p>';
  return (
    `<div class="run-list">${search}${renderTabs(list.rows)}` +
    `<div class="run-scroll" data-scroll="list">${groups}${empty}${renderOmitted(list)}</div></div>`
  );
}
