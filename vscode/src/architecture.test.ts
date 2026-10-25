// 構造の検査。AC-44：記録の読み取りと図の状態の組み立て（入口 src/extension.ts 以外のすべて）は vscode を import しない。
// D0021-AC-03 の 2 件（utimes の検査と、その検査そのものの確かめ）は、今のまま通る（赤ではなく、守り続けるために置く。名前の末尾に「守る」と書いた）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { blockAfter, callArgs, findClockOrNode, withoutComments } from './test/sourceText.ts';

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

function targets(): string[] {
  return listTsFiles(SRC).filter((file) => {
    const rel = path.relative(SRC, file).split(path.sep).join('/');
    if (rel === 'extension.ts') return false;
    if (rel.endsWith('.test.ts')) return false;
    if (rel.startsWith('test/')) return false;
    return true;
  });
}

const VSCODE_IMPORTS = [
  /from\s+['"]vscode['"]/,
  /import\(\s*['"]vscode['"]\s*\)/,
  /require\(\s*['"]vscode['"]\s*\)/,
];

test('AC-44: src/ の記録の読み取り・図の状態の組み立てのモジュールが vscode を import していない', () => {
  const files = targets();
  // 対象が1つもないときは失敗にする（設計書：テスト先行の時点では赤になる）
  assert.ok(files.length > 0, '検査する製品コードのモジュールが src/ にあること');
  // 少なくとも記録の読み取りと図の状態の組み立てのモジュールが対象に入っていること
  const rels = files.map((f) => path.relative(SRC, f).split(path.sep).join('/'));
  for (const required of ['domain/runRecord.ts', 'domain/stageLog.ts', 'domain/artifacts.ts', 'domain/pipelineView.ts']) {
    assert.ok(rels.includes(required), `${required} が検査の対象にあること`);
  }
  const offenders = files.filter((file) => {
    const text = readFileSync(file, 'utf8');
    return VSCODE_IMPORTS.some((re) => re.test(text));
  });
  assert.deepEqual(
    offenders.map((f) => path.relative(SRC, f)),
    [],
  );
});

// ---- D0002-AC-07: 層ごとに使ってよい node: の部品（docs/development/design.md の「拡張の層」） ----

const LAYER_NODE_IMPORTS: Record<string, string[]> = {
  domain: ['node:path'],
  app: ['node:path'],
  view: [],
  webview: [],
  infra: ['node:fs', 'node:fs/promises', 'node:os', 'node:path'],
};

/** 層の決まりに合わない import（「ファイル → 読み込んだもの」）。テストと test/ の補助は見ない */
export function layerViolations(files: { rel: string; source: string }[]): string[] {
  const out: string[] = [];
  for (const { rel, source } of files) {
    const layer = rel.split('/')[0]!;
    const allowed = LAYER_NODE_IMPORTS[layer];
    if (!allowed || rel.endsWith('.test.ts')) continue;
    for (const m of source.matchAll(/(?:from|import)\s*\(?\s*['"]([^'"]+)['"]/g)) {
      const target = m[1]!;
      const external = !target.startsWith('.');
      if (external && !allowed.includes(target)) out.push(`${rel} → ${target}`);
    }
  }
  return out;
}

test('D0002-AC-07: 層ごとに、使ってよい node: の部品だけを使う（外のパッケージも使わない）', () => {
  const files = targets().map((file) => ({
    rel: path.relative(SRC, file).split(path.sep).join('/'),
    source: readFileSync(file, 'utf8'),
  }));
  assert.deepEqual(layerViolations(files), []);
});

// ---- D0019-AC-21: 子プロセスを起こさない ----

/** child_process を読み込んでいるファイル（node: つきも無しも、import・require・動的 import）。テストと test/ の補助は見ない */
export function childProcessUsers(files: { rel: string; source: string }[]): string[] {
  const re = /(?:from|import|require)\s*\(?\s*['"](?:node:)?child_process(?:\/[^'"]*)?['"]/;
  return files.filter((f) => !f.rel.endsWith('.test.ts') && !f.rel.startsWith('test/') && re.test(f.source)).map((f) => f.rel);
}

test('D0019-AC-21: 拡張の src/ のどこにも child_process の import が無い（別の worktree は .git のファイルを読んで見つける）', () => {
  const files = listTsFiles(SRC).map((file) => ({
    rel: path.relative(SRC, file).split(path.sep).join('/'),
    source: readFileSync(file, 'utf8'),
  }));
  assert.ok(files.some((f) => f.rel === 'extension.ts'), '入口も検査の対象に入っている');
  assert.deepEqual(childProcessUsers(files), []);
});

test('D0019-AC-21: 子プロセスの検査そのものが、child_process の読み込みを見つける', () => {
  const found = childProcessUsers([
    { rel: 'infra/a.ts', source: "import { spawn } from 'node:child_process';" },
    { rel: 'infra/b.ts', source: "import cp from 'child_process';" },
    { rel: 'extension.ts', source: "const cp = require('node:child_process');" },
    { rel: 'infra/c.ts', source: "const cp = await import('node:child_process');" },
    { rel: 'infra/d.ts', source: "import { execFile } from 'node:child_process/promises';" },
    { rel: 'infra/e.ts', source: "import { readFile } from 'node:fs/promises';" },
    { rel: 'infra/f.test.ts', source: "import { spawn } from 'node:child_process';" },
  ]);
  assert.deepEqual(found, ['infra/a.ts', 'infra/b.ts', 'extension.ts', 'infra/c.ts', 'infra/d.ts']);
});

// ---- D0021-AC-03: ファイルの更新時刻を書き換える関数（utimes）を製品のコードに入れない ----

/**
 * ファイルの更新時刻を書き換える関数（utimes・futimes・lutimes と、その Sync 版）を使っているファイル。
 * 更新時刻は読むだけ（stat）で、書き換えるのは確認用ページの作り（scripts/）とテストの中だけ。テストと test/ の補助は見ない。
 */
export function timeWriterUsers(files: { rel: string; source: string }[]): string[] {
  const re = /\b[fl]?utimes(?:Sync)?\b/;
  return files.filter((f) => !f.rel.endsWith('.test.ts') && !f.rel.startsWith('test/') && re.test(f.source)).map((f) => f.rel);
}

test('D0021-AC-03: 拡張の src/ の製品のコードのどこにも utimes・futimes・lutimes が無い（更新時刻は読むだけ。書き換えるのは scripts/ とテストの中だけ）（今のまま通る。守る）', () => {
  const files = listTsFiles(SRC).map((file) => ({
    rel: path.relative(SRC, file).split(path.sep).join('/'),
    source: readFileSync(file, 'utf8'),
  }));
  assert.ok(files.some((f) => f.rel === 'infra/fsWorkDirSource.ts'), '更新時刻を読む基盤のファイルも検査の対象に入っている');
  assert.ok(files.some((f) => f.rel === 'extension.ts'), '入口も検査の対象に入っている');
  assert.deepEqual(timeWriterUsers(files), []);
});

test('D0021-AC-03: 更新時刻の書き換えの検査そのものが、utimes を使うファイルを見つける（stat で読むだけのファイル・テストは見逃す）（今のまま通る。守る）', () => {
  const found = timeWriterUsers([
    { rel: 'infra/a.ts', source: "import { utimes } from 'node:fs/promises';" },
    { rel: 'infra/b.ts', source: 'await handle.futimes(fd, atime, mtime);' },
    { rel: 'infra/c.ts', source: 'lutimesSync(file, atime, mtime);' },
    { rel: 'infra/d.ts', source: "const { utimes } = await import('node:fs/promises');" },
    { rel: 'extension.ts', source: 'await fs.promises.utimes(file, atime, mtime);' },
    { rel: 'app/e.ts', source: 'fs.utimesSync(file, atime, mtime);' },
    { rel: 'infra/f.ts', source: "const info = await fs.stat(file);\nconst last = info.mtimeMs;" },
    { rel: 'infra/g.ts', source: 'const utimesCount = 3; const futimesLike = 4;' },
    { rel: 'infra/h.test.ts', source: "import { utimes } from 'node:fs/promises';" },
    { rel: 'test/i.ts', source: "import { utimes } from 'node:fs/promises';" },
  ]);
  assert.deepEqual(found, ['infra/a.ts', 'infra/b.ts', 'infra/c.ts', 'infra/d.ts', 'extension.ts', 'app/e.ts']);
});

test('D0019-AC-32: 2版目で足す部品が、決まった層（domain・view）にある。どれも vscode と node: の決まりの検査の対象に入る', () => {
  const rels = targets().map((f) => path.relative(SRC, f).split(path.sep).join('/'));
  for (const required of ['domain/sessionName.ts', 'domain/gantt.ts', 'view/shellHtml.ts', 'view/ganttHtml.ts', 'view/panelScript.ts']) {
    assert.ok(rels.includes(required), `${required} が src/ にある`);
  }
});

test('D0002-AC-07: 層の検査そのものが、決まりに合わない import を見つける', () => {
  const found = layerViolations([
    { rel: 'domain/a.ts', source: "import { readFile } from 'node:fs/promises';\nimport path from 'node:path';" },
    { rel: 'view/b.ts', source: "import path from 'node:path';" },
    { rel: 'webview/c.ts', source: "import x from 'some-package';" },
    { rel: 'infra/d.ts', source: "import { spawn } from 'node:child_process';" },
    { rel: 'app/e.ts', source: "import { x } from '../domain/x.ts';" },
    { rel: 'domain/f.test.ts', source: "import { readFile } from 'node:fs';" },
  ]);
  assert.deepEqual(found, ['domain/a.ts → node:fs/promises', 'view/b.ts → node:path', 'webview/c.ts → some-package', 'infra/d.ts → node:child_process']);
});

// ---- D0024-AC-42: 件数の判断（domain/runList.ts）と文字を作る部品（view/statusBar.ts）は、時計を読まない ----
// 本物のファイルの検査も、検査そのものの確かめも、今のまま通る（赤ではなく、守り続けるために置く。名前の末尾に「守る」と書いた）。

/** 時計を読まないと決めたファイル（ステータスバーの件数に関わる 2 つ。src/ からの相対パス）。 */
const CLOCK_FREE = ['view/statusBar.ts', 'domain/runList.ts'];

/**
 * 時計を読んでいるファイル（Date・setTimeout・setInterval・setImmediate を語境界で探す）。
 * 行頭のコメント（ブロックと //）は見ない。語境界で探すので、`updatedDate` のような名前の一部は見逃す。
 */
export function clockUsers(files: { rel: string; source: string }[]): string[] {
  const re = /\b(?:Date|setTimeout|setInterval|setImmediate)\b/;
  return files
    .filter((f) => re.test(f.source.replace(/^[ \t]*\/\*[\s\S]*?\*\//gm, '').replace(/^[ \t]*\/\/.*$/gm, '')))
    .map((f) => f.rel);
}

test('D0024-AC-42: view/statusBar.ts と domain/runList.ts は時計を読まない（Date・setTimeout・setInterval・setImmediate が無い）（今のまま通る。守る）', () => {
  const files = CLOCK_FREE.map((rel) => ({ rel, source: readFileSync(path.join(SRC, rel), 'utf8') }));
  assert.equal(files.length, 2);
  assert.deepEqual(clockUsers(files), []);
});

// 時計を読む見本（見つける）
const CLOCK_FOUND: [string, string][] = [
  ['Date.now()', 'const at = Date.now();'],
  ['new Date()', 'const d = new Date();'],
  ['new Date(引数)', 'const d = new Date(text);'],
  ['setTimeout(', 'setTimeout(() => render(), 200);'],
  ['setInterval(', 'const t = setInterval(tick, 1000);'],
  ['setImmediate(', 'setImmediate(run);'],
  ['コメントの行のあとの行にある Date.now()（コメントと一緒に消さない）', '// 次の行で読む\nconst at = Date.now();'],
];

for (const [label, source] of CLOCK_FOUND) {
  test(`D0024-AC-42: 時計の検査そのものが、${label} を使うファイルを見つける（今のまま通る。守る）`, () => {
    assert.deepEqual(clockUsers([{ rel: 'view/a.ts', source }]), ['view/a.ts']);
  });
}

// 時計ではない見本（見逃す）
const CLOCK_MISSED: [string, string][] = [
  ['updatedDate: string を含む行（今の domain/runList.ts にある）', '  updatedDate: string;'],
  ['updatedDate を使う行（今の domain/runList.ts にある）', '    updatedDate: updatedText === DASH ? DASH : updatedText.slice(0, 5),'],
  ['行頭の // のコメントに書いた Date', '// Date.now() は使わない'],
  ['行頭の /** */ の 1 行コメントに書いた Date', '/** new Date() は渡された値から作る */'],
  ['ブロックコメントの途中の行に書いた Date と setTimeout', '/**\n * 「今」は Date を読まずに引数で受ける\n * setTimeout も使わない\n */\nexport const x = 1;'],
  ['時計と関係のない行', 'const rows = sortRows(list);'],
];

for (const [label, source] of CLOCK_MISSED) {
  test(`D0024-AC-42: 時計の検査そのものが、${label} は見逃す（今のまま通る。守る）`, () => {
    assert.deepEqual(clockUsers([{ rel: 'view/a.ts', source }]), []);
  });
}

test('D0024-AC-42: 時計の検査そのものが、使うファイルだけを渡した順に返す（使わないファイルは含めない）（今のまま通る。守る）', () => {
  const found = clockUsers([
    { rel: 'domain/a.ts', source: 'const at = Date.now();' },
    { rel: 'domain/b.ts', source: 'export const x = 1;' },
    { rel: 'view/c.ts', source: 'setTimeout(f, 1);' },
  ]);
  assert.deepEqual(found, ['domain/a.ts', 'view/c.ts']);
});

// ---- D0050：エージェント・スキル・道具の表の部品（domain/toolsTable.ts・view/toolsHtml.ts）の構造 ----
// AC-33：表を作る部品は「今」を使わない（時計を読まず、引数にも取らない）。AC-38：層の向きを守る。
// AC-41(2)：一覧の行の組み立て（domain/runList.ts）・app/runList.ts・infra/ は、表を作る部品を値として import しない。buildPipelineView の呼び出し元は 2 か所だけ。
// 新しいファイルが無いあいだは「まだ作っていない」で落とす（無いファイルを readFileSync で読んで ENOENT で落ちると、赤の理由が読み取りにくい）。
// 検査そのもの（違反の見本を見つけ、守っている見本を見逃す）と、今ある製品のコードへの検査（import・呼び出し元）は、今のまま通る（守る）。

const TOOLS_PARTS = ['domain/toolsTable.ts', 'view/toolsHtml.ts'] as const;

function needSource(rel: string): string {
  const file = path.join(SRC, rel);
  assert.ok(existsSync(file), `${rel} が無い（まだ作っていない）`);
  return readFileSync(file, 'utf8');
}
const relOf = (file: string): string => path.relative(SRC, file).split(path.sep).join('/');

/** 製品のコードの読み込み先の文字（from '…'・import '…'・import('…')）。行頭のコメントは見ない */
function specifiersOf(source: string): string[] {
  return Array.from(withoutComments(source).matchAll(/(?:\bfrom|\bimport)\s*\(?\s*['"]([^'"]+)['"]/g), (m) => m[1]!);
}

test('D0050-AC-33: domain/toolsTable.ts と view/toolsHtml.ts は時計を読まない（Date・setTimeout・setInterval・setImmediate・乱数・node: の読み込みが無い）', () => {
  const files = TOOLS_PARTS.map((rel) => ({ rel: rel as string, source: needSource(rel) }));
  assert.deepEqual(clockUsers(files), []);
  for (const f of files) assert.deepEqual(findClockOrNode(f.source), [], `${f.rel}: 時計・乱数・node: の読み込み`);
});

/** ToolsInput の中身に、時計の項目（clock・now・nowMs）が無いか。ToolsInput が見つからなければ、それが問題 */
export function toolsInputProblems(source: string): string[] {
  const body = blockAfter(withoutComments(source), /export interface ToolsInput\s*\{/);
  if (body === null) return ['export interface ToolsInput { … } が見つからない'];
  return Array.from(body.matchAll(/\b(?:clock|nowMs|now)\b/g), (m) => `ToolsInput に ${m[0]} がある`);
}

test('D0050-AC-33: 表を作る入力 ToolsInput は「今」（clock・now・nowMs）を引数に取らない（ToolsInput が見つからなければ落とす）', () => {
  assert.deepEqual(toolsInputProblems(needSource('domain/toolsTable.ts')), []);
});

test('D0050-AC-33: 検査そのもの：ToolsInput に clock・now・nowMs を持つ見本は見つけ、持たない見本は見逃す。行頭のコメントだけに書いた clock は見逃し、ToolsInput の無いソースは問題にする（今のまま通る。守る）', () => {
  const clean = 'export interface ToolsInput {\n  logs: readonly ToolsLog[];\n  driver: boolean;\n}\n';
  assert.deepEqual(toolsInputProblems(clean), []);
  assert.deepEqual(toolsInputProblems(clean.replace('driver: boolean;', 'driver: boolean;\n  clock: ViewClock;')), ['ToolsInput に clock がある']);
  assert.deepEqual(toolsInputProblems(clean.replace('driver: boolean;', 'driver: boolean;\n  nowMs: number;')), ['ToolsInput に nowMs がある']);
  assert.deepEqual(toolsInputProblems(clean.replace('driver: boolean;', 'driver: boolean;\n  now?: number;')), ['ToolsInput に now がある']);
  assert.deepEqual(toolsInputProblems(clean.replace('  driver: boolean;', '  // clock は取らない\n  driver: boolean;')), [], '行頭のコメントは見逃す');
  assert.deepEqual(toolsInputProblems('export function buildToolsTable() {}'), ['export interface ToolsInput { … } が見つからない']);
  assert.deepEqual(findClockOrNode('const at = Date.now();'), ['Date']);
  assert.deepEqual(findClockOrNode("import path from 'node:path';").length, 1);
  assert.deepEqual(findClockOrNode('// Date.now() は使わない\nexport const x = 1;'), []);
});

// ---- AC-38：層の向き ----

test('D0050-AC-38: domain/toolsTable.ts と view/toolsHtml.ts が、構造の検査の対象（targets()）に入っている（vscode を import しない・層ごとの node: の決まり）', () => {
  const rels = targets().map(relOf);
  for (const rel of TOOLS_PARTS) assert.ok(rels.includes(rel), `${rel} が検査の対象にある（まだ作っていない）`);
});

/** toolsTable.ts の読み込み先は ./ だけ（domain の中だけ。view・app・infra・外のパッケージ・node: を読まない） */
export function tableDirectionProblems(source: string): string[] {
  return specifiersOf(source)
    .filter((s) => !s.startsWith('./'))
    .map((s) => `domain/toolsTable.ts が ${s} を読んでいる`);
}
/** toolsHtml.ts は app・infra・vscode を読まない（domain の型と view の中だけ） */
export function htmlDirectionProblems(source: string): string[] {
  return specifiersOf(source)
    .filter((s) => /^\.\.\/(?:app|infra)\b/.test(s) || s === 'vscode')
    .map((s) => `view/toolsHtml.ts が ${s} を読んでいる`);
}

test('D0050-AC-38: toolsTable.ts は ./ の読み込みだけ（../view・../app・../infra を読まない）、toolsHtml.ts は ../app・../infra を読まない', () => {
  assert.deepEqual(tableDirectionProblems(needSource('domain/toolsTable.ts')), []);
  assert.deepEqual(htmlDirectionProblems(needSource('view/toolsHtml.ts')), []);
});

test('D0050-AC-38: 検査そのもの：向きを破る import の見本を見つけ、./ や ../domain の読み込みは見逃す（今のまま通る。守る）', () => {
  assert.deepEqual(tableDirectionProblems("import { a } from './gantt.ts';\nimport type { b } from './stageLog.ts';"), []);
  assert.deepEqual(tableDirectionProblems("import { escapeHtml } from '../view/escape.ts';"), ['domain/toolsTable.ts が ../view/escape.ts を読んでいる']);
  assert.deepEqual(tableDirectionProblems("import x from '../app/refreshView.ts';\nimport y from '../infra/fsPresence.ts';").length, 2);
  assert.deepEqual(tableDirectionProblems("import path from 'node:path';"), ['domain/toolsTable.ts が node:path を読んでいる']);
  assert.deepEqual(htmlDirectionProblems("import type { ToolsTable } from '../domain/toolsTable.ts';\nimport { escapeHtml } from './escape.ts';\nimport { formatDuration } from './duration.ts';"), []);
  assert.deepEqual(htmlDirectionProblems("import { refreshView } from '../app/refreshView.ts';"), ['view/toolsHtml.ts が ../app/refreshView.ts を読んでいる']);
  assert.deepEqual(htmlDirectionProblems("import { read } from '../infra/fsWorkDirSource.ts';\nimport * as vscode from 'vscode';").length, 2);
  assert.deepEqual(htmlDirectionProblems("// import x from '../app/y.ts';\nexport const A = 1;"), [], '行頭のコメントの import は見逃す');
});

// ---- AC-41(2)：一覧の行の組み立ては、表を作る部品を値として import しない ----

/** toolsTable.ts を「値として」読み込んでいる文（import type だけは可。import … from・export … from・import '…'・動的 import(…) は値）。 */
export function toolsTableValueImports(source: string): string[] {
  const code = withoutComments(source);
  const hits: string[] = [];
  for (const m of code.matchAll(/\bimport\s+(type\s+)?[^;'"]*?\bfrom\s*['"][^'"]*toolsTable(?:\.ts)?['"]/g)) if (m[1] === undefined) hits.push(m[0].replace(/\s+/g, ' '));
  for (const m of code.matchAll(/\bexport\s+(type\s+)?[^;'"]*?\bfrom\s*['"][^'"]*toolsTable(?:\.ts)?['"]/g)) if (m[1] === undefined) hits.push(m[0].replace(/\s+/g, ' '));
  for (const m of code.matchAll(/\bimport\s*['"][^'"]*toolsTable(?:\.ts)?['"]/g)) hits.push(m[0]);
  for (const m of code.matchAll(/\bimport\s*\(\s*['"][^'"]*toolsTable(?:\.ts)?['"]/g)) hits.push(m[0]);
  return hits;
}

test('D0050-AC-41: domain/runList.ts・app/runList.ts・infra/ の製品のコードは、toolsTable.ts を値として import しない（import type は可。今のまま通る。守る）', () => {
  const infra = listTsFiles(path.join(SRC, 'infra')).filter((f) => !f.endsWith('.test.ts'));
  assert.ok(infra.length > 0, 'infra/ のファイルが読めている（検査が空振りでない）');
  const files = [path.join(SRC, 'domain', 'runList.ts'), path.join(SRC, 'app', 'runList.ts'), ...infra];
  for (const file of files) assert.deepEqual(toolsTableValueImports(readFileSync(file, 'utf8')), [], relOf(file));
});

test('D0050-AC-41: 検査そのもの：値の import・export … from・副作用の import・動的 import は見つけ、import type・export type は見逃す（今のまま通る。守る）', () => {
  const found: [string, string][] = [
    ['値の import', "import { buildToolsTable } from './toolsTable.ts';"],
    ['全部を読む import', "import * as t from '../domain/toolsTable.ts';"],
    ['型と値を一緒に読む import', "import { type ToolsTable, buildToolsTable } from './toolsTable.ts';"],
    ['拡張子なしの import', "import { buildToolsTable } from './toolsTable';"],
    ['複数行の import', "import {\n  buildToolsTable,\n  compareCodePoints,\n} from './toolsTable.ts';"],
    ['export … from', "export { buildToolsTable } from './toolsTable.ts';"],
    ['export * from', "export * from './toolsTable.ts';"],
    ['副作用の import', "import './toolsTable.ts';"],
    ['動的 import', "const m = await import('./toolsTable.ts');"],
  ];
  for (const [label, source] of found) assert.notDeepEqual(toolsTableValueImports(source), [], label);
  const missed: [string, string][] = [
    ['import type', "import type { ToolsTable } from './toolsTable.ts';"],
    ['export type … from', "export type { ToolsTable } from './toolsTable.ts';"],
    ['別のファイルの import', "import { buildPipelineView } from './pipelineView.ts';"],
    ['行頭のコメントの import', "// import { buildToolsTable } from './toolsTable.ts';\nexport const A = 1;"],
    ['名前の一部（toolsTableNote）', "import { x } from './toolsTableNote.ts';"],
  ];
  for (const [label, source] of missed) assert.deepEqual(toolsTableValueImports(source), [], label);
});

/** buildPipelineView( の呼び出しの引数を、呼び出しのあるファイルごとに返す（関数の宣言は数えない）。 */
function viewCallers(files: { rel: string; source: string }[]): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const f of files) {
    const args = callArgs(withoutComments(f.source), 'buildPipelineView');
    if (args.length > 0) out.set(f.rel, args);
  }
  return out;
}

/** 呼び出し元は domain/runList.ts（引数に tools: false）と app/refreshView.ts（引数に tools が無い）の 2 か所だけ。破りの文を返す */
export function viewCallerProblems(files: { rel: string; source: string }[]): string[] {
  const callers = viewCallers(files);
  const problems: string[] = [];
  const rels = [...callers.keys()].sort();
  if (rels.join(',') !== 'app/refreshView.ts,domain/runList.ts') problems.push(`buildPipelineView の呼び出し元が 2 か所（app/refreshView.ts・domain/runList.ts）だけでない：${rels.join('・')}`);
  for (const args of callers.get('domain/runList.ts') ?? []) if (!/\btools\s*:\s*false\b/.test(args)) problems.push('domain/runList.ts の buildPipelineView の呼び出しが tools: false を渡していない');
  for (const args of callers.get('app/refreshView.ts') ?? []) if (/\btools\b/.test(args)) problems.push('app/refreshView.ts の buildPipelineView の呼び出しが tools を渡している（既定の表ありに任せる）');
  return problems;
}

test('D0050-AC-41: buildPipelineView( の呼び出し元は domain/runList.ts（引数に tools: false）と app/refreshView.ts（引数に tools が無い）の 2 か所だけ（製品のコード。入口の extension.ts も含む）', () => {
  const files = [...targets(), path.join(SRC, 'extension.ts')].map((file) => ({ rel: relOf(file), source: readFileSync(file, 'utf8') }));
  assert.ok(files.some((f) => f.rel === 'domain/runList.ts') && files.some((f) => f.rel === 'extension.ts'), '検査の対象に入っている');
  assert.deepEqual(viewCallerProblems(files), []);
});

test('D0050-AC-41: 検査そのもの：呼び出し元が 3 か所の見本・tools: false の無い summarizeRun の見本・tools を渡す refreshView の見本を見つけ、そろった見本は見逃す（今のまま通る。守る）', () => {
  const runList = { rel: 'domain/runList.ts', source: "const view = buildPipelineView({ workDir: '', stateJson, stageLogs, artifacts: {} }, clock, { tools: false });" };
  const refresh = { rel: 'app/refreshView.ts', source: 'return buildPipelineView(snapshot, clock);' };
  const definition = { rel: 'domain/pipelineView.ts', source: 'export function buildPipelineView(snapshot: WorkDirSnapshot): PipelineView {}' };
  assert.deepEqual(viewCallerProblems([runList, refresh, definition]), [], '宣言は呼び出しに数えない');
  assert.equal(viewCallerProblems([runList, refresh, { rel: 'view/statusBar.ts', source: 'const v = buildPipelineView(snap);' }]).length, 1, '呼び出し元が 3 か所');
  assert.equal(viewCallerProblems([runList, refresh, { rel: 'extension.ts', source: 'const v = buildPipelineView(snap, clock);' }]).length, 1, '入口が直に呼ぶ');
  assert.equal(viewCallerProblems([{ ...runList, source: 'const view = buildPipelineView({ workDir: "" }, clock);' }, refresh]).length, 1, 'tools: false が無い');
  assert.equal(viewCallerProblems([{ ...runList, source: 'const view = buildPipelineView({ workDir: "" }, clock, { tools: true });' }, refresh]).length, 1, 'tools: true は止めていない');
  assert.equal(viewCallerProblems([runList, { ...refresh, source: 'return buildPipelineView(snapshot, clock, { tools: true });' }]).length, 1, 'refreshView が tools を渡す');
  assert.equal(viewCallerProblems([runList]).length, 1, 'refreshView の呼び出しが無い');
  assert.deepEqual(viewCallerProblems([runList, { ...refresh, source: '// buildPipelineView(a, b) を呼ぶ\nreturn buildPipelineView(snapshot, clock);' }]), [], '行頭のコメントの呼び出しは数えない');
});
