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
