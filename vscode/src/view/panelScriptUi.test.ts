// パネルのスクリプトの画面の操作（D0019・2版目）：絞り込み・状態のタブ・詳細のタブ・描き直しをまたぐ保持（スクロール・入力の焦点と選択範囲・日本語入力の保護）。
// panelScript.ts の PANEL_SCRIPT を node:vm で、偽の DOM（src/test/fakeDom.ts）の上で動かす。
// 絞り込み・タブ・詳細のタブは、パネルの中だけで決める：拡張へメッセージを送らず、保存もしない。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import type { RunListView } from '../domain/runList.ts';
import { bootPanel, extractScript, FakeNode } from '../test/fakeDom.ts';
import type { BootOptions, PanelHarness } from '../test/fakeDom.ts';
import { finishedView } from '../test/liveFixtures.ts';
import { showcaseView } from '../test/reasonFixtures.ts';
import { SID, listView, row, sampleRows } from '../test/runListFixtures.ts';

const NONCE = 'TESTNONCE';
const LIST = listView(sampleRows(), { selected: 'here|survey' });

const boot = (view: PipelineView = finishedView(), list: RunListView = LIST, opts?: BootOptions): PanelHarness => bootPanel(renderPanelHtml(view, NONCE, list), opts);
const render = (h: PanelHarness, view: PipelineView, list: RunListView): void => h.send({ type: 'render', html: renderViewBody(view, list) });

const filterInput = (h: PanelHarness): FakeNode => {
  const el = h.doc.querySelector('input[data-keep="filter"]');
  assert.ok(el, '絞り込みの入力がある');
  return el;
};
const keyOf = (li: FakeNode): string => li.querySelector('button[data-run]')!.getAttribute('data-run')!;
/** いま見えている行の key（文書の順）。行・見出しのどちらかが hidden なら見えない */
const visibleKeys = (h: PanelHarness): string[] =>
  h.doc
    .querySelectorAll('li[data-group]')
    .filter((li) => li.closest('[hidden]') === null)
    .map(keyOf);
const groupShown = (h: PanelHarness, group: string): boolean => {
  const section = h.doc.querySelector(`section[data-group="${group}"]`);
  return section !== null && section.closest('[hidden]') === null;
};
const shownGroups = (h: PanelHarness): string[] => ['waiting', 'running', 'done'].filter((g) => groupShown(h, g));
const emptyNote = (h: PanelHarness): FakeNode => {
  const el = h.doc.querySelector('.run-empty');
  assert.ok(el, '「該当する実行がありません」の要素がある');
  return el;
};
const noteShown = (h: PanelHarness): boolean => emptyNote(h).closest('[hidden]') === null;
const listTab = (h: PanelHarness, name: string): FakeNode => {
  const el = h.doc.querySelector(`button[data-list-tab="${name}"]`);
  assert.ok(el, `状態のタブ ${name}`);
  return el;
};
const selectedListTabs = (h: PanelHarness): string[] =>
  h.doc
    .querySelectorAll('button[data-list-tab]')
    .filter((b) => b.getAttribute('aria-selected') === 'true')
    .map((b) => b.getAttribute('data-list-tab')!);
const counts = (h: PanelHarness): string[] => h.doc.querySelectorAll('button[data-list-tab]').map((b) => h.text(b.querySelector('.count')!));
const detailTab = (h: PanelHarness, name: string): FakeNode => {
  const el = h.doc.querySelector(`button[data-detail-tab="${name}"]`);
  assert.ok(el, `詳細のタブ ${name}`);
  return el;
};
const selectedDetailTabs = (h: PanelHarness): string[] =>
  h.doc
    .querySelectorAll('button[data-detail-tab]')
    .filter((b) => b.getAttribute('aria-selected') === 'true')
    .map((b) => b.getAttribute('data-detail-tab')!);
/** 見えているタブパネルの data-detail-panel の値（diagram 図と出力・artifacts 成果物・tools エージェント・スキル・usage 使用量）。D0047：番号でなく名前で取る */
const shownPanels = (h: PanelHarness): string[] =>
  h.doc
    .querySelectorAll('[role="tabpanel"]')
    .filter((p) => p.closest('[hidden]') === null)
    .map((p) => p.getAttribute('data-detail-panel') ?? '');
const type = (h: PanelHarness, text: string): void => h.typeText(filterInput(h), text);

test('D0019-AC-65: パネルのスクリプトは view/panelScript.ts の PANEL_SCRIPT で、HTML の <script nonce> にそのまま入る。外部の読み込みをしない', async () => {
  const { PANEL_SCRIPT } = await import('./panelScript.ts');
  assert.equal(typeof PANEL_SCRIPT, 'string');
  assert.equal(extractScript(renderPanelHtml(finishedView(), NONCE, LIST)).trim(), PANEL_SCRIPT.trim());
  assert.doesNotMatch(PANEL_SCRIPT, /\bfetch\s*\(|XMLHttpRequest|importScripts|\beval\s*\(|new Function|https?:\/\//);
  assert.match(PANEL_SCRIPT, /acquireVsCodeApi/);
  for (const type of ['ready', 'openArtifact', 'selectRun']) assert.ok(PANEL_SCRIPT.includes(`'${type}'`), `${type} を送る`);
});

// ---- AC-58：絞り込み ----

test('D0019-AC-58: 初めは全部の行が見え、「該当する実行がありません」は隠れている。入力は空', () => {
  const h = boot();
  assert.equal(visibleKeys(h).length, 8);
  assert.equal(noteShown(h), false);
  assert.equal(filterInput(h).value, '');
  assert.deepEqual(shownGroups(h), ['waiting', 'running', 'done']);
});

test('D0019-AC-58: セッション名に含まれる文字で絞れる。大文字小文字を区別しない（qa でも QA でも 同じ行）', () => {
  const h = boot();
  type(h, 'qa');
  assert.deepEqual(visibleKeys(h), ['here|']);
  type(h, 'QA');
  assert.deepEqual(visibleKeys(h), ['here|']);
  type(h, '不具合');
  assert.deepEqual(visibleKeys(h), ['wt.fix-login|']);
  type(h, 'csv');
  assert.deepEqual(visibleKeys(h), ['wt.feat-x|']);
});

test('D0019-AC-58: セッション ID は全部が対象（先頭 8 文字だけでなく、途中の文字でも絞れる）', () => {
  const h = boot();
  type(h, SID.feat);
  assert.deepEqual(visibleKeys(h), ['wt.feat-x|']);
  type(h, '0123456789c3');
  assert.deepEqual(visibleKeys(h), ['here|diagrams']);
  type(h, 'DDDD4444');
  assert.deepEqual(visibleKeys(h), ['wt.fix-login|']);
});

test('D0019-AC-58: ブランチ名で絞れる（大文字小文字を区別しない）。ブランチが同じ行は全部残る', () => {
  const h = boot();
  type(h, 'EXPORT-CSV');
  assert.deepEqual(visibleKeys(h), ['wt.feat-x|']);
  type(h, 'fix/login');
  assert.deepEqual(visibleKeys(h), ['wt.fix-login|']);
  type(h, 'main');
  assert.deepEqual(visibleKeys(h), ['here|', 'here|diagrams', 'here|idle', 'here|survey', 'here|review', 'here|archive/20261016-090000']);
});

test('D0019-AC-58: パイプ名・今の段・状態の言葉は絞り込みの対象にならない（名前・ID・ブランチ名だけ）', () => {
  const h = boot();
  for (const text of ['spec-qa', 'idle-pipe', '図を描く', '確認待ち', '合格']) {
    type(h, text);
    assert.deepEqual(visibleKeys(h), [], text);
    assert.equal(noteShown(h), true, `${text}: 該当なしの文`);
  }
});

test('D0019-AC-58: 残る行の無い見出しは隠れる。どの行も残らなければ「該当する実行がありません」が出て、入力を消すと全部戻る', () => {
  const h = boot();
  type(h, 'ログイン');
  assert.deepEqual(visibleKeys(h), ['wt.fix-login|']);
  assert.deepEqual(shownGroups(h), ['running']);
  assert.equal(noteShown(h), false);
  type(h, '該当しない文字列');
  assert.deepEqual(shownGroups(h), []);
  assert.equal(noteShown(h), true);
  assert.match(h.text(emptyNote(h)), /該当する実行がありません/);
  type(h, '');
  assert.equal(visibleKeys(h).length, 8);
  assert.deepEqual(shownGroups(h), ['waiting', 'running', 'done']);
  assert.equal(noteShown(h), false);
});

test('D0019-AC-58: 状態のタブと一緒に効く（タブで絞った行の中から、文字でさらに絞る）', () => {
  const h = boot();
  listTab(h, 'running').dispatch('click');
  type(h, 'main');
  assert.deepEqual(visibleKeys(h), ['here|diagrams', 'here|idle']);
  listTab(h, 'waiting').dispatch('click');
  assert.deepEqual(visibleKeys(h), ['here|'], '確認待ちの行のうち main のもの');
  listTab(h, 'all').dispatch('click');
  assert.equal(visibleKeys(h).length, 6, 'タブを すべて に戻すと、文字だけで絞る');
});

// ---- AC-59：状態のタブ ----

test('D0019-AC-59: 状態のタブを押すと、その状態の行だけが見える。選んだタブは aria-selected="true" になり、ほかは false', () => {
  const h = boot();
  assert.deepEqual(selectedListTabs(h), ['all']);
  listTab(h, 'waiting').dispatch('click');
  assert.deepEqual(selectedListTabs(h), ['waiting']);
  assert.deepEqual(visibleKeys(h), ['here|', 'wt.feat-x|']);
  assert.deepEqual(shownGroups(h), ['waiting']);
  listTab(h, 'done').dispatch('click');
  assert.deepEqual(selectedListTabs(h), ['done']);
  assert.deepEqual(visibleKeys(h), ['here|survey', 'here|review', 'here|archive/20261016-090000']);
  assert.deepEqual(shownGroups(h), ['done']);
  listTab(h, 'all').dispatch('click');
  assert.deepEqual(selectedListTabs(h), ['all']);
  assert.equal(visibleKeys(h).length, 8);
});

test('D0019-AC-59: 「動いている」のタブには、段の合間で動いていない「待ち」（idle）の行も入る（見出しも同じ）', () => {
  const h = boot();
  listTab(h, 'running').dispatch('click');
  assert.deepEqual(visibleKeys(h), ['here|diagrams', 'wt.fix-login|', 'here|idle']);
  assert.deepEqual(shownGroups(h), ['running']);
});

test('D0019-AC-59: タブの件数は記録の run の数で、絞り込みの文字やタブの選びで変わらない', () => {
  const h = boot();
  assert.deepEqual(counts(h), ['8', '2', '3', '3']);
  type(h, 'qa');
  listTab(h, 'done').dispatch('click');
  assert.deepEqual(counts(h), ['8', '2', '3', '3']);
});

test('D0019-AC-59: 該当する行が無いタブ（その状態の run が無い）を押しても例外を出さず、「該当する実行がありません」が出る', () => {
  const h = boot(finishedView(), listView([row({ key: 'here|a', state: 'done', result: '合格' })]));
  listTab(h, 'waiting').dispatch('click');
  assert.deepEqual(visibleKeys(h), []);
  assert.equal(noteShown(h), true);
});

// ---- AC-62：詳細のタブ ----

test('D0019-AC-62: 詳細のタブは初め「図と出力」が選ばれ、そのパネルだけが見える', () => {
  const h = boot();
  assert.deepEqual(selectedDetailTabs(h), ['diagram']);
  assert.deepEqual(shownPanels(h), ['diagram']);
});

test('D0019-AC-62: 「成果物」「使用量」のタブを押すと、そのパネルだけが見える。「図と出力」に戻せる', () => {
  const h = boot();
  detailTab(h, 'artifacts').dispatch('click');
  assert.deepEqual(selectedDetailTabs(h), ['artifacts']);
  assert.deepEqual(shownPanels(h), ['artifacts']);
  detailTab(h, 'usage').dispatch('click');
  assert.deepEqual(selectedDetailTabs(h), ['usage']);
  assert.deepEqual(shownPanels(h), ['usage']);
  detailTab(h, 'diagram').dispatch('click');
  assert.deepEqual(selectedDetailTabs(h), ['diagram']);
  assert.deepEqual(shownPanels(h), ['diagram']);
});

test('D0019-AC-62: 「成果物を開く」ボタンは「成果物」のタブを選ぶ（メッセージは送らない）', () => {
  const h = boot();
  const open = h.doc.querySelector('button[data-open-artifacts]');
  assert.ok(open, '「成果物を開く」ボタンがある');
  open.dispatch('click');
  assert.deepEqual(selectedDetailTabs(h), ['artifacts']);
  assert.deepEqual(shownPanels(h), ['artifacts']);
  assert.deepEqual(h.posted, [{ type: 'ready' }]);
});

test('D0019-AC-62: 成果物のタブの中のボタンは、今までどおり openArtifact を送る（タブを切り替えても変わらない）', () => {
  const h = boot();
  detailTab(h, 'artifacts').dispatch('click');
  h.doc.querySelectorAll('button[data-artifact]')[0]!.dispatch('click');
  assert.deepEqual(h.posted.map((m) => (m as { type: string }).type), ['ready', 'openArtifact']);
});

// ---- AC-31：タブ・絞り込みの操作はメッセージを送らない ----

test('D0019-AC-31: 絞り込みを打つ・状態のタブを押す・詳細のタブを押す・描き直しを受ける、のどれでも拡張へ送るのは ready だけ', () => {
  const h = boot(showcaseView());
  type(h, 'qa');
  listTab(h, 'waiting').dispatch('click');
  listTab(h, 'all').dispatch('click');
  detailTab(h, 'usage').dispatch('click');
  detailTab(h, 'artifacts').dispatch('click');
  h.doc.querySelector('button[data-open-artifacts]')!.dispatch('click');
  render(h, showcaseView(), LIST);
  assert.deepEqual(h.posted, [{ type: 'ready' }]);
});

// ---- AC-65：描き直しをまたぐ保持 ----

test('D0019-AC-65: 描き直しをまたいで、絞り込みの文字と、それで絞った行が残る（新しい行も同じ絞り込みで出し分けされる）', () => {
  const h = boot();
  type(h, 'qa');
  render(h, finishedView(), LIST);
  assert.equal(filterInput(h).value, 'qa');
  assert.deepEqual(visibleKeys(h), ['here|']);
  const more = listView([...sampleRows(), row({ key: 'here|extra', session: 'QA を足した', state: 'running', sessionId: null })], { selected: 'here|survey' });
  render(h, finishedView(), more);
  assert.deepEqual(visibleKeys(h), ['here|', 'here|extra'], '新しい行にも絞り込みが効く');
  type(h, '該当しない');
  render(h, finishedView(), more);
  assert.equal(noteShown(h), true, '該当なしの文も残る');
});

test('D0019-AC-65: 描き直しをまたいで、状態のタブの選びと、詳細のタブの選びが残る', () => {
  const h = boot();
  listTab(h, 'done').dispatch('click');
  detailTab(h, 'usage').dispatch('click');
  render(h, finishedView(), LIST);
  assert.deepEqual(selectedListTabs(h), ['done']);
  assert.deepEqual(visibleKeys(h), ['here|survey', 'here|review', 'here|archive/20261016-090000']);
  assert.deepEqual(selectedDetailTabs(h), ['usage']);
  assert.deepEqual(shownPanels(h), ['usage']);
});

test('D0019-AC-65: 選んだ run を替える描き直しでも、絞り込み・状態のタブ・詳細のタブ・理由の欄の選びは残る', () => {
  const h = boot(showcaseView());
  type(h, 'main');
  listTab(h, 'all').dispatch('click');
  detailTab(h, 'diagram').dispatch('click');
  h.node('implement').dispatch('click');
  render(h, showcaseView(), listView(sampleRows(), { selected: 'here|' }));
  assert.equal(filterInput(h).value, 'main');
  assert.deepEqual(selectedListTabs(h), ['all']);
  assert.deepEqual(h.doc.querySelectorAll('[data-reasons-for]').filter((s) => !s.hidden).map((s) => s.getAttribute('data-reasons-for')), ['implement']);
});

// スクロールを試すための枠の高さ：一覧 1000/200・図の枠 800/300・出力 600/100・時系列 500/100
const LAYOUT: BootOptions['layout'] = (n) => {
  switch (n.getAttribute('data-scroll')) {
    case 'list':
      return { scrollHeight: 1000, clientHeight: 200 };
    case 'diagram':
      return { scrollHeight: 800, clientHeight: 300 };
    case 'output':
      return { scrollHeight: 600, clientHeight: 100 };
    case 'gantt':
      return { scrollHeight: 500, clientHeight: 100 };
    default:
      return null;
  }
};
const scroller = (h: PanelHarness, name: string): FakeNode => {
  const el = h.doc.querySelector(`[data-scroll="${name}"]`);
  assert.ok(el, `[data-scroll="${name}"] がある`);
  return el;
};
const tops = (h: PanelHarness): Record<string, number> => Object.fromEntries(['list', 'diagram', 'output', 'gantt'].map((n) => [n, scroller(h, n).scrollTop]));

test('D0019-AC-65: 描き直しをまたいで、一覧・図の枠・時系列のスクロール位置が残る。出力は末尾から離れていれば同じ位置に戻る', () => {
  const h = boot(finishedView(), LIST, { layout: LAYOUT });
  scroller(h, 'list').scrollTop = 150;
  scroller(h, 'diagram').scrollTop = 200;
  scroller(h, 'output').scrollTop = 100;
  scroller(h, 'gantt').scrollTop = 50;
  render(h, finishedView(), LIST);
  assert.deepEqual(tops(h), { list: 150, diagram: 200, output: 100, gantt: 50 });
});

test('D0019-AC-65: 出力が末尾近くにあるときは、描き直しのあとも末尾に付いていく（今までの末尾追従）', () => {
  const h = boot(finishedView(), LIST, { layout: LAYOUT });
  scroller(h, 'output').scrollTop = 500; // 最大（600 - 100）
  render(h, finishedView(), LIST);
  assert.equal(scroller(h, 'output').scrollTop, 500);
  render(h, finishedView(), LIST);
  assert.equal(scroller(h, 'output').scrollTop, 500);
});

test('D0019-AC-65: 選んだ run が変わる描き直しでは、図の枠・時系列は先頭から、出力は末尾追従になり、一覧のスクロール位置は残る', () => {
  const h = boot(finishedView(), LIST, { layout: LAYOUT });
  scroller(h, 'list').scrollTop = 150;
  scroller(h, 'diagram').scrollTop = 200;
  scroller(h, 'output').scrollTop = 100;
  scroller(h, 'gantt').scrollTop = 50;
  render(h, finishedView(), listView(sampleRows(), { selected: 'wt.feat-x|' }));
  const after = tops(h);
  assert.equal(after.list, 150, '一覧は残る');
  assert.equal(after.diagram, 0, '図の枠は先頭から');
  assert.equal(after.gantt, 0, '時系列は先頭から');
  assert.equal(after.output, 500, '出力は末尾追従');
});

test('D0019-AC-65: タブを切り替える前に見えている枠の位置を控え、戻したときに戻す（隠れた枠はブラウザが位置を失うため）', () => {
  const h = boot(finishedView(), LIST, { layout: LAYOUT });
  scroller(h, 'diagram').scrollTop = 200;
  scroller(h, 'gantt').scrollTop = 40;
  detailTab(h, 'artifacts').dispatch('click');
  scroller(h, 'diagram').scrollTop = 0; // 隠れている間にブラウザが位置を失った
  scroller(h, 'gantt').scrollTop = 0;
  detailTab(h, 'diagram').dispatch('click');
  assert.equal(scroller(h, 'diagram').scrollTop, 200);
  assert.equal(scroller(h, 'gantt').scrollTop, 40);
});

test('D0019-AC-65: 絞り込みの入力にフォーカスがあるとき、描き直しのあとも同じ入力にフォーカスが戻り、選択範囲も残る', () => {
  const h = boot();
  type(h, 'main');
  const before = filterInput(h);
  before.focus();
  before.setSelectionRange(1, 3);
  render(h, finishedView(), LIST);
  const after = filterInput(h);
  assert.notEqual(after, before, '入力は作り直されている');
  assert.ok(h.doc.activeElement === after, 'フォーカスが新しい入力に戻っていない');
  assert.deepEqual([after.selectionStart, after.selectionEnd], [1, 3]);
  assert.equal(after.value, 'main');
});

test('D0019-AC-65: 状態のタブにフォーカスがあるとき、描き直しのあとも同じタブにフォーカスが戻る。フォーカスがどこにも無ければ奪わない', () => {
  const h = boot();
  const tab = listTab(h, 'done');
  tab.focus();
  tab.dispatch('click');
  render(h, finishedView(), LIST);
  assert.ok(h.doc.activeElement === listTab(h, 'done'), 'フォーカスが同じタブに戻っていない');
  const h2 = boot();
  render(h2, finishedView(), LIST);
  assert.ok(h2.doc.activeElement === null, 'フォーカスを奪っている');
});

test('D0019-AC-65: 日本語入力の変換中（compositionstart〜compositionend）に render が来ても、入力を作り直さず、終わったあとに 1 回だけ（最後の描き直しを）適用する', () => {
  const h = boot();
  const proto = Object.getOwnPropertyDescriptor(FakeNode.prototype, 'innerHTML');
  assert.ok(proto?.set, '偽の DOM の innerHTML の代入口');
  let sets = 0;
  let last = '';
  Object.defineProperty(h.root, 'innerHTML', {
    configurable: true,
    set(this: FakeNode, html: string) {
      sets++;
      last = html;
      proto.set!.call(this, html);
    },
  });
  const input = filterInput(h);
  input.focus();
  input.dispatch('compositionstart');
  h.typeText(input, 'ログ', true);
  const next = listView([...sampleRows(), row({ key: 'here|late', session: 'ログの追加', state: 'running' })], { selected: 'here|survey' });
  render(h, finishedView(), LIST);
  render(h, finishedView(), next);
  assert.equal(sets, 0, '変換中は入力を作り直さない');
  assert.ok(filterInput(h) === input, '同じ入力のまま');
  assert.equal(input.value, 'ログ', '変換中の文字が消えない');
  input.dispatch('compositionend', { data: 'ログ' });
  assert.equal(sets, 1, '終わったあとに 1 回だけ適用する');
  assert.ok(last.includes('here|late'), '最後に来た描き直しを適用する');
  assert.equal(filterInput(h).value, 'ログ');
  assert.deepEqual(visibleKeys(h), ['wt.fix-login|', 'here|late'], '変換した文字で絞り込まれる');
  render(h, finishedView(), next);
  assert.equal(sets, 2, '変換が終わったあとの描き直しはすぐ適用する');
});

test('D0019-AC-65: 変換中でない描き直しはすぐ適用する（保留しない）', () => {
  const h = boot();
  const before = filterInput(h);
  render(h, finishedView(), LIST);
  assert.notEqual(filterInput(h), before, '作り直されている');
});

test('D0019-AC-65: 描き直しで数え上げ（D0017）が続く：タブを切り替えても、描き直しても、タイマーは 1 つだけ', () => {
  const h = boot();
  assert.equal(h.activeIntervals(), 1);
  detailTab(h, 'usage').dispatch('click');
  listTab(h, 'waiting').dispatch('click');
  render(h, finishedView(), LIST);
  assert.equal(h.activeIntervals(), 1);
  assert.ok(h.createdIntervals() >= 1);
});
