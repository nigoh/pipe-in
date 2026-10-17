// 作業台の読み込みと保存の手順。ファイルの置き場所は口 PipeStore の向こう（infra/fsPipes.ts）。
// 保存は pipe.toml・prompts/・layout.json を書き、使わなくなった指示を消す。README は無いときだけ作る。
// 今の形は .pipe-in/pipes/pipe-in-<名前>/。前の版の置き場所・フォルダ名も読み、直して保存すると元のフォルダに書く。
import path from 'node:path';
import { PipeLoadError, isPipeName, orderStages, pipeFiles, pipeFromFiles, promptPath } from '../domain/pipeModel.ts';
import type { PipeModel } from '../domain/pipeModel.ts';

export { isPipeName };

/** 新しく作るパイプのフォルダ名の頭 */
export const PREFIX = 'pipe-in-';
/** 前の版のフォルダ名の頭（読むだけ。新しくは作らない） */
export const LEGACY_PREFIX = 'devpipe-';
/** 同じ置き場所に両方あれば、この順に選ぶ */
const PREFIXES = [PREFIX, LEGACY_PREFIX] as const;

/** 置き場所の中のパイプの1つ。name は頭を除いた名前、dir は置き場所、folder はその中のフォルダ名。legacy は前の版の名前か */
export interface PipeRef { name: string; dir: string; folder: string; legacy: boolean }

/** パイプの置き場所（.pipe-in/pipes/ など）の中のパイプのフォルダを読み書きする口。pipe はフォルダの名前（pipe-in-<名前> など）、rel はその中の相対パス */
export interface PipeStore {
  listPipes(): Promise<string[]>;
  read(pipe: string, rel: string): Promise<string | null>;
  listPrompts(pipe: string): Promise<string[]>;
  write(pipe: string, rel: string, text: string): Promise<void>;
  remove(pipe: string, rel: string): Promise<void>;
}

/** 新しく作るときのフォルダ名（pipe-in-<名前>） */
export function folderFor(name: string): string {
  return PREFIX + name;
}

/** フォルダ名から名前を読む。どちらかの頭で始まり、残りが使える名前のときだけ。ほかは null */
export function nameOfFolder(folder: string): string | null {
  for (const p of PREFIXES) {
    if (folder.startsWith(p) && isPipeName(folder.slice(p.length))) return folder.slice(p.length);
  }
  return null;
}

/** 前の版の置き場所の、ワークスペースの中のフォルダ */
const LEGACY_PIPES_DIR = ['.devpipe', 'pipes'] as const;

/** 前の版の置き場所（<ワークスペース>/.devpipe/pipes）か */
function isLegacyDir(dir: string): boolean {
  return path.basename(dir) === LEGACY_PIPES_DIR[1] && path.basename(path.dirname(dir)) === LEGACY_PIPES_DIR[0];
}

/**
 * 作業台で読み書きするパイプの置き場所（前のものほど先に探す）。設定（pipe-in.pipesDir）があればそれだけ（相対ならワークスペースから）。
 * 無ければ、ワークスペースの .pipe-in/pipes・前の版の置き場所のうち、あるもの（この順）。どちらも無くて pipes があれば pipes。
 * 何も無ければ .pipe-in/pipes（pipe-in-gen new の既定と同じ）。ワークスペースも絶対パスの設定も無ければ空。
 */
export function choosePipesDirs(setting: string, workspace: string | null, exists: (dir: string) => boolean): string[] {
  if (setting && path.isAbsolute(setting)) return [setting];
  if (!workspace) return [];
  if (setting) return [path.join(workspace, setting)];
  const project = path.join(workspace, '.pipe-in', 'pipes');
  const legacy = path.join(workspace, ...LEGACY_PIPES_DIR);
  const found = [project, legacy].filter((d) => exists(d));
  if (found.length) return found;
  const repo = path.join(workspace, 'pipes');
  return exists(repo) ? [repo] : [project];
}

/** 置き場所ごとのフォルダの一覧から、名前ごとに1つ選ぶ（置き場所の順 → 同じ置き場所では頭の順）。名前の順に並べて返す */
export function pickPipes(found: { dir: string; folders: string[] }[]): PipeRef[] {
  const picked = new Map<string, PipeRef>();
  for (const { dir, folders } of found) {
    for (const p of PREFIXES) {
      for (const folder of folders) {
        if (!folder.startsWith(p)) continue;
        const name = nameOfFolder(folder);
        if (name === null || picked.has(name)) continue;
        picked.set(name, { name, dir, folder, legacy: p === LEGACY_PREFIX || isLegacyDir(dir) });
      }
    }
  }
  return [...picked.values()].sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}

/** 置き場所ごとの口から、pipe.toml を持つパイプだけを選んで一覧にする */
export async function listPipeRefs(shelves: { dir: string; store: PipeStore }[]): Promise<PipeRef[]> {
  const found: { dir: string; folders: string[] }[] = [];
  for (const { dir, store } of shelves) {
    const folders: string[] = [];
    for (const f of await store.listPipes()) {
      if (nameOfFolder(f) !== null && (await store.read(f, 'pipe.toml')) !== null) folders.push(f);
    }
    found.push({ dir, folders });
  }
  return pickPipes(found);
}

/** フォルダ（pipe-in-<名前> か前の版の名前）からパイプを読む。モデルの名前は頭を除いたもの */
export async function loadPipe(store: PipeStore, folder: string): Promise<PipeModel> {
  const name = nameOfFolder(folder);
  if (name === null) throw new PipeLoadError(`パイプのフォルダ「${folder}」は読めません`);
  const toml = await store.read(folder, 'pipe.toml');
  if (toml === null) throw new PipeLoadError(`${folder}/pipe.toml が見つかりません`);
  const prompts: Record<string, string> = {};
  for (const rel of await store.listPrompts(folder)) {
    const text = await store.read(folder, rel);
    if (text !== null) prompts[rel] = text;
  }
  return pipeFromFiles(name, toml, prompts, await store.read(folder, 'layout.json'));
}

/**
 * 保存先を決める。開いたパイプ（opened）と同じ名前なら、そのフォルダ（前の版のフォルダでもそのまま）。
 * 新しい・名前を変えたパイプは、最初の置き場所の pipe-in-<名前>/。ほかに同じ名前のパイプがあれば断る（pipe-in-gen new と同じ決まり）。
 */
export function saveTarget(refs: PipeRef[], opened: PipeRef | null, name: string, dirs: string[]): { dir: string; folder: string } | { error: string } {
  if (opened && opened.name === name) return { dir: opened.dir, folder: opened.folder };
  if (!isPipeName(name)) return { error: `パイプの名前「${name}」は使えません（英小文字・数字・- だけ）` };
  const clash = refs.find((r) => r.name === name && r !== opened);
  if (clash) return { error: `同じ名前のパイプが ${path.join(clash.dir, clash.folder)} にあります。そちらを開いて直すか、別の名前にしてください` };
  const dir = dirs[0];
  if (dir === undefined) return { error: 'パイプの置き場所が決まっていません' };
  return { dir, folder: folderFor(name) };
}

/** パイプの README の下書き。見出しは実際のフォルダ名 */
export function readmeFor(m: PipeModel, folder: string): string {
  const need = m.input === 'required' ? ' --text "依頼メモ"' : m.input === 'optional' ? ' [--text "依頼メモ"]' : '';
  return [
    `# ${folder}：${m.label}`,
    '',
    m.description,
    '',
    'パイプ作業台（VSCode の「pipe-in: パイプ作業台を開く」）で作ったパイプです。',
    '',
    '## 段',
    '',
    ...orderStages(m).map((s, i) => `${i + 1}. ${s.label}（${s.name}）→ \`${s.output}\``),
    '',
    '## 流し方',
    '',
    '```bash',
    `pipe-in --pipe ${m.name} --project <対象のフォルダ>${need}`,
    '```',
    '',
    `直したら \`pipe-in-gen check ${m.name} --project <対象のフォルダ>\` で確かめてください。`,
    '',
  ].join('\n');
}

/** フォルダ（saveTarget で決めたもの）に保存して、書いたファイル（相対パス）を返す */
export async function savePipe(store: PipeStore, m: PipeModel, folder: string): Promise<string[]> {
  if (!isPipeName(m.name)) throw new Error(`パイプの名前「${m.name}」は使えません（英小文字・数字・- だけ）`);
  if (nameOfFolder(folder) !== m.name) throw new Error(`パイプ「${m.name}」をフォルダ「${folder}」には保存できません`);
  const files = pipeFiles(m);
  const written: string[] = [];
  for (const [rel, text] of Object.entries(files)) {
    await store.write(folder, rel, text);
    written.push(rel);
  }
  for (const rel of await store.listPrompts(folder)) if (!(rel in files)) await store.remove(folder, rel);
  if ((await store.read(folder, 'README.md')) === null) {
    await store.write(folder, 'README.md', readmeFor(m, folder));
    written.push('README.md');
  }
  return written;
}

/** 保存済みのモデル saved で、段 name の指示文のファイル（prompts/NN_name.md）。その段が無ければ null */
export function promptRelFor(saved: PipeModel, name: string): string | null {
  const ord = orderStages(saved), i = ord.findIndex((s) => s.name === name);
  return i < 0 ? null : promptPath(ord[i]!, i);
}
