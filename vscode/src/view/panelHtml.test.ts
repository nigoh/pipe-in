// パネルの HTML の検査。AC-42（外部の読み込みなし）・AC-43（色はテーマの変数だけ）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderPanelHtml } from './panelHtml.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import {
  assistantText,
  assistantTool,
  logText,
  promptLine,
  resultLine,
  snapshot,
  stageRunEntry,
  stateJson,
} from '../test/fixtures.ts';

// 図の状態に入れる文章・ツールの対象には `#` を含めない（設計書「リスクと注意点」：AC-43 のテストの前提）。
function viewWithRecords() {
  return buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [
          stageRunEntry({ stage: 'requirements', seq: 1, numTurns: 10, costUsd: 0.2, durationSec: 30 }),
          { stage: 'requirements', review: 'revise', feedback: '直して' },
          stageRunEntry({ stage: 'requirements', seq: 2, numTurns: 5, costUsd: 0.1, durationSec: 20 }),
          { stage: 'requirements', review: 'approved' },
          stageRunEntry({ stage: 'design', seq: 3, isError: true }),
        ],
        totalCostUsd: 0.3,
      }),
      stageLogs: [
        {
          fileName: '01_requirements.jsonl',
          text: logText([promptLine('requirements'), assistantText('要件を読みます'), resultLine()]),
        },
        {
          fileName: '04_red.jsonl',
          text: logText([
            promptLine('red'),
            assistantTool('Bash', { command: 'npm test' }),
            assistantText('<b>"テスト" & \'書く\'</b>'),
          ]),
        },
      ],
      artifacts: { '00_input.md': 'メモ', '01_requirements.md': '要件', '03_red_tests.md': '  ' },
    }),
  );
}

const views = [
  ['記録のある図の状態', () => viewWithRecords()],
  ['空の図の状態', () => buildPipelineView(snapshot())],
] as const;

for (const [name, make] of views) {
  test(`AC-42: ${name}の HTML に http:・https: で始まる読み込み先がない`, () => {
    const html = renderPanelHtml(make(), 'n');
    assert.ok(html.length > 0);
    assert.doesNotMatch(html, /(src|href)\s*=\s*["']?https?:/i);
    assert.doesNotMatch(html, /url\(\s*["']?https?:/i);
    assert.doesNotMatch(html, /@import/i);
  });

  test(`AC-43: ${name}の HTML に色の直書きがなく、色は var(--vscode- で指定されている`, () => {
    const html = renderPanelHtml(make(), 'n');
    assert.doesNotMatch(html, /#[0-9a-fA-F]{3,8}\b/);
    assert.doesNotMatch(html, /rgba?\(/);
    assert.doesNotMatch(html, /hsla?\(/);
    assert.match(html, /var\(--vscode-/);
  });
}
