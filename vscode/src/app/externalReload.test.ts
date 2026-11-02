// 外の変更の手順（D0065）：読み直す・版に残す・選んだ結果の反映。vscode もファイルも使わない偽物の口でテストする。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EXTERNAL_DEBOUNCE_MS, PIPE_WATCH_GLOB, createExternalReload, recordBeforeTaking } from './externalReload.ts';
import type { ExternalDeps } from './externalReload.ts';
import type { VersionStore } from './pipeVersions.ts';
import type { ExternalNotice } from '../domain/pipeExternal.ts';
import { isWatchedRel } from '../domain/pipeExternal.ts';
import { PipeLoadError } from '../domain/pipeModel.ts';
import type { PipeModel } from '../domain/pipeModel.ts';
import { baseModel, reread } from '../test/externalFixtures.ts';

const T = 1760000000000;

/** 版の置き場所の偽物。書いた順を events に積む。failWrite なら書き込みが失敗する */
function memStore(events: string[], opts: { failWrite?: boolean } = {}) {
  const files: Record<string, string> = {};
  const writes: string[] = [];
  const removes: string[] = [];
  const store: VersionStore = {
    async list(pipe) { return Object.keys(files).filter((k) => k.startsWith(`${pipe}/`)).map((k) => k.slice(pipe.length + 1)); },
    async read(pipe, file) { return files[`${pipe}/${file}`] ?? null; },
    async write(pipe, file, text) {
      writes.push(file);
      if (opts.failWrite) throw new Error('disk full');
      files[`${pipe}/${file}`] = text;
      events.push(`write:${file}`);
    },
    async remove(pipe, file) { removes.push(file); delete files[`${pipe}/${file}`]; },
  };
  return { store, files, writes, removes };
}

interface Options {
  saved?: PipeModel;
  unsaved?: PipeModel | null;
  /** ディスクの今の形（呼ぶたびに読み直した新しいオブジェクトを返す。Error なら読めない） */
  disk?: () => PipeModel | Error;
  noVersions?: boolean;
  failWrite?: boolean;
  load?: ExternalDeps['load'];
}

function harness(o: Options = {}) {
  const events: string[] = [];
  const st = { saved: o.saved ?? baseModel(), unsaved: o.unsaved ?? null, disk: o.disk ?? ((): PipeModel | Error => baseModel()) };
  const mem = memStore(events, { failWrite: o.failWrite });
  const posts: ExternalNotice[] = [];
  const setSavedCalls: PipeModel[] = [];
  let clears = 0;
  const reload = createExternalReload({
    load: o.load ?? (async () => { const d = st.disk(); if (d instanceof Error) throw d; return d; }),
    versions: o.noVersions ? null : mem.store,
    now: () => T,
    saved: () => st.saved,
    unsaved: () => st.unsaved,
    setSaved: (m) => { events.push('setSaved'); setSavedCalls.push(m); st.saved = m; },
    clearUnsaved: () => { events.push('clearUnsaved'); clears++; st.unsaved = null; },
    post: (n) => { events.push(`post:${n.type}`); posts.push(n); },
  });
  return { reload, st, events, posts, setSavedCalls, mem, clears: () => clears };
}

/** 外で label を書き換えた形（書き出して読み直したもの） */
function diskWith(label: string): () => PipeModel {
  return () => { const m = baseModel(); m.label = label; return reread(m); };
}
function unsavedWith(label: string): PipeModel {
  const m = baseModel();
  m.label = label;
  return m;
}
const types = (posts: ExternalNotice[]): string[] => posts.map((p) => p.type);

// ---- 見張りの決まり（AC-01・AC-07 の定数） ----

/** {a,b,prompts/*.md} の形の glob を、相対パスに合うか調べる関数にする（テスト用の小さな実装。{} は 1 段だけ） */
function globMatcher(glob: string): (rel: string) => boolean {
  const inner = /^\{(.*)\}$/.exec(glob)?.[1];
  assert.ok(inner !== undefined, `glob は {…} の形：${glob}`);
  const res = inner.split(',').map((p) => new RegExp(`^${p.replace(/[.+^$()|[\]\\]/g, '\\$&').replace(/\*/g, '[^/]*')}$`));
  return (rel) => res.some((re) => re.test(rel));
}

test('D0065-AC-01: 見張りの glob は、見るべきファイル（isWatchedRel）と同じ 3 つを指す', () => {
  assert.equal(PIPE_WATCH_GLOB, '{pipe.toml,layout.json,prompts/*.md}');
  const hit = globMatcher(PIPE_WATCH_GLOB);
  for (const rel of ['pipe.toml', 'layout.json', 'prompts/01_a.md', 'README.md', 'prompts/sub/x.md', 'prompts/x.txt', 'other.md', '../pipe.toml']) {
    assert.equal(hit(rel), isWatchedRel(rel), rel);
  }
});

test('D0065-AC-07: デバウンスの待ちは 300ms', () => {
  assert.equal(EXTERNAL_DEBOUNCE_MS, 300);
});

// ---- 判断のとおりに動く（none / reload / choose） ----

test('D0065-AC-02: ディスクが保存済みと同じ形なら、何も出さず・何も変えない（作業台自身の保存の知らせ）', async () => {
  const h = harness({ unsaved: unsavedWith('編集中') });
  await h.reload.onDiskChanged();
  assert.deepEqual(h.posts, []);
  assert.equal(h.setSavedCalls.length, 0);
  assert.equal(h.mem.writes.length, 0);
});

test('D0065-AC-03: 違っていて保存していない変更が無い → 版を残して読み直し、externalReloaded（auto）を出す', async () => {
  const disk = diskWith('外で書き換えた');
  const h = harness({ disk });
  await h.reload.onDiskChanged();
  assert.equal(h.setSavedCalls.length, 1);
  assert.equal(h.setSavedCalls[0]!.label, '外で書き換えた');
  assert.equal(h.posts.length, 1);
  const n = h.posts[0]!;
  assert.ok(n.type === 'externalReloaded');
  assert.equal(n.cause, 'auto');
  assert.equal(n.model.label, '外で書き換えた');
  assert.deepEqual(n.savedNames, ['survey', 'write']);
});

test('D0065-AC-04: 違っていて保存していない変更がある → externalConflict だけ。読み直さず・版も残さず・画面の形に触れない', async () => {
  const h = harness({ disk: diskWith('外で書き換えた'), unsaved: unsavedWith('編集中') });
  await h.reload.onDiskChanged();
  assert.deepEqual(types(h.posts), ['externalConflict']);
  const n = h.posts[0]!;
  assert.ok(n.type === 'externalConflict');
  assert.ok(n.diff.some((d) => d.kind === 'pipe'), '差分に label の違いが出る');
  assert.equal(h.setSavedCalls.length, 0);
  assert.equal(h.clears(), 0);
  assert.equal(h.mem.writes.length, 0);
});

test('D0065-AC-04: 帯を出したあと、ディスクが保存済みの形に戻れば externalResolved（帯を消す）。出していなければ何も出さない', async () => {
  const h = harness({ disk: diskWith('外で書き換えた'), unsaved: unsavedWith('編集中') });
  await h.reload.onDiskChanged();
  h.st.disk = () => baseModel();
  await h.reload.onDiskChanged();
  assert.deepEqual(types(h.posts), ['externalConflict', 'externalResolved']);
});

// ---- AC-06 自分の変更を残す ----

test('D0065-AC-06: 「自分の変更を残す」のあと、同じ外の形では何も出さない。さらに別の形になれば externalConflict に戻る', async () => {
  const h = harness({ disk: diskWith('外 その1'), unsaved: unsavedWith('編集中') });
  await h.reload.onDiskChanged();
  await h.reload.choose('keep');
  assert.deepEqual(types(h.posts), ['externalConflict', 'externalKept']);
  const kept = h.posts[1]!;
  assert.ok(kept.type === 'externalKept');
  assert.deepEqual(kept.savedNames, ['survey', 'write']);
  assert.equal(h.st.saved.label, '外 その1', '外の形が保存済みの形になる');
  // 同じ外の形で、もう一度知らせが来ても
  await h.reload.onDiskChanged();
  await h.reload.onDiskChanged();
  assert.equal(h.posts.length, 2, '何も増えない');
  // さらに別の形に変わった
  h.st.disk = diskWith('外 その2');
  await h.reload.onDiskChanged();
  assert.deepEqual(types(h.posts), ['externalConflict', 'externalKept', 'externalConflict']);
});

test('D0065-AC-06: 待たせている外の形が無いときの choose は何もしない（load も keep も）', async () => {
  const h = harness({ unsaved: unsavedWith('編集中') });
  await h.reload.choose('keep');
  await h.reload.choose('load');
  assert.deepEqual(h.posts, []);
  assert.equal(h.setSavedCalls.length, 0);
  assert.equal(h.mem.writes.length, 0);
});

// ---- AC-12 取り込む前に版に残す ----

test('D0065-AC-12: 「外の変更を読み込む」は、保存済みの形を -external に、保存していない今の形を -draft に残してから取り込む', async () => {
  const h = harness({ disk: diskWith('外で書き換えた'), unsaved: unsavedWith('自分の変更') });
  await h.reload.onDiskChanged();
  await h.reload.choose('load');
  const ext = h.mem.files[`pipe-in-one/${T}-external.json`];
  const draft = h.mem.files[`pipe-in-one/${T}-draft.json`];
  assert.ok(ext, '-external の版がある');
  assert.ok(draft, '-draft の版がある');
  assert.equal((JSON.parse(ext) as PipeModel).label, '見本', '-external は変わる前の保存済みの形');
  assert.equal((JSON.parse(draft) as PipeModel).label, '自分の変更', '-draft は保存していなかった今の形');
  assert.equal(h.st.saved.label, '外で書き換えた');
  assert.equal(h.st.unsaved, null, '保存していない変更は取り込みで消える');
  const last = h.posts.at(-1)!;
  assert.ok(last.type === 'externalReloaded');
  assert.equal(last.cause, 'chosen');
  assert.equal(last.model.label, '外で書き換えた');
  assert.ok(last.versions?.some((v) => v.external === true), '一覧に外の版が出る');
  assert.ok(last.versions?.some((v) => v.draft === true));
});

test('D0065-AC-12: 版を残す→保存済みを差し替える→保存していない変更を消す→知らせる、の順', async () => {
  const h = harness({ disk: diskWith('外で書き換えた'), unsaved: unsavedWith('自分の変更') });
  await h.reload.onDiskChanged();
  h.events.length = 0;
  await h.reload.choose('load');
  const at = (e: string): number => h.events.indexOf(e);
  assert.ok(at(`write:${T}-external.json`) >= 0 && at(`write:${T}-draft.json`) >= 0, h.events.join(','));
  assert.ok(Math.max(at(`write:${T}-external.json`), at(`write:${T}-draft.json`)) < at('setSaved'), '残してから取り込む');
  assert.ok(at('setSaved') < at('clearUnsaved'));
  assert.ok(at('clearUnsaved') < at('post:externalReloaded'));
});

test('D0065-AC-12: 自動の読み直し（保存していない変更なし）は -external だけを残す。-draft は残さない', async () => {
  const h = harness({ disk: diskWith('外で書き換えた') });
  await h.reload.onDiskChanged();
  assert.deepEqual(h.mem.writes, [`${T}-external.json`]);
  assert.equal((JSON.parse(h.mem.files[`pipe-in-one/${T}-external.json`]!) as PipeModel).label, '見本');
  const n = h.posts[0]!;
  assert.ok(n.type === 'externalReloaded');
  assert.deepEqual(n.versions?.map((v) => v.id), [`${T}-external`]);
});

test('D0065-AC-12: 版の書き込みが失敗しても、取り込みは進む（setSaved・externalReloaded まで。versions は null）', async () => {
  for (const kind of ['auto', 'chosen'] as const) {
    const h = harness({ disk: diskWith('外で書き換えた'), unsaved: kind === 'chosen' ? unsavedWith('自分の変更') : null, failWrite: true });
    await h.reload.onDiskChanged();
    if (kind === 'chosen') await h.reload.choose('load');
    assert.equal(h.st.saved.label, '外で書き換えた', kind);
    const last = h.posts.at(-1)!;
    assert.ok(last.type === 'externalReloaded', kind);
    assert.equal(last.cause, kind);
    assert.equal(last.versions, null, kind);
  }
});

test('D0065-AC-12: 版の置き場所が無く（versions が null）ても、取り込みは進む', async () => {
  const h = harness({ disk: diskWith('外で書き換えた'), noVersions: true });
  await h.reload.onDiskChanged();
  assert.equal(h.st.saved.label, '外で書き換えた');
  const n = h.posts[0]!;
  assert.ok(n.type === 'externalReloaded');
  assert.equal(n.versions, null);
});

test('D0065-AC-12: recordBeforeTaking は、saved を -external、unsaved を -draft で残し、最後の一覧を返す', async () => {
  const events: string[] = [];
  const mem = memStore(events);
  const list = await recordBeforeTaking(mem.store, baseModel(), unsavedWith('編集中'), T);
  assert.deepEqual(list?.map((v) => v.id).sort(), [`${T}-draft`, `${T}-external`].sort());
  assert.deepEqual(mem.writes.sort(), [`${T}-draft.json`, `${T}-external.json`]);
  const only = memStore([]);
  const list2 = await recordBeforeTaking(only.store, baseModel(), null, T);
  assert.deepEqual(list2?.map((v) => v.id), [`${T}-external`]);
});

test('D0065-AC-12: recordBeforeTaking は、置き場所が無い・全部失敗したときは例外にせず null', async () => {
  assert.equal(await recordBeforeTaking(null, baseModel(), unsavedWith('編集中'), T), null);
  const failing = memStore([], { failWrite: true });
  assert.equal(await recordBeforeTaking(failing.store, baseModel(), unsavedWith('編集中'), T), null);
});

// ---- AC-13 自分の変更を残す：書かない ----

test('D0065-AC-13: 「自分の変更を残す」は、版に書かず・消さず、setSaved だけ（保存していない変更も消さない）', async () => {
  const h = harness({ disk: diskWith('外で書き換えた'), unsaved: unsavedWith('自分の変更') });
  await h.reload.onDiskChanged();
  await h.reload.choose('keep');
  assert.equal(h.mem.writes.length, 0, 'VersionStore.write が 0 回');
  assert.equal(h.mem.removes.length, 0, 'VersionStore.remove が 0 回');
  assert.equal(h.setSavedCalls.length, 1);
  assert.equal(h.clears(), 0, '自分の変更は残る');
  assert.equal(h.st.unsaved?.label, '自分の変更');
});

// ---- AC-14 読めない ----

test('D0065-AC-14: フォルダが無い・pipe.toml が壊れている → externalUnreadable を 1 回だけ。saved・版・待たせている外の形は変えない', async () => {
  for (const err of [new PipeLoadError('pipe-in-one/pipe.toml が見つかりません'), new PipeLoadError('pipe.toml を読めません：壊れている'), new Error('ENOENT')]) {
    const h = harness({ disk: () => err, unsaved: unsavedWith('編集中') });
    await h.reload.onDiskChanged();
    assert.equal(h.posts.length, 1, err.message);
    const n = h.posts[0]!;
    assert.ok(n.type === 'externalUnreadable');
    assert.ok(n.reason.length > 0);
    if (err instanceof PipeLoadError) assert.ok(n.reason.includes(err.message), n.reason);
    else assert.ok(n.reason.startsWith('読めませんでした（'), n.reason);
    assert.equal(h.setSavedCalls.length, 0);
    assert.equal(h.clears(), 0);
    assert.equal(h.mem.writes.length, 0);
    assert.equal(h.st.saved.label, '見本');
  }
});

test('D0065-AC-14: 選ばせている途中で読めなくなっても、待たせている外の形は変わらない（あとで「読み込む」を選べる）', async () => {
  const h = harness({ disk: diskWith('外で書き換えた'), unsaved: unsavedWith('編集中') });
  await h.reload.onDiskChanged();
  h.st.disk = () => new PipeLoadError('pipe.toml を読めません：壊れている');
  await h.reload.onDiskChanged();
  assert.deepEqual(types(h.posts), ['externalConflict', 'externalUnreadable']);
  await h.reload.choose('load');
  assert.equal(h.st.saved.label, '外で書き換えた', '最初に待たせた外の形が取り込まれる');
});

// ---- 競り合い（世代） ----

test('D0065-AC-02: 読んでいる途中で保存が済んだら（onSaved）、そのとき読んだ形は捨てる。何も出さず・何も変えない', async () => {
  let release: (m: PipeModel) => void = () => {};
  const pending = new Promise<PipeModel>((res) => { release = res; });
  const h = harness({ load: () => pending });
  const running = h.reload.onDiskChanged();
  h.reload.onSaved();
  release(diskWith('保存の途中で読んだ半端な形')());
  await running;
  assert.deepEqual(h.posts, []);
  assert.equal(h.setSavedCalls.length, 0);
  assert.equal(h.mem.writes.length, 0);
});

test('D0065-AC-06: 保存が済んだら（onSaved）、待たせていた外の形は捨てる（そのあとの choose は何もしない）', async () => {
  const h = harness({ disk: diskWith('外で書き換えた'), unsaved: unsavedWith('編集中') });
  await h.reload.onDiskChanged();
  h.reload.onSaved();
  await h.reload.choose('keep');
  await h.reload.choose('load');
  assert.equal(h.setSavedCalls.length, 0);
  assert.equal(h.mem.writes.length, 0);
  assert.deepEqual(types(h.posts), ['externalConflict']);
});

test('D0065-AC-02: dispose のあとに読み終わった結果は捨てる', async () => {
  let release: (m: PipeModel) => void = () => {};
  const pending = new Promise<PipeModel>((res) => { release = res; });
  const h = harness({ load: () => pending });
  const running = h.reload.onDiskChanged();
  h.reload.dispose();
  release(diskWith('閉じたあとに読み終えた形')());
  await running;
  assert.deepEqual(h.posts, []);
  assert.equal(h.setSavedCalls.length, 0);
});
