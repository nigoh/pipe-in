// 作業台から流すコマンドの形と、依頼メモの検め（D0078。domain/runCommand.ts）。AC-01〜04・15〜17・34・39〜43。
// 共通の表 tests/fixtures/run_command.json を、本体のテスト（tests/test_run_command.py）と一緒に読む（domain/costEstimate.test.ts と同じやり方）。
// 判断は純粋な関数に置いてあるので、偽物は要らない。時計・ファイル・子プロセスは使わない。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildRunCommand, isAbsolutePath, MAX_TEXT_LENGTH, previewRunCommand, TEXT_REASONS, textProblem } from './runCommand.ts';
import type { OsKind, RunCommandInput } from './runCommand.ts';

const HERE = path.dirname(fileURLToPath(import.meta.url));

interface Row { id: string; os?: OsKind; input: 'required' | 'optional' | 'none'; text: string; pipe_dir: string; project: string; args?: string[]; problem?: string; text_repeat?: { unit: string; count: number } }
const TABLE = JSON.parse(readFileSync(path.join(HERE, '..', '..', '..', 'tests', 'fixtures', 'run_command.json'), 'utf8')) as { executable: string; rows: Row[]; not_run: Row[] };

const EXE = '/usr/local/bin/pipe-in';
const WIN_EXE = 'D:\\tools\\pipe-in.exe';
const PIPE = '/work/app/.pipe-in/pipes/pipe-in-p';
const PROJECT = '/work/app';

function input(over: Partial<RunCommandInput> = {}): RunCommandInput {
  return { os: 'posix', executable: EXE, pipeDir: PIPE, project: PROJECT, input: 'required', text: 'メモ', ...over };
}
function fromRow(row: Row): RunCommandInput {
  const os = row.os ?? 'posix';
  const text = row.text_repeat ? row.text_repeat.unit.repeat(row.text_repeat.count) : row.text;
  return { os, executable: os === 'windows' ? WIN_EXE : TABLE.executable, pipeDir: row.pipe_dir, project: row.project, input: row.input, text };
}

// ---- AC-01：3つの引数 ----

test('D0078-AC-01: required と optional で、依頼メモがあると args は --pipe= --project= --text= の3つ（command は渡した絶対パスのまま）', () => {
  for (const mode of ['required', 'optional'] as const) {
    const r = buildRunCommand(input({ input: mode, text: '使い方を直して' }));
    assert.ok(r.ok, mode);
    if (!r.ok) return;
    assert.equal(r.command, EXE);
    assert.deepEqual(r.args, [`--pipe=${PIPE}`, `--project=${PROJECT}`, '--text=使い方を直して']);
  }
});

test('D0078-AC-01: 依頼メモは切らない・直さない（前後の空白も、そのまま --text= の後ろに付く）', () => {
  const r = buildRunCommand(input({ text: '  前後に空白  \n' }));
  assert.ok(r.ok);
  if (r.ok) assert.equal(r.args[2], '--text=  前後に空白  \n');
});

test('D0078-AC-01: 結果の鍵は ok・command・args だけ（env・shell・cwd を持たない）', () => {
  const r = buildRunCommand(input());
  assert.ok(r.ok);
  if (r.ok) assert.deepEqual(Object.keys(r).sort(), ['args', 'command', 'ok']);
});

// ---- AC-02：依頼メモが無いとき ----

for (const text of ['', ' ', '   ', '\t', '\n', '　　', ' \n\t　 ']) {
  test(`D0078-AC-02: optional で依頼メモが空（${JSON.stringify(text)}）なら args は2つで --text が付かない`, () => {
    const r = buildRunCommand(input({ input: 'optional', text }));
    assert.ok(r.ok);
    if (r.ok) assert.deepEqual(r.args, [`--pipe=${PIPE}`, `--project=${PROJECT}`]);
  });
}

test('D0078-AC-02: none は依頼メモを書いても args は2つ（--text を付けない。NUL や長すぎる文があっても断らない）', () => {
  for (const text of ['書いても渡さない', '', 'a\u0000b', 'x'.repeat(5000), '\ud800']) {
    const r = buildRunCommand(input({ input: 'none', text }));
    assert.ok(r.ok, JSON.stringify(text.slice(0, 10)));
    if (r.ok) assert.deepEqual(r.args, [`--pipe=${PIPE}`, `--project=${PROJECT}`]);
  }
});

// ---- AC-03：旗・シェルの文字でも1つの引数 ----

const TEXT_ROWS = TABLE.rows.filter((r) => r.args !== undefined && r.args.length === 3);

test('D0078-AC-03: 表に、旗・シェルの文字・引用符・複数行・日本語・省略形の行がそろっている（表が痩せていない）', () => {
  const ids = TABLE.rows.map((r) => r.id);
  for (const id of ['text-yes', 'text-help', 'text-after', 'text-text-flag', 'text-pipe-evil', 'text-review-approve', 'text-dashdash', 'text-leading-dash', 'text-equals', 'text-semicolon', 'text-subst', 'text-backtick', 'text-quotes', 'text-newline', 'text-japanese', 'text-long', 'text-abbrev-pipe', 'text-abbrev-project', 'text-abbrev-text']) {
    assert.ok(ids.includes(id), id);
  }
  assert.ok((TABLE.rows.find((r) => r.id === 'text-long')?.text.length ?? 0) > 250);
});

for (const row of TEXT_ROWS) {
  test(`D0078-AC-03: 表の行 ${row.id}：args は3つで、3つ目は --text= ＋依頼メモそのまま`, () => {
    const r = buildRunCommand(fromRow(row));
    assert.ok(r.ok);
    if (!r.ok) return;
    assert.equal(r.args.length, 3);
    assert.equal(r.args[2], `--text=${row.text}`);
    assert.equal(r.args[0], `--pipe=${row.pipe_dir}`);
    assert.equal(r.args[1], `--project=${row.project}`);
  });
}

// ---- AC-04：パスは絶対パスだけ ----

const BAD_PATHS: readonly (readonly [string, string])[] = [
  ['空', ''],
  ['相対（pipes/p）', 'pipes/pipe-in-p'],
  ['相対（./）', './pipe-in-p'],
  ['相対（..）', '../pipe-in-p'],
  ['名前だけ', 'pipe-in-p'],
  ['NUL を含む', '/work/app/\u0000x'],
  ['改行を含む', '/work/app\n--yes'],
  ['CR を含む', '/work/app\r--yes'],
  ['Windows の根だけの \\foo', '\\foo'],
  ['ドライブ文字だけで相対（C:foo）', 'C:foo'],
];

for (const [label, bad] of BAD_PATHS) {
  test(`D0078-AC-04: パイプのフォルダが ${label} なら断る`, () => {
    const r = buildRunCommand(input({ pipeDir: bad }));
    assert.equal(r.ok, false);
    if (!r.ok) assert.ok(r.reason.length > 0);
  });
  test(`D0078-AC-04: プロジェクトが ${label} なら断る`, () => {
    const r = buildRunCommand(input({ project: bad }));
    assert.equal(r.ok, false);
  });
  test(`D0078-AC-04: 実行ファイルが ${label} なら断る（名前だけを PATH 任せで起こす道が無い）`, () => {
    const r = buildRunCommand(input({ executable: bad }));
    assert.equal(r.ok, false);
  });
}

test('D0078-AC-04: 実行ファイルが pipe-in（名前だけ）でも断る', () => {
  assert.equal(buildRunCommand(input({ executable: 'pipe-in' })).ok, false);
});

const GOOD_PATHS: readonly (readonly [string, OsKind, string])[] = [
  ['空白を含む', 'posix', '/work/my app/.pipe-in/pipes/pipe-in-p'],
  ['= を含む', 'posix', '/work/a=b/.pipe-in/pipes/pipe-in-p'],
  ['日本語を含む', 'posix', '/work/アプリ/.pipe-in/pipes/pipe-in-p'],
  ['先頭が - のフォルダ名を含む', 'posix', '/work/-x/pipe-in-p'],
  ['Windows のドライブ（D:\\）', 'windows', 'D:\\work\\app\\.pipe-in\\pipes\\pipe-in-p'],
  ['Windows のドライブ（D:/）', 'windows', 'D:/work/app/.pipe-in/pipes/pipe-in-p'],
  ['Windows の UNC', 'windows', '\\\\server\\share\\app\\.pipe-in\\pipes\\pipe-in-p'],
];

for (const [label, os, good] of GOOD_PATHS) {
  test(`D0078-AC-04: パイプのフォルダが ${label} でも、そのまま1つの引数になる`, () => {
    const exe = os === 'windows' ? WIN_EXE : EXE;
    const r = buildRunCommand(input({ os, executable: exe, pipeDir: good, project: good }));
    assert.ok(r.ok);
    if (r.ok) {
      assert.equal(r.args[0], `--pipe=${good}`);
      assert.equal(r.args[1], `--project=${good}`);
      assert.equal(r.command, exe);
    }
  });
}

const ABSOLUTE_CASES: readonly (readonly [OsKind, unknown, boolean])[] = [
  ['posix', '/usr/bin/pipe-in', true],
  ['posix', '/', true],
  ['posix', '', false],
  ['posix', 'usr/bin', false],
  ['posix', './x', false],
  ['posix', 'C:\\x', false],
  ['posix', '/x\u0000', false],
  ['posix', '/x\n', false],
  ['posix', '/x\r', false],
  ['posix', 42, false],
  ['posix', null, false],
  ['posix', undefined, false],
  ['windows', 'C:\\tools\\pipe-in.exe', true],
  ['windows', 'c:/tools/pipe-in.exe', true],
  ['windows', '\\\\server\\share\\pipe-in.exe', true],
  ['windows', '\\\\?\\C:\\tools\\pipe-in.exe', false],
  ['windows', '\\\\.\\pipe\\x', false],
  ['windows', '\\\\server', false],
  ['windows', '\\foo', false],
  ['windows', '/usr/bin/pipe-in', false],
  ['windows', 'C:foo', false],
  ['windows', 'tools\\pipe-in.exe', false],
  ['windows', 'C:\\x\u0000', false],
  ['windows', 'C:\\x\n', false],
  ['windows', '', false],
  ['windows', 7, false],
];

for (const [os, value, expected] of ABSOLUTE_CASES) {
  test(`D0078-AC-04: isAbsolutePath(${os}, ${JSON.stringify(value)}) は ${expected}`, () => {
    assert.equal(isAbsolutePath(os, value), expected);
  });
}

// ---- AC-15〜17：依頼メモの検め（textProblem と二重の守り） ----

test('D0078-AC-16: 上限は 4000（UTF-16 の単位）で、理由の文は4つとも空でない', () => {
  assert.equal(MAX_TEXT_LENGTH, 4000);
  for (const k of ['empty', 'tooLong', 'nul', 'broken'] as const) assert.ok(TEXT_REASONS[k].length > 0, k);
  assert.match(TEXT_REASONS.empty, /依頼メモ/);
  assert.match(TEXT_REASONS.tooLong, /4,000/);
  assert.match(TEXT_REASONS.nul, /NUL/);
  assert.match(TEXT_REASONS.broken, /壊れ|サロゲート/);
});

test('D0078-AC-15: textProblem：required は空・空白だけ（全角空白・改行・タブを含む）で empty。optional と none は問題にしない', () => {
  for (const text of ['', ' ', '\t', '\n', '\r\n', '　', ' \n\t　 ']) {
    assert.equal(textProblem('required', text), 'empty', JSON.stringify(text));
    assert.equal(textProblem('optional', text), null, JSON.stringify(text));
    assert.equal(textProblem('none', text), null, JSON.stringify(text));
  }
  assert.equal(textProblem('required', 'a'), null);
});

test('D0078-AC-16: textProblem：4,000 ちょうどは通り、4,001 は tooLong。サロゲートペアは 2 と数える。none は見ない', () => {
  assert.equal(textProblem('required', 'a'.repeat(4000)), null);
  assert.equal(textProblem('required', 'a'.repeat(4001)), 'tooLong');
  assert.equal(textProblem('optional', 'a'.repeat(4001)), 'tooLong');
  assert.equal(textProblem('required', '😀'.repeat(2000)), null);
  assert.equal(textProblem('required', '😀'.repeat(2000) + 'a'), 'tooLong');
  assert.equal(textProblem('required', '😀'.repeat(2001)), 'tooLong');
  assert.equal(textProblem('none', 'a'.repeat(9999)), null);
});

test('D0078-AC-17: textProblem：NUL は nul、対にならないサロゲートは broken、対になったもの（絵文字）は通る', () => {
  assert.equal(textProblem('required', 'a\u0000b'), 'nul');
  assert.equal(textProblem('optional', '\u0000'), 'nul');
  assert.equal(textProblem('required', 'a\ud800b'), 'broken');
  assert.equal(textProblem('required', 'a\udc00b'), 'broken');
  assert.equal(textProblem('required', '末尾\ud800'), 'broken');
  assert.equal(textProblem('required', '\udc00\ud800'), 'broken', '順が逆の2つは対ではない');
  assert.equal(textProblem('required', '😀'), null);
  assert.equal(textProblem('required', 'a😀b'), null);
  assert.equal(textProblem('none', 'a\u0000\ud800'), null);
});

test('D0078-AC-17: textProblem：複数当たるときの順は empty → tooLong → nul → broken', () => {
  assert.equal(textProblem('required', 'a'.repeat(4001) + '\u0000\ud800'), 'tooLong');
  assert.equal(textProblem('required', 'a\u0000\ud800'), 'nul');
  assert.equal(textProblem('required', '\ud800'), 'broken');
  assert.equal(textProblem('required', ' \u0000'), 'nul', 'NUL は空白ではないので empty にならない');
});

const GUARDED: readonly (readonly [string, RunCommandInput['input'], string])[] = [
  ['required の空', 'required', ''],
  ['required の空白だけ', 'required', '　 \n'],
  ['長すぎる', 'required', 'a'.repeat(4001)],
  ['NUL', 'optional', 'a\u0000b'],
  ['対にならない上位サロゲート', 'required', 'a\ud800'],
  ['対にならない下位サロゲート', 'optional', '\udc00'],
];

for (const [label, mode, text] of GUARDED) {
  test(`D0078-AC-15: buildRunCommand は textProblem が出るもの（${label}）を断る（二重の守り）`, () => {
    const r = buildRunCommand(input({ input: mode, text }));
    assert.equal(r.ok, false);
    if (!r.ok) assert.ok(r.reason.length > 0);
  });
}

test('D0078-AC-17: buildRunCommand は 4,000 ちょうどと絵文字の文を通す', () => {
  assert.ok(buildRunCommand(input({ text: 'a'.repeat(4000) })).ok);
  assert.ok(buildRunCommand(input({ text: '😀'.repeat(2000) })).ok);
});

// ---- AC-34：共通の表 ----

test('D0078-AC-34: run_command.json の rows の入力から作った args が、表の期待と等しい（optional の空・none の行を含む）', () => {
  assert.ok(TABLE.rows.length >= 28);
  assert.ok(TABLE.rows.some((r) => r.input === 'optional' && r.args?.length === 2));
  assert.ok(TABLE.rows.some((r) => r.input === 'none'));
  for (const row of TABLE.rows) {
    const r = buildRunCommand(fromRow(row));
    assert.ok(r.ok, row.id);
    if (r.ok) {
      assert.deepEqual(r.args, row.args, row.id);
      assert.equal(r.command, fromRow(row).executable, row.id);
    }
  }
});

const PROBLEM_TO_TEXT: Record<string, ReturnType<typeof textProblem>> = { textEmpty: 'empty', textTooLong: 'tooLong', textNul: 'nul', textBroken: 'broken' };

for (const row of TABLE.not_run) {
  test(`D0078-AC-34: 表の not_run の行 ${row.id}（${row.problem}）は buildRunCommand が断る`, () => {
    const r = buildRunCommand(fromRow(row));
    assert.equal(r.ok, false);
  });
  const problem = row.problem;
  if (problem !== undefined && problem !== 'path') {
    test(`D0078-AC-34: 表の not_run の行 ${row.id} は textProblem が ${PROBLEM_TO_TEXT[problem]} を返す`, () => {
      const { input: mode, text } = fromRow(row);
      assert.equal(textProblem(mode, text), PROBLEM_TO_TEXT[problem]);
    });
  }
}

// ---- 画面に見せる形（previewRunCommand。AC-39〜43 の支え） ----

test('D0078-AC-39: previewRunCommand：required で依頼メモが空のときだけ、3つ目が --text=<依頼メモ> の仮の文字で placeholder: true（形が見える）', () => {
  const r = previewRunCommand(input({ input: 'required', text: '' }));
  assert.ok(r.ok);
  if (r.ok) {
    assert.equal(r.placeholder, true);
    assert.equal(r.command, EXE);
    assert.deepEqual(r.args, [`--pipe=${PIPE}`, `--project=${PROJECT}`, '--text=<依頼メモ>']);
  }
  const blank = previewRunCommand(input({ input: 'required', text: '　 ' }));
  assert.ok(blank.ok);
  if (blank.ok) assert.equal(blank.placeholder, true);
});

test('D0078-AC-40: previewRunCommand：依頼メモがあれば、本物の --text=… で placeholder: false', () => {
  const r = previewRunCommand(input({ input: 'required', text: '使い方を直して' }));
  assert.ok(r.ok);
  if (r.ok) {
    assert.equal(r.placeholder, false);
    assert.equal(r.args[2], '--text=使い方を直して');
  }
});

test('D0078-AC-42: previewRunCommand：optional で空なら args は2つ（仮の文字を出さない）。書けば3つ', () => {
  const empty = previewRunCommand(input({ input: 'optional', text: '' }));
  assert.ok(empty.ok);
  if (empty.ok) {
    assert.equal(empty.placeholder, false);
    assert.equal(empty.args.length, 2);
  }
  const typed = previewRunCommand(input({ input: 'optional', text: 'README を直して' }));
  assert.ok(typed.ok);
  if (typed.ok) assert.equal(typed.args.length, 3);
});

test('D0078-AC-43: previewRunCommand：none は依頼メモがあっても args は2つ', () => {
  const r = previewRunCommand(input({ input: 'none', text: '書いても渡さない' }));
  assert.ok(r.ok);
  if (r.ok) {
    assert.equal(r.placeholder, false);
    assert.equal(r.args.length, 2);
  }
});

test('D0078-AC-04: previewRunCommand も絶対パスでなければ断り、長すぎる依頼メモなど buildRunCommand が断るものは断る', () => {
  assert.equal(previewRunCommand(input({ pipeDir: 'pipes/p' })).ok, false);
  assert.equal(previewRunCommand(input({ project: '' })).ok, false);
  assert.equal(previewRunCommand(input({ executable: 'pipe-in' })).ok, false);
  assert.equal(previewRunCommand(input({ text: 'a'.repeat(4001) })).ok, false);
  assert.equal(previewRunCommand(input({ text: 'a\u0000' })).ok, false);
});

test('D0078-AC-34: previewRunCommand は placeholder 以外では buildRunCommand と同じ args を返す（表の全行）', () => {
  for (const row of TABLE.rows) {
    const built = buildRunCommand(fromRow(row));
    const shown = previewRunCommand(fromRow(row));
    assert.ok(built.ok && shown.ok, row.id);
    if (built.ok && shown.ok) assert.deepEqual(shown.args, built.args, row.id);
  }
});
