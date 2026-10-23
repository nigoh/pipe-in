// Markdown → 許すタグだけの HTML（純粋）。D0025。成果物のプレビューに使う、自前の小さな変換。
// 入れ物の div.md は付けない（呼ぶ側が付ける）。空の入力は空の出力。
// 守ること：
// - 出すタグは h3〜h6・p・ul・ol・li・table・thead・tbody・tr・th・td・pre・code・blockquote・hr・strong・em・div だけ。属性は class と、ol の整数の start だけ。
// - 外から来た文字は、出すところで escapeHtml を 1 回だけ通す（先に HTML にしてから通すことはしない）。
// - リンクは a にせず、画像は読み込まない（どちらも文字にして出す）。HTML・自動リンクなど、ほかの書き方も文字のまま出す。
// - 入力の長さに比例する走査にする。同じところを読み直す書き方（入れ子の繰り返しの正規表現）を使わず、行の中の印は 1 回なめて組にする。
// - 同じ入力からは同じ出力。時計・乱数・ファイルに触れない。変換の途中の状態（表のセルの数・表の HTML の残りの長さ）は 1 回の呼びの中だけで持つ。
// - 小さい入力から大きな HTML ができないように、表は「セルの数」と「HTML の長さ（入力の 20 倍）」の両方で止める。
import { escapeHtml } from './escape.ts';

/** 入れ子の深さと表の安全弁。表は列 100・1 回の変換のセル 20,000 まで（超えた分は省いて TABLE_CUT_NOTE を出す） */
export const MARKDOWN_LIMITS = Object.freeze({ listDepth: 3, quoteDepth: 3, tableCols: 100, tableCells: 20_000 });
/** 表を省いたときの一文（1 回の変換で 1 つだけ） */
export const TABLE_CUT_NOTE = '（表が大きいので、ここから先は省略しました。続きはエディタで開いてください。）';
/**
 * 表の HTML の長さの上限は、入力の長さの 20 倍（1 回の変換の全部の表の合計）。超えた本文の行は、セルの数の上限と同じに省く。
 * セルの数だけでは、小さい入力が大きな HTML になる（右寄せの 100 列の表に `|` だけの行を足すと、2.6 KB が約 52 万文字）。
 * 頭の行は、予算が足りなくても出す（セルの数の上限で止まる）。予算から引くので、あとの本文の行から省かれる。
 */
const TABLE_HTML_RATIO = 20;
/** 表の枠のタグ（div・table・thead・tr・tbody の開きと閉じ）の文字数。頭の行を出すときに、予算から先に引く */
const TABLE_FRAME_LENGTH = '<div class="md-table"><table><thead><tr></tr></thead><tbody></tbody></table></div>'.length;
/** 省略の一文の HTML。予算の始めから引いておく（行を予算いっぱいまで出したあとに足しても、20 倍を超えない） */
const TABLE_CUT_HTML = `<p>${escapeHtml(TABLE_CUT_NOTE)}</p>`;

// ---- 文字の番号 ----

const TAB = 9;
const SPACE = 32;
const BANG = 33;
const HASH = 35;
const STAR = 42;
const PLUS = 43;
const DASH = 45;
const DOT = 46;
const LPAREN = 40;
const RPAREN = 41;
const GT = 62;
const LBRACKET = 91;
const BACKSLASH = 92;
const UNDERSCORE = 95;
const BACKTICK = 96;
const PIPE = 124;
const TILDE = 126;

const UNICODE_SPACE = /\s/;
const WORD_CHAR = /^[\p{L}\p{N}]$/u;
// 表の区切り行に出てよい文字だけか（全部を分ける前の軽い確かめ）／区切り行のセル
const SEP_CHARS = /^[\s|:-]*$/;
const SEP_CELL = /^:?-+:?$/;

/** 空白（全角など Unicode の空白も含む） */
function isSpaceCode(code: number): boolean {
  if (code === SPACE || (code >= TAB && code <= 13)) return true;
  return code > 127 && UNICODE_SPACE.test(String.fromCharCode(code));
}

/** 字下げに使う空白（空白とタブ） */
function isBlankCode(code: number): boolean {
  return code === SPACE || code === TAB;
}

/** 文字か数字（日本語の文字も含む）。cp は文字の番号 */
function isWordCode(cp: number): boolean {
  if (cp < 128) return (cp >= 48 && cp <= 57) || (cp >= 65 && cp <= 90) || (cp >= 97 && cp <= 122);
  return WORD_CHAR.test(String.fromCodePoint(cp));
}

/** s の i 番目の直前の 1 文字（サロゲートペアは 1 文字として見る）が、文字か数字か */
function wordBefore(s: string, i: number): boolean {
  if (i <= 0) return false;
  const low = s.charCodeAt(i - 1);
  if (low >= 0xdc00 && low <= 0xdfff && i >= 2) {
    const high = s.charCodeAt(i - 2);
    if (high >= 0xd800 && high <= 0xdbff) return isWordCode(s.codePointAt(i - 2) ?? 0);
  }
  return isWordCode(low);
}

/** s の i 番目の 1 文字が、文字か数字か */
function wordAt(s: string, i: number): boolean {
  if (i >= s.length) return false;
  return isWordCode(s.codePointAt(i) ?? 0);
}

// ---- 行の中（コード・太字・斜体・リンク・画像） ----

interface Ticks {
  pos: number[]; // バッククォートの並びの始まり
  len: number[]; // その長さ
  next: number[]; // 同じ長さの、次の並びの番号（無ければ -1）
}

/** from 以降のバッククォートの並びを集め、同じ長さの次の並びを後ろから 1 回で引けるようにする */
function scanTicks(s: string, from: number): Ticks {
  const pos: number[] = [];
  const len: number[] = [];
  let i = s.indexOf('`', from);
  while (i !== -1) {
    let j = i + 1;
    while (s.charCodeAt(j) === BACKTICK) j += 1;
    pos.push(i);
    len.push(j - i);
    i = s.indexOf('`', j);
  }
  const next: number[] = new Array<number>(pos.length).fill(-1);
  const seen = new Map<number, number>();
  for (let k = pos.length - 1; k >= 0; k -= 1) {
    next[k] = seen.get(len[k]) ?? -1;
    seen.set(len[k], k);
  }
  return { pos, len, next };
}

/** 位置 p より後ろで最初の ch の位置。問い合わせの p は前にしか進まないので、前の答えを使い回して全体を線形にする（無ければ -1） */
function nextOf(s: string, ch: string, p: number, cache: { v: number }): number {
  if (cache.v === -1 || cache.v > p) return cache.v;
  cache.v = s.indexOf(ch, p + 1);
  return cache.v;
}

/**
 * 行の中の印を HTML にする。
 * - `コード`（同じ長さのバッククォートの並びで閉じる。閉じが無ければ文字）。中は変換しない。
 * - **太字**・*斜体*・_斜体_。始まりの印は次が空白でないこと、終わりの印は前が空白でないこと。* の並びは 1 つか 2 つだけが印、_ は 1 つだけ。
 *   _ は両隣が文字か数字なら印にしない。\ の直後の * と _ は印にしない。終わりの印は、同じ種類の一番新しい開いた印とだけ組にする。
 * - [文字](先) は「文字（先）」、![代わり](先) は「[画像：代わり]」の文字にする。リンクの文字の中の印は変換しない。
 * 閉じなかった印・組にならなかった印は、書いたとおりの文字で出す。
 */
function inline(s: string): string {
  if (s === '') return '';
  const len = s.length;
  const out: string[] = [];
  // 開いたままの印（out の番号）。0 が **、1 が *、2 が _
  const open: number[][] = [[], [], []];
  const closeCache = { v: -2 };
  const openCache = { v: -2 };
  let ticks: Ticks | null = null;
  let ti = 0;
  let text = 0; // まだ出していない普通の文字の始まり
  let linkText0 = 0;
  let linkText1 = 0;
  let linkDest0 = 0;
  let linkDest1 = 0;

  const flush = (upTo: number): void => {
    if (upTo > text) out.push(escapeHtml(s.slice(text, upTo)));
  };

  /** p の [ から始まるリンクなら、閉じの ) の次の位置（文字の範囲は linkText*、先は linkDest* に入れる）。リンクでなければ -1 */
  const linkAt = (p: number): number => {
    const close = nextOf(s, ']', p, closeCache);
    if (close === -1) return -1;
    // 文字の中に別の [ があるときは、あとの [ のほうが組になる
    const nextOpen = nextOf(s, '[', p, openCache);
    if (nextOpen !== -1 && nextOpen < close) return -1;
    if (s.charCodeAt(close + 1) !== LPAREN) return -1;
    let e = close + 2;
    while (e < len) {
      const d = s.charCodeAt(e);
      if (d === LPAREN || d === RPAREN || isSpaceCode(d)) break;
      e += 1;
    }
    if (e === close + 2 || s.charCodeAt(e) !== RPAREN) return -1;
    linkText0 = p + 1;
    linkText1 = close;
    linkDest0 = close + 2;
    linkDest1 = e;
    return e + 1;
  };

  let i = 0;
  while (i < len) {
    const c = s.charCodeAt(i);
    if (c === BACKTICK) {
      if (ticks === null) ticks = scanTicks(s, i);
      while (ti < ticks.pos.length && ticks.pos[ti] < i) ti += 1;
      if (ti >= ticks.pos.length || ticks.pos[ti] !== i) {
        i += 1;
        continue;
      }
      const run = ticks.len[ti];
      const partner = ticks.next[ti];
      if (partner === -1) {
        // 閉じが無いバッククォートは文字
        i += run;
        ti += 1;
        continue;
      }
      flush(i);
      out.push(`<code>${escapeHtml(s.slice(i + run, ticks.pos[partner]))}</code>`);
      i = ticks.pos[partner] + ticks.len[partner];
      text = i;
      ti = partner + 1;
    } else if (c === BACKSLASH) {
      const after = s.charCodeAt(i + 1);
      i += after === STAR || after === UNDERSCORE ? 2 : 1;
    } else if (c === BANG && s.charCodeAt(i + 1) === LBRACKET) {
      const end = linkAt(i + 1);
      if (end === -1) {
        i += 1;
        continue;
      }
      flush(i);
      out.push(`[画像：${escapeHtml(s.slice(linkText0, linkText1))}]`);
      i = end;
      text = i;
    } else if (c === LBRACKET) {
      const end = linkAt(i);
      if (end === -1) {
        i += 1;
        continue;
      }
      flush(i);
      out.push(`${escapeHtml(s.slice(linkText0, linkText1))}（${escapeHtml(s.slice(linkDest0, linkDest1))}）`);
      i = end;
      text = i;
    } else if (c === STAR || c === UNDERSCORE) {
      let j = i + 1;
      while (s.charCodeAt(j) === c) j += 1;
      const run = j - i;
      const isMark = run <= (c === STAR ? 2 : 1) && !(c === UNDERSCORE && wordBefore(s, i) && wordAt(s, j));
      if (isMark) {
        const canOpen = j < len && !isSpaceCode(s.charCodeAt(j));
        const canClose = i > 0 && !isSpaceCode(s.charCodeAt(i - 1));
        const kind = c === UNDERSCORE ? 2 : run === 2 ? 0 : 1;
        const stack = open[kind];
        if (canClose && stack.length > 0) {
          flush(i);
          const opener = stack[stack.length - 1];
          stack.pop();
          const tag = kind === 0 ? 'strong' : 'em';
          out[opener] = `<${tag}>`;
          out.push(`</${tag}>`);
          // 組にした 2 つの間に開いたままだった印は、組にならないので文字のまま残す
          for (const other of open) {
            while (other.length > 0 && other[other.length - 1] > opener) other.pop();
          }
          text = j;
        } else if (canOpen) {
          flush(i);
          stack.push(out.length);
          out.push(escapeHtml(s.slice(i, j)));
          text = j;
        }
      }
      i = j;
    } else {
      i += 1;
    }
  }
  flush(len);
  return out.join('');
}

// ---- 行の判定 ----

type Align = '' | 'md-left' | 'md-center' | 'md-right';

interface FenceLine {
  k: 'fence';
  ch: number;
  len: number;
  indent: number;
}
interface TableLine {
  k: 'table';
  head: string[];
  aligns: Align[];
}
interface ItemLine {
  k: 'item';
  indent: number;
  ordered: boolean;
  num: string;
  text: string;
}
type Line =
  | { k: 'blank' }
  | { k: 'hr' }
  | { k: 'quote' }
  | { k: 'heading'; level: number; text: string }
  | { k: 'para'; text: string }
  | FenceLine
  | TableLine
  | ItemLine;

const BLANK: Line = { k: 'blank' };
const RULE: Line = { k: 'hr' };
const QUOTE: Line = { k: 'quote' };

/** 同じ記号を 3 つ以上並べただけの行か（間の空白は許さない）。t は右の空白を取ってある */
function isRule(t: string): boolean {
  if (t.length < 3) return false;
  const c = t.charCodeAt(0);
  for (let i = 1; i < t.length; i += 1) if (t.charCodeAt(i) !== c) return false;
  return true;
}

/** 見出し。# が 1〜6 個、空白、文字が 1 つ以上。行末の # は取らない */
function headingOf(t: string): Line | null {
  let n = 0;
  while (n < 7 && t.charCodeAt(n) === HASH) n += 1;
  if (n < 1 || n > 6 || !isBlankCode(t.charCodeAt(n))) return null;
  const text = t.slice(n).trim();
  return text === '' ? null : { k: 'heading', level: n, text };
}

/** コードブロックの囲みの始まり。``` か ~~~ が 3 つ以上（``` の言語名にバッククォートがあるときは、行の中のコードなので囲みにしない） */
function openFence(t: string, col: number): Line | null {
  const ch = t.charCodeAt(0);
  let n = 1;
  while (t.charCodeAt(n) === ch) n += 1;
  if (n < 3) return null;
  if (ch === BACKTICK && t.indexOf('`', n) !== -1) return null;
  return { k: 'fence', ch, len: n, indent: col };
}

/** 囲みの終わり。同じ記号を同じかそれ以上の長さだけ並べた行（前後の空白は可） */
function closesFence(line: string, f: FenceLine): boolean {
  const t = line.trim();
  if (t.length < f.len) return false;
  for (let i = 0; i < t.length; i += 1) if (t.charCodeAt(i) !== f.ch) return false;
  return true;
}

/** 囲みの中の行から、開始行と同じ数までの字下げを取る */
function dropIndent(line: string, max: number): string {
  if (max <= 0) return line;
  let pos = 0;
  let col = 0;
  while (pos < line.length) {
    const c = line.charCodeAt(pos);
    const width = c === SPACE ? 1 : c === TAB ? 4 : 0;
    if (width === 0 || col + width > max) break;
    col += width;
    pos += 1;
  }
  return pos === 0 ? line : line.slice(pos);
}

/** 箇条書きの項目。印は [-*+] か 数字+.、そのあとに空白（タブ）1 つ以上。数字は何桁でもよい */
function itemOf(rest: string, col: number): Line | null {
  const c0 = rest.charCodeAt(0);
  if (c0 === DASH || c0 === STAR || c0 === PLUS) {
    if (!isBlankCode(rest.charCodeAt(1))) return null;
    return { k: 'item', indent: col, ordered: false, num: '', text: rest.slice(2).trim() };
  }
  if (c0 >= 48 && c0 <= 57) {
    let d = 1;
    while (rest.charCodeAt(d) >= 48 && rest.charCodeAt(d) <= 57) d += 1;
    if (rest.charCodeAt(d) !== DOT || !isBlankCode(rest.charCodeAt(d + 1))) return null;
    return { k: 'item', indent: col, ordered: true, num: rest.slice(0, d), text: rest.slice(d + 2).trim() };
  }
  return null;
}

/**
 * 表の 1 行を、| で分けたセルにする（前後の空白を取る。\| は文字の |。両端の | は省ける）。
 * セルが max 個になったら、そこで止める（本文の行は頭の行の列数までしか要らない）。
 */
function splitRow(line: string, max: number): string[] {
  const s = line.trim();
  const len = s.length;
  const cells: string[] = [];
  let parts: string[] = [];
  let from = 0;
  let i = 0;
  if (s.charCodeAt(0) === PIPE) {
    i = 1;
    from = 1;
  }
  let endsWithBar = false;
  while (i < len) {
    const c = s.charCodeAt(i);
    if (c === BACKSLASH && s.charCodeAt(i + 1) === PIPE) {
      parts.push(s.slice(from, i), '|');
      i += 2;
      from = i;
    } else if (c === PIPE) {
      parts.push(s.slice(from, i));
      cells.push(parts.join('').trim());
      if (cells.length >= max) return cells;
      parts = [];
      i += 1;
      from = i;
      endsWithBar = i === len;
    } else {
      i += 1;
    }
  }
  if (!endsWithBar) {
    parts.push(s.slice(from));
    cells.push(parts.join('').trim());
  }
  return cells;
}

/** 表の頭の行 head と、次の行 next が区切り行なら表の始まり（区切り行は | を含み、各セルが :?-+:?、セルの数が頭の行と同じ） */
function tableAt(head: string, next: string): Line | null {
  if (!next.includes('|') || !SEP_CHARS.test(next)) return null;
  const sep = splitRow(next, Infinity);
  for (const cell of sep) if (!SEP_CELL.test(cell)) return null;
  const cells = splitRow(head, Infinity);
  if (cells.length !== sep.length) return null;
  const cols = Math.min(cells.length, MARKDOWN_LIMITS.tableCols);
  const aligns: Align[] = sep.slice(0, cols).map((cell) => {
    const left = cell.startsWith(':');
    const right = cell.endsWith(':');
    return left && right ? 'md-center' : right ? 'md-right' : left ? 'md-left' : '';
  });
  return { k: 'table', head: cells.slice(0, cols), aligns };
}

/**
 * 行 i の種類。判定の順は 空行 → 囲み → 区切り線 → 見出し → 引用 → 表 → 箇条書きの項目 → 段落。
 * 見出し・区切り線・引用・表の頭は字下げ 3 つまで。囲みと箇条書きは何個でもよい（箇条書きは字下げを深さに使う）。タブは空白 4 つ。
 */
function classify(lines: readonly string[], i: number): Line {
  const line = lines[i];
  let pos = 0;
  let col = 0;
  while (pos < line.length) {
    const c = line.charCodeAt(pos);
    if (c === SPACE) col += 1;
    else if (c === TAB) col += 4;
    else break;
    pos += 1;
  }
  const rest = pos === 0 ? line : line.slice(pos);
  const t = rest.trimEnd();
  if (t === '') return BLANK;
  const c0 = t.charCodeAt(0);
  if (c0 === BACKTICK || c0 === TILDE) {
    const fence = openFence(t, col);
    if (fence !== null) return fence;
  }
  if (col <= 3) {
    if ((c0 === DASH || c0 === STAR || c0 === UNDERSCORE) && isRule(t)) return RULE;
    if (c0 === HASH) {
      const heading = headingOf(t);
      if (heading !== null) return heading;
    }
    if (c0 === GT) return QUOTE;
    if (i + 1 < lines.length && t.includes('|')) {
      const table = tableAt(t, lines[i + 1]);
      if (table !== null) return table;
    }
  }
  const item = itemOf(rest, col);
  if (item !== null) return item;
  return { k: 'para', text: rest.trim() };
}

// ---- 引用 ----

/** 引用の行から、字下げ（空白 3 つまで）と > と、その後ろの空白 1 つを取る。引用の行でなければ null */
function unquote(line: string): string | null {
  let p = 0;
  while (p < 4 && line.charCodeAt(p) === SPACE) p += 1;
  if (p > 3 || line.charCodeAt(p) !== GT) return null;
  p += 1;
  if (line.charCodeAt(p) === SPACE) p += 1;
  return line.slice(p);
}

/** 行頭の > を（続くものも）全部取る。4 段目以降の > は、取り除いて 3 段目の中身にする */
function unquoteAll(line: string): string {
  let cur = line;
  for (;;) {
    const next = unquote(cur);
    if (next === null) return cur;
    cur = next;
  }
}

// ---- 箇条書き ----

interface ItemNode {
  lines: string[];
  kids: ListNode[];
}
interface ListNode {
  ordered: boolean;
  num: string; // ol の最初の項目の数字
  items: ItemNode[];
}
interface Level {
  list: ListNode;
  indent: number;
  parent: ItemNode | null; // この一覧を子に持つ項目（いちばん上は null）
}
interface ListState {
  roots: ListNode[]; // 同じ深さで種類が替わると並ぶ
  stack: Level[]; // 開いている段（浅い順）
  last: ItemNode;
  lastIndent: number;
}

function newList(item: ItemLine, node: ItemNode): ListNode {
  return { ordered: item.ordered, num: item.num, items: [node] };
}

function startList(first: ItemLine): ListState {
  const node: ItemNode = { lines: [first.text], kids: [] };
  const list = newList(first, node);
  return { roots: [list], stack: [{ list, indent: first.indent, parent: null }], last: node, lastIndent: first.indent };
}

/**
 * 次の項目が入る場所。直前の項目より字下げが 2 つ以上深ければ子（3 段まで。それより深いときは 3 段目に並ぶ）、
 * 浅ければ、字下げが合う段まで戻り、そうでなければ兄弟。
 */
function placeOf(ls: ListState, indent: number): { child: boolean; level: number } {
  const deeper = indent >= ls.lastIndent + 2;
  if (deeper && ls.stack.length < MARKDOWN_LIMITS.listDepth) return { child: true, level: ls.stack.length };
  let level = ls.stack.length - 1;
  if (!deeper) while (level > 0 && ls.stack[level].indent > indent) level -= 1;
  return { child: false, level };
}

/** 空行のあとの項目が、同じ一覧に入れるか（入る段の一覧と同じ種類か、子として新しく開くとき） */
function listAccepts(ls: ListState, item: ItemLine): boolean {
  const place = placeOf(ls, item.indent);
  return place.child || ls.stack[place.level].list.ordered === item.ordered;
}

function listAdd(ls: ListState, item: ItemLine): void {
  const place = placeOf(ls, item.indent);
  const node: ItemNode = { lines: [item.text], kids: [] };
  if (place.child) {
    const list = newList(item, node);
    ls.last.kids.push(list);
    ls.stack.push({ list, indent: item.indent, parent: ls.last });
  } else {
    // 浅いほうへ戻るときは、深い段を閉じる
    ls.stack.length = place.level + 1;
    const top = ls.stack[place.level];
    if (top.list.ordered === item.ordered) {
      top.list.items.push(node);
    } else {
      // 種類が替わると、その深さで一覧を閉じて開き直す
      const list = newList(item, node);
      if (top.parent === null) ls.roots.push(list);
      else top.parent.kids.push(list);
      top.list = list;
      top.indent = item.indent;
    }
  }
  ls.last = node;
  ls.lastIndent = item.indent;
}

/**
 * 段落の途中に出た項目の印が、段落を終わらせるか。箇条書き（- * +）と「1.」は終わらせる。
 * 1 でない番号（「2025. …」のように、折り返した行の頭に来た年や番号）は、段落の文字の続き（CommonMark と同じ）。
 */
function endsParagraph(item: ItemLine): boolean {
  return !item.ordered || Number(item.num) === 1;
}

/** ol の start。最初の数字が 1〜4 桁で値が 2 以上のときだけ付ける */
function startAttr(num: string): string {
  if (num.length > 4) return '';
  const value = Number(num);
  return value >= 2 ? ` start="${value}"` : '';
}

function renderList(list: ListNode): string {
  const tag = list.ordered ? 'ol' : 'ul';
  const attr = list.ordered ? startAttr(list.num) : '';
  const items = list.items.map((item) => `<li>${inline(item.lines.join(' ').trim())}${item.kids.map(renderList).join('')}</li>`);
  return `<${tag}${attr}>${items.join('')}</${tag}>`;
}

// ---- 表 ----

/** 1 回の変換の中だけで持つ状態 */
interface State {
  cells: number; // 出した表のセルの数（全部の表の合計）
  room: number; // 表の HTML に使える残りの文字数（全部の表の合計。頭の行で負になることがある）
  noted: boolean; // 省略の一文を出したか
}

function cellsHtml(tag: 'th' | 'td', cells: readonly string[], aligns: readonly Align[]): string {
  return cells.map((cell, k) => `<${tag}${aligns[k] === '' ? '' : ` class="${aligns[k]}"`}>${inline(cell)}</${tag}>`).join('');
}

/**
 * 表を作る。頭の行が lines[i]、区切り行が lines[i + 1]。次に読む行の番号も返す。
 * セルの数か HTML の長さの上限を超えたら、そこから先の行は省く。省略の一文を出したあとの表は、丸ごと省く。
 */
function renderTable(lines: readonly string[], i: number, table: TableLine, st: State): { html: string; next: number } {
  const cols = table.head.length;
  const limit = MARKDOWN_LIMITS.tableCells;
  const parts: string[] = [];
  const showTable = !st.noted && st.cells + cols <= limit;
  let cut = !showTable;
  if (showTable) {
    const head = cellsHtml('th', table.head, table.aligns);
    st.cells += cols;
    st.room -= TABLE_FRAME_LENGTH + head.length;
    parts.push(`<div class="md-table"><table><thead><tr>${head}</tr></thead>`);
  }
  const rows: string[] = [];
  let j = i + 2;
  // 本文は、| を含まない行か空行の前まで。省いたあとも、読み進めるために行は数える
  while (j < lines.length && lines[j].includes('|')) {
    if (!cut) {
      if (st.cells + cols > limit) {
        cut = true;
      } else {
        const cells = splitRow(lines[j], cols);
        while (cells.length < cols) cells.push('');
        const row = `<tr>${cellsHtml('td', cells, table.aligns)}</tr>`;
        if (row.length > st.room) {
          cut = true;
        } else {
          st.cells += cols;
          st.room -= row.length;
          rows.push(row);
        }
      }
    }
    j += 1;
  }
  if (showTable) {
    if (rows.length > 0) parts.push(`<tbody>${rows.join('')}</tbody>`);
    parts.push('</table></div>');
  }
  if (cut && !st.noted) {
    st.noted = true;
    parts.push(TABLE_CUT_HTML);
  }
  return { html: parts.join(''), next: j };
}

// ---- ブロック ----

/** 行の並びをブロックにして、HTML の並びで返す。depth は引用の深さ（3 に着いたら、行頭の > は取り除いて中身にする） */
function parseBlocks(input: readonly string[], depth: number, st: State): string[] {
  const lines = depth >= MARKDOWN_LIMITS.quoteDepth ? input.map(unquoteAll) : input;
  const n = lines.length;
  const out: string[] = [];
  let i = 0;
  while (i < n) {
    const ln = classify(lines, i);
    switch (ln.k) {
      case 'blank': {
        i += 1;
        break;
      }
      case 'hr': {
        out.push('<hr>');
        i += 1;
        break;
      }
      case 'heading': {
        // # が h3、## が h4、### が h5、#### 以降が h6（元の段は class に残す）
        const tag = Math.min(ln.level + 2, 6);
        out.push(`<h${tag} class="md-h${ln.level}">${inline(ln.text)}</h${tag}>`);
        i += 1;
        break;
      }
      case 'fence': {
        const body: string[] = [];
        i += 1;
        while (i < n && !closesFence(lines[i], ln)) {
          body.push(dropIndent(lines[i], ln.indent));
          i += 1;
        }
        // 閉じが無ければ最後まで。あれば閉じの行を読み終える
        if (i < n) i += 1;
        out.push(`<pre><code>${escapeHtml(body.join('\n'))}</code></pre>`);
        break;
      }
      case 'quote': {
        // > で始まる続く行を 1 つの引用にして、中身を同じ規則で読み直す
        const inner: string[] = [];
        let rest = unquote(lines[i]);
        while (rest !== null) {
          inner.push(rest);
          i += 1;
          rest = i < n ? unquote(lines[i]) : null;
        }
        out.push(`<blockquote>${parseBlocks(inner, depth + 1, st).join('')}</blockquote>`);
        break;
      }
      case 'table': {
        const table = renderTable(lines, i, ln, st);
        out.push(table.html);
        i = table.next;
        break;
      }
      case 'item': {
        const ls = startList(ln);
        i += 1;
        while (i < n) {
          const next = classify(lines, i);
          if (next.k === 'item') {
            listAdd(ls, next);
            i += 1;
          } else if (next.k === 'para') {
            // 印のない行は、直前の項目の文字の続き
            ls.last.lines.push(next.text);
            i += 1;
          } else if (next.k === 'blank') {
            // 空行のあと、同じ種類の項目が続くなら同じ一覧。そうでなければ一覧を閉じる
            let j = i + 1;
            let after: Line = BLANK;
            while (j < n) {
              after = classify(lines, j);
              if (after.k !== 'blank') break;
              j += 1;
            }
            if (j < n && after.k === 'item' && listAccepts(ls, after)) {
              listAdd(ls, after);
              i = j + 1;
            } else {
              break;
            }
          } else {
            // 見出し・囲み・区切り線・引用・表の頭は、一覧を閉じる
            break;
          }
        }
        out.push(ls.roots.map(renderList).join(''));
        break;
      }
      case 'para': {
        const texts: string[] = [ln.text];
        i += 1;
        while (i < n) {
          const next = classify(lines, i);
          if (next.k === 'para') texts.push(next.text);
          else if (next.k === 'item' && !endsParagraph(next)) texts.push(lines[i].trim());
          else break;
          i += 1;
        }
        out.push(`<p>${inline(texts.join(' '))}</p>`);
        break;
      }
    }
  }
  return out;
}

/** Markdown → 許すタグだけの HTML。純粋。入れ物の div.md は付けない。空の入力は '' */
export function renderMarkdown(source: string): string {
  let text = source.replace(/\u0000/g, '�');
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  const room = TABLE_HTML_RATIO * source.length - TABLE_CUT_HTML.length;
  return parseBlocks(lines, 0, { cells: 0, room, noted: false }).join('');
}
