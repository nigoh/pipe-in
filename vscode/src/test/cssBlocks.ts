// パネルの CSS を波括弧で読む、小さなテストの補助（D0017：動きの規則が prefers-reduced-motion: no-preference の中だけにあるかを見る）。
// CSS の全部を読むものではなく、パネルの STYLE が使う形（規則・@media・@keyframes）だけを読む。

export interface CssRule {
  /** 規則の頭（セレクタ、または @keyframes の名前の行） */
  selector: string;
  /** 波括弧の中身 */
  body: string;
  /** 外側の @media の頭を、外から内の順につないだもの。無ければ null */
  media: string | null;
  /** @keyframes か */
  keyframes: boolean;
}

/** <style …>…</style> の中身をすべてつなぐ。 */
export function extractCss(html: string): string {
  return [...html.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/g)].map((m) => m[1]).join('\n');
}

function matchingBrace(css: string, open: number): number {
  let depth = 0;
  for (let i = open; i < css.length; i++) {
    if (css[i] === '{') depth++;
    else if (css[i] === '}' && --depth === 0) return i;
  }
  return css.length;
}

/** CSS を、規則の並び（@media の中は展開して media を付ける）にする。コメントは捨てる。 */
export function parseCss(css: string, media: string | null = null): CssRule[] {
  const text = media === null ? css.replace(/\/\*[\s\S]*?\*\//g, '') : css;
  const rules: CssRule[] = [];
  let i = 0;
  while (i < text.length) {
    const open = text.indexOf('{', i);
    if (open === -1) break;
    const prelude = text.slice(i, open).trim();
    const close = matchingBrace(text, open);
    const body = text.slice(open + 1, close);
    if (prelude.startsWith('@media')) {
      rules.push(...parseCss(body, media === null ? prelude : `${media} ${prelude}`));
    } else {
      rules.push({ selector: prelude, body, media, keyframes: prelude.startsWith('@keyframes') });
    }
    i = close + 1;
  }
  return rules;
}

const NO_PREFERENCE = /\(\s*prefers-reduced-motion\s*:\s*no-preference\s*\)/;
const ANIMATION = /\banimation(-name)?\s*:/;

/** 動き（animation・@keyframes）を、no-preference の @media の外に置いている規則の説明。無ければ空。 */
export function motionOutsideNoPreference(css: string): string[] {
  return parseCss(css)
    .filter((r) => r.keyframes || ANIMATION.test(r.body))
    .filter((r) => r.media === null || !NO_PREFERENCE.test(r.media))
    .map((r) => `${r.media ?? '(media なし)'} ${r.selector}`);
}

/** no-preference の @media の中にある @keyframes の名前。 */
export function keyframesInNoPreference(css: string): string[] {
  return parseCss(css)
    .filter((r) => r.keyframes && r.media !== null && NO_PREFERENCE.test(r.media))
    .map((r) => r.selector.replace('@keyframes', '').trim());
}

/** reduce の @media の中で、時間の要素を隠す・消す規則（display:none・visibility:hidden・opacity:0 など）の説明。無ければ空。 */
export function hidingInReduce(css: string): string[] {
  return parseCss(css)
    .filter((r) => r.media !== null && /\breduce\b/.test(r.media))
    .filter((r) => /display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0\b|\bhidden\b/.test(r.body) || /elapsed|node-wait/.test(r.selector))
    .map((r) => `${r.media} ${r.selector}`);
}
