// 作業台から流してよいかの判断（D0078）。作業台のパネルも入口も、同じ関数を使う。外の部品（node:・vscode・パッケージ）を import しない。
import type { InputMode } from './pipeModel.ts';
import { textProblem, TEXT_REASONS } from './runCommand.ts';
import type { TextProblem } from './runCommand.ts';
import type { ExecutableResult } from './runExecutable.ts';

/** 入口がパネルへ送る・入口が自分でも作る「今の事実」。パネルから入口へは送らない */
export interface RunContext {
  /** 保存済みの形の input */
  input: InputMode;
  /** 開いたパイプのフォルダの絶対パス。まだ一度も保存していなければ null */
  pipeDir: string | null;
  /** 保存済みの形の検査の誤りの数 */
  savedErrors: number;
  /** ワークスペースの最初のフォルダの絶対パス。無ければ null */
  project: string | null;
  trusted: boolean;
  executable: ExecutableResult;
  /** このパイプのフォルダから起こした実行がまだ終わっていない */
  running: boolean;
}
export type RunBlock = 'untrusted' | 'noProject' | 'noExecutable' | 'running' | 'notSaved' | 'dirty' | 'invalid' | 'textEmpty' | 'textTooLong' | 'textNul' | 'textBroken';
/** 理由を決める順。環境の問題（パネルで直せないもの）を先に、パネルで直せるものを後に並べる */
export const RUN_BLOCK_ORDER: readonly RunBlock[] = ['untrusted', 'noProject', 'noExecutable', 'running', 'notSaved', 'dirty', 'invalid', 'textEmpty', 'textTooLong', 'textNul', 'textBroken'];
export type RunDecision = { ok: true } | { ok: false; block: RunBlock; reason: string };

const TEXT_BLOCKS: Record<TextProblem, RunBlock> = { empty: 'textEmpty', tooLong: 'textTooLong', nul: 'textNul', broken: 'textBroken' };

/** 流してよいか。上から見て、最初に当たった理由を1つ返す。dirty は「保存していない変更がある」 */
export function decideRun(ctx: RunContext, dirty: boolean, text: string): RunDecision {
  if (!ctx.trusted) return { ok: false, block: 'untrusted', reason: '信頼していないワークスペースでは流せません。フォルダを信頼してから流してください' };
  if (ctx.project === null) return { ok: false, block: 'noProject', reason: 'ワークスペースのフォルダを開いてから流してください' };
  if (!ctx.executable.ok) return { ok: false, block: 'noExecutable', reason: ctx.executable.reason };
  if (ctx.running) return { ok: false, block: 'running', reason: 'このパイプは実行中です。終わってから、もう一度流してください' };
  if (ctx.pipeDir === null) return { ok: false, block: 'notSaved', reason: '先に保存してください（まだ一度も保存していないパイプは流せません）' };
  if (dirty) return { ok: false, block: 'dirty', reason: '保存していない変更があります。先に保存してください' };
  if (ctx.savedErrors > 0) return { ok: false, block: 'invalid', reason: `保存した形に検査の誤りが ${ctx.savedErrors} 件あります。直して保存してください` };
  const problem = textProblem(ctx.input, text);
  if (problem !== null) return { ok: false, block: TEXT_BLOCKS[problem], reason: TEXT_REASONS[problem] };
  return { ok: true };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readExecutable(value: unknown): ExecutableResult | null {
  if (!isRecord(value)) return null;
  if (value.ok === true && typeof value.path === 'string') return { ok: true, path: value.path };
  if (value.ok === false && typeof value.reason === 'string') return { ok: false, reason: value.reason };
  return null;
}

/** パネル側で知らせを検める。型・形が違えば null。7項目だけを返し、type などほかの鍵は捨てる */
export function readRunContext(value: unknown): RunContext | null {
  if (!isRecord(value)) return null;
  const { input, pipeDir, savedErrors, project, trusted, running } = value;
  if (input !== 'required' && input !== 'optional' && input !== 'none') return null;
  if (pipeDir !== null && typeof pipeDir !== 'string') return null;
  if (typeof savedErrors !== 'number') return null;
  if (project !== null && typeof project !== 'string') return null;
  if (typeof trusted !== 'boolean' || typeof running !== 'boolean') return null;
  const executable = readExecutable(value.executable);
  if (executable === null) return null;
  return { input, pipeDir, savedErrors, project, trusted, executable, running };
}
