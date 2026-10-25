// 確認待ちの知らせの文（D0044）。AC-08・09。外から来た文字（セッション名・段）は plainLine と同じ規則で整える。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SHOW_RUN_LABEL, waitingNoticeText } from './waitNotice.ts';
import { plainLine } from './statusBar.ts';

const r = (session: string, stage: string): { session: string; stage: string } => ({ session, stage });

/** コードポイントの番号から文字を作る（ソースに特殊な文字を直に書かない） */
const ch = (...codes: number[]): string => String.fromCharCode(...codes);

/** 1 行のプレーンな文字でないものが残っているか：改行を含む制御文字・行区切り・段落区切り・向きを変える制御文字 */
function hasUnsafe(text: string): boolean {
  return Array.from(text).some((c) => {
    const n = c.codePointAt(0) ?? 0;
    return n <= 0x1f || (n >= 0x7f && n <= 0x9f) || n === 0x2028 || n === 0x2029 || n === 0x200e || n === 0x200f || (n >= 0x202a && n <= 0x202e) || (n >= 0x2066 && n <= 0x2069);
  });
}

test('D0044-AC-08: ボタンの文字は「実行を見る」', () => {
  assert.equal(SHOW_RUN_LABEL, '実行を見る');
});

test('D0044-AC-08: 0件は null', () => {
  assert.equal(waitingNoticeText([]), null);
});

test('D0044-AC-08: 1件は「<セッション名>（<段>）が確認待ちです」', () => {
  assert.equal(waitingNoticeText([r('通知を足す', '設計')]), '通知を足す（設計）が確認待ちです');
});

test('D0044-AC-08: 2件以上は「確認待ちの実行が N 件になりました」で、名前を並べない', () => {
  const two = waitingNoticeText([r('名前A', '設計'), r('名前B', '実装')]);
  assert.equal(two, '確認待ちの実行が 2 件になりました');
  const three = waitingNoticeText([r('名前A', '設計'), r('名前B', '実装'), r('名前C', '検証')]);
  assert.equal(three, '確認待ちの実行が 3 件になりました');
  assert.ok(!two?.includes('名前A'));
});

const HOSTILE: readonly [string, string][] = [
  ['改行', 'a\nb\r\nc'],
  ['制御文字', `x${ch(0)}y${ch(0x1b)}z${ch(0x7f)}`],
  ['$(zap)', '$(zap)'],
  ['<script>', '<script>alert(1)</script>'],
  ['1万文字', 'あ'.repeat(10000)],
  ['向きを変える文字と行区切り', `a${ch(0x202e)}b${ch(0x2066)}c${ch(0x2028)}d${ch(0x2029)}e`],
];

for (const [label, text] of HOSTILE) {
  test(`D0044-AC-09: セッション名に ${label} を入れても、1 行のプレーンな文字で、plainLine と同じになる`, () => {
    const out = waitingNoticeText([r(text, '設計')]);
    assert.notEqual(out, null);
    assert.equal(out, `${plainLine(text)}（${plainLine('設計')}）が確認待ちです`);
    assert.ok(!hasUnsafe(out!), '制御文字が残っていない');
    assert.ok(plainLine(text).length <= 60, '名前は 60 文字まで');
  });

  test(`D0044-AC-09: 段に ${label} を入れても、1 行のプレーンな文字で、plainLine と同じになる`, () => {
    const out = waitingNoticeText([r('名前', text)]);
    assert.notEqual(out, null);
    assert.equal(out, `名前（${plainLine(text)}）が確認待ちです`);
    assert.ok(!hasUnsafe(out!), '制御文字が残っていない');
  });
}

test('D0044-AC-09: 検査の見本：hasUnsafe は改行・制御文字・行区切り・向きを変える文字を見つけ、ふつうの文字は見逃す', () => {
  for (const bad of ['a\nb', `a${ch(0)}`, `a${ch(0x2028)}`, `a${ch(0x202e)}`, `a${ch(0x2069)}`]) assert.ok(hasUnsafe(bad), JSON.stringify(bad));
  assert.ok(!hasUnsafe('通知を足す（設計） $(zap) <script>'));
});

test('D0044-AC-09: 2件以上の文には、外から来た文字が入らない', () => {
  const out = waitingNoticeText([r('<script>', '$(zap)'), r('x\ny', 'z')]);
  assert.equal(out, '確認待ちの実行が 2 件になりました');
});

test('D0044-AC-09: セッション名・段が空でも、文は作れて例外を出さない', () => {
  assert.equal(waitingNoticeText([r('', '')]), `${plainLine('')}（${plainLine('')}）が確認待ちです`);
});
