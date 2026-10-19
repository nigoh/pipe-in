// 時刻の読み方：記録の時刻の文字を、ミリ秒と経過秒にする。純粋（時計に触れない）。
// 本体は新しい時刻を UTC からのずれつき（+09:00・Z）で書くが、started_at などの古い書き方はずれがない。
// ずれのない時刻は、読む側の手元の時刻（localOffsetMin）として読む。

const PATTERN = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$/;

/** 時刻の文字を分けて、UTC のミリ秒（ずれは引かない）とずれ（分、無ければ null）にする。形や暦が合わなければ null。 */
function split(text: string): { wallMs: number; offsetMin: number | null } | null {
  const m = PATTERN.exec(text);
  if (!m) return null;
  const [year, month, day, hour, minute, second] = m.slice(1, 7).map((v) => Number.parseInt(v, 10));
  if (month < 1 || month > 12 || hour > 23 || minute > 59 || second > 59) return null;
  const date = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
  // 2月30日のように、暦が戻って合わなくなる日付を弾く
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
  const millis = m[7] === undefined ? 0 : Math.floor(Number(`0.${m[7]}`) * 1000);
  let offsetMin: number | null = null;
  const zone = m[8];
  if (zone !== undefined) {
    if (zone === 'Z') {
      offsetMin = 0;
    } else {
      const digits = zone.slice(1).replace(':', '');
      const oh = Number.parseInt(digits.slice(0, 2), 10);
      const om = Number.parseInt(digits.slice(2, 4), 10);
      if (oh > 23 || om > 59) return null;
      offsetMin = (zone[0] === '-' ? -1 : 1) * (oh * 60 + om);
    }
  }
  return { wallMs: date.getTime() + millis, offsetMin };
}

/** 記録の時刻として読める文字か（文字でない値・形の違う文字・存在しない日付は false）。 */
export function isTimestampText(text: unknown): text is string {
  return typeof text === 'string' && split(text) !== null;
}

/** 時刻の文字を UTC のミリ秒にする。ずれがあればそれ、無ければ localOffsetMin（手元の UTC からのずれ、分）で読む。読めなければ null。 */
export function parseInstant(text: string, localOffsetMin: number): number | null {
  const parts = split(text);
  if (parts === null) return null;
  const offset = parts.offsetMin ?? (Number.isFinite(localOffsetMin) ? localOffsetMin : 0);
  return parts.wallMs - offset * 60_000;
}

/** fromMs から toMs までの経過秒。切り捨てで、負（未来の時刻）や読めない値は 0。 */
export function elapsedSec(fromMs: number, toMs: number): number {
  const sec = Math.floor((toMs - fromMs) / 1000);
  return Number.isFinite(sec) && sec > 0 ? sec : 0;
}
