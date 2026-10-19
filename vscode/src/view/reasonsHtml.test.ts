// 理由の欄の HTML（D0016）。部品 reasonsHtml.ts を直接ではなく、パネルの本体（renderViewBody）と
// パネル全体（renderPanelHtml）の出力を通して確かめる。欄が警告の下・出力の上に入ることまで見る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { escapeHtml, renderPanelHtml, renderViewBody } from './panelHtml.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { snapshot, stageRunEntry, stateJson } from '../test/fixtures.ts';
import {
  failVerdict,
  implementAndTest,
  oneSendBackView,
  passVerdict,
  reviseEntry,
  showcaseView,
  unresolvedView,
  viewOf,
} from '../test/reasonFixtures.ts';

/** data-reasons-for が id の欄（<section> の中身まで）。無ければ null。 */
function section(html: string, id: string): string | null {
  const m = new RegExp(`<section[^>]*data-reasons-for="${id}"[^>]*>([\\s\\S]*?)</section>`).exec(html);
  return m === null ? null : m[0];
}
function need(html: string, id: string): string {
  const s = section(html, id);
  assert.ok(s !== null, `欄 ${id} が無い`);
  return s;
}

// 検査そのもの
const hasRawScript = (html: string): boolean => /<script/i.test(html);
const hasStyleAttr = (html: string): boolean => /\sstyle\s*=/i.test(html);
const hasExternalLoad = (html: string): boolean => /https?:\/\//i.test(html);
const hasInlineHandler = (html: string): boolean => /\son[a-z]+\s*=/i.test(html);

const DETAIL = '出力の先頭に BOM が無く、Excel で開くと文字化けする';

test('D0016-AC-10: 実装の欄に、回数・戻り先の段の名前・要約・criterion・detail が入る', () => {
  const html = renderViewBody(showcaseView());
  const s = need(html, 'implement');
  assert.match(s, /理由：実装/);
  assert.match(s, /検証 1 回目で不合格 → 実装へ戻した/);
  assert.match(s, /AC-02 が不合格（BOM が無い）/);
  assert.match(s, /AC-02/);
  assert.ok(s.includes(DETAIL));
});

test('D0016-AC-10: 判定の欄にも同じ差し戻しの理由が入る', () => {
  const s = need(renderViewBody(showcaseView()), 'verdict');
  assert.match(s, /理由：判定/);
  assert.match(s, /検証 1 回目で不合格 → 実装へ戻した/);
  assert.ok(s.includes(DETAIL));
});

test('D0016-AC-10: 確認の欄に、段の名前・回数・feedback が入る', () => {
  const s = need(renderViewBody(showcaseView()), 'review:requirements');
  assert.match(s, /理由：確認（要件定義）/);
  assert.ok(s.includes("1 回目の修正の依頼：AC-02 を『文字コード』と『列の順』に分けて"));
});

test('D0016-AC-10: 不合格が2回なら、回数の順に2件並ぶ', () => {
  const view = viewOf(
    stateJson({
      runs: [
        ...implementAndTest(1),
        failVerdict({ attempt: 1, summary: '一つ目', failures: [{ criterion: 'AC-01', detail: 'a' }] }),
        ...implementAndTest(2),
        failVerdict({ attempt: 2, summary: '二つ目', failures: [{ criterion: 'AC-02', detail: 'b' }, { criterion: 'AC-03', detail: 'c' }] }),
        ...implementAndTest(3),
        passVerdict(3),
      ],
    }),
  );
  const s = need(renderViewBody(view), 'implement');
  const first = s.indexOf('検証 1 回目で不合格');
  const second = s.indexOf('検証 2 回目で不合格');
  assert.ok(first >= 0 && second > first, '1回目、2回目の順');
  assert.ok(s.indexOf('一つ目') < second && s.indexOf('二つ目') > second);
  for (const c of ['AC-01', 'AC-02', 'AC-03']) assert.ok(s.includes(c), c);
  assert.doesNotMatch(s, /検証 3 回目/);
});

test('D0016-AC-10: 同じ段の修正の依頼が2回なら、1 回目・2 回目の順に並ぶ', () => {
  const view = viewOf(stateJson({ runs: [reviseEntry('design', 'まず'), reviseEntry('design', 'つぎ')] }));
  const s = need(renderViewBody(view), 'review:design');
  assert.ok(s.indexOf('1 回目の修正の依頼：まず') >= 0);
  assert.ok(s.indexOf('2 回目の修正の依頼：つぎ') > s.indexOf('1 回目の修正の依頼：まず'));
});

test('D0016-AC-10: 差し戻されずに終わった不合格は「差し戻されていない」と出し、「実装へ戻した」とは出さない', () => {
  const s = need(renderViewBody(unresolvedView()), 'implement');
  assert.match(s, /検証 1 回目で不合格（差し戻されていない）/);
  assert.doesNotMatch(s, /実装へ戻した/);
});

test('D0016-AC-10: 選ぶ前は全部の欄が hidden で、警告の下・出力の上に入る', () => {
  const view = oneSendBackView({ summary: 's', failures: [{ criterion: 'AC-01', detail: 'd' }], feedback: 'f', warnings: ['注意書き'] });
  const html = renderViewBody(view);
  const tags = html.match(/<section[^>]*data-reasons-for="[^"]*"[^>]*>/g) ?? [];
  assert.equal(tags.length, 3, '実装・判定・確認（要件定義）');
  for (const tag of tags) assert.match(tag, /\shidden(\s|>|=)/, tag);
  const warn = html.indexOf('注意書き');
  const reasons = html.indexOf('data-reasons-for=');
  const output = html.indexOf('出力');
  assert.ok(warn >= 0 && warn < reasons, '警告の下');
  assert.ok(reasons >= 0 && reasons < output, '出力の上');
});

// ---- 外から来た文字はすべてエスケープする ----

const PAYLOAD = `<script>alert(1)</script>"&'`;
const FIELDS: [string, () => PipelineView][] = [
  ['criterion', () => oneSendBackView({ failures: [{ criterion: PAYLOAD, detail: 'd' }] })],
  ['detail', () => oneSendBackView({ failures: [{ criterion: 'AC-01', detail: PAYLOAD }] })],
  ['summary', () => oneSendBackView({ summary: PAYLOAD })],
  ['feedback', () => oneSendBackView({ feedback: PAYLOAD })],
];
for (const [field, make] of FIELDS) {
  test(`D0016-AC-11: ${field} に <script>・"・&・' を含めても、生のまま出ずエスケープされる`, () => {
    const html = renderViewBody(make());
    assert.ok(html.includes(escapeHtml(PAYLOAD)), `${field} がエスケープされて欄に入る`);
    assert.equal(hasRawScript(html), false, '生の <script が無い');
    assert.ok(!html.includes(PAYLOAD), '生の文字が残っていない');
    assert.ok(!html.includes('alert(1)</script>'));
  });
}

test('D0016-AC-11: パイプの段の表示名に タグを含めても、欄の見出しでエスケープされる', () => {
  const label = '<img src=x onerror=alert(1)>';
  const view = viewOf(
    stateJson({
      pipe: 'p',
      stages: [{ name: 'a', label, output: '01_a.md', review: true }],
      runs: [stageRunEntry({ stage: 'a', seq: 1 }), reviseEntry('a', '直して')],
    }),
  );
  const html = renderViewBody(view);
  assert.ok(html.includes('data-reasons-for="review:a"'), '欄が出る');
  assert.ok(html.includes(escapeHtml(label)));
  assert.doesNotMatch(html, /<img/i);
});

// 検査そのものが違反を見つけられる
test('D0016-AC-11: 生の <script を見つける検査は、違反のある HTML を見つけ、安全な HTML は通す', () => {
  assert.equal(hasRawScript('<p><script>alert(1)</script></p>'), true);
  assert.equal(hasRawScript('<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>'), false);
});
test('D0016-AC-12: style 属性・外部の読み込み・インラインのイベント属性を見つける検査は、違反を見つけ、安全な HTML は通す', () => {
  assert.equal(hasStyleAttr('<p style="color:red">x</p>'), true);
  assert.equal(hasStyleAttr('<g class="a" style = "x">'), true);
  assert.equal(hasStyleAttr('<p class="reason-detail">style</p>'), false);
  assert.equal(hasExternalLoad('<img src="https://example.com/a.png">'), true);
  assert.equal(hasExternalLoad('<link href="http://example.com/a.css">'), true);
  assert.equal(hasExternalLoad('<marker id="mk-pick">'), false);
  assert.equal(hasInlineHandler('<g onclick="x()">'), true);
  assert.equal(hasInlineHandler('<g class="node">'), false);
});

// ---- CSP とインライン ----

test('D0016-AC-12: 理由の欄を含むパネル全体に style 属性・外部の読み込み・インラインのイベント属性・色の直書きが無く、CSP は今のまま', () => {
  const view = oneSendBackView({ summary: '要約', failures: [{ criterion: 'AC-01', detail: '直す' }], feedback: '直して' });
  const html = renderPanelHtml(view, 'NONCE123');
  assert.ok(html.includes('data-reasons-for="implement"'), '理由の欄が出ている');
  assert.equal(hasStyleAttr(html), false);
  assert.equal(hasExternalLoad(html), false);
  assert.equal(hasInlineHandler(html), false);
  assert.doesNotMatch(html, /#[0-9a-fA-F]{3,8}\b/);
  assert.doesNotMatch(html, /rgba?\(/);
  assert.match(
    html,
    /<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-NONCE123'; script-src 'nonce-NONCE123';">/,
  );
});

test('D0016-AC-12: 選びのスクリプトは el.style を使わず、<script>・<style> は nonce つきの1つずつのまま', () => {
  const html = renderPanelHtml(showcaseView(), 'N0NCE');
  const script = /<script nonce="N0NCE">([\s\S]*?)<\/script>/.exec(html)![1];
  assert.doesNotMatch(script, /\.style\b/);
  assert.equal((html.match(/<script/g) ?? []).length, 1);
  assert.equal((html.match(/<style/g) ?? []).length, 1);
  assert.match(html, /<style nonce="N0NCE">/);
});

// ---- 履歴が無い・理由の文字が無い ----

test('D0016-AC-14: 履歴の無い記録では理由の欄を出さない（守り続ける検査）', () => {
  for (const view of [buildPipelineView(snapshot()), viewOf(stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }))]) {
    const html = renderViewBody(view);
    assert.doesNotMatch(html, /data-reasons-for/);
    assert.doesNotMatch(html, /理由/);
  }
});

test('D0016-AC-14: 理由の文字が空の不合格は「理由は記録されていません」を出す', () => {
  const view = oneSendBackView({ summary: '', failures: [] });
  const s = need(renderViewBody(view), 'implement');
  assert.match(s, /検証 1 回目で不合格 → 実装へ戻した/);
  assert.match(s, /理由は記録されていません/);
});

test('D0016-AC-14: feedback が無い・空の修正の依頼は「N 回目の修正の依頼」と「理由は記録されていません」を出す', () => {
  for (const feedback of [null, '']) {
    const view = viewOf(stateJson({ runs: [reviseEntry('requirements', feedback)] }));
    const s = need(renderViewBody(view), 'review:requirements');
    assert.match(s, /1 回目の修正の依頼/, String(feedback));
    assert.match(s, /理由は記録されていません/, String(feedback));
  }
});

test('D0016-AC-14: 理由の文字がある履歴には「理由は記録されていません」を出さない', () => {
  const html = renderViewBody(showcaseView());
  assert.ok(html.includes('data-reasons-for="implement"'), '欄が出ている');
  assert.doesNotMatch(html, /理由は記録されていません/);
});

// ---- 大きな入力 ----

test('D0016-AC-15: failures が100件・detail が1万文字でも HTML の組み立てが終わり、図の大きさ（viewBox）は変わらない', () => {
  const viewBox = (html: string): string => /<svg class="flow" viewBox="([^"]*)"/.exec(html)![1];
  const failures = Array.from({ length: 100 }, (_, i) => ({ criterion: `AC-${i}`, detail: 'あ'.repeat(10000) }));
  const base = renderViewBody(oneSendBackView({}));
  const big = renderViewBody(oneSendBackView({ failures }));
  assert.ok(big.includes('data-reasons-for="implement"'), '欄が出ている');
  assert.ok((big.match(/AC-99/g) ?? []).length >= 1, '100件目まで入っている');
  assert.ok(big.includes('あ'.repeat(10000)), '1万文字がそのまま入る');
  assert.equal(viewBox(big), viewBox(base));
});
