// 確認用ページの素材のテスト（D0090・AC-01〜05 の見本の行）：scripts/previewPages.ts と scripts/devSamples.ts が作る、開発用の新しい記録の見本ページ。
//   run-panel-dev-light・run-panel-dev-dark（schema: 1・費用と使用量が取れない・段が 1 秒ほどで終わる短い記録・テスト先行の確認待ちで止まる）。
// 画面そのもの（AC-05・12・13）は Playwright で見る。ここで確かめるのは、画面で見る前の素材：ページの一覧・種類の判定・見本の記録の形・
// 共通の表（tests/fixtures/state_record.json）との突き合わせ・本物の読み取りで読んだ時系列・描くと下の行に出ること・tests/fixtures/ に書かないこと。
//
// まだ無いもの（buildDevDir・devPageHtml・PANEL_PAGES の 2 行・panelKind の dev）は、ファイルごと読み込めなくならないように、
// 名前空間の import（import * as pages）から関数を取り出す形で書く（無ければ「まだ作っていない」で、そのテストだけ落ちる）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as pages from '../scripts/previewPages.ts';
import { FIXTURES_DIR, PANEL_PAGES, panelKind, readShowcaseView } from '../scripts/previewPages.ts';
import { devLogs, devStateJson } from '../scripts/devSamples.ts';
import { fingerprint } from './test/previewText.ts';
import { loadStateTable } from './test/stateRecordFixtures.ts';
import { needFunction } from './test/needModule.ts';
import { withTempDir } from './test/tempDir.ts';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCRIPTS = path.resolve(HERE, '..', 'scripts');

type BuildDevDir = (dest: string) => Promise<string>;
type DevPageHtml = (dest: string, theme: 'light' | 'dark') => Promise<string>;
const buildDevDir = (): BuildDevDir => needFunction<BuildDevDir>(pages, 'buildDevDir', 'scripts/previewPages.ts');
const devPageHtml = (): DevPageHtml => needFunction<DevPageHtml>(pages, 'devPageHtml', 'scripts/previewPages.ts');

/** 今の確認用ページの先頭 32 件（run-panel-light から run-panel-chat-dark まで）。順・テーマとも今のまま。 */
const BASE_PAGES: [string, string][] = [
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
  ['run-panel-tools-light', 'light'],
  ['run-panel-tools-dark', 'dark'],
  ['run-panel-budget-light', 'light'],
  ['run-panel-budget-dark', 'dark'],
  ['run-panel-check-self-light', 'light'],
  ['run-panel-check-self-dark', 'dark'],
  ['run-panel-check-back-light', 'light'],
  ['run-panel-check-back-dark', 'dark'],
  ['run-panel-check-old-light', 'light'],
  ['run-panel-check-old-dark', 'dark'],
  ['run-panel-group-running-light', 'light'],
  ['run-panel-group-running-dark', 'dark'],
  ['run-panel-group-failed-light', 'light'],
  ['run-panel-group-failed-dark', 'dark'],
  ['run-panel-group-old-light', 'light'],
  ['run-panel-group-old-dark', 'dark'],
  ['run-panel-chat-light', 'light'],
  ['run-panel-chat-dark', 'dark'],
];

// ---- ページの一覧・種類（AC-01・02） ----

test('D0090-AC-01: PANEL_PAGES に run-panel-dev-light（明るい）・run-panel-dev-dark（暗い）の 2 件が、chat-dark の次・reply-runs-light の前にある', () => {
  const names = PANEL_PAGES.map(([name]) => name);
  const at = names.indexOf('run-panel-dev-light');
  assert.ok(at >= 0, 'run-panel-dev-light がある');
  assert.deepEqual(
    PANEL_PAGES.slice(at, at + 2).map(([name, theme]) => [name, theme]),
    [
      ['run-panel-dev-light', 'light'],
      ['run-panel-dev-dark', 'dark'],
    ],
  );
  assert.equal(names[at - 1], 'run-panel-chat-dark');
  assert.equal(names[at + 2], 'run-panel-reply-runs-light');
  assert.equal(names.filter((n) => n.includes('-dev-')).length, 2, '-dev- を含む名前はこの 2 件だけ');
});

test('D0090-AC-01: panelKind は run-panel-dev-light・run-panel-dev-dark に dev を返す', () => {
  assert.equal(panelKind('run-panel-dev-light'), 'dev');
  assert.equal(panelKind('run-panel-dev-dark'), 'dev');
});

test('D0090-AC-01: scripts/preview.ts に kind === \'dev\' の枝があり、devPageHtml で書く（out/preview/ に 2 つのページができる）', async () => {
  const text = await readFile(path.join(SCRIPTS, 'preview.ts'), 'utf8');
  assert.match(text, /kind === 'dev'/);
  assert.match(text, /devPageHtml\(/);
});

test('D0090-AC-02: 既存のページ名の種類は今のまま（-dev- を含む名前だけが dev になる）。今のまま通る。守る', () => {
  const expected: Record<string, string> = {
    'run-panel-light': 'done',
    'run-panel-running-dark': 'running',
    'run-panel-waiting-dark': 'waiting',
    'run-panel-runs-light': 'runs',
    'run-panel-runs-omitted-dark': 'runs-omitted',
    'run-panel-stale-dark': 'stale',
    'run-panel-stale-soon-dark': 'stale-soon',
    'run-panel-artifacts-dark': 'artifacts',
    'run-panel-tools-dark': 'tools',
    'run-panel-budget-dark': 'budget',
    'run-panel-check-self-light': 'check',
    'run-panel-group-old-dark': 'group',
    'run-panel-chat-dark': 'chat',
    'run-panel-reply-runs-light': 'reply',
  };
  assert.deepEqual(Object.fromEntries(Object.keys(expected).map((name) => [name, panelKind(name)])), expected);
});

test('D0090-AC-02: 先頭 32 件（run-panel-light から run-panel-chat-dark まで）の名前・順・テーマは今のまま。名前の重複が無い。今のまま通る。守る', () => {
  assert.deepEqual(
    PANEL_PAGES.slice(0, BASE_PAGES.length).map(([name, theme]) => [name, theme]),
    BASE_PAGES,
  );
  const names = PANEL_PAGES.map(([name]) => name);
  assert.equal(new Set(names).size, names.length, '名前の重複が無い');
});

// ---- 見本の記録の形（AC-03） ----

test('D0090-AC-03: buildDevDir(dest) は dest の中の docs/pipeline に state.json・logs/01_requirements.jsonl・02_design.jsonl・03_red.jsonl・00_input.md を書く', async () => {
  const build = buildDevDir();
  await withTempDir(async (dest) => {
    const dir = await build(dest);
    assert.equal(dir, path.join(dest, 'docs', 'pipeline'));
    for (const rel of ['state.json', 'logs/01_requirements.jsonl', 'logs/02_design.jsonl', 'logs/03_red.jsonl', '00_input.md']) {
      const text = await readFile(path.join(dir, ...rel.split('/')), 'utf8');
      assert.ok(text.length > 0, `${rel} が空でない`);
    }
  });
});

test('D0090-AC-03: buildDevDir は tests/fixtures/ に何も書かない（前後の指紋が同じ）', async () => {
  const build = buildDevDir();
  const before = await fingerprint(FIXTURES_DIR);
  await withTempDir(async (dest) => {
    await build(dest);
  });
  assert.deepEqual(await fingerprint(FIXTURES_DIR), before);
});

test('D0090-AC-03: 見本の state.json：schema 1・driver pipe-dev・費用 null・使用量は取れない（available false と理由）・各段の cost_usd は null・metrics は持たない', () => {
  const state = JSON.parse(devStateJson()) as Record<string, any>;
  assert.equal(state.schema, 1);
  assert.equal(state.driver, 'pipe-dev');
  assert.equal(state.total_cost_usd, null);
  assert.equal(state.usage_summary?.available, false);
  assert.equal(typeof state.usage_summary?.reason, 'string');
  assert.ok(state.usage_summary.reason.length > 0, '理由が空でない');
  assert.equal(state.runs.length, 3);
  for (const run of state.runs) {
    assert.equal(run.cost_usd, null);
    assert.ok(!('metrics' in run), 'metrics を持たない');
  }
});

test('D0090-AC-03: 見本の state.json：5 段（要件定義・設計・テスト先行・実装・検証。実装と検証は確認なし）・pending_review.stage は red・runs の duration_sec は 0.3・0.6・1.0', () => {
  const state = JSON.parse(devStateJson()) as Record<string, any>;
  assert.deepEqual(
    state.stages.map((s: any) => [s.name, s.label, s.review]),
    [
      ['requirements', '要件定義', true],
      ['design', '設計', true],
      ['red', 'テスト先行', true],
      ['implement', '実装', false],
      ['test', '検証', false],
    ],
  );
  assert.equal(state.pending_review?.stage, 'red');
  assert.deepEqual(
    state.runs.map((r: any) => r.duration_sec),
    [0.3, 0.6, 1.0],
  );
  assert.deepEqual(
    state.runs.map((r: any) => r.stage),
    ['requirements', 'design', 'red'],
  );
});

test('D0090-AC-03: 見本の時刻はすべて時差なし（タイムゾーンに左右されない）で、started_at は 11:40:42・pending_review.since は 11:40:43', () => {
  const state = JSON.parse(devStateJson()) as Record<string, any>;
  assert.match(state.started_at, /^\d{4}-\d\d-\d\dT11:40:42$/);
  assert.match(state.pending_review.since, /^\d{4}-\d\d-\d\dT11:40:43$/);
  for (const log of devLogs()) assert.match(log.text, /"at":"\d{4}-\d\d-\d\dT11:40:42"/, `${log.fileName} の Prompt の at`);
});

test('D0090-AC-03: 見本のログは 3 つ（01_requirements・02_design・03_red）で、どれにも _type が Prompt の行（stage と at つき）がある', () => {
  const logs = devLogs();
  assert.deepEqual(
    logs.map((l) => l.fileName),
    ['01_requirements.jsonl', '02_design.jsonl', '03_red.jsonl'],
  );
  for (const log of logs) {
    const prompt = log.text
      .split('\n')
      .filter((line) => line.trim() !== '')
      .map((line) => JSON.parse(line) as Record<string, unknown>)
      .find((row) => row._type === 'Prompt');
    assert.ok(prompt, `${log.fileName} に Prompt の行がある`);
    assert.equal(typeof prompt.at, 'string');
    assert.equal(typeof prompt.stage, 'string');
  }
});

test('D0090-AC-03: 見本の鍵は共通の表（tests/fixtures/state_record.json）の dev の行と合う：鍵の並び（任意の鍵を除く）・driver・schema・値の種類', () => {
  const table = loadStateTable();
  const row = table.kinds.dev;
  const state = JSON.parse(devStateJson()) as Record<string, unknown>;
  assert.deepEqual(
    Object.keys(state).filter((k) => !row.optional_keys.includes(k)),
    row.keys,
  );
  for (const key of Object.keys(state)) assert.ok(row.keys.includes(key) || row.optional_keys.includes(key), `表に無い鍵 ${key}`);
  assert.equal(state.driver, row.driver);
  assert.equal(state.schema, table.schema);
  assert.equal(row.total_cost_usd, 'null');
  assert.equal(row.usage_summary, 'unavailable');
  assert.equal(row.run_cost_usd, 'null');
  assert.equal(row.run_metrics, 'absent');
});

// ---- 再現（AC-04）----

test('D0090-AC-04: 見本の記録を本物の読み取り（readShowcaseView。時計なし）で読むと、時系列は 3 行・全体 1.0 秒で、時刻が読める', async () => {
  const build = buildDevDir();
  await withTempDir(async (dest) => {
    const view = await readShowcaseView(await build(dest));
    assert.equal(view.gantt.hasTimes, true);
    assert.equal(view.gantt.rows.length, 3);
    assert.equal(view.gantt.totalSec, 1.0);
  });
});

test('D0090-AC-04: 3 行目（テスト先行）の wait は、長さ 0 の live の帯（startSec ＝ endSec ＝ 1.0）。1・2 行目に wait は無い', async () => {
  const build = buildDevDir();
  await withTempDir(async (dest) => {
    const rows = (await readShowcaseView(await build(dest))).gantt.rows;
    assert.equal(rows[0]!.wait, null);
    assert.equal(rows[1]!.wait, null);
    const wait = rows[2]!.wait;
    assert.ok(wait, '3 行目に待ちの帯がある');
    assert.equal(wait.live, true);
    assert.equal(wait.startSec, 1.0);
    assert.equal(wait.endSec, 1.0);
  });
});

test('D0090-AC-04: 3 行の実行の帯は、どれも 0 秒から始まり、長さは 0.3・0.6・1.0 秒（3 段のログの Prompt の at が同じ秒）', async () => {
  const build = buildDevDir();
  await withTempDir(async (dest) => {
    const rows = (await readShowcaseView(await build(dest))).gantt.rows;
    assert.deepEqual(
      rows.map((r) => [r.run?.startSec, r.run?.endSec]),
      [
        [0, 0.3],
        [0, 0.6],
        [0, 1.0],
      ],
    );
  });
});

// ---- ページ（AC-05 の素材・再現の描画） ----

test('D0090-AC-04: devPageHtml で見本を描くと、確認待ちの字が青い帯の上に乗らず下の行に出る（data-side="below"・行は has-below）。明るい・暗いの両方', async () => {
  const html = devPageHtml();
  await withTempDir(async (dest) => {
    for (const theme of ['light', 'dark'] as const) {
      const out = await html(dest, theme);
      assert.match(out, /<div class="g-row has-below"/, `${theme}: has-below の行`);
      assert.match(out, /data-side="below">確認待ち 0:00 ● 待っている</, `${theme}: 下の行に出る字`);
      assert.doesNotMatch(out, /data-side="left">確認待ち/, `${theme}: 青い帯の上（left）に出ない`);
    }
  });
});

test('D0090-AC-05: devPageHtml のページ（画面で見る前の素材）：費用は「取れない」・使用量の欄は「使用量は取れません」と理由を出し、「$0.000」はどこにも無い', async () => {
  const html = devPageHtml();
  await withTempDir(async (dest) => {
    for (const theme of ['light', 'dark'] as const) {
      const out = await html(dest, theme);
      assert.match(out, /<strong>取れない<\/strong>/, `${theme}: 上のバーの費用は「取れない」`);
      assert.match(out, /data-usage-unavailable/, `${theme}: 使用量の欄`);
      assert.match(out, /使用量は取れません/, `${theme}: 使用量の理由`);
      assert.doesNotMatch(out, /\$0\.000/, `${theme}: $0.000 は出ない`);
    }
  });
});
