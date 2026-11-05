// D0076：会話の中でパイプを流した記録（driver が pipe-chat・使用量が「取れない」）の見本。テストの中で文字列として作る（tests/fixtures/ には足さない）。
// 本体（pipe-in-gen chat）が書く形は docs/pipeline/02_design.md の 4.1。古い記録（費用が数・usage_summary あり）の対照も作る。
import type { WorkDirSnapshot } from '../domain/pipelineView.ts';
import { snapshot, stageRunEntry, usageSummaryDict } from './fixtures.ts';

export const UNAVAILABLE_REASON = '会話の中で流したため、費用とトークンは取れません';

/** 会話の道の記録の段の並び：下書き（確認あり）→ 確かめ（下書きへ戻す判定つき）。 */
export const CHAT_STAGES = [
  { name: 'draft', label: '下書き', output: '01_draft.md', review: true },
  { name: 'verify', label: '確かめ', output: '02_verify.md', review: false, check: { on_fail: 'draft', max_retries: 2 } },
];

/** 段の実行 1 回（会話の道は費用が取れないので cost_usd は null）。numeric を渡すと古い記録の形（費用が数）になる。 */
export function chatRun(stage: string, seq: number, opts: { cost?: number | null; attempt?: number | null; note?: string } = {}): object {
  return {
    ...(stageRunEntry({ stage, seq, numTurns: 0, durationSec: 3.2 }) as Record<string, unknown>),
    attempt: opts.attempt ?? null,
    note: opts.note ?? '',
    cost_usd: opts.cost === undefined ? null : opts.cost,
    session_id: null,
  };
}

const AT = '2026-11-05T10:00:00+00:00';

/** 下書き → 直す → 下書き → 承認 → 確かめ（不合格）→ 下書き（戻り）→ 確かめ（合格）の全部入りの runs。cost が数なら古い記録の形。 */
export function fullRuns(cost: number | null = null): object[] {
  return [
    chatRun('draft', 1, { cost }),
    { stage: 'draft', review: 'revise', feedback: 'ここを直して', at: AT },
    chatRun('draft', 2, { cost, note: '指摘を反映' }),
    { stage: 'draft', review: 'approved', at: AT },
    chatRun('verify', 3, { cost }),
    { stage: 'verify', check: { attempt: 1, status: 'fail', problems: ['矢印が逆'], summary: '' } },
    chatRun('draft', 4, { cost, note: '検証の指摘を反映' }),
    chatRun('verify', 5, { cost }),
    { stage: 'verify', check: { attempt: 2, status: 'pass', problems: [], summary: '' } },
  ];
}

export interface ChatState {
  runs?: object[];
  final?: string | null;
  pendingReview?: unknown;
  /** 省くと「取れない」。null を渡すと usage_summary を null に、'old' を渡すと古い記録の数の使用量（usageSummaryDict）にする */
  usageSummary?: unknown;
  /** 省くと null。数を渡すと古い記録の形 */
  totalCostUsd?: number | null;
  /** パイプ名（state.json の pipe。省くと cp） */
  pipe?: string;
  /** false なら driver を書かない（古い記録の形）。文字ならその値（pipe-dev など） */
  driver?: boolean | string;
}

/** state.json の中身（文字列）。 */
export function chatStateJson(p: ChatState = {}): string {
  const usage = p.usageSummary === undefined ? { available: false, reason: UNAVAILABLE_REASON } : p.usageSummary === 'old' ? usageSummaryDict() : p.usageSummary;
  return JSON.stringify({
    started_at: '2026-11-05T09:58:00',
    updated_at: '2026-11-05T10:05:00',
    pipe: p.pipe ?? 'cp',
    name: '会話の道の見本',
    ...(p.driver === false ? {} : { driver: typeof p.driver === 'string' ? p.driver : 'pipe-chat' }),
    stages: CHAT_STAGES,
    final: p.final ?? null,
    total_cost_usd: p.totalCostUsd === undefined ? null : p.totalCostUsd,
    usage_summary: usage,
    pending_review: p.pendingReview ?? null,
    warnings: [],
    open: null,
    runs: p.runs ?? fullRuns(),
  });
}

/** 記録の写し。 */
export function chatSnapshot(p: ChatState = {}): WorkDirSnapshot {
  return snapshot({ stateJson: chatStateJson(p), artifacts: { '00_input.md': 'メモ' } });
}

/** 古い記録（費用が数・usage_summary が数の表）の対照。 */
export function oldSnapshot(): WorkDirSnapshot {
  return chatSnapshot({ runs: fullRuns(0.01), usageSummary: 'old', totalCostUsd: 1.234, final: 'PASSED', driver: false });
}

/** 確認待ちの記録（下書きのあと承認を待っている）。 */
export function waitingSnapshot(p: ChatState = {}): WorkDirSnapshot {
  return chatSnapshot({
    ...p,
    runs: [chatRun('draft', 1)],
    pendingReview: { stage: 'draft', doc: 'docs/pipeline/cp/01_draft.md', session_id: null, next: 'verify', since: AT },
  });
}

/** 本体が持たないはずの項目を、型に頼らず読む（RunRecord / PipelineView の新しい項目 usageUnavailable）。 */
export const usageUnavailableOf = (x: unknown): unknown => (x as { usageUnavailable?: unknown }).usageUnavailable;
