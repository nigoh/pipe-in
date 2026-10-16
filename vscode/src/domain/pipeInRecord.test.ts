// /pipe-in が devpipe record で書く記録（tests/fixtures/pipe_in/ の見本）を、拡張が開発フローとして図にできるか。
// 見本は Python のテスト（tests/test_record.py）が devpipe record の出力と同じであることを確かめている。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildPipelineView } from './pipelineView.ts';
import type { PipelineView } from './pipelineView.ts';
import { isDevRecord, parseRunRecord } from './runRecord.ts';
import { statusBarLabel } from '../view/statusBar.ts';

const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'tests', 'fixtures', 'pipe_in');
const read = (...p: string[]): string => readFileSync(path.join(FIXTURES, ...p), 'utf8');

function view(name: string, logs: { fileName: string; text: string }[] = []): PipelineView {
  return buildPipelineView({ workDir: 'docs/pipeline', stateJson: read(name, 'state.json'), stageLogs: logs, artifacts: { '00_input.md': 'メモ' } });
}
const status = (v: PipelineView, id: string): string => v.nodes.find((n) => n.id === id)!.status;

test('AC-01: /pipe-in の記録は開発フローの記録として読める', () => {
  for (const name of ['running', 'waiting', 'finished']) assert.equal(isDevRecord(parseRunRecord(read(name, 'state.json'))), true, name);
});

test('AC-01: 段を始めたところ（記録が開いている）は「動いている」', () => {
  const v = view('running', [{ fileName: '01_requirements.jsonl', text: read('running', 'logs', '01_requirements.jsonl') }]);
  assert.equal(v.runningStage, 'requirements');
  assert.equal(status(v, 'requirements'), 'running');
  assert.match(statusBarLabel(v).text, /要件定義/);
});

test('AC-01: 確認待ちは、終わった段と確認待ちの段がわかる', () => {
  const v = view('waiting');
  assert.equal(status(v, 'requirements'), 'done');
  assert.equal(status(v, 'review:requirements'), 'done');
  assert.equal(v.nodes.find((n) => n.id === 'review:requirements')!.reviseCount, 1);
  assert.equal(status(v, 'design'), 'done');
  assert.equal(status(v, 'red'), 'done');
  assert.equal(status(v, 'review:red'), 'pending');
  assert.equal(v.pendingReview?.stage, 'red');
  assert.equal(v.final, null);
  assert.match(statusBarLabel(v).text, /確認待ち/);
});

test('AC-01: 終わった記録は、差し戻しと判定と最後の結果がわかる', () => {
  const v = view('finished');
  assert.equal(v.final, 'PASSED');
  assert.equal(status(v, 'final'), 'done');
  assert.equal(status(v, 'verdict'), 'done');
  assert.equal(v.nodes.find((n) => n.id === 'implement')!.sendBackCount, 1);
  assert.equal(v.pendingReview, null);
});
