// 使用量（devpipe 0.2 の state.json の usage_summary と、段の実行ごとの metrics）の読み取りと図の状態。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseRunRecord } from './runRecord.ts';
import { buildPipelineView } from './pipelineView.ts';
import { snapshot, stageMetricsDict, stageRunEntry, stateJson, tokensDict, usageSummaryDict } from '../test/fixtures.ts';

test('使用量：usage_summary から合計のトークン・キャッシュ再利用率・API 待ち時間を読む', () => {
  const usage = parseRunRecord(stateJson({ usageSummary: usageSummaryDict() })).usage;
  assert.ok(usage);
  assert.deepEqual(usage.tokens, { input: 122, cacheWrite: 550460, cacheRead: 5224407, output: 126952, thinking: 23628 });
  assert.equal(usage.cacheReuseRate, 0.9047); // 5224407 / (122 + 550460 + 5224407)
  assert.equal(usage.durationApiMs, 1133000);
  assert.deepEqual(usage.models, ['claude-opus-5-5']);
});

test('使用量：モデル別は費用の高い順に並べる', () => {
  const usage = parseRunRecord(stateJson({ usageSummary: usageSummaryDict() })).usage;
  assert.deepEqual(
    usage?.byModel.map((m) => [m.model, m.costUsd, m.tokens.output]),
    [
      ['claude-opus-5-5', 7.988, 126952],
      ['claude-haiku-5-5', 0.001, 1206],
    ],
  );
});

test('使用量：利用枠は 5時間枠・7日枠の順に、言葉の名前と、途中で枠が戻ったかを持つ', () => {
  const usage = parseRunRecord(stateJson({ usageSummary: usageSummaryDict() })).usage;
  assert.deepEqual(
    usage?.rateLimits.map((w) => [w.label, w.first, w.last, w.peak, w.resetSeen]),
    [
      ['5時間枠', 0.12, 0.02, 0.13, true],
      ['7日枠', 0.14, 0.15, 0.15, false],
    ],
  );
  assert.equal(usage?.rateLimits[0].resetsAt, 1792170000);
});

test('使用量：知らない枠の名前は、そのまま名前にして後ろに置く', () => {
  const summary = { ...(usageSummaryDict() as Record<string, unknown>), rate_limits: { opus_week: { first: 0.5, last: 0.6 }, five_hour: { first: 0.1, last: 0.2 } } };
  const usage = parseRunRecord(stateJson({ usageSummary: summary })).usage;
  assert.deepEqual(usage?.rateLimits.map((w) => w.label), ['5時間枠', 'opus_week']);
});

test('使用量：usage_summary のない古い記録では null', () => {
  assert.equal(parseRunRecord(stateJson({})).usage, null);
  assert.equal(parseRunRecord(null).usage, null);
});

test('使用量：形の違う usage_summary でも例外を出さず、読めない値は 0・空にする', () => {
  assert.equal(parseRunRecord(stateJson({ usageSummary: 'x' })).usage, null);
  const usage = parseRunRecord(
    stateJson({ usageSummary: { tokens: { input: '1', output: 5 }, by_model: [], rate_limits: { five_hour: 'x' }, models: [3] } }),
  ).usage;
  assert.ok(usage);
  assert.deepEqual(usage.tokens, { input: 0, cacheWrite: 0, cacheRead: 0, output: 5, thinking: 0 });
  assert.deepEqual(usage.byModel, []);
  assert.deepEqual(usage.rateLimits, []);
  assert.deepEqual(usage.models, []);
});

test('使用量：段の実行ごとのトークンを metrics から読む。古い記録の段の実行では null', () => {
  const record = parseRunRecord(
    stateJson({
      runs: [
        stageRunEntry({ stage: 'requirements', seq: 1 }),
        stageRunEntry({ stage: 'design', seq: 2, metrics: stageMetricsDict({ tokens: tokensDict({ input: 10, cacheWrite: 100, cacheRead: 900, output: 50, thinking: 5 }) }) }),
      ],
    }),
  );
  assert.equal(record.stageRuns[0].tokens, null);
  assert.deepEqual(record.stageRuns[1].tokens, { input: 10, cacheWrite: 100, cacheRead: 900, output: 50, thinking: 5 });
  assert.equal(record.stageRuns[1].cacheReuseRate, 0.8911);
});

test('図の状態：使用量があれば、段の実行ごとの行と合計を持つ', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        usageSummary: usageSummaryDict(),
        runs: [
          stageRunEntry({ stage: 'implement', seq: 4, attempt: 1, metrics: stageMetricsDict({ tokens: tokensDict({ output: 7 }) }) }),
          stageRunEntry({ stage: 'test', seq: 5, attempt: 1 }),
        ],
      }),
    }),
  );
  assert.ok(view.usage);
  assert.equal(view.usage.summary.tokens.output, 126952);
  assert.deepEqual(
    view.usage.rows.map((r) => [r.seq, r.stage, r.attempt, r.tokens?.output ?? null]),
    [
      [4, 'implement', 1, 7],
      [5, 'test', 1, null],
    ],
  );
});

test('図の状態：使用量のない記録では usage は null', () => {
  assert.equal(buildPipelineView(snapshot()).usage, null);
  assert.equal(buildPipelineView(snapshot({ stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }) })).usage, null);
});
