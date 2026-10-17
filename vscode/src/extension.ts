// 入口：vscode に触れる唯一のファイル。コマンド・ステータスバー・パネル・ファイルの監視・エディタで開く、を担い、判定は持たない。
// 監視は拡張機能で1つ。記録が変わったら図の状態を作り直し、ステータスバーと（開いていれば）パネルの両方に配る。
// work_dir の中の実行（直下の開発フローと <work_dir>/<パイプ名>/）から1つを選んで見る。既定は最新、パネルで切り替えられる。
// パイプ作業台（devpipe.editPipe）は .devpipe/pipes/（無ければ pipes/）のパイプを開き、保存を押したときだけその devpipe-<名前>/ に書く。work_dir には書かない。
// 保存した版と、閉じたときの下書きは、拡張の保存場所（storageUri の pipe-versions/）にだけ書く。
import { randomBytes } from 'node:crypto';
import { existsSync } from 'node:fs';
import path from 'node:path';
import * as vscode from 'vscode';
import { choosePipesDir, isPipeName, listPipes, loadPipe, promptRelFor, savePipe } from './app/pipeEditor.ts';
import { listVersions, readVersion, recordVersion } from './app/pipeVersions.ts';
import type { VersionStore } from './app/pipeVersions.ts';
import { createFsVersionStore } from './infra/fsVersions.ts';
import { PipeLoadError, newPipe, validatePipe } from './domain/pipeModel.ts';
import type { PipeModel } from './domain/pipeModel.ts';
import { createFsPipeStore } from './infra/fsPipes.ts';
import { parseEditorMessage } from './view/messages.ts';
import type { ToEditorMessage } from './view/messages.ts';
import { editorTitle, renderPipeEditorHtml } from './view/pipeEditorHtml.ts';
import { refreshView, resolveWorkDir } from './app/refreshView.ts';
import type { PipelineView } from './domain/pipelineView.ts';
import { resolveArtifactPath } from './domain/artifacts.ts';
import { pickRun, resolveRunDir } from './domain/runs.ts';
import { createFsWorkDirSource, listRunCandidates } from './infra/fsWorkDirSource.ts';
import { parseWebviewMessage } from './view/messages.ts';
import type { ToPanelMessage } from './view/messages.ts';
import { renderPanelHtml, renderViewBody } from './view/panelHtml.ts';
import type { RunPicker } from './view/panelHtml.ts';
import { statusBarLabel } from './view/statusBar.ts';

const DEBOUNCE_MS = 200;
const COMMAND = 'devpipe.showRun';
const EDIT_COMMAND = 'devpipe.editPipe';

interface WorkDirTarget {
  abs: string;
  display: string;
}

let panel: vscode.WebviewPanel | undefined;
let statusItem: vscode.StatusBarItem | undefined;
let target: WorkDirTarget | null = null;
let watcher: vscode.FileSystemWatcher | undefined;
let timer: ReturnType<typeof setTimeout> | undefined;
/** パネルで選んだ実行の id。パネルを閉じたら忘れる（既定の最新に戻る）。 */
let selectedRun: string | null = null;
/** いま見ている実行のフォルダと、開いてよい成果物の名前 */
let shown: { runAbs: string; artifacts: string[] } | null = null;

interface CurrentView {
  view: PipelineView;
  picker: RunPicker;
}

let extensionUri: vscode.Uri | undefined;
/** 保存した版の置き場所（拡張の保存場所の pipe-versions/） */
let versionsRoot: string | undefined;
/** 開いている作業台（パイプの名前 → パネル） */
const editors = new Map<string, vscode.WebviewPanel>();

export function activate(context: vscode.ExtensionContext): void {
  extensionUri = context.extensionUri;
  versionsRoot = vscode.Uri.joinPath(context.storageUri ?? context.globalStorageUri, 'pipe-versions').fsPath;
  statusItem = vscode.window.createStatusBarItem('devpipe.status', vscode.StatusBarAlignment.Left, 50);
  statusItem.name = 'devpipe';
  statusItem.command = COMMAND;

  context.subscriptions.push(
    statusItem,
    vscode.commands.registerCommand(COMMAND, () => showRun()),
    vscode.commands.registerCommand(EDIT_COMMAND, () => editPipe()),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration('devpipe.workDir')) retarget();
    }),
    vscode.workspace.onDidChangeWorkspaceFolders(() => retarget()),
    { dispose: () => stopWatching() },
  );
  retarget();
}

export function deactivate(): void {
  panel?.dispose();
  panel = undefined;
  for (const p of editors.values()) p.dispose();
  editors.clear();
  stopWatching();
}

function currentWorkDir(): WorkDirTarget | null {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) return null;
  const setting = vscode.workspace.getConfiguration('devpipe').get<string>('workDir');
  const abs = resolveWorkDir(folder.uri.fsPath, setting);
  return { abs, display: abs };
}

function stopWatching(): void {
  if (timer !== undefined) clearTimeout(timer);
  timer = undefined;
  watcher?.dispose();
  watcher = undefined;
}

/** 見る work_dir を決め直し、監視を張り直して描き直す。フォルダを開いていなければボタンを隠す。 */
function retarget(): void {
  stopWatching();
  selectedRun = null;
  shown = null;
  target = currentWorkDir();
  if (!target) {
    statusItem?.hide();
    return;
  }
  watcher = vscode.workspace.createFileSystemWatcher(
    new vscode.RelativePattern(
      vscode.Uri.file(target.abs),
      '{state.json,*.md,logs/*.jsonl,*/state.json,*/*.md,*/logs/*.jsonl}',
    ),
  );
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

/** 候補を読み、見る実行を選んで図の状態を作る。 */
async function currentView(): Promise<CurrentView | null> {
  if (!target) return null;
  const candidates = await listRunCandidates(target.abs);
  const runId = pickRun(candidates, selectedRun);
  const runAbs = resolveRunDir(target.abs, runId, candidates) ?? target.abs;
  const view = await refreshView(createFsWorkDirSource(runAbs, runAbs), runAbs);
  shown = { runAbs, artifacts: view.artifacts.map((a) => a.name) };
  return { view, picker: { choices: candidates.map(({ id, label }) => ({ id, label })), selected: runId } };
}

async function render(): Promise<void> {
  const current = await currentView();
  if (!current) return;
  const { view, picker } = current;
  if (statusItem) {
    const label = statusBarLabel(view);
    statusItem.text = label.text;
    statusItem.tooltip = label.tooltip;
  }
  if (panel) {
    const message: ToPanelMessage = { type: 'render', html: renderViewBody(view, picker) };
    void panel.webview.postMessage(message);
  }
}

async function showRun(): Promise<void> {
  if (panel) {
    panel.reveal();
    return;
  }
  if (!target) {
    void vscode.window.showWarningMessage('devpipe: ワークスペースのフォルダを開いてから実行してください。');
    return;
  }

  const created = vscode.window.createWebviewPanel('devpipe.run', 'devpipe', vscode.ViewColumn.Beside, {
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
      // 候補にある id だけを受け付ける（パネルから来た文字でフォルダを決めない）
      if (resolveRunDir(target.abs, msg.id, await listRunCandidates(target.abs)) === null) return;
      selectedRun = msg.id;
      await render();
      return;
    }
    if (!shown) return;
    const file = resolveArtifactPath(shown.runAbs, msg.name, shown.artifacts);
    if (file === null) return;
    try {
      await vscode.window.showTextDocument(vscode.Uri.file(file), { preview: true, viewColumn: vscode.ViewColumn.One });
    } catch {
      void vscode.window.showWarningMessage(`devpipe: ${msg.name} を開けませんでした。`);
    }
  });

  created.onDidDispose(() => {
    onMessage.dispose();
    if (panel === created) {
      panel = undefined;
      selectedRun = null;
      void render();
    }
  });

  const current = await currentView();
  if (current) created.webview.html = renderPanelHtml(current.view, randomBytes(16).toString('base64'), current.picker);
}

// ---- パイプ作業台 ----------------------------------------------------------------

/** 作業台で読み書きするパイプの置き場所（設定 devpipe.pipesDir。空ならワークスペースの .devpipe/pipes → pipes） */
function pipesDir(): string | null {
  const folder = vscode.workspace.workspaceFolders?.[0];
  const setting = vscode.workspace.getConfiguration('devpipe').get<string>('pipesDir') || '';
  return choosePipesDir(setting, folder ? folder.uri.fsPath : null, existsSync);
}

async function editPipe(): Promise<void> {
  const dir = pipesDir();
  if (!dir || !extensionUri) {
    void vscode.window.showWarningMessage('devpipe: ワークスペースのフォルダを開くか、設定 devpipe.pipesDir にパイプの置き場所を書いてください。');
    return;
  }
  const store = createFsPipeStore(dir);
  const names = await listPipes(store);
  const NEW = '$(add) 新しいパイプを作る';
  const picked = await vscode.window.showQuickPick([NEW, ...names], { placeHolder: `開くパイプ（${dir}）` });
  if (!picked) return;
  let model: PipeModel;
  if (picked === NEW) {
    const name = await vscode.window.showInputBox({
      prompt: `新しいパイプの名前（${path.join(dir, 'devpipe-<名前>')} になります）`,
      validateInput: (v) => (!isPipeName(v) ? '英小文字・数字・- で書いてください（logs・end は使えません）' : names.includes(v) ? 'その名前のパイプはもうあります' : null),
    });
    if (!name) return;
    model = newPipe(name);
  } else {
    try {
      model = await loadPipe(store, picked);
    } catch (e) {
      void vscode.window.showErrorMessage(`devpipe: ${e instanceof PipeLoadError ? e.message : `パイプを読めませんでした（${String(e)}）`}`);
      return;
    }
  }
  openEditor(dir, model, picked === NEW ? [] : model.stages.map((s) => s.name));
}

/** 保存した版の置き場所（拡張の保存場所の pipe-versions/。プロジェクトには書かない） */
function versionStore(): VersionStore | null {
  return versionsRoot ? createFsVersionStore(versionsRoot) : null;
}

/**
 * 作業台を開く。saved は保存済みの形（指示文を開くときに場所を決める）、savedNames はそのうちファイルのある段の name。
 * draft を渡すと、保存していない下書きとして開く（閉じたときに残した下書きを開き直すとき）。
 */
function openEditor(dir: string, saved: PipeModel, savedNames: string[], draft?: PipeModel): void {
  const name = saved.name;
  const existing = editors.get(name);
  if (existing) {
    existing.reveal();
    return;
  }
  const store = createFsPipeStore(dir), versions = versionStore();
  const outDir = vscode.Uri.joinPath(extensionUri!, 'out');
  const panel = vscode.window.createWebviewPanel('devpipe.pipeEditor', editorTitle(name, draft !== undefined), vscode.ViewColumn.Active, {
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
      post({ type: 'load', model: draft ?? saved, savedNames, ...(draft ? { dirty: true } : {}) });
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
      else void vscode.window.showWarningMessage('devpipe: その版を読めませんでした。');
      return;
    }
    if (msg.type === 'openPrompt') {
      // 開く場所は保存済みの形から決める（パネルから来た name は、保存済みの段にあるかを確かめるのに使うだけ）
      const rel = savedNames.includes(msg.name) ? promptRelFor(saved, msg.name) : null;
      if (rel === null) {
        void vscode.window.showWarningMessage(`devpipe: 段 ${msg.name} の指示文はまだ保存されていません。`);
        return;
      }
      try {
        await vscode.window.showTextDocument(vscode.Uri.file(path.join(dir, `devpipe-${name}`, ...rel.split('/'))), { preview: true, viewColumn: vscode.ViewColumn.Beside });
        // 書き換えても作業台の保存で上書きされるので、読むだけにする
        await vscode.commands.executeCommand('workbench.action.files.setActiveEditorReadonlyInSession');
      } catch {
        void vscode.window.showWarningMessage(`devpipe: ${rel} を開けませんでした。`);
      }
      return;
    }
    // 保存先はこのパネルを開いたパイプに決める（パネルから来た名前では決めない）
    const toSave: PipeModel = { ...msg.model, name };
    try {
      const written = await savePipe(store, toSave);
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
      if (errors.length) void vscode.window.showWarningMessage(`devpipe: devpipe-${name} を保存しました。検査で ${errors.length} 件の誤りがあります（パネルの「検査」を見てください）。`);
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
      const pick = await vscode.window.showInformationMessage(`devpipe: devpipe-${name} を保存せずに閉じました。下書きを履歴の「保存した版」に残しています。`, REOPEN);
      if (pick === REOPEN) openEditor(dir, saved, savedNames, { ...left, name });
    })();
  });
  panel.webview.html = renderPipeEditorHtml({
    nonce: randomBytes(16).toString('base64'),
    scriptUri: panel.webview.asWebviewUri(vscode.Uri.joinPath(outDir, 'pipeEditor.js')).toString(),
    cspSource: panel.webview.cspSource,
  });
}
