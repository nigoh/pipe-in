// 確認用ページの素材のテスト（D0025 の AC-73〜75）：scripts/previewPages.ts と scripts/preview.ts が作る、成果物のタブの見本ページ。
//   AC-73：run-panel-artifacts-light・-dark（実行の一覧つき。実行は 2 つ：(a) 動いている開発フロー・(b) 12 個のパイプ）。
//   AC-74：写した成果物の更新時刻を、見本の「今」から決めた固定の値にそろえる（新しいページ以外の既存のページの写しも）。
//   AC-75：既存のページの「図と出力」「使用量」のパネルの HTML は変わらない（今の作りで測った SHA-256 を直書きした、守る検査）。
// 画面そのもの（AC-80〜87）は Playwright で見る。ここで確かめるのは、画面で見る前の素材：ページの文字・見本の木・preview.ts の呼び方。
// 確認用ページの HTML は bootPanel に渡さない（置き換えのスクリプトが先に拾われ、パネルのスクリプトが動かないため）。
// 新しい関数（buildArtifactsTree・artifactsPageHtml・setArtifactTimes）と新しい出口（PANEL_PAGES の 2 件・panelKind の 'artifacts'・recordPosted）は、
// テスト先行のときに「まだ無い」で落ちるようにしたため、動的 import で読んでから呼ぶ（ファイルごと import で落ちて、守る検査まで赤になるのを避けた）。
// buildArtifactsTree(dest, variant) の variant の値は、'current'（今の見本）と 'next'（更新後の見本）。
// 見本の木は一時フォルダの中にだけ作る。tests/fixtures/ には書かない（指紋で確かめる）。
// 「今のまま通る。守る」と書いたテストは、今の作りで通り、実装のあとも通り続けることを見張る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { readFile, readdir, stat, mkdir, utimes, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { HERE, makeRunKey } from './domain/runs.ts';
import type { ViewClock } from './domain/pipelineView.ts';
import {
  PANEL_PAGES,
  RUNNING_DIR,
  RUNNING_NEXT_DIR,
  RUNNING_SEC,
  SHOWCASE_DIR,
  STALE_AFTER_SEC,
  THEMES,
  WAITING_DIR,
  WAITING_SEC,
  buildOmittedTree,
  buildRunsTree,
  panelKind,
  panelPreviewHtml,
  panelRunsPreviewHtml,
  previewClock,
  readLiveViewAligned,
  readRunsView,
  readShowcaseView,
  staleRunsPageHtml,
  startOfLiveness,
} from '../scripts/previewPages.ts';
import type { Theme } from '../scripts/previewPages.ts';
// ページの文字を読む補助（fingerprint・between・panelsOf・runStub など）は、D0050 で test/previewText.ts へ移した（関数の中身は変えていない）
import {
  bodiesOf,
  between,
  dangerousAttributes,
  definedVars,
  fingerprint,
  pageBodies,
  panelsOf,
  plain,
  pressedRuns,
  previewNextBody,
  rootBody,
  runStub,
  sha256,
  stubOf,
  unescapeText,
  usedVars,
} from './test/previewText.ts';
import { callArgs, withoutComments } from './test/sourceText.ts';
import { withTempDir } from './test/tempDir.ts';
import { renderViewBody } from './view/panelHtml.ts';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const THEME_NAMES: Theme[] = ['light', 'dark'];
const HERE_KEY = makeRunKey(HERE, '');
const CUT_NOTICE = '先頭 256 KiB までを表示しています。続きはエディタで開いてください。';
const MAX_BYTES = 262_144;
const DAY_MS = 86_400_000;

// tests/test_rules.py の LOCAL_INFO と同じ4つの書き方（ユーザー名の入ったパス・メールアドレス）
const LOCAL_INFO: RegExp[] = [
  /[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_.-]/,
  /(?<![A-Za-z0-9_.-])\/Users\/[A-Za-z0-9_.-]/,
  /(?<![A-Za-z0-9_.-])\/home\/[A-Za-z0-9_.-]/,
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+/,
];

// ---- 新しい関数を動的 import で読む（テスト先行のとき「まだ無い」で落ちるようにした） ----

type Pages = Record<string, any>;
const loadPages = async (): Promise<Pages> => (await import('../scripts/previewPages.ts')) as unknown as Pages;
/** previewPages.ts の関数を取り出す。無ければ落とす。 */
function need(pages: Pages, name: string): (...args: any[]) => any {
  assert.equal(typeof pages[name], 'function', `scripts/previewPages.ts に ${name} が無い（export されていない）`);
  return pages[name] as (...args: any[]) => any;
}

/** 見本の「今」（確認待ちの見本の待ち始めから WAITING_SEC 秒後。一覧・成果物の見本の時計と同じ）。 */
async function previewNow(): Promise<ViewClock> {
  const since = await startOfLiveness(WAITING_DIR);
  assert.ok(since !== null, '確認待ちの見本に待ち始めの時刻がある');
  return previewClock(since, WAITING_SEC);
}

// ---- 指紋（見本の記録が変わっていないかを見る。fingerprint は test/previewText.ts） ----

const FIXTURE_DIRS = [SHOWCASE_DIR, RUNNING_DIR, RUNNING_NEXT_DIR, WAITING_DIR];
const fixturePrints = async (): Promise<string[][]> => Promise.all(FIXTURE_DIRS.map(fingerprint));

// ---- ページの文字の読み方（between・bodiesOf・panelsOf など多くは test/previewText.ts） ----

/** 本体の文字にある data-quiet="…" の値（同じ値は 1 つにまとめる）。 */
function quietSet(html: string): string[] {
  return [...new Set([...html.matchAll(/\sdata-quiet="(\d+)"/g)].map((m) => m[1]!))].sort();
}

interface PickRow {
  /** data-art-pick の名前（文字参照を戻したもの） */
  name: string;
  pressed: boolean;
  /** 「まだない」行（disabled） */
  missing: boolean;
  /** ボタンの中の HTML */
  inner: string;
}
/** 「成果物」タブの成果物の一覧の行（button[data-art-pick]）を、文字の順に。 */
function pickRows(body: string): PickRow[] {
  const rows: PickRow[] = [];
  for (const m of body.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)) {
    const attrs = m[1]!;
    const pick = /\sdata-art-pick="([^"]*)"/.exec(attrs);
    if (pick === null) continue;
    rows.push({
      name: unescapeText(pick[1]!),
      pressed: /\saria-pressed="true"/.test(attrs),
      missing: /\sdisabled(?=[\s=>]|$)/.test(attrs),
      inner: m[2]!,
    });
  }
  return rows;
}

interface Preview {
  name: string;
  hidden: boolean;
  /** section の中の HTML */
  html: string;
}
/** 「成果物」タブのプレビュー（section[data-art-preview]）を、文字の順に。 */
function previewsOf(body: string): Preview[] {
  const out: Preview[] = [];
  for (const m of body.matchAll(/<section\b([^>]*)>([\s\S]*?)<\/section>/g)) {
    const attrs = m[1]!;
    const name = /\sdata-art-preview="([^"]*)"/.exec(attrs);
    if (name === null) continue;
    out.push({ name: unescapeText(name[1]!), hidden: /\shidden(?=[\s=>]|$)/.test(attrs), html: m[2]! });
  }
  return out;
}
const previewOf = (body: string, name: string): Preview => {
  const found = previewsOf(body).find((p) => p.name === name);
  assert.ok(found !== undefined, `${name} のプレビューがある`);
  return found;
};

const STAMP = /\d{2}\/\d{2} \d{2}:\d{2}/;

// ---- 更新時刻の読み方 ----

/** dir 直下の、成果物の拡張子（.md・.txt）のファイルの更新時刻（ミリ秒。名前順）。 */
async function artifactTimes(dir: string): Promise<Map<string, number>> {
  const names = (await readdir(dir)).filter((n) => n.endsWith('.md') || n.endsWith('.txt')).sort();
  const out = new Map<string, number>();
  for (const n of names) out.set(n, Math.round((await stat(path.join(dir, n))).mtimeMs));
  return out;
}
/** root の下すべてのフォルダの成果物の更新時刻。キーは root からの相対パス。 */
async function artifactTimesDeep(root: string): Promise<Map<string, number>> {
  const out = new Map<string, number>();
  const walk = async (dir: string): Promise<void> => {
    for (const [name, ms] of await artifactTimes(dir)) out.set(path.relative(root, path.join(dir, name)).split(path.sep).join('/'), ms);
    for (const ent of await readdir(dir, { withFileTypes: true })) if (ent.isDirectory()) await walk(path.join(dir, ent.name));
  };
  await walk(root);
  return out;
}

/**
 * 成果物の更新時刻（キーは相対パス）の問題を並べる。無ければ空。
 * どれも整数の秒・見本の「今」を超えない・「今」の 5 日前より前でない。同じフォルダの成果物は 1 分以上ずつ違う（「数分ずつ違う」）。
 */
function stampProblems(times: ReadonlyMap<string, number>, nowMs: number): string[] {
  const problems: string[] = [];
  const byDir = new Map<string, number[]>();
  for (const [rel, ms] of times) {
    if (ms % 1000 !== 0) problems.push(`${rel}: 整数の秒でない（${ms}）`);
    if (ms > nowMs) problems.push(`${rel}: 見本の「今」より ${(ms - nowMs) / 1000} 秒あと`);
    if (ms < nowMs - 5 * DAY_MS) problems.push(`${rel}: 見本の「今」の 5 日より前`);
    const dir = path.posix.dirname(rel);
    byDir.set(dir, [...(byDir.get(dir) ?? []), ms]);
  }
  for (const [dir, list] of byDir) {
    const sorted = [...list].sort((a, b) => a - b);
    for (let i = 1; i < sorted.length; i += 1) {
      if (sorted[i]! - sorted[i - 1]! < 60_000) problems.push(`${dir}: 成果物の更新時刻が 1 分未満しか違わない（${sorted[i - 1]} と ${sorted[i]}）`);
    }
  }
  return problems;
}
const mapToObject = (m: ReadonlyMap<string, number>): Record<string, number> => Object.fromEntries(m);
/** キーの頭に「フォルダ名/」を付ける（stampProblems はフォルダごとに 1 分以上ずつ違うかを見る） */
const withPrefix = (prefix: string, times: ReadonlyMap<string, number>): Map<string, number> =>
  new Map([...times].map(([name, ms]): [string, number] => [`${prefix}/${name}`, ms]));

// ---- 見本の木・ページの組み立て（キャッシュして、確かめごとのテストで使い回す） ----

type TreeVariant = 'current' | 'next';
const CURRENT: TreeVariant = 'current';
const NEXT: TreeVariant = 'next';

/** 成果物のページの文字と、そのとき使った一時フォルダの名前（フォルダは作ったあとで消してある）。テーマごとに 1 回だけ作る。 */
const builtArtifactPages = new Map<Theme, Promise<{ html: string; dest: string }>>();
function artifactsPage(theme: Theme): Promise<{ html: string; dest: string }> {
  let page = builtArtifactPages.get(theme);
  if (page === undefined) {
    page = (async () => {
      const pages = await loadPages();
      return withTempDir(async (dest) => ({ html: (await need(pages, 'artifactsPageHtml')(dest, theme)) as string, dest }));
    })();
    builtArtifactPages.set(theme, page);
  }
  return page;
}

/** 実行の一覧の見本（buildRunsTree の既定）の行ごとの図。1 回だけ作る。 */
let runsEntriesCache: Promise<Awaited<ReturnType<typeof readRunsView>>> | null = null;
function runsEntries(): Promise<Awaited<ReturnType<typeof readRunsView>>> {
  runsEntriesCache ??= withTempDir(async (dest) => {
    const { workspace } = await buildRunsTree(dest);
    return readRunsView(workspace, await previewNow());
  });
  return runsEntriesCache;
}

// ======== AC-73：確認用ページ run-panel-artifacts-light・-dark ========

const EXISTING_PAGES: readonly (readonly [string, string])[] = [
  ['run-panel-light', 'light'],
  ['run-panel-dark', 'dark'],
  ['run-panel-running-light', 'light'],
  ['run-panel-running-dark', 'dark'],
  ['run-panel-waiting-light', 'light'],
  ['run-panel-waiting-dark', 'dark'],
  ['run-panel-runs-light', 'light'],
  ['run-panel-runs-dark', 'dark'],
  ['run-panel-runs-omitted-dark', 'dark'],
  ['run-panel-stale-light', 'light'],
  ['run-panel-stale-dark', 'dark'],
  ['run-panel-stale-soon-dark', 'dark'],
];

test('D0025-AC-73: PANEL_PAGES の先頭 12 件は今のまま（名前・順・テーマ。今のまま通る。守る）', () => {
  assert.deepEqual(PANEL_PAGES.slice(0, 12).map(([name, theme]) => [name, theme]), EXISTING_PAGES.map(([name, theme]) => [name, theme]));
});

// D0050-AC-29：エージェント・スキルのタブの確認用ページが 2 件足されるので、成果物の 2 件は 13・14 件目（slice(12, 14)）として見る。
// 14 件目より後ろが tools の 2 件だけであることは previewPagesTools.test.ts（D0050-AC-46）が見る。
test('D0025-AC-73: PANEL_PAGES は先頭 12 件のあとに run-panel-artifacts-light（明るい）・run-panel-artifacts-dark（暗い）の 2 件だけが足される', () => {
  assert.deepEqual(PANEL_PAGES.slice(12, 14).map(([name, theme]) => [name, theme]), [
    ['run-panel-artifacts-light', 'light'],
    ['run-panel-artifacts-dark', 'dark'],
  ]);
});

test('D0025-AC-73: panelKind は run-panel-artifacts-light・run-panel-artifacts-dark に artifacts を返す', async () => {
  const pages = await loadPages();
  assert.equal(need(pages, 'panelKind')('run-panel-artifacts-light'), 'artifacts');
  assert.equal(need(pages, 'panelKind')('run-panel-artifacts-dark'), 'artifacts');
});

test('D0025-AC-73: 今までの 12 のページの種類は変わらない（今のまま通る。守る）', () => {
  const expected: Record<string, string> = {
    'run-panel-light': 'done',
    'run-panel-dark': 'done',
    'run-panel-running-light': 'running',
    'run-panel-running-dark': 'running',
    'run-panel-waiting-light': 'waiting',
    'run-panel-waiting-dark': 'waiting',
    'run-panel-runs-light': 'runs',
    'run-panel-runs-dark': 'runs',
    'run-panel-runs-omitted-dark': 'runs-omitted',
    'run-panel-stale-light': 'stale',
    'run-panel-stale-dark': 'stale',
    'run-panel-stale-soon-dark': 'stale-soon',
  };
  assert.deepEqual(Object.fromEntries(Object.keys(expected).map((name) => [name, panelKind(name)])), expected);
});

// ---- 見本の木（buildArtifactsTree） ----

test('D0025-AC-73: buildArtifactsTree(dest, current) の木は、(a) 動いている開発フロー（直下。動いている段は実装。99_summary.md だけ「まだない」）と、(b) 12 個のパイプの 2 つの実行を持つ', async () => {
  const pages = await loadPages();
  const clock = await previewNow();
  await withTempDir(async (dest) => {
    const { workspace } = (await need(pages, 'buildArtifactsTree')(dest, CURRENT)) as { workspace: string };
    assert.ok(workspace === dest || workspace.startsWith(dest + path.sep), '返す作業フォルダは dest の中');
    const entries = await readRunsView(workspace, clock);
    assert.equal(entries.length, 2, '実行は 2 つ');
    const a = entries.find((e) => e.key === HERE_KEY);
    const b = entries.find((e) => e.key !== HERE_KEY);
    assert.ok(a !== undefined && b !== undefined, '(a) は直下、(b) はパイプ');
    assert.equal(a.view.runningStage, 'implement', '(a) の動いている段は実装');
    assert.deepEqual(a.view.artifacts.filter((x) => !x.ready).map((x) => x.name), ['99_summary.md'], '(a) で「まだない」のはまとめだけ');
    assert.equal(a.view.artifacts.length, 7);
    assert.equal(b.view.artifacts.length, 12, '(b) の成果物は 12 個');
    assert.deepEqual(b.view.artifacts.filter((x) => !x.ready).map((x) => x.name), [], '(b) の 12 個はすべて「ある」');
    assert.equal(b.view.runningStage, null, '(b) は終わった記録');
  });
});

test('D0025-AC-73: buildArtifactsTree(dest, next) の木の (a) は更新後の見本：動いている段が検証（test）で、04_implementation.md がある', async () => {
  const pages = await loadPages();
  const clock = await previewNow();
  await withTempDir(async (dest) => {
    const { workspace } = (await need(pages, 'buildArtifactsTree')(dest, NEXT)) as { workspace: string };
    const a = (await readRunsView(workspace, clock)).find((e) => e.key === HERE_KEY);
    assert.ok(a !== undefined, '(a) は直下');
    assert.equal(a.view.runningStage, 'test', '更新後は検証が動いている');
    assert.equal(a.view.artifacts.find((x) => x.name === '04_implementation.md')?.ready, true);
  });
});

test('D0025-AC-73: (a) の見本の文章：02_design.md は上限（262,144 バイト）を超える日本語、03_red_tests.md は外から来た文字（<script>・<img src=…>・リンク・画像）、04_implementation.md は長い Markdown', async () => {
  const pages = await loadPages();
  await withTempDir(async (dest) => {
    const { workspace } = (await need(pages, 'buildArtifactsTree')(dest, CURRENT)) as { workspace: string };
    const here = path.join(workspace, 'docs', 'pipeline');
    const design = await readFile(path.join(here, '02_design.md'), 'utf8');
    assert.ok(Buffer.byteLength(design, 'utf8') > MAX_BYTES, `02_design.md は ${MAX_BYTES} バイトを超える（${Buffer.byteLength(design, 'utf8')}）`);
    assert.match(design, /[\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Han}]/u, '02_design.md は日本語入り');
    const hostile = await readFile(path.join(here, '03_red_tests.md'), 'utf8');
    assert.ok(hostile.includes('<script>'), '03: <script>');
    assert.ok(hostile.includes('<img src='), '03: <img src=…>');
    assert.match(hostile, /(?<!!)\[[^\]\n]+\]\([^)\s]+\)/, '03: リンク');
    assert.match(hostile, /!\[[^\]\n]*\]\([^)\s]+\)/, '03: 画像');
    const long = await readFile(path.join(here, '04_implementation.md'), 'utf8');
    assert.ok(long.split('\n').length >= 30, '04 は長い Markdown（30 行以上）');
  });
});

test('D0025-AC-73: (b) の見本：名前に \' ] & 空白を含む成果物・.txt・空白の無い 100 文字を超える名前・広い表・空白の無い長い段の表示名がある', async () => {
  const pages = await loadPages();
  const clock = await previewNow();
  await withTempDir(async (dest) => {
    const { workspace } = (await need(pages, 'buildArtifactsTree')(dest, CURRENT)) as { workspace: string };
    const entries = await readRunsView(workspace, clock);
    const b = entries.find((e) => e.key !== HERE_KEY);
    assert.ok(b !== undefined);
    const names = b.view.artifacts.map((x) => x.name);
    assert.ok(names.some((n) => n.includes("'") && n.includes(']') && n.includes('&') && n.includes(' ')), `名前に ' ] & 空白を全部含む成果物がある: ${names.join(' | ')}`);
    assert.ok(names.some((n) => n.endsWith('.txt')), '.txt の成果物がある');
    assert.ok(names.some((n) => /^\S{101,}$/.test(n)), '空白の無い 100 文字を超える名前がある');
    assert.deepEqual(names.filter((n) => n.includes('/') || n.includes('\\') || n.includes(':') || n.startsWith('.')), [], 'Windows でも作れる名前（パスの区切り・: ・先頭の . が無い）');
    const labels = b.view.artifacts.map((x) => x.label);
    assert.ok(labels.some((l) => /^\S{40,}$/.test(l)), `空白の無い 40 文字以上の段の表示名がある: ${labels.join(' | ')}`);
  });
});

// ---- ページの文字 ----

test('D0025-AC-73: ページは実行の一覧つきで、実行は 2 つ（行の key は直下と 1 つのパイプ）。初めに見ているのは (a)（直下）', async () => {
  const { html } = await artifactsPage('dark');
  const list = between(html, 'class="sidebar"', 'class="detail"');
  const keys = [...list.matchAll(/\sdata-run="([^"]*)"/g)].map((m) => m[1]!);
  assert.equal(keys.length, 2, `一覧の行は 2 つ: ${keys.join(' | ')}`);
  assert.deepEqual(Object.keys(bodiesOf(html)).sort(), [...keys].sort(), '行ごとの本体（BODIES）が行と同じ key で 2 つ');
  assert.ok(keys.includes(HERE_KEY), '(a) は直下の開発フロー');
  assert.deepEqual(pressedRuns(html), [HERE_KEY], '初めに見るのは (a)');
  assert.equal(rootBody(html), bodiesOf(html)[HERE_KEY], '初めの本体は (a) の行の本体と同じ');
});

test('D0025-AC-73: (a) の「成果物」の一覧：7 行が決まった順に並び、既定の行は動いている段の成果物 04_implementation.md の 1 つだけ。99_summary.md だけ「まだない」', async () => {
  const { html } = await artifactsPage('dark');
  const rows = pickRows(rootBody(html));
  assert.deepEqual(rows.map((r) => r.name), ['00_input.md', '01_requirements.md', '02_design.md', '03_red_tests.md', '04_implementation.md', '05_test_report.md', '99_summary.md']);
  assert.deepEqual(rows.filter((r) => r.pressed).map((r) => r.name), ['04_implementation.md']);
  assert.deepEqual(rows.filter((r) => r.missing).map((r) => r.name), ['99_summary.md']);
  assert.match(rows.find((r) => r.name === '99_summary.md')!.inner, /まだない/, '「まだない」の文字が行の中に見える');
});

test('D0025-AC-73: (a) のプレビューは「ある」6 つだけで、見えるのは既定の 04_implementation.md の 1 つ。「まだない」99_summary.md のプレビューは無い', async () => {
  const { html } = await artifactsPage('dark');
  const previews = previewsOf(rootBody(html));
  assert.deepEqual(previews.map((p) => p.name), ['00_input.md', '01_requirements.md', '02_design.md', '03_red_tests.md', '04_implementation.md', '05_test_report.md']);
  assert.deepEqual(previews.filter((p) => !p.hidden).map((p) => p.name), ['04_implementation.md']);
});

/** 長い Markdown の見本の出力に、入れ子の箇条書き・番号つき箇条書きの途中のコードブロック・表・コードブロック・引用があるか。無いものを並べる。 */
function markdownFeatureProblems(html: string): string[] {
  const problems: string[] = [];
  if (!/<li\b[^>]*>(?:(?!<\/li>)[\s\S])*<(?:ul|ol)\b/.test(html)) problems.push('入れ子の箇条書き（li の中の ul か ol）が無い');
  if (!/<\/ol>\s*<pre\b[\s\S]*?<\/pre>\s*<ol\b[^>]*\sstart="\d+"/.test(html)) problems.push('番号つき箇条書きの途中のコードブロック（ol → pre → ol start=…）が無い');
  if (!/<table\b[\s\S]*<thead\b[\s\S]*<tbody\b/.test(html)) problems.push('表（table・thead・tbody）が無い');
  if ((html.match(/<pre\b/g) ?? []).length < 2) problems.push('コードブロック（pre）が 2 つ以上無い');
  if (!/<blockquote\b/.test(html)) problems.push('引用（blockquote）が無い');
  return problems;
}

test('D0025-AC-73: (a) の 04_implementation.md のプレビューに、入れ子の箇条書き・番号つき箇条書きの途中のコードブロック・表・コードブロック・引用が出る', async () => {
  const { html } = await artifactsPage('dark');
  assert.deepEqual(markdownFeatureProblems(previewOf(rootBody(html), '04_implementation.md').html), []);
});

test('D0025-AC-73: (a) の 02_design.md のプレビューは切れた案内（先頭 256 KiB まで…）を見出しの下に持つ。切れていないほかのプレビューには出ない', async () => {
  const { html } = await artifactsPage('dark');
  const body = rootBody(html);
  const design = previewOf(body, '02_design.md');
  assert.ok(design.html.includes(CUT_NOTICE), '02 に切れた案内');
  assert.ok(design.html.indexOf(CUT_NOTICE) > design.html.indexOf('</header>'), '案内は見出しの下');
  assert.deepEqual(previewsOf(body).filter((p) => p.html.includes(CUT_NOTICE)).map((p) => p.name), ['02_design.md'], '案内が出るのは 02 だけ');
});

test('D0025-AC-84: (a) の 03_red_tests.md のプレビューは、<script>・<img src=…>・リンク・画像を文字として見せ、script・img・a の要素を作らない', async () => {
  const { html } = await artifactsPage('dark');
  const preview = previewOf(rootBody(html), '03_red_tests.md').html;
  assert.ok(preview.includes('&lt;script&gt;'), '<script> は文字');
  assert.ok(preview.includes('&lt;img '), '<img …> は文字');
  assert.ok(preview.includes('[画像：'), '画像は「[画像：…]」の文字');
  assert.doesNotMatch(preview, /<(?:script|img|iframe|style|a|link)\b/i, '危ない要素を作らない');
  assert.deepEqual(dangerousAttributes(preview), [], 'style・on…・src・href の属性が無い');
});

test('D0025-AC-84: ページに入っている本体すべて（初めの本体・行ごとの本体・次の本体）に、タグの属性として style・on…・src・href が無い（タグだけを取り出して調べる）', async () => {
  const { html } = await artifactsPage('dark');
  const bodies = [rootBody(html), ...pageBodies(html)];
  assert.equal(bodies.length, 4, '初めの本体 + 行ごとの本体 2 + 次の本体');
  for (const body of bodies) assert.deepEqual(dangerousAttributes(body), []);
  assert.deepEqual(dangerousAttributes(html), [], 'ページ全体（script・style の中は除く）でも');
});

test('D0025-AC-73: (b) の「成果物」の一覧：12 行（先頭が 00_input.md・最後が 99_summary.md）、既定はまとめ（最後の行）の 1 つだけ。名前の特別な文字・.txt・長い名前が行にある', async () => {
  const { html } = await artifactsPage('dark');
  const bKey = Object.keys(bodiesOf(html)).find((k) => k !== HERE_KEY);
  assert.ok(bKey !== undefined, '(b) の行がある');
  const body = bodiesOf(html)[bKey]!;
  const rows = pickRows(body);
  assert.equal(rows.length, 12);
  assert.equal(rows[0]!.name, '00_input.md');
  assert.equal(rows.at(-1)!.name, '99_summary.md');
  assert.deepEqual(rows.filter((r) => r.missing), [], '12 個ぜんぶ「ある」');
  assert.deepEqual(rows.filter((r) => r.pressed).map((r) => r.name), ['99_summary.md'], '既定はまとめ');
  assert.equal(previewsOf(body).length, 12, 'プレビューも 12 個');
  assert.deepEqual(previewsOf(body).filter((p) => !p.hidden).map((p) => p.name), ['99_summary.md']);
  const names = rows.map((r) => r.name);
  assert.ok(names.some((n) => n.includes("'") && n.includes(']') && n.includes('&') && n.includes(' ')), "名前に ' ] & 空白");
  assert.ok(names.some((n) => n.endsWith('.txt')), '.txt');
  assert.ok(names.some((n) => /^\S{101,}$/.test(n)), '空白の無い 100 文字を超える名前');
});

test('D0025-AC-73: (b) の .txt の成果物は Markdown に直さず pre の文字で出る。広い表の成果物は 8 列以上の表で出る', async () => {
  const { html } = await artifactsPage('dark');
  const bKey = Object.keys(bodiesOf(html)).find((k) => k !== HERE_KEY)!;
  const body = bodiesOf(html)[bKey]!;
  const txt = previewsOf(body).find((p) => p.name.endsWith('.txt'));
  assert.ok(txt !== undefined, '.txt のプレビューがある');
  assert.match(txt.html, /<pre\b/);
  assert.doesNotMatch(txt.html, /class="md"/, 'Markdown の入れ物にしない');
  const widest = Math.max(0, ...previewsOf(body).map((p) => Math.max(0, ...[...p.html.matchAll(/<table\b[\s\S]*?<\/table>/g)].map((t) => (t[0].match(/<th\b/g) ?? []).length))));
  assert.ok(widest >= 8, `(b) のどれかのプレビューに 8 列以上の表がある（いちばん広い表は ${widest} 列）`);
});

test('D0025-AC-73: window.__previewNext() は (a) の更新後の本体を送る：既定の行が 05_test_report.md に移り、04_implementation.md の文章が 1 段落増えている。ほかの行の並びは同じ', async () => {
  const { html } = await artifactsPage('dark');
  const now = rootBody(html);
  const next = previewNextBody(html);
  assert.deepEqual(pickRows(next).map((r) => r.name), pickRows(now).map((r) => r.name), '行の並びは同じ');
  assert.deepEqual(pickRows(next).filter((r) => r.pressed).map((r) => r.name), ['05_test_report.md']);
  const paragraphs = (body: string): number => (previewOf(body, '04_implementation.md').html.match(/<p\b/g) ?? []).length;
  assert.equal(paragraphs(next), paragraphs(now) + 1, '04 の文章に段落が 1 つ足されている');
  assert.deepEqual(previewsOf(next).filter((p) => !p.hidden).map((p) => p.name), ['05_test_report.md']);
});

test('D0025-AC-73: ページの script と style のタグはすべて nonce="preview" を持ち、window.__previewNext=（nonce つき）と acquireVsCodeApi の置き換えがある', async () => {
  for (const theme of THEME_NAMES) {
    const { html } = await artifactsPage(theme);
    const tags = [...html.matchAll(/<(script|style)\b[^>]*>/g)].map((m) => m[0]);
    assert.ok(tags.length >= 4, `${theme}: 本物の style・script と、テーマの色・置き換え・__previewNext（${tags.length} 個）`);
    assert.deepEqual(tags.filter((t) => !t.includes('nonce="preview"')), [], theme);
    assert.match(html, /<body>\s*<script nonce="preview">window\.acquireVsCodeApi=/, theme);
    assert.match(html, /<script nonce="preview">window\.__previewNext=/, theme);
    assert.doesNotMatch(html, /\sstyle="/, `${theme}: style 属性を使わない（CSP に捨てられる）`);
  }
});

test('D0025-AC-73: ページは CSP をそのまま持ち、使う --vscode-* の色をすべて THEMES が決め、テーマの色が入っている（明るい・暗い）', async () => {
  const csp = /<meta http-equiv="Content-Security-Policy"[^>]*>/g;
  const done = panelPreviewHtml(await readShowcaseView(SHOWCASE_DIR), 'dark').match(csp);
  assert.ok(done !== null && done.length === 1);
  for (const theme of THEME_NAMES) {
    const { html } = await artifactsPage(theme);
    assert.deepEqual(html.match(csp), done, `${theme}: CSP は今のページと同じ`);
    const defined = definedVars(THEMES[theme]);
    assert.deepEqual(usedVars(html).filter((name) => !defined.has(name)), [], `${theme}: THEMES に無い色`);
    assert.ok(html.includes(THEMES[theme]), `${theme}: テーマの色がページに入っている`);
  }
});

test('D0025-AC-73: ページに手元の情報（ユーザー名の入ったパス・メールアドレス）や、一時フォルダ・リポジトリの絶対パスが出ていない', async () => {
  for (const theme of THEME_NAMES) {
    const { html, dest } = await artifactsPage(theme);
    assert.deepEqual(LOCAL_INFO.filter((re) => re.test(html)).map(String), [], theme);
    assert.ok(!html.includes(dest), `${theme}: 一時フォルダの絶対パスが出ていない`);
    assert.ok(!html.includes(REPO), `${theme}: リポジトリの絶対パスが出ていない`);
    assert.match(html, /docs\/pipeline/, `${theme}: 作業フォルダの表示は docs/pipeline`);
  }
});

test('D0025-AC-73: ページは止まっているかもの目安 STALE_AFTER_SEC で組み立てる：目安 data-stale-after="600" が出て、印の元（data-quiet）は動いている (a) の 0 だけ（初めの本体も次の本体も）', async () => {
  const { html } = await artifactsPage('dark');
  assert.equal(STALE_AFTER_SEC, 600);
  assert.ok(rootBody(html).includes('data-stale-after="600"'));
  assert.deepEqual(quietSet(rootBody(html)), ['0']);
  assert.deepEqual(quietSet(previewNextBody(html)), ['0'], '更新後の本体も、印は出ない');
  assert.equal(rootBody(html).includes('is-stale'), false, '更新なしの印が付かない');
});

test('D0025-AC-73: 明るいページと暗いページは、テーマの色の <style> 以外が同じ', async () => {
  const strip = (html: string, theme: Theme): string => html.replace(`:root{${THEMES[theme]}}`, '');
  assert.equal(strip((await artifactsPage('light')).html, 'light'), strip((await artifactsPage('dark')).html, 'dark'));
});

// ---- recordPosted（window.__posted） ----

// （stubOf・runStub・plain は test/previewText.ts）

test('D0025-AC-73: panelRunsPreviewHtml に recordPosted: true を渡すと、置き換えの acquireVsCodeApi が送られたメッセージの type を window.__posted に貯める。selectRun への返信（render）は今のまま', async () => {
  const pages = await loadPages();
  const entries = await runsEntries();
  const html = pages.panelRunsPreviewHtml(entries, 'dark', { staleAfterSec: STALE_AFTER_SEC, recordPosted: true }) as string;
  const { win, sent } = runStub(html);
  assert.ok(Array.isArray(win.__posted), 'window.__posted は配列で始まる');
  assert.deepEqual(plain(win.__posted), []);
  const api = win.acquireVsCodeApi();
  const key = entries[0]!.key;
  api.postMessage({ type: 'ready' });
  api.postMessage({ type: 'openArtifact', name: '01_requirements.md' });
  api.postMessage({ type: 'selectRun', id: key });
  assert.deepEqual(plain(win.__posted), ['ready', 'openArtifact', 'selectRun']);
  assert.deepEqual(plain(sent), [{ type: 'render', html: bodiesOf(html)[key] }], 'selectRun にだけ、その行の本体を render で返す');
});

test('D0025-AC-73: recordPosted: true でも、知らない id の selectRun には返信せず、型を貯める。null や文字のメッセージでも例外を出さない', async () => {
  const pages = await loadPages();
  const html = pages.panelRunsPreviewHtml(await runsEntries(), 'dark', { staleAfterSec: STALE_AFTER_SEC, recordPosted: true }) as string;
  const { win, sent } = runStub(html);
  assert.ok(Array.isArray(win.__posted), 'window.__posted は配列で始まる');
  const api = win.acquireVsCodeApi();
  api.postMessage({ type: 'selectRun', id: 'no-such-run|' });
  assert.deepEqual(plain(sent), [], '知らない id には返信しない');
  assert.deepEqual(plain(win.__posted), ['selectRun']);
  for (const odd of [null, undefined, 'ready', 0, [], {}]) assert.doesNotThrow(() => api.postMessage(odd), String(odd));
});

test('D0025-AC-73: recordPosted を渡さない（または false の）ページの置き換えは、window.__posted を作らず、selectRun にだけ返信する（今のまま通る。守る）', async () => {
  const pages = await loadPages();
  const entries = await runsEntries();
  for (const options of [{ staleAfterSec: STALE_AFTER_SEC }, { staleAfterSec: STALE_AFTER_SEC, recordPosted: false }]) {
    const html = pages.panelRunsPreviewHtml(entries, 'dark', options) as string;
    const { win, sent } = runStub(html);
    const api = win.acquireVsCodeApi();
    api.postMessage({ type: 'ready' });
    api.postMessage({ type: 'selectRun', id: entries[0]!.key });
    assert.equal(win.__posted, undefined, JSON.stringify(options));
    assert.equal(sent.length, 1, JSON.stringify(options));
    assert.equal(sent[0].type, 'render');
  }
});

test('D0025-AC-73: recordPosted を渡さないページの置き換えのスクリプトは、今までの文字のまま（既存の runs・stale のページの stub は変えない。今のまま通る。守る）', async () => {
  const pages = await loadPages();
  const html = pages.panelRunsPreviewHtml(await runsEntries(), 'dark', { staleAfterSec: STALE_AFTER_SEC }) as string;
  const json = JSON.stringify(bodiesOf(html)).replace(/</g, '\\u003c');
  assert.equal(
    stubOf(html),
    `window.acquireVsCodeApi=(()=>{const BODIES=${json};` +
      `return()=>({postMessage(m){if(m&&m.type==='selectRun'&&typeof BODIES[m.id]==='string')window.postMessage({type:'render',html:BODIES[m.id]},'*')}})})();`,
  );
});

test('D0025-AC-73: 成果物のページの置き換えは recordPosted を渡して作る：window.__posted が配列で、行を選ぶ selectRun に (b) の本体を返す', async () => {
  const { html } = await artifactsPage('dark');
  const { win, sent } = runStub(html);
  assert.ok(Array.isArray(win.__posted), 'window.__posted は配列で始まる');
  const bKey = Object.keys(bodiesOf(html)).find((k) => k !== HERE_KEY)!;
  win.acquireVsCodeApi().postMessage({ type: 'selectRun', id: bKey });
  assert.deepEqual(plain(win.__posted), ['selectRun']);
  assert.deepEqual(plain(sent), [{ type: 'render', html: bodiesOf(html)[bKey] }]);
});

// ---- preview.ts の呼び方を文字で守る（D0021-AC-41 の文字の検査と同じ形） ----

/** preview.ts の文字の問題（成果物のページを作らない・一時フォルダの外で作る・種類の分かれが無い）。無ければ空。 */
function artifactsWiringProblems(source: string): string[] {
  const code = withoutComments(source);
  const problems: string[] = [];
  if (callArgs(code, 'artifactsPageHtml').length === 0) problems.push('artifactsPageHtml( を呼んでいない');
  if (!/kind\s*===\s*['"]artifacts['"]/.test(code)) problems.push("kind === 'artifacts' の分かれが無い");
  if (!callArgs(code, 'inTempDir').some((args) => args.includes('artifactsPageHtml('))) problems.push('artifactsPageHtml( を inTempDir( の中で呼んでいない（見本の木は一時フォルダに作る）');
  return problems;
}

test('D0025-AC-73: scripts/preview.ts は kind === artifacts で、artifactsPageHtml( を inTempDir( の中で呼ぶ', () => {
  assert.deepEqual(artifactsWiringProblems(readFileSync(path.join(REPO, 'vscode', 'scripts', 'preview.ts'), 'utf8')), []);
});

const CLEAN_WIRING = [
  'for (const [page, theme] of PANEL_PAGES) {',
  '  const kind = panelKind(page);',
  "  if (kind === 'artifacts') {",
  "    writeFileSync(path.join(OUT, `${page}.html`), await inTempDir('artifacts', (dest) => artifactsPageHtml(dest, theme)), 'utf8');",
  '    continue;',
  '  }',
  '}',
].join('\n');

const BROKEN_WIRINGS: readonly (readonly [string, string, string])[] = [
  ['成果物のページを作らない', CLEAN_WIRING.replace(/await inTempDir\([^\n]*\), 'utf8'\);/, "'', 'utf8');"), 'artifactsPageHtml( を呼んでいない'],
  ['種類の分かれを書かない', CLEAN_WIRING.replace("kind === 'artifacts'", "kind === 'stale'"), "kind === 'artifacts' の分かれが無い"],
  ['一時フォルダの外で作る', CLEAN_WIRING.replace("await inTempDir('artifacts', (dest) => artifactsPageHtml(dest, theme))", 'await artifactsPageHtml(OUT, theme)'), 'inTempDir( の中で呼んでいない'],
];
for (const [label, source, word] of BROKEN_WIRINGS) {
  test(`D0025-AC-73: 検査そのもの：${label} preview.ts の見本の文字は見つける`, () => {
    assert.notEqual(source, CLEAN_WIRING, '見本の文字を壊せている');
    assert.ok(artifactsWiringProblems(source).some((p) => p.includes(word)), artifactsWiringProblems(source).join(' / '));
  });
}
test('D0025-AC-73: 検査そのもの：きれいな preview.ts の見本の文字は見逃す（コメントの中の artifactsPageHtml( は数えない）', () => {
  assert.deepEqual(artifactsWiringProblems(CLEAN_WIRING), []);
  const commentOnly = CLEAN_WIRING.replace(/await inTempDir\([^\n]*\), 'utf8'\);/, "'', 'utf8');").replace('continue;', "continue;\n  // artifactsPageHtml(dest, theme) は後で呼ぶ\n  /* inTempDir(artifactsPageHtml(x)) */");
  assert.ok(artifactsWiringProblems(commentOnly).includes('artifactsPageHtml( を呼んでいない'), 'コメントの中の呼び出しは数えない');
});

test('D0025-AC-73: 検査そのもの：markdownFeatureProblems は、5 つがそろった見本を見逃し、1 つ欠けた見本ではその 1 つを見つける', () => {
  const full =
    '<ul><li>a<ul><li>b</li></ul></li></ul><ol><li>x</li></ol><pre><code>c</code></pre><ol start="2"><li>y</li></ol>' +
    '<table><thead><tr><th>h</th></tr></thead><tbody><tr><td>d</td></tr></tbody></table><pre><code>z</code></pre><blockquote><p>q</p></blockquote>';
  assert.deepEqual(markdownFeatureProblems(full), []);
  const cases: readonly (readonly [string, string, string])[] = [
    ['入れ子の箇条書き', full.replace('<ul><li>b</li></ul>', 'b'), '入れ子の箇条書き'],
    ['途中のコードブロック', full.replace('</ol><pre><code>c</code></pre><ol start="2">', '</ol><ol start="2">'), '途中のコードブロック'],
    ['表', full.replace(/<table>[\s\S]*<\/table>/, ''), '表'],
    ['引用', full.replace('<blockquote><p>q</p></blockquote>', ''), '引用'],
  ];
  for (const [label, text, word] of cases) {
    assert.notEqual(text, full, `${label}: 見本を壊せている`);
    assert.ok(markdownFeatureProblems(text).some((p) => p.includes(word)), `${label}: ${markdownFeatureProblems(text).join(' / ')}`);
  }
});

test('D0025-AC-84: 検査そのもの：dangerousAttributes は <img src=x onerror=…> のタグを見つけ、文字の中の src= や属性の値の中の onerror= は見逃す', () => {
  assert.deepEqual(dangerousAttributes('<p><img src=x onerror=alert(1)></p>').sort(), ['onerror', 'src']);
  assert.deepEqual(dangerousAttributes('<a href="x" style="y">t</a>').sort(), ['href', 'style']);
  assert.deepEqual(dangerousAttributes('<p>&lt;img src=x onerror=alert(1)&gt;</p>'), [], '文字の中は見ない');
  assert.deepEqual(dangerousAttributes('<button data-art-pick="a src=b onclick=c" aria-label="x href=y">t</button>'), [], '属性の値の中は見ない');
  assert.deepEqual(dangerousAttributes('<script>var a = "<img src=x>";</script><style>a[href]{}</style><p class="x">t</p>'), [], 'script・style の中は見ない');
});

// ======== AC-74：写した成果物の更新時刻を、見本の「今」から決めた固定の値にそろえる ========

test('D0025-AC-74: 検査そのもの：stampProblems は、整数の秒でない・「今」より後・古すぎる・同じフォルダで 1 分未満しか違わない時刻を見つけ、そろった時刻は見逃す', () => {
  const now = Date.UTC(2026, 9, 17, 10, 2, 55);
  const good = new Map([['a/00.md', now - 180_000], ['a/01.md', now - 360_000], ['b/00.md', now - 180_000]]);
  assert.deepEqual(stampProblems(good, now), []);
  assert.equal(stampProblems(new Map([['a/00.md', now - 180_500]]), now).length, 1, '整数の秒でない');
  assert.equal(stampProblems(new Map([['a/00.md', now + 5_000]]), now).length, 1, '「今」より後');
  assert.equal(stampProblems(new Map([['a/00.md', now - 6 * DAY_MS]]), now).length, 1, '古すぎる');
  assert.equal(stampProblems(new Map([['a/00.md', now - 180_000], ['a/01.md', now - 180_000]]), now).length, 1, '同じ時刻');
  assert.equal(stampProblems(new Map([['a/00.md', now - 180_000], ['a/01.md', now - 200_000]]), now).length, 1, '1 分未満');
});

test('D0025-AC-74: setArtifactTimes(dir, atMs) は dir 直下の *.md・*.txt の更新時刻を、整数の秒・atMs を超えない・1 分以上ずつ違う固定の値にそろえる。同じ呼び方なら何度でも同じ値', async () => {
  const pages = await loadPages();
  const setArtifactTimes = need(pages, 'setArtifactTimes');
  const atMs = Date.UTC(2026, 9, 17, 10, 2, 55) + 789; // 端数のミリ秒つき（整数の秒に置く）
  await withTempDir(async (tmp) => {
    const make = async (name: string): Promise<string> => {
      const dir = path.join(tmp, name);
      await mkdir(path.join(dir, 'logs'), { recursive: true });
      await mkdir(path.join(dir, 'sub'));
      for (const rel of ['00_input.md', '01_requirements.md', '02_design.md', '04_raw_log.txt', '99_summary.md']) await writeFile(path.join(dir, rel), `# ${rel}\n`);
      return dir;
    };
    const dir = await make('a');
    await setArtifactTimes(dir, atMs);
    const first = await artifactTimes(dir);
    assert.deepEqual([...first.keys()], ['00_input.md', '01_requirements.md', '02_design.md', '04_raw_log.txt', '99_summary.md']);
    assert.deepEqual(stampProblems(withPrefix('x', first), atMs), [], '整数の秒・atMs を超えない・1 分以上ずつ違う');
    await setArtifactTimes(dir, atMs);
    assert.deepEqual(mapToObject(await artifactTimes(dir)), mapToObject(first), '2 回呼んでも同じ');
    const other = await make('b');
    await setArtifactTimes(other, atMs);
    assert.deepEqual(mapToObject(await artifactTimes(other)), mapToObject(first), '別のフォルダでも、同じ名前なら同じ値');
  });
});

test('D0025-AC-74: setArtifactTimes は dir 直下の *.md・*.txt だけを変える（state.json・logs/・サブフォルダの中は変えない）', async () => {
  const pages = await loadPages();
  const old = new Date('2000-01-01T00:00:00Z');
  await withTempDir(async (dir) => {
    await mkdir(path.join(dir, 'logs'));
    await mkdir(path.join(dir, 'sub'));
    const others = ['state.json', 'logs/01_a.jsonl', 'sub/inner.md', 'sub/inner.txt', 'notes.json'];
    for (const rel of [...others, '00_input.md', '04_raw_log.txt']) {
      await writeFile(path.join(dir, rel), '{}\n');
      await utimes(path.join(dir, rel), old, old);
    }
    await need(pages, 'setArtifactTimes')(dir, Date.UTC(2026, 9, 17, 10, 2, 55));
    for (const rel of others) assert.equal(Math.round((await stat(path.join(dir, rel))).mtimeMs), old.getTime(), `${rel} は変えない`);
    assert.ok(Math.round((await stat(path.join(dir, '00_input.md'))).mtimeMs) > old.getTime(), '00_input.md は変わる');
    assert.ok(Math.round((await stat(path.join(dir, '04_raw_log.txt'))).mtimeMs) > old.getTime(), '04_raw_log.txt も変わる');
  });
});

test('D0025-AC-74: copySample(src, dest, nowMs) が写した成果物の更新時刻は、整数の秒・nowMs を超えない・1 分以上ずつ違う固定の値（写した時刻ではない）。ログの更新時刻の指定（quietAgoSec）と関係しない', async () => {
  const pages = await loadPages();
  const copySample = need(pages, 'copySample');
  const now = Date.UTC(2020, 0, 1, 0, 0, 0); // 写す本物の今よりずっと前。そろえていなければ、写した時刻が「今」より後になる
  const before = await fingerprint(RUNNING_DIR);
  await withTempDir(async (tmp) => {
    await copySample(RUNNING_DIR, path.join(tmp, 'a'), now);
    await copySample(RUNNING_DIR, path.join(tmp, 'b'), now, 612);
    const a = await artifactTimes(path.join(tmp, 'a'));
    const b = await artifactTimes(path.join(tmp, 'b'));
    assert.ok(a.size >= 6, `成果物を写している（${a.size} 個）`);
    assert.deepEqual(stampProblems(withPrefix('a', a), now), []);
    assert.deepEqual(mapToObject(b), mapToObject(a), '成果物の時刻は quietAgoSec で変わらない（ログの時刻だけが「今 − 秒」）');
    await copySample(RUNNING_DIR, path.join(tmp, 'c'), now);
    assert.deepEqual(mapToObject(await artifactTimes(path.join(tmp, 'c'))), mapToObject(a), '同じ見本から 2 回作ると、同じ値');
  });
  assert.deepEqual(await fingerprint(RUNNING_DIR), before, '元の見本は書き換えない');
});

test('D0025-AC-74: readLiveViewAligned が写した成果物（動いている・次の・確認待ちの見本）の更新時刻は、見本の「今」を超えない整数の秒で、2 回作っても同じ', async () => {
  const samples: readonly (readonly [string, string, number])[] = [
    ['動いている見本', RUNNING_DIR, RUNNING_SEC],
    ['次の見本', RUNNING_NEXT_DIR, 5],
    ['確認待ちの見本', WAITING_DIR, WAITING_SEC],
  ];
  for (const [label, src, sec] of samples) {
    const nowMs = previewClock((await startOfLiveness(src))!, sec).nowMs;
    await withTempDir(async (tmp) => {
      await mkdir(path.join(tmp, '1'));
      await mkdir(path.join(tmp, '2'));
      await readLiveViewAligned(src, sec, path.join(tmp, '1'));
      await readLiveViewAligned(src, sec, path.join(tmp, '2'));
      const one = await artifactTimes(path.join(tmp, '1', path.basename(src)));
      const two = await artifactTimes(path.join(tmp, '2', path.basename(src)));
      assert.deepEqual(stampProblems(withPrefix(path.basename(src), one), nowMs), [], label);
      assert.deepEqual(mapToObject(two), mapToObject(one), `${label}: 2 回作っても同じ`);
    });
  }
});

/** buildRunsTree・buildOmittedTree・buildArtifactsTree の木の成果物（.md・.txt）の更新時刻を、相対パスつきで。 */
async function treeTimes(build: (dest: string) => Promise<{ workspace: string }>): Promise<Map<string, number>> {
  return withTempDir(async (dest) => {
    await build(dest);
    return artifactTimesDeep(dest);
  });
}

test('D0025-AC-74: buildRunsTree の木の成果物すべて（直下・diagrams・survey・archive・別の worktree）の更新時刻は、見本の「今」を超えない整数の秒で、2 回作っても同じ', async () => {
  const nowMs = (await previewNow()).nowMs;
  const one = await treeTimes((dest) => buildRunsTree(dest));
  const two = await treeTimes((dest) => buildRunsTree(dest));
  assert.ok(one.size >= 30, `成果物を写している（${one.size} 個）`);
  assert.deepEqual(stampProblems(one, nowMs), []);
  assert.deepEqual(mapToObject(two), mapToObject(one), '2 回作っても同じ');
});

test('D0025-AC-74: buildOmittedTree の木の成果物の更新時刻も、見本の「今」を超えない整数の秒で、2 回作っても同じ', async () => {
  const nowMs = (await previewNow()).nowMs;
  const one = await treeTimes((dest) => buildOmittedTree(dest));
  const two = await treeTimes((dest) => buildOmittedTree(dest));
  assert.ok(one.size >= 6, `成果物を写している（${one.size} 個）`);
  assert.deepEqual(stampProblems(one, nowMs), []);
  assert.deepEqual(mapToObject(two), mapToObject(one), '2 回作っても同じ');
});

test('D0025-AC-74: buildArtifactsTree の木（current・next）の成果物（.md と .txt）の更新時刻は、見本の「今」を超えない整数の秒で、2 回作っても同じ', async () => {
  const pages = await loadPages();
  const nowMs = (await previewNow()).nowMs;
  for (const variant of [CURRENT, NEXT]) {
    const build = (dest: string): Promise<{ workspace: string }> => need(pages, 'buildArtifactsTree')(dest, variant);
    const one = await treeTimes(build);
    const two = await treeTimes(build);
    // current は (a) 6 個 + (b) 12 個。next は更新後の (a) があればよい（(b) も入れるかは実装に任せる）
    assert.ok(one.size >= (variant === CURRENT ? 18 : 6), `${variant}: 成果物を写している（${one.size} 個）`);
    assert.deepEqual(stampProblems(one, nowMs), [], variant);
    assert.deepEqual(mapToObject(two), mapToObject(one), `${variant}: 2 回作っても同じ`);
  }
});

test('D0025-AC-74: 成果物のページの成果物の一覧：「ある」行の時刻は MM/DD HH:mm で、行ごとに違い、見本の「今」を超えない。「まだない」行は「—」。2 回作っても同じ文字', async () => {
  const now = await previewNow();
  const nowStamp = `${new Date(now.nowMs).toISOString().slice(5, 10).replace('-', '/')} ${new Date(now.nowMs).toISOString().slice(11, 16)}`;
  assert.match(nowStamp, STAMP);
  const pages = await loadPages();
  const { html } = await artifactsPage('dark');
  const second = await withTempDir((dest) => need(pages, 'artifactsPageHtml')(dest, 'dark') as Promise<string>);
  assert.equal(second, html, '同じ見本から 2 回作ると、ページの文字が同じ（時刻の欄を含む）');
  const bodies = [rootBody(html), ...Object.values(bodiesOf(html))];
  for (const body of bodies) {
    const rows = pickRows(body);
    const stamps: string[] = [];
    for (const row of rows) {
      const found = STAMP.exec(row.inner.replace(/<[^>]*>/g, ' '));
      if (row.missing) {
        assert.equal(found, null, `${row.name}: 「まだない」行に時刻は出ない`);
        assert.ok(row.inner.includes('—'), `${row.name}: 「まだない」行の時刻は「—」`);
        continue;
      }
      assert.ok(found !== null, `${row.name}: 「ある」行に MM/DD HH:mm の時刻がある`);
      assert.ok(found[0] <= nowStamp, `${row.name}: 時刻 ${found[0]} は見本の「今」${nowStamp} を超えない`);
      stamps.push(found[0]);
    }
    assert.equal(new Set(stamps).size, stamps.length, `成果物ごとに時刻が違う（${stamps.join(' | ')}）`);
  }
});

test('D0025-AC-74: 見本の木・ページを作っても（成果物のページ・buildRunsTree・読み直し）、tests/fixtures/ の見本の内容と更新時刻は変わらない', async () => {
  const pages = await loadPages();
  const before = await fixturePrints();
  await withTempDir(async (dest) => void (await need(pages, 'artifactsPageHtml')(dest, 'light')));
  await withTempDir(async (dest) => void (await need(pages, 'buildArtifactsTree')(dest, 'next')));
  await withTempDir(async (dest) => void (await buildRunsTree(dest)));
  await withTempDir(async (dest) => {
    await readLiveViewAligned(RUNNING_DIR, RUNNING_SEC, dest);
    await readLiveViewAligned(RUNNING_NEXT_DIR, 5, dest);
    await readLiveViewAligned(WAITING_DIR, WAITING_SEC, dest);
  });
  assert.deepEqual(await fixturePrints(), before);
});

// ======== AC-75：既存のページの「図と出力」「使用量」のパネルは変わらない ========
//
// 今の作り（この機能を入れる前）で測った SHA-256。ページの種類ごとに、本体（行の順。次の本体があれば最後）の
// 「図と出力」のパネルと「使用量」のパネルの HTML をつないだ文字を測る。「成果物」のパネルは含めない（そこだけが新しい作りになる）。
// 本体の作り方は preview.ts と同じ（見本の木・時計・目安）。パネルの HTML はテーマに左右されないので、暗いページで測る。
const PANEL_SHA256: Record<string, string> = {
  done: '0f69d5fb6f30eb5e5127667fdd8ff945f53e2f1b142bf136d919574837ffdff6',
  running: '415860fd689cd2d52d044307e39ea25d3ab774eeaa8df94beafe7ec33d6d28d8',
  waiting: '328a5b8a37e76716b0f1bba7d0b9f4d1170979be774040badad97adffe768672',
  runs: '6ae250f0c4937482f13184ed3f3074326e75e59a36c8e68d6195386aff86b71c',
  'runs-omitted': '4faceb5ea285e1115ea7114c0ba4312b26125048b113e55eec53709f6603d22b',
  stale: 'ebd7a794c210f4596c83c8a2eaf1c1100c55e9980bd41da3a0c701b38ca525a5',
  'stale-soon': 'f7725d0d34cffee14eceba8f09ba583eab172bcf452cdba0f30bd5929d08c32a',
};

/** 既存のページ 1 種類の「図と出力」「使用量」のパネルをつないだ文字。preview.ts と同じ組み立て（目安は STALE_AFTER_SEC）。 */
async function existingPagePanels(kind: string): Promise<string> {
  const html = await withTempDir(async (dest): Promise<string> => {
    if (kind === 'done') return panelPreviewHtml(await readShowcaseView(SHOWCASE_DIR), 'dark', undefined, STALE_AFTER_SEC);
    if (kind === 'running') {
      const running = await readLiveViewAligned(RUNNING_DIR, RUNNING_SEC, dest);
      const next = await readLiveViewAligned(RUNNING_NEXT_DIR, 5, dest);
      return panelPreviewHtml(running, 'dark', next, STALE_AFTER_SEC);
    }
    if (kind === 'waiting') return panelPreviewHtml(await readLiveViewAligned(WAITING_DIR, WAITING_SEC, dest), 'dark', undefined, STALE_AFTER_SEC);
    if (kind === 'runs' || kind === 'runs-omitted') {
      const { workspace } = await (kind === 'runs' ? buildRunsTree(dest) : buildOmittedTree(dest));
      return panelRunsPreviewHtml(await readRunsView(workspace, await previewNow()), 'dark', { staleAfterSec: STALE_AFTER_SEC });
    }
    if (kind === 'stale' || kind === 'stale-soon') return staleRunsPageHtml(dest, kind, 'dark');
    throw new Error(`知らないページの種類 ${kind}`);
  });
  return pageBodies(html).map(panelsOf).join('\n');
}

for (const kind of Object.keys(PANEL_SHA256)) {
  test(`D0025-AC-75: 既存のページ（${kind}）の「図と出力」「使用量」のパネルの HTML の SHA-256 は、今の作りで測った値のまま（今のまま通る。守る）`, async () => {
    assert.equal(sha256(await existingPagePanels(kind)), PANEL_SHA256[kind], `${kind}: パネルの HTML が変わった`);
  });
}

test('D0025-AC-75: 同じ種類のページを 2 回作っても、パネルの HTML は同じ（時刻・一時フォルダの名前に左右されない。今のまま通る。守る）', async () => {
  for (const kind of ['running', 'runs', 'stale-soon']) assert.equal(await existingPagePanels(kind), await existingPagePanels(kind), kind);
});

test('D0025-AC-75: 成果物を変えても（全部「まだない」・成果物が 0 個・外から来た文字の入った成果物）、「図と出力」「使用量」のパネルの HTML は変わらない（今のまま通る。守る）', async () => {
  const view = await readShowcaseView(SHOWCASE_DIR);
  const base = panelsOf(renderViewBody(view));
  const changed = [
    { ...view, artifacts: view.artifacts.map((a) => ({ ...a, ready: false })) },
    { ...view, artifacts: [] },
    { ...view, artifacts: view.artifacts.map((a) => ({ ...a, name: `${a.name}"<script>`, label: '<b>x</b>', ready: true, text: '# t\n<script>alert(1)</script>', cut: true })) },
  ];
  for (const [i, v] of changed.entries()) assert.equal(panelsOf(renderViewBody(v as unknown as typeof view)), base, `${i + 1} 通り目`);
});

test('D0025-AC-75: 検査そのもの：panelsOf は「図と出力」と「使用量」のパネルだけを取り出し、「成果物」のパネルの中身や属性が変わっても同じ。パネルの中身が変われば違う文字になる', () => {
  const panel = (key: string, body: string, extra = ''): string => `<div class="tabpanel" role="tabpanel" data-detail-panel="${key}"${extra}>${body}</div>`;
  const page = (artifacts: string, diagram = 'D', usage = 'U'): string =>
    `<main class="detail"><h1>t</h1>${panel('diagram', diagram)}${artifacts}${panel('usage', usage, ' hidden')}</main></div></div>`;
  const a = panelsOf(page(panel('artifacts', 'A1', ' hidden')));
  assert.equal(a, panel('diagram', 'D') + panel('usage', 'U', ' hidden'));
  assert.equal(panelsOf(page(panel('artifacts', '<ul class="art-list">…</ul>', ' hidden data-scroll="panel-artifacts"'))), a, '成果物のパネルの中身と属性は含めない');
  assert.notEqual(panelsOf(page(panel('artifacts', 'A1'), 'D2')), a, '図のパネルが変われば違う');
  assert.notEqual(panelsOf(page(panel('artifacts', 'A1'), 'D', 'U2')), a, '使用量のパネルが変われば違う');
  assert.throws(() => panelsOf('<main></main>'), '「図と出力」のパネルが無ければ落ちる');
});
