// 入口：vscode に触れる唯一のファイル。コマンド・ステータスバー・パネル・ファイルの監視・エディタで開く、を担い、判定は持たない。
// 監視は拡張機能で1つ。記録が変わったら図の状態を作り直し、ステータスバーと（開いていれば）パネルの両方に配る。
import { randomBytes } from 'node:crypto';
import * as vscode from 'vscode';
import { refreshView, resolveWorkDir } from './app/refreshView.ts';
import type { PipelineView } from './domain/pipelineView.ts';
import { resolveArtifactPath } from './domain/artifacts.ts';
import { createFsWorkDirSource } from './infra/fsWorkDirSource.ts';
import { parseWebviewMessage } from './view/messages.ts';
import type { ToPanelMessage } from './view/messages.ts';
import { renderPanelHtml, renderViewBody } from './view/panelHtml.ts';
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
  target = currentWorkDir();
  if (!target) {
    statusItem?.hide();
    return;
  }
  watcher = vscode.workspace.createFileSystemWatcher(
    new vscode.RelativePattern(vscode.Uri.file(target.abs), '{state.json,*.md,logs/*.jsonl}'),
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

async function currentView(): Promise<PipelineView | null> {
  if (!target) return null;
  return refreshView(createFsWorkDirSource(target.abs, target.display), target.display);
}

async function render(): Promise<void> {
  const view = await currentView();
  if (!view) return;
  if (statusItem) {
    const label = statusBarLabel(view);
    statusItem.text = label.text;
    statusItem.tooltip = label.tooltip;
  }
  if (panel) {
    const message: ToPanelMessage = { type: 'render', html: renderViewBody(view) };
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
    const file = resolveArtifactPath(target.abs, msg.name);
    if (file === null) return;
    try {
      await vscode.window.showTextDocument(vscode.Uri.file(file), { preview: true, viewColumn: vscode.ViewColumn.One });
    } catch {
      void vscode.window.showWarningMessage(`devpipe: ${msg.name} を開けませんでした。`);
    }
  });

  created.onDidDispose(() => {
    onMessage.dispose();
    if (panel === created) panel = undefined;
  });

  const view = await currentView();
  if (view) created.webview.html = renderPanelHtml(view, randomBytes(16).toString('base64'));
}
