// ソースを文字で読む検査の部品（テストの補助）。D0024：extension.ts の配線を extensionCounts.test.ts が見る。
// extension.ts は vscode を import するので単体では動かせない。判断を持たない呼び出しの形を、文字で読んで確かめる。
// D0025：成果物のプレビューの markdownHtml.ts・panelScript.ts・domain/artifacts.ts・infra/readOnlyFs.ts などの形（時計や node: の読み込み・
// 自前のエスケープ・セレクタに名前を連ねる書き方・上限の数の直書き・readHead の確保）を、後ろの探す関数で見る（sourceText.test.ts が確かめる）。
// 構文を読むものではない：かっこの釣り合いを数えるだけなので、かっこの片側だけを文字列に入れた行があると釣り合いが狂う。
// 行の途中に書いた // のコメントは取り除けないので、検査の言葉は自然な行末コメントに出てこないものにする。

const IDENT_SPECIALS = /[.*+?^${}()|[\]\\]/g;

function escapeRegExp(text: string): string {
  return text.replace(IDENT_SPECIALS, '\\$&');
}

/** open の位置にある開きかっこ（( か {）に釣り合う閉じかっこの位置。釣り合わなければ -1。 */
function matching(code: string, open: number): number {
  const opener = code[open];
  const closer = opener === '(' ? ')' : '}';
  let depth = 0;
  for (let i = open; i < code.length; i++) {
    if (code[i] === opener) depth += 1;
    else if (code[i] === closer) {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return -1;
}

/** 正規表現から g・y の旗を外す（exec が前の位置を覚えないように） */
function once(re: RegExp): RegExp {
  return new RegExp(re.source, re.flags.replace(/[gy]/g, ''));
}

/** 行頭から始まるコメント（ブロックと //）を取り除く。コメントに書いた呼び出しで検査を通さない。文字列の中の「/*」（glob）は行頭にならないので触らない。 */
export function withoutComments(source: string): string {
  return source.replace(/^[ \t]*\/\*[\s\S]*?\*\//gm, '').replace(/^[ \t]*\/\/.*$/gm, '');
}

/**
 * name( の呼び出しごとの、引数の文字（かっこの釣り合いで取る）。
 * import の行（name の後ろに ( が続かない）と、関数の宣言（function name( ・ async function name( ・ export function name( ）は数えない。
 */
export function callArgs(code: string, name: string): string[] {
  const out: string[] = [];
  const re = new RegExp(`(?<!\\bfunction\\s+)\\b${escapeRegExp(name)}\\(`, 'g');
  for (let m = re.exec(code); m !== null; m = re.exec(code)) {
    const open = m.index + m[0].length - 1;
    const close = matching(code, open);
    out.push(code.slice(open + 1, close === -1 ? code.length : close));
  }
  return out;
}

/**
 * function name( ・ async function name( の本体（{ } の中）を、{ } の釣り合いで取る。無ければ null。
 * 引数のかっこの後ろ、最初の { を本体の始まりとするので、戻り値の型に { } を書く関数は対象外。
 */
export function functionBody(code: string, name: string): string | null {
  const head = new RegExp(`\\bfunction\\s+${escapeRegExp(name)}\\s*\\(`).exec(code);
  if (head === null) return null;
  const paramsEnd = matching(code, head.index + head[0].length - 1);
  if (paramsEnd === -1) return null;
  const open = code.indexOf('{', paramsEnd);
  if (open === -1) return null;
  const close = matching(code, open);
  return close === -1 ? null : code.slice(open + 1, close);
}

/**
 * 正規表現 head（開きの { までを含む）に最初に合った所のあとから、釣り合う } の前までの中身。
 * 合う所が無い・釣り合わないときは null。head が { で終わっていなければ使い方の誤りなので例外にする。
 */
export function blockAfter(code: string, head: RegExp): string | null {
  const m = once(head).exec(code);
  if (m === null) return null;
  const open = m.index + m[0].length - 1;
  if (code[open] !== '{') throw new Error(`blockAfter の head は { で終わる正規表現にしてください：${String(head)}`);
  const close = matching(code, open);
  return close === -1 ? null : code.slice(open + 1, close);
}

/** parts（正規表現の並び）の、それぞれ最初に出る位置が、この順に並ぶか。どれかが無ければ偽。後ろに同じ語がもう 1 度あっても、最初の出現が逆なら偽。 */
export function inOrder(text: string, parts: readonly RegExp[]): boolean {
  let last = -1;
  for (const part of parts) {
    const m = once(part).exec(text);
    if (m === null || m.index <= last) return false;
    last = m.index;
  }
  return true;
}

// ---- D0025：成果物のプレビューの構造を、ソースの文字で調べる 6 つの探す関数 ----
// どれも (source: string) => string[]。渡すのはコメントを除く前のソースで、中で行頭のコメントを取り除く（architecture.test.ts の clockUsers と同じ形）。
// 返すのは違反の箇所の短い文字（空白を 1 つにつめ、60 字まで）。違反が無ければ空。使う側は「空であること」を見る。
// 構文を読むものではない：行の途中の // のコメントは取り除けない。名前の一部の語（updatedDate・resetState など）は語境界で見逃す。
// 探す関数そのものの確かめは sourceText.test.ts（違反の見本を見つけ、守っている見本を見逃すこと）。

const SHORT_MAX = 60;

function short(text: string): string {
  const flat = text.replace(/\s+/g, ' ').trim();
  return flat.length > SHORT_MAX ? `${flat.slice(0, SHORT_MAX)}…` : flat;
}

/** re（g の旗つき）に合う所を、出る順に短い文字にして返す */
function findAll(code: string, re: RegExp): string[] {
  return Array.from(code.matchAll(re), (m) => short(m[0]));
}

const CLOCK_OR_NODE = /\bDate\b|\bMath\s*\.\s*random\b|\bperformance\s*\.\s*now\b|\b(?:from|import|require)\s*\(?\s*['"`]node:[^'"`\n]*['"`]/g;

/**
 * 時計・乱数・node: の読み込み（D0025-AC-30：同じ入力から同じ出力ができる。変換器は時計・乱数・ファイルに触れない）。
 * Date（語境界。new Date も Date.now も）・Math.random・performance.now・from／import／require の 'node:…'。
 */
export function findClockOrNode(source: string): string[] {
  return findAll(withoutComments(source), CLOCK_OR_NODE);
}

const ENTITY = /&(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-f]+);/gi;

/**
 * 自前のエスケープ（D0025-AC-33：変換器は escapeHtml を呼び、自前のエスケープを持たない）。
 * 文字参照（&amp; &lt; &gt; &quot; &#39; &apos; のほか &#60; &#x3C; など）を、replace の置き換えや表に書いたもの。
 * &・\x26 で書いた & と、'&' + 'amp;' のように分けて書いたものも、つないで読む。escapeHtml(…) の呼び出しは違反でない（文字参照を書かない）。
 */
export function findOwnEscape(source: string): string[] {
  const code = withoutComments(source)
    .replace(/\\u0026|\\x26|\\u\{0*26\}/g, '&')
    .replace(/['"`]\s*\+\s*['"`]/g, '');
  return findAll(code, ENTITY);
}

/** 上限の数の書き方（正規表現の部品）。256 KiB・その +1（読みの上限）・4 MiB・その +1・4 MiB + 256 KiB・その +1 を、数・16 進・掛け算・シフト・べき乗で書いたもの */
const LIMIT_FORMS: readonly string[] = [
  '262144',
  '262145',
  '4194304',
  '4194305',
  '4456448',
  '4456449',
  '0x40000',
  '0x40001',
  '0x400000',
  '0x400001',
  '0x440000',
  '0x440001',
  String.raw`256\s*\*\s*1024`,
  String.raw`1024\s*\*\s*256`,
  String.raw`4\s*\*\s*1024\s*\*\s*1024`,
  String.raw`1024\s*\*\s*1024\s*\*\s*4`,
  String.raw`1024\s*\*\s*4\s*\*\s*1024`,
  String.raw`4\s*\*\s*1024\s*\*\*\s*2`,
  String.raw`1\s*<<\s*18`,
  String.raw`1\s*<<\s*22`,
  String.raw`256\s*<<\s*10`,
  String.raw`4\s*<<\s*20`,
  String.raw`2\s*\*\*\s*18`,
  String.raw`2\s*\*\*\s*22`,
];
const LIMIT_LITERAL = new RegExp(String.raw`(?<![\w.])(?:${LIMIT_FORMS.join('|')})(?!\w)`, 'gi');

/**
 * 上限の数の直書き（D0025-AC-45：256 KiB と合計の 4 MiB の上限は、artifacts.ts の定数の 1 か所だけ）。
 * 262144・262145・4194304・4194305・4456448・4456449（`_` の区切りは取って読む）、同じ値の 16 進、
 * 256 * 1024・1024 * 256・4 * 1024 * 1024（順序は問わない）・4 * 1024 ** 2、1 << 18・1 << 22・256 << 10・4 << 20・2 ** 18・2 ** 22。
 * 名前に置いた 1024（KIB など）を掛ける書き方、定数からの計算（ARTIFACT_MAX_BYTES / 1024 など）は、直書きではないので見ない。
 * 返す文字は 1 つの書き方につき 1 件（4 * 1024 * 1024 を 2 件にしない）。
 */
export function findLimitLiterals(source: string): string[] {
  return findAll(withoutComments(source).replace(/(?<=\d)_(?=\d)/g, ''), LIMIT_LITERAL);
}

const STORAGE = /\b(?:workspaceState|getState|setState|localStorage|sessionStorage)\b/g;

/**
 * 保存の道（D0025-AC-63：選びとスクロールはパネルのスクリプトの変数だけで持つ）。
 * workspaceState・getState・setState・localStorage・sessionStorage（語境界。resetState・setStateless などの名前の一部は見逃す）。
 */
export function findStorage(source: string): string[] {
  return findAll(withoutComments(source), STORAGE);
}

/** ' と " の文字列の中身を空白に替える（長さと位置は変わらない）。文字列は行の終わりで閉じる（行末の // のコメントの ' で、あとの行を巻き込まない）。
 *  バッククォートは追わない：panelScript.ts は全体がバッククォートの文字列で、その中の JS を読むため。 */
function blankQuoted(code: string): string {
  let out = '';
  let quote: string | null = null;
  for (let i = 0; i < code.length; i++) {
    const c = code[i];
    if (quote === null) {
      out += c;
      if (c === "'" || c === '"') quote = c;
    } else if (c === '\n') {
      out += c;
      quote = null;
    } else if (c === '\\') {
      out += code[i + 1] === undefined ? ' ' : '  ';
      i += 1;
    } else if (c === quote) {
      out += c;
      quote = null;
    } else {
      out += ' ';
    }
  }
  return out;
}

const SELECTOR_CALL = /\b(querySelectorAll|querySelector|closest)\s*\(/g;
/** 変数に組み立ててから渡す抜け道：`[属性="` や `[属性=` で終わる文字列に + が続く／`[属性="${` の形 */
const SELECTOR_FRAGMENT = /\[[\w:-]+\s*=\s*(?:\\?["'])?["']\s*\+|\[[\w:-]+\s*=\s*\\?["']?\$\{/g;
/**
 * 許す連ねる形は 1 つだけ：restoreFocus の querySelectorAll('[' + key.attr + ']')（key.attr 以外の識別子は許さない）。
 * key.attr に入るのは data-keep・data-run・data-reasons の固定の 3 つの属性の「名前」で、外から来た値ではない。値の位置（[属性= のあと）でもないので、違反にしない。
 * D0025 は「焦点の復元は今の focusKey／restoreFocus のまま」と決めた。
 * 識別子の連なりなら何でも許すと、'[' + name + ']' のように外から来た名前を連ねる書き方まで見逃す（D0025 の実装の段の読み手が見つけた）ので、key.attr の形だけにした。
 * 空白の入れ方（key . attr、+ の前後）と引用符（' と "）は問わない。key.attrs・key.attr.x・monkey.attr は許さない。
 */
const ATTR_NAME_CONCAT = /(['"])\[\1\s*\+\s*key\s*\.\s*attr\s*\+\s*(['"])\]\2/g;

/** text の spans（[始まり, 終わり)）を、同じ長さの空白に替える */
function eraseSpans(text: string, spans: readonly (readonly [number, number])[]): string {
  let out = text;
  for (const [from, to] of spans) out = out.slice(0, from) + ' '.repeat(to - from) + out.slice(to);
  return out;
}

/**
 * セレクタに名前を連ねる書き方（D0025-AC-64：名前で要素を探すときは getAttribute(…) === 名前 の等値比較にする）。
 * querySelector・querySelectorAll・closest の引数に、+（文字列の外のもの）・.concat(・${ がある呼び出し。
 * 変数に組み立ててから渡す抜け道（const s = '[data-x="' + name + '"]'; … querySelector(s)）も、`[属性="` で終わる文字に + が続く形と、
 * `[属性="${` の形で見つける。引数の文字列の中の + や ( ) は見ない（'li + li'・'[x=")"]'）。
 * 見つけないもの：restoreFocus の '[' + key.attr + ']' の 1 つだけ（属性の名前を連ねるだけで、値の位置ではない。D0025 が「今のまま」とした形）。
 * '[' + name + ']' のように key.attr 以外の識別子を連ねるもの、'[' + key.attr + '="' + key.value + '"]' のように値も連ねるもの、
 * '[' + key.attr + ']' + name のようにほかも連ねるものは見つける。
 */
export function findSelectorConcat(source: string): string[] {
  const code = withoutComments(source);
  const blank = blankQuoted(code);
  const hits: { at: number; text: string }[] = [];
  const covered: (readonly [number, number])[] = [];
  for (const m of blank.matchAll(SELECTOR_CALL)) {
    const open = (m.index ?? 0) + m[0].length - 1;
    const close = matching(blank, open);
    const end = close === -1 ? code.length : close;
    covered.push([open, end]);
    const rawArg = code.slice(open + 1, end);
    const allowed = Array.from(rawArg.matchAll(ATTR_NAME_CONCAT), (a) => [a.index ?? 0, (a.index ?? 0) + a[0].length] as const);
    const blankArg = eraseSpans(blank.slice(open + 1, end), allowed);
    if (/\+|\.\s*concat\s*\(/.test(blankArg) || eraseSpans(rawArg, allowed).includes('${')) {
      hits.push({ at: m.index ?? 0, text: short(`${m[1]}(${rawArg})`) });
    }
  }
  for (const m of code.matchAll(SELECTOR_FRAGMENT)) {
    const at = m.index ?? 0;
    if (covered.some(([from, to]) => at > from && at < to)) continue;
    hits.push({ at, text: short(m[0]) });
  }
  return hits.sort((a, b) => a.at - b.at).map((h) => h.text);
}

const READ_HEAD_ZERO_ALLOC = /\bBuffer\s*\.\s*alloc\s*\(/;
const READ_HEAD_LIGHT_ALLOC = /\bBuffer\s*\.\s*(?:allocUnsafe|allocUnsafeSlow)\s*\(/;
const READ_HEAD_TRIM = /\.\s*subarray\s*\(\s*0\s*,\s*bytesRead\s*\)/;

/**
 * readHead の確保の軽さ（D0025-AC-43：小さいファイルでも 256 KiB を 0 で埋めて確保しない。
 * 確保しただけの領域を漏らさないよう、読んだ分 subarray(0, bytesRead) だけを返す。どちらか一方だけだと、軽くならないか、漏れる）。
 * function readHead( の本体の中に、Buffer.alloc( が無く、Buffer.allocUnsafe( か Buffer.allocUnsafeSlow( があり、.subarray(0, bytesRead) がある、を調べる。
 * 返すのは直すところの文（空なら守っている）。readHead の宣言が読めなければ、それが 1 件。
 * 行頭のコメントと、行末の // のコメントは取り除いて探す（文字列の中身は空白にしてから // を取るので、'a//b' の // は巻き込まない）。
 * 別の関数にだけある呼び出しは数えない（readHead の本体だけを見る）。
 */
export function findReadHeadAlloc(source: string): string[] {
  const code = blankQuoted(withoutComments(source)).replace(/\/\/.*$/gm, '');
  const body = functionBody(code, 'readHead');
  if (body === null) return ['readHead の宣言（function readHead(…) { … }）が読めない'];
  const problems: string[] = [];
  if (READ_HEAD_ZERO_ALLOC.test(body)) problems.push('Buffer.alloc( で確保している（Buffer.allocUnsafe( にする）');
  if (!READ_HEAD_LIGHT_ALLOC.test(body)) problems.push('Buffer.allocUnsafe( で確保していない');
  if (!READ_HEAD_TRIM.test(body)) problems.push('読んだ分だけ .subarray(0, bytesRead) で返していない（確保したままの領域を漏らす）');
  return problems;
}
