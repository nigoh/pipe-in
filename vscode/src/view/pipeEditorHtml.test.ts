// 作業台のパネルの外側の HTML と、パネルとの受け渡しの形。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { editorTitle, renderPipeEditorHtml } from './pipeEditorHtml.ts';
import { parseEditorMessage } from './messages.ts';
import { newPipe } from '../domain/pipeModel.ts';

test('AC-32: CSP は nonce と webview の出どころだけを許し、外から何も読み込まない', () => {
  const html = renderPipeEditorHtml({ nonce: 'abc123', scriptUri: 'vscode-webview://x/out/pipeEditor.js', cspSource: 'vscode-webview://x' });
  const csp = /Content-Security-Policy" content="([^"]+)"/.exec(html)?.[1] ?? '';
  assert.match(csp, /default-src 'none'/);
  assert.match(csp, /script-src 'nonce-abc123' vscode-webview:\/\/x/);
  assert.match(csp, /style-src 'nonce-abc123'/);
  assert.doesNotMatch(csp, /https?:/);
  assert.match(html, /<script nonce="abc123" src="vscode-webview:\/\/x\/out\/pipeEditor.js"><\/script>/);
  assert.doesNotMatch(html, /fonts\.googleapis|https?:\/\//);
  assert.doesNotMatch(html.replace(/var\(--vscode-[^)]+\)/g, ''), /#[0-9A-Fa-f]{6}\b/); // 色は VSCode のテーマから
});

test('AC-32: 渡された値は escape する', () => {
  const html = renderPipeEditorHtml({ nonce: '"><x>', scriptUri: 'a"b', cspSource: 'c' });
  assert.doesNotMatch(html, /"><x>/);
  assert.doesNotMatch(html, /src="a"b"/);
});

test('AC-33: パネルから来るのは ready と save（モデルの形を確かめる）だけ', () => {
  assert.deepEqual(parseEditorMessage({ type: 'ready' }), { type: 'ready' });
  const model = newPipe('x');
  assert.deepEqual(parseEditorMessage({ type: 'save', model }), { type: 'save', model });
  assert.equal(parseEditorMessage({ type: 'save', model: { name: 1 } }), null);
  assert.equal(parseEditorMessage({ type: 'save' }), null);
  assert.equal(parseEditorMessage({ type: 'run', cmd: 'rm -rf /' }), null);
  assert.equal(parseEditorMessage(null), null);
});

test('AC-71: パネルから来る state・openPrompt・loadVersion を検め、形の違う値は捨てる', () => {
  const model = newPipe('x');
  assert.deepEqual(parseEditorMessage({ type: 'state', dirty: true, model }), { type: 'state', dirty: true, model });
  assert.deepEqual(parseEditorMessage({ type: 'state', dirty: false }), { type: 'state', dirty: false });
  assert.equal(parseEditorMessage({ type: 'state', dirty: 'yes' }), null);
  assert.equal(parseEditorMessage({ type: 'state', dirty: true, model: { name: 1 } }), null);
  assert.deepEqual(parseEditorMessage({ type: 'openPrompt', name: 'survey' }), { type: 'openPrompt', name: 'survey' });
  for (const name of ['../x', 'a/b', '', 'C:\\x', 5]) assert.equal(parseEditorMessage({ type: 'openPrompt', name }), null, String(name));
  assert.deepEqual(parseEditorMessage({ type: 'loadVersion', id: '1760000000000' }), { type: 'loadVersion', id: '1760000000000' });
  assert.deepEqual(parseEditorMessage({ type: 'loadVersion', id: '1760000000000-draft' }), { type: 'loadVersion', id: '1760000000000-draft' });
  for (const id of ['../x', '1760000000000.json', 1760000000000]) assert.equal(parseEditorMessage({ type: 'loadVersion', id }), null, String(id));
});

test('AC-73: タブ名は、変更があれば「● パイプ作業台: 名前」、なければ「パイプ作業台: 名前」', () => {
  assert.equal(editorTitle('design-review', true), '● パイプ作業台: design-review');
  assert.equal(editorTitle('design-review', false), 'パイプ作業台: design-review');
});

test('AC-57・AC-79: 見出しは「パイプ作業台」で、右の欄に「履歴」のタブがある', () => {
  const html = renderPipeEditorHtml({ nonce: 'n', scriptUri: 'x.js', cspSource: 's' });
  assert.match(html, /<title>パイプ作業台<\/title>/);
  assert.match(html, /<h1>.*パイプ作業台<\/h1>/);
  assert.match(html, /<button[^>]*data-tab="history"[^>]*>履歴<\/button>/);
  assert.doesNotMatch(html, new RegExp('作' + '図'));
});
