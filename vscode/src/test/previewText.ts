// テストの補助：確認用ページの文字を読む部品（D0050 で previewPagesArtifacts.test.ts から移した。関数の中身は変えていない）。
// 移した理由：D0025-AC-75 の「同じ切り出し」（panelsOf）を 1 つの定義で守り、新しい previewPagesTools.test.ts と shellHtmlTools.test.ts も同じ切り出しを使うため。
// 元のファイルに残したもの：FIXTURE_DIRS と fixturePrints（見本のフォルダの定数に依る）。
// この補助は読むだけ。ファイルを書くものは無い（fingerprint は読むだけ）。
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';

// ---- 指紋（見本の記録が変わっていないかを見る） ----

/** dir の下のファイルごとの「相対パス・大きさ・更新時刻・中身の指紋」。順番は名前順。 */
export async function fingerprint(dir: string): Promise<string[]> {
  const out: string[] = [];
  const walk = async (d: string): Promise<void> => {
    const entries = (await readdir(d, { withFileTypes: true })).sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    for (const ent of entries) {
      const full = path.join(d, ent.name);
      if (ent.isDirectory()) {
        await walk(full);
        continue;
      }
      const info = await stat(full);
      const sum = createHash('sha1').update(await readFile(full)).digest('hex');
      out.push(`${path.relative(dir, full).split(path.sep).join('/')}|${info.size}|${info.mtimeMs}|${sum}`);
    }
  };
  await walk(dir);
  return out;
}

// ---- ページの文字の読み方 ----

export function between(text: string, from: string, to: string): string {
  const start = text.indexOf(from);
  if (start < 0) return '';
  const end = text.indexOf(to, start + from.length);
  return text.slice(start, end < 0 ? undefined : end);
}

export function unescapeText(value: string): string {
  return value
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

/** text の start から始まる JSON のオブジェクトを、波かっこの釣り合いで切り出して読む（文字列の中の波かっこと \ は数えない）。 */
export function jsonObjectAt(text: string, start: number): Record<string, string> {
  let depth = 0;
  let inString = false;
  for (let i = start; i < text.length; i++) {
    const c = text[i];
    if (inString) {
      if (c === '\\') i += 1;
      else if (c === '"') inString = false;
      continue;
    }
    if (c === '"') inString = true;
    else if (c === '{') depth += 1;
    else if (c === '}') {
      depth -= 1;
      if (depth === 0) return JSON.parse(text.slice(start, i + 1)) as Record<string, string>;
    }
  }
  throw new Error('BODIES の JSON が閉じていない');
}

/** 実行の一覧のページに埋めた、行の key ごとの本体（BODIES）。 */
export function bodiesOf(html: string): Record<string, string> {
  const at = html.indexOf('const BODIES=');
  assert.ok(at >= 0, 'BODIES がある');
  return jsonObjectAt(html, at + 'const BODIES='.length);
}

/** `window.__previewNext=…html:"…"` に埋めた本体を、JSON として読み戻す。 */
export function previewNextBody(html: string): string {
  const at = html.indexOf('window.__previewNext=');
  assert.ok(at >= 0, 'window.__previewNext がある');
  const m = /html:("(?:[^"\\]|\\.)*")/.exec(html.slice(at));
  assert.ok(m !== null, '__previewNext に本体の文字が埋まっている');
  return JSON.parse(m[1]!) as string;
}

/** ページの <div class="root"> の中（初めの本体）。 */
export function rootBody(html: string): string {
  const head = '<div class="root">';
  const start = html.indexOf(head);
  assert.ok(start >= 0, '<div class="root"> がある');
  const end = html.indexOf('</div>\n<script nonce="preview">', start);
  assert.ok(end > start, '本体のあとにパネルのスクリプトがある');
  return html.slice(start + head.length, end);
}

/** ページに入っている本体すべて：行ごとの本体（BODIES があるページ）か初めの本体、と、次の本体（__previewNext があるページ）。 */
export function pageBodies(html: string): string[] {
  const bodies = html.includes('const BODIES=') ? Object.values(bodiesOf(html)) : [rootBody(html)];
  if (html.includes('window.__previewNext=')) bodies.push(previewNextBody(html));
  return bodies;
}

/** 本体の文字の、「図と出力」と「使用量」のパネルをつないだもの（「成果物」のパネルは含めない。AC-75）。 */
export function panelsOf(text: string): string {
  const diagram = text.indexOf('<div class="tabpanel" role="tabpanel" data-detail-panel="diagram"');
  assert.ok(diagram >= 0, '「図と出力」のパネルがある');
  const artifactsAt = text.indexOf('data-detail-panel="artifacts"', diagram);
  assert.ok(artifactsAt >= 0, '「成果物」のパネルがある');
  const artifacts = text.lastIndexOf('<div class="tabpanel"', artifactsAt);
  assert.ok(artifacts > diagram, '「成果物」のパネルは「図と出力」のあと');
  const usage = text.indexOf('<div class="tabpanel" role="tabpanel" data-detail-panel="usage"', artifacts);
  assert.ok(usage > artifacts, '「使用量」のパネルがある');
  const end = text.indexOf('</main>', usage);
  assert.ok(end > usage, '「使用量」のパネルのあとに </main> がある');
  return text.slice(diagram, artifacts) + text.slice(usage, end);
}

export const sha256 = (text: string): string => createHash('sha256').update(text, 'utf8').digest('hex');

/** 実行の一覧で aria-pressed="true" の行の data-run（見ている行）。 */
export function pressedRuns(html: string): string[] {
  return [...html.matchAll(/<button\b[^>]*\sdata-run="([^"]*)"[^>]*\saria-pressed="true"/g)].map((m) => m[1]!);
}

/** HTML からスクリプトとスタイルの中身を除き、タグだけを取り出して、属性の名前（小文字）を並べる。属性の値の中の文字は見ない。 */
export function tagAttributeNames(html: string): string[] {
  const markup = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, '').replace(/<style\b[^>]*>[\s\S]*?<\/style>/g, '');
  const names: string[] = [];
  for (const tag of markup.matchAll(/<[a-zA-Z][^>]*>/g)) {
    const bare = tag[0].replace(/="[^"]*"/g, '=""');
    for (const attr of bare.matchAll(/\s([^\s=/>"']+)/g)) names.push(attr[1]!.toLowerCase());
  }
  return names;
}
/** 実行される・読み込まれる道になる属性（style・on…・src・href）。 */
export const dangerousAttributes = (html: string): string[] => tagAttributeNames(html).filter((n) => n === 'style' || n === 'src' || n === 'href' || n.startsWith('on'));

export function usedVars(html: string): string[] {
  return [...new Set([...html.matchAll(/var\(\s*(--vscode-[\w-]+)/g)].map((m) => m[1]!))].sort();
}
export function definedVars(css: string): Set<string> {
  return new Set([...css.matchAll(/(--vscode-[\w-]+)\s*:/g)].map((m) => m[1]!));
}

// ---- recordPosted（window.__posted） ----

/** ページの <body> 直後の置き換えのスクリプト（acquireVsCodeApi）の文字。 */
export function stubOf(html: string): string {
  const m = /<body>\s*<script nonce="preview">([\s\S]*?)<\/script>/.exec(html);
  assert.ok(m !== null, '<body> の直後に置き換えのスクリプトがある');
  return m[1]!;
}
export interface StubWindow {
  postMessage(message: unknown): void;
  acquireVsCodeApi(): { postMessage(message: unknown): void };
  __posted?: unknown;
}
/** 置き換えのスクリプトを偽の window の上で動かす。window.postMessage で届いたものは sent に貯める。 */
export function runStub(html: string): { win: StubWindow; sent: any[] } {
  const sent: any[] = [];
  const win = { postMessage: (message: unknown) => void sent.push(message) } as StubWindow;
  vm.runInNewContext(stubOf(html), { window: win });
  return { win, sent };
}
export const plain = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
