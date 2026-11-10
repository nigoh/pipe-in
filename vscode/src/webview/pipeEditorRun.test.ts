// 作業台の「流す」の節（D0078）：外側の HTML（view/pipeEditorHtml.ts）と、パネルのスクリプト（webview/pipeEditor.ts）の配線、確認用ページの補助（scripts/preview.ts）。
// 画面の見え方（重なり・はみ出し・読めない色）と操作は、確認用のページで見る（手順は .claude/skills/pipe-in/screen-check.md の「作業台の「流す」の節」。見る点は決定の記録 D0078 の AC-39〜51）。
// パネルのスクリプトは DOM を要るので、ソースを文字で読んで、呼び出しの形・順を確かめる（extensionNotify.test.ts と同じ作り。文字で読む部品は test/sourceText.ts）。
// 判断そのもの（流してよいか・コマンドの形）は domain/runDecision.test.ts・runCommand.test.ts、文は view/runHtml.test.ts が見る。ここは配線だけ。
// 構成：1) 外側の HTML  2) 配線の検査の本体  3) 実物  4) 検査そのもの（壊した見本）  5) 確認用ページの補助
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { renderPipeEditorHtml } from '../view/pipeEditorHtml.ts';
import { callArgs, functionBody, withoutComments } from '../test/sourceText.ts';

// ---- 1) 外側の HTML（AC-39） ----

const HTML = renderPipeEditorHtml({ nonce: 'n1', scriptUri: 'x.js', cspSource: 'src' });
const RUN_BOX = /<details class="box run" id="run" open>[\s\S]*?<\/details>/.exec(HTML)?.[0] ?? '';

test('D0078-AC-39: pipeEditorHtml は <details class="box run" id="run" open> と summary「流す」を1つ持つ（開いた形が既定）', () => {
  assert.equal(HTML.split('id="run"').length - 1, 1, 'id="run" がちょうど1つ');
  assert.notEqual(RUN_BOX, '', '<details class="box run" id="run" open> が無い');
  assert.match(RUN_BOX, /<summary>流す<\/summary>/);
});

test('D0078-AC-39: #run-text（複数行の欄）・#run-info・#run-go（最初は無効の主ボタン）は「流す」の節の中にある', () => {
  assert.match(RUN_BOX, /<textarea id="run-text" rows="4" spellcheck="false"><\/textarea>/);
  assert.match(RUN_BOX, /<label for="run-text">依頼メモ<\/label>/);
  assert.match(RUN_BOX, /<div id="run-text-wrap">/);
  assert.match(RUN_BOX, /<div id="run-info"><\/div>/);
  assert.match(RUN_BOX, /<button type="button" class="btn primary" id="run-go" disabled>流す<\/button>/);
  assert.ok(RUN_BOX.indexOf('id="run-text-wrap"') < RUN_BOX.indexOf('id="run-text"'), '欄は #run-text-wrap の中');
  assert.ok(RUN_BOX.indexOf('id="run-text"') < RUN_BOX.indexOf('id="run-info"'));
  assert.ok(RUN_BOX.indexOf('id="run-info"') < RUN_BOX.indexOf('id="run-go"'));
});

test('D0078-AC-39: 「流す」の節は #pane の外（作り直されない固定の節）で、右の欄 <aside class="side"> の中の #pane の下にある', () => {
  assert.match(HTML, /<div class="pane" id="pane"><\/div>\s*<details class="box run" id="run" open>/);
  const side = /<aside class="side">[\s\S]*<\/aside>/.exec(HTML)?.[0] ?? '';
  assert.ok(side.includes('id="run"'), '右の欄の中にある');
  assert.ok(side.indexOf('id="pane"') < side.indexOf('id="run"'));
});

test('D0078-AC-39: 節には CSS の .run が足されている（クラスだけ。style 属性は書かない）', () => {
  assert.match(HTML, /<style nonce="n1">[\s\S]*\.run\b[\s\S]*<\/style>/);
  assert.doesNotMatch(HTML, /\sstyle=/);
});

test('D0078-AC-39: CSP は今のまま（nonce と webview の出どころだけ。外から何も読み込まない）（今のまま通る。守る）', () => {
  const csp = /Content-Security-Policy" content="([^"]+)"/.exec(HTML)?.[1] ?? '';
  assert.match(csp, /default-src 'none'/);
  assert.doesNotMatch(csp, /https?:/);
  assert.doesNotMatch(HTML, /https?:\/\//);
});

// ---- 2) 配線の検査の本体（webview/pipeEditor.ts） ----

type RunWiringId =
  | 'importsShared'
  | 'refreshRunExists'
  | 'refreshUsesShared'
  | 'refreshDisablesButton'
  | 'refreshHandlesNone'
  | 'refreshHandlesNotes'
  | 'refreshDoesNotSend'
  | 'refreshFromSync'
  | 'refreshOnInput'
  | 'refreshOnContext'
  | 'postStateBeforeRun'
  | 'runPostsOnlyText'
  | 'postStateExists'
  | 'syncUsesPostState'
  | 'stateHoldsContextOnly';

function problems(source: string): RunWiringId[] {
  const code = withoutComments(source);
  const refresh = functionBody(code, 'refreshRun');
  const sync = functionBody(code, 'syncDirty');
  const post = functionBody(code, 'postState');
  const runAt = code.search(/postMessage\(\s*\{\s*type:\s*'run'/);
  const runPosts = callArgs(code, 'postMessage').filter((a) => /type:\s*'run'/.test(a));
  const ok: Record<RunWiringId, boolean> = {
    // 判断・コマンドの形・文は、domain と view の部品を使う（パネルが自前で判断しない）
    importsShared:
      /import\s*\{[^}]*\bdecideRun\b[^}]*\}\s*from\s*'\.\.\/domain\/runDecision\.ts'/.test(code) &&
      /import\s*\{[^}]*\breadRunContext\b[^}]*\}\s*from\s*'\.\.\/domain\/runDecision\.ts'/.test(code) &&
      /import\s*\{[^}]*\bpreviewRunCommand\b[^}]*\}\s*from\s*'\.\.\/domain\/runCommand\.ts'/.test(code) &&
      /import\s*\{[^}]*\bMAX_TEXT_LENGTH\b[^}]*\}\s*from\s*'\.\.\/domain\/runCommand\.ts'/.test(code) &&
      /import\s*\{[^}]*\brunInfoHtml\b[^}]*\}\s*from\s*'\.\.\/view\/runHtml\.ts'/.test(code),
    refreshRunExists: refresh !== null,
    refreshUsesShared: refresh !== null && callArgs(refresh, 'decideRun').length === 1 && callArgs(refresh, 'previewRunCommand').length === 1 && callArgs(refresh, 'runInfoHtml').length === 1,
    // 判断が ok でないときだけボタンを無効にする
    refreshDisablesButton: refresh !== null && /run-go/.test(refresh) && /\.disabled\s*=\s*!\s*\w+\.ok\b/.test(refresh),
    // none のときは欄を隠して文字数を出さず、required・optional では文字数と上限を渡す
    refreshHandlesNone: refresh !== null && /run-text-wrap/.test(refresh) && /'none'/.test(refresh) && /\bMAX_TEXT_LENGTH\b/.test(refresh) && /\bcount\b/.test(refresh),
    // 同じ理由を2か所に出さない決まり（noExecutable は commandNote だけ、notSaved は reason に1回）
    refreshHandlesNotes: refresh !== null && /'noExecutable'/.test(refresh) && /'notSaved'/.test(refresh) && /\bcommandNote\b/.test(refresh) && /保存すると、起こすコマンドの形が見えます/.test(refresh),
    // 描き直しは見せるだけ。拡張へは送らない
    refreshDoesNotSend: refresh !== null && !/postMessage\(/.test(refresh),
    refreshFromSync: sync !== null && /\brefreshRun\(\)/.test(sync),
    refreshOnInput: /\$\('run-text'\)\.addEventListener\('input',\s*(?:refreshRun\b|\(\)\s*=>\s*\{?[^;]*\brefreshRun\(\))/.test(code),
    refreshOnContext: /readRunContext\(ev\.data\)[\s\S]{0,300}?st\.run\.ctx\s*=[\s\S]{0,200}?\brefreshRun\(\)/.test(code),
    // 入口の「保存していない変更がある」を最新にするため、state を先に送ってから run を送る
    postStateBeforeRun: runAt >= 0 && /\bpostState\(\)/.test(code.slice(Math.max(0, runAt - 400), runAt)),
    // パネルが送るのは text だけ
    runPostsOnlyText: runPosts.length === 1 && /^\{\s*type:\s*'run',\s*text(?:\s*:\s*[^,{}]+)?\s*\}$/.test(runPosts[0]!.trim()),
    postStateExists: post !== null && /type:\s*'state'/.test(post) && /clearTimeout\(stateTimer\)/.test(post),
    syncUsesPostState: sync !== null && /\bpostState\(/.test(sync) && !/type:\s*'state'/.test(sync),
    // 依頼メモの文字は #run-text の値そのもの（別に持たない）。状態に持つのは受け取った事実 ctx だけ
    stateHoldsContextOnly: /\brun:\s*\{\s*ctx:\s*RunContext\s*\|\s*null\s*\}/.test(code) && /\brun:\s*\{\s*ctx:\s*null\s*\}/.test(code),
  };
  return (Object.keys(ok) as RunWiringId[]).filter((id) => !ok[id]);
}

// ---- 3) 実物の webview/pipeEditor.ts ----

const SCRIPT = readFileSync(new URL('./pipeEditor.ts', import.meta.url), 'utf8');

const WIRING: readonly { id: RunWiringId; ac: string; what: string }[] = [
  { id: 'importsShared', ac: '40', what: '判断（decideRun・readRunContext）・コマンドの形（previewRunCommand・MAX_TEXT_LENGTH）・文（runInfoHtml）は domain と view の部品から読む' },
  { id: 'refreshRunExists', ac: '40', what: '関数 refreshRun がある' },
  { id: 'refreshUsesShared', ac: '40', what: 'refreshRun が decideRun・previewRunCommand・runInfoHtml をそれぞれ1回呼ぶ' },
  { id: 'refreshDisablesButton', ac: '41', what: 'refreshRun が #run-go.disabled = !判断.ok で、ボタンの有効・無効を決める' },
  { id: 'refreshHandlesNone', ac: '43', what: 'refreshRun が none のとき #run-text-wrap を隠し、文字数（MAX_TEXT_LENGTH の上限）を渡す' },
  { id: 'refreshHandlesNotes', ac: '51', what: 'refreshRun が noExecutable（commandNote にだけ）と notSaved（「保存すると、起こすコマンドの形が見えます」）を分ける' },
  { id: 'refreshDoesNotSend', ac: '40', what: 'refreshRun は拡張へ何も送らない（見せるだけ）' },
  { id: 'refreshFromSync', ac: '44', what: 'syncDirty の中で refreshRun() を呼ぶ（保存していない印が変わるたび）' },
  { id: 'refreshOnInput', ac: '41', what: '#run-text の input で refreshRun を呼ぶ' },
  { id: 'refreshOnContext', ac: '49', what: 'runContext の知らせを readRunContext で検めてから st.run.ctx に入れ、refreshRun() を呼ぶ' },
  { id: 'postStateBeforeRun', ac: '40', what: '#run-go の処理は postState() で state を先に送ってから run を送る' },
  { id: 'runPostsOnlyText', ac: '40', what: '送る run の知らせは { type: \'run\', text } だけで、1か所にだけある' },
  { id: 'postStateExists', ac: '40', what: 'postState() が state を送り、待っている stateTimer を止める' },
  { id: 'syncUsesPostState', ac: '44', what: 'syncDirty の中の送信は postState() を呼ぶ形（state を直に書かない）' },
  { id: 'stateHoldsContextOnly', ac: '40', what: '状態に持つのは run: { ctx: RunContext | null } だけ（依頼メモは #run-text の値そのもの）' },
];

for (const w of WIRING) {
  test(`D0078-AC-${w.ac}: webview/pipeEditor.ts：${w.what}`, () => {
    assert.ok(!problems(SCRIPT).includes(w.id), `pipeEditor.ts で守られていない：${w.id}`);
  });
}

test('D0078-AC-48: パネルのスクリプトは、依頼メモや理由を style 属性・eval・document.write で扱わない（今のまま通る。守る）', () => {
  const code = withoutComments(SCRIPT);
  assert.doesNotMatch(code, /\bstyle\s*=\s*["'`]/);
  assert.doesNotMatch(code, /\beval\s*\(|new\s+Function|document\.write/);
});

// ---- 4) 検査そのもの：壊した見本を見つけ、守っている見本を見逃さない ----

const GOOD = `
import { decideRun, readRunContext } from '../domain/runDecision.ts';
import { MAX_TEXT_LENGTH, previewRunCommand } from '../domain/runCommand.ts';
import { runInfoHtml } from '../view/runHtml.ts';
const st: { dirty: boolean; run: { ctx: RunContext | null } } = { dirty: false, run: { ctx: null } };
let stateTimer: ReturnType<typeof setTimeout> | undefined;
function postState(): void {
  if (stateTimer !== undefined) clearTimeout(stateTimer);
  vscode.postMessage(st.dirty ? { type: 'state', dirty: true, model: st.m } : { type: 'state', dirty: false });
}
function syncDirty(): void {
  st.dirty = true;
  stateTimer = setTimeout(() => postState(), 300);
  refreshRun();
}
function refreshRun(): void {
  const ctx = st.run.ctx;
  const text = ($('run-text') as HTMLTextAreaElement).value;
  const decision = decideRun(ctx, st.dirty, text);
  const shown = previewRunCommand(input);
  let commandNote = null;
  if (decision.block === 'noExecutable') commandNote = ctx.executable.reason;
  else if (decision.block === 'notSaved') commandNote = '保存すると、起こすコマンドの形が見えます';
  const count = ctx.input === 'none' ? null : { length: text.length, limit: MAX_TEXT_LENGTH };
  $('run-text-wrap').hidden = ctx.input === 'none';
  $('run-info').innerHTML = runInfoHtml({ command: shown, commandNote, reason: null, count });
  ($('run-go') as HTMLButtonElement).disabled = !decision.ok;
}
$('run-text').addEventListener('input', refreshRun);
$('run-go').addEventListener('click', () => {
  const text = ($('run-text') as HTMLTextAreaElement).value;
  postState();
  vscode.postMessage({ type: 'run', text });
});
window.addEventListener('message', (ev) => {
  const next = readRunContext(ev.data);
  if (next !== null) {
    st.run.ctx = next;
    refreshRun();
  }
});
`;

test('D0078-AC-40: 検査の見本：守っている見本は問題なし', () => {
  assert.deepEqual(problems(GOOD), []);
});

const BROKEN: readonly [string, string, RunWiringId][] = [
  ['判断の部品を読まない', GOOD.replace(/import \{ decideRun, readRunContext \}[^\n]*\n/, ''), 'importsShared'],
  ['refreshRun が無い', GOOD.replace('function refreshRun(): void {', 'function refreshRunX(): void {'), 'refreshRunExists'],
  ['refreshRun が decideRun を呼ばない', GOOD.replace('decideRun(ctx, st.dirty, text)', '{ ok: true }'), 'refreshUsesShared'],
  ['ボタンの無効を判断に任せない', GOOD.replace('disabled = !decision.ok', 'disabled = false'), 'refreshDisablesButton'],
  ['none で欄を隠さない', GOOD.replace("$('run-text-wrap').hidden = ctx.input === 'none';", ''), 'refreshHandlesNone'],
  ['noExecutable の分けが無い', GOOD.replace("decision.block === 'noExecutable'", "decision.block === 'other'"), 'refreshHandlesNotes'],
  ['refreshRun が拡張へ送る', GOOD.replace("  $('run-info').innerHTML", "  vscode.postMessage({ type: 'x' });\n  $('run-info').innerHTML"), 'refreshDoesNotSend'],
  ['syncDirty が refreshRun を呼ばない', GOOD.replace('  stateTimer = setTimeout(() => postState(), 300);\n  refreshRun();', '  stateTimer = setTimeout(() => postState(), 300);'), 'refreshFromSync'],
  ['input で更新しない', GOOD.replace("$('run-text').addEventListener('input', refreshRun);", ''), 'refreshOnInput'],
  ['runContext を検めずに入れる', GOOD.replace('readRunContext(ev.data)', 'ev.data'), 'refreshOnContext'],
  ['run の前に state を送らない', GOOD.replace('  postState();\n  vscode.postMessage({ type: \'run\', text });', "  vscode.postMessage({ type: 'run', text });"), 'postStateBeforeRun'],
  ['run にパイプの名前を付ける', GOOD.replace("{ type: 'run', text }", "{ type: 'run', text, pipe: 'evil' }"), 'runPostsOnlyText'],
  ['run にコマンドを付ける', GOOD.replace("{ type: 'run', text }", "{ type: 'run', text, command: '/x' }"), 'runPostsOnlyText'],
  ['run を2か所から送る', GOOD.replace('refreshRun();\n  }\n});', "refreshRun();\n    vscode.postMessage({ type: 'run', text: '' });\n  }\n});"), 'runPostsOnlyText'],
  ['postState が待っている送信を止めない', GOOD.replace('  if (stateTimer !== undefined) clearTimeout(stateTimer);\n  vscode', '  vscode'), 'postStateExists'],
  ['syncDirty が state を直に書く', GOOD.replace('stateTimer = setTimeout(() => postState(), 300);', "stateTimer = setTimeout(() => vscode.postMessage({ type: 'state', dirty: true }), 300);"), 'syncUsesPostState'],
  ['状態に依頼メモを持つ', GOOD.replace('run: { ctx: RunContext | null }', 'run: { ctx: RunContext | null; text: string }').replace('run: { ctx: null }', 'run: { ctx: null, text: "" }'), 'stateHoldsContextOnly'],
];

for (const [label, source, id] of BROKEN) {
  test(`D0078-AC-40: 検査の見本：${label}と、${id} が見つける`, () => {
    assert.notEqual(source, GOOD, '見本を壊せていない');
    assert.ok(problems(source).includes(id), `${id} が見つけられない（見つけたもの：${problems(source).join(', ')}）`);
  });
}

test('D0078-AC-40: 検査の見本：コメントに書いただけの呼び出しは数えない（行頭のコメントで通さない）', () => {
  const sneaky = GOOD.replace("  vscode.postMessage({ type: 'run', text });", "  // vscode.postMessage({ type: 'run', text });");
  assert.ok(problems(sneaky).includes('postStateBeforeRun'));
  assert.ok(problems(sneaky).includes('runPostsOnlyText'));
});

// ---- 5) 確認用ページの補助（scripts/preview.ts。AC-39〜51 の手順で使う） ----

const PREVIEW = readFileSync(new URL('../../scripts/preview.ts', import.meta.url), 'utf8');

test('D0078-AC-40: 確認用ページのスタブに window.__previewRun(ctx) があり、runContext を送る（画面の確認は、これで状態を送って見る）', () => {
  assert.match(PREVIEW, /window\.__previewRun\s*=/);
  assert.match(PREVIEW, /type:\s*'runContext'/);
});

test('D0078-AC-40: スタブは ready に対して既定の runContext を送る（pipeDir・project は /work/app の見本、実行ファイルは /usr/local/bin/pipe-in）', () => {
  assert.match(PREVIEW, /\/work\/app\/\.pipe-in\/pipes\//);
  assert.match(PREVIEW, /project:\s*['"]\/work\/app['"]/);
  assert.match(PREVIEW, /\/usr\/local\/bin\/pipe-in/);
  assert.match(PREVIEW, /trusted:\s*true/);
  assert.match(PREVIEW, /running:\s*false/);
});

test('D0078-AC-40: 確認用ページの見本のパスは手元の事情に見えない形（/home/・/Users/・C:\\Users\\ を書かない）', () => {
  const code = withoutComments(PREVIEW);
  assert.doesNotMatch(code, /(?<![A-Za-z0-9_.-])\/(?:home|Users)\/[A-Za-z0-9_.-]/);
  assert.doesNotMatch(code, /C:\\\\?Users\\\\?/);
});
