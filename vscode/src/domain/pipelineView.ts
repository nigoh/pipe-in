// 図の状態：記録の写しだけから組み立てる。ファイル・時計・乱数・vscode に触れない。
import { buildArtifactList, isArtifactReady } from './artifacts.ts';
import type { ArtifactEntry, ArtifactName } from './artifacts.ts';
import { parseRunRecord } from './runRecord.ts';
import type { RunRecord, StageRun, TokenCounts, UsageSummary } from './runRecord.ts';
import type { Stage } from './stage.ts';
import { parseStageLog, parseStageLogName } from './stageLog.ts';
import type { OutputItem, StageLog, StageLogName } from './stageLog.ts';

/** 記録の写し。ファイルの中身だけ。基盤の層が作る。 */
export interface WorkDirSnapshot {
  /** 表示用のパス（記録なしの表示に出す） */
  workDir: string;
  /** state.json の中身。ないなら null */
  stateJson: string | null;
  /** logs/ の *.jsonl（ファイル名だけ＋中身）。順は問わない */
  stageLogs: { fileName: string; text: string }[];
  /** ある成果物の中身。ないものは鍵を持たない */
  artifacts: Partial<Record<ArtifactName, string>>;
}

export type NodeStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped';
export const NODE_STATUS_LABELS: Readonly<Record<NodeStatus, string>> = {
  pending: 'まだ',
  running: '動いている',
  done: '完了',
  failed: '失敗',
  skipped: '省略',
};

export type NodeId =
  | 'input'
  | 'requirements'
  | 'review:requirements'
  | 'design'
  | 'review:design'
  | 'red'
  | 'review:red'
  | 'implement'
  | 'test'
  | 'verdict'
  | 'final';

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

export const NODE_LABELS: Readonly<Record<NodeId, string>> = {
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

export interface PipelineNode {
  id: NodeId;
  label: string;
  status: NodeStatus;
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

export interface PipelineView {
  /** 常に11個、NODE_ORDER の順 */
  nodes: PipelineNode[];
  runningStage: Stage | null;
  terminal: TerminalView;
  totalCostUsd: number;
  final: string | null;
  artifacts: ArtifactEntry[];
  /** FR-13 */
  waiting: boolean;
  /** FR-14 */
  noRecords: { message: string; workDir: string } | null;
  /** 使用量（devpipe 0.2 から）。usage_summary のない記録では null */
  usage: UsageView | null;
}

/** 使用量の表の1行：段の実行1回分。metrics のない古い段の実行は tokens が null。 */
export interface UsageRow {
  seq: number;
  stage: Stage;
  attempt: number | null;
  tokens: TokenCounts | null;
  cacheReuseRate: number | null;
}

export interface UsageView {
  summary: UsageSummary;
  /** 通し番号の順 */
  rows: UsageRow[];
}

function buildUsage(record: RunRecord): UsageView | null {
  if (record.usage === null) return null;
  const rows = [...record.stageRuns]
    .sort((a, b) => a.seq - b.seq)
    .map(({ seq, stage, attempt, tokens, cacheReuseRate }) => ({ seq, stage, attempt, tokens, cacheReuseRate }));
  return { summary: record.usage, rows };
}

interface ReadLog {
  name: StageLogName;
  log: StageLog;
  fileName: string;
}

/** 名前の読めるログだけを (seq, fileName) の昇順に並べる。 */
function readLogs(stageLogs: WorkDirSnapshot['stageLogs']): ReadLog[] {
  const logs: ReadLog[] = [];
  for (const { fileName, text } of stageLogs) {
    const name = parseStageLogName(fileName);
    if (name) logs.push({ name, log: parseStageLog(text), fileName });
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
  return { id, label: NODE_LABELS[id], status, reviseCount: null, sendBackCount: null, metrics: null, ...extra };
}

function stageNode(stage: Stage, record: RunRecord, runningStage: Stage | null): PipelineNode {
  const runs = record.stageRuns.filter((r) => r.stage === stage);
  const last = runs.at(-1);
  const status: NodeStatus =
    runningStage === stage ? 'running' : last === undefined ? 'pending' : last.isError ? 'failed' : 'done';
  const extra: Partial<PipelineNode> = { metrics: sumMetrics(runs) };
  if (stage === 'implement') {
    extra.sendBackCount = runs.filter((r) => r.attempt !== null && r.attempt >= 2).length;
  }
  return makeNode(stage, status, extra);
}

/** 確認のあとに続く段。どれかが動いていれば、その確認は通り過ぎている。 */
const STAGES_AFTER_REVIEW: Readonly<Record<'requirements' | 'design' | 'red', readonly Stage[]>> = {
  requirements: ['design', 'red', 'implement', 'test'],
  design: ['red', 'implement', 'test'],
  red: ['implement', 'test'],
};

function reviewNode(id: NodeId, stage: 'requirements' | 'design' | 'red', record: RunRecord): PipelineNode {
  const reviews = record.reviews.filter((r) => r.stage === stage);
  const last = reviews.at(-1)?.action;
  // 確認の記録がないまま先の段が動いた＝確認を省いた（--yes、--from で前回の続きから）
  const passed = record.stageRuns.some((r) => STAGES_AFTER_REVIEW[stage].includes(r.stage));
  const status: NodeStatus =
    last === 'approved' ? 'done' : last === 'quit' ? 'failed' : last === undefined && passed ? 'skipped' : 'pending';
  return makeNode(id, status, { reviseCount: reviews.filter((r) => r.action === 'revise').length });
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

function buildNodes(snapshot: WorkDirSnapshot, record: RunRecord, runningStage: Stage | null): PipelineNode[] {
  return [
    makeNode('input', isArtifactReady(snapshot.artifacts['00_input.md']) ? 'done' : 'pending'),
    stageNode('requirements', record, runningStage),
    reviewNode('review:requirements', 'requirements', record),
    stageNode('design', record, runningStage),
    reviewNode('review:design', 'design', record),
    stageNode('red', record, runningStage),
    reviewNode('review:red', 'red', record),
    stageNode('implement', record, runningStage),
    stageNode('test', record, runningStage),
    verdictNode(record, runningStage),
    finalNode(record),
  ];
}

export function buildPipelineView(snapshot: WorkDirSnapshot): PipelineView {
  const record = parseRunRecord(snapshot.stateJson);
  const logs = readLogs(snapshot.stageLogs);
  const runningLog = findRunningLog(logs, record);
  const runningStage = runningLog?.name.stage ?? null;
  const shown = runningLog ?? logs.at(-1) ?? null;

  const noRecords =
    snapshot.stateJson === null && logs.length === 0 && !('00_input.md' in snapshot.artifacts)
      ? { message: NO_RECORDS_MESSAGE, workDir: snapshot.workDir }
      : null;

  return {
    nodes: buildNodes(snapshot, record, runningStage),
    runningStage,
    terminal: shown ? { source: shown.name, items: shown.log.items } : { source: null, items: [] },
    totalCostUsd: record.totalCostUsd,
    final: record.final,
    artifacts: buildArtifactList(snapshot.artifacts),
    waiting: record.final === null && runningStage === null && record.stageRuns.length >= 1,
    noRecords,
    usage: buildUsage(record),
  };
}
