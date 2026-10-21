// パネルの詳細の「⚠ 止まっているかも」のバッジと「この段のログが … 更新されていません」の知らせ（D0021・AC-31・32・33）。純粋な文字列の検査。
// 一覧の選んだ行（RunRow）の quietSec から作る。行に quietSec を入れて renderShell に目安の秒を渡す（記録の写しは通さない。写しから行を作る側は domain/runListStale.test.ts）。
// 「出ない側」の確かめには、同じ入力に出る条件だけを足した対照を付ける（空振りを防ぐ）。確認待ちの知らせ・メタの「最後に動いた」・状態のバッジは今のまま（守る）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { RunListView, RunRow } from '../domain/runList.ts';
import { parseCss } from '../test/cssBlocks.ts';
import { runningView, waitingView } from '../test/liveFixtures.ts';
import { listView, row, sampleRows } from '../test/runListFixtures.ts';
import { STALE_AFTER_SEC, staleRow } from '../test/staleFixtures.ts';
import { SHELL_STYLE, renderShell } from './shellHtml.ts';

const AFTER = STALE_AFTER_SEC;
const count = (text: string, re: RegExp): number => (text.match(re) ?? []).length;
const plain = (text: string): string => text.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
const squash = (text: string): string => text.replace(/\s+/g, '');
function between(text: string, from: string, to: string): string {
  const start = text.indexOf(from);
  assert.ok(start >= 0, `${from} がある`);
  const end = text.indexOf(to, start + from.length);
  return text.slice(start, end < 0 ? undefined : end);
}
/** 詳細の上の部分：パンくず・見出し・メタ・知らせ。詳細のタブの手前まで */
const detailTop = (out: string): string => between(out, 'class="crumbs"', 'data-detail-tab=');
const headOf = (out: string): string => between(out, 'class="head"', 'class="detail-meta"');
const metaOf = (out: string): string => /<div class="detail-meta">[\s\S]*?<\/div>/.exec(out)?.[0] ?? '';
/** 詳細の全体（左の一覧は含まない） */
const mainOf = (out: string): string => out.slice(out.indexOf('<main'));

/** 選んだ行（rows[0]）が動いている一覧 */
const listOf = (r: RunRow = staleRow(612)): RunListView => listView([r]);
const render = (view = runningView(83), list: RunListView = listOf(), after: number | null = AFTER): string => renderShell(view, list, after);

// ---- 入れ子の要素を取り出す・取り除く ----

interface Found {
  start: number;
  end: number;
  open: string;
  inner: string;
}
function findEl(text: string, tag: string, token: string, from = 0): Found | null {
  const open = new RegExp(`<${tag}\\b[^>]*class="[^"]*\\b${token}\\b[^"]*"[^>]*>`, 'g');
  open.lastIndex = from;
  const m = open.exec(text);
  if (m === null) return null;
  const innerStart = m.index + m[0].length;
  const re = new RegExp(`<${tag}\\b|</${tag}>`, 'g');
  re.lastIndex = innerStart;
  let depth = 1;
  for (let t = re.exec(text); t !== null; t = re.exec(text)) {
    depth += t[0].startsWith('</') ? -1 : 1;
    if (depth === 0) return { start: m.index, end: t.index + t[0].length, open: m[0], inner: text.slice(innerStart, t.index) };
  }
  return null;
}
function removeAll(text: string, tag: string, token: string): string {
  let out = text;
  for (let f = findEl(out, tag, token); f !== null; f = findEl(out, tag, token)) out = out.slice(0, f.start) + out.slice(f.end);
  return out;
}
/** バッジ・知らせ・印の属性を取り除く */
const stripMarks = (out: string): string =>
  removeAll(removeAll(out.replace(/ data-quiet="[^"]*"/g, '').replace(/ data-stale-after="[^"]*"/g, ''), 'div', 'stale-notice'), 'span', 'stale-badge');

// ---- AC-31：バッジと知らせ ----

test('D0021-AC-31: 選んだ行が動いていて quietSec があるとき、見出しに「⚠ 止まっているかも」のバッジ、メタの下に知らせ（role="status"）が出て、どちらも data-quiet・data-stale-after を持つ', () => {
  const out = render();
  const badge = findEl(out, 'span', 'stale-badge');
  assert.ok(badge, '止まっているかものバッジがある');
  assert.match(badge.open, /class="[^"]*\bbadge\b/, '.badge.stale-badge の形（CSS がそのクラスで隠す・見せる）');
  assert.match(badge.open, /\sdata-quiet="612"/);
  assert.match(badge.open, /\sdata-stale-after="600"/);
  assert.equal(plain(badge.inner), '⚠ 止まっているかも');
  const notice = findEl(out, 'div', 'stale-notice');
  assert.ok(notice, '知らせがある');
  assert.match(notice.open, /class="[^"]*\bnotice\b/, '.notice.stale-notice の形');
  assert.match(notice.open, /role="status"/);
  assert.match(notice.open, /\sdata-quiet="612"/);
  assert.match(notice.open, /\sdata-stale-after="600"/);
});

/** a のすぐあとに b が続く（間は空白だけ。間に別の要素を挟まない） */
const follows = (text: string, a: Found, b: Found): boolean => b.start >= a.end && text.slice(a.end, b.start).trim() === '';

test('D0021-AC-31: バッジは見出しの状態のバッジ（動いている）のすぐ隣（前でも後ろでもよい。間に別の要素を挟まない）、知らせはメタの下・タブの上に出る', () => {
  const out = render();
  const head = headOf(out);
  const state = findEl(head, 'span', 'is-running');
  const badge = findEl(head, 'span', 'stale-badge');
  assert.ok(state, '前提：状態のバッジ（is-running）がある');
  assert.ok(badge, '前提：見出しにバッジがある');
  assert.ok(out.includes('stale-notice'), '前提：知らせがある');
  assert.ok(follows(head, state, badge) || follows(head, badge, state), '状態のバッジのすぐ前か後ろにバッジがある');
  const meta = out.indexOf('class="detail-meta"');
  const notice = out.indexOf('stale-notice');
  assert.ok(meta >= 0 && notice > meta, 'メタの下');
  assert.ok(notice < out.indexOf('data-detail-tab='), 'タブの上');
});

test('D0021-AC-31: 状態のバッジの文字は「動いている」のまま（止まっているかもを足さない。守る）', () => {
  const state = findEl(headOf(render()), 'span', 'is-running');
  assert.ok(state, '状態のバッジ（is-running）がある');
  assert.equal(plain(state.inner), '動いている');
});

test('D0021-AC-31: HTML は最初は is-stale を持たない（付けるのはパネルのスクリプト。付くまで見えない）', () => {
  const out = render();
  assert.match(out, /stale-badge/, '前提：バッジがある');
  assert.doesNotMatch(out, /is-stale/);
});

// ラベルは「〜とき」に続けて読める言い方（動詞か形容で終える）にそろえる。
const NO_MARK: readonly (readonly [string, () => RunListView])[] = [
  ['確認待ちの行を選んでいる', () => listOf(staleRow(612, { state: 'waiting', waitingSec: 7 }))],
  ['待ち（idle）の行を選んでいる', () => listOf(staleRow(612, { state: 'idle' }))],
  ['終わった行を選んでいる', () => listOf(staleRow(612, { state: 'done', result: '合格' }))],
  ['前の実行の行を選んでいる', () => listOf(staleRow(612, { state: 'done', result: '合格', previous: true }))],
  ['quietSec が null の動いている行を選んでいる', () => listOf(staleRow(null))],
  ['quietSec の項目が無い動いている行を選んでいる', () => listOf(staleRow(undefined))],
  [
    '動いている行が一覧にあるが、終わった別の行を選んでいる',
    () => listView([staleRow(612, { key: 'here|a' }), row({ key: 'here|b', state: 'done', result: '合格' })], { selected: 'here|b' }),
  ],
  ['一覧が空である', () => listView([])],
];

for (const [label, list] of NO_MARK) {
  test(`D0021-AC-31: ${label}とき、詳細にバッジも知らせも data-quiet も出ない（対照：動いていて quietSec のある行には出る）`, () => {
    const contrast = render();
    assert.match(contrast, /stale-badge/, '対照：バッジが出る');
    assert.match(contrast, /stale-notice/, '対照：知らせが出る');
    assert.doesNotMatch(mainOf(render(runningView(83), list())), /data-quiet|data-stale-after|stale-badge|stale-notice/);
  });
}

test('D0021-AC-11: 目安が「印なし」（null・渡さない）のときは、選んだ行に quietSec があっても、バッジも知らせも出ない', () => {
  assert.match(render(), /stale-badge/, '対照：目安があれば出る');
  for (const out of [render(runningView(83), listOf(), null), renderShell(runningView(83), listOf())]) {
    assert.doesNotMatch(mainOf(out), /data-quiet|data-stale-after|stale-badge|stale-notice/);
  }
});

const flatRules = (css: string): { selector: string; body: string; media: string | null }[] =>
  parseCss(css)
    .filter((r) => !r.keyframes)
    .flatMap((r) => r.selector.split(',').map((sel) => ({ selector: sel.trim().replace(/\s+/g, ' '), body: r.body, media: r.media })));
const hasToken = (selector: string, token: string): boolean => new RegExp(`\\.${token}(?![\\w-])`).test(selector);
const lastCompound = (selector: string): string => selector.trim().split(/\s+/).pop() ?? '';
const decl = (body: string, prop: string): string | null => new RegExp(`(?<![-\\w])${prop}\\s*:\\s*([^;]+)`).exec(body)?.[1]?.trim() ?? null;
const classCount = (selector: string): number => (selector.match(/\.[\w-]+|\[[^\]]+\]|:[\w-]+/g) ?? []).length;

for (const [token, base] of [
  ['stale-badge', 'badge'],
  ['stale-notice', 'notice'],
] as const) {
  test(`D0021-AC-31: CSS：.${token} は is-stale が付くまで見えず（display: none）、付くと見える。基本の .${base} の display に勝つ`, () => {
    const rules = flatRules(SHELL_STYLE).filter((r) => r.media === null && hasToken(lastCompound(r.selector), token));
    const hide = rules.find((r) => !hasToken(r.selector, 'is-stale') && decl(r.body, 'display') === 'none');
    const show = rules.find((r) => hasToken(r.selector, 'is-stale') && ![null, 'none'].includes(decl(r.body, 'display')));
    assert.ok(hide, `.${token} は display: none の規則がある`);
    assert.ok(show, `.${token}.is-stale は見える規則がある`);
    const baseRule = flatRules(SHELL_STYLE).find((r) => r.media === null && r.selector === `.${base}` && decl(r.body, 'display') !== null);
    assert.ok(baseRule, `基本の .${base} の規則がある（今のまま）`);
    assert.ok(classCount(hide.selector) > classCount(baseRule.selector), `隠す規則が基本の .${base} に勝つ`);
    assert.ok(classCount(show.selector) > classCount(hide.selector), '見せる規則が隠す規則に勝つ');
  });
}

// ---- AC-32：知らせの文・メタ ----

test('D0021-AC-32: 知らせに、ログが更新されていない時間（data-elapsed）と「プロセスは調べていません」「長い段では、動いていてもログが更新されないことがあります」が読める', () => {
  const notice = findEl(render(), 'div', 'stale-notice');
  assert.ok(notice, '知らせがある');
  const text = squash(plain(notice.inner));
  assert.ok(text.includes(squash('この段のログが 10:12 更新されていません。')), plain(notice.inner));
  assert.ok(text.includes(squash('プロセスは調べていません。')), plain(notice.inner));
  assert.ok(text.includes(squash('長い段では、動いていてもログが更新されないことがあります。')), plain(notice.inner));
  assert.match(notice.inner, /<span class="elapsed" data-elapsed="612">10:12<\/span>/, '時間は data-elapsed（基準の秒）つきの要素');
});

test('D0021-AC-32: メタの「最後に動いた」（段が終わった時刻）は行の updatedText のまま。印を添えても替えず、印の言葉も入らない（守る）', () => {
  const r = staleRow(612, { updatedText: '10/17 09:41' });
  const meta = metaOf(render(runningView(83), listOf(r)));
  assert.match(plain(meta), /最後に動いた 10\/17 09:41/);
  assert.doesNotMatch(plain(meta), /更新なし|止まっている|10:12/);
  assert.equal(meta, metaOf(render(runningView(83), listOf(r), null)), '目安の有る無しでメタは同じ');
});

/** 要素と要素のあいだの空白は見ない（印を取り除いたあとに残る改行・空白の違いは、ほかの部分が変わったことにしない） */
const tight = (text: string): string => text.replace(/>\s+</g, '><');

test('D0021-AC-32: バッジと知らせと印の属性を取り除くと、詳細は印のない詳細と同じ（ほかの部分は変わらない。要素のあいだの空白は見ない）', () => {
  const marked = render();
  assert.match(marked, /stale-badge/, '前提：バッジがある');
  assert.match(marked, /stale-notice/, '前提：知らせがある');
  assert.equal(tight(mainOf(stripMarks(marked))), tight(mainOf(render(runningView(83), listOf(), null))));
});

// ---- AC-33：確認待ちの知らせは今のまま ----

const WAITING_LIST = (): RunListView => listView(sampleRows().map((r) => ({ ...r, quietSec: 612 }) as RunRow), { selected: 'here|' });

test('D0021-AC-33: 確認待ちの実行の黄の知らせと待ち時間のバッジは今のまま（行に quietSec が入っていても、印の知らせは出ない。対照：動いている実行の印の知らせは出る）', () => {
  assert.match(render(), /stale-notice/, '対照：動いている実行の印の知らせは出る');
  const out = render(waitingView(40), WAITING_LIST());
  const main = mainOf(out);
  assert.doesNotMatch(main, /data-quiet|stale-badge|stale-notice/);
  const notice = findEl(main, 'div', 'notice');
  assert.ok(notice, '黄の知らせがある');
  assert.match(notice.open, /role="status"/);
  assert.match(plain(notice.inner), /要件定義の確認を待っている：docs\/pipeline\/01_requirements\.md/);
  assert.match(plain(notice.inner), /読んで、承認か修正の依頼を返してください/);
  assert.match(headOf(out), /待ち <span class="elapsed" data-elapsed="42">0:42<\/span>/, '待ち時間のバッジ');
  assert.equal(main, mainOf(render(waitingView(40), listView(sampleRows(), { selected: 'here|' }))), 'quietSec の有る無しで詳細は同じ');
});

test('D0021-AC-33: 動いている実行に「の確認を待っている」の知らせは出ない（role="status" は印の知らせの 1 つだけ）', () => {
  const top = detailTop(render());
  assert.match(top, /stale-notice/, '前提：印の知らせがある');
  assert.doesNotMatch(top, /確認を待っている|承認か修正の依頼/);
  assert.equal(count(top, /role="status"/g), 1);
});
