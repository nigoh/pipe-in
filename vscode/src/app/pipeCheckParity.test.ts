// 検査の二重化（pipe-in-gen check の check_pipe と、作業台の validatePipe）の突き合わせ（D0061）。拡張側。
// 見本は tests/fixtures/check_parity/<ケース>/（リポジトリの根の1か所。Python のテスト tests/test_check_parity.py と同じもの）。
// ここは見本を読むだけで、書かない（偽の PipeStore は write・remove が呼ばれたら落とす）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadPipe, nameOfFolder } from './pipeEditor.ts';
import type { PipeStore } from './pipeEditor.ts';
import { validatePipe } from '../domain/pipeModel.ts';

const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'tests', 'fixtures', 'check_parity');

type Keyword = string | string[];
interface Expected { note: string; valid: boolean; errors: number; keywords: Keyword[]; only?: 'python' | 'extension'; reason?: string }

const caseNames = (): string[] => {
  if (!fs.existsSync(FIXTURES)) return [];
  return fs.readdirSync(FIXTURES, { withFileTypes: true }).filter((d) => d.isDirectory() && !d.name.startsWith('_')).map((d) => d.name).sort();
};
const CASES = caseNames();
const expectedOf = (name: string): Expected => JSON.parse(fs.readFileSync(path.join(FIXTURES, name, 'expected.json'), 'utf8')) as Expected;
const folderOf = (name: string): string => {
  const dirs = fs.readdirSync(path.join(FIXTURES, name), { withFileTypes: true }).filter((d) => d.isDirectory());
  assert.equal(dirs.length, 1, `${name} のパイプのフォルダが1つではありません`);
  return dirs[0]!.name;
};

/** ケースのフォルダを読むだけの PipeStore。write・remove は呼ばれたら落とす */
function caseStore(name: string): PipeStore {
  const base = path.join(FIXTURES, name);
  return {
    async listPipes() { return fs.readdirSync(base, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name); },
    async read(pipe, rel) {
      const p = path.join(base, pipe, rel);
      return fs.existsSync(p) && fs.statSync(p).isFile() ? fs.readFileSync(p, 'utf8') : null;
    },
    async listPrompts(pipe) {
      const dir = path.join(base, pipe, 'prompts');
      return fs.existsSync(dir) ? fs.readdirSync(dir).map((f) => `prompts/${f}`).sort() : [];
    },
    async write() { throw new Error('見本には書かない'); },
    async remove() { throw new Error('見本は消さない'); },
  };
}

async function extensionErrors(name: string): Promise<string[]> {
  const model = await loadPipe(caseStore(name), folderOf(name));
  return validatePipe(model).errors;
}

// ---- 突き合わせの規則（tests/test_check_parity.py にも同じものがある。_matcher.json で両側を確かめる） ----------------

const wordsOf = (keywords: Keyword[]): string[] => keywords.flatMap((k) => (typeof k === 'string' ? [k] : k));

/** 件数が等しい・各キーワード（配列はどれか1つ）を含む誤りがある・どの誤りもどれかのキーワードを含む */
function matches(errors: string[], expected: Pick<Expected, 'errors' | 'keywords'>): boolean {
  if (errors.length !== expected.errors) return false;
  for (const k of expected.keywords) {
    const alts = typeof k === 'string' ? [k] : k;
    if (!errors.some((e) => alts.some((a) => e.includes(a)))) return false;
  }
  const words = wordsOf(expected.keywords);
  return errors.every((e) => words.some((w) => e.includes(w)));
}

const describeMismatch = (name: string, errors: string[], expected: Expected): string =>
  [`${name}: 期待 ${expected.errors} 件・キーワード ${JSON.stringify(expected.keywords)}`, `実際 ${errors.length} 件`, ...errors.map((e) => `  - ${e}`)].join('\n');

test('D0061-AC-01: 見本が読め、ok-minimal を含み、only の無いケースが半分以上ある（読めず全部飛ばして通る、を防ぐ）', () => {
  assert.ok(CASES.length >= 30, `ケースが少なすぎる: ${CASES.length}`);
  assert.ok(CASES.includes('ok-minimal'));
  const both = CASES.filter((n) => expectedOf(n).only === undefined);
  assert.ok(both.length * 2 >= CASES.length, `両側で照らすケースが半分に満たない: ${both.length}/${CASES.length}`);
});

test('D0061-AC-19: matcher agrees with matcher.json（突き合わせの規則が Python 側とずれない）', () => {
  const table = JSON.parse(fs.readFileSync(path.join(FIXTURES, '_matcher.json'), 'utf8')) as { name: string; errors: string[]; expected: Pick<Expected, 'errors' | 'keywords'>; matches: boolean }[];
  assert.ok(table.length >= 8);
  const wrong = table.filter((t) => matches(t.errors, t.expected) !== t.matches).map((t) => t.name);
  assert.deepEqual(wrong, []);
});

for (const name of CASES) {
  const expected = expectedOf(name);
  if (expected.valid && expected.only !== 'python') {
    test(`D0061-AC-02: ok cases have no errors in the extension — ${name}`, async () => {
      assert.deepEqual(await extensionErrors(name), []);
    });
  }
  if (expected.only === undefined) {
    test(`D0061-AC-04: cases match expected in the extension — ${name}`, async () => {
      const errors = await extensionErrors(name);
      assert.ok(matches(errors, expected), describeMismatch(name, errors, expected));
    });
  }
  if (expected.only === 'extension') {
    test(`D0061-AC-18: extension-only cases match expected — ${name}`, async () => {
      const errors = await extensionErrors(name);
      assert.ok(matches(errors, expected), describeMismatch(name, errors, expected));
    });
  }
}

test('D0061-AC-14: legacy folder case loads through loadPipe（devpipe- の頭・kind 無しを、拡張も通す）', async () => {
  const folder = folderOf('ok-legacy-folder');
  assert.ok(folder.startsWith('devpipe-'));
  assert.equal(nameOfFolder(folder), 'old');
  const model = await loadPipe(caseStore('ok-legacy-folder'), folder);
  assert.equal(model.name, 'old');
  assert.equal(model.stages.length, 1);
  assert.deepEqual(validatePipe(model).errors, []);
});
