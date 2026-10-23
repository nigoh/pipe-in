// 「成果物」タブの中身：成果物の一覧（左）と、選んだ 1 つのプレビュー（右）の HTML の文字列（純粋）。D0025。
// 「ある」成果物すべてのプレビューを入れ、見えるのは選んだ 1 つだけ（ほかは hidden）。選びはパネルのスクリプトが持ち、ここは最初の選び（既定）だけを決める。
// 一覧の行は選ぶだけのボタン（data-art-pick）で、拡張へメッセージを送る元（data-artifact）は、プレビューの「エディタで開く」だけ。
// .md は renderMarkdown（許すタグだけ）で、ほかは pre の文字でそのまま出す。外から来た文字（名前・段の表示名・中身）はすべて escapeHtml を通し、向きを変える制御文字は U+FFFD にする。
// 中身の HTML の合計は PREVIEW_HTML_MAX_CHARS まで（超えたところから先のプレビューは中身を出さず、案内だけ）。
// 色は var(--vscode-*)、style= は使わない。幅の規則（@media (max-width）は shellHtml.ts の既存の 2 つの @media の中に書く。
import { ARTIFACT_MAX_BYTES, defaultArtifactName } from '../domain/artifacts.ts';
import type { ArtifactEntry } from '../domain/artifacts.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { escapeHtml } from './escape.ts';
import { renderMarkdown } from './markdownHtml.ts';

/** 成果物の欄の CSS（1101px 以上の形）。狭い幅の規則は shellHtml.ts の SHELL_STYLE の既存の 2 つの @media の中に書く（@media (max-width はここに書かない）。 */
export const ARTIFACTS_STYLE = `
.art { flex: 1 1 auto; min-height: 160px; min-width: 0; display: grid; grid-template-columns: clamp(200px, 28%, 300px) minmax(0, 1fr); grid-template-rows: minmax(0, 1fr); gap: 16px; }
.art-list { position: relative; min-height: 0; overflow: auto; list-style: none; margin: 0; padding: 4px; box-sizing: border-box; border: 1px solid var(--vscode-panel-border); border-radius: 6px; display: flex; flex-direction: column; gap: 2px; }
.art-item { flex: none; min-width: 0; margin: 0; padding: 0; }
.art-row { display: flex; flex-direction: column; gap: 2px; width: 100%; min-width: 0; min-height: 56px; box-sizing: border-box; padding: 6px 8px; text-align: left; font: inherit; color: var(--vscode-foreground); border: 1px solid transparent; border-radius: 4px; background: transparent; cursor: pointer; }
.art-row:not(:disabled):not([aria-pressed="true"]):hover { background: var(--vscode-list-hoverBackground); }
.art-row[aria-pressed="true"] { background: var(--vscode-list-activeSelectionBackground); border-color: var(--vscode-focusBorder); color: var(--vscode-list-activeSelectionForeground); }
.art-row[aria-pressed="true"] .art-file, .art-row[aria-pressed="true"] .art-meta { color: inherit; }
.art-row.is-missing { border-style: dashed; border-color: var(--vscode-descriptionForeground); color: var(--vscode-descriptionForeground); cursor: default; }
.art-row:focus-visible, .art-body:focus-visible { outline: 2px solid var(--vscode-focusBorder); outline-offset: -2px; }
.art-name, .art-file, .art-stage, .art-title { min-width: 0; overflow-wrap: anywhere; }
.art-name { font-weight: 600; }
.art-file { font-family: var(--vscode-editor-font-family, monospace); font-size: 11.5px; color: var(--vscode-descriptionForeground); }
.art-missing { font-size: 12px; font-weight: 600; }
.art-meta { display: flex; flex-wrap: wrap; gap: 2px 8px; min-width: 0; font-size: 12px; color: var(--vscode-descriptionForeground); }
.art-time { font-variant-numeric: tabular-nums; }
.art-previews { min-width: 0; min-height: 0; display: flex; flex-direction: column; }
.art-preview { flex: 1 1 auto; min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: 8px; }
.art-head { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; min-width: 0; }
.art-head .secondary { margin-left: auto; }
.art-title { margin: 0; font-size: 16px; font-weight: 600; }
.art-cut { margin: 0; padding: 6px 10px; border: 1px solid var(--vscode-charts-yellow, var(--vscode-foreground)); border-radius: 4px; background: var(--vscode-inputValidation-warningBackground, transparent); font-size: 12px; }
.art-body { flex: 1 1 auto; min-height: 96px; min-width: 0; overflow: auto; box-sizing: border-box; border: 1px solid var(--vscode-panel-border); border-radius: 6px; }
.art-empty, .art-omit { margin: 0; padding: 16px; color: var(--vscode-descriptionForeground); }
.art-plain { margin: 0; padding: 12px; white-space: pre-wrap; overflow-wrap: anywhere; font-family: var(--vscode-editor-font-family, monospace); font-size: 12px; }
.md { padding: 4px 16px 12px; line-height: 1.6; overflow-wrap: anywhere; }
.md h3, .md h4, .md h5, .md h6 { margin: 1.2em 0 0.5em; line-height: 1.3; }
.md h3 { font-size: 1.35em; }
.md h4 { font-size: 1.2em; }
.md h5 { font-size: 1.05em; }
.md h6 { font-size: 1em; color: var(--vscode-descriptionForeground); }
.md p, .md ul, .md ol, .md pre, .md blockquote, .md .md-table { margin: 0 0 0.8em; }
.md ul, .md ol { padding-left: 1.6em; }
.md li > ul, .md li > ol { margin: 0.2em 0 0; }
.md code { font-family: var(--vscode-editor-font-family, monospace); font-size: 0.92em; padding: 1px 4px; border-radius: 3px; background: var(--vscode-textCodeBlock-background); }
.md pre, .md .md-table { overflow-x: auto; }
.md pre { padding: 10px 12px; border-radius: 4px; background: var(--vscode-textCodeBlock-background); }
.md pre code { padding: 0; background: transparent; font-size: 12px; }
.md blockquote { padding: 2px 12px; border-left: 3px solid var(--vscode-descriptionForeground); }
.md hr { height: 0; margin: 1em 0; border: 0; border-top: 1px solid var(--vscode-descriptionForeground); }
.md table { border-collapse: collapse; overflow-wrap: normal; }
.md th, .md td { padding: 4px 10px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--vscode-descriptionForeground); }
.md th { font-weight: 600; }
.md .md-center { text-align: center; }
.md .md-right { text-align: right; }
`;

/** 切れた成果物のプレビューの見出しの下に出す案内。「256」は読む量の上限（ARTIFACT_MAX_BYTES）から作る。 */
export const CUT_NOTICE = `先頭 ${ARTIFACT_MAX_BYTES / 1024} KiB までを表示しています。続きはエディタで開いてください。`;

/**
 * 1 回の描き直しで作るプレビューの中身の HTML の長さの合計の上限（文字数）。
 * 読む量の上限（合計 4 MiB）に収まる入力でも、変換でふくらむ（引用の入れ子は約 14 倍、plain は escape で最大約 6 倍）ので、出す側でも抑える。
 * 超えたところから先のプレビューは、中身を出さずに OMIT_NOTICE だけを出す。
 */
export const PREVIEW_HTML_MAX_CHARS = 8 * 1024 * 1024;
/** 中身の HTML が上限を超えるため、中身を出さなかったプレビューの案内。 */
export const OMIT_NOTICE = '表示する量が多いので、このプレビューは省略しました。エディタで開いて読んでください。';

const DASH = '—';
const EMPTY_MESSAGE = 'まだ成果物がありません';

/** Markdown として直して出す成果物か（拡張子が .md。大文字小文字は問わない）。 */
export function isMarkdownName(name: string): boolean {
  return /\.md$/i.test(name);
}

/** 向きを変える制御文字（U+202A〜202E・U+2066〜2069）。見かけの順を入れ替えた名前や文書を作れないよう、画面に出すときは U+FFFD にする。 */
const BIDI_CONTROLS = /[\u{202A}-\u{202E}\u{2066}-\u{2069}]/gu;

/** 画面に出す名前（行・見出し・aria-label の文字）。data-* の名前は元のまま使う（openArtifact の名前が一覧の名前と合うように）。 */
export function displayName(name: string): string {
  return name.replace(BIDI_CONTROLS, '�');
}

/**
 * プレビューの中身の文字。名前と同じ置き換えをする。確認のために読む文書の見かけの順を、外から来た文字で入れ替えられないように
 * （エディタは見えない文字を目立たせるが、プレビューは目立たせないため）。長さは変わらない。
 */
function displayBody(text: string): string {
  return displayName(text);
}

/** 画面に出す文字を、向きの制御文字を直して escapeHtml に通す。 */
function shown(text: string): string {
  return escapeHtml(displayName(text));
}

/** 一覧の 1 行。「まだない」行は disabled（この語は 1 行に 1 回だけ）で、薄い見た目のクラスと「まだない」の文字が付く。 */
function renderRow(entry: ArtifactEntry, picked: boolean): string {
  const name = escapeHtml(entry.name);
  const cls = entry.ready ? 'art-row' : 'art-row is-missing';
  const off = entry.ready ? '' : ' disabled';
  const missing = entry.ready ? '' : '<span class="art-missing">まだない</span>';
  const stage = entry.stageLabel === null ? DASH : shown(entry.stageLabel);
  const time = entry.ready ? escapeHtml(entry.updatedText) : DASH;
  return (
    '<li class="art-item">' +
    `<button type="button" class="${cls}" data-art-pick="${name}" data-keep="art-row:${name}" aria-pressed="${picked ? 'true' : 'false'}"${off}>` +
    `<span class="art-name">${shown(entry.label)}</span><span class="art-file">${shown(entry.name)}</span>` +
    `${missing}<span class="art-meta"><span class="art-stage">${stage}</span><span class="art-time">${time}</span></span>` +
    '</button></li>'
  );
}

/**
 * プレビューの中身の HTML。.md は Markdown に直し、ほかは pre の文字で出す。向きを変える制御文字は直してから渡す。
 * pre の直後の改行は HTML の決まりで 1 つ捨てられるので、先頭に 1 つ足す（本文が空行で始まっても、空行の数が減らない）。
 */
function renderContent(entry: ArtifactEntry): string {
  const text = displayBody(entry.text);
  return isMarkdownName(entry.name) ? `<div class="md">${renderMarkdown(text)}</div>` : `<pre class="art-plain">\n${escapeHtml(text)}</pre>`;
}

/**
 * 「ある」成果物すべての中身を、PREVIEW_HTML_MAX_CHARS の中で作る。最初に見える（既定の選び）ものを先に作り、あとは一覧の順。
 * 作った HTML が残りの文字数に入らないものが出たら、そこで止める。そのものと、あとのものは入れない（返す表に無い）。
 * 止めるのは、入らないものを次々に変換して捨てて、変換の時間（拡張ホストの同期処理）をむだにしないため。
 * 入力は 1 つ最大 256 KiB で、出力はその 20 倍以内（AC-36）なので、最初の 1 つは必ず入る。
 */
function renderContents(ready: readonly ArtifactEntry[], picked: string | null): Map<ArtifactEntry, string> {
  const contents = new Map<ArtifactEntry, string>();
  let room = PREVIEW_HTML_MAX_CHARS;
  for (const entry of [...ready.filter((e) => e.name === picked), ...ready.filter((e) => e.name !== picked)]) {
    const content = renderContent(entry);
    if (content.length > room) break;
    room -= content.length;
    contents.set(entry, content);
  }
  return contents;
}

/** 「ある」成果物 1 つのプレビュー。選んだもの以外は hidden。切れた成果物は、見出しの下（枠の外）に案内を出す。content が無い（上限を超えた）ときは、枠の中に OMIT_NOTICE を出す。 */
function renderPreview(entry: ArtifactEntry, visible: boolean, content: string | undefined): string {
  const name = escapeHtml(entry.name);
  const label = shown(entry.label);
  const file = shown(entry.name);
  const hide = visible ? '' : ' hidden';
  const notice = entry.cut ? `<p class="art-cut">${CUT_NOTICE}</p>` : '';
  const body = content ?? `<p class="art-omit">${OMIT_NOTICE}</p>`;
  return (
    `<section class="art-preview" data-art-preview="${name}"${hide}>` +
    `<header class="art-head"><h2 class="art-title">${label}</h2><span class="art-file">${file}</span>` +
    `<button type="button" class="secondary" data-artifact="${name}" data-keep="art-open:${name}">エディタで開く</button></header>` +
    notice +
    `<div class="art-body" data-scroll="artifact" data-scroll-name="${name}" tabindex="0" role="region" aria-label="${label}（${file}）のプレビュー" data-keep="art-scroll:${name}">${body}</div>` +
    '</section>'
  );
}

/**
 * 「成果物」タブの中身。最初の選び（既定）は、動いている段（なければ確認待ちの段）の成果物が「ある」ならそれ、そうでなければ一覧の順で最後の「ある」。
 * 「ある」ものが 1 つも無いときは、選びもプレビューも作らず、「まだ成果物がありません」を出す。
 * 中身の HTML の合計が PREVIEW_HTML_MAX_CHARS を超えるときは、超えたところから先のプレビューは中身を出さずに案内だけを出す。
 */
export function renderArtifacts(view: Pick<PipelineView, 'artifacts' | 'runningStage' | 'pendingReview'>): string {
  const picked = defaultArtifactName(view.artifacts, view.runningStage ?? view.pendingReview?.stage ?? null);
  const rows = view.artifacts.map((entry) => renderRow(entry, entry.ready && entry.name === picked));
  const ready = view.artifacts.filter((entry) => entry.ready);
  const contents = renderContents(ready, picked);
  const previews =
    ready.length === 0 ? `<p class="art-empty">${EMPTY_MESSAGE}</p>` : ready.map((entry) => renderPreview(entry, entry.name === picked, contents.get(entry))).join('');
  const attr = picked === null ? '' : ` data-art-default="${escapeHtml(picked)}"`;
  return (
    `<div class="art"${attr}>` +
    `<ul class="art-list" data-scroll="artifact-list" aria-label="成果物の一覧">${rows.join('')}</ul>` +
    `<div class="art-previews">${previews}</div>` +
    '</div>'
  );
}
