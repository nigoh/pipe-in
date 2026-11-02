// 保存した版の記録・一覧・読み込み（置き場所は口 VersionStore の向こう）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { listVersions, readVersion, recordVersion } from './pipeVersions.ts';
import type { VersionStore } from './pipeVersions.ts';
import { newPipe } from '../domain/pipeModel.ts';

function memoryStore(files: Record<string, string> = {}): VersionStore & { files: Record<string, string> } {
  return {
    files,
    async list(pipe) { return Object.keys(files).filter((k) => k.startsWith(`${pipe}/`)).map((k) => k.slice(pipe.length + 1)); },
    async read(pipe, file) { return files[`${pipe}/${file}`] ?? null; },
    async write(pipe, file, text) { files[`${pipe}/${file}`] = text; },
    async remove(pipe, file) { delete files[`${pipe}/${file}`]; },
  };
}
const T = 1760000000000;

test('AC-69: 保存のたびに版を足し、新しい順の一覧を返す。下書きも同じ一覧に並ぶ', async () => {
  const store = memoryStore();
  const m = newPipe('one');
  await recordVersion(store, m, T);
  m.label = '変えた';
  const list = await recordVersion(store, m, T + 1000, true);
  assert.deepEqual(list.map((v) => v.id), [`${T + 1000}-draft`, String(T)]);
  assert.ok(store.files[`pipe-in-one/${T}.json`]);
  assert.deepEqual(await listVersions(store, 'one'), list);
  assert.deepEqual(await listVersions(store, 'two'), []);
});

// ---- D0065：外で書き換わる前の版（-external） ----

test("D0065-AC-09: recordVersion に 'external' を渡すと <id>-external.json が書かれ、一覧に出る（external の印つき）", async () => {
  const store = memoryStore();
  const m = newPipe('one');
  const list = await recordVersion(store, m, T, 'external');
  assert.ok(store.files[`pipe-in-one/${T}-external.json`]);
  assert.deepEqual(list, [{ id: `${T}-external`, savedAt: T, draft: false, external: true }]);
  assert.deepEqual(await listVersions(store, 'one'), list);
});

test('D0065-AC-09: 保存・下書きの版の動きは変わらない（種別の文字でも boolean でも同じ。external の印は付かない）', async () => {
  const store = memoryStore();
  const m = newPipe('one');
  await recordVersion(store, m, T, 'saved');
  await recordVersion(store, m, T + 1, 'draft');
  await recordVersion(store, m, T + 2, true);
  await recordVersion(store, m, T + 3, false);
  await recordVersion(store, m, T + 3, 'external');
  const list = await listVersions(store, 'one');
  assert.deepEqual(list.map((v) => v.id), [`${T + 3}-external`, String(T + 3), `${T + 2}-draft`, `${T + 1}-draft`, String(T)]);
  assert.deepEqual(list.filter((v) => v.external).map((v) => v.id), [`${T + 3}-external`]);
  assert.ok(store.files[`pipe-in-one/${T}.json`]);
  assert.ok(store.files[`pipe-in-one/${T + 1}-draft.json`]);
});

test('D0065-AC-09: 外の版も 50 の上限に数え、超えたら古いほうから消す', async () => {
  const store = memoryStore();
  const m = newPipe('one');
  for (let i = 0; i < 52; i++) await recordVersion(store, m, T + i, i % 2 === 0 ? 'external' : 'saved');
  const list = await listVersions(store, 'one');
  assert.equal(list.length, 50);
  assert.equal(list.at(-1)!.savedAt, T + 2);
  assert.equal(list.filter((v) => v.external === true).length, 25, '外の版として数えられている');
  assert.equal(store.files[`pipe-in-one/${T}-external.json`], undefined);
});

test('D0065-AC-10: -external の無い古い置き場所（無印と -draft だけ）を、今の listVersions がそのまま読む', async () => {
  const m = newPipe('one');
  const store = memoryStore({
    [`pipe-in-one/${T}.json`]: JSON.stringify(m),
    [`pipe-in-one/${T + 1}-draft.json`]: JSON.stringify(m),
    'pipe-in-one/memo.txt': 'x',
  });
  assert.deepEqual(await listVersions(store, 'one'), [
    { id: `${T + 1}-draft`, savedAt: T + 1, draft: true },
    { id: String(T), savedAt: T, draft: false },
  ]);
});

test('D0065-AC-11: readVersion は、一覧にある -external の版を読む（名前はこのパイプに直す）', async () => {
  const store = memoryStore();
  const m = newPipe('one');
  m.label = '外で書き換わる前';
  await recordVersion(store, m, T, 'external');
  assert.equal((await readVersion(store, 'one', `${T}-external`))?.label, '外で書き換わる前');
  store.files[`pipe-in-one/${T + 5}-external.json`] = JSON.stringify({ ...m, name: 'other' });
  assert.equal((await readVersion(store, 'one', `${T + 5}-external`))?.name, 'one');
});

test('D0065-AC-11: 一覧にない -external の id・形が壊れた中身・形の違う id は null', async () => {
  const store = memoryStore();
  const m = newPipe('one');
  await recordVersion(store, m, T, 'external');
  assert.equal(await readVersion(store, 'one', `${T + 1}-external`), null, '一覧に無い');
  store.files[`pipe-in-one/${T + 6}-external.json`] = '{"name": 1}';
  store.files[`pipe-in-one/${T + 7}-external.json`] = 'こわれた';
  assert.equal(await readVersion(store, 'one', `${T + 6}-external`), null);
  assert.equal(await readVersion(store, 'one', `${T + 7}-external`), null);
  assert.equal(await readVersion(store, 'one', `${T}-external-draft`), null);
  assert.equal(await readVersion(store, 'one', `../${T}-external`), null);
});

test('AC-69: 50 版を超えたら、古いほうから消す', async () => {
  const store = memoryStore();
  const m = newPipe('one');
  for (let i = 0; i < 52; i++) await recordVersion(store, m, T + i);
  const list = await listVersions(store, 'one');
  assert.equal(list.length, 50);
  assert.equal(store.files[`pipe-in-one/${T}.json`], undefined);
  assert.equal(list.at(-1)!.savedAt, T + 2);
});

test('AC-69: 読むのは一覧にある版だけ。中身は形を確かめ、名前はこのパイプに直す', async () => {
  const store = memoryStore();
  const m = newPipe('one');
  m.label = 'その時の形';
  await recordVersion(store, m, T);
  const got = await readVersion(store, 'one', String(T));
  assert.equal(got?.label, 'その時の形');
  assert.equal(await readVersion(store, 'one', String(T + 1)), null); // 一覧に無い
  assert.equal(await readVersion(store, 'one', '../../x'), null);
  // 名前を書き換えた版でも、このパイプの名前で返す
  store.files[`pipe-in-one/${T + 5}.json`] = JSON.stringify({ ...m, name: 'other' });
  assert.equal((await readVersion(store, 'one', String(T + 5)))?.name, 'one');
  // 形の違う中身は読まない
  store.files[`pipe-in-one/${T + 6}.json`] = '{"name": 1}';
  store.files[`pipe-in-one/${T + 7}.json`] = 'こわれた';
  assert.equal(await readVersion(store, 'one', String(T + 6)), null);
  assert.equal(await readVersion(store, 'one', String(T + 7)), null);
});
