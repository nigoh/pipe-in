// 入口 extension.ts の配線の検査（D0079：返事を送る。AC-47）。
// extension.ts は vscode を import するので単体では動かせない。呼び出しの形・順を、ソースを文字で読んで確かめる
// （extensionRun.test.ts と同じ作り。文字で読む部品は test/sourceText.ts）。
// ここで見るのは配線だけ：返事を書く口を呼ぶのは handleReply の 1 か所だけ。書く場所は自分が作った一覧（lastList・findEntry）の実行のフォルダから決め、
// パネルから来た値では決めない。段と識別子は読み直した記録（currentView → replyOfferOf）から取る。パネルの知らせから読む値は action と feedback だけ。
// 判断（印が同じか・知らない動作か）は app/replyFlow.ts（replyFlow.test.ts）と domain/ のテスト。
// 構成：1) 検査の本体  2) 実物の extension.ts  3) 検査そのもの（守っている見本・壊した見本）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { blockAfter, callArgs, functionBody, inOrder, withoutComments } from './test/sourceText.ts';

// ---- 1) 検査の本体 ----------------------------------------------------------------

type ReplyWiringId =
  | 'importsStore'
  | 'importsFlow'
  | 'oneStoreCall'
  | 'oneSendReply'
  | 'storeRootFromTarget'
  | 'dispatchOnly'
  | 'handlerExists'
  | 'guardsFirst'
  | 'placeFromList'
  | 'panelFields'
  | 'noPanelPlace'
  | 'rereadFromRecord'
  | 'shownFromOffer'
  | 'refusalShown'
  | 'renderAfter'
  | 'liveIsLive'
  | 'offerAdopted'
  | 'noWrites';

const flat = (s: string): string => s.replace(/\s+/g, ' ').trim();

function problems(source: string): ReplyWiringId[] {
  const code = withoutComments(source);
  const handler = functionBody(code, 'handleReply');
  const sendArgs = handler === null ? [] : callArgs(handler, 'sendReply');
  const dispatch = blockAfter(code, /if \(msg\.type === 'reply'\) \{/);
  const current = functionBody(code, 'currentView');
  const fields = handler === null ? [] : Array.from(new Set(Array.from(handler.matchAll(/\bmsg\.(\w+)/g), (m) => m[1]!))).sort();
  const count = (text: string | null, re: RegExp): number => (text === null ? 0 : Array.from(text.matchAll(new RegExp(re.source, 'g'))).length);

  const ok: Record<ReplyWiringId, boolean> = {
    importsStore: /import \{[^}]*\bcreateFsReplyStore\b[^}]*\} from '\.\/infra\/fsReplies\.ts'/.test(code),
    importsFlow:
      /import \{[^}]*\breplyOfferOf\b[^}]*\} from '\.\/app\/replyFlow\.ts'/.test(code) &&
      /import \{[^}]*\bsendReply\b[^}]*\} from '\.\/app\/replyFlow\.ts'/.test(code) &&
      /import \{[^}]*\bisLive\b[^}]*\} from '\.\/domain\/replyWait\.ts'/.test(code) &&
      /import \{[^}]*\breplyRefusalText\b[^}]*\} from '\.\/view\/replyHtml\.ts'/.test(code),
    // 返事を書く口を作って呼ぶのは 1 か所だけで、handleReply の中
    oneStoreCall: callArgs(code, 'createFsReplyStore').length === 1 && handler !== null && callArgs(handler, 'createFsReplyStore').length === 1,
    oneSendReply: callArgs(code, 'sendReply').length === 1 && sendArgs.length === 1,
    // 口の根は自分が決めた work_dir の絶対パス（target.abs）。パネルから来た値ではない
    storeRootFromTarget: handler !== null && /\bcreateFsReplyStore\(\s*target\.abs\s*\)/.test(handler),
    // パネルの reply の知らせを handleReply に渡すのは 1 か所だけ
    dispatchOnly: dispatch !== null && callArgs(dispatch, 'handleReply').length === 1 && flat(callArgs(dispatch, 'handleReply')[0]!) === 'msg' && callArgs(code, 'handleReply').length === 1,
    handlerExists: handler !== null,
    // 見せている実行の返事の申し出（shown.reply）・一覧・今の work_dir が無ければ書かずに終わる（口を作る前）
    guardsFirst:
      handler !== null &&
      /!target/.test(handler) &&
      /shown\??\.reply\s*===\s*null|!shown\??\.reply/.test(handler) &&
      /lastList\s*===\s*null/.test(handler) &&
      inOrder(handler, [/!target/, /findEntry\(/, /\bsendReply\(/]),
    // 書く場所は、自分が作った一覧の中の、見せている返事の申し出の実行から決める
    placeFromList: handler !== null && /\bfindEntry\(\s*lastList\s*,\s*shown\.reply\.key\s*\)/.test(handler) && inOrder(handler, [/\bfindEntry\(/, /\bcreateFsReplyStore\(/]),
    // パネルの知らせから読む値は action と feedback だけ
    panelFields: JSON.stringify(fields) === '["action","feedback"]',
    noPanelPlace: handler !== null && !/\bmsg\.(?:stage|id|path|dir|pipe|name|version|key|file|runId)\b/.test(handler) && !/\[\s*['"]?(?:stage|id|path|dir)['"]?\s*\]/.test(handler),
    // 段と識別子は、読み直した記録の申し出（replyOfferOf）から取る：sendReply の引数は choice・shown・reread・store だけ
    rereadFromRecord:
      sendArgs.length === 1 &&
      /\breread\s*:/.test(sendArgs[0]!) &&
      /\bcurrentView\(\)/.test(sendArgs[0]!) &&
      /\breplyOfferOf\(/.test(sendArgs[0]!) &&
      /\bstore\s*:/.test(sendArgs[0]!),
    shownFromOffer: sendArgs.length === 1 && /\bshown\s*:\s*shown\.reply\b/.test(sendArgs[0]!) && /\baction\s*:\s*msg\.action\b/.test(sendArgs[0]!) && /\bfeedback\s*:\s*msg\.feedback\b/.test(sendArgs[0]!),
    // 断ったら理由を見せ、パネルに replyRefused を送る
    refusalShown:
      handler !== null &&
      /!result\.ok|\.ok\s*\)\s*\{|!\w+\.ok/.test(handler) &&
      /showWarningMessage\([^)]*replyRefusalText\(/.test(handler) &&
      /type:\s*'replyRefused'/.test(handler),
    // 最後に描き直す（送った表示・消えた帯を反映）
    renderAfter: handler !== null && inOrder(handler, [/\bsendReply\(/, /replyRefused/, /\bawait render\(\)/]),
    // 見せる実行の写しに返事の申し出を入れ（currentView が replyOfferOf を呼ぶ）、読み直しを続ける判断は isLive
    offerAdopted: current !== null && /\breplyOfferOf\(\s*view\s*,\s*choice\.key\s*\)/.test(current) && /\bshown\b[\s\S]{0,80}\breply\b/.test(code),
    liveIsLive: current !== null && /\blive\s*:\s*isLive\(\s*view\s*\)/.test(current) && !/\blive\s*:\s*view\.gantt\.live\b/.test(current),
    // 返事を書く以外に、ファイルへ書く呼び出しを足さない
    noWrites: !/\b(?:writeFile|writeFileSync|appendFile|appendFileSync|mkdir|mkdirSync|rename|unlink|copyFile|rmSync|rm)\s*\(/.test(code) && count(code, /\bcreateFsReplyStore\(/) <= 1,
  };
  return (Object.keys(ok) as ReplyWiringId[]).filter((id) => !ok[id]);
}

// ---- 2) 実物の extension.ts ----------------------------------------------------------

const EXTENSION = readFileSync(new URL('./extension.ts', import.meta.url), 'utf8');

const WIRING: readonly { id: ReplyWiringId; what: string }[] = [
  { id: 'importsStore', what: 'extension.ts が infra/fsReplies.ts から createFsReplyStore を読む' },
  { id: 'importsFlow', what: 'extension.ts が app/replyFlow.ts（replyOfferOf・sendReply）・domain/replyWait.ts（isLive）・view/replyHtml.ts（replyRefusalText）から読む' },
  { id: 'handlerExists', what: '返事を送る手順 handleReply がある' },
  { id: 'oneStoreCall', what: '返事を書く口 createFsReplyStore( を作って呼ぶのは handleReply の中の 1 か所だけ' },
  { id: 'oneSendReply', what: 'sendReply( を呼ぶのは handleReply の中の 1 か所だけ' },
  { id: 'storeRootFromTarget', what: '口の根は target.abs（自分が決めた work_dir）。パネルから来た値ではない' },
  { id: 'dispatchOnly', what: 'パネルの reply の知らせ（msg.type === reply）を handleReply(msg) に渡すのは 1 か所だけ' },
  { id: 'guardsFirst', what: 'handleReply は target・shown.reply・lastList が無ければ、口を作る前に終わる（findEntry より前に確かめる）' },
  { id: 'placeFromList', what: '書く場所は、自分が作った一覧（lastList）の findEntry(lastList, shown.reply.key) の実行から決める（口を作るより前）' },
  { id: 'panelFields', what: 'handleReply がパネルの知らせから読む値は action と feedback だけ' },
  { id: 'noPanelPlace', what: 'handleReply はパネルの知らせの stage・id・path・dir・pipe などを使わない' },
  { id: 'rereadFromRecord', what: '段と識別子は読み直した記録から：sendReply の reread が currentView() と replyOfferOf( を通る' },
  { id: 'shownFromOffer', what: 'sendReply に渡す shown は shown.reply（自分が最後に描いた申し出）、choice は msg.action と msg.feedback だけ' },
  { id: 'refusalShown', what: '断られたら showWarningMessage に replyRefusalText( の文を出し、パネルへ replyRefused を送る' },
  { id: 'renderAfter', what: '最後に await render() で描き直す（送った表示・消えた帯を反映する）' },
  { id: 'offerAdopted', what: 'currentView が replyOfferOf(view, choice.key) を見せている実行の写し（shown）に入れる' },
  { id: 'liveIsLive', what: '読み直しを続ける判断 live は isLive(view)（印のある実行も続ける）。gantt.live のままにしない' },
  { id: 'noWrites', what: 'extension.ts にファイルへ書く呼び出しを足さない（書くのは createFsReplyStore の口だけ・1 か所）' },
];

// 実装の前から満たしていた検査は無い（noWrites は create の数が 0 でも満たすので「守る」）
const KEEP = new Set<ReplyWiringId>(['noWrites']);

for (const w of WIRING) {
  test(`D0079-AC-47: ${w.what}${KEEP.has(w.id) ? '（今のまま通る。守る）' : ''}`, () => {
    assert.ok(!problems(EXTENSION).includes(w.id), `extension.ts で守られていない：${w.id}`);
  });
}

// ---- 3) 検査そのもの：守っている見本は問題なし。壊した見本を見つける ----------------------

const GOOD = `
import { createFsReplyStore } from './infra/fsReplies.ts';
import { replyOfferOf, sendReply } from './app/replyFlow.ts';
import type { ReplyOffer } from './app/replyFlow.ts';
import { isLive } from './domain/replyWait.ts';
import { replyRefusalText } from './view/replyHtml.ts';
import { chooseEntry, findEntry, loadRunList, toListView } from './app/runList.ts';

let target: WorkDirTarget | null = null;
let lastList: RunList | null = null;
let lastListView: RunListView | null = null;
let shown: { runAbs: string; artifacts: string[]; reply: ReplyOffer | null } | null = null;

async function currentView(): Promise<CurrentView | null> {
  const t = target;
  const list = await loadRunList(src, { showOthers, clock });
  const choice = chooseEntry(list, selected, here);
  const view = await refreshView(createFsWorkDirSource(choice.dirAbs, choice.dirAbs, { previous: isPreviousRun(list, choice.key) }), choice.dirAbs, clock);
  return {
    view,
    list,
    listView: toListView(list, choice.key, t.setting),
    shownRun: { runAbs: choice.dirAbs, artifacts: view.artifacts.map((a) => a.name), reply: replyOfferOf(view, choice.key) },
    live: isLive(view),
    staleAfterSec,
  };
}

async function handleReply(msg: { type: 'reply'; action: string; feedback?: string }): Promise<void> {
  if (!target || !shown || shown.reply === null || lastList === null || lastListView === null) return;
  if (findEntry(lastList, shown.reply.key) === null) return;
  const result = await sendReply(
    { action: msg.action, feedback: msg.feedback },
    {
      shown: shown.reply,
      reread: () => currentView().then((c) => (c === null ? null : replyOfferOf(c.view, c.listView.selected))),
      store: createFsReplyStore(target.abs),
    },
  );
  if (!result.ok) {
    void vscode.window.showWarningMessage(NAME + ': ' + replyRefusalText(result.reason));
    void panel?.webview.postMessage({ type: 'replyRefused' });
  }
  await render();
}

async function showRun(): Promise<void> {
  const onMessage = created.webview.onDidReceiveMessage(async (value: unknown) => {
    const msg = parseWebviewMessage(value);
    if (!msg) return;
    if (msg.type === 'reply') {
      await handleReply(msg);
      return;
    }
    if (msg.type === 'selectRun') return;
  });
}
`;

const rep = (from: string, to: string): string => {
  assert.ok(GOOD.includes(from), `見本に無い文字：${from}`);
  return GOOD.replace(from, to);
};

const BROKEN: readonly [string, string, ReplyWiringId][] = [
  ['口を読み込まない', rep("import { createFsReplyStore } from './infra/fsReplies.ts';\n", ''), 'importsStore'],
  ['isLive を読み込まない', rep("import { isLive } from './domain/replyWait.ts';\n", ''), 'importsFlow'],
  ['handleReply が無い', rep('async function handleReply(', 'async function handleOther('), 'handlerExists'],
  ['口を 2 か所で作る', rep('async function showRun(): Promise<void> {', "const extra = createFsReplyStore(target!.abs);\nasync function showRun(): Promise<void> {"), 'oneStoreCall'],
  ['口を handleReply の外で作る', rep('      store: createFsReplyStore(target.abs),', '      store,').replace('async function handleReply(', 'const store = createFsReplyStore(target.abs);\nasync function handleReply('), 'oneStoreCall'],
  ['sendReply を 2 回呼ぶ', rep('  await render();\n}\n\nasync function showRun', '  await sendReply({ action: msg.action }, { shown: shown.reply, reread, store });\n  await render();\n}\n\nasync function showRun'), 'oneSendReply'],
  ['口の根をパネルの値にする', rep('createFsReplyStore(target.abs)', 'createFsReplyStore(msg.dir)'), 'storeRootFromTarget'],
  ['パネルの知らせの分かれが無い', rep("    if (msg.type === 'reply') {\n      await handleReply(msg);\n      return;\n    }\n", ''), 'dispatchOnly'],
  ['handleReply にパネルの知らせ以外を渡す', rep('await handleReply(msg);', 'await handleReply({ ...msg, dir: value });'), 'dispatchOnly'],
  ['handleReply を別の所からも呼ぶ', rep('async function showRun(): Promise<void> {', 'async function other(m: never): Promise<void> {\n  await handleReply(m);\n}\nasync function showRun(): Promise<void> {'), 'dispatchOnly'],
  ['見せている申し出が無くても進む', rep('shown.reply === null || ', ''), 'guardsFirst'],
  ['一覧が無くても進む', rep(' || lastList === null', ''), 'guardsFirst'],
  ['work_dir が無くても進む', rep('!target || ', ''), 'guardsFirst'],
  ['findEntry を通さない', rep('  if (findEntry(lastList, shown.reply.key) === null) return;\n', ''), 'placeFromList'],
  ['findEntry にパネルの値を渡す', rep('findEntry(lastList, shown.reply.key)', 'findEntry(lastList, msg.key)'), 'placeFromList'],
  ['パネルの段を読む', rep('{ action: msg.action, feedback: msg.feedback }', '{ action: msg.action, feedback: msg.feedback, stage: msg.stage }'), 'panelFields'],
  ['パネルの識別子を読む', rep('{ action: msg.action, feedback: msg.feedback }', '{ action: msg.action, feedback: msg.feedback, id: msg.id }'), 'noPanelPlace'],
  ['パネルの場所を読む', rep('createFsReplyStore(target.abs)', 'createFsReplyStore(target.abs + msg.path)'), 'noPanelPlace'],
  ['feedback を読まない', rep('{ action: msg.action, feedback: msg.feedback }', '{ action: msg.action }'), 'panelFields'],
  ['読み直さない（reread が無い）', rep('      reread: () => currentView().then((c) => (c === null ? null : replyOfferOf(c.view, c.listView.selected))),\n', '      reread: async () => shown!.reply,\n'), 'rereadFromRecord'],
  ['読み直した記録から申し出を作らない', rep('replyOfferOf(c.view, c.listView.selected)', 'shown!.reply'), 'rereadFromRecord'],
  ['shown が自分の申し出でない', rep('shown: shown.reply,', 'shown: { key: msg.key, stage: msg.stage, id: msg.id },'), 'shownFromOffer'],
  ['断った理由を見せない', rep("    void vscode.window.showWarningMessage(NAME + ': ' + replyRefusalText(result.reason));\n", ''), 'refusalShown'],
  ['パネルに replyRefused を送らない', rep("    void panel?.webview.postMessage({ type: 'replyRefused' });\n", ''), 'refusalShown'],
  ['最後に描き直さない', rep('  await render();\n}\n\nasync function showRun', '}\n\nasync function showRun'), 'renderAfter'],
  ['申し出を写しに入れない', rep(', reply: replyOfferOf(view, choice.key) }', ' }'), 'offerAdopted'],
  ['申し出に別の目印を渡す', rep('replyOfferOf(view, choice.key)', 'replyOfferOf(view, selected)'), 'offerAdopted'],
  ['読み直しの判断が gantt.live のまま', rep('live: isLive(view),', 'live: view.gantt.live,'), 'liveIsLive'],
  ['ファイルに書く', rep('  await render();\n}\n\nasync function showRun', "  await writeFile('x', msg.feedback ?? '');\n  await render();\n}\n\nasync function showRun"), 'noWrites'],
];

test('D0079-AC-47: 検査の見本：守っている見本は問題なし（今のまま通る。守る）', () => {
  assert.deepEqual(problems(GOOD), []);
});

for (const [label, source, id] of BROKEN) {
  test(`D0079-AC-47: 検査の見本：${label}と、${id} が見つける（今のまま通る。守る）`, () => {
    assert.notEqual(source, GOOD, '見本を壊せていない');
    assert.ok(problems(source).includes(id), `${id} が見つけられない（見つけたもの：${problems(source).join(', ')}）`);
  });
}

test('D0079-AC-47: 検査の見本：行頭のコメントに書いただけの呼び出しは数えない（コメントで通さない）（今のまま通る。守る）', () => {
  const sneaky = rep('      store: createFsReplyStore(target.abs),', '      // store: createFsReplyStore(target.abs),\n      store: fakeStore,');
  assert.ok(problems(sneaky).includes('oneStoreCall'));
  const second = rep('async function showRun(): Promise<void> {', '// createFsReplyStore(msg.dir) は使わない\nasync function showRun(): Promise<void> {');
  assert.ok(!problems(second).includes('oneStoreCall'), '行頭のコメントの呼び出しは数えない');
});
