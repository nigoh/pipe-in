// 確認用ページの、返事を受け付けている確認待ちの見本（D0079）。
// 見本の記録は tests/fixtures/ には足さない：確認待ちの見本（showcase_waiting）を一時フォルダに写し、ここの差し分け（patch）を当てて、行ごとの記録を作る。
// 行は、帯の出し分けの表（返事のボタン・pipe-in --review・record review・pipe-in-gen chat review・次を待っている・帯なし）を 1 つずつ見られるように並べる。
// 外から来た文字（段の表示名・文書名・パイプ名）を危ない文字にした行（hostile）も 1 つ持つ。手元の情報（絶対パス・名前・メールアドレス）は書かない。

/** 最初の待ちの識別子と、次の待ち（修正の依頼のあとの 2 回目の確認待ち）の識別子 */
export const REPLY_ID = 'a1b2c3d4e5';
export const REPLY_NEXT_ID = 'f0e1d2c3b4';
/** 最初の待ちを始めた時刻（確認待ちの見本の待ち始めと同じ）と、次の待ちを始めた時刻 */
export const REPLY_SINCE = '2026-10-17T10:02:15+00:00';
export const REPLY_NEXT_SINCE = '2026-10-17T10:02:45+00:00';
/** 見本の「今」は、最初の待ちを始めてから何秒後か */
export const REPLY_NOW_SEC = 40;

/** パイプの記録の見本の段（表示名つき）。 */
export const REPLY_PIPE_STAGES = [
  { name: 'survey', label: 'ソースの調査', output: '01_survey.md', review: true },
  { name: 'draw', label: '図を描く', output: '02_diagrams.md', review: true },
  { name: 'verify', label: '図とソースの突き合わせ', output: '03_verify.md', review: false },
];

/** 段の実行 1 回の記録（最小の形）。 */
export function sampleRun(stage: string): Record<string, unknown> {
  return { stage, session_id: null, is_error: false, subtype: 'success', result: '', cost_usd: 0.21, num_turns: 9, duration_sec: 48.0, seq: 1, attempt: null, note: '' };
}

const mark = (stage: string, since: string = REPLY_SINCE): Record<string, unknown> => ({ stage, id: REPLY_ID, since });
/** パイプの記録の見本の段と、最初の段の実行 1 回 */
const survey = (): Record<string, unknown> => ({ stages: REPLY_PIPE_STAGES, runs: [sampleRun('survey')] });

export interface ReplySample {
  /** 見本の行の名前（実行の目印の id と同じ。直下は 'dev'） */
  name: string;
  /** work_dir（または別の worktree の work_dir）の下の実行のフォルダ。直下は '' */
  folder: string;
  /** 別の worktree の行のとき、登録名とブランチ名 */
  worktree?: { name: string; branch: string };
  /** セッション名と ID（見本の題） */
  sessionName: string;
  sessionId: string;
  /** 時刻（started_at・updated_at・pending_review.since・段のログの at）をずらすミリ秒。直下の開発フローを最新にするため、ほかは負 */
  shiftMs: number;
  /** state.json の最上位の鍵を差し替える値 */
  patch: Record<string, unknown>;
  /** 足す文書（名前 → 中身） */
  files?: Record<string, string>;
}

const MIN = 60_000;

export const REPLY_SAMPLES: readonly ReplySample[] = [
  {
    name: 'dev',
    folder: '',
    sessionName: '返事を受け付ける確認待ち（開発フロー）',
    sessionId: '7f3c9a21-4b6e-4d0a-9c1e-2a8b5d0e6f13',
    shiftMs: 0,
    patch: { pending_review: null, reply_wait: mark('requirements') },
  },
  {
    name: 'reply-pipe',
    folder: 'reply-pipe',
    sessionName: '返事を受け付ける確認待ち（パイプ）',
    sessionId: '3a6f8e02-1d5b-4c97-a0e4-8b2c6d1f9a75',
    shiftMs: -5 * MIN,
    patch: { ...survey(), pipe: 'reply-pipe', pending_review: null, reply_wait: mark('survey') },
    files: { '01_survey.md': '# ソースの調査\n\n見本の調査結果です。\n' },
  },
  {
    name: 'pause-dev',
    folder: 'pause-dev',
    sessionName: '--pause で止めた開発フロー',
    sessionId: 'c5b0e7a9-2f4d-4a61-9e3c-6d8f1b2a0c57',
    shiftMs: -10 * MIN,
    patch: {},
  },
  {
    name: 'pause-pipe',
    folder: 'pause-pipe',
    sessionName: '--pause で止めたパイプ',
    sessionId: '0d8a3c6f-7e1b-4b25-a9d0-4f6e2c8b1a93',
    shiftMs: -15 * MIN,
    patch: {
      ...survey(),
      pipe: 'pause-pipe',
      pending_review: { stage: 'survey', doc: 'docs/pipeline/pause-pipe/01_survey.md', session_id: null, since: REPLY_SINCE },
    },
    files: { '01_survey.md': '# ソースの調査\n\n見本の調査結果です。\n' },
  },
  {
    name: 'slash',
    folder: 'slash',
    sessionName: '/pipe-in で流した開発フロー',
    sessionId: '9e1f6b4d-3c8a-4f07-b5e2-1a7d9c3e0b28',
    shiftMs: -20 * MIN,
    patch: { driver: 'pipe-dev' },
  },
  {
    name: 'chat',
    folder: 'chat',
    sessionName: '会話の中で流したパイプ',
    sessionId: 'b21e07c4-9a3f-4f8d-8e52-71c0d3a9b6e4',
    shiftMs: -25 * MIN,
    patch: {
      ...survey(),
      pipe: 'chat',
      driver: 'pipe-chat',
      usage_summary: { available: false, reason: '会話の中で流したので、使用量は取れません' },
      pending_review: { stage: 'survey', doc: 'docs/pipeline/chat/01_survey.md', session_id: null, since: REPLY_SINCE },
    },
    files: { '01_survey.md': '# ソースの調査\n\n見本の調査結果です。\n' },
  },
  {
    name: 'old',
    folder: 'old',
    sessionName: '古い本体の記録（印なし）',
    sessionId: 'e9d4512b-6c7a-4e1f-b3d8-05a2f7c9e118',
    shiftMs: -30 * MIN,
    patch: { pending_review: null },
  },
  {
    name: 'done',
    folder: 'done',
    sessionName: '終わった記録（印が残っている）',
    sessionId: '5d2b8f10-6a4c-4e39-8c71-0b9e3a7d2f64',
    shiftMs: -35 * MIN,
    patch: { pending_review: null, final: 'PASSED', reply_wait: mark('requirements') },
  },
  {
    name: 'archive',
    folder: 'archive/20261016-090000',
    sessionName: '前の実行（印が残っている）',
    sessionId: 'a1c4e7b9-3d28-4f56-9b0a-6e2d8c1f7a35',
    shiftMs: -24 * 60 * MIN,
    patch: { pending_review: null, reply_wait: mark('requirements') },
  },
  {
    name: 'worktree',
    folder: '',
    worktree: { name: 'feat-export', branch: 'feat/export-csv' },
    sessionName: '別の worktree の実行（印あり）',
    sessionId: '1b7d3f95-8c2e-4a60-b4d1-9e5a0c6f2d87',
    shiftMs: 0,
    patch: { pending_review: null, reply_wait: mark('requirements') },
  },
  {
    name: 'hostile',
    folder: 'hostile',
    sessionName: '危ない文字を含む見本 <b>"\'',
    sessionId: '6c0a9e3d-5b8f-4d12-a7c4-2f1e8b0d9a36',
    shiftMs: -40 * MIN,
    patch: {
      pipe: '<img src=x onerror=alert(1)>',
      stages: [{ name: 'x', label: '<script>alert(1)</script>"\'<b>', output: '"><img src=x onerror=alert(1)>.md', review: true }],
      runs: [sampleRun('x')],
      pending_review: null,
      reply_wait: mark('x'),
    },
  },
];
