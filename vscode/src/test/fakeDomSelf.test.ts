// テストの補助（fakeDom.ts）自身の検査（D0017）：偽の時計・setInterval・visibilityState・matchMedia・textContent・getAnimations。
// 補助が間違っていると、パネルのスクリプトのテストが間違った理由で通る・落ちるので、補助そのものの動きを確かめておく。
// パネルの本物のスクリプトは使わず、補助を呼ぶだけの小さなスクリプトで試す。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { bootPanel } from './fakeDom.ts';
import type { BootOptions } from './fakeDom.ts';

const SCRIPT = `
const vscode = acquireVsCodeApi();
const root = document.querySelector('.root');
let n = 0;
const id = setInterval(function () { n++; root.textContent = 'n=' + n + ' t=' + (Date.now() % 100000); }, 1000);
window.addEventListener('message', function (e) { if (e.data === 'stop') clearInterval(id); });
document.addEventListener('visibilitychange', function () { root.setAttribute('data-vis', document.visibilityState); });
root.setAttribute('data-vis', document.visibilityState);
root.setAttribute('data-reduce', String(window.matchMedia('(prefers-reduced-motion: reduce)').matches));
root.setAttribute('data-nopref', String(window.matchMedia('(prefers-reduced-motion: no-preference)').matches));
`;
const page = `<!DOCTYPE html><html><body><div class="root"></div><script nonce="x">${SCRIPT}</script></body></html>`;
const boot = (opts?: BootOptions) => bootPanel(page, opts);

test('D0017-AC-22: 偽の時計は startMs から始まり、advance で進む（本物の時間を使わない）', () => {
  const h = boot({ startMs: 5000 });
  assert.equal(h.now(), 5000);
  h.advance(2500);
  assert.equal(h.now(), 7500);
});

test('D0017-AC-22: setInterval は期限の来た数だけ呼ばれ、1 秒に満たない advance では呼ばれない', () => {
  const h = boot({ startMs: 0 });
  h.advance(999);
  assert.equal(h.text(h.root), '');
  h.advance(1);
  assert.equal(h.text(h.root), 'n=1 t=1000');
  h.advance(2500);
  assert.equal(h.text(h.root), 'n=3 t=3000', '2000・3000 の 2 回が呼ばれ、最後の呼びは 3000 の時刻で行われる');
  assert.equal(h.now(), 3500, 'advance の終わりでは時計が目的の時刻に着く');
});

test('D0017-AC-22: 1 回の advance で何回分の期限が来ても、期限の時刻の順に時計を進めながら呼ぶ', () => {
  const h = boot({ startMs: 0 });
  h.advance(3000);
  assert.equal(h.text(h.root), 'n=3 t=3000');
  assert.equal(h.now(), 3000);
});

test('D0017-AC-23: activeIntervals と createdIntervals は、作った数・止めていない数を数える。clearInterval で止まる', () => {
  const h = boot();
  assert.equal(h.activeIntervals(), 1);
  assert.equal(h.createdIntervals(), 1);
  h.send('stop');
  assert.equal(h.activeIntervals(), 0);
  assert.equal(h.createdIntervals(), 1, '作った数は減らない');
  const before = h.text(h.root);
  h.advance(10_000);
  assert.equal(h.text(h.root), before, '止めたあとは呼ばれない');
});

test('D0017-AC-25: setNow は時計だけを動かし（戻せる）、タイマーは呼ばない。tick は時計を動かさず 1 回ずつ呼ぶ', () => {
  const h = boot({ startMs: 10_000 });
  h.setNow(2000);
  assert.equal(h.now(), 2000);
  assert.equal(h.text(h.root), '');
  h.tick();
  assert.equal(h.text(h.root), 'n=1 t=2000');
  assert.equal(h.now(), 2000);
});

test('D0017-AC-24: setVisibility は document.visibilityState を替え、visibilitychange を届ける', () => {
  const h = boot();
  assert.equal(h.root.getAttribute('data-vis'), 'visible');
  h.setVisibility('hidden');
  assert.equal(h.doc.visibilityState, 'hidden');
  assert.equal(h.root.getAttribute('data-vis'), 'hidden');
  h.setVisibility('visible');
  assert.equal(h.root.getAttribute('data-vis'), 'visible');
  assert.equal(boot({ visibility: 'hidden' }).root.getAttribute('data-vis'), 'hidden', '最初から hidden で開ける');
});

test('D0017-AC-30: matchMedia は reducedMotion の指定のとおりに reduce・no-preference へ答える', () => {
  const normal = boot();
  assert.equal(normal.root.getAttribute('data-reduce'), 'false');
  assert.equal(normal.root.getAttribute('data-nopref'), 'true');
  const reduced = boot({ reducedMotion: true });
  assert.equal(reduced.root.getAttribute('data-reduce'), 'true');
  assert.equal(reduced.root.getAttribute('data-nopref'), 'false');
});

test('D0017-AC-22: textContent に代入すると子が 1 つの文字に替わり、空にすると子が無くなる', () => {
  const h = boot();
  h.root.textContent = 'abc';
  assert.equal(h.root.children.length, 1);
  assert.equal(h.root.textContent, 'abc');
  h.root.textContent = '';
  assert.equal(h.root.children.length, 0);
  assert.equal(h.root.textContent, '');
});

test('D0017-AC-29: getAnimations は is-new が付いている間だけ 1 つの動きを返し、外すと空。noAnimations では持たない', () => {
  const h = boot();
  const el = h.root;
  assert.deepEqual(el.getAnimations!(), []);
  el.classList.add('is-new');
  const first = el.getAnimations!();
  assert.equal(first.length, 1);
  first[0].currentTime = 600;
  assert.equal(el.getAnimations!()[0].currentTime, 600, '同じ動きを返す');
  el.classList.remove('is-new');
  assert.deepEqual(el.getAnimations!(), []);
  assert.equal(boot({ noAnimations: true }).root.getAnimations, undefined);
});
