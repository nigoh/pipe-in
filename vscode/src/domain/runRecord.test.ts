// 実行の記録（state.json）の読み取り。AC-03〜AC-05。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseRunRecord } from './runRecord.ts';
import { stageRunEntry, stateJson } from '../test/fixtures.ts';

test('AC-03: state.json がないとき、例外が出ず、段の実行0件・final null・合計の費用 0', () => {
  const record = parseRunRecord(null);
  assert.deepEqual(record.stageRuns, []);
  assert.equal(record.final, null);
  assert.equal(record.totalCostUsd, 0);
});

const pendingOf = (since: unknown) =>
  parseRunRecord(
    stateJson({ pendingReview: { stage: 'design', doc: 'docs/pipeline/02_design.md', session_id: 's', ...(since === undefined ? {} : { since }) } }),
  ).pendingReview;

test('D0017-AC-07: pending_review.since が読まれる（stage・doc は今までどおり）', () => {
  for (const since of ['2026-10-17T10:00:00+09:00', '2026-10-17T10:00:00']) {
    const pending = pendingOf(since);
    assert.ok(pending !== null);
    assert.equal(pending.since, since);
    assert.equal(pending.stage, 'design');
    assert.equal(pending.doc, 'docs/pipeline/02_design.md');
  }
});

for (const [label, since] of [
  ['無い', undefined],
  ['数', 1792230000],
  ['オブジェクト', { a: 1 }],
  ['null', null],
  ['空の文字', ''],
  ['"x"', 'x'],
  ['存在しない日付', '2026-02-30T10:00:00'],
] as const) {
  test(`D0017-AC-07: since が${label}なら null（pending_review そのものは残り、例外を投げない）`, () => {
    const pending = pendingOf(since);
    assert.ok(pending !== null, '確認待ちの印は残る');
    assert.equal(pending.since, null);
    assert.equal(pending.stage, 'design');
  });
}

test('D0017-AC-07: 確認待ちが無い記録では pendingReview は null のまま', () => {
  assert.equal(parseRunRecord(stateJson({})).pendingReview, null);
});

test('AC-04: 途中で切れた JSON でも、例外が出ず AC-03 と同じ結果', () => {
  const record = parseRunRecord('{"runs": [');
  assert.deepEqual(record.stageRuns, []);
  assert.equal(record.final, null);
  assert.equal(record.totalCostUsd, 0);
});

test('AC-05: 段の実行・確認の結果・テスト先行の結果・判定を区別して1件ずつ取り出す', () => {
  const text = stateJson({
    runs: [
      stageRunEntry({ stage: 'red', seq: 3 }),
      { stage: 'red', review: 'approved', feedback: null },
      { stage: 'red', result: { status: 'red', summary: '落ちた', tests: [], commands: [] } },
      { stage: 'red', command_check: { command: 'npm test', returncode: 1 } },
      {
        stage: 'test',
        attempt: 1,
        verdict: { status: 'pass', summary: '通った', failures: [], commands: [], command_check: null },
      },
    ],
  });
  const record = parseRunRecord(text);

  assert.equal(record.stageRuns.length, 1);
  assert.equal(record.stageRuns[0].stage, 'red');
  assert.equal(record.stageRuns[0].seq, 3);

  assert.equal(record.reviews.length, 1);
  assert.equal(record.reviews[0].stage, 'red');
  assert.equal(record.reviews[0].action, 'approved');

  assert.equal(record.redResults.length, 1);
  assert.equal(record.redResults[0].status, 'red');

  assert.equal(record.verdicts.length, 1);
  assert.equal(record.verdicts[0].status, 'pass');
});

// ---- D0016：検証の不合格の「直す点」（failures）を読む ----

const failEntry = (failures?: unknown): object => ({
  stage: 'test',
  attempt: 1,
  verdict: { status: 'fail', summary: '不合格', ...(failures === undefined ? {} : { failures }) },
});

test('D0016-AC-01: 不合格の判定の failures（criterion・detail）を読む', () => {
  const record = parseRunRecord(
    stateJson({ runs: [failEntry([{ criterion: 'AC-02', detail: '出力の先頭に BOM が無い' }, { criterion: 'AC-03', detail: '列の順が違う' }])] }),
  );
  assert.equal(record.verdicts.length, 1);
  assert.deepEqual(record.verdicts[0].failures, [
    { criterion: 'AC-02', detail: '出力の先頭に BOM が無い' },
    { criterion: 'AC-03', detail: '列の順が違う' },
  ]);
});

// 読めない形の failures。例外を投げず、読める要素だけを残す（片方だけ文字列なら、もう片方は空の文字列）
const UNREADABLE_FAILURES: [string, unknown, { criterion: string; detail: string }[]][] = [
  ['failures が無い', undefined, []],
  ['null', null, []],
  ['文字列', 'AC-02 が不合格', []],
  ['数', 3, []],
  ['配列でないオブジェクト', { criterion: 'AC-02', detail: 'd' }, []],
  ['要素が数・文字列・null・空のオブジェクトだけ', [1, 'AC-02', null, {}], []],
  ['要素の criterion・detail が文字列でない', [{ criterion: 1, detail: 2 }], []],
  ['criterion だけ文字列', [{ criterion: 'AC-01' }], [{ criterion: 'AC-01', detail: '' }]],
  ['detail だけ文字列', [{ detail: '直して' }], [{ criterion: '', detail: '直して' }]],
  ['読めない要素の間の読める要素', [1, { criterion: 'AC-02', detail: 'd' }, null], [{ criterion: 'AC-02', detail: 'd' }]],
];
for (const [label, failures, expected] of UNREADABLE_FAILURES) {
  test(`D0016-AC-02: failures が読めない形（${label}）でも例外を投げず、読める要素だけが残る`, () => {
    const record = parseRunRecord(stateJson({ runs: [failEntry(failures)] }));
    assert.equal(record.verdicts.length, 1);
    assert.deepEqual(record.verdicts[0].failures, expected);
    assert.equal(record.verdicts[0].summary, '不合格');
  });
}

// ---- D0019（2版目）：セッション名・セッション ID・受け持ち ----

test('D0019-AC-51: state.json の name（文字）と session_id（文字）が読まれる。無い記録（古い形）では null', () => {
  const record = parseRunRecord(stateJson({ name: '仕様の QA を回す', sessionId: '7f3a9c01-2b4d-4e5f-8a6b-0c1d2e3f4a5b' }));
  assert.equal(record.name, '仕様の QA を回す');
  assert.equal(record.sessionId, '7f3a9c01-2b4d-4e5f-8a6b-0c1d2e3f4a5b');
  const old = parseRunRecord(stateJson({}));
  assert.equal(old.name, null);
  assert.equal(old.sessionId, null);
  assert.equal(parseRunRecord(null).name, null);
  assert.equal(parseRunRecord('{壊れた').sessionId, null);
});

test('D0019-AC-51: name は 200 文字まで、session_id は 100 文字まで読む（ちょうどは通る）', () => {
  assert.equal(parseRunRecord(stateJson({ name: 'あ'.repeat(200) })).name, 'あ'.repeat(200));
  assert.equal(parseRunRecord(stateJson({ sessionId: 'a'.repeat(100) })).sessionId, 'a'.repeat(100));
});

const BAD_NAMES: [string, unknown][] = [
  ['数', 5],
  ['null', null],
  ['配列', ['a']],
  ['オブジェクト', { a: 1 }],
  ['真偽', true],
  ['空の文字', ''],
  ['201 文字', 'あ'.repeat(201)],
];
for (const [label, value] of BAD_NAMES) {
  test(`D0019-AC-51: name が読めない形（${label}）なら null。例外を出さず、ほかの項目は読める`, () => {
    const record = parseRunRecord(stateJson({ name: value, totalCostUsd: 2, runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }));
    assert.equal(record.name, null);
    assert.equal(record.totalCostUsd, 2);
    assert.equal(record.stageRuns.length, 1);
  });
}

const BAD_TOKENS: [string, unknown][] = [
  ['数', 5],
  ['null', null],
  ['配列', ['a']],
  ['空の文字', ''],
  ['101 文字', 'a'.repeat(101)],
  ['空白を含む', 'a b'],
  ['改行を含む', 'a\nb'],
  ['タブを含む', 'a\tb'],
  ['制御文字を含む', 'a\u0000b'],
  ['全角空白を含む', 'a　b'],
];
for (const [label, value] of BAD_TOKENS) {
  test(`D0019-AC-51: session_id が読めない形（${label}）なら null。例外を出さない`, () => {
    assert.equal(parseRunRecord(stateJson({ sessionId: value })).sessionId, null);
  });

  test(`D0019-AC-51: runs[] の agent・session_id が読めない形（${label}）なら、その項目だけ null。段の実行は読める`, () => {
    const record = parseRunRecord(stateJson({ runs: [stageRunEntry({ stage: 'design', seq: 1, agent: value, sessionId: value, durationSec: 12 })] }));
    assert.equal(record.stageRuns.length, 1);
    assert.equal(record.stageRuns[0]!.agent, null);
    assert.equal(record.stageRuns[0]!.sessionId, null);
    assert.equal(record.stageRuns[0]!.durationSec, 12);
  });
}

test('D0019-AC-51: runs[] の agent（受け持ち）と session_id（SDK の会話の ID）が段の実行ごとに読まれる。無ければ null', () => {
  const record = parseRunRecord(
    stateJson({
      runs: [
        stageRunEntry({ stage: 'requirements', seq: 1, agent: 'pipe-in-analyst', sessionId: 'sess-1' }),
        stageRunEntry({ stage: 'design', seq: 2, sessionId: null }),
        stageRunEntry({ stage: 'red', seq: 3 }),
      ],
    }),
  );
  assert.deepEqual(record.stageRuns.map((r) => [r.agent, r.sessionId]), [['pipe-in-analyst', 'sess-1'], [null, null], [null, 's']]);
});

test('D0019-AC-53: 確認の結果（review）が、直前の同じ段の実行に付く（修正の依頼・承認・中止）。reviews はこれまでどおり全部残る', () => {
  const record = parseRunRecord(
    stateJson({
      runs: [
        stageRunEntry({ stage: 'requirements', seq: 1 }),
        { stage: 'requirements', review: 'revise', feedback: '直して' },
        stageRunEntry({ stage: 'requirements', seq: 2 }),
        { stage: 'requirements', review: 'approved' },
        stageRunEntry({ stage: 'design', seq: 3 }),
        { stage: 'design', review: 'quit' },
        stageRunEntry({ stage: 'red', seq: 4 }),
      ],
    }),
  );
  assert.deepEqual(record.stageRuns.map((r) => r.review), ['revise', 'approved', 'quit', null]);
  assert.equal(record.reviews.length, 3);
  assert.deepEqual(record.reviews.map((r) => r.action), ['revise', 'approved', 'quit']);
});

test('D0019-AC-53: 確認の結果は、同じ段の最後の実行で、まだ確認の結果が付いていないものに付く。実行が無い段の確認は捨てても例外を出さない', () => {
  const record = parseRunRecord(
    stateJson({
      runs: [
        { stage: 'design', review: 'approved' },
        stageRunEntry({ stage: 'requirements', seq: 1 }),
        stageRunEntry({ stage: 'design', seq: 2 }),
        { stage: 'requirements', review: 'approved' },
        { stage: 'requirements', review: 'quit' },
      ],
    }),
  );
  assert.deepEqual(record.stageRuns.map((r) => [r.stage, r.review]), [['requirements', 'approved'], ['design', null]]);
});

test('D0019-AC-53: 判定・テスト先行の結果・check の要素は、段の実行の review にならない', () => {
  const record = parseRunRecord(
    stateJson({
      runs: [
        stageRunEntry({ stage: 'test', seq: 1, attempt: 1 }),
        { stage: 'test', attempt: 1, verdict: { status: 'fail', summary: 'x', failures: [], commands: [], command_check: null } },
        { stage: 'test', check: { status: 'fail', problems: ['x'] } },
      ],
    }),
  );
  assert.equal(record.stageRuns[0]!.review, null);
});

test('D0019-AC-30: name・session_id・agent の無い古い形の記録は今までどおり読め、足した項目は null になるだけ', () => {
  const record = parseRunRecord(stateJson({ final: 'PASSED', totalCostUsd: 1.5, runs: [stageRunEntry({ stage: 'requirements', seq: 1, durationSec: 30 })] }));
  assert.equal(record.final, 'PASSED');
  assert.equal(record.totalCostUsd, 1.5);
  assert.equal(record.stageRuns[0]!.durationSec, 30);
  assert.equal(record.name, null);
  assert.equal(record.sessionId, null);
  assert.equal(record.stageRuns[0]!.agent, null);
});
