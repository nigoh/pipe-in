// 確認用ページ（エージェント・スキルのタブ。D0050）の見本の記録の中身（純粋。文字と数を組み立てるだけで、ファイルにも時計にも触れない）。
// 置くのは previewPages.ts で、一時フォルダの中だけ。tests/fixtures/ の見本の記録には何も足さない・書かない。
// 「今」は引数 nowMs で受ける（呼ぶ側が決める）。ID は呼び出しごとに別（toolu_tools_<通し番号>_<番号>）。手元の情報（ユーザー名の入ったパス・メールアドレス）は書かない。
// 見本は 4 つ（どれも全部をここで作る）：
//   (a) sdkSample          動いている SDK のパイプ（tools-sdk）。エージェント・スキル・道具・入れ子・外から来た文字・100 種類を超える名前を持つ。agent も driver も入れない。
//   (b) skillRecordSample  /pipe-in の記録（直下）。受け持ち pipe-in-analyst・pipe-in-tester と、段の実行の長さ。driver あり・確認待ち。
//   (c) bareRecordSample   /pipe-in の記録で --agent を付けなかったもの（archive/ の前の実行）。driver あり・受け持ち無し。
//   (d) freshSample        呼び出しがまだ無い SDK の実行（tools-fresh）。driver なし・ログは Prompt だけ。

export type ToolsVariant = 'current' | 'next';
export type SampleKind = 'agent' | 'skill' | 'tool';

/** 表になるはずの 1 行：種類・表に出す名前・回数。生成した呼び出しを生成する側で数えたもの（表を作る側の計算を写さない）。 */
export interface ToolsExpected {
  kind: SampleKind;
  name: string;
  count: number;
}

export interface SampleLog {
  fileName: string;
  text: string;
}

/** 見本の実行 1 つ：state.json の中身・段のログ・置き場所の直下に書く文書（ファイル名 → 中身）。 */
export interface SampleRun {
  state: Record<string, unknown>;
  logs: SampleLog[];
  files: Record<string, string>;
}

export interface SdkSample extends SampleRun {
  /** 表の期待（並びは持たない。呼び出しを入れた順） */
  expected: ToolsExpected[];
}

/** 表に出す代わりの名前（domain/toolsTable.ts の定数と同じ文字。見本は表を作る側を import しない） */
const UNSPECIFIED = '（指定なし）';
const UNREADABLE = '（読めない名前）';

const MODEL = 'claude-opus-5-5';
const pad2 = (n: number): string => String(n).padStart(2, '0');
const SEC = 1000;

/** 段の始まりの時刻（at）の書き方：UTC からのずれつき。 */
const atText = (ms: number): string => `${new Date(ms).toISOString().slice(0, 19)}+00:00`;
/** state.json の started_at・updated_at の書き方：ずれなし（見本の手元のずれは 0）。 */
const stampText = (ms: number): string => new Date(ms).toISOString().slice(0, 19);

const jsonl = (lines: readonly object[]): string => `${lines.map((l) => JSON.stringify(l)).join('\n')}\n`;
const docText = (...rows: string[]): string => `${rows.join('\n')}\n`;

// ---- 呼び出しの数え上げ（生成する側） ----------------------------------------------------------

type Tally = Map<string, ToolsExpected>;

function tallyAdd(tally: Tally, kind: SampleKind, name: string): void {
  const key = `${kind}\u0000${name}`;
  const found = tally.get(key);
  if (found === undefined) tally.set(key, { kind, name, count: 1 });
  else found.count += 1;
}

/** 段のログ 1 つを組み立てる。call は呼び出しの行を足して、呼び出しの id を返し、表に出る名前を数える。 */
function logWriter(seq: number, tally: Tally) {
  const lines: object[] = [];
  let n = 0;
  return {
    lines,
    prompt(stage: string, prompt: string, at: number): void {
      lines.push({ _type: 'Prompt', stage, resume: null, prompt, at: atText(at) });
      lines.push({ subtype: 'init', data: { type: 'system', subtype: 'init', model: MODEL, permissionMode: 'default' }, _type: 'SystemMessage' });
    },
    say(text: string, parent: string | null = null): void {
      lines.push({ content: [{ text }], model: MODEL, parent_tool_use_id: parent, _type: 'AssistantMessage' });
    },
    think(parent: string | null = null): void {
      lines.push({ content: [{ thinking: '次に読む場所を決める。', signature: 'sample' }], model: MODEL, parent_tool_use_id: parent, _type: 'AssistantMessage' });
    },
    /** 呼び出し 1 回。shown は表に出る名前（読めない名前・指定なしは代わりの文字）。 */
    call(kind: SampleKind, shown: string, name: string, input: Record<string, unknown>, parent: string | null = null): string {
      n += 1;
      const id = `toolu_tools_${pad2(seq)}_${n}`;
      lines.push({ content: [{ id, name, input }], model: MODEL, parent_tool_use_id: parent, _type: 'AssistantMessage' });
      tallyAdd(tally, kind, shown);
      return id;
    },
    result(durationSec: number): void {
      lines.push({ _type: 'ResultMessage', subtype: 'success', is_error: false, num_turns: 6, duration_ms: Math.round(durationSec * SEC), total_cost_usd: 0.05, result: '完了' });
    },
  };
}
type Writer = ReturnType<typeof logWriter>;

const tool = (w: Writer, name: string, input: Record<string, unknown> = {}, times = 1, parent: string | null = null): void => {
  for (let i = 0; i < times; i++) w.call('tool', name, name, input, parent);
};
const read = (w: Writer, times: number, parent: string | null = null): void => tool(w, 'Read', { file_path: 'src/app/refreshView.ts' }, times, parent);
const grep = (w: Writer, times: number, parent: string | null = null): void => tool(w, 'Grep', { pattern: 'buildPipelineView', path: 'src' }, times, parent);
const bash = (w: Writer, times: number): void => tool(w, 'Bash', { command: 'npm --prefix vscode test' }, times);

/** エージェントを呼ぶ。type が undefined なら subagent_type の鍵そのものを省く。shown は表に出る名前。 */
function agent(w: Writer, via: 'Agent' | 'Task', type: unknown, shown: string, parent: string | null = null): string {
  const input: Record<string, unknown> = { description: '指定のモジュールを読む', prompt: '指定のモジュールを読み、役割を 3 行でまとめてください。' };
  if (type !== undefined) input.subagent_type = type;
  return w.call('agent', shown, via, input, parent);
}

/** スキルを呼ぶ。name が undefined なら skill の鍵そのものを省く。 */
function skill(w: Writer, name: unknown, shown: string): void {
  const input: Record<string, unknown> = { args: 'docs/guide' };
  if (name !== undefined) input.skill = name;
  w.call('skill', shown, 'Skill', input);
}

// ---- (a) 動いている SDK の実行 ----------------------------------------------------------------

/** 外から来た文字の見本（空白を含まないので名前の決まりに合い、そのまま行になる）。表では文字のまま出る。 */
const HOSTILE_AGENT = '<img/src=x/onerror=alert(1)>';
const HOSTILE_SKILL = '<script>alert(1)</script>';
const QUOTED_TOOL = 'weird"quote';
const AMP_TOOL = 'amp&<tool>';
/** 空白のない 100 文字の道具の名前 */
const LONG_TOOL = 'long_name_'.repeat(10);
/** 名前だけが違う道具（回数 1 の行を 100 を超えて作る） */
const FILLER_COUNT = 105;
const fillerName = (i: number): string => `custom_tool_${String(i).padStart(3, '0')}`;
/** 更新後の見本で足す、新しい道具（現在の見本に無い名前） */
const NEW_TOOL = 'custom_tool_new';
/** 更新後の見本で足す Grep の回数（Read を抜く） */
const NEXT_GREP = 15;
/** 更新後の見本で足す module-reader の回数 */
const NEXT_READER = 2;

const SDK_STAGES = [
  { name: 'survey', label: '調査', output: '01_survey.md', review: false },
  { name: 'draw', label: '図を描く', output: '02_draw.md', review: false },
  { name: 'verify', label: '突き合わせ <ソース> & "図"', output: '03_verify.md', review: false },
  { name: 'rubric', label: '審査', output: '04_rubric.md', review: false },
];

/** 段の実行の見本：[通し番号, 段, ログのファイル名の回, 始まり（今の何秒前か）, 長さ（秒）] */
const SDK_RUNS: readonly (readonly [number, string, number | null, number, number])[] = [
  [1, 'survey', null, 600, 110],
  [2, 'draw', 1, 480, 100],
  [3, 'verify', 1, 360, 90],
  [4, 'draw', 2, 240, 80],
  [5, 'verify', 2, 150, 70],
];
/** 動いている段（06_rubric）の始まり（今の何秒前か） */
const RUBRIC_AGO_SEC = 60;

const logName = (seq: number, stage: string, attempt: number | null): string => `${pad2(seq)}_${stage}${attempt === null ? '' : `_${attempt}`}.jsonl`;

/** (a) のログ 6 つのうち、通し番号 seq の呼び出しを入れる。 */
function fillSdkLog(w: Writer, seq: number, variant: ToolsVariant): void {
  switch (seq) {
    case 1: {
      w.say('調べる対象のモジュールを洗い出します。');
      w.think();
      tool(w, 'Glob', { pattern: 'src/**/*.ts' });
      read(w, 2);
      grep(w, 1);
      bash(w, 2);
      tool(w, 'mcp__jira__get_issue', { issue: 'DOC-1' }, 3);
      tool(w, 'mcp__docs__search', { query: 'パネルの描き直し' });
      skill(w, 'repo-map', 'repo-map');
      skill(w, HOSTILE_SKILL, HOSTILE_SKILL);
      agent(w, 'Agent', undefined, UNSPECIFIED);
      agent(w, 'Agent', HOSTILE_AGENT, HOSTILE_AGENT);
      const reader = agent(w, 'Agent', 'module-reader', 'module-reader');
      w.say('モジュールを読んでいます。', reader);
      read(w, 2, reader);
      grep(w, 1, reader);
      agent(w, 'Task', 'module-reader', 'module-reader');
      break;
    }
    case 2: {
      w.say('調査をもとに図を描きます。');
      read(w, 4);
      grep(w, 2);
      tool(w, 'Glob', { pattern: 'docs/**/*.md' });
      bash(w, 2);
      tool(w, 'Write', { file_path: 'docs/diagrams/flow.md' });
      tool(w, 'Edit', { file_path: 'docs/diagrams/flow.md' }, 3);
      tool(w, 'mcp__docs__search', { query: '図の書き方' });
      skill(w, 'repo-map', 'repo-map');
      skill(w, undefined, UNSPECIFIED);
      agent(w, 'Agent', 'bad name', UNREADABLE);
      tool(w, QUOTED_TOOL);
      break;
    }
    case 3: {
      w.say('図とソースを突き合わせます。');
      read(w, 2);
      grep(w, 1);
      tool(w, 'Glob', { pattern: 'src/domain/*.ts' });
      bash(w, 2);
      tool(w, 'mcp__docs__search', { query: '突き合わせの手順' }, 2);
      skill(w, 'review-docs', 'review-docs');
      agent(w, 'Agent', 'module-reader', 'module-reader');
      const checker = agent(w, 'Agent', 'source-checker', 'source-checker');
      read(w, 1, checker);
      const inner = agent(w, 'Agent', 'source-checker', 'source-checker', checker);
      w.say('入れ子の確認です。', inner);
      agent(w, 'Agent', 'source-checker', 'source-checker');
      tool(w, LONG_TOOL);
      break;
    }
    case 4: {
      w.say('指摘を直して図を描き直します。');
      w.think();
      read(w, 3);
      grep(w, 1);
      tool(w, 'Glob', { pattern: 'docs/diagrams/*.md' });
      bash(w, 1);
      tool(w, 'Write', { file_path: 'docs/diagrams/sequence.md' }, 2);
      tool(w, 'Edit', { file_path: 'docs/diagrams/flow.md' }, 3);
      skill(w, HOSTILE_SKILL, HOSTILE_SKILL);
      agent(w, 'Agent', undefined, UNSPECIFIED);
      agent(w, 'Task', 5, UNREADABLE);
      tool(w, LONG_TOOL);
      break;
    }
    case 5: {
      w.say('描き直した図を突き合わせます。');
      read(w, 3);
      grep(w, 1);
      bash(w, 1);
      skill(w, 'review-docs', 'review-docs');
      skill(w, 'review-docs', 'review-docs');
      agent(w, 'Agent', 'module-reader', 'module-reader');
      agent(w, 'Task', 'module-reader', 'module-reader');
      agent(w, 'Agent', HOSTILE_AGENT, HOSTILE_AGENT);
      tool(w, QUOTED_TOOL);
      tool(w, AMP_TOOL);
      break;
    }
    default: {
      // 動いている段（06_rubric）。更新後の見本では、続きの呼び出しが増える
      w.say('成果物を審査しています。');
      read(w, 3);
      grep(w, 1);
      bash(w, 1);
      tool(w, AMP_TOOL);
      if (variant === 'next') {
        grep(w, NEXT_GREP);
        for (let i = 0; i < NEXT_READER; i++) agent(w, 'Agent', 'module-reader', 'module-reader');
        tool(w, NEW_TOOL);
      }
    }
  }
  // 名前だけが違う道具を、回数 1 で全部のログに散らす（100 種類を超える）
  for (let i = 1; i <= FILLER_COUNT; i++) if (i % 6 === seq % 6) tool(w, fillerName(i));
}

const SDK_SESSION_ID = 'b7e2c1d4-5a90-4f3e-8d16-2c9a7e0b4f58';

/**
 * (a) 動いている SDK のパイプ tools-sdk。段は survey・draw・verify・rubric（verify の表示名に < & " を含む）。
 * ログは 6 つ：01_survey・02_draw_1・03_verify_1・04_draw_2・05_verify_2 は終わり、06_rubric が動いている。
 * 状態にもログにも agent と driver は入れない（時間の列も案内も出ない）。variant が next なら 06_rubric に呼び出しが増える：
 * Grep を 15 回（Read を抜く）・module-reader を 2 回・新しい道具を 1 種。
 */
export function sdkSample(nowMs: number, variant: ToolsVariant): SdkSample {
  const tally: Tally = new Map();
  const logs: SampleLog[] = [];
  const runs: object[] = [];
  for (const [seq, stage, attempt, agoSec, durationSec] of SDK_RUNS) {
    const w = logWriter(seq, tally);
    w.prompt(stage, `${stage} の段です。`, nowMs - agoSec * SEC);
    fillSdkLog(w, seq, variant);
    w.result(durationSec);
    logs.push({ fileName: logName(seq, stage, attempt), text: jsonl(w.lines) });
    runs.push({
      stage,
      session_id: null,
      is_error: false,
      subtype: 'success',
      result: '完了',
      cost_usd: 0.05,
      num_turns: 6,
      duration_sec: durationSec,
      denials: [],
      errors: [],
      metrics: {},
      seq,
      attempt,
      note: '',
    });
  }
  const running = logWriter(6, tally);
  running.prompt('rubric', 'rubric の段です。', nowMs - RUBRIC_AGO_SEC * SEC);
  fillSdkLog(running, 6, variant);
  logs.push({ fileName: logName(6, 'rubric', null), text: jsonl(running.lines) });

  return {
    state: {
      started_at: stampText(nowMs - 630 * SEC),
      updated_at: stampText(nowMs - 5 * SEC),
      pipe: 'tools-sdk',
      name: '呼び出しの数を見る（確認用の見本）',
      session_id: SDK_SESSION_ID,
      stages: SDK_STAGES,
      final: null,
      total_cost_usd: 0.25,
      usage_summary: null,
      pending_review: null,
      warnings: [],
      runs,
    },
    logs,
    files: { '00_input.md': docText('# 依頼メモ', '', 'モジュールを調べて、図を描き、ソースと突き合わせる（確認用の見本）。') },
    expected: [...tally.values()],
  };
}

// ---- (b)(c) /pipe-in の記録 ---------------------------------------------------------------------

const DEV_STAGES = [
  { name: 'requirements', label: '要件定義', output: '01_requirements.md', review: true },
  { name: 'design', label: '設計', output: '02_design.md', review: true },
  { name: 'red', label: 'テスト先行', output: '03_red_tests.md', review: true },
  { name: 'implement', label: '実装', output: '04_implementation.md', review: false },
  { name: 'test', label: '検証', output: '05_test_report.md', review: false },
];

const DRIVER = 'pipe-dev';
const ANALYST = 'pipe-in-analyst';
const TESTER = 'pipe-in-tester';

/** record begin / done が書く形のログ：Prompt（driver・agent・at）→ 要約の文 1 行 → ResultMessage。道具の呼び出しは残らない。 */
function recordLog(stage: string, prompt: string, agent: string, at: number, durationSec: number, summary: string): string {
  return jsonl([
    { _type: 'Prompt', stage, resume: null, prompt, driver: DRIVER, agent, at: atText(at) },
    { _type: 'AssistantMessage', content: [{ text: summary }], model: DRIVER },
    { _type: 'ResultMessage', subtype: 'success', is_error: false, num_turns: 0, duration_ms: Math.round(durationSec * SEC), total_cost_usd: 0.0, result: summary },
  ]);
}

/** record done が runs に足す段の実行 */
function recordRun(stage: string, seq: number, attempt: number | null, durationSec: number, result: string, agent: string | null, note = ''): object {
  return {
    stage,
    session_id: null,
    is_error: false,
    subtype: 'success',
    result,
    cost_usd: 0.0,
    num_turns: 0,
    duration_sec: durationSec,
    denials: [],
    errors: [],
    metrics: {},
    seq,
    attempt,
    note,
    ...(agent === null ? {} : { agent }),
  };
}

const PIPE_IN_SESSION_ID = '4e8a1b7c-2d93-4f60-a5c1-9b3e6d0f7a24';

/**
 * (b) /pipe-in の記録（置き場所の直下）。driver あり・テスト先行の確認待ち。
 * 受け持ちは pipe-in-analyst（要件定義 95.0 秒・要件定義 2 回目 41.2 秒・設計 120.4 秒）と pipe-in-tester（テスト先行 75.0 秒）。
 */
export function skillRecordSample(nowMs: number): SampleRun {
  const since = nowMs - 200 * SEC;
  return {
    state: {
      started_at: stampText(nowMs - 700 * SEC),
      updated_at: stampText(since),
      pipe: 'dev',
      name: '一覧に CSV 出力ボタンを足す（/pipe-in の記録の見本）',
      session_id: PIPE_IN_SESSION_ID,
      driver: DRIVER,
      stages: DEV_STAGES,
      final: null,
      total_cost_usd: 0.0,
      usage_summary: null,
      pending_review: { stage: 'red', doc: 'docs/pipeline/03_red_tests.md', session_id: null, since: atText(since) },
      warnings: [],
      open: null,
      runs: [
        recordRun('requirements', 1, null, 95.0, '要件定義を書いた', ANALYST),
        { stage: 'requirements', review: 'revise', feedback: '受け入れ基準を分けてください' },
        recordRun('requirements', 2, 2, 41.2, '指摘を反映した', ANALYST, '指摘を反映'),
        { stage: 'requirements', review: 'approved' },
        recordRun('design', 3, null, 120.4, '設計を書いた', ANALYST),
        { stage: 'design', review: 'approved' },
        recordRun('red', 4, null, 75.0, 'テストを書いた', TESTER),
        { stage: 'red', result: { status: 'red', summary: 'AC-01 が赤', tests: [{ criterion: 'AC-01', test: 'tests/test_export.py::test_header' }], commands: ['python -m pytest -q'] } },
      ],
    },
    logs: [
      { fileName: '01_requirements.jsonl', text: recordLog('requirements', '/pipe-dev の要件定義', ANALYST, nowMs - 690 * SEC, 95.0, '要件定義を書いた') },
      { fileName: '02_requirements_2.jsonl', text: recordLog('requirements', '/pipe-dev の要件定義（2 回目）', ANALYST, nowMs - 560 * SEC, 41.2, '指摘を反映した') },
      { fileName: '03_design.jsonl', text: recordLog('design', '/pipe-dev の設計', ANALYST, nowMs - 450 * SEC, 120.4, '設計を書いた') },
      { fileName: '04_red.jsonl', text: recordLog('red', '/pipe-dev のテスト先行', TESTER, nowMs - 300 * SEC, 75.0, 'テストを書いた') },
    ],
    files: {
      '00_input.md': docText('# 依頼メモ', '', 'ユーザー一覧に CSV 出力ボタンを足したい（確認用の見本）。'),
      '01_requirements.md': docText('# 要件定義', '', '- AC-01 CSV の先頭に見出しの行を付ける。'),
      '02_design.md': docText('# 設計', '', '- 出力の関数を 1 つ足し、ボタンと API から呼ぶ。'),
      '03_red_tests.md': docText('# テスト先行', '', '- AC-01 のテストを足した（赤）。'),
    },
  };
}

/** (c) --agent を付けなかった /pipe-in の記録（archive/ の前の実行）。driver あり・受け持ち無し・合格。ログは残さない（state.json だけ）。 */
export function bareRecordSample(nowMs: number): SampleRun {
  const start = nowMs - 26 * 3600 * SEC;
  const runs = DEV_STAGES.map((s, i) => recordRun(s.name, i + 1, null, 60 + i * 10, `${s.label}を終えた`, null));
  return {
    state: {
      started_at: stampText(start),
      updated_at: stampText(start + 1800 * SEC),
      pipe: 'dev',
      name: 'CSV 出力の見直し（受け持ちを付けなかった記録の見本）',
      session_id: '9d2f6a40-7c15-4b8e-b3a9-1e5c0d8f2a67',
      driver: DRIVER,
      stages: DEV_STAGES,
      final: 'PASSED',
      total_cost_usd: 0.0,
      usage_summary: null,
      pending_review: null,
      warnings: [],
      open: null,
      runs,
    },
    logs: [],
    files: {},
  };
}

/** (d) 呼び出しがまだ無い SDK の実行 tools-fresh。driver なし・runs は空・ログは Prompt の行だけ（動いている）。 */
export function freshSample(nowMs: number): SampleRun {
  const prompt = { _type: 'Prompt', stage: 'survey', resume: null, prompt: 'survey の段です。', at: atText(nowMs - 8 * SEC) };
  return {
    state: {
      started_at: stampText(nowMs - 20 * SEC),
      updated_at: stampText(nowMs - 8 * SEC),
      pipe: 'tools-fresh',
      name: 'まだ呼び出しが無い実行（確認用の見本）',
      session_id: 'c3a7e915-0b24-4d68-9f1e-5a8d2c6b0e43',
      stages: SDK_STAGES.slice(0, 2),
      final: null,
      total_cost_usd: 0.0,
      usage_summary: null,
      pending_review: null,
      warnings: [],
      runs: [],
    },
    logs: [{ fileName: '01_survey.jsonl', text: jsonl([prompt]) }],
    files: { '00_input.md': docText('# 依頼メモ', '', '始めたばかりの実行（確認用の見本）。') },
  };
}
