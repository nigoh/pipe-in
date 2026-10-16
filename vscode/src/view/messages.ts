// パネルとの受け渡しの形。
import { isPipeModel } from '../domain/pipeModel.ts';
import type { PipeModel } from '../domain/pipeModel.ts';

export type ToPanelMessage = { type: 'render'; html: string };
export type FromPanelMessage =
  | { type: 'ready' }
  | { type: 'openArtifact'; name: string }
  /** 見る実行を選ぶ（id は候補の id。候補にあるかは入口で確かめる） */
  | { type: 'selectRun'; id: string };

/** パネルから来た値を検める。形が違えば null。 */
export function parseWebviewMessage(value: unknown): FromPanelMessage | null {
  if (typeof value !== 'object' || value === null) return null;
  const msg = value as Record<string, unknown>;
  if (msg.type === 'ready') return { type: 'ready' };
  if (msg.type === 'openArtifact' && typeof msg.name === 'string') return { type: 'openArtifact', name: msg.name };
  if (msg.type === 'selectRun' && typeof msg.id === 'string') return { type: 'selectRun', id: msg.id };
  return null;
}

// ---- パイプ作図台のパネルとの受け渡し ----

export type ToEditorMessage =
  | { type: 'load'; model: PipeModel }
  | { type: 'saved'; written: string[]; errors: string[] }
  | { type: 'failed'; message: string };
export type FromEditorMessage = { type: 'ready' } | { type: 'save'; model: PipeModel };

/** 作図台のパネルから来た値を検める。形が違えば null（保存先は入口が決める。パネルから来た名前では決めない） */
export function parseEditorMessage(value: unknown): FromEditorMessage | null {
  if (typeof value !== 'object' || value === null) return null;
  const msg = value as Record<string, unknown>;
  if (msg.type === 'ready') return { type: 'ready' };
  if (msg.type === 'save' && isPipeModel(msg.model)) return { type: 'save', model: msg.model };
  return null;
}
