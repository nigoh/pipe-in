// 確認用ページの素材のテスト（D0079・AC-39 の見本の行）：scripts/previewPages.ts と scripts/replySamples.ts が作る、返事を受け付けている確認待ちの見本ページ。
//   run-panel-reply-runs-light・run-panel-reply-runs-dark（実行の一覧つき）。一覧の行は、帯の出し分けの 5 つの状態と、ボタンの出ない見本を 1 行ずつ持つ。
// 画面そのもの（AC-44・59〜65）は Playwright で見る。ここで確かめるのは、画面で見る前の素材：ページの一覧・見本の木・各行の記録が帯の表のどの行に当たるか・ページの文字・
// 描き直しを送る補助 window.__previewReply・送った知らせをそのまま残す window.__posted・tests/fixtures/ に書かないこと。
// 見本の記録は一時フォルダ（dest）の中にだけ作る。tests/fixtures/ には足さず・書かない（前後の指紋で確かめる）。
//
// このテストが読む約束（設計の 2.11。実装の段が満たす）：
//   - replySamples.ts：REPLY_ID = 'a1b2c3d4e5'（最初の待ち）・REPLY_NEXT_ID = 'f0e1d2c3b4'（次の待ち）・REPLY_SAMPLES（{ name, patch } の並び）。
//   - previewPages.ts：buildReplyTree(dest) → { workspace }（workspace は dest の中）。replyPageHtml(dest, theme) → ページの文字。PANEL_PAGES に 2 件。panelKind は 'reply'。
//   - 一覧の行（実行の目印）：here|（開発フロー。最初に選ぶ）・here|reply-pipe・here|pause-dev・here|pause-pipe・here|slash・here|chat・here|old・here|done・here|archive/20261016-090000・
//     別の worktree（wt.<登録名>|）・here|hostile。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { WAITING_MESSAGE } from './domain/pipelineView.ts';
import type { PipelineView } from './domain/pipelineView.ts';
import { renderViewBody } from './view/panelHtml.ts';
import { FIXTURES_DIR, PANEL_PAGES, THEMES, buildReplyTree, panelKind, previewClock, readRunsView, replyPageHtml } from '../scripts/previewPages.ts';
import type { RunsPreviewEntry, Theme } from '../scripts/previewPages.ts';
import { REPLY_ID, REPLY_NEXT_ID, REPLY_SAMPLES } from '../scripts/replySamples.ts';
import { bodiesOf, definedVars, dangerousAttributes, fingerprint, plain as plainValue, rootBody, runStub, usedVars } from './test/previewText.ts';
import { withTempDir } from './test/tempDir.ts';
import { hasDriverOf, pausePipeOf, replyOf } from './test/replyFixtures.ts';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const THEME_NAMES: Theme[] = ['light', 'dark'];
const LOCAL_INFO: RegExp[] = [
  /[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_.-]/,
  /(?<![A-Za-z0-9_.-])\/Users\/[A-Za-z0-9_.-]/,
  /(?<![A-Za-z0-9_.-])\/home\/[A-Za-z0-9_.-]/,
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+/,
];

// ---- ページの一覧・種類 ----

test('D0079-AC-39: PANEL_PAGES に run-panel-reply-runs-light（明るい）・run-panel-reply-runs-dark（暗い）の 2 件がある', () => {
  assert.deepEqual(PANEL_PAGES.filter(([name]) => name.startsWith('run-panel-reply-')).map(([name, theme]) => [name, theme]), [
    ['run-panel-reply-runs-light', 'light'],
    ['run-panel-reply-runs-dark', 'dark'],
  ]);
});

test('D0079-AC-39: panelKind は run-panel-reply-runs-* に reply を返す（-reply- は -runs- より先に見る）。ほかのページの種類は変わらない', () => {
  assert.equal(panelKind('run-panel-reply-runs-light'), 'reply');
  assert.equal(panelKind('run-panel-reply-runs-dark'), 'reply');
});

test('D0079-AC-39: 既存のページの種類は変わらない（runs・runs-omitted・waiting・tools・chat ほか。今のまま通る。守る）', () => {
  const expected: Record<string, string> = {
    'run-panel-light': 'done',
    'run-panel-running-dark': 'running',
    'run-panel-waiting-dark': 'waiting',
    'run-panel-runs-light': 'runs',
    'run-panel-runs-dark': 'runs',
    'run-panel-runs-omitted-dark': 'runs-omitted',
    'run-panel-stale-dark': 'stale',
    'run-panel-stale-soon-dark': 'stale-soon',
    'run-panel-artifacts-dark': 'artifacts',
    'run-panel-tools-dark': 'tools',
    'run-panel-budget-dark': 'budget',
    'run-panel-chat-dark': 'chat',
  };
  assert.deepEqual(Object.fromEntries(Object.keys(expected).map((name) => [name, panelKind(name)])), expected);
});

test('D0079-AC-39: 先頭の既存のページ（run-panel-light から run-panel-chat-dark まで）の名前・順・テーマは今のまま（今のまま通る。守る）', () => {
  const names = PANEL_PAGES.map(([name]) => name);
  assert.equal(names[0], 'run-panel-light');
  assert.ok(names.indexOf('run-panel-chat-dark') > names.indexOf('run-panel-tools-dark'));
  assert.equal(new Set(names).size, names.length, '名前の重複が無い');
});

// ---- 定数・見本 ----

test('D0079-AC-39: 見本の識別子は a1b2c3d4e5（最初の待ち）と f0e1d2c3b4（次の待ち）。見本の差し分け（REPLY_SAMPLES）は { name, patch } の並び', () => {
  assert.equal(REPLY_ID, 'a1b2c3d4e5');
  assert.equal(REPLY_NEXT_ID, 'f0e1d2c3b4');
  assert.ok(REPLY_SAMPLES.length > 0, 'REPLY_SAMPLES が空でない');
  for (const sample of REPLY_SAMPLES) {
    assert.equal(typeof sample.name, 'string');
    assert.ok(sample.name.length > 0);
    assert.equal(typeof sample.patch, 'object');
    assert.notEqual(sample.patch, null);
  }
});

// ---- 見本の木：各行の記録が帯の出し分けの表の各行に当たる ----

const KEY = (id: string): string => `here|${id}`;
const KEYS = {
  dev: KEY(''),
  pipe: KEY('reply-pipe'),
  pauseDev: KEY('pause-dev'),
  pausePipe: KEY('pause-pipe'),
  slash: KEY('slash'),
  chat: KEY('chat'),
  old: KEY('old'),
  done: KEY('done'),
  archive: KEY('archive/20261016-090000'),
  hostile: KEY('hostile'),
};

interface Tree {
  entries: RunsPreviewEntry[];
  since: string;
}
const cache: { value?: Promise<Tree> } = {};
/** 見本の木を一時フォルダに作って読む（読み終えたら消す）。「今」は開発フローの印の始めた時刻から 40 秒後。 */
function tree(): Promise<Tree> {
  cache.value ??= withTempDir(async (dest) => {
    const { workspace } = await buildReplyTree(dest);
    assert.ok(workspace.startsWith(dest + path.sep) || workspace === dest, '返す作業フォルダは dest の中');
    const state = JSON.parse(await readFile(path.join(workspace, 'docs', 'pipeline', 'state.json'), 'utf8')) as { reply_wait?: { since?: string } };
    const since = state.reply_wait?.since;
    assert.equal(typeof since, 'string', '開発フロー（直下）の state.json に印（reply_wait）の始めた時刻がある');
    const entries = await readRunsView(workspace, previewClock(since!, 40));
    return { entries, since: since! };
  });
  return cache.value;
}
const entryOf = async (key: string): Promise<RunsPreviewEntry> => {
  const found = (await tree()).entries.find((e) => e.key === key);
  assert.ok(found, `一覧に ${key} の行がある`);
  return found;
};
const rowOf = (e: RunsPreviewEntry) => e.listView.rows.find((r) => r.key === e.key)!;
const bodyOf = (e: RunsPreviewEntry): string => renderViewBody(e.view, e.listView);
const plain = (html: string): string => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
const hasButtons = (html: string): boolean => /data-reply="/.test(html);
const viewOf = (e: RunsPreviewEntry): PipelineView => e.view;

test('D0079-AC-39: 一覧に、設計の表の行（開発フロー・reply-pipe・pause-dev・pause-pipe・slash・chat・old・done・archive・別の worktree・hostile）がそろう。最初に選ぶのは開発フロー', async () => {
  const { entries } = await tree();
  const keys = entries.map((e) => e.key);
  for (const key of Object.values(KEYS)) assert.ok(keys.includes(key), `${key} の行がある`);
  assert.ok(keys.some((k) => k.startsWith('wt.')), '別の worktree の行がある');
  assert.equal(entries.find((e) => e.selected)?.key, KEYS.dev);
});

test('D0079-AC-39: 開発フローの行（印あり）：確認待ちの行になり、ボタンが出る。印の識別子は見本の a1b2c3d4e5', async () => {
  const e = await entryOf(KEYS.dev);
  assert.equal(replyOf(viewOf(e))?.id, REPLY_ID);
  assert.equal(rowOf(e).state, 'waiting');
  assert.match(bodyOf(e), new RegExp(`data-reply-id="${REPLY_ID}"`));
  assert.ok(hasButtons(bodyOf(e)));
  assert.ok(!bodyOf(e).includes(WAITING_MESSAGE));
});

test('D0079-AC-39: reply-pipe の行（パイプ・印あり）：パイプの段の表示名で、ボタンが出る', async () => {
  const e = await entryOf(KEYS.pipe);
  assert.notEqual(replyOf(viewOf(e)), null);
  assert.equal(rowOf(e).state, 'waiting');
  assert.ok(hasButtons(bodyOf(e)));
  assert.match(plain(bodyOf(e)), new RegExp(`${replyOf(viewOf(e))!.label}の確認を待っている`));
});

test('D0079-AC-39: pause-dev の行（driver なし・pending_review）：pipe-in --review approve の案内で、ボタンは出ない', async () => {
  const e = await entryOf(KEYS.pauseDev);
  assert.equal(replyOf(viewOf(e)), null);
  assert.notEqual(viewOf(e).pendingReview, null);
  assert.equal(hasDriverOf(viewOf(e)), false);
  assert.equal(pausePipeOf(viewOf(e)), null);
  assert.match(plain(bodyOf(e)), /pipe-in --review approve/);
  assert.ok(!hasButtons(bodyOf(e)));
});

test('D0079-AC-39: pause-pipe の行（パイプの記録・driver なし・pending_review）：--review approve --pipe pause-pipe の案内で、ボタンは出ない', async () => {
  const e = await entryOf(KEYS.pausePipe);
  assert.equal(pausePipeOf(viewOf(e)), 'pause-pipe');
  assert.match(plain(bodyOf(e)), /pipe-in --review approve --pipe pause-pipe/);
  assert.ok(!hasButtons(bodyOf(e)));
});

test('D0079-AC-39: slash の行（driver が pipe-dev・pending_review）：record review と /pipe-in --artifact の案内で、ボタンは出ない', async () => {
  const e = await entryOf(KEYS.slash);
  assert.equal(hasDriverOf(viewOf(e)), true);
  assert.equal(viewOf(e).chatPipe, null);
  assert.match(plain(bodyOf(e)), /python -m pipe_in record review/);
  assert.match(plain(bodyOf(e)), /\/pipe-in --artifact/);
  assert.ok(!hasButtons(bodyOf(e)));
});

test('D0079-AC-39: chat の行（driver が pipe-chat・pending_review）：pipe-in-gen chat review の案内で、ボタンは出ない', async () => {
  const e = await entryOf(KEYS.chat);
  assert.notEqual(viewOf(e).chatPipe, null);
  assert.match(plain(bodyOf(e)), /pipe-in-gen chat review/);
  assert.ok(!hasButtons(bodyOf(e)));
});

test('D0079-AC-39: old の行（確認ありの段が済んで答えなし・印なし）：「次を待っている（人の確認かもしれない）」で、ボタンは出ない', async () => {
  const e = await entryOf(KEYS.old);
  assert.equal(replyOf(viewOf(e)), null);
  assert.equal(viewOf(e).pendingReview, null);
  assert.equal(viewOf(e).waiting, true);
  assert.ok(bodyOf(e).includes(WAITING_MESSAGE));
  assert.ok(!hasButtons(bodyOf(e)));
});

test('D0079-AC-39: done の行（終わった・印あり）、archive の行（印あり）、別の worktree の行（印あり）：帯が無く、ボタンは出ない。確認待ちの行にならない', async () => {
  const done = await entryOf(KEYS.done);
  assert.notEqual(viewOf(done).final, null);
  const archive = await entryOf(KEYS.archive);
  const remote = (await tree()).entries.find((e) => e.key.startsWith('wt.'));
  assert.ok(remote, '別の worktree の行がある');
  for (const e of [done, archive, remote]) {
    assert.equal(replyOf(viewOf(e)), null, e.key);
    assert.ok(!hasButtons(bodyOf(e)), `${e.key}: ボタンが出ない`);
    assert.notEqual(rowOf(e).state, 'waiting', `${e.key}: 確認待ちの行にならない`);
  }
});

test('D0079-AC-39: 一覧の確認待ちは、印のある 2 行（開発フロー・reply-pipe）と pending_review の行だけ。条件を崩した印のある行は数えない', async () => {
  const { entries } = await tree();
  const waiting = entries[0]!.listView.rows.filter((r) => r.state === 'waiting').map((r) => r.key);
  for (const key of [KEYS.dev, KEYS.pipe, KEYS.pauseDev, KEYS.pausePipe, KEYS.slash, KEYS.chat]) assert.ok(waiting.includes(key), `${key} は確認待ち`);
  for (const key of [KEYS.old, KEYS.done, KEYS.archive]) assert.ok(!waiting.includes(key), `${key} は確認待ちでない`);
  assert.ok(!waiting.some((k) => k.startsWith('wt.')), '別の worktree の印のある行は確認待ちでない');
});

test('D0079-AC-39: hostile の行（段の名前・表示名・文書名・パイプ名に <script> や引用符）：ボタンは出て、文字はタグにならず、エスケープされて見える', async () => {
  const e = await entryOf(KEYS.hostile);
  const body = bodyOf(e);
  assert.notEqual(replyOf(viewOf(e)), null);
  assert.ok(hasButtons(body));
  assert.doesNotMatch(body, /<script>alert|<img [^>]*onerror/i);
  assert.ok(body.includes('&lt;script&gt;') || body.includes('&lt;img'), 'エスケープされた形で出ている');
});

// ---- 見本の木は tests/fixtures/ に書かない ----

test('D0079-AC-39: 見本の木は一時フォルダの中にだけ作り、tests/fixtures/ には書かない（前後の指紋が同じ）（空の形では何も作らないので、今のまま通る。守る）', async () => {
  const before = await fingerprint(FIXTURES_DIR);
  await withTempDir(async (dest) => {
    await buildReplyTree(dest);
  });
  assert.deepEqual(await fingerprint(FIXTURES_DIR), before);
});

// ---- ページの文字 ----

const builtPages = new Map<Theme, Promise<{ html: string; dest: string }>>();
function page(theme: Theme): Promise<{ html: string; dest: string }> {
  let found = builtPages.get(theme);
  if (found === undefined) {
    found = withTempDir(async (dest) => ({ html: await replyPageHtml(dest, theme), dest }));
    builtPages.set(theme, found);
  }
  return found;
}

test('D0079-AC-39: ページの script と style のタグはすべて nonce="preview" を持ち、style 属性を使わない。CSP をそのまま持ち、使う --vscode-* の色をすべて THEMES が決めている', async () => {
  for (const theme of THEME_NAMES) {
    const { html } = await page(theme);
    const tags = [...html.matchAll(/<(script|style)\b[^>]*>/g)].map((m) => m[0]);
    assert.ok(tags.length >= 4, `${theme}: 本物の style・script と、テーマの色・置き換え・__previewReply（${tags.length} 個）`);
    assert.deepEqual(tags.filter((t) => !t.includes('nonce="preview"')), [], theme);
    assert.doesNotMatch(html, /\sstyle="/, `${theme}: style 属性を使わない（CSP に捨てられる）`);
    assert.match(html, /<meta http-equiv="Content-Security-Policy"[^>]*>/);
    const defined = definedVars(THEMES[theme]);
    assert.deepEqual(usedVars(html).filter((name) => !defined.has(name)), [], `${theme}: THEMES に無い色`);
    assert.ok(html.includes(THEMES[theme]), `${theme}: テーマの色がページに入っている`);
  }
});

test('D0079-AC-39: ページに入っている本体すべて（初めの本体・行ごとの本体）に、タグの属性として style・on…・src・href が無い（外部の読み込みが無い）', async () => {
  const { html } = await page('dark');
  const bodies = [rootBody(html), ...Object.values(bodiesOf(html))];
  assert.ok(bodies.length >= 11, `行ごとの本体がそろっている（${bodies.length}）`);
  for (const body of bodies) assert.deepEqual(dangerousAttributes(body), []);
  assert.ok(!html.includes('<script>alert'), '生の <script> が入っていない');
});

test('D0079-AC-39: 明るいページと暗いページは、テーマの色の <style> 以外が同じ。同じ見本から 2 回作ると、ページの文字が同じ', async () => {
  const strip = (html: string, theme: Theme): string => html.replace(`:root{${THEMES[theme]}}`, '');
  assert.ok((await page('dark')).html.length > 1000, 'ページが作れている');
  assert.equal(strip((await page('light')).html, 'light'), strip((await page('dark')).html, 'dark'));
  const again = await withTempDir((dest) => replyPageHtml(dest, 'dark'));
  assert.equal(again, (await page('dark')).html, '一時フォルダの名前・時刻に左右されない');
});

test('D0079-AC-39: ページに手元の情報（ユーザー名の入ったパス・メールアドレス）や、一時フォルダ・リポジトリの絶対パスが出ていない', async () => {
  for (const theme of THEME_NAMES) {
    const { html, dest } = await page(theme);
    assert.ok(html.length > 1000, 'ページが作れている');
    assert.deepEqual(LOCAL_INFO.filter((re) => re.test(html)).map(String), [], theme);
    assert.ok(!html.includes(dest), `${theme}: 一時フォルダの絶対パスが出ていない`);
    assert.ok(!html.includes(REPO), `${theme}: リポジトリの絶対パスが出ていない`);
  }
});

test('D0079-AC-39: 初めのページ（開発フロー）に返事を受け付けている帯がある：識別子 a1b2c3d4e5 と 3 つのボタン', async () => {
  const { html } = await page('dark');
  const root = rootBody(html);
  assert.match(root, new RegExp(`data-reply-id="${REPLY_ID}"`));
  assert.deepEqual([...root.matchAll(/data-reply="([^"]+)"/g)].map((m) => m[1]!).slice(0, 3), ['approve', 'revise-open', 'quit-open']);
});

// ---- 描き直しを送る補助 window.__previewReply と、送った知らせを残す window.__posted ----

test('D0079-AC-39: ページに window.__previewReply がある：same・other・sent・stalled・gone の 5 つの名前を扱い、次の待ちの識別子 f0e1d2c3b4・送った（data-reply-sent=1）・30 秒（data-reply-stalled=1）の本体を埋めている', async () => {
  const { html } = await page('dark');
  const at = html.indexOf('window.__previewReply');
  assert.ok(at >= 0, 'window.__previewReply がある');
  const helper = html.slice(at);
  for (const name of ['same', 'other', 'sent', 'stalled', 'gone']) assert.match(helper, new RegExp(`['"]${name}['"]`), name);
  assert.match(helper, new RegExp(`data-reply-id=\\\\?"${REPLY_NEXT_ID}\\\\?"`), '次の待ちの識別子');
  assert.match(helper, /data-reply-sent=\\?"1\\?"/, '送った');
  assert.match(helper, /data-reply-stalled=\\?"1\\?"/, '30 秒たった');
});

test('D0079-AC-39: 埋めた本体に生の < が無い（</script> などでページが切れない。< は \\u003c にしてある）', async () => {
  const { html } = await page('dark');
  const at = html.indexOf('window.__previewReply');
  const end = html.indexOf('</script>', at);
  assert.ok(end > at);
  assert.ok(!html.slice(at, end).includes('<'), '補助のスクリプトの中に < が無い');
});

test('D0079-AC-39: window.__posted は、パネルから送られた知らせのオブジェクトをそのまま残す（reply の知らせの動作・直してほしい点まで）。reply の知らせには何も返さない', async () => {
  const { html } = await page('dark');
  const { win, sent } = runStub(html);
  const api = win.acquireVsCodeApi();
  api.postMessage({ type: 'ready' });
  api.postMessage({ type: 'reply', action: 'approve' });
  api.postMessage({ type: 'reply', action: 'revise', feedback: '直して' });
  assert.deepEqual(plainValue(win.__posted), [{ type: 'ready' }, { type: 'reply', action: 'approve' }, { type: 'reply', action: 'revise', feedback: '直して' }]);
  assert.deepEqual(plainValue(sent), [], 'reply の知らせには返さない');
});

test('D0079-AC-39: 一覧の行を押す知らせ（selectRun）には、今までどおりその行の本体を render で返し、その知らせも window.__posted に残る', async () => {
  const { html } = await page('dark');
  const { win, sent } = runStub(html);
  win.acquireVsCodeApi().postMessage({ type: 'selectRun', id: KEYS.pausePipe });
  assert.equal(sent.length, 1);
  assert.equal(sent[0].type, 'render');
  assert.match(plain(sent[0].html), /pipe-in --review approve --pipe pause-pipe/);
  assert.deepEqual(plainValue(win.__posted), [{ type: 'selectRun', id: KEYS.pausePipe }]);
});
