// 実行の記録：devpipe の state.json を読んだもの。記録の形の知識はここに閉じる。
import { isJsonObject } from './json.ts';
import type { JsonObject } from './json.ts';
import { isStage } from './stage.ts';
import type { Stage } from './stage.ts';

export type ReviewAction = 'approved' | 'revise' | 'quit';
export type VerdictStatus = 'pass' | 'fail' | 'blocked';

export interface StageRun {
  stage: Stage;
  seq: number;
  attempt: number | null;
  note: string;
  numTurns: number;
  costUsd: number;
  durationSec: number;
  isError: boolean;
}
export interface Review {
  stage: Stage;
  action: ReviewAction;
  feedback: string | null;
}
export interface RedResult {
  status: 'red' | 'blocked';
  summary: string;
}
export interface Verdict {
  attempt: number | null;
  status: VerdictStatus;
  summary: string;
}

export interface RunRecord {
  stageRuns: StageRun[];
  reviews: Review[];
  redResults: RedResult[];
  verdicts: Verdict[];
  /** 'PASSED' ほか。知らない文字列もそのまま */
  final: string | null;
  totalCostUsd: number;
  startedAt: string | null;
}

export const EMPTY_RUN_RECORD: RunRecord = {
  stageRuns: [],
  reviews: [],
  redResults: [],
  verdicts: [],
  final: null,
  totalCostUsd: 0,
  startedAt: null,
};

/** EMPTY_RUN_RECORD の写し（配列は新しく作る。読み取りの途中で足していくため）。 */
function emptyRecord(): RunRecord {
  return { ...EMPTY_RUN_RECORD, stageRuns: [], reviews: [], redResults: [], verdicts: [] };
}

const REVIEW_ACTIONS: readonly string[] = ['approved', 'revise', 'quit'];
const VERDICT_STATUSES: readonly string[] = ['pass', 'fail', 'blocked'];
const RED_STATUSES: readonly string[] = ['red', 'blocked'];

function num(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}
function numOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}
function str(value: unknown): string {
  return typeof value === 'string' ? value : '';
}
function strOrNull(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

/** state.json の中身を読む。null（ファイルなし）・壊れた JSON・形の違う JSON でも例外を投げず EMPTY_RUN_RECORD 相当を返す。 */
export function parseRunRecord(text: string | null): RunRecord {
  if (text === null) return emptyRecord();
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return emptyRecord();
  }
  if (!isJsonObject(data)) return emptyRecord();

  const record = emptyRecord();
  record.final = strOrNull(data.final);
  record.totalCostUsd = num(data.total_cost_usd);
  record.startedAt = strOrNull(data.started_at);
  if (!Array.isArray(data.runs)) return record;

  for (const entry of data.runs) {
    if (!isJsonObject(entry)) continue;
    classifyRunEntry(entry, record);
  }
  return record;
}

/** runs の要素1つを見分けて record に足す（上から順に最初に当てはまるもの。どれでもなければ捨てる）。 */
function classifyRunEntry(entry: JsonObject, record: RunRecord): void {
  const stage = entry.stage;
  if (typeof entry.seq === 'number' && isStage(stage)) {
    record.stageRuns.push({
      stage,
      seq: entry.seq,
      attempt: numOrNull(entry.attempt),
      note: str(entry.note),
      numTurns: num(entry.num_turns),
      costUsd: num(entry.cost_usd),
      durationSec: num(entry.duration_sec),
      isError: entry.is_error === true,
    });
    return;
  }
  if (typeof entry.review === 'string' && REVIEW_ACTIONS.includes(entry.review) && isStage(stage)) {
    record.reviews.push({ stage, action: entry.review as ReviewAction, feedback: strOrNull(entry.feedback) });
    return;
  }
  const verdict = entry.verdict;
  if (isJsonObject(verdict) && typeof verdict.status === 'string' && VERDICT_STATUSES.includes(verdict.status)) {
    record.verdicts.push({
      attempt: numOrNull(entry.attempt),
      status: verdict.status as VerdictStatus,
      summary: str(verdict.summary),
    });
    return;
  }
  const result = entry.result;
  if (stage === 'red' && isJsonObject(result) && typeof result.status === 'string' && RED_STATUSES.includes(result.status)) {
    record.redResults.push({ status: result.status as RedResult['status'], summary: str(result.summary) });
  }
  // command_check を持つ要素・知らない形の要素は捨てる
}
