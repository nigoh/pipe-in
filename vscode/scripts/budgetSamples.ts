// 上限と費用の表の見本の記録（D0051）。確認用ページ（run-panel-budget-*）と、実機の手動の確認（AC-80）に使う state.json の中身だけを持つ。
// tests/fixtures/ には見本の記録を足さない。previewPages.ts の buildBudgetDir が、一時フォルダに書いて本物の読み取りで読む。
// runs[] の要素の鍵は、本体が書く形に、共通の表 tests/fixtures/budget_record.json の keys（max_budget_usd・resumed）だけを足したもの。
// 止まった段を 4 つ並べるのは見た目を確かめるための見本で、本物の流れ（止まったら終わる）ではない。

const STOP = 'error_max_budget_usd';

interface SampleRun {
  cost: number;
  /** 効いた上限。無ければ記録に鍵を書かない */
  limit?: number;
  /** 続きの会話の回（true のときだけ鍵を書く） */
  resumed?: boolean;
  /** 費用の上限で止まった回 */
  stopped?: boolean;
}
interface SampleStage {
  name: string;
  runs: SampleRun[];
}

const BUDGET_STAGES: readonly SampleStage[] = [
  { name: 'bd-ok', runs: [{ cost: 0.2, limit: 1 }] }, // 余裕
  { name: 'bd-near', runs: [{ cost: 0.9, limit: 1 }] }, // 近い
  { name: 'bd-over', runs: [{ cost: 1.2, limit: 1 }] }, // 超えた
  { name: 'bd-stopped', runs: [{ cost: 1.02, limit: 1, stopped: true }] }, // 止まった
  { name: 'bd-nolimit', runs: [{ cost: 0.35 }] }, // 上限なし
  { name: 'bd-nolimit-stopped', runs: [{ cost: 0.4, stopped: true }] }, // 上限なしで止まった（言葉だけ）
  { name: 'bd-resumed-ok', runs: [{ cost: 0.9, limit: 1, resumed: true }] }, // 続きの会話の回で、止まらなかった
  { name: 'bd-resumed-stopped', runs: [{ cost: 0.9, limit: 1, resumed: true, stopped: true }] }, // 続きの会話の回で止まった（言葉だけ）
  { name: 'bd-multi', runs: [{ cost: 0.9, limit: 1 }, { cost: 0.4, limit: 1 }] }, // 複数回の段
  { name: 'bd-maxpair', runs: [{ cost: 0.5, limit: 10000 }, { cost: 9999.999, limit: 10000, stopped: true }] }, // 最大の組
];

const FOUR_STAGES: readonly SampleStage[] = [
  { name: 'bd-ok', runs: [{ cost: 0.2, limit: 1 }] },
  { name: 'bd-near', runs: [{ cost: 0.9, limit: 1 }] },
  { name: 'bd-over', runs: [{ cost: 1.2, limit: 1 }] },
  { name: 'bd-stopped', runs: [{ cost: 1.02, limit: 1, stopped: true }] },
];

/** 段の並びから state.json の文字を作る（パイプ budget-demo。最後は STAGE_ERROR で、動いている段は出さない）。 */
function stateJsonOf(stages: readonly SampleStage[]): string {
  const runs: Record<string, unknown>[] = [];
  let seq = 0;
  let total = 0;
  for (const stage of stages) {
    for (const run of stage.runs) {
      seq += 1;
      total += run.cost;
      runs.push({
        stage: stage.name,
        session_id: `bd-session-${seq}`,
        is_error: run.stopped === true,
        subtype: run.stopped === true ? STOP : 'success',
        result: run.stopped === true ? '費用の上限で止まりました' : '完了しました',
        cost_usd: run.cost,
        num_turns: 3,
        duration_sec: 20.0,
        denials: [],
        errors: [],
        seq,
        attempt: null,
        note: '',
        ...(run.limit === undefined ? {} : { max_budget_usd: run.limit }),
        ...(run.resumed === true ? { resumed: true } : {}),
      });
    }
  }
  const state = {
    started_at: '2026-10-17T10:00:00',
    updated_at: '2026-10-17T10:20:00',
    pipe: 'budget-demo',
    name: '段ごとの費用の見本',
    stages: stages.map((s) => ({ name: s.name, label: s.name, output: `${s.name}.md`, review: false })),
    runs,
    final: 'STAGE_ERROR',
    total_cost_usd: Math.round(total * 1e4) / 1e4,
  };
  return `${JSON.stringify(state, null, 2)}\n`;
}

/** 10 個の段（余裕・近い・超えた・止まった・上限なし ほか）の見本の記録。 */
export function budgetStateJson(): string {
  return stateJsonOf(BUDGET_STAGES);
}

/** 実機の確認（AC-80）で手で作る、4 つの段（余裕・近い・超えた・止まった）の記録。 */
export function fourStagesStateJson(): string {
  return stateJsonOf(FOUR_STAGES);
}
