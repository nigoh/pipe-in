// 理由の欄の判定の節（D0062 の AC-10・AC-16 の下地）：検証ごとの回・合否・要約・直す点が古い順に入る。外から来た文字は escapeHtml を通る。
// 赤の理由は「まだ描いていない」：data-reasons-for="check:<段>" の欄が無い。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderReasons } from './reasonsHtml.ts';
import { checkEntry, checkView, runEntry, stageDef } from '../test/checkFixtures.ts';

const stages = [stageDef({ name: 'draw' }), stageDef({ name: 'verify', check: { on_fail: 'draw', max_retries: 2 } })];

/** 欄 <section … data-reasons-for="id">…</section>。無ければ null。 */
const sectionOf = (html: string, id: string): string | null =>
  new RegExp(`<section\\b[^>]*data-reasons-for="${id}"[^>]*>[\\s\\S]*?</section>`).exec(html)?.[0] ?? null;

test('D0062-AC-10: 判定の節の欄に検証ごとの回・合否・要約・直す点が古い順に入る', () => {
  const view = checkView(
    [
      runEntry('draw', 1),
      runEntry('verify', 2),
      checkEntry({ stage: 'verify', status: 'fail', attempt: 1, summary: '図が足りない', problems: ['矢印が逆', '凡例が無い'] }),
      runEntry('draw', 3),
      runEntry('verify', 4),
      checkEntry({ stage: 'verify', status: 'pass', attempt: 2, summary: 'よい', problems: [] }),
    ],
    { pipe: 'p', stages },
  );
  const section = sectionOf(renderReasons(view), 'check:verify');
  assert.ok(section !== null, 'data-reasons-for="check:verify" の欄がある');
  assert.match(section, /\bhidden\b/, '選ぶまでは hidden');
  const at = (text: string): number => {
    const i = section.indexOf(text);
    assert.ok(i >= 0, `欄に「${text}」がある`);
    return i;
  };
  const order = [at('検証 1 回目：不合格'), at('図が足りない'), at('矢印が逆'), at('凡例が無い'), at('検証 2 回目：合格'), at('よい')];
  assert.deepEqual([...order].sort((a, b) => a - b), order, '古い順（1 回目が先）に並ぶ');
  const list = section.indexOf('<ul');
  assert.ok(list >= 0 && list < order[2]!, '直す点は箇条書き（<ul>）の中');
});

test('D0062-AC-10: 直す点が無い合格の回は、直す点の箇条書きを出さない', () => {
  const view = checkView([runEntry('verify', 1), checkEntry({ stage: 'verify', status: 'pass', attempt: 1, summary: 'よい', problems: [] })], { pipe: 'p', stages });
  const section = sectionOf(renderReasons(view), 'check:verify');
  assert.ok(section !== null);
  assert.match(section, /検証 1 回目：合格/);
  assert.doesNotMatch(section, /<ul\b[^>]*>\s*<\/ul>/, '空の箇条書きは出さない');
});

test('D0062-AC-10: 検証がまだ無い判定の節には欄を出さない（ほかの欄も無ければ空の文字）', () => {
  const view = checkView([runEntry('draw', 1)], { pipe: 'p', stages });
  assert.equal(sectionOf(renderReasons(view), 'check:verify'), null);
});

test('D0062-AC-10: summary と problems の外から来た文字は escapeHtml を通る', () => {
  const evil = '<script>alert(1)</script>';
  const view = checkView(
    [runEntry('verify', 1), checkEntry({ stage: 'verify', status: 'fail', attempt: 1, summary: evil, problems: [evil, '<img src=x onerror=alert(2)>', 'a & "b"'] })],
    { pipe: 'p', stages },
  );
  const html = renderReasons(view);
  const section = sectionOf(html, 'check:verify');
  assert.ok(section !== null, 'data-reasons-for="check:verify" の欄がある');
  assert.ok(!html.includes('<script>'), '生の <script> が出ている');
  assert.ok(!html.includes('<img'), '生の <img> が出ている');
  assert.ok(section.includes('&lt;script&gt;alert(1)&lt;/script&gt;'), '文字参照になっている');
  assert.ok(section.includes('&lt;img src=x onerror=alert(2)&gt;'));
  assert.ok(section.includes('a &amp; &quot;b&quot;'));
});

test('D0062-AC-16: 開発フロー・判定の無い記録の理由の欄に check の欄は出ない。今のまま通る。守る', () => {
  const plain = [stageDef({ name: 'draw' }), stageDef({ name: 'verify' })];
  const view = checkView([runEntry('verify', 1), checkEntry({ stage: 'verify', status: 'fail', attempt: 1 })], { pipe: 'p', stages: plain });
  assert.doesNotMatch(renderReasons(view), /data-reasons-for="check:/);
});
