// 確認用ページの素材のテスト（D0050-AC-46）：scripts/previewPages.ts と scripts/preview.ts と scripts/toolsSamples.ts が作る、エージェント・スキルのタブの見本ページ。
//   run-panel-tools-light・run-panel-tools-dark（実行の一覧つき。実行は 4 つ：(a) 動いている SDK の実行・(b) /pipe-in の記録・(c) --agent を付けなかった /pipe-in の記録・(d) 呼び出しがまだ無い SDK の実行）。
// 画面そのもの（AC-52〜59）は Playwright で見る。ここで確かめるのは、画面で見る前の素材：ページの一覧・見本の木・ページの文字・preview.ts の呼び方・tests/fixtures/ に書かないこと。
// 新しい関数（buildToolsTree・toolsPageHtml）と toolsSamples.ts は、テスト先行のときに「まだ無い」で落ちるようにしたため、動的に読んでから呼ぶ
// （ファイルごと import で落ちて、守る検査まで赤になるのを避けた）。
// 見本の木は一時フォルダ（dest）の中にだけ作る。tests/fixtures/ には足さず・書かない（前後の指紋で確かめる）。
//
// このテストが読む約束（実装の段が満たす。名前や形は下に書いた）：
//   - previewPages.ts：buildToolsTree(dest, 'current' | 'next') → { workspace }（workspace は dest の中）。toolsPageHtml(dest, theme) → ページの文字。
//   - toolsSamples.ts：sdkSample(nowMs, 'current' | 'next') → { expected: { kind, name, count }[], … }。expected は生成した呼び出しを生成する側で数えた表
//     （名前は表に出す名前。読めない名前・指定なしは代わりの文字）。並びは持たなくてよい（このテストが別に並べる）。
//   - (a) の実行は docs/pipeline/tools-sdk/、(b) は docs/pipeline/ の直下、(c) は docs/pipeline/archive/20261016-090000/、(d) は docs/pipeline/tools-fresh/。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { HERE, makeRunKey } from './domain/runs.ts';
import type { ViewClock } from './domain/pipelineView.ts';
import { FIXTURES_DIR, PANEL_PAGES, THEMES, WAITING_DIR, WAITING_SEC, panelKind, previewClock, readRunsView, startOfLiveness } from '../scripts/previewPages.ts';
import type { Theme } from '../scripts/previewPages.ts';
import { bodiesOf, definedVars, dangerousAttributes, fingerprint, pageBodies, pressedRuns, previewNextBody, rootBody, runStub, usedVars } from './test/previewText.ts';
import { needModule } from './test/needModule.ts';
import { callArgs, withoutComments } from './test/sourceText.ts';
import { withTempDir } from './test/tempDir.ts';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const THEME_NAMES: Theme[] = ['light', 'dark'];

// tests/test_rules.py の LOCAL_INFO と同じ4つの書き方（ユーザー名の入ったパス・メールアドレス）
const LOCAL_INFO: RegExp[] = [
  /[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_.-]/,
  /(?<![A-Za-z0-9_.-])\/Users\/[A-Za-z0-9_.-]/,
  /(?<![A-Za-z0-9_.-])\/home\/[A-Za-z0-9_.-]/,
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+/,
];

// 実行の目印（一覧の行の key）
const SDK_KEY = makeRunKey(HERE, 'tools-sdk');
const SKILL_KEY = makeRunKey(HERE, '');
const BARE_KEY = makeRunKey(HERE, 'archive/20261016-090000');
const FRESH_KEY = makeRunKey(HERE, 'tools-fresh');

// ---- 新しい関数・部品を動的に読む ----

type Variant = 'current' | 'next';
type Pages = Record<string, unknown>;
const loadPages = async (): Promise<Pages> => (await import('../scripts/previewPages.ts')) as unknown as Pages;
function need<T extends (...args: never[]) => unknown>(pages: Pages, name: string): T {
  assert.equal(typeof pages[name], 'function', `scripts/previewPages.ts に ${name} が無い（export されていない。まだ作っていない）`);
  return pages[name] as T;
}
const buildToolsTree = async (dest: string, variant: Variant): Promise<{ workspace: string }> =>
  need<(dest: string, variant: Variant) => Promise<{ workspace: string }>>(await loadPages(), 'buildToolsTree')(dest, variant);
const toolsPageHtmlOf = async (dest: string, theme: Theme): Promise<string> =>
  need<(dest: string, theme: Theme) => Promise<string>>(await loadPages(), 'toolsPageHtml')(dest, theme);

interface Expected {
  kind: 'agent' | 'skill' | 'tool';
  name: string;
  count: number;
}
interface SamplesModule {
  sdkSample(nowMs: number, variant: Variant): { expected: Expected[] };
}
const samples = (): Promise<SamplesModule> => needModule<SamplesModule>(import.meta.url, '../scripts/toolsSamples.ts');

/** 見本の「今」（確認待ちの見本の待ち始めから WAITING_SEC 秒後。一覧・成果物の見本の時計と同じ） */
async function previewNow(): Promise<ViewClock> {
  const since = await startOfLiveness(WAITING_DIR);
  assert.ok(since !== null, '確認待ちの見本に待ち始めの時刻がある');
  return previewClock(since, WAITING_SEC);
}

interface Row {
  kind: string;
  name: string;
  count: number;
  stages: string[];
  durationSec: number | null;
}
interface Tools {
  rows: Row[];
  kinds: number;
  total: number;
  omitted: number;
  showTime: boolean;
  notice: 'A' | 'B' | null;
}
interface Entry {
  key: string;
  view: { tools?: Tools | null };
}
const toolsOf = (entry: Entry | undefined, what: string): Tools => {
  assert.ok(entry !== undefined, `${what} の行が一覧にある`);
  assert.ok(entry.view.tools !== undefined && entry.view.tools !== null, `${what} の図の状態に表がある（まだ作っていない）`);
  return entry.view.tools;
};

/** 見本の木を作って読む（木は読み終えたら消す）。 */
async function readTree(variant: Variant): Promise<Entry[]> {
  const clock = await previewNow();
  return withTempDir(async (dest) => {
    const { workspace } = await buildToolsTree(dest, variant);
    assert.ok(workspace === dest || workspace.startsWith(dest + path.sep), '返す作業フォルダは dest の中');
    return (await readRunsView(workspace, clock, { selected: SDK_KEY })) as unknown as Entry[];
  });
}
const treeCache = new Map<Variant, Promise<Entry[]>>();
function tree(variant: Variant): Promise<Entry[]> {
  let found = treeCache.get(variant);
  if (found === undefined) {
    found = readTree(variant);
    treeCache.set(variant, found);
  }
  return found;
}
const entryOf = async (variant: Variant, key: string): Promise<Entry | undefined> => (await tree(variant)).find((e) => e.key === key);

/** ページの文字とそのとき使った一時フォルダの名前（フォルダは作ったあとで消してある）。テーマごとに 1 回だけ作る */
const builtPages = new Map<Theme, Promise<{ html: string; dest: string }>>();
function toolsPage(theme: Theme): Promise<{ html: string; dest: string }> {
  let page = builtPages.get(theme);
  if (page === undefined) {
    page = withTempDir(async (dest) => ({ html: await toolsPageHtmlOf(dest, theme), dest }));
    builtPages.set(theme, page);
  }
  return page;
}

// ======== PANEL_PAGES・panelKind ========

const EXISTING_14: readonly (readonly [string, string])[] = [
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
  ['run-panel-artifacts-light', 'light'],
  ['run-panel-artifacts-dark', 'dark'],
];

test('D0050-AC-46: PANEL_PAGES の先頭 14 件は今のまま（既存 12 件＋成果物の 2 件。名前・順・テーマ。今のまま通る。守る）', () => {
  assert.deepEqual(PANEL_PAGES.slice(0, 14).map(([name, theme]) => [name, theme]), EXISTING_14.map(([name, theme]) => [name, theme]));
});

// D0051 で直した：あとの機能（上限と費用の表のページ）が PANEL_PAGES の末尾にページを足すので、「だけが足される」と slice(14) をやめ、
// 先頭 14 件のすぐあとの 2 件（15・16 件目）を見る形にした。意味（先頭 14 件のあとに tools の 2 件が続く）は変わらない。
test('D0050-AC-46: PANEL_PAGES は先頭 14 件のあと（15・16 件目）に run-panel-tools-light（明るい）・run-panel-tools-dark（暗い）の 2 件が続く（17 件目以降はあとの機能のページが足されてよい）', () => {
  assert.deepEqual(PANEL_PAGES.slice(14, 16).map(([name, theme]) => [name, theme]), [
    ['run-panel-tools-light', 'light'],
    ['run-panel-tools-dark', 'dark'],
  ]);
});

test('D0050-AC-46: panelKind は run-panel-tools-light・run-panel-tools-dark に tools を返す', () => {
  assert.equal(panelKind('run-panel-tools-light'), 'tools');
  assert.equal(panelKind('run-panel-tools-dark'), 'tools');
});

test('D0050-AC-46: 既存の 14 ページの種類は変わらない（今のまま通る。守る）', () => {
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
    'run-panel-artifacts-light': 'artifacts',
    'run-panel-artifacts-dark': 'artifacts',
  };
  assert.deepEqual(Object.fromEntries(Object.keys(expected).map((name) => [name, panelKind(name)])), expected);
});

// ======== 見本の木：4 つの実行 ========

test('D0050-AC-46: 見本の木は 4 つの実行を持つ：(a) tools-sdk・(b) 直下の /pipe-in の記録・(c) archive/ の --agent なしの /pipe-in の記録・(d) tools-fresh', async () => {
  const entries = await tree('current');
  assert.deepEqual(entries.map((e) => e.key).sort(), [SDK_KEY, SKILL_KEY, BARE_KEY, FRESH_KEY].sort());
});

const sdkTools = async (): Promise<Tools> => toolsOf(await entryOf('current', SDK_KEY), '(a)');

test('D0050-AC-46: (a) 動いている SDK の実行：表の行は 100（上限）で、100 を超える種類があって省略の文が出る', async () => {
  const t = await sdkTools();
  assert.equal(t.rows.length, 100, '行は上限の 100');
  assert.ok(t.kinds > 100 && t.omitted === t.kinds - 100 && t.omitted > 0, `100 を超える種類があり、省略がある（種類 ${t.kinds}・省略 ${t.omitted}）`);
});

test('D0050-AC-46: (a) 空白のない 100 文字の名前の行が、先頭 100 行の中にある', async () => {
  const t = await sdkTools();
  assert.ok(t.rows.some((r) => Array.from(r.name).length === 100 && !/\s/.test(r.name)), '空白のない 100 文字の名前の行がある');
});

test('D0050-AC-46: (a) 外から来た文字（<script>・"・& を含む名前）の行が、先頭 100 行の中にある（AC-53 の画面で見る文字）', async () => {
  const t = await sdkTools();
  assert.ok(t.rows.some((r) => r.name.includes('<script>')), '<script> を含む名前の行がある');
  assert.ok(t.rows.some((r) => r.name.includes('"')), '" を含む名前の行がある');
  assert.ok(t.rows.some((r) => r.name.includes('&')), '& を含む名前の行がある');
});

test('D0050-AC-46: (a) 3 つの種類（エージェント・スキル・道具）がそろい、MCP の道具（mcp__…）と Bash の行が先頭 100 行の中にある', async () => {
  const t = await sdkTools();
  assert.deepEqual([...new Set(t.rows.map((r) => r.kind))].sort(), ['agent', 'skill', 'tool'], '3 つの種類がそろう');
  assert.ok(t.rows.some((r) => r.kind === 'tool' && r.name.startsWith('mcp__')), 'MCP の道具（mcp__…）の行がある');
  assert.ok(t.rows.some((r) => r.kind === 'tool' && r.name === 'Bash'), 'Bash の行がある');
});

test('D0050-AC-46: (a) 使った段が 3 つを超える行がある（Read は 6 つの実行で使う）', async () => {
  const t = await sdkTools();
  assert.ok(t.rows.some((r) => r.stages.length > 3), '使った段が 3 つを超える行がある');
  assert.equal(t.rows.find((r) => r.kind === 'tool' && r.name === 'Read')?.stages.length, 6, 'Read は 6 つの実行で使う');
});

test('D0050-AC-46: (a) 時間の列は無く（agent を入れない）、案内も無い（driver を入れない）', async () => {
  const t = await sdkTools();
  assert.equal(t.showTime, false, '時間の列は無い（agent を入れない）');
  assert.equal(t.notice, null, 'driver を入れないので案内は無い');
});

test('D0050-AC-46: (a) のエージェントの行に、鍵の無い呼び出し（指定なし）・空白を含む名前（読めない名前）・module-reader・source-checker がある', async () => {
  const t = toolsOf(await entryOf('current', SDK_KEY), '(a)');
  const agents = t.rows.filter((r) => r.kind === 'agent').map((r) => r.name);
  for (const name of ['module-reader', 'source-checker', '（指定なし）', '（読めない名前）']) assert.ok(agents.includes(name), `エージェント ${name}：${agents.join(' | ')}`);
  assert.ok(t.rows.filter((r) => r.kind === 'skill').length >= 2, 'スキルの行が 2 つ以上');
});

/** 種類（エージェント → スキル → 道具）、回数の多い順、名前のコードポイントの順。表を作る側とは別に並べる */
function sortExpected(rows: readonly Expected[]): Expected[] {
  const order = { agent: 0, skill: 1, tool: 2 } as const;
  const byCodePoint = (a: string, b: string): number => {
    const x = Array.from(a, (c) => c.codePointAt(0)!);
    const y = Array.from(b, (c) => c.codePointAt(0)!);
    for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) return x[i]! - y[i]!;
    return x.length - y.length;
  };
  return [...rows].sort((a, b) => order[a.kind] - order[b.kind] || b.count - a.count || byCodePoint(a.name, b.name));
}

for (const variant of ['current', 'next'] as const) {
  test(`D0050-AC-46: (a) の表（${variant}）は、見本を生成する側で数えた expected（種類・名前・回数）と一致する（先頭 100 行。種類の数と回数の合計も）`, async () => {
    const { sdkSample } = await samples();
    const now = (await previewNow()).nowMs;
    const expected = sortExpected(sdkSample(now, variant).expected);
    const t = toolsOf(await entryOf(variant, SDK_KEY), '(a)');
    assert.ok(expected.length > 100, `expected は 100 種類を超える（${expected.length}）`);
    assert.equal(t.kinds, expected.length);
    assert.equal(t.total, expected.reduce((sum, r) => sum + r.count, 0));
    assert.deepEqual(
      t.rows.map((r) => ({ kind: r.kind, name: r.name, count: r.count })),
      expected.slice(0, 100),
    );
  });
}

test('D0050-AC-46: toolsSamples.ts の sdkSample は純粋：同じ引数からは同じ結果で、Date.now を投げる関数に替えても動く（時計を読まない。「今」は引数）', async () => {
  const { sdkSample } = await samples();
  const now = (await previewNow()).nowMs;
  const a = sdkSample(now, 'current');
  assert.deepEqual(sdkSample(now, 'current'), a);
  const real = Date.now;
  const made: { value?: ReturnType<SamplesModule['sdkSample']> } = {};
  try {
    Date.now = () => {
      throw new Error('見本を作る関数が時計を読んだ');
    };
    made.value = sdkSample(now, 'current');
  } finally {
    Date.now = real;
  }
  assert.deepEqual(made.value, a);
});

test('D0050-AC-46: (a) の next は更新後の本体：Grep が 15 回増えて Read を抜き、module-reader が 2 回増え、新しい道具が 1 種増える', async () => {
  const current = toolsOf(await entryOf('current', SDK_KEY), '(a) current');
  const next = toolsOf(await entryOf('next', SDK_KEY), '(a) next');
  const count = (t: Tools, name: string): number => t.rows.find((r) => r.kind === 'tool' && r.name === name)?.count ?? 0;
  assert.ok(count(current, 'Read') > count(current, 'Grep'), '今は Read が Grep より多い');
  assert.equal(count(next, 'Grep'), count(current, 'Grep') + 15);
  assert.ok(count(next, 'Grep') > count(next, 'Read'), '更新後は Grep が Read を抜く');
  assert.equal(count(next, 'Read'), count(current, 'Read'), 'Read の回数は増えない');
  const agent = (t: Tools): number => t.rows.find((r) => r.kind === 'agent' && r.name === 'module-reader')?.count ?? 0;
  assert.equal(agent(next), agent(current) + 2);
  assert.equal(next.kinds, current.kinds + 1, '新しい道具が 1 種');
  assert.ok(next.total - current.total >= 15 + 2 + 1, `回数の合計は Grep 15・module-reader 2・新しい道具 1 以上増える（${current.total} → ${next.total}）`);
});

test('D0050-AC-46: (b) /pipe-in の記録（driver あり）：案内 A・受け持ち pipe-in-analyst（3 実行）と pipe-in-tester（1 実行）の行・時間の列が出る（時間は runs[].duration_sec の合計）', async () => {
  const t = toolsOf(await entryOf('current', SKILL_KEY), '(b)');
  assert.equal(t.notice, 'A');
  assert.equal(t.showTime, true);
  const analyst = t.rows.find((r) => r.kind === 'agent' && r.name === 'pipe-in-analyst');
  const tester = t.rows.find((r) => r.kind === 'agent' && r.name === 'pipe-in-tester');
  assert.ok(analyst !== undefined && tester !== undefined, '受け持ちの行がある');
  assert.equal(analyst.count, 3);
  assert.ok(analyst.durationSec !== null && Math.abs(analyst.durationSec - (95.0 + 41.2 + 120.4)) < 1e-6, `pipe-in-analyst の時間（${analyst.durationSec}）`);
  assert.equal(tester.count, 1);
  assert.equal(tester.durationSec, 75);
  assert.equal(analyst.stages.length, 3, '使った段は 3 つ（要件定義・要件定義 2 回目・設計の通し番号 3 つ）');
});

test('D0050-AC-46: (c) --agent を付けなかった /pipe-in の記録（driver あり・受け持ち無し）：案内 B だけ（行 0）。前の実行（archive/）として一覧に出る', async () => {
  const entry = await entryOf('current', BARE_KEY);
  const t = toolsOf(entry, '(c)');
  assert.equal(t.notice, 'B');
  assert.deepEqual(t.rows, []);
});

test('D0050-AC-46: (d) 呼び出しがまだ無い SDK の実行（driver なし・ログは Prompt だけ）：行 0・案内なし（空の文）。動いている実行', async () => {
  const t = toolsOf(await entryOf('current', FRESH_KEY), '(d)');
  assert.equal(t.notice, null);
  assert.deepEqual(t.rows, []);
  const logs = await withTempDir(async (dest) => {
    const { workspace } = await buildToolsTree(dest, 'current');
    const dir = path.join(workspace, 'docs', 'pipeline', 'tools-fresh', 'logs');
    return Promise.all((await readdir(dir)).map(async (name) => [name, await readFile(path.join(dir, name), 'utf8')] as const));
  });
  assert.equal(logs.length, 1, 'ログは 1 つ');
  const lines = logs[0]![1].split('\n').filter((l) => l.trim() !== '');
  assert.equal(lines.length, 1, 'Prompt の行だけ');
  assert.equal((JSON.parse(lines[0]!) as { _type: string })._type, 'Prompt');
});

/** (a) の木のログ（ファイル名 → 中身）と state.json。木は読み終えたら消す（1 回だけ作る） */
interface SdkFiles {
  texts: Map<string, string>;
  state: Record<string, unknown>;
}
let sdkFiles: Promise<SdkFiles> | undefined;
function readSdkFiles(): Promise<SdkFiles> {
  sdkFiles ??= withTempDir(async (dest) => {
    const { workspace } = await buildToolsTree(dest, 'current');
    const dir = path.join(workspace, 'docs', 'pipeline', 'tools-sdk');
    const names = (await readdir(path.join(dir, 'logs'))).sort();
    const texts = new Map(await Promise.all(names.map(async (n) => [n, await readFile(path.join(dir, 'logs', n), 'utf8')] as const)));
    const state = JSON.parse(await readFile(path.join(dir, 'state.json'), 'utf8')) as Record<string, unknown>;
    return { texts, state };
  });
  return sdkFiles;
}
const allLogText = async (): Promise<string> => [...(await readSdkFiles()).texts.values()].join('\n');

test('D0050-AC-46: (a) のログは 6 つ：01_survey・02_draw_1・03_verify_1・04_draw_2・05_verify_2・06_rubric', async () => {
  assert.deepEqual([...(await readSdkFiles()).texts.keys()], ['01_survey.jsonl', '02_draw_1.jsonl', '03_verify_1.jsonl', '04_draw_2.jsonl', '05_verify_2.jsonl', '06_rubric.jsonl']);
});

test('D0050-AC-46: (a) のログのうち、終わっている（結果の行がある）のは 06_rubric 以外で、06_rubric が動いている', async () => {
  for (const [name, text] of (await readSdkFiles()).texts) {
    assert.equal(text.includes('"ResultMessage"'), name !== '06_rubric.jsonl', `${name}：終わっているのは 06_rubric 以外`);
  }
});

test('D0050-AC-46: (a) のログに、サブエージェントの中の発言（parent_tool_use_id）・Task（旧名）と Agent の呼び出しがある', async () => {
  const all = await allLogText();
  assert.match(all, /"parent_tool_use_id":\s*"[^"]+"/, 'サブエージェントの中の発言がある');
  assert.match(all, /"name":\s*"Task"/, 'Task（旧名）の呼び出しがある');
  assert.match(all, /"name":\s*"Agent"/);
});

test('D0050-AC-46: (a) のログに、文章の部品と考え中の部品がある', async () => {
  const all = await allLogText();
  assert.match(all, /"thinking"/, '考え中の部品がある');
  assert.match(all, /"text"/, '文章の部品がある');
});

test('D0050-AC-46: (a) の state.json はパイプ tools-sdk で、段は survey・draw・verify・rubric。driver を入れない', async () => {
  const { state } = await readSdkFiles();
  assert.equal(state.pipe, 'tools-sdk');
  assert.equal('driver' in state, false, 'state.json に driver を入れない');
  assert.deepEqual((state.stages as { name: string }[]).map((s) => s.name), ['survey', 'draw', 'verify', 'rubric']);
});

test('D0050-AC-46: (a) の段のログにも state.json にも agent を入れない（時間の列を出さない）', async () => {
  const { state } = await readSdkFiles();
  assert.ok(!/"agent"/.test(await allLogText()) && !/"agent"/.test(JSON.stringify(state)), '段のログにも state.json にも agent を入れない');
});

// ======== 見本の木・ページを作っても、tests/fixtures/ は変わらない ========

test('D0050-AC-46: 見本の木・ページを作っても（4 つの実行・current/next・明るい/暗い）、tests/fixtures/ の全体の内容と更新時刻は変わらない', async () => {
  const before = await fingerprint(FIXTURES_DIR);
  assert.ok(before.length > 0, 'tests/fixtures/ の指紋が取れている（検査が空振りでない）');
  await withTempDir(async (dest) => void (await buildToolsTree(dest, 'current')));
  await withTempDir(async (dest) => void (await buildToolsTree(dest, 'next')));
  await withTempDir(async (dest) => void (await toolsPageHtmlOf(dest, 'light')));
  await withTempDir(async (dest) => void (await toolsPageHtmlOf(dest, 'dark')));
  assert.deepEqual(await fingerprint(FIXTURES_DIR), before);
});

// ======== ページの文字 ========

test('D0050-AC-46: ページは実行の一覧つきで、実行は 4 つ（行の key は (a)〜(d)）。初めに見ているのは (a)。初めの本体は (a) の行の本体', async () => {
  const { html } = await toolsPage('dark');
  const bodies = bodiesOf(html);
  assert.deepEqual(Object.keys(bodies).sort(), [SDK_KEY, SKILL_KEY, BARE_KEY, FRESH_KEY].sort());
  assert.deepEqual(pressedRuns(html), [SDK_KEY], '初めに見るのは (a)');
  assert.equal(rootBody(html), bodies[SDK_KEY]);
});

test('D0050-AC-46: 本体の「エージェント・スキル」のパネルに、(a) は表（枠 data-scroll="tools-table"）、(b) は案内 A と表、(c) は案内 B、(d) は空の文が出る', async () => {
  const { html } = await toolsPage('light');
  const bodies = bodiesOf(html);
  const toolsPanel = (body: string): string => {
    const at = body.indexOf('data-detail-panel="tools"');
    assert.ok(at >= 0, 'tools のパネルがある（まだ作っていない）');
    const end = body.indexOf('data-detail-panel="usage"', at);
    return body.slice(at, end < 0 ? undefined : end);
  };
  assert.match(toolsPanel(bodies[SDK_KEY]!), /data-scroll="tools-table"/);
  assert.match(toolsPanel(bodies[SDK_KEY]!), /ほか \d+ 種類を省いています/);
  assert.match(toolsPanel(bodies[SKILL_KEY]!), /tools-notice/);
  assert.match(toolsPanel(bodies[SKILL_KEY]!), /pipe-in-analyst/);
  assert.match(toolsPanel(bodies[BARE_KEY]!), /段の受け持ち（record begin --agent）も記録に無いので/);
  assert.doesNotMatch(toolsPanel(bodies[BARE_KEY]!), /<table/);
  assert.match(toolsPanel(bodies[FRESH_KEY]!), /エージェント・スキル・道具の呼び出しは、まだ記録にありません。/);
});

test('D0050-AC-46: window.__previewNext は (a) の更新後の本体を送り、window.__posted にメッセージの種類が貯まる。更新後の本体の Grep の回数は今より多い', async () => {
  const { html } = await toolsPage('dark');
  assert.match(html, /<script nonce="preview">window\.__previewNext=/);
  const { win } = runStub(html);
  assert.ok(Array.isArray(win.__posted), 'window.__posted は配列で始まる');
  const now = rootBody(html);
  const next = previewNextBody(html);
  assert.notEqual(next, now);
  assert.equal(pressedRuns(next).join(), SDK_KEY, '更新後の本体も (a) を見ている');
  const grep = (body: string): number => Number(/<td class="tools-name">Grep<\/td>\s*<td class="tools-kind">道具<\/td>\s*<td class="tools-count">(\d+)<\/td>/.exec(body)?.[1] ?? -1);
  assert.ok(grep(now) >= 0 && grep(next) === grep(now) + 15, `Grep の回数が 15 増える（${grep(now)} → ${grep(next)}）`);
});

test('D0050-AC-46: ページの script と style のタグはすべて nonce="preview" を持ち、style 属性を使わない。CSP をそのまま持ち、使う --vscode-* の色をすべて THEMES が決めている', async () => {
  for (const theme of THEME_NAMES) {
    const { html } = await toolsPage(theme);
    const tags = [...html.matchAll(/<(script|style)\b[^>]*>/g)].map((m) => m[0]);
    assert.ok(tags.length >= 4, `${theme}: 本物の style・script と、テーマの色・置き換え・__previewNext（${tags.length} 個）`);
    assert.deepEqual(tags.filter((t) => !t.includes('nonce="preview"')), [], theme);
    assert.doesNotMatch(html, /\sstyle="/, `${theme}: style 属性を使わない（CSP に捨てられる）`);
    assert.match(html, /<meta http-equiv="Content-Security-Policy"[^>]*>/);
    const defined = definedVars(THEMES[theme]);
    assert.deepEqual(usedVars(html).filter((name) => !defined.has(name)), [], `${theme}: THEMES に無い色`);
    assert.ok(html.includes(THEMES[theme]), `${theme}: テーマの色がページに入っている`);
  }
});

test('D0050-AC-46: ページに入っている本体すべて（初めの本体・行ごとの本体・次の本体）に、タグの属性として style・on…・src・href が無い。外から来た文字は文字のまま（生の <script> を作らない）', async () => {
  const { html } = await toolsPage('dark');
  const bodies = [rootBody(html), ...pageBodies(html)];
  assert.equal(bodies.length, 6, '初めの本体 + 行ごとの本体 4 + 次の本体');
  for (const body of bodies) {
    assert.deepEqual(dangerousAttributes(body), []);
    assert.ok(body.includes('data-detail-panel="tools"'), 'tools のパネルがある（まだ作っていない）');
  }
  assert.ok(!bodiesOf(html)[SDK_KEY]!.includes('<script>alert'), '生の <script> が入っていない');
  assert.ok(bodiesOf(html)[SDK_KEY]!.includes('&lt;script&gt;'), 'エスケープされた形で出ている');
});

test('D0050-AC-46: 明るいページと暗いページは、テーマの色の <style> 以外が同じ。同じ見本から 2 回作ると、ページの文字が同じ', async () => {
  const strip = (html: string, theme: Theme): string => html.replace(`:root{${THEMES[theme]}}`, '');
  assert.equal(strip((await toolsPage('light')).html, 'light'), strip((await toolsPage('dark')).html, 'dark'));
  const again = await withTempDir((dest) => toolsPageHtmlOf(dest, 'dark'));
  assert.equal(again, (await toolsPage('dark')).html, '一時フォルダの名前・時刻に左右されない');
});

test('D0050-AC-46: ページに手元の情報（ユーザー名の入ったパス・メールアドレス）や、一時フォルダ・リポジトリの絶対パスが出ていない', async () => {
  for (const theme of THEME_NAMES) {
    const { html, dest } = await toolsPage(theme);
    assert.deepEqual(LOCAL_INFO.filter((re) => re.test(html)).map(String), [], theme);
    assert.ok(!html.includes(dest), `${theme}: 一時フォルダの絶対パスが出ていない`);
    assert.ok(!html.includes(REPO), `${theme}: リポジトリの絶対パスが出ていない`);
  }
});

// ======== preview.ts の呼び方を文字で守る（D0025-AC-73 と同じ形） ========

/** preview.ts の文字の問題（エージェント・スキルのページを作らない・一時フォルダの外で作る・種類の分かれが無い）。無ければ空。 */
function toolsWiringProblems(source: string): string[] {
  const code = withoutComments(source);
  const problems: string[] = [];
  if (callArgs(code, 'toolsPageHtml').length === 0) problems.push('toolsPageHtml( を呼んでいない');
  if (!/kind\s*===\s*['"]tools['"]/.test(code)) problems.push("kind === 'tools' の分かれが無い");
  if (!callArgs(code, 'inTempDir').some((args) => args.includes('toolsPageHtml('))) problems.push('toolsPageHtml( を inTempDir( の中で呼んでいない（見本の木は一時フォルダに作る）');
  return problems;
}

test('D0050-AC-46: scripts/preview.ts は kind === tools で、toolsPageHtml( を inTempDir( の中で呼ぶ', () => {
  assert.deepEqual(toolsWiringProblems(readFileSync(path.join(REPO, 'vscode', 'scripts', 'preview.ts'), 'utf8')), []);
});

const CLEAN_WIRING = [
  'for (const [page, theme] of PANEL_PAGES) {',
  '  const kind = panelKind(page);',
  "  if (kind === 'tools') {",
  "    writeFileSync(path.join(OUT, `${page}.html`), await inTempDir('tools', (dest) => toolsPageHtml(dest, theme)), 'utf8');",
  '    continue;',
  '  }',
  '}',
].join('\n');

const BROKEN_WIRINGS: readonly (readonly [string, string, string])[] = [
  ['エージェント・スキルのページを作らない', CLEAN_WIRING.replace(/await inTempDir\([^\n]*\), 'utf8'\);/, "'', 'utf8');"), 'toolsPageHtml( を呼んでいない'],
  ['種類の分かれを書かない', CLEAN_WIRING.replace("kind === 'tools'", "kind === 'stale'"), "kind === 'tools' の分かれが無い"],
  ['一時フォルダの外で作る', CLEAN_WIRING.replace("await inTempDir('tools', (dest) => toolsPageHtml(dest, theme))", 'await toolsPageHtml(OUT, theme)'), 'inTempDir( の中で呼んでいない'],
];
for (const [label, source, word] of BROKEN_WIRINGS) {
  test(`D0050-AC-46: 検査そのもの：${label} preview.ts の見本の文字は見つける（今のまま通る。守る）`, () => {
    assert.notEqual(source, CLEAN_WIRING, '見本の文字を壊せている');
    assert.ok(toolsWiringProblems(source).some((p) => p.includes(word)), toolsWiringProblems(source).join(' / '));
  });
}
test('D0050-AC-46: 検査そのもの：きれいな preview.ts の見本の文字は見逃す（コメントの中の toolsPageHtml( は数えない）（今のまま通る。守る）', () => {
  assert.deepEqual(toolsWiringProblems(CLEAN_WIRING), []);
  const commentOnly = CLEAN_WIRING.replace(/await inTempDir\([^\n]*\), 'utf8'\);/, "'', 'utf8');").replace('continue;', "continue;\n  // toolsPageHtml(dest, theme) は後で呼ぶ\n  /* inTempDir(toolsPageHtml(x)) */");
  assert.ok(toolsWiringProblems(commentOnly).includes('toolsPageHtml( を呼んでいない'), 'コメントの中の呼び出しは数えない');
});
