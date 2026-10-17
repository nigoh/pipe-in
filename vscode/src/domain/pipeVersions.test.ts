// 保存した版：id（保存した時刻の ms と、閉じたときの下書きの印）・ファイル名との行き来・残す数。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { VERSION_LIMIT, isVersionId, sortVersions, versionFromFile, versionId, versionsToDrop } from './pipeVersions.ts';
import type { VersionEntry } from './pipeVersions.ts';

const T = 1760000000000;

test('AC-69: 版の id は保存した時刻（ms）で、下書きには -draft がつく', () => {
  assert.equal(versionId(T, false), String(T));
  assert.equal(versionId(T, true), `${T}-draft`);
  assert.equal(isVersionId(String(T)), true);
  assert.equal(isVersionId(`${T}-draft`), true);
  for (const bad of ['', '../x', `${T}.json`, `${T}-other`, '123', `${T}/..`]) assert.equal(isVersionId(bad), false, bad);
});

test('AC-69: ファイル名から版を読む（形の違うファイルは無視する）', () => {
  assert.deepEqual(versionFromFile(`${T}.json`), { id: String(T), savedAt: T, draft: false });
  assert.deepEqual(versionFromFile(`${T}-draft.json`), { id: `${T}-draft`, savedAt: T, draft: true });
  assert.equal(versionFromFile('index.json'), null);
  assert.equal(versionFromFile(`${T}.txt`), null);
});

test('AC-69: 一覧は新しい順で、残すのは新しい方から 50 版まで', () => {
  assert.equal(VERSION_LIMIT, 50);
  const list: VersionEntry[] = Array.from({ length: 53 }, (_, i) => ({ id: String(T + i), savedAt: T + i, draft: false }));
  const sorted = sortVersions(list);
  assert.equal(sorted[0]!.savedAt, T + 52);
  assert.deepEqual(versionsToDrop(list), [String(T + 2), String(T + 1), String(T)]);
  assert.deepEqual(versionsToDrop(list.slice(0, 50)), []);
  assert.deepEqual(versionsToDrop(list, 52), [String(T)]);
});
