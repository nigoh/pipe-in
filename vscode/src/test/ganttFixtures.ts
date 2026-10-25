// テストの補助：時系列（D0019）の記録の組み立て。時刻は BASE_MS（2026-10-17 10:00:00 UTC）からの秒で決める。
// 記録の始まり（started_at）は BASE の時刻（ずれなしの古い書き方）、段のログの at はずれつき（+00:00）で書く。
import { BASE_MS } from './liveFixtures.ts';
import { assistantText, logText, promptLine, resultLine, snapshot, stageRunEntry, stateJson } from './fixtures.ts';
import { failVerdict, passVerdict } from './reasonFixtures.ts';
import type { WorkDirSnapshot } from '../domain/pipelineView.ts';

/** 記録の始まり（started_at。ずれなし。手元のずれ 0 のとき BASE と同じ） */
export const GANTT_STARTED_AT = '2026-10-17T10:00:00';

/** BASE から sec 秒後の時刻の文字（UTC からのずれつき） */
export function atSec(sec: number): string {
  return new Date(BASE_MS + sec * 1000).toISOString().replace('.000Z', '+00:00');
}

/** BASE から sec 秒後の時刻の文字（ずれなしの古い書き方。手元のずれ 0 のとき同じ時刻） */
export function naiveAtSec(sec: number): string {
  return new Date(BASE_MS + sec * 1000).toISOString().replace('.000Z', '');
}

export function logName(seq: number, stage: string, attempt?: number): string {
  return `${String(seq).padStart(2, '0')}_${stage}${attempt === undefined ? '' : `_${attempt}`}.jsonl`;
}

/**
 * 段のログ 1 つ。finished なら結果の行を持つ（動いていない）。at は文字でも壊れた値でもよい。
 * lines（D0050）は、文章の行のあと・結果の行の前に足す行（呼び出しの行など。呼び出しごとに別の id を持たせた行を渡す）。
 */
export function stageLog(p: {
  seq: number;
  stage: string;
  attempt?: number;
  at?: unknown;
  finished?: boolean;
  agent?: unknown;
  lines?: readonly string[];
}): { fileName: string; text: string } {
  return {
    fileName: logName(p.seq, p.stage, p.attempt),
    text: logText([promptLine(p.stage, p.at, p.agent), assistantText('x'), ...(p.lines ?? []), ...(p.finished === false ? [] : [resultLine()])]),
  };
}

export interface RunSpec {
  stage: string;
  seq: number;
  attempt?: number;
  /** 段の始まりの BASE からの秒（段のログの at に書く）。undefined ならログの at を書かない */
  start?: number;
  durationSec?: number;
  agent?: unknown;
  isError?: boolean;
  /** 段のログに足す行（D0050。呼び出しの行など）。省くと足さない */
  lines?: readonly string[];
}

export const dur = (run: RunSpec): number => run.durationSec ?? 0;

/**
 * 段の実行の並びから、記録の写しを作る。runs のあとに続く要素（review・verdict など）は extras に、位置を指定して差し込む。
 * 各実行に、結果の行つきのログ（start があるとき at つき）を付ける。running は動いている段のログ（結果の行なし）。
 */
export function ganttSnapshot(p: {
  runs: RunSpec[];
  /** runs[] に入れる、段の実行以外の要素。after は直前の実行の seq（その実行の直後に差し込む） */
  extras?: { after: number; entry: object }[];
  running?: { seq: number; stage: string; attempt?: number; start?: unknown; agent?: unknown; lines?: readonly string[] };
  final?: string | null;
  startedAt?: unknown;
  updatedAt?: unknown;
  pendingReview?: unknown;
  stages?: unknown;
  pipe?: string;
}): WorkDirSnapshot {
  const entries: object[] = [];
  for (const r of p.runs) {
    entries.push(
      stageRunEntry({
        stage: r.stage,
        seq: r.seq,
        attempt: r.attempt ?? null,
        durationSec: r.durationSec ?? 0,
        isError: r.isError ?? false,
        agent: r.agent,
      }),
    );
    for (const x of p.extras ?? []) if (x.after === r.seq) entries.push(x.entry);
  }
  const logs = p.runs.map((r) =>
    stageLog({ seq: r.seq, stage: r.stage, attempt: r.attempt, at: r.start === undefined ? undefined : atSec(r.start), agent: r.agent, ...(r.lines === undefined ? {} : { lines: r.lines }) }),
  );
  if (p.running !== undefined) {
    logs.push(
      stageLog({
        seq: p.running.seq,
        stage: p.running.stage,
        attempt: p.running.attempt,
        at: p.running.start,
        finished: false,
        agent: p.running.agent,
        ...(p.running.lines === undefined ? {} : { lines: p.running.lines }),
      }),
    );
  }
  return snapshot({
    stateJson: stateJson({
      runs: entries,
      final: p.final ?? null,
      startedAt: p.startedAt === undefined ? GANTT_STARTED_AT : p.startedAt,
      updatedAt: p.updatedAt === undefined ? naiveAtSec(0) : p.updatedAt,
      ...(p.pendingReview === undefined ? {} : { pendingReview: p.pendingReview }),
      ...(p.stages === undefined ? {} : { stages: p.stages }),
      ...(p.pipe === undefined ? {} : { pipe: p.pipe }),
    }),
    stageLogs: logs,
    artifacts: { '00_input.md': 'メモ' },
  });
}

export const review = (stage: string, action: 'approved' | 'revise' | 'quit'): object =>
  action === 'revise' ? { stage, review: 'revise', feedback: '直して' } : { stage, review: action };

export { failVerdict, passVerdict };

/**
 * 終わった開発フロー（合格）。実行 8 回。時刻（BASE からの秒）：
 *   1 要件定義 5〜35（修正の依頼）→ 2 要件定義 60〜80（承認）→ 3 設計 90〜130（承認）→ 4 テスト先行 140〜150（確認なし）
 *   → 5 実装(1) 160〜210 → 6 検証(1) 220〜240（不合格）→ 7 実装(2) 250〜280 → 8 検証(2) 290〜305（合格）
 * 確認の待ち：1 は 35〜60、2 は 80〜90、3 は 130〜140。4 以降は確認なし。updated_at は 330 秒。
 */
export function finishedGantt(): WorkDirSnapshot {
  return ganttSnapshot({
    runs: [
      { stage: 'requirements', seq: 1, start: 5, durationSec: 30, agent: 'pipe-in-analyst' },
      { stage: 'requirements', seq: 2, start: 60, durationSec: 20, agent: 'pipe-in-analyst' },
      { stage: 'design', seq: 3, start: 90, durationSec: 40, agent: 'pipe-in-analyst' },
      { stage: 'red', seq: 4, start: 140, durationSec: 10, agent: 'pipe-in-tester' },
      { stage: 'implement', seq: 5, attempt: 1, start: 160, durationSec: 50, agent: 'pipe-in-coder' },
      { stage: 'test', seq: 6, attempt: 1, start: 220, durationSec: 20, agent: 'pipe-in-verifier' },
      { stage: 'implement', seq: 7, attempt: 2, start: 250, durationSec: 30, agent: 'pipe-in-coder' },
      { stage: 'test', seq: 8, attempt: 2, start: 290, durationSec: 15, agent: 'pipe-in-verifier' },
    ],
    extras: [
      { after: 1, entry: review('requirements', 'revise') },
      { after: 2, entry: review('requirements', 'approved') },
      { after: 3, entry: review('design', 'approved') },
      { after: 6, entry: failVerdict({ attempt: 1, summary: '不合格', failures: [{ criterion: 'AC-01', detail: 'x' }] }) },
      { after: 8, entry: passVerdict(2) },
    ],
    final: 'PASSED',
    updatedAt: naiveAtSec(330),
  });
}
