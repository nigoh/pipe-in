// 段：パイプラインの1工程。devpipe の段の名前に合わせる。

export type Stage = 'requirements' | 'design' | 'red' | 'implement' | 'test';

export const STAGES: readonly Stage[] = ['requirements', 'design', 'red', 'implement', 'test'];

export const STAGE_LABELS: Readonly<Record<Stage, string>> = {
  requirements: '要件定義',
  design: '設計',
  red: 'テスト先行',
  implement: '実装',
  test: '検証',
};

export function isStage(value: unknown): value is Stage {
  return typeof value === 'string' && (STAGES as readonly string[]).includes(value);
}
