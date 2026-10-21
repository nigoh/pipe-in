// 入口：vscode に触れる唯一のファイル。コマンド・ステータスバー・パネル・ファイルの監視・エディタで開く、を担い、判定は持たない。
// 監視は拡張機能で1つ。記録が変わったら図の状態を作り直し、ステータスバーと（開いていれば）パネルの両方に配る。
// 実行の一覧（直下の開発フロー・<work_dir>/<パイプ名>/・archive/・同じ git リポジトリの別の worktree）から1つを選んで見る。
// 既定はいまの work_dir の最新、パネルの一覧で切り替えられる。選びは workspaceState に覚える（書くのはそれだけ。work_dir・.git・別の worktree には書かない）。
// 別の worktree と archive は、パネルが見えている間だけ約5秒ごとに読み直す（app/refreshPolicy.ts）。
// 「止まっているかも」の印の目安（pipe-in.staleAfterMinutes）は、設定を読んで画面の部品に渡すだけ（秒への直しは app/staleness.ts）。変わったら描き直す。
// パイプ作業台（pipe-in.editPipe）は .pipe-in/pipes/ と前の版の置き場所（どちらも無ければ pipes/）のパイプを開き、
// 保存を押したときだけ、開いたパイプのフォルダ（新しいパイプは pipe-in-<名前>/）に書く。work_dir には書かない。
// 保存した版と、閉じたときの下書きは、拡張の保存場所（storageUri の pipe-versions/）にだけ書く。
// 名前（コマンド ID・設定の節・パネルの型）は app/names.ts の表から読む。前の版の設定・コマンド ID もそこで読み替える。
import { randomBytes } from 'node:crypto';
import { existsSync } from 'node:fs';
import path from 'node:path';
import * as vscode from 'vscode';
import { COMMANDS, LEGACY_COMMANDS, LEGACY_SECTION, SECTION, SETTING_SHOW_OTHER, SETTING_STALE_AFTER, VIEW_IDS, chooseSetting, settingKeys } from './app/names.ts';
import { choosePipesDirs, folderFor, isPipeName, listPipeRefs, loadPipe, promptRelFor, savePipe, saveTarget } from './app/pipeEditor.ts';
import type { PipeRef, PipeStore } from './app/pipeEditor.ts';
import { listVersions, readVersion, recordVersion } from './app/pipeVersions.ts';
import type { VersionStore } from './app/pipeVersions.ts';
import { createFsVersionStore } from './infra/fsVersions.ts';
import { PipeLoadError, newPipe, validatePipe } from './domain/pipeModel.ts';
import type { PipeModel } from './domain/pipeModel.ts';
import { createFsPipeStore } from './infra/fsPipes.ts';
import { parseEditorMessage } from './view/messages.ts';
import type { ToEditorMessage } from './view/messages.ts';
import { editorTitle, renderPipeEditorHtml } from './view/pipeEditorHtml.ts';
import { DEFAULT_WORK_DIR, refreshView, resolveWorkDir } from './app/refreshView.ts';
import type { PipelineView } from './domain/pipelineView.ts';
import { resolveArtifactPath } from './domain/artifacts.ts';
import { HERE } from './domain/runs.ts';
import type { RunKey } from './domain/runs.ts';
import type { RunListView } from './domain/runList.ts';
import { DEBOUNCE_MS, POLL_MS, WATCH_GLOB, createPoller, shouldPoll } from './app/refreshPolicy.ts';
import { chooseEntry, findEntry, isPreviousRun, loadRunList, toListView } from './app/runList.ts';
import type { RunList, RunsSource } from './app/runList.ts';
import { rememberRun, restoreRun } from './app/selection.ts';
import { staleAfterSeconds } from './app/staleness.ts';
import { createFsRunsSource, createFsWorkDirSource } from './infra/fsWorkDirSource.ts';
import { parseWebviewMessage } from './view/messages.ts';
import type { ToPanelMessage } from './view/messages.ts';
import { renderPanelHtml, renderViewBody } from './view/panelHtml.ts';
import { statusBarLabel } from './view/statusBar.ts';

/** 知らせの頭とパネルの題に出す名前 */
const NAME = 'pipe-in';
/** 選んだ run が別の worktree にあるとき、そのフォルダに足す監視の対象（外の場所は再帰で張れないので 1 段） */
const REMOTE_WATCH_GLOB = '{state.json,*.md,logs/*.jsonl}';

interface WorkDirTarget {
  abs: string;
  display: string;
  /** ワークスペースの最初のフォルダ（別の worktree を見つける起点） */
  root: string;
  /** work_dir の設定値（別の worktree の根に当てはめる） */
  setting: string;
}

let panel: vscode.WebviewPanel | undefined;let statusItem: vscode.StatusBarItem | undefined;
let target: WorkDirTarget | null = null;
let watcher: vscode.FileSystemWatcher | undefined;
let timer: ReturnType<typeof setTimeout> | undefined;
/** 別の worktree の run を選んでいるときだけ、そのフォルダを見る 2 つ目の監視 */
let remoteWatcher: vscode.FileSystemWatcher | undefined;
let remoteDir: string | null = null;
/** 選んだ実行の目印。workspaceState に覚え、開き直しても戻す。一覧に無ければ使わない（既定の最新） */
let selected: RunKey | null = null;
/** 覚える場所（ワークスペースごとの拡張の保存場所） */
let memory: vscode.Memento | undefined;
/** 直前に出した一覧。パネルから来た目印はこの中にあるものだけ受け付ける */
let lastList: RunList | null = null;
let runsSource: RunsSource | null = null;
/** 直前に出した、選んだ run が動いている・確認待ちか（パネルが隠れて見えたとき、読み直しを続けるかの判断に使う） */
let lastLive = false;
/** いま見ている実行のフォルダと、開いてよい成果物の名前 */
let shown: { runAbs: string; artifacts: string[] } | null = null;
/** パネルが見えている間だけ、別の worktree と archive を読み直す */
const poller = createPoller({
  intervalMs: POLL_MS,
  run: () => render(),
  setTimer: (fn, ms) => setTimeout(fn, ms),
  clearTimer: (handle) => clearTimeout(handle),
});

interface CurrentView {
  view: PipelineView;
  listView: RunListView;
  /** 選んだ run が別の worktree にあるとき、そのフォルダ */
  otherDir: string | null;
  /** 選んだ run が動いている・確認待ちか（時系列の帯が「今」まで伸びる。読み直しを続ける） */
  live: boolean;
  /** 「止まっているかも」の印を出す目安（秒）。設定 pipe-in.staleAfterMinutes から。null なら印を出さない */
  staleAfterSec: number | null;
}

let extensionUri: vscode.Uri | undefined;
/** 保存した版の置き場所（拡張の保存場所の pipe-versions/） */
let versionsRoot: string | undefined;
/** 開いている作業台（パイプの名前 → パネル） */
const editors = new Map<string, vscode.WebviewPanel>();

export function activate(context: vscode.ExtensionContext): void {
  extensionUri = context.extensionUri;
  versionsRoot = vscode.Uri.joinPath(context.storageUri ?? context.globalStorageUri, 'pipe-versions').fsPath;
  statusItem = vscode.window.createStatusBarItem(VIEW_IDS.status, vscode.StatusBarAlignment.Left, 50);
  statusItem.name = NAME;
  statusItem.command = COMMANDS.showRun;
  memory = context.workspaceState;
  selected = restoreRun(memory);

  const handlers: Record<string, () => Promise<void>> = {
    [COMMANDS.showRun]: () => showRun(),
    [COMMANDS.editPipe]: () => editPipe(),
  };
  for (const [id, run] of Object.entries(handlers)) context.subscriptions.push(vscode.commands.registerCommand(id, run));
  // 前の版のコマンド ID は、キー割り当てが効くように登録だけする（package.json に出さないのでパレットには出ない）
  for (const [old, now] of Object.entries(LEGACY_COMMANDS)) {
    const run = handlers[now];
    if (run) context.subscriptions.push(vscode.commands.registerCommand(old, run));
  }

  context.subscriptions.push(
    statusItem,
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (settingKeys('workDir').some((key) => event.affectsConfiguration(key))) retarget();
      // 別の worktree を出す・出さないは、場所を決め直すだけ（監視は変わらない）。覚えた選びは消さない
      else if (event.affectsConfiguration(`${SECTION}.${SETTING_SHOW_OTHER}`)) void render();
      // 止まっているかもの目安が変わったら、開いているパネルを描き直す（拡張を開き直さなくてよい）
      else if (event.affectsConfiguration(`${SECTION}.${SETTING_STALE_AFTER}`)) void render();
    }),
    vscode.workspace.onDidChangeWorkspaceFolders(() => retarget()),
    { dispose: () => stopWatching() },
  );
  retarget();
}

/** 設定を読む。新しい設定を書いていればそれ、無くて前の版の設定があればそれ、どちらも無ければ fallback */
function readSetting(key: 'workDir' | 'pipesDir', fallback: string): string {
  const current = vscode.workspace.getConfiguration(SECTION).inspect<string>(key);
  const legacy = vscode.workspace.getConfiguration(LEGACY_SECTION).inspect<string>(key);
  return chooseSetting(current, legacy, fallback);
}

export function deactivate(): void {
  poller.stop();
  panel?.dispose();
  panel = undefined;
  for (const p of editors.values()) p.dispose();
  editors.clear();
  stopWatching();
}

function currentWorkDir(): WorkDirTarget | null {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) return null;
  const setting = readSetting('workDir', DEFAULT_WORK_DIR).trim() || DEFAULT_WORK_DIR;
  const abs = resolveWorkDir(folder.uri.fsPath, setting);
  return { abs, display: abs, root: folder.uri.fsPath, setting };
}

function stopWatching(): void {
  if (timer !== undefined) clearTimeout(timer);
  timer = undefined;
  watcher?.dispose();
  watcher = undefined;
  watchRemote(null);
}

/** 選んだ run が別の worktree にあるときだけ、そのフォルダにも監視を張る。無ければ（変わったら）捨てる。 */
function watchRemote(dir: string | null): void {
  if (dir === remoteDir) return;
  remoteWatcher?.dispose();
  remoteWatcher = undefined;
  remoteDir = dir;
  if (dir === null) return;
  const remoteUri = vscode.Uri.file(dir);
  remoteWatcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(remoteUri, REMOTE_WATCH_GLOB));
  remoteWatcher.onDidCreate(schedule);
  remoteWatcher.onDidChange(schedule);
  remoteWatcher.onDidDelete(schedule);
}

/** パネルが見えていて、別の worktree か archive の行があるか、選んだ run が動いている・確認待ちのときだけ、約5秒ごとの読み直しを動かす。 */
function updatePolling(live: boolean): void {
  if (shouldPoll({ visible: panel !== undefined && panel.visible, hasRemote: lastList?.hasRemote === true, live })) poller.start();
  else poller.stop();
}

/** 見る work_dir を決め直し、監視を張り直して描き直す。フォルダを開いていなければボタンを隠す。覚えた選びは消さない（新しい候補にあれば使う）。 */
function retarget(): void {
  stopWatching();
  shown = null;
  lastList = null;
  target = currentWorkDir();
  if (!target) {
    runsSource = null;
    statusItem?.hide();
    return;
  }
  runsSource = createFsRunsSource(target.root, target.abs, target.setting);
  const workDirUri = vscode.Uri.file(target.abs);
  watcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(workDirUri, WATCH_GLOB));
  watcher.onDidCreate(schedule);
  watcher.onDidChange(schedule);
  watcher.onDidDelete(schedule);
  statusItem?.show();
  void render();
}

function schedule(): void {
  if (timer !== undefined) clearTimeout(timer);
  timer = setTimeout(() => {
    timer = undefined;
    void render();
  }, DEBOUNCE_MS);
}

/** 実行の一覧を読み、見る実行を選んで図の状態を作る。 */
async function currentView(): Promise<CurrentView | null> {
  if (!target || !runsSource) return null;
  // 時計を読むのはここだけ（ドメインは「今」を引数で受ける）
  const clock = { nowMs: Date.now(), localOffsetMin: -new Date().getTimezoneOffset() };
  const showOthers = vscode.workspace.getConfiguration(SECTION).get<boolean>(SETTING_SHOW_OTHER, true);
  // 設定の値（分）を目安の秒にするのは app/staleness.ts。ここは読んで渡すだけ
  const staleAfterSec = staleAfterSeconds(vscode.workspace.getConfiguration(SECTION).get<unknown>(SETTING_STALE_AFTER));
  const list = await loadRunList(runsSource, { showOthers, clock });
  const here = { key: HERE, label: null, workDirAbs: target.abs };
  const choice = chooseEntry(list, selected, here);
  // 前の実行（archive/）の写しだと基盤に伝える（前の実行は印の対象外）
  const view = await refreshView(createFsWorkDirSource(choice.dirAbs, choice.dirAbs, { previous: isPreviousRun(list, choice.key) }), choice.dirAbs, clock);
  shown = { runAbs: choice.dirAbs, artifacts: view.artifacts.map((a) => a.name) };
  lastList = list;
  const other = !choice.key.startsWith(`${HERE}|`);
  return { view, listView: toListView(list, choice.key, target.setting), otherDir: other ? choice.dirAbs : null, live: view.gantt.live, staleAfterSec };
}

async function render(): Promise<void> {
  const current = await currentView();
  if (!current) return;
  const { view, listView, otherDir, live, staleAfterSec } = current;
  if (statusItem) {
    const label = statusBarLabel(view);
    statusItem.text = label.text;
    statusItem.tooltip = label.tooltip;
  }
  if (panel) {
    const message: ToPanelMessage = { type: 'render', html: renderViewBody(view, listView, staleAfterSec) };
    void panel.webview.postMessage(message);
  }
  watchRemote(panel !== undefined ? otherDir : null);
  lastLive = live;
  updatePolling(live);
}

async function showRun(): Promise<void> {
  if (panel) {
    panel.reveal();
    return;
  }
  if (!target) {
    void vscode.window.showWarningMessage(`${NAME}: ワークスペースのフォルダを開いてから実行してください。`);
    return;
  }

  const created = vscode.window.createWebviewPanel(VIEW_IDS.run, NAME, vscode.ViewColumn.Beside, {
    enableScripts: true,
    localResourceRoots: [],
  });
  panel = created;

  const onMessage = created.webview.onDidReceiveMessage(async (value: unknown) => {
    const msg = parseWebviewMessage(value);
    if (!msg) return;
    if (msg.type === 'ready') {
      await render();
      return;
    }
    if (!target) return;
    if (msg.type === 'selectRun') {
      // 直前に出した一覧にある目印だけを受け付ける（パネルから来た文字でフォルダを決めない）
      if (lastList === null || findEntry(lastList, msg.id) === null) return;
      selected = msg.id;
      if (memory) await rememberRun(memory, msg.id);
      await render();
      return;
    }
    if (!shown) return;
    const file = resolveArtifactPath(shown.runAbs, msg.name, shown.artifacts);
    if (file === null) return;
    try {
      await vscode.window.showTextDocument(vscode.Uri.file(file), { preview: true, viewColumn: vscode.ViewColumn.One });
    } catch {
      void vscode.window.showWarningMessage(`${NAME}: ${msg.name} を開けませんでした。`);
    }
  });

  // 隠れたら読み直しを止め、また見えたら1回すぐ読み直して追いつく
  const onViewState = created.onDidChangeViewState(() => {
    updatePolling(lastLive);
    if (created.visible) void render();
  });

  created.onDidDispose(() => {
    onMessage.dispose();
    onViewState.dispose();
    if (panel === created) {
      panel = undefined;
      // 選びは忘れない（開き直したときに戻す）。別の worktree の監視と読み直しは止める
      poller.stop();
      watchRemote(null);
      void render();
    }
  });

  const current = await currentView();
  if (current) {
    created.webview.html = renderPanelHtml(current.view, randomBytes(16).toString('base64'), current.listView, current.staleAfterSec);
    watchRemote(current.otherDir);
    lastLive = current.live;
    updatePolling(current.live);
  }
}

// ---- パイプ作業台 ----------------------------------------------------------------

/** 作業台で読み書きするパイプの置き場所（設定 pipe-in.pipesDir。空ならワークスペースの .pipe-in/pipes・前の版の置き場所 → pipes） */
function pipesDirs(): string[] {
  const folder = vscode.workspace.workspaceFolders?.[0];
  return choosePipesDirs(readSetting('pipesDir', ''), folder ? folder.uri.fsPath : null, existsSync);
}

/** 置き場所ごとの口 */
function shelves(dirs: string[]): { dir: string; store: PipeStore }[] {
  return dirs.map((dir) => ({ dir, store: createFsPipeStore(dir) }));
}

type PipeItem = vscode.QuickPickItem & { ref?: PipeRef };

async function editPipe(): Promise<void> {
  const dirs = pipesDirs();
  const first = dirs[0];
  if (first === undefined || !extensionUri) {
    void vscode.window.showWarningMessage(`${NAME}: ワークスペースのフォルダを開くか、設定 pipe-in.pipesDir にパイプの置き場所を書いてください。`);
    return;
  }
  const refs = await listPipeRefs(shelves(dirs));
  const NEW: PipeItem = { label: '$(add) 新しいパイプを作る' };
  const items: PipeItem[] = [NEW, ...refs.map((ref) => ({ label: ref.name, description: path.join(ref.dir, ref.folder), ref }))];
  const picked = await vscode.window.showQuickPick(items, { placeHolder: `開くパイプ（${dirs.join('・')}）` });
  if (!picked) return;
  let model: PipeModel;
  if (!picked.ref) {
    const name = await vscode.window.showInputBox({
      prompt: `新しいパイプの名前（${path.join(first, folderFor('<名前>'))} になります）`,
      validateInput: (v) => {
        if (!isPipeName(v)) return '英小文字・数字・- で書いてください（logs・end は使えません）';
        const same = refs.find((r) => r.name === v);
        return same ? `その名前のパイプはもうあります（${path.join(same.dir, same.folder)}）` : null;
      },
    });
    if (!name) return;
    model = newPipe(name);
  } else {
    try {
      model = await loadPipe(createFsPipeStore(picked.ref.dir), picked.ref.folder);
    } catch (e) {
      void vscode.window.showErrorMessage(`${NAME}: ${e instanceof PipeLoadError ? e.message : `パイプを読めませんでした（${String(e)}）`}`);
      return;
    }
  }
  openEditor(dirs, picked.ref ?? null, model, picked.ref ? model.stages.map((s) => s.name) : []);
}

/** 保存した版の置き場所（拡張の保存場所の pipe-versions/。プロジェクトには書かない） */
function versionStore(): VersionStore | null {
  return versionsRoot ? createFsVersionStore(versionsRoot) : null;
}

/**
 * 作業台を開く。saved は保存済みの形（指示文を開くときに場所を決める）、savedNames はそのうちファイルのある段の name。
 * draft を渡すと、保存していない下書きとして開く（閉じたときに残した下書きを開き直すとき）。
 */
function openEditor(dirs: string[], opened: PipeRef | null, saved: PipeModel, savedNames: string[], draft?: PipeModel): void {
  const name = saved.name;
  const existing = editors.get(name);
  if (existing) {
    existing.reveal();
    return;
  }
  // 保存先は拡張の側で持つ（開いたパイプのフォルダ。新しいパイプは最初の保存で決まる）。パネルから来た値では決めない
  let ref: PipeRef | null = opened;
  const folderNow = (): string => ref?.folder ?? folderFor(name);
  const versions = versionStore();
  const outDir = vscode.Uri.joinPath(extensionUri!, 'out');
  const panel = vscode.window.createWebviewPanel(VIEW_IDS.pipeEditor, editorTitle(name, draft !== undefined), vscode.ViewColumn.Active, {
    enableScripts: true,
    retainContextWhenHidden: true,
    localResourceRoots: [outDir],
  });
  editors.set(name, panel);
  /** 保存していない今の形（パネルが知らせてくる）。閉じたときに下書きとして残す */
  let unsaved: PipeModel | null = draft ?? null;
  const post = (message: ToEditorMessage): void => { void panel.webview.postMessage(message); };
  const postVersions = async (): Promise<void> => { if (versions) post({ type: 'versions', list: await listVersions(versions, name) }); };
  const onMessage = panel.webview.onDidReceiveMessage(async (value: unknown) => {
    const msg = parseEditorMessage(value);
    if (!msg) return;
    if (msg.type === 'ready') {
      post({ type: 'load', model: draft ?? saved, folder: folderNow(), savedNames, ...(draft ? { dirty: true } : {}) });
      await postVersions();
      return;
    }
    if (msg.type === 'state') {
      panel.title = editorTitle(name, msg.dirty);
      unsaved = msg.dirty ? msg.model ?? unsaved : null;
      return;
    }
    if (msg.type === 'loadVersion') {
      const model = versions ? await readVersion(versions, name, msg.id) : null;
      if (model) post({ type: 'version', id: msg.id, model });
      else void vscode.window.showWarningMessage(`${NAME}: その版を読めませんでした。`);
      return;
    }
    if (msg.type === 'openPrompt') {
      // 開く場所は保存済みの形から決める（パネルから来た name は、保存済みの段にあるかを確かめるのに使うだけ）
      const rel = ref && savedNames.includes(msg.name) ? promptRelFor(saved, msg.name) : null;
      if (rel === null || !ref) {
        void vscode.window.showWarningMessage(`${NAME}: 段 ${msg.name} の指示文はまだ保存されていません。`);
        return;
      }
      try {
        await vscode.window.showTextDocument(vscode.Uri.file(path.join(ref.dir, ref.folder, ...rel.split('/'))), { preview: true, viewColumn: vscode.ViewColumn.Beside });
        // 書き換えても作業台の保存で上書きされるので、読むだけにする
        await vscode.commands.executeCommand('workbench.action.files.setActiveEditorReadonlyInSession');
      } catch {
        void vscode.window.showWarningMessage(`${NAME}: ${rel} を開けませんでした。`);
      }
      return;
    }
    // 保存先はこのパネルを開いたパイプに決める（パネルから来た名前では決めない）
    const toSave: PipeModel = { ...msg.model, name };
    try {
      const target = saveTarget(await listPipeRefs(shelves(dirs)), ref, name, dirs);
      if ('error' in target) throw new Error(target.error);
      const written = await savePipe(createFsPipeStore(target.dir), toSave, target.folder);
      if (!ref || ref.dir !== target.dir || ref.folder !== target.folder) ref = { name, dir: target.dir, folder: target.folder, legacy: false };
      saved = toSave;
      savedNames = toSave.stages.map((s) => s.name);
      unsaved = null;
      panel.title = editorTitle(name, false);
      const { errors } = validatePipe(toSave);
      post({ type: 'saved', written, errors, savedNames });
      if (versions) {
        try {
          post({ type: 'versions', list: await recordVersion(versions, toSave, Date.now()) });
        } catch {
          // 版を残せなくても、保存そのものは済んでいる
        }
      }
      if (errors.length) void vscode.window.showWarningMessage(`${NAME}: ${folderNow()} を保存しました。検査で ${errors.length} 件の誤りがあります（パネルの「検査」を見てください）。`);
    } catch (e) {
      post({ type: 'failed', message: String(e instanceof Error ? e.message : e) });
    }
  });
  panel.onDidDispose(() => {
    onMessage.dispose();
    editors.delete(name);
    // VSCode はパネルを閉じるのを止められないので、保存していない変更は下書きの版に残し、開き直せるようにする
    const left = unsaved;
    if (!left || !versions) return;
    void (async () => {
      try {
        await recordVersion(versions, { ...left, name }, Date.now(), true);
      } catch {
        return;
      }
      const REOPEN = '開き直す';
      const pick = await vscode.window.showInformationMessage(`${NAME}: ${folderNow()} を保存せずに閉じました。下書きを履歴の「保存した版」に残しています。`, REOPEN);
      if (pick === REOPEN) openEditor(dirs, ref, saved, savedNames, { ...left, name });
    })();
  });
  panel.webview.html = renderPipeEditorHtml({
    nonce: randomBytes(16).toString('base64'),
    scriptUri: panel.webview.asWebviewUri(vscode.Uri.joinPath(outDir, 'pipeEditor.js')).toString(),
    cspSource: panel.webview.cspSource,
  });
}
