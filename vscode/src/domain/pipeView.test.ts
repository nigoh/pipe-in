// パイプ（kind = "linear"）の記録から図の状態を作る。AC-03〜AC-08。
// 開発フローの図（11節）は pipelineView.test.ts が確かめる。ここでは段の並びを記録から取る場合を見る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import * as artifacts from './artifacts.ts';
import { buildPipelineView } from './pipelineView.ts';
import type { PipelineView } from './pipelineView.ts';
import { parseRunRecord } from './runRecord.ts';
import type { RunRecord } from './runRecord.ts';
import { parseStageLogName } from './stageLog.ts';
import {
  DEV_STAGES,
  DIAGRAMS_STAGES,
  assistantText,
  logText,
  promptLine,
  snapshot,
  stageRunEntry,
  stateJson,
} from '../test/fixtures.ts';

// 新しく足す関数（今はない）。呼んで、何で落ちたかが見えるように名前空間から引く。
const artifactNamesFor = (record: RunRecord): string[] =>
  (artifacts as unknown as { artifactNamesFor: (r: RunRecord) => string[] }).artifactNamesFor(record);
const resolveArtifactPath = artifacts.resolveArtifactPath as (w: string, name: string, allowed?: readonly string[]) => string | null;

// 拡張して足す図の状態の項目
type PipeView = PipelineView & {
  pendingReview?: { stage: string; label: string; doc: string } | null;
  warnings?: string[];
};

function diagramsState(p: Parameters<typeof stateJson>[0] = {}): string {
  return stateJson({ pipe: 'diagrams', stages: DIAGRAMS_STAGES, ...p });
}

function node(view: PipelineView, id: string) {
  const n = view.nodes.find((x) => x.id === id);
  assert.ok(n, `節 ${id} がない`);
  return n;
}

test('AC-03: stages の並びで節を作る（依頼メモ → 段 →（確認）→ … → 完了。判定はない）', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: diagramsState({
        runs: [
          stageRunEntry({ stage: 'survey', seq: 1, numTurns: 4, costUsd: 0.12, durationSec: 30 }),
          { stage: 'survey', review: 'approved' },
          stageRunEntry({ stage: 'draw', seq: 2 }),
        ],
      }),
      artifacts: { '00_input.md': '注文の流れを中心に' },
    }),
  );
  assert.deepEqual(
    view.nodes.map((n) => n.id),
    ['input', 'survey', 'review:survey', 'draw', 'review:draw', 'verify', 'final'],
  );
  assert.deepEqual(
    view.nodes.map((n) => n.label),
    ['依頼メモ', 'ソースの調査', '確認', '図を描く', '確認', '図とソースの突き合わせ', '完了'],
  );
  assert.deepEqual(
    view.nodes.map((n) => n.status),
    ['done', 'done', 'done', 'done', 'pending', 'pending', 'pending'],
  );
  assert.deepEqual(node(view, 'survey').metrics, { numTurns: 4, costUsd: 0.12, durationSec: 30 });
  assert.equal(node(view, 'draw').sendBackCount, null);
  assert.equal(node(view, 'review:survey').reviseCount, 0);
});

test('AC-03: 段の失敗・確認の修正と中止・省いた確認・最後の結果を節に出す', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: diagramsState({
        final: 'STOPPED_BY_HUMAN',
        runs: [
          stageRunEntry({ stage: 'survey', seq: 1 }),
          stageRunEntry({ stage: 'draw', seq: 2 }),
          { stage: 'draw', review: 'revise', feedback: '状態遷移図も' },
          stageRunEntry({ stage: 'draw', seq: 3, isError: true }),
          { stage: 'draw', review: 'quit' },
        ],
      }),
    }),
  );
  assert.equal(node(view, 'review:survey').status, 'skipped'); // 確認の記録がないまま先の段が動いた（--yes など）
  assert.equal(node(view, 'draw').status, 'failed');
  assert.equal(node(view, 'review:draw').status, 'failed');
  assert.equal(node(view, 'review:draw').reviseCount, 1);
  assert.equal(node(view, 'final').status, 'failed');

  const passed = buildPipelineView(snapshot({ stateJson: diagramsState({ final: 'PASSED' }) }));
  assert.equal(node(passed, 'final').status, 'done');
});

test('AC-03: output・review のない記録では、確認の記録がある段のあとにだけ確認の節を置き、成果物は依頼メモとまとめだけ', () => {
  const stages = DIAGRAMS_STAGES.map(({ name, label }) => ({ name, label }));
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        pipe: 'diagrams',
        stages,
        runs: [stageRunEntry({ stage: 'survey', seq: 1 }), stageRunEntry({ stage: 'draw', seq: 2 }), { stage: 'draw', review: 'approved' }],
      }),
    }),
  );
  assert.deepEqual(
    view.nodes.map((n) => n.id),
    ['input', 'survey', 'draw', 'review:draw', 'verify', 'final'],
  );
  assert.deepEqual(
    view.artifacts.map((a) => a.name),
    ['00_input.md', '99_summary.md'],
  );
});

test('AC-03: 使用量の表の行にも段の label を持たせる', () => {
  const view = buildPipelineView(
    snapshot({ stateJson: diagramsState({ usageSummary: {}, runs: [stageRunEntry({ stage: 'survey', seq: 1 })] }) }),
  );
  const rows = view.usage?.rows as unknown as { stage: string; label?: string }[];
  assert.equal(rows.length, 1);
  assert.equal(rows[0].label, 'ソースの調査');
});

test('AC-04: 開発フローの stages があってもなくても11節は同じ', () => {
  const runs = [
    stageRunEntry({ stage: 'requirements', seq: 1 }),
    { stage: 'requirements', review: 'approved' },
    stageRunEntry({ stage: 'design', seq: 2 }),
    { stage: 'design', review: 'revise', feedback: 'x' },
    stageRunEntry({ stage: 'implement', seq: 3, attempt: 1 }),
    stageRunEntry({ stage: 'test', seq: 4, attempt: 1 }),
    { stage: 'test', attempt: 1, verdict: { status: 'fail', summary: 'x' } },
  ];
  const before = buildPipelineView(snapshot({ stateJson: stateJson({ runs }), artifacts: { '00_input.md': 'メモ' } }));
  const now = buildPipelineView(
    snapshot({ stateJson: stateJson({ pipe: 'dev', stages: DEV_STAGES, runs }), artifacts: { '00_input.md': 'メモ' } }),
  );
  assert.equal(now.nodes.length, 11);
  assert.deepEqual(now.nodes, before.nodes);
  assert.deepEqual(
    now.artifacts.map((a) => a.name),
    before.artifacts.map((a) => a.name),
  );
  // kind = "dev" のパイプ（名前が dev 以外）でも、段が開発の5段なら同じ図
  const named = buildPipelineView(
    snapshot({ stateJson: stateJson({ pipe: 'mydev', stages: DEV_STAGES, runs }), artifacts: { '00_input.md': 'メモ' } }),
  );
  assert.deepEqual(named.nodes, before.nodes);
});

test('AC-05: 任意の段の名前のログを読み、動いている段にする', () => {
  assert.deepEqual(parseStageLogName('03_verify.jsonl'), { seq: 3, stage: 'verify', attempt: null });
  assert.deepEqual(parseStageLogName('12_spec-map_2.jsonl'), { seq: 12, stage: 'spec-map', attempt: 2 });
  for (const bad of ['03_Verify.jsonl', '03_a_b.jsonl', '03_-x.jsonl', 'x_verify.jsonl', '03_verify.json']) {
    assert.equal(parseStageLogName(bad), null, bad);
  }

  const view = buildPipelineView(
    snapshot({
      stateJson: diagramsState({ runs: [stageRunEntry({ stage: 'survey', seq: 1 }), stageRunEntry({ stage: 'draw', seq: 2 })] }),
      stageLogs: [{ fileName: '03_verify.jsonl', text: logText([promptLine('verify'), assistantText('突き合わせ中')]) }],
    }),
  );
  assert.equal(view.runningStage, 'verify');
  assert.equal(node(view, 'verify').status, 'running');
  assert.deepEqual(view.terminal.source, { seq: 3, stage: 'verify', attempt: null });
  assert.deepEqual(view.terminal.items, [{ kind: 'text', text: '突き合わせ中' }]);
  assert.equal(view.waiting, false);
});

test('AC-06: linear の成果物の一覧（依頼メモ・各段の output・まとめ）', () => {
  const view = buildPipelineView(
    snapshot({ stateJson: diagramsState(), artifacts: { '00_input.md': 'メモ', '01_survey.md': '調査', '02_diagrams.md': '  ' } }),
  );
  assert.deepEqual(
    view.artifacts.map((a) => [a.name, a.label, a.ready]),
    [
      ['00_input.md', '依頼メモ', true],
      ['01_survey.md', 'ソースの調査', true],
      ['02_diagrams.md', '図を描く', false],
      ['03_verify.md', '図とソースの突き合わせ', false],
      ['99_summary.md', 'まとめ', false],
    ],
  );
  assert.deepEqual(artifactNamesFor(parseRunRecord(diagramsState())), [
    '00_input.md',
    '01_survey.md',
    '02_diagrams.md',
    '03_verify.md',
    '99_summary.md',
  ]);
  assert.deepEqual(artifactNamesFor(parseRunRecord(null)), [
    '00_input.md',
    '01_requirements.md',
    '02_design.md',
    '03_red_tests.md',
    '04_implementation.md',
    '05_test_report.md',
    '99_summary.md',
  ]);
});

test('AC-06: 段の output がファイル名でなければ一覧に入れず、一覧の外の名前は開くパスを返さない', () => {
  const stages = [
    ...DIAGRAMS_STAGES,
    { name: 'a', label: 'A', output: '../evil.md', review: false },
    { name: 'b', label: 'B', output: 'sub/x.md', review: false },
    { name: 'c', label: 'C', output: '.hidden.md', review: false },
    { name: 'd', label: 'D', output: 'C:\\x.md', review: false },
  ];
  const names = artifactNamesFor(parseRunRecord(stateJson({ pipe: 'diagrams', stages })));
  assert.deepEqual(names, ['00_input.md', '01_survey.md', '02_diagrams.md', '03_verify.md', '99_summary.md']);

  const w = path.resolve('/ws/docs/pipeline/diagrams');
  assert.equal(resolveArtifactPath(w, '01_survey.md', names), path.join(w, '01_survey.md'));
  for (const name of ['../evil.md', '01_requirements.md', 'state.json', '']) {
    assert.equal(resolveArtifactPath(w, name, names), null, name);
  }
});

test('AC-07: 確認待ちの段と文書を図の状態に入れる', () => {
  const pending = { stage: 'draw', doc: 'docs/pipeline/diagrams/02_diagrams.md', session_id: 's-2' };
  const view = buildPipelineView(
    snapshot({
      stateJson: diagramsState({
        pendingReview: pending,
        runs: [stageRunEntry({ stage: 'survey', seq: 1 }), { stage: 'survey', review: 'approved' }, stageRunEntry({ stage: 'draw', seq: 2 })],
      }),
    }),
  ) as PipeView;
  assert.deepEqual(view.pendingReview, { stage: 'draw', label: '図を描く', doc: 'docs/pipeline/diagrams/02_diagrams.md' });

  const dev = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        pendingReview: { stage: 'requirements', doc: 'docs/pipeline/01_requirements.md', session_id: 's' },
        runs: [stageRunEntry({ stage: 'requirements', seq: 1 })],
      }),
    }),
  ) as PipeView;
  assert.deepEqual(dev.pendingReview, { stage: 'requirements', label: '要件定義', doc: 'docs/pipeline/01_requirements.md' });

  const none = buildPipelineView(snapshot({ stateJson: diagramsState() })) as PipeView;
  assert.equal(none.pendingReview, null);
  const broken = buildPipelineView(snapshot({ stateJson: diagramsState({ pendingReview: { stage: 3 } }) })) as PipeView;
  assert.equal(broken.pendingReview, null);
});

test('AC-08: warnings を図の状態に入れる（文字列でないものは捨てる）', () => {
  const view = buildPipelineView(
    snapshot({ stateJson: diagramsState({ warnings: ['赤になっていません', 3, null] }) }),
  ) as PipeView;
  assert.deepEqual(view.warnings, ['赤になっていません']);
  const none = buildPipelineView(snapshot({ stateJson: diagramsState() })) as PipeView;
  assert.deepEqual(none.warnings, []);
});
