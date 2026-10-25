// 時間の書き方（純粋）：m:ss、1時間以上は h:mm:ss。小数は切り捨て、負・読めない値は 0:00。
// パネルのスクリプト（panelScript.ts）は同じ書き方の写しを持つ。食い違いはテスト（同じ表を両方に通す）で防ぐ。

export function formatDuration(sec: number): string {
  const total = Number.isFinite(sec) && sec > 0 ? Math.floor(sec) : 0;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const ss = String(s).padStart(2, '0');
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}
