// 入口 extension.ts の配線の検査（D0021）。AC-51 ②③。
// extension.ts は vscode を import するので、単体では動かせない。判断を持たない呼び出しの形を、ソースを文字で読んで確かめる
// （manifest.test.ts が extension.ts を文字で読む前例と同じ）。設定を変えると開いているパネルの目安が変わる「動き」は AC-43（実機）。
// ここで見るのは配線だけ：設定を読む・関数を呼ぶ・渡す。名前の定数と package.json の一致は names.test.ts・manifest.test.ts（AC-51 ①）、
// 目安だけが違う HTML の差は AC-52（view の側）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

/** 行頭から始まるコメント（ブロックと //）を取り除く。コメントに書いた呼び出しで検査を通さない。文字列の中の「/*」（glob）は行頭にならないので触らない。 */
export function withoutComments(source: string): string {
  return source.replace(/^[ \t]*\/\*[\s\S]*?\*\//gm, '').replace(/^[ \t]*\/\/.*$/gm, '');
}

/** name( の呼び出しごとの、引数の文字（かっこの釣り合いで取る）。import の行（name の後ろに ( が続かない）は拾わない。 */
export function callArgs(code: string, name: string): string[] {
  const out: string[] = [];
  const re = new RegExp(`\\b${name}\\(`, 'g');
  for (let m = re.exec(code); m !== null; m = re.exec(code)) {
    const start = m.index + m[0].length;
    let depth = 1;
    let i = start;
    for (; i < code.length && depth > 0; i++) {
      if (code[i] === '(') depth += 1;
      else if (code[i] === ')') depth -= 1;
    }
    out.push(code.slice(start, depth === 0 ? i - 1 : i));
  }
  return out;
}

export type WiringId = 'staleAfterSeconds' | 'readSetting' | 'previous' | 'renderViewBody' | 'renderPanelHtml' | 'affectsConfiguration';

/** 配線で欠けているもの。空なら全部そろっている。 */
export function wiringProblems(source: string): WiringId[] {
  const code = withoutComments(source);
  const problems: WiringId[] = [];
  // 設定の値を目安の秒にする関数を呼ぶ
  if (!/\bstaleAfterSeconds\(/.test(code)) problems.push('staleAfterSeconds');
  // 設定は名前の定数（SETTING_STALE_AFTER）で読む
  if (!/\.get\s*(?:<[^>]*>)?\(\s*SETTING_STALE_AFTER\b/.test(code)) problems.push('readSetting');
  // 選んだ run の写しを読むとき、前の実行（archive/）かどうかを一覧の行から渡す
  if (!/\bcreateFsWorkDirSource\([^;]*\bprevious:\s*isPreviousRun\(/.test(code)) problems.push('previous');
  // 描くときに目安（staleAfterSec）を渡す
  for (const name of ['renderViewBody', 'renderPanelHtml'] as const) {
    const calls = callArgs(code, name);
    if (calls.length === 0 || !calls.every((args) => /\bstaleAfterSec\b/.test(args))) problems.push(name);
  }
  // 設定が変わったら描き直す
  if (!callArgs(code, 'affectsConfiguration').some((args) => /\bSETTING_STALE_AFTER\b/.test(args))) problems.push('affectsConfiguration');
  return problems;
}

// ---- AC-51 ②：実物の extension.ts の配線 ----

const EXTENSION = readFileSync(new URL('./extension.ts', import.meta.url), 'utf8');

const WIRING: readonly (readonly [WiringId, string])[] = [
  ['staleAfterSeconds', '設定の値を staleAfterSeconds( で目安の秒にしている'],
  ['readSetting', '設定を SETTING_STALE_AFTER の名前で .get( している'],
  ['previous', 'createFsWorkDirSource( に previous: isPreviousRun( を渡している'],
  ['renderViewBody', 'renderViewBody( の呼び出しが staleAfterSec を受けている'],
  ['renderPanelHtml', 'renderPanelHtml( の呼び出しが staleAfterSec を受けている'],
  ['affectsConfiguration', 'affectsConfiguration( に SETTING_STALE_AFTER があり、設定が変わったら描き直す'],
];

for (const [id, what] of WIRING) {
  test(`D0021-AC-51: extension.ts は ${what}`, () => {
    assert.ok(!wiringProblems(EXTENSION).includes(id), `配線が足りない：${what}、という形が extension.ts に無い`);
  });
}

// ---- AC-51 ③：検査そのもの ----

/** 配線がそろっている見本のソース（1 行ずつ。1 行を差し替えて、欠けた見本を作る）。 */
const LINES = {
  imports: "import { SECTION, SETTING_STALE_AFTER } from './app/names.ts';\nimport { staleAfterSeconds } from './app/staleness.ts';",
  setting: "  const staleAfterSec = staleAfterSeconds(vscode.workspace.getConfiguration(SECTION).get<unknown>(SETTING_STALE_AFTER));",
  previous: "  const view = await refreshView(createFsWorkDirSource(choice.dirAbs, choice.dirAbs, { previous: isPreviousRun(list, choice.key) }), choice.dirAbs, clock);",
  viewBody: "  const message = { type: 'render', html: renderViewBody(view, listView, staleAfterSec) };",
  panelHtml: "  created.webview.html = renderPanelHtml(current.view, randomBytes(16).toString('base64'), current.listView, current.staleAfterSec);",
  affects: "  else if (event.affectsConfiguration(`${SECTION}.${SETTING_STALE_AFTER}`)) void render();",
  other: "  if (event.affectsConfiguration(`${SECTION}.${SETTING_SHOW_OTHER}`)) void render();",
};

function sourceWith(over: Partial<typeof LINES> = {}): string {
  return Object.values({ ...LINES, ...over }).join('\n');
}

test('D0021-AC-51: 配線の検査そのもの：配線がそろった見本は見逃す（何も見つけない）。別の設定（SETTING_SHOW_OTHER）の配線だけでは足りない（今のまま通る。守る）', () => {
  assert.deepEqual(wiringProblems(sourceWith()), []);
  assert.deepEqual(wiringProblems(sourceWith({ affects: '' })), ['affectsConfiguration'], '別の設定の affectsConfiguration だけでは足りない');
});

/** 4 点のどれかを欠いた見本と、見つけるはずのもの。 */
const MISSING: readonly (readonly [string, Partial<typeof LINES>, WiringId])[] = [
  ['staleAfterSeconds( を呼ばない', { setting: "  const staleAfterSec = Number(vscode.workspace.getConfiguration(SECTION).get<unknown>(SETTING_STALE_AFTER));" }, 'staleAfterSeconds'],
  ['設定を名前の定数で読まない（文字を直に書く）', { setting: "  const staleAfterSec = staleAfterSeconds(vscode.workspace.getConfiguration(SECTION).get<unknown>('staleAfterMinutes'));" }, 'readSetting'],
  ['previous を渡さない', { previous: '  const view = await refreshView(createFsWorkDirSource(choice.dirAbs, choice.dirAbs), choice.dirAbs, clock);' }, 'previous'],
  ['previous に isPreviousRun を使わない', { previous: '  const view = await refreshView(createFsWorkDirSource(choice.dirAbs, choice.dirAbs, { previous: false }), choice.dirAbs, clock);' }, 'previous'],
  ['renderViewBody( に staleAfterSec を渡さない', { viewBody: "  const message = { type: 'render', html: renderViewBody(view, listView) };" }, 'renderViewBody'],
  ['renderPanelHtml( に staleAfterSec を渡さない', { panelHtml: "  created.webview.html = renderPanelHtml(current.view, randomBytes(16).toString('base64'), current.listView);" }, 'renderPanelHtml'],
  ['renderViewBody( を呼ばない', { viewBody: "  const message = { type: 'render', html: '' };" }, 'renderViewBody'],
  ['設定が変わっても描き直さない（affectsConfiguration に SETTING_STALE_AFTER が無い）', { affects: '' }, 'affectsConfiguration'],
];

for (const [label, over, expected] of MISSING) {
  test(`D0021-AC-51: 配線の検査そのもの：${label}見本は、欠けを見つける（${expected}）（今のまま通る。守る）`, () => {
    assert.deepEqual(wiringProblems(sourceWith(over)), [expected]);
  });
}

test('D0021-AC-51: 配線の検査そのもの：呼び出しが 2 つあり、片方だけ staleAfterSec を渡す見本は、欠けを見つける（今のまま通る。守る）', () => {
  const twice = sourceWith({ viewBody: `${LINES.viewBody}\n  const again = renderViewBody(view, listView);` });
  assert.deepEqual(wiringProblems(twice), ['renderViewBody']);
});

test('D0021-AC-51: 配線の検査そのもの：コメントに書いただけの配線では通らない（行頭の // とブロックコメント）（今のまま通る。守る）', () => {
  const commented = sourceWith({
    setting: `  // ${LINES.setting.trim()}`,
    previous: `/*\n${LINES.previous}\n*/`,
    viewBody: `  // ${LINES.viewBody.trim()}`,
    panelHtml: `  // ${LINES.panelHtml.trim()}`,
    affects: `  // ${LINES.affects.trim()}`,
  });
  assert.deepEqual(wiringProblems(commented).sort(), ['affectsConfiguration', 'previous', 'readSetting', 'renderPanelHtml', 'renderViewBody', 'staleAfterSeconds']);
});

test('D0021-AC-51: 配線の検査そのもの：文字列の中の「/*」（glob）をコメントの始まりと取り違えて、配線の行を消さない（今のまま通る。守る）', () => {
  const withGlob = `const GLOB = '{state.json,*.md,logs/*.jsonl}';\n${sourceWith()}\n/** 後ろのブロックコメント */`;
  assert.deepEqual(wiringProblems(withGlob), []);
});
