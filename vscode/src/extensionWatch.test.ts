// 入口 extension.ts の配線の検査（D0034：work_dir がまだ無いときの最初の実行）。AC-09・12・17・19〜25・30・32・37・43。
// extension.ts は vscode を import するので、単体では動かせない。判断を持たない呼び出しの形を、ソースを文字で読んで確かめる
// （extensionCounts.test.ts と同じ作り。文字で読む部品は test/sourceText.ts に置く）。
// ここで見るのは配線だけ：何を呼ぶか・どの順に呼ぶか・どこに書くか。有無の判断・手順・見張りの持ち方は app/workDirWatch.ts のテストが見る。
// 構成：1) 検査の本体  2) 実物の extension.ts  3) 検査そのもの（配線がそろった見本・壊した見本・コメントに書いただけの見本）。
// 3) は今のまま通る（赤ではなく、守り続けるために置く）。2) は ID ごとに 1 テスト：テスト先行のときに配線がまだ無かった ID は赤だった（今は緑）。そのときから通っていた ID は「守る」と書いた。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { blockAfter, callArgs, functionBody, inOrder, withoutComments } from './test/sourceText.ts';

// ---- 1) 検査の本体 ----------------------------------------------------------------

const WATCH_IDS = [
  'separateGenerations', 'checkerCollaborators', 'holderGetsSchedule', 'scheduleDebounces', 'noDirectEvents',
  'presenceNotPoll', 'twoPollers', 'startInRetarget', 'stopInNoTarget', 'stopInDeactivate',
  'retargetOrder', 'firstCheckNow', 'stopWatchingResets', 'deactivateNextChecks', 'disposeNextChecks', 'retargetNoRender',
  'configRetargets', 'checkArgIsTargetAbs', 'noStatInExt', 'workDirSingleSource', 'watcherBase',
  'twoWatchers', 'patternsShape', 'remoteGlobValue', 'remoteCalls',
  'noJudgmentInExt', 'headerComment',
] as const;
type WatchWiringId = (typeof WATCH_IDS)[number];

const NO_TARGET_HEAD = /if \(!target\) \{/;
const PRESENCE_WORDS = /presence|PRESENCE_CHECK_MS|checkWorkDir/i;
const PRESENCE_START = /\bpresencePoller\.start\(\)/;
const PRESENCE_STOP = /\bpresencePoller\.stop\(\)/;
const CHECKS_NEXT = /\bchecks\.next\(\)/;
const STOP_WATCHING = /\bstopWatching\(\)/;
const PLAIN_POLLER_STOP = /\bpoller\.stop\(\)/;
const STATE_WORD = /(['"])(?:present|absent|unknown)\1/;
/** 'workDir' の設定を読む呼び出し（pipesDir は数えない） */
const WORK_DIR_SETTING = /^\s*'workDir'/;

const has = (text: string | null, re: RegExp): boolean => text !== null && re.test(text);
const count = (text: string | null, re: RegExp): number => (text === null ? 0 : Array.from(text.matchAll(new RegExp(re.source, 'g'))).length);
const calls = (text: string | null, name: string): string[] => (text === null ? [] : callArgs(text, name));

/** 最初の import より前の、行頭の // のコメント（冒頭のコメント） */
function headerComment(source: string): string {
  const out: string[] = [];
  for (const line of source.split('\n')) {
    if (/^import\b/.test(line)) break;
    if (line.trimStart().startsWith('//')) out.push(line);
  }
  return out.join('\n');
}

/** './app/workDirWatch.ts' から import している名前（並べ替え済み。import が無ければ空） */
function importedFromWatch(code: string): string[] {
  const names: string[] = [];
  for (const m of code.matchAll(/import\s+(?:type\s+)?\{([^}]*)\}\s*from\s*'\.\/app\/workDirWatch\.ts'/g)) {
    names.push(...(m[1] ?? '').split(',').map((s) => s.trim().replace(/^type\s+/, '')).filter((s) => s !== ''));
  }
  return names.sort();
}

/** createWorkDirWatcher の本体が、引数 dir から Uri を作った変数を RelativePattern の第 1 引数にし、第 2 引数が WATCH_GLOB で、target・root・workspaceFolders を読まないか */
function watcherBaseIsDir(body: string | null): boolean {
  if (body === null) return false;
  const base = /\bconst\s+(\w+)\s*=\s*vscode\.Uri\.file\(\s*dir\s*\)/.exec(body);
  if (base === null) return false;
  const patterns = callArgs(body, 'RelativePattern');
  if (patterns.length !== 1) return false;
  const [first, second] = (patterns[0] ?? '').split(',').map((s) => s.trim());
  return first === base[1] && second === 'WATCH_GLOB' && !/\b(?:target|root|workspaceFolders)\b/.test(body);
}

/** 配線で欠けている・守られていないもの。空なら全部そろっている。 */
function watchWiringProblems(source: string): WatchWiringId[] {
  const code = withoutComments(source);
  const render = functionBody(code, 'render');
  const showRun = functionBody(code, 'showRun');
  const updatePolling = functionBody(code, 'updatePolling');
  const retarget = functionBody(code, 'retarget');
  const deactivate = functionBody(code, 'deactivate');
  const stopWatching = functionBody(code, 'stopWatching');
  const schedule = functionBody(code, 'schedule');
  const currentWorkDir = functionBody(code, 'currentWorkDir');
  const createWatcher = functionBody(code, 'createWorkDirWatcher');
  const noTarget = retarget === null ? null : blockAfter(retarget, NO_TARGET_HEAD);
  const retargetOutside = retarget === null || noTarget === null ? null : retarget.replace(noTarget, '');
  const disposeBlock = blockAfter(code, /\{\s*dispose:\s*\(\)\s*=>\s*\{/);
  const config = blockAfter(code, /onDidChangeConfiguration\(\(event\) => \{/);
  const panelDispose = blockAfter(code, /created\.onDidDispose\(\(\) => \{/);
  const watcherCalls = callArgs(code, 'createFileSystemWatcher').map((a) => a.trim());
  const pollerCalls = callArgs(code, 'createPoller');
  const pollCalls = calls(updatePolling, 'shouldPoll');
  const holderCalls = callArgs(code, 'createWatchHolder');
  const checkerCalls = callArgs(code, 'createWorkDirChecker');
  const checkCalls = callArgs(code, 'check');
  const settingReads = callArgs(code, 'readSetting').filter((a) => WORK_DIR_SETTING.test(a));
  const isRenderPoller = (a: string): boolean => /\bintervalMs:\s*POLL_MS\b/.test(a) && /\brun:\s*\(\)\s*=>\s*render\(\)/.test(a);
  const isCheckPoller = (a: string): boolean => /\bintervalMs:\s*PRESENCE_CHECK_MS\b/.test(a) && /\brun:\s*\(\)\s*=>\s*checkWorkDir\(\)/.test(a);
  const imported = importedFromWatch(code);

  const ok: Record<WatchWiringId, boolean> = {
    // AC-12：確かめの世代は、読み込みの世代とは別
    separateGenerations:
      callArgs(code, 'createGeneration').length === 2 &&
      count(code, /\bconst\s+checks\s*=\s*createGeneration\(\)\s*;/) === 1 &&
      count(code, /\bconst\s+loads\s*=\s*createGeneration\(\)\s*;/) === 1 &&
      checkerCalls.length === 1 &&
      /\bgeneration:\s*checks\b/.test(checkerCalls[0] ?? ''),
    // AC-09・24：確かめの手順に渡す 3 つの口。holder は createWatchHolder( の戻り（dirWatch）、probe は dirPresence、reload は render（空にすると最初の読み直しも張ったあとの読み直しも起きない）
    checkerCollaborators:
      checkerCalls.length === 1 &&
      /\bholder:\s*dirWatch\b/.test(checkerCalls[0] ?? '') &&
      /\bprobe:\s*dirPresence\b/.test(checkerCalls[0] ?? '') &&
      /\breload:\s*\(\)\s*=>\s*render\(\)(?=\s*[,}])/.test(checkerCalls[0] ?? '') &&
      count(code, /\bconst\s+dirWatch\s*=\s*createWatchHolder\(/) === 1,
    // AC-17：3 つの知らせは 1 つの受け口（schedule）へ
    holderGetsSchedule: holderCalls.length === 1 && /\bonEvent:\s*schedule\b/.test(holderCalls[0] ?? '') && /\bcreate:\s*createWorkDirWatcher\b/.test(holderCalls[0] ?? ''),
    scheduleDebounces: has(schedule, /\bsetTimeout\(/) && has(schedule, /\bDEBOUNCE_MS\b/),
    noDirectEvents: count(code, /\.onDidCreate\(/) === 1 && count(code, /\.onDidChange\(/) === 1 && count(code, /\.onDidDelete\(/) === 1,
    // AC-19・20：約 5 秒の読み直しは変えず、確かめは別のタイマー
    presenceNotPoll: updatePolling !== null && !PRESENCE_WORDS.test(updatePolling) && pollCalls.every((args) => !PRESENCE_WORDS.test(args)),
    twoPollers:
      pollerCalls.length === 2 &&
      ((isRenderPoller(pollerCalls[0] ?? '') && isCheckPoller(pollerCalls[1] ?? '')) || (isCheckPoller(pollerCalls[0] ?? '') && isRenderPoller(pollerCalls[1] ?? ''))),
    // AC-21：始めるのは retarget の「見る先がある」枝だけ。止めるのは見る先が無い枝と deactivate
    startInRetarget: count(code, PRESENCE_START) === 1 && has(retargetOutside, PRESENCE_START) && !has(noTarget, PRESENCE_START),
    stopInNoTarget: has(noTarget, PRESENCE_STOP) && has(noTarget, PLAIN_POLLER_STOP),
    stopInDeactivate: has(deactivate, PRESENCE_STOP),
    // AC-22：見る先が決まったら、世代を進め、見張りを外し、確かめを始めて、その場で 1 回確かめる。読み直しは部品がする（retarget は読まない）
    retargetOrder: retarget !== null && inOrder(retarget, [CHECKS_NEXT, STOP_WATCHING, PRESENCE_START, /\bcheckWorkDir\(\)/]),
    firstCheckNow: has(retarget, /\bvoid\s+checkWorkDir\(\)\s*;/) && !has(retarget, /\bsetTimeout\b/),
    stopWatchingResets: has(stopWatching, /\bworkDirChecker\.reset\(\)/),
    deactivateNextChecks: deactivate !== null && inOrder(deactivate, [/\bpanel\?\.dispose\(\)/, CHECKS_NEXT]),
    disposeNextChecks: disposeBlock !== null && inOrder(disposeBlock, [CHECKS_NEXT, STOP_WATCHING]),
    retargetNoRender: retarget !== null && !/\brender\(/.test(retarget),
    // AC-23：設定とフォルダの変更は retarget() を呼ぶ
    configRetargets:
      config !== null &&
      config.includes("settingKeys('workDir')") &&
      /\bretarget\(\)/.test(config) &&
      /onDidChangeWorkspaceFolders\(\(\)\s*=>\s*retarget\(\)\)/.test(code),
    // AC-24：確かめる work_dir は target.abs ただ 1 つ。入口は stat も isDirectory も書かない
    checkArgIsTargetAbs: checkCalls.length === 1 && /^(?:t|target)\.abs$/.test((checkCalls[0] ?? '').trim()),
    noStatInExt: ['stat', 'isDirectory', 'dirPresence'].every((name) => callArgs(code, name).length === 0),
    workDirSingleSource: settingReads.length === 1 && calls(currentWorkDir, 'readSetting').filter((a) => WORK_DIR_SETTING.test(a)).length === 1,
    // AC-25：見張りの基準は引数 dir から作った変数
    watcherBase: watcherBaseIsDir(createWatcher),
    // AC-30・32：別の worktree の見張りは今のまま。いまの work_dir 用は基準を変数で渡す
    twoWatchers: watcherCalls.length === 2,
    patternsShape:
      watcherCalls.length === 2 &&
      watcherCalls.filter((a) => /^new (?:vscode\.)?RelativePattern\(\s*\w+\s*,\s*WATCH_GLOB\s*\)$/.test(a)).length === 1 &&
      watcherCalls.filter((a) => /^new (?:vscode\.)?RelativePattern\(\s*\w+\s*,\s*REMOTE_WATCH_GLOB\s*\)$/.test(a)).length === 1,
    remoteGlobValue: /\bconst\s+REMOTE_WATCH_GLOB\s*=\s*'\{state\.json,\*\.md,logs\/\*\.jsonl\}'\s*;/.test(code),
    remoteCalls:
      calls(render, 'watchRemote').filter((a) => a.trim() === 'panel !== undefined ? otherDir : null').length === 1 &&
      calls(showRun, 'watchRemote').filter((a) => a.trim() === 'current.otherDir').length === 1 &&
      calls(panelDispose, 'watchRemote').filter((a) => a.trim() === 'null').length === 1 &&
      calls(stopWatching, 'watchRemote').filter((a) => a.trim() === 'null').length === 1,
    // AC-37：判断は入口に置かない
    noJudgmentInExt:
      callArgs(code, 'decideWatch').length === 0 &&
      callArgs(code, 'finishStep').length === 0 &&
      !STATE_WORD.test(code) &&
      imported.length === 2 &&
      imported[0] === 'createWatchHolder' &&
      imported[1] === 'createWorkDirChecker',
    // AC-43：冒頭のコメント
    headerComment: /無いあいだは\s*0\s*個/.test(headerComment(source)) && /有れば\s*1\s*個/.test(headerComment(source)) && !/監視は\s*1\s*つ/.test(headerComment(source)),
  };
  return WATCH_IDS.filter((id) => !ok[id]);
}

// ---- 2) 実物の extension.ts ---------------------------------------------------------

const EXTENSION = readFileSync(new URL('./extension.ts', import.meta.url), 'utf8');

interface Wiring {
  id: WatchWiringId;
  /** テスト名の頭に付ける AC の番号（ID ごとに 1 つ以上） */
  acs: readonly number[];
  what: string;
  /** 今の extension.ts でも通る（守り続けるための検査） */
  keep?: true;
}

const WIRING: readonly Wiring[] = [
  { id: 'separateGenerations', acs: [12], what: '確かめの世代 checks を、読み込みの世代 loads とは別に createGeneration( で作り、createWorkDirChecker( に generation: checks を渡す' },
  { id: 'checkerCollaborators', acs: [9, 24], what: 'createWorkDirChecker( に holder: dirWatch（createWatchHolder( の戻り）・probe: dirPresence・reload: () => render() を渡す（reload が空だと最初の読み直しも張ったあとの読み直しも起きない）' },
  { id: 'holderGetsSchedule', acs: [17], what: 'createWatchHolder( に onEvent: schedule と create: createWorkDirWatcher を渡す' },
  { id: 'scheduleDebounces', acs: [17], what: 'schedule の本体が setTimeout と DEBOUNCE_MS でまとめる', keep: true },
  { id: 'noDirectEvents', acs: [17], what: '.onDidCreate(・.onDidChange(・.onDidDelete( を結ぶのは別の worktree の見張り 1 か所だけ（いまの work_dir の見張りは部品が結ぶ）' },
  { id: 'presenceNotPoll', acs: [19], what: 'updatePolling の本体と shouldPoll( の引数に、有無の確かめ（presence・PRESENCE_CHECK_MS・checkWorkDir）を入れない', keep: true },
  { id: 'twoPollers', acs: [20], what: 'createPoller( をちょうど 2 つ作る：約 5 秒の読み直し（intervalMs: POLL_MS・run: () => render()）と、確かめ（intervalMs: PRESENCE_CHECK_MS・run: () => checkWorkDir()）' },
  { id: 'startInRetarget', acs: [21], what: 'presencePoller.start() を extension.ts の 1 か所だけ、retarget の「見る先がある」枝（if (!target) { の外）で呼ぶ' },
  { id: 'stopInNoTarget', acs: [21], what: 'retarget の target が無い枝で presencePoller.stop() も poller.stop() も呼ぶ' },
  { id: 'stopInDeactivate', acs: [21], what: 'deactivate で presencePoller.stop() を呼ぶ' },
  { id: 'retargetOrder', acs: [22], what: 'retarget が checks.next() → stopWatching() → presencePoller.start() → checkWorkDir() の順に進める' },
  { id: 'firstCheckNow', acs: [22], what: 'retarget が void checkWorkDir(); で最初の確かめをその場で 1 回する（setTimeout に包まない）' },
  { id: 'stopWatchingResets', acs: [22], what: 'stopWatching が workDirChecker.reset() を呼ぶ' },
  { id: 'deactivateNextChecks', acs: [22], what: 'deactivate が panel?.dispose() のあとに checks.next() で途中の確かめの結果を捨てる' },
  { id: 'disposeNextChecks', acs: [22], what: '購読の { dispose: () => { checks.next(); stopWatching(); } } が checks.next() を stopWatching() より前に呼ぶ' },
  { id: 'retargetNoRender', acs: [9], what: 'retarget の本体で render( を呼ばない（最初の読み直しは手順の部品がする）' },
  { id: 'configRetargets', acs: [23], what: '設定 workDir の変更とワークスペースのフォルダの変更の購読が retarget() を呼ぶ', keep: true },
  { id: 'checkArgIsTargetAbs', acs: [24], what: '.check( の呼び出しをちょうど 1 つにし、引数を t.abs か target.abs だけにする' },
  { id: 'noStatInExt', acs: [24], what: 'stat(・isDirectory(・dirPresence( を呼ばない（probe: dirPresence と渡すだけ）', keep: true },
  { id: 'workDirSingleSource', acs: [24], what: "readSetting('workDir' …) の呼び出しを currentWorkDir の本体の 1 か所だけにする", keep: true },
  { id: 'watcherBase', acs: [25], what: 'createWorkDirWatcher の本体が、引数 dir から Uri.file(dir) の変数を作って RelativePattern( の第 1 引数にし、第 2 引数を WATCH_GLOB にして、target・root・workspaceFolders を読まない' },
  { id: 'twoWatchers', acs: [30], what: 'createFileSystemWatcher( の呼び出しをちょうど 2 つにする', keep: true },
  { id: 'patternsShape', acs: [30, 32], what: 'createFileSystemWatcher( の引数を、RelativePattern(<識別子>, WATCH_GLOB) が 1 つ（間に ) を挟まない）、RelativePattern(<識別子>, REMOTE_WATCH_GLOB) が 1 つにする', keep: true },
  { id: 'remoteGlobValue', acs: [30], what: "REMOTE_WATCH_GLOB の値を '{state.json,*.md,logs/*.jsonl}' のままにする", keep: true },
  { id: 'remoteCalls', acs: [30], what: 'watchRemote( を render（panel !== undefined ? otherDir : null）・showRun（current.otherDir）・パネルの onDidDispose（null）・stopWatching（null）の 4 か所で、1 つずつ呼ぶ', keep: true },
  { id: 'noJudgmentInExt', acs: [37], what: "decideWatch(・finishStep( を呼ばず、'present'・'absent'・'unknown' の文字を持たず、workDirWatch.ts から import するのは createWatchHolder と createWorkDirChecker だけにする" },
  { id: 'headerComment', acs: [43], what: '冒頭のコメントを「無いあいだは 0 個、有れば 1 個」と読める文にし、「監視は1つ」を残さない' },
];

const KEEP_NOTE = '（今のまま通る。守る）';

/** AC の番号を 2 桁にそろえる（記録の D0034-AC-09 と同じ書き方。1 桁だと記録に無い ID になる） */
const pad = (ac: number): string => String(ac).padStart(2, '0');

const acsOf = (id: WatchWiringId): readonly number[] => {
  const found = WIRING.find((w) => w.id === id);
  if (found === undefined) throw new Error(`WIRING に ${id} が無い`);
  return found.acs;
};
/** 見つける ID の、テスト名に付ける AC の番号（先頭の 1 つ。2 桁） */
const firstAc = (id: WatchWiringId): string => pad(acsOf(id)[0] ?? 0);

test(`D0034-AC-20: 配線の検査の表そのもの：表の ID の並びは、検査する ID の一覧と同じ${KEEP_NOTE}`, () => {
  assert.deepEqual(WIRING.map((w) => w.id), [...WATCH_IDS]);
});

test(`D0034-AC-20: 配線の検査の表そのもの：検査する ID は重複せず 27 個${KEEP_NOTE}`, () => {
  assert.deepEqual([new Set(WATCH_IDS).size, WATCH_IDS.length], [27, 27]);
});

// 失敗の文は、ある・無いのどちらにも寄らない言い方にする（「あってはいけない形がある」ときも、「あるはずの形が無い」ときも落ちる）。
for (const { id, acs, what, keep } of WIRING) {
  for (const ac of acs) {
    test(`D0034-AC-${pad(ac)}: extension.ts は ${what}（${id}）${keep ? KEEP_NOTE : ''}`, () => {
      assert.ok(!watchWiringProblems(EXTENSION).includes(id), `配線の約束を守っていない（${id}）：extension.ts は ${what}`);
    });
  }
}

/**
 * 検査が本体を読む関数と、その本体にあるはずの語（取れない・語が無いなら、読めないのであって赤の理由にならない）。
 * 3 つ目は、その本体を読んで支える AC の番号（失敗の名前が、直す先の AC を指すように）。表そのものの確かめ（ID の並び・数など）は、
 * どの AC にも属さないので、配線の表を持つ AC-20 の頭を付けた。
 */
const READABLE_BODIES: readonly (readonly [string, string, number])[] = [
  ['stopWatching', 'watchRemote(', 30],
  ['checkWorkDir', 'workDirChecker.check(', 24],
  ['createWorkDirWatcher', 'createFileSystemWatcher(', 25],
  ['schedule', 'setTimeout(', 17],
  ['retarget', 'createFsRunsSource(', 22],
  ['deactivate', 'poller.stop()', 21],
  ['currentWorkDir', 'readSetting(', 24],
  ['updatePolling', 'shouldPoll(', 19],
  ['render', 'statusBarLabel(', 30],
  ['showRun', 'createWebviewPanel(', 30],
];

for (const [name, word, ac] of READABLE_BODIES) {
  test(`D0034-AC-${pad(ac)}: 配線の検査そのもの：実物の extension.ts から ${name} の本体を取れる（${word} を含む。読めないから通る、にしない）${name === 'checkWorkDir' || name === 'createWorkDirWatcher' ? '' : KEEP_NOTE}`, () => {
    const body = functionBody(withoutComments(EXTENSION), name);
    assert.ok(body !== null && body.includes(word), `${name} の本体が取れない（${word} を含むはず）`);
  });
}

/**
 * 検査が枝として取り出すブロック。word があれば、その語が中にあるはず（無ければ、取れること）。
 * within があれば、その関数の本体の中で取る（ファイル全体の最初の一致だと、別の関数の同じ形を読んでしまう）。
 */
const READABLE_BLOCKS: readonly (readonly [string, number, string | null, RegExp, string | null])[] = [
  ['パネルの onDidDispose の中身', 30, null, /created\.onDidDispose\(\(\) => \{/, 'watchRemote(null)'],
  ['onDidChangeConfiguration の中身', 23, null, /onDidChangeConfiguration\(\(event\) => \{/, "settingKeys('workDir')"],
  ['retarget の if (!target) { のブロック', 21, 'retarget', /if \(!target\) \{/, 'poller.stop()'],
];

for (const [label, ac, within, head, word] of READABLE_BLOCKS) {
  test(`D0034-AC-${pad(ac)}: 配線の検査そのもの：実物の extension.ts から ${label} を取れる（読めないから通る、にしない）${KEEP_NOTE}`, () => {
    const code = withoutComments(EXTENSION);
    const scope: string = within === null ? code : (functionBody(code, within) ?? '');
    const block = blockAfter(scope, head);
    assert.ok(block !== null && (word === null || block.includes(word)), `${label} が取れない${word === null ? '' : `（${word} を含むはず）`}`);
  });
}

// ---- 3) 検査そのもの ---------------------------------------------------------------

const lines = (...rows: string[]): string => rows.join('\n');

/** 配線がそろっている見本のソース（関数ごとに短く写したもの）。1 つの部品を差し替えて、欠けた見本を作る。 */
const PIECES = {
  header: lines(
    '// 入口：vscode に触れる唯一のファイル。',
    '// いまの work_dir の見張りは、無いあいだは 0 個、有れば 1 個（別の worktree の見張りは別に足す）。',
    '// 無いあいだは決まった間隔で有無だけを確かめ、できたら張って読み直す。',
  ),
  imports: lines(
    "import { DEBOUNCE_MS, POLL_MS, PRESENCE_CHECK_MS, WATCH_GLOB, createGeneration, createPoller, shouldPoll } from './app/refreshPolicy.ts';",
    "import { createWatchHolder, createWorkDirChecker } from './app/workDirWatch.ts';",
    "import { dirPresence } from './infra/fsPresence.ts';",
  ),
  glob: "const REMOTE_WATCH_GLOB = '{state.json,*.md,logs/*.jsonl}';",
  state: lines('let panel: vscode.WebviewPanel | undefined;', 'let target: WorkDirTarget | null = null;', 'let timer: ReturnType<typeof setTimeout> | undefined;'),
  generations: lines('const loads = createGeneration();', 'const checks = createGeneration();'),
  poller: lines(
    'const poller = createPoller({',
    '  intervalMs: POLL_MS,',
    '  run: () => render(),',
    '  setTimer: (fn, ms) => setTimeout(fn, ms),',
    '  clearTimer: (handle) => clearTimeout(handle),',
    '});',
  ),
  holder: lines(
    'const dirWatch = createWatchHolder({ create: createWorkDirWatcher, onEvent: schedule });',
    'const workDirChecker = createWorkDirChecker({ generation: checks, holder: dirWatch, probe: dirPresence, reload: () => render() });',
  ),
  presencePoller: lines(
    'const presencePoller = createPoller({',
    '  intervalMs: PRESENCE_CHECK_MS,',
    '  run: () => checkWorkDir(),',
    '  setTimer: (fn, ms) => setTimeout(fn, ms),',
    '  clearTimer: (handle) => clearTimeout(handle),',
    '});',
  ),
  activate: lines(
    'export function activate(context: vscode.ExtensionContext): void {',
    '  context.subscriptions.push(',
    '    statusItem,',
    '    vscode.workspace.onDidChangeConfiguration((event) => {',
    "      if (settingKeys('workDir').some((key) => event.affectsConfiguration(key))) retarget();",
    '      else if (event.affectsConfiguration(`${SECTION}.${SETTING_SHOW_OTHER}`)) void render();',
    '    }),',
    '    vscode.workspace.onDidChangeWorkspaceFolders(() => retarget()),',
    '    { dispose: () => { checks.next(); stopWatching(); } },',
    '  );',
    '  retarget();',
    '}',
  ),
  readSetting: lines('function readSetting(key: string, fallback: string): string {', '  return fallback;', '}'),
  deactivate: lines(
    'export function deactivate(): void {',
    '  poller.stop();',
    '  presencePoller.stop();',
    '  panel?.dispose();',
    '  panel = undefined;',
    '  stopWatching();',
    '  loads.next();',
    '  checks.next();',
    '}',
  ),
  currentWorkDir: lines(
    'function currentWorkDir(): WorkDirTarget | null {',
    '  const folder = vscode.workspace.workspaceFolders?.[0];',
    '  if (!folder) return null;',
    "  const setting = readSetting('workDir', DEFAULT_WORK_DIR).trim() || DEFAULT_WORK_DIR;",
    '  const abs = resolveWorkDir(folder.uri.fsPath, setting);',
    '  return { abs, display: abs, root: folder.uri.fsPath, setting };',
    '}',
  ),
  stopWatching: lines(
    'function stopWatching(): void {',
    '  if (timer !== undefined) clearTimeout(timer);',
    '  timer = undefined;',
    '  workDirChecker.reset();',
    '  watchRemote(null);',
    '}',
  ),
  createWatcher: lines(
    'function createWorkDirWatcher(dir: string): vscode.FileSystemWatcher {',
    '  const workDirUri = vscode.Uri.file(dir);',
    '  return vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(workDirUri, WATCH_GLOB));',
    '}',
  ),
  checkWorkDir: lines(
    'async function checkWorkDir(): Promise<void> {',
    '  const t = target;',
    '  if (!t) return;',
    '  await workDirChecker.check(t.abs);',
    '}',
  ),
  watchRemote: lines(
    'function watchRemote(dir: string | null): void {',
    '  if (dir === remoteDir) return;',
    '  remoteWatcher?.dispose();',
    '  remoteWatcher = undefined;',
    '  remoteDir = dir;',
    '  if (dir === null) return;',
    '  const remoteUri = vscode.Uri.file(dir);',
    '  remoteWatcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(remoteUri, REMOTE_WATCH_GLOB));',
    '  remoteWatcher.onDidCreate(schedule);',
    '  remoteWatcher.onDidChange(schedule);',
    '  remoteWatcher.onDidDelete(schedule);',
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
    '  checks.next();',
    '  stopWatching();',
    '  target = currentWorkDir();',
    '  if (!target) {',
    '    runsSource = null;',
    '    poller.stop();',
    '    presencePoller.stop();',
    '    statusItem?.hide();',
    '    return;',
    '  }',
    '  runsSource = createFsRunsSource(target.root, target.abs, target.setting);',
    '  statusItem?.show();',
    '  presencePoller.stop();',
    '  presencePoller.start();',
    '  void checkWorkDir();',
    '}',
  ),
  schedule: lines(
    'function schedule(): void {',
    '  if (timer !== undefined) clearTimeout(timer);',
    '  timer = setTimeout(() => {',
    '    timer = undefined;',
    '    void render();',
    '  }, DEBOUNCE_MS);',
    '}',
  ),
  render: lines(
    'async function render(): Promise<void> {',
    '  const current = await loadLatest();',
    '  if (!current) return;',
    '  const { otherDir, live } = current;',
    '  statusItem.text = statusBarLabel(view, listView).text;',
    '  watchRemote(panel !== undefined ? otherDir : null);',
    '  updatePolling(live);',
    '}',
  ),
  showRun: lines(
    'async function showRun(): Promise<void> {',
    '  const created = vscode.window.createWebviewPanel(VIEW_IDS.run, NAME, vscode.ViewColumn.Beside, {});',
    '  created.onDidDispose(() => {',
    '    if (panel === created) {',
    '      panel = undefined;',
    '      poller.stop();',
    '      watchRemote(null);',
    '      void render();',
    '    }',
    '  });',
    '  const mine = loads.next();',
    '  const current = await currentView();',
    '  if (loads.isCurrent(mine)) {',
    '    watchRemote(current.otherDir);',
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

test(`D0034-AC-20: 配線の検査そのもの：配線がそろった見本は見逃す（何も見つけない）${KEEP_NOTE}`, () => {
  assert.deepEqual(watchWiringProblems(sampleWith()), []);
});

interface Broken {
  id: WatchWiringId;
  /** 「…した見本は、見つける」の前半 */
  label: string;
  over: Over;
  /** その壊し方で、同時に見つかるのが当然のほかの ID（理由はテストの上のコメント） */
  also?: readonly WatchWiringId[];
}

const RT = PIECES.retarget;
const DEACT = PIECES.deactivate;
const UP = PIECES.updatePolling;
const R = PIECES.render;
const SHOW = PIECES.showRun;
const STOP = PIECES.stopWatching;
const REMOTE = PIECES.watchRemote;
const ACTIVATE = PIECES.activate;
const HEADER_COMMENT = '// いまの work_dir の見張りは、無いあいだは 0 個、有れば 1 個。';

// 見本は ID ごとに 1 つ以上。見つけるのはその ID だけ（deepEqual）。ただし次の組は、片方が欠ければ必ずもう片方も欠ける作りなので、also に書く：
//   startInRetarget の「updatePolling でも start する」見本は、updatePolling の本体に presence の語が入るので presenceNotPoll も欠ける、
//   startInRetarget の「start を呼ばない」見本は、順の検査 retargetOrder にも start が無い、
//   firstCheckNow の「checkWorkDir( を呼ばない」見本は、retargetOrder にも checkWorkDir( が無い、
//   twoWatchers の見張りを増やす・減らす見本は、patternsShape（ちょうど 2 つ）にも当たる、
//   watcherBase の「WATCH_GLOB を REMOTE_WATCH_GLOB にする」見本は、patternsShape（WATCH_GLOB が 1 つ）にも当たる、
//   RelativePattern( の基準を関数呼びにする見本は、patternsShape（基準は識別子だけ。AC-32）にも当たる。
const BROKEN: readonly Broken[] = [
  // AC-12
  { id: 'separateGenerations', label: 'checks の世代を作らない（loads だけ）', over: { generations: 'const loads = createGeneration();' } },
  { id: 'separateGenerations', label: 'createWorkDirChecker( に loads を使い回す（generation: loads）', over: { holder: swap(PIECES.holder, 'generation: checks', 'generation: loads') } },
  { id: 'separateGenerations', label: '世代を 3 つ作る', over: { extra: 'const third = createGeneration();' } },
  // AC-09・24：確かめの手順に渡す口
  { id: 'checkerCollaborators', label: '読み直しの口 reload を何もしない関数（() => Promise.resolve()）にする', over: { holder: swap(PIECES.holder, 'reload: () => render()', 'reload: () => Promise.resolve()') } },
  { id: 'checkerCollaborators', label: '読み直しの口 reload を render でなく別の関数にする', over: { holder: swap(PIECES.holder, 'reload: () => render()', 'reload: () => other()') } },
  { id: 'checkerCollaborators', label: '読み直しの口 reload を結果を捨てる形（() => void render()）にする', over: { holder: swap(PIECES.holder, 'reload: () => render()', 'reload: () => void render()') } },
  { id: 'checkerCollaborators', label: '確かめの口 probe を dirPresence でなく別の関数にする', over: { holder: swap(PIECES.holder, 'probe: dirPresence', 'probe: otherProbe') } },
  { id: 'checkerCollaborators', label: '見張りを持つ部品 holder に dirWatch でなく別の変数を渡す', over: { holder: swap(PIECES.holder, 'holder: dirWatch', 'holder: otherHolder') } },
  {
    id: 'checkerCollaborators',
    label: 'createWorkDirChecker( を 2 回呼ぶ',
    over: { extra: 'const again = createWorkDirChecker({ generation: checks, holder: dirWatch, probe: dirPresence, reload: () => render() });' },
    also: ['separateGenerations'],
  },
  // AC-17
  { id: 'holderGetsSchedule', label: 'onEvent に schedule を渡さない', over: { holder: swap(PIECES.holder, 'onEvent: schedule', 'onEvent: () => undefined') } },
  { id: 'holderGetsSchedule', label: 'create に createWorkDirWatcher を渡さない', over: { holder: swap(PIECES.holder, 'create: createWorkDirWatcher', 'create: (dir) => other(dir)') } },
  { id: 'holderGetsSchedule', label: 'createWatchHolder( を 2 回呼ぶ', over: { extra: 'const again = createWatchHolder({ create: createWorkDirWatcher, onEvent: schedule });' } },
  { id: 'scheduleDebounces', label: 'schedule が setTimeout を使わない', over: { schedule: swap(PIECES.schedule, 'timer = setTimeout(() => {', 'timer = later(() => {') } },
  { id: 'scheduleDebounces', label: 'schedule が DEBOUNCE_MS でなく 0 でまとめる', over: { schedule: swap(PIECES.schedule, '}, DEBOUNCE_MS);', '}, 0);') } },
  { id: 'noDirectEvents', label: 'いまの work_dir の見張りにも .onDidCreate( を直に結ぶ', over: { extra: 'watcher.onDidCreate(schedule);' } },
  { id: 'noDirectEvents', label: 'いまの work_dir の見張りにも .onDidChange( を直に結ぶ', over: { extra: 'watcher.onDidChange(schedule);' } },
  { id: 'noDirectEvents', label: 'いまの work_dir の見張りにも .onDidDelete( を直に結ぶ', over: { extra: 'watcher.onDidDelete(schedule);' } },
  { id: 'noDirectEvents', label: '別の worktree の見張りが .onDidDelete( を結ばない', over: { watchRemote: dropLine(REMOTE, '  remoteWatcher.onDidDelete(schedule);') } },
  // AC-19
  { id: 'presenceNotPoll', label: 'updatePolling の本体で checkWorkDir( を呼ぶ', over: { updatePolling: addAfter(UP, '  else poller.stop();', '  void checkWorkDir();') } },
  { id: 'presenceNotPoll', label: 'updatePolling の本体で PRESENCE_CHECK_MS を使う', over: { updatePolling: addAfter(UP, '  else poller.stop();', '  void PRESENCE_CHECK_MS;') } },
  { id: 'presenceNotPoll', label: 'shouldPoll( の引数に有無（presence）を渡す', over: { updatePolling: swap(UP, 'hasOtherWorktree: lastList?.hasOtherWorktree === true', 'hasOtherWorktree: presenceKnown') } },
  // AC-20
  { id: 'twoPollers', label: '確かめの createPoller( が無い（1 つしかない）', over: { presencePoller: '' } },
  { id: 'twoPollers', label: '確かめの poller の間隔が POLL_MS', over: { presencePoller: swap(PIECES.presencePoller, 'intervalMs: PRESENCE_CHECK_MS', 'intervalMs: POLL_MS') } },
  { id: 'twoPollers', label: '確かめの poller の run が checkWorkDir() でなく render()', over: { presencePoller: swap(PIECES.presencePoller, 'run: () => checkWorkDir()', 'run: () => render()') } },
  { id: 'twoPollers', label: '確かめの poller の run が別の関数', over: { presencePoller: swap(PIECES.presencePoller, 'run: () => checkWorkDir()', 'run: () => other()') } },
  { id: 'twoPollers', label: 'createPoller( を 3 つ作る', over: { extra: 'const third = createPoller({ intervalMs: 1, run: () => render() });' } },
  // AC-21
  { id: 'startInRetarget', label: 'updatePolling でも presencePoller.start() する（2 か所）', over: { updatePolling: addAfter(UP, '  else poller.stop();', '  presencePoller.start();') }, also: ['presenceNotPoll'] },
  { id: 'startInRetarget', label: 'render でも presencePoller.start() する（2 か所）', over: { render: addAfter(R, '  updatePolling(live);', '  presencePoller.start();') } },
  { id: 'startInRetarget', label: 'presencePoller.start() が retarget の「見る先が無い」枝の中にある', over: { retarget: addAfter(dropLine(RT, '  presencePoller.start();'), '    presencePoller.stop();', '    presencePoller.start();') } },
  { id: 'startInRetarget', label: 'presencePoller.start() を呼ばない', over: { retarget: dropLine(RT, '  presencePoller.start();') }, also: ['retargetOrder'] },
  { id: 'stopInNoTarget', label: 'retarget の target が無い枝で presencePoller.stop() しない', over: { retarget: dropLine(RT, '    presencePoller.stop();') } },
  { id: 'stopInNoTarget', label: 'retarget の target が無い枝で poller.stop() しない', over: { retarget: dropLine(RT, '    poller.stop();') } },
  { id: 'stopInDeactivate', label: 'deactivate で presencePoller.stop() しない', over: { deactivate: dropLine(DEACT, '  presencePoller.stop();') } },
  // AC-22
  { id: 'retargetOrder', label: 'checks.next() が stopWatching() のあと', over: { retarget: swap(RT, lines('  checks.next();', '  stopWatching();'), lines('  stopWatching();', '  checks.next();')) } },
  { id: 'retargetOrder', label: 'checks.next() を呼ばない', over: { retarget: dropLine(RT, '  checks.next();') } },
  { id: 'retargetOrder', label: 'void checkWorkDir() が presencePoller.start() の前', over: { retarget: swap(RT, lines('  presencePoller.start();', '  void checkWorkDir();'), lines('  void checkWorkDir();', '  presencePoller.start();')) } },
  { id: 'firstCheckNow', label: 'void checkWorkDir() を setTimeout に包む', over: { retarget: swap(RT, '  void checkWorkDir();', '  setTimeout(() => void checkWorkDir(), 0);') } },
  { id: 'firstCheckNow', label: 'checkWorkDir( を呼ばない（最初の確かめをその場でしない）', over: { retarget: dropLine(RT, '  void checkWorkDir();') }, also: ['retargetOrder'] },
  { id: 'stopWatchingResets', label: 'stopWatching が workDirChecker.reset() を呼ばない', over: { stopWatching: dropLine(STOP, '  workDirChecker.reset();') } },
  { id: 'stopWatchingResets', label: 'workDirChecker.reset() を stopWatching でなく retarget で呼ぶ', over: { stopWatching: dropLine(STOP, '  workDirChecker.reset();'), retarget: addAfter(RT, '  stopWatching();', '  workDirChecker.reset();') } },
  { id: 'deactivateNextChecks', label: 'deactivate が checks.next() を呼ばない', over: { deactivate: dropLine(DEACT, '  checks.next();') } },
  {
    id: 'deactivateNextChecks',
    label: 'deactivate が panel?.dispose() の前に checks.next() を呼ぶ',
    over: {
      deactivate: lines(
        'export function deactivate(): void {',
        '  poller.stop();',
        '  presencePoller.stop();',
        '  checks.next();',
        '  panel?.dispose();',
        '  panel = undefined;',
        '  stopWatching();',
        '  loads.next();',
        '}',
      ),
    },
  },
  { id: 'disposeNextChecks', label: '購読の dispose を { dispose: () => stopWatching() } に戻す', over: { activate: swap(ACTIVATE, '{ dispose: () => { checks.next(); stopWatching(); } },', '{ dispose: () => stopWatching() },') } },
  { id: 'disposeNextChecks', label: '購読の dispose が checks.next() を stopWatching() のあとに呼ぶ', over: { activate: swap(ACTIVATE, '{ checks.next(); stopWatching(); }', '{ stopWatching(); checks.next(); }') } },
  // AC-09
  { id: 'retargetNoRender', label: 'retarget が void render() で読み直す', over: { retarget: addAfter(RT, '  void checkWorkDir();', '  void render();') } },
  { id: 'retargetNoRender', label: 'retarget が await render() で読み直す（async にした見本）', over: { retarget: swap(swap(RT, 'function retarget(): void {', 'async function retarget(): Promise<void> {'), '  void checkWorkDir();', '  await render();') }, also: ['firstCheckNow', 'retargetOrder'] },
  // AC-23
  { id: 'configRetargets', label: '設定 workDir の変更が retarget() でなく void render() を呼ぶ', over: { activate: swap(ACTIVATE, "event.affectsConfiguration(key))) retarget();", 'event.affectsConfiguration(key))) void render();') } },
  { id: 'configRetargets', label: 'フォルダの変更が retarget() を呼ばない', over: { activate: swap(ACTIVATE, 'onDidChangeWorkspaceFolders(() => retarget())', 'onDidChangeWorkspaceFolders(() => void render())') } },
  { id: 'configRetargets', label: "設定の変更が settingKeys('workDir') を見ない", over: { activate: swap(ACTIVATE, "settingKeys('workDir')", "settingKeys('pipesDir')") } },
  // AC-24
  { id: 'checkArgIsTargetAbs', label: 'check( に target.root を渡す', over: { checkWorkDir: swap(PIECES.checkWorkDir, 'check(t.abs)', 'check(t.root)') } },
  { id: 'checkArgIsTargetAbs', label: 'check( に t.display を渡す', over: { checkWorkDir: swap(PIECES.checkWorkDir, 'check(t.abs)', 'check(t.display)') } },
  { id: 'checkArgIsTargetAbs', label: 'check( を 2 か所で呼ぶ', over: { extra: 'void workDirChecker.check(target.abs);' } },
  { id: 'checkArgIsTargetAbs', label: 'check( を呼ばない', over: { checkWorkDir: swap(PIECES.checkWorkDir, '  await workDirChecker.check(t.abs);', '  await Promise.resolve(t.abs);') } },
  { id: 'noStatInExt', label: 'stat( を直に呼ぶ', over: { extra: 'const info = await stat(dir);' } },
  { id: 'noStatInExt', label: 'isDirectory( を直に呼ぶ', over: { extra: 'const there = await isDirectory(dir);' } },
  { id: 'noStatInExt', label: 'dirPresence( を直に呼ぶ', over: { extra: 'const there = await dirPresence(dir);' } },
  { id: 'workDirSingleSource', label: "checkWorkDir で readSetting('workDir' …) を読み直す（2 か所）", over: { checkWorkDir: addAfter(PIECES.checkWorkDir, '  if (!t) return;', "  const again = readSetting('workDir', 'docs/pipeline');") } },
  { id: 'workDirSingleSource', label: "currentWorkDir が readSetting('workDir' …) を読まない", over: { currentWorkDir: swap(PIECES.currentWorkDir, "readSetting('workDir', DEFAULT_WORK_DIR)", 'DEFAULT_WORK_DIR') } },
  // AC-25
  { id: 'watcherBase', label: '基準を Uri.file(target.root) で作る（dir から作らない）', over: { createWatcher: swap(PIECES.createWatcher, 'vscode.Uri.file(dir)', 'vscode.Uri.file(target!.root)') } },
  { id: 'watcherBase', label: '本体で target を読む（基準は dir のまま）', over: { createWatcher: addAfter(PIECES.createWatcher, '  const workDirUri = vscode.Uri.file(dir);', '  const t = target;') } },
  { id: 'watcherBase', label: 'RelativePattern( の第 1 引数が dir から作った変数でない', over: { createWatcher: swap(PIECES.createWatcher, 'new vscode.RelativePattern(workDirUri, WATCH_GLOB)', 'new vscode.RelativePattern(otherUri, WATCH_GLOB)') } },
  { id: 'watcherBase', label: 'RelativePattern( の第 2 引数が WATCH_GLOB でなく REMOTE_WATCH_GLOB', over: { createWatcher: swap(PIECES.createWatcher, 'workDirUri, WATCH_GLOB', 'workDirUri, REMOTE_WATCH_GLOB') }, also: ['patternsShape'] },
  { id: 'watcherBase', label: 'RelativePattern( の基準を関数呼びにする（Uri.file(dir) を直に入れる）', over: { createWatcher: lines('function createWorkDirWatcher(dir: string): vscode.FileSystemWatcher {', '  return vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(vscode.Uri.file(dir), WATCH_GLOB));', '}') }, also: ['patternsShape'] },
  // AC-30・32
  { id: 'twoWatchers', label: '3 つ目の createFileSystemWatcher( を足す（親の見張り）', over: { extra: 'const parent = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(parentUri, WATCH_GLOB));' }, also: ['patternsShape'] },
  { id: 'twoWatchers', label: '別の worktree の見張りを無くす（1 つに減らす）', over: { watchRemote: swap(REMOTE, '  remoteWatcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(remoteUri, REMOTE_WATCH_GLOB));', '  remoteWatcher = undefined;') }, also: ['patternsShape'] },
  { id: 'patternsShape', label: '別の worktree の見張りが REMOTE_WATCH_GLOB でなく WATCH_GLOB を使う', over: { watchRemote: swap(REMOTE, 'remoteUri, REMOTE_WATCH_GLOB', 'remoteUri, WATCH_GLOB') } },
  { id: 'patternsShape', label: '別の worktree の見張りの基準が関数呼び', over: { watchRemote: swap(REMOTE, 'new vscode.RelativePattern(remoteUri, REMOTE_WATCH_GLOB)', 'new vscode.RelativePattern(vscode.Uri.file(dir), REMOTE_WATCH_GLOB)') } },
  { id: 'remoteGlobValue', label: 'REMOTE_WATCH_GLOB の値を深くした', over: { glob: "const REMOTE_WATCH_GLOB = '{state.json,*.md,logs/*.jsonl,*/state.json}';" } },
  { id: 'remoteGlobValue', label: 'REMOTE_WATCH_GLOB を WATCH_GLOB と同じ値にした', over: { glob: "const REMOTE_WATCH_GLOB = '{state.json,*.md,logs/*.jsonl,*/state.json,*/*.md,*/logs/*.jsonl}';" } },
  { id: 'remoteCalls', label: 'render の watchRemote( の引数が otherDir だけ', over: { render: swap(R, 'watchRemote(panel !== undefined ? otherDir : null)', 'watchRemote(otherDir)') } },
  { id: 'remoteCalls', label: 'render で watchRemote( を 2 回呼ぶ', over: { render: addAfter(R, '  watchRemote(panel !== undefined ? otherDir : null);', '  watchRemote(panel !== undefined ? otherDir : null);') } },
  { id: 'remoteCalls', label: 'showRun で watchRemote( を呼ばない', over: { showRun: dropLine(SHOW, '    watchRemote(current.otherDir);') } },
  { id: 'remoteCalls', label: 'パネルの onDidDispose で watchRemote(null) しない', over: { showRun: dropLine(SHOW, '      watchRemote(null);') } },
  { id: 'remoteCalls', label: 'stopWatching で watchRemote(null) しない', over: { stopWatching: dropLine(STOP, '  watchRemote(null);') } },
  // AC-37
  { id: 'noJudgmentInExt', label: 'decideWatch( を呼ぶ', over: { extra: 'const action = decideWatch(true, result);' } },
  { id: 'noJudgmentInExt', label: 'finishStep( を呼ぶ', over: { extra: 'const step = finishStep({ action, attached, first, followUp });' } },
  { id: 'noJudgmentInExt', label: "'present' の文字で結果を比べる", over: { extra: "if (result === 'present') { void 0; }" } },
  { id: 'noJudgmentInExt', label: '"absent" の文字で結果を比べる', over: { extra: 'if (result === "absent") { void 0; }' } },
  { id: 'noJudgmentInExt', label: "'unknown' の文字で結果を比べる", over: { extra: "if (result === 'unknown') { void 0; }" } },
  { id: 'noJudgmentInExt', label: 'workDirWatch.ts から decideWatch も import する', over: { imports: swap(PIECES.imports, '{ createWatchHolder, createWorkDirChecker }', '{ createWatchHolder, createWorkDirChecker, decideWatch }') } },
  { id: 'noJudgmentInExt', label: 'workDirWatch.ts から createWorkDirChecker を import しない', over: { imports: swap(PIECES.imports, '{ createWatchHolder, createWorkDirChecker }', '{ createWatchHolder }') } },
  { id: 'noJudgmentInExt', label: 'workDirWatch.ts から何も import しない', over: { imports: dropLine(PIECES.imports, "import { createWatchHolder, createWorkDirChecker } from './app/workDirWatch.ts';") } },
  // AC-43
  { id: 'headerComment', label: '冒頭のコメントに「監視は1つ」が残っている', over: { header: lines('// 入口：vscode に触れる唯一のファイル。', '// いまの work_dir の監視は1つ。無いあいだは 0 個、有れば 1 個とも書く。') } },
  { id: 'headerComment', label: '冒頭のコメントに「無いあいだは 0 個」が無い', over: { header: lines('// 入口：vscode に触れる唯一のファイル。', '// いまの work_dir の見張りは、有れば 1 個。') } },
  { id: 'headerComment', label: '冒頭のコメントに「有れば 1 個」が無い', over: { header: lines('// 入口：vscode に触れる唯一のファイル。', '// いまの work_dir の見張りは、無いあいだは 0 個。') } },
  { id: 'headerComment', label: '冒頭のコメントが無い', over: { header: '' } },
  { id: 'headerComment', label: '「無いあいだは 0 個、有れば 1 個」が import より後ろのコメントにしか無い', over: { header: '', extra: HEADER_COMMENT } },
];

for (const { id, label, over, also = [] } of BROKEN) {
  const expected = [id, ...also];
  test(`D0034-AC-${firstAc(id)}: 配線の検査そのもの：${label}見本は、見つける（${expected.join('・')}）${KEEP_NOTE}`, () => {
    assert.deepEqual(sorted(watchWiringProblems(sampleWith(over))), sorted(expected));
  });
}

test(`D0034-AC-20: 配線の検査の表そのもの：ID ごとに、壊した見本が 1 つ以上ある${KEEP_NOTE}`, () => {
  const covered = new Set(BROKEN.map((b) => b.id));
  assert.deepEqual(WATCH_IDS.filter((id) => !covered.has(id)), []);
});

// 関数を消した見本：本体を読む検査はどれも、本体が取れなければ欠けと見る（読めないから通る、にしない）。
const READS_BODY: readonly (readonly [PieceName, readonly WatchWiringId[]])[] = [
  ['stopWatching', ['stopWatchingResets', 'remoteCalls']],
  ['checkWorkDir', ['checkArgIsTargetAbs']],
  ['createWatcher', ['watcherBase']],
  ['schedule', ['scheduleDebounces']],
  ['retarget', ['startInRetarget', 'stopInNoTarget', 'retargetOrder', 'firstCheckNow', 'retargetNoRender']],
  ['deactivate', ['stopInDeactivate', 'deactivateNextChecks']],
  ['currentWorkDir', ['workDirSingleSource']],
  ['updatePolling', ['presenceNotPoll']],
  ['render', ['remoteCalls']],
  ['showRun', ['remoteCalls']],
];

for (const [piece, ids] of READS_BODY) {
  for (const id of ids) {
    test(`D0034-AC-${firstAc(id)}: 配線の検査そのもの：${piece} を消した見本は、その本体を読む検査（${id}）が欠けを見つける${KEEP_NOTE}`, () => {
      const found = watchWiringProblems(sampleWith({ [piece]: '' } as Over));
      assert.ok(found.includes(id), `${id} を見つけない：${found.join('・')}`);
    });
  }
}

/** 違反に見えて、違反でないもの（見つけてはいけない）。extra は見本の最後に足す行 */
const NOT_VIOLATIONS: readonly (readonly [WatchWiringId, string, string])[] = [
  ['noStatInExt', 'probe: dirPresence のように、呼ばずに渡す', 'const parts = { probe: dirPresence };'],
  ['noStatInExt', 'statusItem（stat で始まる別の名前）', 'statusItem?.show();'],
  ['noJudgmentInExt', "コメントに書いた 'present'（行頭の //）", "// 結果が 'present' のとき張るのは部品の仕事"],
  ['noJudgmentInExt', 'present で始まる別の名前（文字列の外）', 'const presentation = 1;'],
  ['workDirSingleSource', 'pipesDir の readSetting( は数えない', "const pipes = readSetting('pipesDir', '');"],
  ['noDirectEvents', 'onDidChangeViewState などの別の onDidChange…( は数えない', 'const s = created.onDidChangeViewState(() => {});'],
  ['startInRetarget', 'コメントに書いた presencePoller.start()（行頭の //）', '// presencePoller.start() はここでは呼ばない'],
];

for (const [id, label, extra] of NOT_VIOLATIONS) {
  test(`D0034-AC-${firstAc(id)}: 配線の検査そのもの：「${label}」は、違反に数えない（${id}）${KEEP_NOTE}`, () => {
    assert.deepEqual(watchWiringProblems(sampleWith({ extra })), []);
  });
}

// コメントに書いただけの配線では通らない（行頭の // とブロックコメント）。
const COMMENTED: readonly (readonly [string, Over, readonly WatchWiringId[]])[] = [
  ['presencePoller.start() を行頭の // に書いただけの', { retarget: swap(RT, '  presencePoller.start();', '  // presencePoller.start();') }, ['startInRetarget', 'retargetOrder']],
  ['checks.next() をブロックコメントに書いただけの deactivate の', { deactivate: swap(DEACT, '  checks.next();', '  /*\n  checks.next();\n  */') }, ['deactivateNextChecks']],
  ['workDirChecker.reset() を // に書いただけの', { stopWatching: swap(STOP, '  workDirChecker.reset();', '  // workDirChecker.reset();') }, ['stopWatchingResets']],
  ['確かめの poller をブロックコメントに書いただけの', { presencePoller: `/*\n${PIECES.presencePoller}\n*/` }, ['twoPollers']],
  // 見張りを持つ部品を作る行が無ければ、確かめの手順に渡す holder: dirWatch も指す先が無い（checkerCollaborators）
  ['createWatchHolder( の行を // に書いただけの', { holder: swap(PIECES.holder, 'const dirWatch = createWatchHolder({ create: createWorkDirWatcher, onEvent: schedule });', '// const dirWatch = createWatchHolder({ create: createWorkDirWatcher, onEvent: schedule });') }, ['holderGetsSchedule', 'checkerCollaborators']],
];

for (const [label, over, expected] of COMMENTED) {
  test(`D0034-AC-${firstAc(expected[0] as WatchWiringId)}: 配線の検査そのもの：コメントに書いただけの配線では通らない：${label}見本は、見つける（${expected.join('・')}）${KEEP_NOTE}`, () => {
    assert.deepEqual(sorted(watchWiringProblems(sampleWith(over))), sorted(expected));
  });
}

/** コメントに書いた違反は、違反に数えない（見つけてはいけない）。extra は見本の最後に足す行 */
const COMMENTED_VIOLATIONS: readonly (readonly [WatchWiringId, string, string])[] = [
  ['noStatInExt', '行頭の // に書いた stat( の呼び出し', '// const info = await stat(dir);'],
  ['noJudgmentInExt', '行頭の // に書いた decideWatch( の呼び出し', '// const action = decideWatch(true, result);'],
  ['noDirectEvents', 'ブロックコメントに書いた .onDidCreate( の呼び出し', lines('/*', ' * watcher.onDidCreate(schedule);', ' */')],
];

for (const [id, label, extra] of COMMENTED_VIOLATIONS) {
  test(`D0034-AC-${firstAc(id)}: 配線の検査そのもの：「${label}」は、見つけない（${id}）${KEEP_NOTE}`, () => {
    assert.deepEqual(watchWiringProblems(sampleWith({ extra })), []);
  });
}

test(`D0034-AC-09: 配線の検査そのもの：retarget の中のコメントに書いた render( は違反に数えない（行頭の //）${KEEP_NOTE}`, () => {
  assert.deepEqual(watchWiringProblems(sampleWith({ retarget: addAfter(RT, '  void checkWorkDir();', '  // 読み直しは部品がする。ここで render() は呼ばない') })), []);
});

test(`D0034-AC-43: 配線の検査そのもの：冒頭のコメントは最初の import より前の行頭の // だけを読む。CRLF の改行でも同じ${KEEP_NOTE}`, () => {
  const crlf = sampleWith().split('\n').join('\r\n');
  assert.equal(headerComment(crlf).includes('無いあいだは 0 個'), true);
  assert.deepEqual(watchWiringProblems(sampleWith({ header: PIECES.header.split('\n').join('\r\n') })), []);
});

test(`D0034-AC-37: 配線の検査そのもの：import の探し方は、型だけの import と複数の名前を読む${KEEP_NOTE}`, () => {
  assert.deepEqual(importedFromWatch("import { createWorkDirChecker, createWatchHolder } from './app/workDirWatch.ts';"), ['createWatchHolder', 'createWorkDirChecker']);
  assert.deepEqual(importedFromWatch("import type { Presence, WatchHandle } from './app/workDirWatch.ts';"), ['Presence', 'WatchHandle']);
  assert.deepEqual(importedFromWatch("import { other } from './app/other.ts';"), []);
});
