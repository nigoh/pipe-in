// 返事のファイル（reply.json）の決まり（D0079）。
// 実行パネルのボタンから、端末で待っている pipe-in へ「承認・修正の依頼・中止」を返すための、ファイルの名前・版・上限と、
// 返事の中身（文字）を作る関数。本体（pipe_in/engine/reply.py）が読む形と同じ決まりで、共通の表 tests/fixtures/reply_file.json の同じ行で結ぶ。
// 長さはコードポイントで数える（UTF-16 の length では数えない）。純粋な関数だけ（ファイル・時計・vscode に触れない）。

export const REPLY_FILE_NAME = 'reply.json';
export const REPLY_VERSION = 1;
export const REPLY_ACTIONS = ['approve', 'revise', 'quit'] as const;
export type ReplyAction = (typeof REPLY_ACTIONS)[number];
/** 直してほしい点の長さの上限（コードポイント） */
export const REPLY_MAX_FEEDBACK = 1000;
/** ファイル全体の上限（バイト） */
export const REPLY_MAX_BYTES = 16384;

export type ReplyBuildReason =
  | 'bad_action'
  | 'bad_stage'
  | 'bad_id'
  | 'need_feedback'
  | 'feedback_not_allowed'
  | 'feedback_too_long'
  | 'bad_chars';
export type ReplyChoice = { action: 'approve' | 'quit' } | { action: 'revise'; feedback: string };
export type ReplyText = string & { readonly __brand: 'ReplyText' };

/** 段の名前の形（本体の STAGE_RE と同じ） */
export const REPLY_STAGE_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$/;
/** 待ちの識別子の形（10 文字の小文字の 16 進） */
export const REPLY_ID_RE = /^[0-9a-f]{10}$/;

/** 改行とタブ以外の制御文字・書式文字・サロゲート・行区切り・段落区切り */
const BAD_CHARS_RE = /(?![\n\t])[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u;

const isAction = (value: unknown): value is ReplyAction => typeof value === 'string' && (REPLY_ACTIONS as readonly string[]).includes(value);

/**
 * 動作と直してほしい点を検める。本体の parse_reply と同じ順（直してほしい点が文字でないときの理由の語だけ違う：ここは need_feedback、本体は bad_type）：
 * 動作 → （承認・中止に直してほしい点が付けば断る）→ 修正の依頼は「文字か → 使えない文字 → 前後の空白を取る → 空か → 長さ」。
 * 書き出す直してほしい点は、前後の空白を取ったあとの文字。
 */
export function checkReplyChoice(
  action: unknown,
  feedback: unknown,
): { ok: true; choice: ReplyChoice } | { ok: false; reason: ReplyBuildReason } {
  if (!isAction(action)) return { ok: false, reason: 'bad_action' };
  if (action !== 'revise') {
    if (feedback !== undefined) return { ok: false, reason: 'feedback_not_allowed' };
    return { ok: true, choice: { action } };
  }
  if (typeof feedback !== 'string') return { ok: false, reason: 'need_feedback' };
  if (BAD_CHARS_RE.test(feedback)) return { ok: false, reason: 'bad_chars' };
  const trimmed = feedback.trim();
  if (trimmed === '') return { ok: false, reason: 'need_feedback' };
  if (Array.from(trimmed).length > REPLY_MAX_FEEDBACK) return { ok: false, reason: 'feedback_too_long' };
  return { ok: true, choice: { action: 'revise', feedback: trimmed } };
}

/**
 * 返事の中身（文字）を作る。検める順は 動作 → 段 → 識別子 → 直してほしい点。
 * 鍵の順は version, stage, id, action, feedback。区切りの隙間と末尾の改行は付けない。
 */
export function buildReplyText(input: {
  action: unknown;
  stage: unknown;
  id: unknown;
  feedback?: unknown;
}): { ok: true; text: ReplyText } | { ok: false; reason: ReplyBuildReason } {
  if (!isAction(input.action)) return { ok: false, reason: 'bad_action' };
  if (typeof input.stage !== 'string' || !REPLY_STAGE_RE.test(input.stage)) return { ok: false, reason: 'bad_stage' };
  if (typeof input.id !== 'string' || !REPLY_ID_RE.test(input.id)) return { ok: false, reason: 'bad_id' };
  const checked = checkReplyChoice(input.action, input.feedback);
  if (!checked.ok) return checked;
  const body: Record<string, unknown> = { version: REPLY_VERSION, stage: input.stage, id: input.id, action: checked.choice.action };
  if (checked.choice.action === 'revise') body.feedback = checked.choice.feedback;
  return { ok: true, text: JSON.stringify(body) as ReplyText };
}
