// 時系列の確認待ちの字を行の下へ出す（D0090・AC-09〜11・15）：renderGantt の出力。
// - AC-09（赤）：再現の入力（実行 0〜1.0 秒・長さ 0 の live の待ち・全体 1.0 秒）で、待ちの字は data-side="below"、その行だけ has-below。
// - AC-10（守る。今の作りで通る）：既存の入力の時系列の行は、変える前に今の ganttHtml.ts が返した HTML をそのまま固定する。
//   has-below と data-side="below" が、入口（幅 5% 未満で右端 85% 超の待ち）を持たない既存の確認用ページに出ないことも確かめる。
//   設計の 1.4 は「既存のページに 5% 未満の待ちは無い見込み」だったが、実際は 7 種のページに入口がある（ENTRANCE_PAGES）。そこは変わってよい（推し 6。画面の AC-13 で見る）。
// - AC-11：外から来た文字は escapeHtml を通る。style 属性・動き・外部の読み込み・font-size を足さない（below の規則の CSS は赤）。
// - AC-15（守る）：時刻の無い記録は今までどおりの文で、has-below を出さない。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { GanttModel, GanttRow } from '../domain/gantt.ts';
import { GANTT_STYLE, renderGantt } from './ganttHtml.ts';
import { withTempDir } from '../test/tempDir.ts';
import {
  RUNNING_DIR,
  RUNNING_NEXT_DIR,
  RUNNING_SEC,
  SHOWCASE_DIR,
  STALE_AFTER_SEC,
  WAITING_DIR,
  WAITING_SEC,
  artifactsPageHtml,
  budgetPageHtml,
  buildOmittedTree,
  buildRunsTree,
  chatPageHtml,
  checkPageHtml,
  groupPageHtml,
  panelPreviewHtml,
  panelRunsPreviewHtml,
  previewClock,
  readLiveViewAligned,
  readRunsView,
  readShowcaseView,
  replyPageHtml,
  staleRunsPageHtml,
  startOfLiveness,
  toolsPageHtml,
} from '../../scripts/previewPages.ts';

const gRow = (p: Partial<GanttRow> & { seq: number; label: string }): GanttRow => ({ agent: null, run: null, wait: null, ...p });
const gModel = (rows: GanttRow[], p: Partial<GanttModel> = {}): GanttModel => ({
  rows,
  omittedRows: 0,
  totalSec: 100,
  ticks: [20, 40, 60, 80, 100],
  live: false,
  hasTimes: true,
  ...p,
});
const runBar = (startSec: number, endSec: number, p: { failed?: boolean; live?: boolean } = {}) => ({ startSec, endSec, failed: p.failed ?? false, live: p.live ?? false });
const waitBar = (startSec: number, endSec: number, live = false) => ({ startSec, endSec, live });

/** 行の部分だけ（最初の行の始まりから凡例の前まで）。軸・凡例・定義は含めない。 */
function rowsOf(out: string): string {
  const from = out.indexOf('<div class="g-row"');
  const to = out.indexOf('<div class="g-key">');
  assert.ok(from >= 0 && to > from, '行と凡例がある');
  return out.slice(from, to);
}
/** 行ごとに分ける（各行は <div class="g-row" から始まる）。 */
const splitRows = (out: string): string[] => rowsOf(out).split(/(?=<div class="g-row)/);

// ---- 再現の入力 ----

/** 実物の記録の再現：要件定義 0〜0.3・設計 0〜0.6・テスト先行 0〜1.0 秒。最後の行だけ、長さ 0 の live の待ち（1.0〜1.0 秒）。全体は 1.0 秒。 */
const REPRO = gModel(
  [
    gRow({ seq: 1, label: '要件定義', agent: 'pipe-in-analyst', run: runBar(0, 0.3) }),
    gRow({ seq: 2, label: '設計', agent: 'pipe-in-analyst', run: runBar(0, 0.6) }),
    gRow({ seq: 3, label: 'テスト先行', agent: 'pipe-in-tester', run: runBar(0, 1.0), wait: waitBar(1.0, 1.0, true) }),
  ],
  { totalSec: 1.0, ticks: [0, 0.5, 1.0], live: true },
);

test('D0090-AC-09: 再現の入力：確認待ちの字は実行の帯の上に乗る位置（data-side="left"）に出ず、帯の下（data-side="below"）に出る', () => {
  const out = renderGantt(REPRO);
  assert.doesNotMatch(out, /data-side="left"[^<]*>確認待ち/, '左（実行の帯の上）に確認待ちの字を出さない');
  assert.match(out, /<span class="g-text r\d+" data-side="below">確認待ち 0:00 ● 待っている<\/span>/);
});

test('D0090-AC-09: 再現の入力：below の字の位置のクラス（r の数）は 0〜100 の範囲内で、帯の右端にそろえる（右端 100% なら r0）', () => {
  const out = renderGantt(REPRO);
  const m = /<span class="g-text r(\d+)" data-side="below">/.exec(out);
  assert.ok(m !== null, 'below の字がある');
  const n = Number(m[1]);
  assert.ok(n >= 0 && n <= 100, `r${n} は 0〜100`);
  assert.equal(n, 0);
});

test('D0090-AC-09: 再現の入力：字が below の行だけが has-below を持つ。ほかの 2 行は今までと同じ <div class="g-row">', () => {
  const rows = splitRows(renderGantt(REPRO));
  assert.equal(rows.length, 3);
  assert.ok(rows[0]!.startsWith('<div class="g-row">'), '1 行目は has-below なし');
  assert.ok(rows[1]!.startsWith('<div class="g-row">'), '2 行目は has-below なし');
  assert.ok(rows[2]!.startsWith('<div class="g-row has-below">'), '3 行目は has-below つき');
});

test('D0090-AC-09: 再現の入力：実行の帯の中の字（要件定義 0:00・設計 0:00・テスト先行 0:01）は今までどおり帯の真ん中（g-in・x15・x30・x50）に出る', () => {
  const out = renderGantt(REPRO);
  assert.match(out, /<span class="g-text g-in x15">0:0\d<\/span>/);
  assert.match(out, /<span class="g-text g-in x30">0:0\d<\/span>/);
  assert.match(out, /<span class="g-text g-in x50">0:01<\/span>/);
});

test('D0090-AC-09: below の字と行のための CSS 規則がある（.g-text[data-side="below"]・.g-row.has-below）。font-size は足さない', () => {
  assert.match(GANTT_STYLE, /\.g-text\[data-side="below"\]\s*\{/);
  assert.match(GANTT_STYLE, /\.g-row\.has-below\s*\{/);
  assert.equal((GANTT_STYLE.match(/font-size/g) ?? []).length, 1, 'font-size は .gantt の 1 か所のまま（既存の px の検査を保つ）');
});

test('D0090-AC-09: 待ちが短い（5% 未満）でも、右端が 85% 以下の待ちや、実行の帯が字の範囲にかからない待ちでは、below にも has-below にもならない（今の作りで通る。守る）', () => {
  const noRun = renderGantt(gModel([gRow({ seq: 1, label: 'a', run: runBar(0, 50), wait: waitBar(100, 100, true) })], { live: true }));
  assert.doesNotMatch(noRun, /has-below|data-side="below"/);
  const middle = renderGantt(gModel([gRow({ seq: 1, label: 'a', run: runBar(0, 40), wait: waitBar(40, 41, true) })], { live: true }));
  assert.doesNotMatch(middle, /has-below|data-side="below"/);
});

// ---- AC-10：既存の入力の行は変えない（変える前の出力をそのまま固定。今の作りで通る） ----

/** liveWait の形（ganttHtml.test.ts D0019-AC-77）：実行 0〜(start-5)・待ち start〜end（live）。 */
const liveWait = (start: number, end: number): GanttModel =>
  gModel([gRow({ seq: 1, label: 'a', run: runBar(0, Math.max(start - 5, 1)), wait: waitBar(start, end, true) })], { totalSec: 100, live: true });

const GOLDEN: [string, GanttModel, string][] = [
  [
    '待ち 40〜60%（右）',
    liveWait(40, 60),
    '<div class="g-row"><span class="g-label" title="a">a</span><div class="g-track"><svg class="g-bars" viewBox="0 0 100 16" preserveAspectRatio="none" aria-hidden="true"><rect class="g-run" x="0" y="0" width="35" height="16"/><rect class="g-wait" x="40" y="0" width="20" height="16"/><rect class="g-ring" x="40" y="0" width="20" height="16"/></svg><span class="g-text g-in x18">0:35</span><span class="g-text x60" data-side="right">確認待ち 0:20 ● 待っている</span></div></div>',
  ],
  [
    '待ち 70〜86%（左）',
    liveWait(70, 86),
    '<div class="g-row"><span class="g-label" title="a">a</span><div class="g-track"><svg class="g-bars" viewBox="0 0 100 16" preserveAspectRatio="none" aria-hidden="true"><rect class="g-run" x="0" y="0" width="65" height="16"/><rect class="g-wait" x="70" y="0" width="16" height="16"/><rect class="g-ring" x="70" y="0" width="16" height="16"/></svg><span class="g-text g-in x33">1:05</span><span class="g-text r30" data-side="left">確認待ち 0:16 ● 待っている</span></div></div>',
  ],
  [
    '待ち 90〜96%（幅 6%・左）',
    liveWait(90, 96),
    '<div class="g-row"><span class="g-label" title="a">a</span><div class="g-track"><svg class="g-bars" viewBox="0 0 100 16" preserveAspectRatio="none" aria-hidden="true"><rect class="g-run" x="0" y="0" width="85" height="16"/><rect class="g-wait" x="90" y="0" width="6" height="16"/><rect class="g-ring" x="90" y="0" width="6" height="16"/></svg><span class="g-text g-in x43">1:25</span><span class="g-text r10" data-side="left">確認待ち 0:06 ● 待っている</span></div></div>',
  ],
  [
    '待ち 90〜100%（左）',
    liveWait(90, 100),
    '<div class="g-row"><span class="g-label" title="a">a</span><div class="g-track"><svg class="g-bars" viewBox="0 0 100 16" preserveAspectRatio="none" aria-hidden="true"><rect class="g-run" x="0" y="0" width="85" height="16"/><rect class="g-wait" x="90" y="0" width="10" height="16"/><rect class="g-ring" x="90" y="0" width="10" height="16"/></svg><span class="g-text g-in x43">1:25</span><span class="g-text r10" data-side="left">確認待ち 0:10 ● 待っている</span></div></div>',
  ],
  [
    '待ち中でない 60〜95%（実行は 0〜50%・左）',
    gModel([gRow({ seq: 1, label: 'a', run: runBar(0, 50), wait: waitBar(60, 95) })]),
    '<div class="g-row"><span class="g-label" title="a">a</span><div class="g-track"><svg class="g-bars" viewBox="0 0 100 16" preserveAspectRatio="none" aria-hidden="true"><rect class="g-run" x="0" y="0" width="50" height="16"/><rect class="g-wait" x="60" y="0" width="35" height="16"/></svg><span class="g-text g-in x25">0:50</span><span class="g-text r40" data-side="left">確認待ち 0:35</span></div></div>',
  ],
];

for (const [name, model, golden] of GOLDEN) {
  test(`D0090-AC-10: 既存の入力（${name}）の行の HTML は、変える前と 1 字も違わない（今の作りで通る。守る）`, () => {
    assert.equal(rowsOf(renderGantt(model)), golden);
  });
}

test('D0090-AC-10: 既存の入力のどれも has-below・data-side="below" を出さない（守る）', () => {
  for (const [name, model] of GOLDEN) assert.doesNotMatch(renderGantt(model), /has-below|data-side="below"/, name);
});

test('D0090-AC-10: 時系列に待ちの無い行（実行だけ・実行の帯が無い行）も has-below にならない（守る）', () => {
  const out = renderGantt(gModel([gRow({ seq: 1, label: 'a', run: runBar(0, 50) }), gRow({ seq: 2, label: 'b', run: null })]));
  assert.doesNotMatch(out, /has-below/);
  assert.match(out, /<span class="g-note">時刻の記録なし<\/span>/);
});

// ---- AC-10 の根拠：入口を持たない既存の確認用ページに、新しい置き方は出ない ----

/** 既存の確認用ページ（dev 以外）の本体の HTML を、ページ名つきで組み立てる（暗い画面。時系列の本体はテーマによらない）。 */
async function existingPages(): Promise<[string, string][]> {
  return withTempDir(async (dest) => {
    const out: [string, string][] = [];
    const theme = 'dark' as const;
    out.push(['done', panelPreviewHtml(await readShowcaseView(SHOWCASE_DIR), theme, undefined, STALE_AFTER_SEC)]);
    const running = await readLiveViewAligned(RUNNING_DIR, RUNNING_SEC, dest);
    const next = await readLiveViewAligned(RUNNING_NEXT_DIR, 5, dest);
    out.push(['running', panelPreviewHtml(running, theme, next, STALE_AFTER_SEC)]);
    out.push(['waiting', panelPreviewHtml(await readLiveViewAligned(WAITING_DIR, WAITING_SEC, dest), theme, undefined, STALE_AFTER_SEC)]);
    const since = await startOfLiveness(WAITING_DIR);
    assert.ok(since !== null, '確認待ちの見本に待ち始めの時刻がある');
    for (const kind of ['runs', 'runs-omitted'] as const) {
      const { workspace } = await (kind === 'runs' ? buildRunsTree(dest) : buildOmittedTree(dest));
      out.push([kind, panelRunsPreviewHtml(await readRunsView(workspace, previewClock(since, WAITING_SEC)), theme, { staleAfterSec: STALE_AFTER_SEC })]);
    }
    for (const kind of ['stale', 'stale-soon'] as const) out.push([kind, await staleRunsPageHtml(dest, kind, theme)]);
    out.push(['artifacts', await artifactsPageHtml(dest, theme)]);
    out.push(['tools', await toolsPageHtml(dest, theme)]);
    out.push(['budget', await budgetPageHtml(dest, theme)]);
    for (const kind of ['self', 'back', 'old'] as const) out.push([`check-${kind}`, await checkPageHtml(dest, kind, theme)]);
    for (const kind of ['running', 'failed', 'old'] as const) out.push([`group-${kind}`, await groupPageHtml(dest, kind, theme)]);
    out.push(['chat', await chatPageHtml(dest, theme)]);
    out.push(['reply', await replyPageHtml(dest, theme)]);
    return out;
  });
}

const WAIT_RECT = /class=\\*"g-wait\\*" x=\\*"([\d.]+)\\*" y=\\*"[\d.]+\\*" width=\\*"([\d.]+)/g;

/** 新しい置き方の入口になりうる待ちの帯（幅 5% 未満で右端が 85% 超）を持つページ。設計の 1.4 は「無い見込み」と書いたが、実際には下の 7 つにある。 */
const ENTRANCE_PAGES = ['runs', 'runs-omitted', 'stale', 'stale-soon', 'artifacts', 'tools', 'reply'];

function hasEntrance(html: string): boolean {
  return [...html.matchAll(WAIT_RECT)].some((m) => Number(m[2]) < 5 && Number(m[1]) + Number(m[2]) > 85);
}

test('D0090-AC-10: 既存の確認用ページのうち、新しい置き方の入口の待ちを持たないページ（done・running・waiting・budget・check・group・chat）の時系列に、has-below の行と data-side="below" の字は出ない（今の作りで通る。守る）', async () => {
  let checked = 0;
  for (const [name, html] of await existingPages()) {
    if (ENTRANCE_PAGES.includes(name)) continue;
    checked += 1;
    assert.doesNotMatch(html, /class=\\*"g-row has-below/, `${name}: has-below の行が出ない`);
    // ページの <style> には .g-text[data-side="below"] の規則が入るので、言葉の要素（span）に絞って見る
    assert.doesNotMatch(html, /<span[^>]*data-side=\\*"below/, `${name}: data-side="below" が出ない`);
  }
  assert.ok(checked >= 10, `確かめたページが ${checked} 件しかない`);
});

test('D0090-AC-10: （前提の記録）新しい置き方の入口（幅 5% 未満で右端が 85% 超の待ち）を持つ確認用ページは runs・runs-omitted・stale・stale-soon・artifacts・tools・reply だけ。ほかのページには無い（今の作りで通る。守る）', async () => {
  const withEntrance = (await existingPages()).filter(([, html]) => hasEntrance(html)).map(([name]) => name);
  assert.deepEqual(withEntrance, ENTRANCE_PAGES);
});

test('D0090-AC-10: 入口を持つ 7 ページ以外の待ちの帯は、幅が 5% 未満でも右端が 85% 以下（置き場所は今のまま right）で、見え方が変わらない（今の作りで通る。守る）', async () => {
  let waits = 0;
  for (const [name, html] of await existingPages()) {
    if (ENTRANCE_PAGES.includes(name)) continue;
    for (const m of html.matchAll(WAIT_RECT)) {
      waits += 1;
      const width = Number(m[2]);
      assert.ok(width >= 5 || Number(m[1]) + width <= 85, `${name}: 幅 ${width}%・右端 ${Number(m[1]) + width}%`);
    }
  }
  assert.ok(waits > 0, '待ちの帯を持つページがある');
});

// ---- AC-11：外から来た文字・CSP ----

const EVIL = '<img src=x onerror=alert(1)>"&';

test('D0090-AC-11: below の行でも、段の表示名・受け持ちの < " & は escapeHtml を通る（生のタグが出ない）', () => {
  const out = renderGantt(
    gModel([gRow({ seq: 1, label: EVIL, agent: EVIL, run: runBar(0, 100), wait: waitBar(100, 100, true) })], { totalSec: 100, live: true }),
  );
  assert.match(out, /data-side="below"/, '再現の形（below）で確かめる');
  assert.doesNotMatch(out, /<img/, '生のタグが出ない');
  assert.match(out, /&lt;img src=x onerror=alert\(1\)&gt;&quot;&amp;/);
});

test('D0090-AC-11: 時系列の出力と GANTT_STYLE に、style 属性・動き（animation・@keyframes）・外部の読み込み（http・@import・url(http)）を足さない', () => {
  const out = renderGantt(REPRO);
  assert.doesNotMatch(out, /\sstyle=/);
  assert.doesNotMatch(out, /https?:/);
  assert.doesNotMatch(GANTT_STYLE, /animation|@keyframes|@import|https?:/);
});

// ---- AC-15：時刻の無い記録 ----

test('D0090-AC-15: 時刻の記録が無い（hasTimes: false）ときは、今までどおり「時刻の記録がありません」だけで、has-below も行も出ない（今の作りで通る。守る）', () => {
  const out = renderGantt(gModel([gRow({ seq: 1, label: 'a', run: null })], { hasTimes: false }));
  assert.equal(out, '<h2 class="terminal-title">時系列</h2><p class="gantt-none">時刻の記録がありません</p>');
});
