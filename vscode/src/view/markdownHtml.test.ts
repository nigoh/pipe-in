// Markdown → HTML の変換 renderMarkdown（D0025・FR-08）：書き方の範囲（AC-18〜29・34）と、同じ入力から同じ出力（AC-30）。
// 外から来た文字の扱い（AC-31〜33）と極端な入力（AC-36）は markdownHtmlSafety.test.ts が持つ。
// 新しい部品（view/markdownHtml.ts）は、テストの中で読み込む（テスト先行のとき、まだ無い部品が「モジュールが無い」で各テストが落ち、
// ファイルごと読めずに落ちることが無いようにした。前例：domain/runListCounts.test.ts の rl()）。
// 出力の形は、タグのあいだの改行・<hr> の書き方・コードの終わりの改行を norm でそろえてから、タグごと文字で突き合わせる
// （AC-20 の例 ul[li(a, ul[li(b)])] は <ul><li>a<ul><li>b</li></ul></li></ul>。表は div.md-table で包まれる）。
// AC に書いていない細かい境目（決定の記録 D0025 の「聞かずに決めたこと」）は、「AC に無い境目」と書いて固定する。
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { escapeHtml } from './escape.ts';
import { findClockOrNode } from '../test/sourceText.ts';

/** 使う分だけの型。テスト先行のとき markdownHtml.ts がまだ無くても型検査が通るよう、読み込みの指定を定数でない形にして型を与えた */
interface MarkdownHtmlMod {
  renderMarkdown(source: string): string;
}
const md = (): Promise<MarkdownHtmlMod> => import(String('./markdownHtml.ts')) as Promise<MarkdownHtmlMod>;
const HERE = path.dirname(fileURLToPath(import.meta.url));

const FENCE = '`'.repeat(3);

/** タグのあいだの改行・<hr /> の書き方・コードの終わりの改行をそろえる（形の細かい違いで赤にならないように） */
function norm(html: string): string {
  return html
    .trim()
    .replace(/\s*\n\s*(?=<)/g, '')
    .replace(/(?<=>)\s*\n\s*/g, '')
    .replace(/<hr\s*\/?>/g, '<hr>');
}

async function render(source: string): Promise<string> {
  const { renderMarkdown } = await md();
  return norm(renderMarkdown(source));
}

// ---- 期待の組み立て（文字は escapeHtml 済みの HTML で渡す） ----

const L = (...lines: string[]): string => lines.join('\n');
const P = (html: string): string => `<p>${html}</p>`;
const HR = '<hr>';
type Level = 1 | 2 | 3 | 4 | 5 | 6;
const h = (level: Level, html: string): string => {
  const tag = Math.min(level + 2, 6);
  return `<h${tag} class="md-h${level}">${html}</h${tag}>`;
};
const li = (inner: string): string => `<li>${inner}</li>`;
const ul = (...items: string[]): string => `<ul>${items.map((i) => li(i)).join('')}</ul>`;
const ol = (...items: string[]): string => `<ol>${items.map((i) => li(i)).join('')}</ol>`;
const olFrom = (start: number, ...items: string[]): string => `<ol start="${start}">${items.map((i) => li(i)).join('')}</ol>`;
const bq = (html: string): string => `<blockquote>${html}</blockquote>`;
const pre = (text: string): string => `<pre><code>${text}</code></pre>`;

type Align = 'left' | 'center' | 'right' | null;
function table(head: string[], rows: string[][], aligns: Align[] = []): string {
  const cell = (tag: 'th' | 'td', html: string, i: number): string => {
    const a = aligns[i] ?? null;
    return a === null ? `<${tag}>${html}</${tag}>` : `<${tag} class="md-${a}">${html}</${tag}>`;
  };
  const tr = (tag: 'th' | 'td', cells: string[]): string => `<tr>${cells.map((c, i) => cell(tag, c, i)).join('')}</tr>`;
  const body = rows.length === 0 ? '' : `<tbody>${rows.map((r) => tr('td', r)).join('')}</tbody>`;
  return `<div class="md-table"><table><thead>${tr('th', head)}</thead>${body}</table></div>`;
}

type Row = readonly [label: string, source: string, expected: string];

function cases(id: string, rows: readonly Row[]): void {
  for (const [label, source, expected] of rows) {
    test(`${id}: ${label}`, async () => {
      assert.equal(await render(source), expected, `入力：${JSON.stringify(source)}`);
    });
  }
}

// ---- 検査の足場そのものの確かめ（このファイルの norm と期待の組み立てが、決めた形を作ること。製品の部品に頼らないので、今のまま通る） ----

const KEEP_NOTE = '（今のまま通る。守る）';

test(`D0025-AC-20: 検査の足場：norm はタグのあいだの改行と <hr /> の書き方・コードの終わりの改行をそろえ、文の中の空白とコードの中の改行は残す${KEEP_NOTE}`, () => {
  assert.equal(norm('<p>a</p>\n<p>b</p>\n'), '<p>a</p><p>b</p>');
  assert.equal(norm('<ul>\n  <li>a</li>\n</ul>'), '<ul><li>a</li></ul>');
  assert.equal(norm('<li>a\n<ul><li>b</li></ul></li>'), '<li>a<ul><li>b</li></ul></li>');
  for (const hr of ['<hr>', '<hr/>', '<hr />']) assert.equal(norm(hr), '<hr>');
  assert.equal(norm('<pre><code>a\nb\n</code></pre>'), '<pre><code>a\nb</code></pre>');
  assert.equal(norm('<p>a <strong>b</strong> c</p>'), '<p>a <strong>b</strong> c</p>');
});

test(`D0025-AC-18: 検査の足場：見出しの組み立ては # が h3、## が h4、### が h5、#### 以降が h6（class は md-h<段>）${KEEP_NOTE}`, () => {
  assert.equal(h(1, 'x'), '<h3 class="md-h1">x</h3>');
  assert.equal(h(2, 'x'), '<h4 class="md-h2">x</h4>');
  assert.equal(h(3, 'x'), '<h5 class="md-h3">x</h5>');
  assert.equal(h(4, 'x'), '<h6 class="md-h4">x</h6>');
  assert.equal(h(6, 'x'), '<h6 class="md-h6">x</h6>');
});

test(`D0025-AC-20: 検査の足場：一覧の組み立ては、入れ子を li の中に置き、start は ol に付ける${KEEP_NOTE}`, () => {
  assert.equal(ul('a' + ul('b'), 'c'), '<ul><li>a<ul><li>b</li></ul></li><li>c</li></ul>');
  assert.equal(ol('a'), '<ol><li>a</li></ol>');
  assert.equal(olFrom(3, 'x', 'y'), '<ol start="3"><li>x</li><li>y</li></ol>');
});

test(`D0025-AC-22: 検査の足場：表の組み立ては div.md-table の中の table で、寄せは th と td の class、本文が 0 行なら tbody を出さない${KEEP_NOTE}`, () => {
  assert.equal(
    table(['a', 'b'], [['1', '2']], ['left', null]),
    '<div class="md-table"><table><thead><tr><th class="md-left">a</th><th>b</th></tr></thead><tbody><tr><td class="md-left">1</td><td>2</td></tr></tbody></table></div>',
  );
  assert.equal(table(['a'], []), '<div class="md-table"><table><thead><tr><th>a</th></tr></thead></table></div>');
});

// ---- AC-18：見出し ----

cases('D0025-AC-18', [
  ['見出し：# は h3（class md-h1）', '# 題', h(1, '題')],
  ['見出し：## は h4（class md-h2）', '## 題', h(2, '題')],
  ['見出し：### は h5（class md-h3）', '### 題', h(3, '題')],
  ['見出し：#### は h6（class md-h4）', '#### 題', h(4, '題')],
  ['見出し：##### は h6（class md-h5）', '##### 題', h(5, '題')],
  ['見出し：###### は h6（class md-h6）', '###### 題', h(6, '題')],
  ['見出し：# の後ろの空白は何個でもよい', '##   題', h(2, '題')],
  ['見出し：行末の # は取らない', '# 題 #', h(1, '題 #')],
  ['見出し：行末の ## も取らない', '## 題 ##', h(2, '題 ##')],
  ['見出し：文字は escapeHtml を通る', '# a<b', h(1, escapeHtml('a<b'))],
  ['見出し：前後の行とつながらず、段落と見出しに分かれる', L('前', '# 題', '後'), P('前') + h(1, '題') + P('後')],
  ['見出しにならない：#題（空白なし）は段落の文字', '#題', P('#題')],
  ['見出しにならない：# だけの行は段落の文字', '#', P('#')],
  ['見出しにならない：# と空白だけの行（文字が続かない）は段落の文字', '# ', P('#')],
  ['見出しにならない：7 個の # は段落の文字', '####### 題', P('####### 題')],
]);

// ---- AC-19：段落 ----

cases('D0025-AC-19', [
  ['段落：1 行は 1 つの p', 'あいう', P('あいう')],
  ['段落：続く行は 1 つの段落で、行の切れ目は空白 1 つ', L('a', 'b', 'c'), P('a b c')],
  ['段落：空行で段落が分かれる', L('a', '', 'b'), P('a') + P('b')],
  ['段落：空行が何行続いても分かれるだけ', L('a', '', '', '', 'b'), P('a') + P('b')],
  ['段落：空白だけの行も空行', L('a', '   ', 'b'), P('a') + P('b')],
  ['段落：入力の \\r\\n は \\n と同じ', 'a\r\nb\r\n\r\nc', P('a b') + P('c')],
  ['段落：行末の空白 2 つで br を作らない', 'a  \nb', P('a b')],
  ['段落：行の前後の空白は取る', L('  a  ', '  b  '), P('a b')],
  ['段落：先頭と末尾の空行は出力に出ない', L('', '', 'a', '', ''), P('a')],
  ['段落：下線の見出し（===）は使わず、段落の文字', L('題', '==='), P('題 ===')],
  ['段落は見出しの開始で終わる', L('a', '# b'), P('a') + h(1, 'b')],
  ['段落は箇条書きの項目の開始で終わる', L('a', '- b'), P('a') + ul('b')],
  ['段落は番号つきの項目の開始で終わる', L('a', '1. b'), P('a') + ol('b')],
  ['段落は引用の開始で終わる', L('a', '> b'), P('a') + bq(P('b'))],
  ['段落はコードブロックの囲みの開始で終わる', L('a', FENCE, 'b', FENCE), P('a') + pre('b')],
  ['段落は表の頭と区切り行で終わる', L('a', '| h |', '|---|', '| 1 |'), P('a') + table(['h'], [['1']])],
]);

test('D0025-AC-19: 空の入力は空の出力', async () => {
  const { renderMarkdown } = await md();
  assert.equal(renderMarkdown(''), '');
});

test('D0025-AC-19: 空行と空白だけの入力も空の出力', async () => {
  const { renderMarkdown } = await md();
  for (const source of ['\n', '\n\n\n', '   ', ' \n  \n\t\n', '\r\n\r\n']) {
    assert.equal(renderMarkdown(source).trim(), '', JSON.stringify(source));
  }
});

// ---- AC-20：箇条書き ----

cases('D0025-AC-20', [
  ['箇条書き：- は ul の項目', L('- a', '- b'), ul('a', 'b')],
  ['箇条書き：* と + も ul の項目で、印が混ざっても 1 つの ul', L('* a', '+ b', '- c'), ul('a', 'b', 'c')],
  ['箇条書き：1. のように数字と . と空白は ol の項目', L('1. a', '2. b'), ol('a', 'b')],
  ['箇条書き：入れ子（- a / 2 つ字下げ - b / 4 つ字下げ - c / - d）', L('- a', '  - b', '    - c', '- d'), ul('a' + ul('b' + ul('c')), 'd')],
  ['箇条書き：空白 4 つの字下げは直前の項目の子', L('- a', '    - b'), ul('a' + ul('b'))],
  ['箇条書き：タブ 1 つ（空白 4 つ）の字下げは子', L('- a', '\t- b'), ul('a' + ul('b'))],
  ['箇条書き：同じ深さは兄弟', L('- a', '- b', '- c'), ul('a', 'b', 'c')],
  ['箇条書き：浅くなれば同じ深さの項目まで戻る', L('- a', '  - b', '    - c', '  - d'), ul('a' + ul('b' + ul('c'), 'd'))],
  ['箇条書き：1 つだけ深い字下げは子にならず兄弟（子は 2 つ以上深いとき）', L('- a', ' - b'), ul('a', 'b')],
  ['箇条書き：4 段目の項目は 3 段目の兄弟', L('- a', '  - b', '    - c', '      - d'), ul('a' + ul('b' + ul('c', 'd')))],
  ['箇条書き：5 段目以降も 3 段目に並ぶ', L('- a', '  - b', '    - c', '      - d', '        - e'), ul('a' + ul('b' + ul('c', 'd', 'e')))],
  ['箇条書き：ul の項目の子に ol を置ける', L('- a', '  1. b'), ul('a' + ol('b'))],
  ['箇条書き：ol の項目の子に ul を置ける', L('1. a', '   - b'), ol('a' + ul('b'))],
  ['箇条書き：項目の中でコード・太字が使える', '- **b** `c`', ul('<strong>b</strong> <code>c</code>')],
  ['箇条書きにならない：**太字** は項目にしない', '**太字**', P('<strong>太字</strong>')],
  ['箇条書きにならない：*斜体* で始まる文は項目にしない', '*i* x', P('<em>i</em> x')],
  ['箇条書きにならない：-a（空白が続かない）は段落の文字', '-a', P('-a')],
  ['箇条書きにならない：1.a（空白が続かない）は段落の文字', '1.a', P('1.a')],
  ['箇条書き：印のない行は直前の項目の文字の続き（空白 1 つでつなぐ）', L('- a', 'b', '- c'), ul('a b', 'c')],
  ['箇条書き：字下げした印のない行も続き', L('- a', '  b'), ul('a b')],
  ['箇条書き：空行をはさんでも、次の行が同じ種類の項目なら同じ一覧（項目が 2 つの ul が 1 つ）', L('- a', '', '- b'), ul('a', 'b')],
  ['箇条書き：空行をはさんでも ol は同じ一覧', L('1. a', '', '2. b'), ol('a', 'b')],
  ['箇条書き：空行のあとの印のない行は一覧を終わらせて段落', L('- a', '', 'b'), ul('a') + P('b')],
  ['箇条書き：空行のあとの別の種類の項目は新しい一覧（ul → ol）', L('- a', '', '1. b'), ul('a') + ol('b')],
  ['箇条書き：ul から ol に替わると同じ深さで一覧を閉じて開き直す（AC に無い境目）', L('- a', '1. b'), ul('a') + ol('b')],
  ['箇条書き：ol から ul に替わると同じ深さで一覧を閉じて開き直す（AC に無い境目）', L('1. a', '- b'), ol('a') + ul('b')],
  ['一覧を終わらせる：見出し', L('- a', '# b'), ul('a') + h(1, 'b')],
  ['一覧を終わらせる：コードブロックの囲み', L('- a', FENCE, 'x', FENCE), ul('a') + pre('x')],
  ['一覧を終わらせる：表', L('- a', '| h |', '|---|', '| 1 |'), ul('a') + table(['h'], [['1']])],
  ['一覧を終わらせる：引用', L('- a', '> q'), ul('a') + bq(P('q'))],
  ['一覧を終わらせる：--- の行', L('- a', '---'), ul('a') + HR],
  ['一覧を終わらせる：終わったあとの項目は新しい一覧', L('- a', '---', '- b'), ul('a') + HR + ul('b')],
]);

test('D0025-AC-20: AC に無い境目：- - - は hr ではなく箇条書き（間の空白は許さない）', async () => {
  const out = await render('- - -');
  assert.match(out, /^<ul><li>/, out);
  assert.doesNotMatch(out, /<hr/, out);
});

// ---- AC-21：番号つき箇条書きの番号 ----

cases('D0025-AC-21', [
  ['ol の start：最初の数字が 2 なら start="2"', '2. a', olFrom(2, 'a')],
  ['ol の start：最初の数字が 1 なら付けない', '1. a', ol('a')],
  ['ol の start：最初の数字が 0 なら付けない', '0. a', ol('a')],
  ['ol の start：最初の数字が 9999 なら start="9999"', '9999. a', olFrom(9999, 'a')],
  ['ol の start：最初の数字が 10000 以上なら付けず、ol の項目のまま（段落にならない）', '10000. a', ol('a')],
  ['ol の start：5 桁の 12345 も付けない', '12345. a', ol('a')],
  ['ol の start：20 桁の数字も ol の項目で、start なし（例外なし）', '99999999999999999999. a', ol('a')],
  ['ol の start：02. は start="2"（AC に無い境目）', '02. a', olFrom(2, 'a')],
  ['ol の start：3. x / 4. y は start="3" の 2 項目', L('3. x', '4. y'), olFrom(3, 'x', 'y')],
  ['ol の start：2 つ目以降の数字は読まない（連番）', L('1. a', '5. b', '3. c'), ol('a', 'b', 'c')],
  ['ol の start：最初が 5 なら 2 つ目の 1 は読まず start="5"', L('5. a', '1. b'), olFrom(5, 'a', 'b')],
  ['ol の start：コードブロックで分かれた ol は、あとの ol に start="2"', L('1. a', FENCE, 'code', FENCE, '2. b'), ol('a') + pre('code') + olFrom(2, 'b')],
]);

// ---- AC-22・23・24：表 ----

cases('D0025-AC-22', [
  ['表：頭の行・区切り行・本文の行が thead・tbody の table になる', L('| a | b |', '|---|---|', '| 1 | 2 |'), table(['a', 'b'], [['1', '2']])],
  ['表：両端の | を省いた表', L('a | b', '--- | ---', '1 | 2'), table(['a', 'b'], [['1', '2']])],
  ['表：区切り行のセルは - が 1 つでもよい', L('| a | b |', '|-|-|', '| 1 | 2 |'), table(['a', 'b'], [['1', '2']])],
  ['表：セルの前後の空白は取る', L('|   a   |  b|', '|---|---|', '|  1|2   |'), table(['a', 'b'], [['1', '2']])],
  ['表：本文の行が複数', L('| a |', '|---|', '| 1 |', '| 2 |', '| 3 |'), table(['a'], [['1'], ['2'], ['3']])],
  ['表：本文は | を含まない行の前まで', L('| a |', '|---|', '| 1 |', '後ろの文'), table(['a'], [['1']]) + P('後ろの文')],
  ['表：本文は空行の前まで（空行のあとの | の行は表の本文でなく段落）', L('| a |', '|---|', '| 1 |', '', '| 2 |'), table(['a'], [['1']]) + P('| 2 |')],
  ['表：段落のあとに空行なしで続く表', L('前', '| a |', '|---|', '| 1 |'), P('前') + table(['a'], [['1']])],
  ['表：表のあとの空行のあとは通常の段落', L('| a |', '|---|', '| 1 |', '', '後'), table(['a'], [['1']]) + P('後')],
  ['表にならない：区切り行が無い | の行は段落の文字', '| a | b |', P('| a | b |')],
  ['表にならない：区切り行が無い 2 行は 1 つの段落', L('| a | b |', '| 1 | 2 |'), P('| a | b | | 1 | 2 |')],
  ['表にならない：| を含まない行と --- は、表の頭と区切り行ではなく、段落と hr', L('a b', '---'), P('a b') + HR],
  ['表にならない：区切り行のセルの数が頭の行とちがう', L('| a | b |', '|---|', '| 1 | 2 |'), P('| a | b | |---| | 1 | 2 |')],
  ['表にならない：区切り行のセルが :?-+: の形でない', L('| a | b |', '|--x|---|', '| 1 | 2 |'), P('| a | b | |--x|---| | 1 | 2 |')],
  ['表：本文が 0 行の表は tbody を出さない（AC に無い境目）', L('| a |', '|---|'), table(['a'], [])],
]);

cases('D0025-AC-23', [
  ['表の寄せ：--- だけの列は class なし', L('| a |', '|---|', '| 1 |'), table(['a'], [['1']], [null])],
  ['表の寄せ：:-- は md-left', L('| a |', '|:--|', '| 1 |'), table(['a'], [['1']], ['left'])],
  ['表の寄せ：:--: は md-center', L('| a |', '|:--:|', '| 1 |'), table(['a'], [['1']], ['center'])],
  ['表の寄せ：--: は md-right', L('| a |', '|--:|', '| 1 |'), table(['a'], [['1']], ['right'])],
  [
    '表の寄せ：列ごとに class が決まり、th にも td にも付く',
    L('| a | b | c | d |', '|:--|:--:|--:|---|', '| 1 | 2 | 3 | 4 |', '| 5 | 6 | 7 | 8 |'),
    table(['a', 'b', 'c', 'd'], [['1', '2', '3', '4'], ['5', '6', '7', '8']], ['left', 'center', 'right', null]),
  ],
  [
    '表の寄せ：短い書き方 :-: と :- と -: も同じ',
    L('| a | b | c |', '|:-:|:-|-:|', '| 1 | 2 | 3 |'),
    table(['a', 'b', 'c'], [['1', '2', '3']], ['center', 'left', 'right']),
  ],
]);

cases('D0025-AC-24', [
  ['表のセル：足りない分は空のセルにする', L('| a | b | c |', '|---|---|---|', '| 1 |', '| 1 | 2 |'), table(['a', 'b', 'c'], [['1', '', ''], ['1', '2', '']])],
  ['表のセル：余りは捨てる', L('| a | b |', '|---|---|', '| 1 | 2 | 3 | 4 |'), table(['a', 'b'], [['1', '2']])],
  ['表のセル：\\| はセルの中の |', L('| x | y |', '|---|---|', '| a \\| b | c |'), table(['x', 'y'], [['a | b', 'c']])],
  ['表のセル：ヘッダのセルの \\| も', L('| a \\| b | c |', '|---|---|', '| 1 | 2 |'), table(['a | b', 'c'], [['1', '2']])],
  [
    '表のセル：セルの中でコード・太字・斜体が使える',
    L('| x | y | z |', '|---|---|---|', '| `c` | **b** | *i* |'),
    table(['x', 'y', 'z'], [['<code>c</code>', '<strong>b</strong>', '<em>i</em>']]),
  ],
  ['表のセル：ヘッダのセルでも太字が使える', L('| **x** |', '|---|', '| 1 |'), table(['<strong>x</strong>'], [['1']])],
  ['表のセル：セルの文字は escapeHtml を通る', L('| x |', '|---|', '| a<b |'), table(['x'], [[escapeHtml('a<b')]])],
]);

// ---- AC-25：コードブロック ----

cases('D0025-AC-25', [
  ['コードブロック：``` で囲んだ範囲は pre の中の code', L(FENCE, 'a', 'b', FENCE), pre('a\nb')],
  ['コードブロック：~~~ でも同じ', L('~~~', 'a', '~~~'), pre('a')],
  [
    'コードブロック：中身は変換しない（< * # - > | も文字で、escapeHtml を通る）',
    L(FENCE, '<b>*x*</b> # h', '- i', '> q', '| a |', '|---|', FENCE),
    pre(escapeHtml(L('<b>*x*</b> # h', '- i', '> q', '| a |', '|---|'))),
  ],
  ['コードブロック：言語名は出さない（class も付けない）', L(`${FENCE}js`, 'x', FENCE), pre('x')],
  ['コードブロック：閉じが無いときは最後まで', L(FENCE, 'a', 'b'), pre('a\nb')],
  ['コードブロック：閉じは同じ長さかそれ以上（5 個で閉じる）', L(FENCE, 'a', '`'.repeat(5)), pre('a')],
  ['コードブロック：開きより短い囲みでは閉じない', L('`'.repeat(4), 'a', FENCE, 'b', '`'.repeat(4)), pre(L('a', FENCE, 'b'))],
  ['コードブロック：別の記号では閉じない', L(FENCE, 'a', '~~~', 'b', FENCE), pre(L('a', '~~~', 'b'))],
  ['コードブロック：閉じの行の後ろに文字があると閉じない', L(FENCE, 'a', `${FENCE} b`, FENCE), pre(L('a', `${FENCE} b`))],
  ['コードブロック：閉じの行の後ろの空白は許す', L(FENCE, 'a', `${FENCE}   `), pre('a')],
  ['コードブロック：囲みの中の空行は残る', L(FENCE, 'a', '', 'b', FENCE), pre('a\n\nb')],
  ['コードブロック：囲みのあとは通常の段落', L(FENCE, 'a', FENCE, '後'), pre('a') + P('後')],
  ['コードブロック：中身の HTML は文字', L(FENCE, '<script>x</script>', FENCE), pre(escapeHtml('<script>x</script>'))],
  ['コードブロック：字下げした囲みは、箇条書きを終わらせて一覧の外の pre', L('- a', `  ${FENCE}`, '  code', `  ${FENCE}`), ul('a') + pre('code')],
  ['コードブロック：字下げ 4 つ以上の囲みも囲み（囲みは何個字下げしてもよい）', L(`    ${FENCE}`, '    code', `    ${FENCE}`), pre('code')],
  [
    'コードブロック：中身の各行から、開始行と同じ数までの字下げを取り除く',
    L(`  ${FENCE}`, '  a', '    b', ' c', 'd', `  ${FENCE}`),
    pre(L('a', '  b', 'c', 'd')),
  ],
  ['コードブロック：引用の中の囲みは、引用の中の pre', L(`> ${FENCE}`, '> <b>', `> ${FENCE}`), bq(pre(escapeHtml('<b>')))],
]);

// ---- AC-26：行の中 ----

cases('D0025-AC-26', [
  ['行の中：`コード` は code', 'a `b` c', P('a <code>b</code> c')],
  ['行の中：**太字** は strong', '**b**', P('<strong>b</strong>')],
  ['行の中：*斜体* は em', '*i*', P('<em>i</em>')],
  ['行の中：_斜体_ は em', '_i_', P('<em>i</em>')],
  ['行の中：文の途中の太字と斜体', 'x **b** y *i* z', P('x <strong>b</strong> y <em>i</em> z')],
  ['行の中：太字の中の斜体', '**a *b* c**', P('<strong>a <em>b</em> c</strong>')],
  ['行の中：コードの中は変換しない', '`**b** *i* _u_ [a](b)`', P('<code>**b** *i* _u_ [a](b)</code>')],
  ['行の中：コードの中の < は escapeHtml を通る', '`<b>`', P(`<code>${escapeHtml('<b>')}</code>`)],
  ['行の中：同じ長さの ` の並びで閉じる（`` で囲むと中に ` を含められる。AC に無い境目）', '``a`b``', P('<code>a`b</code>')],
  ['閉じていない印：** はそのまま文字', '**a', P('**a')],
  ['閉じていない印：* はそのまま文字', '*a', P('*a')],
  ['閉じていない印：_ はそのまま文字', '_a', P('_a')],
  ['閉じていない印：` はそのまま文字', '`a', P('`a')],
  ['閉じていない印のあとに閉じた印があっても、閉じた印だけが効く', '**a `b`', P('**a <code>b</code>')],
  ['斜体にしない：単語の中の _ （snake_case_name）', 'snake_case_name', P('snake_case_name')],
  ['斜体にしない：単語の中の _ が複数ある文', 'my_var_name and other_thing_here', P('my_var_name and other_thing_here')],
  ['斜体になる：単語の両端の _ は印', 'a _b_ c', P('a <em>b</em> c')],
  ['斜体になる：かっこの内側の _ は印（両隣が英数字ではない）', '(_b_)', P('(<em>b</em>)')],
  ['斜体にしない：空白にはさまれた * は印にしない', 'a * b * c', P('a * b * c')],
  ['斜体にしない：終わりの印の前が空白なら閉じない', 'x *a * y', P('x *a * y')],
]);

// ---- AC-27：引用 ----

cases('D0025-AC-27', [
  ['引用：> の行は blockquote', '> a', bq(P('a'))],
  ['引用：続く行は 1 つの引用の 1 つの段落', L('> a', '> b'), bq(P('a b'))],
  ['引用：> だけの行で、引用の中の段落が分かれる', L('> a', '>', '> b'), bq(P('a') + P('b'))],
  ['引用：中身を読み直す（見出し）', '> # h', bq(h(1, 'h'))],
  ['引用：中身を読み直す（箇条書き）', L('> - a', '> - b'), bq(ul('a', 'b'))],
  ['引用：中身を読み直す（番号つき箇条書きの start）', '> 2. a', bq(olFrom(2, 'a'))],
  ['引用：中身を読み直す（表）', L('> | a |', '> |---|', '> | 1 |'), bq(table(['a'], [['1']]))],
  ['引用：中身を読み直す（コードブロック）', L(`> ${FENCE}`, '> x', `> ${FENCE}`), bq(pre('x'))],
  ['引用：中身を読み直す（---）', '> ---', bq(HR)],
  ['引用：2 段の入れ子', '> > a', bq(bq(P('a')))],
  ['引用：3 段の入れ子', '> > > a', bq(bq(bq(P('a'))))],
  ['引用：4 段目の > は取り除いて 3 段目に並べる', '> > > > a', bq(bq(bq(P('a'))))],
  ['引用：6 段の > でも、4 段目以降を取り除いて 3 段に並べる', '> > > > > > a', bq(bq(bq(P('a'))))],
  ['引用：引用の中の引用の行は、段落を終わらせて入れ子になる', L('> a', '> > b'), bq(P('a') + bq(P('b')))],
  ['引用：> の無い行で引用が終わる（> で始まる続く行だけが 1 つの引用。AC に無い境目）', L('> a', 'b'), bq(P('a')) + P('b')],
  ['引用：空行をはさむと別の引用', L('> a', '', '> b'), bq(P('a')) + bq(P('b'))],
]);

// ---- AC-28：区切り線 ----

cases('D0025-AC-28', [
  ['区切り線：--- は hr', '---', HR],
  ['区切り線：*** は hr（強調・箇条書きより先）', '***', HR],
  ['区切り線：___ は hr（太字より先）', '___', HR],
  ['区切り線：3 つより多くてもよい（-----）', '-----', HR],
  ['区切り線：*****', '*****', HR],
  ['区切り線：__________', '__________', HR],
  ['区切り線：行末の空白は可', '---   ', HR],
  ['区切り線：字下げ 3 つまでは hr（AC に無い境目）', '   ---', HR],
  ['区切り線：字下げ 4 つ以上は段落の文字（AC に無い境目）', '    ---', P('---')],
  ['区切り線：段落の直後の --- も hr（下線の見出しにしない）', L('a', '---'), P('a') + HR],
  ['区切り線：前後の段落が分かれる', L('a', '***', 'b'), P('a') + HR + P('b')],
  ['区切り線：hr のあとの文は段落', L('---', 'a'), HR + P('a')],
  ['区切り線：箇条書きの印より先に読む（--- は項目にならない）', L('- a', '---'), ul('a') + HR],
  ['区切り線：表の区切り行より先に読む（| の無い --- は表の区切りにならない）', L('a | b', '---', '1 | 2'), P('a | b') + HR + P('1 | 2')],
  ['区切り線にならない：-- （2 つ）は段落の文字', '--', P('--')],
  ['区切り線にならない：** （2 つ）は段落の文字', '**', P('**')],
]);

test('D0025-AC-28: 同じ記号でない行（-*-）は hr にならない', async () => {
  const out = await render('-*-');
  assert.doesNotMatch(out, /<hr/, out);
});

// ---- AC-29：ほかの書き方は変換せず、そのまま文字として出す ----

/** [名前, 入力, 段落に見える文字（escapeHtml を通す前）] */
const AS_TEXT: readonly (readonly [label: string, source: string, shown: string])[] = [
  ['脚注の定義', '[^1]: 脚注の文', '[^1]: 脚注の文'],
  ['脚注の参照', '本文[^1]です', '本文[^1]です'],
  ['定義リスト', L('用語', ': 定義'), '用語 : 定義'],
  ['数式（行の中）', '$E = mc^2$', '$E = mc^2$'],
  ['数式（ブロック）', L('$$', 'a + b', '$$'), '$$ a + b $$'],
  ['Markdown の中の HTML（div）', '<div>x</div>', '<div>x</div>'],
  ['Markdown の中の HTML（複数行）', L('<div>', '<b>x</b>', '</div>'), '<div> <b>x</b> </div>'],
  ['Markdown の中の HTML（br）', 'a<br>b', 'a<br>b'],
  ['参照形式のリンク', '[a][b]', '[a][b]'],
  ['参照形式の定義', '[b]: https://example.com/x', '[b]: https://example.com/x'],
  ['<https://…> の自動リンク', '<https://example.com/x>', '<https://example.com/x>'],
  ['裸の URL', 'https://example.com/x', 'https://example.com/x'],
  ['バックスラッシュの打ち消し \\*a\\*（\\ も * も文字のまま）', '\\*a\\*', '\\*a\\*'],
  ['バックスラッシュの打ち消し \\_a\\_（\\ も _ も文字のまま）', '\\_a\\_', '\\_a\\_'],
  ['バックスラッシュの打ち消し \\# 題（見出しにならない）', '\\# 題', '\\# 題'],
  ['取り消し線 ~~a~~', '~~a~~', '~~a~~'],
];

for (const [label, source, shown] of AS_TEXT) {
  test(`D0025-AC-29: ${label} は変換せず、そのまま文字として出す`, async () => {
    assert.equal(await render(source), P(escapeHtml(shown)), `入力：${JSON.stringify(source)}`);
  });
}

cases('D0025-AC-29', [
  ['タスクリストの印 [ ] は変換せず、項目の文字として出す', '- [ ] 未了', ul('[ ] 未了')],
  ['タスクリストの印 [x] も変換せず、項目の文字として出す', '- [x] 済み', ul('[x] 済み')],
  ['コードの中の \\ で終わる `C:\\dir\\` は 1 つの code（\\ は打ち消しにならない）', '`C:\\dir\\`', P('<code>C:\\dir\\</code>')],
  ['\\* で打ち消した * の隣のコードは code のまま', '\\*a `b`', P('\\*a <code>b</code>')],
]);

// ---- AC-34：リンクと画像 ----

const LINK_ROWS: readonly Row[] = [
  ['リンク：[文字](先) は「文字（先）」の文字になる', '[docs](https://example.com/x)', P('docs（https://example.com/x）')],
  ['リンク：文の途中のリンク', 'see [docs](x) now', P('see docs（x） now')],
  ['リンク：先の & も escapeHtml を通る', '[a](b?c=1&d=2)', P(`a（${escapeHtml('b?c=1&d=2')}）`)],
  ['リンク：文字の中の印は変換しない（AC に無い境目）', '[**a**](x)', P('**a**（x）')],
  ['リンク：文字の < も escapeHtml を通る', '[<b>](x)', P(`${escapeHtml('<b>')}（x）`)],
  ['画像：![代わり](先) は「[画像：代わり]」の文字になる', '![alt](x.png)', P('[画像：alt]')],
  ['画像：リンクと画像が並ぶ', '![a](x) [b](y)', P('[画像：a] b（y）')],
  ['画像：代わりの文字の < も escapeHtml を通る', '![<i>](x)', P(`[画像：${escapeHtml('<i>')}]`)],
  ['リンクにならない：[a]() は書いたとおりの文字（先が空）', '[a]()', P('[a]()')],
  ['リンクにならない：[a](b c) は書いたとおりの文字（先に空白）', '[a](b c)', P('[a](b c)')],
  ['リンクにならない：[a](b(c)) は書いたとおりの文字（先に丸括弧）', '[a](b(c))', P('[a](b(c))')],
  ['リンクにならない：[a](b は書いたとおりの文字（閉じが無い）', '[a](b', P('[a](b')],
  ['画像にならない：![a]() は書いたとおりの文字（先が空）', '![a]()', P('![a]()')],
  ['画像にならない：![a](b c) は書いたとおりの文字（先に空白）', '![a](b c)', P('![a](b c)')],
];

cases('D0025-AC-34', LINK_ROWS);

test('D0025-AC-34: リンクも画像も、a と img の要素を作らない（クリックできず、読み込みもしない）', async () => {
  for (const [label, source] of LINK_ROWS) {
    const out = await render(source);
    assert.doesNotMatch(out, /<\s*(?:a|img)\b/i, `${label}：${out}`);
    assert.doesNotMatch(out, /\b(?:href|src)\s*=/i, `${label}：${out}`);
  }
});

// ---- AC に無い境目：AC に書いていないところを埋める決まり ----

cases('D0025-AC-18', [
  ['AC に無い境目：先頭の U+FEFF（BOM）を取る（見出し）', '\uFEFF# 題', h(1, '題')],
  ['AC に無い境目：見出しは字下げ 3 つまで許す', '   # 題', h(1, '題')],
  ['AC に無い境目：字下げが 4 つ以上の見出しは段落の文字（字下げは取る）', '    # 題', P('# 題')],
]);

cases('D0025-AC-19', [
  ['AC に無い境目：先頭の U+FEFF（BOM）を取る（段落）', '\uFEFFa', P('a')],
  ['AC に無い境目：字下げが 4 つ以上の、ほかのブロックに当たらない行は段落の文字（字下げは取る）', '     text', P('text')],
]);

cases('D0025-AC-27', [
  ['AC に無い境目：引用は字下げ 3 つまで許す', '   > q', bq(P('q'))],
  ['AC に無い境目：字下げが 4 つ以上の > は段落の文字', '    > q', P(escapeHtml('> q'))],
]);

cases('D0025-AC-22', [
  ['AC に無い境目：表の頭は字下げ 3 つまで許す', L('   | a |', '|---|', '| 1 |'), table(['a'], [['1']])],
  ['AC に無い境目：字下げが 4 つ以上の表の頭は表にならず、段落の文字（字下げは取る）', L('    | a |', '|---|', '| 1 |'), P('| a | |---| | 1 |')],
]);

cases('D0025-AC-26', [
  ['AC に無い境目：*** は強調にならず、3 つ以上の * の並びは文字', '***a***', P('***a***')],
  ['AC に無い境目：__ は印にならず文字', '__a__', P('__a__')],
  ['AC に無い境目：日本語の隣の _ は斜体にしない（両隣が文字）', '日本_語_です', P('日本_語_です')],
]);

// ---- AC-68：表は div.md-table で包まれる（包みが無いと .md-table の横スクロールの規則が当たらない） ----

test('D0025-AC-68: 表は div.md-table で包まれる（table が直接 pre や p と並ばない）', async () => {
  const out = await render(L('| a |', '|---|', '| 1 |'));
  assert.ok(out.startsWith('<div class="md-table"><table>'), out);
  assert.ok(out.endsWith('</table></div>'), out);
});

test('D0025-AC-68: 表が 2 つあれば包みも 2 つで、コードブロック（pre）は包まない', async () => {
  const out = await render(L('| a |', '|---|', '| 1 |', '', '| b |', '|---|', '| 2 |', '', FENCE, 'x', FENCE));
  assert.equal((out.match(/class="md-table"/g) ?? []).length, 2, out);
  assert.equal((out.match(/<table>/g) ?? []).length, 2, out);
  assert.match(out, /<pre><code>x<\/code><\/pre>$/, out);
});

// ---- AC-30：同じ入力から同じ出力。時計・乱数・ファイルに触れない ----

const SAMPLE_DOC = L(
  '# 題',
  '',
  '段落 **太字** と *斜体* と `コード` と [リンク](x) と ![図](y)。',
  '',
  '- a',
  '  - b',
  '    - c',
  '- d',
  '',
  '3. 三',
  '4. 四',
  '',
  '| 列1 | 列2 |',
  '|:--|--:|',
  '| a | b |',
  '',
  '> 引用',
  '> > 入れ子',
  '',
  FENCE,
  'code <b>',
  FENCE,
  '',
  '---',
);

test('D0025-AC-30: 同じ入力を 2 回変換すると同じ出力（見本の文書）', async () => {
  const { renderMarkdown } = await md();
  const first = renderMarkdown(SAMPLE_DOC);
  assert.ok(first.length > 100, '出力が空でない（見本の検査が空振りしない）');
  assert.equal(renderMarkdown(SAMPLE_DOC), first);
  assert.equal(renderMarkdown(SAMPLE_DOC), first);
});

test('D0025-AC-30: 前の呼びの影響を受けない：別の入力（大きな表を含む）を変換したあとでも、同じ入力は同じ出力', async () => {
  const { renderMarkdown } = await md();
  const first = renderMarkdown(SAMPLE_DOC);
  const head = `|${' c |'.repeat(100)}`;
  const sep = `|${'---|'.repeat(100)}`;
  const body = Array.from({ length: 400 }, () => `|${' x |'.repeat(100)}`).join('\n');
  renderMarkdown(L(head, sep, body));
  renderMarkdown('# 別の入力\n\n**x**');
  renderMarkdown('');
  assert.equal(renderMarkdown(SAMPLE_DOC), first);
});

test('D0025-AC-30: \\r\\n 区切りの入力も、\\n 区切りと同じ出力（改行の種類で出力が変わらない）', async () => {
  const { renderMarkdown } = await md();
  assert.equal(renderMarkdown(SAMPLE_DOC.replace(/\n/g, '\r\n')), renderMarkdown(SAMPLE_DOC));
});

test('D0025-AC-30: markdownHtml.ts に Date・Math.random・performance.now・node: の読み込みが無い（ソースの文字。探す関数は test/sourceText.test.ts で確かめ済み）', () => {
  const source = readFileSync(path.join(HERE, 'markdownHtml.ts'), 'utf8');
  assert.match(source, /export function renderMarkdown\b/, 'renderMarkdown が書かれたファイルを読んでいる');
  assert.deepEqual(findClockOrNode(source), []);
});
