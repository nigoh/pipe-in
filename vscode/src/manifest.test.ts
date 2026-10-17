// 拡張機能の宣言（package.json）の検査。AC-01・AC-02。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

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

test('AC-34: 作業台のコマンドと、pipes/ の場所の設定がある', () => {
  const manifest = readManifest();
  const commands = manifest.contributes?.commands ?? [];
  assert.equal(commands.filter((c: any) => c?.command === 'devpipe.editPipe' && c?.title === 'devpipe: パイプ作業台を開く').length, 1);
  const prop = manifest.contributes?.configuration?.properties?.['devpipe.pipesDir'];
  assert.ok(prop, 'devpipe.pipesDir の設定項目があること');
  assert.equal(prop.default, '', '空なら .devpipe/pipes → pipes の順に自動で決める');
});

test('AC-34: パネルの中で動く作業台のスクリプトも、ビルドで out/ に束ねる', () => {
  const manifest = readManifest();
  assert.match(manifest.scripts?.build ?? '', /src\/webview\/pipeEditor\.ts/);
  assert.match(manifest.scripts?.build ?? '', /out\/pipeEditor\.js/);
});

test('AC-57: 名前は「パイプ作業台」。コマンドの表示を変え、ID（devpipe.editPipe）はそのまま', () => {
  const commands = readManifest().contributes?.commands ?? [];
  const edit = commands.find((c: any) => c?.command === 'devpipe.editPipe');
  assert.equal(edit?.title, 'devpipe: パイプ作業台を開く');
});

test('AC-57: 拡張・README・スキル・エージェント・CLAUDE.md に、古い名前が残っていない', () => {
  // この検査自体が古い名前を含まないよう、文字をつないで作る
  const OLD = new RegExp('作' + '図');
  const root = fileURLToPath(new URL('..', import.meta.url));
  const files = [
    ...listFiles(path.join(root, 'src')),
    ...listFiles(path.join(root, 'scripts')),
    path.join(root, 'package.json'),
    path.join(root, 'README.md'),
    path.join(root, '..', 'README.md'),
    path.join(root, '..', 'CLAUDE.md'),
    path.join(root, '..', '.claude', 'skills', 'pipe-in', 'SKILL.md'),
    path.join(root, '..', '.claude', 'skills', 'pipe-help', 'SKILL.md'),
    path.join(root, '..', 'plugin', 'skills', 'pipe-build', 'SKILL.md'),
    path.join(root, '..', 'plugin', 'agents', 'pipe-builder.md'),
  ];
  const left = files.filter((f) => OLD.test(readFileSync(f, 'utf8'))).map((f) => path.relative(root, f));
  assert.deepEqual(left, []);
});

function listFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const full = path.join(dir, e.name);
    return e.isDirectory() ? listFiles(full) : e.name.endsWith('.ts') ? [full] : [];
  });
}
