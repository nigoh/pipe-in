// 作業台の「流す」の節の中身（D0078。view/runHtml.ts）。AC-46〜48・51 の支え（画面の確認は確認用ページで、手順は 03_red_tests.md）。
// 文字は escapeHtml を通り、style 属性は書かない。同じ理由を2か所に出さない（呼ぶ側 refreshRun の決まりを、渡し方の見本で確かめる）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runInfoHtml } from './runHtml.ts';
import type { RunView } from './runHtml.ts';

const CMD = { command: '/usr/local/bin/pipe-in', args: ['--pipe=/work/app/.pipe-in/pipes/pipe-in-p', '--project=/work/app', '--text=使い方を直して'], placeholder: false };

function view(over: Partial<RunView> = {}): RunView {
  return { command: CMD, commandNote: null, reason: null, count: null, ...over };
}

const occurrences = (text: string, part: string): number => text.split(part).length - 1;

test('D0078-AC-39: 起こすコマンドの形：実行ファイルが出て、引数は1つずつ <li><code> で出る', () => {
  const html = runInfoHtml(view());
  assert.ok(html.includes('/usr/local/bin/pipe-in'));
  for (const arg of CMD.args) assert.ok(html.includes(`<li><code>${arg}</code></li>`), arg);
  assert.equal(occurrences(html, '<li>'), 3);
});

test('D0078-AC-40: 引数の順は渡した順（--pipe=、--project=、--text=）', () => {
  const html = runInfoHtml(view());
  const at = CMD.args.map((a) => html.indexOf(a));
  assert.ok(at.every((i) => i >= 0));
  assert.deepEqual([...at].sort((a, b) => a - b), at);
});

test('D0078-AC-42: 引数が2つなら <li> も2つ（--text を足さない）', () => {
  const html = runInfoHtml(view({ command: { ...CMD, args: CMD.args.slice(0, 2) } }));
  assert.equal(occurrences(html, '<li>'), 2);
  assert.ok(!html.includes('--text'));
});

test('D0078-AC-39: 仮の文字（placeholder）の引数も出る。< > は文字として出る', () => {
  const html = runInfoHtml(view({ command: { ...CMD, args: [...CMD.args.slice(0, 2), '--text=<依頼メモ>'], placeholder: true } }));
  assert.ok(html.includes('--text=&lt;依頼メモ&gt;'));
  assert.ok(!html.includes('<依頼メモ>'));
});

// ---- 理由（AC-41・46・51） ----

test('D0078-AC-41: reason があれば <p class="run-reason" role="status"> に1回出る', () => {
  const html = runInfoHtml(view({ reason: '依頼メモを書いてください' }));
  assert.match(html, /<p class="run-reason" role="status">依頼メモを書いてください<\/p>/);
  assert.equal(occurrences(html, '依頼メモを書いてください'), 1);
});

test('D0078-AC-51: reason が null なら <p> ごと出さない（run-reason の語も出ない）', () => {
  const html = runInfoHtml(view({ reason: null }));
  assert.ok(!html.includes('run-reason'));
  assert.ok(!html.includes('role="status"'));
});

test('D0078-AC-46: notSaved では、理由の行に「先に保存してください」が1回、コマンドの形の欄に「保存すると、起こすコマンドの形が見えます」が出る（同じ文が2か所に出ない）', () => {
  const html = runInfoHtml({
    command: null,
    commandNote: '保存すると、起こすコマンドの形が見えます',
    reason: '先に保存してください（まだ一度も保存していないパイプは流せません）',
    count: null,
  });
  assert.equal(occurrences(html, '先に保存してください'), 1);
  assert.equal(occurrences(html, '保存すると、起こすコマンドの形が見えます'), 1);
  assert.match(html, /<p class="run-reason" role="status">[^<]*先に保存してください/);
  assert.ok(!html.includes('<li>'), 'コマンドの引数は出ない');
});

test('D0078-AC-51: noExecutable では、理由がコマンドの形の欄（commandNote）にだけ出て、理由の行（run-reason）は出ない', () => {
  const reason = '`pipe-in` が見つかりません。設定 `pipe-in.command` に絶対パスを書いてください';
  const html = runInfoHtml({ command: null, commandNote: reason, reason: null, count: null });
  assert.equal(occurrences(html, '見つかりません'), 1);
  assert.ok(html.includes('pipe-in.command'));
  assert.ok(!html.includes('run-reason'));
});

test('D0078-AC-51: 実行ファイルが決まらず、ほかの理由（信頼など）が先に当たったときは、commandNote と reason に別々の文が出る', () => {
  const html = runInfoHtml({ command: null, commandNote: '`pipe-in` が見つかりません', reason: '信頼していないワークスペースでは流せません', count: null });
  assert.equal(occurrences(html, '見つかりません'), 1);
  assert.equal(occurrences(html, '信頼していないワークスペース'), 1);
  assert.match(html, /<p class="run-reason" role="status">信頼していない/);
});

test('D0078-AC-46: command も commandNote も null なら、コマンドの形の欄は空のまま（<li> が無く、例外にならない）', () => {
  const html = runInfoHtml({ command: null, commandNote: null, reason: '依頼メモを書いてください', count: null });
  assert.ok(!html.includes('<li>'));
  assert.ok(html.includes('依頼メモを書いてください'));
});

// ---- 文字数（AC-47） ----

test('D0078-AC-47: count があるときだけ「長さ / 上限」を出す。上限ちょうどは over にしない', () => {
  const html = runInfoHtml(view({ count: { length: 4000, limit: 4000 } }));
  assert.ok(html.includes('4000 / 4000'));
  assert.match(html, /class="run-count"/);
  assert.doesNotMatch(html, /run-count over/);
  assert.ok(!html.includes('超えています'));
});

test('D0078-AC-47: 上限を超えたら class="run-count over" と「超えています」が出る', () => {
  const html = runInfoHtml(view({ count: { length: 4001, limit: 4000 } }));
  assert.ok(html.includes('4001 / 4000'));
  assert.match(html, /class="run-count over"/);
  assert.ok(html.includes('超えています'));
});

test('D0078-AC-47: count が null なら文字数の行は出ない（none のとき）', () => {
  const html = runInfoHtml(view({ count: null }));
  assert.ok(!html.includes('run-count'));
  assert.doesNotMatch(html, /\d+ \/ \d+/);
});

test('D0078-AC-47: 途中の数も出る（1234 / 4000）', () => {
  assert.ok(runInfoHtml(view({ count: { length: 1234, limit: 4000 } })).includes('1234 / 4000'));
});

// ---- 外から来た文字（AC-48） ----

const HOSTILE = '<script>alert(1)</script> --yes';

test('D0078-AC-48: 依頼メモ由来の引数に <script> があっても、文字として出る（script 要素にならず、alert が動く形にならない）', () => {
  const html = runInfoHtml(view({ command: { ...CMD, args: [...CMD.args.slice(0, 2), `--text=${HOSTILE}`] } }));
  assert.ok(!html.includes('<script'));
  assert.ok(!html.includes('</script'));
  assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt; --yes'));
});

test('D0078-AC-48: 実行ファイル・理由・commandNote・引数の " \' & < > はすべて文字参照にする', () => {
  const nasty = `"><img src=x onerror=alert(1)> & 'q'`;
  const html = runInfoHtml({
    command: { command: `/opt/${nasty}/pipe-in`, args: [`--pipe=${nasty}`, `--project=${nasty}`], placeholder: false },
    commandNote: nasty,
    reason: nasty,
    count: null,
  });
  assert.ok(!html.includes('<img'));
  assert.ok(!html.includes('onerror=alert(1)>'));
  assert.ok(html.includes('&quot;&gt;&lt;img src=x onerror=alert(1)&gt; &amp; &apos;q&apos;'));
});

test('D0078-AC-48: どの入力でも style 属性を書かない（CSP が捨てる）', () => {
  const views: RunView[] = [
    view(),
    view({ reason: '理由' }),
    view({ count: { length: 5000, limit: 4000 } }),
    { command: null, commandNote: '保存すると、起こすコマンドの形が見えます', reason: '先に保存してください', count: null },
  ];
  for (const v of views) assert.doesNotMatch(runInfoHtml(v), /\sstyle\s*=/i);
});

test('D0078-AC-48: runInfoHtml は呼ぶたびに同じ結果（時計・乱数に頼らない）', () => {
  const v = view({ reason: '理由', count: { length: 10, limit: 4000 } });
  assert.equal(runInfoHtml(v), runInfoHtml(v));
});
