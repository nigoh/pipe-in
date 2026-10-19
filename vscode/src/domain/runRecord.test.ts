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
