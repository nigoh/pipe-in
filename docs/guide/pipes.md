# パイプ（目的に合わせた段の並び）

[ガイドの目次](README.md) · [README](../../README.md) — 段の並びを自分で決めた「パイプ」の作り方・書き方・流し方の説明です。

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

Claude Code では、プラグインのスキル `/pipe-in:pipe-build <目的、または直したいパイプと直したい点>` で、会話で作る・直すことができます（「[Claude Code のプラグイン](plugin.md)」）。

- `pipe-in-gen new` は対象のファイルを見て、テストのコマンドやソース・文書の場所を埋めます。対象の絶対パスはパイプに書きません。
- `pipe-in-gen design` は、Claude が対象を読むだけで調べて段を組み、ジェネレーターが検査に通るまで（3回まで）直させてから書きます。通らなければ何も書きません。設計の段が SDK の受信バッファの上限（`max_buffer_mb`）を超えたときは、やり直さずに案内を出して止まり、何も書かずに終了コード 1 で終わります（直し方は[設定](config.md)の `max_buffer_mb`）。設計の記録は対象の `<work_dir>/design-<名前>/logs/` に残ります。`judge`（`must`・`criteria`）も組めます。審査で差し戻すなら `command` と組んでください。利用料がかかります。
- 同じ名前のパイプがあれば作りません（`--force` で作り直し）。ほかの置き場所（前の版の置き場所を含む）に同じ名前があるときは、`--force` を付けても作りません。
- パイプは対象プロジェクトの `.pipe-in/pipes/` に作ります。`--pipes-dir`（そこだけを使う）か `PIPE_IN_PIPES_DIR` で変えられます。
- 探すときは、対象の `.pipe-in/pipes/` → 前の版の置き場所（[前の名前から移る](migrate.md)）→ 今までの場所（`PIPE_IN_PIPES_DIR`、なければ pipe-in のリポジトリの `pipes/`）の順です。前の版で `pipes/` に作ったパイプも、そのまま流せます。

<details>
<summary><code>pipe-in-gen new</code> が見るもの</summary>

Python（pytest。uv・poetry も）・Node（npm・pnpm・yarn・bun）・Go・Rust・Java（Maven・Gradle）・Ruby（RSpec・Rake）・PHP（composer・PHPUnit）・.NET・Deno・Makefile の test、`src/`・`docs/` など。

</details>

> [!WARNING]
> 指示文には対象プロジェクトの事情が入りやすいので、対象が公開リポジトリなら、`.pipe-in/` などの生成物はコミットする前に中身を確かめてください（入れたくなければ `.gitignore` に足します）。

共有したいものは、中身を確かめてから `generator/templates/` にひな形として足してください。

### 検査の警告

`pipe-in-gen check`（と `pipe-in-gen new`）は、誤りのほかに、流すと詰まりやすい段の形を `⚠` の行で知らせます。警告は誤りではないので、警告だけなら検査は通ります（終了コード 0。誤りがあれば 1）。警告が無ければ、出力は今までと同じ1行です。実際のパイプを流して分かったことから作った3つです。

- `access = "read"` で `bash = true` の段で、指示文に書き出す・書き込む・保存する・取り出す・描く・試作・下書き・置き場所などの言葉があるとき。`read` の段は、Bash でも自分の成果物のほかは書けません（[安全の仕組み](safety.md)）。試作や図を置く場所が要るなら、`access = "docs"` と `docs_dir`（要るなら `writes`）にしてください。
- `access = "tests"` の段が `bash = true` でなく、あとの段に `check.command` があるとき。テストを書く段が、あとで掛かる検査（lint や inspect など）を自分で流せず、実装の段で初めて落ちて差し戻しが回ります。テストを書く段にも `bash = true` を付け、同じ検査を流させてください。
- 検査（`[stages.check]`）の `on_fail` の戻り先が、`access = "read"` の別の段のとき。読むだけの段に戻しても、指摘を直せません。直す段（`code`・`tests`・`docs`）に戻してください。

警告が1件のときの出力の例です（`pipe-in-gen check mypipe`）。

```text
✓ パイプ「mypipe」: 誤りはありません（注意 1 件）
⚠ 段 3（target）: access = "read" で bash = true の段は、Bash でも成果物のほかは書けません（D0036）。試作・図・下書きなどを置くなら、access = "docs" と docs_dir にしてください
```

## ひな形

| 名前 | 段 | 作るもの |
|---|---|---|
| `dev` | 要件定義 → 設計 → テスト先行 → 実装 → 検証 | [開発フロー](usage.md#開発フローの流れ)そのもの。テストのコマンドを環境から埋める |
| `diagrams` | ソースの調査 → 図を描く → 図とソースの突き合わせ | フロー図・シーケンス図・状態遷移図・クラス図（Mermaid）。検査コマンド（`python`）と審査つき。`python` が無い・`python3` だけの環境では、`pipe.toml` の `command` を `python3 -c …` などに書き換える |
| `spec-qa` | 仕様とソースの対応 → 食い違いと検討事項 → QA の観点とテストケース | 対応表・食い違いの一覧・テストケース案。どの段もコードは書かない |

## 見本のパイプ

`examples/video/` に、SNS 向けの短い紹介動画を人の確認を挟んで作るパイプの見本（`聞く → 台本 → 見本 → 書き出し → 確かめる`）があります。ひな形ではなく、`pipe-in --pipe examples/video/pipes/pipe-in-video` のようにフォルダのパスで指したときだけ読まれます。
`ffmpeg` と Playwright が要ります。流し方・案のデータの形・ブラウザから答える受付（`examples/video/review_server.py`）は `examples/video/pipes/pipe-in-video/README.md`、台本の見本は `examples/video/pipe-in-intro-script.md` にあります。

## 定義の書き方（`pipe.toml`）

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

## 検証と差し戻し

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
- `verdict`・`command`・`judge`（下の「ルーブリックで審査する」）のどれかは書いてください。

### ルーブリックで審査する（`[stages.check.judge]`）

採点の項目（criteria）と、1つでも破ると不合格になる決まり（must）を書くと、審査役（段の Claude）が理由と点を返し、合否は pipe-in が計算します。審査役に平均や合否を言わせないので、同じ点なら同じ結果になります。

```toml
[stages.check]
command = "python -m pytest -q"   # 機械の検査（審査で差し戻すなら必ず組む）
on_fail = "draw"
max_retries = 2

[stages.check.judge]
threshold = 0.7                # 合格のしきい値（0 以上 1 以下。省くと 0.7）

[[stages.check.judge.criteria]]
name = "clarity"
description = "読みやすい"

[[stages.check.judge.must]]
name = "no_secret"
description = "秘密の値を書かない"
```

- 審査役は、項目ごとに理由を先に書いてから、点を 1.0・0.75・0.5・0.25・0.0 のどれかで付けます。確かめられないときは `null` です（平均に数えません）。must は違反かどうか（`violated`）と、違反なら根拠だけを返します。
- 合格は、点の平均（小数 2 桁に四捨五入）がしきい値以上で、must がどれも違反でなく、確かめられないものも無いときです。must が 1 つでも違反なら、点が満点でも不合格です。確かめられなかった must（`null`）も、安全側に倒して不合格です。採点できた項目が 1 つも無いときも不合格です。
- 返りが決まりに合わないとき（項目の欠け・0.3 のような点・理由が空・違反なのに根拠が無い、など）は、段の失敗にせず、検証の不合格として差し戻します。
- 不合格のときは、must の違反の根拠が「前回の検証で見つかった問題」に入って、戻した段に渡ります。平均がしきい値に届かなかったときは、点が満点でない項目の理由も入ります。
- `verdict`・`command` と併せて書けます。3つとも評価し、どれも通ったときだけ合格です。`group` の段にも使えます。
- 審査で差し戻す（`on_fail` を書く）なら、必ず `command`（機械の検査）と組んでください。審査の指摘で書き直すと決まりが崩れることがあり、それを拾えるのは機械の検査です（[docs/research/eval-vs-judge/](../research/eval-vs-judge/README.md)）。
- 書く項目は `threshold`・`criteria`（1つ以上）・`must`（なくてよい）だけです。項目は `name` と `description`。同じ入れ物の中の名前の重なり、範囲の外のしきい値、知らないキーは、`pipe-in-gen check` が拒みます。
- 結果は `state.json` の `check.judge` に残り、`99_summary.md` の検証の行の下に 1 行（平均・しきい値・合否）が出ます。
- **古い版の pipe-in では、`judge` は知らないキーとして黙って無視されます。** `verdict` や `command` を併記していれば審査なしで動き、`judge` だけだと検証が無いのと同じになります。審査を使うパイプは新しい版の pipe-in で流してください。
- VSCode の作業台には審査の編集画面はありません。審査つきのパイプを開いて保存しても `judge` は消えず、そのまま書き戻します（検証のスイッチを切って保存した段では、`judge` も書き出されません）。書き換えるときは `pipe.toml` を直接直してください。

## 分岐・飛び先・並列

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

## Agent SDK の設定

段ごとに、Claude Agent SDK の設定を書けます。書いたものだけを SDK に渡します。

- 許可のモード（`permission_mode`）・考える量（`max_thinking_tokens`）・予備のモデル（`fallback_model`）・この段の決まり（`system_append`）・追加で読めるフォルダ（`add_dirs`）・使う MCP の道具（`mcp`）・サブエージェント（`agents`）・この段だけの MCP サーバー（`mcp_servers`）。
- `agents` のある段だけ、サブエージェントに任せる道具（`Task`・`Agent`）を通します。サブエージェントの道具の呼び出しにも guard が掛かるので、書き込める範囲や止める操作は段と同じです（本物で確かめています）。
- サブエージェント（`Agent`・`Task`）は `run_in_background: false` を付けて（待つ形で）呼びます。付けないとメインからは裏で動くので、guard が止めます。段は、応答が終わると裏の作業の結果を待てないためです。`isolation` を付けた呼び出しも止めます。`Bash` は `run_in_background` を書かなければ待つ形で、`false` 以外の値を付けると、どの段でも止めます。段の指示文に「`run_in_background: false` で呼び、全部返るまで待つ」と書いておくと、止められて呼び直す手間が減ります。
- 1回の実行で呼べるサブエージェントは、`max_agent_calls` 回までです（既定 20。1 以上の整数で、`agents` のある段だけに書けます）。超えた呼び出しは止めて、それまでに返った結果で成果物を書かせます。段は失敗にしません。差し戻しのやり直し・指摘の反映・`group` の段は、それぞれ 0 から数えます。止めた呼び出しは数えません。
- サブエージェントの中からのサブエージェントの呼び出しは止めます（くわしくは[安全の仕組み](safety.md#どの段でも止める操作)）。
- VSCode の作業台でパイプを開いて保存すると、`max_agent_calls` は消えます（上限は既定の 20 に戻ります）。変えた上限を残すときは、`pipe.toml` を直接直してください。
- 古い版の pipe-in は `max_agent_calls` を知らないキーとして黙って無視します（古い版には上限がありません）。
- `mcp_servers` を書いても、使う道具を `mcp` に書かなければ使えません。
- 受信バッファの上限（`max_buffer_size`）だけは、書かなくてもいつも SDK に渡します。値は段ごとではなく、`pipeline.toml` の `[pipeline]` の `max_buffer_mb`（既定 32MB）で決めます（[設定](config.md)）。

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
max_agent_calls = 8               # 1回の実行で呼べるサブエージェントの数（既定 20）

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
