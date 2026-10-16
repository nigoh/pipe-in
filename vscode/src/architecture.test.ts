// 構造の検査。AC-44：記録の読み取りと図の状態の組み立て（入口 src/extension.ts 以外のすべて）は vscode を import しない。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = path.dirname(fileURLToPath(import.meta.url));

function listTsFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listTsFiles(full));
    else if (entry.isFile() && entry.name.endsWith('.ts')) out.push(full);
  }
  return out;
}

function targets(): string[] {
  return listTsFiles(SRC).filter((file) => {
    const rel = path.relative(SRC, file).split(path.sep).join('/');
    if (rel === 'extension.ts') return false;
    if (rel.endsWith('.test.ts')) return false;
    if (rel.startsWith('test/')) return false;
    return true;
  });
}

const VSCODE_IMPORTS = [
  /from\s+['"]vscode['"]/,
  /import\(\s*['"]vscode['"]\s*\)/,
  /require\(\s*['"]vscode['"]\s*\)/,
];

test('AC-44: src/ の記録の読み取り・図の状態の組み立てのモジュールが vscode を import していない', () => {
  const files = targets();
  // 対象が1つもないときは失敗にする（設計書：テスト先行の時点では赤になる）
  assert.ok(files.length > 0, '検査する製品コードのモジュールが src/ にあること');
  // 少なくとも記録の読み取りと図の状態の組み立てのモジュールが対象に入っていること
  const rels = files.map((f) => path.relative(SRC, f).split(path.sep).join('/'));
  for (const required of ['domain/runRecord.ts', 'domain/stageLog.ts', 'domain/artifacts.ts', 'domain/pipelineView.ts']) {
    assert.ok(rels.includes(required), `${required} が検査の対象にあること`);
  }
  const offenders = files.filter((file) => {
    const text = readFileSync(file, 'utf8');
    return VSCODE_IMPORTS.some((re) => re.test(text));
  });
  assert.deepEqual(
    offenders.map((f) => path.relative(SRC, f)),
    [],
  );
});

// ---- D0002-AC-07: 層ごとに使ってよい node: の部品（docs/development/design.md の「拡張の層」） ----

const LAYER_NODE_IMPORTS: Record<string, string[]> = {
  domain: ['node:path'],
  app: ['node:path'],
  view: [],
  webview: [],
  infra: ['node:fs', 'node:fs/promises', 'node:os', 'node:path'],
};

/** 層の決まりに合わない import（「ファイル → 読み込んだもの」）。テストと test/ の補助は見ない */
export function layerViolations(files: { rel: string; source: string }[]): string[] {
  const out: string[] = [];
  for (const { rel, source } of files) {
    const layer = rel.split('/')[0]!;
    const allowed = LAYER_NODE_IMPORTS[layer];
    if (!allowed || rel.endsWith('.test.ts')) continue;
    for (const m of source.matchAll(/(?:from|import)\s*\(?\s*['"]([^'"]+)['"]/g)) {
      const target = m[1]!;
      const external = !target.startsWith('.');
      if (external && !allowed.includes(target)) out.push(`${rel} → ${target}`);
    }
  }
  return out;
}

test('D0002-AC-07: 層ごとに、使ってよい node: の部品だけを使う（外のパッケージも使わない）', () => {
  const files = targets().map((file) => ({
    rel: path.relative(SRC, file).split(path.sep).join('/'),
    source: readFileSync(file, 'utf8'),
  }));
  assert.deepEqual(layerViolations(files), []);
});

test('D0002-AC-07: 層の検査そのものが、決まりに合わない import を見つける', () => {
  const found = layerViolations([
    { rel: 'domain/a.ts', source: "import { readFile } from 'node:fs/promises';\nimport path from 'node:path';" },
    { rel: 'view/b.ts', source: "import path from 'node:path';" },
    { rel: 'webview/c.ts', source: "import x from 'some-package';" },
    { rel: 'infra/d.ts', source: "import { spawn } from 'node:child_process';" },
    { rel: 'app/e.ts', source: "import { x } from '../domain/x.ts';" },
    { rel: 'domain/f.test.ts', source: "import { readFile } from 'node:fs';" },
  ]);
  assert.deepEqual(found, ['domain/a.ts → node:fs/promises', 'view/b.ts → node:path', 'webview/c.ts → some-package', 'infra/d.ts → node:child_process']);
});
