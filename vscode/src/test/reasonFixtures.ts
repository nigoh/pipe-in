// 差し戻し・修正の理由（D0016）のテストで使う、記録の組み立て。
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { DIAGRAMS_STAGES, snapshot, stageRunEntry, stateJson } from './fixtures.ts';

const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'tests', 'fixtures');

/** 見本の記録（tests/fixtures/<dir>/state.json）を読むだけ。書かない。 */
export function readFixtureState(...parts: string[]): string {
  return readFileSync(path.join(FIXTURES, ...parts, 'state.json'), 'utf8');
}

export function viewOf(stateText: string): PipelineView {
  return buildPipelineView(snapshot({ stateJson: stateText, artifacts: { '00_input.md': 'メモ' } }));
}

export function showcaseView(): PipelineView {
  return viewOf(readFixtureState('showcase'));
}

export interface FailureInput {
  criterion: string;
  detail: string;
}

/** 不合格の判定1件（本体の record verdict fail が書く形）。attempt を null にすると attempt の無い古い形。 */
export function failVerdict(p: { attempt: number | null; summary?: string; failures?: unknown }): object {
  const entry: Record<string, unknown> = {
    stage: 'test',
    verdict: { status: 'fail', summary: p.summary ?? '', failures: p.failures ?? [], commands: [], command_check: null },
  };
  if (p.attempt !== null) entry.attempt = p.attempt;
  return entry;
}

export function passVerdict(attempt: number | null): object {
  const entry: Record<string, unknown> = {
    stage: 'test',
    verdict: { status: 'pass', summary: '合格', failures: [], commands: [], command_check: null },
  };
  if (attempt !== null) entry.attempt = attempt;
  return entry;
}

/** 実装 → 検証の実行（attempt 回目）。seq は実装が 2a-1、検証が 2a。 */
export function implementAndTest(attempt: number): object[] {
  return [
    stageRunEntry({ stage: 'implement', seq: 2 * attempt - 1, attempt }),
    stageRunEntry({ stage: 'test', seq: 2 * attempt, attempt }),
  ];
}

export function reviseEntry(stage: string, feedback: string | null): object {
  return feedback === null ? { stage, review: 'revise' } : { stage, review: 'revise', feedback };
}

/** 開発フローの記録で、失敗の中身を指定して不合格1回のあと合格したもの。 */
export function oneSendBackView(p: { summary?: string; failures?: unknown; feedback?: string | null; warnings?: string[] }): PipelineView {
  const runs: object[] = [
    stageRunEntry({ stage: 'requirements', seq: 1 }),
    ...(p.feedback === undefined ? [] : [reviseEntry('requirements', p.feedback)]),
    ...implementAndTest(1),
    failVerdict({ attempt: 1, summary: p.summary ?? '', failures: p.failures ?? [] }),
    ...implementAndTest(2),
    passVerdict(2),
  ];
  return viewOf(stateJson({ runs, warnings: p.warnings }));
}

/** 不合格が1回だけで、やり直しの実装が無いまま終わった記録。 */
export function unresolvedView(): PipelineView {
  return viewOf(stateJson({ runs: [...implementAndTest(1), failVerdict({ attempt: 1, summary: '直らなかった', failures: [{ criterion: 'AC-01', detail: 'x' }] })], final: 'TEST_FAILED' }));
}

/** パイプ（段が開発の5段でない記録）。確認の直しと check の不合格、念のため判定の形の要素も持つ。 */
export function pipeView(): PipelineView {
  return viewOf(
    stateJson({
      pipe: 'diagrams',
      stages: DIAGRAMS_STAGES,
      runs: [
        stageRunEntry({ stage: 'survey', seq: 1 }),
        reviseEntry('survey', '範囲を絞って'),
        stageRunEntry({ stage: 'survey', seq: 2 }),
        { stage: 'survey', review: 'approved' },
        stageRunEntry({ stage: 'draw', seq: 3 }),
        { stage: 'draw', check: { status: 'fail', problems: ['図が空'] } },
        failVerdict({ attempt: 1, summary: 'パイプでも判定の形が来ても', failures: [{ criterion: 'AC-01', detail: 'x' }] }),
      ],
    }),
  );
}
