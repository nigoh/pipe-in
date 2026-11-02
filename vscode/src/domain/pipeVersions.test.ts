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

// ---- D0065：外で書き換わる前の版（-external） ----

test('D0065-AC-08: 版の id に -external を付けられる。boolean の渡し方（true = 下書き）と種別の文字は同じ id になる', () => {
  assert.equal(versionId(T, 'external'), `${T}-external`);
  assert.equal(versionId(T, 'saved'), String(T));
  assert.equal(versionId(T, 'draft'), `${T}-draft`);
  assert.equal(versionId(T, false), String(T));
  assert.equal(versionId(T, true), `${T}-draft`);
  assert.equal(isVersionId(`${T}-external`), true);
  for (const bad of [`${T}-external-draft`, `${T}-draft-external`, `${T}-ext`, `${T}-externals`, `${T}-external.json`]) assert.equal(isVersionId(bad), false, bad);
});

test('D0065-AC-08: versionFromFile は -external を種別として読む（今の無印・-draft はそのまま。external の印は外の版だけ）', () => {
  assert.deepEqual(versionFromFile(`${T}-external.json`), { id: `${T}-external`, savedAt: T, draft: false, external: true });
  assert.deepEqual(versionFromFile(`${T}.json`), { id: String(T), savedAt: T, draft: false });
  assert.deepEqual(versionFromFile(`${T}-draft.json`), { id: `${T}-draft`, savedAt: T, draft: true });
  assert.equal(versionFromFile(`${T}-external-draft.json`), null);
  assert.equal(versionFromFile(`${T}-external.txt`), null);
  assert.equal(versionFromFile(`${T}-other.json`), null);
});

test('D0065-AC-08: 並びは新しい順。同じ時刻は 下書き → 外 → 保存 の順', () => {
  const plain: VersionEntry = { id: String(T), savedAt: T, draft: false };
  const draft: VersionEntry = { id: `${T}-draft`, savedAt: T, draft: true };
  const ext: VersionEntry = { id: `${T}-external`, savedAt: T, draft: false, external: true };
  const newer: VersionEntry = { id: String(T + 1), savedAt: T + 1, draft: false };
  assert.deepEqual(sortVersions([plain, ext, draft, newer]).map((v) => v.id), [newer.id, draft.id, ext.id, plain.id]);
  assert.deepEqual(sortVersions([draft, plain, ext, newer]).map((v) => v.id), [newer.id, draft.id, ext.id, plain.id]);
  assert.deepEqual(sortVersions([ext, draft, plain]).map((v) => v.id), [draft.id, ext.id, plain.id]);
});

test('D0065-AC-08: 残す数は今まで通り 50。外の版も同じ 50 に数え、古いほうから落とす', () => {
  const list: VersionEntry[] = Array.from({ length: 53 }, (_, i) =>
    i % 3 === 0 ? { id: `${T + i}-external`, savedAt: T + i, draft: false, external: true } : { id: String(T + i), savedAt: T + i, draft: false });
  assert.deepEqual(versionsToDrop(list), [`${T + 2}`, `${T + 1}`, `${T}-external`]);
  assert.deepEqual(versionsToDrop(list.slice(0, 50)), []);
});

test('D0065-AC-10: 前の規則（/^(\\d{13})(-draft)?$/ の写し）は -external を読み飛ばす。無印と -draft は今まで通り読む', () => {
  const previous = /^(\d{13})(-draft)?$/;
  const fromFile = (file: string): boolean => file.endsWith('.json') && previous.test(file.slice(0, -'.json'.length));
  assert.equal(fromFile(`${T}-external.json`), false, '前の拡張は形の違うファイルとして読み飛ばす');
  assert.equal(fromFile(`${T}.json`), true);
  assert.equal(fromFile(`${T}-draft.json`), true);
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
