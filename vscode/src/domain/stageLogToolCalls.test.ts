// 段のログの呼び出しの数え上げ（D0049）：parseStageLog(text, { calls: true }) が返す calls（{ kind, name }）。
// 出力の道具の行と同じ判定（partOf 1 つ）から出ること、エージェント・スキル・道具の見分け、入力の中身を持ち出さないこと、
// サブエージェントの中の発言も同じ規則で数えること、壊れた部品・行でも例外を出さないことを確かめる。
// parseStageLog の第 2 引数と戻りの calls は、実装の段で足される。呼び出しの前に型を緩めた形（parse）で受け、calls が返らなければ落とす。
// 「calls を頼まなければ項目ごと無い」ことと、実物のソースの判定が 1 か所であること（tool_use_id・thinking が各 1 回）は、今のまま通る（守る）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseStageLog } from './stageLog.ts';
import { assistantParts, assistantText, assistantTool, logText, promptLine, resultPart, thinkingPart, toolPart } from '../test/fixtures.ts';
import { fixtureSnapshot } from '../test/liveFixtures.ts';
import { withoutComments } from '../test/sourceText.ts';
import { withPollutedPrototype } from '../test/toolsFixtures.ts';

interface Call {
  kind: string;
  name?: unknown;
}
interface CallsLog {
  items: { kind: string; tool?: string; target?: string | null; text?: string }[];
  hasPrompt: boolean;
  finished: boolean;
  startedAt: string | null;
  agent: string | null;
  calls?: Call[];
}
/** 第 2 引数（{ calls: true }）は実装の段で足される。型を緩めて呼ぶ（テスト先行のときも型検査が通るように） */
const parse = parseStageLog as unknown as (text: string, options?: { calls?: boolean }) => CallsLog;

/** calls を頼んで読み、calls の配列を返す。calls が返らなければ落とす（まだ作っていない） */
function callsOf(text: string): Call[] {
  const log = parse(text, { calls: true });
  assert.ok(Array.isArray(log.calls), 'parseStageLog(text, { calls: true }) が calls を返す（まだ作っていない）');
  return log.calls;
}
/** [kind, name] の組。name が無い（undefined）ときは undefined のまま。 */
const pairs = (calls: readonly Call[]): [string, unknown][] => calls.map((c) => [c.kind, c.name]);
/** 'tool:Read' の形の文字（name が文字のときの見やすい書き方） */
const tags = (calls: readonly Call[]): string[] => calls.map((c) => `${c.kind}:${String(c.name)}`);
const log = (...lines: string[]): string => logText([promptLine('x'), ...lines]);
const noPrompt = (...lines: string[]): string => logText(lines);

// ---- AC-01：数える呼び出しの判定（出力の道具の行と同じ判定） ----

const user = (...parts: unknown[]): string => JSON.stringify({ _type: 'UserMessage', content: parts });
const raw = (message: object): string => JSON.stringify(message);
const READ = toolPart('Read', { file_path: 'a.py' }, 'r1');

interface Case {
  label: string;
  text: string;
  /** 'kind:name' の並び */
  want: string[];
}
const AC01: Case[] = [
  { label: '部品 { id, name, input } は数える', text: log(assistantParts([READ])), want: ['tool:Read'] },
  { label: '部品 { name, input }（id が無い）も数える', text: log(assistantParts([{ name: 'Read', input: {} }])), want: ['tool:Read'] },
  { label: '1 つの発言の部品が 2 つなら、順に 2 つ数える', text: log(assistantParts([READ, toolPart('Grep', {}, 'g1')])), want: ['tool:Read', 'tool:Grep'] },
  {
    label: 'tool_use_id の鍵を持つ部品は、name・input もある形でも数えない',
    text: log(assistantParts([{ tool_use_id: 'x', name: 'Read', input: {} }])),
    want: [],
  },
  {
    label: 'thinking の鍵を持つ部品は、name・input もある形でも数えない',
    text: log(assistantParts([{ thinking: '考え中', name: 'Read', input: {} }])),
    want: [],
  },
  { label: '考え中の部品（thinking・signature）は数えない', text: log(assistantParts([thinkingPart()])), want: [] },
  { label: '文章の部品は数えない', text: log(assistantText('こんにちは')), want: [] },
  { label: '結果（UserMessage）の部品は数えない', text: log(user(resultPart('r1', true))), want: [] },
  {
    label: '結果の行に呼び出しの形の部品があっても、UserMessage なので数えない',
    text: log(user({ id: 'u1', name: 'Read', input: {} })),
    want: [],
  },
  {
    label: 'TaskNotificationMessage（知らない _type）の行は、呼び出しの形の部品を持っていても数えない',
    text: log(raw({ _type: 'TaskNotificationMessage', tool_use_id: 'a1', usage: { duration_ms: 5000 }, content: [{ id: 'n1', name: 'Read', input: {} }] })),
    want: [],
  },
  { label: '知らない _type の行は数えない', text: log(raw({ _type: 'SystemMessage', content: [{ id: 's1', name: 'Read', input: {} }] })), want: [] },
  { label: '壊れた行（途中までの JSON）は数えない', text: log('{"_type":"AssistantMessage","content":[{"id":"a","name":"Re'), want: [] },
  { label: 'JSON でない行・配列の行・数の行は数えない', text: log('これは JSON ではない', '[1,2,3]', '42'), want: [] },
  { label: 'name が数の部品は数えない', text: log(assistantParts([{ id: 'a', name: 5, input: {} }])), want: [] },
  { label: 'name が null の部品は数えない', text: log(assistantParts([{ id: 'a', name: null, input: {} }])), want: [] },
  { label: 'input が配列の部品は数えない', text: log(assistantParts([{ id: 'a', name: 'Read', input: [] }])), want: [] },
  { label: 'input が null の部品は数えない', text: log(assistantParts([{ id: 'a', name: 'Read', input: null }])), want: [] },
  { label: 'input が文字の部品は数えない', text: log(assistantParts([{ id: 'a', name: 'Read', input: 'x' }])), want: [] },
  { label: 'input の無い部品は数えない', text: log(assistantParts([{ id: 'a', name: 'Read' }])), want: [] },
  {
    label: '範囲は最後の Prompt 行より後ろだけ（前の試みの呼び出しは数えない）',
    text: logText([promptLine('x'), assistantParts([toolPart('Old', {}, 'o1')]), promptLine('x'), assistantParts([toolPart('New', {}, 'n1')])]),
    want: ['tool:New'],
  },
  {
    label: 'Prompt 行が無いログは全行を数える（出力と同じ）',
    text: noPrompt(assistantParts([toolPart('A', {}, 'a1')]), assistantParts([toolPart('B', {}, 'b1')])),
    want: ['tool:A', 'tool:B'],
  },
];
for (const c of AC01) {
  test(`D0049-AC-01: ${c.label}`, () => {
    assert.deepEqual(tags(callsOf(c.text)), c.want);
  });
}

test('D0049-AC-01: 判定は stageLog.ts の 1 か所だけ（コメントを除いたソースに tool_use_id・thinking が各 1 回）（今のまま通る。守る）', () => {
  const source = readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), 'stageLog.ts'), 'utf8');
  assert.equal(mentions(source, 'tool_use_id'), 1, 'tool_use_id を弾く判定は 1 か所');
  assert.equal(mentions(source, 'thinking'), 1, 'thinking を弾く判定は 1 か所');
});

/** コメントを除いたソースに、語（ふつうの文字）が何回出るか。行頭のコメントは数えず、行の後ろのコメントは数える（行の後ろにも書かない決まり） */
function mentions(source: string, word: string): number {
  return withoutComments(source).split(word).length - 1;
}

test('D0049-AC-01: 検査そのもの：mentions は、2 回のソースは 2、1 回＋行頭のコメントでの言及は 1、0 回は 0、行の後ろのコメントでの言及は数える（今のまま通る。守る）', () => {
  assert.equal(mentions("if ('tool_use_id' in a) return null;\nif ('tool_use_id' in b) return null;", 'tool_use_id'), 2);
  assert.equal(mentions("// tool_use_id は結果の部品\nif ('tool_use_id' in a) return null;", 'tool_use_id'), 1);
  assert.equal(mentions("/** tool_use_id を弾く */\nif ('tool_use_id' in a) return null;", 'tool_use_id'), 1);
  assert.equal(mentions('const x = 1;', 'tool_use_id'), 0);
  assert.equal(mentions("if ('tool_use_id' in a) return null; // tool_use_id", 'tool_use_id'), 2, '行の後ろのコメントは数える');
});

test('D0049-AC-01: calls を頼まなければ、これまでと同じ読みで、calls の項目ごと無い（{} や { calls: false } を渡しても）（今のまま通る。守る）', () => {
  const text = log(assistantParts([READ]), assistantText('文章'));
  for (const options of [undefined, {}, { calls: false }]) {
    const read = parse(text, options);
    assert.equal(Object.hasOwn(read, 'calls'), false, JSON.stringify(options));
    assert.deepEqual(read.items, [{ kind: 'tool', tool: 'Read', target: 'a.py' }, { kind: 'text', text: '文章' }]);
  }
});

test('D0049-AC-01: calls を頼んでも、出力の項目・Prompt の有無・終わり・始まりの時刻・受け持ちは、頼まないときと同じ（今のまま通る。守る）', () => {
  const text = logText([promptLine('x', '2026-10-17T10:00:00+00:00', 'pipe-in-analyst'), assistantParts([READ]), assistantText('文章')]);
  const without = parse(text);
  const withCalls = parse(text, { calls: true });
  assert.deepEqual({ ...withCalls, calls: undefined }, { ...without, calls: undefined });
});

// ---- AC-02：数えた呼び出しの数は、出力の道具の行の数と同じ ----

const toolItems = (l: CallsLog): string[] => l.items.filter((i) => i.kind === 'tool').map((i) => i.tool ?? '');

const AC02: { label: string; text: string; count: number }[] = [
  {
    label: 'tool_use_id を持つ部品（name・input もある形）を混ぜたログ',
    text: log(assistantParts([READ, { tool_use_id: 'x', name: 'Hidden', input: {} }, toolPart('Grep', {}, 'g1')])),
    count: 2,
  },
  {
    label: 'thinking を持つ部品（name・input もある形）を混ぜたログ',
    text: log(assistantParts([{ thinking: '考え中', name: 'Hidden', input: {} }, READ])),
    count: 1,
  },
  {
    label: 'Prompt が複数あるログ（最後より後ろだけ）',
    text: logText([promptLine('x'), assistantParts([toolPart('Old', {}, 'o1')]), promptLine('x'), assistantParts([READ, toolPart('Grep', {}, 'g1')])]),
    count: 2,
  },
  { label: 'Prompt が無いログ（全行）', text: noPrompt(assistantParts([READ]), assistantParts([toolPart('Grep', {}, 'g1')]), assistantText('文章')), count: 2 },
  {
    label: '壊れた行・途中までの行を混ぜたログ',
    text: log('{"_type":"AssistantMessage","content":[{"id":"a","na', assistantParts([READ]), 'ごみの行', assistantParts([toolPart('Grep', {}, 'g1')])),
    count: 2,
  },
  { label: '空のログ', text: '', count: 0 },
];
for (const c of AC02) {
  test(`D0049-AC-02: ${c.label}で、calls の数は出力の道具の行の数と同じ（名前の並びも同じ）`, () => {
    const read = parse(c.text, { calls: true });
    assert.ok(Array.isArray(read.calls), 'calls が返る（まだ作っていない）');
    assert.equal(toolItems(read).length, c.count, '出力の道具の行の数（見本の数が合っている）');
    assert.equal(read.calls.length, toolItems(read).length);
    assert.deepEqual(
      read.calls.map((call) => call.name),
      toolItems(read),
    );
  });
}

test('D0049-AC-02: Agent・Task・Skill・MCP の道具を混ぜたログでも、calls の数は出力の道具の行の数と同じで、出力の項目は calls を頼まないときと同じ（頼んだときだけ行を落とさない）', () => {
  const text = log(
    assistantParts([READ, toolPart('Agent', { subagent_type: 'a' }, 'a1'), toolPart('Task', {}, 't1')]),
    assistantParts([toolPart('Skill', { skill: 's' }, 's1'), toolPart('mcp__jira__get_issue', {}, 'm1')], 'a1'),
  );
  const withCalls = parse(text, { calls: true });
  assert.ok(Array.isArray(withCalls.calls), 'calls が返る（まだ作っていない）');
  const without = parse(text);
  assert.deepEqual(toolItems(without), ['Read', 'Agent', 'Task', 'Skill', 'mcp__jira__get_issue'], '出力の道具の行（見本が合っている）');
  assert.deepEqual(withCalls.items, without.items, 'calls を頼んでも、出力の道具の行は同じ（Agent・Task・Skill の行を落とさない）');
  assert.equal(withCalls.calls.length, toolItems(without).length);
  assert.deepEqual(tags(withCalls.calls), ['tool:Read', 'agent:a', 'agent:undefined', 'skill:s', 'tool:mcp__jira__get_issue']);
});

test('D0049-AC-02: 実物の形のログ（tests/fixtures/showcase の 8 つ。SystemMessage・RateLimitEvent・ResultMessage 入りで、発言に parent_tool_use_id: null が付く）でも、ログごとに calls の数と名前の並びは出力の道具の行と同じ（合計 21）', () => {
  const files = fixtureSnapshot('showcase').stageLogs;
  assert.equal(files.length, 8, '見本のログが 8 つ読めている（検査が空振りでない）');
  let total = 0;
  for (const file of files) {
    const read = parse(file.text, { calls: true });
    assert.ok(Array.isArray(read.calls), `${file.fileName}: calls が返る（まだ作っていない）`);
    assert.deepEqual(
      read.calls.map((call) => call.name),
      toolItems(read),
      file.fileName,
    );
    total += read.calls.length;
  }
  assert.equal(total, 21, '見本の道具の呼び出しの合計');
});

// ---- AC-05：エージェント・スキル・道具の見分け ----

const AC05:{ label: string; part: unknown; want: [string, unknown] }[] = [
  { label: 'Agent と subagent_type → エージェント（名前は subagent_type）', part: toolPart('Agent', { subagent_type: 'a' }, 'p1'), want: ['agent', 'a'] },
  { label: 'Task（旧名）と subagent_type → エージェント', part: toolPart('Task', { subagent_type: 'a' }, 'p1'), want: ['agent', 'a'] },
  { label: 'Skill と skill → スキル（名前は skill）', part: toolPart('Skill', { skill: 's' }, 'p1'), want: ['skill', 's'] },
  { label: 'Read → 道具（名前は name のまま）', part: toolPart('Read', { file_path: 'a' }, 'p1'), want: ['tool', 'Read'] },
  { label: 'mcp__jira__get_issue → 道具（MCP の道具も道具）', part: toolPart('mcp__jira__get_issue', {}, 'p1'), want: ['tool', 'mcp__jira__get_issue'] },
  { label: 'agent（小文字）→ 道具（大文字小文字を区別する）', part: toolPart('agent', { subagent_type: 'a' }, 'p1'), want: ['tool', 'agent'] },
  { label: 'AGENT → 道具', part: toolPart('AGENT', { subagent_type: 'a' }, 'p1'), want: ['tool', 'AGENT'] },
  { label: 'task（小文字）→ 道具', part: toolPart('task', { subagent_type: 'a' }, 'p1'), want: ['tool', 'task'] },
  { label: 'skill（小文字）→ 道具', part: toolPart('skill', { skill: 's' }, 'p1'), want: ['tool', 'skill'] },
  { label: '鍵の取り違え：Agent と { skill } → エージェントで名前は無い（skill を subagent_type と読まない）', part: toolPart('Agent', { skill: 's' }, 'p1'), want: ['agent', undefined] },
  { label: '鍵の取り違え：Skill と { subagent_type } → スキルで名前は無い', part: toolPart('Skill', { subagent_type: 'a' }, 'p1'), want: ['skill', undefined] },
  { label: 'Agent と {}（subagent_type を省いた呼び出し）→ エージェントで名前は無い', part: toolPart('Agent', {}, 'p1'), want: ['agent', undefined] },
  { label: 'Skill と {} → スキルで名前は無い', part: toolPart('Skill', {}, 'p1'), want: ['skill', undefined] },
  { label: 'subagent_type が数 → 生の値のまま渡す（読めない名前にするのは表を作る側）', part: toolPart('Agent', { subagent_type: 5 }, 'p1'), want: ['agent', 5] },
  { label: 'skill が null → 生の値のまま渡す', part: toolPart('Skill', { skill: null }, 'p1'), want: ['skill', null] },
  { label: 'subagent_type が空の文字 → 生の値のまま渡す', part: toolPart('Agent', { subagent_type: '' }, 'p1'), want: ['agent', ''] },
];
for (const c of AC05) {
  test(`D0049-AC-05: ${c.label}`, () => {
    assert.deepEqual(pairs(callsOf(log(assistantParts([c.part])))), [c.want]);
  });
}

test('D0049-AC-05: input に自分の鍵 __proto__ があっても、中の subagent_type・skill とは読まない（名前の取り違えを見る補助。JSON.parse は __proto__ を自分の鍵として作るだけで、プロトタイプは替わらない）', () => {
  const agent = `{"_type":"AssistantMessage","content":[{"id":"a1","name":"Agent","input":{"__proto__":{"subagent_type":"polluted"}}}]}`;
  const skill = `{"_type":"AssistantMessage","content":[{"id":"s1","name":"Skill","input":{"__proto__":{"skill":"polluted"}}}]}`;
  assert.deepEqual(pairs(callsOf(log(agent, skill))), [
    ['agent', undefined],
    ['skill', undefined],
  ]);
});

test('D0049-AC-05: 入力の自分の鍵だけを読む：Object.prototype に subagent_type・skill が（一時的に）あっても、鍵を省いた Agent・Task・Skill の名前は undefined（継承された値を名前にしない）', () => {
  const text = log(assistantParts([toolPart('Agent', {}, 'a1'), toolPart('Task', { skill: 'x' }, 't1'), toolPart('Skill', {}, 's1')]));
  const calls = withPollutedPrototype({ subagent_type: 'polluted', skill: 'polluted' }, () => callsOf(text));
  assert.deepEqual(pairs(calls), [
    ['agent', undefined],
    ['agent', undefined],
    ['skill', undefined],
  ]);
  assert.equal(Object.hasOwn(Object.prototype, 'subagent_type'), false, '足した鍵を元に戻している');
});

// ---- AC-08：calls に入る入力は名前だけ（プロンプトなどを持ち出さない） ----

test('D0049-AC-08: calls の要素のキーは kind と name だけ（prompt・description・command・file_path・pattern・args・content は持ち出さない）', () => {
  const markers = {
    prompt: 'M-prompt',
    description: 'M-description',
    command: 'M-command',
    file_path: 'M-file',
    pattern: 'M-pattern',
    args: 'M-args',
    content: 'M-content',
  };
  const calls = callsOf(
    log(
      assistantParts([
        toolPart('Agent', { subagent_type: 'agent-a', ...markers }, 'a1'),
        toolPart('Skill', { skill: 'skill-s', ...markers }, 's1'),
        toolPart('Bash', markers, 'b1'),
        toolPart('Read', markers, 'r1'),
      ]),
    ),
  );
  assert.equal(calls.length, 4, '4 つの呼び出しを数えている（検査が空振りでない）');
  for (const call of calls) {
    for (const key of Object.keys(call)) assert.ok(key === 'kind' || key === 'name', `calls の要素に ${key} がある`);
  }
  const json = JSON.stringify(calls);
  for (const marker of Object.values(markers)) assert.ok(!json.includes(marker), `calls に ${marker} がある`);
  assert.deepEqual(
    pairs(calls),
    [
      ['agent', 'agent-a'],
      ['skill', 'skill-s'],
      ['tool', 'Bash'],
      ['tool', 'Read'],
    ],
    'subagent_type と skill の値は出る',
  );
});

// ---- AC-09：parent_tool_use_id は数え方に使わない ----

const PARENTS: [string, unknown][] = [
  ['文字（サブエージェントの中）', 'toolu_parent'],
  ['null（メイン）', null],
  ['項目が無い', undefined],
  ['数', 5],
  ['オブジェクト', {}],
];
for (const [label, parent] of PARENTS) {
  test(`D0049-AC-09: 発言の行の parent_tool_use_id が ${label} でも、その行の呼び出しは同じ規則で数える`, () => {
    const calls = callsOf(log(assistantParts([toolPart('Read', {}, 'r1'), toolPart('Agent', { subagent_type: 'a' }, 'a1')], parent)));
    assert.deepEqual(pairs(calls), [
      ['tool', 'Read'],
      ['agent', 'a'],
    ]);
  });
}

test('D0049-AC-09: parent_tool_use_id を部品の項目に置いても（部品の項目ではない）、数え方は変わらない', () => {
  const calls = callsOf(log(assistantParts([{ id: 'r1', name: 'Read', input: {}, parent_tool_use_id: 'x' }])));
  assert.deepEqual(pairs(calls), [['tool', 'Read']]);
});

// ---- AC-11：回数は呼んだ数（結果・成否・重複を見ない） ----

test('D0049-AC-11: 同じ id の部品が 2 つあっても、それぞれ数える（同じ行の中でも、別の行でも）', () => {
  const sameLine = callsOf(log(assistantParts([toolPart('Read', {}, 'dup'), toolPart('Read', {}, 'dup')])));
  const twoLines = callsOf(log(assistantTool('Read', {}, 'dup'), assistantTool('Read', {}, 'dup')));
  assert.equal(sameLine.length, 2);
  assert.equal(twoLines.length, 2);
});

test('D0049-AC-11: 結果の行（失敗の結果も）があっても、結果が無くても、数は同じ', () => {
  const call = assistantTool('Read', {}, 'r1');
  const withResult = callsOf(log(call, user(resultPart('r1', true))));
  const withoutResult = callsOf(log(call));
  assert.deepEqual(pairs(withResult), pairs(withoutResult));
  assert.equal(withResult.length, 1);
});

test('D0049-AC-11: Agent を 25 回（max_agent_calls の既定 20 を超える）呼んだログは 25 回と数える（止められた呼び出しも、モデルが出した時点でログにある）', () => {
  const lines = Array.from({ length: 25 }, (_, i) => assistantTool('Agent', { subagent_type: 'a' }, `a${i}`));
  assert.equal(callsOf(log(...lines)).length, 25);
});

// ---- AC-14：TaskNotificationMessage は読まない ----

test('D0049-AC-14: TaskNotificationMessage（tool_use_id・usage.duration_ms）の行を足しても、calls は増えず、中身も変わらない', () => {
  const base = log(assistantTool('Agent', { subagent_type: 'a' }, 'a1'), assistantTool('Read', {}, 'r1'));
  const note = raw({ _type: 'TaskNotificationMessage', tool_use_id: 'a1', usage: { duration_ms: 5000 }, status: 'completed' });
  const withNote = log(assistantTool('Agent', { subagent_type: 'a' }, 'a1'), note, assistantTool('Read', {}, 'r1'));
  assert.deepEqual(callsOf(withNote), callsOf(base));
  assert.equal(callsOf(withNote).length, 2);
  assert.ok(!JSON.stringify(callsOf(withNote)).includes('5000'), '時間を calls に持ち出さない');
});

// ---- AC-42：壊れた部品・行でも例外を出さず、数えられるものだけ数える ----

const GOOD = { id: 'k1', name: 'Read', input: {} };
const AC42: { label: string; text: string; want: string[] }[] = [
  { label: 'content が文字の AssistantMessage は 0 個', text: log(raw({ _type: 'AssistantMessage', content: 'Read' })), want: [] },
  { label: 'content が null の AssistantMessage は 0 個', text: log(raw({ _type: 'AssistantMessage', content: null })), want: [] },
  { label: 'content がオブジェクトの AssistantMessage は 0 個（配列でない）', text: log(raw({ _type: 'AssistantMessage', content: GOOD })), want: [] },
  { label: 'content の無い AssistantMessage は 0 個', text: log(raw({ _type: 'AssistantMessage' })), want: [] },
  {
    label: '部品が null・数・文字・配列のときは飛ばし、ほかの部品は数える',
    text: log(assistantParts([null, 5, 'Read', ['name'], GOOD])),
    want: ['tool:Read'],
  },
  { label: 'name が配列の部品は数えない', text: log(assistantParts([{ id: 'a', name: ['Read'], input: {} }])), want: [] },
  { label: 'name が真偽値の部品は数えない', text: log(assistantParts([{ id: 'a', name: true, input: {} }])), want: [] },
  { label: 'input が数の部品は数えない', text: log(assistantParts([{ id: 'a', name: 'Read', input: 7 }])), want: [] },
  { label: 'id が無い部品は数える', text: log(assistantParts([{ name: 'Read', input: {} }])), want: ['tool:Read'] },
  { label: 'id が数の部品は数える', text: log(assistantParts([{ id: 5, name: 'Read', input: {} }])), want: ['tool:Read'] },
  { label: 'id が null の部品は数える', text: log(assistantParts([{ id: null, name: 'Read', input: {} }])), want: ['tool:Read'] },
  { label: 'parent_tool_use_id が数の発言の部品は数える', text: log(assistantParts([GOOD], 5)), want: ['tool:Read'] },
  { label: 'parent_tool_use_id が {} の発言の部品は数える', text: log(assistantParts([GOOD], {})), want: ['tool:Read'] },
  { label: '_type が AssistantMessage でない行（UserMessage）は、呼び出しの形の部品があっても 0 個', text: log(raw({ _type: 'UserMessage', content: [GOOD] })), want: [] },
  { label: '_type の無い行は 0 個', text: log(raw({ content: [GOOD] })), want: [] },
  { label: '壊れた行と途中までの行が間にあっても、その前後の呼び出しは数える', text: log(assistantParts([GOOD]), '{"_type":', assistantParts([toolPart('Grep', {}, 'g1')])), want: ['tool:Read', 'tool:Grep'] },
  { label: '空のログは 0 個', text: '', want: [] },
  { label: '改行だけのログは 0 個', text: '\n\n\n', want: [] },
  { label: '空白だけの行を含むログは 0 個', text: '   \n\t\n', want: [] },
  { label: '最後の行が途中で切れた（改行も無い）ログは、その前までの呼び出しを数える', text: `${log(assistantParts([GOOD]))}{"_type":"AssistantMessage","content":[{"id"`, want: ['tool:Read'] },
  { label: 'CRLF の改行のログも読める', text: `${promptLine('x')}\r\n${assistantParts([GOOD])}\r\n`, want: ['tool:Read'] },
];
for (const c of AC42) {
  test(`D0049-AC-42: ${c.label}（例外を出さない）`, () => {
    assert.deepEqual(tags(callsOf(c.text)), c.want);
  });
}
