// 入口：vscode に触れる唯一のファイル。コマンド・パネル・ファイルの監視・エディタで開く、を担い、判定は持たない。
import { randomBytes } from 'node:crypto';
import * as vscode from 'vscode';
import { refreshView, resolveWorkDir } from './app/refreshView.ts';
import { resolveArtifactPath } from './domain/artifacts.ts';
import { createFsWorkDirSource } from './infra/fsWorkDirSource.ts';
import { parseWebviewMessage } from './view/messages.ts';
import type { ToPanelMessage } from './view/messages.ts';
import { renderPanelHtml, renderViewBody } from './view/panelHtml.ts';

const DEBOUNCE_MS = 200;

let panel: vscode.WebviewPanel | undefined;

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(vscode.commands.registerCommand('devpipe.showRun', () => showRun()));
}

export function deactivate(): void {
  panel?.dispose();
  panel = undefined;
}

interface WorkDirTarget {
  abs: string;
  display: string;
}

function currentWorkDir(): WorkDirTarget | null {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) return null;
  const setting = vscode.workspace.getConfiguration('devpipe').get<string>('workDir');
  const abs = resolveWorkDir(folder.uri.fsPath, setting);
  return { abs, display: abs };
}

async function showRun(): Promise<void> {
  if (panel) {
    panel.reveal();
    return;
  }
  const initial = currentWorkDir();
  if (!initial) {
    void vscode.window.showWarningMessage('devpipe: ワークスペースのフォルダを開いてから実行してください。');
    return;
  }

  const created = vscode.window.createWebviewPanel('devpipe.run', 'devpipe', vscode.ViewColumn.Beside, {
    enableScripts: true,
    localResourceRoots: [],
  });
  panel = created;

  let target = initial;
  let watcher: vscode.FileSystemWatcher | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const disposables: vscode.Disposable[] = [];

  const render = async (): Promise<void> => {
    const view = await refreshView(createFsWorkDirSource(target.abs, target.display), target.display);
    const message: ToPanelMessage = { type: 'render', html: renderViewBody(view) };
    void created.webview.postMessage(message);
  };

  const schedule = (): void => {
    if (timer !== undefined) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = undefined;
      void render();
    }, DEBOUNCE_MS);
  };

  const watch = (): void => {
    watcher?.dispose();
    watcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(vscode.Uri.file(target.abs), '{state.json,*.md,logs/*.jsonl}'),
    );
    watcher.onDidCreate(schedule);
    watcher.onDidChange(schedule);
    watcher.onDidDelete(schedule);
  };

  watch();

  disposables.push(
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (!event.affectsConfiguration('devpipe.workDir')) return;
      const next = currentWorkDir();
      if (!next) return;
      target = next;
      watch();
      schedule();
    }),
    created.webview.onDidReceiveMessage(async (value: unknown) => {
      const msg = parseWebviewMessage(value);
      if (!msg) return;
      if (msg.type === 'ready') {
        await render();
        return;
      }
      const file = resolveArtifactPath(target.abs, msg.name);
      if (file === null) return;
      try {
        await vscode.window.showTextDocument(vscode.Uri.file(file), { preview: true, viewColumn: vscode.ViewColumn.One });
      } catch {
        void vscode.window.showWarningMessage(`devpipe: ${msg.name} を開けませんでした。`);
      }
    }),
  );

  created.onDidDispose(() => {
    if (timer !== undefined) clearTimeout(timer);
    watcher?.dispose();
    for (const d of disposables) d.dispose();
    if (panel === created) panel = undefined;
  });

  const nonce = randomBytes(16).toString('base64');
  const view = await refreshView(createFsWorkDirSource(target.abs, target.display), target.display);
  created.webview.html = renderPanelHtml(view, nonce);
}
