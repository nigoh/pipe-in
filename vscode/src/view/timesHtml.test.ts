// 右の欄の「時間」の節（D0017）：実行が2回以上ある段の、回ごとの時間と合計。timesHtml.ts はテスト先行の時点でまだ無いので、
// テストの中で読み込む（呼んだところで落ちる）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { snapshot, stageRunEntry, stateJson } from '../test/fixtures.ts';
import { finishedView, runningView, viewAt } from '../test/liveFixtures.ts';

const load = () => import('./timesHtml.ts');

test('D0017-AC-16: 全段が1回ずつなら「時間」の節は出ない（空の文字＝今と同じ HTML）', async () => {
  const { renderTimes } = await load();
  assert.equal(renderTimes(runningView(83)), '');
  assert.equal(renderTimes(buildPipelineView(snapshot())), '');
});

test('D0017-AC-16: 回が複数の段だけが「時間」の節に出る（要件定義は1回なので出ない）', async () => {
  const { renderTimes } = await load();
  const html = renderTimes(finishedView());
  assert.match(html, /^<section class="times">/);
  assert.match(html, /<h2 class="terminal-title">時間<\/h2>/);
  assert.ok(html.includes('実装'));
  assert.ok(html.includes('検証'));
  assert.ok(!html.includes('要件定義'), '1回だけの段は出ない');
});

test('D0017-AC-16: 実装の回ごとの時間と合計が m:ss で出る（121.04・78.02・40.01 秒 → 2:01・1:18・0:40、合計 3:59）', async () => {
  const { renderTimes } = await load();
  const html = renderTimes(finishedView());
  assert.ok(html.includes('実装（合計 3:59）'), html);
  assert.ok(html.includes('1 回目 2:01'));
  assert.ok(html.includes('2 回目 1:18'));
  assert.ok(html.includes('3 回目 0:40'));
});

test('D0017-AC-16: 回ごとの並びは古い順（1 回目 → 2 回目 → 3 回目）', async () => {
  const { renderTimes } = await load();
  const html = renderTimes(finishedView());
  const i1 = html.indexOf('1 回目 2:01');
  const i2 = html.indexOf('2 回目 1:18');
  const i3 = html.indexOf('3 回目 0:40');
  assert.ok(i1 > 0 && i1 < i2 && i2 < i3);
});

test('D0017-AC-16: attempt を持たない段（要件定義を修正して2回）は、実行の順で 1 回目・2 回目になる', async () => {
  const { renderTimes } = await load();
  const view = viewAt(
    snapshot({
      stateJson: stateJson({
        runs: [
          stageRunEntry({ stage: 'requirements', seq: 1, durationSec: 30 }),
          { stage: 'requirements', review: 'revise', feedback: '直して' },
          stageRunEntry({ stage: 'requirements', seq: 2, durationSec: 20 }),
        ],
      }),
    }),
  );
  const html = renderTimes(view);
  assert.ok(html.includes('要件定義（合計 0:50）'), html);
  assert.ok(html.includes('1 回目 0:30'));
  assert.ok(html.includes('2 回目 0:20'));
});

test('D0017-AC-16: 時間の節は数え上げ（data-elapsed）も動き・style 属性も持たない固定の表示', async () => {
  const { renderTimes } = await load();
  const html = renderTimes(finishedView());
  assert.doesNotMatch(html, /data-elapsed|\sstyle\s*=|\son[a-z]+\s*=|hidden|data-reasons-for/);
});

test('D0017-AC-16: 段の名前（ラベル）の <script>・"・& はエスケープされる', async () => {
  const { renderTimes } = await load();
  const evil = '<script>alert(1)</script>"&';
  const draw = (seq: number) => stageRunEntry({ stage: 'draw', seq, durationSec: 20 });
  const view = viewAt(
    snapshot({
      stateJson: stateJson({
        pipe: 'p',
        stages: [{ name: 'draw', label: evil, output: 'a.md', review: false }],
        runs: [draw(1), draw(2)],
      }),
    }),
  );
  const html = renderTimes(view);
  assert.ok(html.length > 0);
  assert.ok(!html.includes('<script>'), html);
  assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt;&quot;&amp;'), html);
});

test('D0017-AC-16: TIMES_STYLE は色を var(--vscode-*) だけで決める（色の直書き・style 属性の元になる値が無い）', async () => {
  const { TIMES_STYLE } = await load();
  assert.equal(typeof TIMES_STYLE, 'string');
  assert.doesNotMatch(TIMES_STYLE, /#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/);
  assert.doesNotMatch(TIMES_STYLE, /animation|@keyframes/, '動きの規則は panelHtml の no-preference の塊に置く');
});
