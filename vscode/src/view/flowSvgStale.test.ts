// 図の節・入る矢印の「⚠ 更新なし」の印（D0021・AC-24・25・26・54。目安なし・at なしの見え方は AC-11・AC-35 の図の分）。
// 節（PipelineNode）に quietSec を手で足して renderFlowSvg に目安の秒を渡し、描かれ方を文字列で確かめる（純粋。記録の写しは通さない）。
// 記録の写しから quietSec を作る側は domain/pipelineViewStale.test.ts が確かめる。CSS は panelHtml.ts の STYLE を renderPanelHtml の出力から読む。
// 「出ない側」の確かめには、同じ入力に出る条件だけを足した対照を付ける（空振りを防ぐ）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { PipelineNode } from '../domain/pipelineView.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { extractCss, motionOutsideNoPreference, parseCss } from '../test/cssBlocks.ts';
import { snapshot } from '../test/fixtures.ts';
import { finishedView, runningSnapshot, runningView, sendBackView, viewAt, waitingView } from '../test/liveFixtures.ts';
import { STALE_AFTER_SEC } from '../test/staleFixtures.ts';
import { renderFlowSvg } from './flowSvg.ts';
import { renderPanelHtml } from './panelHtml.ts';

const AFTER = STALE_AFTER_SEC;
const count = (text: string, re: RegExp): number => (text.match(re) ?? []).length;
const plain = (text: string): string => text.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();

/** 節 id の <g>（節の中に <g> は入れ子にならない）。 */
const nodeGroup = (svg: string, id: string): string => new RegExp(`<g class="node [^"]*" data-node="${id}"[^>]*>[\\s\\S]*?</g>`).exec(svg)?.[0] ?? '';
const openTag = (markup: string): string => /^<[a-z]+\b[^>]*>/.exec(markup)?.[0] ?? '';
const attrOf = (attrs: string, name: string): string | undefined => new RegExp(`(?:^|\\s)${name}="([^"]*)"`).exec(attrs)?.[1];
/** <text> のうち、クラスに cls を持つものの {属性, 中身}（<text> は入れ子にならない） */
function textsWithClass(markup: string, cls: string): { attrs: string; inner: string }[] {
  return [...markup.matchAll(/<text\b([^>]*)>([\s\S]*?)<\/text>/g)]
    .map((m) => ({ attrs: m[1]!, inner: m[2]! }))
    .filter((e) => new RegExp(`class="[^"]*\\b${cls}\\b[^"]*"`).test(e.attrs));
}
const lineTags = (svg: string): string[] => [...svg.matchAll(/<line\b[^>]*>/g)].map((m) => m[0]);

// ---- 節の組み立て（domain が作る形を手で書く） ----

/** 節 id の節に quietSec を足す。undefined なら項目ごと足さない。 */
function withQuiet(nodes: PipelineNode[], quietSec: number | null | undefined, id = 'design'): PipelineNode[] {
  return nodes.map((n) => (n.id === id && quietSec !== undefined ? ({ ...n, quietSec } as PipelineNode) : n));
}
/** quietSec の項目ごと無い節（手で作った節。項目が無くても例外を出さず、印も出さないことを見る） */
const withoutQuietItem = (nodes: PipelineNode[]): PipelineNode[] =>
  nodes.map((n) => {
    const copy: Record<string, unknown> = { ...n };
    delete copy.quietSec;
    return copy as unknown as PipelineNode;
  });
/** すべての節に quietSec を足す（動いていない節に入っていても出ないことを見る） */
const everyNode = (nodes: PipelineNode[], quietSec: number): PipelineNode[] => nodes.map((n) => ({ ...n, quietSec }) as PipelineNode);
/** 設計が動いている図の節（「今」は始まりの 83 秒後） */
const running = (): PipelineNode[] => runningView(83).nodes;
/** 印あり：設計が動いていて、最後の更新から 612 秒、目安 600 秒 */
const stale = (): string => renderFlowSvg(withQuiet(running(), 612), new Set(), AFTER);
/** 印なし（今までの図） */
const calm = (): string => renderFlowSvg(running());

/** 印の属性と印の要素を取り除く */
function stripMarks(svg: string): string {
  return svg
    .replace(/ data-quiet="[^"]*"/g, '')
    .replace(/ data-stale-after="[^"]*"/g, '')
    .replace(/<text\b[^>]*\bclass="[^"]*\bnode-stale\b[^"]*"[^>]*>[\s\S]*?<\/text>/g, '');
}

// ---- CSS を波括弧で読む ----

interface Flat {
  selector: string;
  body: string;
  media: string | null;
  order: number;
}
function flatRules(css: string): Flat[] {
  const flat: Flat[] = [];
  parseCss(css).forEach((r, order) => {
    if (r.keyframes) return;
    for (const sel of r.selector.split(',')) flat.push({ selector: sel.trim().replace(/\s+/g, ' '), body: r.body, media: r.media, order });
  });
  return flat;
}
const panelCss = (): string => extractCss(renderPanelHtml(runningView(83), 'n'));
const NO_PREFERENCE = /\(\s*prefers-reduced-motion\s*:\s*no-preference\s*\)/;
const hasToken = (selector: string, token: string): boolean => new RegExp(`\\.${token}(?![\\w-])`).test(selector);
const lastCompound = (selector: string): string => selector.trim().split(/\s+/).pop() ?? '';
const decl = (body: string, prop: string): string | null => new RegExp(`(?<![-\\w])${prop}\\s*:\\s*([^;]+)`).exec(body)?.[1]?.trim() ?? null;
const classCount = (selector: string): number => (selector.match(/\.[\w-]+|\[[^\]]+\]|:[\w-]+/g) ?? []).length;
/** a が b に勝つか（クラスの数が多い、同じなら後ろにある） */
const beats = (a: Flat, b: Flat): boolean =>
  classCount(a.selector) > classCount(b.selector) || (classCount(a.selector) === classCount(b.selector) && a.order > b.order);

// ---- AC-24：節の印 ----

test('D0021-AC-24: quietSec のある動いている段の節に、data-quiet・data-stale-after と、「⚠ 更新なし」と data-elapsed つきの時間を持つ印（text.node-stale）が出る', () => {
  const group = nodeGroup(stale(), 'design');
  assert.match(openTag(group), /\sdata-quiet="612"/);
  assert.match(openTag(group), /\sdata-stale-after="600"/);
  const marks = textsWithClass(group, 'node-stale');
  assert.equal(marks.length, 1, '印の要素が 1 つ');
  assert.equal(plain(marks[0]!.inner), '⚠ 更新なし 10:12');
  assert.match(marks[0]!.inner, /<tspan\b[^>]*\bdata-elapsed="612"[^>]*>10:12<\/tspan>/, '時間は data-elapsed（基準の秒）つきの要素');
});

test('D0021-AC-24: 基準の秒は整数部（83.9 → data-quiet="83"・data-elapsed="83"・1:23）', () => {
  const group = nodeGroup(renderFlowSvg(withQuiet(running(), 83.9), new Set(), AFTER), 'design');
  assert.match(openTag(group), /\sdata-quiet="83"/);
  assert.equal(plain(textsWithClass(group, 'node-stale')[0]?.inner ?? ''), '⚠ 更新なし 1:23');
});

test('D0021-AC-24: 印は節の 2 行目（経過の文字 node-detail と同じ位置）に置く', () => {
  const group = nodeGroup(stale(), 'design');
  const mark = textsWithClass(group, 'node-stale')[0];
  const detail = textsWithClass(group, 'node-detail')[0];
  assert.ok(mark, '前提：印の要素がある');
  assert.ok(detail, '経過の文字は残る（隠すのは CSS）');
  assert.equal(attrOf(mark.attrs, 'x'), attrOf(detail.attrs, 'x'));
  assert.equal(attrOf(mark.attrs, 'y'), attrOf(detail.attrs, 'y'));
});

test('D0021-AC-24: 状態の文字は「● 動いている」のまま、節は is-running のまま（印を添えても替えない）', () => {
  const svg = stale();
  const group = nodeGroup(svg, 'design');
  assert.match(group, /node-stale/, '前提：印の要素がある');
  assert.match(group, /class="node-status"[^>]*>[^<]*● 動いている</);
  assert.match(svg, /<g class="node is-running" data-node="design"/);
});

test('D0021-AC-24: 動いている段でない節（完了・まだ）に quietSec が入っていても、印は出ない（対照：動いている節に入れると出る）', () => {
  assert.match(stale(), /node-stale/, '対照：動いている節に入れると出る');
  const nodes = running().map((n) => (n.status === 'running' ? n : ({ ...n, quietSec: 612 } as PipelineNode)));
  const svg = renderFlowSvg(nodes, new Set(), AFTER);
  assert.doesNotMatch(svg, /data-quiet|data-stale-after|node-stale/);
});

test('D0021-AC-24: 選べる節（差し戻しのある実装・data-reasons あり）が動いていても、印の属性は同じ <g> に付き、選びの属性は残る', () => {
  const nodes = sendBackView(1).nodes.map((n) =>
    n.id === 'implement' ? ({ ...n, status: 'running', runningSec: 5, quietSec: 612 } as PipelineNode) : n,
  );
  const group = nodeGroup(renderFlowSvg(nodes, new Set(['implement']), AFTER), 'implement');
  assert.match(openTag(group), /\sdata-quiet="612"/);
  assert.match(openTag(group), /\sdata-reasons="implement"/);
  assert.match(openTag(group), /aria-pressed="false"/);
  assert.match(group, /node-stale/);
});

test('D0021-AC-24: CSS：印（.node-stale）は is-stale が付くまで見えず（display: none）、.node.is-stale の下では見える', () => {
  const rules = flatRules(panelCss()).filter((r) => r.media === null && hasToken(lastCompound(r.selector), 'node-stale'));
  const hide = rules.find((r) => !hasToken(r.selector, 'is-stale') && decl(r.body, 'display') === 'none');
  const show = rules.find((r) => hasToken(r.selector, 'is-stale') && hasToken(r.selector, 'node') && ![null, 'none'].includes(decl(r.body, 'display')));
  assert.ok(hide, '.node-stale は display: none の規則がある');
  assert.ok(show, '.node.is-stale .node-stale は見える規則がある');
  assert.ok(classCount(show.selector) > classCount(hide.selector), '見える規則の方が強い（クラスの数が多い）');
});

test('D0021-AC-24: CSS：印が付く（is-stale）と、同じ位置の経過の文字（.node-detail）は隠れる（2 つが重ならない）', () => {
  const rules = flatRules(panelCss()).filter((r) => r.media === null && hasToken(lastCompound(r.selector), 'node-detail'));
  const hide = rules.find((r) => hasToken(r.selector, 'is-stale') && hasToken(r.selector, 'node') && decl(r.body, 'display') === 'none');
  assert.ok(hide, '.node.is-stale .node-detail は display: none');
});

// ---- AC-25：点線の枠・脈打ちが止まる・動きの CSS は no-preference の中だけ ----

test('D0021-AC-25: CSS：.node.is-stale の枠（.shape）が点線になる（stroke-dasharray。@media の外なので、動きを減らす設定でも点線）', () => {
  const rule = flatRules(panelCss()).find(
    (r) =>
      r.media === null &&
      hasToken(lastCompound(r.selector), 'shape') &&
      hasToken(r.selector, 'node') &&
      hasToken(r.selector, 'is-stale') &&
      !hasToken(r.selector, 'is-picked') &&
      ![null, 'none'].includes(decl(r.body, 'stroke-dasharray')),
  );
  assert.ok(rule, '.node.is-stale .shape に stroke-dasharray がある');
});

test('D0021-AC-25: CSS：no-preference の中の .node.is-stale .shape が animation: none で、脈打ち（pulse）の規則に勝つ', () => {
  const rules = flatRules(panelCss());
  const stop = rules.find(
    (r) =>
      r.media !== null &&
      NO_PREFERENCE.test(r.media) &&
      hasToken(lastCompound(r.selector), 'shape') &&
      hasToken(r.selector, 'is-stale') &&
      !hasToken(r.selector, 'is-picked') &&
      /animation\s*:\s*none\b/.test(r.body),
  );
  assert.ok(stop, 'no-preference の中に .node.is-stale .shape { animation: none } がある');
  const pulse = rules.find((r) => /animation\s*:[^;]*\bpulse\b/.test(r.body));
  assert.ok(pulse, '脈打ちの規則がある（今のまま）');
  assert.ok(beats(stop, pulse), `止める規則（${stop.selector}）が脈打ちの規則（${pulse.selector}）に勝つ`);
});

test('D0021-AC-25: 動き（animation・@keyframes）は、足したあとも prefers-reduced-motion: no-preference の中だけにある（守る）', () => {
  assert.deepEqual(motionOutsideNoPreference(panelCss()), []);
});

// ---- AC-26：出ない側（対照つき） ----

const NO_MARK: readonly (readonly [string, () => PipelineNode[]])[] = [
  ['確認待ちの図（動いている段が無い。全部の節に quietSec が入っていても）', () => everyNode(waitingView(40).nodes, 612)],
  ['終わった図（全部の節に quietSec が入っていても）', () => everyNode(finishedView().nodes, 612)],
  ['記録なしの図（全部の節に quietSec が入っていても）', () => everyNode(buildPipelineView(snapshot()).nodes, 612)],
  ['動いている段はあるが quietSec が null の図', () => withQuiet(running(), null)],
  ['動いている段はあるが quietSec の項目が無い図（手で作った節）', () => withoutQuietItem(running())],
];

for (const [label, nodes] of NO_MARK) {
  test(`D0021-AC-26: ${label}には、data-quiet も node-stale も出ない（対照：quietSec のある動いている図には出る）`, () => {
    assert.match(stale(), /data-quiet=/, '対照：出る図');
    assert.match(stale(), /node-stale/, '対照：出る図');
    const svg = renderFlowSvg(nodes(), new Set(), AFTER);
    assert.doesNotMatch(svg, /data-quiet|data-stale-after|node-stale/);
  });
}

test('D0021-AC-26: 動いている段で quietSec が null のとき、入る矢印は今までどおり流れ（is-flowing）、印の属性は付かない（対照：quietSec が数なら、流れる矢印に属性が付く）', () => {
  const flowing = (svg: string): string[] => lineTags(svg).filter((tag) => /\bis-flowing\b/.test(tag));
  assert.ok(
    flowing(stale()).some((tag) => /\sdata-quiet="612"/.test(tag)),
    '対照：quietSec が数なら、流れる矢印に属性が付く',
  );
  const svg = renderFlowSvg(withQuiet(running(), null), new Set(), AFTER);
  assert.ok(flowing(svg).length >= 1, '入る矢印は今までどおり流れる');
  assert.doesNotMatch(svg, /data-quiet|data-stale-after/);
});

test('D0021-AC-26: 目安の手前の見え方は D0017 のまま：印の属性と node-stale を取り除いた図は、印のない図と同じ（経過の文字も残る）', () => {
  const marked = stale();
  assert.match(marked, /node-stale/, '前提：印の要素がある');
  assert.match(marked, /data-quiet=/, '前提：印の属性がある');
  assert.equal(stripMarks(marked), calm());
  assert.match(nodeGroup(marked, 'design'), /経過 <tspan class="elapsed" data-elapsed="83">1:23<\/tspan>/);
});

test('D0021-AC-11: 目安が「印なし」（null・渡さない）のときは、quietSec があっても、属性も印の要素も出ず、今までの図と同じ', () => {
  const nodes = withQuiet(running(), 612);
  assert.match(renderFlowSvg(nodes, new Set(), AFTER), /data-quiet=/, '対照：目安があれば出る');
  for (const svg of [renderFlowSvg(nodes, new Set(), null), renderFlowSvg(nodes, new Set()), renderFlowSvg(nodes)]) {
    assert.doesNotMatch(svg, /data-quiet|data-stale-after|node-stale/);
    assert.equal(svg, calm());
  }
});

// ---- AC-54：入る矢印 ----

test('D0021-AC-54: 動いている段へ入る矢印（line.edge.is-flowing）にだけ、節と同じ値の data-quiet・data-stale-after が付く', () => {
  const svg = stale();
  const lines = lineTags(svg);
  assert.equal(lines.length, 10);
  const into = runningView(83).nodes.findIndex((n) => n.id === 'design') - 1;
  const group = openTag(nodeGroup(svg, 'design'));
  lines.forEach((tag, i) => {
    if (i === into) {
      assert.match(tag, /\bis-flowing\b/);
      assert.equal(attrOf(tag, 'data-quiet'), attrOf(group, 'data-quiet'), '節と同じ基準の秒');
      assert.equal(attrOf(tag, 'data-stale-after'), attrOf(group, 'data-stale-after'), '節と同じ目安の秒');
      assert.equal(attrOf(tag, 'data-quiet'), '612');
      assert.equal(attrOf(tag, 'data-stale-after'), '600');
    } else {
      assert.doesNotMatch(tag, /data-quiet|data-stale-after/, `${i} 本目の矢印は動いている段へ入らない`);
    }
  });
  assert.equal(count(svg, /data-quiet=/g), 2, '節の 1 か所と、入る矢印の 1 か所だけ');
});

test('D0021-AC-54: 始まりの時刻が読めない（Prompt に at が無く is-flowing が付かない）ときは、矢印に属性も is-flowing も付かない（対照：at のある図は付く）', () => {
  assert.ok(lineTags(stale()).some((tag) => /\bis-flowing\b/.test(tag) && /\sdata-quiet="612"/.test(tag)), '対照：at のある図の流れる矢印には付く');
  const nodes = withQuiet(viewAt(runningSnapshot({ omitAt: true }), 83).nodes, 612);
  const lines = lineTags(renderFlowSvg(nodes, new Set(), AFTER));
  assert.equal(lines.length, 10);
  for (const tag of lines) assert.doesNotMatch(tag, /is-flowing|data-quiet|data-stale-after/);
});

test('D0021-AC-35: Prompt に at が無い（経過が出ない）動いている節にも、更新なしの印は出る（矢印は出ない）', () => {
  const svg = renderFlowSvg(withQuiet(viewAt(runningSnapshot({ omitAt: true }), 83).nodes, 612), new Set(), AFTER);
  const group = nodeGroup(svg, 'design');
  assert.match(openTag(group), /\sdata-quiet="612"/);
  assert.equal(plain(textsWithClass(group, 'node-stale')[0]?.inner ?? ''), '⚠ 更新なし 10:12');
  assert.doesNotMatch(group, /data-elapsed="83"/, '経過の要素は出ない（D0017-AC-19）');
});

test('D0021-AC-54: CSS：no-preference の中で .edge.is-flowing.is-stale が animation: none・stroke-dasharray: none（流れる点が止まり、線は見えたまま）', () => {
  const rules = flatRules(panelCss());
  const stop = rules.find(
    (r) =>
      r.media !== null &&
      NO_PREFERENCE.test(r.media) &&
      hasToken(lastCompound(r.selector), 'edge') &&
      hasToken(r.selector, 'is-flowing') &&
      hasToken(r.selector, 'is-stale'),
  );
  assert.ok(stop, 'no-preference の中に .edge.is-flowing.is-stale の規則がある');
  assert.match(stop.body, /animation\s*:\s*none\b/);
  assert.equal(decl(stop.body, 'stroke-dasharray'), 'none');
  // 線は見えたまま
  assert.doesNotMatch(stop.body, /display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0\s*(;|$)/);
  const width = decl(stop.body, 'stroke-width');
  assert.ok(width === null || Number.parseFloat(width) > 0, `線の太さ ${String(width)}`);
  // 流れる点の規則（animation: flow）に勝つ
  const flowing = rules.find((r) => /animation\s*:[^;]*\bflow\b/.test(r.body));
  assert.ok(flowing, '流れる点の規則がある（今のまま）');
  assert.ok(beats(stop, flowing), `止める規則（${stop.selector}）が流れる点の規則（${flowing.selector}）に勝つ`);
});
