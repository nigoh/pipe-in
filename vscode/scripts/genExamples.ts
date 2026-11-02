// 見本のデータを作る道具（D0070）：npm run examples:gen（vscode/ で）。
// リポジトリの examples/<名前>/pipes/pipe-in-*/ の pipe.toml と prompts/*.md だけを読み、src/domain/exampleData.ts を書く。
// README・layout.json は入れない。動画の見本（video）は ffmpeg などを要し、作業台では写せないので除く（truncate は pipes/ が無いので入らない）。
// 拡張の実行時のコードではない（実行時は examples/ を読まず、生成物だけを使う）。import しただけでは何も書かない。
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export interface ExampleData { name: string; files: Record<string, string> }

/** 見本から外すフォルダ（作業台で写せないもの・パイプの見本ではないもの） */
const SKIP = new Set(['video', 'truncate']);

const lf = (s: string): string => s.replace(/\r\n/g, '\n');
const isDir = (p: string): boolean => existsSync(p) && statSync(p).isDirectory();
const sorted = (xs: string[]): string[] => [...xs].sort();

/** examples/ の直下の見本を、名前順に読む（pipe.toml と prompts/*.md だけ。改行は LF にそろえる） */
export function buildExampleData(examplesDir: string): ExampleData[] {
  const out: ExampleData[] = [];
  for (const name of sorted(readdirSync(examplesDir))) {
    if (SKIP.has(name)) continue;
    const pipesDir = path.join(examplesDir, name, 'pipes');
    if (!isDir(pipesDir)) continue;
    const folder = sorted(readdirSync(pipesDir)).find((f) => f.startsWith('pipe-in-') && isDir(path.join(pipesDir, f)));
    if (folder === undefined) continue;
    const dir = path.join(pipesDir, folder);
    const tomlFile = path.join(dir, 'pipe.toml');
    if (!existsSync(tomlFile)) continue;
    const files: Record<string, string> = { 'pipe.toml': lf(readFileSync(tomlFile, 'utf8')) };
    const promptsDir = path.join(dir, 'prompts');
    if (isDir(promptsDir)) {
      for (const f of sorted(readdirSync(promptsDir))) {
        if (f.endsWith('.md')) files[`prompts/${f}`] = lf(readFileSync(path.join(promptsDir, f), 'utf8'));
      }
    }
    out.push({ name, files: Object.fromEntries(sorted(Object.keys(files)).map((k) => [k, files[k]!])) });
  }
  return out;
}

/** exampleData.ts の中身（JSON.stringify で書いた TS の文字。import は持たない） */
export function renderExampleModule(data: ExampleData[]): string {
  return [
    '// 作業台の「見本から作る」の見本のデータ。生成物なので直接直さない。',
    '// 元は リポジトリの見本のフォルダ。直したあとは、vscode/ で npm run examples:gen を流して作り直す。',
    '// 何も import しない（domain の層）。中身は pipe.toml と prompts/*.md だけで、改行は LF。',
    '',
    'export interface ExampleData { name: string; files: Record<string, string> }',
    '',
    `export const EXAMPLE_DATA: ExampleData[] = ${JSON.stringify(data, null, 2)};`,
    '',
  ].join('\n');
}

/** 直接実行されたときに、src/domain/exampleData.ts へ書く（書き込み先はこの 1 つだけ） */
function main(): void {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const data = buildExampleData(path.resolve(here, '..', '..', 'examples'));
  const target = path.resolve(here, '..', 'src', 'domain', 'exampleData.ts');
  writeFileSync(target, renderExampleModule(data), 'utf8');
  console.log(`見本 ${data.length} 件を ${path.relative(process.cwd(), target)} に書きました：${data.map((d) => d.name).join('、')}`);
}

if (process.argv[1] !== undefined && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
