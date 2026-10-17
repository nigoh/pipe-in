// 段：パイプラインの1工程。本体の段の名前に合わせる。
// 開発フローの段は5つに決まっている。パイプ（pipe-in-gen で作るもの）の段の名前は定義しだい。

/** 段の名前。パイプの定義の name と同じ規則（英小文字・数字・-）。 */
export type Stage = string;

export type DevStage = 'requirements' | 'design' | 'red' | 'implement' | 'test';

export const STAGES: readonly DevStage[] = ['requirements', 'design', 'red', 'implement', 'test'];

export const STAGE_LABELS: Readonly<Record<DevStage, string>> = {
  requirements: '要件定義',
  design: '設計',
  red: 'テスト先行',
  implement: '実装',
  test: '検証',
};

const STAGE_NAME = /^[a-z0-9][a-z0-9-]*$/;

export function isStageName(value: unknown): value is Stage {
  return typeof value === 'string' && STAGE_NAME.test(value);
}

export function isStage(value: unknown): value is DevStage {
  return typeof value === 'string' && (STAGES as readonly string[]).includes(value);
}
