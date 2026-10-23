// 画面の確認用のページのうち、ページの中身を決める部分（副作用なし。out/ に書くのは preview.ts だけ）。
// テーマの色（--vscode-* の仮の値）と、「実行を見る」パネルのページの組み立てをここに置き、テストから import する。
// パネルのページは、画面用の見本の記録（tests/fixtures/showcase/）を、拡張の本物の記録の読み取り（infra）→
// 図の状態（app・domain）→ renderPanelHtml（view）で HTML にしたもの。CSP の <meta> はそのまま残し、
// 足す script タグ・style タグにはすべて nonce を付ける。
// 「止まっているかもしれない実行の印」（D0021）の見本も、ここで作る。tests/fixtures/ の見本は読むだけで書かない。
// 「成果物」タブの見本（D0025）も、ここで作る。長い Markdown などの見本の文章は artifactSamples.ts にある。
// ログと成果物の更新時刻（utimes）をそろえるのは、呼ぶ側が作った一時フォルダの中の写しだけ（拡張の src/ は更新時刻を読むだけ）。
import { cp, mkdir, readFile, readdir, rm, utimes, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { refreshView } from '../src/app/refreshView.ts';
import { chooseEntry, isPreviousRun, loadRunList, toListView } from '../src/app/runList.ts';
import { DEFAULT_STALE_AFTER_MINUTES } from '../src/app/staleness.ts';
import type { PipelineView, ViewClock } from '../src/domain/pipelineView.ts';
import { parseRunRecord } from '../src/domain/runRecord.ts';
import type { RunListView } from '../src/domain/runList.ts';
import { HERE, makeRunKey } from '../src/domain/runs.ts';
import { parseStageLog, parseStageLogName } from '../src/domain/stageLog.ts';
import { createFsRunsSource, createFsWorkDirSource } from '../src/infra/fsWorkDirSource.ts';
import { renderPanelHtml, renderViewBody } from '../src/view/panelHtml.ts';
import { PIPE_STAGES, hostileSample, implementationSample, longDesignSample, pipeMemoSample, pipeSummarySample } from './artifactSamples.ts';

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
 * 実行の一覧の見本（runs）・archive を省く一覧の見本（runs-omitted）、
 * 更新なしの印の見本（stale）・目安の数秒手前から印が付く見本（stale-soon。更新後の本体を送る補助つき）、
 * 「成果物」タブの見本（artifacts。実行の一覧つき。更新後の本体を送る補助と、送ったメッセージを貯める window.__posted つき）。
 */
export type PanelKind = 'done' | 'running' | 'waiting' | 'runs' | 'runs-omitted' | 'stale' | 'stale-soon' | 'artifacts';

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
  ['run-panel-stale-light', 'light'],
  ['run-panel-stale-dark', 'dark'],
  ['run-panel-stale-soon-dark', 'dark'],
  ['run-panel-artifacts-light', 'light'],
  ['run-panel-artifacts-dark', 'dark'],
];

/** ページの名前から、どの見本のページかを決める。 */
export function panelKind(page: string): PanelKind {
  if (page.includes('-artifacts-')) return 'artifacts';
  if (page.includes('-stale-soon-')) return 'stale-soon';
  if (page.includes('-stale-')) return 'stale';
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

/**
 * 動いている・確認待ちの見本を、一時フォルダ（dest）に写して、見本の「今」にそろえて読む。
 * 見本の記録（tests/fixtures/）のログの更新時刻は、チェックアウトした時刻しだいで、見本の「今」とずれる。
 * そのまま読むと「止まっているかも」の印の元（最後の更新からの秒）が、見るたびに変わってしまうので、
 * 写しのログの更新時刻を見本の「今」にそろえる（元の見本は書き換えない）。時刻の読めない見本は、そろえずにそのまま読む。
 */
export async function readLiveViewAligned(src: string, sec: number, dest: string): Promise<PipelineView> {
  const base = await startOfLiveness(src);
  const clock = base === null ? undefined : previewClock(base, sec);
  const copied = path.join(dest, path.basename(src));
  if (clock === undefined) await cp(src, copied, { recursive: true });
  else await copySample(src, copied, clock.nowMs);
  return readShowcaseView(copied, clock);
}

/** 確認用ページの動き（脈打ち・点の流れ・点滅）を見るときの、始まりからの秒（動いている見本・確認待ちの見本）。 */
export const RUNNING_SEC = 83;
export const WAITING_SEC = 40;

// ---- 止まっているかもしれない実行の印の見本（D0021）-------------------------------------------
/** 確認用ページの目安（秒）。拡張の既定（DEFAULT_STALE_AFTER_MINUTES ＝ 10 分）と同じ数から作る。確認用のページは、既存のものも含めてこの目安で組み立てる。 */
export const STALE_AFTER_SEC = DEFAULT_STALE_AFTER_MINUTES * 60;
/** 更新なしの見本で、目安を何秒越えているか（diagrams）。 */
const STALE_OVER_SEC = 12;
/** 更新なしの見本で、目安を何秒越えているか（別の worktree の fix-login）。 */
const STALE_OTHER_OVER_SEC = 40;
/** 目安の数秒手前の見本で、印が付くまでの秒（diagrams）。 */
const STALE_SOON_SEC = 5;

/** dir/logs の段のログ（*.jsonl）の更新時刻を atMs にそろえる（整数の秒に置く。粗い時刻のファイルシステムでも同じ値になる）。logs/ の外は変えない。 */
export async function setLogTimes(dir: string, atMs: number): Promise<void> {
  const logsDir = path.join(dir, 'logs');
  let names: string[];
  try {
    names = (await readdir(logsDir)).filter((n) => n.endsWith('.jsonl'));
  } catch {
    return;
  }
  const at = new Date(Math.floor(atMs / 1000) * 1000);
  for (const name of names) await utimes(path.join(logsDir, name), at, at);
}

/** 成果物の更新時刻の間隔：名前順に 1 つずつ、これだけ古くする。 */
const ARTIFACT_STEP_MS = 3 * 60_000;

/**
 * dir 直下の成果物（*.md・*.txt）の更新時刻を、名前順に「atMs − 3 分、atMs − 6 分、…」の固定の値にそろえる（整数の秒）。
 * 0 番目も atMs そのものにはしない（確認待ちの見本の updated_at は見本の「今」より後なので、「今」を超えないようにする）。
 * 写しのままだと、更新時刻は写した時刻になり、ビルドのたびに変わり、見本の「今」より先の日時も出る。
 * state.json・logs/・サブフォルダの中は変えない。見本の文章を置いたあとで呼ぶ（書き直すと更新時刻が変わる）。
 */
export async function setArtifactTimes(dir: string, atMs: number): Promise<void> {
  let names: string[];
  try {
    names = (await readdir(dir, { withFileTypes: true }))
      .filter((e) => e.isFile() && /\.(md|txt)$/.test(e.name))
      .map((e) => e.name)
      .sort();
  } catch {
    return;
  }
  const base = Math.floor(atMs / 1000) * 1000;
  for (const [i, name] of names.entries()) {
    const at = new Date(base - (i + 1) * ARTIFACT_STEP_MS);
    await utimes(path.join(dir, name), at, at);
  }
}

/**
 * 見本 src を dest に写し、ログの更新時刻を「nowMs − quietAgoSec 秒」に、成果物の更新時刻を nowMs から決めた固定の値（setArtifactTimes）にする。
 * nowMs は見本の組み立てに使う時計の「今」（本物の今ではない）。
 * quietAgoSec の既定は 0（最後の更新が「今」）。成果物の時刻は quietAgoSec と関係しない。dest は呼ぶ側が作った一時フォルダの中。src は変えない。
 */
export async function copySample(src: string, dest: string, nowMs: number, quietAgoSec = 0): Promise<void> {
  await cp(src, dest, { recursive: true });
  await setLogTimes(dest, nowMs - quietAgoSec * 1000);
  await setArtifactTimes(dest, nowMs);
}

/** 最初の <style nonce="preview"> の前に、テーマの色を決める <style> を入れる（作業台のページと同じ入れ方）。 */
export function withTheme(html: string, theme: Theme): string {
  const first = `<style nonce="${NONCE}">`;
  return html.replace(first, `<style nonce="${NONCE}">:root{${THEMES[theme]}}</style>${first}`);
}

/**
 * パネルの確認用ページ。VSCode の API の代わりに、何もしない acquireVsCodeApi を <body> の直後に入れる。
 * next を渡すと（動いている見本のページ）、その本体を render のメッセージで送る補助 window.__previewNext() も入れる
 * （戻る矢印の光りを画面で確かめるための、確認用ページだけの補助。nonce つき）。
 * staleAfterSec は「止まっているかも」の目安の秒（初めの本体にも次の本体にも同じ目安を渡す）。渡さなければ印は出ない（今までと同じ）。
 */
export function panelPreviewHtml(view: PipelineView, theme: Theme, next?: PipelineView, staleAfterSec: number | null = null): string {
  const stub = `<script nonce="${NONCE}">window.acquireVsCodeApi=()=>({postMessage(){}});</script>`;
  const helper = next === undefined ? '' : previewNextScript(renderViewBody(next, undefined, staleAfterSec));
  // 関数で置き換える（埋める文字に本体の HTML が入る。$ を置き換えの特別な書き方と取り違えない）
  return withTheme(renderPanelHtml(view, NONCE, undefined, staleAfterSec), theme)
    .replace('<body>', () => `<body>\n${stub}`)
    .replace('</body>', () => `${helper}\n</body>`);
}

/**
 * 次の本体を render のメッセージで送る補助 window.__previewNext() の script（確認用ページだけの補助。nonce つき。先頭に改行を置く）。
 * 本体の HTML を文字として埋める。< は < にして、</script> などでページが切れないようにする。
 */
function previewNextScript(body: string): string {
  const json = JSON.stringify(body).replace(/</g, '\\u003c');
  return `\n<script nonce="${NONCE}">window.__previewNext=()=>window.postMessage({type:'render',html:${json}},'*');</script>`;
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

/** 記録の時刻の文字を、書かれた日時のまま（ずれは見ずに）UTC のミリ秒にする。時刻でない文字は null。 */
function wallMs(text: unknown): number | null {
  const m = typeof text === 'string' ? TIME_TEXT.exec(text) : null;
  return m === null ? null : Date.parse(`${m[1]}T${m[2]}Z`);
}

interface CopyOptions {
  /** 時刻（started_at・updated_at・pending_review.since・段のログの at）をまとめてずらすミリ秒。並びと「今」からの経過を決める */
  shiftMs?: number;
  /** セッション名と ID（見本の題） */
  name: string;
  sessionId: string;
  patch?: Patch;
  /**
   * 成果物の更新時刻の基準（UTC のミリ秒。setArtifactTimes に渡す）。動いている run は「今」を渡す。
   * 省くと、ずらしたあとの updated_at（読めない記録では、成果物の更新時刻は変えない）。
   */
  artifactsAtMs?: number;
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
 * 成果物の更新時刻も、写した時刻のままにせず、基準（options.artifactsAtMs か updated_at）から決めた固定の値にそろえる。
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
  const artifactsAtMs = options.artifactsAtMs ?? wallMs(state.updated_at);
  if (artifactsAtMs !== null) await setArtifactTimes(dest, artifactsAtMs);
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

/** buildRunsTree の options：動いている 2 つの run の、最後の更新が「今」の何秒前か（既定は 0 ＝「今」）。 */
export interface RunsTreeOptions {
  diagramsQuietSec?: number;
  fixLoginQuietSec?: number;
}
/** 別の worktree の fix-login の段が始まったのが「今」の何秒前か（既定。diagrams は RUNNING_SEC）。 */
const FIX_LOGIN_START_SEC = 20;
/** 段の始まりを、最後の更新より何秒前にするか（更新なしの見本で、経過が更新なしの時間以上になる余裕）。 */
const DIAGRAMS_START_MARGIN_SEC = 60;
const FIX_LOGIN_START_MARGIN_SEC = 20;

/**
 * 実行の一覧の見本の木。ワークスペースは dest/main（返す workspace）。
 * いまの work_dir：確認待ちの開発フロー（直下）・動いている diagrams・合格の survey・archive/ の前の実行 2 つ（不合格・合格）。
 * 別の worktree：feat-export（確認待ちの spec-qa）・fix-login（動いている開発フロー）。
 * 動いている 2 つ（diagrams・fix-login）は、ログの更新時刻を「今 − 秒」にそろえる（options。既定は 0 ＝「今」。いつ作っても印は出ない）。
 * 成果物の更新時刻は、どの run も固定の値にそろう（動いている 2 つは「今」から、ほかは updated_at から。止まっているかもの印とは関係しない）。
 * 段の始まりも、経過が更新なしの時間以上になるよう古くする（更新時刻が段の始まりより前の見本にならない。既定では今までと同じ値）。
 */
export async function buildRunsTree(dest: string, options: RunsTreeOptions = {}): Promise<{ workspace: string }> {
  const diagramsQuietSec = options.diagramsQuietSec ?? 0;
  const fixLoginQuietSec = options.fixLoginQuietSec ?? 0;
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

  // いまの work_dir：確認待ち（そのまま）・動いている diagrams（今の 83 秒前に段が始まった。更新なしの見本では、更新なしの時間より古い）・
  // 合格の survey（3 時間前）・前の実行 2 つ（1 日前・2 日前）
  await copyRun(WAITING_DIR, here, { name: '仕様の QA を回す', sessionId: '7f3c9a21-4b6e-4d0a-9c1e-2a8b5d0e6f13' });
  const diagrams = path.join(here, 'diagrams');
  await copyRun(RUNNING_DIR, diagrams, {
    shiftMs: now - Math.max(RUNNING_SEC, diagramsQuietSec + DIAGRAMS_START_MARGIN_SEC) * 1000 - Date.parse(runningAt),
    name: '設計図をそろえる',
    sessionId: '3a6f8e02-1d5b-4c97-a0e4-8b2c6d1f9a75',
    patch: { pipe: 'diagrams' },
    artifactsAtMs: now,
  });
  await setLogTimes(diagrams, now - diagramsQuietSec * 1000);
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

  // 別の worktree：確認待ちの spec-qa（待ち始めが 33 秒あと）・動いている開発フロー（今の 20 秒前に段が始まった。更新なしの見本では、更新なしの時間より古い）
  const feat = await writeWorktree(dest, 'feat-export', 'feat/export-csv');
  await copyRun(WAITING_DIR, feat, {
    shiftMs: 33_000,
    name: 'CSV 出力を足す',
    sessionId: 'b21e07c4-9a3f-4f8d-8e52-71c0d3a9b6e4',
    patch: { pipe: 'spec-qa' },
  });
  const fix = await writeWorktree(dest, 'fix-login', 'fix/login');
  await copyRun(RUNNING_NEXT_DIR, fix, {
    shiftMs: now - Math.max(FIX_LOGIN_START_SEC, fixLoginQuietSec + FIX_LOGIN_START_MARGIN_SEC) * 1000 - Date.parse(runningNextAt),
    name: 'ログインの不具合を直す',
    sessionId: 'e9d4512b-6c7a-4e1f-b3d8-05a2f7c9e118',
    artifactsAtMs: now,
  });
  await setLogTimes(fix, now - fixLoginQuietSec * 1000);
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
 * options.selected で、初めに選ぶ行（行の目印）を決められる（無ければ、本番の既定の選び方）。
 * 各行の写しは、本番の入口と同じく、前の実行（archive/）かどうかを伝えて読む（前の実行は印の対象にならない）。
 */
export async function readRunsView(workspace: string, clock: ViewClock, options: { selected?: string | null } = {}): Promise<RunsPreviewEntry[]> {
  const workDirAbs = path.join(workspace, 'docs', 'pipeline');
  const list = await loadRunList(createFsRunsSource(workspace, workDirAbs, 'docs/pipeline'), { showOthers: true, clock });
  const chosen = chooseEntry(list, options.selected ?? null, { key: HERE, label: null, workDirAbs });
  const entries: RunsPreviewEntry[] = [];
  for (const entry of list.entries) {
    const source = createFsWorkDirSource(entry.dirAbs, 'docs/pipeline', { previous: isPreviousRun(list, entry.row.key) });
    const view = await refreshView(source, 'docs/pipeline', clock);
    entries.push({ key: entry.row.key, view, listView: toListView(list, entry.row.key, 'docs/pipeline'), selected: entry.row.key === chosen.key });
  }
  return entries;
}

/**
 * 一覧の見本のページ。VSCode の API の代わりの acquireVsCodeApi は、selectRun を受けたら、その行の本体（BODIES）を render で返す
 * （押す→図が切り替わる・aria-pressed が移る・タイマーが回る、までをブラウザで確かめられる）。nonce つきで <body> の直後に入れる。
 * options.staleAfterSec は「止まっているかも」の目安の秒（各行の本体と初めの本体に渡す。渡さなければ印は出ない）。
 * options.next を渡すと、その行の本体を render で送る補助 window.__previewNext() も入れる（更新後の見本。nonce つき）。
 * options.recordPosted が true のときだけ、送られたメッセージの type を window.__posted に貯める（画面の確認で、行を押しても余計な通信が増えないことを見る。
 * selectRun の返信は今のまま）。渡さない・false のときの置き換えは、今までと同じ文字。
 * options を渡さない呼び方（今までの 3 つ目の引数）は、どの項目も無いので今までと同じ。
 */
export function panelRunsPreviewHtml(
  entries: readonly RunsPreviewEntry[],
  theme: Theme,
  options: { staleAfterSec?: number | null; next?: RunsPreviewEntry; recordPosted?: boolean } = {},
): string {
  const staleAfterSec = options.staleAfterSec ?? null;
  const record = options.recordPosted === true;
  const initial = entries.find((e) => e.selected) ?? entries[0];
  if (initial === undefined) throw new Error('一覧の見本の行がありません');
  const bodies: Record<string, string> = {};
  for (const e of entries) bodies[e.key] = renderViewBody(e.view, e.listView, staleAfterSec);
  // 本体の HTML を文字として埋める。< は < にして、</script> などでページが切れないようにする
  const json = JSON.stringify(bodies).replace(/</g, '\\u003c');
  const stub =
    `<script nonce="${NONCE}">window.acquireVsCodeApi=(()=>{const BODIES=${json};${record ? 'window.__posted=[];' : ''}` +
    `return()=>({postMessage(m){${record ? "if(m&&typeof m.type==='string')window.__posted.push(m.type);" : ''}` +
    `if(m&&m.type==='selectRun'&&typeof BODIES[m.id]==='string')window.postMessage({type:'render',html:BODIES[m.id]},'*')}})})();</script>`;
  // 関数で置き換える（埋める文字に本体の HTML が入る。$ を置き換えの特別な書き方と取り違えない）
  const page = withTheme(renderPanelHtml(initial.view, NONCE, initial.listView, staleAfterSec), theme).replace('<body>', () => `<body>\n${stub}`);
  const next = options.next;
  if (next === undefined) return page;
  const helper = previewNextScript(renderViewBody(next.view, next.listView, staleAfterSec));
  return page.replace('</body>', () => `${helper}\n</body>`);
}

/**
 * 更新なしの印の見本のページ（D0021）。木を dest の中に組み立て、本番と同じ読み取りで読み、目安 STALE_AFTER_SEC で一覧のページにする。
 * stale：diagrams は目安を 12 秒、fix-login は 40 秒越えている（6 つの面すべてに印が出る。初めに選ぶのは diagrams）。
 * stale-soon：diagrams は目安の 5 秒手前（5 秒待つと印が付く）、fix-login は今。window.__previewNext() で、
 * diagrams の更新時刻を「今」にした本体を送ると、印が全部消える（そのために、dest/next にもう 1 つ木を組み立てる）。
 */
export async function staleRunsPageHtml(dest: string, kind: 'stale' | 'stale-soon', theme: Theme): Promise<string> {
  const since = await startOfLiveness(WAITING_DIR);
  if (since === null) throw new Error('確認待ちの見本に待ち始めの時刻がありません');
  const clock = previewClock(since, WAITING_SEC);
  const diagrams = makeRunKey(HERE, 'diagrams');
  const quiet: RunsTreeOptions =
    kind === 'stale'
      ? { diagramsQuietSec: STALE_AFTER_SEC + STALE_OVER_SEC, fixLoginQuietSec: STALE_AFTER_SEC + STALE_OTHER_OVER_SEC }
      : { diagramsQuietSec: STALE_AFTER_SEC - STALE_SOON_SEC, fixLoginQuietSec: 0 };
  const entries = await readRunsView((await buildRunsTree(dest, quiet)).workspace, clock, { selected: diagrams });
  if (kind === 'stale') return panelRunsPreviewHtml(entries, theme, { staleAfterSec: STALE_AFTER_SEC });
  const updated = await readRunsView((await buildRunsTree(path.join(dest, 'next'), { diagramsQuietSec: 0, fixLoginQuietSec: 0 })).workspace, clock, { selected: diagrams });
  const next = updated.find((e) => e.key === diagrams);
  if (next === undefined) throw new Error('更新後の見本に diagrams の行がありません');
  return panelRunsPreviewHtml(entries, theme, { staleAfterSec: STALE_AFTER_SEC, next });
}

// ---- 「成果物」タブの見本（D0025）---------------------------------------------------------------
// 実行は 2 つ。(a) 動いている開発フロー（直下。実装が動いていて、既定の選びは 04_implementation.md）と、
// (b) 12 個の成果物を持つ終わったパイプ（既定の選びは最後のまとめ）。見本の文章は artifactSamples.ts。
// 木は呼ぶ側が作った一時フォルダ（dest）の中だけに作る。tests/fixtures/ の見本は写すだけで書かない。

/** 成果物の見本の木の種類：current ＝ 今の見本、next ＝ 更新後の見本（(a) は検証が動き、実装の記録に 1 段落増える）。 */
export type ArtifactsVariant = 'current' | 'next';

/** (b) のパイプのフォルダ名。 */
const SURVEY_PIPE = 'survey-report';
/** 更新後の見本で、(a) の検証の段が始まってから「今」までの秒（動いている見本の次の見本と同じ）。 */
const ARTIFACTS_NEXT_SEC = 5;
/** (b) の終わった記録の時刻を、何時間前にするか。 */
const SURVEY_AGO_HOURS = 3;

/** dir に、名前と中身の組を書く（置き換える）。 */
async function writeFiles(dir: string, files: Readonly<Record<string, string>>): Promise<void> {
  for (const [name, text] of Object.entries(files)) await writeFile(path.join(dir, name), text, 'utf8');
}

/**
 * 「成果物」タブの見本の木。ワークスペースは dest/main（返す workspace）。
 * (a) 直下は、動いている開発フロー（showcase_running を写す。variant が next なら showcase_running_next で、検証が動く）。
 * 02_design.md（上限を超える日本語）・03_red_tests.md（外から来た文字）・04_implementation.md（長い Markdown）は見本の文章に替える。
 * 99_summary.md は無い（「まだない」）。ログの更新時刻は「今」（止まっているかもの印は出ない）。
 * (b) パイプ survey-report は、依頼メモ・10 段の成果物・まとめの 12 個（名前の特別な文字・.txt・広い表・空白の無い長い名前・長い段の表示名を含む）。
 * 成果物の更新時刻は、文章を置いたあとで setArtifactTimes にそろえる。「今」は確認待ちの見本の待ち始めから WAITING_SEC 秒後。
 */
export async function buildArtifactsTree(dest: string, variant: ArtifactsVariant): Promise<{ workspace: string }> {
  const workspace = path.join(dest, 'main');
  const here = path.join(workspace, 'docs', 'pipeline');
  await writeMainGit(workspace);
  const waitingSince = await startOfLiveness(WAITING_DIR);
  const src = variant === 'next' ? RUNNING_NEXT_DIR : RUNNING_DIR;
  const startedAt = await startOfLiveness(src);
  if (waitingSince === null || startedAt === null) throw new Error('見本の記録に、動いている段か待ち始めの時刻がありません');
  const now = Date.parse(waitingSince) + WAITING_SEC * 1000;

  // (a) 動いている開発フロー：段の始まりが「今」の RUNNING_SEC 秒前（次の見本は ARTIFACTS_NEXT_SEC 秒前）
  await copyRun(src, here, {
    shiftMs: now - (variant === 'next' ? ARTIFACTS_NEXT_SEC : RUNNING_SEC) * 1000 - Date.parse(startedAt),
    name: 'ユーザー一覧に CSV 出力ボタンを足す',
    sessionId: '5d2b8f10-6a4c-4e39-8c71-0b9e3a7d2f64',
    artifactsAtMs: now,
  });
  await setLogTimes(here, now);
  await writeFiles(here, {
    '02_design.md': longDesignSample(),
    '03_red_tests.md': hostileSample(),
    '04_implementation.md': implementationSample(variant === 'next'),
  });
  await setArtifactTimes(here, now);

  // (b) 12 個の成果物を持つ終わったパイプ：写した見本の成果物（段の名前が違う）は消して、見本の文章に替える
  const survey = path.join(here, SURVEY_PIPE);
  const finishedAt = now - SURVEY_AGO_HOURS * 3_600_000;
  await copyRun(SHOWCASE_DIR, survey, {
    shiftMs: -SURVEY_AGO_HOURS * 3_600_000,
    name: '調査レポートをまとめる',
    sessionId: 'a1c4e7b9-3d28-4f56-9b0a-6e2d8c1f7a35',
    patch: { pipe: SURVEY_PIPE, stages: PIPE_STAGES.map((s) => ({ name: s.name, label: s.label, output: s.output, review: false })) },
    artifactsAtMs: finishedAt,
  });
  for (const name of await readdir(survey)) if (name.endsWith('.md')) await rm(path.join(survey, name));
  await writeFiles(survey, {
    '00_input.md': pipeMemoSample(),
    ...Object.fromEntries(PIPE_STAGES.map((s) => [s.output, s.text])),
    '99_summary.md': pipeSummarySample(),
  });
  await setArtifactTimes(survey, finishedAt);
  return { workspace };
}

/**
 * 「成果物」タブの確認用ページ。木を dest の中に組み立て、本番と同じ読み取りで読み、目安 STALE_AFTER_SEC で一覧のページにする。
 * 初めに見るのは (a)。window.__previewNext() は (a) の更新後の本体を送る（既定の行が検証の成果物に移り、実装の記録が 1 段落増える。
 * そのために dest/next にもう 1 つ木を組み立てる。実行の一覧が変わらないよう、(b) も同じに作る）。
 * window.__posted に、パネルが送ったメッセージの type が貯まる（行を押しても余計な通信が増えないことを見る）。
 */
export async function artifactsPageHtml(dest: string, theme: Theme): Promise<string> {
  const since = await startOfLiveness(WAITING_DIR);
  if (since === null) throw new Error('確認待ちの見本に待ち始めの時刻がありません');
  const clock = previewClock(since, WAITING_SEC);
  const here = makeRunKey(HERE, '');
  const entries = await readRunsView((await buildArtifactsTree(dest, 'current')).workspace, clock, { selected: here });
  const updated = await readRunsView((await buildArtifactsTree(path.join(dest, 'next'), 'next')).workspace, clock, { selected: here });
  const next = updated.find((e) => e.key === here);
  if (next === undefined) throw new Error('更新後の見本に開発フローの行がありません');
  return panelRunsPreviewHtml(entries, theme, { staleAfterSec: STALE_AFTER_SEC, recordPosted: true, next });
}
