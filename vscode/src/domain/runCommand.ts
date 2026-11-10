// 作業台から流すコマンドの形と、依頼メモの検め（D0078）。作業台のパネルも読むので、外の部品（node:・vscode・パッケージ）を import しない。
// 絶対パスの判断は、動かしている OS に頼らず、OS の種類（'windows' | 'posix'）を引数で受ける正規表現で行う（Linux の CI でも同じ判断を確かめられる）。
import type { InputMode } from './pipeModel.ts';

export type OsKind = 'windows' | 'posix';
/** 依頼メモの長さの上限（UTF-16 の単位。JS の文字列の length） */
export const MAX_TEXT_LENGTH = 4000;
export type TextProblem = 'empty' | 'tooLong' | 'nul' | 'broken';
/** 依頼メモの問題ごとの理由の文。decideRun も同じ文を使う */
export const TEXT_REASONS: Record<TextProblem, string> = {
  empty: '依頼メモを書いてください',
  tooLong: '依頼メモが長すぎます（4,000 文字まで。UTF-16 の長さで数えます）',
  nul: '依頼メモに使えない文字（NUL）が含まれています',
  broken: '依頼メモに壊れた文字（対にならないサロゲート）が含まれています',
};

const CONTROL = /[\u0000\r\n]/;
const WINDOWS_DRIVE = /^[A-Za-z]:[\\/]/;
// UNC（\\server\share）。\\?\ と \\.\ の装置のパスは絶対としない
const WINDOWS_UNC = /^\\\\[^\\/?.]+\\[^\\/]+/;

/** 絶対パスか。NUL・CR・LF を含むもの、空のものは絶対としない */
export function isAbsolutePath(os: OsKind, value: unknown): value is string {
  if (typeof value !== 'string' || value === '' || CONTROL.test(value)) return false;
  if (os === 'posix') return value.startsWith('/');
  return WINDOWS_DRIVE.test(value) || WINDOWS_UNC.test(value);
}

function hasLoneSurrogate(text: string): boolean {
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      const next = text.charCodeAt(i + 1);
      if (next >= 0xdc00 && next <= 0xdfff) i++;
      else return true;
    } else if (c >= 0xdc00 && c <= 0xdfff) {
      return true;
    }
  }
  return false;
}

/** 依頼メモの問題。複数当たるときの順は empty → tooLong → nul → broken。none は見ない。optional の空は問題にしない（渡さないだけ） */
export function textProblem(input: InputMode, text: string): TextProblem | null {
  if (input === 'none') return null;
  if (text.trim() === '') return input === 'required' ? 'empty' : null;
  if (text.length > MAX_TEXT_LENGTH) return 'tooLong';
  if (text.includes('\u0000')) return 'nul';
  if (hasLoneSurrogate(text)) return 'broken';
  return null;
}

export interface RunCommand { command: string; args: string[] }
export type BuildResult = ({ ok: true } & RunCommand) | { ok: false; reason: string };
export interface RunCommandInput { os: OsKind; executable: string; pipeDir: string; project: string; input: InputMode; text: string }

/**
 * 起こすコマンドを作る。引数は --pipe= と --project= のあと、依頼メモがあるときだけ --text=（そのまま。切らない・直さない・包まない）。
 * 依頼メモは --text= の中の1要素なので、旗やシェルの文字として読まれない。
 */
export function buildRunCommand(i: RunCommandInput): BuildResult {
  if (!isAbsolutePath(i.os, i.executable)) return { ok: false, reason: '実行ファイルが絶対パスではありません' };
  if (!isAbsolutePath(i.os, i.pipeDir)) return { ok: false, reason: 'パイプのフォルダが絶対パスではありません' };
  if (!isAbsolutePath(i.os, i.project)) return { ok: false, reason: 'プロジェクトのフォルダが絶対パスではありません' };
  const problem = textProblem(i.input, i.text);
  if (problem !== null) return { ok: false, reason: TEXT_REASONS[problem] };
  const args = [`--pipe=${i.pipeDir}`, `--project=${i.project}`];
  if (i.input !== 'none' && i.text.trim() !== '') args.push(`--text=${i.text}`);
  return { ok: true, command: i.executable, args };
}

const PLACEHOLDER_TEXT = '<依頼メモ>';

/** 画面に形を見せる用。required で依頼メモが空のときだけ、3つ目を仮の文字にして placeholder: true を返す。ほかは buildRunCommand と同じ */
export function previewRunCommand(i: RunCommandInput): ({ ok: true; placeholder: boolean } & RunCommand) | { ok: false; reason: string } {
  const placeholder = i.input === 'required' && i.text.trim() === '';
  const built = buildRunCommand(placeholder ? { ...i, text: PLACEHOLDER_TEXT } : i);
  if (!built.ok) return built;
  return { ok: true, placeholder, command: built.command, args: built.args };
}
