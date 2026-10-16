// 記録（JSON）を読むときの小さな検め。ドメインの中だけで使う。

export type JsonObject = Record<string, unknown>;

/** 配列でない、null でないオブジェクトか。 */
export function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
