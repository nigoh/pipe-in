// 流す前の費用の目安の計算（D0066）：domain/costEstimate.ts。純粋な関数（ファイル・時計・vscode に触れない）。
// 本体（pipe_in/usage/estimate.py）と同じ決まり・同じ数字。共通の表 tests/fixtures/cost_estimate.json を、本体のテスト（tests/test_cost_estimate.py）と一緒に読む。
// 新しい部品（domain/costEstimate.ts）は、呼んだところで落ちるように、テストの中で読み込む（無いあいだは「まだ作っていない」で落とす）。
// 部品の形（このファイルが決める。実装はこれに合わせる）：
//   PRICES = { as_of: 'YYYY-MM', per_turn: { haiku, sonnet, opus }, note }（単位は units = 1/10000 ドル）・DISCLAIMER
//   familyOf(model: unknown) → { family: 'haiku' | 'sonnet' | 'opus'; unknown: boolean }
//   estimateCost(stages: { name, model, maxTurns, maxBudget, maxRetries }[], today: 'YYYY-MM-DD' | null)
//     → { stages: { name, model, low, high, marks: string[] }[]; low; high; stale: boolean }（印は model_unknown・turns_invalid）
//   ターン上限が null（や読めない値）のときの既定は 100（拡張はパイプだけを扱う）。today が null のときは古さを見ない（stale は偽）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const TABLE = JSON.parse(readFileSync(path.join(HERE, '..', '..', '..', 'tests', 'fixtures', 'cost_estimate.json'), 'utf8')) as {
  prices: { as_of: string; per_turn: Record<string, number> };
  disclaimer: string;
  cases: {
    memo: string;
    today: string;
    stages: { name: string; model: unknown; max_turns: unknown; default_turns: number; max_budget_usd: number | null; max_retries: number }[];
    expect: { stages: { name: string; low: number; high: number; marks: string[] }[]; low: number; high: number; stale: boolean };
  }[];
};

interface StageIn {
  name: string;
  model: unknown;
  maxTurns: unknown;
  maxBudget: number | null;
  maxRetries: number;
}
interface StageOut {
  name: string;
  model?: unknown;
  low: number;
  high: number;
  marks: string[];
}
interface Out {
  stages: StageOut[];
  low: number;
  high: number;
  stale: boolean;
}
interface Mod {
  PRICES: { as_of: string; per_turn: Record<string, number>; note: string };
  DISCLAIMER: string;
  familyOf(model: unknown): { family: string; unknown: boolean };
  estimateCost(stages: StageIn[], today: string | null): Out;
}

async function mod(): Promise<Mod> {
  try {
    return (await import('./costEstimate.ts')) as unknown as Mod;
  } catch (e) {
    return assert.fail(`domain/costEstimate.ts が無い（まだ作っていない）: ${String(e)}`);
  }
}

const TODAY = '2026-11-02';
const stage = (p: Partial<StageIn> = {}): StageIn => ({ name: 'a', model: 'sonnet', maxTurns: 10, maxBudget: null, maxRetries: 0, ...p });
const lowTurns = (t: number): number => Math.floor((t * 20 + 99) / 100);
async function perTurn(family: string): Promise<number> {
  return (await mod()).PRICES.per_turn[family]!;
}
async function one(p: Partial<StageIn>, today: string | null = TODAY): Promise<StageOut> {
  const m = await mod();
  const est = m.estimateCost([stage(p)], today);
  assert.equal(est.stages.length, 1);
  return est.stages[0]!;
}

// ---- AC-17：共通の表のケースで、本体と同じ数字 ----

for (const c of TABLE.cases) {
  test(`D0066-AC-17: 共通の表のケースで本体と同じ数字（1/10000 ドルまで）を出す：${c.memo.slice(0, 40)}`, async () => {
    const m = await mod();
    const est = m.estimateCost(
      c.stages.map((s) => ({ name: s.name, model: s.model, maxTurns: s.max_turns, maxBudget: s.max_budget_usd, maxRetries: s.max_retries })),
      c.today,
    );
    const norm = (list: StageOut[]) => list.map((s) => ({ name: s.name, low: s.low, high: s.high, marks: [...s.marks].sort() }));
    assert.deepEqual(norm(est.stages), norm(c.expect.stages));
    assert.deepEqual([est.low, est.high, est.stale], [c.expect.low, c.expect.high, c.expect.stale]);
  });
}

// ---- AC-18：単価表と文は共通の表と同じ ----

test('D0066-AC-18: PRICES は共通の表と同じ（系統・1 ターンの費用・as_of。片方を変えると落ちる）。注意の文もある', async () => {
  const { PRICES } = await mod();
  assert.equal(PRICES.as_of, TABLE.prices.as_of);
  assert.deepEqual(PRICES.per_turn, TABLE.prices.per_turn);
  assert.ok(PRICES.note.includes('公式の価格表') && PRICES.note.includes('手で'), PRICES.note);
});

test('D0066-AC-18: DISCLAIMER は共通の表の文と一字一句同じ（本体の DISCLAIMER も同じ表）', async () => {
  const { DISCLAIMER } = await mod();
  assert.equal(DISCLAIMER, TABLE.disclaimer);
  assert.ok(DISCLAIMER.includes('約束するものではありません'));
});

// ---- AC-17（個別）：本体の AC-01〜06 と同じ入力 ----

test('D0066-AC-17: 2 段（sonnet・ターン上限 40 と 100・やり直し 0）は、少なめ < 多めで、多めは「ターン上限 × 1 ターンの費用」の合計', async () => {
  const m = await mod();
  const p = await perTurn('sonnet');
  const est = m.estimateCost([stage({ name: 'a', maxTurns: 40 }), stage({ name: 'b', maxTurns: 100 })], TODAY);
  assert.ok(est.low < est.high);
  assert.deepEqual(est.stages.map((s) => s.high), [40 * p, 100 * p]);
  assert.equal(est.high, 140 * p);
  assert.equal(est.low, (lowTurns(40) + lowTurns(100)) * p);
});

test('D0066-AC-17: 費用の上限があると 1 回分が頭打ちで、多めは 上限 ×（1 + やり直し）。少なめも上限を超えない', async () => {
  const p = await perTurn('sonnet');
  const s = await one({ maxTurns: 100, maxBudget: (10 * p) / 10000, maxRetries: 2 });
  assert.equal(s.high, 10 * p * 3);
  assert.equal(s.low, Math.min(lowTurns(100) * p, 10 * p));
  const big = await one({ maxTurns: 100, maxBudget: 1000, maxRetries: 2 });
  assert.equal(big.high, 100 * p * 3);
});

test('D0066-AC-17: やり直し 3 の多めは、やり直し 0 の 4 倍（少なめは同じ）', async () => {
  const zero = await one({ model: 'opus', maxTurns: 20, maxRetries: 0 });
  const three = await one({ model: 'opus', maxTurns: 20, maxRetries: 3 });
  assert.equal(three.high, zero.high * 4);
  assert.equal(three.low, zero.low);
});

const FAMILIES: [string, string][] = [
  ['claude-opus-4-1', 'opus'],
  ['claude-sonnet-4-5', 'sonnet'],
  ['claude-haiku-4-5', 'haiku'],
  ['opus', 'opus'],
  ['sonnet', 'sonnet'],
  ['haiku', 'haiku'],
  ['OPUS', 'opus'],
  ['Claude-Haiku-4-5', 'haiku'],
];
for (const [model, family] of FAMILIES) {
  test(`D0066-AC-17: モデル ${model} は系統 ${family} の 1 ターンの費用で計算し、印は付かない（大文字小文字を区別しない）`, async () => {
    const m = await mod();
    assert.deepEqual(m.familyOf(model), { family, unknown: false });
    const s = await one({ model, maxTurns: 10 });
    assert.equal(s.high, 10 * (await perTurn(family)));
    assert.ok(!s.marks.includes('model_unknown'));
  });
}

for (const model of [null, '', 'gpt-4', 5, ['opus']] as unknown[]) {
  test(`D0066-AC-17: モデル ${JSON.stringify(model)} は sonnet で計算し、model_unknown の印が付く（落ちない）`, async () => {
    const m = await mod();
    assert.deepEqual(m.familyOf(model), { family: 'sonnet', unknown: true });
    const s = await one({ model, maxTurns: 10 });
    assert.equal(s.high, 10 * (await perTurn('sonnet')));
    assert.ok(s.marks.includes('model_unknown'));
  });
}

test('D0066-AC-17: ターン上限が null は既定（100）で印なし。0・負・文字列・真偽・小数は既定に戻して turns_invalid の印（落ちない）', async () => {
  const p = await perTurn('sonnet');
  const none = await one({ maxTurns: null });
  assert.equal(none.high, 100 * p);
  assert.deepEqual(none.marks, []);
  for (const bad of [0, -1, '50', '', true, false, 2.5, [], {}] as unknown[]) {
    const s = await one({ maxTurns: bad });
    assert.equal(s.high, 100 * p, `maxTurns = ${JSON.stringify(bad)}`);
    assert.ok(s.marks.includes('turns_invalid'), `maxTurns = ${JSON.stringify(bad)}`);
  }
});

// ---- AC-21：入力を変えると数字が変わる ----

test('D0066-AC-21: モデルを opus に・ターン上限を増やす・段を足す消すと、数字が変わる（opus と増やした分は増え、段の足す消すは全体に出る）', async () => {
  const m = await mod();
  const base = m.estimateCost([stage({ name: 'a' }), stage({ name: 'b' })], TODAY);
  const opus = m.estimateCost([stage({ name: 'a', model: 'opus' }), stage({ name: 'b' })], TODAY);
  assert.ok(opus.high > base.high && opus.low > base.low, 'opus は sonnet より高い');
  const more = m.estimateCost([stage({ name: 'a', maxTurns: 50 }), stage({ name: 'b' })], TODAY);
  assert.ok(more.high > base.high && more.low > base.low, 'ターン上限を増やすと増える');
  const added = m.estimateCost([stage({ name: 'a' }), stage({ name: 'b' }), stage({ name: 'c' })], TODAY);
  assert.ok(added.high > base.high && added.low > base.low, '段を足すと増える');
  const removed = m.estimateCost([stage({ name: 'a' })], TODAY);
  assert.ok(removed.high < base.high && removed.low < base.low, '段を消すと減る');
  assert.deepEqual(m.estimateCost([], TODAY).stages, [], '段が 0 でも落ちない');
  assert.equal(m.estimateCost([], TODAY).high, 0);
});

// ---- AC-23：印は該当するときだけ ----

test('D0066-AC-23: 古い・モデル不明・ターン上限不正は、該当するときだけ印が付く（古さは 180 日ちょうどが境。today が null なら見ない）', async () => {
  const m = await mod();
  const day = new Date(`${m.PRICES.as_of}-01T00:00:00Z`); // テストの中で日付を作るだけ（部品は Date を使わない）
  const iso = (offset: number) => new Date(day.getTime() + offset * 86400000).toISOString().slice(0, 10);
  assert.equal(m.estimateCost([stage()], iso(180)).stale, false, '180 日ちょうどは古くない');
  assert.equal(m.estimateCost([stage()], iso(181)).stale, true, '181 日目は古い');
  assert.equal(m.estimateCost([stage()], null).stale, false, 'today が null なら古さを見ない');
  const clean = m.estimateCost([stage()], TODAY);
  assert.deepEqual(clean.stages[0]!.marks, []);
  assert.equal(clean.stale, false);
  assert.deepEqual(m.estimateCost([stage({ model: null })], TODAY).stages[0]!.marks, ['model_unknown']);
  assert.deepEqual(m.estimateCost([stage({ maxTurns: 0 })], TODAY).stages[0]!.marks, ['turns_invalid']);
});

test('D0066-AC-23: 印は段ごと（1 つの段の印がほかの段に付かない）', async () => {
  const m = await mod();
  const est = m.estimateCost([stage({ name: 'a', model: null }), stage({ name: 'b' }), stage({ name: 'c', maxTurns: -1 })], TODAY);
  assert.deepEqual(est.stages.map((s) => s.marks), [['model_unknown'], [], ['turns_invalid']]);
});

// ---- AC-19：ファイル・時計・vscode に触れない ----

test('D0066-AC-19: ソースに Date・setTimeout・Math.random・node:fs・child_process・vscode が無い（今日は引数）', () => {
  const file = path.join(HERE, 'costEstimate.ts');
  assert.ok(existsSync(file), 'domain/costEstimate.ts が無い（まだ作っていない）');
  const code = readFileSync(file, 'utf8').replace(/^[ \t]*\/\*[\s\S]*?\*\//gm, '').replace(/^[ \t]*\/\/.*$/gm, '');
  assert.doesNotMatch(code, /\b(?:Date|setTimeout|setInterval|setImmediate|performance)\b/);
  assert.doesNotMatch(code, /Math\.random/);
  assert.doesNotMatch(code, /node:fs|from\s+['"]fs|child_process|from\s+['"]vscode['"]/);
  assert.doesNotMatch(code, /from\s+['"]node:(?!path)/);
});
