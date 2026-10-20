// 拡張の名前の表（コマンド ID・設定の節・パネルの型）と、古い設定・古いコマンド ID の読み替え。
// 前の版の名前（devpipe.*）は、新しい名前（pipe-in.*）が書かれていないときだけ読む。
import { test } from 'node:test';
import assert from 'node:assert/strict';
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

test('D0006-AC-17: 古いコマンド ID は新しい ID に対応する', () => {
  assert.deepEqual({ ...LEGACY_COMMANDS }, { 'devpipe.showRun': 'pipe-in.showRun', 'devpipe.editPipe': 'pipe-in.editPipe' });
  for (const id of Object.values(LEGACY_COMMANDS)) assert.ok(Object.values(COMMANDS).includes(id as never), id);
});
