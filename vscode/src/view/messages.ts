// パネルとの受け渡しの形。
import { isPipeModel } from '../domain/pipeModel.ts';
import type { PipeModel } from '../domain/pipeModel.ts';
import { isVersionId } from '../domain/pipeVersions.ts';
import type { VersionEntry } from '../domain/pipeVersions.ts';
import { isRunKey } from '../domain/runs.ts';

export type ToPanelMessage = { type: 'render'; html: string };
export type FromPanelMessage =
  | { type: 'ready' }
  | { type: 'openArtifact'; name: string }
  /** 見る実行を選ぶ（id は実行の目印 <場所>|<id>。形はここで検め、一覧にあるかは入口で確かめる） */
  | { type: 'selectRun'; id: string };

/** パネルから来た値を検める。形が違えば null。 */
export function parseWebviewMessage(value: unknown): FromPanelMessage | null {
  if (typeof value !== 'object' || value === null) return null;
  const msg = value as Record<string, unknown>;
  if (msg.type === 'ready') return { type: 'ready' };
  if (msg.type === 'openArtifact' && typeof msg.name === 'string') return { type: 'openArtifact', name: msg.name };
  if (msg.type === 'selectRun' && typeof msg.id === 'string' && isRunKey(msg.id)) return { type: 'selectRun', id: msg.id };
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
  | { type: 'version'; id: string; model: PipeModel };
export type FromEditorMessage =
  | { type: 'ready' }
  | { type: 'save'; model: PipeModel }
  /** 保存していない変更があるか。あるときは、閉じたときに下書きとして残すための今の形も送る */
  | { type: 'state'; dirty: boolean; model?: PipeModel }
  /** 保存済みの段の指示文を開く（name は段の name。場所は入口が保存済みのモデルから決める） */
  | { type: 'openPrompt'; name: string }
  | { type: 'loadVersion'; id: string };

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
  return null;
}
