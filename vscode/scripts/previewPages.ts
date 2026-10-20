// 画面の確認用のページのうち、ページの中身を決める部分（副作用なし。out/ に書くのは preview.ts だけ）。
// テーマの色（--vscode-* の仮の値）と、「実行を見る」パネルのページの組み立てをここに置き、テストから import する。
// パネルのページは、画面用の見本の記録（tests/fixtures/showcase/）を、拡張の本物の記録の読み取り（infra）→
// 図の状態（app・domain）→ renderPanelHtml（view）で HTML にしたもの。CSP の <meta> はそのまま残し、
// 足す script タグ・style タグにはすべて nonce を付ける。
import { cp, mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { refreshView } from '../src/app/refreshView.ts';
import { chooseEntry, loadRunList, toListView } from '../src/app/runList.ts';
import type { PipelineView, ViewClock } from '../src/domain/pipelineView.ts';
import { parseRunRecord } from '../src/domain/runRecord.ts';
import type { RunListView } from '../src/domain/runList.ts';
import { HERE } from '../src/domain/runs.ts';
import { parseStageLog, parseStageLogName } from '../src/domain/stageLog.ts';
import { createFsRunsSource, createFsWorkDirSource } from '../src/infra/fsWorkDirSource.ts';
import { renderPanelHtml, renderViewBody } from '../src/view/panelHtml.ts';

export type Theme = 'light' | 'dark';

const NONCE = 'preview';

// VSCode のテーマの色の仮の値（Dark Modern・Light Modern に近いもの）。作業台とパネルが使う色をすべて決める
const COMMON = '--vscode-font-family:system-ui,"Segoe UI","Hiragino Sans","Yu Gothic",sans-serif;--vscode-font-size:13px;--vscode-editor-font-family:Consolas,"SF Mono",monospace;--vscode-button-foreground:#ffffff;--vscode-button-background:#0078d4;--vscode-button-hoverBackground:#026ec1;--vscode-focusBorder:#0078d4;';
export const THEMES: Record<Theme, string> = {
  dark: COMMON + '--vscode-editor-background:#1f1f1f;--vscode-foreground:#cccccc;--vscode-descriptionForeground:#9d9d9d;--vscode-editorWidget-background:#202020;--vscode-panel-border:#2b2b2b;--vscode-editorIndentGuide-background:#404040;--vscode-charts-blue:#3794ff;--vscode-charts-orange:#d18616;--vscode-charts-red:#f14c4c;--vscode-charts-green:#89d185;--vscode-charts-purple:#b180d7;--vscode-charts-yellow:#cca700;--vscode-editor-selectionBackground:#264f78;--vscode-button-secondaryBackground:#313131;--vscode-button-secondaryForeground:#cccccc;--vscode-button-secondaryHoverBackground:#3c3c3c;--vscode-input-background:#313131;--vscode-input-foreground:#cccccc;--vscode-notifications-background:#1f1f1f;--vscode-notifications-foreground:#cccccc;--vscode-textCodeBlock-background:#2b2b2b;--vscode-list-hoverBackground:#2a2d2e;--vscode-dropdown-background:#313131;--vscode-dropdown-foreground:#cccccc;--vscode-inputValidation-errorBackground:#5a1d1d;--vscode-errorForeground:#f85149;--vscode-terminal-background:#181818;--vscode-terminal-foreground:#cccccc;--vscode-textLink-foreground:#4daafc;--vscode-list-activeSelectionBackground:#04395e;--vscode-list-activeSelectionForeground:#ffffff;--vscode-inputValidation-warningBackground:#352a05;',
  light: COMMON + '--vscode-editor-background:#ffffff;--vscode-foreground:#3b3b3b;--vscode-descriptionForeground:#717171;--vscode-editorWidget-background:#f8f8f8;--vscode-panel-border:#e5e5e5;--vscode-editorIndentGuide-background:#d3d3d3;--vscode-charts-blue:#1a85ff;--vscode-charts-orange:#d18616;--vscode-charts-red:#e51400;--vscode-charts-green:#388a34;--vscode-charts-purple:#652d90;--vscode-charts-yellow:#bf8803;--vscode-editor-selectionBackground:#add6ff;--vscode-button-secondaryBackground:#e5e5e5;--vscode-button-secondaryForeground:#3b3b3b;--vscode-button-secondaryHoverBackground:#cccccc;--vscode-input-background:#ffffff;--vscode-input-foreground:#3b3b3b;--vscode-notifications-background:#ffffff;--vscode-notifications-foreground:#3b3b3b;--vscode-textCodeBlock-background:#f2f2f2;--vscode-list-hoverBackground:#f2f2f2;--vscode-dropdown-background:#ffffff;--vscode-dropdown-foreground:#3b3b3b;--vscode-inputValidation-errorBackground:#f2dede;--vscode-errorForeground:#e51400;--vscode-terminal-background:#f8f8f8;--vscode-terminal-foreground:#3b3b3b;--vscode-textLink-foreground:#005fb8;--vscode-list-activeSelectionBackground:#e8e8e8;--vscode-list-activeSelectionForeground:#000000;--vscode-inputValidation-warningBackground:#f6f0d4;',
};

/** 画面用の見本の記録の置き場所（<リポジトリ>/tests/fixtures/showcase）。 */
export const SHOWCASE_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'tests', 'fixtures', 'showcase');

/** 画面用の見本の記録を置く場所（<リポジトリ>/tests/fixtures）。 */
export const FIXTURES_DIR = path.dirname(SHOWCASE_DIR);
/** 動いている見本（07_implement_2 が動いている）・その次の見本（08_test_2 が動き、差し戻しの回数が 1 増えている）・確認待ちの見本。 */
export const RUNNING_DIR = path.join(FIXTURES_DIR, 'showcase_running');
export const RUNNING_NEXT_DIR = path.join(FIXTURES_DIR, 'showcase_running_next');
export const WAITING_DIR = path.join(FIXTURES_DIR, 'showcase_waiting');

/**
 * パネルのページの種類：完了した見本・動いている見本（次の render を送る補助つき）・確認待ちの見本、
 * 実行の一覧の見本（runs）・archive を省く一覧の見本（runs-omitted）。
 */
export type PanelKind = 'done' | 'running' | 'waiting' | 'runs' | 'runs-omitted';

/** パネルのページ（ファイル名の頭とテーマ）。 */
export const PANEL_PAGES: readonly [string, Theme][] = [
  ['run-panel-light', 'light'],
  ['run-panel-dark', 'dark'],
  ['run-panel-running-light', 'light'],
  ['run-panel-running-dark', 'dark'],
  ['run-panel-waiting-light', 'light'],
  ['run-panel-waiting-dark', 'dark'],
  ['run-panel-runs-light', 'light'],
  ['run-panel-runs-dark', 'dark'],
  ['run-panel-runs-omitted-dark', 'dark'],
];

/** ページの名前から、どの見本のページかを決める。 */
export function panelKind(page: string): PanelKind {
  if (page.includes('-runs-omitted-')) return 'runs-omitted';
  if (page.includes('-runs-')) return 'runs';
  return page.includes('-running-') ? 'running' : page.includes('-waiting-') ? 'waiting' : 'done';
}

/** 記録の時刻（at・since）から sec 秒後を「今」にする時計。手元のずれは 0（見本の時刻はオフセットつきなので、手元に左右されない）。 */
export function previewClock(timeText: string, sec: number): ViewClock {
  return { nowMs: Date.parse(timeText) + sec * 1000, localOffsetMin: 0 };
}

/** 記録を拡張の本物の読み取りで読み、図の状態にする。表示の work_dir は 'docs/pipeline'（絶対パスを出さない）。clock は「今」。 */
export function readShowcaseView(workDirAbs: string, clock?: ViewClock): Promise<PipelineView> {
  return refreshView(createFsWorkDirSource(workDirAbs, 'docs/pipeline'), 'docs/pipeline', clock);
}

/** 動いている段の始まりの時刻（at）、無ければ確認待ちの待ち始め（since）。どちらも無ければ null。見本から「今」を決めるのに使う。 */
export async function startOfLiveness(workDirAbs: string): Promise<string | null> {
  const snapshot = await createFsWorkDirSource(workDirAbs, 'docs/pipeline').read();
  const logs = snapshot.stageLogs
    .map((l) => ({ name: parseStageLogName(l.fileName), log: parseStageLog(l.text) }))
    .filter((l) => l.name !== null && l.log.hasPrompt && !l.log.finished)
    .sort((a, b) => a.name!.seq - b.name!.seq);
  const running = logs.at(-1)?.log.startedAt ?? null;
  return running ?? parseRunRecord(snapshot.stateJson).pendingReview?.since ?? null;
}

/** 動いている・確認待ちの見本の図の状態。「今」は始まりの時刻から sec 秒後に固定する（ページを開いた時点からパネルが数え上げる）。 */
export async function readLiveView(workDirAbs: string, sec: number): Promise<PipelineView> {
  const base = await startOfLiveness(workDirAbs);
  return readShowcaseView(workDirAbs, base === null ? undefined : previewClock(base, sec));
}

/** 確認用ページの動き（脈打ち・点の流れ・点滅）を見るときの、始まりからの秒（動いている見本・確認待ちの見本）。 */
export const RUNNING_SEC = 83;
export const WAITING_SEC = 40;

/** 最初の <style nonce="preview"> の前に、テーマの色を決める <style> を入れる（作業台のページと同じ入れ方）。 */
export function withTheme(html: string, theme: Theme): string {
  const first = `<style nonce="${NONCE}">`;
  return html.replace(first, `<style nonce="${NONCE}">:root{${THEMES[theme]}}</style>${first}`);
}

/**
 * パネルの確認用ページ。VSCode の API の代わりに、何もしない acquireVsCodeApi を <body> の直後に入れる。
 * next を渡すと（動いている見本のページ）、その本体を render のメッセージで送る補助 window.__previewNext() も入れる
 * （戻る矢印の光りを画面で確かめるための、確認用ページだけの補助。nonce つき）。
 */
export function panelPreviewHtml(view: PipelineView, theme: Theme, next?: PipelineView): string {
  const stub = `<script nonce="${NONCE}">window.acquireVsCodeApi=()=>({postMessage(){}});</script>`;
  // 本体の HTML を文字として埋める。< は < にして、</script> などでページが切れないようにする
  const nextBody = next === undefined ? '' : JSON.stringify(renderViewBody(next)).replace(/</g, '\\u003c');
  const helper = next === undefined ? '' : `\n<script nonce="${NONCE}">window.__previewNext=()=>window.postMessage({type:'render',html:${nextBody}},'*');</script>`;
  return withTheme(renderPanelHtml(view, NONCE), theme).replace('<body>', `<body>\n${stub}`).replace('</body>', `${helper}\n</body>`);
}

// ---- 実行の一覧の見本（D0019）----------------------------------------------------------------
// 見本は4つの記録（tests/fixtures/）から、一時フォルダ（dest）の中に置き場所の木を組み立てる。tests/fixtures/ には何も足さない・書かない。
// 木は実物の形：主の checkout（dest/main）の .git はフォルダ、別の worktree の .git はファイルで、登録は .git/worktrees/<名前>/{gitdir,HEAD,commondir}。

type Patch = Record<string, unknown>;

/** 見本の開発フローの段ごとの受け持ち（record begin --agent で残る値の見本）。 */
const AGENTS: Readonly<Record<string, string>> = {
  requirements: 'pipe-in-analyst',
  design: 'pipe-in-analyst',
  red: 'pipe-in-tester',
  implement: 'pipe-in-coder',
  test: 'pipe-in-verifier',
};

const TIME_TEXT = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$/;

/** 記録の時刻の文字を ms ミリ秒ずらす（書かれ方 ― ずれの有無・小数 ― は変えない）。時刻でない文字はそのまま。 */
function shiftTime(text: unknown, ms: number): unknown {
  if (typeof text !== 'string') return text;
  const m = TIME_TEXT.exec(text);
  if (m === null) return text;
  const wall = Date.parse(`${m[1]}T${m[2]}Z`) + ms;
  return `${new Date(wall).toISOString().slice(0, 19)}${m[3] ?? ''}${m[4] ?? ''}`;
}

interface CopyOptions {
  /** 時刻（started_at・updated_at・pending_review.since・段のログの at）をまとめてずらすミリ秒。並びと「今」からの経過を決める */
  shiftMs?: number;
  /** セッション名と ID（見本の題） */
  name: string;
  sessionId: string;
  patch?: Patch;
}

/** 段のログ（logs/*.jsonl）の at をずらし、開発フローの Prompt 行に受け持ち（agent）を足す。 */
async function rewriteLogs(logsDir: string, shiftMs: number): Promise<void> {
  let names: string[];
  try {
    names = (await readdir(logsDir)).filter((n) => n.endsWith('.jsonl'));
  } catch {
    return;
  }
  for (const name of names) {
    const file = path.join(logsDir, name);
    const lines = (await readFile(file, 'utf8')).split('\n').filter((l) => l.trim() !== '');
    const out = lines.map((line) => {
      const obj = JSON.parse(line) as Record<string, unknown>;
      if ('at' in obj) obj.at = shiftTime(obj.at, shiftMs);
      if (obj._type === 'Prompt' && typeof obj.stage === 'string' && obj.stage in AGENTS) obj.agent = AGENTS[obj.stage];
      return JSON.stringify(obj);
    });
    await writeFile(file, `${out.join('\n')}\n`, 'utf8');
  }
}

/**
 * 見本の記録を dest に写し、時刻をまとめて動かし、名前・ID・受け持ちを足し、決まった項目だけ書き換える。
 * 4つの見本の時刻は同じ日に固まっているので、写しごとに動かして、動いている run は今の少し前に始まり、終わった run は数時間〜数日前になるようにする。
 */
async function copyRun(src: string, dest: string, options: CopyOptions): Promise<void> {
  const shiftMs = options.shiftMs ?? 0;
  await cp(src, dest, { recursive: true });
  const file = path.join(dest, 'state.json');
  const state = JSON.parse(await readFile(file, 'utf8')) as Record<string, unknown>;
  for (const key of ['started_at', 'updated_at']) state[key] = shiftTime(state[key], shiftMs);
  const pending = state.pending_review;
  if (pending !== null && typeof pending === 'object') {
    state.pending_review = { ...(pending as Record<string, unknown>), since: shiftTime((pending as Record<string, unknown>).since, shiftMs) };
  }
  if (Array.isArray(state.runs)) {
    state.runs = state.runs.map((entry: unknown) => {
      const run = entry as Record<string, unknown>;
      return typeof run.seq === 'number' && typeof run.stage === 'string' && run.stage in AGENTS ? { ...run, agent: AGENTS[run.stage] } : run;
    });
  }
  await writeFile(file, `${JSON.stringify({ ...state, name: options.name, session_id: options.sessionId, ...options.patch }, null, 2)}\n`, 'utf8');
  await rewriteLogs(path.join(dest, 'logs'), shiftMs);
}

/** 主の checkout の .git（フォルダ）。HEAD だけ置く。 */
async function writeMainGit(main: string): Promise<void> {
  await mkdir(path.join(main, '.git'), { recursive: true });
  await writeFile(path.join(main, '.git', 'HEAD'), 'ref: refs/heads/main\n', 'utf8');
}

/** 別の worktree 1つ（登録と根の .git ファイル）。作業フォルダ（docs/pipeline）の絶対パスを返す。 */
async function writeWorktree(dest: string, name: string, branch: string): Promise<string> {
  const root = path.join(dest, name);
  const reg = path.join(dest, 'main', '.git', 'worktrees', name);
  await mkdir(reg, { recursive: true });
  await mkdir(root, { recursive: true });
  await writeFile(path.join(reg, 'gitdir'), `${path.join(root, '.git')}\n`, 'utf8');
  await writeFile(path.join(reg, 'HEAD'), `ref: refs/heads/${branch}\n`, 'utf8');
  await writeFile(path.join(reg, 'commondir'), '../..\n', 'utf8');
  await writeFile(path.join(root, '.git'), `gitdir: ${reg}\n`, 'utf8');
  return path.join(root, 'docs', 'pipeline');
}

const pad2 = (n: number): string => String(n).padStart(2, '0');

/**
 * 実行の一覧の見本の木。ワークスペースは dest/main（返す workspace）。
 * いまの work_dir：確認待ちの開発フロー（直下）・動いている diagrams・合格の survey・archive/ の前の実行 2 つ（不合格・合格）。
 * 別の worktree：feat-export（確認待ちの spec-qa）・fix-login（動いている開発フロー）。
 */
export async function buildRunsTree(dest: string): Promise<{ workspace: string }> {
  const workspace = path.join(dest, 'main');
  const here = path.join(workspace, 'docs', 'pipeline');
  await writeMainGit(workspace);
  // 全体の「今」は、確認待ちの見本の待ち始めから WAITING_SEC 秒後（readRunsView を呼ぶ側の時計と同じ）
  const waitingSince = await startOfLiveness(WAITING_DIR);
  const runningAt = await startOfLiveness(RUNNING_DIR);
  const runningNextAt = await startOfLiveness(RUNNING_NEXT_DIR);
  if (waitingSince === null || runningAt === null || runningNextAt === null) throw new Error('見本の記録に、動いている段か待ち始めの時刻がありません');
  const now = Date.parse(waitingSince) + WAITING_SEC * 1000;
  const HOUR = 3_600_000;

  // いまの work_dir：確認待ち（そのまま）・動いている diagrams（今の 83 秒前に段が始まった）・合格の survey（3 時間前）・前の実行 2 つ（1 日前・2 日前）
  await copyRun(WAITING_DIR, here, { name: '仕様の QA を回す', sessionId: '7f3c9a21-4b6e-4d0a-9c1e-2a8b5d0e6f13' });
  await copyRun(RUNNING_DIR, path.join(here, 'diagrams'), {
    shiftMs: now - RUNNING_SEC * 1000 - Date.parse(runningAt),
    name: '設計図をそろえる',
    sessionId: '3a6f8e02-1d5b-4c97-a0e4-8b2c6d1f9a75',
    patch: { pipe: 'diagrams' },
  });
  await copyRun(SHOWCASE_DIR, path.join(here, 'survey'), {
    shiftMs: -3 * HOUR,
    name: 'アンケートを集計する',
    sessionId: 'c5b0e7a9-2f4d-4a61-9e3c-6d8f1b2a0c57',
    patch: { pipe: 'survey' },
  });
  await copyRun(SHOWCASE_DIR, path.join(here, 'archive', '20261016-090000'), {
    shiftMs: -24 * HOUR,
    name: 'CSV 出力（1 回目）',
    sessionId: '0d8a3c6f-7e1b-4b25-a9d0-4f6e2c8b1a93',
    patch: { final: 'TEST_FAILED' },
  });
  await copyRun(SHOWCASE_DIR, path.join(here, 'archive', '20261015-090000'), {
    shiftMs: -48 * HOUR,
    name: '一覧の並び替え',
    sessionId: '9e1f6b4d-3c8a-4f07-b5e2-1a7d9c3e0b28',
  });

  // 別の worktree：確認待ちの spec-qa（待ち始めが 33 秒あと）・動いている開発フロー（今の 20 秒前に段が始まった）
  const feat = await writeWorktree(dest, 'feat-export', 'feat/export-csv');
  await copyRun(WAITING_DIR, feat, {
    shiftMs: 33_000,
    name: 'CSV 出力を足す',
    sessionId: 'b21e07c4-9a3f-4f8d-8e52-71c0d3a9b6e4',
    patch: { pipe: 'spec-qa' },
  });
  const fix = await writeWorktree(dest, 'fix-login', 'fix/login');
  await copyRun(RUNNING_NEXT_DIR, fix, {
    shiftMs: now - 20_000 - Date.parse(runningNextAt),
    name: 'ログインの不具合を直す',
    sessionId: 'e9d4512b-6c7a-4e1f-b3d8-05a2f7c9e118',
  });
  return { workspace };
}

/** archive/ が 12 件ある見本の木（新しい方から 10 件を読み、2 件を省く）。archive の記録は state.json だけの写し。 */
export async function buildOmittedTree(dest: string): Promise<{ workspace: string }> {
  const workspace = path.join(dest, 'main');
  const here = path.join(workspace, 'docs', 'pipeline');
  await writeMainGit(workspace);
  await copyRun(SHOWCASE_DIR, here, { shiftMs: -3 * 3_600_000, name: 'アンケートを集計する', sessionId: 'c5b0e7a9-2f4d-4a61-9e3c-6d8f1b2a0c57' });
  const state = JSON.parse(await readFile(path.join(SHOWCASE_DIR, 'state.json'), 'utf8')) as Record<string, unknown>;
  for (let i = 1; i <= 12; i++) {
    const dir = path.join(here, 'archive', `202610${pad2(i)}-090000`);
    await mkdir(dir, { recursive: true });
    const patch = {
      name: `前の実行 ${i}`,
      session_id: `0d8a${pad2(i)}6f-7e1b-4b25-a9d0-4f6e2c8b1a93`,
      updated_at: `2026-10-${pad2(i)}T09:20:00`,
      ...(i % 3 === 0 ? { final: 'TEST_FAILED' } : {}),
    };
    await writeFile(path.join(dir, 'state.json'), `${JSON.stringify({ ...state, ...patch }, null, 2)}\n`, 'utf8');
  }
  return { workspace };
}

/** 一覧の見本の1行ぶん：行の目印・その行を選んだときの図・一覧（選んだ行つき）・初めに選ばれている行か。 */
export interface RunsPreviewEntry {
  key: string;
  view: PipelineView;
  listView: RunListView;
  selected: boolean;
}

/**
 * 拡張の本物の読み取りと組み立て（createFsRunsSource → loadRunList → chooseEntry → refreshView）をそのまま通して、行ごとの図を作る。
 * 見本のための別の組み立ては作らない。表示の work_dir は 'docs/pipeline'（一時フォルダの絶対パスを出さない）。
 */
export async function readRunsView(workspace: string, clock: ViewClock): Promise<RunsPreviewEntry[]> {
  const workDirAbs = path.join(workspace, 'docs', 'pipeline');
  const list = await loadRunList(createFsRunsSource(workspace, workDirAbs, 'docs/pipeline'), { showOthers: true, clock });
  const chosen = chooseEntry(list, null, { key: HERE, label: null, workDirAbs });
  const entries: RunsPreviewEntry[] = [];
  for (const entry of list.entries) {
    const view = await refreshView(createFsWorkDirSource(entry.dirAbs, 'docs/pipeline'), 'docs/pipeline', clock);
    entries.push({ key: entry.row.key, view, listView: toListView(list, entry.row.key, 'docs/pipeline'), selected: entry.row.key === chosen.key });
  }
  return entries;
}

/**
 * 一覧の見本のページ。VSCode の API の代わりの acquireVsCodeApi は、selectRun を受けたら、その行の本体（BODIES）を render で返す
 * （押す→図が切り替わる・aria-pressed が移る・タイマーが回る、までをブラウザで確かめられる）。nonce つきで <body> の直後に入れる。
 */
export function panelRunsPreviewHtml(entries: readonly RunsPreviewEntry[], theme: Theme): string {
  const initial = entries.find((e) => e.selected) ?? entries[0];
  if (initial === undefined) throw new Error('一覧の見本の行がありません');
  const bodies: Record<string, string> = {};
  for (const e of entries) bodies[e.key] = renderViewBody(e.view, e.listView);
  // 本体の HTML を文字として埋める。< は < にして、</script> などでページが切れないようにする
  const json = JSON.stringify(bodies).replace(/</g, '\\u003c');
  const stub =
    `<script nonce="${NONCE}">window.acquireVsCodeApi=(()=>{const BODIES=${json};` +
    `return()=>({postMessage(m){if(m&&m.type==='selectRun'&&typeof BODIES[m.id]==='string')window.postMessage({type:'render',html:BODIES[m.id]},'*')}})})();</script>`;
  return withTheme(renderPanelHtml(initial.view, NONCE, initial.listView), theme).replace('<body>', `<body>\n${stub}`);
}
