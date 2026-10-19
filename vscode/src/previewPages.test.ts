// パネルの確認用ページ（scripts/previewPages.ts）：画面用の見本の記録（tests/fixtures/showcase/）を、拡張の本物の
// 記録の読み取り → 図の状態 → renderPanelHtml で HTML にしたもの。out/ には書かず、関数の返す文字列だけを見る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { PANEL_PAGES, SHOWCASE_DIR, THEMES, panelPreviewHtml, readShowcaseView, withTheme } from '../scripts/previewPages.ts';
import type { Theme } from '../scripts/previewPages.ts';
import { createFsWorkDirSource } from './infra/fsWorkDirSource.ts';
import { isDevRecord, parseRunRecord } from './domain/runRecord.ts';
import { renderPanelHtml, renderViewBody } from './view/panelHtml.ts';
import { bootPanel } from './test/fakeDom.ts';

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
  // D0017: 動いている・確認待ちの見本のページが増えた（完了の見本の 2 つはそのまま残る）
  const done = PANEL_PAGES.filter(([name]) => name === 'run-panel-light' || name === 'run-panel-dark');
  assert.deepEqual(done.map(([name, theme]) => [name, theme]), [['run-panel-light', 'light'], ['run-panel-dark', 'dark']]);
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

// ---- D0017：動いている・確認待ちの見本（画面の確認 AC-34〜AC-37 の素材） ----

const FIXTURES_DIR = path.dirname(SHOWCASE_DIR);
const RUNNING_DIR = path.join(FIXTURES_DIR, 'showcase_running');
const RUNNING_NEXT_DIR = path.join(FIXTURES_DIR, 'showcase_running_next');
const WAITING_DIR = path.join(FIXTURES_DIR, 'showcase_waiting');
const VARIANT_DIRS = [RUNNING_DIR, RUNNING_NEXT_DIR, WAITING_DIR];

/** 見本の段のログのうち、ResultMessage の無いもの（動いている段）の Prompt 行の at。 */
function runningAt(dir: string): string {
  const logs = readdirSync(path.join(dir, 'logs')).filter((f) => f.endsWith('.jsonl')).sort();
  const open = logs.map((f) => ({ f, lines: readFileSync(path.join(dir, 'logs', f), 'utf8').split('\n').filter((l) => l.trim() !== '').map((l) => JSON.parse(l) as Record<string, unknown>) }))
    .filter((x) => x.lines.some((l) => l._type === 'Prompt') && !x.lines.some((l) => l._type === 'ResultMessage'));
  assert.equal(open.length, 1, '動いている段のログがちょうど 1 つある');
  const prompt = open[0].lines.find((l) => l._type === 'Prompt')!;
  assert.equal(typeof prompt.at, 'string');
  return prompt.at as string;
}

test('D0017-AC-34: 動いている・確認待ちの見本の記録（3 つ）が tests/fixtures/ にあり、手元の情報が無い', () => {
  for (const dir of VARIANT_DIRS) {
    assert.ok(existsSync(path.join(dir, 'state.json')), `${path.basename(dir)}/state.json がある`);
    for (const file of readdirSync(dir, { recursive: true, encoding: 'utf8' })) {
      const full = path.join(dir, file);
      if (!statSync(full).isFile()) continue;
      const text = readFileSync(full, 'utf8');
      assert.deepEqual(LOCAL_INFO.filter((re) => re.test(text)).map(String), [], `${path.basename(dir)}/${file}`);
    }
  }
});

test('D0017-AC-34: previewClock は、記録の時刻（at）から sec 秒後を「今」にする時計を返す（手元のずれは 0）', async () => {
  const pages = await import('../scripts/previewPages.ts');
  const at = runningAt(RUNNING_DIR);
  const clock = pages.previewClock(at, 83);
  assert.equal(clock.nowMs, Date.parse(at) + 83_000);
  assert.equal(typeof clock.localOffsetMin, 'number');
});

test('D0017-AC-34: 動いている見本（showcase_running）は 07_implement_2 が動いていて、83 秒後の経過と全体の経過が出る', async () => {
  const pages = await import('../scripts/previewPages.ts');
  const at = runningAt(RUNNING_DIR);
  const view = await pages.readShowcaseView(RUNNING_DIR, pages.previewClock(at, 83));
  assert.equal(view.runningStage, 'implement');
  assert.equal(view.final, null);
  const impl = view.nodes.find((n) => n.id === 'implement') as unknown as { runningSec: number | null; sendBackCount: number };
  assert.equal(impl.runningSec, 83);
  assert.equal(impl.sendBackCount, 0, '戻る矢印の回数は 0');
  const elapsed = (view as unknown as { elapsed: { seconds: number; live: boolean } | null }).elapsed;
  assert.ok(elapsed !== null && elapsed.live && elapsed.seconds > 83, '全体の経過が数え上げられる');
  const body = renderViewBody(view); // CSS とスクリプトの文字に反応させない
  assert.match(body, /data-elapsed="83"/);
  assert.match(body, /class="edge is-flowing"|class="edge[^"]*\bis-flowing\b/);
});

test('D0017-AC-37: 次の見本（showcase_running_next）は 08_test_2 が動き、差し戻しの回数が 1 に増えている', async () => {
  const pages = await import('../scripts/previewPages.ts');
  const at = runningAt(RUNNING_NEXT_DIR);
  const view = await pages.readShowcaseView(RUNNING_NEXT_DIR, pages.previewClock(at, 5));
  assert.equal(view.runningStage, 'test');
  const impl = view.nodes.find((n) => n.id === 'implement')!;
  assert.equal(impl.sendBackCount, 1);
  assert.equal(view.sendBacks.length, 1);
});

test('D0017-AC-37: running の次の render を送ると、戻る矢印が一度だけ光る（次の render は 1.4 秒より後なら光らない）', async () => {
  const pages = await import('../scripts/previewPages.ts');
  const first = await pages.readShowcaseView(RUNNING_DIR, pages.previewClock(runningAt(RUNNING_DIR), 83));
  const next = await pages.readShowcaseView(RUNNING_NEXT_DIR, pages.previewClock(runningAt(RUNNING_NEXT_DIR), 5));
  const h = bootPanel(renderPanelHtml(first, 'preview'));
  h.send({ type: 'render', html: renderViewBody(next) });
  assert.deepEqual(h.doc.querySelectorAll('[data-loop]').filter((l) => l.classList.contains('is-new')).map((l) => l.getAttribute('data-loop')), ['send-back']);
  h.advance(2000);
  h.send({ type: 'render', html: renderViewBody(next) });
  assert.deepEqual(h.doc.querySelectorAll('[data-loop]').filter((l) => l.classList.contains('is-new')).map((l) => l.getAttribute('data-loop')), []);
});

test('D0017-AC-35: 確認待ちの見本（showcase_waiting）は要件定義の確認で止まり、待ち始めの時刻と待ち時間が出る', async () => {
  const pages = await import('../scripts/previewPages.ts');
  const state = JSON.parse(readFileSync(path.join(WAITING_DIR, 'state.json'), 'utf8')) as { pending_review: { stage: string; since: string } | null; final: unknown };
  assert.equal(state.final, null);
  assert.equal(state.pending_review?.stage, 'requirements');
  assert.equal(typeof state.pending_review?.since, 'string');
  assert.match(state.pending_review!.since, /[+-]\d{2}:\d{2}$|Z$/, '待ち始めの時刻はオフセットつき');
  const view = await pages.readShowcaseView(WAITING_DIR, pages.previewClock(state.pending_review!.since, 40));
  const node = view.nodes.find((n) => n.id === 'review:requirements') as unknown as { waitingSec: number | null };
  assert.equal(node.waitingSec, 40);
  const body = renderViewBody(view);
  assert.match(body, /<g class="node [^"]*\bis-waiting\b/);
  assert.match(body, /要件定義の確認を待っている/);
});

test('D0017-AC-34: 確認用ページの一覧に、動いている・確認待ちの明るい・暗いのページ（run-panel-running-*・run-panel-waiting-*）が増える', async () => {
  const pages = await import('../scripts/previewPages.ts');
  const names = pages.PANEL_PAGES.map(([name]: readonly [string, string]) => name);
  for (const name of ['run-panel-light', 'run-panel-dark', 'run-panel-running-light', 'run-panel-running-dark', 'run-panel-waiting-light', 'run-panel-waiting-dark']) {
    assert.ok(names.includes(name), name);
  }
});

test('D0017-AC-37: 確認用ページ（running）に、次の見本を render で送る補助（window.__previewNext）がある。CSP は残り、script には nonce が付く', () => {
  const sources = ['previewPages.ts', 'preview.ts'].map((f) => readFileSync(path.join(REPO, 'vscode', 'scripts', f), 'utf8')).join('\n');
  assert.ok(sources.includes('__previewNext'), '__previewNext がある');
  assert.match(sources, /type:\s*['"]render['"]/, 'render のメッセージで送る');
  assert.doesNotMatch(sources, /replace\([^)]*Content-Security-Policy/);
  assert.doesNotMatch(sources, /<script>/);
});
