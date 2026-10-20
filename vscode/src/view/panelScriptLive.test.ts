// パネルのスクリプトの数え上げと、戻る矢印の光り（D0017）。renderPanelHtml の出力から <script nonce> の中身を取り出し、
// node:vm で、手で書いた偽の DOM（src/test/fakeDom.ts）と偽の時計の上で動かす。本物の時間は使わない（sleep しない）。
// スクリプトは「記録の時刻と今の時刻」を比べず、render を受けた時刻（パネルの時計）からの差だけを足す。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';
import type { RunListView } from '../domain/runList.ts';
import { listView, row } from '../test/runListFixtures.ts';
import { bootPanel } from '../test/fakeDom.ts';
import type { BootOptions, FakeNode, PanelHarness } from '../test/fakeDom.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { DURATION_TABLE, finishedView, loopSnapshot, reviseView, runningView, sendBackView, viewAt, waitingView } from '../test/liveFixtures.ts';

const NONCE = 'TESTNONCE';
// D0019: 実行を選ぶボタン（RunPicker）は実行の一覧（RunListView）に置き換わった。期待する動きは変えない
const boot = (view: PipelineView, opts?: BootOptions, picker?: RunListView): PanelHarness =>
  bootPanel(renderPanelHtml(view, NONCE, picker), opts);
const body = (view: PipelineView, picker?: RunListView): string => renderViewBody(view, picker);
const render = (h: PanelHarness, view: PipelineView, picker?: RunListView): void => h.send({ type: 'render', html: body(view, picker) });
/** 実行 a・b の 2 行の一覧（selected は 'a' か 'b'） */
const pickerOf = (selected: string): RunListView =>
  listView([row({ key: 'here|a', session: 'A' }), row({ key: 'here|b', session: 'B' })], { selected: `here|${selected}` });

/** 数え上げる要素の今の文字（文書の順。runningView なら [バナー, 動いている段の節]）。 */
const shown = (h: PanelHarness): string[] => h.doc.querySelectorAll('[data-elapsed]').map((n) => h.text(n));
const isNew = (h: PanelHarness, id: string): boolean => h.loop(id).classList.contains('is-new');
const newLoops = (h: PanelHarness): string[] =>
  h.doc
    .querySelectorAll('[data-loop]')
    .filter((l) => l.classList.contains('is-new'))
    .map((l) => l.getAttribute('data-loop')!);
const clickNode = (h: PanelHarness, id: string): void => {
  const g = h.node(id);
  const child = g.children.find((c): c is FakeNode => 'tagName' in c && c.tagName === 'text') ?? g;
  child.dispatch('click');
};
const openIds = (h: PanelHarness): string[] =>
  h.doc
    .querySelectorAll('[data-reasons-for]')
    .filter((s) => !s.hidden)
    .map((s) => s.getAttribute('data-reasons-for')!);

// ---- AC-22：数え上げ ----

test('D0017-AC-22: 読み込み直後は基準の秒の表示（83 秒 → 1:23、全体 203 秒 → 3:23）で、時計が進むと増える（5 秒後は 1:28）', () => {
  const h = boot(runningView(83));
  assert.deepEqual(shown(h), ['3:23', '1:23']);
  h.advance(5000);
  assert.deepEqual(shown(h), ['3:28', '1:28']);
});

test('D0017-AC-22: 1 秒ごとに 1 秒ずつ増える（1 秒に満たないあいだは変わらない）', () => {
  const h = boot(runningView(83));
  h.advance(999);
  assert.deepEqual(shown(h), ['3:23', '1:23']);
  h.advance(1);
  assert.deepEqual(shown(h), ['3:24', '1:24']);
  h.advance(1000);
  assert.deepEqual(shown(h), ['3:25', '1:25']);
});

test('D0017-AC-22: 60 秒・1 時間をまたぐと m:ss → h:mm:ss になる（3599 秒の 2 秒後は 1:00:01）', () => {
  const h = boot(runningView(3599));
  assert.equal(shown(h)[1], '59:59');
  h.advance(2000);
  assert.equal(shown(h)[1], '1:00:01');
});

test('D0017-AC-22: 確認待ちの待ち時間（node-wait）も同じ仕組みで増える', () => {
  const h = boot(waitingView(40));
  assert.deepEqual(shown(h), ['2:40', '0:40']);
  h.advance(5000);
  assert.deepEqual(shown(h), ['2:45', '0:45']);
});

test('D0017-AC-22: render を受けた直後は、HTML の文字でなく基準の秒の表示になる（その後は 1 秒ごとに増える）', () => {
  const h = boot(finishedView());
  h.advance(30_000);
  h.send({ type: 'render', html: '<p><span class="elapsed" data-elapsed="83">古い文字</span></p>' });
  assert.deepEqual(shown(h), ['1:23']);
  h.advance(5000);
  assert.deepEqual(shown(h), ['1:28']);
});

test('D0017-AC-22: 数え上げは render を受けた時刻（パネルの時計）からの差で、前の render からの時間を引き継がない', () => {
  const h = boot(runningView(83));
  h.advance(10_000);
  assert.equal(shown(h)[1], '1:33');
  render(h, runningView(83)); // 同じ基準でも、受けた時刻から数え直す
  assert.equal(shown(h)[1], '1:23');
  h.advance(2000);
  assert.equal(shown(h)[1], '1:25');
});

// ---- AC-23：render で数え直し・タイマーは 1 つ ----

test('D0017-AC-23: render で基準が替わったら、替わった基準から数え直す（83 → 500 秒、2 秒後は 8:22）', () => {
  const h = boot(runningView(83));
  h.advance(3000);
  render(h, runningView(500));
  assert.deepEqual(shown(h), ['10:20', '8:20']);
  h.advance(2000);
  assert.deepEqual(shown(h), ['10:22', '8:22']);
});

test('D0017-AC-23: render を何度受けても、動いているタイマーは 1 つのまま（古いものは止める）', () => {
  const h = boot(runningView(83));
  assert.equal(h.activeIntervals(), 1, '起動時に 1 つ');
  for (let i = 0; i < 10; i++) {
    h.advance(1500);
    render(h, runningView(83 + i));
    assert.equal(h.activeIntervals(), 1, `${i + 1} 回目の render のあと`);
  }
  assert.ok(h.createdIntervals() >= 1);
});

test('D0017-AC-23: 古いタイマーが残って、表示が 1 秒に 2 回以上書き換わることはない（1 秒の間に増えるのは 1 秒分）', () => {
  const h = boot(runningView(83));
  render(h, runningView(100));
  render(h, runningView(200));
  h.advance(1000);
  assert.equal(shown(h)[1], '3:21');
  h.advance(1000);
  assert.equal(shown(h)[1], '3:22');
});

// ---- AC-24：見えていないあいだは止める ----

test('D0017-AC-24: hidden になるとタイマーが止まり（登録が解かれ）、visible に戻ると隠れていた時間を足した値にすぐ直って再開する', () => {
  const h = boot(runningView(83));
  assert.equal(h.activeIntervals(), 1);
  h.setVisibility('hidden');
  assert.equal(h.activeIntervals(), 0);
  h.advance(10_000);
  assert.equal(shown(h)[1], '1:23', '隠れているあいだは書き換えない');
  h.setVisibility('visible');
  assert.equal(shown(h)[1], '1:33', '戻った瞬間に、隠れていた 10 秒を足した値になる');
  assert.equal(shown(h)[0], '3:33');
  assert.equal(h.activeIntervals(), 1, 'タイマーが再開している');
  h.advance(2000);
  assert.equal(shown(h)[1], '1:35');
});

test('D0017-AC-24: hidden と visible を何度繰り返しても、動いているタイマーは多くても 1 つで、visible を重ねて受けても増えない', () => {
  const h = boot(runningView(83));
  for (let i = 0; i < 4; i++) {
    h.setVisibility('hidden');
    assert.equal(h.activeIntervals(), 0);
    h.setVisibility('hidden');
    assert.equal(h.activeIntervals(), 0);
    h.setVisibility('visible');
    h.setVisibility('visible');
    assert.equal(h.activeIntervals(), 1);
  }
});

test('D0017-AC-24: 隠れているあいだに render が来ても、タイマーは回さない。visible に戻ると、その render の基準で直って再開する', () => {
  const h = boot(runningView(83));
  h.setVisibility('hidden');
  render(h, runningView(500));
  assert.equal(h.activeIntervals(), 0);
  h.advance(4000);
  h.setVisibility('visible');
  assert.equal(shown(h)[1], '8:24', '受けた基準 500 秒＋隠れていた 4 秒');
  assert.equal(h.activeIntervals(), 1);
});

test('D0017-AC-24: 最初から hidden で開かれたときはタイマーを回さず、visible になると回り始める', () => {
  const h = boot(runningView(83), { visibility: 'hidden' });
  assert.equal(h.activeIntervals(), 0);
  h.advance(3000);
  h.setVisibility('visible');
  assert.equal(h.activeIntervals(), 1);
  assert.equal(shown(h)[1], '1:26');
});

// ---- AC-25：時計が戻っても小さくならない ----

test('D0017-AC-25: パネルの時計が基準より前に戻っても、表示は基準（render を受けたときの値）より小さくならない', () => {
  const h = boot(runningView(83));
  h.advance(5000);
  assert.equal(shown(h)[1], '1:28');
  h.setNow(h.now() - 60_000); // スリープ明けや時計の補正で戻った
  h.tick();
  assert.deepEqual(shown(h), ['3:23', '1:23']);
});

test('D0017-AC-25: 時計が戻ったあと visible に戻っても、基準より小さくならない', () => {
  const h = boot(runningView(83));
  h.setVisibility('hidden');
  h.setNow(h.now() - 3_600_000);
  h.setVisibility('visible');
  assert.deepEqual(shown(h), ['3:23', '1:23']);
});

// ---- AC-26：数え上げる要素が無いときは回さない ----

test('D0017-AC-26: 数え上げる要素が 1 つも無い記録では、起動してもタイマーを作らない', () => {
  const h = boot(finishedView());
  assert.equal(h.activeIntervals(), 0);
  assert.equal(h.createdIntervals(), 0);
  h.advance(10_000);
  assert.deepEqual(shown(h), []);
});

test('D0017-AC-26: 数え上げる要素が無い render を受けたら、動いていたタイマーを止める（無駄に回さない）', () => {
  const h = boot(runningView(83));
  assert.equal(h.activeIntervals(), 1, '要素があるあいだは回る');
  render(h, finishedView());
  assert.equal(h.activeIntervals(), 0);
  render(h, runningView(83));
  assert.equal(h.activeIntervals(), 1, '要素が戻ったら回り始める');
});

test('D0017-AC-26: 起動後に数え上げる要素が現れる render を受けたら、そこから回り始める', () => {
  const h = boot(finishedView());
  assert.equal(h.activeIntervals(), 0);
  render(h, waitingView(40));
  assert.equal(h.activeIntervals(), 1);
  h.advance(1000);
  assert.deepEqual(shown(h), ['2:41', '0:41']);
});

// ---- AC-27：拡張へ送るメッセージは増えない ----

test('D0017-AC-27: 数え上げ・render・visibilitychange・戻る矢印の光りのどれでも、拡張へ送るのは ready だけ（守り続ける検査）', () => {
  const h = boot(runningView(83));
  h.advance(30_000);
  render(h, runningView(100));
  h.setVisibility('hidden');
  h.setVisibility('visible');
  h.advance(5000);
  render(h, finishedView());
  render(h, sendBackView(1));
  render(h, sendBackView(2));
  h.loop('send-back').dispatch('animationend');
  assert.deepEqual(h.posted, [{ type: 'ready' }]);
});

test('D0017-AC-27: 送る type は ready・openArtifact・selectRun だけ（成果物・実行のボタンも、数え上げのあと今までどおり）', () => {
  const picker = pickerOf('a');
  const h = boot(runningView(83), {}, picker);
  h.advance(5000);
  h.doc.querySelectorAll('button[data-run]')[1]!.dispatch('click');
  render(h, runningView(90), picker);
  h.setVisibility('hidden');
  h.setVisibility('visible');
  h.doc.querySelectorAll('button[data-run]')[0]!.dispatch('click');
  const types = h.posted.map((m) => (m as { type: string }).type);
  assert.deepEqual(types, ['ready', 'selectRun', 'selectRun']);
  for (const t of types) assert.ok(['ready', 'openArtifact', 'selectRun'].includes(t), t);
  assert.ok(h.activeIntervals() <= 1);
  assert.ok(shown(h).length > 0, '数え上げの要素がある状態で確かめている');
});

// ---- AC-28：選びは数え上げ・render のあとも残る ----

test('D0017-AC-28: 理由の欄の選び・開閉は、数え上げが進んでも、render を受けても残る（時間も正しく数え直される）', () => {
  const view = viewAt(loopSnapshot({ sendBack: 1, running: true }), 83);
  const h = boot(view);
  assert.equal(shown(h)[1], '1:23', '検証が動いていて、経過が出ている');
  clickNode(h, 'implement');
  assert.deepEqual(openIds(h), ['implement']);
  h.advance(3000);
  assert.deepEqual(openIds(h), ['implement']);
  assert.equal(shown(h)[1], '1:26');
  render(h, view);
  assert.deepEqual(openIds(h), ['implement']);
  assert.equal(h.node('implement').getAttribute('aria-pressed'), 'true');
  assert.equal(h.loop('send-back').classList.contains('is-picked'), true);
  assert.equal(shown(h)[1], '1:23', 'render で数え直されている');
});

test('D0017-AC-28: 選べる節にフォーカスがあるとき、数え上げのあとの render でもフォーカスが同じ節に戻る', () => {
  const view = viewAt(loopSnapshot({ sendBack: 1, running: true }), 83);
  const h = boot(view);
  h.node('implement').focus();
  h.advance(2000);
  render(h, view);
  assert.equal(h.doc.activeElement, h.node('implement'));
  assert.equal(shown(h)[1], '1:23');
});

test('D0017-AC-28: 時間の節（data-reasons-for が無い）は、理由の欄の開閉の対象にならず、選んでも閉じても見えたまま', () => {
  const h = boot(finishedView());
  clickNode(h, 'implement');
  const times = h.doc.querySelectorAll('.times');
  assert.ok(times.length >= 1, '時間の節がある');
  for (const t of times) assert.equal(t.hidden, false);
  clickNode(h, 'implement');
  for (const t of times) assert.equal(t.hidden, false);
});

// ---- AC-29：新しく起きた差し戻し・修正だけ光る ----

test('D0017-AC-29: 差し戻しの回数が前の render より増えたとき、その矢印（send-back）にだけ is-new が付く', () => {
  const h = boot(sendBackView(1));
  assert.deepEqual(newLoops(h), []);
  render(h, sendBackView(2));
  assert.deepEqual(newLoops(h), ['send-back']);
});

test('D0017-AC-29: 修正の依頼の回数が増えたとき、その段の戻る矢印（revise:requirements）にだけ is-new が付く', () => {
  const h = boot(reviseView(0));
  render(h, reviseView(1));
  assert.deepEqual(newLoops(h), ['revise:requirements']);
});

test('D0017-AC-29: 差し戻しと修正の依頼が同じ render で増えたら、両方の矢印に付く', () => {
  const h = boot(viewAt(loopSnapshot({ sendBack: 1, revise: 0 })));
  render(h, viewAt(loopSnapshot({ sendBack: 2, revise: 1 })));
  assert.deepEqual(newLoops(h).sort(), ['revise:requirements', 'send-back']);
});

test('D0017-AC-29: 最初の render（読み込み）では、回数がいくつあっても付かない', () => {
  const h = boot(viewAt(loopSnapshot({ sendBack: 2, revise: 2 })));
  assert.deepEqual(newLoops(h), []);
});

test('D0017-AC-29: 回数が同じ render では付かない（守り続ける検査）', () => {
  const h = boot(sendBackView(1));
  render(h, sendBackView(1));
  assert.deepEqual(newLoops(h), []);
});

test('D0017-AC-29: 回数が減った render では付かない', () => {
  const h = boot(sendBackView(2));
  render(h, sendBackView(1));
  assert.deepEqual(newLoops(h), []);
});

test('D0017-AC-29: 増えた render のあとにもう一度同じ render を送っても、別の矢印には付かない（ほかの矢印は光らない）', () => {
  const h = boot(viewAt(loopSnapshot({ sendBack: 1, revise: 1 })));
  render(h, viewAt(loopSnapshot({ sendBack: 2, revise: 1 })));
  assert.deepEqual(newLoops(h), ['send-back']);
});

test('D0017-AC-29: animationend で is-new が外れる（動きが終わったあと光ったまま残らない）', () => {
  const h = boot(sendBackView(1));
  render(h, sendBackView(2));
  assert.equal(isNew(h, 'send-back'), true);
  h.loop('send-back').dispatch('animationend');
  assert.equal(isNew(h, 'send-back'), false);
});

test('D0017-AC-29: animationend は、光っている矢印の中の要素（path）で起きても外れる（イベントは上へ上がる）', () => {
  const h = boot(sendBackView(1));
  render(h, sendBackView(2));
  assert.equal(isNew(h, 'send-back'), true, '光っている');
  const path = h.loop('send-back').children.find((c): c is FakeNode => 'tagName' in c && c.tagName === 'path')!;
  path.dispatch('animationend');
  assert.equal(isNew(h, 'send-back'), false);
});

test('D0017-AC-29: 光り始めから 1.4 秒のあいだに別の render が来ても、is-new は付け直され、光りが途中で切れない', () => {
  const h = boot(sendBackView(1));
  render(h, sendBackView(2));
  h.advance(600);
  render(h, sendBackView(2)); // 同じ回数の render（段のログが増えただけ、など）
  assert.equal(isNew(h, 'send-back'), true);
  h.advance(300);
  render(h, sendBackView(2));
  assert.equal(isNew(h, 'send-back'), true);
});

test('D0017-AC-29: 付け直すときは、経過に合わせて動きを続きから動かす（currentTime が光り始めからの ms）', () => {
  const h = boot(sendBackView(1));
  render(h, sendBackView(2));
  h.advance(600);
  render(h, sendBackView(2));
  const animations = h.loop('send-back').getAnimations!();
  assert.equal(animations.length, 1);
  assert.equal(animations[0].currentTime, 600);
  h.advance(400);
  render(h, sendBackView(2));
  assert.equal(h.loop('send-back').getAnimations!()[0].currentTime, 1000);
});

test('D0017-AC-29: getAnimations が無い環境でも、付け直すだけで例外を投げない', () => {
  const h = boot(sendBackView(1), { noAnimations: true });
  render(h, sendBackView(2));
  h.advance(600);
  render(h, sendBackView(2));
  assert.equal(isNew(h, 'send-back'), true);
  assert.equal(h.loop('send-back').getAnimations, undefined);
});

test('D0017-AC-29: 1.4 秒を過ぎた render では付かない', () => {
  const h = boot(sendBackView(1));
  render(h, sendBackView(2));
  assert.equal(isNew(h, 'send-back'), true, '増えた render では光る');
  h.advance(1500);
  render(h, sendBackView(2));
  assert.equal(isNew(h, 'send-back'), false);
  assert.deepEqual(newLoops(h), []);
});

test('D0017-AC-29: 1.4 秒を過ぎたあとに回数がまた増えたら、新しく起きたものとして付く', () => {
  const h = boot(sendBackView(1));
  render(h, sendBackView(2));
  h.advance(2000);
  render(h, sendBackView(3));
  assert.deepEqual(newLoops(h), ['send-back']);
  assert.equal(h.loop('send-back').getAnimations!()[0].currentTime, 0, '新しい光りは最初から');
});

test('D0017-AC-29: 実行を選び替えた直後の render（回数が違っても別の実行）では付かない', () => {
  const picker = pickerOf;
  const h = boot(sendBackView(1), {}, picker('a'));
  render(h, sendBackView(3), picker('b'));
  assert.deepEqual(newLoops(h), []);
  render(h, sendBackView(4), picker('b'));
  assert.deepEqual(newLoops(h), ['send-back'], '選び替えたあとの次の増加は光る');
});

test('D0017-AC-29: 実行を選び替えたら、前の実行の光りは 1.4 秒以内でも付け直さない', () => {
  const picker = pickerOf;
  const h = boot(sendBackView(1), {}, picker('a'));
  render(h, sendBackView(2), picker('a'));
  assert.deepEqual(newLoops(h), ['send-back']);
  h.advance(300);
  render(h, sendBackView(2), picker('b'));
  assert.deepEqual(newLoops(h), []);
  h.advance(300);
  render(h, sendBackView(2), picker('b'));
  assert.deepEqual(newLoops(h), []);
});

test('D0017-AC-29: 光りは回数の増えた矢印だけで、ほかの節・矢印の印（is-picked など）には触れない', () => {
  const h = boot(sendBackView(1));
  clickNode(h, 'implement');
  render(h, sendBackView(2));
  assert.deepEqual(newLoops(h), ['send-back']);
  assert.equal(h.loop('send-back').classList.contains('is-picked'), true);
  assert.deepEqual(openIds(h), ['implement']);
});

// ---- AC-30：動きを減らす設定 ----

test('D0017-AC-30: prefers-reduced-motion: reduce のとき、数え上げは続く', () => {
  const h = boot(runningView(83), { reducedMotion: true });
  assert.equal(h.activeIntervals(), 1);
  h.advance(5000);
  assert.deepEqual(shown(h), ['3:28', '1:28']);
});

test('D0017-AC-30: reduce のとき、回数が増えても is-new は付かない（動きの設定が違うだけの対照つき）', () => {
  const normal = boot(sendBackView(1));
  render(normal, sendBackView(2));
  assert.deepEqual(newLoops(normal), ['send-back'], '対照：reduce でなければ付く');
  const reduced = boot(sendBackView(1), { reducedMotion: true });
  render(reduced, sendBackView(2));
  assert.deepEqual(newLoops(reduced), []);
  reduced.advance(300);
  render(reduced, sendBackView(2));
  assert.deepEqual(newLoops(reduced), []);
});

test('D0017-AC-30: matchMedia を持たない環境は安全側（動きを減らす）として扱い、is-new は付けず、数え上げは続く', () => {
  const h = boot(runningView(83), { noMatchMedia: true });
  h.advance(2000);
  assert.deepEqual(shown(h), ['3:25', '1:25']);
  const g = boot(sendBackView(1), { noMatchMedia: true });
  render(g, sendBackView(2));
  assert.deepEqual(newLoops(g), []);
});

test('D0017-AC-30: reduce のとき、hidden → visible の差の計算し直しも今までどおり働く', () => {
  const h = boot(runningView(83), { reducedMotion: true });
  h.setVisibility('hidden');
  h.advance(10_000);
  h.setVisibility('visible');
  assert.equal(shown(h)[1], '1:33');
});

// ---- AC-13：スクリプトの書き方は formatDuration と同じ ----

test('D0017-AC-13: スクリプトの書き方が formatDuration と同じ（同じ表を通す：0・7・59・60・83・3599・3600・3725・小数・負）', () => {
  const h = boot(finishedView());
  const spans = DURATION_TABLE.map(([sec]) => `<span class="elapsed" data-elapsed="${sec}">?</span>`).join('');
  h.send({ type: 'render', html: `<p>${spans}</p>` });
  assert.deepEqual(
    shown(h),
    DURATION_TABLE.map(([, want]) => want),
  );
});

test('D0017-AC-13: 数でない data-elapsed は飛ばす（文字を書き換えず、例外も投げない）', () => {
  const h = boot(finishedView());
  h.send({ type: 'render', html: '<p><span class="elapsed" data-elapsed="abc">そのまま</span><span class="elapsed" data-elapsed="83">?</span><span class="elapsed" data-elapsed="">空</span></p>' });
  assert.deepEqual(shown(h), ['そのまま', '1:23', '空']);
  h.advance(2000);
  assert.deepEqual(shown(h), ['そのまま', '1:25', '空']);
});

test('D0017-AC-13: 時間の書き方は、1 秒進むごとの更新でも同じ表のとおり（59 秒 → 1 秒後に 1:00、3599 秒 → 1 秒後に 1:00:00）', () => {
  const h = boot(finishedView());
  h.send({ type: 'render', html: '<p><span data-elapsed="59">?</span><span data-elapsed="3599">?</span></p>' });
  h.advance(1000);
  assert.deepEqual(shown(h), ['1:00', '1:00:00']);
});
