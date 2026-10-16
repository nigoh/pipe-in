// 作図台のパネルの外側の HTML と、パネルとの受け渡しの形。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderPipeEditorHtml } from './pipeEditorHtml.ts';
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
