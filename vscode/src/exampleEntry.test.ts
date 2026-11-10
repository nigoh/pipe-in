// 作業台の入口「見本から作る」の配線と、package.json の変わらない所（D0070）。
// extension.ts は vscode を import するので動かせない。配線は字面で見る（判断は app/exampleFlow.ts にあり、そちらは単体で確かめる）。
// package.json の contributes・依存が変わらないことの検査は、今のまま通る（守る）。scripts の examples:gen と生成の道具は、まだ無いので落ちる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const read = (url: string): string => readFileSync(new URL(url, import.meta.url), 'utf8').replace(/\r\n/g, '\n');

/** extension.ts の editPipe 関数の本文（async function editPipe から、行頭の } まで） */
function editPipeBody(): string {
  const src = read('./extension.ts');
  const start = src.indexOf('async function editPipe(');
  assert.ok(start >= 0, 'extension.ts に editPipe がありません');
  const end = src.indexOf('\n}\n', start);
  return src.slice(start, end + 3);
}

// 実装前に数えた値（extension.ts の registerCommand( は 2 つ：showRun・editPipe）
const REGISTER_COMMAND_COUNT = 2;

test('D0070-AC-29: extension.tsに見本の入口があり_registerCommandの数は変わらない', () => {
  const src = read('./extension.ts');
  assert.equal((src.match(/registerCommand\(/g) ?? []).length, REGISTER_COMMAND_COUNT);
  const body = editPipeBody();
  // 「新しいパイプを作る」の隣に「見本から作る」の項目
  const iNew = body.indexOf('新しいパイプを作る');
  const iExample = body.indexOf('見本から作る');
  assert.ok(iNew >= 0 && iExample > iNew, 'editPipe の一覧に「見本から作る」が「新しいパイプを作る」の次にない');
  assert.ok(body.includes('$(library)'), '見本の項目のアイコン $(library)');
  // 見本の選び（QuickPick）と名前の入力（InputBox）。もとの 1 つずつに加えて、もう 1 つずつ
  assert.ok((body.match(/showQuickPick\(/g) ?? []).length >= 2, '見本の showQuickPick');
  assert.ok((body.match(/showInputBox\(/g) ?? []).length >= 2, '見本の名前の showInputBox');
  assert.ok(body.includes('listExamples('), 'listExamples を使う');
  assert.ok(/validateInput:[^\n]*exampleNameProblem\(|exampleNameProblem\([^\n]*\)[\s\S]{0,80}validateInput|validateInput[\s\S]{0,200}exampleNameProblem\(/.test(body), '名前の validateInput が exampleNameProblem を使う');
  assert.ok(body.includes('startFromExample('), 'startFromExample で作る');
});

test('D0070-AC-29: 見本は未保存の下書きとして開く（openEditor に空の newPipe を基準に、見本のモデルを draft で渡す）。同名は開かずに知らせる', () => {
  const body = editPipeBody();
  assert.ok(/openEditor\(\s*dirs\s*,\s*null\s*,\s*newPipe\([^)]*\)\s*,\s*\[\]\s*,\s*[\w.]+\s*\)/.test(body), 'openEditor(dirs, null, newPipe(名前), [], model) の形がない');
  assert.ok(/showWarningMessage\(/.test(body), '同名のときの知らせ');
});

test('D0070-AC-29: extension.ts は見本の文字を webview.html に直接入れない・examples/ を読まない（今のまま通る。守る）', () => {
  const src = read('./extension.ts');
  assert.ok(!/['"`/]examples['"`/]/.test(src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')), 'extension.ts が examples/ を読んでいる');
});

test('D0070-AC-36: contributesのコマンドは2つのまま_dependenciesは空', () => {
  const pkg = JSON.parse(read('../package.json')) as {
    contributes: { commands: { command: string }[]; configuration: { properties: Record<string, unknown> } };
    dependencies?: Record<string, string>;
    devDependencies: Record<string, string>;
  };
  assert.deepEqual(pkg.contributes.commands.map((c) => c.command), ['pipe-in.showRun', 'pipe-in.editPipe']);
  assert.deepEqual(Object.keys(pkg.contributes.configuration.properties).sort(), [
    // D0078：作業台から流す実行ファイルの設定（pipe-in.command）が増えた。期待の一覧に足しただけ
    'pipe-in.command', 'pipe-in.notifyWhenWaiting', 'pipe-in.pipesDir', 'pipe-in.showOtherWorktrees', 'pipe-in.staleAfterMinutes', 'pipe-in.workDir',
  ]);
  assert.deepEqual(Object.keys(pkg.dependencies ?? {}), []);
  assert.deepEqual(Object.keys(pkg.devDependencies).sort(), ['@types/node', '@types/vscode', '@vscode/vsce', 'esbuild', 'typescript']);
});

test('D0070-AC-19: package.json の scripts に examples:gen があり、生成の道具 scripts/genExamples.ts を流す', () => {
  const pkg = JSON.parse(read('../package.json')) as { scripts: Record<string, string> };
  const cmd = pkg.scripts['examples:gen'];
  assert.ok(cmd, 'scripts に examples:gen がありません（まだ作っていない）');
  assert.match(cmd, /scripts\/genExamples\.ts/);
  assert.ok(existsSync(fileURLToPath(new URL('../scripts/genExamples.ts', import.meta.url))), 'scripts/genExamples.ts が無い（まだ作っていない）');
});
