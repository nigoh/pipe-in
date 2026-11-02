// 「見本から作る」の手順（app/exampleFlow.ts）：名前の確かめ・見本からモデルを作る。書く口（PipeStore・VersionStore）は受け取らない（D0070）。
// 保存は既存の savePipe（偽の PipeStore）で確かめる。新しいファイルが無いあいだは「まだ作っていない」で落とす。
// 書ける範囲（fsPipes）が変わらないことの検査は、今のまま通る（守る）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadPipe, savePipe, saveTarget } from './pipeEditor.ts';
import type { PipeRef, PipeStore } from './pipeEditor.ts';
import { createFsPipeStore } from '../infra/fsPipes.ts';
import { validatePipe, targetName } from '../domain/pipeModel.ts';
import type { PipeModel } from '../domain/pipeModel.ts';

const SRC = fileURLToPath(new URL('..', import.meta.url));
interface ExampleData { name: string; files: Record<string, string> }
type Started = { model: PipeModel } | { error: string };

function needFile(rel: string): string {
  const file = path.join(SRC, rel);
  assert.ok(existsSync(file), `${rel} が無い（まだ作っていない）`);
  return file;
}
async function mods() {
  needFile('app/exampleFlow.ts');
  needFile('domain/pipeExamples.ts');
  needFile('domain/exampleData.ts');
  const flow = (await import('./exampleFlow.ts')) as unknown as {
    exampleNameProblem(refs: PipeRef[], dirs: string[], name: string): string | null;
    startFromExample(refs: PipeRef[], dirs: string[], ex: ExampleData, name: string): Started;
  };
  const ex = (await import('../domain/pipeExamples.ts')) as unknown as {
    listExamples(): { name: string }[];
    exampleModel(ex: ExampleData, name: string): PipeModel;
    findExample(name: string, d?: ExampleData[]): ExampleData | undefined | null;
  };
  const { EXAMPLE_DATA } = (await import('../domain/exampleData.ts')) as { EXAMPLE_DATA: ExampleData[] };
  return { ...flow, ...ex, EXAMPLE_DATA };
}

/** 呼び出しを数える偽の PipeStore（書く・消すが呼ばれた回数と、書いたファイルを持つ） */
function countingStore(files: Record<string, string> = {}) {
  const calls = { write: [] as [string, string][], remove: [] as [string, string][], read: 0 };
  const store: PipeStore = {
    async listPipes() { return [...new Set(Object.keys(files).map((k) => k.split('/')[0]!))].sort(); },
    async read(pipe, rel) { calls.read++; return files[`${pipe}/${rel}`] ?? null; },
    async listPrompts(pipe) { return Object.keys(files).filter((k) => k.startsWith(`${pipe}/prompts/`)).map((k) => k.slice(pipe.length + 1)); },
    async write(pipe, rel, text) { calls.write.push([pipe, rel]); files[`${pipe}/${rel}`] = text; },
    async remove(pipe, rel) { calls.remove.push([pipe, rel]); delete files[`${pipe}/${rel}`]; },
  };
  return { store, calls, files };
}

const DIRS = ['/w/.pipe-in/pipes'];
const ref = (name: string): PipeRef => ({ name, dir: DIRS[0]!, folder: `pipe-in-${name}`, legacy: false });
const small: ExampleData = {
  name: 'small',
  files: {
    'pipe.toml': '[pipe]\nkind = "linear"\nlabel = "小さい見本"\ndescription = "説明"\n\n[[stages]]\nname = "a"\nlabel = "A"\noutput = "a.md"\naccess = "read"\nprompt_file = "prompts/01_a.md"\n',
    'prompts/01_a.md': 'A をする\n',
  },
};

// ---- AC-24 ----

test('D0070-AC-24: 見本からモデルを作り_名前と同名の断りはsaveTargetと同じ文', async () => {
  const { startFromExample, exampleNameProblem } = await mods();
  const ok = startFromExample([], DIRS, small, 'mine');
  assert.ok('model' in ok, JSON.stringify(ok));
  assert.equal(ok.model.name, 'mine');
  assert.deepEqual(ok.model.stages.map((s) => s.name), ['a']);
  assert.equal(ok.model.stages[0]!.prompt, 'A をする');
  assert.equal(exampleNameProblem([], DIRS, 'mine'), null);
  // 使えない名前・同名・置き場所なしは、保存の確かめ（saveTarget）と同じ文で断る
  const refs = [ref('research')];
  const cases: [PipeRef[], string[], string][] = [
    [[], DIRS, 'Bad'], [[], DIRS, 'logs'], [[], DIRS, 'end'], [[], DIRS, ''], [refs, DIRS, 'research'], [[], [], 'fine'],
  ];
  for (const [r, d, name] of cases) {
    const target = saveTarget(r, null, name, d);
    assert.ok('error' in target, `${name}: saveTarget が断る前提`);
    assert.equal(exampleNameProblem(r, d, name), target.error, name);
    assert.deepEqual(startFromExample(r, d, small, name), { error: target.error }, name);
  }
});

test('D0070-AC-24: 3 つの見本からモデルを作ると、名前は渡した名前で、段・指示文は見本のとおり', async () => {
  const { startFromExample, EXAMPLE_DATA, exampleModel } = await mods();
  assert.equal(EXAMPLE_DATA.length, 3);
  for (const ex of EXAMPLE_DATA) {
    const r = startFromExample([], DIRS, ex, 'my-copy');
    assert.ok('model' in r, ex.name);
    assert.equal(r.model.name, 'my-copy');
    assert.deepEqual(r.model.stages.map((s) => s.name), exampleModel(ex, ex.name).stages.map((s) => s.name));
    assert.deepEqual(validatePipe(r.model).errors, [], ex.name);
  }
});

// ---- AC-25 ----

test('D0070-AC-25: 見本をsavePipeで保存すると書くのは決まったファイルだけ（第1引数は pipe-in-<名前>・remove は呼ばれない）', async () => {
  const { startFromExample, EXAMPLE_DATA } = await mods();
  for (const ex of EXAMPLE_DATA) {
    const r = startFromExample([], DIRS, ex, 'saved');
    assert.ok('model' in r, ex.name);
    const { store, calls } = countingStore();
    const written = await savePipe(store, r.model, 'pipe-in-saved');
    assert.ok(calls.write.length > 0, ex.name);
    assert.ok(calls.write.every(([pipe]) => pipe === 'pipe-in-saved'), ex.name);
    assert.ok(calls.write.every(([, rel]) => rel === 'pipe.toml' || rel === 'layout.json' || rel === 'README.md' || /^prompts\/[^/]+\.md$/.test(rel)), `${ex.name}: ${calls.write.map((c) => c[1]).join(',')}`);
    assert.equal(calls.write.filter(([, rel]) => rel.startsWith('prompts/')).length, r.model.stages.length, `${ex.name}: 指示文の数`);
    assert.ok(written.includes('README.md'), `${ex.name}: README が無ければ下書きを作る`);
    assert.deepEqual(calls.remove, [], `${ex.name}: remove`);
  }
});

// ---- AC-26 ----

test('D0070-AC-26: 保存してloadPipeで読み戻しても段_access_上限が落ちない（3 つの見本）', async () => {
  const { startFromExample, EXAMPLE_DATA } = await mods();
  for (const ex of EXAMPLE_DATA) {
    const r = startFromExample([], DIRS, ex, 'round');
    assert.ok('model' in r, ex.name);
    const { store } = countingStore();
    await savePipe(store, r.model, 'pipe-in-round');
    const back = await loadPipe(store, 'pipe-in-round');
    const pick = (m: PipeModel) => m.stages.map((s) => [s.name, s.access, s.docsDir, s.maxBudget, s.maxTurns, s.review, s.prompt, s.output, s.check.on, s.check.command, s.check.verdict, s.check.maxRetries, s.onFail ? targetName(m, s.onFail) : null, JSON.stringify(s.check.judge ?? null)]);
    assert.deepEqual(pick(back), pick(r.model), ex.name);
    assert.deepEqual(validatePipe(back).errors, [], ex.name);
    assert.equal(back.input, r.model.input, `${ex.name}: input`);
  }
});

// ---- AC-27 ----

test('D0070-AC-27: 一覧_名前_モデルの手順はwriteもremoveも呼ばずVersionStoreにも書かない（書く口を受け取らない形）', async () => {
  const { startFromExample, exampleNameProblem, listExamples, EXAMPLE_DATA } = await mods();
  const { store, calls } = countingStore();
  const versions = { saved: 0 };
  void store; void versions;
  listExamples();
  exampleNameProblem([], DIRS, 'x');
  for (const ex of EXAMPLE_DATA) startFromExample([], DIRS, ex, 'x');
  assert.deepEqual(calls, { write: [], remove: [], read: 0 });
  assert.equal(versions.saved, 0);
  // 書く口を引数に取らない：関数の形と、ファイルの字面の両方で
  assert.equal(startFromExample.length, 4);
  assert.equal(exampleNameProblem.length, 3);
  const source = readFileSync(needFile('app/exampleFlow.ts'), 'utf8');
  assert.ok(!/\b(?:PipeStore|VersionStore)\b/.test(source.replace(/\/\/.*$/gm, '')), 'exampleFlow.ts が PipeStore・VersionStore を使っている');
  assert.ok(!/node:fs|\bwriteFile\b|\bmkdir\b|\bvscode\b/.test(source.replace(/\/\/.*$/gm, '')));
});

// ---- AC-28 ----

test('D0070-AC-28: logs_.._スラッシュを含む名前は断り_fsPipesの書けるファイルは変わらない', async () => {
  const { startFromExample, exampleNameProblem } = await mods();
  for (const bad of ['logs', '..', '../x', 'a/b', '/etc', 'a\\b', 'x/..', '.']) {
    assert.ok(exampleNameProblem([], DIRS, bad) !== null, bad);
    assert.ok('error' in startFromExample([], DIRS, small, bad), bad);
  }
  // fsPipes が書けるファイルは pipe.toml・layout.json・README.md・prompts/*.md のまま（今のまま通る）
  const root = mkdtempSync(path.join(tmpdir(), 'ex-fs-'));
  const fs = createFsPipeStore(root);
  for (const rel of ['pipe.toml', 'layout.json', 'README.md', 'prompts/01_a.md']) await fs.write('pipe-in-ok', rel, 'x');
  for (const rel of ['run.sh', 'notes.txt', 'prompts/a.sh', 'prompts/../pipe.toml', '../x.md', 'sub/pipe.toml']) {
    await assert.rejects(fs.write('pipe-in-ok', rel, 'x'), rel);
  }
  await assert.rejects(fs.write('other', 'pipe.toml', 'x'));
  await assert.rejects(fs.write('pipe-in-..', 'pipe.toml', 'x'));
});

// ---- AC-33 ----

test('D0070-AC-33: exampleFlow_tsは ./pipeEditor.ts と domain だけを読む（vscode・infra・view を読まない）', () => {
  const source = readFileSync(needFile('app/exampleFlow.ts'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  const specs = Array.from(source.matchAll(/(?:\bfrom|\bimport)\s*\(?\s*['"]([^'"]+)['"]/g), (m) => m[1]!);
  assert.ok(specs.length > 0);
  for (const s of specs) assert.ok(s === './pipeEditor.ts' || s === 'node:path' || /^\.\.\/domain\//.test(s), `読んでよいのは ./pipeEditor.ts と ../domain/ だけ：${s}`);
});
