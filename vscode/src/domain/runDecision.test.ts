// 作業台から流してよいかの判断（D0078。domain/runDecision.ts）。AC-10〜20・49 の支え。
// 理由の文は丸ごとは比べない（言い回しで実装を縛らない）。block の種類と、要点の語（保存・実行中・信頼・4,000 など）で確かめる。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { decideRun, readRunContext, RUN_BLOCK_ORDER } from './runDecision.ts';
import type { RunBlock, RunContext } from './runDecision.ts';
import type { InputMode } from './pipeModel.ts';

const PIPE_DIR = '/work/app/.pipe-in/pipes/pipe-in-p';

function ctx(over: Partial<RunContext> = {}): RunContext {
  return { input: 'required', pipeDir: PIPE_DIR, savedErrors: 0, project: '/work/app', trusted: true, executable: { ok: true, path: '/usr/local/bin/pipe-in' }, running: false, ...over };
}

function blockOf(c: RunContext, dirty: boolean, text: string): RunBlock | null {
  const d = decideRun(c, dirty, text);
  return d.ok ? null : d.block;
}

function reasonOf(c: RunContext, dirty: boolean, text: string): string {
  const d = decideRun(c, dirty, text);
  assert.equal(d.ok, false);
  return d.ok ? '' : d.reason;
}

// ---- AC-20：順と ok ----

test('D0078-AC-20: RUN_BLOCK_ORDER は設計 §3 の表の順', () => {
  assert.deepEqual([...RUN_BLOCK_ORDER], ['untrusted', 'noProject', 'noExecutable', 'running', 'notSaved', 'dirty', 'invalid', 'textEmpty', 'textTooLong', 'textNul', 'textBroken']);
});

test('D0078-AC-20: どの条件にも当たらないときだけ ok（required・optional・none のどれでも）', () => {
  assert.deepEqual(decideRun(ctx(), false, '使い方を直して'), { ok: true });
  assert.deepEqual(decideRun(ctx({ input: 'optional' }), false, ''), { ok: true });
  assert.deepEqual(decideRun(ctx({ input: 'none' }), false, ''), { ok: true });
  assert.deepEqual(decideRun(ctx({ input: 'none' }), false, 'a\u0000'.repeat(3000)), { ok: true }, 'none は依頼メモを見ない');
});

/** 良い入力から、1つの条件だけを悪くする（RUN_BLOCK_ORDER の順） */
const BREAKS: readonly { block: RunBlock; apply: (c: RunContext, dirty: boolean, text: string) => { c: RunContext; dirty: boolean; text: string } }[] = [
  { block: 'untrusted', apply: (c, dirty, text) => ({ c: { ...c, trusted: false }, dirty, text }) },
  { block: 'noProject', apply: (c, dirty, text) => ({ c: { ...c, project: null }, dirty, text }) },
  { block: 'noExecutable', apply: (c, dirty, text) => ({ c: { ...c, executable: { ok: false, reason: '`pipe-in` が見つかりません' } }, dirty, text }) },
  { block: 'running', apply: (c, dirty, text) => ({ c: { ...c, running: true }, dirty, text }) },
  { block: 'notSaved', apply: (c, dirty, text) => ({ c: { ...c, pipeDir: null }, dirty, text }) },
  { block: 'dirty', apply: (c, _dirty, text) => ({ c, dirty: true, text }) },
  { block: 'invalid', apply: (c, dirty, text) => ({ c: { ...c, savedErrors: 2 }, dirty, text }) },
];
const TEXTS: readonly { block: RunBlock; text: string }[] = [
  { block: 'textEmpty', text: '　\n' },
  { block: 'textTooLong', text: 'a'.repeat(4001) },
  { block: 'textNul', text: 'a\u0000b' },
  { block: 'textBroken', text: 'a\ud800b' },
];

test('D0078-AC-20: BREAKS は RUN_BLOCK_ORDER の先頭7つと同じ並び（この検査の前提）', () => {
  assert.deepEqual([...BREAKS.map((b) => b.block), ...TEXTS.map((t) => t.block)], [...RUN_BLOCK_ORDER]);
});

for (const b of BREAKS) {
  test(`D0078-AC-20: ${b.block} だけが当たる入力は、その block と空でない理由を返す`, () => {
    const { c, dirty, text } = b.apply(ctx(), false, '使い方を直して');
    const d = decideRun(c, dirty, text);
    assert.equal(d.ok, false);
    if (!d.ok) {
      assert.equal(d.block, b.block);
      assert.ok(d.reason.length > 0);
    }
  });
}

for (const t of TEXTS) {
  test(`D0078-AC-20: ${t.block} だけが当たる入力は、その block と空でない理由を返す`, () => {
    const d = decideRun(ctx(), false, t.text);
    assert.equal(d.ok, false);
    if (!d.ok) {
      assert.equal(d.block, t.block);
      assert.ok(d.reason.length > 0);
    }
  });
}

// 2つ当たるときは、表の上のほうが返る（すべての組）
for (let i = 0; i < BREAKS.length; i++) {
  for (let j = i + 1; j < BREAKS.length; j++) {
    test(`D0078-AC-20: ${BREAKS[i]!.block} と ${BREAKS[j]!.block} が両方当たるときは ${BREAKS[i]!.block}`, () => {
      const first = BREAKS[i]!.apply(ctx(), false, '使い方を直して');
      const both = BREAKS[j]!.apply(first.c, first.dirty, first.text);
      assert.equal(blockOf(both.c, both.dirty, both.text), BREAKS[i]!.block);
    });
  }
  for (const t of TEXTS) {
    test(`D0078-AC-20: ${BREAKS[i]!.block} と ${t.block} が両方当たるときは ${BREAKS[i]!.block}`, () => {
      const broken = BREAKS[i]!.apply(ctx(), false, t.text);
      assert.equal(blockOf(broken.c, broken.dirty, broken.text), BREAKS[i]!.block);
    });
  }
}

test('D0078-AC-20: 全部に当たる入力から、1つずつ条件を直すと、順どおりに理由が1つずつ変わり、最後に ok になる', () => {
  let c: RunContext = ctx({ trusted: false, project: null, executable: { ok: false, reason: '見つかりません' }, running: true, pipeDir: null, savedErrors: 2, input: 'required' });
  let dirty = true;
  let text = '';
  const seen: (RunBlock | 'ok')[] = [];
  const note = (): void => {
    const d = decideRun(c, dirty, text);
    seen.push(d.ok ? 'ok' : d.block);
  };
  note();
  c = { ...c, trusted: true }; note();
  c = { ...c, project: '/work/app' }; note();
  c = { ...c, executable: { ok: true, path: '/usr/local/bin/pipe-in' } }; note();
  c = { ...c, running: false }; note();
  c = { ...c, pipeDir: PIPE_DIR }; note();
  dirty = false; note();
  c = { ...c, savedErrors: 0 }; note(); // 依頼メモが空 → textEmpty
  text = 'a'.repeat(4001); note();
  text = 'a\u0000\ud800'; note();
  text = 'a\ud800'; note();
  text = 'ok'; note();
  assert.deepEqual(seen, ['untrusted', 'noProject', 'noExecutable', 'running', 'notSaved', 'dirty', 'invalid', 'textEmpty', 'textTooLong', 'textNul', 'textBroken', 'ok']);
});

// ---- AC-10〜14・18・19：個々の理由 ----

test('D0078-AC-10: pipeDir が null なら notSaved と「先に保存」の理由（保存していないパイプは流せない）', () => {
  const d = decideRun(ctx({ pipeDir: null }), false, '使い方を直して');
  assert.equal(d.ok, false);
  if (!d.ok) {
    assert.equal(d.block, 'notSaved');
    assert.match(d.reason, /先に保存/);
  }
});

test('D0078-AC-11: dirty なら dirty の理由（保存していない変更がある。先に保存）', () => {
  const d = decideRun(ctx(), true, '使い方を直して');
  assert.equal(d.ok, false);
  if (!d.ok) {
    assert.equal(d.block, 'dirty');
    assert.match(d.reason, /保存していない変更/);
    assert.match(d.reason, /先に保存/);
  }
});

test('D0078-AC-11: dirty は呼び手の値で決まる（ctx に dirty は無い）。false なら通る', () => {
  assert.equal(blockOf(ctx(), true, 'メモ'), 'dirty');
  assert.equal(blockOf(ctx(), false, 'メモ'), null);
});

for (const n of [1, 2, 10]) {
  test(`D0078-AC-12: savedErrors が ${n} なら invalid（理由に件数 ${n} が出る）`, () => {
    const d = decideRun(ctx({ savedErrors: n }), false, 'メモ');
    assert.equal(d.ok, false);
    if (!d.ok) {
      assert.equal(d.block, 'invalid');
      assert.ok(d.reason.includes(String(n)), d.reason);
      assert.match(d.reason, /保存/);
    }
  });
}

test('D0078-AC-12: savedErrors が 0 なら invalid にならない', () => {
  assert.equal(blockOf(ctx({ savedErrors: 0 }), false, 'メモ'), null);
});

test('D0078-AC-13: project が null なら noProject（ワークスペースのフォルダを開く）', () => {
  const d = decideRun(ctx({ project: null }), false, 'メモ');
  assert.equal(d.ok, false);
  if (!d.ok) {
    assert.equal(d.block, 'noProject');
    assert.match(d.reason, /ワークスペース/);
  }
});

test('D0078-AC-14: trusted が false なら untrusted（信頼）', () => {
  const d = decideRun(ctx({ trusted: false }), false, 'メモ');
  assert.equal(d.ok, false);
  if (!d.ok) {
    assert.equal(d.block, 'untrusted');
    assert.match(d.reason, /信頼/);
  }
});

test('D0078-AC-18: executable が ok でなければ noExecutable で、その reason をそのまま返す', () => {
  for (const reason of ['`pipe-in` が見つかりません。設定 `pipe-in.command` に絶対パスを書いてください', '`pipe-in.command` のファイルがありません：/opt/x/pipe-in', '別の理由 <b>']) {
    const d = decideRun(ctx({ executable: { ok: false, reason } }), false, 'メモ');
    assert.equal(d.ok, false);
    if (!d.ok) {
      assert.equal(d.block, 'noExecutable');
      assert.equal(d.reason, reason);
    }
  }
});

test('D0078-AC-19: running なら running の理由（実行中）', () => {
  const d = decideRun(ctx({ running: true }), false, 'メモ');
  assert.equal(d.ok, false);
  if (!d.ok) {
    assert.equal(d.block, 'running');
    assert.match(d.reason, /実行中/);
  }
});

// ---- AC-15〜17：依頼メモ ----

test('D0078-AC-15: required は空・空白だけ（全角空白・改行・タブを含む）で textEmpty。optional は通る。none は見ない', () => {
  for (const text of ['', ' ', '\t', '\n', '\r\n', '　', ' \n\t　 ']) {
    assert.equal(blockOf(ctx({ input: 'required' }), false, text), 'textEmpty', JSON.stringify(text));
    assert.equal(blockOf(ctx({ input: 'optional' }), false, text), null, JSON.stringify(text));
    assert.equal(blockOf(ctx({ input: 'none' }), false, text), null, JSON.stringify(text));
  }
  assert.match(reasonOf(ctx(), false, ''), /依頼メモ/);
});

test('D0078-AC-16: 4,000 ちょうどは通り、4,001 は textTooLong。サロゲートペアは 2 と数える。none は長さを見ない', () => {
  assert.equal(blockOf(ctx(), false, 'a'.repeat(4000)), null);
  assert.equal(blockOf(ctx(), false, 'a'.repeat(4001)), 'textTooLong');
  assert.equal(blockOf(ctx(), false, '😀'.repeat(2000)), null);
  assert.equal(blockOf(ctx(), false, '😀'.repeat(2001)), 'textTooLong');
  assert.equal(blockOf(ctx({ input: 'optional' }), false, 'a'.repeat(4001)), 'textTooLong');
  assert.equal(blockOf(ctx({ input: 'none' }), false, 'a'.repeat(100000)), null);
  assert.match(reasonOf(ctx(), false, 'a'.repeat(4001)), /4,000/);
});

test('D0078-AC-17: NUL は textNul、対にならない上位/下位のサロゲートは textBroken、対になったサロゲート（絵文字）は通る', () => {
  assert.equal(blockOf(ctx(), false, 'a\u0000b'), 'textNul');
  assert.equal(blockOf(ctx({ input: 'optional' }), false, '\u0000'), 'textNul');
  assert.equal(blockOf(ctx(), false, 'a\ud800b'), 'textBroken');
  assert.equal(blockOf(ctx(), false, 'a\udc00b'), 'textBroken');
  assert.equal(blockOf(ctx(), false, 'a😀b'), null);
  assert.equal(blockOf(ctx({ input: 'none' }), false, 'a\u0000\ud800'), null);
  assert.match(reasonOf(ctx(), false, 'a\u0000b'), /NUL/);
});

// ---- readRunContext（パネル側で知らせを検める） ----

const GOOD_RAW = { type: 'runContext', input: 'optional', pipeDir: PIPE_DIR, savedErrors: 0, project: '/work/app', trusted: true, executable: { ok: true, path: '/usr/local/bin/pipe-in' }, running: false };

test('D0078-AC-49: readRunContext：正しい知らせは7項目の RunContext にして返し、type などほかの鍵は捨てる', () => {
  const r = readRunContext({ ...GOOD_RAW, dirty: true, text: 'x', cwd: '/evil' });
  assert.notEqual(r, null);
  assert.deepEqual(r, { input: 'optional', pipeDir: PIPE_DIR, savedErrors: 0, project: '/work/app', trusted: true, executable: { ok: true, path: '/usr/local/bin/pipe-in' }, running: false });
  assert.deepEqual(Object.keys(r ?? {}).sort(), ['executable', 'input', 'pipeDir', 'project', 'running', 'savedErrors', 'trusted']);
});

test('D0078-AC-49: readRunContext：pipeDir と project は null でもよく、executable は ok: false と reason でもよい', () => {
  const r = readRunContext({ ...GOOD_RAW, pipeDir: null, project: null, executable: { ok: false, reason: '見つかりません' }, running: true });
  assert.deepEqual(r, { input: 'optional', pipeDir: null, savedErrors: 0, project: null, trusted: true, executable: { ok: false, reason: '見つかりません' }, running: true });
});

test('D0078-AC-49: readRunContext：入力の3種類はどれも読める', () => {
  for (const input of ['required', 'optional', 'none'] as InputMode[]) assert.equal(readRunContext({ ...GOOD_RAW, input })?.input, input);
});

const BAD_RAW: readonly (readonly [string, unknown])[] = [
  ['null', null],
  ['文字', 'runContext'],
  ['数', 3],
  ['配列', []],
  ['空のオブジェクト', {}],
  ['input が知らない種類', { ...GOOD_RAW, input: 'maybe' }],
  ['input が無い', { ...GOOD_RAW, input: undefined }],
  ['pipeDir が数', { ...GOOD_RAW, pipeDir: 1 }],
  ['pipeDir が無い（undefined）', { ...GOOD_RAW, pipeDir: undefined }],
  ['savedErrors が文字', { ...GOOD_RAW, savedErrors: '0' }],
  ['savedErrors が無い', { ...GOOD_RAW, savedErrors: undefined }],
  ['project が数', { ...GOOD_RAW, project: 5 }],
  ['trusted が文字', { ...GOOD_RAW, trusted: 'true' }],
  ['trusted が無い', { ...GOOD_RAW, trusted: undefined }],
  ['running が数', { ...GOOD_RAW, running: 1 }],
  ['running が無い', { ...GOOD_RAW, running: undefined }],
  ['executable が無い', { ...GOOD_RAW, executable: undefined }],
  ['executable が文字', { ...GOOD_RAW, executable: '/usr/bin/pipe-in' }],
  ['executable.ok が文字', { ...GOOD_RAW, executable: { ok: 'true', path: '/x' } }],
  ['executable.ok が真で path が数', { ...GOOD_RAW, executable: { ok: true, path: 3 } }],
  ['executable.ok が真で path が無い', { ...GOOD_RAW, executable: { ok: true } }],
  ['executable.ok が偽で reason が数', { ...GOOD_RAW, executable: { ok: false, reason: 3 } }],
  ['executable.ok が偽で reason が無い', { ...GOOD_RAW, executable: { ok: false } }],
];

for (const [label, value] of BAD_RAW) {
  test(`D0078-AC-49: readRunContext：${label}は null（型・形が違えば使わない）`, () => {
    assert.equal(readRunContext(value), null);
  });
}
