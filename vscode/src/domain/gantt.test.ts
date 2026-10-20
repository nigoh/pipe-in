// 時系列（D0019）：記録の写しから、段の実行ごとの行・エージェントの帯・確認を待った帯・横軸を組み立てる（純粋な関数）。
// 組み立ては buildPipelineView の結果（PipelineView.gantt）で確かめる：記録の写しと「今」だけから決まる。新しい部品（domain/gantt.ts）は、
// 呼んだところで落ちるように、gantt が無いことで落ちる。時刻は BASE（2026-10-17 10:00:00 UTC）からの秒で書く。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPipelineView } from './pipelineView.ts';
import type { WorkDirSnapshot } from './pipelineView.ts';
import type { GanttModel, GanttRow } from './gantt.ts';
import { DIAGRAMS_STAGES, snapshot, stageRunEntry, stateJson } from '../test/fixtures.ts';
import { clockAt } from '../test/liveFixtures.ts';
import { GANTT_STARTED_AT, atSec, finishedGantt, ganttSnapshot, naiveAtSec, review, stageLog } from '../test/ganttFixtures.ts';
import { failVerdict } from '../test/reasonFixtures.ts';

const model = (snap: WorkDirSnapshot, nowSec = 400, localOffsetMin = 0): GanttModel => buildPipelineView(snap, clockAt(nowSec, localOffsetMin)).gantt;
const near = (actual: number | undefined, expected: number, label = ''): void =>
  assert.ok(actual !== undefined && Math.abs(actual - expected) < 0.001, `${label} ${String(actual)} ≠ ${expected}`);
const bar = (r: GanttRow | undefined) => r?.run ?? null;

/** どの帯も 0 以上 totalSec 以下で、始まり ≤ 終わり（負の幅・欄の外が出ない） */
function assertBounds(g: GanttModel): void {
  for (const row of g.rows) {
    for (const b of [row.run, row.wait]) {
      if (b === null) continue;
      assert.ok(Number.isFinite(b.startSec) && Number.isFinite(b.endSec), `seq ${row.seq}: 有限の数`);
      assert.ok(b.startSec >= 0, `seq ${row.seq}: 始まりが 0 以上 (${b.startSec})`);
      assert.ok(b.endSec >= b.startSec, `seq ${row.seq}: 負の幅が無い (${b.startSec}〜${b.endSec})`);
      assert.ok(b.endSec <= g.totalSec + 0.001, `seq ${row.seq}: 欄の外へ出ない (${b.endSec} > ${g.totalSec})`);
    }
  }
}

// ---- AC-68：段の実行ごとに 1 行 ----

test('D0019-AC-68: 段の実行ごとに 1 行が、通し番号（seq）の順に出る。確認の待ちは別の行にならない', () => {
  const g = model(finishedGantt());
  assert.deepEqual(g.rows.map((r) => r.seq), [1, 2, 3, 4, 5, 6, 7, 8]);
  assert.equal(g.rows.length, 8);
});

test('D0019-AC-68: 行の名前は 段の表示名＋「 N 回目」（回が無い段は回を省く）。受け持ち（agent）は別の項目で、無ければ null', () => {
  const g = model(finishedGantt());
  assert.deepEqual(g.rows.map((r) => r.label), ['要件定義', '要件定義', '設計', 'テスト先行', '実装 1 回目', '検証 1 回目', '実装 2 回目', '検証 2 回目']);
  assert.deepEqual(g.rows.map((r) => r.agent), [
    'pipe-in-analyst',
    'pipe-in-analyst',
    'pipe-in-analyst',
    'pipe-in-tester',
    'pipe-in-coder',
    'pipe-in-verifier',
    'pipe-in-coder',
    'pipe-in-verifier',
  ]);
});

test('D0019-AC-68: agent の無い記録（SDK で流した段・古い記録）では受け持ちが null で、行の名前は 段（と回）だけ', () => {
  const g = model(ganttSnapshot({ runs: [{ stage: 'design', seq: 1, start: 5, durationSec: 10 }, { stage: 'implement', seq: 2, attempt: 1, start: 20, durationSec: 5 }] }));
  assert.deepEqual(g.rows.map((r) => [r.label, r.agent]), [['設計', null], ['実装 1 回目', null]]);
});

test('D0019-AC-68: 並びは通し番号の順（記録の並びが入れ替わっていても）', () => {
  const snap = ganttSnapshot({ runs: [{ stage: 'design', seq: 2, start: 50, durationSec: 5 }, { stage: 'requirements', seq: 1, start: 5, durationSec: 5 }] });
  assert.deepEqual(model(snap).rows.map((r) => [r.seq, r.label]), [[1, '要件定義'], [2, '設計']]);
});

test('D0019-AC-68: パイプの記録の行の名前は、記録の stages の label（段の表示名）', () => {
  const g = model(
    ganttSnapshot({
      pipe: 'diagrams',
      stages: DIAGRAMS_STAGES,
      runs: [{ stage: 'survey', seq: 1, start: 5, durationSec: 10 }, { stage: 'draw', seq: 2, start: 30, durationSec: 10 }],
    }),
  );
  assert.deepEqual(g.rows.map((r) => r.label), ['ソースの調査', '図を描く']);
});

test('D0019-AC-68: 動いている段の行が足される（まだ runs[] に無い段）。動いている段の名前と回がそのログの名前から決まる', () => {
  const g = model(
    ganttSnapshot({
      runs: [{ stage: 'implement', seq: 1, attempt: 1, start: 5, durationSec: 20 }],
      running: { seq: 2, stage: 'test', attempt: 1, start: atSec(40), agent: 'pipe-in-verifier' },
    }),
    100,
  );
  assert.deepEqual(g.rows.map((r) => [r.seq, r.label, r.agent]), [[1, '実装 1 回目', null], [2, '検証 1 回目', 'pipe-in-verifier']]);
});

test('D0019-AC-68: 記録が無いときは行が 0・時刻が無い（hasTimes が偽）・目盛りも空で、例外を出さない', () => {
  const g = model(snapshot());
  assert.deepEqual(g.rows, []);
  assert.equal(g.hasTimes, false);
  assert.equal(g.omittedRows, 0);
  assert.equal(g.live, false);
  assert.deepEqual(g.ticks, []);
});

// ---- AC-69：エージェントの帯 ----

test('D0019-AC-69: 帯は 最後の Prompt の at から、その時刻＋duration_sec まで（記録の始まりからの秒）', () => {
  const g = model(finishedGantt());
  const want: [number, number][] = [[5, 35], [60, 80], [90, 130], [140, 150], [160, 210], [220, 240], [250, 280], [290, 305]];
  g.rows.forEach((r, i) => {
    assert.ok(r.run !== null, `seq ${r.seq} の帯がある`);
    near(r.run.startSec, want[i]![0], `seq ${r.seq} の始まり`);
    near(r.run.endSec, want[i]![1], `seq ${r.seq} の終わり`);
    assert.equal(r.run.live, false);
  });
  assertBounds(g);
});

test('D0019-AC-69: 段のログに Prompt が 2 つあるとき、最後の Prompt の at を始まりにする（最初でなく）', () => {
  const snap = ganttSnapshot({ runs: [{ stage: 'design', seq: 1, durationSec: 10 }] });
  const text = `${stageLog({ seq: 1, stage: 'design', at: atSec(5) }).text}${stageLog({ seq: 1, stage: 'design', at: atSec(50) }).text}`;
  snap.stageLogs = [{ fileName: '01_design.jsonl', text }];
  const row = model(snap).rows[0]!;
  near(row.run!.startSec, 50);
  near(row.run!.endSec, 60);
});

test('D0019-AC-69: 動いている段は「今」まで伸び、live の印が付く。今を進めて作り直すと、帯の終わりが伸びる', () => {
  const snap = ganttSnapshot({
    runs: [{ stage: 'requirements', seq: 1, start: 5, durationSec: 30 }],
    extras: [{ after: 1, entry: review('requirements', 'approved') }],
    running: { seq: 2, stage: 'design', start: atSec(60) },
  });
  const early = model(snap, 100);
  const later = model(snap, 200);
  const a = early.rows[1]!.run!;
  const b = later.rows[1]!.run!;
  assert.equal(a.live, true);
  near(a.startSec, 60);
  near(a.endSec, 100);
  near(b.endSec, 200);
  near(later.totalSec, 200);
  assert.equal(early.live, true);
  assert.equal(later.live, true);
  assertBounds(early);
  assertBounds(later);
  assert.equal(early.rows[0]!.run!.live, false, '終わった段の帯は伸びない');
  near(later.rows[0]!.run!.endSec, 35);
});

// ---- AC-70：確認の待ち ----

test('D0019-AC-70: 確認の待ちの帯は、段の実行の終わりから 次の実行の始まりまで（修正の依頼・承認のどちらも）', () => {
  const g = model(finishedGantt());
  const waits = g.rows.map((r) => (r.wait === null ? null : [r.wait.startSec, r.wait.endSec, r.wait.live]));
  assert.deepEqual(waits[0], [35, 60, false]);
  assert.deepEqual(waits[1], [80, 90, false]);
  assert.deepEqual(waits[2], [130, 140, false]);
  assertBounds(g);
});

test('D0019-AC-70: 確認を取らない段・--yes の run（確認の結果が記録に無い）には、待ちの帯が無い', () => {
  const g = model(finishedGantt());
  for (const r of g.rows.slice(3)) assert.equal(r.wait, null, `seq ${r.seq}`);
  const yes = model(ganttSnapshot({ runs: [{ stage: 'requirements', seq: 1, start: 5, durationSec: 10 }, { stage: 'design', seq: 2, start: 30, durationSec: 10 }], final: 'PASSED' }));
  assert.deepEqual(yes.rows.map((r) => r.wait), [null, null]);
});

test('D0019-AC-70: 最後の確認（次の実行が無い）の待ちの帯は、updated_at までの近似', () => {
  const g = model(
    ganttSnapshot({
      runs: [{ stage: 'requirements', seq: 1, start: 5, durationSec: 30 }],
      extras: [{ after: 1, entry: review('requirements', 'quit') }],
      final: 'STOPPED_BY_HUMAN',
      updatedAt: naiveAtSec(60),
    }),
  );
  const wait = g.rows[0]!.wait!;
  near(wait.startSec, 35);
  near(wait.endSec, 60);
  assert.equal(wait.live, false);
  assert.equal(g.live, false);
  near(g.totalSec, 60, '終わった run でも、最後の帯（待ち）の終わりまでが横軸');
  assertBounds(g);
});

test('D0019-AC-70: いま確認待ちのときは、待ちの帯が 待ち始め（pending_review.since）から「今」まで伸び、live の印が付く', () => {
  const snap = ganttSnapshot({
    runs: [{ stage: 'requirements', seq: 1, start: 5, durationSec: 30 }],
    pendingReview: { stage: 'requirements', doc: 'docs/pipeline/01_requirements.md', session_id: 's', since: atSec(40) },
  });
  const g = model(snap, 100);
  const wait = g.rows[0]!.wait!;
  near(wait.startSec, 40);
  near(wait.endSec, 100);
  assert.equal(wait.live, true);
  assert.equal(g.live, true);
  near(g.totalSec, 100);
  near(model(snap, 160).rows[0]!.wait!.endSec, 160, '今を進めると伸びる');
  assertBounds(g);
});

for (const [label, since] of [['since が無い', undefined], ['since が読めない', 'いつか'], ['since が数', 5]] as const) {
  test(`D0019-AC-70: いま確認待ちで ${label}ときは、待ちの帯の始まりが段の実行の終わりになる（「今」までは伸びる）`, () => {
    const snap = ganttSnapshot({
      runs: [{ stage: 'requirements', seq: 1, start: 5, durationSec: 30 }],
      pendingReview: { stage: 'requirements', doc: 'a.md', session_id: 's', ...(since === undefined ? {} : { since }) },
    });
    const wait = model(snap, 100).rows[0]!.wait!;
    near(wait.startSec, 35);
    near(wait.endSec, 100);
    assert.equal(wait.live, true);
  });
}

test('D0019-AC-70: 動いている段があるあいだは、確認待ちの印が古いので、いま待っている帯（live の待ち）を作らない', () => {
  const snap = ganttSnapshot({
    runs: [{ stage: 'requirements', seq: 1, start: 5, durationSec: 30 }],
    extras: [{ after: 1, entry: review('requirements', 'revise') }],
    running: { seq: 2, stage: 'requirements', start: atSec(60) },
    pendingReview: { stage: 'requirements', doc: 'a.md', session_id: 's', since: atSec(40) },
  });
  const g = model(snap, 100);
  assert.ok(g.rows.every((r) => r.wait === null || r.wait.live === false));
  const first = g.rows[0]!.wait!;
  near(first.startSec, 35);
  near(first.endSec, 60);
});

// ---- AC-71：赤（不合格・失敗）----

test('D0019-AC-71: 検証が不合格（verdict の fail）の回の帯だけ failed。合格の回・実装の帯は failed でない', () => {
  const g = model(finishedGantt());
  assert.deepEqual(g.rows.map((r) => r.run?.failed ?? null), [false, false, false, false, false, true, false, false]);
});

test('D0019-AC-71: 段の実行が失敗（is_error）した帯は failed', () => {
  const g = model(ganttSnapshot({ runs: [{ stage: 'design', seq: 1, start: 5, durationSec: 10, isError: true }, { stage: 'design', seq: 2, start: 30, durationSec: 10 }] }));
  assert.deepEqual(g.rows.map((r) => r.run?.failed), [true, false]);
});

test('D0019-AC-71: 判定が「実行できず」（blocked）の回も failed。判定は同じ回（attempt）の検証にだけ当たる', () => {
  const blocked = { stage: 'test', attempt: 2, verdict: { status: 'blocked', summary: '環境', failures: [], commands: [], command_check: null } };
  const g = model(
    ganttSnapshot({
      runs: [
        { stage: 'test', seq: 1, attempt: 1, start: 5, durationSec: 10 },
        { stage: 'test', seq: 2, attempt: 2, start: 30, durationSec: 10 },
      ],
      extras: [{ after: 2, entry: blocked }],
    }),
  );
  assert.deepEqual(g.rows.map((r) => r.run?.failed), [false, true]);
  const failOne = model(
    ganttSnapshot({
      runs: [
        { stage: 'test', seq: 1, attempt: 1, start: 5, durationSec: 10 },
        { stage: 'test', seq: 2, attempt: 2, start: 30, durationSec: 10 },
      ],
      extras: [{ after: 1, entry: failVerdict({ attempt: 1, summary: 'x', failures: [] }) }],
    }),
  );
  assert.deepEqual(failOne.rows.map((r) => r.run?.failed), [true, false]);
});

// ---- AC-72：横軸 ----

test('D0019-AC-72: 横軸の 0 は started_at。終わった run の全体の長さは最後の帯の終わり。目盛りは 6 本以下で、等しい間隔の秒', () => {
  const g = model(finishedGantt());
  near(g.totalSec, 305);
  const positive = g.ticks.filter((t) => t > 0);
  assert.deepEqual(positive, [60, 120, 180, 240, 300]);
  assert.ok(g.ticks.length <= 6);
  for (const t of g.ticks) assert.ok(t >= 0 && t <= g.totalSec);
  assert.equal(g.hasTimes, true);
  assert.equal(g.live, false);
});

test('D0019-AC-72: 目盛りの間隔は 5・10・15・30・60・120・300・600・900・1800・3600 秒… の中から、6 本以下になる最小のもの', () => {
  const longRun = (end: number) => ganttSnapshot({ runs: [{ stage: 'design', seq: 1, start: 0, durationSec: end }] });
  const spacing = (end: number): number => {
    const t = model(longRun(end)).ticks.filter((x) => x > 0);
    return t.length >= 2 ? t[1]! - t[0]! : (t[0] ?? 0);
  };
  assert.equal(spacing(25), 5);
  assert.equal(spacing(55), 10);
  assert.equal(spacing(80), 15);
  assert.equal(spacing(300), 60);
  assert.equal(spacing(700), 120);
  assert.equal(spacing(1500), 300);
  assert.equal(spacing(3000), 600);
  assert.equal(spacing(7000), 1800);
});

test('D0019-AC-72: ずれつきの時刻とずれなしの時刻が混ざっても、同じ瞬間なら同じ位置になる（手元のずれを使う）', () => {
  // 手元は UTC+9：ずれなしの started_at '19:00:00' は 10:00:00 UTC。段の at は 10:00:05Z と 19:00:05+09:00 の同じ瞬間
  const withZ = ganttSnapshot({ runs: [{ stage: 'design', seq: 1, durationSec: 10 }], startedAt: '2026-10-17T19:00:00' });
  withZ.stageLogs = [{ fileName: '01_design.jsonl', text: stageLog({ seq: 1, stage: 'design', at: '2026-10-17T10:00:05Z' }).text }];
  const withOffset = ganttSnapshot({ runs: [{ stage: 'design', seq: 1, durationSec: 10 }], startedAt: '2026-10-17T19:00:00' });
  withOffset.stageLogs = [{ fileName: '01_design.jsonl', text: stageLog({ seq: 1, stage: 'design', at: '2026-10-17T19:00:05+09:00' }).text }];
  const withNaive = ganttSnapshot({ runs: [{ stage: 'design', seq: 1, durationSec: 10 }], startedAt: '2026-10-17T19:00:00' });
  withNaive.stageLogs = [{ fileName: '01_design.jsonl', text: stageLog({ seq: 1, stage: 'design', at: '2026-10-17T19:00:05' }).text }];
  for (const snap of [withZ, withOffset, withNaive]) {
    const row = model(snap, 400, 540).rows[0]!;
    near(row.run!.startSec, 5);
    near(row.run!.endSec, 15);
  }
});

test('D0019-AC-72: 同じ入力は同じ結果（今の時刻を引数で受ける純粋な関数）。入力の記録の写しを書き換えない', () => {
  const snap = finishedGantt();
  const before = JSON.stringify(snap);
  const a = buildPipelineView(snap, clockAt(400)).gantt;
  const b = buildPipelineView(snap, clockAt(400)).gantt;
  assert.equal(a.rows.length, 8, '組み立てられている');
  assert.deepEqual(a, b);
  assert.equal(JSON.stringify(snap), before);
});

test('D0019-AC-72: started_at が無い・読めない記録では、読めた最初の始まりを横軸の 0 にする', () => {
  for (const startedAt of [null, 'いつか', 12345]) {
    const g = model(
      ganttSnapshot({
        startedAt,
        runs: [
          { stage: 'requirements', seq: 1, start: 100, durationSec: 20 },
          { stage: 'design', seq: 2, start: 150, durationSec: 20 },
        ],
      }),
    );
    near(g.rows[0]!.run!.startSec, 0, `${String(startedAt)}: 最初の帯の始まり`);
    near(g.rows[1]!.run!.startSec, 50);
    near(g.totalSec, 70);
    assertBounds(g);
  }
});

test('D0019-AC-72: started_at より前に始まった段（時計のずれ）でも、帯は 0 から始まり、負にならない', () => {
  const g = model(ganttSnapshot({ startedAt: naiveAtSec(30), runs: [{ stage: 'requirements', seq: 1, start: 5, durationSec: 20 }, { stage: 'design', seq: 2, start: 60, durationSec: 10 }] }));
  assertBounds(g);
  assert.ok(g.rows[0]!.run!.startSec >= 0);
});

// ---- AC-73：時刻が読めない ----

const UNREADABLE_AT: [string, unknown][] = [
  ['Prompt に at が無い（D0017 より前の記録）', undefined],
  ['at が壊れた文字', 'x'],
  ['at が数', 1792230000],
  ['at が null', null],
  ['at が存在しない日付', '2026-02-30T10:00:00'],
  ['at が「今」より 60 秒を超えて先', 'FUTURE'],
];

for (const [label, at] of UNREADABLE_AT) {
  test(`D0019-AC-73: ${label}段は、行は出て帯が出ない（run が null）。ほかの段の帯は出る`, () => {
    const value = at === 'FUTURE' ? atSec(400 + 61) : at;
    const snap = ganttSnapshot({ runs: [{ stage: 'requirements', seq: 1, start: 5, durationSec: 20 }, { stage: 'design', seq: 2, durationSec: 20 }] });
    snap.stageLogs = [
      stageLog({ seq: 1, stage: 'requirements', at: atSec(5) }),
      stageLog({ seq: 2, stage: 'design', at: value }),
    ];
    const g = model(snap, 400);
    assert.equal(g.rows.length, 2);
    assert.equal(g.rows[1]!.run, null);
    assert.equal(g.rows[1]!.wait, null);
    assert.ok(bar(g.rows[0]) !== null);
    assert.equal(g.hasTimes, true);
    assertBounds(g);
  });
}

test('D0019-AC-73: 時刻が一つも取れない記録では hasTimes が偽で、行は残り、帯が無い', () => {
  const g = model(ganttSnapshot({ runs: [{ stage: 'requirements', seq: 1, durationSec: 20 }, { stage: 'design', seq: 2, durationSec: 20 }] }));
  assert.equal(g.hasTimes, false);
  assert.equal(g.rows.length, 2);
  assert.ok(g.rows.every((r) => r.run === null && r.wait === null));
  assert.deepEqual(g.ticks, []);
});

for (const [label, value] of [['負', -5], ['巨大', 1e12], ['文字', 'x'], ['null', null], ['小さな負の小数', -0.5]] as const) {
  test(`D0019-AC-73: duration_sec が${label}でも例外を投げず、帯が負の幅・欄の外にならない`, () => {
    const snap = ganttSnapshot({ runs: [{ stage: 'design', seq: 1, start: 5, durationSec: 10 }, { stage: 'implement', seq: 2, attempt: 1, start: 30, durationSec: 10 }] });
    snap.stateJson = stateJson({
      startedAt: GANTT_STARTED_AT,
      updatedAt: naiveAtSec(60),
      runs: [stageRunEntry({ stage: 'design', seq: 1, rawDurationSec: value }), stageRunEntry({ stage: 'implement', seq: 2, attempt: 1, durationSec: 10 })],
    });
    const g = model(snap, 400);
    assert.equal(g.rows.length, 2);
    assertBounds(g);
    for (const r of g.rows) if (r.run) assert.ok(r.run.endSec - r.run.startSec <= 7 * 24 * 3600 + 0.001, '長さは 7 日まで');
  });
}

test('D0019-AC-73: 壊れた記録（JSON が壊れている・runs が配列でない）でも例外を投げず、行が無い', () => {
  for (const text of ['{壊れた', '[1,2]', JSON.stringify({ runs: 5 }), JSON.stringify({ runs: [1, 'a', null] })]) {
    const g = model(snapshot({ stateJson: text }));
    assert.deepEqual(g.rows, []);
    assert.equal(g.hasTimes, false);
  }
});

// ---- AC-74：行の上限 ----

const manyRuns = (n: number): WorkDirSnapshot =>
  snapshot({
    stateJson: stateJson({ startedAt: GANTT_STARTED_AT, runs: Array.from({ length: n }, (_, i) => stageRunEntry({ stage: 'requirements', seq: i + 1, durationSec: 1 })) }),
  });

test('D0019-AC-74: 行は 200 まで。ちょうど 200 なら省かない', () => {
  const g = model(manyRuns(200));
  assert.equal(g.rows.length, 200);
  assert.equal(g.omittedRows, 0);
  assert.equal(g.rows[0]!.seq, 1);
});

test('D0019-AC-74: 201 行以上は、新しい方の 200 行を残し、古い方の数を omittedRows に入れる', () => {
  const g = model(manyRuns(201));
  assert.equal(g.rows.length, 200);
  assert.equal(g.omittedRows, 1);
  assert.equal(g.rows[0]!.seq, 2);
  assert.equal(g.rows.at(-1)!.seq, 201);
  const big = model(manyRuns(450));
  assert.equal(big.rows.length, 200);
  assert.equal(big.omittedRows, 250);
  assert.deepEqual([big.rows[0]!.seq, big.rows.at(-1)!.seq], [251, 450]);
  assertBounds(big);
});

test('D0019-AC-74: 段の表示名・受け持ちに入った文字は、モデルではそのまま持つ（エスケープは描く側の ganttHtml）。空白を含む受け持ちは null', () => {
  const evil = '<script>alert(1)</script>';
  const snap = ganttSnapshot({
    pipe: 'p',
    stages: [{ name: 'draw', label: evil, output: 'a.md', review: false }],
    runs: [{ stage: 'draw', seq: 1, start: 5, durationSec: 5, agent: '<b>x</b>' }, { stage: 'draw', seq: 2, start: 20, durationSec: 5, agent: 'a b' }],
  });
  const rows = model(snap).rows;
  assert.equal(rows[0]!.label, evil);
  assert.equal(rows[0]!.agent, '<b>x</b>', '空白も制御文字も無い文字は受け持ちとして読む（エスケープは描く側）');
  assert.equal(rows[1]!.agent, null, '空白を含む受け持ちは読み捨てる');
});
