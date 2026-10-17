// VersionStore の実装：node:fs/promises で、拡張の保存場所（storageUri の pipe-versions/）を読み書きする。
// 触れるのは根の中の pipe-in-<名前>/<版の id>.json だけ。プロジェクト（.pipe-in/pipes など）には書かない。
// 拡張の保存場所は前の版から引き継がないので、前の版のフォルダ名は受け付けない。
import { mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import type { VersionStore } from '../app/pipeVersions.ts';

const PIPE_DIR = /^pipe-in-[a-z0-9][a-z0-9-]*$/;
const FILE = /^\d{13}(-draft)?\.json$/;

export function createFsVersionStore(root: string): VersionStore {
  const base = path.resolve(root);
  const resolve = (pipe: string, file: string): string | null => {
    if (!PIPE_DIR.test(pipe) || !FILE.test(file)) return null;
    const full = path.resolve(base, pipe, file);
    return full.startsWith(base + path.sep) ? full : null;
  };
  const must = (pipe: string, file: string): string => {
    const full = resolve(pipe, file);
    if (full === null) throw new Error(`版の置き場所の決まったファイルの外には書けません（${pipe}/${file}）`);
    return full;
  };
  return {
    async list(pipe) {
      if (!PIPE_DIR.test(pipe)) return [];
      try {
        return (await readdir(path.join(base, pipe))).filter((f) => FILE.test(f)).sort();
      } catch {
        return [];
      }
    },
    async read(pipe, file) {
      const full = resolve(pipe, file);
      if (full === null) return null;
      try {
        return await readFile(full, 'utf8');
      } catch {
        return null;
      }
    },
    async write(pipe, file, text) {
      const full = must(pipe, file);
      await mkdir(path.dirname(full), { recursive: true });
      await writeFile(full, text, 'utf8');
    },
    async remove(pipe, file) {
      await rm(must(pipe, file), { force: true });
    },
  };
}
