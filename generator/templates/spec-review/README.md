# pipe-in-{{name}}：仕様書のレビュー

仕様書を読み、素人の質問と視点別の検査で指摘を集め、引用と出典を機械で確かめて、人に聞く質問票（CSV）にまとめます。
どの指摘にも、仕様書の本文からの引用と、出典の台帳の ID が付きます。

## 段

| 段 | 成果物 | 書き込める範囲 | 人の確認 | モデル |
|---|---|---|---|---|
| `naive`（素人の質問） | `01_naive.json` | 成果物だけ | なし | haiku |
| `knowledge`（知識の下ごしらえ） | `02_knowledge.md` と知識の置き場 | 成果物と `docs/spec-review/knowledge/` | あり | sonnet |
| `quality`（品質の検査） | `03_quality.json` | 成果物だけ | なし（同時に流れる） | haiku |
| `gap`（網羅の検査） | `04_gap.json` | 成果物だけ | なし（同時に流れる） | haiku |
| `user`（利用者の視点） | `05_user.json` | 成果物だけ | なし（同時に流れる） | haiku |
| `tester`（テスターの視点） | `06_tester.json` | 成果物だけ | なし（同時に流れる） | haiku |
| `designer`（設計者の視点） | `07_designer.json` | 成果物だけ | なし（同時に流れる） | haiku |
| `operations`（運用の視点） | `08_operations.json` | 成果物だけ | なし（同時に流れる） | haiku |
| `verify`（根拠の確認） | `09_findings.json` | 成果物だけ | なし | sonnet |
| `report`（まとめと質問票） | `10_report.md` と `questionnaire.csv` | 成果物と `docs/spec-review/out/questionnaire.csv` | あり | sonnet |

どの段も、Bash・Web・MCP は使えません。

## 仕様書の置き場所

仕様書は、対象プロジェクトの `docs/spec-review/spec.md` に、Markdown 1ファイルで置きます。複数のファイルに分かれているときは、1つにまとめるか、`pipe.toml` の `verify` の `command` に `--spec` を足してください（出典の台帳の `SRC-001` の `file` は `spec.md` です）。
Word・Excel・PDF は読めません。Markdown に直してから置いてください。

## 流し方

```bash
pipe-in --pipe {{name}} --project <対象のフォルダ> --text "見てほしい範囲や背景（省いてもよい）"
```

途中から流し直すときは、`--from <段の名前>`（例：`--from verify`）を付けます。`knowledge` と `report` のあとで、人の確認が入ります。

## 成果物と文書の置き場所

- 段の成果物：`docs/pipeline/{{name}}/`
- 知識（用語集・ドメインモデル・論点・出典の台帳）：`docs/spec-review/knowledge/`
- 質問票と報告の置き場：`docs/spec-review/out/`（`questionnaire.csv`）

## 指摘の検査（findings-check）

`verify` の段は、終わったあとに `pipe-in-gen findings-check` を流して、指摘の形・出典・引用が仕様書の本文と一致するかを、LLM を使わずに確かめます。合わなければ、問題の行を添えて `verify` を流し直します（2回まで）。`pipe-in-gen` コマンドを使います。`report` の質問票の検査は `python` を使います。

- `work_dir` を変えているときは、`pipe.toml` の `verify` の `command` にある `docs/pipeline/{{name}}/` を、実際の置き場所に書き換えてください。
- `findings-check` が無い古い版の `pipe-in-gen` では、`command` が失敗し、流し直しが2回あったあと終了コード 1 で止まります。`pipe-in-gen --help` に `findings-check` が出るか確かめてください。
- `python` が無い・`python3` だけの環境では、`report` の `command` を `python3 -c …` などに書き換えてください。

## 役割の入れ外し

`pipe.toml` から、その段の `[[stages]]` の塊（その行から、次の `[[stages]]` の手前まで）を消すと、その段が外れます。

- 消してよい：`naive`、検査役の6段（`quality`・`gap`・`user`・`tester`・`designer`・`operations`）のどれか。6段を全部消してもかまいません。
- 消してはいけない：`knowledge`・`verify`・`report`。`knowledge` は出典の台帳を作り、`verify` は台帳を使って引用と出典の検査をし、`report` は質問票を作ります。どれが欠けても、台帳や検査が動きません。
- 消したあとは、`pipe-in-gen check {{name}} --project <対象のフォルダ>` で確かめてください。

## 素人質問者の注意

`naive` に知識の置き場（`docs/spec-review/knowledge/`）を読ませないのは、指示文の決まりだけで、仕組みの制限ではありません。`--from` で途中から流し直すと、知識の置き場がすでにあります。素人の目を保ちたいときは、最初から流してください。

## 費用の目安

仕様書の長さで変わります。段ごとの費用は `state.json` に残ります。まず短い仕様書で1回流して、費用を見てください。

## 質問票

`questionnaire.csv` は UTF-8 で、先頭に BOM が付きます。Excel で開いて文字が化けるときは、「データの取り込み」から文字コードに UTF-8 を選んでください。列は8つです（指摘ID・重大度・質問・回答の型・選択肢・場所・引用・回答）。

## 直し方

- 段の並び・書き込める範囲・確認の有無は `pipe.toml`、各段への指示は `prompts/` のファイルです。
- 直したら `pipe-in-gen check {{name}} --project <対象のフォルダ>` で確かめてください。
- ひな形は写しです。あとから pipe-in 側の `spec-review` が直っても、すでに写したパイプには届かないので、必要なら写し直すか、手で直してください。
