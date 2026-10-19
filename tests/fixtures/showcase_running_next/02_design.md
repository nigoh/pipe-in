# 設計：ユーザー一覧の CSV 出力

## 置き場所

| 置くもの | 場所 |
| --- | --- |
| CSV を組み立てる関数 `export_users_csv(users)` | `src/users/export.py` |
| 出力の入口（一覧と同じ絞り込みを使う） | `src/users/views.py` |
| ボタン | `templates/users/list.html` |

## AC とテストの対応

| AC | テスト |
| --- | --- |
| AC-01 | `tests/test_users_export.py::test_ac01_button_downloads_csv` |
| AC-02 | `tests/test_users_export.py::test_ac02_utf8_with_bom` |
| AC-03 | `tests/test_users_export.py::test_ac03_column_order` |
