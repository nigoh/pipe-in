// パネルの CSP（style-src は nonce だけ）の中で、作業台の見た目が崩れないための決まり。
// CSP はインラインの style="…" 属性を捨てるので、位置や大きさは CSSOM（el.style.*）かクラスで入れる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderPipeEditorHtml } from '../view/pipeEditorHtml.ts';
import { renderPanelHtml } from '../view/panelHtml.ts';
import { extractScript } from '../test/fakeDom.ts';
import { finishedView, runningView, waitingView } from '../test/liveFixtures.ts';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (rel: string): string => readFileSync(path.join(ROOT, rel), 'utf8');

test('AC-35: 作業台のスクリプトは style 属性を書かない（CSP に捨てられて、ブロックが左上に縮むため）', () => {
  const src = read('src/webview/pipeEditor.ts');
  assert.doesNotMatch(src, /\sstyle=/);
  assert.doesNotMatch(src, /setAttribute\(\s*['"]style['"]/);
});

test('AC-35: 外側の HTML も style 属性を使わない（<style nonce> だけ）', () => {
  const html = renderPipeEditorHtml({ nonce: 'n1', scriptUri: 'x.js', cspSource: 'src' });
  assert.doesNotMatch(html, /\sstyle=/);
  assert.match(html, /<style nonce="n1">/);
});

test('D0017-AC-21: 時間の要素つきの実行パネルの CSP は今のまま（default-src none・style と script は nonce だけ）', () => {
  for (const view of [runningView(83), waitingView(40), finishedView()]) {
    const html = renderPanelHtml(view, 'NONCE');
    const csp = /http-equiv="Content-Security-Policy" content="([^"]*)"/.exec(html);
    assert.ok(csp, 'CSP がある');
    assert.equal(csp[1], "default-src 'none'; style-src 'nonce-NONCE'; script-src 'nonce-NONCE';");
    assert.doesNotMatch(html, /<script(?![^>]*nonce=)/);
    assert.doesNotMatch(html, /<style(?![^>]*nonce=)/);
  }
});

test('D0017-AC-21: 実行パネルのスクリプトは、style 属性を書かず、外部を読み込まず、文字列から式を作らない（CSP を緩めずに動く）', () => {
  const script = extractScript(renderPanelHtml(runningView(83), 'NONCE'));
  assert.doesNotMatch(script, /setAttribute\(\s*['"]style['"]/);
  assert.doesNotMatch(script, /\sstyle=/);
  assert.doesNotMatch(script, /\bfetch\s*\(|XMLHttpRequest|\bimport\s*\(|\beval\s*\(|new\s+Function|document\.write|insertAdjacentHTML|outerHTML/);
  assert.doesNotMatch(script, /https?:\/\//);
});

test('AC-36: 確認用のページは CSP を外さない（本物と同じ条件で崩れを見つけるため）', () => {
  const src = read('scripts/preview.ts');
  assert.doesNotMatch(src, /replace\([^)]*Content-Security-Policy/);
  assert.doesNotMatch(src, /<script>/);
  assert.doesNotMatch(src, /<style>/);
});
