// 実行の候補（work_dir 直下の開発フローと、<work_dir>/<パイプ名>/ のパイプ）から、見る実行を選ぶ。AC-02・AC-11。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { stateJson } from '../test/fixtures.ts';

// 新しい部品はテストの中で読み込む（1件ずつ、何で落ちたかが見えるように）
const runs = () => import('./runs.ts');

const ROOT = { id: '', label: '開発フロー', updatedAt: '2026-10-16T10:00:00' };
const DIAGRAMS = { id: 'diagrams', label: 'diagrams', updatedAt: '2026-10-16T11:00:00' };

test('AC-02: 既定は updated_at の新しい実行', async () => {
  const { pickRun } = await runs();
  assert.equal(pickRun([ROOT, DIAGRAMS], null), 'diagrams');
  assert.equal(pickRun([{ ...ROOT, updatedAt: '2026-10-16T12:00:00' }, DIAGRAMS], null), '');
});

test('AC-02: updated_at がない・同じなら直下（開発フロー）、候補がなければ直下', async () => {
  const { pickRun } = await runs();
  assert.equal(pickRun([{ ...ROOT, updatedAt: null }, { ...DIAGRAMS, updatedAt: null }], null), '');
  assert.equal(pickRun([ROOT, { ...DIAGRAMS, updatedAt: ROOT.updatedAt }], null), '');
  assert.equal(pickRun([], null), '');
});

test('AC-02: 候補の名前は記録から作る（開発フローは「開発フロー」、パイプはパイプの名前）', async () => {
  const { describeRun } = await runs();
  assert.deepEqual(describeRun('', stateJson({ pipe: 'dev', updatedAt: '2026-10-16T09:00:00' })), {
    id: '',
    label: '開発フロー',
    updatedAt: '2026-10-16T09:00:00',
  });
  assert.deepEqual(describeRun('diagrams', stateJson({ pipe: 'diagrams', updatedAt: '2026-10-16T11:00:00' })), {
    id: 'diagrams',
    label: 'diagrams',
    updatedAt: '2026-10-16T11:00:00',
  });
  assert.deepEqual(describeRun('', null), { id: '', label: '開発フロー', updatedAt: null });
  assert.deepEqual(describeRun('x', '{壊れた'), { id: 'x', label: 'x', updatedAt: null });
});

test('AC-11: 選んだ候補があればそれを見て、候補にない id を選んでいたら既定に戻る', async () => {
  const { pickRun } = await runs();
  assert.equal(pickRun([{ ...ROOT, updatedAt: '2026-10-16T12:00:00' }, DIAGRAMS], 'diagrams'), 'diagrams');
  assert.equal(pickRun([ROOT, DIAGRAMS], ''), '');
  assert.equal(pickRun([ROOT, DIAGRAMS], 'gone'), 'diagrams');
});

test('AC-11: 選んだ候補のフォルダ。候補にない id（../x・logs・知らない名前）はフォルダにしない', async () => {
  const { resolveRunDir } = await runs();
  const w = path.resolve('/ws/docs/pipeline');
  const candidates = [ROOT, DIAGRAMS];
  assert.equal(resolveRunDir(w, '', candidates), w);
  assert.equal(resolveRunDir(w, 'diagrams', candidates), path.join(w, 'diagrams'));
  for (const id of ['../x', 'logs', 'spec-qa', '..', 'diagrams/../..']) {
    assert.equal(resolveRunDir(w, id, candidates), null, id);
  }
  // 候補に紛れ込んでいても、フォルダ名として正しくなければ通さない
  assert.equal(resolveRunDir(w, '../x', [...candidates, { id: '../x', label: 'x', updatedAt: null }]), null);
});

// ---- D0019：実行の目印（場所 + id）と archive ----

test('D0019-AC-01: archive はパイプのフォルダ名にならない（logs と同じ予約名）。ほかの名前は今までどおり', async () => {
  const { isRunFolderName } = await runs();
  assert.equal(isRunFolderName('archive'), false);
  assert.equal(isRunFolderName('logs'), false);
  for (const name of ['diagrams', 'spec-qa', 'archive2', 'my-archive']) assert.equal(isRunFolderName(name), true, name);
});

test('D0019-AC-01: archive の id は archive/<日時>（-2 のような重なりつき）だけ。日時は archiveStamp で取り出す', async () => {
  const { isArchiveId, archiveStamp, ARCHIVE_DIR } = await runs();
  assert.equal(ARCHIVE_DIR, 'archive');
  for (const [id, stamp] of [
    ['archive/20261017-100000', '20261017-100000'],
    ['archive/20261017-100000-2', '20261017-100000-2'],
    ['archive/20261017-100000-12', '20261017-100000-12'],
  ] as const) {
    assert.equal(isArchiveId(id), true, id);
    assert.equal(archiveStamp(id), stamp, id);
  }
  for (const id of ['', 'archive', 'archive/', 'archive/..', 'archive/2026', 'archive/20261017-100000/x', 'archive/../20261017-100000', 'diagrams', 'x/archive/20261017-100000', 'archive/20261017-100000-', 'archive\\20261017-100000']) {
    assert.equal(isArchiveId(id), false, id);
    assert.equal(archiveStamp(id), null, id);
  }
});

test('D0019-AC-01: 実行の目印は 場所|id。作って、分けると元に戻る', async () => {
  const { makeRunKey, parseRunKey, isRunKey, HERE } = await runs();
  assert.equal(HERE, 'here');
  const cases: [string, string, string][] = [
    ['here', '', 'here|'],
    ['here', 'diagrams', 'here|diagrams'],
    ['main', 'archive/20261017-100000-2', 'main|archive/20261017-100000-2'],
    ['wt.feat-x', 'spec-qa', 'wt.feat-x|spec-qa'],
    ['wt.A_b.c-1', '', 'wt.A_b.c-1|'],
  ];
  for (const [place, id, key] of cases) {
    assert.equal(makeRunKey(place, id), key);
    assert.deepEqual(parseRunKey(key), { place, id }, key);
    assert.equal(isRunKey(key), true, key);
  }
});

// すり抜けの道（パスに化ける文字・形の違い）を並べる。どれも目印として通さない
const BAD_KEYS: [string, string][] = [
  ['空文字', ''],
  ['場所だけ', 'here'],
  ['区切りが2つ', 'here||x'],
  ['昔の id だけ（開発フロー）', ''],
  ['昔の id だけ（パイプ名）', 'diagrams'],
  ['知らない場所', 'other|diagrams'],
  ['場所が空', '|diagrams'],
  ['wt. だけ', 'wt.|diagrams'],
  ['場所に空白', 'wt.a b|diagrams'],
  ['場所に /', 'wt.a/b|diagrams'],
  ['場所が長すぎる（101 字）', `wt.${'a'.repeat(101)}|diagrams`],
  ['id に ..', 'here|..'],
  ['id に ../x', 'here|../x'],
  ['id に /', 'here|a/b'],
  ['id に \\', 'here|a\\b'],
  ['id が絶対パス', 'here|/etc/passwd'],
  ['id が Windows の絶対パス', 'here|C:\\x'],
  ['id が logs（予約名）', 'here|logs'],
  ['id が archive だけ（予約名）', 'here|archive'],
  ['archive の日時が壊れている', 'here|archive/2026'],
  ['archive/..', 'here|archive/..'],
  ['archive の外へ', 'here|archive/../x'],
  ['archive の下がさらに深い', 'here|archive/20261017-100000/x'],
  ['大文字・下線のフォルダ名', 'here|Bad_Name'],
  ['長すぎる id', `here|${'a'.repeat(5000)}`],
  ['改行', 'here|a\nb'],
];

for (const [label, key] of BAD_KEYS) {
  test(`D0019-AC-01: 形の違う実行の目印は通さない：${label}`, async () => {
    const { parseRunKey, isRunKey } = await runs();
    assert.equal(parseRunKey(key), null);
    assert.equal(isRunKey(key), false);
  });
}

test('D0019-AC-01: 文字でない値は目印でない（例外を出さない）', async () => {
  const { parseRunKey, isRunKey } = await runs();
  for (const value of [3, null, undefined, {}, ['here|']] as unknown[]) {
    assert.equal(isRunKey(value as string), false);
    assert.equal(parseRunKey(value as string), null);
  }
});
