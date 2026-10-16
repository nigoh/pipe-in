// PipeStore の実装：node:fs/promises で、パイプの置き場所（.devpipe/pipes/ など）を読み書きする。
// 触れるのは置き場所の中の devpipe-<名前>/ の pipe.toml・layout.json・README.md・prompts/*.md だけ。ほかは読まず、書かない。
import { mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import type { PipeStore } from '../app/pipeEditor.ts';

const PIPE_DIR = /^devpipe-[a-z0-9][a-z0-9-]*$/;
const FIXED = new Set(['pipe.toml', 'layout.json', 'README.md']);
const PROMPT = /^prompts\/[A-Za-z0-9_][A-Za-z0-9_.-]*\.md$/;

const allowedRel = (rel: string): boolean => FIXED.has(rel) || (PROMPT.test(rel) && !rel.includes('..'));

export function createFsPipeStore(pipesDir: string): PipeStore {
  const root = path.resolve(pipesDir);
  const resolve = (pipe: string, rel: string): string | null => {
    if (!PIPE_DIR.test(pipe) || !allowedRel(rel)) return null;
    const file = path.resolve(root, pipe, ...rel.split('/'));
    return file.startsWith(root + path.sep) ? file : null;
  };
  const must = (pipe: string, rel: string): string => {
    const file = resolve(pipe, rel);
    if (file === null) throw new Error(`パイプの置き場所の決まったファイルの外には書けません（${pipe}/${rel}）`);
    return file;
  };
  return {
    async listPipes() {
      try {
        const entries = await readdir(root, { withFileTypes: true });
        return entries.filter((e) => e.isDirectory() && PIPE_DIR.test(e.name)).map((e) => e.name).sort();
      } catch {
        return [];
      }
    },
    async read(pipe, rel) {
      const file = resolve(pipe, rel);
      if (file === null) return null;
      try {
        return await readFile(file, 'utf8');
      } catch {
        return null;
      }
    },
    async listPrompts(pipe) {
      if (!PIPE_DIR.test(pipe)) return [];
      try {
        const names = await readdir(path.join(root, pipe, 'prompts'));
        return names.map((n) => `prompts/${n}`).filter(allowedRel).sort();
      } catch {
        return [];
      }
    },
    async write(pipe, rel, text) {
      const file = must(pipe, rel);
      await mkdir(path.dirname(file), { recursive: true });
      await writeFile(file, text, 'utf8');
    },
    async remove(pipe, rel) {
      if (!PROMPT.test(rel)) throw new Error(`消せるのは prompts/ の指示ファイルだけです（${rel}）`);
      await rm(must(pipe, rel), { force: true });
    },
  };
}
