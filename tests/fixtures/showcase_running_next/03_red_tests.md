# テスト先行の記録

| AC | テスト | 落ちた理由 |
| --- | --- | --- |
| AC-01 | `test_ac01_button_downloads_csv` | 出力の入口がまだ無い（404） |
| AC-02 | `test_ac02_utf8_with_bom` | `export_users_csv` がまだ無い |
| AC-03 | `test_ac03_column_order` | `export_users_csv` がまだ無い |

流したコマンド：`pytest -q tests/test_users_export.py`（3 failed）
