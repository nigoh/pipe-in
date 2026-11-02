// 見本のデータ（domain/exampleData.ts）と、見本の一覧・モデルを作る関数（domain/pipeExamples.ts）、生成の道具（scripts/genExamples.ts）（D0070）。
// 見本の中身は examples/ から作った生成物で、examples/ と一字も違わないことをここで見張る。
// 新しいファイルが無いあいだは「まだ作っていない」で落とす。実行時のコードが examples/ を読まないことの検査（AC-22）と、その検査そのものの検査は今のまま通る（守る）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { pipeFromFiles, targetName, validatePipe } from './pipeModel.ts';

const SRC = fileURLToPath(new URL('..', import.meta.url));
const EXAMPLES_DIR = fileURLToPath(new URL('../../../examples', import.meta.url));
const NAMES = ['diagrams', 'research', 'spec-qa'] as const; // 名前順

interface ExampleData { name: string; files: Record<string, string> }
interface ExampleSummary { name: string; label: string; description: string; stages: number; budgetTotal: number }

function needFile(rel: string): string {
  const file = path.join(SRC, rel);
  assert.ok(existsSync(file), `${rel} が無い（まだ作っていない）`);
  return file;
}
async function data(): Promise<ExampleData[]> {
  needFile('domain/exampleData.ts');
  return ((await import('./exampleData.ts')) as { EXAMPLE_DATA: ExampleData[] }).EXAMPLE_DATA;
}
async function api() {
  needFile('domain/pipeExamples.ts');
  return (await import('./pipeExamples.ts')) as unknown as {
    listExamples(d?: ExampleData[]): ExampleSummary[];
    findExample(name: string, d?: ExampleData[]): ExampleData | undefined | null;
    exampleModel(ex: ExampleData, name: string): ReturnType<typeof pipeFromFiles>;
  };
}
async function gen() {
  const file = path.join(SRC, '..', 'scripts', 'genExamples.ts');
  assert.ok(existsSync(file), 'scripts/genExamples.ts が無い（まだ作っていない）');
  return (await import('../../scripts/genExamples.ts')) as unknown as {
    buildExampleData(dir: string): ExampleData[];
    renderExampleModule(d: ExampleData[]): string;
  };
}

const promptsOf = (files: Record<string, string>): Record<string, string> => Object.fromEntries(Object.entries(files).filter(([k]) => k.startsWith('prompts/')));
const lf = (s: string): string => s.replace(/\r\n/g, '\n');

// 設計 2 節の表：見本 → 段（名前・access・上限・戻り先）
const EXPECT: Record<string, { name: string; access: string; budget: number; onFail?: string }[]> = {
  diagrams: [
    { name: 'survey', access: 'read', budget: 1.0 },
    { name: 'draw', access: 'docs', budget: 2.0 },
    { name: 'verify', access: 'read', budget: 1.0, onFail: 'draw' },
  ],
  'spec-qa': [
    { name: 'trace', access: 'read', budget: 1.5 },
    { name: 'gaps', access: 'read', budget: 1.5 },
    { name: 'qa', access: 'read', budget: 1.5 },
  ],
  research: [
    { name: 'frame', access: 'read', budget: 0.5 },
    { name: 'gather', access: 'read', budget: 2.0 },
    { name: 'summarize', access: 'docs', budget: 1.0 },
    { name: 'verify', access: 'read', budget: 1.5, onFail: 'summarize' },
  ],
};
const TOTAL: Record<string, number> = { diagrams: 4.0, 'spec-qa': 4.5, research: 5.0 };

// ---- AC-19：生成物が examples/ と一字も違わない ----

test('D0070-AC-19: 見本のデータがexamplesと一字も違わない（データの深い比較＋生成した文字とコミットした文字の比較）', async () => {
  const committed = await data();
  const { buildExampleData, renderExampleModule } = await gen();
  const built = buildExampleData(EXAMPLES_DIR);
  assert.deepEqual(committed, built, 'examples/ を直したのに npm run examples:gen を流していない');
  const text = lf(readFileSync(needFile('domain/exampleData.ts'), 'utf8'));
  assert.equal(text, lf(renderExampleModule(built)), 'domain/exampleData.ts が生成の結果と違う（npm run examples:gen を流す）');
});

test('D0070-AC-19: 見本は 3 つ（名前順）で、files の鍵は文字列順。先頭に「npm run examples:gen で作る」の注意', async () => {
  const committed = await data();
  assert.deepEqual(committed.map((e) => e.name), [...NAMES]);
  for (const e of committed) assert.deepEqual(Object.keys(e.files), Object.keys(e.files).sort(), `${e.name}: files の鍵の順`);
  const head = readFileSync(needFile('domain/exampleData.ts'), 'utf8').split('\n').slice(0, 5).join('\n');
  assert.match(head, /examples:gen/);
});

test('D0070-AC-19: データの中身に \\r が入らない（Windows の改行変換で落ちない）。生成の道具は CRLF を LF にそろえる', async () => {
  for (const e of await data()) for (const [rel, text] of Object.entries(e.files)) assert.ok(!text.includes('\r'), `${e.name}/${rel}`);
  const { buildExampleData } = await gen();
  const root = mkdtempSync(path.join(tmpdir(), 'ex-'));
  const dir = path.join(root, 'foo', 'pipes', 'pipe-in-foo');
  mkdirSync(path.join(dir, 'prompts'), { recursive: true });
  writeFileSync(path.join(dir, 'pipe.toml'), '[pipe]\r\nlabel = "x"\r\n');
  writeFileSync(path.join(dir, 'prompts', '01_a.md'), 'A\r\nをする\r\n');
  const [one] = buildExampleData(root);
  assert.deepEqual(one, { name: 'foo', files: { 'pipe.toml': '[pipe]\nlabel = "x"\n', 'prompts/01_a.md': 'A\nをする\n' } });
});

// ---- AC-20：pipeFromFiles で読め、validatePipe の誤りが 0 件 ----

test('D0070-AC-20: 見本はpipeFromFilesで読めvalidatePipeの誤りが0件で段が同じ（名前・access・上限・戻り先）', async () => {
  const committed = await data();
  for (const ex of committed) {
    const m = pipeFromFiles(ex.name, ex.files['pipe.toml']!, promptsOf(ex.files), null);
    assert.deepEqual(validatePipe(m).errors, [], ex.name);
    const want = EXPECT[ex.name]!;
    assert.deepEqual(m.stages.map((s) => s.name), want.map((w) => w.name), `${ex.name}: 段の並び`);
    assert.deepEqual(m.stages.map((s) => s.access), want.map((w) => w.access), `${ex.name}: access`);
    assert.deepEqual(m.stages.map((s) => s.maxBudget), want.map((w) => w.budget), `${ex.name}: max_budget_usd`);
    assert.ok(m.stages.every((s) => s.maxTurns > 0 && s.maxTurns < 100 && s.prompt.length > 0), `${ex.name}: max_turns・指示文`);
    assert.deepEqual(m.stages.map((s) => (s.onFail ? targetName(m, s.onFail) : undefined)), want.map((w) => w.onFail), `${ex.name}: 戻り先`);
  }
});

// ---- AC-21：データに入れるのは pipe.toml と prompts/*.md だけ ----

test('D0070-AC-21: データにはpipe_tomlとprompts_mdだけ（README・layout.json は入れない）。指示文の数は段の数', async () => {
  for (const ex of await data()) {
    const keys = Object.keys(ex.files);
    assert.ok(keys.includes('pipe.toml'), `${ex.name}: pipe.toml`);
    assert.ok(keys.every((k) => k === 'pipe.toml' || /^prompts\/[^/]+\.md$/.test(k)), `${ex.name}: ${keys.join(',')}`);
    const m = pipeFromFiles(ex.name, ex.files['pipe.toml']!, promptsOf(ex.files), null);
    assert.equal(keys.length - 1, m.stages.length, `${ex.name}: 指示文の数と段の数`);
  }
});

test('D0070-AC-21: 生成の道具は README・layout.json・prompts 以外のファイルを読まない（pipe-in-* の見本だけを対象にする）', async () => {
  const { buildExampleData } = await gen();
  const root = mkdtempSync(path.join(tmpdir(), 'ex-'));
  const dir = path.join(root, 'bar', 'pipes', 'pipe-in-bar');
  mkdirSync(path.join(dir, 'prompts'), { recursive: true });
  writeFileSync(path.join(dir, 'pipe.toml'), '[pipe]\nlabel = "b"\n');
  writeFileSync(path.join(dir, 'README.md'), '# b\n');
  writeFileSync(path.join(dir, 'layout.json'), '{}');
  writeFileSync(path.join(dir, 'prompts', '01_a.md'), 'A\n');
  writeFileSync(path.join(dir, 'prompts', 'memo.txt'), 'x');
  const out = buildExampleData(root);
  assert.deepEqual(out.map((e) => [e.name, Object.keys(e.files).sort()]), [['bar', ['pipe.toml', 'prompts/01_a.md']]]);
});

// ---- AC-22：実行時のコードが examples/ を読まない ----

/** 行コメント・ブロックコメントを消す（文字列の中の // は壊さない程度のごく簡単なもの） */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`\\])\/\/.*$/gm, '$1');
}
/** 'examples' というパス部品（引用符・スラッシュで区切られた examples）を持つか */
const readsExamples = (source: string): boolean => /['"`/\\]examples['"`/\\]/.test(stripComments(source));

function runtimeFiles(dir: string): string[] {
  const out: string[] = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...runtimeFiles(p));
    else if (e.name.endsWith('.ts') && !e.name.endsWith('.test.ts') && e.name !== 'exampleData.ts') out.push(p);
  }
  return out;
}

test('D0070-AC-22: 実行時のコードがexamplesを読まない（vscode/src/ の非テストの .ts に examples のパス部品がない。exampleData.ts を除く）', () => {
  const bad = runtimeFiles(SRC).filter((f) => readsExamples(readFileSync(f, 'utf8'))).map((f) => path.relative(SRC, f));
  assert.deepEqual(bad, []);
});

test('D0070-AC-22: 検査そのものが、examples を読む書き方を見つけ、コメントや別の語は見逃す（今のまま通る）', () => {
  assert.equal(readsExamples("path.join(root, 'examples', 'x')"), true);
  assert.equal(readsExamples('readFileSync("../examples/diagrams/pipe.toml")'), true);
  assert.equal(readsExamples('// examples/ から生成する\nconst a = 1;'), false);
  assert.equal(readsExamples("const label = 'my-examples-list';"), false);
});

// ---- AC-23：一覧 ----

function fake(name: string, label: string, description: string, budgets: (number | null)[]): ExampleData {
  const stages = budgets.map((b, i) => `[[stages]]\nname = "s${i + 1}"\nlabel = "S${i + 1}"\noutput = "0${i + 1}_s.md"\naccess = "read"\nprompt_file = "prompts/0${i + 1}_s${i + 1}.md"\n${b === null ? '' : `max_budget_usd = ${b}\n`}`);
  const files: Record<string, string> = { 'pipe.toml': `[pipe]\nkind = "linear"\nlabel = "${label}"\ndescription = "${description}"\n\n${stages.join('\n')}` };
  budgets.forEach((_, i) => { files[`prompts/0${i + 1}_s${i + 1}.md`] = `S${i + 1} をする\n`; });
  return { name, files };
}

test('D0070-AC-23: 一覧は名前順で名前_ラベル_説明_段の数_上限の合計を返し_空なら空', async () => {
  const { listExamples, findExample } = await api();
  const given = [fake('zeta', 'ゼータ', 'z の説明', [1.5, 2.0]), fake('alpha', 'アルファ', 'a の説明', [0.5, null, 1.0])];
  assert.deepEqual(listExamples(given), [
    { name: 'alpha', label: 'アルファ', description: 'a の説明', stages: 3, budgetTotal: 1.5 }, // 上限のない段は 0
    { name: 'zeta', label: 'ゼータ', description: 'z の説明', stages: 2, budgetTotal: 3.5 },
  ]);
  assert.deepEqual(listExamples([]), []);
  assert.equal(findExample('zeta', given)?.name, 'zeta');
  assert.ok(!findExample('nothing', given));
});

test('D0070-AC-23: 組み込みの見本は 3 つ（名前順）で、段の数と上限の合計が設計の表のとおり', async () => {
  const { listExamples } = await api();
  const list = listExamples();
  assert.deepEqual(list.map((x) => x.name), [...NAMES]);
  for (const x of list) {
    assert.equal(x.stages, EXPECT[x.name]!.length, `${x.name}: 段の数`);
    assert.ok(Math.abs(x.budgetTotal - TOTAL[x.name]!) < 1e-9, `${x.name}: 上限の合計 ${x.budgetTotal}`);
    assert.ok(x.label.length > 0 && x.description.length > 0, `${x.name}: ラベルと説明`);
  }
});

test('D0070-AC-23: exampleModel は名前を渡した名前にし、段・指示文は見本のとおり', async () => {
  const { exampleModel } = await api();
  const ex = fake('src', 'ラベル', '説明', [1.0, 2.0]);
  const m = exampleModel(ex, 'mine');
  assert.equal(m.name, 'mine');
  assert.deepEqual(m.stages.map((s) => s.name), ['s1', 's2']);
  assert.deepEqual(m.stages.map((s) => s.prompt), ['S1 をする', 'S2 をする']);
});

// ---- AC-33：層の向き ----

const specifiers = (source: string): string[] => Array.from(stripComments(source).matchAll(/(?:\bfrom|\bimport)\s*\(?\s*['"]([^'"]+)['"]/g), (m) => m[1]!);

test('D0070-AC-33: exampleData_tsは何もimportしない。pipeExamples.ts は ./pipeModel.ts・./exampleData.ts・node:path だけ', () => {
  const dataSrc = readFileSync(needFile('domain/exampleData.ts'), 'utf8');
  assert.deepEqual(specifiers(dataSrc), []);
  assert.ok(!/^\s*import\b/m.test(stripComments(dataSrc)));
  const apiSrc = readFileSync(needFile('domain/pipeExamples.ts'), 'utf8');
  assert.deepEqual(specifiers(apiSrc).filter((s) => !['./pipeModel.ts', './exampleData.ts', 'node:path'].includes(s)), []);
  assert.ok(!/['"]vscode['"]/.test(apiSrc));
});
