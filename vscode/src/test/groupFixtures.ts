// 並列の枠（D0063）の記録と図の状態のテストで使う、記録・段のログの組み立て。
// vscode/src/test/fixtures.ts・checkFixtures.ts は編集せず、ここに足す。
// 本体が書く鍵（stages[].group）の名前は、本体と共通の表 tests/fixtures/group_record.json の keys と同じ。
// 同じであることは domain/runRecordGroup.test.ts が確かめる（手で同じ語を 2 度打たずに、本体が書く鍵を拡張が読むことを守るため）。
// StageDef.group・PipelineView.frames などの新しい項目は、実装の段で型に入るまで、型に頼らず読む（下の *Of 関数）。
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { PipelineNode, PipelineView, StageLogFile } from '../domain/pipelineView.ts';
import { parseRunRecord } from '../domain/runRecord.ts';
import type { RunRecord } from '../domain/runRecord.ts';
import { assistantText, logText, promptLine, resultLine, stageRunEntry } from './fixtures.ts';
import { checkSnapshot, checkView, runEntry } from './checkFixtures.ts';
import type { CheckViewOptions } from './checkFixtures.ts';
import { BASE_AT } from './liveFixtures.ts';

export { runEntry };

const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'tests', 'fixtures');

// ---- 本体と共通の表 ----

/** 共通の表 tests/fixtures/group_record.json の 1 件。written は本体が書く形、read は拡張が読む形（段の名前 → group。null は項目なし／null）。 */
export interface GroupCase {
  memo: string;
  stages: { name: string; group?: string }[];
  written: { group: Record<string, string | null> };
  read: { group: Record<string, string | null> };
}
export interface GroupTable {
  keys: string[];
  cases: GroupCase[];
}
/** 共通の表を読む（読むだけで書かない）。 */
export function loadGroupTable(): GroupTable {
  return JSON.parse(readFileSync(path.join(FIXTURES, 'group_record.json'), 'utf8')) as GroupTable;
}

// ---- state.json の stages[] の要素 ----

export interface GroupStageParams {
  /** 表示の名前。省くと `${name}の段` */
  label?: string;
  review?: boolean;
  /** stages[].check（判定の設定） */
  check?: unknown;
}
/** state.json の stages[] の要素。group は渡したときだけ鍵を持つ（壊れた値も入れて試せる。undefined は鍵なし）。 */
export function gStage(name: string, group?: unknown, p: GroupStageParams = {}): Record<string, unknown> {
  return {
    name,
    label: p.label ?? `${name}の段`,
    output: `${name}.md`,
    review: p.review ?? false,
    ...(p.check === undefined ? {} : { check: p.check }),
    ...(group === undefined ? {} : { group }),
  };
}

/** 前の段 survey → 枠 draw（flow・klass）→ 次の段 report のパイプの段の並び。 */
export const GROUP_STAGES = [gStage('survey'), gStage('flow', 'draw'), gStage('klass', 'draw'), gStage('report')];

/** 枠 draw の中が 4 段（折り返しを見る）のパイプの段の並び。 */
export const GROUP_STAGES_4 = [gStage('survey'), gStage('a', 'draw'), gStage('b', 'draw'), gStage('c', 'draw'), gStage('d', 'draw'), gStage('report')];

// ---- 段のログ ----

/** 終わった段のログ（Prompt・本文・終わりの行がある）。text は出力の本文。 */
export function doneLog(seq: number, stage: string, attempt: number | null, text = `${stage}の出力`): StageLogFile {
  const name = `${String(seq).padStart(2, '0')}_${stage}${attempt === null ? '' : `_${attempt}`}.jsonl`;
  return { fileName: name, text: logText([promptLine(stage, BASE_AT), assistantText(text), resultLine()]) };
}

/** 動いている段のログ（Prompt があり、終わりの行が無い）。 */
export function liveLog(seq: number, stage: string, attempt: number | null = null, text = `${stage}を作業中`): StageLogFile {
  const name = `${String(seq).padStart(2, '0')}_${stage}${attempt === null ? '' : `_${attempt}`}.jsonl`;
  return { fileName: name, text: logText([promptLine(stage, BASE_AT), assistantText(text)]) };
}

/** 失敗した段の実行（runs[] の seq を持つ要素）。 */
export function failedRun(stage: string, seq: number): object {
  return stageRunEntry({ stage, seq, isError: true, costUsd: 0.01, durationSec: 1 });
}

// ---- 記録・図の状態 ----

/** 記録の写しから図の状態を作る（パイプ名は p。stages は渡さなければ GROUP_STAGES）。 */
export function groupView(runs: readonly object[], opts: CheckViewOptions = {}): PipelineView {
  return checkView(runs, { pipe: 'p', stages: GROUP_STAGES, ...opts });
}

/** 記録を読んだもの（stages は渡さなければ GROUP_STAGES）。 */
export function groupRecord(runs: readonly object[], opts: CheckViewOptions = {}): RunRecord {
  return parseRunRecord(checkSnapshot(runs, { pipe: 'p', stages: GROUP_STAGES, ...opts }).stateJson);
}

// ---- 新しい項目の読み（型に入るまで、型に頼らず読む） ----

/** 枠の 1 つ（設計 FrameView）の形。 */
export interface FrameLike {
  name: string;
  status: string;
  members: string[];
  nodeIds: string[];
}
/** PipelineView.frames。項目が無ければ undefined（まだ作っていない）。 */
export const framesOf = (view: PipelineView): FrameLike[] | undefined => (view as unknown as { frames?: FrameLike[] }).frames;
/** 枠の名前・中の段・中の節の id だけ（状態は別に比べる）。 */
export const frameShapes = (view: PipelineView): { name: string; members: string[]; nodeIds: string[] }[] | undefined =>
  framesOf(view)?.map((f) => ({ name: f.name, members: f.members, nodeIds: f.nodeIds }));
/** 枠の状態だけ（枠の順）。 */
export const frameStatuses = (view: PipelineView): string[] | undefined => framesOf(view)?.map((f) => f.status);
/** PipelineView.runningStages。項目が無ければ undefined。 */
export const runningStagesOf = (view: PipelineView): string[] | undefined => (view as unknown as { runningStages?: string[] }).runningStages;
/** PipelineView.groupLogs。項目が無ければ undefined。 */
export const groupLogsOf = (view: PipelineView): Record<string, { source: unknown; items: unknown[] }> | undefined =>
  (view as unknown as { groupLogs?: Record<string, { source: unknown; items: unknown[] }> }).groupLogs;
/** StageDef.group。項目が無ければ undefined（まだ読んでいない）。 */
export const stageGroupOf = (record: RunRecord, name: string): unknown => {
  const def = record.stages?.find((s) => s.name === name);
  if (def === undefined) throw new Error(`段 ${name} が record.stages に無い`);
  return (def as unknown as { group?: unknown }).group;
};
/** PipelineNode.group（枠の中の段の節だけ）。無ければ undefined。 */
export const nodeGroupOf = (node: PipelineNode): unknown => (node as unknown as { group?: unknown }).group;
/** 出力の本文だけ（OutputItem の text）。 */
export const textsOfItems = (items: readonly { kind: string; text?: string }[]): string[] =>
  items.map((i) => (i.kind === 'text' ? (i.text ?? '') : ''));
