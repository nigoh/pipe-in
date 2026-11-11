// 開発用の新しい記録（/pipe-in の記録）の見本（D0090）。確認用ページ（run-panel-dev-*）に使う state.json と段のログの中身だけを持つ。
// tests/fixtures/ には見本の記録を足さない。previewPages.ts の buildDevDir が、一時フォルダに書いて本物の読み取りで読む。
// 本体（pipe-in record）が書く形：schema 1・driver が pipe-dev・費用は null・使用量は available=false と理由・runs に metrics は持たない。
// 段が 1 秒ほどで終わる短い記録（0.3・0.6・1.0 秒）が、テスト先行の確認待ちで止まる。時系列の字が重ならないかを見るための見本。
// 時刻はすべて時差なし（本体の record.py と同じ書き方）。動かす場所のタイムゾーンに左右されない。

const STARTED_AT = '2026-11-11T11:40:42';
const UPDATED_AT = '2026-11-11T11:40:43';
const SINCE = '2026-11-11T11:40:43';

/** 見本の理由の文（本体が書く文と同じ意味） */
const REASON = '開発用の記録は費用とトークンを取りません';

interface Entry {
  name: string;
  label: string;
  output: string;
  agent: string;
  sec: number;
}

const ENTRIES: readonly Entry[] = [
  { name: 'requirements', label: '要件定義', output: '01_requirements.md', agent: 'pipe-in-analyst', sec: 0.3 },
  { name: 'design', label: '設計', output: '02_design.md', agent: 'pipe-in-analyst', sec: 0.6 },
  { name: 'red', label: 'テスト先行', output: '03_red_tests.md', agent: 'pipe-in-tester', sec: 1.0 },
];

function runEntry(entry: Entry, seq: number): Record<string, unknown> {
  return {
    stage: entry.name,
    session_id: null,
    is_error: false,
    subtype: 'success',
    result: '',
    cost_usd: null,
    num_turns: 0,
    duration_sec: entry.sec,
    denials: [],
    errors: [],
    seq,
    attempt: null,
    note: '',
    agent: entry.agent,
  };
}

/** 見本の state.json の文字（テスト先行の確認待ちで止まっている）。 */
export function devStateJson(): string {
  const state = {
    schema: 1,
    started_at: STARTED_AT,
    updated_at: UPDATED_AT,
    pipe: 'dev',
    name: '開発用の記録の見本',
    driver: 'pipe-dev',
    stages: [
      { name: 'requirements', label: '要件定義', output: '01_requirements.md', review: true },
      { name: 'design', label: '設計', output: '02_design.md', review: true },
      { name: 'red', label: 'テスト先行', output: '03_red_tests.md', review: true },
      { name: 'implement', label: '実装', output: '04_implementation.md', review: false },
      { name: 'test', label: '検証', output: '05_verification.md', review: false },
    ],
    final: null,
    total_cost_usd: null,
    usage_summary: { available: false, reason: REASON },
    pending_review: { stage: 'red', doc: 'docs/pipeline/03_red_tests.md', session_id: null, next: 'implement', since: SINCE },
    warnings: [],
    open: null,
    runs: ENTRIES.map((entry, i) => runEntry(entry, i + 1)),
  };
  return `${JSON.stringify(state, null, 2)}\n`;
}

/** 見本の段のログ（logs/*.jsonl）の文字。Prompt の at は 3 つとも同じ秒（実物と同じ 1 秒の刻み）。 */
export function devLogs(): { fileName: string; text: string }[] {
  const files = ['01_requirements.jsonl', '02_design.jsonl', '03_red.jsonl'];
  return ENTRIES.map((entry, i) => ({
    fileName: files[i]!,
    text:
      `${JSON.stringify({ _type: 'Prompt', stage: entry.name, resume: null, prompt: `${entry.label}の段を進めてください。`, at: STARTED_AT, agent: entry.agent })}\n` +
      `${JSON.stringify({ content: [{ text: `${entry.label}の記録を書きます。` }], model: 'claude-opus-5-5', parent_tool_use_id: null, _type: 'AssistantMessage' })}\n`,
  }));
}
