// 実行の一覧の行（D0019）：記録から1行を組み立てる・状態・並び・省く件数・覚えた値の検め。純粋な関数だけを確かめる。
// 新しい部品（domain/runList.ts）は、呼んだところで落ちるように、テストの中で読み込む。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPipelineView } from './pipelineView.ts';
import { statusBarLabel } from '../view/statusBar.ts';
import {
  DIAGRAMS_STAGES,
  logText,
  promptLine,
  resultLine,
  snapshot,
  stageRunEntry,
  stateJson,
} from '../test/fixtures.ts';
import {
  BASE_AT,
  FINISHED_UPDATED_AT,
  RUNNING_UPDATED_AT,
  STARTED_AT,
  clockAt,
  finishedSnapshot,
  fixtureSnapshot,
  loopSnapshot,
  runningSnapshot,
  waitingSnapshot,
} from '../test/liveFixtures.ts';
import type { RunRow } from './runList.ts';
import { row, sampleRows } from '../test/runListFixtures.ts';

const rl = () => import('./runList.ts');

// 2版目（D0019）：入力に branch（ブランチ名か短い ID。git の外は null）・other（別の worktree）・memoHead（00_input.md の先頭。無ければ null）が増えた。
// 行の name は pipe（パイプ名／開発フロー）と session（セッション名）に分かれ、place は branch と other に分かれた。
interface SumInput {
  stateJson: string | null;
  stageLogs?: { fileName: string; text: string }[];
  key?: string;
  id?: string;
  branch?: string | null;
  other?: boolean;
  memoHead?: string | null;
  previous?: boolean;
}

/** 1行にする。既定は「いまの work_dir の直下」で、今は BASE から sec 秒後。 */
async function summarize(p: SumInput, sec = 0): Promise<RunRow> {
  const { summarizeRun } = await rl();
  return summarizeRun(
    { key: 'here|', id: '', branch: null, other: false, memoHead: null, previous: false, stageLogs: [], ...p },
    clockAt(sec),
  );
}
const fromSnapshot = (s: { stateJson: string | null; stageLogs: { fileName: string; text: string }[] }, sec = 0, rest: Partial<SumInput> = {}) =>
  summarize({ stateJson: s.stateJson, stageLogs: s.stageLogs, ...rest }, sec);

const REQ = stageRunEntry({ stage: 'requirements', seq: 1 });
const DESIGN = stageRunEntry({ stage: 'design', seq: 2 });

// ---- AC-03：1行の項目 ----

test('D0019-AC-03: 1行に セッション名・パイプ名・ブランチ・状態・今の段・費用・最後に動いた日付・セッション ID が入る（動いている開発フロー）', async () => {
  const r = await summarize(
    { ...runningSnapshot(), branch: 'main', stateJson: stateJson({ name: '仕様の QA を回す', sessionId: 'aaaa1111-0000-4000-8000-0123456789a1', runs: [stageRunEntry({ stage: 'requirements', seq: 1, durationSec: 30 })], startedAt: STARTED_AT, updatedAt: RUNNING_UPDATED_AT }) },
    83,
  );
  assert.equal(r.key, 'here|');
  assert.equal(r.session, '仕様の QA を回す');
  assert.equal(r.pipe, '開発フロー');
  assert.equal(r.branch, 'main');
  assert.equal(r.other, false);
  assert.equal(r.stage, '設計');
  assert.equal(r.state, 'running');
  assert.equal(r.costText, '$0.000');
  assert.equal(r.updatedText, '10/17 10:00');
  assert.equal(r.updatedDate, '10/17');
  assert.equal(r.updatedMs, Date.UTC(2026, 9, 17, 10, 0, 30));
  assert.equal(r.sessionId, 'aaaa1111-0000-4000-8000-0123456789a1', '行の項目は ID の全部（先頭 8 文字にするのは描く側）');
  assert.equal(r.previous, false);
});

test('D0019-AC-03: パイプ名は記録の pipe。開発フローは「開発フロー」。別の worktree の行は other が真で、ブランチ名が branch に入る', async () => {
  const pipe = await summarize({
    key: 'wt.feat-x|diagrams',
    id: 'diagrams',
    branch: 'feat/x',
    other: true,
    stateJson: stateJson({ pipe: 'diagrams', stages: DIAGRAMS_STAGES, runs: [stageRunEntry({ stage: 'survey', seq: 1 })] }),
  });
  assert.equal(pipe.key, 'wt.feat-x|diagrams');
  assert.equal(pipe.pipe, 'diagrams');
  assert.equal(pipe.branch, 'feat/x');
  assert.equal(pipe.other, true);
  assert.equal(pipe.stage, 'ソースの調査');
  const dev = await summarize({ stateJson: stateJson({ pipe: 'dev', runs: [REQ] }) });
  assert.equal(dev.pipe, '開発フロー');
  assert.equal(dev.branch, null, 'git の外では、ブランチ名を出さない（項目ごと省く）');
  assert.equal(dev.other, false);
});

test('D0019-AC-03: ブランチ名はいまの work_dir の行にも入る（別の worktree かどうかは other で分ける）', async () => {
  const here = await summarize({ branch: 'feat/run-list', stateJson: stateJson({ runs: [REQ] }) });
  assert.equal(here.branch, 'feat/run-list');
  assert.equal(here.other, false);
});

test('D0019-AC-03: 費用は図のバナーと同じ $0.000 の形（小数 3 桁）。時刻は記録の壁時計の MM/DD HH:mm、日付は MM/DD', async () => {
  const r = await summarize({ stateJson: stateJson({ totalCostUsd: 1.23456, runs: [REQ], updatedAt: '2026-10-17T09:05:00+09:00' }) });
  assert.equal(r.costText, '$1.235');
  assert.equal(r.updatedText, '10/17 09:05', 'オフセットつきでも、記録に書かれた壁時計の時刻のまま');
  assert.equal(r.updatedDate, '10/17');
  assert.equal(r.updatedMs, Date.UTC(2026, 9, 17, 0, 5, 0), '並びに使うミリ秒はオフセットを引いた UTC');
});

// ---- AC-52：セッション名 ----

test('D0019-AC-52: セッション名は state.json の name が先。00_input.md の先頭（memoHead）があっても name を使う', async () => {
  const r = await summarize({ memoHead: '# 別の題\n本文', stateJson: stateJson({ name: '付けた名前', runs: [REQ] }) });
  assert.equal(r.session, '付けた名前');
});

test('D0019-AC-52: name が無ければ 00_input.md の最初の行（見出しの印を取り、規則は本体と同じ）から作る', async () => {
  const r = await summarize({ memoHead: '\n\n## 仕様の QA を回す\n2行目は使わない', stateJson: stateJson({ runs: [REQ] }) });
  assert.equal(r.session, '仕様の QA を回す');
  const long = await summarize({ memoHead: 'あ'.repeat(61), stateJson: stateJson({ runs: [REQ] }) });
  assert.equal(long.session, `${'あ'.repeat(59)}…`);
});

test('D0019-AC-52: name も memoHead も無い（読めない・名前が取れない）ときは、今までの呼び名（パイプ名／「開発フロー」）。例外を出さない', async () => {
  const dev = await summarize({ stateJson: stateJson({ runs: [REQ] }) });
  assert.equal(dev.session, '開発フロー');
  const pipe = await summarize({ id: 'diagrams', key: 'here|diagrams', stateJson: stateJson({ pipe: 'diagrams', stages: DIAGRAMS_STAGES, runs: [] }) });
  assert.equal(pipe.session, 'diagrams');
  for (const memoHead of ['', '   \n', '###', null]) {
    const r = await summarize({ memoHead, stateJson: stateJson({ runs: [REQ] }) });
    assert.equal(r.session, '開発フロー', JSON.stringify(memoHead));
  }
  const broken = await summarize({ id: 'spec-qa', key: 'here|spec-qa', memoHead: null, stateJson: '{壊れた' });
  assert.equal(broken.session, 'spec-qa');
});

test('D0019-AC-52: name が読めない形（空・数・長すぎる）の記録は、00_input.md の先頭から作る', async () => {
  for (const name of ['', 5, 'あ'.repeat(201)]) {
    const r = await summarize({ memoHead: '# 題から', stateJson: stateJson({ name, runs: [REQ] }) });
    assert.equal(r.session, '題から', JSON.stringify(name).slice(0, 20));
  }
});

test('D0019-AC-52: archive の行（previous）も、同じ順でセッション名が決まる', async () => {
  const r = await summarize({ previous: true, id: 'archive/20261016-090000', key: 'here|archive/20261016-090000', memoHead: '# 前の題', stateJson: stateJson({ final: 'PASSED', runs: [REQ] }) });
  assert.equal(r.session, '前の題');
  assert.equal(r.previous, true);
});

// ---- AC-53：セッション ID ----

test('D0019-AC-53: セッション ID は state.json の session_id が先。無ければ 通し番号が最大の段の session_id。無ければ null', async () => {
  const pipeRuns = [
    stageRunEntry({ stage: 'survey', seq: 1, sessionId: 'sess-a' }),
    stageRunEntry({ stage: 'verify', seq: 3, sessionId: 'sess-c' }),
    stageRunEntry({ stage: 'draw', seq: 2, sessionId: 'sess-b' }),
  ];
  const base = { pipe: 'diagrams', stages: DIAGRAMS_STAGES, runs: pipeRuns };
  assert.equal((await summarize({ stateJson: stateJson({ ...base, sessionId: 'rec-1' }) })).sessionId, 'rec-1');
  assert.equal((await summarize({ stateJson: stateJson(base) })).sessionId, 'sess-c', 'パイプの記録は runs[] の seq が最大の段から出る');
  assert.equal((await summarize({ stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1, sessionId: null })] }) })).sessionId, null, '開発フローの record done は session_id が null');
  assert.equal((await summarize({ stateJson: stateJson({ runs: [] }) })).sessionId, null);
  assert.equal((await summarize({ stateJson: '{壊れた' })).sessionId, null);
});

// ---- AC-66：経過 ----

test('D0019-AC-66: 動いている行は経過が live で、始まり（started_at）から「今」までの秒', async () => {
  const r = await fromSnapshot(runningSnapshot(), 83);
  assert.deepEqual(r.elapsed, { seconds: 203, live: true });
  const later = await fromSnapshot(runningSnapshot(), 100);
  assert.deepEqual(later.elapsed, { seconds: 220, live: true }, '今を進めると増える');
});

test('D0019-AC-66: 終わった行の経過は、始まりから updated_at までの固定の秒（live でない）。「今」を進めても変わらない', async () => {
  const r = await fromSnapshot(finishedSnapshot(), 83);
  assert.deepEqual(r.elapsed, { seconds: 420, live: false });
  assert.deepEqual((await fromSnapshot(finishedSnapshot(), 9999)).elapsed, { seconds: 420, live: false });
  const old = await summarize({ previous: true, id: 'archive/20261016-090000', key: 'here|archive/20261016-090000', stateJson: stateJson({ final: 'PASSED', runs: [REQ], startedAt: '2026-10-16T09:00:00', updatedAt: '2026-10-16T09:10:00' }) }, 5);
  assert.deepEqual(old.elapsed, { seconds: 600, live: false });
});

test('D0019-AC-66: started_at が読めない・無いときは経過を出さない（elapsed が null）。例外を出さない', async () => {
  for (const startedAt of [null, 'いつか', 12345]) {
    const r = await fromSnapshot(runningSnapshot({ startedAt }), 83);
    assert.equal(r.elapsed, null, String(startedAt));
    assert.equal(r.state, 'running');
  }
  assert.equal((await summarize({ stateJson: '{壊れた' })).elapsed, null);
  assert.equal((await summarize({ stateJson: null })).elapsed, null);
});

test('D0019-AC-66: 終わった行で updated_at が読めないときは、経過を出さない（null）', async () => {
  const r = await summarize({ stateJson: stateJson({ final: 'PASSED', runs: [REQ], startedAt: '2026-10-16T09:00:00', updatedAt: 'いつか' }) });
  assert.equal(r.elapsed, null);
});

// ---- 状態の言葉・件数（AC-56・AC-59）----

test('D0019-AC-56: stateWord は 確認待ち／動いている／待ち、終わった行は結果の言葉（結果が無ければ「終わった」）', async () => {
  const { stateWord } = await rl();
  assert.equal(stateWord(row({ state: 'waiting' })), '確認待ち');
  assert.equal(stateWord(row({ state: 'running' })), '動いている');
  assert.equal(stateWord(row({ state: 'idle' })), '待ち');
  assert.equal(stateWord(row({ state: 'done', result: '合格' })), '合格');
  assert.equal(stateWord(row({ state: 'done', result: '不合格' })), '不合格');
  assert.equal(stateWord(row({ state: 'done', result: 'SOMETHING_NEW' })), 'SOMETHING_NEW', '知らない結果の文字はそのまま');
  assert.equal(stateWord(row({ state: 'done', result: null })), '終わった');
});

test('D0019-AC-59: countStates は すべて・確認待ち・動いている・終わった の件数。待ち（idle）は動いているに数える', async () => {
  const { countStates } = await rl();
  const rows = sampleRows();
  assert.deepEqual(countStates(rows), { all: 8, waiting: 2, running: 3, done: 3 });
  assert.deepEqual(countStates([]), { all: 0, waiting: 0, running: 0, done: 0 });
  assert.deepEqual(countStates([row({ state: 'idle' })]), { all: 1, waiting: 0, running: 1, done: 0 });
});

test('D0019-AC-03: formatStamp は記録の時刻の文字を MM/DD HH:mm にし、読めない文字は「—」', async () => {
  const { formatStamp } = await rl();
  assert.equal(formatStamp('2026-10-17T10:05:00'), '10/17 10:05');
  assert.equal(formatStamp('2026-01-02 03:04:05'), '01/02 03:04');
  assert.equal(formatStamp('2026-10-17T10:00:30+00:00'), '10/17 10:00');
  assert.equal(formatStamp('2026-10-17T10:00:30.123Z'), '10/17 10:00');
  for (const bad of ['', 'まだ', '2026-02-30T10:00:00', '2026-13-01T10:00:00', '10:05']) assert.equal(formatStamp(bad), '—', bad);
});

// ---- AC-04：終わった ----

const FINALS: [string, string][] = [
  ['PASSED', '合格'],
  ['TEST_FAILED', '不合格'],
  ['STOPPED_BY_HUMAN', '中止'],
  ['STAGE_ERROR', '段が失敗'],
  ['BLOCKED', '実行できず'],
];

for (const [final, word] of FINALS) {
  test(`D0019-AC-04: final=${final} の run は「終わった」で、結果が「${word}」と言葉で付く`, async () => {
    const r = await summarize({ stateJson: stateJson({ final, runs: [REQ, DESIGN] }) });
    assert.equal(r.state, 'done');
    assert.equal(r.result, word);
    assert.equal(r.stage, '設計', '終わった run の今の段は、通し番号が最大の段');
  });
}

test('D0019-AC-04: 知らない結果の文字は、そのまま出す', async () => {
  const r = await summarize({ stateJson: stateJson({ final: 'SOMETHING_NEW', runs: [REQ] }) });
  assert.equal(r.state, 'done');
  assert.equal(r.result, 'SOMETHING_NEW');
});

test('D0019-AC-04: 結果の言葉の表（FINAL_WORDS・finalWord）。知らない文字はそのまま', async () => {
  const { FINAL_WORDS, finalWord } = await rl();
  assert.deepEqual(Object.fromEntries(Object.entries(FINAL_WORDS)), Object.fromEntries(FINALS));
  for (const [final, word] of FINALS) assert.equal(finalWord(final), word);
  assert.equal(finalWord('X'), 'X');
});

test('D0019-AC-04: 終わった以外の run は result が null', async () => {
  for (const s of [runningSnapshot(), waitingSnapshot()]) assert.equal((await fromSnapshot(s)).result, null);
});

// ---- AC-05・AC-06：確認待ち・動いている・待ち ----

test('D0019-AC-05: pending_review のある run は「確認待ち」で、今の段に確認の対象の段が出る', async () => {
  const r = await fromSnapshot(waitingSnapshot(), 40);
  assert.equal(r.state, 'waiting');
  assert.equal(r.stage, '要件定義');
  assert.equal(r.result, null);
});

test('D0019-AC-05: パイプの確認待ちは、その段の label が今の段に出る', async () => {
  const r = await summarize({
    id: 'diagrams',
    key: 'here|diagrams',
    stateJson: stateJson({
      pipe: 'diagrams',
      stages: DIAGRAMS_STAGES,
      runs: [stageRunEntry({ stage: 'survey', seq: 1 }), stageRunEntry({ stage: 'draw', seq: 2 })],
      pendingReview: { stage: 'draw', doc: 'docs/pipeline/diagrams/02_diagrams.md', session_id: 's' },
    }),
  });
  assert.equal(r.state, 'waiting');
  assert.equal(r.stage, '図を描く');
});

test('D0019-AC-06: 段のログに結果の行がない run（final なし・確認待ちなし）は「動いている」で、今の段にそのログの段が出る', async () => {
  const r = await fromSnapshot(runningSnapshot(), 83);
  assert.equal(r.state, 'running');
  assert.equal(r.stage, '設計');
  assert.equal(r.result, null);
});

test('D0019-AC-06: 結果の行があるログだけなら動いていない。動いている段の回（attempt）は「（2 回目）」と付く', async () => {
  const finishedLog = [{ fileName: '01_requirements.jsonl', text: logText([promptLine('requirements'), resultLine()]) }];
  const idle = await summarize({ stateJson: stateJson({ runs: [REQ] }), stageLogs: finishedLog });
  assert.equal(idle.state, 'idle');
  const again = await fromSnapshot(loopSnapshot({ sendBack: 1, running: true }));
  assert.equal(again.state, 'running');
  assert.equal(again.stage, '検証（2 回目）');
});

test('D0019-AC-06: final・確認待ち・動いているログのどれも無い run は「待ち」（idle）。今の段は通し番号が最大の段', async () => {
  const r = await summarize({ stateJson: stateJson({ runs: [REQ, DESIGN] }) });
  assert.equal(r.state, 'idle');
  assert.equal(r.stage, '設計');
  assert.equal(r.result, null);
});

// ---- AC-07：図の帯・ステータスバーと食い違わない ----

const NONE = { stateJson: null as string | null, stageLogs: [] as { fileName: string; text: string }[] };
const RUNNING_LOG = { fileName: '02_design.jsonl', text: logText([promptLine('design', BASE_AT)]) };
const SAME_RECORDS: [string, { stateJson: string | null; stageLogs: { fileName: string; text: string }[] }][] = [
  ['見本 showcase（合格）', fixtureSnapshot('showcase')],
  ['見本 showcase_running（動いている）', fixtureSnapshot('showcase_running')],
  ['見本 showcase_running_next（動いている・差し戻し 1 回）', fixtureSnapshot('showcase_running_next')],
  ['見本 showcase_waiting（確認待ち）', fixtureSnapshot('showcase_waiting')],
  ['前の版の見本 pipe_in/waiting', fixtureSnapshot('pipe_in', 'waiting')],
  ['前の版の見本 pipe_in/finished', fixtureSnapshot('pipe_in', 'finished')],
  ['前の版の見本 pipe_in/running', fixtureSnapshot('pipe_in', 'running')],
  ['今の見本 pipe_dev/waiting', fixtureSnapshot('pipe_dev', 'waiting')],
  ['今の見本 pipe_dev/finished', fixtureSnapshot('pipe_dev', 'finished')],
  ['今の見本 pipe_dev/running', fixtureSnapshot('pipe_dev', 'running')],
  ['パイプを持つ前の記録（stages なし・待ち）', { stateJson: stateJson({ runs: [REQ, DESIGN] }), stageLogs: [] }],
  ['パイプを持つ前の記録（stages なし・確認待ち）', { stateJson: stateJson({ runs: [REQ], pendingReview: { stage: 'requirements', doc: 'a.md', session_id: 's' } }), stageLogs: [] }],
  ['final があり、動いているログもある（final が先）', { stateJson: stateJson({ final: 'STOPPED_BY_HUMAN', runs: [REQ] }), stageLogs: [RUNNING_LOG] }],
  ['確認待ちで、動いているログもある（動いているが先）', { stateJson: stateJson({ runs: [REQ], pendingReview: { stage: 'requirements', doc: 'a.md', session_id: 's' } }), stageLogs: [RUNNING_LOG] }],
  ['記録なし', NONE],
  ['壊れた JSON', { stateJson: '{壊れた', stageLogs: [] }],
];

for (const [label, rec] of SAME_RECORDS) {
  test(`D0019-AC-07: 同じ記録を図とステータスバー・1 行に通しても、状態・今の段・結果が食い違わない：${label}`, async () => {
    const clock = clockAt(40);
    const view = buildPipelineView(snapshot({ stateJson: rec.stateJson, stageLogs: rec.stageLogs }), clock);
    const bar = statusBarLabel(view);
    const { summarizeRun } = await rl();
    const r = summarizeRun({ key: 'here|', id: '', branch: null, other: false, memoHead: null, previous: false, stateJson: rec.stateJson, stageLogs: rec.stageLogs }, clock);

    const expected = view.final !== null
      ? 'done'
      : bar.text.startsWith('$(sync~spin)')
        ? 'running'
        : bar.text.startsWith('$(comment-discussion)')
          ? 'waiting'
          : 'idle';
    assert.equal(r.state, expected, bar.text);
    if (r.state === 'running' || r.state === 'waiting') {
      assert.ok(bar.text.includes(r.stage), `ステータスバー「${bar.text}」に 今の段「${r.stage}」がある`);
    }
    if (r.state === 'done') {
      assert.ok(r.result !== null && bar.text.endsWith(`: ${r.result}`), `ステータスバー「${bar.text}」の結果の言葉と同じ`);
    }
  });
}

// ---- AC-08：archive の run ----

test('D0019-AC-08: archive の run は「終わった」で、前の実行の印（previous）が付く', async () => {
  const r = await summarize({
    key: 'here|archive/20261016-090000',
    id: 'archive/20261016-090000',
    previous: true,
    stateJson: stateJson({ final: 'PASSED', runs: [REQ, DESIGN] }),
  });
  assert.equal(r.state, 'done');
  assert.equal(r.previous, true);
  assert.equal(r.result, '合格');
});

test('D0019-AC-08: final が無い古い記録の archive の run も「終わった」として出る', async () => {
  const r = await summarize({ previous: true, id: 'archive/20261016-090000', key: 'here|archive/20261016-090000', stateJson: stateJson({ runs: [REQ, DESIGN] }) });
  assert.equal(r.state, 'done');
  assert.equal(r.previous, true);
  assert.equal(r.stage, '設計');
});

test('D0019-AC-08: archive でない run は previous が false', async () => {
  const r = await fromSnapshot(finishedSnapshot());
  assert.equal(r.previous, false);
  assert.equal(r.updatedText, '10/17 10:05');
  assert.equal(FINISHED_UPDATED_AT.slice(11, 16), '10:05');
});

// ---- AC-09：並び ----

test('D0019-AC-09: sortRows は 確認待ち → 動いている → 待ち → 終わった。同じ状態のなかは最後に動いた時刻の新しい順', async () => {
  const { sortRows } = await rl();
  const t = (h: number) => Date.UTC(2026, 9, 17, h, 0, 0);
  const rows = [
    row({ key: 'k1', state: 'done', updatedMs: t(9) }),
    row({ key: 'k2', state: 'waiting', updatedMs: t(8) }),
    row({ key: 'k3', state: 'running', updatedMs: t(7) }),
    row({ key: 'k4', state: 'idle', updatedMs: t(12) }),
    row({ key: 'k5', state: 'waiting', updatedMs: t(10) }),
    row({ key: 'k6', state: 'done', updatedMs: t(11) }),
    row({ key: 'k7', state: 'running', updatedMs: t(13) }),
  ];
  assert.deepEqual(sortRows(rows).map((r) => r.key), ['k5', 'k2', 'k7', 'k3', 'k4', 'k6', 'k1']);
});

test('D0019-AC-09: 読めない時刻（null）は、同じ状態のなかの最後。時刻が同じなら key の順', async () => {
  const { sortRows } = await rl();
  const t = Date.UTC(2026, 9, 17, 10, 0, 0);
  const rows = [
    row({ key: 'b', state: 'done', updatedMs: null }),
    row({ key: 'z', state: 'done', updatedMs: t }),
    row({ key: 'a', state: 'done', updatedMs: t }),
    row({ key: 'c', state: 'done', updatedMs: t - 1000 }),
  ];
  assert.deepEqual(sortRows(rows).map((r) => r.key), ['a', 'z', 'c', 'b']);
});

test('D0019-AC-09: 入れる順が違っても同じ並びになり、選び（引数）は取らない：選びで並びが変わらない', async () => {
  const { sortRows } = await rl();
  const t = (h: number) => Date.UTC(2026, 9, 17, h, 0, 0);
  const rows = [
    row({ key: 'a', state: 'running', updatedMs: t(1) }),
    row({ key: 'b', state: 'waiting', updatedMs: t(2) }),
    row({ key: 'c', state: 'done', updatedMs: t(3) }),
    row({ key: 'd', state: 'done', updatedMs: null }),
  ];
  const expected = sortRows(rows).map((r) => r.key);
  assert.deepEqual(sortRows([...rows].reverse()).map((r) => r.key), expected);
  assert.deepEqual(sortRows([rows[2]!, rows[0]!, rows[3]!, rows[1]!]).map((r) => r.key), expected);
  assert.equal(sortRows.length, 1, 'sortRows は並べる行だけを受け取る（選んでいる行は引数に無い）');
});

// ---- AC-10：省く件数 ----

test('D0019-AC-10: 省いた件数の文字は「古い実行を N 件、省いています」。0 以下は空', async () => {
  const { omittedText, ARCHIVE_LIMIT, WORKTREE_LIMIT } = await rl();
  assert.equal(omittedText(2), '古い実行を 2 件、省いています');
  assert.equal(omittedText(11), '古い実行を 11 件、省いています');
  assert.equal(omittedText(0), '');
  assert.equal(omittedText(-3), '');
  assert.equal(ARCHIVE_LIMIT, 10);
  assert.equal(WORKTREE_LIMIT, 8);
});

// ---- AC-12・AC-14：待ち時間 ----

test('D0019-AC-12: 確認待ちの行だけ waitingSec（待ち始めからの秒）が入る', async () => {
  assert.equal((await fromSnapshot(waitingSnapshot(), 40)).waitingSec, 40);
  assert.equal((await fromSnapshot(waitingSnapshot(), 90)).waitingSec, 90);
});

test('D0019-AC-12: since が読めない・無い古い記録では waitingSec が null。確認待ちのまま', async () => {
  for (const snap of [waitingSnapshot({ omitSince: true }), waitingSnapshot({ since: 'いつか' }), waitingSnapshot({ since: 12345 })]) {
    const r = await fromSnapshot(snap, 40);
    assert.equal(r.state, 'waiting');
    assert.equal(r.waitingSec, null);
  }
});

test('D0019-AC-14: 動いている・終わった・待ちの行は waitingSec が null', async () => {
  assert.equal((await fromSnapshot(runningSnapshot(), 83)).waitingSec, null);
  assert.equal((await fromSnapshot(finishedSnapshot(), 83)).waitingSec, null);
  assert.equal((await summarize({ stateJson: stateJson({ runs: [REQ] }) }, 83)).waitingSec, null);
  assert.equal((await summarize({ previous: true, stateJson: stateJson({ final: 'PASSED', runs: [REQ] }) }, 83)).waitingSec, null);
});

// ---- AC-30：壊れた・古い形 ----

const BROKEN: [string, string | null, Partial<RunRow>][] = [
  ['壊れた JSON', '{壊れた', { pipe: '開発フロー', session: '開発フロー', costText: '—', updatedText: '—', updatedDate: '—', updatedMs: null, stage: '—', sessionId: null, elapsed: null }],
  ['JSON の配列', '[1,2]', { costText: '—', updatedText: '—', updatedDate: '—', updatedMs: null, elapsed: null }],
  ['JSON の数', '42', { costText: '—', updatedText: '—', updatedDate: '—', updatedMs: null }],
  ['中身が空の {}', '{}', { costText: '—', updatedText: '—', updatedDate: '—', updatedMs: null, stage: '—', sessionId: null, elapsed: null }],
  ['記録なし（null）', null, { costText: '—', updatedText: '—', updatedDate: '—', updatedMs: null, stage: '—', sessionId: null, elapsed: null }],
  ['updated_at が無い', JSON.stringify({ final: null, total_cost_usd: 1, runs: [] }), { updatedText: '—', updatedDate: '—', updatedMs: null, costText: '$1.000' }],
  ['updated_at が数', JSON.stringify({ updated_at: 12345, total_cost_usd: 1, runs: [] }), { updatedText: '—', updatedDate: '—', updatedMs: null }],
  ['updated_at が読めない文字', JSON.stringify({ updated_at: 'さっき', total_cost_usd: 1, runs: [] }), { updatedText: '—', updatedDate: '—', updatedMs: null }],
  ['total_cost_usd が無い', JSON.stringify({ updated_at: '2026-10-16T10:00:00', runs: [] }), { costText: '—', updatedText: '10/16 10:00', updatedDate: '10/16' }],
  ['total_cost_usd が文字', JSON.stringify({ updated_at: '2026-10-16T10:00:00', total_cost_usd: 'たくさん', runs: [] }), { costText: '—' }],
  ['pipe が数', JSON.stringify({ updated_at: '2026-10-16T10:00:00', pipe: 5, total_cost_usd: 0, runs: [] }), { pipe: '開発フロー', session: '開発フロー' }],
  ['name が数・session_id が数', JSON.stringify({ updated_at: '2026-10-16T10:00:00', name: 5, session_id: 7, total_cost_usd: 0, runs: [] }), { session: '開発フロー', sessionId: null }],
  ['stages が文字', JSON.stringify({ updated_at: '2026-10-16T10:00:00', stages: 'x', total_cost_usd: 0, runs: [REQ] }), { costText: '$0.000' }],
  ['runs が無い（stages も無い）', JSON.stringify({ updated_at: '2026-10-16T10:00:00', total_cost_usd: 0 }), { stage: '—' }],
];

for (const [label, text, expected] of BROKEN) {
  test(`D0019-AC-30: 読めない・欠けた記録でも行が出て、読めない項目は「—」になる：${label}`, async () => {
    const r = await summarize({ stateJson: text });
    for (const [k, v] of Object.entries(expected)) assert.deepEqual(r[k as keyof RunRow], v, k);
    assert.equal(typeof r.session, 'string');
    assert.ok(r.session.length > 0);
    assert.equal(typeof r.pipe, 'string');
    assert.ok(r.pipe.length > 0);
    assert.ok(['waiting', 'running', 'idle', 'done'].includes(r.state));
  });
}

test('D0019-AC-30: 壊れた記録の archive の行も、例外を出さず「終わった」で出る', async () => {
  const r = await summarize({ previous: true, id: 'archive/20261016-090000', key: 'here|archive/20261016-090000', stateJson: '{壊れた' });
  assert.equal(r.state, 'done');
  assert.equal(r.costText, '—');
});

test('D0019-AC-30: 壊れた記録でも、名前は id から決まる（パイプ名のフォルダ）', async () => {
  const r = await summarize({ id: 'spec-qa', key: 'here|spec-qa', stateJson: '{壊れた' });
  assert.equal(r.pipe, 'spec-qa');
  assert.equal(r.session, 'spec-qa');
});

// ---- AC-33：古い形 ----

test('D0019-AC-33: パイプを持つ前の記録（stages なし）は、これまでどおり開発の5段で今の段・状態が出る', async () => {
  const idle = await summarize({ stateJson: stateJson({ runs: [REQ, DESIGN, stageRunEntry({ stage: 'red', seq: 3 })] }) });
  assert.equal(idle.state, 'idle');
  assert.equal(idle.stage, 'テスト先行');
  const waiting = await summarize({
    stateJson: stateJson({ runs: [REQ, DESIGN], pendingReview: { stage: 'design', doc: 'docs/pipeline/02_design.md', session_id: 's' } }),
  });
  assert.equal(waiting.state, 'waiting');
  assert.equal(waiting.stage, '設計');
  const done = await summarize({ stateJson: stateJson({ final: 'PASSED', runs: [REQ, stageRunEntry({ stage: 'implement', seq: 2, attempt: 1 }), stageRunEntry({ stage: 'test', seq: 3, attempt: 1 })] }) });
  assert.equal(done.state, 'done');
  assert.equal(done.stage, '検証');
  const running = await summarize({ stateJson: stateJson({ runs: [REQ] }), stageLogs: [{ fileName: '02_design.jsonl', text: logText([promptLine('design')]) }] });
  assert.equal(running.state, 'running');
  assert.equal(running.stage, '設計');
});

test('D0019-AC-33: 前の版の見本（tests/fixtures/pipe_in/）も今の段・状態が出る', async () => {
  const waiting = await fromSnapshot(fixtureSnapshot('pipe_in', 'waiting'));
  assert.equal(waiting.state, 'waiting');
  assert.equal(waiting.stage, 'テスト先行');
  const finished = await fromSnapshot(fixtureSnapshot('pipe_in', 'finished'));
  assert.equal(finished.state, 'done');
  assert.equal(finished.result, '合格');
});

// ---- AC-23：覚えた値の検め ----

test('D0019-AC-23: parseRemembered は {place, id} の2つの文字列で、実行の目印の検査を通るものだけを通す', async () => {
  const { parseRemembered } = await rl();
  assert.deepEqual(parseRemembered({ place: 'here', id: '' }), { place: 'here', id: '' });
  assert.deepEqual(parseRemembered({ place: 'wt.feat-x', id: 'spec-qa' }), { place: 'wt.feat-x', id: 'spec-qa' });
  assert.deepEqual(parseRemembered({ place: 'main', id: 'archive/20261017-100000-2' }), { place: 'main', id: 'archive/20261017-100000-2' });
});

const BAD_REMEMBERED: [string, unknown][] = [
  ['null', null],
  ['undefined', undefined],
  ['数', 3],
  ['文字', 'here|x'],
  ['配列', ['here', '']],
  ['place が数', { place: 1, id: '' }],
  ['id が数', { place: 'here', id: 5 }],
  ['id が無い', { place: 'here' }],
  ['place が無い', { id: '' }],
  ['知らない place', { place: 'zzz', id: '' }],
  ['id が ..', { place: 'here', id: '..' }],
  ['id が ../x', { place: 'here', id: '../x' }],
  ['id が絶対パス', { place: 'here', id: '/etc/passwd' }],
  ['id が長すぎる', { place: 'here', id: 'a'.repeat(5000) }],
  ['place が長すぎる', { place: `wt.${'a'.repeat(500)}`, id: '' }],
];

for (const [label, value] of BAD_REMEMBERED) {
  test(`D0019-AC-23: 壊れた覚えた値は通さない（null になり、例外を出さない）：${label}`, async () => {
    const { parseRemembered } = await rl();
    assert.equal(parseRemembered(value), null);
  });
}
