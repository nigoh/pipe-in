// 段の判定の札と、右のパネルの判定の箱（D0005）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { END, newPipe, newStage } from '../domain/pipeModel.ts';
import type { BlockKind, PipeModel, StageModel } from '../domain/pipeModel.ts';
import { checkBoxHtml, checkChip, checkChipHtml } from './checkHtml.ts';

function stage(id: string, kind: BlockKind, x: number, y: number, over: Partial<StageModel> = {}): StageModel {
  return { ...newStage(id, kind, id), prompt: 'x', x, y, ...over };
}

/** a（名前に < > を含む）→ b → c → 並列の枠 F（f1）→ 終わり。c は判定に通らなければ a へ戻す。b は自分をやり直す。 */
function sample(): PipeModel {
  const m = newPipe('check');
  m.stages = [
    stage('a', 'research', 100, 100, { next: 'b', label: '<b>調べる' }),
    stage('b', 'research', 400, 100, { next: 'c', check: { on: true, verdict: true, command: '', maxRetries: 2 } }),
    stage('c', 'research', 700, 100, { next: 'F', check: { on: true, verdict: true, command: '', maxRetries: 3 }, onFail: 'a' }),
    stage('f1', 'docs', 1050, 40, { check: { on: true, verdict: true, command: '', maxRetries: 1 } }),
    stage('d', 'research', 1500, 100, { next: END }),
  ];
  m.frames = [{ id: 'F', name: 'g', x: 1000, y: 0, w: 320, h: 200, next: 'd' }];
  return m;
}
const st = (m: PipeModel, id: string): StageModel => m.stages.find((s) => s.id === id)!;
const options = (html: string): string[] => [...html.matchAll(/<option[^>]*>([^<]*)<\/option>/g)].map((x) => x[1]!);

test('D0005-AC-07: 自分をやり直す段の札は「判定 ↻」で、説明に「この段をやり直す」と戻す上限の回数が入る', () => {
  const m = sample();
  const chip = checkChip(m, st(m, 'b'));
  assert.ok(chip);
  assert.equal(chip.text, '判定 ↻');
  assert.match(chip.title, /この段をやり直す/);
  assert.match(chip.title, /2 回/);
});

test('D0005-AC-08: 前の段へ戻す段の札は「判定 ↩」で、説明に戻す先の名前と回数が入り、名前はエスケープされる', () => {
  const m = sample();
  const chip = checkChip(m, st(m, 'c'));
  assert.ok(chip);
  assert.equal(chip.text, '判定 ↩');
  assert.match(chip.title, /<b>調べる/);
  assert.match(chip.title, /3 回/);
  const html = checkChipHtml(m, st(m, 'c'));
  assert.match(html, /判定 ↩/);
  assert.match(html, /&lt;b&gt;調べる/);
  assert.doesNotMatch(html, /<b>/);
});

test('D0005-AC-09: 判定がオフの段には、札が出ない', () => {
  const m = sample();
  assert.equal(checkChip(m, st(m, 'a')), null);
  assert.equal(checkChipHtml(m, st(m, 'a')), '');
});

test('D0005-AC-10: 判定の箱には、見出し「判定」と「判定する」のスイッチ（#b-check）がある', () => {
  const m = sample();
  for (const id of ['a', 'b']) {
    const html = checkBoxHtml(m, st(m, id));
    assert.match(html, /<h3>判定<\/h3>/);
    assert.match(html, /<input type="checkbox" id="b-check"/);
    assert.match(html, /判定する/);
  }
  assert.match(checkBoxHtml(m, st(m, 'b')), /id="b-check" checked/);
  assert.doesNotMatch(checkBoxHtml(m, st(m, 'a')), /id="b-check" checked/);
});

test('D0005-AC-11: 判定がオフのときは、スイッチと説明だけで、ほかの欄が無い', () => {
  const m = sample();
  const html = checkBoxHtml(m, st(m, 'a'));
  assert.match(html, /オンにすると/);
  for (const id of ['b-onfail', 'b-retries', 'b-command', 'b-verdict']) assert.doesNotMatch(html, new RegExp(`id="${id}"`), id);
});

test('D0005-AC-12: 判定がオンのときは、判定のしかた・確認用のコマンド・不合格のとき・戻す上限の欄がある', () => {
  const m = sample();
  const html = checkBoxHtml(m, st(m, 'c'));
  for (const id of ['b-verdict', 'b-command', 'b-onfail', 'b-retries']) assert.match(html, new RegExp(`id="${id}"`), id);
  assert.match(html, /Claude が判定する/);
  assert.match(html, /不合格のとき/);
});

test('D0005-AC-13: 「不合格のとき」の選択肢は、この段をやり直す＋前の段。枠の中の段は、この段をやり直すだけ', () => {
  const m = sample();
  assert.deepEqual(options(checkBoxHtml(m, st(m, 'c'))), ['この段をやり直す', '&lt;b&gt;調べる', 'b']);
  assert.match(checkBoxHtml(m, st(m, 'c')), /<option value="a" selected>/);
  assert.deepEqual(options(checkBoxHtml(m, st(m, 'f1'))), ['この段をやり直す']);
});

test('D0005-AC-13: 並列の枠の中の前の段へ戻す段では、その段が選ばれた状態で出る（行き先が消えない）', () => {
  const m = sample();
  const d = st(m, 'd');
  d.check = { on: true, verdict: true, command: '', maxRetries: 2 };
  d.onFail = 'f1';
  const html = checkBoxHtml(m, d);
  assert.match(html, /<option value="f1" selected>f1<\/option>/);
  assert.deepEqual(checkChip(m, d)?.text, '判定 ↩');
});
