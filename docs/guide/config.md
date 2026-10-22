# 設定（pipeline.toml）

[ガイドの目次](README.md) · [README](../../README.md) — 対象プロジェクトに置く設定ファイルの説明です。

対象プロジェクトの直下に置くと読み込みます。見本はリポジトリの直下の [`pipeline.toml`](../../pipeline.toml) です。

```toml
[pipeline]
work_dir = "docs/pipeline"
max_retries = 3                 # 実装への差し戻しの上限（3 なら実装は最大4回）
test_command = "pytest -q"      # テストの段のあとに実行する確認用コマンド（任意）
max_buffer_mb = 32              # SDK の受信バッファの上限（MB。既定 32）

[stages.requirements]
model = "opus"                  # 段ごとにモデルを変えられる
max_turns = 40
max_budget_usd = 1.0            # 段ごとの費用の上限（概算）

[stages.implement]
model = "sonnet"
```

項目の意味（上の例に無い項目と、例の `max_buffer_mb` のくわしい説明）:

| 項目 | 意味 |
|---|---|
| `domain_dir` | 用語集・コンテキストマップを置くフォルダ。要件定義と設計の段が読み、設計の段だけが更新できる |
| `setting_sources` | SDK に読ませる設定の出どころ。`["project"]` で対象の CLAUDE.md・`.claude/`（規約・フック）を各段に効かせる |
| `protected_paths` | どの段も書き換えられないパス（glob） |
| `extra_test_globs` | テストファイルとみなす追加のパターン |
| `max_buffer_mb` | SDK が1つのメッセージとして受け取れる大きさの上限（MB。1 以上の整数。既定 32）。どの段・どのパイプにも同じ値が効く。画像は base64 でメッセージに入るので、段が大きい画像を読むと超えることがある。超えるとその段を失敗にして（終了コード 3）、直し方を出す。そのときは、画像を小さくするか、必要な所だけを切り出してから読ませる。今の値が 32 より小さいなら、値を大きくしてもよい（API の1つのリクエストの上限も 32MB なので、32 より上げても通らないおそれがある）。上限は前もって確保する量ではなく、大きいメッセージが来たときだけ使う |

段の名前は `requirements` / `design` / `red` / `implement` / `test` です。
