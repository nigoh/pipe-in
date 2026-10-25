// エージェント・スキル・道具の表のモデル（D0050）：段のログの呼び出し（calls）と、/pipe-in の記録の段の受け持ちから、
// 名前ごとの回数・使った段・受け持ちの行の時間を数えて並べる。純粋な関数：読んだあとの形だけから決まり、ファイル・時計に触れない。
// 種類（エージェント・スキル・道具）の見分けと入力の鍵の読みは stageLog.ts に閉じてある。ここは名前の決まりと数え方だけを持つ。
// 段の表示名の書き方と受け持ちの決め方は、時系列（gantt.ts）と同じ関数を使う（表と時系列で、使った段と受け持ちがずれない）。
import { firstLogBySeq, labelOf, ownerOf } from './gantt.ts';
import type { StageRun } from './runRecord.ts';
import { isSafeToken } from './sessionName.ts';
import type { Stage } from './stage.ts';
import type { ToolCall, ToolKind } from './stageLog.ts';

/** 表に出す行の上限。超えた分は並びの後ろから省く */
export const TOOLS_MAX_ROWS = 100;
/** 名前に使えない値（数・null・空・空白入り・101 コードポイント以上など）をまとめる行の名前 */
export const TOOLS_UNREADABLE = '（読めない名前）';
/** 名前の鍵そのものが無い呼び出し（subagent_type や skill を省いた呼び出し）の行の名前 */
export const TOOLS_UNSPECIFIED = '（指定なし）';

/** 名前の長さの粗い上限（コードユニット）。100 コードポイントは最大 200 コードユニットなので、超えれば 101 コードポイント以上と分かる */
const NAME_UNITS_MAX = 200;

/** 段のログ 1 つ（readLogs の順：通し番号、ファイル名）。 */
export interface ToolsLog {
  seq: number;
  stage: Stage;
  /** ログのファイル名の回 */
  attempt: number | null;
  /** 最後の Prompt 行の agent（読める値だけ） */
  agent: string | null;
  calls: readonly ToolCall[];
}

export interface ToolsInput {
  logs: readonly ToolsLog[];
  /** record.stageRuns（seq を持つ要素だけ） */
  runs: readonly Pick<StageRun, 'seq' | 'stage' | 'attempt' | 'agent' | 'durationSec'>[];
  /** runs[] に無い動いているログ。無ければ null */
  running: Pick<ToolsLog, 'seq' | 'stage' | 'attempt' | 'agent'> | null;
  /** 段の表示名の表（view.stageLabels。時系列と同じ元） */
  labels: Readonly<Record<string, string>>;
  /** record.hasDriver */
  driver: boolean;
}

export interface ToolsRow {
  kind: ToolKind;
  /** 表に出す名前（読めない・指定なしの代わりの文字を含む）。生の文字（escape は view） */
  name: string;
  count: number;
  /** 使った段の全部。labelOf の書き方。通し番号の順、同じ実行は 1 つ */
  stages: string[];
  /** 受け持ちの実行のうち runs[] に入っているものの合計。受け持ちの分が無ければ null */
  durationSec: number | null;
}

export interface ToolsTable {
  /** 並べた先頭 TOOLS_MAX_ROWS 行まで */
  rows: ToolsRow[];
  /** 行を省く前の全体の行数 */
  kinds: number;
  /** 行を省く前の回数の合計 */
  total: number;
  /** 省いた行数 */
  omitted: number;
  /** 表に出る行のどれかの durationSec が null でない（時間の列を出す） */
  showTime: boolean;
  /** driver あり＆行 1 以上 → 'A'、driver あり＆行 0 → 'B'、driver なし → null */
  notice: 'A' | 'B' | null;
}

/** 名前の状態。同じ文字の本物の名前と別の行にするため、集計の鍵に入れる。並びの最後のキーにも使う（読める → 指定なし → 読めない） */
type NameState = 'named' | 'unspecified' | 'unreadable';
const STATE_RANK: Readonly<Record<NameState, number>> = { named: 0, unspecified: 1, unreadable: 2 };
const KIND_RANK: Readonly<Record<ToolKind, number>> = { agent: 0, skill: 1, tool: 2 };

interface Entry {
  kind: ToolKind;
  state: NameState;
  name: string;
  count: number;
  /** 通し番号 → 使った段の書き方（先に入れたものを残す） */
  stages: Map<number, string>;
  /** 受け持ちとして数えた段の実行の数（時間を足した数） */
  agentRuns: number;
  durationSec: number;
}

/** コードポイントの順に比べる（JavaScript の既定の比べ方は UTF-16 の順で、U+FF21 と絵文字で食い違うので使わない）。 */
export function compareCodePoints(a: string, b: string): number {
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    const ca = a.codePointAt(i) ?? 0;
    const cb = b.codePointAt(j) ?? 0;
    if (ca !== cb) return ca < cb ? -1 : 1;
    i += ca > 0xffff ? 2 : 1;
    j += cb > 0xffff ? 2 : 1;
  }
  if (i < a.length) return 1;
  return j < b.length ? -1 : 0;
}

/** 集計の行を探す（無ければ作る）。鍵に種類と状態を入れるので、__proto__ などの名前でも壊れず、代わりの文字と同じ文字の本物の名前は別の行になる。 */
function entryFor(entries: Map<string, Entry>, kind: ToolKind, state: NameState, name: string): Entry {
  const key = `${kind}\u0000${state}\u0000${name}`;
  let entry = entries.get(key);
  if (entry === undefined) {
    entry = { kind, state, name, count: 0, stages: new Map(), agentRuns: 0, durationSec: 0 };
    entries.set(key, entry);
  }
  return entry;
}

/** 呼び出し 1 回（または受け持ち 1 回）を数える。使った段は通し番号ごとに 1 つ。 */
function mark(entry: Entry, seq: number, label: string): void {
  entry.count += 1;
  if (!entry.stages.has(seq)) entry.stages.set(seq, label);
}

/** 呼び出しの行を探す。名前の決まり：鍵が無い → 指定なし、読める文字 → そのまま、それ以外 → 読めない名前。 */
function entryForCall(entries: Map<string, Entry>, call: ToolCall): Entry {
  const raw = call.name;
  if (raw === undefined) return entryFor(entries, call.kind, 'unspecified', TOOLS_UNSPECIFIED);
  // 長い値は isSafeToken（コードポイントに分ける）に渡す前に読めない扱いにする。巨大な名前で大きな配列を作らない
  if (typeof raw === 'string' && raw.length <= NAME_UNITS_MAX && isSafeToken(raw)) return entryFor(entries, call.kind, 'named', raw);
  return entryFor(entries, call.kind, 'unreadable', TOOLS_UNREADABLE);
}

function compareEntries(a: Entry, b: Entry): number {
  return (
    KIND_RANK[a.kind] - KIND_RANK[b.kind] ||
    b.count - a.count ||
    compareCodePoints(a.name, b.name) ||
    STATE_RANK[a.state] - STATE_RANK[b.state]
  );
}

function toRow(entry: Entry): ToolsRow {
  return {
    kind: entry.kind,
    name: entry.name,
    count: entry.count,
    stages: Array.from(entry.stages).sort((a, b) => a[0] - b[0]).map(([, label]) => label),
    durationSec: entry.agentRuns > 0 ? entry.durationSec : null,
  };
}

export function buildToolsTable(input: ToolsInput): ToolsTable {
  const { logs, runs, running, labels, driver } = input;
  const entries = new Map<string, Entry>();

  // SDK の呼び出し：段のログごとに数える。結果・成否・parent_tool_use_id は見ない（calls に入っていない）。id で重複を除かない
  for (const log of logs) {
    if (log.calls.length === 0) continue;
    const label = labelOf(log.stage, log.attempt, labels);
    for (const call of log.calls) mark(entryForCall(entries, call), log.seq, label);
  }

  // 段の受け持ち：runs[] の要素ごと（時系列と同じ決め方）に、エージェントの行へ足す。動いている段は回数と使った段だけ（時間は無い）
  const logOf = firstLogBySeq(logs);
  for (const run of [...runs].sort((a, b) => a.seq - b.seq)) {
    const agent = ownerOf(run, logOf);
    if (agent === null) continue;
    const log = logOf.get(run.seq);
    const label = log === undefined ? labelOf(run.stage, run.attempt, labels) : labelOf(log.stage, log.attempt, labels);
    const entry = entryFor(entries, 'agent', 'named', agent);
    mark(entry, run.seq, label);
    entry.agentRuns += 1;
    entry.durationSec += Number.isFinite(run.durationSec) ? Math.max(0, run.durationSec) : 0;
  }
  if (running !== null && running.agent !== null) {
    mark(entryFor(entries, 'agent', 'named', running.agent), running.seq, labelOf(running.stage, running.attempt, labels));
  }

  let total = 0;
  for (const entry of entries.values()) total += entry.count;
  const sorted = Array.from(entries.values()).sort(compareEntries);
  const rows = sorted.slice(0, TOOLS_MAX_ROWS).map(toRow);
  const kinds = sorted.length;
  return {
    rows,
    kinds,
    total,
    omitted: kinds - rows.length,
    // 時間の列は、表に出る行に時間があるときだけ（出ない行の時間のために「—」だけの列を出さない）
    showTime: rows.some((row) => row.durationSec !== null),
    notice: driver ? (kinds >= 1 ? 'A' : 'B') : null,
  };
}
