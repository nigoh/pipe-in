// ソースを文字で読む検査の部品（テストの補助。D0024：extension.ts の配線を extensionCounts.test.ts が見る）。
// extension.ts は vscode を import するので単体では動かせない。判断を持たない呼び出しの形を、文字で読んで確かめる。
// 構文を読むものではない：かっこの釣り合いを数えるだけなので、かっこの片側だけを文字列に入れた行があると釣り合いが狂う。
// 行の途中に書いた // のコメントは取り除けないので、検査の言葉は自然な行末コメントに出てこないものにする。

const IDENT_SPECIALS = /[.*+?^${}()|[\]\\]/g;

function escapeRegExp(text: string): string {
  return text.replace(IDENT_SPECIALS, '\\$&');
}

/** open の位置にある開きかっこ（( か {）に釣り合う閉じかっこの位置。釣り合わなければ -1。 */
function matching(code: string, open: number): number {
  const opener = code[open];
  const closer = opener === '(' ? ')' : '}';
  let depth = 0;
  for (let i = open; i < code.length; i++) {
    if (code[i] === opener) depth += 1;
    else if (code[i] === closer) {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return -1;
}

/** 正規表現から g・y の旗を外す（exec が前の位置を覚えないように） */
function once(re: RegExp): RegExp {
  return new RegExp(re.source, re.flags.replace(/[gy]/g, ''));
}

/** 行頭から始まるコメント（ブロックと //）を取り除く。コメントに書いた呼び出しで検査を通さない。文字列の中の「/*」（glob）は行頭にならないので触らない。 */
export function withoutComments(source: string): string {
  return source.replace(/^[ \t]*\/\*[\s\S]*?\*\//gm, '').replace(/^[ \t]*\/\/.*$/gm, '');
}

/**
 * name( の呼び出しごとの、引数の文字（かっこの釣り合いで取る）。
 * import の行（name の後ろに ( が続かない）と、関数の宣言（function name( ・ async function name( ・ export function name( ）は数えない。
 */
export function callArgs(code: string, name: string): string[] {
  const out: string[] = [];
  const re = new RegExp(`(?<!\\bfunction\\s+)\\b${escapeRegExp(name)}\\(`, 'g');
  for (let m = re.exec(code); m !== null; m = re.exec(code)) {
    const open = m.index + m[0].length - 1;
    const close = matching(code, open);
    out.push(code.slice(open + 1, close === -1 ? code.length : close));
  }
  return out;
}

/**
 * function name( ・ async function name( の本体（{ } の中）を、{ } の釣り合いで取る。無ければ null。
 * 引数のかっこの後ろ、最初の { を本体の始まりとするので、戻り値の型に { } を書く関数は対象外。
 */
export function functionBody(code: string, name: string): string | null {
  const head = new RegExp(`\\bfunction\\s+${escapeRegExp(name)}\\s*\\(`).exec(code);
  if (head === null) return null;
  const paramsEnd = matching(code, head.index + head[0].length - 1);
  if (paramsEnd === -1) return null;
  const open = code.indexOf('{', paramsEnd);
  if (open === -1) return null;
  const close = matching(code, open);
  return close === -1 ? null : code.slice(open + 1, close);
}

/**
 * 正規表現 head（開きの { までを含む）に最初に合った所のあとから、釣り合う } の前までの中身。
 * 合う所が無い・釣り合わないときは null。head が { で終わっていなければ使い方の誤りなので例外にする。
 */
export function blockAfter(code: string, head: RegExp): string | null {
  const m = once(head).exec(code);
  if (m === null) return null;
  const open = m.index + m[0].length - 1;
  if (code[open] !== '{') throw new Error(`blockAfter の head は { で終わる正規表現にしてください：${String(head)}`);
  const close = matching(code, open);
  return close === -1 ? null : code.slice(open + 1, close);
}

/** parts（正規表現の並び）の、それぞれ最初に出る位置が、この順に並ぶか。どれかが無ければ偽。後ろに同じ語がもう 1 度あっても、最初の出現が逆なら偽。 */
export function inOrder(text: string, parts: readonly RegExp[]): boolean {
  let last = -1;
  for (const part of parts) {
    const m = once(part).exec(text);
    if (m === null || m.index <= last) return false;
    last = m.index;
  }
  return true;
}
