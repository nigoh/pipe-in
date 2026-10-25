// 入口 extension.ts の配線の検査（D0046：確認待ちの知らせ）。AC-10・13〜16・18・19。
// extension.ts は vscode を import するので単体では動かせない。呼び出しの形を、ソースを文字で読んで確かめる
// （extensionCounts.test.ts と同じ作り。文字で読む部品は test/sourceText.ts）。
// ここで見るのは配線だけ：何を呼ぶか・どの順に呼ぶか・どこに書くか。判断（新しく確認待ちになったか）は domain/、文は view/、絞り込みは app/ のテスト。
// 構成：1) 検査の本体  2) 実物の extension.ts  3) 検査そのもの（壊した見本）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { callArgs, functionBody, inOrder, withoutComments } from './test/sourceText.ts';

// ---- 1) 検査の本体 ----------------------------------------------------------------

const SHOW_MESSAGE = /\bshow(?:Information|Warning|Error)Message\(/;

type NotifyWiringId =
  | 'notifyFnExists'
  | 'showOnlyInNotifyFn'
  | 'oneButton'
  | 'buttonRunsShowRun'
  | 'rejectionCaught'
  | 'renderCallsNotify'
  | 'notifyAfterLoadLatest'
  | 'retargetDropsBase'
  | 'baseUpdatedEveryTime'
  | 'baseOnlyInNotifyAndRetarget'
  | 'usesPlan'
  | 'usesText'
  | 'readsSettingWithLegacy'
  | 'noPersist'
  | 'noPostNoStatus';

function problems(source: string): NotifyWiringId[] {
  const code = withoutComments(source);
  const render = functionBody(code, 'render');
  const notify = functionBody(code, 'notifyWaiting');
  const retarget = functionBody(code, 'retarget');
  const readSetting = functionBody(code, 'readNotifySetting');
  const withoutBodies = (names: string[]): string => {
    let rest = code;
    for (const n of names) {
      const body = functionBody(code, n);
      if (body !== null) rest = rest.replace(body, '');
    }
    return rest;
  };
  const showArgs = notify === null ? [] : callArgs(notify, 'showInformationMessage');
  const ok: Record<NotifyWiringId, boolean> = {
    notifyFnExists: notify !== null,
    // AC-14：show*Message( は notifyWaiting の本体にだけある（render の本体にも、ほかの所にも新しくは増えない）
    showOnlyInNotifyFn: notify !== null && SHOW_MESSAGE.test(notify) && render !== null && !SHOW_MESSAGE.test(render),
    // AC-10：ボタンは SHOW_RUN_LABEL 1つだけ
    oneButton: showArgs.length === 1 && /^\s*`[^`]*`\s*,\s*SHOW_RUN_LABEL\s*$/.test(showArgs[0]!),
    // AC-13：押されたときだけ、既存のコマンド showRun を実行する
    buttonRunsShowRun:
      notify !== null &&
      callArgs(notify, 'executeCommand').length === 1 &&
      /^\s*COMMANDS\.showRun\s*$/.test(callArgs(notify, 'executeCommand')[0]!) &&
      inOrder(notify, [/===\s*SHOW_RUN_LABEL/, /\bexecuteCommand\(/]),
    rejectionCaught: notify !== null && /\.then\(/.test(notify) && /\(\)\s*=>\s*undefined/.test(notify),
    // AC-14・15：render が 1 回だけ呼び、loadLatest のあと（古い結果で早く return したあと）に呼ぶ
    renderCallsNotify: render !== null && callArgs(render, 'notifyWaiting').length === 1 && callArgs(code, 'notifyWaiting').length === 1,
    notifyAfterLoadLatest: render !== null && inOrder(render, [/\bloadLatest\(/, /if \(!current\) return;/, /\bnotifyWaiting\(/]),
    // AC-15：見る先が変わったら基準を捨てる
    retargetDropsBase: retarget !== null && /\bnoticeBase\s*=\s*null\b/.test(retarget),
    // 設計：基準は毎回更新する（設定が false のあいだも）。比べる前に前の値を取り出してから入れ替える
    baseUpdatedEveryTime: notify !== null && inOrder(notify, [/\bprev\s*=\s*noticeBase\b/, /\bnoticeBase\s*=\s*listView\.rows\b/, /\bplanWaitingNotice\(/]),
    baseOnlyInNotifyAndRetarget: !/(?<!\blet\s+)\bnoticeBase\s*=(?![=>])/.test(withoutBodies(['notifyWaiting', 'retarget'])) && /\blet\s+noticeBase\b/.test(code),
    // 判断・文・設定の読みは、domain/・view/・app/ の部品に任せる
    usesPlan: notify !== null && callArgs(notify, 'planWaitingNotice').length === 1 && /\bnotifyEnabled\(/.test(notify),
    usesText: notify !== null && callArgs(notify, 'waitingNoticeText').length === 1 && /\bif \(text === null\) return;/.test(notify),
    // AC-18：新しい節と前の版の節の両方を inspect で読み、chooseSetting に渡す
    readsSettingWithLegacy:
      readSetting !== null &&
      (readSetting.match(/\.inspect(?:<[^>()]*>)?\(/g) ?? []).length === 2 &&
      /\bSETTING_NOTIFY\b/.test(readSetting) &&
      /\bSECTION\b/.test(readSetting) &&
      /\bLEGACY_SECTION\b/.test(readSetting) &&
      callArgs(readSetting, 'chooseSetting').length === 1,
    // AC-19：基準は拡張のメモリだけ。workspaceState に書かない
    noPersist: notify !== null && !/\b(?:memory|workspaceState|rememberRun|update)\b/.test(notify) && !/\bnoticeBase\b[^;\n]*\brememberRun\b/.test(code),
    // AC-16：知らせの関数は、パネルへ送らず、ステータスバーを触らない
    noPostNoStatus: notify !== null && !/\bpostMessage\(/.test(notify) && !/\bstatusItem\b/.test(notify) && !/\bMarkdownString\b/.test(notify),
  };
  return (Object.keys(ok) as NotifyWiringId[]).filter((id) => !ok[id]);
}

// ---- 2) 実物の extension.ts ----------------------------------------------------------

const EXTENSION = readFileSync(new URL('./extension.ts', import.meta.url), 'utf8');

const WIRING: readonly { id: NotifyWiringId; ac: string; what: string }[] = [
  { id: 'notifyFnExists', ac: '14', what: '知らせを出す関数 notifyWaiting が render() の外にある' },
  { id: 'showOnlyInNotifyFn', ac: '14', what: 'show*Message( は notifyWaiting の本体にあり、render() の本体には無い' },
  { id: 'renderCallsNotify', ac: '14', what: 'render() の本体が notifyWaiting( を 1 回だけ呼ぶ（呼び出しはほかに無い）' },
  { id: 'oneButton', ac: '10', what: 'showInformationMessage( をボタン SHOW_RUN_LABEL 1つだけで呼ぶ' },
  { id: 'buttonRunsShowRun', ac: '13', what: 'ボタンが押された（pick === SHOW_RUN_LABEL）ときだけ executeCommand(COMMANDS.showRun) を呼ぶ' },
  { id: 'rejectionCaught', ac: '13', what: '知らせの拒否を握る（.then の第 2 引数）' },
  { id: 'notifyAfterLoadLatest', ac: '15', what: 'notifyWaiting は loadLatest の後、古い結果の return の後に呼ぶ（古い世代の結果では判断も知らせもしない）' },
  { id: 'retargetDropsBase', ac: '15', what: 'retarget() が noticeBase = null に戻す' },
  { id: 'baseUpdatedEveryTime', ac: '15', what: '基準は前の値を取ってから毎回入れ替え、そのあとで planWaitingNotice( に渡す' },
  { id: 'baseOnlyInNotifyAndRetarget', ac: '15', what: 'noticeBase に代入するのは notifyWaiting と retarget だけ（let の宣言がある）' },
  { id: 'usesPlan', ac: '11', what: '対象の行は planWaitingNotice( で決め、設定は notifyEnabled( を通す' },
  { id: 'usesText', ac: '08', what: '文は waitingNoticeText( で作り、null なら出さない' },
  { id: 'readsSettingWithLegacy', ac: '18', what: 'readNotifySetting が新しい節と前の版の節を inspect で読み、chooseSetting に渡す' },
  { id: 'noPersist', ac: '19', what: 'notifyWaiting が memory・workspaceState・rememberRun を使わない（基準は拡張のメモリだけ）' },
  { id: 'noPostNoStatus', ac: '16', what: 'notifyWaiting がパネルへ送らず、ステータスバー・Markdown を触らない' },
];

for (const w of WIRING) {
  test(`D0046-AC-${w.ac}: ${w.what}`, () => {
    assert.ok(!problems(EXTENSION).includes(w.id), `extension.ts で守られていない：${w.id}`);
  });
}

test('D0046-AC-16: render() の本体の postMessage( は 1 回のまま（知らせはパネルのメッセージの種類を増やさない）', () => {
  const render = functionBody(withoutComments(EXTENSION), 'render');
  assert.notEqual(render, null);
  assert.equal(callArgs(render!, 'postMessage').length, 1);
});

test('D0046-AC-16: 知らせのために ステータスバーの色（backgroundColor・color）への代入が増えない', () => {
  const code = withoutComments(EXTENSION);
  assert.ok(!/\.(?:backgroundColor|color)\s*=(?![=>])/.test(code));
  assert.ok(!/\bMarkdownString\b/.test(code));
});

test('D0046-AC-14: extension.ts が app/notifyWaiting.ts・view/waitNotice.ts から読んでいる', () => {
  assert.match(EXTENSION, /from '\.\/app\/notifyWaiting\.ts'/);
  assert.match(EXTENSION, /from '\.\/view\/waitNotice\.ts'/);
});

test('D0046-AC-14: extension.ts に確認待ちの文字（\'waiting\'）や .state の比べを新しく書かない', () => {
  const code = withoutComments(EXTENSION);
  assert.ok(!/(['"])waiting\1/.test(code));
  assert.ok(!/\.state\s*[!=]==?/.test(code));
});

// ---- 3) 検査そのもの：壊した見本を見つけ、守っている見本を見逃さない ----------------------

const GOOD = `
let noticeBase: RunRow[] | null = null;
function retarget(): void {
  lastLive = false;
  noticeBase = null;
}
async function render(): Promise<void> {
  const current = await loadLatest();
  if (!current) return;
  void panel.webview.postMessage(message);
  notifyWaiting(listView);
}
function notifyWaiting(listView: RunListView): void {
  const prev = noticeBase;
  noticeBase = listView.rows;
  const rows = planWaitingNotice({ prev, rows: listView.rows, enabled: notifyEnabled(readNotifySetting()) });
  const text = waitingNoticeText(rows);
  if (text === null) return;
  void vscode.window.showInformationMessage(\`\${NAME}: \${text}\`, SHOW_RUN_LABEL).then(
    (pick) => { if (pick === SHOW_RUN_LABEL) void vscode.commands.executeCommand(COMMANDS.showRun); },
    () => undefined,
  );
}
function readNotifySetting(): unknown {
  const current = vscode.workspace.getConfiguration(SECTION).inspect<unknown>(SETTING_NOTIFY);
  const legacy = vscode.workspace.getConfiguration(LEGACY_SECTION).inspect<unknown>(SETTING_NOTIFY);
  return chooseSetting(current, legacy, true);
}
`;

test('D0046-AC-14: 検査の見本：守っている見本は問題なし', () => {
  assert.deepEqual(problems(GOOD), []);
});

const BROKEN: readonly [string, string, NotifyWiringId][] = [
  ['render() の本体に知らせを書く', GOOD.replace('  notifyWaiting(listView);', '  void vscode.window.showInformationMessage("x");\n  notifyWaiting(listView);'), 'showOnlyInNotifyFn'],
  ['ボタンを 2 つにする', GOOD.replace('SHOW_RUN_LABEL).then', 'SHOW_RUN_LABEL, "もう1つ").then'), 'oneButton'],
  ['押されなくてもコマンドを実行する', GOOD.replace('if (pick === SHOW_RUN_LABEL) ', ''), 'buttonRunsShowRun'],
  ['retarget で基準を捨てない', GOOD.replace('  noticeBase = null;\n', ''), 'retargetDropsBase'],
  ['loadLatest の前に呼ぶ', GOOD.replace('  const current = await loadLatest();\n  if (!current) return;\n', '  notifyWaiting(listView);\n  const current = await loadLatest();\n  if (!current) return;\n'), 'renderCallsNotify'],
  ['基準を workspaceState に覚える', GOOD.replace('  noticeBase = listView.rows;', '  noticeBase = listView.rows;\n  void rememberRun(memory, "x");'), 'noPersist'],
  ['前の版の節を読まない', GOOD.replace(/  const legacy = .*\n/, '').replace('chooseSetting(current, legacy, true)', 'chooseSetting(current, undefined, true)'), 'readsSettingWithLegacy'],
  ['知らせの関数がステータスバーを触る', GOOD.replace('  const text = ', '  statusItem.text = "x";\n  const text = '), 'noPostNoStatus'],
];

for (const [label, source, id] of BROKEN) {
  test(`D0046-AC-14: 検査の見本：${label}と、${id} が見つける`, () => {
    assert.notEqual(source, GOOD, '見本を壊せていない');
    assert.ok(problems(source).includes(id), `${id} が見つけられない（見つけたもの：${problems(source).join(', ')}）`);
  });
}
