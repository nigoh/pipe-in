// 作業台から流す実行ファイルの決め方のうち、純粋な部分（D0078。domain/runExecutable.ts）。AC-05〜08・18（PATH の候補・設定の値・Windows の拡張子）。
// 実際にファイルがあるかを見る手順は app/runExecutable.test.ts。ここはファイルに触れない。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chooseCommand, DEFAULT_COMMAND, executableProblem, NOT_FOUND_REASON, pathCandidates, userCommandValue } from './runExecutable.ts';

test('D0078-AC-05: 既定のコマンド名は pipe-in', () => {
  assert.equal(DEFAULT_COMMAND, 'pipe-in');
});

test('D0078-AC-55: 見つからないときの理由に pipe-in・見つかりません・設定 pipe-in.command・絶対パスが出る（設定を案内する）', () => {
  for (const word of ['`pipe-in`', '見つかりません', '`pipe-in.command`', '絶対パス']) assert.ok(NOT_FOUND_REASON.includes(word), word);
});

// ---- 設定の値（AC-05・26 の支え） ----

test('D0078-AC-05: userCommandValue：globalValue が undefined でなければそれ、なければ defaultValue', () => {
  assert.equal(userCommandValue({ globalValue: '/opt/pipe-in', defaultValue: 'pipe-in' }), '/opt/pipe-in');
  assert.equal(userCommandValue({ globalValue: undefined, defaultValue: 'pipe-in' }), 'pipe-in');
  assert.equal(userCommandValue({ defaultValue: 'pipe-in' }), 'pipe-in');
  assert.equal(userCommandValue({}), undefined);
  assert.equal(userCommandValue({ globalValue: '', defaultValue: 'pipe-in' }), '', '空の文字も書かれた値として返す（既定に黙って戻さない）');
  assert.equal(userCommandValue({ globalValue: null, defaultValue: 'pipe-in' }), null);
});

test('D0078-AC-26: userCommandValue はワークスペースの値を受け取らない（鍵が付いていても読まない）', () => {
  const hostile = { globalValue: undefined, defaultValue: 'pipe-in', workspaceValue: '/evil/pipe-in', workspaceFolderValue: '/evil/pipe-in' };
  assert.equal(userCommandValue(hostile), 'pipe-in');
  const both = { globalValue: '/opt/pipe-in', defaultValue: 'pipe-in', workspaceValue: '/evil/pipe-in', workspaceFolderValue: '/evil/pipe-in' };
  assert.equal(userCommandValue(both), '/opt/pipe-in');
});

// ---- chooseCommand（AC-05） ----

test('D0078-AC-05: chooseCommand：未設定か、ちょうど pipe-in なら search', () => {
  for (const os of ['posix', 'windows'] as const) {
    assert.deepEqual(chooseCommand(undefined, os), { kind: 'search' });
    assert.deepEqual(chooseCommand('pipe-in', os), { kind: 'search' });
  }
});

const FIXED: readonly (readonly ['posix' | 'windows', string])[] = [
  ['posix', '/usr/local/bin/pipe-in'],
  ['posix', '/work/my app/.venv/bin/pipe-in'],
  ['posix', '/opt/アプリ/pipe-in'],
  ['windows', 'C:\\tools\\pipe-in.exe'],
  ['windows', 'D:/tools/pipe-in.exe'],
  ['windows', '\\\\server\\share\\pipe-in.exe'],
  ['windows', 'C:\\tools\\pipe-in.EXE'],
  ['windows', 'C:\\tools\\pipe-in.com'],
];

for (const [os, value] of FIXED) {
  test(`D0078-AC-05: chooseCommand(${JSON.stringify(value)}, ${os}) は fixed で、値のまま`, () => {
    assert.deepEqual(chooseCommand(value, os), { kind: 'fixed', path: value });
  });
}

const REFUSED: readonly (readonly [string, unknown])[] = [
  ['相対（bin/pipe-in）', 'bin/pipe-in'],
  ['./pipe-in', './pipe-in'],
  ['../pipe-in', '../pipe-in'],
  ['pipe-in2', 'pipe-in2'],
  ['大文字の Pipe-in', 'Pipe-in'],
  ['引数つき', 'pipe-in --yes'],
  ['- で始まる', '-x'],
  ['-- で始まる', '--pipe=/x'],
  ['前に空白', ' /usr/local/bin/pipe-in'],
  ['後ろに空白', '/usr/local/bin/pipe-in '],
  ['空', ''],
  ['空白だけ', '   '],
  ['改行を含む', '/usr/local/bin/pipe-in\n--yes'],
  ['CR を含む', '/usr/local/bin/pipe-in\r'],
  ['NUL を含む', '/usr/local/bin/pipe-in\u0000'],
  ['数', 42],
  ['null', null],
  ['真偽', true],
  ['配列', ['/usr/local/bin/pipe-in']],
  ['オブジェクト', { path: '/usr/local/bin/pipe-in' }],
];

for (const [label, value] of REFUSED) {
  for (const os of ['posix', 'windows'] as const) {
    test(`D0078-AC-05: chooseCommand：${label} は refused（理由つき。既定に黙って戻さない）[${os}]`, () => {
      const r = chooseCommand(value, os);
      assert.equal(r.kind, 'refused');
      if (r.kind === 'refused') assert.ok(r.reason.length > 0);
    });
  }
}

test('D0078-AC-05: chooseCommand：OS に合わない絶対パスは refused（posix で C:\\…、windows で /usr/…）', () => {
  assert.equal(chooseCommand('C:\\tools\\pipe-in.exe', 'posix').kind, 'refused');
  assert.equal(chooseCommand('/usr/local/bin/pipe-in', 'windows').kind, 'refused');
  assert.equal(chooseCommand('\\foo\\pipe-in.exe', 'windows').kind, 'refused');
});

// ---- Windows の拡張子（AC-08） ----

test('D0078-AC-08: chooseCommand：Windows で .cmd・.bat・拡張子なしの絶対パスは refused（.exe・.com だけ）', () => {
  for (const value of ['C:\\tools\\pipe-in.cmd', 'C:\\tools\\pipe-in.bat', 'C:\\tools\\pipe-in', 'C:\\tools\\pipe-in.ps1', 'C:\\tools\\pipe-in.exe.cmd']) {
    assert.equal(chooseCommand(value, 'windows').kind, 'refused', value);
  }
});

test('D0078-AC-08: chooseCommand：posix は絶対パスなら拡張子を見ない', () => {
  for (const value of ['/usr/local/bin/pipe-in.cmd', '/usr/local/bin/pipe-in.sh', '/usr/local/bin/pipe-in']) {
    assert.deepEqual(chooseCommand(value, 'posix'), { kind: 'fixed', path: value });
  }
});

test('D0078-AC-08: executableProblem：windows で最後の要素が .exe・.com（大小文字を問わない）なら null、そうでなければ理由', () => {
  for (const ok of ['C:\\a\\pipe-in.exe', 'C:\\a\\pipe-in.com', 'C:\\a\\pipe-in.EXE', 'C:\\a\\pipe-in.Com', 'C:/a/pipe-in.exe', 'C:\\a.b\\pipe-in.exe']) {
    assert.equal(executableProblem(ok, 'windows'), null, ok);
  }
  for (const bad of ['C:\\a\\pipe-in.cmd', 'C:\\a\\pipe-in.bat', 'C:\\a\\pipe-in', 'C:\\a.exe\\pipe-in', 'C:\\a\\.exe', 'C:\\a\\pipe-in.exe\\', 'C:\\a\\pipe-in.exe.txt']) {
    const r = executableProblem(bad, 'windows');
    assert.equal(typeof r, 'string', bad);
    assert.ok((r ?? '').length > 0, bad);
  }
});

test('D0078-AC-08: executableProblem：posix は拡張子を見ず、常に null', () => {
  for (const value of ['/usr/bin/pipe-in', '/usr/bin/pipe-in.cmd', '/usr/bin/pipe-in.bat', '/usr/bin/.exe']) {
    assert.equal(executableProblem(value, 'posix'), null, value);
  }
});

// ---- PATH の候補（AC-06・07） ----

test('D0078-AC-06: pathCandidates(posix)：項目ごとに <項目>/pipe-in を、PATH の順に並べる', () => {
  assert.deepEqual(pathCandidates('/usr/local/bin:/usr/bin:/bin', 'posix'), ['/usr/local/bin/pipe-in', '/usr/bin/pipe-in', '/bin/pipe-in']);
});

test('D0078-AC-06: pathCandidates：PATH が無い・空なら候補は無い', () => {
  assert.deepEqual(pathCandidates(undefined, 'posix'), []);
  assert.deepEqual(pathCandidates('', 'posix'), []);
  assert.deepEqual(pathCandidates(undefined, 'windows'), []);
  assert.deepEqual(pathCandidates('', 'windows'), []);
});

const SKIPPED_POSIX: readonly (readonly [string, string])[] = [
  ['空の項目（::）', '/usr/bin::/bin'],
  ['先頭の空の項目', ':/usr/bin:/bin'],
  ['末尾の空の項目', '/usr/bin:/bin:'],
  ['相対の項目', '/usr/bin:bin:/bin'],
  ['./ で始まる項目', '/usr/bin:./bin:/bin'],
  ['. だけ', '/usr/bin:.:/bin'],
  ['.. だけ', '/usr/bin:..:/bin'],
  ['../ で始まる項目', '/usr/bin:../bin:/bin'],
  ['~ で始まる項目（展開されない）', '/usr/bin:~/bin:/bin'],
  ['空白だけの項目', '/usr/bin: :/bin'],
];

for (const [label, pathEnv] of SKIPPED_POSIX) {
  test(`D0078-AC-06: pathCandidates(posix)：${label}は飛ばし、絶対の項目だけを並べる`, () => {
    assert.deepEqual(pathCandidates(pathEnv, 'posix'), ['/usr/bin/pipe-in', '/bin/pipe-in']);
  });
}

test('D0078-AC-06: pathCandidates(posix)：項目の終わりの区切りを1つ落としてつなぐ（/usr/bin/ → /usr/bin/pipe-in。根の / → /pipe-in）', () => {
  assert.deepEqual(pathCandidates('/usr/bin/', 'posix'), ['/usr/bin/pipe-in']);
  assert.deepEqual(pathCandidates('/', 'posix'), ['/pipe-in']);
});

test('D0078-AC-06: pathCandidates(posix)：; は区切りにしない（posix の区切りは : だけ）', () => {
  assert.deepEqual(pathCandidates('C:\\a;D:\\b', 'posix'), []);
  assert.deepEqual(pathCandidates('/usr/bin;/bin', 'posix'), ['/usr/bin;/bin/pipe-in']);
});

test('D0078-AC-07: pathCandidates(windows)：; 区切りで、項目ごとに pipe-in.exe → pipe-in.com の順に並べる', () => {
  assert.deepEqual(pathCandidates('C:\\Tools;D:\\bin', 'windows'), [
    'C:\\Tools\\pipe-in.exe',
    'C:\\Tools\\pipe-in.com',
    'D:\\bin\\pipe-in.exe',
    'D:\\bin\\pipe-in.com',
  ]);
});

test('D0078-AC-07: pathCandidates(windows)：.cmd・.bat・拡張子なし・PATHEXT の名前は並べない', () => {
  const all = pathCandidates('C:\\Tools;D:\\bin;\\\\server\\share\\bin', 'windows');
  assert.ok(all.length > 0);
  for (const c of all) assert.match(c, /\\pipe-in\.(?:exe|com)$/);
  for (const c of all) assert.doesNotMatch(c, /\.(?:cmd|bat|ps1|vbs|js)$/i);
});

test('D0078-AC-07: pathCandidates(windows)：同じ項目では .exe が .com より先', () => {
  const [first, second] = pathCandidates('C:\\Tools', 'windows');
  assert.equal(first, 'C:\\Tools\\pipe-in.exe');
  assert.equal(second, 'C:\\Tools\\pipe-in.com');
});

test('D0078-AC-07: pathCandidates(windows)：両端の " を1組だけ外す。先頭だけの " や二重の " は外したあとも絶対パスにならないので飛ばす', () => {
  assert.deepEqual(pathCandidates('"C:\\Program Files\\pipe-in"', 'windows'), ['C:\\Program Files\\pipe-in\\pipe-in.exe', 'C:\\Program Files\\pipe-in\\pipe-in.com']);
  assert.deepEqual(pathCandidates('"C:\\Tools', 'windows'), []);
  assert.deepEqual(pathCandidates('""C:\\Tools""', 'windows'), []);
});

const SKIPPED_WINDOWS: readonly (readonly [string, string])[] = [
  ['空の項目', 'C:\\a;;D:\\b'],
  ['相対の項目（bin）', 'C:\\a;bin;D:\\b'],
  ['. だけ', 'C:\\a;.;D:\\b'],
  ['.\\ で始まる項目', 'C:\\a;.\\bin;D:\\b'],
  ['..\\ で始まる項目', 'C:\\a;..\\bin;D:\\b'],
  ['ドライブ文字だけの相対（C:bin）', 'C:\\a;C:bin;D:\\b'],
  ['今のドライブの根（\\bin）', 'C:\\a;\\bin;D:\\b'],
  ['装置のパス（\\\\?\\）', 'C:\\a;\\\\?\\C:\\bin;D:\\b'],
  ['装置のパス（\\\\.\\）', 'C:\\a;\\\\.\\pipe;D:\\b'],
  ['posix の絶対パス（/usr/bin）', 'C:\\a;/usr/bin;D:\\b'],
];

for (const [label, pathEnv] of SKIPPED_WINDOWS) {
  test(`D0078-AC-07: pathCandidates(windows)：${label}は飛ばし、絶対の項目だけを並べる`, () => {
    assert.deepEqual(pathCandidates(pathEnv, 'windows'), ['C:\\a\\pipe-in.exe', 'C:\\a\\pipe-in.com', 'D:\\b\\pipe-in.exe', 'D:\\b\\pipe-in.com']);
  });
}

test('D0078-AC-07: pathCandidates(windows)：項目の終わりの \\ を1つ落としてつなぐ。UNC の項目も使える', () => {
  assert.deepEqual(pathCandidates('D:\\bin\\', 'windows'), ['D:\\bin\\pipe-in.exe', 'D:\\bin\\pipe-in.com']);
  assert.deepEqual(pathCandidates('\\\\server\\share\\bin', 'windows'), ['\\\\server\\share\\bin\\pipe-in.exe', '\\\\server\\share\\bin\\pipe-in.com']);
});

test('D0078-AC-06: pathCandidates は呼ぶたびに同じ結果（PATH を覚えない・書き換えない）', () => {
  const env = '/usr/bin:bin:/bin';
  assert.deepEqual(pathCandidates(env, 'posix'), pathCandidates(env, 'posix'));
  assert.equal(env, '/usr/bin:bin:/bin');
});
