// テスト用の記録（state.json・段のログ・記録の写し）を文字列として作る小さな関数。
// 本体 が work_dir に書く形（要件定義書「本体 が今書いている記録」）に合わせる。
import type { WorkDirSnapshot } from '../domain/pipelineView.ts';

/**
 * 段のログの始まりの行（`Prompt`）。at（段の始まりの時刻。D0017）は渡したときだけ入れる（壊れた値もそのまま入れて試せる）。
 * agent（受け持ち。D0019）も渡したときだけ入れる（本体の `record begin --agent` が書く項目）。
 */
export function promptLine(stage: string, at?: unknown, agent?: unknown): string {
  return JSON.stringify({
    _type: 'Prompt',
    stage,
    resume: null,
    prompt: `${stage} の依頼文`,
    ...(at === undefined ? {} : { at }),
    ...(agent === undefined ? {} : { agent }),
  });
}

/** 文章の部品を1つ持つ発言。 */
export function assistantText(text: string): string {
  return JSON.stringify({ _type: 'AssistantMessage', content: [{ text }], model: 'x' });
}

/** ツールの呼び出しの部品を1つ持つ発言。id（呼び出しの ID）は既定 't'。呼び出しごとに別の id を渡せる（D0049）。 */
export function assistantTool(name: string, input: object, id = 't'): string {
  return JSON.stringify({ _type: 'AssistantMessage', content: [{ id, name, input }], model: 'x' });
}

/**
 * 部品を複数持つ発言（D0049）。parentToolUseId は発言の行の項目（部品の項目ではない。サブエージェントの中の発言が、呼んだ Agent の id を持つ）。
 * 渡さない（undefined）と項目ごと無い。文字・null・数・オブジェクトも渡せる（壊れた値を試すため）。
 */
export function assistantParts(parts: readonly unknown[], parentToolUseId?: unknown): string {
  return JSON.stringify({
    _type: 'AssistantMessage',
    content: parts,
    model: 'x',
    ...(parentToolUseId === undefined ? {} : { parent_tool_use_id: parentToolUseId }),
  });
}

/** 道具の呼び出しの部品 { id, name, input }（D0049。assistantParts に渡す）。 */
export function toolPart(name: string, input: unknown, id: string): { id: string; name: string; input: unknown } {
  return { id, name, input };
}

/** 道具の結果の部品 { tool_use_id, content, is_error }（UserMessage の部品。数えない）。 */
export function resultPart(toolUseId: string, isError = false): { tool_use_id: string; content: string; is_error: boolean } {
  return { tool_use_id: toolUseId, content: '結果', is_error: isError };
}

/** 考え中の部品 { thinking, signature }（数えない）。 */
export function thinkingPart(): { thinking: string; signature: string } {
  return { thinking: '考え中', signature: 'sig' };
}

/** 段の実行の終わりの行。 */
export function resultLine(): string {
  return JSON.stringify({
    _type: 'ResultMessage',
    subtype: 'success',
    is_error: false,
    num_turns: 1,
    duration_ms: 1000,
    total_cost_usd: 0.01,
    result: 'ok',
  });
}

/** 行を改行でつないで、ファイルの中身にする（末尾に改行を付ける）。 */
export function logText(lines: string[]): string {
  return lines.map((l) => `${l}\n`).join('');
}

/** state.json の runs に入る「段の実行」の要素（本体 の `Pipeline._run_stage` が書く形）。 */
export function stageRunEntry(p: {
  stage: string;
  seq: number;
  attempt?: number | null;
  isError?: boolean;
  numTurns?: number;
  costUsd?: number;
  durationSec?: number;
  /** 本体 0.2 の metrics（StageMetrics.to_dict の形）。省くと古い記録と同じく持たない */
  metrics?: object;
  /** 受け持ち（D0019。record begin --agent が書く）。省くと持たない。壊れた値（数・空白を含む文字など）も入れて試せる */
  agent?: unknown;
  /** runs[].session_id（SDK の会話の ID）。省くと 's'。null（開発フローの record done）も渡せる */
  sessionId?: unknown;
  /** duration_sec を壊れた値（負・巨大・文字）にして試す。省くと durationSec */
  rawDurationSec?: unknown;
}): object {
  return {
    stage: p.stage,
    seq: p.seq,
    attempt: p.attempt ?? null,
    note: '',
    num_turns: p.numTurns ?? 1,
    cost_usd: p.costUsd ?? 0,
    duration_sec: p.rawDurationSec === undefined ? (p.durationSec ?? 0) : p.rawDurationSec,
    denials: [],
    is_error: p.isError ?? false,
    subtype: 'success',
    result: '',
    session_id: p.sessionId === undefined ? 's' : p.sessionId,
    errors: [],
    ...(p.agent === undefined ? {} : { agent: p.agent }),
    ...(p.metrics === undefined ? {} : { metrics: p.metrics }),
  };
}

/** トークン数（本体 の Tokens を dict にした形）。 */
export function tokensDict(p: { input?: number; cacheWrite?: number; cacheRead?: number; output?: number; thinking?: number }): object {
  const input = p.input ?? 0;
  const cacheWrite = p.cacheWrite ?? 0;
  const cacheRead = p.cacheRead ?? 0;
  const total = input + cacheWrite + cacheRead;
  return {
    input,
    cache_write: cacheWrite,
    cache_write_1h: cacheWrite,
    cache_write_5m: 0,
    cache_read: cacheRead,
    output: p.output ?? 0,
    thinking: p.thinking ?? 0,
    web_search: 0,
    web_fetch: 0,
    cache_reuse_rate: total === 0 ? 0 : Math.round((cacheRead / total) * 1e4) / 1e4,
  };
}

/** 段の実行の metrics（本体 の StageMetrics.to_dict の形）。 */
export function stageMetricsDict(p: { tokens?: object; model?: string } = {}): object {
  return {
    model: p.model ?? 'claude-opus-5-5',
    claude_code_version: '2.1.301',
    api_key_source: 'none',
    permission_mode: 'default',
    cost_basis: 'list',
    tokens: p.tokens ?? tokensDict({}),
    by_model: {},
    duration_api_ms: 1000,
    stop_reason: 'end_turn',
    terminal_reason: 'completed',
    permission_denials: [],
    rate_limits: {},
    overage_status: null,
  };
}

/** state.json の usage_summary（本体 の summarize_runs の形）。前回の本物の実行の数字に近いもの。 */
export function usageSummaryDict(): object {
  return {
    tokens: tokensDict({ input: 122, cacheWrite: 550460, cacheRead: 5224407, output: 126952, thinking: 23628 }),
    by_model: {
      'claude-haiku-5-5': { tokens: tokensDict({ input: 6676, output: 1206, thinking: 1085 }), cost_usd: 0.001 },
      'claude-opus-5-5': {
        tokens: tokensDict({ input: 122, cacheWrite: 550460, cacheRead: 5224407, output: 126952, thinking: 23628 }),
        cost_usd: 7.988,
      },
    },
    models: ['claude-opus-5-5'],
    rate_limits: {
      seven_day: { first: 0.14, last: 0.15, resets_at: 1792591200, peak: 0.15, reset_seen: false },
      five_hour: { first: 0.12, last: 0.02, resets_at: 1792170000, peak: 0.13, reset_seen: true },
    },
    duration_api_ms: 1133000,
  };
}

/** state.json の中身。 */
export function stateJson(p: {
  runs?: object[];
  final?: string | null;
  totalCostUsd?: number;
  /** 本体 0.2 の usage_summary。省くと古い記録と同じく持たない */
  usageSummary?: unknown;
  /** 以下は 本体 がパイプを持つようになってからの項目。省くとその前の記録と同じく持たない */
  pipe?: string;
  /** 段の並び（{name, label, output?, review?} の配列） */
  stages?: unknown;
  pendingReview?: unknown;
  warnings?: unknown;
  /** 時刻は壊れた値（数・オブジェクトなど）も入れて試せる（D0017） */
  updatedAt?: unknown;
  startedAt?: unknown;
  /** セッション名（D0019。本体が足した name）。省くと持たない。壊れた値も入れて試せる */
  name?: unknown;
  /** セッション ID（D0019。record start --session-id が書く session_id）。省くと持たない */
  sessionId?: unknown;
  /** 外の会話で進めた記録の印（本体が書く driver。D0049）。省くと持たない。null・''・0・false・{} も渡せる（null でなければ「ある」） */
  driver?: unknown;
}): string {
  return JSON.stringify({
    started_at: p.startedAt === undefined ? '2026-10-16T00:00:00' : p.startedAt,
    updated_at: p.updatedAt === undefined ? '2026-10-16T00:00:00' : p.updatedAt,
    ...(p.driver === undefined ? {} : { driver: p.driver }),
    ...(p.pipe === undefined ? {} : { pipe: p.pipe }),
    ...(p.name === undefined ? {} : { name: p.name }),
    ...(p.sessionId === undefined ? {} : { session_id: p.sessionId }),
    ...(p.stages === undefined ? {} : { stages: p.stages }),
    final: p.final ?? null,
    total_cost_usd: p.totalCostUsd ?? 0,
    ...(p.usageSummary === undefined ? {} : { usage_summary: p.usageSummary }),
    ...(p.pendingReview === undefined ? {} : { pending_review: p.pendingReview }),
    ...(p.warnings === undefined ? {} : { warnings: p.warnings }),
    runs: p.runs ?? [],
  });
}

/** 記録の写し。既定は workDir:'/w'・stateJson:null・stageLogs:[]・artifacts:{}。 */
export function snapshot(p: Partial<WorkDirSnapshot> = {}): WorkDirSnapshot {
  return {
    workDir: p.workDir ?? '/w',
    stateJson: p.stateJson ?? null,
    stageLogs: p.stageLogs ?? [],
    artifacts: p.artifacts ?? {},
  };
}

/** パイプ diagrams の段の並び（state.json の stages）。output・review まで持つ今の形。 */
export const DIAGRAMS_STAGES = [
  { name: 'survey', label: 'ソースの調査', output: '01_survey.md', review: true },
  { name: 'draw', label: '図を描く', output: '02_diagrams.md', review: true },
  { name: 'verify', label: '図とソースの突き合わせ', output: '03_verify.md', review: false },
];

/** 開発フローの段の並び（state.json の stages）。 */
export const DEV_STAGES = [
  { name: 'requirements', label: '要件定義', output: '01_requirements.md', review: true },
  { name: 'design', label: '設計', output: '02_design.md', review: true },
  { name: 'red', label: 'テスト先行', output: '03_red_tests.md', review: true },
  { name: 'implement', label: '実装', output: '04_implementation.md', review: false },
  { name: 'test', label: '検証', output: '05_test_report.md', review: false },
];
