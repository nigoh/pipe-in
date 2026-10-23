// 「成果物」タブの中身 renderArtifacts（D0025）：実装の段で読み手の指摘を受けて直した 3 つの動きのテスト（決定の記録 D0025 の「実装で人が決めたこと」「聞かずに決めたこと」）。
//   pre の直後の改行（AC-39）：.md でない成果物（pre.art-plain）の先頭が改行でも、HTML の決まり（pre の直後の改行 1 つは捨てられる）で 1 行少なく見えない。
//   中身の向きの制御文字（AC-35）：プレビューの中身（.md の本文・コードブロック・.txt）の向きを変える制御文字（U+202A〜202E・U+2066〜2069）を U+FFFD にする。名前の扱いは変えない。
//   プレビューの HTML の合計の上限（AC-37）：1 回の描き直しで作るプレビューの HTML の合計に上限（PREVIEW_HTML_MAX_CHARS）。既定の選びを先に変換し、入らないものは p.art-omit の案内だけ。
// どれも、直した今の作りで通る（緑）。直しを外すと落ちるように書いた。上限の値はテストに直書きせず、製品の定数（PREVIEW_HTML_MAX_CHARS・ARTIFACT_MAX_BYTES）から読む。
// 既存のテスト（artifactsHtml.test.ts ほか）は書き換えず、足すだけ。偽の DOM は使わない：8 MiB 近い HTML を木に読み込むと重いので、文字列のまま調べる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ARTIFACT_MAX_BYTES } from '../domain/artifacts.ts';
import type { ArtifactEntry } from '../domain/artifacts.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import * as artifactsHtml from './artifactsHtml.ts';
import { escapeHtml } from './escape.ts';

// 上限の定数は、名前つきの import でなく名前空間から読む：直しを外して確かめるとき、定数が無くても、ファイルごと読めずに落ちず、テストごとに落ちる（undefined になる）。
const { renderArtifacts } = artifactsHtml;
const { OMIT_NOTICE, PREVIEW_HTML_MAX_CHARS } = artifactsHtml;

type View = Pick<PipelineView, 'artifacts' | 'runningStage' | 'pendingReview'>;

function entry(name: string, text: string, over: Partial<ArtifactEntry> = {}): ArtifactEntry {
  return { name, label: name, stage: null, stageLabel: null, ready: true, text, cut: false, updatedText: '10/17 10:05', ...over };
}

function viewOf(artifacts: ArtifactEntry[], runningStage: string | null = null): View {
  return { artifacts, runningStage, pendingReview: null };
}

/** name のプレビューの中身の枠（div.art-body）の中の HTML。枠は `data-keep="art-scroll:<名前>">` で始まり、`</div></section>` で終わる */
function bodyOf(out: string, name: string): string {
  const open = `data-keep="art-scroll:${escapeHtml(name)}">`;
  const from = out.indexOf(open);
  assert.notEqual(from, -1, `${name} の中身の枠がある`);
  const start = from + open.length;
  const end = out.indexOf('</div></section>', start);
  assert.notEqual(end, -1, `${name} の中身の枠の終わりがある`);
  return out.slice(start, end);
}

const countOf = (text: string, part: string): number => text.split(part).length - 1;

// ---- pre の直後の改行（AC-39）：pre.art-plain の直後の改行 ----
// HTML の決まりで、<pre> の直後の改行 1 つは捨てられる。先頭が改行のテキストをそのまま入れると、その改行が 1 つ消えて、空行が 1 行少なく見える。
// そこで、<pre class="art-plain"> の直後に改行を 1 つ足す。偽の DOM はこの決まりを持たない（見えない）ので、出力の文字から決まりを当てはめて確かめる。

const PRE_OPEN = '<pre class="art-plain">';

/** 出力の pre.art-plain の中を、HTML の構文解析と同じに（開きタグの直後の改行 1 つを捨てて）読んだ文字（まだ escapeHtml 済み） */
function plainAsParsed(out: string): string {
  const from = out.indexOf(PRE_OPEN);
  assert.notEqual(from, -1, 'pre.art-plain がある');
  const start = from + PRE_OPEN.length;
  const end = out.indexOf('</pre>', start);
  assert.notEqual(end, -1, '</pre> がある');
  const inner = out.slice(start, end);
  return inner.startsWith('\n') ? inner.slice(1) : inner;
}

const PLAIN_TEXTS: readonly (readonly [label: string, text: string])[] = [
  ['空行 2 つで始まる', '\n\n見出し'],
  ['空行 1 つで始まる', '\n見出し'],
  ['空行 3 つだけ', '\n\n\n'],
  ['改行 1 つだけ', '\n'],
  ['改行で始まらない', '見出し\n本文'],
  ['空', ''],
  ['先頭が改行で、<b> と & を含む', '\n<b>見出し</b> & 本文'],
];

for (const [label, text] of PLAIN_TEXTS) {
  // 先頭が改行でない中身は、足す改行が無くても通る（直す前から通る）ので、そう書く
  const keep = text.startsWith('\n') ? '' : '（先頭が改行でないので、直す前から通る。守る）';
  test(`D0025-AC-39: .txt の中身（${label}）は、pre の直後の改行 1 つを捨てる HTML の決まりを当てはめても、元の文字のまま（行が減らない）${keep}`, () => {
    const out = renderArtifacts(viewOf([entry('notes.txt', text)]));
    assert.equal(plainAsParsed(out), escapeHtml(text));
  });
}

test('D0025-AC-39: .txt の中身が \\n\\n見出し のとき、HTML は <pre class="art-plain">\\n\\n\\n見出し</pre>（捨てられる改行 1 つを足した形）', () => {
  const out = renderArtifacts(viewOf([entry('notes.txt', '\n\n見出し')]));
  assert.ok(out.includes('<pre class="art-plain">\n\n\n見出し</pre>'), bodyOf(out, 'notes.txt'));
});

test('D0025-AC-39: .md の中身は pre.art-plain にならない（足す改行は .txt など、.md でない成果物だけ。今のまま通る。守る）', () => {
  const out = renderArtifacts(viewOf([entry('notes.md', '\n\n# 題')]));
  assert.ok(!out.includes(PRE_OPEN), 'pre.art-plain が無い');
  assert.ok(bodyOf(out, 'notes.md').startsWith('<div class="md">'), 'div.md の中に入る');
});

// ---- 中身の向きの制御文字（AC-35）：中身の向きを変える制御文字は U+FFFD ----
// 外から来た文字で、確認のために読む文書の見かけの順を入れ替えられないようにする（名前と同じ置き換え）。長さは変わらない。

const BIDI = [0x202a, 0x202b, 0x202c, 0x202d, 0x202e, 0x2066, 0x2067, 0x2068, 0x2069];
const hexOf = (code: number): string => `U+${code.toString(16).toUpperCase()}`;

/** [置き場所, 成果物の名前, 中身を作る関数（hit に向きの制御文字が入る）] */
const BODY_PLACES: readonly (readonly [label: string, name: string, make: (hit: string) => string])[] = [
  ['.md の段落', 'notes.md', (hit) => `前${hit}後`],
  ['.md のコードブロック', 'notes.md', (hit) => ['```', `前${hit}後`, '```'].join('\n')],
  ['.md の行の中のコード', 'notes.md', (hit) => `\`前${hit}後\``],
  ['.md の表のセル', 'notes.md', (hit) => [`| 前${hit}後 |`, '|---|', '| x |'].join('\n')],
  ['.txt', 'notes.txt', (hit) => `前${hit}後`],
];

for (const [place, name, make] of BODY_PLACES) {
  for (const code of BIDI) {
    test(`D0025-AC-35: ${place}の中身にある向きを変える制御文字（${hexOf(code)}）は、プレビューの HTML で U+FFFD になり、元の文字は残らない`, () => {
      const ch = String.fromCodePoint(code);
      const out = renderArtifacts(viewOf([entry(name, make(ch))]));
      const body = bodyOf(out, name);
      assert.ok(body.includes('前�後'), body);
      assert.ok(!body.includes(ch), '中身に元の制御文字が残っていない');
      assert.ok(!out.includes(ch), '出力のどこにも元の制御文字が残っていない');
    });
  }
}

test('D0025-AC-35: 向きを変える制御文字 9 つが並んでいても、中身では 9 つの U+FFFD になる（.txt）', () => {
  const all = BIDI.map((c) => String.fromCodePoint(c)).join('');
  const out = renderArtifacts(viewOf([entry('notes.txt', `前${all}後`)]));
  assert.ok(bodyOf(out, 'notes.txt').includes(`前${'�'.repeat(9)}後`));
});

for (const code of [0x2029, 0x202f, 0x2065, 0x206a, 0x200e, 0x200f]) {
  test(`D0025-AC-35: 向きを変える制御文字の隣の文字（${hexOf(code)}）は、中身で変えない（.txt と .md の段落。今のまま通る。守る）`, () => {
    const text = `a${String.fromCodePoint(code)}b`;
    assert.ok(bodyOf(renderArtifacts(viewOf([entry('notes.txt', text)])), 'notes.txt').includes(text));
    assert.ok(bodyOf(renderArtifacts(viewOf([entry('notes.md', text)])), 'notes.md').includes(text));
  });
}

test('D0025-AC-35: 名前の扱いは変えない：名前に入った向きの制御文字は data-* の名前で元のまま、画面に出る名前は U+FFFD。中身だけが中身の規則で U+FFFD になる', () => {
  const rlo = String.fromCodePoint(0x202e);
  const name = `a${rlo}b.md`;
  const out = renderArtifacts(viewOf([entry(name, `x${rlo}y`, { label: `L${rlo}` })]));
  for (const attr of ['data-art-pick', 'data-art-preview', 'data-artifact']) {
    assert.ok(out.includes(`${attr}="${name}"`), `${attr} の名前は元のまま`);
  }
  assert.ok(out.includes('<span class="art-file">a�b.md</span>'), '画面に出るファイル名は U+FFFD');
  assert.ok(out.includes('<span class="art-name">L�</span>'), '画面に出る名前は U+FFFD');
  assert.equal(bodyOf(out, name), '<div class="md"><p>x�y</p></div>', '中身は U+FFFD');
});

// ---- プレビューの HTML の合計の上限（AC-37）：描き直し 1 回のプレビューの HTML の合計の上限 ----
// 空行で区切った `>>>a` の繰り返しは、6 バイトが 83 文字ほど（約 14 倍）になる。読む量の上限（合計 4 MiB）の中でも、16 個で HTML が 5800 万文字を超えた（直す前）。
// 出す側の合計の上限（PREVIEW_HTML_MAX_CHARS）を超えるところから先のプレビューは、中身を出さず、案内（p.art-omit）だけにする。

const QUOTES = '>>>a\n\n'.repeat(Math.floor(ARTIFACT_MAX_BYTES / '>>>a\n\n'.length));
const ENTRY_COUNT = 16;
const NAMES = Array.from({ length: ENTRY_COUNT }, (_, i) => `${String(i + 1).padStart(2, '0')}_quote.md`);
const OMIT_BODY = `<p class="art-omit">${OMIT_NOTICE}</p>`;

interface Rendered {
  out: string;
  /** NAMES の順の、中身の枠の中の HTML */
  bodies: string[];
}

const rendered = new Map<string, Rendered>();

/** 16 個の成果物（どれも上限いっぱいの引用）を描く。mid が数なら、その番号の成果物が段 'mid' の成果物になり、running が 'mid' のとき既定の選びになる */
function renderSixteen(key: string, mid: number | null, running: string | null): Rendered {
  const cached = rendered.get(key);
  if (cached !== undefined) return cached;
  const entries = NAMES.map((name, i) => entry(name, QUOTES, i === mid ? { stage: 'mid', stageLabel: '途中の段' } : {}));
  const out = renderArtifacts(viewOf(entries, running));
  const value = { out, bodies: NAMES.map((name) => bodyOf(out, name)) };
  rendered.set(key, value);
  return value;
}

/** [名前, 段の番号, 動いている段, 既定の選びの番号] */
const SCENARIOS: readonly (readonly [label: string, mid: number | null, running: string | null, picked: number])[] = [
  ['動いている段が無く、既定の選びは一覧の順で最後', null, null, ENTRY_COUNT - 1],
  ['動いている段の成果物（一覧の真ん中）が既定の選び', 7, 'mid', 7],
];

test('D0025-AC-37: 上限の定数 PREVIEW_HTML_MAX_CHARS は整数で、成果物 1 つの出力の上限（読む量の上限の 20 倍）以上（最初の 1 つは必ず入る）', () => {
  assert.ok(Number.isInteger(PREVIEW_HTML_MAX_CHARS));
  assert.ok(PREVIEW_HTML_MAX_CHARS >= 20 * ARTIFACT_MAX_BYTES, `${PREVIEW_HTML_MAX_CHARS} は ${20 * ARTIFACT_MAX_BYTES} 以上のはず`);
});

for (const [label, mid, running, picked] of SCENARIOS) {
  test(`D0025-AC-37: 上限いっぱいの引用 16 個（${label}）：中身の HTML の合計が PREVIEW_HTML_MAX_CHARS 以内で、入らないものがある`, () => {
    const { bodies } = renderSixteen(label, mid, running);
    const total = bodies.filter((b) => b !== OMIT_BODY).reduce((sum, b) => sum + b.length, 0);
    assert.ok(total <= PREVIEW_HTML_MAX_CHARS, `中身の合計 ${total} 文字は上限 ${PREVIEW_HTML_MAX_CHARS} 以内のはず`);
    assert.ok(bodies.some((b) => b === OMIT_BODY), '入らないプレビューは、案内（p.art-omit）だけになる');
    assert.ok(bodies.every((b) => b === OMIT_BODY || b.startsWith('<div class="md">')), '中身は div.md か案内のどちらか');
  });

  test(`D0025-AC-37: 上限いっぱいの引用 16 個（${label}）：既定の選び（${NAMES[picked]}）は先に変換されるので、一覧の順で後ろでも案内にならず、中身が入る`, () => {
    const { out, bodies } = renderSixteen(label, mid, running);
    assert.ok(out.includes(`data-art-default="${NAMES[picked]}"`), '既定の選びの前提');
    const body = bodies[picked];
    assert.notEqual(body, OMIT_BODY, '既定の選びのプレビューが案内だけになっていない');
    assert.ok(body.startsWith('<div class="md">') && body.includes('<blockquote>'), '中身（引用）が入っている');
  });

  test(`D0025-AC-37: 上限いっぱいの引用 16 個（${label}）：案内になったプレビューも、見出し・「エディタで開く」・枠は残り、プレビューの数は変わらない。.art-empty は使わない`, () => {
    const { out } = renderSixteen(label, mid, running);
    assert.equal(countOf(out, 'data-art-preview="'), ENTRY_COUNT, 'プレビューは「ある」成果物ごとに 1 つのまま');
    assert.equal(countOf(out, 'class="art-title"'), ENTRY_COUNT, '見出しも成果物ごとに 1 つ');
    assert.equal(countOf(out, 'data-artifact="'), ENTRY_COUNT, '「エディタで開く」も成果物ごとに 1 つ');
    assert.equal(countOf(out, 'data-scroll="artifact"'), ENTRY_COUNT, '中身の枠も成果物ごとに 1 つ');
    assert.ok(countOf(out, 'class="art-omit"') >= 1, '案内がある');
    assert.ok(!out.includes('art-empty'), '案内は .art-empty（「まだ成果物がありません」の検出に使うクラス）にしない');
    assert.ok(!out.includes('まだ成果物がありません'));
  });
}

test('D0025-AC-37: 合計が上限の中に収まるときは、案内は出ず、全部のプレビューに中身が入る（今のまま通る。守る）', () => {  const names = ['01_a.md', '02_b.md', '03_c.txt', '04_d.md'];
  const out = renderArtifacts(viewOf(names.map((name) => entry(name, '# 題\n\n本文'))));
  assert.ok(!out.includes('art-omit'), '案内が出ていない');
  for (const name of names) assert.notEqual(bodyOf(out, name), OMIT_BODY, name);
});
