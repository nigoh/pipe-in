// ステータスバーの件数の形（D0024）：選んでいる実行のほかに数える行があるときの文字（text）と説明（tooltip）。
// statusBarLabel(view, list) と plainLine は純粋な関数。今の出し方（第 2 引数なし）が 1 文字も変わらないことは「守る」と書く。
// 新しい部品（statusBar.ts の plainLine・STATUS_LINES_LIMIT、domain/runList.ts の frontWaitingKey）は、テストの中で読み込む
// （テスト先行のとき、まだ無い部品が呼んだところで落ちるようにしたため）。
// 向きを変える文字・行区切りなどの見えにくい文字は、ソースに生の文字で書かず、cp(0x202e) のようにコードポイントで書く
// （エディタやレビューの画面で、行の見え方が入れ替わったり、行が割れたりしないように）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { statusBarLabel } from './statusBar.ts';
import type { StatusBarLabel } from './statusBar.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { summarizeRun } from '../domain/runList.ts';
import type { RunRow, RunState } from '../domain/runList.ts';
import { snapshot, stageRunEntry, stateJson, usageSummaryDict } from '../test/fixtures.ts';
import { clockAt, finishedView, loopSnapshot, runningView, viewAt, waitingView } from '../test/liveFixtures.ts';
import { listView, row } from '../test/runListFixtures.ts';

const sb = () => import('./statusBar.ts');
const dom = () => import('../domain/runList.ts');

const SUFFIX = '（確認待ちの実行を先に出す）';
const CLICK = 'クリックでパネルを開く';

/** text の「アイコン pipe-in: 件数」の、件数の前までの文字。 */
const TEXT_HEAD = 'pipe-in: ';

/** 「今」より minAgo 分前（大きいほど古い）。一覧の並びを決める更新時刻。 */
const t = (minAgo: number): number => Date.UTC(2026, 9, 17, 10, 0, 0) - minAgo * 60_000;
const pad = (n: number): string => String(n).padStart(2, '0');
const lines = (label: StatusBarLabel): string[] => label.tooltip.split('\n');
/** コードポイントから文字を作る（生の制御文字をソースに書かないため）。 */
const cp = (...codes: number[]): string => String.fromCodePoint(...codes);

/** 一覧の行 1 つ。名前は key のまま（行を見る検査では session などを渡す）。別の worktree の key（wt.…）は other が真。 */
function r(key: string, state: RunState, p: Partial<RunRow> = {}): RunRow {
  return row({ key, state, session: key, stage: '設計', branch: null, other: key.startsWith('wt.'), ...p });
}

// ---- 図の状態の見本 ----

const clock = clockAt(40);
const noRecordsView = (): PipelineView => buildPipelineView(snapshot(), clock);
const idleView = (): PipelineView =>
  buildPipelineView(snapshot({ stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }) }), clock);
/** 終わった（合格）記録。usageSummary を渡すと使用量を持つ。 */
function finishedWith(usageSummary?: unknown): PipelineView {
  return buildPipelineView(
    snapshot({ stateJson: stateJson({ final: 'PASSED', totalCostUsd: 1, usageSummary, runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }) }),
    clock,
  );
}

/** 選んでいる行の状態に合う図の状態（一覧に無い選びは記録なし）。 */
function viewFor(rows: readonly RunRow[], selected: string): PipelineView {
  const state = rows.find((x) => x.key === selected)?.state;
  if (state === 'waiting') return waitingView(40);
  if (state === 'running') return runningView(40);
  if (state === 'idle') return idleView();
  if (state === 'done') return finishedView();
  return noRecordsView();
}

/** 一覧（行と選び）から文字と説明を作る。view を渡さなければ、選んでいる行に合う図の状態を使う。 */
function labelOf(rows: RunRow[], selected: string, o: { view?: PipelineView; omittedWorktrees?: number } = {}): StatusBarLabel {
  return statusBarLabel(o.view ?? viewFor(rows, selected), listView(rows, { selected, omittedWorktrees: o.omittedWorktrees ?? 0 }));
}

/** 動いている自分の実行と、別の worktree の確認待ち 1 件（件数の形になる最小の一覧）。 */
const runningAndWaiting = (): RunRow[] => [
  r('here|', 'running', { session: '自分', stage: '設計', branch: 'main' }),
  r('wt.feat-x|', 'waiting', { session: '他', stage: '図を描く', branch: 'feat/x' }),
];

// ---- AC-07：選んでいる実行のほかに数える行が無いとき、今の出し方と同じ（守る） ----

interface Plain {
  name: string;
  view: () => PipelineView;
  rows: RunRow[];
  selected: string;
  text: string;
  omittedWorktrees?: number;
}

const ARCHIVE_KEY = 'here|archive/20261016-090000';

const NO_OTHER: readonly Plain[] = [
  { name: '実行が 1 件だけ（動いている）', view: () => runningView(40), rows: [r('here|', 'running')], selected: 'here|', text: '$(sync~spin) pipe-in: 設計' },
  {
    name: '実行が 1 件だけ（確認待ち）',
    view: () => waitingView(40),
    rows: [r('here|', 'waiting')],
    selected: 'here|',
    text: '$(comment-discussion) pipe-in: 要件定義の確認待ち',
  },
  {
    name: '選んでいる実行が動いていて、ほかが全部終わった（段の名前と回が残る）',
    view: () => viewAt(loopSnapshot({ sendBack: 1, running: true })),
    rows: [r('here|', 'running'), r('wt.feat-x|', 'done', { result: '合格' }), r(ARCHIVE_KEY, 'done', { previous: true, result: '合格' })],
    selected: 'here|',
    text: '$(sync~spin) pipe-in: 検証（2 回目）',
  },
  {
    name: '選んでいる実行が合格で、ほかも全部終わった',
    view: () => finishedView(),
    rows: [r('here|', 'done', { result: '合格' }), r('wt.feat-x|', 'done', { result: '不合格' })],
    selected: 'here|',
    text: '$(pass) pipe-in: 合格',
  },
  {
    name: 'archive だけ（前の実行を選んでいる）',
    view: () => finishedView(),
    rows: [r(ARCHIVE_KEY, 'done', { previous: true, result: '合格' })],
    selected: ARCHIVE_KEY,
    text: '$(pass) pipe-in: 合格',
  },
  { name: '一覧が空（記録なし）', view: noRecordsView, rows: [], selected: 'here|', text: '$(circuit-board) pipe-in' },
  {
    name: '一覧を読めなかった（図は動いているが、一覧は空）',
    view: () => runningView(40),
    rows: [],
    selected: 'here|',
    text: '$(sync~spin) pipe-in: 設計',
  },
  {
    name: '別の worktree を省いているが、数える行は選んでいる実行だけ（省いた分は件数に入れない）',
    view: () => runningView(40),
    rows: [r('here|', 'running')],
    selected: 'here|',
    text: '$(sync~spin) pipe-in: 設計',
    omittedWorktrees: 3,
  },
];

test('D0024-AC-07: 選んでいる実行のほかに数える行が無いとき、text も tooltip も今の出し方と同じ（1 件だけ・ほかが全部終わった・archive だけ・一覧が空・一覧を読めなかった）（今のまま通る。守る）', () => {
  for (const c of NO_OTHER) {
    const view = c.view();
    const withList = statusBarLabel(view, listView(c.rows, { selected: c.selected, omittedWorktrees: c.omittedWorktrees ?? 0 }));
    assert.deepEqual(withList, statusBarLabel(view), c.name);
    assert.equal(withList.text, c.text, c.name);
  }
});

// ---- AC-08〜11：件数の形に切り替わる ----

test('D0024-AC-08: 選んでいる実行が動いていて、別に確認待ちが 1 つあるとき、「$(comment-discussion) pipe-in: 動き 1・確認待ち 1」の件数の形になる', () => {
  const label = labelOf(runningAndWaiting(), 'here|');
  assert.equal(label.text, '$(comment-discussion) pipe-in: 動き 1・確認待ち 1');
});

test('D0024-AC-09: 選んでいる実行が合格で、別の worktree に確認待ちが 1 つだけのとき、「確認待ち 1」になる（合格で隠さない）', () => {
  const rows = [r('here|', 'done', { session: '調査', result: '合格' }), r('wt.feat-x|', 'waiting', { session: '他' })];
  assert.equal(labelOf(rows, 'here|', { view: finishedView() }).text, '$(comment-discussion) pipe-in: 確認待ち 1');
});

test('D0024-AC-09: 選んでいる実行が合格のとき、説明の「選んでいる実行」の行に結果が出る', () => {
  const rows = [r('here|', 'done', { session: '調査', result: '合格' }), r('wt.feat-x|', 'waiting', { session: '他' })];
  const picked = lines(labelOf(rows, 'here|', { view: finishedView() })).filter((l) => l.startsWith('選んでいる実行：'));
  assert.deepEqual(picked, ['選んでいる実行：調査（合格）']);
});

test('D0024-AC-10: 選んでいる実行が記録なし（一覧に行が無い）で、別の worktree に確認待ちが 1 つのとき、「確認待ち 1」になる', () => {
  const rows = [r('wt.feat-x|', 'waiting', { session: '他' })];
  assert.equal(labelOf(rows, 'here|', { view: noRecordsView() }).text, '$(comment-discussion) pipe-in: 確認待ち 1');
});

test('D0024-AC-10: 記録なしのとき、説明は件数の形で、「記録がありません」の文は出ず、「選んでいる実行：記録なし」の 1 行が出る', () => {
  const rows = [r('wt.feat-x|', 'waiting', { session: '他' })];
  const label = labelOf(rows, 'here|', { view: noRecordsView() });
  assert.doesNotMatch(label.tooltip, /記録がありません/);
  assert.deepEqual(lines(label).filter((l) => l.startsWith('選んでいる実行：')), ['選んでいる実行：記録なし']);
});

test('D0024-AC-11: 図が動いているのに一覧の行が終わっているずれでも、行で決める（別に確認待ちがあれば件数の形）', () => {
  const rows = [r('here|', 'done', { session: '自分', result: '合格' }), r('wt.feat-x|', 'waiting', { session: '他' })];
  const label = statusBarLabel(runningView(40), listView(rows, { selected: 'here|' }));
  assert.equal(label.text, '$(comment-discussion) pipe-in: 確認待ち 1');
});

test('D0024-AC-11: 図が終わっているのに一覧の行が動いているずれでも、行で決める（ほかに数える行が無ければ今の出し方）（今のまま通る。守る）', () => {
  const rows = [r('here|', 'running', { session: '自分' }), r(ARCHIVE_KEY, 'done', { previous: true, result: '合格' })];
  const view = finishedView();
  const label = statusBarLabel(view, listView(rows, { selected: 'here|' }));
  assert.deepEqual(label, statusBarLabel(view));
  assert.equal(label.text, '$(pass) pipe-in: 合格');
});

// ---- AC-12：text の形 ----

interface TextCase {
  name: string;
  rows: RunRow[];
  selected: string;
  text: string;
}

const manyRunning = (n: number): RunRow[] => Array.from({ length: n }, (_, i) => r(i === 0 ? 'here|' : `here|p${pad(i)}`, 'running', { updatedMs: t(i) }));

const TEXT_CASES: readonly TextCase[] = [
  { name: '動きだけ（動いている 2）', rows: [r('here|', 'running'), r('wt.feat-x|', 'running')], selected: 'here|', text: '$(sync~spin) pipe-in: 動き 2' },
  { name: '動いている 1・待ち 1（待ちは動きに数える）', rows: [r('here|', 'running'), r('wt.feat-x|', 'idle')], selected: 'here|', text: '$(sync~spin) pipe-in: 動き 2' },
  {
    name: '確認待ちだけ（見ているのは合格）',
    rows: [r('here|', 'done', { result: '合格' }), r('wt.feat-x|', 'waiting')],
    selected: 'here|',
    text: '$(comment-discussion) pipe-in: 確認待ち 1',
  },
  {
    name: '確認待ち 2',
    rows: [r('here|', 'done', { result: '合格' }), r('wt.feat-x|', 'waiting'), r('here|spec-qa', 'waiting')],
    selected: 'here|',
    text: '$(comment-discussion) pipe-in: 確認待ち 2',
  },
  {
    name: '待ちだけ（動き 1。見ているのは合格）',
    rows: [r('here|', 'done', { result: '合格' }), r('wt.feat-x|', 'idle')],
    selected: 'here|',
    text: '$(clock) pipe-in: 動き 1',
  },
  { name: '待ちだけ（動き 2）', rows: [r('here|', 'idle'), r('wt.feat-x|', 'idle')], selected: 'here|', text: '$(clock) pipe-in: 動き 2' },
  {
    name: '動き 2・確認待ち 1',
    rows: [r('here|', 'running'), r('wt.feat-x|', 'running'), r('here|spec-qa', 'waiting')],
    selected: 'here|',
    text: '$(comment-discussion) pipe-in: 動き 2・確認待ち 1',
  },
  {
    name: '待ち 1・確認待ち 1',
    rows: [r('here|', 'idle'), r('wt.feat-x|', 'waiting')],
    selected: 'here|',
    text: '$(comment-discussion) pipe-in: 動き 1・確認待ち 1',
  },
  {
    name: '確認待ちを見ていて、ほかに動いている行',
    rows: [r('here|', 'waiting'), r('wt.feat-x|', 'running')],
    selected: 'here|',
    text: '$(comment-discussion) pipe-in: 動き 1・確認待ち 1',
  },
  { name: '動き 12（10 進の整数）', rows: manyRunning(12), selected: 'here|', text: '$(sync~spin) pipe-in: 動き 12' },
];

test('D0024-AC-12: 件数の text の形：動き N・確認待ち M、0 の項目は省く、アイコンは 確認待ち ＞ 動いている ＞ 待ち（動きだけ・確認待ちだけ・待ちだけ・混ぜた組の表）', () => {
  for (const c of TEXT_CASES) {
    assert.equal(labelOf(c.rows, c.selected).text, c.text, c.name);
  }
});

test('D0024-AC-12: 数える行が選んでいる実行だけ・無いときは、「動き 0」「確認待ち 0」の件数の形を作らない（今のまま通る。守る）', () => {
  const cases: readonly (readonly [string, RunRow[]])[] = [
    ['終わった行だけ', [r('here|', 'done', { result: '合格' }), r('wt.feat-x|', 'done', { result: '不合格' })]],
    ['一覧が空', []],
    ['選んでいる実行が動いている 1 件だけ', [r('here|', 'running')]],
  ];
  for (const [name, rows] of cases) {
    const label = labelOf(rows, 'here|');
    assert.doesNotMatch(label.text, /動き \d|確認待ち \d/, name);
  }
});

// ---- AC-13：text に外から来た文字を入れない ----

test('D0024-AC-13: text は固定の言葉と数字だけ（$(zap)・<script> などを入れたセッション名・段・ブランチ・パイプ名でも同じ）', () => {
  const expected = '$(sync~spin) pipe-in: 動き 2';
  for (const hostile of ['$(zap)', '<script>alert(1)</script>', '**太字**', 'a\nb', '[x](command:pipe-in.showRun)']) {
    const p = { session: hostile, pipe: hostile, stage: hostile, branch: hostile };
    const rows = [r('here|', 'running', p), r('wt.feat-x|', 'running', p)];
    const label = labelOf(rows, 'here|');
    assert.equal(label.text, expected, JSON.stringify(hostile));
    assert.ok(!label.text.includes(hostile), JSON.stringify(hostile));
  }
});

// ---- AC-14：返り値の鍵（守る） ----

test('D0024-AC-14: 返り値の鍵は text と tooltip だけ（件数の形の入力でも・第 2 引数なしでも）（今のまま通る。守る）', () => {
  const countsForm = labelOf(runningAndWaiting(), 'here|');
  const plain = statusBarLabel(runningView(40));
  assert.deepEqual(Object.keys(countsForm).sort(), ['text', 'tooltip']);
  assert.deepEqual(Object.keys(plain).sort(), ['text', 'tooltip']);
});

// ---- AC-16：数えた実行の行 ----

/** 要件定義の例：確認待ち 1・動いている 2（うち 1 つは選んでいる実行でブランチ無し）・終わった 1・archive 1。 */
function exampleRows(): RunRow[] {
  return [
    r('here|', 'waiting', { session: '画面を直す', stage: '要件定義', branch: 'feat/status-counts', updatedMs: t(1) }),
    r('wt.other|', 'running', { session: 'テストを足す', stage: '実装（2 回目）', branch: 'feat/other', updatedMs: t(2) }),
    r('here|diagrams', 'running', { session: '図を作る', stage: '図の生成', branch: null, updatedMs: t(3) }),
    r('here|survey', 'done', { session: '調査', stage: '検証', branch: 'main', result: '合格', updatedMs: t(4) }),
    r(ARCHIVE_KEY, 'done', { session: '前の仕様', stage: '検証', branch: 'main', previous: true, result: '合格', updatedMs: t(5) }),
  ];
}

test('D0024-AC-16: 説明の 1 行目は「pipe-in：動き N・確認待ち M」、続けて数えた実行を「状態の言葉：セッション名（段・ブランチ）」の形で出す', () => {
  const label = labelOf(exampleRows(), 'here|diagrams');
  assert.deepEqual(lines(label).slice(0, 4), [
    'pipe-in：動き 2・確認待ち 1',
    '確認待ち：画面を直す（要件定義・feat/status-counts）',
    '動いている：テストを足す（実装（2 回目）・feat/other）',
    '動いている：図を作る（図の生成）',
  ]);
});

test('D0024-AC-16: 説明の 1 行目は text の「pipe-in: 」より後ろと同じ件数・同じ省き方（0 の項目を出さない。確認待ちだけ・待ちだけ・動き 12 を含む表）', () => {
  for (const c of TEXT_CASES) {
    const counts = c.text.slice(c.text.indexOf(TEXT_HEAD) + TEXT_HEAD.length);
    const first = lines(labelOf(c.rows, c.selected))[0] ?? '';
    assert.equal(first, `pipe-in：${counts}`, c.name);
    assert.doesNotMatch(first, /動き 0|確認待ち 0/, c.name);
  }
});

test('D0024-AC-16: ブランチの無い行（git の外）は「・ブランチ」ごと省く', () => {
  const rows = [
    r('here|', 'running', { session: '前', stage: '設計', branch: null, updatedMs: t(1) }),
    r('wt.feat-x|', 'running', { session: '後', stage: '設計', branch: 'feat/x', updatedMs: t(2) }),
  ];
  const l = lines(labelOf(rows, 'here|'));
  assert.ok(l.includes('動いている：前（設計）'), l.join(' / '));
  assert.ok(l.includes('動いている：後（設計・feat/x）'), l.join(' / '));
});

test('D0024-AC-16: 状態の言葉で始まる行は、数えた実行の 3 件（確認待ち 1・動いている 2）だけ', () => {
  const l = lines(labelOf(exampleRows(), 'here|diagrams'));
  assert.equal(l.filter((x) => /^(確認待ち|動いている|待ち|合格|不合格|終わった)：/.test(x)).length, 3, l.join(' / '));
});

test('D0024-AC-16: 終わった実行（合格・archive）の名前は、件数の形の説明のどの行にも出ない（前提：1 行目が件数の形）', () => {
  const l = lines(labelOf(exampleRows(), 'here|diagrams'));
  assert.equal(l[0], 'pipe-in：動き 2・確認待ち 1', '前提：件数の形になっている');
  assert.ok(!l.some((x) => x.includes('調査') || x.includes('前の仕様')), l.join(' / '));
});

test('D0024-AC-16: 数えた実行は一覧と同じ並び：確認待ち → 動いている → 待ち、同じ状態の中は新しい順（行を入れる順を替えても同じ）', () => {
  const rows = [
    r('here|self', 'done', { session: '自分', result: '合格', updatedMs: t(0) }),
    r('here|idle', 'idle', { session: '待ち行', updatedMs: t(1) }),
    r('here|run-old', 'running', { session: '動き古', updatedMs: t(9) }),
    r('wt.feat-x|w-old', 'waiting', { session: '確認古', updatedMs: t(8) }),
    r('here|run-new', 'running', { session: '動き新', updatedMs: t(2) }),
    r('here|w-new', 'waiting', { session: '確認新', updatedMs: t(4) }),
  ];
  const expected = [
    'pipe-in：動き 3・確認待ち 2',
    '確認待ち：確認新（設計）',
    '確認待ち：確認古（設計）',
    '動いている：動き新（設計）',
    '動いている：動き古（設計）',
    '待ち：待ち行（設計）',
  ];
  const orders: readonly (readonly [string, RunRow[]])[] = [
    ['そのままの順', rows],
    ['逆順', [...rows].reverse()],
    ['並べ替えた順', [rows[3]!, rows[0]!, rows[5]!, rows[1]!, rows[4]!, rows[2]!]],
  ];
  for (const [name, input] of orders) {
    assert.deepEqual(lines(labelOf(input, 'here|self')).slice(0, 6), expected, name);
  }
});

// ---- AC-17：並べるのは 10 件まで ----

test('D0024-AC-17: 説明に並べる数えた実行の上限 STATUS_LINES_LIMIT は 10', async () => {
  const { STATUS_LINES_LIMIT } = await sb();
  assert.equal(STATUS_LINES_LIMIT, 10);
});

test('D0024-AC-17: 並べるのは 10 件まで。超えたら 10 件目のあとに「ほか N 件（パネルの一覧で見られます）」（9・10・11・25 件の表）', () => {
  const cases: readonly (readonly [number, number, string | null])[] = [
    [9, 9, null],
    [10, 10, null],
    [11, 10, 'ほか 1 件（パネルの一覧で見られます）'],
    [25, 10, 'ほか 15 件（パネルの一覧で見られます）'],
  ];
  for (const [n, listed, more] of cases) {
    const rows = Array.from({ length: n }, (_, i) => r(`here|p${i + 1}`, 'running', { session: `実行${i + 1}`, updatedMs: t(i) }));
    const l = lines(labelOf(rows, 'here|p1'));
    assert.equal(l[0], `pipe-in：動き ${n}`, `${n} 件：見出し`);
    assert.equal(l.filter((x) => x.startsWith('動いている：')).length, listed, `${n} 件：並べた数`);
    assert.equal(l[listed], `動いている：実行${listed}（設計）`, `${n} 件：最後に並べた行`);
    assert.equal(l[listed + 1], more ?? l[listed + 1], `${n} 件：10 件目のあと`);
    assert.equal(l.filter((x) => x.startsWith('ほか ')).length, more === null ? 0 : 1, `${n} 件：ほか N 件の行の数`);
    if (more === null) assert.ok(l[listed + 1]?.startsWith('選んでいる実行：'), `${n} 件：ほか N 件が無ければ次は選んでいる実行`);
  }
});

// ---- AC-18：別の worktree を省いているとき ----

test('D0024-AC-18: omittedWorktrees が 1 以上のとき「別の worktree を N 個、省いています（件数に入っていません）」の 1 行。0 なら出さない', () => {
  for (const n of [0, 1, 3, 8]) {
    const l = lines(labelOf(runningAndWaiting(), 'here|', { omittedWorktrees: n }));
    const omitted = l.filter((x) => x.startsWith('別の worktree を'));
    assert.deepEqual(omitted, n === 0 ? [] : [`別の worktree を ${n} 個、省いています（件数に入っていません）`], `省いた数 ${n}`);
    assert.equal(l[0], 'pipe-in：動き 1・確認待ち 1', `省いた数 ${n}：件数の形のまま（省いた分は件数に入れない）`);
  }
});

// ---- AC-19：選んでいる実行 ----

test('D0024-AC-19: 「選んでいる実行：セッション名（状態の言葉）」を、数える行でも数えない行でも出す（確認待ち・動いている・待ち・合格・結果なしの終わった・知らない結果の文字・記録なしの表）', () => {
  const other = r('wt.feat-x|', 'waiting', { session: '他', stage: '設計', branch: 'feat/x' });
  const cases: readonly (readonly [string, RunRow | null, string])[] = [
    ['確認待ち', r('here|', 'waiting', { session: '自分' }), '選んでいる実行：自分（確認待ち）'],
    ['動いている', r('here|', 'running', { session: '自分' }), '選んでいる実行：自分（動いている）'],
    ['待ち', r('here|', 'idle', { session: '自分' }), '選んでいる実行：自分（待ち）'],
    ['合格', r('here|', 'done', { session: '自分', result: '合格' }), '選んでいる実行：自分（合格）'],
    ['不合格', r('here|', 'done', { session: '自分', result: '不合格' }), '選んでいる実行：自分（不合格）'],
    ['結果なしの終わった', r('here|', 'done', { session: '自分', result: null }), '選んでいる実行：自分（終わった）'],
    ['知らない結果の文字', r('here|', 'done', { session: '自分', result: 'SOMETHING_NEW' }), '選んでいる実行：自分（SOMETHING_NEW）'],
    ['記録なし（一覧に行が無い）', null, '選んでいる実行：記録なし'],
  ];
  for (const [name, self, expected] of cases) {
    const rows = self === null ? [other] : [self, other];
    const picked = lines(labelOf(rows, 'here|')).filter((x) => x.startsWith('選んでいる実行：'));
    assert.deepEqual(picked, [expected], name);
  }
});

// ---- AC-20：利用枠 ----

const withoutRateLimits = (): Record<string, unknown> => Object.fromEntries(Object.entries(usageSummaryDict()).filter(([k]) => k !== 'rate_limits'));

const DONE_AND_WAITING = (): RunRow[] => [r('here|', 'done', { session: '自分', result: '合格' }), r('wt.feat-x|', 'waiting', { session: '他' })];

test('D0024-AC-20: rateLimits が 1 つ以上なら「利用枠：5時間枠 2%・7日枠 15%」の 1 行を出す', () => {
  const l = lines(labelOf(DONE_AND_WAITING(), 'here|', { view: finishedWith(usageSummaryDict()) }));
  assert.deepEqual(l.filter((x) => x.startsWith('利用枠')), ['利用枠：5時間枠 2%・7日枠 15%']);
});

test('D0024-AC-20: 使用量の無い記録・rateLimits が空の記録・rate_limits の鍵が無い記録では、件数の形の説明に利用枠の行が無い（ほかの行はそのまま）', () => {
  const rows = DONE_AND_WAITING();
  const expected = ['pipe-in：確認待ち 1', '確認待ち：他（設計）', '選んでいる実行：自分（合格）', `${CLICK}${SUFFIX}`];
  const absent: readonly (readonly [string, PipelineView])[] = [
    ['使用量の無い記録', finishedWith()],
    ['使用量はあるが rateLimits が空の記録', finishedWith({ ...(usageSummaryDict() as Record<string, unknown>), rate_limits: {} })],
    ['使用量はあるが rate_limits の鍵が無い記録', finishedWith(withoutRateLimits())],
  ];
  for (const [name, view] of absent) {
    assert.deepEqual(lines(labelOf(rows, 'here|', { view })), expected, name);
  }
});

// ---- AC-21・AC-29：クリックの案内 ----

interface ClickCase {
  name: string;
  rows: RunRow[];
  selected: string;
  front: boolean;
}

const CLICK_CASES: readonly ClickCase[] = [
  { name: '動いている実行を見ていて、別に確認待ちがある', rows: [r('here|', 'running'), r('wt.feat-x|', 'waiting')], selected: 'here|', front: true },
  { name: '終わった実行（合格）を見ていて、別に確認待ちがある', rows: [r('here|', 'done', { result: '合格' }), r('wt.feat-x|', 'waiting')], selected: 'here|', front: true },
  { name: '待ちの実行を見ていて、別に確認待ちがある', rows: [r('here|', 'idle'), r('wt.feat-x|', 'waiting')], selected: 'here|', front: true },
  { name: '記録なし（一覧に行が無い選び）で、別に確認待ちがある', rows: [r('wt.feat-x|', 'waiting')], selected: 'here|', front: true },
  { name: '確認待ちの実行を見ていて、ほかにも確認待ちがある', rows: [r('here|', 'waiting'), r('wt.feat-x|', 'waiting')], selected: 'here|', front: false },
  { name: '確認待ちの実行を見ていて、ほかは動いている', rows: [r('here|', 'waiting'), r('wt.feat-x|', 'running')], selected: 'here|', front: false },
  { name: '確認待ちが無い（動いている実行が 2 つ）', rows: [r('here|', 'running'), r('wt.feat-x|', 'running')], selected: 'here|', front: false },
  { name: '確認待ちが無い（動いている実行と待ち）', rows: [r('here|', 'running'), r('wt.feat-x|', 'idle')], selected: 'here|', front: false },
];

test('D0024-AC-21: 最後の行は「クリックでパネルを開く」。確認待ちがあり選んでいる実行が確認待ちでないときだけ「（確認待ちの実行を先に出す）」が付く', () => {
  for (const c of CLICK_CASES) {
    const last = lines(labelOf(c.rows, c.selected)).at(-1);
    assert.equal(last, c.front ? `${CLICK}${SUFFIX}` : CLICK, c.name);
  }
});

test('D0024-AC-29: 「（確認待ちの実行を先に出す）」の有無は frontWaitingKey の結果と一致する（入力の表）', async () => {
  const { frontWaitingKey } = await dom();
  for (const c of CLICK_CASES) {
    const last = lines(labelOf(c.rows, c.selected)).at(-1);
    const front = frontWaitingKey(c.rows, c.selected) !== null;
    assert.equal(front, c.front, `${c.name}：前提（frontWaitingKey の結果）`);
    assert.equal(last, front ? `${CLICK}${SUFFIX}` : CLICK, c.name);
  }
});

// ---- AC-22：全部の行が出る入力で、説明の全体を比べる ----

test('D0024-AC-22: 全部の行が出る入力で、説明の全体の文字を比べる（見出し → 数えた実行 → ほか N 件 → 別の worktree の省略 → 選んでいる実行 → 利用枠 → クリックの案内）', () => {
  const running = Array.from({ length: 11 }, (_, i) =>
    r(`here|run${pad(i + 1)}`, 'running', { session: `実行${pad(i + 1)}`, stage: '実装', branch: `feat/b${pad(i + 1)}`, updatedMs: t(10 + i) }),
  );
  const rows = [
    r('here|', 'done', { session: '仕様の QA を回す', stage: '検証', branch: 'main', result: '合格', updatedMs: t(30) }),
    r('wt.feat-x|', 'waiting', { session: 'CSV 出力を足す', stage: '図を描く', branch: 'feat/export-csv', updatedMs: t(1) }),
    ...running,
  ];
  const label = labelOf(rows, 'here|', { view: finishedWith(usageSummaryDict()), omittedWorktrees: 3 });
  const expected = [
    'pipe-in：動き 11・確認待ち 1',
    '確認待ち：CSV 出力を足す（図を描く・feat/export-csv）',
    ...Array.from({ length: 9 }, (_, i) => `動いている：実行${pad(i + 1)}（実装・feat/b${pad(i + 1)}）`),
    'ほか 2 件（パネルの一覧で見られます）',
    '別の worktree を 3 個、省いています（件数に入っていません）',
    '選んでいる実行：仕様の QA を回す（合格）',
    '利用枠：5時間枠 2%・7日枠 15%',
    `${CLICK}${SUFFIX}`,
  ];
  assert.equal(label.tooltip, expected.join('\n'));
});

// ---- AC-23：外から来た文字を 1 行のプレーンな文字にする ----

const PLAIN_CASES: readonly (readonly [string, string, string])[] = [
  ['LF', 'a\nb', 'a b'],
  ['CRLF', 'a\r\nb', 'a b'],
  ['CR', 'a\rb', 'a b'],
  ['ESC（U+001B）', 'a\u001bb', 'a b'],
  ['RLO（U+202E）', `a${cp(0x202e)}b`, 'a b'],
  ['NUL（U+0000）', 'a\u0000b', 'a b'],
  ['DEL（U+007F）', 'a\u007fb', 'a b'],
  ['NEL（U+0085）', 'a\u0085b', 'a b'],
  ['C1 の終わり（U+009F）', 'a\u009fb', 'a b'],
  ['行区切り（U+2028）', `a${cp(0x2028)}b`, 'a b'],
  ['段落区切り（U+2029）', `a${cp(0x2029)}b`, 'a b'],
  ['全角空白の連続', 'a　　b', 'a b'],
  ['空白の連続（半角・タブ・全角）', 'a \t　 b', 'a b'],
  ['前後の改行と空白', '\n  a b \r\n', 'a b'],
  ['半角空白 1 つだけ', ' ', '—'],
  ['空文字', '', '—'],
  ['改行だけ', '\n\n', '—'],
  ['制御文字だけ', '\u001b\u007f\u0085', '—'],
  ['向きを変える文字だけ（U+202E・U+2066・U+2069）', cp(0x202e, 0x2066, 0x2069), '—'],
  ['60 文字ちょうど', 'あ'.repeat(60), 'あ'.repeat(60)],
  ['61 文字', 'あ'.repeat(61), `${'あ'.repeat(59)}…`],
  ['改行で 2 つに分かれた 61 文字（空白に替えたあとの文字数で省く）', `${'あ'.repeat(30)}\n${'い'.repeat(30)}`, `${'あ'.repeat(30)} ${'い'.repeat(28)}…`],
  ['絵文字 60 個（コードポイントで数える）', '😀'.repeat(60), '😀'.repeat(60)],
  ['絵文字 61 個（コードポイントで数える）', '😀'.repeat(61), `${'😀'.repeat(59)}…`],
  ['1 万文字', 'あ'.repeat(10_000), `${'あ'.repeat(59)}…`],
  ['ふつうの名前', '仕様の QA を回す', '仕様の QA を回す'],
  ['$(zap) はそのまま', '$(zap)', '$(zap)'],
];

test('D0024-AC-23: plainLine：制御文字・行区切り・向きを変える文字を空白にし、前後を落とし、連続を 1 つにし、60 文字を超えたら 59 文字＋「…」、空は「—」（表）', async () => {
  const { plainLine } = await sb();
  for (const [name, input, expected] of PLAIN_CASES) {
    assert.equal(plainLine(input), expected, name);
  }
});

const range = (from: number, to: number): number[] => Array.from({ length: to - from + 1 }, (_, i) => from + i);

test('D0024-AC-23: plainLine が空白に替える範囲：U+0000〜U+001F・U+007F〜U+009F・U+2028・U+2029・U+200E・U+200F・U+202A〜U+202E・U+2066〜U+2069 のどれも', async () => {
  const { plainLine } = await sb();
  const replaced = [...range(0x00, 0x1f), ...range(0x7f, 0x9f), 0x2028, 0x2029, 0x200e, 0x200f, ...range(0x202a, 0x202e), ...range(0x2066, 0x2069)];
  for (const code of replaced) {
    const ch = String.fromCodePoint(code);
    const name = `U+${code.toString(16).toUpperCase().padStart(4, '0')}`;
    assert.equal(plainLine(`a${ch}b`), 'a b', name);
    assert.equal(plainLine(`a${ch}${ch}b`), 'a b', `${name} の連続`);
  }
});

test('D0024-AC-23: plainLine は、列挙した範囲のすぐ外の文字（U+00A0・U+200D・U+2010・U+202F・U+2065・U+206A）を替えない', async () => {
  const { plainLine } = await sb();
  for (const code of [0x00a0, 0x200d, 0x2010, 0x202f, 0x2065, 0x206a]) {
    const text = `a${String.fromCodePoint(code)}b`;
    assert.equal(plainLine(text), text, `U+${code.toString(16).toUpperCase().padStart(4, '0')}`);
  }
});

const HOSTILE: readonly (readonly [string, string, string])[] = [
  ['LF を含む', 'a\nb', 'a b'],
  ['CRLF を含む', 'a\r\nb', 'a b'],
  ['ESC を含む', 'a\u001b[31mb', 'a [31mb'],
  ['行区切り（U+2028）を含む', `a${cp(0x2028)}b`, 'a b'],
  ['向きを変える文字（U+202E）を含む', `a${cp(0x202e)}b`, 'a b'],
  ['61 文字', 'あ'.repeat(61), `${'あ'.repeat(59)}…`],
];

test('D0024-AC-23: 改行などを含むセッション名・今の段・ブランチ名を渡しても、説明の行の数は変わらず、1 行のプレーンな文字で出る', () => {
  const fields = ['session', 'stage', 'branch'] as const;
  for (const field of fields) {
    for (const [name, raw, clean] of HOSTILE) {
      const pick = (v: string): Partial<RunRow> => (field === 'session' ? { session: v } : field === 'stage' ? { stage: v } : { branch: v });
      const self = { session: '自分', stage: '設計', branch: 'main' };
      const rows = [r('here|', 'running', { ...self, ...pick(raw) }), r('wt.feat-x|', 'waiting', { session: '他', stage: '図', branch: 'feat/x' })];
      const c = { ...self, ...pick(clean) } as { session: string; stage: string; branch: string };
      const expected = [
        'pipe-in：動き 1・確認待ち 1',
        '確認待ち：他（図・feat/x）',
        `動いている：${c.session}（${c.stage}・${c.branch}）`,
        `選んでいる実行：${c.session}（動いている）`,
        `${CLICK}${SUFFIX}`,
      ];
      assert.deepEqual(lines(labelOf(rows, 'here|')), expected, `${field}：${name}`);
    }
  }
});

test('D0024-AC-23: 結果の言葉（知らない final の文字）に改行を含んでも、「選んでいる実行」の行は 1 行で、plainLine を通る', () => {
  const rows = [r('here|', 'done', { session: '自分', result: 'BAD\nSTATE\u001b' }), r('wt.feat-x|', 'waiting', { session: '他' })];
  const picked = lines(labelOf(rows, 'here|')).filter((x) => x.startsWith('選んでいる実行：'));
  assert.deepEqual(picked, ['選んでいる実行：自分（BAD STATE）']);
});

/** rate_limits に five_hour と、鍵 key の枠（使用率 50%）を持つ使用量。 */
function usageWithKey(key: string): unknown {
  const window = { first: 0.1, last: 0.5, resets_at: 1792591200, peak: 0.5, reset_seen: false };
  return {
    ...(usageSummaryDict() as Record<string, unknown>),
    rate_limits: { five_hour: { first: 0.12, last: 0.02, resets_at: 1792170000, peak: 0.13, reset_seen: true }, [key]: window },
  };
}

test('D0024-AC-23: 利用枠の名前（rate_limits の鍵）も plainLine を通る：改行・ESC・$(zap)・61 文字以上の鍵でも、説明の行の数は変わらず、「利用枠：」の行は 1 行', () => {
  const rows = DONE_AND_WAITING();
  const baseline = lines(labelOf(rows, 'here|', { view: finishedWith(usageWithKey('plain_key')) }));
  assert.deepEqual(baseline.filter((x) => x.startsWith('利用枠')), ['利用枠：5時間枠 2%・plain_key 50%'], '対照：ふつうの鍵');
  const keys: readonly (readonly [string, string, string])[] = [
    ['改行を含む鍵', 'a\nb', 'a b'],
    ['ESC を含む鍵', 'a\u001bb', 'a b'],
    ['$(zap) の鍵', '$(zap)', '$(zap)'],
    ['向きを変える文字を含む鍵', `x${cp(0x202e)}y`, 'x y'],
    ['61 文字の鍵', 'k'.repeat(61), `${'k'.repeat(59)}…`],
  ];
  for (const [name, key, clean] of keys) {
    const l = lines(labelOf(rows, 'here|', { view: finishedWith(usageWithKey(key)) }));
    assert.deepEqual(l.filter((x) => x.startsWith('利用枠')), [`利用枠：5時間枠 2%・${clean} 50%`], name);
    assert.equal(l.length, baseline.length, `${name}：説明の行の数`);
  }
});

test('D0024-AC-23: 今の出し方（第 2 引数なし）の利用枠の名前は素のまま出る（今のまま通る。守る）', () => {
  const label = statusBarLabel(finishedWith(usageWithKey('a\nb')));
  assert.ok(label.tooltip.includes('・5時間枠 2%・a\nb 50%'), label.tooltip);
});

// ---- AC-24：説明は文字列のまま ----

test('D0024-AC-24: 説明は文字列のまま（MarkdownString でない）。「**太字**」「[x](command:…)」などを名前に入れても、そのまま文字で出る', () => {
  const names = ['**太字**', '[x](command:pipe-in.showRun)', '[x](https://example.com)', '`code`', '<b>x</b>', '# 見出し'];
  for (const name of names) {
    const rows = [r('here|', 'running', { session: name, stage: '設計', branch: 'main' }), r('wt.feat-x|', 'waiting', { session: '他', stage: '図', branch: 'feat/x' })];
    const label = labelOf(rows, 'here|');
    assert.equal(typeof label.tooltip, 'string', name);
    const l = lines(label);
    assert.ok(l.includes(`動いている：${name}（設計・main）`), `${name}：${l.join(' / ')}`);
    assert.ok(l.includes(`選んでいる実行：${name}（動いている）`), `${name}：${l.join(' / ')}`);
  }
});

// ---- AC-44：古い形・壊れた記録でも例外を出さない ----

const BROKEN_ROW = summarizeRun(
  { key: 'here|spec-qa', id: 'spec-qa', branch: null, other: false, memoHead: null, previous: false, stateJson: '{壊れた', stageLogs: [] },
  clock,
);

test('D0024-AC-44: 前提：壊れた state.json の行は、待ち・段は「—」・セッション名はフォルダ名になる（今のまま通る。守る）', () => {
  assert.equal(BROKEN_ROW.state, 'idle');
  assert.equal(BROKEN_ROW.stage, '—');
  assert.equal(BROKEN_ROW.session, 'spec-qa');
});

// 「無い」の表し方は RunRow の型に合わせる：quietSec は省ける項目なので、項目ごと省く行と null の行を試す。
// branch は null（git の外）、session は空文字で表す。型は session: string・branch: string | null で、summarizeRun は必ず埋めるので、
// 項目そのものが undefined の行は、設計が想定していない形として試さない。
test('D0024-AC-44: 壊れた・古い形の行（quietSec・branch が無い、session が空・1 万文字、壊れた state.json の待ち）でも、例外を出さず件数の形を作る', () => {
  const other = (p: Partial<RunRow>): RunRow => r('wt.feat-x|', 'running', { session: '他', stage: '実装', branch: 'main', ...p });
  const cases: readonly (readonly [string, RunRow, string])[] = [
    ['quietSec の項目が無い行', other({}), '動いている：他（実装・main）'],
    ['quietSec が null の行', other({ quietSec: null }), '動いている：他（実装・main）'],
    ['branch が無い（null）行', other({ branch: null }), '動いている：他（実装）'],
    ['session が空の行', other({ session: '' }), '動いている：—（実装・main）'],
    ['session が 1 万文字の行', other({ session: 'あ'.repeat(10_000) }), `動いている：${'あ'.repeat(59)}…（実装・main）`],
    ['stage が空の行', other({ stage: '' }), '動いている：他（—・main）'],
    ['branch が 1 万文字の行', other({ branch: 'あ'.repeat(10_000) }), `動いている：他（実装・${'あ'.repeat(59)}…）`],
    ['state.json が壊れて待ちになった行', BROKEN_ROW, '待ち：spec-qa（—）'],
  ];
  for (const [name, broken, line] of cases) {
    const rows = [r('here|', 'running', { session: '自分', stage: '設計', branch: 'main' }), broken];
    const label = labelOf(rows, 'here|');
    assert.equal(label.text, '$(sync~spin) pipe-in: 動き 2', name);
    assert.ok(lines(label).includes(line), `${name}：${lines(label).join(' / ')}`);
  }
});

test('D0024-AC-44: 数える行の引数を省いた呼び出し（statusBarLabel(view)）は、壊れた記録でも例外を出さず、今までと同じ結果（今のまま通る。守る）', () => {
  const brokenJson = ['{壊れた', '[]', '"文字"', 'null', '{}', '{"runs": 5, "final": 7}'];
  for (const json of brokenJson) {
    const view = buildPipelineView(snapshot({ stateJson: json }), clock);
    assert.deepEqual(statusBarLabel(view), { text: '$(circuit-board) pipe-in', tooltip: `pipe-in・合計 $0.000\n${CLICK}` }, json);
  }
});
