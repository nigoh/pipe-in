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
