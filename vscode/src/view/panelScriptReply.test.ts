// パネルのスクリプトの、確認待ちの帯の返事の部分（D0079・AC-42・43）：PANEL_SCRIPT を node:vm で、偽の DOM（src/test/fakeDom.ts）の上で動かす。
// 帯の中の状態は、最初（choose）・修正の入力（revise）・中止の確かめ（confirm）・送った（sent）の 4 つで、パネルのスクリプトの変数だけで持つ（保存しない）。
// 約 5 秒ごとの描き直しでは、帯の識別子（data-reply-id）が同じなら入力中の文字・確かめの途中・送ったあとの表示を保ち、識別子が替わる・帯が無くなると最初に戻す。
// 帯の HTML は設計の約束（data-reply-id・data-reply-sent・data-reply-stalled・data-reply-pane・data-reply・data-keep="reply-feedback"）どおりに、このテストの中で手で書く
// （スクリプトと HTML の部品が別々に直っても約束で結ばれていることを見る）。最後に、本物の帯の HTML（view/replyHtml.ts）でも通す。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';
import { bootPanel, FakeNode } from '../test/fakeDom.ts';
import type { PanelHarness } from '../test/fakeDom.ts';
import { finishedView } from '../test/liveFixtures.ts';
import { MARK_ID, NEXT_ID, replyView } from '../test/replyFixtures.ts';
import { listView, sampleRows } from '../test/runListFixtures.ts';

const NONCE = 'TESTNONCE';
const LIST = listView(sampleRows(), { selected: 'here|survey' });

/** 設計 2.9 の約束どおりの、確認待ちの帯の HTML（手で書く）。 */
function replyBody(o: { id?: string; sent?: boolean; stalled?: boolean } = {}): string {
  const id = o.id ?? MARK_ID;
  const sent = o.sent === true;
  return (
    `<div class="notice" role="status" data-reply-id="${id}" data-reply-sent="${sent ? 1 : 0}" data-reply-stalled="${o.stalled === true ? 1 : 0}">` +
    '<strong>要件定義の確認を待っている：01_requirements.md</strong>' +
    `<div class="reply" data-reply-pane="choose"${sent ? ' hidden' : ''}>` +
    '<button type="button" class="reply-primary" data-reply="approve">承認</button>' +
    '<button type="button" class="secondary" data-reply="revise-open">修正を依頼</button>' +
    '<button type="button" class="secondary" data-reply="quit-open">中止</button></div>' +
    '<div class="reply" data-reply-pane="revise" hidden>' +
    '<textarea class="reply-input" data-keep="reply-feedback" rows="3" aria-label="直してほしい点"></textarea>' +
    '<span class="notice-sub">1,000 文字まで</span>' +
    '<button type="button" class="reply-primary" data-reply="revise-send" disabled>送る</button>' +
    '<button type="button" class="secondary" data-reply="back">戻る</button></div>' +
    '<div class="reply" data-reply-pane="confirm" hidden><span>本当に中止しますか</span>' +
    '<button type="button" class="secondary" data-reply="quit-send">中止する</button>' +
    '<button type="button" class="secondary" data-reply="back">戻る</button></div>' +
    `<div class="reply" data-reply-pane="sent"${sent ? '' : ' hidden'}><span class="reply-sent">送りました（pipe-in が読むのを待っています）</span></div>` +
    '</div>'
  );
}
/** 帯が無い本体（待ちが終わって次の段が動いている、など） */
const NO_NOTICE = '<p class="banner-msg is-running">いま：設計</p>';

function boot(html: string = replyBody()): PanelHarness {
  const h = bootPanel(renderPanelHtml(finishedView(), NONCE, LIST));
  h.send({ type: 'render', html });
  return h;
}
const render = (h: PanelHarness, html: string): void => h.send({ type: 'render', html });

const paneEls = (h: PanelHarness): FakeNode[] => h.doc.querySelectorAll('[data-reply-pane]');
/** 見えている枠の名前（hidden が自分にも祖先にも無いもの） */
const shownPanes = (h: PanelHarness): string[] => paneEls(h).filter((p) => p.closest('[hidden]') === null).map((p) => p.getAttribute('data-reply-pane')!);
/** 見えているボタン（同じ data-reply が複数あるとき、見えている方） */
const button = (h: PanelHarness, name: string): FakeNode => {
  const found = h.doc.querySelectorAll('button[data-reply]').filter((b) => b.getAttribute('data-reply') === name && b.closest('[hidden]') === null);
  assert.equal(found.length, 1, `見えている「${name}」のボタンが 1 つある（${found.length} 個）`);
  return found[0]!;
};
/** 隠れていても取る（押せない道を試す） */
const anyButton = (h: PanelHarness, name: string): FakeNode => {
  const found = h.doc.querySelectorAll('button[data-reply]').find((b) => b.getAttribute('data-reply') === name);
  assert.ok(found, `「${name}」のボタンがある`);
  return found;
};
const textarea = (h: PanelHarness): FakeNode => {
  const el = h.doc.querySelector('textarea[data-keep="reply-feedback"]');
  assert.ok(el, '直してほしい点の入力欄がある');
  return el;
};
const click = (h: PanelHarness, name: string): void => void button(h, name).dispatch('click');
const replies = (h: PanelHarness): unknown[] => h.posted.filter((m) => (m as { type?: string }).type === 'reply');
const sendDisabled = (h: PanelHarness): boolean => anyButton(h, 'revise-send').disabled;

// ---- AC-42：操作と、送る知らせ ----

test('D0079-AC-42: 最初は 3 つのボタンだけが見える。「承認」を押すと { type: reply, action: approve } だけが送られ、「送りました」だけが見える', () => {
  const h = boot();
  assert.deepEqual(shownPanes(h), ['choose']);
  click(h, 'approve');
  assert.deepEqual(replies(h), [{ type: 'reply', action: 'approve' }]);
  assert.deepEqual(shownPanes(h), ['sent']);
});

test('D0079-AC-42: 「修正を依頼」を押すと入力欄と「送る」「戻る」が出る（まだ送らない）。空・空白だけのあいだ「送る」は押せず、書くと押せて、前後の空白を取った文字だけが送られる', () => {
  const h = boot();
  click(h, 'revise-open');
  assert.deepEqual(shownPanes(h), ['revise']);
  assert.deepEqual(replies(h), []);
  assert.equal(sendDisabled(h), true, '空');
  h.typeText(textarea(h), '   \n\t  ');
  assert.equal(sendDisabled(h), true, '空白だけ');
  h.typeText(textarea(h), '  ここを直して\n次も  ');
  assert.equal(sendDisabled(h), false, '書くと押せる');
  click(h, 'revise-send');
  assert.deepEqual(replies(h), [{ type: 'reply', action: 'revise', feedback: 'ここを直して\n次も' }]);
  assert.deepEqual(shownPanes(h), ['sent']);
});

test('D0079-AC-42: 押せない「送る」を押しても何も送られない（disabled のボタンへの click）', () => {
  const h = boot();
  click(h, 'revise-open');
  anyButton(h, 'revise-send').dispatch('click');
  h.typeText(textarea(h), '  ');
  anyButton(h, 'revise-send').dispatch('click');
  assert.deepEqual(replies(h), []);
  assert.deepEqual(shownPanes(h), ['revise']);
});

test('D0079-AC-42: 直してほしい点は 1000 文字（コードポイント）まで：絵文字 1000 個（UTF-16 では 2000）は送れ、1001 個は「送る」が押せない', () => {
  const h = boot();
  click(h, 'revise-open');
  h.typeText(textarea(h), '😀'.repeat(1000));
  assert.equal(sendDisabled(h), false, '絵文字 1000 個');
  h.typeText(textarea(h), '😀'.repeat(1001));
  assert.equal(sendDisabled(h), true, '絵文字 1001 個');
  h.typeText(textarea(h), 'a'.repeat(1000));
  assert.equal(sendDisabled(h), false, 'a 1000 個');
  h.typeText(textarea(h), 'a'.repeat(1001));
  assert.equal(sendDisabled(h), true, 'a 1001 個');
  h.typeText(textarea(h), `　${'a'.repeat(1000)}　`);
  assert.equal(sendDisabled(h), false, '前後の空白を取ると 1000 文字');
});

test('D0079-AC-42: 「戻る」で最初の 3 つのボタンに戻り、書いた文字は残らない（開き直すと空で、「送る」は押せない）', () => {
  const h = boot();
  click(h, 'revise-open');
  h.typeText(textarea(h), '書きかけ');
  click(h, 'back');
  assert.deepEqual(shownPanes(h), ['choose']);
  assert.deepEqual(replies(h), []);
  click(h, 'revise-open');
  assert.equal(textarea(h).value, '');
  assert.equal(sendDisabled(h), true);
});

test('D0079-AC-42: 「中止」を押すとすぐには送られず、「本当に中止しますか」と「中止する」「戻る」が出る。「戻る」で最初に戻り何も送られず、「中止する」で { type: reply, action: quit } だけが送られる', () => {
  const h = boot();
  click(h, 'quit-open');
  assert.deepEqual(shownPanes(h), ['confirm']);
  assert.deepEqual(replies(h), []);
  click(h, 'back');
  assert.deepEqual(shownPanes(h), ['choose']);
  assert.deepEqual(replies(h), []);
  click(h, 'quit-open');
  click(h, 'quit-send');
  assert.deepEqual(replies(h), [{ type: 'reply', action: 'quit' }]);
  assert.deepEqual(shownPanes(h), ['sent']);
});

test('D0079-AC-42: 送ったあとは、同じ確認にもう一度送れない（隠れたボタンを押しても送られない）', () => {
  const h = boot();
  click(h, 'approve');
  anyButton(h, 'approve').dispatch('click');
  anyButton(h, 'quit-open').dispatch('click');
  anyButton(h, 'quit-send').dispatch('click');
  assert.equal(replies(h).length, 1);
  assert.deepEqual(shownPanes(h), ['sent']);
});

test('D0079-AC-42: 帯のボタン以外のメッセージを送らない：増える type は reply だけ（ready・openArtifact・selectRun のほかは reply だけ）', () => {
  const h = boot();
  click(h, 'revise-open');
  h.typeText(textarea(h), '直して');
  click(h, 'revise-send');
  const types = new Set(h.posted.map((m) => (m as { type: string }).type));
  assert.deepEqual([...types].sort(), ['ready', 'reply']);
});

// ---- AC-42：識別子が同じ描き直しで保たれる ----

test('D0079-AC-42: 識別子が同じ描き直しで、「修正を依頼」の入力中の文字と、押せる「送る」が保たれる', () => {
  const h = boot();
  click(h, 'revise-open');
  h.typeText(textarea(h), 'ここを直して');
  render(h, replyBody());
  assert.deepEqual(shownPanes(h), ['revise']);
  assert.equal(textarea(h).value, 'ここを直して');
  assert.equal(sendDisabled(h), false);
  render(h, replyBody());
  assert.equal(textarea(h).value, 'ここを直して');
  click(h, 'revise-send');
  assert.deepEqual(replies(h), [{ type: 'reply', action: 'revise', feedback: 'ここを直して' }]);
});

test('D0079-AC-42: 識別子が同じ描き直しで、入力欄の焦点と選択範囲も戻る（data-keep の仕組み）', () => {
  const h = boot();
  click(h, 'revise-open');
  h.typeText(textarea(h), '0123456789');
  textarea(h).focus();
  textarea(h).setSelectionRange(2, 5);
  render(h, replyBody());
  assert.ok(h.doc.activeElement === textarea(h), '焦点が新しい入力欄に戻る');
  assert.equal(textarea(h).value, '0123456789');
  assert.deepEqual([textarea(h).selectionStart, textarea(h).selectionEnd], [2, 5]);
});

test('D0079-AC-42: 識別子が同じ描き直しで、「中止」の確かめの途中が保たれる', () => {
  const h = boot();
  click(h, 'quit-open');
  render(h, replyBody());
  assert.deepEqual(shownPanes(h), ['confirm']);
  click(h, 'quit-send');
  assert.deepEqual(replies(h), [{ type: 'reply', action: 'quit' }]);
});

test('D0079-AC-42: 識別子が同じ描き直しで、送ったあとの表示が保たれる（ファイルがまだ見えない描き直しでも、見えた描き直しでも「送りました」のまま）', () => {
  const h = boot();
  click(h, 'approve');
  render(h, replyBody({ sent: false }));
  assert.deepEqual(shownPanes(h), ['sent'], '押した直後でまだファイルが見えない');
  render(h, replyBody({ sent: true }));
  assert.deepEqual(shownPanes(h), ['sent'], 'ファイルが見えた');
  render(h, replyBody({ sent: true, stalled: true }));
  assert.deepEqual(shownPanes(h), ['sent'], '30 秒たった');
  assert.equal(replies(h).length, 1);
});

test('D0079-AC-42: パネルを開き直した直後（このパネルでは何も押していない）でも、サーバーが送ったあと（data-reply-sent=1）と言う帯は「送りました」を見せる（HTML が決めるので、今のまま通る。守る）', () => {
  const h = boot(replyBody({ sent: true }));
  assert.deepEqual(shownPanes(h), ['sent']);
  assert.deepEqual(replies(h), []);
  render(h, replyBody({ sent: true }));
  assert.deepEqual(shownPanes(h), ['sent'], '再描画のあともボタンが戻らない');
});

// ---- AC-42 の支え：日本語入力の変換中 ----

test('D0079-AC-42: 日本語入力の変換中に描き直しが来ても、返事の入力欄を作り直さず、変換が終わったあとに 1 回だけ（最後の描き直しを）適用する', () => {
  const h = boot();
  click(h, 'revise-open');
  const proto = Object.getOwnPropertyDescriptor(FakeNode.prototype, 'innerHTML');
  assert.ok(proto?.set, '偽の DOM の innerHTML の代入口');
  let sets = 0;
  let last = '';
  Object.defineProperty(h.root, 'innerHTML', {
    configurable: true,
    set(this: FakeNode, html: string) {
      sets++;
      last = html;
      proto.set!.call(this, html);
    },
  });
  const input = textarea(h);
  input.focus();
  input.dispatch('compositionstart');
  h.typeText(input, 'なおし', true);
  render(h, replyBody());
  render(h, replyBody({ stalled: false, sent: false }).replace('要件定義', '要件定義（更新）'));
  assert.equal(sets, 0, '変換中は入力を作り直さない');
  assert.ok(textarea(h) === input, '同じ入力のまま');
  assert.equal(input.value, 'なおし', '変換中の文字が消えない');
  input.dispatch('compositionend', { data: 'なおし' });
  assert.equal(sets, 1, '終わったあとに 1 回だけ適用する');
  assert.ok(last.includes('要件定義（更新）'), '最後に来た描き直しを適用する');
  assert.equal(textarea(h).value, 'なおし', '変換した文字が残る');
  assert.deepEqual(shownPanes(h), ['revise']);
  assert.equal(sendDisabled(h), false, '変換した文字で「送る」が押せる');
  click(h, 'revise-send');
  assert.deepEqual(replies(h), [{ type: 'reply', action: 'revise', feedback: 'なおし' }]);
});

test('D0079-AC-42: 変換の途中で入力欄から焦点が外れたときも、変換を終えたものとして取っておいた描き直しを適用する', () => {
  const h = boot();
  click(h, 'revise-open');
  const input = textarea(h);
  input.focus();
  input.dispatch('compositionstart');
  h.typeText(input, 'なお', true);
  render(h, replyBody());
  input.dispatch('focusout');
  assert.equal(textarea(h).value, 'なお');
  assert.deepEqual(shownPanes(h), ['revise']);
  assert.equal(sendDisabled(h), false);
});

// ---- AC-43：識別子が替わる・帯が消える・ファイルが消える ----

test('D0079-AC-43: 識別子が替わる描き直し（別の待ち）で、入力中の文字が消え、最初の 3 つのボタンに戻る', () => {
  const h = boot();
  click(h, 'revise-open');
  h.typeText(textarea(h), '前の待ちへの文字');
  assert.deepEqual(shownPanes(h), ['revise'], '前の待ちで修正の入力まで進んでいる');
  render(h, replyBody({ id: NEXT_ID }));
  assert.deepEqual(shownPanes(h), ['choose']);
  click(h, 'revise-open');
  assert.equal(textarea(h).value, '', '前の待ちの文字は残らない');
  assert.equal(sendDisabled(h), true);
});

test('D0079-AC-43: 識別子が替わる描き直しで、「中止」の確かめの途中が消えて最初に戻る', () => {
  const h = boot();
  click(h, 'quit-open');
  assert.deepEqual(shownPanes(h), ['confirm'], '前の待ちで中止の確かめまで進んでいる');
  render(h, replyBody({ id: NEXT_ID }));
  assert.deepEqual(shownPanes(h), ['choose']);
});

test('D0079-AC-43: 識別子が替わる描き直しで、送ったあとの表示が消えて、新しい確認の 3 つのボタンが押せる', () => {
  const h = boot();
  click(h, 'approve');
  render(h, replyBody({ id: NEXT_ID }));
  assert.deepEqual(shownPanes(h), ['choose']);
  click(h, 'approve');
  assert.deepEqual(replies(h), [
    { type: 'reply', action: 'approve' },
    { type: 'reply', action: 'approve' },
  ]);
});

test('D0079-AC-43: 待ちが終わって帯が消える描き直し（次の段が動く）のあと、同じ識別子の帯が戻っても、入力中の文字と途中の状態は消えている', () => {
  const h = boot();
  click(h, 'revise-open');
  h.typeText(textarea(h), '消えるはずの文字');
  assert.deepEqual(shownPanes(h), ['revise'], '修正の入力まで進んでいる');
  render(h, NO_NOTICE);
  assert.deepEqual(paneEls(h), [], '帯が無い');
  render(h, replyBody());
  assert.deepEqual(shownPanes(h), ['choose']);
  click(h, 'revise-open');
  assert.equal(textarea(h).value, '');
  const g = boot();
  click(g, 'approve');
  assert.deepEqual(shownPanes(g), ['sent'], '送った表示まで進んでいる');
  render(g, NO_NOTICE);
  render(g, replyBody());
  assert.deepEqual(shownPanes(g), ['choose'], '送ったあとの表示も消える');
});

test('D0079-AC-43: 送ったあと返事のファイルが見えた（data-reply-sent=1）のに、同じ識別子で消えた（0）描き直しは、本体が断った印として最初の 3 つのボタンに戻る', () => {
  const h = boot();
  click(h, 'approve');
  render(h, replyBody({ sent: true }));
  assert.deepEqual(shownPanes(h), ['sent']);
  render(h, replyBody({ sent: false }));
  assert.deepEqual(shownPanes(h), ['choose']);
  click(h, 'approve');
  assert.equal(replies(h).length, 2, '断られたあとは、もう一度答えられる');
});

test('D0079-AC-43: 開き直したパネルで返事のファイルが見えていた（sent=1）あと、同じ識別子で消えた（0）描き直しも最初に戻る（HTML が決めるので、今のまま通る。守る）', () => {
  const h = boot(replyBody({ sent: true }));
  assert.deepEqual(shownPanes(h), ['sent']);
  assert.equal(anyButton(h, 'approve').closest('[hidden]') !== null, true, '送ったあとはボタンが隠れている');
  render(h, replyBody({ sent: false }));
  assert.deepEqual(shownPanes(h), ['choose']);
});

test('D0079-AC-43: 拡張が書くのを断った（replyRefused）知らせで、送る前の状態に戻る：承認は最初の 3 つ、修正の依頼は入力欄（書いた文字つき）', () => {
  const a = boot();
  click(a, 'approve');
  a.send({ type: 'replyRefused' });
  assert.deepEqual(shownPanes(a), ['choose']);
  const r = boot();
  click(r, 'revise-open');
  r.typeText(textarea(r), '直して');
  click(r, 'revise-send');
  assert.deepEqual(shownPanes(r), ['sent']);
  r.send({ type: 'replyRefused' });
  assert.deepEqual(shownPanes(r), ['revise']);
  assert.equal(textarea(r).value, '直して');
  assert.equal(sendDisabled(r), false);
  const q = boot();
  click(q, 'quit-open');
  click(q, 'quit-send');
  q.send({ type: 'replyRefused' });
  assert.ok(!shownPanes(q).includes('sent'), '送った表示のまま残らない');
});

test('D0079-AC-43: 帯が無いときに replyRefused が来ても何も起きない（例外を出さない）（今のまま通る。守る）', () => {
  const h = boot(NO_NOTICE);
  assert.doesNotThrow(() => h.send({ type: 'replyRefused' }));
  assert.deepEqual(paneEls(h), []);
});

// ---- 本物の帯の HTML（view/replyHtml.ts）でも同じに動く ----

test('D0079-AC-42: 本物の帯の HTML でも、修正の入力中の文字は同じ識別子の描き直しで保たれ、識別子が替わると消える', () => {
  const real = (sec: number) => replyView({}, sec);
  const h = bootPanel(renderPanelHtml(real(40), NONCE, LIST));
  click(h, 'revise-open');
  h.typeText(textarea(h), '実物の帯');
  h.send({ type: 'render', html: renderViewBody(real(45), LIST) });
  assert.equal(textarea(h).value, '実物の帯');
  assert.deepEqual(shownPanes(h), ['revise']);
  click(h, 'revise-send');
  assert.deepEqual(replies(h), [{ type: 'reply', action: 'revise', feedback: '実物の帯' }]);
});

test('D0079-AC-43: 本物の帯の HTML でも、識別子が替わる描き直し（次の待ちの帯）で最初の 3 つのボタンに戻る', () => {
  const h = bootPanel(renderPanelHtml(replyView(), NONCE, LIST));
  click(h, 'approve');
  assert.deepEqual(shownPanes(h), ['sent']);
  const next = replyView({ mark: { stage: 'requirements', id: NEXT_ID, since: '2026-10-17T10:01:00+00:00' } }, 45);
  h.send({ type: 'render', html: renderViewBody(next, LIST) });
  assert.deepEqual(shownPanes(h), ['choose']);
});
