// パイプ（pipe.toml・prompts/・layout.json）と作業台のモデルの行き来、並び、検査。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  PipeLoadError,
  autoLayout,
  blockSize,
  freeSpot,
  frameOf,
  newPipe,
  newStage,
  orderStages,
  pipeFiles,
  pipeFromFiles,
  validatePipe,
} from './pipeModel.ts';
import type { PipeModel } from './pipeModel.ts';
import { parseToml } from './toml.ts';

const TOML = `[pipe]
kind = "linear"
label = "依頼に合わせて図か仕様"
input = "required"

[[stages]]
name = "triage"
label = "依頼の仕分け"
output = "01_triage.md"
access = "read"
prompt_file = "prompts/01_triage.md"
[stages.routes]
diagrams = "survey"
spec = "spec-check"
none = "end"

[[stages]]
name = "survey"
label = "ソースの調査"
output = "02_survey.md"
access = "read"
review = true
max_thinking_tokens = 16000
prompt_file = "prompts/02_survey.md"
[stages.agents.module-reader]
description = "モジュールを読む"
prompt = "1つだけ読む"
tools = ["Read", "Grep"]

[[stages]]
name = "flow"
label = "フロー図"
output = "03_flow.md"
access = "docs"
docs_dir = "docs/diagrams"
group = "draw"
prompt_file = "prompts/03_flow.md"

[[stages]]
name = "sequence"
label = "シーケンス図"
output = "04_sequence.md"
access = "docs"
docs_dir = "docs/diagrams"
group = "draw"
prompt_file = "prompts/04_sequence.md"

[[stages]]
name = "verify"
label = "突き合わせ"
output = "05_verify.md"
access = "read"
next = "end"
prompt_file = "prompts/05_verify.md"
[stages.check]
verdict = true
on_fail = "flow"
max_retries = 2

[[stages]]
name = "spec-check"
label = "仕様の突き合わせ"
output = "06_spec.md"
access = "read"
permission_mode = "plan"
web = ["docs.python.org"]
mcp = ["mcp__jira__get_issue"]
prompt_file = "prompts/06_spec-check.md"
[stages.mcp_servers.jira]
type = "http"
url = "https://mcp.example.com/jira"
`;

const PROMPTS: Record<string, string> = {
  'prompts/01_triage.md': '依頼を仕分ける\n',
  'prompts/02_survey.md': 'ソースを調べる\n\n## 先に読むファイル\n\n- `docs/spec/`\n',
  'prompts/03_flow.md': 'フロー図を描く\n',
  'prompts/04_sequence.md': 'シーケンス図を描く\n',
  'prompts/05_verify.md': '突き合わせる\n',
  'prompts/06_spec-check.md': '仕様と突き合わせる\n',
};

function load(layout: string | null = null): PipeModel {
  return pipeFromFiles('design-review', TOML, PROMPTS, layout);
}
const byName = (m: PipeModel, name: string) => m.stages.find((s) => s.name === name)!;

test('AC-22: pipe.toml と prompts/ から作業台のモデルを作る（ブロックの形は中身から決める）', () => {
  const m = load();
  assert.equal(m.name, 'design-review');
  assert.equal(m.input, 'required');
  assert.deepEqual(orderStages(m).map((s) => s.name), ['triage', 'survey', 'flow', 'sequence', 'verify', 'spec-check']);
  assert.equal(byName(m, 'triage').kind, 'branch');
  assert.equal(byName(m, 'survey').kind, 'agent');
  assert.equal(byName(m, 'flow').kind, 'docs');
  assert.equal(byName(m, 'verify').kind, 'verify');
  assert.equal(byName(m, 'spec-check').kind, 'outside');
  assert.equal(byName(m, 'survey').prompt, 'ソースを調べる');
  assert.deepEqual(byName(m, 'survey').refs, ['docs/spec/']);
  assert.equal(byName(m, 'survey').thinking, 16000);
  assert.deepEqual(byName(m, 'survey').agents, [{ name: 'module-reader', description: 'モジュールを読む', prompt: '1つだけ読む', tools: ['Read', 'Grep'], model: '' }]);
  assert.deepEqual(byName(m, 'spec-check').mcpServers, [{ name: 'jira', type: 'http', command: '', args: [], url: 'https://mcp.example.com/jira' }]);
  assert.equal(byName(m, 'spec-check').web, 'domains');
  assert.deepEqual(byName(m, 'spec-check').domains, ['docs.python.org']);
});

test('AC-22: つなぎを明示する（定義の次の段・並列の枠・分岐・差し戻し）', () => {
  const m = load();
  assert.equal(m.frames.length, 1);
  const frame = m.frames[0]!;
  assert.equal(frame.name, 'draw');
  assert.equal(frameOf(m, byName(m, 'flow')), frame);
  assert.equal(frameOf(m, byName(m, 'sequence')), frame);
  assert.equal(byName(m, 'survey').next, frame.id); // 定義の次（並列の枠）へ
  assert.equal(frame.next, byName(m, 'verify').id); // 枠のあと
  assert.equal(byName(m, 'verify').next, 'end');
  assert.equal(byName(m, 'verify').onFail, byName(m, 'flow').id);
  assert.deepEqual(byName(m, 'triage').routes.map((r) => r.key), ['diagrams', 'spec', 'none']);
  assert.equal(byName(m, 'triage').routes[2]!.to, 'end');
  assert.equal(byName(m, 'spec-check').next, 'end'); // 最後の段は終わりへ
  assert.deepEqual(validatePipe(m).errors, []);
});

test('AC-23: 書き出すと、同じ pipe.toml の意味に戻る（定義の次の段は next を書かない）', () => {
  const m = load();
  const files = pipeFiles(m);
  const back = parseToml(files['pipe.toml']!);
  const stages = back.stages as Record<string, unknown>[];
  assert.deepEqual(stages.map((s) => s.name), ['triage', 'survey', 'flow', 'sequence', 'verify', 'spec-check']);
  assert.equal(stages[1]!.next, undefined);
  assert.equal(stages[4]!.next, 'end');
  assert.equal(stages[5]!.next, undefined);
  assert.deepEqual(stages[0]!.routes, { diagrams: 'survey', spec: 'spec-check', none: 'end' });
  assert.deepEqual(stages[4]!.check, { verdict: true, on_fail: 'flow', max_retries: 2 });
  assert.equal(stages[2]!.group, 'draw');
  assert.equal(stages[1]!.max_thinking_tokens, 16000);
  assert.deepEqual(stages[1]!.agents, { 'module-reader': { description: 'モジュールを読む', prompt: '1つだけ読む', tools: ['Read', 'Grep'] } });
  assert.deepEqual(stages[5]!.mcp_servers, { jira: { type: 'http', url: 'https://mcp.example.com/jira' } });
  assert.equal(stages[5]!.permission_mode, 'plan');
  assert.deepEqual(stages[5]!.web, ['docs.python.org']);
  assert.equal(files['prompts/02_survey.md'], 'ソースを調べる\n\n## 先に読むファイル\n\n- `docs/spec/`\n');
  const again = pipeFromFiles('design-review', files['pipe.toml']!, files, files['layout.json']!);
  assert.deepEqual(pipeFiles(again), files);
});

test('AC-23: ブロックの位置と形は layout.json に残し、読み込みで戻す', () => {
  const m = load();
  byName(m, 'triage').x = 333;
  byName(m, 'survey').kind = 'research';
  const files = pipeFiles(m);
  const layout = JSON.parse(files['layout.json']!);
  assert.equal(layout.stages.triage.x, 333);
  const again = pipeFromFiles('design-review', files['pipe.toml']!, files, files['layout.json']!);
  assert.equal(byName(again, 'triage').x, 333);
  assert.equal(byName(again, 'survey').kind, 'research');
});

test('AC-24: layout.json がなければ、並びの順に左から右へ並べる（枠の段は縦に積む）', () => {
  const m = autoLayout(load());
  const x = (n: string) => byName(m, n).x;
  assert.ok(x('triage') < x('survey') && x('survey') < x('flow') && x('flow') < x('verify'));
  assert.equal(x('flow'), x('sequence'));
  assert.notEqual(byName(m, 'flow').y, byName(m, 'sequence').y);
  assert.equal(frameOf(m, byName(m, 'flow')), m.frames[0]);
  assert.ok(m.end.x > x('verify'));
});

test('AC-25: 検査は devpipe-gen check と同じ決まり（主なもの）と、作業台で起きやすい誤り', () => {
  const m = load();
  byName(m, 'flow').name = 'survey';
  assert.ok(validatePipe(m).errors.some((e) => e.includes('重複')));
  const m2 = load();
  byName(m2, 'verify').onFail = byName(m2, 'spec-check').id;
  assert.ok(validatePipe(m2).errors.some((e) => e.includes('前の段')));
  const m3 = load();
  byName(m3, 'survey').next = null;
  assert.ok(validatePipe(m3).errors.some((e) => e.includes('つなぎがありません')));
  const m4 = load();
  byName(m4, 'spec-check').permissionMode = 'bypassPermissions';
  assert.ok(validatePipe(m4).errors.some((e) => e.includes('permission_mode')));
  const m5 = load();
  byName(m5, 'survey').agents[0]!.tools = ['Read', 'PowerShell'];
  assert.ok(validatePipe(m5).errors.some((e) => e.includes('PowerShell')));
  const m6 = load();
  byName(m6, 'spec-check').mcp = [];
  assert.ok(validatePipe(m6).errors.some((e) => e.includes('mcp__jira__')));
  const m7 = load();
  byName(m7, 'triage').prompt = '';
  assert.ok(validatePipe(m7).errors.some((e) => e.includes('頼むこと')));
});

test('AC-26: 作業台で読めないパイプは、理由をつけて断る', () => {
  assert.throws(() => pipeFromFiles('x', '[pipe]\nkind = "dev"\nlabel = "開発"\n', {}, null), (e: unknown) => e instanceof PipeLoadError && /開発フロー/.test(e.message));
  assert.throws(() => pipeFromFiles('x', 'a = { b = 1 }\n', {}, null), PipeLoadError);
  assert.throws(() => pipeFromFiles('x', '[pipe]\nkind = "linear"\n[[stages]]\nname = "a"\nprompt_file = "../a.md"\n', {}, null), (e: unknown) => e instanceof PipeLoadError && /prompts\//.test(e.message));
});

test('AC-27: 新しいパイプは、始まりと終わりだけの空の状態から', () => {
  const m = newPipe('my-pipe');
  assert.equal(m.name, 'my-pipe');
  assert.equal(m.stages.length, 0);
  assert.ok(validatePipe(m).errors.some((e) => e.includes('段がありません')));
});

test('AC-39: 押して置くブロックは、ほかのブロック・枠・始まりと終わりに重ならない空いた場所に置く', () => {
  const m = pipeFromFiles('design-review', TOML, {}, null);
  const over = (a: { x: number; y: number; w: number; h: number }, b: typeof a): boolean =>
    a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  // 枠の真ん中を狙っても、枠の中には入れない（入れると並列の段になって意味が変わるため）
  const f = m.frames[0]!, at = { x: f.x + f.w / 2, y: f.y + f.h / 2 };
  for (let i = 0; i < 10; i++) {
    const kind = (['research', 'branch', 'docs'] as const)[i % 3], z = blockSize(kind);
    const p = freeSpot(m, z, at), r = { x: p.x, y: p.y, ...z };
    const others = [
      ...m.stages.map((s) => ({ x: s.x, y: s.y, ...blockSize(s.kind) })),
      ...m.frames.map((x) => ({ x: x.x, y: x.y, w: x.w, h: x.h })),
      { x: m.start.x, y: m.start.y, w: 132, h: 56 }, { x: m.end.x, y: m.end.y, w: 132, h: 56 },
    ];
    assert.ok(others.every((o) => !over(r, o)), `${i} 個目が重なった`);
    assert.equal(Math.abs(p.x % 10), 0);
    assert.equal(Math.abs(p.y % 10), 0);
    const s = newStage(`n${i}`, kind, `n${i}`);
    s.x = p.x;
    s.y = p.y;
    m.stages.push(s);
    assert.equal(frameOf(m, s), null);
  }
});

test('AC-39: 空いていれば、狙った点を中心に置く', () => {
  const m = newPipe('x'), z = blockSize('research');
  assert.deepEqual(freeSpot(m, z, { x: 300, y: 600 }), { x: 300 - Math.round(z.w / 20) * 10, y: 600 - Math.round(z.h / 20) * 10 });
});
