// 図の判定の節（D0062 の AC-09・AC-11・AC-14〜16 の下地）：check:<段> の節の形・札・「N / 上限 回」・状態のクラス・戻りの矢印・選べる印。
// 画面の見え方そのもの（重なり・色・クリックの動き）は画面の確認（run-panel-check-*。手順は .claude/skills/pipe-in/screen-check.md）で見る。ここは形の下地。
// checkChipText（pipeCheck.ts）は、実装の段で入るまで、名前空間 import で読む（無ければ「無い」ことを理由に落とす）。
// 赤の理由は「まだ描いていない」：check:<段> の節が SVG に無い（nodeG が「節がある」で落とす）／戻りの矢印が無い。
// 「今のまま通る。守る」と書いたものは、今の作りで通り、実装のあとも通り続けることを見張る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import * as pipeCheck from '../domain/pipeCheck.ts';
import { reasonNodeIds } from '../domain/pipelineView.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { renderFlowSvg } from './flowSvg.ts';
import { classesOf, nodeG, textsOf } from '../test/budgetFixtures.ts';
import { checkEntry, checkView, runEntry, stageDef } from '../test/checkFixtures.ts';

/** checkChipText（無ければ、無いことを理由に落とす） */
function chipText(kind: 'self' | 'back'): string {
  const fn = (pipeCheck as Record<string, unknown>).checkChipText;
  if (typeof fn !== 'function') assert.fail('pipeCheck.checkChipText が無い（まだ作っていない）');
  return (fn as (k: 'self' | 'back') => string)(kind);
}

const svgOf = (view: PipelineView): string => renderFlowSvg(view.nodes, new Set(reasonNodeIds(view)), null);
const fail = (stage: string, attempt: number) => checkEntry({ stage, status: 'fail', attempt });
const pass = (stage: string, attempt: number) => checkEntry({ stage, status: 'pass', attempt });

const SELF3 = { on_fail: null, max_retries: 3 };
const BACK2 = { on_fail: 'draw', max_retries: 2 };
const selfStages = [stageDef({ name: 'verify', check: SELF3 })];
const backStages = [stageDef({ name: 'draw' }), stageDef({ name: 'verify', check: BACK2 })];

/** 自分をやり直す判定が、1 回 fail → pass で終わった図 */
const selfDone = (): PipelineView =>
  checkView([runEntry('verify', 1), fail('verify', 1), runEntry('verify', 2), pass('verify', 2)], { pipe: 'p', stages: selfStages });
/** 前の段へ戻す判定が、上限（2 回）まで落ちた図 */
const backExhausted = (): PipelineView =>
  checkView(
    [runEntry('draw', 1), runEntry('verify', 2), fail('verify', 1), runEntry('draw', 3), runEntry('verify', 4), fail('verify', 2), runEntry('draw', 5), runEntry('verify', 6), fail('verify', 3)],
    { pipe: 'p', stages: backStages, final: 'TEST_FAILED' },
  );

/** 戻りの矢印 <g class="loop…" data-loop="id">…</g>。無ければ null。 */
const loopG = (svg: string, id: string): string | null =>
  new RegExp(`<g class="loop[^"]*" data-loop="${id}"[\\s\\S]*?</g>`).exec(svg)?.[0] ?? null;
/** 矢印の道筋 d の x の値 */
const xsOf = (g: string): number[] => {
  const d = /<path class="loop-path" d="([^"]*)"/.exec(g)?.[1] ?? '';
  return [...d.matchAll(/[ML]\s*(-?[\d.]+)[ ,]\s*(-?[\d.]+)/g)].map((m) => Number(m[1]));
};

// ======== AC-09：戻りの矢印 ========

test('D0062-AC-09: on_fail が別の段なら check:<段> から戻り先への戻りの辺（data-loop="check:<段>"）が入る', () => {
  const g = loopG(svgOf(backExhausted()), 'check:verify');
  assert.ok(g !== null, 'data-loop="check:verify" の矢印がある');
  assert.match(g, /marker-end="url\(#mk-(hot|loop)\)"/, '矢じりが付く');
  const xs = xsOf(g);
  assert.ok(xs.length >= 3, '道筋が折れ線になっている');
  assert.ok(Math.min(...xs) >= 10 && Math.min(...xs) <= 30, `左の通り道（x が 10〜30）を通る: ${xs.join(',')}`);
});

test('D0062-AC-09: 自分をやり直す判定は辺を入れない', () => {
  const svg = svgOf(selfDone());
  assert.ok(svg.includes('data-node="check:verify"'), '判定の節は図にある');
  assert.equal(loopG(svg, 'check:verify'), null);
  assert.doesNotMatch(svg, /data-loop="check:/);
});

test('D0062-AC-09: 戻りの辺が複数あるときは通り道が重ならず、最小 10 より左へ出ない', () => {
  const stages = [
    stageDef({ name: 'draw' }),
    ...Array.from({ length: 6 }, (_, i) => stageDef({ name: `v${i}`, check: { on_fail: 'draw', max_retries: 1 } })),
  ];
  const svg = svgOf(checkView([runEntry('draw', 1)], { pipe: 'p', stages }));
  const minXs = [0, 1, 2, 3, 4, 5].map((i) => {
    const g = loopG(svg, `check:v${i}`);
    assert.ok(g !== null, `check:v${i} の矢印がある`);
    return Math.min(...xsOf(g));
  });
  assert.ok(minXs.every((x) => x >= 10), `どれも x が 10 以上: ${minXs.join(',')}`);
  assert.ok(new Set(minXs.slice(0, 3)).size === 3, `最初の 3 本は通り道が別: ${minXs.join(',')}`);
});

// ======== AC-11：札の文字 ========

test('D0062-AC-11: 図の節の札は checkChipText の文字（自分をやり直す＝判定 ↻、前の段へ戻す＝判定 ↩）', () => {
  const self = textsOf(nodeG(svgOf(selfDone()), 'check:verify'));
  assert.ok(self.some((t) => t.includes(chipText('self'))), `自分をやり直す: ${self.join(' | ')}`);
  const back = textsOf(nodeG(svgOf(backExhausted()), 'check:verify'));
  assert.ok(back.some((t) => t.includes(chipText('back'))), `前の段へ戻す: ${back.join(' | ')}`);
  assert.equal(chipText('self'), '判定 ↻');
  assert.equal(chipText('back'), '判定 ↩');
});

test('D0062-AC-11: 札の文字が checkHtml.ts と flowSvg.ts に直に書かれていない（pipeCheck.ts にだけある）', () => {
  const read = (name: string): string => readFileSync(fileURLToPath(new URL(name, import.meta.url)), 'utf8');
  const literals = ['判定 ↻', '判定 ↩'];
  for (const literal of literals) {
    assert.ok(!read('./checkHtml.ts').includes(literal), `checkHtml.ts に「${literal}」が直に書かれている`);
    assert.ok(!read('./flowSvg.ts').includes(literal), `flowSvg.ts に「${literal}」が直に書かれている`);
    assert.ok(read('../domain/pipeCheck.ts').includes(literal), `pipeCheck.ts に「${literal}」が無い`);
  }
});

// ======== AC-14：自分をやり直す判定が 1 回 fail → pass（下地） ========

test('D0062-AC-14: 札・「1 / 3 回」・is-done', () => {
  const g = nodeG(svgOf(selfDone()), 'check:verify');
  assert.ok(classesOf(g).includes('is-done'), `クラス: ${classesOf(g).join(' ')}`);
  const texts = textsOf(g);
  assert.ok(texts.some((t) => t.includes(chipText('self'))), `札: ${texts.join(' | ')}`);
  assert.ok(texts.some((t) => t.includes('1 / 3 回')), `回数: ${texts.join(' | ')}`);
});

test('D0062-AC-14: 上限が記録に無いときは「N 回」だけで、「/」は出さない', () => {
  const stages = [stageDef({ name: 'verify', check: { on_fail: null } })];
  const runs = [runEntry('verify', 1), fail('verify', 1), runEntry('verify', 2), pass('verify', 2)];
  const texts = textsOf(nodeG(svgOf(checkView(runs, { pipe: 'p', stages })), 'check:verify'));
  assert.ok(texts.some((t) => t.includes('1 回')), texts.join(' | '));
  assert.ok(!texts.some((t) => t.includes('/')), `「/」が出ている: ${texts.join(' | ')}`);
});

// ======== AC-15：前の段へ戻す判定が上限まで落ちた（下地） ========

test('D0062-AC-15: is-failed・戻りの矢印・上限まで', () => {
  const svg = svgOf(backExhausted());
  const g = nodeG(svg, 'check:verify');
  assert.ok(classesOf(g).includes('is-failed'), `クラス: ${classesOf(g).join(' ')}`);
  assert.ok(loopG(svg, 'check:verify') !== null, '戻りの矢印がある');
  const texts = textsOf(g);
  assert.ok(texts.some((t) => t.includes('上限まで')), `「上限まで」の言葉: ${texts.join(' | ')}`);
  assert.ok(texts.some((t) => t.includes('2 / 2 回')), `回数: ${texts.join(' | ')}`);
  assert.ok(texts.some((t) => t.includes(chipText('back'))), `札: ${texts.join(' | ')}`);
});

test('D0062-AC-15: 上限の手前で fail のままの節（上限まで落ちていない）には「上限まで」を出さない', () => {
  const runs = [runEntry('draw', 1), runEntry('verify', 2), fail('verify', 1)];
  const g = nodeG(svgOf(checkView(runs, { pipe: 'p', stages: backStages })), 'check:verify');
  assert.ok(classesOf(g).includes('is-failed'));
  assert.ok(!textsOf(g).some((t) => t.includes('上限まで')), textsOf(g).join(' | '));
});

// ======== AC-16：選べる印 ========

test('D0062-AC-16: 判定の節に data-reasons と data-reasons-loop が付く', () => {
  const g = nodeG(svgOf(backExhausted()), 'check:verify');
  assert.match(g, /data-reasons="check:verify"/);
  assert.match(g, /data-reasons-loop="check:verify"/);
  assert.match(g, /tabindex="0"/);
  assert.match(g, /role="button"/);
});

test('D0062-AC-16: 自分をやり直す判定の節も選べる（data-reasons が付く）', () => {
  assert.match(nodeG(svgOf(selfDone()), 'check:verify'), /data-reasons="check:verify"/);
});

test('D0062-AC-16: 検証がまだ無い判定の節は選べない（印が付かない）', () => {
  const g = nodeG(svgOf(checkView([runEntry('draw', 1)], { pipe: 'p', stages: backStages })), 'check:verify');
  assert.doesNotMatch(g, /data-reasons/);
});

// ======== 外から来た文字 ========

test('D0062-AC-14: 段の表示の名前の外から来た文字は図に生のまま出ない。今のまま通る。守る', () => {
  const stages = [stageDef({ name: 'verify', label: '<script>alert(1)</script>', check: SELF3 })];
  const svg = svgOf(checkView([runEntry('verify', 1), pass('verify', 1)], { pipe: 'p', stages }));
  assert.ok(!svg.includes('<script>'), '生の <script> が出ている');
});
