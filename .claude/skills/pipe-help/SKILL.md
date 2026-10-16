---
name: pipe-help
description: devpipe の使いかたの一覧を出す。Claude Code のコマンド（/pipe-in・プラグインの /devpipe:pipe-build）、devpipe と devpipe-gen の CLI、VSCode 拡張のコマンドを、何をしたいときに何を使うかで案内する。
argument-hint: [知りたいこと（例: パイプ・作図台・再開・--auto）]
disable-model-invocation: true
---

# /pipe-help — devpipe の使いかた

知りたいこと: $ARGUMENTS

## 答え方

- 引数が空なら、下の「一覧」をそのまま見せる（表は崩さない）。最後に「`/pipe-help パイプ` のように付けると、そこだけ詳しく答えます」と1行添える。
- 引数があれば、一覧の中から当てはまる所だけを選び、README.md・vscode/README.md・pipes/README.md の該当する節を読んで、手順を具体的に答える。コマンドは実際の書き方で示す。
- このリポジトリの今の版で確かめられることだけを答える（コマンドやオプションは `devpipe --help`・`devpipe-gen --help` か README で確かめる）。書かれていないことは「書かれていない」と言う。
- 何も実行しない（流す・作る・保存するのは、人に言われてから）。

## 一覧

### Claude Code のコマンド（このリポジトリで開発するとき）

| コマンド | すること |
| --- | --- |
| `/pipe-in <要件メモ>` | devpipe に機能を足す。要件定義 → 設計 → テスト先行 → 実装 → 検証 を段ごとにサブエージェントへ任せて進め、段ごとに止まって確認を取る。進み具合は VSCode の「devpipe: 実行を見る」で見られる |
| `/pipe-in --auto <要件メモ>` | 同じことを、段の区切りで止まらずに最後まで進める（決めきれない点や、利用料のかかる実行の前では止まる。コミットはしない） |
| `/devpipe:pipe-build <目的か直したい点>` | パイプ（段の並び）を会話で作る・直す。プラグイン（`/plugin marketplace add ./` → `/plugin install devpipe@devpipe`）を入れて使う。どのプロジェクトでも使える |
| `/pipe-help [知りたいこと]` | この一覧。知りたいことを付けると、そこだけ詳しく |

### devpipe（流す）

| やりたいこと | コマンド |
| --- | --- |
| 開発フローを流す（要件定義 → 設計 → テスト先行 → 実装 → 検証） | `devpipe --project <対象> --input request.md` |
| 確認なしで最後まで流す | `devpipe --project <対象> --input request.md --yes` |
| チャットから流す（確認で止めて、あとで答える） | `devpipe ... --pause` → `devpipe --project <対象> --review approve` ／ `--review revise --feedback "…"` ／ `--review quit` |
| 途中から再開する | `devpipe --project <対象> --from design`（パイプでは段の名前） |
| 記録だけを書く（段は流さない。/pipe-in が使う） | `devpipe record start --text "…"` → `begin <段>` → `done <段>` → `wait <段>` → `review <段> approved` … → `finish PASSED`（`devpipe record --help`） |
| パイプを流す | `devpipe --pipe <名前> --project <対象> --text "依頼メモ"`（`--pause`・`--review`・`--from` も使える。`--review` のときも `--pipe <名前>` を付ける） |

### devpipe-gen（パイプを作る）

| やりたいこと | コマンド |
| --- | --- |
| ひな形と、作ったパイプの一覧 | `devpipe-gen list --project <対象>` |
| ひな形から作る（dev / diagrams / spec-qa） | `devpipe-gen new <名前> --from <ひな形> --project <対象>` |
| 目的から段を組ませる（Claude が設計する。利用料がかかる） | `devpipe-gen design <名前> --purpose "…" --project <対象>` |
| 定義の誤りを調べる | `devpipe-gen check <名前> --project <対象>` |

作ったパイプは対象の `.devpipe/pipes/devpipe-<名前>/`（pipe.toml・prompts/・README.md）に置かれる（`--pipes-dir` か `DEVPIPE_PIPES_DIR` で変えられる。今までの `pipes/` も探す）。

### VSCode 拡張（コマンドパレット）

| コマンド | すること |
| --- | --- |
| devpipe: 実行を見る | 流している・流した実行を、図と出力で見る（ステータスバーのボタンでも開く） |
| devpipe: パイプを作図する | パイプ作図台を開く。形のブロックを置き、プラグをコンセントに差してつなぎ、各ブロックで Claude に頼むことと SDK の設定を決めて保存する |

### もっと詳しく

- devpipe 全体：README.md（パイプの書き方・検証と差し戻し・分岐と並列・Agent SDK の設定・終了コード）
- VSCode 拡張と作図台：vscode/README.md
- パイプの置き場所とプラグイン：README.md の「パイプ」「Claude Code のプラグイン」
