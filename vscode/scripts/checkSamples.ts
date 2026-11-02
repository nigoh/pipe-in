// パイプの判定とやり直しの見本の記録（D0062）。確認用ページ（run-panel-check-*）に使う state.json の中身だけを持つ。
// tests/fixtures/ には見本の記録を足さない。previewPages.ts の buildCheckDir が、一時フォルダに書いて本物の読み取りで読む。
// 判定の設定と検証の結果の並びは、本体と拡張が結ぶ共通の表 tests/fixtures/check_record.json から取る（読むだけ）。
// stages[].check と、runs[] の check の要素（attempt が先頭の鍵）は、本体が書く形と同じ。
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/** 見本の種類：self ＝ 自分をやり直す（1 回 fail → pass）、back ＝ 前の段へ戻す（上限まで落ちた）、old ＝ 古い記録（判定の情報なし）。 */
export type CheckSampleKind = 'self' | 'back' | 'old';

interface TableCase {
  memo: string;
  check: { on_fail: string | null; max_retries: number };
  results: ('pass' | 'fail')[];
  exit: string;
}

const TABLE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'tests', 'fixtures', 'check_record.json');

/** 共通の表の case を、メモの頭で引く。 */
function tableCase(memoHead: string): TableCase {
  const table = JSON.parse(readFileSync(TABLE, 'utf8')) as { cases: TableCase[] };
  const found = table.cases.find((c) => c.memo.startsWith(memoHead));
  if (found === undefined) throw new Error(`共通の表 check_record.json に「${memoHead}」の case がありません`);
  return found;
}

// 直す点の文。1 つは外から来た文字の見本（画面で、タグがそのまま文字として見えることを確かめる）
const PROBLEMS = ['矢印の向きが逆になっている', '凡例が足りない（<b>太字</b> と書かれていても、そのまま見える）'];

function runEntry(stage: string, seq: number): Record<string, unknown> {
  return {
    stage,
    session_id: `check-session-${seq}`,
    is_error: false,
    subtype: 'success',
    result: '完了しました',
    cost_usd: 0.1,
    num_turns: 3,
    duration_sec: 20.0,
    denials: [],
    errors: [],
    seq,
    attempt: null,
    note: '',
  };
}

function checkEntry(stage: string, status: 'pass' | 'fail', attempt: number | null): Record<string, unknown> {
  return {
    stage,
    check: {
      ...(attempt === null ? {} : { attempt }),
      status,
      problems: status === 'fail' ? PROBLEMS : [],
      summary: status === 'fail' ? `${attempt ?? 1} 回目は直す点があります` : '直す点はありません',
    },
  };
}

/** 判定をつけた段（verify）を results の並びだけ検証する。前の段へ戻す（on_fail がある）ときは、不合格のたびにその段も流し直す。 */
function checkedRuns(first: string, verify: string, c: TableCase, withAttempt: boolean): Record<string, unknown>[] {
  const runs: Record<string, unknown>[] = [runEntry(first, 1)];
  let seq = 1;
  c.results.forEach((status, i) => {
    if (i > 0 && c.check.on_fail !== null) runs.push(runEntry(c.check.on_fail, (seq += 1)));
    runs.push(runEntry(verify, (seq += 1)));
    runs.push(checkEntry(verify, status, withAttempt ? i + 1 : null));
  });
  return runs;
}

/** 見本の種類ごとの state.json の文字（パイプ check-demo。動いている段は出さない）。 */
export function checkStateJson(kind: CheckSampleKind): string {
  const self = kind === 'self';
  const c = kind === 'old' ? tableCase('自分をやり直す・1 回目 fail') : self ? tableCase('自分をやり直す・1 回目 fail') : tableCase('前の段へ戻す・上限');
  const first = kind === 'back' ? 'draw' : 'plan';
  const verify = kind === 'back' ? 'verify' : 'build';
  const runs = checkedRuns(first, verify, c, kind !== 'old').filter((r) => kind !== 'old' || !('check' in r));
  const stages = [
    { name: first, label: kind === 'back' ? '図を描く' : '計画', output: `${first}.md`, review: false },
    {
      name: verify,
      label: kind === 'back' ? '図の突き合わせ' : '実装',
      output: `${verify}.md`,
      review: false,
      ...(kind === 'old' ? {} : { check: { on_fail: c.check.on_fail, max_retries: c.check.max_retries } }),
    },
  ];
  const state = {
    started_at: '2026-10-17T10:00:00',
    updated_at: '2026-10-17T10:20:00',
    pipe: 'check-demo',
    name: '判定とやり直しの見本',
    stages,
    runs,
    final: c.exit,
    total_cost_usd: Math.round(runs.filter((r) => 'seq' in r).length * 0.1 * 1e4) / 1e4,
  };
  return `${JSON.stringify(state, null, 2)}\n`;
}
