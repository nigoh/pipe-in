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

test('AC-01・D0006-AC-15: contributes.commands に「pipe-in: 実行を見る」のコマンド（pipe-in.showRun）が1つある', () => {
  const manifest = readManifest();
  const commands = manifest.contributes?.commands;
  assert.ok(Array.isArray(commands), 'contributes.commands が配列であること');
  const matched = commands.filter((c: any) => c?.title === 'pipe-in: 実行を見る');
  assert.equal(matched.length, 1);
  assert.equal(matched[0].command, 'pipe-in.showRun');
});

test('AC-02・D0006-AC-15: contributes.configuration に work_dir の設定項目（pipe-in.workDir）があり、既定値が docs/pipeline', () => {
  const manifest = readManifest();
  const prop = manifest.contributes?.configuration?.properties?.['pipe-in.workDir'];
  assert.ok(prop, 'pipe-in.workDir の設定項目があること');
  assert.equal(prop.default, 'docs/pipeline');
});

test('D0006-AC-15: 拡張の名前・表示名・repository・コマンド・設定が pipe-in で、contributes に devpipe で始まる ID・キーが無い', () => {
  const manifest = readManifest();
  assert.equal(manifest.name, 'pipe-in-vscode');
  assert.equal(manifest.displayName, 'pipe-in');
  assert.equal(manifest.repository?.url, 'https://github.com/nigoh/pipe-in');
  assert.equal(manifest.contributes?.configuration?.title, 'pipe-in');
  const commands = (manifest.contributes?.commands ?? []).map((c: any) => c?.command).sort();
  assert.deepEqual(commands, ['pipe-in.editPipe', 'pipe-in.showRun']);
  const keys = Object.keys(manifest.contributes?.configuration?.properties ?? {}).sort();
  assert.deepEqual(keys, ['pipe-in.pipesDir', 'pipe-in.workDir']);
  assert.equal(manifest.contributes.configuration.properties['pipe-in.pipesDir'].default, '');
  assert.doesNotMatch(JSON.stringify(manifest.contributes), /devpipe/i);
  assert.doesNotMatch(JSON.stringify({ name: manifest.name, displayName: manifest.displayName, description: manifest.description }), /devpipe/i);
});

test('D0006-AC-17: 古いコマンド ID はパレットに出さない（contributes.commands に無く、拡張が登録だけする）', () => {
  const manifest = readManifest();
  const ids = (manifest.contributes?.commands ?? []).map((c: any) => c?.command);
  for (const old of ['devpipe.showRun', 'devpipe.editPipe']) assert.ok(!ids.includes(old), old);
  const src = readFileSync(new URL('./extension.ts', import.meta.url), 'utf8');
  assert.match(src, /LEGACY_COMMANDS/, 'extension.ts が古いコマンド ID の表（LEGACY_COMMANDS）を使って登録する');
  assert.match(src, /from '\.\/app\/names\.ts'/, 'コマンド ID は app/names.ts の表から読む');
});

test('D0006-AC-15: パッケージのスクリプトが pipe-in-vscode.vsix を作る', () => {
  assert.match(readManifest().scripts?.package ?? '', /-o pipe-in-vscode\.vsix$/);
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

test('AC-34・D0006-AC-15: 作業台のコマンドと、pipes/ の場所の設定がある', () => {
  const manifest = readManifest();
  const commands = manifest.contributes?.commands ?? [];
  assert.equal(commands.filter((c: any) => c?.command === 'pipe-in.editPipe' && c?.title === 'pipe-in: パイプ作業台を開く').length, 1);
  const prop = manifest.contributes?.configuration?.properties?.['pipe-in.pipesDir'];
  assert.ok(prop, 'pipe-in.pipesDir の設定項目があること');
  assert.equal(prop.default, '', '空なら .pipe-in/pipes・.devpipe/pipes（無くて pipes があれば pipes）を自動で決める');
});

test('AC-34: パネルの中で動く作業台のスクリプトも、ビルドで out/ に束ねる', () => {
  const manifest = readManifest();
  assert.match(manifest.scripts?.build ?? '', /src\/webview\/pipeEditor\.ts/);
  assert.match(manifest.scripts?.build ?? '', /out\/pipeEditor\.js/);
});

test('AC-57・D0006-AC-15: 名前は「パイプ作業台」。コマンドの表示は「pipe-in: パイプ作業台を開く」', () => {
  const commands = readManifest().contributes?.commands ?? [];
  const edit = commands.find((c: any) => c?.command === 'pipe-in.editPipe');
  assert.equal(edit?.title, 'pipe-in: パイプ作業台を開く');
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
