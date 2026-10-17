// 画面の確認用のページを作る：npm run build のあとに npm run preview。
// 本物の HTML（view/pipeEditorHtml.ts）と本物のビルド（out/pipeEditor.js）から、VSCode の外のブラウザで開けるページを
// out/preview/ に書く。VSCode の API の代わりに、見本のパイプを読み込ませるだけの小さな置き換えを入れ、
// テーマの色（--vscode-*）は明るい・暗いの2通りを仮の値で入れる。Playwright（MCP）で開いて画面を確かめるのに使う。
// CSP は本物と同じに残す（style="…" 属性が捨てられるなど、パネルの中だけで起きる崩れをここでも見つけるため）。
// 置き換えのスクリプトとテーマの色には nonce を付けて入れる。out/ は .gitignore 済み。
import { copyFileSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { pipeFromFiles } from '../src/domain/pipeModel.ts';
import { renderPipeEditorHtml } from '../src/view/pipeEditorHtml.ts';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT = path.join(ROOT, 'out', 'preview');

// 見本：分岐・並列・差し戻し・サブエージェント・MCP・許可のモードを一通り使うパイプ
const SAMPLE = `[pipe]
kind = "linear"
label = "依頼に合わせて図か仕様"
input = "required"
[[stages]]
name = "triage"
label = "依頼の仕分け"
output = "01_triage.md"
prompt = "依頼を仕分ける"
[stages.routes]
diagrams = "survey"
spec = "spec-check"
none = "end"
[[stages]]
name = "survey"
label = "ソースの調査"
output = "02_survey.md"
review = true
max_thinking_tokens = 16000
prompt = "ソースを調べる"
[stages.agents.module-reader]
description = "モジュールを読む"
prompt = "1つだけ読む"
tools = ["Read", "Grep"]
[stages.check]
verdict = true
[[stages]]
name = "flow"
label = "フロー図"
output = "03_flow.md"
access = "docs"
docs_dir = "docs/diagrams"
group = "draw"
prompt = "フロー図を描く"
[[stages]]
name = "sequence"
label = "シーケンス図"
output = "04_sequence.md"
access = "docs"
docs_dir = "docs/diagrams"
group = "draw"
prompt = "シーケンス図を描く"
[[stages]]
name = "verify"
label = "図とソースの突き合わせ"
output = "05_verify.md"
next = "end"
prompt = "突き合わせる"
[stages.check]
verdict = true
on_fail = "flow"
[[stages]]
name = "spec-check"
label = "仕様の突き合わせ"
output = "06_spec.md"
permission_mode = "plan"
web = ["docs.python.org"]
mcp = ["mcp__jira__get_issue"]
prompt = "仕様と突き合わせる"
[stages.mcp_servers.jira]
type = "http"
url = "https://mcp.example.com/jira"
`;

// VSCode のテーマの色の仮の値（Dark Modern・Light Modern に近いもの）
const COMMON = '--vscode-font-family:system-ui,"Segoe UI","Hiragino Sans","Yu Gothic",sans-serif;--vscode-editor-font-family:Consolas,"SF Mono",monospace;--vscode-button-foreground:#ffffff;--vscode-button-background:#0078d4;--vscode-button-hoverBackground:#026ec1;--vscode-focusBorder:#0078d4;';
const THEMES: Record<string, string> = {
  dark: COMMON + '--vscode-editor-background:#1f1f1f;--vscode-foreground:#cccccc;--vscode-descriptionForeground:#9d9d9d;--vscode-editorWidget-background:#202020;--vscode-panel-border:#2b2b2b;--vscode-editorIndentGuide-background:#404040;--vscode-charts-blue:#3794ff;--vscode-charts-orange:#d18616;--vscode-charts-red:#f14c4c;--vscode-charts-green:#89d185;--vscode-charts-purple:#b180d7;--vscode-charts-yellow:#cca700;--vscode-editor-selectionBackground:#264f78;--vscode-button-secondaryBackground:#313131;--vscode-button-secondaryForeground:#cccccc;--vscode-button-secondaryHoverBackground:#3c3c3c;--vscode-input-background:#313131;--vscode-input-foreground:#cccccc;--vscode-notifications-background:#1f1f1f;--vscode-notifications-foreground:#cccccc;--vscode-textCodeBlock-background:#2b2b2b;--vscode-list-hoverBackground:#2a2d2e;--vscode-dropdown-background:#313131;--vscode-dropdown-foreground:#cccccc;--vscode-inputValidation-errorBackground:#5a1d1d;',
  light: COMMON + '--vscode-editor-background:#ffffff;--vscode-foreground:#3b3b3b;--vscode-descriptionForeground:#717171;--vscode-editorWidget-background:#f8f8f8;--vscode-panel-border:#e5e5e5;--vscode-editorIndentGuide-background:#d3d3d3;--vscode-charts-blue:#1a85ff;--vscode-charts-orange:#d18616;--vscode-charts-red:#e51400;--vscode-charts-green:#388a34;--vscode-charts-purple:#652d90;--vscode-charts-yellow:#bf8803;--vscode-editor-selectionBackground:#add6ff;--vscode-button-secondaryBackground:#e5e5e5;--vscode-button-secondaryForeground:#3b3b3b;--vscode-button-secondaryHoverBackground:#cccccc;--vscode-input-background:#ffffff;--vscode-input-foreground:#3b3b3b;--vscode-notifications-background:#ffffff;--vscode-notifications-foreground:#3b3b3b;--vscode-textCodeBlock-background:#f2f2f2;--vscode-list-hoverBackground:#f2f2f2;--vscode-dropdown-background:#ffffff;--vscode-dropdown-foreground:#3b3b3b;--vscode-inputValidation-errorBackground:#f2dede;',
};

// ジェネレーターのひな形「diagrams」（devpipe-gen new で作られるパイプ）。prompts/ も読み込む
const DIAGRAMS = path.join(ROOT, '..', 'generator', 'templates', 'diagrams');
const diagramPrompts: Record<string, string> = {};
for (const f of readdirSync(path.join(DIAGRAMS, 'prompts'))) diagramPrompts[`prompts/${f}`] = readFileSync(path.join(DIAGRAMS, 'prompts', f), 'utf8');
const PAGES: [string, ReturnType<typeof pipeFromFiles>, string][] = [
  ['pipe-editor-dark', pipeFromFiles('design-review', SAMPLE, {}, null), 'dark'],
  ['pipe-editor-light', pipeFromFiles('design-review', SAMPLE, {}, null), 'light'],
  ['pipe-editor-diagrams', pipeFromFiles('diagrams', readFileSync(path.join(DIAGRAMS, 'pipe.toml'), 'utf8'), diagramPrompts, null), 'dark'],
];

mkdirSync(OUT, { recursive: true });
copyFileSync(path.join(ROOT, 'out', 'pipeEditor.js'), path.join(OUT, 'pipeEditor.js'));
for (const [page, model, theme] of PAGES) {
  // 保存を押したら、受け取った中身を window.__saved に残す（画面の確認で、保存が届いたかを見られるように）。
  // 送られたものはすべて window.__posted に残す。版の一覧は見本を2つ（1つは閉じたときの下書き）返し、選ばれたら見本のパイプを返す
  const json = JSON.stringify(model).replace(/</g, '\u003c');
  const names = JSON.stringify(model.stages.map((s) => s.name));
  const versions = JSON.stringify([{ id: '1760000600000-draft', savedAt: 1760000600000, draft: true }, { id: '1760000000000', savedAt: 1760000000000, draft: false }]);
  const stub = `<script nonce="preview">window.__posted=[];window.acquireVsCodeApi=()=>({postMessage(m){window.__posted.push(m);const send=(x)=>setTimeout(()=>window.postMessage(x,'*'),0);`
    + `if(m.type==='ready'){send({type:'load',model:${json},savedNames:${names}});send({type:'versions',list:${versions}})}`
    + `if(m.type==='save'){window.__saved=m.model;send({type:'saved',written:['pipe.toml'],errors:[],savedNames:m.model.stages.map(s=>s.name)})}`
    + `if(m.type==='loadVersion'){const v=${json};v.label='保存した版の見本';send({type:'version',id:m.id,model:v})}}});</script>`;
  let html = renderPipeEditorHtml({ nonce: 'preview', scriptUri: 'pipeEditor.js', cspSource: '' });
  html = html.replace('<style nonce="preview">', `<style nonce="preview">:root{${THEMES[theme]}}</style><style nonce="preview">`);
  html = html.replace('<script nonce="preview" src="pipeEditor.js">', `${stub}<script nonce="preview" src="pipeEditor.js">`);
  writeFileSync(path.join(OUT, `${page}.html`), html, 'utf8');
}
console.log(`out/preview/ に ${PAGES.map(([p]) => `${p}.html`).join('・')} を作りました`);
