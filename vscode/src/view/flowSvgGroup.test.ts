// 図（SVG）の並列の枠（D0063 の AC-08〜10）：枠の要素と名前の札・中の段の節の座標・枠の前後の矢印・色の取り方・外から来た文字。
// 画面の見え方そのもの（色・重なり・押したときの動き）は画面の確認（run-panel-group-*。手順は .claude/skills/pipe-in/screen-check.md）で見る。ここは形の下地。
// renderFlowSvg の第 4 引数 frames（PipelineView.frames）は、実装の段で型に入るまで、型に頼らず渡す（cast）。
// frameStyle.ts は、実装の段で入るまで、有無を確かめてから読み込む（test/needModule.ts）。
// 赤の理由は「まだ描いていない」：枠の <g class="frame…"> が SVG に無い（frameG が「枠がある」で落とす）／矢印の数が枠なしのまま。
// 「今のまま通る。守る」と書いたものは、今の作りで通り、実装のあとも通り続けることを見張る（枠なしの SVG が変わらないなど）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { reasonNodeIds } from '../domain/pipelineView.ts';
import type { PipelineNode, PipelineView } from '../domain/pipelineView.ts';
import { renderFlowSvg } from './flowSvg.ts';
import { renderPanelHtml } from './panelHtml.ts';
import { renderPipeEditorHtml } from './pipeEditorHtml.ts';
import { nodeG } from '../test/budgetFixtures.ts';
import { extractCss, parseCss } from '../test/cssBlocks.ts';
import { needModule } from '../test/needModule.ts';
import { GROUP_STAGES, GROUP_STAGES_4, framesOf, gStage, groupView, runEntry } from '../test/groupFixtures.ts';
import type { FrameLike } from '../test/groupFixtures.ts';

type RenderWithFrames = (nodes: PipelineNode[], pickable: ReadonlySet<string>, stale: number | null, frames?: readonly FrameLike[]) => string;
const render = renderFlowSvg as unknown as RenderWithFrames;

/** 図の SVG（枠は view.frames から渡す。nodes・frames は差し替えられる） */
function svgOf(view: PipelineView, over: { nodes?: PipelineNode[]; frames?: readonly FrameLike[] } = {}): string {
  return render(over.nodes ?? view.nodes, new Set(reasonNodeIds(view)), null, over.frames ?? framesOf(view));
}

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}
const num = (g: string, attr: string): number => Number(new RegExp(`\\b${attr}="(-?[\\d.]+)"`).exec(g)?.[1] ?? Number.NaN);
const boxOf = (tag: string): Box => ({ x: num(tag, 'x'), y: num(tag, 'y'), w: num(tag, 'width'), h: num(tag, 'height') });

/** 枠の <g class="frame…" data-frame="名前">…</g>（中に <g> は入れ子にならない）。無ければ落とす。 */
function frameG(svg: string, name: string): string {
  const m = new RegExp(`<g class="frame[^"]*" data-frame="${name}">[\\s\\S]*?</g>`).exec(svg);
  assert.ok(m !== null, `枠 ${name} の <g class="frame…" data-frame="${name}"> がある（まだ描いていない）`);
  return m[0];
}
/** 枠の中の部品（class を持つ <rect>）の位置と大きさ */
function frameRect(g: string, cls: string): Box {
  const m = new RegExp(`<rect class="${cls}"[^>]*/>`).exec(g);
  assert.ok(m !== null, `枠に <rect class="${cls}"> がある`);
  return boxOf(m[0]);
}
/** 節の外形（<rect class="shape…">）の位置と大きさ */
function shapeOf(svg: string, id: string): Box {
  const m = /<rect class="shape[^"]*"[^>]*\/>/.exec(nodeG(svg, id));
  assert.ok(m !== null, `節 ${id} に外形の <rect> がある`);
  return boxOf(m[0]);
}
const inside = (inner: Box, outer: Box): boolean =>
  inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.w <= outer.x + outer.w && inner.y + inner.h <= outer.y + outer.h;

interface Edge {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  cls: string;
}
const edgesOf = (svg: string): Edge[] =>
  [...svg.matchAll(/<line class="(edge[^"]*)"[^>]*>/g)].map((m) => ({
    cls: m[1]!,
    x1: num(m[0], 'x1'),
    y1: num(m[0], 'y1'),
    x2: num(m[0], 'x2'),
    y2: num(m[0], 'y2'),
  }));
const viewBoxWidth = (svg: string): number => Number(/viewBox="0 0 ([\d.]+) /.exec(svg)?.[1] ?? Number.NaN);

// ======== AC-08：枠の要素・名前の札・中の段の節の座標 ========

test('D0063-AC-08: 枠の要素（枠の線・名前の札・札の文字）が入り、状態のクラスと名前を持つ', () => {
  const view = groupView([runEntry('survey', 1)]);
  const g = frameG(svgOf(view), 'draw');
  assert.match(g, /^<g class="frame is-pending" data-frame="draw">/, '状態のクラス（まだ）');
  assert.match(g, /<rect class="frame-box"[^>]*\brx="24"/, '角丸 24 の枠の線（作業台と同じ）');
  const tab = frameRect(g, 'frame-tab');
  const box = frameRect(g, 'frame-box');
  assert.ok(tab.x >= box.x && tab.x + tab.w <= box.x + box.w, '札は枠の左右の中');
  assert.ok(tab.y < box.y && tab.y + tab.h > box.y, '札は枠の上辺にかかる（左上の名前の札）');
  assert.match(g, /<text class="frame-tab-text"[^>]*>draw<\/text>/, '札の文字は枠の名前');
  assert.match(g, /<title>[^<]*draw[^<]*<\/title>/, '読み上げ用の <title> に名前が入る');
});

test('D0063-AC-08: 枠の状態が running／done／failed のとき、枠のクラスが変わる', () => {
  const running = groupView([runEntry('survey', 1)], { stageLogs: [] });
  assert.match(frameG(svgOf(running), 'draw'), /class="frame is-pending"/);
  const done = groupView([runEntry('survey', 1), runEntry('flow', 2), runEntry('klass', 3)]);
  assert.match(frameG(svgOf(done), 'draw'), /class="frame is-done"/);
  const asRunning = svgOf(running, { frames: framesOf(running)?.map((f) => ({ ...f, status: 'running' })) });
  assert.match(frameG(asRunning, 'draw'), /class="frame is-running"/);
  const asFailed = svgOf(running, { frames: framesOf(running)?.map((f) => ({ ...f, status: 'failed' })) });
  assert.match(frameG(asFailed, 'draw'), /class="frame is-failed"/);
});

test('D0063-AC-08: 中の段の節がその枠の内側の座標に置かれ、横に並ぶ。枠の外の節は枠の上・下にある', () => {
  const view = groupView([runEntry('survey', 1)]);
  const svg = svgOf(view);
  const box = frameRect(frameG(svg, 'draw'), 'frame-box');
  const flow = shapeOf(svg, 'flow');
  const klass = shapeOf(svg, 'klass');
  assert.ok(inside(flow, box), `flow が枠の内側: ${JSON.stringify({ flow, box })}`);
  assert.ok(inside(klass, box), `klass が枠の内側: ${JSON.stringify({ klass, box })}`);
  assert.equal(flow.y, klass.y, '同じ行に並ぶ（横並び）');
  assert.ok(flow.x + flow.w <= klass.x, `flow が左・klass が右で重ならない: ${JSON.stringify({ flow, klass })}`);
  const survey = shapeOf(svg, 'survey');
  const report = shapeOf(svg, 'report');
  assert.ok(survey.y + survey.h <= box.y, '前の段は枠の上');
  assert.ok(report.y >= box.y + box.h, '次の段は枠の下');
});

test('D0063-AC-08: 枠の中が 4 段のとき、4 段目は 2 行目に折り返す（1〜3 段目は同じ行）。すべて枠の内側', () => {
  const view = groupView([runEntry('survey', 1)], { stages: GROUP_STAGES_4 });
  const svg = svgOf(view);
  const box = frameRect(frameG(svg, 'draw'), 'frame-box');
  const [a, b, c, d] = ['a', 'b', 'c', 'd'].map((id) => shapeOf(svg, id)) as [Box, Box, Box, Box];
  assert.equal(a.y, b.y);
  assert.equal(b.y, c.y);
  assert.ok(a.x < b.x && b.x < c.x, '左から順');
  assert.ok(d.y >= a.y + a.h, `4 段目は 1 行目の下: ${JSON.stringify({ a, d })}`);
  for (const [id, shape] of [['a', a], ['b', b], ['c', c], ['d', d]] as const) assert.ok(inside(shape, box), `${id} が枠の内側`);
  assert.ok(shapeOf(svg, 'report').y >= box.y + box.h, '次の段は枠の下');
});

test('D0063-AC-08: 枠が図の幅の中に収まる（左右にはみ出さない）', () => {
  const cases: readonly (readonly [string, typeof GROUP_STAGES])[] = [
    ['draw', GROUP_STAGES],
    ['draw', GROUP_STAGES_4],
    ['solo', [gStage('a', 'solo')]],
  ];
  for (const [name, stages] of cases) {
    const svg = svgOf(groupView([], { stages }));
    const box = frameRect(frameG(svg, name), 'frame-box');
    assert.ok(box.x >= 0, `枠の左端が 0 以上: ${box.x}`);
    assert.ok(box.x + box.w <= viewBoxWidth(svg), `枠の右端が viewBox の幅の中: ${box.x + box.w} <= ${viewBoxWidth(svg)}`);
  }
});

test('D0063-AC-08: 枠の中の段の節は、細い形で表示名と状態の印を持ち、全文は <title> に入る', () => {
  const view = groupView([runEntry('survey', 1), runEntry('flow', 2)], { stages: [gStage('survey'), gStage('flow', 'draw', { label: 'とても長い名前の段のフロー' }), gStage('klass', 'draw')] });
  const svg = svgOf(view);
  const g = nodeG(svg, 'flow');
  assert.ok(shapeOf(svg, 'flow').w <= 110, `枠の中の節は枠の外の節（幅 176）より細い: ${shapeOf(svg, 'flow').w}`);
  assert.match(g, /<title>[^<]*とても長い名前の段のフロー[^<]*完了[^<]*<\/title>/, '<title> に全文と状態の言葉');
  assert.match(g, /✓/, '状態の印');
  assert.match(g, /data-node="flow"/);
});

test('D0063-AC-08: 枠の無い記録の SVG は、frames を省いても空にしても渡さなくても同じで、枠の要素・ずらしの包みが無い。今のまま通る。守る', () => {
  const stages = [gStage('survey'), gStage('flow'), gStage('klass'), gStage('report')];
  const view = groupView([runEntry('survey', 1), runEntry('flow', 2)], { stages });
  const pick = new Set(reasonNodeIds(view));
  const omitted = renderFlowSvg(view.nodes, pick, null);
  assert.equal(render(view.nodes, pick, null, []), omitted, 'frames が空');
  assert.equal(render(view.nodes, pick, null, undefined), omitted, 'frames が undefined');
  assert.doesNotMatch(omitted, /data-frame|class="frame|frame-box|frame-tab/);
  assert.doesNotMatch(omitted, /<g transform="translate/, 'ずらしの包みは枠があるときだけ');
  assert.match(omitted, /viewBox="0 0 320 /, '幅は今までの 320');
});

// ======== AC-09：枠の前後の矢印 ========

test('D0063-AC-09: 枠の前後に矢印が 1 本ずつ、枠の中の段どうしには矢印がない', () => {
  const view = groupView([runEntry('survey', 1)]);
  const svg = svgOf(view);
  const box = frameRect(frameG(svg, 'draw'), 'frame-box');
  const cx = box.x + box.w / 2;
  const edges = edgesOf(svg);
  // 単位は 依頼メモ・survey・枠・report・完了 の 5 つなので、矢印は 4 本
  assert.equal(edges.length, 4, `矢印の数: ${JSON.stringify(edges)}`);
  const entering = edges.filter((e) => Math.abs(e.y2 - (box.y - 2)) <= 2 && Math.abs(e.x2 - cx) <= 1);
  const leaving = edges.filter((e) => Math.abs(e.y1 - (box.y + box.h)) <= 1 && Math.abs(e.x1 - cx) <= 1);
  assert.equal(entering.length, 1, `枠の入口（上辺の中央）に着く矢印が 1 本: ${JSON.stringify(edges)}`);
  assert.equal(leaving.length, 1, `枠の出口（下辺の中央）から出る矢印が 1 本: ${JSON.stringify(edges)}`);
  const within = edges.filter((e) => e.y1 > box.y && e.y2 < box.y + box.h);
  assert.deepEqual(within, [], '枠の中の段どうしには矢印を引かない');
  assert.match(svg, /marker-end="url\(#mk-edge\)"/, '矢じりは今までと同じ');
});

test('D0063-AC-09: 枠の中が 4 段（折り返し）でも、枠の前後の矢印は 1 本ずつで、中に矢印は無い', () => {
  const view = groupView([runEntry('survey', 1)], { stages: GROUP_STAGES_4 });
  const svg = svgOf(view);
  const box = frameRect(frameG(svg, 'draw'), 'frame-box');
  const edges = edgesOf(svg);
  assert.equal(edges.length, 4, JSON.stringify(edges));
  assert.deepEqual(edges.filter((e) => e.y1 > box.y && e.y2 < box.y + box.h), []);
});

test('D0063-AC-09: 枠の中の段に判定があるとき、段からその判定の節への短い矢印が 1 本だけ枠の中にある（段どうしではない）', () => {
  const stages = [gStage('survey'), gStage('flow', 'draw', { check: { on_fail: null, max_retries: 2 } }), gStage('klass', 'draw'), gStage('report')];
  const view = groupView([runEntry('survey', 1)], { stages });
  const svg = svgOf(view);
  const box = frameRect(frameG(svg, 'draw'), 'frame-box');
  assert.ok(inside(shapeOf(svg, 'check:flow'), box), '判定の節も枠の内側');
  const within = edgesOf(svg).filter((e) => e.y1 > box.y && e.y2 < box.y + box.h);
  assert.equal(within.length, 1, `枠の中の矢印は 1 本: ${JSON.stringify(within)}`);
  const flow = shapeOf(svg, 'flow');
  assert.ok(Math.abs(within[0]!.x1 - within[0]!.x2) <= 1, '縦の短い矢印');
  assert.ok(Math.abs(within[0]!.x1 - (flow.x + flow.w / 2)) <= 1, 'flow の真下から出る');
  const total = edgesOf(svg).filter((e) => !(e.y1 > box.y && e.y2 < box.y + box.h));
  assert.equal(total.length, 4, '枠の外側の矢印は前後の 4 本');
});

test('D0063-AC-09: 枠の中に動いている段があるとき、枠へ入る矢印にだけ流れる点の印（is-flowing）が付く', () => {
  const view = groupView([runEntry('survey', 1)]);
  const nodes = view.nodes.map((n) => (n.id === 'flow' ? { ...n, status: 'running' as const, runningSec: 12 } : n));
  const svg = svgOf(view, { nodes });
  const box = frameRect(frameG(svg, 'draw'), 'frame-box');
  const edges = edgesOf(svg);
  const entering = edges.find((e) => Math.abs(e.y2 - (box.y - 2)) <= 2);
  const leaving = edges.find((e) => Math.abs(e.y1 - (box.y + box.h)) <= 1);
  assert.ok(entering?.cls.includes('is-flowing'), `枠へ入る矢印: ${entering?.cls}`);
  assert.ok(!leaving?.cls.includes('is-flowing'), `枠から出る矢印: ${leaving?.cls}`);
});

test('D0063-AC-09: 枠の無い記録の矢印は、節と節の間に 1 本ずつ（今のまま）。今のまま通る。守る', () => {
  const stages = [gStage('survey'), gStage('flow'), gStage('klass'), gStage('report')];
  const svg = renderFlowSvg(groupView([], { stages }).nodes);
  assert.equal(edgesOf(svg).length, 5, '節 6 個 → 矢印 5 本');
});

// ======== AC-10：色は --par から・外から来た文字は escapeHtml ========

test('D0063-AC-10: 枠の色の定数 PAR_COLOR が frameStyle.ts にあり、値は作業台の --par と同じ', async () => {
  const mod = await needModule<{ PAR_COLOR?: unknown }>(import.meta.url, './frameStyle.ts');
  assert.equal(mod.PAR_COLOR, 'var(--vscode-charts-green)');
});

test('D0063-AC-10: 作業台とパネルの CSS はどちらも --par を PAR_COLOR から取り、色の値を別々に持たない', async () => {
  await needModule(import.meta.url, './frameStyle.ts');
  const read = (name: string): string => readFileSync(fileURLToPath(new URL(name, import.meta.url)), 'utf8');
  for (const name of ['./pipeEditorHtml.ts', './panelHtml.ts']) {
    const text = read(name);
    assert.match(text, /--par:\s*\$\{PAR_COLOR\}/, `${name} は --par を \${PAR_COLOR} で定義する`);
    assert.match(text, /from '\.\/frameStyle\.ts'/, `${name} は frameStyle.ts を読む`);
    assert.doesNotMatch(text, /--par:\s*var\(/, `${name} に --par の色の直書きがある`);
  }
  // --par を定義するのはこの 2 つだけ（ほかの view/*.ts に色を持たない）
  const dir = fileURLToPath(new URL('.', import.meta.url));
  const definers = readdirSync(dir)
    .filter((f) => f.endsWith('.ts') && !f.endsWith('.test.ts'))
    .filter((f) => /--par:/.test(readFileSync(`${dir}${f}`, 'utf8')))
    .sort();
  assert.deepEqual(definers, ['panelHtml.ts', 'pipeEditorHtml.ts']);
});

test('D0063-AC-10: 実行パネルの CSS は .flow に --par を 1 か所だけ定義し、枠の線・札はその --par から色を取る', async () => {
  const mod = await needModule<{ PAR_COLOR: string }>(import.meta.url, './frameStyle.ts');
  const html = renderPanelHtml(groupView([]), 'NONCE');
  const rules = parseCss(extractCss(html));
  const definers = rules.filter((r) => /--par\s*:/.test(r.body));
  assert.equal(definers.length, 1, `--par を定義する規則は 1 つ: ${definers.map((r) => r.selector).join(' | ')}`);
  assert.equal(definers[0]!.selector, '.flow');
  assert.match(definers[0]!.body, new RegExp(`--par:\\s*${mod.PAR_COLOR.replace(/[()]/g, '\\$&')}`));
  const box = rules.find((r) => r.selector === '.flow .frame-box');
  assert.ok(box !== undefined, '.flow .frame-box の規則がある');
  assert.match(box.body, /stroke:\s*var\(--par\)/);
  assert.doesNotMatch(box.body, /#[0-9a-f]{3,8}\b|rgb\(|vscode-charts-green/i, '色の直書きがない');
  const tab = rules.filter((r) => /frame-tab/.test(r.selector));
  assert.ok(tab.length >= 1, '札の規則がある');
  for (const r of tab) assert.doesNotMatch(r.body, /#[0-9a-f]{3,8}\b|rgb\(|vscode-charts-green/i, `札の規則に色の直書き: ${r.selector}`);
});

test('D0063-AC-10: 作業台の --par の見た目は今のまま（var(--vscode-charts-green)）。今のまま通る。守る', () => {
  const html = renderPipeEditorHtml({ nonce: 'N', scriptUri: 'vscode-resource:/x.js', cspSource: 'vscode-resource:' });
  assert.match(html, /--par:\s*var\(--vscode-charts-green\);/);
});

test('D0063-AC-10: 枠の名前・段の名前・表示の名前の外から来た文字は escapeHtml を通り、生のタグも二重のエスケープも出ない', () => {
  const evil = '<script>alert(1)</script>';
  const stages = [gStage('survey'), gStage('flow', 'draw', { label: evil }), gStage('klass', 'draw')];
  const view = groupView([runEntry('survey', 1)], { stages });
  const frames = framesOf(view)?.map((f) => ({ ...f, name: '<b>x</b>' }));
  const svg = svgOf(view, { frames });
  assert.ok(!svg.includes('<script>') && !svg.includes('<b>'), '生のタグが出ている');
  assert.ok(svg.includes('data-frame="&lt;b&gt;x&lt;/b&gt;"'), '枠の名前が属性に 1 回だけエスケープされて入る');
  assert.ok(svg.includes('&lt;b&gt;x&lt;/b&gt;</text>'), '札の文字が 1 回だけエスケープされる');
  assert.ok(svg.includes('&lt;script&gt;alert(1)&lt;/script&gt;'), '段の表示の名前の全文が <title> に 1 回だけエスケープされて入る');
  assert.ok(!svg.includes('&amp;lt;'), '二重にエスケープされていない');
});

test('D0063-AC-10: 押せる印（data-logpick）の段の名前に引用符があっても、属性から外れない', () => {
  const view = groupView([runEntry('survey', 1)]);
  const evilId = 'x" onmouseover="alert(1)';
  const nodes = view.nodes.map((n) => (n.id === 'flow' ? { ...n, id: evilId } : n));
  const frames = framesOf(view)?.map((f) => ({ ...f, members: f.members.map((m) => (m === 'flow' ? evilId : m)), nodeIds: f.nodeIds.map((m) => (m === 'flow' ? evilId : m)) }));
  const svg = svgOf(view, { nodes, frames });
  assert.ok(!svg.includes('onmouseover="alert(1)"'), '属性が外れて生の onmouseover が出ている');
  assert.ok(svg.includes('data-logpick="x&quot; onmouseover=&quot;alert(1)"'), 'data-logpick の値の引用符がエスケープされている（まだ付けていない）');
});

// ======== 押せる印（data-logpick。ログを選ぶ元。AC-11 の下地） ========

test('D0063-AC-11: 枠の中の段の節に data-logpick が付き（押せる・キーボードで届く）、枠の外の節・枠そのものには付かない', () => {
  const view = groupView([runEntry('survey', 1)]);
  const svg = svgOf(view);
  for (const id of ['flow', 'klass']) {
    const g = nodeG(svg, id);
    assert.match(g, new RegExp(`data-logpick="${id}"`), `${id} に data-logpick`);
    assert.match(g, /tabindex="0"/);
    assert.match(g, /role="button"/);
    assert.match(g, /aria-pressed="false"/);
    assert.doesNotMatch(g, /data-reasons/, '理由の欄の選びとは別');
  }
  for (const id of ['input', 'survey', 'report', 'final']) assert.doesNotMatch(nodeG(svg, id), /data-logpick/, `${id} には付かない`);
  assert.doesNotMatch(frameG(svg, 'draw'), /data-logpick|tabindex|role="button"/, '枠自体は押せない');
});

test('D0063-AC-11: 枠を渡さないとき（枠の無い記録）は、どの節にも data-logpick が付かない。今のまま通る。守る', () => {
  const view = groupView([runEntry('survey', 1)]);
  assert.doesNotMatch(renderFlowSvg(view.nodes), /data-logpick/);
});
