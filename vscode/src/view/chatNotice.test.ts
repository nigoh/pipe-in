// D0077-AC-24（判断の部分）：確認待ちの黄の知らせの「答え方」は、記録の種類で変わる。
// 会話の道の記録（driver が pipe-chat）は「/pipe-in:pipe-run を流している会話で返す」と pipe-in-gen chat review。
// 端末の記録（driver なし）と開発用の記録（driver が pipe-dev）は今のまま（python -m pipe_in record review）。
// 赤の理由は「まだ直していない」：renderNotice が記録の種類を見ずに、いつも開発用の文を出す。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { emptyListFor, renderShell } from './shellHtml.ts';
import { waitingSnapshot } from '../test/chatFixtures.ts';
import type { ChatState } from '../test/chatFixtures.ts';

/** 黄の知らせ（class="notice" の要素）だけを取り出す */
function noticeOf(p: ChatState): string {
  const view = buildPipelineView(waitingSnapshot(p));
  const html = renderShell(view, emptyListFor(view));
  const start = html.indexOf('<div class="notice" role="status">');
  assert.ok(start >= 0, '確認待ちの知らせが出ている');
  const end = html.indexOf('</div>', start);
  return html.slice(start, end + 6);
}

test('D0077-AC-24: 会話の道の記録の知らせは、「/pipe-in:pipe-run を流している会話で返す」と pipe-in-gen chat review を出す', () => {
  const n = noticeOf({ pipe: 'cp' });
  assert.match(n, /\/pipe-in:pipe-run/);
  assert.match(n, /pipe-in-gen chat review --pipe cp approved/);
  assert.match(n, /revise --feedback/);
  assert.match(n, /quit/);
});

test('D0077-AC-24: 会話の道の記録の知らせは、python -m pipe_in record review と /pipe-in --artifact の文を出さない', () => {
  const n = noticeOf({ pipe: 'cp' });
  assert.doesNotMatch(n, /python -m pipe_in record review/);
  assert.doesNotMatch(n, /\/pipe-in --artifact/);
  assert.doesNotMatch(n, /アーティファクトのボタン/);
});

test('D0077-AC-24: 会話の道の知らせのパイプ名は、HTML として解釈させない（escapeHtml を通る）', () => {
  const n = noticeOf({ pipe: '<img src=x onerror=alert(1)>' });
  assert.doesNotMatch(n, /<img/);
  assert.match(n, /&lt;img/);
  assert.match(n, /pipe-in-gen chat review --pipe /);
});

test('D0077-AC-24: 端末の記録（driver なし）の知らせは、今までどおり python -m pipe_in record review を出す（今のまま通る。守る）', () => {
  const n = noticeOf({ driver: false });
  assert.match(n, /python -m pipe_in record review draft approved/);
  assert.match(n, /\/pipe-in --artifact/);
  assert.doesNotMatch(n, /pipe-in-gen chat review/);
  assert.doesNotMatch(n, /\/pipe-in:pipe-run/);
});

test('D0077-AC-24: 開発用の記録（driver が pipe-dev）の知らせは、今までどおり python -m pipe_in record review を出す（今のまま通る。守る）', () => {
  const n = noticeOf({ driver: 'pipe-dev', usageSummary: 'old' });
  assert.match(n, /python -m pipe_in record review draft approved/);
  assert.match(n, /\/pipe-in --artifact/);
  assert.doesNotMatch(n, /pipe-in-gen chat review/);
  assert.doesNotMatch(n, /\/pipe-in:pipe-run/);
});
