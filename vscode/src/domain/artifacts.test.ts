// 成果物の一覧と、開く求めの解決。AC-34〜AC-36。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { buildArtifactList, resolveArtifactPath } from './artifacts.ts';

test('AC-34: 7件が 00〜05・99 の順に並び、01 は「ある」、02（なし）と 03（空白だけ）は「まだない」', () => {
  const list = buildArtifactList({ '01_requirements.md': '中身', '03_red_tests.md': '  \n' });
  assert.deepEqual(
    list.map((a) => a.name),
    [
      '00_input.md',
      '01_requirements.md',
      '02_design.md',
      '03_red_tests.md',
      '04_implementation.md',
      '05_test_report.md',
      '99_summary.md',
    ],
  );
  const ready = Object.fromEntries(list.map((a) => [a.name, a.ready]));
  assert.equal(ready['01_requirements.md'], true);
  assert.equal(ready['02_design.md'], false);
  assert.equal(ready['03_red_tests.md'], false);
});

test('AC-35: 01_requirements.md を開く求めは、work_dir 直下のそのパスになる', () => {
  const w = path.resolve('/ws/docs/pipeline');
  assert.equal(resolveArtifactPath(w, '01_requirements.md'), path.join(w, '01_requirements.md'));
});

test('AC-36: ../secret.md を開く求めは拒否され、パスは返らない', () => {
  const w = path.resolve('/ws/docs/pipeline');
  assert.equal(resolveArtifactPath(w, '../secret.md'), null);
});
