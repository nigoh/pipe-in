// 画面の確認用のページのうち、ページの中身を決める部分（副作用なし。out/ に書くのは preview.ts だけ）。
// テーマの色（--vscode-* の仮の値）と、「実行を見る」パネルのページの組み立てをここに置き、テストから import する。
// パネルのページは、画面用の見本の記録（tests/fixtures/showcase/）を、拡張の本物の記録の読み取り（infra）→
// 図の状態（app・domain）→ renderPanelHtml（view）で HTML にしたもの。CSP の <meta> はそのまま残し、
// 足す script タグ・style タグにはすべて nonce を付ける。
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { refreshView } from '../src/app/refreshView.ts';
import type { PipelineView, ViewClock } from '../src/domain/pipelineView.ts';
import { parseRunRecord } from '../src/domain/runRecord.ts';
import { parseStageLog, parseStageLogName } from '../src/domain/stageLog.ts';
import { createFsWorkDirSource } from '../src/infra/fsWorkDirSource.ts';
import { renderPanelHtml, renderViewBody } from '../src/view/panelHtml.ts';

export type Theme = 'light' | 'dark';

const NONCE = 'preview';

// VSCode のテーマの色の仮の値（Dark Modern・Light Modern に近いもの）。作業台とパネルが使う色をすべて決める
const COMMON = '--vscode-font-family:system-ui,"Segoe UI","Hiragino Sans","Yu Gothic",sans-serif;--vscode-font-size:13px;--vscode-editor-font-family:Consolas,"SF Mono",monospace;--vscode-button-foreground:#ffffff;--vscode-button-background:#0078d4;--vscode-button-hoverBackground:#026ec1;--vscode-focusBorder:#0078d4;';
export const THEMES: Record<Theme, string> = {
  dark: COMMON + '--vscode-editor-background:#1f1f1f;--vscode-foreground:#cccccc;--vscode-descriptionForeground:#9d9d9d;--vscode-editorWidget-background:#202020;--vscode-panel-border:#2b2b2b;--vscode-editorIndentGuide-background:#404040;--vscode-charts-blue:#3794ff;--vscode-charts-orange:#d18616;--vscode-charts-red:#f14c4c;--vscode-charts-green:#89d185;--vscode-charts-purple:#b180d7;--vscode-charts-yellow:#cca700;--vscode-editor-selectionBackground:#264f78;--vscode-button-secondaryBackground:#313131;--vscode-button-secondaryForeground:#cccccc;--vscode-button-secondaryHoverBackground:#3c3c3c;--vscode-input-background:#313131;--vscode-input-foreground:#cccccc;--vscode-notifications-background:#1f1f1f;--vscode-notifications-foreground:#cccccc;--vscode-textCodeBlock-background:#2b2b2b;--vscode-list-hoverBackground:#2a2d2e;--vscode-dropdown-background:#313131;--vscode-dropdown-foreground:#cccccc;--vscode-inputValidation-errorBackground:#5a1d1d;--vscode-errorForeground:#f85149;--vscode-terminal-background:#181818;--vscode-terminal-foreground:#cccccc;--vscode-textLink-foreground:#4daafc;--vscode-list-activeSelectionBackground:#04395e;--vscode-list-activeSelectionForeground:#ffffff;',
  light: COMMON + '--vscode-editor-background:#ffffff;--vscode-foreground:#3b3b3b;--vscode-descriptionForeground:#717171;--vscode-editorWidget-background:#f8f8f8;--vscode-panel-border:#e5e5e5;--vscode-editorIndentGuide-background:#d3d3d3;--vscode-charts-blue:#1a85ff;--vscode-charts-orange:#d18616;--vscode-charts-red:#e51400;--vscode-charts-green:#388a34;--vscode-charts-purple:#652d90;--vscode-charts-yellow:#bf8803;--vscode-editor-selectionBackground:#add6ff;--vscode-button-secondaryBackground:#e5e5e5;--vscode-button-secondaryForeground:#3b3b3b;--vscode-button-secondaryHoverBackground:#cccccc;--vscode-input-background:#ffffff;--vscode-input-foreground:#3b3b3b;--vscode-notifications-background:#ffffff;--vscode-notifications-foreground:#3b3b3b;--vscode-textCodeBlock-background:#f2f2f2;--vscode-list-hoverBackground:#f2f2f2;--vscode-dropdown-background:#ffffff;--vscode-dropdown-foreground:#3b3b3b;--vscode-inputValidation-errorBackground:#f2dede;--vscode-errorForeground:#e51400;--vscode-terminal-background:#f8f8f8;--vscode-terminal-foreground:#3b3b3b;--vscode-textLink-foreground:#005fb8;--vscode-list-activeSelectionBackground:#e8e8e8;--vscode-list-activeSelectionForeground:#000000;',
};

/** 画面用の見本の記録の置き場所（<リポジトリ>/tests/fixtures/showcase）。 */
export const SHOWCASE_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'tests', 'fixtures', 'showcase');

/** 画面用の見本の記録を置く場所（<リポジトリ>/tests/fixtures）。 */
export const FIXTURES_DIR = path.dirname(SHOWCASE_DIR);
/** 動いている見本（07_implement_2 が動いている）・その次の見本（08_test_2 が動き、差し戻しの回数が 1 増えている）・確認待ちの見本。 */
export const RUNNING_DIR = path.join(FIXTURES_DIR, 'showcase_running');
export const RUNNING_NEXT_DIR = path.join(FIXTURES_DIR, 'showcase_running_next');
export const WAITING_DIR = path.join(FIXTURES_DIR, 'showcase_waiting');

/** パネルのページの種類：完了した見本・動いている見本（次の render を送る補助つき）・確認待ちの見本。 */
export type PanelKind = 'done' | 'running' | 'waiting';

/** パネルのページ（ファイル名の頭とテーマ）。 */
export const PANEL_PAGES: readonly [string, Theme][] = [
  ['run-panel-light', 'light'],
  ['run-panel-dark', 'dark'],
  ['run-panel-running-light', 'light'],
  ['run-panel-running-dark', 'dark'],
  ['run-panel-waiting-light', 'light'],
  ['run-panel-waiting-dark', 'dark'],
];

/** ページの名前から、どの見本のページかを決める。 */
export function panelKind(page: string): PanelKind {
  return page.includes('-running-') ? 'running' : page.includes('-waiting-') ? 'waiting' : 'done';
}

/** 記録の時刻（at・since）から sec 秒後を「今」にする時計。手元のずれは 0（見本の時刻はオフセットつきなので、手元に左右されない）。 */
export function previewClock(timeText: string, sec: number): ViewClock {
  return { nowMs: Date.parse(timeText) + sec * 1000, localOffsetMin: 0 };
}

/** 記録を拡張の本物の読み取りで読み、図の状態にする。表示の work_dir は 'docs/pipeline'（絶対パスを出さない）。clock は「今」。 */
export function readShowcaseView(workDirAbs: string, clock?: ViewClock): Promise<PipelineView> {
  return refreshView(createFsWorkDirSource(workDirAbs, 'docs/pipeline'), 'docs/pipeline', clock);
}

/** 動いている段の始まりの時刻（at）、無ければ確認待ちの待ち始め（since）。どちらも無ければ null。見本から「今」を決めるのに使う。 */
export async function startOfLiveness(workDirAbs: string): Promise<string | null> {
  const snapshot = await createFsWorkDirSource(workDirAbs, 'docs/pipeline').read();
  const logs = snapshot.stageLogs
    .map((l) => ({ name: parseStageLogName(l.fileName), log: parseStageLog(l.text) }))
    .filter((l) => l.name !== null && l.log.hasPrompt && !l.log.finished)
    .sort((a, b) => a.name!.seq - b.name!.seq);
  const running = logs.at(-1)?.log.startedAt ?? null;
  return running ?? parseRunRecord(snapshot.stateJson).pendingReview?.since ?? null;
}

/** 動いている・確認待ちの見本の図の状態。「今」は始まりの時刻から sec 秒後に固定する（ページを開いた時点からパネルが数え上げる）。 */
export async function readLiveView(workDirAbs: string, sec: number): Promise<PipelineView> {
  const base = await startOfLiveness(workDirAbs);
  return readShowcaseView(workDirAbs, base === null ? undefined : previewClock(base, sec));
}

/** 確認用ページの動き（脈打ち・点の流れ・点滅）を見るときの、始まりからの秒（動いている見本・確認待ちの見本）。 */
export const RUNNING_SEC = 83;
export const WAITING_SEC = 40;

/** 最初の <style nonce="preview"> の前に、テーマの色を決める <style> を入れる（作業台のページと同じ入れ方）。 */
export function withTheme(html: string, theme: Theme): string {
  const first = `<style nonce="${NONCE}">`;
  return html.replace(first, `<style nonce="${NONCE}">:root{${THEMES[theme]}}</style>${first}`);
}

/**
 * パネルの確認用ページ。VSCode の API の代わりに、何もしない acquireVsCodeApi を <body> の直後に入れる。
 * next を渡すと（動いている見本のページ）、その本体を render のメッセージで送る補助 window.__previewNext() も入れる
 * （戻る矢印の光りを画面で確かめるための、確認用ページだけの補助。nonce つき）。
 */
export function panelPreviewHtml(view: PipelineView, theme: Theme, next?: PipelineView): string {
  const stub = `<script nonce="${NONCE}">window.acquireVsCodeApi=()=>({postMessage(){}});</script>`;
  // 本体の HTML を文字として埋める。< は < にして、</script> などでページが切れないようにする
  const nextBody = next === undefined ? '' : JSON.stringify(renderViewBody(next)).replace(/</g, '\\u003c');
  const helper = next === undefined ? '' : `\n<script nonce="${NONCE}">window.__previewNext=()=>window.postMessage({type:'render',html:${nextBody}},'*');</script>`;
  return withTheme(renderPanelHtml(view, NONCE), theme).replace('<body>', `<body>\n${stub}`).replace('</body>', `${helper}\n</body>`);
}
