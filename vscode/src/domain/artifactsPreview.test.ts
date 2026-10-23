// 成果物の一覧の項目（D0025・イシュー #49）：作った段・更新時刻の書き方・読んだ範囲の文字・切れた印・既定の選び・古い形の写し・変な名前。
// 純粋な関数と buildPipelineView だけを確かめる（ファイル・時計に触れない。「今」は引数）。
// 新しい部品（artifactFileOf・defaultArtifactName・formatLocalStamp）は、テストの中で読み込む
// （テスト先行のとき、まだ無い部品が「関数ではない」で落ちるようにしたため。前例：runListCounts.test.ts の rl()）。
// テスト先行のときから通っていたテスト（赤ではなく、守り続けるために置く）は、名前の末尾に「（今のまま通る。守る）」と書いた。
// 型は、テスト先行のとき（部品がまだ無いとき）も通るように、このファイルの中で緩く書き直している（Entry・DefLike・build）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { artifactDefsFor, buildArtifactList, isArtifactReady } from './artifacts.ts';
import { buildPipelineView } from './pipelineView.ts';
import type { PipelineView, ViewClock, WorkDirSnapshot } from './pipelineView.ts';
import { parseRunRecord } from './runRecord.ts';
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
import { BASE_AT } from '../test/liveFixtures.ts';
import { failVerdict } from '../test/reasonFixtures.ts';

// ---- 補助 ----

/** 成果物の一覧の 1 行（D0025 で足す項目を含む）。 */
interface Entry {
  name: string;
  label: string;
  stage: string | null;
  stageLabel: string | null;
  ready: boolean;
  text: string;
  cut: boolean;
  updatedText: string;
}
interface DefLike {
  name: string;
  label: string;
  stage?: string | null;
  stageLabel?: string | null;
}
type Build = (contents: Record<string, unknown>, defs?: readonly DefLike[], clock?: { localOffsetMin: number }) => Entry[];
const build = buildArtifactList as unknown as Build;
/** isArtifactReady(content: unknown) を、型に頼らず unknown を受ける形で呼ぶ（テスト先行のときは、文字か undefined だけを受ける型だったため） */
const isReady = isArtifactReady as unknown as (content: unknown) => boolean;

interface ArtifactFileLike {
  text: string;
  mtimeMs: number | null;
  cut: boolean;
}
interface ArtMod {
  artifactFileOf(value: unknown): ArtifactFileLike | null;
  defaultArtifactName(entries: readonly Entry[], liveStage: string | null): string | null;
}
const art = async (): Promise<ArtMod> => (await import('./artifacts.ts')) as unknown as ArtMod;
const stamp = async (): Promise<(ms: unknown, localOffsetMin: number) => string | null> =>
  ((await import('./timestamp.ts')) as unknown as { formatLocalStamp: (ms: unknown, localOffsetMin: number) => string | null }).formatLocalStamp;

const DASH = '—';

const DEV_NAMES = ['00_input.md', '01_requirements.md', '02_design.md', '03_red_tests.md', '04_implementation.md', '05_test_report.md', '99_summary.md'];
const DEV_LABELS = ['要件メモ', '要件定義書', '設計書', 'テスト先行の記録', '実装の記録', 'テスト報告', 'まとめ'];

const defsOf = (state: string | null): DefLike[] => artifactDefsFor(parseRunRecord(state)) as unknown as DefLike[];

/** 写しの成果物の欄（新旧どちらの形も、壊れた値も渡せるように緩い型で受ける） */
function snap(artifacts: Record<string, unknown>, p: Partial<WorkDirSnapshot> = {}): WorkDirSnapshot {
  return snapshot({ ...p, artifacts: artifacts as WorkDirSnapshot['artifacts'] });
}
const viewOf = (artifacts: Record<string, unknown>, p: Partial<WorkDirSnapshot> = {}, clock?: ViewClock): PipelineView =>
  buildPipelineView(snap(artifacts, p), clock);
const entriesOf = (view: PipelineView): Entry[] => view.artifacts as unknown as Entry[];
const entryOf = (view: PipelineView, name: string): Entry => {
  const found = entriesOf(view).find((e) => e.name === name);
  assert.ok(found, `${name} の行がある`);
  return found;
};
/** 既定の選びの引数（動いている段 ?? 確認待ちの段 ?? null。view が作る形） */
const liveOf = (view: PipelineView): string | null => view.runningStage ?? view.pendingReview?.stage ?? null;
const inputStatus = (view: PipelineView): string | undefined => view.nodes.find((n) => n.id === 'input')?.status;

/** 自分のキーとして入れる（__proto__ という名前でも、原型を替えずに自分のキーになる） */
function withOwn(base: Record<string, unknown>, key: string, value: unknown): Record<string, unknown> {
  const out = { ...base };
  Object.defineProperty(out, key, { value, enumerable: true, writable: true, configurable: true });
  return out;
}

const T_VALID = Date.UTC(2026, 9, 17, 1, 5, 0);
const CLOCK_JST = { localOffsetMin: 540 };

const requirementsDone = stageRunEntry({ stage: 'requirements', seq: 1 });
const designLog = { fileName: '02_design.jsonl', text: logText([promptLine('design', BASE_AT), assistantText('設計します')]) };

// ---- AC-01：成果物の一覧の並びと名前 ----

test('D0025-AC-01: 開発フロー（記録なし）で全部「ある」とき、7 行が 要件メモ…まとめ の順に出て、行ごとにラベルとファイル名が読める（今のまま通る。守る）', () => {
  const list = build(Object.fromEntries(DEV_NAMES.map((n) => [n, `${n} の中身`])));
  assert.deepEqual(
    list.map((e) => [e.label, e.name]),
    DEV_LABELS.map((label, i) => [label, DEV_NAMES[i]]),
  );
  assert.ok(list.every((e) => e.ready));
});

const DEV_RECORDS: readonly (readonly [string, string | null])[] = [
  ['記録なし（state.json が無い）', null],
  ['stages の無い古い記録', stateJson({ runs: [requirementsDone] })],
  ['開発の 5 段そのものの stages を持つ記録', stateJson({ stages: DEV_STAGES, runs: [requirementsDone] })],
];

for (const [label, state] of DEV_RECORDS) {
  test(`D0025-AC-01: ${label}でも、図の状態の成果物の一覧は 7 行で、同じ順・同じラベル・同じファイル名（今のまま通る。守る）`, () => {
    const view = viewOf(Object.fromEntries(DEV_NAMES.map((n) => [n, `${n} の中身`])), { stateJson: state });
    assert.deepEqual(
      entriesOf(view).map((e) => [e.label, e.name, e.ready]),
      DEV_LABELS.map((l, i) => [l, DEV_NAMES[i], true]),
    );
  });
}

test('D0025-AC-01: 開発フローで中身が新しい形（{ text }）でも、7 行が「ある」になる', () => {
  const list = build(Object.fromEntries(DEV_NAMES.map((n) => [n, { text: `${n} の中身` }])));
  assert.deepEqual(
    list.map((e) => [e.name, e.ready, e.text]),
    DEV_NAMES.map((n) => [n, true, `${n} の中身`]),
  );
});

test('D0025-AC-01: パイプは 依頼メモ・各段の output（名前は段の表示名）・まとめ の順で、行ごとにラベルとファイル名が読める（今のまま通る。守る）', () => {
  const defs = defsOf(stateJson({ pipe: 'diagrams', stages: DIAGRAMS_STAGES }));
  const list = build({}, defs);
  assert.deepEqual(
    list.map((e) => [e.label, e.name]),
    [
      ['依頼メモ', '00_input.md'],
      ['ソースの調査', '01_survey.md'],
      ['図を描く', '02_diagrams.md'],
      ['図とソースの突き合わせ', '03_verify.md'],
      ['まとめ', '99_summary.md'],
    ],
  );
});

test('D0025-AC-01: パイプで同じ output を持つ段が 2 つあっても、その行は 1 回だけ（名前は先の段の表示名）（今のまま通る。守る）', () => {
  const stages = [
    { name: 'a', label: '段A', output: 'x.md', review: false },
    { name: 'b', label: '段B', output: 'x.md', review: false },
    { name: 'c', label: '段C', output: 'y.md', review: false },
  ];
  const list = build({}, defsOf(stateJson({ pipe: 'p', stages })));
  assert.deepEqual(
    list.map((e) => [e.label, e.name]),
    [['依頼メモ', '00_input.md'], ['段A', 'x.md'], ['段C', 'y.md'], ['まとめ', '99_summary.md']],
  );
});

// ---- AC-02・AC-03：作った段 ----

const DEV_STAGE_TABLE: readonly (readonly [string, string | null, string | null])[] = [
  ['00_input.md', null, null],
  ['01_requirements.md', 'requirements', '要件定義'],
  ['02_design.md', 'design', '設計'],
  ['03_red_tests.md', 'red', 'テスト先行'],
  ['04_implementation.md', 'implement', '実装'],
  ['05_test_report.md', 'test', '検証'],
  ['99_summary.md', null, null],
];

test('D0025-AC-02: 開発フローの作った段は 01→要件定義・02→設計・03→テスト先行・04→実装・05→検証、00 と 99 は無し（—）', () => {
  const defs = defsOf(stateJson({}));
  assert.deepEqual(
    defs.map((d) => [d.name, d.stage, d.stageLabel]),
    DEV_STAGE_TABLE,
  );
});

test('D0025-AC-02: 記録なし（null）と、開発の 5 段の stages を持つ記録でも、作った段の表は同じ', () => {
  for (const state of [null, stateJson({ stages: DEV_STAGES })]) {
    assert.deepEqual(
      defsOf(state).map((d) => [d.name, d.stage, d.stageLabel]),
      DEV_STAGE_TABLE,
      String(state === null ? 'null' : 'stages つき'),
    );
  }
});

test('D0025-AC-02: 開発の 5 段の stages の表示名が違う記録でも、開発フローの作った段の表示名は固定の表（STAGE_LABELS）', () => {
  const relabeled = DEV_STAGES.map((s) => ({ ...s, label: `別名-${s.name}` }));
  assert.deepEqual(
    defsOf(stateJson({ stages: relabeled })).map((d) => [d.name, d.stage, d.stageLabel]),
    DEV_STAGE_TABLE,
  );
});

test('D0025-AC-02: 図の状態の成果物の一覧の各行（開発フロー）に、作った段（名前と表示名）が付く', () => {
  const view = viewOf({ '01_requirements.md': '要件', '02_design.md': '設計' }, { stateJson: stateJson({ runs: [requirementsDone] }) });
  assert.deepEqual(
    entriesOf(view).map((e) => [e.name, e.stage, e.stageLabel]),
    DEV_STAGE_TABLE,
  );
});

test('D0025-AC-02: パイプの作った段は、その output を持つ段（名前と表示名）。依頼メモとまとめは無し（—）', () => {
  const defs = defsOf(stateJson({ pipe: 'diagrams', stages: DIAGRAMS_STAGES }));
  assert.deepEqual(
    defs.map((d) => [d.name, d.stage, d.stageLabel]),
    [
      ['00_input.md', null, null],
      ['01_survey.md', 'survey', 'ソースの調査'],
      ['02_diagrams.md', 'draw', '図を描く'],
      ['03_verify.md', 'verify', '図とソースの突き合わせ'],
      ['99_summary.md', null, null],
    ],
  );
});

test('D0025-AC-02: パイプで同じ output を持つ段が複数あれば、作った段は先の段', () => {
  const stages = [
    { name: 'a', label: '段A', output: 'x.md', review: false },
    { name: 'b', label: '段B', output: 'x.md', review: false },
  ];
  const x = defsOf(stateJson({ pipe: 'p', stages })).find((d) => d.name === 'x.md');
  assert.deepEqual([x?.stage, x?.stageLabel], ['a', '段A']);
});

test('D0025-AC-03: 作った段は、成果物が「まだない」行にも付く（段は記録で決まり、ファイルの有無で決まらない）', () => {
  const dev = build({}, defsOf(stateJson({})));
  assert.ok(dev.every((e) => !e.ready));
  assert.deepEqual(
    dev.map((e) => [e.name, e.stage, e.stageLabel]),
    DEV_STAGE_TABLE,
  );
  const pipe = build({}, defsOf(stateJson({ pipe: 'diagrams', stages: DIAGRAMS_STAGES })));
  assert.deepEqual(
    pipe.map((e) => [e.name, e.ready, e.stage]),
    [['00_input.md', false, null], ['01_survey.md', false, 'survey'], ['02_diagrams.md', false, 'draw'], ['03_verify.md', false, 'verify'], ['99_summary.md', false, null]],
  );
});

test('D0025-AC-03: 「ある」行と「まだない」行で、作った段は同じ（設計だけ「ある」でも 01 の段は変わらない）', () => {
  const view = viewOf({ '02_design.md': '設計' }, { stateJson: stateJson({ runs: [requirementsDone] }) });
  assert.equal(entryOf(view, '02_design.md').ready, true);
  assert.equal(entryOf(view, '01_requirements.md').ready, false);
  assert.equal(entryOf(view, '02_design.md').stage, 'design');
  assert.equal(entryOf(view, '01_requirements.md').stage, 'requirements');
});

test('D0025-AC-03: 段を引けない成果物（呼ぶ側が渡した一覧の段が無いもの）は、段も表示名も null のまま行に届く', () => {
  const defs: DefLike[] = [{ name: 'zz.md', label: 'どの段のものでもない', stage: null, stageLabel: null }];
  const [row] = build({ 'zz.md': '中身' }, defs);
  assert.deepEqual([row?.stage, row?.stageLabel, row?.ready], [null, null, true]);
});

// ---- AC-04：時刻の書き方 ----

const STAMPS: readonly (readonly [string, number, number, string])[] = [
  ['同じ日の中（UTC 01:05・+540 分）', Date.UTC(2026, 9, 17, 1, 5), 540, '10/17 10:05'],
  ['日付と月が変わる（10/31 23:30 UTC・+540 分）', Date.UTC(2026, 9, 31, 23, 30), 540, '11/01 08:30'],
  ['戻る向きで月が変わる（11/01 00:30 UTC・-300 分）', Date.UTC(2026, 10, 1, 0, 30), -300, '10/31 19:30'],
  ['年が変わっても年は出さない', Date.UTC(2026, 11, 31, 23, 30), 60, '01/01 00:30'],
  ['うるう日', Date.UTC(2028, 1, 29, 12, 0), 0, '02/29 12:00'],
  ['月・日・時・分は 2 桁にそろえる', Date.UTC(2026, 0, 2, 3, 4), 0, '01/02 03:04'],
  ['30 分単位のずれ（+330 分）', Date.UTC(2026, 9, 17, 1, 5), 330, '10/17 06:35'],
  ['秒以下は切り捨てる', Date.UTC(2026, 9, 17, 1, 5, 59, 999), 0, '10/17 01:05'],
];

for (const [label, ms, offset, expected] of STAMPS) {
  test(`D0025-AC-04: formatLocalStamp は ${label} を ${expected} にする`, async () => {
    const formatLocalStamp = await stamp();
    assert.equal(formatLocalStamp(ms, offset), expected);
  });
}

const NOT_STAMPABLE: readonly (readonly [string, unknown])[] = [
  ['NaN', Number.NaN],
  ['Infinity', Number.POSITIVE_INFINITY],
  ['-Infinity', Number.NEGATIVE_INFINITY],
  ['0', 0],
  ['負の数', -1],
  ['数の文字', '1760000000000'],
  ['null', null],
  ['undefined', undefined],
  ['true', true],
  ['オブジェクト', {}],
  ['Date にできない巨大な数', 8_640_000_000_000_001],
  ['桁違いに大きい数', 1e300],
];

for (const [label, bad] of NOT_STAMPABLE) {
  test(`D0025-AC-04: formatLocalStamp は ${label} を null にする（例外を出さない）`, async () => {
    const formatLocalStamp = await stamp();
    assert.equal(formatLocalStamp(bad, 540), null);
  });
}

test('D0025-AC-04: formatLocalStamp は、時刻自体は Date にできても、手元の時刻に直すと Date にできなくなる値も null にする', async () => {
  const formatLocalStamp = await stamp();
  assert.equal(formatLocalStamp(8_640_000_000_000_000, 540), null);
});

test('D0025-AC-04: 成果物の一覧の行の updatedText に、手元のずれで直した MM/DD HH:mm が入る（3 つの例）', () => {
  const cases: readonly (readonly [number, number, string])[] = [
    [Date.UTC(2026, 9, 17, 1, 5), 540, '10/17 10:05'],
    [Date.UTC(2026, 9, 31, 23, 30), 540, '11/01 08:30'],
    [Date.UTC(2026, 10, 1, 0, 30), -300, '10/31 19:30'],
  ];
  for (const [ms, offset, expected] of cases) {
    const [row] = build({ '01_requirements.md': { text: '中身', mtimeMs: ms } }, [{ name: '01_requirements.md', label: '要件定義書' }], { localOffsetMin: offset });
    assert.equal(row?.updatedText, expected);
  }
});

test('D0025-AC-04: buildPipelineView(写し, 時計) を通しても、各行の updatedText は時計のずれで直した時刻（時計の nowMs は使わない）', () => {
  const view = viewOf(
    { '01_requirements.md': { text: '要件', mtimeMs: Date.UTC(2026, 9, 17, 1, 5) }, '02_design.md': { text: '設計', mtimeMs: Date.UTC(2026, 9, 31, 23, 30) } },
    { stateJson: stateJson({ runs: [requirementsDone] }) },
    { nowMs: Date.UTC(2030, 0, 1), localOffsetMin: 540 },
  );
  assert.equal(entryOf(view, '01_requirements.md').updatedText, '10/17 10:05');
  assert.equal(entryOf(view, '02_design.md').updatedText, '11/01 08:30');
});

// ---- AC-05：時刻が読めないとき ----

const BAD_MTIMES: readonly (readonly [string, unknown])[] = [
  ['文字', '1760000000000'],
  ['負の数', -1],
  ['0', 0],
  ['NaN', Number.NaN],
  ['Infinity', Number.POSITIVE_INFINITY],
  ['Date にできない巨大な数', 8_640_000_000_000_001],
  ['桁違いに大きい数', 1e300],
  ['null', null],
  ['undefined（項目なし）', undefined],
  ['真偽', true],
  ['オブジェクト', {}],
];

for (const [label, bad] of BAD_MTIMES) {
  test(`D0025-AC-05: 更新時刻が ${label} の成果物は updatedText が「—」になり、中身は出る`, () => {
    const [row] = build({ '01_requirements.md': { text: '中身', mtimeMs: bad } }, [{ name: '01_requirements.md', label: '要件定義書' }], CLOCK_JST);
    assert.equal(row?.ready, true);
    assert.equal(row?.text, '中身');
    assert.equal(row?.updatedText, DASH);
  });
}

test('D0025-AC-05: 時計（ViewClock）が渡されないときは、更新時刻が正しくても updatedText は「—」で、中身は出る', () => {
  const [row] = build({ '01_requirements.md': { text: '中身', mtimeMs: T_VALID } }, [{ name: '01_requirements.md', label: '要件定義書' }]);
  assert.equal(row?.ready, true);
  assert.equal(row?.text, '中身');
  assert.equal(row?.updatedText, DASH);
});

test('D0025-AC-05: 図の状態の組み立てで時計が無いときも、updatedText は「—」で中身は出る', () => {
  const view = viewOf({ '01_requirements.md': { text: '要件', mtimeMs: T_VALID } });
  assert.equal(entryOf(view, '01_requirements.md').updatedText, DASH);
  assert.equal(entryOf(view, '01_requirements.md').text, '要件');
});

// ---- AC-06：「あるか」の判定 ----

const BLANK_TEXTS: readonly (readonly [string, string])[] = [
  ['空', ''],
  ['空白と改行だけ', '  \n\t '],
  ['全角空白と NBSP だけ', '　 \n'],
];

for (const [label, text] of BLANK_TEXTS) {
  test(`D0025-AC-06: 中身が ${label} の成果物（文字だけの旧形）は「まだない」で、text は空・updatedText は「—」`, () => {
    const [row] = build({ '01_requirements.md': text }, [{ name: '01_requirements.md', label: '要件定義書' }], CLOCK_JST);
    assert.equal(row?.ready, false);
    assert.equal(row?.text, '');
    assert.equal(row?.updatedText, DASH);
  });
  test(`D0025-AC-06: 中身が ${label} の成果物（新しい形）は、更新時刻が正しくても「まだない」で、text は空・updatedText は「—」`, () => {
    const [row] = build({ '01_requirements.md': { text, mtimeMs: T_VALID } }, [{ name: '01_requirements.md', label: '要件定義書' }], CLOCK_JST);
    assert.equal(row?.ready, false);
    assert.equal(row?.text, '');
    assert.equal(row?.updatedText, DASH);
  });
}

test('D0025-AC-06: 「ある」の判定は、空白だけでない文字があること（旧形の文字でも新しい形でも。前後の空白は text に残る）', () => {
  const [oldForm, newForm] = [
    build({ '01_requirements.md': '\n  # 題\n' }, [{ name: '01_requirements.md', label: 'a' }])[0],
    build({ '01_requirements.md': { text: '\n  # 題\n' } }, [{ name: '01_requirements.md', label: 'a' }])[0],
  ];
  assert.deepEqual([oldForm?.ready, newForm?.ready], [true, true]);
  assert.equal(oldForm?.text, '\n  # 題\n');
  assert.equal(newForm?.text, '\n  # 題\n');
});

test('D0025-AC-06: isArtifactReady は、空白だけの文字・無いものを偽、空白だけでない文字を真にする（今のまま通る。守る）', () => {
  assert.equal(isReady('中身'), true);
  assert.equal(isReady('  \n'), false);
  assert.equal(isReady(''), false);
  assert.equal(isReady(undefined), false);
});

test('D0025-AC-06: isArtifactReady は新しい形（{ text }）でも同じに決まる', () => {
  assert.equal(isReady({ text: '中身' }), true);
  assert.equal(isReady({ text: '  \n' }), false);
  assert.equal(isReady({ text: '' }), false);
});

// ---- AC-11・AC-12・AC-13：既定の選び ----

/** 設計が動いている開発フロー（要件定義は終わり、02_design.jsonl が動いている）。 */
const designRunning = (artifacts: Record<string, unknown>, p: Partial<WorkDirSnapshot> = {}): PipelineView =>
  viewOf(artifacts, { stateJson: stateJson({ runs: [requirementsDone] }), stageLogs: [designLog], ...p });

/** 差し戻しの 2 回目で実装が動いている開発フロー。 */
function implementRunningSecondTime(artifacts: Record<string, unknown>): PipelineView {
  const runs = [
    requirementsDone,
    stageRunEntry({ stage: 'implement', seq: 2, attempt: 1 }),
    stageRunEntry({ stage: 'test', seq: 3, attempt: 1 }),
    failVerdict({ attempt: 1, summary: '不合格', failures: [{ criterion: 'AC-01', detail: 'x' }] }),
  ];
  const log = { fileName: '04_implement_2.jsonl', text: logText([promptLine('implement', BASE_AT), assistantText('直します')]) };
  return viewOf(artifacts, { stateJson: stateJson({ runs }), stageLogs: [log] });
}

const allReady = (names: readonly string[]): Record<string, unknown> => Object.fromEntries(names.map((n) => [n, { text: `${n} の中身` }]));

test('D0025-AC-11: 動いている段が設計で 02_design.md が「ある」とき、既定は 02_design.md', async () => {
  const { defaultArtifactName } = await art();
  const view = designRunning(allReady(['00_input.md', '01_requirements.md', '02_design.md']));
  assert.equal(view.runningStage, 'design');
  assert.equal(defaultArtifactName(entriesOf(view), liveOf(view)), '02_design.md');
});

test('D0025-AC-11: 差し戻しの 2 回目で動いている段が実装のとき、既定は 04_implementation.md（それより後ろの 05 が「ある」でも）', async () => {
  const { defaultArtifactName } = await art();
  const view = implementRunningSecondTime(allReady(['00_input.md', '01_requirements.md', '02_design.md', '03_red_tests.md', '04_implementation.md', '05_test_report.md']));
  assert.equal(view.runningStage, 'implement');
  assert.equal(defaultArtifactName(entriesOf(view), liveOf(view)), '04_implementation.md');
});

test('D0025-AC-11: パイプは、動いている段の output が既定（段 draw が動いていれば 02_diagrams.md。後ろの 03 が「ある」でも）', async () => {
  const { defaultArtifactName } = await art();
  const state = stateJson({ pipe: 'diagrams', stages: DIAGRAMS_STAGES, runs: [stageRunEntry({ stage: 'survey', seq: 1 })] });
  const log = { fileName: '02_draw.jsonl', text: logText([promptLine('draw', BASE_AT), assistantText('描きます')]) };
  const view = viewOf(allReady(['00_input.md', '01_survey.md', '02_diagrams.md', '03_verify.md']), { stateJson: state, stageLogs: [log] });
  assert.equal(view.runningStage, 'draw');
  assert.equal(defaultArtifactName(entriesOf(view), liveOf(view)), '02_diagrams.md');
});

test('D0025-AC-11: 動いている段と確認待ちの段が両方あるときは、動いている段が先（確認待ちの印が古くても）', async () => {
  const { defaultArtifactName } = await art();
  const pendingReview = { stage: 'requirements', doc: 'docs/pipeline/01_requirements.md', session_id: 's' };
  const view = designRunning(allReady(['00_input.md', '01_requirements.md', '02_design.md']), {
    stateJson: stateJson({ runs: [requirementsDone], pendingReview }),
  });
  assert.equal(view.runningStage, 'design');
  assert.equal(view.pendingReview?.stage, 'requirements');
  assert.equal(defaultArtifactName(entriesOf(view), liveOf(view)), '02_design.md');
});

test('D0025-AC-12: 動いている段が無く、確認待ちの段の成果物が「ある」とき、既定はそれ（後ろの成果物が「ある」でも）', async () => {
  const { defaultArtifactName } = await art();
  const pendingReview = { stage: 'requirements', doc: 'docs/pipeline/01_requirements.md', session_id: 's' };
  const view = viewOf(allReady(['00_input.md', '01_requirements.md', '02_design.md']), { stateJson: stateJson({ runs: [requirementsDone], pendingReview }) });
  assert.equal(view.runningStage, null);
  assert.equal(view.pendingReview?.stage, 'requirements');
  assert.equal(defaultArtifactName(entriesOf(view), liveOf(view)), '01_requirements.md');
});

test('D0025-AC-12: パイプで確認待ちの段の成果物が「ある」とき、既定はその段の output', async () => {
  const { defaultArtifactName } = await art();
  const pendingReview = { stage: 'survey', doc: 'docs/pipeline/diagrams/01_survey.md', session_id: 's' };
  const state = stateJson({ pipe: 'diagrams', stages: DIAGRAMS_STAGES, runs: [stageRunEntry({ stage: 'survey', seq: 1 })], pendingReview });
  const view = viewOf(allReady(['00_input.md', '01_survey.md', '02_diagrams.md']), { stateJson: state });
  assert.equal(defaultArtifactName(entriesOf(view), liveOf(view)), '01_survey.md');
});

test('D0025-AC-13: 終わった実行（動いている段も確認待ちも無い）は、一覧の順で最後の「ある」＝ 99_summary.md', async () => {
  const { defaultArtifactName } = await art();
  const view = viewOf(allReady(DEV_NAMES), { stateJson: stateJson({ runs: [requirementsDone], final: 'PASSED' }) });
  assert.equal(liveOf(view), null);
  assert.equal(defaultArtifactName(entriesOf(view), liveOf(view)), '99_summary.md');
});

test('D0025-AC-13: 終わった実行で 99_summary.md が無いときは、一覧の順で最後の「ある」（途中の 03 が抜けていても）', async () => {
  const { defaultArtifactName } = await art();
  const view = viewOf(allReady(['00_input.md', '01_requirements.md', '02_design.md', '04_implementation.md']), { stateJson: stateJson({ final: 'TEST_FAILED' }) });
  assert.equal(defaultArtifactName(entriesOf(view), liveOf(view)), '04_implementation.md');
});

test('D0025-AC-13: 設計が動き始めたばかりで 02_design.md がまだ無い実行は、一覧の順で最後の「ある」＝ 01_requirements.md', async () => {
  const { defaultArtifactName } = await art();
  const view = designRunning(allReady(['00_input.md', '01_requirements.md']));
  assert.equal(view.runningStage, 'design');
  assert.equal(entryOf(view, '02_design.md').ready, false);
  assert.equal(defaultArtifactName(entriesOf(view), liveOf(view)), '01_requirements.md');
});

test('D0025-AC-13: 動いている段の成果物が「まだない」ときは、確認待ちの段を見ず、一覧の順で最後の「ある」', async () => {
  const { defaultArtifactName } = await art();
  const pendingReview = { stage: 'requirements', doc: 'docs/pipeline/01_requirements.md', session_id: 's' };
  const view = designRunning(allReady(['00_input.md', '01_requirements.md', '03_red_tests.md']), {
    stateJson: stateJson({ runs: [requirementsDone], pendingReview }),
  });
  assert.equal(view.runningStage, 'design');
  assert.equal(view.pendingReview?.stage, 'requirements');
  assert.equal(defaultArtifactName(entriesOf(view), liveOf(view)), '03_red_tests.md');
});

test('D0025-AC-13: 動いている段の名前が記録に無い（どの成果物の段でもない）ときは、一覧の順で最後の「ある」', async () => {
  const { defaultArtifactName } = await art();
  const ghost = { fileName: '02_ghost.jsonl', text: logText([promptLine('ghost', BASE_AT), assistantText('?')]) };
  const view = viewOf(allReady(['00_input.md', '01_requirements.md', '02_design.md']), { stateJson: stateJson({ runs: [requirementsDone] }), stageLogs: [ghost] });
  assert.equal(view.runningStage, 'ghost');
  assert.equal(defaultArtifactName(entriesOf(view), liveOf(view)), '02_design.md');
});

test('D0025-AC-13: 段の名前を渡さない（null）ときも、一覧の順で最後の「ある」', async () => {
  const { defaultArtifactName } = await art();
  const entries = build(allReady(['00_input.md', '02_design.md']), defsOf(stateJson({})));
  assert.equal(defaultArtifactName(entries, null), '02_design.md');
});

test('D0025-AC-14: 「ある」成果物が 1 つも無いときの既定は null（空白だけ・無いものばかり）', async () => {
  const { defaultArtifactName } = await art();
  const entries = build({ '01_requirements.md': { text: '  \n' }, '02_design.md': '' }, defsOf(stateJson({})));
  assert.ok(entries.every((e) => !e.ready));
  assert.equal(defaultArtifactName(entries, 'design'), null);
  assert.equal(defaultArtifactName(entries, null), null);
  assert.equal(defaultArtifactName([], null), null);
});

test('D0025-AC-13: 既定の選びは一覧の項目を書き換えない（同じ入力で何度でも同じ答え）', async () => {
  const { defaultArtifactName } = await art();
  const entries = build(allReady(['00_input.md', '01_requirements.md', '02_design.md']), defsOf(stateJson({})));
  const before = JSON.stringify(entries);
  const first = defaultArtifactName(entries, 'requirements');
  const second = defaultArtifactName(entries, 'requirements');
  assert.equal(first, '01_requirements.md');
  assert.equal(second, first);
  assert.equal(JSON.stringify(entries), before);
});

// 既定の選びの判断だけを確かめる。項目は旧形（文字だけ）の写しから作る：新しい形（{ text }）の読み（isArtifactReady の対応）に頼らないので、
// 新しい形がまだ読めないあいだも、上の { text } のテストのように手前で落ちず、defaultArtifactName が無いこと自体で落ちる。答えは上のテストと同じ。
const oldForm = (names: readonly string[]): Record<string, unknown> => Object.fromEntries(names.map((n) => [n, `${n} の中身`]));
const devDefs = (): DefLike[] => defsOf(stateJson({}));
const diagramsDefs = (): DefLike[] => defsOf(stateJson({ pipe: 'diagrams', stages: DIAGRAMS_STAGES }));

const PICK_ROWS: readonly (readonly [ac: string, label: string, defs: () => DefLike[], ready: readonly string[], live: string | null, expected: string | null])[] = [
  ['AC-11', '動いている段が設計で 02_design.md が「ある」→ 02_design.md', devDefs, DEV_NAMES.slice(0, 3), 'design', '02_design.md'],
  ['AC-11', '差し戻しの 2 回目で動いている段が実装 → 04_implementation.md（後ろの 05 が「ある」でも）', devDefs, DEV_NAMES.slice(0, 6), 'implement', '04_implementation.md'],
  ['AC-11', 'パイプは動いている段 draw の output → 02_diagrams.md（後ろの 03 が「ある」でも）', diagramsDefs, ['00_input.md', '01_survey.md', '02_diagrams.md', '03_verify.md'], 'draw', '02_diagrams.md'],
  ['AC-12', '確認待ちの段（要件定義）の成果物が「ある」→ 01_requirements.md（後ろの成果物が「ある」でも）', devDefs, DEV_NAMES.slice(0, 3), 'requirements', '01_requirements.md'],
  ['AC-12', 'パイプで確認待ちの段 survey の成果物が「ある」→ 01_survey.md', diagramsDefs, ['00_input.md', '01_survey.md', '02_diagrams.md'], 'survey', '01_survey.md'],
  ['AC-13', '動いている段も確認待ちの段も無い終わった実行 → 一覧の順で最後の「ある」＝ 99_summary.md', devDefs, DEV_NAMES, null, '99_summary.md'],
  ['AC-13', '99_summary.md が無い終わった実行 → 最後の「ある」（途中の 03 が抜けていても）', devDefs, ['00_input.md', '01_requirements.md', '02_design.md', '04_implementation.md'], null, '04_implementation.md'],
  ['AC-13', '設計が動き始めたばかりで 02_design.md がまだ無い → 最後の「ある」＝ 01_requirements.md', devDefs, DEV_NAMES.slice(0, 2), 'design', '01_requirements.md'],
  ['AC-13', '動いている段の成果物が「まだない」ときは確認待ちを見ず、最後の「ある」＝ 03_red_tests.md', devDefs, ['00_input.md', '01_requirements.md', '03_red_tests.md'], 'design', '03_red_tests.md'],
  ['AC-13', '段の名前がどの成果物の段でもない → 最後の「ある」＝ 02_design.md', devDefs, ['00_input.md', '02_design.md'], 'no-such-stage', '02_design.md'],
  ['AC-14', '「ある」成果物が 1 つも無い → null', devDefs, [], 'design', null],
];

for (const [ac, label, defs, readyNames, live, expected] of PICK_ROWS) {
  test(`D0025-${ac}: 既定の選び（旧形の文字の写しから作った項目で defaultArtifactName だけを確かめる）：${label}`, async () => {
    const { defaultArtifactName } = await art();
    assert.equal(defaultArtifactName(build(oldForm(readyNames), defs()), live), expected);
  });
}

// ---- AC-46：切れた成果物の「あるか」 ----

test('D0025-AC-46: 切れた成果物でも、先頭が空白だけでなければ「ある」（text と切れた印がそのまま行に届く）', () => {
  const text = `本文${' '.repeat(262_144)}`;
  const [row] = build({ '01_requirements.md': { text, cut: true } }, [{ name: '01_requirements.md', label: '要件定義書' }]);
  assert.equal(row?.ready, true);
  assert.equal(row?.cut, true);
  assert.equal(row?.text, text);
});

test('D0025-AC-46: 先頭の 262,144 バイトが空白だけの切れた成果物は「まだない」（text は空）', () => {
  const [row] = build({ '01_requirements.md': { text: ' '.repeat(262_144), cut: true } }, [{ name: '01_requirements.md', label: '要件定義書' }]);
  assert.equal(row?.ready, false);
  assert.equal(row?.text, '');
});

test('D0025-AC-46: 切れていない成果物の cut は偽（cut を持たない・偽の項目も、旧形の文字も）', () => {
  const defs = [{ name: 'a.md', label: 'a' }, { name: 'b.md', label: 'b' }, { name: 'c.md', label: 'c' }];
  const rows = build({ 'a.md': { text: '中身' }, 'b.md': { text: '中身', cut: false }, 'c.md': '中身' }, defs);
  assert.deepEqual(rows.map((r) => [r.ready, r.cut]), [[true, false], [true, false], [true, false]]);
});

// ---- AC-64：変な名前（constructor・__proto__ ほか） ----

const ODD_NAMES = ['constructor', '__proto__', 'toString', 'hasOwnProperty', 'valueOf', 'text'];

for (const name of ODD_NAMES) {
  test(`D0025-AC-64: 名前が ${name} の成果物は、写しに無ければ「まだない」（例外なし）で、ほかの成果物の判定は変わらない`, () => {
    const defs: DefLike[] = [
      { name: '01_requirements.md', label: '要件', stage: null, stageLabel: null },
      { name, label: '変な名前', stage: null, stageLabel: null },
    ];
    const rows = build({ '01_requirements.md': { text: '要件' } }, defs);
    assert.deepEqual(rows.map((r) => [r.name, r.ready, r.text]), [['01_requirements.md', true, '要件'], [name, false, '']]);
  });

  test(`D0025-AC-64: 名前が ${name} の成果物が写しに自分のキーとしてあれば「ある」になり、ほかの成果物を壊さず、原型も汚れない`, () => {
    const defs: DefLike[] = [
      { name: '01_requirements.md', label: '要件', stage: null, stageLabel: null },
      { name, label: '変な名前', stage: null, stageLabel: null },
      { name: '02_design.md', label: '設計', stage: null, stageLabel: null },
    ];
    const contents = withOwn({ '01_requirements.md': { text: '要件' }, '02_design.md': '設計' }, name, { text: '変な名前の中身' });
    const rows = build(contents, defs);
    assert.deepEqual(rows.map((r) => [r.name, r.ready, r.text]), [['01_requirements.md', true, '要件'], [name, true, '変な名前の中身'], ['02_design.md', true, '設計']]);
    assert.equal(Object.getPrototypeOf(contents), Object.prototype, '入れ物の原型が替わっていない');
    assert.equal(Object.hasOwn(Object.prototype, 'text'), false, 'Object.prototype に text が生えていない');
  });

  test(`D0025-AC-64: パイプの output が ${name} の記録でも、図の状態の組み立てが例外なく、その成果物は写しにあれば「ある」・無ければ「まだない」`, () => {
    const stages = [
      { name: 'a', label: '段A', output: name, review: false },
      { name: 'b', label: '段B', output: '02_b.md', review: false },
    ];
    const state = stateJson({ pipe: 'p', stages });
    const absent = viewOf({ '02_b.md': { text: 'B' } }, { stateJson: state });
    assert.deepEqual(entriesOf(absent).map((e) => [e.name, e.ready]), [['00_input.md', false], [name, false], ['02_b.md', true], ['99_summary.md', false]]);
    const present = viewOf(withOwn({ '02_b.md': { text: 'B' } }, name, { text: 'A' }), { stateJson: state });
    assert.deepEqual(entriesOf(present).map((e) => [e.name, e.ready, e.text]), [['00_input.md', false, ''], [name, true, 'A'], ['02_b.md', true, 'B'], ['99_summary.md', false, '']]);
    assert.equal(entryOf(present, name).stage, 'a');
  });
}

// ---- AC-71：古い記録・壊れた値 ----

test('D0025-AC-71: stages の無い古い記録は、開発フローの 7 つの成果物が出て、作った段は表のとおり', () => {
  const view = viewOf(allReady(['00_input.md', '01_requirements.md']), { stateJson: stateJson({ runs: [requirementsDone] }) });
  assert.deepEqual(
    entriesOf(view).map((e) => [e.name, e.stage]),
    DEV_STAGE_TABLE.map(([name, stage]) => [name, stage]),
  );
  assert.deepEqual(entriesOf(view).map((e) => e.ready), [true, true, false, false, false, false, false]);
});

test('D0025-AC-71: output の無い記録（パイプで依頼メモとまとめだけ）でも、2 行が出て、作った段は引けない（null）', () => {
  const stages = [{ name: 'a', label: '段A' }, { name: 'b', label: '段B', review: true }];
  const view = viewOf({ '00_input.md': { text: 'メモ' }, '99_summary.md': { text: 'まとめ' } }, { stateJson: stateJson({ pipe: 'p', stages }) });
  assert.deepEqual(
    entriesOf(view).map((e) => [e.name, e.ready, e.stage, e.stageLabel, e.text]),
    [['00_input.md', true, null, null, 'メモ'], ['99_summary.md', true, null, null, 'まとめ']],
  );
});

const BROKEN_STATES: readonly (readonly [string, string | null])[] = [
  ['state.json が無い（null）', null],
  ['壊れた JSON', '{壊れた'],
  ['JSON の配列', '[1,2]'],
  ['JSON の数', '42'],
  ['中身が空の {}', '{}'],
];

for (const [label, state] of BROKEN_STATES) {
  test(`D0025-AC-71: ${label}の run でも、ファイルが読めれば中身が出る（開発フローの 7 つ。作った段は表のとおり）`, () => {
    const view = viewOf({ '01_requirements.md': { text: '要件の本文', mtimeMs: T_VALID }, '99_summary.md': '終わり' }, { stateJson: state }, { nowMs: T_VALID, localOffsetMin: 540 });
    assert.deepEqual(entriesOf(view).map((e) => e.name), DEV_NAMES);
    const req = entryOf(view, '01_requirements.md');
    assert.deepEqual([req.ready, req.text, req.stage, req.updatedText], [true, '要件の本文', 'requirements', '10/17 10:05']);
    const done = entryOf(view, '99_summary.md');
    assert.deepEqual([done.ready, done.text, done.updatedText], [true, '終わり', DASH]);
    assert.equal(entryOf(view, '02_design.md').ready, false);
  });
}

// ---- AC-72：旧形（文字だけ）の写しと、壊れた値 ----

test('D0025-AC-72: 今の形の写し（成果物が中身の文字だけ）は、「ある」「まだない」が今までと同じに決まる（今のまま通る。守る）', () => {
  const view = viewOf({ '00_input.md': 'メモ', '01_requirements.md': '要件', '02_design.md': '  \n', '03_red_tests.md': '' }, { stateJson: stateJson({}) });
  assert.deepEqual(view.artifacts.map((a) => [a.name, a.ready]), [
    ['00_input.md', true], ['01_requirements.md', true], ['02_design.md', false], ['03_red_tests.md', false],
    ['04_implementation.md', false], ['05_test_report.md', false], ['99_summary.md', false],
  ]);
});

test('D0025-AC-72: 今の形の写しでは、時計があっても updatedText は「—」、切れた印は偽で、text は中身の文字', () => {
  const view = viewOf({ '00_input.md': 'メモ', '01_requirements.md': '要件' }, { stateJson: stateJson({}) }, { nowMs: T_VALID, localOffsetMin: 540 });
  for (const name of ['00_input.md', '01_requirements.md']) {
    const row = entryOf(view, name);
    assert.deepEqual([row.ready, row.cut, row.updatedText], [true, false, DASH], name);
  }
  assert.equal(entryOf(view, '01_requirements.md').text, '要件');
});

test('D0025-AC-72: 旧形の文字と新しい形（同じ text）で、全行の「ある」「まだない」が同じになる', () => {
  const texts: Record<string, string> = { '00_input.md': 'メモ', '01_requirements.md': '', '02_design.md': ' \n', '03_red_tests.md': '　x', '99_summary.md': '終わり' };
  const oldForm = build(texts, defsOf(null));
  const newForm = build(Object.fromEntries(Object.entries(texts).map(([k, v]) => [k, { text: v }])), defsOf(null));
  assert.deepEqual(newForm.map((e) => [e.name, e.ready]), oldForm.map((e) => [e.name, e.ready]));
  assert.deepEqual(newForm.map((e) => e.ready), [true, false, false, true, false, false, true]);
});

const ARTIFACT_FILE_ROWS: readonly (readonly [string, unknown, ArtifactFileLike | null])[] = [
  ['文字', 'abc', { text: 'abc', mtimeMs: null, cut: false }],
  ['空の文字', '', { text: '', mtimeMs: null, cut: false }],
  ['text だけのオブジェクト', { text: 'a' }, { text: 'a', mtimeMs: null, cut: false }],
  ['text・mtimeMs・cut を持つオブジェクト', { text: 'a', mtimeMs: 1_760_000_000_000, cut: true }, { text: 'a', mtimeMs: 1_760_000_000_000, cut: true }],
  ['mtimeMs が文字', { text: 'a', mtimeMs: '1760000000000' }, { text: 'a', mtimeMs: null, cut: false }],
  ['mtimeMs が負', { text: 'a', mtimeMs: -1 }, { text: 'a', mtimeMs: null, cut: false }],
  ['mtimeMs が 0', { text: 'a', mtimeMs: 0 }, { text: 'a', mtimeMs: null, cut: false }],
  ['mtimeMs が NaN', { text: 'a', mtimeMs: Number.NaN }, { text: 'a', mtimeMs: null, cut: false }],
  ['mtimeMs が無限大', { text: 'a', mtimeMs: Number.POSITIVE_INFINITY }, { text: 'a', mtimeMs: null, cut: false }],
  ['mtimeMs が null', { text: 'a', mtimeMs: null }, { text: 'a', mtimeMs: null, cut: false }],
  ['cut が true 以外の真の値（1）', { text: 'a', cut: 1 }, { text: 'a', mtimeMs: null, cut: false }],
  ['cut が "true"（文字）', { text: 'a', cut: 'true' }, { text: 'a', mtimeMs: null, cut: false }],
  ['null', null, null],
  ['undefined', undefined, null],
  ['数', 5, null],
  ['真偽', true, null],
  ['空の配列', [], null],
  ['文字の配列', ['a'], null],
  ['関数', () => 'a', null],
  ['text を持つ関数', Object.assign(() => 'a', { text: 'a' }), null],
  ['text の無いオブジェクト', {}, null],
  ['text が数', { text: 5 }, null],
  ['text が null', { text: null }, null],
  ['text が配列', { text: ['a'] }, null],
  ['text が原型から来るオブジェクト', Object.create({ text: 'a' }), null],
];

for (const [label, value, expected] of ARTIFACT_FILE_ROWS) {
  test(`D0025-AC-72: artifactFileOf は ${label} を ${expected === null ? 'null' : '{ text, mtimeMs, cut } に正規化'} にする（例外を出さない）`, async () => {
    const { artifactFileOf } = await art();
    assert.deepEqual(artifactFileOf(value), expected);
  });
}

test('D0025-AC-72: artifactFileOf は渡された値（凍結したもの）を書き換えず、正規化した結果を返す', async () => {
  const { artifactFileOf } = await art();
  const given = Object.freeze({ text: 'a', mtimeMs: 1_760_000_000_000, cut: true });
  assert.deepEqual(artifactFileOf(given), { text: 'a', mtimeMs: 1_760_000_000_000, cut: true });
  assert.deepEqual(given, { text: 'a', mtimeMs: 1_760_000_000_000, cut: true });
});

const WEIRD_VALUES: readonly (readonly [string, unknown])[] = [
  ['数', 5],
  ['null', null],
  ['真偽', true],
  ['配列', ['メモ']],
  ['text が数のオブジェクト', { text: 5 }],
  ['関数', () => 'メモ'],
];

for (const [label, value] of WEIRD_VALUES) {
  test(`D0025-AC-72: 写しの項目が ${label} でも、isArtifactReady は例外を出さず偽で、成果物の行は「まだない」になる`, () => {
    assert.equal(isReady(value), false);
    const rows = build({ '01_requirements.md': value }, [{ name: '01_requirements.md', label: '要件定義書' }]);
    assert.deepEqual([rows[0]?.ready, rows[0]?.text, rows[0]?.updatedText], [false, '', DASH]);
  });
}

for (const [label, bad] of BAD_MTIMES.filter(([l]) => l !== 'undefined（項目なし）')) {
  test(`D0025-AC-72: 更新時刻が ${label} の写しでも、図の状態の組み立て全体が例外を出さず、時刻は「—」・中身は出る`, () => {
    const view = viewOf({ '00_input.md': { text: 'メモ', mtimeMs: bad }, '01_requirements.md': { text: '要件', mtimeMs: bad } }, { stateJson: stateJson({}) }, { nowMs: T_VALID, localOffsetMin: 540 });
    for (const name of ['00_input.md', '01_requirements.md']) {
      const row = entryOf(view, name);
      assert.deepEqual([row.ready, row.updatedText], [true, DASH], name);
    }
    assert.equal(inputStatus(view), 'done');
  });
}

// 写しを直に読む 2 か所（図の要件メモの節 inputStatus・記録なしの noRecords）：新旧どちらの形でも例外を出さず、同じ入力の判定が同じになる

const INPUT_ROWS: readonly (readonly [string, unknown, string, boolean])[] = [
  // [ラベル, 00_input.md の項目, 図の要件メモの節の状態, 記録なしの表示が出るか（state.json もログも無い写しで）]
  ['文字（中身あり）', 'メモ', 'done', false],
  ['新しい形（中身あり）', { text: 'メモ', mtimeMs: T_VALID, cut: false }, 'done', false],
  ['新しい形（切れている・先頭は中身あり）', { text: 'メモ', cut: true }, 'done', false],
  ['空の文字', '', 'pending', false],
  ['新しい形（空）', { text: '' }, 'pending', false],
  ['空白だけの文字', ' \n\t', 'pending', false],
  ['新しい形（空白だけ・切れている）', { text: ' \n\t', cut: true }, 'pending', false],
  ['数', 5, 'pending', false],
  ['null', null, 'pending', false],
  ['text が数のオブジェクト', { text: 5 }, 'pending', false],
];

for (const [label, value, status, noRecords] of INPUT_ROWS) {
  const keep = typeof value === 'string' ? '（今のまま通る。守る）' : '';
  test(`D0025-AC-72: 00_input.md が ${label} の写しは、図の要件メモの節が ${status}・記録なしの表示は${noRecords ? '出る' : '出ない（項目があるので）'}${keep}`, () => {
    const view = viewOf({ '00_input.md': value });
    assert.equal(inputStatus(view), status);
    assert.equal(view.noRecords !== null, noRecords);
  });
}

test('D0025-AC-72: 写しに 00_input.md の項目が無い（symlink のとき）と、図の要件メモの節は「まだ」で、ほかの成果物があっても記録なしの表示が出る（state.json もログも無いとき）', () => {
  const view = viewOf({ '01_requirements.md': { text: '要件' } });
  assert.equal(inputStatus(view), 'pending');
  assert.notEqual(view.noRecords, null);
  assert.equal(entryOf(view, '00_input.md').ready, false);
});

test('D0025-AC-72: 写しに 00_input.md の項目が無くても、state.json があれば記録なしの表示は出ない（要件メモの節は「まだ」のまま）', () => {
  const view = viewOf({ '01_requirements.md': { text: '要件' } }, { stateJson: stateJson({ runs: [requirementsDone] }) });
  assert.equal(inputStatus(view), 'pending');
  assert.equal(view.noRecords, null);
});

test('D0025-AC-72: 写しに 00_input.md の項目が無くても、名前の読めるログがあれば記録なしの表示は出ない（今のまま通る。守る）', () => {
  const view = viewOf({}, { stageLogs: [designLog] });
  assert.equal(inputStatus(view), 'pending');
  assert.equal(view.noRecords, null);
});

test('D0025-AC-72: パイプの依頼メモの節（buildPipeNodes）も、新旧どちらの形でも例外を出さず同じ状態になる', () => {
  const state = stateJson({ pipe: 'diagrams', stages: DIAGRAMS_STAGES });
  for (const [form, value] of [['文字', 'メモ'], ['新しい形', { text: 'メモ' }]] as const) {
    const view = viewOf({ '00_input.md': value }, { stateJson: state });
    assert.equal(inputStatus(view), 'done', form);
  }
  assert.equal(inputStatus(viewOf({ '00_input.md': { text: ' ' } }, { stateJson: state })), 'pending');
});

test('D0025-AC-72: 凍結した写し（書き換えると TypeError になる）を渡しても例外を出さず、写しを書き換えない', () => {
  const artifacts = Object.freeze({
    '00_input.md': Object.freeze({ text: 'メモ', mtimeMs: T_VALID, cut: false }),
    '01_requirements.md': Object.freeze({ text: '要件', mtimeMs: T_VALID, cut: true }),
  });
  const view = viewOf(artifacts, { stateJson: stateJson({}) }, { nowMs: T_VALID, localOffsetMin: 540 });
  assert.equal(entryOf(view, '01_requirements.md').cut, true);
  assert.deepEqual(artifacts['01_requirements.md'], { text: '要件', mtimeMs: T_VALID, cut: true });
});

test('D0025-AC-53: 同じ写し・同じ時計から作った成果物の一覧は、何度作っても等しい', () => {
  const artifacts = { '00_input.md': { text: 'メモ', mtimeMs: T_VALID }, '01_requirements.md': { text: '要件', mtimeMs: T_VALID + 60_000, cut: true } };
  const clock = { nowMs: T_VALID, localOffsetMin: 540 };
  const a = viewOf(artifacts, { stateJson: stateJson({}) }, clock).artifacts;
  const b = viewOf(artifacts, { stateJson: stateJson({}) }, clock).artifacts;
  assert.deepEqual(a, b);
});
