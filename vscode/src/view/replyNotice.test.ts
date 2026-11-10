// 確認待ちの帯（黄の知らせ）の出し分けと、返事の部分の HTML（D0079・AC-35 の単独表示・39・40・41・58）。
// 帯は記録の種類で変わる：印あり＝承認・修正を依頼・中止のボタン、driver なし＋pending_review＝pipe-in --review（--pause で止めた SDK の実行）、
// pipe-dev＝record review と /pipe-in --artifact、pipe-chat＝pipe-in-gen chat review、印も pending_review も無く waiting＝「次を待っている」。
// 項目 reply・hasDriver・pausePipe（図の状態）はまだ型に無いので、記録の状態から本物の buildPipelineView で作る。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { WAITING_MESSAGE } from '../domain/pipelineView.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { renderReplyNotice, replyRefusalText } from './replyHtml.ts';
import { renderViewBody } from './panelHtml.ts';
import { statusBarLabel } from './statusBar.ts';
import { withoutComments } from '../test/sourceText.ts';
import { MARK_ID, pending, replySnapshot, replyState, replyView, withKeys } from '../test/replyFixtures.ts';
import type { ReplySnapshotOptions } from '../test/replyFixtures.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import { stageRunEntry } from '../test/fixtures.ts';

const HERE_DIR = path.dirname(fileURLToPath(import.meta.url));

/** 黄の知らせ（class="notice" の要素。止まっているかもの知らせは class="notice stale-notice" なので別）を、入れ子の div も含めて取り出す。無ければ null */
function noticeOf(html: string): string | null {
  const start = html.search(/<div class="notice"[ >]/);
  if (start < 0) return null;
  let depth = 0;
  for (const m of html.slice(start).matchAll(/<div\b|<\/div>/g)) {
    depth += m[0] === '</div>' ? -1 : 1;
    if (depth === 0) return html.slice(start, start + (m.index ?? 0) + m[0].length);
  }
  return null;
}
const bodyOf = (view: PipelineView): string => renderViewBody(view);
const notice = (view: PipelineView): string => {
  const n = noticeOf(bodyOf(view));
  assert.ok(n !== null, '確認待ちの知らせが出ている');
  return n;
};
const plain = (html: string): string => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
const buttons = (html: string): string[] => [...html.matchAll(/data-reply="([^"]+)"/g)].map((m) => m[1]!);
/** data-reply-pane の値が name の要素の開きタグ */
const paneTag = (html: string, name: string): string => {
  const tag = new RegExp(`<[a-z]+\\b[^>]*data-reply-pane="${name}"[^>]*>`).exec(html)?.[0];
  assert.ok(tag !== undefined, `data-reply-pane="${name}" の要素がある`);
  return tag;
};
const isHidden = (tag: string): boolean => /\shidden(?=[\s>=])/.test(tag);

// ---- AC-39：帯の出し分けの 5 行 ----

test('D0079-AC-39: 印あり：どの段の確認待ちか・確認する文書・「承認」「修正を依頼」「中止」の 3 つのボタンが出て、「次を待っている」は出ない', () => {
  const view = replyView();
  const text = plain(notice(view));
  assert.match(text, /要件定義の確認を待っている/);
  assert.match(text, /01_requirements\.md/);
  assert.ok(text.includes('承認') && text.includes('修正を依頼') && text.includes('中止'));
  assert.ok(!bodyOf(view).includes(WAITING_MESSAGE), '「次を待っている」は出ない');
  assert.deepEqual(buttons(notice(view)).slice(0, 3), ['approve', 'revise-open', 'quit-open']);
});

test('D0079-AC-39: 印あり（パイプ）：パイプの段の表示名と成果物の名前の確認待ちになる', () => {
  const text = plain(notice(replyView({ pipe: 'reply-pipe' })));
  assert.match(text, /ソースの調査の確認を待っている/);
  assert.match(text, /01_survey\.md/);
});

test('D0079-AC-39: driver なし・pending_review あり（--pause で止めた SDK の実行）：pipe-in --review の案内が出て、ボタンは出ない', () => {
  const view = replyView({ mark: null, pendingReview: pending() });
  const text = plain(notice(view));
  assert.match(text, /pipe-in --review approve/);
  assert.deepEqual(buttons(notice(view)), []);
});

test('D0079-AC-39: driver が pipe-dev・pending_review あり：record review と /pipe-in --artifact の案内（今のまま通る。守る）', () => {
  const text = plain(notice(replyView({ mark: null, driver: 'pipe-dev', pendingReview: pending() })));
  assert.match(text, /python -m pipe_in record review requirements approved/);
  assert.match(text, /\/pipe-in --artifact/);
  assert.doesNotMatch(text, /pipe-in --review/);
});

test('D0079-AC-39: driver が pipe-chat・pending_review あり：pipe-in-gen chat review の案内（今のまま通る。守る）', () => {
  const text = plain(notice(replyView({ pipe: 'reply-pipe', mark: null, driver: 'pipe-chat', pendingReview: pending('survey', 'docs/pipeline/reply-pipe/01_survey.md') })));
  assert.match(text, /pipe-in-gen chat review --pipe reply-pipe approved/);
  assert.match(text, /\/pipe-in:pipe-run/);
  assert.doesNotMatch(text, /pipe-in --review/);
});

test('D0079-AC-39: 印も pending_review も無く waiting（古い本体の記録）：「次を待っている（人の確認かもしれない）」だけで、黄の知らせは出ない（今のまま通る。守る）', () => {
  const body = bodyOf(replyView({ mark: null }));
  assert.ok(body.includes(WAITING_MESSAGE));
  assert.equal(noticeOf(body), null);
});

test('D0079-AC-39: 動いている段があるとき・終わったあとは、どの記録の状態でも帯が出ない（今のまま通る。守る）', () => {
  const states: ReplySnapshotOptions[] = [{}, { mark: null, pendingReview: pending() }, { mark: null, driver: 'pipe-dev', pendingReview: pending() }, { mark: null, driver: 'pipe-chat', pendingReview: pending() }];
  for (const state of states) {
    assert.equal(noticeOf(bodyOf(replyView({ ...state, running: true }))), null, `動いている：${JSON.stringify(state)}`);
    assert.equal(noticeOf(bodyOf(replyView({ ...state, final: 'PASSED' }))), null, `終わった：${JSON.stringify(state)}`);
  }
});

test('D0079-AC-39: 印があっても条件を崩した記録（driver あり・別の worktree・archive/）には、ボタンが出ない（今のまま通る。守る）', () => {
  for (const options of [{ driver: 'pipe-dev' }, { other: true }, { previous: true }]) {
    assert.doesNotMatch(bodyOf(replyView(options)), /data-reply=/, JSON.stringify(options));
  }
});

// ---- 返事の部分の HTML の約束（パネルのスクリプトが読む）。AC-39・42 の支え ----

test('D0079-AC-39: renderReplyNotice は印のある図の帯の返事の部分を返し、印の無い図では空', () => {
  assert.notEqual(renderReplyNotice(replyView()), '');
  assert.equal(renderReplyNotice(replyView({ mark: null })), '');
  assert.equal(renderReplyNotice(replyView({ mark: null, pendingReview: pending() })), '');
});

test('D0079-AC-42: 帯は識別子・送ったか・30 秒たったかを data-reply-id・data-reply-sent・data-reply-stalled に持つ（スクリプトが描き直しをまたいで読む）', () => {
  const n = notice(replyView());
  const head = /<div class="notice"[^>]*>/.exec(n)![0];
  assert.match(head, new RegExp(`data-reply-id="${MARK_ID}"`));
  assert.match(head, /data-reply-sent="0"/);
  assert.match(head, /data-reply-stalled="0"/);
  assert.match(head, /role="status"/);
});

test('D0079-AC-42: 4 つの状態の枠（choose・revise・confirm・sent）があり、最初は choose だけが見える', () => {
  const n = notice(replyView());
  assert.equal(isHidden(paneTag(n, 'choose')), false);
  for (const pane of ['revise', 'confirm', 'sent']) assert.equal(isHidden(paneTag(n, pane)), true, pane);
});

test('D0079-AC-42: 最初の枠に承認・修正を依頼・中止、修正の枠に入力欄（data-keep=reply-feedback）と送る・戻る、確かめの枠に中止する・戻る', () => {
  const n = notice(replyView());
  assert.deepEqual(buttons(n), ['approve', 'revise-open', 'quit-open', 'revise-send', 'back', 'quit-send', 'back']);
  assert.match(n, /<textarea\b[^>]*data-keep="reply-feedback"[^>]*>/);
  assert.match(n, /aria-label="直してほしい点"/);
  assert.match(n, /1,000 文字まで/);
  assert.match(n, /本当に中止しますか/);
  const send = /<button\b[^>]*data-reply="revise-send"[^>]*>/.exec(n)![0];
  assert.match(send, /\sdisabled(?=[\s>=])/, '空のあいだ「送る」は押せない');
});

test('D0079-AC-42: 送った（返事のファイルが有る）図では、choose・revise・confirm が隠れ、「送りました（pipe-in が読むのを待っています）」が 1 か所だけ見える', () => {
  const now = Date.UTC(2026, 9, 17, 10, 0, 40);
  const n = notice(replyView({ replyFile: { mtimeMs: now - 5_000 } }));
  assert.match(/<div class="notice"[^>]*>/.exec(n)![0], /data-reply-sent="1"/);
  for (const pane of ['choose', 'revise', 'confirm']) assert.equal(isHidden(paneTag(n, pane)), true, pane);
  assert.equal(isHidden(paneTag(n, 'sent')), false);
  assert.equal(n.split('送りました（pipe-in が読むのを待っています）').length - 1, 1, '同じ文を 2 か所に出さない');
  assert.doesNotMatch(n, /止まっていないか確かめてください/, '5 秒では案内を足さない');
});

test('D0079-AC-51: 送って 30 秒たつと「端末の pipe-in が止まっていないか確かめてください」が足される（29 秒では出ない）', () => {
  const now = Date.UTC(2026, 9, 17, 10, 0, 40);
  const at29 = notice(replyView({ replyFile: { mtimeMs: now - 29_000 } }));
  const at30 = notice(replyView({ replyFile: { mtimeMs: now - 30_000 } }));
  assert.doesNotMatch(at29, /止まっていないか確かめてください/);
  assert.match(at29, /data-reply-stalled="0"/);
  assert.match(at30, /data-reply-stalled="1"/);
  assert.equal(at30.split('止まっていないか確かめてください').length - 1, 1, '1 か所だけ');
  assert.match(plain(at30), /送りました（pipe-in が読むのを待っています）/);
});

test('D0079-AC-58: 帯に style 属性・インラインの動作（onclick など）・外部の読み込み（src・href）が無い', () => {
  for (const view of [replyView(), replyView({ replyFile: { mtimeMs: Date.UTC(2026, 9, 17, 10, 0, 0) } })]) {
    const n = notice(view);
    assert.doesNotMatch(n, /\sstyle=|\son[a-z]+=|\ssrc=|\shref=|<script|<iframe|<link/i);
  }
});

// ---- AC-35：ステータスバーの単独表示 ----

test('D0079-AC-35: 単独表示のステータスバーは、reply があれば「確認待ち」と出す（pending_review の確認待ちと同じ形）', () => {
  const label = statusBarLabel(replyView());
  assert.match(label.text, /要件定義の確認待ち/);
  assert.match(label.text, /comment-discussion/);
  assert.match(label.tooltip, /要件定義の確認を待っている/);
});

test('D0079-AC-35: 単独表示は、印の無い waiting では今までどおり「待ち」（今のまま通る。守る）', () => {
  const label = statusBarLabel(replyView({ mark: null }));
  assert.match(label.text, /待ち/);
  assert.doesNotMatch(label.text, /確認待ち/);
  assert.match(statusBarLabel(replyView({ mark: null, pendingReview: pending() })).text, /要件定義の確認待ち/);
});

// ---- AC-40：--pause の案内 ----

test('D0079-AC-40: driver なし・pending_review ありの帯に、pipe-in --review approve・--review revise --feedback・--review quit が出る', () => {
  const text = plain(notice(replyView({ mark: null, pendingReview: pending() })));
  assert.match(text, /pipe-in --review approve/);
  assert.match(text, /--review revise --feedback/);
  assert.match(text, /--review quit/);
});

test('D0079-AC-40: 開発フロー（pipe が dev・無い）の案内では、pipe-in --review approve のコマンドに --pipe が付かない', () => {
  const dev = plain(notice(replyView({ mark: null, pendingReview: pending() })));
  assert.match(dev, /pipe-in --review approve/);
  assert.doesNotMatch(dev, /--review approve\s+--pipe/);
  const none = replySnapshot({ stateJson: withKeys(replyState({ mark: null, pendingReview: pending() }), { pipe: undefined }) });
  const text = plain(notice(buildPipelineView(none)));
  assert.match(text, /pipe-in --review approve/);
  assert.doesNotMatch(text, /--review approve\s+--pipe/);
});

test('D0079-AC-40: パイプの記録（state.json の pipe がパイプ名）の案内には、--pipe <パイプ名> が付く', () => {
  const view = replyView({ pipe: 'pause-pipe', mark: null, pendingReview: pending('survey', 'docs/pipeline/pause-pipe/01_survey.md') });
  const text = plain(notice(view));
  assert.match(text, /pipe-in --review approve --pipe pause-pipe/);
  assert.match(text, /--review revise --feedback/);
  assert.match(text, /--review quit/);
});

test('D0079-AC-40: python -m pipe_in record review と /pipe-in --artifact の案内は出ない', () => {
  for (const pipe of ['dev', 'pause-pipe']) {
    const text = plain(notice(replyView({ pipe, mark: null, pendingReview: pending() })));
    assert.doesNotMatch(text, /python -m pipe_in record review/, pipe);
    assert.doesNotMatch(text, /\/pipe-in --artifact/, pipe);
    assert.doesNotMatch(text, /アーティファクトのボタン/, pipe);
  }
});

test('D0079-AC-40: パイプ名は escapeHtml を通る（タグ・引用符を壊さない）', () => {
  const hostile = '<img src=x onerror=alert(1)>"\'';
  const n = notice(replyView({ pipe: hostile, mark: null, pendingReview: pending() }));
  assert.doesNotMatch(n, /<img/);
  assert.match(n, /&lt;img/);
  assert.match(n, /pipe-in --review approve/);
});

// ---- AC-41：pipe-dev と pipe-chat は今のまま ----

test('D0079-AC-41: pipe-dev の帯は、record review の文と /pipe-in --artifact の文（今のまま通る。守る）', () => {
  const text = plain(notice(replyView({ mark: null, driver: 'pipe-dev', pendingReview: pending() })));
  assert.match(text, /python -m pipe_in record review requirements approved/);
  assert.match(text, /revise --feedback/);
  assert.match(text, /\/pipe-in --artifact/);
  assert.match(text, /アーティファクトのボタン/);
  assert.doesNotMatch(text, /pipe-in-gen chat review/);
});

test('D0079-AC-41: pipe-chat の帯は、pipe-in-gen chat review --pipe の文（今のまま通る。守る）', () => {
  const text = plain(notice(replyView({ pipe: 'reply-pipe', mark: null, driver: 'pipe-chat', pendingReview: pending('survey', 'docs/pipeline/reply-pipe/01_survey.md') })));
  assert.match(text, /pipe-in-gen chat review --pipe reply-pipe approved/);
  assert.doesNotMatch(text, /python -m pipe_in record review/);
  assert.doesNotMatch(text, /\/pipe-in --artifact/);
});

// ---- AC-58：確認の部品の検査 ----

/** window.confirm・alert・prompt（と window を付けない呼び出し）。コメントは見ない */
function dialogCalls(source: string): string[] {
  return [...withoutComments(source).matchAll(/(?<![\w.$])(?:window\s*\.\s*)?(?:confirm|alert|prompt)\s*\(/g)].map((m) => m[0]);
}

test('D0079-AC-58: replyHtml.ts と panelScript.ts に window.confirm・alert・prompt を使う呼び出しが無い（今のまま通る。守る）', () => {
  for (const file of ['replyHtml.ts', 'panelScript.ts']) {
    const source = readFileSync(path.join(HERE_DIR, file), 'utf8');
    assert.ok(source.length > 100, `${file} が読めている`);
    assert.deepEqual(dialogCalls(source), [], file);
  }
});

test('D0079-AC-58: 検査そのもの：window.confirm(・alert(・prompt( の呼び出しは見つけ、コメント・名前の一部は見逃す（今のまま通る。守る）', () => {
  assert.deepEqual(dialogCalls("if (window.confirm('x')) go();"), ['window.confirm(']);
  assert.deepEqual(dialogCalls("alert('x'); prompt ('y');"), ['alert(', 'prompt (']);
  assert.deepEqual(dialogCalls("// window.confirm('x')\nconst replyConfirm = 1; const confirmed = reply.confirm(1);"), []);
});

test('D0079-AC-58: 帯を作る部品（replyHtml.ts）は、外から来た文字を escapeHtml を通してから HTML に入れる（escape.ts から読む）', () => {
  const source = withoutComments(readFileSync(path.join(HERE_DIR, 'replyHtml.ts'), 'utf8'));
  assert.match(source, /import \{[^}]*\bescapeHtml\b[^}]*\} from '\.\/escape\.ts'/, 'escapeHtml を escape.ts から読む');
  assert.ok((source.match(/\bescapeHtml\(/g) ?? []).length >= 2, '段の表示名・文書名などに escapeHtml を使う');
  assert.doesNotMatch(source, /&(?:amp|lt|gt|quot|apos|#\d+);/, '自前のエスケープを持たない');
});

test('D0079-AC-58: 段の表示名・文書名・識別子に <script> や引用符が入っていても、帯の中では文字のまま（タグにならず、ボタンの属性を壊さない）', () => {
  const label = '<script>alert(1)</script>"\'<b>';
  const doc = '"><img src=x onerror=alert(1)>.md';
  const stages = [{ name: 'x', label, output: doc, review: true }];
  const text = withKeys(replyState({ pipe: 'reply-pipe' }), { stages, runs: [stageRunEntry({ stage: 'x', seq: 1 })], reply_wait: { stage: 'x', id: MARK_ID, since: '2026-10-17T10:00:00+00:00' } });
  const view = buildPipelineView(replySnapshot({ stateJson: text }));
  const n = notice(view);
  assert.doesNotMatch(n, /<script|<img|<b>/);
  assert.match(n, /&lt;script&gt;/);
  assert.deepEqual(buttons(n).slice(0, 3), ['approve', 'revise-open', 'quit-open'], 'ボタンは壊れない');
  assert.ok(plain(n).includes('alert(1)'), '文字としては見える');
});

// ---- AC-48：断った理由の文 ----

test('D0079-AC-48: 断った理由の文：no_offer・changed・exists は決まった文、ほか（bad_input・bad_run・bad_text・outside・failed）は「送れませんでした」で始まる', () => {
  assert.equal(replyRefusalText('no_offer'), 'いまは返事を受け付けていません');
  assert.equal(replyRefusalText('changed'), '確認が進んだか別の確認になったので、送りませんでした');
  assert.equal(replyRefusalText('exists'), 'すでに返事を送っています');
  for (const reason of ['bad_input', 'bad_run', 'bad_text', 'outside', 'failed']) {
    assert.match(replyRefusalText(reason), /^送れませんでした/, reason);
  }
});
