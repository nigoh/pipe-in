// パネルのスクリプトを動かすための、手で書いた小さな偽物の DOM。外のライブラリは使わない。
// HTML を読んで木にし、スクリプトが使うもの（querySelector(All)・closest・getAttribute・setAttribute・classList・hidden・
// focus・addEventListener・innerHTML・postMessage）だけを持つ。スクリプトが使う操作を足したら、ここも足す。
// D0019 で足したもの：入力欄の value・選択範囲（selectionStart/End・setSelectionRange）、scrollTop/scrollLeft（枠の高さが分かるときは範囲に収める）、
// 変換中の入力の知らせ（compositionstart/end・input）、枠の高さを決める layout（BootOptions）、closest('[hidden]') で隠れているかを見る道。
// D0025 で足したもの（5 つ）：
// - セレクタが本物の SyntaxError になる形（閉じていない引用符・引用符のない値に引用符・識別子でない値・あまった文字）で、同じ SyntaxError を投げる。
//   名前を連ねたセレクタ（'[data-x="' + name + '"]'）が、名前に " が入ると壊れることを、テストで見つけられるようにするため。
//   引用符の中は \ で逃がせる（[data-x="a\"b"]）。かんたんな書き方だけを持つ（子孫・子の組み合わせ・[a~=b] などは SyntaxError にする。偽物が未対応）。
// - offsetTop・offsetHeight（既定 0。layout が決める）。選んだ行を枠の中へ寄せる動きを試すため。
// - hidden にした節の中の枠は、縦横のスクロール位置を 0 に戻す（本物の display: none と同じ。戻しても元には戻らない）。
// - hidden の中（自分か祖先に hidden がある節）では、offsetTop・offsetHeight・scrollHeight・clientHeight が 0 になり、scrollTop・scrollLeft に書いても残らない
//   （本物の display: none と同じ。見えていないあいだに寄せても空振りになる。見せると layout の大きさに戻る）。
//   「見えていないあいだは寄せず、見えたときに寄せる」動き（AC-62）が、起動時（まだ見えていない）に寄せて使い切る実装を見分けるため。
// - focus() は、hidden の中の節と disabled の要素には効かない（activeElement は替わらない。本物と同じ）。
//   「焦点が効かずに落ちる先」へ移す動き（AC-61）が、focus() のあとで調べる書き方でも、前もって調べる書き方でも同じに試せるようにするため。
import vm from 'node:vm';

const VOID_TAGS = new Set(['meta', 'br', 'hr', 'img', 'input', 'link']);

function unescapeAttr(value: string): string {
  return value
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

export interface FakeEvent {
  type: string;
  target: FakeNode;
  key?: string;
  /** 変換中（IME）の入力か（input・compositionupdate などに付く） */
  isComposing?: boolean;
  /** 入力された文字（input・compositionend に付く） */
  data?: string;
  /** wheel・click・keydown に付く修飾キー（D0019-AC-79：Ctrl＋ホイールで図を拡大縮小する） */
  ctrlKey?: boolean;
  metaKey?: boolean;
  /** wheel の縦の量（上へ回すと負） */
  deltaY?: number;
  defaultPrevented: boolean;
  preventDefault(): void;
}
type Listener = (event: FakeEvent) => void;

/** 文字の節。 */
export class FakeText {
  parent: FakeNode | null = null;
  text: string;
  constructor(text: string) {
    this.text = text;
  }
}

interface SimpleSelector {
  tag: string | null;
  classes: string[];
  attrs: { name: string; value: string | null }[];
}

// CSS の識別子（引用符のない属性の値）。数字で始まるもの（[a=1]）は本物でも SyntaxError。\ の逃がしは使える。
const CSS_ESCAPE = String.raw`\\(?:[0-9a-fA-F]{1,6}[ \t\n\r\f]?|[^\n\r\f0-9a-fA-F])`;
const IDENT_CHAR = String.raw`(?:[\w\u0080-￿-]|${CSS_ESCAPE})`;
const IDENT_START = String.raw`(?:[A-Za-z_\u0080-￿]|${CSS_ESCAPE})`;
const IDENT = String.raw`(?:--${IDENT_CHAR}*|-?${IDENT_START}${IDENT_CHAR}*)`;
// 引用符つきの値。中に改行は置けず、同じ引用符は \ で逃がす
const DOUBLE_QUOTED = String.raw`"((?:[^"\\\n\r\f]|\\[\s\S])*)"`;
const SINGLE_QUOTED = String.raw`'((?:[^'\\\n\r\f]|\\[\s\S])*)'`;
// 1 つの属性 [名前] か [名前=値]。1 番が名前、2・3 番が引用符つきの値、4 番が引用符のない値。後ろに余った文字があれば合わない
const TAG_RE = /[A-Za-z][\w-]*/y;
const CLASS_RE = /\.([\w-]+)/y;
const ATTR_RE = new RegExp(String.raw`\[\s*([\w:-]+)\s*(?:=\s*(?:${DOUBLE_QUOTED}|${SINGLE_QUOTED}|(${IDENT}))\s*)?\]`, 'y');

function selectorError(selector: string): SyntaxError {
  return new SyntaxError(`偽物の DOM が扱えないセレクタ（本物でも SyntaxError か、偽物が未対応）: ${selector}`);
}

/** 値の中の \ の逃がしを戻す（\" → "、\\ → \、\26 → &、行の続き \改行 → なし） */
function cssUnescape(raw: string): string {
  return raw.replace(
    /\\(?:([0-9a-fA-F]{1,6})[ \t\n\r\f]?|(\r\n|[\n\r\f])|([\s\S]))/g,
    (_all: string, hex: string | undefined, newline: string | undefined, char: string | undefined) => {
      if (hex !== undefined) {
        const code = parseInt(hex, 16);
        return code === 0 || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff) ? '�' : String.fromCodePoint(code);
      }
      return newline !== undefined ? '' : (char ?? '');
    },
  );
}

/** 「,」で並べたものを分ける。引用符の中の「,」では分けない（[data-x="a,b"]） */
function splitSelectorList(selector: string): string[] {
  const parts: string[] = [];
  let quote: string | null = null;
  let start = 0;
  for (let i = 0; i < selector.length; i++) {
    const c = selector[i];
    if (c === '\\') i += 1;
    else if (quote !== null) {
      if (c === quote) quote = null;
    } else if (c === '"' || c === "'") quote = c;
    else if (c === ',') {
      parts.push(selector.slice(start, i));
      start = i + 1;
    }
  }
  parts.push(selector.slice(start));
  return parts;
}

/** タグ・.クラス・[属性]・[属性=値] の組み合わせ 1 つ。子孫・子の組み合わせは使わない（スクリプトが使っていない） */
function parseCompound(text: string, selector: string): SimpleSelector {
  if (text === '') throw selectorError(selector);
  const simple: SimpleSelector = { tag: null, classes: [], attrs: [] };
  let pos = 0;
  TAG_RE.lastIndex = 0;
  const tag = TAG_RE.exec(text);
  if (tag !== null) {
    simple.tag = tag[0].toLowerCase();
    pos = TAG_RE.lastIndex;
  }
  while (pos < text.length) {
    CLASS_RE.lastIndex = pos;
    const cls = CLASS_RE.exec(text);
    if (cls !== null) {
      simple.classes.push(cls[1]);
      pos = CLASS_RE.lastIndex;
      continue;
    }
    ATTR_RE.lastIndex = pos;
    const attr = ATTR_RE.exec(text);
    if (attr === null) throw selectorError(selector);
    const value = attr[2] ?? attr[3] ?? attr[4];
    simple.attrs.push({ name: attr[1], value: value === undefined ? null : cssUnescape(value) });
    pos = ATTR_RE.lastIndex;
  }
  return simple;
}

/** 本物の querySelector が SyntaxError にするセレクタは、同じ SyntaxError にする（木に合う節が無くても、呼んだ時点で投げる） */
function parseSelector(selector: string): SimpleSelector[] {
  return splitSelectorList(selector).map((part) => parseCompound(part.trim(), selector));
}

/** 要素（と文書の根）。 */
export class FakeNode {
  parent: FakeNode | null = null;
  children: (FakeNode | FakeText)[] = [];
  private readonly listeners = new Map<string, Listener[]>();
  /** layout が決めた大きさ・位置（既定 0）。読むときは下の getter を通る：hidden の中では 0 になる（本物の display: none と同じ） */
  private readonly sizes = { scrollHeight: 0, clientHeight: 0, offsetTop: 0, offsetHeight: 0 };
  get scrollHeight(): number {
    return this.isHidden() ? 0 : this.sizes.scrollHeight;
  }
  set scrollHeight(value: number) {
    this.sizes.scrollHeight = value;
  }
  get clientHeight(): number {
    return this.isHidden() ? 0 : this.sizes.clientHeight;
  }
  set clientHeight(value: number) {
    this.sizes.clientHeight = value;
  }
  /** 親の枠の中での位置と高さ（既定 0。layout が決める。選んだ行を枠の中へ寄せる動きを試すため） */
  get offsetTop(): number {
    return this.isHidden() ? 0 : this.sizes.offsetTop;
  }
  set offsetTop(value: number) {
    this.sizes.offsetTop = value;
  }
  get offsetHeight(): number {
    return this.isHidden() ? 0 : this.sizes.offsetHeight;
  }
  set offsetHeight(value: number) {
    this.sizes.offsetHeight = value;
  }
  disabledFlag = false;
  /** 入力欄の中身（本物と同じく、代入すると選択範囲は末尾に移る） */
  private text = '';
  selectionStart = 0;
  selectionEnd = 0;
  private top = 0;
  private left = 0;

  /** 自分か祖先に hidden がある（本物では display: none）。大きさは 0、スクロール位置は持てず、焦点も移らない */
  private isHidden(): boolean {
    for (let n: FakeNode | null = this; n !== null; n = n.parent) if (n.attrs.has('hidden')) return true;
    return false;
  }

  /** 縦のスクロール位置。枠の高さ（scrollHeight・clientHeight）が分かるときは 0〜最大に収める（本物の枠と同じ）。hidden の中では書いても残らない */
  get scrollTop(): number {
    return this.top;
  }
  set scrollTop(value: number) {
    if (this.isHidden()) return;
    const wanted = Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0;
    this.top = this.scrollHeight > 0 ? Math.min(wanted, Math.max(0, this.scrollHeight - this.clientHeight)) : wanted;
  }
  /** 横のスクロール位置。hidden の中では書いても残らない */
  get scrollLeft(): number {
    return this.left;
  }
  set scrollLeft(value: number) {
    if (this.isHidden()) return;
    this.left = value;
  }

  get value(): string {
    return this.text;
  }
  set value(value: string) {
    this.text = String(value);
    this.selectionStart = this.selectionEnd = this.text.length;
  }
  setSelectionRange(start: number, end: number): void {
    this.selectionStart = Math.min(Math.max(0, start), this.text.length);
    this.selectionEnd = Math.min(Math.max(start, end), this.text.length);
  }

  readonly tagName: string;
  readonly attrs: Map<string, string>;
  private readonly doc: FakeDocument | null;

  // node の「型を消すだけ」の読み込みでは、引数に public を付ける書き方（パラメータプロパティ）が使えない
  constructor(tagName: string, attrs: Map<string, string>, doc: FakeDocument | null) {
    this.tagName = tagName;
    this.attrs = attrs;
    this.doc = doc;
  }

  private get document(): FakeDocument {
    return this.doc ?? (this as unknown as FakeDocument);
  }

  getAttribute(name: string): string | null {
    return this.attrs.get(name) ?? null;
  }
  setAttribute(name: string, value: string): void {
    this.attrs.set(name, String(value));
    if (name === 'hidden') this.loseScroll();
  }
  removeAttribute(name: string): void {
    this.attrs.delete(name);
  }
  hasAttribute(name: string): boolean {
    return this.attrs.has(name);
  }

  get hidden(): boolean {
    return this.attrs.has('hidden');
  }
  set hidden(value: boolean) {
    if (value) {
      this.attrs.set('hidden', '');
      this.loseScroll();
    } else this.attrs.delete('hidden');
  }

  /** 隠した（display: none にした）節の中の枠は、縦横のスクロール位置を失う（本物と同じ）。見せ直しても元の位置には戻らない */
  private loseScroll(): void {
    this.top = 0;
    this.left = 0;
    for (const child of this.children) if (child instanceof FakeNode) child.loseScroll();
  }
  get disabled(): boolean {
    return this.attrs.has('disabled');
  }

  get classList() {
    const node = this;
    const read = (): string[] => (node.attrs.get('class') ?? '').split(/\s+/).filter((c) => c !== '');
    const write = (list: string[]): void => {
      node.attrs.set('class', list.join(' '));
    };
    return {
      contains: (name: string): boolean => read().includes(name),
      add: (name: string): void => {
        const list = read();
        if (!list.includes(name)) write([...list, name]);
      },
      remove: (name: string): void => write(read().filter((c) => c !== name)),
      toggle: (name: string, force?: boolean): boolean => {
        const list = read();
        const on = force ?? !list.includes(name);
        if (on && !list.includes(name)) write([...list, name]);
        if (!on) write(list.filter((c) => c !== name));
        return on;
      },
    };
  }

  private matchesAny(list: SimpleSelector[]): boolean {
    return list.some((s) => {
      if (s.tag !== null && s.tag !== this.tagName) return false;
      const classes = (this.attrs.get('class') ?? '').split(/\s+/);
      if (!s.classes.every((c) => classes.includes(c))) return false;
      return s.attrs.every((a) => {
        const v = this.attrs.get(a.name);
        return v !== undefined && (a.value === null || v === a.value);
      });
    });
  }

  matches(selector: string): boolean {
    return this.matchesAny(parseSelector(selector));
  }

  closest(selector: string): FakeNode | null {
    const list = parseSelector(selector);
    for (let n: FakeNode | null = this; n !== null; n = n.parent) {
      if (n.tagName !== '#document' && n.matchesAny(list)) return n;
    }
    return null;
  }

  querySelectorAll(selector: string): FakeNode[] {
    const list = parseSelector(selector);
    const found: FakeNode[] = [];
    const walk = (n: FakeNode): void => {
      for (const c of n.children) {
        if (c instanceof FakeNode) {
          if (c.matchesAny(list)) found.push(c);
          walk(c);
        }
      }
    };
    walk(this);
    return found;
  }
  querySelector(selector: string): FakeNode | null {
    return this.querySelectorAll(selector)[0] ?? null;
  }

  get textContent(): string {
    return this.children.map((c) => (c instanceof FakeText ? c.text : c.textContent)).join('');
  }
  /** 子を、1つの文字に替える（本物の textContent と同じ）。 */
  set textContent(value: string) {
    const node = new FakeText(String(value));
    node.parent = this;
    this.children = value === '' ? [] : [node];
  }

  /** この節に付いた動き（Web Animations の getAnimations の偽物）。is-new が付いている間だけ1つ持つ。 */
  private animation: FakeAnimation | null = null;
  /** getAnimations を持たない環境（document.noAnimations）では undefined（スクリプトは有無を見分ける） */
  get getAnimations(): (() => FakeAnimation[]) | undefined {
    if (this.document.noAnimations) return undefined;
    return () => {
      const flashing = (this.attrs.get('class') ?? '').split(/\s+/).includes('is-new');
      if (!flashing) this.animation = null;
      else if (this.animation === null) this.animation = { currentTime: 0 };
      return this.animation === null ? [] : [this.animation];
    };
  }

  set innerHTML(html: string) {
    this.children = [];
    parseInto(this, html, this.document);
  }

  /** 本物と同じく、hidden の中の節と disabled の要素には効かない（activeElement は替わらない） */
  focus(): void {
    if (this.disabled || this.isHidden()) return;
    this.document.activeElement = this;
  }

  addEventListener(type: string, listener: Listener): void {
    const list = this.listeners.get(type) ?? [];
    list.push(listener);
    this.listeners.set(type, list);
  }

  /** この節から文書の根へ、泡のように上がりながらリスナーを呼ぶ。preventDefault が呼ばれたかを返す。 */
  dispatch(
    type: string,
    extra: { key?: string; isComposing?: boolean; data?: string; ctrlKey?: boolean; metaKey?: boolean; deltaY?: number } = {},
  ): FakeEvent {
    const event: FakeEvent = {
      type,
      target: this,
      key: extra.key,
      isComposing: extra.isComposing,
      data: extra.data,
      ctrlKey: extra.ctrlKey ?? false,
      metaKey: extra.metaKey ?? false,
      deltaY: extra.deltaY ?? 0,
      defaultPrevented: false,
      preventDefault() {
        event.defaultPrevented = true;
      },
    };
    for (let n: FakeNode | null = this; n !== null; n = n.parent) {
      for (const l of n.listeners.get(type) ?? []) l(event);
    }
    return event;
  }
}

/** layout が節ごとに決める大きさ・位置（無いものは 0）。offsetTop・offsetHeight は D0025 で足した */
export interface LayoutSize {
  scrollHeight?: number;
  clientHeight?: number;
  offsetTop?: number;
  offsetHeight?: number;
}

/** Web Animations の Animation の偽物（currentTime だけ）。 */
export interface FakeAnimation {
  currentTime: number | null;
}

/** 文書。根でもある。 */
export class FakeDocument extends FakeNode {
  activeElement: FakeNode | null = null;
  /** 'visible' か 'hidden'（D0017：見えていないあいだは数え上げを止める） */
  visibilityState: 'visible' | 'hidden' = 'visible';
  /** true なら、どの節も getAnimations を持たない */
  noAnimations = false;
  /** 作られた節の枠の高さ・位置を決める（無ければ 0 のまま）。スクロールの位置や末尾追従、選んだ行を枠の中へ寄せる動きを試すときに使う */
  layout: ((node: FakeNode) => LayoutSize | null | undefined) | null = null;
  constructor() {
    super('#document', new Map(), null);
  }
}

function parseInto(parent: FakeNode, html: string, doc: FakeDocument): void {
  const tagRe = /<(\/?)([A-Za-z][\w:-]*)((?:[^>"']|"[^"]*"|'[^']*')*?)(\/?)>/g;
  const stack: FakeNode[] = [parent];
  let last = 0;
  const addText = (text: string): void => {
    if (text === '') return;
    const top = stack[stack.length - 1];
    const node = new FakeText(unescapeAttr(text));
    node.parent = top;
    top.children.push(node);
  };
  for (let m = tagRe.exec(html); m !== null; m = tagRe.exec(html)) {
    addText(html.slice(last, m.index));
    last = tagRe.lastIndex;
    const [, closing, rawName, rawAttrs, selfClose] = m;
    const name = rawName.toLowerCase();
    if (closing === '/') {
      for (let i = stack.length - 1; i > 0; i--) {
        if (stack[i].tagName === name) {
          stack.length = i;
          break;
        }
      }
      continue;
    }
    const attrs = new Map<string, string>();
    const attrRe = /([^\s=/>"']+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'))?/g;
    for (let a = attrRe.exec(rawAttrs); a !== null; a = attrRe.exec(rawAttrs)) {
      attrs.set(a[1], unescapeAttr(a[2] ?? a[3] ?? ''));
    }
    const node = new FakeNode(name, attrs, doc);
    const size = doc.layout?.(node);
    if (size) {
      node.scrollHeight = size.scrollHeight ?? 0;
      node.clientHeight = size.clientHeight ?? 0;
      node.offsetTop = size.offsetTop ?? 0;
      node.offsetHeight = size.offsetHeight ?? 0;
    }
    const top = stack[stack.length - 1];
    node.parent = top;
    top.children.push(node);
    if (selfClose !== '/' && !VOID_TAGS.has(name)) stack.push(node);
  }
  addText(html.slice(last));
}

/** 完成した HTML 全体（renderPanelHtml の出力）から、<script nonce> の中身を取り出す。 */
export function extractScript(html: string): string {
  const m = /<script nonce="[^"]*">([\s\S]*?)<\/script>/.exec(html);
  if (!m) throw new Error('<script nonce> がない');
  return m[1];
}

export interface BootOptions {
  /** prefers-reduced-motion: reduce に合う（既定 false＝no-preference） */
  reducedMotion?: boolean;
  /** window.matchMedia を持たない環境（スクリプトは安全側で「動きを減らす」と見る） */
  noMatchMedia?: boolean;
  /** getAnimations を持たない環境 */
  noAnimations?: boolean;
  /** 起動時の visibilityState（既定 'visible'） */
  visibility?: 'visible' | 'hidden';
  /** 偽の時計の始まり（ミリ秒。既定 1.7e12） */
  startMs?: number;
  /** 作られた節の枠の高さ・位置（scrollHeight・clientHeight・offsetTop・offsetHeight）を決める。起動時と render のあとに作られる節のすべてに当てる */
  layout?: FakeDocument['layout'];
}

export interface PanelHarness {
  doc: FakeDocument;
  /** 偽の時計の今（Date.now() が返す値） */
  now(): number;
  /** 偽の時計を ms 進め、期限の来た setInterval・setTimeout を、期限の順に呼ぶ */
  advance(ms: number): void;
  /** 偽の時計を（戻すことも含めて）ms の値にする。タイマーは呼ばない */
  setNow(ms: number): void;
  /** 登録されている setInterval を、時計を動かさずに1回ずつ呼ぶ（時計が戻ったあとの表示を見るため） */
  tick(): void;
  /** visibilityState を替え、document に visibilitychange を届ける */
  setVisibility(state: 'visible' | 'hidden'): void;
  /** 今動いている（clearInterval されていない）setInterval の数 */
  activeIntervals(): number;
  /** これまでに setInterval で作られた数 */
  createdIntervals(): number;
  /** 節の文字 */
  text(el: FakeNode): string;
  /** スクリプトが拡張へ送ったメッセージ（postMessage に渡されたもの） */
  posted: unknown[];
  root: FakeNode;
  /** window の message を受ける（拡張からの render を送る） */
  send(data: unknown): void;
  /** data-reasons が id の節 */
  node(id: string): FakeNode;
  section(id: string): FakeNode;
  /** data-loop が id の矢印 */
  loop(id: string): FakeNode;
  /** 入力欄に文字を打ったことにする：value を替え（選択範囲は末尾）、input を届ける。変換中なら composing を真に */
  typeText(el: FakeNode, text: string, composing?: boolean): void;
}

/** renderPanelHtml の出力を偽物の DOM に読み込み、本物の SCRIPT を node:vm で動かす。 */
export function bootPanel(html: string, opts: BootOptions = {}): PanelHarness {
  const script = extractScript(html);
  const body = html.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<style[\s\S]*?<\/style>/g, '');
  const doc = new FakeDocument();
  doc.layout = opts.layout ?? null;
  parseInto(doc, body, doc);
  doc.visibilityState = opts.visibility ?? 'visible';
  doc.noAnimations = opts.noAnimations === true;
  const posted: unknown[] = [];
  const windowListeners = new Map<string, Listener[]>();

  // 偽の時計とタイマー（本物の時間は使わない。sleep しない）
  let nowMs = opts.startMs ?? 1_700_000_000_000;
  interface Timer {
    id: number;
    fn: () => void;
    every: number | null;
    due: number;
  }
  const timers = new Map<number, Timer>();
  let nextId = 1;
  let created = 0;
  const add = (fn: () => void, ms: number, repeat: boolean): number => {
    const id = nextId++;
    timers.set(id, { id, fn, every: repeat ? Math.max(1, Number(ms) || 0) : null, due: nowMs + Math.max(0, Number(ms) || 0) });
    return id;
  };
  const sandboxApi = {
    Date: { now: () => nowMs },
    setInterval: (fn: () => void, ms: number): number => {
      created++;
      return add(fn, ms, true);
    },
    clearInterval: (id: number): void => void timers.delete(id),
    setTimeout: (fn: () => void, ms: number): number => add(fn, ms, false),
    clearTimeout: (id: number): void => void timers.delete(id),
  };
  const mediaMatches = (query: string): boolean => {
    const reduce = /:\s*reduce\b/.test(query);
    const noPreference = /:\s*no-preference\b/.test(query);
    if (reduce) return opts.reducedMotion === true;
    if (noPreference) return opts.reducedMotion !== true;
    return false;
  };
  const window = {
    addEventListener(type: string, listener: Listener): void {
      windowListeners.set(type, [...(windowListeners.get(type) ?? []), listener]);
    },
    ...(opts.noMatchMedia ? {} : { matchMedia: (query: string) => ({ media: query, matches: mediaMatches(query) }) }),
  };
  const sandbox = {
    document: doc,
    window,
    ...sandboxApi,
    // vm の中で作られたオブジェクトは、こちらの Object と別物（deepEqual が合わない）なので、JSON を通して写す
    acquireVsCodeApi: () => ({ postMessage: (m: unknown) => posted.push(JSON.parse(JSON.stringify(m))) }),
    console,
  };
  vm.runInNewContext(script, sandbox);
  const root = doc.querySelector('.root');
  if (root === null) throw new Error('.root がない');
  const byAttr = (name: string, id: string): FakeNode => {
    const found = doc.querySelectorAll(`[${name}]`).find((n) => n.getAttribute(name) === id);
    if (found === undefined) throw new Error(`[${name}="${id}"] がない`);
    return found;
  };
  return {
    doc,
    now: () => nowMs,
    advance(ms) {
      const target = nowMs + ms;
      for (;;) {
        const due = [...timers.values()].filter((t) => t.due <= target).sort((a, b) => a.due - b.due || a.id - b.id)[0];
        if (due === undefined) break;
        nowMs = Math.max(nowMs, due.due);
        if (due.every === null) timers.delete(due.id);
        else due.due += due.every;
        due.fn();
      }
      nowMs = target;
    },
    setNow(ms) {
      nowMs = ms;
      for (const t of timers.values()) t.due = Math.max(t.due, nowMs); // 時計が戻ったあと、過ぎた期限を溜めて連続で呼ばない
    },
    tick() {
      for (const t of [...timers.values()]) if (t.every !== null) t.fn();
    },
    setVisibility(state) {
      doc.visibilityState = state;
      doc.dispatch('visibilitychange');
    },
    activeIntervals: () => [...timers.values()].filter((t) => t.every !== null).length,
    createdIntervals: () => created,
    text: (el) => el.textContent,
    posted,
    root,
    send(data) {
      for (const l of windowListeners.get('message') ?? []) l({ data } as unknown as FakeEvent);
    },
    node: (id) => byAttr('data-reasons', id),
    section: (id) => byAttr('data-reasons-for', id),
    loop: (id) => byAttr('data-loop', id),
    typeText(el, text, composing = false) {
      el.value = text;
      el.dispatch('input', { isComposing: composing, data: text });
    },
  };
}
