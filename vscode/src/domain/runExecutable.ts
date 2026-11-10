// 作業台から流す実行ファイルの決め方のうち、純粋な部分（D0078）。外の部品（node:・vscode・パッケージ）を import しない。
// ファイルがあるかを見る手順は app/runExecutable.ts。ここはファイルに触れない。
import { isAbsolutePath } from './runCommand.ts';
import type { OsKind } from './runCommand.ts';

export const DEFAULT_COMMAND = 'pipe-in';
export const NOT_FOUND_REASON = '`pipe-in` が見つかりません。設定 `pipe-in.command` に絶対パスを書いてください';
export type ExecutableResult = { ok: true; path: string } | { ok: false; reason: string };
export type CommandChoice = { kind: 'search' } | { kind: 'fixed'; path: string } | { kind: 'refused'; reason: string };

/** 設定の値。ユーザーの設定（globalValue）があればそれ、なければ既定。ワークスペースの値は受け取らない */
export function userCommandValue(s: { globalValue?: unknown; defaultValue?: unknown }): unknown {
  return s.globalValue !== undefined ? s.globalValue : s.defaultValue;
}

const WINDOWS_EXECUTABLE = /[^\\/]\.(?:exe|com)$/i;

/** Windows で実行ファイルにしてよいか（最後の要素が .exe か .com）。posix は拡張子を見ない */
export function executableProblem(path: string, os: OsKind): string | null {
  if (os !== 'windows') return null;
  if (WINDOWS_EXECUTABLE.test(path)) return null;
  return 'Windows では `.exe` か `.com` の絶対パスだけ使えます（`.cmd`・`.bat` は使えません）';
}

/** 設定の値から、PATH から探すか・絶対パスで決めるか・断るかを選ぶ。断るときも既定に黙って戻さない */
export function chooseCommand(value: unknown, os: OsKind): CommandChoice {
  if (value === undefined || value === DEFAULT_COMMAND) return { kind: 'search' };
  if (typeof value !== 'string') return { kind: 'refused', reason: '`pipe-in.command` は文字で書いてください' };
  if (value.trim() === '') return { kind: 'refused', reason: '`pipe-in.command` が空です。絶対パスを書いてください' };
  if (value !== value.trim()) return { kind: 'refused', reason: '`pipe-in.command` の前後に空白があります' };
  if (value.startsWith('-')) return { kind: 'refused', reason: '`pipe-in.command` は `-` で始められません。絶対パスを書いてください' };
  if (!isAbsolutePath(os, value)) return { kind: 'refused', reason: '`pipe-in.command` は絶対パスで書いてください（名前だけなら pipe-in）' };
  const problem = executableProblem(value, os);
  if (problem !== null) return { kind: 'refused', reason: problem };
  return { kind: 'fixed', path: value };
}

/** PATH の項目ごとの、実行ファイルの候補。絶対の項目だけを PATH の順に並べる。区切りと拡張子は OS から決める */
export function pathCandidates(pathEnv: string | undefined, os: OsKind): string[] {
  if (pathEnv === undefined || pathEnv === '') return [];
  const windows = os === 'windows';
  const names = windows ? ['pipe-in.exe', 'pipe-in.com'] : ['pipe-in'];
  const separator = windows ? '\\' : '/';
  const out: string[] = [];
  for (const raw of pathEnv.split(windows ? ';' : ':')) {
    // Windows の PATH は項目を " で囲むことがある。両端の " を1組だけ外す
    const item = windows && raw.length >= 2 && raw.startsWith('"') && raw.endsWith('"') ? raw.slice(1, -1) : raw;
    if (!isAbsolutePath(os, item)) continue;
    const last = item[item.length - 1];
    const dir = last === '/' || (windows && last === '\\') ? item.slice(0, -1) : item;
    for (const name of names) out.push(dir + separator + name);
  }
  return out;
}
