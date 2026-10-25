// 「エージェント・スキル」のタブの中身の HTML（view/toolsHtml.ts の renderTools と TOOLS_STYLE。D0047）：表と要約と案内と空の文。
// 表（ToolsTable）を直に渡して、列・並び・時間・使った段（3 つまでと title）・要約・100 行の上限・案内 A/B・空の文・外から来た文字・属性・CSS を確かめる。
// 純粋な文字列の検査（SDK を呼ばない・ファイルに書かない）。HTML は偽の DOM（test/fakeDom.ts）に読ませて、セルの文字と属性を見る。
// 新しい部品（view/toolsHtml.ts）は、テストの中で動的に読み込む（無ければ「まだ作っていない」で落とす。ファイルごと落ちて、ほかのテストまで赤にならないように）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { THEMES } from '../../scripts/previewPages.ts';
import { parseCss } from '../test/cssBlocks.ts';
import { FakeDocument } from '../test/fakeDom.ts';
import type { FakeNode } from '../test/fakeDom.ts';
import { needModule } from '../test/needModule.ts';
import { dangerousAttributes, definedVars, usedVars } from '../test/previewText.ts';
import { HOSTILE, PROTO_NAMES } from '../test/toolsFixtures.ts';
import { escapeHtml } from './escape.ts';

type Kind = 'agent' | 'skill' | 'tool';
interface Row {
  kind: Kind;
  name: string;
  count: number;
  stages: string[];
  durationSec: number | null;
}
interface Tools {
  rows: Row[];
  kinds: number;
  total: number;
  omitted: number;
  showTime: boolean;
  notice: 'A' | 'B' | null;
}
interface ToolsHtmlModule {
  renderTools(tools: Tools | null | undefined): string;
  TOOLS_STYLE: string;
}
const mod = (): Promise<ToolsHtmlModule> => needModule<ToolsHtmlModule>(import.meta.url, './toolsHtml.ts');
const render = async (tools: Tools | null | undefined): Promise<string> => (await mod()).renderTools(tools);

const row = (kind: Kind, name: string, count: number, over: Partial<Row> = {}): Row => ({ kind, name, count, stages: ['調査'], durationSec: null, ...over });
const table = (rows: Row[], over: Partial<Tools> = {}): Tools => ({
  rows,
  kinds: rows.length,
  total: rows.reduce((sum, r) => sum + r.count, 0),
  omitted: 0,
  showTime: rows.some((r) => r.durationSec !== null),
  notice: null,
  ...over,
});
const parse = (out: string): FakeDocument => {
  const doc = new FakeDocument();
  doc.innerHTML = out;
  return doc;
};
const text = (node: FakeNode | null | undefined): string => (node?.textContent ?? '').trim();
const bodyRows = (doc: FakeDocument): FakeNode[] => doc.querySelectorAll('tbody').flatMap((tbody) => tbody.querySelectorAll('tr'));
const cells = (tr: FakeNode): string[] => tr.querySelectorAll('td').map((td) => text(td));
const headers = (doc: FakeDocument): string[] => doc.querySelectorAll('th').map((th) => text(th));

const NOTICE_A = 'この記録は外の会話（/pipe-in のスキル）で進めたので、スキルや道具の呼び出しは記録に残りません。記録にある段の受け持ち（record begin --agent）を、エージェントの行として出しています。';
const NOTICE_B = 'この記録は外の会話（/pipe-in のスキル）で進めたので、スキルや道具の呼び出しは記録に残りません。段の受け持ち（record begin --agent）も記録に無いので、出せるものがありません。';
const EMPTY = 'エージェント・スキル・道具の呼び出しは、まだ記録にありません。';
const FRAME_LABEL = '使ったエージェント・スキル・道具の表';

// ---- AC-27：パネルの中の枠と表 ----

test('D0047-AC-27: 表は <table> で、列見出しは th（scope="col"）。列は 名前・種類・回数・使った段（時間の列は無い）', async () => {
  const out = await render(table([row('tool', 'Read', 3)]));
  const doc = parse(out);
  assert.equal(doc.querySelectorAll('table').length, 1);
  const ths = doc.querySelectorAll('th');
  assert.ok(ths.length > 0 && ths.every((th) => th.getAttribute('scope') === 'col'), 'th は scope="col"');
  assert.deepEqual(headers(doc), ['名前', '種類', '回数', '使った段']);
});

test('D0047-AC-27: 表を包む枠は tabindex="0"・role="region"・aria-label が一字一句・横の位置を覚える印 data-scroll="tools-table"・焦点を戻す印 data-keep="tools-table"', async () => {
  const doc = parse(await render(table([row('tool', 'Read', 3)])));
  const frames = doc.querySelectorAll('[data-scroll]');
  assert.equal(frames.length, 1, '位置を覚える枠は表の枠 1 つだけ（パネル自身の印は shellHtml が付ける）');
  const frame = frames[0]!;
  assert.equal(frame.getAttribute('data-scroll'), 'tools-table');
  assert.equal(frame.getAttribute('data-keep'), 'tools-table');
  assert.equal(frame.getAttribute('tabindex'), '0');
  assert.equal(frame.getAttribute('role'), 'region');
  assert.equal(frame.getAttribute('aria-label'), FRAME_LABEL);
  assert.equal(frame.querySelectorAll('table').length, 1, '枠が表を包む');
});

test('D0047-AC-27: 見出し h2「エージェント・スキル・道具」は、表があるときも、空のときも、案内だけのときも出る', async () => {
  for (const tools of [table([row('tool', 'Read', 1)]), table([]), table([], { notice: 'B' }), null, undefined]) {
    const doc = parse(await render(tools));
    assert.equal(text(doc.querySelector('h2')), 'エージェント・スキル・道具');
  }
});

test('D0047-AC-27: 種類は色でなく文字で分かる（エージェント・スキル・道具）', async () => {
  const doc = parse(await render(table([row('agent', 'a', 1), row('skill', 's', 1), row('tool', 'Read', 1)])));
  assert.deepEqual(bodyRows(doc).map((tr) => cells(tr)[1]), ['エージェント', 'スキル', '道具']);
});

// ---- AC-23：列・並び（view は渡された行の順に出す） ----

test('D0047-AC-23: 行は渡された順に出る（並べ替えは表を作る側）。列は 名前・種類・回数・使った段の順で、セルに値が入る', async () => {
  const doc = parse(await render(table([row('agent', 'b', 2, { stages: ['調査', '描く'] }), row('agent', 'a', 1), row('tool', 'Read', 12)])));
  assert.deepEqual(bodyRows(doc).map(cells), [
    ['b', 'エージェント', '2', '調査、描く'],
    ['a', 'エージェント', '1', '調査'],
    ['Read', '道具', '12', '調査'],
  ]);
});

test('D0047-AC-23: 時間の列があるときは、回数と使った段のあいだに入る（列見出し 名前・種類・回数・時間・使った段）', async () => {
  const doc = parse(await render(table([row('agent', 'x', 2, { durationSec: 61 }), row('tool', 'Read', 3)])));
  assert.deepEqual(headers(doc), ['名前', '種類', '回数', '時間', '使った段']);
  assert.deepEqual(bodyRows(doc).map(cells), [
    ['x', 'エージェント', '2', '1:01', '調査'],
    ['Read', '道具', '3', '—', '調査'],
  ]);
});

test('D0047-AC-23: 回数は桁区切りなしの整数', async () => {
  const doc = parse(await render(table([row('tool', 'Read', 1234567)])));
  assert.equal(cells(bodyRows(doc)[0]!)[2], '1234567');
});

// ---- AC-14・AC-15・AC-16：時間 ----

test('D0047-AC-15: 時間は m:ss（1 時間以上は h:mm:ss、小数は切り捨て）。時間のある受け持ちの行の隣の呼び出しの行は「—」', async () => {
  const doc = parse(
    await render(
      table([
        row('agent', 'sum', 3, { durationSec: 61.4 }),
        row('agent', 'zero', 1, { durationSec: 0 }),
        row('agent', 'long', 1, { durationSec: 3725 }),
        row('skill', 's', 1),
        row('tool', 'Read', 1),
      ]),
    ),
  );
  const times = bodyRows(doc).map((tr) => cells(tr)[3]);
  assert.deepEqual(times, ['1:01', '0:00', '1:02:05', '—', '—']);
});

test('D0047-AC-14: 呼び出しを数えた行（スキル・道具・SDK のエージェント呼び出し）は、時間のある行と並んでも「—」', async () => {
  const doc = parse(await render(table([row('agent', 'task-agent', 2), row('agent', 'owner', 1, { durationSec: 30 }), row('skill', 's', 1), row('tool', 'Read', 4)])));
  assert.deepEqual(
    bodyRows(doc).map((tr) => [cells(tr)[0], cells(tr)[3]]),
    [['task-agent', '—'], ['owner', '0:30'], ['s', '—'], ['Read', '—']],
  );
});

test('D0047-AC-16: 時間のある行が無い（showTime が偽）と、「時間」の見出しも時間のセルも出ない（「—」だけの列を作らない）', async () => {
  const out = await render(table([row('tool', 'Read', 1), row('skill', 's', 1)]));
  const doc = parse(out);
  assert.ok(!headers(doc).includes('時間'));
  assert.ok(bodyRows(doc).every((tr) => tr.querySelectorAll('td').length === 4), 'どの行もセルは 4 つ');
  assert.equal(doc.querySelectorAll('.tools-time').length, 0);
});

test('D0047-AC-16: showTime が真のとき、どの行にも時間のセルがあり、列見出しにも「時間」がある', async () => {
  const doc = parse(await render(table([row('agent', 'x', 1, { durationSec: 5 }), row('tool', 'Read', 1)])));
  assert.ok(headers(doc).includes('時間'));
  assert.ok(bodyRows(doc).every((tr) => tr.querySelectorAll('td').length === 5));
  assert.equal(doc.querySelectorAll('.tools-time').length, 2);
});

// ---- AC-24・AC-25：要約と 100 行の上限 ----

test('D0047-AC-24: 要約「N 種類・合計 M 回」は行を省く前の全体：150 種類をすべて回数 2 にすると「150 種類・合計 300 回」で、表の行は 100・表に出る回数の合計は 200', async () => {
  const rows = Array.from({ length: 100 }, (_, i) => row('tool', `t${String(i).padStart(3, '0')}`, 2));
  const out = await render({ rows, kinds: 150, total: 300, omitted: 50, showTime: false, notice: null });
  const doc = parse(out);
  assert.equal(text(doc.querySelector('.tools-summary')), '150 種類・合計 300 回');
  const trs = bodyRows(doc);
  assert.equal(trs.length, 100);
  assert.equal(trs.reduce((sum, tr) => sum + Number(cells(tr)[2]), 0), 200);
});

test('D0047-AC-24: 要約は表の上（要約 → 枠 の順）に出る', async () => {
  const out = await render(table([row('tool', 'Read', 3)]));
  assert.match(text(parse(out).querySelector('.tools-summary')), /^1 種類・合計 3 回$/);
  assert.ok(out.indexOf('tools-summary') < out.indexOf('tools-scroll'));
});

for (const [omitted, sentence] of [
  [0, null],
  [1, 'ほか 1 種類を省いています'],
  [20, 'ほか 20 種類を省いています'],
] as [number, string | null][]) {
  test(`D0047-AC-25: 省いた種類が ${omitted} のとき、表の下に${sentence === null ? '省略の文は出ない' : `「${sentence}」が出る`}`, async () => {
    const rows = Array.from({ length: 100 }, (_, i) => row('tool', `t${String(i).padStart(3, '0')}`, 1));
    const out = await render({ rows, kinds: 100 + omitted, total: 100 + omitted, omitted, showTime: false, notice: null });
    const doc = parse(out);
    const omit = doc.querySelector('.tools-omit');
    if (sentence === null) {
      assert.equal(omit, null);
    } else {
      assert.equal(text(omit), sentence);
      assert.ok(out.indexOf('tools-omit') > out.indexOf('</table>'), '表の下');
    }
  });
}

// ---- AC-26：空の文 ----

test('D0047-AC-26: 行が無く案内も無い表・tools が null・tools が undefined のときは、空の文だけが出る（要約・表・案内は無い）', async () => {
  for (const tools of [table([]), null, undefined]) {
    const out = await render(tools);
    const doc = parse(out);
    assert.equal(text(doc.querySelector('.tools-empty')), EMPTY);
    assert.equal(doc.querySelectorAll('table').length, 0);
    assert.equal(doc.querySelector('.tools-summary'), null);
    assert.equal(doc.querySelector('.tools-notice'), null);
    assert.equal(doc.querySelector('.tools-omit'), null);
  }
});

test('D0047-AC-26: 行があるときは、空の文は出ない', async () => {
  assert.equal(parse(await render(table([row('tool', 'Read', 1)]))).querySelector('.tools-empty'), null);
});

// ---- AC-21・AC-22：案内 A・B ----

test('D0047-AC-21: 案内 A（driver があり行がある）は固定の文で、要約の前（表の上）に出る。「受け持ちだけ」とは言わない', async () => {
  const out = await render(table([row('agent', 'pipe-in-analyst', 1, { durationSec: 95 })], { notice: 'A' }));
  const doc = parse(out);
  assert.equal(text(doc.querySelector('.tools-notice')), NOTICE_A);
  assert.ok(out.indexOf('tools-notice') < out.indexOf('tools-summary'), '案内は要約の前');
  assert.ok(doc.querySelectorAll('table').length === 1, '案内 A のときも表は出る');
  assert.ok(!out.includes('受け持ちだけ'));
});

test('D0047-AC-21: 案内が無い（driver が無い）表には、案内の要素が出ない', async () => {
  assert.equal(parse(await render(table([row('tool', 'Read', 1)]))).querySelector('.tools-notice'), null);
});

test('D0047-AC-22: 案内 B（driver があり行が 0）は固定の文だけが出て、要約・表・空の文は出ない', async () => {
  const doc = parse(await render(table([], { notice: 'B' })));
  assert.equal(text(doc.querySelector('.tools-notice')), NOTICE_B);
  assert.equal(doc.querySelector('.tools-summary'), null);
  assert.equal(doc.querySelectorAll('table').length, 0);
  assert.equal(doc.querySelector('.tools-empty'), null);
});

test('D0047-AC-21: 案内 A・B の文は、/pipe-in のスキルで進めた記録では呼び出しが残らないことと、record begin --agent を言う', async () => {
  for (const [notice, rows] of [['A', [row('agent', 'x', 1)]], ['B', []]] as const) {
    const out = parse(await render(table([...rows], { notice }))).querySelector('.tools-notice');
    assert.match(text(out), /外の会話（\/pipe-in のスキル）/);
    assert.match(text(out), /スキルや道具の呼び出しは記録に残りません/);
    assert.match(text(out), /record begin --agent/);
  }
});

// ---- AC-12：使った段（3 つまでと title） ----

/** 長さ len の label（先頭の数字で見分ける） */
const label = (n: number, len: number): string => String(n).padEnd(len, 'x');
const stagesCell = async (stages: string[]): Promise<{ text: string; title: string | null }> => {
  const cell = parse(await render(table([row('tool', 'Read', stages.length, { stages })]))).querySelector('.tools-stages');
  assert.ok(cell, '使った段のセルがある');
  return { text: text(cell), title: cell.getAttribute('title') };
};

test('D0047-AC-12: 使った段が 3 つ以下のときは「、」でつないで全部出し、title は付けない', async () => {
  assert.deepEqual(await stagesCell(['調査']), { text: '調査', title: null });
  assert.deepEqual(await stagesCell(['調査', '描く']), { text: '調査、描く', title: null });
  assert.deepEqual(await stagesCell(['調査', '描く', '検証']), { text: '調査、描く、検証', title: null });
});

test('D0047-AC-12: 使った段が 6 つのときは、3 つと「ほか 3 件」が出て、title に 6 つ全部（「、」でつないだ）が入る', async () => {
  const stages = ['一', '二', '三', '四', '五', '六'];
  assert.deepEqual(await stagesCell(stages), { text: '一、二、三、ほか 3 件', title: '一、二、三、四、五、六' });
});

test('D0047-AC-12: 使った段が 4 つのときは、3 つと「ほか 1 件」が出て、title が付く', async () => {
  assert.deepEqual(await stagesCell(['一', '二', '三', '四']), { text: '一、二、三、ほか 1 件', title: '一、二、三、四' });
});

test('D0047-AC-12: title の切り詰め (1) 70 文字の label を 6 つ：70・141 で 2 つ収まり、212 で超える → 「L1、L2、ほか 4 件」', async () => {
  const L = [1, 2, 3, 4, 5, 6].map((n) => label(n, 70));
  const cell = await stagesCell(L);
  assert.equal(cell.text, `${L[0]}、${L[1]}、${L[2]}、ほか 3 件`);
  assert.equal(cell.title, `${L[0]}、${L[1]}、ほか 4 件`);
});

test('D0047-AC-12: title の切り詰め (2) 50 文字の label を 4 つ：50・101・152 で 3 つ収まり、203 で超える → 「L1、L2、L3、ほか 1 件」', async () => {
  const L = [1, 2, 3, 4].map((n) => label(n, 50));
  assert.equal((await stagesCell(L)).title, `${L[0]}、${L[1]}、${L[2]}、ほか 1 件`);
});

test('D0047-AC-12: title の切り詰め (3) 49 文字の label を 4 つ：199 文字で全部収まるので、切らずに全部をつなぐ（「ほか」なし）', async () => {
  const L = [1, 2, 3, 4].map((n) => label(n, 49));
  const cell = await stagesCell(L);
  assert.equal(cell.title, L.join('、'));
  assert.equal(cell.text, `${L[0]}、${L[1]}、${L[2]}、ほか 1 件`);
});

test('D0047-AC-12: title の切り詰め (4) 250 文字の label を 4 つ：1 つも収まらないので、title は「ほか 4 件」だけ', async () => {
  const L = [1, 2, 3, 4].map((n) => label(n, 250));
  assert.equal((await stagesCell(L)).title, 'ほか 4 件');
});

test('D0047-AC-12: title の切り詰め (5) 49・49・49・50 文字の label を 4 つ：つないだ長さがちょうど 200 文字（49+1+49+1+49+1+50）。200 までは収まるので、切らずに全部をつなぐ（「ほか」なし）', async () => {
  const L = [label(1, 49), label(2, 49), label(3, 49), label(4, 50)];
  assert.equal(Array.from(L.join('、')).length, 200, '前提：ちょうど 200 文字');
  const cell = await stagesCell(L);
  assert.equal(cell.title, L.join('、'));
  assert.equal(cell.text, `${L[0]}、${L[1]}、${L[2]}、ほか 1 件`);
});

test('D0047-AC-12: title の切り詰め (6) 対照：(5) の 4 つに label「e」を足すと全部で 202 文字になって超える。ちょうど 200 文字に収まった 4 つまでと「ほか 1 件」', async () => {
  const L = [label(1, 49), label(2, 49), label(3, 49), label(4, 50), 'e'];
  assert.equal((await stagesCell(L)).title, `${L[0]}、${L[1]}、${L[2]}、${L[3]}、ほか 1 件`);
});

test('D0047-AC-12: title の 200 文字はコードポイントで数える（絵文字 1 つは 1 文字）：絵文字 99 個の label 2 つは 199 文字で収まり、3 つ目の c を足すと 201 で超える → 「a、b、ほか 2 件」', async () => {
  const a = '😀'.repeat(99);
  const b = '😁'.repeat(99);
  const cell = await stagesCell([a, b, 'c', 'd']);
  assert.equal(cell.title, `${a}、${b}、ほか 2 件`);
});

// ---- AC-35：外から来た文字は escapeHtml を 1 回だけ ----

for (const hostile of HOSTILE) {
  test(`D0047-AC-35: 外から来た文字 ${JSON.stringify(hostile)} を 道具・エージェント・スキルの名前と段の表示名に入れても、生の HTML にならず、二重にエスケープもしない（title の中も）`, async () => {
    const stages = [hostile, '二', '三', '四'];
    const out = await render(table([row('agent', hostile, 1, { stages }), row('skill', hostile, 1, { stages }), row('tool', hostile, 1, { stages })]));
    assert.ok(out.includes(escapeHtml(hostile)), 'エスケープされた形で出ている');
    assert.ok(!out.includes('&amp;lt;') && !out.includes('&amp;amp;') && !out.includes('&amp;quot;') && !out.includes('&amp;apos;') && !out.includes('&amp;gt;'), '二重にエスケープしていない');
    if (hostile.includes('<')) assert.ok(!out.includes(hostile), '生の文字が出ていない');
    assert.ok(!out.includes('</td></tr></table>'), '表の終わりの形を作れない');
    const doc = parse(out);
    const trs = bodyRows(doc);
    assert.equal(trs.length, 3, '表が崩れず 3 行');
    for (const tr of trs) {
      const tds = tr.querySelectorAll('td');
      assert.equal(text(tds[0]), hostile.trim(), '名前のセルの文字は、元の文字そのまま（1 回だけエスケープ）');
      assert.equal(tds[tds.length - 1]!.getAttribute('title'), [hostile, '二', '三', '四'].join('、'), 'title の中の文字も 1 回だけ');
    }
    assert.equal(doc.querySelectorAll('script').length, 0);
  });
}

for (const hostile of HOSTILE) {
  for (const stages of [[hostile], [hostile, '二', '三']]) {
    test(`D0047-AC-35: 外から来た文字 ${JSON.stringify(hostile)} を段の表示名に入れた、使った段が ${stages.length} 件の行（title が付かない、いちばんよく通る分かれ）も、生の HTML にならず、二重にエスケープもしない`, async () => {
      const out = await render(table([row('tool', 'Read', 1, { stages })]));
      assert.ok(out.includes(escapeHtml(hostile)), 'エスケープされた形で出ている');
      assert.ok(!out.includes('&amp;lt;') && !out.includes('&amp;amp;') && !out.includes('&amp;quot;') && !out.includes('&amp;apos;') && !out.includes('&amp;gt;'), '二重にエスケープしていない');
      if (hostile.includes('<')) assert.ok(!out.includes(hostile), '生の文字が出ていない');
      assert.ok(!out.includes('</td></tr></table>'), '表の終わりの形を作れない');
      const doc = parse(out);
      const cell = doc.querySelector('.tools-stages');
      assert.ok(cell, '使った段のセルがある');
      assert.equal(cell.getAttribute('title'), null, 'title は付かない');
      assert.equal(text(cell), stages.join('、'), '使った段のセルの文字は、元の文字そのまま（1 回だけエスケープ）');
      assert.equal(bodyRows(doc).length, 1, '表が崩れず 1 行');
      assert.equal(doc.querySelectorAll('script').length, 0);
    });
  }
}

test('D0047-AC-35: 段の表示名に <div class="tabpanel" role="tabpanel" data-detail-panel="usage" を入れても、生では出ない', async () => {
  const evil = '<div class="tabpanel" role="tabpanel" data-detail-panel="usage"';
  const out = await render(table([row('tool', 'Read', 1, { stages: [evil, 'a', 'b', 'c'] })]));
  assert.ok(!out.includes(evil));
  assert.ok(!out.includes('<div class="tabpanel"'));
  assert.ok(out.includes(escapeHtml(evil)));
});

// ---- AC-36：属性 ----

test('D0047-AC-36: パネルの HTML に style 属性・on… の属性・src・href を持つタグが無い（外から来た文字を入れても）', async () => {
  const out = await render(table([row('agent', 'a', 1, { durationSec: 3, stages: ['a', 'b', 'c', 'd'] }), row('skill', HOSTILE[0]!, 1), row('tool', HOSTILE[4]!, 1)], { notice: 'A', omitted: 3, kinds: 6 }));
  assert.deepEqual(dangerousAttributes(out), []);
  assert.ok(!/\sstyle=/i.test(out));
  assert.ok(!/<a\b|<img\b|<script\b|<link\b|<iframe\b/i.test(out));
});

// ---- AC-44：組み込みの名前 ----

test('D0047-AC-44: 道具の名前が __proto__・constructor・toString の行が、HTML にも 3 つ出る', async () => {
  const doc = parse(await render(table(PROTO_NAMES.map((name) => row('tool', name, 1)))));
  assert.deepEqual(bodyRows(doc).map((tr) => cells(tr)[0]), [...PROTO_NAMES]);
});

// ---- 同じ入力から同じ HTML ----

test('D0047-AC-33: 同じ表からは同じ HTML ができる（呼ぶたびに変わらない）', async () => {
  const tools = table([row('agent', 'a', 2, { durationSec: 9 }), row('tool', 'Read', 3)], { notice: 'A' });
  assert.equal(await render(tools), await render(tools));
});

// ---- CSS ----

const ruleBodies = (css: ReturnType<typeof parseCss>, selector: string): string[] => css.filter((r) => r.selector.split(',').map((s) => s.trim()).includes(selector)).map((r) => r.body);

test('D0047-AC-27: 枠 .tools-scroll は overflow-x: auto（キーボードだけで横にスクロールできる）で、焦点の輪（:focus-visible）の outline に --vscode-focusBorder を使う', async () => {
  const css = parseCss((await mod()).TOOLS_STYLE);
  assert.ok(ruleBodies(css, '.tools-scroll').some((b) => /overflow-x\s*:\s*auto/.test(b)), '.tools-scroll に overflow-x: auto');
  assert.ok(ruleBodies(css, '.tools-scroll:focus-visible').some((b) => /outline\s*:[^;]*var\(--vscode-focusBorder/.test(b)), '焦点の輪');
});

test('D0047-AC-27: 長い名前は枠の中で折り返す：.tools-name と .tools-stages に overflow-wrap: anywhere、.tools-table に min-width（狭い幅で列がつぶれず、枠が横にスクロールする）', async () => {
  const css = parseCss((await mod()).TOOLS_STYLE);
  for (const sel of ['.tools-name', '.tools-stages']) assert.ok(ruleBodies(css, sel).some((b) => /overflow-wrap\s*:\s*anywhere/.test(b)), `${sel} に overflow-wrap: anywhere`);
  assert.ok(ruleBodies(css, '.tools-table').some((b) => /min-width\s*:/.test(b)), '.tools-table に min-width');
});

// 検証 1 回目の画面の確認（attempt 2）：明るいテーマの 1280×800 で、列見出し「回数」が「回／数」と 2 行に折れた。
// 本文のセル（.tools-kind・.tools-count・.tools-time）には white-space: nowrap があるが、列見出し（th）には無かった。
// セレクタの書き方（`.tools-table th` 単独か、`.tools-table td` との並びか）に引きずられないよう、th に当たる規則の中に nowrap があるかを見る。
test('D0047-AC-57: 列見出し（.tools-table th）に white-space: nowrap が当たっている（「回数」のような短い見出しが 2 行に折れない）', async () => {
  const css = parseCss((await mod()).TOOLS_STYLE);
  const onTh = css.filter((r) =>
    r.selector
      .split(',')
      .map((s) => s.trim())
      .some((s) => /^\.tools-table[\s>]+(?:[\w-]+[\s>]+)*th$/.test(s)),
  );
  assert.ok(onTh.length > 0, '.tools-table th に当たる規則がある');
  assert.ok(
    onTh.some((r) => /white-space\s*:\s*nowrap/.test(r.body)),
    `列見出し（.tools-table th）に white-space: nowrap が無い（th に当たる規則：${onTh.map((r) => r.selector).join(' / ')}）`,
  );
});

test('D0047-AC-27: TOOLS_STYLE に @media が無い（幅の規則は shellHtml の既存の 2 つの @media だけ）', async () => {
  const css = parseCss((await mod()).TOOLS_STYLE);
  assert.ok(css.length > 0);
  assert.deepEqual(css.filter((r) => r.media !== null).map((r) => r.media), []);
});

test('D0047-AC-36: TOOLS_STYLE の色は var(--vscode-*) だけ（色の直書き・外部の読み込み・id セレクタが無い）で、使う変数は確認用ページの THEMES が決めているものだけ', async () => {
  const style = (await mod()).TOOLS_STYLE;
  assert.match(style, /var\(--vscode-/);
  for (const re of [/#[0-9a-fA-F]{3,8}\b/, /rgba?\(/, /hsla?\(/, /url\(\s*["']?https?:/i, /@import/i]) assert.doesNotMatch(style, re);
  assert.doesNotMatch(style, /(^|[\s,}])#[A-Za-z_-]/, 'id セレクタを使わない（クラスだけ）');
  for (const theme of ['light', 'dark'] as const) {
    const defined = definedVars(THEMES[theme]);
    assert.deepEqual(usedVars(style).filter((name) => !defined.has(name)), [], `${theme}: THEMES に無い色`);
  }
});
