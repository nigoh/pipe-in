// 作業台から流す計画（D0078。app/runFlow.ts）。AC-12・24・29・38 の支え。
// 保存済みの形と開いたパイプから「今の事実」を作る runContextFor と、判断とコマンドの形を通す planRun。偽物は手で書いた小さな関数だけ。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { newPipe, newStage, validatePipe } from '../domain/pipeModel.ts';
import type { InputMode, PipeModel } from '../domain/pipeModel.ts';
import { decideRun } from '../domain/runDecision.ts';
import type { RunContext } from '../domain/runDecision.ts';
import { planRun, runContextFor } from './runFlow.ts';
import type { PipeRef } from './pipeEditor.ts';

const EXE = { ok: true, path: '/usr/local/bin/pipe-in' } as const;
const PROJECT = '/work/app';
const REF: PipeRef = { name: 'p', dir: '/work/app/.pipe-in/pipes', folder: 'pipe-in-p', legacy: false };
const LEGACY_REF: PipeRef = { name: 'x', dir: '/work/app/.devpipe/pipes', folder: 'devpipe-x', legacy: true };

function validModel(input: InputMode = 'required', name = 'p'): PipeModel {
  return { ...newPipe(name), input, stages: [{ ...newStage('s1', 'research', 'survey'), prompt: '調べる' }] };
}

function context(over: Partial<Parameters<typeof runContextFor>[0]> = {}): RunContext {
  return runContextFor({ ref: REF, saved: validModel(), project: PROJECT, trusted: true, executable: EXE, isRunning: () => false, ...over });
}

// ---- runContextFor（AC-12・38） ----

test('D0078-AC-12: runContextFor：保存済みの形が検査を通れば savedErrors は 0、input は保存済みの形の input', () => {
  assert.deepEqual(validatePipe(validModel()).errors, [], '前提：見本の形に誤りが無い');
  const c = context();
  assert.equal(c.savedErrors, 0);
  assert.equal(c.input, 'required');
  assert.equal(context({ saved: validModel('optional') }).input, 'optional');
  assert.equal(context({ saved: validModel('none') }).input, 'none');
});

test('D0078-AC-12: runContextFor の savedErrors は保存済みの形の validatePipe から数える（段が無いパイプは誤りが 1 件以上）', () => {
  const broken = newPipe('p');
  const expected = validatePipe(broken).errors.length;
  assert.ok(expected > 0, '前提：段の無いパイプは誤りがある');
  assert.equal(context({ saved: broken }).savedErrors, expected);
});

test('D0078-AC-12: runContextFor の引数は ref・saved・project・trusted・executable・isRunning だけ（パネルの値を受け取る口が無い）', () => {
  const source = readFileSync(new URL('./runFlow.ts', import.meta.url), 'utf8');
  const m = /export function runContextFor\(\s*i:\s*\{([^}]*)\}/.exec(source);
  assert.notEqual(m, null, 'runContextFor の宣言が読めない');
  const params = m?.[1] ?? '';
  for (const key of ['ref', 'saved', 'project', 'trusted', 'executable', 'isRunning']) assert.match(params, new RegExp(`\\b${key}\\s*:`), key);
  assert.doesNotMatch(params, /\b(?:dirty|text|panel|input|savedErrors|running)\s*:/, 'パネルから来た値・計算済みの値を受け取る口が無い');
});

test('D0078-AC-12: runContextFor：project・trusted・executable は渡した値のまま', () => {
  const c = context({ project: null, trusted: false, executable: { ok: false, reason: '見つかりません' } });
  assert.equal(c.project, null);
  assert.equal(c.trusted, false);
  assert.deepEqual(c.executable, { ok: false, reason: '見つかりません' });
  assert.deepEqual(Object.keys(context()).sort(), ['executable', 'input', 'pipeDir', 'project', 'running', 'savedErrors', 'trusted']);
});

test('D0078-AC-38: runContextFor：pipeDir は path.resolve(ref.dir, ref.folder)。前の版の置き場所・フォルダ名のパイプも同じ', () => {
  assert.equal(context().pipeDir, path.resolve('/work/app/.pipe-in/pipes', 'pipe-in-p'));
  assert.equal(context({ ref: LEGACY_REF, saved: validModel('required', 'x') }).pipeDir, path.resolve('/work/app/.devpipe/pipes', 'devpipe-x'));
});

test('D0078-AC-10: runContextFor：まだ一度も保存していない（ref が null）なら pipeDir は null で、running を聞きに行かない', () => {
  const asked: string[] = [];
  const c = context({ ref: null, isRunning: (d) => { asked.push(d); return true; } });
  assert.equal(c.pipeDir, null);
  assert.equal(c.running, false);
  assert.deepEqual(asked, []);
});

test('D0078-AC-19: runContextFor：running は isRunning(pipeDir) の答え（絶対パスで聞く）', () => {
  const asked: string[] = [];
  const c = context({ isRunning: (d) => { asked.push(d); return true; } });
  assert.equal(c.running, true);
  assert.deepEqual(asked, [path.resolve('/work/app/.pipe-in/pipes', 'pipe-in-p')]);
  assert.equal(context({ isRunning: () => false }).running, false);
});

// ---- planRun（AC-24・38） ----

test('D0078-AC-24: planRun：流してよいなら、command は executable.path、args は決まった形、cwd は project、pipeDir は ctx の値', () => {
  const c = context();
  const plan = planRun(c, false, '使い方を直して', 'posix');
  assert.deepEqual(plan, {
    ok: true,
    command: '/usr/local/bin/pipe-in',
    args: [`--pipe=${c.pipeDir}`, `--project=${PROJECT}`, '--text=使い方を直して'],
    cwd: PROJECT,
    pipeDir: c.pipeDir,
  });
});

test('D0078-AC-24: planRun の ok の結果の鍵は ok・command・args・cwd・pipeDir だけ（env・shell を持たない）', () => {
  const plan = planRun(context(), false, 'メモ', 'posix');
  assert.deepEqual(Object.keys(plan).sort(), ['args', 'command', 'cwd', 'ok', 'pipeDir']);
});

test('D0078-AC-02: planRun：none は依頼メモを書いても args は2つ。optional の空も2つ', () => {
  const none = planRun(context({ saved: validModel('none') }), false, '書いても渡さない', 'posix');
  assert.ok(none.ok);
  if (none.ok) assert.equal(none.args.length, 2);
  const optional = planRun(context({ saved: validModel('optional') }), false, '', 'posix');
  assert.ok(optional.ok);
  if (optional.ok) assert.equal(optional.args.length, 2);
});

const CASES: readonly (readonly [string, Partial<Parameters<typeof runContextFor>[0]>, boolean, string])[] = [
  ['信頼していない', { trusted: false }, false, 'メモ'],
  ['プロジェクトが無い', { project: null }, false, 'メモ'],
  ['実行ファイルが決まらない', { executable: { ok: false, reason: '見つかりません' } }, false, 'メモ'],
  ['実行中', { isRunning: () => true }, false, 'メモ'],
  ['保存していない（ref が null）', { ref: null }, false, 'メモ'],
  ['保存していない変更がある', {}, true, 'メモ'],
  ['検査の誤りがある', { saved: newPipe('p') }, false, 'メモ'],
  ['required で依頼メモが空', {}, false, '　'],
  ['依頼メモが長すぎる', {}, false, 'a'.repeat(4001)],
  ['依頼メモに NUL', {}, false, 'a\u0000'],
  ['依頼メモに壊れた文字', {}, false, 'a\ud800'],
];

for (const [label, over, dirty, text] of CASES) {
  test(`D0078-AC-20: planRun：${label}ときは、decideRun と同じ理由で ok: false（command を返さない）`, () => {
    const c = context(over);
    const expected = decideRun(c, dirty, text);
    assert.equal(expected.ok, false, '前提：decideRun が断る');
    const plan = planRun(c, dirty, text, 'posix');
    assert.equal(plan.ok, false);
    if (!plan.ok && !expected.ok) assert.equal(plan.reason, expected.reason);
    assert.ok(!('command' in plan));
  });
}

test('D0078-AC-12: planRun：ctx.executable.ok が偽なら、その reason をそのまま返す', () => {
  const plan = planRun(context({ executable: { ok: false, reason: '`pipe-in` が見つかりません' } }), false, 'メモ', 'posix');
  assert.deepEqual(plan, { ok: false, reason: '`pipe-in` が見つかりません' });
});

test('D0078-AC-04: planRun：判断を通っても、ctx.pipeDir や project が絶対パスでなければ buildRunCommand が断り、その理由を返す（二重の守り）', () => {
  const c: RunContext = { ...context(), pipeDir: 'pipes/pipe-in-p' };
  const plan = planRun(c, false, 'メモ', 'posix');
  assert.equal(plan.ok, false);
  const c2: RunContext = { ...context(), project: 'app' };
  assert.equal(planRun(c2, false, 'メモ', 'posix').ok, false);
  const c3: RunContext = { ...context(), executable: { ok: true, path: 'pipe-in' } };
  assert.equal(planRun(c3, false, 'メモ', 'posix').ok, false);
});

test('D0078-AC-38: 前の版の置き場所（.devpipe/pipes/devpipe-x）の ref でも planRun の --pipe= は、そのフォルダの絶対パス', () => {
  const c = context({ ref: LEGACY_REF, saved: validModel('required', 'x') });
  const plan = planRun(c, false, 'メモ', 'posix');
  assert.ok(plan.ok);
  if (plan.ok) {
    assert.equal(plan.args[0], `--pipe=${path.resolve('/work/app/.devpipe/pipes', 'devpipe-x')}`);
    assert.equal(plan.pipeDir, path.resolve('/work/app/.devpipe/pipes', 'devpipe-x'));
  }
});

test('D0078-AC-38: pipeDir が null（保存前）は断る。理由は「先に保存」', () => {
  const plan = planRun(context({ ref: null }), false, 'メモ', 'posix');
  assert.equal(plan.ok, false);
  if (!plan.ok) assert.match(plan.reason, /先に保存/);
});

test('D0078-AC-04: planRun(windows)：Windows の絶対パスで args が決まる', () => {
  const c: RunContext = {
    input: 'required',
    pipeDir: 'D:\\work\\app\\.pipe-in\\pipes\\pipe-in-p',
    savedErrors: 0,
    project: 'D:\\work\\app',
    trusted: true,
    executable: { ok: true, path: 'D:\\tools\\pipe-in.exe' },
    running: false,
  };
  const plan = planRun(c, false, 'メモ', 'windows');
  assert.deepEqual(plan, {
    ok: true,
    command: 'D:\\tools\\pipe-in.exe',
    args: ['--pipe=D:\\work\\app\\.pipe-in\\pipes\\pipe-in-p', '--project=D:\\work\\app', '--text=メモ'],
    cwd: 'D:\\work\\app',
    pipeDir: 'D:\\work\\app\\.pipe-in\\pipes\\pipe-in-p',
  });
});

test('D0078-AC-33: runFlow.ts は書く呼び出しも node:fs も vscode も読まない（計画を作るだけ）', () => {
  const code = readFileSync(new URL('./runFlow.ts', import.meta.url), 'utf8').replace(/^[ \t]*\/\/.*$/gm, '');
  assert.doesNotMatch(code, /node:fs|from 'vscode'|\b(?:writeFile|appendFile|mkdir|rename|unlink)\b|child_process/);
});
