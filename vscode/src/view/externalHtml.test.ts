// 外で書き換わったときの帯の HTML（D0065）：外から来た文字は escapeHtml を通す。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderExternalBanner } from './externalHtml.ts';

const EVIL = '<script>alert(1)</script>';

test('D0065-AC-20: conflict の差分の target・text に <script> が来ても、生の <script が出ない（文字として出る）', () => {
  const html = renderExternalBanner({
    type: 'externalConflict',
    diff: [
      { kind: 'prompt', target: EVIL, text: EVIL },
      { kind: 'setting', target: 'a" onclick="x', text: `<img src=x onerror=alert(1)> & '` },
    ],
  });
  assert.doesNotMatch(html, /<script/i);
  assert.doesNotMatch(html, /<img/i);
  assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt;'), html);
  assert.doesNotMatch(html, /onclick="x/);
  assert.ok(html.includes('a&quot; onclick=&quot;x'), html);
});

test('D0065-AC-20: unreadable の reason に <script> が来ても、生の <script が出ない', () => {
  const html = renderExternalBanner({ type: 'externalUnreadable', reason: `pipe.toml を読めません：${EVIL}` });
  assert.doesNotMatch(html, /<script/i);
  assert.ok(html.includes('&lt;script&gt;'), html);
  assert.ok(html.includes('pipe.toml を読めません'));
});

test('D0065-AC-17: conflict の帯は「外の変更を読み込む」「自分の変更を残す」の 2 つのボタン（data-ext="load" / "keep"）と、差分の一覧を持つ', () => {
  const html = renderExternalBanner({ type: 'externalConflict', diff: [{ kind: 'prompt', target: 'survey', text: '新しい指示' }, { kind: 'layout', target: 'write', text: '位置' }] });
  assert.equal((html.match(/data-ext="load"/g) ?? []).length, 1);
  assert.equal((html.match(/data-ext="keep"/g) ?? []).length, 1);
  assert.ok(html.includes('外の変更を読み込む'));
  assert.ok(html.includes('自分の変更を残す'));
  assert.ok(html.includes('外で書き換わっています'));
  assert.ok(html.includes('survey') && html.includes('新しい指示'));
  assert.equal((html.match(/<li\b/g) ?? []).length, 2, '差分 1 件につき 1 行');
});

test('D0065-AC-17: unreadable の帯は理由だけで、ボタンはない', () => {
  const html = renderExternalBanner({ type: 'externalUnreadable', reason: 'pipe.toml が見つかりません' });
  assert.ok(html.includes('pipe.toml が見つかりません'));
  assert.doesNotMatch(html, /data-ext=/);
  assert.doesNotMatch(html, /<button/i);
});

test('D0065-AC-21: 帯の HTML に style 属性・外部の URL・インラインのイベント属性が無い', () => {
  for (const html of [
    renderExternalBanner({ type: 'externalConflict', diff: [{ kind: 'flow', target: 'a', text: 'つなぎ' }] }),
    renderExternalBanner({ type: 'externalUnreadable', reason: 'x' }),
  ]) {
    assert.doesNotMatch(html, /\sstyle=/);
    assert.doesNotMatch(html, /https?:\/\//);
    assert.doesNotMatch(html, /\son[a-z]+=/i);
  }
});
