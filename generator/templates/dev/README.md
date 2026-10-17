# pipe-in-{{name}}：開発

要件メモから、要件定義 → 設計 → テスト先行 → 実装 → 検証 を順に流し、検証に通るまで実装へ差し戻します。
段の中身は pipe-in に組み込みです（pipe-in の README の「使い方」を見てください）。

## 流し方

```bash
pipe-in --pipe {{name}} --project <対象のフォルダ> --input request.md
```

## 直し方

- テストのコマンドは `pipe.toml` の `test_command` で変えられます。
- 段ごとのモデル・ターン数・費用の上限は、対象プロジェクトの `pipeline.toml` の `[stages.<段>]` で決めます。
