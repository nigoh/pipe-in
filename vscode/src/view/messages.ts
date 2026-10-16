// パネルとの受け渡しの形。

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
