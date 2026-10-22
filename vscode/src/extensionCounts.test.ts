// 入口 extension.ts の配線の検査（D0024：ステータスバーの件数）。AC-15・25・29〜33・37〜41・43。
// extension.ts は vscode を import するので、単体では動かせない。判断を持たない呼び出しの形を、ソースを文字で読んで確かめる
// （extensionStale.test.ts と同じ作り。文字で読む部品は test/sourceText.ts に置く）。
// ここで見るのは配線だけ：何を呼ぶか・どの順に呼ぶか・どこに書くか。数え方と文字は domain/ と view/ のテスト、
// 一覧 → 文字の通しは app/runListCounts.test.ts が見る。
// 構成：1) 検査の本体  2) 実物の extension.ts・view/statusBar.ts  3) 検査そのもの（壊した見本・部品）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { blockAfter, callArgs, functionBody, inOrder, withoutComments } from './test/sourceText.ts';

// ---- 1) 検査の本体 ----------------------------------------------------------------

const COUNTS_IDS = [
  'noColor', 'noMessageInRender', 'noMarkdown', 'labelWithList', 'labelOutsideVisible',
  'frontWaitingInExt', 'waitingUsesFrontKey', 'noStateCompare', 'noWaitingLiteral',
  'selectBeforeRender', 'renderBeforeOpen', 'waitingNeedsList', 'waitingUsesChoose', 'waitingCatchesWrite', 'waitingChecksEntry',
  'rememberOnlyInChoose', 'selectRunUsesChoose', 'noDirectUpdate',
  'pollsWithFlag', 'showOthersRenders', 'stopOnNoTarget', 'pollNeedsTarget', 'retargetResetsLive',
  'bodyOnlyWhenVisible', 'postOnlyWhenVisible', 'viewStateRenders',
  'createsGeneration', 'loadLatestOrder', 'renderUsesLoadLatest', 'renderNoCurrentView', 'assignOnlyInAdopt', 'retargetDropsStale',
  'showRunAdoptsCurrent', 'panelHtmlAlways', 'deactivateDropsStale', 'currentViewSnapshot',
  'pollerRunsRender', 'oneRunsSource', 'oneWorkDirSource',
] as const;
type CountsWiringId = (typeof COUNTS_IDS)[number];

/** 「パネルが見えている」ブロックの頭。この中だけで本体を作り、パネルへ送る */
const VISIBLE_HEAD = /if \(panel !== undefined && panel\.visible\) \{/;
const NO_TARGET_HEAD = /if \(!target\) \{/;
/** 本体の最初の文が if (!target) { であること（updatePolling の先頭。前に別の文があるものは先頭と言わない） */
const NO_TARGET_FIRST = /^\s*if \(!target\) \{/;
/** 色への代入（比較の === ・ => は除く） */
const COLOR_ASSIGN = /\.(?:backgroundColor|color)\s*=(?![=>])/;
const SHOW_MESSAGE = /\bshow(?:Information|Warning|Error)Message\(/;
/** 取り込みの 1 か所（adopt）と初期化（retarget）の外に書いてはいけない代入（let の宣言は除く） */
const KEPT_ASSIGN = /(?<!\blet\s+)\b(?:lastListView|lastList|shown|lastLive)\s*=(?![=>])/;
const POLL_FLAG = /\bhasOtherWorktree:\s*lastList\?\.hasOtherWorktree\s*===\s*true\b/;
const SHOW_OTHERS_RENDERS = /\baffectsConfiguration\(\s*`\$\{SECTION\}\.\$\{SETTING_SHOW_OTHER\}`\s*\)\s*\)\s*void render\(\);/;
const NEXT = /\.next\(\)/;
const IS_CURRENT = /\.isCurrent\(/;
const ADOPT = /\badopt\(/;
const TARGET_TAKEN = /\bconst\s+\w+\s*=\s*target\s*;/;
const SOURCE_TAKEN = /\bconst\s+\w+\s*=\s*runsSource\s*;/;

const has = (text: string | null, re: RegExp): boolean => text !== null && re.test(text);
const calls = (text: string | null, name: string): number => (text === null ? 0 : callArgs(text, name).length);

/** 本体 names を取り除いた残り（取れない関数は何も取り除かない） */
function withoutBodies(code: string, names: readonly string[]): string {
  let rest = code;
  for (const name of names) {
    const body = functionBody(code, name);
    if (body !== null) rest = rest.replace(body, '');
  }
  return rest;
}

/** try { … } のブロックに chooseRun( があり、その閉じかっこのあとに catch が続くか */
function catchesWrite(selectWaiting: string | null): boolean {
  if (selectWaiting === null) return false;
  const tryBlock = blockAfter(selectWaiting, /\btry \{/);
  if (tryBlock === null || calls(tryBlock, 'chooseRun') === 0) return false;
  const end = selectWaiting.indexOf(tryBlock) + tryBlock.length;
  return /^\}\s*catch\b/.test(selectWaiting.slice(end));
}

/** 配線で欠けている・守られていないもの。空なら全部そろっている。 */
function countsWiringProblems(source: string): CountsWiringId[] {
  const code = withoutComments(source);
  const render = functionBody(code, 'render');
  const showRun = functionBody(code, 'showRun');
  const selectWaiting = functionBody(code, 'selectWaiting');
  const updatePolling = functionBody(code, 'updatePolling');
  const retarget = functionBody(code, 'retarget');
  const deactivate = functionBody(code, 'deactivate');
  const currentView = functionBody(code, 'currentView');
  const loadLatest = functionBody(code, 'loadLatest');
  const chooseRun = functionBody(code, 'chooseRun');
  // render の「パネルが見えている」ブロックの中と外（ブロックが無ければ null）
  const visible = render === null ? null : blockAfter(render, VISIBLE_HEAD);
  const outsideVisible = render === null || visible === null ? null : render.replace(visible, '');
  const labelCalls = render === null ? [] : callArgs(render, 'statusBarLabel');
  const pollCalls = updatePolling === null ? [] : callArgs(updatePolling, 'shouldPoll');
  const selectRunBranch = blockAfter(code, /if \(msg\.type === 'selectRun'\) \{/);
  const rememberCalls = callArgs(code, 'rememberRun');
  const viewState = blockAfter(code, /onDidChangeViewState\(\(\) => \{/);
  const afterSnapshot = currentView === null ? null : currentView.replace(TARGET_TAKEN, '').replace(SOURCE_TAKEN, '');

  const ok: Record<CountsWiringId, boolean> = {
    // AC-15・25：色・吹き出し・Markdown を使わない
    noColor: !COLOR_ASSIGN.test(code),
    noMessageInRender: render !== null && !SHOW_MESSAGE.test(render),
    noMarkdown: !/\bMarkdownString\b/.test(code),
    // AC-33：一覧を渡し、パネルの条件の外で状態バーを直す
    labelWithList: labelCalls.length >= 1 && labelCalls.every((args) => /\blistView\b/.test(args)),
    labelOutsideVisible: outsideVisible !== null && /\bstatusItem\.text\s*=(?!=)/.test(outsideVisible) && /\bstatusItem\.tooltip\s*=(?!=)/.test(outsideVisible),
    // AC-29・43：先に出す確認待ちは frontWaitingKey で決め、行の状態を自分で比べない
    frontWaitingInExt: callArgs(code, 'frontWaitingKey').length >= 1,
    waitingUsesFrontKey: calls(selectWaiting, 'frontWaitingKey') >= 1,
    noStateCompare: !/\.state\s*[!=]==?/.test(code),
    noWaitingLiteral: !/(['"])waiting\1/.test(code),
    // AC-30・31：ボタンの順と守り
    selectBeforeRender: showRun !== null && inOrder(showRun, [/\bselectWaiting\(/, /\brender\(/]),
    renderBeforeOpen: showRun !== null && inOrder(showRun, [/\brender\(/, /\bpanel\.reveal\(/]) && inOrder(showRun, [/\brender\(/, /\bcreateWebviewPanel\(/]),
    waitingNeedsList: has(selectWaiting, /\blastList\s*===\s*null\b/),
    waitingUsesChoose: calls(selectWaiting, 'chooseRun') >= 1,
    waitingCatchesWrite: catchesWrite(selectWaiting),
    waitingChecksEntry: calls(selectWaiting, 'findEntry') >= 1,
    // AC-32：選びを覚える書き込みは 1 か所
    rememberOnlyInChoose: rememberCalls.length === 1 && calls(chooseRun, 'rememberRun') === 1,
    selectRunUsesChoose: calls(selectRunBranch, 'chooseRun') >= 1,
    noDirectUpdate: !/\.update\(/.test(code),
    // AC-37・38：読み直しの要否
    pollsWithFlag: pollCalls.length >= 1 && pollCalls.every((args) => POLL_FLAG.test(args)),
    showOthersRenders: SHOW_OTHERS_RENDERS.test(code),
    stopOnNoTarget: has(retarget === null ? null : blockAfter(retarget, NO_TARGET_HEAD), /\bpoller\.stop\(\)/),
    pollNeedsTarget:
      updatePolling !== null &&
      NO_TARGET_FIRST.test(updatePolling) &&
      has(blockAfter(updatePolling, NO_TARGET_HEAD), /\bpoller\.stop\(\)/) &&
      inOrder(updatePolling, [NO_TARGET_HEAD, /\bshouldPoll\(/]),
    retargetResetsLive: has(retarget, /\blastLive\s*=\s*false\b/),
    // AC-39：見えているパネルにだけ本体を作って送る
    bodyOnlyWhenVisible: visible !== null && outsideVisible !== null && calls(visible, 'renderViewBody') === 1 && calls(outsideVisible, 'renderViewBody') === 0,
    postOnlyWhenVisible: visible !== null && outsideVisible !== null && calls(visible, 'postMessage') === 1 && calls(outsideVisible, 'postMessage') === 0,
    viewStateRenders: has(viewState, /\bif \(created\.visible\) void render\(\);/),
    // AC-40：世代
    createsGeneration: callArgs(code, 'createGeneration').length >= 1,
    loadLatestOrder: loadLatest !== null && inOrder(loadLatest, [NEXT, IS_CURRENT, ADOPT]),
    renderUsesLoadLatest: calls(render, 'loadLatest') >= 1,
    renderNoCurrentView: render !== null && calls(render, 'currentView') === 0,
    assignOnlyInAdopt: !KEPT_ASSIGN.test(withoutBodies(code, ['adopt', 'retarget'])),
    retargetDropsStale: has(retarget, NEXT),
    showRunAdoptsCurrent: showRun !== null && inOrder(showRun, [NEXT, IS_CURRENT, ADOPT]),
    panelHtmlAlways: showRun !== null && inOrder(showRun, [/\brenderPanelHtml\(/, IS_CURRENT]),
    deactivateDropsStale: deactivate !== null && inOrder(deactivate, [/\bpanel\?\.dispose\(\)/, NEXT]),
    currentViewSnapshot:
      currentView !== null && afterSnapshot !== null && TARGET_TAKEN.test(currentView) && SOURCE_TAKEN.test(currentView) && !/\btarget\b/.test(afterSnapshot) && !/\brunsSource\b/.test(afterSnapshot),
    // AC-41：読む口は増えない
    pollerRunsRender: /\brun:\s*\(\)\s*=>\s*render\(\)/.test(code),
    oneRunsSource: callArgs(code, 'createFsRunsSource').length === 1,
    oneWorkDirSource: callArgs(code, 'createFsWorkDirSource').length === 1,
  };
  return COUNTS_IDS.filter((id) => !ok[id]);
}

type StatusBarWiringId = 'frontWaitingInLabel';

/** view/statusBar.ts の配線で欠けているもの：先に出す確認待ちの案内も frontWaitingKey( で決める（別の判断を書かない）。 */
function statusBarProblems(source: string): StatusBarWiringId[] {
  return callArgs(withoutComments(source), 'frontWaitingKey').length >= 1 ? [] : ['frontWaitingInLabel'];
}

// ---- 2) 実物の extension.ts・view/statusBar.ts ---------------------------------------

const EXTENSION = readFileSync(new URL('./extension.ts', import.meta.url), 'utf8');
const STATUS_BAR = readFileSync(new URL('./view/statusBar.ts', import.meta.url), 'utf8');

interface Wiring {
  id: CountsWiringId;
  /** テスト名の頭に付ける AC の番号（ID ごとに 1 つ） */
  ac: number;
  what: string;
  /** 今の extension.ts でも通る（守り続けるための検査） */
  keep?: true;
}

const WIRING: readonly Wiring[] = [
  { id: 'noColor', ac: 15, what: 'statusItem の backgroundColor・color に代入しない', keep: true },
  { id: 'noMessageInRender', ac: 15, what: 'render() の本体で show*Message( を呼ばない（吹き出しを出さない）', keep: true },
  { id: 'noMarkdown', ac: 25, what: 'MarkdownString を使わない', keep: true },
  { id: 'labelWithList', ac: 33, what: 'render() で statusBarLabel( に listView を渡す' },
  { id: 'labelOutsideVisible', ac: 33, what: 'render() で statusItem.text・tooltip を「パネルが見えている」ブロックの外で書き込む（パネルが無くても直す）' },
  { id: 'frontWaitingInExt', ac: 43, what: 'frontWaitingKey( を呼ぶ' },
  { id: 'waitingUsesFrontKey', ac: 29, what: 'selectWaiting が frontWaitingKey( を呼んで先に出す確認待ちを決める' },
  { id: 'noStateCompare', ac: 43, what: '行の状態を .state の ===・!== で比べない', keep: true },
  { id: 'noWaitingLiteral', ac: 43, what: "'waiting' の文字を持たない", keep: true },
  { id: 'selectBeforeRender', ac: 30, what: 'showRun で selectWaiting( を render( より前に呼ぶ' },
  { id: 'renderBeforeOpen', ac: 30, what: 'showRun で render( を panel.reveal( ・createWebviewPanel( より前に呼ぶ' },
  { id: 'waitingNeedsList', ac: 30, what: 'selectWaiting が lastList === null のときは選びを変えない' },
  { id: 'waitingUsesChoose', ac: 30, what: 'selectWaiting が chooseRun( で選びを替える' },
  { id: 'waitingCatchesWrite', ac: 30, what: 'selectWaiting が chooseRun( を try { } catch で握る（書き込みに失敗してもパネルを開く）' },
  { id: 'waitingChecksEntry', ac: 31, what: 'selectWaiting が findEntry( で一覧にある目印だけを選ぶ' },
  { id: 'rememberOnlyInChoose', ac: 32, what: 'rememberRun( を呼ぶのは chooseRun の 1 か所だけ' },
  { id: 'selectRunUsesChoose', ac: 32, what: 'selectRun の枝が chooseRun( を通る' },
  { id: 'noDirectUpdate', ac: 32, what: 'memory に直接 .update( しない', keep: true },
  { id: 'pollsWithFlag', ac: 37, what: 'updatePolling が shouldPoll( に hasOtherWorktree: lastList?.hasOtherWorktree === true を渡す' },
  { id: 'showOthersRenders', ac: 37, what: 'pipe-in.showOtherWorktrees が変わったら void render(); で読み直す', keep: true },
  { id: 'stopOnNoTarget', ac: 38, what: 'retarget の target が無い枝で poller.stop() する' },
  { id: 'pollNeedsTarget', ac: 38, what: 'updatePolling の本体の最初の文が if (!target) { で、そのブロックの poller.stop() が shouldPoll( の前にある' },
  { id: 'retargetResetsLive', ac: 38, what: 'retarget で lastLive = false に戻す' },
  { id: 'bodyOnlyWhenVisible', ac: 39, what: 'render() が renderViewBody( を「パネルが見えている」ブロックの中だけで 1 回呼ぶ' },
  { id: 'postOnlyWhenVisible', ac: 39, what: 'render() が postMessage( を「パネルが見えている」ブロックの中だけで 1 回呼ぶ' },
  { id: 'viewStateRenders', ac: 39, what: 'パネルがまた見えたら（onDidChangeViewState）render() を呼ぶ', keep: true },
  { id: 'createsGeneration', ac: 40, what: 'createGeneration( で世代の部品を作る' },
  { id: 'loadLatestOrder', ac: 40, what: 'loadLatest が .next() → .isCurrent( → adopt( の順に進める' },
  { id: 'renderUsesLoadLatest', ac: 40, what: 'render() が loadLatest( で読む' },
  { id: 'renderNoCurrentView', ac: 40, what: 'render() が currentView( を直に呼ばない' },
  { id: 'assignOnlyInAdopt', ac: 40, what: 'lastList・lastListView・shown・lastLive への代入が adopt と retarget の中だけにある' },
  { id: 'retargetDropsStale', ac: 40, what: 'retarget が .next() で途中の読み込みの結果を捨てる' },
  { id: 'showRunAdoptsCurrent', ac: 40, what: 'showRun が .next() → .isCurrent( → adopt( の順で取り込む' },
  { id: 'panelHtmlAlways', ac: 40, what: 'showRun が最初の .isCurrent( より前に renderPanelHtml( で HTML を入れる（空のパネルを残さない）' },
  { id: 'deactivateDropsStale', ac: 40, what: 'deactivate が panel?.dispose() のあとに .next() で途中の結果を捨てる' },
  { id: 'currentViewSnapshot', ac: 40, what: 'currentView が target・runsSource を先頭で const に取り、そのあとは読まない' },
  { id: 'pollerRunsRender', ac: 41, what: 'poller の run が render() を呼ぶだけ', keep: true },
  { id: 'oneRunsSource', ac: 41, what: 'createFsRunsSource( の呼び出しが 1 か所のまま', keep: true },
  { id: 'oneWorkDirSource', ac: 41, what: 'createFsWorkDirSource( の呼び出しが 1 か所のまま', keep: true },
];

const KEEP_NOTE = '（今のまま通る。守る）';
const acOf = (id: CountsWiringId): number => {
  const found = WIRING.find((w) => w.id === id);
  if (found === undefined) throw new Error(`WIRING に ${id} が無い`);
  return found.ac;
};

test(`D0024-AC-30: 配線の検査の表そのもの：表の ID の並びは、検査する ID の一覧と同じ${KEEP_NOTE}`, () => {
  assert.deepEqual(WIRING.map((w) => w.id), [...COUNTS_IDS]);
});

test(`D0024-AC-30: 配線の検査の表そのもの：検査する ID は重複せず 39 個${KEEP_NOTE}`, () => {
  assert.deepEqual([new Set(COUNTS_IDS).size, COUNTS_IDS.length], [39, 39]);
});

// 失敗の文は、ある・無いのどちらにも寄らない言い方にする（「あってはいけない形がある」ときも、「あるはずの形が無い」ときも落ちる）。
for (const { id, ac, what, keep } of WIRING) {
  test(`D0024-AC-${ac}: extension.ts は ${what}（${id}）${keep ? KEEP_NOTE : ''}`, () => {
    assert.ok(!countsWiringProblems(EXTENSION).includes(id), `配線の約束を守っていない（${id}）：extension.ts は ${what}`);
  });
}

test('D0024-AC-29: view/statusBar.ts は frontWaitingKey( を呼んで、先に出す確認待ちの案内を決める（frontWaitingInLabel）', () => {
  assert.ok(
    !statusBarProblems(STATUS_BAR).includes('frontWaitingInLabel'),
    '配線の約束を守っていない（frontWaitingInLabel）：view/statusBar.ts は frontWaitingKey( を呼んで、先に出す確認待ちの案内を決める',
  );
});

/** 検査が本体を読む関数と、その本体にあるはずの語（取れない・語が無いなら、読めないのであって赤の理由にならない） */
const READABLE_BODIES: readonly (readonly [string, string])[] = [
  ['render', 'statusBarLabel('],
  ['showRun', 'createWebviewPanel('],
  ['retarget', 'createFsRunsSource('],
  ['updatePolling', 'shouldPoll('],
  ['currentView', 'loadRunList('],
  ['deactivate', 'poller.stop()'],
];

for (const [name, word] of READABLE_BODIES) {
  test(`D0024-AC-30: 配線の検査そのもの：実物の extension.ts から ${name} の本体を取れる（${word} を含む。読めないから赤、にならない）${KEEP_NOTE}`, () => {
    const body = functionBody(withoutComments(EXTENSION), name);
    assert.ok(body !== null && body.includes(word), `${name} の本体が取れない（${word} を含むはず）`);
  });
}

/** 検査が枝として取り出すブロック。word があれば、その語が中にあるはず（無ければ、取れること）。 */
const READABLE_BLOCKS: readonly (readonly [string, RegExp, string | null])[] = [
  ['onDidChangeViewState の中身', /onDidChangeViewState\(\(\) => \{/, 'updatePolling('],
  ['selectRun の枝', /if \(msg\.type === 'selectRun'\) \{/, 'findEntry('],
  ['if (!target) { のブロック', /if \(!target\) \{/, null],
];

for (const [label, head, word] of READABLE_BLOCKS) {
  test(`D0024-AC-30: 配線の検査そのもの：実物の extension.ts から ${label} を取れる（読めないから赤、にならない）${KEEP_NOTE}`, () => {
    const block = blockAfter(withoutComments(EXTENSION), head);
    assert.ok(block !== null && (word === null || block.includes(word)), `${label} が取れない${word === null ? '' : `（${word} を含むはず）`}`);
  });
}

// ---- 3) 検査そのもの ---------------------------------------------------------------

const lines = (...rows: string[]): string => rows.join('\n');

/** 配線がそろっている見本のソース（関数ごとに短く写したもの）。1 つの部品を差し替えて、欠けた見本を作る。 */
const PIECES = {
  imports: lines(
    "import { frontWaitingKey } from './domain/runList.ts';",
    "import { createGeneration, createPoller, shouldPoll } from './app/refreshPolicy.ts';",
    "import { findEntry, loadRunList } from './app/runList.ts';",
    "import { rememberRun } from './app/selection.ts';",
    "import { createFsRunsSource, createFsWorkDirSource } from './infra/fsWorkDirSource.ts';",
    "import { statusBarLabel } from './view/statusBar.ts';",
  ),
  glob: "const REMOTE_WATCH_GLOB = '{state.json,*.md,logs/*.jsonl}';",
  state: lines(
    'let statusItem: vscode.StatusBarItem | undefined;',
    'let selected: RunKey | null = null;',
    'let lastList: RunList | null = null;',
    'let lastListView: RunListView | null = null;',
    'let lastLive = false;',
    'let shown: { runAbs: string; artifacts: string[] } | null = null;',
  ),
  loads: 'const loads = createGeneration();',
  poller: lines(
    'const poller = createPoller({',
    '  intervalMs: POLL_MS,',
    '  run: () => render(),',
    '  setTimer: (fn, ms) => setTimeout(fn, ms),',
    '  clearTimer: (handle) => clearTimeout(handle),',
    '});',
  ),
  affects: "  if (event.affectsConfiguration(`${SECTION}.${SETTING_SHOW_OTHER}`)) void render();",
  deactivate: lines(
    'export function deactivate(): void {',
    '  poller.stop();',
    '  panel?.dispose();',
    '  panel = undefined;',
    '  stopWatching();',
    '  loads.next();',
    '}',
  ),
  updatePolling: lines(
    'function updatePolling(live: boolean): void {',
    '  if (!target) {',
    '    poller.stop();',
    '    return;',
    '  }',
    '  if (shouldPoll({ visible: panel !== undefined && panel.visible, hasRemote: lastList?.hasRemote === true, live, hasOtherWorktree: lastList?.hasOtherWorktree === true })) poller.start();',
    '  else poller.stop();',
    '}',
  ),
  retarget: lines(
    'function retarget(): void {',
    '  loads.next();',
    '  stopWatching();',
    '  shown = null;',
    '  lastList = null;',
    '  lastListView = null;',
    '  lastLive = false;',
    '  target = currentWorkDir();',
    '  if (!target) {',
    '    runsSource = null;',
    '    poller.stop();',
    '    statusItem?.hide();',
    '    return;',
    '  }',
    '  runsSource = createFsRunsSource(target.root, target.abs, target.setting);',
    '  statusItem?.show();',
    '  void render();',
    '}',
  ),
  currentView: lines(
    'async function currentView(): Promise<CurrentView | null> {',
    '  const t = target; const src = runsSource;',
    '  if (!t || !src) return null;',
    '  const list = await loadRunList(src, { showOthers, clock });',
    '  const choice = chooseEntry(list, selected, { key: HERE, label: null, workDirAbs: t.abs });',
    '  const view = await refreshView(createFsWorkDirSource(choice.dirAbs, choice.dirAbs, { previous: isPreviousRun(list, choice.key) }), choice.dirAbs, clock);',
    '  return { view, list, listView: toListView(list, choice.key, t.setting), shownRun: { runAbs: choice.dirAbs, artifacts: [] }, live: view.gantt.live };',
    '}',
  ),
  adopt: lines(
    'function adopt(current: CurrentView): void {',
    '  lastList = current.list;',
    '  lastListView = current.listView;',
    '  shown = current.shownRun;',
    '  lastLive = current.live;',
    '}',
  ),
  loadLatest: lines(
    'async function loadLatest(): Promise<CurrentView | null> {',
    '  const mine = loads.next();',
    '  const current = await currentView();',
    '  if (current === null || !loads.isCurrent(mine)) return null;',
    '  adopt(current);',
    '  return current;',
    '}',
  ),
  render: lines(
    'async function render(): Promise<void> {',
    '  const current = await loadLatest();',
    '  if (!current) return;',
    '  const { view, listView, otherDir, live, staleAfterSec } = current;',
    '  if (statusItem) {',
    '    const label = statusBarLabel(view, listView);',
    '    statusItem.text = label.text;',
    '    statusItem.tooltip = label.tooltip;',
    '  }',
    '  if (panel !== undefined && panel.visible) {',
    "    const message = { type: 'render', html: renderViewBody(view, listView, staleAfterSec) };",
    '    void panel.webview.postMessage(message);',
    '  }',
    '  watchRemote(panel !== undefined ? otherDir : null);',
    '  updatePolling(live);',
    '}',
  ),
  choose: lines(
    'async function chooseRun(key: RunKey): Promise<void> {',
    '  selected = key;',
    '  if (memory) await rememberRun(memory, key);',
    '}',
  ),
  selectWaiting: lines(
    'async function selectWaiting(): Promise<boolean> {',
    '  if (!target || lastList === null || lastListView === null) return false;',
    '  const key = frontWaitingKey(lastListView.rows, lastListView.selected);',
    '  if (key === null || findEntry(lastList, key) === null) return false;',
    '  try {',
    '    await chooseRun(key);',
    '  } catch {',
    '    // 覚える書き込みに失敗しても、選びは（メモリでは）変わっている。パネルは開く',
    '  }',
    '  return true;',
    '}',
  ),
  showRun: lines(
    'async function showRun(): Promise<void> {',
    '  if (await selectWaiting()) await render();',
    '  if (panel) {',
    '    panel.reveal();',
    '    return;',
    '  }',
    '  const created = vscode.window.createWebviewPanel(VIEW_IDS.run, NAME, vscode.ViewColumn.Beside, {',
    '    enableScripts: true,',
    '    localResourceRoots: [],',
    '  });',
    '  panel = created;',
    '  const onMessage = created.webview.onDidReceiveMessage(async (value: unknown) => {',
    '    const msg = parseWebviewMessage(value);',
    '    if (!msg) return;',
    "    if (msg.type === 'selectRun') {",
    '      if (lastList === null || findEntry(lastList, msg.id) === null) return;',
    '      await chooseRun(msg.id);',
    '      await render();',
    '      return;',
    '    }',
    '  });',
    '  const onViewState = created.onDidChangeViewState(() => {',
    '    updatePolling(lastLive);',
    '    if (created.visible) void render();',
    '  });',
    '  const mine = loads.next();',
    '  const current = await currentView();',
    "  created.webview.html = renderPanelHtml(current.view, 'nonce', current.listView, current.staleAfterSec);",
    '  if (loads.isCurrent(mine)) {',
    '    adopt(current);',
    '    watchRemote(current.otherDir);',
    '    updatePolling(current.live);',
    '  }',
    '}',
  ),
  extra: '',
};
type PieceName = keyof typeof PIECES;
type Over = Partial<Record<PieceName, string>>;

function sampleWith(over: Over = {}): string {
  return Object.values({ ...PIECES, ...over }).join('\n');
}

/** 部品の文字 from を、ちょうど 1 か所、to に替える。つづりの誤りで何も替わらない見本を作らないよう、見つからなければ落とす。 */
function swap(piece: string, from: string, to: string): string {
  assert.equal(piece.split(from).length, 2, `見本の部品に「${from}」がちょうど 1 か所無い（見本の書き間違い）`);
  return piece.replace(from, () => to);
}
const dropLine = (piece: string, line: string): string => swap(piece, `${line}\n`, '');
const addAfter = (piece: string, line: string, added: string): string => swap(piece, line, `${line}\n${added}`);

const sorted = <T extends string>(ids: readonly T[]): T[] => [...ids].sort();

/** view/statusBar.ts の配線がそろっている見本（call の 1 行を差し替えて、欠けた見本を作る） */
const FRONT_CALL = '  const front = frontWaitingKey(list.rows, list.selected);';
function statusBarSample(call: string = FRONT_CALL): string {
  return lines("import { frontWaitingKey, hasOtherCounted } from '../domain/runList.ts';", 'export function countsLabel(view, list) {', call, '  return front !== null;', '}');
}

test(`D0024-AC-30: 配線の検査そのもの：配線がそろった見本は見逃す（何も見つけない）。let の宣言・adopt と retarget の代入・import の行・関数の宣言は違反に数えない${KEEP_NOTE}`, () => {
  assert.deepEqual(countsWiringProblems(sampleWith()), []);
});

test(`D0024-AC-29: 配線の検査そのもの：view/statusBar.ts の配線がそろった見本は見逃す（何も見つけない）${KEEP_NOTE}`, () => {
  assert.deepEqual(statusBarProblems(statusBarSample()), []);
});

interface Broken {
  id: CountsWiringId;
  /** 「…した見本は、見つける」の前半 */
  label: string;
  over: Over;
  /** その壊し方で、同時に見つかるのが当然のほかの ID（理由はテストの上のコメント） */
  also?: readonly CountsWiringId[];
}

const R = PIECES.render;
const SEL = PIECES.selectWaiting;
const SHOW = PIECES.showRun;
const UP = PIECES.updatePolling;
const RT = PIECES.retarget;
const CV = PIECES.currentView;
const LL = PIECES.loadLatest;
const DEACT = PIECES.deactivate;
const CHOOSE = PIECES.choose;

const SHOW_TOP = lines('  if (await selectWaiting()) await render();', '  if (panel) {', '    panel.reveal();', '    return;', '  }', '');
const SEL_TRY = lines('  try {', '    await chooseRun(key);', '  } catch {', '    // 覚える書き込みに失敗しても、選びは（メモリでは）変わっている。パネルは開く', '  }', '');
const ADOPT_BLOCK = lines('  if (loads.isCurrent(mine)) {', '    adopt(current);', '    watchRemote(current.otherDir);', '    updatePolling(current.live);', '  }', '');
const HTML_LINE = "  created.webview.html = renderPanelHtml(current.view, 'nonce', current.listView, current.staleAfterSec);";

// 見本は ID ごとに 1 つ以上。見つけるのはその ID だけ（deepEqual）。
// ただし次の 3 組は、片方が欠ければ必ずもう片方も欠ける作りなので、also に書く：
//   frontWaitingInExt ⊂ waitingUsesFrontKey（呼び出しが 1 つも無ければ selectWaiting にも無い）、
//   waitingUsesChoose ⊂ waitingCatchesWrite（selectWaiting に chooseRun( が無ければ try の中にも無い）、
//   showRunAdoptsCurrent の「isCurrent が全く無い」見本 ⊂ panelHtmlAlways（isCurrent より前、が言えない）。
// bodyOnlyWhenVisible の「if (panel) に戻す」見本は、ブロックが無いので labelOutsideVisible・postOnlyWhenVisible も欠ける。
const BROKEN: readonly Broken[] = [
  // AC-15・25
  { id: 'noColor', label: 'statusItem.color に代入した', over: { extra: "statusItem.color = new vscode.ThemeColor('x');" } },
  { id: 'noColor', label: 'statusItem.backgroundColor に代入した', over: { extra: "statusItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');" } },
  ...(['showInformationMessage', 'showWarningMessage', 'showErrorMessage'] as const).map(
    (name): Broken => ({ id: 'noMessageInRender', label: `render() の本体で ${name}( を呼ぶ`, over: { render: addAfter(R, '  if (!current) return;', `  void vscode.window.${name}('x');`) } }),
  ),
  { id: 'noMarkdown', label: 'new vscode.MarkdownString( を使う', over: { extra: "const md = new vscode.MarkdownString('**x**');" } },
  // AC-33
  { id: 'labelWithList', label: 'statusBarLabel(view) に listView を渡さない', over: { render: swap(R, 'statusBarLabel(view, listView)', 'statusBarLabel(view)') } },
  { id: 'labelWithList', label: '2 つ目の statusBarLabel(view) だけ listView を渡さない', over: { render: addAfter(R, '    statusItem.tooltip = label.tooltip;', '    statusBarLabel(view);') } },
  { id: 'labelWithList', label: 'statusBarLabel( を呼ばない', over: { render: swap(R, 'const label = statusBarLabel(view, listView);', "const label = { text: '', tooltip: '' };") } },
  {
    id: 'labelOutsideVisible',
    label: 'statusItem.text・tooltip への代入を「パネルが見えている」ブロックの中へ入れる',
    over: {
      render: lines(
        'async function render(): Promise<void> {',
        '  const current = await loadLatest();',
        '  if (!current) return;',
        '  const { view, listView, otherDir, live, staleAfterSec } = current;',
        '  if (panel !== undefined && panel.visible) {',
        '    const label = statusBarLabel(view, listView);',
        '    statusItem.text = label.text;',
        '    statusItem.tooltip = label.tooltip;',
        "    const message = { type: 'render', html: renderViewBody(view, listView, staleAfterSec) };",
        '    void panel.webview.postMessage(message);',
        '  }',
        '  watchRemote(panel !== undefined ? otherDir : null);',
        '  updatePolling(live);',
        '}',
      ),
    },
  },
  // AC-29・43
  {
    id: 'frontWaitingInExt',
    label: 'frontWaitingKey( をどこでも呼ばない',
    over: { selectWaiting: swap(SEL, 'const key = frontWaitingKey(lastListView.rows, lastListView.selected);', 'const key = lastListView.rows[0]?.key ?? null;') },
    also: ['waitingUsesFrontKey'],
  },
  {
    id: 'waitingUsesFrontKey',
    label: 'selectWaiting が frontWaitingKey( を呼ばず（別の所で呼ぶ）',
    over: {
      selectWaiting: swap(SEL, 'const key = frontWaitingKey(lastListView.rows, lastListView.selected);', 'const key = lastListView.rows[0]?.key ?? null;'),
      extra: 'const elsewhere = frontWaitingKey(rows, null);',
    },
  },
  { id: 'noStateCompare', label: "if (row.state === 'x') と行の状態を === で比べる", over: { extra: "if (row.state === 'x') { void 0; }" } },
  { id: 'noStateCompare', label: "if (row.state !== 'x') と行の状態を !== で比べる", over: { extra: "if (row.state !== 'x') { void 0; }" } },
  { id: 'noWaitingLiteral', label: "const w = 'waiting'; と書く", over: { extra: "const w = 'waiting';" } },
  { id: 'noWaitingLiteral', label: 'const w = "waiting"; と書く', over: { extra: 'const w = "waiting";' } },
  // AC-30・31
  { id: 'selectBeforeRender', label: 'render() のあとに selectWaiting() を呼ぶ（順を逆にした）', over: { showRun: swap(SHOW, SHOW_TOP, lines('  await render();', '  await selectWaiting();', '  if (panel) {', '    panel.reveal();', '    return;', '  }', '')) } },
  { id: 'selectBeforeRender', label: 'selectWaiting() を呼ばない', over: { showRun: swap(SHOW, '  if (await selectWaiting()) await render();', '  await render();') } },
  {
    id: 'renderBeforeOpen',
    label: 'render() を panel.reveal() のあとへ移した',
    over: { showRun: swap(SHOW, SHOW_TOP, lines('  await selectWaiting();', '  if (panel) {', '    panel.reveal();', '    await render();', '    return;', '  }', '')) },
  },
  {
    id: 'renderBeforeOpen',
    label: '開く前に render() を呼ばない（呼ぶのはパネルの受け取りの中だけ）',
    over: { showRun: swap(SHOW, SHOW_TOP, lines('  await selectWaiting();', '  if (panel) {', '    panel.reveal();', '    return;', '  }', '')) },
  },
  { id: 'waitingNeedsList', label: 'selectWaiting が lastList === null を見ない', over: { selectWaiting: swap(SEL, 'lastList === null || ', '') } },
  { id: 'waitingUsesChoose', label: 'selectWaiting が selected = key と直に書く', over: { selectWaiting: swap(SEL, '    await chooseRun(key);', '    selected = key;') }, also: ['waitingCatchesWrite'] },
  { id: 'waitingCatchesWrite', label: 'selectWaiting の try { } catch を外した', over: { selectWaiting: swap(SEL, SEL_TRY, '  await chooseRun(key);\n') } },
  { id: 'waitingCatchesWrite', label: 'chooseRun( を try の外で呼ぶ', over: { selectWaiting: swap(SEL, SEL_TRY, lines('  await chooseRun(key);', '  try {', '    void key;', '  } catch {', '  }', '')) } },
  { id: 'waitingCatchesWrite', label: 'try のあとを catch でなく finally にした', over: { selectWaiting: swap(SEL, '  } catch {', '  } finally {') } },
  { id: 'waitingChecksEntry', label: 'selectWaiting が findEntry( で一覧を確かめない', over: { selectWaiting: swap(SEL, 'key === null || findEntry(lastList, key) === null', 'key === null') } },
  // AC-32
  { id: 'rememberOnlyInChoose', label: 'selectRun の枝でも rememberRun( を直に呼ぶ（2 か所）', over: { showRun: addAfter(SHOW, '      await chooseRun(msg.id);', '      if (memory) await rememberRun(memory, msg.id);') } },
  {
    id: 'rememberOnlyInChoose',
    label: 'rememberRun( を chooseRun でなく selectWaiting で呼ぶ',
    over: { choose: dropLine(CHOOSE, '  if (memory) await rememberRun(memory, key);'), selectWaiting: addAfter(SEL, '    await chooseRun(key);', '    if (memory) await rememberRun(memory, key);') },
  },
  { id: 'rememberOnlyInChoose', label: 'chooseRun が rememberRun( を呼ばない', over: { choose: dropLine(CHOOSE, '  if (memory) await rememberRun(memory, key);') } },
  { id: 'selectRunUsesChoose', label: 'selectRun の枝が selected = msg.id; と直に書く（宣言と selectWaiting の chooseRun( だけが残る）', over: { showRun: swap(SHOW, '      await chooseRun(msg.id);', '      selected = msg.id;') } },
  { id: 'selectRunUsesChoose', label: 'selectRun の枝が無い', over: { showRun: swap(SHOW, "if (msg.type === 'selectRun') {", "if (msg.type === 'ready') {") } },
  { id: 'noDirectUpdate', label: 'memory.update( を直に呼ぶ', over: { extra: "memory.update('k', 1);" } },
  { id: 'noDirectUpdate', label: 'context.workspaceState.update( を直に呼ぶ', over: { extra: "context.workspaceState.update('k', 1);" } },
  // AC-37・38
  { id: 'pollsWithFlag', label: 'shouldPoll( に hasOtherWorktree を渡さない', over: { updatePolling: swap(UP, ', hasOtherWorktree: lastList?.hasOtherWorktree === true', '') } },
  { id: 'pollsWithFlag', label: 'hasOtherWorktree: true と直に書く', over: { updatePolling: swap(UP, 'hasOtherWorktree: lastList?.hasOtherWorktree === true', 'hasOtherWorktree: true') } },
  { id: 'showOthersRenders', label: 'void render() を外した', over: { affects: '  if (event.affectsConfiguration(`${SECTION}.${SETTING_SHOW_OTHER}`)) retarget();' } },
  { id: 'showOthersRenders', label: '別の設定（SETTING_STALE_AFTER）にだけ void render() を付けた', over: { affects: '  if (event.affectsConfiguration(`${SECTION}.${SETTING_STALE_AFTER}`)) void render();' } },
  { id: 'stopOnNoTarget', label: 'retarget の target が無い枝で poller.stop() しない', over: { retarget: dropLine(RT, '    poller.stop();') } },
  { id: 'stopOnNoTarget', label: 'poller.stop() が target が無い枝の外にある', over: { retarget: swap(RT, lines('    poller.stop();', '    statusItem?.hide();', '    return;', '  }', ''), lines('    statusItem?.hide();', '    return;', '  }', '  poller.stop();', '')) } },
  { id: 'pollNeedsTarget', label: 'updatePolling に target が無いときのブロックが無い', over: { updatePolling: swap(UP, lines('  if (!target) {', '    poller.stop();', '    return;', '  }', ''), '') } },
  { id: 'pollNeedsTarget', label: 'target が無いときのブロックで poller.stop() しない', over: { updatePolling: swap(UP, lines('    poller.stop();', '    return;'), '    return;') } },
  {
    id: 'pollNeedsTarget',
    label: 'target が無いときのブロックが本体の最初の文でない（shouldPoll( の前だが、別の文が先にある）',
    over: { updatePolling: swap(UP, 'function updatePolling(live: boolean): void {\n', 'function updatePolling(live: boolean): void {\n  const wasLive = live;\n') },
  },
  {
    id: 'pollNeedsTarget',
    label: 'target が無いときのブロックが shouldPoll( のあとにある',
    over: {
      updatePolling: lines(
        'function updatePolling(live: boolean): void {',
        '  if (shouldPoll({ visible: panel !== undefined && panel.visible, hasRemote: lastList?.hasRemote === true, live, hasOtherWorktree: lastList?.hasOtherWorktree === true })) poller.start();',
        '  else poller.stop();',
        '  if (!target) {',
        '    poller.stop();',
        '    return;',
        '  }',
        '}',
      ),
    },
  },
  { id: 'retargetResetsLive', label: 'retarget で lastLive = false に戻さない', over: { retarget: dropLine(RT, '  lastLive = false;') } },
  // AC-39
  {
    id: 'bodyOnlyWhenVisible',
    label: 'if (panel) に戻した（見えているかを見ない）',
    over: { render: swap(R, 'if (panel !== undefined && panel.visible) {', 'if (panel) {') },
    also: ['postOnlyWhenVisible', 'labelOutsideVisible'],
  },
  {
    id: 'bodyOnlyWhenVisible',
    label: 'renderViewBody( をブロックの外で呼ぶ',
    over: {
      render: swap(
        swap(R, "html: renderViewBody(view, listView, staleAfterSec) };", 'html: body };'),
        '  if (panel !== undefined && panel.visible) {',
        lines('  const body = renderViewBody(view, listView, staleAfterSec);', '  if (panel !== undefined && panel.visible) {'),
      ),
    },
  },
  { id: 'bodyOnlyWhenVisible', label: 'renderViewBody( をブロックの中で 2 回呼ぶ', over: { render: addAfter(R, "    const message = { type: 'render', html: renderViewBody(view, listView, staleAfterSec) };", '    const again = renderViewBody(view, listView, staleAfterSec);') } },
  { id: 'postOnlyWhenVisible', label: 'postMessage( をブロックの外で呼ぶ', over: { render: swap(R, lines('    void panel.webview.postMessage(message);', '  }'), lines('  }', '  void panel?.webview.postMessage(message);')) } },
  { id: 'postOnlyWhenVisible', label: 'postMessage( をブロックの中で 2 回呼ぶ', over: { render: addAfter(R, '    void panel.webview.postMessage(message);', '    void panel.webview.postMessage(message);') } },
  { id: 'viewStateRenders', label: 'onDidChangeViewState の中で render() を呼ばない', over: { showRun: dropLine(SHOW, '    if (created.visible) void render();') } },
  // AC-40
  { id: 'createsGeneration', label: 'createGeneration( を呼ばない', over: { loads: 'const loads = { next: () => 1, isCurrent: () => true };' } },
  { id: 'loadLatestOrder', label: 'loadLatest が isCurrent( で確かめない', over: { loadLatest: swap(LL, 'if (current === null || !loads.isCurrent(mine)) return null;', 'if (current === null) return null;') } },
  {
    id: 'loadLatestOrder',
    label: 'loadLatest が adopt( を isCurrent( の確かめより先にする',
    over: { loadLatest: swap(LL, lines('  if (current === null || !loads.isCurrent(mine)) return null;', '  adopt(current);'), lines('  if (current === null) return null;', '  adopt(current);', '  if (!loads.isCurrent(mine)) return null;')) },
  },
  { id: 'loadLatestOrder', label: 'loadLatest が .next() で番号を進めない', over: { loadLatest: swap(LL, 'const mine = loads.next();', 'const mine = 0;') } },
  { id: 'renderUsesLoadLatest', label: 'render() が loadLatest( を呼ばない', over: { render: swap(R, 'await loadLatest()', 'await reload()') } },
  { id: 'renderNoCurrentView', label: 'render() が currentView( を直に呼ぶ', over: { render: addAfter(R, '  if (!current) return;', '  const again = await currentView();') } },
  { id: 'assignOnlyInAdopt', label: 'currentView の中で shown = … と代入する', over: { currentView: addAfter(CV, '  if (!t || !src) return null;', '  shown = { runAbs: t.abs, artifacts: [] };') } },
  { id: 'assignOnlyInAdopt', label: 'currentView の中で lastList = … と代入する', over: { currentView: addAfter(CV, '  if (!t || !src) return null;', '  lastList = null;') } },
  { id: 'assignOnlyInAdopt', label: 'render() の中で lastLive = … と代入する', over: { render: addAfter(R, '  if (!current) return;', '  lastLive = current.live;') } },
  { id: 'assignOnlyInAdopt', label: 'showRun の中で adopt( の代わりに lastListView = … と代入する', over: { showRun: addAfter(SHOW, '    adopt(current);', '    lastListView = current.listView;') } },
  { id: 'retargetDropsStale', label: 'retarget が .next() を呼ばない', over: { retarget: dropLine(RT, '  loads.next();') } },
  {
    id: 'showRunAdoptsCurrent',
    label: 'isCurrent( の確かめより先に adopt( する',
    over: { showRun: swap(SHOW, ADOPT_BLOCK, lines('  adopt(current);', '  watchRemote(current.otherDir);', '  updatePolling(current.live);', '  void loads.isCurrent(mine);', '')) },
  },
  {
    id: 'showRunAdoptsCurrent',
    label: 'isCurrent( の確かめなしで adopt( する',
    over: { showRun: swap(SHOW, ADOPT_BLOCK, lines('  adopt(current);', '  watchRemote(current.otherDir);', '  updatePolling(current.live);', '')) },
    also: ['panelHtmlAlways'],
  },
  { id: 'showRunAdoptsCurrent', label: 'showRun が .next() で番号を進めない', over: { showRun: swap(SHOW, 'const mine = loads.next();', 'const mine = 0;') } },
  {
    id: 'panelHtmlAlways',
    label: 'renderPanelHtml( を isCurrent の条件の中へ入れる（世代が古いと空のパネルが残る）',
    over: { showRun: swap(SHOW, lines(HTML_LINE, '  if (loads.isCurrent(mine)) {', ''), lines('  if (loads.isCurrent(mine)) {', HTML_LINE.replace('  created', '    created'), '')) },
  },
  { id: 'deactivateDropsStale', label: 'deactivate が .next() を呼ばない', over: { deactivate: swap(DEACT, lines('  stopWatching();', '  loads.next();'), '  stopWatching();') } },
  {
    id: 'deactivateDropsStale',
    label: 'deactivate が panel?.dispose() の前に .next() を呼ぶ',
    over: { deactivate: swap(swap(DEACT, lines('  poller.stop();', '  panel?.dispose();'), lines('  poller.stop();', '  loads.next();', '  panel?.dispose();')), lines('  stopWatching();', '  loads.next();'), '  stopWatching();') },
  },
  { id: 'currentViewSnapshot', label: 'await のあとで target.abs を読む', over: { currentView: swap(CV, 'workDirAbs: t.abs', 'workDirAbs: target.abs') } },
  { id: 'currentViewSnapshot', label: 'await のあとで runsSource を読む', over: { currentView: swap(CV, 'loadRunList(src,', 'loadRunList(runsSource,') } },
  {
    id: 'currentViewSnapshot',
    label: '先頭で const に取らず、target・runsSource を直に読む',
    over: {
      currentView: swap(
        swap(swap(swap(CV, lines('  const t = target; const src = runsSource;', '  if (!t || !src) return null;'), '  if (!target || !runsSource) return null;'), 'loadRunList(src,', 'loadRunList(runsSource,'), 'workDirAbs: t.abs', 'workDirAbs: target.abs'),
        't.setting',
        'target.setting',
      ),
    },
  },
  // AC-41
  { id: 'pollerRunsRender', label: 'poller の run が render() でなく別の関数を呼ぶ', over: { poller: swap(PIECES.poller, 'run: () => render(),', 'run: () => other(),') } },
  { id: 'oneRunsSource', label: 'createFsRunsSource( を 2 か所で呼ぶ', over: { extra: 'const again = createFsRunsSource(a, b, c);' } },
  { id: 'oneRunsSource', label: 'createFsRunsSource( を呼ばない', over: { retarget: swap(RT, 'createFsRunsSource(target.root, target.abs, target.setting)', 'null') } },
  { id: 'oneWorkDirSource', label: 'createFsWorkDirSource( を 2 か所で呼ぶ', over: { extra: 'const again = createFsWorkDirSource(a, b);' } },
  { id: 'oneWorkDirSource', label: 'createFsWorkDirSource( を呼ばない', over: { currentView: swap(CV, 'createFsWorkDirSource(choice.dirAbs, choice.dirAbs, { previous: isPreviousRun(list, choice.key) })', 'null') } },
];

for (const { id, label, over, also = [] } of BROKEN) {
  const expected = [id, ...also];
  test(`D0024-AC-${acOf(id)}: 配線の検査そのもの：${label}見本は、見つける（${expected.join('・')}）${KEEP_NOTE}`, () => {
    assert.deepEqual(sorted(countsWiringProblems(sampleWith(over))), sorted(expected));
  });
}

test(`D0024-AC-30: 配線の検査の表そのもの：ID ごとに、壊した見本が 1 つ以上ある${KEEP_NOTE}`, () => {
  const covered = new Set(BROKEN.map((b) => b.id));
  assert.deepEqual(COUNTS_IDS.filter((id) => !covered.has(id)), []);
});

// render の関数を消した見本：render の本体を読む検査はどれも、本体が取れなければ欠けと見る（読めないから通る、にしない）。
const READS_RENDER: readonly CountsWiringId[] = [
  'noMessageInRender', 'labelWithList', 'labelOutsideVisible', 'bodyOnlyWhenVisible', 'postOnlyWhenVisible', 'renderUsesLoadLatest', 'renderNoCurrentView',
];

for (const id of READS_RENDER) {
  test(`D0024-AC-${acOf(id)}: 配線の検査そのもの：render を消した見本は、render の本体を読む検査（${id}）が欠けを見つける${KEEP_NOTE}`, () => {
    const found = countsWiringProblems(sampleWith({ render: '' }));
    assert.ok(found.includes(id), `${id} を見つけない：${found.join('・')}`);
  });
}

/** 違反に見えて、違反でないもの（見つけてはいけない）。extra は見本の最後に足す行 */
const NOT_VIOLATIONS: readonly (readonly [CountsWiringId, string, string])[] = [
  ['noColor', '代入でない比較（statusItem.color ===）', 'if (statusItem.color === undefined) { void 0; }'],
  ['noStateCompare', '比べるのでなく代入する（row.state = next）', 'row.state = next;'],
  ['noMessageInRender', 'render の外（別の関数）の showWarningMessage(', lines('function warn(): void {', "  void vscode.window.showWarningMessage('x');", '}')],
];

for (const [id, label, extra] of NOT_VIOLATIONS) {
  test(`D0024-AC-${acOf(id)}: 配線の検査そのもの：「${label}」は、違反に数えない（${id}）${KEEP_NOTE}`, () => {
    assert.deepEqual(countsWiringProblems(sampleWith({ extra })), []);
  });
}

const BROKEN_STATUS_BAR: readonly (readonly [string, string])[] = [
  ['import だけ残して frontWaitingKey( を呼ばない', statusBarSample('  const front = null;')],
  ['同じ判断を自分で書く（find で先頭の確認待ちを探す）', statusBarSample('  const front = list.rows.find((r) => r.key !== list.selected) ?? null;')],
  ['frontWaitingKey( の呼び出しをコメントにだけ書く', statusBarSample(`  // ${FRONT_CALL.trim()}`)],
  ['frontWaitingKey( の宣言だけがあり、呼び出しが無い', statusBarSample('  function frontWaitingKey(rows, selected) { return null; }')],
];

for (const [label, source] of BROKEN_STATUS_BAR) {
  test(`D0024-AC-29: 配線の検査そのもの：view/statusBar.ts の見本で、${label}場合は、見つける（frontWaitingInLabel）${KEEP_NOTE}`, () => {
    assert.deepEqual(statusBarProblems(source), ['frontWaitingInLabel']);
  });
}

// コメントに書いただけの配線では通らない（行頭の // とブロックコメント）。コメントに書いた違反は見つけない。

const COMMENTED: readonly (readonly [string, Over, readonly CountsWiringId[]])[] = [
  ['createGeneration( を行頭の // に書いただけの', { loads: `// ${PIECES.loads}` }, ['createsGeneration']],
  ['poller の run をブロックコメントに書いただけの', { poller: `/*\n${PIECES.poller}\n*/` }, ['pollerRunsRender']],
  ['frontWaitingKey( を // に書いただけの（呼び出しは selectWaiting の 1 つだけ）', { selectWaiting: swap(SEL, '  const key = frontWaitingKey(lastListView.rows, lastListView.selected);', '  // const key = frontWaitingKey(lastListView.rows, lastListView.selected);') }, ['frontWaitingInExt', 'waitingUsesFrontKey']],
  ['createFsRunsSource( を /** … */ に書いただけの（呼び出しが 0 になる）', { retarget: swap(RT, '  runsSource = createFsRunsSource(target.root, target.abs, target.setting);', '  /**\n   * runsSource = createFsRunsSource(target.root, target.abs, target.setting);\n   */') }, ['oneRunsSource']],
];

// AC の番号は、見つける ID（expected の先頭）のもの
for (const [label, over, expected] of COMMENTED) {
  test(`D0024-AC-${acOf(expected[0])}: 配線の検査そのもの：コメントに書いただけの配線では通らない：${label}見本は、見つける（${expected.join('・')}）${KEEP_NOTE}`, () => {
    assert.deepEqual(sorted(countsWiringProblems(sampleWith(over))), sorted(expected));
  });
}

/** コメントに書いた違反は、違反に数えない（見つけてはいけない）。extra は見本の最後に足す行 */
const COMMENTED_VIOLATIONS: readonly (readonly [CountsWiringId, string, string])[] = [
  ['noColor', '行頭の // に書いた色への代入', "// statusItem.color = new vscode.ThemeColor('x');"],
  ['noMarkdown', 'ブロックコメントに書いた MarkdownString', lines('/*', " * new vscode.MarkdownString('x');", '*/')],
  ['noDirectUpdate', 'ブロックコメントに書いた .update(', lines('/*', " * memory.update('k', 1);", '*/')],
  ['noStateCompare', '行頭の // に書いた .state ===', "// if (row.state === 'x') {}"],
  ['noWaitingLiteral', "行頭の // に書いた 'waiting'", "// const w = 'waiting';"],
];

for (const [id, label, extra] of COMMENTED_VIOLATIONS) {
  test(`D0024-AC-${acOf(id)}: 配線の検査そのもの：「${label}」は、見つけない（${id}）${KEEP_NOTE}`, () => {
    assert.deepEqual(countsWiringProblems(sampleWith({ extra })), []);
  });
}

test('D0024-AC-15: 配線の検査そのもの：文字列の中の「/*」（glob）をコメントの始まりと取り違えて、配線の行を消さない（今のまま通る。守る）', () => {
  const withGlob = `const GLOB = '{state.json,*.md,logs/*.jsonl}';\n${sampleWith()}\n/** 後ろのブロックコメント */`;
  assert.deepEqual(countsWiringProblems(withGlob), []);
});

// ---- 部品そのもの（test/sourceText.ts）。今のまま通る。守る ----

/** コメントの書き方。除くのはコメントだけで、後ろの keep(5); は残る（改行は残る） */
const COMMENT_FORMS: readonly (readonly [string, string])[] = [
  ['行頭の // のコメント', '// foo(1)'],
  ['字下げした // のコメント', '  // bar(2)'],
  ['1 行のブロックコメント', '/* baz(3) */'],
  ['複数行のブロックコメント（/** … */）', '/**\n * qux(4)\n */'],
];

for (const [label, comment] of COMMENT_FORMS) {
  test(`D0024-AC-15: withoutComments は、${label}を除き、コメントに書いた呼び出しを残さない${KEEP_NOTE}`, () => {
    assert.equal(withoutComments(`${comment}\nkeep(5);`), '\nkeep(5);');
  });
}

test('D0024-AC-15: withoutComments は文字列の中の「/*」（glob）をコメントの始まりと取り違えない（今のまま通る。守る）', () => {
  const source = "const GLOB = '{state.json,*.md,logs/*.jsonl}';\ncall(1);";
  assert.equal(withoutComments(source), source);
});

test('D0024-AC-32: callArgs は関数の宣言（function・async function・export async function）を数えず、呼び出しだけを数える（今のまま通る。守る）', () => {
  const code = lines(
    'async function chooseRun(key: RunKey): Promise<void> {}',
    'export async function chooseRun(key: RunKey): Promise<void> {}',
    'function  chooseRun(key) {}',
    'await chooseRun(a);',
    'void chooseRun(b);',
    'function chooseRunAll(c) {}',
  );
  assert.deepEqual(callArgs(code, 'chooseRun'), ['a', 'b']);
});

test('D0024-AC-32: callArgs は import の行（後ろに ( が続かない）を拾わない（今のまま通る。守る）', () => {
  assert.deepEqual(callArgs("import { rememberRun, restoreRun } from './app/selection.ts';\nimport type { RunKey } from 'x';", 'rememberRun'), []);
});

const CALL_ARGS_NESTED: readonly (readonly [string, string, string, readonly string[]])[] = [
  ['入れ子のかっこ', 'rememberRun(memory, pick(key, (1)), [2]);', 'rememberRun', ['memory, pick(key, (1)), [2]']],
  ['同じ名前の入れ子の呼び出し（外 → 内の順）', 'f(f(1), 2)', 'f', ['f(1), 2', '1']],
];

for (const [label, code, name, expected] of CALL_ARGS_NESTED) {
  test(`D0024-AC-32: callArgs は、${label}も取る${KEEP_NOTE}`, () => {
    assert.deepEqual(callArgs(code, name), expected);
  });
}

test(`D0024-AC-32: callArgs はメソッドの呼び出し（loads.next()）も数える${KEEP_NOTE}`, () => {
  assert.deepEqual(callArgs('const n = loads.next();', 'next'), ['']);
});

test(`D0024-AC-32: callArgs は別の名前の一部（nextAll(・xnext(）を数えない${KEEP_NOTE}`, () => {
  assert.deepEqual(callArgs('nextAll(1);\nxnext(2);', 'next'), []);
});

const FUNCTIONS = lines(
  'function a() { if (x) { y(); } z(); }',
  'export async function load(opts: { n: number }): Promise<void> { return; }',
  'function b() {}',
);

/** [見出し, 読む文字, 関数の名前, 本体（取れなければ null)] */
const FUNCTION_BODIES: readonly (readonly [string, string, string, string | null])[] = [
  ['入れ子の { } を釣り合いで取り、本体だけを返す', FUNCTIONS, 'a', ' if (x) { y(); } z(); '],
  ['async・export・引数の型の { } があっても本体だけを返す', FUNCTIONS, 'load', ' return; '],
  ['中身が空の本体は空の文字を返す', FUNCTIONS, 'b', ''],
  ['名前の前方一致（renderViewBody）で別の関数を拾わず null を返す', 'function renderViewBody() { x(); }', 'render', null],
  ['const の矢印関数を関数と数えず null を返す', 'const render = () => { x(); };', 'render', null],
  ['{ } が釣り合わなければ null を返す', 'function render() { if (x) { y(); }', 'render', null],
];

for (const [label, code, name, expected] of FUNCTION_BODIES) {
  test(`D0024-AC-30: functionBody：${label}（${name}）${KEEP_NOTE}`, () => {
    assert.equal(functionBody(code, name), expected);
  });
}

/** [見出し, 読む文字, head, 中身（取れなければ null)] */
const BLOCKS: readonly (readonly [string, string, RegExp, string | null])[] = [
  ['head に合った所のあとから、釣り合う } の前までを取る。入れ子の { } も 1 つに数える', 'if (!target) { if (a) { b(); } c(); } d();', /if \(!target\) \{/, ' if (a) { b(); } c(); '],
  ['中身が空のブロックは空の文字を返す', 'x(() => {})', /x\(\(\) => \{/, ''],
  ['合う所が無ければ null を返す', 'if (a) { b(); }', /if \(!target\) \{/, null],
  ['{ } が釣り合わなければ null を返す', 'if (a) { b(); ', /if \(a\) \{/, null],
  ['最初に合った所だけを取る', 'if (a) { first(); } if (a) { second(); }', /if \(a\) \{/, ' first(); '],
];

for (const [label, code, head, expected] of BLOCKS) {
  test(`D0024-AC-30: blockAfter：${label}${KEEP_NOTE}`, () => {
    assert.equal(blockAfter(code, head), expected);
  });
}

test(`D0024-AC-30: blockAfter は { で終わらない head（使い方の誤り）を例外にし、見逃して null を返さない${KEEP_NOTE}`, () => {
  assert.throws(() => blockAfter('if (a) { b(); }', /if \(a\)/), /blockAfter/);
});

/** [見出し, 読む文字, 正規表現の並び, 順に並ぶか] */
const IN_ORDER: readonly (readonly [string, string, readonly RegExp[], boolean])[] = [
  ['最初の出現が渡した順に並べば真を返す', 'a(); b(); c();', [/\ba\(/, /\bb\(/, /\bc\(/], true],
  ['順が違えば偽を返す', 'b(); a();', [/\ba\(/, /\bb\(/], false],
  ['どれかが無ければ偽を返す', 'a(); c();', [/\ba\(/, /\bb\(/], false],
  ['並びが空なら真を返す', 'a();', [], true],
  ['後ろに同じ語がもう 1 度あっても、最初の出現が逆なら偽を返す（render() が後ろの枝に何度もあっても順の誤りを隠さない）', 'render(); selectWaiting(); render();', [/\bselectWaiting\(/, /\brender\(/], false],
  ['後ろに同じ語がもう 1 度あっても、最初の出現が順どおりなら真を返す', 'selectWaiting(); render(); render();', [/\bselectWaiting\(/, /\brender\(/], true],
];

for (const [label, text, parts, expected] of IN_ORDER) {
  test(`D0024-AC-30: inOrder：${label}${KEEP_NOTE}`, () => {
    assert.equal(inOrder(text, parts), expected);
  });
}

// g 旗のある正規表現は、同じものを使い回すと前の検索の位置（lastIndex）が残る。使い回して 2 度呼んでも同じ結果になること。
test(`D0024-AC-30: inOrder は g 旗のある正規表現でも、前の検索の位置を引きずらない（同じ正規表現で 2 度呼んでも同じ結果）${KEEP_NOTE}`, () => {
  const parts = [/\ba\(/g, /\bb\(/g];
  assert.deepEqual([inOrder('a(); b();', parts), inOrder('a(); b();', parts)], [true, true]);
});

test(`D0024-AC-30: blockAfter は g 旗のある head でも、前の検索の位置を引きずらない（同じ正規表現で 2 度呼んでも同じ結果）${KEEP_NOTE}`, () => {
  const head = /if \(a\) \{/g;
  assert.deepEqual([blockAfter('if (a) { b(); }', head), blockAfter('if (a) { b(); }', head)], [' b(); ', ' b(); ']);
});
