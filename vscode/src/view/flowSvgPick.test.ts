// 図の「選べる節」の印（D0016）。履歴のある節の <g> だけが、押せる印を持つ。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderFlowSvg } from './flowSvg.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { PipelineNode } from '../domain/pipelineView.ts';
import { snapshot } from '../test/fixtures.ts';
import { pipeView, showcaseView } from '../test/reasonFixtures.ts';

/** 第2引数（選べる節の id の集合）を渡して呼ぶ。 */
const render = renderFlowSvg as (nodes: PipelineNode[], pickable?: ReadonlySet<string>) => string;

/** 節 id の <g> の開始タグ。 */
function openTag(svg: string, id: string): string {
  const m = new RegExp(`<g class="node [^"]*" data-node="${id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"[^>]*>`).exec(svg);
  assert.ok(m, `節 ${id} の <g> が無い`);
  return m[0];
}
const PICK_MARKS = [/data-reasons=/, /data-reasons-loop=/, /tabindex=/, /role="button"/, /aria-pressed=/];

const PICKABLE = new Set(['implement', 'verdict', 'review:requirements']);

test('D0016-AC-09: 履歴のある節（実装・判定・確認）の g は、選べる印（data-reasons・tabindex・role・aria-pressed）を持つ', () => {
  const svg = render(showcaseView().nodes, PICKABLE);
  for (const id of PICKABLE) {
    const tag = openTag(svg, id);
    assert.match(tag, new RegExp(`data-reasons="${id}"`), id);
    assert.match(tag, /tabindex="0"/, id);
    assert.match(tag, /role="button"/, id);
    assert.match(tag, /aria-pressed="false"/, id);
  }
});

test('D0016-AC-09: 履歴の無い節の g は、選べる印を1つも持たない', () => {
  const svg = render(showcaseView().nodes, PICKABLE);
  for (const id of ['input', 'requirements', 'design', 'review:design', 'red', 'review:red', 'test', 'final']) {
    const tag = openTag(svg, id);
    for (const re of PICK_MARKS) assert.doesNotMatch(tag, re, `${id}: ${re}`);
  }
});

test('D0016-AC-09: 節に対応する矢印の id を data-reasons-loop に持つ（実装・判定は send-back、確認は revise:<段>）', () => {
  const svg = render(showcaseView().nodes, PICKABLE);
  assert.match(openTag(svg, 'implement'), /data-reasons-loop="send-back"/);
  assert.match(openTag(svg, 'verdict'), /data-reasons-loop="send-back"/);
  assert.match(openTag(svg, 'review:requirements'), /data-reasons-loop="revise:requirements"/);
  // 指す先の矢印は図の中に本当にある
  assert.match(svg, /data-loop="send-back"/);
  assert.match(svg, /data-loop="revise:requirements"/);
});

test('D0016-AC-09: パイプの確認の節も選べる印を持ち、矢印の id は revise:<段の name>', () => {
  const view = pipeView();
  const svg = render(view.nodes, new Set(['review:survey']));
  const tag = openTag(svg, 'review:survey');
  assert.match(tag, /data-reasons="review:survey"/);
  assert.match(tag, /data-reasons-loop="revise:survey"/);
  assert.match(svg, /data-loop="revise:survey"/);
});

test('D0016-AC-09: 選べる節があると svg は role="group"（role="img" の中には押せるものを置けない）で、aria-label は残る', () => {
  const svg = render(showcaseView().nodes, PICKABLE);
  const open = /^<svg[^>]*>/.exec(svg)![0];
  assert.match(open, /role="group"/);
  assert.doesNotMatch(open, /role="img"/);
  assert.match(open, /aria-label="パイプラインの図：/);
});

test('D0016-AC-09: 選べる節の title（読み上げ・ツールチップ）は今のまま（節の名前と状態）', () => {
  const svg = render(showcaseView().nodes, PICKABLE);
  assert.match(svg, /<g class="node is-done"[^>]*data-node="implement"[^>]*><title>実装：完了<\/title>/);
});

test('D0016-AC-09: 節の id に引用符があっても data-reasons の属性値から外へ出ない（エスケープされる）', () => {
  const evil: PipelineNode = { id: 'review:a"b', label: '確認', status: 'pending', reviseCount: 0, sendBackCount: null, metrics: null };
  const svg = render([evil], new Set([evil.id]));
  assert.match(svg, /data-reasons="review:a&quot;b"/);
  assert.doesNotMatch(svg, /data-reasons="review:a"b/);
});

// ---- 今の作りのままで通る（守り続けるための検査）----

test('D0016-AC-09: pickable が空・省略なら出力は今までと1文字も変わらず、role="img" のまま（守り続ける検査）', () => {
  const nodes = buildPipelineView(snapshot()).nodes;
  const plain = renderFlowSvg(nodes);
  assert.equal(render(nodes, new Set()), plain);
  assert.match(plain, /^<svg class="flow" viewBox="[^"]*" role="img"/);
  for (const re of PICK_MARKS) assert.doesNotMatch(plain, re, String(re));
});

test('D0016-AC-09: 図に無い節の id を pickable に入れても、どの節にも選べる印は付かない（守り続ける検査）', () => {
  const nodes = buildPipelineView(snapshot()).nodes;
  const svg = render(nodes, new Set(['no-such-node']));
  assert.doesNotMatch(svg, /data-reasons=/);
  assert.doesNotMatch(svg, /tabindex=/);
});
