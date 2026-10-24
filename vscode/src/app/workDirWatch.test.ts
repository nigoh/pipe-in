// work_dir の見張りの判断・手順・持ち方（D0034）：有無の判断 decideWatch、読み直しの判断 finishStep、見張りを持つ部品 createWatchHolder、
// 手順 createWorkDirChecker。判断は vscode を知らない純粋な部品で、時計も使わない。ここでは偽の口（確かめ・見張りを作る・読み直し）と
// 偽のタイマーで、呼ばれた順と回数を確かめる。本物の時間は使わない（sleep しない）。リポジトリの実物にも書かない。
// まだ無い部品（app/workDirWatch.ts）は、呼んだところで落ちるように、テストの中で読み込む（ファイルごと読めずに全部が落ちる形にしない）。
// 型は、この中で形を書いて受ける（部品の型に合わせた型検査は、部品ができてから実装の段が見る）。
// 補助（fakeTimers など）は、承認された別のテストの中の関数で、そちらを書き換えないので、同じ作りでこの中に持つ。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createGeneration, createPoller } from './refreshPolicy.ts';
import type { Generation } from './refreshPolicy.ts';
import { findClockOrNode, withoutComments } from '../test/sourceText.ts';

type Presence = 'present' | 'absent' | 'unknown';
type WatchAction = 'attach' | 'detach' | 'keep';
interface WatchHandle {
  onDidCreate(listener: () => void): unknown;
  onDidChange(listener: () => void): unknown;
  onDidDelete(listener: () => void): unknown;
  dispose(): void;
}
interface WatchHolder {
  readonly active: boolean;
  attach(dir: string): boolean;
  detach(): void;
}
interface WorkDirChecker {
  check(dir: string): Promise<void>;
  reset(): void;
}
interface FinishInput {
  action: WatchAction;
  attached: boolean;
  first: boolean;
  followUp: boolean;
}
interface WorkDirWatchModule {
  decideWatch(watching: boolean, presence: Presence): WatchAction;
  finishStep(input: FinishInput): { read: boolean; followUp: boolean };
  createWatchHolder(options: { create: (dir: string) => WatchHandle; onEvent: () => void }): WatchHolder;
  createWorkDirChecker(options: { generation: Generation; holder: WatchHolder; probe: (dir: string) => Promise<Presence>; reload: () => Promise<void> }): WorkDirChecker;
}
const loadModule = async (): Promise<WorkDirWatchModule> => (await import('./workDirWatch.ts')) as unknown as WorkDirWatchModule;

const KEEP_NOTE = '（今のまま通る。守る）';
const settle = () => new Promise<void>((resolve) => setImmediate(resolve));
/** 条件が満たされるまで、非同期の続きを流す（時間は使わない） */
async function until(condition: () => boolean): Promise<void> {
  for (let i = 0; i < 200; i++) {
    if (condition()) return;
    await settle();
  }
  assert.fail('待っていることが起きない（偽の口が呼ばれない）');
}

// ---- 偽の口 ----------------------------------------------------------------------------

/** 確かめの台本の 1 手：結果、または probe が例外を投げる */
type Step = Presence | 'throw';
type EventKind = 'create' | 'change' | 'delete';

interface FakeOptions {
  /** work_dir の絶対パス（既定はワークスペースの中） */
  dir?: string;
  /** n 回目（1 から）の create が例外を投げる */
  createFails?: (n: number) => boolean;
  /** n 個目（1 から）の見張りで、知らせの登録（onDidChange）が例外を投げる */
  registerFails?: (n: number) => boolean;
  /** n 個目（1 から）の見張りの dispose が例外を投げる */
  disposeFails?: (n: number) => boolean;
  /** n 回目（1 から）の reload が例外を投げる */
  reloadFails?: (n: number) => boolean;
  /** probe を手で開ける門にする（台本の代わり。全部の probe） */
  gate?: boolean;
  /** n 回目（1 から）の probe だけを手で開ける門にする（ほかの probe は台本どおり） */
  gateAt?: (n: number) => boolean;
  /** n 回目（1 から）の reload を、手で開けるまで終わらせない（読み直しが長引く場面。開ける関数は reloadGates に溜まる） */
  reloadHeld?: (n: number) => boolean;
}

interface FakeWatch extends WatchHandle {
  readonly n: number;
  /** dispose が呼ばれた回数 */
  disposed: number;
  fire(kind: EventKind): void;
}

/** 偽の見張り。登録された知らせを溜め、fire で呼ぶ。dispose の呼び出しを共通の log に書く。 */
function fakeWatch(n: number, log: string[], options: FakeOptions): FakeWatch {
  const listeners: Record<EventKind, (() => void)[]> = { create: [], change: [], delete: [] };
  const watch: FakeWatch = {
    n,
    disposed: 0,
    onDidCreate(listener) {
      listeners.create.push(listener);
      return undefined;
    },
    onDidChange(listener) {
      if (options.registerFails?.(n)) throw new Error('知らせの登録に失敗');
      listeners.change.push(listener);
      return undefined;
    },
    onDidDelete(listener) {
      listeners.delete.push(listener);
      return undefined;
    },
    dispose() {
      watch.disposed++;
      log.push(`dispose ${n}`);
      if (options.disposeFails?.(n)) throw new Error('片付けに失敗');
    },
    fire(kind) {
      for (const listener of listeners[kind]) listener();
    },
  };
  return watch;
}

/** 本物の部品を組み、口は偽物にした世界。log に probe・create n・dispose n・reload が呼ばれた順に残る。 */
async function build(options: FakeOptions = {}) {
  const mod = await loadModule();
  const dir = options.dir ?? '/ws/docs/pipeline';
  const log: string[] = [];
  const handles: FakeWatch[] = [];
  const probedDirs: string[] = [];
  const createdDirs: string[] = [];
  const gates: ((presence: Presence) => void)[] = [];
  const reloadGates: (() => void)[] = [];
  const counts = { probe: 0, create: 0, reload: 0, events: 0 };
  let next: Step = 'unknown';

  const generation = createGeneration();
  const holder = mod.createWatchHolder({
    create: (target) => {
      counts.create++;
      log.push(`create ${counts.create}`);
      createdDirs.push(target);
      if (options.createFails?.(counts.create)) throw new Error('見張りを作れない');
      const watch = fakeWatch(counts.create, log, options);
      handles.push(watch);
      return watch;
    },
    onEvent: () => {
      counts.events++;
    },
  });
  const checker = mod.createWorkDirChecker({
    generation,
    holder,
    probe: async (target) => {
      counts.probe++;
      log.push('probe');
      probedDirs.push(target);
      if (options.gate || options.gateAt?.(counts.probe)) return new Promise<Presence>((resolve) => gates.push(resolve));
      if (next === 'throw') throw new Error('確かめが例外で終わった');
      return next;
    },
    reload: async () => {
      counts.reload++;
      const nth = counts.reload;
      log.push('reload');
      if (options.reloadHeld?.(nth)) await new Promise<void>((resolve) => reloadGates.push(() => resolve()));
      if (options.reloadFails?.(nth)) throw new Error('読み直しに失敗');
    },
  });
  const disposes = (): number => log.filter((line) => line.startsWith('dispose')).length;
  return {
    dir,
    log,
    handles,
    probedDirs,
    createdDirs,
    gates,
    reloadGates,
    counts,
    generation,
    holder,
    checker,
    disposes,
    /** 生きている（片付けていない）見張りの数 */
    live: (): number => handles.filter((h) => h.disposed === 0).length,
    /** 台本の 1 手で確かめを 1 回して、その間に増えた log を返す */
    async run(step: Step): Promise<string[]> {
      next = step;
      const from = log.length;
      await checker.check(dir);
      return log.slice(from);
    },
    /** 台本の 1 手で確かめを始めるだけで、終わりを待たない（読み直しや確かめの途中に、次の手を差し込む場面用）。probe が呼ばれるまで、次の手は進めない */
    begin(step: Step): Promise<void> {
      next = step;
      return checker.check(dir);
    },
  };
}

/** 台本を順に流し、1 手ごとの（読み直しの合計・見張っているか）を返す */
async function runScript(steps: readonly Step[], options: FakeOptions = {}) {
  const w = await build(options);
  const reloads: number[] = [];
  const active: boolean[] = [];
  for (const step of steps) {
    await w.run(step);
    reloads.push(w.counts.reload);
    active.push(w.holder.active);
  }
  return { w, reloads, active };
}

// ---- AC-07：見張る・外す・そのまま（decideWatch）----

const DECIDE_CASES: readonly (readonly [boolean, Presence, WatchAction])[] = [
  [false, 'present', 'attach'],
  [true, 'absent', 'detach'],
  [true, 'present', 'keep'],
  [false, 'absent', 'keep'],
  [false, 'unknown', 'keep'],
  [true, 'unknown', 'keep'],
];

for (const [watching, presence, expected] of DECIDE_CASES) {
  test(`D0034-AC-07: decideWatch（見張っている=${watching}・確かめの結果=${presence}）は ${expected}（同じ入力は同じ答え）`, async () => {
    const { decideWatch } = await loadModule();
    assert.equal(decideWatch(watching, presence), expected);
    assert.equal(decideWatch(watching, presence), expected);
  });
}

test('D0034-AC-07: 「分からない」のときは何も触らない：見張りを外さず、見張っているままで、読み直しは最初の 1 回だけ（有る → 分からない → 確かめが例外 → 分からない）', async () => {
  const { w, reloads, active } = await runScript(['present', 'unknown', 'throw', 'unknown']);
  assert.equal(w.disposes(), 0, '外していない');
  assert.deepEqual(active, [true, true, true, true]);
  assert.equal(w.counts.create, 1);
  assert.deepEqual(reloads, [1, 1, 1, 1]);
});

test('D0034-AC-07: 「分からない」のときは何も触らない：見張りを張らず、読み直しは最初の 1 回だけ（無い → 分からない）', async () => {
  const { w, reloads, active } = await runScript(['absent', 'unknown']);
  assert.equal(w.counts.create, 0);
  assert.deepEqual(active, [false, false]);
  assert.deepEqual(reloads, [1, 1]);
});

// ---- AC-08：手順の順番 ----

test('D0034-AC-08: 張るときは 確かめる → 見張りを作る → 読み直す、外すときは 確かめる → 外す → 読み直す（無い → 有る → 無い）', async () => {
  const w = await build();
  await w.run('absent');
  assert.deepEqual(await w.run('present'), ['probe', 'create 1', 'reload'], '張る：張ってから読む（張る前に起きた変化を読み直しで拾う）');
  assert.deepEqual(await w.run('absent'), ['probe', 'dispose 1', 'reload'], '外す：外してから読む');
});

test('D0034-AC-08: 見張りを持つ部品に attach を 2 回続けると、古い見張りを片付けてから新しく作る（create 1 → dispose 1 → create 2）', async () => {
  const w = await build();
  assert.equal(w.holder.attach(w.dir), true);
  assert.equal(w.holder.attach(w.dir), true);
  assert.deepEqual(w.log, ['create 1', 'dispose 1', 'create 2']);
});

// ---- AC-09：最初の確かめは、結果が何でも読み直しがちょうど 1 回（読む主は手順の部品。設計で人が決めた読み替え）----

const FIRST_CHECKS: readonly (readonly [string, Step, FakeOptions, readonly string[], boolean])[] = [
  ['有る', 'present', {}, ['probe', 'create 1', 'reload'], true],
  ['無い', 'absent', {}, ['probe', 'reload'], false],
  ['分からない', 'unknown', {}, ['probe', 'reload'], false],
  ['確かめが例外', 'throw', {}, ['probe', 'reload'], false],
  ['有る・見張りを作るのが例外', 'present', { createFails: () => true }, ['probe', 'create 1', 'reload'], false],
];

for (const [label, step, options, expectedLog, active] of FIRST_CHECKS) {
  test(`D0034-AC-09: 最初の確かめが「${label}」のとき、読み直しはちょうど 1 回（呼ぶ順：${expectedLog.join(' → ')}）。例外は外に出ない`, async () => {
    const w = await build(options);
    assert.deepEqual(await w.run(step), [...expectedLog]);
    assert.equal(w.counts.reload, 1);
    assert.equal(w.disposes(), 0);
    assert.equal(w.holder.active, active);
  });
}

// ---- AC-10：2 回目以降の確かめで「そのまま」なら読み直さない ----

const RELOAD_SCRIPTS: readonly (readonly [string, readonly Step[], readonly number[]])[] = [
  ['無い、無い、無い', ['absent', 'absent', 'absent'], [1, 1, 1]],
  ['有る、有る、有る', ['present', 'present', 'present'], [1, 1, 1]],
  ['無い、有る、有る、有る（張るで 1、追い読みで 1、そのあとは 0）', ['absent', 'present', 'present', 'present'], [1, 2, 3, 3]],
  ['有る、無い、無い（外すで 1、そのあとは 0）', ['present', 'absent', 'absent'], [1, 2, 2]],
];

for (const [label, steps, expected] of RELOAD_SCRIPTS) {
  test(`D0034-AC-10: 確かめの列「${label}」の、読み直しの合計は ${expected.join('・')}`, async () => {
    const { reloads } = await runScript(steps);
    assert.deepEqual(reloads, [...expected]);
  });
}

// ---- AC-11：追い読み（張った直後の取りこぼしを拾う、もう 1 回の読み直し）----

/** 状態の移り変わりの表（decideWatch の答えと finishStep の規則を合わせたもの。workDirWatch.ts の説明）の行：[行, 見張っている, 結果, 張れたか, 最初, 追い読みの番, 動き, 読み直し, 次の追い読みの番] */
const FINISH_ROWS: readonly (readonly [number, boolean, Presence, boolean, boolean, boolean, WatchAction, boolean, boolean])[] = [
  [1, false, 'present', true, true, false, 'attach', true, false],
  [2, false, 'present', false, true, false, 'attach', true, false],
  [3, false, 'absent', false, true, false, 'keep', true, false],
  [4, false, 'unknown', false, true, false, 'keep', true, false],
  [5, false, 'present', true, false, false, 'attach', true, true],
  [6, false, 'present', false, false, false, 'attach', false, false],
  [7, false, 'absent', false, false, false, 'keep', false, false],
  [8, false, 'unknown', false, false, false, 'keep', false, false],
  [9, true, 'present', false, false, false, 'keep', false, false],
  [10, true, 'present', false, false, true, 'keep', true, false],
  [11, true, 'absent', false, false, false, 'detach', true, false],
  [12, true, 'absent', false, false, true, 'detach', true, false],
  [13, true, 'unknown', false, false, false, 'keep', false, false],
  [14, true, 'unknown', false, false, true, 'keep', true, false],
];

for (const [row, watching, presence, attached, first, followUp, action, read, nextFollowUp] of FINISH_ROWS) {
  test(`D0034-AC-11: 移り変わりの表の行 ${row}（見張っている=${watching}・${presence}・張れた=${attached}・最初=${first}・追い読みの番=${followUp}）は 動き=${action}・読み直し=${read}・次の追い読みの番=${nextFollowUp}`, async () => {
    const { decideWatch, finishStep } = await loadModule();
    const decided = decideWatch(watching, presence);
    assert.equal(decided, action);
    assert.deepEqual(finishStep({ action: decided, attached, first, followUp }), { read, followUp: nextFollowUp });
  });
}

test('D0034-AC-11: finishStep は全部の組（動き 3 × 張れた 2 × 最初 2 × 追い読みの番 2）に式どおりの答えを返し、起こらない組でも例外にならない', async () => {
  const { finishStep } = await loadModule();
  for (const action of ['attach', 'detach', 'keep'] as const) {
    for (const attached of [false, true]) {
      for (const first of [false, true]) {
        for (const followUp of [false, true]) {
          const expected = {
            read: first || (action === 'attach' && attached) || action === 'detach' || followUp,
            followUp: action === 'attach' && attached && !first,
          };
          assert.deepEqual(finishStep({ action, attached, first, followUp }), expected, JSON.stringify({ action, attached, first, followUp }));
        }
      }
    }
  }
});

test('D0034-AC-11: finishStep は純粋：同じ入力に同じ答えを返し、渡した入力を書き換えない', async () => {
  const { finishStep } = await loadModule();
  const input: FinishInput = { action: 'attach', attached: true, first: false, followUp: false };
  const frozen = Object.freeze({ ...input });
  assert.deepEqual(finishStep(frozen), finishStep({ ...input }));
  assert.deepEqual(input, { action: 'attach', attached: true, first: false, followUp: false });
});

const FOLLOW_UP_SCRIPTS: readonly (readonly [string, readonly Step[], FakeOptions, readonly number[], readonly boolean[]])[] = [
  ['無い（最初）、有る、分からない、分からない', ['absent', 'present', 'unknown', 'unknown'], {}, [1, 2, 3, 3], [false, true, true, true]],
  ['無い（最初）、有る、確かめが例外、有る', ['absent', 'present', 'throw', 'present'], {}, [1, 2, 3, 3], [false, true, true, true]],
  ['無い（最初）、有る、無い、有る、有る（外すは追い読みを兼ねる）', ['absent', 'present', 'absent', 'present', 'present'], {}, [1, 2, 3, 4, 5], [false, true, false, true, true]],
  ['有る（最初）、有る、有る（最初に張ったときは追い読みをしない）', ['present', 'present', 'present'], {}, [1, 1, 1], [true, true, true]],
  // 最初の確かめが「張らずに終わった」3 通りのあと：最初の旗は落ちて（移り変わりの表の行 2・4 → 行 5）、次に張れた確かめが追い読みの番を立てる
  ['有る・見張りを作るのが例外（最初）、有る、有る', ['present', 'present', 'present'], { createFails: (n) => n === 1 }, [1, 2, 3], [false, true, true]],
  ['分からない（最初）、有る、有る', ['unknown', 'present', 'present'], {}, [1, 2, 3], [false, true, true]],
  ['確かめが例外（最初）、有る、有る', ['throw', 'present', 'present'], {}, [1, 2, 3], [false, true, true]],
];

for (const [label, steps, options, expectedReloads, expectedActive] of FOLLOW_UP_SCRIPTS) {
  test(`D0034-AC-11: 追い読みは張ったあとの最初の確かめで 1 回だけ：「${label}」→ 読み直しの合計 ${expectedReloads.join('・')}`, async () => {
    const { reloads, active } = await runScript(steps, options);
    assert.deepEqual(reloads, [...expectedReloads]);
    assert.deepEqual(active, [...expectedActive], '見張っているか（holder.active）');
  });
}

// ---- AC-12：確かめ用の世代（古い確かめの結果を捨てる）----

test('D0034-AC-12: 確かめの途中で世代が進んだら（retarget など）、結果が「有る」でも張らず・読み直さない', async () => {
  const w = await build({ gate: true });
  const pending = w.checker.check(w.dir);
  await until(() => w.gates.length === 1);
  w.generation.next();
  w.gates[0]!('present');
  await pending;
  assert.equal(w.counts.create, 0);
  assert.equal(w.counts.reload, 0);
  assert.equal(w.holder.active, false);
});

test('D0034-AC-12: 確かめの途中で世代が進んだら、見張っているときの結果が「無い」でも外さず・読み直さない', async () => {
  const w = await build({ gate: true });
  const first = w.checker.check(w.dir);
  await until(() => w.gates.length === 1);
  w.gates[0]!('present');
  await first;
  assert.deepEqual([w.counts.create, w.counts.reload, w.holder.active], [1, 1, true]);

  const second = w.checker.check(w.dir);
  await until(() => w.gates.length === 2);
  w.generation.next();
  w.gates[1]!('absent');
  await second;
  assert.equal(w.disposes(), 0, '外していない');
  assert.equal(w.holder.active, true);
  assert.equal(w.counts.reload, 1, '読み直しも増えない');
});

test('D0034-AC-12: 2 つ目の確かめが先に終わったら、あとで終わる 1 つ目の結果は捨てる（外さず・読み直さない）', async () => {
  const w = await build({ gate: true });
  const a = w.checker.check(w.dir);
  await until(() => w.gates.length === 1);
  const b = w.checker.check(w.dir);
  await until(() => w.gates.length === 2);
  w.gates[1]!('present');
  await b;
  assert.deepEqual([w.counts.create, w.counts.reload, w.holder.active], [1, 1, true]);
  w.gates[0]!('absent');
  await a;
  assert.equal(w.disposes(), 0, '1 つ目の「無い」で外さない');
  assert.equal(w.holder.active, true);
  assert.equal(w.counts.reload, 1);
});

test('D0034-AC-12: 捨てた確かめは状態に触れない：そのあとの確かめは「最初の確かめ」のままで、読み直しが失われない', async () => {
  const w = await build({ gate: true });
  const discarded = w.checker.check(w.dir);
  await until(() => w.gates.length === 1);
  w.generation.next();
  w.gates[0]!('present');
  await discarded;
  assert.deepEqual([w.counts.create, w.counts.reload], [0, 0]);

  const next = w.checker.check(w.dir);
  await until(() => w.gates.length === 2);
  w.gates[1]!('absent');
  await next;
  assert.equal(w.counts.reload, 1, '最初の確かめの読み直しが 1 回ある');
});

test('D0034-AC-12: 捨てた確かめは追い読みの番も消さない：（無い（最初）、有る）で追い読みの番が立ったあと、世代を進めて捨てた確かめを挟んでも、次の確かめ（有る）が追い読みを 1 回する（合計 3）', async () => {
  const w = await build({ gateAt: (n) => n === 3 });
  await w.run('absent');
  await w.run('present');
  assert.deepEqual([w.counts.create, w.counts.reload, w.holder.active], [1, 2, true]);

  const discarded = w.begin('present');
  await until(() => w.gates.length === 1);
  w.generation.next();
  w.gates[0]!('present');
  await discarded;
  assert.equal(w.counts.reload, 2, '捨てた確かめは読み直さない');

  await w.run('present');
  assert.equal(w.counts.reload, 3, '追い読みの番が消えていないので、次の確かめが追い読みをする');
  await w.run('present');
  assert.equal(w.counts.reload, 3, '追い読みは 1 回だけ');
});

// ---- AC-13：例外を外に出さず、次の確かめは続く ----

test('D0034-AC-13: 確かめが例外でも、手順は例外を出さず、次の確かめでは「有る」を見つけて張り直す', async () => {
  const w = await build();
  await w.run('absent');
  await w.run('throw');
  assert.equal(w.counts.reload, 1, '「分からない」と同じ：読み直さない');
  await w.run('present');
  assert.deepEqual([w.counts.create, w.counts.reload, w.holder.active], [1, 2, true]);
});

test('D0034-AC-13: 見張りを作るのが 1 回目だけ例外でも、手順は例外を出さず、読み直さず、次の確かめで直って張る', async () => {
  const w = await build({ createFails: (n) => n === 1 });
  await w.run('absent');
  assert.deepEqual(await w.run('present'), ['probe', 'create 1'], '1 回目：作れない。読み直さない');
  assert.deepEqual([w.holder.active, w.counts.reload], [false, 1]);
  assert.deepEqual(await w.run('present'), ['probe', 'create 2', 'reload'], '2 回目：張れて、読み直す');
  assert.deepEqual([w.holder.active, w.counts.reload], [true, 2]);
});

test('D0034-AC-13: 読み直しが例外でも、手順は例外を出さず、見張りは持ったまま、次の確かめは続く（追い読みの番も消えない）', async () => {
  const w = await build({ reloadFails: (n) => n === 2 });
  await w.run('absent');
  await w.run('present');
  assert.deepEqual([w.counts.create, w.counts.reload, w.holder.active], [1, 2, true]);
  await w.run('present');
  assert.equal(w.counts.reload, 3, '張ったあとの次の確かめで、追い読みの読み直しをする');
  await w.run('present');
  assert.equal(w.counts.reload, 3, 'その次は読まない');
});

test('D0034-AC-13: 見張りを作ったあとの知らせの登録が例外なら、作りかけを片付けて「見張っていない」のまま。持ち越さず、次の確かめでまた試す', async () => {
  const w = await build({ registerFails: (n) => n === 1 });
  await w.run('absent');
  await w.run('present');
  assert.equal(w.holder.active, false);
  assert.equal(w.live(), 0, '作りかけを片付けた（見張りは 0 個）');
  assert.equal(w.counts.reload, 1, '読み直さない');
  await w.run('present');
  assert.deepEqual([w.holder.active, w.live(), w.counts.reload], [true, 1, 2]);
});

test('D0034-AC-13: 見張りの片付けが例外でも、手順は例外を出さず、見張りは持ち越さず、読み直しはする。次の確かめで張り直せる', async () => {
  const w = await build({ disposeFails: (n) => n === 1 });
  await w.run('present');
  await w.run('absent');
  assert.equal(w.holder.active, false);
  assert.equal(w.counts.reload, 2, '外すときの読み直しはする');
  await w.run('present');
  assert.deepEqual([w.holder.active, w.counts.create], [true, 2]);
});

// ---- 状態（最初か・追い読みの番か）は、読み直しを待つ前に更新する（createWorkDirChecker の説明）----
// 読み直しが長引いても、次の確かめや reset() が前の状態を見ない。更新を読み直しのあとに回すと、下の 3 つが落ちる。
// 読み直しの偽物 reload を reloadHeld で手に持ち、終わらない間に次の手を差し込む。

test('D0034-AC-09: 最初の確かめの読み直しが終わらないうちに次の確かめ（有る）が来ても、その確かめは「最初」でなく、読み直さない（合計 1 回のまま）', async () => {
  const w = await build({ reloadHeld: (n) => n === 1 });
  const first = w.begin('present');
  await until(() => w.reloadGates.length === 1);
  assert.deepEqual([w.counts.create, w.counts.reload, w.holder.active], [1, 1, true], '張って、最初の読み直しが終わらない');

  await w.run('present');
  assert.equal(w.counts.reload, 1, '最初の確かめはもう済んだ扱い：次の確かめ（そのまま）は読まない');

  w.reloadGates[0]!();
  await first;
  assert.equal(w.counts.reload, 1);
});

test('D0034-AC-11: 張るときの読み直しが終わらないうちに次の確かめ（有る）が来ても、追い読みの番は立っていて、その確かめが追い読みを 1 回する（そのあとは読まない）', async () => {
  const w = await build({ reloadHeld: (n) => n === 2 });
  await w.run('absent');
  const attach = w.begin('present');
  await until(() => w.reloadGates.length === 1);
  assert.deepEqual([w.counts.create, w.counts.reload, w.holder.active], [1, 2, true], '張って、2 回目の読み直しが終わらない');

  await w.run('present');
  assert.equal(w.counts.reload, 3, '追い読みの番はもう立っている：終わらない読み直しを待たずに追い読みをする');

  w.reloadGates[0]!();
  await attach;
  await w.run('present');
  assert.equal(w.counts.reload, 3, '追い読みは 1 回だけ');
});

test('D0034-AC-22: 古い確かめの読み直しが reset() のあとに終わっても、reset() が戻した「最初の確かめ」を上書きしない：次の確かめ（無い）が読み直しを 1 回する', async () => {
  const w = await build({ reloadHeld: (n) => n === 1 });
  const stale = w.begin('present');
  await until(() => w.reloadGates.length === 1);
  assert.deepEqual([w.counts.create, w.counts.reload, w.holder.active], [1, 1, true]);

  w.generation.next();
  w.checker.reset();
  assert.equal(w.holder.active, false, 'retarget がすること：世代を進め、見張りを外し、最初の確かめに戻す');

  w.reloadGates[0]!();
  await stale;
  await w.run('absent');
  assert.equal(w.counts.reload, 2, '新しい work_dir の最初の確かめは、読み直しがちょうど 1 回増える');
  await w.run('absent');
  assert.equal(w.counts.reload, 2, 'その次は読まない');
});

// ---- AC-14：新しい見張りを作る前に、古い見張りを片付ける ----

test('D0034-AC-14: attach を続けて 3 回呼ぶと、作る前に古い見張りを片付けた順が log に残る', async () => {
  const w = await build();
  for (let i = 0; i < 3; i++) assert.equal(w.holder.attach(w.dir), true);
  assert.deepEqual(w.log, ['create 1', 'dispose 1', 'create 2', 'dispose 2', 'create 3']);
});

// ---- AC-15：片付けは 2 回呼んでも安全。片付けた見張りの知らせは何もしない ----

test('D0034-AC-15: detach を 2 回呼んでも dispose は 1 回。片付けたあとは active が false', async () => {
  const w = await build();
  w.holder.attach(w.dir);
  w.holder.detach();
  w.holder.detach();
  assert.equal(w.disposes(), 1);
  assert.equal(w.holder.active, false);
});

test('D0034-AC-15: 片付けた見張りの 3 つの知らせ（作られた・変わった・消えた）は、受け口を呼ばない', async () => {
  const w = await build();
  w.holder.attach(w.dir);
  const old = w.handles[0]!;
  w.holder.detach();
  for (const kind of ['create', 'change', 'delete'] as const) old.fire(kind);
  assert.equal(w.counts.events, 0);
});

test('D0034-AC-15: 張り直したあと、古い見張りの知らせは受け口を呼ばず、新しい見張りの 3 つの知らせは 1 回ずつ呼ぶ', async () => {
  const w = await build();
  w.holder.attach(w.dir);
  const old = w.handles[0]!;
  w.holder.detach();
  w.holder.attach(w.dir);
  const fresh = w.handles[1]!;
  for (const kind of ['create', 'change', 'delete'] as const) old.fire(kind);
  assert.equal(w.counts.events, 0, '古い見張り');
  for (const kind of ['create', 'change', 'delete'] as const) {
    // 型を書く：assert.equal の絞り込みと、下の before + 1 が輪になって型が決まらなくなるのを避ける（TS7022）
    const before: number = w.counts.events;
    fresh.fire(kind);
    assert.equal(w.counts.events, before + 1, `新しい見張りの ${kind}`);
  }
});

// 片付け（dispose）が例外のときの約束：確かめの手順の中だけでなく、detach・attach の頭の片付け・reset() を直に呼んでも、例外を出さず、見張りを持ち越さない。

test('D0034-AC-15: 片付け（dispose）が例外でも detach は例外を出さず、見張りを持ち越さない（active は false。もう一度呼んでも片付けは増えない）', async () => {
  const w = await build({ disposeFails: (n) => n === 1 });
  assert.equal(w.holder.attach(w.dir), true);
  assert.doesNotThrow(() => w.holder.detach());
  assert.equal(w.holder.active, false);
  assert.doesNotThrow(() => w.holder.detach());
  assert.equal(w.disposes(), 1, '失敗した片付けを、持ち越してもう一度試さない');
});

test('D0034-AC-14: 古い見張りの片付けが例外でも attach は例外を出さず、古い見張りを持ち越さない（戻り値と active が合い、生きている見張りは多くて 1 個）', async () => {
  const w = await build({ disposeFails: (n) => n === 1 });
  assert.equal(w.holder.attach(w.dir), true);
  const results: boolean[] = [];
  assert.doesNotThrow(() => {
    results.push(w.holder.attach(w.dir));
  });
  assert.deepEqual([w.holder.active], results, '戻り値（張れたか）と active が合う');
  assert.ok(w.live() <= 1, '生きている見張りは多くて 1 個');
});

test('D0034-AC-22: 片付け（dispose）が例外でも reset() は例外を出さず、見張りを持ち越さず、最初の確かめに戻る：次の確かめ（有る）で張り直し、読み直しが 1 回増える', async () => {
  const w = await build({ disposeFails: (n) => n === 1 });
  await w.run('present');
  assert.doesNotThrow(() => w.checker.reset());
  assert.equal(w.holder.active, false);
  await w.run('present');
  assert.deepEqual([w.holder.active, w.counts.create, w.counts.reload], [true, 2, 2]);
});

// ---- AC-16：往復の列でも、同時に生きている見張りは最大 1 個 ----

async function roundTrips(steps: readonly Step[]) {
  const w = await build();
  const live: number[] = [];
  const balance: number[] = [];
  for (const step of steps) {
    await w.run(step);
    live.push(w.live());
    balance.push(w.handles.length - w.disposes());
  }
  return { w, live, balance };
}

test('D0034-AC-16: 入力 A（有る、（無い、有る）を 5 回。11 要素。最後は有る）：毎回 0 か 1 個で、最後は 1 個（作った 6・片付けた 5）', async () => {
  const steps: Step[] = ['present'];
  for (let i = 0; i < 5; i++) steps.push('absent', 'present');
  assert.equal(steps.length, 11);
  const { w, live, balance } = await roundTrips(steps);
  assert.deepEqual(live, [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]);
  assert.deepEqual(balance, live, '作った数 − 片付けた数 が、生きている数と同じ');
  assert.deepEqual([w.handles.length, w.disposes()], [6, 5]);
});

test('D0034-AC-16: 入力 B（有る、（無い、有る）を 4 回、最後に無い。10 要素）：毎回 0 か 1 個で、最後は 0 個（作った 5・片付けた 5）', async () => {
  const steps: Step[] = ['present'];
  for (let i = 0; i < 4; i++) steps.push('absent', 'present');
  steps.push('absent');
  assert.equal(steps.length, 10);
  const { w, live, balance } = await roundTrips(steps);
  assert.deepEqual(live, [1, 0, 1, 0, 1, 0, 1, 0, 1, 0]);
  assert.deepEqual(balance, live);
  assert.deepEqual([w.handles.length, w.disposes()], [5, 5]);
});

// ---- AC-17：3 つの知らせは、1 つの受け口を呼ぶ ----

test('D0034-AC-17: work_dir が最初から有るとき、最初の確かめで張って読み直し 1 回。そのあとは確かめを待たずに、3 つの知らせのどれでも受け口が 1 回ずつ呼ばれ、読み直しは増えない', async () => {
  const w = await build();
  await w.run('present');
  assert.deepEqual([w.counts.create, w.counts.reload, w.counts.events], [1, 1, 0]);
  const watch = w.handles[0]!;
  for (const kind of ['create', 'change', 'delete'] as const) watch.fire(kind);
  assert.equal(w.counts.events, 3);
  assert.equal(w.counts.reload, 1, '受け口が呼ばれるだけ。読み直し（schedule の 200ms 後）は入口がつなぐ');
});

// ---- AC-18：確かめの間隔 ----

/** 手で書いた偽のタイマー（app/refreshPolicy.test.ts の fakeTimers と同じ作り）。 */
function fakeTimers() {
  let nextId = 1;
  const pending = new Map<number, { fn: () => void; ms: number }>();
  const log = { set: [] as number[], cleared: [] as number[] };
  return {
    pending,
    log,
    setTimer: (fn: () => void, ms: number): number => {
      const id = nextId++;
      pending.set(id, { fn, ms });
      log.set.push(ms);
      return id;
    },
    clearTimer: (id: number): void => {
      log.cleared.push(id);
      pending.delete(id);
    },
    fire(): boolean {
      const first = [...pending.entries()][0];
      if (first === undefined) return false;
      pending.delete(first[0]);
      first[1].fn();
      return true;
    },
  };
}

const presenceInterval = async (): Promise<unknown> => ((await import('./refreshPolicy.ts')) as unknown as { PRESENCE_CHECK_MS?: unknown }).PRESENCE_CHECK_MS;

test('D0034-AC-18: 有無の確かめの間隔 PRESENCE_CHECK_MS は 3000ms', async () => {
  assert.equal(await presenceInterval(), 3000);
});

test('D0034-AC-18: PRESENCE_CHECK_MS で createPoller を動かすと、3000ms ごとに確かめる（終わってから次を仕掛ける）', async () => {
  const timers = fakeTimers();
  let runs = 0;
  const poller = createPoller({
    intervalMs: (await presenceInterval()) as number,
    run: async () => {
      runs++;
    },
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
  });
  poller.start();
  timers.fire();
  await settle();
  assert.equal(runs, 1);
  assert.deepEqual(timers.log.set, [3000, 3000]);
});

// ---- AC-22（部品）：reset() は見張りを片付け、「最初の確かめ」に戻す。世代は進めない ----

test('D0034-AC-22: reset() は見張りを片付け（dispose 1 回）、見張っていない状態に戻す', async () => {
  const w = await build();
  await w.run('present');
  w.checker.reset();
  assert.equal(w.disposes(), 1);
  assert.equal(w.holder.active, false);
});

const AFTER_RESET: readonly (readonly [string, Step])[] = [
  ['有る', 'present'],
  ['無い', 'absent'],
  ['分からない', 'unknown'],
  ['確かめが例外', 'throw'],
];

for (const [label, step] of AFTER_RESET) {
  test(`D0034-AC-22: reset() のあとの最初の確かめ（${label}）は、最初の確かめに戻っているので、読み直しがちょうど 1 回増える`, async () => {
    const w = await build();
    await w.run('present');
    assert.equal(w.counts.reload, 1);
    w.checker.reset();
    await w.run(step);
    assert.equal(w.counts.reload, 2);
  });
}

test('D0034-AC-22: reset() は追い読みの番も最初に戻す：（無い、有る）→ reset → （有る、有る）の読み直しの合計が 1・2・3・3', async () => {
  const w = await build();
  const totals: number[] = [];
  for (const step of ['absent', 'present'] as const) {
    await w.run(step);
    totals.push(w.counts.reload);
  }
  w.checker.reset();
  for (const step of ['present', 'present'] as const) {
    await w.run(step);
    totals.push(w.counts.reload);
  }
  assert.deepEqual(totals, [1, 2, 3, 3]);
});

test('D0034-AC-22: reset() は世代を進めない（進めるのは呼ぶ側）：reset() のあとも、先に取った番号が現役のまま', async () => {
  const w = await build();
  const mine = w.generation.next();
  w.checker.reset();
  assert.equal(w.generation.isCurrent(mine), true);
});

// ---- AC-25・26：場所によらず進む（無いあいだは張らない。できたら work_dir に 1 つだけ張る）----

const PLACES: readonly (readonly [string, string])[] = [
  ['ワークスペースの中', '/ws/docs/pipeline'],
  ['ワークスペースの外', '/outside/p/docs/pipeline'],
  ['親が何段も無い', '/ws/build/a/b/c/d'],
];

for (const [label, dir] of PLACES) {
  test(`D0034-AC-25: ${label}（${dir}）：無いあいだは見張りを 0 個のまま、できたら work_dir に 1 回だけ作る（親・ワークスペースには作らない）`, async () => {
    const w = await build({ dir });
    for (let i = 0; i < 3; i++) await w.run('absent');
    assert.equal(w.counts.create, 0);
    assert.equal(w.live(), 0);
    await w.run('present');
    assert.deepEqual(w.createdDirs, [dir]);
    assert.equal(w.live(), 1);
    assert.ok(w.probedDirs.every((d) => d === dir), '確かめに渡すのも work_dir の絶対パスだけ');
  });

  test(`D0034-AC-26: ${label}（${dir}）：「無い」から「有る」に変えると、変える前の確かめは「そのまま」（最初の確かめを除いて読み直さない）、変えたあとの最初の確かめで 張る → 読み直す`, async () => {
    const w = await build({ dir });
    assert.deepEqual(await w.run('absent'), ['probe', 'reload'], '最初の確かめ');
    assert.deepEqual(await w.run('absent'), ['probe'], '変える前：そのまま');
    assert.deepEqual(await w.run('present'), ['probe', 'create 1', 'reload'], '変えたあと：張る → 読み直す');
    assert.deepEqual(w.createdDirs, [dir]);
  });
}

// ---- AC-28：有る → 無い → 有る ----

test('D0034-AC-28: 「有る → 無い → 有る」の列で、手順は 張る → 外す → 張る の順に動き、外すときも張り直すときも読み直す', async () => {
  const w = await build();
  assert.deepEqual(await w.run('present'), ['probe', 'create 1', 'reload']);
  assert.deepEqual(await w.run('absent'), ['probe', 'dispose 1', 'reload']);
  assert.deepEqual(await w.run('present'), ['probe', 'create 2', 'reload']);
});

// ---- 純粋な部品の禁止事項を、ソースの文字で探す（AC-28・AC-37 が共通で使う）----

const VSCODE_IMPORT = /\b(?:from|import|require)\s*\(?\s*['"`]vscode['"`]/g;
const STORAGE_OR_UPDATE = /\bworkspaceState\b|\.\s*update\s*\(/g;

const flat = (text: string): string => text.replace(/\s+/g, ' ').trim();

/** vscode の読み込み（import・動的 import・require。型だけの import も）。コメントに書いただけのものは数えない。 */
function findVscodeImport(source: string): string[] {
  return Array.from(withoutComments(source).matchAll(VSCODE_IMPORT), (m) => flat(m[0]));
}

/** 選びの記憶への道（workspaceState と .update( ）。部品は読み直しの口 reload の外に書かない。 */
function findStorageOrUpdate(source: string): string[] {
  return Array.from(withoutComments(source).matchAll(STORAGE_OR_UPDATE), (m) => flat(m[0]));
}

/** 純粋な部品に無いはずのもの：時計・乱数・node: の読み込み、vscode の読み込み、選びの記憶への道。 */
function forbiddenInPureModule(source: string): string[] {
  return [...findClockOrNode(source), ...findVscodeImport(source), ...findStorageOrUpdate(source)];
}

const PURE_VIOLATIONS: readonly (readonly [string, string, readonly string[]])[] = [
  ['Date.now()', 'const at = Date.now();', ['Date']],
  ['Math.random()', 'const r = Math.random();', ['Math.random']],
  ["node: の import", "import { stat } from 'node:fs/promises';", ["from 'node:fs/promises'"]],
  ["vscode の import（* as）", "import * as vscode from 'vscode';", ["from 'vscode'"]],
  ["vscode の型だけの import", "import type { FileSystemWatcher } from 'vscode';", ["from 'vscode'"]],
  ["vscode の動的な import", "const v = await import('vscode');", ["import('vscode'"]],
  ["vscode の require", "const v = require('vscode');", ["require('vscode'"]],
  ['workspaceState', 'const memory = context.workspaceState;', ['workspaceState']],
  ['.update(', "await memory.update('pipe-in.selectedRun', key);", ['.update(']],
];

const PURE_OK: readonly (readonly [string, string])[] = [
  ['読み直しの口だけを呼ぶ', 'await options.reload();'],
  ['コメントに書いただけの workspaceState と vscode の import', "// workspaceState には書かない\n// import * as vscode from 'vscode';"],
  ['ブロックコメントに書いただけの Date.now()', '/** Date.now() は使わない（時間は poller の仕事） */'],
  ['app 層の型だけの import', "import type { Generation } from './refreshPolicy.ts';"],
  ['名前に vscode を含む文字列', "const label = 'vscode の外';"],
  ['update で始まる別の名前', 'const view = updateStatus(model); const when = row.updatedAt;'],
];

for (const [label, source, expected] of PURE_VIOLATIONS) {
  test(`D0034-AC-28: 探し方そのもの：${label} を見つける${KEEP_NOTE}`, () => {
    assert.deepEqual(forbiddenInPureModule(source), [...expected]);
  });
}

for (const [label, source] of PURE_OK) {
  test(`D0034-AC-28: 探し方そのもの：${label} は見逃す${KEEP_NOTE}`, () => {
    assert.deepEqual(forbiddenInPureModule(source), []);
  });
}

const PART = (): string => {
  try {
    return readFileSync(new URL('./workDirWatch.ts', import.meta.url), 'utf8');
  } catch {
    return assert.fail('app/workDirWatch.ts がまだ無い');
  }
};

test('D0034-AC-28: 部品は選びの記憶に触れない：workDirWatch.ts の文字に workspaceState・.update( が無い（読み直しの口 reload だけを呼ぶ）', () => {
  assert.deepEqual(findStorageOrUpdate(PART()), []);
});

test('D0034-AC-37: 判断は app 層の純粋な部品に置く：workDirWatch.ts は時計・乱数・node: の読み込み・vscode の読み込みを持たない', () => {
  assert.deepEqual(forbiddenInPureModule(PART()), []);
});
