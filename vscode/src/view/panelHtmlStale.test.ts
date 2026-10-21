// パネル全体の HTML の「⚠ 更新なし」の印（D0021・AC-11・12・44〜50 の HTML の分・52）。CSP・禁止の文字（AC-22）は panelScriptStale.test.ts が確かめる。
// 記録の写し（test/staleFixtures.ts）から、同じ「今」で図の状態と一覧の行を作り（staleParts）、renderPanelHtml・renderViewBody に目安の秒を渡す。
// 6 つの面（節・入る矢印・一覧の行・詳細のバッジ・知らせ・時系列の行）の印を、本体の HTML の文字で確かめる。is-stale が付くかは bootPanel でパネルのスクリプトを動かして見る。
// 「出ない側」の確かめには、同じ写しに出る条件だけを足した対照を付ける（空振りを防ぐ）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { WorkDirSnapshot } from '../domain/pipelineView.ts';
import { bootPanel } from '../test/fakeDom.ts';
import { snapshot } from '../test/fixtures.ts';
import { waitingSnapshot } from '../test/liveFixtures.ts';
import {
  BROKEN_STATE_KINDS,
  FINAL_VALUES,
  NO_MTIME_KINDS,
  STALE_AFTER_SEC,
  abandonedSnapshot,
  ancientSnapshot,
  brokenStateSnapshot,
  hostileSnapshot,
  mtimeAgo,
  noMtimeOnRunningSnapshot,
  resumedSnapshot,
  staleParts,
  staleSnapshot,
  withAllMtimes,
  withPrevious,
} from '../test/staleFixtures.ts';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';

const NONCE = 'TESTNONCE';
const AFTER = STALE_AFTER_SEC;
type Parts = ReturnType<typeof staleParts>;

/** 本体の HTML（一覧・詳細）。style・script を含まない */
const bodyOf = (p: Parts, after: number | null = AFTER): string => renderViewBody(p.view, p.list, after);
/** 完成した HTML 全体（bootPanel に渡す） */
const pageOf = (p: Parts, after: number | null = AFTER): string => renderPanelHtml(p.view, NONCE, p.list, after);
/** 完成した HTML の本体の部分（style・script を除く） */
const rootOf = (page: string): string => page.slice(page.indexOf('<div class="root">'), page.indexOf('<script nonce='));

const count = (text: string, re: RegExp): number => (text.match(re) ?? []).length;
const plain = (text: string): string => text.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
const squash = (text: string): string => text.replace(/\s+/g, '');
const attrOf = (tag: string, name: string): string | undefined => new RegExp(`(?:^|\\s)${name}="([^"]*)"`).exec(tag)?.[1];

/** 印の属性・印の要素のどれか（本体の HTML にだけ使う。CSS の文字は含まない） */
const MARK_RE = /data-quiet|data-stale-after|node-stale|run-stale|stale-badge|stale-notice|g-stalled|g-calm|run-foot/;

// ---- 入れ子の要素を取り出す ----

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
function allEl(text: string, tag: string, token: string): Found[] {
  const found: Found[] = [];
  for (let f = findEl(text, tag, token); f !== null; f = findEl(text, tag, token, f.end)) found.push(f);
  return found;
}

// ---- data-quiet を持つ要素 ----

/** data-quiet を持つ開きタグ */
const quietTags = (out: string): string[] => [...out.matchAll(/<[a-z]+\b[^>]*\sdata-quiet="[^"]*"[^>]*>/g)].map((m) => m[0]);
const quietValues = (out: string): string[] => quietTags(out).map((tag) => attrOf(tag, 'data-quiet') ?? '');

/** 印を持つ要素の種類（節・入る矢印・一覧の行・バッジ・知らせ・時系列の行） */
function kindOf(tag: string): string {
  const name = /^<([a-z]+)/.exec(tag)?.[1] ?? '';
  const cls = (attrOf(tag, 'class') ?? '').split(/\s+/);
  if (name === 'g' && cls.includes('node')) return 'node';
  if (name === 'line' && cls.includes('edge')) return 'edge';
  if (name === 'button' && cls.includes('run-row')) return 'row';
  if (name === 'span' && cls.includes('stale-badge')) return 'badge';
  if (name === 'div' && cls.includes('stale-notice')) return 'notice';
  if (name === 'div' && cls.includes('g-row')) return 'gantt';
  return `?${name}.${cls.join('.')}`;
}
const quietKinds = (out: string): string[] => quietTags(out).map(kindOf).sort();
const SIX = ['badge', 'edge', 'gantt', 'node', 'notice', 'row'];

// ---- AC-11：6 つの面に印の属性が出る ----

test('D0021-AC-11: 印の対象の動いている実行の HTML に、節・入る矢印・一覧の行・バッジ・知らせ・時系列の行の 6 か所へ data-quiet・data-stale-after が出る', () => {
  const out = bodyOf(staleParts(staleSnapshot()));
  assert.deepEqual(quietKinds(out), SIX);
  for (const tag of quietTags(out)) {
    assert.equal(attrOf(tag, 'data-quiet'), '612', kindOf(tag));
    assert.equal(attrOf(tag, 'data-stale-after'), '600', kindOf(tag));
  }
  assert.equal(count(out, /\sdata-stale-after=/g), 6, 'data-stale-after も同じ 6 か所');
});

test('D0021-AC-11: 各面に印の要素（node-stale・run-stale・stale-badge・stale-notice・g-stalled）が出る', () => {
  const out = bodyOf(staleParts(staleSnapshot()));
  assert.equal(allEl(out, 'text', 'node-stale').length, 1, '図の節');
  assert.equal(allEl(out, 'span', 'run-stale').length, 1, '一覧の行');
  assert.equal(allEl(out, 'span', 'stale-badge').length, 1, '詳細のバッジ');
  assert.equal(allEl(out, 'div', 'stale-notice').length, 1, '詳細の知らせ');
  assert.equal(allEl(out, 'span', 'g-stalled').length, 1, '時系列の帯');
});

test('D0021-AC-11: HTML は最初は is-stale を持たない（付けるのはパネルのスクリプト）', () => {
  const out = bodyOf(staleParts(staleSnapshot()));
  assert.equal(quietKinds(out).length, 6, '前提：印がある');
  assert.doesNotMatch(out, /is-stale/);
});

const NULL_CASES: readonly (readonly [string, () => WorkDirSnapshot])[] = [
  ...NO_MTIME_KINDS.map((kind) => [`動いているログの更新時刻が読めない（${kind}）`, () => noMtimeOnRunningSnapshot(kind)] as const),
  ['確認待ちの実行（ログに更新時刻がある）', () => withAllMtimes(waitingSnapshot(), mtimeAgo(612))],
  ['記録なし', () => snapshot()],
];
// final のある（終わった）実行は、動いているログが残る写しで AC-46 の表が確かめる（ログの無い終わった写しは、final の絞り込みを外しても通る空振りになる）。

for (const [label, make] of NULL_CASES) {
  test(`D0021-AC-11: ${label}では quietSec が null で、どの面にも data-quiet も印の要素も出ない（対照：動いている写しには出る）`, () => {
    assert.deepEqual(quietKinds(bodyOf(staleParts(staleSnapshot()))), SIX, '対照：出る');
    assert.doesNotMatch(bodyOf(staleParts(make())), MARK_RE);
  });
}

test('D0021-AC-11: 目安が「印なし」（null・渡さない）のときは、印の対象の実行でも、どの面にも属性も印の要素も出ず、今までの HTML と同じ', () => {
  const p = staleParts(staleSnapshot());
  assert.deepEqual(quietKinds(bodyOf(p)), SIX, '対照：目安があれば出る');
  const without = renderViewBody(p.view, p.list);
  assert.doesNotMatch(without, MARK_RE);
  assert.equal(bodyOf(p, null), without);
  assert.doesNotMatch(bodyOf(p, null), MARK_RE);
  assert.doesNotMatch(rootOf(renderPanelHtml(p.view, NONCE, p.list)), MARK_RE);
  assert.doesNotMatch(rootOf(pageOf(p, null)), MARK_RE);
});

// ---- AC-12：同じ入力は同じ HTML ----

test('D0021-AC-12: 同じ記録・同じ「今」・同じ目安なら、同じ HTML になる（時計を読まない）', () => {
  const a = staleParts(staleSnapshot());
  const b = staleParts(staleSnapshot());
  assert.equal(quietKinds(bodyOf(a)).length, 6, '前提：data-quiet が出ている');
  assert.equal(bodyOf(a), bodyOf(b));
  assert.equal(pageOf(a), pageOf(b));
});

// ---- AC-44：再開後の実行（古い途中のログが選ばれても、全ログの最新で決める） ----

test('D0021-AC-44: 動いている段の判定は今のまま（通し番号の大きい古い方の実装が動いている段）。再開後の新しいログに替わらない（守る）', () => {
  const p = staleParts(resumedSnapshot());
  assert.equal(p.view.runningStage, 'implement');
  assert.match(bodyOf(p), /<g class="node is-running" data-node="implement"/);
  assert.equal(p.row.state, 'running');
});

test('D0021-AC-44: 中断した古い途中のログ（3 日前）と再開後の新しいログ（5 秒前）が並ぶ写しは、印の属性が data-quiet="5"（全ログの最新）で出る', () => {
  const out = bodyOf(staleParts(resumedSnapshot()));
  const values = quietValues(out);
  assert.ok(values.length >= 4, `印の属性が出る（${values.length} か所）`);
  assert.deepEqual([...new Set(values)], ['5']);
  for (const kind of ['node', 'row', 'badge', 'notice']) assert.ok(quietKinds(out).includes(kind), `${kind} に出る`);
  for (const tag of quietTags(out)) assert.equal(attrOf(tag, 'data-stale-after'), '600');
});

test('D0021-AC-44: そのパネルを起動しても is-stale は付かない（基準 5 秒は目安 600 秒に届かない。1 分たっても付かない）', () => {
  const h = bootPanel(pageOf(staleParts(resumedSnapshot())));
  const marked = h.doc.querySelectorAll('[data-quiet]');
  assert.ok(marked.length >= 4, `前提：印の属性を持つ要素がある（${marked.length} 個）`);
  assert.deepEqual(marked.filter((n) => n.classList.contains('is-stale')), [], '起動直後');
  h.advance(60_000);
  assert.deepEqual(marked.filter((n) => n.classList.contains('is-stale')), [], '1 分後');
});

// ---- AC-45：放置された実行 ----

test('D0021-AC-45: 全ログの更新時刻が目安より古い（700 秒・900 秒前）写しは、最新の 700 が data-quiet="700" で出て、起動直後に is-stale が付く', () => {
  const p = staleParts(abandonedSnapshot());
  const values = quietValues(bodyOf(p));
  assert.ok(values.length >= 4, `印の属性が出る（${values.length} か所）`);
  assert.deepEqual([...new Set(values)], ['700'], '動いているログ自身（900）ではなく全ログの最新');
  const h = bootPanel(pageOf(p));
  const marked = h.doc.querySelectorAll('[data-quiet]');
  assert.ok(marked.length >= 4);
  assert.ok(
    marked.every((n) => n.classList.contains('is-stale')),
    `すべてに is-stale が付く：${marked.map((n) => `${n.tagName}:${n.classList.contains('is-stale')}`).join(' ')}`,
  );
});

test('D0021-AC-45: 1 つでも目安より新しい（100 秒前）ログがあれば、quietSec はその値（data-quiet="100"）で、is-stale は付かない', () => {
  const p = staleParts(abandonedSnapshot({ latestAgoSec: 100 }));
  const values = quietValues(bodyOf(p));
  assert.ok(values.length >= 4, `印の属性が出る（${values.length} か所）`);
  assert.deepEqual([...new Set(values)], ['100']);
  const h = bootPanel(pageOf(p));
  const marked = h.doc.querySelectorAll('[data-quiet]');
  assert.ok(marked.length >= 4);
  assert.deepEqual(marked.filter((n) => n.classList.contains('is-stale')), []);
});

// ---- AC-46：final のある run には出ない ----

for (const final of FINAL_VALUES) {
  test(`D0021-AC-46: final が ${final} の run に、結果の行が無い途中のログが残っていても、どの面にも data-quiet も印の要素も出ない（対照：final を外すと出る）`, () => {
    assert.equal(quietKinds(bodyOf(staleParts(staleSnapshot()))).length, 6, '対照：final の無い同じ写しには出る');
    assert.doesNotMatch(bodyOf(staleParts(staleSnapshot({ final }))), MARK_RE);
  });
}

// ---- AC-47：前の実行（archive/）には出ない ----

test('D0021-AC-47: 前の実行（previous: true）の写しは、final が無く動いているログに更新時刻があっても、どの面にも印が出ない（対照：previous を外すと出る）', () => {
  assert.equal(quietKinds(bodyOf(staleParts(staleSnapshot()))).length, 6, '対照：previous を外すと出る');
  const out = bodyOf(staleParts(withPrevious(staleSnapshot())));
  assert.doesNotMatch(out, MARK_RE);
});

// ---- AC-48：7 日の上限 ----

test('D0021-AC-48: 更新時刻が 1980 年のログでも、印の基準は 604800（7 日）で頭打ちになり、時間は 168:00:00 で桁あふれしない', () => {
  const out = bodyOf(staleParts(ancientSnapshot()));
  const values = quietValues(out);
  assert.ok(values.length >= 4, `印の属性が出る（${values.length} か所）`);
  assert.deepEqual([...new Set(values)], ['604800']);
  const node = new RegExp('<g class="node [^"]*" data-node="design"[^>]*>[\\s\\S]*?</g>').exec(out)?.[0] ?? '';
  assert.match(node, /data-elapsed="604800">168:00:00</, '図の節');
  assert.match(allEl(out, 'span', 'run-stale')[0]?.inner ?? '', /data-elapsed="604800">168:00:00</, '一覧の行');
  assert.match(allEl(out, 'div', 'stale-notice')[0]?.inner ?? '', /data-elapsed="604800">168:00:00</, '詳細の知らせ');
});

// ---- AC-49：state.json が読めない run には出ない ----

for (const kind of BROKEN_STATE_KINDS) {
  test(`D0021-AC-49: state.json が ${kind} の run は、動いているログに更新時刻があっても、どの面にも data-quiet も印の要素も出ない（対照：state.json を正しい記録にすると出る）`, () => {
    assert.equal(quietKinds(bodyOf(staleParts(staleSnapshot()))).length, 6, '対照：正しい state.json なら出る');
    assert.doesNotMatch(bodyOf(staleParts(brokenStateSnapshot(kind))), MARK_RE);
  });
}

// ---- AC-50：外から来た文字は印の要素に入らない ----

test('D0021-AC-50: セッション名・段の名前・ログの文字に <script> や " を入れた写しでも、印の要素の中身は固定の言葉と時間だけ（対照：印の要素が出ている）', () => {
  const out = bodyOf(staleParts(hostileSnapshot()));
  const expected: readonly (readonly [string, Found[], (text: string) => boolean])[] = [
    ['節の印', allEl(out, 'text', 'node-stale'), (t) => t === squash('⚠ 更新なし 10:12')],
    ['一覧の行の印', allEl(out, 'span', 'run-stale'), (t) => t === squash('⚠ 更新なし 10:12')],
    ['バッジ', allEl(out, 'span', 'stale-badge'), (t) => t === squash('⚠ 止まっているかも')],
    [
      '知らせ',
      allEl(out, 'div', 'stale-notice'),
      (t) => t === squash('この段のログが 10:12 更新されていません。プロセスは調べていません。長い段では、動いていてもログが更新されないことがあります。'),
    ],
    ['時系列の印つきの文字', allEl(out, 'span', 'g-stalled'), (t) => /^\d+:\d{2}(?::\d{2})?●動いている⚠更新なし$/.test(t)],
  ];
  for (const [label, found, ok] of expected) {
    assert.ok(found.length >= 1, `前提：${label}の要素が出ている`);
    for (const f of found) {
      assert.ok(ok(squash(plain(f.inner))), `${label}の中身が固定の言葉だけ：${plain(f.inner)}`);
      assert.doesNotMatch(f.inner, /script|alert|&lt;|&gt;|&quot;|&amp;|&#39;/i, `${label}に外から来た文字が入っていない`);
    }
  }
  for (const tag of quietTags(out)) {
    assert.match(attrOf(tag, 'data-quiet') ?? '', /^\d+$/, '基準の秒は数字だけ');
    assert.match(attrOf(tag, 'data-stale-after') ?? '', /^\d+$/, '目安の秒は数字だけ');
  }
});

// ---- AC-52：目安だけ替えると、違いは data-stale-after の値だけ ----

test('D0021-AC-52: 同じ記録・同じ「今」で目安だけ 600 → 300 に替えると、HTML の違いは data-stale-after の値だけ（値を取り除くと同じ HTML）', () => {
  const p = staleParts(staleSnapshot());
  const norm = (html: string): string => html.replace(/data-stale-after="\d+"/g, 'data-stale-after="N"');
  for (const [a, b] of [
    [bodyOf(p, 600), bodyOf(p, 300)],
    [pageOf(p, 600), pageOf(p, 300)],
  ] as const) {
    assert.match(a, /data-stale-after="600"/, '前提：目安 600 が出ている');
    assert.match(b, /data-stale-after="300"/, '前提：目安 300 が出ている');
    assert.doesNotMatch(b, /data-stale-after="600"/);
    assert.equal(count(a, /data-stale-after=/g), count(b, /data-stale-after=/g));
    assert.equal(norm(a), norm(b));
  }
});
