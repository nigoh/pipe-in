// セッション名の取り方（本体 pipe_in/engine/session.py と同じ規則を、同じ字で書く）。純粋な関数だけ。
// 空白は JS の \s に頼らず、半角空白・タブ・改行・改ページ・垂直タブ・全角空白に決める。

export const NAME_LIMIT = 60;
export const TOKEN_LIMIT = 100;

const WS = ' \\t\\r\\n\\f\\v\\u3000';
const WS_RUN = new RegExp(`[${WS}]+`, 'g');
const WS_EDGES = new RegExp(`^[${WS}]+|[${WS}]+$`, 'g');
const LINE_BREAK = /\r\n|\r|\n/;
const HEADING_MARK = new RegExp(`^#{1,6}(?:[${WS}]+|$)`);
const BAD_TOKEN_CHAR = new RegExp(`[\\u0000-\\u001f\\u007f${WS}]`);

function trimWs(text: string): string {
  return text.replace(WS_EDGES, '');
}

/** 前後の空白を落とし、中の連続する空白を 1 つにし、60 文字（コードポイント）を超えるときは 59 文字＋「…」。空なら null。 */
export function normalizeName(text: string): string | null {
  const s = trimWs(trimWs(text).replace(WS_RUN, ' '));
  if (s === '') return null;
  const points = Array.from(s);
  return points.length <= NAME_LIMIT ? s : `${points.slice(0, NAME_LIMIT - 1).join('')}…`;
}

/** 要件メモの最初の「空白だけでない行」から名前を作る。先頭の見出しの印（# を 1〜6 個と空白）は 1 回だけ取る。 */
export function nameFromMemo(memo: string): string | null {
  for (const raw of memo.split(LINE_BREAK)) {
    const line = trimWs(raw);
    if (line === '') continue;
    return normalizeName(line.replace(HEADING_MARK, ''));
  }
  return null;
}

/** セッション ID・受け持ちとして読める値か（空でない・空白や制御文字を含まない・100 文字まで）。 */
export function isSafeToken(text: unknown): text is string {
  return typeof text === 'string' && text !== '' && !BAD_TOKEN_CHAR.test(text) && Array.from(text).length <= TOKEN_LIMIT;
}
