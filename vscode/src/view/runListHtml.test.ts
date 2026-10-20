// 実行の一覧の HTML と CSS（D0019・2版目の作り直し）。純粋な文字列の検査。
// 左の欄に、絞り込みの入力・状態のタブ・状態ごとの見出し・3 行の行。色はテーマの変数だけ・動きは no-preference の中だけ・外から来た文字は escapeHtml。
// 新しい部品（view/runListHtml.ts の作り直し）は、呼んだところで落ちるように、テストの中で読み込む。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderViewBody } from './panelHtml.ts';
import { escapeHtml } from './escape.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { hidingInReduce, keyframesInNoPreference, motionOutsideNoPreference, parseCss } from '../test/cssBlocks.ts';
import { snapshot } from '../test/fixtures.ts';
import { SID, listView, row, sampleRows } from '../test/runListFixtures.ts';
import type { RunListView, RunRow } from '../domain/runList.ts';

const html = () => import('./runListHtml.ts');
const render = async (list: RunListView): Promise<string> => (await html()).renderRunList(list);
const body = (list?: RunListView | null) => renderViewBody(buildPipelineView(snapshot()), list as RunListView | undefined);

/** 一覧の行（<li …>…</li>）を並びの順に取り出す */
function rowsOf(out: string): string[] {
  return [...out.matchAll(/<li\b[^>]*>[\s\S]*?<\/li>/g)].map((m) => m[0]);
}
const rowOf = (out: string, key: string): string => {
  const found = rowsOf(out).find((r) => r.includes(`data-run="${key}"`));
  assert.ok(found, `${key} の行がある`);
  return found;
};
const count = (text: string, re: RegExp): number => (text.match(re) ?? []).length;
const plain = (text: string): string => text.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
/** from の印から to の印の手前まで（無ければ終わりまで） */
function between(text: string, from: string, to: string): string {
  const start = text.indexOf(from);
  assert.ok(start >= 0, `${from} がある`);
  const end = text.indexOf(to, start + from.length);
  return text.slice(start, end < 0 ? undefined : end);
}
/** open の直後から、その要素の閉じ </span> の手前まで（入れ子の <span> を数える） */
function spanInner(text: string, open: string): string {
  const at = text.indexOf(open);
  assert.ok(at >= 0, `${open} がある`);
  const from = at + open.length;
  let depth = 1;
  const tag = /<span\b|<\/span>/g;
  tag.lastIndex = from;
  for (let m = tag.exec(text); m !== null; m = tag.exec(text)) {
    depth += m[0] === '</span>' ? -1 : 1;
    if (depth === 0) return text.slice(from, m.index);
  }
  assert.fail(`${open} の閉じ </span> が無い`);
}
/** 行の 2 行目（パイプ名 · ブランチ · … · 状態 · 今の段）の文字。run-sub の span の中だけ */
const subOf = (r: string): string => plain(spanInner(r, 'class="run-sub">'));
/** 行の 1 行目の右側（待ち時間か経過・日付）。run-sub の前まで */
const rightOf = (r: string): string => between(r, 'class="run-right"', 'class="run-sub"');
const groupKeys = (out: string): string[] => [...out.matchAll(/<section class="run-group" data-group="([^"]+)"/g)].map((m) => m[1]!);

// ---- AC-43：一覧は run が 0・1・2 つ以上のどれでも出る ----

test('D0019-AC-43: 行が 0 のとき、一覧は出て「実行がありません」が見える。タブの件数は 0、見出しは出ない', async () => {
  const out = await render(listView([], { selected: 'here|' }));
  assert.match(out, /<p class="run-none"[^>]*>実行がありません<\/p>/);
  assert.doesNotMatch(out.match(/<p class="run-none"[^>]*>/)![0], /hidden/, '0 件のときは見える');
  assert.deepEqual(groupKeys(out), []);
  assert.equal(count(out, /data-run="/g), 0);
  const counts = [...out.matchAll(/<span class="count">(\d+)<\/span>/g)].map((m) => m[1]);
  assert.deepEqual(counts, ['0', '0', '0', '0']);
});

test('D0019-AC-43: 行が 1 つのときも一覧が出る（1回目の「1 つだけのときは出ない」は廃止）。「実行がありません」は出ない', async () => {
  const out = await render(listView([row({ key: 'here|' })]));
  assert.equal(count(out, /data-run="/g), 1);
  assert.doesNotMatch(out, /class="run-none"/);
  assert.match(out, /class="run-list"/);
});

test('D0019-AC-43: パネルの本体は、一覧を渡さない・null のときも 0 件の一覧を出す', () => {
  for (const out of [body(), body(null)]) {
    assert.match(out, /class="run-list"/);
    assert.match(out, /実行がありません/);
    assert.equal(count(out, /data-run="/g), 0);
  }
});

// ---- AC-56：絞り込み・状態のタブ・状態の見出し ----

test('D0019-AC-56: 絞り込みの入力はラベルつきの type="search" で、パネルの中だけの入力（data-keep="filter"）', async () => {
  const out = await render(listView(sampleRows()));
  assert.match(out, /<label class="run-search"[^>]*>/);
  assert.match(out, /<input type="search"[^>]*data-keep="filter"[^>]*>/);
  assert.match(out, /実行を絞り込む/, '見えないラベルの文字（スクリーンリーダー用）');
  assert.match(out, /placeholder="[^"]*絞り込む[^"]*"/);
  assert.match(out, /autocomplete="off"/);
  assert.equal(count(out, /<input\b/g), 1);
});

test('D0019-AC-56: 状態のタブは すべて・確認待ち・動いている・終わった の 4 つで、role="tablist" の中に並び、選んでいるのは すべて だけ（aria-selected）', async () => {
  const out = await render(listView(sampleRows()));
  assert.match(out, /<div class="run-tabs" role="tablist"[^>]*>/);
  const tabs = [...out.matchAll(/<button\b[^>]*data-list-tab="([^"]+)"[^>]*>([\s\S]*?)<\/button>/g)];
  assert.deepEqual(tabs.map((t) => t[1]), ['all', 'waiting', 'running', 'done']);
  assert.deepEqual(tabs.map((t) => plain(t[2]!).replace(/\d+$/, '')), ['すべて', '確認待ち', '動いている', '終わった']);
  for (const t of tabs) assert.match(t[0], /type="button"/);
  for (const t of tabs) assert.match(t[0], /role="tab"/);
  assert.deepEqual(tabs.map((t) => /aria-selected="(true|false)"/.exec(t[0])?.[1]), ['true', 'false', 'false', 'false']);
});

test('D0019-AC-56: タブの件数は記録の run の数（待ち idle は「動いている」に数える）。絞り込みの文字には関わらない', async () => {
  const out = await render(listView(sampleRows()));
  const tabs = [...out.matchAll(/<button\b[^>]*data-list-tab="([^"]+)"[^>]*>[\s\S]*?<span class="count">(\d+)<\/span>[\s\S]*?<\/button>/g)];
  assert.deepEqual(tabs.map((t) => [t[1], t[2]]), [['all', '8'], ['waiting', '2'], ['running', '3'], ['done', '3']]);
});

test('D0019-AC-56: 状態ごとの見出しで行を分ける。見出しの順は 確認待ち → 動いている → 終わった で、行が 1 つも無い見出しは出さない', async () => {
  const out = await render(listView(sampleRows()));
  assert.deepEqual(groupKeys(out), ['waiting', 'running', 'done']);
  const heads = [...out.matchAll(/<h2 class="run-group-head">([^<]*)<\/h2>/g)].map((m) => m[1]);
  assert.deepEqual(heads, ['確認待ち', '動いている', '終わった']);
  const onlyDone = await render(listView([row({ key: 'here|a', state: 'done', result: '合格' })]));
  assert.deepEqual(groupKeys(onlyDone), ['done']);
  const noWaiting = await render(listView([row({ key: 'here|a', state: 'running' }), row({ key: 'here|b', state: 'idle' })]));
  assert.deepEqual(groupKeys(noWaiting), ['running']);
});

test('D0019-AC-56: 行は渡された順のまま、それぞれの見出しの中に入る。idle の行は「動いている」の見出しの中で、li の data-group は running', async () => {
  const out = await render(listView(sampleRows()));
  const keysIn = (group: string): string[] => {
    const section = new RegExp(`<section class="run-group" data-group="${group}">[\\s\\S]*?</section>`).exec(out)![0];
    return [...section.matchAll(/data-run="([^"]*)"/g)].map((m) => m[1]!);
  };
  assert.deepEqual(keysIn('waiting'), ['here|', 'wt.feat-x|']);
  assert.deepEqual(keysIn('running'), ['here|diagrams', 'wt.fix-login|', 'here|idle']);
  assert.deepEqual(keysIn('done'), ['here|survey', 'here|review', 'here|archive/20261016-090000']);
  assert.match(rowOf(out, 'here|idle'), /^<li\b[^>]*data-group="running"/);
  assert.match(rowOf(out, 'here|'), /^<li\b[^>]*data-group="waiting"/);
  assert.match(rowOf(out, 'here|review'), /^<li\b[^>]*data-group="done"/);
});

test('D0019-AC-56: 行の一覧は一覧だけがスクロールする枠（data-scroll="list"）の中にあり、省いた件数の文字もその中に入る', async () => {
  const out = await render(listView(sampleRows(), { omitted: [{ place: null, count: 2 }] }));
  assert.match(out, /<div class="run-scroll" data-scroll="list">/);
  const scroll = out.indexOf('class="run-scroll"');
  assert.ok(scroll > out.indexOf('data-list-tab="all"'), 'タブのあとに一覧の枠');
  assert.ok(out.indexOf('class="run-group"') > scroll);
  assert.ok(out.indexOf('class="run-omitted"') > out.indexOf('class="run-group"'), '省いた件数は行のあと');
  assert.ok(out.indexOf('class="run-search"') < out.indexOf('data-list-tab="all"'), '入力 → タブ → 行 の順');
});

test('D0019-AC-58: 絞り込みのための印：li に data-name（セッション名）・data-sid（セッション ID の全部）・data-branch（ブランチ名）。無い項目は空', async () => {
  const out = await render(listView(sampleRows()));
  const r = rowOf(out, 'wt.feat-x|');
  assert.match(r, /data-name="CSV 出力を足す"/);
  assert.match(r, new RegExp(`data-sid="${SID.feat}"`));
  assert.match(r, /data-branch="feat\/export-csv"/);
  const bare = rowOf(out, 'here|idle');
  assert.match(bare, /data-sid=""/);
  const noBranch = await render(listView([row({ key: 'here|', branch: null })]));
  assert.match(noBranch, /data-branch=""/);
});

test('D0019-AC-58: 「該当する実行がありません」が、初めは隠れた状態（hidden）で一覧にある。行が 0 のときの「実行がありません」とは別の文', async () => {
  const out = await render(listView(sampleRows()));
  assert.match(out, /<p class="run-empty" hidden>該当する実行がありません<\/p>/);
  assert.doesNotMatch(out, /class="run-none"/);
});

// ---- AC-03・AC-57：行の 3 行の中身 ----

test('D0019-AC-03: 行は 1 行目 セッション名・日付、2 行目 パイプ名 · ブランチ · 状態 · 今の段、3 行目 セッション ID の先頭 8 文字（等幅）', async () => {
  const out = await render(listView(sampleRows()));
  const r = rowOf(out, 'wt.feat-x|');
  assert.match(r, /<span class="run-session">CSV 出力を足す<\/span>/);
  assert.match(r, /<span class="run-date">10\/17<\/span>/);
  assert.match(r, /<span class="run-id">bbbb2222<\/span>/);
  const sub = subOf(r);
  const at = (word: string): number => {
    const i = sub.indexOf(word);
    assert.ok(i >= 0, `「${sub}」に ${word} がある`);
    return i;
  };
  assert.ok(at('spec-qa') < at('feat/export-csv'), 'パイプ名 → ブランチ');
  assert.ok(at('feat/export-csv') < at('確認待ち'), 'ブランチ → 状態');
  assert.ok(at('確認待ち') < at('図を描く'), '状態 → 今の段');
  assert.ok(/<span class="run-id">[^<]{8}<\/span>/.test(r) && !/<span class="run-id">[^<]{9,}<\/span>/.test(r), 'ID は先頭 8 文字だけ');
  const idPos = r.indexOf('class="run-id"');
  assert.ok(idPos > r.indexOf('class="run-sub"') && r.indexOf('class="run-sub"') > r.indexOf('class="run-session"'), '1 行目 → 2 行目 → 3 行目の順');
});

test('D0019-AC-03: セッション ID が無い行は「—」。読めない日付・ブランチ名なしも、そのまま「—」か省く', async () => {
  const out = await render(
    listView([row({ key: 'here|', session: '名前', sessionId: null, updatedDate: '—', updatedText: '—', branch: null, stage: '—' }), row({ key: 'here|x' })]),
  );
  const r = rowOf(out, 'here|');
  assert.match(r, /<span class="run-id">—<\/span>/);
  assert.match(r, /<span class="run-date">—<\/span>/);
  assert.doesNotMatch(subOf(r), /null|undefined/);
  const sub = subOf(r);
  assert.ok(sub.includes('開発フロー') && sub.includes('動いている') && sub.includes('—'), `パイプ名・状態・今の段(—)が読める：${sub}`);
});

test('D0019-AC-03: ブランチ名が無い行（git の外）の 2 行目は、ブランチの項目ごと省く（「—」を出さない）', async () => {
  const out = await render(listView([row({ key: 'here|', pipe: 'diagrams', branch: null, stage: '設計' })]));
  const sub = subOf(rowOf(out, 'here|'));
  assert.doesNotMatch(sub, /—/);
  assert.match(sub, /^diagrams\b[^—]*動いている[^—]*設計$/);
});

test('D0019-AC-04: 状態の言葉：確認待ち・動いている・待ち・終わった行は結果の言葉（結果が無ければ「終わった」）。クラスは is-waiting・is-running・is-idle・is-done（合格以外は is-failed）', async () => {
  const out = await render(
    listView([
      row({ key: 'here|a', state: 'waiting' }),
      row({ key: 'here|b', state: 'running' }),
      row({ key: 'here|c', state: 'idle' }),
      row({ key: 'here|d', state: 'done', result: '合格' }),
      row({ key: 'here|e', state: 'done', result: '不合格' }),
      row({ key: 'here|f', state: 'done', result: 'SOMETHING' }),
      row({ key: 'here|g', state: 'done', result: null }),
    ]),
  );
  const word = (k: string): string => subOf(rowOf(out, k));
  assert.match(word('here|a'), /確認待ち/);
  assert.match(word('here|b'), /動いている/);
  assert.match(word('here|c'), /待ち/);
  assert.doesNotMatch(word('here|c'), /確認待ち/);
  assert.match(word('here|d'), /合格/);
  assert.doesNotMatch(word('here|d'), /不合格/);
  assert.match(word('here|e'), /不合格/);
  assert.match(word('here|f'), /SOMETHING/);
  assert.match(word('here|g'), /終わった/);
  assert.match(rowOf(out, 'here|a'), /class="run-row [^"]*\bis-waiting\b/);
  assert.match(rowOf(out, 'here|b'), /class="run-row [^"]*\bis-running\b/);
  assert.match(rowOf(out, 'here|c'), /class="run-row [^"]*\bis-idle\b/);
  assert.match(rowOf(out, 'here|d'), /class="run-row [^"]*\bis-done\b/);
  assert.doesNotMatch(rowOf(out, 'here|d'), /is-failed/);
  for (const k of ['here|e', 'here|f']) assert.match(rowOf(out, k), /class="run-row [^"]*\bis-failed\b/, k);
});

test('D0019-AC-57: 行は <button type="button"> で（Tab で移れ、Enter・Space で押せる）、中は span だけ。選んでいる行だけ aria-pressed="true"、data-run は key', async () => {
  const out = await render(listView(sampleRows(), { selected: 'wt.feat-x|' }));
  for (const r of rowsOf(out)) {
    const button = /<button type="button"[^>]*class="run-row[^"]*"[^>]*>([\s\S]*)<\/button>/.exec(r) ?? /<button[^>]*>([\s\S]*)<\/button>/.exec(r);
    assert.ok(button, '行の中に button がある');
    assert.doesNotMatch(button[1]!.replace(/<\/?span\b[^>]*>/g, ''), /<[a-z]/i, '中に span 以外のタグが無い');
    assert.match(r, /<button type="button"/);
  }
  assert.match(rowOf(out, 'wt.feat-x|'), /aria-pressed="true"/);
  for (const r of rowsOf(out)) if (!r.includes('data-run="wt.feat-x|"')) assert.match(r, /aria-pressed="false"/);
  assert.equal(count(out, /aria-pressed="true"/g), 1);
  assert.equal(count(out, /data-run="/g), sampleRows().length);
});

test('D0019-AC-09: 選びを変えても行の順は同じ（選びで並びが動かない）', async () => {
  const keys = (out: string) => rowsOf(out).map((r) => /data-run="([^"]*)"/.exec(r)![1]);
  const a = await render(listView(sampleRows(), { selected: 'here|' }));
  const b = await render(listView(sampleRows(), { selected: 'here|survey' }));
  assert.deepEqual(keys(a), keys(b));
  assert.deepEqual([...keys(a)].sort(), sampleRows().map((r) => r.key).sort());
});

// ---- AC-08・AC-15：前の実行・別の worktree の印 ----

test('D0019-AC-08: 「前の実行」の印は archive の行の 2 行目にだけ付く', async () => {
  const out = await render(listView(sampleRows()));
  const prevKey = 'here|archive/20261016-090000';
  assert.match(subOf(rowOf(out, prevKey)), /前の実行/);
  assert.match(subOf(rowOf(out, prevKey)), /合格/);
  for (const r of rowsOf(out)) if (!r.includes(prevKey)) assert.doesNotMatch(subOf(r), /前の実行/);
  assert.equal(count(out, /前の実行/g), 1);
});

test('D0019-AC-15: 「別の worktree」の印は別の worktree の行（other）の 2 行目にだけ付き、行に is-other が付く。いまの work_dir の行には付かない（ブランチ名は付く）', async () => {
  const out = await render(listView(sampleRows()));
  for (const key of ['wt.feat-x|', 'wt.fix-login|']) {
    assert.match(subOf(rowOf(out, key)), /別の worktree/);
    assert.match(rowOf(out, key), /class="run-row [^"]*\bis-other\b/);
  }
  assert.equal(count(out, /別の worktree/g), 2);
  assert.equal(count(out, /is-other/g), 2);
  const here = rowOf(out, 'here|');
  assert.doesNotMatch(here, /is-other|別の worktree/);
  assert.match(subOf(here), /main/, 'いまの work_dir の行にもブランチ名が出る');
});

// ---- AC-12・AC-14・AC-66：確認待ちの目立たせ方と経過 ----

test('D0019-AC-12: 確認待ちの行にだけ、is-waiting・「確認待ち」の文字・待ち時間（data-elapsed＝基準の秒）が付く', async () => {
  const out = await render(listView(sampleRows()));
  const waiting = rowOf(out, 'here|');
  assert.match(waiting, /\bis-waiting\b/);
  assert.match(subOf(waiting), /確認待ち/);
  assert.match(rightOf(waiting), /待ち <span class="elapsed" data-elapsed="42">0:42<\/span>/);
  assert.match(rightOf(rowOf(out, 'wt.feat-x|')), /data-elapsed="7">0:07</);
  assert.equal(count(out, /is-waiting/g), 2);
});

test('D0019-AC-12: 基準の秒は切り捨て（42.9 → 42）。1 時間を超える待ちは h:mm:ss', async () => {
  const out = await render(listView([row({ key: 'here|a', state: 'waiting', waitingSec: 42.9 }), row({ key: 'here|b', state: 'waiting', waitingSec: 3725 })]));
  assert.match(rightOf(rowOf(out, 'here|a')), /data-elapsed="42">0:42</);
  assert.match(rightOf(rowOf(out, 'here|b')), /data-elapsed="3725">1:02:05</);
});

test('D0019-AC-12: since が読めない古い記録（waitingSec が null）では待ち時間を出さず、印（is-waiting）と「確認待ち」の文字だけ付く', async () => {
  const out = await render(listView([row({ key: 'here|', state: 'waiting', waitingSec: null }), row({ key: 'here|x' })]));
  const r = rowOf(out, 'here|');
  assert.match(r, /is-waiting/);
  assert.match(subOf(r), /確認待ち/);
  assert.doesNotMatch(r, /data-elapsed/);
  assert.doesNotMatch(rightOf(r), /待ち /);
});

test('D0019-AC-14: 動いている行・待ちの行・終わった行には、確認待ちの印も点滅も待ち時間も付かない（waitingSec が入っていても）', async () => {
  const out = await render(
    listView([
      row({ key: 'here|a', state: 'running', waitingSec: 5 }),
      row({ key: 'here|b', state: 'idle', waitingSec: 5 }),
      row({ key: 'here|c', state: 'done', result: '合格', waitingSec: 5 }),
      row({ key: 'here|d', state: 'done', result: '不合格', previous: true }),
    ]),
  );
  // 状態のタブの「確認待ち」は 0 件でもいつも出る（AC-43・AC-56）ので、見るのは一覧の行の中だけ
  assert.doesNotMatch(out, /is-waiting/);
  assert.equal(rowsOf(out).length, 4);
  for (const r of rowsOf(out)) assert.doesNotMatch(plain(r), /確認待ち/);
  for (const r of rowsOf(out)) assert.doesNotMatch(rightOf(r), /待ち /);
});

test('D0019-AC-66: 動いている行は経過を data-elapsed（基準の秒）で出し、終わった行は固定の文字だけ（data-elapsed なし）', async () => {
  const out = await render(listView(sampleRows()));
  assert.match(rightOf(rowOf(out, 'here|diagrams')), /<span class="elapsed" data-elapsed="125">2:05<\/span>/);
  assert.match(rightOf(rowOf(out, 'wt.fix-login|')), /<span class="elapsed" data-elapsed="61">1:01<\/span>/);
  const done = rowOf(out, 'here|survey');
  assert.doesNotMatch(done, /data-elapsed/);
  assert.match(rightOf(done), /7:00/);
  assert.match(rightOf(rowOf(out, 'here|archive/20261016-090000')), /15:00/);
  // data-elapsed を持つのは、確認待ちの 2 行と、動いている 2 行だけ
  assert.equal(count(out, /data-elapsed=/g), 4);
});

test('D0019-AC-66: started_at が読めない（elapsed が null）行は、経過を出さない（data-elapsed も経過の要素も無い）', async () => {
  const out = await render(listView([row({ key: 'here|a', state: 'running', elapsed: null }), row({ key: 'here|b', state: 'done', result: '合格', elapsed: null }), row({ key: 'here|c', state: 'idle', elapsed: null })]));
  assert.doesNotMatch(out, /data-elapsed/);
  assert.doesNotMatch(out, /class="elapsed"/);
});

// ---- AC-10・AC-19：省いた数 ----

test('D0019-AC-10: 省いた archive があれば「古い実行を N 件、省いています」が場所の名前つきで出る。無ければ出ない', async () => {
  const withOmitted = await render(listView(sampleRows(), { omitted: [{ place: null, count: 2 }, { place: 'feat/x', count: 4 }] }));
  assert.match(withOmitted, /古い実行を 2 件、省いています/);
  assert.match(withOmitted, /<p class="run-omitted"><span>feat\/x：<\/span>古い実行を 4 件、省いています<\/p>/);
  assert.equal(count(withOmitted, /class="run-omitted"/g), 2);
  const none = await render(listView(sampleRows(), { omitted: [{ place: null, count: 0 }] }));
  assert.doesNotMatch(none, /省いています|run-omitted/);
  assert.doesNotMatch(await render(listView(sampleRows())), /省いています|run-omitted/);
});

test('D0019-AC-19: 別の worktree を省いたときは「別の worktree を N 個、省いています」が出る。0 なら出ない', async () => {
  const out = await render(listView(sampleRows(), { omittedWorktrees: 3 }));
  assert.match(out, /<p class="run-omitted">別の worktree を 3 個、省いています<\/p>/);
  assert.doesNotMatch(await render(listView(sampleRows(), { omittedWorktrees: 0 })), /別の worktree を \d/);
});

// ---- AC-28：同じ記録なら同じ HTML ----

test('D0019-AC-28: 同じ入力は同じ HTML（時計を読まない）', async () => {
  const a = await render(listView(sampleRows(), { omittedWorktrees: 1, omitted: [{ place: null, count: 1 }] }));
  const b = await render(listView(sampleRows(), { omittedWorktrees: 1, omitted: [{ place: null, count: 1 }] }));
  assert.equal(a, b);
  assert.equal(body(listView(sampleRows())), body(listView(sampleRows())));
});

// ---- AC-13：動き ----

test('D0019-AC-13: 点滅の CSS（animation・@keyframes run-attention）は prefers-reduced-motion: no-preference の中だけにある', async () => {
  const { RUN_LIST_STYLE } = await html();
  assert.deepEqual(motionOutsideNoPreference(RUN_LIST_STYLE), []);
  assert.deepEqual(keyframesInNoPreference(RUN_LIST_STYLE), ['run-attention']);
  const inside = parseCss(RUN_LIST_STYLE).filter((r) => r.media !== null && /no-preference/.test(r.media) && !r.keyframes);
  assert.ok(inside.some((r) => /is-waiting/.test(r.selector) && /animation\s*:[^;]*run-attention[^;]*2\.4s/.test(r.body)), '確認待ちの行が 2.4 秒周期で点滅する');
});

test('D0019-AC-13: 動きの周期は 1 秒に 3 回以下（周期 2.4 秒＝約 0.42 Hz）', async () => {
  const { RUN_LIST_STYLE } = await html();
  const m = /animation\s*:[^;]*?run-attention\s+([\d.]+)s/.exec(RUN_LIST_STYLE) ?? /animation\s*:\s*([\d.]+)s[^;]*run-attention/.exec(RUN_LIST_STYLE);
  assert.ok(m, 'run-attention の周期が読める');
  assert.ok(1 / Number(m[1]) <= 3, `${m[1]} 秒周期`);
});

test('D0019-AC-38: 点滅（@keyframes run-attention）は枠だけを動かし、文字の濃さ（opacity・color）は動かさない', async () => {
  const { RUN_LIST_STYLE } = await html();
  const frames = parseCss(RUN_LIST_STYLE).filter((r) => r.keyframes && /run-attention/.test(r.selector));
  assert.ok(frames.length === 1, '@keyframes run-attention が 1 つある');
  const keyframeBody = frames[0].body;
  assert.ok(!/\bopacity\s*:/.test(keyframeBody), `opacity を動かしている: ${keyframeBody.trim()}`);
  assert.ok(!/(^|[\s;{])color\s*:/.test(keyframeBody), `文字の color を動かしている: ${keyframeBody.trim()}`);
  assert.ok(/border-color|box-shadow|outline/.test(keyframeBody), '枠（border-color・box-shadow・outline）を動かしている');
});

test('D0019-AC-13: 動きを減らす設定（reduce）の中に、時間の要素や行を隠す規則が無い', async () => {
  const { RUN_LIST_STYLE } = await html();
  assert.deepEqual(hidingInReduce(RUN_LIST_STYLE), []);
});

test('D0019-AC-13: 検査そのものが違反を見つける（外の animation・reduce の中の animation・外の @keyframes）', () => {
  assert.equal(motionOutsideNoPreference('.run-row.is-waiting { animation: run-attention 2.4s infinite; }').length, 1);
  assert.equal(motionOutsideNoPreference('@keyframes run-attention { 50% { opacity: 0.55; } }').length, 1);
  assert.equal(motionOutsideNoPreference('@media (prefers-reduced-motion: reduce) { .a { animation: run-attention 1s; } }').length, 1);
  assert.deepEqual(
    motionOutsideNoPreference('@media (prefers-reduced-motion: no-preference) { .run-row.is-waiting { animation: run-attention 2.4s infinite; } @keyframes run-attention { 50% { opacity: 0.55; } } }'),
    [],
  );
  assert.equal(hidingInReduce('@media (prefers-reduced-motion: reduce) { .run-right .elapsed { display: none; } }').length, 1);
});

test('D0019-AC-12: 状態は動きに頼らない：確認待ちの行の黄の枠（2px）は、@media の外の静的な規則で決まる', async () => {
  const { RUN_LIST_STYLE } = await html();
  const rules = parseCss(RUN_LIST_STYLE).filter((r) => r.media === null && !r.keyframes);
  const border = rules.find((r) => /^\.run-row\.is-waiting$/.test(r.selector.trim()));
  assert.ok(border, '.run-row.is-waiting の静的な規則がある');
  assert.match(border.body, /border\s*:\s*2px[^;]*var\(--vscode-charts-yellow/);
});

test('D0019-AC-12: 選んだ行は aria-pressed の静的な規則で分かる（背景と枠）。キーボードの焦点（focus-visible）の枠もある', async () => {
  const { RUN_LIST_STYLE } = await html();
  const rules = parseCss(RUN_LIST_STYLE).filter((r) => r.media === null && !r.keyframes);
  assert.ok(rules.some((r) => /aria-pressed="true"/.test(r.selector) && /list-activeSelectionBackground/.test(r.body) && /focusBorder/.test(r.body)));
  assert.ok(rules.some((r) => /:focus-visible/.test(r.selector) && /focusBorder/.test(r.body)));
});

test('D0019-AC-38: 触れる大きさ：行は最小の高さ 44px、状態のタブは 28px 以上。ID は等幅の文字', async () => {
  const { RUN_LIST_STYLE } = await html();
  const rules = parseCss(RUN_LIST_STYLE).filter((r) => r.media === null && !r.keyframes);
  const heightOf = (re: RegExp): number[] =>
    rules.filter((r) => re.test(r.selector)).map((r) => Number(/min-height\s*:\s*(\d+)px/.exec(r.body)?.[1] ?? 0));
  assert.ok(Math.max(0, ...heightOf(/(^|[\s,])\.run-row\b/)) >= 44, '行は最小の高さ 44px');
  assert.ok(Math.max(0, ...heightOf(/run-tabs|data-list-tab|\[role="tab"\]/)) >= 28, '状態のタブは 28px 以上');
  assert.ok(rules.some((r) => /\.run-id\b/.test(r.selector) && /monospace|editor-font-family/.test(r.body)), 'ID は等幅');
});

test('D0019-AC-67: 一覧の CSS が持つ max-width の @media は、パネルの 2 つの区切り（800px・1100px）だけ（1回目の 640px は無い）', async () => {
  const { RUN_LIST_STYLE } = await html();
  const widths = parseCss(RUN_LIST_STYLE)
    .filter((r) => r.media !== null && /max-width/.test(r.media))
    .map((r) => /max-width\s*:\s*(\d+)px/.exec(r.media!)?.[1]);
  for (const w of widths) assert.ok(w === '800' || w === '1100', `max-width: ${String(w)}px の区切りがある`);
});

// ---- AC-29：外から来た文字・CSP ----

const EVIL = '<script>alert(1)</script>"&\'';

const EVIL_ROWS: [string, Partial<RunRow>][] = [
  ['セッション名', { session: EVIL }],
  ['パイプ名', { pipe: EVIL }],
  ['今の段', { stage: EVIL }],
  ['結果', { state: 'done', result: EVIL }],
  ['ブランチ名', { branch: EVIL }],
  ['セッション ID', { sessionId: EVIL }],
  ['費用・時刻の文字', { costText: EVIL, updatedText: EVIL, updatedDate: EVIL }],
  ['key（data-run）', { key: `here|${EVIL}` }],
];

for (const [label, over] of EVIL_ROWS) {
  test(`D0019-AC-29: 外から来た文字（${label}）の <script>・"・& は生で出ず、エスケープされる`, async () => {
    const out = await render(listView([row(over), row({ key: 'here|ok' })]));
    assert.ok(!out.includes('<script>alert'), '生の <script> が入っていない');
    assert.ok(!out.includes('alert(1)</script>'));
    assert.ok(!/<script/i.test(out));
    assert.ok(out.includes('&lt;script&gt;alert(1)&lt;/script&gt;'), 'エスケープされた形で出ている');
    assert.doesNotMatch(out, /\sstyle\s*=/i);
    assert.doesNotMatch(out, /<[a-z][^>]*\son[a-z]+\s*=/i, 'イベント属性が増えていない');
  });
}

test('D0019-AC-29: 絞り込みの印（data-name・data-sid・data-branch）の属性にも、外から来た文字がエスケープされて入る（" で属性が切れない）', async () => {
  const out = await render(listView([row({ key: 'here|', session: EVIL, sessionId: EVIL, branch: EVIL })]));
  const r = rowOf(out, 'here|');
  assert.ok(r.includes(`data-name="${escapeHtml(EVIL)}"`));
  assert.ok(r.includes(`data-sid="${escapeHtml(EVIL)}"`));
  assert.ok(r.includes(`data-branch="${escapeHtml(EVIL)}"`));
  assert.doesNotMatch(r, /data-name="[^"]*"[^>]*"[^>]*alert/);
});

test('D0019-AC-29: 省いた場所の名前もエスケープされる', async () => {
  const out = await render(listView(sampleRows(), { omitted: [{ place: EVIL, count: 3 }] }));
  assert.ok(!out.includes('<script>alert'));
  assert.ok(out.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
});

test('D0019-AC-29: 一覧に style 属性・on…= のイベント属性・外部の読み込みが無く、色の直書きも無い（HTML と CSS）', async () => {
  const { RUN_LIST_STYLE } = await html();
  const out = await render(listView(sampleRows(), { omitted: [{ place: 'feat/x', count: 1 }], omittedWorktrees: 2 }));
  assert.doesNotMatch(out, /\sstyle\s*=/i);
  assert.doesNotMatch(out, /<[a-z][^>]*\son[a-z]+\s*=/i);
  for (const text of [out, RUN_LIST_STYLE]) {
    assert.doesNotMatch(text, /(src|href)\s*=\s*["']?https?:/i);
    assert.doesNotMatch(text, /url\(\s*["']?https?:/i);
    assert.doesNotMatch(text, /@import/i);
    for (const re of [/#[0-9a-fA-F]{3,8}\b/, /rgba?\(/, /hsla?\(/]) assert.doesNotMatch(text, re);
  }
  assert.match(RUN_LIST_STYLE, /var\(--vscode-/);
  assert.doesNotMatch(RUN_LIST_STYLE, /(^|[\s,}])#[A-Za-z_-]/, 'id セレクタを使わない（クラスだけ）');
});
