// 使用量のパネルの「段ごとの費用」の節（D0051 の AC-62・63・66〜69）：段ごとの費用を、費用の多い順に並べた表。
// 節は <section class="stage-costs" data-stage-costs>。探すのは data-stage-costs の印で、タブの数・位置の添字は使わない（別の PR が足すタブと取り違えないため）。
// 表の中身の見方：<tr> ごとに <td>・<th> の文字を取る（見出しの行は <td> を持たない行）。合計の行は最初の文字が「合計」の行。
// 赤の理由は「まだ節が無い」：空の形の renderStageCosts は空の文字を返し、パネルにも足されていない。
// 期待が「出ない」のテスト（AC-67）は、空の形の出力と区別できないので、費用があれば節が出る対照を先に確かめる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderViewBody } from './panelHtml.ts';
import { renderStageCosts } from './usageHtml.ts';
import type { StageCostsView } from '../domain/stageCosts.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { STAGES } from '../domain/stage.ts';
import type { CostTable } from '../test/budgetFixtures.ts';
import { budgetRun, budgetView, costTableOf, pipeStages, stageCostsSection, stripStageCosts, usagePanelOf } from '../test/budgetFixtures.ts';
import { clockAt, fixtureSnapshot } from '../test/liveFixtures.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { usageSummaryDict } from '../test/fixtures.ts';

// ---- ページの文字の読み方（test/budgetFixtures.ts：usagePanelOf・stageCostsSection・costTableOf） ----

const usagePanel = usagePanelOf;
const sectionOf = stageCostsSection;
const tableOf = costTableOf;
type Table = CostTable;
const count = (text: string, needle: string): number => text.split(needle).length - 1;
const stageCostsOf = (view: PipelineView): StageCostsView | null | undefined => (view as unknown as { stageCosts?: StageCostsView | null }).stageCosts;

/** 要件定義 0.4・設計 0.6 の開発フローの記録（合計 $1.00）。 */
const TWO_STAGES = [budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.4 }), budgetRun({ stage: 'design', seq: 2, costUsd: 0.6 })];
const tableFor = (runs: readonly object[]): Table => {
  const section = sectionOf(renderViewBody(budgetView(runs)));
  assert.ok(section !== null, '「段ごとの費用」の節が出ている');
  return tableOf(section);
};

// ======== AC-62：実行の詳細に「段ごとの費用」の表が 1 つ出る ========

test('D0051-AC-62: 使用量のパネルに data-stage-costs の節が 1 つ出る（ページ全体で 1 つ。使用量のパネルの枠の中にある）', () => {
  const html = renderViewBody(budgetView(TWO_STAGES));
  assert.equal(count(html, 'data-stage-costs'), 1, 'ページ全体で 1 つ');
  assert.equal(count(usagePanel(html), 'data-stage-costs'), 1, '使用量のパネルの中にある');
  assert.ok(sectionOf(usagePanel(html)) !== null);
});

test('D0051-AC-62: 節の見出しは「段ごとの費用」で、使用量の節の上にある。見出しに「使用量」の語は入れない', () => {
  const view = budgetView(TWO_STAGES, { usageSummary: usageSummaryDict() });
  const panel = usagePanel(renderViewBody(view));
  const section = sectionOf(panel);
  assert.ok(section !== null, '節が出ている');
  assert.ok(section.includes('段ごとの費用'));
  assert.ok(!section.includes('使用量'), '節の中に「使用量」の語を入れない');
  assert.ok(panel.indexOf('data-stage-costs') < panel.indexOf('使用量'), '使用量の節より上');
});

test('D0051-AC-62: 節の中に別の <section> を入れない（既存の使用量のパネルの SHA-256 の検査が、節を取り除いて測るため）', () => {
  const section = sectionOf(renderViewBody(budgetView(TWO_STAGES)));
  assert.ok(section !== null, '節が出ている');
  assert.equal(count(section, '<section'), 1);
});

test('D0051-AC-62: 費用の節を取り除くと、費用の節が無いときと同じ文字になる（費用の節の外は何も変わらない）。今のまま通る。守る', () => {
  const view = budgetView(TWO_STAGES, { usageSummary: usageSummaryDict() });
  const withTable = renderViewBody(view);
  const without = renderViewBody({ ...view, stageCosts: null } as unknown as PipelineView);
  assert.equal(stripStageCosts(withTable), stripStageCosts(without));
  assert.equal(stripStageCosts(without), without, '節が無い版には取り除くものが無い');
});

test('D0051-AC-62: 検査そのもの：stripStageCosts は費用の節だけを取り除き、使用量の節（別の <section>）は残す。今のまま通る。守る', () => {
  const costs = '<section class="stage-costs" data-stage-costs><h2>段ごとの費用</h2><table><tr><td>a</td></tr></table></section>';
  const usage = '<section><h2 class="terminal-title">使用量</h2></section>';
  assert.equal(stripStageCosts(`<div>${costs}${usage}</div>`), `<div>${usage}</div>`);
  assert.equal(stripStageCosts(`<div>${usage}</div>`), `<div>${usage}</div>`);
});

// ======== AC-63：行は段ごと。同じ段の複数回は 1 行で、2 回以上なら「N 回」を添える。列は 段の名前・費用・割合 ========

test('D0051-AC-63: 行は 段の名前・費用・割合 の 3 つのセル（設計 $0.60 60%・要件定義 $0.40 40%）', () => {
  const table = tableFor(TWO_STAGES);
  assert.deepEqual(table.rows, [
    ['設計', '$0.60', '60%'],
    ['要件定義', '$0.40', '40%'],
  ]);
  assert.equal(table.head.length, 3, '見出しも 3 列');
});

test('D0051-AC-63: 同じ段の複数回は 1 行にまとめ、2 回以上なら「N 回」を添える（実装 3 回 → 「3 回」）。1 回の段には添えない', () => {
  const table = tableFor([
    budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.4 }),
    budgetRun({ stage: 'implement', seq: 2, attempt: 1, costUsd: 0.2 }),
    budgetRun({ stage: 'implement', seq: 3, attempt: 2, costUsd: 0.2 }),
    budgetRun({ stage: 'implement', seq: 4, attempt: 3, costUsd: 0.2 }),
  ]);
  assert.equal(table.rows.length, 2, '段ごとに 1 行');
  const implement = table.rows.find((r) => r[0]!.startsWith('実装'));
  const requirements = table.rows.find((r) => r[0]!.startsWith('要件定義'));
  assert.ok(implement !== undefined && requirements !== undefined);
  assert.match(implement[0]!, /3 回/);
  assert.equal(implement[1], '$0.60', '3 回の合計');
  assert.doesNotMatch(requirements[0]!, /\d+ 回/, '1 回の段には回数を添えない');
});

// ======== AC-66：合計の行は費用だけで、割合は出さない ========

test('D0051-AC-66: 合計の行は費用（$1.00）だけで、割合（%）は出さない', () => {
  const table = tableFor(TWO_STAGES);
  assert.ok(table.total !== null, '合計の行がある');
  assert.equal(table.total[1], '$1.00');
  assert.ok(!table.total.join('').includes('%'), `合計の行に割合が出ている: ${table.total.join(' | ')}`);
  assert.equal(table.rows.length, 2, '合計の行は段の行に数えない');
});

// ======== AC-67：金額の書き方は AC-46 と同じ。表が出ない記録では節そのものが出ない ========

test('D0051-AC-67: 金額は 1/1000 ドル単位に丸めた書き方（0.125 → $0.125・12.3456 → $12.346・0.004 → $0.004・0.42 → $0.42・1.0 → $1.00）', () => {
  const table = tableFor([
    budgetRun({ stage: 'requirements', seq: 1, costUsd: 0.125 }),
    budgetRun({ stage: 'design', seq: 2, costUsd: 12.3456 }),
    budgetRun({ stage: 'red', seq: 3, costUsd: 0.004 }),
    budgetRun({ stage: 'implement', seq: 4, costUsd: 0.42 }),
    budgetRun({ stage: 'test', seq: 5, costUsd: 1.0 }),
  ]);
  const costOf = (label: string): string | undefined => table.rows.find((r) => r[0]!.startsWith(label))?.[1];
  assert.equal(costOf('要件定義'), '$0.125');
  assert.equal(costOf('設計'), '$12.346');
  assert.equal(costOf('テスト先行'), '$0.004');
  assert.equal(costOf('実装'), '$0.42');
  assert.equal(costOf('検証'), '$1.00');
  assert.equal(table.total?.[1], '$13.895', '合計 13.8946 も同じ書き方');
});

test('D0051-AC-67: 費用が 0 の段は行に出ない（流れていない段・費用 0 の実行）', () => {
  const table = tableFor([budgetRun({ stage: 'requirements', seq: 1, costUsd: 0 }), budgetRun({ stage: 'design', seq: 2, costUsd: 0.5 })]);
  assert.deepEqual(
    table.rows.map((r) => r[0]),
    ['設計'],
  );
});

test('D0051-AC-67: 全部の段の費用が 0 の記録、実行の無い記録では、節そのものが出ない', () => {
  assert.equal(count(renderViewBody(budgetView(TWO_STAGES)), 'data-stage-costs'), 1, '対照：費用があれば節が出る');
  assert.equal(count(renderViewBody(budgetView([budgetRun({ stage: 'requirements', seq: 1, costUsd: 0 })])), 'data-stage-costs'), 0);
  assert.equal(count(renderViewBody(budgetView([])), 'data-stage-costs'), 0);
});

test('D0051-AC-67: /pipe-in の記録（費用 0・ターン 0）では、節そのものが出ない', () => {
  assert.equal(count(renderViewBody(budgetView(TWO_STAGES)), 'data-stage-costs'), 1, '対照：費用があれば節が出る');
  for (const name of ['finished', 'running', 'waiting']) {
    const view = buildPipelineView(fixtureSnapshot('pipe_dev', name), clockAt(100));
    assert.equal(count(renderViewBody(view), 'data-stage-costs'), 0, `pipe_dev/${name}`);
  }
});

test('D0051-AC-67: renderStageCosts は、値が null なら空の文字、値があれば data-stage-costs の節を返す', () => {
  const costs: StageCostsView = { rows: [{ stage: 'design', label: '設計', costUsd: 0.5, runs: 1, percent: 100 }], totalUsd: 0.5 };
  assert.equal(renderStageCosts(null), '');
  const html = renderStageCosts(costs);
  assert.ok(html.includes('data-stage-costs'), '値があれば節を返す');
  assert.ok(html.includes('設計') && html.includes('$0.50') && html.includes('100%'));
});

/** 独立に書いた集計：state.json の runs[] から、段ごとの費用・並び・割合を出す（部品を呼ばない）。 */
function aggregate(stateText: string): { label: string; runs: number; cost: string; percent: string }[] {
  const state = JSON.parse(stateText) as { stages: { name: string; label: string }[]; runs: Record<string, unknown>[] };
  const per = new Map<string, { sum: number; runs: number }>();
  for (const run of state.runs) {
    if (typeof run.seq !== 'number' || typeof run.stage !== 'string') continue;
    const cur = per.get(run.stage) ?? { sum: 0, runs: 0 };
    per.set(run.stage, { sum: cur.sum + (typeof run.cost_usd === 'number' ? run.cost_usd : 0), runs: cur.runs + 1 });
  }
  const rows = STAGES.map((stage, order) => ({ stage, order, units: Math.round((per.get(stage)?.sum ?? 0) * 1e4), runs: per.get(stage)?.runs ?? 0 })).filter((r) => r.units > 0);
  rows.sort((a, b) => b.units - a.units || a.order - b.order);
  const total = rows.reduce((s, r) => s + r.units, 0);
  const dollars = (usd: number): string => {
    const milli = Math.round(usd * 1000);
    if (milli > 10_000_000) return '$10000+';
    const fixed = (milli / 1000).toFixed(3);
    return `$${fixed.endsWith('0') ? fixed.slice(0, -1) : fixed}`;
  };
  return rows.map((r) => ({
    label: state.stages.find((s) => s.name === r.stage)?.label ?? r.stage,
    runs: r.runs,
    cost: dollars(r.units / 1e4),
    percent: `${Math.round((r.units * 100) / total)}%`,
  }));
}

test('D0051-AC-67: 見本の記録（showcase）の費用の表は、state.json の runs[] を別に集計した並び・費用・割合と同じ', () => {
  const snap = fixtureSnapshot('showcase');
  const expected = aggregate(snap.stateJson!);
  assert.equal(expected.length, 5, '前提：見本は 5 つの段に費用がある');
  const section = sectionOf(renderViewBody(buildPipelineView(snap, clockAt(100))));
  assert.ok(section !== null, '費用の節が出ている');
  const table = tableOf(section);
  assert.equal(table.rows.length, expected.length);
  expected.forEach((e, i) => {
    const row = table.rows[i]!;
    assert.ok(row[0]!.startsWith(e.label), `${i + 1} 行目の段の名前 ${row[0]} は ${e.label}`);
    if (e.runs >= 2) assert.match(row[0]!, new RegExp(`${e.runs} 回`), `${e.label} の回数`);
    else assert.doesNotMatch(row[0]!, /\d+ 回/, `${e.label} は 1 回`);
    assert.equal(row[1], e.cost, `${e.label} の費用`);
    assert.equal(row[2], e.percent, `${e.label} の割合`);
  });
});

// ======== AC-68：usage_summary の無い古い記録でも、runs[] の費用があれば表が出る ========

test('D0051-AC-68: usage_summary の無い記録（使用量の節が無い）でも、runs[] に費用があれば「段ごとの費用」の表が出る', () => {
  const view = budgetView(TWO_STAGES);
  assert.equal(view.usage, null, '前提：usage_summary が無い');
  const panel = usagePanel(renderViewBody(view));
  assert.ok(sectionOf(panel) !== null, '費用の表が出ている');
  assert.ok(!panel.includes('使用量'), '使用量の節は出ない（使用量の語が使用量のパネルに出ない今の決まりを守る）');
});

// ======== AC-69：段の名前は escapeHtml を通す ========

test('D0051-AC-69: 段の名前（表示の名前）が <img onerror=…> でも、生の HTML が出ない（文字として出る）', () => {
  const hostile = '<img src=x onerror=alert(1)>';
  const view = budgetView([budgetRun({ stage: 'a', seq: 1, costUsd: 0.5 }), budgetRun({ stage: 'b', seq: 2, costUsd: 0.2 })], {
    pipe: 'p',
    stages: [
      { name: 'a', label: hostile, output: 'a.md', review: false },
      { name: 'b', label: 'A&B "quote" \'q\'', output: 'b.md', review: false },
    ],
  });
  const section = sectionOf(renderViewBody(view));
  assert.ok(section !== null, '費用の節が出ている');
  assert.doesNotMatch(section, /<img/i);
  assert.ok(section.includes('&lt;img'), '文字として出ている');
  assert.ok(section.includes('A&amp;B'), '& も文字参照');
  assert.doesNotMatch(section, /<[^>]*\sonerror=/, '属性としては出ない（タグの中に onerror= が無い）');
});

test('D0051-AC-69: 段の名前の文字参照を戻した文字が、元の名前と同じ（表に出る名前は、記録の名前そのもの）', () => {
  const label = '<b>図</b> & "表"';
  const view = budgetView([budgetRun({ stage: 'a', seq: 1, costUsd: 0.5 })], {
    pipe: 'p',
    stages: [{ name: 'a', label, output: 'a.md', review: false }],
  });
  const section = sectionOf(renderViewBody(view));
  assert.ok(section !== null, '費用の節が出ている');
  assert.equal(tableOf(section).rows[0]?.[0], label);
});

test('D0051-AC-69: パイプの記録でも、段ごとの費用の表が出る（段の名前は record.stages の表示の名前）', () => {
  const view = budgetView([budgetRun({ stage: 'a', seq: 1, costUsd: 0.5 })], { pipe: 'p', stages: pipeStages(['a', 'b']) });
  assert.ok(stageCostsOf(view) !== null);
  const section = sectionOf(renderViewBody(view));
  assert.ok(section !== null, '費用の節が出ている');
  assert.deepEqual(tableOf(section).rows, [['a', '$0.50', '100%']]);
});
