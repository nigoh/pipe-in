// 時間の書き方（D0017）：m:ss、1時間以上は h:mm:ss。duration.ts はテスト先行の時点でまだ無いので、テストの中で読み込む。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DURATION_TABLE } from '../test/liveFixtures.ts';

const load = () => import('./duration.ts');

for (const [sec, want] of DURATION_TABLE) {
  test(`D0017-AC-13: ${sec} 秒は ${want}`, async () => {
    const { formatDuration } = await load();
    assert.equal(formatDuration(sec), want);
  });
}

for (const [label, value] of [['NaN', Number.NaN], ['Infinity', Number.POSITIVE_INFINITY], ['-Infinity', Number.NEGATIVE_INFINITY], ['-0.5', -0.5]] as const) {
  test(`D0017-AC-13: 読めない・負の値（${label}）は 0:00 に丸める`, async () => {
    const { formatDuration } = await load();
    assert.equal(formatDuration(value), '0:00');
  });
}

test('D0017-AC-13: 文字・null・undefined のような数でない値が来ても例外を投げず 0:00', async () => {
  const { formatDuration } = await load();
  for (const bad of ['83', null, undefined, {}, []]) {
    assert.equal(formatDuration(bad as unknown as number), '0:00', JSON.stringify(bad));
  }
});
