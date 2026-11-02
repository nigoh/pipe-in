// 並列の枠の見本の記録（D0063）。確認用ページ（run-panel-group-*）に使う state.json と段のログの中身だけを持つ。
// tests/fixtures/ には見本の記録を足さない。previewPages.ts の buildGroupDir が、一時フォルダに書いて本物の読み取りで読む。
// 記録の鍵（stages[].group）は、本体と拡張が結ぶ共通の表 tests/fixtures/group_record.json の keys から取る（読むだけ）。
// stages[] と runs[] の形は、本体が書く形と同じ（枠の中の段にだけ group を持つ）。

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/** 見本の種類：running ＝ 枠の中の 2 段が同時に動く（4 段で折り返す）、failed ＝ 枠の中に完了・失敗・判定のやり直し、old ＝ group の無い古い記録。 */
export type GroupSampleKind = 'running' | 'failed' | 'old';

/** 見本の「今」の基準：枠の中で動いている段のうち、早く始まったほうの始まりの時刻（at の書き方）。 */
export const GROUP_BASE_AT = '2026-10-17T10:01:00+00:00';

const TABLE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'tests', 'fixtures', 'group_record.json');

/** 共通の表の keys の先頭（段の group の鍵の名前）。 */
function groupKey(): string {
  const table = JSON.parse(readFileSync(TABLE, 'utf8')) as { keys: string[] };
  const key = table.keys[0];
  if (key === undefined) throw new Error('共通の表 group_record.json に keys がありません');
  return key;
}

// 枠の名前は日本語（作業台では日本語の名前もつけられる）
const FRAME = '図を描く';

interface StageSpec {
  name: string;
  label: string;
  group?: boolean;
  check?: { on_fail: string | null; max_retries: number };
}

const STAGES: readonly StageSpec[] = [
  { name: 'survey', label: '調べる' },
  { name: 'flow', label: '流れ図', group: true },
  { name: 'klass', label: 'クラス図', group: true },
  { name: 'seq', label: 'シーケンス図', group: true },
  { name: 'state', label: '状態図', group: true },
  { name: 'report', label: 'まとめ' },
];

// failed の見本は枠の中が 3 段（流れ図・クラス図・シーケンス図。シーケンス図に判定）
const FAILED_STAGES: readonly StageSpec[] = [
  { name: 'survey', label: '調べる' },
  { name: 'flow', label: '流れ図', group: true },
  { name: 'klass', label: 'クラス図', group: true },
  { name: 'seq', label: 'シーケンス図', group: true, check: { on_fail: null, max_retries: 2 } },
  { name: 'report', label: 'まとめ' },
];

function stageEntry(spec: StageSpec, withGroup: boolean): Record<string, unknown> {
  return {
    name: spec.name,
    label: spec.label,
    output: `${spec.name}.md`,
    review: false,
    ...(spec.check === undefined || !withGroup ? {} : { check: spec.check }),
    ...(spec.group === true && withGroup ? { [groupKey()]: FRAME } : {}),
  };
}

interface RunOpts {
  isError?: boolean;
  limit?: number;
}

function runEntry(stage: string, seq: number, attempt: number | null, opts: RunOpts = {}): Record<string, unknown> {
  return {
    stage,
    session_id: `group-session-${seq}`,
    is_error: opts.isError === true,
    subtype: opts.isError === true ? 'error_during_execution' : 'success',
    result: opts.isError === true ? '失敗しました' : '完了しました',
    cost_usd: 0.1,
    num_turns: 3,
    duration_sec: 20.0,
    denials: [],
    errors: [],
    seq,
    attempt,
    note: '',
    ...(opts.limit === undefined ? {} : { max_budget_usd: opts.limit }),
  };
}

function checkEntry(stage: string, status: 'pass' | 'fail', attempt: number): Record<string, unknown> {
  return {
    stage,
    check: {
      attempt,
      status,
      problems: status === 'fail' ? ['矢印の向きが逆になっている'] : [],
      summary: status === 'fail' ? `${attempt} 回目は直す点があります` : '直す点はありません',
    },
  };
}

const pad2 = (n: number): string => String(n).padStart(2, '0');

/** 段のログの 1 つ（ファイル名と中身）。 */
export interface GroupLog {
  fileName: string;
  text: string;
}

/** 段のログ：Prompt → 発言 →（終わっていれば）ResultMessage。終わりの行が無いものが「動いている」。 */
function logFile(seq: number, stage: string, attempt: number | null, atMs: number, text: string, end: 'done' | 'error' | 'open'): GroupLog {
  const at = `${new Date(atMs).toISOString().slice(0, 19)}+00:00`;
  const lines: object[] = [
    { _type: 'Prompt', stage, resume: null, prompt: `${stage} の依頼文`, at },
    { _type: 'AssistantMessage', content: [{ text }], model: 'x' },
  ];
  if (end !== 'open') {
    lines.push({ _type: 'ResultMessage', subtype: 'success', is_error: end === 'error', num_turns: 3, duration_ms: 20000, total_cost_usd: 0.1, result: text });
  }
  return { fileName: `${pad2(seq)}_${stage}${attempt === null ? '' : `_${attempt}`}.jsonl`, text: `${lines.map((l) => JSON.stringify(l)).join('\n')}\n` };
}

const BASE_MS = Date.parse(GROUP_BASE_AT);
const MIN = 60_000;

/** 見本の種類ごとの state.json の文字（パイプ group-demo）。 */
export function groupStateJson(kind: GroupSampleKind): string {
  const old = kind === 'old';
  const specs = kind === 'failed' ? FAILED_STAGES : STAGES;
  let runs: Record<string, unknown>[];
  let final: string | null = null;
  if (kind === 'running') {
    // flow・klass が動いていて、そのあとに始まった seq が先に済んだ（通し番号 4 > 2・3）。state はまだ
    runs = [runEntry('survey', 1, null), runEntry('seq', 4, null)];
  } else if (kind === 'failed') {
    // flow は完了、klass は失敗、seq は 1 回目の検証が fail → やり直して pass（2 回目）。上限つきなので「2 回目」が出る
    runs = [
      runEntry('survey', 1, null),
      runEntry('flow', 2, null),
      runEntry('klass', 3, null, { isError: true }),
      runEntry('seq', 4, null, { limit: 1 }),
      checkEntry('seq', 'fail', 1),
      runEntry('seq', 5, 2, { limit: 1 }),
      checkEntry('seq', 'pass', 2),
    ];
    final = 'STAGE_ERROR';
  } else {
    // group の無い古い記録：同じ段が一列に並び、動いている段は無い
    runs = [runEntry('survey', 1, null), runEntry('flow', 2, null), runEntry('klass', 3, null), runEntry('seq', 4, null)];
  }
  const state = {
    started_at: '2026-10-17T10:00:00',
    updated_at: '2026-10-17T10:04:00',
    pipe: 'group-demo',
    name: '並列の枠の見本',
    stages: specs.map((s) => stageEntry(s, !old)),
    runs,
    final,
    total_cost_usd: Math.round(runs.filter((r) => 'seq' in r).length * 0.1 * 1e4) / 1e4,
  };
  return `${JSON.stringify(state, null, 2)}\n`;
}

/** 見本の種類ごとの段のログ（logs/ に置く）。running は flow・klass が動いている（終わりの行が無い）。 */
export function groupLogs(kind: GroupSampleKind): GroupLog[] {
  if (kind === 'running') {
    return [
      logFile(1, 'survey', null, BASE_MS - MIN, '調べた結果をまとめた', 'done'),
      logFile(2, 'flow', null, BASE_MS, '流れ図を描いている（<b>太字</b> と書かれていても、そのまま見える）', 'open'),
      logFile(3, 'klass', null, BASE_MS + 5_000, 'クラス図を描いている', 'open'),
      logFile(4, 'seq', null, BASE_MS + 10_000, 'シーケンス図を描いた', 'done'),
    ];
  }
  if (kind === 'failed') {
    return [
      logFile(1, 'survey', null, BASE_MS - MIN, '調べた結果をまとめた', 'done'),
      logFile(2, 'flow', null, BASE_MS, '流れ図を描いた', 'done'),
      logFile(3, 'klass', null, BASE_MS + 5_000, 'クラス図の途中で止まった', 'error'),
      logFile(4, 'seq', null, BASE_MS + 10_000, 'シーケンス図の 1 回目', 'done'),
      logFile(5, 'seq', 2, BASE_MS + 2 * MIN, 'シーケンス図の 2 回目（直した）', 'done'),
    ];
  }
  return [
    logFile(1, 'survey', null, BASE_MS - MIN, '調べた結果をまとめた', 'done'),
    logFile(2, 'flow', null, BASE_MS, '流れ図を描いた', 'done'),
    logFile(3, 'klass', null, BASE_MS + 5_000, 'クラス図を描いた', 'done'),
    logFile(4, 'seq', null, BASE_MS + 10_000, 'シーケンス図を描いた', 'done'),
  ];
}
