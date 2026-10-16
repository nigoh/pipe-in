// コンセントとプラグの形：差さったプラグは刃がコンセントの中に入り、本体がコンセントの面に付く。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SOCKET_BOX, plugParts, plugSvg, socketSvg } from './plugSvg.ts';

const inside = (r: { x: number; y: number; w: number; h: number }, box: typeof r): boolean =>
  r.x >= box.x && r.x + r.w <= box.x + box.w && r.y >= box.y && r.y + r.h <= box.y + box.h;

test('AC-56: 差さったプラグは、刃がすべてコンセントの中にあり、本体がコンセントの面に付く', () => {
  const p = plugParts('in');
  assert.ok(p.prongs.length >= 2);
  for (const r of p.prongs) assert.ok(inside(r, SOCKET_BOX), `刃 ${JSON.stringify(r)} がコンセントの外に出ている`);
  assert.equal(p.body.x + p.body.w, SOCKET_BOX.x); // 隙間なく付く
});

test('AC-56: 抜けたプラグは、刃が本体の先に見え、先端が掴んでいる点に来る', () => {
  const p = plugParts('loose');
  assert.ok(p.prongs.length >= 2);
  for (const r of p.prongs) {
    assert.ok(r.x >= p.body.x + p.body.w - 0.5, '刃は本体の先にある');
    assert.ok(Math.abs(r.x + r.w) <= 1, '刃の先端が掴んでいる点に来る');
  }
});

test('AC-56: 埋まったコンセントと空きのコンセントは描き分ける', () => {
  const full = socketSvg(10, 20, 0, true), empty = socketSvg(10, 20, 0, false);
  assert.match(empty, /socket empty/);
  assert.doesNotMatch(full, /empty/);
  assert.match(full, /socket plugged/);
  assert.match(empty, /class="slot"/);
});

test('AC-56: プラグは掴む印と、差した瞬間の動きを付けられる。style 属性は使わない（CSP）', () => {
  const s = plugSvg(10, 20, 90, 'next', 'in', { grab: 3, snap: true });
  assert.match(s, /data-plug="3"/);
  assert.match(s, /class="[^"]*snap/);
  assert.match(s, /translate\(10 20\) rotate\(90\)/);
  assert.doesNotMatch(s + socketSvg(0, 0, 0, true), /\sstyle=/);
  assert.doesNotMatch(plugSvg(0, 0, 0, 'temp', 'loose'), /data-plug/);
});
