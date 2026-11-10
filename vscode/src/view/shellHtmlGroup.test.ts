// パネルの並列の枠のログ選び（D0063 の AC-11・AC-12）：右の欄の出力を段ごとに用意し（隠しておく）、枠の中の段の節を押すと切り替える。
// パネルのスクリプト（panelScript.ts の PANEL_SCRIPT）は node:vm で偽の DOM の上で動かす（test/fakeDom.ts）。選びは拡張へ送らず、保存もしない。
// 偽の DOM が扱えるのは、タグ・.クラス・[属性]・[属性=値] の組み合わせだけ（子孫・:not() は扱えない）。スクリプトはこの範囲で書く。
// 赤の理由は「まだ作っていない」：右の欄に data-log-for の欄が無い／節に data-logpick が無い。
// 「今のまま通る。守る」と書いたものは、今の作りで通り、実装のあとも通り続けることを見張る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { emptyListFor, renderShell } from './shellHtml.ts';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';
import { PANEL_SCRIPT } from './panelScript.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { bootPanel } from '../test/fakeDom.ts';
import type { FakeNode, PanelHarness } from '../test/fakeDom.ts';
import { checkEntry } from '../test/checkFixtures.ts';
import { findStorage } from '../test/sourceText.ts';
import { assistantText, logText, promptLine, resultLine } from '../test/fixtures.ts';
import { BASE_AT } from '../test/liveFixtures.ts';
import { GROUP_STAGES, doneLog, gStage, groupView, liveLog, runEntry } from '../test/groupFixtures.ts';

const shell = (view: PipelineView): string => renderShell(view, emptyListFor(view));

/** flow が 2 回（1 回目 02・2 回目 04）、klass が 1 回（03）流れた実行 */
const TWO_RUNS = (): PipelineView =>
  groupView([runEntry('survey', 1), runEntry('flow', 2), runEntry('klass', 3), runEntry('flow', 4)], {
    stageLogs: [doneLog(1, 'survey', null, 'survey 出力'), doneLog(2, 'flow', null, 'flow 1回目'), doneLog(3, 'klass', null, 'klass 出力'), doneLog(4, 'flow', 2, 'flow 2回目')],
  });
/** 同時に動いている実行（klass の通し番号がいちばん大きい） */
const BOTH_RUNNING = (): PipelineView =>
  groupView([runEntry('survey', 1)], { stageLogs: [doneLog(1, 'survey', null), liveLog(2, 'flow'), liveLog(3, 'klass')] });
/** klass はログがまだ無い */
const KLASS_NO_LOG = (): PipelineView => groupView([runEntry('survey', 1), runEntry('flow', 2)], { stageLogs: [doneLog(1, 'survey', null), doneLog(2, 'flow', null, 'flow 出力')] });

/** 右の欄の <section class="pane-output" …> の開きタグから </section> まで */
const paneOf = (html: string, stage: string): string | null =>
  new RegExp(`<section class="pane-output"[^>]*data-log-for="${stage}"[^>]*>[\\s\\S]*?</section>`).exec(html)?.[0] ?? null;
/** 段ごとの欄ではない、既定の欄 */
const defaultPanes = (html: string): string[] => [...html.matchAll(/<section class="pane-output"(?![^>]*data-log-for)[^>]*>[\s\S]*?<\/section>/g)].map((m) => m[0]);
const textLines = (pane: string): string[] => [...pane.matchAll(/<div class="line[^"]*">([^<]*)<\/div>/g)].map((m) => m[1]!);

// ======== AC-11：枠の中の段ごとの隠した出力の欄 ========

test('D0063-AC-11: 枠の中の段ごとに、隠した出力の欄があり、見出しに段の名前と何回目かが出る', () => {
  const html = shell(TWO_RUNS());
  const flow = paneOf(html, 'flow');
  assert.ok(flow !== null, 'flow の欄がある（まだ作っていない）');
  assert.match(flow.slice(0, flow.indexOf('>') + 1), /\bhidden\b/, '選ぶまでは hidden');
  assert.match(flow, /<h2 class="terminal-title">出力：flowの段（2 回目）<\/h2>/, '見出し');
  assert.match(flow, /data-scroll="output"[^>]*data-scroll-name="flow"|data-scroll-name="flow"[^>]*data-scroll="output"/, 'スクロール位置は欄ごとに覚える');
  assert.deepEqual(textLines(flow), ['flow 2回目'], 'いちばん新しい実行の出力だけ');
  const klass = paneOf(html, 'klass');
  assert.ok(klass !== null, 'klass の欄がある');
  assert.match(klass, /出力：klassの段/);
  assert.deepEqual(textLines(klass), ['klass 出力']);
});

test('D0063-AC-11: 枠の外の段（survey・report）の欄は出ない', () => {
  const html = shell(TWO_RUNS());
  assert.equal(paneOf(html, 'survey'), null);
  assert.equal(paneOf(html, 'report'), null);
  assert.equal((html.match(/data-log-for="/g) ?? []).length, 2, '欄は枠の中の段の数だけ');
});

test('D0063-AC-11: ログが無い段の欄は、見出しに「ログなし」と段の名前が出て、出力は空', () => {
  const klass = paneOf(shell(KLASS_NO_LOG()), 'klass');
  assert.ok(klass !== null, 'klass の欄がある（まだ作っていない）');
  assert.match(klass, /<h2 class="terminal-title">出力：klassの段（ログなし）<\/h2>/);
  assert.deepEqual(textLines(klass), []);
});

test('D0063-AC-11: 既定の欄（今までの出力の欄）は 1 つだけあり、隠されず、動いている中でいちばん新しいログのまま。今のまま通る。守る', () => {
  const html = shell(BOTH_RUNNING());
  const panes = defaultPanes(html);
  assert.equal(panes.length, 1);
  assert.doesNotMatch(panes[0]!.slice(0, panes[0]!.indexOf('>') + 1), /hidden/);
  assert.match(panes[0]!, /出力：klassの段/);
  assert.deepEqual(textLines(panes[0]!), ['klassを作業中']);
  assert.match(panes[0]!, /data-scroll="output"/);
  assert.doesNotMatch(panes[0]!, /data-scroll-name/, '既定の欄は名前なし');
});

test('D0063-AC-11: 外から来た文字（段の表示の名前・出力の本文）は欄の中で escapeHtml を通る', () => {
  const evil = '<script>alert(1)</script>';
  const stages = [gStage('survey'), gStage('flow', 'draw', { label: evil }), gStage('klass', 'draw')];
  const log = { fileName: '02_flow.jsonl', text: logText([promptLine('flow', BASE_AT), assistantText('<img src=x onerror=alert(2)>'), resultLine()]) };
  const view = groupView([runEntry('survey', 1), runEntry('flow', 2)], { stages, stageLogs: [log] });
  const html = shell(view);
  const flow = paneOf(html, 'flow');
  assert.ok(flow !== null, 'flow の欄がある（まだ作っていない）');
  assert.ok(!html.includes('<script>alert(1)') && !html.includes('<img'), '生のタグが出ている');
  assert.ok(flow.includes('&lt;script&gt;alert(1)&lt;/script&gt;'), '見出しの表示の名前がエスケープされている');
  assert.ok(flow.includes('&lt;img src=x onerror=alert(2)&gt;'), '出力の本文がエスケープされている');
  assert.ok(!flow.includes('&amp;lt;'), '二重にエスケープされていない');
});

test('D0063-AC-11: 枠の無い記録では、段ごとの欄は出ず、出力の欄は今までの 1 つだけ。今のまま通る。守る', () => {
  const plain = [gStage('survey'), gStage('flow'), gStage('klass')];
  const view = groupView([runEntry('survey', 1), runEntry('flow', 2)], { stages: plain, stageLogs: [doneLog(2, 'flow', null)] });
  const html = shell(view);
  assert.doesNotMatch(html, /data-log-for|data-logpick/);
  assert.equal(defaultPanes(html).length, 1);
  assert.match(html, /<section class="pane-output"><h2 class="terminal-title">出力：flowの段<\/h2>/);
});

// ======== AC-11・AC-12：節を押すと切り替わる（パネルのスクリプトを動かす） ========

const NONCE = 'TESTNONCE';
const boot = (view: PipelineView): PanelHarness => bootPanel(renderPanelHtml(view, NONCE));

/** 節（data-logpick が段の名前の <g>）。無ければ落とす。 */
function logNode(h: PanelHarness, stage: string): FakeNode {
  const found = h.doc.querySelectorAll('[data-logpick]').find((n) => n.getAttribute('data-logpick') === stage);
  assert.ok(found, `data-logpick="${stage}" の節がある（まだ作っていない）`);
  return found;
}
const logPanes = (h: PanelHarness): FakeNode[] => h.doc.querySelectorAll('section').filter((s) => s.hasAttribute('data-log-for'));
const shownLogs = (h: PanelHarness): string[] => logPanes(h).filter((s) => !s.hasAttribute('hidden')).map((s) => s.getAttribute('data-log-for')!);
const defaultPane = (h: PanelHarness): FakeNode => {
  const found = h.doc.querySelectorAll('section').find((s) => s.getAttribute('class') === 'pane-output' && !s.hasAttribute('data-log-for'));
  assert.ok(found, '既定の出力の欄がある');
  return found;
};
const pressed = (n: FakeNode): string | null => n.getAttribute('aria-pressed');

test('D0063-AC-11: 読み込み直後は既定の欄だけが見え、段ごとの欄は隠れ、枠の中の節は押されていない', () => {
  const h = boot(TWO_RUNS());
  assert.equal(logPanes(h).length, 2);
  assert.deepEqual(shownLogs(h), []);
  assert.equal(defaultPane(h).hasAttribute('hidden'), false);
  assert.equal(pressed(logNode(h, 'flow')), 'false');
  assert.equal(pressed(logNode(h, 'klass')), 'false');
});

test('D0063-AC-11: 枠の中の段の節を押すと、その段の欄が見え、既定の欄が隠れる。別の段の節を押すとそちらに替わる', () => {
  const h = boot(TWO_RUNS());
  logNode(h, 'flow').dispatch('click');
  assert.deepEqual(shownLogs(h), ['flow']);
  assert.equal(defaultPane(h).hasAttribute('hidden'), true);
  assert.equal(pressed(logNode(h, 'flow')), 'true');
  assert.ok(logNode(h, 'flow').classList.contains('is-picked'));
  assert.equal(pressed(logNode(h, 'klass')), 'false');
  logNode(h, 'klass').dispatch('click');
  assert.deepEqual(shownLogs(h), ['klass']);
  assert.equal(pressed(logNode(h, 'flow')), 'false');
  assert.equal(pressed(logNode(h, 'klass')), 'true');
  assert.equal(defaultPane(h).hasAttribute('hidden'), true);
});

test('D0063-AC-11: 同じ節をもう一度押すと、いちばん新しいログ（既定の欄）に戻る', () => {
  const h = boot(TWO_RUNS());
  logNode(h, 'flow').dispatch('click');
  logNode(h, 'flow').dispatch('click');
  assert.deepEqual(shownLogs(h), []);
  assert.equal(defaultPane(h).hasAttribute('hidden'), false);
  assert.equal(pressed(logNode(h, 'flow')), 'false');
});

test('D0063-AC-11: 枠の外の節（前の段）を押すと、既定の欄に戻る', () => {
  const h = boot(TWO_RUNS());
  logNode(h, 'flow').dispatch('click');
  const survey = h.doc.querySelectorAll('[data-node]').find((n) => n.getAttribute('data-node') === 'survey');
  assert.ok(survey, 'survey の節がある');
  survey.dispatch('click');
  assert.deepEqual(shownLogs(h), []);
  assert.equal(defaultPane(h).hasAttribute('hidden'), false);
  assert.equal(pressed(logNode(h, 'flow')), 'false');
});

test('D0063-AC-11: キーボード（Enter・Space）でも選べる', () => {
  const h = boot(TWO_RUNS());
  const flow = logNode(h, 'flow');
  assert.equal(flow.dispatch('keydown', { key: 'Enter' }).defaultPrevented, true, 'Enter は既定の動きを止める');
  assert.deepEqual(shownLogs(h), ['flow']);
  logNode(h, 'klass').dispatch('keydown', { key: ' ' });
  assert.deepEqual(shownLogs(h), ['klass']);
  logNode(h, 'klass').dispatch('keydown', { key: 'a' });
  assert.deepEqual(shownLogs(h), ['klass'], '他のキーでは変わらない');
});

test('D0063-AC-11: ログが無い段の節を押すと、「ログなし」の欄が見える', () => {
  const h = boot(KLASS_NO_LOG());
  logNode(h, 'klass').dispatch('click');
  assert.deepEqual(shownLogs(h), ['klass']);
  const title = logPanes(h)
    .find((s) => s.getAttribute('data-log-for') === 'klass')!
    .querySelector('h2');
  assert.match(h.text(title!), /ログなし/);
});

const WITH_CHECK_STAGES = [...GROUP_STAGES.slice(0, 3), gStage('verify', undefined, { check: { on_fail: null, max_retries: 2 } })];
const WITH_CHECK = (): PipelineView =>
  groupView(
    [runEntry('survey', 1), runEntry('flow', 2), runEntry('klass', 3), runEntry('verify', 4), checkEntry({ stage: 'verify', status: 'fail', attempt: 1, summary: '直す点あり' })],
    { stages: WITH_CHECK_STAGES, stageLogs: [doneLog(2, 'flow', null), doneLog(3, 'klass', null)] },
  );
const reasonsPane = (h: PanelHarness): FakeNode => {
  const found = h.doc.querySelectorAll('[data-reasons-for]').find((s) => s.getAttribute('data-reasons-for') === 'check:verify');
  assert.ok(found, '判定の節の理由の欄がある');
  return found;
};
const checkNode = (h: PanelHarness): FakeNode => {
  const found = h.doc.querySelectorAll('[data-reasons]').find((n) => n.getAttribute('data-reasons') === 'check:verify');
  assert.ok(found, '判定の節がある');
  return found;
};

test('D0063-AC-11: 判定の節の理由の選びと、段のログの選びは排他（どちらかを選ぶともう一方は外れる）', () => {
  const h = boot(WITH_CHECK());
  logNode(h, 'flow').dispatch('click');
  assert.deepEqual(shownLogs(h), ['flow']);
  assert.equal(reasonsPane(h).hasAttribute('hidden'), true);
  checkNode(h).dispatch('click');
  assert.equal(reasonsPane(h).hasAttribute('hidden'), false, '理由の欄が見える');
  assert.deepEqual(shownLogs(h), [], '段のログの選びは外れる');
  assert.equal(defaultPane(h).hasAttribute('hidden'), false);
  assert.equal(pressed(logNode(h, 'flow')), 'false');
  logNode(h, 'klass').dispatch('click');
  assert.deepEqual(shownLogs(h), ['klass']);
  assert.equal(reasonsPane(h).hasAttribute('hidden'), true, '理由の選びは外れる');
  assert.equal(pressed(checkNode(h)), 'false');
});

// ======== AC-12：選びは拡張へ送らず保存しない・描き直しをまたぐ・枠の中にない選びは捨てる ========

test('D0063-AC-12: 選んでも拡張へメッセージを送らない（送るのは起動時の ready だけ）', () => {
  const h = boot(TWO_RUNS());
  logNode(h, 'flow').dispatch('click');
  logNode(h, 'klass').dispatch('keydown', { key: 'Enter' });
  logNode(h, 'klass').dispatch('click');
  assert.deepEqual(h.posted, [{ type: 'ready' }]);
});

test('D0063-AC-12: 描き直し（同じ内容の render）をまたいで、選びが残る', () => {
  const view = TWO_RUNS();
  const h = boot(view);
  logNode(h, 'flow').dispatch('click');
  h.send({ type: 'render', html: renderViewBody(view) });
  assert.deepEqual(shownLogs(h), ['flow']);
  assert.equal(pressed(logNode(h, 'flow')), 'true');
  assert.equal(defaultPane(h).hasAttribute('hidden'), true);
});

test('D0063-AC-12: 描き直しのあと、選んだ段が枠の中にない（枠の無い記録になった）なら、選びを捨てて既定のログを出す', () => {
  const h = boot(TWO_RUNS());
  logNode(h, 'flow').dispatch('click');
  const plain = [gStage('survey'), gStage('flow'), gStage('klass'), gStage('report')];
  const old = groupView([runEntry('survey', 1), runEntry('flow', 2)], { stages: plain, stageLogs: [doneLog(2, 'flow', null)] });
  h.send({ type: 'render', html: renderViewBody(old) });
  assert.equal(logPanes(h).length, 0);
  assert.equal(h.doc.querySelectorAll('[data-logpick]').length, 0);
  assert.equal(defaultPane(h).hasAttribute('hidden'), false);
  // 枠のある記録に戻っても、前の選びは戻らない
  h.send({ type: 'render', html: renderViewBody(TWO_RUNS()) });
  assert.deepEqual(shownLogs(h), []);
});

test('D0063-AC-12: 選んでいる間に新しい出力で描き直されても、選んだログを出し続ける（既定に勝手に戻らない）', () => {
  const h = boot(BOTH_RUNNING());
  logNode(h, 'flow').dispatch('click');
  const later = groupView([runEntry('survey', 1)], { stageLogs: [doneLog(1, 'survey', null), liveLog(2, 'flow', null, 'flow 新しい出力'), liveLog(3, 'klass', null, 'klass 新しい出力')] });
  h.send({ type: 'render', html: renderViewBody(later) });
  assert.deepEqual(shownLogs(h), ['flow']);
  const text = h.text(logPanes(h).find((s) => s.getAttribute('data-log-for') === 'flow')!);
  assert.match(text, /flow 新しい出力/);
});

test('D0063-AC-12: パネルのスクリプトは段のログの選びを変数で持ち（data-logpick・pickedLog）、拡張へ送るメッセージは 4 種類（ready・openArtifact・selectRun と、D0079 で足した reply）', () => {
  assert.match(PANEL_SCRIPT, /data-logpick/, 'スクリプトが data-logpick を扱う（まだ作っていない）');
  assert.match(PANEL_SCRIPT, /\bpickedLog\b/, 'pickedLog の変数（まだ作っていない）');
  const types = [...PANEL_SCRIPT.matchAll(/postMessage\(\{\s*type:\s*'([^']+)'/g)].map((m) => m[1]);
  assert.deepEqual([...new Set(types)].sort(), ['openArtifact', 'ready', 'reply', 'selectRun']);
});

test('D0063-AC-12: パネルのスクリプトは保存の道（workspaceState・getState・setState・localStorage など）を使わない。今のまま通る。守る', () => {
  assert.deepEqual(findStorage(PANEL_SCRIPT), []);
});
