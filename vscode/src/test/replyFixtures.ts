// D0079：返事を受け付けている確認待ちの記録（state.json の reply_wait＝印）の見本。テストの中で文字列として作る（tests/fixtures/ には足さない）。
// 印の形：{ stage, id, since }。待っている間だけ本体が書く。見本の時刻は liveFixtures.ts の BASE_AT（「今」は clockAt(sec) で決める）。
// 項目がまだ無い型（PipelineView.reply・RunRecord.replyWait など）は、型に頼らず値を読む。
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { PipelineView, WorkDirSnapshot } from '../domain/pipelineView.ts';
import type { RunRow } from '../domain/runList.ts';
import { summarizeRun } from '../domain/runList.ts';
import { assistantText, DEV_STAGES, DIAGRAMS_STAGES, logText, promptLine, snapshot, stageRunEntry, stateJson } from './fixtures.ts';
import { BASE_AT, RUNNING_UPDATED_AT, STARTED_AT, clockAt } from './liveFixtures.ts';

/** 印の識別子の見本（10 文字の 16 進）と、次の待ちの識別子 */
export const MARK_ID = 'a1b2c3d4e5';
export const NEXT_ID = 'f0e1d2c3b4';
/** 印の始めた時刻（BASE_AT）。「今」を clockAt(40) にすると 40 秒たったところ */
export const MARK_AT = BASE_AT;
export const PIPE_NAME = 'reply-pipe';

/** 印（reply_wait）の値。stage の既定は開発フローの requirements */
export function mark(over: Record<string, unknown> = {}): Record<string, unknown> {
  return { stage: 'requirements', id: MARK_ID, since: MARK_AT, ...over };
}

export interface ReplyStateOptions {
  /** 'dev'（既定。開発フロー）か、パイプ名。パイプは DIAGRAMS_STAGES の段を持つ */
  pipe?: string;
  /** 印の値。省くと既定の印、null なら印の鍵を書かない（古い本体の記録） */
  mark?: unknown;
  /** driver の値（省くと書かない＝端末で流した SDK の実行） */
  driver?: unknown;
  /** pending_review（省くと書かない） */
  pendingReview?: unknown;
  final?: string | null;
}

/** 確認の段が 1 つ済んで、答えを待っている記録の state.json（最初の段の実行が 1 件）。 */
export function replyState(p: ReplyStateOptions = {}): string {
  const pipe = p.pipe ?? 'dev';
  const dev = pipe === 'dev';
  const first = dev ? 'requirements' : 'survey';
  const base = JSON.parse(
    stateJson({
      pipe,
      stages: dev ? DEV_STAGES : DIAGRAMS_STAGES,
      runs: [stageRunEntry({ stage: first, seq: 1, durationSec: 30 })],
      startedAt: STARTED_AT,
      updatedAt: RUNNING_UPDATED_AT,
      ...(p.final === undefined ? {} : { final: p.final }),
      ...(p.driver === undefined ? {} : { driver: p.driver }),
      ...(p.pendingReview === undefined ? {} : { pendingReview: p.pendingReview }),
    }),
  ) as Record<string, unknown>;
  if (p.mark !== null) base.reply_wait = p.mark === undefined ? mark({ stage: first }) : p.mark;
  return JSON.stringify(base);
}

/** 既存の state.json に鍵を足す（印の鍵を後から足す・形を壊すときに使う） */
export function withKeys(json: string, extra: Record<string, unknown>): string {
  return JSON.stringify({ ...(JSON.parse(json) as Record<string, unknown>), ...extra });
}

/** pending_review の見本（--pause や /pipe-in の記録）。 */
export function pending(stage = 'requirements', doc = 'docs/pipeline/01_requirements.md'): Record<string, unknown> {
  return { stage, doc, session_id: 's', since: MARK_AT };
}

export interface ReplySnapshotOptions extends ReplyStateOptions {
  /** reply.json の有無と更新時刻（読み取りの口が返す形）。省くと項目ごと無い */
  replyFile?: { mtimeMs: number | null } | null;
  /** 別の worktree の写し */
  other?: boolean;
  /** archive/ の前の実行の写し */
  previous?: boolean;
  /** true なら、次の段が動いているログを足す（動いている段がある） */
  running?: boolean;
  /** state.json の文字を直に渡す（p の ReplyStateOptions より優先） */
  stateJson?: string | null;
}

/** 記録の写し。項目 other・replyFile はまだ型に無いので、型を越えて足す。 */
export function replySnapshot(p: ReplySnapshotOptions = {}): WorkDirSnapshot {
  const dev = (p.pipe ?? 'dev') === 'dev';
  const next = dev ? { file: '02_design.jsonl', stage: 'design' } : { file: '02_draw.jsonl', stage: 'draw' };
  const snap = snapshot({
    stateJson: p.stateJson === undefined ? replyState(p) : p.stateJson,
    stageLogs: p.running ? [{ fileName: next.file, text: logText([promptLine(next.stage, BASE_AT), assistantText('進めます')]) }] : [],
    artifacts: dev ? { '00_input.md': 'メモ', '01_requirements.md': '要件' } : { '00_input.md': 'メモ', '01_survey.md': '調査' },
  });
  const extra: Record<string, unknown> = {};
  if (p.previous === true) extra.previous = true;
  if (p.other === true) extra.other = true;
  if (p.replyFile !== undefined) extra.replyFile = p.replyFile;
  return { ...snap, ...extra } as WorkDirSnapshot;
}

/** 図の状態。「今」は印の始めた時刻から sec 秒後。 */
export function replyView(p: ReplySnapshotOptions = {}, sec = 40): PipelineView {
  return buildPipelineView(replySnapshot(p), clockAt(sec));
}

/** 実行の一覧の行 1 つ（summarizeRun）。「今」は印の始めた時刻から sec 秒後。 */
export function replyRow(p: ReplySnapshotOptions & { key?: string; id?: string } = {}, sec = 40): RunRow {
  const snap = replySnapshot(p);
  return summarizeRun(
    {
      key: p.key ?? 'here|',
      id: p.id ?? '',
      branch: null,
      other: p.other === true,
      memoHead: null,
      previous: p.previous === true,
      stateJson: snap.stateJson,
      stageLogs: snap.stageLogs,
    },
    clockAt(sec),
  );
}

// ---- まだ型に無い項目を、型に頼らず読む ----

export interface ReplyViewLike {
  stage: string;
  label: string;
  id: string;
  doc: string;
  waitingSec: number | null;
  sent: boolean;
  stalled: boolean;
}
export const replyOf = (view: PipelineView): ReplyViewLike | null => (view as unknown as { reply?: ReplyViewLike | null }).reply ?? null;
export const hasDriverOf = (view: PipelineView): unknown => (view as unknown as { hasDriver?: unknown }).hasDriver;
export const pausePipeOf = (view: PipelineView): unknown => (view as unknown as { pausePipe?: unknown }).pausePipe;
