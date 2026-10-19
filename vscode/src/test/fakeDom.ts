// パネルのスクリプトを動かすための、手で書いた小さな偽物の DOM。外のライブラリは使わない。
// HTML を読んで木にし、スクリプトが使うもの（querySelector(All)・closest・getAttribute・setAttribute・classList・hidden・
// focus・addEventListener・innerHTML・postMessage）だけを持つ。スクリプトが使う操作を足したら、ここも足す。
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
  scrollTop = 0;
  scrollHeight = 0;
  clientHeight = 0;
  disabledFlag = false;

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
  dispatch(type: string, extra: { key?: string } = {}): FakeEvent {
    const event: FakeEvent = {
      type,
      target: this,
      key: extra.key,
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

/** 文書。根でもある。 */
export class FakeDocument extends FakeNode {
  activeElement: FakeNode | null = null;
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

export interface PanelHarness {
  doc: FakeDocument;
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
}

/** renderPanelHtml の出力を偽物の DOM に読み込み、本物の SCRIPT を node:vm で動かす。 */
export function bootPanel(html: string): PanelHarness {
  const script = extractScript(html);
  const body = html.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<style[\s\S]*?<\/style>/g, '');
  const doc = new FakeDocument();
  parseInto(doc, body, doc);
  const posted: unknown[] = [];
  const windowListeners = new Map<string, Listener[]>();
  const window = {
    addEventListener(type: string, listener: Listener): void {
      windowListeners.set(type, [...(windowListeners.get(type) ?? []), listener]);
    },
  };
  const sandbox = {
    document: doc,
    window,
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
    posted,
    root,
    send(data) {
      for (const l of windowListeners.get('message') ?? []) l({ data } as unknown as FakeEvent);
    },
    node: (id) => byAttr('data-reasons', id),
    section: (id) => byAttr('data-reasons-for', id),
    loop: (id) => byAttr('data-loop', id),
  };
}
