// パネルの枠組みの中の「エージェント・スキル」のタブとパネル（D0049）：タブの位置・パネルの属性・図と出力／使用量のパネルが変わらないこと・属性の安全・CSS。
// タブが 4 つになったこと（並びと hidden）は、直した view/shellHtml.test.ts の D0049-AC-28 の 2 件が見る（ここに二重に置かない）。
// ここは、tools のパネルそのものの検査：data-detail-panel="tools"・data-scroll="panel-tools"・成果物と使用量のあいだ・初めは hidden・表が入る。
// 図の状態に tools を足して渡す（表そのものの形は view/toolsHtml.test.ts）。tools の項目を持たない古い写しは、空の文が出る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { PipelineView } from '../domain/pipelineView.ts';
import { parseCss } from '../test/cssBlocks.ts';
import { panelTag, panelsByName } from '../test/panelParts.ts';
import { dangerousAttributes, panelsOf } from '../test/previewText.ts';
import { runningView } from '../test/liveFixtures.ts';
import { showcaseView } from '../test/reasonFixtures.ts';
import { listView, sampleRows } from '../test/runListFixtures.ts';
import { HOSTILE } from '../test/toolsFixtures.ts';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';
import { SHELL_STYLE } from './shellHtml.ts';

interface Row {
  kind: 'agent' | 'skill' | 'tool';
  name: string;
  count: number;
  stages: string[];
  durationSec: number | null;
}
const row = (kind: Row['kind'], name: string, count: number, over: Partial<Row> = {}): Row => ({ kind, name, count, stages: ['調査'], durationSec: null, ...over });
const tools = (rows: Row[], over: object = {}): object => ({
  rows,
  kinds: rows.length,
  total: rows.reduce((s, r) => s + r.count, 0),
  omitted: 0,
  showTime: rows.some((r) => r.durationSec !== null),
  notice: null,
  ...over,
});
const withTools = (view: PipelineView, t: object | null | undefined): PipelineView => ({ ...view, tools: t }) as unknown as PipelineView;
const THREE = tools([row('agent', 'module-reader', 3), row('skill', 'review', 2), row('tool', 'Read', 5)]);
const LIST = listView(sampleRows());
const body = (view: PipelineView): string => renderViewBody(view, LIST);

// ---- AC-27：パネルとタブ ----

test('D0049-AC-27: パネルは data-detail-panel="tools" で、縦の位置を覚える印 data-scroll="panel-tools" を持ち、初めは hidden（見えるのは「図と出力」だけ）', () => {
  const tag = panelTag(body(withTools(runningView(83), THREE)), 'tools');
  assert.match(tag, /role="tabpanel"/);
  assert.match(tag, /\bhidden\b/);
  assert.match(tag, /data-scroll="panel-tools"/);
});

test('D0049-AC-27: tools のパネルは「成果物」と「使用量」のあいだにある（図と出力・成果物・エージェント・スキル・使用量の順）', () => {
  const out = body(withTools(runningView(83), THREE));
  const order = ['diagram', 'artifacts', 'tools', 'usage'].map((name) => out.indexOf(`data-detail-panel="${name}"`));
  assert.ok(order.every((at) => at >= 0), `4 つのパネルがある：${order}`);
  assert.deepEqual([...order].sort((a, b) => a - b), order, 'この順に並ぶ');
});

test('D0049-AC-27: タブのボタンは「エージェント・スキル」で、data-detail-tab="tools"・role="tab"・data-keep="detail-tab:tools"（焦点を戻す印）を持ち、選ばれていない', () => {
  const out = body(withTools(runningView(83), THREE));
  const button = [...out.matchAll(/<button\b[^>]*data-detail-tab="tools"[^>]*>([\s\S]*?)<\/button>/g)][0];
  assert.ok(button, 'data-detail-tab="tools" のボタンがある（まだ作っていない）');
  assert.match(button[0], /role="tab"/);
  assert.match(button[0], /aria-selected="false"/);
  assert.match(button[0], /data-keep="detail-tab:tools"/);
  assert.equal(button[1]!.trim(), 'エージェント・スキル');
});

test('D0049-AC-27: tools のパネルの中に、表の枠（data-scroll="tools-table"・data-keep="tools-table"）と行が入る', () => {
  const panel = panelsByName(body(withTools(runningView(83), THREE))).tools;
  assert.ok(panel !== undefined, 'tools のパネルがある（まだ作っていない）');
  assert.match(panel, /data-scroll="tools-table"/);
  assert.match(panel, /data-keep="tools-table"/);
  for (const name of ['module-reader', 'review', 'Read']) assert.ok(panel.includes(name), name);
});

test('D0049-AC-27: tools の項目を持たない図の状態（古い写し）・null は「表が空」として読み、パネルに空の文が出る（例外を出さない）', () => {
  for (const t of [undefined, null, tools([])]) {
    const panel = panelsByName(body(withTools(runningView(83), t))).tools;
    assert.ok(panel !== undefined, 'tools のパネルがある（まだ作っていない）');
    assert.ok(panel.includes('エージェント・スキル・道具の呼び出しは、まだ記録にありません。'));
  }
});

test('D0049-AC-27: 「図と出力」以外のタブパネルに、図・出力・時系列は入らない。tools のパネルにも入らない', () => {
  const panel = panelsByName(body(withTools(showcaseView(), THREE))).tools;
  assert.ok(panel !== undefined, 'tools のパネルがある（まだ作っていない）');
  assert.doesNotMatch(panel, /class="flow"|class="terminal"|gantt-svg|data-reasons/);
});

// ---- AC-32：図と出力・使用量のパネルは変わらない ----

test('D0049-AC-32: tools のパネルの中身（外から来た文字・段の表示名に data-detail-panel="usage" を入れたものを含む）が変わっても、「図と出力」「使用量」のパネルの HTML（D0025-AC-75 の切り出し）は同じ', () => {
  const evil = '<div class="tabpanel" role="tabpanel" data-detail-panel="usage"';
  // 段の表示名が外から来た文字の行を、使った段の数が 1 つ・3 つ（title が付かない）・4 つ以上（title が付く）の 3 通りで入れる
  const hostile = tools([
    row('tool', HOSTILE[0]!, 1, { stages: [evil, 'a', 'b', 'c'] }),
    row('agent', evil, 1),
    row('skill', HOSTILE[1]!, 1, { stages: [evil] }),
    row('tool', HOSTILE[4]!, 1, { stages: [evil, 'a', 'b'] }),
  ]);
  const base = body(withTools(showcaseView(), THREE));
  assert.ok(base.includes('data-detail-panel="tools"'), 'tools のパネルがある（まだ作っていない）');
  const expected = panelsOf(base);
  assert.equal(panelsOf(body(withTools(showcaseView(), hostile))), expected);
  assert.equal(panelsOf(body(withTools(showcaseView(), tools([])))), expected);
  assert.equal(panelsOf(body(withTools(showcaseView(), null))), expected);
});

test('D0049-AC-32: tools の有る無しで、「図と出力」「成果物」「使用量」のパネルの HTML は変わらない（今のまま通る。守る）', () => {
  const without = panelsByName(body(showcaseView()));
  const withIt = panelsByName(body(withTools(showcaseView(), THREE)));
  for (const name of ['diagram', 'artifacts', 'usage']) assert.equal(withIt[name], without[name], name);
  assert.equal(panelsOf(body(withTools(showcaseView(), THREE))), panelsOf(body(showcaseView())));
});

// ---- AC-36：属性・CSS ----

test('D0049-AC-36: 3 つの種類がそろった図の状態の本体全体で、タグの属性に style・on…・src・href が無い（tools のパネルがあることを先に確かめる）', () => {
  const hostile = tools([row('agent', HOSTILE[0]!, 1, { stages: HOSTILE.slice() }), row('skill', HOSTILE[1]!, 1), row('tool', HOSTILE[4]!, 1)], { notice: 'A', omitted: 2, kinds: 5 });
  for (const t of [THREE, hostile]) {
    const out = body(withTools(showcaseView(), t));
    assert.ok(out.includes('data-detail-panel="tools"'), 'tools のパネルがある（まだ作っていない）');
    assert.deepEqual(dangerousAttributes(out), []);
  }
});

test('D0049-AC-36: パネルの CSS（renderPanelHtml の style）に表の CSS（TOOLS_STYLE）が束ねられている', () => {
  const html = renderPanelHtml(withTools(runningView(83), THREE), 'TESTNONCE', LIST);
  const css = html.match(/<style\b[^>]*>([\s\S]*?)<\/style>/g)?.join('\n') ?? '';
  assert.ok(css.includes('.tools-scroll'), 'CSS に .tools-scroll がある（まだ束ねていない）');
  assert.ok(css.includes('.tools-table'));
});

test('D0049-AC-36: CSP は今のまま（nonce つきの style・script だけ。外部を読み込まない）。tools のパネルを入れても style 属性が増えない（今のまま通る。守る）', () => {
  const html = renderPanelHtml(withTools(runningView(83), THREE), 'TESTNONCE', LIST);
  assert.match(html, /<meta http-equiv="Content-Security-Policy"/);
  assert.doesNotMatch(html.replace(/<style\b[\s\S]*?<\/style>/g, ''), /\sstyle=/i);
  assert.doesNotMatch(html, /https?:\/\//);
});

// ---- 幅の帯とタブの折り返し ----

test('D0049-AC-28: タブが増えても折り返せる：.detail-tabs に flex-wrap: wrap、.detail-tabs button に white-space: nowrap（タブの文字が途中で切れない）', () => {
  const css = parseCss(SHELL_STYLE);
  const bodyOf = (selector: string): string => css.filter((r) => r.media === null && r.selector.split(',').map((s) => s.trim()).includes(selector)).map((r) => r.body).join(';');
  assert.match(bodyOf('.detail-tabs'), /flex-wrap\s*:\s*wrap/);
  assert.match(bodyOf('.detail-tabs button'), /white-space\s*:\s*nowrap/);
});

// 枠組みの @media が 1100px と 800px の 2 つのままであること（タブの折り返しは @media を足さず flex-wrap で足す）は、
// 束ねたあとの CSS 全体を見る既存の panelHtml.test.ts の D0019-AC-67 が見張る（TOOLS_STYLE に @media が無いことは toolsHtml.test.ts）。ここに二重に置かない。
