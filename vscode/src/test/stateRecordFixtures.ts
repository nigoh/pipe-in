// D0080：記録（state.json）の3つの書き手の形を、本体と共通の表 tests/fixtures/state_record.json から組み立てる（budgetFixtures.ts の前例）。
// 表は鍵の並びと値の種類だけを持つ。ここで値の種類（number・null・summary・unavailable・present・absent）を具体的な値にして、
// parseRunRecord・実行の一覧・実行パネルに通す。本体が同じ表のとおりに書くことは tests/test_state_schema.py が確かめる。
// 新しい形の開発用の記録は、tests/fixtures/pipe_dev/ の見本（schema なしの古い記録の例）とは別に、ここで組む。
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { WorkDirSnapshot } from '../domain/pipelineView.ts';
import { DEV_STAGES, snapshot, stageMetricsDict, stageRunEntry, usageSummaryDict } from './fixtures.ts';

const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'tests', 'fixtures');

export type WriterKind = 'sdk' | 'dev' | 'chat';
export const WRITER_KINDS: readonly WriterKind[] = ['sdk', 'dev', 'chat'];

/** 表の 1 種類（書き手 1 つ分）。 */
export interface StateKindRow {
  driver: string | null;
  keys: string[];
  optional_keys: string[];
  total_cost_usd: string;
  usage_summary: string;
  run_cost_usd: string;
  run_metrics: string;
}
export interface StateTable {
  schema: number;
  kinds: Record<WriterKind, StateKindRow>;
  unavailable: { available: boolean; reason: string };
  legacy_dev: { total_cost_usd: number; usage_summary: null; run_cost_usd: number; run_metrics: Record<string, never> };
}

/** 共通の表を読む（読むだけで書かない）。 */
export function loadStateTable(): StateTable {
  return JSON.parse(readFileSync(path.join(FIXTURES, 'state_record.json'), 'utf8')) as StateTable;
}

/** 取れない記録の理由の文（開発用）。本体の文そのものは決めない（空でない文字であることだけが決まり）。 */
export const DEV_REASON = '会話の中で進めたため、費用とトークンは取れません（テスト用の文）';

const SDK_TOTAL = 0.02;
const SDK_RUN_COST = 0.01;

/** 表の「値の種類」を具体的な値にする。 */
function valueOf(kind: string, sdk: unknown): unknown {
  switch (kind) {
    case 'number':
      return sdk;
    case 'null':
      return null;
    case 'summary':
      return usageSummaryDict();
    case 'unavailable':
      return { available: false, reason: DEV_REASON };
    default:
      throw new Error(`表の値の種類が分からない: ${kind}`);
  }
}

export interface StateOptions {
  /** schema の値。省くと表の値（1）。NO_SCHEMA を渡すと鍵ごと持たない（古い記録） */
  schema?: unknown;
  final?: string | null;
  /** 任意の鍵（name など）を足す */
  extra?: Record<string, unknown>;
}
/** schema の鍵を持たない印。 */
export const NO_SCHEMA = Symbol('no-schema');

/** 書き手 kind が書く state.json（表の鍵の並びどおり）を、辞書で返す。段の実行は 2 つ（requirements・design）。 */
export function stateRecord(kind: WriterKind, opts: StateOptions = {}): Record<string, unknown> {
  const table = loadStateTable();
  const row = table.kinds[kind];
  const runs = [1, 2].map((seq) => {
    const entry = stageRunEntry({ stage: seq === 1 ? 'requirements' : 'design', seq, numTurns: kind === 'sdk' ? 3 : 0, durationSec: 3 }) as Record<string, unknown>;
    entry.cost_usd = valueOf(row.run_cost_usd, SDK_RUN_COST);
    if (row.run_metrics === 'present') entry.metrics = stageMetricsDict();
    else delete entry.metrics;
    return entry;
  });
  const parts: Record<string, unknown> = {
    schema: opts.schema === undefined ? table.schema : opts.schema,
    started_at: '2026-11-11T09:58:00',
    updated_at: '2026-11-11T10:05:00',
    pipe: kind === 'dev' ? 'dev' : kind === 'chat' ? 'cp' : 'dev',
    driver: row.driver,
    stages: DEV_STAGES,
    final: opts.final ?? null,
    total_cost_usd: valueOf(row.total_cost_usd, SDK_TOTAL),
    usage_summary: valueOf(row.usage_summary, null),
    pending_review: null,
    warnings: [],
    open: null,
    runs,
    chat: { pipe_dir: '.pipe-in/pipes/pipe-in-cp', steps: 2 },
  };
  const out: Record<string, unknown> = {};
  for (const key of row.keys) {
    if (key === 'schema' && opts.schema === NO_SCHEMA) continue;
    out[key] = parts[key];
  }
  for (const [key, value] of Object.entries(opts.extra ?? {})) out[key] = value;
  return out;
}

/** 書き手 kind が書く state.json の中身（文字列）。 */
export function stateRecordJson(kind: WriterKind, opts: StateOptions = {}): string {
  return JSON.stringify(stateRecord(kind, opts));
}

/** 記録の写し。 */
export function stateRecordSnapshot(kind: WriterKind, opts: StateOptions = {}): WorkDirSnapshot {
  return snapshot({ stateJson: stateRecordJson(kind, opts), artifacts: { '00_input.md': 'メモ' } });
}

/** schema の無い古い開発用の記録（表の legacy_dev：費用 0.0・使用量 null・runs[].cost_usd 0.0・runs[].metrics {}）。 */
export function legacyDevRecord(opts: { final?: string | null } = {}): Record<string, unknown> {
  const table = loadStateTable();
  const legacy = table.legacy_dev;
  const dev = stateRecord('dev', { schema: NO_SCHEMA, ...(opts.final === undefined ? {} : { final: opts.final }) });
  dev.total_cost_usd = legacy.total_cost_usd;
  dev.usage_summary = legacy.usage_summary;
  dev.runs = (dev.runs as Record<string, unknown>[]).map((r) => ({ ...r, cost_usd: legacy.run_cost_usd, metrics: { ...legacy.run_metrics } }));
  return dev;
}

export function legacyDevJson(opts: { final?: string | null } = {}): string {
  return JSON.stringify(legacyDevRecord(opts));
}

export function legacyDevSnapshot(opts: { final?: string | null } = {}): WorkDirSnapshot {
  return snapshot({ stateJson: legacyDevJson(opts), artifacts: { '00_input.md': 'メモ' } });
}

/** schema に入れて試す、数でない・2 以上の値。 */
export const ODD_SCHEMA_VALUES: readonly [string, unknown][] = [
  ['文字の "1"', '1'],
  ['null', null],
  ['真偽 true', true],
  ['配列', []],
  ['2', 2],
  ['小数 1.5', 1.5],
  ['辞書', { a: 1 }],
  ['文字 "x"', 'x'],
];
