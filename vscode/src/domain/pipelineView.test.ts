// 図の状態の組み立て（buildPipelineView）。AC-15〜AC-33・AC-37〜AC-41。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPipelineView } from './pipelineView.ts';
import type { NodeId, PipelineView } from './pipelineView.ts';
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

function node(view: PipelineView, id: NodeId) {
  const found = view.nodes.find((n) => n.id === id);
  assert.ok(found, `節 ${id} があること`);
  return found;
}

const NODE_IDS: NodeId[] = [
  'input',
  'requirements',
  'review:requirements',
  'design',
  'review:design',
  'red',
  'review:red',
  'implement',
  'test',
  'verdict',
  'final',
];

test('AC-15: 記録が何もないとき、節は11個の順で、すべて「まだ」', () => {
  const view = buildPipelineView(snapshot());
  assert.deepEqual(
    view.nodes.map((n) => n.label),
    ['要件メモ', '要件定義', '確認', '設計', '確認', 'テスト先行', '確認', '実装', '検証', '判定', '完了'],
  );
  assert.deepEqual(
    view.nodes.map((n) => n.id),
    NODE_IDS,
  );
  for (const n of view.nodes) assert.equal(n.status, 'pending', `${n.id} が pending`);
});

test('AC-16: 00_input.md が中身ありで存在すれば、要件メモの節が「完了」', () => {
  const view = buildPipelineView(snapshot({ artifacts: { '00_input.md': '中身' } }));
  assert.equal(node(view, 'input').status, 'done');
});

test('AC-17: 要件定義の段の実行（seq 1、is_error false）があれば、要件定義の節が「完了」', () => {
  const view = buildPipelineView(
    snapshot({ stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1, isError: false })] }) }),
  );
  assert.equal(node(view, 'requirements').status, 'done');
});

test('AC-18: 設計の段の実行が is_error true なら、設計の節が「失敗」', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [stageRunEntry({ stage: 'requirements', seq: 1 }), stageRunEntry({ stage: 'design', seq: 2, isError: true })],
      }),
    }),
  );
  assert.equal(node(view, 'design').status, 'failed');
});

test('AC-19: 最大 seq 1 で、02_design.jsonl に ResultMessage がなければ、設計の節が「動いている」', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }),
      stageLogs: [{ fileName: '02_design.jsonl', text: logText([promptLine('design'), assistantText('設計します')]) }],
    }),
  );
  assert.equal(node(view, 'design').status, 'running');
  assert.equal(view.runningStage, 'design');
});

test('AC-20: 最大 seq 2 なら、02_design.jsonl に ResultMessage がなくても、どの節も「動いている」にならない', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [stageRunEntry({ stage: 'requirements', seq: 1 }), stageRunEntry({ stage: 'design', seq: 2 })],
      }),
      stageLogs: [{ fileName: '02_design.jsonl', text: logText([promptLine('design'), assistantText('設計します')]) }],
    }),
  );
  assert.equal(view.nodes.filter((n) => n.status === 'running').length, 0);
  assert.equal(view.runningStage, null);
});

test('AC-21: 要件定義の確認が approved なら、要件定義のあとの確認の節が「完了」', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [stageRunEntry({ stage: 'requirements', seq: 1 }), { stage: 'requirements', review: 'approved' }],
      }),
    }),
  );
  assert.equal(node(view, 'review:requirements').status, 'done');
});

test('AC-22: 設計の確認が quit なら、設計のあとの確認の節が「失敗」', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [stageRunEntry({ stage: 'design', seq: 2 }), { stage: 'design', review: 'quit' }],
        final: 'STOPPED_BY_HUMAN',
      }),
    }),
  );
  assert.equal(node(view, 'review:design').status, 'failed');
});

test('AC-23: 要件定義の revise が2件なら、要件定義のあとの確認の節の修正の依頼の回数が 2', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [
          stageRunEntry({ stage: 'requirements', seq: 1 }),
          { stage: 'requirements', review: 'revise', feedback: '直して1' },
          stageRunEntry({ stage: 'requirements', seq: 2 }),
          { stage: 'requirements', review: 'revise', feedback: '直して2' },
          stageRunEntry({ stage: 'requirements', seq: 3 }),
        ],
      }),
    }),
  );
  assert.equal(node(view, 'review:requirements').reviseCount, 2);
});

test('AC-24: 実装の段の実行が attempt 1・2・3 なら、実装の節の差し戻しの回数が 2', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [
          stageRunEntry({ stage: 'implement', seq: 4, attempt: 1 }),
          stageRunEntry({ stage: 'implement', seq: 6, attempt: 2 }),
          stageRunEntry({ stage: 'implement', seq: 8, attempt: 3 }),
        ],
      }),
    }),
  );
  assert.equal(node(view, 'implement').sendBackCount, 2);
});

test('AC-25: 判定が fail → pass の順なら、判定の節が「完了」', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [
          { stage: 'test', attempt: 1, verdict: { status: 'fail', summary: '落ちた', failures: [], commands: [] } },
          { stage: 'test', attempt: 2, verdict: { status: 'pass', summary: '通った', failures: [], commands: [] } },
        ],
      }),
    }),
  );
  assert.equal(node(view, 'verdict').status, 'done');
});

test('AC-26: 最後の判定が blocked なら、判定の節が「失敗」', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [
          { stage: 'test', attempt: 1, verdict: { status: 'pass', summary: '通った', failures: [], commands: [] } },
          { stage: 'test', attempt: 2, verdict: { status: 'blocked', summary: '動かない', failures: [], commands: [] } },
        ],
      }),
    }),
  );
  assert.equal(node(view, 'verdict').status, 'failed');
});

test('AC-27: final が PASSED なら、完了の節が「完了」', () => {
  const view = buildPipelineView(snapshot({ stateJson: stateJson({ final: 'PASSED' }) }));
  assert.equal(node(view, 'final').status, 'done');
});

test('AC-28: final が TEST_FAILED なら、完了の節が「失敗」', () => {
  const view = buildPipelineView(snapshot({ stateJson: stateJson({ final: 'TEST_FAILED' }) }));
  assert.equal(node(view, 'final').status, 'failed');
});

test('AC-29: 動いている段が設計なら、ターミナル風の出力は設計のログの項目だけ', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }),
      stageLogs: [
        {
          fileName: '01_requirements.jsonl',
          text: logText([promptLine('requirements'), assistantText('要件の文章'), resultLine()]),
        },
        {
          fileName: '02_design.jsonl',
          text: logText([promptLine('design'), assistantTool('Read', { file_path: '01_requirements.md' }), assistantText('設計の文章')]),
        },
      ],
    }),
  );
  assert.equal(view.terminal.source?.stage, 'design');
  assert.deepEqual(view.terminal.items, [
    { kind: 'tool', tool: 'Read', target: '01_requirements.md' },
    { kind: 'text', text: '設計の文章' },
  ]);
});

test('AC-30: 動いている段がなければ、通し番号が最大の 02_design.jsonl の項目を出す', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [stageRunEntry({ stage: 'requirements', seq: 1 }), stageRunEntry({ stage: 'design', seq: 2 })],
      }),
      stageLogs: [
        // 順は問わない（写しの並びに左右されないこと）
        { fileName: '02_design.jsonl', text: logText([promptLine('design'), assistantText('設計の文章'), resultLine()]) },
        {
          fileName: '01_requirements.jsonl',
          text: logText([promptLine('requirements'), assistantText('要件の文章'), resultLine()]),
        },
      ],
    }),
  );
  assert.equal(view.runningStage, null);
  assert.equal(view.terminal.source?.seq, 2);
  assert.deepEqual(view.terminal.items, [{ kind: 'text', text: '設計の文章' }]);
});

test('AC-31: 動いている段のログに文章Cの行を足して組み立て直すと、出力は3件で最後が文章C', () => {
  const state = stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] });
  const before = logText([promptLine('design'), assistantText('文章A'), assistantText('文章B')]);
  const first = buildPipelineView(snapshot({ stateJson: state, stageLogs: [{ fileName: '02_design.jsonl', text: before }] }));
  assert.equal(first.terminal.items.length, 2);

  const after = before + logText([assistantText('文章C')]);
  const second = buildPipelineView(snapshot({ stateJson: state, stageLogs: [{ fileName: '02_design.jsonl', text: after }] }));
  assert.equal(second.terminal.items.length, 3);
  assert.deepEqual(second.terminal.items.at(-1), { kind: 'text', text: '文章C' });
});

test('AC-32: 実装の段の実行2件の合計 → ターン 15、費用 0.3、時間 50', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [
          stageRunEntry({ stage: 'implement', seq: 4, attempt: 1, numTurns: 10, costUsd: 0.2, durationSec: 30 }),
          stageRunEntry({ stage: 'implement', seq: 6, attempt: 2, numTurns: 5, costUsd: 0.1, durationSec: 20 }),
        ],
      }),
    }),
  );
  assert.deepEqual(node(view, 'implement').metrics, { numTurns: 15, costUsd: 0.3, durationSec: 50 });
});

test('AC-33: total_cost_usd 1.25 → 合計の費用 1.25', () => {
  const view = buildPipelineView(
    snapshot({ stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })], totalCostUsd: 1.25 }) }),
  );
  assert.equal(view.totalCostUsd, 1.25);
});

test('AC-37: 途中の記録 X で組み立ててから Y で組み立てた結果と、Y だけで組み立てた結果が等しい', () => {
  const x = snapshot({
    stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1, numTurns: 3, costUsd: 0.05 })], totalCostUsd: 0.05 }),
    stageLogs: [
      {
        fileName: '01_requirements.jsonl',
        text: logText([promptLine('requirements'), assistantText('要件の文章'), resultLine()]),
      },
      { fileName: '02_design.jsonl', text: logText([promptLine('design'), assistantText('設計の文章1')]) },
    ],
    artifacts: { '00_input.md': 'メモ', '01_requirements.md': '要件' },
  });
  const y = snapshot({
    stateJson: stateJson({
      runs: [
        stageRunEntry({ stage: 'requirements', seq: 1, numTurns: 3, costUsd: 0.05 }),
        { stage: 'requirements', review: 'approved' },
        stageRunEntry({ stage: 'design', seq: 2, numTurns: 4, costUsd: 0.07 }),
      ],
      totalCostUsd: 0.12,
    }),
    stageLogs: [
      {
        fileName: '01_requirements.jsonl',
        text: logText([promptLine('requirements'), assistantText('要件の文章'), resultLine()]),
      },
      {
        fileName: '02_design.jsonl',
        text: logText([promptLine('design'), assistantText('設計の文章1'), assistantText('設計の文章2'), resultLine()]),
      },
    ],
    artifacts: { '00_input.md': 'メモ', '01_requirements.md': '要件', '02_design.md': '設計' },
  });

  buildPipelineView(x);
  const afterX = buildPipelineView(y);
  const onlyY = buildPipelineView(y);
  assert.deepStrictEqual(afterX, onlyY);
});

test('AC-38: final null・動いている段なし・段の実行1件 → 待ちの表示が有効', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }),
      stageLogs: [
        {
          fileName: '01_requirements.jsonl',
          text: logText([promptLine('requirements'), assistantText('要件の文章'), resultLine()]),
        },
      ],
    }),
  );
  assert.equal(view.runningStage, null);
  assert.equal(view.waiting, true);
});

test('AC-39: final null・動いている段あり → 待ちの表示が無効', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }),
      stageLogs: [{ fileName: '02_design.jsonl', text: logText([promptLine('design'), assistantText('設計します')]) }],
    }),
  );
  assert.equal(view.runningStage, 'design');
  assert.equal(view.waiting, false);
});

test('AC-40: final PASSED・動いている段なし → 待ちの表示が無効', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({ runs: [stageRunEntry({ stage: 'test', seq: 5, attempt: 1 })], final: 'PASSED' }),
    }),
  );
  assert.equal(view.runningStage, null);
  assert.equal(view.waiting, false);
});

test('AC-41: state.json・段のログ・00_input.md がないとき、「記録がありません」と work_dir のパスを出す', () => {
  const view = buildPipelineView(snapshot({ workDir: '/w/docs-internal/pipeline' }));
  assert.ok(view.noRecords, '記録なしの表示が有効であること');
  assert.equal(view.noRecords.message, '記録がありません');
  assert.equal(view.noRecords.workDir, '/w/docs-internal/pipeline');
});

test('確認の省略：確認の記録がないまま先の段が動いたら、その確認は「省略」（--yes など）', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [
          stageRunEntry({ stage: 'requirements', seq: 1 }),
          { stage: 'requirements', review: 'approved' },
          stageRunEntry({ stage: 'design', seq: 2 }),
          stageRunEntry({ stage: 'red', seq: 3 }),
        ],
      }),
    }),
  );
  assert.equal(node(view, 'review:requirements').status, 'done');
  assert.equal(node(view, 'review:design').status, 'skipped');
  // テスト先行のあとの段はまだ動いていないので、確認は省略ではなく「まだ」
  assert.equal(node(view, 'review:red').status, 'pending');
});

test('判定のやり直し：差し戻して実装をもう一度動かしたら、前回の不合格は消して判定を「まだ」に戻す', () => {
  const runs = [
    stageRunEntry({ stage: 'implement', seq: 1, attempt: 1 }),
    stageRunEntry({ stage: 'test', seq: 2, attempt: 1 }),
    { stage: 'test', attempt: 1, verdict: { status: 'fail', summary: 'x', failures: [], commands: [] } },
  ];
  const failed = buildPipelineView(snapshot({ stateJson: stateJson({ runs }) }));
  assert.equal(node(failed, 'verdict').status, 'failed');

  const retrying = buildPipelineView(
    snapshot({ stateJson: stateJson({ runs: [...runs, stageRunEntry({ stage: 'implement', seq: 3, attempt: 2 })] }) }),
  );
  assert.equal(node(retrying, 'verdict').status, 'pending');
});

test('判定のやり直し：検証の段が動いている間も、判定は「まだ」', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [
          stageRunEntry({ stage: 'test', seq: 1, attempt: 1 }),
          { stage: 'test', attempt: 1, verdict: { status: 'fail', summary: 'x', failures: [], commands: [] } },
        ],
      }),
      stageLogs: [{ fileName: '02_test_2.jsonl', text: logText([promptLine('test')]) }],
    }),
  );
  assert.equal(node(view, 'verdict').status, 'pending');
});
