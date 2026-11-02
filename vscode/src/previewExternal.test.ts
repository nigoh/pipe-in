// 画面の AC（D0065-AC-16〜19）の、テストで確かめられる部分：確認用ページを作る台本（scripts/preview.ts）と、パネルの台本（webview/pipeEditor.ts）が、
// 外の書き換えのページ・補助・メッセージの取り扱いを持っていること。見た目と操作そのものは Playwright で確かめる（docs/pipeline/03_red_tests.md の「画面の確認の手順」）。
// 台本の文字を読むだけの検査（偽物の画面で動かすものではない）。行頭のコメントは見ない。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { withoutComments } from './test/sourceText.ts';

const SRC = path.dirname(fileURLToPath(import.meta.url));
const preview = (): string => withoutComments(readFileSync(path.join(SRC, '..', 'scripts', 'preview.ts'), 'utf8'));
const editor = (): string => withoutComments(readFileSync(path.join(SRC, 'webview', 'pipeEditor.ts'), 'utf8'));

test('D0065-AC-16: 確認用ページに pipe-editor-external-dark と pipe-editor-external-light がある', () => {
  const src = preview();
  assert.ok(src.includes("'pipe-editor-external-dark'"), 'pipe-editor-external-dark');
  assert.ok(src.includes("'pipe-editor-external-light'"), 'pipe-editor-external-light');
});

test("D0065-AC-16: ページの補助 window.__previewExternal(kind) が 'reloaded'・'conflict'・'unreadable' を受け、版の一覧の見本に -external が 1 つ入る", () => {
  const src = preview();
  assert.ok(src.includes('__previewExternal'), '__previewExternal');
  for (const kind of ['reloaded', 'conflict', 'unreadable']) assert.ok(src.includes(`'${kind}'`) || src.includes(`"${kind}"`), kind);
  for (const type of ['externalReloaded', 'externalConflict', 'externalUnreadable']) assert.ok(src.includes(type), type);
  assert.ok(src.includes('-external'), '版の見本に -external');
});

test('D0065-AC-17: ページのスタブは externalChoice を受けて、load なら externalReloaded（chosen）、keep なら externalKept を返す', () => {
  const src = preview();
  assert.ok(src.includes('externalChoice'), 'externalChoice');
  assert.ok(src.includes('externalKept'), 'externalKept');
  assert.ok(src.includes('chosen'), "cause 'chosen'");
});

test('D0065-AC-16: パネルは externalReloaded・externalConflict・externalKept・externalUnreadable・externalResolved を取り扱い、トーストの文を出す', () => {
  const src = editor();
  for (const type of ['externalReloaded', 'externalConflict', 'externalKept', 'externalUnreadable', 'externalResolved']) assert.ok(src.includes(type), type);
  assert.ok(src.includes('外で書き換わったので読み直しました'), 'auto のトースト');
  assert.ok(src.includes('外の変更を読み込みました'), 'chosen のトースト');
  assert.ok(src.includes('自分の変更を残しました'), 'keep のトースト');
});

test('D0065-AC-17: パネルは #ext-banner に renderExternalBanner を入れ、data-ext のボタンで externalChoice を送る', () => {
  const src = editor();
  assert.ok(src.includes('ext-banner'), 'ext-banner');
  assert.ok(src.includes('renderExternalBanner'), 'renderExternalBanner');
  assert.ok(src.includes('data-ext'), 'data-ext');
  assert.ok(src.includes('externalChoice'), 'externalChoice');
});

test('D0065-AC-19: 履歴の行に、外の版の印「外で書き換わる前」を出す', () => {
  const src = editor();
  assert.ok(src.includes('外で書き換わる前'), '外で書き換わる前');
  assert.ok(src.includes('.external'), 'v.external を見る');
});
