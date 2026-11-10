// 構造の検査：作業台から流す機能の8つの部品（D0078）。AC-09（ソース）・32。
//   domain 3（runCommand・runExecutable・runDecision）／app 3（runExecutable・runActive・runFlow）／infra 1（fsFileProbe）／view 1（runHtml）。
// 既存の architecture.test.ts は変えずに通る（targets() に入った新しい部品に、vscode の import 禁止・層ごとの node: の決まり・子プロセス禁止が自動で効く）。
// ここでは、新しい部品に固有の決まり（domain の3つは外の部品を読まない・時計と乱数を読まない・書かない・覚えない・fsFileProbe は stat を通すだけ）を足す。
// 守る検査（部品の中身に関わらず通る形）。stat を1回呼ぶこと・escapeHtml を通すことだけは、部品の中身を見る。
// 構成：1) 検査の本体  2) 実物  3) 検査そのもの（違反の見本を見つけ、守っている見本を見逃さない）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { callArgs, withoutComments } from './test/sourceText.ts';

const SRC = path.dirname(fileURLToPath(import.meta.url));

function listTsFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listTsFiles(full));
    else if (entry.isFile() && entry.name.endsWith('.ts')) out.push(full);
  }
  return out;
}

const relOf = (file: string): string => path.relative(SRC, file).split(path.sep).join('/');

/** architecture.test.ts の targets() と同じ：入口・テスト・test/ の補助を除く製品のコード */
function targets(): string[] {
  return listTsFiles(SRC).filter((file) => {
    const rel = relOf(file);
    return rel !== 'extension.ts' && !rel.endsWith('.test.ts') && !rel.startsWith('test/');
  });
}

/** 製品のコードの読み込み先の文字（from '…'・import '…'・import('…')）。行頭のコメントは見ない */
function specifiersOf(source: string): string[] {
  return Array.from(withoutComments(source).matchAll(/(?:\bfrom|\bimport)\s*\(?\s*['"]([^'"]+)['"]/g), (m) => m[1]!);
}

// ---- 1) 検査の本体 ----------------------------------------------------------------

const DOMAIN_PARTS = ['domain/runCommand.ts', 'domain/runExecutable.ts', 'domain/runDecision.ts'] as const;
const APP_PARTS = ['app/runExecutable.ts', 'app/runActive.ts', 'app/runFlow.ts'] as const;
const INFRA_PARTS = ['infra/fsFileProbe.ts'] as const;
const VIEW_PARTS = ['view/runHtml.ts'] as const;
const PARTS = [...DOMAIN_PARTS, ...APP_PARTS, ...INFRA_PARTS, ...VIEW_PARTS] as const;

const DOMAIN_SIBLING = /^\.\/(?:pipeModel|runCommand|runExecutable|runDecision)\.ts$/;
const WRITE_VERBS = /\b(?:writeFile|writeFileSync|appendFile|appendFileSync|mkdir|mkdtemp|rm|rmSync|unlink|rename|copyFile|createWriteStream|truncate)\s*\(/;
const READ_VERBS = /\b(?:readFile|readdir|readHead|realpath|lstat|open|opendir|createReadStream)\s*\(/;
const KEEPING = /\b(?:workspaceState|globalState|localStorage|sessionStorage|setState|getState)\b/;
const CLOCKS = /\b(?:Date|setTimeout|setInterval|setImmediate)\b|Math\s*\.\s*random|performance\s*\.\s*now/;
const VSCODE_IMPORT = /from\s+['"]vscode['"]|import\(\s*['"]vscode['"]\s*\)|require\(\s*['"]vscode['"]\s*\)/;

/** 部品 rel（src/ からの相対パス）のソースが破っている決まり。空なら守っている */
export function partProblems(rel: string, source: string): string[] {
  const code = withoutComments(source);
  const specs = specifiersOf(source);
  const layer = rel.split('/')[0];
  const out: string[] = [];
  if (VSCODE_IMPORT.test(code)) out.push('vscode を読んでいる');
  if (/\bchild_process\b/.test(code)) out.push('child_process を読んでいる');
  if (CLOCKS.test(code)) out.push('時計・乱数を読んでいる');
  if (WRITE_VERBS.test(code)) out.push('ファイルに書く呼び出しがある');
  if (KEEPING.test(code)) out.push('値を覚える道（workspaceState など）を使っている');
  if (layer === 'domain') {
    for (const s of specs) if (!DOMAIN_SIBLING.test(s)) out.push(`domain が ${s} を読んでいる（同じ domain/ の部品だけ）`);
  } else if (layer === 'app') {
    for (const s of specs) {
      if (s.startsWith('.')) {
        if (/^\.\.\/(?:view|infra|webview)\b/.test(s)) out.push(`app が ${s} を読んでいる`);
      } else if (s !== 'node:path') out.push(`app が ${s} を読んでいる（node:path だけ）`);
    }
  } else if (layer === 'view') {
    for (const s of specs) {
      if (!s.startsWith('.') || /^\.\.\/(?:app|infra)\b/.test(s)) out.push(`view が ${s} を読んでいる`);
    }
    if (/\sstyle\s*=/.test(code)) out.push('style 属性を書いている');
  } else if (layer === 'infra') {
    for (const s of specs) if (!s.startsWith('.')) out.push(`infra の通常ファイルの確かめが ${s} を直に読んでいる（readOnlyFs を通す）`);
    if (READ_VERBS.test(code)) out.push('stat 以外の読む呼び出しがある');
  }
  return out;
}

// ---- 2) 実物 ----------------------------------------------------------------------------

const sourceOf = (rel: string): string => {
  const file = path.join(SRC, rel);
  assert.ok(existsSync(file), `${rel} が無い`);
  return readFileSync(file, 'utf8');
};

test('D0078-AC-32: 8つの部品が src/ にあり、構造の検査の対象（targets()）に入っている（今のまま通る。守る）', () => {
  const rels = targets().map(relOf);
  for (const rel of PARTS) {
    sourceOf(rel);
    assert.ok(rels.includes(rel), `${rel} が検査の対象にある`);
  }
});

for (const rel of PARTS) {
  test(`D0078-AC-32: ${rel} は決まりを守る（vscode・child_process・時計・乱数・書く呼び出し・覚える道・層の外の読み込みが無い）（今のまま通る。守る）`, () => {
    assert.deepEqual(partProblems(rel, sourceOf(rel)), []);
  });
}

test('D0078-AC-32: domain の3つが読むのは同じ domain/ の部品（./pipeModel.ts と互いの run*.ts）だけ。node:・vscode・パッケージ・../ を読まない（今のまま通る。守る）', () => {
  for (const rel of DOMAIN_PARTS) {
    for (const s of specifiersOf(sourceOf(rel))) assert.match(s, DOMAIN_SIBLING, `${rel} → ${s}`);
  }
});

test('D0078-AC-32: 作業台のスクリプト（webview/pipeEditor.ts）は run の部品を domain と view から読み、app・infra・vscode・node: を読まない（束ね：esbuild --platform=browser）（今のまま通る。守る）', () => {
  const specs = specifiersOf(readFileSync(path.join(SRC, 'webview', 'pipeEditor.ts'), 'utf8'));
  assert.deepEqual(specs.filter((s) => /^\.\.\/(?:app|infra|webview)\b/.test(s) || s === 'vscode' || s.startsWith('node:')), []);
});

test('D0078-AC-09: domain と app の run*.ts は node:fs を読まない（app が読んでよい node: は node:path だけ）（今のまま通る。守る）', () => {
  for (const rel of [...DOMAIN_PARTS, ...APP_PARTS]) {
    const fsUsers = specifiersOf(sourceOf(rel)).filter((s) => /^(?:node:)?fs(?:\/|$)/.test(s));
    assert.deepEqual(fsUsers, [], rel);
  }
});

test('D0078-AC-09: fsFileProbe.ts は readOnlyFs（stat だけの口）を通し、node:fs を直に読まず、書く関数も stat 以外の読む関数も持たない（今のまま通る。守る）', () => {
  const source = sourceOf('infra/fsFileProbe.ts');
  assert.deepEqual([...new Set(specifiersOf(source))], ['./readOnlyFs.ts']);
  assert.match(source, /Pick<ReadOnlyFs,\s*'stat'>/);
  assert.deepEqual(partProblems('infra/fsFileProbe.ts', source), []);
});

test('D0078-AC-09: fsFileProbe.ts は stat を1回だけ呼び、既定の口は nodeReadOnlyFs', () => {
  const code = withoutComments(sourceOf('infra/fsFileProbe.ts'));
  assert.equal(callArgs(code, 'stat').length, 1, 'stat( の呼び出しはちょうど1つ');
  assert.match(code, /\bnodeReadOnlyFs\b/);
  assert.match(code, /\bisFile\(\)/);
});

test('D0078-AC-32: view/runHtml.ts は外から来た文字を escapeHtml に通し（./escape.ts を読む）、自前のエスケープを持たない', () => {
  const code = withoutComments(sourceOf('view/runHtml.ts'));
  assert.match(code, /import \{[^}]*\bescapeHtml\b[^}]*\} from '\.\/escape\.ts'/);
  assert.doesNotMatch(code, /&(?:amp|lt|gt|quot|apos|#\d+);/i);
});

test('D0078-AC-32: 既存の architecture.test.ts の検査（vscode の import 禁止・層ごとの node:）が新しい部品にも自動で効くよう、部品は targets() が拾う場所（domain・app・infra・view）にある（今のまま通る。守る）', () => {
  for (const rel of PARTS) assert.match(rel, /^(?:domain|app|infra|view)\/[A-Za-z]+\.ts$/);
});

// ---- 3) 検査そのもの：違反の見本を見つけ、守っている見本を見逃さない（今のまま通る。守る） --------------------------

const GOOD_DOMAIN = "import type { InputMode } from './pipeModel.ts';\nimport type { OsKind } from './runCommand.ts';\nexport const A = 1;\n";
const GOOD_APP = "import path from 'node:path';\nimport { decideRun } from '../domain/runDecision.ts';\nimport type { PipeRef } from './pipeEditor.ts';\nexport const A = path.resolve('/x');\n";
const GOOD_VIEW = "import { escapeHtml } from './escape.ts';\nimport type { RunView } from '../domain/runDecision.ts';\nexport const A = escapeHtml('x');\n";
const GOOD_INFRA = "import { nodeReadOnlyFs } from './readOnlyFs.ts';\nimport type { ReadOnlyFs } from './readOnlyFs.ts';\nexport async function f(p: string): Promise<boolean> { return (await nodeReadOnlyFs.stat(p)).isFile(); }\n";

test('D0078-AC-32: 検査の見本：守っている見本は問題なし（domain・app・view・infra）（今のまま通る。守る）', () => {
  assert.deepEqual(partProblems('domain/runX.ts', GOOD_DOMAIN), []);
  assert.deepEqual(partProblems('app/runX.ts', GOOD_APP), []);
  assert.deepEqual(partProblems('view/runX.ts', GOOD_VIEW), []);
  assert.deepEqual(partProblems('infra/fsX.ts', GOOD_INFRA), []);
});

const BAD: readonly [string, string, string, string][] = [
  ['domain が node:path を読む', 'domain/runX.ts', "import path from 'node:path';\n", 'node:path'],
  ['domain が ../app を読む', 'domain/runX.ts', "import { x } from '../app/runFlow.ts';\n", '../app/runFlow.ts'],
  ['domain が ../view を読む', 'domain/runX.ts', "import { escapeHtml } from '../view/escape.ts';\n", '../view/escape.ts'],
  ['domain が他の domain の部品を読む', 'domain/runX.ts', "import { x } from './pipeEdit.ts';\n", './pipeEdit.ts'],
  ['domain が外のパッケージを読む', 'domain/runX.ts', "import x from 'some-package';\n", 'some-package'],
  ['domain が vscode を読む', 'domain/runX.ts', "import * as vscode from 'vscode';\n", 'vscode'],
  ['app が node:fs を読む', 'app/runX.ts', "import { readFile } from 'node:fs/promises';\n", 'node:fs/promises'],
  ['app が ../infra を読む', 'app/runX.ts', "import { isRegularFile } from '../infra/fsFileProbe.ts';\n", '../infra/fsFileProbe.ts'],
  ['app が ../view を読む', 'app/runX.ts', "import { runInfoHtml } from '../view/runHtml.ts';\n", '../view/runHtml.ts'],
  ['view が ../app を読む', 'view/runX.ts', "import { planRun } from '../app/runFlow.ts';\n", '../app/runFlow.ts'],
  ['view が node:path を読む', 'view/runX.ts', "import path from 'node:path';\n", 'node:path'],
  ['infra が node:fs を直に読む', 'infra/fsX.ts', "import { stat } from 'node:fs/promises';\n", 'node:fs/promises'],
];

for (const [label, rel, line, needle] of BAD) {
  test(`D0078-AC-32: 検査の見本：${label}と、見つける（今のまま通る。守る）`, () => {
    const found = partProblems(rel, `${line}export const A = 1;\n`);
    assert.ok(found.some((p) => p.includes(needle)), `見つからない（見つけたもの：${found.join(' / ')}）`);
  });
}

const BAD_BODY: readonly [string, string, string][] = [
  ['時計（Date.now）を読む', 'domain/runX.ts', 'export const A = Date.now();\n'],
  ['時計（new Date）を読む', 'app/runX.ts', 'export const A = new Date();\n'],
  ['タイマー（setTimeout）を使う', 'app/runX.ts', 'setTimeout(() => undefined, 1);\n'],
  ['乱数を使う', 'domain/runX.ts', 'export const A = Math.random();\n'],
  ['ファイルに書く（writeFile）', 'infra/fsX.ts', 'await writeFile(p, "x");\n'],
  ['ファイルに書く（mkdir）', 'app/runX.ts', 'await mkdir(p);\n'],
  ['stat 以外を読む（readFile）', 'infra/fsX.ts', 'await fs.readFile(p);\n'],
  ['stat 以外を読む（realpath）', 'infra/fsX.ts', 'await fs.realpath(p);\n'],
  ['値を覚える（workspaceState）', 'app/runX.ts', 'memory = workspaceState;\n'],
  ['値を覚える（localStorage）', 'view/runX.ts', 'localStorage.setItem("a", "b");\n'],
  ['style 属性を書く', 'view/runX.ts', 'export const H = `<p style="color:red">x</p>`;\n'],
  ['child_process を読む', 'app/runX.ts', "const cp = require('child_process');\n"],
];

for (const [label, rel, body] of BAD_BODY) {
  test(`D0078-AC-32: 検査の見本：${label}と、見つける（今のまま通る。守る）`, () => {
    assert.notDeepEqual(partProblems(rel, body), []);
  });
}

test('D0078-AC-32: 検査の見本：行頭のコメントに書いただけの語は見逃し、updatedDate のような名前の一部は時計にしない（今のまま通る。守る）', () => {
  assert.deepEqual(partProblems('domain/runX.ts', '// Date.now() は使わない\n/** setTimeout も workspaceState も使わない */\nexport const updatedDate = 1;\n'), []);
});
