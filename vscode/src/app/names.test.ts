// 拡張の名前の表（コマンド ID・設定の節・パネルの型）と、古い設定・古いコマンド ID の読み替え。
// 前の版の名前（devpipe.*）は、新しい名前（pipe-in.*）が書かれていないときだけ読む。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { COMMANDS, LEGACY_COMMANDS, LEGACY_SECTION, SECTION, VIEW_IDS, chooseSetting, settingKeys } from './names.ts';

test('D0006-AC-15: 設定の節・コマンド ID・パネルの型は pipe-in', () => {
  assert.equal(SECTION, 'pipe-in');
  assert.equal(LEGACY_SECTION, 'devpipe');
  assert.deepEqual({ ...COMMANDS }, { showRun: 'pipe-in.showRun', editPipe: 'pipe-in.editPipe' });
  assert.deepEqual({ ...VIEW_IDS }, { status: 'pipe-in.status', run: 'pipe-in.run', pipeEditor: 'pipe-in.pipeEditor' });
});

test('D0006-AC-16: chooseSetting は新しい設定 → 古い設定 → 既定の順', () => {
  const fallback = 'docs/pipeline';
  // どちらも書かれていなければ既定
  assert.equal(chooseSetting<string>(undefined, undefined, fallback), fallback);
  assert.equal(chooseSetting<string>({}, {}, fallback), fallback);
  // 新しい設定だけ
  assert.equal(chooseSetting<string>({ globalValue: 'new' }, {}, fallback), 'new');
  // 古い設定だけ（新しい設定を書いていない人）
  assert.equal(chooseSetting<string>({}, { workspaceValue: 'old' }, fallback), 'old');
  assert.equal(chooseSetting<string>(undefined, { globalValue: 'old' }, fallback), 'old');
  // 両方あれば新しい設定
  assert.equal(chooseSetting<string>({ workspaceValue: 'new' }, { workspaceValue: 'old' }, fallback), 'new');
});

test('D0006-AC-16: 新しい設定に既定と同じ値をわざわざ書いた場合も、新しい設定を使う', () => {
  assert.equal(chooseSetting<string>({ workspaceValue: 'docs/pipeline' }, { workspaceValue: 'other/place' }, 'docs/pipeline'), 'docs/pipeline');
  assert.equal(chooseSetting<string>({ globalValue: '' }, { globalValue: '.devpipe/pipes' }, ''), '');
});

test('D0006-AC-16: 同じ側の中では workspaceFolder → workspace → global の順', () => {
  assert.equal(chooseSetting<string>({ globalValue: 'g', workspaceValue: 'w', workspaceFolderValue: 'f' }, undefined, 'x'), 'f');
  assert.equal(chooseSetting<string>({ globalValue: 'g', workspaceValue: 'w' }, undefined, 'x'), 'w');
  assert.equal(chooseSetting<string>(undefined, { globalValue: 'g', workspaceValue: 'w', workspaceFolderValue: 'f' }, 'x'), 'f');
  // 新しい設定が global にだけあっても、古い設定の workspaceFolder より先
  assert.equal(chooseSetting<string>({ globalValue: 'new' }, { workspaceFolderValue: 'old' }, 'x'), 'new');
});

test('D0006-AC-16: settingKeys は新旧の両方を返す', () => {
  assert.deepEqual(settingKeys('workDir'), ['pipe-in.workDir', 'devpipe.workDir']);
  assert.deepEqual(settingKeys('pipesDir'), ['pipe-in.pipesDir', 'devpipe.pipesDir']);
});

test('D0019-AC-15: 別の worktree を出す設定の名前は showOtherWorktrees（package.json の pipe-in.showOtherWorktrees と同じ）。前の版の名前は無い', async () => {
  const names = (await import('./names.ts')) as unknown as { SETTING_SHOW_OTHER?: string };
  assert.equal(names.SETTING_SHOW_OTHER, 'showOtherWorktrees');
  assert.equal(`${SECTION}.${names.SETTING_SHOW_OTHER}`, 'pipe-in.showOtherWorktrees');
  // 前の版（devpipe）にはこの設定が無いので、読み替えの対象にしない（settingKeys はそのまま）
  assert.deepEqual(settingKeys('workDir'), ['pipe-in.workDir', 'devpipe.workDir']);
});

// ---- D0021：止まっているかもしれない印の目安の設定（pipe-in.staleAfterMinutes）----

/** 宣言（package.json）の設定のキー。この名前の定数が、宣言と同じ名前を指すことを見る */
function declaredSettingKeys(): string[] {
  const manifest = JSON.parse(readFileSync(new URL('../../package.json', import.meta.url), 'utf8')) as {
    contributes?: { configuration?: { properties?: Record<string, unknown> } };
  };
  return Object.keys(manifest.contributes?.configuration?.properties ?? {});
}

test('D0021-AC-51: 目安の設定の名前の定数 SETTING_STALE_AFTER は staleAfterMinutes（pipe-in.staleAfterMinutes）', async () => {
  const names = (await import('./names.ts')) as unknown as { SETTING_STALE_AFTER?: string };
  assert.equal(names.SETTING_STALE_AFTER, 'staleAfterMinutes');
  assert.equal(`${SECTION}.${names.SETTING_STALE_AFTER}`, 'pipe-in.staleAfterMinutes');
});

test('D0021-AC-51: 定数の名前は package.json の設定のキー（pipe-in.staleAfterMinutes）と一致する', async () => {
  const names = (await import('./names.ts')) as unknown as { SETTING_STALE_AFTER?: string };
  assert.equal(typeof names.SETTING_STALE_AFTER, 'string', '定数 SETTING_STALE_AFTER が app/names.ts にある');
  assert.ok(declaredSettingKeys().includes(`${SECTION}.${names.SETTING_STALE_AFTER}`), `${SECTION}.${names.SETTING_STALE_AFTER} が package.json の設定のキーにある`);
});

// この設定には前の版（devpipe）の名前が無いので、読み替えの表には入れない。その確かめは新しく置かない：
// settingKeys が workDir・pipesDir だけを読み替えるのは上の D0006-AC-16・D0019-AC-15 が、
// 宣言に devpipe で始まるキーが無いのは manifest.test.ts の D0006-AC-15 が、すでに確かめている。

// ---- D0045：確認待ちの知らせの設定（pipe-in.notifyWhenWaiting）----

test('D0045-AC-17: 知らせの設定の名前の定数 SETTING_NOTIFY は notifyWhenWaiting（pipe-in.notifyWhenWaiting）', async () => {
  const names = (await import('./names.ts')) as unknown as { SETTING_NOTIFY?: string };
  assert.equal(names.SETTING_NOTIFY, 'notifyWhenWaiting');
  assert.equal(`${SECTION}.${names.SETTING_NOTIFY}`, 'pipe-in.notifyWhenWaiting');
});

test('D0045-AC-17: 定数の名前は package.json の設定のキー（pipe-in.notifyWhenWaiting）と一致する', async () => {
  const names = (await import('./names.ts')) as unknown as { SETTING_NOTIFY?: string };
  assert.equal(typeof names.SETTING_NOTIFY, 'string', '定数 SETTING_NOTIFY が app/names.ts にある');
  assert.ok(declaredSettingKeys().includes(`${SECTION}.${names.SETTING_NOTIFY}`), `${SECTION}.${names.SETTING_NOTIFY} が package.json の設定のキーにある`);
});

test('D0045-AC-18: chooseSetting は新しい節が無ければ前の版の節の false を読み、どちらも無ければ true（今の作りで通る。守る）', () => {
  assert.equal(chooseSetting<unknown>({}, { workspaceValue: false }, true), false);
  assert.equal(chooseSetting<unknown>(undefined, { globalValue: false }, true), false);
  assert.equal(chooseSetting<unknown>({ globalValue: true }, { globalValue: false }, true), true);
  assert.equal(chooseSetting<unknown>({ workspaceValue: false }, { globalValue: true }, true), false);
  assert.equal(chooseSetting<unknown>(undefined, undefined, true), true);
});

test('D0045-AC-18: この設定には前の版の名前が無いので、settingKeys の読み替えの表（workDir・pipesDir）は増やさない（今の作りで通る。守る）', () => {
  assert.deepEqual(settingKeys('workDir'), ['pipe-in.workDir', 'devpipe.workDir']);
  assert.deepEqual(settingKeys('pipesDir'), ['pipe-in.pipesDir', 'devpipe.pipesDir']);
});

test('D0006-AC-17: 古いコマンド ID は新しい ID に対応する', () => {
  assert.deepEqual({ ...LEGACY_COMMANDS }, { 'devpipe.showRun': 'pipe-in.showRun', 'devpipe.editPipe': 'pipe-in.editPipe' });
  for (const id of Object.values(LEGACY_COMMANDS)) assert.ok(Object.values(COMMANDS).includes(id as never), id);
});
