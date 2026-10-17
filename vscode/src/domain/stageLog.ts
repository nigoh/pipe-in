// 段のログ：logs/NN_<段>[_回].jsonl の名前と中身を読む。記録の形の知識はここに閉じる。
import { isJsonObject } from './json.ts';
import type { JsonObject } from './json.ts';
import type { Stage } from './stage.ts';

export interface StageLogName {
  seq: number;
  stage: Stage;
  attempt: number | null;
}

// 段の名前は英小文字・数字・-（_ を含まない）なので、回の数（_2）と混ざらない
const LOG_NAME = /^(\d+)_([a-z0-9][a-z0-9-]*)(?:_(\d+))?\.jsonl$/;

/** '07_implement_2.jsonl' → { seq: 7, stage: 'implement', attempt: 2 }。合わなければ null。パスではなくファイル名だけを渡す。 */
export function parseStageLogName(fileName: string): StageLogName | null {
  const m = LOG_NAME.exec(fileName);
  if (!m) return null;
  return {
    seq: Number.parseInt(m[1], 10),
    stage: m[2],
    attempt: m[3] === undefined ? null : Number.parseInt(m[3], 10),
  };
}

export type OutputItem = { kind: 'tool'; tool: string; target: string | null } | { kind: 'text'; text: string };

export interface StageLog {
  items: OutputItem[];
  hasPrompt: boolean;
  finished: boolean;
}

/** 1行ずつ JSON として読む。読めない行・オブジェクトでない行は飛ばす。 */
function parseLines(text: string): JsonObject[] {
  const lines: JsonObject[] = [];
  for (const line of text.split(/\r?\n/)) {
    if (line.trim() === '') continue;
    try {
      const value: unknown = JSON.parse(line);
      if (isJsonObject(value)) lines.push(value);
    } catch {
      // 壊れた行・途中までの行は飛ばす
    }
  }
  return lines;
}

/** 段のログの中身（ファイル全体の文字列）を読む。例外を投げない。 */
export function parseStageLog(text: string): StageLog {
  const lines = parseLines(text);
  let lastPrompt = -1;
  lines.forEach((line, i) => {
    if (line._type === 'Prompt') lastPrompt = i;
  });
  const current = lines.slice(lastPrompt + 1);

  const items: OutputItem[] = [];
  let finished = false;
  for (const line of current) {
    if (line._type === 'ResultMessage') finished = true;
    if (line._type !== 'AssistantMessage' || !Array.isArray(line.content)) continue;
    for (const part of line.content) {
      const item = toOutputItem(part);
      if (item) items.push(item);
    }
  }
  return { items, hasPrompt: lastPrompt >= 0, finished };
}

/** 発言の部品1つを出力の項目にする。ツールの結果・考え中・知らない部品は null。 */
function toOutputItem(part: unknown): OutputItem | null {
  if (!isJsonObject(part)) return null;
  if ('tool_use_id' in part) return null;
  if ('thinking' in part) return null;
  if (typeof part.name === 'string' && isJsonObject(part.input)) {
    return { kind: 'tool', tool: part.name, target: summarizeToolTarget(part.input) };
  }
  if (typeof part.text === 'string' && part.text.trim() !== '') {
    return { kind: 'text', text: part.text };
  }
  return null;
}

const TARGET_KEYS = ['file_path', 'notebook_path', 'command', 'pattern', 'path'] as const;
const TARGET_MAX = 90;

/** ツールの呼び出しの対象（FR-09）。本体の _short と同じ切り詰め。 */
export function summarizeToolTarget(input: Record<string, unknown>): string | null {
  const key = TARGET_KEYS.find((k) => k in input);
  if (key === undefined) return null;
  const value = input[key];
  const raw = typeof value === 'string' ? value : (JSON.stringify(value) ?? String(value));
  const flat = raw.replace(/\s+/g, ' ').trim();
  return flat.length > TARGET_MAX ? `${flat.slice(0, TARGET_MAX - 1)}…` : flat;
}
