// 作業台から流す実行ファイルを、絶対パスに決める手順（D0078）。「そのパスに通常のファイルがあるか」は口で受け取る。
import type { OsKind } from '../domain/runCommand.ts';
import { chooseCommand, NOT_FOUND_REASON, pathCandidates, userCommandValue } from '../domain/runExecutable.ts';
import type { ExecutableResult } from '../domain/runExecutable.ts';

/** 「そのパスに通常のファイルがあるか」。投げたら false とみなす */
export type FileProbe = (absolutePath: string) => Promise<boolean>;

async function exists(isFile: FileProbe, file: string): Promise<boolean> {
  try {
    return await isFile(file);
  } catch {
    return false;
  }
}

/**
 * 実行ファイルを絶対パスに決める。設定はユーザーの設定の値（globalValue・defaultValue）だけを見る。
 * 設定が断られた・絶対パスにファイルが無いときは、PATH に戻らず理由を返す。pipe-in（未設定）なら、PATH の絶対の項目だけを順に探す。
 */
export async function resolveExecutable(i: { setting: { globalValue?: unknown; defaultValue?: unknown }; pathEnv: string | undefined; os: OsKind; isFile: FileProbe }): Promise<ExecutableResult> {
  const choice = chooseCommand(userCommandValue(i.setting), i.os);
  if (choice.kind === 'refused') return { ok: false, reason: choice.reason };
  if (choice.kind === 'fixed') {
    if (await exists(i.isFile, choice.path)) return { ok: true, path: choice.path };
    return { ok: false, reason: `\`pipe-in.command\` のファイルがありません：${choice.path}` };
  }
  for (const candidate of pathCandidates(i.pathEnv, i.os)) {
    if (await exists(i.isFile, candidate)) return { ok: true, path: candidate };
  }
  return { ok: false, reason: NOT_FOUND_REASON };
}
