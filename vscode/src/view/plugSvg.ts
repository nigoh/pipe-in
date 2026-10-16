// コンセントとプラグの SVG（ケーブルの先）。純粋な文字列だけ。
// 座標は差し込む点（コンセントの面の手前）を原点に、ケーブルが入ってくる向きを +x にとる。
// 差さったプラグは本体がコンセントの面に付き、刃はコンセントの中に入る（コンセントをあとに描いて刃を隠す）。
// 抜けたプラグは刃が本体の先に出て、刃の先端が掴んでいる点に来る。CSP があるので style 属性は使わない。

export interface Box { x: number; y: number; w: number; h: number }
export type PlugPose = 'in' | 'loose';

/** コンセントの外形（ブロックの左の縁の 16px 手前から） */
export const SOCKET_BOX: Box = { x: -1, y: -12, w: 15, h: 24 };
const SLOTS: Box[] = [{ x: 3.5, y: -6.5, w: 2.2, h: 5 }, { x: 8.3, y: -6.5, w: 2.2, h: 5 }, { x: 3.5, y: 2, w: 2.2, h: 4 }, { x: 8.3, y: 2, w: 2.2, h: 4 }];
const BODY = { w: 14, h: 15 }, PRONG = { w: 9, h: 2.6 };

/** プラグの本体と刃の四角 */
export function plugParts(pose: PlugPose): { body: Box; prongs: Box[] } {
  // 差さった姿：本体の右の縁がコンセントの面（SOCKET_BOX.x）。抜けた姿：刃の先端が原点
  const bodyRight = pose === 'in' ? SOCKET_BOX.x : -PRONG.w;
  const body = { x: bodyRight - BODY.w, y: -BODY.h / 2, w: BODY.w, h: BODY.h };
  const px = pose === 'in' ? SOCKET_BOX.x : -PRONG.w;
  return { body, prongs: [{ x: px, y: -5, w: PRONG.w, h: PRONG.h }, { x: px, y: 2.4, w: PRONG.w, h: PRONG.h }] };
}

const rect = (cls: string, b: Box, rx = 0): string =>
  `<rect class="${cls}" x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}"${rx ? ` rx="${rx}"` : ''}/>`;
const at = (x: number, y: number, ang: number): string => `translate(${x} ${y}) rotate(${ang})`;

/** コンセント。plugged なら差し込み口は埋まって見え、空きなら差し込み口が見える */
export function socketSvg(x: number, y: number, ang: number, plugged: boolean): string {
  const face = rect(`socket ${plugged ? 'plugged' : 'empty'}`, SOCKET_BOX, 4);
  const holes = plugged
    ? rect('seat', { x: SOCKET_BOX.x, y: -6.5, w: 2.4, h: 13 })
    : SLOTS.map((b) => rect('slot', b)).join('');
  return `<g transform="${at(x, y, ang)}">${face}${holes}</g>`;
}

/**
 * プラグ。kind はケーブルの種類（色）。grab を渡すと掴める印（data-plug）と掴む所を付ける。
 * snap は差した瞬間の押し込む動き（内側の g に CSS の動きを付ける。外側の transform 属性とぶつからないように）。
 */
export function plugSvg(x: number, y: number, ang: number, kind: string, pose: PlugPose, o: { grab?: number; snap?: boolean } = {}): string {
  const p = plugParts(pose);
  const parts = p.prongs.map((b) => rect('prong', b)).join('') + rect(`plug-body ${kind}`, p.body, 3.5);
  const grab = o.grab === undefined ? '' : ` data-plug="${o.grab}"`;
  const hit = o.grab === undefined ? '' : rect('plug-hit', { x: p.body.x - 3, y: -11, w: p.body.w + 4, h: 22 });
  return `<g class="plug${o.grab === undefined ? '' : ' grab'}" transform="${at(x, y, ang)}"${grab}><g class="plug-in${o.snap ? ' snap' : ''}">${parts}</g>${hit}</g>`;
}
