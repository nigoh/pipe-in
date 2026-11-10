// 拡張機能の宣言（package.json）のうち、作業台から流す機能（D0078）の分。AC-30・31。
// 既存の manifest.test.ts は設定の鍵の数（5 → 6）だけを書き換えた（理由：機能の要件で設定 pipe-in.command が1つ増えるため）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

function readManifest(): any {
  return JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
}

const commandProp = (): any => readManifest().contributes?.configuration?.properties?.['pipe-in.command'];

// ---- AC-30：設定 pipe-in.command ----

test('D0078-AC-30: 設定 pipe-in.command がある。型は string、既定は pipe-in', () => {
  const prop = commandProp();
  assert.ok(prop, 'pipe-in.command の設定項目があること');
  assert.equal(prop.type, 'string');
  assert.equal(prop.default, 'pipe-in');
});

test('D0078-AC-30: 設定 pipe-in.command の scope は machine（ワークスペースの設定ファイルでは決められない）', () => {
  assert.equal(commandProp()?.scope, 'machine');
});

test('D0078-AC-30: 設定 pipe-in.command の説明に「絶対パス」と、既定の pipe-in が出る。前の名前（devpipe）は書かない', () => {
  const prop = commandProp();
  assert.ok(prop, 'pipe-in.command の設定項目があること');
  assert.equal(typeof prop.description, 'string');
  assert.ok(prop.description.includes('絶対パス'), prop.description);
  assert.ok(prop.description.includes('pipe-in'), prop.description);
  assert.doesNotMatch(JSON.stringify(prop), /devpipe/i);
});

test('D0078-AC-30: 設定の鍵は 6 つ（pipe-in.command が増えた）で、既存の 5 つは残る。コマンド ID は 2 つのまま', () => {
  const manifest = readManifest();
  const keys = Object.keys(manifest.contributes?.configuration?.properties ?? {}).sort();
  assert.deepEqual(keys, ['pipe-in.command', 'pipe-in.notifyWhenWaiting', 'pipe-in.pipesDir', 'pipe-in.showOtherWorktrees', 'pipe-in.staleAfterMinutes', 'pipe-in.workDir']);
  assert.equal((manifest.contributes?.commands ?? []).length, 2, 'コマンド ID は増やさない');
});

test('D0078-AC-30: タスクの宣言（taskDefinitions・problemMatchers・problemPatterns・onTaskType の起動）を足さない（利用者が tasks.json に書ける型を増やさない）', () => {
  const manifest = readManifest();
  const contributes = manifest.contributes ?? {};
  for (const key of ['taskDefinitions', 'problemMatchers', 'problemPatterns', 'tasks']) assert.equal(contributes[key], undefined, key);
  const events: string[] = manifest.activationEvents ?? [];
  assert.ok(!events.some((e) => /^onTaskType/.test(e)), 'onTaskType で起動しない');
  assert.doesNotMatch(JSON.stringify(manifest), /taskDefinitions|"type"\s*:\s*"pipe-in"/);
});

test('D0078-AC-30: 設定の名前は他の設定と同じ節 pipe-in にあり、前の版の節（devpipe.command）は宣言しない', () => {
  const props = readManifest().contributes?.configuration?.properties ?? {};
  assert.equal(props['devpipe.command'], undefined);
  assert.ok(Object.keys(props).every((k) => k.startsWith('pipe-in.')));
});

test('D0078-AC-30: 既存の設定の鍵・型・既定は変えない（pipesDir・workDir は文字、showOtherWorktrees は真偽、staleAfterMinutes は整数、notifyWhenWaiting は真偽）（今のまま通る。守る）', () => {
  const props = readManifest().contributes?.configuration?.properties ?? {};
  assert.equal(props['pipe-in.pipesDir']?.type, 'string');
  assert.equal(props['pipe-in.workDir']?.default, 'docs/pipeline');
  assert.equal(props['pipe-in.showOtherWorktrees']?.default, true);
  assert.equal(props['pipe-in.staleAfterMinutes']?.type, 'integer');
  assert.equal(props['pipe-in.notifyWhenWaiting']?.default, true);
});

// ---- AC-31：信頼していないワークスペース ----

test('D0078-AC-31: capabilities.untrustedWorkspaces.supported は false（limited でも true でもない）', () => {
  const cap = readManifest().capabilities?.untrustedWorkspaces;
  assert.ok(cap, 'capabilities.untrustedWorkspaces があること');
  assert.strictEqual(cap.supported, false);
});

test('D0078-AC-31: untrustedWorkspaces に説明（description）がある。空でなく、信頼に触れる', () => {
  const cap = readManifest().capabilities?.untrustedWorkspaces;
  assert.ok(cap, 'capabilities.untrustedWorkspaces があること');
  assert.equal(typeof cap.description, 'string');
  assert.ok(cap.description.trim().length > 0);
  assert.match(cap.description, /信頼/);
});

test('D0078-AC-31: 信頼していない場所でも限定的に動く（limited）の宣言をしない（restrictedConfigurations を使わない）', () => {
  const cap = readManifest().capabilities?.untrustedWorkspaces;
  assert.ok(cap, 'capabilities.untrustedWorkspaces があること');
  assert.equal(cap.restrictedConfigurations, undefined);
  assert.notEqual(cap.supported, 'limited');
});
