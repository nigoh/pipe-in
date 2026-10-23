// 「成果物」タブの中身（成果物の一覧＋選んだ 1 つのプレビュー）の HTML（D0025・view/artifactsHtml.ts の renderArtifacts）。
// 純粋な文字列と、偽の DOM（src/test/fakeDom.ts）に読み込んだ木の検査。パネルの CSS と全体の HTML は artifactsPanel.test.ts、スクリプトの動きは panelScriptArtifacts.test.ts が持つ。
// 新しい部品（view/artifactsHtml.ts）は、テストの中で読み込む（テスト先行のとき、まだ無いあいだも各テストが「モジュールが無い」で落ち、ファイルごと読めずに落ちることが無いようにしたため。
// 前例：domain/runListCounts.test.ts の rl()）。
// 成果物の一覧の項目（domain/artifacts.ts の ArtifactEntry：name・label・stage・stageLabel・ready・text・cut・updatedText）は、手で組み立てて渡す。
// domain の作り（既定の選び・時刻の書き方など）とは切り離して、HTML の部分だけを確かめる。domain は artifactsPreview.test.ts が持つ。
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { PipelineView } from '../domain/pipelineView.ts';
import { FakeDocument, FakeNode } from '../test/fakeDom.ts';
import { findLimitLiterals, withoutComments } from '../test/sourceText.ts';
import { escapeHtml } from './escape.ts';

/** 使う分だけの型。テスト先行のとき artifactsHtml.ts がまだ無くても型検査が通るよう、読み込みの指定を定数でない形にして型を与えた */
interface ArtifactsHtmlMod {
  renderArtifacts(view: Pick<PipelineView, 'artifacts' | 'runningStage' | 'pendingReview'>): string;
  CUT_NOTICE: string;
  isMarkdownName(name: string): boolean;
  displayName(name: string): string;
}
const ah = (): Promise<ArtifactsHtmlMod> => import(String('./artifactsHtml.ts')) as Promise<ArtifactsHtmlMod>;
const HERE = path.dirname(fileURLToPath(import.meta.url));

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
interface Live {
  running?: string | null;
  pending?: string | null;
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
const missing = (name: string, label: string = name, over: Partial<Entry> = {}): Entry => ({
  ...ready(name, label),
  ready: false,
  text: '',
  updatedText: '—',
  ...over,
});

/** 開発フローの 7 つ：[ファイル名, 名前（label）, 作った段, その表示名] */
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

/** 開発フローの 7 つ。readyNames にあるものが「ある」、ほかは「まだない」。over は名前ごとの上書き */
function dev(readyNames: readonly string[] = DEV_NAMES, over: Record<string, Partial<Entry>> = {}): Entry[] {
  return DEV.map(([name, label, stage, stageLabel]) =>
    (readyNames.includes(name) ? ready : missing)(name, label, { stage, stageLabel, ...(over[name] ?? {}) }),
  );
}

/** パイプ：依頼メモ・各段の output（名前は段の表示名）・まとめ。03 だけ「まだない」 */
const PIPE: Entry[] = [
  ready('00_input.md', '依頼メモ'),
  ready('01_survey.md', 'ソースの調査', { stage: 'survey', stageLabel: 'ソースの調査' }),
  ready('02_diagrams.md', '図を描く', { stage: 'draw', stageLabel: '図を描く' }),
  missing('03_verify.md', '図とソースの突き合わせ', { stage: 'verify', stageLabel: '図とソースの突き合わせ' }),
  ready('99_summary.md', 'まとめ'),
];

async function html(entries: Entry[], live: Live = {}): Promise<string> {
  const { renderArtifacts } = await ah();
  return renderArtifacts({
    artifacts: entries as unknown as PipelineView['artifacts'],
    runningStage: live.running ?? null,
    pendingReview: live.pending == null ? null : { stage: live.pending, label: live.pending, doc: 'docs/pipeline/x.md' },
  });
}

// ---- 木の読み取り（偽の DOM に読み込む。属性の順や空白に左右されない） ----

function parse(out: string): FakeDocument {
  const doc = new FakeDocument();
  doc.innerHTML = out;
  return doc;
}
const elementsOf = (node: FakeNode): FakeNode[] => node.children.filter((c): c is FakeNode => c instanceof FakeNode);
/** 木のすべての要素（文書の順） */
function allElements(node: FakeNode): FakeNode[] {
  return elementsOf(node).flatMap((c) => [c, ...allElements(c)]);
}
/** 子孫のうち最初の 1 つ（無ければテストの失敗） */
function one(node: FakeNode, selector: string): FakeNode {
  const found = node.querySelector(selector);
  assert.ok(found, `${selector} がある`);
  return found;
}
const partText = (node: FakeNode, selector: string): string => one(node, selector).textContent;
/** 成果物の一覧の行（「まだない」行を含む） */
const allRows = (doc: FakeDocument): FakeNode[] => doc.querySelectorAll('.art-row');
const rowByFile = (doc: FakeDocument, file: string): FakeNode => {
  const found = allRows(doc).find((r) => r.querySelector('.art-file')?.textContent === file);
  assert.ok(found, `${file} の行がある`);
  return found;
};
/** 押せる行（選べる行）で aria-pressed="true" のもの */
const pressed = (doc: FakeDocument): string[] =>
  doc
    .querySelectorAll('button[data-art-pick]')
    .filter((b) => b.getAttribute('aria-pressed') === 'true')
    .map((b) => b.getAttribute('data-art-pick')!);
const previewsOf = (doc: FakeDocument): FakeNode[] => doc.querySelectorAll('[data-art-preview]');
const previewByName = (doc: FakeDocument, name: string): FakeNode => {
  const found = previewsOf(doc).find((p) => p.getAttribute('data-art-preview') === name);
  assert.ok(found, `${name} のプレビューがある`);
  return found;
};
/** 見える（hidden を持たない）プレビューの名前 */
const shown = (doc: FakeDocument): string[] =>
  previewsOf(doc)
    .filter((p) => !p.hasAttribute('hidden'))
    .map((p) => p.getAttribute('data-art-preview')!);
const countOf = (text: string, re: RegExp): number => (text.match(re) ?? []).length;

// ---- AC-01：成果物の一覧 ----

test('D0025-AC-01: 開発フロー（7 つ全部ある）では、7 行が 要件メモ・要件定義書・設計書・テスト先行の記録・実装の記録・テスト報告・まとめ の順に出て、行ごとに名前とファイル名が読める', async () => {
  const doc = parse(await html(dev()));
  const rows = allRows(doc);
  assert.equal(rows.length, 7);
  assert.deepEqual(rows.map((r) => partText(r, '.art-name')), ['要件メモ', '要件定義書', '設計書', 'テスト先行の記録', '実装の記録', 'テスト報告', 'まとめ']);
  assert.deepEqual(rows.map((r) => partText(r, '.art-file')), DEV_NAMES);
  assert.deepEqual(doc.querySelectorAll('button[data-art-pick]').map((b) => b.getAttribute('data-art-pick')), DEV_NAMES, '行は押せるボタンで、順も同じ');
});

test('D0025-AC-01: 「まだない」ものが混じっても、行は 7 つのまま同じ順に出る（行を減らさない）', async () => {
  const doc = parse(await html(dev(['00_input.md', '01_requirements.md'])));
  assert.deepEqual(allRows(doc).map((r) => partText(r, '.art-file')), DEV_NAMES);
});

test('D0025-AC-01: パイプは 依頼メモ・各段の output（名前は段の表示名）・まとめ の順で、項目の並びのまま行になる', async () => {
  const doc = parse(await html(PIPE));
  const rows = allRows(doc);
  assert.deepEqual(rows.map((r) => partText(r, '.art-name')), ['依頼メモ', 'ソースの調査', '図を描く', '図とソースの突き合わせ', 'まとめ']);
  assert.deepEqual(rows.map((r) => partText(r, '.art-file')), ['00_input.md', '01_survey.md', '02_diagrams.md', '03_verify.md', '99_summary.md']);
});

test('D0025-AC-01: 項目が 1 つも無くても例外を出さず、「まだ成果物がありません」だけが出る', async () => {
  const doc = parse(await html([]));
  assert.equal(allRows(doc).length, 0);
  assert.equal(partText(doc, '.art-empty').trim(), 'まだ成果物がありません');
});

// ---- AC-02・AC-03・AC-04・AC-05：作った段と時刻の欄 ----

test('D0025-AC-02: 行の「作った段」の欄に、項目の作った段の表示名が出る。依頼メモ・まとめ（段が無い）は「—」', async () => {
  const doc = parse(await html(dev()));
  assert.deepEqual(
    allRows(doc).map((r) => partText(r, '.art-stage')),
    DEV.map((d) => d[3] ?? '—'),
  );
  const pipe = parse(await html(PIPE));
  assert.deepEqual(allRows(pipe).map((r) => partText(r, '.art-stage')), ['—', 'ソースの調査', '図を描く', '図とソースの突き合わせ', '—']);
});

test('D0025-AC-03: 作った段は「まだない」行にも出る。段が引けない項目（stage が null）は「—」', async () => {
  const doc = parse(await html(dev(['00_input.md'])));
  assert.equal(partText(rowByFile(doc, '02_design.md'), '.art-stage'), '設計');
  assert.equal(partText(rowByFile(doc, '05_test_report.md'), '.art-stage'), '検証');
  assert.equal(partText(rowByFile(doc, '99_summary.md'), '.art-stage'), '—');
});

test('D0025-AC-04: 行の「時刻」の欄に、項目の updatedText（MM/DD HH:mm）がそのまま出る', async () => {
  const doc = parse(await html(dev(DEV_NAMES, { '00_input.md': { updatedText: '10/17 10:05' }, '01_requirements.md': { updatedText: '11/01 08:30' } })));
  assert.equal(partText(rowByFile(doc, '00_input.md'), '.art-time'), '10/17 10:05');
  assert.equal(partText(rowByFile(doc, '01_requirements.md'), '.art-time'), '11/01 08:30');
});

test('D0025-AC-05: 時刻が読めない項目（updatedText が「—」）でも、行は「—」を出し、プレビューの中身は出る', async () => {
  const doc = parse(await html(dev(DEV_NAMES, { '02_design.md': { updatedText: '—', text: '設計の本文' } }), { running: 'design' }));
  assert.equal(partText(rowByFile(doc, '02_design.md'), '.art-time'), '—');
  assert.match(partText(previewByName(doc, '02_design.md'), '.art-body'), /設計の本文/);
});

// ---- AC-06：「まだない」行 ----

test('D0025-AC-06: 「まだない」行は disabled のボタンで、薄い見た目のクラス（is-missing）が付き、「まだない」の文字が行の中に見える。名前・ファイル名・作った段が読め、時刻の欄は「—」', async () => {
  const doc = parse(await html(dev(['00_input.md', '01_requirements.md'])));
  const row = rowByFile(doc, '02_design.md');
  assert.equal(row.tagName, 'button');
  assert.ok(row.disabled, 'disabled');
  assert.ok(row.classList.contains('art-row') && row.classList.contains('is-missing'));
  assert.equal(partText(row, '.art-missing'), 'まだない');
  assert.match(row.textContent, /まだない/, '薄い見た目だけに頼らず、文字が見える');
  assert.equal(partText(row, '.art-name'), '設計書');
  assert.equal(partText(row, '.art-stage'), '設計');
  assert.equal(partText(row, '.art-time'), '—');
});

test('D0025-AC-06: 「ある」行は disabled でなく、is-missing も「まだない」の文字も持たない', async () => {
  const doc = parse(await html(dev(['00_input.md', '01_requirements.md'])));
  const row = rowByFile(doc, '01_requirements.md');
  assert.ok(!row.disabled);
  assert.ok(!row.classList.contains('is-missing'));
  assert.equal(row.querySelector('.art-missing'), null);
  assert.doesNotMatch(row.textContent, /まだない/);
});

test('D0025-AC-06: disabled の語は「まだない」行に 1 回ずつだけ出る（クラス名・属性に disabled の語を増やさない。panelHtmlEdge.test.ts が本体の disabled の語を数える）', async () => {
  const out = await html(dev(['00_input.md', '01_requirements.md', '02_design.md']));
  assert.equal(countOf(out, /\bdisabled\b/g), 4, '「まだない」が 4 行');
  const none = await html(dev());
  assert.equal(countOf(none, /\bdisabled\b/g), 0, '全部あれば disabled は無い');
});

// ---- AC-08・AC-11・AC-12・AC-13：選んだ行と既定 ----

test('D0025-AC-08: 押せる行のうち aria-pressed="true" は選んだ 1 つだけで、ほかの「ある」行は "false"', async () => {
  const doc = parse(await html(dev(), { running: 'design' }));
  const pickable = doc.querySelectorAll('button[data-art-pick]').filter((b) => !b.disabled);
  assert.equal(pickable.length, 7);
  assert.deepEqual(pressed(doc), ['02_design.md']);
  for (const b of pickable) assert.ok(['true', 'false'].includes(b.getAttribute('aria-pressed')!), '値は true か false');
  assert.equal(pickable.filter((b) => b.getAttribute('aria-pressed') === 'false').length, 6);
});

const DEFAULT_CASES: readonly [string, string, string[], Live, string][] = [
  ['AC-11', '動いている段（設計）の成果物がある', DEV_NAMES, { running: 'design' }, '02_design.md'],
  ['AC-11', '差し戻しの 2 回目で動いている段が実装', DEV_NAMES, { running: 'implement' }, '04_implementation.md'],
  ['AC-12', '動いている段が無く、確認待ちの段（要件定義）の成果物がある', DEV_NAMES, { pending: 'requirements' }, '01_requirements.md'],
  ['AC-12', '動いている段が無く、確認待ちの段がテスト先行', DEV_NAMES.slice(0, 4), { pending: 'red' }, '03_red_tests.md'],
  ['AC-11', '動いている段と確認待ちの段が両方あれば、動いている段が先', DEV_NAMES, { running: 'design', pending: 'requirements' }, '02_design.md'],
  ['AC-13', 'どちらも無い終わった実行は、一覧の順で最後の「ある」（まとめ）', DEV_NAMES, {}, '99_summary.md'],
  ['AC-13', 'どちらも無く、まとめがまだ無ければ、その前の最後の「ある」', DEV_NAMES.slice(0, 3), {}, '02_design.md'],
  ['AC-13', '設計が動き始めたばかりで 02 がまだ無いときは、一覧の順で最後の「ある」（要件定義書）', ['00_input.md', '01_requirements.md'], { running: 'design' }, '01_requirements.md'],
  ['AC-13', '動いている段の名前が項目に無いときは、最後の「ある」', DEV_NAMES, { running: 'no-such-stage' }, '99_summary.md'],
  // 本番の合成（renderArtifacts が 動いている段 ?? 確認待ちの段 から既定を決める所）で、確認待ちの段を見る・見ないの境目を固定する
  [
    'AC-13',
    '動いている段（設計）の成果物がまだ無く、確認待ちの段（要件定義）の成果物は「ある」ときは、確認待ちを見ず、一覧の順で最後の「ある」（試す先を動いている段 → 確認待ちの段の順にしない）',
    ['00_input.md', '01_requirements.md', '03_red_tests.md'],
    { running: 'design', pending: 'requirements' },
    '03_red_tests.md',
  ],
  ['AC-13', '動いている段が無く、確認待ちの段（設計）の成果物がまだ無いときは、一覧の順で最後の「ある」', ['00_input.md', '01_requirements.md'], { pending: 'design' }, '01_requirements.md'],
  ['AC-13', '動いている段が無く、確認待ちの段の名前が項目に無いときは、最後の「ある」', DEV_NAMES, { pending: 'no-such-stage' }, '99_summary.md'],
];
for (const [ac, label, readyNames, live, expected] of DEFAULT_CASES) {
  test(`D0025-${ac}: ${label}（既定の行が aria-pressed="true"、data-art-default もその名前）`, async () => {
    const doc = parse(await html(dev(readyNames), live));
    assert.deepEqual(pressed(doc), [expected]);
    assert.equal(one(doc, '.art').getAttribute('data-art-default'), expected);
  });
}

test('D0025-AC-11: パイプは、動いている段の output（段の名前で引く）が既定になる', async () => {
  const doc = parse(await html(PIPE, { running: 'draw' }));
  assert.deepEqual(pressed(doc), ['02_diagrams.md']);
  const none = parse(await html(PIPE, { running: 'verify' }));
  assert.deepEqual(pressed(none), ['99_summary.md'], '動いている段の成果物が「まだない」ので最後の「ある」');
});

// ---- AC-14：「ある」が 1 つも無い ----

test('D0025-AC-14: 「ある」成果物が 1 つも無いとき、aria-pressed="true" の行は無く、プレビューの場所に「まだ成果物がありません」が出る（プレビューも data-art-default も無い）', async () => {
  const doc = parse(await html(dev([]), { running: 'requirements' }));
  assert.deepEqual(pressed(doc), []);
  assert.equal(doc.querySelectorAll('[aria-pressed="true"]').length, 0);
  assert.equal(partText(doc, '.art-previews').trim(), 'まだ成果物がありません');
  assert.equal(partText(doc, '.art-empty').trim(), 'まだ成果物がありません');
  assert.equal(previewsOf(doc).length, 0);
  assert.equal(one(doc, '.art').getAttribute('data-art-default'), null);
  assert.equal(allRows(doc).length, 7, '行は「まだない」で並ぶ');
  assert.ok(allRows(doc).every((r) => r.disabled));
});

test('D0025-AC-14: 「ある」成果物が 1 つでもあれば、「まだ成果物がありません」は出ない', async () => {
  const doc = parse(await html(dev(['00_input.md'])));
  assert.equal(doc.querySelector('.art-empty'), null);
  assert.doesNotMatch(await html(dev(['00_input.md'])), /まだ成果物がありません/);
});

// ---- AC-10・AC-16・AC-17：行とプレビューの作り ----

test('D0025-AC-10: 成果物の一覧の行のボタンは data-artifact を持たない（行を押しても openArtifact は送られない）。data-artifact を持つのはプレビューの「エディタで開く」だけ', async () => {
  const doc = parse(await html(dev(['00_input.md', '01_requirements.md', '02_design.md']), { running: 'design' }));
  for (const row of allRows(doc)) assert.equal(row.hasAttribute('data-artifact'), false, '行は data-artifact を持たない');
  const withArtifact = doc.querySelectorAll('[data-artifact]');
  assert.deepEqual(withArtifact.map((n) => n.getAttribute('data-artifact')), ['00_input.md', '01_requirements.md', '02_design.md'], '「ある」成果物ごとに 1 つ');
  for (const n of withArtifact) {
    assert.equal(n.tagName, 'button');
    assert.ok(n.closest('[data-art-preview]') !== null, 'プレビューの見出しの中');
    assert.ok(n.closest('.art-list') === null, '成果物の一覧の中には無い');
  }
});

test('D0025-AC-16: プレビューは「ある」成果物ごとに 1 つ（見出し：名前・ファイル名・「エディタで開く」と、中身の枠）。「まだない」成果物のプレビューは作らない', async () => {
  const doc = parse(await html(dev(['00_input.md', '01_requirements.md', '02_design.md']), { running: 'design' }));
  assert.deepEqual(previewsOf(doc).map((p) => p.getAttribute('data-art-preview')), ['00_input.md', '01_requirements.md', '02_design.md']);
  for (const [name, label] of [['00_input.md', '要件メモ'], ['01_requirements.md', '要件定義書'], ['02_design.md', '設計書']] as const) {
    const p = previewByName(doc, name);
    const head = one(p, '.art-head');
    assert.equal(partText(head, '.art-title'), label);
    assert.equal(partText(head, '.art-file'), name);
    const open = one(head, 'button[data-artifact]');
    assert.equal(open.getAttribute('data-artifact'), name);
    assert.equal(open.textContent.trim(), 'エディタで開く');
    const body = one(p, '.art-body');
    assert.ok(body.closest('.art-head') === null, '中身の枠は見出しの外');
  }
  for (const name of ['03_red_tests.md', '04_implementation.md', '05_test_report.md', '99_summary.md']) {
    assert.equal(previewsOf(doc).some((p) => p.getAttribute('data-art-preview') === name), false, `${name}（まだない）のプレビューは無い`);
  }
});

test('D0025-AC-16: 見えるのは選んだ 1 つだけ（ほかのプレビューは hidden）', async () => {
  const doc = parse(await html(dev(), { running: 'design' }));
  assert.equal(previewsOf(doc).length, 7);
  assert.deepEqual(shown(doc), ['02_design.md']);
  assert.equal(previewsOf(doc).filter((p) => p.hasAttribute('hidden')).length, 6);
  assert.deepEqual(shown(parse(await html(dev(), { pending: 'requirements' }))), ['01_requirements.md']);
});

test('D0025-AC-52: 「ある」成果物すべてのプレビューが HTML に入る（見えるのは選んだ 1 つだけ）', async () => {
  const doc = parse(await html(PIPE, { running: 'survey' }));
  assert.deepEqual(previewsOf(doc).map((p) => p.getAttribute('data-art-preview')), ['00_input.md', '01_survey.md', '02_diagrams.md', '99_summary.md']);
  assert.deepEqual(shown(doc), ['01_survey.md']);
});

test('D0025-AC-17: 中身の枠は data-scroll="artifact"・tabindex="0"・role="region"・aria-label="<名前>（<ファイル名>）のプレビュー" を持ち、名前つきで覚えられる（data-scroll-name）', async () => {
  const doc = parse(await html(dev(['00_input.md', '01_requirements.md'])));
  for (const [name, label] of [['00_input.md', '要件メモ'], ['01_requirements.md', '要件定義書']] as const) {
    const body = one(previewByName(doc, name), '.art-body');
    assert.equal(body.getAttribute('data-scroll'), 'artifact');
    assert.equal(body.getAttribute('tabindex'), '0');
    assert.equal(body.getAttribute('role'), 'region');
    assert.equal(body.getAttribute('aria-label'), `${label}（${name}）のプレビュー`);
    assert.equal(body.getAttribute('data-scroll-name'), name);
  }
  assert.equal(doc.querySelectorAll('[data-scroll="artifact"]').length, 2, '枠は「ある」成果物ごとに 1 つ');
});

test('D0025-AC-17: 成果物の一覧の枠は data-scroll="artifact-list" と aria-label="成果物の一覧" を持つ', async () => {
  const list = one(parse(await html(dev())), '.art-list');
  assert.equal(list.getAttribute('data-scroll'), 'artifact-list');
  assert.equal(list.getAttribute('aria-label'), '成果物の一覧');
});

test('D0025-AC-61: data-keep の値は名前を含めて 1 つに決まる（行 art-row:<名前>・枠 art-scroll:<名前>・「エディタで開く」 art-open:<名前>）。同じ値は 2 つ無い', async () => {
  const doc = parse(await html(dev(DEV_NAMES.slice(0, 4))));
  for (const name of DEV_NAMES.slice(0, 4)) {
    assert.equal(rowByFile(doc, name).getAttribute('data-keep'), `art-row:${name}`);
    const p = previewByName(doc, name);
    assert.equal(one(p, '.art-body').getAttribute('data-keep'), `art-scroll:${name}`);
    assert.equal(one(p, 'button[data-artifact]').getAttribute('data-keep'), `art-open:${name}`);
  }
  const keeps = doc.querySelectorAll('[data-keep]').map((n) => n.getAttribute('data-keep')!);
  assert.equal(new Set(keeps).size, keeps.length, 'data-keep は 1 つに決まる');
});

// ---- AC-41：切れた成果物のボタンと案内 ----

test('D0025-AC-41: 切れた成果物でも切れていない成果物でも、プレビューの見出しに同じ「エディタで開く」がある。「まだない」成果物には無い', async () => {
  const doc = parse(await html(dev(DEV_NAMES, { '01_requirements.md': { cut: true }, '03_red_tests.md': { ready: false, text: '', updatedText: '—' } }), { running: 'requirements' }));
  for (const name of ['00_input.md', '01_requirements.md', '02_design.md']) {
    const open = one(previewByName(doc, name), 'button[data-artifact]');
    assert.equal(open.getAttribute('data-artifact'), name);
    assert.equal(open.textContent.trim(), 'エディタで開く');
  }
  assert.equal(doc.querySelectorAll('[data-artifact]').some((b) => b.getAttribute('data-artifact') === '03_red_tests.md'), false);
});

test('D0025-AC-40: 「エディタで開く」は data-artifact="<その成果物の名前>"（名前はそのまま）を持つボタンで、type="button"', async () => {
  const name = '01_requirements.md';
  const open = one(previewByName(parse(await html(dev([name]))), name), 'button[data-artifact]');
  assert.equal(open.getAttribute('type'), 'button');
  assert.equal(open.getAttribute('data-artifact'), name);
});

// ---- AC-45：切れた案内 ----

test('D0025-AC-45: 切れた成果物のプレビューの見出しの下（中身の枠の外）に、切れた案内が出る。見出し → 案内 → 枠 の順', async () => {
  const { CUT_NOTICE } = await ah();
  const doc = parse(await html(dev(['01_requirements.md', '02_design.md'], { '01_requirements.md': { cut: true } }), { running: 'requirements' }));
  const cutPreview = previewByName(doc, '01_requirements.md');
  const notice = one(cutPreview, '.art-cut');
  assert.equal(notice.textContent, CUT_NOTICE);
  assert.ok(notice.closest('.art-body') === null, '枠の外');
  assert.ok(notice.closest('.art-head') === null, '見出しの外（見出しの下）');
  const order = elementsOf(cutPreview).map((n) => (n.classList.contains('art-head') ? 'head' : n.classList.contains('art-cut') ? 'cut' : n.classList.contains('art-body') ? 'body' : '?'));
  assert.deepEqual(order, ['head', 'cut', 'body']);
  assert.equal(previewByName(doc, '02_design.md').querySelector('.art-cut'), null, '切れていない成果物には出ない');
  assert.equal(doc.querySelectorAll('.art-cut').length, 1);
});

test('D0025-AC-45: 切れた案内の文は「先頭 256 KiB までを表示しています。続きはエディタで開いてください。」', async () => {
  const { CUT_NOTICE } = await ah();
  assert.equal(CUT_NOTICE, '先頭 256 KiB までを表示しています。続きはエディタで開いてください。');
});

test('D0025-AC-45: 切れた案内の「256」は、上限の定数（ARTIFACT_MAX_BYTES）の KiB から作る（1 か所の定数）', async () => {
  const { CUT_NOTICE } = await ah();
  const { ARTIFACT_MAX_BYTES } = (await import('../domain/artifacts.ts')) as unknown as Record<string, unknown>;
  assert.equal(typeof ARTIFACT_MAX_BYTES, 'number', 'domain/artifacts.ts が上限の定数を持つ');
  assert.equal(CUT_NOTICE, `先頭 ${(ARTIFACT_MAX_BYTES as number) / 1024} KiB までを表示しています。続きはエディタで開いてください。`);
  const code = withoutComments(readFileSync(path.join(HERE, 'artifactsHtml.ts'), 'utf8'));
  assert.match(code, /\bARTIFACT_MAX_BYTES\b/, 'artifactsHtml.ts は定数から作る');
});

test('D0025-AC-45: 上限の数（262144・4194304・256 * 1024・4 * 1024 * 1024 など）を、画面の部品（view/ の製品のファイル）に直書きしない（上限は artifacts.ts の 1 か所だけ）', () => {
  const files = readdirSync(HERE).filter((f) => f.endsWith('.ts') && !f.endsWith('.test.ts'));
  for (const must of ['artifactsHtml.ts', 'shellHtml.ts', 'panelHtml.ts', 'panelScript.ts']) assert.ok(files.includes(must), `${must} を調べている`);
  for (const f of files) assert.deepEqual(findLimitLiterals(readFileSync(path.join(HERE, f), 'utf8')), [], `${f} に上限の数の直書きが無い`);
});

// ---- AC-35：外から来た名前 ----

const WEIRD_NAMES: readonly (readonly [string, string])[] = [
  ['<script>', '<script>alert(1)</script>.md'],
  ['ダブルクォート', 'a"b.md'],
  ['シングルクォート', "it's.md"],
  ['閉じかっこ', 'x]y.md'],
  ['バックスラッシュ', 'back\\slash.md'],
  ['アンパサンド', 'a&b.md'],
  ['文字参照に見える文字', 'a&amp;b&lt;.md'],
  ['空白', 'sp ace.md'],
  ['全部入り', 'a"]\'\\& <b>x</b>.md'],
];
for (const [label, name] of WEIRD_NAMES) {
  test(`D0025-AC-35: 外から来た名前（${label}）を output・段の表示名に入れても、行・属性・プレビューの見出しに生で出ず、読み戻すと元の名前に戻る`, async () => {
    const out = await html([ready(name, name, { stage: 'x', stageLabel: name, text: 'x' })], { running: 'x' });
    if (escapeHtml(name) !== name) assert.ok(!out.includes(name), '生の名前が出ていない');
    assert.ok(out.includes(escapeHtml(name)), 'escapeHtml を通した形で出ている');
    assert.ok(!/<script/i.test(out), '生の <script> が無い');
    assert.ok(!/<b>/.test(out), '生の <b> が無い');
    const doc = parse(out);
    const row = allRows(doc)[0]!;
    assert.equal(row.getAttribute('data-art-pick'), name);
    assert.equal(row.getAttribute('data-keep'), `art-row:${name}`);
    assert.equal(partText(row, '.art-name'), name);
    assert.equal(partText(row, '.art-file'), name);
    assert.equal(partText(row, '.art-stage'), name);
    const preview = previewByName(doc, name);
    assert.equal(partText(preview, '.art-title'), name);
    assert.equal(partText(preview, '.art-file'), name);
    assert.equal(one(preview, 'button[data-artifact]').getAttribute('data-artifact'), name);
    assert.equal(one(preview, '.art-body').getAttribute('aria-label'), `${name}（${name}）のプレビュー`);
    assert.equal(one(preview, '.art-body').getAttribute('data-scroll-name'), name);
    assert.equal(one(doc, '.art').getAttribute('data-art-default'), name);
    assert.deepEqual(pressed(doc), [name]);
    assert.doesNotMatch(out, /\sstyle\s*=|\son[a-z]+\s*=/i, '属性が壊れて style・on… が生えていない');
  });
}

test('D0025-AC-35: 段の表示名・名前に、属性を壊して属性を足す文字（" onmouseover="…）を入れても、属性が増えない（木のどの要素も onmouseover を持たない）', async () => {
  const evil = 'x" onmouseover="alert(1)';
  const out = await html([ready('a.md', evil, { stage: 'x', stageLabel: evil }), ready(`${evil}.md`, 'b', { text: 'y' })], { running: 'x' });
  const doc = parse(out);
  assert.ok(allElements(doc).length > 10, '木が読めている');
  assert.ok(allElements(doc).every((n) => !n.attrs.has('onmouseover')), 'onmouseover を持つ要素が無い');
  assert.ok(allElements(doc).every((n) => [...n.attrs.keys()].every((k) => !k.startsWith('on'))), 'on… の属性が無い');
});

/** 向きを変える制御文字（displayName が U+FFFD にするもの） */
const BIDI = [0x202a, 0x202b, 0x202c, 0x202d, 0x202e, 0x2066, 0x2067, 0x2068, 0x2069];
for (const code of BIDI) {
  const hex = `U+${code.toString(16).toUpperCase()}`;
  test(`D0025-AC-35: output に向きを変える制御文字（${hex}）を入れると、行・見出し・aria-label の文字では U+FFFD になり、data-art-pick・data-artifact・data-keep・data-art-preview の名前は元のまま`, async () => {
    const ch = String.fromCodePoint(code);
    const name = `a${ch}b.md`;
    const label = `x${ch}y`;
    const out = await html([ready(name, label, { text: 'plain' })], { running: 'none' });
    const doc = parse(out);
    const row = allRows(doc)[0]!;
    assert.equal(partText(row, '.art-file'), 'a�b.md');
    assert.equal(partText(row, '.art-name'), 'x�y');
    const preview = previewByName(doc, name);
    assert.equal(partText(preview, '.art-title'), 'x�y');
    assert.equal(partText(preview, '.art-file'), 'a�b.md');
    assert.equal(one(preview, '.art-body').getAttribute('aria-label'), 'x�y（a�b.md）のプレビュー');
    assert.equal(row.getAttribute('data-art-pick'), name, '行を押して選ぶ名前は元のまま');
    assert.equal(row.getAttribute('data-keep'), `art-row:${name}`);
    assert.equal(one(preview, 'button[data-artifact]').getAttribute('data-artifact'), name, 'openArtifact の名前が一覧の名前と合う');
    assert.equal(one(preview, 'button[data-artifact]').getAttribute('data-keep'), `art-open:${name}`);
    assert.equal(one(preview, '.art-body').getAttribute('data-keep'), `art-scroll:${name}`);
    assert.equal(one(preview, '.art-body').getAttribute('data-scroll-name'), name);
    // 画面に出る文字（属性の外）には、向きを変える制御文字が残らない
    assert.equal(one(doc, '.art-list').textContent.includes(ch), false);
    assert.equal(partText(preview, '.art-head').includes(ch), false);
  });
}

test('D0025-AC-35: displayName は向きを変える制御文字（U+202A〜202E・U+2066〜2069）を 1 つずつ U+FFFD にし、ほかの文字（隣の U+2029・U+202F・U+2065・U+206A を含む）は変えない', async () => {
  const { displayName } = await ah();
  for (const code of BIDI) assert.equal(displayName(`a${String.fromCodePoint(code)}b`), 'a�b', `U+${code.toString(16)}`);
  assert.equal(displayName(BIDI.map((c) => String.fromCodePoint(c)).join('')), '�'.repeat(9));
  for (const code of [0x2029, 0x202f, 0x2065, 0x206a, 0x200e, 0x200f]) {
    const text = `a${String.fromCodePoint(code)}b`;
    assert.equal(displayName(text), text, `U+${code.toString(16)} は変えない`);
  }
  for (const text of ['', '01_requirements.md', '要件定義書', 'a"b&c<d>.md', '😀.md']) assert.equal(displayName(text), text);
});

// ---- AC-39：Markdown でない成果物 ----

const MD_NAME_CASES: readonly (readonly [string, boolean])[] = [
  ['a.md', true],
  ['A.MD', true],
  ['a.Md', true],
  ['a.mD', true],
  ['01_requirements.md', true],
  ['a.txt', false],
  ['a.markdown', false],
  ['a.mdx', false],
  ['a.md.txt', false],
  ['README', false],
  ['md', false],
  ['a.md ', false],
];
for (const [name, expected] of MD_NAME_CASES) {
  test(`D0025-AC-39: isMarkdownName(${JSON.stringify(name)}) は ${expected}（拡張子が .md か、大文字小文字は問わない）`, async () => {
    const { isMarkdownName } = await ah();
    assert.equal(isMarkdownName(name), expected);
  });
}

const RAW = '# 題\n- 項目 <b>太字</b> & "引用" \'一重\'\n| a | b |\n|---|---|\n| 1 | 2 |';
for (const name of ['notes.txt', 'plain', 'a.markdown', 'x.md.txt']) {
  test(`D0025-AC-39: ${name} は Markdown に直さず、pre の中に escapeHtml を通した文字としてそのまま出す`, async () => {
    const out = await html([ready(name, name, { text: RAW })], { running: 'none' });
    const doc = parse(out);
    const body = one(previewByName(doc, name), '.art-body');
    const pre = one(body, 'pre');
    assert.ok(pre.classList.contains('art-plain'));
    assert.ok(out.includes(escapeHtml(RAW)), 'escapeHtml を通した文字がそのまま入っている');
    assert.equal(body.querySelector('.md'), null, 'Markdown の入れ物が無い');
    for (const tag of ['h3', 'h4', 'ul', 'li', 'table', 'strong']) assert.equal(body.querySelector(tag), null, `<${tag}> を作らない`);
    assert.ok(!out.includes('<b>'), '生の <b> が無い');
  });
}

for (const name of ['notes.md', 'NOTES.MD']) {
  test(`D0025-AC-39: ${name} は Markdown に直して出す（div.md の中に見出しなどができ、pre.art-plain にはしない）`, async () => {
    const doc = parse(await html([ready(name, name, { text: '# 題\n\n- 項目' })], { running: 'none' }));
    const body = one(previewByName(doc, name), '.art-body');
    const md = one(body, '.md');
    assert.equal(md.tagName, 'div');
    assert.equal(partText(md, 'h3'), '題');
    assert.equal(partText(md, 'li'), '項目');
    assert.equal(body.querySelector('.art-plain'), null);
  });
}

test('D0025-AC-39: .md のプレビューでも、外から来た文字（<script>・<img onerror>）は生で出ない', async () => {
  const text = '<script>alert(1)</script>\n\n<img src=x onerror=alert(2)>';
  const out = await html([ready('x.md', 'x', { text })], { running: 'none' });
  assert.ok(!/<script/i.test(out) && !/<img/i.test(out), '生のタグが無い');
  assert.ok(out.includes(escapeHtml('<script>alert(1)</script>')), 'escapeHtml を通した文字として入っている');
});

// ---- 決まった形のくり返し ----

test('D0025-AC-53: 同じ項目・同じ「今」なら、同じ HTML ができる', async () => {
  assert.equal(await html(dev(), { running: 'design' }), await html(dev(), { running: 'design' }));
  assert.equal(await html(PIPE), await html(PIPE));
});

