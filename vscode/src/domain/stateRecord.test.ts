// D0080：記録（state.json）の空の値の決まり（「測れた」「取れない」の2通り）と、版の鍵 schema を、拡張が読む側から確かめる。
// 共通の表 tests/fixtures/state_record.json を本体のテスト（tests/test_state_schema.py）と同じに読む（test/stateRecordFixtures.ts）。
// 拡張の読む側のコードは変えない見込み：新しい形の開発用の記録は usage_summary.available === false で、会話の道と同じ道を通る。
// そのため、ここのテストの多くは「今のまま通る。守る」。読む側に零を出す所が見つかったら、ここが落ちる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPipelineView } from './pipelineView.ts';
import { parseRunRecord } from './runRecord.ts';
import { UNAVAILABLE_COST_TEXT, summarizeRun } from './runList.ts';
import type { RunListView } from './runList.ts';
import { renderFlowSvg } from '../view/flowSvg.ts';
import { renderPanelHtml } from '../view/panelHtml.ts';
import { emptyListFor, renderShell } from '../view/shellHtml.ts';
import { statusBarLabel } from '../view/statusBar.ts';
import { clockAt } from '../test/liveFixtures.ts';
import { usageUnavailableOf } from '../test/chatFixtures.ts';
import {
  DEV_REASON,
  NO_SCHEMA,
  ODD_SCHEMA_VALUES,
  WRITER_KINDS,
  legacyDevJson,
  legacyDevSnapshot,
  loadStateTable,
  stateRecord,
  stateRecordJson,
  stateRecordSnapshot,
} from '../test/stateRecordFixtures.ts';
import type { WriterKind } from '../test/stateRecordFixtures.ts';

const MONEY = /\$\d/;

const rowOf = (text: string | null) =>
  summarizeRun({ key: 'here|', id: '', branch: null, other: false, memoHead: null, previous: false, stageLogs: [], stateJson: text }, clockAt(0)) as unknown as {
    costText: string;
    costUsd: number | null;
  };

function listWith(stateJson: string): RunListView {
  const row = summarizeRun({ key: 'here|', id: '', branch: null, other: false, memoHead: null, previous: false, stageLogs: [], stateJson }, clockAt(0));
  return { rows: [row], selected: row.key, omitted: [], omittedWorktrees: 0, workDir: '/w' };
}

const UNAVAILABLE_KINDS: readonly WriterKind[] = ['dev', 'chat'];

// ---- AC-09：共通の表 ----

test('D0080-AC-09: 共通の表の形を、sdk・dev・chat の3つで組んだ記録が守り、schema が最初の鍵で、書き手の印（driver）が表のとおり', () => {
  const table = loadStateTable();
  assert.equal(table.schema, 1);
  assert.deepEqual([...WRITER_KINDS].sort(), Object.keys(table.kinds).sort());
  for (const kind of WRITER_KINDS) {
    const row = table.kinds[kind];
    const state = stateRecord(kind);
    assert.deepEqual(Object.keys(state), row.keys, `${kind} の鍵の並び`);
    assert.equal(row.keys[0], 'schema', `${kind} の表は schema が先頭`);
    assert.equal(state.schema, 1);
    const record = parseRunRecord(JSON.stringify(state));
    assert.equal(record.hasDriver, row.driver !== null, `${kind}: driver の有無`);
  }
});

test('D0080-AC-09: 測れた形（sdk）は費用と使用量を数と集計で読み、取れない形（dev・chat）は費用を持たず理由つきの「取れない」で読む', () => {
  const sdk = parseRunRecord(stateRecordJson('sdk'));
  assert.equal(sdk.totalCostUsd, 0.02);
  assert.notEqual(sdk.usage, null);
  assert.equal(usageUnavailableOf(sdk), null);
  assert.deepEqual(sdk.stageRuns.map((r) => r.costUsd), [0.01, 0.01]);
  for (const kind of UNAVAILABLE_KINDS) {
    const record = parseRunRecord(stateRecordJson(kind));
    assert.equal(record.usage, null, `${kind}: 零の表を作らない`);
    assert.equal(usageUnavailableOf(record), DEV_REASON, `${kind}: 理由を持つ`);
    assert.equal(record.stageRuns.length, 2);
  }
});

test('D0080-AC-09: 表を読む補助が組む記録は、取れない形で runs[].cost_usd が null・metrics の鍵なし、測れた形で数と metrics あり（表の値の種類のとおり）', () => {
  for (const kind of WRITER_KINDS) {
    const row = loadStateTable().kinds[kind];
    const runs = stateRecord(kind).runs as Record<string, unknown>[];
    for (const run of runs) {
      assert.equal(run.cost_usd === null, row.run_cost_usd === 'null', `${kind}: cost_usd`);
      assert.equal('metrics' in run, row.run_metrics === 'present', `${kind}: metrics の鍵`);
    }
  }
});

// ---- AC-07：古い記録は今までどおり ----

test('D0080-AC-07: schema の無い古い開発用の記録は、一覧の費用が今までどおり「$0.000」で、取れない印を持たない（変換しない。今のまま通る。守る）', () => {
  const row = rowOf(legacyDevJson({ final: 'PASSED' }));
  assert.equal(row.costText, '$0.000');
  assert.equal(row.costUsd, 0);
  const record = parseRunRecord(legacyDevJson());
  assert.equal(usageUnavailableOf(record), null);
  assert.equal(record.totalCostUsd, 0);
  assert.equal(record.usage, null);
  assert.deepEqual(record.stageRuns.map((r) => r.costUsd), [0, 0]);
  assert.equal(record.hasDriver, true);
});

test('D0080-AC-07: schema の無い古い開発用の記録のパネルは、今までどおり費用が $0.000 で出る（今のまま通る。守る）', () => {
  const view = buildPipelineView(legacyDevSnapshot({ final: 'PASSED' }));
  assert.equal(usageUnavailableOf(view), null);
  assert.equal(view.totalCostUsd, 0);
  const html = renderShell(view, emptyListFor(view));
  assert.match(html, /\$0\.000/);
  assert.doesNotMatch(html, /使用量は取れません/);
});

// ---- AC-11：開発用の新しい記録は「取れない」 ----

test('D0080-AC-11: 開発用の新しい記録の一覧の費用は「取れない」で「$0.000」が出ない（実績の数 costUsd も無し）', () => {
  const row = rowOf(stateRecordJson('dev', { final: 'PASSED' }));
  assert.equal(row.costText, UNAVAILABLE_COST_TEXT);
  assert.equal(row.costText, '取れない');
  assert.doesNotMatch(row.costText, MONEY);
  assert.equal(row.costUsd, null, '前の実績に 0 ドルを渡さない');
});

test('D0080-AC-11: 開発用の新しい記録のパネルは、費用が「取れない」で、使用量の節が「使用量は取れません（理由）」になり、零の表と $ の数が出ない', () => {
  const view = buildPipelineView(stateRecordSnapshot('dev', { final: 'PASSED' }));
  assert.equal(usageUnavailableOf(view), DEV_REASON);
  assert.equal(view.usage, null);
  assert.equal(view.stageCosts, null);
  const html = renderShell(view, listWith(stateRecordJson('dev', { final: 'PASSED' })));
  assert.doesNotMatch(html, MONEY, '$ の数が出ている');
  assert.match(html, /費用[^]*?取れ/);
  const start = html.indexOf('data-detail-panel="usage"');
  assert.ok(start >= 0, '使用量のパネルの枠はある');
  const end = html.indexOf('</main>', start);
  const panel = html.slice(start, end < 0 ? undefined : end);
  assert.match(panel, /使用量は取れません/);
  assert.ok(panel.includes(DEV_REASON), '理由の文が出る');
  assert.doesNotMatch(panel, /usage-table/);
  assert.doesNotMatch(panel, /段ごとの費用/);
});

test('D0080-AC-11: 開発用の新しい記録の図の段の節は、費用が 0 でなく無し（null）で、$ の数もターン数も出ない', () => {
  const view = buildPipelineView(stateRecordSnapshot('dev', { final: 'PASSED' }));
  const stages = view.nodes.filter((n) => n.metrics !== null);
  assert.ok(stages.length >= 2, '実行のある段の節がある');
  for (const node of stages) assert.equal(node.metrics?.costUsd, null, `${node.id} の費用は無し（null）`);
  const svg = renderFlowSvg(view.nodes, new Set(), null);
  assert.doesNotMatch(svg, MONEY);
  assert.doesNotMatch(svg, /ターン/);
});

test('D0080-AC-11: 開発用の新しい記録のステータスバーとページ全体にも $ の数が出ず、「取れない」と読める', () => {
  const view = buildPipelineView(stateRecordSnapshot('dev', { final: 'PASSED' }));
  const bar = statusBarLabel(view);
  assert.doesNotMatch(bar.tooltip, MONEY, bar.tooltip);
  assert.doesNotMatch(bar.text, MONEY);
  assert.match(bar.tooltip, /取れ/);
  assert.doesNotMatch(renderPanelHtml(view, 'n'), MONEY);
});

test('D0080-AC-11: 開発用の新しい記録（確認待ち・動いていない）でも、費用は「取れない」で $ の数が出ない', () => {
  const waiting = stateRecord('dev', { extra: { pending_review: { stage: 'design', doc: 'docs/pipeline/02_design.md', session_id: null, since: '2026-11-11T10:00:00+00:00' } } });
  const idle = stateRecord('dev', { extra: { runs: [] } });
  for (const [label, state] of [['確認待ち', waiting], ['動いていない', idle]] as const) {
    const text = JSON.stringify(state);
    assert.equal(rowOf(text).costText, '取れない', label);
    const view = buildPipelineView({ workDir: '/w', stateJson: text, stageLogs: [], artifacts: { '00_input.md': 'メモ' } });
    assert.doesNotMatch(statusBarLabel(view).tooltip, MONEY, label);
    assert.doesNotMatch(renderShell(view, emptyListFor(view)), MONEY, label);
  }
});

// ---- AC-12：schema が変な値でも落ちない ----

for (const [label, value] of ODD_SCHEMA_VALUES) {
  for (const kind of WRITER_KINDS) {
    test(`D0080-AC-12: ${kind} の記録の schema が ${label} でも、落ちずに schema が無いときと同じに読む（一覧の行・記録・図の状態・パネル。今のまま通る。守る）`, () => {
      const odd = stateRecordJson(kind, { schema: value, final: 'PASSED' });
      const base = stateRecordJson(kind, { schema: NO_SCHEMA, final: 'PASSED' });
      assert.deepEqual(rowOf(odd), rowOf(base), '一覧の行が schema の有無で変わらない');
      assert.deepEqual(parseRunRecord(odd), parseRunRecord(base));
      const view = buildPipelineView({ workDir: '/w', stateJson: odd, stageLogs: [], artifacts: { '00_input.md': 'メモ' } });
      assert.equal(view.final, 'PASSED');
      assert.doesNotThrow(() => renderShell(view, emptyListFor(view)));
    });
  }
}
