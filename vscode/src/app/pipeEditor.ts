// 作図台の読み込みと保存の手順。ファイルの置き場所は口 PipeStore の向こう（infra/fsPipes.ts）。
// 保存は pipe.toml・prompts/・layout.json を書き、使わなくなった指示を消す。README は無いときだけ作る。
import path from 'node:path';
import { PipeLoadError, isPipeName, orderStages, pipeFiles, pipeFromFiles } from '../domain/pipeModel.ts';
import type { PipeModel } from '../domain/pipeModel.ts';

export { isPipeName };

const PREFIX = 'devpipe-';

/** パイプの置き場所（.devpipe/pipes/ など）の中の devpipe-<名前>/ を読み書きする口。pipe はフォルダの名前（devpipe-<名前>）、rel はその中の相対パス */
export interface PipeStore {
  listPipes(): Promise<string[]>;
  read(pipe: string, rel: string): Promise<string | null>;
  listPrompts(pipe: string): Promise<string[]>;
  write(pipe: string, rel: string, text: string): Promise<void>;
  remove(pipe: string, rel: string): Promise<void>;
}

const folder = (name: string): string => `${PREFIX}${name}`;

/**
 * 作図台で読み書きするパイプの置き場所。設定（devpipe.pipesDir）があればそこ（相対ならワークスペースから）。
 * 無ければ、ワークスペースの .devpipe/pipes → pipes の、あるほう。どちらも無ければ .devpipe/pipes（devpipe-gen new の既定と同じ）。
 */
export function choosePipesDir(setting: string, workspace: string | null, exists: (dir: string) => boolean): string | null {
  if (setting && path.isAbsolute(setting)) return setting;
  if (!workspace) return null;
  if (setting) return path.join(workspace, setting);
  const project = path.join(workspace, '.devpipe', 'pipes');
  const legacy = path.join(workspace, 'pipes');
  if (exists(project)) return project;
  return exists(legacy) ? legacy : project;
}

/** pipe.toml を持つパイプの名前（devpipe- を除いたもの） */
export async function listPipes(store: PipeStore): Promise<string[]> {
  const names: string[] = [];
  for (const f of await store.listPipes()) {
    if (!f.startsWith(PREFIX) || !isPipeName(f.slice(PREFIX.length))) continue;
    if ((await store.read(f, 'pipe.toml')) !== null) names.push(f.slice(PREFIX.length));
  }
  return names.sort();
}

export async function loadPipe(store: PipeStore, name: string): Promise<PipeModel> {
  if (!isPipeName(name)) throw new PipeLoadError(`パイプの名前「${name}」は使えません`);
  const f = folder(name);
  const toml = await store.read(f, 'pipe.toml');
  if (toml === null) throw new PipeLoadError(`${f}/pipe.toml が見つかりません`);
  const prompts: Record<string, string> = {};
  for (const rel of await store.listPrompts(f)) {
    const text = await store.read(f, rel);
    if (text !== null) prompts[rel] = text;
  }
  return pipeFromFiles(name, toml, prompts, await store.read(f, 'layout.json'));
}

export function readmeFor(m: PipeModel): string {
  const need = m.input === 'required' ? ' --text "依頼メモ"' : m.input === 'optional' ? ' [--text "依頼メモ"]' : '';
  return [
    `# devpipe-${m.name}：${m.label}`,
    '',
    m.description,
    '',
    'パイプ作図台（VSCode の「devpipe: パイプを作図する」）で作ったパイプです。',
    '',
    '## 段',
    '',
    ...orderStages(m).map((s, i) => `${i + 1}. ${s.label}（${s.name}）→ \`${s.output}\``),
    '',
    '## 流し方',
    '',
    '```bash',
    `devpipe --pipe ${m.name} --project <対象のフォルダ>${need}`,
    '```',
    '',
    `直したら \`devpipe-gen check ${m.name} --project <対象のフォルダ>\` で確かめてください。`,
    '',
  ].join('\n');
}

/** 保存して、書いたファイル（相対パス）を返す */
export async function savePipe(store: PipeStore, m: PipeModel): Promise<string[]> {
  if (!isPipeName(m.name)) throw new Error(`パイプの名前「${m.name}」は使えません（英小文字・数字・- だけ）`);
  const f = folder(m.name);
  const files = pipeFiles(m);
  const written: string[] = [];
  for (const [rel, text] of Object.entries(files)) {
    await store.write(f, rel, text);
    written.push(rel);
  }
  for (const rel of await store.listPrompts(f)) if (!(rel in files)) await store.remove(f, rel);
  if ((await store.read(f, 'README.md')) === null) {
    await store.write(f, 'README.md', readmeFor(m));
    written.push('README.md');
  }
  return written;
}
