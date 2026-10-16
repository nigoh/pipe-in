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

test('AC-02: contributes.configuration に work_dir の設定項目があり、既定値が docs/pipeline', () => {
  const manifest = readManifest();
  const prop = manifest.contributes?.configuration?.properties?.['devpipe.workDir'];
  assert.ok(prop, 'devpipe.workDir の設定項目があること');
  assert.equal(prop.default, 'docs/pipeline');
});

test('パッケージ：.vsix にできる宣言（publisher・main・パッケージ前のビルド）がある', () => {
  const manifest = readManifest();
  assert.equal(typeof manifest.publisher, 'string');
  assert.ok(manifest.publisher.length > 0);
  assert.equal(manifest.main, './out/extension.cjs');
  assert.match(manifest.scripts?.['vscode:prepublish'] ?? '', /build/);
  assert.match(manifest.scripts?.package ?? '', /vsce package/);
});

test('パッケージ：.vscodeignore でソースと node_modules を同梱しない（ビルド済みの out/ だけを載せる）', () => {
  const ignore = readFileSync(new URL('../.vscodeignore', import.meta.url), 'utf8').split(/\r?\n/);
  for (const entry of ['src/**', 'node_modules/**']) assert.ok(ignore.includes(entry), entry);
  assert.ok(!ignore.includes('out/**'));
});

test('ステータスバー：起動の後すぐ動き出す（ボタンをいつも出すため）', () => {
  const manifest = readManifest();
  assert.ok((manifest.activationEvents ?? []).includes('onStartupFinished'));
});
