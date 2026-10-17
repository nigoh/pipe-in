// 開発用のスキルが pipe-in record で書く記録を、拡張が開発フローとして図にできるか。
// 見本は2つ：今の形（tests/fixtures/pipe_dev/、driver = "pipe-dev"）と、前の版の形（tests/fixtures/pipe_in/、driver = "pipe-in"）。
// 今の見本は Python のテスト（tests/test_record.py）が pipe-in record の出力と同じであることを確かめている。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildPipelineView } from './pipelineView.ts';
import type { PipelineView } from './pipelineView.ts';
import { isDevRecord, parseRunRecord } from './runRecord.ts';
import { statusBarLabel } from '../view/statusBar.ts';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'tests', 'fixtures');
// [見本のフォルダ, driver]
const KINDS = [['pipe_dev', 'pipe-dev'], ['pipe_in', 'pipe-in']] as const;

for (const [dir, driver] of KINDS) {
  const read = (...p: string[]): string => readFileSync(path.join(ROOT, dir, ...p), 'utf8');
  const view = (name: string, logs: { fileName: string; text: string }[] = []): PipelineView =>
    buildPipelineView({ workDir: 'docs/pipeline', stateJson: read(name, 'state.json'), stageLogs: logs, artifacts: { '00_input.md': 'メモ' } });
  const status = (v: PipelineView, id: string): string => v.nodes.find((n) => n.id === id)!.status;

  test(`D0006-AC-24（${dir}）: 見本の driver は ${driver}`, () => {
    for (const name of ['running', 'waiting', 'finished']) assert.equal(JSON.parse(read(name, 'state.json')).driver, driver, name);
  });

  test(`AC-01・D0006-AC-24（${dir}）: 開発用のスキルの記録は開発フローの記録として読める`, () => {
    for (const name of ['running', 'waiting', 'finished']) assert.equal(isDevRecord(parseRunRecord(read(name, 'state.json'))), true, name);
  });

  test(`AC-01・D0006-AC-24（${dir}）: 段を始めたところ（記録が開いている）は「動いている」`, () => {
    const v = view('running', [{ fileName: '01_requirements.jsonl', text: read('running', 'logs', '01_requirements.jsonl') }]);
    assert.equal(v.runningStage, 'requirements');
    assert.equal(status(v, 'requirements'), 'running');
    assert.match(statusBarLabel(v).text, /要件定義/);
  });

  test(`AC-01・D0006-AC-24（${dir}）: 確認待ちは、終わった段と確認待ちの段がわかる`, () => {
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

  test(`AC-01・D0006-AC-24（${dir}）: 終わった記録は、差し戻しと判定と最後の結果がわかる`, () => {
    const v = view('finished');
    assert.equal(v.final, 'PASSED');
    assert.equal(status(v, 'final'), 'done');
    assert.equal(status(v, 'verdict'), 'done');
    assert.equal(v.nodes.find((n) => n.id === 'implement')!.sendBackCount, 1);
    assert.equal(v.pendingReview, null);
  });
}

test('D0006-AC-24: 今の見本と前の版の見本は、同じ図・確認待ち・結果になる', () => {
  for (const name of ['running', 'waiting', 'finished']) {
    const make = (dir: string) => {
      const text = readFileSync(path.join(ROOT, dir, name, 'state.json'), 'utf8');
      return buildPipelineView({ workDir: 'docs/pipeline', stateJson: text, stageLogs: [], artifacts: { '00_input.md': 'メモ' } });
    };
    assert.deepEqual(make('pipe_dev'), make('pipe_in'), name);
  }
});
