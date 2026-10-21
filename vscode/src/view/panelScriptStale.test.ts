// 止まっているかもしれない実行の印（D0021）のうち、パネルのスクリプトの分：目安に届いた印の要素への is-stale の付与。
// panelScript.ts の PANEL_SCRIPT を node:vm で、手で書いた偽の DOM と偽の時計（src/test/fakeDom.ts）の上で動かす。本物の時間は使わない。
// スクリプトは「記録の時刻と今の時刻」を比べず、描き直しを受けた時刻（パネルの時計）からの差 dt だけを data-quiet（基準の秒）に足し、
// 基準 + dt ≥ data-stale-after（目安の秒）の要素に is-stale を付ける。付けるだけで、外すのは描き直し（DOM ごとの入れ替え）だけ。
// HTML は主に手で書く（data-quiet・data-stale-after・data-elapsed を持つ要素）。目安つきの renderPanelHtml から作るのは AC-22 ②③ の 2 つだけ
// （まだ無い引数は、余分な引数を受ける型で呼ぶ。今は無視されるので、目安なしと同じ HTML になり、今のままで通る）。
// 全ログの最新で決まる基準が起動直後の is-stale に出ること（AC-44・45）は、設計の対応表どおり panelHtmlStale.test.ts が確かめる（ここには置かない）。
// 「付かない側」の確かめには、同じ HTML に「付く対照」（基準 700・目安 600 など）を入れる（空振りを防ぐ）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';
import { PANEL_SCRIPT } from './panelScript.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import type { RunListView } from '../domain/runList.ts';
import { extractCss, parseCss } from '../test/cssBlocks.ts';
import { bootPanel, extractScript } from '../test/fakeDom.ts';
import type { BootOptions, FakeNode, PanelHarness } from '../test/fakeDom.ts';
import { finishedView, loopSnapshot, sendBackView, viewAt } from '../test/liveFixtures.ts';
import { listView, sampleRows } from '../test/runListFixtures.ts';
import { STALE_AFTER_SEC, abandonedSnapshot, staleParts } from '../test/staleFixtures.ts';

const NONCE = 'TESTNONCE';

// 目安（staleAfterSec）を受ける renderPanelHtml。実装の段で型に入るまでは、余分な引数を受ける型で呼ぶ。
const panelWith = renderPanelHtml as (view: PipelineView, nonce: string, list?: RunListView | null, staleAfterSec?: number | null) => string;

// ---- 手で書く HTML ----

/** 印の元の属性。null の項目は属性ごと付けない（属性なしの確かめ）。 */
function stale(quiet: string | null, after: string | null): string {
  return `${quiet === null ? '' : ` data-quiet="${quiet}"`}${after === null ? '' : ` data-stale-after="${after}"`}`;
}
/** 印の要素 1 つ。本物の HTML と同じく、中に data-elapsed の時間（基準の秒）を持つ。 */
const mark = (id: string, quiet: string | null, after: string | null, elapsed = quiet ?? '0'): string =>
  `<div id="${id}" class="mark"${stale(quiet, after)}>⚠ 更新なし <span class="elapsed" data-elapsed="${elapsed}">?</span></div>`;
/** data-elapsed を持たない印の要素（詳細のバッジのように、時間を持たない面）。 */
const bareMark = (id: string, quiet: string | null, after: string | null): string => `<div id="${id}" class="mark"${stale(quiet, after)}>⚠ 止まっているかも</div>`;
const PLAIN = '<p>印の無い本体</p>';

/** 手で書いた本体だけを .root に入れた、パネルの HTML 全体。スクリプトは本物の PANEL_SCRIPT。 */
const pageOf = (body: string): string =>
  `<!DOCTYPE html>\n<html lang="ja"><head><meta charset="UTF-8"></head><body>\n<div class="root">${body}</div>\n<script nonce="${NONCE}">${PANEL_SCRIPT}</script>\n</body></html>`;
const boot = (body: string, opts?: BootOptions): PanelHarness => bootPanel(pageOf(body), opts);
const render = (h: PanelHarness, body: string): void => h.send({ type: 'render', html: body });

const byId = (h: PanelHarness, id: string): FakeNode => {
  const el = h.doc.querySelector(`[id="${id}"]`);
  assert.ok(el !== null, `#${id} がある`);
  return el;
};
const isStale = (h: PanelHarness, id: string): boolean => byId(h, id).classList.contains('is-stale');
/** 印の中の data-elapsed の今の文字。 */
const timeOf = (h: PanelHarness, id: string): string => h.text(byId(h, id).querySelector('[data-elapsed]')!);

// ---- AC-13：描き直しの直後・起動直後に判定する（基準 ≥ 目安） ----

const BOUNDARY: readonly (readonly [number, boolean])[] = [
  [599, false],
  [600, true],
  [601, true],
];
for (const [quiet, want] of BOUNDARY) {
  const word = want ? '付く' : '付かない';
  test(`D0021-AC-13: 描き直しを受けた直後、基準 ${quiet}・目安 600 の要素は is-stale が${word}（対照：基準 700 は付く）`, () => {
    const h = boot(PLAIN);
    render(h, mark('m', String(quiet), '600') + mark('ctl', '700', '600'));
    assert.equal(isStale(h, 'm'), want);
    assert.equal(isStale(h, 'ctl'), true, '対照：基準 700・目安 600 は付く');
  });
  test(`D0021-AC-13: 起動した直後、基準 ${quiet}・目安 600 の要素は is-stale が${word}（対照：基準 700 は付く）`, () => {
    const h = boot(mark('m', String(quiet), '600') + mark('ctl', '700', '600'));
    assert.equal(isStale(h, 'm'), want);
    assert.equal(isStale(h, 'ctl'), true, '対照：基準 700・目安 600 は付く');
  });
}

// ---- AC-14：時間は描き直しを受けた時刻からの差だけ。記録の時刻・ファイルは読まない ----

test('D0021-AC-14: 基準 595・目安 600 の要素は、4 秒後はまだ付かず（基準 596 の対照は付く）、5 秒後に付く', () => {
  const h = boot(mark('m', '595', '600') + mark('ctl', '596', '600'));
  assert.equal(isStale(h, 'm'), false, '起動直後');
  h.advance(4000);
  assert.equal(isStale(h, 'm'), false, '4 秒後は 599');
  assert.equal(isStale(h, 'ctl'), true, '対照：4 秒後に 596 + 4 = 600 で付く');
  h.advance(1000);
  assert.equal(isStale(h, 'm'), true, '5 秒後は 600');
});

const FORBIDDEN_WORDS = ['Date.parse', 'mtime', 'readFile'] as const;
/** スクリプトの文字にある、記録の時刻・ファイルを読む言葉。 */
const forbiddenIn = (script: string): string[] => FORBIDDEN_WORDS.filter((w) => script.includes(w));

test('D0021-AC-14: パネルのスクリプトの文字に Date.parse・mtime・readFile が無い（記録の時刻・ファイルを読まない。守り続ける検査）', () => {
  assert.deepEqual(forbiddenIn(extractScript(renderPanelHtml(finishedView(), NONCE))), []);
  assert.deepEqual(forbiddenIn(PANEL_SCRIPT), []);
});

test('D0021-AC-14: 検査そのもの：Date.parse(x) などを足したスクリプトの文字は見つけ、きれいな文字は見逃す', () => {
  assert.deepEqual(forbiddenIn(`${PANEL_SCRIPT}\nconst t = Date.parse(x);`), ['Date.parse']);
  assert.deepEqual(forbiddenIn(`${PANEL_SCRIPT}\nconst m = file.mtimeMs;`), ['mtime']);
  assert.deepEqual(forbiddenIn(`${PANEL_SCRIPT}\nreadFile(path);`), ['readFile']);
  assert.deepEqual(forbiddenIn(`${PANEL_SCRIPT}\nDate.parse(a); readFile(b); mtime;`), ['Date.parse', 'mtime', 'readFile']);
  assert.deepEqual(forbiddenIn(PANEL_SCRIPT), []);
});

// ---- AC-15：印の中の時間は、印が付く前も後も数え上げが続く ----

test('D0021-AC-15: 印の中の data-elapsed は、is-stale が付く前も後も 1 秒ごとに 1 秒ずつ増える（9:58 → 9:59 → 10:00 → 10:01 → 10:02）', () => {
  const h = boot(mark('m', '598', '600'));
  const times = ['9:58', '9:59', '10:00', '10:01', '10:02'];
  const stalled = [false, false, true, true, true];
  for (let i = 0; i < times.length; i++) {
    assert.equal(isStale(h, 'm'), stalled[i], `${i} 秒後に目安を越えたかどうか（前提）`);
    assert.equal(timeOf(h, 'm'), times[i], `${i} 秒後の時間`);
    h.advance(1000);
  }
});

// ---- AC-16：外すのは描き直しだけ（描き直しで DOM ごと入れ替わる） ----

test('D0021-AC-16: 新しい描き直しで基準が目安より小さくなる（612 → 3）と、is-stale が外れる', () => {
  const h = boot(mark('m', '612', '600'));
  assert.equal(isStale(h, 'm'), true, '前提：612 では付いている');
  render(h, mark('m', '3', '600'));
  assert.equal(isStale(h, 'm'), false);
});

test('D0021-AC-16: 基準が目安以上のまま（612 → 700）の描き直しなら、is-stale が付いている', () => {
  const h = boot(mark('m', '612', '600'));
  render(h, mark('m', '700', '600'));
  assert.equal(isStale(h, 'm'), true);
});

test('D0021-AC-16: 基準が小さくなった描き直しのあとは、新しい基準から数え直し、目安に届くとまた付く（3 → 596 秒後は付かず 597 秒後に付く）', () => {
  const h = boot(mark('m', '612', '600'));
  render(h, mark('m', '3', '600'));
  h.advance(596_000);
  assert.equal(isStale(h, 'm'), false, '3 + 596 = 599');
  h.advance(1000);
  assert.equal(isStale(h, 'm'), true, '3 + 597 = 600');
});

// ---- AC-17：data-quiet だけの HTML でもタイマーを回す・止める ----

const QUIET_ONLY = bareMark('q', '10', '600');

test('D0021-AC-17: data-quiet だけの HTML（data-elapsed は無い）の描き直しを受けると、タイマーが 1 つ回る（対照：受ける前は 0）', () => {
  const h = boot(PLAIN);
  assert.equal(h.activeIntervals(), 0, '対照：数える要素が無いあいだは回さない');
  render(h, QUIET_ONLY);
  assert.equal(h.activeIntervals(), 1);
});

test('D0021-AC-17: そのあと data-elapsed も data-quiet も無い描き直しを受けると、タイマーが止まる（1 → 0）', () => {
  const h = boot(PLAIN);
  render(h, QUIET_ONLY);
  assert.equal(h.activeIntervals(), 1, '前提：data-quiet だけで回っている');
  render(h, PLAIN);
  assert.equal(h.activeIntervals(), 0);
});

test('D0021-AC-17: data-quiet だけの描き直しを何度受けても、動いているタイマーは 1 つのまま', () => {
  const h = boot(PLAIN);
  for (let i = 0; i < 5; i++) {
    h.advance(1500);
    render(h, bareMark('q', String(i), '600'));
    assert.equal(h.activeIntervals(), 1, `${i + 1} 回目の描き直しのあと`);
  }
});

// ---- AC-18：隠れているあいだは止め、戻ったら隠れていた時間を足す ----

test('D0021-AC-18: data-quiet だけの HTML でタイマーが 1 つ回っていて、隠れると 0 になる', () => {
  const h = boot(QUIET_ONLY);
  assert.equal(h.activeIntervals(), 1);
  h.setVisibility('hidden');
  assert.equal(h.activeIntervals(), 0);
});

test('D0021-AC-18: 隠れているあいだに目安を越えたら、戻った時点で is-stale が付く（隠れているあいだは付けない）', () => {
  const h = boot(mark('m', '590', '600'));
  h.setVisibility('hidden');
  h.advance(10_000);
  assert.equal(isStale(h, 'm'), false, '隠れているあいだは数え上げも止まっている');
  h.setVisibility('visible');
  assert.equal(isStale(h, 'm'), true, '590 + 隠れていた 10 秒 = 600');
});

test('D0021-AC-18: 隠れる前に付いていれば、隠れても戻っても付いたまま', () => {
  const h = boot(mark('m', '599', '600'));
  h.advance(1000);
  assert.equal(isStale(h, 'm'), true, '前提：1 秒後に付いている');
  h.setVisibility('hidden');
  assert.equal(isStale(h, 'm'), true);
  h.setVisibility('visible');
  assert.equal(isStale(h, 'm'), true);
});

// ---- AC-19：時計が戻っても小さくならず、付いたものは外れない ----

test('D0021-AC-19: パネルの時計が過去へ戻っても、数え上げは基準より小さくならず、付いた is-stale は外れない', () => {
  const h = boot(mark('m', '595', '600'));
  h.advance(5000);
  assert.equal(isStale(h, 'm'), true, '前提：5 秒後に付いている');
  assert.equal(timeOf(h, 'm'), '10:00');
  h.setNow(h.now() - 60_000); // スリープ明けや時計の補正で戻った
  h.tick();
  assert.equal(timeOf(h, 'm'), '9:55', '基準（595 秒）より小さくならない');
  assert.equal(isStale(h, 'm'), true);
});

// ---- AC-20：属性の値が合わないときは付けない ----

// [ラベル, data-quiet, data-stale-after]。null は属性なし。基準が合わない行は目安 600、目安が合わない行は基準 700 の組み合わせ。
const BAD_AFTER: readonly (readonly [string, string | null, string | null])[] = [
  ['目安が空', '700', ''],
  ['目安が空白', '700', ' '],
  ['目安が 0', '700', '0'],
  ['目安が -5', '700', '-5'],
  ['目安が abc', '700', 'abc'],
  ['目安が NaN', '700', 'NaN'],
  ['目安が Infinity', '700', 'Infinity'],
  ['目安が 1e3', '700', '1e3'],
  ['目安が +5', '700', '+5'],
  ['目安が 1.5', '700', '1.5'],
  ['目安の属性なし', '700', null],
  ['目安 0 で基準も 0（最初から印にならない）', '0', '0'],
];
const BAD_QUIET: readonly (readonly [string, string | null, string | null])[] = [
  ['基準が空', '', '600'],
  ['基準が空白', ' ', '600'],
  ['基準が -5', '-5', '600'],
  ['基準が abc', 'abc', '600'],
  ['基準が NaN', 'NaN', '600'],
  ['基準が Infinity', 'Infinity', '600'],
  ['基準が 1e3', '1e3', '600'],
  ['基準が +5', '+5', '600'],
  ['基準が 1.5', '1.5', '600'],
  ['基準の属性なし', null, '600'],
];
for (const [label, quiet, after] of [...BAD_AFTER, ...BAD_QUIET]) {
  test(`D0021-AC-20: ${label}の要素は、時間がたっても is-stale を付けない（対照：基準 700・目安 600 は付く。同じ id の要素も、正しい値で描き直すと付く）`, () => {
    const h = boot(mark('bad', quiet, after, '0') + mark('ctl', '700', '600'));
    assert.equal(isStale(h, 'ctl'), true, '対照：基準 700・目安 600 は起動直後に付く');
    assert.equal(isStale(h, 'bad'), false, '起動直後');
    h.advance(700_000); // 700 秒たっても、数字だけの文字でない値は読み取らない
    assert.equal(isStale(h, 'bad'), false, '700 秒後');
    render(h, mark('bad', '700', '600'));
    assert.equal(isStale(h, 'bad'), true, '対照：同じ id の要素を正しい値（基準 700・目安 600）で描き直すと、起動直後に付く');
  });
}

// ---- AC-21：動きを減らす設定でも付く ----

const REDUCED: readonly (readonly [string, BootOptions])[] = [
  ['prefers-reduced-motion: reduce', { reducedMotion: true }],
  ['matchMedia を持たない環境（安全側で動きを減らす扱い）', { noMatchMedia: true }],
];
for (const [label, opts] of REDUCED) {
  test(`D0021-AC-21: ${label}でも is-stale が付く（起動直後と、時間がたってから）`, () => {
    const h = boot(mark('now', '700', '600') + mark('later', '595', '600'), opts);
    assert.equal(isStale(h, 'now'), true, '起動直後');
    assert.equal(isStale(h, 'later'), false);
    h.advance(5000);
    assert.equal(isStale(h, 'later'), true, '5 秒後');
  });
}

// ---- AC-22：拡張へ送るメッセージ・CSP・禁止の書き方は増えない ----

test('D0021-AC-22: is-stale の付け外し（付く・描き直しで外れる・また付く）のあとも、拡張へ送るメッセージの種類は ready・openArtifact・selectRun だけ', () => {
  const body = (quiet: string): string =>
    mark('m', quiet, '600') + '<button data-artifact="01_requirements.md">成果物</button><button data-run="here|a" aria-pressed="false">行</button>';
  const h = boot(body('595'));
  h.advance(5000);
  assert.equal(isStale(h, 'm'), true, '対照：is-stale が付いている');
  h.doc.querySelector('button[data-artifact]')!.dispatch('click');
  render(h, body('3'));
  assert.equal(isStale(h, 'm'), false, '描き直しで外れた');
  h.advance(1000);
  render(h, body('612'));
  assert.equal(isStale(h, 'm'), true, 'また付いた');
  h.doc.querySelector('button[data-run]')!.dispatch('click');
  assert.deepEqual(h.posted, [{ type: 'ready' }, { type: 'openArtifact', name: '01_requirements.md' }, { type: 'selectRun', id: 'here|a' }]);
  for (const m of h.posted) assert.ok(['ready', 'openArtifact', 'selectRun'].includes((m as { type: string }).type));
});

const CSP_META = /<meta http-equiv="Content-Security-Policy"[^>]*>/g;
const FORBIDDEN_PARTS: readonly (readonly [string, RegExp])[] = [
  ['style=', /\sstyle\s*=/gi],
  ['on…=', /\son[a-z]+\s*=/gi],
  ['src=', /\ssrc\s*=/gi],
  ['href=', /\shref\s*=/gi],
  ['@import', /@import/gi],
  ['url(http', /url\(\s*["']?https?:/gi],
];
/** CSP が禁じる書き方（インラインの style・イベントの属性・外部の読み込み）の数。 */
const countForbidden = (html: string): Record<string, number> => Object.fromEntries(FORBIDDEN_PARTS.map(([name, re]) => [name, (html.match(re) ?? []).length]));

// ②③は設計どおり「守る」検査（今のままで通る）。目安つきの renderPanelHtml に印の属性が出ていること（空振りでないこと）は、
// panelHtmlStale.test.ts の AC-44・45（完成した HTML を bootPanel して data-quiet を持つ要素を数える）と AC-11（本体の HTML）が見る。

test('D0021-AC-22: 目安を渡した renderPanelHtml の CSP の <meta> は、目安なしと同じ文字（守り続ける検査）', () => {
  const { view, list } = staleParts(abandonedSnapshot(), 0);
  const without = renderPanelHtml(view, NONCE, list);
  const withStale = panelWith(view, NONCE, list, STALE_AFTER_SEC);
  assert.equal(without.match(CSP_META)?.length, 1);
  assert.deepEqual(withStale.match(CSP_META), without.match(CSP_META));
});

test('D0021-AC-22: 目安を渡した HTML に、style=・on…=・src=・href=・@import・url(http が、目安なしより増えない（守り続ける検査）', () => {
  const { view, list } = staleParts(abandonedSnapshot(), 0);
  const before = countForbidden(renderPanelHtml(view, NONCE, list));
  const after = countForbidden(panelWith(view, NONCE, list, STALE_AFTER_SEC));
  for (const [name] of FORBIDDEN_PARTS) assert.ok(after[name]! <= before[name]!, `${name}：目安なし ${before[name]} → 目安あり ${after[name]}`);
});

const FORBIDDEN_SAMPLES: readonly (readonly [string, string])[] = [
  ['style=', '<p style="color:red">x</p>'],
  ['on…=', '<button onclick="run()">x</button>'],
  ['src=', '<img src="a.png">'],
  ['href=', '<a href="https://example.com/">x</a>'],
  ['@import', '<style>@import "a.css";</style>'],
  ['url(http', '<style>.a { background: url(http://example.com/a.png); }</style>'],
];
for (const [name, html] of FORBIDDEN_SAMPLES) {
  test(`D0021-AC-22: 検査そのもの：${name} を足した HTML は見つける`, () => {
    assert.ok(countForbidden(html)[name]! >= 1);
  });
}
test('D0021-AC-22: 検査そのもの：禁止の書き方の無い HTML（印の要素を含む）は見逃す（どれも 0）', () => {
  assert.deepEqual(Object.values(countForbidden(mark('m', '612', '600') + '<p class="a">安全</p>')), [0, 0, 0, 0, 0, 0]);
});

// ---- AC-23：理由の欄の選び・絞り込み・タブ・スクロール・焦点・戻る矢印の光りは、is-stale と両立する ----

const clickNode = (h: PanelHarness, id: string): void => {
  const g = h.node(id);
  (g.children.find((c): c is FakeNode => 'tagName' in c && c.tagName === 'text') ?? g).dispatch('click');
};
const openIds = (h: PanelHarness): string[] =>
  h.doc
    .querySelectorAll('[data-reasons-for]')
    .filter((s) => !s.hidden)
    .map((s) => s.getAttribute('data-reasons-for')!);

// 付け外しの確かめ方：is-stale が付く描き直し（基準 612）→ 続く描き直し（612 のまま）→ 外れる描き直し（基準 3 < 目安 600）の 3 回のあとで、中の状態が残る。
test('D0021-AC-23: 理由の欄の選びと開閉（D0016）は、is-stale が付いたあと・続く描き直しのあと・is-stale が外れる描き直しのあとも残る', () => {
  const view = viewAt(loopSnapshot({ sendBack: 1, running: true }), 83);
  const h = bootPanel(renderPanelHtml(view, NONCE));
  clickNode(h, 'implement');
  const draw = (quiet: string): void => render(h, renderViewBody(view) + mark('m', quiet, '600'));
  const keptPick = (): void => {
    assert.deepEqual(openIds(h), ['implement']);
    assert.equal(h.node('implement').classList.contains('is-picked'), true);
    assert.equal(h.node('implement').getAttribute('aria-pressed'), 'true');
  };
  draw('612');
  assert.equal(isStale(h, 'm'), true, '対照：is-stale が付いている');
  keptPick();
  draw('612');
  assert.equal(isStale(h, 'm'), true, '続く描き直し');
  keptPick();
  draw('3');
  assert.equal(isStale(h, 'm'), false, '基準が目安より小さい描き直しで外れた');
  keptPick();
});

const LIST = listView(sampleRows(), { selected: 'here|survey' });
const listBody = (quiet: string): string => renderViewBody(finishedView(), LIST) + mark('m', quiet, '600');
const bootList = (opts?: BootOptions): PanelHarness => bootPanel(renderPanelHtml(finishedView(), NONCE, LIST), opts);
const filterInput = (h: PanelHarness): FakeNode => {
  const el = h.doc.querySelector('input[data-keep="filter"]');
  assert.ok(el !== null, '絞り込みの入力がある');
  return el;
};
const visibleKeys = (h: PanelHarness): string[] =>
  h.doc
    .querySelectorAll('li[data-group]')
    .filter((li) => li.closest('[hidden]') === null)
    .map((li) => li.querySelector('button[data-run]')!.getAttribute('data-run')!);
const selectedOf = (h: PanelHarness, attr: string): string[] =>
  h.doc
    .querySelectorAll(`button[${attr}]`)
    .filter((b) => b.getAttribute('aria-selected') === 'true')
    .map((b) => b.getAttribute(attr)!);

test('D0021-AC-23: 絞り込みの文字と、状態のタブ・詳細のタブの選びは、is-stale が付いたあと・続く描き直しのあと・is-stale が外れる描き直しのあとも残る', () => {
  const h = bootList();
  render(h, listBody('612'));
  assert.equal(isStale(h, 'm'), true, '対照：is-stale が付いている');
  h.typeText(filterInput(h), 'main');
  h.doc.querySelector('button[data-list-tab="done"]')!.dispatch('click');
  h.doc.querySelector('button[data-detail-tab="usage"]')!.dispatch('click');
  const keys = ['here|survey', 'here|review', 'here|archive/20261016-090000'];
  const kept = (): void => {
    assert.equal(filterInput(h).value, 'main');
    assert.deepEqual(selectedOf(h, 'data-list-tab'), ['done']);
    assert.deepEqual(selectedOf(h, 'data-detail-tab'), ['usage']);
    assert.deepEqual(visibleKeys(h), keys);
  };
  assert.deepEqual(visibleKeys(h), keys);
  assert.equal(isStale(h, 'm'), true);
  render(h, listBody('612'));
  assert.equal(isStale(h, 'm'), true, '続く描き直し');
  kept();
  render(h, listBody('3'));
  assert.equal(isStale(h, 'm'), false, '基準が目安より小さい描き直しで外れた');
  kept();
});

const LAYOUT: BootOptions['layout'] = (n) => {
  switch (n.getAttribute('data-scroll')) {
    case 'list':
      return { scrollHeight: 1000, clientHeight: 200 };
    case 'diagram':
      return { scrollHeight: 800, clientHeight: 300 };
    case 'output':
      return { scrollHeight: 600, clientHeight: 100 };
    case 'gantt':
      return { scrollHeight: 500, clientHeight: 100 };
    default:
      return null;
  }
};
const scroller = (h: PanelHarness, name: string): FakeNode => {
  const el = h.doc.querySelector(`[data-scroll="${name}"]`);
  assert.ok(el !== null, `[data-scroll="${name}"] がある`);
  return el;
};

test('D0021-AC-23: 一覧・図の枠・出力・時系列のスクロール位置は、is-stale が付いたあと・続く描き直しのあと・is-stale が外れる描き直しのあとも残る', () => {
  const h = bootList({ layout: LAYOUT });
  render(h, listBody('612'));
  assert.equal(isStale(h, 'm'), true, '対照：is-stale が付いている');
  scroller(h, 'list').scrollTop = 150;
  scroller(h, 'diagram').scrollTop = 200;
  scroller(h, 'output').scrollTop = 100;
  scroller(h, 'gantt').scrollTop = 50;
  const positions = (): number[] => ['list', 'diagram', 'output', 'gantt'].map((n) => scroller(h, n).scrollTop);
  render(h, listBody('612'));
  assert.equal(isStale(h, 'm'), true, '続く描き直し');
  assert.deepEqual(positions(), [150, 200, 100, 50]);
  render(h, listBody('3'));
  assert.equal(isStale(h, 'm'), false, '基準が目安より小さい描き直しで外れた');
  assert.deepEqual(positions(), [150, 200, 100, 50]);
});

test('D0021-AC-23: 絞り込みの入力の焦点と選択範囲は、is-stale が付いたあと・続く描き直しのあと・is-stale が外れる描き直しのあとも戻る', () => {
  const h = bootList();
  render(h, listBody('612'));
  assert.equal(isStale(h, 'm'), true, '対照：is-stale が付いている');
  h.typeText(filterInput(h), 'main');
  const before = filterInput(h);
  before.focus();
  before.setSelectionRange(1, 3);
  render(h, listBody('612'));
  const after = filterInput(h);
  assert.notEqual(after, before, '入力は作り直されている');
  assert.ok(h.doc.activeElement === after, '焦点が新しい入力に戻っていない');
  assert.deepEqual([after.selectionStart, after.selectionEnd], [1, 3]);
  assert.equal(isStale(h, 'm'), true, '続く描き直し');
  render(h, listBody('3'));
  const last = filterInput(h);
  assert.notEqual(last, after, '入力はまた作り直されている');
  assert.ok(h.doc.activeElement === last, 'is-stale が外れる描き直しでも、焦点が新しい入力に戻る');
  assert.deepEqual([last.selectionStart, last.selectionEnd], [1, 3]);
  assert.equal(isStale(h, 'm'), false, '基準が目安より小さい描き直しで外れた');
});

test('D0021-AC-23: 戻る矢印の光り（D0017）は、is-stale が付いた描き直しでも付き、is-stale が付いても・外れる描き直しでも消えない', () => {
  const h = bootPanel(renderPanelHtml(sendBackView(1), NONCE));
  render(h, renderViewBody(sendBackView(2)) + mark('m', '612', '600'));
  assert.equal(isStale(h, 'm'), true, '対照：is-stale が付いている');
  const flashing = (): string[] =>
    h.doc
      .querySelectorAll('[data-loop]')
      .filter((l) => l.classList.contains('is-new'))
      .map((l) => l.getAttribute('data-loop')!);
  assert.deepEqual(flashing(), ['send-back']);
  h.advance(300);
  render(h, renderViewBody(sendBackView(2)) + mark('m', '612', '600'));
  assert.equal(isStale(h, 'm'), true, '続く描き直し');
  assert.deepEqual(flashing(), ['send-back'], '光りの途中の描き直しでも、付け直されて続く');
  render(h, renderViewBody(sendBackView(2)) + mark('m', '3', '600'));
  assert.equal(isStale(h, 'm'), false, '基準が目安より小さい描き直しで外れた');
  assert.deepEqual(flashing(), ['send-back'], 'is-stale が外れる描き直しでも、光りは続く');
});

test('D0021-AC-23: 差し戻しのある実装の節を選んだまま is-stale が付いても、is-picked と aria-pressed が残る', () => {
  const view = viewAt(loopSnapshot({ sendBack: 1, running: true }), 83);
  // 実装の節（g.node）そのものに、印の元の属性を付ける（実物では、動いている最中の実装の節が選べて、印が付く）
  const withNodeStale = (): string =>
    renderViewBody(view).replace(/(<g class="node [^"]*" data-node="implement")/, `$1${stale('595', '600')}`);
  assert.match(withNodeStale(), /data-node="implement" data-quiet="595" data-stale-after="600"/, '前提：実装の節に属性を付けた');
  const h = bootPanel(renderPanelHtml(view, NONCE));
  render(h, withNodeStale());
  clickNode(h, 'implement');
  assert.equal(h.node('implement').classList.contains('is-picked'), true, '前提：選んでいる');
  h.advance(5000);
  const g = h.node('implement');
  assert.equal(g.classList.contains('is-stale'), true, '対照：同じ節に is-stale が付いている');
  assert.equal(g.classList.contains('is-picked'), true);
  assert.equal(g.getAttribute('aria-pressed'), 'true');
});

test('D0021-AC-23: STYLE に .node.is-stale.is-picked .shape の規則があり、選びの色と点線の形を決める（media の外）', () => {
  const rules = parseCss(extractCss(renderPanelHtml(finishedView(), NONCE)));
  const classesOf = (selector: string): Set<string> => new Set([...selector.matchAll(/\.([\w-]+)/g)].map((m) => m[1]!));
  const rule = rules.find((r) => {
    const parts = classesOf(r.selector);
    return r.media === null && !r.keyframes && parts.has('node') && parts.has('is-stale') && parts.has('is-picked') && /\.shape\s*$/.test(r.selector.trim());
  });
  assert.ok(rule !== undefined, '.node.is-stale.is-picked .shape の規則がある');
  assert.match(rule.body, /stroke\s*:\s*var\(--vscode-focusBorder/, '選びの色（focusBorder）');
  assert.match(rule.body, /stroke-dasharray\s*:\s*4 3/, '点線の形は残す');
});
