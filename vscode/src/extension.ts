// 入口：vscode に触れる唯一のファイル。コマンド・ステータスバー・パネル・ファイルの監視・エディタで開く、を担い、判定は持たない。
// 監視は拡張機能で1つ。記録が変わったら図の状態を作り直し、ステータスバーと（開いていれば）パネルの両方に配る。
// work_dir の中の実行（直下の開発フローと <work_dir>/<パイプ名>/）から1つを選んで見る。既定は最新、パネルで切り替えられる。
import { randomBytes } from 'node:crypto';
import * as vscode from 'vscode';
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

export function activate(context: vscode.ExtensionContext): void {
  statusItem = vscode.window.createStatusBarItem('devpipe.status', vscode.StatusBarAlignment.Left, 50);
  statusItem.name = 'devpipe';
  statusItem.command = COMMAND;

  context.subscriptions.push(
    statusItem,
    vscode.commands.registerCommand(COMMAND, () => showRun()),
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
