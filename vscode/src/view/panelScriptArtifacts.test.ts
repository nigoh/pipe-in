// 「成果物」タブのパネルのスクリプトの動き（D0025）：選び・スクロール・焦点・選んだ行へ寄せる・見る実行が替わったとき既定に戻る・「まだない」行・メッセージ。
// panelScript.ts の PANEL_SCRIPT を node:vm で、偽の DOM（src/test/fakeDom.ts）の上で動かす。本物の時間は使わない（sleep しない）。
// 偽の DOM は、本物と同じに、閉じていない引用符などのセレクタで SyntaxError を投げ（名前をセレクタに連ねた書き方を見つけられる）、
// hidden にした節の中の枠のスクロール位置を 0 に戻し（別のタブへ移って戻るテストが、本当に記憶で戻っていることを見分けられる）、
// offsetTop・offsetHeight を layout で決められる（選んだ行を枠の中へ寄せる動きを試せる）。
// hidden の中では、本物の display: none と同じに、大きさ（offsetTop・offsetHeight・scrollHeight・clientHeight）が 0、スクロール位置の書き込みは残らず、focus() も効かない
// （成果物のタブのパネルは初めから hidden なので、起動時の寄せは空振りする。見えたときに寄せ直す実装だけが緑になる）。
// 成果物の一覧の項目（domain/artifacts.ts の ArtifactEntry）は手で組み立て、図の状態（runningView）の artifacts と動いている段・確認待ちの段を差し替えて渡す
// （パネルのスクリプトだけを確かめる。名前の特別な文字をまとめて試すので、項目を直に渡す。" は記録から作れるが、\ は output に入れられず記録から作れない）。
// 拡張は選びを持たない：パネルのスクリプトの変数だけで持つ。render が届かない場合（世代で捨てられる読み込み）は拡張側の話（D0024）で、ここは「render が届いたら」を前提にする。
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { PipelineView } from '../domain/pipelineView.ts';
import type { RunListView } from '../domain/runList.ts';
import { bootPanel, FakeNode } from '../test/fakeDom.ts';
import type { BootOptions, PanelHarness } from '../test/fakeDom.ts';
import { runningView } from '../test/liveFixtures.ts';
import { listView, row } from '../test/runListFixtures.ts';
import { callArgs, findSelectorConcat, findStorage, withoutComments } from '../test/sourceText.ts';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';

const NONCE = 'TESTNONCE';
const HERE = path.dirname(fileURLToPath(import.meta.url));

// ---- 項目の組み立て ----

interface Entry {
  name: string;
  label: string;
  stage: string | null;
  stageLabel: string | null;
  ready: boolean;
  text: string;
  cut: boolean;
  updatedText: string;
}
interface Live {
  running?: string | null;
  pending?: string | null;
}
const ready = (name: string, label: string = name, over: Partial<Entry> = {}): Entry => ({
  name,
  label,
  stage: null,
  stageLabel: null,
  ready: true,
  text: `本文 ${name}`,
  cut: false,
  updatedText: '10/17 10:05',
  ...over,
});
const missing = (name: string, label: string = name, over: Partial<Entry> = {}): Entry => ({ ...ready(name, label), ready: false, text: '', updatedText: '—', ...over });

const DEV: readonly (readonly [string, string, string | null, string | null])[] = [
  ['00_input.md', '要件メモ', null, null],
  ['01_requirements.md', '要件定義書', 'requirements', '要件定義'],
  ['02_design.md', '設計書', 'design', '設計'],
  ['03_red_tests.md', 'テスト先行の記録', 'red', 'テスト先行'],
  ['04_implementation.md', '実装の記録', 'implement', '実装'],
  ['05_test_report.md', 'テスト報告', 'test', '検証'],
  ['99_summary.md', 'まとめ', null, null],
];
const DEV_NAMES = DEV.map((d) => d[0]);
/** 開発フローの 7 つ。readyNames のものが「ある」。中身には版（v）を入れる（描き直しで中身が替わったことを見分けるため） */
function devEntries(readyNames: readonly string[] = DEV_NAMES, v = 'v1'): Entry[] {
  return DEV.map(([name, label, stage, stageLabel]) =>
    readyNames.includes(name) ? ready(name, label, { stage, stageLabel, text: `# ${label}\n\n本文 ${name} ${v}` }) : missing(name, label, { stage, stageLabel }),
  );
}

// ---- パネルを起こす・描き直しを送る ----

interface Opts {
  live?: Live;
  list?: RunListView;
  layout?: BootOptions['layout'];
}
function viewOf(entries: Entry[], live: Live = {}): PipelineView {
  return {
    ...runningView(83),
    artifacts: entries as unknown as PipelineView['artifacts'],
    runningStage: live.running ?? null,
    pendingReview: live.pending == null ? null : { stage: live.pending, label: live.pending, doc: 'docs/pipeline/x.md' },
  };
}
const boot = (entries: Entry[], o: Opts = {}): PanelHarness => bootPanel(renderPanelHtml(viewOf(entries, o.live), NONCE, o.list), { layout: o.layout });
const send = (h: PanelHarness, entries: Entry[], o: Opts = {}): void => h.send({ type: 'render', html: renderViewBody(viewOf(entries, o.live), o.list) });

/** 枠の高さと、成果物の一覧の行の位置（行の高さは 56。i 番目の行は i * 56）を決める。スクロールを試すための大きさ */
const ROW_H = 56;
function layoutOf(names: readonly string[], listClient = 200): NonNullable<BootOptions['layout']> {
  return (n) => {
    const pick = n.getAttribute('data-art-pick');
    if (pick !== null) return { offsetTop: Math.max(0, names.indexOf(pick)) * ROW_H, offsetHeight: ROW_H };
    switch (n.getAttribute('data-scroll')) {
      case 'artifact':
        return { scrollHeight: 3000, clientHeight: 300 };
      case 'artifact-list':
        return { scrollHeight: names.length * ROW_H, clientHeight: listClient };
      case 'detail':
        return { scrollHeight: 1500, clientHeight: 600 };
      case 'panel-artifacts':
        return { scrollHeight: 900, clientHeight: 400 };
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
}

// ---- 木の読み取り ----

function one(node: FakeNode, selector: string): FakeNode {
  const found = node.querySelector(selector);
  assert.ok(found, `${selector} がある`);
  return found;
}
/** 成果物の一覧の行（「まだない」行を含む）を、ファイル名の欄の文字で探す（名前をセレクタに連ねない） */
function rowBtn(h: PanelHarness, file: string): FakeNode {
  const found = h.doc.querySelectorAll('.art-row').find((r) => r.querySelector('.art-file')?.textContent === file);
  assert.ok(found, `${file} の行がある`);
  return found;
}
const pickable = (h: PanelHarness): FakeNode[] => h.doc.querySelectorAll('button[data-art-pick]').filter((b) => !b.disabled);
const picked = (h: PanelHarness): string[] => pickable(h).filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.getAttribute('data-art-pick')!);
const previewOf = (h: PanelHarness, name: string): FakeNode => {
  const found = h.doc.querySelectorAll('[data-art-preview]').find((p) => p.getAttribute('data-art-preview') === name);
  assert.ok(found, `${name} のプレビューがある`);
  return found;
};
/** 見える（hidden を持たない）プレビューの名前 */
const shown = (h: PanelHarness): string[] =>
  h.doc
    .querySelectorAll('[data-art-preview]')
    .filter((p) => !p.hasAttribute('hidden'))
    .map((p) => p.getAttribute('data-art-preview')!);
const frameOf = (h: PanelHarness, name: string): FakeNode => one(previewOf(h, name), '.art-body');
const openBtn = (h: PanelHarness, name: string): FakeNode => one(previewOf(h, name), 'button[data-artifact]');
/** data-scroll がこの名前の枠（最初の 1 つ。名前を持つ枠は frameOf で探す） */
const scroller = (h: PanelHarness, name: string): FakeNode => one(h.doc, `[data-scroll="${name}"]`);
const openTab = (h: PanelHarness, tab: 'diagram' | 'artifacts' | 'usage' = 'artifacts'): void => {
  one(h.doc, `button[data-detail-tab="${tab}"]`).dispatch('click');
};
const types = (h: PanelHarness): string[] => h.posted.map((m) => (m as { type: string }).type);
/** 選んだ行が、成果物の一覧の枠の見える範囲に全部入っているか */
function rowInView(h: PanelHarness, file: string): boolean {
  const list = scroller(h, 'artifact-list');
  const r = rowBtn(h, file);
  return list.scrollTop <= r.offsetTop && r.offsetTop + r.offsetHeight <= list.scrollTop + list.clientHeight;
}
const filterInput = (h: PanelHarness): FakeNode => one(h.doc, 'input[data-keep="filter"]');
const activeKeep = (h: PanelHarness): string | null => h.doc.activeElement?.getAttribute('data-keep') ?? null;

const RUN_ROWS = [row({ key: 'here|a', session: 'run-a' }), row({ key: 'here|b', session: 'run-b' })];
const listFor = (selected: 'a' | 'b'): RunListView => listView(RUN_ROWS, { selected: `here|${selected}` });
const runBtn = (h: PanelHarness, key: string): FakeNode => {
  const found = h.doc.querySelectorAll('button[data-run]').find((b) => b.getAttribute('data-run') === key);
  assert.ok(found, `${key} の実行の行がある`);
  return found;
};

// ---- 起動：既定の選び ----

test('D0025-AC-15: パネルのスクリプトが動いたあとも、既定の行（動いている段の成果物）だけが aria-pressed="true" で、そのプレビューだけが見える。起動で送るのは ready だけ', () => {
  const h = boot(devEntries(), { live: { running: 'design' } });
  assert.deepEqual(picked(h), ['02_design.md']);
  assert.deepEqual(shown(h), ['02_design.md']);
  assert.equal(pickable(h).filter((b) => b.getAttribute('aria-pressed') === 'false').length, 6);
  assert.deepEqual(h.posted, [{ type: 'ready' }]);
});

test('D0025-AC-14: 「ある」成果物が 1 つも無いパネルを起こしても、例外を出さず、選びは無く、「まだ成果物がありません」が見える。描き直しで「ある」ようになれば、既定が選ばれる', () => {
  const h = boot(devEntries([]), { live: { running: 'requirements' } });
  assert.deepEqual(picked(h), []);
  assert.deepEqual(shown(h), []);
  assert.match(one(h.doc, '.art-empty').textContent, /まだ成果物がありません/);
  send(h, devEntries(['00_input.md', '01_requirements.md']), { live: { running: 'requirements' } });
  assert.deepEqual(picked(h), ['01_requirements.md']);
  assert.deepEqual(shown(h), ['01_requirements.md']);
});

// ---- AC-07・AC-09・AC-10：行を押す ----

test('D0025-AC-09: 行を押すと、その行が選ばれ（aria-pressed="true"）、そのプレビューだけが見え（ほかは hidden）、ほかの行は aria-pressed="false" になる。拡張へのメッセージは 1 つも送らない', () => {
  const h = boot(devEntries(), { live: { running: 'design' } });
  rowBtn(h, '04_implementation.md').dispatch('click');
  assert.deepEqual(picked(h), ['04_implementation.md']);
  assert.deepEqual(shown(h), ['04_implementation.md']);
  assert.equal(pickable(h).filter((b) => b.getAttribute('aria-pressed') === 'false').length, 6);
  assert.deepEqual(h.posted, [{ type: 'ready' }], 'postMessage は呼ばれない（ready のあと何も増えない）');
});

test('D0025-AC-09: 行の中の文字（ファイル名・作った段）を押しても、その行が選ばれる（イベントは行のボタンに着く）', () => {
  const h = boot(devEntries(), { live: { running: 'design' } });
  one(rowBtn(h, '05_test_report.md'), '.art-file').dispatch('click');
  assert.deepEqual(picked(h), ['05_test_report.md']);
  one(rowBtn(h, '03_red_tests.md'), '.art-stage').dispatch('click');
  assert.deepEqual(picked(h), ['03_red_tests.md']);
  assert.deepEqual(shown(h), ['03_red_tests.md']);
  assert.deepEqual(h.posted, [{ type: 'ready' }]);
});

test('D0025-AC-10: 成果物の一覧の行を押しても openArtifact は送られない（7 つの行を順に押しても、送るのは ready だけ）', () => {
  const h = boot(devEntries(), { live: { running: 'design' } });
  for (const [name] of DEV) rowBtn(h, name).dispatch('click');
  assert.deepEqual(types(h), ['ready']);
});

test('D0025-AC-09: 行は <button> なので、Tab で移り Enter・Space で押せる（本物のブラウザが click にする）。スクリプトは行の keydown を横取りせず、keydown だけでは選びも替えない', () => {
  const h = boot(devEntries(), { live: { running: 'design' } });
  const target = rowBtn(h, '04_implementation.md');
  assert.equal(target.tagName, 'button');
  const enter = target.dispatch('keydown', { key: 'Enter' });
  const space = target.dispatch('keydown', { key: ' ' });
  assert.equal(enter.defaultPrevented, false, 'Enter を横取りしない（button の既定の動きに任せる）');
  assert.equal(space.defaultPrevented, false);
  assert.deepEqual(picked(h), ['02_design.md'], 'click が来るまで選びは替わらない');
  assert.deepEqual(h.posted, [{ type: 'ready' }]);
});

test('D0025-AC-17: プレビューの中身の枠は tabindex="0" の枠で、キーボードのスクロールの鍵（矢印・Space・PageDown・Home・End）をスクリプトが横取りしない（枠が自分でスクロールする）', () => {
  const h = boot(devEntries(), { live: { running: 'design' } });
  const frame = frameOf(h, '02_design.md');
  assert.equal(frame.getAttribute('tabindex'), '0');
  for (const key of ['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight', ' ', 'PageDown', 'PageUp', 'Home', 'End', 'Enter']) {
    assert.equal(frame.dispatch('keydown', { key }).defaultPrevented, false, `${JSON.stringify(key)} を横取りしない`);
  }
  assert.deepEqual(h.posted, [{ type: 'ready' }]);
});

test('D0025-AC-07: 「まだない」行を押しても、選びは変わらず、メッセージも送らない（行の中の文字を押しても同じ）', () => {
  const h = boot(devEntries(['00_input.md', '01_requirements.md']), { live: { running: 'requirements' } });
  assert.deepEqual(picked(h), ['01_requirements.md']);
  const none = rowBtn(h, '03_red_tests.md');
  assert.ok(none.disabled);
  none.dispatch('click');
  one(none, '.art-missing').dispatch('click');
  one(none, '.art-file').dispatch('click');
  assert.deepEqual(picked(h), ['01_requirements.md']);
  assert.deepEqual(shown(h), ['01_requirements.md']);
  assert.deepEqual(h.posted, [{ type: 'ready' }]);
  rowBtn(h, '00_input.md').dispatch('click');
  assert.deepEqual(picked(h), ['00_input.md'], '「ある」行は押せる（検査が空振りでない）');
});

// ---- AC-40・AC-52：「エディタで開く」とメッセージ ----

test('D0025-AC-40: 「エディタで開く」を押すと { type: "openArtifact", name } を送る（名前はそのまま）。見えていないプレビューのボタンでも、その成果物の名前を送る', () => {
  const h = boot(devEntries(), { live: { running: 'design' } });
  openBtn(h, '02_design.md').dispatch('click');
  assert.deepEqual(h.posted.at(-1), { type: 'openArtifact', name: '02_design.md' });
  openBtn(h, '04_implementation.md').dispatch('click');
  assert.deepEqual(h.posted.at(-1), { type: 'openArtifact', name: '04_implementation.md' });
  assert.deepEqual(types(h), ['ready', 'openArtifact', 'openArtifact']);
});

test('D0025-AC-52: パネルが拡張へ送るメッセージの type は ready・openArtifact・selectRun だけ。行・タブ・描き直し・「エディタで開く」を一通り操作しても、増えるのは openArtifact だけ', () => {
  const h = boot(devEntries(), { live: { running: 'design' }, list: listFor('a') });
  openTab(h, 'artifacts');
  rowBtn(h, '01_requirements.md').dispatch('click');
  rowBtn(h, '99_summary.md').dispatch('click');
  send(h, devEntries(DEV_NAMES, 'v2'), { live: { running: 'implement' }, list: listFor('a') });
  openTab(h, 'usage');
  openTab(h, 'artifacts');
  openBtn(h, '99_summary.md').dispatch('click');
  one(h.doc, 'button[data-open-artifacts]').dispatch('click');
  assert.deepEqual(types(h), ['ready', 'openArtifact']);
  for (const t of types(h)) assert.ok(['ready', 'openArtifact', 'selectRun'].includes(t));
});

// ---- AC-54・AC-59・AC-60：描き直しをまたぐ選び ----

test('D0025-AC-54: 行を押したあと、中身が更新された render を受けても、同じ行が選ばれたまま、同じ成果物のプレビューが見える（既定が別の成果物に移っても、押した成果物のまま）', () => {
  const h = boot(devEntries(DEV_NAMES, 'v1'), { live: { running: 'design' } });
  rowBtn(h, '01_requirements.md').dispatch('click');
  send(h, devEntries(DEV_NAMES, 'v2'), { live: { running: 'implement' } });
  assert.deepEqual(picked(h), ['01_requirements.md']);
  assert.deepEqual(shown(h), ['01_requirements.md']);
  assert.match(previewOf(h, '01_requirements.md').textContent, /v2/, '中身は新しいものに替わっている');
  assert.doesNotMatch(previewOf(h, '01_requirements.md').textContent, /v1/);
  send(h, devEntries(DEV_NAMES, 'v3'), { live: { running: 'test' } });
  assert.deepEqual(picked(h), ['01_requirements.md']);
});

test('D0025-AC-60: 行を押していないあいだは、描き直しで既定が変わる（動いている段が進む）と、プレビューも新しい既定へ移る。一度行を押したあとは、移らない', () => {
  const h = boot(devEntries(), { live: { running: 'requirements' } });
  assert.deepEqual(shown(h), ['01_requirements.md']);
  send(h, devEntries(), { live: { running: 'design' } });
  assert.deepEqual(picked(h), ['02_design.md']);
  assert.deepEqual(shown(h), ['02_design.md']);
  send(h, devEntries(), { live: { running: 'implement' } });
  assert.deepEqual(shown(h), ['04_implementation.md']);
  send(h, devEntries(), { live: {} });
  assert.deepEqual(shown(h), ['99_summary.md'], '動いている段が無くなれば最後の「ある」');
  rowBtn(h, '00_input.md').dispatch('click');
  send(h, devEntries(), { live: { running: 'test' } });
  assert.deepEqual(picked(h), ['00_input.md']);
  assert.deepEqual(shown(h), ['00_input.md'], '押したあとは移らない');
});

test('D0025-AC-59: 選んだ成果物が描き直しで「まだない」になったら、既定の選びに戻り、利用者の選びは捨てる。同じ名前のファイルがまた出来ても、行を押し直すまで選びは戻らない（例外は出ない）', () => {
  const h = boot(devEntries(['00_input.md', '01_requirements.md', '02_design.md']));
  assert.deepEqual(shown(h), ['02_design.md'], '既定は最後の「ある」');
  rowBtn(h, '00_input.md').dispatch('click');
  assert.deepEqual(shown(h), ['00_input.md']);
  send(h, devEntries(['01_requirements.md', '02_design.md']));
  assert.deepEqual(picked(h), ['02_design.md'], '00 が「まだない」になったので既定に戻る');
  assert.deepEqual(shown(h), ['02_design.md']);
  assert.ok(rowBtn(h, '00_input.md').disabled);
  send(h, devEntries(['00_input.md', '01_requirements.md', '02_design.md']));
  assert.deepEqual(picked(h), ['02_design.md'], '同じ名前のファイルが戻っても、選びは戻らない');
  assert.deepEqual(shown(h), ['02_design.md']);
  rowBtn(h, '00_input.md').dispatch('click');
  assert.deepEqual(shown(h), ['00_input.md'], '押し直せば選べる');
});

test('D0025-AC-59: 選んだ成果物が一覧から消えた（項目が無い）ときも、既定の選びに戻り、選びを捨てる（例外は出ない）', () => {
  const h = boot(devEntries());
  rowBtn(h, '01_requirements.md').dispatch('click');
  send(h, devEntries().filter((e) => e.name !== '01_requirements.md'));
  assert.deepEqual(picked(h), ['99_summary.md']);
  assert.deepEqual(shown(h), ['99_summary.md']);
  send(h, devEntries());
  assert.deepEqual(picked(h), ['99_summary.md'], '戻っても選びは戻らない');
});

test('D0025-AC-59: すべての成果物が「まだない」になっても例外を出さず、選びは無くなる。「ある」ようになれば既定が選ばれる', () => {
  const h = boot(devEntries());
  rowBtn(h, '02_design.md').dispatch('click');
  send(h, devEntries([]));
  assert.deepEqual(picked(h), []);
  assert.deepEqual(shown(h), []);
  send(h, devEntries());
  assert.deepEqual(picked(h), ['99_summary.md'], '押した選びは捨てられている');
});

test('D0025-AC-65: .art が無い本体（手書きの本体）を render で送っても例外を出さず、成果物の選びは変わらない。次の完全な本体でも、押した行の選びが残る', () => {
  const h = boot(devEntries(), { live: { running: 'design' } });
  rowBtn(h, '01_requirements.md').dispatch('click');
  h.send({ type: 'render', html: '<p>手書きの本体</p>' });
  assert.equal(h.root.querySelector('.art'), null);
  send(h, devEntries(DEV_NAMES, 'v2'), { live: { running: 'design' } });
  assert.deepEqual(picked(h), ['01_requirements.md']);
  assert.deepEqual(shown(h), ['01_requirements.md']);
});

// ---- AC-55・AC-56：スクロール位置 ----

test('D0025-AC-55: 描き直しのあと、同じ成果物が見えたままなら、プレビューのスクロール位置（縦・横）が残る', () => {
  const h = boot(devEntries(), { live: { running: 'design' }, layout: layoutOf(DEV_NAMES) });
  openTab(h);
  const before = frameOf(h, '02_design.md');
  before.scrollTop = 120;
  before.scrollLeft = 30;
  assert.equal(before.scrollTop, 120, '枠はスクロールできる（検査が空振りでない）');
  send(h, devEntries(DEV_NAMES, 'v2'), { live: { running: 'design' } });
  const after = frameOf(h, '02_design.md');
  assert.ok(after !== before, '枠は作り直されている');
  assert.equal(after.scrollTop, 120);
  assert.equal(after.scrollLeft, 30);
  send(h, devEntries(DEV_NAMES, 'v3'), { live: { running: 'design' } });
  assert.equal(frameOf(h, '02_design.md').scrollTop, 120, '何度描き直しても残る');
});

test('D0025-AC-55: 外側の枠のスクロール位置も、描き直しのあと残る（801〜1100px の <main class="detail"> と、窓が低いときの「成果物」タブのパネル）', () => {
  const h = boot(devEntries(), { live: { running: 'design' }, layout: layoutOf(DEV_NAMES) });
  scroller(h, 'detail').scrollTop = 500;
  assert.equal(scroller(h, 'detail').scrollTop, 500, '外側の枠はスクロールできる（検査が空振りでない）');
  send(h, devEntries(DEV_NAMES, 'v2'), { live: { running: 'design' } });
  assert.equal(scroller(h, 'detail').scrollTop, 500);
  openTab(h);
  scroller(h, 'panel-artifacts').scrollTop = 200;
  assert.equal(scroller(h, 'panel-artifacts').scrollTop, 200);
  send(h, devEntries(DEV_NAMES, 'v3'), { live: { running: 'design' } });
  assert.equal(scroller(h, 'panel-artifacts').scrollTop, 200);
  assert.equal(scroller(h, 'detail').scrollTop, 500);
});

test('D0025-AC-56: 別のタブ（使用量・図と出力）へ移って「成果物」へ戻っても、同じ成果物が見えていれば、プレビューのスクロール位置（縦・横）が残る', () => {
  const h = boot(devEntries(), { live: { running: 'design' }, layout: layoutOf(DEV_NAMES) });
  openTab(h);
  const frame = frameOf(h, '02_design.md');
  frame.scrollTop = 120;
  frame.scrollLeft = 30;
  scroller(h, 'panel-artifacts').scrollTop = 200;
  for (const other of ['usage', 'diagram'] as const) {
    openTab(h, other);
    assert.equal(frame.scrollTop, 0, `${other} へ移ると、隠れた枠は位置を失う（偽の DOM が本物と同じに戻す）`);
    openTab(h);
    assert.equal(frame.scrollTop, 120, `${other} から戻ると記憶で戻る`);
    assert.equal(frame.scrollLeft, 30);
    assert.equal(scroller(h, 'panel-artifacts').scrollTop, 200);
  }
});

test('D0025-AC-56: 別のタブにいるあいだに描き直しが来ても、戻ったとき同じ成果物なら位置が残る', () => {
  const h = boot(devEntries(), { live: { running: 'design' }, layout: layoutOf(DEV_NAMES) });
  openTab(h);
  frameOf(h, '02_design.md').scrollTop = 120;
  openTab(h, 'usage');
  send(h, devEntries(DEV_NAMES, 'v2'), { live: { running: 'design' } });
  openTab(h);
  assert.equal(frameOf(h, '02_design.md').scrollTop, 120);
});

// ---- AC-57：見える成果物が替わったら先頭から ----

test('D0025-AC-57: (1) A でスクロール → B を押す → B は先頭から → A を押し直す → A も先頭から（縦も横も 0）', () => {
  const h = boot(devEntries(), { live: { running: 'requirements' }, layout: layoutOf(DEV_NAMES) });
  openTab(h);
  const a = frameOf(h, '01_requirements.md');
  a.scrollTop = 120;
  a.scrollLeft = 30;
  rowBtn(h, '02_design.md').dispatch('click');
  assert.equal(frameOf(h, '02_design.md').scrollTop, 0, 'B は先頭から');
  assert.equal(frameOf(h, '02_design.md').scrollLeft, 0);
  frameOf(h, '02_design.md').scrollTop = 77;
  rowBtn(h, '01_requirements.md').dispatch('click');
  assert.equal(frameOf(h, '01_requirements.md').scrollTop, 0, 'A も先頭から');
  assert.equal(frameOf(h, '01_requirements.md').scrollLeft, 0);
});

test('D0025-AC-57: (2) 押していない状態で、既定が A → B → A と移る描き直しでも、見える成果物が替わるたびに先頭から出る（前の成果物の位置を当てない）', () => {
  const h = boot(devEntries(), { live: { running: 'requirements' }, layout: layoutOf(DEV_NAMES) });
  openTab(h);
  frameOf(h, '01_requirements.md').scrollTop = 120;
  frameOf(h, '01_requirements.md').scrollLeft = 30;
  send(h, devEntries(), { live: { running: 'design' } });
  assert.deepEqual(shown(h), ['02_design.md']);
  assert.equal(frameOf(h, '02_design.md').scrollTop, 0, 'B は先頭から（A の位置を当てない）');
  assert.equal(frameOf(h, '02_design.md').scrollLeft, 0);
  frameOf(h, '02_design.md').scrollTop = 77;
  send(h, devEntries(), { live: { running: 'requirements' } });
  assert.deepEqual(shown(h), ['01_requirements.md']);
  assert.equal(frameOf(h, '01_requirements.md').scrollTop, 0, 'A に戻ると先頭から');
  assert.equal(frameOf(h, '01_requirements.md').scrollLeft, 0);
});

test('D0025-AC-57: (3) A を押してスクロール → A が「まだない」になり既定 B へ戻る → A が戻る → A を押し直すと先頭から', () => {
  const h = boot(devEntries(), { live: { running: 'design' }, layout: layoutOf(DEV_NAMES) });
  openTab(h);
  rowBtn(h, '01_requirements.md').dispatch('click');
  frameOf(h, '01_requirements.md').scrollTop = 120;
  frameOf(h, '01_requirements.md').scrollLeft = 30;
  send(h, devEntries(DEV_NAMES.filter((n) => n !== '01_requirements.md')), { live: { running: 'design' } });
  assert.deepEqual(shown(h), ['02_design.md']);
  assert.equal(frameOf(h, '02_design.md').scrollTop, 0, 'B は先頭から');
  send(h, devEntries(), { live: { running: 'design' } });
  assert.deepEqual(shown(h), ['02_design.md'], 'A が戻っても、押し直すまで B のまま');
  rowBtn(h, '01_requirements.md').dispatch('click');
  assert.equal(frameOf(h, '01_requirements.md').scrollTop, 0);
  assert.equal(frameOf(h, '01_requirements.md').scrollLeft, 0);
});

test('D0025-AC-57: (4) 別のタブにいるあいだに見える成果物が A → B → A と替わっても、「成果物」へ戻ったときは先頭から（隠れているあいだに記憶が残らない）', () => {
  const h = boot(devEntries(), { live: { running: 'requirements' }, layout: layoutOf(DEV_NAMES) });
  openTab(h);
  frameOf(h, '01_requirements.md').scrollTop = 120;
  frameOf(h, '01_requirements.md').scrollLeft = 30;
  openTab(h, 'usage');
  send(h, devEntries(), { live: { running: 'design' } });
  send(h, devEntries(), { live: { running: 'requirements' } });
  openTab(h);
  assert.deepEqual(shown(h), ['01_requirements.md']);
  assert.equal(frameOf(h, '01_requirements.md').scrollTop, 0, '一度 B になったので、A の古い位置は戻さない');
  assert.equal(frameOf(h, '01_requirements.md').scrollLeft, 0);
});

test('D0025-AC-57: 名前が違う成果物へは、記憶した位置を戻さない（記憶は名前つき）。押した成果物に描き直しが来ても、その成果物の位置だけが戻る', () => {
  const h = boot(devEntries(), { live: { running: 'design' }, layout: layoutOf(DEV_NAMES) });
  openTab(h);
  rowBtn(h, '03_red_tests.md').dispatch('click');
  frameOf(h, '03_red_tests.md').scrollTop = 150;
  send(h, devEntries(DEV_NAMES, 'v2'), { live: { running: 'implement' } });
  assert.equal(frameOf(h, '03_red_tests.md').scrollTop, 150);
  assert.equal(frameOf(h, '02_design.md').scrollTop, 0, '見えていないプレビューに位置を当てない');
  assert.equal(frameOf(h, '04_implementation.md').scrollTop, 0);
});

// ---- AC-58：ほかの枠の保持は今のまま ----

test('D0025-AC-58: 実行の一覧・図の枠・時系列・出力のスクロール位置、絞り込みの文字、状態のタブ、詳細のタブの選びは、成果物入りの HTML でも描き直しをまたいで残る（今のまま通る。守る）', () => {
  const o: Opts = { live: { running: 'design' }, list: listFor('a'), layout: layoutOf(DEV_NAMES) };
  const h = boot(devEntries(), o);
  scroller(h, 'list').scrollTop = 150;
  scroller(h, 'diagram').scrollTop = 200;
  scroller(h, 'output').scrollTop = 100;
  scroller(h, 'gantt').scrollTop = 50;
  h.typeText(filterInput(h), 'run');
  one(h.doc, 'button[data-list-tab="running"]').dispatch('click');
  openTab(h, 'diagram');
  send(h, devEntries(DEV_NAMES, 'v2'), o);
  assert.deepEqual(
    ['list', 'diagram', 'output', 'gantt'].map((n) => scroller(h, n).scrollTop),
    [150, 200, 100, 50],
  );
  assert.equal(filterInput(h).value, 'run');
  assert.equal(one(h.doc, 'button[data-list-tab="running"]').getAttribute('aria-selected'), 'true');
  assert.equal(one(h.doc, 'button[data-detail-tab="diagram"]').getAttribute('aria-selected'), 'true');
});

// ---- AC-61：焦点 ----

const FOCUS_TARGETS: readonly (readonly [string, string, (h: PanelHarness, name: string) => FakeNode])[] = [
  ['成果物の一覧の行のボタン', 'art-row:', rowBtn],
  ['プレビューの中身の枠', 'art-scroll:', frameOf],
  ['「エディタで開く」', 'art-open:', openBtn],
];
for (const [label, prefix, find] of FOCUS_TARGETS) {
  test(`D0025-AC-61: ${label}に焦点があるまま描き直すと、同じ data-keep（${prefix}<名前>）の新しい要素に焦点が戻る。焦点が無いときは奪わない`, () => {
    const h = boot(devEntries(), { live: { running: 'design' } });
    openTab(h);
    const before = find(h, '02_design.md');
    before.focus();
    send(h, devEntries(DEV_NAMES, 'v2'), { live: { running: 'design' } });
    const after = h.doc.activeElement;
    assert.ok(after !== null && after !== before, '作り直された要素に焦点がある');
    assert.equal(after.getAttribute('data-keep'), `${prefix}02_design.md`);
    assert.ok(after === find(h, '02_design.md'), '新しい要素');
    assert.ok(after.closest('[hidden]') === null, '見えている要素');
    const h2 = boot(devEntries(), { live: { running: 'design' } });
    send(h2, devEntries(DEV_NAMES, 'v2'), { live: { running: 'design' } });
    assert.ok(h2.doc.activeElement === null, '焦点を奪っていない');
  });
}

test('D0025-AC-61: 焦点のある行が選んだ行でなく、既定が移っても、行のボタンの焦点はその行に戻る（行は隠れず、押せるまま）', () => {
  const h = boot(devEntries(), { live: { running: 'design' } });
  openTab(h);
  const before = rowBtn(h, '03_red_tests.md');
  before.focus();
  send(h, devEntries(DEV_NAMES, 'v2'), { live: { running: 'implement' } });
  assert.ok(h.doc.activeElement === rowBtn(h, '03_red_tests.md'));
  assert.equal(activeKeep(h), 'art-row:03_red_tests.md');
});

for (const [label, prefix, find] of FOCUS_TARGETS.slice(1)) {
  test(`D0025-AC-61: 焦点のあった${label}のプレビューが、既定の移動で hidden になったとき、焦点は body に落ちず、見えているプレビューの枠へ移る`, () => {
    const h = boot(devEntries(), { live: { running: 'design' } });
    openTab(h);
    find(h, '02_design.md').focus();
    send(h, devEntries(DEV_NAMES, 'v2'), { live: { running: 'implement' } });
    assert.deepEqual(shown(h), ['04_implementation.md']);
    const active = h.doc.activeElement;
    assert.ok(active !== null, '焦点がある');
    assert.equal(active.getAttribute('data-keep'), 'art-scroll:04_implementation.md');
    assert.ok(active === frameOf(h, '04_implementation.md'));
    assert.ok(active.closest('[hidden]') === null, '見えているプレビューの枠');
    assert.notEqual(active.getAttribute('data-keep'), `${prefix}02_design.md`);
  });
}

test('D0025-AC-61: 焦点のあった行の成果物が「まだない」になって行が disabled になったときも、焦点は見えているプレビューの枠へ移る（押せない行に焦点を残さない）', () => {
  const h = boot(devEntries(), { live: { running: 'requirements' } });
  openTab(h);
  rowBtn(h, '01_requirements.md').focus();
  send(h, devEntries(DEV_NAMES.filter((n) => n !== '01_requirements.md')), { live: { running: 'requirements' } });
  assert.ok(rowBtn(h, '01_requirements.md').disabled);
  const active = h.doc.activeElement;
  assert.ok(active !== null && active !== rowBtn(h, '01_requirements.md'), '押せない行に焦点が無い');
  assert.deepEqual(shown(h), ['99_summary.md']);
  assert.ok(active === frameOf(h, '99_summary.md'));
});

test('D0025-AC-61: 成果物以外の data-keep（絞り込みの入力）の復元は今のまま：同じ入力に焦点と選択範囲が戻り、成果物の枠へ寄せない', () => {
  const o: Opts = { live: { running: 'design' }, list: listFor('a') };
  const h = boot(devEntries(), o);
  rowBtn(h, '01_requirements.md').dispatch('click');
  h.typeText(filterInput(h), 'run');
  const before = filterInput(h);
  before.focus();
  before.setSelectionRange(1, 3);
  send(h, devEntries(DEV_NAMES, 'v2'), o);
  const after = filterInput(h);
  assert.ok(after !== before);
  assert.ok(h.doc.activeElement === after, '同じ入力に焦点が戻る');
  assert.deepEqual([after.selectionStart, after.selectionEnd], [1, 3]);
  assert.deepEqual(picked(h), ['01_requirements.md']);
});

test('D0025-AC-61: 日本語入力の変換中に来た描き直しは取っておき、変換のあとに 1 回だけ（最後のものを）適用する。押した行の選びはそのまま（今の動きを保つ）', () => {
  const o: Opts = { live: { running: 'design' }, list: listFor('a') };
  const h = boot(devEntries(), o);
  rowBtn(h, '03_red_tests.md').dispatch('click');
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
  h.typeText(input, 'run', true);
  send(h, devEntries(DEV_NAMES, 'v2'), o);
  send(h, devEntries(DEV_NAMES, 'v3'), o);
  assert.equal(sets, 0, '変換中は作り直さない');
  input.dispatch('compositionend', { data: 'run' });
  assert.equal(sets, 1, '終わったあとに 1 回だけ適用する');
  assert.ok(last.includes('v3') && !last.includes('v2'), '最後に来た描き直しを適用する');
  assert.deepEqual(picked(h), ['03_red_tests.md']);
  assert.match(previewOf(h, '03_red_tests.md').textContent, /v3/);
});

// ---- AC-62：成果物の一覧の枠 ----

test('D0025-AC-62: 成果物の一覧の枠（data-scroll="artifact-list"）のスクロール位置は、選びが替わらない描き直しのあとも残る（利用者のスクロールを優先する）', () => {
  const h = boot(devEntries(), { live: { running: 'requirements' }, layout: layoutOf(DEV_NAMES, 100) });
  openTab(h);
  const list = scroller(h, 'artifact-list');
  assert.ok(rowInView(h, '01_requirements.md'), '初めの表示で、選んだ行が見える');
  list.scrollTop = 250;
  assert.equal(list.scrollTop, 250, '一覧の枠はスクロールできる（検査が空振りでない）');
  send(h, devEntries(DEV_NAMES, 'v2'), { live: { running: 'requirements' } });
  assert.equal(scroller(h, 'artifact-list').scrollTop, 250, '選びが替わらないので動かさない');
  send(h, devEntries(DEV_NAMES, 'v3'), { live: { running: 'requirements' } });
  assert.equal(scroller(h, 'artifact-list').scrollTop, 250);
});

test('D0025-AC-62: 行を押して選びが替わったとき、選んだ行が成果物の一覧の枠の中に見える位置まで動く（下の行も、上の行も）', () => {
  const h = boot(devEntries(), { live: { running: 'requirements' }, layout: layoutOf(DEV_NAMES, 100) });
  openTab(h);
  rowBtn(h, '99_summary.md').dispatch('click');
  assert.ok(rowInView(h, '99_summary.md'), '下の行');
  assert.ok(scroller(h, 'artifact-list').scrollTop > 0);
  rowBtn(h, '00_input.md').dispatch('click');
  assert.ok(rowInView(h, '00_input.md'), '上の行');
  rowBtn(h, '04_implementation.md').dispatch('click');
  assert.ok(rowInView(h, '04_implementation.md'), '途中の行');
});

test('D0025-AC-62: 既定が移る描き直し（動いている段が進む）でも、新しい既定の行が枠の中に見える位置まで動く', () => {
  const h = boot(devEntries(), { live: { running: 'requirements' }, layout: layoutOf(DEV_NAMES, 100) });
  openTab(h);
  send(h, devEntries(DEV_NAMES, 'v2'), { live: { running: 'test' } });
  assert.deepEqual(picked(h), ['05_test_report.md']);
  assert.ok(rowInView(h, '05_test_report.md'));
  send(h, devEntries(DEV_NAMES, 'v3'), { live: { running: 'requirements' } });
  assert.ok(rowInView(h, '01_requirements.md'));
});

test('D0025-AC-62: 成果物の一覧の枠が見えていない（別のタブにいる）あいだは寄せず、見えたとき（「成果物」へ移ったとき）に選んだ行へ寄せる。起動時（成果物のタブは初めは見えていない）の寄せで使い切らない', () => {
  const h = boot(devEntries(), { live: { running: 'test' }, layout: layoutOf(DEV_NAMES, 100) });
  const list = scroller(h, 'artifact-list');
  // 偽の DOM は本物の display: none と同じに、hidden の中では大きさが 0 で、スクロール位置を書いても残らない
  assert.ok(list.closest('[hidden]') !== null, '起動時、成果物のタブは見えていない');
  assert.equal(list.clientHeight, 0, '見えていないあいだは大きさが 0（寄せても空振りになる）');
  assert.equal(list.scrollTop, 0, '見えていないあいだは動いていない');
  assert.deepEqual(picked(h), ['05_test_report.md']);
  openTab(h);
  assert.ok(list.closest('[hidden]') === null, '「成果物」へ移ると見える');
  assert.ok(rowInView(h, '05_test_report.md'), '見えたときに寄る（起動時に寄せて使い切っていれば、ここで見えない）');
  openTab(h, 'usage');
  send(h, devEntries(DEV_NAMES, 'v2'), { live: { running: 'requirements' } });
  assert.equal(scroller(h, 'artifact-list').scrollTop, 0, '別のタブにいるあいだは寄せない（隠れた枠は位置を持てない）');
  openTab(h);
  assert.deepEqual(picked(h), ['01_requirements.md']);
  assert.ok(rowInView(h, '01_requirements.md'), '隠れているあいだに既定が移っても、見えたときに寄る');
});

test('D0025-AC-62: 寄せたあと、利用者が動かした位置は、次の描き直し（選びが替わらない）で戻されない', () => {
  const h = boot(devEntries(), { live: { running: 'test' }, layout: layoutOf(DEV_NAMES, 100) });
  openTab(h);
  assert.ok(rowInView(h, '05_test_report.md'));
  scroller(h, 'artifact-list').scrollTop = 0;
  send(h, devEntries(DEV_NAMES, 'v2'), { live: { running: 'test' } });
  assert.equal(scroller(h, 'artifact-list').scrollTop, 0, '選んだ行が見えなくても、動かさない');
});

// ---- AC-65：見る実行が替わったら、選びを既定に戻し、プレビューを先頭に戻す ----

for (const mode of ['render', 'click'] as const) {
  test(`D0025-AC-65: 見る実行が替わる描き直し（${mode === 'render' ? 'ステータスバーのボタンで確認待ちが先に出る場合と同じ：aria-pressed の移った HTML だけが届く' : '実行の一覧の行を押して selectRun を送ったあと'}）で、選んだ成果物が既定に戻り、スクロール（プレビュー・成果物の一覧・外側の枠）が先頭に戻る。実行の一覧のスクロール・絞り込み・状態のタブ・詳細のタブの選びは残る`, () => {
    const o: Opts = { list: listFor('a'), layout: layoutOf(DEV_NAMES, 100) };
    const h = boot(devEntries(), o);
    openTab(h);
    rowBtn(h, '01_requirements.md').dispatch('click');
    frameOf(h, '01_requirements.md').scrollTop = 120;
    frameOf(h, '01_requirements.md').scrollLeft = 30;
    scroller(h, 'artifact-list').scrollTop = 137;
    scroller(h, 'detail').scrollTop = 500;
    scroller(h, 'panel-artifacts').scrollTop = 200;
    scroller(h, 'list').scrollTop = 150;
    h.typeText(filterInput(h), 'run');
    one(h.doc, 'button[data-list-tab="running"]').dispatch('click');
    assert.equal(scroller(h, 'detail').scrollTop, 500, '外側の枠はスクロールできる（検査が空振りでない）');
    if (mode === 'click') {
      runBtn(h, 'here|b').dispatch('click');
      assert.deepEqual(h.posted.at(-1), { type: 'selectRun', id: 'here|b' });
    }
    send(h, devEntries(DEV_NAMES, 'v2'), { list: listFor('b') });
    assert.deepEqual(picked(h), ['99_summary.md'], '押した 01 は捨てられ、既定（最後の「ある」）に戻る');
    assert.deepEqual(shown(h), ['99_summary.md']);
    assert.equal(frameOf(h, '99_summary.md').scrollTop, 0);
    assert.equal(frameOf(h, '99_summary.md').scrollLeft, 0);
    assert.equal(scroller(h, 'detail').scrollTop, 0, '外側の枠（detail）は先頭に戻る');
    assert.equal(scroller(h, 'panel-artifacts').scrollTop, 0, '外側の枠（panel-artifacts）は先頭に戻る');
    assert.ok(rowInView(h, '99_summary.md'), '成果物の一覧は、古い位置でなく、既定の行が見える位置');
    assert.notEqual(scroller(h, 'artifact-list').scrollTop, 137, '古い位置を戻さない');
    assert.equal(scroller(h, 'list').scrollTop, 150, '実行の一覧のスクロールは残る');
    assert.equal(filterInput(h).value, 'run', '絞り込みは残る');
    assert.equal(one(h.doc, 'button[data-list-tab="running"]').getAttribute('aria-selected'), 'true', '状態のタブは残る');
    assert.equal(one(h.doc, 'button[data-detail-tab="artifacts"]').getAttribute('aria-selected'), 'true', '詳細のタブは残る');
    assert.deepEqual(types(h).filter((t) => t !== 'selectRun'), ['ready']);
  });
}

test('D0025-AC-65: 見る実行が替わるとき、前の実行で見ていた成果物と同じ名前が既定になっても、プレビューは先頭から出る（スクロールの記憶の成果物の項目が消える）', () => {
  const o: Opts = { list: listFor('a'), layout: layoutOf(DEV_NAMES) };
  const h = boot(devEntries(), o);
  openTab(h);
  assert.deepEqual(shown(h), ['99_summary.md'], '押していないので既定');
  frameOf(h, '99_summary.md').scrollTop = 120;
  frameOf(h, '99_summary.md').scrollLeft = 30;
  scroller(h, 'detail').scrollTop = 300;
  send(h, devEntries(DEV_NAMES, 'v2'), { list: listFor('a') });
  assert.equal(frameOf(h, '99_summary.md').scrollTop, 120, '同じ実行の描き直しでは残る（対照）');
  send(h, devEntries(DEV_NAMES, 'v3'), { list: listFor('b') });
  assert.deepEqual(shown(h), ['99_summary.md'], 'b の既定も同じ名前');
  assert.equal(frameOf(h, '99_summary.md').scrollTop, 0);
  assert.equal(frameOf(h, '99_summary.md').scrollLeft, 0);
  assert.equal(scroller(h, 'detail').scrollTop, 0);
  send(h, devEntries(DEV_NAMES, 'v4'), { list: listFor('a') });
  assert.equal(frameOf(h, '99_summary.md').scrollTop, 0, 'a へ戻っても先頭から');
});

test('D0025-AC-65: 見る実行が替わったあとは、また行を押して選べる（選びを替えたあとの描き直しで、新しい選びが残る）', () => {
  const o: Opts = { list: listFor('a') };
  const h = boot(devEntries(), o);
  send(h, devEntries(), { list: listFor('b') });
  rowBtn(h, '02_design.md').dispatch('click');
  send(h, devEntries(DEV_NAMES, 'v2'), { list: listFor('b') });
  assert.deepEqual(picked(h), ['02_design.md']);
});

// ---- AC-63・AC-64・AC-69：ソースの文字 ----

const SCRIPT_SRC = readFileSync(path.join(HERE, 'panelScript.ts'), 'utf8');

test('D0025-AC-63: パネルのスクリプトに、保存の道（workspaceState・getState・setState・localStorage・sessionStorage）が無い。選びとスクロールは変数だけで持つ（今のまま通る。守る）', () => {
  assert.deepEqual(findStorage(SCRIPT_SRC), []);
});

test('D0025-AC-63: パネルのスクリプトが postMessage で送る type は ready・openArtifact・selectRun だけ（新しい種類を足さない）（今のまま通る。守る）', () => {
  const sent = callArgs(withoutComments(SCRIPT_SRC), 'postMessage').map((args) => /\btype\s*:\s*'([^']+)'/.exec(args)?.[1] ?? null);
  assert.ok(sent.length >= 3, `postMessage の呼び出しが読めている（${sent.length} 件）`);
  assert.ok(sent.every((t) => t !== null), 'type を直に書いている');
  assert.deepEqual([...new Set(sent)].sort(), ['openArtifact', 'ready', 'selectRun']);
});

test('D0025-AC-63: 選びの操作（行を押す・描き直し・タブ・焦点）を一通りしても、保存の口（getState・setState）を呼ばない：スクリプトに渡る vscode の API は postMessage だけ', () => {
  const h = boot(devEntries(), { live: { running: 'design' }, list: listFor('a'), layout: layoutOf(DEV_NAMES) });
  openTab(h);
  rowBtn(h, '01_requirements.md').dispatch('click');
  frameOf(h, '01_requirements.md').scrollTop = 50;
  frameOf(h, '01_requirements.md').focus();
  send(h, devEntries(DEV_NAMES, 'v2'), { live: { running: 'test' }, list: listFor('b') });
  openTab(h, 'usage');
  assert.deepEqual(types(h), ['ready'], '例外なしで動き、送ったのは ready だけ');
});

test('D0025-AC-64: パネルのスクリプトに、セレクタへ名前（や値）を連ねた書き方（querySelector・querySelectorAll・closest の引数の + ・ ${}・.concat）が無い。名前で要素を探すときは getAttribute(…) === 名前 の等値比較にする。属性の名前だけを連ねる \'[\' + key.attr + \']\'（今の restoreFocus。data-keep・data-run・data-reasons の固定の 3 つ）は、外から来た値でないので許す（今のまま通る。守る）', () => {
  assert.deepEqual(findSelectorConcat(SCRIPT_SRC), []);
});

test('D0025-AC-69: パネルのスクリプトのコード（コメントを除く）に style= と setAttribute("style") が無い（CSP が style 属性を許さない）。外部の読み込みもしない（今のまま通る。守る）', () => {
  // コメントに書いた語（文書の説明に出てくる style=・fetch( など）で、コードが正しくても赤にならないよう、コメントを除いて見る
  const code = withoutComments(SCRIPT_SRC);
  assert.doesNotMatch(code, /\bstyle\s*=|setAttribute\(\s*['"]style['"]/);
  assert.doesNotMatch(code, /\bfetch\s*\(|XMLHttpRequest|importScripts|\beval\s*\(|new Function|insertAdjacentHTML|outerHTML|https?:\/\//);
});

// ---- AC-64：外から来た名前 ----

/** 外から来た名前（"・'・]・\・&・空白、セレクタの特別な文字、オブジェクトの組み込みの名前）。記録からは作れないものを含むので、項目を直に渡す */
const NAMES: readonly (readonly [string, string])[] = [
  ['ダブルクォート', 'a"b.md'],
  ['シングルクォート', "it's.md"],
  ['閉じかっこ', 'x]y.md'],
  ['バックスラッシュ', 'back\\slash.md'],
  ['アンパサンド', 'a&b.md'],
  ['文字参照に見える文字', 'a&amp;b&lt;.md'],
  ['空白', 'sp ace.md'],
  ['引用符で閉じる形', 'x"] [data-a="y.md'],
  ['全部入り', 'a"]\'\\& b.md'],
  ['<script>', '<script>alert(1)</script>.md'],
  ['連ねたセレクタの形', 'a"],[data-art-pick.md'],
  ['constructor', 'constructor'],
  ['__proto__', '__proto__'],
  ['toString', 'toString'],
  ['hasOwnProperty', 'hasOwnProperty'],
  ['text', 'text'],
];
for (const [label, name] of NAMES) {
  test(`D0025-AC-64: 外から来た名前（${label}）の成果物でも、行を押す・描き直し後の選び・スクロールの記憶・焦点の復元・「エディタで開く」が、例外なく動く`, () => {
    const names = ['plain-a.md', name, 'plain-b.md'];
    const make = (v: string, off: readonly string[] = []): Entry[] => names.map((n) => (off.includes(n) ? missing(n, n) : ready(n, n, { text: `本文 ${n} ${v}` })));
    const h = boot(make('v1'), { layout: layoutOf(names) });
    openTab(h);
    assert.deepEqual(picked(h), ['plain-b.md'], '既定は最後の「ある」');
    rowBtn(h, name).dispatch('click');
    assert.deepEqual(picked(h), [name], '押すとその行が選ばれる');
    assert.deepEqual(shown(h), [name]);
    const before = frameOf(h, name);
    before.scrollTop = 90;
    before.scrollLeft = 12;
    send(h, make('v2'));
    assert.deepEqual(picked(h), [name], '描き直しのあとも選びが残る');
    assert.ok(frameOf(h, name) !== before);
    assert.equal(frameOf(h, name).scrollTop, 90, 'スクロールの記憶');
    assert.equal(frameOf(h, name).scrollLeft, 12);
    for (const [prefix, find] of [['art-row:', rowBtn], ['art-scroll:', frameOf], ['art-open:', openBtn]] as const) {
      const old = find(h, name);
      old.focus();
      send(h, make('v3'));
      const active = h.doc.activeElement;
      assert.ok(active !== null && active !== old, `${prefix} の焦点が新しい要素に戻る`);
      assert.equal(active.getAttribute('data-keep'), `${prefix}${name}`);
    }
    openBtn(h, name).dispatch('click');
    assert.deepEqual(h.posted.at(-1), { type: 'openArtifact', name });
    send(h, make('v4', [name]));
    assert.deepEqual(picked(h), ['plain-b.md'], '「まだない」になれば既定に戻る');
    assert.ok(rowBtn(h, name).disabled);
    assert.deepEqual(types(h), ['ready', 'openArtifact']);
  });
}
