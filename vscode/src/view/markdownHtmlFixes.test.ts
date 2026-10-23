// Markdown 変換 renderMarkdown（D0025）：実装の段で読み手の指摘を受けて直した 3 つの動きのテスト（決定の記録 D0025 の「聞かずに決めたこと」）。
//   表の HTML の長さの予算（AC-36）：表の出力の長さが、小さな入力でも入力の 20 倍以内（表の HTML の長さの予算）。
//   省略の一文のあとの表（AC-24）：表の省略の一文を出したあとの別の表は、丸ごと出ない（頭の行だけを出して本文を黙って落とさない）。
//   段落の途中の番号（AC-20）：段落の途中の行が「2025. 」のように 1 でない番号で始まっても、項目にせず段落の続き（「1. 」・「- 」は段落に割り込める）。
// どれも、直した今の作りで通る（緑）。直しを外すと落ちるように、入力と期待を決めた：
//   表の予算は、セルの数の上限（20,000）が先に効かない小さな入力、省略の一文のあとの表は、一文のあとでもセルの数に空きが残る小さな表、
//   段落の途中の番号は、段落の途中に来る 2 以上の番号。
// 既存のテスト（markdownHtml.test.ts・markdownHtmlSafety.test.ts）は書き換えず、足すだけ。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { escapeHtml } from './escape.ts';
import { MARKDOWN_LIMITS, TABLE_CUT_NOTE, renderMarkdown } from './markdownHtml.ts';

const L = (...lines: string[]): string => lines.join('\n');
const P = (html: string): string => `<p>${html}</p>`;
const li = (inner: string): string => `<li>${inner}</li>`;
const ul = (...items: string[]): string => `<ul>${items.map((i) => li(i)).join('')}</ul>`;
const ol = (...items: string[]): string => `<ol>${items.map((i) => li(i)).join('')}</ol>`;
const olFrom = (start: number, ...items: string[]): string => `<ol start="${start}">${items.map((i) => li(i)).join('')}</ol>`;

/** タグのあいだの改行・<hr /> の書き方・コードの終わりの改行をそろえる（markdownHtml.test.ts の norm と同じ） */
function norm(html: string): string {
  return html
    .trim()
    .replace(/\s*\n\s*(?=<)/g, '')
    .replace(/(?<=>)\s*\n\s*/g, '')
    .replace(/<hr\s*\/?>/g, '<hr>');
}

const count = (html: string, re: RegExp): number => (html.match(re) ?? []).length;
/** 省略の一文が出た数 */
const notes = (html: string): number => html.split(escapeHtml(TABLE_CUT_NOTE)).length - 1;

// ---- 表の HTML の長さの予算（AC-36）：表の出力の長さは、小さな入力でも入力の 20 倍以内 ----
// 右寄せなどの 100 列の表に、`|` だけの本文の行を足すと、1 行ごとに 100 個の空のセルができる。
// 入力は 2 文字の行を足すだけなのに、出力は 1 行で 2,500 文字ほど増える。セルの数の上限（20,000）だけでは、
// 小さい入力のとき 20 倍に収まらない（直す前は、約 1.5 KB の入力が 50 万文字ほどになった）。

const COLS = 100;
/** 空のセル 1 つの最小の長さ（`<td></td>`）。セルの数の上限だけでは出力が 20 倍に収まらないことの確かめに使う */
const MIN_CELL_LENGTH = '<td></td>'.length;

/** 頭の行が 100 列、区切り行が sep の 100 列で、本文が `|` だけの行 bodyRows 本の表（本文の行は、空のセルで 100 列に足される） */
function wideHeadShortBody(sep: string, bodyRows: number): string {
  const head = `|${' h |'.repeat(COLS)}`;
  const sepRow = `|${` ${sep} |`.repeat(COLS)}`;
  return L(head, sepRow, ...Array.from({ length: bodyRows }, () => '|'));
}

// [名前, 区切りのセル, 本文の行の数]。入力はどれも約 1.5 KB。
// 本文の行の数は、出力が 20 倍の枠にどれだけ余るか（余り）を 400 文字以上にする値にした。余りが省略の一文より短くなる境目は、下の NOTE_EDGE で見る
// （予算の直しのあとの余り：右寄せ 1,142・中央 442・左寄せ 2,242・寄せなし 753 文字。直す前は、どれも入力の 120〜360 倍＝20 倍の枠の 6〜18 倍になった）。
const ALIGNS: readonly (readonly [label: string, sep: string, bodyRows: number])[] = [
  ['右寄せ --:', '--:', 250],
  ['中央 :-:', ':-:', 260],
  ['左寄せ :--', ':--', 250],
  ['寄せなし ---', '---', 250],
];

for (const [label, sep, bodyRows] of ALIGNS) {
  test(`D0025-AC-36: 頭の行が 100 列で本文が | だけの行の表（${label}）は、小さい入力でも、出力の長さが入力の 20 倍以内`, () => {
    const input = wideHeadShortBody(sep, bodyRows);
    // 前提：セルの数の上限（20,000 個）まで出しても 20 倍を超える入力（この入力では、セルの数の上限だけでは出力の長さを抑えられない）
    assert.ok(
      MARKDOWN_LIMITS.tableCells * MIN_CELL_LENGTH > 20 * input.length,
      `前提：セルの上限いっぱい（${MARKDOWN_LIMITS.tableCells * MIN_CELL_LENGTH} 文字以上）は入力 ${input.length} 文字の 20 倍を超える`,
    );
    assert.ok(bodyRows * COLS > MARKDOWN_LIMITS.tableCells, '前提：本文のセルの数は、セルの数の上限を超える');
    const out = renderMarkdown(input);
    assert.ok(out.length <= 20 * input.length, `出力 ${out.length} 文字は、入力 ${input.length} 文字の 20 倍（${20 * input.length}）以内のはず`);
  });
}

// 省略の一文（<p>…</p>）も予算に入る：予算いっぱいまで行を出したあとの余りが一文より短い入力でも、一文を足した出力が 20 倍を超えない。
// 本文の行の数は、一文を予算の外に出していた作りで、出力が 20 倍を超えた値（右寄せ 221 本は 18 文字・中央 248 本は 38 文字・
// 左寄せ 256 本は 27 文字・寄せなし 208 本は 18 文字超えた）。
const NOTE_EDGE: readonly (readonly [label: string, sep: string, bodyRows: number])[] = [
  ['右寄せ --:', '--:', 221],
  ['中央 :-:', ':-:', 248],
  ['左寄せ :--', ':--', 256],
  ['寄せなし ---', '---', 208],
];

for (const [label, sep, bodyRows] of NOTE_EDGE) {
  test(`D0025-AC-36: 表を長さの予算で省いたときの省略の一文も予算に入る（${label}・本文 ${bodyRows} 行）：出力は入力の 20 倍以内で、一文は 1 つ出る`, () => {
    const input = wideHeadShortBody(sep, bodyRows);
    const out = renderMarkdown(input);
    assert.equal(notes(out), 1, '省略の一文がちょうど 1 つ');
    assert.ok(out.length <= 20 * input.length, `出力 ${out.length} 文字は、入力 ${input.length} 文字の 20 倍（${20 * input.length}）以内のはず`);
  });
}

test('D0025-AC-36: 本文の行を省いても、頭の行（100 列）は出て、省略の一文が 1 つ出る（本文の行を黙って落とさない。セルの数の上限だけのときも同じなので、今のまま通る。守る）', () => {
  const out = renderMarkdown(wideHeadShortBody('--:', 250));
  assert.equal(count(out, /<table>/g), 1);
  assert.equal(count(out, /<th[\s>]/g), COLS, '頭の行は出る');
  assert.ok(count(out, /<tr>/g) < 250, '本文の行は全部は出ない');
  assert.equal(notes(out), 1, '省略の一文がちょうど 1 つ');
  assert.ok(out.includes(`</table></div><p>${escapeHtml(TABLE_CUT_NOTE)}</p>`), '表のあとに p と一文が出る');
});

test('D0025-AC-36: 長さの予算は次の呼びに持ち越さない：予算で省いた変換のあとでも、小さな表は全部出て、一文は出ない（今のまま通る。守る）', () => {
  renderMarkdown(wideHeadShortBody('--:', 250));
  const out = norm(renderMarkdown(L('| a |', '|---|', '| 1 |')));
  assert.equal(out, '<div class="md-table"><table><thead><tr><th>a</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table></div>');
  assert.equal(notes(out), 0);
});

test('D0025-AC-36: ふつうの大きさの表（4 列・30 行の短い文字）は、長さの予算で省かれず、全部出て、一文は出ない（今のまま通る。守る）', () => {
  const rows = Array.from({ length: 30 }, (_, i) => `| ${i + 1} | 項目${i + 1} | 説明 ${i + 1} | 備考 |`);
  const out = renderMarkdown(L('| 番号 | 名前 | 説明 | 備考 |', '|---|:--|--:|:-:|', ...rows));
  assert.equal(count(out, /<tr>/g), 31, '頭の行と本文の 30 行');
  assert.equal(count(out, /<td[\s>]/g), 120);
  assert.equal(notes(out), 0);
});

// ---- 省略の一文のあとの表（AC-24）：省略の一文を出したあとの別の表は、丸ごと出ない ----
// 3 列の大きい表（セルが 20,000 個を超える）で一文を出したあと、セルの数に空きが残っていると、小さい表の頭の行だけが出て、
// 本文が黙って消えていた（直す前）。直したあとは、省略の一文を出したあとの表は、頭の行も本文も出さない。

/** 3 列・本文 6,700 行の表（セルは 20,100 個。本文の 6,665 行目までで 20,000 個の上限に届き、そこから先を省く） */
const bigTable = (): string => L('|a|b|c|', '|-|-|-|', ...Array.from({ length: 6700 }, () => '|a|b|c|'));

// あとの表は 1 列にする：大きい表のあとのセルの数の空きは 2 個（19,998 個まで出る）なので、1 列なら空きに余裕を残して頭の行が入る
const AFTER_NOTE: readonly (readonly [label: string, table: string])[] = [
  ['頭の行と本文の行がある 1 列の表', L('| ZH1 |', '|---|', '| ZB1 |')],
  ['頭の行だけで本文の行が無い 1 列の表', L('| ZH1 |', '|---|')],
];

for (const [label, table] of AFTER_NOTE) {
  test(`D0025-AC-24: 省略の一文を出したあとの別の表（${label}）は、頭の行も本文も出ず、一文は重ならない`, () => {
    const out = renderMarkdown(L(bigTable(), '', table));
    assert.equal(notes(out), 1, '省略の一文は大きい表のあとの 1 つだけ');
    assert.equal(count(out, /<table>/g), 1, '表は大きい表の 1 つだけ（あとの表は出ない）');
    assert.ok(!out.includes('ZH1'), 'あとの表の頭の行が出ていない');
    assert.ok(!out.includes('ZB1'), 'あとの表の本文が出ていない');
  });
}

test('D0025-AC-24: 省略の一文を出す前の表は全部出て、あとの表を省いても、そのあとの段落・見出しは出る', () => {
  const out = renderMarkdown(
    L('| FH |', '|---|', '| FB |', '', bigTable(), '', '| ZH1 |', '|---|', '| ZB1 |', '', '## あとの見出し', '', 'あとの段落'),
  );
  assert.equal(notes(out), 1);
  assert.equal(count(out, /<table>/g), 2, '前の小さい表と大きい表の 2 つ（あとの表は省く）');
  assert.ok(out.includes('<th>FH</th>') && out.includes('<td>FB</td>'), '前の小さい表は頭の行も本文も出る');
  assert.ok(!out.includes('ZH1') && !out.includes('ZB1'), 'あとの表は出ない');
  assert.ok(out.includes('<h4 class="md-h2">あとの見出し</h4>'), 'あとの見出しは出る');
  assert.ok(out.includes('<p>あとの段落</p>'), 'あとの段落は出る');
});

// ---- 段落の途中の番号（AC-20）：段落の途中の「2025. 」は段落の続き（CommonMark と同じ） ----
// 折り返した行の頭に来た年や番号が、番号つきの項目（ol start="2025"）になって段落が切れていた（直す前）。
// 段落に割り込める項目の印は、箇条書き（- * +）と、番号が 1 の「1.」だけ。

type Row = readonly [label: string, source: string, expected: string];

const CONTINUES: readonly Row[] = [
  [
    '2025. （年）で始まる折り返しの行は段落の続き',
    L('これは 2024 年の話で、', '2025. という番号は年です。'),
    P('これは 2024 年の話で、 2025. という番号は年です。'),
  ],
  ['2. で始まる行は段落の続き', L('a', '2. b'), P('a 2. b')],
  ['10. で始まる行は段落の続き', L('a', '10. b'), P('a 10. b')],
  ['0. で始まる行は段落の続き', L('a', '0. b'), P('a 0. b')],
  ['字下げした 2. も段落の続き（字下げは取る）', L('a', '   2. b'), P('a 2. b')],
  ['そのあとの行も段落の続き', L('a', '2025. b', 'c'), P('a 2025. b c')],
  ['段落の続きになった 2025. のあとの箇条書きは、段落を終わらせる', L('a', '2025. b', '- c'), P('a 2025. b') + ul('c')],
];

for (const [label, source, expected] of CONTINUES) {
  test(`D0025-AC-20: ${label}`, () => {
    const out = norm(renderMarkdown(source));
    assert.equal(out, expected);
    assert.ok(!out.includes('<ol'), '番号つきの一覧（ol）ができていない');
  });
}

const INTERRUPTS: readonly Row[] = [
  ['1. は段落に割り込める（番号つきの一覧が始まる。CommonMark と同じ）', L('a', '1. b'), P('a') + ol('b')],
  ['- は段落に割り込める', L('a', '- b'), P('a') + ul('b')],
  ['* は段落に割り込める', L('a', '* b'), P('a') + ul('b')],
  ['+ は段落に割り込める', L('a', '+ b'), P('a') + ul('b')],
  ['段落に割り込んだ 1. のあとの 2. は、一覧の項目', L('a', '1. b', '2. c'), P('a') + ol('b', 'c')],
];

for (const [label, source, expected] of INTERRUPTS) {
  test(`D0025-AC-20: ${label}（今のまま通る。守る）`, () => {
    assert.equal(norm(renderMarkdown(source)), expected);
  });
}

test('D0025-AC-20: ブロックの最初の行の 2025. は、これまでどおり番号つきの一覧（start="2025"）になる（段落の途中だけが続きになる。今のまま通る。守る）', () => {
  assert.equal(norm(renderMarkdown('2025. a')), olFrom(2025, 'a'));
  assert.equal(norm(renderMarkdown(L('a', '', '2025. b'))), P('a') + olFrom(2025, 'b'));
});
