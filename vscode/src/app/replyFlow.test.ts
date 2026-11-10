// 返事を送る手順（D0079。app/replyFlow.ts）：AC-48・49。偽の口（ReplyStore）と偽の「読み直し」を手で書いて、流れを最初から最後まで通す。
// 最後に描いた図の印（段と識別子）と、書く直前に読み直した印が同じときだけ書く。違うときは書かず changed を返す（描き直して理由を見せるのは入口）。
// 選んでいる実行が条件を満たさない（shown が null）ときは、古い画面からの知らせでも書かない。パネルから来る値は動作と直してほしい点だけ。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { replyOfferOf, sendReply } from './replyFlow.ts';
import type { ReplyOffer, ReplyStore, ReplyStoreReason } from './replyFlow.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import type { ReplyText } from '../domain/replyFile.ts';
import { finishedView } from '../test/liveFixtures.ts';
import { MARK_ID, NEXT_ID } from '../test/replyFixtures.ts';
import type { ReplyViewLike } from '../test/replyFixtures.ts';

const APPROVE_TEXT = (stage: string, id: string): string => `{"version":1,"stage":"${stage}","id":"${id}","action":"approve"}`;

/** 手で書いた偽の口：呼ばれた (runId, text) を覚え、決めた結果を返す */
class FakeStore implements ReplyStore {
  calls: { runId: string; text: string }[] = [];
  // node の「型を消すだけ」の読み込みでは、引数に private を付ける書き方（パラメータプロパティ）が使えないので、項目を別に書く
  private readonly result: { ok: true } | { ok: false; reason: ReplyStoreReason };
  constructor(result: { ok: true } | { ok: false; reason: ReplyStoreReason } = { ok: true }) {
    this.result = result;
  }
  async create(runId: string, text: ReplyText): Promise<{ ok: true } | { ok: false; reason: ReplyStoreReason }> {
    this.calls.push({ runId, text });
    return this.result;
  }
}

const offer = (over: Partial<ReplyOffer> = {}): ReplyOffer => ({ key: 'here|', stage: 'requirements', id: MARK_ID, ...over });

/** 読み直しの偽物：呼ばれた回数を数え、決めた申し出（または null）を返す */
function rereader(value: ReplyOffer | null): { reread: () => Promise<ReplyOffer | null>; count: () => number } {
  let n = 0;
  return {
    reread: async () => {
      n += 1;
      return value;
    },
    count: () => n,
  };
}

// ---- replyOfferOf ----

const withReply = (reply: ReplyViewLike | null): PipelineView => ({ ...finishedView(), reply }) as unknown as PipelineView;
const REPLY: ReplyViewLike = { stage: 'requirements', label: '要件定義', id: MARK_ID, doc: '01_requirements.md', waitingSec: 40, sent: false, stalled: false };

test('D0079-AC-48: replyOfferOf は reply のある図と、いまの work_dir の実行の目印（直下・パイプ）から、{ key, stage, id } を作る', () => {
  assert.deepEqual(replyOfferOf(withReply(REPLY), 'here|'), { key: 'here|', stage: 'requirements', id: MARK_ID });
  assert.deepEqual(replyOfferOf(withReply({ ...REPLY, stage: 'survey' }), 'here|reply-pipe'), { key: 'here|reply-pipe', stage: 'survey', id: MARK_ID });
});

test('D0079-AC-49: replyOfferOf は reply が無い図・別の worktree・主の checkout・archive/ の実行・形の違う目印では null', () => {
  assert.equal(replyOfferOf(withReply(null), 'here|'), null, 'reply が無い');
  assert.equal(replyOfferOf(finishedView(), 'here|'), null, '項目が無い図');
  for (const key of ['wt.feat-x|', 'wt.feat-x|reply-pipe', 'main|', 'main|reply-pipe', 'here|archive/20261016-090000', 'here|logs', 'here|../x', 'here', '', 'archive']) {
    assert.equal(replyOfferOf(withReply(REPLY), key), null, key);
  }
});

// ---- AC-48：書く直前に読み直して、同じときだけ書く ----

test('D0079-AC-48: 読み直した印が同じなら、返事の中身を作って口に渡す：承認（直下）', async () => {
  const store = new FakeStore();
  const r = rereader(offer());
  const result = await sendReply({ action: 'approve' }, { shown: offer(), reread: r.reread, store });
  assert.deepEqual(result, { ok: true });
  assert.deepEqual(store.calls, [{ runId: '', text: APPROVE_TEXT('requirements', MARK_ID) }]);
  assert.equal(r.count(), 1, '書く直前に 1 回読み直す');
});

test('D0079-AC-48: 実行のフォルダ名は読み直した目印から（パイプは here|<パイプ名> → パイプ名）。段と識別子は自分の申し出から入る', async () => {
  const store = new FakeStore();
  const shown = offer({ key: 'here|reply-pipe', stage: 'survey' });
  await sendReply({ action: 'quit' }, { shown, reread: rereader(shown).reread, store });
  assert.deepEqual(store.calls, [{ runId: 'reply-pipe', text: '{"version":1,"stage":"survey","id":"a1b2c3d4e5","action":"quit"}' }]);
});

test('D0079-AC-48: 修正の依頼は直してほしい点が入った文字になる（前後の空白は取る）', async () => {
  const store = new FakeStore();
  await sendReply({ action: 'revise', feedback: '  ここを直して\n' }, { shown: offer(), reread: rereader(offer()).reread, store });
  assert.deepEqual(store.calls, [{ runId: '', text: `{"version":1,"stage":"requirements","id":"${MARK_ID}","action":"revise","feedback":"ここを直して"}` }]);
});

const CHANGED: readonly (readonly [string, ReplyOffer | null])[] = [
  ['印が消えた（待ちが終わった）', null],
  ['次の待ちが始まった（識別子が違う）', offer({ id: NEXT_ID })],
  ['同じ段の 2 回目の待ち（識別子が違う）', offer({ id: 'ffffffffff' })],
  ['別の段の確認待ちになった', offer({ stage: 'design' })],
  ['選んでいる実行が替わった（目印が違う）', offer({ key: 'here|reply-pipe' })],
  ['別の場所の実行になった', offer({ key: 'wt.feat-x|' })],
];
for (const [label, fresh] of CHANGED) {
  test(`D0079-AC-48: 読み直した印が違うときは書かず changed を返す：${label}`, async () => {
    const store = new FakeStore();
    const result = await sendReply({ action: 'approve' }, { shown: offer(), reread: rereader(fresh).reread, store });
    assert.deepEqual(result, { ok: false, reason: 'changed' });
    assert.deepEqual(store.calls, [], '口を呼ばない');
  });
}

test('D0079-AC-48: 読み直しの結果が違っても、渡した申し出と読み直しの結果は変わらない（書いたのは自分の申し出）', async () => {
  const shown = offer();
  const fresh = offer();
  await sendReply({ action: 'approve' }, { shown, reread: rereader(fresh).reread, store: new FakeStore() });
  assert.deepEqual(shown, offer());
  assert.deepEqual(fresh, offer());
});

// ---- AC-49：条件を満たさない実行には書かない ----

test('D0079-AC-49: 選んでいる実行が条件を満たさない（shown が null）ときは、古い画面からの知らせでも書かず no_offer を返す。読み直しもしない', async () => {
  const store = new FakeStore();
  const r = rereader(offer());
  const result = await sendReply({ action: 'approve' }, { shown: null, reread: r.reread, store });
  assert.deepEqual(result, { ok: false, reason: 'no_offer' });
  assert.deepEqual(store.calls, []);
  assert.equal(r.count(), 0);
});

// ---- パネルから来る値の検め ----

const BAD_INPUT: readonly (readonly [string, { action: unknown; feedback?: unknown }])[] = [
  ['approved（record review の言葉）', { action: 'approved' }],
  ['知らない動作', { action: 'delete' }],
  ['動作が無い', { action: undefined }],
  ['動作が数', { action: 1 }],
  ['承認に直してほしい点', { action: 'approve', feedback: '直して' }],
  ['中止に直してほしい点', { action: 'quit', feedback: '直して' }],
  ['修正の依頼で直してほしい点が無い', { action: 'revise' }],
  ['修正の依頼で直してほしい点が空白だけ', { action: 'revise', feedback: '  ' }],
  ['修正の依頼で 1001 文字', { action: 'revise', feedback: 'a'.repeat(1001) }],
  ['修正の依頼で使えない文字', { action: 'revise', feedback: '直\u0000して' }],
];
for (const [label, choice] of BAD_INPUT) {
  test(`D0079-AC-48: 形の違う入力は何も書かず bad_input を返す（読み直しもしない）：${label}`, async () => {
    const store = new FakeStore();
    const r = rereader(offer());
    const result = await sendReply(choice, { shown: offer(), reread: r.reread, store });
    assert.deepEqual(result, { ok: false, reason: 'bad_input' });
    assert.deepEqual(store.calls, []);
    assert.equal(r.count(), 0);
  });
}

// ---- 口の結果はそのまま返す ----

for (const reason of ['bad_run', 'bad_text', 'outside', 'exists', 'failed'] as const) {
  test(`D0079-AC-48: 口が断った理由はそのまま返す：${reason}`, async () => {
    const store = new FakeStore({ ok: false, reason });
    const result = await sendReply({ action: 'approve' }, { shown: offer(), reread: rereader(offer()).reread, store });
    assert.deepEqual(result, { ok: false, reason });
    assert.equal(store.calls.length, 1);
  });
}

test('D0079-AC-48: 同じ確認に二度送ると、2 回目は口が exists で断る（二度書かない口の結果をそのまま返す）', async () => {
  let created = false;
  const store: ReplyStore = {
    async create() {
      if (created) return { ok: false, reason: 'exists' };
      created = true;
      return { ok: true };
    },
  };
  const deps = { shown: offer(), reread: rereader(offer()).reread, store };
  assert.deepEqual(await sendReply({ action: 'approve' }, deps), { ok: true });
  assert.deepEqual(await sendReply({ action: 'approve' }, deps), { ok: false, reason: 'exists' });
});
