// 図の状態：記録の写しだけから組み立てる。ファイル・時計・乱数・vscode に触れない。
import { artifactDefsFor, buildArtifactList, isArtifactReady } from './artifacts.ts';
import type { ArtifactContent, ArtifactEntry, ArtifactName } from './artifacts.ts';
import { buildGantt } from './gantt.ts';
import type { GanttModel } from './gantt.ts';
import { latestMtime, quietSecAt, validMtime } from './quiet.ts';
import { isDevRecord, isReadableState, parseRunRecord } from './runRecord.ts';
import type { RunRecord, StageDef, StageRun, TokenCounts, UsageSummary, VerdictFailure } from './runRecord.ts';
import { STAGE_LABELS } from './stage.ts';
import type { DevStage, Stage } from './stage.ts';
import { parseStageLog, parseStageLogName } from './stageLog.ts';
import type { OutputItem, StageLog, StageLogName } from './stageLog.ts';
import { elapsedSec, parseInstant } from './timestamp.ts';
import { buildToolsTable } from './toolsTable.ts';
import type { ToolsTable } from './toolsTable.ts';

/**
 * 段のログ 1 つの写し：ファイル名と中身と、ファイルの更新時刻。
 * 以前の `{ fileName; text }` と同じく、型の別名で書く（interface だと Record<string, unknown> との型変換が通らなくなる）。
 */
export type StageLogFile = {
  fileName: string;
  text: string;
  /** ファイルの更新時刻（UTC のミリ秒）。読めない・手で作った写しでは null か無し（印は出さない） */
  mtimeMs?: number | null;
};

/** 記録の写し。ファイルの中身だけ。基盤の層が作る。 */
export interface WorkDirSnapshot {
  /** 表示用のパス（記録なしの表示に出す） */
  workDir: string;
  /** state.json の中身。ないなら null */
  stateJson: string | null;
  /** logs/ の *.jsonl（ファイル名＋中身＋更新時刻）。順は問わない */
  stageLogs: StageLogFile[];
  /** ある成果物の中身（読んだ範囲の文字・更新時刻・切れた印。旧形は文字だけ）。ないものは鍵を持たない */
  artifacts: Partial<Record<ArtifactName, ArtifactContent>>;
  /** archive/ の前の実行の写し。止まっているかもの印の対象から外す。省けば false */
  previous?: boolean;
}

export type NodeStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped';
export const NODE_STATUS_LABELS: Readonly<Record<NodeStatus, string>> = {
  pending: 'まだ',
  running: '動いている',
  done: '完了',
  failed: '失敗',
  skipped: '省略',
};

/** 節の id。'input'・'final'・'verdict'、段の名前、確認は 'review:<段>'。 */
export type NodeId = string;

/** 開発フローの11節 */
export const NODE_ORDER: readonly NodeId[] = [
  'input',
  'requirements',
  'review:requirements',
  'design',
  'review:design',
  'red',
  'review:red',
  'implement',
  'test',
  'verdict',
  'final',
];

export const NODE_LABELS: Readonly<Record<string, string>> = {
  input: '要件メモ',
  requirements: '要件定義',
  'review:requirements': '確認',
  design: '設計',
  'review:design': '確認',
  red: 'テスト先行',
  'review:red': '確認',
  implement: '実装',
  test: '検証',
  verdict: '判定',
  final: '完了',
};

export interface StageMetrics {
  numTurns: number;
  costUsd: number;
  durationSec: number;
}

/** 「今」。時計は読まず、入口（extension.ts）が作って渡す。localOffsetMin は手元の UTC からのずれ（分）。 */
export interface ViewClock {
  nowMs: number;
  localOffsetMin: number;
}

/** 全体の経過。live なら数え上げる（動いている・確認待ち）、そうでなければ固定の値。 */
export interface Elapsed {
  seconds: number;
  live: boolean;
}

/** 段の実行1回分の時間。 */
export interface StageTimeRun {
  seq: number;
  attempt: number | null;
  durationSec: number;
}

/** 実行が2回以上ある段の、回ごとの時間と合計（右の欄の「時間」の節）。確認待ちの時間は入れない。 */
export interface StageTimes {
  stage: Stage;
  label: string;
  runs: StageTimeRun[];
  totalSec: number;
}

export interface PipelineNode {
  id: NodeId;
  label: string;
  status: NodeStatus;
  /** 動いている段の節だけ、始まりの時刻からの経過秒。時計や始まりの時刻が無ければ null（組み立てでは必ず入る。節を手で作る側のために省けるようにしてある） */
  runningSec?: number | null;
  /** 確認待ちの確認の節だけ、待ち始めの時刻からの経過秒。ほかは null（同上） */
  waitingSec?: number | null;
  /** 動いている段の節だけ、段のログが最後に更新されてからの秒（view.quietSec と同じ値）。ほかは null（同上） */
  quietSec?: number | null;
  /** 確認の節だけ数値（0 以上）。ほかは null */
  reviseCount: number | null;
  /** 実装の節だけ数値（0 以上）。ほかは null */
  sendBackCount: number | null;
  /** 段の節で段の実行が1件以上あるときだけ。ほかは null */
  metrics: StageMetrics | null;
}

export interface TerminalView {
  /** どの段のログを出しているか。ログがなければ null */
  source: StageLogName | null;
  items: OutputItem[];
}

export const WAITING_MESSAGE = '次を待っている（人の確認かもしれない）';
export const NO_RECORDS_MESSAGE = '記録がありません';

/** 人の確認で止まっている段と、確認する文書。 */
export interface PendingReviewView {
  stage: Stage;
  label: string;
  doc: string;
}

export interface PipelineView {
  /** 開発フローは常に11個（NODE_ORDER の順）。パイプは 依頼メモ・段（と確認）・完了 */
  nodes: PipelineNode[];
  /** 段の名前 → 表示の名前 */
  stageLabels: Readonly<Record<Stage, string>>;
  runningStage: Stage | null;
  terminal: TerminalView;
  totalCostUsd: number;
  final: string | null;
  artifacts: ArtifactEntry[];
  /** FR-13 */
  waiting: boolean;
  /** FR-14 */
  noRecords: { message: string; workDir: string } | null;
  /** 使用量（本体 0.2 から）。usage_summary のない記録では null */
  usage: UsageView | null;
  /** 確認待ち（state.json の pending_review）。なければ null */
  pendingReview: PendingReviewView | null;
  /** 注意（state.json の warnings） */
  warnings: string[];
  /** 検証の不合格（開発フローだけ。古い順） */
  sendBacks: SendBack[];
  /** 確認の直し（開発フローもパイプも。古い順） */
  revisions: ReviseNote[];
  /** 全体の経過（バナー用）。始まりの時刻が読めない・数え上げる時刻が無い記録では null */
  elapsed: Elapsed | null;
  /**
   * 動いている段の、段のログが最後に更新されてからの秒（止まっているかもの印の元は、ここ 1 つ）。
   * 印の対象でない run・更新時刻が読めない・時計が無いときは null（省いてもよい）
   */
  quietSec?: number | null;
  /** 実行が2回以上ある段の、回ごとの時間と合計 */
  stageTimes: StageTimes[];
  /** 時系列（段の実行ごとの行・エージェントの帯・確認を待った帯・横軸） */
  gantt: GanttModel;
  /**
   * 使ったエージェント・スキル・道具の表（D0047）。null ＝ 作らなかった（一覧の行の組み立て）。
   * 項目が無い（古い写し）ときも、表が空として読む。
   */
  tools?: ToolsTable | null;
}

/** 図の状態の組み立て方。 */
export interface BuildViewOptions {
  /** 偽なら表（tools）を作らず、段のログから呼び出しも取り出さない（null）。省けば真。一覧の行の組み立て（summarizeRun）だけが偽にする */
  tools?: boolean;
}

/** 検証の不合格1件。 */
export interface SendBack {
  /** 何回目の検証か（記録の attempt。無ければ不合格の並びの番号） */
  attempt: number;
  /** 戻り先の段（常に 'implement'）と表示の名前 */
  target: Stage;
  targetLabel: string;
  summary: string;
  failures: VerdictFailure[];
  /** 不合格のあとに実装のやり直しがあれば true。不合格のまま終わったなら false */
  sentBack: boolean;
}

/** 確認の直し（revise）1件。 */
export interface ReviseNote {
  stage: Stage;
  /** 段の表示の名前 */
  label: string;
  /** その段の何回目の修正の依頼か（1から） */
  attempt: number;
  feedback: string | null;
}

/** 節を選んだときに出す理由。 */
export type NodeReasons =
  | { kind: 'sendBack'; items: SendBack[] }
  | { kind: 'revise'; stage: Stage; label: string; items: ReviseNote[] };

const REVIEW_NODE_PREFIX = 'review:';

/** 検証の不合格を古い順に並べる。パイプの記録では空（パイプの check の戻り先は記録に残らない）。 */
function buildSendBacks(record: RunRecord, labels: Readonly<Record<Stage, string>>): SendBack[] {
  if (!isDevRecord(record)) return [];
  const implementAttempts = record.stageRuns.filter((r) => r.stage === 'implement').map((r) => r.attempt);
  const sendBacks: SendBack[] = [];
  record.verdicts.forEach((verdict, index) => {
    if (verdict.status !== 'fail') return;
    const attempt = verdict.attempt;
    const sentBack =
      attempt === null
        ? index < record.verdicts.length - 1
        : implementAttempts.some((a) => a !== null && a > attempt);
    sendBacks.push({
      attempt: attempt ?? sendBacks.length + 1,
      target: 'implement',
      targetLabel: labels.implement ?? 'implement',
      summary: verdict.summary,
      failures: verdict.failures,
      sentBack,
    });
  });
  return sendBacks;
}

/** 確認の直し（revise）を古い順に並べ、段ごとに回数を数える。 */
function buildRevisions(record: RunRecord, labels: Readonly<Record<Stage, string>>): ReviseNote[] {
  const counts = new Map<Stage, number>();
  const notes: ReviseNote[] = [];
  for (const review of record.reviews) {
    if (review.action !== 'revise') continue;
    const attempt = (counts.get(review.stage) ?? 0) + 1;
    counts.set(review.stage, attempt);
    notes.push({ stage: review.stage, label: labels[review.stage] ?? review.stage, attempt, feedback: review.feedback });
  }
  return notes;
}

/** 理由を持つ（選べる）節の id。図に無い節は入れない。 */
export function reasonNodeIds(view: PipelineView): NodeId[] {
  const revised = new Set(view.revisions.map((r) => r.stage));
  return view.nodes
    .filter((n) => {
      if (n.id === 'implement' || n.id === 'verdict') return view.sendBacks.length > 0;
      return n.id.startsWith(REVIEW_NODE_PREFIX) && revised.has(n.id.slice(REVIEW_NODE_PREFIX.length));
    })
    .map((n) => n.id);
}

/** 節の理由。履歴の無い節（と図に無い節）は null。 */
export function nodeReasons(view: PipelineView, nodeId: NodeId): NodeReasons | null {
  if (!reasonNodeIds(view).includes(nodeId)) return null;
  if (nodeId === 'implement' || nodeId === 'verdict') return { kind: 'sendBack', items: view.sendBacks };
  const stage = nodeId.slice(REVIEW_NODE_PREFIX.length);
  const items = view.revisions.filter((r) => r.stage === stage);
  return { kind: 'revise', stage, label: view.stageLabels[stage] ?? stage, items };
}

/** 使用量の表の1行：段の実行1回分。metrics のない古い段の実行は tokens が null。 */
export interface UsageRow {
  seq: number;
  stage: Stage;
  /** 段の表示の名前 */
  label: string;
  attempt: number | null;
  tokens: TokenCounts | null;
  cacheReuseRate: number | null;
}

export interface UsageView {
  summary: UsageSummary;
  /** 通し番号の順 */
  rows: UsageRow[];
}

function buildUsage(record: RunRecord, labels: Readonly<Record<Stage, string>>): UsageView | null {
  if (record.usage === null) return null;
  const rows = [...record.stageRuns]
    .sort((a, b) => a.seq - b.seq)
    .map(({ seq, stage, attempt, tokens, cacheReuseRate }) => ({
      seq,
      stage,
      label: labels[stage] ?? stage,
      attempt,
      tokens,
      cacheReuseRate,
    }));
  return { summary: record.usage, rows };
}

interface ReadLog {
  name: StageLogName;
  log: StageLog;
  fileName: string;
  /** ファイルの更新時刻（UTC のミリ秒）。読めなければ null */
  mtimeMs: number | null;
}

/** 名前の読めるログだけを (seq, fileName) の昇順に並べる。withCalls なら道具の呼び出し（calls）も取り出す。 */
function readLogs(stageLogs: WorkDirSnapshot['stageLogs'], withCalls: boolean): ReadLog[] {
  const logs: ReadLog[] = [];
  for (const file of stageLogs) {
    const name = parseStageLogName(file.fileName);
    if (name) {
      const log = parseStageLog(file.text, withCalls ? { calls: true } : undefined);
      logs.push({ name, log, fileName: file.fileName, mtimeMs: validMtime(file.mtimeMs) });
    }
  }
  return logs.sort((a, b) => a.name.seq - b.name.seq || (a.fileName < b.fileName ? -1 : a.fileName > b.fileName ? 1 : 0));
}

/** 動いている段のログ（FR-07）：Prompt があり終わっておらず、state.json に載った最大の通し番号より後ろのもの。 */
function findRunningLog(logs: ReadLog[], record: RunRecord): ReadLog | null {
  const maxSeq = record.stageRuns.reduce((max, run) => Math.max(max, run.seq), 0);
  const candidates = logs.filter(({ name, log }) => log.hasPrompt && !log.finished && name.seq > maxSeq);
  return candidates.at(-1) ?? null;
}

function sumMetrics(runs: StageRun[]): StageMetrics | null {
  if (runs.length === 0) return null;
  const numTurns = runs.reduce((s, r) => s + r.numTurns, 0);
  const costUsd = runs.reduce((s, r) => s + r.costUsd, 0);
  const durationSec = runs.reduce((s, r) => s + r.durationSec, 0);
  return {
    numTurns,
    costUsd: Math.round(costUsd * 1e4) / 1e4,
    durationSec: Math.round(durationSec * 10) / 10,
  };
}

function makeNode(id: NodeId, status: NodeStatus, extra: Partial<PipelineNode> = {}): PipelineNode {
  return {
    id,
    label: NODE_LABELS[id] ?? id,
    status,
    runningSec: null,
    waitingSec: null,
    quietSec: null,
    reviseCount: null,
    sendBackCount: null,
    metrics: null,
    ...extra,
  };
}

/** 段の節。countSendBack なら差し戻しの回数（2回目以降の実行の数）も数える（開発フローの実装）。 */
function stageNode(
  stage: Stage,
  record: RunRecord,
  runningStage: Stage | null,
  extraNode: Partial<PipelineNode> = {},
  countSendBack = false,
): PipelineNode {
  const runs = record.stageRuns.filter((r) => r.stage === stage);
  const last = runs.at(-1);
  const status: NodeStatus =
    runningStage === stage ? 'running' : last === undefined ? 'pending' : last.isError ? 'failed' : 'done';
  const extra: Partial<PipelineNode> = { metrics: sumMetrics(runs), ...extraNode };
  if (countSendBack) {
    extra.sendBackCount = runs.filter((r) => r.attempt !== null && r.attempt >= 2).length;
  }
  return makeNode(stage, status, extra);
}

/** 開発フローで、確認のあとに続く段。どれかが動いていれば、その確認は通り過ぎている。 */
const STAGES_AFTER_REVIEW: Readonly<Record<'requirements' | 'design' | 'red', readonly DevStage[]>> = {
  requirements: ['design', 'red', 'implement', 'test'],
  design: ['red', 'implement', 'test'],
  red: ['implement', 'test'],
};

/** 確認の節。laterStages は確認のあとに続く段。 */
function reviewNode(id: NodeId, stage: Stage, laterStages: readonly Stage[], record: RunRecord): PipelineNode {
  const reviews = record.reviews.filter((r) => r.stage === stage);
  const last = reviews.at(-1)?.action;
  // 確認の記録がないまま先の段が動いた＝確認を省いた（--yes、--from で前回の続きから）
  const passed = record.stageRuns.some((r) => laterStages.includes(r.stage));
  const status: NodeStatus =
    last === 'approved' ? 'done' : last === 'quit' ? 'failed' : last === undefined && passed ? 'skipped' : 'pending';
  return makeNode(id, status, { label: '確認', reviseCount: reviews.filter((r) => r.action === 'revise').length });
}

function verdictNode(record: RunRecord, runningStage: Stage | null): PipelineNode {
  const last = record.verdicts.at(-1);
  // 差し戻しのやり直し（実装・検証が動いている、または前回の判定より後の回の実装がある）なら、前回の判定はもう古い
  const latestImplement = record.stageRuns
    .filter((r) => r.stage === 'implement')
    .reduce((max, r) => Math.max(max, r.attempt ?? 0), 0);
  const retrying =
    runningStage === 'implement' ||
    runningStage === 'test' ||
    (last !== undefined && last.attempt !== null && latestImplement > last.attempt);
  const status: NodeStatus =
    last === undefined || retrying ? 'pending' : last.status === 'pass' ? 'done' : 'failed';
  return makeNode('verdict', status);
}

function finalNode(record: RunRecord): PipelineNode {
  const status: NodeStatus = record.final === null ? 'pending' : record.final === 'PASSED' ? 'done' : 'failed';
  return makeNode('final', status);
}

/** 依頼メモの節の状態。写しの項目が新旧どちらの形でも（項目が無くても）例外なく決まる。 */
function inputStatus(snapshot: WorkDirSnapshot): NodeStatus {
  return isArtifactReady(snapshot.artifacts['00_input.md']) ? 'done' : 'pending';
}

/** 開発フローの11節（判定と差し戻しあり）。 */
function buildDevNodes(snapshot: WorkDirSnapshot, record: RunRecord, runningStage: Stage | null): PipelineNode[] {
  return [
    makeNode('input', inputStatus(snapshot)),
    stageNode('requirements', record, runningStage),
    reviewNode('review:requirements', 'requirements', STAGES_AFTER_REVIEW.requirements, record),
    stageNode('design', record, runningStage),
    reviewNode('review:design', 'design', STAGES_AFTER_REVIEW.design, record),
    stageNode('red', record, runningStage),
    reviewNode('review:red', 'red', STAGES_AFTER_REVIEW.red, record),
    stageNode('implement', record, runningStage, {}, true),
    stageNode('test', record, runningStage),
    verdictNode(record, runningStage),
    finalNode(record),
  ];
}

/**
 * パイプの節：依頼メモ → 段 →（確認）→ … → 完了。差し戻しはないので判定の節もない。
 * 確認の節は review = true の段のあと。review を持たない古い記録では、確認の記録がある段のあとだけ。
 */
function buildPipeNodes(
  snapshot: WorkDirSnapshot,
  record: RunRecord,
  stages: StageDef[],
  runningStage: Stage | null,
): PipelineNode[] {
  const nodes = [makeNode('input', inputStatus(snapshot), { label: '依頼メモ' })];
  stages.forEach((s, i) => {
    nodes.push(stageNode(s.name, record, runningStage, { label: s.label }));
    const hasReview = s.review ?? record.reviews.some((r) => r.stage === s.name);
    if (hasReview) {
      const later = stages.slice(i + 1).map((x) => x.name);
      nodes.push(reviewNode(`review:${s.name}`, s.name, later, record));
    }
  });
  nodes.push(finalNode(record));
  return nodes;
}

function stageLabelsOf(record: RunRecord, dev: boolean): Readonly<Record<Stage, string>> {
  if (dev) return STAGE_LABELS;
  return Object.fromEntries((record.stages ?? []).map((s) => [s.name, s.label]));
}

// ---- 時間（D0017）：今の時刻は引数 clock で受ける -----------------------------------

/** 記録の時刻の文字を UTC のミリ秒にする。読めなければ null。 */
function instantOf(text: string | null, clock: ViewClock | undefined): number | null {
  return text === null ? null : parseInstant(text, clock?.localOffsetMin ?? 0);
}

/** 今の時刻からの経過秒。時計や記録の時刻が無ければ null。 */
function secondsSince(text: string | null, clock: ViewClock | undefined): number | null {
  if (clock === undefined) return null;
  const from = instantOf(text, clock);
  return from === null ? null : elapsedSec(from, clock.nowMs);
}

/** 止まっているかもしれない印の対象か（D0021）：state.json がオブジェクトとして読め、final が無く、前の実行（archive/）でない run。 */
function staleEligible(snapshot: WorkDirSnapshot, record: RunRecord): boolean {
  return snapshot.previous !== true && record.final === null && isReadableState(snapshot.stateJson);
}

/**
 * 動いている段の、最後の更新からの秒。基準は run の全ログ（名前の読めるもの）のうち更新時刻が読める最新。
 * 動いているログが無い・そのログ自身の更新時刻が読めない・時計が無い・「今」が壊れているなら null（ほかのログの時刻で代わりにしない）。
 */
function quietSecOf(logs: ReadLog[], running: ReadLog | null, clock: ViewClock | undefined): number | null {
  if (running === null || running.mtimeMs === null || clock === undefined) return null;
  return quietSecAt(latestMtime(logs.map((l) => l.mtimeMs)), clock.nowMs);
}

/** 動いている段の節に runningSec と quietSec、確認待ちの確認の節に waitingSec を付ける（付けられるときだけ）。 */
function withLiveSeconds(
  nodes: PipelineNode[],
  runningLog: ReadLog | null,
  pending: RunRecord['pendingReview'],
  quietSec: number | null,
  clock: ViewClock | undefined,
): PipelineNode[] {
  const runningSec = runningLog === null ? null : secondsSince(runningLog.log.startedAt, clock);
  // 動いている段があるあいだは、確認待ちの印は古い。待ち時間は出さない
  const waitingStage = runningLog === null && pending !== null ? pending.stage : null;
  const waitingSec = waitingStage === null ? null : secondsSince(pending?.since ?? null, clock);
  return nodes.map((node) => {
    // Prompt の at が無い古い記録（runningSec が null）でも、更新なしの印は出す
    if ((runningSec !== null || quietSec !== null) && node.id === runningLog?.name.stage) {
      return { ...node, ...(runningSec !== null ? { runningSec } : {}), ...(quietSec !== null ? { quietSec } : {}) };
    }
    if (waitingSec !== null && node.id === `${REVIEW_NODE_PREFIX}${waitingStage}` && node.status === 'pending') {
      return { ...node, waitingSec };
    }
    return node;
  });
}

/** 全体の経過。終わった・止まっている実行は updated_at までの固定。動いている・確認待ちは「今」まで数え上げる。 */
function overallElapsed(
  record: RunRecord,
  runningLog: ReadLog | null,
  nodes: PipelineNode[],
  clock: ViewClock | undefined,
): Elapsed | null {
  const from = instantOf(record.startedAt, clock);
  if (from === null) return null;
  const active = record.final === null && (runningLog !== null || record.pendingReview !== null);
  if (active && clock !== undefined) {
    // 段の始まりの時刻・待ち始めの時刻が読めない記録（古い版）では数え上げない（FR-18）
    const counting = nodes.some((n) => n.runningSec !== null || n.waitingSec !== null);
    return counting ? { seconds: elapsedSec(from, clock.nowMs), live: true } : null;
  }
  const to = instantOf(record.updatedAt, clock);
  return to === null ? null : { seconds: elapsedSec(from, to), live: false };
}

/** 実行が2回以上ある段の、回ごとの時間と合計。段は最初に出た順、回は通し番号の順。 */
function buildStageTimes(record: RunRecord, labels: Readonly<Record<Stage, string>>): StageTimes[] {
  const byStage = new Map<Stage, StageRun[]>();
  for (const run of [...record.stageRuns].sort((a, b) => a.seq - b.seq)) {
    byStage.set(run.stage, [...(byStage.get(run.stage) ?? []), run]);
  }
  const out: StageTimes[] = [];
  for (const [stage, runs] of byStage) {
    if (runs.length < 2) continue;
    const total = runs.reduce((s, r) => s + r.durationSec, 0);
    out.push({
      stage,
      label: labels[stage] ?? stage,
      runs: runs.map(({ seq, attempt, durationSec }) => ({ seq, attempt, durationSec })),
      totalSec: Math.round(total * 10) / 10,
    });
  }
  return out;
}

/** 使ったエージェント・スキル・道具の表。段のログの呼び出しと、記録の段の受け持ちから作る（時系列と同じ段の表示名・受け持ちの決め方）。 */
function buildTools(logs: ReadLog[], runningLog: ReadLog | null, record: RunRecord, stageLabels: Readonly<Record<Stage, string>>): ToolsTable {
  return buildToolsTable({
    logs: logs.map(({ name, log }) => ({ seq: name.seq, stage: name.stage, attempt: name.attempt, agent: log.agent, calls: log.calls ?? [] })),
    runs: record.stageRuns,
    running:
      runningLog === null
        ? null
        : { seq: runningLog.name.seq, stage: runningLog.name.stage, attempt: runningLog.name.attempt, agent: runningLog.log.agent },
    labels: stageLabels,
    driver: record.hasDriver,
  });
}

export function buildPipelineView(snapshot: WorkDirSnapshot, clock?: ViewClock, options?: BuildViewOptions): PipelineView {
  const withTools = options?.tools !== false;
  const record = parseRunRecord(snapshot.stateJson);
  const dev = isDevRecord(record);
  const stageLabels = stageLabelsOf(record, dev);
  const logs = readLogs(snapshot.stageLogs, withTools);
  const runningLog = findRunningLog(logs, record);
  const runningStage = runningLog?.name.stage ?? null;
  const shown = runningLog ?? logs.at(-1) ?? null;
  const baseNodes = dev
    ? buildDevNodes(snapshot, record, runningStage)
    : buildPipeNodes(snapshot, record, record.stages ?? [], runningStage);
  // 印の元は 1 つ。節・時系列の帯・一覧の行は、どれもこの値から取る（節が作られない段名でも食い違わない）
  const quietSec = staleEligible(snapshot, record) ? quietSecOf(logs, runningLog, clock) : null;
  const nodes = withLiveSeconds(baseNodes, runningLog, record.pendingReview, quietSec, clock);

  // 項目の有無だけ見る（値が新旧どちらの形でも同じ。symlink の 00_input.md は写しに項目が無い）
  const noRecords =
    snapshot.stateJson === null && logs.length === 0 && !('00_input.md' in snapshot.artifacts)
      ? { message: NO_RECORDS_MESSAGE, workDir: snapshot.workDir }
      : null;

  return {
    nodes,
    stageLabels,
    runningStage,
    terminal: shown ? { source: shown.name, items: shown.log.items } : { source: null, items: [] },
    totalCostUsd: record.totalCostUsd,
    final: record.final,
    artifacts: buildArtifactList(snapshot.artifacts, artifactDefsFor(record), clock),
    waiting: record.final === null && runningStage === null && record.stageRuns.length >= 1,
    noRecords,
    usage: buildUsage(record, stageLabels),
    pendingReview:
      record.pendingReview === null
        ? null
        : {
            stage: record.pendingReview.stage,
            label: stageLabels[record.pendingReview.stage] ?? record.pendingReview.stage,
            doc: record.pendingReview.doc,
          },
    warnings: record.warnings,
    sendBacks: buildSendBacks(record, stageLabels),
    revisions: buildRevisions(record, stageLabels),
    elapsed: overallElapsed(record, runningLog, nodes, clock),
    quietSec,
    stageTimes: buildStageTimes(record, stageLabels),
    gantt: buildGantt({
      record,
      logs: logs.map(({ name, log }) => ({ seq: name.seq, stage: name.stage, attempt: name.attempt, startedAt: log.startedAt, agent: log.agent })),
      running:
        runningLog === null
          ? null
          : {
              seq: runningLog.name.seq,
              stage: runningLog.name.stage,
              attempt: runningLog.name.attempt,
              startedAt: runningLog.log.startedAt,
              agent: runningLog.log.agent,
            },
      labels: stageLabels,
      clock,
      quietSec,
    }),
    tools: withTools ? buildTools(logs, runningLog, record, stageLabels) : null,
  };
}
