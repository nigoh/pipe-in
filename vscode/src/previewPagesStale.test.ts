// 確認用ページの素材のテスト（D0021 の AC-39〜41）：scripts/previewPages.ts と scripts/preview.ts が作る、止まっているかもしれない実行の印の見本。
// 画面そのもの（橙の点線・印の文字・動き）は Playwright で見る。ここで確かめるのは、画面で見る前の素材：
// 動かす側（renderPanelHtml の出力を bootPanel に渡し、6 つの面に is-stale が付くか）と、ページ側（文字）、見本の木の作り方、preview.ts の呼び方。
// 確認用ページの HTML は bootPanel に渡さない（置き換えのスクリプトが先に拾われ、パネルのスクリプトが動かないため）。
// 新しい関数は、テスト先行のときに「まだ無い」で落ちるように、動的 import で読んでから呼ぶ（ファイルごと import で落ちて、今のまま通る検査まで赤になるのを避ける）。
// 見本の木は一時フォルダの中にだけ作る。tests/fixtures/ には書かない（指紋で確かめる）。
// 「見本のログの更新時刻を、見本の今にそろえる」（AC-41）は、view.quietSec が 0 かどうかでは確かめられない（写しの更新時刻は本物の今で、
// 見本の今より後になり、未来の時刻は 0 秒に丸められる）。そこで、写したログの更新時刻そのものを、見本の今（previewClock の nowMs）と比べる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { cp, mkdir, readFile, readdir, stat, utimes, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { HERE, makeRunKey } from './domain/runs.ts';
import type { PipelineView, ViewClock } from './domain/pipelineView.ts';
import type { RunListView } from './domain/runList.ts';
import { PANEL_PAGES, RUNNING_DIR, RUNNING_NEXT_DIR, RUNNING_SEC, SHOWCASE_DIR, THEMES, WAITING_DIR, WAITING_SEC, panelKind } from '../scripts/previewPages.ts';
import type { Theme } from '../scripts/previewPages.ts';
import { renderPanelHtml, renderViewBody } from './view/panelHtml.ts';
import { bootPanel } from './test/fakeDom.ts';
import type { PanelHarness } from './test/fakeDom.ts';
import { withTempDir } from './test/tempDir.ts';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const NONCE = 'preview';
const STALE_AFTER = 600;
const DIAGRAMS = makeRunKey(HERE, 'diagrams');
const FIX_LOGIN = 'wt.fix-login|';
const SURVEY = makeRunKey(HERE, 'survey');
const THEME_NAMES: Theme[] = ['light', 'dark'];
/** HTML の属性としての data-stale-after="…"（パネルのスクリプトの文字には、名前だけが出る） */
const STALE_ATTR = /\sdata-stale-after="/;

// 目安（staleAfterSec）を受ける renderPanelHtml・renderViewBody。実装の段で型に入るまでは、余分な引数を受ける型で呼ぶ。
const panelWith = renderPanelHtml as (view: PipelineView, nonce: string, list?: RunListView | null, staleAfterSec?: number | null) => string;
const bodyWith = renderViewBody as (view: PipelineView, list?: RunListView | null, staleAfterSec?: number | null) => string;

// ---- 新しい関数を動的 import で読む（テスト先行のときは「まだ無い」で落ちる） ----

type Pages = Record<string, any>;
const loadPages = async (): Promise<Pages> => (await import('../scripts/previewPages.ts')) as unknown as Pages;
/** previewPages.ts の関数を取り出す。無ければ「まだ無い」で落とす。 */
function need(pages: Pages, name: string): (...args: any[]) => any {
  assert.equal(typeof pages[name], 'function', `scripts/previewPages.ts の ${name} がまだ無い`);
  return pages[name] as (...args: any[]) => any;
}

interface Entry {
  key: string;
  view: PipelineView;
  listView: RunListView;
  selected: boolean;
}
const entryOf = (entries: readonly Entry[], key: string): Entry => {
  const found = entries.find((e) => e.key === key);
  assert.ok(found !== undefined, `${key} の行がある`);
  return found;
};
// quietSec（実装の段で型に入る）と runningSec は、型に頼らず読む
const quietOf = (view: PipelineView): number | null | undefined => (view as unknown as { quietSec?: number | null }).quietSec;
/** 動いている段の節の、段が始まってからの秒。 */
const runningSecOf = (view: PipelineView): number | null | undefined =>
  (view.nodes.find((n) => n.id === view.runningStage) as unknown as { runningSec?: number | null } | undefined)?.runningSec;

/** 見本の「今」（確認待ちの見本の待ち始めから WAITING_SEC 秒後。一覧の見本の時計と同じ）。 */
async function previewNow(pages: Pages): Promise<ViewClock> {
  const since = (await pages.startOfLiveness(WAITING_DIR)) as string;
  return pages.previewClock(since, WAITING_SEC) as ViewClock;
}

interface TreeOptions {
  diagramsQuietSec?: number;
  fixLoginQuietSec?: number;
}
/** 一覧の見本の木を dest の中に組み立て、本物の読み取りで行ごとの図を作る。 */
async function readTree(pages: Pages, dest: string, tree?: TreeOptions, selected?: string): Promise<Entry[]> {
  const { workspace } = (await pages.buildRunsTree(dest, tree)) as { workspace: string };
  return (await pages.readRunsView(workspace, await previewNow(pages), selected === undefined ? undefined : { selected })) as Entry[];
}

// 6 つの面（節・入る矢印・一覧の行・バッジ・知らせ・時系列の行）。一覧の行は diagrams の行を見る。
const SURFACES: readonly (readonly [string, string])[] = [
  ['図の節', 'g.node.is-stale'],
  ['入る矢印', 'line.edge.is-flowing.is-stale'],
  ['一覧の行', `button.run-row.is-stale[data-run="${DIAGRAMS}"]`],
  ['詳細のバッジ', 'span.badge.stale-badge.is-stale'],
  ['詳細の知らせ', 'div.notice.stale-notice.is-stale'],
  ['時系列の行', 'div.g-row.is-stale'],
];
const missingSurfaces = (h: PanelHarness): string[] => SURFACES.filter(([, selector]) => h.doc.querySelectorAll(selector).length === 0).map(([name]) => name);
const staleCount = (h: PanelHarness): number => h.doc.querySelectorAll('.is-stale').length;
const quietValues = (h: PanelHarness): string[] => [...new Set(h.doc.querySelectorAll('[data-quiet]').map((n) => n.getAttribute('data-quiet')!))];

// ---- ページの文字の読み方 ----

/** `window.__previewNext=…html:"…"` に埋めた本体を、JSON として読み戻す。 */
function previewNextBody(html: string): string {
  const at = html.indexOf('window.__previewNext=');
  assert.ok(at >= 0, 'window.__previewNext がある');
  const m = /html:("(?:[^"\\]|\\.)*")/.exec(html.slice(at));
  assert.ok(m !== null, '__previewNext に本体の文字が埋まっている');
  return JSON.parse(m[1]!) as string;
}
/** 実行の一覧のページに埋めた、行の key ごとの本体（BODIES）。 */
function bodiesOf(html: string): Record<string, string> {
  const m = /const BODIES=(\{[\s\S]*?\});return\(\)/.exec(html);
  assert.ok(m !== null, 'BODIES がある');
  return JSON.parse(m[1]!) as Record<string, string>;
}
function usedVars(html: string): string[] {
  return [...new Set([...html.matchAll(/var\(\s*(--vscode-[\w-]+)/g)].map((m) => m[1]!))].sort();
}
function definedVars(css: string): Set<string> {
  return new Set([...css.matchAll(/(--vscode-[\w-]+)\s*:/g)].map((m) => m[1]!));
}
/** 本体の文字にある data-quiet="…" の値（同じ値は 1 つにまとめ、文字の順に並べる）。ページに埋めた本体（BODIES・__previewNext）は " が \" になっているので、数えない。 */
function quietSet(html: string): string[] {
  return [...new Set([...html.matchAll(/\sdata-quiet="(\d+)"/g)].map((m) => m[1]!))].sort();
}
/** 本体の文字で aria-pressed="true" の行の data-run（選んでいる行）。 */
function pressedRuns(html: string): string[] {
  return [...html.matchAll(/<button\b[^>]*\sdata-run="([^"]*)"[^>]*\saria-pressed="true"/g)].map((m) => m[1]!);
}

// ---- 更新なし・もうすぐのページの文字（種類とテーマごとに 1 回だけ作り、確かめごとのテストで使い回す） ----

type StalePageKind = 'stale' | 'stale-soon';
const builtPages = new Map<string, Promise<{ html: string; dest: string }>>();
/** staleRunsPageHtml が作ったページの文字と、そのとき使った一時フォルダの名前（フォルダは作ったあとで消してある）。 */
function builtPage(kind: StalePageKind, theme: Theme): Promise<{ html: string; dest: string }> {
  const key = `${kind}|${theme}`;
  let page = builtPages.get(key);
  if (page === undefined) {
    page = (async () => {
      const pages = await loadPages();
      return withTempDir(async (dest) => ({ html: (await need(pages, 'staleRunsPageHtml')(dest, kind, theme)) as string, dest }));
    })();
    builtPages.set(key, page);
  }
  return page;
}

// ---- 指紋（見本の記録が変わっていないかを見る） ----

/** dir の下のファイルごとの「相対パス・大きさ・更新時刻・中身の指紋」。順番は名前順。 */
async function fingerprint(dir: string): Promise<string[]> {
  const out: string[] = [];
  const walk = async (d: string): Promise<void> => {
    const entries = (await readdir(d, { withFileTypes: true })).sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    for (const ent of entries) {
      const full = path.join(d, ent.name);
      if (ent.isDirectory()) {
        await walk(full);
        continue;
      }
      const info = await stat(full);
      const sum = createHash('sha1').update(await readFile(full)).digest('hex');
      out.push(`${path.relative(dir, full).split(path.sep).join('/')}|${info.size}|${info.mtimeMs}|${sum}`);
    }
  };
  await walk(dir);
  return out;
}
const FIXTURE_DIRS = [SHOWCASE_DIR, RUNNING_DIR, RUNNING_NEXT_DIR, WAITING_DIR];
const fixturePrints = async (): Promise<string[][]> => Promise.all(FIXTURE_DIRS.map(fingerprint));

/** dir/logs/*.jsonl の更新時刻（ミリ秒、名前順）。 */
async function logTimes(dir: string): Promise<[string, number][]> {
  const names = (await readdir(path.join(dir, 'logs'))).filter((n) => n.endsWith('.jsonl')).sort();
  return Promise.all(names.map(async (n): Promise<[string, number]> => [n, Math.round((await stat(path.join(dir, 'logs', n))).mtimeMs)]));
}
/**
 * ログの更新時刻が、見本の「今」（nowMs）にそろっていること。ログが 1 つ以上あり、どれも nowMs から 1 秒未満のずれ。
 * そろえていなければ、写した時刻（本物の今）は見本の今より数日あとになる。1 秒の許しは、その差に比べて十分に小さい。
 */
function assertAligned(times: readonly (readonly [string, number])[], nowMs: number): void {
  assert.ok(times.length > 0, 'ログを写している');
  const off = times.filter(([, ms]) => Math.abs(ms - nowMs) >= 1000).map(([name, ms]) => `${name}: 見本の今との差 ${(ms - nowMs) / 1000} 秒`);
  assert.deepEqual(off, [], '見本の今にそろっていないログ');
}

// ======== AC-39：更新なしの見本（run-panel-stale-light・-dark） ========

// 目安を越える 12 秒・手前の 5 秒（STALE_OVER_SEC・STALE_SOON_SEC）は previewPages.ts の中の定数でよい。export は要らない（設計は export を求めない）。
// 値は、更新なしの見本が 612 と 640（下の buildRunsTree と、ページ側の文字）、もうすぐの見本が 595（動かす側とページ側）で守られる。
test('D0021-AC-39: 見本の目安 STALE_AFTER_SEC は 600 秒（preview.ts が確認用ページの組み立てに渡すので export する）', async () => {
  const pages = await loadPages();
  assert.equal(pages.STALE_AFTER_SEC, 600);
});

test('D0021-AC-39: PANEL_PAGES に run-panel-stale-light・run-panel-stale-dark があり、panelKind は stale', () => {
  const stalePages = PANEL_PAGES.filter(([name]) => name.startsWith('run-panel-stale-') && !name.includes('-soon-')).map(([name, theme]) => [name, theme]);
  assert.deepEqual(stalePages, [
    ['run-panel-stale-light', 'light'],
    ['run-panel-stale-dark', 'dark'],
  ]);
  assert.equal(panelKind('run-panel-stale-light'), 'stale');
  assert.equal(panelKind('run-panel-stale-dark'), 'stale');
});

test('D0021-AC-39: 今までのページの種類は変わらない（守り続ける検査）', () => {
  assert.equal(panelKind('run-panel-light'), 'done');
  assert.equal(panelKind('run-panel-running-dark'), 'running');
  assert.equal(panelKind('run-panel-waiting-dark'), 'waiting');
  assert.equal(panelKind('run-panel-runs-dark'), 'runs');
  assert.equal(panelKind('run-panel-runs-omitted-dark'), 'runs-omitted');
});

/** buildRunsTree が組んだ木の中の、動いている 2 つの run（いまの work_dir の diagrams・別の worktree の fix-login）。 */
const TREE_RUNS = [
  { label: 'diagrams', key: DIAGRAMS, quietSec: 612, startSec: RUNNING_SEC, dir: (dest: string) => path.join(dest, 'main', 'docs', 'pipeline', 'diagrams') },
  { label: 'fix-login', key: FIX_LOGIN, quietSec: 640, startSec: 20, dir: (dest: string) => path.join(dest, 'fix-login', 'docs', 'pipeline') },
] as const;
const TREE_STALE: TreeOptions = { diagramsQuietSec: 612, fixLoginQuietSec: 640 };

for (const run of TREE_RUNS) {
  test(`D0021-AC-39: buildRunsTree の options で、${run.label} の quietSec が「今 − ${run.quietSec} 秒」の ${run.quietSec} になる`, async () => {
    const pages = await loadPages();
    await withTempDir(async (dest) => {
      assert.equal(quietOf(entryOf(await readTree(pages, dest, TREE_STALE), run.key).view), run.quietSec);
    });
  });

  test(`D0021-AC-39: buildRunsTree の options で、${run.label} の段の始まりも、経過が更新なしの時間（${run.quietSec} 秒）以上になる`, async () => {
    const pages = await loadPages();
    await withTempDir(async (dest) => {
      const elapsed = runningSecOf(entryOf(await readTree(pages, dest, TREE_STALE), run.key).view) ?? 0;
      assert.ok(elapsed >= run.quietSec, `${run.label} の経過 ${elapsed} 秒は更新なしの時間 ${run.quietSec} 秒以上`);
    });
  });

  test(`D0021-AC-39: buildRunsTree の既定でも、${run.label} の段の始まりは今までと同じ（経過 ${run.startSec} 秒。守り続ける検査）`, async () => {
    const pages = await loadPages();
    await withTempDir(async (dest) => {
      assert.equal(runningSecOf(entryOf(await readTree(pages, dest), run.key).view), run.startSec);
    });
  });

  test(`D0021-AC-39: buildRunsTree の既定は、${run.label} の更新時刻が「今」で、quietSec は 0`, async () => {
    const pages = await loadPages();
    await withTempDir(async (dest) => {
      assert.equal(quietOf(entryOf(await readTree(pages, dest), run.key).view), 0);
    });
  });

  test(`D0021-AC-41: buildRunsTree の既定は、${run.label} のログの更新時刻を見本の「今」にそろえる（写した時刻＝本物の今のままではない）`, async () => {
    const pages = await loadPages();
    const nowMs = (await previewNow(pages)).nowMs;
    await withTempDir(async (dest) => {
      await pages.buildRunsTree(dest);
      assertAligned(await logTimes(run.dir(dest)), nowMs);
    });
  });
}

test('D0021-AC-39: readRunsView の options.selected で、初めに選ぶ行を決められる（選ぶのは 1 行だけ）', async () => {
  const pages = await loadPages();
  await withTempDir(async (dest) => {
    for (const [i, key] of [DIAGRAMS, SURVEY].entries()) {
      const entries = await readTree(pages, path.join(dest, `tree${i}`), undefined, key);
      assert.deepEqual(entries.filter((e) => e.selected).map((e) => e.key), [key], `${key} を選ぶ`);
      assert.equal(entryOf(entries, key).listView.selected, key, 'その行を選んだ一覧');
    }
  });
});

test('D0021-AC-39: 動かす側：更新なしの見本（diagrams が目安を 12 秒越え）を renderPanelHtml(目安 600) で組んで起動すると、6 つの面のそれぞれに is-stale が付く', async () => {
  const pages = await loadPages();
  await withTempDir(async (dest) => {
    const entries = await readTree(pages, dest, TREE_STALE, DIAGRAMS);
    const entry = entryOf(entries, DIAGRAMS);
    const h = bootPanel(panelWith(entry.view, NONCE, entry.listView, STALE_AFTER));
    assert.ok(quietValues(h).includes('612'), `印の元（data-quiet）に 612 が出ている: ${quietValues(h).join(',')}`);
    assert.deepEqual(missingSurfaces(h), [], 'is-stale が付いていない面');
  });
});

// ページ側（文字）の確かめ。1 つの確かめを 1 つのテストにし、種類とテーマごとに作ったページ（builtPage）を使い回す。
type PageCheck = readonly [string, (html: string, dest: string, theme: Theme) => void];

/** 更新なし・もうすぐのどちらのページにも要る確かめ（CSP に合う書き方・使う色・手元の情報）。 */
const COMMON_PAGE_CHECKS: readonly PageCheck[] = [
  [
    'script と style のタグはすべて nonce="preview" を持つ（3 つ以上ある）',
    (html) => {
      const tags = [...html.matchAll(/<(script|style)\b[^>]*>/g)].map((m) => m[0]);
      assert.ok(tags.length >= 3, `本物の style・script と、足したテーマの色・置き換えのスクリプト（${tags.length} 個）`);
      assert.deepEqual(tags.filter((t) => !t.includes('nonce="preview"')), []);
    },
  ],
  ['style 属性が無い', (html) => assert.doesNotMatch(html, /\sstyle="/)],
  [
    '使う --vscode-* の色をすべて THEMES が決めている',
    (html, _dest, theme) => {
      const defined = definedVars(THEMES[theme]);
      assert.deepEqual(usedVars(html).filter((name) => !defined.has(name)), [], `${theme}: THEMES に無い色`);
    },
  ],
  ['テーマの色がページに入っている', (html, _dest, theme) => assert.ok(html.includes(THEMES[theme]))],
  ['一時フォルダの絶対パスが出ていない', (html, dest) => assert.ok(!html.includes(dest))],
];

const STALE_PAGE_CHECKS: readonly PageCheck[] = [
  ['初めの本体に目安 data-stale-after="600" が出ている', (html) => assert.ok(html.includes('data-stale-after="600"'))],
  ['印の元（data-quiet）は、diagrams の 612 と fix-login の 640 の 2 つだけ', (html) => assert.deepEqual(quietSet(html), ['612', '640'])],
  ['初めに選ぶ行は diagrams だけ', (html) => assert.deepEqual(pressedRuns(html), [DIAGRAMS])],
  ['次の見本の補助 __previewNext は無い', (html) => assert.ok(!html.includes('__previewNext'))],
];

for (const theme of THEME_NAMES) {
  for (const [label, check] of [...STALE_PAGE_CHECKS, ...COMMON_PAGE_CHECKS]) {
    test(`D0021-AC-39: ページ側（文字・${theme}）：staleRunsPageHtml(stale) のページは、${label}`, async () => {
      const { html, dest } = await builtPage('stale', theme);
      check(html, dest, theme);
    });
  }
}

test('D0021-AC-39: 見本の木を作っても（更新なし・もうすぐ・そろえて読む）、tests/fixtures/ の見本の内容と更新時刻は変わらない', async () => {
  const pages = await loadPages();
  const staleRunsPageHtml = need(pages, 'staleRunsPageHtml');
  const readLiveViewAligned = need(pages, 'readLiveViewAligned');
  const before = await fixturePrints();
  for (const [kind, theme] of [['stale', 'light'], ['stale-soon', 'dark']] as const) {
    await withTempDir(async (dest) => void (await staleRunsPageHtml(dest, kind, theme)));
  }
  await withTempDir(async (dest) => {
    await readLiveViewAligned(RUNNING_DIR, RUNNING_SEC, dest);
    await readLiveViewAligned(RUNNING_NEXT_DIR, 5, dest);
    await readLiveViewAligned(WAITING_DIR, WAITING_SEC, dest);
  });
  assert.deepEqual(await fixturePrints(), before);
});

test('D0021-AC-39: 検査そのもの：指紋は、内容を変えた木・更新時刻だけ変えた木を見つけ、変えない木は見逃す', async () => {
  await withTempDir(async (dir) => {
    await mkdir(path.join(dir, 'logs'));
    const file = path.join(dir, 'logs', '01_a.jsonl');
    await writeFile(file, 'abc\n');
    await writeFile(path.join(dir, 'state.json'), '{}\n');
    const t0 = new Date('2026-10-17T10:00:00Z');
    await utimes(file, t0, t0);
    const base = await fingerprint(dir);
    assert.deepEqual(await fingerprint(dir), base, '変えない木は見逃す');

    await writeFile(file, 'abd\n'); // 大きさは同じで、中身だけ違う
    await utimes(file, t0, t0);
    assert.notDeepEqual(await fingerprint(dir), base, '内容だけ変えた木を見つける');

    await writeFile(file, 'abc\n');
    await utimes(file, t0, t0);
    assert.deepEqual(await fingerprint(dir), base, '戻すと同じに戻る');
    const t1 = new Date('2026-10-17T10:00:10Z');
    await utimes(file, t1, t1);
    assert.notDeepEqual(await fingerprint(dir), base, '更新時刻だけ変えた木を見つける');
  });
});

// ======== AC-40：もうすぐ印が付く見本（run-panel-stale-soon-dark） ========

test('D0021-AC-40: PANEL_PAGES に run-panel-stale-soon-dark があり、panelKind は stale-soon（stale とは別）', () => {
  assert.deepEqual(PANEL_PAGES.filter(([name]) => name.includes('-stale-soon-')).map(([name, theme]) => [name, theme]), [['run-panel-stale-soon-dark', 'dark']]);
  assert.equal(panelKind('run-panel-stale-soon-dark'), 'stale-soon');
  assert.equal(panelKind('run-panel-stale-dark'), 'stale');
});

test('D0021-AC-40: 動かす側：diagrams の quietSec は 595。起動直後と 4 秒後は is-stale が無く、5 秒後に 6 つの面に付く。更新後の本体を送ると 0 個になる', async () => {
  const pages = await loadPages();
  await withTempDir(async (dest) => {
    const soon = entryOf(await readTree(pages, dest, { diagramsQuietSec: 595, fixLoginQuietSec: 0 }, DIAGRAMS), DIAGRAMS);
    const next = entryOf(await readTree(pages, path.join(dest, 'next'), { diagramsQuietSec: 0, fixLoginQuietSec: 0 }, DIAGRAMS), DIAGRAMS);
    assert.equal(quietOf(soon.view), 595);
    const h = bootPanel(panelWith(soon.view, NONCE, soon.listView, STALE_AFTER));
    assert.ok(quietValues(h).includes('595'), `印の元（data-quiet）に 595 が出ている: ${quietValues(h).join(',')}`);
    assert.equal(staleCount(h), 0, '起動直後');
    h.advance(4000);
    assert.equal(staleCount(h), 0, '4 秒後は 599');
    h.advance(1000);
    assert.deepEqual(missingSurfaces(h), [], '5 秒後（600）に is-stale が付いていない面');
    h.send({ type: 'render', html: bodyWith(next.view, next.listView, STALE_AFTER) });
    assert.equal(staleCount(h), 0, '更新後の本体を送ると、印が全部消える');
  });
});

const SOON_PAGE_CHECKS: readonly PageCheck[] = [
  ['初めの本体に目安 data-stale-after="600" が出ている', (html) => assert.ok(html.includes('data-stale-after="600"'))],
  ['印の元（data-quiet）は、diagrams の 595 と fix-login の「今」の 0 の 2 つだけ', (html) => assert.deepEqual(quietSet(html), ['0', '595'])],
  ['初めに選ぶ行は diagrams だけ', (html) => assert.deepEqual(pressedRuns(html), [DIAGRAMS])],
  ['window.__previewNext がある', (html) => assert.ok(html.includes('window.__previewNext='))],
  ['__previewNext に埋めた本体は、印の元がすべて 0（更新後は diagrams も「今」）', (html) => assert.deepEqual(quietSet(previewNextBody(html)), ['0'])],
  ['__previewNext に埋めた本体も、目安 600', (html) => assert.ok(previewNextBody(html).includes('data-stale-after="600"'))],
];
// 共通の確かめ（nonce は __previewNext の script にも要る）
for (const [label, check] of [...SOON_PAGE_CHECKS, ...COMMON_PAGE_CHECKS]) {
  test(`D0021-AC-40: ページ側（文字・dark）：staleRunsPageHtml(stale-soon) のページは、${label}`, async () => {
    const { html, dest } = await builtPage('stale-soon', 'dark');
    check(html, dest, 'dark');
  });
}

test('D0021-AC-40: panelRunsPreviewHtml の options：staleAfterSec を各本体に渡し、next があれば __previewNext（nonce つき）を足す', async () => {
  const pages = await loadPages();
  await withTempDir(async (dest) => {
    const entries = await readTree(pages, path.join(dest, 'a'), undefined, DIAGRAMS);
    const next = entryOf(await readTree(pages, path.join(dest, 'b'), undefined, DIAGRAMS), DIAGRAMS);
    const html = pages.panelRunsPreviewHtml(entries, 'dark', { staleAfterSec: STALE_AFTER, next }) as string;
    assert.ok(bodiesOf(html)[DIAGRAMS]!.includes('data-stale-after="600"'), '行ごとの本体に目安が渡っている');
    assert.ok(html.includes('data-stale-after="600"'), '初めの本体にも目安が渡っている');
    assert.match(html, /<script nonce="preview">window\.__previewNext=/);
    assert.ok(previewNextBody(html).includes('data-stale-after="600"'), '次の本体も同じ目安');
  });
});

test('D0021-AC-40: panelRunsPreviewHtml を options なし（3 つ目は時計の object。今までの呼び方）で呼ぶと、目安も __previewNext も無い（守り続ける検査）', async () => {
  const pages = await loadPages();
  await withTempDir(async (dest) => {
    const entries = await readTree(pages, dest);
    const clock = await previewNow(pages);
    const html = pages.panelRunsPreviewHtml(entries, 'dark', clock) as string;
    assert.ok(!html.includes('__previewNext'));
    assert.doesNotMatch(html, STALE_ATTR, '目安の属性（data-stale-after="…"）は出ない。スクリプトの文字には名前が出てよい');
    assert.match(html, /<body>\s*<script nonce="preview">window\.acquireVsCodeApi=/);
  });
});

// ======== AC-41：既存のページ・目安の手前の見本に、印がどこにも出ない ========
// 下の「動かす側」（is-stale が 0 個）は、見本が見本の今にそろっているかは見ない（そろえなくても、写しの更新時刻は見本の今より後で、0 秒に丸められるため）。
// そろえているかは、写したログの更新時刻そのものを見本の今と比べる確かめ（readLiveViewAligned・buildRunsTree の既定）が見る。

test('D0021-AC-41: 動かす側：動いている・次の・確認待ちの見本を readLiveViewAligned で読み、目安 600 で起動しても、is-stale は 0 個（動いている見本の data-quiet は 0）', async () => {
  const pages = await loadPages();
  const aligned = need(pages, 'readLiveViewAligned');
  await withTempDir(async (dest) => {
    const samples: readonly (readonly [string, string, number, boolean])[] = [
      ['動いている見本', RUNNING_DIR, RUNNING_SEC, true],
      ['次の見本', RUNNING_NEXT_DIR, 5, true],
      ['確認待ちの見本', WAITING_DIR, WAITING_SEC, false],
    ];
    for (const [label, dir, sec, running] of samples) {
      const view = (await aligned(dir, sec, dest)) as PipelineView;
      const h = bootPanel(panelWith(view, NONCE, null, STALE_AFTER));
      if (running) assert.deepEqual(quietValues(h), ['0'], `${label}：印の元は 0（対照）`);
      assert.equal(staleCount(h), 0, `${label}：起動直後`);
      h.advance(5000);
      assert.equal(staleCount(h), 0, `${label}：5 秒後`);
    }
  });
});

test('D0021-AC-41: 動かす側：一覧の見本（buildRunsTree の既定と readRunsView）の全部の行も、目安 600 で起動して is-stale は 0 個。動いている行（diagrams・fix-login）の data-quiet は 0', async () => {
  const pages = await loadPages();
  await withTempDir(async (dest) => {
    const entries = await readTree(pages, dest);
    assert.ok(entries.length >= 7);
    for (const e of entries) {
      const h = bootPanel(panelWith(e.view, NONCE, e.listView, STALE_AFTER));
      if (e.key === DIAGRAMS || e.key === FIX_LOGIN) assert.deepEqual(quietValues(h), ['0'], `${e.key}：印の元は 0（対照）`);
      assert.equal(staleCount(h), 0, `${e.key}：起動直後`);
      h.advance(5000);
      assert.equal(staleCount(h), 0, `${e.key}：5 秒後`);
    }
  });
});

// panelPreviewHtml の 4 つ目の引数（目安）。見本の読み方はここの確かめ（目安を渡すか）と関係がないので、今ある readLiveView で読む。
test('D0021-AC-41: panelPreviewHtml(view, theme, next, 600) は、初めの本体に目安 600 を渡す', async () => {
  const pages = await loadPages();
  const view = (await pages.readLiveView(RUNNING_DIR, RUNNING_SEC)) as PipelineView;
  const next = (await pages.readLiveView(RUNNING_NEXT_DIR, 5)) as PipelineView;
  assert.ok((pages.panelPreviewHtml(view, 'dark', next, STALE_AFTER) as string).includes('data-stale-after="600"'));
});

test('D0021-AC-41: panelPreviewHtml(view, theme, next, 600) は、次の本体（__previewNext に埋める）にも目安 600 を渡す', async () => {
  const pages = await loadPages();
  const view = (await pages.readLiveView(RUNNING_DIR, RUNNING_SEC)) as PipelineView;
  const next = (await pages.readLiveView(RUNNING_NEXT_DIR, 5)) as PipelineView;
  assert.ok(previewNextBody(pages.panelPreviewHtml(view, 'dark', next, STALE_AFTER) as string).includes('data-stale-after="600"'));
});

test('D0021-AC-41: readLiveViewAligned で読んだ見本を panelPreviewHtml(…, 600) に渡すと、初めの本体も次の本体も、印の元（data-quiet）は 0 だけ', async () => {
  const pages = await loadPages();
  const aligned = need(pages, 'readLiveViewAligned');
  await withTempDir(async (dest) => {
    const view = (await aligned(RUNNING_DIR, RUNNING_SEC, dest)) as PipelineView;
    const next = (await aligned(RUNNING_NEXT_DIR, 5, dest)) as PipelineView;
    const html = pages.panelPreviewHtml(view, 'dark', next, STALE_AFTER) as string;
    assert.deepEqual(quietSet(html), ['0']);
    assert.deepEqual(quietSet(previewNextBody(html)), ['0'], '次の本体も同じ');
  });
});

test('D0021-AC-41: panelPreviewHtml(view, theme, next) は目安を渡さない呼び方で、今までと同じ（印の属性 data-stale-after が出ない。守り続ける検査）', async () => {
  const pages = await loadPages();
  const view = (await pages.readLiveView(RUNNING_DIR, RUNNING_SEC)) as PipelineView;
  const next = (await pages.readLiveView(RUNNING_NEXT_DIR, 5)) as PipelineView;
  assert.doesNotMatch(pages.panelPreviewHtml(view, 'dark', next) as string, STALE_ATTR);
});

const ALIGNED_SAMPLES = [
  { label: 'RUNNING_DIR', dir: RUNNING_DIR, sec: RUNNING_SEC },
  { label: 'RUNNING_NEXT_DIR', dir: RUNNING_NEXT_DIR, sec: 5 },
] as const;
for (const { label, dir, sec } of ALIGNED_SAMPLES) {
  test(`D0021-AC-41: readLiveViewAligned(${label}) の view.quietSec は 0`, async () => {
    const pages = await loadPages();
    await withTempDir(async (dest) => {
      assert.equal(quietOf((await need(pages, 'readLiveViewAligned')(dir, sec, dest)) as PipelineView), 0);
    });
  });

  test(`D0021-AC-41: readLiveViewAligned(${label}) の段の経過と動いている段は、readLiveView と同じ（そろえて読んでも、今までの見え方は変わらない）`, async () => {
    const pages = await loadPages();
    await withTempDir(async (dest) => {
      const view = (await need(pages, 'readLiveViewAligned')(dir, sec, dest)) as PipelineView;
      const plain = (await pages.readLiveView(dir, sec)) as PipelineView;
      assert.equal(runningSecOf(view), runningSecOf(plain));
      assert.equal(view.runningStage, plain.runningStage);
    });
  });
}

for (const { label, dir, sec } of [...ALIGNED_SAMPLES, { label: 'WAITING_DIR', dir: WAITING_DIR, sec: WAITING_SEC }] as const) {
  test(`D0021-AC-41: readLiveViewAligned(${label}) は見本を dest/<見本の名前> に写し、写したログの更新時刻を見本の「今」にそろえる（本物の今ではない）`, async () => {
    const pages = await loadPages();
    const nowMs = (pages.previewClock((await pages.startOfLiveness(dir)) as string, sec) as ViewClock).nowMs;
    await withTempDir(async (dest) => {
      await need(pages, 'readLiveViewAligned')(dir, sec, dest);
      const copied = path.join(dest, path.basename(dir));
      assert.ok(existsSync(path.join(copied, 'state.json')), '見本を dest の中に写している');
      assertAligned(await logTimes(copied), nowMs);
    });
  });
}

for (const { label, dir, sec } of ALIGNED_SAMPLES) {
  test(`D0021-AC-41: ログの更新時刻が 2000 年の見本（${label} の写し）でも、readLiveViewAligned の view.quietSec は 0（対照：そのまま読むと 604800＝7 日で頭打ち）`, async () => {
    const pages = await loadPages();
    await withTempDir(async (tmp) => {
      const old = path.join(tmp, 'old', path.basename(dir));
      await cp(dir, old, { recursive: true });
      const t2000 = new Date('2000-01-01T00:00:00Z');
      for (const name of await readdir(path.join(old, 'logs'))) await utimes(path.join(old, 'logs', name), t2000, t2000);
      const clock = pages.previewClock((await pages.startOfLiveness(old)) as string, sec) as ViewClock;
      assert.equal(quietOf((await pages.readShowcaseView(old, clock)) as PipelineView), 604800, '対照：そろえずに読むと、古い更新時刻のまま 7 日で頭打ちになる');
      const dest = path.join(tmp, 'dest');
      await mkdir(dest);
      assert.equal(quietOf((await need(pages, 'readLiveViewAligned')(old, sec, dest)) as PipelineView), 0);
    });
  });
}

test('D0021-AC-41: setLogTimes(dir, atMs) は dir/logs/*.jsonl の更新時刻を atMs にそろえる（state.json は変えない）', async () => {
  const pages = await loadPages();
  await withTempDir(async (dir) => {
    await mkdir(path.join(dir, 'logs'));
    const old = new Date('2026-01-01T00:00:00Z');
    for (const rel of ['logs/01_a.jsonl', 'logs/02_b.jsonl', 'state.json']) {
      await writeFile(path.join(dir, rel), '{}\n');
      await utimes(path.join(dir, rel), old, old);
    }
    const at = Date.UTC(2026, 9, 17, 10, 2, 55);
    await need(pages, 'setLogTimes')(dir, at);
    assert.deepEqual(await logTimes(dir), [
      ['01_a.jsonl', at],
      ['02_b.jsonl', at],
    ]);
    assert.equal(Math.round((await stat(path.join(dir, 'state.json'))).mtimeMs), old.getTime(), 'logs/ の外は変えない');
  });
});

test('D0021-AC-41: copySample(src, dest, nowMs, 612) は見本を写し、ログの更新時刻を「今 − 612 秒」にする（既定の 0 秒前は「今」）。写す前の見本は変えない', async () => {
  const pages = await loadPages();
  const copySample = need(pages, 'copySample');
  const now = Date.UTC(2026, 9, 17, 10, 1, 23);
  const before = await fingerprint(RUNNING_DIR);
  await withTempDir(async (tmp) => {
    const late = path.join(tmp, 'late');
    await copySample(RUNNING_DIR, late, now, 612);
    const times = await logTimes(late);
    assert.ok(times.length > 0, 'ログを写している');
    assert.deepEqual([...new Set(times.map(([, ms]) => ms))], [now - 612_000]);
    assert.equal(readFileSync(path.join(late, 'state.json'), 'utf8'), readFileSync(path.join(RUNNING_DIR, 'state.json'), 'utf8'), '中身は見本のまま');
    const fresh = path.join(tmp, 'fresh');
    await copySample(RUNNING_DIR, fresh, now);
    assert.deepEqual([...new Set((await logTimes(fresh)).map(([, ms]) => ms))], [now]);
  });
  assert.deepEqual(await fingerprint(RUNNING_DIR), before);
});

// ---- preview.ts の呼び方を文字で守る（D0017-AC-37 の文字の検査と同じ形） ----

/** コメントを除く（`//` の前が `:` の URL は残す）。 */
const stripComments = (source: string): string => source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:\\])\/\/.*$/gm, '$1');
/** `name(` の呼び出しごとの、括弧の中の文字。 */
function callsOf(source: string, name: string): string[] {
  const calls: string[] = [];
  const re = new RegExp(`(?<![\\w.])${name}\\(`, 'g');
  for (let m = re.exec(source); m !== null; m = re.exec(source)) {
    let depth = 1;
    let i = re.lastIndex;
    for (; i < source.length && depth > 0; i++) {
      if (source[i] === '(') depth++;
      else if (source[i] === ')') depth--;
    }
    calls.push(source.slice(re.lastIndex, i - 1));
  }
  return calls;
}
/** preview.ts の文字の問題（見本を一時フォルダでそろえずに読む・目安を渡さない・更新なしのページを作らない）。無ければ空。 */
function previewProblems(source: string): string[] {
  const code = stripComments(source);
  const problems: string[] = [];
  const aligned = callsOf(code, 'readLiveViewAligned').length;
  if (aligned < 3) problems.push(`readLiveViewAligned( の呼び出しが ${aligned} 回（動いている・次の・確認待ちの 3 つとも要る）`);
  if (callsOf(code, 'readLiveView').length > 0) problems.push('readLiveView( を直接呼んでいる（tests/fixtures/ を直接読むと、更新時刻がチェックアウトの時刻になる）');
  for (const name of ['panelPreviewHtml', 'panelRunsPreviewHtml']) {
    const calls = callsOf(code, name);
    if (calls.length === 0) problems.push(`${name}( を呼んでいない`);
    if (calls.some((args) => !args.includes('STALE_AFTER_SEC'))) problems.push(`${name}( に目安（STALE_AFTER_SEC）を渡していない呼び出しがある`);
  }
  if (callsOf(code, 'staleRunsPageHtml').length === 0) problems.push('staleRunsPageHtml( を呼んでいない');
  return problems;
}

test('D0021-AC-41: scripts/preview.ts は readLiveViewAligned( を 3 回呼び、readLiveView( を直接呼ばず、panelPreviewHtml・panelRunsPreviewHtml に STALE_AFTER_SEC を渡し、staleRunsPageHtml( を呼ぶ', () => {
  assert.deepEqual(previewProblems(readFileSync(path.join(REPO, 'vscode', 'scripts', 'preview.ts'), 'utf8')), []);
});

const CLEAN_PREVIEW = [
  'const views = {',
  '  running: await readLiveViewAligned(RUNNING_DIR, RUNNING_SEC, dir),',
  '  waiting: await readLiveViewAligned(WAITING_DIR, WAITING_SEC, dir),',
  '};',
  'const runningNext = await readLiveViewAligned(RUNNING_NEXT_DIR, 5, dir);',
  'html = panelPreviewHtml(views.running, theme, runningNext, STALE_AFTER_SEC);',
  'html = panelRunsPreviewHtml(entries, theme, { staleAfterSec: STALE_AFTER_SEC });',
  'html = await staleRunsPageHtml(dest, kind, theme);',
].join('\n');

const BROKEN_PREVIEWS: readonly (readonly [string, string, string])[] = [
  ['見本を readLiveView( で直接読む', CLEAN_PREVIEW.replace('readLiveViewAligned(RUNNING_DIR', 'readLiveView(RUNNING_DIR'), 'readLiveView('],
  ['次の見本の readLiveViewAligned( を呼び忘れる', CLEAN_PREVIEW.replace(/const runningNext = [^\n]*\n/, ''), 'readLiveViewAligned('],
  ['panelPreviewHtml( に目安を渡さない', CLEAN_PREVIEW.replace('runningNext, STALE_AFTER_SEC', 'runningNext'), 'panelPreviewHtml('],
  ['panelRunsPreviewHtml( に目安を渡さない', CLEAN_PREVIEW.replace('{ staleAfterSec: STALE_AFTER_SEC }', '{}'), 'panelRunsPreviewHtml('],
  ['staleRunsPageHtml( を呼ばない', CLEAN_PREVIEW.replace(/html = await staleRunsPageHtml[^\n]*$/, ''), 'staleRunsPageHtml('],
];
for (const [label, source, word] of BROKEN_PREVIEWS) {
  test(`D0021-AC-41: 検査そのもの：${label} preview.ts の見本の文字は見つける`, () => {
    assert.notEqual(source, CLEAN_PREVIEW, '見本の文字を壊せている');
    assert.ok(previewProblems(source).some((p) => p.includes(word)), previewProblems(source).join(' / '));
  });
}
test('D0021-AC-41: 検査そのもの：きれいな preview.ts の見本の文字は見逃す（コメントの中の readLiveView( や panelPreviewHtml( は数えない）', () => {
  assert.deepEqual(previewProblems(CLEAN_PREVIEW), []);
  assert.deepEqual(previewProblems(`${CLEAN_PREVIEW}\n// readLiveView( は使わない\n/* panelPreviewHtml(x) */\nconst url = "https://example.com/a";`), []);
});
