// テストの補助：エージェント・スキル・道具の表（D0049）の記録の組み立て。
// 偽の段のログ（文字列）と一時フォルダだけで作る。SDK は呼ばない。リポジトリの実物には書かない。
// 呼び出しごとに別の id を持たせる（assistantTool の id の引数・uniqueCalls）。入れ子は parent_tool_use_id（assistantParts の第 2 引数。発言の行の項目）。
// 壊れた行・driver あり／なし・極端な入力（bigLog）も、ここで作る。
import type { WorkDirSnapshot } from '../domain/pipelineView.ts';
import { assistantParts, logText, promptLine, resultLine, snapshot, stageRunEntry, stateJson, toolPart } from './fixtures.ts';
import { stageLog } from './ganttFixtures.ts';

/** 外から来た文字の見本（名前・段の表示名に入れる）。空白を含まないので、名前の決まりには合う（読める名前になる）。 */
export const HOSTILE: readonly string[] = ['<script>alert(1)</script>', '"', "'", '&', '</td></tr></table>'];

/** オブジェクトの組み込みの名前（名前にしても、ほかの行を壊さない）。 */
export const PROTO_NAMES: readonly string[] = ['__proto__', 'constructor', 'toString'];

/**
 * Object.prototype に、値を持つ鍵を一時的に足して run を流し、必ず元に戻す（数え方が「入力の自分の鍵だけ」を読むことを見張るため）。
 * 足した鍵は数え上げられない（enumerable: false）ので、ほかの比べ方には影響しない。run は同期（途中で他のテストに割り込まれない）。
 * JSON.parse が作る自分の鍵 __proto__ はプロトタイプを替えない（ただの自分の鍵）ので、継承された値を読む実装と見分けるには、この足し方が要る。
 */
export function withPollutedPrototype<T>(values: Readonly<Record<string, string>>, run: () => T): T {
  const added: string[] = [];
  try {
    for (const key of Object.keys(values)) {
      if (Object.hasOwn(Object.prototype, key)) throw new Error(`Object.prototype にもう ${key} がある（テストの前提が違う）`);
      Object.defineProperty(Object.prototype, key, { value: values[key], configurable: true, writable: true, enumerable: false });
      added.push(key);
    }
    return run();
  } finally {
    for (const key of added) delete (Object.prototype as Record<string, unknown>)[key];
  }
}

/** 呼び出し 1 種類ぶんの指定。count 回、別々の id で呼ぶ。parent はサブエージェントの中の発言（parent_tool_use_id）。 */
export interface CallSpec {
  name: string;
  input?: unknown;
  count?: number;
  /** 発言の行の parent_tool_use_id。省くと項目ごと無し（メインの発言） */
  parent?: unknown;
}

/** 呼び出しの行（AssistantMessage 1 行に部品 1 つ）を、指定の順に作る。id は prefix + 通し番号で、全部別。 */
export function uniqueCalls(specs: readonly CallSpec[], prefix = 'c'): string[] {
  const lines: string[] = [];
  let n = 0;
  for (const spec of specs) {
    for (let i = 0; i < (spec.count ?? 1); i++) {
      n += 1;
      lines.push(assistantParts([toolPart(spec.name, spec.input ?? {}, `${prefix}${n}`)], spec.parent));
    }
  }
  return lines;
}

/** 段のログの中身（Prompt → 行 → 結果の行）。finished を偽にすると結果の行を付けない（動いている）。 */
export function logOf(stage: string, lines: readonly string[], opts: { finished?: boolean; at?: unknown; agent?: unknown } = {}): string {
  return logText([promptLine(stage, opts.at, opts.agent), ...lines, ...(opts.finished === false ? [] : [resultLine()])]);
}

export interface ToolLogSpec {
  seq: number;
  stage: string;
  /** ログのファイル名の回（NN_<段>_<回>.jsonl） */
  attempt?: number;
  /** 最後の Prompt 行の agent */
  agent?: unknown;
  at?: unknown;
  /** 偽にすると動いている（結果の行なし） */
  finished?: boolean;
  /** 呼び出しの行（文章の行のあと・結果の行の前） */
  lines?: readonly string[];
}

export interface ToolRunSpec {
  seq: number;
  stage: string;
  /** runs[].attempt（ログのファイル名の回と違ってもよい） */
  attempt?: number | null;
  /** runs[].agent（壊れた値も渡せる）。省くと持たない */
  agent?: unknown;
  durationSec?: number;
  /** runs[].duration_sec を壊れた値にして試す */
  rawDurationSec?: unknown;
  /** runs[].denials（本体の守りが止めた呼び出しの記録の文）。省くと空 */
  denials?: readonly string[];
}

/**
 * 表のテスト用の記録の写し。logs は段のログ（stageLog に lines を足したもの）、runs は state.json の runs[] の段の実行。
 * extras は runs[] に足す段の実行以外の要素（review・verdict など。seq を持たないもの）。
 * stateText を渡すと、state.json はその文字そのまま（null ならファイルなし。壊れた JSON も渡せる）。
 * running は、動いている段のログ（結果の行なし）を logs の最後に足す近道。
 */
export function toolsSnapshot(p: {
  logs?: readonly ToolLogSpec[];
  runs?: readonly ToolRunSpec[];
  extras?: readonly object[];
  driver?: unknown;
  pipe?: string;
  stages?: unknown;
  final?: string | null;
  running?: Omit<ToolLogSpec, 'finished'>;
  stateText?: string | null;
  artifacts?: WorkDirSnapshot['artifacts'];
}): WorkDirSnapshot {
  const logs = [...(p.logs ?? []), ...(p.running === undefined ? [] : [{ ...p.running, finished: false }])];
  const entries: object[] = (p.runs ?? []).map((r) => ({
    ...stageRunEntry({
      stage: r.stage,
      seq: r.seq,
      attempt: r.attempt ?? null,
      durationSec: r.durationSec ?? 0,
      ...(r.rawDurationSec === undefined ? {} : { rawDurationSec: r.rawDurationSec }),
      agent: r.agent,
    }),
    ...(r.denials === undefined ? {} : { denials: [...r.denials] }),
  }));
  entries.push(...(p.extras ?? []));
  return snapshot({
    stateJson:
      p.stateText !== undefined
        ? p.stateText
        : stateJson({
            runs: entries,
            final: p.final ?? null,
            ...(p.driver === undefined ? {} : { driver: p.driver }),
            ...(p.pipe === undefined ? {} : { pipe: p.pipe }),
            ...(p.stages === undefined ? {} : { stages: p.stages }),
          }),
    stageLogs: logs.map((l) =>
      stageLog({
        seq: l.seq,
        stage: l.stage,
        ...(l.attempt === undefined ? {} : { attempt: l.attempt }),
        at: l.at,
        agent: l.agent,
        ...(l.finished === undefined ? {} : { finished: l.finished }),
        ...(l.lines === undefined ? {} : { lines: l.lines }),
      }),
    ),
    artifacts: p.artifacts ?? { '00_input.md': 'メモ' },
  });
}

/**
 * 極端な入力の段のログの中身（AC-45）。calls 回の呼び出し（names 種類の名前を順に回す）と、
 * hugeInputBytes バイトの入力を持つ 1 行（その行の呼び出しの command に長い文字を入れる）。
 * 名前は t0, t1, …（空白なし・短い）。呼び出しごとに別の id。
 */
export function bigLog(p: { calls: number; names: number; hugeInputBytes?: number }): string {
  const lines: string[] = [promptLine('big')];
  for (let i = 0; i < p.calls; i++) {
    lines.push(JSON.stringify({ _type: 'AssistantMessage', content: [{ id: `b${i}`, name: `t${i % p.names}`, input: {} }], model: 'x' }));
  }
  if ((p.hugeInputBytes ?? 0) > 0) {
    lines.push(
      JSON.stringify({ _type: 'AssistantMessage', content: [{ id: 'huge', name: 'Bash', input: { command: 'x'.repeat(p.hugeInputBytes ?? 0) } }], model: 'x' }),
    );
  }
  lines.push(resultLine());
  return logText(lines);
}
