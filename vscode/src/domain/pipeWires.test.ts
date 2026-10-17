// ケーブルの通り道：段や枠をよけ、同じ通路では高さをずらし、コンセントは入ってくる本数だけ並べる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { autoLayout, blockSize, freeSpot, frameOf, newPipe, newStage, pipeFromFiles } from './pipeModel.ts';
import type { PipeModel, StageModel } from './pipeModel.ts';
import { blockRect, layoutWires, nearestWire } from './pipeWires.ts';
import type { Wire } from './pipeWires.ts';

function stage(over: Partial<StageModel> & { id: string; name: string }): StageModel {
  return {
    kind: 'research', label: over.name, output: `${over.name}.md`, access: 'read', docsDir: '', writes: [], bash: false, review: false,
    model: '', maxTurns: 100, maxBudget: null, prompt: 'x', refs: [], web: 'off', domains: [], mcp: [],
    check: { on: false, verdict: true, command: '', maxRetries: 2 }, onFail: null, next: null, routes: [],
    permissionMode: '', thinking: null, fallbackModel: '', systemAppend: '', addDirs: [], agents: [], mcpServers: [], x: 0, y: 0,
    ...over,
  };
}

/** 一直線の3つ（a → b → c）と、a から c へ飛ぶ分岐。b が途中にあるので、分岐のケーブルは b をよける。 */
function sample(): PipeModel {
  const m = newPipe('wires');
  m.stages = [
    stage({ id: 'a', name: 'a', kind: 'branch', x: 100, y: 100, routes: [{ key: 'one', to: 'b' }, { key: 'two', to: 'c' }] }),
    stage({ id: 'b', name: 'b', x: 400, y: 100, next: 'c' }),
    stage({ id: 'c', name: 'c', x: 700, y: 100, next: 'end', check: { on: true, verdict: true, command: '', maxRetries: 2 }, onFail: 'a' }),
  ];
  m.start = { x: -150, y: 120 };
  m.end = { x: 1000, y: 120 };
  return m;
}

function segmentsHit(points: { x: number; y: number }[], r: { x: number; y: number; w: number; h: number }): boolean {
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1]!, b = points[i]!;
    const n = Math.max(2, Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / 4));
    for (let k = 0; k <= n; k++) {
      const x = a.x + ((b.x - a.x) * k) / n, y = a.y + ((b.y - a.y) * k) / n;
      if (x > r.x && x < r.x + r.w && y > r.y && y < r.y + r.h) return true;
    }
  }
  return false;
}

test('AC-28: ケーブルは、つないでいない段の上を通らない', () => {
  const m = sample();
  for (const w of layoutWires(m)) {
    for (const s of m.stages) {
      if (s.id === w.from || s.id === w.to) continue;
      assert.equal(segmentsHit(w.points, blockRect(m, s.id)), false, `${w.from}→${w.to} が ${s.id} を通る`);
    }
  }
});

test('AC-28: 同じ段へ入るケーブルは、別々のコンセントに差す（高さがずれる）', () => {
  const m = sample();
  const into = layoutWires(m).filter((w) => w.to === 'c' && w.kind !== 'return');
  assert.equal(into.length, 2);
  const ys = into.map((w) => w.points[w.points.length - 1]!.y);
  assert.notEqual(ys[0], ys[1]);
  for (const w of into) assert.equal(w.points[w.points.length - 1]!.x, blockRect(m, 'c').x - 16); // コンセントの面で止まる
});

test('AC-28: 差し戻しは、段の下か上を回って、戻す先のコンセントへ', () => {
  const m = sample();
  const back = layoutWires(m).find((w) => w.kind === 'return')!;
  assert.equal(back.from, 'c');
  assert.equal(back.to, 'a');
  const ra = blockRect(m, 'a'), last = back.points[back.points.length - 1]!;
  assert.ok(last.y > ra.y + ra.h || last.y < ra.y, '戻す先の上か下のコンセントへ差す');
  assert.equal(segmentsHit(back.points, blockRect(m, 'b')), false);
});

test('AC-28: 自動で並べた見本でも、ケーブルが段の上を通らない', () => {
  const m = sample();
  autoLayout(m);
  for (const w of layoutWires(m)) {
    for (const s of m.stages) {
      if (s.id === w.from || s.id === w.to) continue;
      assert.equal(segmentsHit(w.points, blockRect(m, s.id)), false, `${w.from}→${w.to} が ${s.id} を通る`);
    }
  }
});

// 本物の見本を描いて見つかったこと：上の通路で、差し戻しと前へ進むケーブルが近い高さで横に重なっていた。
test('AC-28: 違うケーブルの横の区間は、近い高さで重ならない（差し戻しと前へ進むケーブルも）', async () => {
  const { pipeFromFiles } = await import('./pipeModel.ts');
  const m = pipeFromFiles('w', `[pipe]
kind = "linear"
label = "x"
[[stages]]
name = "triage"
output = "1.md"
prompt = "x"
[stages.routes]
a = "survey"
b = "spec"
none = "end"
[[stages]]
name = "survey"
output = "2.md"
prompt = "x"
[[stages]]
name = "flow"
output = "3.md"
access = "docs"
docs_dir = "d"
group = "g"
prompt = "x"
[[stages]]
name = "seq"
output = "4.md"
access = "docs"
docs_dir = "d"
group = "g"
prompt = "x"
[[stages]]
name = "verify"
output = "5.md"
next = "end"
prompt = "x"
[stages.check]
verdict = true
on_fail = "flow"
[[stages]]
name = "spec"
output = "6.md"
prompt = "x"
`, {}, null);
  const horizontal = layoutWires(m).map((w) => {
    const segs: { y: number; lo: number; hi: number }[] = [];
    for (let i = 1; i < w.points.length; i++) {
      const a = w.points[i - 1]!, b = w.points[i]!;
      if (Math.abs(a.y - b.y) < 0.5 && Math.abs(a.x - b.x) > 30) segs.push({ y: a.y, lo: Math.min(a.x, b.x), hi: Math.max(a.x, b.x) });
    }
    return { id: `${w.kind}:${w.from}→${w.to}`, segs };
  });
  for (let i = 0; i < horizontal.length; i++) {
    for (let j = i + 1; j < horizontal.length; j++) {
      for (const p of horizontal[i]!.segs) {
        for (const q of horizontal[j]!.segs) {
          const overlap = Math.min(p.hi, q.hi) - Math.max(p.lo, q.lo);
          assert.ok(!(Math.abs(p.y - q.y) < 8 && overlap > 20), `${horizontal[i]!.id} と ${horizontal[j]!.id} が y=${p.y} あたりで重なる`);
        }
      }
    }
  }
});

// 本物の画面で見つかったこと：棚から足したブロックの上を、分岐のケーブルが通路へ降りる斜めの区間で横切っていた。
test('AC-40: 棚から足したブロックがあっても、ケーブルは段の上を通らない（通路へ降りる区間も）', () => {
  const m = pipeFromFiles('w', `[pipe]
kind = "linear"
label = "x"
[[stages]]
name = "triage"
output = "1.md"
prompt = "x"
[stages.routes]
a = "survey"
b = "spec"
none = "end"
[[stages]]
name = "survey"
output = "2.md"
prompt = "x"
[[stages]]
name = "flow"
output = "3.md"
access = "docs"
docs_dir = "d"
group = "g"
prompt = "x"
[[stages]]
name = "seq"
output = "4.md"
access = "docs"
docs_dir = "d"
group = "g"
prompt = "x"
[[stages]]
name = "verify"
output = "5.md"
next = "end"
prompt = "x"
[stages.check]
verdict = true
on_fail = "flow"
[[stages]]
name = "spec"
output = "6.md"
prompt = "x"
`, {}, null);
  const xs = m.stages.map((s) => s.x), ys = m.stages.map((s) => s.y);
  const at = { x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2 };
  (['docs', 'research', 'tests', 'code', 'agent', 'verify', 'outside', 'branch'] as const).forEach((kind, i) => {
    const s = newStage(`n${i}`, kind, `n${i}`), p = freeSpot(m, blockSize(kind), at);
    s.x = p.x;
    s.y = p.y;
    m.stages.push(s);
  });
  for (const w of layoutWires(m)) {
    if (w.self) continue;
    for (const s of m.stages) {
      if (s.id === w.from || s.id === w.to || frameOf(m, s)) continue;
      assert.equal(segmentsHit(w.points, blockRect(m, s.id)), false, `${w.kind}:${w.from}→${w.to} が ${s.name} を通る`);
    }
  }
});

test('AC-77: 点の近くを通る「次の段」のケーブルを探す（落とせる先を目立たせるため）', () => {
  const w = (kind: Wire['kind'], points: { x: number; y: number }[]): Wire => ({ kind, from: 'p', to: 'q', points });
  const wires = [
    w('start', [{ x: 0, y: 0 }, { x: 100, y: 0 }]),
    w('next', [{ x: 0, y: 50 }, { x: 100, y: 50 }, { x: 100, y: 150 }]),
    w('route', [{ x: 0, y: 60 }, { x: 100, y: 60 }]),
    w('next', [{ x: 0, y: 200 }, { x: 100, y: 200 }]),
  ];
  assert.equal(nearestWire(wires, { x: 50, y: 52 }, 12), 1);
  assert.equal(nearestWire(wires, { x: 104, y: 120 }, 12), 1); // 曲がったあとの縦の線
  assert.equal(nearestWire(wires, { x: 50, y: 195 }, 12), 3);
  assert.equal(nearestWire(wires, { x: 50, y: 2 }, 12), -1); // 始まりのケーブルには落とさない
  assert.equal(nearestWire(wires, { x: 50, y: 61 }, 3), -1); // 分岐のケーブルにも落とさない
  assert.equal(nearestWire(wires, { x: 500, y: 500 }, 12), -1);
});

// ---- D0005: 自分をやり直す判定は、図にケーブルを描かない ----

test('D0005-AC-01: 判定がオンで onFail が無い段は、差し戻しのケーブルが返らない', () => {
  const m = newPipe('self');
  m.stages = [stage({ id: 'a', name: 'a', x: 100, y: 100, next: 'end', check: { on: true, verdict: true, command: '', maxRetries: 2 }, onFail: null })];
  assert.deepEqual(layoutWires(m).filter((w) => w.kind === 'return'), []);
});

test('D0005-AC-02: onFail が自分の id の段も、差し戻しのケーブルが返らない', () => {
  const m = newPipe('self');
  m.stages = [stage({ id: 'a', name: 'a', x: 100, y: 100, next: 'end', check: { on: true, verdict: true, command: '', maxRetries: 2 }, onFail: 'a' })];
  assert.deepEqual(layoutWires(m).filter((w) => w.kind === 'return'), []);
});

test('D0005-AC-03: 前の段へ戻す段には、B から A への差し戻しが1本返る', () => {
  const m = newPipe('back');
  m.stages = [
    stage({ id: 'a', name: 'a', x: 100, y: 100, next: 'b' }),
    stage({ id: 'b', name: 'b', x: 400, y: 100, next: 'end', check: { on: true, verdict: true, command: '', maxRetries: 2 }, onFail: 'a' }),
  ];
  m.end = { x: 700, y: 120 };
  const back = layoutWires(m).filter((w) => w.kind === 'return');
  assert.equal(back.length, 1);
  assert.equal(back[0]!.from, 'b');
  assert.equal(back[0]!.to, 'a');
});

test('D0005-AC-05: 前の版の pipe.toml（判定オン・on_fail なし）を読んでも、差し戻しのケーブルが返らない', () => {
  const toml = `[pipe]
kind = "linear"
label = "前の版"

[[stages]]
name = "survey"
label = "ソースの調査"
output = "01_survey.md"
access = "read"
review = true
prompt_file = "prompts/01_survey.md"
[stages.check]
verdict = true
max_retries = 2
`;
  const m = pipeFromFiles('old', toml, { 'prompts/01_survey.md': '調べる\n' }, null);
  assert.equal(m.stages[0]!.check.on, true);
  assert.deepEqual(layoutWires(m).filter((w) => w.kind === 'return'), []);
});
