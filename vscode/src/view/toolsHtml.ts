// 使ったエージェント・スキル・道具の表（ToolsTable）→ パネルの「エージェント・スキル」のタブの中身の HTML（純粋。D0049）。
// 外から来た文字（名前・段の表示名）は escapeHtml を、表示と属性（title）にそれぞれ 1 回だけ通す。style=・on…=・src・href は出さない。
// 表を包む枠は、キーボードだけで横にスクロールできるよう tabindex="0"・role="region"。位置を覚える印（data-scroll）と焦点を戻す印（data-keep）はパネルのスクリプトが使う。
// 並べ替えは表を作る側（domain/toolsTable.ts）が済ませてある。ここは渡された順に出す。色は var(--vscode-*) だけ、CSS に @media は書かない（幅の規則は shellHtml.ts の既存の 2 つ）。
import type { ToolsRow, ToolsTable } from '../domain/toolsTable.ts';
import { formatDuration } from './duration.ts';
import { escapeHtml } from './escape.ts';

export const TOOLS_STYLE = `
.tools { min-width: 0; }
.tools-summary { margin: 0 0 6px; color: var(--vscode-descriptionForeground); }
.tools-notice { margin: 0 0 8px; padding: 6px 10px; border-left: 3px solid var(--vscode-descriptionForeground); color: var(--vscode-descriptionForeground); overflow-wrap: anywhere; }
.tools-scroll { min-width: 0; overflow-x: auto; }
.tools-scroll:focus-visible { outline: 2px solid var(--vscode-focusBorder); outline-offset: -2px; }
.tools-table { width: 100%; min-width: 30em; border-collapse: collapse; font-variant-numeric: tabular-nums; font-size: 0.92em; }
.tools-table th, .tools-table td { padding: 2px 6px; border-bottom: 1px solid var(--vscode-panel-border); text-align: left; vertical-align: top; }
.tools-table th { font-weight: 600; color: var(--vscode-descriptionForeground); background: var(--vscode-editorWidget-background); white-space: nowrap; }
.tools-name, .tools-stages { overflow-wrap: anywhere; }
.tools-kind, .tools-count, .tools-time { white-space: nowrap; }
.tools-count, .tools-time { text-align: right; }
.tools-omit, .tools-empty { margin: 6px 0 0; color: var(--vscode-descriptionForeground); }
`;

const TITLE = 'エージェント・スキル・道具';
const FRAME_LABEL = '使ったエージェント・スキル・道具の表';
const NOTICE_A =
  'この記録は外の会話（/pipe-in のスキル）で進めたので、スキルや道具の呼び出しは記録に残りません。記録にある段の受け持ち（record begin --agent）を、エージェントの行として出しています。';
const NOTICE_B =
  'この記録は外の会話（/pipe-in のスキル）で進めたので、スキルや道具の呼び出しは記録に残りません。段の受け持ち（record begin --agent）も記録に無いので、出せるものがありません。';
const EMPTY = 'エージェント・スキル・道具の呼び出しは、まだ記録にありません。';

const KIND_WORDS: Readonly<Record<ToolsRow['kind'], string>> = { agent: 'エージェント', skill: 'スキル', tool: '道具' };
const DASH = '—';
const SEPARATOR = '、';

/** 表に並べる使った段の数。超えた分は「ほか N 件」にする */
const STAGES_SHOWN = 3;
/** title に入れる使った段の長さの上限（コードポイント）。末尾の「、ほか N 件」は数えない */
const TITLE_MAX = 200;

/** 使った段の欄の文字：先頭 3 つを「、」でつなぎ、4 つ以上なら「、ほか N 件」（N は 3 を引いた数）。 */
function stagesText(stages: readonly string[]): string {
  if (stages.length <= STAGES_SHOWN) return stages.join(SEPARATOR);
  return `${stages.slice(0, STAGES_SHOWN).join(SEPARATOR)}${SEPARATOR}ほか ${stages.length - STAGES_SHOWN} 件`;
}

/** 使った段の全部を「、」でつないだ title。200 文字（コードポイント）を超えるときは、収まる分までと「、ほか N 件」。つなぎながら打ち切る。 */
function stagesTitle(stages: readonly string[]): string {
  let text = '';
  let length = 0;
  let fit = 0;
  for (const label of stages) {
    // 1 コードポイントは 2 コードユニット以下なので、401 コードユニット以上なら必ず 200 文字を超える（長い値を分けて数えない）
    if (label.length > TITLE_MAX * 2) break;
    const add = (fit === 0 ? 0 : SEPARATOR.length) + Array.from(label).length;
    if (length + add > TITLE_MAX) break;
    text += (fit === 0 ? '' : SEPARATOR) + label;
    length += add;
    fit += 1;
  }
  if (fit === stages.length) return text;
  const rest = `ほか ${stages.length - fit} 件`;
  return fit === 0 ? rest : `${text}${SEPARATOR}${rest}`;
}

function renderStagesCell(stages: readonly string[]): string {
  const title = stages.length > STAGES_SHOWN ? ` title="${escapeHtml(stagesTitle(stages))}"` : '';
  return `<td class="tools-stages"${title}>${escapeHtml(stagesText(stages))}</td>`;
}

function renderRow(row: ToolsRow, showTime: boolean): string {
  const time = showTime ? `<td class="tools-time">${row.durationSec === null ? DASH : formatDuration(row.durationSec)}</td>` : '';
  return (
    `<tr><td class="tools-name">${escapeHtml(row.name)}</td><td class="tools-kind">${KIND_WORDS[row.kind]}</td>` +
    `<td class="tools-count">${row.count}</td>${time}${renderStagesCell(row.stages)}</tr>`
  );
}

function renderTable(tools: ToolsTable): string {
  const time = tools.showTime ? '<th scope="col">時間</th>' : '';
  const head = `<thead><tr><th scope="col">名前</th><th scope="col">種類</th><th scope="col">回数</th>${time}<th scope="col">使った段</th></tr></thead>`;
  const body = `<tbody>${tools.rows.map((row) => renderRow(row, tools.showTime)).join('')}</tbody>`;
  return (
    `<div class="tools-scroll" data-scroll="tools-table" data-keep="tools-table" tabindex="0" role="region" aria-label="${FRAME_LABEL}">` +
    `<table class="tools-table">${head}${body}</table></div>`
  );
}

const notice = (text: string): string => `<p class="tools-notice" role="note">${text}</p>`;

/**
 * 「エージェント・スキル」のタブの中身。
 * 行があれば（案内 A・）要約・表（・省いた数）、行が無くて案内 B なら案内 B だけ、そのほか（tools が null・無いときも）空の文だけ。見出しはどの場合も出す。
 */
export function renderTools(tools: ToolsTable | null | undefined): string {
  let body: string;
  if (tools !== null && tools !== undefined && tools.rows.length > 0) {
    const lead = tools.notice === 'A' ? notice(NOTICE_A) : '';
    const summary = `<p class="tools-summary">${tools.kinds} 種類・合計 ${tools.total} 回</p>`;
    const omit = tools.omitted > 0 ? `<p class="tools-omit">ほか ${tools.omitted} 種類を省いています</p>` : '';
    body = `${lead}${summary}${renderTable(tools)}${omit}`;
  } else if (tools !== null && tools !== undefined && tools.notice === 'B') {
    body = notice(NOTICE_B);
  } else {
    body = `<p class="tools-empty">${EMPTY}</p>`;
  }
  return `<section class="tools"><h2 class="terminal-title">${TITLE}</h2>${body}</section>`;
}
