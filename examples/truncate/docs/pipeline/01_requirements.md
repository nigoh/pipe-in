# 要件定義書：文字列切り詰め関数 truncate

## 目的
`src/textutil.py` に、文字列を指定した文字数以内に収まるよう切り詰める関数 `truncate(text, width)` を追加し、表示領域などの文字数制限がある箇所で利用できるようにする。

## 背景・現状
- `src/textutil.py` には現在 `normalize_spaces(text)` のみが定義されている。
- 文字列を文字数で切り詰め、省略を示す関数は存在しない。

## スコープ
### 含む
- `src/textutil.py` への `truncate(text, width)` 関数の追加。
- 切り詰め発生時に末尾を「…」（U+2026, 1文字）に置き換える処理。
- `width` が不正な場合の例外送出。

### 含まない
- `normalize_spaces` など既存関数の変更。
- CLI やその他モジュールからの呼び出し箇所の追加・変更。
- 全角文字・絵文字などの表示幅（画面上の幅）を考慮した計算（本要件は Python の文字列長 `len()` に基づく文字数のみを対象とする）。

## 機能要件
- FR-01: `truncate(text, width)` は `text` が `width` 文字以内（`len(text) <= width`）であれば、`text` をそのまま返す。
- FR-02: `text` が `width` 文字を超える場合、末尾を「…」1文字に置き換え、戻り値の全体の長さが `width` 文字以内になるように切り詰めて返す（すなわち本文部分は `width - 1` 文字に切り詰め、末尾に「…」を付加する）。
- FR-03: `width` が `1` 未満（`width < 1`）の場合、`ValueError` を送出する。

## 非機能要件
- 既存の `normalize_spaces` と同様、型ヒント・簡潔な日本語 docstring を付した実装とする。
- 外部ライブラリへの依存は追加しない。

## 受け入れ基準
| ID | 前提条件 | 操作 | 期待結果 | 対応する要件 |
|---|---|---|---|---|
| AC-01 | text="hello", width=10 | `truncate(text, width)` を呼ぶ | 戻り値は `"hello"`（切り詰めなし） | FR-01 |
| AC-02 | text="hello", width=5 | `truncate(text, width)` を呼ぶ | 戻り値は `"hello"`（ちょうど width と同じ長さは切り詰めなし） | FR-01 |
| AC-03 | text="hello world", width=5 | `truncate(text, width)` を呼ぶ | 戻り値は `"hell…"`（長さ5、末尾が「…」） | FR-02 |
| AC-04 | text="hello", width=1 | `truncate(text, width)` を呼ぶ | 戻り値は `"…"`（長さ1） | FR-02 |
| AC-05 | text="hello", width=0 | `truncate(text, width)` を呼ぶ | `ValueError` が送出される | FR-03 |
| AC-06 | text="hello", width=-1 | `truncate(text, width)` を呼ぶ | `ValueError` が送出される | FR-03 |

## 前提
- `text` は `str` 型、`width` は `int` 型で呼び出されることを前提とし、型不一致時の挙動（`TypeError` 送出など）は本要件の対象外とする。
- 文字数のカウントは Python の `len()` が返すコードポイント数に基づくものとし、結合文字や絵文字（サロゲートペア等）による見た目の文字数のズレは考慮しない。
- `text` が空文字列の場合は FR-01 により空文字列がそのまま返る。

## 未確定事項
- `width` に `int` 以外の型（`float` や文字列など）が渡された場合に明示的な型チェック・エラーを行うべきか。
- 全角文字・絵文字など、表示幅と文字数が一致しない文字列への対応が将来的に必要か。
