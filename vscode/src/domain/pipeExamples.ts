// 作業台の「見本から作る」：見本の一覧と、見本から作業台のモデルを作る（D0070）。
// 見本のデータは domain/exampleData.ts（examples/ から npm run examples:gen で作った生成物）。実行時にリポジトリの見本は読まない。
// 純粋な関数だけ（ファイル・vscode に触れない）。
import { EXAMPLE_DATA } from './exampleData.ts';
import type { ExampleData } from './exampleData.ts';
import { pipeFromFiles } from './pipeModel.ts';
import type { PipeModel } from './pipeModel.ts';

export type { ExampleData } from './exampleData.ts';

/** 見本の一覧に出す要約。budgetTotal は段の max_budget_usd の合計（上限のない段は 0）。 */
export interface ExampleSummary { name: string; label: string; description: string; stages: number; budgetTotal: number }

/** 見本の指示文（prompts/ で始まる鍵だけ） */
const promptsOf = (files: Record<string, string>): Record<string, string> =>
  Object.fromEntries(Object.entries(files).filter(([k]) => k.startsWith('prompts/')));

/** 見本から作業台のモデルを作る。名前は、呼び出し側が決めた新しいパイプの名前にする。 */
export function exampleModel(ex: ExampleData, name: string): PipeModel {
  return pipeFromFiles(name, ex.files['pipe.toml'] ?? '', promptsOf(ex.files), null);
}

/** 見本の一覧（名前順）。 */
export function listExamples(data: ExampleData[] = EXAMPLE_DATA): ExampleSummary[] {
  return [...data]
    .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))
    .map((ex) => {
      const m = exampleModel(ex, ex.name);
      const total = m.stages.reduce((sum, s) => sum + (s.maxBudget ?? 0), 0);
      return { name: ex.name, label: m.label, description: m.description, stages: m.stages.length, budgetTotal: Math.round(total * 100) / 100 };
    });
}

export function findExample(name: string, data: ExampleData[] = EXAMPLE_DATA): ExampleData | undefined {
  return data.find((ex) => ex.name === name);
}
