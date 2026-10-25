// 表を作る純粋な関数 buildToolsTable（domain/toolsTable.ts。D0049）：名前の決まり・同じ名前の合算・使った段・受け持ちの行と時間・並び・100 行の上限。
// 入力は「読んだあとの形」（段のログごとの calls、runs[] の要素、動いているログ、段の表示名の表、driver の有無）。ファイル・時計に触れない。
// toolsTable.ts と gantt.ts の新しい export（labelOf）は実装の段で足される。動的 import で読み、無ければ「まだ作っていない」で落とす（ファイルごと落ちて、ほかのテストまで赤にならないように）。
// 数・並び・時間の期待は、このファイルの中で別に数える（表を作る側の計算を写さない）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { performance } from 'node:perf_hooks';
import * as gantt from './gantt.ts';
import { needFunction, needModule } from '../test/needModule.ts';

type Kind = 'agent' | 'skill' | 'tool';
interface TCall {
  kind: Kind;
  name: unknown;
}
interface TLog {
  seq: number;
  stage: string;
  attempt: number | null;
  agent: string | null;
  calls: TCall[];
}
interface TRun {
  seq: number;
  stage: string;
  attempt: number | null;
  agent: string | null;
  durationSec: number;
}
interface TRunning {
  seq: number;
  stage: string;
  attempt: number | null;
  agent: string | null;
}
interface TInput {
  logs: TLog[];
  runs: TRun[];
  running: TRunning | null;
  labels: Record<string, string>;
  driver: boolean;
}
interface TRow {
  kind: Kind;
  name: string;
  count: number;
  stages: string[];
  durationSec: number | null;
}
interface TTable {
  rows: TRow[];
  kinds: number;
  total: number;
  omitted: number;
  showTime: boolean;
  notice: 'A' | 'B' | null;
}
interface ToolsTableModule {
  buildToolsTable(input: TInput): TTable;
  compareCodePoints(a: string, b: string): number;
}
const mod = (): Promise<ToolsTableModule> => needModule<ToolsTableModule>(import.meta.url, './toolsTable.ts');
const build = async (over: Partial<TInput> = {}): Promise<TTable> => (await mod()).buildToolsTable({ logs: [], runs: [], running: null, labels: {}, driver: false, ...over });

const UNSPECIFIED = '（指定なし）';
const UNREADABLE = '（読めない名前）';

const agent = (name: unknown): TCall => ({ kind: 'agent', name });
const skill = (name: unknown): TCall => ({ kind: 'skill', name });
const tool = (name: unknown): TCall => ({ kind: 'tool', name });
const times = (n: number, c: TCall): TCall[] => Array.from({ length: n }, () => c);
const log = (seq: number, stage: string, calls: TCall[], over: Partial<TLog> = {}): TLog => ({ seq, stage, attempt: null, agent: null, calls, ...over });
const run = (seq: number, stage: string, over: Partial<TRun> = {}): TRun => ({ seq, stage, attempt: null, agent: null, durationSec: 0, ...over });
/** 1 つのログの calls だけから表を作る */
const fromCalls = (calls: TCall[], over: Partial<TInput> = {}): Promise<TTable> => build({ logs: [log(1, 'survey', calls)], labels: { survey: '調査' }, ...over });
const names = (t: TTable): string[] => t.rows.map((r) => r.name);
const rowOf = (t: TTable, kind: Kind, name: string): TRow => {
  const found = t.rows.find((r) => r.kind === kind && r.name === name);
  assert.ok(found, `${kind} の ${name} の行がある：${JSON.stringify(t.rows.map((r) => [r.kind, r.name]))}`);
  return found;
};

// ---- AC-06：名前の決まり ----

const READABLE: [string, string][] = [
  ['1 文字', 'a'],
  ['ちょうど 100 文字', 'x'.repeat(100)],
  ['絵文字 100 個（コードポイントで数える）', '😀'.repeat(100)],
  ['外から来た文字（空白を含まない）', '<script>alert(1)</script>'],
];
const UNREADABLE_STRINGS: [string, string][] = [
  ['空の文字', ''],
  ['半角空白を含む', 'a b'],
  ['全角空白だけ', '　'],
  ['改行を含む', 'a\nb'],
  ['タブを含む', 'a\tb'],
  ['制御文字を含む', 'a\u0000b'],
  ['101 文字', 'x'.repeat(101)],
  ['絵文字 101 個', '😀'.repeat(101)],
];
const KINDS: [Kind, (name: unknown) => TCall][] = [
  ['agent', agent],
  ['skill', skill],
  ['tool', tool],
];
for (const [kind, make] of KINDS) {
  for (const [label, name] of READABLE) {
    test(`D0049-AC-06: ${kind} の名前が ${label} のときは、そのまま名前になる`, async () => {
      const t = await fromCalls([make(name)]);
      assert.deepEqual(t.rows.map((r) => [r.kind, r.name, r.count]), [[kind, name, 1]]);
    });
  }
  for (const [label, name] of UNREADABLE_STRINGS) {
    test(`D0049-AC-06: ${kind} の名前が ${label} のときは「（読めない名前）」にする`, async () => {
      const t = await fromCalls([make(name)]);
      assert.deepEqual(t.rows.map((r) => [r.kind, r.name, r.count]), [[kind, UNREADABLE, 1]]);
    });
  }
}
for (const [kind, make] of KINDS.slice(0, 2)) {
  for (const [label, value] of [['数 5', 5], ['null', null], ['真偽値', true], ['オブジェクト', {}], ['配列', ['a']]] as [string, unknown][]) {
    test(`D0049-AC-06: ${kind} の名前（subagent_type・skill）が ${label} のときは「（読めない名前）」にする（数・null は道具の name では起こらない）`, async () => {
      const t = await fromCalls([make(value)]);
      assert.deepEqual(t.rows.map((r) => [r.kind, r.name, r.count]), [[kind, UNREADABLE, 1]]);
    });
  }
  test(`D0049-AC-06: ${kind} の鍵そのものが無い（名前が undefined）呼び出しは「（指定なし）」にする（鍵を省いた呼び出しはあり得る）`, async () => {
    const t = await fromCalls([make(undefined)]);
    assert.deepEqual(t.rows.map((r) => [r.kind, r.name, r.count]), [[kind, UNSPECIFIED, 1]]);
  });
}

test('D0049-AC-06: 読めない名前は、種類ごとに 1 行にまとめて回数を足す（どの値でも同じ行）', async () => {
  const t = await fromCalls([agent(5), agent(null), agent(''), agent('a b'), agent('x'.repeat(101)), skill(5), tool('a\nb'), tool('a\nb')]);
  assert.deepEqual(
    t.rows.map((r) => [r.kind, r.name, r.count]),
    [
      ['agent', UNREADABLE, 5],
      ['skill', UNREADABLE, 1],
      ['tool', UNREADABLE, 2],
    ],
  );
});

test('D0049-AC-06: 「（指定なし）」と「（読めない名前）」と同じ文字の本物の名前は、代わりの文字の行とは別の行になる（まとめない）', async () => {
  const t = await fromCalls([agent(UNSPECIFIED), agent(undefined), agent(UNREADABLE), agent(5)]);
  assert.equal(t.rows.length, 4);
  assert.deepEqual(t.rows.map((r) => r.count), [1, 1, 1, 1]);
  assert.deepEqual(names(t).sort(), [UNREADABLE, UNREADABLE, UNSPECIFIED, UNSPECIFIED].sort());
});

// ---- AC-07：同じ種類・同じ名前は 1 行 ----

test('D0049-AC-07: 同じ種類・同じ名前の呼び出しは 1 行に数える（Agent 由来と Task 由来のエージェントは同じ行）', async () => {
  const t = await fromCalls([agent('a'), agent('a')]);
  assert.deepEqual(t.rows.map((r) => [r.kind, r.name, r.count]), [['agent', 'a', 2]]);
});

test('D0049-AC-07: 種類が違えば、同じ名前でも別の行（エージェント x・スキル x・道具 x で 3 行）', async () => {
  const t = await fromCalls([agent('x'), skill('x'), tool('x')]);
  assert.deepEqual(
    t.rows.map((r) => [r.kind, r.name, r.count]),
    [
      ['agent', 'x', 1],
      ['skill', 'x', 1],
      ['tool', 'x', 1],
    ],
  );
});

test('D0049-AC-07: 別々のログ（段の実行）の同じ名前の呼び出しも、1 行に足す', async () => {
  const t = await build({ logs: [log(1, 'survey', times(2, tool('Read'))), log(2, 'draw', times(3, tool('Read')))], labels: { survey: '調査', draw: '描く' } });
  assert.deepEqual(t.rows.map((r) => [r.name, r.count]), [['Read', 5]]);
});

// ---- 行の形（AC-09：内訳の項目が無い） ----

test('D0049-AC-09: 行の項目は kind・name・count・stages・durationSec の 5 つだけ（メインとサブエージェントの中の内訳の項目が無い）', async () => {
  const t = await fromCalls([tool('Read')]);
  assert.deepEqual(Object.keys(t.rows[0]!).sort(), ['count', 'durationSec', 'kind', 'name', 'stages']);
  assert.deepEqual(Object.keys(t).sort(), ['kinds', 'notice', 'omitted', 'rows', 'showTime', 'total']);
});

// ---- AC-12：使った段 ----

const SIX = (order: number[]): TLog[] => order.map((seq) => log(seq, `s${seq}`, [tool('Read')]));
const SIX_LABELS = Object.fromEntries([1, 2, 3, 4, 5, 6].map((n) => [`s${n}`, `段${n}`]));

test('D0049-AC-12: 使った段は通し番号の順に並ぶ（ログを 1・3・4・5・6・2 の順に渡しても、1〜6 の順）', async () => {
  const t = await build({ logs: SIX([1, 3, 4, 5, 6, 2]), labels: SIX_LABELS });
  assert.deepEqual(rowOf(t, 'tool', 'Read').stages, ['段1', '段2', '段3', '段4', '段5', '段6']);
  assert.equal(rowOf(t, 'tool', 'Read').count, 6);
});

test('D0049-AC-12: 同じ段の実行で何回呼んでも、使った段は 1 つ（同じ実行は 1 回だけ並べる）', async () => {
  const t = await build({ logs: [log(1, 'survey', times(100, tool('Read')))], labels: { survey: '調査' } });
  const row = rowOf(t, 'tool', 'Read');
  assert.equal(row.count, 100);
  assert.deepEqual(row.stages, ['調査']);
});

test('D0049-AC-12: 「N 回目」はログのファイル名の回に従う（runs[].attempt が 3 でも、ログが _2 なら「2 回目」）', async () => {
  const t = await build({
    logs: [log(1, 'draw', [tool('Read')], { attempt: 2 })],
    runs: [run(1, 'draw', { attempt: 3 })],
    labels: { draw: '描く' },
  });
  assert.deepEqual(rowOf(t, 'tool', 'Read').stages, ['描く 2 回目']);
});

test('D0049-AC-12: 動いているログの回もログのファイル名の回：まだログの呼び出しが無い running（attempt 2）の受け持ちの行は「描く 2 回目」', async () => {
  const t = await build({ running: { seq: 3, stage: 'draw', attempt: 2, agent: 'x' }, labels: { draw: '描く' } });
  assert.deepEqual(rowOf(t, 'agent', 'x').stages, ['描く 2 回目']);
});

test('D0049-AC-12: 動いているログ（attempt 2）が logs にもあるとき、受け持ちの行も、そのログの呼び出しの行も「描く 2 回目」', async () => {
  const t = await build({
    logs: [log(3, 'draw', [agent('y')], { attempt: 2 })],
    running: { seq: 3, stage: 'draw', attempt: 2, agent: 'x' },
    labels: { draw: '描く' },
  });
  assert.deepEqual(rowOf(t, 'agent', 'x').stages, ['描く 2 回目']);
  assert.deepEqual(rowOf(t, 'agent', 'y').stages, ['描く 2 回目']);
});

test('D0049-AC-12: 回の無い段は表示名だけ。回は 1 以上のときだけ付ける', async () => {
  const t = await build({
    logs: [log(1, 'draw', [tool('Read')]), log(2, 'draw', [tool('Read')], { attempt: 1 }), log(3, 'draw', [tool('Read')], { attempt: 0 })],
    labels: { draw: '描く' },
  });
  assert.deepEqual(rowOf(t, 'tool', 'Read').stages, ['描く', '描く 1 回目', '描く']);
});

test('D0049-AC-12: 名前の違う呼び出しは、それぞれ自分の呼んだ段だけを持つ', async () => {
  const t = await build({ logs: [log(1, 'survey', [tool('Read')]), log(2, 'draw', [tool('Grep'), tool('Read')])], labels: { survey: '調査', draw: '描く' } });
  assert.deepEqual(rowOf(t, 'tool', 'Read').stages, ['調査', '描く']);
  assert.deepEqual(rowOf(t, 'tool', 'Grep').stages, ['描く']);
});

// ---- AC-13：段の表示名は時系列と同じ元（labelOf） ----

type LabelOf = (stage: string, attempt: number | null, labels: Readonly<Record<string, string>>) => unknown;

test('D0049-AC-13: gantt.ts の labelOf は export されていて、表示名＋「 N 回目」を返す（時系列の行の label と同じ書き方）', () => {
  const labelOf = needFunction<LabelOf>(gantt, 'labelOf', 'domain/gantt.ts');
  assert.equal(labelOf('survey', null, { survey: '調査' }), '調査');
  assert.equal(labelOf('survey', 2, { survey: '調査' }), '調査 2 回目');
  assert.equal(labelOf('survey', 0, { survey: '調査' }), '調査');
  assert.equal(labelOf('survey', -1, { survey: '調査' }), '調査');
  assert.equal(labelOf('other', null, { survey: '調査' }), 'other', '表示名の無い段は、ログの名前のまま');
  assert.equal(labelOf('other', 3, {}), 'other 3 回目');
});

for (const stage of ['constructor', '__proto__', 'toString', 'hasOwnProperty', 'valueOf']) {
  test(`D0049-AC-13: labelOf は、段の名前が ${stage}（Object のプロパティ名）でも、表示名の代わりに関数を返さず、段の名前の文字そのものを返す`, () => {
    const labelOf = needFunction<LabelOf>(gantt, 'labelOf', 'domain/gantt.ts');
    const plain = labelOf(stage, null, {});
    assert.equal(typeof plain, 'string');
    assert.equal(plain, stage);
    assert.equal(labelOf(stage, 2, {}), `${stage} 2 回目`);
    assert.equal(labelOf(stage, null, Object.fromEntries([[stage, '表示名']])), '表示名', '自分の鍵に表示名があればそれ');
  });
}

test('D0049-AC-13: 表の使った段の文字は labelOf の戻りと同じ（時系列の行と同じ元）', async () => {
  const labelOf = needFunction<LabelOf>(gantt, 'labelOf', 'domain/gantt.ts');
  const labels = { survey: '調査', draw: '描く' };
  const t = await build({ logs: [log(1, 'survey', [tool('Read')]), log(2, 'draw', [tool('Read')], { attempt: 2 }), log(3, 'constructor', [tool('Read')])], labels });
  assert.deepEqual(rowOf(t, 'tool', 'Read').stages, [labelOf('survey', null, labels), labelOf('draw', 2, labels), labelOf('constructor', null, labels)]);
  assert.ok(rowOf(t, 'tool', 'Read').stages.every((s) => typeof s === 'string'));
});

// ---- AC-14：呼び出しを数えた行の時間は「—」（null）。段の時間などで代えない ----

test('D0049-AC-14: スキル・道具・SDK のエージェント呼び出しの行の durationSec は null（runs[] に durationSec があっても、段の時間で代えない）', async () => {
  const t = await build({
    logs: [log(1, 'survey', [skill('review'), tool('Read'), agent('module-reader')])],
    runs: [run(1, 'survey', { durationSec: 300 })],
    labels: { survey: '調査' },
  });
  assert.equal(t.rows.length, 3);
  assert.deepEqual(t.rows.map((r) => r.durationSec), [null, null, null]);
  assert.equal(t.showTime, false, '時間のある行が無いので列を出さない');
});

// ---- AC-15：受け持ちの行の時間 ----

const close = (actual: number | null, expected: number): boolean => actual !== null && Math.abs(actual - expected) < 1e-9;

test('D0049-AC-15: (1) 受け持ちの 3 つの実行（10.9・20・30.5 秒）の合計 61.4 秒が、その行の時間になる', async () => {
  const t = await build({
    runs: [run(1, 'survey', { agent: 'pipe-in-analyst', durationSec: 10.9 }), run(2, 'draw', { agent: 'pipe-in-analyst', durationSec: 20 }), run(3, 'verify', { agent: 'pipe-in-analyst', durationSec: 30.5 })],
    labels: { survey: '調査', draw: '描く', verify: '検証' },
  });
  const row = rowOf(t, 'agent', 'pipe-in-analyst');
  assert.equal(row.count, 3);
  assert.ok(close(row.durationSec, 61.4), `合計 61.4 秒（${row.durationSec}）`);
  assert.equal(t.showTime, true);
});

test('D0049-AC-15: (2) 負・有限でない値は 0 として足す。合計が 0 秒でも時間は 0（null ではない。画面では「0:00」）', async () => {
  const t = await build({
    runs: [run(1, 'survey', { agent: 'x', durationSec: -5 }), run(2, 'draw', { agent: 'x', durationSec: Number.NaN }), run(3, 'verify', { agent: 'x', durationSec: Number.POSITIVE_INFINITY })],
  });
  assert.equal(rowOf(t, 'agent', 'x').durationSec, 0);
  assert.equal(t.showTime, true, '時間が 0 でも「—」ではないので列を出す');
});

test('D0049-AC-15: (2b) 負の値は 0 として足す（ほかの実行の時間を打ち消さない）', async () => {
  const t = await build({ runs: [run(1, 'survey', { agent: 'x', durationSec: -100 }), run(2, 'draw', { agent: 'x', durationSec: 12 })] });
  assert.equal(rowOf(t, 'agent', 'x').durationSec, 12);
});

test('D0049-AC-15: (3) runs[] に入っていない動いている段だけの受け持ちは、行は出る（回数 1）が時間は null（画面では「—」）', async () => {
  const t = await build({ running: { seq: 1, stage: 'survey', attempt: null, agent: 'pipe-in-analyst' }, labels: { survey: '調査' } });
  const row = rowOf(t, 'agent', 'pipe-in-analyst');
  assert.equal(row.count, 1);
  assert.equal(row.durationSec, null);
  assert.deepEqual(row.stages, ['調査']);
  assert.equal(t.showTime, false);
});

test('D0049-AC-15: (4) 同じ名前の SDK のエージェント呼び出しと合算した行は、受け持ちの分の時間だけ（呼び出しの分の時間は無い）', async () => {
  const t = await build({
    logs: [log(2, 'draw', times(2, agent('x')))],
    runs: [run(1, 'survey', { agent: 'x', durationSec: 30 })],
    labels: { survey: '調査', draw: '描く' },
  });
  const row = rowOf(t, 'agent', 'x');
  assert.equal(row.count, 3);
  assert.equal(row.durationSec, 30);
});

test('D0049-AC-15: (5) 3725 秒の受け持ちの時間はそのまま 3725（画面では 1:02:05）', async () => {
  const t = await build({ runs: [run(1, 'survey', { agent: 'x', durationSec: 3725 })] });
  assert.equal(rowOf(t, 'agent', 'x').durationSec, 3725);
});

test('D0049-AC-15: (6) runs[] に入った実行と動いている実行が混ざる行は、入った分だけを足し、回数には動いている分も数える', async () => {
  const t = await build({
    runs: [run(1, 'survey', { agent: 'x', durationSec: 40 })],
    running: { seq: 2, stage: 'draw', attempt: null, agent: 'x' },
    labels: { survey: '調査', draw: '描く' },
  });
  const row = rowOf(t, 'agent', 'x');
  assert.equal(row.count, 2);
  assert.equal(row.durationSec, 40);
  assert.deepEqual(row.stages, ['調査', '描く']);
});

// ---- AC-16：時間の列は、表に出る行に時間があるときだけ ----

test('D0049-AC-16: 時間のある行が 1 つも無いと showTime は偽', async () => {
  const t = await fromCalls([tool('Read'), skill('s'), agent('a')]);
  assert.equal(t.showTime, false);
});

test('D0049-AC-16: 受け持ちの行に時間（durationSec）があれば showTime は真', async () => {
  const t = await build({ runs: [run(1, 'survey', { agent: 'x', durationSec: 5 })] });
  assert.equal(t.showTime, true);
});

/** 100 種類のエージェント（回数 2）と、時間を持つ受け持ちの 1 行 zz-last（回数 = zzCount） */
async function overflowTable(zzCount: number): Promise<TTable> {
  const many = Array.from({ length: 100 }, (_, i) => `ag-${String(i).padStart(3, '0')}`);
  const calls = many.flatMap((name) => times(2, agent(name)));
  const runs = Array.from({ length: zzCount }, (_, i) => run(10 + i, 'draw', { agent: 'zz-last', durationSec: 10 }));
  return build({ logs: [log(1, 'survey', calls)], runs, labels: { survey: '調査', draw: '描く' } });
}

test('D0049-AC-16: 時間を持つ行が 101 行目で切られる（並びの最後の 1 行）ときは、showTime は偽（表に出ない行の時間のために「—」だけの列を出さない）', async () => {
  const t = await overflowTable(1);
  assert.equal(t.kinds, 101);
  assert.equal(t.rows.length, 100);
  assert.ok(!names(t).includes('zz-last'), '時間を持つ行は切られている');
  assert.equal(t.showTime, false);
});

test('D0049-AC-16: 対照：時間を持つ行の回数を 3 にすると先頭に並び、切られず、showTime は真', async () => {
  const t = await overflowTable(3);
  assert.equal(t.kinds, 101);
  assert.equal(t.rows[0]!.name, 'zz-last');
  assert.equal(t.rows[0]!.count, 3);
  assert.equal(t.showTime, true);
});

// ---- AC-17・AC-18：受け持ちの決め方 ----

test('D0049-AC-17: 受け持ちは runs[] の agent が先。無ければ、その通し番号のログの agent（時系列と同じ決め方）', async () => {
  const t = await build({
    logs: [log(1, 'survey', [], { agent: 'from-log' }), log(2, 'draw', [], { agent: 'ignored' })],
    runs: [run(1, 'survey', { agent: null }), run(2, 'draw', { agent: 'from-run' })],
    labels: { survey: '調査', draw: '描く' },
  });
  assert.deepEqual(t.rows.map((r) => [r.kind, r.name, r.count]).sort(), [['agent', 'from-log', 1], ['agent', 'from-run', 1]]);
});

test('D0049-AC-17: runs[] に無い終わったログの agent は数えない', async () => {
  const t = await build({ logs: [log(1, 'survey', [], { agent: 'finished-not-in-runs' })], runs: [] });
  assert.deepEqual(t.rows, []);
});

test('D0049-AC-17: 動いているログ（runs[] に無い）の agent は数える。agent が無ければ行を作らない', async () => {
  const withAgent = await build({ running: { seq: 3, stage: 'draw', attempt: null, agent: 'w' }, labels: { draw: '描く' } });
  assert.deepEqual(withAgent.rows.map((r) => [r.name, r.count]), [['w', 1]]);
  const without = await build({ running: { seq: 3, stage: 'draw', attempt: null, agent: null } });
  assert.deepEqual(without.rows, []);
});

test('D0049-AC-17: 受け持ちの行の使った段は、その通し番号のログの段・回から。ログが無ければ runs[] の段・回から', async () => {
  const t = await build({
    logs: [log(1, 'draw', [], { attempt: 2, agent: null })],
    runs: [run(1, 'draw', { attempt: 5, agent: 'x' }), run(2, 'verify', { attempt: 1, agent: 'x' })],
    labels: { draw: '描く', verify: '確かめる' },
  });
  assert.deepEqual(rowOf(t, 'agent', 'x').stages, ['描く 2 回目', '確かめる 1 回目']);
});

test('D0049-AC-17: 受け持ちの行の回数は受け持った段の実行の数（runs[] の要素ごとに 1 回）', async () => {
  const t = await build({ runs: [run(1, 'survey', { agent: 'x' }), run(2, 'draw', { agent: 'x' }), run(3, 'draw', { agent: 'y' })] });
  assert.deepEqual(t.rows.map((r) => [r.name, r.count]), [['x', 2], ['y', 1]]);
});

// ---- 時系列と共有する 2 つ（gantt.ts の firstLogBySeq・ownerOf）と、同じ通し番号が重なる記録 ----

type FirstLogBySeq = (logs: readonly { seq: number; tag: string }[]) => Map<number, { seq: number; tag: string }>;
type OwnerOf = (run: { agent: string | null; seq: number }, logOf: ReadonlyMap<number, { agent: string | null }>) => string | null;

test('D0049-AC-17: gantt.ts の firstLogBySeq は export されていて、通し番号ごとに最初のログを残す（同じ通し番号が重なれば先のほう。時系列の今までの動き）', () => {
  const firstLogBySeq = needFunction<FirstLogBySeq>(gantt, 'firstLogBySeq', 'domain/gantt.ts');
  const a = { seq: 1, tag: 'a' };
  const b = { seq: 1, tag: 'b' };
  const c = { seq: 2, tag: 'c' };
  const map = firstLogBySeq([a, b, c]);
  assert.equal(map.size, 2);
  assert.equal(map.get(1), a, '同じ通し番号 1 のうち先のログ');
  assert.equal(map.get(2), c);
  assert.equal(firstLogBySeq([]).size, 0);
});

test('D0049-AC-17: gantt.ts の ownerOf は export されていて、run.agent を先に、無ければその通し番号の最初のログの agent、どちらも無ければ null（時系列と同じ決め方）', () => {
  const ownerOf = needFunction<OwnerOf>(gantt, 'ownerOf', 'domain/gantt.ts');
  const logOf = new Map([[1, { agent: 'from-log' }], [2, { agent: null }]]);
  assert.equal(ownerOf({ agent: 'from-run', seq: 1 }, logOf), 'from-run');
  assert.equal(ownerOf({ agent: null, seq: 1 }, logOf), 'from-log');
  assert.equal(ownerOf({ agent: null, seq: 2 }, logOf), null);
  assert.equal(ownerOf({ agent: null, seq: 3 }, logOf), null, 'その通し番号のログが無い');
});

test('D0049-AC-17: 同じ通し番号のログが 2 つ（01_a・01_b）あるとき、最初のログを使う：受け持ちはその agent、使った段の label も最初のログの段（SDK の呼び出しの行も）', async () => {
  const t = await build({
    logs: [log(1, 'a', [tool('Read')], { agent: 'first' }), log(1, 'b', [tool('Read')], { agent: 'second' })],
    runs: [run(1, 'a')],
    labels: { a: '甲', b: '乙' },
  });
  assert.deepEqual(t.rows.map((r) => [r.kind, r.name, r.count]), [['agent', 'first', 1], ['tool', 'Read', 2]], '2 つ目のログの agent（second）は受け持ちにならない');
  assert.deepEqual(rowOf(t, 'agent', 'first').stages, ['甲']);
  assert.deepEqual(rowOf(t, 'tool', 'Read').stages, ['甲'], '同じ通し番号は 1 つ。先に入れた label を残す');
});

test('D0049-AC-17: runs[] に同じ通し番号の要素が 2 つある（壊れた記録）と、受け持ちの回数は 2 つ数える（時系列の行も 2 つになるのと同じ）。使った段は 1 つ、時間は 2 つの合計', async () => {
  const t = await build({
    runs: [run(1, 'survey', { agent: 'x', durationSec: 10 }), run(1, 'survey', { agent: 'x', durationSec: 20 })],
    labels: { survey: '調査' },
  });
  const row = rowOf(t, 'agent', 'x');
  assert.equal(row.count, 2);
  assert.deepEqual(row.stages, ['調査']);
  assert.equal(row.durationSec, 30);
});

test('D0049-AC-18: 同じ段の実行は、runs[] とログの両方に agent があっても 1 回だけ数える（runs[] の名前で）', async () => {
  const t = await build({
    logs: [log(1, 'survey', [], { agent: 'log-name' })],
    runs: [run(1, 'survey', { agent: 'run-name', durationSec: 7 })],
    labels: { survey: '調査' },
  });
  assert.deepEqual(t.rows.map((r) => [r.kind, r.name, r.count, r.durationSec]), [['agent', 'run-name', 1, 7]]);
});

test('D0049-AC-18: runs[] とログの agent が同じ名前でも 2 回数えない', async () => {
  const t = await build({ logs: [log(1, 'survey', [], { agent: 'x' })], runs: [run(1, 'survey', { agent: 'x' })] });
  assert.deepEqual(t.rows.map((r) => [r.name, r.count]), [['x', 1]]);
});

// ---- AC-19：受け持ちと subagent_type が同じ名前なら 1 行 ----

test('D0049-AC-19: 受け持ち x（2 実行）と Agent{subagent_type:x} 3 回は 1 行：回数 5・使った段は和集合（通し番号順）・時間は受け持ちの 2 実行の分だけ', async () => {
  const t = await build({
    logs: [log(5, 'verify', times(3, agent('x')))],
    runs: [run(1, 'survey', { agent: 'x', durationSec: 10 }), run(2, 'draw', { agent: 'x', durationSec: 20 })],
    labels: { survey: '調査', draw: '描く', verify: '確かめる' },
  });
  assert.equal(t.rows.length, 1);
  const row = t.rows[0]!;
  assert.deepEqual([row.kind, row.name, row.count, row.durationSec], ['agent', 'x', 5, 30]);
  assert.deepEqual(row.stages, ['調査', '描く', '確かめる']);
});

test('D0049-AC-19: 同じ通し番号の段の実行に、受け持ちと呼び出しの両方があっても、使った段は 1 つ', async () => {
  const t = await build({
    logs: [log(1, 'survey', times(2, agent('x')))],
    runs: [run(1, 'survey', { agent: 'x', durationSec: 10 })],
    labels: { survey: '調査' },
  });
  const row = rowOf(t, 'agent', 'x');
  assert.equal(row.count, 3);
  assert.deepEqual(row.stages, ['調査']);
});

// ---- AC-21・AC-22：案内（notice） ----

test('D0049-AC-21: driver があり行が 1 つ以上あるときは notice は A、driver が無いときは null（行があっても）', async () => {
  assert.equal((await fromCalls([tool('Read')], { driver: true })).notice, 'A');
  assert.equal((await fromCalls([tool('Read')], { driver: false })).notice, null);
});

test('D0049-AC-22: driver があり行が 0 のときは notice は B、driver が無く行が 0 のときは null', async () => {
  assert.equal((await build({ driver: true })).notice, 'B');
  assert.equal((await build({ driver: false })).notice, null);
});

test('D0049-AC-21: 受け持ちの行だけでも、driver があれば notice は A（行の元は問わない）', async () => {
  const t = await build({ driver: true, runs: [run(1, 'survey', { agent: 'x' })] });
  assert.equal(t.notice, 'A');
});

// ---- AC-23：並び ----

test('D0049-AC-23: 種類の順（エージェント → スキル → 道具）、同じ種類の中は回数が多い順、同じ回数は名前の順', async () => {
  const t = await fromCalls([
    tool('Read'),
    tool('Grep'),
    tool('Grep'),
    tool('Glob'),
    tool('Glob'),
    tool('Glob'),
    skill('s2'),
    skill('s1'),
    skill('s1'),
    agent('b'),
    agent('a'),
    agent('c'),
    agent('c'),
    agent('c'),
  ]);
  assert.deepEqual(
    t.rows.map((r) => `${r.kind}:${r.name}:${r.count}`),
    ['agent:c:3', 'agent:a:1', 'agent:b:1', 'skill:s1:2', 'skill:s2:1', 'tool:Glob:3', 'tool:Grep:2', 'tool:Read:1'],
  );
});

test('D0049-AC-23: 名前の順はコードポイントの順（Ａ（U+FF21）と 😀（U+1F600）は UTF-16 の順と逆。Z < a < Ａ < 😀）', async () => {
  const t = await fromCalls([tool('😀'), tool('Ａ'), tool('a'), tool('Z')]);
  assert.deepEqual(names(t), ['Z', 'a', 'Ａ', '😀']);
  // UTF-16 の順（JavaScript の既定の比べ方）は 😀 が Ａ より前になる。これと食い違う組で、コードポイントの順を固定している
  assert.deepEqual(['Ａ', '😀'].sort(), ['😀', 'Ａ'], '前提：既定の比べ方は逆になる');
});

test('D0049-AC-23: compareCodePoints はコードポイントの順（Ａ < 😀。UTF-16 の順ではない）で、同じ文字は 0', async () => {
  const { compareCodePoints } = await mod();
  assert.ok(compareCodePoints('Ａ', '😀') < 0);
  assert.ok(compareCodePoints('😀', 'Ａ') > 0);
  assert.equal(compareCodePoints('abc', 'abc'), 0);
  assert.ok(compareCodePoints('a', 'ab') < 0);
  assert.ok(compareCodePoints('Z', 'a') < 0);
});

test('D0049-AC-23: 同じ入力の順を入れ替えても（ログ・runs[]・呼び出しの順）、同じ並びになる', async () => {
  const logs = [log(1, 'survey', [tool('Read'), tool('Grep'), skill('s'), agent('a'), agent('b')]), log(2, 'draw', [tool('Read'), tool('Ａ'), tool('😀'), agent('a')])];
  const runs = [run(3, 'verify', { agent: 'b' }), run(4, 'verify', { agent: 'c' })];
  const labels = { survey: '調査', draw: '描く', verify: '確かめる' };
  const base = await build({ logs, runs, labels });
  const shuffled = await build({
    logs: [...logs].reverse().map((l) => ({ ...l, calls: [...l.calls].reverse() })),
    runs: [...runs].reverse(),
    labels,
  });
  assert.deepEqual(shuffled.rows, base.rows);
  assert.equal(base.rows.length, 8, '道具 4（Read・Grep・Ａ・😀）・スキル 1・エージェント 3（a・b・c）');
});

test('D0049-AC-23: 名前が同じで状態が違う行は、読める名前 → 指定なし → 読めない名前の順に並ぶ（最後のキー）。ログを逆順に渡しても同じ', async () => {
  const labels = { a: '甲', b: '乙', c: '丙', d: '丁' };
  // 4 つのログに 1 つずつ。使った段の文字で、どの行かを見分ける。入力の順は、並びの最後のキーが無いと別の並びになる順（読めない → 読める → 指定なし → 読める）
  const logs = [log(1, 'a', [agent(5)]), log(2, 'b', [agent(UNREADABLE)]), log(3, 'c', [agent(undefined)]), log(4, 'd', [agent(UNSPECIFIED)])];
  const order = async (input: TLog[]): Promise<string[]> => (await build({ logs: input, labels })).rows.map((r) => r.stages.join());
  // 名前は 指定なし < 読めない名前（コードポイントの順）。同じ名前の中は 読める名前 → 代わりの文字
  const expected = ['丁', '丙', '乙', '甲'];
  assert.deepEqual(names(await build({ logs, labels })), [UNSPECIFIED, UNSPECIFIED, UNREADABLE, UNREADABLE], '前提：同じ名前の行が 2 つずつ');
  assert.deepEqual(await order(logs), expected);
  assert.deepEqual(await order([...logs].reverse()), expected);
});

// ---- AC-24：要約の元の数 ----

test('D0049-AC-24: kinds は行を省く前の種類の数、total は回数の合計（150 種類を回数 2 ずつ：150 と 300。表の行は 100 で、回数の合計は 200）', async () => {
  const calls = Array.from({ length: 150 }, (_, i) => times(2, tool(`t${String(i).padStart(3, '0')}`))).flat();
  const t = await fromCalls(calls);
  assert.equal(t.kinds, 150);
  assert.equal(t.total, 300);
  assert.equal(t.rows.length, 100);
  assert.equal(t.omitted, 50);
  assert.equal(t.rows.reduce((s, r) => s + r.count, 0), 200);
});

// ---- AC-25：100 行の上限 ----

for (const [kinds, omitted] of [[100, 0], [101, 1], [120, 20]] as const) {
  test(`D0049-AC-25: ${kinds} 種類のとき、行は ${Math.min(kinds, 100)}・省いた数は ${omitted}（省くのは並びの後ろの行）`, async () => {
    const calls = Array.from({ length: kinds }, (_, i) => tool(`t${String(i).padStart(3, '0')}`));
    const t = await fromCalls(calls);
    assert.equal(t.rows.length, Math.min(kinds, 100));
    assert.equal(t.omitted, omitted);
    assert.equal(t.kinds, kinds);
    if (omitted > 0) assert.deepEqual(names(t), calls.slice(0, 100).map((c) => String(c.name)), '並びの先頭の 100 行が残り、後ろが省かれる');
  });
}

// ---- AC-44：Object の組み込みの名前 ----

const PROTO = ['__proto__', 'constructor', 'toString'];
for (const [kind, make] of KINDS) {
  test(`D0049-AC-44: ${kind} の名前が __proto__・constructor・toString でも、それぞれ 1 行（回数 1）で、ほかの行の回数を変えない`, async () => {
    const t = await fromCalls([...PROTO.map((n) => make(n)), tool('Read'), tool('Read')]);
    for (const name of PROTO) assert.equal(rowOf(t, kind, name).count, 1, name);
    assert.equal(rowOf(t, 'tool', 'Read').count, 2);
    assert.equal(t.kinds, 4, '組み込みの名前 3 つ＋Read');
  });
}
test('D0049-AC-44: 組み込みの名前を何度呼んでも、その名前の回数だけが増える（Object.prototype が汚れない）', async () => {
  const before = Object.getOwnPropertyNames(Object.prototype).sort();
  const t = await fromCalls([tool('__proto__'), tool('__proto__'), tool('constructor'), agent('toString'), skill('__proto__')]);
  assert.equal(rowOf(t, 'tool', '__proto__').count, 2);
  assert.equal(rowOf(t, 'tool', 'constructor').count, 1);
  assert.equal(rowOf(t, 'agent', 'toString').count, 1);
  assert.equal(rowOf(t, 'skill', '__proto__').count, 1);
  assert.deepEqual(Object.getOwnPropertyNames(Object.prototype).sort(), before);
  assert.equal(({} as Record<string, unknown>).count, undefined);
  assert.equal(({} as Record<string, unknown>).stages, undefined);
});

// ---- AC-45：呼び出しの数を 2 倍にしたときの時間の伸び（表を作る部品だけを測る） ----
// 全体（parse → 表 → renderViewBody）の比は、既存の「出力」の欄の組み立てと GC が支配して揺れる（正しい実装でも 2.5 倍を超えることがある）ので、
// 新しく足した表を作る部品だけを測る。名前も呼び出しに比例して増やす（呼び出し 10 倍 = 名前 1 万種類の割合）ので、
// 呼び出しごとに行を探す・行の配列を作り直すような、名前の数に対して 2 乗の作りも見つかる。入力は測る前に作り、小さい側と大きい側を交互に測って、最小値で比べる。

/** calls 回の道具の呼び出し（名前は calls の 10 分の 1 種類。t0, t1, …）を持つ 1 つのログの入力 */
const loadInput = (calls: number): TInput => ({
  logs: [log(1, 'survey', Array.from({ length: calls }, (_, i) => tool(`t${i % Math.floor(calls / 10)}`)))],
  runs: [],
  running: null,
  labels: { survey: '調査' },
  driver: false,
});

test('D0049-AC-45: 表を作る部品は、呼び出しの数を 2 倍（10 万 → 20 万。名前も 1 万 → 2 万種類）にしたときの時間の伸びが 2.5 倍以内（ならし 1 回のあと、小さい側・大きい側を交互に 7 回ずつ測った最小値。小さい側は 50ms を床にする）', async () => {
  const { buildToolsTable } = await mod();
  const small = loadInput(100_000);
  const large = loadInput(200_000);
  const table = buildToolsTable(large);
  assert.equal(table.kinds, 20_000, '先に表ができていることを確かめる（検査が空振りでない）');
  assert.equal(table.total, 200_000);
  assert.equal(table.rows.length, 100);
  buildToolsTable(small);
  const time = (input: TInput): number => {
    const started = performance.now();
    buildToolsTable(input);
    return performance.now() - started;
  };
  let smallMs = Number.POSITIVE_INFINITY;
  let largeMs = Number.POSITIVE_INFINITY;
  for (let i = 0; i < 7; i++) {
    smallMs = Math.min(smallMs, time(small));
    largeMs = Math.min(largeMs, time(large));
  }
  assert.ok(largeMs <= 2.5 * Math.max(smallMs, 50), `10 万 ${Math.round(smallMs)}ms → 20 万 ${Math.round(largeMs)}ms`);
});

// ---- 空の入力 ----

test('D0049-AC-26: 呼び出しも受け持ちも無い入力は、行 0・種類 0・回数 0・showTime 偽（driver が無ければ notice も null）', async () => {
  const t = await build();
  assert.deepEqual(t, { rows: [], kinds: 0, total: 0, omitted: 0, showTime: false, notice: null });
});
