// 動きと各段の時間（D0017）のテストで使う、時刻つきの記録の組み立て。
// 時計は固定の値（ViewClock）で、ここで「今」を決める。本物の時計には触れない。
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { PipelineView, ViewClock, WorkDirSnapshot } from '../domain/pipelineView.ts';
import { assistantText, logText, promptLine, snapshot, stageRunEntry, stateJson } from './fixtures.ts';
import { failVerdict, reviseEntry } from './reasonFixtures.ts';

/** 動いている段が始まった・確認を待ち始めた時刻（UTC）。「今」はここからの秒で決める。 */
export const BASE_MS = Date.UTC(2026, 9, 17, 10, 0, 0);
/** BASE_MS をオフセットつきの文字にしたもの（本体が新しく書く書き方）。 */
export const BASE_AT = '2026-10-17T10:00:00+00:00';
/** 全体の始まり（started_at。本体は今もオフセットなしで書く）。手元のずれ 0 のとき BASE の 120 秒前。 */
export const STARTED_AT = '2026-10-17T09:58:00';
export const OVERALL_BEFORE_SEC = 120;
/** 終わった記録の updated_at（STARTED_AT から 420 秒後）。 */
export const FINISHED_UPDATED_AT = '2026-10-17T10:05:00';
export const FINISHED_ELAPSED_SEC = 420;
/** 動いている記録の updated_at（STARTED_AT から 150 秒後）。 */
export const RUNNING_UPDATED_AT = '2026-10-17T10:00:30';

const REQUIREMENTS_DOC = 'docs/pipeline/01_requirements.md';
const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'tests', 'fixtures');

/** 見本の記録（tests/fixtures/<dir>/）の state.json と logs/*.jsonl を、記録の写しにする。読むだけで書かない。 */
export function fixtureSnapshot(...parts: string[]): WorkDirSnapshot {
  const dir = path.join(FIXTURES, ...parts);
  let logs: string[] = [];
  try {
    logs = readdirSync(path.join(dir, 'logs')).filter((f) => f.endsWith('.jsonl'));
  } catch {
    // logs/ の無い見本
  }
  return snapshot({
    stateJson: readFileSync(path.join(dir, 'state.json'), 'utf8'),
    stageLogs: logs.map((fileName) => ({ fileName, text: readFileSync(path.join(dir, 'logs', fileName), 'utf8') })),
    artifacts: { '00_input.md': 'メモ' },
  });
}

/** 「今」＝ BASE から sec 秒後。localOffsetMin は手元の UTC からのずれ（分）。 */
export function clockAt(sec: number, localOffsetMin = 0): ViewClock {
  return { nowMs: BASE_MS + sec * 1000, localOffsetMin };
}

/** 要件定義は終わり、設計が at から動いている記録（開発フロー）。 */
export function runningSnapshot(p: { at?: unknown; omitAt?: boolean; startedAt?: unknown } = {}): WorkDirSnapshot {
  const at = p.omitAt ? undefined : p.at === undefined ? BASE_AT : p.at;
  return snapshot({
    stateJson: stateJson({
      runs: [stageRunEntry({ stage: 'requirements', seq: 1, durationSec: 30 })],
      startedAt: p.startedAt === undefined ? STARTED_AT : p.startedAt,
      updatedAt: RUNNING_UPDATED_AT,
    }),
    stageLogs: [{ fileName: '02_design.jsonl', text: logText([promptLine('design', at), assistantText('設計します')]) }],
    artifacts: { '00_input.md': 'メモ' },
  });
}

/** 要件定義が終わり、その確認を since から待っている記録（開発フロー）。 */
export function waitingSnapshot(p: { since?: unknown; omitSince?: boolean; startedAt?: unknown } = {}): WorkDirSnapshot {
  const since = p.omitSince ? undefined : p.since === undefined ? BASE_AT : p.since;
  return snapshot({
    stateJson: stateJson({
      runs: [stageRunEntry({ stage: 'requirements', seq: 1, durationSec: 30 })],
      pendingReview: { stage: 'requirements', doc: REQUIREMENTS_DOC, session_id: 's', ...(since === undefined ? {} : { since }) },
      startedAt: p.startedAt === undefined ? STARTED_AT : p.startedAt,
      updatedAt: RUNNING_UPDATED_AT,
    }),
    stageLogs: [{ fileName: '01_requirements.jsonl', text: logText([promptLine('requirements', BASE_AT), assistantText('書いた')]) }],
    artifacts: { '00_input.md': 'メモ', '01_requirements.md': '要件' },
  });
}

/** 最後まで終わった記録（PASSED）。実装は3回（差し戻し2回）で、回ごとの時間を持つ。 */
export function finishedSnapshot(): WorkDirSnapshot {
  return snapshot({
    stateJson: stateJson({
      runs: [
        stageRunEntry({ stage: 'requirements', seq: 1, durationSec: 48 }),
        stageRunEntry({ stage: 'implement', seq: 2, attempt: 1, durationSec: 121.04 }),
        stageRunEntry({ stage: 'test', seq: 3, attempt: 1, durationSec: 57 }),
        failVerdict({ attempt: 1, summary: '不合格', failures: [{ criterion: 'AC-01', detail: 'a' }] }),
        stageRunEntry({ stage: 'implement', seq: 4, attempt: 2, durationSec: 78.02 }),
        stageRunEntry({ stage: 'test', seq: 5, attempt: 2, durationSec: 52 }),
        failVerdict({ attempt: 2, summary: '不合格', failures: [{ criterion: 'AC-01', detail: 'b' }] }),
        stageRunEntry({ stage: 'implement', seq: 6, attempt: 3, durationSec: 40.01 }),
        stageRunEntry({ stage: 'test', seq: 7, attempt: 3, durationSec: 30 }),
        { stage: 'test', attempt: 3, verdict: { status: 'pass', summary: '合格', failures: [], commands: [], command_check: null } },
      ],
      final: 'PASSED',
      startedAt: STARTED_AT,
      updatedAt: FINISHED_UPDATED_AT,
    }),
    artifacts: { '00_input.md': 'メモ' },
  });
}

/**
 * 戻る矢印の回数を決めた記録：差し戻し（検証の不合格）sendBack 回、要件定義の修正の依頼 revise 回。
 * running = true なら、最後の検証が at から動いている。
 */
export function loopSnapshot(p: { sendBack?: number; revise?: number; running?: boolean } = {}): WorkDirSnapshot {
  const sendBack = p.sendBack ?? 0;
  const revise = p.revise ?? 0;
  const runs: object[] = [stageRunEntry({ stage: 'requirements', seq: 1 })];
  for (let i = 0; i < revise; i++) runs.push(reviseEntry('requirements', `直して ${i + 1}`));
  let seq = 2;
  for (let attempt = 1; attempt <= sendBack + 1; attempt++) {
    runs.push(stageRunEntry({ stage: 'implement', seq: seq++, attempt }));
    if (attempt <= sendBack || !p.running) {
      runs.push(stageRunEntry({ stage: 'test', seq: seq++, attempt }));
    }
    if (attempt <= sendBack) runs.push(failVerdict({ attempt, summary: '不合格', failures: [{ criterion: 'AC-01', detail: `x${attempt}` }] }));
  }
  return snapshot({
    stateJson: stateJson({ runs, startedAt: STARTED_AT, updatedAt: RUNNING_UPDATED_AT }),
    stageLogs: p.running
      ? [{ fileName: `${String(seq).padStart(2, '0')}_test_${sendBack + 1}.jsonl`, text: logText([promptLine('test', BASE_AT), assistantText('検証します')]) }]
      : [],
    artifacts: { '00_input.md': 'メモ' },
  });
}

export function viewAt(snap: WorkDirSnapshot, sec = 0, localOffsetMin = 0): PipelineView {
  return buildPipelineView(snap, clockAt(sec, localOffsetMin));
}

/** 動いている段（設計）が BASE_AT から動いていて、「今」が secIn 秒後の図の状態。 */
export const runningView = (secIn: number): PipelineView => viewAt(runningSnapshot(), secIn);
/** 要件定義の確認を BASE_AT から待っていて、「今」が secIn 秒後の図の状態。 */
export const waitingView = (secIn: number): PipelineView => viewAt(waitingSnapshot(), secIn);
export const finishedView = (): PipelineView => viewAt(finishedSnapshot(), 9999);
/** 差し戻し sendBack 回の記録。 */
export const sendBackView = (sendBack: number): PipelineView => viewAt(loopSnapshot({ sendBack }));
/** 修正の依頼 revise 回の記録。 */
export const reviseView = (revise: number): PipelineView => viewAt(loopSnapshot({ revise }));

/** 時間の書き方の表（TypeScript の formatDuration と、パネルのスクリプトの写しの両方に同じ表を通す）。 */
export const DURATION_TABLE: readonly (readonly [number, string])[] = [
  [0, '0:00'],
  [7, '0:07'],
  [59, '0:59'],
  [60, '1:00'],
  [83, '1:23'],
  [3599, '59:59'],
  [3600, '1:00:00'],
  [3725, '1:02:05'],
  [36000, '10:00:00'],
  [7.9, '0:07'],
  [83.99, '1:23'],
  [-5, '0:00'],
];
