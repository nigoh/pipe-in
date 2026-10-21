// テストの補助：止まっているかもしれない実行の印（D0021）の、段のログに更新時刻（mtimeMs）を付けた記録の写し。
// 時刻は liveFixtures.ts の BASE_MS からの相対。「今」は clockAt(0) ＝ BASE_MS（nowSec を渡す補助は clockAt(nowSec)）。
// 本物の時計・ファイルには触れない。テスト先行のときは項目（mtimeMs・previous・quietSec）が型に無かったので、写しは WorkDirSnapshot に広げて返す（実装後は型に入っているが、同じ作りで通る）
// （型検査は実装の段で緑にする。ここの as は、その項目が型に入るまでのつなぎ）。
//
// ■ export の一覧と、使う AC（Dnnnn は D0021）
//
// 【定数】
//   STALE_AFTER_SEC = 600         目安（10 分）。AC-11・13・14・45・52・54 ほか
//   QUIET_OVER_SEC = 612          目安を 12 秒越えた更新なしの秒（staleSnapshot の既定）
//   QUIET_SOON_SEC = 595          目安の 5 秒手前（AC-14・40）
//   ANCIENT_MS                    1980-01-01 00:00:00 UTC（AC-48）
//   HOSTILE                       '<script>alert("x")</script>'（AC-50。< と " を含む）
//   LOG_REQUIREMENTS / LOG_DESIGN  '01_requirements.jsonl' / '02_design.jsonl'（withMtimes で名前を指すとき）
//
// 【表（表を回すテストに使う）】
//   FINAL_VALUES                  AC-46：PASSED・TEST_FAILED・STAGE_ERROR・STOPPED_BY_HUMAN・BLOCKED
//   BAD_MTIME_VALUES              AC-36：[ラベル, 壊れた mtimeMs] の並び（文字・数の文字・NaN・無限大・負・0・真偽・オブジェクト・配列）。どれも validMtime で null
//   BROKEN_STATE_KINDS            AC-49：'missing'・'broken'・'array'・'number'・'string'
//   OLD_SHAPE_KINDS               AC-35：'noAt'・'noStartedAt'・'noStages'
//   NO_MTIME_KINDS                AC-06：'absent'・'null'・'string'・'nan'（動いているログの mtimeMs が読めない形。対照は 'number'）
//   BROKEN_LOG_KINDS              AC-36：'garbage'・'empty'・'noPrompt'・'truncated'
//
// 【時刻を付ける道具】
//   mtimeAgo(agoSec, nowSec = 0)  「今」の agoSec 秒前の更新時刻（整数のミリ秒）。「今」＝ BASE_MS + nowSec 秒
//   withMtimes(snap, { ファイル名: 値 })  写しの各ログに mtimeMs を付けた写し。値は何でもよい（null・文字・NaN も）。
//                                 指定の無いログ・値が undefined のログには付けない（＝ mtimeMs の項目が無い）
//   withAllMtimes(snap, 値)       全ログに同じ mtimeMs を付ける
//   withPrevious(snap)            previous: true を付ける（AC-47。archive/ の前の実行の写し）
//
// 【写し】どれも「動いている開発フロー」が土台（liveFixtures の runningSnapshot）。別に書いたものは各行に。
//   staleSnapshot({ quietSec = 612, previous?, final?, omitAt?, at?, startedAt? })
//        動いている写し。ログは 02_design.jsonl（Prompt のみ・結果の行なし）が 1 つ。その mtimeMs ＝ 「今」の quietSec 秒前。
//        quietSec は小数でもよい（83.9 → 「今」から 83900ms 前。view.quietSec は 83）。
//        previous: true → 写しに previous: true（AC-47）。
//        final を渡す → state.json の final を入れる。ログは結果の行の無い途中のまま（AC-46。対照は final を渡さない同じ呼び出し）。
//        omitAt: true → Prompt に at が無い（AC-35 の at なし、AC-04 の古い記録）。at / startedAt を渡すと runningSnapshot にそのまま渡る。
//        at の既定は BASE_AT（runningSnapshot と同じ）。「経過 ≥ 更新なしの時間」の辻褄は合わせていない。必要なら at / startedAt を渡す
//        使う AC：04 ①（quietSec: 83.9 → view.quietSec は 83）・07・08・11〜23・26〜34・46・47・52・54 ほか、「動いていて印が出る」側の対照
//        （未来の時刻は futureSnapshot、再開・放置は resumedSnapshot・abandonedSnapshot、時系列は staleGanttSnapshot を使う）
//   resumedSnapshot()            AC-44。state.json の runs は 1・2。ログは 05_implement_1.jsonl（Prompt のみ・mtimeMs は 3 日前）と
//        03_red.jsonl（Prompt のみ・5 秒前）。動いている段の判定は通し番号が大きい 05_implement_1（実装 1 回目）のまま。
//        view.quietSec は 5（全ログの最新）。定数 RESUMED_OLD_AGO_SEC（3 日）・RESUMED_NEW_AGO_SEC（5）
//   abandonedSnapshot({ latestAgoSec = 700, otherAgoSec = 900, runningIsLatest = false })
//        AC-45。ログは 01_requirements.jsonl（終わった）と 02_design.jsonl（動いている）の 2 つ。
//        既定では、終わった方が latestAgoSec 前、動いている方が otherAgoSec 前（latestAgoSec ≤ otherAgoSec にする）。
//        runningIsLatest: true なら入れ替わる（動いている方が latestAgoSec 前）。
//        view.quietSec ＝ latestAgoSec（全ログの最新。動いているログ自身の otherAgoSec ではない）。
//        1 つだけ新しい版は abandonedSnapshot({ latestAgoSec: 100 })（quietSec 100 → 目安の手前で印が付かない）
//   unknownStageSnapshot({ quietSec = 612 })
//        AC-04 ③。段の一覧に無い名前（mystery）の動いているログ 02_mystery.jsonl だけ。節は作られない。
//        それでも view.quietSec・動いている帯の quietSec・行の quietSec が同じ数（quietSec）になる
//   brokenStateSnapshot(kind, { quietSec = 612 })
//        AC-49。ログは staleSnapshot({ quietSec }) と同じで、state.json だけが無い（null）／壊れた JSON／配列／数／文字。
//        どれも quietSec は null。対照は staleSnapshot({ quietSec })
//   ancientSnapshot()            AC-48。全ログの mtimeMs が ANCIENT_MS。quietSec は 604800（7 日で頭打ち）、時間の文字は 168:00:00
//   oldShapeSnapshot(kind, { quietSec = 612 })
//        AC-35。ログに更新時刻があり、state.json が読める。土台は stages つき（開発の 5 段）・started_at つき・Prompt に at つきの新しい形で、
//        'noAt'＝Prompt に at が無い、'noStartedAt'＝started_at の項目が無い、'noStages'＝stages の項目が無い。
//        節・行・バッジ・知らせには印が出る。矢印と時系列の帯が出ないのは Prompt に at が無い記録だけ（決定の記録 D0021）
//        （noAt は矢印・帯が出ない／noStartedAt と noStages は出る）
//   badMtimeSnapshot(value)      AC-36。全ログ（動いている 1 つ）の mtimeMs に value を入れた写し。印は出ない。対照は staleSnapshot()
//   brokenLogSnapshot(kind)      AC-36。mtimeMs は数（612 秒前）で、ログの中身が壊れている。
//        'garbage'・'empty'・'noPrompt' は動いているログが無い扱い（quietSec は null、例外なし）。
//        'truncated' は Prompt の行は読めて途中の行が切れている → 動いているログのまま（quietSec は 612、例外なし）
//   futureSnapshot()             AC-05。全ログの mtimeMs が「今」の 5 分先。quietSec は 0
//   noMtimeOnRunningSnapshot(kind = 'absent', { runningAgoSec = 612, otherAgoSec = 10 })
//        AC-06。ログは 01_requirements.jsonl（終わった・10 秒前の mtimeMs あり）と 02_design.jsonl（動いている）。
//        動いているログの mtimeMs は kind で、'absent'＝項目なし・'null'・'string'・'nan'。ほかのログの時刻・Prompt の at・updated_at はある。
//        どの kind も quietSec は null（ほかのログで代わりにしない）。対照は kind = 'number'（動いているログも 612 秒前）→ quietSec は 10（全ログの最新）
//   hostileSnapshot({ quietSec = 612 })
//        AC-50。パイプ（diagrams）の動いている写し。セッション名（state.json の name）・段の表示名（stages の label）・
//        ログの文字（発言・ツールの対象）がすべて HOSTILE。印の要素の中身は固定の言葉と数字だけになるはず
//   staleGanttSnapshot({ nowSec = 1000, quietSec = 612, runningStartSec = 100, untimedRow = false })
//        AC-34・35・54 の時系列用。ganttSnapshot が土台：started_at ＝ BASE、終わった行 2 つ（要件定義 5〜35 秒・設計 60〜80 秒）と
//        動いている行（red・seq 3）が Prompt の at ＝ BASE から runningStartSec 秒後。全ログの mtimeMs ＝ nowSec の quietSec 秒前。
//        見るときの「今」は clockAt(nowSec)。帯は runningStartSec 〜 nowSec（既定は全体の 90%）。
//        runningStartSec を null にすると動いている行の at が無い（帯の無い行 run: null）。untimedRow: true で設計の行の at が無い（帯の無い行）
//
// 【一覧の行・組み立て】
//   summarizeInput(snap, 上書き)   summarizeRun に渡す入力（key 'here|'・id ''・別の worktree でない。previous は snap.previous から）
//   staleParts(snap, nowSec = 0, 一覧の上書き)  { view, row, list }：同じ写し・同じ「今」から作った図の状態・summarizeRun の行・その 1 行の一覧
//                                  （renderPanelHtml(view, nonce, list, 目安) に渡す。AC-11・12・44・45・46 ほか）
//   staleRow(quietSec, 上書き)     動いている行（既定）に quietSec を入れた RunRow（AC-27〜29・50。state を上書きすれば確認待ちなど）
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { PipelineView, WorkDirSnapshot } from '../domain/pipelineView.ts';
import { summarizeRun } from '../domain/runList.ts';
import type { RunListView, RunRow, SummarizeInput } from '../domain/runList.ts';
import {
  DEV_STAGES,
  DIAGRAMS_STAGES,
  assistantText,
  assistantTool,
  logText,
  promptLine,
  resultLine,
  snapshot,
  stageRunEntry,
  stateJson,
} from './fixtures.ts';
import { atSec, ganttSnapshot, naiveAtSec } from './ganttFixtures.ts';
import { BASE_AT, BASE_MS, RUNNING_UPDATED_AT, STARTED_AT, clockAt, runningSnapshot } from './liveFixtures.ts';
import { listView, row } from './runListFixtures.ts';

// ---- 定数 -------------------------------------------------------------------------

export const STALE_AFTER_SEC = 600;
export const QUIET_OVER_SEC = 612;
export const QUIET_SOON_SEC = 595;
export const ANCIENT_MS = Date.UTC(1980, 0, 1, 0, 0, 0);
export const HOSTILE = '<script>alert("x")</script>';
export const LOG_REQUIREMENTS = '01_requirements.jsonl';
export const LOG_DESIGN = '02_design.jsonl';
export const RESUMED_OLD_AGO_SEC = 3 * 24 * 3600;
export const RESUMED_NEW_AGO_SEC = 5;

export const FINAL_VALUES = ['PASSED', 'TEST_FAILED', 'STAGE_ERROR', 'STOPPED_BY_HUMAN', 'BLOCKED'] as const;

/** 壊れた mtimeMs。どれも validMtime（有限で 0 より大きい数だけ通す）で null になる。 */
export const BAD_MTIME_VALUES: readonly (readonly [string, unknown])[] = [
  ['文字', 'abc'],
  ['数の文字', '1760000000000'],
  ['NaN', Number.NaN],
  ['無限大', Number.POSITIVE_INFINITY],
  ['負', -1],
  ['0', 0],
  ['真偽', true],
  ['オブジェクト', { ms: 1760000000000 }],
  ['配列', [1760000000000]],
];

export const BROKEN_STATE_KINDS = ['missing', 'broken', 'array', 'number', 'string'] as const;
export type BrokenStateKind = (typeof BROKEN_STATE_KINDS)[number];

export const OLD_SHAPE_KINDS = ['noAt', 'noStartedAt', 'noStages'] as const;
export type OldShapeKind = (typeof OLD_SHAPE_KINDS)[number];

export const NO_MTIME_KINDS = ['absent', 'null', 'string', 'nan'] as const;
export type NoMtimeKind = (typeof NO_MTIME_KINDS)[number] | 'number';

export const BROKEN_LOG_KINDS = ['garbage', 'empty', 'noPrompt', 'truncated'] as const;
export type BrokenLogKind = (typeof BROKEN_LOG_KINDS)[number];

// ---- 時刻を付ける道具 ------------------------------------------------------------------

/** 「今」（BASE_MS + nowSec 秒）の agoSec 秒前の更新時刻。整数のミリ秒にそろえる（83.9 秒前 → 83900ms 前）。 */
export function mtimeAgo(agoSec: number, nowSec = 0): number {
  return BASE_MS + Math.round((nowSec - agoSec) * 1000);
}

/** 項目（mtimeMs・previous）を足した写しを WorkDirSnapshot として返す（テスト先行のときは型に無かったので広げる。実装後は型に入っている）。 */
function asSnapshot(value: object): WorkDirSnapshot {
  return value as unknown as WorkDirSnapshot;
}

/** 写しの各ログに mtimeMs を付ける。指定の無いログと、値が undefined のログには付けない。 */
export function withMtimes(snap: WorkDirSnapshot, mtimes: Readonly<Record<string, unknown>>): WorkDirSnapshot {
  const stageLogs = snap.stageLogs.map((log) => {
    const value = Object.hasOwn(mtimes, log.fileName) ? mtimes[log.fileName] : undefined;
    return value === undefined ? { ...log } : { ...log, mtimeMs: value };
  });
  return asSnapshot({ ...snap, stageLogs });
}

/** 全ログに同じ mtimeMs を付ける（値が undefined なら付けない）。 */
export function withAllMtimes(snap: WorkDirSnapshot, value: unknown): WorkDirSnapshot {
  return withMtimes(snap, Object.fromEntries(snap.stageLogs.map((log) => [log.fileName, value])));
}

/** archive/ の前の実行の写し（previous: true）。 */
export function withPrevious(snap: WorkDirSnapshot): WorkDirSnapshot {
  return asSnapshot({ ...snap, previous: true });
}

/** state.json の項目を足す・直す。値が undefined の項目は消える（JSON にしたとき項目ごと無い）。 */
function patchState(snap: WorkDirSnapshot, patch: Readonly<Record<string, unknown>>): WorkDirSnapshot {
  const data = JSON.parse(snap.stateJson ?? '{}') as Record<string, unknown>;
  return asSnapshot({ ...snap, stateJson: JSON.stringify({ ...data, ...patch }) });
}

// ---- 写し ---------------------------------------------------------------------------

/** 動いている写し。全ログの mtimeMs ＝ 「今」の quietSec 秒前。 */
export function staleSnapshot(
  p: { quietSec?: number; previous?: boolean; final?: string | null; omitAt?: boolean; at?: unknown; startedAt?: unknown } = {},
): WorkDirSnapshot {
  const quietSec = p.quietSec ?? QUIET_OVER_SEC;
  let snap = withAllMtimes(runningSnapshot({ omitAt: p.omitAt, at: p.at, startedAt: p.startedAt }), mtimeAgo(quietSec));
  if (p.final !== undefined && p.final !== null) snap = patchState(snap, { final: p.final });
  return p.previous === true ? withPrevious(snap) : snap;
}

/** 通し番号の大きい古い途中のログと、再開後の新しいログが並ぶ写し（AC-44）。 */
export function resumedSnapshot(): WorkDirSnapshot {
  const oldLog = {
    fileName: '05_implement_1.jsonl',
    text: logText([promptLine('implement', atSec(-RESUMED_OLD_AGO_SEC)), assistantText('実装します')]),
  };
  const newLog = {
    fileName: '03_red.jsonl',
    text: logText([promptLine('red', atSec(-RESUMED_NEW_AGO_SEC)), assistantText('テストを書きます')]),
  };
  const snap = snapshot({
    stateJson: stateJson({
      runs: [stageRunEntry({ stage: 'requirements', seq: 1, durationSec: 30 }), stageRunEntry({ stage: 'design', seq: 2, durationSec: 40 })],
      startedAt: naiveAtSec(-4 * 24 * 3600),
      updatedAt: naiveAtSec(-RESUMED_NEW_AGO_SEC),
    }),
    stageLogs: [newLog, oldLog],
    artifacts: { '00_input.md': 'メモ' },
  });
  return withMtimes(snap, {
    [oldLog.fileName]: mtimeAgo(RESUMED_OLD_AGO_SEC),
    [newLog.fileName]: mtimeAgo(RESUMED_NEW_AGO_SEC),
  });
}

/** 全ログが古い（目安より前の）放置された写し。1 つだけ新しい版は latestAgoSec を小さくする（AC-45）。 */
export function abandonedSnapshot(p: { latestAgoSec?: number; otherAgoSec?: number; runningIsLatest?: boolean } = {}): WorkDirSnapshot {
  const latest = p.latestAgoSec ?? 700;
  const other = p.otherAgoSec ?? 900;
  const oldest = Math.max(latest, other);
  const requirementsAgo = p.runningIsLatest === true ? other : latest;
  const designAgo = p.runningIsLatest === true ? latest : other;
  const snap = snapshot({
    stateJson: stateJson({
      runs: [stageRunEntry({ stage: 'requirements', seq: 1, durationSec: 30 })],
      startedAt: naiveAtSec(-(oldest + 300)),
      updatedAt: naiveAtSec(-latest),
    }),
    stageLogs: [
      { fileName: LOG_REQUIREMENTS, text: logText([promptLine('requirements', atSec(-(oldest + 240))), assistantText('書いた'), resultLine()]) },
      { fileName: LOG_DESIGN, text: logText([promptLine('design', atSec(-(oldest + 60))), assistantText('設計します')]) },
    ],
    artifacts: { '00_input.md': 'メモ' },
  });
  return withMtimes(snap, { [LOG_REQUIREMENTS]: mtimeAgo(requirementsAgo), [LOG_DESIGN]: mtimeAgo(designAgo) });
}

/** 段の一覧に無い名前の動いているログ（節が作られない）だけを持つ写し（AC-04 ③）。 */
export function unknownStageSnapshot(p: { quietSec?: number } = {}): WorkDirSnapshot {
  const base = runningSnapshot();
  const snap: WorkDirSnapshot = {
    ...base,
    stageLogs: [{ fileName: '02_mystery.jsonl', text: logText([promptLine('mystery', BASE_AT), assistantText('調べます')]) }],
  };
  return withAllMtimes(snap, mtimeAgo(p.quietSec ?? QUIET_OVER_SEC));
}

const BROKEN_STATE_TEXT: Readonly<Record<BrokenStateKind, string | null>> = {
  missing: null,
  broken: '{壊れた',
  array: '[]',
  number: '42',
  string: '"abc"',
};

/** ログは staleSnapshot と同じで、state.json が無い・壊れている写し（AC-49）。 */
export function brokenStateSnapshot(kind: BrokenStateKind, p: { quietSec?: number } = {}): WorkDirSnapshot {
  const snap = staleSnapshot({ quietSec: p.quietSec });
  return asSnapshot({ ...snap, stateJson: BROKEN_STATE_TEXT[kind] });
}

/** 更新時刻が 1980 年の写し（AC-48）。 */
export function ancientSnapshot(): WorkDirSnapshot {
  return withAllMtimes(runningSnapshot(), ANCIENT_MS);
}

/** 古い形の記録（AC-35）。土台は stages・started_at・Prompt の at が全部ある形で、kind の 1 つだけを無くす。 */
export function oldShapeSnapshot(kind: OldShapeKind, p: { quietSec?: number } = {}): WorkDirSnapshot {
  const modern = patchState(runningSnapshot({ omitAt: kind === 'noAt' }), { stages: DEV_STAGES });
  let snap = modern;
  if (kind === 'noStartedAt') snap = patchState(modern, { started_at: undefined });
  if (kind === 'noStages') snap = patchState(modern, { stages: undefined });
  return withAllMtimes(snap, mtimeAgo(p.quietSec ?? QUIET_OVER_SEC));
}

/** 全ログの mtimeMs に壊れた値を入れた写し（AC-36）。 */
export function badMtimeSnapshot(value: unknown): WorkDirSnapshot {
  return withAllMtimes(runningSnapshot(), value);
}

const BROKEN_LOG_TEXT: Readonly<Record<BrokenLogKind, string>> = {
  garbage: '{壊れた\n\u0001\u0002 not json\n[1, 2\n',
  empty: '',
  noPrompt: logText([assistantText('Prompt の行が無い')]),
  truncated: `${promptLine('design', BASE_AT)}\n{"_type":"AssistantMessage","content":[{"te`,
};

/** mtimeMs は数（612 秒前）で、ログの中身が壊れている写し（AC-36）。 */
export function brokenLogSnapshot(kind: BrokenLogKind): WorkDirSnapshot {
  const base = runningSnapshot();
  const snap: WorkDirSnapshot = { ...base, stageLogs: [{ fileName: LOG_DESIGN, text: BROKEN_LOG_TEXT[kind] }] };
  return withAllMtimes(snap, mtimeAgo(QUIET_OVER_SEC));
}

/** 更新時刻が「今」の 5 分先の写し（AC-05。quietSec は 0）。 */
export function futureSnapshot(): WorkDirSnapshot {
  return withAllMtimes(runningSnapshot(), mtimeAgo(-300));
}

/** 動いているログだけ mtimeMs が読めず、ほかのログには時刻がある写し（AC-06）。kind = 'number' は対照。 */
export function noMtimeOnRunningSnapshot(
  kind: NoMtimeKind = 'absent',
  p: { runningAgoSec?: number; otherAgoSec?: number } = {},
): WorkDirSnapshot {
  const base = runningSnapshot();
  const snap: WorkDirSnapshot = {
    ...base,
    stageLogs: [
      { fileName: LOG_REQUIREMENTS, text: logText([promptLine('requirements', atSec(-1000)), assistantText('書いた'), resultLine()]) },
      ...base.stageLogs,
    ],
  };
  const runningValue: Readonly<Record<NoMtimeKind, unknown>> = {
    absent: undefined,
    null: null,
    string: 'abc',
    nan: Number.NaN,
    number: mtimeAgo(p.runningAgoSec ?? QUIET_OVER_SEC),
  };
  return withMtimes(snap, { [LOG_REQUIREMENTS]: mtimeAgo(p.otherAgoSec ?? 10), [LOG_DESIGN]: runningValue[kind] });
}

/** セッション名・段の表示名・ログの文字がすべて HOSTILE の、動いているパイプの写し（AC-50）。 */
export function hostileSnapshot(p: { quietSec?: number } = {}): WorkDirSnapshot {
  const stages = DIAGRAMS_STAGES.slice(0, 2).map((s) => ({ ...s, label: HOSTILE }));
  const snap = snapshot({
    stateJson: stateJson({
      runs: [stageRunEntry({ stage: 'survey', seq: 1, durationSec: 30 })],
      pipe: 'diagrams',
      name: HOSTILE,
      stages,
      startedAt: STARTED_AT,
      updatedAt: RUNNING_UPDATED_AT,
    }),
    stageLogs: [
      {
        fileName: '02_draw.jsonl',
        text: logText([promptLine('draw', BASE_AT), assistantText(HOSTILE), assistantTool('Bash', { command: HOSTILE })]),
      },
    ],
    artifacts: { '00_input.md': 'メモ' },
  });
  return withAllMtimes(snap, mtimeAgo(p.quietSec ?? QUIET_OVER_SEC));
}

/** 時系列用：動いている帯（red・seq 3）がある写し。見るときの「今」は clockAt(nowSec)。 */
export function staleGanttSnapshot(
  p: { nowSec?: number; quietSec?: number; runningStartSec?: number | null; untimedRow?: boolean } = {},
): WorkDirSnapshot {
  const nowSec = p.nowSec ?? 1000;
  const startSec = p.runningStartSec === undefined ? 100 : p.runningStartSec;
  const snap = ganttSnapshot({
    runs: [
      { stage: 'requirements', seq: 1, start: 5, durationSec: 30 },
      { stage: 'design', seq: 2, start: p.untimedRow === true ? undefined : 60, durationSec: 20 },
    ],
    running: { seq: 3, stage: 'red', start: startSec === null ? undefined : atSec(startSec) },
  });
  return withAllMtimes(snap, mtimeAgo(p.quietSec ?? QUIET_OVER_SEC, nowSec));
}

// ---- 一覧の行・組み立て ---------------------------------------------------------------

/** summarizeRun に渡す入力。previous は写しの previous から取る。 */
export function summarizeInput(snap: WorkDirSnapshot, overrides: Partial<SummarizeInput> = {}): SummarizeInput {
  return {
    key: 'here|',
    id: '',
    branch: null,
    other: false,
    memoHead: null,
    previous: (snap as { previous?: boolean }).previous === true,
    stateJson: snap.stateJson,
    stageLogs: snap.stageLogs,
    ...overrides,
  };
}

/** 同じ写し・同じ「今」から作った、図の状態・summarizeRun の行・その 1 行の一覧。 */
export function staleParts(
  snap: WorkDirSnapshot,
  nowSec = 0,
  listOverrides: Partial<RunListView> = {},
): { view: PipelineView; row: RunRow; list: RunListView } {
  const clock = clockAt(nowSec);
  const view = buildPipelineView(snap, clock);
  const runRow = summarizeRun(summarizeInput(snap), clock);
  return { view, row: runRow, list: listView([runRow], listOverrides) };
}

/** 動いている行（state を上書きすれば別の状態）に quietSec を入れた行。undefined なら項目を入れない。 */
export function staleRow(quietSec: number | null | undefined, overrides: Partial<RunRow> = {}): RunRow {
  return row({ ...overrides, ...(quietSec === undefined ? {} : { quietSec }) } as Partial<RunRow>);
}
