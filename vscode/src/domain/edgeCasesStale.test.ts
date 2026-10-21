// 止まっているかもしれない実行の印（D0021）：古い形の記録（AC-35）と、壊れた・形の違う値（AC-36）。
// 組み立てから HTML まで、例外を投げず、読めないものには印を出さない。
// 「出ない側」の確かめには、必ず対照（出る条件だけを足した同じ写し）を同じテストの中で確かめる（決定の記録 D0021）。
// AC-36 の表は「印が出ない」ものだけ。途中の行が切れただけのログ（Prompt は読める）は壊れたログではないので、境目の別のテストにしている。
// 新しい項目（quietSec・目安の引数）は、テスト先行のときに「まだ無い」ことで落ちるように、読み取り用の関数と型を逃がした呼び出しで読む（実装後は型に入っている）。
// HTML は、スクリプトと CSS を含まない本体（renderViewBody）の文字を調べる（パネルのスクリプトと CSS には、印の名前そのものが入るため）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { PipelineView, WorkDirSnapshot } from './pipelineView.ts';
import type { RunListView } from './runList.ts';
import { renderPanelHtml, renderViewBody } from '../view/panelHtml.ts';
import {
  BAD_MTIME_VALUES,
  BROKEN_LOG_KINDS,
  OLD_SHAPE_KINDS,
  QUIET_OVER_SEC,
  STALE_AFTER_SEC,
  badMtimeSnapshot,
  brokenLogSnapshot,
  mtimeAgo,
  oldShapeSnapshot,
  staleParts,
  staleSnapshot,
} from '../test/staleFixtures.ts';
import type { BrokenLogKind, OldShapeKind } from '../test/staleFixtures.ts';

// ---- 道具 ----

const quietOf = (x: object): unknown => (x as { quietSec?: unknown }).quietSec;

type BodyFn = (view: PipelineView, list: RunListView | null | undefined, staleAfterSec: number | null) => string;
type PanelFn = (view: PipelineView, nonce: string, list: RunListView | null | undefined, staleAfterSec: number | null) => string;
// 目安（staleAfterSec）の引数は、実装の段で足される。それまでの型のつなぎ
const renderBody = renderViewBody as unknown as BodyFn;
const renderPage = renderPanelHtml as unknown as PanelFn;

/** 動いている帯の quietSec（帯が無い・項目が無いときは null）。 */
function bandQuiet(view: PipelineView): unknown {
  const row = view.gantt.rows.find((r) => r.run?.live === true);
  return row?.run == null ? null : (quietOf(row.run) ?? null);
}

interface Built {
  view: PipelineView;
  row: unknown;
  /** パネルの本体（スクリプト・CSS を含まない）。目安 600 */
  body: string;
}

/** 写しから、図の状態・行・本体の HTML を組み立てる（パネルの HTML 全体も組み立てて、投げないことも確かめる）。 */
function build(snap: WorkDirSnapshot, nowSec = 0): Built {
  const { view, row, list } = staleParts(snap, nowSec);
  const page = renderPage(view, 'n', list, STALE_AFTER_SEC);
  assert.ok(page.length > 0);
  return { view, row: quietOf(row), body: renderBody(view, list, STALE_AFTER_SEC) };
}

/** html の中の開始タグ <tag ...> のうち、class に cls を持つもの。 */
function openTags(html: string, tag: string, cls: string): string[] {
  const found: string[] = [];
  for (const m of html.matchAll(new RegExp(`<${tag}\\b[^>]*>`, 'g'))) {
    const attr = /\bclass="([^"]*)"/.exec(m[0]);
    if (attr !== null && attr[1]!.split(/\s+/).includes(cls)) found.push(m[0]);
  }
  return found;
}

const hasMark = (tag: string, quiet: number, after: number): boolean =>
  tag.includes(`data-quiet="${quiet}"`) && tag.includes(`data-stale-after="${after}"`);

/** 動いている段（design）へ入る、流れる矢印（line.edge.is-flowing）。 */
const flowingArrows = (body: string): string[] => openTags(body, 'line', 'edge').filter((t) => /\bclass="[^"]*\bis-flowing\b/.test(t));

type Surface = '節' | '入る矢印' | '一覧の行' | '詳細のバッジ' | '詳細の知らせ' | '時系列の帯';

/** 面ごとに、印（data-quiet と data-stale-after を持つ要素）が出ているか。 */
function markedSurfaces(body: string, quiet: number, after: number): Record<Surface, boolean> {
  const has = (tags: string[]): boolean => tags.some((t) => hasMark(t, quiet, after));
  return {
    節: has(openTags(body, 'g', 'node').filter((t) => t.includes('data-node="design"'))),
    入る矢印: has(flowingArrows(body)),
    一覧の行: has(openTags(body, 'button', 'run-row')),
    詳細のバッジ: has(openTags(body, 'span', 'stale-badge')),
    詳細の知らせ: has(openTags(body, 'div', 'stale-notice').filter((t) => /\brole="status"/.test(t))),
    時系列の帯: has(openTags(body, 'div', 'g-row')),
  };
}

/** 印の属性・印の要素のどれかが本体に出ているか。 */
const ANY_MARK = /data-quiet|data-stale-after|node-stale|run-stale|stale-badge|stale-notice|g-stalled/;

// ---- AC-35：古い形の記録 ----

interface OldShape {
  label: string;
  /** 入る矢印（is-flowing と属性）が出るか */
  arrow: boolean;
  /** 時系列の動いている帯の行に属性が出るか */
  gantt: boolean;
}

// 設計「古いものを読んだとき」の表：矢印と時系列の帯が出るかは、古い形の種類で違う
const OLD_SHAPES: Readonly<Record<OldShapeKind, OldShape>> = {
  noAt: { label: 'Prompt に at が無い古い', arrow: false, gantt: false },
  noStartedAt: { label: 'started_at が無い古い', arrow: true, gantt: true },
  noStages: { label: 'stages が無い古い', arrow: true, gantt: true },
};

const ALWAYS: readonly Surface[] = ['節', '一覧の行', '詳細のバッジ', '詳細の知らせ'];

for (const kind of OLD_SHAPE_KINDS) {
  const { label, arrow, gantt } = OLD_SHAPES[kind];

  test(`D0021-AC-35: ${label}記録でも、state.json が読めてログの更新時刻が読めれば、view・動いている段の節・行の quietSec が出る`, () => {
    const built = build(oldShapeSnapshot(kind));
    assert.equal(built.view.runningStage, 'design');
    assert.equal(quietOf(built.view), QUIET_OVER_SEC);
    assert.equal(quietOf(built.view.nodes.find((n) => n.id === 'design')!), QUIET_OVER_SEC);
    assert.equal(built.row, QUIET_OVER_SEC);
  });

  test(`D0021-AC-35: ${label}記録の、時系列の動いている帯の quietSec は ${gantt ? QUIET_OVER_SEC : '無し（帯が無い）'}`, () => {
    const view = build(oldShapeSnapshot(kind)).view;
    assert.equal(view.gantt.hasTimes, gantt, '時系列の「時刻の記録」の有無は、今までどおり');
    // 対照：新しい形の記録（at・started_at・stages がそろう）の帯には出る
    assert.equal(bandQuiet(build(staleSnapshot()).view), QUIET_OVER_SEC);
    assert.equal(bandQuiet(view), gantt ? QUIET_OVER_SEC : null);
  });

  for (const surface of ALWAYS) {
    test(`D0021-AC-35: ${label}記録でも、${surface}の印が出る`, () => {
      const marks = markedSurfaces(build(oldShapeSnapshot(kind)).body, QUIET_OVER_SEC, STALE_AFTER_SEC);
      assert.equal(marks[surface], true);
    });
  }

  test(`D0021-AC-35: ${label}記録では、入る矢印は ${arrow ? '流れて（is-flowing）印の属性が付く' : '元から流れず（is-flowing が無い）、属性も付かない（対照：節には印が出る）'}`, () => {
    const body = build(oldShapeSnapshot(kind)).body;
    assert.equal(flowingArrows(body).length, arrow ? 1 : 0, '流れる矢印（is-flowing）の数は、今までどおり');
    const marks = markedSurfaces(body, QUIET_OVER_SEC, STALE_AFTER_SEC);
    assert.equal(marks['節'], true, '対照：節には印が出ている');
    assert.equal(marks['入る矢印'], arrow);
  });

  test(`D0021-AC-35: ${label}記録では、時系列の行の属性は ${gantt ? '出る' : '出ない（「時刻の記録がありません」のまま。対照：節には印が出る）'}`, () => {
    const body = build(oldShapeSnapshot(kind)).body;
    assert.equal(body.includes('時刻の記録がありません'), !gantt, '時系列の「時刻の記録がありません」は、今までどおり');
    const marks = markedSurfaces(body, QUIET_OVER_SEC, STALE_AFTER_SEC);
    assert.equal(marks['節'], true, '対照：節には印が出ている');
    assert.equal(marks['時系列の帯'], gantt);
  });
}

test('D0021-AC-35: Prompt に at が無い記録は経過の要素（D0017）が出ないが、節の印（別の要素）は出る', () => {
  const body = build(oldShapeSnapshot('noAt')).body;
  assert.doesNotMatch(body, /class="node-detail"[^>]*>経過/, '経過の要素は出ない（D0017-AC-19）');
  assert.match(body, /class="node-stale"/, '節の印が出ている');
});

test('D0021-AC-35: state.json が読めない古い記録（ログだけ）は、ログの更新時刻が読めても何も出ない（対照：読める記録は出る）', () => {
  const noState: WorkDirSnapshot = { ...oldShapeSnapshot('noStages'), stateJson: null };
  const built = build(noState);
  assert.equal(built.view.runningStage, 'design', '動いているログは拾われる');
  const control = build(oldShapeSnapshot('noStages'));
  assert.equal(quietOf(control.view), QUIET_OVER_SEC);
  assert.equal(quietOf(built.view), null);
  assert.equal(built.row, null);
  assert.doesNotMatch(built.body, ANY_MARK);
});

// ---- AC-36：壊れた・形の違う値 ----

for (const [label, value] of BAD_MTIME_VALUES) {
  test(`D0021-AC-36: 全ログの mtimeMs が${label}でも、組み立てから HTML まで例外を投げず、印は出ない（対照：数なら出る）`, () => {
    let built: Built | undefined;
    assert.doesNotThrow(() => {
      built = build(badMtimeSnapshot(value));
    });
    assert.equal(built!.view.runningStage, 'design', '動いているログは今までどおり拾われる');

    const control = build(badMtimeSnapshot(mtimeAgo(QUIET_OVER_SEC)));
    assert.equal(quietOf(control.view), QUIET_OVER_SEC);
    assert.match(control.body, /data-quiet="612"/);

    assert.equal(quietOf(built!.view), null);
    assert.equal(built!.row, null);
    assert.equal(bandQuiet(built!.view), null);
    assert.doesNotMatch(built!.body, ANY_MARK);
  });
}

// 壊れたログ：Prompt の行が読めず、動いているログが無い扱いになるもの。
// 途中の行が切れただけで Prompt の読めるログ（truncated）は壊れたログではないので、この表に入れない（下の別のテスト）。
const BROKEN_LOG_TEXT: Readonly<Record<Exclude<BrokenLogKind, 'truncated'>, string>> = {
  garbage: '壊れた行ばかりのログ（Prompt が読めない）',
  empty: '空のログ（起動直後で、まだ何も出ていない）',
  noPrompt: 'Prompt の行が無いログ',
};

for (const kind of BROKEN_LOG_KINDS) {
  if (kind === 'truncated') continue;
  const text = BROKEN_LOG_TEXT[kind];
  test(`D0021-AC-36: ${text}でも、組み立てから HTML まで例外を投げず、動いているログが無い扱いで印は出ない（対照：正しい中身なら出る）`, () => {
    let built: Built | undefined;
    assert.doesNotThrow(() => {
      built = build(brokenLogSnapshot(kind));
    });
    assert.equal(built!.view.runningStage, null, '動いているログが無い扱いは、今までどおり');

    const control = build(staleSnapshot());
    assert.equal(quietOf(control.view), QUIET_OVER_SEC);
    assert.match(control.body, /data-quiet="612"/);

    assert.equal(quietOf(built!.view), null);
    assert.equal(built!.row, null);
    assert.doesNotMatch(built!.body, ANY_MARK);
  });
}

// 壊れたログとの境目：書き込みの途中のログは、最後の行が切れているのが普通。Prompt が読めるなら壊れたログ扱いにしない。
test('D0021-AC-36: 途中の行が切れただけで Prompt の読めるログは、壊れたログではなく動いているログのまま（例外なし。印の元は出る。対照：Prompt の読めない壊れたログは出ない）', () => {
  let truncated: Built | undefined;
  assert.doesNotThrow(() => {
    truncated = build(brokenLogSnapshot('truncated'));
  });
  assert.equal(truncated!.view.runningStage, 'design', '動いているログのまま');
  assert.equal(quietOf(truncated!.view), QUIET_OVER_SEC);
  assert.equal(truncated!.row, QUIET_OVER_SEC);
  assert.match(truncated!.body, /data-quiet="612"/);

  const garbage = build(brokenLogSnapshot('garbage'));
  assert.equal(garbage.view.runningStage, null, '対照：Prompt の読めない壊れたログは、動いているログが無い扱い');
  assert.equal(quietOf(garbage.view), null);
  assert.doesNotMatch(garbage.body, ANY_MARK);
});
