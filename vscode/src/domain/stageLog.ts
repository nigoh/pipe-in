// 段のログ：logs/NN_<段>[_回].jsonl の名前と中身を読む。記録の形の知識はここに閉じる。
// 道具の呼び出しの見分け（部品の判定 partOf）は 1 つだけで、出力の道具の行と、頼んだときだけ返す呼び出しの記録 calls（D0049）の両方がそこから出る。
// Agent・Task・Skill の見分けと、入力の鍵 subagent_type・skill の読み（入力自身が持つ鍵だけ）もここに閉じる。表を作る側は、名前の決まりだけを持つ。
// 読むのは本体（Python の SDK）がメッセージを dataclasses.asdict で書いた形（_type・content）だけ。TypeScript の SDK の形（type・message.content）は読まない。
import { isJsonObject } from './json.ts';
import type { JsonObject } from './json.ts';
import { isSafeToken } from './sessionName.ts';
import type { Stage } from './stage.ts';
import { isTimestampText } from './timestamp.ts';

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

/** 呼び出しの種類（D0049）：エージェント（Agent・Task）・スキル（Skill）・それ以外の道具。 */
export type ToolKind = 'agent' | 'skill' | 'tool';

/** 道具の呼び出し 1 つの小さな記録。入力のうち持ち出すのは名前に使う 1 つの値だけ（プロンプトやコマンドは持ち出さない）。 */
export interface ToolCall {
  kind: ToolKind;
  /** 名前に使う生の値。agent は input.subagent_type、skill は input.skill（どちらも自分の鍵だけ。無ければ undefined）、tool は部品の name（文字） */
  name: unknown;
}

export interface StageLog {
  items: OutputItem[];
  hasPrompt: boolean;
  finished: boolean;
  /** 段の始まりの時刻（最後の Prompt 行の at の文字）。無い・読めない・Prompt が無いなら null */
  startedAt: string | null;
  /** 段の受け持ち（最後の Prompt 行の agent）。無い・読めない・Prompt が無いなら null */
  agent: string | null;
  /** 道具の呼び出し（出力の道具の行と同じ判定・同じ順）。parseStageLog に { calls: true } を渡したときだけ（頼まないときは項目ごと無い） */
  calls?: ToolCall[];
}

export interface ParseStageLogOptions {
  /** 真なら calls も返す。一覧の行のように数えない読み方は頼まない（今までと同じ重さ） */
  calls?: boolean;
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

/**
 * 段のログの中身（ファイル全体の文字列）を読む。例外を投げない。
 * options.calls が真のときだけ、道具の呼び出しの小さな記録 calls も返す（出力の道具の行と同じ部品の判定 partOf から、同じ走査で作る）。
 */
export function parseStageLog(text: string, options?: ParseStageLogOptions): StageLog {
  const lines = parseLines(text);
  let lastPrompt = -1;
  lines.forEach((line, i) => {
    if (line._type === 'Prompt') lastPrompt = i;
  });
  const current = lines.slice(lastPrompt + 1);

  const items: OutputItem[] = [];
  const calls: ToolCall[] = [];
  const wantCalls = options?.calls === true;
  let finished = false;
  for (const line of current) {
    if (line._type === 'ResultMessage') finished = true;
    if (line._type !== 'AssistantMessage' || !Array.isArray(line.content)) continue;
    for (const part of line.content) {
      const found = partOf(part);
      if (found === null) continue;
      if (found.kind === 'text') {
        items.push({ kind: 'text', text: found.text });
        continue;
      }
      items.push({ kind: 'tool', tool: found.name, target: summarizeToolTarget(found.input) });
      if (wantCalls) calls.push(callOf(found.name, found.input));
    }
  }
  const at = lastPrompt >= 0 ? lines[lastPrompt].at : null;
  const agent = lastPrompt >= 0 ? lines[lastPrompt].agent : null;
  const log: StageLog = {
    items,
    hasPrompt: lastPrompt >= 0,
    finished,
    startedAt: isTimestampText(at) ? at : null,
    agent: isSafeToken(agent) ? agent : null,
  };
  if (wantCalls) log.calls = calls;
  return log;
}

/** 発言の部品1つの見分け。道具の呼び出し（名前と入力）か文章か。ツールの結果・考え中・知らない部品は null。出力の行と calls の両方がこの判定 1 つから出る。 */
function partOf(part: unknown): { kind: 'tool'; name: string; input: JsonObject } | { kind: 'text'; text: string } | null {
  if (!isJsonObject(part)) return null;
  if ('tool_use_id' in part) return null;
  if ('thinking' in part) return null;
  if (typeof part.name === 'string' && isJsonObject(part.input)) {
    return { kind: 'tool', name: part.name, input: part.input };
  }
  if (typeof part.text === 'string' && part.text.trim() !== '') {
    return { kind: 'text', text: part.text };
  }
  return null;
}

/** エージェントを呼ぶ道具の名前（Task は旧名）。大文字小文字は区別する。 */
const AGENT_TOOLS: readonly string[] = ['Agent', 'Task'];
const SKILL_TOOL = 'Skill';

/** 道具の呼び出し 1 つの種類と名前。入力は名前に使う鍵（subagent_type・skill）の、入力自身が持つ値だけを読む（継承した値は読まない）。 */
function callOf(name: string, input: JsonObject): ToolCall {
  if (AGENT_TOOLS.includes(name)) return { kind: 'agent', name: ownValue(input, 'subagent_type') };
  if (name === SKILL_TOOL) return { kind: 'skill', name: ownValue(input, 'skill') };
  return { kind: 'tool', name };
}

/** 入力が自分で持つ鍵の値。無ければ undefined。 */
function ownValue(input: JsonObject, key: string): unknown {
  return Object.hasOwn(input, key) ? input[key] : undefined;
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
