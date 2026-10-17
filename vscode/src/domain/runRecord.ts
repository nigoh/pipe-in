// 実行の記録：本体の state.json を読んだもの。記録の形の知識はここに閉じる。
import { isJsonObject } from './json.ts';
import type { JsonObject } from './json.ts';
import { STAGES, isStage, isStageName } from './stage.ts';
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
  /** 本体 0.2 の metrics から。古い記録では null */
  tokens: TokenCounts | null;
  cacheReuseRate: number | null;
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

/** トークン数（本体の Tokens のうち、表に出すもの）。 */
export interface TokenCounts {
  /** キャッシュを使わない入力 */
  input: number;
  cacheWrite: number;
  cacheRead: number;
  output: number;
  /** 出力のうち考える過程の分 */
  thinking: number;
}
export interface ModelUsage {
  model: string;
  tokens: TokenCounts;
  costUsd: number;
}
/** 利用枠1つの、パイプラインの間の使用率（0〜1）。 */
export interface RateWindow {
  /** 記録上の名前（five_hour など） */
  name: string;
  /** 言葉の名前（5時間枠 など。知らない枠は name のまま） */
  label: string;
  first: number | null;
  last: number | null;
  peak: number | null;
  /** 使用率が下がった＝途中で枠が戻った */
  resetSeen: boolean;
  /** 枠が戻る時刻（UNIX 秒） */
  resetsAt: number | null;
}
/** パイプライン全体の使用量（state.json の usage_summary）。 */
export interface UsageSummary {
  tokens: TokenCounts;
  cacheReuseRate: number;
  durationApiMs: number;
  /** 段の既定のモデル */
  models: string[];
  /** 費用の高い順 */
  byModel: ModelUsage[];
  /** 5時間枠・7日枠・知らない枠の順 */
  rateLimits: RateWindow[];
}

/** 段の並びの1つ（state.json の stages）。output・review はそれを書く前の記録では null。 */
export interface StageDef {
  name: Stage;
  label: string;
  /** 段の成果物のファイル名。ファイル名として読めないもの（パスの区切りを含む・. で始まる）は null */
  output: string | null;
  /** このあとに人の確認を取るか */
  review: boolean | null;
}

/** 人の確認で止まっているときの段と文書（state.json の pending_review）。 */
export interface PendingReview {
  stage: Stage;
  /** 確認する文書のパス（プロジェクトからの相対） */
  doc: string;
}

export interface RunRecord {
  /** パイプの名前（開発フローは 'dev'）。パイプを持つ前の記録では null */
  pipe: string | null;
  /** 段の並び。パイプを持つ前の記録では null */
  stages: StageDef[] | null;
  pendingReview: PendingReview | null;
  warnings: string[];
  updatedAt: string | null;
  stageRuns: StageRun[];
  reviews: Review[];
  redResults: RedResult[];
  verdicts: Verdict[];
  /** 'PASSED' ほか。知らない文字列もそのまま */
  final: string | null;
  totalCostUsd: number;
  startedAt: string | null;
  /** 本体 0.2 から。古い記録では null */
  usage: UsageSummary | null;
}

export const EMPTY_RUN_RECORD: RunRecord = {
  pipe: null,
  stages: null,
  pendingReview: null,
  warnings: [],
  updatedAt: null,
  stageRuns: [],
  reviews: [],
  redResults: [],
  verdicts: [],
  final: null,
  totalCostUsd: 0,
  startedAt: null,
  usage: null,
};

/** EMPTY_RUN_RECORD の写し（配列は新しく作る。読み取りの途中で足していくため）。 */
function emptyRecord(): RunRecord {
  return { ...EMPTY_RUN_RECORD, warnings: [], stageRuns: [], reviews: [], redResults: [], verdicts: [] };
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
  record.usage = parseUsageSummary(data.usage_summary);
  record.pipe = strOrNull(data.pipe);
  record.updatedAt = strOrNull(data.updated_at);
  record.stages = parseStages(data.stages);
  record.pendingReview = parsePendingReview(data.pending_review);
  record.warnings = Array.isArray(data.warnings) ? data.warnings.filter((w): w is string => typeof w === 'string') : [];
  if (!Array.isArray(data.runs)) return record;

  // 段の並びを持たない記録はパイプを持つ前の開発フローのものなので、開発の5段だけを受け付ける
  const knownStage: (value: unknown) => value is Stage = record.stages === null ? isStage : isStageName;

  for (const entry of data.runs) {
    if (!isJsonObject(entry)) continue;
    classifyRunEntry(entry, record, knownStage);
  }
  return record;
}

/** runs の要素1つを見分けて record に足す（上から順に最初に当てはまるもの。どれでもなければ捨てる）。 */
function classifyRunEntry(entry: JsonObject, record: RunRecord, knownStage: (value: unknown) => value is Stage): void {
  const stage = entry.stage;
  if (typeof entry.seq === 'number' && knownStage(stage)) {
    record.stageRuns.push({
      stage,
      seq: entry.seq,
      attempt: numOrNull(entry.attempt),
      note: str(entry.note),
      numTurns: num(entry.num_turns),
      costUsd: num(entry.cost_usd),
      durationSec: num(entry.duration_sec),
      isError: entry.is_error === true,
      ...stageRunUsage(entry.metrics),
    });
    return;
  }
  if (typeof entry.review === 'string' && REVIEW_ACTIONS.includes(entry.review) && knownStage(stage)) {
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

// ---- 段の並び・確認待ち（パイプを持つようになってからの記録） --------------------------

/** 記録の置き場所の中のファイル名だけを通す（パスの区切り・. で始まるもの・: を含むものは null）。 */
function fileNameOrNull(value: unknown): string | null {
  if (typeof value !== 'string' || value === '' || value.startsWith('.')) return null;
  return /[/\\:]/.test(value) ? null : value;
}

function parseStages(value: unknown): StageDef[] | null {
  if (!Array.isArray(value)) return null;
  const stages: StageDef[] = [];
  for (const s of value) {
    if (!isJsonObject(s) || !isStageName(s.name)) continue;
    stages.push({
      name: s.name,
      label: typeof s.label === 'string' && s.label !== '' ? s.label : s.name,
      output: fileNameOrNull(s.output),
      review: typeof s.review === 'boolean' ? s.review : null,
    });
  }
  return stages;
}

/** 開発フローの記録か。段の並びがない（パイプを持つ前の）記録と、段が開発の5段そのものの記録（kind = "dev" のパイプも）。 */
export function isDevRecord(record: RunRecord): boolean {
  const names = record.stages?.map((s) => s.name);
  return names === undefined || (names.length === STAGES.length && names.every((n, i) => n === STAGES[i]));
}

function parsePendingReview(value: unknown): PendingReview | null {
  if (!isJsonObject(value) || !isStageName(value.stage) || typeof value.doc !== 'string') return null;
  return { stage: value.stage, doc: value.doc };
}

// ---- 使用量（本体 0.2 の metrics・usage_summary） ----------------------------

const RATE_WINDOW_LABELS: Readonly<Record<string, string>> = { five_hour: '5時間枠', seven_day: '7日枠' };
const RATE_WINDOW_ORDER: readonly string[] = ['five_hour', 'seven_day'];

function parseTokens(value: unknown): TokenCounts {
  const t = isJsonObject(value) ? value : {};
  return {
    input: num(t.input),
    cacheWrite: num(t.cache_write),
    cacheRead: num(t.cache_read),
    output: num(t.output),
    thinking: num(t.thinking),
  };
}

function cacheReuseRate(value: unknown): number {
  return isJsonObject(value) ? num(value.cache_reuse_rate) : 0;
}

function stageRunUsage(metrics: unknown): Pick<StageRun, 'tokens' | 'cacheReuseRate'> {
  if (!isJsonObject(metrics) || !isJsonObject(metrics.tokens)) return { tokens: null, cacheReuseRate: null };
  return { tokens: parseTokens(metrics.tokens), cacheReuseRate: cacheReuseRate(metrics.tokens) };
}

function parseRateWindow(name: string, value: unknown): RateWindow | null {
  if (!isJsonObject(value)) return null;
  return {
    name,
    label: RATE_WINDOW_LABELS[name] ?? name,
    first: numOrNull(value.first),
    last: numOrNull(value.last),
    peak: numOrNull(value.peak),
    resetSeen: value.reset_seen === true,
    resetsAt: numOrNull(value.resets_at),
  };
}

function rateOrder(name: string): number {
  const i = RATE_WINDOW_ORDER.indexOf(name);
  return i === -1 ? RATE_WINDOW_ORDER.length : i;
}

/** usage_summary を読む。ない・オブジェクトでないなら null。中の読めない値は 0・空にする。 */
function parseUsageSummary(value: unknown): UsageSummary | null {
  if (!isJsonObject(value)) return null;
  const byModel: ModelUsage[] = [];
  if (isJsonObject(value.by_model)) {
    for (const [model, mu] of Object.entries(value.by_model)) {
      if (!isJsonObject(mu)) continue;
      byModel.push({ model, tokens: parseTokens(mu.tokens), costUsd: num(mu.cost_usd) });
    }
  }
  byModel.sort((a, b) => b.costUsd - a.costUsd);
  const rateLimits: RateWindow[] = [];
  if (isJsonObject(value.rate_limits)) {
    for (const [name, w] of Object.entries(value.rate_limits)) {
      const window = parseRateWindow(name, w);
      if (window) rateLimits.push(window);
    }
  }
  rateLimits.sort((a, b) => rateOrder(a.name) - rateOrder(b.name));
  return {
    tokens: parseTokens(value.tokens),
    cacheReuseRate: cacheReuseRate(value.tokens),
    durationApiMs: num(value.duration_api_ms),
    models: Array.isArray(value.models) ? value.models.filter((m): m is string => typeof m === 'string') : [],
    byModel,
    rateLimits,
  };
}
