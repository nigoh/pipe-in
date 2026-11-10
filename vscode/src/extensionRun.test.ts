// 入口 extension.ts の配線の検査（D0078：作業台から流す）。AC-23〜29・33。
// extension.ts は vscode を import するので単体では動かせない。呼び出しの形・順を、ソースを文字で読んで確かめる
// （extensionNotify.test.ts と同じ作り。文字で読む部品は test/sourceText.ts）。
// ここで見るのは配線だけ：何を呼ぶか・どの順に呼ぶか・どこに書くか。判断（流してよいか・コマンドの形・実行ファイルの決め方）は domain/ と app/ のテスト。
// 構成：1) 検査の本体  2) 実物の extension.ts  3) 検査そのもの（守っている見本・壊した見本）。
// 注意：関数の本体は「行頭の function … から、行頭の } まで」で読む（戻り値の型に { } を書いても読める。入口の関数は行頭で閉じる書き方）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { blockAfter, callArgs, inOrder, withoutComments } from './test/sourceText.ts';

// ---- 1) 検査の本体 ----------------------------------------------------------------

/** 行頭の function name(…) から、行頭の } まで（入口の関数は行頭で閉じる）。無ければ null */
function topLevel(code: string, name: string): string | null {
  const head = new RegExp(`\\n(?:export )?(?:async )?function ${name}\\b`).exec(`\n${code}`);
  if (head === null) return null;
  const text = `\n${code}`;
  const end = text.indexOf('\n}', head.index + 1);
  return end === -1 ? null : text.slice(head.index, end + 2);
}

/** runNotifiers を使う関数（「作業台へ runContext を送り直す」口を呼ぶ補助）の名前 */
function broadcasters(code: string): string[] {
  const names: string[] = [];
  for (const m of `\n${code}`.matchAll(/\n(?:export )?(?:async )?function (\w+)/g)) {
    const name = m[1]!;
    if (['openEditor', 'startRun', 'onRunTaskEnded', 'activate'].includes(name)) continue;
    if (/\brunNotifiers\b/.test(topLevel(code, name) ?? '')) names.push(name);
  }
  return names;
}

/** text が runNotifiers を直に使うか、それを使う補助を呼ぶか */
const reaches = (text: string, code: string): boolean => /\brunNotifiers\b/.test(text) || broadcasters(code).some((n) => new RegExp(`\\b${n}\\(`).test(text));

const WRITE_CALLS = /\b(?:writeFile|writeFileSync|appendFile|mkdir|rename|unlink|copyFile|rmSync|rm)\s*\(|\.update\s*\(|\brememberRun\b|\bworkspaceState\b|\bglobalState\b|\bWorkspaceEdit\b|\bapplyEdit\b/;
const CLOCKS = /\bDate\b|Math\.random|\bsetTimeout\b|\bsetInterval\b/;
const flat = (s: string): string => s.replace(/\s+/g, ' ').trim();

type RunWiringId =
  | 'bannedApis'
  | 'oneProcessExecution'
  | 'oneExecuteTask'
  | 'processArgs'
  | 'noEnv'
  | 'envOnlyPath'
  | 'planBeforeProcess'
  | 'refusalShown'
  | 'startOrder'
  | 'noAwaitBetween'
  | 'runIdSeq'
  | 'taskShape'
  | 'presentation'
  | 'executeCatch'
  | 'afterSuccess'
  | 'chooseRunTryCatch'
  | 'showRunOption'
  | 'contextFromHost'
  | 'settingOnlyUser'
  | 'runBranch'
  | 'dirtyTracked'
  | 'notifiersRegistered'
  | 'postRunContextShape'
  | 'readySendsContext'
  | 'sentAtSaved'
  | 'sentAtViewState'
  | 'sentAtExternalReload'
  | 'endTaskHandlers'
  | 'releaseCallers'
  | 'endedShape'
  | 'moduleLevelRuns'
  | 'configRetarget'
  | 'hostOsShape'
  | 'noWrites'
  | 'noClock'
  | 'imports'
  | 'showRunCallers';

function problems(source: string): RunWiringId[] {
  const code = withoutComments(source);
  const startRun = topLevel(code, 'startRun');
  const current = topLevel(code, 'currentRunContext');
  const ended = topLevel(code, 'onRunTaskEnded');
  const userSetting = topLevel(code, 'userCommandSetting');
  const host = topLevel(code, 'hostOs');
  const show = topLevel(code, 'showRun');
  const open = topLevel(code, 'openEditor');
  const activate = topLevel(code, 'activate');
  const count = (text: string | null, re: RegExp): number => (text === null ? 0 : Array.from(text.matchAll(new RegExp(re.source, 'g'))).length);

  const planAt = startRun === null ? -1 : startRun.search(/\bplanRun\(/);
  const startAt = startRun === null ? -1 : startRun.search(/\bactiveRuns\.start\(/);
  let between = startRun !== null && planAt >= 0 && startAt > planAt ? startRun.slice(planAt, startAt) : null;
  const refusal = startRun === null ? null : blockAfter(startRun, /if \(!plan\.ok\) \{/);
  if (between !== null && refusal !== null) between = between.replace(refusal, '');

  const executeCatch = startRun === null ? null : blockAfter(startRun, /\bcatch \(\w+\) \{/);
  const runBlock = open === null ? null : blockAfter(open, /if \(msg\.type === 'run'\) \{/);
  const readyBlock = open === null ? null : blockAfter(open, /if \(msg\.type === 'ready'\) \{/);
  const disposeBlock = open === null ? null : blockAfter(open, /panel\.onDidDispose\(\(\) => \{/);
  const startArgs = runBlock === null ? [] : callArgs(runBlock, 'startRun');
  const fieldsInRun = runBlock === null ? [] : Array.from(new Set(Array.from(runBlock.matchAll(/\bmsg\.(\w+)/g), (m) => m[1]!))).sort();
  const shorthand = (args: string): string[] => args.trim().replace(/^\{|\}$/g, '').split(',').map((s) => s.trim()).filter((s) => /^\w+$/.test(s)).sort();
  const textPart = (args: string): boolean => /(?:^|[,{\s])text\s*:\s*msg\.text\s*(?:[,}]|$)/.test(args);
  const rest = code.replace(startRun ?? '\u0000', '').replace(ended ?? '\u0000', '');
  const settingLeft = code
    .replace(userSetting ?? '\u0000', '')
    .split('\n')
    .filter((line) => /SETTING_COMMAND/.test(line) && !/^\s*import\b/.test(line) && !/affectsConfiguration\(/.test(line));
  // 保存できた知らせ（type: 'saved'）のあと、次の見張り・後始末（onDidChangeViewState・onDidDispose）より前に、runContext を送り直す
  const afterSaved = open === null ? '' : open.slice(Math.max(0, open.search(/type:\s*'saved'/)));
  const savedAt = open === null ? -1 : open.search(/type:\s*'saved'/);
  const savedSend = afterSaved.search(/\bpostRunContext\(\)/);
  const savedBoundary = afterSaved.search(/onDidChangeViewState|onDidDispose/);
  const configSlice = /affectsConfiguration\([^)]*SETTING_COMMAND[^)]*\)\)?([\s\S]{0,200})/.exec(code)?.[1] ?? null;

  const ok: Record<RunWiringId, boolean> = {
    // AC-23：シェル・端末への文字送り・child_process を使わない
    bannedApis: !/\bShellExecution\b|\bsendText\s*\(|\bcreateTerminal\s*\(|child_process/.test(code),
    // AC-23：子プロセスを起こす口は new vscode.ProcessExecution( と vscode.tasks.executeTask( がそれぞれ1か所だけで、startRun の中
    oneProcessExecution: count(code, /new vscode\.ProcessExecution\(/) === 1 && count(startRun, /new vscode\.ProcessExecution\(/) === 1,
    oneExecuteTask: callArgs(code, 'executeTask').length === 1 && startRun !== null && callArgs(startRun, 'executeTask').length === 1,
    // AC-24：ProcessExecution に渡すのは plan.command・plan.args・{ cwd: plan.cwd } だけ（env を渡さない）
    processArgs: startRun !== null && callArgs(startRun, 'vscode.ProcessExecution').length === 1 && flat(callArgs(startRun, 'vscode.ProcessExecution')[0]!) === 'plan.command, plan.args, { cwd: plan.cwd }',
    noEnv: startRun !== null && !/\benv\b/.test(startRun),
    envOnlyPath: !/process\.env\b(?!\.PATH\b)/.test(code),
    // AC-24：planRun が断ったら ProcessExecution に進まない
    planBeforeProcess: startRun !== null && inOrder(startRun, [/\bcurrentRunContext\(/, /\bplanRun\(/, /!plan\.ok/, /ProcessExecution\(/]),
    refusalShown: startRun !== null && /!plan\.ok[\s\S]{0,300}?show(?:Warning|Information|Error)Message\([\s\S]{0,120}?plan\.reason[\s\S]{0,200}?return/.test(startRun),
    // AC-27：currentRunContext → planRun → activeRuns.start → executeTask の順で、planRun と start の間に await が無い
    startOrder: startRun !== null && inOrder(startRun, [/\bcurrentRunContext\(/, /\bplanRun\(/, /\bactiveRuns\.start\(/, /\bexecuteTask\(/]),
    noAwaitBetween: between !== null && !/\bawait\b/.test(between),
    runIdSeq: /\blet runSeq = 0;/.test(code) && startRun !== null && /String\(\+\+runSeq\)/.test(startRun),
    taskShape:
      startRun !== null &&
      callArgs(startRun, 'vscode.Task').length === 1 &&
      /type:\s*RUN_TASK_TYPE/.test(callArgs(startRun, 'vscode.Task')[0]!) &&
      /runId:\s*id\b/.test(callArgs(startRun, 'vscode.Task')[0]!) &&
      /workspaceFolders!\[0\]!/.test(callArgs(startRun, 'vscode.Task')[0]!) &&
      /const RUN_TASK_TYPE = 'pipe-in';/.test(code),
    presentation:
      startRun !== null &&
      /reveal:\s*vscode\.TaskRevealKind\.Always/.test(startRun) &&
      /focus:\s*true/.test(startRun) &&
      /panel:\s*vscode\.TaskPanelKind\.Dedicated/.test(startRun) &&
      /clear:\s*false/.test(startRun) &&
      /close:\s*false/.test(startRun),
    // AC-28：executeTask の失敗は記録を外して理由を見せ、選ばない・開かない。成功のあとに pipeRunKey → chooseRun → showRun({ keepSelection: true })
    executeCatch:
      executeCatch !== null &&
      /\bactiveRuns\.release\(/.test(executeCatch) &&
      /show(?:Error|Warning)Message\(/.test(executeCatch) &&
      !/\bchooseRun\(|\bshowRun\(/.test(executeCatch) &&
      startRun !== null &&
      inOrder(startRun, [/\btry \{/, /\bexecuteTask\(/, /\bcatch \(/]),
    afterSuccess: startRun !== null && inOrder(startRun, [/\bexecuteTask\(/, /\bpipeRunKey\(/, /\bkey !== null/, /\bchooseRun\(/, /\bshowRun\(\s*\{\s*keepSelection:\s*true\s*\}\s*\)/]),
    chooseRunTryCatch: startRun !== null && /try\s*\{\s*await chooseRun\(\w+\);?\s*\}\s*catch\s*\{/.test(startRun),
    showRunOption:
      /function showRun\(\s*options:\s*\{\s*keepSelection\?:\s*boolean\s*\}\s*=\s*\{\}\s*\)/.test(code) && show !== null && /!options\.keepSelection\s*&&\s*\(await selectWaiting\(\)\)/.test(show),
    // AC-27：信頼と実行中は await のあとで読む。project は workspaceFolders[0]。PATH と設定は決まった口から
    contextFromHost:
      current !== null &&
      inOrder(current, [/await resolveExecutable\(/, /vscode\.workspace\.isTrusted/]) &&
      /\brunContextFor\(/.test(current) &&
      /isFile:\s*isRegularFile/.test(current) &&
      /pathEnv:\s*process\.env\.PATH/.test(current) &&
      /workspaceFolders\?\.\[0\]\?\.uri\.fsPath/.test(current) &&
      /\buserCommandSetting\(\)/.test(current) &&
      /\bactiveRuns\.isRunning\(/.test(current) &&
      /\bos:\s*hostOs\(\)/.test(current),
    // AC-26：設定は globalValue・defaultValue だけを取り出す。ワークスペースの値は読まず、ほかの所でもこの設定を読まない
    settingOnlyUser:
      userSetting !== null &&
      /getConfiguration\(SECTION\)\.inspect(?:<[^>()]*>)?\(SETTING_COMMAND\)/.test(userSetting) &&
      /\bglobalValue\b/.test(userSetting) &&
      /\bdefaultValue\b/.test(userSetting) &&
      !/workspace(?:Folder)?Value|languageIds?|\.\.\.\s*\w+|return\s+\w+\s*;/.test(userSetting) &&
      settingLeft.length === 0,
    // AC-25：run の分岐が読む msg のフィールドは text だけ。startRun に渡すパネル由来の値は text だけ（project などは入口が決める）
    runBranch:
      runBlock !== null &&
      JSON.stringify(fieldsInRun) === '["text"]' &&
      startArgs.length === 1 &&
      textPart(startArgs[0]!) &&
      JSON.stringify(shorthand(startArgs[0]!)) === JSON.stringify(['dirty', 'name', 'ref', 'saved']),
    dirtyTracked:
      open !== null &&
      /let dirty = draft !== undefined;/.test(open) &&
      /\bdirty\s*=\s*msg\.dirty\b/.test(open) &&
      /clearUnsaved:\s*\(\)\s*=>\s*\{[^}]*\bdirty\s*=\s*false/.test(open) &&
      count(open, /\bdirty\s*=\s*false\b/) >= 2,
    // AC-29：開いている作業台ごとの口。閉じたら口を外すが、実行中の記録には触れない
    notifiersRegistered: open !== null && /runNotifiers\.set\(name,\s*postRunContext\)/.test(open) && disposeBlock !== null && /runNotifiers\.delete\(name\)/.test(disposeBlock) && !/\bactiveRuns\b/.test(disposeBlock),
    postRunContextShape: open !== null && /const postRunContext\s*=\s*async\s*\(\)[^=]*=>\s*\{[\s\S]*?post\(\{\s*type:\s*'runContext',\s*\.\.\.\(await currentRunContext\(ref,\s*saved\)\)\s*\}\)/.test(open),
    readySendsContext: readyBlock !== null && inOrder(readyBlock, [/estimateContext/, /\bpostRunContext\(\)/]),
    sentAtSaved: savedAt >= 0 && savedSend >= 0 && (savedBoundary < 0 || savedSend < savedBoundary),
    sentAtViewState: open !== null && /onDidChangeViewState\([\s\S]{0,300}?\bpostRunContext\(\)/.test(open),
    sentAtExternalReload: open !== null && /externalReloaded[\s\S]{0,300}?\bpostRunContext\(\)/.test(open),
    endTaskHandlers:
      activate !== null &&
      callArgs(activate, 'onDidEndTask').length === 1 &&
      /\bonRunTaskEnded\(/.test(callArgs(activate, 'onDidEndTask')[0]!) &&
      callArgs(activate, 'onDidEndTaskProcess').length === 1 &&
      /\bonRunTaskEnded\(/.test(callArgs(activate, 'onDidEndTaskProcess')[0]!),
    releaseCallers: ended !== null && /\bactiveRuns\.release\(/.test(ended) && startRun !== null && /\bactiveRuns\.release\(/.test(startRun) && !/\bactiveRuns\.release\(/.test(rest),
    endedShape:
      ended !== null &&
      /\bRUN_TASK_TYPE\b/.test(ended) &&
      /\.definition\b/.test(ended) &&
      /typeof\s+[\w.]+\s*(?:!==|===)\s*'string'/.test(ended) &&
      /!==\s*null/.test(ended) &&
      reaches(ended, code) &&
      startRun !== null &&
      reaches(startRun, code),
    moduleLevelRuns: /^const activeRuns = createActiveRuns\(\);/m.test(code) && !/createActiveRuns\(/.test(open ?? '') && !/createActiveRuns\(/.test(startRun ?? ''),
    configRetarget: configSlice !== null && reaches(configSlice, code),
    hostOsShape: host !== null && /process\.platform\s*===\s*'win32'\s*\?\s*'windows'\s*:\s*'posix'/.test(host),
    // AC-33：流す処理は書く呼び出しを持たず、時計も乱数も使わない（書くのは chooseRun の既存の道だけ）
    noWrites: [startRun, current, ended].every((b) => b !== null && !WRITE_CALLS.test(b)),
    noClock: [startRun, current, ended].every((b) => b !== null && !CLOCKS.test(b)),
    imports:
      /import \{[^}]*\bcreateActiveRuns\b[^}]*\} from '\.\/app\/runActive\.ts'/.test(code) &&
      /import \{[^}]*\bplanRun\b[^}]*\} from '\.\/app\/runFlow\.ts'/.test(code) &&
      /import \{[^}]*\brunContextFor\b[^}]*\} from '\.\/app\/runFlow\.ts'/.test(code) &&
      /import \{[^}]*\bresolveExecutable\b[^}]*\} from '\.\/app\/runExecutable\.ts'/.test(code) &&
      /import \{[^}]*\bisRegularFile\b[^}]*\} from '\.\/infra\/fsFileProbe\.ts'/.test(code) &&
      /import \{[^}]*\bpipeRunKey\b[^}]*\} from '\.\/domain\/runs\.ts'/.test(code),
    showRunCallers: callArgs(code, 'showRun').filter((a) => /keepSelection/.test(a)).length === 1 && startRun !== null && callArgs(startRun, 'showRun').filter((a) => /keepSelection/.test(a)).length === 1,
  };
  return (Object.keys(ok) as RunWiringId[]).filter((id) => !ok[id]);
}

// ---- 2) 実物の extension.ts ----------------------------------------------------------

const EXTENSION = readFileSync(new URL('./extension.ts', import.meta.url), 'utf8');

const WIRING: readonly { id: RunWiringId; ac: string; what: string }[] = [
  { id: 'bannedApis', ac: '23', what: 'ShellExecution・sendText(・createTerminal(・child_process が現れない（シェルを通さない）' },
  { id: 'oneProcessExecution', ac: '23', what: 'new vscode.ProcessExecution( は startRun の中に1か所だけ' },
  { id: 'oneExecuteTask', ac: '23', what: 'vscode.tasks.executeTask( は startRun の中に1か所だけ' },
  { id: 'processArgs', ac: '24', what: 'ProcessExecution( の引数は plan.command, plan.args, { cwd: plan.cwd } だけ' },
  { id: 'noEnv', ac: '24', what: 'startRun に env を渡さない' },
  { id: 'envOnlyPath', ac: '24', what: 'process.env を読むのは process.env.PATH だけ（実行ファイルを探すため）' },
  { id: 'planBeforeProcess', ac: '24', what: 'planRun が断ったら（!plan.ok）ProcessExecution に進まない' },
  { id: 'refusalShown', ac: '24', what: '断られた理由を見せて終わる（showWarningMessage に plan.reason）' },
  { id: 'startOrder', ac: '27', what: 'startRun の順は currentRunContext → planRun → activeRuns.start → executeTask' },
  { id: 'noAwaitBetween', ac: '27', what: 'planRun と activeRuns.start の間に await が無い（判断と記録の追加の間に別の run が割り込めない）' },
  { id: 'runIdSeq', ac: '29', what: 'タスクの印は連番（++runSeq）。時計も乱数も使わない' },
  { id: 'taskShape', ac: '24', what: 'new vscode.Task の定義は { type: RUN_TASK_TYPE, runId: id }、場所は workspaceFolders[0]、型は pipe-in' },
  { id: 'presentation', ac: '24', what: 'タスクの表示は端末を前に出し（reveal Always・focus・Dedicated）、終わっても残す（clear・close を false）' },
  { id: 'executeCatch', ac: '28', what: 'executeTask の失敗（catch）は記録を外して理由を見せ、選ばない・開かない' },
  { id: 'afterSuccess', ac: '28', what: '成功のあとに pipeRunKey → key !== null → chooseRun → showRun({ keepSelection: true }) の順' },
  { id: 'chooseRunTryCatch', ac: '28', what: '覚える書き込み（chooseRun）に失敗しても続ける（try/catch）' },
  { id: 'showRunOption', ac: '28', what: 'showRun は options: { keepSelection?: boolean } = {} を受け、keepSelection のときは selectWaiting で選びを上書きしない' },
  { id: 'contextFromHost', ac: '27', what: 'currentRunContext は await resolveExecutable のあとで isTrusted を読み、project は workspaceFolders[0]、PATH・設定・実行中は決まった口から' },
  { id: 'settingOnlyUser', ac: '26', what: 'userCommandSetting は inspect の globalValue・defaultValue だけを取り出し（workspaceValue などを書かない）、ほかの所でこの設定を読まない' },
  { id: 'runBranch', ac: '25', what: 'run の分岐が読む msg のフィールドは text だけで、startRun に渡すパネル由来の値は text だけ' },
  { id: 'dirtyTracked', ac: '25', what: '作業台の dirty は入口が持つ（開いたとき draft の有無・state の知らせ・保存・外の取り込みで更新）' },
  { id: 'notifiersRegistered', ac: '29', what: '作業台ごとに runNotifiers.set(name, postRunContext) し、閉じたら delete。閉じても activeRuns には触れない' },
  { id: 'postRunContextShape', ac: '29', what: 'postRunContext は currentRunContext(ref, saved) の結果を runContext として post する' },
  { id: 'readySendsContext', ac: '29', what: 'ready のとき estimateContext の次に runContext を送る（開き直しても running が入る）' },
  { id: 'sentAtSaved', ac: '29', what: '保存できたあとに runContext を送り直す' },
  { id: 'sentAtViewState', ac: '29', what: 'パネルが見えるようになったとき runContext を送り直す' },
  { id: 'sentAtExternalReload', ac: '29', what: '外で書き換わった取り込み（externalReloaded）のあとに runContext を送り直す' },
  { id: 'endTaskHandlers', ac: '29', what: 'onDidEndTask と onDidEndTaskProcess が同じ onRunTaskEnded を呼ぶ' },
  { id: 'releaseCallers', ac: '29', what: 'activeRuns.release( の呼び出し元は onRunTaskEnded と startRun の失敗の catch だけ' },
  { id: 'endedShape', ac: '29', what: 'onRunTaskEnded は定義の型が RUN_TASK_TYPE で runId が文字のときだけ release し、外れたら全部の作業台へ送り直す' },
  { id: 'moduleLevelRuns', ac: '29', what: 'activeRuns はモジュールの変数（行頭の const）で、openEditor・startRun の中で作らない' },
  { id: 'configRetarget', ac: '29', what: '設定 pipe-in.command が変わったら（affectsConfiguration）runContext を送り直す' },
  { id: 'hostOsShape', ac: '27', what: 'hostOs は process.platform === \'win32\' ? \'windows\' : \'posix\'' },
  { id: 'noWrites', ac: '33', what: 'startRun・currentRunContext・onRunTaskEnded に書く呼び出し（writeFile・mkdir・.update( など）が無い' },
  { id: 'noClock', ac: '33', what: 'startRun・currentRunContext・onRunTaskEnded が Date・乱数・タイマーを使わない' },
  { id: 'imports', ac: '27', what: 'extension.ts が app/runActive.ts・app/runFlow.ts・app/runExecutable.ts・infra/fsFileProbe.ts・domain/runs.ts から読む' },
  { id: 'showRunCallers', ac: '28', what: 'showRun({ keepSelection: true }) を呼ぶのは startRun だけ' },
];

// AC-23〜29・33 の検査。実装の前から満たしていたもの（禁止の API が無い・環境変数は PATH だけ）は「守る」と書き、ほかは実装で満たした。
const KEEP = new Set<RunWiringId>(['bannedApis', 'envOnlyPath']);

for (const w of WIRING) {
  test(`D0078-AC-${w.ac}: ${w.what}${KEEP.has(w.id) ? '（今のまま通る。守る）' : ''}`, () => {
    assert.ok(!problems(EXTENSION).includes(w.id), `extension.ts で守られていない：${w.id}`);
  });
}

// ---- AC-23：src/ 全体で、起こす口は extension.ts だけ ----

const SRC = path.dirname(fileURLToPath(import.meta.url));

function listTsFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listTsFiles(full));
    else if (entry.isFile() && entry.name.endsWith('.ts')) out.push(full);
  }
  return out;
}

const PRODUCTION = listTsFiles(SRC)
  .map((file) => ({ rel: path.relative(SRC, file).split(path.sep).join('/'), source: readFileSync(file, 'utf8') }))
  .filter((f) => !f.rel.endsWith('.test.ts') && !f.rel.startsWith('test/'));

test('D0078-AC-23: src/ の製品のコードのどこにも ShellExecution・sendText(・createTerminal(・child_process が現れない（今のまま通る。守る）', () => {
  assert.ok(PRODUCTION.some((f) => f.rel === 'extension.ts') && PRODUCTION.length > 20, '検査の対象が読めている');
  const hits = PRODUCTION.filter((f) => /\bShellExecution\b|\bsendText\s*\(|\bcreateTerminal\s*\(|child_process/.test(withoutComments(f.source))).map((f) => f.rel);
  assert.deepEqual(hits, []);
});

test('D0078-AC-23: ProcessExecution と tasks.executeTask を使うのは extension.ts だけ', () => {
  const users = PRODUCTION.filter((f) => /\bProcessExecution\b|\btasks\.executeTask\b/.test(withoutComments(f.source))).map((f) => f.rel);
  assert.deepEqual(users, ['extension.ts']);
});

test('D0078-AC-26: app/names.ts に設定の名前 SETTING_COMMAND = \'command\' がある（新しい節 pipe-in だけ。前の版の節 devpipe には command が無いので読み替えない）', () => {
  const names = withoutComments(PRODUCTION.find((f) => f.rel === 'app/names.ts')?.source ?? '');
  assert.match(names, /export const SETTING_COMMAND = 'command';/);
});

test('D0078-AC-26: extension.ts は前の版の節（LEGACY_SECTION）から command を読まない', () => {
  const code = withoutComments(EXTENSION);
  assert.doesNotMatch(code, /LEGACY_SECTION[^;\n]*SETTING_COMMAND|SETTING_COMMAND[^;\n]*LEGACY_SECTION/);
  assert.doesNotMatch(code, /devpipe\.command/);
});

// ---- 3) 検査そのもの：守っている見本は問題なし。壊した見本を見つける ----------------------

const GOOD = `
import { createActiveRuns } from './app/runActive.ts';
import { planRun, runContextFor } from './app/runFlow.ts';
import { resolveExecutable } from './app/runExecutable.ts';
import { isRegularFile } from './infra/fsFileProbe.ts';
import { pipeRunKey } from './domain/runs.ts';
const activeRuns = createActiveRuns();
let runSeq = 0;
const RUN_TASK_TYPE = 'pipe-in';
const runNotifiers = new Map<string, () => Promise<void>>();

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (settingKeys('workDir').some((key) => event.affectsConfiguration(key))) retarget();
      else if (event.affectsConfiguration(\`\${SECTION}.\${SETTING_COMMAND}\`)) notifyRunPanels();
    }),
    vscode.tasks.onDidEndTask((e) => onRunTaskEnded(e.execution)),
    vscode.tasks.onDidEndTaskProcess((e) => onRunTaskEnded(e.execution)),
  );
}

function hostOs(): OsKind {
  return process.platform === 'win32' ? 'windows' : 'posix';
}

function userCommandSetting(): { globalValue: unknown; defaultValue: unknown } {
  const i = vscode.workspace.getConfiguration(SECTION).inspect<unknown>(SETTING_COMMAND);
  return { globalValue: i?.globalValue, defaultValue: i?.defaultValue };
}

async function currentRunContext(ref: PipeRef | null, saved: PipeModel): Promise<RunContext> {
  const executable = await resolveExecutable({ setting: userCommandSetting(), pathEnv: process.env.PATH, os: hostOs(), isFile: isRegularFile });
  return runContextFor({ ref, saved, project: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? null, trusted: vscode.workspace.isTrusted, executable, isRunning: (d) => activeRuns.isRunning(d) });
}

function notifyRunPanels(): void {
  for (const post of runNotifiers.values()) void post();
}

async function startRun(i: { name: string; ref: PipeRef | null; saved: PipeModel; dirty: boolean; text: string }): Promise<void> {
  const ctx = await currentRunContext(i.ref, i.saved);
  const plan = planRun(ctx, i.dirty, i.text, hostOs());
  if (!plan.ok) {
    void vscode.window.showWarningMessage(NAME + ': ' + plan.reason);
    notifyRunPanels();
    return;
  }
  const id = String(++runSeq);
  if (!activeRuns.start(plan.pipeDir, id)) return;
  const task = new vscode.Task({ type: RUN_TASK_TYPE, runId: id }, vscode.workspace.workspaceFolders![0]!, NAME + ' ' + i.name, NAME, new vscode.ProcessExecution(plan.command, plan.args, { cwd: plan.cwd }), []);
  task.presentationOptions = { reveal: vscode.TaskRevealKind.Always, focus: true, panel: vscode.TaskPanelKind.Dedicated, clear: false, echo: true, showReuseMessage: false, close: false };
  try {
    await vscode.tasks.executeTask(task);
  } catch (e) {
    activeRuns.release(id);
    void vscode.window.showErrorMessage(NAME + ': ' + String(e));
    notifyRunPanels();
    return;
  }
  notifyRunPanels();
  const key = pipeRunKey(i.saved.name);
  if (key !== null) {
    try { await chooseRun(key); } catch { /* 覚える書き込みに失敗しても続ける */ }
  }
  await showRun({ keepSelection: true });
}

function onRunTaskEnded(execution: vscode.TaskExecution): void {
  const def = execution.task.definition;
  if (def.type !== RUN_TASK_TYPE || typeof def.runId !== 'string') return;
  if (activeRuns.release(def.runId) !== null) notifyRunPanels();
}

async function showRun(options: { keepSelection?: boolean } = {}): Promise<void> {
  if (!options.keepSelection && (await selectWaiting())) await render();
}

function openEditor(dirs: string[], opened: PipeRef | null, saved: PipeModel, savedNames: string[], draft?: PipeModel): void {
  const name = saved.name;
  let ref: PipeRef | null = opened;
  let dirty = draft !== undefined;
  const post = (message: ToEditorMessage): void => {
    void panel.webview.postMessage(message);
    if (message.type === 'externalReloaded') void postRunContext();
  };
  const reload = createExternalReload({
    clearUnsaved: () => { unsaved = null; dirty = false; },
  });
  const postRunContext = async (): Promise<void> => {
    post({ type: 'runContext', ...(await currentRunContext(ref, saved)) });
  };
  runNotifiers.set(name, postRunContext);
  const onMessage = panel.webview.onDidReceiveMessage(async (value: unknown) => {
    const msg = parseEditorMessage(value);
    if (!msg) return;
    if (msg.type === 'ready') {
      post({ type: 'load', model: saved });
      post({ type: 'estimateContext', ...estimateContext(lastList, name, Date.now()) });
      await postRunContext();
      return;
    }
    if (msg.type === 'state') {
      dirty = msg.dirty;
      return;
    }
    if (msg.type === 'run') {
      await startRun({ name, ref, saved, dirty, text: msg.text });
      return;
    }
    dirty = false;
    post({ type: 'saved', written });
    await postRunContext();
  });
  panel.onDidChangeViewState(() => {
    if (panel.visible) void postRunContext();
  });
  panel.onDidDispose(() => {
    onMessage.dispose();
    runNotifiers.delete(name);
  });
}
`;

test('D0078-AC-23: 検査の見本：守っている見本は問題なし', () => {
  assert.deepEqual(problems(GOOD), []);
});

const rep = (from: string, to: string): string => {
  assert.ok(GOOD.includes(from), `見本に無い文字：${from}`);
  return GOOD.replace(from, to);
};

const BROKEN: readonly [string, string, RunWiringId][] = [
  ['端末に文字を送る', rep("    notifyRunPanels();\n    return;\n  }\n  const id", "    notifyRunPanels();\n    vscode.window.createTerminal('x').sendText('pipe-in ' + i.text);\n    return;\n  }\n  const id"), 'bannedApis'],
  ['ShellExecution を使う', rep('new vscode.ProcessExecution(plan.command, plan.args, { cwd: plan.cwd })', 'new vscode.ShellExecution(plan.command + " " + plan.args.join(" "))'), 'bannedApis'],
  ['ProcessExecution を2か所で作る', rep('    await vscode.tasks.executeTask(task);', "    await vscode.tasks.executeTask(task);\n    new vscode.ProcessExecution('x', []);"), 'oneProcessExecution'],
  ['executeTask を2回呼ぶ', rep('  notifyRunPanels();\n  const key', '  await vscode.tasks.executeTask(task);\n  notifyRunPanels();\n  const key'), 'oneExecuteTask'],
  ['ProcessExecution に env を渡す', rep('{ cwd: plan.cwd }', "{ cwd: plan.cwd, env: { PATH: '/evil' } }"), 'processArgs'],
  ['ProcessExecution に env を渡す（noEnv）', rep('{ cwd: plan.cwd }', "{ cwd: plan.cwd, env: { PATH: '/evil' } }"), 'noEnv'],
  ['コマンドを plan でなく変数から渡す', rep('new vscode.ProcessExecution(plan.command,', 'new vscode.ProcessExecution(i.name,'), 'processArgs'],
  ['PATH 以外の環境変数を読む', rep('pathEnv: process.env.PATH', 'pathEnv: process.env.PATH, extra: process.env.HOME'), 'envOnlyPath'],
  ['断られても進む', rep('if (!plan.ok) {', 'if (false) {'), 'planBeforeProcess'],
  ['断った理由を見せない', rep("    void vscode.window.showWarningMessage(NAME + ': ' + plan.reason);\n", ''), 'refusalShown'],
  ['記録を付けずに起こす', rep('  if (!activeRuns.start(plan.pipeDir, id)) return;\n', ''), 'startOrder'],
  ['判断と記録の追加の間に await を挟む', rep('  const id = String(++runSeq);', '  await Promise.resolve();\n  const id = String(++runSeq);'), 'noAwaitBetween'],
  ['タスクの印を時計で作る', rep('String(++runSeq)', 'String(Date.now())'), 'runIdSeq'],
  ['タスクの定義に runId が無い', rep('{ type: RUN_TASK_TYPE, runId: id }', '{ type: RUN_TASK_TYPE }'), 'taskShape'],
  ['端末に焦点を渡さない', rep('focus: true', 'focus: false'), 'presentation'],
  ['失敗しても記録を外さない', rep('    activeRuns.release(id);\n    void vscode.window.showErrorMessage', '    void vscode.window.showErrorMessage'), 'executeCatch'],
  ['失敗の catch で実行パネルを開く', rep('    activeRuns.release(id);', '    activeRuns.release(id);\n    await showRun({ keepSelection: true });'), 'executeCatch'],
  ['選びを上書きされる呼び方をする', rep('await showRun({ keepSelection: true });', 'await showRun();'), 'afterSuccess'],
  ['pipeRunKey を使わない', rep('  const key = pipeRunKey(i.saved.name);', "  const key = 'here|' + i.saved.name;"), 'afterSuccess'],
  ['覚える書き込みの失敗で止まる', rep('try { await chooseRun(key); } catch { /* 覚える書き込みに失敗しても続ける */ }', 'await chooseRun(key);'), 'chooseRunTryCatch'],
  ['keepSelection を見ない', rep('!options.keepSelection && (await selectWaiting())', '(await selectWaiting())'), 'showRunOption'],
  ['信頼を決め打ちにする', rep('trusted: vscode.workspace.isTrusted', 'trusted: true'), 'contextFromHost'],
  ['実行ファイルを await せずに文脈を作る', rep('const executable = await resolveExecutable(', 'const executable = resolveExecutable('), 'contextFromHost'],
  ['project をパネルの値にする', rep('project: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? null', 'project: i.project'), 'contextFromHost'],
  ['ワークスペースの設定の値も取り出す', rep('return { globalValue: i?.globalValue, defaultValue: i?.defaultValue };', 'return { globalValue: i?.globalValue, defaultValue: i?.defaultValue, workspaceValue: i?.workspaceValue };'), 'settingOnlyUser'],
  ['inspect の結果を丸ごと返す', rep('return { globalValue: i?.globalValue, defaultValue: i?.defaultValue };', 'return i;'), 'settingOnlyUser'],
  ['ほかの所でこの設定を get で読む', rep('  const executable = await', '  const cmd = vscode.workspace.getConfiguration(SECTION).get(SETTING_COMMAND);\n  const executable = await'), 'settingOnlyUser'],
  ['run の分岐が cwd を読む', rep('text: msg.text }', 'text: msg.text, cwd: msg.cwd }'), 'runBranch'],
  ['run の分岐が dirty をパネルから読む', rep('dirty, text: msg.text', 'dirty: msg.dirty, text: msg.text'), 'runBranch'],
  ['run の分岐が name をパネルから読む', rep('startRun({ name, ref,', 'startRun({ name: msg.name, ref,'), 'runBranch'],
  ['state の知らせで dirty を更新しない', rep('      dirty = msg.dirty;\n', ''), 'dirtyTracked'],
  ['作業台の口を登録しない', rep('  runNotifiers.set(name, postRunContext);\n', ''), 'notifiersRegistered'],
  ['閉じたときに実行中の記録を外す', rep('    runNotifiers.delete(name);', '    runNotifiers.delete(name);\n    activeRuns.release(name);'), 'notifiersRegistered'],
  ['runContext の送り方が違う', rep("post({ type: 'runContext', ...(await currentRunContext(ref, saved)) });", "post({ type: 'runContext', ...(await currentRunContext(null, saved)) });"), 'postRunContextShape'],
  ['ready で runContext を送らない', rep('      await postRunContext();\n      return;\n    }\n    if (msg.type === \'state\') {', "      return;\n    }\n    if (msg.type === 'state') {"), 'readySendsContext'],
  ['保存のあとに送り直さない', rep("    post({ type: 'saved', written });\n    await postRunContext();", "    post({ type: 'saved', written });"), 'sentAtSaved'],
  ['見えるようになったとき送り直さない', rep('    if (panel.visible) void postRunContext();\n', ''), 'sentAtViewState'],
  ['外の取り込みのあとに送り直さない', rep("    if (message.type === 'externalReloaded') void postRunContext();\n", ''), 'sentAtExternalReload'],
  ['onDidEndTaskProcess を聞かない', rep('    vscode.tasks.onDidEndTaskProcess((e) => onRunTaskEnded(e.execution)),\n', ''), 'endTaskHandlers'],
  ['onDidEndTask が別の関数を呼ぶ', rep('vscode.tasks.onDidEndTask((e) => onRunTaskEnded(e.execution))', 'vscode.tasks.onDidEndTask((e) => activeRuns.release(String(e.execution)))'), 'endTaskHandlers'],
  ['別の関数で release する', rep('  for (const post of runNotifiers.values()) void post();', '  activeRuns.release(\'x\');\n  for (const post of runNotifiers.values()) void post();'), 'releaseCallers'],
  ['runId が文字かを見ない', rep("typeof def.runId !== 'string'", 'false'), 'endedShape'],
  ['外れても送り直さない', rep('if (activeRuns.release(def.runId) !== null) notifyRunPanels();', 'activeRuns.release(def.runId);'), 'endedShape'],
  ['activeRuns を作業台ごとに作る', rep('const activeRuns = createActiveRuns();\nlet runSeq', 'let runSeq').replace('  let dirty = draft !== undefined;', '  const activeRuns = createActiveRuns();\n  let dirty = draft !== undefined;'), 'moduleLevelRuns'],
  ['設定の変更で送り直さない', rep('      else if (event.affectsConfiguration(`${SECTION}.${SETTING_COMMAND}`)) notifyRunPanels();\n', ''), 'configRetarget'],
  ['OS を決め打ちにする', rep("process.platform === 'win32'", 'true'), 'hostOsShape'],
  ['流す処理がファイルに書く', rep('  const key = pipeRunKey(i.saved.name);', "  await writeFile('x', i.text);\n  const key = pipeRunKey(i.saved.name);"), 'noWrites'],
  ['流す処理が設定を書き換える', rep('  const key = pipeRunKey(i.saved.name);', "  await vscode.workspace.getConfiguration(SECTION).update('command', '/x');\n  const key = pipeRunKey(i.saved.name);"), 'noWrites'],
  ['流す処理が時計を読む', rep('  const id = String(++runSeq);', '  const at = Date.now();\n  const id = String(++runSeq);'), 'noClock'],
  ['fsFileProbe を読まない', rep("import { isRegularFile } from './infra/fsFileProbe.ts';\n", ''), 'imports'],
  ['showRun({ keepSelection }) を別の所からも呼ぶ', rep('if (activeRuns.release(def.runId) !== null) notifyRunPanels();', 'if (activeRuns.release(def.runId) !== null) { notifyRunPanels(); void showRun({ keepSelection: true }); }'), 'showRunCallers'],
];

for (const [label, source, id] of BROKEN) {
  test(`D0078-AC-23: 検査の見本：${label}と、${id} が見つける`, () => {
    assert.notEqual(source, GOOD, '見本を壊せていない');
    assert.ok(problems(source).includes(id), `${id} が見つけられない（見つけたもの：${problems(source).join(', ')}）`);
  });
}

test('D0078-AC-23: 検査の見本：行頭のコメントに書いただけの呼び出しは数えない（コメントで通さない）', () => {
  const sneaky = rep('    await vscode.tasks.executeTask(task);', '    // await vscode.tasks.executeTask(task);\n    await Promise.resolve(task);');
  assert.ok(problems(sneaky).includes('oneExecuteTask'));
  const banned = rep('  const id = String(++runSeq);', '  // createTerminal( は使わない\n  const id = String(++runSeq);');
  assert.ok(!problems(banned).includes('bannedApis'), '行頭のコメントの語は見逃す');
});
