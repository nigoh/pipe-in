// D0027：進み具合のページの JS を、Node の vm の中で動かすための台（テストの補助。本体には入らない）。
//
//   node tests/fixtures/live_page_harness.mjs   ← 標準入力に「場面」の JSON を渡す。結果の JSON を標準出力に書く。
//
// 場面（入力）:
//   html     build_page() の HTML 全体（<body> の骨組みを偽の DOM にし、最初の <script> の中身を動かす）
//   now      仮想の時計の始まり（ISO 8601。省くと 2026-10-17T02:00:00+00:00）
//   claude   "db"（既定）| "null"（claude.use("db") が null）| "undefined"（claude 自体が無い）| "use_rejects" | "use_throws" |
//            "use_undefined" | "doc_throws" | "onsnapshot_throws"
//   hidden   始めに document.hidden にするか（既定 false）
//   initial  購読した直後に（非同期で）届ける値。{"value": ...} | {"missing": true}。省くと何も届かない
//   steps    順に行う操作（下）
//   comments D0039：偽の claude.use("comments")。省くと use("comments") は null（前の版と同じ）。次のキーを持つ（すべて省ける）
//              use     "ok"（既定）| "null" | "rejects" | "throws" | "undefined"
//              can     "available"（既定）| "writers_only" | "no_session" | "off" | 任意の JSON 値 | {"$":"reject"} | {"$":"throw"} |
//                      {"$":"undefined"} | "pending"（settle_can で終わらせるまで返さない）
//              anchor  "ok"（既定）| "rejects" | "throws" | "not_an_object" | "pending"（settle_anchor で終わらせる）
//              send    "resolve"（既定）| "pending" | {"reject": 値} | {"reject_code": "claude_unavailable"} | "throws" |
//                      それらの配列（呼ぶたびに順に使い、最後のものを繰り返す）
//              anchorFor(el) は {path, x, y, token: "ANCHOR-TOKEN-<n>"} を発行する。sendToClaude は受けた anchor が発行したものそのものか
//              （anchor_issued）と、押した操作の中で呼ばれたか（in_gesture。await を挟むと偽）を記録する。
//
// 操作（steps の要素。結果の steps[i] に threw（投げた例外の文。無ければ null）と view が入る）:
//   {"op":"send","value":V}            db に値 V を届ける（snap.exists = true, snap.data() = V）
//   {"op":"send","missing":true}       snap.exists = false, snap.data() = undefined
//   {"op":"send_raw","what":W}         W = null | undefined | no_data | data_throws | data_function | number | string | exists_string
//   {"op":"error","message":M}         onSnapshot の error 側を呼ぶ
//   {"op":"advance","ms":N}            仮想の時計を N ms 進め、期限の来たタイマーを順に動かす
//   {"op":"set_now","at":ISO}          時計をその時刻にする（タイマーは動かさない。時計が戻る場面）
//   {"op":"hidden","value":B}          document.hidden を B にして visibilitychange を送る
//   {"op":"call","fn":NAME,"args":[…]} トップレベルの関数 NAME を呼ぶ（結果は result）
//   {"op":"query","selector":S}        S に合う要素の {tag, text, attrs, value, selection, disabled, shown, focused} を result に返す
//                                      （shown = 文書に付いていて、自分も祖先も hidden でない）
//   {"op":"click","selector":S,"times":1,"force":false}  S に合う最初の要素を times 回、続けて（同じ操作の中で）押す。force が偽なら、
//                                      disabled か hidden（自分か祖先）の要素には押さない（ブラウザと同じ）。押している間 gesture の旗が立つ。
//                                      result = {found, dispatched, skipped}。click は親へ伝わる（bubbles）
//   {"op":"input","selector":S,"value":V,"force":false}  S の .value を V にして input を送る（disabled・hidden には force なしで届かない）
//   {"op":"focus","selector":S}        S の要素を focus() する（見えない・disabled・focus できない要素には効かない）
//   {"op":"select","selector":S,"start":A,"end":B}  S の要素に setSelectionRange(A, B)
//   {"op":"focus_state"}               document.activeElement の {tag, class} を result に返す（何も無ければ body）
//   {"op":"settle","call":I,"how":"resolve"|{"reject":V}}  send: "pending" の I 番目の送信を終わらせる
//   {"op":"settle_can","call":I,"value":V}   can: "pending" の I 番目の canSendToClaude を V で終わらせる（{"$":"reject"} は reject）
//   {"op":"settle_anchor","call":I,"how":"resolve"|"reject"}  anchor: "pending" の I 番目の anchorFor を終わらせる
//   {"op":"set_can","value":V}         canSendToClaude が次に返す値を替える
//
// 値の中の NaN・Infinity は {"$":"NaN"}・{"$":"Infinity"}・{"$":"-Infinity"} と書く（JSON に書けないため）。結果も同じ書き方で返す。
//
// view（画面の様子）: lines（文字の節。順番どおり）・text（lines を改行でつないだもの）・tags（要素の種類ごとの数）・attrs（使われた属性名）・
//   created（createElement で作った要素の種類の一覧）・intervals（回っている setInterval の数）・timeouts・interval_ms・
//   html_insertions（innerHTML などに書こうとした回数）・hidden・now_ms・
//   shown_lines / shown_text（hidden の要素の中を除いた文字。画面に見える文字）
// 結果の最上位: comments {use_calls, can_calls, anchor_calls[{el_tag, el_class, attached}], sends[{text, anchor, anchor_issued, in_gesture, n, keys, argc}],
//   pending_sends, pending_can, pending_anchor}・dialogs（alert・confirm・prompt を呼んだ記録）

import fs from "node:fs";
import vm from "node:vm";

const VOID = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"]);

function decodeEntities(s) {
  return s.replace(/&(#x[0-9a-fA-F]+|#\d+|[a-zA-Z]+);/g, (m, e) => {
    if (e[0] === "#") {
      const code = e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      return Number.isFinite(code) && code <= 0x10ffff ? String.fromCodePoint(code) : m;
    }
    const table = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
    return Object.prototype.hasOwnProperty.call(table, e) ? table[e] : m;
  });
}

// ---- 偽の DOM -------------------------------------------------------------------------------------

const counters = { htmlInsertions: 0, created: [], alerts: [], dialogs: [] };
const focusState = { el: null };
const gesture = { active: false };
const world = { root: null, body: null };

class Node_ {
  constructor() {
    this.parentNode = null;
    this.childNodes = [];
    this._listeners = {};
  }
  get parentElement() {
    return this.parentNode && this.parentNode.nodeType === 1 ? this.parentNode : null;
  }
  get firstChild() {
    return this.childNodes[0] || null;
  }
  get lastChild() {
    return this.childNodes[this.childNodes.length - 1] || null;
  }
  get nextSibling() {
    if (!this.parentNode) return null;
    const i = this.parentNode.childNodes.indexOf(this);
    return this.parentNode.childNodes[i + 1] || null;
  }
  get previousSibling() {
    if (!this.parentNode) return null;
    const i = this.parentNode.childNodes.indexOf(this);
    return i > 0 ? this.parentNode.childNodes[i - 1] : null;
  }
  hasChildNodes() {
    return this.childNodes.length > 0;
  }
  contains(other) {
    for (let n = other; n; n = n.parentNode) if (n === this) return true;
    return false;
  }
  _detach() {
    if (this.parentNode) {
      const i = this.parentNode.childNodes.indexOf(this);
      if (i >= 0) this.parentNode.childNodes.splice(i, 1);
      this.parentNode = null;
    }
    // 動かした・外した要素（かその祖先）が focus を持っていたら、ブラウザと同じく focus を失う
    if (focusState.el && (this === focusState.el || this.contains(focusState.el))) focusState.el = null;
  }
  _nodes(items) {
    const out = [];
    for (const it of items) {
      if (it && it.nodeType === 11) out.push(...it.childNodes.slice());
      else if (it && typeof it === "object" && it.nodeType) out.push(it);
      else out.push(new Text_(String(it)));
    }
    return out;
  }
  _insert(nodes, index) {
    for (const n of nodes) {
      if (n === this || n.contains(this)) throw new Error("HierarchyRequestError");
      n._detach();
    }
    this.childNodes.splice(index, 0, ...nodes);
    for (const n of nodes) n.parentNode = this;
  }
  appendChild(node) {
    if (!node || !node.nodeType) throw new TypeError("appendChild: not a node");
    this._insert(this._nodes([node]), this.childNodes.length);
    return node;
  }
  append(...items) {
    this._insert(this._nodes(items), this.childNodes.length);
  }
  prepend(...items) {
    this._insert(this._nodes(items), 0);
  }
  insertBefore(node, ref) {
    if (!node || !node.nodeType) throw new TypeError("insertBefore: not a node");
    const nodes = this._nodes([node]);
    let i = ref ? this.childNodes.indexOf(ref) : this.childNodes.length;
    if (i < 0) throw new Error("NotFoundError");
    nodes.forEach((n) => n._detach());
    i = ref ? this.childNodes.indexOf(ref) : this.childNodes.length;
    this._insert(nodes, i);
    return node;
  }
  removeChild(node) {
    if (!node || node.parentNode !== this) throw new Error("NotFoundError");
    node._detach();
    return node;
  }
  replaceChild(node, old) {
    this.insertBefore(node, old);
    this.removeChild(old);
    return old;
  }
  replaceChildren(...items) {
    const nodes = this._nodes(items);
    for (const c of this.childNodes.slice()) c._detach();
    this._insert(nodes, 0);
  }
  remove() {
    this._detach();
  }
  replaceWith(...items) {
    const p = this.parentNode;
    if (!p) return;
    const i = p.childNodes.indexOf(this);
    const nodes = p._nodes(items);
    nodes.forEach((n) => n._detach());
    this._detach();
    p._insert(nodes, i);
  }
  before(...items) {
    const p = this.parentNode;
    if (p) p._insert(p._nodes(items), p.childNodes.indexOf(this));
  }
  after(...items) {
    const p = this.parentNode;
    if (p) p._insert(p._nodes(items), p.childNodes.indexOf(this) + 1);
  }
  addEventListener(type, fn) {
    if (typeof fn !== "function" && !(fn && typeof fn.handleEvent === "function")) return;
    (this._listeners[type] = this._listeners[type] || []).push(fn);
  }
  removeEventListener(type, fn) {
    const l = this._listeners[type];
    if (l) this._listeners[type] = l.filter((f) => f !== fn);
  }
  dispatchEvent(ev) {
    ev.target = ev.target || this;
    for (const fn of (this._listeners[ev.type] || []).slice()) {
      if (typeof fn === "function") fn.call(this, ev);
      else fn.handleEvent(ev);
    }
    return true;
  }
}

class Text_ extends Node_ {
  constructor(data) {
    super();
    this.nodeType = 3;
    this.nodeName = "#text";
    this.data = String(data);
  }
  get textContent() {
    return this.data;
  }
  set textContent(v) {
    this.data = v == null ? "" : String(v);
  }
  get nodeValue() {
    return this.data;
  }
  set nodeValue(v) {
    this.data = String(v);
  }
  cloneNode() {
    return new Text_(this.data);
  }
}

class Fragment_ extends Node_ {
  constructor() {
    super();
    this.nodeType = 11;
    this.nodeName = "#document-fragment";
  }
  get textContent() {
    return this.childNodes.map((c) => c.textContent).join("");
  }
}

function camelToKebab(s) {
  return s.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase());
}

class Element_ extends Node_ {
  constructor(tag) {
    super();
    this.nodeType = 1;
    this.tagName = String(tag).toUpperCase();
    this.nodeName = this.tagName;
    this.localName = String(tag).toLowerCase();
    this._attrs = new Map();
    this._style = {};
    const self = this;
    this.dataset = new Proxy(
      {},
      {
        get: (_t, p) => (typeof p === "string" && self._attrs.has("data-" + camelToKebab(p)) ? self._attrs.get("data-" + camelToKebab(p)) : undefined),
        set: (_t, p, v) => {
          self._attrs.set("data-" + camelToKebab(String(p)), String(v));
          return true;
        },
        deleteProperty: (_t, p) => {
          self._attrs.delete("data-" + camelToKebab(String(p)));
          return true;
        },
        has: (_t, p) => self._attrs.has("data-" + camelToKebab(String(p))),
      },
    );
    this.style = new Proxy(this._style, {
      get: (t, p) => {
        if (p === "setProperty") return (k, v) => void (t[k] = String(v));
        if (p === "removeProperty") return (k) => void delete t[k];
        if (p === "getPropertyValue") return (k) => (k in t ? t[k] : "");
        return p in t ? t[p] : "";
      },
      set: (t, p, v) => {
        t[p] = String(v);
        return true;
      },
    });
    const classes = () => (self._attrs.get("class") || "").split(/\s+/).filter(Boolean);
    const save = (list) => void self._attrs.set("class", list.join(" "));
    this.classList = {
      add: (...c) => save([...new Set([...classes(), ...c])]),
      remove: (...c) => save(classes().filter((x) => !c.includes(x))),
      contains: (c) => classes().includes(c),
      toggle: (c, force) => {
        const has = classes().includes(c);
        const want = force === undefined ? !has : !!force;
        if (want && !has) save([...classes(), c]);
        if (!want && has) save(classes().filter((x) => x !== c));
        return want;
      },
      replace: (a, b) => {
        if (!classes().includes(a)) return false;
        save(classes().map((x) => (x === a ? b : x)));
        return true;
      },
      item: (i) => classes()[i] ?? null,
      get length() {
        return classes().length;
      },
      toString: () => classes().join(" "),
    };
  }
  get children() {
    return this.childNodes.filter((c) => c.nodeType === 1);
  }
  get childElementCount() {
    return this.children.length;
  }
  get firstElementChild() {
    return this.children[0] || null;
  }
  get lastElementChild() {
    const c = this.children;
    return c[c.length - 1] || null;
  }
  get attributes() {
    return [...this._attrs].map(([name, value]) => ({ name, value }));
  }
  getAttribute(n) {
    return this._attrs.has(n) ? this._attrs.get(n) : null;
  }
  setAttribute(n, v) {
    this._attrs.set(String(n), String(v));
  }
  hasAttribute(n) {
    return this._attrs.has(n);
  }
  removeAttribute(n) {
    this._attrs.delete(n);
  }
  toggleAttribute(n, force) {
    const want = force === undefined ? !this._attrs.has(n) : !!force;
    if (want) this._attrs.set(n, "");
    else this._attrs.delete(n);
    return want;
  }
  get id() {
    return this._attrs.get("id") || "";
  }
  set id(v) {
    this._attrs.set("id", String(v));
  }
  get className() {
    return this._attrs.get("class") || "";
  }
  set className(v) {
    this._attrs.set("class", String(v));
  }
  get title() {
    return this._attrs.get("title") || "";
  }
  set title(v) {
    this._attrs.set("title", String(v));
  }
  get hidden() {
    return this._attrs.has("hidden");
  }
  set hidden(v) {
    if (v) this._attrs.set("hidden", "");
    else this._attrs.delete("hidden");
  }
  get lang() {
    return this._attrs.get("lang") || "";
  }
  get textContent() {
    return this.childNodes.map((c) => c.textContent).join("");
  }
  set textContent(v) {
    for (const c of this.childNodes.slice()) c._detach();
    const s = v == null ? "" : String(v);
    if (s !== "") this._insert([new Text_(s)], 0);
  }
  get innerText() {
    return this.textContent;
  }
  set innerText(v) {
    this.textContent = v;
  }
  _banned(what) {
    counters.htmlInsertions += 1;
    throw new Error(`${what} は使えない（文字は textContent で出す）`);
  }
  set innerHTML(_v) {
    this._banned("innerHTML");
  }
  get innerHTML() {
    return this.childNodes.map((c) => (c.nodeType === 3 ? c.data : c.outerHTML)).join("");
  }
  set outerHTML(_v) {
    this._banned("outerHTML");
  }
  get outerHTML() {
    const attrs = [...this._attrs].map(([k, v]) => ` ${k}="${v}"`).join("");
    return `<${this.localName}${attrs}>${this.innerHTML}</${this.localName}>`;
  }
  insertAdjacentHTML() {
    this._banned("insertAdjacentHTML");
  }
  insertAdjacentElement(where, el) {
    if (where === "beforeend") this.appendChild(el);
    else if (where === "afterbegin") this.prepend(el);
    else if (where === "beforebegin") this.before(el);
    else if (where === "afterend") this.after(el);
    return el;
  }
  insertAdjacentText(where, text) {
    this.insertAdjacentElement(where, new Text_(text));
  }
  cloneNode(deep) {
    const c = new Element_(this.localName);
    for (const [k, v] of this._attrs) c._attrs.set(k, v);
    if (deep) for (const ch of this.childNodes) c.appendChild(ch.cloneNode(true));
    return c;
  }
  matches(sel) {
    return parseSelector(sel).some((chain) => matchChain(this, chain));
  }
  closest(sel) {
    for (let n = this; n && n.nodeType === 1; n = n.parentNode) if (n.matches(sel)) return n;
    return null;
  }
  querySelectorAll(sel) {
    return queryAll(this, sel);
  }
  querySelector(sel) {
    return queryAll(this, sel)[0] || null;
  }
  getElementsByTagName(tag) {
    return descendants(this).filter((e) => tag === "*" || e.localName === String(tag).toLowerCase());
  }
  getElementsByClassName(cls) {
    return descendants(this).filter((e) => e.classList.contains(cls));
  }
  get isConnected() {
    for (let n = this; n; n = n.parentNode) if (n === world.root) return true;
    return false;
  }
  _rendered() {
    // 文書に付いていて、自分も祖先も hidden でない（display: none でない）
    if (!this.isConnected) return false;
    for (let n = this; n && n.nodeType === 1; n = n.parentNode) if (n._attrs.has("hidden")) return false;
    return true;
  }
  _focusable() {
    return ["button", "textarea", "input", "select"].includes(this.localName) || this._attrs.has("tabindex");
  }
  focus() {
    if (!this._rendered() || this.disabled || !this._focusable()) return;
    focusState.el = this;
  }
  blur() {
    if (focusState.el === this) focusState.el = null;
  }
  get disabled() {
    return this._attrs.has("disabled");
  }
  set disabled(v) {
    if (v) this._attrs.set("disabled", "");
    else this._attrs.delete("disabled");
  }
  get value() {
    if (this._value !== undefined) return this._value;
    if (this._attrs.has("value")) return this._attrs.get("value");
    return this.localName === "textarea" ? this.textContent : "";
  }
  set value(v) {
    this._value = v == null ? "" : String(v);
    this._selStart = this._selEnd = this._value.length;
  }
  get selectionStart() {
    return this._selStart === undefined ? this.value.length : this._selStart;
  }
  get selectionEnd() {
    return this._selEnd === undefined ? this.value.length : this._selEnd;
  }
  setSelectionRange(a, b) {
    const n = this.value.length;
    const lo = Math.max(0, Math.min(Number(a) || 0, n));
    const hi = Math.max(lo, Math.min(Number(b) || 0, n));
    this._selStart = lo;
    this._selEnd = hi;
  }
  get type() {
    return this._attrs.get("type") || "";
  }
  set type(v) {
    this._attrs.set("type", String(v));
  }
  get rows() {
    return Number(this._attrs.get("rows")) || 2;
  }
  set rows(v) {
    this._attrs.set("rows", String(v));
  }
  get maxLength() {
    return this._attrs.has("maxlength") ? Number(this._attrs.get("maxlength")) : -1;
  }
  set maxLength(v) {
    this._attrs.set("maxlength", String(v));
  }
  get placeholder() {
    return this._attrs.get("placeholder") || "";
  }
  set placeholder(v) {
    this._attrs.set("placeholder", String(v));
  }
  get name() {
    return this._attrs.get("name") || "";
  }
  set name(v) {
    this._attrs.set("name", String(v));
  }
  get tabIndex() {
    return this._attrs.has("tabindex") ? Number(this._attrs.get("tabindex")) : this._focusable() ? 0 : -1;
  }
  set tabIndex(v) {
    this._attrs.set("tabindex", String(v));
  }
  get ownerDocument() {
    return world.document;
  }
  click() {
    this.dispatchEvent({ type: "click" });
  }
  scrollIntoView() {}
  getBoundingClientRect() {
    return { x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 };
  }
}

function descendants(root) {
  const out = [];
  const walk = (n) => {
    for (const c of n.childNodes) {
      if (c.nodeType === 1) {
        out.push(c);
        walk(c);
      }
    }
  };
  walk(root);
  return out;
}

// 簡単なセレクタ：, で区切る・子孫（空白）・子（>）・複合（タグ #id .class [attr] [attr=val]）
function parseSelector(sel) {
  return String(sel)
    .split(",")
    .map((part) => {
      const tokens = part.trim().replace(/\s*>\s*/g, " > ").split(/\s+/).filter(Boolean);
      const chain = [];
      let comb = " ";
      for (const t of tokens) {
        if (t === ">") {
          comb = ">";
          continue;
        }
        chain.push({ comb, compound: parseCompound(t) });
        comb = " ";
      }
      return chain;
    });
}

function parseCompound(t) {
  const c = { tag: null, id: null, classes: [], attrs: [] };
  const re = /^([a-zA-Z][\w-]*|\*)|#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\]]*)))?\]/g;
  let m;
  while ((m = re.exec(t))) {
    if (m[1]) c.tag = m[1].toLowerCase();
    else if (m[2]) c.id = m[2];
    else if (m[3]) c.classes.push(m[3]);
    else if (m[4]) c.attrs.push([m[4], m[5] ?? m[6] ?? m[7] ?? null]);
  }
  return c;
}

function matchCompound(el, c) {
  if (c.tag && c.tag !== "*" && el.localName !== c.tag) return false;
  if (c.id && el.id !== c.id) return false;
  if (!c.classes.every((k) => el.classList.contains(k))) return false;
  return c.attrs.every(([k, v]) => (v === null ? el.hasAttribute(k) : el.getAttribute(k) === v));
}

function matchChain(el, chain) {
  const rec = (node, i) => {
    if (!matchCompound(node, chain[i].compound)) return false;
    if (i === 0) return true;
    if (chain[i].comb === ">") return !!node.parentNode && node.parentNode.nodeType === 1 && rec(node.parentNode, i - 1);
    for (let p = node.parentNode; p && p.nodeType === 1; p = p.parentNode) if (rec(p, i - 1)) return true;
    return false;
  };
  return chain.length > 0 && rec(el, chain.length - 1);
}

function queryAll(root, sel) {
  const chains = parseSelector(sel);
  return descendants(root).filter((e) => chains.some((ch) => matchChain(e, ch)));
}

// ---- HTML から偽の DOM を作る（骨組みだけ。<script>・<style> の中身は読まない） --------------------------------------

function parseAttrs(s) {
  const attrs = [];
  const re = /([^\s=\/"'<>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g;
  let m;
  while ((m = re.exec(s))) attrs.push([m[1], decodeEntities(m[2] ?? m[3] ?? m[4] ?? "")]);
  return attrs;
}

function buildDom(html) {
  const htmlEl = new Element_("html");
  const head = new Element_("head");
  const body = new Element_("body");
  htmlEl.append(head, body);
  let title = "";
  const htmlTag = /<html\b([^>]*)>/i.exec(html);
  if (htmlTag) for (const [k, v] of parseAttrs(htmlTag[1])) htmlEl.setAttribute(k, v);
  const t = /<title>([\s\S]*?)<\/title>/i.exec(html);
  if (t) title = decodeEntities(t[1]);
  const bodyOpen = /<body\b([^>]*)>/i.exec(html);
  if (!bodyOpen) return { htmlEl, head, body, title };
  for (const [k, v] of parseAttrs(bodyOpen[1])) body.setAttribute(k, v);
  let rest = html.slice(bodyOpen.index + bodyOpen[0].length);
  const end = rest.search(/<script\b|<\/body>/i);
  if (end >= 0) rest = rest.slice(0, end);
  const stack = [body];
  const re = /<!--[\s\S]*?-->|<\/([a-zA-Z][\w-]*)\s*>|<([a-zA-Z][\w-]*)([^>]*?)(\/?)>|([^<]+)/g;
  let m;
  while ((m = re.exec(rest))) {
    if (m[5] !== undefined) {
      if (m[5].trim() !== "" || stack.length > 1) stack[stack.length - 1].appendChild(new Text_(decodeEntities(m[5])));
    } else if (m[1]) {
      const name = m[1].toLowerCase();
      for (let i = stack.length - 1; i > 0; i--) {
        if (stack[i].localName === name) {
          stack.length = i;
          break;
        }
      }
    } else if (m[2]) {
      const el = new Element_(m[2]);
      for (const [k, v] of parseAttrs(m[3])) el.setAttribute(k, v);
      stack[stack.length - 1].appendChild(el);
      if (!VOID.has(el.localName) && m[4] !== "/") stack.push(el);
    }
  }
  return { htmlEl, head, body, title };
}

// 親へ伝わる（要素 → 親 → html → document）イベントを送る（click・input）。止める・既定を止めるの呼び出しも受ける。聞き手の例外はブラウザと同じく他の聞き手を止めない
const reported = [];
function fire(target, type) {
  const ev = {
    type,
    target,
    bubbles: true,
    cancelable: true,
    defaultPrevented: false,
    isTrusted: true,
    detail: 1,
    preventDefault() {
      this.defaultPrevented = true;
    },
    stopPropagation() {
      this._stop = true;
    },
    stopImmediatePropagation() {
      this._stop = true;
    },
  };
  // 要素 → 親 → … → html → document の順に伝える
  const path = [];
  for (let n = target; n; n = n.parentNode) path.push(n);
  if (world.document) path.push(world.document);
  for (const n of path) {
    if (ev._stop) break;
    ev.currentTarget = n;
    for (const fn of ((n._listeners && n._listeners[type]) || []).slice()) {
      try {
        if (typeof fn === "function") fn.call(n, ev);
        else fn.handleEvent(ev);
      } catch (e) {
        reported.push(`${type}: ${e && e.message ? e.message : e}`);
      }
    }
  }
}

// ---- 主な処理 --------------------------------------------------------------------------------------------

const PRELUDE = `
(function () {
  var RealDate = Date;
  class FakeDate extends RealDate {
    constructor(...a) { if (a.length === 0) super(globalThis.__vnow()); else super(...a); }
    static now() { return globalThis.__vnow(); }
  }
  globalThis.Date = FakeDate;
  globalThis.__decode = function (text) {
    return JSON.parse(text, function (k, v) {
      if (v && typeof v === "object" && !Array.isArray(v)) {
        var ks = Object.keys(v);
        if (ks.length === 1 && ks[0] === "$") {
          if (v.$ === "NaN") return NaN;
          if (v.$ === "Infinity") return Infinity;
          if (v.$ === "-Infinity") return -Infinity;
        }
      }
      return v;
    });
  };
  globalThis.__enc = function enc(v, depth) {
    depth = depth || 0;
    if (depth > 20) return { $: "deep" };
    if (v === undefined) return { $: "undefined" };
    if (typeof v === "number") {
      if (v !== v) return { $: "NaN" };
      if (v === Infinity) return { $: "Infinity" };
      if (v === -Infinity) return { $: "-Infinity" };
      return v;
    }
    if (typeof v === "function") return { $: "function" };
    if (typeof v === "bigint") return { $: "bigint" };
    if (typeof v === "symbol") return { $: "symbol" };
    if (v === null || typeof v !== "object") return v;
    if (Array.isArray(v)) return v.map(function (x) { return enc(x, depth + 1); });
    var out = {};
    Object.keys(v).forEach(function (k) { out[k] = enc(v[k], depth + 1); });
    return out;
  };
})();
`;

async function flush() {
  for (let i = 0; i < 8; i++) await Promise.resolve();
  await new Promise((r) => setImmediate(r));
  for (let i = 0; i < 8; i++) await Promise.resolve();
}

function errText(e) {
  return e && e.message ? String(e.message) : String(e);
}

async function main() {
  const scene = JSON.parse(fs.readFileSync(0, "utf8"));
  const html = String(scene.html ?? "");
  const mode = scene.claude ?? "db";
  const startMs = Date.parse(scene.now ?? "2026-10-17T02:00:00+00:00");
  let vnow = startMs;
  let hidden = !!scene.hidden;
  const unhandled = [];
  const uncaught = [];
  process.on("unhandledRejection", (e) => unhandled.push(errText(e)));
  process.on("uncaughtException", (e) => uncaught.push(errText(e)));

  const { htmlEl, head, body, title } = buildDom(html);
  const docListeners = new Node_();
  const timers = new Map();
  let nextTimer = 0;
  const consoleLines = { log: [], error: [], warn: [] };
  const listenerErrors = [];

  const document = Object.assign(docListeners, {
    nodeType: 9,
    nodeName: "#document",
    documentElement: htmlEl,
    head,
    body,
    title,
    readyState: "loading",
    get hidden() {
      return hidden;
    },
    get visibilityState() {
      return hidden ? "hidden" : "visible";
    },
    createElement(tag) {
      if (typeof tag !== "string" || !/^[a-zA-Z][\w-]*$/.test(tag)) throw new Error("InvalidCharacterError");
      counters.created.push(tag.toLowerCase());
      return new Element_(tag);
    },
    createTextNode(t) {
      return new Text_(t);
    },
    createDocumentFragment() {
      return new Fragment_();
    },
    createComment() {
      return new Text_("");
    },
    getElementById(id) {
      return descendants(htmlEl).find((e) => e.id === id) || null;
    },
    querySelector(sel) {
      return queryAll(htmlEl, sel)[0] || null;
    },
    querySelectorAll(sel) {
      return queryAll(htmlEl, sel);
    },
    getElementsByTagName(tag) {
      return htmlEl.getElementsByTagName(tag);
    },
    getElementsByClassName(cls) {
      return htmlEl.getElementsByClassName(cls);
    },
    write() {
      counters.htmlInsertions += 1;
      throw new Error("document.write は使えない");
    },
    writeln() {
      counters.htmlInsertions += 1;
      throw new Error("document.writeln は使えない");
    },
  });
  world.root = htmlEl;
  world.body = body;
  world.document = document;
  Object.defineProperty(document, "activeElement", {
    get: () => {
      const a = focusState.el;
      if (a && (!a._rendered() || a.disabled)) focusState.el = null;
      return focusState.el || body;
    },
    configurable: true,
  });
  Object.defineProperty(document, "hidden", { get: () => hidden, configurable: true });
  Object.defineProperty(document, "visibilityState", { get: () => (hidden ? "hidden" : "visible"), configurable: true });
  htmlEl.parentNode = null;

  function addTimer(fn, ms, interval, args) {
    if (typeof fn !== "function") throw new TypeError("タイマーに関数でないものが渡された");
    const delay = Math.max(0, Number(ms) || 0);
    const id = ++nextTimer;
    timers.set(id, { fn, ms: delay, due: vnow + delay, interval, args });
    return id;
  }

  const db = { calls: [], writes: [], subs: [], unsub: 0, useCalls: [] };
  function makeRef(path) {
    return {
      path,
      onSnapshot(next, error) {
        db.calls.push(["onSnapshot", path]);
        if (mode === "onsnapshot_throws") throw new Error("onSnapshot failed");
        const sub = { next, error, active: true };
        db.subs.push(sub);
        if (scene.initial) {
          Promise.resolve().then(() => deliver(sub, scene.initial.missing ? { kind: "missing" } : { kind: "data", value: scene.initial.value }));
        }
        return () => {
          sub.active = false;
          db.unsub += 1;
        };
      },
      set() {
        db.writes.push(["ref.set", path]);
        return Promise.resolve();
      },
      update() {
        db.writes.push(["ref.update", path]);
        return Promise.resolve();
      },
      delete() {
        db.writes.push(["ref.delete", path]);
        return Promise.resolve();
      },
    };
  }
  const fakeDb = {
    doc(path) {
      db.calls.push(["doc", path]);
      if (mode === "doc_throws") throw new Error("doc failed");
      return makeRef(path);
    },
    set() {
      db.writes.push(["db.set"]);
    },
    update() {
      db.writes.push(["db.update"]);
    },
    delete() {
      db.writes.push(["db.delete"]);
    },
    add() {
      db.writes.push(["db.add"]);
    },
  };

  const sandbox = {
    document,
    __vnow: () => vnow,
    console: {
      log: (...a) => consoleLines.log.push(a.map(String).join(" ")),
      info: (...a) => consoleLines.log.push(a.map(String).join(" ")),
      debug: (...a) => consoleLines.log.push(a.map(String).join(" ")),
      warn: (...a) => consoleLines.warn.push(a.map(String).join(" ")),
      error: (...a) => consoleLines.error.push(a.map(String).join(" ")),
    },
    setInterval: (fn, ms, ...args) => addTimer(fn, ms, true, args),
    setTimeout: (fn, ms, ...args) => addTimer(fn, ms, false, args),
    clearInterval: (id) => void timers.delete(id),
    clearTimeout: (id) => void timers.delete(id),
    requestAnimationFrame: (fn) => addTimer(() => fn(vnow), 16, false, []),
    cancelAnimationFrame: (id) => void timers.delete(id),
    queueMicrotask,
    alert: (...a) => void (counters.alerts.push(a.map(String).join(" ")), counters.dialogs.push("alert")),
    confirm: () => (counters.dialogs.push("confirm"), false),
    prompt: () => (counters.dialogs.push("prompt"), null),
    navigator: { language: "ja", languages: ["ja"], userAgent: "live-page-harness" },
    performance: { now: () => vnow - startMs },
    matchMedia: (q) => ({ matches: false, media: String(q), addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }),
    innerWidth: 360,
    innerHeight: 640,
    devicePixelRatio: 1,
    location: { href: "about:blank", protocol: "about:", search: "", hash: "" },
  };
  const winListeners = new Node_();
  sandbox.addEventListener = (t, f) => winListeners.addEventListener(t, f);
  sandbox.removeEventListener = (t, f) => winListeners.removeEventListener(t, f);
  sandbox.dispatchEvent = (e) => winListeners.dispatchEvent(e);
  sandbox.window = sandbox;
  sandbox.self = sandbox;
  sandbox.top = sandbox;
  sandbox.parent = sandbox;
  sandbox.frames = sandbox;

  // ---- D0039：偽の comments ----
  const cfg = scene.comments && typeof scene.comments === "object" ? scene.comments : null;
  const comm = {
    useCalls: 0,
    canCalls: 0,
    anchorCalls: [],
    sends: [],
    can: cfg && cfg.can !== undefined ? cfg.can : "available",
    anchors: 0,
    issued: [],
    pendingSends: [],
    pendingCan: [],
    pendingAnchors: [],
  };
  const special = (v, name) => v !== null && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === 1 && v.$ === name;
  const decodeValue = (v) => (special(v, "undefined") ? undefined : v);
  const elPath = (el) => {
    const parts = [];
    for (let n = el; n && n.nodeType === 1 && n !== world.root; n = n.parentNode) {
      const sibs = n.parentNode ? n.parentNode.children : [n];
      const cls = n.className ? "." + n.className.split(/\s+/).filter(Boolean).join(".") : "";
      parts.unshift(`${n.localName}${cls}:nth-child(${sibs.indexOf(n) + 1})`);
    }
    return parts.join(" > ");
  };
  const issueAnchor = (el) => {
    const a = { path: elPath(el), x: 1, y: 2, token: `ANCHOR-TOKEN-${++comm.anchors}` };
    comm.issued.push(a);
    return a;
  };
  const rejection = (message, code) => Object.assign(new Error(message), code === undefined ? {} : { code });
  const fakeComments = {
    canSendToClaude() {
      comm.canCalls += 1;
      const v = comm.can;
      if (v === "pending") return new Promise((resolve, reject) => comm.pendingCan.push({ resolve, reject }));
      if (special(v, "throw")) throw new Error("canSendToClaude threw");
      if (special(v, "reject")) return Promise.reject(new Error("canSendToClaude rejected"));
      return Promise.resolve(decodeValue(v));
    },
    anchorFor(el) {
      comm.anchorCalls.push({ el_tag: el && el.localName, el_class: el && el.className, attached: !!(el && el.isConnected) });
      const how = cfg && cfg.anchor !== undefined ? cfg.anchor : "ok";
      if (how === "throws") throw new Error("anchorFor threw");
      if (how === "rejects") return Promise.reject(rejection("invalid", "invalid"));
      if (how === "not_an_object") return Promise.resolve("ANCHOR-STRING");
      if (how === "pending") return new Promise((resolve, reject) => comm.pendingAnchors.push({ resolve, reject, el }));
      return Promise.resolve(issueAnchor(el));
    },
    sendToClaude(arg) {
      const n = comm.sends.length;
      const isObj = arg !== null && typeof arg === "object";
      comm.sends.push({
        text: isObj ? arg.text : null,
        anchor: isObj ? arg.anchor : null,
        anchor_issued: isObj && comm.issued.includes(arg.anchor),
        in_gesture: gesture.active,
        n,
        keys: isObj ? Object.keys(arg).sort() : null,
        argc: arguments.length,
      });
      let how = cfg && cfg.send !== undefined ? cfg.send : "resolve";
      if (Array.isArray(how)) how = how[Math.min(n, how.length - 1)];
      if (how === "throws") throw new Error("sendToClaude threw");
      if (how === "pending") return new Promise((resolve, reject) => comm.pendingSends.push({ resolve, reject }));
      if (how !== null && typeof how === "object" && "reject_code" in how) return Promise.reject(rejection("REJECT-MESSAGE-SECRET", how.reject_code));
      if (how !== null && typeof how === "object" && "reject" in how) return Promise.reject(decodeValue(how.reject));
      return Promise.resolve();
    },
  };
  function commentsUse() {
    comm.useCalls += 1;
    if (!cfg) return Promise.resolve(null);
    const how = cfg.use !== undefined ? cfg.use : "ok";
    if (how === "throws") throw new Error("claude.use('comments') threw");
    if (how === "rejects") return Promise.reject(new Error("claude.use('comments') rejected"));
    if (how === "null") return Promise.resolve(null);
    if (how === "undefined") return Promise.resolve(undefined);
    return Promise.resolve(fakeComments);
  }

  if (mode !== "undefined") {
    sandbox.claude = {
      use: (name) => {
        db.useCalls.push(name);
        if (mode === "use_throws") throw new Error("claude.use threw");
        if (mode === "use_rejects") return Promise.reject(new Error("claude.use rejected"));
        if (mode === "use_undefined") return Promise.resolve(undefined);
        if (name === "comments" && mode !== "null") return commentsUse();
        if (name !== "db" || mode === "null") return Promise.resolve(null);
        return Promise.resolve(fakeDb);
      },
    };
  }

  const ctx = vm.createContext(sandbox);
  vm.runInContext(PRELUDE, ctx, { filename: "prelude.js" });

  function callIn(fnName, args) {
    ctx.__args = JSON.stringify(args ?? []);
    ctx.__fn = fnName;
    const code = `(function () {
      try {
        var f = (0, eval)(__fn);
      } catch (e) { return JSON.stringify({ thrown: String(e && e.message || e) }); }
      try {
        return JSON.stringify({ value: __enc(f.apply(null, __decode(__args))) });
      } catch (e) { return JSON.stringify({ thrown: String(e && e.message || e) }); }
    })()`;
    return JSON.parse(vm.runInContext(code, ctx));
  }

  function view() {
    const lines = [];
    const tags = {};
    const attrs = new Set();
    const walk = (n) => {
      for (const c of n.childNodes) {
        if (c.nodeType === 3) {
          const t = c.data.replace(/\s+/g, " ").trim();
          if (t) lines.push(t);
        } else if (c.nodeType === 1) {
          tags[c.localName] = (tags[c.localName] || 0) + 1;
          for (const k of c._attrs.keys()) attrs.add(k);
          walk(c);
        }
      }
    };
    walk(body);
    const shown = [];
    const walkShown = (n) => {
      for (const c of n.childNodes) {
        if (c.nodeType === 3) {
          const t = c.data.replace(/\s+/g, " ").trim();
          if (t) shown.push(t);
        } else if (c.nodeType === 1 && !c._attrs.has("hidden")) {
          walkShown(c);
        }
      }
    };
    walkShown(body);
    const live = [...timers.values()];
    return {
      lines,
      text: lines.join("\n"),
      shown_lines: shown,
      shown_text: shown.join("\n"),
      tags,
      attrs: [...attrs].sort(),
      created: counters.created.slice(),
      intervals: live.filter((t) => t.interval).length,
      timeouts: live.filter((t) => !t.interval).length,
      interval_ms: live.filter((t) => t.interval).map((t) => t.ms),
      html_insertions: counters.htmlInsertions,
      hidden,
      now_ms: vnow,
    };
  }

  function mkSnap(kind, value, what) {
    if (kind === "missing") return vm.runInContext("({ exists: false, data: function () { return undefined; } })", ctx);
    if (kind === "data") {
      ctx.__text = JSON.stringify(value === undefined ? null : value);
      return vm.runInContext("(function () { var v = __decode(__text); return { exists: true, data: function () { return v; } }; })()", ctx);
    }
    switch (what) {
      case "no_data":
        return vm.runInContext("({ exists: true })", ctx);
      case "data_throws":
        return vm.runInContext("({ exists: true, data: function () { throw new Error('boom'); } })", ctx);
      case "data_function":
        return vm.runInContext("({ exists: true, data: function () { return function () {}; } })", ctx);
      case "number":
        return 5;
      case "string":
        return "text";
      case "exists_string":
        return vm.runInContext("({ exists: 'yes', data: function () { return { schema: 1, stages: [] }; } })", ctx);
      case "null":
        return null;
      case "undefined":
        return undefined;
      default:
        throw new Error("send_raw: 知らない what " + what);
    }
  }

  function deliver(sub, spec) {
    const snap = spec.kind === "raw" ? mkSnap("raw", null, spec.what) : mkSnap(spec.kind, spec.value);
    if (sub.active) sub.next(snap);
  }

  async function advance(ms) {
    const target = vnow + ms;
    let guard = 0;
    for (;;) {
      let pick = null;
      let pickId = 0;
      for (const [id, t] of timers) if (t.due <= target && (pick === null || t.due < pick.due || (t.due === pick.due && id < pickId))) [pick, pickId] = [t, id];
      if (!pick) break;
      if (++guard > 200000) throw new Error("タイマーが多すぎる（止まらない）");
      vnow = Math.max(vnow, pick.due);
      if (pick.interval) pick.due = vnow + Math.max(1, pick.ms);
      else timers.delete(pickId);
      try {
        pick.fn(...pick.args);
      } catch (e) {
        listenerErrors.push("timer: " + errText(e));
      }
      await flush();
    }
    vnow = target;
  }

  // ---- ページの JS を動かす ----
  let loadError = null;
  const m = /<script\b[^>]*>([\s\S]*?)<\/script>/i.exec(html);
  if (!m) {
    loadError = "ページに <script> が無い";
  } else {
    try {
      vm.runInContext(m[1], ctx, { filename: "page.js" });
    } catch (e) {
      loadError = "読み込みで例外: " + errText(e);
    }
  }
  await flush();
  document.readyState = "interactive";
  for (const [target, type] of [[document, "DOMContentLoaded"]]) {
    try {
      target.dispatchEvent({ type });
    } catch (e) {
      listenerErrors.push(type + ": " + errText(e));
    }
  }
  document.readyState = "complete";
  try {
    winListeners.dispatchEvent({ type: "load" });
  } catch (e) {
    listenerErrors.push("load: " + errText(e));
  }
  await flush();
  const loaded = view();

  const steps = [];
  for (const step of scene.steps ?? []) {
    const r = { op: step.op, threw: null, result: null };
    try {
      if (step.op === "send") {
        const spec = step.missing ? { kind: "missing" } : { kind: "data", value: step.value };
        for (const sub of db.subs.slice()) deliver(sub, spec);
      } else if (step.op === "send_raw") {
        for (const sub of db.subs.slice()) deliver(sub, { kind: "raw", what: step.what });
      } else if (step.op === "error") {
        for (const sub of db.subs.slice()) if (sub.active && typeof sub.error === "function") sub.error(new Error(step.message ?? "error"));
      } else if (step.op === "advance") {
        await advance(Number(step.ms));
      } else if (step.op === "set_now") {
        // 時計（Date）だけを動かす。タイマーは Date に左右されない（単調な時間で動く）ので、期限は同じ幅だけずらす
        const next = Date.parse(step.at);
        const delta = next - vnow;
        for (const t of timers.values()) t.due += delta;
        vnow = next;
      } else if (step.op === "hidden") {
        hidden = !!step.value;
        document.dispatchEvent({ type: "visibilitychange" });
      } else if (step.op === "call") {
        const out = callIn(step.fn, step.args);
        if (out.thrown !== undefined) r.threw = out.thrown;
        else r.result = out.value;
      } else if (step.op === "query") {
        r.result = queryAll(body, step.selector).map((e) => ({
          tag: e.localName,
          text: e.textContent,
          attrs: Object.fromEntries(e._attrs),
          value: e._value === undefined ? null : e._value,
          selection: e.localName === "textarea" ? [e.selectionStart, e.selectionEnd] : null,
          disabled: e.disabled,
          shown: e._rendered(),
          focused: document.activeElement === e,
        }));
      } else if (step.op === "click") {
        const target = queryAll(body, step.selector)[0] || null;
        r.result = { found: target !== null, dispatched: 0, skipped: 0 };
        if (target) {
          gesture.active = true;
          try {
            for (let i = 0; i < (step.times ?? 1); i++) {
              if (!step.force && (target.disabled || !target._rendered())) {
                r.result.skipped += 1;
                continue;
              }
              r.result.dispatched += 1;
              fire(target, "click");
            }
          } finally {
            gesture.active = false;
          }
        }
      } else if (step.op === "input") {
        const target = queryAll(body, step.selector)[0] || null;
        r.result = { found: target !== null, dispatched: 0, skipped: 0 };
        if (target) {
          if (!step.force && (target.disabled || !target._rendered())) {
            r.result.skipped += 1;
          } else {
            target.value = step.value;
            r.result.dispatched += 1;
            fire(target, "input");
          }
        }
      } else if (step.op === "focus") {
        const target = queryAll(body, step.selector)[0] || null;
        r.result = { found: target !== null };
        if (target) target.focus();
      } else if (step.op === "select") {
        const target = queryAll(body, step.selector)[0] || null;
        r.result = { found: target !== null };
        if (target) target.setSelectionRange(step.start, step.end);
      } else if (step.op === "focus_state") {
        const a = document.activeElement;
        r.result = { tag: a.localName, class: a.className };
      } else if (step.op === "settle") {
        const p = comm.pendingSends[step.call];
        if (!p) throw new Error("settle: その送信は pending でない " + step.call);
        if (step.how === "resolve") p.resolve();
        else p.reject(decodeValue(step.how.reject));
        r.result = { settled: step.call };
      } else if (step.op === "settle_can") {
        const p = comm.pendingCan[step.call];
        if (!p) throw new Error("settle_can: その呼び出しは pending でない " + step.call);
        if (special(step.value, "reject")) p.reject(new Error("canSendToClaude rejected"));
        else p.resolve(decodeValue(step.value));
        r.result = { settled: step.call };
      } else if (step.op === "settle_anchor") {
        const p = comm.pendingAnchors[step.call];
        if (!p) throw new Error("settle_anchor: その呼び出しは pending でない " + step.call);
        if (step.how === "reject") p.reject(rejection("invalid", "invalid"));
        else p.resolve(issueAnchor(p.el));
        r.result = { settled: step.call };
      } else if (step.op === "set_can") {
        comm.can = step.value;
        r.result = { set: true };
      } else {
        throw new Error("知らない op " + step.op);
      }
    } catch (e) {
      r.threw = errText(e);
    }
    await flush();
    r.view = view();
    steps.push(r);
  }

  const out = {
    load_error: loadError,
    loaded,
    steps,
    final: view(),
    console_errors: consoleLines.error,
    console_warnings: consoleLines.warn,
    console_logs: consoleLines.log,
    unhandled,
    uncaught,
    listener_errors: listenerErrors.concat(reported),
    alerts: counters.alerts,
    dialogs: counters.dialogs,
    comments: {
      use_calls: comm.useCalls,
      can_calls: comm.canCalls,
      anchor_calls: comm.anchorCalls,
      sends: comm.sends,
      pending_sends: comm.pendingSends.length,
      pending_can: comm.pendingCan.length,
      pending_anchor: comm.pendingAnchors.length,
    },
    db: {
      calls: db.calls,
      writes: db.writes,
      use_calls: db.useCalls,
      subscriptions: db.subs.length,
      active_subscriptions: db.subs.filter((s) => s.active).length,
      unsubscribed: db.unsub,
    },
  };
  process.stdout.write(JSON.stringify(out));
}

main().catch((e) => {
  process.stdout.write(JSON.stringify({ harness_error: errText(e), stack: String(e && e.stack) }));
});
