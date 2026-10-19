// 時刻の読み方（D0017）：記録の時刻の文字を、ミリ秒と経過秒にする。純粋（時計に触れない）。
// timestamp.ts はテスト先行の時点でまだ無いので、テストの中で読み込む（呼んだところで落ちる）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BASE_MS } from '../test/liveFixtures.ts';

const load = () => import('./timestamp.ts');

test('D0017-AC-11: Z・+09:00・+0900・-05:00 の時刻を、同じ瞬間のミリ秒として読める', async () => {
  const ts = await load();
  const same: [string, number][] = [
    ['2026-10-17T10:00:00Z', 0],
    ['2026-10-17T10:00:00+00:00', 0],
    ['2026-10-17T19:00:00+09:00', 0],
    ['2026-10-17T19:00:00+0900', 0],
    ['2026-10-17T05:00:00-05:00', 0],
    ['2026-10-17T10:00:00Z', 540], // オフセットがあれば、手元のずれは使わない
  ];
  for (const [text, localOffsetMin] of same) assert.equal(ts.parseInstant(text, localOffsetMin), BASE_MS, `${text} / ${localOffsetMin}`);
});

test('D0017-AC-11: 小数秒つきの時刻も読める（秒としては同じ瞬間）', async () => {
  const ts = await load();
  const ms = ts.parseInstant('2026-10-17T10:00:00.789Z', 0);
  assert.ok(ms !== null);
  assert.equal(Math.floor(ms / 1000), BASE_MS / 1000);
  const ms2 = ts.parseInstant('2026-10-17T19:00:00.5+09:00', 0);
  assert.ok(ms2 !== null);
  assert.equal(Math.floor(ms2 / 1000), BASE_MS / 1000);
});

test('D0017-AC-11: オフセットの無い時刻は、渡した手元のずれ（分）で読む。同じ瞬間なら、あってもなくても同じ', async () => {
  const ts = await load();
  assert.equal(ts.parseInstant('2026-10-17T10:00:00', 0), BASE_MS);
  assert.equal(ts.parseInstant('2026-10-17T19:00:00', 540), BASE_MS); // 手元が +09:00
  assert.equal(ts.parseInstant('2026-10-17T05:00:00', -300), BASE_MS); // 手元が -05:00
  assert.equal(ts.parseInstant('2026-10-17T19:00:00', 540), ts.parseInstant('2026-10-17T19:00:00+09:00', 0));
});

test('D0017-AC-32: 壊れた時刻（形が違う・存在しない日付・空）は null で、例外を投げない', async () => {
  const ts = await load();
  for (const bad of ['', 'x', '2026', '2026-10-17', '2026-02-30T10:00:00', '2026-13-01T10:00:00', '2026-10-32T10:00:00', '2026-10-17T25:00:00', '2026-10-17T10:61:00', 'ten o\'clock', '２０２６-10-17T10:00:00']) {
    assert.equal(ts.parseInstant(bad, 0), null, JSON.stringify(bad));
    assert.equal(ts.isTimestampText(bad), false, JSON.stringify(bad));
  }
});

test('D0017-AC-32: うるう日は読め（2028-02-29）、うるう年でない 2027-02-29 は null', async () => {
  const ts = await load();
  assert.notEqual(ts.parseInstant('2028-02-29T00:00:00Z', 0), null);
  assert.equal(ts.parseInstant('2027-02-29T00:00:00Z', 0), null);
});

test('D0017-AC-32: isTimestampText は文字でない値（数・オブジェクト・null・配列・真偽）を false にする', async () => {
  const ts = await load();
  for (const bad of [0, 1.5, 1792230000, {}, { a: 1 }, null, undefined, [], ['2026-10-17T10:00:00Z'], true]) {
    assert.equal(ts.isTimestampText(bad), false, JSON.stringify(bad));
  }
  for (const ok of ['2026-10-17T10:00:00', '2026-10-17T10:00:00+09:00', '2026-10-17T10:00:00Z', '2026-10-17T10:00:00.123456']) {
    assert.equal(ts.isTimestampText(ok), true, ok);
  }
});

test('D0017-AC-11: elapsedSec は切り捨てで、負にならない（未来の時刻は 0 秒）', async () => {
  const ts = await load();
  assert.equal(ts.elapsedSec(BASE_MS, BASE_MS + 83_000), 83);
  assert.equal(ts.elapsedSec(BASE_MS, BASE_MS + 83_999), 83);
  assert.equal(ts.elapsedSec(BASE_MS, BASE_MS), 0);
  assert.equal(ts.elapsedSec(BASE_MS + 5000, BASE_MS), 0);
  assert.equal(ts.elapsedSec(BASE_MS + 1, BASE_MS), 0);
});
