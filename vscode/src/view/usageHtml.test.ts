// パネルの「使用量」の節と、ステータスバーの説明の利用枠。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';
import { statusBarLabel } from './statusBar.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { snapshot, stageMetricsDict, stageRunEntry, stateJson, tokensDict, usageSummaryDict } from '../test/fixtures.ts';

function viewWithUsage(summary: unknown = usageSummaryDict()) {
  return buildPipelineView(
    snapshot({
      stateJson: stateJson({
        final: 'PASSED',
        totalCostUsd: 7.989,
        usageSummary: summary,
        runs: [
          stageRunEntry({ stage: 'requirements', seq: 1, metrics: stageMetricsDict({ tokens: tokensDict({ input: 16, cacheWrite: 87454, cacheRead: 452322, output: 20834, thinking: 9023 }) }) }),
          stageRunEntry({ stage: 'implement', seq: 4, attempt: 1 }),
        ],
      }),
    }),
  );
}

test('使用量の節：合計のトークンを桁区切りで、キャッシュ再利用率を % で出す', () => {
  const body = renderViewBody(viewWithUsage());
  assert.match(body, /使用量/);
  assert.match(body, /126,952/);
  assert.match(body, /5,224,407/);
  assert.match(body, /90\.5%/);
});

test('使用量の節：段の実行ごとの行に段の名前と回を出し、metrics のない段は — にする', () => {
  const body = renderViewBody(viewWithUsage());
  assert.match(body, /要件定義/);
  assert.match(body, /20,834/);
  assert.match(body, /実装（1 回目）[^]*?—/);
});

test('使用量の節：モデル別の費用と、利用枠の推移（途中で枠が戻ったら最大値も）を出す', () => {
  const body = renderViewBody(viewWithUsage());
  assert.match(body, /claude-opus-5-5[^]*?\$7\.988/);
  assert.match(body, /5時間枠[^]*?12% → 2%（途中で枠が戻った。最大 13%）/);
  assert.match(body, /7日枠[^]*?14% → 15%/);
});

test('使用量の節：ログから来たモデルの名前は HTML として解釈させない', () => {
  const summary = { ...(usageSummaryDict() as Record<string, unknown>), by_model: { '<img src=x onerror=alert(1)>': { tokens: {}, cost_usd: 1 } } };
  const body = renderViewBody(viewWithUsage(summary));
  assert.doesNotMatch(body, /<img/);
  assert.match(body, /&lt;img/);
});

test('使用量の節：使用量のない記録では節を出さない', () => {
  // 詳細のタブ「使用量」はいつも出るので、見るのは使用量のパネルの中だけ
  const html = renderViewBody(buildPipelineView(snapshot()));
  const start = html.indexOf('data-detail-panel="usage"');
  assert.ok(start >= 0, '使用量のパネルの枠はある');
  const end = html.indexOf('</main>', start);
  assert.doesNotMatch(html.slice(start, end < 0 ? undefined : end), /使用量/);
});

test('使用量の節：HTML に外部の読み込みと色の直書きがない（AC-42・AC-43 と同じ検査）', () => {
  const html = renderPanelHtml(viewWithUsage(), 'n');
  assert.doesNotMatch(html, /(src|href)\s*=\s*["']?https?:/i);
  assert.doesNotMatch(html, /#[0-9a-fA-F]{3,8}\b/);
  assert.doesNotMatch(html, /rgba?\(|hsla?\(/);
});

test('ステータスバー：使用量があれば、説明に利用枠の今の使用率を足す', () => {
  const label = statusBarLabel(viewWithUsage());
  assert.match(label.tooltip, /5時間枠 2%・7日枠 15%/);
  assert.match(label.tooltip, /クリックでパネルを開く/);
});

test('ステータスバー：使用量がなければ、説明は今までどおり', () => {
  const label = statusBarLabel(buildPipelineView(snapshot({ stateJson: stateJson({ final: 'PASSED', totalCostUsd: 1 }) })));
  assert.doesNotMatch(label.tooltip, /枠/);
});
