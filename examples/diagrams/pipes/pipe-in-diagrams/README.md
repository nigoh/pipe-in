# pipe-in-diagrams：ソースから図を作る（見本）

ソースを調べ、フロー図・シーケンス図・状態遷移図・クラス図を Mermaid で描き、図とソースが合っているかを確かめます。
図は Markdown の中に書くので、GitHub や VSCode の Markdown のプレビューでそのまま図として見えます。
`generator/templates/diagrams/` を決まった値で埋めた写しに、各段の上限（`max_turns`・`max_budget_usd`）を足した見本です。

## 何をするか

3 つの段で進みます。ソースの調査 → 図を描く → 図とソースの突き合わせ。
図は対象プロジェクトの `docs/diagrams/` に書かれ、成果物は `docs/pipeline/diagrams/` に置かれます。
突き合わせで合わなければ、直す点を添えて「図を描く」へ戻します（2 回まで）。

## 向く場面と向かない場面

- 向く：初めて読むプロジェクトの全体像をつかみたいとき。説明用の図の下書きがほしいとき。
- 向かない：図の見た目を整えたいとき（Mermaid の記法の範囲です）。ソースが無い設計だけの段階。

## 必要なもの

- `pipe-in` と `pipe-in-gen`（`pip install -e .`）、Claude Agent SDK を使える状態。
- 検証の機械の検査は `python` コマンドを使います。`python3` だけの環境では、`pipe.toml` の `command` を書き換えてください。
- 対象のプロジェクトのフォルダ（読むだけで、書くのは `docs/` の中だけです）。

## 流し方

```bash
pipe-in --pipe examples/diagrams/pipes/pipe-in-diagrams --project <対象のフォルダ> --text "図にしたい範囲や観点（省いてもよい）"
```

`--pipe` にはこのフォルダのパスを渡します（リポジトリの直下で流すときの形）。
自分のプロジェクトで使い続けるときは、`pipe-in-diagrams/` を対象の `.pipe-in/pipes/` に写せば、`pipe-in --pipe diagrams` で流せます。
VSCode の拡張の作業台では、「見本から作る」で写せます。

## 段と書ける範囲

| 段 | 成果物 | access | docs_dir | 人の確認 |
| --- | --- | --- | --- | --- |
| `survey` | `01_survey.md` | read | — | あり |
| `draw` | `02_diagrams.md` と図のファイル | docs | docs/diagrams | あり |
| `verify` | `03_verify.md` | read | — | なし |

`read` の段は、成果物のほかを書けません。`docs` の段は、成果物と `docs_dir` の中だけを書けます。

## 費用の目安

| 段 | max_budget_usd | max_turns |
| --- | --- | --- |
| `survey` | $1.0 | 40 |
| `draw` | $2.0 | 60 |
| `verify` | $1.0 | 40 |

1 回通しの上限の合計：$4.0

差し戻しを使い切ったときの上限の合計：$10.0（「図を描く」と「突き合わせ」を 2 回ずつやり直したとき）

**実測はまだありません。** ここの金額は、各段の `max_budget_usd` の合計（上限）で、見積りではありません。審査（`judge`）の費用は検証の段の上限の中に入ります。

## 直し方

- 段の並び・書き込める範囲・確認の有無・上限は `pipe.toml`、各段への指示は `prompts/` のファイルです。
- 上限は、実際に流した費用を見て決め直してください。
- 直したら `pipe-in-gen check diagrams --pipes-dir examples/diagrams/pipes` で確かめてください。
