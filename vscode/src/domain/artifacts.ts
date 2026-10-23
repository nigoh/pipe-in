// 成果物：段が work_dir に書くファイル（開発フローの 7 つは Markdown。パイプの output は拡張子を決めない）。開いてよいのは、記録から作った一覧にあるものだけ。
// 開発フローは決まった7つ。パイプは「依頼メモ・各段の成果物（state.json の stages の output）・まとめ」。
// 基盤が写しに入れる成果物は、読んだ範囲の文字・更新時刻・切れた印（旧形は文字だけ）。ここで一覧の行（作った段・時刻の文字つき）にする。
import path from 'node:path';
import { validMtime } from './quiet.ts';
import { isDevRecord } from './runRecord.ts';
import type { RunRecord } from './runRecord.ts';
import { STAGE_LABELS } from './stage.ts';
import type { DevStage, Stage } from './stage.ts';
import { formatLocalStamp } from './timestamp.ts';

/** 成果物のファイル名（記録の置き場所の中のファイル名だけ）。 */
export type ArtifactName = string;

/** 成果物 1 つの読む量の上限（256 KiB、UTF-8 のバイト）。上限の数はここの 1 か所だけに置く。案内の文も、読む量（+1）もここから作る。 */
export const ARTIFACT_MAX_BYTES = 256 * 1024;

/** 1 回の読みで写しに入れる成果物の文字の合計（UTF-8 のバイト）の上限（4 MiB）。届いたら残りは読まない。 */
export const ARTIFACT_TOTAL_MAX_BYTES = 4 * 1024 * 1024;

/** 基盤が写しに入れる成果物 1 つ。text は上限で切ったあとの文字。mtimeMs は更新時刻（UTC のミリ秒）。cut は上限で切ったとき true。 */
export interface ArtifactFile {
  text: string;
  mtimeMs?: number | null;
  cut?: boolean;
}

/** 写しの成果物の値。旧形（文字だけ）も読む。 */
export type ArtifactContent = string | ArtifactFile;

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
const DASH = '—';

/** 開発フローで、成果物を作った段。決まった名前でだけ引く（外から来た名前の表にはしない）。依頼メモとまとめは段が作らない。 */
const DEV_MADE_BY: ReadonlyMap<ArtifactName, DevStage> = new Map<ArtifactName, DevStage>([
  ['01_requirements.md', 'requirements'],
  ['02_design.md', 'design'],
  ['03_red_tests.md', 'red'],
  ['04_implementation.md', 'implement'],
  ['05_test_report.md', 'test'],
]);

export interface ArtifactDef {
  name: ArtifactName;
  label: string;
  /** 作った段の名前。依頼メモ・まとめ・引けないものは null */
  stage: Stage | null;
  /** その段の表示名（開発フローは STAGE_LABELS、パイプは段の label）。引けなければ null */
  stageLabel: string | null;
}

export interface ArtifactEntry extends ArtifactDef {
  ready: boolean;
  /** 読んだ範囲の文字。ready でなければ '' */
  text: string;
  /** 上限で切れた印。ready のときだけ意味がある */
  cut: boolean;
  /** 更新時刻の文字（'MM/DD HH:mm'）。読めない・時計が無い・まだない → '—' */
  updatedText: string;
}

const DEV_ARTIFACTS: readonly ArtifactDef[] = ARTIFACT_NAMES.map((name) => {
  const stage = DEV_MADE_BY.get(name) ?? null;
  return { name, label: ARTIFACT_LABELS[name], stage, stageLabel: stage === null ? null : STAGE_LABELS[stage] };
});

/** 記録から成果物の一覧を作る。開発フロー（と記録なし）は7つ、パイプは依頼メモ・各段の output・まとめ。同じ output は先の段の 1 行。 */
export function artifactDefsFor(record: RunRecord | null): ArtifactDef[] {
  if (record === null || isDevRecord(record)) return [...DEV_ARTIFACTS];
  const defs: ArtifactDef[] = [{ name: INPUT, label: '依頼メモ', stage: null, stageLabel: null }];
  for (const stage of record.stages ?? []) {
    if (stage.output !== null && !defs.some((d) => d.name === stage.output)) {
      defs.push({ name: stage.output, label: stage.label, stage: stage.name, stageLabel: stage.label });
    }
  }
  if (!defs.some((d) => d.name === SUMMARY)) defs.push({ name: SUMMARY, label: 'まとめ', stage: null, stageLabel: null });
  return defs;
}

export function artifactNamesFor(record: RunRecord | null): ArtifactName[] {
  return artifactDefsFor(record).map((d) => d.name);
}

/** 自分の項目だけを見る（原型から来る値は読まない）。 */
function ownValue(object: object, key: string): unknown {
  return Object.hasOwn(object, key) ? (object as Record<string, unknown>)[key] : undefined;
}

/**
 * 写しの項目を { text, mtimeMs, cut } にそろえる。どんな値でも例外を出さない。
 * 文字（旧形）→ 更新時刻なし・切れていない。自分の項目 text が文字のオブジェクト → mtimeMs は読める値だけ（有限で 0 より大きい数）、cut は true のときだけ true。
 * それ以外（数・null・配列・関数・text が文字でない・text が原型から来るもの）→ null。
 */
export function artifactFileOf(value: unknown): Required<ArtifactFile> | null {
  if (typeof value === 'string') return { text: value, mtimeMs: null, cut: false };
  try {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return null;
    const text = ownValue(value, 'text');
    if (typeof text !== 'string') return null;
    return { text, mtimeMs: validMtime(ownValue(value, 'mtimeMs')), cut: ownValue(value, 'cut') === true };
  } catch {
    return null;
  }
}

/** 中身があり、空白だけでない（本体の _doc_ready）。undefined（ファイルなし）や読めない値は偽。 */
export function isArtifactReady(content: unknown): boolean {
  const file = artifactFileOf(content);
  return file !== null && file.text.trim() !== '';
}

/**
 * 一覧（既定は開発フローの7つ）の順に、ある・まだないと、読んだ範囲の文字・切れた印・更新時刻の文字を付けて返す。
 * 名前は自分のキーとしてだけ引く（constructor・__proto__ という名前でも、ほかの項目を壊さない）。
 * clock が無ければ、更新時刻の文字は「—」。
 */
export function buildArtifactList(
  contents: Partial<Record<ArtifactName, ArtifactContent>>,
  defs: readonly ArtifactDef[] = DEV_ARTIFACTS,
  clock?: { localOffsetMin: number },
): ArtifactEntry[] {
  return defs.map((def) => {
    const base = { name: def.name, label: def.label, stage: def.stage ?? null, stageLabel: def.stageLabel ?? null };
    const file = artifactFileOf(ownValue(contents, def.name));
    if (file === null || file.text.trim() === '') return { ...base, ready: false, text: '', cut: false, updatedText: DASH };
    const stamp = clock === undefined ? null : formatLocalStamp(file.mtimeMs, clock.localOffsetMin);
    return { ...base, ready: true, text: file.text, cut: file.cut, updatedText: stamp ?? DASH };
  });
}

/**
 * 既定の選び。liveStage は 動いている段 ?? 確認待ちの段 ?? null。
 * その段の成果物が「ある」ならそれ、そうでなければ一覧の順で最後の「ある」、無ければ null。
 */
export function defaultArtifactName(entries: readonly ArtifactEntry[], liveStage: Stage | null): ArtifactName | null {
  if (liveStage !== null) {
    const live = entries.find((e) => e.stage === liveStage);
    if (live !== undefined && live.ready) return live.name;
  }
  return entries.findLast((e) => e.ready)?.name ?? null;
}

/** name が allowed（既定は開発フローの7つ）のどれかと完全一致するときだけ path.join(workDirAbs, name) を返す。それ以外は null。 */
export function resolveArtifactPath(
  workDirAbs: string,
  name: string,
  allowed: readonly ArtifactName[] = ARTIFACT_NAMES,
): string | null {
  return allowed.includes(name) ? path.join(workDirAbs, name) : null;
}
