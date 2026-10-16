// 成果物：段が work_dir に書く Markdown（7つ）。開いてよいのはこの7つだけ。
import path from 'node:path';

export type ArtifactName =
  | '00_input.md'
  | '01_requirements.md'
  | '02_design.md'
  | '03_red_tests.md'
  | '04_implementation.md'
  | '05_test_report.md'
  | '99_summary.md';

export const ARTIFACT_NAMES: readonly ArtifactName[] = [
  '00_input.md',
  '01_requirements.md',
  '02_design.md',
  '03_red_tests.md',
  '04_implementation.md',
  '05_test_report.md',
  '99_summary.md',
];

export const ARTIFACT_LABELS: Readonly<Record<ArtifactName, string>> = {
  '00_input.md': '要件メモ',
  '01_requirements.md': '要件定義書',
  '02_design.md': '設計書',
  '03_red_tests.md': 'テスト先行の記録',
  '04_implementation.md': '実装の記録',
  '05_test_report.md': 'テスト報告',
  '99_summary.md': 'まとめ',
};

export interface ArtifactEntry {
  name: ArtifactName;
  label: string;
  ready: boolean;
}

export function isArtifactName(value: string): value is ArtifactName {
  return (ARTIFACT_NAMES as readonly string[]).includes(value);
}

/** 中身があり、空白だけでない（devpipe の _doc_ready）。undefined はファイルなし。 */
export function isArtifactReady(content: string | undefined): boolean {
  return content !== undefined && content.trim() !== '';
}

/** 7件を ARTIFACT_NAMES の順に返す。 */
export function buildArtifactList(contents: Partial<Record<ArtifactName, string>>): ArtifactEntry[] {
  return ARTIFACT_NAMES.map((name) => ({ name, label: ARTIFACT_LABELS[name], ready: isArtifactReady(contents[name]) }));
}

/** name が ARTIFACT_NAMES のどれかと完全一致するときだけ path.join(workDirAbs, name) を返す。それ以外は null。 */
export function resolveArtifactPath(workDirAbs: string, name: string): string | null {
  return isArtifactName(name) ? path.join(workDirAbs, name) : null;
}
