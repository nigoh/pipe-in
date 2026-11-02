// テストの補助（D0065）：外で書き換わったパイプの判断・差分・手順のテストが使う見本。ファイルは作らない（文字列と、メモリの中の形だけ）。
import { pipeFiles, pipeFromFiles } from '../domain/pipeModel.ts';
import type { PipeModel } from '../domain/pipeModel.ts';

export const BASE_TOML = `[pipe]
kind = "linear"
label = "見本"
input = "optional"

[[stages]]
name = "survey"
label = "調べる"
output = "01_survey.md"
access = "read"
prompt_file = "prompts/01_survey.md"

[[stages]]
name = "write"
label = "書く"
output = "02_write.md"
access = "docs"
docs_dir = "docs"
prompt_file = "prompts/02_write.md"
`;

export const BASE_PROMPTS: Record<string, string> = {
  'prompts/01_survey.md': '資料を調べる\n',
  'prompts/02_write.md': '文書を書く\n',
};

/** 見本のパイプ（名前は one）。呼ぶたびに新しいオブジェクト。 */
export const baseModel = (): PipeModel => pipeFromFiles('one', BASE_TOML, BASE_PROMPTS, null);

/** モデルを書き出して読み直した形（保存した直後・外のツールが同じ内容を書いたあとにディスクから読む形）。ファイルは作らない */
export function reread(m: PipeModel): PipeModel {
  const files = pipeFiles(m);
  const prompts: Record<string, string> = {};
  for (const [rel, text] of Object.entries(files)) if (rel.startsWith('prompts/')) prompts[rel] = text;
  return pipeFromFiles(m.name, files['pipe.toml']!, prompts, files['layout.json']!);
}

/** 段・枠の id を付け替えた写し（つなぎの行き先も付け替える）。読み込みのたびに id が変わっても、つなぎが同じなら差にしない確かめに使う */
export function renameIds(m: PipeModel, prefix: string): PipeModel {
  const copy = JSON.parse(JSON.stringify(m)) as PipeModel;
  const map = new Map<string, string>();
  for (const s of copy.stages) map.set(s.id, `${prefix}${s.id}`);
  for (const f of copy.frames) map.set(f.id, `${prefix}${f.id}`);
  const to = (id: string | null): string | null => (id === null ? null : map.get(id) ?? id);
  for (const s of copy.stages) {
    s.id = to(s.id)!;
    s.next = to(s.next);
    s.onFail = to(s.onFail);
    for (const r of s.routes) r.to = to(r.to)!;
  }
  for (const f of copy.frames) {
    f.id = to(f.id)!;
    f.next = to(f.next);
  }
  return copy;
}
