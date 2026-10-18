<h1>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/pipe-in-logo-dark.svg">
    <img src="docs/assets/pipe-in-logo.svg" alt="pipe-in" width="420">
  </picture>
</h1>

pipe-in は、要件メモから **要件定義 → 設計 → テスト先行 → 実装 → 検証** を Claude Agent SDK（Python）で順に流し、段の区切りで人が確かめながら進める道具です。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/run-panel-dark.png">
  <img src="docs/assets/run-panel-light.png" alt="VSCode のパネル。左に開発フローの段の図（要件定義 → 設計 → テスト先行 → 実装 → 検証。修正の依頼1回・差し戻し1回）、右に検証の出力・成果物・使用量" width="900">
</picture>

<sub>VSCode の拡張のパネル。見本の記録（数字は見本）を拡張の本物の画面で写したもの。</sub>

- 段の区切りで止まり、人が 承認 / 修正を依頼 / 中止 を選びます。→ [使い方](#使い方)
- テストを先に書かせて赤を確かめ、検証で不合格なら実装へ差し戻します（既定で最大3回）。→ [開発フローの流れ](#開発フローの流れ)
- 段ごとに書ける範囲を決め、範囲外の書き込みや危ない操作は止めます。→ [安全のしくみ](#安全のしくみ)
- 進み具合と使用量を VSCode のパネルで図として見られます。パイプは作業台で組み立てます。→ [VSCode の拡張](#vscode-の拡張)
- 段の並びを自分で決めた「パイプ」を作って流せます（図を作る・仕様とソースの突き合わせなど）。→ [パイプ](#パイプ目的に合わせた段の並び)
- 費用・トークン・利用枠を、段ごとに記録に残します。→ [記録と使用量](#記録と使用量)

**目次**：[すぐ試す](#すぐ試す) · [使い方](#使い方) · [VSCode の拡張](#vscode-の拡張) · [パイプ](#パイプ目的に合わせた段の並び) · [安全のしくみ](#安全のしくみ) · [記録と使用量](#記録と使用量) · [設定](#設定pipelinetoml) · [終了コード](#終了コード) · [前の名前から移る](#migrate) · [中身を直したいとき](#中身を直したいとき) · [注意](#注意) · [ライセンス](#ライセンス)

## すぐ試す

### 必要なもの

- Python 3.11 以上
- Claude Code にログイン済み（`claude` で一度ログイン）か、`ANTHROPIC_API_KEY` を設定済み
- 対象プロジェクトは git 管理下で、作業用ブランチにしておくのがおすすめです

### 入れる

```bash
# リポジトリを手元に写す
git clone https://github.com/nigoh/pipe-in.git
cd pipe-in

# 仮想環境を作る
python -m venv .venv
# 仮想環境に入る（どちらか1つ）
. .venv/Scripts/activate        # Windows の Git Bash
source .venv/bin/activate       # macOS / Linux

# 入れる
pip install -e .                # pipe-in と pipe-in-gen が入る
```

前の名前のころに入れていたときは、[移行の節](#migrate)の手順で入れ直してください。

### 最初の1回

```bash
# 対象のプロジェクトで、要件メモから開発フローを流す
pipe-in --project ~/src/myapp --text "ユーザー一覧に CSV 出力ボタンを追加したい"
```

要件定義のあとで止まり、文書の先頭を見せて確認を求めます（[確認の画面](#確認の画面)）。記録は対象の `docs/pipeline/` に残ります（[作られるファイル](#作られるファイル)）。

> [!IMPORTANT]
> 段ごとに Claude Agent SDK を呼ぶので、利用料がかかります。対象は git 管理下にして、作業用のブランチで流してください。

## 使い方

### 開発フローの流れ

- 要件定義・設計・テスト先行のあとに、人が内容を確認します（承認 / 修正を依頼 / 中止）。
- テスト先行の段は、製品コードより先に受け入れ基準（AC）ごとのテストを書き、落ちることを確かめます。テストのない AC が残れば差し戻します。
- 検証が不合格なら、検証報告を添えて実装へ差し戻します（既定で最大3回）。
- 段ごとに書き込める範囲を決めてあり、範囲外の書き込みや危ない操作は止めます。

テスト駆動（赤 → 緑 → 整理）とドメイン駆動の設計を前提にしています。

```
要件メモ ─▶ 要件定義 ─[確認]─▶ 設計 ─[確認]─▶ テスト先行（赤）─[確認]─▶ 実装（緑・整理）─▶ 検証 ─▶ 合格
                                                                         ▲                │
                                                                         └──── 不合格 ────┘（最大3回）
```

### 流す

```bash
# 要件メモをファイルで渡す
pipe-in --project ~/src/myapp --input request.md

# 直接書く
pipe-in --project ~/src/myapp --text "ユーザー一覧に CSV 出力ボタンを追加したい"

# 確認なしで最後まで流す
pipe-in --project ~/src/myapp --input request.md --yes

# テスト担当の判定に加えて、自分のテストコマンドでも裏付けを取る
pipe-in --project ~/src/myapp --input request.md --test-cmd "pytest -q"
```

> [!WARNING]
> `--yes` は確認なしで最後まで流します。人が見ないままコードが書き換わり、費用もかかります。

`pipe-in` の代わりに `python -m pipe_in` でも動きます。

### 途中から再開する

前の段の文書が残っていれば、その次から始められます。

```bash
pipe-in --project ~/src/myapp --from design      # 要件定義書を手で直したあと
pipe-in --project ~/src/myapp --from red         # 設計書を手で直したあと
pipe-in --project ~/src/myapp --from implement   # 先に書いたテストを手で直したあと
pipe-in --project ~/src/myapp --from test        # 検証だけやり直す
```

### 確認の画面

要件定義・設計・テスト先行のあとに、文書の先頭60行を表示して止まります。テスト先行のあとは「このテストが通れば要件を満たすと言えるか」を見てください。ここが実装にとっての仕様になります。

- `Enter`：承認して次の段へ
- `r`：修正してほしい点を書く（空行で終わり）。同じ会話のまま直させて、もう一度確認します
- `q`：中止

### 確認で止めて、あとから答える（チャットから動かすとき）

対話できない所（Claude Code のチャット、CI など）から動かすときは `--pause` を付けます。確認の段まで流したら、入力を待たずに `state.json` の `pending_review`（段・文書・会話の ID）を残して止まります（終了コード 5）。文書を読んで、`--review` で答えると続きから流れます。

```bash
pipe-in --project ~/src/myapp --input request.md --pause --test-cmd "pytest -q"   # 要件定義のあとで止まる
pipe-in --project ~/src/myapp --review approve --test-cmd "pytest -q"             # 承認 → 設計のあとで止まる
pipe-in --project ~/src/myapp --review revise --feedback "AC-03 を分けて"          # 同じ会話のまま直させ、また止まる
pipe-in --project ~/src/myapp --review quit                                       # 中止
```

- 記録（`state.json` の `runs`・段のログの番号・費用の合計・注意）は、呼び出しをまたいで続きます。
- `--test-cmd`・`--max-retries` は記録に残らないので、`--review` のたびに同じものを渡してください。
- 止まっている間の `final` は空のままです（VSCode のパネルでは「次を待っている」と出ます）。

### 記録だけを書く（`pipe-in record`）

段を流さずに、開発フローと同じ形の記録（`state.json`・段のログ・`99_summary.md`）だけを書きます。SDK は呼ばず、利用料もかかりません。Claude Code の開発用スキル（このリポジトリの `/pipe-in`）が、会話の中で進めた段を VSCode の拡張で見られるように使います。

<details>
<summary>コマンドの一覧</summary>

```bash
pipe-in record start --text "要件メモ"            # 00_input.md と空の記録（途中の記録があれば断る。終わった記録は archive/ へ）
pipe-in record begin requirements                 # 段を始める（拡張に「動いている」と出る）
pipe-in record done requirements --summary "…"    # 段を閉じる
pipe-in record wait requirements                  # 確認待ち
pipe-in record review requirements approved       # revise --feedback "…" / quit
pipe-in record red red --summary "…"              # テスト先行の結果
pipe-in record verdict pass --attempt 1 --summary "…"   # 検証の判定
pipe-in record finish PASSED                      # 記録を閉じる
```

</details>

- 記録には `"driver": "pipe-dev"` が入ります。`pipe-in --review` は、`driver` の入った記録（前の版の記録も）の続きを流しません。

### Claude Code で開発するとき

このリポジトリの開発用スキル `/pipe-audit`（文書・定義・コードの食い違いの監査）と `/pipe-advise`（公式の文書と照らした助言）は、会話を開かずに `claude -p` でも流せます。プロンプトの先頭を `/pipe-audit` か `/pipe-advise` にして、このリポジトリ（または worktree）の中で呼びます。

```bash
claude -p "/pipe-audit <範囲>" --max-budget-usd 5 --permission-mode dontAsk --tools "Agent,Read,Grep,Glob" --allowedTools "Agent(pipe-in-auditor)" Read Grep Glob
claude -p "/pipe-advise <テーマ>" --max-budget-usd 5 --permission-mode dontAsk --tools "Agent,Read,Grep,Glob,WebFetch,WebSearch" --allowedTools "Agent(pipe-in-advisor)" Read Grep Glob WebSearch "WebFetch(domain:code.claude.com)" "WebFetch(domain:docs.claude.com)" "WebFetch(domain:docs.anthropic.com)" "WebFetch(domain:platform.claude.com)" "WebFetch(domain:github.com)" "WebFetch(domain:raw.githubusercontent.com)"
```

- 読むだけに絞るのは `--tools` です。使える組み込みの道具そのものを絞るので、Bash・Write・Edit などは出てきません。`Read Grep Glob` を `--allowedTools` にも書くのは、Linux・macOS では Glob と Grep が初めの道具に入らず、名前を書くと戻るためです。
- `--allowedTools` は「確認なしで通す」許可で、制限ではありません。`--permission-mode dontAsk` が断るのは、確認が要る呼び出しのうち許可に当たらないものです（許可に無い道具を全部断るわけではありません）。読むだけ・行き先の絞りの保証は、`.claude/hooks/pipe_in_guard.py` とサブエージェントの `tools:` が担います。
- 助言は WebSearch と、公式の文書の場所の WebFetch を許します（ガードの `DOC_HOSTS`・`GITHUB_HOSTS` と同じ）。WebSearch の行き先や、github の `anthropics/` の下への絞りはガードが受け持ちます（許可の書き方では絞れません）。
- `--max-budget-usd 5` は目安の上限で、超えることがあります（サブエージェントの費用も数えます）。好みで変えてください。`--model sonnet` なども任意です。回数の上限は `--max-turns`、断られたときに再試行させないのは `--permission-prompts none`（v2.1.259 以降。どちらも任意）。
- `--bare`・`--disable-slash-commands` は付けません。付けるとスキルが開かれず、`/pipe-audit …` がふつうの文としてモデルに渡ります。公式の文書に「`--bare` は将来 `-p` の既定になる」とあり、そうなると開かれなくなるので、下の見分け方で確かめてください。
- 信頼していない作業フォルダ（新しい worktree など）では、`.claude/settings.json` の allow が無視されます。さらに `.mcp.json` のサーバーは確認なしでつながります。入れている MCP の道具（プラグインのものを含む）は `--tools` では消えませんが、`dontAsk` で許可に無ければ断られます。`--allowedTools` は省かないでください。
- 会話を開かない呼び方では、報告を出して止まります。直すのは、人が承認したあと、会話（`/pipe-audit` を対話で開く、またはメインに頼む）でします。
- 開かれたか確かめるときだけ、末尾に `--output-format stream-json --verbose` を足し、最初の `system/init` の `slash_commands`（と `skills`）に `pipe-audit`（`/pipe-advise` のときは `pipe-advise`）があるかを見ます。あれば開かれています。サブエージェントが動いたかは `parent_tool_use_id` で追えます。無ければ、作業フォルダがこのリポジトリか、`--bare`・`--disable-slash-commands` を付けていないか、`claude --version` を確かめます。

## VSCode の拡張

`vscode/` にある拡張で、実行の進み具合をパネルに図として見たり、パイプを作業台で組み立てたりできます。拡張は記録を読むだけで、記録には何も書きません。くわしい使い方は [vscode/README.md](vscode/README.md) にあります。

```bash
# 拡張を作って、普段の VSCode に入れる
cd vscode
npm install
npm run package                                        # pipe-in-vscode.vsix ができる
code --install-extension pipe-in-vscode.vsix --force
```

### 実行を見る

コマンドパレットの「pipe-in: 実行を見る」か、ステータスバーの `pipe-in` のボタンでパネルが開きます（冒頭の画像）。

- 左に段の図（要件メモ → 要件定義 → 確認 → … → 完了）。動いている段・確認待ち・差し戻しの回数が出ます。
- 右に、いま見ている段の出力・成果物の一覧（押すと開く）・使用量（段ごとのトークン・モデル別・利用枠）。
- `pipe-in --pipe` で流したパイプの記録も、開発フローと切り替えて見られます。

### パイプ作業台

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/pipe-editor-dark.png">
  <img src="docs/assets/pipe-editor-light.png" alt="パイプ作業台。ブロックをケーブルでつないで段の並びを組み、右で選んだ段の設定を決める" width="900">
</picture>

<sub>パイプ作業台。見本のパイプを開き、段「ソースの調査」を選んだところ。</sub>

VSCode 拡張の「pipe-in: パイプ作業台を開く」で、パイプをフロー図として組み立てられます（[vscode/README.md](vscode/README.md)）。
形で見分けるブロックを置き、プラグをコンセントに差すようにつなぎ、各ブロックで Claude に頼むことと[パイプの設定](#定義の書き方pipetoml)を決めて、`.pipe-in/pipes/pipe-in-<名前>/`（無ければ `pipes/`。前の版のフォルダのパイプは元のフォルダ）に保存します。

## パイプ（目的に合わせた段の並び）

開発の5段のほかに、段の並びを自分で決めた **パイプ** を作って流せます（ソースから図を作る、仕様とソースを突き合わせて QA の観点を出す、など）。
パイプは1つのフォルダ（対象プロジェクトの `.pipe-in/pipes/pipe-in-<名前>/`）で、**ジェネレーター**（`pipe-in-gen`）がひな形から作ります。

```
~/src/myapp/                対象プロジェクト
└─ .pipe-in/pipes/         作ったパイプ（1パイプ＝1フォルダ）
   └─ pipe-in-diagrams/
      ├─ pipe.toml         段の並び・書き込める範囲・確認の有無
      ├─ prompts/          段ごとの指示文
      └─ README.md         何をするパイプか・流し方

pipe-in のリポジトリ
├─ generator/              ジェネレーター（環境の検出・ひな形・パイプの生成と検査）
│  └─ templates/           ひな形（dev / diagrams / spec-qa）
└─ plugin/                 Claude Code のプラグイン（/pipe-in:pipe-build と pipe-builder）
```

```bash
pipe-in-gen list --project ~/src/myapp                          # ひな形と、作ったパイプの一覧
pipe-in-gen new diagrams --from diagrams --project ~/src/myapp  # ひな形から .pipe-in/pipes/pipe-in-diagrams/ を作る
pipe-in-gen design apidoc --purpose "ソースから API の文書を作り、突き合わせたい" --project ~/src/myapp
                                                                # 目的から段を組んで作る（Claude が設計する）
pipe-in-gen check diagrams --project ~/src/myapp                # 定義の誤りを調べる
pipe-in --pipe diagrams --project ~/src/myapp --text "注文の流れを中心に"   # 作ったパイプを流す
```

対象のフォルダで、ひな形 diagrams からパイプを作り、定義を調べたときの出力（Python のプロジェクト：pytest・`src/`・`docs/`）：

```text
$ pipe-in-gen new diagrams --from diagrams
✓ <対象>/.pipe-in/pipes/pipe-in-diagrams を作りました（ひな形: diagrams）
  見つけた環境: 言語 python・テスト pytest -q・ソース src・文書 docs
✓ パイプ「diagrams」: 問題ありません

中身は自由に直せます（段の並び・権限・確認は pipe.toml、指示は prompts/）。直したら pipe-in-gen check で確かめてください。
流す: pipe-in --pipe diagrams --project <対象のフォルダ> [--text "依頼メモ"]
```

```text
$ pipe-in-gen check diagrams
✓ パイプ「diagrams」: 問題ありません
```

Claude Code では、プラグインのスキル `/pipe-in:pipe-build <目的、または直したいパイプと直したい点>` で、会話で作る・直すことができます（下の「[Claude Code のプラグイン](#claude-code-のプラグイン)」）。

- `pipe-in-gen new` は対象のファイルを見て、テストのコマンドやソース・文書の場所を埋めます。対象の絶対パスはパイプに書きません。
- `pipe-in-gen design` は、Claude が対象を読むだけで調べて段を組み、ジェネレーターが検査に通るまで（3回まで）直させてから書きます。通らなければ何も書きません。設計の記録は対象の `<work_dir>/design-<名前>/logs/` に残ります。利用料がかかります。
- 同じ名前のパイプがあれば作りません（`--force` で作り直し）。ほかの置き場所（前の版の置き場所を含む）に同じ名前があるときは、`--force` を付けても作りません。
- パイプは対象プロジェクトの `.pipe-in/pipes/` に作ります。`--pipes-dir`（そこだけを使う）か `PIPE_IN_PIPES_DIR` で変えられます。
- 探すときは、対象の `.pipe-in/pipes/` → 前の版の置き場所（[移行の節](#migrate)）→ 今までの場所（`PIPE_IN_PIPES_DIR`、なければ pipe-in のリポジトリの `pipes/`）の順です。前の版で `pipes/` に作ったパイプも、そのまま流せます。

<details>
<summary><code>pipe-in-gen new</code> が見るもの</summary>

Python（pytest。uv・poetry も）・Node（npm・pnpm・yarn・bun）・Go・Rust・Java（Maven・Gradle）・Ruby（RSpec・Rake）・PHP（composer・PHPUnit）・.NET・Deno・Makefile の test、`src/`・`docs/` など。

</details>

> [!WARNING]
> 指示文には対象プロジェクトの事情が入りやすいので、対象が公開リポジトリなら、`.pipe-in/` などの生成物はコミットする前に中身を確かめてください（入れたくなければ `.gitignore` に足します）。

共有したいものは、中身を確かめてから `generator/templates/` にひな形として足してください。

### Claude Code のプラグイン

このリポジトリは Claude Code のプラグインのマーケットプレイスにもなっています（`.claude-plugin/marketplace.json` → `plugin/`）。
入れると、どのプロジェクトでも会話でパイプを作る・直すことができます。`pipe-in-gen` が使えること（`pip install -e .`）が前提です。

```
/plugin marketplace add <pipe-in のリポジトリのフォルダか GitHub の nigoh/pipe-in>
/plugin install pipe-in@pipe-in
```

| 入るもの | すること |
| --- | --- |
| スキル `/pipe-in:pipe-build` | 目的か直したい点を聞き、段の表（直すときは「前 → 後」の表）を見せて確認を取り、pipe-builder に任せ、`pipe-in-gen check` の結果と流し方を伝える。流すのは言われてから |
| エージェント `pipe-builder` | 確認が取れた表どおりに `pipe.toml`・`prompts/`・`README.md` を書き、`pipe-in-gen check` が通るまで直す。表に無い権限の拡大はせず差し戻す |
| フック（`pipe-in-gen guard-hook`） | pipe-builder が書けるのを、パイプのフォルダ（`…/pipes/pipe-in-<名前>/`。前の版のフォルダ名も）の `pipe.toml`・`README.md`・`prompts/*.md` だけに、Bash を `pipe-in-gen list / new / check` だけに絞る。PowerShell・MCP・Web・ほかのエージェントの呼び出しも止める。ほかのエージェントには何もしない |

フックは `pipe-in-gen` で動くので、`pipe-in-gen` が無い環境では効きません（スキルは、はじめに `pipe-in-gen` を確かめて、無ければ止まります）。

### ひな形

| 名前 | 段 | 作るもの |
|---|---|---|
| `dev` | 要件定義 → 設計 → テスト先行 → 実装 → 検証 | 上の開発フローそのもの。テストのコマンドを環境から埋める |
| `diagrams` | ソースの調査 → 図を描く → 図とソースの突き合わせ | フロー図・シーケンス図・状態遷移図・クラス図（Mermaid）|
| `spec-qa` | 仕様とソースの対応 → 食い違いと検討事項 → QA の観点とテストケース | 対応表・食い違いの一覧・テストケース案。どの段もコードは書かない |

### 見本のパイプ

`examples/video/` に、SNS 向けの短い紹介動画を人の確認を挟んで作るパイプの見本（`聞く → 台本 → 見本 → 書き出し → 確かめる`）があります。ひな形ではなく、`pipe-in --pipe examples/video/pipes/pipe-in-video` のようにフォルダのパスで指したときだけ読まれます。
`ffmpeg` と Playwright が要ります。流し方・案のデータの形・ブラウザから答える受付（`examples/video/review_server.py`）は `examples/video/pipes/pipe-in-video/README.md`、台本の見本は `examples/video/pipe-in-intro-script.md` にあります。

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
# writes = ["src/api/**"]  # docs / tests / code の範囲を、さらに場所で絞る（* は / もまたぐ）
# web = true               # WebFetch と WebSearch を使わせる。web = ["docs.python.org"] ならそのドメインへの WebFetch だけ
# mcp = ["mcp__jira__get_issue", "mcp__figma__*"]   # 使わせる MCP の道具（サーバーの名前は必ず書く）
# model = "sonnet" / max_turns = 100 / max_budget_usd = 1.0
```

| access | 書き込める範囲 |
|---|---|
| `read` | 自分の成果物だけ |
| `docs` | 自分の成果物と `docs_dir` の下（`docs_dir` はプロジェクトの中） |
| `tests` | 自分の成果物とテストファイル |
| `code` | 自分の成果物と製品コード（テストファイルは除く） |

- 段は定義の順に流れ、各段には依頼メモと、前の段のうち成果物があるものの場所が渡されます。
- 記録は対象の `<work_dir>/<パイプ名>/` に置かれます（例: `docs/pipeline/diagrams/`）。開発フローの記録は上書きしません。VSCode のパネルでも、開発フローと切り替えて見られます。
- 確認・`--pause`・`--review`・`--from <段の名前>`・`--yes` は開発フローと同じように使えます（`--review` のときも `--pipe` を付けてください）。
- Web と MCP は、段に `web`・`mcp` を書いたときだけ使えます（既定は止める）。PowerShell は、どの段でも使えません。サブエージェントに任せる道具（`Task`・`Agent`）は、`agents` を書いた段だけで使えます（下の「Agent SDK の設定」）。`protected_paths` とパイプのフォルダは、どの段も書けません。
- MCP のサーバーは、Claude Code の設定から読みます。対象の `pipeline.toml` の `setting_sources` に `"project"`（`.mcp.json`）か `"user"` を入れてください。
- `kind = "dev"` の定義に書けるのは `test_command` だけです（`--test-cmd` → パイプの定義 → `pipeline.toml` の順に優先）。段ごとのモデルなどは `pipeline.toml` で決めます。

### 検証と差し戻し

段の成果物を確かめ、不合格なら直す点を添えて前の段へ戻せます。

```toml
[[stages]]
name = "verify"
# ...
[stages.check]
verdict = true                 # 段に pass / fail と直す点（problems）を返させる
command = "python -m pytest -q tests/test_docs.py"   # pipe-in が流す確認用のコマンド（終了コード 0 で合格）
on_fail = "draw"               # 不合格のときに戻す段（自分か前の段。省くと自分）
max_retries = 2                # 戻す回数の上限。超えたら終了コード 1
```

- `verdict` と `command` は、どちらか一方でも両方でもかまいません。両方なら、どちらも合格で合格です。
- 検証は、人の確認より先に行います（不合格のものは人に見せない）。
- 戻した段には「前回の検証で見つかった問題」が渡され、新しい会話でやり直します。
- `command` は利用者が書くコマンドで、pipe-in が対象のフォルダで実行します。`curl` や `git push` などの危ない操作は、`pipe-in-gen check` で拒みます。

### 分岐・飛び先・並列

- `[stages.routes]`：段に choice を返させ、行き先を選びます（`"end"` で終わり）。
- `next`：次の段を決めます（`"end"` で終わり）。省くと定義の次の段です。
- `group`：同じ group の続いた段は同時に流します。
- 分岐先の段が、ほかの分岐先に流れ込まないように、最後に `next` を書いてください。
- `group` の段には `review`・`routes`・`next` を書けません。`check` の `on_fail` は自分だけを指せます（自分だけをやり直す）。
- 段を流す回数は `[pipe]` の `max_steps`（既定 50）までです。超えたら終了コード 3 で止めます（飛び先や差し戻しの無限ループを防ぐ）。

<details>
<summary>書き方の例</summary>

```toml
[[stages]]
name = "classify"
# ...
[stages.routes]                # 段に choice を返させ、行き先を選ぶ（"end" で終わり）
api = "api-doc"
ui = "ui-doc"
none = "end"

[[stages]]
name = "api-doc"
next = "report"                # 次の段を決める（"end" で終わり）。省くと定義の次の段
# ...

[[stages]]
name = "flow"
group = "draw"                 # 同じ group の続いた段は同時に流す
# ...
[[stages]]
name = "sequence"
group = "draw"
```

</details>

### Agent SDK の設定

段ごとに、Claude Agent SDK の設定を書けます。書いたものだけを SDK に渡します。

- 許可のモード（`permission_mode`）・考える量（`max_thinking_tokens`）・予備のモデル（`fallback_model`）・この段の決まり（`system_append`）・追加で読めるフォルダ（`add_dirs`）・使う MCP の道具（`mcp`）・サブエージェント（`agents`）・この段だけの MCP サーバー（`mcp_servers`）。
- `agents` のある段だけ、サブエージェントに任せる道具（`Task`・`Agent`）を通します。サブエージェントの道具の呼び出しにも guard が掛かるので、書き込める範囲や止める操作は段と同じです（本物で確かめています）。
- `mcp_servers` を書いても、使う道具を `mcp` に書かなければ使えません。

<details>
<summary>書き方の例</summary>

```toml
[[stages]]
name = "survey"
# ...
permission_mode = "plan"          # default / acceptEdits / plan（確認を省くモードは安全のため使えません）
max_thinking_tokens = 16000       # 考える量
fallback_model = "sonnet"         # 予備のモデル
system_append = "表を使って書く"   # この段の決まり（system prompt に足す）
add_dirs = ["../shared-docs"]     # 追加で読めるフォルダ（プロジェクトからの相対パス。書き込みはできない）
mcp = ["mcp__jira__get_issue"]    # 使う MCP の道具

[stages.agents.module-reader]     # サブエージェント
description = "1つのモジュールを読んで要点を返す"
prompt = "渡されたモジュールだけを読む"
tools = ["Read", "Grep"]          # 段で使える道具の範囲だけ（Task・Agent・PowerShell は不可）
model = "haiku"

[stages.mcp_servers.jira]         # この段だけで使う MCP サーバー
type = "http"                     # stdio（command・args）/ http・sse（url）
url = "https://mcp.example.com/jira"
```

</details>

## 安全のしくみ

### 段ごとの役割と書き込める範囲

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

テストファイルの判定は、`tests/`・`test/`・`__tests__/`・`spec/`・`specs/` の中にあるか、`test_*.py`・`*_test.py`・`*_test.go`・`*.test.*`・`*.spec.*`・`*_spec.rb`・`conftest.py` の名前かで行います。足りなければ `extra_test_globs` に追加してください。

### どの段でも止める操作

`git push`、`git reset --hard`、`git clean -f`、ブランチの切り替え、再帰的な削除（`rm -r`）、`sudo`、`curl`・`wget`・`ssh` などの外部通信、パッケージの公開、プロジェクトの外への書き込み、Web 検索と Web 取得（パイプでは、`web` を書いた段を除く）。

また、段ごとに許したツール（`pipe_in/dev/specs.py`・`pipe_in/pipe/specs.py` の `allowed_tools`）と、読むだけの道具（`Read`・`Glob`・`Grep`・`Skill`・`ToolSearch`・`TodoWrite`）と構造化出力を返す道具（`StructuredOutput`）以外は、すべて止めます。PowerShell・MCP のツール・サブエージェント（`Task`）などから、書き込み範囲や危ない操作の判定をすり抜けられないようにするためです。PowerShell は最初から使えないツールにも入れています。

止めた操作はその場で表示され、`99_summary.md` にも残ります。仕組みは `pipe_in/engine/guard.py` の PreToolUse フックで、すべてのツールに掛かり、自動承認したツールにも効きます。

## 記録と使用量

### 作られるファイル

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

### まとめに出る使用量

各段の最後に Claude Code が返す結果（`ResultMessage`）と、途中の利用枠のイベント（`RateLimitEvent`）、開始時の環境（`SystemMessage` の `init`）から集めます（`pipe_in/usage/metrics.py`、表は `pipe_in/usage/report.py`）。`99_summary.md` に、次の節が出ます。

<details>
<summary>節ごとの中身</summary>

| 節 | 中身 |
|---|---|
| トークンの内訳 | 段ごとの入力・キャッシュ書き込み・キャッシュ読み込み・出力・うち thinking・キャッシュ再利用率・API 待ち時間と合計 |
| モデル別 | モデルごとのトークンと費用 |
| 環境 | 使われたモデル、Claude Code の版、認証の出どころ、許可のモード、費用の根拠、途中で止まった段 |
| 利用枠 | 5時間枠・7日枠の使用率（開始 → 終了。途中で枠が戻ったときは最大値も）、枠が戻る時刻、超過利用の可否 |

</details>

> [!NOTE]
> 費用は定価での概算（`costBasis: list`）です。サブスクリプションでログインしている場合は、利用枠の使用率のほうが実際の負担に近い値です。

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
| 0 | 検証まで合格（パイプは最後の段まで終わった） |
| 1 | 差し戻しの上限までテストが通らなかった（パイプは検証に通らなかった） |
| 2 | 確認の段階で中止した |
| 3 | 段の実行が失敗した（文書が作られない、上限に達した、テストのない AC が残った、パイプの分岐先が返らない・max_steps を超えたなど） |
| 4 | テストを実行できなかった（環境の問題など。差し戻しはしない） |
| 5 | 人の確認を待っている（`--pause` のとき。`--review` で続ける） |
| 130 | Ctrl+C で中断（`--from` で再開できます） |

<a id="migrate"></a>

## devpipe から移る

この道具の名前は devpipe から pipe-in に変わりました（0.3.0）。前の版を使っていたときは、次の手順で移ってください。パスは `<リポジトリ>`（このリポジトリのフォルダ）・`<対象>`（パイプを流すプロジェクト）に読み替えてください。

1. **入れ直す**：古いものを先に外してから入れます（順が逆だと、外すときに新しく入った別名のコマンドも消えます）。

   ```bash
   cd <リポジトリ>
   pip uninstall devpipe
   pip install -e '.[dev]'
   ```

2. **古いコマンド**：`devpipe`・`devpipe-gen` は 0.3 の間だけ別名として動き、標準エラーに「名前が変わりました」の案内を1行出します。**0.4 で消します。** `python -m devpipe` は無くなりました（`python -m pipe_in` を使います）。
3. **プラグイン**：古いマーケットプレイスを外して、登録し直します。スキルは `/pipe-in:pipe-build` になります。登録し直すまでの間も、古いプラグインのフックは別名の `devpipe-gen guard-hook` で動き、pipe-builder を止めます。

   ```
   /plugin marketplace remove devpipe
   /plugin marketplace add nigoh/pipe-in
   /plugin install pipe-in@pipe-in
   ```

4. **VSCode の拡張**：新しい `pipe-in-vscode.vsix` を入れ（[vscode/README.md](vscode/README.md)）、古い拡張を `code --uninstall-extension nok.devpipe-vscode` で外します。
   - 古い設定 `devpipe.workDir`・`devpipe.pipesDir` は、新しい設定 `pipe-in.workDir`・`pipe-in.pipesDir` を書いていない間は読みます。
   - 古いコマンド ID（`devpipe.showRun`・`devpipe.editPipe`）に付けたキー割り当ても効きます（パレットには出しません）。
   - 作業台の「保存した版」は引き継がれません（拡張の保存場所が変わるため）。
5. **パイプの置き場所**：前の版の `<対象>/.devpipe/pipes/devpipe-<名前>/` は、そのまま読めて流せます。作業台で直して保存しても、元のフォルダに書きます。新しい置き場所に移したいときは、次のようにします。

   ```bash
   cd <対象>
   mkdir -p .pipe-in/pipes
   git mv .devpipe/pipes/devpipe-<名前> .pipe-in/pipes/pipe-in-<名前>
   ```

   同じ名前のパイプが両方にあると新しいほうを使い、`pipe-in-gen new` はその名前では作りません。`pipe-in-gen list` は、古いものに「（古い名前）」と添えます。`<対象>` の `.gitignore` に `.devpipe/` を書いていたときは、`.pipe-in/` も足してください。
6. **環境変数**：パイプの置き場所は `PIPE_IN_PIPES_DIR` で変えます。`DEVPIPE_PIPES_DIR` も読みます（両方あれば新しいほう。プラグインのフックも同じ）。
7. **記録**：前の版が書いた記録（`docs/pipeline/` の `state.json` など）は、そのまま拡張で見られます。
8. **GitHub の URL**：リポジトリの名前が変わったあとは、手元の複製の向き先を直します（古い URL からも転送されます）。

   ```bash
   git remote set-url origin https://github.com/nigoh/pipe-in.git
   ```

## 中身を直したいとき

| やりたいこと | 場所 |
|---|---|
| 開発フローの各段への指示（文書の構成、守ること） | `pipe_in/dev/prompts/*.md` |
| 開発フローの段の順番、確認、差し戻しの流れ | `pipe_in/dev/pipeline.py` |
| 開発フローの段ごとのツールと書き込み範囲 | `pipe_in/dev/specs.py` |
| どのパイプにも共通の流れ（記録・確認・まとめ） | `pipe_in/engine/pipeline.py` |
| 止める操作 | `pipe_in/engine/guard.py` の `DANGEROUS_BASH` |
| SDK の呼び出し | `pipe_in/engine/runner.py` |
| パイプの読み込み・検査・流れ・権限の型 | `pipe_in/pipe/` |
| パイプの生成・環境の検出・ひな形 | `generator/`（`pipe-in-gen`）・`generator/templates/` |

```bash
# テストを流す（SDK を呼ばずに、段の順番・確認・差し戻し・書き込み制限を確かめる）
pip install -e '.[dev]' && pytest
```

直す・機能を足すときの決まり（原則・仕様の書き方・設計・テスト・進め方）は [docs/development/](docs/development/) に、機能ごとに何をなぜ決めたかは [docs/decisions/](docs/decisions/) にあります。README の画像の撮り直し方は [docs/assets/README.md](docs/assets/README.md) にあります。

## 注意

> [!NOTE]
> 費用は SDK が返す概算です。実際の請求とはずれることがあります。

- Claude Code の中（Bash ツール）から起動しても、修正の依頼（同じ会話の続き）は使えます（Claude Code 2.1.119・claude-agent-sdk 0.2.168 で確認）。古い版で会話を引き継げないときは、普段のターミナルから実行してください。
- 対象プロジェクトの CLAUDE.md・`.claude/` の規約やフックを各段に効かせたいときは、`setting_sources = ["project"]` を設定してください。
- Windows で日本語の表示が崩れるときは `PYTHONUTF8=1` を設定してください。
- 動作を確認した環境：Python 3.13、claude-agent-sdk 0.2.159〜0.2.168、Claude Code 2.1.301。

## ライセンス

MIT（[LICENSE](LICENSE)）
