// 図の状態 PipelineView の tools（D0047）：記録の写し（state.json と段のログの文字）から、エージェント・スキル・道具の表ができる。
// buildPipelineView(snapshot, clock, { tools }) の tools は既定で真（表を作る）。{ tools: false } は null（一覧の行の組み立てが使う）。
// 項目 tools・第 3 引数・renderTools は実装の段で足される。呼ぶ前に、tools が非 null・非 undefined であることを確かめて落とす
// （undefined どうしが deepStrictEqual で等しくなって、赤にならないのを避ける）。
// 偽の段のログと state.json の文字だけで作る（SDK は呼ばない・ファイルに書かない）。見本の記録（tests/fixtures/pipe_dev・pipe_in）は読むだけ。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { performance } from 'node:perf_hooks';
import { buildPipelineView } from './pipelineView.ts';
import type { PipelineView, ViewClock, WorkDirSnapshot } from './pipelineView.ts';
import { renderViewBody } from '../view/panelHtml.ts';
import { DEV_STAGES, DIAGRAMS_STAGES, assistantParts, assistantTool, logText, promptLine, resultLine, resultPart, snapshot, stageRunEntry, stateJson, toolPart } from '../test/fixtures.ts';
import { ganttSnapshot } from '../test/ganttFixtures.ts';
import { clockAt, fixtureSnapshot } from '../test/liveFixtures.ts';
import { needModule } from '../test/needModule.ts';
import { HOSTILE, PROTO_NAMES, bigLog, toolsSnapshot, uniqueCalls, withPollutedPrototype } from '../test/toolsFixtures.ts';
import { parseStageLog } from './stageLog.ts';

interface Row {
  kind: string;
  name: string;
  count: number;
  stages: string[];
  durationSec: number | null;
}
interface Tools {
  rows: Row[];
  kinds: number;
  total: number;
  omitted: number;
  showTime: boolean;
  notice: 'A' | 'B' | null;
}
type BuildView = (snap: WorkDirSnapshot, clock?: ViewClock, options?: { tools?: boolean }) => PipelineView;
/** 第 3 引数は実装の段で足される。型を緩めて呼ぶ（テスト先行のときも型検査が通るように） */
const build = buildPipelineView as unknown as BuildView;

/** 図の状態の表。無い（undefined）・作っていない（null）なら落とす */
function toolsOf(view: PipelineView): Tools {
  const tools = (view as unknown as { tools?: Tools | null }).tools;
  assert.ok(tools !== undefined && tools !== null, 'view.tools（エージェント・スキル・道具の表）がある（まだ作っていない）');
  return tools;
}
const viewOf = (snap: WorkDirSnapshot, clock?: ViewClock): PipelineView => build(snap, clock);
const tableOf = (snap: WorkDirSnapshot, clock?: ViewClock): Tools => toolsOf(viewOf(snap, clock));
const brief = (t: Tools): string[] => t.rows.map((r) => `${r.kind}:${r.name}:${r.count}`);
const rowOf = (t: Tools, kind: string, name: string): Row => {
  const found = t.rows.find((r) => r.kind === kind && r.name === name);
  assert.ok(found, `${kind} の ${name} の行がある：${JSON.stringify(brief(t))}`);
  return found;
};
interface HtmlMod {
  renderTools(tools: unknown): string;
}
const html = async (tools: unknown): Promise<string> => (await needModule<HtmlMod>(import.meta.url, '../view/toolsHtml.ts')).renderTools(tools);

const UNSPECIFIED = '（指定なし）';
const REQ = (lines: readonly string[]) => toolsSnapshot({ runs: [{ seq: 1, stage: 'requirements' }], logs: [{ seq: 1, stage: 'requirements', lines }] });

// ---- AC-05：表の行の種類 ----

test('D0047-AC-05: 同じ入力から、エージェント a（Agent と Task）・スキル s・道具 Read の行ができ、鍵の取り違えは「（指定なし）」の行になる', () => {
  const t = tableOf(
    REQ(
      uniqueCalls([
        { name: 'Agent', input: { subagent_type: 'a' } },
        { name: 'Task', input: { subagent_type: 'a' } },
        { name: 'Skill', input: { skill: 's' } },
        { name: 'Agent', input: { skill: 's' } },
        { name: 'Skill', input: { subagent_type: 'a' } },
        { name: 'Read', input: { file_path: 'x.py' } },
      ]),
    ),
  );
  assert.deepEqual(brief(t), ['agent:a:2', `agent:${UNSPECIFIED}:1`, 'skill:s:1', `skill:${UNSPECIFIED}:1`, 'tool:Read:1']);
});

test('D0047-AC-02: 実物の形のログ（tests/fixtures/showcase。SystemMessage・RateLimitEvent・ResultMessage 入りで、発言に parent_tool_use_id: null が付く）を表にすると、回数の合計は各ログの出力の道具の行の数の合計（21）と同じで、表は Write 7・Bash 5・Edit 4・Read 4・Grep 1', () => {
  const snap = fixtureSnapshot('showcase');
  const outputRows = snap.stageLogs.reduce((sum, file) => sum + parseStageLog(file.text).items.filter((i) => i.kind === 'tool').length, 0);
  assert.equal(outputRows, 21, '出力の道具の行の合計（見本が変わっていない）');
  const t = tableOf(snap);
  assert.equal(t.total, outputRows, '表の回数の合計は出力の道具の行の数と同じ');
  assert.equal(t.kinds, 5);
  assert.deepEqual(brief(t), ['tool:Write:7', 'tool:Bash:5', 'tool:Edit:4', 'tool:Read:4', 'tool:Grep:1']);
  assert.equal(t.notice, null, 'driver が無い');
  assert.equal(t.showTime, false, '受け持ちが無い');
  assert.deepEqual(rowOf(t, 'tool', 'Grep').stages, ['要件定義']);
  assert.deepEqual(rowOf(t, 'tool', 'Edit').stages, ['要件定義', '実装 1 回目', '実装 2 回目'], '通し番号 2・5・7（ログのファイル名の回）');
  assert.deepEqual(rowOf(t, 'tool', 'Read').stages, ['要件定義', '設計', '検証 1 回目']);
});

// ---- AC-08：入力の中身は出さない ----

const MARKERS = {
  prompt: 'M-prompt-9f1',
  description: 'M-description-9f2',
  command: 'M-command-9f3',
  file_path: 'M-file-9f4',
  pattern: 'M-pattern-9f5',
  args: 'M-args-9f6',
  content: 'M-content-9f7',
};
const MARKED = REQ(
  uniqueCalls([
    { name: 'Agent', input: { subagent_type: 'agent-a', ...MARKERS } },
    { name: 'Skill', input: { skill: 'skill-s', ...MARKERS } },
    { name: 'Bash', input: MARKERS },
    { name: 'Read', input: MARKERS },
  ]),
);

test('D0047-AC-08: 表の図の状態の項目を JSON にした文字に、prompt・description・command・file_path・pattern・args・content の値が出ない。subagent_type と skill の値は出る', () => {
  const json = JSON.stringify(toolsOf(viewOf(MARKED)));
  for (const [key, marker] of Object.entries(MARKERS)) assert.ok(!json.includes(marker), `${key} の値が表に出ている`);
  assert.ok(json.includes('agent-a'), 'subagent_type の値は出る');
  assert.ok(json.includes('skill-s'), 'skill の値は出る');
});

test('D0047-AC-08: 新しいタブのパネルの HTML にも、ほかの入力の値が出ない。subagent_type と skill の値は出る', async () => {
  const out = await html(toolsOf(viewOf(MARKED)));
  for (const [key, marker] of Object.entries(MARKERS)) assert.ok(!out.includes(marker), `${key} の値がパネルに出ている`);
  assert.ok(out.includes('agent-a') && out.includes('skill-s'));
});

test('D0047-AC-08: 既存の「出力」の欄は対象外で、入力の一部（command・file_path）が今までどおり出る（今のまま通る。守る）', () => {
  const view = viewOf(REQ(uniqueCalls([{ name: 'Bash', input: { command: MARKERS.command } }, { name: 'Read', input: { file_path: MARKERS.file_path } }])));
  const targets = view.terminal.items.flatMap((i) => (i.kind === 'tool' ? [i.target] : []));
  assert.ok(targets.includes(MARKERS.command), 'Bash の command が出力に出る');
  assert.ok(targets.includes(MARKERS.file_path), 'Read の file_path が出力に出る');
});

// ---- AC-09・AC-10：サブエージェントの中の呼び出し ----

test('D0047-AC-09: 発言の行の parent_tool_use_id が 文字・null・項目なし・数・{} の 5 通りでも、表の行は同じ（内訳を分けない）', () => {
  const rows = [undefined, null, 'toolu_parent', 5, {}].map((parent) =>
    tableOf(REQ([assistantParts([toolPart('Read', {}, 'r1'), toolPart('Agent', { subagent_type: 'a' }, 'a1')], parent)])).rows,
  );
  assert.deepEqual(rows[0]!.map((r) => [r.kind, r.name, r.count]), [['agent', 'a', 1], ['tool', 'Read', 1]]);
  for (const other of rows.slice(1)) assert.deepEqual(other, rows[0]);
  for (const row of rows[0]!) assert.deepEqual(Object.keys(row).sort(), ['count', 'durationSec', 'kind', 'name', 'stages']);
});

test('D0047-AC-10: Agent（subagent_type が a）を 1 回呼び、その中（parent_tool_use_id が呼んだ Agent の id）で Read を 3 回呼ぶと、エージェント a が 1 回・道具 Read が 3 回', () => {
  const t = tableOf(
    REQ([
      assistantParts([toolPart('Agent', { subagent_type: 'a' }, 'A1')]),
      ...uniqueCalls([{ name: 'Read', input: { file_path: 'x' }, count: 3, parent: 'A1' }], 'n'),
    ]),
  );
  assert.deepEqual(brief(t), ['agent:a:1', 'tool:Read:3']);
});

test('D0047-AC-10: 入れ子の中の Agent・Task も同じ規則で数え、エージェントの行に足す（入れ子を止めるのは本体の守りで、拡張は止めない）', () => {
  const t = tableOf(
    REQ([
      assistantParts([toolPart('Agent', { subagent_type: 'a' }, 'A1')]),
      assistantParts([toolPart('Agent', { subagent_type: 'a' }, 'A2'), toolPart('Task', { subagent_type: 'b' }, 'T1')], 'A1'),
      assistantParts([toolPart('Read', {}, 'r1')], 'A2'),
    ]),
  );
  assert.deepEqual(brief(t), ['agent:a:2', 'agent:b:1', 'tool:Read:1']);
});

// ---- AC-11：回数は呼んだ数 ----

test('D0047-AC-11: 結果の行（失敗の結果）が有っても、結果が無くても、回数は同じ', () => {
  const call = assistantTool('Read', {}, 'r1');
  const result = JSON.stringify({ _type: 'UserMessage', content: [resultPart('r1', true)] });
  assert.deepEqual(brief(tableOf(REQ([call, result]))), ['tool:Read:1']);
  assert.deepEqual(brief(tableOf(REQ([call]))), ['tool:Read:1']);
});

test('D0047-AC-11: runs[].denials に止めた記録の文が有る記録でも、回数は同じ（止められた呼び出しも、モデルが出した時点でログにあるので数える）', () => {
  const snap = toolsSnapshot({
    runs: [{ seq: 1, stage: 'requirements', denials: ['入れ子の Agent を止めた', 'Agent の回数の上限を超えた'] }],
    logs: [{ seq: 1, stage: 'requirements', lines: uniqueCalls([{ name: 'Agent', input: { subagent_type: 'a' }, count: 3 }]) }],
  });
  assert.deepEqual(brief(tableOf(snap)), ['agent:a:3']);
});

test('D0047-AC-11: 同じ id の部品が 2 つあれば、それぞれ数える（id で重複を除かない）', () => {
  const t = tableOf(REQ([assistantParts([toolPart('Read', {}, 'dup'), toolPart('Read', {}, 'dup')]), assistantTool('Read', {}, 'dup')]));
  assert.deepEqual(brief(t), ['tool:Read:3']);
});

test('D0047-AC-11: Agent を 25 回（max_agent_calls の既定 20 を超える）呼んだ記録は 25 と数える', () => {
  const t = tableOf(REQ(uniqueCalls([{ name: 'Agent', input: { subagent_type: 'a' }, count: 25 }])));
  assert.deepEqual(brief(t), ['agent:a:25']);
});

// ---- AC-13：段の表示名は時系列と同じ元 ----

const read1 = (): string[] => uniqueCalls([{ name: 'Read', input: {} }]);

test('D0047-AC-13: 開発フローの記録（state.json に stages が無い）は STAGE_LABELS の表示名で、回はログのファイル名の回', () => {
  const snap = toolsSnapshot({
    runs: [{ seq: 1, stage: 'requirements' }, { seq: 2, stage: 'design' }, { seq: 3, stage: 'implement', attempt: 1 }],
    logs: [{ seq: 1, stage: 'requirements', lines: read1() }, { seq: 2, stage: 'design', lines: read1() }, { seq: 3, stage: 'implement', attempt: 1, lines: read1() }],
  });
  assert.deepEqual(rowOf(tableOf(snap), 'tool', 'Read').stages, ['要件定義', '設計', '実装 1 回目']);
});

test('D0047-AC-13: パイプの記録は state.json の stages の label を使う。label の無い段名は、ログの名前の段そのまま', () => {
  const snap = toolsSnapshot({
    pipe: 'diagrams',
    stages: DIAGRAMS_STAGES,
    runs: [{ seq: 1, stage: 'survey' }, { seq: 2, stage: 'draw', attempt: 2 }],
    logs: [
      { seq: 1, stage: 'survey', lines: read1() },
      { seq: 2, stage: 'draw', attempt: 2, lines: read1() },
      { seq: 3, stage: 'extra', lines: read1() },
    ],
  });
  assert.deepEqual(rowOf(tableOf(snap), 'tool', 'Read').stages, ['ソースの調査', '図を描く 2 回目', 'extra']);
});

test('D0047-AC-13: state.json が壊れていても表は出て、ログの名前が開発の段ならその表示名、そうでなければ名前のまま', () => {
  const snap = toolsSnapshot({
    stateText: '{"壊れた',
    logs: [{ seq: 1, stage: 'requirements', lines: read1() }, { seq: 2, stage: 'zzz', lines: read1() }],
  });
  assert.deepEqual(rowOf(tableOf(snap), 'tool', 'Read').stages, ['要件定義', 'zzz']);
});

test('D0047-AC-13: 段の名前が constructor（Object のプロパティ名）のログでも、使った段の文字は段の名前そのもの（関数にならない）', () => {
  const snap = toolsSnapshot({ logs: [{ seq: 3, stage: 'constructor', lines: read1() }] });
  const stages = rowOf(tableOf(snap), 'tool', 'Read').stages;
  assert.deepEqual(stages, ['constructor']);
  assert.equal(typeof stages[0], 'string');
});

test('D0047-AC-13: 時系列の行がある記録（見本）では、使った段の文字が時系列の行の label と同じ書き方（通し番号 8 つの順）', () => {
  const run = (seq: number, stage: string, attempt?: number, agent?: string) => ({ seq, stage, ...(attempt === undefined ? {} : { attempt }), ...(agent === undefined ? {} : { agent }), start: seq * 10, durationSec: 5, lines: read1() });
  const snap = ganttSnapshot({
    runs: [run(1, 'requirements'), run(2, 'requirements'), run(3, 'design'), run(4, 'red'), run(5, 'implement', 1), run(6, 'test', 1), run(7, 'implement', 2), run(8, 'test', 2)],
    final: 'PASSED',
  });
  const view = viewOf(snap);
  assert.equal(view.gantt.rows.length, 8);
  assert.deepEqual(rowOf(toolsOf(view), 'tool', 'Read').stages, view.gantt.rows.map((r) => r.label));
});

test('D0047-AC-13: パイプの記録（見本）でも、使った段の文字が時系列の行の label と同じ書き方', () => {
  const run = (seq: number, stage: string, attempt?: number) => ({ seq, stage, ...(attempt === undefined ? {} : { attempt }), start: seq * 10, durationSec: 5, lines: read1() });
  const snap = ganttSnapshot({ pipe: 'diagrams', stages: DIAGRAMS_STAGES, runs: [run(1, 'survey'), run(2, 'draw', 1), run(3, 'verify'), run(4, 'draw', 2), run(5, 'verify', 2)] });
  const view = viewOf(snap);
  assert.deepEqual(rowOf(toolsOf(view), 'tool', 'Read').stages, view.gantt.rows.map((r) => r.label));
  assert.ok(view.gantt.rows.some((r) => r.label === '図を描く 2 回目'), '見本が回つきの label を含む（検査が空振りでない）');
});

test('D0047-AC-13: 段の名前が constructor のとき、時系列の行の label も段の名前そのまま（labelOf の穴を直す。今は関数が入る。設計の「意味が変わるもの」(2)）', () => {
  const snap = toolsSnapshot({
    pipe: 'diagrams',
    stages: DIAGRAMS_STAGES,
    runs: [{ seq: 1, stage: 'survey' }, { seq: 2, stage: 'constructor' }],
    logs: [{ seq: 1, stage: 'survey' }, { seq: 2, stage: 'constructor' }],
  });
  const labels = viewOf(snap).gantt.rows.map((r) => r.label);
  assert.deepEqual(labels.map((l) => typeof l), ['string', 'string'], '時系列の行の label は文字（段名が constructor でも関数にならない）');
  assert.deepEqual(labels, ['ソースの調査', 'constructor']);
});

test('D0047-AC-13: 段の名前が constructor のログでも、表の使った段の文字は時系列の行の label と同じ（表と時系列が同じ元）', () => {
  const snap = toolsSnapshot({
    pipe: 'diagrams',
    stages: DIAGRAMS_STAGES,
    runs: [{ seq: 1, stage: 'survey' }, { seq: 2, stage: 'constructor' }],
    logs: [{ seq: 1, stage: 'survey', lines: read1() }, { seq: 2, stage: 'constructor', lines: read1() }],
  });
  const view = viewOf(snap);
  const stages = rowOf(toolsOf(view), 'tool', 'Read').stages;
  assert.deepEqual(stages, ['ソースの調査', 'constructor']);
  assert.deepEqual(stages, view.gantt.rows.map((r) => r.label));
});

// ---- AC-12：「N 回目」はログのファイル名の回 ----

test('D0047-AC-12: 「N 回目」の元はログのファイル名の回：runs[].attempt が 3 でも、ログが _2 なら使った段は「実装 2 回目」（時系列の行は runs[] に従って「3 回目」で、ここだけ食い違うのが要件の決めた動き）', () => {
  const snap = toolsSnapshot({
    runs: [{ seq: 1, stage: 'implement', attempt: 3 }],
    logs: [{ seq: 1, stage: 'implement', attempt: 2, lines: read1() }],
  });
  const view = viewOf(snap);
  assert.deepEqual(rowOf(toolsOf(view), 'tool', 'Read').stages, ['実装 2 回目']);
  assert.deepEqual(view.gantt.rows.map((r) => r.label), ['実装 3 回目'], '時系列の行は runs[].attempt の回のまま（今のまま。表はこれに合わせない）');
});

test('D0047-AC-12: 動いている段のログ（06_implement_2.jsonl。結果の行なし）でも、受け持ちの行も SDK のエージェント呼び出しの行も、使った段は「実装 2 回目」（動いているログの回もログのファイル名から）', () => {
  const t = tableOf(
    toolsSnapshot({
      driver: 'pipe-dev',
      pipe: 'dev',
      stages: DEV_STAGES,
      runs: [{ seq: 1, stage: 'requirements', agent: 'pipe-in-analyst' }],
      running: { seq: 6, stage: 'implement', attempt: 2, agent: 'pipe-in-coder', lines: uniqueCalls([{ name: 'Agent', input: { subagent_type: 'module-reader' } }]) },
    }),
  );
  assert.deepEqual(rowOf(t, 'agent', 'pipe-in-coder').stages, ['実装 2 回目']);
  assert.deepEqual(rowOf(t, 'agent', 'module-reader').stages, ['実装 2 回目']);
  assert.deepEqual(rowOf(t, 'agent', 'pipe-in-analyst').stages, ['要件定義']);
});

// ---- AC-14：道具ごとの時間は出さない ----

test('D0047-AC-14: TaskNotificationMessage（usage.duration_ms）の行が有っても、SDK の Agent の行の durationSec は null で、数も変わらない', () => {
  const agentCall = assistantTool('Agent', { subagent_type: 'a' }, 'a1');
  const note = JSON.stringify({ _type: 'TaskNotificationMessage', tool_use_id: 'a1', usage: { duration_ms: 5000 } });
  const withNote = tableOf(toolsSnapshot({ runs: [{ seq: 1, stage: 'requirements', durationSec: 300 }], logs: [{ seq: 1, stage: 'requirements', lines: [agentCall, note] }] }));
  const without = tableOf(toolsSnapshot({ runs: [{ seq: 1, stage: 'requirements', durationSec: 300 }], logs: [{ seq: 1, stage: 'requirements', lines: [agentCall] }] }));
  assert.deepEqual(withNote, without);
  assert.equal(rowOf(withNote, 'agent', 'a').durationSec, null);
  assert.equal(rowOf(withNote, 'agent', 'a').count, 1);
  assert.equal(withNote.showTime, false);
});

// ---- AC-16：/pipe-in の記録の begin のあいだと done のあと ----

const PIPE_IN = { driver: 'pipe-dev', pipe: 'dev', stages: DEV_STAGES } as const;

test('D0047-AC-16: /pipe-in の begin のあと（動いているログに agent があり、runs[] が空）は時間の列が無く、done のあと（runs[] に duration_sec）は列が出る', () => {
  const begin = tableOf(toolsSnapshot({ ...PIPE_IN, running: { seq: 1, stage: 'requirements', agent: 'pipe-in-analyst' } }));
  assert.deepEqual(brief(begin), ['agent:pipe-in-analyst:1']);
  assert.equal(begin.showTime, false);
  assert.equal(begin.rows[0]!.durationSec, null);
  const done = tableOf(
    toolsSnapshot({ ...PIPE_IN, runs: [{ seq: 1, stage: 'requirements', agent: 'pipe-in-analyst', durationSec: 95 }], logs: [{ seq: 1, stage: 'requirements', agent: 'pipe-in-analyst' }] }),
  );
  assert.deepEqual(brief(done), ['agent:pipe-in-analyst:1']);
  assert.equal(done.showTime, true);
  assert.equal(done.rows[0]!.durationSec, 95);
});

// ---- AC-17：受け持ち（記録の文字から） ----

const analystLog = (agents: readonly (string | undefined)[], extra?: string) =>
  logText([...agents.map((a) => promptLine('requirements', undefined, a)), ...(extra === undefined ? [] : [extra]), resultLine()]);

test('D0047-AC-17: Prompt が 2 つあるログは、後ろの Prompt の agent を受け持ちにする（runs[].agent が無いとき）', () => {
  const snap = snapshot({
    stateJson: stateJson({ ...PIPE_IN, runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }),
    stageLogs: [{ fileName: '01_requirements.jsonl', text: analystLog(['first', 'second']) }],
  });
  assert.deepEqual(brief(tableOf(snap)), ['agent:second:1']);
});

test('D0047-AC-17: runs[].agent が読めない値（数・空白入り）のときは、ログの agent を使う', () => {
  for (const bad of [5, 'a b', '']) {
    const t = tableOf(toolsSnapshot({ ...PIPE_IN, runs: [{ seq: 1, stage: 'requirements', agent: bad }], logs: [{ seq: 1, stage: 'requirements', agent: 'from-log' }] }));
    assert.deepEqual(brief(t), ['agent:from-log:1'], JSON.stringify(bad));
  }
});

test('D0047-AC-17: runs[] の review・verdict の要素（seq を持たない）は無視する', () => {
  const t = tableOf(
    toolsSnapshot({
      ...PIPE_IN,
      runs: [{ seq: 1, stage: 'requirements', agent: 'pipe-in-analyst' }],
      extras: [
        { stage: 'requirements', review: 'approved' },
        { stage: 'test', attempt: 1, verdict: { status: 'pass', summary: '合格', failures: [], commands: [], command_check: null } },
        { stage: 'red', result: { status: 'red', summary: 'x' } },
      ],
      logs: [{ seq: 1, stage: 'requirements', agent: 'pipe-in-analyst' }],
    }),
  );
  assert.deepEqual(brief(t), ['agent:pipe-in-analyst:1']);
});

test('D0047-AC-17: runs[] に無い終わったログの agent は数えない。動いているログの agent は数える', () => {
  const t = tableOf(
    toolsSnapshot({
      ...PIPE_IN,
      runs: [{ seq: 1, stage: 'requirements', agent: 'a' }],
      logs: [{ seq: 1, stage: 'requirements' }, { seq: 2, stage: 'design', agent: 'orphan' }],
      running: { seq: 3, stage: 'red', agent: 'w' },
    }),
  );
  assert.deepEqual(brief(t).sort(), ['agent:a:1', 'agent:w:1']);
});

test('D0047-AC-17: 時系列との突き合わせ：同じ記録から作った view.gantt.rows の agent と、表の受け持ちの行（回数・使った段）が、通し番号ごとに同じ', () => {
  const plan: [number, string, number | undefined, string][] = [
    [1, 'requirements', undefined, 'pipe-in-analyst'],
    [2, 'requirements', undefined, 'pipe-in-analyst'],
    [3, 'design', undefined, 'pipe-in-analyst'],
    [4, 'red', undefined, 'pipe-in-tester'],
    [5, 'implement', 1, 'pipe-in-coder'],
    [6, 'test', 1, 'pipe-in-verifier'],
    [7, 'implement', 2, 'pipe-in-coder'],
    [8, 'test', 2, 'pipe-in-verifier'],
  ];
  const snap = toolsSnapshot({
    ...PIPE_IN,
    runs: plan.map(([seq, stage, attempt]) => ({ seq, stage, ...(attempt === undefined ? {} : { attempt }), durationSec: 10 })),
    logs: plan.map(([seq, stage, attempt, agent]) => ({ seq, stage, ...(attempt === undefined ? {} : { attempt }), agent })),
    extras: [{ stage: 'requirements', review: 'approved' }],
  });
  const view = viewOf(snap);
  const table = toolsOf(view);
  assert.equal(view.gantt.rows.length, 8);
  const agents = [...new Set(view.gantt.rows.map((r) => r.agent))];
  assert.equal(agents.length, 4, '4 つの受け持ち（検査が空振りでない）');
  for (const name of agents) {
    const rows = view.gantt.rows.filter((r) => r.agent === name);
    const row = rowOf(table, 'agent', name!);
    assert.equal(row.count, rows.length, `${name} の回数`);
    assert.deepEqual(row.stages, rows.map((r) => r.label), `${name} の使った段（時系列の行の label と同じ書き方・同じ順）`);
  }
});

// ---- AC-21・AC-22：案内（state.json の driver から） ----

const withRun = (driver: unknown, agent: string | undefined) =>
  toolsSnapshot({ ...(driver === undefined ? {} : { driver }), pipe: 'dev', stages: DEV_STAGES, runs: [{ seq: 1, stage: 'requirements', ...(agent === undefined ? {} : { agent }) }], logs: [{ seq: 1, stage: 'requirements', agent }] });

test('D0047-AC-21: driver があり、数えた行が 1 つ以上 → 案内 A（受け持ちの行だけでも）', () => {
  assert.equal(tableOf(withRun('pipe-dev', 'pipe-in-analyst')).notice, 'A');
  assert.equal(tableOf(withRun('', 'pipe-in-analyst')).notice, 'A', '空の文字でも「あり」');
  assert.equal(tableOf(toolsSnapshot({ driver: 'pipe-dev', logs: [{ seq: 1, stage: 'requirements', lines: read1() }] })).notice, 'A', '呼び出しの行だけでも');
});

test('D0047-AC-21: driver が無く（項目なし・null）、数えた行が 1 つ以上 → 案内なし（表だけ）', () => {
  assert.equal(tableOf(withRun(undefined, 'pipe-in-analyst')).notice, null);
  assert.equal(tableOf(withRun(null, 'pipe-in-analyst')).notice, null);
});

test('D0047-AC-22: driver があり、数えた行が 0（--agent を付けなかった・古い記録）→ 案内 B だけ', () => {
  const t = tableOf(withRun('pipe-dev', undefined));
  assert.equal(t.notice, 'B');
  assert.deepEqual(t.rows, []);
});

test('D0047-AC-21: driver が無く、数えた行が 0 → 案内なし（空の文）', () => {
  const t = tableOf(withRun(undefined, undefined));
  assert.equal(t.notice, null);
  assert.deepEqual(t.rows, []);
});

// ---- AC-26：数えた行が 0 で driver が無い入力 ----

const EMPTY_SENTENCE = 'エージェント・スキル・道具の呼び出しは、まだ記録にありません。';
const EMPTY_INPUTS: [string, WorkDirSnapshot][] = [
  ['記録もログも無い（noRecords）', snapshot()],
  ['ログは有るが呼び出しが 0', toolsSnapshot({ runs: [{ seq: 1, stage: 'requirements' }], logs: [{ seq: 1, stage: 'requirements' }] })],
  ['記録は有るがログが無い', toolsSnapshot({ runs: [{ seq: 1, stage: 'requirements' }] })],
];
for (const [label, snap] of EMPTY_INPUTS) {
  test(`D0047-AC-26: ${label}とき（driver なし）は、行 0・案内なしで、空の文だけが出る`, async () => {
    const t = tableOf(snap);
    assert.deepEqual(t.rows, []);
    assert.equal(t.notice, null);
    const out = await html(t);
    assert.ok(out.includes(EMPTY_SENTENCE));
    assert.ok(!out.includes('<table') && !out.includes('tools-summary') && !out.includes('tools-notice'), '表・要約・案内が無い');
  });
}

test('D0047-AC-26: noRecords の図の状態は、表も空の文の側（記録が無いことを案内 B などにしない）', () => {
  const view = viewOf(snapshot());
  assert.ok(view.noRecords !== null);
  assert.equal(toolsOf(view).notice, null);
});

// ---- AC-33：同じ写しからは同じ HTML（時計を読まない） ----

test('D0047-AC-33: 同じ写しを clockAt(0)・clockAt(99999)・時計なしで組み立てても、表も、表の HTML も同じ', async () => {
  const snap = toolsSnapshot({
    ...PIPE_IN,
    runs: [{ seq: 1, stage: 'requirements', agent: 'pipe-in-analyst', durationSec: 12 }],
    logs: [{ seq: 1, stage: 'requirements', agent: 'pipe-in-analyst', lines: uniqueCalls([{ name: 'Read', count: 3 }, { name: 'Skill', input: { skill: 's' } }]) }],
    running: { seq: 2, stage: 'design', agent: 'pipe-in-analyst', lines: read1(), at: '2026-10-17T10:00:00+00:00' },
  });
  const tables = [clockAt(0), clockAt(99999), undefined].map((clock) => tableOf(snap, clock));
  assert.deepEqual(tables[1], tables[0]);
  assert.deepEqual(tables[2], tables[0]);
  const outs = await Promise.all(tables.map((t) => html(t)));
  assert.equal(outs[1], outs[0]);
  assert.equal(outs[2], outs[0]);
});

test('D0047-AC-33: Date.now を投げる関数に替えても、表と HTML ができて、同じ結果になる（表を作る部品が時計を読まない）', async () => {
  const snap = toolsSnapshot({ ...PIPE_IN, runs: [{ seq: 1, stage: 'requirements', agent: 'x', durationSec: 5 }], logs: [{ seq: 1, stage: 'requirements', agent: 'x', lines: read1() }] });
  const normal = tableOf(snap, clockAt(0));
  const tools = await needModule<HtmlMod>(import.meta.url, '../view/toolsHtml.ts');
  const expected = tools.renderTools(normal);
  const real = Date.now;
  const made: { table?: Tools; out?: string } = {};
  try {
    Date.now = () => {
      throw new Error('表を作る部品が時計（Date.now）を読んだ');
    };
    made.table = toolsOf(build(snap, clockAt(0)));
    made.out = tools.renderTools(made.table);
  } finally {
    Date.now = real;
  }
  assert.deepEqual(made.table, normal);
  assert.equal(made.out, expected);
});

// ---- AC-34：動いている実行は描き直しで増える ----

test('D0047-AC-34: 動いている段のログに呼び出しが増えた写しは、回数が増え・行が増え・並びが入れ替わった表になる（HTML も変わる）', async () => {
  const lines = (extra: readonly string[]) => [...uniqueCalls([{ name: 'Read', count: 3 }, { name: 'Grep', count: 1 }]), ...extra];
  const snapBefore = toolsSnapshot({ running: { seq: 1, stage: 'requirements', lines: lines([]) } });
  const snapAfter = toolsSnapshot({ running: { seq: 1, stage: 'requirements', lines: lines(uniqueCalls([{ name: 'Grep', count: 3 }, { name: 'NewTool' }], 'x')) } });
  const a = tableOf(snapBefore);
  const b = tableOf(snapAfter);
  assert.deepEqual(brief(a), ['tool:Read:3', 'tool:Grep:1']);
  assert.deepEqual(brief(b), ['tool:Grep:4', 'tool:Read:3', 'tool:NewTool:1'], '回数が増え、NewTool の行が増え、Grep が Read を抜いて並びが入れ替わる');
  assert.equal(b.total, a.total + 4);
  assert.notEqual(await html(b), await html(a));
});

// ---- AC-41：一覧の行のための図の状態には表が無い ----

test('D0047-AC-41: { tools: false } の図の状態は tools が null。既定（オプションなし）は表があって行を持つ。2 つは tools 以外が同じ', () => {
  const snap = REQ(uniqueCalls([{ name: 'Read', count: 2 }, { name: 'Skill', input: { skill: 's' } }]));
  const clock = clockAt(0);
  const without = build(snap, clock, { tools: false });
  const withTools = build(snap, clock);
  assert.equal((without as unknown as { tools?: unknown }).tools, null, '{ tools: false } は null（作らなかった）');
  assert.ok(toolsOf(withTools).rows.length > 0);
  const strip = (v: PipelineView): object => {
    const copy: Record<string, unknown> = { ...(v as unknown as Record<string, unknown>) };
    delete copy.tools;
    return copy;
  };
  assert.deepStrictEqual(strip(without), strip(withTools), '表の有る無しで、ほかの項目（節・時系列・使用量・成果物）は変わらない');
});

test('D0047-AC-41: { tools: true } を渡しても、既定と同じ表ができる', () => {
  const snap = REQ(uniqueCalls([{ name: 'Read', count: 2 }]));
  assert.deepEqual(toolsOf(build(snap, clockAt(0), { tools: true })), toolsOf(build(snap, clockAt(0))));
});

// ---- AC-43：古い記録・壊れた state.json でも読める ----

test('D0047-AC-43: state.json が無い・壊れている・stages が無い古い形でも、ログが有れば表が出る（段の表示名は AC-13 のとおり）', () => {
  const logs = [{ seq: 1, stage: 'requirements', lines: uniqueCalls([{ name: 'Read' }, { name: 'Skill', input: { skill: 's' } }]) }];
  for (const [label, stateText] of [['無い', null], ['壊れた JSON', '{"runs": ['], ['配列の JSON', '[1]'], ['空のオブジェクト', '{}']] as [string, string | null][]) {
    const t = tableOf(toolsSnapshot({ stateText, logs }));
    assert.deepEqual(brief(t), ['skill:s:1', 'tool:Read:1'], label);
  }
  const old = tableOf(toolsSnapshot({ logs }));
  assert.deepEqual(brief(old), ['skill:s:1', 'tool:Read:1'], 'stages の無い古い形');
});

test('D0047-AC-43: runs[].agent が壊れている（数・空白入り）記録でも、例外なく呼び出しの表が出る', () => {
  const t = tableOf(
    toolsSnapshot({
      runs: [{ seq: 1, stage: 'requirements', agent: 5 }, { seq: 2, stage: 'design', agent: 'a b' }],
      logs: [{ seq: 1, stage: 'requirements', lines: read1() }, { seq: 2, stage: 'design', lines: read1() }],
    }),
  );
  assert.deepEqual(brief(t), ['tool:Read:2']);
});

test('D0047-AC-43: state.json が壊れた /pipe-in の記録（Prompt に agent・ResultMessage で終わる）は、受け持ちの行も案内も出ず、行 0・案内なし（空の文）', () => {
  const snap = snapshot({ stateJson: '{"壊れた', stageLogs: [{ fileName: '01_requirements.jsonl', text: analystLog(['pipe-in-analyst']) }] });
  const t = tableOf(snap);
  assert.deepEqual(t.rows, []);
  assert.equal(t.notice, null);
});

const FIXTURE_RUNS: [string, string][] = [
  ['pipe_dev', 'finished'],
  ['pipe_dev', 'running'],
  ['pipe_dev', 'waiting'],
  ['pipe_in', 'finished'],
  ['pipe_in', 'running'],
  ['pipe_in', 'waiting'],
];
for (const [dir, name] of FIXTURE_RUNS) {
  test(`D0047-AC-43: 見本の記録 tests/fixtures/${dir}/${name} を読んでも例外なく、agent が無いので行 0・案内 B（driver はあるが数えた行が無い）`, () => {
    const t = tableOf(fixtureSnapshot(dir, name));
    assert.deepEqual(t.rows, []);
    assert.equal(t.notice, 'B');
  });
}

// ---- AC-44：__proto__ などの名前（記録の文字から） ----

test('D0047-AC-44: 道具の名前が __proto__・constructor・toString でも、記録の文字から読んで、それぞれ 1 行（ほかの行を壊さない）', () => {
  const t = tableOf(REQ([...PROTO_NAMES.flatMap((n) => uniqueCalls([{ name: n }], `p${n}`)), ...uniqueCalls([{ name: 'Read', count: 2 }])]));
  for (const name of PROTO_NAMES) assert.equal(rowOf(t, 'tool', name).count, 1, name);
  assert.equal(rowOf(t, 'tool', 'Read').count, 2);
  assert.equal(t.kinds, 4);
});

test('D0047-AC-44: subagent_type・skill に __proto__ などを入れても、それぞれ 1 行。input の自分の鍵 __proto__（JSON.parse）は「（指定なし）」', () => {
  const nasty = `{"_type":"AssistantMessage","content":[{"id":"z1","name":"Agent","input":{"__proto__":{"subagent_type":"polluted"}}}]}`;
  const t = tableOf(
    REQ([
      ...PROTO_NAMES.flatMap((n) => uniqueCalls([{ name: 'Agent', input: { subagent_type: n } }, { name: 'Skill', input: { skill: n } }], `q${n}`)),
      nasty,
    ]),
  );
  for (const name of PROTO_NAMES) {
    assert.equal(rowOf(t, 'agent', name).count, 1, `agent ${name}`);
    assert.equal(rowOf(t, 'skill', name).count, 1, `skill ${name}`);
  }
  assert.equal(rowOf(t, 'agent', UNSPECIFIED).count, 1);
  assert.ok(!t.rows.some((r) => r.name === 'polluted'));
});

test('D0047-AC-44: Object.prototype に subagent_type・skill が（一時的に）あっても、鍵を省いた Agent・Skill は「（指定なし）」の行で、継承された値の名前の行はできない（自分の鍵だけを読む）', () => {
  const snap = REQ(uniqueCalls([{ name: 'Agent', input: {} }, { name: 'Skill', input: {} }, { name: 'Task', input: { skill: 'x' } }]));
  const t = withPollutedPrototype({ subagent_type: 'polluted', skill: 'polluted' }, () => tableOf(snap));
  assert.deepEqual(brief(t), [`agent:${UNSPECIFIED}:2`, `skill:${UNSPECIFIED}:1`]);
  assert.ok(!t.rows.some((r) => r.name === 'polluted'));
});

// ---- 外から来た文字（図の状態は生の文字を持ち、escape は view） ----

test('D0047-AC-35: 図の状態の表は生の文字を持つ（escape は view で 1 回だけ）：外から来た名前・段の表示名がそのまま入る', () => {
  const stages = [{ name: 'draw', label: HOSTILE[0]!, output: 'a.md', review: false }];
  const snap = toolsSnapshot({
    pipe: 'p',
    stages,
    runs: [{ seq: 1, stage: 'draw' }],
    logs: [{ seq: 1, stage: 'draw', lines: uniqueCalls([{ name: HOSTILE[0]! }, { name: 'Agent', input: { subagent_type: HOSTILE[2]! } }, { name: 'Skill', input: { skill: HOSTILE[3]! } }]) }],
  });
  const t = tableOf(snap);
  assert.deepEqual(rowOf(t, 'tool', HOSTILE[0]!).stages, [HOSTILE[0]!], '段の表示名もそのまま');
  assert.equal(rowOf(t, 'agent', HOSTILE[2]!).count, 1);
  assert.equal(rowOf(t, 'skill', HOSTILE[3]!).count, 1);
  assert.ok(!JSON.stringify(t).includes('&lt;'), '図の状態の段階では escape しない');
});

// ---- AC-45：極端な入力 ----

const LIMIT_MS = 5000;
const bigSnapshot = (calls: number, names: number, hugeInputBytes = 0): WorkDirSnapshot =>
  snapshot({
    stateJson: stateJson({ runs: [] }),
    stageLogs: [{ fileName: '01_requirements.jsonl', text: bigLog({ calls, names, hugeInputBytes }) }],
    artifacts: { '00_input.md': 'メモ' },
  });

test('D0047-AC-45: 呼び出し 10 万回・名前 1 万種類・入力が 1 MiB の 1 行でも、例外なく、5000ms 未満で表と HTML ができる（先に行が 100 有ることを確かめる）', () => {
  const snap = bigSnapshot(100_000, 10_000, 1024 * 1024);
  const started = performance.now();
  const view = viewOf(snap, clockAt(0));
  const body = renderViewBody(view);
  const elapsed = performance.now() - started;
  const t = toolsOf(view);
  assert.equal(t.rows.length, 100, '表の行は上限の 100 行');
  assert.equal(t.kinds, 10_001, '1 万種類の名前＋Bash（1 MiB の入力の行）');
  assert.equal(t.total, 100_001);
  assert.ok(body.includes('data-detail-panel="tools"'), 'tools のパネルが HTML に入っている');
  assert.ok(elapsed < LIMIT_MS, `${Math.round(elapsed)}ms（上限 ${LIMIT_MS}ms）`);
});

// 呼び出しの数を 2 倍にしたときの時間の伸び（2.5 倍以内）は、ここでは測らない。この全体（parse → 表 → renderViewBody）の時間は、
// 既存の「出力」の欄の 10 万項目の組み立てと GC が支配し、正しい実装でも負荷しだいで比が 2.5 倍を超える（読み手の確かめで、並列 6 の 36 回中 2 回落ち、比だけを 48 回取ると最大 3.17 だった）。
// 比は、新しく足した表を作る部品だけを測る（domain/toolsTable.test.ts の D0047-AC-45）。ここは、絶対の上限と、HTML の長さの頭打ちだけを見る。

test('D0047-AC-45: 同じ 120 名で呼び出しだけを 10 倍にしても、tools の HTML の長さは 1.1 倍以内（行の上限 100 で頭打ちで、呼び出しの数に比例しない）', async () => {
  const lengths: number[] = [];
  for (const calls of [1_200, 12_000]) {
    const t = toolsOf(viewOf(bigSnapshot(calls, 120), clockAt(0)));
    assert.equal(t.rows.length, 100, `${calls} 回：行が 100 有る`);
    lengths.push((await html(t)).length);
  }
  assert.ok(lengths[1]! <= lengths[0]! * 1.1, `${lengths[0]} → ${lengths[1]}`);
});
