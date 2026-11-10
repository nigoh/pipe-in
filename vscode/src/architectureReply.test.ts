// 構造の検査（D0079・AC-57）：返事のファイルを書く口 infra/fsReplies.ts は、vscode・child_process・時計・乱数を読み込まない。
// infra/ で書く関数を持つファイルは、fsPipes.ts・fsVersions.ts とこの口の 3 つだけ（既存の D0065-AC-22 の検査を、この口を加えた形に直した。architecture.test.ts）。
// 返事を書く口を読み込むのは入口 extension.ts だけ（AC-47 の配線の検査と合わせて、書く道が 1 つだけになる）。
// architecture.test.ts の部品は import できない（import すると、そのファイルのテストがもう一度走る）ので、必要な小さな検査はここに持つ。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { withoutComments } from './test/sourceText.ts';

const SRC = path.dirname(fileURLToPath(import.meta.url));
const REPLIES = 'infra/fsReplies.ts';

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

/** 製品のコード（テストと test/ の補助を除く） */
const production = (): { rel: string; source: string }[] =>
  listTsFiles(SRC)
    .map((file) => ({ rel: relOf(file), source: readFileSync(file, 'utf8') }))
    .filter((f) => !f.rel.endsWith('.test.ts') && !f.rel.startsWith('test/'));

// ---- 検査の本体：返事を書く口の読み込みと、時計・乱数 ----

const ALLOWED_EXTERNAL = new Set(['node:fs/promises', 'node:path']);
const ALLOWED_RELATIVE = /^\.\.\/(?:domain|app)\//;

/** 読み込み先の文字（from '…'・import '…'・import('…')・require('…')）。コメントは見ない */
function specifiersOf(source: string): string[] {
  return Array.from(withoutComments(source).matchAll(/(?:\bfrom|\bimport|\brequire)\s*\(?\s*['"]([^'"]+)['"]/g), (m) => m[1]!);
}

/** 返事を書く口の決まりに合わない点：読み込み先（vscode・child_process など許さないもの）、時計、乱数。無ければ空 */
function replyStoreProblems(source: string): string[] {
  const code = withoutComments(source);
  const found: string[] = [];
  for (const spec of specifiersOf(source)) {
    if (spec.startsWith('.')) {
      if (!ALLOWED_RELATIVE.test(spec)) found.push(`読み込み先 ${spec}（domain と app 以外の層）`);
    } else if (!ALLOWED_EXTERNAL.has(spec)) {
      found.push(`読み込み先 ${spec}`);
    }
  }
  if (/\b(?:Date|setTimeout|setInterval|setImmediate)\b/.test(code)) found.push('時計');
  if (/\bperformance\s*\.\s*now\b|\bprocess\s*\.\s*hrtime\b/.test(code)) found.push('時計（performance・hrtime）');
  if (/\bMath\s*\.\s*random\b|\brandomBytes\b|\brandomUUID\b|\brandomInt\b|\bgetRandomValues\b/.test(code)) found.push('乱数');
  return found;
}

// ---- 実物の fsReplies.ts ----

test('D0079-AC-57: infra/fsReplies.ts がある（返事のファイルを書く口。空の形が置いてあるので、今のまま通る。守る）', () => {
  assert.ok(existsSync(path.join(SRC, REPLIES)), `${REPLIES} が無い`);
});

test('D0079-AC-57: fsReplies.ts は vscode・child_process・時計・乱数を import / 使わない。読み込むのは node:fs/promises・node:path と、domain・app だけ（今のまま通る。守る）', () => {
  const source = readFileSync(path.join(SRC, REPLIES), 'utf8');
  assert.deepEqual(replyStoreProblems(source), []);
});

test('D0079-AC-57: fsReplies.ts は排他（wx）で開いて書く口として実装されている（書く関数を持つ）', () => {
  const code = withoutComments(readFileSync(path.join(SRC, REPLIES), 'utf8'));
  assert.match(code, /\bwx\b|O_EXCL/);
  assert.match(code, /\bcreateFsReplyStore\b/);
});

test('D0079-AC-57: infra/ で書く関数を持つファイルは、fsPipes.ts・fsVersions.ts・fsReplies.ts の 3 つだけ', () => {
  const writers = listTsFiles(path.join(SRC, 'infra'))
    .filter((f) => !f.endsWith('.test.ts') && /\b(?:writeFile|appendFile|mkdir|rm|unlink|rename|copyFile)\b/.test(withoutComments(readFileSync(f, 'utf8'))))
    .map(relOf)
    .sort();
  assert.deepEqual(writers, ['infra/fsPipes.ts', 'infra/fsReplies.ts', 'infra/fsVersions.ts']);
});

test('D0079-AC-57: infra/ のほかのファイル（読み取りの口）は、排他で開く操作（wx・O_EXCL）を持たない（今のまま通る。守る）', () => {
  const others = listTsFiles(path.join(SRC, 'infra'))
    .map((f) => ({ rel: relOf(f), code: withoutComments(readFileSync(f, 'utf8')) }))
    .filter((f) => !f.rel.endsWith('.test.ts') && f.rel !== REPLIES && /['"]wx['"]|\bO_EXCL\b/.test(f.code))
    .map((f) => f.rel);
  assert.deepEqual(others.filter((rel) => rel !== 'infra/fsPipes.ts' && rel !== 'infra/fsVersions.ts'), []);
});

test('D0079-AC-57: 返事を書く口（fsReplies.ts）を読み込む製品のコードは、入口 extension.ts だけ', () => {
  const importers = production()
    .filter((f) => f.rel !== REPLIES && specifiersOf(f.source).some((s) => /(?:^|\/)fsReplies(?:\.ts)?$/.test(s)))
    .map((f) => f.rel);
  assert.deepEqual(importers, ['extension.ts']);
});

// ---- 検査そのもの：違反を見つけ、守っている見本は見逃す ----

const GOOD = `
import { lstat, open, realpath, unlink } from 'node:fs/promises';
import path from 'node:path';
import type { ReplyStore } from '../app/replyFlow.ts';
import { REPLY_FILE_NAME, REPLY_MAX_BYTES } from '../domain/replyFile.ts';
import { isRunFolderName } from '../domain/runs.ts';

// Date や Math.random は使わない（コメントの中の語は数えない）
export function createFsReplyStore(workDirAbs: string): ReplyStore {
  return { create: async () => ({ ok: true }) };
}
`;

const BAD: readonly (readonly [string, string, string])[] = [
  ['vscode を import する', GOOD.replace("import path from 'node:path';", "import * as vscode from 'vscode';\nimport path from 'node:path';"), '読み込み先 vscode'],
  ['child_process を import する', GOOD.replace("import path from 'node:path';", "import { spawn } from 'node:child_process';\nimport path from 'node:path';"), '読み込み先 node:child_process'],
  ['node:crypto を import する', GOOD.replace("import path from 'node:path';", "import { randomBytes } from 'node:crypto';\nimport path from 'node:path';"), '読み込み先 node:crypto'],
  ['node:os を import する', GOOD.replace("import path from 'node:path';", "import os from 'node:os';\nimport path from 'node:path';"), '読み込み先 node:os'],
  ['外のパッケージを import する', GOOD.replace("import path from 'node:path';", "import x from 'some-package';\nimport path from 'node:path';"), '読み込み先 some-package'],
  ['view を import する', GOOD.replace("import type { ReplyStore }", "import { renderReplyNotice } from '../view/replyHtml.ts';\nimport type { ReplyStore }"), '読み込み先 ../view/replyHtml.ts（domain と app 以外の層）'],
  ['別の infra を import する', GOOD.replace("import type { ReplyStore }", "import { createFsPipeStore } from './fsPipes.ts';\nimport type { ReplyStore }"), '読み込み先 ./fsPipes.ts（domain と app 以外の層）'],
  ['動的に vscode を import する', GOOD.replace('return {', "const v = await import('vscode');\n  return {"), '読み込み先 vscode'],
  ['時計を使う', GOOD.replace('return {', 'const at = Date.now();\n  return {'), '時計'],
  ['タイマーを使う', GOOD.replace('return {', 'setTimeout(() => undefined, 1);\n  return {'), '時計'],
  ['乱数を使う', GOOD.replace('return {', 'const r = Math.random();\n  return {'), '乱数'],
];
for (const [label, source, word] of BAD) {
  test(`D0079-AC-57: 検査そのもの：${label}と見つける（今のまま通る。守る）`, () => {
    assert.notEqual(source, GOOD, '見本を壊せている');
    assert.ok(replyStoreProblems(source).includes(word), `見つけられない（見つけたもの：${replyStoreProblems(source).join(' / ')}）`);
  });
}

test('D0079-AC-57: 検査そのもの：守っている見本は見逃す（node:fs/promises・node:path・domain・app だけ。コメントの Date・Math.random は数えない）（今のまま通る。守る）', () => {
  assert.deepEqual(replyStoreProblems(GOOD), []);
});
