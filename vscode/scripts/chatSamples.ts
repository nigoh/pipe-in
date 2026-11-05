// 会話の中で流したパイプの記録の見本（D0076）。確認用ページ（run-panel-chat-*）に使う state.json の中身だけを持つ。
// tests/fixtures/ には見本の記録を足さない。previewPages.ts の buildChatDir が、一時フォルダに書いて本物の読み取りで読む。
// 本体（pipe-in-gen chat）が書く形：driver が pipe-chat、usage_summary は available=false と理由、total_cost_usd と段の cost_usd は null。
// 流れは、下書き（確認あり）→ 直す（revise 1 回）→ 承認 → 確かめ（不合格）→ 下書きへ戻る → 確かめ（合格）→ 次の段の確認待ち。
// テストの見本（src/test/chatFixtures.ts）と同じ意味のもの。ここは拡張の外の開発用の道具なので、テストの見本は import しない。

const AT = '2026-11-05T10:00:00+09:00';

/** 見本の理由の文（本体が書く文と同じ意味） */
const REASON = '会話の中で流したため、費用とトークンは取れません';

function runEntry(stage: string, seq: number, note: string): Record<string, unknown> {
  return {
    stage,
    session_id: null,
    is_error: false,
    subtype: 'success',
    result: '',
    cost_usd: null,
    num_turns: 0,
    duration_sec: 3.2,
    denials: [],
    errors: [],
    seq,
    attempt: null,
    note,
  };
}

/** 見本の state.json の文字（パイプ chat-demo。最後の段「公開」の前の確認待ちで止まっている）。 */
export function chatStateJson(): string {
  const runs = [
    runEntry('draft', 1, ''),
    { stage: 'draft', review: 'revise', feedback: 'ここを直して（<b>太字</b> と書かれていても、そのまま見える）', at: AT },
    runEntry('draft', 2, '指摘を反映'),
    { stage: 'draft', review: 'approved', at: AT },
    runEntry('verify', 3, ''),
    { stage: 'verify', check: { attempt: 1, status: 'fail', problems: ['矢印が逆'], summary: '1 回目は直す点があります' } },
    runEntry('draft', 4, '検証の指摘を反映'),
    runEntry('verify', 5, ''),
    { stage: 'verify', check: { attempt: 2, status: 'pass', problems: [], summary: '直す点はありません' } },
    runEntry('publish', 6, ''),
  ];
  const state = {
    started_at: '2026-11-05T09:58:00',
    updated_at: '2026-11-05T10:05:00',
    pipe: 'chat-demo',
    name: '会話の道の見本',
    driver: 'pipe-chat',
    stages: [
      { name: 'draft', label: '下書き', output: '01_draft.md', review: true },
      { name: 'verify', label: '確かめ', output: '02_verify.md', review: false, check: { on_fail: 'draft', max_retries: 2 } },
      { name: 'publish', label: '公開', output: '03_publish.md', review: true },
    ],
    final: null,
    total_cost_usd: null,
    usage_summary: { available: false, reason: REASON },
    pending_review: { stage: 'publish', doc: 'docs/pipeline/chat-demo/03_publish.md', session_id: null, next: null, since: AT },
    warnings: [],
    open: null,
    runs,
  };
  return `${JSON.stringify(state, null, 2)}\n`;
}
