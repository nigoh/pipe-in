// 図の節の上限の表示（D0051 の AC-25 の SVG・AC-47〜61）：金額の対・棒・言葉・「N 回目」・状態のクラス・高さ・動いている段・外から来た文字・CSP。
// 節の中の置き方（行の並び・数値）は設計の第 3 節で、画面の確認（run-panel-budget-*）で詰めてよい。ここで固定するのは、変えてはいけないもの：
// 表示の無い節の高さ 50 と節の幅 176、表示のある節は高くなり（言葉だけ < 金額の対と棒 < さらに言葉か N 回目）、後ろの節・矢印・viewBox が増えた分だけずれること。
// 表示の判断（金額・棒・言葉の出し分け）は、節に手で budget を入れた単体のテストで見る（domain の判断に頼らない）。
// 記録から図までの通しは、buildPipelineView を通すテスト（AC-53〜56・58〜60）で見る。
// PipelineNode.budget は、実装の段で型に入るまで、型に頼らず入れる。赤の理由は「まだ描いていない」：空の形のままの図は、表示の無い今の図と同じ。
// 「今のまま通る。守る」と書いたものは、今の作りで通り、実装のあとも通り続けることを見張る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { renderFlowSvg } from './flowSvg.ts';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';
import { buildPipelineView, reasonNodeIds } from '../domain/pipelineView.ts';
import type { PipelineNode, PipelineView } from '../domain/pipelineView.ts';
import { extractCss, parseCss } from '../test/cssBlocks.ts';
import { budgetRun, budgetView, classesOf, nodeG, pipeStages, runningLogFile, textsOf, titleOf, withoutBudgetKeys } from '../test/budgetFixtures.ts';
import { clockAt, fixtureSnapshot } from '../test/liveFixtures.ts';

const STOP = 'error_max_budget_usd';
const WORD_NEAR = '上限に近い';
const WORD_OVER = '上限を超えた';
const WORD_STOPPED = '上限で止まった';
const WORDS = [WORD_NEAR, WORD_OVER, WORD_STOPPED];
/** 金額の対（$0.42 / $1.00・$10000+ / $10000.00 など） */
const PAIR = /\$[0-9.]+\+? \/ \$[0-9.]+\+?/;
const NODE_WIDTH = 176;
const BAR_WIDTH = 152;

// ---- 節に入れる budget（手で作る） ----

interface BudgetLike {
  state: 'ok' | 'near' | 'over' | 'stopped';
  ratio: number | null;
  costMilli: number | null;
  limitMilli: number | null;
  nth: number;
  runCount: number;
}
/** 割合のある budget（費用・上限は USD。1/1000 ドルの整数は四捨五入で作る） */
function budgetFor(state: BudgetLike['state'], cost: number, limit: number, nth = 1, runCount = 1): BudgetLike {
  return { state, ratio: cost / limit, costMilli: Math.round(cost * 1000), limitMilli: Math.round(limit * 1000), nth, runCount };
}
/** 割合の無い「止まった」（上限の値が記録に無い・続きの会話の印のある回） */
const wordOnly = (nth = 1, runCount = 1): BudgetLike => ({ state: 'stopped', ratio: null, costMilli: null, limitMilli: null, nth, runCount });

/** 節に budget を入れる（byId にある節だけ）。 */
function withBudgets(nodes: PipelineNode[], byId: Readonly<Record<string, BudgetLike | null>>): PipelineNode[] {
  return nodes.map((n) => (n.id in byId ? ({ ...n, budget: byId[n.id] } as unknown as PipelineNode) : n));
}
const budgetOfNode = (node: PipelineNode): unknown => (node as unknown as { budget?: unknown }).budget;

/** 開発フローの 4 つの段（要件定義・設計・テスト先行・実装）が終わった図の節。 */
function doneNodes(): PipelineNode[] {
  return budgetView(['requirements', 'design', 'red', 'implement'].map((stage, i) => budgetRun({ stage, seq: i + 1, costUsd: 0.5 }))).nodes;
}
const svgOf = (nodes: PipelineNode[]): string => renderFlowSvg(nodes, new Set(), null);

// ---- SVG の文字の読み方 ----

// 節の <g>・クラス・<title>・<text> の読み方は test/budgetFixtures.ts（nodeG・classesOf・titleOf・textsOf）
const ariaOf = (svg: string): string => /aria-label="([^"]*)"/.exec(svg)?.[1] ?? '';
const attrOf = (tag: string, name: string): string | null => new RegExp(`\\s${name}="([^"]*)"`).exec(tag)?.[1] ?? null;
const rectByClass = (g: string, cls: string): string | null => new RegExp(`<rect\\b[^>]*\\sclass="${cls}"[^>]*>`).exec(g)?.[0] ?? null;
const hasBudgetClass = (g: string): boolean => classesOf(g).some((c) => c.startsWith('is-budget-'));
const shown = (g: string): boolean => PAIR.test(g) || WORDS.some((w) => g.includes(w)) || g.includes('budget-fill') || g.includes('budget-track');

// ======== AC-25（SVG）：見本の図は、実装の前に測った値のまま ========
//
// 10 個の見本（前の版の形 pipe_in/・今の形 pipe_dev/・showcase*）の図の SVG の SHA-256。
// 測り方：この機能を入れる前（main の 38cc1d6）のコードで、fixtureSnapshot(…parts) を buildPipelineView(snap, clockAt(100)) で図の状態にし、
// renderFlowSvg(view.nodes, new Set(reasonNodeIds(view)), null) の文字を SHA-256 にした（テストの中の式と同じ）。時計は clockAt(100)（固定）。
// 前の版の形（pipe_in/）と今の形（pipe_dev/）は、図に出す節・費用・時間が同じ形なので、同じ段のものは SHA-256 も同じ値になる（測ったとおり）。
const sha256 = (text: string): string => createHash('sha256').update(text, 'utf8').digest('hex');
const FIXTURE_SVG_SHA256: Readonly<Record<string, string>> = {
  'pipe_in/finished': 'fa9a8c8ed0289d9b3cdfebf0bcf2c5dcabf883d4b685127f6c4c45e767d4400c',
  'pipe_in/running': 'f66977c820fd2a5769888cb2eee729a388d4280a6d7394ff3009755a2a7f045b',
  'pipe_in/waiting': '1b7a273efce986386fa2f96bdd86dd7ed4d8f4c8380c227ee9d6c2a1d4d9e8d1',
  'pipe_dev/finished': 'fa9a8c8ed0289d9b3cdfebf0bcf2c5dcabf883d4b685127f6c4c45e767d4400c',
  'pipe_dev/running': 'f66977c820fd2a5769888cb2eee729a388d4280a6d7394ff3009755a2a7f045b',
  'pipe_dev/waiting': '1b7a273efce986386fa2f96bdd86dd7ed4d8f4c8380c227ee9d6c2a1d4d9e8d1',
  showcase: 'b1de8fc9812e50fa9f1a2cd45e320a5fbda32a2ad754943869b08ff0d4d4da11',
  showcase_running: 'a9a1e2d74bdfcf9330b7e3d68285314b6c299e2384ed8a8c45a43f9bab7cba76',
  showcase_running_next: '0adacaf5969e93d201bfe461d20f309efba6a9421197c0b912530458655ab83c',
  showcase_waiting: '5443578cbe8b4151a7a7e3f7e0ecd6fdcc8bb39aaa011687568d1706121dff24',
};
for (const [name, expected] of Object.entries(FIXTURE_SVG_SHA256)) {
  test(`D0051-AC-25: 見本 ${name} の図の SVG の SHA-256 は、実装の前に測った値のまま。今のまま通る。守る`, () => {
    const view = buildPipelineView(fixtureSnapshot(...name.split('/')), clockAt(100));
    const svg = renderFlowSvg(view.nodes, new Set(reasonNodeIds(view)), null);
    assert.match(svg, /^<svg class="flow"/);
    assert.equal(sha256(svg), expected);
  });
}

// ======== AC-47：金額の対 ========

for (const [cost, limit, pair] of [
  [0.42, 1.0, '$0.42 / $1.00'],
  [0.004, 0.01, '$0.004 / $0.01'],
  [123.456, 200, '$123.456 / $200.00'],
] as const) {
  test(`D0051-AC-47: 割合のある、終わった段の節の SVG に金額の対がある：${cost} / ${limit} → ${pair}`, () => {
    const g = nodeG(svgOf(withBudgets(doneNodes(), { requirements: budgetFor('ok', cost, limit) })), 'requirements');
    assert.ok(textsOf(g).some((t) => t.includes(pair)), `${pair} が節の文字にある: ${textsOf(g).join(' | ')}`);
  });
}

test('D0051-AC-47: 費用が上限の 8 割以上の節（近い・超えた・止まった）にも金額の対がある', () => {
  const nodes = withBudgets(doneNodes(), {
    requirements: budgetFor('near', 0.9, 1.0),
    design: budgetFor('over', 1.2, 1.0),
    red: budgetFor('stopped', 1.02, 1.0),
  });
  const svg = svgOf(nodes);
  assert.ok(nodeG(svg, 'requirements').includes('$0.90 / $1.00'));
  assert.ok(nodeG(svg, 'design').includes('$1.20 / $1.00'));
  assert.ok(nodeG(svg, 'red').includes('$1.02 / $1.00'));
});

// ======== AC-48：棒 ========

/** 棒の塗りの幅。棒が無ければ null。 */
function fillWidth(g: string): number | null {
  const tag = rectByClass(g, 'budget-fill');
  return tag === null ? null : Number(attrOf(tag, 'width'));
}

for (const [ratio, expected] of [
  [0.42, 63.84],
  [0.5, 76],
  [1.0, 152],
  [1.5, 152],
] as const) {
  test(`D0051-AC-48: 棒の塗りの幅は割合に比例し、枠（幅 ${BAR_WIDTH}）からはみ出さない：割合 ${ratio} → ${expected}`, () => {
    const state = ratio > 1 ? 'over' : ratio >= 0.8 ? 'near' : 'ok';
    const g = nodeG(svgOf(withBudgets(doneNodes(), { requirements: budgetFor(state, ratio, 1.0) })), 'requirements');
    const width = fillWidth(g);
    assert.ok(width !== null, '棒の塗り（budget-fill）がある');
    assert.ok(Math.abs(width - expected) < 0.01, `幅 ${width} は ${expected}`);
    assert.equal(Number(attrOf(rectByClass(g, 'budget-track')!, 'width')), BAR_WIDTH, '枠の幅');
    assert.ok(width <= BAR_WIDTH, '枠からはみ出さない');
  });
}

test('D0051-AC-48: 割合 0 の棒は空の枠（枠はあり、塗りの幅は 0）', () => {
  const g = nodeG(svgOf(withBudgets(doneNodes(), { requirements: budgetFor('ok', 0, 1.0) })), 'requirements');
  assert.ok(rectByClass(g, 'budget-track') !== null, '枠がある');
  assert.equal(fillWidth(g) ?? 0, 0);
});

test('D0051-AC-48: 棒は SVG の属性（x・y・width・height）で描き、style 属性を使わない', () => {
  const g = nodeG(svgOf(withBudgets(doneNodes(), { requirements: budgetFor('near', 0.9, 1.0) })), 'requirements');
  const fill = rectByClass(g, 'budget-fill');
  assert.ok(fill !== null, '棒の塗りがある');
  for (const name of ['x', 'y', 'width', 'height']) assert.ok(attrOf(fill, name) !== null, `棒の塗りに ${name} 属性`);
  assert.doesNotMatch(g, /\sstyle=/);
});

// ======== AC-49：言葉 ========

for (const [state, word, cost] of [
  ['near', WORD_NEAR, 0.9],
  ['over', WORD_OVER, 1.2],
  ['stopped', WORD_STOPPED, 1.02],
] as const) {
  test(`D0051-AC-49: 「${state}」の節に「${word}」の言葉が入り、ほかの 2 つの言葉は入らない`, () => {
    const g = nodeG(svgOf(withBudgets(doneNodes(), { requirements: budgetFor(state, cost, 1.0) })), 'requirements');
    assert.ok(textsOf(g).some((t) => t === word), `${word} が文字として見える: ${textsOf(g).join(' | ')}`);
    assert.deepEqual(WORDS.filter((w) => w !== word && g.includes(w)), []);
  });
}

test('D0051-AC-49: 「余裕」の節には、3 つの言葉のどれも入らない（金額の対と棒は出る）', () => {
  const g = nodeG(svgOf(withBudgets(doneNodes(), { requirements: budgetFor('ok', 0.2, 1.0) })), 'requirements');
  assert.ok(PAIR.test(g), '対照：金額の対は出る');
  assert.deepEqual(WORDS.filter((w) => g.includes(w)), []);
});

// ======== AC-50：状態のクラスと色 ========

for (const [state, cost] of [
  ['ok', 0.2],
  ['near', 0.9],
  ['over', 1.2],
  ['stopped', 1.02],
] as const) {
  test(`D0051-AC-50: 「${state}」の節の <g> は is-budget-${state} のクラスを持ち、ほかの is-budget-* は持たない`, () => {
    const g = nodeG(svgOf(withBudgets(doneNodes(), { requirements: budgetFor(state, cost, 1.0) })), 'requirements');
    assert.deepEqual(classesOf(g).filter((c) => c.startsWith('is-budget-')), [`is-budget-${state}`]);
    assert.ok(classesOf(g).includes('node'), '節のクラス node は残る');
  });
}

test('D0051-AC-50: 状態を持たない節（budget が null）の <g> には、どの is-budget-* も付かない', () => {
  const svg = svgOf(withBudgets(doneNodes(), { requirements: budgetFor('near', 0.9, 1.0), design: null }));
  assert.ok(hasBudgetClass(nodeG(svg, 'requirements')), '対照：状態を持つ節には付く');
  for (const id of ['design', 'red', 'implement', 'input', 'final']) assert.equal(hasBudgetClass(nodeG(svg, id)), false, id);
});

test('D0051-AC-50: 割合の無い「止まった」の節も is-budget-stopped のクラスを持つ', () => {
  const g = nodeG(svgOf(withBudgets(doneNodes(), { requirements: wordOnly() })), 'requirements');
  assert.ok(classesOf(g).includes('is-budget-stopped'));
});

test('D0051-AC-50: 色は状態のクラスから CSS で決める：パネルの CSS に is-budget-near・is-budget-over・is-budget-stopped の規則がある', () => {
  const rules = parseCss(extractCss(renderPanelHtml(budgetView([budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.5 })]), 'N')));
  for (const state of ['near', 'over', 'stopped']) {
    assert.ok(
      rules.some((r) => r.selector.includes(`.is-budget-${state}`)),
      `.is-budget-${state} の規則がある`,
    );
  }
});

// ======== AC-51：言葉が <title> と aria-label に入る ========

for (const [state, word, cost] of [
  ['near', WORD_NEAR, 0.9],
  ['over', WORD_OVER, 1.2],
  ['stopped', WORD_STOPPED, 1.02],
] as const) {
  test(`D0051-AC-51: 「${state}」の節の <title> に「${word}」が入る`, () => {
    const g = nodeG(svgOf(withBudgets(doneNodes(), { requirements: budgetFor(state, cost, 1.0) })), 'requirements');
    assert.ok(titleOf(g).includes(word), `title: ${titleOf(g)}`);
    assert.ok(titleOf(g).includes('要件定義'), '節の名前も title に残る');
  });

  test(`D0051-AC-51: 「${state}」の節の名前と「${word}」が、SVG 全体の aria-label に入る`, () => {
    const aria = ariaOf(svgOf(withBudgets(doneNodes(), { requirements: budgetFor(state, cost, 1.0) })));
    assert.match(aria, new RegExp(`要件定義[^、]*${word}`), `aria-label: ${aria}`);
  });
}

test('D0051-AC-51: 「余裕」の節と状態を持たない節は、aria-label が今のまま（言葉を足さない）。今のまま通る。守る', () => {
  const before = ariaOf(svgOf(doneNodes()));
  assert.equal(ariaOf(svgOf(withBudgets(doneNodes(), { requirements: budgetFor('ok', 0.2, 1.0) }))), before);
  assert.deepEqual(WORDS.filter((w) => before.includes(w)), []);
});

// ======== AC-52：2 回以上流れた段の節に「N 回目」 ========

test('D0051-AC-52: 2 回以上流れた段の、金額の対を出す節に「2 回目」が文字で見え、<title> にも入る', () => {
  const g = nodeG(svgOf(withBudgets(doneNodes(), { requirements: budgetFor('near', 0.9, 1.0, 2, 3) })), 'requirements');
  assert.ok(textsOf(g).some((t) => t.includes('2 回目')), `文字: ${textsOf(g).join(' | ')}`);
  assert.ok(titleOf(g).includes('2 回目'), `title: ${titleOf(g)}`);
});

test('D0051-AC-52: 余裕の節でも、2 回以上流れた段なら「N 回目」が出る', () => {
  const g = nodeG(svgOf(withBudgets(doneNodes(), { requirements: budgetFor('ok', 0.2, 1.0, 1, 2) })), 'requirements');
  assert.ok(PAIR.test(g), '対照：金額の対は出る');
  assert.ok(textsOf(g).some((t) => t.includes('1 回目')));
});

test('D0051-AC-52: 1 回だけの段の節には「N 回目」が出ない（金額の対は出る）', () => {
  const g = nodeG(svgOf(withBudgets(doneNodes(), { requirements: budgetFor('near', 0.9, 1.0, 1, 1) })), 'requirements');
  assert.ok(PAIR.test(g), '対照：金額の対は出る');
  assert.doesNotMatch(g, /\d+ 回目/);
});

test('D0051-AC-52: 状態を持たない節（budget が null）には、何回流れた段でも「N 回目」が出ない', () => {
  // 要件定義を 3 回流した記録の節。対照：budget があれば「3 回目」が出る
  const base = budgetView([1, 2, 3].map((seq) => budgetRun({ stage: 'requirements', seq, costUsd: 0.1 }))).nodes;
  assert.match(nodeG(svgOf(withBudgets(base, { requirements: budgetFor('ok', 0.1, 1.0, 3, 3) })), 'requirements'), /3 回目/, '対照');
  assert.doesNotMatch(nodeG(svgOf(withBudgets(base, { requirements: null })), 'requirements'), /\d+ 回目/);
});

test('D0051-AC-52: 言葉だけの節（割合の無い止まった）も、2 回以上流れた段なら「N 回目」が出る', () => {
  const g = nodeG(svgOf(withBudgets(doneNodes(), { requirements: wordOnly(3, 3) })), 'requirements');
  assert.ok(textsOf(g).some((t) => t.includes('3 回目')), `文字: ${textsOf(g).join(' | ')}`);
  assert.ok(titleOf(g).includes('3 回目'));
});

// ======== AC-53：選んだ回の値だけが出て、2 行目は全部の回の合計のまま ========

test('D0051-AC-53: 1回目 0.90 / 1.00・2回目 0.40 / 1.00 の段は、1回目の値（$0.90 / $1.00・上限に近い・1 回目）が出て、2回目の $0.40 / $1.00 は出ない。2 行目は合計のまま（$1.300）', () => {
  const view = budgetView([
    budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.9, maxBudgetUsd: 1.0 }),
    budgetRun({ stage: 'requirements', seq: 2, costUsd: 0.4, maxBudgetUsd: 1.0 }),
  ]);
  const g = nodeG(svgOf(view.nodes), 'requirements');
  assert.ok(g.includes('$0.90 / $1.00'), '選んだ回の金額の対');
  assert.ok(g.includes(WORD_NEAR));
  assert.ok(textsOf(g).some((t) => t.includes('1 回目')));
  assert.ok(!g.includes('$0.40 / $1.00'), '別の回の金額の対は出ない');
  assert.ok(textsOf(g).some((t) => t.startsWith('2 ターン・$1.300')), `2 行目は全部の回の合計: ${textsOf(g).join(' | ')}`);
});

// ======== AC-54：上限が記録に無い「止まった」は言葉だけ ========

test('D0051-AC-54: 上限が記録に無い「止まった」の節は、「上限で止まった」の言葉だけを出し、金額の対も棒も出さない', () => {
  const view = budgetView([budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.4, subtype: STOP, isError: true })]);
  const g = nodeG(svgOf(view.nodes), 'requirements');
  assert.ok(textsOf(g).some((t) => t === WORD_STOPPED), `言葉: ${textsOf(g).join(' | ')}`);
  assert.ok(classesOf(g).includes('is-budget-stopped'));
  assert.equal(PAIR.test(g), false, '金額の対は出ない');
  assert.ok(!g.includes('budget-fill') && !g.includes('budget-track'), '棒は出ない');
  assert.doesNotMatch(g, /\d+ 回目/, '1 回だけの段には「N 回目」を出さない');
});

test('D0051-AC-54: 上限が記録に無い「止まった」の節も、2 回以上流れた段なら「N 回目」を出す（2回目で止まった記録）', () => {
  const view = budgetView([
    budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.2 }),
    budgetRun({ stage: 'requirements', seq: 2, costUsd: 0.4, subtype: STOP, isError: true }),
  ]);
  const g = nodeG(svgOf(view.nodes), 'requirements');
  assert.ok(g.includes(WORD_STOPPED));
  assert.ok(textsOf(g).some((t) => t.includes('2 回目')), `文字: ${textsOf(g).join(' | ')}`);
  assert.equal(PAIR.test(g), false);
  assert.ok(!g.includes('budget-fill'));
});

// ======== AC-55：続きの会話の回で止まった節は言葉だけ ========

test('D0051-AC-55: 続きの会話の印のある回で止まった節は「上限で止まった」の言葉だけを出す。その回の費用（0.9）の金額の対も棒も出ない', () => {
  const view = budgetView([budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.9, maxBudgetUsd: 1.0, resumed: true, subtype: STOP, isError: true })]);
  const g = nodeG(svgOf(view.nodes), 'requirements');
  assert.ok(textsOf(g).some((t) => t === WORD_STOPPED), `言葉: ${textsOf(g).join(' | ')}`);
  assert.equal(PAIR.test(g), false, '金額の対は出ない');
  assert.ok(!g.includes('$0.90 /'), '0.9 の金額の対は出ない');
  assert.ok(!g.includes('budget-fill') && !g.includes('budget-track'), '棒は出ない');
  assert.ok(textsOf(g).some((t) => t.startsWith('1 ターン・$0.900')), '2 行目は今までどおり');
});

test('D0051-AC-55: 続きの会話の回で止まった節も、2 回以上流れた段なら「N 回目」を出す', () => {
  const view = budgetView([
    budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.4, maxBudgetUsd: 1.0 }),
    budgetRun({ stage: 'requirements', seq: 2, costUsd: 0.9, maxBudgetUsd: 1.0, resumed: true, subtype: STOP, isError: true }),
  ]);
  const g = nodeG(svgOf(view.nodes), 'requirements');
  assert.ok(g.includes(WORD_STOPPED));
  assert.ok(textsOf(g).some((t) => t.includes('2 回目')));
  assert.equal(PAIR.test(g), false);
});

// ======== AC-56：状態を持たない節は今までと同じ ========

/** 上限のある節・無い節・続きの会話の節・動いている節が混ざる記録。 */
const MIXED = [
  budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.9, maxBudgetUsd: 1.0 }), // 近い
  budgetRun({ stage: 'design', seq: 2, costUsd: 0.4 }), // 上限なし
  budgetRun({ stage: 'red', seq: 3, costUsd: 1.2, maxBudgetUsd: 1.0, resumed: true }), // 続きの会話で止まっていない
  budgetRun({ stage: 'implement', seq: 4, attempt: 1, costUsd: 0.2, maxBudgetUsd: 1.0 }), // 余裕
];
const MIXED_LOGS = [runningLogFile(5, 'test', 1)]; // 検証が動いている
const mixedView = (strip: boolean): PipelineView =>
  budgetView(strip ? MIXED.map(withoutBudgetKeys) : MIXED, { stageLogs: MIXED_LOGS, clock: clockAt(100) });
/** 縦の位置（y="…"。判定の節の菱形は path の d="…"）の数字を除く（前の節が高くなった分のずれは比べない）。 */
const withoutY = (g: string): string => g.replace(/\sy="[^"]*"/g, ' y="Y"').replace(/\sd="[^"]*"/g, ' d="D"');

test('D0051-AC-56: 状態を持たない節の <g> は、状態を持つ節を並べても、縦の位置を除いて、上限・印・subtype を除いた同じ記録のものと同じ。今のまま通る。守る', () => {
  const withKeys = mixedView(false);
  const without = mixedView(true);
  assert.equal(withKeys.runningStage, 'test', '前提：検証が動いている');
  const svgWith = svgOf(withKeys.nodes);
  const svgWithout = svgOf(without.nodes);
  const plainIds = withKeys.nodes.filter((n) => budgetOfNode(n) == null).map((n) => n.id);
  assert.ok(plainIds.includes('design') && plainIds.includes('red') && plainIds.includes('test'), `状態を持たない節: ${plainIds.join(',')}`);
  for (const id of plainIds) assert.equal(withoutY(nodeG(svgWith, id)), withoutY(nodeG(svgWithout, id)), `節 ${id}`);
});

test('D0051-AC-56: （対照）状態を持つ節（要件定義・実装）の <g> は、上限・印・subtype を除いた同じ記録のものと違う（表示が足されている）', () => {
  const svgWith = svgOf(mixedView(false).nodes);
  const svgWithout = svgOf(mixedView(true).nodes);
  for (const id of ['requirements', 'implement']) assert.notEqual(withoutY(nodeG(svgWith, id)), withoutY(nodeG(svgWithout, id)), `節 ${id}`);
});

// ======== AC-57：高さ ========

interface Shape {
  y: number;
  h: number;
  w: number;
}
const shapesOf = (svg: string): Shape[] =>
  [...svg.matchAll(/<rect\b[^>]*\sclass="shape[^"]*"[^>]*>/g)].map((m) => ({ y: Number(attrOf(m[0], 'y')), h: Number(attrOf(m[0], 'height')), w: Number(attrOf(m[0], 'width')) }));
const edgesOf = (svg: string): { y1: number; y2: number }[] =>
  [...svg.matchAll(/<line\b[^>]*\sclass="edge[^"]*"[^>]*>/g)].map((m) => ({ y1: Number(attrOf(m[0], 'y1')), y2: Number(attrOf(m[0], 'y2')) }));
const viewBoxHeight = (svg: string): number => Number(/viewBox="0 0 \d+ (\d+)"/.exec(svg)?.[1]);

/** パイプの 4 つの段 a・b・c・d が終わった図の節（依頼メモ → a → b → c → d → 完了。確認と判定は無い）。 */
function pipeNodes(): PipelineNode[] {
  const runs = ['a', 'b', 'c', 'd'].map((stage, i) => budgetRun({ stage, seq: i + 1, costUsd: 0.5 }));
  return budgetView(runs, { pipe: 'p', stages: pipeStages(['a', 'b', 'c', 'd']) }).nodes;
}
/** a：言葉つき（近い）・b：金額の対と棒だけ（余裕）・c：言葉だけ（割合の無い止まった）・d：表示なし。 */
const shownPipe = (): PipelineNode[] =>
  withBudgets(pipeNodes(), { a: budgetFor('near', 0.9, 1.0), b: budgetFor('ok', 0.2, 1.0), c: wordOnly(), d: null });

test('D0051-AC-57: 金額の対・棒・言葉のどれも出さない節の高さは 50、幅は 176 のまま（表示のある節が前にあっても）', () => {
  const shapes = shapesOf(svgOf(shownPipe()));
  assert.equal(shapes.length, 6, '前提：依頼メモ・4 つの段・完了');
  assert.ok(shapes[1]!.h > 50, '対照：言葉つきの節（a）は 50 より高い');
  const d = shapes[4]!;
  assert.equal(d.h, 50);
  assert.equal(d.w, NODE_WIDTH);
});

test('D0051-AC-57: 表示を出す節は高くなる：言葉だけ（c）< 金額の対と棒だけ（b）< 金額の対と棒と言葉（a）。幅は 176 のまま', () => {
  const [, a, b, c] = shapesOf(svgOf(shownPipe()));
  assert.ok(c!.h > 50, `言葉だけの節は 50 より高い（${c!.h}）`);
  assert.ok(b!.h > c!.h, `金額の対と棒は言葉だけより高い（${b!.h} と ${c!.h}）`);
  assert.ok(a!.h > b!.h, `さらに言葉を足すと高い（${a!.h} と ${b!.h}）`);
  for (const s of [a!, b!, c!]) assert.equal(s.w, NODE_WIDTH);
});

test('D0051-AC-57: 後ろの節と矢印は、増えた分だけ下にずれる：節のあいだの間隔と、矢印の始まり・終わりは変わらない', () => {
  const base = svgOf(pipeNodes());
  const withShown = svgOf(shownPipe());
  const before = shapesOf(base);
  const after = shapesOf(withShown);
  assert.equal(after.length, before.length);
  const gap = before[1]!.y - (before[0]!.y + before[0]!.h);
  after.forEach((s, i) => {
    if (i === 0) return;
    assert.equal(s.y, after[i - 1]!.y + after[i - 1]!.h + gap, `${i} 番目の節の上端は、前の節の下端から間隔 ${gap}`);
  });
  const edges = edgesOf(withShown);
  assert.equal(edges.length, after.length - 1);
  edges.forEach((e, i) => {
    assert.equal(e.y1, after[i]!.y + after[i]!.h, `${i + 1} 本目の矢印の始まりは前の節の下端`);
    assert.equal(e.y2, after[i + 1]!.y - 2, `${i + 1} 本目の矢印の終わりは次の節の上端の手前`);
  });
  assert.ok(after[5]!.y > before[5]!.y, '完了の節は増えた分だけ下にずれる');
});

test('D0051-AC-57: viewBox の高さは、節が高くなった分（合計）だけ増える', () => {
  const base = svgOf(pipeNodes());
  const withShown = svgOf(shownPipe());
  const grown = shapesOf(withShown).reduce((sum, s, i) => sum + (s.h - shapesOf(base)[i]!.h), 0);
  assert.ok(grown > 0, `節が高くなっている（増えた合計 ${grown}）`);
  assert.equal(viewBoxHeight(withShown) - viewBoxHeight(base), grown);
});

test('D0051-AC-57: 表示を出さない節（budget が null）ばかりの図は、高さも viewBox も今までと同じ。今のまま通る。守る', () => {
  const nodes = pipeNodes();
  const none = withBudgets(nodes, { a: null, b: null, c: null, d: null });
  assert.equal(svgOf(none), svgOf(nodes));
  assert.ok(shapesOf(svgOf(nodes)).slice(1, 5).every((s) => s.h === 50));
});

// ======== AC-58：動いている段の節には出さない ========

test('D0051-AC-58: 動いている段の節には金額の対も棒も言葉も出ない（経過のまま）。動いていない並列の段は、前の回の状態で出る', () => {
  const runs = [
    budgetRun({ stage: 'a', seq: 1, costUsd: 0.9, maxBudgetUsd: 1.0 }),
    budgetRun({ stage: 'b', seq: 2, costUsd: 0.9, maxBudgetUsd: 1.0 }),
  ];
  const view = budgetView(runs, {
    pipe: 'p',
    stages: pipeStages(['a', 'b']),
    stageLogs: [runningLogFile(3, 'a', 2), runningLogFile(4, 'b', 2)],
    clock: clockAt(100),
  });
  assert.equal(view.runningStage, 'b', '前提：並列の段のうち動いていると判定されるのは 1 つ（b）');
  const svg = svgOf(view.nodes);
  const running = nodeG(svg, 'b');
  assert.ok(running.includes('経過'), 'b は経過のまま');
  assert.equal(shown(running), false, '動いている b に金額の対・棒・言葉は出ない');
  assert.equal(hasBudgetClass(running), false);
  const idle = nodeG(svg, 'a');
  assert.ok(idle.includes('$0.90 / $1.00'), '動いていないと判定された a は、前の回の金額の対で出る');
  assert.ok(idle.includes(WORD_NEAR));
});

// ======== AC-59：/pipe-in の記録は今までと同じ ========

for (const name of ['finished', 'running', 'waiting']) {
  test(`D0051-AC-59: /pipe-in の記録（pipe_dev/${name}。driver があり、費用 0・ターン 0）の図は、全部の節の budget が null で、SVG に is-budget- が無い`, () => {
    const view = buildPipelineView(fixtureSnapshot('pipe_dev', name), clockAt(100));
    assert.deepEqual(view.nodes.filter((n) => budgetOfNode(n) !== null).map((n) => n.id), [], 'budget が null でない節');
    assert.doesNotMatch(renderFlowSvg(view.nodes, new Set(reasonNodeIds(view)), null), /is-budget-/);
  });
}

// ======== AC-60：外から来た値は HTML にそのまま出ない ========

test('D0051-AC-60: 上限・subtype に <script> や数でない値が入っていても、SVG にそのまま出ない（上限は数として読み、言葉は固定の文だけ）', () => {
  const view = budgetView([
    budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.3, maxBudgetUsd: '<script>alert(1)</script>', subtype: '<img src=x onerror=alert(1)>' }),
    budgetRun({ stage: 'requirements', seq: 2, costUsd: 0.9, maxBudgetUsd: 1.0, subtype: '<script>alert(2)</script>' }),
    budgetRun({ stage: 'design', seq: 3, costUsd: 0.4, maxBudgetUsd: { x: '<b>' }, subtype: { y: '<i>' } }),
    budgetRun({ stage: 'red', seq: 4, costUsd: 0.4, maxBudgetUsd: ['<u>'], subtype: 12345, resumed: '<s>' }),
  ]);
  const svg = svgOf(view.nodes);
  assert.ok(nodeG(svg, 'requirements').includes('$0.90 / $1.00'), '対照：数として読める上限は出る');
  assert.doesNotMatch(svg, /<script|<img|<b>|<i>|<u>|<s>|onerror/i);
  assert.doesNotMatch(renderViewBody(view), /<script|<img|<b>|<i>|<u>|<s>|onerror/i, 'ページ全体（使用量のパネルの費用の表も）にも出ない');
  assert.equal(hasBudgetClass(nodeG(svg, 'design')), false, '数でない上限だけの節は状態を持たない');
});

test('D0051-AC-60: 数でない上限の実行が subtype だけで止まった節は、固定の言葉（上限で止まった）だけを出し、記録の文字は出ない', () => {
  const view = budgetView([budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.4, maxBudgetUsd: '<img src=x onerror=alert(1)>', subtype: STOP, isError: true })]);
  const g = nodeG(svgOf(view.nodes), 'requirements');
  assert.ok(g.includes(WORD_STOPPED));
  assert.doesNotMatch(g, /<img|onerror/);
  assert.equal(PAIR.test(g), false);
});

// ======== AC-61：style 属性・外部の読み込み・直書きの色が無い ========

/** 4 つの状態と言葉だけの節・「N 回目」を全部並べた図。 */
const ALL_STATES = (): PipelineNode[] =>
  withBudgets(
    budgetView(['a', 'b', 'c', 'd', 'e'].map((stage, i) => budgetRun({ stage, seq: i + 1, costUsd: 0.5 })), { pipe: 'p', stages: pipeStages(['a', 'b', 'c', 'd', 'e']) }).nodes,
    { a: budgetFor('ok', 0.2, 1.0), b: budgetFor('near', 0.9, 1.0, 2, 2), c: budgetFor('over', 1.2, 1.0), d: budgetFor('stopped', 1.02, 1.0), e: wordOnly(2, 3) },
  );

test('D0051-AC-61: SVG に style 属性が無く、外部の読み込みが無く、色の直書きが無い（4 つの状態・言葉だけの節・「N 回目」を並べても）', () => {
  const svg = svgOf(ALL_STATES());
  assert.ok(svg.includes('budget-fill') && svg.includes(WORD_STOPPED), '対照：上限の表示が描かれている');
  assert.doesNotMatch(svg, /\sstyle=/);
  assert.doesNotMatch(svg, /\s(?:href|src|xlink:href)=|<image\b|<foreignObject\b|<script\b|<link\b|@import|url\((?!#)/i);
  assert.doesNotMatch(svg, /\s(?:fill|stroke|color|stop-color)="(?!none"|currentColor"|url\(#|var\(--vscode-)/, '色の属性を直書きしない（var(--vscode-*) は許す）');
  assert.doesNotMatch(svg, /#[0-9a-f]{3,8}\b(?!\))|rgba?\(|hsla?\(/i, '色の値（#rrggbb・rgb(）を直書きしない');
});

test('D0051-AC-61: 上限の表示の CSS（budget を含む規則）の色は var(--vscode-*) だけ。規則は budget-fill・budget-track・budget-word と 3 つの状態にある', () => {
  const rules = parseCss(extractCss(renderPanelHtml(budgetView([budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.5 })]), 'N'))).filter((r) => r.selector.includes('budget'));
  for (const part of ['.budget-fill', '.budget-track', '.budget-word', '.is-budget-near', '.is-budget-over', '.is-budget-stopped']) {
    assert.ok(rules.some((r) => r.selector.includes(part)), `${part} の規則がある`);
  }
  const colored = rules.flatMap((r) => [...r.body.matchAll(/(?:^|;)\s*(?:fill|stroke|color|background|background-color)\s*:\s*([^;]+)/g)].map((m) => `${r.selector} { ${m[1]!.trim()} }`));
  assert.ok(colored.length > 0, '色を決める宣言がある');
  assert.deepEqual(colored.filter((c) => !/\{\s*var\(--vscode-[\w-]+/.test(c)), [], 'var(--vscode-*) でない色');
});
