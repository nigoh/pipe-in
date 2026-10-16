// 作図台の読み込みと保存の手順（ファイルの置き場所は口 PipeStore の向こう）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { choosePipesDir, isPipeName, listPipes, loadPipe, savePipe } from './pipeEditor.ts';
import type { PipeStore } from './pipeEditor.ts';
import { newPipe } from '../domain/pipeModel.ts';

function memoryStore(files: Record<string, string> = {}): PipeStore & { files: Record<string, string> } {
  return {
    files,
    async listPipes() { return [...new Set(Object.keys(files).map((k) => k.split('/')[0]!))].sort(); },
    async read(pipe, rel) { return files[`${pipe}/${rel}`] ?? null; },
    async listPrompts(pipe) { return Object.keys(files).filter((k) => k.startsWith(`${pipe}/prompts/`)).map((k) => k.slice(pipe.length + 1)); },
    async write(pipe, rel, text) { files[`${pipe}/${rel}`] = text; },
    async remove(pipe, rel) { delete files[`${pipe}/${rel}`]; },
  };
}

const TOML = '[pipe]\nkind = "linear"\nlabel = "x"\n\n[[stages]]\nname = "a"\nlabel = "A"\noutput = "a.md"\naccess = "read"\nprompt_file = "prompts/01_a.md"\n';

test('AC-29: pipes/ のパイプ（devpipe-<名前>）を一覧にする', async () => {
  const store = memoryStore({ 'devpipe-one/pipe.toml': TOML, 'devpipe-two/pipe.toml': TOML, 'other/pipe.toml': TOML, 'devpipe-empty/README.md': '' });
  assert.deepEqual(await listPipes(store), ['one', 'two']);
});

test('AC-29: 読み込み：pipe.toml と prompts/ と layout.json から', async () => {
  const store = memoryStore({ 'devpipe-one/pipe.toml': TOML, 'devpipe-one/prompts/01_a.md': 'A をする\n' });
  const m = await loadPipe(store, 'one');
  assert.equal(m.stages[0]!.prompt, 'A をする');
  assert.ok(m.stages[0]!.x > 0); // layout.json がないので自動で並べた
});

test('AC-30: 保存：pipe.toml・prompts/・layout.json を書き、使わなくなった指示を消し、README は無いときだけ作る', async () => {
  const store = memoryStore({ 'devpipe-one/pipe.toml': TOML, 'devpipe-one/prompts/01_a.md': 'A をする\n', 'devpipe-one/prompts/09_old.md': '古い\n' });
  const m = await loadPipe(store, 'one');
  m.stages[0]!.prompt = 'A を丁寧にする';
  const written = await savePipe(store, m);
  assert.ok(written.includes('pipe.toml') && written.includes('layout.json') && written.includes('prompts/01_a.md'));
  assert.equal(store.files['devpipe-one/prompts/01_a.md'], 'A を丁寧にする\n');
  assert.equal(store.files['devpipe-one/prompts/09_old.md'], undefined);
  assert.ok(store.files['devpipe-one/README.md']!.includes('devpipe --pipe one'));
  store.files['devpipe-one/README.md'] = '# 手で書いた\n';
  await savePipe(store, m);
  assert.equal(store.files['devpipe-one/README.md'], '# 手で書いた\n');
});

test('AC-30: 新しいパイプも保存できる。名前は devpipe と同じ決まり', async () => {
  assert.equal(isPipeName('my-pipe'), true);
  for (const bad of ['', 'Bad', '../x', 'logs', 'end', 'a/b']) assert.equal(isPipeName(bad), false, bad);
  const store = memoryStore();
  await savePipe(store, newPipe('fresh'));
  assert.ok(store.files['devpipe-fresh/pipe.toml']!.includes('[pipe]'));
  await assert.rejects(() => savePipe(store, newPipe('../escape')));
});

test('AC-17: 作図台の置き場所は、設定 → .devpipe/pipes → pipes → .devpipe/pipes の順に決める', () => {
  const ws = '/work/app';
  const has = (...dirs: string[]) => (p: string) => dirs.includes(p);
  assert.equal(choosePipesDir('/abs/pipes', ws, has()), '/abs/pipes');
  assert.equal(choosePipesDir('my-pipes', ws, has()), path.join(ws, 'my-pipes'));
  assert.equal(choosePipesDir('', ws, has(path.join(ws, '.devpipe', 'pipes'), path.join(ws, 'pipes'))), path.join(ws, '.devpipe', 'pipes'));
  assert.equal(choosePipesDir('', ws, has(path.join(ws, 'pipes'))), path.join(ws, 'pipes'));
  assert.equal(choosePipesDir('', ws, has()), path.join(ws, '.devpipe', 'pipes'));
  assert.equal(choosePipesDir('', null, has()), null);
  assert.equal(choosePipesDir('/abs/pipes', null, has()), '/abs/pipes');
});
