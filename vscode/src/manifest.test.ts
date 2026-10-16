// 拡張機能の宣言（package.json）の検査。AC-01・AC-02。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

function readManifest(): any {
  const url = new URL('../package.json', import.meta.url);
  return JSON.parse(readFileSync(url, 'utf8'));
}

test('AC-01: contributes.commands に「devpipe: 実行を見る」のコマンドが1つある', () => {
  const manifest = readManifest();
  const commands = manifest.contributes?.commands;
  assert.ok(Array.isArray(commands), 'contributes.commands が配列であること');
  const matched = commands.filter((c: any) => c?.title === 'devpipe: 実行を見る');
  assert.equal(matched.length, 1);
});

test('AC-02: contributes.configuration に work_dir の設定項目があり、既定値が docs-internal/pipeline', () => {
  const manifest = readManifest();
  const prop = manifest.contributes?.configuration?.properties?.['devpipe.workDir'];
  assert.ok(prop, 'devpipe.workDir の設定項目があること');
  assert.equal(prop.default, 'docs-internal/pipeline');
});
