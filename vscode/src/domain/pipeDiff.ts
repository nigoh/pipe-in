// 2つのパイプの形の差分の一覧（D0065）。外で書き換わったときに、作業台の帯に出す。
// 段は name で対応づける。つなぎの行き先は id でなく名前で比べる（読み込みのたびに id が変わっても、つなぎが同じなら差にしない）。
import { END, targetName } from './pipeModel.ts';
import type { FrameModel, PipeModel, StageModel } from './pipeModel.ts';

export type DiffKind = 'pipe' | 'stage-added' | 'stage-removed' | 'prompt' | 'flow' | 'setting' | 'layout';
/** target は段の name・枠の name・'pipe'。text は画面に出す短い文（外から来た文字を含む。出すときは escapeHtml） */
export interface DiffItem { kind: DiffKind; target: string; text: string }

export const DIFF_KIND_LABEL: Record<DiffKind, string> = {
  'pipe': 'パイプ',
  'stage-added': '段が増えた',
  'stage-removed': '段が減った',
  'prompt': '指示文',
  'flow': 'つなぎ',
  'setting': '設定',
  'layout': '位置',
};

const EXCERPT_MAX = 40;
/** 新しい指示文の先頭の 1 行を 40 字までに切った抜粋 */
const excerpt = (prompt: string): string => {
  const line = prompt.split(/\r?\n/)[0] ?? '';
  const cut = Array.from(line).slice(0, EXCERPT_MAX).join('');
  return cut.length < line.length ? `${cut}…` : cut;
};

// 段の設定として比べる項目から外すもの（id・位置・指示文・つなぎは別の種別で比べる）
const NOT_SETTING = new Set(['id', 'x', 'y', 'prompt', 'next', 'routes', 'onFail']);
const same = (a: unknown, b: unknown): boolean => JSON.stringify(a) === JSON.stringify(b);

function changedSettings(a: StageModel, b: StageModel): string[] {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  const rec = (s: StageModel): Record<string, unknown> => s as unknown as Record<string, unknown>;
  return [...keys].filter((k) => !NOT_SETTING.has(k) && !same(rec(a)[k], rec(b)[k]));
}

/** 段のつなぎ（行き先は名前）を 1 つの組にして返す */
const stageFlow = (m: PipeModel, s: StageModel): unknown => ({
  next: targetName(m, s.next),
  routes: s.routes.map((r) => [r.key, targetName(m, r.to)]),
  onFail: s.onFail === null ? null : targetName(m, s.onFail),
});
const frameFlow = (m: PipeModel, f: FrameModel): unknown => ({ next: f.next === null ? null : targetName(m, f.next) });

/** a（保存済みの形）から b（ディスクの今の形）への差分。同じ形どうしは [] */
export function diffPipes(a: PipeModel, b: PipeModel): DiffItem[] {
  const out: DiffItem[] = [];
  const add = (kind: DiffKind, target: string, text: string): void => { out.push({ kind, target, text }); };

  const pipeChanged = (['label', 'description', 'input', 'maxSteps'] as const).filter((k) => a[k] !== b[k]);
  if (pipeChanged.length) add('pipe', 'pipe', pipeChanged.join('・'));

  const aBy = new Map(a.stages.map((s) => [s.name, s]));
  const bBy = new Map(b.stages.map((s) => [s.name, s]));
  for (const s of b.stages) if (!aBy.has(s.name)) add('stage-added', s.name, s.label || s.name);
  for (const s of a.stages) if (!bBy.has(s.name)) add('stage-removed', s.name, s.label || s.name);

  for (const sb of b.stages) {
    const sa = aBy.get(sb.name);
    if (!sa) continue;
    if (sa.prompt !== sb.prompt) add('prompt', sb.name, excerpt(sb.prompt));
    if (!same(stageFlow(a, sa), stageFlow(b, sb))) add('flow', sb.name, `${targetName(b, sb.next)} へつなぐ`);
    const set = changedSettings(sa, sb);
    if (set.length) add('setting', sb.name, set.join('・'));
    if (sa.x !== sb.x || sa.y !== sb.y) add('layout', sb.name, '位置が変わった');
  }

  const fa = new Map(a.frames.map((f) => [f.name, f])), fb = new Map(b.frames.map((f) => [f.name, f]));
  for (const f of b.frames) {
    const o = fa.get(f.name);
    if (!o) { add('layout', f.name, '枠が増えた'); continue; }
    if (!same(frameFlow(a, o), frameFlow(b, f))) add('flow', f.name, `${f.next === null ? END : targetName(b, f.next)} へつなぐ`);
    if (o.x !== f.x || o.y !== f.y || o.w !== f.w || o.h !== f.h) add('layout', f.name, '位置・大きさが変わった');
  }
  for (const f of a.frames) if (!fb.has(f.name)) add('layout', f.name, '枠が減った');

  if (a.start.x !== b.start.x || a.start.y !== b.start.y) add('layout', 'start', '始まりの位置が変わった');
  if (a.end.x !== b.end.x || a.end.y !== b.end.y) add('layout', 'end', '終わりの位置が変わった');
  return out;
}
