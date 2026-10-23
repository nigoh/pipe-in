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
import type { CheckModel, PipeModel } from './pipeModel.ts';
import { setCheck } from './pipeCheck.ts';
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

test('AC-25: 検査は pipe-in-gen check と同じ決まり（主なもの）と、作業台で起きやすい誤り', () => {
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

// ---- D0005-AC-17: 判定の保存の形は、前の版と同じ ----

/** pipe.toml の文から、[stages.check] の表を1つずつ取り出す */
function checkTables(toml: string): string[] {
  const out: string[] = [];
  let cur: string[] | null = null;
  for (const l of toml.split('\n')) {
    if (l.startsWith('[')) {
      if (cur) out.push(cur.join('\n').trim());
      cur = l === '[stages.check]' ? [l] : null;
    } else if (cur) cur.push(l);
  }
  if (cur) out.push(cur.join('\n').trim());
  return out;
}

test('D0005-AC-17: 自分をやり直す・前の段へ戻す・判定オフの段の [stages.check] は、前の版と同じ形で保存する', () => {
  const m = newPipe('keep');
  m.stages = [
    { ...newStage('a', 'research', 'a'), prompt: 'x', x: 100, y: 100, next: 'b' },
    { ...newStage('b', 'research', 'b'), prompt: 'x', x: 400, y: 100, next: 'c', check: { on: true, verdict: true, command: '', maxRetries: 2 } },
    { ...newStage('c', 'research', 'c'), prompt: 'x', x: 700, y: 100, next: 'end', check: { on: true, verdict: false, command: 'npm test', maxRetries: 3 }, onFail: 'a' },
  ];
  m.end = { x: 1000, y: 120 };
  const files = pipeFiles(m), toml = files['pipe.toml']!;
  assert.deepEqual(checkTables(toml), [
    '[stages.check]\nverdict = true\nmax_retries = 2',
    '[stages.check]\ncommand = "npm test"\non_fail = "a"\nmax_retries = 3',
  ]);
  const again = pipeFromFiles('keep', toml, files, null);
  const nameOf = (id: string | null): string | null => (id ? again.stages.find((s) => s.id === id)?.name ?? id : null);
  assert.deepEqual(again.stages.map((s) => [s.name, s.check.on, s.check.verdict, s.check.command, s.check.maxRetries, nameOf(s.onFail)]), [
    ['a', false, false, '', 2, null], ['b', true, true, '', 2, null], ['c', true, false, 'npm test', 3, 'a'],
  ]);
});

test('D0007-AC-37: 保存の形は変わらない（layout.json はブロックの位置と形だけで、ケーブルの形やひもの状態を書かない）', () => {
  const files = pipeFiles(load());
  assert.deepEqual(Object.keys(files).filter((f) => !f.startsWith('prompts/')).sort(), ['layout.json', 'pipe.toml']);
  const layout = JSON.parse(files['layout.json']!);
  assert.deepEqual(Object.keys(layout).sort(), ['end', 'frames', 'stages', 'start']);
  for (const v of Object.values(layout.stages as Record<string, object>)) assert.deepEqual(Object.keys(v).sort(), ['kind', 'x', 'y']);
  assert.doesNotMatch(files['pipe.toml']!, /cable|rope|wire/i);
});

// ---- D0028: 検証の審査（[stages.check.judge]）を、知らないまま守る ----

const JUDGE_HEAD = `[pipe]
kind = "linear"
label = "審査つき"

[[stages]]
name = "draw"
label = "書く"
output = "01_draw.md"
access = "read"
prompt_file = "prompts/01_draw.md"

[[stages]]
name = "verify"
label = "確かめ"
output = "02_verify.md"
access = "read"
prompt_file = "prompts/02_verify.md"
`;
const JUDGE_PROMPTS: Record<string, string> = { 'prompts/01_draw.md': '書く\n', 'prompts/02_verify.md': '審査する\n' };
const JUDGE_BODY = `[stages.check.judge]
threshold = 0.8
[[stages.check.judge.criteria]]
name = "clarity"
description = "読みやすい"
[[stages.check.judge.criteria]]
name = "accuracy"
description = "事実に合っている"
[[stages.check.judge.must]]
name = "safe"
description = "秘密を書かない"
`;
/** verdict・on_fail・max_retries と審査を並べて書いた pipe.toml */
const JUDGE_TOML = JUDGE_HEAD + `[stages.check]\nverdict = true\non_fail = "draw"\nmax_retries = 2\n` + JUDGE_BODY;
/** 審査だけ（verdict も command も無い） */
const JUDGE_ONLY_TOML = JUDGE_HEAD + `[stages.check]\n` + JUDGE_BODY;
/** 拡張が知らないキー・入れ子の表・配列を、judge の中に持つもの */
const JUDGE_UNKNOWN_TOML = JUDGE_HEAD + `[stages.check]
verdict = true
max_retries = 1
[stages.check.judge]
threshold = 0.65
weight = 2
note = "メモ"
tags = ["a", "b"]
ratio = 0.5
strict = true
[stages.check.judge.extra]
level = 3
flag = false
label = "入れ子"
[[stages.check.judge.criteria]]
name = "clarity"
description = "読みやすい"
hint = "見出しを見る"
weights = [1, 2]
[[stages.check.judge.criteria]]
name = "accuracy"
description = "事実に合っている"
[[stages.check.judge.must]]
name = "safe"
description = "秘密を書かない"
severity = "high"
`;

const judgeOf = (toml: string): unknown => ((parseToml(toml).stages as Record<string, unknown>[])[1]!.check as Record<string, unknown>).judge;
const loadJudge = (toml: string): PipeModel => pipeFromFiles('judge', toml, JUDGE_PROMPTS, null);

test('D0028-AC-25: judge を持つ check を読んで書くと judge が残る', () => {
  const m = loadJudge(JUDGE_TOML);
  const files = pipeFiles(m);
  const toml = files['pipe.toml']!;
  assert.match(toml, /^\[stages\.check\.judge\]$/m);
  assert.equal((toml.match(/^\[\[stages\.check\.judge\.criteria\]\]$/gm) ?? []).length, 2);
  assert.equal((toml.match(/^\[\[stages\.check\.judge\.must\]\]$/gm) ?? []).length, 1);
  assert.deepEqual(judgeOf(toml), judgeOf(JUDGE_TOML));
  assert.deepEqual(judgeOf(toml), {
    threshold: 0.8,
    criteria: [{ name: 'clarity', description: '読みやすい' }, { name: 'accuracy', description: '事実に合っている' }],
    must: [{ name: 'safe', description: '秘密を書かない' }],
  });
  // verdict / on_fail / max_retries の書き出しは今のまま
  assert.deepEqual(checkTables(toml), ['[stages.check]\nverdict = true\non_fail = "draw"\nmax_retries = 2']);
  // 往復しても同じ（2回目の書き出しが1回目と変わらない）
  const again = pipeFromFiles('judge', toml, files, files['layout.json']!);
  assert.deepEqual(pipeFiles(again), files);
});

test('D0028-AC-25: judge だけの check（verdict も command も無い）も、読んで書くと judge が残る', () => {
  const m = loadJudge(JUDGE_ONLY_TOML);
  const s = byName(m, 'verify');
  assert.equal(s.check.on, true);
  assert.equal(s.check.verdict, false);
  assert.equal(s.check.command, '');
  const toml = pipeFiles(m)['pipe.toml']!;
  assert.deepEqual(judgeOf(toml), judgeOf(JUDGE_ONLY_TOML));
  assert.deepEqual(checkTables(toml), ['[stages.check]\nmax_retries = 2']);
});

test('D0028-AC-25: 読んだ judge は check.judge に表として持ち、読み直しても同じ書き出しになる', () => {
  const m = loadJudge(JUDGE_TOML);
  const judge = byName(m, 'verify').check.judge as unknown as { threshold: number; criteria: { name: string }[] };
  assert.ok(judge, 'check.judge に表を持つ');
  assert.equal(judge.threshold, 0.8);
  assert.equal(judge.criteria.length, 2);
  const a = pipeFiles(m)['pipe.toml']!;
  const b = pipeFiles(loadJudge(JUDGE_TOML))['pipe.toml']!;
  assert.equal(a, b);
});

test('D0028-AC-25: check を切ると judge は書き出さず、入れ直すと戻る（持ち続ける）', () => {
  const m = loadJudge(JUDGE_TOML);
  const s = byName(m, 'verify');
  setCheck(s, false);
  assert.ok(s.check.judge, '切っても judge は持ち続ける');
  assert.doesNotMatch(pipeFiles(m)['pipe.toml']!, /judge/);
  setCheck(s, true);
  assert.deepEqual(judgeOf(pipeFiles(m)['pipe.toml']!), judgeOf(JUDGE_TOML));
});

test('D0028-AC-26: judge の中の知らないキーも往復で変わらない', () => {
  const m = loadJudge(JUDGE_UNKNOWN_TOML);
  const files = pipeFiles(m);
  const toml = files['pipe.toml']!;
  assert.deepEqual(judgeOf(toml), judgeOf(JUDGE_UNKNOWN_TOML));
  const j = judgeOf(toml) as Record<string, unknown>;
  assert.equal(j.weight, 2);
  assert.equal(j.note, 'メモ');
  assert.deepEqual(j.tags, ['a', 'b']);
  assert.equal(j.ratio, 0.5);
  assert.equal(j.strict, true);
  assert.deepEqual(j.extra, { level: 3, flag: false, label: '入れ子' });
  assert.deepEqual((j.criteria as Record<string, unknown>[])[0], { name: 'clarity', description: '読みやすい', hint: '見出しを見る', weights: [1, 2] });
  assert.deepEqual((j.must as Record<string, unknown>[])[0], { name: 'safe', description: '秘密を書かない', severity: 'high' });
  assert.deepEqual(checkTables(toml), ['[stages.check]\nverdict = true\nmax_retries = 1']);
  const again = pipeFromFiles('judge', toml, files, files['layout.json']!);
  assert.deepEqual(pipeFiles(again), files);
});

test('D0028-AC-27: judge だけの check は「判定か…」を出さず、何も無い check は出す', () => {
  const only = loadJudge(JUDGE_ONLY_TOML);
  assert.deepEqual(validatePipe(only).errors.filter((e) => e.includes('検証には')), []);
  assert.deepEqual(validatePipe(only).errors, []);
  // judge・verdict・command のどれも無い check は、今と同じく誤りを出す
  const none = loadJudge(JUDGE_HEAD + '[stages.check]\nmax_retries = 2\n');
  assert.ok(validatePipe(none).errors.some((e) => e.includes('検証には')), '何も無い check は誤り');
  const stripped = loadJudge(JUDGE_ONLY_TOML);
  byName(stripped, 'verify').check.judge = null;
  assert.ok(validatePipe(stripped).errors.some((e) => e.includes('検証には')), 'judge を外すと誤り');
});

test('D0028-AC-27: 何も無い check の誤りの文は、審査も書けることを含む', () => {
  const none = loadJudge(JUDGE_HEAD + '[stages.check]\nmax_retries = 2\n');
  assert.ok(validatePipe(none).errors.some((e) => e.includes('検証には') && e.includes('審査')), validatePipe(none).errors.join('\n'));
});

test('D0028-AC-28: judge の無い pipe.toml の読み書き・検査は変わらない（check.judge は null）', () => {
  const m = load();
  for (const s of m.stages) assert.equal(s.check.judge, null, `${s.name} の check.judge は null`);
  const toml = pipeFiles(m)['pipe.toml']!;
  assert.doesNotMatch(toml, /judge/);
  assert.deepEqual(validatePipe(m).errors, []);
  assert.deepEqual(parseToml(toml).stages && (parseToml(toml).stages as Record<string, unknown>[])[4]!.check, { verdict: true, on_fail: 'flow', max_retries: 2 });
});

test('D0028-AC-28: judge の項目が無い（古い形の）check の書き出しも変わらない（守り続けるための検査。今も通る）', () => {
  const m = newPipe('keep');
  // judge を持たない古い形のオブジェクト（as で judge を省く）でも書き出せる
  const oldCheck = { on: true, verdict: true, command: '', maxRetries: 2 } as unknown as CheckModel;
  m.stages = [{ ...newStage('a', 'research', 'a'), prompt: 'x', x: 100, y: 100, next: 'end', check: oldCheck }];
  m.end = { x: 400, y: 120 };
  const toml = pipeFiles(m)['pipe.toml']!;
  assert.doesNotMatch(toml, /judge/);
  assert.deepEqual(checkTables(toml), ['[stages.check]\nverdict = true\nmax_retries = 2']);
});
