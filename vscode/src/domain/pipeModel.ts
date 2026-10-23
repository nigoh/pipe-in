// 作業台のモデル：パイプ（pipe.toml・prompts/・layout.json）と、路線図の上のブロック・枠・つなぎの行き来。
// 純粋な関数だけ（ファイル・vscode に触れない）。検査の決まりは pipe-in-gen check（pipe_in/pipe/definition.py）に合わせる。
import { TomlError, parseToml } from './toml.ts';
import type { TomlTable, TomlValue } from './toml.ts';

export type BlockKind = 'research' | 'agent' | 'docs' | 'tests' | 'code' | 'verify' | 'branch' | 'outside';
export const BLOCK_KINDS: readonly BlockKind[] = ['research', 'agent', 'docs', 'tests', 'code', 'verify', 'branch', 'outside'];
/** 棚・メニューに出すブロックの種類の名前 */
export const KIND_LABEL: Record<BlockKind, string> = {
  research: '調べる', agent: '任せる', docs: '文書と図', tests: 'テスト', code: 'コード', verify: '確かめる', branch: '仕分け', outside: '外を見る',
};
export type Access = 'read' | 'docs' | 'tests' | 'code';
export type InputMode = 'required' | 'optional' | 'none';

export interface Point { x: number; y: number }
export interface Rect { x: number; y: number; w: number; h: number }
/** judge は [stages.check.judge] の表をそのまま持つ（表示・編集はしない。知らないキーも残して書き戻す。古い形で無いときは null と同じ） */
export interface CheckModel { on: boolean; verdict: boolean; command: string; maxRetries: number; judge?: TomlTable | null }
export interface RouteModel { key: string; to: string }
export interface AgentModel { name: string; description: string; prompt: string; tools: string[]; model: string }
export interface McpServerModel { name: string; type: 'stdio' | 'http' | 'sse'; command: string; args: string[]; url: string }

/** 段（ブロック）。つなぎ先（next・routes の to・onFail）は段の id、枠の id、または 'end'。 */
export interface StageModel {
  id: string;
  kind: BlockKind;
  name: string;
  label: string;
  output: string;
  access: Access;
  docsDir: string;
  writes: string[];
  bash: boolean;
  review: boolean;
  model: string;
  maxTurns: number;
  maxBudget: number | null;
  prompt: string;
  refs: string[];
  web: 'off' | 'domains' | 'all';
  domains: string[];
  mcp: string[];
  check: CheckModel;
  /** 判定に通らないときに戻す段の id（null は自分をやり直す） */
  onFail: string | null;
  next: string | null;
  routes: RouteModel[];
  permissionMode: string;
  thinking: number | null;
  fallbackModel: string;
  systemAppend: string;
  addDirs: string[];
  agents: AgentModel[];
  mcpServers: McpServerModel[];
  x: number;
  y: number;
}

/** 並列の枠。中に置いた段が同じ group になる。 */
export interface FrameModel { id: string; name: string; x: number; y: number; w: number; h: number; next: string | null }

export interface PipeModel {
  name: string;
  label: string;
  description: string;
  input: InputMode;
  maxSteps: number;
  stages: StageModel[];
  frames: FrameModel[];
  start: Point;
  end: Point;
}

export class PipeLoadError extends Error {}

export const END = 'end';
const NAME_RE = /^[a-z0-9][a-z0-9-]*$/;
const RESERVED = new Set(['logs', 'end']);
const PERMISSION_MODES = ['default', 'acceptEdits', 'plan'];
const MCP_RE = /^mcp__[A-Za-z0-9][A-Za-z0-9_.-]*?__(\*|[A-Za-z0-9][A-Za-z0-9_.-]*)$/;
const DOMAIN_RE = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/;
const READ_ONLY_TOOLS = ['Read', 'Glob', 'Grep', 'Skill', 'ToolSearch', 'TodoWrite', 'StructuredOutput'];
const EDIT_TOOLS = ['Write', 'Edit', 'MultiEdit', 'NotebookEdit'];
const REFS_HEADING = '\n\n## 先に読むファイル\n\n';

// ---- 大きさ ------------------------------------------------------------------

const SIZES: Record<BlockKind, { w: number; h: number }> = {
  research: { w: 214, h: 84 },
  agent: { w: 214, h: 84 },
  docs: { w: 214, h: 92 },
  tests: { w: 214, h: 84 },
  code: { w: 214, h: 84 },
  verify: { w: 226, h: 84 },
  branch: { w: 196, h: 128 },
  outside: { w: 226, h: 84 },
};
export const TERMINAL_SIZE = { w: 132, h: 56 };
export const blockSize = (kind: BlockKind): { w: number; h: number } => SIZES[kind] ?? SIZES.research;

export const isPipeName = (name: string): boolean => NAME_RE.test(name) && !RESERVED.has(name);

// ---- 並びと枠 ----------------------------------------------------------------

/** 段の中心が入っている枠（なければ null） */
export function frameOf(m: PipeModel, s: StageModel): FrameModel | null {
  const z = blockSize(s.kind), cx = s.x + z.w / 2, cy = s.y + z.h / 2;
  return m.frames.find((f) => cx > f.x && cx < f.x + f.w && cy > f.y && cy < f.y + f.h) ?? null;
}

/** pipe.toml に書く順番：左から右（枠の中の段は枠の位置で、上から下） */
export function orderStages(m: PipeModel): StageModel[] {
  const key = (s: StageModel): [number, number, string, number] => {
    const f = frameOf(m, s);
    return f ? [f.x, 0, f.id, s.y] : [s.x, 1, '', s.y];
  };
  return [...m.stages].sort((a, b) => {
    const ka = key(a), kb = key(b);
    for (let i = 0; i < 4; i++) if (ka[i] !== kb[i]) return ka[i]! < kb[i]! ? -1 : 1;
    return 0;
  });
}

export const membersOf = (m: PipeModel, f: FrameModel): StageModel[] => orderStages(m).filter((s) => frameOf(m, s) === f);

/** つなぎ先の id を、pipe.toml の段の名前にする（枠はその最初の段） */
export function targetName(m: PipeModel, id: string | null): string {
  if (!id || id === END) return END;
  const f = m.frames.find((x) => x.id === id);
  if (f) return membersOf(m, f)[0]?.name ?? END;
  return m.stages.find((s) => s.id === id)?.name ?? END;
}

/**
 * 新しいブロックを置く場所：狙った点を中心に、ほかのブロック・枠・始まりと終わりから 60 離れた空きを近い順に探す
 * （横はプラグとコンセント、縦は差し戻しのケーブルが通る分）。
 * 押して置いたブロックが重なったり、うっかり並列の枠に入ったりしないように（ドラッグで置くときは使わない）。
 */
export function freeSpot(m: PipeModel, size: { w: number; h: number }, at: Point): Point {
  const gap = 60, step = 20, snap = (v: number): number => Math.round(v / 10) * 10;
  const taken: Rect[] = [
    ...m.stages.map((s) => ({ x: s.x, y: s.y, ...blockSize(s.kind) })),
    ...m.frames.map((f) => ({ x: f.x, y: f.y, w: f.w, h: f.h })),
    { x: m.start.x, y: m.start.y, ...TERMINAL_SIZE },
    { x: m.end.x, y: m.end.y, ...TERMINAL_SIZE },
  ];
  const free = (x: number, y: number): boolean =>
    taken.every((r) => x + size.w + gap <= r.x || r.x + r.w + gap <= x || y + size.h + gap <= r.y || r.y + r.h + gap <= y);
  const x0 = snap(at.x - snap(size.w / 2)), y0 = snap(at.y - snap(size.h / 2));
  for (let k = 0; k <= 200; k++) {
    const ring: Point[] = [];
    for (let i = -k; i <= k; i++) for (let j = -k; j <= k; j++) if (Math.max(Math.abs(i), Math.abs(j)) === k) ring.push({ x: x0 + i * step, y: y0 + j * step });
    ring.sort((a, b) => Math.hypot(a.x - x0, a.y - y0) - Math.hypot(b.x - x0, b.y - y0));
    const hit = ring.find((p) => free(p.x, p.y));
    if (hit) return hit;
  }
  return { x: x0, y: y0 };
}

// ---- 新しいパイプ・段 ----------------------------------------------------------

export function newPipe(name: string): PipeModel {
  return { name, label: name, description: '', input: 'optional', maxSteps: 50, stages: [], frames: [], start: { x: 20, y: 200 }, end: { x: 460, y: 200 } };
}

export function newStage(id: string, kind: BlockKind, name: string): StageModel {
  const access: Access = kind === 'docs' ? 'docs' : kind === 'tests' ? 'tests' : kind === 'code' ? 'code' : 'read';
  return {
    id, kind, name, label: name, output: `${name}.md`, access, docsDir: kind === 'docs' ? 'docs' : '', writes: [], bash: false, review: false,
    model: '', maxTurns: 100, maxBudget: null, prompt: '', refs: [], web: kind === 'outside' ? 'domains' : 'off', domains: [], mcp: [],
    check: { on: kind === 'verify', verdict: true, command: '', maxRetries: 2, judge: null }, onFail: null, next: null, routes: [],
    permissionMode: '', thinking: null, fallbackModel: '', systemAppend: '', addDirs: [],
    agents: kind === 'agent' ? [{ name: 'helper', description: '', prompt: '', tools: ['Read', 'Grep', 'Glob'], model: '' }] : [],
    mcpServers: [], x: 0, y: 0,
  };
}

// ---- 読み込み：pipe.toml・prompts/・layout.json → モデル -----------------------------

const str = (v: TomlValue | undefined): string => (typeof v === 'string' ? v : '');
const strList = (v: TomlValue | undefined): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []);
const num = (v: TomlValue | undefined): number | null => (typeof v === 'number' ? v : null);
const isTable = (v: TomlValue | undefined): v is TomlTable => typeof v === 'object' && v !== null && !Array.isArray(v);
const table = (v: TomlValue | undefined): TomlTable => (isTable(v) ? v : {});

function splitRefs(text: string): { prompt: string; refs: string[] } {
  const body = text.replace(/\r\n/g, '\n').replace(/\s+$/, '');
  const i = body.indexOf(REFS_HEADING);
  if (i < 0) return { prompt: body, refs: [] };
  const refs = body.slice(i + REFS_HEADING.length).split('\n').map((l) => /^- `(.+)`$/.exec(l.trim())?.[1]).filter((x): x is string => !!x);
  return { prompt: body.slice(0, i), refs };
}

function inferKind(s: StageModel): BlockKind {
  if (s.routes.length) return 'branch';
  if (s.check.on && s.check.verdict) return 'verify';
  if (s.agents.length) return 'agent';
  if (s.web !== 'off' || s.mcp.length || s.mcpServers.length) return 'outside';
  if (s.access === 'docs') return 'docs';
  if (s.access === 'tests') return 'tests';
  if (s.access === 'code') return 'code';
  return 'research';
}

interface Layout {
  stages?: Record<string, { x?: number; y?: number; kind?: string }>;
  frames?: Record<string, { x?: number; y?: number; w?: number; h?: number }>;
  start?: Point;
  end?: Point;
}

export function pipeFromFiles(name: string, tomlText: string, files: Record<string, string>, layoutJson: string | null): PipeModel {
  let doc: TomlTable;
  try {
    doc = parseToml(tomlText);
  } catch (e) {
    throw new PipeLoadError(`pipe.toml を読めません：${e instanceof TomlError ? e.message : String(e)}`);
  }
  const p = table(doc.pipe);
  if (str(p.kind) === 'dev') throw new PipeLoadError('開発フローのパイプ（kind = "dev"）は、段が pipe-in に組み込みのため、作業台では開けません');
  const m = newPipe(name);
  m.label = str(p.label) || name;
  m.description = str(p.description);
  const input = str(p.input);
  m.input = input === 'required' || input === 'none' ? input : 'optional';
  m.maxSteps = num(p.max_steps) ?? 50;

  const raws = Array.isArray(doc.stages) ? doc.stages.map(table) : [];
  const groupOf: (string | null)[] = [];
  const pending: { routes: [string, string][]; next: string | null; onFail: string | null }[] = [];
  raws.forEach((raw, i) => {
    const sname = str(raw.name);
    const s = newStage(`s${i + 1}`, 'research', sname);
    s.label = str(raw.label) || sname;
    s.output = str(raw.output);
    const access = str(raw.access);
    s.access = access === 'docs' || access === 'tests' || access === 'code' ? access : 'read';
    s.docsDir = str(raw.docs_dir);
    s.writes = strList(raw.writes);
    s.bash = raw.bash === true;
    s.review = raw.review === true;
    s.model = str(raw.model);
    s.maxTurns = num(raw.max_turns) ?? 100;
    s.maxBudget = num(raw.max_budget_usd);
    if (raw.web === true) s.web = 'all';
    else if (Array.isArray(raw.web)) { s.web = 'domains'; s.domains = strList(raw.web); }
    else s.web = 'off';
    s.mcp = strList(raw.mcp);
    s.permissionMode = str(raw.permission_mode);
    s.thinking = num(raw.max_thinking_tokens);
    s.fallbackModel = str(raw.fallback_model);
    s.systemAppend = str(raw.system_append);
    s.addDirs = strList(raw.add_dirs);
    s.agents = Object.entries(table(raw.agents)).map(([an, av]) => {
      const a = table(av);
      return { name: an, description: str(a.description), prompt: str(a.prompt), tools: strList(a.tools), model: str(a.model) };
    });
    s.mcpServers = Object.entries(table(raw.mcp_servers)).map(([mn, mv]) => {
      const t = table(mv), type = str(t.type);
      return { name: mn, type: type === 'http' || type === 'sse' ? type : 'stdio', command: str(t.command), args: strList(t.args), url: str(t.url) };
    });
    const check = table(raw.check);
    s.check = { on: raw.check !== undefined, verdict: check.verdict === true, command: str(check.command), maxRetries: num(check.max_retries) ?? 2,
      judge: check.judge !== undefined && isTable(check.judge) ? (JSON.parse(JSON.stringify(check.judge)) as TomlTable) : null };
    const pf = str(raw.prompt_file);
    if (pf) {
      if (!/^prompts\/[^/\\]+\.md$/.test(pf) || pf.includes('..')) throw new PipeLoadError(`段「${sname}」の指示ファイル ${pf} は、prompts/ の下の .md にしてください`);
      const text = files[pf];
      if (text !== undefined) Object.assign(s, splitRefs(text));
    } else {
      Object.assign(s, splitRefs(str(raw.prompt)));
    }
    groupOf.push(str(raw.group) || null);
    pending.push({
      routes: Object.entries(table(raw.routes)).map(([k, v]) => [k, str(v)] as [string, string]),
      next: typeof raw.next === 'string' ? raw.next : null,
      onFail: str(check.on_fail) || null,
    });
    m.stages.push(s);
  });

  // 枠：同じ group の段のまとまり
  const frameByGroup = new Map<string, FrameModel>();
  groupOf.forEach((g) => { if (g && !frameByGroup.has(g)) frameByGroup.set(g, { id: `f:${g}`, name: g, x: 0, y: 0, w: 0, h: 0, next: null }); });
  m.frames = [...frameByGroup.values()];
  const idOfName = (n: string): string => {
    if (n === END) return END;
    const i = m.stages.findIndex((s) => s.name === n);
    if (i < 0) return END;
    const g = groupOf[i];
    if (g && groupOf.indexOf(g) === i) return frameByGroup.get(g)!.id; // 枠の最初の段へ入る＝枠へ
    return m.stages[i]!.id;
  };
  const natural = (i: number): string => (i + 1 < m.stages.length ? idOfName(m.stages[i + 1]!.name) : END);
  m.stages.forEach((s, i) => {
    const pend = pending[i]!, g = groupOf[i];
    if (pend.onFail) s.onFail = m.stages.find((x) => x.name === pend.onFail)?.id ?? null;
    if (g) return; // 枠の中の段は、つなぎを持たない（枠から出る）
    if (pend.routes.length) s.routes = pend.routes.map(([key, to]) => ({ key, to: idOfName(to) }));
    else s.next = pend.next !== null ? idOfName(pend.next) : natural(i);
  });
  for (const [g, f] of frameByGroup) {
    let last = -1;
    groupOf.forEach((x, i) => { if (x === g) last = i; });
    f.next = natural(last);
  }
  m.stages.forEach((s) => { s.kind = inferKind(s); });

  // 位置：layout.json があればそれを、なければ自動で並べる
  const owner = new Map<string, FrameModel>();
  m.stages.forEach((s, i) => { const g = groupOf[i]; if (g) owner.set(s.id, frameByGroup.get(g)!); });
  arrange(m, owner, m.stages);
  if (layoutJson) applyLayout(m, layoutJson);
  return m;
}

function applyLayout(m: PipeModel, layoutJson: string): void {
  let layout: Layout;
  try {
    layout = JSON.parse(layoutJson) as Layout;
  } catch {
    return; // 位置が読めなければ、自動で並べたままにする
  }
  for (const s of m.stages) {
    const l = layout.stages?.[s.name];
    if (!l) continue;
    if (typeof l.x === 'number' && typeof l.y === 'number') { s.x = l.x; s.y = l.y; }
    if (typeof l.kind === 'string' && (BLOCK_KINDS as readonly string[]).includes(l.kind)) s.kind = l.kind as BlockKind;
  }
  for (const f of m.frames) {
    const l = layout.frames?.[f.name];
    if (l && [l.x, l.y, l.w, l.h].every((v) => typeof v === 'number')) Object.assign(f, { x: l.x, y: l.y, w: l.w, h: l.h });
  }
  if (layout.start && typeof layout.start.x === 'number') m.start = { x: layout.start.x, y: layout.start.y };
  if (layout.end && typeof layout.end.x === 'number') m.end = { x: layout.end.x, y: layout.end.y };
}

// ---- 自動で並べる ------------------------------------------------------------

const X0 = 200, COL = 310, LANE = 250, MID = 112;

function arrange(m: PipeModel, owner: Map<string, FrameModel>, ord: StageModel[]): PipeModel {
  const col = new Map<string, number>();
  let c = 0;
  let last: FrameModel | undefined;
  for (const s of ord) {
    const f = owner.get(s.id);
    if (f && f === last) { col.set(s.id, c - 1); continue; }
    col.set(s.id, c++);
    last = f;
  }
  const firstOf = (id: string): string | undefined => {
    const f = m.frames.find((x) => x.id === id);
    return f ? ord.find((s) => owner.get(s.id) === f)?.id : id;
  };
  const lane = new Map<string, number>();
  ord.forEach((s, i) => {
    if (!lane.has(s.id)) lane.set(s.id, i ? lane.get(ord[i - 1]!.id) ?? 0 : 0);
    s.routes.forEach((r, k) => {
      const t = firstOf(r.to);
      if (t && t !== END && !lane.has(t)) lane.set(t, (lane.get(s.id) ?? 0) + k);
    });
  });
  const stack = new Map<string, number>();
  for (const s of ord) {
    const f = owner.get(s.id), x = X0 + (col.get(s.id) ?? 0) * COL, ln = lane.get(s.id) ?? 0;
    if (f) {
      const j = stack.get(f.id) ?? 0;
      stack.set(f.id, j + 1);
      s.x = x + 30;
      s.y = 60 + ln * LANE + 40 + j * 116;
    } else {
      s.x = x;
      s.y = 60 + ln * LANE + MID - blockSize(s.kind).h / 2;
    }
  }
  for (const f of m.frames) {
    const ms = ord.filter((s) => owner.get(s.id) === f);
    if (!ms.length) continue;
    f.x = Math.min(...ms.map((s) => s.x)) - 30;
    f.y = Math.min(...ms.map((s) => s.y)) - 30;
    f.w = Math.max(...ms.map((s) => blockSize(s.kind).w)) + 60;
    f.h = Math.max(...ms.map((s) => s.y + blockSize(s.kind).h)) + 30 - f.y;
  }
  m.start = { x: 20, y: 60 + MID - TERMINAL_SIZE.h / 2 };
  m.end = { x: X0 + c * COL, y: 60 + MID - TERMINAL_SIZE.h / 2 };
  return m;
}

/** 今の並び（左から右・枠）のまま、ブロックを並べ直す */
export function autoLayout(m: PipeModel): PipeModel {
  const ord = orderStages(m);
  const owner = new Map<string, FrameModel>();
  ord.forEach((s) => { const f = frameOf(m, s); if (f) owner.set(s.id, f); });
  return arrange(m, owner, ord);
}

// ---- 書き出し：モデル → pipe.toml・prompts/・layout.json ------------------------------

const q = (v: string): string => JSON.stringify(v);
const key = (k: string): string => (/^[A-Za-z0-9_-]+$/.test(k) ? k : q(k));
export const promptPath = (s: StageModel, i: number): string => `prompts/${String(i + 1).padStart(2, '0')}_${s.name}.md`;
export const promptFileText = (s: StageModel): string =>
  s.prompt.trim() + (s.refs.length ? `${REFS_HEADING}${s.refs.map((r) => `- \`${r}\``).join('\n')}` : '') + '\n';

const scalarOrList = (v: TomlValue): string => (Array.isArray(v) ? `[${v.map(scalarOrList).join(', ')}]` : typeof v === 'string' ? q(v) : String(v));
const isTableArray = (v: TomlValue): v is TomlTable[] => Array.isArray(v) && v.length > 0 && v.every(isTable);

/** 読んだ表を、読んだ順のまま書き出す（スカラー・値の配列 → 入れ子の表 → 表の配列）。審査（judge）を知らないまま守るための汎用の書き出し */
function judgeLines(path: string, t: TomlTable): string[] {
  const L: string[] = [`[${path}]`];
  const entries = Object.entries(t);
  for (const [k, v] of entries) if (!isTable(v) && !isTableArray(v)) L.push(`${key(k)} = ${scalarOrList(v)}`);
  for (const [k, v] of entries) if (isTable(v)) L.push(...judgeLines(`${path}.${key(k)}`, v));
  for (const [k, v] of entries) {
    if (!isTableArray(v)) continue;
    for (const item of v) L.push(...judgeLines(`${path}.${key(k)}`, item).map((l, i) => (i === 0 ? `[${l}]` : l)));
  }
  return L;
}

export function toToml(m: PipeModel): string {
  const ord = orderStages(m), L: string[] = [];
  L.push('# パイプ作業台で作った定義。各段への指示は prompts/ のファイル、ブロックの位置は layout.json です。', '', '[pipe]', 'kind = "linear"', `label = ${q(m.label)}`);
  if (m.description) L.push(`description = ${q(m.description)}`);
  L.push(`input = ${q(m.input)}`);
  if (m.maxSteps !== 50) L.push(`max_steps = ${m.maxSteps}`);
  ord.forEach((s, i) => {
    const f = frameOf(m, s), after = ord[i + 1];
    L.push('', '[[stages]]', `name = ${q(s.name)}`, `label = ${q(s.label)}`, `output = ${q(s.output)}`, `access = ${q(s.access)}`);
    if (s.access === 'docs' && s.docsDir) L.push(`docs_dir = ${q(s.docsDir)}`);
    if (s.access !== 'read' && s.writes.length) L.push(`writes = [${s.writes.map(q).join(', ')}]`);
    if (s.bash) L.push('bash = true');
    if (s.review && !f) L.push('review = true');
    if (f) L.push(`group = ${q(f.name)}`);
    if (!f && !s.routes.length) {
      const to = targetName(m, s.next), naturalName = after ? after.name : END;
      if (to !== naturalName) L.push(`next = ${q(to)}`);
    }
    if (s.model) L.push(`model = ${q(s.model)}`);
    if (s.maxTurns !== 100) L.push(`max_turns = ${s.maxTurns}`);
    if (s.maxBudget !== null) L.push(`max_budget_usd = ${s.maxBudget}`);
    if (s.web === 'all') L.push('web = true');
    if (s.web === 'domains' && s.domains.length) L.push(`web = [${s.domains.map(q).join(', ')}]`);
    if (s.mcp.length) L.push(`mcp = [${s.mcp.map(q).join(', ')}]`);
    if (s.permissionMode) L.push(`permission_mode = ${q(s.permissionMode)}`);
    if (s.thinking !== null) L.push(`max_thinking_tokens = ${s.thinking}`);
    if (s.fallbackModel) L.push(`fallback_model = ${q(s.fallbackModel)}`);
    if (s.systemAppend.trim()) L.push(`system_append = ${q(s.systemAppend.trim())}`);
    if (s.addDirs.length) L.push(`add_dirs = [${s.addDirs.map(q).join(', ')}]`);
    L.push(`prompt_file = ${q(promptPath(s, i))}`);
    if (s.check.on) {
      L.push('[stages.check]');
      if (s.check.verdict) L.push('verdict = true');
      if (s.check.command) L.push(`command = ${q(s.check.command)}`);
      if (s.onFail && s.onFail !== s.id) L.push(`on_fail = ${q(targetName(m, s.onFail))}`);
      L.push(`max_retries = ${s.check.maxRetries}`);
      if (s.check.judge) L.push(...judgeLines('stages.check.judge', s.check.judge));
    }
    if (s.routes.length && !f) {
      L.push('[stages.routes]');
      s.routes.forEach((r) => L.push(`${key(r.key)} = ${q(targetName(m, r.to))}`));
    }
    for (const a of s.agents) {
      L.push(`[stages.agents.${key(a.name)}]`, `description = ${q(a.description)}`, `prompt = ${q(a.prompt)}`);
      if (a.tools.length) L.push(`tools = [${a.tools.map(q).join(', ')}]`);
      if (a.model) L.push(`model = ${q(a.model)}`);
    }
    for (const srv of s.mcpServers) {
      L.push(`[stages.mcp_servers.${key(srv.name)}]`, `type = ${q(srv.type)}`);
      if (srv.type === 'stdio') {
        L.push(`command = ${q(srv.command)}`);
        if (srv.args.length) L.push(`args = [${srv.args.map(q).join(', ')}]`);
      } else L.push(`url = ${q(srv.url)}`);
    }
  });
  return L.join('\n') + '\n';
}

export function toLayout(m: PipeModel): string {
  const layout: Layout = { stages: {}, frames: {}, start: m.start, end: m.end };
  for (const s of orderStages(m)) layout.stages![s.name] = { x: s.x, y: s.y, kind: s.kind };
  for (const f of m.frames) layout.frames![f.name] = { x: f.x, y: f.y, w: f.w, h: f.h };
  return JSON.stringify(layout, null, 2) + '\n';
}

/** パイプのフォルダに書くファイル（相対パス → 中身）。README は含めない（無いときだけ app が作る） */
export function pipeFiles(m: PipeModel): Record<string, string> {
  const files: Record<string, string> = { 'pipe.toml': toToml(m), 'layout.json': toLayout(m) };
  orderStages(m).forEach((s, i) => { files[promptPath(s, i)] = promptFileText(s); });
  return files;
}

// ---- 検査 ------------------------------------------------------------------

function stageTools(s: StageModel): string[] {
  const tools = [...READ_ONLY_TOOLS, ...EDIT_TOOLS];
  if (s.bash) tools.push('Bash');
  if (s.web === 'all') tools.push('WebFetch', 'WebSearch');
  else if (s.web === 'domains' && s.domains.length) tools.push('WebFetch');
  return tools;
}

export function validatePipe(m: PipeModel): { errors: string[] } {
  const ord = orderStages(m), errors: string[] = [], names = new Set<string>(), outs = new Set<string>();
  const pos = (id: string | null): number => ord.findIndex((s) => s.id === id);
  const firstOf = (id: string): string | null => {
    const f = m.frames.find((x) => x.id === id);
    return f ? membersOf(m, f)[0]?.id ?? null : id;
  };
  if (!isPipeName(m.name)) errors.push(`パイプの名前「${m.name}」は使えません（英小文字・数字・- だけ。logs・end は不可）`);
  if (!ord.length) errors.push('段がありません。左の棚からブロックを置いてください');
  if (!(m.maxSteps >= 1)) errors.push('max_steps は 1 以上の整数で書いてください');
  ord.forEach((s, i) => {
    const at = `${String(i + 1).padStart(2, '0')} ${s.label}：`, f = frameOf(m, s);
    if (!isPipeName(s.name)) errors.push(at + 'name は英小文字・数字・- で書いてください（logs・end は不可）');
    else if (names.has(s.name)) errors.push(at + `段の名前「${s.name}」が重複しています`);
    names.add(s.name);
    if (!s.output || /[\\/]/.test(s.output) || s.output.startsWith('.')) errors.push(at + '成果物はファイル名だけを書いてください（例: 01_survey.md）');
    else if (outs.has(s.output)) errors.push(at + `成果物「${s.output}」が重複しています`);
    outs.add(s.output);
    if (!s.prompt.trim()) errors.push(at + '頼むこと（指示）が空です');
    if (s.access === 'docs' && !s.docsDir) errors.push(at + '文書のフォルダ（docs_dir）が要ります');
    if (s.access === 'docs' && s.docsDir && (s.docsDir.startsWith('/') || s.docsDir.split('/').includes('..'))) errors.push(at + `docs_dir「${s.docsDir}」はプロジェクトの外を指しています`);
    s.writes.forEach((g) => { if (!g || g.startsWith('/') || g.split('/').includes('..')) errors.push(at + `writes の「${g}」は、プロジェクトの中の相対パスで書いてください`); });
    if (s.check.on && !s.check.verdict && !s.check.command && !s.check.judge) errors.push(at + '検証には、判定・確認用のコマンド・審査のどれかが要ります');
    if (s.check.on && /\b(curl|wget|ssh|scp|rsync|nc)\b|\bgit\s+push\b/.test(s.check.command)) errors.push(at + '確認用のコマンドに、外への通信や git push は使えません');
    if (s.check.on && !(s.check.maxRetries >= 0)) errors.push(at + 'check の max_retries は 0 以上の整数で書いてください');
    if (s.onFail && s.onFail !== s.id) {
      const j = pos(s.onFail);
      if (j < 0 || j > i) errors.push(at + '差し戻しの先は、並びで自分より前の段にしてください（左に置く）');
      if (f) errors.push(at + '並列の枠の中の段は、自分だけをやり直せます（差し戻しの先を外してください）');
    }
    s.mcp.forEach((x) => { if (!MCP_RE.test(x)) errors.push(at + `MCP の道具「${x}」は mcp__<サーバー>__<ツール> の形で書いてください`); });
    if (s.web === 'domains') s.domains.forEach((d) => { if (!DOMAIN_RE.test(d)) errors.push(at + `ドメイン「${d}」は名前だけで書いてください（例: docs.python.org）`); });
    if (f) {
      if (s.review) errors.push(at + '並列の枠の中では、人の確認は取れません');
      if (s.routes.length || s.next) errors.push(at + '並列の枠の中の段からはつなげません。枠の右のプラグを差してください');
    } else {
      const keys = new Set<string>();
      s.routes.forEach((r) => {
        if (!r.key) errors.push(at + '分岐の選択肢に名前がありません');
        else if (keys.has(r.key)) errors.push(at + `分岐の選択肢「${r.key}」が重複しています`);
        keys.add(r.key);
      });
      const targets = s.routes.length ? s.routes.map((r) => r.to) : s.next ? [s.next] : [];
      targets.forEach((t) => {
        if (t === END) return;
        const j = pos(firstOf(t));
        if (j >= 0 && j <= i) errors.push(at + '前の段へ進むつなぎがあります。戻すなら、確かめるブロックの差し戻しにしてください');
      });
      if (!s.routes.length && !s.next && ord[i + 1]) errors.push(at + 'つなぎがありません（ここで終わるなら「終わり」へ差してください）');
    }
    if (s.kind === 'branch' && !s.routes.length) errors.push(at + '仕分けのブロックに、分岐がありません（右のプラグを行き先に差してください）');
    // Agent SDK の設定（pipe_in/pipe/definition.py の _check_sdk と同じ決まり）
    if (s.permissionMode && !PERMISSION_MODES.includes(s.permissionMode)) errors.push(at + `permission_mode「${s.permissionMode}」は使えません（${PERMISSION_MODES.join(' / ')} のどれか）`);
    if (s.thinking !== null && !(s.thinking >= 1)) errors.push(at + 'max_thinking_tokens は 1 以上の整数で書いてください');
    s.addDirs.forEach((d) => { if (!d || d.startsWith('/') || d.startsWith('\\') || /^[A-Za-z]:/.test(d)) errors.push(at + `add_dirs の「${d}」は、プロジェクトからの相対パスで書いてください`); });
    const allowed = new Set(stageTools(s));
    s.agents.forEach((a) => {
      if (!NAME_RE.test(a.name)) errors.push(at + `サブエージェントの名前「${a.name}」は、英小文字・数字・- で書いてください`);
      if (!a.description.trim()) errors.push(at + `サブエージェント「${a.name}」の description（いつ任せるか）がありません`);
      if (!a.prompt.trim()) errors.push(at + `サブエージェント「${a.name}」の prompt（指示）がありません`);
      a.tools.forEach((t) => {
        if (['Task', 'Agent', 'PowerShell'].includes(t)) errors.push(at + `サブエージェント「${a.name}」に ${t} は持たせられません`);
        else if (!allowed.has(t) && !(t.startsWith('mcp__') && s.mcp.some((x) => x === t || (x.endsWith('__*') && t.startsWith(x.slice(0, -1)))))) errors.push(at + `サブエージェント「${a.name}」の道具 ${t} は、この段で使えない道具です`);
      });
    });
    s.mcpServers.forEach((srv) => {
      if (!srv.name) errors.push(at + 'MCP サーバーに名前がありません');
      if (srv.type === 'stdio' && !srv.command) errors.push(at + `MCP サーバー「${srv.name}」（stdio）には command が要ります`);
      if (srv.type !== 'stdio' && !srv.url) errors.push(at + `MCP サーバー「${srv.name}」（${srv.type}）には url が要ります`);
      if (!s.mcp.length) errors.push(at + `MCP サーバー「${srv.name}」の道具が mcp にありません（mcp__${srv.name}__<道具> を書いてください）`);
    });
  });
  for (const fr of m.frames) {
    const ms = membersOf(m, fr);
    if (!ms.length) { errors.push(`並列の枠「${fr.name}」が空です。段を枠の中に置いてください`); continue; }
    const last = ord.indexOf(ms[ms.length - 1]!), after = ord[last + 1];
    const to = targetName(m, fr.next);
    if (!fr.next && after) errors.push(`並列の枠「${fr.name}」のあとにつなぎがありません`);
    else if (fr.next && to !== (after ? after.name : END)) errors.push(`並列の枠「${fr.name}」からは、並びで次にある段へしか進めません（行き先を枠のすぐ右に置いてください）`);
  }
  return { errors };
}

/** パネルから来たモデルの形を確かめる（中身の正しさは validatePipe） */
export function isPipeModel(v: unknown): v is PipeModel {
  if (typeof v !== 'object' || v === null) return false;
  const m = v as Record<string, unknown>;
  const point = (p: unknown): boolean => typeof p === 'object' && p !== null && typeof (p as Point).x === 'number' && typeof (p as Point).y === 'number';
  return typeof m.name === 'string' && typeof m.label === 'string' && Array.isArray(m.stages) && Array.isArray(m.frames)
    && point(m.start) && point(m.end)
    && m.stages.every((s) => typeof s === 'object' && s !== null && typeof (s as StageModel).id === 'string' && typeof (s as StageModel).name === 'string'
      && typeof (s as StageModel).prompt === 'string' && typeof (s as StageModel).check === 'object' && Array.isArray((s as StageModel).routes))
    && m.frames.every((f) => typeof f === 'object' && f !== null && typeof (f as FrameModel).id === 'string' && typeof (f as FrameModel).name === 'string');
}
