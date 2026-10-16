# テスト報告（1 回目）

## 判定
pass

## 実行したコマンド
```
python3 -m pytest -q
```

## AC ごとの結果
| AC | テスト | 結果 | メモ |
|---|---|---|---|
| AC-01 | `test_ac01_no_truncation_when_shorter_than_width` | 合格 | `truncate("hello", 10) == "hello"` |
| AC-02 | `test_ac02_no_truncation_when_equal_to_width` | 合格 | `truncate("hello", 5) == "hello"` |
| AC-03 | `test_ac03_truncated_with_ellipsis` | 合格 | `truncate("hello world", 5) == "hell…"`、長さ5も確認 |
| AC-04 | `test_ac04_width_one_returns_ellipsis_only` | 合格 | `truncate("hello", 1) == "…"`、長さ1も確認 |
| AC-05 | `test_ac05_width_zero_raises_value_error` | 合格 | `truncate("hello", 0)` で `ValueError` |
| AC-06 | `test_ac06_negative_width_raises_value_error` | 合格 | `truncate("hello", -1)` で `ValueError` |
| （参考・前提） | `test_empty_string_returns_empty_string` | 合格 | 空文字列のケース（FR-01 の前提事項、必須ACではないが設計書の推奨に従い追加） |

`tests/test_textutil.py` は新規作成（実装担当が作成予定としていたが未着手だったため、設計書の指定通りに作成した）。

実行結果：`7 passed in 0.01s`

## 不合格の詳細
なし。

## 実装の担当への指摘
なし。設計書の処理の流れ（`width < 1` で `ValueError`、`len(text) <= width` ならそのまま返す、それ以外は `text[: width - 1] + "…"`）通りに実装されており、全 AC を満たしている。
