// 作業台のパネルとの受け渡しのうち、「流す」の知らせ（D0078。view/messages.ts）。AC-21・22。
// パネル → 入口は { type: 'run', text } だけ。パイプのフォルダ・プロジェクト・コマンド・引数などは、付いていても読まない（入口が自分で決める）。
// 入口 → パネルの runContext の型は、型だけなのでソースの文字で確かめる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseEditorMessage } from './messages.ts';

test('D0078-AC-21: parseEditorMessage は { type: \'run\', text } を { type, text } で返す', () => {
  assert.deepEqual(parseEditorMessage({ type: 'run', text: '使い方を直して' }), { type: 'run', text: '使い方を直して' });
});

test('D0078-AC-21: text が空でも読める（optional は空で流せる。要るかの判断は入口の decideRun）', () => {
  assert.deepEqual(parseEditorMessage({ type: 'run', text: '' }), { type: 'run', text: '' });
});

test('D0078-AC-21: text は切らない・直さない（前後の空白・改行・NUL・サロゲートもそのまま入口に渡す。検めるのは decideRun）', () => {
  for (const text of ['  前後  ', 'a\nb', 'a\u0000b', 'a\ud800b', '--yes', 'x'.repeat(10000)]) {
    assert.deepEqual(parseEditorMessage({ type: 'run', text }), { type: 'run', text });
  }
});

const NOT_RUN: readonly (readonly [string, unknown])[] = [
  ['text が無い', { type: 'run' }],
  ['text が数', { type: 'run', text: 3 }],
  ['text が null', { type: 'run', text: null }],
  ['text が配列', { type: 'run', text: ['a'] }],
  ['text がオブジェクト', { type: 'run', text: { a: 1 } }],
  ['text が真偽', { type: 'run', text: true }],
  ['type が違う（Run）', { type: 'Run', text: 'x' }],
  ['type が無い', { text: 'x' }],
];

for (const [label, value] of NOT_RUN) {
  test(`D0078-AC-21: ${label}は null（捨てる）`, () => {
    assert.equal(parseEditorMessage(value), null);
  });
}

const EXTRA_KEYS: readonly (readonly [string, unknown])[] = [
  ['pipe', 'evil'],
  ['name', 'other'],
  ['path', '/etc'],
  ['dir', '/etc'],
  ['project', '/evil'],
  ['cwd', '/evil'],
  ['command', '/evil/pipe-in'],
  ['args', ['--yes']],
  ['env', { PATH: '/evil' }],
  ['shell', true],
  ['input', 'none'],
  ['pipeDir', '/evil'],
  ['dirty', false],
  ['executable', '/evil/pipe-in'],
  ['__proto__', { text: 'x' }],
];

for (const [key, value] of EXTRA_KEYS) {
  test(`D0078-AC-22: run に ${key} が付いても、結果の鍵は type と text だけ（読まない）`, () => {
    const msg = Object.defineProperty({ type: 'run', text: 'メモ' }, key, { value, enumerable: true, configurable: true, writable: true });
    const parsed = parseEditorMessage(msg);
    assert.deepEqual(parsed, { type: 'run', text: 'メモ' });
    assert.deepEqual(Object.keys(parsed ?? {}).sort(), ['text', 'type']);
  });
}

test('D0078-AC-22: 全部の鍵が一度に付いても、結果の鍵は type と text だけ', () => {
  const msg: Record<string, unknown> = { type: 'run', text: 'メモ' };
  for (const [key, value] of EXTRA_KEYS) if (key !== '__proto__') msg[key] = value;
  assert.deepEqual(parseEditorMessage(msg), { type: 'run', text: 'メモ' });
});

test('D0078-AC-22: run の枝は msg.text だけを読む（ソース：parseEditorMessage の run の行が text 以外の鍵を読まない）', () => {
  const source = readFileSync(new URL('./messages.ts', import.meta.url), 'utf8');
  const line = source.split('\n').find((l) => /msg\.type === 'run'/.test(l));
  assert.notEqual(line, undefined, "parseEditorMessage に msg.type === 'run' の分岐が無い");
  const keys = Array.from((line ?? '').matchAll(/\bmsg\.(\w+)/g), (m) => m[1]);
  assert.deepEqual([...new Set(keys)].sort(), ['text', 'type']);
});

test('D0078-AC-29: 入口 → パネルの知らせ runContext が ToEditorMessage にあり、RunContext の型を domain から import type する（ソース）', () => {
  const source = readFileSync(new URL('./messages.ts', import.meta.url), 'utf8').replace(/^[ \t]*\/\/.*$/gm, '');
  assert.match(source, /\{\s*type:\s*'runContext'\s*\}\s*&\s*RunContext/);
  assert.match(source, /import type \{[^}]*\bRunContext\b[^}]*\} from '\.\.\/domain\/runDecision\.ts'/);
});

test('D0078-AC-21: FromEditorMessage に { type: \'run\'; text: string } がある（ソース）', () => {
  const source = readFileSync(new URL('./messages.ts', import.meta.url), 'utf8').replace(/^[ \t]*\/\/.*$/gm, '');
  assert.match(source, /\{\s*type:\s*'run';\s*text:\s*string\s*\}/);
});

test('D0078-AC-21: ほかの知らせ（ready・state・save など）の読み方は変わらない（今のまま通る。守る）', () => {
  assert.deepEqual(parseEditorMessage({ type: 'ready' }), { type: 'ready' });
  assert.deepEqual(parseEditorMessage({ type: 'state', dirty: false }), { type: 'state', dirty: false });
  assert.deepEqual(parseEditorMessage({ type: 'externalChoice', choice: 'keep' }), { type: 'externalChoice', choice: 'keep' });
  assert.equal(parseEditorMessage({ type: 'unknown' }), null);
});
