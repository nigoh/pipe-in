// 段のログ（logs/NN_<段>[_回].jsonl）の名前と中身の読み取り。AC-06〜AC-14。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseStageLog, parseStageLogName } from './stageLog.ts';
import { assistantText, assistantTool, logText, promptLine, resultLine } from '../test/fixtures.ts';

test('AC-06: 03_red.jsonl → 通し番号 3、段 red、回なし', () => {
  assert.deepEqual(parseStageLogName('03_red.jsonl'), { seq: 3, stage: 'red', attempt: null });
});

test('AC-07: 07_implement_2.jsonl → 通し番号 7、段 implement、回 2', () => {
  assert.deepEqual(parseStageLogName('07_implement_2.jsonl'), { seq: 7, stage: 'implement', attempt: 2 });
});

test('AC-08: ツールの呼び出しの部品 → 種類はツールの呼び出し、ツール名 Read、対象 a.md', () => {
  const log = parseStageLog(logText([promptLine('requirements'), assistantTool('Read', { file_path: 'a.md' })]));
  assert.deepEqual(log.items, [{ kind: 'tool', tool: 'Read', target: 'a.md' }]);
});

test('AC-09: 文章の部品 → 種類は文章、中身「要件を読みます」', () => {
  const log = parseStageLog(logText([promptLine('requirements'), assistantText('要件を読みます')]));
  assert.deepEqual(log.items, [{ kind: 'text', text: '要件を読みます' }]);
});

test('AC-10: ツールの結果と考え中だけのログ → 例外が出ず、出力の項目は0件', () => {
  const toolResult = JSON.stringify({ _type: 'UserMessage', content: [{ tool_use_id: 'x', content: 'ok' }] });
  const thinking = JSON.stringify({ _type: 'AssistantMessage', content: [{ thinking: '…', signature: 's' }], model: 'x' });
  const log = parseStageLog(logText([promptLine('design'), toolResult, thinking]));
  assert.deepEqual(log.items, []);
});

test('AC-11: 壊れた行を飛ばし、文章A・文章B をこの順に出す', () => {
  const log = parseStageLog(logText([promptLine('design'), assistantText('文章A'), '{"_type":', assistantText('文章B')]));
  assert.deepEqual(log.items, [
    { kind: 'text', text: '文章A' },
    { kind: 'text', text: '文章B' },
  ]);
});

test('AC-12: 最後の行が改行のない途中までの JSON → 例外が出ず、その行は項目にならない', () => {
  const full = assistantText('文章A');
  const partial = assistantText('途中の文章').slice(0, 30);
  const text = `${promptLine('design')}\n${full}\n${partial}`;
  const log = parseStageLog(text);
  assert.deepEqual(log.items, [{ kind: 'text', text: '文章A' }]);
});

test('AC-13: 知らない形の発言（repr の形）は飛ばし、文章A だけを出す', () => {
  const unknown = JSON.stringify({ _type: 'Foo', repr: 'Foo(…)' });
  const log = parseStageLog(logText([promptLine('design'), unknown, assistantText('文章A')]));
  assert.deepEqual(log.items, [{ kind: 'text', text: '文章A' }]);
});

test('AC-14: 最後の Prompt 行より後ろの発言だけを出す', () => {
  const log = parseStageLog(
    logText([promptLine('design'), assistantText('文章A'), resultLine(), promptLine('design'), assistantText('文章B')]),
  );
  assert.deepEqual(log.items, [{ kind: 'text', text: '文章B' }]);
});
