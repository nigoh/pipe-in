# pipe-in-research：調べものを出典つきでまとめる（見本）

プロジェクトのファイルを読んで調べ、出典つきの報告にまとめ、出典と中身が合っているかを確かめます。
ひな形はなく、この見本が元です。Web は使わず、読むのは対象のプロジェクトのファイルだけです。

## 何をするか

4 つの段で進みます。問いを整える → 調べる → まとめる → 出典と中身の突き合わせ。
報告は成果物（`03_report.md`）と `docs/research/report.md` に書かれます。
突き合わせで合わなければ、直す点を添えて「まとめる」へ戻します（2 回まで）。

## 向く場面と向かない場面

- 向く：「この機能はどこで決まっているか」のように、プロジェクトの中の根拠を集めて報告にしたいとき。
- 向かない：最新の情報を Web で調べたいとき（下の「直し方」で足せます）。コードを直したいとき。

## 必要なもの

- `pipe-in` と `pipe-in-gen`（`pip install -e .`）、Claude Agent SDK を使える状態。
- 依頼メモ（必須）に、調べたいことを書きます。
- 検証の機械の検査は `python` コマンドを使います。`python3` だけの環境では、`pipe.toml` の `command` を書き換えてください。

## 流し方

```bash
pipe-in --pipe examples/research/pipes/pipe-in-research --project <対象のフォルダ> --text "調べたいこと"
```

`--pipe` にはこのフォルダのパスを渡します（リポジトリの直下で流すときの形）。
自分のプロジェクトで使い続けるときは、`pipe-in-research/` を対象の `.pipe-in/pipes/` に写せば、`pipe-in --pipe research` で流せます。
VSCode の拡張の作業台では、「見本から作る」で写せます。

## 段と書ける範囲

| 段 | 成果物 | access | docs_dir | 人の確認 |
| --- | --- | --- | --- | --- |
| `frame` | `01_question.md` | read | — | あり |
| `gather` | `02_findings.md` | read | — | なし |
| `summarize` | `03_report.md` と `docs/research/report.md` | docs | docs/research | あり |
| `verify` | `04_verify.md` | read | — | なし |

「まとめる」だけが `docs` なのは、検証で差し戻されたときに報告を直せるようにするためです（戻り先が `read` の段だと、直せません）。
Web・MCP・Bash は、どの段でも使えません。

## 費用の目安

| 段 | max_budget_usd | max_turns |
| --- | --- | --- |
| `frame` | $0.5 | 20 |
| `gather` | $2.0 | 60 |
| `summarize` | $1.0 | 30 |
| `verify` | $1.5 | 50 |

1 回通しの上限の合計：$5.0

差し戻しを使い切ったときの上限の合計：$10.0（「まとめる」と「突き合わせ」を 2 回ずつやり直したとき）

**実測はまだありません。** ここの金額は、各段の `max_budget_usd` の合計（上限）で、見積りではありません。審査（`judge`）の費用は検証の段の上限の中に入ります。

## 直し方

- 段の並び・書き込める範囲・確認の有無・上限は `pipe.toml`、各段への指示は `prompts/` のファイルです。
- Web で調べたいときは、「調べる」の段に `web = ["docs.python.org"]` のように調べてよいドメインを足します。足したら、この README の書ける範囲と費用の表も直してください。
- 上限は、実際に流した費用を見て決め直してください。
- 直したら `pipe-in-gen check research --pipes-dir examples/research/pipes` で確かめてください。
