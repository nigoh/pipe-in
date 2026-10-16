// 検証の段で足した画面（純粋関数）とパネルとの受け渡しのテスト。AC-42・AC-43・FR-11・非機能（注入）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { escapeHtml, renderPanelHtml, renderViewBody } from './panelHtml.ts';
import { parseWebviewMessage } from './messages.ts';
import { buildPipelineView } from '../domain/pipelineView.ts';
import {
  assistantText,
  assistantTool,
  logText,
  promptLine,
  snapshot,
  stageRunEntry,
  stateJson,
} from '../test/fixtures.ts';

const EXTERNAL = [/(src|href)\s*=\s*["']?https?:/i, /url\(\s*["']?https?:/i, /@import/i];
const HARD_COLORS = [/#[0-9a-fA-F]{3,8}\b/, /rgba?\(/, /hsla?\(/];

function assertClean(html: string, label: string) {
  for (const re of EXTERNAL) assert.doesNotMatch(html, re, `${label}: ${re}`);
  for (const re of HARD_COLORS) assert.doesNotMatch(html, re, `${label}: ${re}`);
  assert.match(html, /var\(--vscode-/, label);
}

test('AC-42/43 追加: 待ち・最終の結果（PASSED／失敗）・記録なしの各図の状態でも外部の読み込みと色の直書きがない', () => {
  const views = {
    waiting: buildPipelineView(snapshot({ stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }) })),
    passed: buildPipelineView(snapshot({ stateJson: stateJson({ final: 'PASSED', totalCostUsd: 1.25 }) })),
    failed: buildPipelineView(snapshot({ stateJson: stateJson({ final: 'TEST_FAILED' }) })),
    noRecords: buildPipelineView(snapshot({ workDir: 'D:/repo/docs-internal/pipeline' })),
    allArtifacts: buildPipelineView(
      snapshot({
        artifacts: {
          '00_input.md': 'a',
          '01_requirements.md': 'a',
          '02_design.md': 'a',
          '03_red_tests.md': 'a',
          '04_implementation.md': 'a',
          '05_test_report.md': 'a',
          '99_summary.md': 'a',
        },
      }),
    ),
  };
  for (const [label, view] of Object.entries(views)) assertClean(renderPanelHtml(view, 'abc123=='), label);
});

test('AC-42 追加: CSP は default-src none で、外部の読み込み先を許さない（https: も cspSource も入れない）', () => {
  const html = renderPanelHtml(buildPipelineView(snapshot()), 'NONCE');
  const csp = /http-equiv="Content-Security-Policy" content="([^"]*)"/.exec(html);
  assert.ok(csp, 'CSP がある');
  assert.match(csp[1], /default-src 'none'/);
  assert.doesNotMatch(csp[1], /https?:/);
  assert.match(csp[1], /script-src 'nonce-NONCE'/);
  // スクリプト・スタイルには nonce が付く
  assert.match(html, /<script nonce="NONCE">/);
  assert.match(html, /<style nonce="NONCE">/);
  assert.doesNotMatch(html, /<script(?![^>]*nonce=)/);
});

test('非機能（注入）: ログの文章とツールの対象は escapeHtml を通り、生のタグ・外部の読み込みにならない', () => {
  const evil = '<script src="https://evil.example/x.js"></script><img src=https://evil.example/a.png>';
  const view = buildPipelineView(
    snapshot({
      stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })] }),
      stageLogs: [
        {
          fileName: '02_design.jsonl',
          text: logText([promptLine('design'), assistantText(evil), assistantTool('Bash', { command: evil })]),
        },
      ],
    }),
  );
  const body = renderViewBody(view);
  assert.doesNotMatch(body, /<script/i);
  assert.doesNotMatch(body, /<img/i);
  assert.match(body, /&lt;script src=&quot;https:\/\/evil\.example/);
  assert.match(body, /&lt;img src=https:/);
  // 文字としての「src=https:」は本文に残る（AC-42 の文字列検査の前提外。設計書「リスクと注意点」の # と同じ扱い）。
  // 読み込み先になる生のタグの属性がないことを確かめる。
  assert.doesNotMatch(body, /<[a-z]+[^>]*\s(src|href)\s*=/i);
});

test('非機能（注入）: work_dir のパスと final の値も escapeHtml を通る', () => {
  const noRec = renderViewBody(buildPipelineView(snapshot({ workDir: '<b>dir</b>' })));
  assert.doesNotMatch(noRec, /<b>dir/);
  assert.match(noRec, /記録がありません/);
  assert.match(noRec, /&lt;b&gt;dir/);
  const fin = renderViewBody(buildPipelineView(snapshot({ stateJson: stateJson({ final: '<i>X</i>' }) })));
  assert.doesNotMatch(fin, /<i>X/);
});

test('escapeHtml: & < > " \' を名前の文字参照にし、数値の文字参照（&#）を使わない', () => {
  assert.equal(escapeHtml(`&<>"'`), '&amp;&lt;&gt;&quot;&apos;');
  assert.doesNotMatch(escapeHtml(`'"<>&`), /&#/);
  assert.equal(escapeHtml('普通の文'), '普通の文');
});

test('FR-13/14 追加: 待ちの表示・記録なしの表示・合計の費用の文言が本体に出る', () => {
  const waiting = renderViewBody(
    buildPipelineView(snapshot({ stateJson: stateJson({ runs: [stageRunEntry({ stage: 'requirements', seq: 1 })], totalCostUsd: 1.25 }) })),
  );
  assert.match(waiting, /次を待っている（人の確認かもしれない）/);
  assert.match(waiting, /\$1\.250/);
  const noRec = renderViewBody(buildPipelineView(snapshot({ workDir: '/w/docs-internal/pipeline' })));
  assert.match(noRec, /記録がありません/);
  assert.match(noRec, /\/w\/docs-internal\/pipeline/);
});

test('FR-08/10 追加: 修正の依頼・差し戻しの回数と段の数値が本体に出る', () => {
  const body = renderViewBody(
    buildPipelineView(
      snapshot({
        stateJson: stateJson({
          runs: [
            { stage: 'requirements', review: 'revise', feedback: 'a' },
            { stage: 'requirements', review: 'revise', feedback: 'b' },
            stageRunEntry({ stage: 'implement', seq: 1, attempt: 1, numTurns: 10, costUsd: 0.2, durationSec: 30 }),
            stageRunEntry({ stage: 'implement', seq: 2, attempt: 2, numTurns: 5, costUsd: 0.1, durationSec: 20 }),
            stageRunEntry({ stage: 'implement', seq: 3, attempt: 3 }),
          ],
        }),
      }),
    ),
  );
  assert.match(body, /修正の依頼 2 回/);
  assert.match(body, /差し戻し 2 回/);
  assert.match(body, /16 ターン・\$0\.300・50s/);
});

test('FR-06 追加: 節の状態は文字でも出て、状態ごとにクラス（色）が分かれる', () => {
  const body = renderViewBody(
    buildPipelineView(
      snapshot({
        stateJson: stateJson({
          runs: [stageRunEntry({ stage: 'requirements', seq: 1 }), stageRunEntry({ stage: 'design', seq: 2, isError: true })],
        }),
        stageLogs: [{ fileName: '03_red.jsonl', text: logText([promptLine('red')]) }],
      }),
    ),
  );
  for (const [cls, label] of [
    ['is-done', '完了'],
    ['is-failed', '失敗'],
    ['is-running', '動いている'],
    ['is-pending', 'まだ'],
  ]) {
    assert.match(body, new RegExp(`class="node ${cls}"`), cls);
    assert.match(body, new RegExp(`class="node-status"[^>]*>[^<]*${label}</text>`), label);
  }
  assert.equal((body.match(/<g class="node /g) ?? []).length, 11);
});

test('FR-11 追加: 「ある」成果物だけが押せるボタン（data-artifact）、「まだない」は disabled', () => {
  const body = renderViewBody(buildPipelineView(snapshot({ artifacts: { '01_requirements.md': 'x', '03_red_tests.md': ' ' } })));
  assert.match(body, /data-artifact="01_requirements\.md"/);
  assert.equal((body.match(/data-artifact=/g) ?? []).length, 1);
  assert.equal((body.match(/disabled/g) ?? []).length, 6);
});

test('FR-09 追加: ターミナル風の出力はツールを「· ツール名 対象」、文章をそのまま、行の順に出す', () => {
  const body = renderViewBody(
    buildPipelineView(
      snapshot({
        stageLogs: [
          {
            fileName: '01_requirements.jsonl',
            text: logText([promptLine('requirements'), assistantTool('Read', { file_path: 'a.md' }), assistantText('読みました')]),
          },
        ],
      }),
    ),
  );
  const i = body.indexOf('· Read a.md');
  const j = body.indexOf('読みました');
  assert.ok(i >= 0 && j > i, 'ツール → 文章の順');
});

test('パネルとの受け渡し: 知らない形の値は null', () => {
  assert.deepEqual(parseWebviewMessage({ type: 'ready' }), { type: 'ready' });
  assert.deepEqual(parseWebviewMessage({ type: 'openArtifact', name: '01_requirements.md' }), {
    type: 'openArtifact',
    name: '01_requirements.md',
  });
  for (const v of [null, undefined, 1, 'ready', [], {}, { type: 'openArtifact' }, { type: 'openArtifact', name: 1 }, { type: 'x' }]) {
    assert.equal(parseWebviewMessage(v), null, JSON.stringify(v));
  }
});
