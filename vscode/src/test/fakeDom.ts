// パネルのスクリプトを動かすための、手で書いた小さな偽物の DOM。外のライブラリは使わない。
// HTML を読んで木にし、スクリプトが使うもの（querySelector(All)・closest・getAttribute・setAttribute・classList・hidden・
// focus・addEventListener・innerHTML・postMessage）だけを持つ。スクリプトが使う操作を足したら、ここも足す。
// D0019 で足したもの：入力欄の value・選択範囲（selectionStart/End・setSelectionRange）、scrollTop/scrollLeft（枠の高さが分かるときは範囲に収める）、
// 変換中の入力の知らせ（compositionstart/end・input）、枠の高さを決める layout（BootOptions）、closest('[hidden]') で隠れているかを見る道。
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

function parseSelector(selector: string): SimpleSelector[] {
  // 「,」で並べたもの。子孫・子の組み合わせは使わない（スクリプトが使っていない）
  return selector.split(',').map((part) => {
    const text = part.trim();
    const simple: SimpleSelector = { tag: null, classes: [], attrs: [] };
    const re = /^[A-Za-z][\w-]*|\.[\w-]+|\[([\w:-]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\]]*)))?\]/g;
    let consumed = 0;
    for (let m = re.exec(text); m !== null; m = re.exec(text)) {
      if (m.index !== consumed) throw new Error(`偽物の DOM が扱えないセレクタ: ${selector}`);
      consumed = re.lastIndex;
      const token = m[0];
      if (token.startsWith('.')) simple.classes.push(token.slice(1));
      else if (token.startsWith('[')) simple.attrs.push({ name: m[1], value: m[2] ?? m[3] ?? m[4] ?? null });
      else simple.tag = token.toLowerCase();
    }
    if (consumed !== text.length || text === '') throw new Error(`偽物の DOM が扱えないセレクタ: ${selector}`);
    return simple;
  });
}

/** 要素（と文書の根）。 */
export class FakeNode {
  parent: FakeNode | null = null;
  children: (FakeNode | FakeText)[] = [];
  private readonly listeners = new Map<string, Listener[]>();
  scrollHeight = 0;
  clientHeight = 0;
  scrollLeft = 0;
  disabledFlag = false;
  /** 入力欄の中身（本物と同じく、代入すると選択範囲は末尾に移る） */
  private text = '';
  selectionStart = 0;
  selectionEnd = 0;
  private top = 0;

  /** 縦のスクロール位置。枠の高さ（scrollHeight・clientHeight）が分かるときは 0〜最大に収める（本物の枠と同じ） */
  get scrollTop(): number {
    return this.top;
  }
  set scrollTop(value: number) {
    const wanted = Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0;
    this.top = this.scrollHeight > 0 ? Math.min(wanted, Math.max(0, this.scrollHeight - this.clientHeight)) : wanted;
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
    if (value) this.attrs.set('hidden', '');
    else this.attrs.delete('hidden');
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

  matches(selector: string): boolean {
    return parseSelector(selector).some((s) => {
      if (s.tag !== null && s.tag !== this.tagName) return false;
      const classes = (this.attrs.get('class') ?? '').split(/\s+/);
      if (!s.classes.every((c) => classes.includes(c))) return false;
      return s.attrs.every((a) => {
        const v = this.attrs.get(a.name);
        return v !== undefined && (a.value === null || v === a.value);
      });
    });
  }

  closest(selector: string): FakeNode | null {
    for (let n: FakeNode | null = this; n !== null; n = n.parent) {
      if (n.tagName !== '#document' && n.matches(selector)) return n;
    }
    return null;
  }

  querySelectorAll(selector: string): FakeNode[] {
    const found: FakeNode[] = [];
    const walk = (n: FakeNode): void => {
      for (const c of n.children) {
        if (c instanceof FakeNode) {
          if (c.matches(selector)) found.push(c);
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

  focus(): void {
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
  /** 作られた節の枠の高さを決める（無ければ 0 のまま）。スクロールの位置や末尾追従を試すときに使う */
  layout: ((node: FakeNode) => { scrollHeight?: number; clientHeight?: number } | null | undefined) | null = null;
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
  /** 作られた節の枠の高さ（scrollHeight・clientHeight）を決める。起動時と render のあとに作られる節のすべてに当てる */
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
