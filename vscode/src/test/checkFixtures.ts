// パイプの判定（check）の記録と図の状態（D0062）のテストで使う、記録の組み立て。
// vscode/src/test/fixtures.ts は編集せず、ここに足す。
// 本体が書く鍵（stages[].check・runs[] の check の attempt）の名前は、本体と共通の表 tests/fixtures/check_record.json の keys と同じ。
// 同じであることは domain/runRecordCheck.test.ts が確かめる（手で同じ語を 2 度打たずに、本体が書く鍵を拡張が読むことを守るため）。
// RunRecord の新しい項目（checks・stages[].check）と PipelineNode.check は、実装の段で型に入るまで、型に頼らず読む（下の *Of 関数）。
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { PipelineNode, PipelineView, StageLogFile, WorkDirSnapshot } from '../domain/pipelineView.ts';
import { parseRunRecord } from '../domain/runRecord.ts';
import type { RunRecord } from '../domain/runRecord.ts';
import { snapshot, stageRunEntry, stateJson } from './fixtures.ts';

const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'tests', 'fixtures');

// ---- 本体と共通の表 ----

/** 共通の表 tests/fixtures/check_record.json の 1 件。written は本体が書く形、read は拡張が読む形。 */
export interface CheckCase {
  memo: string;
  check: { on_fail: string | null; max_retries: number };
  results: ('pass' | 'fail')[];
  exit: string;
  written: { check: { on_fail: string | null; max_retries: number }; attempt: number[] };
  read: { onFail: string | null; maxRetries: number; checks: { attempt: number; status: 'pass' | 'fail' }[] };
}
export interface CheckTable {
  keys: string[];
  cases: CheckCase[];
}
/** 共通の表を読む（読むだけで書かない）。 */
export function loadCheckTable(): CheckTable {
  return JSON.parse(readFileSync(path.join(FIXTURES, 'check_record.json'), 'utf8')) as CheckTable;
}

// ---- state.json の stages[]・runs[] の要素 ----

export interface CheckStageParams {
  name: string;
  /** 表示の名前。省くと `${name}の段` */
  label?: string;
  review?: boolean;
  /** stages[].check。省くと項目なし（判定の無い段・古い記録）。壊れた値（文字・配列・null など）も入れて試せる */
  check?: unknown;
}
/** state.json の stages[] の要素（本体が書く形。check は渡したときだけ）。 */
export function stageDef(p: CheckStageParams): Record<string, unknown> {
  return {
    name: p.name,
    label: p.label ?? `${p.name}の段`,
    output: `${p.name}.md`,
    review: p.review ?? false,
    ...(p.check === undefined ? {} : { check: p.check }),
  };
}

export interface CheckRunParams {
  stage: string;
  status: 'pass' | 'fail';
  /** check.attempt。省くと鍵を持たない（古い記録）。壊れた値も入れて試せる */
  attempt?: unknown;
  summary?: unknown;
  problems?: unknown;
}
/** runs[] の check の要素（本体の LinearPipeline._check が書く形：attempt が先頭の鍵）。 */
export function checkEntry(p: CheckRunParams): { stage: string; check: Record<string, unknown> } {
  return {
    stage: p.stage,
    check: {
      ...(p.attempt === undefined ? {} : { attempt: p.attempt }),
      status: p.status,
      problems: p.problems === undefined ? (p.status === 'fail' ? ['矢印が逆'] : []) : p.problems,
      summary: p.summary === undefined ? (p.status === 'fail' ? '直す点あり' : 'よい') : p.summary,
    },
  };
}

/** 段の実行の要素（seq を持つ要素）。 */
export function runEntry(stage: string, seq: number): object {
  return stageRunEntry({ stage, seq, costUsd: 0.01, durationSec: 1 });
}

// ---- 記録・図の状態 ----

export interface CheckViewOptions {
  pipe?: string;
  stages?: unknown;
  final?: string | null;
  stageLogs?: StageLogFile[];
}

/** 記録の写し（runs の要素を並べた state.json）。 */
export function checkSnapshot(runs: readonly object[], opts: CheckViewOptions = {}): WorkDirSnapshot {
  return snapshot({
    stateJson: stateJson({
      runs: [...runs],
      ...(opts.pipe === undefined ? {} : { pipe: opts.pipe }),
      ...(opts.stages === undefined ? {} : { stages: opts.stages }),
      ...(opts.final === undefined ? {} : { final: opts.final }),
    }),
    stageLogs: opts.stageLogs ?? [],
    artifacts: { '00_input.md': 'メモ' },
  });
}

/** 記録の写しから図の状態を作る。 */
export function checkView(runs: readonly object[], opts: CheckViewOptions = {}): PipelineView {
  return buildPipelineView(checkSnapshot(runs, opts));
}

/** 記録を読んだもの。 */
export function checkRecord(runs: readonly object[], opts: CheckViewOptions = {}): RunRecord {
  return parseRunRecord(checkSnapshot(runs, opts).stateJson);
}

// ---- 新しい項目の読み（型に入るまで、型に頼らず読む） ----

/** RunRecord.checks の 1 件の形（設計 CheckResult）。 */
export interface CheckResultLike {
  stage: string;
  attempt: number | null;
  status: string;
  summary: string;
  problems: string[];
}
/** RunRecord.checks。項目が無ければ undefined（まだ読んでいない）。 */
export const checksOf = (record: RunRecord): CheckResultLike[] | undefined => (record as unknown as { checks?: CheckResultLike[] }).checks;
/** StageDef.check。項目が無ければ undefined（まだ読んでいない）。無い・読めない判定は null。 */
export const stageCheckOf = (record: RunRecord, name: string): unknown => {
  const def = record.stages?.find((s) => s.name === name);
  if (def === undefined) throw new Error(`段 ${name} が record.stages に無い`);
  return (def as unknown as { check?: unknown }).check;
};
/** PipelineNode.check（判定の節だけ）。無ければ undefined。 */
export const nodeCheckOf = (node: PipelineNode): unknown => (node as unknown as { check?: unknown }).check;
