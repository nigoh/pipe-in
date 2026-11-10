// reply.json は予約名（D0079・AC-66）：パイプの段の output に reply.json は使えない。本体の check_pipe（pipe_in/pipe/definition.py の RESERVED_OUTPUTS）と、
// 拡張の validatePipe（domain/pipeModel.ts の RESERVED_OUTPUTS の写し）の両方が、理由つき（「本体が書くファイル」）で断る。reply.json.bak など別の名前は断らない。
// 共通の見本（tests/fixtures/check_parity/err-output-reserved）は app/pipeCheckParity.test.ts と tests/test_check_parity.py が同じものを読む（見本の直しだけで通る）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { END, newPipe, newStage, validatePipe } from './pipeModel.ts';
import type { PipeModel } from './pipeModel.ts';

/** 段が 1 つで、output を決めたパイプ（ほかは正しい） */
function pipeWith(output: string): PipeModel {
  const m = newPipe('reply-demo');
  m.stages = [{ ...newStage('a', 'research', 'a'), prompt: '調べる', output, next: END, x: 100, y: 100 }];
  m.start = { x: -200, y: 110 };
  m.end = { x: 600, y: 110 };
  return m;
}
const reservedErrors = (output: string): string[] => validatePipe(pipeWith(output)).errors.filter((e) => e.includes('本体が書くファイル'));

test('D0079-AC-66: output = "reply.json" の段は、validatePipe が「本体が書くファイル」の理由つきで断る', () => {
  const errors = reservedErrors('reply.json');
  assert.equal(errors.length, 1);
  assert.match(errors[0]!, /reply\.json/);
  assert.match(errors[0]!, /使えません/);
});

test('D0079-AC-66: reply.json.bak・reply.jsonl・my-reply.json・reply_json など別の名前は、予約名として断らない（今のまま通る。守る）', () => {
  for (const output of ['reply.json.bak', 'reply.jsonl', 'my-reply.json', 'reply_json', 'reply.md', '01_reply.json']) {
    assert.deepEqual(reservedErrors(output), [], output);
  }
});

test('D0079-AC-66: 今までの予約名（00_input.md・99_summary.md・state.json）も、同じ理由で断る（今のまま通る。守る）', () => {
  for (const output of ['00_input.md', '99_summary.md', 'state.json']) {
    assert.equal(reservedErrors(output).length, 1, output);
  }
});

test('D0079-AC-66: output が正しい名前（01_survey.md）のパイプは、予約名の誤りが無い（今のまま通る。守る）', () => {
  assert.deepEqual(reservedErrors('01_survey.md'), []);
  assert.deepEqual(validatePipe(pipeWith('01_survey.md')).errors, []);
});

test('D0079-AC-66: reply.json 以外の誤りは 1 件も増えない：output が reply.json の段の誤りは、予約名の 1 件だけ', () => {
  assert.equal(validatePipe(pipeWith('reply.json')).errors.length, 1);
});

test('D0079-AC-66: 大文字だけ違う名前（Reply.json）は、予約名の比べ方を変えないので断らない（00_input.md なども同じ。今の守りの限界）（今のまま通る。守る）', () => {
  assert.deepEqual(reservedErrors('Reply.json'), []);
  assert.deepEqual(reservedErrors('STATE.JSON'), []);
});
