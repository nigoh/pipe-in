// SVG の表示上の幅（px）を、偽の DOM と CSS から読むテストの補助（D0019：図・時系列を元の大きさで描く、図の拡大縮小）。
// 幅の決め方は 2 通りあり、どちらでも読めるようにする：SVG の width 属性、または nonce つきの style 要素の CSS（class ごとの width: Npx）。
import type { FakeNode } from './fakeDom.ts';
import { parseCss } from './cssBlocks.ts';

/** 節から文書の根までの class（自分を含む） */
export function classesUp(node: FakeNode): Set<string> {
  const found = new Set<string>();
  for (let n: FakeNode | null = node; n !== null; n = n.parent) {
    for (const c of (n.getAttribute('class') ?? '').split(/\s+/)) if (c !== '') found.add(c);
  }
  return found;
}

/**
 * svg の表示上の幅（px）。width 属性があればそれ。無ければ CSS の規則のうち、
 * 「最後の部分に .<own> を持ち、使っている class が svg とその祖先に全部付いている」ものの width: Npx（class が多い規則を優先、同じなら後ろの規則）。
 * 読めなければ null（width: 100% など、px で決まらないとき）。
 */
export function shownWidth(css: string, svg: FakeNode, own: string): number | null {
  const attr = svg.getAttribute('width');
  if (attr !== null && /^\d+(\.\d+)?(px)?$/.test(attr.trim())) return parseFloat(attr);
  const have = classesUp(svg);
  const lastHas = new RegExp(`\\.${own}(?![\\w-])`);
  let best: { classes: number; width: number } | null = null;
  for (const rule of parseCss(css)) {
    if (rule.keyframes) continue;
    const width = /(?<![-\w])width\s*:\s*(\d+(?:\.\d+)?)px/.exec(rule.body);
    if (width === null) continue;
    for (const selector of rule.selector.split(',')) {
      const last = selector.trim().split(/\s+/).pop() ?? '';
      if (!lastHas.test(last)) continue;
      const tokens = [...selector.matchAll(/\.([\w-]+)/g)].map((m) => m[1]!);
      if (!tokens.every((t) => have.has(t))) continue;
      if (best === null || tokens.length >= best.classes) best = { classes: tokens.length, width: parseFloat(width[1]!) };
    }
  }
  return best === null ? null : best.width;
}
