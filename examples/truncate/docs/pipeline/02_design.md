# 設計書：文字列切り詰め関数 truncate

## 方針
- `src/textutil.py` に既存の `normalize_spaces` と同じスタイル（型ヒント・簡潔な日本語 docstring）で関数 `truncate(text: str, width: int) -> str` を追加する。
- ロジックは単純な分岐のみ：
  1. `width < 1` なら `ValueError` を送出。
  2. `len(text) <= width` ならそのまま返す。
  3. それ以外は `text` の先頭 `width - 1` 文字に「…」(U+2026) を連結して返す。
- 新しい依存やヘルパー関数は追加しない。

## 変更・追加するファイル
| パス | 種別（新規/変更） | 役割 |
|---|---|---|
| `src/textutil.py` | 変更 | `truncate(text, width)` 関数を追加 |
| `tests/test_textutil.py` | 新規 | `truncate` の単体テストを追加（`normalize_spaces` のテストは対象外） |

## インタフェースとデータ

```python
def truncate(text: str, width: int) -> str:
    """文字列を width 文字以内に切り詰める。超える場合は末尾を「…」にする。"""
```

- 引数
  - `text: str` — 対象文字列。
  - `width: int` — 許容する最大文字数（戻り値の `len()` がこの値以下になる）。
- 戻り値: `str`
- 例外: `width < 1` の場合に `ValueError` を送出する。
- 既存の `normalize_spaces(text: str) -> str` は変更しない。

## 処理の流れ
1. `width < 1` を判定し、真なら `ValueError` を送出して終了。
2. `len(text) <= width` を判定し、真なら `text` をそのまま返す。
3. 上記以外の場合、`text[: width - 1] + "…"` を返す。

## エラー処理
- `width < 1`（`0` および負数を含む）のとき `ValueError` を送出する（メッセージ内容は要件に規定がないため任意の説明文でよい）。
- `text` / `width` の型不正（`TypeError` 等）は要件のスコープ外のため、明示的なチェックは行わない。

## テスト方針
| AC | 確かめ方 | テストの種類 | テストファイル |
|---|---|---|---|
| AC-01 | `truncate("hello", 10) == "hello"` を assert | 単体 | `tests/test_textutil.py` |
| AC-02 | `truncate("hello", 5) == "hello"` を assert | 単体 | `tests/test_textutil.py` |
| AC-03 | `truncate("hello world", 5) == "hell…"` を assert | 単体 | `tests/test_textutil.py` |
| AC-04 | `truncate("hello", 1) == "…"` を assert | 単体 | `tests/test_textutil.py` |
| AC-05 | `truncate("hello", 0)` が `pytest.raises(ValueError)` で捕捉されることを assert | 単体 | `tests/test_textutil.py` |
| AC-06 | `truncate("hello", -1)` が `pytest.raises(ValueError)` で捕捉されることを assert | 単体 | `tests/test_textutil.py` |

- 追加で、空文字列（`truncate("", 5) == ""`）のケースをFR-01の確認として含めてもよい（前提に明記されているが必須ACではない）。

## テストの実行方法
```
python3 -m pytest -q
```

## 実装の順序
1. `src/textutil.py` に `truncate` 関数を追加する。
2. `tests/test_textutil.py` を新規作成し、AC-01〜AC-06 に対応するテストケースを実装する。
3. `python3 -m pytest -q` を実行し、全テストが成功することを確認する。

## リスクと注意点
- `width - 1` が負になるのは `width < 1` のケースのみであり、そのケースは事前に `ValueError` で弾かれるため、本文切り詰め処理で負のスライスになる心配はない。
- 絵文字・結合文字・サロゲートペア等による見た目の文字数ズレは要件のスコープ外であり、`len()` ベースの実装で問題ない。
- `tests/` ディレクトリが存在しない場合は新規作成する（`__init__.py` は不要、pytest のテスト探索に依存）。
