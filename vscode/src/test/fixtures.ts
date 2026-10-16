// テスト用の記録（state.json・段のログ・記録の写し）を文字列として作る小さな関数。
// devpipe が work_dir に書く形（要件定義書「devpipe が今書いている記録」）に合わせる。
import type { Stage } from '../domain/stage.ts';
import type { WorkDirSnapshot } from '../domain/pipelineView.ts';

/** 段のログの始まりの行（`Prompt`）。 */
export function promptLine(stage: Stage): string {
  return JSON.stringify({ _type: 'Prompt', stage, resume: null, prompt: `${stage} の依頼文` });
}

/** 文章の部品を1つ持つ発言。 */
export function assistantText(text: string): string {
  return JSON.stringify({ _type: 'AssistantMessage', content: [{ text }], model: 'x' });
}

/** ツールの呼び出しの部品を1つ持つ発言。 */
export function assistantTool(name: string, input: object): string {
  return JSON.stringify({ _type: 'AssistantMessage', content: [{ id: 't', name, input }], model: 'x' });
}

/** 段の実行の終わりの行。 */
export function resultLine(): string {
  return JSON.stringify({
    _type: 'ResultMessage',
    subtype: 'success',
    is_error: false,
    num_turns: 1,
    duration_ms: 1000,
    total_cost_usd: 0.01,
    result: 'ok',
  });
}

/** 行を改行でつないで、ファイルの中身にする（末尾に改行を付ける）。 */
export function logText(lines: string[]): string {
  return lines.map((l) => `${l}\n`).join('');
}

/** state.json の runs に入る「段の実行」の要素（devpipe の `Pipeline._run_stage` が書く形）。 */
export function stageRunEntry(p: {
  stage: Stage;
  seq: number;
  attempt?: number | null;
  isError?: boolean;
  numTurns?: number;
  costUsd?: number;
  durationSec?: number;
}): object {
  return {
    stage: p.stage,
    seq: p.seq,
    attempt: p.attempt ?? null,
    note: '',
    num_turns: p.numTurns ?? 1,
    cost_usd: p.costUsd ?? 0,
    duration_sec: p.durationSec ?? 0,
    denials: [],
    is_error: p.isError ?? false,
    subtype: 'success',
    result: '',
    session_id: 's',
    errors: [],
  };
}

/** state.json の中身。 */
export function stateJson(p: { runs?: object[]; final?: string | null; totalCostUsd?: number }): string {
  return JSON.stringify({
    started_at: '2026-10-16T00:00:00',
    updated_at: '2026-10-16T00:00:00',
    final: p.final ?? null,
    total_cost_usd: p.totalCostUsd ?? 0,
    runs: p.runs ?? [],
  });
}

/** 記録の写し。既定は workDir:'/w'・stateJson:null・stageLogs:[]・artifacts:{}。 */
export function snapshot(p: Partial<WorkDirSnapshot> = {}): WorkDirSnapshot {
  return {
    workDir: p.workDir ?? '/w',
    stateJson: p.stateJson ?? null,
    stageLogs: p.stageLogs ?? [],
    artifacts: p.artifacts ?? {},
  };
}
