// 作業台の「流す」の節の見た目の直し（D0078 AC-39。検証 1 回目の画面の確認で見つかった不具合）。
// 1) 節の中がスクロールしても、ボタン #run-go が下の端に留まる（STYLE の position: sticky; bottom: 0）。
// 2) 狭い幅（右の欄が下に回る幅）では、読み込みのとき 1 回だけ節を畳んだ形で始める（webview/pipeEditor.ts の matchMedia）。
//    その幅の数は STYLE の @media と同じ（片方だけ変えると落ちる）。
// 間隔（すき間）は見た目なのでテストで縛らない。画面で確かめる（.claude/skills/pipe-in/screen-check.md の「作業台の「流す」の節」）。
// 構成：1) 検査の本体  2) 実物  3) 検査そのもの（壊した見本・守った見本）
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { renderPipeEditorHtml } from '../view/pipeEditorHtml.ts';
import { blockAfter, functionBody, withoutComments } from '../test/sourceText.ts';

// ---- 1) 検査の本体 ----

/** <style> の中身 */
function styleOf(html: string): string {
  return /<style[^>]*>([\s\S]*?)<\/style>/.exec(html)?.[1] ?? '';
}

/** #run-go を選ぶ規則（選ぶ並びの1つが #run-go で終わる）の本体の文字。@media の中の規則も数える */
function runGoRules(css: string): string[] {
  const bodies: string[] = [];
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selectors = m[1]!.split(',').map((s) => s.trim());
    if (selectors.some((s) => /(?:^|\s)#run-go$/.test(s))) bodies.push(m[2]!);
  }
  return bodies;
}

/** ボタンが節の下の端に留まる規則があるか */
function runGoSticky(css: string): boolean {
  return runGoRules(css).some((b) => /position\s*:\s*sticky\b/.test(b) && /\bbottom\s*:\s*0(?:px)?\s*(?:;|$)/.test(b));
}

/** 右の欄が図の下に回る @media (max-width: N px) の N。無ければ null */
function wrapWidth(css: string): number | null {
  for (const m of css.matchAll(/@media\s*\(max-width:\s*(\d+)px\)\s*\{/g)) {
    const body = blockAfter(css.slice(m.index), /@media\s*\(max-width:\s*\d+px\)\s*\{/);
    if (body !== null && /\.work\s*>\s*\.side\s*\{[^}]*grid-row/.test(body)) return Number(m[1]);
  }
  return null;
}

const FOLD_CALL = /matchMedia\(\s*['"]\(max-width:\s*(\d+)px\)['"]\s*\)/g;

/** 読み込みのときに節を畳む文の幅（refreshRun の外にあるものだけ）。refreshRun の中にあるものは inside に数える */
function foldWidths(source: string): { outside: number[]; inside: number } {
  const code = withoutComments(source);
  const body = functionBody(code, 'refreshRun');
  const rest = body === null ? code : code.replace(body, '');
  const folds = (text: string): number[] =>
    Array.from(text.matchAll(FOLD_CALL))
      .filter((m) => /^[\s\S]{0,200}?['"]run['"][\s\S]{0,100}?\.open\s*=\s*false\b/.test(text.slice((m.index ?? 0) + m[0].length)))
      .map((m) => Number(m[1]));
  return { outside: folds(rest), inside: body === null ? 0 : folds(body).length };
}

// ---- 1b) 検査の本体（検証 2 回目：ボタンを幅いっぱいの不透明な帯にし、見える順を変える） ----

/** 選ぶ並びの1つが tail に合う規則の本体の文字（@media の中の規則も数える） */
function bodiesEndingWith(css: string, tail: RegExp): string[] {
  const bodies: string[] = [];
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selectors = m[1]!.split(',').map((s) => s.trim());
    if (selectors.some((s) => tail.test(s))) bodies.push(m[2]!);
  }
  return bodies;
}

/** 宣言 prop の値（規則の本体のうち最後に書いたもの）。無ければ null */
function declared(bodies: string[], prop: string): string | null {
  let value: string | null = null;
  for (const b of bodies) {
    for (const m of b.matchAll(new RegExp(`(?:^|[;\\s])${prop}\\s*:\\s*([^;]+)`, 'g'))) value = m[1]!.trim();
  }
  return value;
}

/** #run-go を選ぶ規則のどれかに width: 100% があるか */
function runGoFullWidth(css: string): boolean {
  return declared(runGoRules(css), 'width') === '100%';
}

/** #run-go の規則（無効のときも含む）のどれかに opacity があるか */
function runGoUsesOpacity(css: string): boolean {
  return bodiesEndingWith(css, /(?:^|\s)#run-go(?::[a-z-]+)?$/).some((b) => /(?:^|[;\s])opacity\s*:/.test(b));
}

/** 部品の order（書いていなければ 0） */
function orderOf(css: string, cls: string): number {
  const v = declared(bodiesEndingWith(css, new RegExp(`(?:^|\\s)\\.${cls}$`)), 'order');
  return v === null ? 0 : Number(v);
}

/** 文字数と理由が、起こすコマンドの形より前に見えるか */
function countAndReasonBeforeCmd(css: string): boolean {
  const cmd = orderOf(css, 'run-cmd');
  return orderOf(css, 'run-count') < cmd && orderOf(css, 'run-reason') < cmd;
}

/** #run-info の規則に display: grid があるか */
function runInfoIsGrid(css: string): boolean {
  return declared(bodiesEndingWith(css, /(?:^|\s)#run-info$/), 'display') === 'grid';
}

/** 節（.run）の max-height。wide は @media の外、narrow は @media (max-width) の中 */
function runMaxHeight(css: string): { wide: string | null; narrow: string | null } {
  const head = /@media\s*\(max-width:\s*\d+px\)\s*\{/;
  const media = blockAfter(css, head);
  const outside = media === null ? css : css.replace(media, '');
  const tail = /(?:^|\s)\.run$/;
  return {
    wide: declared(bodiesEndingWith(outside, tail), 'max-height'),
    narrow: media === null ? null : declared(bodiesEndingWith(media, tail), 'max-height'),
  };
}

/** .run-cmd::before の content */
function cmdHeading(css: string): string | null {
  return declared(bodiesEndingWith(css, /\.run-cmd::before$/), 'content');
}

// ---- 2) 実物 ----

const HTML = renderPipeEditorHtml({ nonce: 'n1', scriptUri: 'x.js', cspSource: 'src' });
const CSS = styleOf(HTML);
const SCRIPT = readFileSync(new URL('./pipeEditor.ts', import.meta.url), 'utf8');

test('D0078-AC-39: STYLE の #run-go の規則に position: sticky と bottom: 0 がある（節の中がスクロールしてもボタンが隠れない）', () => {
  assert.notEqual(runGoRules(CSS).length, 0, '#run-go を選ぶ規則が無い');
  assert.ok(runGoSticky(CSS), `#run-go の規則に position: sticky と bottom: 0 が無い：${runGoRules(CSS).join(' | ')}`);
});

test('D0078-AC-39: 節の DOM の順（#run-text-wrap → #run-info → #run-go）は変えない（今のまま通る。守る）', () => {
  const box = /<details class="box run" id="run" open>[\s\S]*?<\/details>/.exec(HTML)?.[0] ?? '';
  assert.notEqual(box, '');
  assert.ok(box.indexOf('id="run-text-wrap"') < box.indexOf('id="run-info"'));
  assert.ok(box.indexOf('id="run-info"') < box.indexOf('id="run-go"'));
});

test('D0078-AC-39: STYLE に、右の欄が図の下に回る @media (max-width: N px) がある（今のまま通る。守る）', () => {
  assert.notEqual(wrapWidth(CSS), null);
});

test('D0078-AC-39: 狭い幅では読み込みのとき、matchMedia で #run の open を false にする文が refreshRun の外にちょうど 1 か所ある', () => {
  const f = foldWidths(SCRIPT);
  assert.equal(f.inside, 0, 'refreshRun の中に書いてある（描き直しのたびに畳んでしまう）');
  assert.equal(f.outside.length, 1, `refreshRun の外の文が ${f.outside.length} か所（1 か所のはず）`);
});

test('D0078-AC-39: 畳む幅の数は、STYLE の「右の欄が下に回る」@media の幅と同じ', () => {
  const wrap = wrapWidth(CSS);
  const f = foldWidths(SCRIPT);
  assert.notEqual(wrap, null);
  assert.deepEqual(f.outside, [wrap], `畳む幅 ${f.outside.join(',')} と @media の幅 ${String(wrap)} が違う`);
});

test('D0078-AC-39: HTML の <details … open> は変えず、広い幅の既定は開いた形（今のまま通る。守る）', () => {
  assert.match(HTML, /<details class="box run" id="run" open>/);
});

test('D0078-AC-39: #run-go の規則に width: 100% がある（幅いっぱいの帯。横に文字が残らない）', () => {
  assert.ok(runGoFullWidth(CSS), `#run-go の規則に width: 100% が無い：${runGoRules(CSS).join(' | ')}`);
});

test('D0078-AC-39: #run-go の規則（無効のときも）に opacity が無い（後ろの文字が透けない）', () => {
  assert.ok(!runGoUsesOpacity(CSS), `opacity がある：${bodiesEndingWith(CSS, /(?:^|\s)#run-go(?::[a-z-]+)?$/).join(' | ')}`);
});

test('D0078-AC-39: #run-info は grid のまま（今のまま通る。守る）', () => {
  assert.ok(runInfoIsGrid(CSS));
});

test('D0078-AC-39: 見える順は 文字数・理由 → 起こすコマンドの形（order が .run-cmd より小さい）', () => {
  assert.ok(
    countAndReasonBeforeCmd(CSS),
    `order：count=${orderOf(CSS, 'run-count')} reason=${orderOf(CSS, 'run-reason')} cmd=${orderOf(CSS, 'run-cmd')}`,
  );
});

test('D0078-AC-39: 節の max-height は広い幅で 50vh、狭い幅（@media）で 30vh', () => {
  assert.deepEqual(runMaxHeight(CSS), { wide: '50vh', narrow: '30vh' });
});

test('D0078-AC-39: .run-cmd::before の content に「起こすコマンド」がある', () => {
  assert.match(cmdHeading(CSS) ?? '', /起こすコマンド/);
});

// ---- 3) 検査そのもの ----

const GOOD_CSS = `
.side > .run { max-height: 50vh; overflow: auto; }
#run-info { display: grid; gap: 6px; }
.run-cmd { display: grid; order: 3; }
.run-cmd::before { content: "起こすコマンド"; }
.run-count { order: 1; }
.run-reason { order: 2; }
.run #run-go { justify-self: start; position: sticky; bottom: 0; width: 100%; box-shadow: 0 -6px 0 var(--panel); }
.run #run-go:disabled { cursor: default; }
@media (max-width: 1000px) {
  .work > .side { grid-column: 1 / -1; grid-row: 3; }
  .side > .run { max-height: 30vh; }
}
`;

const GOOD_SCRIPT = `
function refreshRun(): void {
  const ctx = st.run.ctx;
  ($('run-go') as HTMLButtonElement).disabled = ctx === null;
}
if (window.matchMedia('(max-width: 1000px)').matches) ($('run') as HTMLDetailsElement).open = false;
window.addEventListener('message', () => refreshRun());
`;

test('D0078-AC-39: 検査の見本：守っている CSS・スクリプトは通る', () => {
  assert.ok(runGoSticky(GOOD_CSS));
  assert.equal(wrapWidth(GOOD_CSS), 1000);
  assert.deepEqual(foldWidths(GOOD_SCRIPT), { outside: [1000], inside: 0 });
});

test('D0078-AC-39: 検査の見本（見た目）：守っている CSS は通る', () => {
  assert.ok(runGoFullWidth(GOOD_CSS));
  assert.ok(!runGoUsesOpacity(GOOD_CSS));
  assert.ok(countAndReasonBeforeCmd(GOOD_CSS));
  assert.ok(runInfoIsGrid(GOOD_CSS));
  assert.deepEqual(runMaxHeight(GOOD_CSS), { wide: '50vh', narrow: '30vh' });
  assert.match(cmdHeading(GOOD_CSS) ?? '', /起こすコマンド/);
});

test('D0078-AC-39: 検査の見本（見た目）：opacity のある無効のボタンを見つける', () => {
  assert.ok(runGoUsesOpacity(GOOD_CSS.replace('cursor: default;', 'opacity: .55;')));
  assert.ok(runGoUsesOpacity(GOOD_CSS.replace('justify-self: start;', 'opacity: .9;')));
});

test('D0078-AC-39: 検査の見本（見た目）：order が逆・無い CSS を見つける', () => {
  assert.ok(!countAndReasonBeforeCmd(GOOD_CSS.replace('.run-count { order: 1; }', '.run-count { order: 5; }')));
  assert.ok(!countAndReasonBeforeCmd(GOOD_CSS.replace('.run-reason { order: 2; }', '.run-reason { color: red; }').replace('order: 3;', 'order: -1;')));
  assert.ok(!countAndReasonBeforeCmd(GOOD_CSS.replace(/ order: \d;/g, '')));
});

test('D0078-AC-39: 検査の見本（見た目）：width の無い・min-width だけの #run-go を見つける', () => {
  assert.ok(!runGoFullWidth(GOOD_CSS.replace(' width: 100%;', '')));
  assert.ok(!runGoFullWidth(GOOD_CSS.replace('width: 100%;', 'min-width: 100%;')));
});

test('D0078-AC-39: 検査の見本（見た目）：max-height が 40vh・見出しが無い CSS を見つける', () => {
  assert.equal(runMaxHeight(GOOD_CSS.replace('max-height: 50vh', 'max-height: 40vh')).wide, '40vh');
  assert.equal(runMaxHeight(GOOD_CSS.replace('max-height: 30vh', 'max-height: 50vh')).narrow, '50vh');
  assert.equal(cmdHeading(GOOD_CSS.replace('.run-cmd::before', '.run-cmd::after')), null);
});

test('D0078-AC-39: 検査の見本：sticky の無い #run-go は見つける', () => {
  assert.ok(!runGoSticky(GOOD_CSS.replace('position: sticky; ', '')));
});

test('D0078-AC-39: 検査の見本：bottom: 0 の無い #run-go は見つける', () => {
  assert.ok(!runGoSticky(GOOD_CSS.replace(' bottom: 0;', '')));
});

test('D0078-AC-39: 検査の見本：sticky が #run-go でなく別の部品（.run-note）に付いていても通さない', () => {
  assert.ok(!runGoSticky(GOOD_CSS.replace('.run #run-go {', '.run .run-note {')));
});

test('D0078-AC-39: 検査の見本：数の違う幅で畳む文は、@media の幅と食い違うと見つかる', () => {
  const broken = GOOD_SCRIPT.replace('1000px', '900px');
  assert.notEqual(broken, GOOD_SCRIPT);
  assert.deepEqual(foldWidths(broken).outside, [900]);
  assert.notDeepEqual(foldWidths(broken).outside, [wrapWidth(GOOD_CSS)]);
});

test('D0078-AC-39: 検査の見本：refreshRun の中に書いた畳む文は inside に数え、outside には数えない', () => {
  const inside = GOOD_SCRIPT.replace(
    "if (window.matchMedia('(max-width: 1000px)').matches) ($('run') as HTMLDetailsElement).open = false;\n",
    '',
  ).replace('disabled = ctx === null;', "disabled = ctx === null;\n  if (window.matchMedia('(max-width: 1000px)').matches) ($('run') as HTMLDetailsElement).open = false;");
  assert.deepEqual(foldWidths(inside), { outside: [], inside: 1 });
});

test('D0078-AC-39: 検査の見本：畳む文が無いスクリプト・2 か所あるスクリプト・コメントだけのスクリプトを見分ける', () => {
  const none = GOOD_SCRIPT.replace(/if \(window\.matchMedia[^\n]*\n/, '');
  assert.equal(foldWidths(none).outside.length, 0);
  const line = /if \(window\.matchMedia[^\n]*\n/.exec(GOOD_SCRIPT)![0];
  assert.equal(foldWidths(GOOD_SCRIPT + line).outside.length, 2);
  assert.equal(foldWidths(GOOD_SCRIPT.replace(line, `// ${line}`)).outside.length, 0);
});

test('D0078-AC-39: 検査の見本：#run の open を触らない matchMedia（動きを減らす）は数えない', () => {
  const other = GOOD_SCRIPT.replace(/if \(window\.matchMedia[^\n]*\n/, "const rm = window.matchMedia('(max-width: 1000px)').matches;\nlet x = 1;\n");
  assert.equal(foldWidths(other).outside.length, 0);
});
