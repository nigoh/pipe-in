// 作業台から流す計画（D0078）。保存済みの形と開いたパイプから「今の事実」を作り、判断とコマンドの形を1か所にそろえる。
import path from 'node:path';
import { validatePipe } from '../domain/pipeModel.ts';
import type { PipeModel } from '../domain/pipeModel.ts';
import { buildRunCommand } from '../domain/runCommand.ts';
import type { OsKind } from '../domain/runCommand.ts';
import { decideRun } from '../domain/runDecision.ts';
import type { RunContext } from '../domain/runDecision.ts';
import type { ExecutableResult } from '../domain/runExecutable.ts';
import type { PipeRef } from './pipeEditor.ts';

/** 「今の事実」を作る。パネルから来た値は引数に無い（保存済みの形と、入口が集めた値だけ） */
export function runContextFor(i: { ref: PipeRef | null; saved: PipeModel; project: string | null; trusted: boolean; executable: ExecutableResult; isRunning: (pipeDir: string) => boolean }): RunContext {
  const pipeDir = i.ref ? path.resolve(i.ref.dir, i.ref.folder) : null;
  return {
    input: i.saved.input,
    pipeDir,
    savedErrors: validatePipe(i.saved).errors.length,
    project: i.project,
    trusted: i.trusted,
    executable: i.executable,
    running: pipeDir !== null && i.isRunning(pipeDir),
  };
}

export type RunPlan = { ok: true; command: string; args: string[]; cwd: string; pipeDir: string } | { ok: false; reason: string };

/** 流す計画。decideRun が断ればその理由。通れば buildRunCommand（二重の守り）で作る。cwd はプロジェクト */
export function planRun(ctx: RunContext, dirty: boolean, text: string, os: OsKind): RunPlan {
  const decision = decideRun(ctx, dirty, text);
  if (!decision.ok) return { ok: false, reason: decision.reason };
  // decideRun が通れば次の3つはある。型のために確かめ、無ければ流さない
  if (ctx.pipeDir === null || ctx.project === null || !ctx.executable.ok) return { ok: false, reason: '流す準備が整っていません' };
  const built = buildRunCommand({ os, executable: ctx.executable.path, pipeDir: ctx.pipeDir, project: ctx.project, input: ctx.input, text });
  if (!built.ok) return { ok: false, reason: built.reason };
  return { ok: true, command: built.command, args: built.args, cwd: ctx.project, pipeDir: ctx.pipeDir };
}
