// 実行の一覧の行（RunRow）の項目を増やさない（D0050-AC-40）：summarizeRun の戻りのキーの集合を、固定のキー一覧と突き合わせる。
// 表（エージェント・スキル・道具）は選んだ実行の描き直しだけで作り、一覧の行の組み立てには入れない。
// 今の作りのまま通る（守る）。実装で表を一覧の行に持ち込むと（RunRow に tools などを足すと）落ちる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { summarizeRun } from './runList.ts';
import type { SummarizeInput } from './runList.ts';
import { assistantTool, stageRunEntry, stateJson } from '../test/fixtures.ts';
import { clockAt } from '../test/liveFixtures.ts';
import { logOf, toolsSnapshot, uniqueCalls } from '../test/toolsFixtures.ts';

/** RunRow の項目（17 個）。増やすときは、人が決めた設計の変更として、ここも直す */
const ROW_KEYS = [
  'key',
  'session',
  'pipe',
  'branch',
  'other',
  'previous',
  'stage',
  'state',
  'result',
  'sessionId',
  'costText',
  'updatedText',
  'updatedDate',
  'updatedMs',
  'elapsed',
  'waitingSec',
  'quietSec',
].sort();

const CALLS = uniqueCalls([
  { name: 'Agent', input: { subagent_type: 'module-reader' } },
  { name: 'Skill', input: { skill: 'review' } },
  { name: 'Read', input: { file_path: 'a.py' }, count: 3 },
  { name: 'Read', input: {}, parent: 'toolu_nested', count: 2 },
]);

function input(over: Partial<SummarizeInput> & Pick<SummarizeInput, 'stateJson'>): SummarizeInput {
  return { key: 'here|', id: '', branch: null, other: false, memoHead: null, previous: false, stageLogs: [], ...over };
}

const base = toolsSnapshot({
  runs: [{ seq: 1, stage: 'requirements' }],
  logs: [{ seq: 1, stage: 'requirements', lines: CALLS }],
  running: { seq: 2, stage: 'design', lines: CALLS },
});

const STATES: [string, SummarizeInput][] = [
  ['動いている（段のログが動いている）', input({ stateJson: base.stateJson, stageLogs: base.stageLogs })],
  [
    '確認待ち',
    input({
      stateJson: stateJson({
        runs: [stageRunEntry({ stage: 'requirements', seq: 1 })],
        pendingReview: { stage: 'requirements', doc: 'docs/pipeline/01_requirements.md', session_id: 's', since: '2026-10-17T10:00:00+00:00' },
      }),
      stageLogs: [{ fileName: '01_requirements.jsonl', text: logOf('requirements', CALLS) }],
    }),
  ],
  [
    '待ち（段の合間）',
    input({ stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }), stageLogs: [{ fileName: '01_requirements.jsonl', text: logOf('requirements', CALLS) }] }),
  ],
  [
    '終わった（final あり）',
    input({
      stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })], final: 'PASSED', driver: 'pipe-dev' }),
      stageLogs: [{ fileName: '01_requirements.jsonl', text: logOf('requirements', CALLS) }],
    }),
  ],
  [
    'archive（前の実行）',
    input({
      key: 'here|archive/20261016-090000',
      id: 'archive/20261016-090000',
      previous: true,
      stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }),
      stageLogs: [{ fileName: '01_requirements.jsonl', text: logOf('requirements', CALLS) }],
    }),
  ],
  ['state.json が無い', input({ stateJson: null })],
  ['AssistantMessage だけの大きな呼び出し（Agent を 25 回）', input({ stateJson: base.stateJson, stageLogs: [{ fileName: '01_requirements.jsonl', text: logOf('requirements', Array.from({ length: 25 }, (_, i) => assistantTool('Agent', { subagent_type: 'a' }, `a${i}`)), { finished: false }) }] })],
];
for (const [label, given] of STATES) {
  test(`D0050-AC-40: summarizeRun の戻りのキーは固定の 17 個のまま（${label}。Agent・Skill・入れ子の呼び出しを含む記録でも。今のまま通る。守る）`, () => {
    const row = summarizeRun(given, clockAt(0));
    assert.deepEqual(Object.keys(row).sort(), ROW_KEYS);
  });
}

test('D0050-AC-40: 一覧の行に、表（tools）やその数え上げの項目が入っていない（今のまま通る。守る）', () => {
  const row = summarizeRun(STATES[0]![1], clockAt(0)) as unknown as Record<string, unknown>;
  for (const key of ['tools', 'toolsTable', 'calls', 'agents', 'skills', 'toolCount']) assert.equal(key in row, false, key);
  assert.ok(!JSON.stringify(row).includes('module-reader'), '呼び出しの名前が一覧の行に出ない');
});
