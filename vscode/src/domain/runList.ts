// 実行の一覧の行：記録の写しから1行を組み立てる・状態・並び・省く件数・覚えた値の検め。純粋（ファイル・時計・vscode に触れない）。
// 行の状態と今の段は、同じ記録から作った図の帯・ステータスバーと食い違わないよう、buildPipelineView の結果から決める。
import { isJsonObject } from './json.ts';
import { buildPipelineView } from './pipelineView.ts';
import type { PipelineView, ViewClock } from './pipelineView.ts';
import { parseRunRecord } from './runRecord.ts';
import type { RunRecord, StageRun } from './runRecord.ts';
import { ROOT_RUN_ID, isArchiveId, makeRunKey, parseRunKey } from './runs.ts';
import type { PlaceKey, RunKey } from './runs.ts';
import { nameFromMemo } from './sessionName.ts';
import { elapsedSec, isTimestampText, parseInstant } from './timestamp.ts';

/** 確認待ち・動いている・待ち・終わった。待ち（idle）は final も確認待ちも動いているログも無い run（段の合間・記録なし）。 */
export type RunState = 'waiting' | 'running' | 'idle' | 'done';

export interface RunRow {
  key: RunKey;
  /** セッション名：state.json の name → 00_input.md の最初の行 → パイプ名／開発フロー */
  session: string;
  /** パイプ名／開発フロー */
  pipe: string;
  /** いまの checkout・別の worktree のブランチ名か短い ID。git の外は null（項目ごと省く） */
  branch: string | null;
  /** 別の worktree の run */
  other: boolean;
  /** archive/ の run */
  previous: boolean;
  /** 今の段の表示名。読めなければ '—' */
  stage: string;
  state: RunState;
  /** final の言葉（合格…）。知らない文字はそのまま。終わった以外と、final の無い終わった行は null */
  result: string | null;
  /** セッション ID の全部：state.json の session_id → seq が最大の段の session_id。無ければ null（行は先頭 8 文字、詳細は全部） */
  sessionId: string | null;
  /** '$0.123'。読めなければ '—' */
  costText: string;
  /** '10/17 10:05'。読めなければ '—' */
  updatedText: string;
  /** '10/17'。読めなければ '—' */
  updatedDate: string;
  /** 並び用。読めなければ null */
  updatedMs: number | null;
  /** 全体の経過。started_at が読めるとき。動いている行だけ live（数え上げる）。読めなければ null */
  elapsed: { seconds: number; live: boolean } | null;
  /** 確認待ちだけ（待ち始めからの秒）。since が読めなければ null */
  waitingSec: number | null;
}

export interface RunListView {
  rows: RunRow[];
  selected: RunKey;
  /** archive を省いた数（場所ごと。place は別の worktree のときだけ名前、いまの work_dir は null） */
  omitted: { place: string | null; count: number }[];
  /** 省いた別の worktree の数 */
  omittedWorktrees: number;
  /** 上のバーに出す作業フォルダ（設定の値のまま） */
  workDir: string;
}

/** archive/ の run を、場所ごとに新しい方から読む件数 */
export const ARCHIVE_LIMIT = 10;
/** 別の worktree を、更新の新しい方から読む個数 */
export const WORKTREE_LIMIT = 8;

const DASH = '—';
const DEV_LABEL = '開発フロー';

/** 本体の終了の名前（state.json の final）→ 短い言葉。ステータスバーもここから読む。 */
export const FINAL_WORDS: Readonly<Record<string, string>> = {
  PASSED: '合格',
  TEST_FAILED: '不合格',
  STOPPED_BY_HUMAN: '中止',
  STAGE_ERROR: '段が失敗',
  BLOCKED: '実行できず',
};

/** 結果の言葉。知らない文字はそのまま。 */
export function finalWord(final: string): string {
  return Object.hasOwn(FINAL_WORDS, final) ? FINAL_WORDS[final]! : final;
}

export interface SummarizeInput {
  key: RunKey;
  /** 直下は ''、パイプはフォルダ名、archive は archive/<日時> */
  id: string;
  /** ブランチ名か短い ID。git の外は null */
  branch: string | null;
  /** 別の worktree の run */
  other: boolean;
  /** 00_input.md の先頭（name が無い記録のときだけ読む）。読めなければ null */
  memoHead: string | null;
  previous: boolean;
  stateJson: string | null;
  stageLogs: { fileName: string; text: string }[];
}

/** 生の JSON のオブジェクト。壊れていれば空（parseRunRecord は欠けを 0 にするので、欠けと 0 を分けるために生を読む）。 */
function rawState(stateJson: string | null): Record<string, unknown> {
  if (stateJson === null) return {};
  try {
    const data: unknown = JSON.parse(stateJson);
    return isJsonObject(data) ? data : {};
  } catch {
    return {};
  }
}

function nameOf(raw: Record<string, unknown>, id: string): string {
  const pipe = typeof raw.pipe === 'string' && raw.pipe !== '' ? raw.pipe : null;
  if (pipe !== null && pipe !== 'dev') return pipe;
  return id === ROOT_RUN_ID || isArchiveId(id) || pipe === 'dev' ? DEV_LABEL : id;
}

/** 記録の時刻の文字から、書かれたままの壁時計の MM/DD HH:mm を作る。読めなければ「—」。 */
export function formatStamp(text: string): string {
  if (!isTimestampText(text)) return DASH;
  return `${text.slice(5, 7)}/${text.slice(8, 10)} ${text.slice(11, 13)}:${text.slice(14, 16)}`;
}

function stageName(view: PipelineView, stage: string): string {
  return view.stageLabels[stage] ?? stage;
}

/** 通し番号が最大の段の実行。無ければ null。 */
function lastStageRun(record: RunRecord): StageRun | null {
  let last: StageRun | null = null;
  for (const run of record.stageRuns) {
    if (last === null || run.seq > last.seq) last = run;
  }
  return last;
}

/** 通し番号が最大の段の表示名。無ければ「—」。 */
function lastStageLabel(view: PipelineView, record: RunRecord): string {
  const last = lastStageRun(record);
  return last === null ? DASH : stageName(view, last.stage);
}

/** 全体の経過。動いている行は「今」まで数え上げる（live）、ほかは updated_at までの固定。読めなければ null。 */
function elapsedOf(record: RunRecord, state: RunState, clock: ViewClock): RunRow['elapsed'] {
  const from = record.startedAt === null ? null : parseInstant(record.startedAt, clock.localOffsetMin);
  if (from === null) return null;
  if (state === 'running') return { seconds: elapsedSec(from, clock.nowMs), live: true };
  const to = record.updatedAt === null ? null : parseInstant(record.updatedAt, clock.localOffsetMin);
  return to === null ? null : { seconds: elapsedSec(from, to), live: false };
}

/** 状態の言葉：確認待ち／動いている／待ち。終わった行は結果の言葉（結果が無ければ「終わった」）。 */
export function stateWord(row: Pick<RunRow, 'state' | 'result'>): string {
  if (row.state === 'waiting') return '確認待ち';
  if (row.state === 'running') return '動いている';
  if (row.state === 'idle') return '待ち';
  return row.result ?? '終わった';
}

/** 状態のタブの件数。待ち（idle）は「動いている」に数える。絞り込みには関わらない。 */
export function countStates(rows: readonly Pick<RunRow, 'state'>[]): { all: number; waiting: number; running: number; done: number } {
  const counts = { all: rows.length, waiting: 0, running: 0, done: 0 };
  for (const r of rows) {
    if (r.state === 'waiting') counts.waiting += 1;
    else if (r.state === 'done') counts.done += 1;
    else counts.running += 1;
  }
  return counts;
}

/** 記録の写し1つから1行を作る。archive の行（previous）はログを読まず、final が無くても「終わった」にする。壊れた記録でも例外を投げない。 */
export function summarizeRun(input: SummarizeInput, clock: ViewClock): RunRow {
  const raw = rawState(input.stateJson);
  const record = parseRunRecord(input.stateJson);
  const stageLogs = input.previous ? [] : input.stageLogs;
  const view = buildPipelineView({ workDir: '', stateJson: input.stateJson, stageLogs, artifacts: {} }, clock);

  // 判定の順は図の帯・ステータスバーと同じ：final → 動いている → 確認待ち → それ以外
  let state: RunState;
  let stage: string;
  const source = view.terminal.source;
  if (view.final !== null || input.previous) {
    state = 'done';
    stage = lastStageLabel(view, record);
  } else if (view.runningStage !== null && source !== null) {
    state = 'running';
    stage = `${stageName(view, source.stage)}${source.attempt === null ? '' : `（${source.attempt} 回目）`}`;
  } else if (view.pendingReview !== null) {
    state = 'waiting';
    stage = view.pendingReview.label;
  } else {
    state = 'idle';
    stage = lastStageLabel(view, record);
  }

  const updated = typeof raw.updated_at === 'string' ? raw.updated_at : null;
  const updatedText = updated === null ? DASH : formatStamp(updated);
  const waitingNode = state === 'waiting' ? view.nodes.find((n) => typeof n.waitingSec === 'number') : undefined;
  const pipe = nameOf(raw, input.id);
  const fromMemo = input.memoHead === null ? null : nameFromMemo(input.memoHead);
  return {
    key: input.key,
    session: record.name ?? fromMemo ?? pipe,
    pipe,
    branch: input.branch,
    other: input.other,
    previous: input.previous,
    stage,
    state,
    result: state === 'done' && view.final !== null ? finalWord(view.final) : null,
    sessionId: record.sessionId ?? lastStageRun(record)?.sessionId ?? null,
    costText: typeof raw.total_cost_usd === 'number' && Number.isFinite(raw.total_cost_usd) ? `$${raw.total_cost_usd.toFixed(3)}` : DASH,
    updatedText,
    updatedDate: updatedText === DASH ? DASH : updatedText.slice(0, 5),
    updatedMs: updated === null ? null : parseInstant(updated, clock.localOffsetMin),
    elapsed: elapsedOf(record, state, clock),
    waitingSec: waitingNode === undefined ? null : (waitingNode.waitingSec ?? null),
  };
}

const STATE_ORDER: Readonly<Record<RunState, number>> = { waiting: 0, running: 1, idle: 2, done: 3 };

/** 確認待ち → 動いている → 待ち → 終わった。同じ状態の中は新しい順（読めない時刻は最後）、同じなら key の順。選びは取らない。 */
export function sortRows(rows: readonly RunRow[]): RunRow[] {
  return [...rows].sort((a, b) => {
    if (a.state !== b.state) return STATE_ORDER[a.state] - STATE_ORDER[b.state];
    if (a.updatedMs !== b.updatedMs) {
      if (a.updatedMs === null) return 1;
      if (b.updatedMs === null) return -1;
      return b.updatedMs - a.updatedMs;
    }
    return a.key < b.key ? -1 : a.key > b.key ? 1 : 0;
  });
}

/** 省いた archive の件数の文字。0 以下は空。 */
export function omittedText(count: number): string {
  return count > 0 ? `古い実行を ${count} 件、省いています` : '';
}

/** workspaceState から読んだ値の検め：{place, id} の2つの文字列で、実行の目印の形に合うものだけ。 */
export function parseRemembered(value: unknown): { place: PlaceKey; id: string } | null {
  if (!isJsonObject(value)) return null;
  const { place, id } = value;
  if (typeof place !== 'string' || typeof id !== 'string') return null;
  return parseRunKey(makeRunKey(place, id)) === null ? null : { place, id };
}
