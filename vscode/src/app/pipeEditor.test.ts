// 作業台の読み込みと保存の手順（ファイルの置き場所は口 PipeStore の向こう）。
// 置き場所は .pipe-in/pipes/pipe-in-<名前>/ が今の形。前の版の .devpipe/pipes/・devpipe-<名前>/ も読み、直して保存すると元のフォルダに書く。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {
  LEGACY_PREFIX, PREFIX, choosePipesDirs, folderFor, isPipeName, listPipeRefs, loadPipe, nameOfFolder, pickPipes, promptRelFor, readmeFor, savePipe, saveTarget,
} from './pipeEditor.ts';
import type { PipeRef, PipeStore } from './pipeEditor.ts';
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
const byName = (refs: PipeRef[]) => [...refs].sort((a, b) => a.name.localeCompare(b.name));

test('D0006-AC-19: フォルダ名の頭は pipe-in-（新しい）と devpipe-（前の版）。名前とフォルダを読み替える', () => {
  assert.equal(PREFIX, 'pipe-in-');
  assert.equal(LEGACY_PREFIX, 'devpipe-');
  assert.equal(folderFor('one'), 'pipe-in-one');
  assert.equal(nameOfFolder('pipe-in-one'), 'one');
  assert.equal(nameOfFolder('devpipe-one'), 'one');
  for (const bad of ['one', 'other', 'pipe-in-', 'pipe-in', 'pipe-in-Bad', 'devpipe-../x', 'pipe-in-logs']) assert.equal(nameOfFolder(bad), null, bad);
});

test('AC-29・D0006-AC-19: pipe.toml のあるパイプ（pipe-in-<名前>・devpipe-<名前>）を一覧にする', async () => {
  const store = memoryStore({
    'pipe-in-one/pipe.toml': TOML, 'devpipe-two/pipe.toml': TOML, 'other/pipe.toml': TOML, 'pipe-in-empty/README.md': '',
  });
  const refs = byName(await listPipeRefs([{ dir: '/w/.pipe-in/pipes', store }]));
  assert.deepEqual(refs.map((r) => [r.name, r.folder]), [['one', 'pipe-in-one'], ['two', 'devpipe-two']]);
  assert.ok(refs.every((r) => r.dir === '/w/.pipe-in/pipes'));
});

test('D0006-AC-19: pickPipes は新しい置き場所・新しいフォルダ名を先に選ぶ（名前ごとに1つ）', () => {
  const NEW = '/w/.pipe-in/pipes', OLD = '/w/.devpipe/pipes';
  const refs = byName(pickPipes([
    { dir: NEW, folders: ['pipe-in-both', 'devpipe-same', 'pipe-in-same', 'other', 'pipe-in-Bad'] },
    { dir: OLD, folders: ['devpipe-both', 'devpipe-old', 'pipe-in-same'] },
  ]));
  assert.deepEqual(refs.map((r) => [r.name, r.dir, r.folder]), [
    ['both', NEW, 'pipe-in-both'], // 置き場所の順が先
    ['old', OLD, 'devpipe-old'], // 古い置き場所にしか無ければそれ
    ['same', NEW, 'pipe-in-same'], // 同じ置き場所では pipe-in- が先
  ]);
  const old = refs.find((r) => r.name === 'old')!;
  assert.equal(old.legacy, true);
  assert.equal(refs.find((r) => r.name === 'both')!.legacy, false);
});

test('AC-29・D0006-AC-19: 読み込み：フォルダ名で、pipe.toml と prompts/ と layout.json から', async () => {
  const store = memoryStore({ 'pipe-in-one/pipe.toml': TOML, 'pipe-in-one/prompts/01_a.md': 'A をする\n' });
  const m = await loadPipe(store, 'pipe-in-one');
  assert.equal(m.name, 'one');
  assert.equal(m.stages[0]!.prompt, 'A をする');
  assert.ok(m.stages[0]!.x > 0); // layout.json がないので自動で並べた
});

test('AC-30・D0006-AC-20: 保存：pipe.toml・prompts/・layout.json を書き、使わなくなった指示を消し、README は無いときだけ作る', async () => {
  const store = memoryStore({ 'pipe-in-one/pipe.toml': TOML, 'pipe-in-one/prompts/01_a.md': 'A をする\n', 'pipe-in-one/prompts/09_old.md': '古い\n' });
  const m = await loadPipe(store, 'pipe-in-one');
  m.stages[0]!.prompt = 'A を丁寧にする';
  const written = await savePipe(store, m, 'pipe-in-one');
  assert.ok(written.includes('pipe.toml') && written.includes('layout.json') && written.includes('prompts/01_a.md'));
  assert.equal(store.files['pipe-in-one/prompts/01_a.md'], 'A を丁寧にする\n');
  assert.equal(store.files['pipe-in-one/prompts/09_old.md'], undefined);
  assert.ok(store.files['pipe-in-one/README.md']!.includes('pipe-in --pipe one'));
  store.files['pipe-in-one/README.md'] = '# 手で書いた\n';
  await savePipe(store, m, 'pipe-in-one');
  assert.equal(store.files['pipe-in-one/README.md'], '# 手で書いた\n');
});

test('AC-30: 名前の決まりは本体と同じ。使えない名前は保存しない', async () => {
  assert.equal(isPipeName('my-pipe'), true);
  for (const bad of ['', 'Bad', '../x', 'logs', 'end', 'a/b']) assert.equal(isPipeName(bad), false, bad);
  const store = memoryStore();
  await assert.rejects(() => savePipe(store, newPipe('../escape'), folderFor('../escape')));
  assert.deepEqual(store.files, {});
});

test('D0006-AC-19: 新しいパイプは pipe-in-<名前>/ に書く', async () => {
  const store = memoryStore();
  await savePipe(store, newPipe('fresh'), folderFor('fresh'));
  assert.ok((store.files['pipe-in-fresh/pipe.toml'] ?? '').includes('[pipe]'), Object.keys(store.files).join(', '));
  assert.ok(Object.keys(store.files).every((k) => k.startsWith('pipe-in-fresh/')), Object.keys(store.files).join(', '));
});

test('D0006-AC-19: 古いフォルダのパイプを保存すると、そのフォルダだけが変わる（pipe-in-<名前>/ は作らない）', async () => {
  const store = memoryStore({
    'devpipe-old/pipe.toml': TOML, 'devpipe-old/prompts/01_a.md': 'A をする\n', 'devpipe-old/README.md': '# 前の版\n',
  });
  const m = await loadPipe(store, 'devpipe-old');
  assert.equal(m.name, 'old');
  m.stages[0]!.prompt = 'A を直した';
  await savePipe(store, m, 'devpipe-old');
  assert.equal(store.files['devpipe-old/prompts/01_a.md'], 'A を直した\n');
  assert.equal(store.files['devpipe-old/README.md'], '# 前の版\n');
  assert.deepEqual(Object.keys(store.files).filter((k) => !k.startsWith('devpipe-old/')), []);
});

test('D0006-AC-19: saveTarget は、開いたパイプは元のフォルダへ、新しい・名前を変えたパイプは最初の置き場所の pipe-in-<名前>/ へ', () => {
  const NEW = '/w/.pipe-in/pipes', OLD = '/w/.devpipe/pipes';
  const old: PipeRef = { name: 'old', dir: OLD, folder: 'devpipe-old', legacy: true };
  const refs = [old];
  assert.deepEqual(saveTarget(refs, old, 'old', [NEW, OLD]), { dir: OLD, folder: 'devpipe-old' });
  assert.deepEqual(saveTarget(refs, null, 'fresh', [NEW, OLD]), { dir: NEW, folder: 'pipe-in-fresh' });
  assert.deepEqual(saveTarget(refs, old, 'renamed', [NEW, OLD]), { dir: NEW, folder: 'pipe-in-renamed' });
});

test('D0006-AC-19: saveTarget はほかの置き場所に同じ名前があれば断る', () => {
  const NEW = '/w/.pipe-in/pipes', OLD = '/w/.devpipe/pipes';
  const old: PipeRef = { name: 'old', dir: OLD, folder: 'devpipe-old', legacy: true };
  const other: PipeRef = { name: 'other', dir: NEW, folder: 'pipe-in-other', legacy: false };
  const fresh = saveTarget([old, other], null, 'old', [NEW, OLD]);
  assert.ok('error' in fresh && fresh.error.includes('devpipe-old'), JSON.stringify(fresh));
  const renamed = saveTarget([old, other], other, 'old', [NEW, OLD]);
  assert.ok('error' in renamed, JSON.stringify(renamed));
});

test('D0006-AC-20: README の下書きは pipe-in のコマンドで、devpipe を含まない', () => {
  const m = newPipe('one');
  const text = readmeFor(m, 'pipe-in-one');
  assert.match(text, /^# pipe-in-one：/);
  assert.ok(text.includes('pipe-in --pipe one'), text);
  assert.ok(text.includes('pipe-in-gen check one'), text);
  assert.ok(text.includes('pipe-in: パイプ作業台を開く'), text);
  assert.doesNotMatch(text, /devpipe/i);
});

test('D0006-AC-20: README の下書きの見出しは、実際のフォルダ名', () => {
  assert.match(readmeFor(newPipe('old'), 'devpipe-old'), /^# devpipe-old：/);
});

test('AC-17・D0006-AC-18: 作業台の置き場所は、設定があればそれだけ。無ければ .pipe-in/pipes・.devpipe/pipes のあるもの → pipes → .pipe-in/pipes', () => {
  const ws = '/work/app';
  const NEW = path.join(ws, '.pipe-in', 'pipes'), OLD = path.join(ws, '.devpipe', 'pipes'), REPO = path.join(ws, 'pipes');
  const has = (...dirs: string[]) => (p: string) => dirs.includes(p);
  assert.deepEqual(choosePipesDirs('/abs/pipes', ws, has(NEW, OLD)), ['/abs/pipes']);
  assert.deepEqual(choosePipesDirs('my-pipes', ws, has(NEW)), [path.join(ws, 'my-pipes')]);
  assert.deepEqual(choosePipesDirs('', ws, has(NEW, OLD, REPO)), [NEW, OLD]);
  assert.deepEqual(choosePipesDirs('', ws, has(OLD, REPO)), [OLD]);
  assert.deepEqual(choosePipesDirs('', ws, has(NEW)), [NEW]);
  assert.deepEqual(choosePipesDirs('', ws, has(REPO)), [REPO]);
  assert.deepEqual(choosePipesDirs('', ws, has()), [NEW]);
  assert.deepEqual(choosePipesDirs('', null, has()), []);
  assert.deepEqual(choosePipesDirs('/abs/pipes', null, has()), ['/abs/pipes']);
});

test('AC-72: 指示文を開くパスは、保存済みのモデルの段の name から決める（無い name は断る）', async () => {
  const two = TOML + '\n[[stages]]\nname = "b"\nlabel = "B"\noutput = "b.md"\naccess = "read"\nprompt_file = "prompts/02_b.md"\n';
  const store = memoryStore({ 'pipe-in-one/pipe.toml': two, 'pipe-in-one/prompts/01_a.md': 'A\n', 'pipe-in-one/prompts/02_b.md': 'B\n' });
  const saved = await loadPipe(store, 'pipe-in-one');
  assert.equal(promptRelFor(saved, 'a'), 'prompts/01_a.md');
  assert.equal(promptRelFor(saved, 'b'), 'prompts/02_b.md');
  assert.equal(promptRelFor(saved, 'c'), null);
  assert.equal(promptRelFor(saved, '../a'), null);
});
