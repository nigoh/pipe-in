// 記録の読み（D0062 の AC-05・AC-13）：stages[].check と runs[] の check の要素（attempt・status・summary・problems）。
// 本体が書く形と拡張が読む形は、共通の表 tests/fixtures/check_record.json で結ぶ（本体のテストも同じ表を読む）。
// RunRecord.checks と StageDef.check は、実装の段で型に入るまで、型に頼らず読む（test/checkFixtures.ts の checksOf・stageCheckOf）。
// 赤の理由は「まだ読んでいない」：新しい項目が undefined になる（期待は null や配列。厳密に比べる）。
// 「今のまま通る。守る」と書いたものは、今の作りで通り、実装のあとも通り続けることを見張る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseRunRecord } from './runRecord.ts';
import { stateJson } from '../test/fixtures.ts';
import { checkEntry, checkRecord, checksOf, loadCheckTable, runEntry, stageCheckOf, stageDef } from '../test/checkFixtures.ts';

const PIPE = { pipe: 'p' };
const VERIFY_CHECK = { on_fail: 'draw', max_retries: 2 };

/** draw と verify の 2 段のパイプの記録を読む。verifyCheck は stages[verify].check、runs はそのまま。 */
function readPipe(verifyCheck: unknown, runs: readonly object[] = []) {
  return checkRecord(runs, { ...PIPE, stages: [stageDef({ name: 'draw' }), stageDef({ name: 'verify', check: verifyCheck })] });
}

// ======== AC-05：新しい形を RunRecord に読む ========

test('D0062-AC-05: stages[].check と check の要素を RunRecord に読む', () => {
  const record = checkRecord(
    [
      runEntry('draw', 1),
      runEntry('verify', 2),
      checkEntry({ stage: 'verify', status: 'fail', attempt: 1, summary: '図が足りない', problems: ['矢印が逆', '凡例が無い'] }),
      runEntry('draw', 3),
      runEntry('verify', 4),
      checkEntry({ stage: 'verify', status: 'pass', attempt: 2, summary: 'よい', problems: [] }),
    ],
    { ...PIPE, stages: [stageDef({ name: 'draw' }), stageDef({ name: 'verify', check: VERIFY_CHECK })] },
  );
  assert.equal(stageCheckOf(record, 'draw'), null, '判定の無い段の check は null');
  assert.deepEqual(stageCheckOf(record, 'verify'), { onFail: 'draw', maxRetries: 2 });
  assert.deepEqual(checksOf(record), [
    { stage: 'verify', attempt: 1, status: 'fail', summary: '図が足りない', problems: ['矢印が逆', '凡例が無い'] },
    { stage: 'verify', attempt: 2, status: 'pass', summary: 'よい', problems: [] },
  ]);
});

test('D0062-AC-05: check の要素は段の実行（stageRuns）に入らず、段の実行の読みは変わらない', () => {
  const record = readPipe(VERIFY_CHECK, [runEntry('draw', 1), runEntry('verify', 2), checkEntry({ stage: 'verify', status: 'pass', attempt: 1 })]);
  assert.deepEqual(record.stageRuns.map((r) => r.seq), [1, 2]);
  assert.equal(checksOf(record)?.length, 1);
});

test('D0062-AC-05: check の項目が無い記録では、checks は空・stages[].check は null', () => {
  const record = readPipe(undefined, [runEntry('draw', 1), runEntry('verify', 2)]);
  assert.deepEqual(checksOf(record), []);
  assert.equal(stageCheckOf(record, 'draw'), null);
  assert.equal(stageCheckOf(record, 'verify'), null);
});

test('D0062-AC-05: 記録が空・壊れた JSON・形の違う JSON でも、checks は空の配列で例外を出さない', () => {
  for (const text of [null, '{', '[]', '"x"', '{}', stateJson({})]) {
    assert.deepEqual(checksOf(parseRunRecord(text)), [], String(text));
  }
});

// ---- stages[].check の壊れた形 ----

const STAGE_CHECK_CASES: readonly (readonly [string, unknown, unknown])[] = [
  ['文字', 'x', null],
  ['配列', [], null],
  ['数', 5, null],
  ['null', null, null],
  ['真偽', true, null],
  ['空のオブジェクト', {}, { onFail: null, maxRetries: null }],
  ['on_fail が null', { on_fail: null, max_retries: 2 }, { onFail: null, maxRetries: 2 }],
  ['on_fail が数', { on_fail: 3, max_retries: 2 }, { onFail: null, maxRetries: 2 }],
  ['on_fail が配列', { on_fail: ['draw'], max_retries: 2 }, { onFail: null, maxRetries: 2 }],
  ['on_fail が自分自身の名前', { on_fail: 'verify', max_retries: 2 }, { onFail: null, maxRetries: 2 }],
  ['on_fail が段の名前でない文字', { on_fail: '../x', max_retries: 2 }, { onFail: null, maxRetries: 2 }],
  ['max_retries が 0', { on_fail: null, max_retries: 0 }, { onFail: null, maxRetries: 0 }],
  ['max_retries が負', { on_fail: null, max_retries: -1 }, { onFail: null, maxRetries: null }],
  ['max_retries が小数', { on_fail: null, max_retries: 1.5 }, { onFail: null, maxRetries: null }],
  ['max_retries が文字', { on_fail: null, max_retries: '2' }, { onFail: null, maxRetries: null }],
  ['max_retries が真偽', { on_fail: null, max_retries: true }, { onFail: null, maxRetries: null }],
  ['max_retries が null', { on_fail: 'draw', max_retries: null }, { onFail: 'draw', maxRetries: null }],
  ['max_retries の項目なし', { on_fail: 'draw' }, { onFail: 'draw', maxRetries: null }],
];
for (const [label, value, expected] of STAGE_CHECK_CASES) {
  test(`D0062-AC-05: 壊れた形は捨てるか null にして例外を出さない：stages[].check が ${label}`, () => {
    assert.deepEqual(stageCheckOf(readPipe(value), 'verify'), expected);
  });
}

// ---- check の要素の壊れた形 ----

const BROKEN_ENTRIES: readonly (readonly [string, object])[] = [
  ['check が文字', { stage: 'verify', check: 'x' }],
  ['check が配列', { stage: 'verify', check: [] }],
  ['check が null', { stage: 'verify', check: null }],
  ['check が数', { stage: 'verify', check: 3 }],
  ['status が不明な文字', { stage: 'verify', check: { status: 'maybe', problems: [], summary: 'x' } }],
  ['status が数', { stage: 'verify', check: { status: 1, problems: [], summary: 'x' } }],
  ['status が無い', { stage: 'verify', check: { problems: [], summary: 'x' } }],
  ['stage が無い', { check: { status: 'fail', problems: [], summary: 'x' } }],
  ['stage が数', { stage: 7, check: { status: 'fail', problems: [], summary: 'x' } }],
  ['stage が段の名前でない文字', { stage: '../x', check: { status: 'fail', problems: [], summary: 'x' } }],
];
for (const [label, entry] of BROKEN_ENTRIES) {
  test(`D0062-AC-05: 壊れた形は捨てるか null にして例外を出さない：check の要素が ${label}`, () => {
    const record = readPipe(VERIFY_CHECK, [runEntry('draw', 1), entry, checkEntry({ stage: 'verify', status: 'pass', attempt: 1 })]);
    assert.deepEqual(
      checksOf(record)?.map((c) => `${c.stage}:${c.status}:${c.attempt}`),
      ['verify:pass:1'],
      '壊れた要素は捨て、読める要素だけ残る',
    );
  });
}

test('D0062-AC-05: attempt が文字・小数でない・無いときは null、読める要素は残す（並びの番号は図の組み立てで使う）', () => {
  const record = readPipe(VERIFY_CHECK, [
    checkEntry({ stage: 'verify', status: 'fail', attempt: '2' }),
    checkEntry({ stage: 'verify', status: 'fail', attempt: null }),
    checkEntry({ stage: 'verify', status: 'fail' }),
    checkEntry({ stage: 'verify', status: 'pass', attempt: 4 }),
  ]);
  assert.deepEqual(checksOf(record)?.map((c) => c.attempt), [null, null, null, 4]);
});

test('D0062-AC-05: summary が文字でなければ空・problems は文字だけ残す（文字でない値は捨てる・配列でなければ空）', () => {
  const record = readPipe(VERIFY_CHECK, [
    checkEntry({ stage: 'verify', status: 'fail', attempt: 1, summary: 3, problems: ['a', 3, null, { x: 1 }, 'b'] }),
    checkEntry({ stage: 'verify', status: 'fail', attempt: 2, summary: null, problems: 'a' }),
    checkEntry({ stage: 'verify', status: 'fail', attempt: 3, summary: { x: 1 }, problems: null }),
    checkEntry({ stage: 'verify', status: 'pass', attempt: 4, summary: '', problems: [] }),
  ]);
  const checks = checksOf(record);
  assert.deepEqual(checks?.map((c) => c.summary), ['', '', '', '']);
  assert.deepEqual(checks?.map((c) => c.problems), [['a', 'b'], [], [], []]);
});

test('D0062-AC-05: 開発フローの記録（stages が無い・開発の 5 段）では、check の要素を読まず checks は空', () => {
  const entry = checkEntry({ stage: 'test', status: 'fail', attempt: 1 });
  assert.deepEqual(checksOf(checkRecord([entry])), [], 'stages が無い記録');
  const dev = ['requirements', 'design', 'red', 'implement', 'test'].map((name) => stageDef({ name }));
  assert.deepEqual(checksOf(checkRecord([entry], { pipe: 'dev', stages: dev })), [], '開発の 5 段の記録');
});

// ======== AC-13：共通の表 ========

test('D0062-AC-13: 共通の表の keys が拡張の読む鍵と同じ（テスト補助が重ねる鍵と同じ）。今のまま通る。守る', () => {
  const table = loadCheckTable();
  assert.deepEqual([...table.keys].sort(), ['attempt', 'check']);
  const plainStage = Object.keys(stageDef({ name: 'a' }));
  const stageKeys = Object.keys(stageDef({ name: 'a', check: {} })).filter((k) => !plainStage.includes(k));
  const plainCheck = Object.keys(checkEntry({ stage: 'a', status: 'pass' }).check);
  const runKeys = Object.keys(checkEntry({ stage: 'a', status: 'pass', attempt: 1 }).check).filter((k) => !plainCheck.includes(k));
  assert.deepEqual([...stageKeys, ...runKeys].sort(), [...table.keys].sort(), 'stageDef・checkEntry が足す鍵は表の keys と同じ');
  for (const c of table.cases) assert.deepEqual(Object.keys(c.written).sort(), [...table.keys].sort(), c.memo);
  assert.ok(table.cases.length >= 3, 'ケースは 3 つ以上');
});

for (const c of loadCheckTable().cases) {
  test(`D0062-AC-13: 共通の表の written を読むと read になる：${c.memo}`, () => {
    const runs: object[] = [runEntry('draw', 1)];
    c.results.forEach((status, i) => {
      runs.push(runEntry('verify', runs.length + 1));
      runs.push(checkEntry({ stage: 'verify', status, attempt: c.written.attempt[i] }));
    });
    const record = checkRecord(runs, {
      ...PIPE,
      stages: [stageDef({ name: 'draw' }), stageDef({ name: 'verify', check: c.written.check })],
    });
    assert.deepEqual(stageCheckOf(record, 'verify'), { onFail: c.read.onFail, maxRetries: c.read.maxRetries });
    assert.deepEqual(
      checksOf(record)?.map((x) => ({ attempt: x.attempt, status: x.status })),
      c.read.checks,
    );
  });
}
