// 確認用ページの素材のテスト（D0051 の AC-75・76・79・80 の画面の前の素材）：scripts/previewPages.ts と scripts/preview.ts が作る、上限と費用の表の見本のページ
// （run-panel-budget-light・-dark）と、見本の記録 scripts/budgetSamples.ts（budgetStateJson・fourStagesStateJson）。
// 画面そのもの（見た目・コントラスト・はみ出し・グレースケール・本物の VSCode）は Playwright か手で見る（手順は 03 に書く）。ここで確かめるのは、画面で見る前の素材：
// ページの一覧と種類・10 段の見本の中身・節の状態の数・使用量のパネルの費用の表の並び・一時フォルダ・CSP・手元の情報が出ないこと・preview.ts の呼び方。
// 見本の記録は一時フォルダの中にだけ書く。tests/fixtures/ には見本の記録を足さず、書かない（指紋で確かめる）。
// 新しい関数（buildBudgetDir・budgetPageHtml・budgetStateJson・fourStagesStateJson）と新しい出口（PANEL_PAGES の 2 件・panelKind の 'budget'）は、
// テスト先行のときに「まだ無い」で落ちるよう、動的 import で読んでから呼ぶ（空の形があるので、落ち方は「中身が無い」）。
// 確認用ページの HTML は bootPanel に渡さない（置き換えのスクリプトが先に拾われ、パネルのスクリプトが動かないため）。
// 「今のまま通る。守る」と書いたものは、今の作りで通り、実装のあとも通り続けることを見張る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { readFile, readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { PANEL_PAGES, SHOWCASE_DIR, THEMES, panelKind, panelPreviewHtml, readShowcaseView } from '../scripts/previewPages.ts';
import type { Theme } from '../scripts/previewPages.ts';
import { buildPipelineView, reasonNodeIds } from './domain/pipelineView.ts';
import type { NodeBudget } from './domain/stageBudget.ts';
import { renderFlowSvg } from './view/flowSvg.ts';
import { callArgs, withoutComments } from './test/sourceText.ts';
import { classesOf, costTableOf, loadBudgetTable, nodeG, stageCostsSection, textsOf, usagePanelOf } from './test/budgetFixtures.ts';
import { snapshot } from './test/fixtures.ts';
import { withTempDir } from './test/tempDir.ts';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const STOP = 'error_max_budget_usd';
const THEME_NAMES: Theme[] = ['light', 'dark'];

// tests/test_rules.py の LOCAL_INFO と同じ4つの書き方（ユーザー名の入ったパス・メールアドレス）
const LOCAL_INFO: RegExp[] = [
  /[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_.-]/,
  /(?<![A-Za-z0-9_.-])\/Users\/[A-Za-z0-9_.-]/,
  /(?<![A-Za-z0-9_.-])\/home\/[A-Za-z0-9_.-]/,
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+/,
];

// ---- 新しい部品を動的 import で読む ----

type Pages = Record<string, any>;
const loadPages = async (): Promise<Pages> => (await import('../scripts/previewPages.ts')) as unknown as Pages;
const loadSamples = async (): Promise<Pages> => (await import('../scripts/budgetSamples.ts')) as unknown as Pages;
function need(mod: Pages, file: string, name: string): (...args: any[]) => any {
  assert.equal(typeof mod[name], 'function', `scripts/${file} に ${name} が無い（export されていない）`);
  return mod[name] as (...args: any[]) => any;
}
const needPage = (pages: Pages, name: string): ((...args: any[]) => any) => need(pages, 'previewPages.ts', name);
const needSample = (samples: Pages, name: string): ((...args: any[]) => any) => need(samples, 'budgetSamples.ts', name);

// ---- 見本の記録の中身（設計の第 1.5 節） ----

interface RunSpec {
  cost: number;
  limit: number | null;
  subtype?: string;
  resumed?: boolean;
  isError?: boolean;
}
interface StageSpec {
  /** 節の状態（budget.state）。状態を持たない節は null */
  state: 'ok' | 'near' | 'over' | 'stopped' | null;
  runs: RunSpec[];
  /** 節に出る金額の対（無ければ null） */
  pair: string | null;
  /** 節に出る言葉（無ければ null） */
  word: string | null;
  /** 節に出る「N 回目」（無ければ null） */
  nth: number | null;
}
const WORD = { near: '上限に近い', over: '上限を超えた', stopped: '上限で止まった' } as const;
const SAMPLE: Readonly<Record<string, StageSpec>> = {
  'bd-ok': { state: 'ok', runs: [{ cost: 0.2, limit: 1 }], pair: '$0.20 / $1.00', word: null, nth: null },
  'bd-near': { state: 'near', runs: [{ cost: 0.9, limit: 1 }], pair: '$0.90 / $1.00', word: WORD.near, nth: null },
  'bd-over': { state: 'over', runs: [{ cost: 1.2, limit: 1 }], pair: '$1.20 / $1.00', word: WORD.over, nth: null },
  'bd-stopped': { state: 'stopped', runs: [{ cost: 1.02, limit: 1, subtype: STOP, isError: true }], pair: '$1.02 / $1.00', word: WORD.stopped, nth: null },
  'bd-nolimit': { state: null, runs: [{ cost: 0.35, limit: null }], pair: null, word: null, nth: null },
  'bd-nolimit-stopped': { state: 'stopped', runs: [{ cost: 0.4, limit: null, subtype: STOP }], pair: null, word: WORD.stopped, nth: null },
  'bd-resumed-ok': { state: null, runs: [{ cost: 0.9, limit: 1, resumed: true }], pair: null, word: null, nth: null },
  'bd-resumed-stopped': { state: 'stopped', runs: [{ cost: 0.9, limit: 1, resumed: true, subtype: STOP }], pair: null, word: WORD.stopped, nth: null },
  'bd-multi': {
    state: 'near',
    runs: [
      { cost: 0.9, limit: 1 },
      { cost: 0.4, limit: 1 },
    ],
    pair: '$0.90 / $1.00',
    word: WORD.near,
    nth: 1,
  },
  'bd-maxpair': {
    state: 'stopped',
    runs: [
      { cost: 0.5, limit: 10000 },
      { cost: 9999.999, limit: 10000, subtype: STOP },
    ],
    pair: '$9999.999 / $10000.00',
    word: WORD.stopped,
    nth: 2,
  },
};
const SAMPLE_NAMES = Object.keys(SAMPLE);
/** AC-80 の手で作る記録：4 つの段（余裕・近い・超えた・止まった）。 */
const FOUR = ['bd-ok', 'bd-near', 'bd-over', 'bd-stopped'] as const;

interface RawState {
  pipe?: unknown;
  final?: unknown;
  stages: { name: string; label: string }[];
  runs: Record<string, unknown>[];
}
const parseState = (text: string): RawState => JSON.parse(text) as RawState;
/** 見本の記録の文字（空の形は空の文字を返すので、中身が無いことを先に伝える）。 */
async function sampleText(name: 'budgetStateJson' | 'fourStagesStateJson'): Promise<string> {
  const text = needSample(await loadSamples(), name)() as string;
  assert.ok(text.length > 0, `${name}() の中身が空（見本の記録がまだ無い）`);
  return text;
}
const sampleState = async (name: 'budgetStateJson' | 'fourStagesStateJson'): Promise<RawState> => parseState(await sampleText(name));
/** state.json の runs[] の段の実行（seq を持つ要素）を、段ごとに出る順で。 */
function runsByStage(state: RawState): Map<string, Record<string, unknown>[]> {
  const out = new Map<string, Record<string, unknown>[]>();
  for (const run of state.runs) {
    if (typeof run.seq !== 'number' || typeof run.stage !== 'string') continue;
    out.set(run.stage, [...(out.get(run.stage) ?? []), run]);
  }
  return out;
}
const stateView = (text: string) => buildPipelineView(snapshot({ stateJson: text, artifacts: { '00_input.md': 'メモ' } }));
const budgetOfNode = (view: ReturnType<typeof stateView>, id: string): NodeBudget | null | undefined =>
  (view.nodes.find((n) => n.id === id) as unknown as { budget?: NodeBudget | null } | undefined)?.budget;

// ======== AC-75：PANEL_PAGES・panelKind ========

test('D0051-AC-75: PANEL_PAGES に run-panel-budget-light（明るい）・run-panel-budget-dark（暗い）の 2 件がある（名前の頭で選ぶ。添字は使わない）', () => {
  const budgetPages = PANEL_PAGES.filter(([name]) => name.startsWith('run-panel-budget-')).map(([name, theme]) => [name, theme]);
  assert.deepEqual(budgetPages, [
    ['run-panel-budget-light', 'light'],
    ['run-panel-budget-dark', 'dark'],
  ]);
});

test('D0051-AC-75: panelKind は run-panel-budget-light・run-panel-budget-dark に budget を返す', () => {
  assert.equal(panelKind('run-panel-budget-light'), 'budget');
  assert.equal(panelKind('run-panel-budget-dark'), 'budget');
});

test('D0051-AC-75: ほかのページの種類は変わらない（成果物・更新なし・一覧・今までのページ）。今のまま通る。守る', () => {
  const expected: Record<string, string> = {
    'run-panel-light': 'done',
    'run-panel-running-dark': 'running',
    'run-panel-waiting-light': 'waiting',
    'run-panel-runs-dark': 'runs',
    'run-panel-runs-omitted-dark': 'runs-omitted',
    'run-panel-stale-light': 'stale',
    'run-panel-stale-soon-dark': 'stale-soon',
    'run-panel-artifacts-light': 'artifacts',
    'run-panel-artifacts-dark': 'artifacts',
  };
  assert.deepEqual(Object.fromEntries(Object.keys(expected).map((name) => [name, panelKind(name)])), expected);
});

// ======== 見本の記録（budgetStateJson） ========

test('D0051-AC-75: budgetStateJson はパイプ budget-demo の記録で、段は 10 個（名前の頭は bd-）。最後は STAGE_ERROR（動いている段を出さない）', async () => {
  const state = await sampleState('budgetStateJson');
  assert.equal(state.pipe, 'budget-demo');
  assert.equal(state.final, 'STAGE_ERROR');
  assert.deepEqual(state.stages.map((s) => s.name).sort(), [...SAMPLE_NAMES].sort());
});

for (const [stage, spec] of Object.entries(SAMPLE)) {
  test(`D0051-AC-75: 見本の記録の ${stage} の実行は、設計のとおり（費用・上限・続きの会話の印・結果の種類）`, async () => {
    const state = await sampleState('budgetStateJson');
    const runs = runsByStage(state).get(stage) ?? [];
    assert.equal(runs.length, spec.runs.length, `${stage} の実行の数`);
    spec.runs.forEach((want, i) => {
      const got = runs[i]!;
      assert.equal(got.cost_usd, want.cost, `${stage} ${i + 1} 回目の費用`);
      if (want.limit === null) assert.ok(!('max_budget_usd' in got), `${stage} ${i + 1} 回目に max_budget_usd の鍵が無い（null も書かない）`);
      else assert.equal(got.max_budget_usd, want.limit, `${stage} ${i + 1} 回目の上限`);
      if (want.resumed === true) assert.equal(got.resumed, true);
      else assert.ok(!('resumed' in got), `${stage} ${i + 1} 回目に resumed の鍵が無い（偽も書かない）`);
      assert.equal(got.subtype, want.subtype ?? 'success');
      // is_error は、設計が決めているものだけ見る（bd-stopped は真・止まっていない実行は偽）。ほかの止まった実行の is_error は、見本の作り手に任せる
      if (want.isError === true) assert.equal(got.is_error, true, `${stage} ${i + 1} 回目の is_error`);
      else if (want.subtype === undefined) assert.equal(got.is_error, false, `${stage} ${i + 1} 回目の is_error`);
    });
  });
}

test('D0051-AC-75: 見本の記録の runs[] の要素の鍵は、本体が書く形（見本 showcase の段の実行の鍵）に、共通の表の keys（max_budget_usd・resumed）だけを足したものの中に収まる', async () => {
  const known = new Set<string>(loadBudgetTable().keys);
  for (const run of parseState(readFileSync(path.join(SHOWCASE_DIR, 'state.json'), 'utf8')).runs) {
    if (typeof run.seq === 'number') for (const key of Object.keys(run)) known.add(key);
  }
  for (const name of ['budgetStateJson', 'fourStagesStateJson'] as const) {
    const stageRuns = (await sampleState(name)).runs.filter((r) => typeof r.seq === 'number');
    assert.ok(stageRuns.length > 0, `${name}: 段の実行がある`);
    for (const run of stageRuns) assert.deepEqual(Object.keys(run).filter((k) => !known.has(k)), [], `${name}: 本体が書かない鍵`);
  }
});

test('D0051-AC-75: 見本の記録の節の状態は、余裕 1・近い 2（bd-near・bd-multi）・超えた 1・止まった 4・状態なし 2（bd-nolimit・bd-resumed-ok）。bd-multi は 1 回目・bd-maxpair は 2 回目を出す', async () => {
  const view = stateView(await sampleText('budgetStateJson'));
  const states = SAMPLE_NAMES.map((id) => [id, budgetOfNode(view, id)?.state ?? null] as const);
  assert.deepEqual(Object.fromEntries(states), Object.fromEntries(SAMPLE_NAMES.map((id) => [id, SAMPLE[id]!.state])));
  const count = (s: string | null): number => states.filter(([, x]) => x === s).length;
  assert.deepEqual([count('ok'), count('near'), count('over'), count('stopped'), count(null)], [1, 2, 1, 4, 2]);
  assert.equal(budgetOfNode(view, 'bd-multi')?.nth, 1);
  assert.equal(budgetOfNode(view, 'bd-maxpair')?.nth, 2);
  assert.equal(budgetOfNode(view, 'bd-maxpair')?.runCount, 2);
});

// ======== AC-80：手で作る記録（fourStagesStateJson） ========

test('D0051-AC-80: fourStagesStateJson はパイプ budget-demo の 4 つの段（余裕 0.2 / 1.0・近い 0.9 / 1.0・超えた 1.2 / 1.0・止まった 1.02 / 1.0）の記録', async () => {
  const state = await sampleState('fourStagesStateJson');
  assert.equal(state.pipe, 'budget-demo');
  assert.deepEqual(state.stages.map((s) => s.name), [...FOUR]);
  const by = runsByStage(state);
  for (const stage of FOUR) {
    const want = SAMPLE[stage]!.runs[0]!;
    const runs = by.get(stage) ?? [];
    assert.equal(runs.length, 1, `${stage} の実行は 1 回`);
    assert.equal(runs[0]!.cost_usd, want.cost, `${stage} の費用`);
    assert.equal(runs[0]!.max_budget_usd, want.limit, `${stage} の上限`);
    assert.equal(runs[0]!.subtype, want.subtype ?? 'success');
    assert.equal(runs[0]!.is_error, want.isError === true);
  }
});

test('D0051-AC-80: fourStagesStateJson の図は、余裕（金額の対と棒だけ。警告の言葉なし）・近い・超えた・止まった（金額の対・棒・言葉）になる', async () => {
  const view = stateView(await sampleText('fourStagesStateJson'));
  assert.deepEqual(FOUR.map((id) => budgetOfNode(view, id)?.state), ['ok', 'near', 'over', 'stopped']);
  const svg = renderFlowSvg(view.nodes, new Set(reasonNodeIds(view)), null);
  for (const id of FOUR) {
    const spec = SAMPLE[id]!;
    const g = nodeG(svg, id);
    assert.ok(g.includes(spec.pair!), `${id}: 金額の対 ${spec.pair}`);
    assert.ok(g.includes('budget-fill'), `${id}: 棒`);
    for (const word of Object.values(WORD)) assert.equal(g.includes(word), word === spec.word, `${id}: 言葉 ${word}`);
  }
});

// ======== 一時フォルダ（buildBudgetDir） ========

test('D0051-AC-75: buildBudgetDir(dest) は dest の中の docs/pipeline に state.json（budgetStateJson の中身）と 00_input.md を書き、その絶対パスを返す', async () => {
  const pages = await loadPages();
  const expected = await sampleText('budgetStateJson');
  await withTempDir(async (dest) => {
    const dir = (await needPage(pages, 'buildBudgetDir')(dest)) as string;
    assert.ok(path.isAbsolute(dir), `絶対パスを返す（返した値: ${JSON.stringify(dir)}）`);
    assert.equal(path.relative(dest, dir).split(path.sep).join('/'), 'docs/pipeline');
    assert.equal(await readFile(path.join(dir, 'state.json'), 'utf8'), expected);
    assert.ok((await readFile(path.join(dir, '00_input.md'), 'utf8')).trim().length > 0, '00_input.md に 1 行のメモ');
  });
});

test('D0051-AC-75: buildBudgetDir が書いた記録を、拡張の本物の読み取り（readShowcaseView）で読むと、10 段の節が並ぶ', async () => {
  const pages = await loadPages();
  const names = (await sampleState('budgetStateJson')).stages.map((s) => s.name);
  await withTempDir(async (dest) => {
    const dir = (await needPage(pages, 'buildBudgetDir')(dest)) as string;
    assert.ok(dir.length > 0, 'buildBudgetDir が作業フォルダの絶対パスを返す');
    const view = await readShowcaseView(dir);
    assert.deepEqual(view.nodes.filter((n) => n.id.startsWith('bd-')).map((n) => n.id), names);
  });
});

// ======== ページの文字（budgetPageHtml） ========

const builtPages = new Map<Theme, Promise<{ html: string; dest: string }>>();
/** budgetPageHtml が作ったページの文字と、そのとき使った一時フォルダの名前（フォルダは作ったあとで消してある）。テーマごとに 1 回だけ作る。 */
function budgetPage(theme: Theme): Promise<{ html: string; dest: string }> {
  let page = builtPages.get(theme);
  if (page === undefined) {
    page = (async () => {
      const pages = await loadPages();
      return withTempDir(async (dest) => {
        const html = (await needPage(pages, 'budgetPageHtml')(dest, theme)) as string;
        assert.ok(html.length > 0, `budgetPageHtml(dest, '${theme}') が空の文字を返した（ページがまだ無い）`);
        return { html, dest };
      });
    })();
    builtPages.set(theme, page);
  }
  return page;
}

for (const theme of THEME_NAMES) {
  test(`D0051-AC-75: ページ（${theme}）の図に、10 段の節が並び、状態のクラスが設計のとおり付く（余裕・近い・超えた・止まった・クラスなし）`, async () => {
    const { html } = await budgetPage(theme);
    for (const id of SAMPLE_NAMES) {
      const want = SAMPLE[id]!.state;
      assert.deepEqual(classesOf(nodeG(html, id)).filter((c) => c.startsWith('is-budget-')), want === null ? [] : [`is-budget-${want}`], id);
    }
  });

  test(`D0051-AC-75: ページ（${theme}）の各節に、設計の金額の対・言葉・「N 回目」が出る。出ないはずのものは出ない`, async () => {
    const { html } = await budgetPage(theme);
    for (const id of SAMPLE_NAMES) {
      const spec = SAMPLE[id]!;
      const g = nodeG(html, id);
      const texts = textsOf(g);
      if (spec.pair === null) assert.ok(!/\$[0-9.]+\+? \/ \$/.test(g), `${id}: 金額の対は出ない`);
      else assert.ok(texts.some((t) => t.includes(spec.pair!)), `${id}: 金額の対 ${spec.pair}（${texts.join(' | ')}）`);
      for (const word of Object.values(WORD)) assert.equal(texts.some((t) => t === word), word === spec.word, `${id}: 言葉 ${word}`);
      if (spec.nth === null) assert.ok(!texts.some((t) => /\d+ 回目/.test(t)), `${id}: 「N 回目」は出ない`);
      else assert.ok(texts.some((t) => t.includes(`${spec.nth} 回目`)), `${id}: ${spec.nth} 回目`);
      assert.equal(g.includes('budget-fill'), spec.pair !== null, `${id}: 棒は金額の対と同じ節だけ`);
    }
  });

  test(`D0051-AC-78: ページ（${theme}）の最大の組の節 bd-maxpair に、金額の対 $9999.999 / $10000.00 と「上限で止まった」と「2 回目」が同時に出る（節の枠からはみ出さないかは画面で計る）`, async () => {
    const { html } = await budgetPage(theme);
    const g = nodeG(html, 'bd-maxpair');
    const texts = textsOf(g);
    assert.ok(texts.some((t) => t.includes('$9999.999 / $10000.00')), `金額の対: ${texts.join(' | ')}`);
    assert.ok(texts.some((t) => t === WORD.stopped), '上限で止まった');
    assert.ok(texts.some((t) => t.includes('2 回目')), '2 回目');
  });

  test(`D0051-AC-79: ページ（${theme}）の使用量のパネルに、データの印 data-stage-costs の節が 1 つあり、行の並びは state.json を別に集計した費用の多い順（同額は段の並びの順）・割合は費用 ÷ 合計の四捨五入`, async () => {
    const { html } = await budgetPage(theme);
    assert.equal(html.split('data-stage-costs').length - 1, 1, 'ページ全体で 1 つ');
    const section = stageCostsSection(usagePanelOf(html));
    assert.ok(section !== null, '使用量のパネルの中に節がある');
    const state = await sampleState('budgetStateJson');
    const by = runsByStage(state);
    const units = state.stages.map((s, order) => ({
      label: s.label,
      order,
      runs: by.get(s.name)?.length ?? 0,
      units: Math.round((by.get(s.name) ?? []).reduce((sum, r) => sum + (r.cost_usd as number), 0) * 1e4),
    }));
    const expected = units.filter((u) => u.units > 0).sort((a, b) => b.units - a.units || a.order - b.order);
    const total = expected.reduce((sum, u) => sum + u.units, 0);
    const table = costTableOf(section);
    assert.equal(table.rows.length, expected.length, '費用のある段の行');
    expected.forEach((e, i) => {
      const row = table.rows[i]!;
      assert.ok(row[0]!.startsWith(e.label), `${i + 1} 行目は ${e.label}（${row[0]}）`);
      assert.equal(row[2], `${Math.round((e.units * 100) / total)}%`, `${e.label} の割合`);
    });
    assert.equal(table.rows[0]![0]!.startsWith(state.stages.find((s) => s.name === 'bd-maxpair')!.label), true, '最大の費用の段（bd-maxpair）が先頭');
  });
}

for (const theme of THEME_NAMES) {
  test(`D0051-AC-75: ページ（${theme}）は CSP をそのまま持ち、script と style のタグはすべて nonce="preview" を持ち、style 属性を使わない。使う --vscode-* の色はすべて THEMES が決めている`, async () => {
    const { html } = await budgetPage(theme);
    const csp = /<meta http-equiv="Content-Security-Policy"[^>]*>/g;
    const done = panelPreviewHtml(await readShowcaseView(SHOWCASE_DIR), 'dark').match(csp);
    assert.ok(done !== null && done.length === 1);
    assert.deepEqual(html.match(csp), done, 'CSP は今のページと同じ');
    const tags = [...html.matchAll(/<(script|style)\b[^>]*>/g)].map((m) => m[0]);
    assert.ok(tags.length >= 3, `本物の style・script と、テーマの色・置き換え（${tags.length} 個）`);
    assert.deepEqual(tags.filter((t) => !t.includes('nonce="preview"')), []);
    assert.doesNotMatch(html, /\sstyle="/);
    const used = new Set([...html.matchAll(/var\(\s*(--vscode-[\w-]+)/g)].map((m) => m[1]!));
    const defined = new Set([...THEMES[theme].matchAll(/(--vscode-[\w-]+)\s*:/g)].map((m) => m[1]!));
    assert.deepEqual([...used].filter((name) => !defined.has(name)).sort(), [], `${theme}: THEMES に無い色`);
    assert.ok(html.includes(THEMES[theme]), 'テーマの色がページに入っている');
  });
}

// 検証の段で直した：作業フォルダの表示（docs/pipeline）は実行の一覧があるページの上のバーにだけ出て、
// 設計どおりの 1 つの実行のページ（panelPreviewHtml）には出ない（既存の完了のページも同じ）ので、その確かめを外した。
test('D0051-AC-75: ページに手元の情報（ユーザー名の入ったパス・メールアドレス）や、一時フォルダ・リポジトリの絶対パスが出ていない', async () => {
  for (const theme of THEME_NAMES) {
    const { html, dest } = await budgetPage(theme);
    assert.ok(html.length > 0, `${theme}: ページが作られている`);
    assert.deepEqual(LOCAL_INFO.filter((re) => re.test(html)).map(String), [], theme);
    assert.ok(!html.includes(dest), `${theme}: 一時フォルダの絶対パスが出ていない`);
    assert.ok(!html.includes(REPO), `${theme}: リポジトリの絶対パスが出ていない`);
  }
});

test('D0051-AC-75: 見本の記録の文字（budgetStateJson・fourStagesStateJson）に手元の情報が出ていない', async () => {
  for (const name of ['budgetStateJson', 'fourStagesStateJson'] as const) {
    const text = await sampleText(name);
    assert.deepEqual(LOCAL_INFO.filter((re) => re.test(text)).map(String), [], name);
    assert.ok(!text.includes(REPO), `${name}: リポジトリの絶対パスが出ていない`);
  }
});

test('D0051-AC-76: 明るいページと暗いページは、テーマの色の <style> 以外が同じ（成果物の更新時刻 MM/DD HH:mm は、作った瞬間の時刻なので除いて比べる）', async () => {
  const strip = (html: string, theme: Theme): string => html.replace(`:root{${THEMES[theme]}}`, '').replace(/\d{2}\/\d{2} \d{2}:\d{2}/g, 'MM/DD HH:mm');
  const light = strip((await budgetPage('light')).html, 'light');
  assert.ok(light.length > 0, 'ページが作られている');
  assert.equal(light, strip((await budgetPage('dark')).html, 'dark'));
});

// ======== 見本の木を作っても tests/fixtures/ は変わらない ========

/** dir の下のファイルごとの「相対パス・大きさ・更新時刻・中身の指紋」。順番は名前順。 */
async function fingerprint(dir: string): Promise<string[]> {
  const out: string[] = [];
  const walk = async (d: string): Promise<void> => {
    const entries = (await readdir(d, { withFileTypes: true })).sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    for (const ent of entries) {
      const full = path.join(d, ent.name);
      if (ent.isDirectory()) {
        await walk(full);
        continue;
      }
      const info = await stat(full);
      out.push(`${path.relative(dir, full).split(path.sep).join('/')}|${info.size}|${info.mtimeMs}|${createHash('sha1').update(await readFile(full)).digest('hex')}`);
    }
  };
  await walk(dir);
  return out;
}

test('D0051-AC-75: 見本のページ・記録を作っても、tests/fixtures/ の内容と更新時刻は変わらない（見本の記録は足さない・書かない）。今のまま通る。守る', async () => {
  const pages = await loadPages();
  const fixtures = path.dirname(SHOWCASE_DIR);
  const before = await fingerprint(fixtures);
  assert.ok(before.length > 0, 'tests/fixtures/ にファイルがある');
  assert.ok(!before.some((line) => line.includes('bd-')), 'tests/fixtures/ に上限の見本の記録（bd-）は無い');
  for (const theme of THEME_NAMES) await withTempDir(async (dest) => void (await needPage(pages, 'budgetPageHtml')(dest, theme)));
  await withTempDir(async (dest) => void (await needPage(pages, 'buildBudgetDir')(dest)));
  assert.deepEqual(await fingerprint(fixtures), before);
});

// ======== preview.ts の呼び方を文字で守る（D0025 の成果物のページと同じ形） ========

/** preview.ts の文字の問題（上限のページを作らない・一時フォルダの外で作る・種類の分かれが無い）。無ければ空。 */
function budgetWiringProblems(source: string): string[] {
  const code = withoutComments(source);
  const problems: string[] = [];
  if (callArgs(code, 'budgetPageHtml').length === 0) problems.push('budgetPageHtml( を呼んでいない');
  if (!/kind\s*===\s*['"]budget['"]/.test(code)) problems.push("kind === 'budget' の分かれが無い");
  if (!callArgs(code, 'inTempDir').some((args) => args.includes('budgetPageHtml('))) problems.push('budgetPageHtml( を inTempDir( の中で呼んでいない（見本の記録は一時フォルダに書く）');
  return problems;
}

test('D0051-AC-75: scripts/preview.ts は kind === budget で、budgetPageHtml( を inTempDir( の中で呼ぶ', () => {
  assert.deepEqual(budgetWiringProblems(readFileSync(path.join(REPO, 'vscode', 'scripts', 'preview.ts'), 'utf8')), []);
});

const CLEAN_WIRING = [
  'for (const [page, theme] of PANEL_PAGES) {',
  '  const kind = panelKind(page);',
  "  if (kind === 'budget') {",
  "    writeFileSync(path.join(OUT, `${page}.html`), await inTempDir('budget', (dest) => budgetPageHtml(dest, theme)), 'utf8');",
  '    continue;',
  '  }',
  '}',
].join('\n');

const BROKEN_WIRINGS: readonly (readonly [string, string, string])[] = [
  ['上限のページを作らない', CLEAN_WIRING.replace(/await inTempDir\([^\n]*\), 'utf8'\);/, "'', 'utf8');"), 'budgetPageHtml( を呼んでいない'],
  ['種類の分かれを書かない', CLEAN_WIRING.replace("kind === 'budget'", "kind === 'stale'"), "kind === 'budget' の分かれが無い"],
  ['一時フォルダの外で作る', CLEAN_WIRING.replace("await inTempDir('budget', (dest) => budgetPageHtml(dest, theme))", 'await budgetPageHtml(OUT, theme)'), 'inTempDir( の中で呼んでいない'],
];
for (const [label, source, word] of BROKEN_WIRINGS) {
  test(`D0051-AC-75: 検査そのもの：${label} preview.ts の見本の文字は見つける。今のまま通る。守る`, () => {
    assert.notEqual(source, CLEAN_WIRING, '見本の文字を壊せている');
    assert.ok(budgetWiringProblems(source).some((p) => p.includes(word)), budgetWiringProblems(source).join(' / '));
  });
}
test('D0051-AC-75: 検査そのもの：きれいな preview.ts の見本の文字は見逃す（コメントの中の budgetPageHtml( は数えない）。今のまま通る。守る', () => {
  assert.deepEqual(budgetWiringProblems(CLEAN_WIRING), []);
  const commentOnly = CLEAN_WIRING.replace(/await inTempDir\([^\n]*\), 'utf8'\);/, "'', 'utf8');").replace('continue;', "continue;\n  // budgetPageHtml(dest, theme) は後で呼ぶ\n  /* inTempDir(budgetPageHtml(x)) */");
  assert.ok(budgetWiringProblems(commentOnly).includes('budgetPageHtml( を呼んでいない'), 'コメントの中の呼び出しは数えない');
});
