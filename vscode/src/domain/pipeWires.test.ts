// ケーブルの通り道：段や枠をよけ、同じ通路では高さをずらし、コンセントは入ってくる本数だけ並べる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { autoLayout, blockSize, freeSpot, frameOf, newPipe, newStage, pipeFromFiles } from './pipeModel.ts';
import type { PipeModel, StageModel } from './pipeModel.ts';
import { blockRect, cablePath, curvePoints, layoutWires, nearestWire, roundedPath, smoothPath } from './pipeWires.ts';
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

// ---- D0007：流線型のケーブルと、ひもの曲線 ----

/** path の文字列の数を読む（M x y C c1x c1y c2x c2y x y …） */
const nums = (d: string): number[] => (d.match(/-?\d+(\.\d+)?(e-?\d+)?/g) ?? []).map(Number);
/** 各 C の終わりの点 */
const cEnds = (d: string): { x: number; y: number }[] =>
  [...d.matchAll(/C\s*([^A-Za-z]+)/g)].map((m) => { const n = m[1]!.trim().split(/[\s,]+/).map(Number); return { x: n[4]!, y: n[5]! }; });
const near = (a: { x: number; y: number }, b: { x: number; y: number }, e = 1e-6): boolean => Math.abs(a.x - b.x) < e && Math.abs(a.y - b.y) < e;

test('D0007-AC-30・32: ひもの曲線（smoothPath）と置いたケーブル（cablePath）は、M で始まり曲線の命令を持ち、最後の点で終わる（2点・同じ点の続き・3点以上）', () => {
  const cases = [
    [{ x: 0, y: 0 }, { x: 100, y: 0 }],
    [{ x: 0, y: 0 }, { x: 0, y: 0 }, { x: 50, y: 20 }],
    [{ x: 0, y: 0 }, { x: 40, y: 30 }, { x: 80, y: -10 }, { x: 120, y: 5 }],
    [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 100 }, { x: 200, y: 100 }],
  ];
  for (const pts of cases) {
    for (const d of [smoothPath(pts), cablePath(pts)]) {
      assert.match(d, /^M\s*-?[\d.]+[\s,]+-?[\d.]+/, d);
      assert.match(d, /[CQ]/, d);
      assert.ok(nums(d).every(Number.isFinite), d);
      const n = nums(d), last = pts.at(-1)!;
      assert.deepEqual([n.at(-2), n.at(-1)], [last.x, last.y], d);
      assert.deepEqual([n[0], n[1]], [pts[0]!.x, pts[0]!.y], d);
    }
  }
});

test('D0007-AC-31: ひもの曲線は、渡した点をすべて順に通る（区間ごとの終わりが渡した点）', () => {
  const pts = [{ x: 0, y: 0 }, { x: 40, y: 30 }, { x: 80, y: -10 }, { x: 120, y: 5 }, { x: 160, y: 40 }];
  const ends = cEnds(smoothPath(pts));
  assert.equal(ends.length, pts.length - 1);
  ends.forEach((e, i) => assert.ok(near(e, pts[i + 1]!), `${i}: ${JSON.stringify(e)}`));
});

test('D0007-AC-33: 置いたケーブルの終わりは、次の段・分岐なら右向き、差し戻しなら縦向きでコンセントに入る', () => {
  const m = sample();
  for (const w of layoutWires(m)) {
    if (w.kind === 'start') continue;
    const c = curvePoints(w.points), a = c.at(-2)!, b = c.at(-1)!;
    assert.deepEqual(b, w.points.at(-1));
    if (w.kind === 'return') assert.ok(Math.abs(b.x - a.x) < 1e-6 && Math.abs(b.y - a.y) > 0, `${w.from}→${w.to}`);
    else assert.ok(Math.abs(b.y - a.y) < 1e-6 && b.x > a.x, `${w.from}→${w.to}`);
  }
});

test('D0007-AC-34: 間に挟む先は、描いた曲線との距離で探す（角の内側の曲線の近くでは見つかり、曲線から離れた角の外では見つからない）', () => {
  const w: Wire = { kind: 'next', from: 'p', to: 'q', points: [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 100 }] };
  // 角 (100, 0) は曲線で内側へ回るので、角そのものは曲線から離れる
  const c = curvePoints(w.points);
  const dist = (p: { x: number; y: number }): number => Math.min(...c.map((q) => Math.hypot(q.x - p.x, q.y - p.y)));
  const inner = c.reduce((best, q) => (Math.hypot(q.x - 100, q.y) < Math.hypot(best.x - 100, best.y) ? q : best));
  assert.ok(dist({ x: 100, y: 0 }) > 6, '角そのものは曲線から離れている');
  assert.equal(nearestWire([w], { x: inner.x - 1, y: inner.y + 1 }, 4), 0);
  assert.equal(nearestWire([w], { x: 100, y: 0 }, 4), -1);
});

test('D0007-AC-36（画面で見つけた不具合）：動かしている、つながっていない段はよける相手から外せる（ケーブルの上に重ねても逃げない）', () => {
  const m = sample(), before = layoutWires(m);
  // b → c のケーブルの上に、つながっていない段 n を重ねる
  m.stages.push(stage({ id: 'n', name: 'n', x: 560, y: 90 }));
  const avoided = layoutWires(m);
  assert.notDeepEqual(avoided.map((w) => w.points), before.map((w) => w.points), 'ふつうは n をよける');
  assert.deepEqual(layoutWires(m, { ignore: 'n' }).map((w) => w.points), before.map((w) => w.points));
});

test('D0007-AC-40: 置いたケーブルは、今の丸め（9px）より大きく角を回る。それでも段の四角には入らない', () => {
  const pts = [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 100 }];
  const gap = (d: { x: number; y: number }[]): number => Math.min(...d.map((q) => Math.hypot(q.x - 100, q.y)));
  // 今の roundedPath（Q 1つ）の、角に最も近い点：Q の中点
  const q = nums(roundedPath(pts));
  const oldMid = { x: 0.25 * q[2]! + 0.5 * q[4]! + 0.25 * q[6]!, y: 0.25 * q[3]! + 0.5 * q[5]! + 0.25 * q[7]! };
  assert.ok(gap(curvePoints(pts)) > gap([oldMid]) + 3, `新 ${gap(curvePoints(pts))} / 今 ${gap([oldMid])}`);
  assert.match(cablePath(pts), /C/);
  // 見本（そのまま・自動で並べたもの）で、曲線の点がつないでいない段の上を通らない
  for (const m of [sample(), autoLayout(sample())]) {
    for (const w of layoutWires(m)) {
      for (const s of m.stages) {
        if (s.id === w.from || s.id === w.to) continue;
        assert.equal(segmentsHit(curvePoints(w.points), blockRect(m, s.id)), false, `${w.from}→${w.to} が ${s.id} を通る`);
      }
    }
  }
});
