// 作業台の編集：複製・コピー・貼り付け・まとめて消す・枠に入れる/出す・つなぎをすべて外す・囲んで選ぶ。純粋な関数だけ。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { END, blockSize, frameOf, membersOf, newPipe, newStage } from './pipeModel.ts';
import type { BlockKind, PipeModel, StageModel } from './pipeModel.ts';
import { copyItems, deleteItems, isLoose, itemsInRect, pasteClip, pasteOffset, putInFrame, takeOutOfFrame, unplugAll } from './pipeEdit.ts';

function stage(id: string, kind: BlockKind, x: number, y: number, over: Partial<StageModel> = {}): StageModel {
  return { ...newStage(id, kind, id), x, y, ...over };
}

/**
 * a → b → c → 並列の枠 F（f1・f2）→ d → 終わり。c は判定に通らなければ a へ戻す。b は分岐（x → c）。
 * n はどことも、つながっていない。
 */
function sample(): PipeModel {
  const m = newPipe('edit');
  m.stages = [
    stage('a', 'research', 100, 100, { next: 'b' }),
    stage('b', 'branch', 400, 80, { routes: [{ key: 'x', to: 'c' }] }),
    stage('c', 'research', 700, 100, { next: 'F', check: { on: true, verdict: true, command: '', maxRetries: 2 }, onFail: 'a' }),
    stage('f1', 'docs', 1050, 40),
    stage('f2', 'docs', 1050, 200),
    stage('d', 'research', 1500, 100, { next: END }),
    stage('n', 'code', 100, 500),
  ];
  m.frames = [{ id: 'F', name: 'g', x: 1000, y: 0, w: 320, h: 340, next: 'd' }];
  m.start = { x: -200, y: 110 };
  m.end = { x: 1800, y: 110 };
  return m;
}
const st = (m: PipeModel, id: string): StageModel => m.stages.find((s) => s.id === id)!;
let n = 0;
const fresh = (p: string): string => `${p}new${++n}`;

test('AC-66: 複製した段は id が新しく、name と成果物が重ならないよう番号をつけ、少しずらして置く', () => {
  const m = sample();
  const added = pasteClip(m, copyItems(m, ['a']), { x: 40, y: 40 }, fresh);
  assert.equal(added.length, 1);
  const s = st(m, added[0]!);
  assert.notEqual(s.id, 'a');
  assert.equal(s.name, 'a-2');
  assert.notEqual(s.output, st(m, 'a').output);
  assert.deepEqual([s.x, s.y], [140, 140]);
  // もう一度貼ると、さらに次の番号
  const again = pasteClip(m, copyItems(m, ['a']), { x: 40, y: 40 }, fresh);
  assert.equal(st(m, again[0]!).name, 'a-3');
  // 元の段はそのまま
  assert.equal(st(m, 'a').next, 'b');
});

test('AC-66: 選んだもの同士のつながりは貼った先どうしにつけ替え、外へのつながりは外す', () => {
  const m = sample();
  const added = pasteClip(m, copyItems(m, ['a', 'b', 'c']), { x: 0, y: 600 }, fresh);
  const [a2, b2, c2] = added.map((id) => st(m, id));
  assert.equal(a2!.next, b2!.id);
  assert.deepEqual(b2!.routes, [{ key: 'x', to: c2!.id }]);
  assert.equal(c2!.onFail, a2!.id);
  assert.equal(c2!.next, null); // 枠 F は写していない
  // 外へ出るつながりだけの段：終わりへのつながりも外へのつながりとして外す
  const d2 = st(m, pasteClip(m, copyItems(m, ['d']), { x: 0, y: 600 }, fresh)[0]!);
  assert.equal(d2.next, null);
});

test('AC-66: 写したあとに元を変えても、写しは変わらない', () => {
  const m = sample();
  const clip = copyItems(m, ['a']);
  st(m, 'a').prompt = 'あとから変えた';
  const s = st(m, pasteClip(m, clip, { x: 40, y: 40 }, fresh)[0]!);
  assert.equal(s.prompt, '');
});

test('AC-66: 枠を写すと中の段も一緒に写り、枠の名前も重ならないようにする', () => {
  const m = sample();
  const added = pasteClip(m, copyItems(m, ['F']), { x: 0, y: 500 }, fresh);
  const f2 = m.frames.find((f) => added.includes(f.id))!;
  assert.ok(f2);
  assert.equal(f2.name, 'g-2');
  assert.equal(f2.next, null);
  const kids = m.stages.filter((s) => frameOf(m, s) === f2).map((s) => s.name).sort();
  assert.deepEqual(kids, ['f1-2', 'f2-2']);
});

test('AC-67: まとめて消すと、消した段・枠へのつながりがすべて外れる', () => {
  const m = sample();
  const r = deleteItems(m, ['a', 'F']);
  assert.deepEqual(r, { stages: 1, frames: 1 });
  assert.equal(m.stages.some((s) => s.id === 'a'), false);
  assert.equal(st(m, 'c').onFail, null);
  assert.equal(st(m, 'c').next, null); // 枠 F へのつなぎ
  assert.ok(st(m, 'f1')); // 枠だけ消して、中の段は残す
  assert.equal(m.frames.length, 0);
});

test('AC-67: 枠を中の段ごと消せる（段の id も一緒に渡す）', () => {
  const m = sample();
  const r = deleteItems(m, ['F', 'f1', 'f2', 'b']);
  assert.deepEqual(r, { stages: 3, frames: 1 });
  assert.equal(st(m, 'a').next, null);
  assert.deepEqual(m.stages.map((s) => s.id), ['a', 'c', 'd', 'n']);
});

test('AC-65: 枠に入れると枠の段になり、入りきらなければ枠を広げる。next と差し戻しは外して知らせる', () => {
  const m = sample();
  const r = putInFrame(m, ['c'], 'F');
  assert.equal(r.changed, true);
  const F = m.frames[0]!, c = st(m, 'c');
  assert.equal(frameOf(m, c), F);
  const z = blockSize(c.kind);
  assert.ok(c.y + z.h <= F.y + F.h && c.x >= F.x && c.x + z.w <= F.x + F.w, '段がまるごと枠の中にある');
  assert.ok(F.h > 340, '枠を高くした');
  assert.equal(c.next, null);
  assert.equal(c.onFail, null);
  assert.match(r.message, /外し/);
  // 前からいた段は枠の中のまま
  assert.equal(frameOf(m, st(m, 'f1')), F);
  assert.equal(frameOf(m, st(m, 'f2')), F);
});

test('AC-65: 分岐や人の確認を持つ段は枠に入れず、理由を返して何も変えない', () => {
  const m = sample();
  const before = JSON.stringify(m);
  assert.equal(putInFrame(m, ['b'], 'F').changed, false);
  st(m, 'a').review = true;
  const r = putInFrame(m, ['a'], 'F');
  assert.equal(r.changed, false);
  assert.match(r.message, /人の確認/);
  st(m, 'a').review = false;
  assert.equal(JSON.stringify(m), before);
});

test('AC-65: 枠から出すと、どの枠にも入らない空いた場所に置く', () => {
  const m = sample();
  const r = takeOutOfFrame(m, 'f1');
  assert.equal(r.changed, true);
  assert.equal(frameOf(m, st(m, 'f1')), null);
  assert.equal(takeOutOfFrame(m, 'a').changed, false);
});

test('つなぎをすべて外す：出るつなぎも入るつなぎも外れる', () => {
  const m = sample();
  assert.equal(unplugAll(m, 'c'), true);
  assert.equal(st(m, 'c').next, null);
  assert.equal(st(m, 'c').onFail, null);
  assert.deepEqual(st(m, 'b').routes, []);
  assert.equal(unplugAll(m, 'n'), false);
  assert.ok(isLoose(m, 'c'));
});

test('つながっていない段を見分ける（出るつなぎも、入るつなぎも無い）', () => {
  const m = sample();
  assert.equal(isLoose(m, 'n'), true);
  assert.equal(isLoose(m, 'a'), false); // 出るつなぎ
  assert.equal(isLoose(m, 'd'), false); // 枠からのつなぎが入る
  assert.equal(isLoose(m, 'f1'), false); // 枠の中
});

test('AC-68: 囲んだ四角にまるごと入るブロックと枠を選ぶ', () => {
  const m = sample();
  assert.deepEqual(itemsInRect(m, { x: 50, y: 50, w: 700, h: 200 }), ['a', 'b']);
  assert.deepEqual(itemsInRect(m, { x: 990, y: -10, w: 400, h: 400 }), ['f1', 'f2', 'F']);
  assert.deepEqual(itemsInRect(m, { x: -100, y: 1000, w: 10, h: 10 }), []);
  // 逆向きに囲んでも（幅や高さが負でも）同じ
  assert.deepEqual(itemsInRect(m, { x: 750, y: 250, w: -700, h: -200 }), ['a', 'b']);
});

test('AC-66（画面で見つけた不具合）：枠を含めて貼るときは、元の枠と重ならない所までずらす（写しの段が元の枠に入らない）', () => {
  const m = sample();
  const clip = copyItems(m, ['F']);
  const added = pasteClip(m, clip, pasteOffset(clip, 1), fresh);
  const F = m.frames.find((f) => f.id === 'F')!, F2 = m.frames.find((f) => added.includes(f.id))!;
  assert.deepEqual(membersOf(m, F).map((s) => s.id), ['f1', 'f2']);
  assert.equal(membersOf(m, F2).length, 2);
  // 段だけを貼るときは、今までどおり少しずつずらす
  assert.deepEqual(pasteOffset(copyItems(m, ['a']), 2), { x: 80, y: 80 });
});

// ---- D0005: つなぎを外しても、判定は残す（判定を切るのはスイッチだけ） ----

test('D0005-AC-04: つなぎをすべて外しても、差し戻しを持っていた段の判定はオンのまま（この段をやり直す）', () => {
  const m = sample();
  assert.equal(unplugAll(m, 'c'), true);
  assert.equal(st(m, 'c').check.on, true);
  assert.equal(st(m, 'c').onFail, null);
});

test('D0005-AC-04: 外した段へ戻していた、ほかの段の判定もオンのまま（この段をやり直す）', () => {
  const m = sample();
  assert.equal(unplugAll(m, 'a'), true);
  assert.equal(st(m, 'c').onFail, null);
  assert.equal(st(m, 'c').check.on, true);
});
