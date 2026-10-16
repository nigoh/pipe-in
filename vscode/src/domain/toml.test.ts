// pipe.toml を読む小さな TOML の読み手（devpipe のパイプで使う書き方だけ）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { TomlError, parseToml } from './toml.ts';

test('AC-21: 表・表の配列・その下の表・文字列・数・真偽・配列を読む', () => {
  const doc = parseToml(`# コメント
[pipe]
kind = "linear"
label = "図を作る"   # 行末のコメント
max_steps = 30

[[stages]]
name = "survey"
review = true
writes = ["docs/a/**", 'docs/b.md']
max_budget_usd = 0.5
[stages.check]
verdict = true
on_fail = "survey"

[[stages]]
name = "draw"
[stages.routes]
api = "a"
"日本語" = "end"
`);
  const pipe = doc.pipe as Record<string, unknown>;
  assert.equal(pipe.kind, 'linear');
  assert.equal(pipe.label, '図を作る');
  assert.equal(pipe.max_steps, 30);
  const stages = doc.stages as Record<string, unknown>[];
  assert.equal(stages.length, 2);
  assert.equal(stages[0]!.review, true);
  assert.deepEqual(stages[0]!.writes, ['docs/a/**', 'docs/b.md']);
  assert.equal(stages[0]!.max_budget_usd, 0.5);
  assert.deepEqual(stages[0]!.check, { verdict: true, on_fail: 'survey' });
  assert.deepEqual(stages[1]!.routes, { api: 'a', 日本語: 'end' });
});

test('AC-21: 文字列のエスケープと、複数行の文字列', () => {
  const doc = parseToml('a = "x\\"y\\\\z\\n\\u3042"\nb = """\n一行目\n二行目"""\nc = \'\'\'\nC:\\raw\'\'\'\nd = [\n  "x",\n  "y",\n]\n');
  assert.equal(doc.a, 'x"y\\z\nあ');
  assert.equal(doc.b, '一行目\n二行目');
  assert.equal(doc.c, 'C:\\raw');
  assert.deepEqual(doc.d, ['x', 'y']);
});

test('AC-21: 読めない書き方は行番号つきで知らせる', () => {
  assert.throws(() => parseToml('a = { b = 1 }\n'), (e: unknown) => e instanceof TomlError && /1 行目/.test(e.message));
  assert.throws(() => parseToml('a = 1\na = 2\n'), (e: unknown) => e instanceof TomlError && /2 行目/.test(e.message));
  assert.throws(() => parseToml('a = "閉じていない\n'), TomlError);
  assert.throws(() => parseToml('[pipe\n'), TomlError);
});
