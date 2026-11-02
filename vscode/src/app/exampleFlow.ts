// 「見本から作る」の手順（D0070）：新しいパイプの名前を確かめ、見本から作業台のモデルを作る。
// ファイルへ書く口は受け取らない（書けない形）。モデルは未保存の下書きとして開かれ、保存は既存の手順に任せる。
import { saveTarget } from './pipeEditor.ts';
import type { PipeRef } from './pipeEditor.ts';
import { exampleModel } from '../domain/pipeExamples.ts';
import type { ExampleData } from '../domain/pipeExamples.ts';
import type { PipeModel } from '../domain/pipeModel.ts';

/** 新しいパイプの名前の断り（使える名前なら null）。保存のときの確かめ（saveTarget）と同じ文で断る。 */
export function exampleNameProblem(refs: PipeRef[], dirs: string[], name: string): string | null {
  const target = saveTarget(refs, null, name, dirs);
  return 'error' in target ? target.error : null;
}

/** 見本から、名前を付けたモデルを作る。名前が使えなければ断りの文を返す。 */
export function startFromExample(refs: PipeRef[], dirs: string[], ex: ExampleData, name: string): { model: PipeModel } | { error: string } {
  const error = exampleNameProblem(refs, dirs, name);
  if (error !== null) return { error };
  return { model: exampleModel(ex, name) };
}
