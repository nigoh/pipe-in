// 返事を受け付けている確認待ちの判断（D0079）。純粋な関数だけ（ファイル・時計・vscode に触れない）。
// 実行パネルに「承認・修正を依頼・中止」のボタンを出すか（canReply）、送ってから 30 秒たったか（isReplyStalled）、
// 約 5 秒ごとの読み直しを続けるか（isLive）を決める。
import type { PipelineView } from './pipelineView.ts';
import type { ReplyWaitMark } from './runRecord.ts';

export type { ReplyWaitMark } from './runRecord.ts';

/** ボタンを出す判断に要る値（記録の写しから buildPipelineView が作る） */
export interface ReplyOfferInput {
  mark: ReplyWaitMark | null;
  /** state.json の final（終わっていれば文字） */
  final: string | null;
  /** state.json に driver がある（/pipe-in や会話の道の記録） */
  hasDriver: boolean;
  /** state.json に pending_review がある（--pause や /pipe-in の記録） */
  hasPendingReview: boolean;
  /** 動いている段がある */
  running: boolean;
  /** archive/ の前の実行 */
  previous: boolean;
  /** 別の worktree の実行 */
  other: boolean;
}

/** reply.json が通常のファイルとして有るときの情報（更新時刻が読めなければ null） */
export interface ReplyFileInfo { mtimeMs: number | null }

/** 帯に出す、返事を受け付けている確認待ち */
export interface ReplyView {
  stage: string;
  label: string;
  /** 待ちの識別子 */
  id: string;
  /** 確認する文書のファイル名（stages[].output）。分からなければ '' */
  doc: string;
  /** 印の since から「今」まで。読めなければ null */
  waitingSec: number | null;
  /** reply.json が有る（送った） */
  sent: boolean;
  /** sent で、30 秒以上たった */
  stalled: boolean;
}

/** 送ってから、端末の pipe-in が止まっていないか確かめる案内を出すまで（ミリ秒） */
export const REPLY_STALL_MS = 30_000;

/**
 * 返事のボタンを出してよいか。7 つの条件がすべて合うときだけ真（文書は、終わりの 2 つを「いまの work_dir の実行である」の 1 つにまとめて 6 つと書く）：
 * 印がある・終わっていない・driver が無い・pending_review が無い・動いている段が無い・前の実行でない・別の worktree でない。
 */
export function canReply(input: ReplyOfferInput): boolean {
  return (
    input.mark !== null &&
    input.final === null &&
    !input.hasDriver &&
    !input.hasPendingReview &&
    !input.running &&
    !input.previous &&
    !input.other
  );
}

/** 送ってから 30 秒以上たったか。ファイルの更新時刻か「今」が数でない・今より先の更新時刻は偽（案内を出さない側に倒す）。 */
export function isReplyStalled(mtimeMs: number | null, nowMs: number | undefined): boolean {
  if (typeof mtimeMs !== 'number' || !Number.isFinite(mtimeMs)) return false;
  if (typeof nowMs !== 'number' || !Number.isFinite(nowMs)) return false;
  return nowMs - mtimeMs >= REPLY_STALL_MS;
}

/** 読み直しを続けるか：動いている・確認待ちの図、または返事を受け付けている図。 */
export function isLive(view: PipelineView): boolean {
  return view.gantt.live || (view.reply ?? null) !== null;
}
