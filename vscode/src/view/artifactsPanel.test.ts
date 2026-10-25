// 「成果物」タブを入れたパネル全体の検査（D0025）：本体の HTML（スクリプトを動かさない）・幅の 3 つの帯の CSS・色・外から来た文字・大きさの上限。
// 一覧とプレビュー 1 つずつの HTML は artifactsHtml.test.ts、パネルのスクリプトの動きは panelScriptArtifacts.test.ts が持つ。
// 新しい部品（view/artifactsHtml.ts の ARTIFACTS_STYLE）は、テストの中で読み込む（テスト先行のとき、まだ無いあいだも各テストが落ち、ファイルごと読めずに落ちることが無いようにしたため）。
// 成果物の一覧の項目（domain/artifacts.ts の ArtifactEntry）は、図の状態（runningView など）の artifacts を手で組み立てた項目に替えて渡す（view の部分だけを確かめる）。
// domain を通す検査（旧形の写し・更新時刻の書き方）は、AC-72・AC-04・AC-05 の組み合わせとして、buildPipelineView を通して確かめる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { PipelineView, ViewClock, WorkDirSnapshot } from '../domain/pipelineView.ts';
import { THEMES } from '../../scripts/previewPages.ts';
import { extractCss, motionOutsideNoPreference, parseCss } from '../test/cssBlocks.ts';
import type { CssRule } from '../test/cssBlocks.ts';
import { FakeDocument } from '../test/fakeDom.ts';
import type { FakeNode } from '../test/fakeDom.ts';
import { snapshot } from '../test/fixtures.ts';
import { finishedView, runningView, waitingView } from '../test/liveFixtures.ts';
import { panelsByName } from '../test/panelParts.ts';
import { showcaseView } from '../test/reasonFixtures.ts';
import { listView, sampleRows } from '../test/runListFixtures.ts';
import { escapeHtml } from './escape.ts';
import { parseWebviewMessage } from './messages.ts';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';
import { SHELL_STYLE } from './shellHtml.ts';

/** 使う分だけの型。テスト先行のとき artifactsHtml.ts がまだ無くても型検査が通るよう、読み込みの指定を定数でない形にして型を与えた */
interface ArtifactsHtmlMod {
  ARTIFACTS_STYLE: string;
  CUT_NOTICE: string;
}
const ah = (): Promise<ArtifactsHtmlMod> => import(String('./artifactsHtml.ts')) as Promise<ArtifactsHtmlMod>;
const NONCE = 'TESTNONCE';

// ---- 項目の組み立て ----

interface Entry {
  name: string;
  label: string;
  stage: string | null;
  stageLabel: string | null;
  ready: boolean;
  text: string;
  cut: boolean;
  updatedText: string;
}
const ready = (name: string, label: string = name, over: Partial<Entry> = {}): Entry => ({
  name,
  label,
  stage: null,
  stageLabel: null,
  ready: true,
  text: `本文 ${name}`,
  cut: false,
  updatedText: '10/17 10:05',
  ...over,
});
const missing = (name: string, label: string = name, over: Partial<Entry> = {}): Entry => ({ ...ready(name, label), ready: false, text: '', updatedText: '—', ...over });

const DEV: readonly (readonly [string, string, string | null, string | null])[] = [
  ['00_input.md', '要件メモ', null, null],
  ['01_requirements.md', '要件定義書', 'requirements', '要件定義'],
  ['02_design.md', '設計書', 'design', '設計'],
  ['03_red_tests.md', 'テスト先行の記録', 'red', 'テスト先行'],
  ['04_implementation.md', '実装の記録', 'implement', '実装'],
  ['05_test_report.md', 'テスト報告', 'test', '検証'],
  ['99_summary.md', 'まとめ', null, null],
];
const DEV_NAMES = DEV.map((d) => d[0]);
function dev(readyNames: readonly string[] = DEV_NAMES, over: Record<string, Partial<Entry>> = {}): Entry[] {
  return DEV.map(([name, label, stage, stageLabel]) => (readyNames.includes(name) ? ready : missing)(name, label, { stage, stageLabel, ...(over[name] ?? {}) }));
}

/** 図の状態の artifacts（と、動いている段・確認待ちの段の元）を差し替える。base が動いている・確認待ち・終わった、のどれかを決める */
function viewWith(entries: Entry[], base: PipelineView = runningView(83)): PipelineView {
  return { ...base, artifacts: entries as unknown as PipelineView['artifacts'] };
}

// ---- 木の読み取り（偽の DOM） ----

function parse(out: string): FakeDocument {
  const doc = new FakeDocument();
  doc.innerHTML = out;
  return doc;
}
const pickedNames = (doc: FakeDocument): string[] =>
  doc
    .querySelectorAll('button[data-art-pick]')
    .filter((b) => b.getAttribute('aria-pressed') === 'true')
    .map((b) => b.getAttribute('data-art-pick')!);
const previews = (doc: FakeDocument): FakeNode[] => doc.querySelectorAll('[data-art-preview]');
const shownNames = (doc: FakeDocument): string[] =>
  previews(doc)
    .filter((p) => !p.hasAttribute('hidden'))
    .map((p) => p.getAttribute('data-art-preview')!);
const count = (text: string, re: RegExp): number => (text.match(re) ?? []).length;
// 詳細のタブパネルを data-detail-panel の値で取る補助（panelsByName）は、D0050 で test/panelParts.ts へ移した（関数の中身は変えていない）。
// 番号でなく名前で取るので、タブが 4 つになっても位置に左右されない。個数は決め打ちしない。

// ---- タグだけを取り出して属性名を調べる（AC-32・AC-38：成果物の文字（text ノード）は調べない） ----

/** HTML から <script>・<style> の中身を除き、<[a-z][^>]*> に当たるタグごとに、名前と属性名を返す */
function tagsOf(out: string): { tag: string; attrs: string[] }[] {
  const body = out.replace(/<script\b[\s\S]*?<\/script>/gi, '').replace(/<style\b[\s\S]*?<\/style>/gi, '');
  return Array.from(body.matchAll(/<([a-z][^\s>/]*)([^>]*)>/gi), (m) => ({ tag: m[1]!.toLowerCase(), attrs: attrNames(m[2]!) }));
}
function attrNames(rest: string): string[] {
  return Array.from(rest.matchAll(/([^\s"'<>/=]+)(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+))?/g), (m) => m[1]!.toLowerCase());
}
const isDangerousAttr = (name: string): boolean => name === 'style' || name === 'src' || name === 'href' || name.startsWith('on');
/** style・on…・src・href を属性に持つタグの数 */
const dangerousTags = (out: string): number => tagsOf(out).filter((t) => t.attrs.some(isDangerousAttr)).length;

test('D0025-AC-38: 検査そのもの：タグだけを取り出して属性名を調べる。<img src=x onerror=1> は見つけ、文字の中の &lt;img src=x onerror=1&gt; は見つけない', () => {
  assert.equal(dangerousTags('<p>安全</p>'), 0);
  assert.equal(dangerousTags('<img src=x onerror=1>'), 1);
  assert.equal(dangerousTags('<a href="javascript:1">x</a><p style="color:red" onclick="f()">y</p>'), 2);
  assert.equal(dangerousTags('<p>&lt;img src=x onerror=1&gt; と &lt;a href="x"&gt;</p>'), 0, '文字の中は調べない');
  assert.equal(dangerousTags('<script nonce="n">if (a < b && c > d) { x = "<img src=1>"; }</script><style nonce="n">.a > .b { color: red }</style><p class="a">ok</p>'), 0, 'script・style の中は調べない');
  assert.deepEqual(tagsOf('<button type="button" class="x" disabled data-a="1 2">go</button>')[0], { tag: 'button', attrs: ['type', 'class', 'disabled', 'data-a'] });
});

// ---- AC-15・AC-52・AC-53：本体の HTML（スクリプトを動かさない） ----

const BASES: readonly (readonly [string, () => PipelineView, string])[] = [
  ['動いている段が設計', () => runningView(83), '02_design.md'],
  ['動いている段が無く、要件定義の確認待ち', () => waitingView(40), '01_requirements.md'],
  ['終わった実行（動いている段も確認待ちも無い）', () => finishedView(), '99_summary.md'],
];
for (const [label, make, expected] of BASES) {
  test(`D0025-AC-15: パネルのスクリプトが動く前の HTML だけで、既定の行が aria-pressed="true" になり、そのプレビューだけが見える（${label} → ${expected}）`, () => {
    for (const list of [undefined, listView(sampleRows(), { selected: 'here|survey' })]) {
      const out = renderViewBody(viewWith(dev(), make()), list);
      const doc = parse(out);
      assert.deepEqual(pickedNames(doc), [expected]);
      assert.deepEqual(shownNames(doc), [expected]);
      assert.equal(previews(doc).length, 7, '「ある」成果物のプレビューが全部入っている');
      assert.equal(doc.querySelector('.art')?.getAttribute('data-art-default'), expected);
    }
  });
}

test('D0025-AC-15: 既定の成果物が「まだない」ときは、一覧の順で最後の「ある」成果物が、HTML だけで選ばれて見える', () => {
  const doc = parse(renderViewBody(viewWith(dev(['00_input.md', '01_requirements.md'])), undefined));
  assert.deepEqual(pickedNames(doc), ['01_requirements.md'], '動いている段（設計）の 02 がまだ無い');
  assert.deepEqual(shownNames(doc), ['01_requirements.md']);
});

test('D0025-AC-14: 「ある」成果物が 1 つも無い実行のパネルは、選んだ行が無く、プレビューの場所に「まだ成果物がありません」が出る', () => {
  const doc = parse(renderViewBody(viewWith(dev([])), undefined));
  assert.deepEqual(pickedNames(doc), []);
  assert.equal(previews(doc).length, 0);
  assert.match(doc.querySelector('.art-empty')?.textContent ?? '', /まだ成果物がありません/);
});

test('D0025-AC-52: 「ある」成果物すべてのプレビューが、描き直しの HTML（render の html になる本体）に入る。「まだない」ものは入らない', () => {
  const entries = dev(['00_input.md', '01_requirements.md', '03_red_tests.md', '99_summary.md']);
  const doc = parse(renderViewBody(viewWith(entries), undefined));
  assert.deepEqual(previews(doc).map((p) => p.getAttribute('data-art-preview')), ['00_input.md', '01_requirements.md', '03_red_tests.md', '99_summary.md']);
  assert.equal(shownNames(doc).length, 1, '見えるのは選んだ 1 つだけ');
});

test('D0025-AC-52: parseWebviewMessage は新しい種類（pickArtifact など）を捨てる（null）。今ある 3 つ（ready・openArtifact・selectRun）はそのまま（今のまま通る。守る）', () => {
  for (const msg of [
    { type: 'pickArtifact', name: '01_requirements.md' },
    { type: 'pickArtifact', id: 'here|' },
    { type: 'selectArtifact', name: 'x.md' },
    { type: 'scrollArtifact', top: 10 },
  ]) {
    assert.equal(parseWebviewMessage(msg), null, msg.type);
  }
  assert.deepEqual(parseWebviewMessage({ type: 'ready' }), { type: 'ready' });
  assert.deepEqual(parseWebviewMessage({ type: 'openArtifact', name: '01_requirements.md' }), { type: 'openArtifact', name: '01_requirements.md' });
  assert.deepEqual(parseWebviewMessage({ type: 'selectRun', id: 'here|' }), { type: 'selectRun', id: 'here|' });
});

test('D0025-AC-53: 同じ記録・同じ中身・同じ「今」なら、同じ HTML ができる（本体も、完成した HTML も）（今のまま通る。守る）', () => {
  const make = (): PipelineView => viewWith(dev(DEV_NAMES, { '02_design.md': { cut: true, text: '# 設計\n\n- a\n- b' } }));
  assert.equal(renderViewBody(make(), listView(sampleRows())), renderViewBody(make(), listView(sampleRows())));
  assert.equal(renderPanelHtml(make(), NONCE), renderPanelHtml(make(), NONCE));
});

// ---- AC-72・AC-04・AC-05・AC-45：domain を通した組み合わせ（旧形の写し・新しい形の写し） ----

const CLOCK: ViewClock = { nowMs: Date.UTC(2026, 9, 17, 12, 0, 0), localOffsetMin: 540 };
const MTIME = Date.UTC(2026, 9, 17, 1, 5, 0);
/** 新しい形の写し（文字・更新時刻・切れた印）を、今の WorkDirSnapshot の型に載せる */
const files = (value: Record<string, unknown>): WorkDirSnapshot['artifacts'] => value as unknown as WorkDirSnapshot['artifacts'];
const rowOf = (doc: FakeDocument, file: string): FakeNode => {
  const found = doc.querySelectorAll('.art-row').find((r) => r.querySelector('.art-file')?.textContent === file);
  assert.ok(found, `${file} の行がある`);
  return found;
};

test('D0025-AC-72: 今の形の写し（成果物が中身の文字だけ）でも、「ある」「まだない」が今までと同じに決まり、時刻は「—」、切れた案内は出ない', () => {
  const view = buildPipelineView(snapshot({ artifacts: { '00_input.md': 'メモ', '01_requirements.md': '要件', '03_red_tests.md': '  ' } }), CLOCK);
  const doc = parse(renderViewBody(view, undefined));
  const rows = doc.querySelectorAll('.art-row');
  assert.equal(rows.length, 7);
  assert.deepEqual(rows.filter((r) => !r.disabled).map((r) => r.querySelector('.art-file')!.textContent), ['00_input.md', '01_requirements.md']);
  assert.ok(rowOf(doc, '03_red_tests.md').disabled, '空白だけは「まだない」');
  for (const r of rows) assert.equal(r.querySelector('.art-time')?.textContent, '—', '旧形は時刻なし');
  assert.deepEqual(previews(doc).map((p) => p.getAttribute('data-art-preview')), ['00_input.md', '01_requirements.md']);
  assert.equal(doc.querySelector('.art-cut'), null);
  assert.deepEqual(pickedNames(doc), ['01_requirements.md'], '最後の「ある」');
});

test('D0025-AC-04: 新しい形の写し（文字と更新時刻）の更新時刻が、手元の時刻の MM/DD HH:mm で行の時刻の欄に出る（UTC 01:05・ずれ 540 分 → 10/17 10:05）', () => {
  const view = buildPipelineView(snapshot({ artifacts: files({ '00_input.md': { text: 'メモ', mtimeMs: MTIME }, '01_requirements.md': { text: '要件', mtimeMs: Date.UTC(2026, 9, 31, 23, 30, 0) } }) }), CLOCK);
  const doc = parse(renderViewBody(view, undefined));
  assert.equal(rowOf(doc, '00_input.md').querySelector('.art-time')?.textContent, '10/17 10:05');
  assert.equal(rowOf(doc, '01_requirements.md').querySelector('.art-time')?.textContent, '11/01 08:30', '日付・月が変わる');
  assert.equal(rowOf(doc, '02_design.md').querySelector('.art-time')?.textContent, '—', '「まだない」は「—」');
});

const BAD_MTIMES: readonly (readonly [string, unknown])[] = [
  ['文字', 'abc'],
  ['負の数', -5],
  ['0', 0],
  ['NaN', Number.NaN],
  ['無限大', Number.POSITIVE_INFINITY],
  ['巨大な数', 1e300],
  ['null', null],
  ['オブジェクト', {}],
];
for (const [label, mtimeMs] of BAD_MTIMES) {
  test(`D0025-AC-05: 更新時刻が読めない写し（${label}）でも例外を出さず、時刻の欄は「—」で、プレビューの中身は出る`, () => {
    const view = buildPipelineView(snapshot({ artifacts: files({ '00_input.md': { text: '中身は出る', mtimeMs } }) }), CLOCK);
    const doc = parse(renderViewBody(view, undefined));
    assert.equal(rowOf(doc, '00_input.md').querySelector('.art-time')?.textContent, '—');
    assert.match(doc.querySelector('[data-art-preview]')?.textContent ?? '', /中身は出る/);
  });
}

test('D0025-AC-05: 時計（ViewClock）が渡されないときも、時刻の欄は「—」で中身は出る', () => {
  const view = buildPipelineView(snapshot({ artifacts: files({ '00_input.md': { text: '中身', mtimeMs: MTIME } }) }));
  const doc = parse(renderViewBody(view, undefined));
  assert.equal(rowOf(doc, '00_input.md').querySelector('.art-time')?.textContent, '—');
  assert.match(doc.querySelector('[data-art-preview]')?.textContent ?? '', /中身/);
});

test('D0025-AC-45: 切れた印（cut）の付いた写しは、そのプレビューの見出しの下にだけ切れた案内が出る', async () => {
  const { CUT_NOTICE } = await ah();
  const view = buildPipelineView(snapshot({ artifacts: files({ '00_input.md': { text: '短い', mtimeMs: MTIME }, '01_requirements.md': { text: '先頭だけ', mtimeMs: MTIME, cut: true } }) }), CLOCK);
  const doc = parse(renderViewBody(view, undefined));
  const notices = doc.querySelectorAll('.art-cut');
  assert.equal(notices.length, 1);
  assert.equal(notices[0]!.textContent, CUT_NOTICE);
  assert.equal(notices[0]!.closest('[data-art-preview]')?.getAttribute('data-art-preview'), '01_requirements.md');
});

// ---- AC-37：大きさの上限 ----

const MAX = 262_144;
/** ASCII なので文字数 = バイト数。上限いっぱいにそろえる */
const exactly = (text: string): string => (text.length >= MAX ? text.slice(0, MAX) : text + ' '.repeat(MAX - text.length));
const SHAPES: readonly (readonly [string, () => string])[] = [
  ['箇条書きの 1 行ずつ', () => exactly('- a\n'.repeat(MAX / 4))],
  ['表の 1 文字ずつ', () => exactly('|a|b|c|d|\n|-|-|-|-|\n' + '|x|y|z|w|\n'.repeat(Math.floor(MAX / 10)))],
  ['引用の 1 行ずつ', () => exactly('> a\n'.repeat(MAX / 4))],
];
const names = (n: number): string[] => Array.from({ length: n }, (_, i) => `a${String(i).padStart(2, '0')}.md`);

function measure(entries: Entry[], base: PipelineView): { out: string; ms: number; inputBytes: number } {
  const inputBytes = entries.reduce((sum, e) => sum + Buffer.byteLength(e.text, 'utf8'), 0);
  const view = viewWith(entries, base);
  const from = performance.now();
  const out = renderViewBody(view, undefined);
  return { out, ms: performance.now() - from, inputBytes };
}

test('D0025-AC-37: 検査そのもの：上限いっぱいの見本は 262,144 バイトちょうどで、3 つの形（箇条書き・表・引用）がそろう', () => {
  for (const [, make] of SHAPES) assert.equal(Buffer.byteLength(make(), 'utf8'), MAX);
  assert.match(SHAPES[0]![1](), /^- a\n- a\n/);
  assert.match(SHAPES[1]![1](), /^\|a\|b\|c\|d\|\n\|-\|-\|-\|-\|\n\|x\|y\|z\|w\|\n/);
  assert.match(SHAPES[2]![1](), /^> a\n> a\n/);
});

test('D0025-AC-37: 上限いっぱいの成果物（箇条書き・表・引用の各 4 つ）を 12 個持つ実行の renderViewBody が、例外を出さず、5000ms 未満で、HTML の長さが入力の合計の 20 倍以内（初めの値。実測して決め直す）', () => {
  const entries = names(12).map((name, i) => ready(name, name, { text: SHAPES[i % 3]![1]() }));
  const { out, ms, inputBytes } = measure(entries, runningView(83));
  assert.equal(count(out, /data-art-preview=/g), 12, '12 個のプレビューが入っている');
  assert.ok(ms < 5000, `${ms.toFixed(0)}ms`);
  assert.ok(out.length <= 20 * inputBytes, `HTML ${out.length} 文字 / 入力 ${inputBytes} バイト`);
});

test('D0025-AC-37: 合計の上限まで読んだ最大の写し（上限いっぱいの 16 個＝4 MiB。残りの 44 個は読まれず「まだない」）の renderViewBody も、例外を出さず、5000ms 未満で、HTML の長さが入力の合計の 20 倍以内', () => {
  const entries = [...names(16).map((name, i) => ready(name, name, { text: SHAPES[i % 3]![1]() })), ...names(60).slice(16).map((name) => missing(name))];
  assert.equal(entries.length, 60);
  const { out, ms, inputBytes } = measure(entries, finishedView());
  assert.equal(inputBytes, 16 * MAX);
  assert.equal(count(out, /data-art-preview=/g), 16);
  assert.equal(count(out, /\bdisabled\b/g), 44);
  assert.ok(ms < 5000, `${ms.toFixed(0)}ms`);
  assert.ok(out.length <= 20 * inputBytes, `HTML ${out.length} 文字 / 入力 ${inputBytes} バイト`);
});

// ---- AC-38：外から来た文字の入ったパネル全体 ----

const EVIL_MD = [
  '# <img src=x onerror=alert(1)>',
  '',
  '<a href="javascript:alert(1)">x</a>',
  '',
  '[x](javascript:alert(1)) ![y](https://example.com/a.png) [z](command:workbench.action.reloadWindow)',
  '',
  '<style>body { background: red }</style><div style="color:red" onclick="x()">z</div>',
  '',
  '- <script>alert(2)</script>',
  '',
  '| <img src=x onerror=1> |',
  '|---|',
  '| <iframe src="https://example.com"></iframe> |',
  '',
  '> <a href=x onmouseover=y>q</a>',
  '',
  '`<img src=1 onerror=2>` **<b>** &lt;script&gt;',
].join('\n');

test('D0025-AC-38: 外から来た文字（<img src onerror>・<a href>・<style>・<iframe>・リンク・画像）を成果物に入れても、パネルの HTML 全体で style・on…・src・href を属性に持つタグが、中身の無い成果物のときより増えない。CSP の <meta> も変わらない', () => {
  const evil = [
    ready('evil.md', 'evil', { text: EVIL_MD }),
    ready('evil.txt', 'evil2', { text: EVIL_MD }),
    ready('x" onerror="y.md', 'x" onerror="y', { stage: 'x" onclick="z', stageLabel: 'x" onclick="z', text: EVIL_MD }),
  ];
  const empty = evil.map((e) => ({ ...e, ready: false, text: '', updatedText: '—' }));
  const withContent = renderPanelHtml(viewWith(evil), NONCE, listView(sampleRows()));
  const without = renderPanelHtml(viewWith(empty), NONCE, listView(sampleRows()));
  assert.ok(withContent.includes(escapeHtml('<img src=x onerror=alert(1)>')), '外から来た文字が（文字として）入っている');
  assert.ok(withContent.includes(escapeHtml('<a href="javascript:alert(1)">')), '属性の引用符も文字になっている');
  const before = dangerousTags(without);
  const after = dangerousTags(withContent);
  assert.ok(after <= before, `style・on…・src・href を持つタグ：中身なし ${before} → 中身あり ${after}`);
  const meta = (h: string): string[] => h.match(/<meta http-equiv="Content-Security-Policy"[^>]*>/g) ?? [];
  assert.equal(meta(withContent).length, 1);
  assert.deepEqual(meta(withContent), meta(without), 'CSP の文字は変わらない');
  assert.match(meta(withContent)[0]!, /default-src 'none'; style-src 'nonce-TESTNONCE'; script-src 'nonce-TESTNONCE';/);
});

test('D0025-AC-38: 外から来た文字を入れても、a・img・iframe・style・script の要素は、中身の無いときと同じ数のまま（パネルのスクリプトと CSS の 1 つずつだけ）', () => {
  const evil = [ready('evil.md', 'evil', { text: EVIL_MD }), ready('evil.txt', 'evil2', { text: EVIL_MD })];
  const empty = evil.map((e) => ({ ...e, ready: false, text: '', updatedText: '—' }));
  const tagCount = (out: string, tag: string): number => tagsOf(out).filter((t) => t.tag === tag).length;
  const withContent = renderPanelHtml(viewWith(evil), NONCE);
  const without = renderPanelHtml(viewWith(empty), NONCE);
  assert.ok(withContent.includes(escapeHtml('<iframe src="https://example.com">')), '外から来た文字が（文字として）入っている');
  for (const tag of ['a', 'img', 'iframe', 'object', 'embed', 'link', 'form', 'input']) {
    assert.ok(tagCount(withContent, tag) <= tagCount(without, tag), `<${tag}> が増えない`);
  }
  assert.equal(count(withContent, /<script\b/gi), count(without, /<script\b/gi), '<script> が増えない');
  assert.equal(count(withContent, /<style\b/gi), count(without, /<style\b/gi), '<style> が増えない');
});

// ---- CSS：幅の規則の置き場所（AC-66）と、3 つの帯（AC-67） ----

const mediaWidth = (media: string | null): number | null => {
  const m = media === null ? null : /^@media\s*\(\s*max-width\s*:\s*(\d+)px\s*\)$/.exec(media.trim());
  return m === null ? null : Number(m[1]);
};
const selectorsOf = (rule: CssRule): string[] => rule.selector.split(',').map((s) => s.trim());
function declarationsOf(body: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of body.split(';')) {
    const at = part.indexOf(':');
    if (at <= 0) continue;
    out[part.slice(0, at).trim().toLowerCase()] = part.slice(at + 1).replace(/!important/gi, '').trim();
  }
  return out;
}
/** 幅 width のときに、selector（カンマで並べたものの 1 つと完全に同じ）へ効く宣言。規則の並びの順に重ねる（あとの規則が勝つ）。@media (max-width) 以外の @media は見ない */
function effective(css: string, width: number, selector: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const rule of parseCss(css)) {
    if (rule.keyframes) continue;
    if (rule.media !== null) {
      const w = mediaWidth(rule.media);
      if (w === null || width > w) continue;
    }
    if (selectorsOf(rule).includes(selector)) Object.assign(out, declarationsOf(rule.body));
  }
  return out;
}
const panelCss = (): string => extractCss(renderPanelHtml(runningView(83), NONCE));
const overflowIsAuto = (d: Record<string, string>): boolean => d.overflow === 'auto' || d['overflow-y'] === 'auto' || d.overflow === 'scroll';
/** 0 より大きい長さ（px・rem・em・vh）の数。そうでなければ null（0・auto・変数など） */
const positiveLength = (value: string | undefined): number | null => {
  const m = value === undefined ? null : /^(\d+(?:\.\d+)?)(px|rem|em|vh)$/.exec(value.trim());
  return m !== null && Number(m[1]) > 0 ? Number(m[1]) : null;
};
/** 窓の高さに連なる長さか：`60vh` のような vh（dvh・svh・lvh も）の長さ、または vh を含む min()・max()・clamp()・calc() の式。none・auto・px・% だけは偽 */
const isVh = (value: string | undefined): boolean => {
  const v = value === undefined ? '' : value.trim();
  return /^\d+(?:\.\d+)?(?:vh|dvh|svh|lvh)$/.test(v) || (/^(?:min|max|clamp|calc)\(/.test(v) && /\d(?:\.\d+)?(?:vh|dvh|svh|lvh)(?![\w-])/.test(v));
};
/** 選択子の属性の書き方をそろえる（[aria-pressed="true"]・['true']・=true・[ aria-pressed = "true" ] は同じ意味）。子孫の組み合わせの空白は残す */
const plainSelector = (selector: string): string =>
  selector
    .trim()
    .replace(
      /\[\s*([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s\]]*))\s*\]/g,
      (_all: string, name: string, double: string | undefined, single: string | undefined, bare: string | undefined) => `[${name}=${double ?? single ?? bare ?? ''}]`,
    );
/** 選んだ行の選択子：.art-row[aria-pressed=true]（button の型つきでもよい） */
const PRESSED_ROW = /^(?:button)?\.art-row\[aria-pressed=true\]$/;
/** 空白で分ける（かっこの中の空白では分けない）。grid-template-columns の列の数を数える */
function tracks(value: string | undefined): string[] {
  const out: string[] = [];
  let depth = 0;
  let cur = '';
  for (const c of value ?? '') {
    if (c === '(') depth += 1;
    if (c === ')') depth -= 1;
    if (c === ' ' && depth === 0) {
      if (cur !== '') out.push(cur);
      cur = '';
    } else cur += c;
  }
  if (cur !== '') out.push(cur);
  return out;
}

test('D0025-AC-67: 検査そのもの：帯ごとに規則を重ねる関数は、今の CSS（.detail：1101px 以上は overflow: hidden、801〜1100px は auto、800px 以下は visible）を読み取れる（今のまま通る。守る）', () => {
  const css = panelCss();
  assert.equal(effective(css, 1280, '.detail').overflow, 'hidden');
  assert.equal(effective(css, 1000, '.detail').overflow, 'auto');
  assert.equal(effective(css, 700, '.detail').overflow, 'visible');
  assert.equal(effective(css, 1280, '.app').height, '100vh');
  assert.equal(effective(css, 700, '.app').height, 'auto');
  assert.equal(tracks(effective(css, 1280, '.app-body')['grid-template-columns']).length, 2);
  assert.equal(tracks(effective(css, 700, '.app-body')['grid-template-columns']).length, 1);
  assert.deepEqual(tracks('clamp(200px, 28%, 300px) minmax(0, 1fr)'), ['clamp(200px, 28%, 300px)', 'minmax(0, 1fr)']);
  assert.equal(effective('.a { x: 1 } @media (max-width: 800px) { .a { x: 2 } } .a { y: 3 }', 700, '.a').x, '2');
  assert.equal(effective('.a { x: 1 } @media (max-width: 800px) { .a { x: 2 } } .a { x: 3 }', 700, '.a').x, '3', 'あとの規則が勝つ');
  assert.equal(effective('.a, .b { x: 1 } @media (max-width: 800px) { .b { x: 2 } }', 1000, '.b').x, '1', '800px 以下の規則は 1000px には効かない');
});

test('D0025-AC-67: 検査そのもの：選んだ行の選択子は引用符の有無・空白・button の型つきの書き方を同じに読み、子孫の組み合わせ・別の値・値なしは同じにしない。isVh は vh の長さと、vh を含む min()・clamp()・calc() の式を受け、none・px・% だけは受けない（今のまま通る。守る）', () => {
  for (const s of ['.art-row[aria-pressed="true"]', ".art-row[aria-pressed='true']", '.art-row[aria-pressed=true]', '.art-row[ aria-pressed = "true" ]', 'button.art-row[aria-pressed="true"]']) {
    assert.ok(PRESSED_ROW.test(plainSelector(s)), `受ける：${s}`);
  }
  for (const s of ['.art-row [aria-pressed="true"]', '.art-row[aria-pressed="false"]', '.art-row', '.art-row[aria-pressed]', '.art-list .art-row[aria-pressed="true"]', '.art-row[aria-pressed="true"] .art-name']) {
    assert.ok(!PRESSED_ROW.test(plainSelector(s)), `受けない：${s}`);
  }
  for (const v of ['60vh', '30.5vh', '70dvh', 'min(60vh, 480px)', 'calc(100vh - 120px)', 'clamp(120px, 40vh, 480px)', ' 60vh ']) assert.ok(isVh(v), `受ける：${v}`);
  for (const v of ['none', 'auto', '480px', '60%', 'min(60%, 480px)', 'calc(100% - 120px)', 'var(--x)', '', undefined]) assert.ok(!isVh(v), `受けない：${String(v)}`);
});

test('D0025-AC-66: 成果物の欄の狭い幅の規則は、SHELL_STYLE の既存の 2 つの @media（1100px・800px）の中にある（1100px：成果物の一覧と枠。800px：欄・一覧・枠）', () => {
  const rules = parseCss(SHELL_STYLE);
  const within = (width: number): string[] => rules.filter((r) => mediaWidth(r.media) === width).flatMap(selectorsOf);
  const s1100 = within(1100);
  const s800 = within(800);
  for (const sel of ['.art-list', '.art-body']) assert.ok(s1100.includes(sel), `1100px の @media の中に ${sel}`);
  for (const sel of ['.art', '.art-list', '.art-body']) assert.ok(s800.includes(sel), `800px の @media の中に ${sel}`);
});

test('D0025-AC-66: ARTIFACTS_STYLE（成果物用の CSS）に @media (max-width を含めない。パネルの全 CSS で max-width の @media は 800px と 1100px が各ちょうど 1 つのまま', async () => {
  const { ARTIFACTS_STYLE } = await ah();
  assert.equal(typeof ARTIFACTS_STYLE, 'string');
  assert.doesNotMatch(ARTIFACTS_STYLE, /@media[^{]*max-width/);
  const css = panelCss();
  assert.equal(count(css, /@media\s*\(\s*max-width\s*:\s*800px\s*\)/g), 1);
  assert.equal(count(css, /@media\s*\(\s*max-width\s*:\s*1100px\s*\)/g), 1);
  assert.equal(count(css, /@media[^{]*max-width/g), 2, 'max-width の @media はこの 2 つだけ');
});

test('D0025-AC-66: ARTIFACTS_STYLE はパネルの CSS に SHELL_STYLE より前に入る（あとの @media の規則が基本の規則を上書きできる）', async () => {
  const { ARTIFACTS_STYLE } = await ah();
  const css = panelCss();
  const at = css.indexOf(ARTIFACTS_STYLE);
  assert.ok(at >= 0, 'ARTIFACTS_STYLE がそのまま入っている');
  assert.ok(at < css.indexOf(SHELL_STYLE), 'SHELL_STYLE より前');
});

test('D0025-AC-10: 古い成果物のボタンの CSS（.artifacts・.artifact）はパネルの CSS に残らない（成果物の一覧の行は .art-row になる）', () => {
  const stale = parseCss(panelCss()).filter((r) => selectorsOf(r).some((s) => /(^|[\s>+~])\.artifacts?(?![\w-])/.test(s)));
  assert.deepEqual(stale.map((r) => r.selector), []);
});

test('D0025-AC-67: 1101px 以上（左に成果物の一覧・右にプレビュー）：成果物の一覧とプレビューの枠が各自 overflow: auto を持ち、プレビューの枠に min-height（0 に潰れない）がある', () => {
  const css = panelCss();
  const art = effective(css, 1280, '.art');
  assert.equal(tracks(art['grid-template-columns']).length, 2, '2 列');
  const list = effective(css, 1280, '.art-list');
  const body = effective(css, 1280, '.art-body');
  assert.ok(overflowIsAuto(list), `.art-list の overflow: ${JSON.stringify(list)}`);
  assert.ok(overflowIsAuto(body), `.art-body の overflow: ${JSON.stringify(body)}`);
  assert.ok(positiveLength(body['min-height']) !== null, `.art-body の min-height は 0 より大きい長さ（${body['min-height']}）`);
});

for (const [label, width, columns] of [['801〜1100px（左右のまま）', 1000, 2], ['801px（左右のまま）', 801, 2], ['1100px（左右のまま）', 1100, 2], ['800px 以下（1 列で成果物の一覧が上）', 800, 1], ['狭い 500px（1 列）', 500, 1]] as const) {
  test(`D0025-AC-67: ${label}：成果物の一覧とプレビューの枠が、max-height（vh）と overflow: auto を持つ。列の数は ${columns}`, () => {
    const css = panelCss();
    assert.equal(tracks(effective(css, width, '.art')['grid-template-columns']).length, columns);
    for (const sel of ['.art-list', '.art-body']) {
      const d = effective(css, width, sel);
      assert.ok(isVh(d['max-height']), `${sel} の max-height は vh（${d['max-height']}）`);
      assert.ok(overflowIsAuto(d), `${sel} の overflow: ${JSON.stringify(d)}`);
    }
  });
}

test('D0025-AC-62: 成果物の一覧の枠（.art-list）は position: relative（選んだ行へ寄せる計算は、行の offsetTop が枠からの位置であることに頼る）。どの幅でも変わらない', () => {
  const css = panelCss();
  for (const width of [1280, 1000, 700]) assert.equal(effective(css, width, '.art-list').position, 'relative', `${width}px`);
});

// ---- AC-68：広い中身・長い名前 ----

test('D0025-AC-68: 表（.md-table）とコードブロック（.md の pre）はプレビューの枠の中で横にスクロールする（overflow-x: auto）。長い 1 行の文章は折り返す（.md の overflow-wrap: anywhere）', () => {
  const css = panelCss();
  const rules = parseCss(css).filter((r) => !r.keyframes && mediaWidth(r.media) === null && r.media === null);
  const decl = (pick: (sel: string) => boolean): Record<string, string>[] => rules.filter((r) => selectorsOf(r).some(pick)).map((r) => declarationsOf(r.body));
  const pre = decl((s) => /(^|[\s>])pre$/.test(s) && /\.(md|art-body)\b/.test(s));
  assert.ok(pre.some((d) => d['overflow-x'] === 'auto' || d.overflow === 'auto'), '.md の pre が横にスクロールする');
  const table = decl((s) => /\.md-table$/.test(s));
  assert.ok(table.some((d) => d['overflow-x'] === 'auto' || d.overflow === 'auto'), '.md-table が横にスクロールする');
  assert.equal(effective(css, 1280, '.md')['overflow-wrap'], 'anywhere', '.md は折り返す');
});

test('D0025-AC-68: 長い名前（空白の無い文字）が行・見出しからあふれない：.art-name・.art-file・.art-stage・.art-title が min-width: 0 と overflow-wrap: anywhere、.art-head が flex-wrap: wrap。ページに横スクロールを出す元の幅（min-width）を持たせない', () => {
  const css = panelCss();
  for (const sel of ['.art-name', '.art-file', '.art-stage', '.art-title']) {
    const d = effective(css, 1280, sel);
    assert.ok(d['min-width'] === '0' || d['min-width'] === '0px', `${sel} の min-width: 0（${d['min-width']}）`);
    assert.equal(d['overflow-wrap'], 'anywhere', `${sel} は折り返す`);
  }
  assert.equal(effective(css, 1280, '.art-head')['flex-wrap'], 'wrap');
  for (const sel of ['.art', '.art-previews', '.art-preview', '.art-body']) {
    const d = effective(css, 1280, sel);
    assert.ok(d['min-width'] === '0' || d['min-width'] === '0px', `${sel} は縮められる（min-width: 0）`);
  }
});

// ---- AC-08・AC-69：色と動き ----

const COLOR_PROP = /^(color|background(-color)?|border(-(top|right|bottom|left))?(-color)?|outline(-color)?|box-shadow|fill|stroke|caret-color|accent-color|text-decoration-color)$/;
const NEUTRAL = new Set(['transparent', 'inherit', 'initial', 'unset', 'none', 'currentcolor', 'solid', 'dashed', 'dotted', 'double', 'thin', 'medium', 'thick', 'hidden', 'auto']);
/** 色に使う宣言の値のうち、var(--vscode-…) でない色（16 進・rgb()・色の名前など）。長さ・線の種類は見ない */
function plainColors(css: string): string[] {
  const bad: string[] = [];
  for (const rule of parseCss(css)) {
    if (rule.keyframes) continue;
    for (const [prop, value] of Object.entries(declarationsOf(rule.body))) {
      if (!COLOR_PROP.test(prop)) continue;
      let rest = value;
      for (let i = 0; i < 4; i++) rest = rest.replace(/var\([^()]*(?:\([^()]*\)[^()]*)*\)/g, ' ');
      for (const token of rest.split(/[\s,]+/).filter((t) => t !== '')) {
        if (NEUTRAL.has(token.toLowerCase()) || /^-?[\d.]+(px|em|rem|%|vh|vw)?$/.test(token)) continue;
        bad.push(`${rule.selector} { ${prop}: ${value} } の ${token}`);
      }
    }
  }
  return bad;
}
const usedVars = (css: string): string[] => [...new Set(Array.from(css.matchAll(/var\(\s*(--[\w-]+)/g), (m) => m[1]!))];
const definedVars = (theme: string): Set<string> => new Set(Array.from(theme.matchAll(/(--[\w-]+)\s*:/g), (m) => m[1]!));
/** 成果物の欄の CSS：ARTIFACTS_STYLE と、SHELL_STYLE の中の .art… の規則 */
async function artCss(): Promise<string> {
  const { ARTIFACTS_STYLE } = await ah();
  const fromShell = parseCss(SHELL_STYLE)
    .filter((r) => selectorsOf(r).some((s) => /\.art(-|\b)/.test(s)))
    .map((r) => `${r.selector} { ${r.body} }`)
    .join('\n');
  return `${ARTIFACTS_STYLE}\n${fromShell}`;
}

test('D0025-AC-69: 検査そのもの：色の直書きを見つける（#fff・rgb()・色の名前）。var(--vscode-…)・transparent・長さ・線の種類は見逃す', () => {
  assert.deepEqual(plainColors('.a { color: var(--vscode-foreground); border: 1px solid var(--vscode-panel-border); background: transparent; border-color: var(--vscode-a, var(--vscode-b)) }'), []);
  assert.equal(plainColors('.a { color: #fff }').length, 1);
  assert.ok(plainColors('.a { background: rgba(0, 0, 0, 0.5) }').length >= 1);
  assert.equal(plainColors('.a { border: 1px dashed red }').length, 1);
  assert.equal(plainColors('.a { border: 1px solid var(--vscode-x); outline: 2px solid blue }').length, 1);
});

test('D0025-AC-69: 成果物の欄の色はすべて var(--vscode-*)（直書きが無い）で、使う変数は確認用ページの THEMES（明るい・暗い）が決めている。style= は使わない', async () => {
  const css = await artCss();
  assert.match(css, /var\(--vscode-/);
  assert.deepEqual(plainColors(css), []);
  assert.doesNotMatch(css, /#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/);
  assert.doesNotMatch(css, /url\(\s*["']?https?:|@import/i, '外部の読み込みをしない');
  const vars = usedVars(css);
  assert.ok(vars.length > 0);
  for (const theme of ['light', 'dark'] as const) {
    const defined = definedVars(THEMES[theme]);
    assert.deepEqual(vars.filter((v) => !defined.has(v) || !v.startsWith('--vscode-')), [], `${theme}: THEMES に無い色`);
  }
});

test('D0025-AC-69: 動き（animation・@keyframes）を足さない。足すなら prefers-reduced-motion: no-preference の中だけ', async () => {
  const { ARTIFACTS_STYLE } = await ah();
  assert.deepEqual(motionOutsideNoPreference(ARTIFACTS_STYLE), []);
  assert.deepEqual(motionOutsideNoPreference(await artCss()), []);
  assert.deepEqual(motionOutsideNoPreference(panelCss()), [], 'パネル全体でも、動きは no-preference の中だけ');
});

test('D0025-AC-08: 選んだ行の背景と枠は CSS の [aria-pressed="true"] で決まり（.art-row[aria-pressed="true"]）、色は var(--vscode-*) だけ。背景は選択行の色、枠は focusBorder', async () => {
  const { ARTIFACTS_STYLE } = await ah();
  const rule = parseCss(ARTIFACTS_STYLE).find((r) => selectorsOf(r).some((s) => PRESSED_ROW.test(plainSelector(s))));
  assert.ok(rule, '.art-row[aria-pressed="true"] の規則がある（引用符の有無・button の型つきの書き方でもよい）');
  const d = declarationsOf(rule.body);
  assert.ok(d.background !== undefined || d['background-color'] !== undefined, '背景を決める');
  assert.ok(d['border-color'] !== undefined || d.border !== undefined, '枠を決める');
  assert.match(d.background ?? d['background-color']!, /var\(--vscode-list-activeSelectionBackground/);
  assert.match(d['border-color'] ?? d.border!, /var\(--vscode-focusBorder/);
  assert.deepEqual(plainColors(`${rule.selector} { ${rule.body} }`), []);
  const base = effective(ARTIFACTS_STYLE, 1280, '.art-row');
  assert.ok(base.cursor === 'pointer', '行は押せる見た目');
});

test('D0025-AC-69: 引用の線・表の罫線・「まだない」行の破線は読める色（--vscode-descriptionForeground）で、--vscode-panel-border は成果物の一覧と枠の外周（.art-list・.art-body）だけに使う', async () => {
  const { ARTIFACTS_STYLE } = await ah();
  const rules = parseCss(ARTIFACTS_STYLE).filter((r) => !r.keyframes);
  const using = (name: string) => rules.filter((r) => r.body.includes(name));
  for (const r of using('--vscode-panel-border')) {
    assert.ok(selectorsOf(r).every((s) => s === '.art-list' || s === '.art-body'), `panel-border を使う規則は一覧と枠の外周だけ：${r.selector}`);
  }
  assert.ok(using('--vscode-panel-border').length >= 1, '一覧の外周は panel-border');
  const desc = using('--vscode-descriptionForeground');
  assert.ok(desc.some((r) => selectorsOf(r).some((s) => /blockquote/.test(s)) && /border-left/.test(r.body)), '引用の線');
  assert.ok(desc.some((r) => selectorsOf(r).some((s) => /(^|\s)(th|td)\b|\bth\b|\btd\b/.test(s)) && /border/.test(r.body)), '表の罫線');
  assert.ok(desc.some((r) => selectorsOf(r).some((s) => /\.is-missing/.test(s)) && /dashed/.test(r.body) && /border/.test(r.body)), '「まだない」行の破線');
});

test('D0025-AC-69: キーボードの焦点：.art-row:focus-visible と .art-body:focus-visible に焦点の輪（outline）があり、色は --vscode-focusBorder', async () => {
  const { ARTIFACTS_STYLE } = await ah();
  const rule = parseCss(ARTIFACTS_STYLE).find((r) => selectorsOf(r).includes('.art-row:focus-visible') && selectorsOf(r).includes('.art-body:focus-visible'));
  const separate = ['.art-row:focus-visible', '.art-body:focus-visible'].map((sel) => parseCss(ARTIFACTS_STYLE).find((r) => selectorsOf(r).includes(sel)));
  for (const r of rule === undefined ? separate : [rule]) {
    assert.ok(r, '焦点の規則がある');
    assert.match(r.body, /outline\s*:[^;]*var\(--vscode-focusBorder/);
  }
});

// ---- AC-70：成果物のタブに図・出力・時系列・理由は入らない ----

test('D0025-AC-70: 「成果物」のタブパネルに、図（.flow）・出力（.terminal）・時系列（gantt-svg）・理由（data-reasons）は入らない（図と出力のタブにだけある）', () => {
  const { diagram, artifacts, usage } = panelsByName(renderViewBody(viewWith(dev(), showcaseView()), listView(sampleRows())));
  for (const p of [artifacts!, usage!]) assert.doesNotMatch(p, /class="flow"|class="terminal"|gantt-svg|data-reasons/);
  assert.match(diagram!, /class="flow"/, '見本の図は「図と出力」にある（検査が空振りでない）');
  assert.match(diagram!, /data-reasons/);
  assert.match(artifacts!, /class="art\b/, '成果物のタブには成果物の欄が入る');
});

test('D0025-AC-70: 見えるのは選んだタブだけ（成果物のタブパネルは、初めは hidden）。「成果物を開く」ボタンは今までどおり data-open-artifacts で、成果物の一覧の行は data-artifact を持たない', () => {
  const out = renderViewBody(viewWith(dev()), undefined);
  const tags = [...out.matchAll(/<[a-z]+\b[^>]*role="tabpanel"[^>]*>/g)].map((m) => m[0]);
  assert.deepEqual(tags.map((t) => /\bhidden\b/.test(t)), [false, true, true, true]);
  assert.match(out, /<button\b[^>]*data-open-artifacts[^>]*>[\s\S]*?成果物を開く[\s\S]*?<\/button>/);
  const doc = parse(out);
  const rows = doc.querySelectorAll('.art-row');
  assert.equal(rows.length, 7, '成果物の一覧の行（.art-row）が 7 つある');
  for (const r of rows) assert.equal(r.hasAttribute('data-artifact'), false);
});

// ---- 隣の確認（今のまま通る。守る） ----

test('D0025-AC-52: 成果物の中身を入れても、拡張へ送るメッセージの type の一覧（ready・openArtifact・selectRun）は panelScript.ts のままで、HTML に postMessage を足さない（今のまま通る。守る）', () => {
  const out = renderPanelHtml(viewWith(dev()), NONCE, listView(sampleRows()));
  const body = out.replace(/<script\b[\s\S]*?<\/script>/g, '');
  assert.doesNotMatch(body, /postMessage|acquireVsCodeApi/);
});
