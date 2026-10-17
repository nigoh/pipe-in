// ケーブルの抜き差し：差し直しても種類（次の段・分岐・差し戻し）はそのままで、行き先だけ変わる。合わない先は断る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { END, newPipe, newStage, orderStages } from './pipeModel.ts';
import type { BlockKind, PipeModel, StageModel } from './pipeModel.ts';
import type { Wire } from './pipeWires.ts';
import { insertBetween, replug, unplug } from './pipeLinks.ts';

function stage(id: string, kind: BlockKind, x: number, y: number, over: Partial<StageModel> = {}): StageModel {
  return { ...newStage(id, kind, id), x, y, ...over };
}

/**
 * a → b（仕分け：x は c へ、y は終わりへ）、c → 並列の枠 F（f1・f2）→ d → 終わり。
 * d は判定に通らなければ a へ戻す。c は判定に通らなければ a へ戻す。f1 は自分をやり直す。
 */
function sample(): PipeModel {
  const m = newPipe('links');
  m.stages = [
    stage('a', 'research', 100, 100, { next: 'b' }),
    stage('b', 'branch', 400, 80, { routes: [{ key: 'x', to: 'c' }, { key: 'y', to: END }] }),
    stage('c', 'research', 700, 100, { next: 'F', check: { on: true, verdict: true, command: '', maxRetries: 2 }, onFail: 'a' }),
    stage('f1', 'docs', 1050, 40, { check: { on: true, verdict: true, command: '', maxRetries: 2 } }),
    stage('f2', 'docs', 1050, 200),
    stage('d', 'verify', 1500, 100, { next: END, onFail: 'a' }),
  ];
  m.frames = [{ id: 'F', name: 'g', x: 1000, y: 0, w: 320, h: 340, next: 'd' }];
  m.start = { x: -200, y: 110 };
  m.end = { x: 1800, y: 110 };
  return m;
}
const wire = (kind: Wire['kind'], from: string, to: string, extra: Partial<Wire> = {}): Wire => ({ kind, from, to, owner: from, points: [], ...extra });
const st = (m: PipeModel, id: string): StageModel => m.stages.find((s) => s.id === id)!;

test('D0005-AC-04: 前の段へ戻すケーブルを抜くと、判定はオンのまま onFail が null になり、知らせに「この段をやり直す」が入る', () => {
  const m = sample();
  const r = unplug(m, wire('return', 'c', 'a'));
  assert.equal(r.changed, true);
  assert.equal(st(m, 'c').check.on, true);
  assert.equal(st(m, 'c').onFail, null);
  assert.match(r.message, /この段をやり直す/);
});

test('AC-51: 次の段のケーブルは、右にある段・枠・終わりへ差し直せる', () => {
  for (const [to, want] of [['c', 'c'], ['F', 'F'], [END, END]] as const) {
    const m = sample(), r = replug(m, wire('next', 'a', 'b'), to);
    assert.equal(r.changed, true, to);
    assert.equal(st(m, 'a').next, want);
    assert.ok(r.message.length > 0);
  }
});

test('AC-51: 次の段のケーブルを左（前）の段へ差すと断り、何も変えない', () => {
  const m = sample(), r = replug(m, wire('next', 'c', 'F'), 'a');
  assert.equal(r.changed, false);
  assert.match(r.message, /右/);
  assert.equal(st(m, 'c').next, 'F');
  assert.equal(st(m, 'c').onFail, 'a'); // 差し戻しには変わらない
});

test('AC-51: 元のコンセントに差し戻したときは、何も変えず知らせもない', () => {
  const m = sample(), r = replug(m, wire('next', 'a', 'b'), 'b');
  assert.deepEqual(r, { changed: false, message: '' });
  assert.equal(st(m, 'a').next, 'b');
});

test('AC-52: 分岐のケーブルは、選択肢の名前を残して行き先だけ変わる', () => {
  const m = sample(), r = replug(m, wire('route', 'b', 'c', { label: 'x' }), 'd');
  assert.equal(r.changed, true);
  assert.deepEqual(st(m, 'b').routes, [{ key: 'x', to: 'd' }, { key: 'y', to: END }]);
});

test('AC-52: 分岐は、同じ行き先がもうある所と、左（前）の段へは差せない', () => {
  const m = sample();
  const dup = replug(m, wire('route', 'b', 'c', { label: 'x' }), END);
  assert.equal(dup.changed, false);
  assert.match(dup.message, /もう/);
  const back = replug(m, wire('route', 'b', 'c', { label: 'x' }), 'a');
  assert.equal(back.changed, false);
  assert.deepEqual(st(m, 'b').routes, [{ key: 'x', to: 'c' }, { key: 'y', to: END }]);
});

test('AC-53: 差し戻しのケーブルは、前の段へ差し直せる。自分へ差すと自分をやり直す', () => {
  const m = sample();
  const r = replug(m, wire('return', 'd', 'a'), 'c');
  assert.equal(r.changed, true);
  assert.equal(st(m, 'd').onFail, 'c');
  assert.equal(st(m, 'd').check.on, true);
  const self = replug(m, wire('return', 'd', 'c'), 'd');
  assert.equal(self.changed, true);
  assert.equal(st(m, 'd').onFail, null);
  assert.equal(st(m, 'd').check.on, true);
});

test('AC-53: 差し戻しは、後ろの段・枠・終わりへは差せない', () => {
  const m = sample();
  for (const to of ['d', 'F', END]) {
    const r = replug(m, wire('return', 'c', 'a'), to);
    assert.equal(r.changed, false, to);
    assert.ok(r.message.length > 0, to);
  }
  assert.equal(st(m, 'c').onFail, 'a');
});

test('AC-53: 並列の枠の中の段の差し戻しは、自分だけ（ほかへは断る）', () => {
  const m = sample(), r = replug(m, wire('return', 'f1', 'f1', { self: true }), 'a');
  assert.equal(r.changed, false);
  assert.match(r.message, /枠/);
  assert.equal(st(m, 'f1').onFail, null);
});

test('AC-54: 並列の枠から出るケーブルは、右にある段へだけ差し直せる', () => {
  const m = sample();
  assert.equal(replug(m, wire('next', 'F', 'd'), END).changed, true);
  assert.equal(m.frames[0]!.next, END);
  const back = replug(m, wire('next', 'F', END), 'c');
  assert.equal(back.changed, false);
  assert.equal(m.frames[0]!.next, END);
});

test('AC-55: 抜くと、どの種類のつなぎも外れる（差し戻しは判定を残す。D0005-AC-04 で変えた）', () => {
  const m = sample();
  assert.equal(unplug(m, wire('next', 'a', 'b')).changed, true);
  assert.equal(st(m, 'a').next, null);
  assert.equal(unplug(m, wire('route', 'b', 'c', { label: 'x' })).changed, true);
  assert.deepEqual(st(m, 'b').routes, [{ key: 'y', to: END }]);
  assert.equal(unplug(m, wire('return', 'd', 'a')).changed, true);
  assert.equal(st(m, 'd').onFail, null);
  assert.equal(st(m, 'd').check.on, true);
  assert.equal(unplug(m, wire('next', 'F', 'd')).changed, true);
  assert.equal(m.frames[0]!.next, null);
});

test('AC-55: 始まりから出るケーブルは自動なので、抜くことも差し直すこともできない', () => {
  const m = sample();
  const s = wire('start', 'start', 'a', { owner: undefined });
  assert.equal(unplug(m, s).changed, false);
  assert.equal(replug(m, s, 'c').changed, false);
  assert.equal(st(m, 'a').next, 'b');
});

// ---- ケーブルの上に落として、間に挟む ----

/** sample に、どこともつながっていない段 n を足したもの */
function withLoose(): PipeModel {
  const m = sample();
  m.stages.push(stage('n', 'code', 100, 600));
  return m;
}
const order = (m: PipeModel): string[] => orderStages(m).map((s) => s.id);

test('AC-61: 次の段のケーブルに挟むと A → X → B になり、並びも A, X, B の順になる。場所が足りなければ B から右をずらす', () => {
  const m = withLoose();
  const before = { b: st(m, 'b').x, c: st(m, 'c').x, f: m.frames[0]!.x, f1: st(m, 'f1').x, end: m.end.x };
  const r = insertBetween(m, wire('next', 'a', 'b'), 'n');
  assert.equal(r.changed, true);
  assert.ok(r.message.length > 0);
  assert.equal(st(m, 'a').next, 'n');
  assert.equal(st(m, 'n').next, 'b');
  const ord = order(m);
  assert.ok(ord.indexOf('a') < ord.indexOf('n') && ord.indexOf('n') < ord.indexOf('b'));
  assert.ok(st(m, 'n').x > st(m, 'a').x);
  const shift = st(m, 'b').x - before.b;
  assert.ok(shift > 0, 'B を右へずらした');
  // B より右にあるものは、同じだけずれる（枠と中の段・終わりも）
  assert.equal(st(m, 'c').x - before.c, shift);
  assert.equal(m.frames[0]!.x - before.f, shift);
  assert.equal(st(m, 'f1').x - before.f1, shift);
  assert.equal(m.end.x - before.end, shift);
  // A より左にあるものは動かない
  assert.equal(st(m, 'a').x, 100);
});

test('AC-61: 間が広ければ、何もずらさない', () => {
  const m = newPipe('wide');
  m.stages = [stage('a', 'research', 100, 100, { next: 'z' }), stage('z', 'research', 1400, 100, { next: END }), stage('n', 'code', 100, 500)];
  m.end = { x: 1800, y: 110 };
  const r = insertBetween(m, wire('next', 'a', 'z'), 'n');
  assert.equal(r.changed, true);
  assert.equal(st(m, 'z').x, 1400);
  assert.equal(m.end.x, 1800);
  assert.deepEqual(order(m), ['a', 'n', 'z']);
});

test('AC-61: 枠から出るケーブルにも、終わりへ入るケーブルにも挟める', () => {
  const m = withLoose();
  assert.equal(insertBetween(m, wire('next', 'F', 'd'), 'n').changed, true);
  assert.equal(m.frames[0]!.next, 'n');
  assert.equal(st(m, 'n').next, 'd');
  const m2 = withLoose();
  assert.equal(insertBetween(m2, wire('next', 'd', END), 'n').changed, true);
  assert.equal(st(m2, 'd').next, 'n');
  assert.equal(st(m2, 'n').next, END);
});

test('AC-62: 分岐・差し戻し・始まりのケーブルには挟まず、理由を返して何も変えない', () => {
  for (const w of [wire('route', 'b', 'c', { label: 'x' }), wire('return', 'd', 'a'), wire('start', 'start', 'a', { owner: undefined })]) {
    const m = withLoose(), before = JSON.stringify(m);
    const r = insertBetween(m, w, 'n');
    assert.equal(r.changed, false, w.kind);
    assert.ok(r.message.length > 0, w.kind);
    assert.equal(JSON.stringify(m), before, w.kind);
  }
});

test('AC-62: つながっている段・枠の中の段・ケーブルの両端の段は挟まない', () => {
  for (const id of ['c', 'f2', 'a', 'b', 'nothing']) {
    const m = withLoose(), before = JSON.stringify(m);
    const r = insertBetween(m, wire('next', 'a', 'b'), id);
    assert.equal(r.changed, false, id);
    assert.equal(JSON.stringify(m), before, id);
  }
});
