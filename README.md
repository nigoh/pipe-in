# devpipe

要件メモから **要件定義 → 設計 → テスト先行 → 実装 → 検証** までを、Claude Agent SDK（Python）で順に実行するパイプラインです。テスト駆動（赤 → 緑 → 整理）とドメイン駆動の設計を前提にしています。

実行の進み具合を VSCode のパネルで図として見るプラグインは [`vscode/`](vscode/README.md) にあります。

開発のほかにも、段の並びを自分で決めた **パイプ** をジェネレーターで作って流せます（ソースから図を作る、仕様とソースを突き合わせて QA の観点を出す、など）。→ [パイプ](#パイプ目的に合わせた段の並び)

- 要件定義・設計・テスト先行のあとに、人が内容を確認します（承認 / 修正を依頼 / 中止）。
- テスト先行の段は、製品コードより先に受け入れ基準（AC）ごとのテストを書き、落ちることを確かめます。テストのない AC が残れば差し戻します。
- 検証が不合格なら、検証報告を添えて実装へ差し戻します（既定で最大3回）。
- 段ごとに書き込める範囲を決めてあり、範囲外の書き込みや危ない操作は止めます。

```
要件メモ ─▶ 要件定義 ─[確認]─▶ 設計 ─[確認]─▶ テスト先行（赤）─[確認]─▶ 実装（緑・整理）─▶ 検証 ─▶ 合格
                                                                         ▲                │
                                                                         └──── 不合格 ────┘（最大3回）
```

## 必要なもの

- Python 3.11 以上
- Claude Code にログイン済み（`claude` で一度ログイン）か、`ANTHROPIC_API_KEY` を設定済み
- 対象プロジェクトは git 管理下で、作業用ブランチにしておくのがおすすめです

## インストール

```bash
cd devpipe
python3 -m venv .venv && source .venv/bin/activate
pip install -e .     # devpipe と devpipe-gen が入る
```

## 使い方

```bash
# 要件メモをファイルで渡す
devpipe --project ~/src/myapp --input request.md

# 直接書く
devpipe --project ~/src/myapp --text "ユーザー一覧に CSV 出力ボタンを追加したい"

# 確認なしで最後まで流す
devpipe --project ~/src/myapp --input request.md --yes

# テスト担当の判定に加えて、自分のテストコマンドでも裏付けを取る
devpipe --project ~/src/myapp --input request.md --test-cmd "pytest -q"
```

`devpipe` の代わりに `python -m devpipe` でも動きます。

### 途中から再開する

前の段の文書が残っていれば、その次から始められます。

```bash
devpipe --project ~/src/myapp --from design      # 要件定義書を手で直したあと
devpipe --project ~/src/myapp --from red         # 設計書を手で直したあと
devpipe --project ~/src/myapp --from implement   # 先に書いたテストを手で直したあと
devpipe --project ~/src/myapp --from test        # 検証だけやり直す
```

### 確認の画面

要件定義・設計・テスト先行のあとに、文書の先頭60行を表示して止まります。テスト先行のあとは「このテストが通れば要件を満たすと言えるか」を見てください。ここが実装にとっての仕様になります。

- `Enter`：承認して次の段へ
- `r`：修正してほしい点を書く（空行で終わり）。同じ会話のまま直させて、もう一度確認します
- `q`：中止

### 確認で止めて、あとから答える（チャットから動かすとき）

対話できない所（Claude Code のチャット、CI など）から動かすときは `--pause` を付けます。確認の段まで流したら、入力を待たずに `state.json` の `pending_review`（段・文書・会話の ID）を残して止まります（終了コード 5）。文書を読んで、`--review` で答えると続きから流れます。

```bash
devpipe --project ~/src/myapp --input request.md --pause --test-cmd "pytest -q"   # 要件定義のあとで止まる
devpipe --project ~/src/myapp --review approve --test-cmd "pytest -q"             # 承認 → 設計のあとで止まる
devpipe --project ~/src/myapp --review revise --feedback "AC-03 を分けて"          # 同じ会話のまま直させ、また止まる
devpipe --project ~/src/myapp --review quit                                       # 中止
```

- 記録（`state.json` の `runs`・段のログの番号・費用の合計・注意）は、呼び出しをまたいで続きます。
- `--test-cmd`・`--max-retries` は記録に残らないので、`--review` のたびに同じものを渡してください。
- 止まっている間の `final` は空のままです（VSCode のパネルでは「次を待っている」と出ます）。

## パイプ（目的に合わせた段の並び）

上の開発の5段のほかに、段の並びを自分で決めた **パイプ** を作って流せます。
パイプは1つのフォルダ（`pipes/devpipe-<名前>/`）で、**ジェネレーター**（`devpipe-gen`）がひな形から作ります。

```
generator/                 ジェネレーター（環境の検出・ひな形・パイプの生成と検査）
└─ templates/              ひな形（dev / diagrams / spec-qa）
pipes/                     作ったパイプ（1パイプ＝1フォルダ。.gitignore 済み）
└─ devpipe-diagrams/
   ├─ pipe.toml            段の並び・書き込める範囲・確認の有無
   ├─ prompts/             段ごとの指示文
   └─ README.md            何をするパイプか・流し方
```

```bash
devpipe-gen list                                                # ひな形と、作ったパイプの一覧
devpipe-gen new diagrams --from diagrams --project ~/src/myapp  # pipes/devpipe-diagrams/ を作る
devpipe-gen check diagrams --project ~/src/myapp                # 定義の誤りを調べる
devpipe --pipe diagrams --project ~/src/myapp --text "注文の流れを中心に"
```

Claude Code では `/pipe-craft <目的>` で、目的を聞きながら作れます。

- `devpipe-gen new` は対象のファイル（`pyproject.toml`・`package.json`・`go.mod`・`Cargo.toml`、`src/`・`docs/` など）を見て、テストのコマンドやソース・文書の場所を埋めます。対象の絶対パスはパイプに書きません。
- 同じ名前のパイプがあれば作りません（`--force` で作り直し）。
- パイプは devpipe のリポジトリの `pipes/` に置きます（clone して `pip install -e .` で使う前提）。`DEVPIPE_PIPES_DIR` か `--pipes-dir` で変えられます。
- `pipes/` の中身は `.gitignore` 済みです。指示文に対象プロジェクトの事情が入りやすいためです。共有したいものは、中身を確かめてから `generator/templates/` にひな形として足してください。

### ひな形

| 名前 | 段 | 作るもの |
|---|---|---|
| `dev` | 要件定義 → 設計 → テスト先行 → 実装 → 検証 | 上の開発フローそのもの。テストのコマンドを環境から埋める |
| `diagrams` | ソースの調査 → 図を描く → 図とソースの突き合わせ | フロー図・シーケンス図・状態遷移図・クラス図（Mermaid）|
| `spec-qa` | 仕様とソースの対応 → 食い違いと検討事項 → QA の観点とテストケース | 対応表・食い違いの一覧・テストケース案。どの段もコードは書かない |

### 定義の書き方（`pipe.toml`）

```toml
[pipe]
kind = "linear"            # "linear"（下の段を順に流す）か "dev"（組み込みの開発フロー）
label = "ソースから図を作る"
input = "optional"         # 依頼メモが required / optional / none

[[stages]]
name = "survey"            # 英小文字・数字・-
label = "ソースの調査"
output = "01_survey.md"    # 成果物（記録の置き場所の中のファイル名）
access = "read"            # 書き込める範囲の型（下の表）
review = true              # この段のあとで人の確認を取る
prompt_file = "prompts/01_survey.md"   # パイプのフォルダの中。短ければ prompt = "..." で直接書いてもよい
# bash = true              # Bash を使わせる（危ない操作はいつも止める）
# model = "sonnet" / max_turns = 100 / max_budget_usd = 1.0
```

| access | 書き込める範囲 |
|---|---|
| `read` | 自分の成果物だけ |
| `docs` | 自分の成果物と `docs_dir` の下（`docs_dir` はプロジェクトの中） |
| `tests` | 自分の成果物とテストファイル |
| `code` | 自分の成果物と製品コード（テストファイルは除く） |

- 段は定義の順に流れ、各段には依頼メモと前の段の成果物の場所が渡されます。差し戻しはありません（前へ進むだけ）。
- 記録は対象の `<work_dir>/<パイプ名>/` に置かれます（例: `docs/pipeline/diagrams/`）。開発フローの記録は上書きしません。VSCode のパネルでも、開発フローと切り替えて見られます。
- 確認・`--pause`・`--review`・`--from <段の名前>`・`--yes` は開発フローと同じように使えます（`--review` のときも `--pipe` を付けてください）。
- Web・PowerShell・MCP などは使えず、`protected_paths` とパイプのフォルダはどの段も書けません。定義でこれを緩めることはできません。
- `kind = "dev"` の定義に書けるのは `test_command` だけです（`--test-cmd` → パイプの定義 → `pipeline.toml` の順に優先）。段ごとのモデルなどは `pipeline.toml` で決めます。

## 作られるファイル
## 作られるファイル

対象プロジェクトの `docs/pipeline/` に置かれます（`work_dir` で変更可）。

| ファイル | 中身 | 書く段 |
|---|---|---|
| `00_input.md` | 渡した要件メモ | パイプライン |
| `01_requirements.md` | 要件定義書（機能要件 FR、受け入れ基準 AC） | 要件定義 |
| `02_design.md` | 設計書（ドメインモデル、層ごとの置き場所、入口の型、AC とテストの対応、テストの実行方法） | 設計 |
| `03_red_tests.md` | テスト先行の記録（AC とテストの対応、落ちたことの確認） | テスト先行 |
| `04_implementation.md` | 実装の記録（回ごとに追記） | 実装 |
| `05_test_report.md` | 検証報告（AC ごとの結果） | 検証 |
| `99_summary.md` | 全体の結果、段ごとのターン数・費用・時間、トークンの内訳、モデル別、環境、利用枠 | パイプライン |
| `state.json` | 実行の記録（機械向け）。段の並び（`stages`：名前・表示名・成果物・確認の有無）、段ごとの `metrics`、全体の `usage_summary`、注意（`warnings`）、確認待ち（`pending_review`）を含む | パイプライン |
| `logs/*.jsonl` | 各段のやり取りの全記録 | パイプライン |

`examples/truncate/` に、小さなプロジェクトで実際に流した結果があります（要件メモから合格まで、4段で約2分・約$0.85）。これはテスト先行の段を足す前（v0.1）の結果なので、ファイル名と段の数が今と違います。

## 段ごとの役割と書き込める範囲

| 段 | できること | 書き込める範囲 |
|---|---|---|
| 要件定義 | コードを読む | `01_requirements.md` だけ |
| 設計 | コードを読む | `02_design.md` と、`domain_dir` を設定していればドメインの文書 |
| テスト先行 | 読む・書く・コマンド実行 | テストファイルと `03_red_tests.md`。**製品コードは書けない** |
| 実装 | 読む・書く・コマンド実行 | 製品コードと `04_implementation.md`。**テストファイルとドメインの文書は書けない** |
| 検証 | 読む・書く・コマンド実行 | テストファイルと `05_test_report.md`。**製品コードは書けない** |

`protected_paths` に書いたパスは、どの段も書けません。

実装とテストの担当を分けているのは、実装の担当が「テストを都合よく直して通す」ことを防ぐためです。実装の担当はテストに不満があれば、実装の記録に「テストへの異議」として書き、次の検証の段がそれを判断します。

テスト先行の段は、判定（`red` / `blocked`）と「AC とテストの対応」を構造化出力で返します。パイプラインは要件定義書から `AC-数字` を拾い、テストのない AC があれば同じ会話で一度だけ補わせ、それでも残れば止めます（終了コード 3）。`test_command` があれば、テスト先行のあとにも実行し、通ってしまったら「赤になっていません」と注意を残します（止めはしません）。

テストファイルの判定は、`tests/`・`test/`・`__tests__/`・`spec/` の中にあるか、`test_*.py`・`*_test.py`・`*.test.*`・`*.spec.*`・`conftest.py` などの名前かで行います。足りなければ `extra_test_globs` に追加してください。

### どの段でも止める操作

`git push`、`git reset --hard`、`git clean -f`、ブランチの切り替え、再帰的な削除（`rm -r`）、`sudo`、`curl`・`wget`・`ssh` などの外部通信、パッケージの公開、プロジェクトの外への書き込み、Web 検索と Web 取得。

また、段ごとに許したツール（`devpipe/dev/specs.py`・`devpipe/pipe/specs.py` の `allowed_tools`）と、読むだけの道具（`Read`・`Glob`・`Grep`・`Skill`・`ToolSearch`・`TodoWrite`）以外は、すべて止めます。PowerShell・MCP のツール・サブエージェント（`Task`）などから、書き込み範囲や危ない操作の判定をすり抜けられないようにするためです。PowerShell は最初から使えないツールにも入れています。

止めた操作はその場で表示され、`99_summary.md` にも残ります。仕組みは `devpipe/engine/guard.py` の PreToolUse フックで、すべてのツールに掛かり、自動承認したツールにも効きます。

### まとめに出る使用量

各段の最後に Claude Code が返す結果（`ResultMessage`）と、途中の利用枠のイベント（`RateLimitEvent`）、開始時の環境（`SystemMessage` の `init`）から集めます（`devpipe/usage/metrics.py`、表は `devpipe/usage/report.py`）。

| 節 | 中身 |
|---|---|
| トークンの内訳 | 段ごとの入力・キャッシュ書き込み・キャッシュ読み込み・出力・うち thinking・キャッシュ再利用率・API 待ち時間と合計 |
| モデル別 | モデルごとのトークンと費用 |
| 環境 | 使われたモデル、Claude Code の版、認証の出どころ、許可のモード、費用の根拠、途中で止まった段 |
| 利用枠 | 5時間枠・7日枠の使用率（開始 → 終了。途中で枠が戻ったときは最大値も）、枠が戻る時刻、超過利用の可否 |

費用は定価での見積もり（`costBasis: list`）です。サブスクリプションでログインしている場合は、利用枠の使用率のほうが実際の負担に近い値です。

## 設定（pipeline.toml）

対象プロジェクトの直下に置くと読み込みます。見本はこのフォルダの `pipeline.toml` です。

```toml
[pipeline]
work_dir = "docs/pipeline"
max_retries = 3                 # 実装への差し戻しの上限（3 なら実装は最大4回）
test_command = "pytest -q"      # テストの段のあとに実行する確認用コマンド（任意）

[stages.requirements]
model = "opus"                  # 段ごとにモデルを変えられる
max_turns = 40
max_budget_usd = 1.0            # 段ごとの費用の上限（概算）

[stages.implement]
model = "sonnet"
```

ほかの項目:

| 項目 | 意味 |
|---|---|
| `domain_dir` | 用語集・コンテキストマップを置くフォルダ。要件定義と設計の段が読み、設計の段だけが更新できる |
| `setting_sources` | SDK に読ませる設定の出どころ。`["project"]` で対象の CLAUDE.md・`.claude/`（規約・フック）を各段に効かせる |
| `protected_paths` | どの段も書き換えられないパス（glob） |
| `extra_test_globs` | テストファイルとみなす追加のパターン |

段の名前は `requirements` / `design` / `red` / `implement` / `test` です。

## 終了コード

| コード | 意味 |
|---|---|
| 0 | 検証まで合格 |
| 1 | 差し戻しの上限までテストが通らなかった |
| 2 | 確認の段階で中止した |
| 3 | 段の実行が失敗した（文書が作られない、上限に達した、テストのない AC が残ったなど） |
| 4 | テストを実行できなかった（環境の問題など。差し戻しはしない） |
| 5 | 人の確認を待っている（`--pause` のとき。`--review` で続ける） |
| 130 | Ctrl+C で中断（`--from` で再開できます） |

## 中身を直したいとき

| やりたいこと | 場所 |
|---|---|
| 開発フローの各段への指示（文書の構成、守ること） | `devpipe/dev/prompts/*.md` |
| 開発フローの段の順番、確認、差し戻しの流れ | `devpipe/dev/pipeline.py` |
| 開発フローの段ごとのツールと書き込み範囲 | `devpipe/dev/specs.py` |
| どのパイプにも共通の流れ（記録・確認・まとめ） | `devpipe/engine/pipeline.py` |
| 止める操作 | `devpipe/engine/guard.py` の `DANGEROUS_BASH` |
| SDK の呼び出し | `devpipe/engine/runner.py` |
| パイプの読み込み・検査・流れ・権限の型 | `devpipe/pipe/` |
| パイプの生成・環境の検出・ひな形 | `generator/`（`devpipe-gen`）・`generator/templates/` |

テストは `pip install -e '.[dev]' && pytest` で実行できます。SDK を呼ばずに、段の順番・確認・差し戻し・書き込み制限を確かめます。

## 注意

- 費用は SDK が返す概算です。実際の請求とはずれることがあります。
- Claude Code のセッションの中（Bash ツール）から起動すると、子のセッションの会話が保存されないことがあります。普段のターミナルから実行してください。
- 対象プロジェクトの CLAUDE.md・`.claude/` の規約やフックを各段に効かせたいときは、`setting_sources = ["project"]` を設定してください。
- Windows で日本語の表示が崩れるときは `PYTHONUTF8=1` を設定してください（`feature.sh`・`feature.ps1` は設定済み）。
- 動作を確認した環境：Python 3.13、claude-agent-sdk 0.2.159〜0.2.168、Claude Code 2.1.301。
