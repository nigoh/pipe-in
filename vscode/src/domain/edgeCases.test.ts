// 検証の段で足した境界値・異常系のテスト（ドメイン）。各テスト名に対応する AC / FR を入れる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { parseRunRecord } from './runRecord.ts';
import { parseStageLog, parseStageLogName, summarizeToolTarget } from './stageLog.ts';
import { buildArtifactList, resolveArtifactPath } from './artifacts.ts';
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
  const n = view.nodes.find((x) => x.id === id);
  assert.ok(n, `節 ${id} があること`);
  return n;
}

// ---- 実行の記録（FR-02・FR-05） ----

test('AC-04 追加: JSON だがオブジェクトでない（配列・数値・null・空文字）でも例外なく空の記録', () => {
  for (const text of ['[]', '42', 'null', '', '"x"']) {
    const r = parseRunRecord(text);
    assert.deepEqual(r.stageRuns, [], text);
    assert.equal(r.final, null, text);
    assert.equal(r.totalCostUsd, 0, text);
  }
});

test('AC-05 追加: runs が配列でなくても final・total_cost_usd は読める', () => {
  const r = parseRunRecord(JSON.stringify({ final: 'PASSED', total_cost_usd: 2.5, runs: 'broken' }));
  assert.equal(r.final, 'PASSED');
  assert.equal(r.totalCostUsd, 2.5);
  assert.deepEqual(r.stageRuns, []);
});

test('AC-05 追加: 知らない形の要素・command_check・知らない段・知らない review は捨て、残りは読む', () => {
  const r = parseRunRecord(
    stateJson({
      runs: [
        null as unknown as object,
        'x' as unknown as object,
        { stage: 'red', command_check: { command: 'npm test', returncode: 1 } },
        { stage: 'unknown', seq: 1 },
        { stage: 'design', review: 'maybe' },
        { stage: 'test', attempt: 1, verdict: { status: 'weird' } },
        { stage: 'red', result: { status: 'green' } },
        stageRunEntry({ stage: 'design', seq: 2 }),
      ],
    }),
  );
  assert.equal(r.stageRuns.length, 1);
  assert.equal(r.reviews.length, 0);
  assert.equal(r.verdicts.length, 0);
  assert.equal(r.redResults.length, 0);
});

test('AC-05 追加: 段の実行の数値が数値でなければ 0、is_error は true のときだけ真', () => {
  const r = parseRunRecord(
    stateJson({ runs: [{ stage: 'implement', seq: 1, num_turns: '3', cost_usd: null, is_error: 'true' }] }),
  );
  assert.equal(r.stageRuns[0].numTurns, 0);
  assert.equal(r.stageRuns[0].costUsd, 0);
  assert.equal(r.stageRuns[0].durationSec, 0);
  assert.equal(r.stageRuns[0].isError, false);
  assert.equal(r.stageRuns[0].attempt, null);
});

test('AC-03 追加: total_cost_usd が数値でなければ 0、final が文字列でなければ null', () => {
  const r = parseRunRecord(JSON.stringify({ final: 1, total_cost_usd: '1.25', runs: [] }));
  assert.equal(r.final, null);
  assert.equal(r.totalCostUsd, 0);
});

// ---- 段のログのファイル名（FR-03） ----

test('AC-06/07 追加: 名前の形に合わないものは null', () => {
  for (const name of [
    'foo.jsonl',
    '03_red.json',
    'logs/03_red.jsonl',
    '03_red_.jsonl',
    'red.jsonl',
    '03_red_2.jsonl.bak',
  ]) {
    assert.equal(parseStageLogName(name), null, name);
  }
});

test('AC-07 追加: 2桁を超える通し番号・検証の回も読める', () => {
  assert.deepEqual(parseStageLogName('12_test_3.jsonl'), { seq: 12, stage: 'test', attempt: 3 });
  assert.deepEqual(parseStageLogName('01_requirements.jsonl'), { seq: 1, stage: 'requirements', attempt: null });
});

// ---- 段のログの中身（FR-04・FR-05・FR-09） ----

test('FR-09 追加: 対象は file_path・notebook_path・command・pattern・path の順で最初にあるもの', () => {
  assert.equal(summarizeToolTarget({ path: 'p', command: 'c' }), 'c');
  assert.equal(summarizeToolTarget({ pattern: 'x', path: 'p' }), 'x');
  assert.equal(summarizeToolTarget({ notebook_path: 'n.ipynb', command: 'c' }), 'n.ipynb');
  assert.equal(summarizeToolTarget({ file_path: 'f', notebook_path: 'n' }), 'f');
  assert.equal(summarizeToolTarget({ url: 'u' }), null);
});

test('FR-09 追加: 空白をまとめ、90 文字を超えたら先頭 89 文字＋…', () => {
  assert.equal(summarizeToolTarget({ command: '  npm \n  test  ' }), 'npm test');
  const ninety = 'a'.repeat(90);
  assert.equal(summarizeToolTarget({ command: ninety }), ninety);
  const long = 'b'.repeat(91);
  const got = summarizeToolTarget({ command: long });
  assert.equal(got, `${'b'.repeat(89)}…`);
  assert.equal(got?.length, 90);
});

test('FR-09 追加: 対象が文字列でなければ JSON にする', () => {
  assert.equal(summarizeToolTarget({ path: ['a', 'b'] }), '["a","b"]');
});

test('AC-08 追加: 対象の鍵のないツールの呼び出しは target null', () => {
  const log = parseStageLog(logText([promptLine('design'), assistantTool('TodoWrite', { todos: [] })]));
  assert.deepEqual(log.items, [{ kind: 'tool', tool: 'TodoWrite', target: null }]);
});

test('AC-09 追加: 1つの発言に文章とツールの呼び出しが並べば、その順で2件', () => {
  const line = JSON.stringify({
    _type: 'AssistantMessage',
    content: [{ text: '読みます' }, { id: 't', name: 'Read', input: { file_path: 'x.md' } }],
  });
  const log = parseStageLog(logText([promptLine('design'), line]));
  assert.deepEqual(log.items, [
    { kind: 'text', text: '読みます' },
    { kind: 'tool', tool: 'Read', target: 'x.md' },
  ]);
});

test('AC-10 追加: 空白だけの文章・UserMessage の文章・content が配列でない発言は項目にしない', () => {
  const log = parseStageLog(
    logText([
      promptLine('design'),
      assistantText('   \n '),
      JSON.stringify({ _type: 'UserMessage', content: [{ text: 'ユーザー' }] }),
      JSON.stringify({ _type: 'AssistantMessage', content: 'not array' }),
      JSON.stringify({ _type: 'AssistantMessage', content: [null, 1, 'x', { foo: 1 }, { name: 'X', input: 'bad' }] }),
    ]),
  );
  assert.deepEqual(log.items, []);
});

test('AC-11 追加: CRLF の改行でも行ごとに読める', () => {
  const text = [promptLine('design'), assistantText('A'), assistantText('B')].join('\r\n') + '\r\n';
  const log = parseStageLog(text);
  assert.deepEqual(
    log.items.map((i) => (i.kind === 'text' ? i.text : '')),
    ['A', 'B'],
  );
});

test('AC-12 追加: 空文字・壊れた行だけのログでも例外なく0件', () => {
  assert.deepEqual(parseStageLog('').items, []);
  assert.deepEqual(parseStageLog('{"_type":\n[1,2]\n42\n').items, []);
});

test('FR-04 追加: Prompt 行がなければ先頭から読み、hasPrompt は false', () => {
  const log = parseStageLog(logText([assistantText('A')]));
  assert.equal(log.hasPrompt, false);
  assert.deepEqual(log.items, [{ kind: 'text', text: 'A' }]);
});

test('FR-07 追加: finished は最後の Prompt より後ろの ResultMessage だけで決まる', () => {
  const resumed = parseStageLog(logText([promptLine('design'), resultLine(), promptLine('design'), assistantText('B')]));
  assert.equal(resumed.finished, false);
  const done = parseStageLog(logText([promptLine('design'), assistantText('A'), resultLine()]));
  assert.equal(done.finished, true);
  assert.deepEqual(done.items, [{ kind: 'text', text: 'A' }]);
});

// ---- 成果物（FR-11） ----

test('AC-34 追加: 7件すべての名前とラベルがあり、中身のない一覧では全部「まだない」', () => {
  const list = buildArtifactList({});
  assert.deepEqual(
    list.map((a) => a.name),
    [
      '00_input.md',
      '01_requirements.md',
      '02_design.md',
      '03_red_tests.md',
      '04_implementation.md',
      '05_test_report.md',
      '99_summary.md',
    ],
  );
  assert.ok(list.every((a) => a.ready === false && a.label.length > 0));
  assert.equal(buildArtifactList({ '00_input.md': '' })[0].ready, false);
});

test('AC-36 追加: 7つの名前以外（state.json・ログ・絶対パス・大文字違い・前後の空白・../ の混ざり）は拒否', () => {
  const w = path.resolve('/w/docs/pipeline');
  for (const name of [
    'state.json',
    'logs/01_requirements.jsonl',
    '/etc/passwd',
    path.join(w, '01_requirements.md'),
    '01_REQUIREMENTS.md',
    ' 01_requirements.md',
    './01_requirements.md',
    '01_requirements.md/../../secret.md',
    '..\\secret.md',
    '',
  ]) {
    assert.equal(resolveArtifactPath(w, name), null, name);
  }
  for (const name of ['00_input.md', '99_summary.md', '05_test_report.md']) {
    assert.equal(resolveArtifactPath(w, name), path.join(w, name));
  }
});

// ---- 図の状態（FR-06〜FR-14） ----

test('AC-15 追加: 確認の節だけ reviseCount が数値、実装の節だけ sendBackCount が数値、段の実行がなければ metrics は null', () => {
  const view = buildPipelineView(snapshot());
  for (const n of view.nodes) {
    assert.equal(n.reviseCount === null, !n.id.startsWith('review:'), n.id);
    assert.equal(n.sendBackCount === null, n.id !== 'implement', n.id);
    assert.equal(n.metrics, null, n.id);
  }
  assert.equal(view.runningStage, null);
  assert.deepEqual(view.terminal, { source: null, items: [] });
  assert.equal(view.totalCostUsd, 0);
  assert.equal(view.waiting, false);
});

test('AC-16 追加: 00_input.md が空白だけなら要件メモの節は「まだ」', () => {
  const view = buildPipelineView(snapshot({ artifacts: { '00_input.md': ' \n\t' } }));
  assert.equal(node(view, 'input').status, 'pending');
});

test('AC-18 追加: 同じ段の最後の段の実行で決まる（失敗のあと成功なら完了、成功のあと失敗なら失敗）', () => {
  const ok = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [stageRunEntry({ stage: 'design', seq: 1, isError: true }), stageRunEntry({ stage: 'design', seq: 2 })],
      }),
    }),
  );
  assert.equal(node(ok, 'design').status, 'done');
  const ng = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [stageRunEntry({ stage: 'design', seq: 1 }), stageRunEntry({ stage: 'design', seq: 2, isError: true })],
      }),
    }),
  );
  assert.equal(node(ng, 'design').status, 'failed');
});

test('AC-19 追加: 段の実行が無く（最大 seq 0）、01_requirements.jsonl が実行中なら要件定義が「動いている」', () => {
  const view = buildPipelineView(
    snapshot({ stageLogs: [{ fileName: '01_requirements.jsonl', text: logText([promptLine('requirements')]) }] }),
  );
  assert.equal(view.runningStage, 'requirements');
  assert.equal(node(view, 'requirements').status, 'running');
  assert.equal(view.noRecords, null);
});

test('AC-19 追加: 前の段の実行で失敗した段でも、もう一度動いていれば「動いている」', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({ runs: [stageRunEntry({ stage: 'implement', seq: 4, attempt: 1, isError: true })] }),
      stageLogs: [{ fileName: '05_implement_2.jsonl', text: logText([promptLine('implement'), assistantText('x')]) }],
    }),
  );
  assert.equal(node(view, 'implement').status, 'running');
});

test('FR-07 追加: Prompt 行のないログ・ResultMessage のあるログは動いている段にならない', () => {
  const noPrompt = buildPipelineView(
    snapshot({ stageLogs: [{ fileName: '01_requirements.jsonl', text: logText([assistantText('A')]) }] }),
  );
  assert.equal(noPrompt.runningStage, null);
  const finished = buildPipelineView(
    snapshot({
      stageLogs: [{ fileName: '01_requirements.jsonl', text: logText([promptLine('requirements'), resultLine()]) }],
    }),
  );
  assert.equal(finished.runningStage, null);
  assert.ok(finished.nodes.every((n) => n.status !== 'running'));
});

test('FR-07 追加: 候補が複数あれば通し番号の大きい方。動いている節はちょうど1つ', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }),
      stageLogs: [
        { fileName: '03_red.jsonl', text: logText([promptLine('red')]) },
        { fileName: '02_design.jsonl', text: logText([promptLine('design')]) },
      ],
    }),
  );
  assert.equal(view.runningStage, 'red');
  assert.equal(view.nodes.filter((n) => n.status === 'running').length, 1);
});

test('FR-03 追加: 名前の読めないログは無視される（記録なしの判定でも数えない）', () => {
  const view = buildPipelineView(
    snapshot({ workDir: '/x', stageLogs: [{ fileName: 'notes.jsonl', text: logText([promptLine('design')]) }] }),
  );
  assert.equal(view.runningStage, null);
  assert.equal(view.terminal.source, null);
  assert.deepEqual(view.noRecords, { message: '記録がありません', workDir: '/x' });
});

test('AC-21/23 追加: revise のあと approved なら「完了」で回数 1。revise だけなら「まだ」。ほかの段の確認は数えない', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [
          { stage: 'requirements', review: 'revise', feedback: 'a' },
          { stage: 'requirements', review: 'approved' },
          { stage: 'design', review: 'revise', feedback: 'b' },
          { stage: 'red', review: 'approved' },
          { stage: 'red', review: 'revise', feedback: 'c' },
        ],
      }),
    }),
  );
  assert.equal(node(view, 'review:requirements').status, 'done');
  assert.equal(node(view, 'review:requirements').reviseCount, 1);
  assert.equal(node(view, 'review:design').status, 'pending');
  assert.equal(node(view, 'review:design').reviseCount, 1);
  assert.equal(node(view, 'review:red').status, 'pending');
  assert.equal(node(view, 'review:red').reviseCount, 1);
});

test('AC-24 追加: attempt null・1 だけなら差し戻し 0。検証の段の attempt 2 は数えない', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [
          stageRunEntry({ stage: 'implement', seq: 1, attempt: null }),
          stageRunEntry({ stage: 'implement', seq: 2, attempt: 1 }),
          stageRunEntry({ stage: 'test', seq: 3, attempt: 2 }),
        ],
      }),
    }),
  );
  assert.equal(node(view, 'implement').sendBackCount, 0);
});

test('AC-25 追加: 判定が pass → fail の順なら「失敗」', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [
          { stage: 'test', attempt: 1, verdict: { status: 'pass', summary: '' } },
          { stage: 'test', attempt: 2, verdict: { status: 'fail', summary: '' } },
        ],
      }),
    }),
  );
  assert.equal(node(view, 'verdict').status, 'failed');
});

test('AC-28 追加: final が STOPPED_BY_HUMAN・STAGE_ERROR・BLOCKED・知らない文字列なら完了の節は「失敗」', () => {
  for (const final of ['STOPPED_BY_HUMAN', 'STAGE_ERROR', 'BLOCKED', 'SOMETHING']) {
    const view = buildPipelineView(snapshot({ stateJson: stateJson({ final }) }));
    assert.equal(node(view, 'final').status, 'failed', final);
    assert.equal(view.final, final);
  }
});

test('AC-30 追加: 同じ通し番号のログが2本あれば、ファイル名が後ろのものを出す', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({ runs: [stageRunEntry({ stage: 'implement', seq: 5, attempt: 2 })] }),
      stageLogs: [
        { fileName: '05_implement_2.jsonl', text: logText([promptLine('implement'), assistantText('I'), resultLine()]) },
        { fileName: '05_implement.jsonl', text: logText([promptLine('implement'), assistantText('H'), resultLine()]) },
      ],
    }),
  );
  assert.deepEqual(view.terminal.source, { seq: 5, stage: 'implement', attempt: 2 });
  assert.deepEqual(view.terminal.items, [{ kind: 'text', text: 'I' }]);
});

test('AC-32 追加: 段の実行のない段の metrics は null、ある段は合計、ほかの段の数値は混ざらない', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [
          stageRunEntry({ stage: 'requirements', seq: 1, numTurns: 3, costUsd: 0.05, durationSec: 12.34 }),
          stageRunEntry({ stage: 'design', seq: 2, numTurns: 7, costUsd: 0.1, durationSec: 5 }),
        ],
      }),
    }),
  );
  assert.deepEqual(node(view, 'requirements').metrics, { numTurns: 3, costUsd: 0.05, durationSec: 12.3 });
  assert.deepEqual(node(view, 'design').metrics, { numTurns: 7, costUsd: 0.1, durationSec: 5 });
  assert.equal(node(view, 'red').metrics, null);
  assert.equal(node(view, 'review:requirements').metrics, null);
});

test('AC-37 追加: 同じ写しからは何度組み立てても等しく、写しを書き換えない', () => {
  const snap = snapshot({
    stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })], totalCostUsd: 0.5 }),
    stageLogs: [
      { fileName: '02_design.jsonl', text: logText([promptLine('design'), assistantText('A')]) },
      { fileName: '01_requirements.jsonl', text: logText([promptLine('requirements'), resultLine()]) },
    ],
    artifacts: { '00_input.md': 'x', '01_requirements.md': 'y' },
  });
  const before = JSON.parse(JSON.stringify(snap));
  const a = buildPipelineView(snap);
  const b = buildPipelineView(snap);
  assert.deepStrictEqual(a, b);
  assert.deepStrictEqual(snap, before);
  // ログの並び（写しの順）を変えても同じ
  const reversed = buildPipelineView({ ...snap, stageLogs: [...snap.stageLogs].reverse() });
  assert.deepStrictEqual(reversed, a);
});

test('AC-38 追加: 段の実行が0件なら待ちの表示は無効（確認の結果だけあっても）', () => {
  const view = buildPipelineView(
    snapshot({ stateJson: stateJson({ runs: [{ stage: 'requirements', review: 'approved' }] }) }),
  );
  assert.equal(view.waiting, false);
});

test('AC-40 追加: final が PASSED 以外の値（STOPPED_BY_HUMAN）でも待ちの表示は無効', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })], final: 'STOPPED_BY_HUMAN' }),
    }),
  );
  assert.equal(view.waiting, false);
});

test('AC-41 追加: state.json・名前の読めるログ・00_input.md（空でも）のどれかがあれば記録なしの表示は無効', () => {
  assert.equal(buildPipelineView(snapshot({ stateJson: '{"runs": [' })).noRecords, null);
  assert.equal(buildPipelineView(snapshot({ artifacts: { '00_input.md': '' } })).noRecords, null);
  assert.equal(
    buildPipelineView(snapshot({ stageLogs: [{ fileName: '01_requirements.jsonl', text: '' }] })).noRecords,
    null,
  );
  // 00_input.md 以外の成果物だけあっても、記録なしの表示は有効（FR-14 の3つに入らない）
  assert.notEqual(buildPipelineView(snapshot({ artifacts: { '02_design.md': 'x' } })).noRecords, null);
});

test('FR-05 追加: どの記録も壊れた写しでも例外を投げず、節は11個', () => {
  const view = buildPipelineView(
    snapshot({
      stateJson: '\u0000garbage',
      stageLogs: [
        { fileName: '01_requirements.jsonl', text: '\u0000\n{"_type":' },
        { fileName: '02_design.jsonl', text: '[]\n"x"\nnull\n' },
      ],
      artifacts: { '00_input.md': '\u0000' },
    }),
  );
  assert.equal(view.nodes.length, 11);
});
