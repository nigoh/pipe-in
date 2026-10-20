// 画面の確認用のページを作る：npm run build のあとに npm run preview。
// 本物の HTML（view/pipeEditorHtml.ts）と本物のビルド（out/pipeEditor.js）から、VSCode の外のブラウザで開けるページを
// out/preview/ に書く。VSCode の API の代わりに、見本のパイプを読み込ませるだけの小さな置き換えを入れ、
// テーマの色（--vscode-*）は明るい・暗いの2通りを仮の値で入れる。Playwright（MCP）で開いて画面を確かめるのに使う。
// 「実行を見る」パネルの明るい・暗いのページ（run-panel-*.html）も、画面用の見本の記録から作る（中身は previewPages.ts）。
// CSP は本物と同じに残す（style="…" 属性が捨てられるなど、パネルの中だけで起きる崩れをここでも見つけるため）。
// 置き換えのスクリプトとテーマの色には nonce を付けて入れる。out/ は .gitignore 済み。
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { folderFor } from '../src/app/pipeEditor.ts';
import { pipeFromFiles } from '../src/domain/pipeModel.ts';
import { renderPipeEditorHtml } from '../src/view/pipeEditorHtml.ts';
import {
  PANEL_PAGES,
  RUNNING_DIR,
  RUNNING_NEXT_DIR,
  RUNNING_SEC,
  SHOWCASE_DIR,
  WAITING_DIR,
  WAITING_SEC,
  buildOmittedTree,
  buildRunsTree,
  panelKind,
  panelPreviewHtml,
  panelRunsPreviewHtml,
  previewClock,
  readLiveView,
  readRunsView,
  readShowcaseView,
  startOfLiveness,
  withTheme,
} from './previewPages.ts';
import type { Theme } from './previewPages.ts';

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

// ジェネレーターのひな形「diagrams」（pipe-in-gen new で作られるパイプ）。prompts/ も読み込む
const DIAGRAMS = path.join(ROOT, '..', 'generator', 'templates', 'diagrams');
const diagramPrompts: Record<string, string> = {};
for (const f of readdirSync(path.join(DIAGRAMS, 'prompts'))) diagramPrompts[`prompts/${f}`] = readFileSync(path.join(DIAGRAMS, 'prompts', f), 'utf8');
const PAGES: [string, ReturnType<typeof pipeFromFiles>, Theme][] = [
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
  const folder = JSON.stringify(folderFor(model.name));
  const versions = JSON.stringify([{ id: '1760000600000-draft', savedAt: 1760000600000, draft: true }, { id: '1760000000000', savedAt: 1760000000000, draft: false }]);
  const stub = `<script nonce="preview">window.__posted=[];window.acquireVsCodeApi=()=>({postMessage(m){window.__posted.push(m);const send=(x)=>setTimeout(()=>window.postMessage(x,'*'),0);`
    + `if(m.type==='ready'){send({type:'load',model:${json},folder:${folder},savedNames:${names}});send({type:'versions',list:${versions}})}`
    + `if(m.type==='save'){window.__saved=m.model;send({type:'saved',written:['pipe.toml'],errors:[],savedNames:m.model.stages.map(s=>s.name)})}`
    + `if(m.type==='loadVersion'){const v=${json};v.label='保存した版の見本';send({type:'version',id:m.id,model:v})}}});</script>`;
  let html = renderPipeEditorHtml({ nonce: 'preview', scriptUri: 'pipeEditor.js', cspSource: '' });
  html = withTheme(html, theme);
  html = html.replace('<script nonce="preview" src="pipeEditor.js">', `${stub}<script nonce="preview" src="pipeEditor.js">`);
  writeFileSync(path.join(OUT, `${page}.html`), html, 'utf8');
}

// 「実行を見る」パネルのページ：画面用の見本の記録（tests/fixtures/showcase/）を、拡張の本物の読み取りと renderPanelHtml で HTML にしたもの。
// 動いている・確認待ちの見本（D0017）は、始まりの時刻から決まった秒数が経った時点を「今」にして組み立てる。
// 動いている見本のページには、次の見本（差し戻しの回数が増えたもの）を render で送る補助 window.__previewNext() も入れる
for (const dir of [SHOWCASE_DIR, RUNNING_DIR, RUNNING_NEXT_DIR, WAITING_DIR]) {
  if (!existsSync(path.join(dir, 'state.json'))) {
    throw new Error(`見本の記録 ${path.basename(dir)}/ がありません。python tests/showcase.py で作ってください`);
  }
}
const views = {
  done: await readShowcaseView(SHOWCASE_DIR),
  running: await readLiveView(RUNNING_DIR, RUNNING_SEC),
  waiting: await readLiveView(WAITING_DIR, WAITING_SEC),
};
const runningNext = await readLiveView(RUNNING_NEXT_DIR, 5);

// 実行の一覧のページ（D0019）：4つの見本の記録から、一時フォルダの中に置き場所の木（主の checkout＋2つの worktree＋archive）を組み立て、
// 拡張の本物の読み取りと組み立てで読む。「今」は確認待ちの見本の待ち始めから WAITING_SEC 秒後。一時フォルダは読み終えたら消す。
async function runsPageHtml(kind: 'runs' | 'runs-omitted', theme: Theme): Promise<string> {
  const dest = mkdtempSync(path.join(os.tmpdir(), 'pipe-in-preview-runs-'));
  try {
    const { workspace } = await (kind === 'runs' ? buildRunsTree(dest) : buildOmittedTree(dest));
    const since = await startOfLiveness(WAITING_DIR);
    if (since === null) throw new Error('確認待ちの見本に待ち始めの時刻がありません');
    const entries = await readRunsView(workspace, previewClock(since, WAITING_SEC));
    return panelRunsPreviewHtml(entries, theme);
  } finally {
    rmSync(dest, { recursive: true, force: true });
  }
}

for (const [page, theme] of PANEL_PAGES) {
  const kind = panelKind(page);
  if (kind === 'runs' || kind === 'runs-omitted') {
    writeFileSync(path.join(OUT, `${page}.html`), await runsPageHtml(kind, theme), 'utf8');
    continue;
  }
  writeFileSync(path.join(OUT, `${page}.html`), panelPreviewHtml(views[kind], theme, kind === 'running' ? runningNext : undefined), 'utf8');
}
const written = [...PAGES.map(([p]) => p), ...PANEL_PAGES.map(([p]) => p)];
console.log(`out/preview/ に ${written.map((p) => `${p}.html`).join('・')} を作りました`);
