# 実装記録

## 実装 1 回目
### 変更したファイル
- `src/textutil.py`: `truncate(text: str, width: int) -> str` 関数を追加。

### 設計からの差分と理由
- なし。設計書の処理の流れ（`width < 1` で `ValueError`、`len(text) <= width` ならそのまま返す、それ以外は `text[: width - 1] + "…"`）通りに実装した。

### 確認したこと（実行したコマンドと結果）
- `python3 -m pytest -q` を実行 → `tests/` 未作成のため `no tests ran in 0.00s`（テストファイルは別担当が作成予定のため未着手）。
- 以下のワンライナーで AC-01〜AC-06 相当の挙動を手動確認し、`OK` を得た。
  ```
  python3 -c "
  from src.textutil import truncate
  assert truncate('hello', 10) == 'hello'
  assert truncate('hello', 5) == 'hello'
  assert truncate('hello world', 5) == 'hell…'
  assert truncate('hello', 1) == '…'
  assert truncate('', 5) == ''
  try:
      truncate('hello', 0); assert False
  except ValueError:
      pass
  try:
      truncate('hello', -1); assert False
  except ValueError:
      pass
  print('OK')
  "
  ```

### テストへの異議（あれば）
- なし。
