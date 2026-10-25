// 拡張機能の宣言（package.json）の検査。AC-01・AC-02。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
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

test('D0019-AC-15: 設定 pipe-in.showOtherWorktrees は真偽で、既定は出す（true）。説明がある。コマンドは増えない', () => {
  const manifest = readManifest();
  const prop = manifest.contributes?.configuration?.properties?.['pipe-in.showOtherWorktrees'];
  assert.ok(prop, 'pipe-in.showOtherWorktrees の設定項目があること');
  assert.equal(prop.type, 'boolean');
  assert.equal(prop.default, true);
  assert.equal(typeof prop.description, 'string');
  assert.ok(prop.description.length > 0);
  assert.doesNotMatch(JSON.stringify(prop), /devpipe/i);
  assert.equal((manifest.contributes?.commands ?? []).length, 2, 'コマンド ID は増やさない');
});

// ---- D0021：止まっているかもしれない印の目安の設定（pipe-in.staleAfterMinutes）----

const staleProp = (): any => readManifest().contributes?.configuration?.properties?.['pipe-in.staleAfterMinutes'];

// コマンドが増えないこと・devpipe の名前が宣言に無いことは、上の D0019-AC-15 と下の D0006-AC-15 が見ている（設定の一覧の期待に足した分も、そこで見る）。ここでは繰り返さない。
test('D0021-AC-09: 設定 pipe-in.staleAfterMinutes は整数で、既定は 10、最小は 0', () => {
  const prop = staleProp();
  assert.ok(prop, 'pipe-in.staleAfterMinutes の設定項目があること');
  assert.equal(prop.type, 'integer');
  assert.equal(prop.default, 10);
  assert.equal(prop.minimum, 0);
});

test('D0021-AC-09: 設定 pipe-in.staleAfterMinutes の説明に「0 で印を出さない」と書いてある', () => {
  const prop = staleProp();
  assert.ok(prop, 'pipe-in.staleAfterMinutes の設定項目があること');
  assert.equal(typeof prop.description, 'string');
  assert.match(prop.description, /0 で印を出さない/);
});

test('D0021-AC-09: 最大は 10080（7 日）で、MAX_STALE_AFTER_MINUTES と同じ。staleAfterSeconds(最大) は MAX_SPAN_SEC と等しい（定数と宣言のずれを止める）', async () => {
  const prop = staleProp();
  assert.ok(prop, 'pipe-in.staleAfterMinutes の設定項目があること');
  assert.equal(prop.maximum, 10080);
  const { MAX_STALE_AFTER_MINUTES, staleAfterSeconds } = await import('./app/staleness.ts');
  const { MAX_SPAN_SEC } = (await import('./domain/timestamp.ts')) as unknown as { MAX_SPAN_SEC?: number };
  assert.equal(prop.maximum, MAX_STALE_AFTER_MINUTES);
  assert.equal(staleAfterSeconds(prop.maximum), MAX_SPAN_SEC);
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
  // D0019: 別の worktree を出す設定（pipe-in.showOtherWorktrees）が増えた。期待の一覧に足しただけで、ほかは変えない
  // D0021: 止まっているかもしれない印の目安の設定（pipe-in.staleAfterMinutes）が増えた。同じく期待の一覧に足しただけ
  // D0044: 確認待ちの知らせの設定（pipe-in.notifyWhenWaiting）が増えた。
  assert.deepEqual(keys, ['pipe-in.notifyWhenWaiting', 'pipe-in.pipesDir', 'pipe-in.showOtherWorktrees', 'pipe-in.staleAfterMinutes', 'pipe-in.workDir']);
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

test('AC-57・D0014-AC-29: 拡張・README・ガイド・スキル・エージェント・CLAUDE.md に、古い名前が残っていない', () => {
  // この検査自体が古い名前を含まないよう、文字をつないで作る
  const OLD = new RegExp('作' + '図');
  const root = fileURLToPath(new URL('..', import.meta.url));
  // README から移したガイドの文書（docs/guide/*.md）も見る。フォルダが空でも通ってしまわないよう、10個あることも確かめる
  const guide = path.join(root, '..', 'docs', 'guide');
  assert.ok(existsSync(guide), 'docs/guide/ が無い');
  const guideFiles = readdirSync(guide)
    .filter((name) => name.endsWith('.md'))
    .map((name) => path.join(guide, name));
  assert.equal(guideFiles.length, 10, 'docs/guide/ の .md が10個でない');
  const files = [
    ...guideFiles,
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

// ---- D0024：ステータスバーの件数 ----
// 宣言は変えない（ボタンは pipe-in.showRun のまま・コマンドは 2 つ・設定の鍵は D0044 で 5 つになった）。
// 変えるのは設定 pipe-in.showOtherWorktrees の説明の文だけ（「ステータスバーの件数」と「パネルを閉じている間の読み直し」にも効く）。
// 説明の言い方は「ステータスバー」にそろえた（利用者向けの文書と statusBar.test.ts に合わせる）。

test('D0024-AC-26: ステータスバーのボタンは pipe-in.showRun のまま（extension.ts が statusItem.command に COMMANDS.showRun だけを入れ、それは宣言のコマンドと同じ）（今のまま通る。守る）', async () => {
  const source = readFileSync(new URL('./extension.ts', import.meta.url), 'utf8');
  // 行頭のコメントに書いた代入で通さない
  const code = source
    .split(/\r?\n/)
    .filter((line) => !/^\s*(?:\/\/|\/\*|\*)/.test(line))
    .join('\n');
  const assigned = code.match(/\bstatusItem\.command\s*=(?!=)/g) ?? [];
  const toShowRun = code.match(/\bstatusItem\.command\s*=\s*COMMANDS\.showRun\s*;/g) ?? [];
  assert.ok(assigned.length >= 1, 'extension.ts が statusItem.command にコマンドを入れていること');
  assert.equal(toShowRun.length, assigned.length, 'statusItem.command に入れるのは COMMANDS.showRun だけ');
  const { COMMANDS } = await import('./app/names.ts');
  assert.equal(COMMANDS.showRun, 'pipe-in.showRun');
  const ids = (readManifest().contributes?.commands ?? []).map((c: any) => c?.command);
  assert.ok(ids.includes('pipe-in.showRun'), 'contributes.commands に pipe-in.showRun があること');
});

test('D0024-AC-26（D0044 で 5 つに書き換え）: コマンドは 2 つ、設定の鍵は 5 つ（件数の形を切る設定などを足さない。理由：機能の要件で設定が1つ増えるため）', () => {
  const manifest = readManifest();
  assert.equal((manifest.contributes?.commands ?? []).length, 2, 'コマンド ID は増やさない');
  assert.equal(Object.keys(manifest.contributes?.configuration?.properties ?? {}).length, 5, '設定の鍵は 5 つ（D0044 まで。増やすときは決定の記録に理由を書く）');
});

test('D0044-AC-17: pipe-in.notifyWhenWaiting は boolean・default true・説明あり', () => {
  const prop = readManifest().contributes?.configuration?.properties?.['pipe-in.notifyWhenWaiting'];
  assert.ok(prop, 'pipe-in.notifyWhenWaiting の設定項目があること');
  assert.equal(prop.type, 'boolean');
  assert.equal(prop.default, true);
  assert.equal(typeof prop.description, 'string');
  assert.ok(prop.description.length > 0, '説明があること');
});

test('D0044-AC-17: 既存の設定の鍵・型・既定は変えない（pipesDir・workDir は文字、showOtherWorktrees は真偽、staleAfterMinutes は整数）（今のまま通る。守る）', () => {
  const props = readManifest().contributes?.configuration?.properties ?? {};
  assert.equal(props['pipe-in.pipesDir']?.type, 'string');
  assert.equal(props['pipe-in.pipesDir']?.default, '');
  assert.equal(props['pipe-in.workDir']?.type, 'string');
  assert.equal(props['pipe-in.workDir']?.default, 'docs/pipeline');
  assert.equal(props['pipe-in.showOtherWorktrees']?.type, 'boolean');
  assert.equal(props['pipe-in.showOtherWorktrees']?.default, true);
  assert.equal(props['pipe-in.staleAfterMinutes']?.type, 'integer');
  assert.equal(props['pipe-in.staleAfterMinutes']?.default, 10);
});

for (const phrase of ['ステータスバーの件数', 'パネルを閉じている間の読み直し']) {
  test(`D0024-AC-48: 設定 pipe-in.showOtherWorktrees の説明に「${phrase}」がある`, () => {
    const prop = readManifest().contributes?.configuration?.properties?.['pipe-in.showOtherWorktrees'];
    assert.ok(prop, 'pipe-in.showOtherWorktrees の設定項目があること');
    assert.equal(typeof prop.description, 'string');
    assert.ok(prop.description.includes(phrase), `説明に「${phrase}」が無い（今の説明：${prop.description}）`);
  });
}

test('D0024-AC-48: 設定 pipe-in.showOtherWorktrees の鍵・型・既定は同じ（真偽で、既定は出す true）（今のまま通る。守る）', () => {
  const prop = readManifest().contributes?.configuration?.properties?.['pipe-in.showOtherWorktrees'];
  assert.ok(prop, 'pipe-in.showOtherWorktrees の設定項目があること');
  assert.equal(prop.type, 'boolean');
  assert.equal(prop.default, true);
});
