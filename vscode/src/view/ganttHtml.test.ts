// 時系列（D0019・3版目：HTML の並びで描く）。モデル（GanttModel）を手で作って、描かれ方を文字列で確かめる（純粋）。
// 行の名前・文字は HTML の文字（元の大きさの px）。帯と横軸の目盛りだけが、枠の幅に合わせて伸び縮みする（位置と幅は % で表す）。
// 帯の位置と幅の出し方は 2 通りのどちらでも通る：
//   (a) サーバー側で作る CSS の規則（行ごとの id かクラスに left / width の % を書く。nonce つきの <style> の中）
//   (b) 帯の部分だけの SVG（preserveAspectRatio="none"）の x / width（viewBox の幅に対する割合）
// style 属性は使わない（CSP）。% で縮まない文字は HTML に置く。
// 決めた印：時系列の外側の要素は class に `gantt` を持ち aria-label="時系列"。行は class `g-row`。
//   「確認待ち …」「● 待っている」を持つ要素は data-side="left"（帯の左）か "right"（帯の右）を持つ。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { GanttModel, GanttRow } from '../domain/gantt.ts';
import { escapeHtml } from './escape.ts';
import { extractCss, parseCss } from '../test/cssBlocks.ts';

const mod = () => import('./ganttHtml.ts');
const render = async (g: GanttModel): Promise<string> => (await mod()).renderGantt(g);

const gRow = (p: Partial<GanttRow> & { seq: number; label: string }): GanttRow => ({ agent: null, run: null, wait: null, ...p });
const gModel = (rows: GanttRow[], p: Partial<GanttModel> = {}): GanttModel => ({
  rows,
  omittedRows: 0,
  totalSec: 100,
  ticks: [20, 40, 60, 80, 100],
  live: false,
  hasTimes: true,
  ...p,
});
const runBar = (startSec: number, endSec: number, p: { failed?: boolean; live?: boolean } = {}) => ({ startSec, endSec, failed: p.failed ?? false, live: p.live ?? false });
const waitBar = (startSec: number, endSec: number, live = false) => ({ startSec, endSec, live });

const count = (text: string, re: RegExp): number => (text.match(re) ?? []).length;
const plain = (text: string): string => text.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
/** 見える文字だけ（<title> の中身は除く） */
const visible = (text: string): string => plain(text.replace(/<title>[\s\S]*?<\/title>/g, ''));
const near = (a: number, b: number, tol = 0.5): void => assert.ok(Math.abs(a - b) <= tol, `${a} ≈ ${b}`);

// ---- 要素を取り出す小さな補助 ----

interface El {
  name: string;
  attrs: string;
  index: number;
  inner: string;
}

const attrOf = (attrs: string, name: string): string | undefined => new RegExp(`(?:^|\\s)${name}="([^"]*)"`).exec(attrs)?.[1];

/** out の中の、条件に合う要素（子孫の同名要素を数えて、閉じるタグまでを inner にする） */
function elements(out: string, want: (name: string, attrs: string) => boolean): El[] {
  const found: El[] = [];
  for (const m of out.matchAll(/<([a-zA-Z][\w-]*)\b([^>]*?)(\/?)>/g)) {
    const name = m[1]!;
    const attrs = m[2]!;
    if (!want(name, attrs)) continue;
    let inner = '';
    if (m[3] !== '/') {
      const from = m.index! + m[0].length;
      const re = new RegExp(`<(/?)${name}\\b[^>]*?(/?)>`, 'g');
      re.lastIndex = from;
      let depth = 1;
      let end = out.length;
      for (let n = re.exec(out); n !== null; n = re.exec(out)) {
        if (n[2] === '/') continue;
        depth += n[1] === '/' ? -1 : 1;
        if (depth === 0) {
          end = n.index;
          break;
        }
      }
      inner = out.slice(from, end);
    }
    found.push({ name, attrs, index: m.index!, inner });
  }
  return found;
}
const hasClass = (attrs: string, token: string): boolean => (attrOf(attrs, 'class') ?? '').split(/\s+/).includes(token);
const byClass = (out: string, token: string): El[] => elements(out, (_n, a) => hasClass(a, token));

/** 出力の中の CSS（<style> の中）と GANTT_STYLE を合わせた規則 */
async function allRules(out: string) {
  const { GANTT_STYLE } = await mod();
  return parseCss(`${extractCss(out)}\n${GANTT_STYLE}`).filter((r) => !r.keyframes);
}

const pctOf = (body: string, prop: string): number | null => {
  const m = new RegExp(`(?<![-\\w])${prop}\\s*:\\s*(-?[\\d.]+)%`).exec(body);
  return m ? Number(m[1]) : null;
};

/** 要素の位置を、全体に対する割合（%）で返す。(a) CSS の left / width か (b) SVG の x / width ÷ viewBox の幅。無ければ null。 */
async function geom(out: string, el: El): Promise<{ left: number; width: number | null } | null> {
  const rules = await allRules(out);
  const id = attrOf(el.attrs, 'id');
  const classes = (attrOf(el.attrs, 'class') ?? '').split(/\s+/).filter(Boolean);
  let left: number | null = null;
  let width: number | null = null;
  for (const r of rules) {
    const mine = r.selector.split(',').some((sel) => {
      const last = sel.trim().split(/\s+/).pop() ?? '';
      return (id !== undefined && new RegExp(`#${id}(?![\\w-])`).test(last)) || classes.some((c) => new RegExp(`\\.${c}(?![\\w-])`).test(last));
    });
    if (!mine) continue;
    left = pctOf(r.body, 'left') ?? left;
    width = pctOf(r.body, 'width') ?? width;
  }
  if (left !== null) return { left, width };
  const x = attrOf(el.attrs, 'x');
  if (x === undefined) return null;
  const svgs = elements(out.slice(0, el.index), (n) => n === 'svg').filter((s) => !out.slice(s.index, el.index).includes('</svg>'));
  const vb = svgs.length > 0 ? /viewBox="\s*[\d.]+\s+[\d.]+\s+([\d.]+)/.exec(svgs[svgs.length - 1]!.attrs)?.[1] : undefined;
  if (vb === undefined) return null;
  const w = attrOf(el.attrs, 'width');
  return { left: (Number(x) / Number(vb)) * 100, width: w === undefined ? null : (Number(w) / Number(vb)) * 100 };
}

const NO_GEOM = { left: Number.NaN, width: Number.NaN };

const SAMPLE = gModel(
  [
    gRow({ seq: 1, label: '要件定義', agent: 'pipe-in-analyst', run: runBar(10, 40), wait: waitBar(40, 60) }),
    gRow({ seq: 2, label: '検証 1 回目', agent: 'pipe-in-verifier', run: runBar(70, 90, { failed: true }) }),
    gRow({ seq: 3, label: '実装 2 回目', agent: null, run: null }),
  ],
  { totalSec: 100 },
);

// ---- 見出し・枠 ----

test('D0019-AC-77: 見出し「時系列」（h2.terminal-title）と「N 回の実行・合計 m:ss」。本体は class gantt・aria-label="時系列" の HTML の枠で、固定の幅 740 の SVG ではない', async () => {
  const out = await render(SAMPLE);
  assert.match(out, /<h2 class="terminal-title">時系列<\/h2>/);
  assert.match(plain(out), /3 回の実行・合計 1:40/);
  const roots = elements(out, (_n, a) => hasClass(a, 'gantt') && attrOf(a, 'aria-label') === '時系列');
  assert.equal(roots.length, 1, 'class gantt・aria-label="時系列" の枠が 1 つ');
  assert.notEqual(roots[0]!.name, 'svg', '外側は HTML');
  assert.doesNotMatch(out, /viewBox="\s*0\s+0\s+740\b/, '幅 740 の座標の SVG ではない');
  assert.doesNotMatch(out, /class="gantt-svg"/);
});

test('D0019-AC-77: 行（.g-row）は実行の数だけ、seq の順に出る。名前は「段 回 · 受け持ち」で、受け持ちが無い行は「 · 受け持ち」を省く', async () => {
  const out = await render(SAMPLE);
  assert.equal(byClass(out, 'g-row').length, 3);
  const t = visible(out);
  const a = t.indexOf('要件定義');
  const b = t.indexOf('検証 1 回目');
  const c = t.indexOf('実装 2 回目');
  assert.ok(a >= 0 && b > a && c > b, '行の順');
  assert.match(t, /要件定義 · pipe-in-analyst/);
  assert.match(t, /検証 1 回目 · pipe-in-verifier/);
  const rows = byClass(out, 'g-row');
  const third = visible(rows[2]!.inner);
  assert.match(third, /実装 2 回目/);
  assert.doesNotMatch(third.replace('時刻の記録なし', ''), /pipe-in|·|・/, '受け持ちが無い行は、段と回だけ');
});

test('D0019-AC-77: 長い名前は 26 文字ほどで「…」にして、全文は title（<title> か title 属性）に入れる', async () => {
  const long = '図とソースの突き合わせを丁寧に何度も繰り返す長い段の名前';
  const out = await render(gModel([gRow({ seq: 1, label: long, agent: 'pipe-in-verifier', run: runBar(0, 50) })]));
  const shown = /図とソース[^\s<]*…/.exec(visible(out))?.[0];
  assert.ok(shown, '「…」で切った名前が見える');
  assert.ok(Array.from(shown).length <= 28, `表示は短く切る: ${shown}`);
  assert.ok(!visible(out).includes(long), '見える所に全文は出ない');
  assert.match(out, new RegExp(`(<title>[^<]*${long}[^<]*</title>|\\btitle="[^"]*${long}[^"]*")`));
});

// ---- 帯：位置と幅は割合（%） ----

test('D0019-AC-69: エージェントの帯（.g-run）の位置と幅は、全体に対する割合（全体 100 秒・10〜40 秒 → left 10%・width 30%）。時間の文字は m:ss', async () => {
  const out = await render(gModel([gRow({ seq: 1, label: '設計', run: runBar(10, 40) })], { totalSec: 100 }));
  const [bar] = byClass(out, 'g-run');
  assert.ok(bar, '帯がある');
  const g = (await geom(out, bar)) ?? NO_GEOM;
  near(g.left, 10);
  near(g.width ?? Number.NaN, 30);
  assert.ok(visible(out).includes('0:30'), '帯の時間 0:30');
});

test('D0019-AC-69: 全体 100 秒・30〜60 秒の帯は left 30%・width 30%。全体が 1000 秒なら 300〜600 秒が同じ割合', async () => {
  for (const [total, s, e] of [[100, 30, 60], [1000, 300, 600]] as const) {
    const out = await render(gModel([gRow({ seq: 1, label: '設計', run: runBar(s, e) })], { totalSec: total, ticks: [] }));
    const g = (await geom(out, byClass(out, 'g-run')[0]!)) ?? NO_GEOM;
    near(g.left, 30);
    near(g.width ?? Number.NaN, 30);
  }
});

test('D0019-AC-69: 帯の時間の文字は、広い帯でも狭い帯でも出る（6:40・0:30）。位置は帯の割合から決まり、px の座標ではない', async () => {
  const out = await render(gModel([gRow({ seq: 1, label: '広い', run: runBar(0, 400) }), gRow({ seq: 2, label: '狭い', run: runBar(500, 530) })], { totalSec: 1000 }));
  const t = visible(out);
  assert.ok(t.includes('6:40') && t.includes('0:30'));
  const [wide, narrow] = byClass(out, 'g-run');
  const gw = (await geom(out, wide!)) ?? NO_GEOM;
  const gn = (await geom(out, narrow!)) ?? NO_GEOM;
  near(gw.width ?? Number.NaN, 40);
  near(gn.left, 50);
  near(gn.width ?? Number.NaN, 3);
});

test('D0019-AC-71: 失敗（failed）の帯だけ .g-fail（赤）のクラスが付く。位置は割合で正しい。ほかの帯には付かない', async () => {
  const out = await render(SAMPLE);
  const fails = byClass(out, 'g-fail');
  assert.equal(fails.length, 1);
  near(((await geom(out, fails[0]!)) ?? NO_GEOM).left, 70);
  assert.equal(byClass(out, 'g-run').length, 2, '失敗の帯も g-run のクラスを持つ（塗りの基本）');
  const ok = await render(gModel([gRow({ seq: 1, label: '設計', run: runBar(0, 50) })]));
  assert.equal(byClass(ok, 'g-fail').length, 0);
});

test('D0019-AC-70: 確認の待ちの帯は、帯とは別の要素（.g-wait）で、位置と幅が割合（40〜60 秒 → left 40%・width 20%）。「確認待ち m:ss」が出る。斜線の塗りは CSS の .g-wait に書く', async () => {
  const out = await render(SAMPLE);
  const [wait] = byClass(out, 'g-wait');
  assert.ok(wait, '待ちの帯がある');
  const g = (await geom(out, wait)) ?? NO_GEOM;
  near(g.left, 40);
  near(g.width ?? Number.NaN, 20);
  assert.notEqual(byClass(out, 'g-run')[0]!.index, wait.index, '帯とは別の要素');
  assert.match(visible(out), /確認待ち 0:20/);
  const rules = await allRules(out);
  assert.ok(rules.some((r) => /\.g-wait\b/.test(r.selector) && /repeating-linear-gradient|gantt-hatch/.test(r.body)), '待ちの帯は斜線の模様');
});

test('D0019-AC-70: 待ちの帯が無い行に、待ちの要素は出ない。待ちの帯を持つ行の数だけ .g-wait がある', async () => {
  const out = await render(gModel([gRow({ seq: 1, label: 'a', run: runBar(0, 10) }), gRow({ seq: 2, label: 'b', run: runBar(20, 30), wait: waitBar(30, 50) })]));
  assert.equal(byClass(out, 'g-wait').length, 1);
  assert.equal(count(visible(out), /確認待ち \d/g), 1);
});

test('D0019-AC-69: 動いている帯には外側の輪（.g-ring）と「● 動いている」、いま待っている帯には輪と「● 待っている」が付く。live でなければ付かない', async () => {
  const live = await render(
    gModel([gRow({ seq: 1, label: 'a', run: runBar(0, 40) }), gRow({ seq: 2, label: 'b', run: runBar(40, 70, { live: true }) }), gRow({ seq: 3, label: 'c', run: runBar(0, 20), wait: waitBar(20, 100, true) })], { live: true }),
  );
  assert.equal(byClass(live, 'g-ring').length, 2);
  assert.equal(count(visible(live), /● 動いている/g), 1);
  assert.equal(count(visible(live), /● 待っている/g), 1);
  const still = await render(SAMPLE);
  assert.equal(byClass(still, 'g-ring').length, 0);
  assert.doesNotMatch(visible(still), /● /);
});

// ---- 「確認待ち …」「● 待っている」は帯に重ならない（帯の右端が 85% を超えたら帯の左、そうでなければ右） ----

/** 「確認待ち」「● 待っている」を持つ要素（data-side を持つもの）の向き。 */
const sides = (out: string, phrase: string): string[] =>
  elements(out, (_n, a) => attrOf(a, 'data-side') !== undefined)
    .filter((e) => visible(e.inner).includes(phrase))
    .map((e) => attrOf(e.attrs, 'data-side')!);

const liveWait = (start: number, end: number): GanttModel =>
  gModel([gRow({ seq: 1, label: 'a', run: runBar(0, Math.max(start - 5, 1)), wait: waitBar(start, end, true) })], { totalSec: 100, live: true });

for (const [start, end, side] of [
  [10, 30, 'right'],
  [40, 60, 'right'],
  [70, 85, 'right'], // 帯の右端がちょうど 85% は右（超えたら左）
  [70, 86, 'left'],
  [80, 87.5, 'left'], // 旧版で文字が右端を越えた所
  [90, 96, 'left'],
  [90, 100, 'left'],
] as const) {
  test(`D0019-AC-77: 待ちの帯 ${start}〜${end}%（右端 ${end}%）では、「確認待ち …」と「● 待っている」を帯の${side === 'left' ? '左' : '右'}（data-side="${side}"）に置く`, async () => {
    const out = await render(liveWait(start, end));
    const a = sides(out, '確認待ち');
    const b = sides(out, '● 待っている');
    assert.ok(a.length >= 1, '確認待ちの文字がある');
    assert.ok(b.length >= 1, '● 待っているの文字がある');
    for (const s of [...a, ...b]) assert.equal(s, side);
  });
}

test('D0019-AC-77: 待ち中でない待ちの帯でも、帯の右端が 85% を超えれば「確認待ち …」は帯の左。帯の位置の割合は変わらない', async () => {
  const out = await render(gModel([gRow({ seq: 1, label: 'a', run: runBar(0, 50), wait: waitBar(60, 95) })]));
  assert.deepEqual(sides(out, '確認待ち'), ['left']);
  const g = (await geom(out, byClass(out, 'g-wait')[0]!)) ?? NO_GEOM;
  near(g.left, 60);
  near(g.width ?? Number.NaN, 35);
});

// ---- 横軸 ----

test('D0019-AC-72: 横軸の目盛りの文字は m:ss（1 時間以上は h:mm:ss）。目盛りの位置は全体に対する割合（3600 秒中 120 秒 → 約 3.3%）', async () => {
  const out = await render(gModel([gRow({ seq: 1, label: 'a', run: runBar(0, 3000) })], { totalSec: 3600, ticks: [60, 120, 600, 3600] }));
  const t = visible(out);
  for (const want of ['1:00', '2:00', '10:00', '1:00:00']) assert.ok(t.includes(want), `${want} が目盛りにある`);
  const two = elements(out, (_n, a) => !hasClass(a, 'g-row')).filter((e) => !/</.test(e.inner) && e.inner.trim() === '2:00');
  assert.equal(two.length, 1, '「2:00」だけを持つ要素が 1 つ');
  near(((await geom(out, two[0]!)) ?? NO_GEOM).left, (120 / 3600) * 100, 0.6);
});

test('D0019-AC-72: 同じ入力は同じ出力（時計を読まない）', async () => {
  assert.equal(await render(SAMPLE), await render(SAMPLE));
});

// ---- 文字の大きさ・横スクロールが起きない ----

test('D0019-AC-77: 行の名前・ラベル・目盛りの文字は % で縮まない。font-size は px で 11px 以上（時系列の規則のどれも %・em・rem・vw にしない）', async () => {
  const { GANTT_STYLE } = await mod();
  const rules = parseCss(GANTT_STYLE).filter((r) => !r.keyframes);
  const sizes = rules.flatMap((r) => [...r.body.matchAll(/(?<![-\w])font-size\s*:\s*([^;]+)/g)].map((m) => ({ selector: r.selector, value: m[1]!.trim() })));
  assert.ok(sizes.length > 0, 'font-size を書く');
  for (const s of sizes) {
    const px = /^(\d+(?:\.\d+)?)px$/.exec(s.value);
    assert.ok(px && Number(px[1]) >= 11, `「${s.selector}」の font-size ${s.value} は 11px 以上の px`);
  }
  assert.ok(sizes.some((s) => /\.(gantt|g-label|g-axis|g-text)(?![\w-])/.test(s.selector)), '時系列の枠か行の名前・目盛り・帯の文字の規則に書く');
  const out = await render(SAMPLE);
  assert.doesNotMatch(out, /font-size\s*[:=]\s*["']?[\d.]+(%|em|rem|vw)/, '出力にも % の文字の大きさが無い');
});

test('D0019-AC-77: 伸び縮みする SVG（preserveAspectRatio="none"）を使うなら、文字（<text>）を入れない。文字は HTML に置く', async () => {
  const out = await render(SAMPLE);
  for (const svg of elements(out, (n, a) => n === 'svg' && /preserveAspectRatio="none"/.test(a))) assert.doesNotMatch(svg.inner, /<text\b/, '横に伸ばす SVG の中の文字は伸びる');
  assert.doesNotMatch(out, /<text\b[^>]*>/, '時系列に <text> を使わない（文字は HTML）');
});

test('D0019-AC-77: 時系列の中身に固定の px 幅（740px など）・min-width が無く、横スクロールを起こさない（overflow-x の要る固定幅が無い）', async () => {
  const out = await render(SAMPLE);
  const rules = await allRules(out);
  for (const r of rules) {
    assert.doesNotMatch(r.body, /(?<![-\w])min-width\s*:\s*(?!0\b|auto\b)/, `「${r.selector}」に min-width`);
    for (const m of r.body.matchAll(/(?<![-\w])width\s*:\s*([\d.]+)px/g)) assert.ok(Number(m[1]) < 100, `「${r.selector}」に固定の幅 ${m[0]}（凡例の見本のような小さな物だけ許す）`);
    assert.doesNotMatch(r.body, /overflow(-x)?\s*:\s*(auto|scroll)/, `「${r.selector}」が自分でスクロールする`);
  }
  for (const m of out.matchAll(/<(?:svg|div|table|section|span)\b[^>]*?\swidth="([\d.]+)"/g)) assert.ok(Number(m[1]) < 100, `width 属性 ${m[1]} は固定幅`);
  assert.doesNotMatch(out, /viewBox="\s*0\s+0\s+(7\d\d|[89]\d\d|\d{4,})\b/, '幅の大きな viewBox（座標を px で持つ SVG）が無い');
});

// ---- AC-73：時刻が読めない ----

test('D0019-AC-73: 時刻が読めない行（run が null）は、行の名前と「時刻の記録なし」が出て、帯が出ない', async () => {
  const out = await render(SAMPLE);
  assert.equal(count(visible(out), /時刻の記録なし/g), 1);
  assert.equal(byClass(out, 'g-run').length, 2);
  const rows = byClass(out, 'g-row');
  assert.match(visible(rows[2]!.inner), /実装 2 回目/);
  assert.match(visible(rows[2]!.inner), /時刻の記録なし/);
  assert.equal(byClass(rows[2]!.inner, 'g-run').length, 0);
});

test('D0019-AC-73: 時刻が一つも取れない（hasTimes が偽）とき、欄全体を「時刻の記録がありません」にして、帯も横軸も出さない', async () => {
  const out = await render(gModel([gRow({ seq: 1, label: '要件定義' }), gRow({ seq: 2, label: '設計' })], { hasTimes: false, totalSec: 0, ticks: [] }));
  assert.match(plain(out), /時刻の記録がありません/);
  assert.equal(byClass(out, 'g-run').length + byClass(out, 'g-wait').length, 0);
  assert.doesNotMatch(plain(out), /時刻の記録なし/, '行ごとの注記ではなく欄全体の文');
});

test('D0019-AC-73: 行が 0 のとき（記録なし）も、例外を出さず「時刻の記録がありません」', async () => {
  const out = await render(gModel([], { hasTimes: false, totalSec: 0, ticks: [] }));
  assert.match(plain(out), /時刻の記録がありません/);
  assert.match(out, /<h2 class="terminal-title">時系列<\/h2>/);
});

// ---- AC-74：省略・エスケープ・style なし ----

test('D0019-AC-74: 省いた行があれば、一番上に「前の N 行を省いています」が出る。無ければ出ない', async () => {
  const out = await render(gModel([gRow({ seq: 5, label: '設計', run: runBar(0, 10) })], { omittedRows: 12 }));
  const t = visible(out);
  assert.match(t, /前の 12 行を省いています/);
  assert.ok(t.indexOf('省いています') < t.indexOf('設計'), '一番上');
  assert.doesNotMatch(plain(await render(SAMPLE)), /省いています/);
});

test('D0019-AC-74: 200 行あっても崩れない（例外を出さず、全部の行の名前が出る）', async () => {
  const rows = Array.from({ length: 200 }, (_, i) => gRow({ seq: i + 1, label: `段${i + 1}`, run: runBar(i, i + 1) }));
  const out = await render(gModel(rows, { totalSec: 201 }));
  for (const n of [1, 100, 200]) assert.ok(visible(out).includes(`段${n}`), `段${n}`);
  assert.equal(byClass(out, 'g-row').length, 200);
  assert.equal(byClass(out, 'g-run').length, 200);
  const last = (await geom(out, byClass(out, 'g-run')[199]!)) ?? NO_GEOM;
  near(last.left, (199 / 201) * 100, 0.6);
});

const EVIL = '<script>alert(1)</script>"&\'';

test('D0019-AC-74: 行の名前（段の表示名）と受け持ちの <script>・"・& は生で出ず、エスケープされる。title も同じ', async () => {
  const out = await render(gModel([gRow({ seq: 1, label: EVIL, agent: EVIL, run: runBar(0, 10), wait: waitBar(10, 20) })]));
  assert.ok(!out.includes('<script>alert'), '生の <script> が入っていない');
  assert.ok(!out.includes('alert(1)</script>'));
  assert.ok(!/<script/i.test(out));
  assert.ok(out.includes('&lt;script&gt;alert(1)&lt;/script&gt;'), 'エスケープされた形で出ている');
  assert.ok(out.includes(escapeHtml(EVIL)));
  assert.doesNotMatch(out, /\sstyle\s*=/i, 'style 属性を使わない');
  assert.doesNotMatch(out, /<[a-z][^>]*\son[a-z]+\s*=/i);
});

test('D0019-AC-74: 出力に style 属性・イベント属性・外部の読み込み・色の直書きが無い', async () => {
  const out = await render(SAMPLE);
  const { GANTT_STYLE } = await mod();
  assert.doesNotMatch(out, /\sstyle\s*=/i);
  assert.doesNotMatch(out, /<[a-z][^>]*\son[a-z]+\s*=/i);
  for (const text of [out, GANTT_STYLE]) {
    assert.doesNotMatch(text, /(src|href)\s*=\s*["']?https?:/i);
    assert.doesNotMatch(text, /url\(\s*["']?https?:/i);
    assert.doesNotMatch(text, /@import/i);
    for (const re of [/#[0-9a-fA-F]{3,8}\b/, /rgba?\(/, /hsla?\(/]) assert.doesNotMatch(text, re);
  }
  assert.doesNotMatch(out, /(fill|stroke)="#/, '色は属性に直書きしない');
});

test('D0019-AC-74: 帯の位置を CSS の規則で出す形なら、その <style> は出力の中にあり、色・外部の読み込み・@import を含まない（外から来た文字は規則に入らない）', async () => {
  const out = await render(gModel([gRow({ seq: 1, label: EVIL, agent: EVIL, run: runBar(10, 40), wait: waitBar(40, 60) })]));
  const css = extractCss(out);
  assert.doesNotMatch(css, /@import|url\(\s*["']?https?:|#[0-9a-fA-F]{3,8}\b|<|alert/);
  assert.doesNotMatch(css, /\bscript\b/i);
});

// ---- CSS ----

test('D0019-AC-77: 時系列の CSS：色はテーマの変数、帯のクラス（.g-run・.g-fail・.g-wait・.g-ring・.g-text）、文字は縁取り（paint-order: stroke）。大きさは元の大きさ（diagramSize.test.ts）', async () => {
  const { GANTT_STYLE } = await mod();
  assert.match(GANTT_STYLE, /var\(--vscode-/);
  const rules = parseCss(GANTT_STYLE).filter((r) => !r.keyframes);
  for (const token of ['g-run', 'g-fail', 'g-wait', 'g-ring', 'g-text']) assert.ok(rules.some((r) => new RegExp(`\\.${token}\\b`).test(r.selector)), `.${token} の規則がある`);
  assert.ok(rules.some((r) => /\.g-text\b/.test(r.selector) && /paint-order\s*:\s*stroke/.test(r.body)), '文字は縁取り');
  assert.ok(rules.some((r) => /\.g-fail\b/.test(r.selector) && /charts-red/.test(r.body)), '失敗は赤');
  assert.ok(rules.some((r) => /\.g-wait\b/.test(r.selector) && /charts-yellow/.test(r.body)), '待ちは黄');
});

test('D0019-AC-77: 時系列の CSS に @keyframes・animation を足さない（動きは 5 つのまま）', async () => {
  const { GANTT_STYLE } = await mod();
  assert.doesNotMatch(GANTT_STYLE, /@keyframes|animation\s*:/);
});

test('D0019-AC-77: 凡例（エージェント・確認待ち・不合格）が出る', async () => {
  const out = await render(SAMPLE);
  const t = visible(out);
  for (const word of ['エージェント', '確認待ち', '不合格']) assert.ok(t.includes(word), word);
  for (const k of ['key-run', 'key-wait', 'key-fail']) assert.ok(byClass(out, k).length >= 1, `.${k} の見本`);
});
