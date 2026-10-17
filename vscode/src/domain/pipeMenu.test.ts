// 右クリックのメニュー：押したもの（ブロック・枠・何もないところ・複数選択）で項目を変え、使えない項目は理由をつけて薄くする。
// キー操作（↑↓・→←・Enter・Esc）と、面からはみ出さない置き場所も、純粋な関数で決める。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BLOCK_KINDS, KIND_LABEL, newPipe, newStage } from './pipeModel.ts';
import type { BlockKind, PipeModel, StageModel } from './pipeModel.ts';
import { menuFor, menuKey, placeMenu } from './pipeMenu.ts';
import type { MenuContext, MenuItem } from './pipeMenu.ts';

function stage(id: string, kind: BlockKind, x: number, y: number, over: Partial<StageModel> = {}): StageModel {
  return { ...newStage(id, kind, id), x, y, ...over };
}

/** a → b（仕分け：x は c）、c は並列の枠 F の外、f1 は枠 F の中。新しい段 n は保存していない */
function sample(): PipeModel {
  const m = newPipe('menu');
  m.stages = [
    stage('a', 'research', 100, 100, { next: 'b' }),
    stage('b', 'branch', 400, 80, { routes: [{ key: 'x', to: 'c' }] }),
    stage('c', 'research', 700, 100, { review: true }),
    stage('f1', 'docs', 1050, 40),
    stage('n', 'code', 100, 400),
  ];
  m.frames = [{ id: 'F', name: 'g', x: 1000, y: 0, w: 320, h: 340, next: null }];
  return m;
}
const ctx = (over: Partial<MenuContext> = {}): MenuContext => ({ hasClip: false, savedNames: ['a', 'b', 'c', 'f1'], ...over });
const ids = (items: MenuItem[]): string[] => items.map((i) => i.id);
const item = (items: MenuItem[], id: string): MenuItem => {
  const it = items.find((i) => i.id === id);
  assert.ok(it, `項目 ${id} があること`);
  return it!;
};

test('AC-58: ブロックのメニューは、決めた項目を決めた順に出す', () => {
  const items = menuFor(sample(), { type: 'stage', id: 'a' }, ctx());
  assert.deepEqual(ids(items), ['rename', 'open-prompt', 'show-prompt', '-', 'duplicate', 'review', 'frame-in', 'unplug-all', '-', 'delete']);
  assert.ok(items.filter((i) => i.id === '-').every((i) => i.sep === true));
  assert.equal(item(items, 'review').label, '人の確認をつける');
  // 枠に入れる ▸ は、枠ごとのサブメニュー
  assert.deepEqual(ids(item(items, 'frame-in').children ?? []), ['frame-in:F']);
  assert.match(item(items, 'frame-in').children![0]!.label, /g/);
  for (const i of items.filter((x) => !x.sep)) assert.ok(i.label.length > 0, `${i.id} に表示の文字がある`);
});

test('AC-58: 人の確認がついている段では「人の確認を外す」になる', () => {
  const items = menuFor(sample(), { type: 'stage', id: 'c' }, ctx());
  assert.equal(item(items, 'review').label, '人の確認を外す');
});

test('AC-58: 枠の中の段では「枠に入れる」の代わりに「枠から出す」を出す', () => {
  const items = menuFor(sample(), { type: 'stage', id: 'f1' }, ctx());
  assert.ok(ids(items).includes('frame-out'));
  assert.ok(!ids(items).includes('frame-in'));
  assert.equal(item(items, 'frame-out').disabled, undefined);
});

test('AC-58: 枠のメニュー', () => {
  assert.deepEqual(ids(menuFor(sample(), { type: 'frame', id: 'F' }, ctx())), ['rename-frame', '-', 'delete-frame', 'delete-frame-all']);
});

test('AC-58: 何もないところのメニュー（ここに段を足す ▸ は棚と同じ種類）', () => {
  const items = menuFor(sample(), { type: 'canvas', at: { x: 10, y: 20 } }, ctx({ hasClip: true }));
  assert.deepEqual(ids(items), ['add', 'add-frame', 'paste', '-', 'arrange', 'fit']);
  const add = item(items, 'add').children ?? [];
  assert.deepEqual(ids(add), BLOCK_KINDS.map((k) => `add:${k}`));
  assert.deepEqual(add.map((i) => i.label), BLOCK_KINDS.map((k) => KIND_LABEL[k]));
  assert.equal(item(items, 'paste').disabled, undefined);
});

test('AC-58: 複数選んでいるときのメニュー', () => {
  const items = menuFor(sample(), { type: 'multi', ids: ['a', 'n'] }, ctx());
  assert.deepEqual(ids(items), ['duplicate', 'frame-in', '-', 'delete']);
  assert.match(item(items, 'delete').label, /2/);
});

test('AC-58: ケーブルにはメニューを出さない', () => {
  assert.deepEqual(menuFor(sample(), { type: 'wire' }, ctx()), []);
});

test('AC-59: 保存していない段の「指示文を開く」は、理由をつけて使えなくする', () => {
  const items = menuFor(sample(), { type: 'stage', id: 'n' }, ctx());
  assert.match(item(items, 'open-prompt').disabled ?? '', /保存/);
  assert.equal(item(menuFor(sample(), { type: 'stage', id: 'a' }, ctx()), 'open-prompt').disabled, undefined);
});

test('AC-59: 枠の中の段は「人の確認」を持てない', () => {
  assert.match(item(menuFor(sample(), { type: 'stage', id: 'f1' }, ctx()), 'review').disabled ?? '', /枠/);
});

test('AC-59: 枠が無いとき・分岐を持つとき・人の確認があるときは「枠に入れる」を使えない', () => {
  const m = sample();
  m.frames = [];
  m.stages = m.stages.filter((s) => s.id !== 'f1');
  assert.match(item(menuFor(m, { type: 'stage', id: 'a' }, ctx()), 'frame-in').disabled ?? '', /枠/);
  assert.match(item(menuFor(sample(), { type: 'stage', id: 'b' }, ctx()), 'frame-in').disabled ?? '', /分岐/);
  assert.match(item(menuFor(sample(), { type: 'stage', id: 'c' }, ctx()), 'frame-in').disabled ?? '', /人の確認/);
  assert.match(item(menuFor(sample(), { type: 'multi', ids: ['a', 'b'] }, ctx()), 'frame-in').disabled ?? '', /分岐/);
});

test('AC-59: つなぎの無い段の「ケーブルをすべて抜く」と、写したものが無いときの「貼り付け」は使えない', () => {
  assert.match(item(menuFor(sample(), { type: 'stage', id: 'n' }, ctx()), 'unplug-all').disabled ?? '', /つな/);
  assert.equal(item(menuFor(sample(), { type: 'stage', id: 'a' }, ctx()), 'unplug-all').disabled, undefined);
  assert.match(item(menuFor(sample(), { type: 'canvas', at: { x: 0, y: 0 } }, ctx()), 'paste').disabled ?? '', /写/);
});

// ---- キー操作 ----

const MENU: MenuItem[] = [
  { id: 'one', label: '1' },
  { id: '-', label: '', sep: true },
  { id: 'two', label: '2', disabled: '使えない' },
  { id: 'sub', label: '3', children: [{ id: 'sub:a', label: 'a' }, { id: 'sub:b', label: 'b' }] },
];

test('AC-60: ↑↓ は区切りを飛ばして動き、端で一周する（使えない項目にも止まる）', () => {
  assert.deepEqual(menuKey(MENU, [0], 'ArrowDown').path, [2]);
  assert.deepEqual(menuKey(MENU, [2], 'ArrowDown').path, [3]);
  assert.deepEqual(menuKey(MENU, [3], 'ArrowDown').path, [0]);
  assert.deepEqual(menuKey(MENU, [0], 'ArrowUp').path, [3]);
  assert.deepEqual(menuKey(MENU, [2], 'ArrowUp').path, [0]);
});

test('AC-60: → でサブメニューに入り、← と Esc で戻る。外側の Esc で閉じる', () => {
  assert.deepEqual(menuKey(MENU, [3], 'ArrowRight').path, [3, 0]);
  assert.deepEqual(menuKey(MENU, [0], 'ArrowRight').path, [0]);
  assert.deepEqual(menuKey(MENU, [3, 0], 'ArrowDown').path, [3, 1]);
  assert.deepEqual(menuKey(MENU, [3, 1], 'ArrowDown').path, [3, 0]);
  assert.deepEqual(menuKey(MENU, [3, 1], 'ArrowLeft').path, [3]);
  const esc = menuKey(MENU, [3, 1], 'Escape');
  assert.deepEqual(esc.path, [3]);
  assert.notEqual(esc.close, true);
  assert.equal(menuKey(MENU, [0], 'Escape').close, true);
});

test('AC-60: Enter で実行する。サブメニューを持つ項目は開き、使えない項目は何もしない', () => {
  assert.equal(menuKey(MENU, [0], 'Enter').run, 'one');
  assert.equal(menuKey(MENU, [3, 1], 'Enter').run, 'sub:b');
  const open = menuKey(MENU, [3], 'Enter');
  assert.deepEqual(open.path, [3, 0]);
  assert.equal(open.run, undefined);
  const no = menuKey(MENU, [2], 'Enter');
  assert.equal(no.run, undefined);
  assert.deepEqual(no.path, [2]);
});

test('AC-75: メニューは面からはみ出さないよう、右端・下端では内側に折り返す', () => {
  const box = { w: 800, h: 600 }, size = { w: 200, h: 300 };
  assert.deepEqual(placeMenu({ x: 100, y: 100 }, size, box), { x: 100, y: 100 });
  assert.deepEqual(placeMenu({ x: 700, y: 100 }, size, box), { x: 500, y: 100 });
  assert.deepEqual(placeMenu({ x: 100, y: 500 }, size, box), { x: 100, y: 200 });
  // 面より大きいときも、左上は面の中に残す
  assert.deepEqual(placeMenu({ x: 50, y: 50 }, { w: 900, h: 700 }, box), { x: 0, y: 0 });
});
