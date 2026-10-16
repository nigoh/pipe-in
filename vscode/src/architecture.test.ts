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
