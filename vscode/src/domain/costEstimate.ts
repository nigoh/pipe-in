// 流す前の費用の目安の計算（D0066）。純粋な関数（ファイル・時計・vscode に触れない。今日は引数）。
// 本体（pipe_in/usage/estimate.py・prices.py）と同じ決まり・同じ数字。2つの表の中身が同じことは、共通の表 tests/fixtures/cost_estimate.json を
// 両側のテストが読んで検査する。単価表を直すときは、本体の prices.py・この PRICES・共通の表を一緒に直す。
//
// 単位は units（1/10000 ドル。整数）。少なめ ＝ 各段 1 回だけ、ターン上限の 20% を使う（切り上げ）。多め ＝ やり直しの上限まで、毎回ターン上限まで使う。
// 費用の上限（maxBudget）があれば 1 回分をそれで頭打ちにする（少なめにも掛ける）。多めは厳密な上限ではなく、目安。

/** 1 ターンの費用の表。as_of は決めた年月（180 日より古いと「古いかもしれません」）。公式の価格表を見て手で直す。 */
export const PRICES = {
  as_of: '2026-10',
  per_turn: { haiku: 150, sonnet: 500, opus: 2500 } as Record<string, number>,
  note: '仮の値。公式の価格表を見て手で直す（自動では更新しない）。直したら as_of も直す。',
};

export const DISCLAIMER =
  '目安です。実際の費用は、会話の長さ・ツールの使い方・キャッシュで変わり、これより多くなることも少なくなることもあります。' +
  '約束するものではありません。サブスクリプションでログインしている場合、請求額とは一致しません。';

export const STALE_DAYS = 180;
export const LOW_PERCENT = 20;
/** ターン上限が無い・読めないときの既定（拡張はパイプだけを扱う） */
export const DEFAULT_TURNS = 100;
const UNITS_PER_USD = 10000;
const FAMILIES = ['haiku', 'sonnet', 'opus'] as const;

export type CostMark = 'model_unknown' | 'turns_invalid';

export interface CostStageIn {
  name: string;
  model: unknown;
  maxTurns: unknown;
  maxBudget: number | null;
  maxRetries: unknown;
}
export interface CostStageOut {
  name: string;
  model: unknown;
  low: number;
  high: number;
  marks: CostMark[];
}
export interface CostEstimate {
  stages: CostStageOut[];
  low: number;
  high: number;
  stale: boolean;
}

/** モデルの名前から系統を決める。名前（小文字）に haiku・sonnet・opus の語があればその系統。無ければ sonnet で、unknown を立てる。 */
export function familyOf(model: unknown): { family: string; unknown: boolean } {
  if (typeof model === 'string') {
    const name = model.toLowerCase();
    for (const family of FAMILIES) if (name.includes(family)) return { family, unknown: false };
  }
  return { family: 'sonnet', unknown: true };
}

const isInt = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v);

function capUnits(budget: unknown): number | null {
  if (typeof budget !== 'number' || !Number.isFinite(budget) || budget <= 0) return null;
  return Math.floor(budget * UNITS_PER_USD + 0.5);
}

/** 'YYYY-MM-DD' を日数にする（時計の部品を使わず、暦の計算で出す）。読めなければ null。 */
function dayNumber(iso: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  // 1 年 3 月を起点にした日数（うるう年の計算が簡単になる）
  const yy = mo <= 2 ? y - 1 : y;
  const mm = mo <= 2 ? mo + 9 : mo - 3;
  return 365 * yy + Math.floor(yy / 4) - Math.floor(yy / 100) + Math.floor(yy / 400) + Math.floor((153 * mm + 2) / 5) + d;
}

function isStale(today: string | null): boolean {
  if (today === null) return false;
  const now = dayNumber(today);
  const asOf = dayNumber(`${PRICES.as_of}-01`);
  return now !== null && asOf !== null && now - asOf > STALE_DAYS;
}

export function estimateCost(stages: CostStageIn[], today: string | null): CostEstimate {
  const out: CostStageOut[] = stages.map((s) => {
    const { family, unknown } = familyOf(s.model);
    const none = s.maxTurns === null || s.maxTurns === undefined;
    const valid = isInt(s.maxTurns) && s.maxTurns > 0;
    const turns = valid ? (s.maxTurns as number) : DEFAULT_TURNS;
    const perTurn = PRICES.per_turn[family]!;
    let onceLow = Math.floor((turns * LOW_PERCENT + 99) / 100) * perTurn;
    let onceHigh = turns * perTurn;
    const cap = capUnits(s.maxBudget);
    if (cap !== null) {
      onceLow = Math.min(onceLow, cap);
      onceHigh = Math.min(onceHigh, cap);
    }
    const retries = isInt(s.maxRetries) && s.maxRetries >= 0 ? s.maxRetries : 0;
    const marks: CostMark[] = [];
    if (unknown) marks.push('model_unknown');
    if (!none && !valid) marks.push('turns_invalid');
    return { name: s.name, model: s.model, low: onceLow, high: onceHigh * (1 + retries), marks };
  });
  return { stages: out, low: out.reduce((a, s) => a + s.low, 0), high: out.reduce((a, s) => a + s.high, 0), stale: isStale(today) };
}
