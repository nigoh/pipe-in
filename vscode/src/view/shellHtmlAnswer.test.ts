// D0064：確認待ちの知らせ（黄の枠）に、確かめる文書を開くボタンと答え方を出す。純粋な文字列の検査。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { PipelineView } from '../domain/pipelineView.ts';
import { finishedView, runningView, waitingView } from '../test/liveFixtures.ts';
import { listView } from '../test/runListFixtures.ts';

const shell = () => import('./shellHtml.ts');
const render = async (view: PipelineView): Promise<string> => (await shell()).renderShell(view, listView([]));
const noticeOf = (out: string): string => {
  const at = out.indexOf('<div class="notice" role="status">');
  assert.ok(at >= 0, '確認待ちの知らせがある');
  return out.slice(at, out.indexOf('</div>', at));
};
const plain = (text: string): string => text.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();

test('D0064-AC-01: 確認待ちの知らせに「確かめる文書を開く」のボタンがあり、成果物の名前（data-artifact）で既存の openArtifact に渡る', async () => {
  const notice = noticeOf(await render(waitingView(40)));
  assert.match(notice, /<button type="button" class="secondary" data-artifact="01_requirements\.md"[^>]*>確かめる文書を開く<\/button>/);
});

// D0079 で直した：入力を driver が pipe-dev の記録（hasDriver: true）にして、今の期待を残した。driver が無い記録（--pause で止めた SDK の実行）の帯は
// pipe-in --review になった（replyNotice.test.ts の D0079-AC-40）。項目 hasDriver は図の状態の省いてよい項目。
const devNotice = (view: PipelineView): PipelineView => ({ ...view, hasDriver: true }) as unknown as PipelineView;

test('D0064-AC-02: 知らせに答え方が読める：record review のコマンド（approved・revise --feedback・quit）と、/pipe-in --artifact のときのアーティファクトのボタン', async () => {
  const text = plain(noticeOf(await render(devNotice(waitingView(40)))));
  assert.match(text, /python -m pipe_in record review requirements approved/);
  assert.match(text, /revise --feedback/);
  assert.match(text, /quit/);
  assert.match(text, /\/pipe-in --artifact/);
  assert.match(text, /アーティファクトのボタン/);
});

test('D0064-AC-03: 文書がまだ読めない（成果物が ready でない・名前が一覧に無い）ときは、開くボタンを出さず、答え方は出す', async () => {
  const base = devNotice(waitingView(40));
  const notReady: PipelineView = { ...base, artifacts: base.artifacts.map((a) => ({ ...a, ready: false })) };
  const unknown: PipelineView = { ...base, pendingReview: { stage: 'requirements', label: '要件定義', doc: 'docs/pipeline/../../secret.md' } };
  for (const view of [notReady, unknown]) {
    const notice = noticeOf(await render(view));
    assert.doesNotMatch(notice, /data-artifact=/);
    assert.doesNotMatch(notice, /確かめる文書を開く/);
    assert.match(plain(notice), /record review requirements approved/);
  }
});

test('D0064-AC-04: 外から来た文字（段・名前）は escapeHtml を通り、タグや属性を壊さない', async () => {
  const base = waitingView(40);
  const evil: PipelineView = {
    ...base,
    pendingReview: { stage: 'a"><script>x</script>' as never, label: '<b>x</b>', doc: 'docs/pipeline/"><img src=x>.md' },
    artifacts: base.artifacts.map((a, i) => (i === 0 ? { ...a, name: '"><img src=x>.md' as never, ready: true } : a)),
  };
  const notice = noticeOf(await render(evil));
  assert.doesNotMatch(notice, /<script>|<img |<b>x/);
});

test('D0064-AC-05: 動いている段があるとき・終わったあとは、知らせも新しい案内も出ない', async () => {
  for (const view of [runningView(83), finishedView()]) {
    const out = await render(view);
    assert.doesNotMatch(out, /確かめる文書を開く|record review/);
  }
});

test('D0064-AC-06: 知らせ（showInformationMessage）のボタンは「実行を見る」だけのまま増えない', async () => {
  const mod = await import('./waitNotice.ts');
  assert.deepEqual(Object.keys(mod).sort(), ['SHOW_RUN_LABEL', 'waitingNoticeText']);
  assert.equal(mod.SHOW_RUN_LABEL, '実行を見る');
});
