// 段の判定：スイッチのオン・オフと、不合格のときの行き先（D0005）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { END, newPipe, newStage, validatePipe } from './pipeModel.ts';
import type { BlockKind, PipeModel, StageModel } from './pipeModel.ts';
import { failKind, failTargets, setCheck } from './pipeCheck.ts';

function stage(id: string, kind: BlockKind, x: number, y: number, over: Partial<StageModel> = {}): StageModel {
  return { ...newStage(id, kind, id), prompt: 'x', x, y, ...over };
}

/** a → b → c → 並列の枠 F（f1）→ d → 終わり。c は判定に通らなければ a へ戻す。 */
function sample(): PipeModel {
  const m = newPipe('check');
  m.stages = [
    stage('a', 'research', 100, 100, { next: 'b' }),
    stage('b', 'research', 400, 100, { next: 'c' }),
    stage('c', 'research', 700, 100, { next: 'F', check: { on: true, verdict: true, command: 'npm test', maxRetries: 3 }, onFail: 'a' }),
    stage('f1', 'docs', 1050, 40),
    stage('d', 'research', 1500, 100, { next: END }),
  ];
  m.frames = [{ id: 'F', name: 'g', x: 1000, y: 0, w: 320, h: 200, next: 'd' }];
  m.start = { x: -200, y: 110 };
  m.end = { x: 1800, y: 110 };
  return m;
}
const st = (m: PipeModel, id: string): StageModel => m.stages.find((s) => s.id === id)!;
const checkErrors = (m: PipeModel): string[] => validatePipe(m).errors.filter((e) => /判定|差し戻し|検証|check/.test(e));

test('D0005-AC-13: 不合格のときの選択肢は、並びで自分より前の段だけ（自分と後ろの段は入らない）', () => {
  const m = sample();
  assert.deepEqual(failTargets(m, st(m, 'c')).map((s) => s.id), ['a', 'b']);
  assert.deepEqual(failTargets(m, st(m, 'a')).map((s) => s.id), []);
});

test('D0005-AC-13: 並列の枠の中の段には、前の段の選択肢が無い（この段をやり直すだけ）', () => {
  const m = sample();
  assert.deepEqual(failTargets(m, st(m, 'f1')), []);
});

test('D0005-AC-13: 不合格の行き先の種類は、自分（onFail が無い・自分）か前の段', () => {
  const m = sample();
  assert.equal(failKind(m, st(m, 'c')), 'back');
  st(m, 'b').check.on = true;
  assert.equal(failKind(m, st(m, 'b')), 'self');
  st(m, 'b').onFail = 'b';
  assert.equal(failKind(m, st(m, 'b')), 'self');
  st(m, 'b').onFail = 'gone';
  assert.equal(failKind(m, st(m, 'b')), 'self');
});

test('D0005-AC-14: 判定がオフの段でスイッチをオンにすると、on・verdict が true、onFail が null になり、検査を通る', () => {
  const m = sample();
  const b = st(m, 'b');
  b.check = { on: false, verdict: false, command: '', maxRetries: 2 };
  b.onFail = 'a';
  setCheck(b, true);
  assert.equal(b.check.on, true);
  assert.equal(b.check.verdict, true);
  assert.equal(b.onFail, null);
  assert.deepEqual(checkErrors(m), []);
});

test('D0005-AC-15: 前の段へ戻す段でスイッチをオフにすると、on が false、onFail が null になる', () => {
  const m = sample();
  const c = st(m, 'c');
  setCheck(c, false);
  assert.equal(c.check.on, false);
  assert.equal(c.onFail, null);
});

test('D0005-AC-15: すでにオンの段をもう一度オンにしても、行き先やコマンドは消えない', () => {
  const m = sample();
  const c = st(m, 'c');
  setCheck(c, true);
  assert.equal(c.check.on, true);
  assert.equal(c.onFail, 'a');
  assert.equal(c.check.command, 'npm test');
  assert.equal(c.check.maxRetries, 3);
});
