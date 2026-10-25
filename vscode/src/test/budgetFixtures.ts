// 段の費用と上限（D0051）のテストで使う、記録と図の状態の組み立て。
// vscode/src/test/fixtures.ts は編集せず（別の PR が触る）、ここに足す。
// runs[] に重ねる鍵の名前（max_budget_usd・resumed）は、本体と共通の表 tests/fixtures/budget_record.json の keys と同じ。
// 同じであることは domain/runRecordBudget.test.ts が確かめる（手で同じ語を 2 度打たずに、本体が書く鍵を拡張が読むことを守るため）。
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { PipelineNode, PipelineView, StageLogFile, ViewClock, WorkDirSnapshot } from '../domain/pipelineView.ts';
import { parseRunRecord } from '../domain/runRecord.ts';
import type { RunRecord, StageRun } from '../domain/runRecord.ts';
import { BASE_AT } from './liveFixtures.ts';
import { assistantText, logText, promptLine, snapshot, stageRunEntry, stateJson } from './fixtures.ts';

const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'tests', 'fixtures');

// ---- 本体と共通の表 ----

/** 共通の表 tests/fixtures/budget_record.json の 1 件。written は本体が runs[] の要素に足す鍵、read は拡張が読んだ StageRun の maxBudgetUsd・resumed。 */
export interface BudgetCase {
  memo: string;
  limit: number | null;
  resume: boolean;
  written: Record<string, unknown>;
  read: { maxBudgetUsd: number | null; resumed: boolean };
}
export interface BudgetTable {
  keys: string[];
  cases: BudgetCase[];
}
/** 共通の表を読む（読むだけで書かない）。 */
export function loadBudgetTable(): BudgetTable {
  return JSON.parse(readFileSync(path.join(FIXTURES, 'budget_record.json'), 'utf8')) as BudgetTable;
}

// ---- runs[] の要素 ----

type StageRunParams = Parameters<typeof stageRunEntry>[0];

export interface BudgetRunParams extends StageRunParams {
  /** runs[].max_budget_usd。省くと鍵を持たない。null や壊れた値（文字・真偽など）も入れて試せる */
  maxBudgetUsd?: unknown;
  /** runs[].resumed。省くと鍵を持たない */
  resumed?: unknown;
  /** runs[].subtype。省くと stageRunEntry の 'success'。null や壊れた値も入れて試せる */
  subtype?: unknown;
  /** cost_usd を壊れた値（負・文字・null）にして試す。省くと costUsd */
  rawCostUsd?: unknown;
  /** 取り除く鍵（項目なしの記録を試す） */
  omit?: readonly string[];
}

/** 段の実行の要素（stageRunEntry の結果に、上限・続きの会話の印・結果の種類を重ねる）。 */
export function budgetRun(p: BudgetRunParams): Record<string, unknown> {
  const { maxBudgetUsd, resumed, subtype, rawCostUsd, omit, ...base } = p;
  const entry: Record<string, unknown> = { ...(stageRunEntry(base) as Record<string, unknown>) };
  if (maxBudgetUsd !== undefined) entry.max_budget_usd = maxBudgetUsd;
  if (resumed !== undefined) entry.resumed = resumed;
  if (subtype !== undefined) entry.subtype = subtype;
  if (rawCostUsd !== undefined) entry.cost_usd = rawCostUsd;
  for (const key of omit ?? []) delete entry[key];
  return entry;
}

/** 上限・続きの会話の印・結果の種類を取り除いた要素（「それらを除いた同じ記録」を作る）。 */
export function withoutBudgetKeys(entry: object): object {
  const copy: Record<string, unknown> = { ...(entry as Record<string, unknown>) };
  delete copy.max_budget_usd;
  delete copy.resumed;
  delete copy.subtype;
  return copy;
}

// ---- 記録・図の状態 ----

/** パイプの段の並び（state.json の stages）。表示の名前は名前と同じ。 */
export function pipeStages(names: readonly string[]): object[] {
  return names.map((name) => ({ name, label: name, output: `${name}.md`, review: false }));
}

export interface BudgetViewOptions {
  /** パイプの名前（省くと開発フローの記録） */
  pipe?: string;
  /** 段の並び（pipe と一緒に渡す） */
  stages?: unknown;
  final?: string | null;
  totalCostUsd?: number;
  usageSummary?: unknown;
  pendingReview?: unknown;
  stageLogs?: StageLogFile[];
  clock?: ViewClock;
}

/** 記録の写し（runs の要素を並べた state.json）。 */
export function budgetSnapshot(runs: readonly object[], opts: BudgetViewOptions = {}): WorkDirSnapshot {
  return snapshot({
    stateJson: stateJson({
      runs: [...runs],
      ...(opts.pipe === undefined ? {} : { pipe: opts.pipe }),
      ...(opts.stages === undefined ? {} : { stages: opts.stages }),
      ...(opts.final === undefined ? {} : { final: opts.final }),
      ...(opts.totalCostUsd === undefined ? {} : { totalCostUsd: opts.totalCostUsd }),
      ...(opts.usageSummary === undefined ? {} : { usageSummary: opts.usageSummary }),
      ...(opts.pendingReview === undefined ? {} : { pendingReview: opts.pendingReview }),
    }),
    stageLogs: opts.stageLogs ?? [],
    artifacts: { '00_input.md': 'メモ' },
  });
}

/** 記録の写しから図の状態を作る。 */
export function budgetView(runs: readonly object[], opts: BudgetViewOptions = {}): PipelineView {
  return buildPipelineView(budgetSnapshot(runs, opts), opts.clock);
}

/** 記録を読んだもの。 */
export function budgetRecord(runs: readonly object[], opts: BudgetViewOptions = {}): RunRecord {
  return parseRunRecord(budgetSnapshot(runs, opts).stateJson);
}

/** 段の実行の並び（parseRunRecord が読んだもの）。 */
export function stageRunsOf(runs: readonly object[], opts: BudgetViewOptions = {}): StageRun[] {
  return budgetRecord(runs, opts).stageRuns;
}

/** 動いている段のログ（Prompt があり、終わっていない）。seq は state.json に載った最大の通し番号より大きくする。 */
export function runningLogFile(seq: number, stage: string, attempt: number | null): StageLogFile {
  const name = `${String(seq).padStart(2, '0')}_${stage}${attempt === null ? '' : `_${attempt}`}.jsonl`;
  return { fileName: name, text: logText([promptLine(stage, BASE_AT), assistantText('作業中')]) };
}

/** 図の状態の節を id で取る。無ければ落とす。 */
export function nodeById(view: PipelineView, id: string): PipelineNode {
  const node = view.nodes.find((n) => n.id === id);
  if (node === undefined) throw new Error(`節 ${id} が図の状態に無い`);
  return node;
}

// ---- 段の実行を直に作る（domain の部品の単体のテスト用。parseRunRecord を通さない） ----

export interface PlainRunParams {
  stage?: string;
  seq?: number;
  attempt?: number | null;
  costUsd?: number;
  maxBudgetUsd?: number | null;
  resumed?: boolean;
  subtype?: string | null;
  isError?: boolean;
}

/**
 * StageRun を直に作る。上限・続きの会話の印・結果の種類は、実装の段で StageRun の型に入るまで、型に頼らず入れる（キャストで型検査を通す）。
 * 既定：上限なし・続きでない・結果の種類は success。
 */
export function plainRun(p: PlainRunParams = {}): StageRun {
  return {
    stage: p.stage ?? 'requirements',
    seq: p.seq ?? 1,
    attempt: p.attempt ?? null,
    note: '',
    numTurns: 1,
    costUsd: p.costUsd ?? 0,
    durationSec: 0,
    isError: p.isError ?? false,
    agent: null,
    sessionId: null,
    review: null,
    tokens: null,
    cacheReuseRate: null,
    maxBudgetUsd: p.maxBudgetUsd ?? null,
    resumed: p.resumed ?? false,
    subtype: p.subtype === undefined ? 'success' : p.subtype,
  } as unknown as StageRun;
}

// ---- 使用量のパネルの「段ごとの費用」の節 ----

/**
 * 本体の文字から「段ごとの費用」の節（<section … data-stage-costs>…</section>。中に別の <section> は入れない）を取り除く。
 * 既存のページの使用量のパネルの SHA-256 を測る前に使う（D0025 の固定。費用の節は仕様で足されるので、節の外が変わっていないことを測る）。
 */
export function stripStageCosts(text: string): string {
  return text.replace(/<section\b[^>]*\sdata-stage-costs\b[^>]*>[\s\S]*?<\/section>/g, '');
}

/** 使用量のパネル（data-detail-panel="usage"）の中身：開きタグのあとから、次の role="tabpanel" か </main> まで。タブの数・位置の添字は使わない。 */
export function usagePanelOf(html: string): string {
  const open = html.indexOf('data-detail-panel="usage"');
  assert.ok(open >= 0, '使用量のパネルの枠がある');
  const tagEnd = html.indexOf('>', open) + 1;
  const next = html.indexOf('role="tabpanel"', tagEnd);
  const main = html.indexOf('</main>', tagEnd);
  const end = next >= 0 && (main < 0 || next < main) ? next : main;
  return html.slice(tagEnd, end < 0 ? undefined : end);
}

/** 「段ごとの費用」の節（data-stage-costs の印の <section>）。無ければ null。 */
export function stageCostsSection(html: string): string | null {
  return /<section\b[^>]*\sdata-stage-costs\b[^>]*>[\s\S]*?<\/section>/.exec(html)?.[0] ?? null;
}

const unescapeText = (s: string): string => s.replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
/** タグを除いて文字参照を戻した文字。 */
export const plainText = (s: string): string => unescapeText(s.replace(/<[^>]*>/g, '')).trim();

/** 費用の表の読み：見出しの行（<td> を持たない行）・合計の行（最初のセルが「合計」）・それ以外の行のセルの文字。 */
export interface CostTable {
  head: string[];
  rows: string[][];
  total: string[] | null;
}
export function costTableOf(section: string): CostTable {
  const all = [...section.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)].map((tr) => ({
    hasTd: /<td\b/.test(tr[1]!),
    cells: [...tr[1]!.matchAll(/<t[dh]\b[^>]*>([\s\S]*?)<\/t[dh]>/g)].map((c) => plainText(c[1]!)),
  }));
  const head = all.find((r) => !r.hasTd)?.cells ?? [];
  const body = all.filter((r) => r.hasTd).map((r) => r.cells);
  return { head, rows: body.filter((r) => r[0] !== '合計'), total: body.find((r) => r[0] === '合計') ?? null };
}

// ---- 図（SVG）の節の読み方 ----

/** 節 id の <g>…</g>（節の中に <g> は入れ子にならない）。 */
export function nodeG(svg: string, id: string): string {
  const at = svg.indexOf(`data-node="${id}"`);
  assert.ok(at >= 0, `節 ${id} がある`);
  const start = svg.lastIndexOf('<g class="node ', at);
  const end = svg.indexOf('</g>', at);
  assert.ok(start >= 0 && end > at, `節 ${id} の <g> が閉じている`);
  return svg.slice(start, end + '</g>'.length);
}
export const classesOf = (g: string): string[] => (/^<g class="([^"]*)"/.exec(g)?.[1] ?? '').split(' ');
export const titleOf = (g: string): string => /<title>([\s\S]*?)<\/title>/.exec(g)?.[1] ?? '';
/** 節の <text> の文字（中のタグは除く）。 */
export const textsOf = (g: string): string[] => [...g.matchAll(/<text\b[^>]*>([\s\S]*?)<\/text>/g)].map((m) => m[1]!.replace(/<[^>]*>/g, ''));
