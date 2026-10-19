// 左の列のパイプライン図（SVG の流れ図）。本線の矢印・戻りの矢印（修正・差し戻し）・節の状態。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderFlowSvg } from './flowSvg.ts';
import { renderViewBody } from './panelHtml.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { snapshot, stageRunEntry, stateJson } from '../test/fixtures.ts';
import { finishedView, loopSnapshot, runningSnapshot, runningView, viewAt, waitingView } from '../test/liveFixtures.ts';

const count = (text: string, re: RegExp) => (text.match(re) ?? []).length;

test('流れ図：11個の節と、それをつなぐ10本の本線の矢印を描く', () => {
  const svg = renderFlowSvg(buildPipelineView(snapshot()).nodes);
  assert.match(svg, /^<svg class="flow"/);
  assert.match(svg, /role="img"/);
  assert.equal(count(svg, /<g class="node is-/g), 11);
  assert.equal(count(svg, /class="edge"/g), 10);
  for (const label of ['要件メモ', '要件定義', '設計', 'テスト先行', '実装', '検証', '判定', '完了']) {
    assert.match(svg, new RegExp(`>${label}<`), label);
  }
});

test('流れ図：戻りの矢印は4本（確認から同じ段へ3本、判定から実装へ1本）。何も起きていなければ強調しない', () => {
  const svg = renderFlowSvg(buildPipelineView(snapshot()).nodes);
  assert.equal(count(svg, /<g class="loop[ "]/g), 4);
  assert.equal(count(svg, /class="loop is-hot"/g), 0);
  assert.match(svg, /data-loop="revise:requirements"/);
  assert.match(svg, /data-loop="revise:design"/);
  assert.match(svg, /data-loop="revise:red"/);
  assert.match(svg, /data-loop="send-back"/);
});

test('流れ図：修正の依頼・差し戻しが起きた戻りの矢印は強調し、回数を添える', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [
          stageRunEntry({ stage: 'requirements', seq: 1 }),
          { stage: 'requirements', review: 'revise', feedback: 'a' },
          stageRunEntry({ stage: 'requirements', seq: 2 }),
          { stage: 'requirements', review: 'approved' },
          stageRunEntry({ stage: 'implement', seq: 3, attempt: 1 }),
          stageRunEntry({ stage: 'implement', seq: 4, attempt: 2 }),
        ],
      }),
    }),
  );
  const svg = renderFlowSvg(view.nodes);
  assert.equal(count(svg, /class="loop is-hot"/g), 2);
  assert.match(svg, /<g class="loop is-hot" data-loop="revise:requirements"[^>]*>/); // D0017: data-count が足される
  assert.match(svg, /<g class="loop is-hot" data-loop="send-back"[^>]*>/);
  assert.match(svg, />修正 1回</);
  assert.match(svg, />差し戻し 1回</);
});

test('流れ図：段の節にはターン・費用・時間を出す', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [stageRunEntry({ stage: 'design', seq: 1, numTurns: 23, costUsd: 1.706, durationSec: 336.7 })],
      }),
    }),
  );
  // D0017: 時間の書き方が m:ss になった（336.7 秒は切り捨てて 5:36）
  assert.match(renderFlowSvg(view.nodes), />23 ターン・\$1\.706・5:36</);
});

test('流れ図：省略した確認は is-skipped と「省略」で出す', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [stageRunEntry({ stage: 'requirements', seq: 1 }), stageRunEntry({ stage: 'design', seq: 2 })],
      }),
    }),
  );
  const svg = renderFlowSvg(view.nodes);
  assert.match(svg, /<g class="node is-skipped" data-node="review:requirements">/);
  assert.match(svg, /class="node-status"[^>]*>[^<]*省略</);
});

test('流れ図：ログから来た文字はないが、節の名前も含めて文字は必ずエスケープされる形で入る', () => {
  const svg = renderFlowSvg(buildPipelineView(snapshot()).nodes);
  assert.doesNotMatch(svg, /<script/i);
  assert.doesNotMatch(svg, /#[0-9a-fA-F]{3,8}\b/);
});

// ---- D0017：動きと各段の時間 ----

/** 節 id の <g> のまとまり（節の中に <g> は入れ子にならない）。 */
const nodeGroup = (svg: string, id: string): string => new RegExp(`<g class="node [^"]*" data-node="${id}"[^>]*>[\\s\\S]*?</g>`).exec(svg)?.[0] ?? '';
/** 要素（<text>・<tspan>）のうち、クラスに cls を持つものの {属性, 文字}。 */
function elementsWithClass(markup: string, cls: string): { attrs: string; text: string }[] {
  return [...markup.matchAll(/<(?:text|tspan)\b([^>]*)>([^<]*)<\/(?:text|tspan)>/g)]
    .map((m) => ({ attrs: m[1], text: m[2] }))
    .filter((e) => new RegExp(`class="[^"]*\\b${cls}\\b[^"]*"`).test(e.attrs));
}
const dataElapsed = (attrs: string): string | null => /data-elapsed="([^"]*)"/.exec(attrs)?.[1] ?? null;
const svgOf = (view: { nodes: Parameters<typeof renderFlowSvg>[0] }): string => renderFlowSvg(view.nodes);

test('D0017-AC-14: 動いている段の節に、「経過」と経過時間の要素（data-elapsed に基準の秒、中は m:ss）がある', () => {
  const group = nodeGroup(svgOf(runningView(83)), 'design');
  assert.match(group, /経過 <tspan class="elapsed" data-elapsed="83">1:23<\/tspan>/);
  assert.equal(elementsWithClass(group, 'elapsed').length, 1);
});

test('D0017-AC-14: 1時間以上の経過は h:mm:ss の初期の文字になる', () => {
  const group = nodeGroup(svgOf(runningView(3725)), 'design');
  assert.match(group, /data-elapsed="3725">1:02:05</);
});

test('D0017-AC-14: 動いていない段の節（要件定義・設計以外）に経過の要素は無い', () => {
  const svg = svgOf(runningView(83));
  assert.equal(count(svg, /data-elapsed=/g), 1, '動いている段の 1 か所だけ');
  assert.equal(elementsWithClass(nodeGroup(svg, 'requirements'), 'elapsed').length, 0);
});

test('D0017-AC-14: 動いている段の状態の文字（動いている）は今までどおり残る', () => {
  const group = nodeGroup(svgOf(runningView(83)), 'design');
  assert.match(group, /class="node-status"[^>]*>[^<]*動いている</);
  assert.match(svgOf(runningView(83)), /<g class="node is-running" data-node="design"/);
});

test('D0017-AC-15: 確認待ちの確認の節に、待ち時間の要素（node-wait・data-elapsed・m:ss）と is-waiting が付き、状態の文字は「確認待ち」', () => {
  const svg = svgOf(waitingView(40));
  const group = nodeGroup(svg, 'review:requirements');
  assert.match(group, /^<g class="node [^"]*\bis-waiting\b/);
  const waits = elementsWithClass(group, 'node-wait');
  assert.equal(waits.length, 1);
  assert.equal(dataElapsed(waits[0].attrs), '40');
  assert.equal(waits[0].text, '0:40');
  assert.match(group, /class="node-status"[^>]*>[^<]*確認待ち</);
});

test('D0017-AC-15: 確認待ちでない確認の節（ほかの確認・結果が出た確認）には、待ちの印も待ち時間も付かない', () => {
  const svg = svgOf(waitingView(40));
  for (const id of ['review:design', 'review:red']) {
    const group = nodeGroup(svg, id);
    assert.ok(group.length > 0, id);
    assert.doesNotMatch(group, /is-waiting|node-wait|data-elapsed/, id);
    assert.match(group, /class="node-status"[^>]*>[^<]*まだ</, `${id} の状態の文字は今までどおり`);
  }
  assert.equal(count(svg, /is-waiting/g), 1, '待ちの印は確認待ちの 1 か所だけ');
  const noWait = svgOf(runningView(83));
  assert.doesNotMatch(noWait, /is-waiting|node-wait/);
});

test('D0017-AC-16: 終わった段の節に、合計の時間が m:ss で出て、今までの「12s」の書き方は出ない', () => {
  const svg = svgOf(finishedView());
  const impl = nodeGroup(svg, 'implement');
  assert.match(impl, /ターン・\$0\.000・3:59</, '実装の合計 239.1 秒 → 3:59');
  assert.match(nodeGroup(svg, 'requirements'), /・0:48</);
  assert.doesNotMatch(svg, /・\d+s</, '「12s」の書き方は出ない');
});

test('D0017-AC-16: 図の節には合計だけを出す（回ごとの時間は図に出ない）', () => {
  const impl = nodeGroup(svgOf(finishedView()), 'implement');
  assert.doesNotMatch(impl, /2:01|1:18|0:40/);
});

test('D0017-AC-17: 動いている段へ入る矢印にだけ is-flowing が付く（ほかの矢印には付かない）', () => {
  const view = runningView(83);
  const svg = svgOf(view);
  const classes = [...svg.matchAll(/<line class="([^"]*)"/g)].map((m) => m[1]);
  assert.equal(classes.length, 10);
  const into = view.nodes.findIndex((n) => n.id === 'design') - 1;
  classes.forEach((cls, i) => {
    assert.equal(/\bis-flowing\b/.test(cls), i === into, `${i} 本目の矢印: ${cls}`);
    assert.match(cls, /\bedge\b/);
  });
});

test('D0017-AC-17: 動いている段が無ければ、どの矢印にも is-flowing が付かない（確認待ち・終わった・記録なし）', () => {
  for (const view of [waitingView(40), finishedView(), buildPipelineView(snapshot())]) {
    assert.doesNotMatch(svgOf(view), /is-flowing/);
  }
});

test('D0017-AC-17: 動いている段でも at が読めない（runningSec が無い）なら点の印は付かない', () => {
  assert.doesNotMatch(svgOf(viewAt(runningSnapshot({ omitAt: true }), 83)), /is-flowing/);
});

test('D0017-AC-29: 戻る矢印の <g> に、その回数が data-count で入る（差し戻し・修正の依頼の両方）', () => {
  const svg = renderFlowSvg(viewAt(loopSnapshot({ sendBack: 2, revise: 1 })).nodes);
  const loopTag = (id: string) => new RegExp(`<g class="loop[^"]*" data-loop="${id}"[^>]*>`).exec(svg)?.[0] ?? '';
  assert.match(loopTag('send-back'), /data-count="2"/);
  assert.match(loopTag('revise:requirements'), /data-count="1"/);
  assert.match(loopTag('revise:design'), /data-count="0"/);
  assert.match(loopTag('revise:red'), /data-count="0"/);
});

test('パネルの本体は左の列に流れ図を入れる', () => {
  const body = renderViewBody(buildPipelineView(snapshot()));
  assert.match(body, /<svg class="flow"/);
  assert.doesNotMatch(body, /<ol class="nodes">/);
});

test('上の帯：段が動いている間は「いま：段の名前（回）」を出す', () => {
  const body = renderViewBody(
    buildPipelineView(
      snapshot({ stageLogs: [{ fileName: '02_test_2.jsonl', text: '{"_type":"Prompt","stage":"test","resume":null,"prompt":"p"}\n' }] }),
    ),
  );
  assert.match(body, /いま：検証（2 回目）/);
});
