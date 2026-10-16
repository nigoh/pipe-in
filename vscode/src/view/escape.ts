// HTML・SVG に文字を入れるときのエスケープ（純粋）。
const ESCAPES: Readonly<Record<string, string>> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&apos;',
};

/** & < > " ' を名前の文字参照にする（数値の文字参照 &#..; は使わない）。 */
export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => ESCAPES[c]);
}
