// ソースの文字を調べる 6 つの探す関数（test/sourceText.ts）そのものの確かめ（D0025）。
// 探す関数が違反を見つけられない（または守っている書き方まで違反にする）と、成果物のプレビューの構造の検査が、間違った理由で通る・落ちる。
// そこで、違反の見本を見つけること、守っている見本（コメントの中の語・名前の一部の語・getAttribute(…) === name の形・escapeHtml の呼び出し）を
// 見逃すことを、1 つずつ確かめる（testing.md の「検査そのものが違反を見つけられる」）。
// 本物のファイル（markdownHtml.ts・panelScript.ts・artifacts.ts・readOnlyFs.ts）に当てる検査は、それぞれの機能のテストが持つ。ここは探す関数だけを見る。
// どれも補助そのものの確かめなので、今のまま通る（赤ではなく、守り続けるために置く）。
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { findClockOrNode, findLimitLiterals, findOwnEscape, findReadHeadAlloc, findSelectorConcat, findStorage } from './sourceText.ts';

const KEEP_NOTE = '（今のまま通る。守る）';

/** [見本の名前, ソース, 見つかる文字の並び（出る順）] */
type FoundRow = readonly [label: string, source: string, expected: readonly string[]];
/** [見本の名前, ソース]（見つからない） */
type MissedRow = readonly [label: string, source: string];

// ---- D0025-AC-30：時計・乱数・node: の読み込み ----

const CLOCK_FOUND: readonly FoundRow[] = [
  ['Date.now()', 'const at = Date.now();', ['Date']],
  ['new Date(引数)', 'const d = new Date(text);', ['Date']],
  ['Math.random()', 'const r = Math.random();', ['Math.random']],
  ['空白を入れた Math . random', 'const r = Math . random();', ['Math . random']],
  ['performance.now()', 'const t = performance.now();', ['performance.now']],
  ["型だけの import の from 'node:fs'", "import type { Stats } from 'node:fs';", ["from 'node:fs'"]],
  ["副作用だけの import 'node:path'", "import 'node:path';", ["import 'node:path'"]],
  ["動的な import('node:fs/promises')", "const fs = await import('node:fs/promises');", ["import('node:fs/promises'"]],
  ["require('node:os')", "const os = require('node:os');", ["require('node:os'"]],
  ['二重引用符の from "node:vm"', 'import vm from "node:vm";', ['from "node:vm"']],
  ['コメントの行のあとの行にある Date.now()（コメントと一緒に消さない）', '// 次の行で読む\nconst at = Date.now();', ['Date']],
  ['1 つの行に 2 つ（出る順に返す）', 'const a = Date.now(); const b = Math.random();', ['Date', 'Math.random']],
];

const CLOCK_MISSED: readonly MissedRow[] = [
  ['空の文字', ''],
  ['updatedDate: string（名前の一部の Date）', '  updatedDate: string;'],
  ['DateRange（Date で始まる名前）', 'const range: DateRange = pick();'],
  ['Math.floor（Math の別の関数）', 'const n = Math.floor(x / 2);'],
  ['random という名前だけ', 'const random = pickOne(list);'],
  ['performanceNote・nowrap（名前の一部）', 'const performanceNote = 1; const nowrap = true;'],
  ["import の形でない文字の中の 'node:'", "const label = 'node: の仲間';"],
  ['node: でない import', "import { escapeHtml } from './escape.ts';"],
  ['行頭の // のコメントに書いた Date.now()', '// Date.now() は使わない'],
  ['行頭の /** */ の 1 行コメントに書いた new Date()', '/** new Date() は渡された値から作る */'],
  ['ブロックコメントの途中の行に書いた Math.random と performance.now', '/**\n * Math.random は使わない\n * performance.now も使わない\n */\nexport const x = 1;'],
  ["コメントに書いた import 'node:fs'", "// import fs from 'node:fs';"],
  ['CRLF の改行のコメント', 'const a = 1;\r\n// Date.now()\r\nconst b = 2;\r\n'],
  ['時計と関係のない行', 'const rows = sortRows(list);'],
];

for (const [label, source, expected] of CLOCK_FOUND) {
  test(`D0025-AC-30: findClockOrNode が、${label} を見つける${KEEP_NOTE}`, () => {
    assert.deepEqual(findClockOrNode(source), expected);
  });
}
for (const [label, source] of CLOCK_MISSED) {
  test(`D0025-AC-30: findClockOrNode が、${label} は見逃す${KEEP_NOTE}`, () => {
    assert.deepEqual(findClockOrNode(source), []);
  });
}

// ---- D0025-AC-33：自前のエスケープ ----

const ESCAPE_FOUND: readonly FoundRow[] = [
  ["replace(/&/g, '&amp;')", "const s = text.replace(/&/g, '&amp;');", ['&amp;']],
  ['表に書いた &lt; と &gt;', "const MAP = { '<': '&lt;', '>': '&gt;' };", ['&lt;', '&gt;']],
  ['&quot;', "const q = '&quot;';", ['&quot;']],
  ['&#39;（10 進の文字参照）', 'const a = "&#39;";', ['&#39;']],
  ['&apos;', "const a = '&apos;';", ['&apos;']],
  ['&#60;（10 進）と &#x3C;（16 進）', "const lt = ['&#60;', '&#x3C;'];", ['&#60;', '&#x3C;']],
  ['大文字の &AMP;', "const a = '&AMP;';", ['&AMP;']],
  ['ユニコードの逃がしで書いた & （\\u0026lt;）', "const a = '\\u0026lt;';", ['&lt;']],
  ['16 進の逃がしで書いた & （\\x26gt;）', "const a = '\\x26gt;';", ['&gt;']],
  ["分けて書いた '&' + 'amp;'", "const a = '&' + 'amp;';", ['&amp;']],
  ['コメントの行のあとの行にある文字参照（コメントと一緒に消さない）', "// 直す\nconst a = '&lt;';", ['&lt;']],
];

const ESCAPE_MISSED: readonly MissedRow[] = [
  ['空の文字', ''],
  ['escapeHtml(text) の呼び出し', 'const html = escapeHtml(text);'],
  ['escapeHtml の import', "import { escapeHtml } from './escape.ts';"],
  ['テンプレートの中の escapeHtml の呼び出し', 'out.push(`<p>${escapeHtml(a)}</p>`);'],
  ["& だけ・&& の演算", "if (c === '&' && next !== ';') {}"],
  ['amp・lt・gt を名前に持つ語', 'const lamp = 1; const ltr = "lt"; const gtk = "gt;";'],
  ["& を足し算で作るが文字参照にならない（'a' + '&' + 'b'）", "const s = 'a' + '&' + 'b';"],
  ['行頭の // のコメントに書いた &amp;', '// &amp; に直さない'],
  ['ブロックコメントに書いた &lt; と &gt;', '/**\n * &lt; &gt; は escapeHtml が作る\n */\nexport const x = 1;'],
  ['エスケープと関係のない行', 'const rows = sortRows(list);'],
];

for (const [label, source, expected] of ESCAPE_FOUND) {
  test(`D0025-AC-33: findOwnEscape が、${label} を見つける${KEEP_NOTE}`, () => {
    assert.deepEqual(findOwnEscape(source), expected);
  });
}
for (const [label, source] of ESCAPE_MISSED) {
  test(`D0025-AC-33: findOwnEscape が、${label} は見逃す${KEEP_NOTE}`, () => {
    assert.deepEqual(findOwnEscape(source), []);
  });
}

// ---- D0025-AC-45：上限の数の直書き ----

const LIMIT_FOUND: readonly FoundRow[] = [
  ['262144', 'export const MAX = 262144;', ['262144']],
  ['262145（読みの上限 + 1）', 'const text = await fs.readHead(file, 262145);', ['262145']],
  ['256 * 1024', 'export const MAX = 256 * 1024;', ['256 * 1024']],
  ['空白なしの 256*1024', 'const MAX = 256*1024;', ['256*1024']],
  ['1024 * 256（順序が逆）', 'const MAX = 1024 * 256;', ['1024 * 256']],
  ['4194304', 'const TOTAL = 4194304;', ['4194304']],
  ['4 * 1024 * 1024（1 件。1024 * 1024 を別に数えない）', 'const TOTAL = 4 * 1024 * 1024;', ['4 * 1024 * 1024']],
  ['1024 * 1024 * 4（順序が逆）', 'const TOTAL = 1024 * 1024 * 4;', ['1024 * 1024 * 4']],
  ['4 * 1024 ** 2', 'const TOTAL = 4 * 1024 ** 2;', ['4 * 1024 ** 2']],
  ['4456448（4 MiB + 256 KiB）', 'const SLACK = 4456448;', ['4456448']],
  ['_ の区切りつきの 262_144（区切りを取って 1 件）', 'const MAX = 262_144;', ['262144']],
  ['16 進の 0x40000', 'const MAX = 0x40000;', ['0x40000']],
  ['シフトの 1 << 18', 'const MAX = 1 << 18;', ['1 << 18']],
  ['べき乗の 2 ** 22', 'const TOTAL = 2 ** 22;', ['2 ** 22']],
  ['2 つの定義（それぞれ 1 件）', 'export const A = 256 * 1024;\nexport const B = 4 * 1024 * 1024;', ['256 * 1024', '4 * 1024 * 1024']],
  ['コメントの行のあとの行にある 262144（コメントと一緒に消さない）', '// 上限\nconst MAX = 262144;', ['262144']],
  ['文字列の中の 262144（メッセージに書いても見つける）', "throw new Error('262144 を超えた');", ['262144']],
];

const LIMIT_MISSED: readonly MissedRow[] = [
  ['空の文字', ''],
  ['定数からの計算 ARTIFACT_MAX_BYTES / 1024', 'const kib = ARTIFACT_MAX_BYTES / 1024;'],
  ['定数 + 1', 'readHead(file, ARTIFACT_MAX_BYTES + 1);'],
  ['定数 * 16', 'const total = ARTIFACT_MAX_BYTES * 16;'],
  ['名前の一部の数（FOO_262144）', 'const FOO_262144 = 1;'],
  ['桁の違う数（2621440・42621445）', 'const a = 2621440; const b = 42621445;'],
  ['小数の一部（0.262144）', 'const ratio = 0.262144;'],
  ['別の数（1024・256・1024 * 1024）', 'const MIB = 1024 * 1024; const BASE = 256; const KIB = 1024;'],
  ["文字の「256 KiB」（掛け算ではない）", "const note = '先頭 256 KiB まで';"],
  ['行頭の // のコメントに書いた 262144', '// 262144 バイトまで'],
  ['ブロックコメントに書いた 256 * 1024 と 4 * 1024 * 1024', '/**\n * 256 * 1024 と 4 * 1024 * 1024\n */\nexport const x = 1;'],
];

for (const [label, source, expected] of LIMIT_FOUND) {
  test(`D0025-AC-45: findLimitLiterals が、${label} を見つける${KEEP_NOTE}`, () => {
    assert.deepEqual(findLimitLiterals(source), expected);
  });
}
for (const [label, source] of LIMIT_MISSED) {
  test(`D0025-AC-45: findLimitLiterals が、${label} は見逃す${KEEP_NOTE}`, () => {
    assert.deepEqual(findLimitLiterals(source), []);
  });
}

// ---- D0025-AC-63：保存の道 ----

const STORAGE_FOUND: readonly FoundRow[] = [
  ['workspaceState', 'await memory.workspaceState.update(KEY, 1);', ['workspaceState']],
  ['getState()', 'const saved = vscode.getState();', ['getState']],
  ['setState(…)', 'vscode.setState({ picked: name });', ['setState']],
  ['localStorage', "window.localStorage.setItem('k', name);", ['localStorage']],
  ['sessionStorage', "const v = sessionStorage.getItem('k');", ['sessionStorage']],
  ['getState と setState が 1 行に 2 つ（出る順に返す）', 'const s = vscode.getState(); vscode.setState(s);', ['getState', 'setState']],
  ['コメントの行のあとの行にある setState（コメントと一緒に消さない）', '// 保存しない\nvscode.setState(s);', ['setState']],
];

const STORAGE_MISSED: readonly MissedRow[] = [
  ['空の文字', ''],
  ['resetState（名前の一部の setState）', 'resetState();'],
  ['setStateless・getStateOf（後ろに続く名前）', 'setStateless(); getStateOf(row);'],
  ['isLocalStorage・workspaceStatePath（名前の一部）', 'const isLocalStorage = false; const workspaceStatePath = "";'],
  ['postMessage で送るだけ', "vscode.postMessage({ type: 'ready' });"],
  ['行頭の // のコメントに書いた workspaceState', '// workspaceState には保存しない'],
  ['ブロックコメントに書いた getState・setState・localStorage・sessionStorage', '/**\n * getState・setState は使わない\n * localStorage も sessionStorage も使わない\n */\nexport const x = 1;'],
];

for (const [label, source, expected] of STORAGE_FOUND) {
  test(`D0025-AC-63: findStorage が、${label} を見つける${KEEP_NOTE}`, () => {
    assert.deepEqual(findStorage(source), expected);
  });
}
for (const [label, source] of STORAGE_MISSED) {
  test(`D0025-AC-63: findStorage が、${label} は見逃す${KEEP_NOTE}`, () => {
    assert.deepEqual(findStorage(source), []);
  });
}

// ---- D0025-AC-64：セレクタに名前を連ねる書き方 ----

/** 全体がバッククォートの文字列で、その中に JS を書く形（panelScript.ts と同じ）。バッククォートの中を文字列として読み飛ばすと、中の違反を見逃す */
const embedded = (inner: string): string => ['export const PANEL_SCRIPT = `', '(function () {', inner, '})();', '`;'].join('\n');

const SELECTOR_FOUND: readonly FoundRow[] = [
  ['querySelector の引数に + で名前を連ねる', "root.querySelector('[data-x=\"' + name + '\"]');", ['querySelector(\'[data-x="\' + name + \'"]\')']],
  ['querySelectorAll の引数に + で名前を連ねる', "root.querySelectorAll('[data-art=\"' + name + '\"]');", ['querySelectorAll(\'[data-art="\' + name + \'"]\')']],
  ['closest の引数に + で名前を連ねる', "target.closest('button[data-art-pick=\"' + name + '\"]');", ['closest(\'button[data-art-pick="\' + name + \'"]\')']],
  ['querySelector のテンプレートの ${…}', 'root.querySelector(`[data-x="${name}"]`);', ['querySelector(`[data-x="${name}"]`)']],
  ['closest のテンプレートの ${…}', 'el.closest(`[data-keep="${name}"]`);', ['closest(`[data-keep="${name}"]`)']],
  [
    "属性の名前に続けて値も連ねる '[' + attr + '=\"' + value + '\"]'（名前だけの形ではない）",
    "root.querySelectorAll('[' + key.attr + '=\"' + key.value + '\"]');",
    ['querySelectorAll(\'[\' + key.attr + \'="\' + key.value + \'"]\')'],
  ],
  ["属性の名前の形のあとに、ほかも連ねる '[' + attr + ']' + name", "root.querySelectorAll('[' + key.attr + ']' + name);", ["querySelectorAll('[' + key.attr + ']' + name)"]],
  ["属性の名前の形の前に、ほかも連ねる prefix + '[' + attr + ']'", "root.querySelector(prefix + '[' + attr + ']');", ["querySelector(prefix + '[' + attr + ']')"]],
  ['属性の名前をテンプレートの ${…} で入れる `[${attr}]`（許すのは + で連ねる形だけ。${ は見つける）', 'root.querySelectorAll(`[${key.attr}]`);', ['querySelectorAll(`[${key.attr}]`)']],
  ['.concat( でつなぐ', "root.querySelector('[data-x=\"'.concat(name, '\"]'));", ['querySelector(\'[data-x="\'.concat(name, \'"]\'))']],
  ['閉じかっこを含む文字列があっても、そのあとの + を見つける', "root.querySelector('[x=\")\"]' + name);", ['querySelector(\'[x=")"]\' + name)']],
  ['呼び出しの名前と ( のあいだの空白', "root.querySelector ('[a=\"' + n + '\"]');", ['querySelector(\'[a="\' + n + \'"]\')']],
  ['変数に組み立ててから渡す（[属性="…" に + が続く）', "const sel = '[data-x=\"' + name + '\"]';\nroot.querySelector(sel);", ['[data-x="\' +']],
  ['変数に組み立ててから渡す（引用符のない [属性= に + が続く）', "const sel = '[data-x=' + name + ']';\nroot.querySelector(sel);", ["[data-x=' +"]],
  ['変数に組み立ててから渡す（テンプレートの [属性="${…}"]）', 'const sel = `[data-x="${name}"]`;\nroot.querySelector(sel);', ['[data-x="${']],
  [
    '全体がバッククォートの文字列の中の JS（panelScript.ts の形）でも見つける',
    embedded("  const again = Array.from(root.querySelectorAll('[data-art=\"' + name + '\"]'));"),
    ['querySelectorAll(\'[data-art="\' + name + \'"]\')'],
  ],
  ['行末のコメントの \' が、次の行の文字列の読みを狂わせない', "const a = 1; // it's\nroot.querySelector('[x=\"' + n + '\"]');", ['querySelector(\'[x="\' + n + \'"]\')']],
  ['コメントの行のあとの行（コメントと一緒に消さない）', "// 名前で探す\nroot.querySelector('.x' + name);", ["querySelector('.x' + name)"]],
  ['2 つ（出る順に返す）', "a.querySelector('.x' + i);\nb.closest('.y' + j);", ["querySelector('.x' + i)", "closest('.y' + j)"]],
];

const SELECTOR_MISSED: readonly MissedRow[] = [
  ['空の文字', ''],
  // D0025 は「焦点の復元は今の focusKey／restoreFocus のまま」と決めた。名前（data-keep・data-run・data-reasons の固定の 3 つ）を連ねるだけで、値は連ねない
  ["属性の名前だけを連ねる '[' + attr + ']'（今の panelScript.ts の restoreFocus の形。値の位置ではない）", "root.querySelectorAll('[' + key.attr + ']');"],
  // 許す形を key.attr の 1 つだけに狭めたので（D0025-AC-64）、ここにあった「attr だけ（空白なし・二重引用符・closest）」と
  // 「識別子の入れ子 a.b.c」の 2 つの見本は、見つけるほうへ移した（下の SELECTOR_ATTR_FOUND）。key.attr の空白なし・二重引用符・closest の形は SELECTOR_ATTR_MISSED が持つ。
  [
    "全体がバッククォートの文字列の中の、属性の名前だけを連ねる形（今の panelScript.ts の restoreFocus の形）",
    embedded("  const again = Array.from(root.querySelectorAll('[' + key.attr + ']')).find(function (n) { return n.getAttribute(key.attr) === key.value; });"),
  ],
  [
    '属性値の等値比較（getAttribute(…) === name）',
    "const again = Array.from(root.querySelectorAll('[data-art-pick]')).find((n) => n.getAttribute('data-art-pick') === name);",
  ],
  [
    '属性の名前を変数で比べる等値比較',
    "Array.from(root.querySelectorAll('[data-keep]')).find(function (n) { return n.getAttribute(key.attr) === key.value; });",
  ],
  ['全体がバッククォートの文字列の中の等値比較（panelScript.ts の形）', embedded("  Array.from(root.querySelectorAll('[data-art]')).find(function (n) { return n.getAttribute('data-art') === name; });")],
  ['固定のセレクタ（引用符つきの値でも連ねない）', "root.querySelector('button[data-run][aria-pressed=\"true\"]'); el.closest('[hidden]');"],
  ['完全な値を持つ固定のセレクタ', "root.querySelectorAll('[data-scroll=\"list\"]');"],
  ['変数だけの引数', 'root.querySelectorAll(COUNTING);'],
  ["文字列の中の + （CSS の隣の記号）", "root.querySelectorAll('li + li');"],
  ['文字列の中の ( ) と引用符', "root.querySelector('[x=\")\"]');"],
  ['呼び出しの外の +', "const label = 'a' + name;\nroot.querySelector('.x');"],
  ['呼び出しのあとの +（引数に入らない）', "const n = root.querySelectorAll('.x').length + 1;"],
  ['閉じかっこを含む文字列のあとの +（引数に入らない）', "root.querySelector('[x=\")\"]') + name;"],
  ['配列の添字と足し算', 'const v = items[index] + 1;'],
  ['名前の一部（closestRow・myquerySelector）', "rows.closestRow('x' + n); myquerySelector('a' + b);"],
  ['行頭の // のコメントに書いた連ねる形', "// root.querySelector('[a=\"' + n + '\"]');"],
  ['ブロックコメントに書いた連ねる形', '/**\n * closest(`[a="${n}"]`) は使わない\n */\nexport const x = 1;'],
];

for (const [label, source, expected] of SELECTOR_FOUND) {
  test(`D0025-AC-64: findSelectorConcat が、${label} を見つける${KEEP_NOTE}`, () => {
    assert.deepEqual(findSelectorConcat(source), expected);
  });
}
for (const [label, source] of SELECTOR_MISSED) {
  test(`D0025-AC-64: findSelectorConcat が、${label} は見逃す${KEEP_NOTE}`, () => {
    assert.deepEqual(findSelectorConcat(source), []);
  });
}

test(`D0025-AC-64: 現物の panelScript.ts（全体がバッククォートの文字列）の中に名前を連ねた行を 1 行足すと、findSelectorConcat が見つける${KEEP_NOTE}`, () => {
  // 現物そのものの検査（連ねた書き方が無いこと）は、パネルのスクリプトのテストが持つ。ここは、現物の形でも探す関数が中を読めること（見逃して空を返さないこと）だけ
  const real = readFileSync(new URL('../view/panelScript.ts', import.meta.url), 'utf8');
  const start = '(function () {';
  assert.ok(real.includes(start), 'スクリプトの始まり（(function () {）が現物にある');
  const probe = "\n  const probe = root.querySelector('[data-probe=\"' + name + '\"]');";
  const found = findSelectorConcat(real.replace(start, () => start + probe));
  assert.ok(
    found.some((f) => f.includes('data-probe')),
    `足した行が見つかる：${JSON.stringify(found)}`,
  );
});

// ---- D0025-AC-64：許す連ね方は '[' + key.attr + ']' の 1 つだけ ----
// 直す前は、'[' + 識別子の連なり + ']' なら何でも許していたので、'[' + name + ']' のように、外から来た名前を属性の名前の位置に連ねる書き方まで見逃した。
// 直したあとは、restoreFocus の '[' + key.attr + ']'（data-keep・data-run・data-reasons の固定の 3 つの名前）だけを許す。直しを外すと、下の見つける見本が落ちる。

const SELECTOR_ATTR_FOUND: readonly FoundRow[] = [
  ["'[' + name + ']'（key.attr 以外の識別子。外から来た名前を属性の名前の位置に連ねる）", "root.querySelectorAll('[' + name + ']');", ["querySelectorAll('[' + name + ']')"]],
  ["'[' + key.name + ']'（key の別の項目）", "root.querySelector('[' + key.name + ']');", ["querySelector('[' + key.name + ']')"]],
  ["'[' + key.attrs + ']'（attr で終わらない名前）", "root.querySelector('[' + key.attrs + ']');", ["querySelector('[' + key.attrs + ']')"]],
  ["'[' + key.attr.name + ']'（key.attr の先に、さらに続く）", "root.querySelector('[' + key.attr.name + ']');", ["querySelector('[' + key.attr.name + ']')"]],
  ["'[' + monkey.attr + ']'（key で終わる別の名前）", "root.closest('[' + monkey.attr + ']');", ["closest('[' + monkey.attr + ']')"]],
  ["'[' + x.key.attr + ']'（key.attr の前に、別の名前が付く）", "root.querySelector('[' + x.key.attr + ']');", ["querySelector('[' + x.key.attr + ']')"]],
  // 直す前は見逃していた 2 つ（直す前の SELECTOR_MISSED の見本。attr だけの形・識別子の入れ子）。許すのは key.attr だけにしたので、見つけるほうへ移した
  ['attr だけを連ねる（空白なし・二重引用符・closest）。key. が付かない', 'el.closest("["+attr+"]");', ['closest("["+attr+"]")']],
  ['識別子の入れ子 a.b.c を連ねる', "root.querySelectorAll('[' + a.b.c + ']');", ["querySelectorAll('[' + a.b.c + ']')"]],
  [
    "全体がバッククォートの文字列の中（panelScript.ts の形）の '[' + name + ']'",
    embedded("  const again = Array.from(root.querySelectorAll('[' + name + ']')).find(function (n) { return n.getAttribute(name) === value; });"),
    ["querySelectorAll('[' + name + ']')"],
  ],
];

/** key.attr の形（restoreFocus）は、空白の入れ方や引用符を変えても見逃す */
const SELECTOR_ATTR_MISSED: readonly MissedRow[] = [
  ['key.attr（空白なし・二重引用符・closest）', 'el.closest("["+key.attr+"]");'],
  ['key . attr（ドットの前後に空白）', "root.querySelectorAll('[' + key . attr + ']');"],
  ['key.attr（+ の前後に空白をたくさん）', "root.querySelectorAll('['   +   key.attr   +   ']');"],
];

for (const [label, source, expected] of SELECTOR_ATTR_FOUND) {
  test(`D0025-AC-64: findSelectorConcat が、${label} を見つける（許す形は key.attr だけ）`, () => {
    assert.deepEqual(findSelectorConcat(source), expected);
  });
}
for (const [label, source] of SELECTOR_ATTR_MISSED) {
  test(`D0025-AC-64: findSelectorConcat が、${label} は見逃す（許す形の書き方の違い。${KEEP_NOTE.slice(1)}`, () => {
    assert.deepEqual(findSelectorConcat(source), []);
  });
}

test("D0025-AC-64: 現物の panelScript.ts の restoreFocus の行（'[' + key.attr + ']'）は、許す形を key.attr だけに狭めたあとも見逃され、現物の全体の違反も 0 件（今のまま通る。守る）", () => {
  const real = readFileSync(new URL('../view/panelScript.ts', import.meta.url), 'utf8');
  const lines = real.split('\n').filter((l) => l.includes("'[' + key.attr + ']'"));
  assert.equal(lines.length, 1, '現物に restoreFocus の行が 1 つある');
  assert.deepEqual(findSelectorConcat(embedded(lines[0])), []);
  assert.deepEqual(findSelectorConcat(real), []);
});

test("D0025-AC-64: 現物の panelScript.ts の中に '[' + name + ']' の行を 1 行足すと、findSelectorConcat が見つける（restoreFocus の行は見逃したまま）", () => {
  const real = readFileSync(new URL('../view/panelScript.ts', import.meta.url), 'utf8');
  const start = '(function () {';
  assert.ok(real.includes(start), 'スクリプトの始まり（(function () {）が現物にある');
  const probe = "\n  const probe = root.querySelectorAll('[' + name + ']');";
  assert.deepEqual(findSelectorConcat(real.replace(start, () => start + probe)), ["querySelectorAll('[' + name + ']')"]);
});

// ---- D0025-AC-43：readHead の確保（Buffer.allocUnsafe と subarray(0, bytesRead)） ----
// 小さいファイルでも 256 KiB を 0 で埋めて確保しない（軽くする）。確保しただけの領域を漏らさないよう、読んだ分だけを返す。一方だけだと漏れる。

/** readHead の宣言の見本。body が本体の中の確保と返し方、extra が readHead の前に置く別の宣言 */
const readHeadSource = (body: string, extra = ''): string =>
  [
    'import { open } from "node:fs/promises";',
    '',
    extra,
    'async function readHead(file: string, maxBytes: number): Promise<string> {',
    '  const handle = await open(file, "r");',
    '  try {',
    body,
    '  } finally {',
    '    await handle.close();',
    '  }',
    '}',
    '',
  ].join('\n');

const GOOD_ALLOC = '    const buffer = Buffer.allocUnsafe(Math.max(0, Math.floor(maxBytes)));';
const GOOD_READ = '    const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0);';
const GOOD_RETURN = '    return buffer.subarray(0, bytesRead).toString("utf8");';
const GOOD_BODY = [GOOD_ALLOC, GOOD_READ, GOOD_RETURN].join('\n');
const PROBLEM_ZERO_ALLOC = 'Buffer.alloc( で確保している（Buffer.allocUnsafe( にする）';
const PROBLEM_NO_LIGHT_ALLOC = 'Buffer.allocUnsafe( で確保していない';
const PROBLEM_NO_TRIM = '読んだ分だけ .subarray(0, bytesRead) で返していない（確保したままの領域を漏らす）';
const PROBLEM_NO_DECLARATION = 'readHead の宣言（function readHead(…) { … }）が読めない';

const ALLOC_FOUND: readonly FoundRow[] = [
  [
    'Buffer.alloc のまま（0 で埋めて確保する、D0025 より前の readOnlyFs.ts の形）',
    readHeadSource([GOOD_ALLOC.replace('allocUnsafe', 'alloc'), GOOD_READ, GOOD_RETURN].join('\n')),
    [PROBLEM_ZERO_ALLOC, PROBLEM_NO_LIGHT_ALLOC],
  ],
  ['確保は軽いが、subarray で切らずに返す（確保しただけの領域を漏らす）', readHeadSource([GOOD_ALLOC, GOOD_READ, '    return buffer.toString("utf8");'].join('\n')), [PROBLEM_NO_TRIM]],
  [
    'subarray の範囲が bytesRead でない',
    readHeadSource([GOOD_ALLOC, GOOD_READ, '    return buffer.subarray(0, buffer.length).toString("utf8");'].join('\n')),
    [PROBLEM_NO_TRIM],
  ],
  [
    'Buffer.alloc( と Buffer.allocUnsafe( の両方がある（alloc も残っている）',
    readHeadSource(['    const zero = Buffer.alloc(1);', GOOD_ALLOC, GOOD_READ, GOOD_RETURN].join('\n')),
    [PROBLEM_ZERO_ALLOC],
  ],
  [
    'allocUnsafe がコメント（行頭・行末）にだけある',
    readHeadSource(
      [
        '    // Buffer.allocUnsafe( にする',
        '    const buffer = Buffer.alloc(Math.max(0, Math.floor(maxBytes))); // Buffer.allocUnsafe(',
        GOOD_READ,
        GOOD_RETURN,
      ].join('\n'),
    ),
    [PROBLEM_ZERO_ALLOC, PROBLEM_NO_LIGHT_ALLOC],
  ],
  [
    'subarray(0, bytesRead) が行末のコメントにだけある',
    readHeadSource([GOOD_ALLOC, GOOD_READ, '    return buffer.toString("utf8"); // buffer.subarray(0, bytesRead)'].join('\n')),
    [PROBLEM_NO_TRIM],
  ],
  [
    'allocUnsafe と subarray(0, bytesRead) が別の関数にだけある（readHead は alloc のまま・切らない）',
    readHeadSource(
      ['    const buffer = Buffer.alloc(maxBytes);', GOOD_READ, '    return buffer.toString("utf8");'].join('\n'),
      'function other(n: number, bytesRead: number) { return Buffer.allocUnsafe(n).subarray(0, bytesRead); }',
    ),
    [PROBLEM_ZERO_ALLOC, PROBLEM_NO_LIGHT_ALLOC, PROBLEM_NO_TRIM],
  ],
  ['readHead の宣言が無い', 'export const x = 1;\nconst buffer = Buffer.allocUnsafe(8);\nbuffer.subarray(0, bytesRead);\n', [PROBLEM_NO_DECLARATION]],
  ['空の文字', '', [PROBLEM_NO_DECLARATION]],
];

const ALLOC_MISSED: readonly MissedRow[] = [
  ['Buffer.allocUnsafe と subarray(0, bytesRead)（今の readOnlyFs.ts の形）', readHeadSource(GOOD_BODY)],
  ['Buffer.allocUnsafeSlow で確保しても、subarray(0, bytesRead) で切るなら', readHeadSource([GOOD_ALLOC.replace('allocUnsafe', 'allocUnsafeSlow'), GOOD_READ, GOOD_RETURN].join('\n'))],
  [
    '空白・改行を入れた書き方（Buffer . allocUnsafe ( と .subarray( 0 , bytesRead )）',
    readHeadSource(
      ['    const buffer = Buffer . allocUnsafe (maxBytes);', GOOD_READ, '    return buffer\n      .subarray( 0 , bytesRead )\n      .toString("utf8");'].join('\n'),
    ),
  ],
  [
    '行末のコメントに Buffer.alloc( と書いた正しい形',
    readHeadSource([GOOD_ALLOC + ' // Buffer.alloc( ではなく軽い確保', GOOD_READ, GOOD_RETURN].join('\n')),
  ],
  [
    '行頭のコメントに Buffer.alloc( と書いた正しい形',
    readHeadSource(['    // Buffer.alloc( は使わない', GOOD_ALLOC, GOOD_READ, GOOD_RETURN].join('\n')),
  ],
  [
    'readHead の外の別の関数にある Buffer.alloc( は数えない',
    readHeadSource(GOOD_BODY, 'function zeros(n: number) { return Buffer.alloc(n); }'),
  ],
  [
    '文字列の中の // があっても本体の読みが狂わない',
    readHeadSource(['    const note = "http://example.com/a";', GOOD_ALLOC, GOOD_READ, GOOD_RETURN].join('\n')),
  ],
];

for (const [label, source, expected] of ALLOC_FOUND) {
  test(`D0025-AC-43: findReadHeadAlloc が、${label} を見つける${KEEP_NOTE}`, () => {
    assert.deepEqual(findReadHeadAlloc(source), expected);
  });
}
for (const [label, source] of ALLOC_MISSED) {
  test(`D0025-AC-43: findReadHeadAlloc が、${label} は見逃す${KEEP_NOTE}`, () => {
    assert.deepEqual(findReadHeadAlloc(source), []);
  });
}
