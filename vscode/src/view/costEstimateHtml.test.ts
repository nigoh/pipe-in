// 作業台の「費用の目安」の節の HTML（D0066）：view/costEstimateHtml.ts。純粋な関数（外から来た文字は escapeHtml を通し、style 属性を書かない）。
// 新しい部品（view/costEstimateHtml.ts・domain/costEstimate.ts）は、呼んだところで落ちるように、テストの中で読み込む。
// 部品の形（このファイルが決める。実装はこれに合わせる）：
//   costEstimateHtml(est: CostEstimate, actualUsd: number | null): string
//     <details class="box" id="cost-estimate"> … </details>。見出し行に「費用の目安」と幅、中に段ごとの内訳・前の実績（あるときだけ）・印・DISCLAIMER。
//   est は domain/costEstimate.ts の estimateCost の返す値。ドルは「$」+ 小数 2〜4 桁（units / 10000）。
import { test } from 'node:test';
import assert from 'node:assert/strict';

type StageIn = { name: string; model: unknown; maxTurns: unknown; maxBudget: number | null; maxRetries: number };
interface Est {
  stages: { name: string; low: number; high: number; marks: string[] }[];
  low: number;
  high: number;
  stale: boolean;
}

async function load(): Promise<{ html: (e: Est, actual: number | null) => string; estimate: (s: StageIn[], today: string | null) => Est; disclaimer: string }> {
  try {
    const ce = (await import('../domain/costEstimate.ts')) as unknown as { estimateCost(s: StageIn[], t: string | null): Est; DISCLAIMER: string };
    const view = (await import('./costEstimateHtml.ts')) as unknown as { costEstimateHtml(e: Est, a: number | null): string };
    return { html: view.costEstimateHtml, estimate: ce.estimateCost, disclaimer: ce.DISCLAIMER };
  } catch (e) {
    return assert.fail(`domain/costEstimate.ts か view/costEstimateHtml.ts が無い（まだ作っていない）: ${String(e)}`);
  }
}

const stage = (p: Partial<StageIn> = {}): StageIn => ({ name: 'draw', model: 'sonnet', maxTurns: 10, maxBudget: null, maxRetries: 0, ...p });
const TODAY = '2026-11-02';
const dollars = (units: number): string[] => [2, 3, 4].map((n) => `$${(units / 10000).toFixed(n)}`);
const hasDollars = (html: string, units: number): boolean => dollars(units).some((d) => html.includes(d));

test('D0066-AC-20: 節は閉じられる details（id="cost-estimate"）で、見出し行に「費用の目安」と幅、中に段ごとの内訳と FR-09 の文がある', async () => {
  const { html, estimate, disclaimer } = await load();
  const est = estimate([stage({ name: 'draw' }), stage({ name: 'verify', maxTurns: 40 })], TODAY);
  const out = html(est, null);
  assert.match(out, /<details[^>]*\bid="cost-estimate"/);
  assert.ok(out.includes('費用の目安'));
  assert.ok(out.includes('draw') && out.includes('verify'));
  assert.ok(hasDollars(out, est.low), '全体の少なめ');
  assert.ok(hasDollars(out, est.high), '全体の多め');
  assert.ok(hasDollars(out, est.stages[1]!.high), '段ごとの多め');
  assert.ok(out.includes(disclaimer), 'FR-09 の文が全文で付く');
});

test('D0066-AC-22: 前の実績は、あるときだけ出る（実績ありは「前の実績」と金額、null は欄ごと無い）', async () => {
  const { html, estimate } = await load();
  const est = estimate([stage()], TODAY);
  const withActual = html(est, 1.23);
  assert.ok(withActual.includes('前の実績') && withActual.includes('$1.23'), withActual);
  const without = html(est, null);
  assert.ok(!without.includes('前の実績') && !without.includes('実績'), '実績が無いときは、その欄を出さない');
  assert.ok(html(est, 0).includes('前の実績'), '0 ドルの実績も実績（欄は出る）');
});

test('D0066-AC-23: 印は該当するときだけ HTML に出る（単価表が古い・モデル不明（sonnet として計算）・ターン上限が読めない）', async () => {
  const { html, estimate } = await load();
  const clean = html(estimate([stage()], TODAY), null);
  assert.ok(!clean.includes('単価表が古いかもしれません'));
  assert.ok(!clean.includes('モデル不明'));
  const old = html(estimate([stage()], '2099-01-01'), null);
  assert.ok(old.includes('単価表が古いかもしれません'));
  assert.ok(!old.includes('モデル不明'));
  const unknown = html(estimate([stage({ model: '' })], TODAY), null);
  assert.ok(unknown.includes('モデル不明（sonnet として計算）'));
  assert.ok(!unknown.includes('単価表が古いかもしれません'));
  const invalid = html(estimate([stage({ maxTurns: 0 })], TODAY), null);
  assert.notEqual(invalid, clean, 'ターン上限が読めない印は、出す');
  assert.ok(!invalid.includes('モデル不明') && !invalid.includes('単価表が古いかもしれません'));
});

test('D0066-AC-24: <script> を含む段の名前・モデルの名前は escapeHtml を通る（そのまま HTML にならない）', async () => {
  const { html, estimate } = await load();
  const evil = '<script>x</script>';
  const out = html(estimate([stage({ name: evil, model: '<img src=x onerror=1>' }), stage({ name: 'a"b&c' })], TODAY), null);
  assert.ok(!out.includes('<script>'), '段の名前がそのまま入っている');
  assert.ok(!out.includes('<img'), 'モデルの名前がそのまま入っている');
  assert.ok(out.includes('&lt;script&gt;x&lt;/script&gt;'), 'エスケープした名前が出る');
  assert.ok(out.includes('a&quot;b&amp;c'));
});

test('D0066-AC-24: 節の HTML に style 属性を書かない（CSP がインラインの style を捨てる。幅や色はクラス）', async () => {
  const { html, estimate } = await load();
  const out = html(estimate([stage({ model: '' }), stage({ maxTurns: 0 })], '2099-01-01'), 2.5);
  assert.doesNotMatch(out, /\sstyle=/);
  assert.doesNotMatch(out, /<script|<link|<img|https?:\/\//, '外部から何も読み込まず、スクリプトも持たない');
});
