// 検証の段で足したテスト：ユースケース refreshView と設定の解決 resolveWorkDir（FR-01・FR-02・FR-14）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { DEFAULT_WORK_DIR, refreshView, resolveWorkDir } from './refreshView.ts';
import type { WorkDirSource } from './refreshView.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { snapshot, stateJson } from '../test/fixtures.ts';

test('FR-01: 既定の work_dir は docs-internal/pipeline で、設定が空・空白・未設定なら既定を使う', () => {
  const root = path.resolve('/ws');
  assert.equal(DEFAULT_WORK_DIR, 'docs-internal/pipeline');
  for (const setting of [undefined, '', '   ']) {
    assert.equal(resolveWorkDir(root, setting), path.resolve(root, 'docs-internal/pipeline'));
  }
});

test('FR-01: 設定はワークスペースの最初のフォルダからの相対パスとして解決する', () => {
  const root = path.resolve('/ws');
  assert.equal(resolveWorkDir(root, 'docs/pipeline'), path.resolve(root, 'docs/pipeline'));
});

test('FR-02/14: 口が例外を投げても、例外を出さず記録なしの表示（work_dir のパス入り）になる', async () => {
  const source: WorkDirSource = {
    read: () => Promise.reject(new Error('boom')),
  };
  const view = await refreshView(source, '/ws/docs-internal/pipeline');
  assert.deepEqual(view.noRecords, { message: '記録がありません', workDir: '/ws/docs-internal/pipeline' });
  assert.equal(view.nodes.length, 11);
});

test('FR-12: refreshView は口の写しから buildPipelineView と同じ図の状態を作る', async () => {
  const snap = snapshot({ stateJson: stateJson({ final: 'PASSED', totalCostUsd: 1.25 }) });
  const view = await refreshView({ read: async () => snap }, '/ignored');
  assert.deepStrictEqual(view, buildPipelineView(snap));
});
