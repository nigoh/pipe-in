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

// ---- D0019：実行の一覧の見本（画面の確認 AC-34〜AC-39 の素材）----
// 見本は4つの記録（tests/fixtures/）から、一時フォルダの中に置き場所の木を組み立てる（tests/fixtures/ には足さない）。
// まだ無い関数は、呼んだところで落ちるように、動的 import から取り出す。

import { withTempDir as withRealTempDir } from './test/tempDir.ts';

type Pages = Record<string, (...args: any[]) => any> & { PANEL_PAGES: readonly [string, string][] };
const loadPages = async (): Promise<Pages> => (await import('../scripts/previewPages.ts')) as unknown as Pages;

interface RunsEntryLike {
  key: string;
  view: Parameters<typeof renderViewBody>[0];
  listView: Parameters<typeof renderViewBody>[1];
  selected: boolean;
}

/**
 * 一覧の見本のページ（HTML 文字列）。木は一時フォルダの中に作り、終わったら消す。
 * list は左の欄（nav.sidebar：絞り込み・タブ・見出し・行）、detail は右の詳細。entries は行ごとの図と一覧（時系列の見本を調べるため）。
 */
async function runsPage(kind: 'runs' | 'omitted', theme: Theme): Promise<{ html: string; list: string; detail: string; workspace: string; entries: RunsEntryLike[] }> {
  const pages = await loadPages();
  return withRealTempDir(async (dest) => {
    const { workspace } = await (kind === 'runs' ? pages.buildRunsTree(dest) : pages.buildOmittedTree(dest));
    const since = (await pages.startOfLiveness(pages.WAITING_DIR)) as string;
    const clock = pages.previewClock(since, pages.WAITING_SEC);
    const entries = (await pages.readRunsView(workspace, clock)) as RunsEntryLike[];
    const html = pages.panelRunsPreviewHtml(entries, theme, clock) as string;
    const list = between(html, 'class="sidebar"', 'class="detail"');
    const detail = html.slice(html.indexOf('class="detail"'));
    return { html, list, detail, workspace, entries };
  });
}

function between(text: string, from: string, to: string): string {
  const start = text.indexOf(from);
  if (start < 0) return '';
  const end = text.indexOf(to, start + from.length);
  return text.slice(start, end < 0 ? undefined : end);
}
const plainText = (text: string): string => text.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
const rowHtmls = (list: string): string[] => [...list.matchAll(/<li\b[^>]*>[\s\S]*?<\/li>/g)].map((m) => m[0]);
const subOf = (r: string): string => plainText(between(r, 'class="run-sub"', 'class="run-id"'));
const groupCounts = (list: string): [string, number][] =>
  [...list.matchAll(/<section class="run-group" data-group="([^"]+)">([\s\S]*?)<\/section>/g)].map((m) => [m[1]!, rowHtmls(m[2]!).length]);

test('D0019-AC-34: 確認用ページの一覧に、一覧の見本の明るい・暗いのページ（run-panel-runs-*）と、省く見本（run-panel-runs-omitted-dark）が増える', async () => {
  const pages = await loadPages();
  const names = pages.PANEL_PAGES.map(([name]) => name);
  for (const name of ['run-panel-runs-light', 'run-panel-runs-dark', 'run-panel-runs-omitted-dark']) assert.ok(names.includes(name), name);
  assert.deepEqual(pages.PANEL_PAGES.filter(([n]) => n.startsWith('run-panel-runs-')).map(([n, t]) => [n, t]), [
    ['run-panel-runs-light', 'light'],
    ['run-panel-runs-dark', 'dark'],
    ['run-panel-runs-omitted-dark', 'dark'],
  ]);
  assert.equal(pages.panelKind('run-panel-runs-dark'), 'runs');
  assert.equal(pages.panelKind('run-panel-runs-light'), 'runs');
  assert.equal(pages.panelKind('run-panel-runs-omitted-dark'), 'runs-omitted');
  // 今までのページの種類は変わらない
  assert.equal(pages.panelKind('run-panel-light'), 'done');
  assert.equal(pages.panelKind('run-panel-running-dark'), 'running');
  assert.equal(pages.panelKind('run-panel-waiting-dark'), 'waiting');
});

test('D0019-AC-34: 見本のページは 上のバー・左の一覧・右の詳細 の 3 領域で、一覧に絞り込み・状態のタブ・見出し、詳細にパンくず・見出し・メタ・タブがある', async () => {
  const { html, list, detail } = await runsPage('runs', 'dark');
  assert.match(html, /<header\b[^>]*class="topbar"/);
  assert.match(plainText(between(html, 'class="topbar"', 'class="sidebar"')), /pipe-in[\s\S]*docs\/pipeline/);
  assert.match(list, /<input type="search"[^>]*data-keep="filter"/);
  assert.equal((list.match(/data-list-tab="/g) ?? []).length, 4, '状態のタブ 4 つ');
  for (const marker of ['class="crumbs"', 'class="head"', 'class="detail-meta"', 'data-detail-tab="diagram"', 'data-detail-tab="artifacts"', 'data-detail-tab="usage"', 'class="pane-diagram"', 'class="pane-gantt"']) {
    assert.ok(detail.includes(marker), marker);
  }
});

test('D0019-AC-34: 見本の一覧の行は 確認待ち → 動いている → 終わった の見出しで、確認待ち 2・動いている 2・終わった 3（合格・不合格・前の実行）', async () => {
  const { list } = await runsPage('runs', 'dark');
  assert.deepEqual(groupCounts(list), [['waiting', 2], ['running', 2], ['done', 3]]);
  const heads = [...list.matchAll(/<h2 class="run-group-head">([^<]*)<\/h2>/g)].map((m) => m[1]);
  assert.deepEqual(heads, ['確認待ち', '動いている', '終わった']);
  const rows = rowHtmls(list);
  assert.equal(rows.length, 7);
  const done = rows.filter((r) => /data-group="done"/.test(r));
  assert.equal(done.length, 3);
  assert.equal(done.filter((r) => /不合格/.test(subOf(r))).length, 1, '不合格は 1 行');
  assert.equal(rows.filter((r) => /前の実行/.test(subOf(r))).length, 2, '前の実行は 2 行');
  assert.equal(rows.filter((r) => /別の worktree/.test(subOf(r))).length, 2, '別の worktree は 2 行');
});

test('D0019-AC-34: 各行に セッション名・パイプ名 · ブランチ · 状態 · 今の段・ID の先頭 8 文字・日付 が読める（読めない「—」が無い）。別の worktree の行にブランチ名が付く', async () => {
  const { list } = await runsPage('runs', 'dark');
  for (const r of rowHtmls(list)) {
    assert.match(r, /<span class="run-session">[^<]+<\/span>/);
    assert.match(r, /<span class="run-id">[^<—]{8}<\/span>/, 'ID の先頭 8 文字');
    assert.match(r, /<span class="run-date">\d{2}\/\d{2}<\/span>/);
    assert.doesNotMatch(r, />—</, '見本は読めない項目を持たない');
    assert.ok(subOf(r).length > 6, `2 行目に パイプ名 · ブランチ · 状態 · 今の段: ${subOf(r)}`);
  }
  const branches = [...new Set([...list.matchAll(/data-branch="([^"]*)"/g)].map((m) => m[1]))].sort();
  assert.deepEqual(branches, ['feat/export-csv', 'fix/login', 'main']);
  const other = rowHtmls(list).filter((r) => /別の worktree/.test(subOf(r)));
  assert.deepEqual(other.map((r) => /data-branch="([^"]*)"/.exec(r)![1]).sort(), ['feat/export-csv', 'fix/login']);
  assert.equal((list.match(/aria-pressed="true"/g) ?? []).length, 1, '見ている行は 1 つ');
});

test('D0019-AC-34: 見本のセッション名は 見本の題（要件メモの題や付けた名前）で、パイプ名だけではない。セッション ID は行ごとに違う', async () => {
  const { list } = await runsPage('runs', 'dark');
  const rows = rowHtmls(list);
  const sessions = rows.map((r) => /<span class="run-session">([^<]+)<\/span>/.exec(r)![1]!);
  assert.equal(new Set(sessions).size >= 4, true, `題がばらける: ${sessions.join(' / ')}`);
  const ids = rows.map((r) => /<span class="run-id">([^<]+)<\/span>/.exec(r)![1]!);
  assert.equal(new Set(ids).size, ids.length, 'ID は行ごとに違う');
  assert.ok(rows.some((r, i) => !subOf(r).startsWith(sessions[i]!)), '名前とパイプ名は別');
});

test('D0019-AC-35: 見本の確認待ちの行に、待ち時間（data-elapsed）が小さな秒で付き、動いている行には経過（data-elapsed）がある。終わった行・待ちの行には data-elapsed が無い', async () => {
  const { list } = await runsPage('runs', 'dark');
  const rows = rowHtmls(list);
  const waiting = rows.filter((r) => r.includes('is-waiting'));
  assert.equal(waiting.length, 2);
  for (const r of waiting) {
    const sec = Number(/data-elapsed="(\d+)"/.exec(r)?.[1] ?? Number.NaN);
    assert.ok(sec >= 0 && sec <= 300, `待ち時間 ${sec} 秒`);
  }
  const running = rows.filter((r) => r.includes('is-running'));
  assert.equal(running.length, 2);
  for (const r of running) {
    const sec = Number(/data-elapsed="(\d+)"/.exec(r)?.[1] ?? Number.NaN);
    assert.ok(sec > 0 && sec <= 3600, `経過 ${sec} 秒（今の少し前に始まった）`);
  }
  for (const r of rows.filter((x) => /data-group="done"/.test(x))) assert.doesNotMatch(r, /data-elapsed/);
});

test('D0019-AC-77: 見本の時系列：終わった見本は確認の待ち（斜線）・差し戻し・不合格（赤）、動いている見本は動いている帯、確認待ちの見本は「いま待っている」帯を持つ', async () => {
  const { entries, html } = await runsPage('runs', 'dark');
  const bodies = entries.map((e) => renderViewBody(e.view, e.listView));
  const some = (re: RegExp): boolean => bodies.some((b) => re.test(b));
  assert.ok(some(/class="[^"]*\bg-fail\b/), '不合格（赤）の帯');
  assert.ok(some(/class="[^"]*\bg-wait\b/), '確認を待った帯');
  assert.ok(some(/● 動いている/), '動いている印');
  assert.ok(some(/● 待っている/), 'いま待っている印');
  const GANTT_ROOT = /class="(?:[^"]*\s)?gantt(?:\s[^"]*)?"[^>]*aria-label="時系列"|aria-label="時系列"[^>]*class="(?:[^"]*\s)?gantt(?:\s[^"]*)?"/;
  assert.ok(some(GANTT_ROOT), '時系列の枠（class gantt）');
  assert.match(html, GANTT_ROOT, 'ページの初めの本体にも時系列がある');
  assert.ok(!some(/class="gantt-svg"/), '幅 740 の SVG は使わない');
  // 受け持ち（agent）が見本の開発フローの記録に入っていて、行の名前に出る
  assert.ok(some(/要件定義[^<]*pipe-in-analyst/), '受け持ちが行の名前に出る');
});

test('D0019-AC-34: 押すと図が切り替わる置き換え（acquireVsCodeApi）が、nonce つきで <body> の直後にあり、行の key ごとの本体（BODIES）を持つ', async () => {
  const { html, list } = await runsPage('runs', 'dark');
  assert.match(html, /<body>\s*<script nonce="preview">window\.acquireVsCodeApi=/);
  assert.match(html, /selectRun/);
  assert.match(html, /BODIES/);
  const keys = [...list.matchAll(/data-run="([^"]*)"/g)].map((m) => m[1]!);
  assert.equal(keys.length, 7);
  for (const key of keys) assert.ok(html.includes(`${JSON.stringify(key)}:`), `BODIES に ${key} がある`);
  assert.doesNotMatch(html, /<\/script>[^<]*<\/script>/, '本体の文字で script が切れていない');
});

for (const [kind, theme] of [['runs', 'light'], ['runs', 'dark'], ['omitted', 'dark']] as const) {
  test(`D0019-AC-38: 一覧の見本のページ（${kind}・${theme}）は、CSP をそのまま持ち、script と style に nonce があり、style 属性が無い。使う --vscode-* の色をすべて決めている`, async () => {
    const { html } = await runsPage(kind, theme);
    assert.deepEqual(html.match(CSP_META), renderPanelHtml(await readShowcaseView(SHOWCASE_DIR), 'preview').match(CSP_META));
    const tags = [...html.matchAll(/<(script|style)\b[^>]*>/g)].map((m) => m[0]);
    assert.ok(tags.length >= 3);
    assert.deepEqual(tags.filter((t) => !t.includes('nonce="preview"')), []);
    assert.doesNotMatch(html, /\sstyle="/);
    const defined = definedVars(THEMES[theme]);
    assert.deepEqual(usedVars(html).filter((name) => !defined.has(name)), [], `${theme}: THEMES に無い色`);
    assert.ok(html.includes(THEMES[theme]), 'テーマの色がページに入っている');
  });
}

test('D0019-AC-38: 一覧の見本のページに手元の情報（ユーザー名の入ったパス・メールアドレス）や、一時フォルダの絶対パスが出ていない', async () => {
  const { html, workspace } = await runsPage('runs', 'dark');
  assert.deepEqual(LOCAL_INFO.filter((re) => re.test(html)).map(String), []);
  assert.ok(!html.includes(workspace), '木の置き場所の絶対パスが出ていない');
  assert.ok(!html.includes(REPO), 'リポジトリの絶対パスが出ていない');
  assert.match(html, /docs\/pipeline/, '作業フォルダの表示は docs/pipeline');
});

test('D0019-AC-38: 新しく使う色（黄の知らせの背景・選んだ行の背景・黄・赤・青・緑）を、明るい・暗いの両方の THEMES が決めている', () => {
  for (const theme of THEME_NAMES) {
    const defined = definedVars(THEMES[theme]);
    for (const name of [
      '--vscode-inputValidation-warningBackground',
      '--vscode-list-activeSelectionBackground',
      '--vscode-list-activeSelectionForeground',
      '--vscode-list-hoverBackground',
      '--vscode-charts-yellow',
      '--vscode-charts-red',
      '--vscode-charts-blue',
      '--vscode-charts-green',
      '--vscode-focusBorder',
    ]) {
      assert.ok(defined.has(name), `${theme}: ${name}`);
    }
  }
});

test('D0019-AC-39: 省く見本（run-panel-runs-omitted-dark）に「古い実行を 2 件、省いています」が出る。通常の見本には出ない', async () => {
  const omitted = await runsPage('omitted', 'dark');
  assert.match(omitted.list, /古い実行を 2 件、省いています/);
  assert.match(omitted.html, /古い実行を 2 件、省いています/);
  const normal = await runsPage('runs', 'dark');
  assert.doesNotMatch(normal.html, /省いています/);
});

test('D0019-AC-34: 見本の木は一時フォルダの中にだけ作り、tests/fixtures/ の見本の記録は変えない', async () => {
  const pages = await loadPages();
  const read = (dir: string) => readFileSync(path.join(dir, 'state.json'), 'utf8');
  const before = [SHOWCASE_DIR, RUNNING_DIR, RUNNING_NEXT_DIR, WAITING_DIR].map(read);
  await withRealTempDir(async (dest) => {
    const { workspace } = await pages.buildRunsTree(dest);
    assert.ok(workspace === dest || workspace.startsWith(dest + path.sep), '返す作業フォルダは dest の中');
    assert.ok(existsSync(path.join(workspace, '.git')), '主の checkout の .git がある');
  });
  assert.deepEqual([SHOWCASE_DIR, RUNNING_DIR, RUNNING_NEXT_DIR, WAITING_DIR].map(read), before);
});

test('D0017-AC-37: 確認用ページ（running）に、次の見本を render で送る補助（window.__previewNext）がある。CSP は残り、script には nonce が付く', () => {
  const sources = ['previewPages.ts', 'preview.ts'].map((f) => readFileSync(path.join(REPO, 'vscode', 'scripts', f), 'utf8')).join('\n');
  assert.ok(sources.includes('__previewNext'), '__previewNext がある');
  assert.match(sources, /type:\s*['"]render['"]/, 'render のメッセージで送る');
  assert.doesNotMatch(sources, /replace\([^)]*Content-Security-Policy/);
  assert.doesNotMatch(sources, /<script>/);
});
