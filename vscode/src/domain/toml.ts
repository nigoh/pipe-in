// pipe.toml を読む小さな TOML の読み手。pipe-in のパイプで使う書き方だけを読む：
// 表・表の配列・その下の表、文字列（基本・リテラル・複数行）、整数・小数、真偽、配列。
// インラインの表・日付など、ほかの書き方は「読めない」と行番号つきで知らせる（ライブラリに頼らないため）。

export type TomlValue = string | number | boolean | TomlValue[] | TomlTable;
export interface TomlTable {
  [key: string]: TomlValue;
}

export class TomlError extends Error {}

const BARE_KEY = /[A-Za-z0-9_-]/;

class Reader {
  pos = 0;
  line = 1;
  readonly text: string;
  constructor(text: string) {
    this.text = text;
  }

  fail(message: string): never {
    throw new TomlError(`${this.line} 行目: ${message}`);
  }
  peek(n = 0): string {
    return this.text[this.pos + n] ?? '';
  }
  startsWith(s: string): boolean {
    return this.text.startsWith(s, this.pos);
  }
  next(): string {
    const c = this.text[this.pos++] ?? '';
    if (c === '\n') this.line++;
    return c;
  }
  eof(): boolean {
    return this.pos >= this.text.length;
  }
  skipSpaces(): void {
    while (this.peek() === ' ' || this.peek() === '\t') this.pos++;
  }
  skipComment(): void {
    if (this.peek() === '#') while (!this.eof() && this.peek() !== '\n') this.pos++;
  }
  /** 空白・改行・コメントを飛ばす（配列の中や、行と行のあいだ） */
  skipBlank(): void {
    for (;;) {
      this.skipSpaces();
      this.skipComment();
      if (this.peek() === '\r') this.pos++;
      if (this.peek() === '\n') { this.next(); continue; }
      return;
    }
  }
  /** 値のあとは、行の終わり（コメントは可）でなければならない */
  endOfLine(): void {
    this.skipSpaces();
    this.skipComment();
    if (this.peek() === '\r') this.pos++;
    if (this.eof()) return;
    if (this.peek() !== '\n') this.fail(`行の終わりに余分な文字があります（${JSON.stringify(this.peek())}）`);
    this.next();
  }
}

function parseKeyPart(r: Reader): string {
  r.skipSpaces();
  const c = r.peek();
  if (c === '"') return parseBasicString(r);
  if (c === "'") return parseLiteralString(r);
  let key = '';
  while (BARE_KEY.test(r.peek()) && r.peek() !== '') key += r.next();
  if (!key) r.fail('名前（キー）がありません');
  return key;
}

function parseKey(r: Reader): string[] {
  const parts = [parseKeyPart(r)];
  r.skipSpaces();
  while (r.peek() === '.') {
    r.next();
    parts.push(parseKeyPart(r));
    r.skipSpaces();
  }
  return parts;
}

function parseEscape(r: Reader): string {
  const c = r.next();
  switch (c) {
    case 'b': return '\b';
    case 't': return '\t';
    case 'n': return '\n';
    case 'f': return '\f';
    case 'r': return '\r';
    case '"': return '"';
    case '\\': return '\\';
    case 'u':
    case 'U': {
      const len = c === 'u' ? 4 : 8;
      const hex = r.text.slice(r.pos, r.pos + len);
      if (!/^[0-9A-Fa-f]+$/.test(hex) || hex.length !== len) r.fail('\\u のあとの16進数が正しくありません');
      r.pos += len;
      return String.fromCodePoint(parseInt(hex, 16));
    }
    default:
      return r.fail(`使えないエスケープ（\\${c}）です`);
  }
}

function parseBasicString(r: Reader): string {
  if (r.startsWith('"""')) {
    r.pos += 3;
    if (r.peek() === '\r') r.pos++;
    if (r.peek() === '\n') r.next();
    let out = '';
    for (;;) {
      if (r.eof()) r.fail('複数行の文字列（"""）が閉じていません');
      if (r.startsWith('"""')) { r.pos += 3; return out; }
      const c = r.next();
      if (c === '\\') {
        if (r.peek() === '\n' || r.peek() === '\r' || r.peek() === ' ') {
          while (/[\s]/.test(r.peek()) && !r.eof()) r.next();
          continue;
        }
        out += parseEscape(r);
      } else if (c !== '\r') out += c;
    }
  }
  r.next();
  let out = '';
  for (;;) {
    if (r.eof() || r.peek() === '\n') r.fail('文字列（"）が閉じていません');
    const c = r.next();
    if (c === '"') return out;
    out += c === '\\' ? parseEscape(r) : c;
  }
}

function parseLiteralString(r: Reader): string {
  if (r.startsWith("'''")) {
    r.pos += 3;
    if (r.peek() === '\r') r.pos++;
    if (r.peek() === '\n') r.next();
    let out = '';
    for (;;) {
      if (r.eof()) r.fail("複数行の文字列（'''）が閉じていません");
      if (r.startsWith("'''")) { r.pos += 3; return out; }
      const c = r.next();
      if (c !== '\r') out += c;
    }
  }
  r.next();
  let out = '';
  for (;;) {
    if (r.eof() || r.peek() === '\n') r.fail("文字列（'）が閉じていません");
    const c = r.next();
    if (c === "'") return out;
    out += c;
  }
}

function parseValue(r: Reader): TomlValue {
  r.skipSpaces();
  const c = r.peek();
  if (c === '"') return parseBasicString(r);
  if (c === "'") return parseLiteralString(r);
  if (c === '[') {
    r.next();
    const items: TomlValue[] = [];
    for (;;) {
      r.skipBlank();
      if (r.peek() === ']') { r.next(); return items; }
      items.push(parseValue(r));
      r.skipBlank();
      if (r.peek() === ',') { r.next(); continue; }
      if (r.peek() === ']') { r.next(); return items; }
      r.fail('配列の区切り（, か ]）がありません');
    }
  }
  if (c === '{') r.fail('インラインの表（{ … }）は、作業台では読めません。[表] の形で書いてください');
  if (r.startsWith('true')) { r.pos += 4; return true; }
  if (r.startsWith('false')) { r.pos += 5; return false; }
  const m = /^[+-]?(\d[\d_]*)(\.\d[\d_]*)?([eE][+-]?\d+)?/.exec(r.text.slice(r.pos));
  if (m && !/^[\d-]{4}-/.test(r.text.slice(r.pos))) {
    r.pos += m[0].length;
    const n = Number(m[0].replace(/_/g, ''));
    if (Number.isNaN(n)) r.fail('数として読めません');
    return n;
  }
  return r.fail('値として読めません（文字列・数・真偽・配列のどれか）');
}

const isTable = (v: TomlValue | undefined): v is TomlTable => typeof v === 'object' && v !== null && !Array.isArray(v);

/** root から path をたどる。途中が表の配列なら、その最後の要素へ進む。 */
function walk(r: Reader, root: TomlTable, path: string[]): TomlTable {
  let t = root;
  for (const key of path) {
    const v = t[key];
    if (v === undefined) {
      const created: TomlTable = {};
      t[key] = created;
      t = created;
    } else if (Array.isArray(v)) {
      const last = v[v.length - 1];
      if (!isTable(last)) r.fail(`「${key}」は表の配列ではありません`);
      t = last;
    } else if (isTable(v)) {
      t = v;
    } else {
      r.fail(`「${key}」はもう値として使われています`);
    }
  }
  return t;
}

export function parseToml(text: string): TomlTable {
  const r = new Reader(text);
  const root: TomlTable = {};
  let current = root;
  const defined = new Set<TomlTable>();
  for (;;) {
    r.skipBlank();
    if (r.eof()) return root;
    if (r.peek() === '[') {
      r.next();
      const isArray = r.peek() === '[';
      if (isArray) r.next();
      const path = parseKey(r);
      if (r.next() !== ']' || (isArray && r.next() !== ']')) r.fail(isArray ? '[[ … ]] が閉じていません' : '[ … ] が閉じていません');
      const parent = walk(r, root, path.slice(0, -1));
      const last = path[path.length - 1]!;
      if (isArray) {
        const existing = parent[last];
        if (existing !== undefined && !Array.isArray(existing)) r.fail(`「${last}」は表の配列ではありません`);
        const table: TomlTable = {};
        if (Array.isArray(existing)) existing.push(table);
        else parent[last] = [table];
        current = table;
      } else {
        const existing = parent[last];
        if (existing !== undefined && !isTable(existing)) r.fail(`「${last}」はもう値として使われています`);
        const table = isTable(existing) ? existing : {};
        if (defined.has(table)) r.fail(`[${path.join('.')}] が二度出てきます`);
        parent[last] = table;
        defined.add(table);
        current = table;
      }
      r.endOfLine();
      continue;
    }
    const path = parseKey(r);
    r.skipSpaces();
    if (r.next() !== '=') r.fail('名前のあとに = がありません');
    const value = parseValue(r);
    const target = walk(r, current, path.slice(0, -1));
    const last = path[path.length - 1]!;
    if (last in target) r.fail(`「${path.join('.')}」が二度書かれています`);
    target[last] = value;
    r.endOfLine();
  }
}
