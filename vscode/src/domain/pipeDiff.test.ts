// 2 つのパイプの形の差分の一覧（D0065）：段の増減・指示文・つなぎ・設定・位置が、それぞれ別の項目になる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DIFF_KIND_LABEL, diffPipes } from './pipeDiff.ts';
import type { DiffKind } from './pipeDiff.ts';
import { newStage } from './pipeModel.ts';
import { baseModel, renameIds } from '../test/externalFixtures.ts';

const KINDS: DiffKind[] = ['pipe', 'stage-added', 'stage-removed', 'prompt', 'flow', 'setting', 'layout'];

test('D0065-AC-05: 同じ形どうしでは []', () => {
  assert.deepEqual(diffPipes(baseModel(), baseModel()), []);
});

test('D0065-AC-05: 種別の画面用の名前が全部ある', () => {
  assert.deepEqual(Object.keys(DIFF_KIND_LABEL).sort(), [...KINDS].sort());
  for (const k of KINDS) assert.ok(DIFF_KIND_LABEL[k].length > 0, k);
});

test('D0065-AC-05: id が違っても、つなぎの行き先（段の name）が同じなら差にしない', () => {
  const a = baseModel();
  assert.deepEqual(diffPipes(a, renameIds(a, 'x')), []);
});

test('D0065-AC-05: 段が増えた → stage-added（target は段の name）', () => {
  const a = baseModel();
  const b = baseModel();
  const s = newStage('s3', 'research', 'extra');
  s.prompt = '追加の指示';
  b.stages.push(s);
  const items = diffPipes(a, b);
  const added = items.filter((i) => i.kind === 'stage-added');
  assert.equal(added.length, 1);
  assert.equal(added[0]!.target, 'extra');
  assert.equal(items.filter((i) => i.kind === 'stage-removed').length, 0);
});

test('D0065-AC-05: 段が減った → stage-removed（target は段の name）', () => {
  const a = baseModel();
  const b = baseModel();
  b.stages = b.stages.filter((s) => s.name !== 'write');
  b.stages[0]!.next = 'end';
  const removed = diffPipes(a, b).filter((i) => i.kind === 'stage-removed');
  assert.equal(removed.length, 1);
  assert.equal(removed[0]!.target, 'write');
});

test('D0065-AC-05: 指示文が違う段は prompt の 1 項目。text は新しい指示文の先頭の 1 行（40 字まで）の抜粋', () => {
  const a = baseModel();
  const b = baseModel();
  b.stages[0]!.prompt = `${'あ'.repeat(40)}ここは切られる\n二行目は出さない`;
  const items = diffPipes(a, b);
  assert.equal(items.length, 1, JSON.stringify(items));
  const item = items[0]!;
  assert.equal(item.kind, 'prompt');
  assert.equal(item.target, 'survey');
  assert.ok(item.text.includes('あ'.repeat(40)), item.text);
  assert.ok(!item.text.includes('ここは切られる'), item.text);
  assert.ok(!item.text.includes('二行目'), item.text);
});

test('D0065-AC-05: つなぎ（next）が違うと flow（行き先は id でなく段の name で比べる）', () => {
  const a = baseModel();
  const b = baseModel();
  b.stages[0]!.next = 'end'; // survey → write だったのを survey → 終わり に
  const items = diffPipes(a, b);
  assert.equal(items.length, 1, JSON.stringify(items));
  assert.equal(items[0]!.kind, 'flow');
  assert.equal(items[0]!.target, 'survey');
});

test('D0065-AC-05: 分岐（routes）の行き先が違うと flow', () => {
  const a = baseModel();
  const b = baseModel();
  a.stages[0]!.routes = [{ key: 'ok', to: a.stages[1]!.id }];
  b.stages[0]!.routes = [{ key: 'ok', to: 'end' }];
  const flows = diffPipes(a, b).filter((i) => i.kind === 'flow');
  assert.equal(flows.length, 1);
  assert.equal(flows[0]!.target, 'survey');
});

test('D0065-AC-05: 差し戻し先（onFail）が違うと flow', () => {
  const a = baseModel();
  const b = baseModel();
  b.stages[1]!.onFail = b.stages[0]!.id;
  const flows = diffPipes(a, b).filter((i) => i.kind === 'flow');
  assert.equal(flows.length, 1);
  assert.equal(flows[0]!.target, 'write');
});

test('D0065-AC-05: 段の設定（model など）が違うと setting（kind は setting、target は段の name）', () => {
  const a = baseModel();
  const b = baseModel();
  b.stages[1]!.model = 'opus';
  b.stages[1]!.bash = true;
  const items = diffPipes(a, b);
  assert.equal(items.length, 1, JSON.stringify(items));
  assert.equal(items[0]!.kind, 'setting');
  assert.equal(items[0]!.target, 'write');
});

test("D0065-AC-05: パイプ自体の設定（label・description・input・maxSteps）の差は kind 'pipe'、target 'pipe'", () => {
  for (const change of [
    (m: ReturnType<typeof baseModel>) => { m.label = '別の表示名'; },
    (m: ReturnType<typeof baseModel>) => { m.description = '説明を足した'; },
    (m: ReturnType<typeof baseModel>) => { m.input = 'none'; },
    (m: ReturnType<typeof baseModel>) => { m.maxSteps = 9; },
  ]) {
    const b = baseModel();
    change(b);
    const items = diffPipes(baseModel(), b);
    assert.equal(items.length, 1, JSON.stringify(items));
    assert.equal(items[0]!.kind, 'pipe');
    assert.equal(items[0]!.target, 'pipe');
  }
});

test('D0065-AC-05: 位置（段の x・y・始まり・終わり）が違うと layout。ほかの項目にはならない', () => {
  const a = baseModel();
  const b = baseModel();
  b.stages[0]!.x += 50;
  const one = diffPipes(a, b);
  assert.deepEqual(one.map((i) => i.kind), ['layout']);
  const c = baseModel();
  c.start = { x: c.start.x + 10, y: c.start.y };
  assert.deepEqual(diffPipes(a, c).map((i) => i.kind), ['layout']);
  const d = baseModel();
  d.end = { x: d.end.x, y: d.end.y + 10 };
  assert.deepEqual(diffPipes(a, d).map((i) => i.kind), ['layout']);
});

test('D0065-AC-05: 枠（frame）の位置・大きさが違うと layout', () => {
  const a = baseModel();
  a.frames = [{ id: 'f:g', name: 'g', x: 0, y: 0, w: 300, h: 200, next: 'end' }];
  const b = JSON.parse(JSON.stringify(a)) as typeof a;
  b.frames[0]!.w = 400;
  const items = diffPipes(a, b);
  assert.deepEqual(items.map((i) => i.kind), ['layout']);
  assert.equal(items[0]!.target, 'g');
});

test('D0065-AC-05: 全部違えば、種別ごとに別の項目になる（混ざらない）', () => {
  const a = baseModel();
  const b = baseModel();
  b.label = '別';
  b.stages[0]!.prompt = '新しい指示';
  b.stages[0]!.next = 'end';
  b.stages[1]!.model = 'opus';
  b.stages[1]!.x += 30;
  b.stages.push(newStage('s3', 'research', 'extra'));
  const kinds = new Set(diffPipes(a, b).map((i) => i.kind));
  for (const k of ['pipe', 'prompt', 'flow', 'setting', 'layout', 'stage-added'] as const) assert.ok(kinds.has(k), `${k} がある`);
  assert.ok(!kinds.has('stage-removed'));
});
