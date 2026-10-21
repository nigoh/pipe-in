// 時系列（ガントチャート）のモデル → HTML の文字列（純粋）。D0019。
// HTML の並び（グリッド）で描く。行の名前・時間の文字は HTML で、元の大きさの px。枠の幅に合わせて伸び縮みするのは位置と幅だけ（% で表す）。
// - 帯：行ごとの細い SVG（viewBox の幅は 100 = 全体、preserveAspectRatio="none"）。rect の x / width が全体に対する割合（%）。中に文字は入れない。
// - 文字（目盛り・時間・確認待ち）：HTML の span。位置は 1% 刻みの決まったクラス（.x37 = 左から 37%、.r37 = 右から 37%）で、規則は GANTT_STYLE にある。
// style 属性も、外から来た文字の入る CSS も使わない（CSP は nonce のスタイルだけを許す）。色と模様はクラスと var(--vscode-*)。
// 外から来た文字（段の表示名・受け持ち）はすべて escapeHtml を通す。動き（animation）は足さない。
// 動いている帯で段のログが目安の時間動かないとき（D0021）は、行に印の属性を持たせ、普段の文字（g-calm）と印つきの文字（g-stalled）の両方を出す。
// パネルのスクリプトが行に is-stale を付けると、CSS が 2 つを入れ替え、輪を点線にする。帯の形と色は替えない。
import type { GanttModel, GanttRow } from '../domain/gantt.ts';
import { formatDuration } from './duration.ts';
import { escapeHtml } from './escape.ts';
import { STALE_WORD, staleAttrs } from './staleMark.ts';

/** 0〜100% を 1% 刻みで並べた位置のクラス（左から .x、右から .r）。 */
function positionClasses(): string {
  const lines: string[] = [];
  for (let n = 0; n <= 100; n++) lines.push(`.x${n} { left: ${n}%; }`, `.r${n} { right: ${n}%; }`);
  return lines.join('\n');
}

export const GANTT_STYLE = `
.gantt-lead { margin: 0 0 4px; color: var(--vscode-descriptionForeground); font-variant-numeric: tabular-nums; }
.gantt-none { margin: 0; color: var(--vscode-descriptionForeground); }
.gantt { display: block; font-family: var(--vscode-font-family); font-size: 11px; font-variant-numeric: tabular-nums; color: var(--vscode-foreground); }
.g-row, .g-axisrow { display: grid; grid-template-columns: minmax(0, 30%) minmax(0, 1fr); column-gap: 8px; align-items: center; min-height: 26px; }
.g-row { border-top: 1px solid var(--vscode-panel-border); }
.g-axisrow { min-height: 20px; }
.g-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.g-track { position: relative; height: 16px; margin-right: 18px; }
.g-axisrow .g-track { height: 18px; }
.g-defs { position: absolute; width: 0; height: 0; overflow: hidden; }
.g-bars { display: block; width: 100%; height: 16px; overflow: visible; }
.g-axis { color: var(--vscode-descriptionForeground); }
.g-tick { position: absolute; top: 0; transform: translateX(-50%); white-space: nowrap; }
.g-note { color: var(--vscode-descriptionForeground); font-style: italic; }
.g-omit { margin: 0 0 4px; color: var(--vscode-descriptionForeground); font-style: italic; }
.g-run { fill: var(--vscode-charts-blue); }
.g-fail { fill: var(--vscode-charts-red, var(--vscode-errorForeground)); }
.g-wait { fill: url(#gantt-hatch); stroke: var(--vscode-charts-yellow, var(--vscode-foreground)); stroke-width: 1.2; vector-effect: non-scaling-stroke; }
.g-hatch-line { stroke: var(--vscode-charts-yellow, var(--vscode-foreground)); stroke-width: 2; }
.g-ring { fill: none; stroke: var(--vscode-focusBorder, var(--vscode-foreground)); stroke-width: 1.6; vector-effect: non-scaling-stroke; }
.g-text { position: absolute; top: 0; line-height: 16px; white-space: nowrap; paint-order: stroke; -webkit-text-stroke: 3px var(--vscode-editor-background); }
.g-text[data-side="right"] { margin-left: 4px; }
.g-text[data-side="left"] { margin-right: 4px; }
.g-in { transform: translateX(-50%); color: var(--vscode-editor-background); font-weight: 600; -webkit-text-stroke: 0; }
.g-key { display: flex; flex-wrap: wrap; gap: 4px 16px; margin-top: 6px; color: var(--vscode-descriptionForeground); }
.g-key span { display: inline-flex; align-items: center; gap: 6px; }
.key-run, .key-wait, .key-fail { display: inline-block; width: 14px; height: 10px; border-radius: 2px; }
.key-run { background: var(--vscode-charts-blue); }
.key-wait { background: repeating-linear-gradient(45deg, transparent 0, transparent 2px, var(--vscode-charts-yellow, var(--vscode-foreground)) 2px, var(--vscode-charts-yellow, var(--vscode-foreground)) 4px); outline: 1px solid var(--vscode-charts-yellow, var(--vscode-foreground)); outline-offset: -1px; }
.key-fail { background: var(--vscode-charts-red, var(--vscode-errorForeground)); }
.g-stalled { display: none; }
.g-row.is-stale .g-stalled { display: block; }
.g-row.is-stale .g-calm { display: none; }
.g-row.is-stale .g-ring { stroke-dasharray: 4 3; }
${positionClasses()}
`;

const NAME_LIMIT = 26;
/** 帯の右端がこの割合（%）を超えたら、文字は帯の左に置く（右に出すと枠の外へ出るため）。 */
const SIDE_LIMIT = 85;
/** 帯がこの割合（%）以上なら、時間の文字を帯の中に入れる。 */
const INSIDE_MIN = 12;
/** 「● 動いている」も帯の中に入れるときの最小の割合（%）。 */
const INSIDE_LIVE_MIN = 28;
/** 「● 動いている ⚠ 更新なし」は長いので、帯の中に入れるときの最小の割合（%）を上げる。これより短い帯では帯の外に出す。 */
const INSIDE_STALE_MIN = 55;
/** 帯の幅の下限（%）。長さ 0 の帯も見えるように。 */
const MIN_BAR = 0.3;

function clip(text: string): string {
  const points = Array.from(text);
  return points.length <= NAME_LIMIT ? text : `${points.slice(0, NAME_LIMIT).join('')}…`;
}

const round = (n: number): number => Math.round(n * 1000) / 1000;

/** 秒 → 全体に対する割合（%）。0〜100 に収める。 */
function pct(sec: number, total: number): number {
  if (!(total > 0)) return 0;
  return round(Math.min(Math.max((sec / total) * 100, 0), 100));
}

interface Bar {
  left: number;
  width: number;
  end: number;
}

function barOf(startSec: number, endSec: number, total: number): Bar {
  const left = pct(startSec, total);
  const end = pct(endSec, total);
  const width = Math.min(Math.max(round(end - left), MIN_BAR), 100 - left > MIN_BAR ? 100 - left : MIN_BAR);
  return { left, end, width };
}

const sideOf = (b: Bar): 'left' | 'right' => (b.end > SIDE_LIMIT ? 'left' : 'right');

/** 帯の外に置く文字（右なら帯の右端から、左なら帯の左端の手前から）。extra は足すクラス（先頭に空白を置く）。 */
function sideText(b: Bar, body: string, extra = ''): string {
  const side = sideOf(b);
  const pos = side === 'right' ? `x${Math.round(b.end)}` : `r${Math.round(100 - b.left)}`;
  return `<span class="g-text ${pos}${extra}" data-side="${side}">${escapeHtml(body)}</span>`;
}

/** 帯の中に置く文字（帯の真ん中）。extra は足すクラス（先頭に空白を置く）。 */
function insideText(b: Bar, body: string, extra = ''): string {
  return `<span class="g-text g-in x${Math.round(b.left + b.width / 2)}${extra}">${escapeHtml(body)}</span>`;
}

function rect(cls: string, b: Bar): string {
  return `<rect class="${cls}" x="${b.left}" y="0" width="${b.width}" height="16"/>`;
}

function renderRow(row: GanttRow, total: number, staleAfterSec: number | null): string {
  const full = row.agent === null ? row.label : `${row.label} · ${row.agent}`;
  const label = `<span class="g-label" title="${escapeHtml(full)}">${escapeHtml(clip(full))}</span>`;
  // 動いている帯で、最後の更新からの秒と目安がそろうときだけ印の属性を持つ（帯の無い行・終わった帯・目安なしは今までの行のまま）
  const stale = row.run !== null && row.run.live ? staleAttrs(row.run.quietSec, staleAfterSec) : '';
  const open = `<div class="g-row"${stale}>${label}<div class="g-track">`;

  if (row.run === null) return `${open}<span class="g-note">時刻の記録なし</span></div></div>`;

  const { run, wait } = row;
  const shapes: string[] = [];
  const texts: string[] = [];

  const rb = barOf(run.startSec, run.endSec, total);
  shapes.push(rect(run.failed ? 'g-run g-fail' : 'g-run', rb));
  if (run.live) shapes.push(rect('g-ring', rb));
  const time = `${run.failed ? '✕ ' : ''}${formatDuration(run.endSec - run.startSec)}`;
  const runText = run.live ? `${time} ● 動いている` : time;
  // 印があるときは、普段の文字（g-calm）と印つきの文字（g-stalled）の両方を持ち、is-stale で入れ替える。
  // 普段の文字の置き場所は今までどおり（目安の手前の見え方を変えない）。印つきの文字は長いので、帯の中に入れる幅の下限を上げる
  const calm = stale === '' ? '' : ' g-calm';
  if (rb.width >= (run.live ? INSIDE_LIVE_MIN : INSIDE_MIN)) {
    texts.push(insideText(rb, runText, calm));
  } else {
    texts.push(sideText(rb, runText, calm));
  }
  if (stale !== '') {
    const stalledText = `${runText} ${STALE_WORD}`;
    texts.push(rb.width >= INSIDE_STALE_MIN ? insideText(rb, stalledText, ' g-stalled') : sideText(rb, stalledText, ' g-stalled'));
  }

  if (wait !== null) {
    const wb = barOf(wait.startSec, wait.endSec, total);
    shapes.push(rect('g-wait', wb));
    if (wait.live) shapes.push(rect('g-ring', wb));
    texts.push(sideText(wb, `確認待ち ${formatDuration(wait.endSec - wait.startSec)}${wait.live ? ' ● 待っている' : ''}`));
  }

  const bars = `<svg class="g-bars" viewBox="0 0 100 16" preserveAspectRatio="none" aria-hidden="true">${shapes.join('')}</svg>`;
  return `${open}${bars}${texts.join('')}</div></div>`;
}

function renderAxis(g: GanttModel): string {
  const ticks = g.ticks.map((t) => `<span class="g-axis g-tick x${Math.round(pct(t, g.totalSec))}">${escapeHtml(formatDuration(t))}</span>`);
  return `<div class="g-axisrow"><span></span><div class="g-track">${ticks.join('')}</div></div>`;
}

const DEFS =
  '<svg class="g-defs" width="0" height="0" aria-hidden="true"><defs><pattern id="gantt-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line class="g-hatch-line" x1="0" y1="0" x2="0" y2="6"/></pattern></defs></svg>';

const KEY =
  '<div class="g-key"><span><i class="key-run"></i>エージェント</span><span><i class="key-wait"></i>確認待ち</span><span><i class="key-fail"></i>不合格</span></div>';

/**
 * 時系列の節（見出し・件数と合計・本体）。時刻が一つも取れないときは、本体を描かず文で知らせる。
 * staleAfterSec は「止まっているかも」の目安の秒（D0021）。null なら更新なしの印は出さない。
 */
export function renderGantt(g: GanttModel, staleAfterSec: number | null = null): string {
  const head = '<h2 class="terminal-title">時系列</h2>';
  if (!g.hasTimes) return `${head}<p class="gantt-none">時刻の記録がありません</p>`;

  const count = g.rows.length + g.omittedRows;
  const lead = `<p class="gantt-lead">${count} 回の実行・合計 ${formatDuration(g.totalSec)}</p>`;
  const omit = g.omittedRows > 0 ? `<p class="g-omit">前の ${g.omittedRows} 行を省いています</p>` : '';
  const rows = g.rows.map((row) => renderRow(row, g.totalSec, staleAfterSec)).join('');
  return `${head}${lead}<div class="gantt" role="group" aria-label="時系列">${DEFS}${omit}${renderAxis(g)}${rows}${KEY}</div>`;
}
