// パネルの確認用ページ（scripts/previewPages.ts）：画面用の見本の記録（tests/fixtures/showcase/）を、拡張の本物の
// 記録の読み取り → 図の状態 → renderPanelHtml で HTML にしたもの。out/ には書かず、関数の返す文字列だけを見る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { PANEL_PAGES, SHOWCASE_DIR, THEMES, panelPreviewHtml, readShowcaseView, withTheme } from '../scripts/previewPages.ts';
import type { Theme } from '../scripts/previewPages.ts';
import { createFsWorkDirSource } from './infra/fsWorkDirSource.ts';
import { isDevRecord, parseRunRecord } from './domain/runRecord.ts';
import { renderPanelHtml } from './view/panelHtml.ts';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const THEME_NAMES: Theme[] = ['light', 'dark'];

const CSP_META = /<meta http-equiv="Content-Security-Policy"[^>]*>/g;

// tests/test_rules.py の LOCAL_INFO と同じ4つの書き方（ユーザー名の入ったパス・メールアドレス）
const LOCAL_INFO: RegExp[] = [
  /[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_.-]/,
  /(?<![A-Za-z0-9_.-])\/Users\/[A-Za-z0-9_.-]/,
  /(?<![A-Za-z0-9_.-])\/home\/[A-Za-z0-9_.-]/,
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+/,
];

function usedVars(html: string): string[] {
  return [...new Set([...html.matchAll(/var\(\s*(--vscode-[\w-]+)/g)].map((m) => m[1]!))].sort();
}

function definedVars(css: string): Set<string> {
  return new Set([...css.matchAll(/(--vscode-[\w-]+)\s*:/g)].map((m) => m[1]!));
}

test('D0009-AC-14: パネルの確認用ページは明るい・暗いの2つで、renderPanelHtml の CSP をそのまま持つ', async () => {
  assert.deepEqual(PANEL_PAGES, [['run-panel-light', 'light'], ['run-panel-dark', 'dark']]);
  const view = await readShowcaseView(SHOWCASE_DIR);
  const csp = renderPanelHtml(view, 'preview').match(CSP_META);
  assert.ok(csp !== null && csp.length === 1, 'renderPanelHtml に CSP の <meta> が1つある');
  const pages = THEME_NAMES.map((theme) => panelPreviewHtml(view, theme));
  for (const html of pages) {
    assert.deepEqual(html.match(CSP_META), csp);
  }
  assert.notEqual(pages[0], pages[1], '明るい・暗いのページの中身が違う（テーマの色が入っている）');
});

test('D0009-AC-14: パネルの確認用ページの script と style には、どれも nonce がある', async () => {
  const view = await readShowcaseView(SHOWCASE_DIR);
  for (const theme of THEME_NAMES) {
    const html = panelPreviewHtml(view, theme);
    const tags = [...html.matchAll(/<(script|style)\b[^>]*>/g)].map((m) => m[0]);
    assert.ok(tags.length >= 3, `${theme}: 本物の style・script と、足したテーマの色と置き換えのスクリプトがある`);
    assert.deepEqual(tags.filter((t) => !t.includes('nonce="preview"')), [], theme);
    assert.match(html, /<style nonce="preview">:root\{/, `${theme}: テーマの色の <style> が入っている`);
    assert.match(html, /<body>\s*<script nonce="preview">window\.acquireVsCodeApi=/, `${theme}: <body> の直後に acquireVsCodeApi の置き換えがある`);
    assert.doesNotMatch(html, /\sstyle="/, `${theme}: style 属性を使わない（CSP に捨てられる）`);
  }
});

test('D0009-AC-14: パネルの確認用ページに、段の名前と使用量の節が入っている', async () => {
  const view = await readShowcaseView(SHOWCASE_DIR);
  for (const theme of THEME_NAMES) {
    const html = panelPreviewHtml(view, theme);
    for (const label of ['要件メモ', '要件定義', '設計', 'テスト先行', '実装', '検証', '判定']) {
      assert.ok(html.includes(label), `${theme}: ${label}`);
    }
    for (const part of ['使用量', 'モデル別', '利用枠', '成果物', '最終の結果：PASSED']) {
      assert.ok(html.includes(part), `${theme}: ${part}`);
    }
  }
});

test('D0009-AC-14: パネルの確認用ページは、使っている --vscode-* の色をすべて決めている', async () => {
  const view = await readShowcaseView(SHOWCASE_DIR);
  for (const theme of THEME_NAMES) {
    const html = panelPreviewHtml(view, theme);
    const defined = definedVars(THEMES[theme]);
    const missing = usedVars(html).filter((name) => !defined.has(name));
    assert.deepEqual(missing, [], `${theme}: THEMES に無い色`);
    assert.ok(html.includes(THEMES[theme]), `${theme}: THEMES の色がページに入っている`);
  }
});

test('D0009-AC-14: withTheme は最初の <style nonce="preview"> の前にテーマの色を入れ、ほかは変えない', () => {
  const html = '<head><style nonce="preview">a{}</style><style nonce="preview">b{}</style></head>';
  const out = withTheme(html, 'dark');
  assert.equal(out, `<head><style nonce="preview">:root{${THEMES.dark}}</style><style nonce="preview">a{}</style><style nonce="preview">b{}</style></head>`);
});

test('D0009-AC-15: 画面用の見本の記録は拡張の記録の読み取りで読めて、使用量を持ち、session_id は null', async () => {
  assert.equal(path.relative(REPO, SHOWCASE_DIR).split(path.sep).join('/'), 'tests/fixtures/showcase');
  assert.ok(existsSync(path.join(SHOWCASE_DIR, 'state.json')), '見本の state.json がある');
  const snapshot = await createFsWorkDirSource(SHOWCASE_DIR, 'docs/pipeline').read();
  assert.ok(snapshot.stateJson !== null);
  assert.ok(snapshot.stageLogs.length > 0, '段のログが読める');
  assert.equal(isDevRecord(parseRunRecord(snapshot.stateJson)), true);
  const state = JSON.parse(snapshot.stateJson);
  assert.equal(state.pending_review, null);
  for (const run of state.runs as Record<string, unknown>[]) {
    if ('session_id' in run) assert.equal(run.session_id, null, `seq ${String(run.seq)}`);
  }

  const view = await readShowcaseView(SHOWCASE_DIR);
  assert.equal(view.final, 'PASSED');
  assert.ok(view.usage !== null, '使用量（usage_summary）がある');
  assert.ok(view.usage.rows.length > 0);
  assert.equal(view.nodes.find((n) => n.id === 'review:requirements')!.reviseCount, 1);
  assert.equal(view.nodes.find((n) => n.id === 'implement')!.sendBackCount, 1);
});

test('D0009-AC-15: パネルの確認用ページに手元の情報が無い', async () => {
  const view = await readShowcaseView(SHOWCASE_DIR);
  for (const theme of THEME_NAMES) {
    const html = panelPreviewHtml(view, theme);
    const found = LOCAL_INFO.filter((re) => re.test(html)).map(String);
    assert.deepEqual(found, [], theme);
    assert.ok(!html.includes(SHOWCASE_DIR), `${theme}: 見本の置き場所の絶対パスが出ていない`);
    assert.ok(!html.includes(REPO), `${theme}: リポジトリの絶対パスが出ていない`);
  }
});

test('D0009-AC-15: 手元の情報の見つけ方そのものが、ユーザー名の入ったパスとメールアドレスを見つける', () => {
  // 見本は実行時につなぐ（このファイルの文字そのものは、リポジトリの手元の情報の検査（tests/test_rules.py）に掛からないように）
  const U = 'Users';
  const bad = [`C:\\${U}\\taro\\work`, `C:/${U}/taro/work`, `/${U}/hanako/src`, '/' + 'home/jiro/app', 'mail: someone' + '@' + 'corp.co.jp'];
  for (const text of bad) assert.ok(LOCAL_INFO.some((re) => re.test(text)), text);
  for (const text of ['docs/pipeline', '~/src/myapp', 'D:/work/app']) assert.ok(!LOCAL_INFO.some((re) => re.test(text)), text);
  assert.ok(readFileSync(path.join(REPO, 'tests', 'test_rules.py'), 'utf8').includes('LOCAL_INFO'), 'Python 側の一覧がある');
});
