// 成果物：段が work_dir に書く Markdown。開いてよいのは、記録から作った一覧にあるものだけ。
// 開発フローは決まった7つ。パイプは「依頼メモ・各段の成果物（state.json の stages の output）・まとめ」。
import path from 'node:path';
import { isDevRecord } from './runRecord.ts';
import type { RunRecord } from './runRecord.ts';

/** 成果物のファイル名（記録の置き場所の中のファイル名だけ）。 */
export type ArtifactName = string;

/** 開発フローの7つ。 */
export const ARTIFACT_NAMES: readonly ArtifactName[] = [
  '00_input.md',
  '01_requirements.md',
  '02_design.md',
  '03_red_tests.md',
  '04_implementation.md',
  '05_test_report.md',
  '99_summary.md',
];

export const ARTIFACT_LABELS: Readonly<Record<string, string>> = {
  '00_input.md': '要件メモ',
  '01_requirements.md': '要件定義書',
  '02_design.md': '設計書',
  '03_red_tests.md': 'テスト先行の記録',
  '04_implementation.md': '実装の記録',
  '05_test_report.md': 'テスト報告',
  '99_summary.md': 'まとめ',
};

const INPUT = '00_input.md';
const SUMMARY = '99_summary.md';

export interface ArtifactDef {
  name: ArtifactName;
  label: string;
}

export interface ArtifactEntry extends ArtifactDef {
  ready: boolean;
}

const DEV_ARTIFACTS: readonly ArtifactDef[] = ARTIFACT_NAMES.map((name) => ({ name, label: ARTIFACT_LABELS[name] }));

/** 記録から成果物の一覧を作る。開発フロー（と記録なし）は7つ、パイプは依頼メモ・各段の output・まとめ。 */
export function artifactDefsFor(record: RunRecord | null): ArtifactDef[] {
  if (record === null || isDevRecord(record)) return [...DEV_ARTIFACTS];
  const defs: ArtifactDef[] = [{ name: INPUT, label: '依頼メモ' }];
  for (const stage of record.stages ?? []) {
    if (stage.output !== null && !defs.some((d) => d.name === stage.output)) {
      defs.push({ name: stage.output, label: stage.label });
    }
  }
  if (!defs.some((d) => d.name === SUMMARY)) defs.push({ name: SUMMARY, label: 'まとめ' });
  return defs;
}

export function artifactNamesFor(record: RunRecord | null): ArtifactName[] {
  return artifactDefsFor(record).map((d) => d.name);
}

/** 中身があり、空白だけでない（devpipe の _doc_ready）。undefined はファイルなし。 */
export function isArtifactReady(content: string | undefined): boolean {
  return content !== undefined && content.trim() !== '';
}

/** 一覧（既定は開発フローの7つ）の順に、ある・まだないを付けて返す。 */
export function buildArtifactList(
  contents: Partial<Record<ArtifactName, string>>,
  defs: readonly ArtifactDef[] = DEV_ARTIFACTS,
): ArtifactEntry[] {
  return defs.map(({ name, label }) => ({ name, label, ready: isArtifactReady(contents[name]) }));
}

/** name が allowed（既定は開発フローの7つ）のどれかと完全一致するときだけ path.join(workDirAbs, name) を返す。それ以外は null。 */
export function resolveArtifactPath(
  workDirAbs: string,
  name: string,
  allowed: readonly ArtifactName[] = ARTIFACT_NAMES,
): string | null {
  return allowed.includes(name) ? path.join(workDirAbs, name) : null;
}
