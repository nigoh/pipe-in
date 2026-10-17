// 画面の確認用のページのうち、ページの中身を決める部分（副作用なし。out/ に書くのは preview.ts だけ）。
// テーマの色（--vscode-* の仮の値）と、「実行を見る」パネルのページの組み立てをここに置き、テストから import する。
// パネルのページは、画面用の見本の記録（tests/fixtures/showcase/）を、拡張の本物の記録の読み取り（infra）→
// 図の状態（app・domain）→ renderPanelHtml（view）で HTML にしたもの。CSP の <meta> はそのまま残し、
// 足す <script>・<style> にはすべて nonce を付ける。
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { refreshView } from '../src/app/refreshView.ts';
import type { PipelineView } from '../src/domain/pipelineView.ts';
import { createFsWorkDirSource } from '../src/infra/fsWorkDirSource.ts';
import { renderPanelHtml } from '../src/view/panelHtml.ts';

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

/** パネルのページ（ファイル名の頭とテーマ）。 */
export const PANEL_PAGES: readonly [string, Theme][] = [
  ['run-panel-light', 'light'],
  ['run-panel-dark', 'dark'],
];

/** 記録を拡張の本物の読み取りで読み、図の状態にする。表示の work_dir は 'docs/pipeline'（絶対パスを出さない）。 */
export function readShowcaseView(workDirAbs: string): Promise<PipelineView> {
  return refreshView(createFsWorkDirSource(workDirAbs, 'docs/pipeline'), 'docs/pipeline');
}

/** 最初の <style nonce="preview"> の前に、テーマの色を決める <style> を入れる（作業台のページと同じ入れ方）。 */
export function withTheme(html: string, theme: Theme): string {
  const first = `<style nonce="${NONCE}">`;
  return html.replace(first, `<style nonce="${NONCE}">:root{${THEMES[theme]}}</style>${first}`);
}

/** パネルの確認用ページ。VSCode の API の代わりに、何もしない acquireVsCodeApi を <body> の直後に入れる。 */
export function panelPreviewHtml(view: PipelineView, theme: Theme): string {
  const stub = `<script nonce="${NONCE}">window.acquireVsCodeApi=()=>({postMessage(){}});</script>`;
  return withTheme(renderPanelHtml(view, NONCE), theme).replace('<body>', `<body>\n${stub}`);
}
