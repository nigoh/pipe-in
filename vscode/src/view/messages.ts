// パネルとの受け渡しの形。
import { isPipeModel } from '../domain/pipeModel.ts';
import { checkReplyChoice } from '../domain/replyFile.ts';
import type { ReplyAction } from '../domain/replyFile.ts';
import type { PipeModel } from '../domain/pipeModel.ts';
import type { ExternalNotice } from '../domain/pipeExternal.ts';
import { isVersionId } from '../domain/pipeVersions.ts';
import type { VersionEntry } from '../domain/pipeVersions.ts';
import type { RunContext } from '../domain/runDecision.ts';
import { isRunKey } from '../domain/runs.ts';

export type ToPanelMessage =
  | { type: 'render'; html: string }
  /** 返事を書けなかった（D0079）。パネルは押す前の状態に戻す */
  | { type: 'replyRefused' };
export type FromPanelMessage =
  | { type: 'ready' }
  | { type: 'openArtifact'; name: string }
  /** 見る実行を選ぶ（id は実行の目印 <場所>|<id>。形はここで検め、一覧にあるかは入口で確かめる） */
  | { type: 'selectRun'; id: string }
  /** 確認待ちへの返事（D0079）。読むのは動作と、修正の依頼の直してほしい点だけ。場所・段・識別子はパネルから受け取らない */
  | { type: 'reply'; action: ReplyAction; feedback?: string };

/** パネルから来る返事の知らせ（合併から取り出す） */
export type ReplyMessage = Extract<FromPanelMessage, { type: 'reply' }>;

/** パネルから来た値を検める。形が違えば null。 */
export function parseWebviewMessage(value: unknown): FromPanelMessage | null {
  if (typeof value !== 'object' || value === null) return null;
  const msg = value as Record<string, unknown>;
  if (msg.type === 'ready') return { type: 'ready' };
  if (msg.type === 'openArtifact' && typeof msg.name === 'string') return { type: 'openArtifact', name: msg.name };
  if (msg.type === 'selectRun' && typeof msg.id === 'string' && isRunKey(msg.id)) return { type: 'selectRun', id: msg.id };
  if (msg.type === 'reply') {
    // 動作と直してほしい点だけを読む。ほかの鍵（stage・id・path など）は読まず、返す物に入れない
    const checked = checkReplyChoice(msg.action, msg.feedback);
    if (!checked.ok) return null;
    return checked.choice.action === 'revise'
      ? { type: 'reply', action: 'revise', feedback: checked.choice.feedback }
      : { type: 'reply', action: checked.choice.action };
  }
  return null;
}

// ---- パイプ作業台のパネルとの受け渡し ----

export type ToEditorMessage =
  /**
   * 開いた・開き直した。folder は保存先のフォルダ名（見せるだけ。保存先は入口が決める）。
   * savedNames は保存済みの段の name（指示文を開けるもの）。dirty は保存していない下書きを開き直したとき
   */
  | { type: 'load'; model: PipeModel; folder: string; savedNames: string[]; dirty?: boolean }
  | { type: 'saved'; written: string[]; errors: string[]; savedNames: string[] }
  | { type: 'failed'; message: string }
  /** 保存した版の一覧（新しい順） */
  | { type: 'versions'; list: VersionEntry[] }
  /** 選んだ版の中身 */
  | { type: 'version'; id: string; model: PipeModel }
  /** 費用の目安に使う今日（UTC の日付）と、前の実績（ドル。無ければ null）。開いたときに一度だけ送る（D0066） */
  | { type: 'estimateContext'; today: string; actualUsd: number | null }
  /** 外で書き換わったときの知らせ（D0065。型だけ。パネルは入口と同じ版で出る） */
  | ExternalNotice
  /** 「流す」を押してよいかの今の事実（D0078）。開いたとき・保存したとき・実行の始まりと終わり・設定が変わったときに入口が送る。パネルは検めてから使う */
  | ({ type: 'runContext' } & RunContext);
export type FromEditorMessage =
  | { type: 'ready' }
  | { type: 'save'; model: PipeModel }
  /** 保存していない変更があるか。あるときは、閉じたときに下書きとして残すための今の形も送る */
  | { type: 'state'; dirty: boolean; model?: PipeModel }
  /** 保存済みの段の指示文を開く（name は段の name。場所は入口が保存済みのモデルから決める） */
  | { type: 'openPrompt'; name: string }
  | { type: 'loadVersion'; id: string }
  /** 外で書き換わった帯での選び（読み込む／自分の変更を残す） */
  | { type: 'externalChoice'; choice: 'load' | 'keep' }
  /** 保存したパイプを流す（D0078）。パネルから来る値は依頼メモだけ。パイプのフォルダ・プロジェクト・コマンドは入口が決める */
  | { type: 'run'; text: string };

const STAGE_NAME = /^[a-z0-9][a-z0-9_-]*$/;

/** 作業台のパネルから来た値を検める。形が違えば null（保存先・開く先・読む版は入口が決める。パネルから来た値では場所を決めない） */
export function parseEditorMessage(value: unknown): FromEditorMessage | null {
  if (typeof value !== 'object' || value === null) return null;
  const msg = value as Record<string, unknown>;
  if (msg.type === 'ready') return { type: 'ready' };
  if (msg.type === 'save' && isPipeModel(msg.model)) return { type: 'save', model: msg.model };
  if (msg.type === 'state' && typeof msg.dirty === 'boolean') {
    if (msg.model === undefined) return { type: 'state', dirty: msg.dirty };
    return isPipeModel(msg.model) ? { type: 'state', dirty: msg.dirty, model: msg.model } : null;
  }
  if (msg.type === 'openPrompt' && typeof msg.name === 'string' && STAGE_NAME.test(msg.name)) return { type: 'openPrompt', name: msg.name };
  if (msg.type === 'loadVersion' && typeof msg.id === 'string' && isVersionId(msg.id)) return { type: 'loadVersion', id: msg.id };
  if (msg.type === 'externalChoice' && (msg.choice === 'load' || msg.choice === 'keep')) return { type: 'externalChoice', choice: msg.choice };
  if (msg.type === 'run' && typeof msg.text === 'string') return { type: 'run', text: msg.text };
  return null;
}
