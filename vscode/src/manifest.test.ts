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
  // D0046: 確認待ちの知らせの設定（pipe-in.notifyWhenWaiting）が増えた。
  // D0078: 作業台から流す実行ファイルの設定（pipe-in.command）が増えた。期待の一覧に足しただけ
  assert.deepEqual(keys, ['pipe-in.command', 'pipe-in.notifyWhenWaiting', 'pipe-in.pipesDir', 'pipe-in.showOtherWorktrees', 'pipe-in.staleAfterMinutes', 'pipe-in.workDir']);
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
  // README から移したガイドの文書（docs/guide/*.md）も見る。フォルダが空でも通ってしまわないよう、11個あることも確かめる（D0072：start-without-commands.md を足したので数だけ 10 → 11）
  const guide = path.join(root, '..', 'docs', 'guide');
  assert.ok(existsSync(guide), 'docs/guide/ が無い');
  const guideFiles = readdirSync(guide)
    .filter((name) => name.endsWith('.md'))
    .map((name) => path.join(guide, name));
  assert.equal(guideFiles.length, 11, 'docs/guide/ の .md が11個でない');
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
// 宣言は変えない（ボタンは pipe-in.showRun のまま・コマンドは 2 つ・設定の鍵は D0046 で 5 つになった）。
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

test('D0024-AC-26（D0046 で 5 つ、D0078 で 6 つに書き換え）: コマンドは 2 つ、設定の鍵は 6 つ（件数の形を切る設定などを足さない。理由：機能の要件で設定が1つずつ増えるため）', () => {
  const manifest = readManifest();
  assert.equal((manifest.contributes?.commands ?? []).length, 2, 'コマンド ID は増やさない');
  assert.equal(Object.keys(manifest.contributes?.configuration?.properties ?? {}).length, 6, '設定の鍵は 6 つ（D0078 まで。増やすときは決定の記録に理由を書く）');
});

test('D0046-AC-17: pipe-in.notifyWhenWaiting は boolean・default true・説明あり', () => {
  const prop = readManifest().contributes?.configuration?.properties?.['pipe-in.notifyWhenWaiting'];
  assert.ok(prop, 'pipe-in.notifyWhenWaiting の設定項目があること');
  assert.equal(prop.type, 'boolean');
  assert.equal(prop.default, true);
  assert.equal(typeof prop.description, 'string');
  assert.ok(prop.description.length > 0, '説明があること');
});

test('D0046-AC-17: 既存の設定の鍵・型・既定は変えない（pipesDir・workDir は文字、showOtherWorktrees は真偽、staleAfterMinutes は整数）（今のまま通る。守る）', () => {
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

// ---- D0072：初めての人向けの案内（walkthrough） ----
// 宣言は contributes.walkthroughs（commands・configuration は変えない）。本文は vscode/walkthrough/ の Markdown。
// 外から何も読み込まず、案内を自動で開かない（globalState に書かない）。実機での見え方は D0072-AC-09（実機。自動のテストでは見ない）。

const WALKTHROUGH_STEP_IDS = ['pipe-in.install', 'pipe-in.choose', 'pipe-in.run', 'pipe-in.answer'];

function walkthroughs(): any[] {
  return readManifest().contributes?.walkthroughs ?? [];
}

function stepMarkdownPaths(): string[] {
  const vscodeRoot = fileURLToPath(new URL('..', import.meta.url));
  return (walkthroughs()[0]?.steps ?? []).map((s: any) => path.join(vscodeRoot, String(s?.media?.markdown ?? '')));
}

/** 案内の宣言（JSON の文字列）と、手順の本文の Markdown。本文が無ければ失敗にする。 */
function walkthroughTexts(): string[] {
  const decl = JSON.stringify(walkthroughs());
  const bodies = stepMarkdownPaths().map((p) => {
    assert.ok(existsSync(p), `${path.relative(fileURLToPath(new URL('..', import.meta.url)), p)} が無い`);
    return readFileSync(p, 'utf8');
  });
  return [decl, ...bodies];
}

test('D0072-AC-01: walkthroughs が1つで id・title・description と steps 4つ', () => {
  const list = walkthroughs();
  assert.equal(list.length, 1, 'contributes.walkthroughs がちょうど1つ');
  for (const key of ['id', 'title', 'description']) {
    assert.equal(typeof list[0][key], 'string', `${key} が文字`);
    assert.ok(list[0][key].length > 0, `${key} が空`);
  }
  assert.equal(list[0].steps?.length, 4, '手順が4つ');
});

test('D0072-AC-02: 手順の id が決めた4つの並びで、どれにも title・description・media.markdown がある', () => {
  const steps: any[] = walkthroughs()[0]?.steps ?? [];
  assert.deepEqual(
    steps.map((s) => s.id),
    WALKTHROUGH_STEP_IDS,
  );
  for (const s of steps) {
    for (const key of ['title', 'description']) {
      assert.ok(typeof s[key] === 'string' && s[key].length > 0, `${s.id} の ${key}`);
    }
    assert.ok(typeof s.media?.markdown === 'string' && s.media.markdown.length > 0, `${s.id} の media.markdown`);
  }
});

test('D0072-AC-03: media.markdown のファイルが実在し空でない', () => {
  const paths = stepMarkdownPaths();
  assert.equal(paths.length, 4, '手順が4つ');
  for (const p of paths) {
    assert.ok(existsSync(p), `${p} が無い`);
    assert.ok(readFileSync(p, 'utf8').trim().length > 0, `${p} が空`);
  }
});

test('D0072-AC-04: 案内の宣言と本文に外の読み込みが無い', () => {
  const texts = walkthroughTexts();
  assert.ok(texts[0].length > 2, '案内の宣言が空');
  for (const t of texts) {
    for (const bad of ['http://', 'https://', '<img', '<script', '<iframe']) {
      assert.ok(!t.includes(bad), `「${bad}」がある`);
    }
  }
});

test('D0072-AC-05: 案内の command: は contributes.commands の ID だけ', () => {
  const ids: string[] = (readManifest().contributes?.commands ?? []).map((c: any) => c?.command);
  assert.ok(ids.length > 0);
  const used = walkthroughTexts().flatMap((t) => [...t.matchAll(/command:([\w.-]+)/g)].map((m) => m[1]));
  assert.ok(used.length > 0, '案内に command: のリンクが1つも無い');
  for (const u of used) assert.ok(ids.includes(u), `command:${u} は contributes.commands に無い`);
});

test('D0072-AC-06（D0078 で設定を 6 つに書き換え）: コマンドは2つ・設定は6つ（理由：作業台から流す機能で設定 pipe-in.command が1つ増えるため）', () => {
  const manifest = readManifest();
  assert.equal((manifest.contributes?.commands ?? []).length, 2);
  assert.equal(Object.keys(manifest.contributes?.configuration?.properties ?? {}).length, 6);
});

test('D0072-AC-07: 本番のコードに openWalkthrough と globalState が無い（今のまま通る。守る）', () => {
  const srcDir = fileURLToPath(new URL('.', import.meta.url));
  const prod = listFiles(srcDir).filter((f) => !f.endsWith('.test.ts') && !f.split(path.sep).includes('test'));
  assert.ok(prod.length > 0, '本番の .ts が見つからない');
  const hits = prod.filter((f) => {
    const code = readFileSync(f, 'utf8')
      .split(/\r?\n/)
      .filter((line) => !/^\s*(?:\/\/|\/\*|\*)/.test(line))
      .join('\n');
    return /openWalkthrough|globalState/.test(code);
  });
  assert.deepEqual(hits.map((f) => path.relative(srcDir, f)), []);
});

test('D0072-AC-08: 手順の本文に pip install -e .・pipe-in の1行・usage.md の確認の画面がある', () => {
  const texts = walkthroughTexts();
  assert.equal(texts.length, 5, '案内の宣言と、手順 4 つの本文が要る（手順が4つ宣言されていない）');
  const [, install, , run, answer] = texts;
  // README.md の塊と同じ綴りで書いてあること
  const readme = readFileSync(new URL('../../README.md', import.meta.url), 'utf8');
  const pip = readme.split(/\r?\n/).find((l) => l.trim().startsWith('pip install -e .'));
  assert.ok(pip, 'README.md に pip install -e . の行が無い');
  assert.ok(install.includes('pip install -e .'), '「入れる」の手順に pip install -e . が無い');
  assert.ok(/^\s*pipe-in\s+--project\b/m.test(run), '「流す」の手順に pipe-in --project … の1行が無い');
  assert.ok(answer.includes('docs/guide/usage.md'), '「確認に答える」の手順に docs/guide/usage.md の案内が無い');
  assert.ok(answer.includes('確認の画面'), '「確認に答える」の手順に確認の画面の案内が無い');
});
