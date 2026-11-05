// D0076-AC-24（判断の部分）：使用量が「取れない」記録（会話の道で流した記録）のパネル・図・ステータスバーは、「$」の数を出さず、「取れない」と読める。
// 画面の見た目（重なり・はみ出し・読めない色）は Playwright で確かめる（docs/pipeline/03_red_tests.md の「画面の確認の手順」）。ここは文字の判断だけ。
// 赤の理由は「まだ作っていない」：renderUsageUnavailable は空の文字を返し、費用の 4 か所（図の段の 2 行目・上のバーの費用・ステータスバー・一覧の行）が $0.000 を出す。
// 「今のまま通る。守る」と書いたものは、古い記録の出し方（費用の数が $ で出る）を見張る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { summarizeRun } from '../domain/runList.ts';
import type { RunListView } from '../domain/runList.ts';
import { renderFlowSvg } from './flowSvg.ts';
import { renderPanelHtml } from './panelHtml.ts';
import { emptyListFor, renderShell } from './shellHtml.ts';
import { statusBarLabel } from './statusBar.ts';
import { renderUsageUnavailable } from './usageHtml.ts';
import { UNAVAILABLE_REASON, chatSnapshot, chatStateJson, oldSnapshot, waitingSnapshot } from '../test/chatFixtures.ts';
import { clockAt } from '../test/liveFixtures.ts';

const MONEY = /\$\d/;

function listWith(view: PipelineView, stateJson: string): RunListView {
  void view;
  const row = summarizeRun({ key: 'here|', id: '', branch: null, other: false, memoHead: null, previous: false, stageLogs: [], stateJson }, clockAt(0));
  return { rows: [row], selected: row.key, omitted: [], omittedWorktrees: 0, workDir: '/w' };
}

const chatView = (): PipelineView => buildPipelineView(chatSnapshot({ final: 'PASSED' }));

// ---- 使用量の欄 ----

test('D0076-AC-24: renderUsageUnavailable は 1 つの section に「使用量」の見出しと「使用量は取れません（理由）」を出す', () => {
  const html = renderUsageUnavailable(UNAVAILABLE_REASON);
  assert.match(html, /^<section[\s>]/);
  assert.match(html, /使用量/);
  assert.match(html, /使用量は取れません/);
  assert.ok(html.includes(UNAVAILABLE_REASON), '理由の文が出る');
  assert.equal((html.match(/<section/g) ?? []).length, 1);
  assert.doesNotMatch(html, MONEY);
});

test('D0076-AC-24: renderUsageUnavailable は理由を HTML として解釈させず、style 属性も外部の読み込みも持たない', () => {
  const html = renderUsageUnavailable('<img src=x onerror=alert(1)>');
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img/);
  assert.doesNotMatch(html, /\sstyle\s*=/i);
  assert.doesNotMatch(html, /(src|href)\s*=\s*["']?https?:/i);
});

// ---- パネル ----

test('D0076-AC-24: パネル（行なし）は、上のバーの費用が「取れない」で、$ の数が出ない', () => {
  const view = chatView();
  const html = renderShell(view, emptyListFor(view));
  assert.doesNotMatch(html, MONEY, '$ の数が出ている');
  assert.match(html, /費用[^]*?取れ/);
});

test('D0076-AC-24: パネル（一覧の行を選んだ）は、上のバーの費用と一覧の行が「取れない」で、$ の数が出ない', () => {
  const view = chatView();
  const html = renderShell(view, listWith(view, chatStateJson({ final: 'PASSED' })));
  assert.doesNotMatch(html, MONEY, '$ の数が出ている');
  assert.match(html, /費用[^]*?取れ/);
});

test('D0076-AC-24: 使用量のタブは「使用量は取れません」と理由を出し、零の表（トークンの表・モデル別）を出さない', () => {
  const view = chatView();
  const html = renderShell(view, emptyListFor(view));
  const start = html.indexOf('data-detail-panel="usage"');
  assert.ok(start >= 0, '使用量のパネルの枠はある');
  const end = html.indexOf('</main>', start);
  const panel = html.slice(start, end < 0 ? undefined : end);
  assert.match(panel, /使用量は取れません/);
  assert.ok(panel.includes(UNAVAILABLE_REASON));
  assert.doesNotMatch(panel, /usage-table/);
  assert.doesNotMatch(panel, /段ごとの費用/);
});

test('D0076-AC-24: ページ全体（スクリプトと CSS を含む）にも $ の数が出ず、外部の読み込みと色の直書きが無い', () => {
  const html = renderPanelHtml(chatView(), 'n');
  assert.doesNotMatch(html, MONEY);
  assert.doesNotMatch(html, /(src|href)\s*=\s*["']?https?:/i);
  assert.doesNotMatch(html, /#[0-9a-fA-F]{3,8}\b/);
  assert.doesNotMatch(html, /rgba?\(|hsla?\(/);
});

test('D0076-AC-25: 古い記録のパネルは、費用が $ の数で出て、使用量の表も出る（今のまま通る。守る）', () => {
  const view = buildPipelineView(oldSnapshot());
  const html = renderShell(view, emptyListFor(view));
  assert.match(html, /\$1\.234/);
  assert.match(html, /usage-table/);
  assert.doesNotMatch(html, /使用量は取れません/);
});

// ---- 図 ----

test('D0076-AC-24: 図の段の 2 行目は、$ もターン数も外して時間だけにする（0 ターンと書いて誤解させない）', () => {
  const svg = renderFlowSvg(chatView().nodes, new Set(), null);
  assert.doesNotMatch(svg, MONEY, '段の節の詳細に $ の数が出ている');
  assert.doesNotMatch(svg, /ターン/, '取れないターン数を 0 ターンと出している');
  assert.match(svg, /class="node-detail"[^>]*>\d+:\d\d</, '2 行目は時間だけ（例 0:09）');
});

test('D0076-AC-25: 古い記録の図の段の 2 行目は、今までどおり $ の費用を出す（今のまま通る。守る）', () => {
  const svg = renderFlowSvg(buildPipelineView(oldSnapshot()).nodes, new Set(), null);
  assert.match(svg, /ターン・\$0\.0\d0・/);
});

// ---- ステータスバー ----

for (const [label, snap] of [
  ['終わった', chatSnapshot({ final: 'PASSED' })],
  ['確認待ち', waitingSnapshot()],
  ['動いていない（待ち）', chatSnapshot({ runs: [] })],
] as const) {
  test(`D0076-AC-24: ステータスバー（${label}）は、$ の数を出さず「取れない」と読める`, () => {
    const bar = statusBarLabel(buildPipelineView(snap));
    assert.doesNotMatch(bar.tooltip, MONEY, bar.tooltip);
    assert.doesNotMatch(bar.text, MONEY);
    assert.match(bar.tooltip, /取れ/);
  });
}

test('D0076-AC-25: 古い記録のステータスバーは、今までどおり「合計 $…」を出す（今のまま通る。守る）', () => {
  const bar = statusBarLabel(buildPipelineView(oldSnapshot()));
  assert.match(bar.tooltip, /合計 \$1\.234/);
});
