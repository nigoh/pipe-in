// テストの補助（fakeDom.ts）自身の検査（D0017）：偽の時計・setInterval・visibilityState・matchMedia・textContent・getAnimations。
// 補助が間違っていると、パネルのスクリプトのテストが間違った理由で通る・落ちるので、補助そのものの動きを確かめておく。
// パネルの本物のスクリプトは使わず、補助を呼ぶだけの小さなスクリプトで試す。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { bootPanel } from './fakeDom.ts';
import type { BootOptions, FakeNode } from './fakeDom.ts';

const SCRIPT = `
const vscode = acquireVsCodeApi();
const root = document.querySelector('.root');
let n = 0;
const id = setInterval(function () { n++; root.textContent = 'n=' + n + ' t=' + (Date.now() % 100000); }, 1000);
window.addEventListener('message', function (e) { if (e.data === 'stop') clearInterval(id); });
document.addEventListener('visibilitychange', function () { root.setAttribute('data-vis', document.visibilityState); });
root.setAttribute('data-vis', document.visibilityState);
root.setAttribute('data-reduce', String(window.matchMedia('(prefers-reduced-motion: reduce)').matches));
root.setAttribute('data-nopref', String(window.matchMedia('(prefers-reduced-motion: no-preference)').matches));
`;
const page = `<!DOCTYPE html><html><body><div class="root"></div><script nonce="x">${SCRIPT}</script></body></html>`;
const boot = (opts?: BootOptions) => bootPanel(page, opts);

test('D0017-AC-22: 偽の時計は startMs から始まり、advance で進む（本物の時間を使わない）', () => {
  const h = boot({ startMs: 5000 });
  assert.equal(h.now(), 5000);
  h.advance(2500);
  assert.equal(h.now(), 7500);
});

test('D0017-AC-22: setInterval は期限の来た数だけ呼ばれ、1 秒に満たない advance では呼ばれない', () => {
  const h = boot({ startMs: 0 });
  h.advance(999);
  assert.equal(h.text(h.root), '');
  h.advance(1);
  assert.equal(h.text(h.root), 'n=1 t=1000');
  h.advance(2500);
  assert.equal(h.text(h.root), 'n=3 t=3000', '2000・3000 の 2 回が呼ばれ、最後の呼びは 3000 の時刻で行われる');
  assert.equal(h.now(), 3500, 'advance の終わりでは時計が目的の時刻に着く');
});

test('D0017-AC-22: 1 回の advance で何回分の期限が来ても、期限の時刻の順に時計を進めながら呼ぶ', () => {
  const h = boot({ startMs: 0 });
  h.advance(3000);
  assert.equal(h.text(h.root), 'n=3 t=3000');
  assert.equal(h.now(), 3000);
});

test('D0017-AC-23: activeIntervals と createdIntervals は、作った数・止めていない数を数える。clearInterval で止まる', () => {
  const h = boot();
  assert.equal(h.activeIntervals(), 1);
  assert.equal(h.createdIntervals(), 1);
  h.send('stop');
  assert.equal(h.activeIntervals(), 0);
  assert.equal(h.createdIntervals(), 1, '作った数は減らない');
  const before = h.text(h.root);
  h.advance(10_000);
  assert.equal(h.text(h.root), before, '止めたあとは呼ばれない');
});

test('D0017-AC-25: setNow は時計だけを動かし（戻せる）、タイマーは呼ばない。tick は時計を動かさず 1 回ずつ呼ぶ', () => {
  const h = boot({ startMs: 10_000 });
  h.setNow(2000);
  assert.equal(h.now(), 2000);
  assert.equal(h.text(h.root), '');
  h.tick();
  assert.equal(h.text(h.root), 'n=1 t=2000');
  assert.equal(h.now(), 2000);
});

test('D0017-AC-24: setVisibility は document.visibilityState を替え、visibilitychange を届ける', () => {
  const h = boot();
  assert.equal(h.root.getAttribute('data-vis'), 'visible');
  h.setVisibility('hidden');
  assert.equal(h.doc.visibilityState, 'hidden');
  assert.equal(h.root.getAttribute('data-vis'), 'hidden');
  h.setVisibility('visible');
  assert.equal(h.root.getAttribute('data-vis'), 'visible');
  assert.equal(boot({ visibility: 'hidden' }).root.getAttribute('data-vis'), 'hidden', '最初から hidden で開ける');
});

test('D0017-AC-30: matchMedia は reducedMotion の指定のとおりに reduce・no-preference へ答える', () => {
  const normal = boot();
  assert.equal(normal.root.getAttribute('data-reduce'), 'false');
  assert.equal(normal.root.getAttribute('data-nopref'), 'true');
  const reduced = boot({ reducedMotion: true });
  assert.equal(reduced.root.getAttribute('data-reduce'), 'true');
  assert.equal(reduced.root.getAttribute('data-nopref'), 'false');
});

test('D0017-AC-22: textContent に代入すると子が 1 つの文字に替わり、空にすると子が無くなる', () => {
  const h = boot();
  h.root.textContent = 'abc';
  assert.equal(h.root.children.length, 1);
  assert.equal(h.root.textContent, 'abc');
  h.root.textContent = '';
  assert.equal(h.root.children.length, 0);
  assert.equal(h.root.textContent, '');
});

// ---- D0019（2版目）で足した補助の確認：入力欄の value・選択範囲、スクロール、変換中の入力、枠の高さ、隠れているかの見分け ----

const FORM_SCRIPT = `
const root = document.querySelector('.root');
window.addEventListener('message', function (e) { if (e.data && e.data.html !== undefined) root.innerHTML = e.data.html; });
const seen = [];
function note(text) { seen.push(text); root.setAttribute('data-seen', seen.join('|')); }
root.addEventListener('input', function (e) { note('input:' + e.target.value + ':' + e.isComposing + ':' + e.data); });
root.addEventListener('compositionstart', function () { note('start'); });
root.addEventListener('compositionend', function (e) { note('end:' + e.data); });
`;
const formPage = `<!DOCTYPE html><html><body><div class="root"><input type="search" data-keep="filter"><div data-scroll="list" class="scroll"><span id-x="a" class="inner"></span></div><section hidden><p class="deep">x</p></section></div><script nonce="x">${FORM_SCRIPT}</script></body></html>`;

test('D0019-AC-65: 入力欄の value は代入すると選択範囲が末尾に移り、setSelectionRange は範囲に収まる（日本語 1 文字は 1）', () => {
  const h = bootPanel(formPage);
  const input = h.doc.querySelector('input')!;
  assert.equal(input.value, '');
  input.value = 'あいう';
  assert.equal(input.selectionStart, 3);
  assert.equal(input.selectionEnd, 3);
  input.setSelectionRange(1, 2);
  assert.deepEqual([input.selectionStart, input.selectionEnd], [1, 2]);
  input.setSelectionRange(2, 99);
  assert.deepEqual([input.selectionStart, input.selectionEnd], [2, 3], '末尾を超えない');
  input.value = 'a';
  assert.deepEqual([input.selectionStart, input.selectionEnd], [1, 1]);
});

test('D0019-AC-65: scrollTop は、枠の高さが分からないうちはそのまま、分かるときは 0〜(scrollHeight - clientHeight) に収まる', () => {
  const plain = bootPanel(formPage);
  const free = plain.doc.querySelector('[data-scroll="list"]')!;
  free.scrollTop = 500;
  assert.equal(free.scrollTop, 500);
  free.scrollTop = -20;
  assert.equal(free.scrollTop, 0, '負にはならない');

  const sized = bootPanel(formPage, { layout: (n) => (n.getAttribute('data-scroll') === 'list' ? { scrollHeight: 1000, clientHeight: 200 } : null) });
  const box = sized.doc.querySelector('[data-scroll="list"]')!;
  assert.equal(box.scrollHeight, 1000);
  assert.equal(box.clientHeight, 200);
  box.scrollTop = 300;
  assert.equal(box.scrollTop, 300);
  box.scrollTop = 99999;
  assert.equal(box.scrollTop, 800, '最大は scrollHeight - clientHeight');
  box.scrollLeft = 12;
  assert.equal(box.scrollLeft, 12);
});

test('D0019-AC-65: layout は render のあとに作られる節にも当たる（作り直された枠も同じ高さを持つ）', () => {
  const h = bootPanel(formPage, { layout: (n) => (n.getAttribute('data-scroll') === 'list' ? { scrollHeight: 600, clientHeight: 100 } : null) });
  h.send({ html: '<div data-scroll="list"></div><div data-scroll="other"></div>' });
  const again = h.doc.querySelector('[data-scroll="list"]')!;
  assert.equal(again.scrollHeight, 600);
  assert.equal(again.scrollTop, 0, '作り直された枠は先頭から');
  assert.equal(h.doc.querySelector('[data-scroll="other"]')!.scrollHeight, 0);
});

test('D0019-AC-65: typeText は value を替えて input を届け、変換中（composing）かと入力した文字も届ける。compositionstart・end も届く', () => {
  const h = bootPanel(formPage);
  const input = h.doc.querySelector('input')!;
  h.typeText(input, 'ab');
  input.dispatch('compositionstart');
  h.typeText(input, 'に', true);
  input.dispatch('compositionend', { data: 'に' });
  assert.equal(h.root.getAttribute('data-seen'), 'input:ab:false:ab|start|input:に:true:に|end:に');
  assert.equal(input.value, 'に');
  assert.deepEqual(h.posted, []);
});

test('D0019-AC-65: closest("[hidden]") は、自分か祖先に hidden があれば それを返し、無ければ null（隠れているかを見る道）', () => {
  const h = bootPanel(formPage);
  const deep = h.doc.querySelector('.deep')!;
  assert.ok(deep.closest('[hidden]') !== null, '祖先が hidden');
  const hiddenSection = h.doc.querySelector('section')!;
  assert.ok(hiddenSection.closest('[hidden]') === hiddenSection, '自分が hidden');
  assert.ok(h.doc.querySelector('input')!.closest('[hidden]') === null);
  hiddenSection.hidden = false;
  assert.ok(deep.closest('[hidden]') === null, 'hidden を外せば見える');
});

test('D0019-AC-79: dispatch は ctrlKey・metaKey・deltaY を届け（付けなければ false・false・0）、preventDefault の有無を返す', () => {
  const h = bootPanel(formPage);
  const seen: string[] = [];
  h.root.addEventListener('wheel', (e) => {
    seen.push(`${e.ctrlKey}:${e.metaKey}:${e.deltaY}`);
    if (e.ctrlKey === true) e.preventDefault();
  });
  const plain = h.root.dispatch('wheel', { deltaY: 40 });
  const ctrl = h.root.dispatch('wheel', { ctrlKey: true, deltaY: -100 });
  const meta = h.root.dispatch('wheel', { metaKey: true, deltaY: -1 });
  assert.deepEqual(seen, ['false:false:40', 'true:false:-100', 'false:true:-1']);
  assert.equal(plain.defaultPrevented, false);
  assert.equal(ctrl.defaultPrevented, true);
  assert.equal(meta.defaultPrevented, false);
});

test('D0017-AC-29: getAnimations は is-new が付いている間だけ 1 つの動きを返し、外すと空。noAnimations では持たない', () => {
  const h = boot();
  const el = h.root;
  assert.deepEqual(el.getAnimations!(), []);
  el.classList.add('is-new');
  const first = el.getAnimations!();
  assert.equal(first.length, 1);
  first[0].currentTime = 600;
  assert.equal(el.getAnimations!()[0].currentTime, 600, '同じ動きを返す');
  el.classList.remove('is-new');
  assert.deepEqual(el.getAnimations!(), []);
  assert.equal(boot({ noAnimations: true }).root.getAnimations, undefined);
});

// ---- D0025 で足した補助の確認：本物と同じ SyntaxError・offsetTop／offsetHeight・hidden にした節の中のスクロール位置 ----
// 今のまま通る（補助そのものの確かめ。守り続けるために置く）。成果物のタブのテストが、名前を連ねたセレクタを見つけ、選んだ行を枠の中へ寄せる動きを試し、
// 別のタブへ移って戻ったときに位置が本当に記憶から戻っていることを見分けるための部品。

const NOTE = '（今のまま通る。守る）';
/** 空のスクリプトで、body の中身だけを替えたページ */
const pageOf = (body: string): string =>
  `<!DOCTYPE html><html><body><div class="root">${body}</div><script nonce="x">void 0;</script></body></html>`;

const BAD_SELECTORS: readonly (readonly [label: string, selector: string])[] = [
  ['値の引用符が途中で閉じ、あとに文字が続く（名前に " が入った連ねた形）', '[data-x="a"b"]'],
  ['引用符のない値に " が入る', '[data-x=a"b]'],
  ["引用符のない値に ' が入る", "[data-x=a'b]"],
  ['閉じていない "', '[data-x="a]'],
  ["閉じていない '", "[data-x='a]"],
  ['引用符のない値のあとに ] が余る', '[data-x=a]b]'],
  ['閉じる ] が無い', '[data-x="a"'],
  ['] のあとにあまった文字', '[data-x="a"]x'],
  ['数字で始まる引用符のない値（本物も SyntaxError）', '[data-x=1]'],
  ['引用符のない値に空白が入る', '[data-x=a b]'],
  ['空のセレクタ', ''],
  ['空の部分（, が続く）', '.a,,.b'],
  ['子孫の組み合わせ（偽物が未対応）', '.a .b'],
];

for (const [label, selector] of BAD_SELECTORS) {
  test(`D0025-AC-64: 偽の DOM の querySelector は、${label}（${selector}）で SyntaxError を投げる${NOTE}`, () => {
    const h = bootPanel(pageOf('<i data-x="a"></i>'));
    assert.throws(() => h.root.querySelector(selector), SyntaxError);
  });
}

test('D0025-AC-64: querySelectorAll・closest・matches も同じ SyntaxError を投げる。合う節が無い（子が無い）木でも、呼んだ時点で投げる' + NOTE, () => {
  const h = bootPanel(pageOf(''));
  const bad = '[data-x="a"b"]';
  assert.equal(h.root.children.length, 0, '比べる節が無い木');
  assert.throws(() => h.root.querySelectorAll(bad), SyntaxError);
  assert.throws(() => h.root.querySelector(bad), SyntaxError);
  assert.throws(() => h.root.closest(bad), SyntaxError);
  assert.throws(() => h.root.matches(bad), SyntaxError);
});

test('D0025-AC-64: 名前を連ねたセレクタは、名前に " が入ると SyntaxError になる。等値比較の形（getAttribute(…) === 名前）なら同じ名前でも探せる' + NOTE, () => {
  const h = bootPanel(pageOf('<i data-x="a&quot;b"></i><i data-x="c"></i>'));
  const name = 'a"b';
  assert.throws(() => h.root.querySelector('[data-x="' + name + '"]'), SyntaxError, '連ねると壊れる');
  const found = Array.from(h.root.querySelectorAll('[data-x]')).find((n) => n.getAttribute('data-x') === name);
  assert.ok(found !== undefined);
  assert.equal(found.getAttribute('data-x'), name);
});

const GOOD_SELECTORS: readonly (readonly [label: string, selector: string, expected: readonly string[]])[] = [
  ['引用符のない識別子の値', '[data-x=a]', ['a']],
  ['空白を含む値（"…"）', '[data-x="a b"]', ['a b']],
  ["値の中の \" を ' で囲む", '[data-x=\'a"b\']', ['a"b']],
  ['値の中の " を \\ で逃がす', '[data-x="a\\"b"]', ['a"b']],
  ["値の中の ' を \" で囲む", '[data-x="a\'b"]', ["a'b"]],
  ['値の中の ]（引用符の中）', '[data-x="a]b"]', ['a]b']],
  ['値の中の ,（引用符の中は分けない）', '[data-x="a,b"]', ['a,b']],
  ['値の中の \\ を \\\\ で逃がす', '[data-x="a\\\\b"]', ['a\\b']],
  ['引用符のない値の中の " を \\ で逃がす', '[data-x=a\\"b]', ['a"b']],
  [', で並べる（文書の順に返す）', '[data-x="a"], [data-x="a b"]', ['a', 'a b']],
];

for (const [label, selector, expected] of GOOD_SELECTORS) {
  test(`D0025-AC-64: 本物が使えるセレクタは偽の DOM でも使える：${label}（${selector}）${NOTE}`, () => {
    const h = bootPanel(
      pageOf(
        [
          '<i data-x="a"></i>',
          '<i data-x="a b"></i>',
          '<i data-x="a&quot;b"></i>',
          '<i data-x="a&#39;b"></i>',
          '<i data-x="a]b"></i>',
          '<i data-x="a,b"></i>',
          '<i data-x="a\\b"></i>',
        ].join(''),
      ),
    );
    assert.deepEqual(
      h.root.querySelectorAll(selector).map((n) => n.getAttribute('data-x')),
      expected,
    );
  });
}

test('D0025-AC-64: getAttribute は " \' & < > \\ を壊さずに返す（HTML の文字参照からも setAttribute からも）。&amp;lt; は &lt; の文字のまま、二重に戻さない' + NOTE, () => {
  const h = bootPanel(pageOf('<i data-x="&quot;&#39;&amp;&lt;&gt;\\ ]"></i><i data-y="&amp;lt;"></i>'));
  const el = h.root.querySelector('i')!;
  assert.equal(el.getAttribute('data-x'), `"'&<>\\ ]`);
  assert.equal(h.root.querySelectorAll('i')[1].getAttribute('data-y'), '&lt;');
  el.setAttribute('data-x', `"'&<>\\ ]`);
  assert.equal(el.getAttribute('data-x'), `"'&<>\\ ]`);
});

test('D0025-AC-64: layout が offsetTop・offsetHeight を決める（決めなければ 0）。render のあとに作られる節にも当たる' + NOTE, () => {
  const layout = (n: FakeNode) => {
    const row = n.getAttribute('data-row');
    if (row === 'a') return { offsetTop: 0, offsetHeight: 56 };
    if (row === 'b') return { offsetTop: 60, offsetHeight: 56, scrollHeight: 300, clientHeight: 100 };
    return null;
  };
  const h = bootPanel(pageOf('<ul data-scroll="list"><li data-row="a"></li><li data-row="b"></li><li data-row="c"></li></ul>'), { layout });
  const rows = h.root.querySelectorAll('li');
  assert.deepEqual(
    rows.map((r) => [r.offsetTop, r.offsetHeight]),
    [
      [0, 56],
      [60, 56],
      [0, 0],
    ],
  );
  assert.equal(rows[1].scrollHeight, 300, 'これまでの scrollHeight・clientHeight も同じ layout で決まる');
  assert.equal(rows[1].clientHeight, 100);
  assert.deepEqual([h.root.offsetTop, h.root.offsetHeight], [0, 0], 'layout が決めない節は 0');
  h.root.innerHTML = '<li data-row="b"></li>';
  const again = h.root.querySelector('li')!;
  assert.deepEqual([again.offsetTop, again.offsetHeight], [60, 56], '作り直された節も同じ位置');
});

const HIDE_WAYS: readonly (readonly [label: string, hide: (node: FakeNode) => void])[] = [
  ['hidden = true', (node) => void (node.hidden = true)],
  ["setAttribute('hidden', '')", (node) => node.setAttribute('hidden', '')],
];

for (const [label, hide] of HIDE_WAYS) {
  test(`D0025-AC-64: ${label} で隠した節の中の枠は、縦横のスクロール位置が 0 に戻り、見せ直しても戻らない。隠していない枠は動かない${NOTE}`, () => {
    const layout = (n: FakeNode) => (n.getAttribute('data-scroll') !== null ? { scrollHeight: 1000, clientHeight: 200 } : null);
    const h = bootPanel(
      pageOf(
        '<section data-tab="a"><div data-scroll="outer"><div data-scroll="inner"></div></div></section>' +
          '<section data-tab="b"><div data-scroll="other"></div></section>',
      ),
      { layout },
    );
    const section = h.root.querySelector('section[data-tab="a"]')!;
    const outer = h.root.querySelector('[data-scroll="outer"]')!;
    const inner = h.root.querySelector('[data-scroll="inner"]')!;
    const other = h.root.querySelector('[data-scroll="other"]')!;
    outer.scrollTop = 300;
    outer.scrollLeft = 40;
    inner.scrollTop = 50;
    other.scrollTop = 70;
    other.scrollLeft = 5;

    hide(section);
    assert.deepEqual([outer.scrollTop, outer.scrollLeft], [0, 0], '隠した節の中の枠');
    assert.deepEqual([inner.scrollTop, inner.scrollLeft], [0, 0], '入れ子の枠も');
    assert.deepEqual([other.scrollTop, other.scrollLeft], [70, 5], '隠していない節の枠は動かない');

    section.hidden = false;
    assert.deepEqual([outer.scrollTop, outer.scrollLeft], [0, 0], '見せ直しても、元の位置には戻らない');
  });
}

test('D0025-AC-64: 枠そのものを隠してもその枠の位置が 0 に戻る。隠していない枠の hidden = false は位置を動かさない' + NOTE, () => {
  const layout = (n: FakeNode) => (n.getAttribute('data-scroll') !== null ? { scrollHeight: 1000, clientHeight: 200 } : null);
  const h = bootPanel(pageOf('<div data-scroll="box"></div>'), { layout });
  const box = h.root.querySelector('[data-scroll="box"]')!;
  box.scrollTop = 300;
  box.hidden = false;
  assert.equal(box.scrollTop, 300, '隠していないので動かない');
  box.hidden = true;
  assert.equal(box.scrollTop, 0, '枠そのものを隠した');
});

// 隠れている（hidden の中の）あいだは、本物の display: none と同じに、大きさが 0 で、スクロール位置を書いても残らない。
// 「見えていないあいだは選んだ行へ寄せず、見えたときに寄せる」動き（AC-62）が、起動時（成果物のタブは初めは hidden）の寄せで使い切る実装を見分けるための部品。

const HIDDEN_PLACES: readonly (readonly [label: string, html: string, pickHidden: (h: ReturnType<typeof bootPanel>) => FakeNode])[] = [
  [
    '祖先の節が hidden',
    '<section data-tab="a" hidden><div data-scroll="box"><i data-row="r"></i></div></section>',
    (h) => h.root.querySelector('section')!,
  ],
  [
    '枠そのものが hidden',
    '<div data-scroll="box" hidden><i data-row="r"></i></div>',
    (h) => h.root.querySelector('[data-scroll="box"]')!,
  ],
];

for (const [label, html, pickHidden] of HIDDEN_PLACES) {
  test(`D0025-AC-62: ${label}のあいだは、枠の scrollHeight・clientHeight と行の offsetTop・offsetHeight が 0 で、scrollTop・scrollLeft に書いても残らない。見せると大きさが戻り、書き込みも効く${NOTE}`, () => {
    const layout = (n: FakeNode) => {
      if (n.getAttribute('data-row') !== null) return { offsetTop: 60, offsetHeight: 56 };
      return n.getAttribute('data-scroll') !== null ? { scrollHeight: 1000, clientHeight: 200 } : null;
    };
    const h = bootPanel(pageOf(html), { layout });
    const hiding = pickHidden(h);
    const box = h.root.querySelector('[data-scroll="box"]')!;
    const row = h.root.querySelector('[data-row]')!;
    const sizes = (): number[] => [box.scrollHeight, box.clientHeight, row.offsetTop, row.offsetHeight];
    assert.deepEqual(sizes(), [0, 0, 0, 0], '隠れているあいだは 0');
    box.scrollTop = 300;
    box.scrollLeft = 40;
    assert.deepEqual([box.scrollTop, box.scrollLeft], [0, 0], '書いても残らない');

    hiding.hidden = false;
    assert.deepEqual(sizes(), [1000, 200, 60, 56], '見せると layout の大きさに戻る');
    assert.deepEqual([box.scrollTop, box.scrollLeft], [0, 0], '隠れているあいだに書いた位置は残っていない');
    box.scrollTop = 300;
    box.scrollLeft = 40;
    assert.deepEqual([box.scrollTop, box.scrollLeft], [300, 40], '見えているので書ける');

    hiding.hidden = true;
    assert.deepEqual(sizes(), [0, 0, 0, 0], '隠し直すとまた 0');
    assert.deepEqual([box.scrollTop, box.scrollLeft], [0, 0]);
  });
}

// focus() は、本物と同じに、hidden の中の節と disabled の要素には効かない（AC-61：焦点のあった先が隠れた・押せなくなったとき、body に落ちる）

test(`D0025-AC-61: focus() は、hidden の中の節と disabled の要素には効かず、activeElement は替わらない。見えていて押せる要素には効く${NOTE}`, () => {
  const h = bootPanel(pageOf('<button data-t="ok"></button><section hidden><button data-t="inHidden"></button></section><button data-t="off" disabled></button>'));
  const pick = (id: string): FakeNode => h.root.querySelector(`[data-t="${id}"]`)!;
  assert.equal(h.doc.activeElement, null);
  pick('inHidden').focus();
  assert.equal(h.doc.activeElement, null, 'hidden の中には移らない');
  pick('off').focus();
  assert.equal(h.doc.activeElement, null, 'disabled には移らない');
  pick('ok').focus();
  assert.ok(h.doc.activeElement === pick('ok'), '見えていて押せる要素には移る');
  pick('inHidden').focus();
  pick('off').focus();
  assert.ok(h.doc.activeElement === pick('ok'), '効かなかったとき、前の焦点のまま');
  h.root.querySelector('section')!.hidden = false;
  pick('inHidden').focus();
  assert.ok(h.doc.activeElement === pick('inHidden'), '見せれば移る');
  pick('off').removeAttribute('disabled');
  pick('off').focus();
  assert.ok(h.doc.activeElement === pick('off'), 'disabled を外せば移る');
});
