// テストの補助：まだ作っていない部品（テスト先行のとき）を、読み込む前に有無を確かめて、無ければ「まだ作っていない」で落とす。
// ファイルごと静的に import すると、ファイルの読み込みで落ちて、同じファイルの「今のまま通る。守る」テストまで赤になる。
// ここは動的 import で、ファイルが有るときの読み込みの失敗（構文の誤りなど）はそのまま投げる（有無の判定を import の失敗に頼らない）。
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/** base（呼ぶ側の import.meta.url）からの相対パス rel の部品を読み込む。ファイルが無ければ落とす。 */
export async function needModule<T>(base: string, rel: string): Promise<T> {
  const url = new URL(rel, base);
  assert.ok(existsSync(fileURLToPath(url)), `${rel} が無い（まだ作っていない）`);
  return (await import(url.href)) as T;
}

/** 名前空間（import * as ns）から関数を取り出す。無ければ落とす。 */
export function needFunction<T extends (...args: never[]) => unknown>(ns: unknown, name: string, where: string): T {
  const value = (ns as Record<string, unknown>)[name];
  assert.equal(typeof value, 'function', `${where} に ${name} が無い（export されていない。まだ作っていない）`);
  return value as T;
}
