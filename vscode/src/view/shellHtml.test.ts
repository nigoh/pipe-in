// パネルの枠組み（D0019・2版目）：上のバー・左の一覧・右の詳細（パンくず・見出し・メタ・知らせ・タブ・「図と出力」の枠）。純粋な文字列の検査。
// 新しい部品（view/shellHtml.ts）は、呼んだところで落ちるように、テストの中で読み込む。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import type { RunListView, RunRow } from '../domain/runList.ts';
import { escapeHtml } from './escape.ts';
import { FakeDocument } from '../test/fakeDom.ts';
import type { FakeNode } from '../test/fakeDom.ts';
import { DIAGRAMS_STAGES, snapshot, stageRunEntry, stateJson } from '../test/fixtures.ts';
import { finishedView, runningView, viewAt, waitingView } from '../test/liveFixtures.ts';
import { panelsByName } from '../test/panelParts.ts';
import { showcaseView } from '../test/reasonFixtures.ts';
import { SID, listView, row, sampleRows } from '../test/runListFixtures.ts';

const shell = () => import('./shellHtml.ts');
const render = async (view: PipelineView, list: RunListView): Promise<string> => (await shell()).renderShell(view, list);

const count = (text: string, re: RegExp): number => (text.match(re) ?? []).length;
const plain = (text: string): string => text.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
function between(text: string, from: string, to: string): string {
  const start = text.indexOf(from);
  assert.ok(start >= 0, `${from} がある`);
  const end = text.indexOf(to, start + from.length);
  return text.slice(start, end < 0 ? undefined : end);
}
/** 詳細の上の部分：パンくず・見出し・メタ・知らせ。詳細のタブの手前まで */
const detailTop = (out: string): string => between(out, 'class="crumbs"', 'data-detail-tab=');
const headOf = (out: string): string => between(out, 'class="head"', 'class="detail-meta"');
const metaOf = (out: string): string => between(out, 'class="detail-meta"', 'data-detail-tab=');
// 詳細のタブパネルを data-detail-panel の値で取る補助（panelsByName）は、D0047 で test/panelParts.ts へ移した（関数の中身は変えていない）。
// 番号でなく名前で取るので、タブが 3 つから 4 つになっても、中身を見るテストが位置に左右されない。個数は決め打ちしない（個数は D0047-AC-28 の 2 件が見る）。

const WAITING_LIST = (selected = 'here|') => listView(sampleRows(), { selected });

// ---- AC-55：3 つの領域 ----

test('D0019-AC-55: パネルの本体が、上のバー・左の一覧・右の詳細の 3 つの領域になる（この順）', async () => {
  const out = await render(waitingView(40), WAITING_LIST());
  assert.match(out, /<header\b[^>]*class="topbar"/);
  assert.match(out, /<nav\b[^>]*class="sidebar"/);
  assert.match(out, /<main\b[^>]*class="detail"/);
  assert.ok(out.indexOf('class="topbar"') < out.indexOf('class="sidebar"') && out.indexOf('class="sidebar"') < out.indexOf('class="detail"'));
  assert.match(out, /class="app"/);
  assert.match(out, /class="app-body"/);
  assert.ok(out.indexOf('class="app-body"') < out.indexOf('class="sidebar"'), '左の一覧と右の詳細は app-body の中');
  assert.equal(count(out, /class="run-list"/g), 1, '左の欄に一覧');
});

test('D0019-AC-55: run が 0 でも 1 つでも 2 つ以上でも、同じ 3 つの領域になる', async () => {
  for (const rows of [[], [row({ key: 'here|' })], sampleRows()]) {
    const out = await render(runningView(83), listView(rows));
    for (const marker of ['class="topbar"', 'class="sidebar"', 'class="detail"', 'class="run-list"', 'class="crumbs"', 'data-detail-tab="diagram"']) {
      assert.ok(out.includes(marker), `${rows.length} 行: ${marker}`);
    }
  }
});

test('D0019-AC-55: 上のバーに アプリ名（pipe-in）と 作業フォルダ（一覧の workDir。設定の相対パスのまま）が出る', async () => {
  const out = await render(waitingView(40), listView(sampleRows(), { workDir: 'records/pipe' }));
  const top = plain(between(out, 'class="topbar"', 'class="sidebar"'));
  assert.match(top, /pipe-in/);
  assert.match(top, /records\/pipe/);
  const def = plain(between(await render(waitingView(40), WAITING_LIST()), 'class="topbar"', 'class="sidebar"'));
  assert.match(def, /docs\/pipeline/);
});

test('D0019-AC-55: 選んだ run が別の worktree のときだけ、上のバーに「別の worktree を表示中：ブランチ名」が出る', async () => {
  const other = plain(between(await render(waitingView(40), WAITING_LIST('wt.feat-x|')), 'class="topbar"', 'class="sidebar"'));
  assert.match(other, /別の worktree を表示中：feat\/export-csv/);
  for (const key of ['here|', 'here|diagrams', 'here|archive/20261016-090000']) {
    const mine = plain(between(await render(waitingView(40), WAITING_LIST(key)), 'class="topbar"', 'class="sidebar"'));
    assert.doesNotMatch(mine, /別の worktree を表示中/, key);
  }
  const none = await render(waitingView(40), listView([]));
  assert.doesNotMatch(plain(between(none, 'class="topbar"', 'class="sidebar"')), /別の worktree を表示中/);
});

test('D0019-AC-55: 選んだ run が一覧に無い（key が合わない）ときも、枠組みは崩れず、別の worktree の表示は出ない', async () => {
  const out = await render(waitingView(40), listView(sampleRows(), { selected: 'here|nothing' }));
  assert.match(out, /class="detail"/);
  assert.doesNotMatch(plain(between(out, 'class="topbar"', 'class="sidebar"')), /別の worktree を表示中/);
  assert.match(plain(between(out, 'class="head"', 'class="detail-meta"')), /実行の記録/);
});

// ---- AC-60：詳細の上の部分 ----

test('D0019-AC-60: パンくずは ブランチ › パイプ名。ブランチ名が無い（git の外）ときは、パイプ名だけで「—」を出さない', async () => {
  const withBranch = plain(between(await render(runningView(83), WAITING_LIST('wt.feat-x|')), 'class="crumbs"', 'class="head"'));
  assert.match(withBranch, /feat\/export-csv\s*›\s*spec-qa/);
  const noBranch = plain(between(await render(runningView(83), listView([row({ key: 'here|', pipe: 'diagrams', branch: null })])), 'class="crumbs"', 'class="head"'));
  assert.match(noBranch, /diagrams/);
  assert.doesNotMatch(noBranch, /—|null/);
});

test('D0019-AC-60: 見出しに、セッション名（h1）と状態のバッジが出る。確認待ちのバッジは「確認待ち」の文字と待ち時間（data-elapsed＝基準の秒）', async () => {
  const waiting = headOf(await render(waitingView(40), WAITING_LIST('here|')));
  assert.match(waiting, /<h1\b[^>]*>仕様の QA を回す<\/h1>/);
  assert.match(plain(waiting), /確認待ち 0:42/);
  assert.match(waiting, /<span class="elapsed" data-elapsed="42">0:42<\/span>/);
  const other = headOf(await render(waitingView(40), WAITING_LIST('wt.feat-x|')));
  assert.match(other, /data-elapsed="7">0:07</);
});

test('D0019-AC-60: 確認待ちで待ち時間が読めない行（waitingSec が null）のバッジは、待ち時間を出さず「確認待ち」の文字だけ', async () => {
  const out = headOf(await render(waitingView(40), listView([row({ key: 'here|', state: 'waiting', waitingSec: null })])));
  assert.match(plain(out), /確認待ち/);
  assert.doesNotMatch(out, /data-elapsed/);
});

test('D0019-AC-60: 確認待ち以外のバッジは状態の言葉（動いている・待ち・結果の言葉）で、待ち時間（data-elapsed）は付かない', async () => {
  const list = (r: Partial<RunRow>) => listView([row({ key: 'here|', ...r })]);
  const view = finishedView();
  const running = headOf(await render(view, list({ state: 'running', waitingSec: 9 })));
  assert.match(plain(running), /動いている/);
  const idle = headOf(await render(view, list({ state: 'idle' })));
  assert.match(plain(idle), /待ち/);
  assert.doesNotMatch(plain(idle), /確認待ち/);
  const passed = headOf(await render(view, list({ state: 'done', result: '合格' })));
  assert.match(plain(passed), /合格/);
  const failed = headOf(await render(view, list({ state: 'done', result: '不合格' })));
  assert.match(plain(failed), /不合格/);
  const unknown = headOf(await render(view, list({ state: 'done', result: null })));
  assert.match(plain(unknown), /終わった/);
  for (const h of [running, idle, passed, failed, unknown]) assert.doesNotMatch(h, /data-elapsed/);
});

test('D0019-AC-60: 「成果物を開く」ボタン（data-open-artifacts）が見出しにある。メッセージは送らない（data-artifact を持たない）', async () => {
  const out = headOf(await render(waitingView(40), WAITING_LIST()));
  assert.match(out, /<button\b[^>]*data-open-artifacts[^>]*>[\s\S]*?成果物を開く[\s\S]*?<\/button>/);
  assert.match(out, /type="button"/);
  assert.doesNotMatch(out, /data-artifact=|data-run=/);
});

test('D0019-AC-60: メタに パイプ・セッション ID（全部）・今の段・経過・費用・最後に動いた時刻 が出る', async () => {
  const out = metaOf(await render(waitingView(40), WAITING_LIST('here|')));
  const text = plain(out);
  assert.match(text, /開発フロー/);
  assert.ok(out.includes(SID.here), 'セッション ID は全部（先頭 8 文字でなく）');
  assert.match(text, /要件定義/);
  assert.match(text, /経過/);
  assert.match(text, /\$1\.250/);
  assert.match(text, /10\/17 10:05/);
});

test('D0019-AC-60: セッション ID が無い行のメタは「—」。経過・費用・時刻が読めない行も「—」で、例外を出さない', async () => {
  const out = metaOf(await render(waitingView(40), listView([row({ key: 'here|', sessionId: null, costText: '—', updatedText: '—', elapsed: null, stage: '—' })])));
  assert.match(plain(out), /—/);
  assert.doesNotMatch(out, /null|undefined|NaN/);
  assert.doesNotMatch(out, /class="elapsed"/, '経過が読めなければ、経過の要素を出さない');
});

test('D0019-AC-60: メタの経過：動いている行は数え上げる要素（data-elapsed）、終わった行は固定の文字（data-elapsed なし）', async () => {
  const live = metaOf(await render(runningView(83), WAITING_LIST('here|diagrams')));
  assert.match(live, /<span class="elapsed" data-elapsed="125">2:05<\/span>/);
  const fixed = metaOf(await render(finishedView(), WAITING_LIST('here|survey')));
  assert.match(fixed, /<span class="elapsed">7:00<\/span>/);
  assert.doesNotMatch(fixed, /data-elapsed/);
});

// ---- 行が無いときは図の状態（view）から：D0017-AC-18 の「バナーに全体の経過」は「詳細のメタに全体の経過」として満たす（AC-76）----

test('D0019-AC-76: 一覧の行が無いとき、見出しは「実行の記録」で、メタに図の状態の全体の経過（動いている・確認待ちは data-elapsed、終わったら固定）と合計の費用が出る', async () => {
  const empty = listView([]);
  const running = await render(runningView(83), empty);
  assert.match(plain(headOf(running)), /実行の記録/);
  assert.match(metaOf(running), /<span class="elapsed" data-elapsed="203">3:23<\/span>/);
  assert.match(plain(metaOf(running)), /\$0\.000/);
  const waiting = await render(waitingView(40), empty);
  assert.match(metaOf(waiting), /<span class="elapsed" data-elapsed="160">2:40<\/span>/);
  const done = await render(finishedView(), empty);
  assert.match(metaOf(done), /<span class="elapsed">7:00<\/span>/);
  assert.doesNotMatch(metaOf(done), /data-elapsed/);
  // 行が無いときの見出しには、状態のバッジ（と待ち時間）を出さない
  assert.doesNotMatch(headOf(waiting), /data-elapsed/);
});

// ---- AC-61：知らせ・バナーの文言 ----

test('D0019-AC-61: 確認待ちの run では、黄の知らせ（role="status"）に、確認を待っている段の名前と文書の場所、読んで承認か修正を返す案内が読める', async () => {
  for (const list of [WAITING_LIST('here|'), listView([])]) {
    const out = detailTop(await render(waitingView(40), list));
    const at = out.search(/role="status"/);
    assert.ok(at >= 0, '知らせがある');
    const notice = plain(out.slice(at));
    assert.match(notice, /要件定義の確認を待っている：docs\/pipeline\/01_requirements\.md/);
    assert.match(notice, /読んで、承認か修正の依頼を返してください/);
  }
});

test('D0019-AC-61: 確認待ちでない run には、確認待ちの知らせ（role="status"）が出ない', async () => {
  for (const view of [runningView(83), finishedView()]) {
    assert.doesNotMatch(detailTop(await render(view, listView([]))), /role="status"/);
  }
});

test('D0019-AC-61: 1回目のバナーの文言が詳細に残る：最終の結果・いま動いている段・次を待っている・記録なし', async () => {
  const done = detailTop(await render(finishedView(), listView([])));
  assert.match(done, /<p class="banner-msg is-done">最終の結果：PASSED<\/p>/);
  const failed = detailTop(await render(viewAt(snapshot({ stateJson: stateJson({ final: 'TEST_FAILED' }) })), listView([])));
  assert.match(failed, /<p class="banner-msg is-failed">最終の結果：TEST_FAILED<\/p>/);
  const running = detailTop(await render(runningView(83), listView([])));
  assert.match(running, /<p class="banner-msg is-running">いま：設計<\/p>/);
  const idle = detailTop(await render(viewAt(snapshot({ stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }) })), listView([])));
  assert.match(idle, /次を待っている（人の確認かもしれない）/);
  const none = detailTop(await render(buildPipelineView(snapshot()), listView([])));
  assert.match(plain(none), /記録がありません：\/w/);
});

test('D0019-AC-61: パイプの確認待ちは、段の label で「○○の確認を待っている：文書」。外から来た文字はエスケープする', async () => {
  const stages = DIAGRAMS_STAGES.map((s) => (s.name === 'draw' ? { ...s, label: '<b>図</b>' } : s));
  const view = viewAt(
    snapshot({
      stateJson: stateJson({
        pipe: 'diagrams',
        stages,
        pendingReview: { stage: 'draw', doc: 'docs/pipeline/diagrams/<x>.md', session_id: 's' },
        runs: [stageRunEntry({ stage: 'survey', seq: 1 }), stageRunEntry({ stage: 'draw', seq: 2 })],
      }),
    }),
  );
  const out = detailTop(await render(view, listView([])));
  assert.match(out, /&lt;b&gt;図&lt;\/b&gt;の確認を待っている/);
  assert.match(out, /docs\/pipeline\/diagrams\/&lt;x&gt;\.md/);
  assert.doesNotMatch(out, /<b>図<\/b>/);
});

// ---- AC-62・AC-63・AC-64：詳細のタブと「図と出力」の枠 ----

test('D0047-AC-28: 詳細のタブ「図と出力」「成果物」「エージェント・スキル」「使用量」が role="tablist" で並び、初めに選ばれているのは「図と出力」だけ（aria-selected）（D0019-AC-62 の「タブ 3 つ」を置き換える）', async () => {
  const out = await render(waitingView(40), WAITING_LIST());
  const tabs = [...out.matchAll(/<button\b[^>]*data-detail-tab="([^"]+)"[^>]*>([\s\S]*?)<\/button>/g)];
  assert.deepEqual(tabs.map((t) => t[1]), ['diagram', 'artifacts', 'tools', 'usage']);
  assert.deepEqual(tabs.map((t) => plain(t[2]!)), ['図と出力', '成果物', 'エージェント・スキル', '使用量']);
  assert.deepEqual(tabs.map((t) => /aria-selected="(true|false)"/.exec(t[0])?.[1]), ['true', 'false', 'false', 'false']);
  for (const t of tabs) assert.match(t[0], /role="tab"/);
  assert.equal(count(out, /role="tablist"/g), 2, '状態のタブと詳細のタブの 2 つ');
  assert.ok(out.lastIndexOf('role="tablist"', out.indexOf('data-detail-tab="diagram"')) > out.indexOf('class="detail"'), '詳細のタブは詳細の中の role="tablist"');
});

test('D0047-AC-28: タブパネルは 4 つ（role="tabpanel"。図と出力・成果物・エージェント・スキル・使用量の順）で、初めに見えるのは「図と出力」だけ（ほかは hidden）（D0019-AC-62 の「タブパネルは 3 つ」を置き換える）', async () => {
  const out = await render(waitingView(40), WAITING_LIST());
  const tags = [...out.matchAll(/<[a-z]+\b[^>]*role="tabpanel"[^>]*>/g)].map((m) => m[0]);
  assert.equal(tags.length, 4);
  assert.deepEqual(tags.map((t) => /\bdata-detail-panel="([^"]*)"/.exec(t)?.[1]), ['diagram', 'artifacts', 'tools', 'usage']);
  assert.deepEqual(tags.map((t) => /\bhidden\b/.test(t)), [false, true, true, true]);
});

test('D0019-AC-63: 「図と出力」は 左に図の枠（.pane-diagram：図・注意・理由・時間）、右に出力（上）と時系列（下）', async () => {
  const out = await render(showcaseView(), listView([]));
  const diagram = between(out, 'class="pane-diagram"', 'class="pane-right"');
  assert.match(diagram, /<svg\b[^>]*class="flow"/, '図');
  assert.match(diagram, /data-reasons-for=/, '理由の欄');
  assert.match(diagram, /class="times"/, '時間の節');
  const right = between(out, 'class="pane-right"', 'role="tabpanel"');
  assert.ok(right.indexOf('class="pane-output"') >= 0 && right.indexOf('class="pane-gantt"') > right.indexOf('class="pane-output"'), '出力 → 時系列 の順');
  assert.match(between(right, 'class="pane-output"', 'class="pane-gantt"'), /class="terminal"/, '出力は .terminal');
  assert.match(between(right, 'class="pane-gantt"', 'role="tabpanel"'), /時系列/);
  assert.ok(out.indexOf('class="pane-diagram"') < out.indexOf('class="pane-right"'));
});

test('D0019-AC-63: 注意（warnings）は図の枠の中、理由の欄・時間の節より前に出る', async () => {
  const view = viewAt(snapshot({ stateJson: stateJson({ warnings: ['赤になっていません'], runs: [stageRunEntry({ stage: 'implement', seq: 1, attempt: 1 }), stageRunEntry({ stage: 'implement', seq: 2, attempt: 2 })] }) }));
  const out = await render(view, listView([]));
  const diagram = between(out, 'class="pane-diagram"', 'class="pane-right"');
  assert.match(diagram, /注意/);
  assert.match(diagram, /赤になっていません/);
  assert.ok(diagram.indexOf('注意') > diagram.indexOf('<svg'), '図のあとに注意');
  assert.ok(diagram.indexOf('class="times"') > diagram.indexOf('注意'), '注意のあとに時間');
});

test('D0019-AC-63: 一覧・図の枠・出力・時系列は、それぞれ別にスクロールする枠の印（data-scroll）を持つ', async () => {
  const out = await render(showcaseView(), WAITING_LIST());
  for (const name of ['list', 'diagram', 'output', 'gantt']) assert.equal(count(out, new RegExp(`data-scroll="${name}"`, 'g')), 1, name);
  // スクロールする枠そのものが印を持つ：図の枠 .pane-diagram・出力 .terminal・時系列 .pane-gantt・一覧 .run-scroll
  const tagOf = (token: string): string => out.match(new RegExp(`<[a-z]+\\b[^>]*class="[^"]*\\b${token}\\b[^"]*"[^>]*>`))?.[0] ?? '';
  assert.match(tagOf('pane-diagram'), /data-scroll="diagram"/);
  assert.match(tagOf('terminal'), /data-scroll="output"/);
  assert.match(tagOf('pane-gantt'), /data-scroll="gantt"/);
  assert.match(tagOf('run-scroll'), /data-scroll="list"/);
  assert.ok(out.indexOf('data-scroll="list"') < out.indexOf('data-scroll="diagram"'), '一覧が先');
  assert.ok(out.indexOf('data-scroll="diagram"') < out.indexOf('data-scroll="output"') && out.indexOf('data-scroll="output"') < out.indexOf('data-scroll="gantt"'));
});

// D0019-AC-64 の「成果物」タブの検査は、D0025 で一覧とプレビューの形に変わったので置き換えた（決定の記録 D0025「既存のテストを変えた理由」）。
// 「成果物」タブには、成果物の一覧の行（選ぶ。data-art-pick。data-artifact を持たない）と、ある成果物のプレビューの「エディタで開く」（data-artifact）がある。
// まだ無い行は押せない（disabled）。メッセージの元になる（data-artifact を持つ）のは、プレビューの「エディタで開く」だけ。
test('D0025-AC-10: 「成果物」タブは、成果物の一覧の行（data-art-pick。data-artifact を持たない）と、ある成果物のプレビューの「エディタで開く」（data-artifact）でできていて、まだ無い行は押せない（disabled）。メッセージの元になるのはプレビューの「エディタで開く」だけ（D0019-AC-64 を D0025 で置き換え）', async () => {
  const view = buildPipelineView(snapshot({ artifacts: { '00_input.md': 'メモ', '01_requirements.md': '要件', '03_red_tests.md': '  ' } }));
  const { artifacts } = panelsByName(await render(view, listView([])));
  const doc = new FakeDocument();
  doc.innerHTML = artifacts!;
  const fileOf = (n: FakeNode): string | undefined => n.querySelector('.art-file')?.textContent;
  const rows = doc.querySelectorAll('.art-row');
  assert.deepEqual(rows.map(fileOf), ['00_input.md', '01_requirements.md', '02_design.md', '03_red_tests.md', '04_implementation.md', '05_test_report.md', '99_summary.md'], '成果物の一覧は今までと同じ 7 行（同じ順）');
  for (const r of rows) {
    assert.equal(r.tagName, 'button');
    assert.equal(r.hasAttribute('data-artifact'), false, '一覧の行は data-artifact を持たない（押しても openArtifact は送られない）');
  }
  assert.deepEqual(
    rows.filter((r) => !r.disabled).map(fileOf),
    ['00_input.md', '01_requirements.md'],
    '押せる行は「ある」成果物だけ',
  );
  assert.deepEqual(
    rows.filter((r) => r.disabled).map(fileOf),
    ['02_design.md', '03_red_tests.md', '04_implementation.md', '05_test_report.md', '99_summary.md'],
    '空・空白だけ・ファイルなしの成果物は押せない（disabled）',
  );
  const open = doc.querySelectorAll('[data-artifact]');
  assert.deepEqual(open.map((n) => n.getAttribute('data-artifact')), ['00_input.md', '01_requirements.md'], 'data-artifact を持つのは「ある」成果物の「エディタで開く」だけ');
  for (const b of open) {
    assert.equal(b.tagName, 'button');
    assert.equal(b.textContent.trim(), 'エディタで開く');
    assert.ok(b.closest('[data-art-preview]') !== null, 'プレビューの見出しの中');
    assert.ok(b.closest('.art-list') === null, '成果物の一覧の中には無い');
  }
  assert.doesNotMatch(artifacts!, /data-artifact="03_red_tests\.md"/, '空の成果物は押せない（プレビューも作らない）');
});

test('D0019-AC-64: 「使用量」タブに使用量の表（usage-table）がある。使用量の無い記録では空', async () => {
  const { usage } = panelsByName(await render(showcaseView(), listView([])));
  assert.match(usage!, /class="usage-table"/);
  assert.match(usage!, /使用量/);
  const { usage: none } = panelsByName(await render(buildPipelineView(snapshot()), listView([])));
  assert.doesNotMatch(none!, /usage-table/);
});

test('D0019-AC-63: 「図と出力」以外のタブパネルに、図・出力・時系列は入らない（図と出力のタブにだけある）', async () => {
  const { artifacts, usage } = panelsByName(await render(showcaseView(), listView([])));
  for (const p of [artifacts!, usage!]) assert.doesNotMatch(p, /class="flow"|class="terminal"|gantt-svg|data-reasons/);
});

// ---- AC-28・AC-29 ----

test('D0019-AC-28: 同じ記録・同じ一覧なら、枠組みの HTML は同じ', async () => {
  assert.equal(await render(waitingView(40), WAITING_LIST()), await render(waitingView(40), WAITING_LIST()));
});

const EVIL = '<script>alert(1)</script>"&\'';
const EVIL_ROWS: [string, Partial<RunRow>][] = [
  ['セッション名', { session: EVIL }],
  ['パイプ名', { pipe: EVIL }],
  ['ブランチ名', { branch: EVIL }],
  ['別の worktree のブランチ名', { branch: EVIL, other: true }],
  ['セッション ID', { sessionId: EVIL }],
  ['今の段', { stage: EVIL }],
  ['結果', { state: 'done', result: EVIL }],
  ['費用・時刻の文字', { costText: EVIL, updatedText: EVIL, updatedDate: EVIL }],
];
for (const [label, over] of EVIL_ROWS) {
  test(`D0019-AC-29: 詳細（パンくず・見出し・メタ・上のバー）に出る外から来た文字（${label}）の <script>・"・& は生で出ない`, async () => {
    const out = await render(waitingView(40), listView([row({ key: 'here|', ...over })]));
    assert.ok(!out.includes('<script>alert'), '生の <script> が入っていない');
    assert.ok(!out.includes('alert(1)</script>'));
    assert.ok(!/<script/i.test(out));
    assert.ok(out.includes('&lt;script&gt;alert(1)&lt;/script&gt;'), 'エスケープされた形で出ている');
    assert.doesNotMatch(out, /\sstyle\s*=/i);
    assert.doesNotMatch(out, /<[a-z][^>]*\son[a-z]+\s*=/i);
  });
}

test('D0019-AC-29: 作業フォルダの表示と、図の状態の外から来た文字（段の label・文書の場所・注意）もエスケープされる', async () => {
  const stages = [{ name: 'draw', label: EVIL, output: 'a.md', review: true }];
  const view = viewAt(
    snapshot({
      stateJson: stateJson({
        pipe: 'p',
        stages,
        warnings: [EVIL],
        pendingReview: { stage: 'draw', doc: EVIL, session_id: 's' },
        runs: [stageRunEntry({ stage: 'draw', seq: 1 })],
      }),
    }),
  );
  const out = await render(view, listView(sampleRows(), { workDir: EVIL }));
  assert.ok(!out.includes('<script>alert'));
  assert.ok(out.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
  assert.ok(out.includes(escapeHtml(EVIL)));
  assert.doesNotMatch(out, /\sstyle\s*=/i);
});

test('D0019-AC-29: 枠組みの CSS（SHELL_STYLE）に色の直書き・外部の読み込み・id セレクタが無く、テーマの変数だけを使う', async () => {
  const { SHELL_STYLE } = await shell();
  assert.match(SHELL_STYLE, /var\(--vscode-/);
  for (const re of [/#[0-9a-fA-F]{3,8}\b/, /rgba?\(/, /hsla?\(/, /url\(\s*["']?https?:/i, /@import/i]) assert.doesNotMatch(SHELL_STYLE, re);
  assert.doesNotMatch(SHELL_STYLE, /(^|[\s,}])#[A-Za-z_-]/, 'id セレクタを使わない（クラスだけ）');
});
