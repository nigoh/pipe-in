# examples/：パイプの見本

流してみられるパイプの見本です。そのまま流しても、自分のプロジェクトに写して直しても使えます。

## 流せる見本

| 名前 | 用途 | 段 | 上限の合計 | くわしく |
| --- | --- | --- | --- | --- |
| `diagrams` | ソースを読んで Mermaid の図を作り、図とソースの合いを確かめる | 3 | $4.0（差し戻しを使い切ると $10.0） | [README](diagrams/pipes/pipe-in-diagrams/README.md) |
| `spec-qa` | 仕様書とソースを突き合わせ、食い違いと QA の観点を書く | 3 | $4.5 | [README](spec-qa/pipes/pipe-in-spec-qa/README.md) |
| `research` | プロジェクトのファイルを調べ、出典つきの報告にまとめる | 4 | $5.0（差し戻しを使い切ると $10.0） | [README](research/pipes/pipe-in-research/README.md) |

上限の合計は、各段の `max_budget_usd` の合計です。**実測はまだありません。** 見積りではなく、上限として読んでください。

## 流し方

見本のフォルダのパスを `--pipe` に渡します（リポジトリの直下で流すときの形）。

```bash
pipe-in --pipe examples/diagrams/pipes/pipe-in-diagrams --project <対象のフォルダ> --text "図にしたい範囲"
```

自分のプロジェクトで使い続けるときは、`pipe-in-<名前>/` を対象の `.pipe-in/pipes/` に写します。そうすると、名前だけで流せます。

```bash
pipe-in --pipe diagrams --project <対象のフォルダ> --text "図にしたい範囲"
pipe-in --pipe spec-qa --project <対象のフォルダ> --text "仕様書は docs/spec/order.md"
pipe-in --pipe research --project <対象のフォルダ> --text "調べたいこと"
```

VSCode の拡張の作業台では、「見本から作る」で、この 3 つを自分のプロジェクトに写せます（[VSCode の拡張](../docs/guide/vscode.md)）。
定義の検査は `pipe-in-gen check <名前> --pipes-dir examples/<名前>/pipes` です。

## 選び方

| やりたいこと | 見本 |
| --- | --- |
| プロジェクトの全体像を図で見たい | `diagrams` |
| 仕様書と実装の食い違いを洗い出したい | `spec-qa` |
| プロジェクトの中の根拠を集めて報告にしたい | `research` |

## そのほかの見本

- `video/`：動画を作るパイプ。ffmpeg や Playwright が要るので、拡張では写せません（[パイプ](../docs/guide/pipes.md)）。
- `truncate/`：`pipe-in` の開発フローを流した記録の見本。

見本の作り方・直し方は [パイプ](../docs/guide/pipes.md) にあります。
`diagrams`・`spec-qa` は `generator/templates/` のひな形を写したもので、ひな形を直したら見本も合わせます（`tests/test_examples.py` が食い違いを見つけます）。
