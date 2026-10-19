// パネルの HTML の検査。AC-42（外部の読み込みなし）・AC-43（色はテーマの変数だけ）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderPanelHtml, renderViewBody } from './panelHtml.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { extractCss, hidingInReduce, keyframesInNoPreference, motionOutsideNoPreference, parseCss } from '../test/cssBlocks.ts';
import {
  BASE_AT,
  STARTED_AT,
  finishedView,
  runningSnapshot,
  runningView,
  viewAt,
  waitingSnapshot,
  waitingView,
} from '../test/liveFixtures.ts';
import {
  assistantText,
  assistantTool,
  logText,
  promptLine,
  resultLine,
  snapshot,
  stageRunEntry,
  stateJson,
} from '../test/fixtures.ts';

// 図の状態に入れる文章・ツールの対象には `#` を含めない（設計書「リスクと注意点」：AC-43 のテストの前提）。
function viewWithRecords() {
  return buildPipelineView(
    snapshot({
      stateJson: stateJson({
        runs: [
          stageRunEntry({ stage: 'requirements', seq: 1, numTurns: 10, costUsd: 0.2, durationSec: 30 }),
          { stage: 'requirements', review: 'revise', feedback: '直して' },
          stageRunEntry({ stage: 'requirements', seq: 2, numTurns: 5, costUsd: 0.1, durationSec: 20 }),
          { stage: 'requirements', review: 'approved' },
          stageRunEntry({ stage: 'design', seq: 3, isError: true }),
        ],
        totalCostUsd: 0.3,
      }),
      stageLogs: [
        {
          fileName: '01_requirements.jsonl',
          text: logText([promptLine('requirements'), assistantText('要件を読みます'), resultLine()]),
        },
        {
          fileName: '04_red.jsonl',
          text: logText([
            promptLine('red'),
            assistantTool('Bash', { command: 'npm test' }),
            assistantText('<b>"テスト" & \'書く\'</b>'),
          ]),
        },
      ],
      artifacts: { '00_input.md': 'メモ', '01_requirements.md': '要件', '03_red_tests.md': '  ' },
    }),
  );
}

const views = [
  ['記録のある図の状態', () => viewWithRecords()],
  ['空の図の状態', () => buildPipelineView(snapshot())],
] as const;

for (const [name, make] of views) {
  test(`AC-42: ${name}の HTML に http:・https: で始まる読み込み先がない`, () => {
    const html = renderPanelHtml(make(), 'n');
    assert.ok(html.length > 0);
    assert.doesNotMatch(html, /(src|href)\s*=\s*["']?https?:/i);
    assert.doesNotMatch(html, /url\(\s*["']?https?:/i);
    assert.doesNotMatch(html, /@import/i);
  });

  test(`AC-43: ${name}の HTML に色の直書きがなく、色は var(--vscode- で指定されている`, () => {
    const html = renderPanelHtml(make(), 'n');
    assert.doesNotMatch(html, /#[0-9a-fA-F]{3,8}\b/);
    assert.doesNotMatch(html, /rgba?\(/);
    assert.doesNotMatch(html, /hsla?\(/);
    assert.match(html, /var\(--vscode-/);
  });
}

// ---- D0017：動きと各段の時間 ----

const NONCE = 'n1';
const htmlOf = (view: PipelineView): string => renderPanelHtml(view, NONCE);
const banner = (html: string): string => /<div class="banner">[\s\S]*?<\/div>/.exec(html)?.[0] ?? '';
const count = (text: string, re: RegExp): number => (text.match(re) ?? []).length;

test('D0017-AC-18: 動いている実行のバナーに、全体の経過の要素と、基準の秒（data-elapsed）・初期の文字が入る', () => {
  const b = banner(htmlOf(runningView(83)));
  assert.match(b, /<span class="cost">経過 <span class="elapsed" data-elapsed="203">3:23<\/span>/);
  assert.match(b, /合計 \$0\.000/, '費用は今までどおり');
});

test('D0017-AC-18: 確認待ちの実行のバナーにも、全体の経過の要素（数え上げる印つき）が入る', () => {
  assert.match(banner(htmlOf(waitingView(40))), /<span class="elapsed" data-elapsed="160">2:40<\/span>/);
});

test('D0017-AC-18: 終わった実行のバナーは固定の時間で、数える印（data-elapsed）が付かない', () => {
  const html = htmlOf(finishedView());
  assert.match(banner(html), /<span class="elapsed">7:00<\/span>/);
  // スクリプトは [data-elapsed] を探す文字を持つので、本体（renderViewBody）だけを見る
  assert.doesNotMatch(renderViewBody(finishedView()), /data-elapsed/, '終わった実行には、数え上げる要素がどこにも無い');
});

test('D0017-AC-18: バナーの経過は、基準の秒だけを HTML に入れる（記録の時刻そのものは入れない）', () => {
  const html = htmlOf(runningView(83));
  assert.doesNotMatch(html, /2026-10-17T/, 'パネルは記録の時刻と今の時刻を比べない');
});

// at・since が無い記録（古い版）。節の並び・状態は変えず、時間の要素・動きの印は出さない
const OLD_TIME_VIEWS: [string, () => PipelineView][] = [
  ['動いている段のログに at が無い', () => viewAt(runningSnapshot({ omitAt: true }), 83)],
  ['確認待ちに since が無い', () => viewAt(waitingSnapshot({ omitSince: true }), 40)],
  ['at が壊れている', () => viewAt(runningSnapshot({ at: 'x' }), 83)],
  ['since が壊れている', () => viewAt(waitingSnapshot({ since: 5 }), 40)],
];
for (const [label, make] of OLD_TIME_VIEWS) {
  test(`D0017-AC-19: ${label}記録では、数え上げの要素も点滅・点の流れの印も出ない（今の作りでも通る守り）`, () => {
    // CSS とスクリプトは data-elapsed・is-flowing などの文字を持つので、本体（renderViewBody）だけを見る。
    // 本体のバナーは「確認待ち」のとき class="banner-msg is-waiting" を持つので、節の印は <g class="node …"> で見る
    const body = renderViewBody(make());
    for (const token of ['data-elapsed', 'is-flowing', 'node-wait', 'class="elapsed"']) {
      assert.ok(!body.includes(token), `${token} が出ていない`);
    }
    assert.doesNotMatch(body, /<g class="node [^"]*\bis-waiting\b/, '節に点滅の印が付いていない');
  });
}

test('D0017-AC-19: 時間の印が無い記録でも、節の数・並び・状態は 11 個のまま（時間が付く記録と同じ）', () => {
  const old = renderViewBody(viewAt(runningSnapshot({ omitAt: true }), 83));
  const live = renderViewBody(runningView(83));
  const nodes = (html: string) => [...html.matchAll(/<g class="node (is-[a-z]+)[^"]*" data-node="([^"]+)"/g)].map((m) => `${m[2]}:${m[1]}`);
  assert.equal(count(old, /<g class="node /g), 11);
  assert.deepEqual(nodes(old), nodes(live));
});

test('D0017-AC-20: 動き（animation・@keyframes）はすべて no-preference の @media の中にあり、外には無い', () => {
  const css = extractCss(htmlOf(runningView(83)));
  assert.deepEqual(motionOutsideNoPreference(css), []);
});

test('D0017-AC-20: no-preference の中に、脈打ち・点の流れ・点滅・光りの4つの @keyframes がある', () => {
  const css = extractCss(htmlOf(runningView(83)));
  assert.deepEqual(keyframesInNoPreference(css).sort(), ['attention', 'flash', 'flow', 'pulse']);
});

test('D0017-AC-20: reduce の @media に、時間の要素（elapsed・node-wait）を隠す・消す規則が無い', () => {
  const css = extractCss(htmlOf(runningView(83)));
  assert.deepEqual(hidingInReduce(css), []);
});

test('D0017-AC-20: 状態は動きに頼らない：待ちの節の枠と文字の色は、@media の外の静的な規則で決まる', () => {
  const css = extractCss(htmlOf(waitingView(40)));
  const rules = parseCss(css).filter((r) => r.media === null && !r.keyframes);
  const waiting = rules.filter((r) => /is-waiting/.test(r.selector));
  assert.ok(waiting.length >= 1, '.is-waiting の静的な規則がある');
  assert.ok(waiting.some((r) => /--vscode-charts-yellow/.test(r.body)), '待ちは黄の色（バナーの「確認を待っている」と同じ）');
  assert.ok(rules.some((r) => /node-wait/.test(r.selector)), '.node-wait の文字の色の静的な規則がある');
  assert.ok(rules.some((r) => /\.elapsed/.test(r.selector)), '.elapsed の文字の色の静的な規則がある');
});

test('D0017-AC-20: 検査そのものが違反を見つける：外の animation・reduce の中の animation・外の @keyframes', () => {
  assert.deepEqual(motionOutsideNoPreference('.a { animation: x 1s infinite; }').length, 1);
  assert.deepEqual(motionOutsideNoPreference('@keyframes x { 50% { opacity: 0.3; } }').length, 1);
  assert.deepEqual(motionOutsideNoPreference('@media (prefers-reduced-motion: reduce) { .a { animation: x 1s; } }').length, 1);
  assert.deepEqual(motionOutsideNoPreference('@media (max-width: 640px) { .a { animation: x 1s; } }').length, 1);
  assert.deepEqual(motionOutsideNoPreference('@media (prefers-reduced-motion: no-preference) { .a { animation: x 1s; } @keyframes x { 50% { opacity: 0.3; } } }'), []);
  assert.deepEqual(hidingInReduce('@media (prefers-reduced-motion: reduce) { .elapsed { display: none; } }').length, 1);
  assert.deepEqual(hidingInReduce('@media (prefers-reduced-motion: reduce) { .a { animation: none; } }'), []);
});

for (const [label, make] of [
  ['動いている', () => runningView(83)],
  ['確認待ち', () => waitingView(40)],
  ['終わった', () => finishedView()],
] as const) {
  test(`D0017-AC-21: ${label}実行の HTML に style 属性・on…= のイベント属性・外部の読み込みが無く、色は直書きでない`, () => {
    const html = htmlOf(make());
    // style 属性・イベント属性は、タグの中だけを見る（スクリプトと CSS の中の文字には反応させない）
    const markup = html.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<style[\s\S]*?<\/style>/g, '');
    assert.doesNotMatch(markup, /\sstyle\s*=/i);
    assert.doesNotMatch(markup, /<[a-z][^>]*\son[a-z]+\s*=/i);
    assert.doesNotMatch(html, /(src|href)\s*=\s*["']?https?:/i);
    assert.doesNotMatch(html, /url\(\s*["']?https?:/i);
    assert.doesNotMatch(html, /@import/i);
    for (const re of [/#[0-9a-fA-F]{3,8}\b/, /rgba?\(/, /hsla?\(/]) assert.doesNotMatch(html, re);
    assert.match(html, /var\(--vscode-/);
    assert.doesNotMatch(html, /<script(?![^>]*nonce=)/);
  });

  test(`D0017-AC-21: ${label}実行の CSP は今のまま（default-src 'none'; style-src 'nonce-…'; script-src 'nonce-…'）`, () => {
    const html = htmlOf(make());
    assert.match(html, new RegExp(`content="default-src 'none'; style-src 'nonce-${NONCE}'; script-src 'nonce-${NONCE}';"`));
  });
}

const EVIL = '<script>alert(1)</script>"&\'';
const evilPipeView = (kind: 'running' | 'waiting'): PipelineView => {
  const stages = [{ name: 'draw', label: EVIL, output: 'a.md', review: true }];
  const draw = (seq: number) => stageRunEntry({ stage: 'draw', seq, durationSec: 20 });
  const snap =
    kind === 'running'
      ? snapshot({
          stateJson: stateJson({ pipe: 'p', stages, runs: [draw(1)], startedAt: STARTED_AT }),
          stageLogs: [{ fileName: '02_draw_2.jsonl', text: logText([promptLine('draw', BASE_AT)]) }],
        })
      : snapshot({
          stateJson: stateJson({
            pipe: 'p',
            stages,
            runs: [draw(1), { stage: 'draw', review: 'revise', feedback: 'f' }, draw(2)],
            pendingReview: { stage: 'draw', doc: 'a.md', session_id: 's', since: BASE_AT },
            startedAt: STARTED_AT,
          }),
        });
  return viewAt(snap, 30);
};

for (const kind of ['running', 'waiting'] as const) {
  test(`D0017-AC-21: 段の名前・ラベルの <script>・"・& は、時間の要素を含む出力（${kind}）でもエスケープされる`, () => {
    const html = htmlOf(evilPipeView(kind));
    assert.ok(!html.includes('<script>alert'), '生の <script> が入っていない');
    assert.ok(!html.includes('alert(1)</script>'));
    assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt;'), 'エスケープされた形で出ている');
    assert.equal(count(html, /<script\b/g), 1, '本物のスクリプトの <script> だけ');
    assert.ok(renderViewBody(evilPipeView(kind)).includes('data-elapsed='), '時間の要素つきの出力で確かめている');
  });
}

test('D0017-AC-18: 右の欄は 注意 → 理由 → 時間 → 出力 → 成果物 の順で、時間の節は理由の欄のあとにある', () => {
  const html = htmlOf(finishedView());
  const times = html.indexOf('class="times"');
  assert.ok(times > 0, '時間の節がある');
  assert.ok(html.indexOf('data-reasons-for="') > 0, '理由の欄がある');
  assert.ok(times > html.indexOf('data-reasons-for="'), '理由の欄のあと');
  assert.ok(times < html.indexOf('>出力'), '出力の前');
  assert.ok(times < html.indexOf('>成果物<'), '成果物の前');
});

test('D0017-AC-18: 時間の節は常に見える：data-reasons-for も hidden も付かず、理由の開け閉めの対象にならない', () => {
  const section = /<section class="times">[\s\S]*?<\/section>/.exec(htmlOf(finishedView()))?.[0] ?? '';
  assert.ok(section.length > 0);
  assert.doesNotMatch(section, /data-reasons-for|hidden/);
});

test('D0006-AC-21: パネルの title は pipe-in', () => {
  for (const [, make] of views) {
    const html = renderPanelHtml(make(), 'n');
    assert.equal(/<title>(.*?)<\/title>/.exec(html)?.[1], 'pipe-in');
    assert.deepEqual(html.match(new RegExp('.{0,20}dev' + 'pipe.{0,20}', 'gi')) ?? [], []);
  }
});
