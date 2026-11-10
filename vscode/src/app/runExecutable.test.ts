// 作業台から流す実行ファイルを、絶対パスに決める手順（D0078。app/runExecutable.ts）。AC-06・07・18。
// 「そのパスに通常のファイルがあるか」の口 isFile は、テストの中で手で書いた偽物を渡す（実物のファイルには触れない）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { NOT_FOUND_REASON } from '../domain/runExecutable.ts';
import { resolveExecutable } from './runExecutable.ts';
import type { FileProbe } from './runExecutable.ts';
import type { OsKind } from '../domain/runCommand.ts';

/** 渡したパスだけが「通常のファイル」だと答える偽物。問い合わせの順を残す */
function probe(files: readonly string[]): { isFile: FileProbe; asked: string[] } {
  const asked: string[] = [];
  const set = new Set(files);
  return {
    asked,
    isFile: async (p) => {
      asked.push(p);
      return set.has(p);
    },
  };
}

function resolve(over: { setting?: { globalValue?: unknown; defaultValue?: unknown }; pathEnv?: string | undefined; os?: OsKind; isFile: FileProbe }) {
  return resolveExecutable({ setting: over.setting ?? { defaultValue: 'pipe-in' }, pathEnv: over.pathEnv, os: over.os ?? 'posix', isFile: over.isFile });
}

// ---- PATH から探す（AC-06） ----

test('D0078-AC-06: resolveExecutable：未設定なら PATH の絶対の項目だけを順に見て、最初の通常ファイルを返す', async () => {
  const { isFile, asked } = probe(['/usr/bin/pipe-in', '/bin/pipe-in']);
  const r = await resolve({ pathEnv: '/opt/none:/usr/bin:/bin', isFile });
  assert.deepEqual(r, { ok: true, path: '/usr/bin/pipe-in' });
  assert.deepEqual(asked, ['/opt/none/pipe-in', '/usr/bin/pipe-in'], '最初に見つかったところで止まる');
});

test('D0078-AC-06: resolveExecutable：空・相対・. の項目は見ない（相対の項目の下の同名のファイルを使わない）', async () => {
  const { isFile, asked } = probe(['bin/pipe-in', './pipe-in', 'pipe-in', '/usr/bin/pipe-in']);
  const r = await resolve({ pathEnv: ':bin:.:./bin::/usr/bin', isFile });
  assert.deepEqual(r, { ok: true, path: '/usr/bin/pipe-in' });
  assert.deepEqual(asked, ['/usr/bin/pipe-in']);
});

test('D0078-AC-06: resolveExecutable：相対の項目の下にしかファイルが無ければ、見つからない（NOT_FOUND_REASON）', async () => {
  const { isFile, asked } = probe(['bin/pipe-in', 'pipe-in']);
  const r = await resolve({ pathEnv: 'bin:.:', isFile });
  assert.deepEqual(r, { ok: false, reason: NOT_FOUND_REASON });
  assert.deepEqual(asked, []);
});

test('D0078-AC-06: resolveExecutable：ディレクトリや無いものは通常のファイルでない（isFile が false）ので次の候補へ', async () => {
  const { isFile } = probe(['/bin/pipe-in']);
  const r = await resolve({ pathEnv: '/usr/local/bin:/usr/bin:/bin', isFile });
  assert.deepEqual(r, { ok: true, path: '/bin/pipe-in' });
});

test('D0078-AC-06: resolveExecutable：isFile が投げたら false とみなして次の候補へ（例外を外に出さない）', async () => {
  const asked: string[] = [];
  const isFile: FileProbe = async (p) => {
    asked.push(p);
    if (p === '/usr/bin/pipe-in') throw new Error('stat が失敗');
    return p === '/bin/pipe-in';
  };
  const r = await resolve({ pathEnv: '/usr/bin:/bin', isFile });
  assert.deepEqual(r, { ok: true, path: '/bin/pipe-in' });
  assert.deepEqual(asked, ['/usr/bin/pipe-in', '/bin/pipe-in']);
});

test('D0078-AC-06: resolveExecutable：どの項目にも無ければ NOT_FOUND_REASON の ok: false', async () => {
  const { isFile } = probe([]);
  assert.deepEqual(await resolve({ pathEnv: '/usr/bin:/bin', isFile }), { ok: false, reason: NOT_FOUND_REASON });
  assert.deepEqual(await resolve({ pathEnv: undefined, isFile }), { ok: false, reason: NOT_FOUND_REASON });
  assert.deepEqual(await resolve({ pathEnv: '', isFile }), { ok: false, reason: NOT_FOUND_REASON });
});

test('D0078-AC-06: resolveExecutable：設定が pipe-in（globalValue も既定値と同じ）でも PATH から探す', async () => {
  const { isFile } = probe(['/usr/bin/pipe-in']);
  const r = await resolve({ setting: { globalValue: 'pipe-in', defaultValue: 'pipe-in' }, pathEnv: '/usr/bin', isFile });
  assert.deepEqual(r, { ok: true, path: '/usr/bin/pipe-in' });
});

// ---- Windows（AC-07） ----

test('D0078-AC-07: resolveExecutable(windows)：.exe を先に見て、同じ項目に両方あれば .exe', async () => {
  const { isFile, asked } = probe(['C:\\Tools\\pipe-in.exe', 'C:\\Tools\\pipe-in.com']);
  const r = await resolve({ os: 'windows', pathEnv: 'C:\\Tools', isFile });
  assert.deepEqual(r, { ok: true, path: 'C:\\Tools\\pipe-in.exe' });
  assert.deepEqual(asked, ['C:\\Tools\\pipe-in.exe']);
});

test('D0078-AC-07: resolveExecutable(windows)：.exe が無ければ .com、項目をまたいでも PATH の順', async () => {
  const { isFile } = probe(['C:\\Tools\\pipe-in.com', 'D:\\bin\\pipe-in.exe']);
  const r = await resolve({ os: 'windows', pathEnv: 'C:\\Tools;D:\\bin', isFile });
  assert.deepEqual(r, { ok: true, path: 'C:\\Tools\\pipe-in.com' });
});

test('D0078-AC-07: resolveExecutable(windows)：.cmd・.bat・拡張子なしの pipe-in しか無いときは見つからない（理由が出る）', async () => {
  const asked: string[] = [];
  const isFile: FileProbe = async (p) => {
    asked.push(p);
    return /pipe-in(?:\.cmd|\.bat)?$/i.test(p);
  };
  const r = await resolve({ os: 'windows', pathEnv: 'C:\\Tools', isFile });
  assert.deepEqual(r, { ok: false, reason: NOT_FOUND_REASON });
  for (const p of asked) assert.match(p, /\.(?:exe|com)$/);
});

// ---- 設定の絶対パス（AC-18） ----

test('D0078-AC-18: resolveExecutable：設定が絶対パスで、そこに通常のファイルがあれば、そのパス（PATH は見ない）', async () => {
  const { isFile, asked } = probe(['/opt/venv/bin/pipe-in', '/usr/bin/pipe-in']);
  const r = await resolve({ setting: { globalValue: '/opt/venv/bin/pipe-in', defaultValue: 'pipe-in' }, pathEnv: '/usr/bin', isFile });
  assert.deepEqual(r, { ok: true, path: '/opt/venv/bin/pipe-in' });
  assert.deepEqual(asked, ['/opt/venv/bin/pipe-in']);
});

test('D0078-AC-18: 設定の絶対パスにファイルが無いとき、PATH に戻らず、理由つきで ok: false（`pipe-in.command` とそのパスが理由に出る）', async () => {
  const { isFile, asked } = probe(['/usr/bin/pipe-in']);
  const r = await resolve({ setting: { globalValue: '/opt/venv/bin/pipe-in', defaultValue: 'pipe-in' }, pathEnv: '/usr/bin', isFile });
  assert.equal(r.ok, false);
  if (!r.ok) {
    assert.ok(r.reason.includes('pipe-in.command'), r.reason);
    assert.ok(r.reason.includes('/opt/venv/bin/pipe-in'), r.reason);
    assert.notEqual(r.reason, NOT_FOUND_REASON);
  }
  assert.deepEqual(asked, ['/opt/venv/bin/pipe-in'], 'PATH の候補は見ない');
});

const REFUSED_SETTINGS: readonly (readonly [string, unknown])[] = [
  ['相対（bin/pipe-in）', 'bin/pipe-in'],
  ['./pipe-in', './pipe-in'],
  ['- 始まり', '-x'],
  ['pipe-in2', 'pipe-in2'],
  ['引数つき', 'pipe-in --yes'],
  ['空', ''],
  ['空白だけ', '  '],
  ['改行を含む', '/opt/pipe-in\n--yes'],
  ['文字でない', 7],
  ['null', null],
];

for (const [label, value] of REFUSED_SETTINGS) {
  test(`D0078-AC-18: 設定の値が ${label} なら、ファイルを探さず理由つきで ok: false（既定の pipe-in に黙って戻さない）`, async () => {
    const { isFile, asked } = probe(['/usr/bin/pipe-in']);
    const r = await resolve({ setting: { globalValue: value, defaultValue: 'pipe-in' }, pathEnv: '/usr/bin', isFile });
    assert.equal(r.ok, false);
    if (!r.ok) assert.ok(r.reason.length > 0);
    assert.deepEqual(asked, [], 'PATH も設定のパスも調べない');
  });
}

test('D0078-AC-18: Windows で設定の絶対パスが .cmd・拡張子なしなら、ファイルがあっても理由つきで ok: false', async () => {
  for (const value of ['C:\\tools\\pipe-in.cmd', 'C:\\tools\\pipe-in.bat', 'C:\\tools\\pipe-in']) {
    const { isFile, asked } = probe([value]);
    const r = await resolve({ os: 'windows', setting: { globalValue: value, defaultValue: 'pipe-in' }, pathEnv: 'C:\\tools', isFile });
    assert.equal(r.ok, false, value);
    assert.deepEqual(asked, [], value);
  }
});

test('D0078-AC-18: Windows で設定の絶対パスが .exe でファイルがあれば、そのパス', async () => {
  const value = 'C:\\tools\\pipe-in.exe';
  const { isFile } = probe([value]);
  const r = await resolve({ os: 'windows', setting: { globalValue: value, defaultValue: 'pipe-in' }, pathEnv: undefined, isFile });
  assert.deepEqual(r, { ok: true, path: value });
});

test('D0078-AC-26: ワークスペースの設定の値は resolveExecutable の引数に入らない（setting の鍵が付いていても読まない）', async () => {
  const { isFile, asked } = probe(['/evil/pipe-in', '/usr/bin/pipe-in']);
  const setting = { globalValue: undefined, defaultValue: 'pipe-in', workspaceValue: '/evil/pipe-in', workspaceFolderValue: '/evil/pipe-in' };
  const r = await resolve({ setting, pathEnv: '/usr/bin', isFile });
  assert.deepEqual(r, { ok: true, path: '/usr/bin/pipe-in' });
  assert.ok(!asked.includes('/evil/pipe-in'));
});
