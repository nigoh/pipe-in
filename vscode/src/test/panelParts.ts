// テストの補助：本体の HTML から、詳細のタブパネルを data-detail-panel の値をキーにして取り出す（D0047）。
// 個数は決め打ちしない。
// 使う側：新しい view/shellHtmlTools.test.ts と、既存の view/shellHtml.test.ts・view/artifactsPanel.test.ts（この 2 つは、それぞれにあった同じ本体の panelsOf を、ここからの import に替えた。関数の中身は変えていない）。
// 切り出しの本体はここの 1 か所だけ。previewPagesArtifacts.test.ts の補助を previewText.ts へ移したのと同じ形。
// 名前を panelsByName にしたのは、previewText.ts の panelsOf（SHA-256 のために「図と出力」と「使用量」のパネルだけを 1 つの文字にする別の補助）と取り違えないため。
// テストのファイルは import できない（import すると、そのファイルのテストがもう一度走る）ので、補助は test/ に置く。
import assert from 'node:assert/strict';

/** tabpanel の開きタグの後ろから、次のパネルの手前まで（最後のパネルは文字の終わりまで）。 */
export function panelsByName(out: string): Record<string, string> {
  const tags = [...out.matchAll(/<[a-z]+\b[^>]*role="tabpanel"[^>]*>/g)];
  const panels: Record<string, string> = {};
  tags.forEach((m, i) => {
    const key = /\bdata-detail-panel="([^"]*)"/.exec(m[0])?.[1];
    assert.ok(key !== undefined, `role="tabpanel" のタグに data-detail-panel がある：${m[0]}`);
    const from = (m.index ?? 0) + m[0].length;
    const to = i + 1 < tags.length ? (tags[i + 1]!.index ?? out.length) : out.length;
    panels[key] = out.slice(from, to);
  });
  return panels;
}

/** data-detail-panel が name のパネルの開きタグ。無ければ落とす。 */
export function panelTag(out: string, name: string): string {
  const tag = [...out.matchAll(/<[a-z]+\b[^>]*role="tabpanel"[^>]*>/g)].map((m) => m[0]).find((t) => new RegExp(`\\bdata-detail-panel="${name}"`).test(t));
  assert.ok(tag !== undefined, `data-detail-panel="${name}" のパネルがある（まだ作っていない）`);
  return tag;
}
