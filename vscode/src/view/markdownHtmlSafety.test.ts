// Markdown 変換 renderMarkdown の安全（D0025・FR-09）：外から来た文字のすり抜け（AC-31・32）、escapeHtml の形（AC-33）、
// とても長い・極端な入力（AC-36）、表の安全弁（AC-24・AC-36）。書き方の範囲（AC-18〜29・34）は markdownHtml.test.ts が持つ。
// 新しい部品（view/markdownHtml.ts）は、テストの中で読み込む（テスト先行のとき、まだ無いあいだも各テストが「モジュールが無い」で落ち、ファイルごと読めずに落ちることが無いようにしたため）。
//
// 検査そのもの（出力からタグだけを取り出して属性名を調べる関数）は、<img src=x onerror=1> を見つけ、文字の中の ` src=` は見逃すことを、テストで示す
// （testing.md の「検査そのものが違反を見つけられる」）。この確かめは製品の部品に頼らないので、今のまま通る（守る）。
// すり抜けの道は表（payload × 置き場所）にして 1 行ずつ test にする。新しい道に気づいたら、まず 1 行足して赤を見てから直す。
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { escapeHtml } from './escape.ts';
import { callArgs, findOwnEscape, withoutComments } from '../test/sourceText.ts';

/** 使う分だけの型。テスト先行のとき markdownHtml.ts がまだ無くても型検査が通るよう、読み込みの指定を定数でない形にして型を与えた */
interface MarkdownHtmlMod {
  renderMarkdown(source: string): string;
  MARKDOWN_LIMITS: { listDepth: number; quoteDepth: number; tableCols: number; tableCells: number };
  TABLE_CUT_NOTE: string;
}
const md = (): Promise<MarkdownHtmlMod> => import(String('./markdownHtml.ts')) as Promise<MarkdownHtmlMod>;
const HERE = path.dirname(fileURLToPath(import.meta.url));
const FENCE = '`'.repeat(3);
const KEEP_NOTE = '（今のまま通る。守る）';

const L = (...lines: string[]): string => lines.join('\n');

/** 生の出力（正規化しない）。タグと属性の検査に使う */
async function raw(source: string): Promise<string> {
  const { renderMarkdown } = await md();
  return renderMarkdown(source);
}

/** タグのあいだの改行・<hr /> の書き方・コードの終わりの改行をそろえる（形の細かい違いで赤にならないように） */
function norm(html: string): string {
  return html
    .trim()
    .replace(/\s*\n\s*(?=<)/g, '')
    .replace(/(?<=>)\s*\n\s*/g, '')
    .replace(/<hr\s*\/?>/g, '<hr>');
}

async function render(source: string): Promise<string> {
  return norm(await raw(source));
}

// ---- 検査：出力に現れるタグの名前と属性 ----

/** 許可の一覧（AC-31）：AC-18〜28 で作ると決めたものだけ。span・br・a・img は作らない */
const ALLOWED_TAGS: readonly string[] = [
  'h3',
  'h4',
  'h5',
  'h6',
  'p',
  'ul',
  'ol',
  'li',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td',
  'pre',
  'code',
  'blockquote',
  'hr',
  'strong',
  'em',
  'div',
];
const ALLOWED = new Set(ALLOWED_TAGS);

/** 出力に現れるタグの名前（開きも閉じも）。文字の中の < は escapeHtml 済みなので、< が出たらタグのはず */
function tagNames(html: string): string[] {
  return Array.from(html.matchAll(/<\/?([a-z][a-z0-9]*)/gi), (m) => m[1].toLowerCase());
}

/** 許可の一覧にないタグの名前（順に、重ねずに）。< の後ろがタグの名前でないもの（<!-- や <? や、はだかの <）は '<' とする */
function outsideTags(html: string): string[] {
  const out: string[] = [];
  for (const name of tagNames(html)) if (!ALLOWED.has(name) && !out.includes(name)) out.push(name);
  const angles = (html.match(/</g) ?? []).length;
  if (angles !== tagNames(html).length) out.push('<');
  return out;
}

interface Tag {
  name: string;
  attrs: { name: string; value: string }[];
}

/** 出力から「タグだけ」を取り出し（<[a-z][^>]*>）、属性の名前と値を取る。成果物の文字（text ノード）は調べない */
function tagsOf(html: string): Tag[] {
  const out: Tag[] = [];
  for (const m of html.matchAll(/<([a-z][a-z0-9]*)([^>]*)>/gi)) {
    const attrs: Tag['attrs'] = [];
    for (const a of m[2].matchAll(/([^\s=\/"'<>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g)) {
      attrs.push({ name: a[1].toLowerCase(), value: a[2] ?? a[3] ?? a[4] ?? '' });
    }
    out.push({ name: m[1].toLowerCase(), attrs });
  }
  return out;
}

/** class と、ol の整数の start（2〜9999）のほかの属性（'タグ.属性' の並び） */
function outsideAttrs(html: string): string[] {
  const bad: string[] = [];
  for (const tag of tagsOf(html)) {
    for (const attr of tag.attrs) {
      if (attr.name === 'class') continue;
      if (tag.name === 'ol' && attr.name === 'start' && /^[1-9][0-9]{0,3}$/.test(attr.value) && Number(attr.value) >= 2) continue;
      bad.push(`${tag.name}.${attr.name}`);
    }
  }
  return bad;
}

/** class の値のうち、md- で始まる決まった語でないもの（外から来た文字が class にならない） */
function strayClasses(html: string): string[] {
  return tagsOf(html).flatMap((tag) => tag.attrs.filter((a) => a.name === 'class' && !/^md-[a-z0-9]+$/.test(a.value)).map((a) => `${tag.name}.${a.value}`));
}

// ---- 検査そのものの確かめ（今のまま通る。守る） ----

const TAGS_FOUND: readonly (readonly [label: string, html: string, expected: readonly string[]])[] = [
  ['script', '<script>alert(1)</script>', ['script']],
  ['img（閉じタグの無いタグ）', '<img src=x>', ['img']],
  ['a', '<a href="x">t</a>', ['a']],
  ['iframe と style（出る順）', '<iframe></iframe><style></style>', ['iframe', 'style']],
  ['span と br', '<p>a<br>b <span>c</span></p>', ['br', 'span']],
  ['h1 と h2（パネルの見出しと同じ段は作らない）', '<h1>t</h1><h2>u</h2>', ['h1', 'h2']],
  ['大文字の SCRIPT', '<SCRIPT>x</SCRIPT>', ['script']],
  ['HTML のコメント（< の後ろがタグの名前でない）', '<p>a</p><!-- c -->', ['<']],
  ['はだかの <（< の後ろが空白）', '<p>a < b</p>', ['<']],
  ['閉じタグだけ', 'x</script>', ['script']],
];

for (const [label, html, expected] of TAGS_FOUND) {
  test(`D0025-AC-31: 検査そのものが、${label} を許可の一覧にないタグとして見つける${KEEP_NOTE}`, () => {
    assert.deepEqual(outsideTags(html), expected);
  });
}

const TAGS_MISSED: readonly (readonly [label: string, html: string])[] = [
  ['許可の一覧のタグだけ', '<h3 class="md-h1">t</h3><p>a <strong>b</strong> <em>c</em> <code>d</code></p><hr>'],
  ['表の入れ物と表', '<div class="md-table"><table><thead><tr><th>a</th></tr></thead><tbody><tr><td>b</td></tr></tbody></table></div>'],
  ['引用・一覧・コードブロック', '<blockquote><ul><li>a</li></ul><ol start="2"><li>b</li></ol></blockquote><pre><code>c</code></pre>'],
  ['文字の中の &lt;script&gt;（escapeHtml 済み）', '<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>'],
  ['文字の中の &lt;!-- コメント --&gt;', '<p>&lt;!-- c --&gt;</p>'],
  ['空の文字', ''],
];

for (const [label, html] of TAGS_MISSED) {
  test(`D0025-AC-31: 検査そのものが、${label} は見逃す${KEEP_NOTE}`, () => {
    assert.deepEqual(outsideTags(html), []);
  });
}

const ATTRS_FOUND: readonly (readonly [label: string, html: string, expected: readonly string[]])[] = [
  ['img の src と onerror（<img src=x onerror=1>）', '<img src=x onerror=1>', ['img.src', 'img.onerror']],
  ['a の href', '<a href="https://x.example">t</a>', ['a.href']],
  ['p の style', '<p style="color:red">t</p>', ['p.style']],
  ['引用符が一重の onclick', "<p onclick='x()'>t</p>", ['p.onclick']],
  ['値のない属性（hidden）', '<p hidden>t</p>', ['p.hidden']],
  ['大文字の属性名', '<p ONCLICK=1>t</p>', ['p.onclick']],
  ['class と src の両方（class は見逃し、src を見つける）', '<p class="md-x" src="b">t</p>', ['p.src']],
  ['ul の start（ol 以外）', '<ul start="3"><li>x</li></ul>', ['ul.start']],
  ['ol の start が整数でない', '<ol start="x"><li>y</li></ol>', ['ol.start']],
  ['ol の start が 1（付けない決まり）', '<ol start="1"><li>y</li></ol>', ['ol.start']],
  ['ol の start が 10000（付けない決まり）', '<ol start="10000"><li>y</li></ol>', ['ol.start']],
  ['2 つのタグに 1 つずつ', '<img src=x><a href=y>t</a>', ['img.src', 'a.href']],
];

for (const [label, html, expected] of ATTRS_FOUND) {
  test(`D0025-AC-32: 検査そのものが、${label} を見つける${KEEP_NOTE}`, () => {
    assert.deepEqual(outsideAttrs(html), expected);
  });
}

const ATTRS_MISSED: readonly (readonly [label: string, html: string])[] = [
  ['class だけ', '<h3 class="md-h1">t</h3>'],
  ['ol の start="3"', '<ol start="3"><li>x</li></ol>'],
  ['ol の start="9999"', '<ol start="9999"><li>x</li></ol>'],
  ['属性のないタグ', '<p>x</p><hr><ul><li>a</li></ul>'],
  ['文字の中の ` src=` と ` onerror=`（&lt;img src=x onerror=1&gt;。見つけてはいけない）', '<p>&lt;img src=x onerror=alert(1)&gt;</p>'],
  ['文字の中の href=', '<p>go to href=&quot;x&quot; now</p>'],
  ['コードの中の style=', '<pre><code>&lt;p style=&quot;x&quot;&gt;</code></pre>'],
  ['空の文字', ''],
];

for (const [label, html] of ATTRS_MISSED) {
  test(`D0025-AC-32: 検査そのものが、${label} は見逃す${KEEP_NOTE}`, () => {
    assert.deepEqual(outsideAttrs(html), []);
  });
}

test(`D0025-AC-32: class の値の検査そのものが、md- で始まらない値を見つけ、md-h1 などは見逃す${KEEP_NOTE}`, () => {
  assert.deepEqual(strayClasses('<p class="evil">t</p><th class="md-left">a</th>'), ['p.evil']);
  assert.deepEqual(strayClasses('<h3 class="md-h1">t</h3><div class="md-table"></div>'), []);
});

// ---- 入力：すり抜けの道（payload）と、置き場所 ----

/** [名前, 入力]。1 行ずつ（NUL を除いて改行を含まない） */
const PAYLOADS: readonly (readonly [label: string, text: string])[] = [
  ['<script>', '<script>alert(1)</script>'],
  ['<img src=x onerror=…>', '<img src=x onerror=alert(1)>'],
  ['<iframe>', '<iframe src="https://evil.example/x"></iframe>'],
  ['<style>', '<style>body{display:none}</style>'],
  ['<a href=…>', '<a href="https://evil.example/x">go</a>'],
  ['HTML のコメント', '<!-- comment -->'],
  ['[x](javascript:…)（丸括弧なし。リンクになる形）', '[x](javascript:alert1)'],
  ['[x](javascript:…)（丸括弧つき）', '[x](javascript:alert(1))'],
  ['[x](command:…)', '[x](command:workbench.action.openSettings)'],
  ['![x](data:…)', '![x](data:text/html;base64,PHNjcmlwdD4=)'],
  ['![x](https://…)', '![x](https://evil.example/a.png)'],
  ['<https://…>', '<https://evil.example/x>'],
  ['裸の URL', 'https://evil.example/x'],
  ['参照形式のリンク', '[x][ref]'],
  ['&lt;script&gt;（文字の書き方）', '&lt;script&gt;alert(1)&lt;/script&gt;'],
  ['"（属性を抜ける形）', '" onmouseover="alert(1)'],
  ["'（属性を抜ける形）", "' onfocus='alert(1)"],
  ['NUL 文字', '\u0000<script>alert(1)</script>'],
  ['</p> で抜ける', '</p><script>alert(1)</script>'],
  ['</code></pre> で抜ける', '</code></pre><script>alert(1)</script>'],
  ['表を閉じて抜ける', '</td></tr></tbody></table></div><script>alert(1)</script>'],
  ['<svg onload=…>', '<svg/onload=alert(1)>'],
];

/** [置き場所, 入力を置いた Markdown] */
const PLACES: readonly (readonly [label: string, put: (text: string) => string])[] = [
  ['見出し', (t) => `# ${t}`],
  ['箇条書き', (t) => `- ${t}`],
  ['番号つき箇条書き', (t) => `1. ${t}`],
  ['表のヘッダ', (t) => L(`| ${t} |`, '|---|', '| v |')],
  ['表のセル', (t) => L('| h |', '|---|', `| ${t} |`)],
  ['引用', (t) => `> ${t}`],
  ['太字', (t) => `**${t}**`],
  ['コード（行の中）', (t) => `\`${t}\``],
  ['コードブロック', (t) => L(FENCE, t, FENCE)],
  ['リンクの文字', (t) => `[${t}](x)`],
  ['リンクの先', (t) => `[x](${t})`],
  ['段落', (t) => t],
];

for (const [place, put] of PLACES) {
  for (const [label, text] of PAYLOADS) {
    test(`D0025-AC-31: ${place}に ${label} を入れても、出力のタグの名前は許可の一覧だけ`, async () => {
      const out = await raw(put(text));
      assert.ok(tagNames(out).length > 0, `何かのタグが出ている（検査が空振りしない）：${out}`);
      assert.deepEqual(outsideTags(out), [], out);
    });
  }
}

for (const [place, put] of PLACES) {
  for (const [label, text] of PAYLOADS) {
    test(`D0025-AC-32: ${place}に ${label} を入れても、出力のどのタグも属性の名前は class だけ（ol の整数の start を除く）`, async () => {
      const out = await raw(put(text));
      assert.ok(tagsOf(out).length > 0, `何かのタグが出ている（検査が空振りしない）：${out}`);
      assert.deepEqual(outsideAttrs(out), [], out);
    });
  }
}

test('D0025-AC-32: すり抜けの入力をすべて 1 つの文書にしても、class の値は md- で始まる決まった語だけ（外から来た文字が class にならない）', async () => {
  const out = await raw(PLACES.flatMap(([, put]) => PAYLOADS.map(([, text]) => put(text))).join('\n\n'));
  assert.ok(tagsOf(out).length > 100, '多くのタグが出ている');
  assert.deepEqual(strayClasses(out), [], out);
  assert.deepEqual(outsideTags(out), [], out);
  assert.deepEqual(outsideAttrs(out), [], out);
});

const SINK = L(
  '# a',
  '## b',
  '### c',
  '#### d',
  '',
  '段落 **s** *e* `c`',
  '',
  '- x',
  '1. y',
  '',
  '| h |',
  '|---|',
  '| v |',
  '',
  FENCE,
  'p',
  FENCE,
  '',
  '> q',
  '',
  '---',
);

test('D0025-AC-31: 許可の一覧は、AC-18〜28 で作ると決めたタグと同じ（見本の文書で 21 個すべてが出て、ほかは出ない）', async () => {
  const out = await raw(SINK);
  assert.deepEqual([...new Set(tagNames(out))].sort(), [...ALLOWED_TAGS].sort(), out);
});

test('D0025-AC-31: span と br は作らない（行末の空白 2 つ・リンク・画像を含む文書でも）', async () => {
  const out = await raw(L('行末の空白 2 つ  ', '次の行', '', '[リンク](x) と ![図](y)', '', '- [ ] 項目  ', '  続き'));
  const names = new Set(tagNames(out));
  for (const banned of ['br', 'span', 'a', 'img']) assert.ok(!names.has(banned), `${banned} が出ている：${out}`);
  assert.deepEqual(outsideTags(out), [], out);
});

test('D0025-AC-32: 見本の文書のどのタグも、属性の名前は class だけ（ol の start を除く）で、class の値は md- で始まる決まった語', async () => {
  const out = await raw(L(SINK, '', '3. 三', '4. 四', '', '| a | b |', '|:--|--:|', '| 1 | 2 |'));
  assert.ok(/<ol start="3">/.test(out), 'ol の start が付く見本を含む');
  assert.deepEqual(outsideAttrs(out), [], out);
  assert.deepEqual(strayClasses(out), [], out);
});

// ---- AC-33：エスケープの形 ----

const S = `a<b>c&d"e'f`;
const E = escapeHtml(S);

test(`D0025-AC-33: 検査の足場：escapeHtml は & < > " ' を名前の文字参照にする（このテストは escapeHtml と突き合わせる）${KEEP_NOTE}`, () => {
  assert.equal(escapeHtml(`&<>"'`), '&amp;&lt;&gt;&quot;&apos;');
  assert.notEqual(E, S);
});

const tableHtml = (th: string, td: string): string =>
  `<div class="md-table"><table><thead><tr><th>${th}</th></tr></thead><tbody><tr><td>${td}</td></tr></tbody></table></div>`;

/** [置き場所, テキストを置いた Markdown, 文字（escapeHtml 済み）から出力を作る] */
const CONTEXTS: readonly (readonly [label: string, input: (text: string) => string, expected: (html: string) => string])[] = [
  ['段落', (t) => t, (e) => `<p>${e}</p>`],
  ['見出し', (t) => `# ${t}`, (e) => `<h3 class="md-h1">${e}</h3>`],
  ['箇条書き', (t) => `- ${t}`, (e) => `<ul><li>${e}</li></ul>`],
  ['番号つき箇条書き', (t) => `1. ${t}`, (e) => `<ol><li>${e}</li></ol>`],
  ['表のセル', (t) => L('| h |', '|---|', `| ${t} |`), (e) => tableHtml('h', e)],
  ['表のヘッダ', (t) => L(`| ${t} |`, '|---|', '| v |'), (e) => tableHtml(e, 'v')],
  ['引用', (t) => `> ${t}`, (e) => `<blockquote><p>${e}</p></blockquote>`],
  ['太字', (t) => `**${t}**`, (e) => `<p><strong>${e}</strong></p>`],
  ['斜体', (t) => `*${t}*`, (e) => `<p><em>${e}</em></p>`],
  ['コード（行の中）', (t) => `\`${t}\``, (e) => `<p><code>${e}</code></p>`],
  ['コードブロック', (t) => L(FENCE, t, FENCE), (e) => `<pre><code>${e}</code></pre>`],
  ['リンクの文字', (t) => `[${t}](x)`, (e) => `<p>${e}（x）</p>`],
  ['リンクの先', (t) => `[x](${t})`, (e) => `<p>x（${e}）</p>`],
  ['画像の代わりの文字', (t) => `![${t}](x)`, (e) => `<p>[画像：${e}]</p>`],
];

for (const [label, input, expected] of CONTEXTS) {
  test(`D0025-AC-33: ${label}の < > & " ' は escapeHtml(入力) の出力そのままで出る`, async () => {
    assert.equal(await render(input(S)), expected(E));
  });
}

test('D0025-AC-33: < > & " \' を 1 文字ずつ段落に入れても、escapeHtml(入力) の出力そのまま', async () => {
  for (const c of ['<', '>', '&', '"', "'"]) {
    const text = `a${c}b`;
    assert.equal(await render(text), `<p>${escapeHtml(text)}</p>`, c);
  }
});

test('D0025-AC-33: 二重にエスケープしない：a < b は a &lt; b で、&amp;lt; にならない', async () => {
  const out = await render('a < b');
  assert.equal(out, `<p>${escapeHtml('a < b')}</p>`);
  assert.doesNotMatch(out, /&amp;lt;/);
});

test('D0025-AC-33: &lt;script&gt; と書かれた入力は、書かれたとおりの文字として見える（出力は &amp;lt;script&amp;gt;）', async () => {
  const input = '&lt;script&gt;';
  const out = await render(input);
  assert.equal(out, `<p>${escapeHtml(input)}</p>`);
  assert.equal(out, '<p>&amp;lt;script&amp;gt;</p>');
});

const ENTITY_INPUTS = ['&lt;', '&gt;', '&amp;', '&quot;', '&apos;', '&#39;', '&#x3C;', '&nbsp;', '&copy;'];

for (const entity of ENTITY_INPUTS) {
  test(`D0025-AC-33: 文字参照 ${entity} と書かれた入力は、& だけが &amp; になり、解釈されずに見える`, async () => {
    assert.equal(await render(`x ${entity} y`), `<p>${escapeHtml(`x ${entity} y`)}</p>`);
  });
}

test('D0025-AC-33: コードの中でも二重にエスケープしない（&lt; と書かれたコードは &amp;lt;）', async () => {
  assert.equal(await render('`&lt;`'), `<p><code>${escapeHtml('&lt;')}</code></p>`);
  assert.equal(await render(L(FENCE, '&lt; <b>', FENCE)), `<pre><code>${escapeHtml('&lt; <b>')}</code></pre>`);
});

const NUL_TEXT = 'a\u0000b';
const NUL_SHOWN = 'a�b';

for (const [label, input, expected] of CONTEXTS) {
  test(`D0025-AC-33: ${label}の NUL 文字（U+0000）は U+FFFD にして出す`, async () => {
    const out = await render(input(NUL_TEXT));
    assert.equal(out, expected(escapeHtml(NUL_SHOWN)));
    assert.ok(!out.includes('\u0000'), 'NUL が出力に残っていない');
  });
}

test('D0025-AC-33: NUL 文字を並べた長い入力でも、出力に NUL は残らない', async () => {
  const out = await raw(`${'\u0000'.repeat(1000)}\n\n# ${'\u0000'.repeat(1000)}`);
  assert.ok(!out.includes('\u0000'));
  assert.ok(out.includes('�'));
});

test('D0025-AC-33: markdownHtml.ts は escapeHtml を ./escape.ts から読み込んで呼び、自前のエスケープ（&amp; &lt; &gt; &quot; &#39; &apos; の作成）を持たない（ソースの文字。探す関数は test/sourceText.test.ts で確かめ済み）', () => {
  const source = readFileSync(path.join(HERE, 'markdownHtml.ts'), 'utf8');
  assert.match(source, /import\s*\{[^}]*\bescapeHtml\b[^}]*\}\s*from\s*['"]\.\/escape\.ts['"]/, 'escapeHtml を ./escape.ts から読み込む');
  assert.ok(callArgs(withoutComments(source), 'escapeHtml').length > 0, 'escapeHtml を呼ぶ');
  assert.deepEqual(findOwnEscape(source), []);
});

// ---- AC-36：とても長い・極端な入力 ----

const LIMIT_MS = 5000;
const BASE = 200_000;
const ONE_LINE = 100_000;

type Gen = (n: number) => string;
/** unit を繰り返して、n 文字ほどにする */
const rep =
  (unit: string): Gen =>
  (n) =>
    unit.repeat(Math.ceil(n / unit.length));
/** 全体で n 文字ほどになる行数（行ごとに深くなる入力は、文字数が行数の 2 乗で増える） */
const lines = (n: number): number => Math.floor(Math.sqrt(n));
const deepLines =
  (line: (i: number) => string): Gen =>
  (n) =>
    Array.from({ length: lines(n) }, (_, i) => line(i)).join('\n');

/** [名前, 入力を作る関数（総文字数のめやす n を受ける）, 1 回目の n] */
const EXTREME: readonly (readonly [label: string, gen: Gen, n: number])[] = [
  // AC-36 の記号 9 種を 20 万個
  ['* を 20 万個並べた入力', rep('*'), BASE],
  ['_ を 20 万個並べた入力', rep('_'), BASE],
  ['[ を 20 万個並べた入力', rep('['), BASE],
  ['( を 20 万個並べた入力', rep('('), BASE],
  ['| を 20 万個並べた入力', rep('|'), BASE],
  ['` を 20 万個並べた入力', rep('`'), BASE],
  ['> を 20 万個並べた入力', rep('>'), BASE],
  ['- を 20 万個並べた入力', rep('-'), BASE],
  ['空白を 20 万個並べた入力', rep(' '), BASE],
  // escapeHtml でふくらむ文字
  ['& を 20 万個並べた入力（&amp; で 5 倍）', rep('&'), BASE],
  ['< を 20 万個並べた入力（&lt; で 4 倍）', rep('<'), BASE],
  ['" を 20 万個並べた入力（&quot; で 6 倍）', rep('"'), BASE],
  ["' を 20 万個並べた入力（&apos; で 6 倍）", rep("'"), BASE],
  // 閉じない印・後戻りしやすい並び
  ['閉じない強調（*a を繰り返す）', rep('*a '), BASE],
  ['閉じない太字（**a を繰り返す）', rep('**a '), BASE],
  ['閉じない斜体（_a を繰り返す）', rep('_a '), BASE],
  ['*_ を交互に並べた入力', rep('*_'), BASE],
  ['[* を交互に並べた入力', rep('[*'), BASE],
  ['([ を交互に並べた入力', rep('(['), BASE],
  ['閉じないリンク（[a]( を繰り返す）', rep('[a]('), BASE],
  ['閉じない画像（![a]( を繰り返す）', rep('![a]('), BASE],
  ['閉じないリンクの先（[a](b を繰り返す）', rep('[a](b '), BASE],
  ['閉じたリンクの連なり（[a](b) を繰り返す）', rep('[a](b)'), BASE],
  ['閉じた画像の連なり（![a](b) を繰り返す）', rep('![a](b)'), BASE],
  ['閉じないコード（`a を繰り返す）', rep('`a '), BASE],
  ['閉じたコードの連なり（`a` を繰り返す）', rep('`a` '), BASE],
  ['バックスラッシュと * の並び', rep('\\*'), BASE],
  ['| と文字を繰り返した 1 行', rep('| a '), BASE],
  // 行ごとのブロックの開始
  ['行頭の > を 1 行に 1 つ', rep('> a\n'), BASE],
  ['行頭の - を 1 行に 1 つ', rep('- a\n'), BASE],
  ['行頭の 1. を 1 行に 1 つ', rep('1. a\n'), BASE],
  ['1 文字の段落を空行で区切って並べた入力', rep('a\n\n'), BASE],
  ['コードブロックの囲みを開いて閉じるのを繰り返した入力', rep(`${FENCE}\n`), BASE],
  ['コードブロックの中に < を並べた入力', (n) => L(FENCE, '<'.repeat(n)), BASE],
  ['表の本文（x|y）の行を並べた入力', (n) => L('a|b', '-|-', rep('x|y\n')(n)), BASE],
  ['表の本文が | だけの行を並べた入力（空のセルの足しでふくらむ）', (n) => L('a|b|c|d|e', '-|-|-|-|-', rep('|\n')(n)), BASE],
  // 10 万文字の 1 行
  ['10 万文字の 1 行（平文）', (n) => 'a'.repeat(n), ONE_LINE],
  ['10 万文字の 1 行（単語と空白）', rep('word '), ONE_LINE],
  ['10 万文字の見出し', (n) => `# ${'a'.repeat(n)}`, ONE_LINE],
  ['10 万文字の箇条書きの項目', (n) => `- ${'a'.repeat(n)}`, ONE_LINE],
  ['10 万文字の番号つき項目', (n) => `1. ${'a'.repeat(n)}`, ONE_LINE],
  ['10 万文字の引用', (n) => `> ${'a'.repeat(n)}`, ONE_LINE],
  ['10 万文字の表のセル', (n) => L('| h |', '|---|', `| ${'a'.repeat(n)} |`), ONE_LINE],
  ['10 万文字のコードブロックの 1 行', (n) => L(FENCE, 'a'.repeat(n), FENCE), ONE_LINE],
  ['10 万文字のリンクの文字', (n) => `[${'a'.repeat(n)}](x)`, ONE_LINE],
  ['10 万文字のリンクの先', (n) => `[a](${'b'.repeat(n)})`, ONE_LINE],
  ['10 万文字の太字', (n) => `**${'a'.repeat(n)}**`, ONE_LINE],
  ['10 万文字のコード', (n) => `\`${'a'.repeat(n)}\``, ONE_LINE],
  // 深く入れ子にした > と -
  ['深い >：1 行に 10 万個（> > > …）', (n) => `${'> '.repeat(Math.floor(n / 2))}x`, ONE_LINE],
  ['深い >：空白なしで 20 万個', (n) => `${'>'.repeat(n)}x`, BASE],
  ['深い >：行ごとに深くなる', deepLines((i) => `${'> '.repeat(i + 1)}x`), BASE],
  ['深い -：1 行に 10 万個（- - - …）', (n) => `${'- '.repeat(Math.floor(n / 2))}x`, ONE_LINE],
  ['深い -：行ごとに字下げが深くなる', deepLines((i) => `${' '.repeat(2 * i)}- x`), BASE],
  ['深い -：行ごとにタブの字下げが深くなる', deepLines((i) => `${'\t'.repeat(i)}- x`), BASE / 4],
  ['深い 1.：行ごとに字下げが深くなる', deepLines((i) => `${' '.repeat(3 * i)}1. x`), BASE],
  ['深い > の中の -：行ごとに深くなる', deepLines((i) => `${'> '.repeat(i + 1)}- x`), BASE],
];

for (const [label, gen, n] of EXTREME) {
  test(`D0025-AC-36: ${label}：例外が出ず、5000ms 未満で、出力は入力の 20 倍以内`, async () => {
    const { renderMarkdown } = await md();
    const input = gen(n);
    const t0 = performance.now();
    const out = renderMarkdown(input);
    const ms = performance.now() - t0;
    assert.ok(ms < LIMIT_MS, `${ms.toFixed(0)}ms かかった（上限 ${LIMIT_MS}ms）`);
    assert.ok(out.length <= 20 * input.length, `出力 ${out.length} 文字は、入力 ${input.length} 文字の 20 倍（${20 * input.length}）以内`);
  });

  test(`D0025-AC-36: ${label}：入力を 2 倍にすると、出力の長さの伸びは 2.5 倍以内（おおむね線形）`, async () => {
    const { renderMarkdown } = await md();
    const small = renderMarkdown(gen(n));
    const input = gen(2 * n);
    const t0 = performance.now();
    const big = renderMarkdown(input);
    const ms = performance.now() - t0;
    assert.ok(ms < LIMIT_MS, `2 倍の入力に ${ms.toFixed(0)}ms かかった（上限 ${LIMIT_MS}ms）`);
    assert.ok(big.length <= 2.5 * small.length + 64, `出力は ${small.length} 文字から ${big.length} 文字に伸びた（2.5 倍 + 64 以内のはず）`);
  });
}

// ---- 表の安全弁（AC-24・AC-36）：列は 100 まで、1 回の変換のセルは 20,000 まで ----

const count = (html: string, re: RegExp): number => (html.match(re) ?? []).length;
/** th と td の数 */
const cellCount = (html: string): number => count(html, /<t[hd][\s>]/g);

/** 本文の行が 1 つのセルだけ（|x|）の表。列の数だけの頭の行と区切り行がつく */
function sparseTable(cols: number, rows: number): string {
  const head = `|${' c |'.repeat(cols)}`;
  const sep = `|${'---|'.repeat(cols)}`;
  const body = Array.from({ length: rows }, () => '|x|').join('\n');
  return rows === 0 ? L(head, sep) : L(head, sep, body);
}

/** どの行もセルがそろった表 */
function fullTable(cols: number, rows: number, cell = 'x'): string {
  const row = `|${` ${cell} |`.repeat(cols)}`;
  return L(`|${' c |'.repeat(cols)}`, `|${'---|'.repeat(cols)}`, ...Array.from({ length: rows }, () => row));
}

const NOTE = '（表が大きいので、ここから先は省略しました。続きはエディタで開いてください。）';

test('D0025-AC-36: 表の安全弁の値と一文が決めたとおり（列 100・セル 20,000・深さ 3、固定の一文）', async () => {
  const { MARKDOWN_LIMITS, TABLE_CUT_NOTE } = await md();
  assert.deepEqual(MARKDOWN_LIMITS, { listDepth: 3, quoteDepth: 3, tableCols: 100, tableCells: 20_000 });
  assert.equal(TABLE_CUT_NOTE, NOTE);
});

test('D0025-AC-36: ヘッダが 1000 列・本文が 1 文字の行を 5 万行：セルの総数が 20,000 以下で、省略の一文が 1 つ出て、出力は入力の 20 倍以内', async () => {
  const { renderMarkdown, TABLE_CUT_NOTE } = await md();
  const input = sparseTable(1000, 50_000);
  const t0 = performance.now();
  const out = norm(renderMarkdown(input));
  const ms = performance.now() - t0;
  assert.ok(ms < LIMIT_MS, `${ms.toFixed(0)}ms かかった`);
  assert.ok(cellCount(out) <= 20_000, `セルが ${cellCount(out)} 個ある（20,000 以下のはず）`);
  assert.equal(count(out, /<th[\s>]/g), 100, 'ヘッダは 100 列まで');
  assert.equal(out.split(escapeHtml(TABLE_CUT_NOTE)).length - 1, 1, '省略の一文がちょうど 1 つ');
  assert.ok(out.includes(`</table></div><p>${escapeHtml(TABLE_CUT_NOTE)}</p>`), '表のあとに p と一文が出る');
  assert.equal(count(out, /<table>/g), 1);
  assert.equal(count(out, /<\/table>/g), 1);
  assert.equal(count(out, /<tbody>/g), count(out, /<\/tbody>/g));
  assert.ok(count(out, /<tr>/g) > 1, '省略の前までの行は出る');
  assert.ok(out.length <= 20 * input.length, `出力 ${out.length} 文字は入力 ${input.length} 文字の 20 倍以内`);
});

test('D0025-AC-36: 本文の足りないセルを空のセルで足す分も、セルの総数に数える（2 列・1 セルだけの行を 2 万行）', async () => {
  const { renderMarkdown, TABLE_CUT_NOTE } = await md();
  const out = norm(renderMarkdown(sparseTable(2, 20_000)));
  assert.ok(cellCount(out) <= 20_000, `セルが ${cellCount(out)} 個ある（20,000 以下のはず）`);
  assert.equal(out.split(escapeHtml(TABLE_CUT_NOTE)).length - 1, 1, '省略の一文がちょうど 1 つ');
});

test('D0025-AC-36: 列は 100 まで：150 列の表は、ヘッダも本文も 100 列にそろえて余りの列を捨てる', async () => {
  const { renderMarkdown } = await md();
  const out = norm(renderMarkdown(fullTable(150, 1)));
  assert.equal(count(out, /<th[\s>]/g), 100);
  assert.equal(count(out, /<td[\s>]/g), 100);
});

test('D0025-AC-36: 安全弁の内側の表は省かない：100 列・本文 99 行（セルは 10,000 個）は全部出て、一文は出ない', async () => {
  const { renderMarkdown, TABLE_CUT_NOTE } = await md();
  const out = norm(renderMarkdown(fullTable(100, 99)));
  assert.equal(cellCount(out), 100 + 100 * 99);
  assert.equal(count(out, /<tr>/g), 100);
  assert.ok(!out.includes(escapeHtml(TABLE_CUT_NOTE)), '一文が出ない');
});

test('D0025-AC-36: セルの総数は 1 回の変換の全部の表で数える：15,000 個の表が 2 つ並ぶと、1 つ目は全部、2 つ目は途中で省く', async () => {
  const { renderMarkdown, TABLE_CUT_NOTE } = await md();
  const out = norm(renderMarkdown(`${fullTable(100, 149, 'x')}\n\n${fullTable(100, 149, 'y')}`));
  const [first, second] = out.split('</table>');
  assert.equal(count(first, /<tr>/g), 150, '1 つ目の表は全部の行が出る');
  assert.ok(count(second, /<tr>/g) < 150, '2 つ目の表は途中で省かれる');
  assert.ok(cellCount(out) <= 20_000, `セルが ${cellCount(out)} 個ある（20,000 以下のはず）`);
  assert.equal(out.split(escapeHtml(TABLE_CUT_NOTE)).length - 1, 1, '省略の一文がちょうど 1 つ');
});

test('D0025-AC-36: セルの数は次の呼びに持ち越さない：省略した変換のあとでも、小さな表は全部出て、一文は出ない', async () => {
  const { renderMarkdown, TABLE_CUT_NOTE } = await md();
  renderMarkdown(sparseTable(1000, 50_000));
  const out = norm(renderMarkdown(L('| a |', '|---|', '| 1 |')));
  assert.equal(out, tableHtml('a', '1'));
  assert.ok(!out.includes(escapeHtml(TABLE_CUT_NOTE)));
});
