---
name: pipe-help
description: pipe-in の使いかたの一覧を出す。Claude Code のコマンド（/pipe-in・/pipe-docs・/pipe-audit・/pipe-advise・/pipe-judge・/pipe-plan・プラグインの /pipe-in:pipe-build・/pipe-in:pipe-eval・/pipe-in:pipe-judge・/pipe-in:pipe-live）、pipe-in と pipe-in-gen の CLI、VSCode 拡張のコマンドを、何をしたいときに何を使うかで案内する。
argument-hint: [知りたいこと（例: パイプ・作業台・再開・--auto）]
disable-model-invocation: true
---

# /pipe-help — pipe-in の使いかた

知りたいこと: $ARGUMENTS

## 答え方

- 引数が空なら、下の「一覧」をそのまま見せる（表は崩さない）。最後に「`/pipe-help パイプ` のように付けると、そこだけ詳しく答えます」と1行添える。
- 引数があれば、一覧の中から当てはまる所だけを選び、README.md・`docs/guide/` の文書・vscode/README.md・pipes/README.md の該当する節を読んで、手順を具体的に答える。コマンドは実際の書き方で示す。
- このリポジトリの今の版で確かめられることだけを答える（コマンドやオプションは `pipe-in --help`・`pipe-in-gen --help` か README・`docs/guide/` で確かめる）。書かれていないことは「書かれていない」と言う。
- 何も実行しない（流す・作る・保存するのは、人に言われてから）。

## 一覧

### Claude Code のコマンド（このリポジトリで開発するとき）

| コマンド | すること |
| --- | --- |
| `/pipe-in <要件メモ>` | pipe-in に機能を足す。要件定義 → 設計 → テスト先行 → 実装 → 検証 を段ごとにサブエージェントへ任せて進め、段ごとに止まって確認を取る。進み具合は VSCode の「pipe-in: 実行を見る」で見られる |
| `/pipe-in --auto <要件メモ>` | 同じことを、段の区切りで止まらずに最後まで進める（要件定義の決めきれない点・文書係の案・監査と助言の報告・検証の不合格が3回続いたときは止まる。迷うときも止まって聞く。コミットは言われるまでしない） |
| `/pipe-in --artifact <要件メモ>` | 同じ流れを、会話の横の Claude のアーティファクトでも見られるようにする（進み具合のページ。確認待ちは、ページの行のボタン（承認・差し戻し・中止）でも会話でも答えられる。会話は `pipe-in live answer` で読んでから `record review` を書く。ボタンは新しく公開したページ・編集者だけ。Artifact と ArtifactData のツールがある会話でだけ使え、`--auto` と一緒に使える） |
| `/pipe-docs [要点か範囲]` | 変えたファイル（空ならこのブランチの全部）に合わせて、文書（README.md・`docs/guide/`・`docs/development/`・vscode/README.md）を文書係にそろえさせる。CLAUDE.md・/pipe-help・決定の記録は案を見せ、承認したものだけをメインが直す。コードを変えて文書がそのままだと、止まるときに一度だけ知らせが出る |
| `/pipe-audit [範囲]` | 文書・定義・コードのあいだの食い違い（名前・パス・コマンド・決まり・数）を、根拠（ファイル:行）付きで並べて止まる。承認した項目だけをメインが直す |
| `/pipe-advise [テーマ]` | Claude Code と Agent SDK の公式の文書と照らして、このリポジトリの使いかたを出典の URL 付きで助言して止まる。承認した項目だけをメインが直す |
| `/pipe-judge [ファイル]` | 調べもの型の報告（空ならこの会話でいちばん新しい助言の報告）を、事実の正確さ・引用の正確さ・網羅性・情報源の質・ツール効率の5項目で 0.0〜1.0 に採点し、総合と合否を JSON で見せて止まる。直さない |
| `/pipe-plan [sync \| add <やりたいこと> \| 聞きたいこと]` | 計画ボード（Claude のアーティファクト）を開く。ロードマップの段階ごとに、完了・手で確かめる・やる予定・進行中・アイデアを並べる。`sync` で GitHub のイシューと決定の記録に合わせ（案を見せて承認を得てから書く）、`add` でやりたいことを足す。ボードのカードの「実行」から、新しいセッションで `/pipe-in` を始められる（書ける人だけ・プランの利用枠を使う）。Artifact と ArtifactData のツールがある会話でだけ使える |
| `/pipe-in:pipe-build <目的か直したい点>` | パイプ（段の並び）を会話で作る・直す。プラグイン（`/plugin marketplace add ./` → `/plugin install pipe-in@pipe-in`）を入れて使う。どのプロジェクトでも使える |
| `/pipe-in:pipe-eval <パイプ名>` | パイプの成果物を、検査のコマンド（`pipe.toml` の `[stages.check]` の `command`、または渡したコマンド）で確かめる。流す前に一覧を見せて返事を待つ。成果物は直さない。プラグインを入れて使う |
| `/pipe-in:pipe-judge <成果物> [--rubric …] [--runs 1〜5]` | 成果物を依頼とルーブリックに照らして 0.0〜1.0 で審査する。must の違反は即不合格。総合点・合否・ばらつきは `pipe-in-gen judge-score` が計算し、JSON で返す。直さない。開発用の `/pipe-judge`（助言の報告の採点）とは別物 |
| `/pipe-in:pipe-live [--work-dir 記録のフォルダ]` | ターミナルで流している pipe-in の進み具合を、Claude のアーティファクトでも見る。ページを1回だけ公開し、Monitor で `pipe-in live watch` を動かして、行のたびに写しを書く。見るだけで、止める・進める・承認はできない。Artifact・ArtifactData・Monitor がある、claude.ai にログインした Claude Code で使う |
| `/pipe-help [知りたいこと]` | この一覧。知りたいことを付けると、そこだけ詳しく |

### 会話を開かずに流す（`claude -p`）

`/pipe-audit`・`/pipe-advise` は、会話を開かずに `claude -p` でも流せます。プロンプトの先頭を `/pipe-audit` か `/pipe-advise` にして、このリポジトリ（または worktree）の中で呼びます。

```bash
claude -p "/pipe-audit <範囲>" --max-budget-usd 5 --permission-mode dontAsk --tools "Agent,Read,Grep,Glob" --disallowedTools "mcp__*" --allowedTools "Agent(pipe-in-auditor)" Read Grep Glob
claude -p "/pipe-advise <テーマ>" --max-budget-usd 5 --permission-mode dontAsk --tools "Agent,Read,Grep,Glob,WebFetch,WebSearch" --disallowedTools "mcp__*" --allowedTools "Agent(pipe-in-advisor)" Read Grep Glob WebSearch "WebFetch(domain:code.claude.com)" "WebFetch(domain:docs.claude.com)" "WebFetch(domain:docs.anthropic.com)" "WebFetch(domain:platform.claude.com)" "WebFetch(domain:github.com)" "WebFetch(domain:raw.githubusercontent.com)"
```

- 読むだけに絞るのは `--tools` です。使える組み込みの道具そのものを絞るので、Bash・Write・Edit などは出てきません。`Read Grep Glob` を `--allowedTools` にも書くのは、Linux・macOS では Glob と Grep が初めの道具に入らず、名前を書くと戻るためです。
- `--allowedTools` は「確認なしで通す」許可で、制限ではありません。`--permission-mode dontAsk` が断るのは、確認が要る呼び出しのうち許可に当たらないものです（許可に無い道具を全部断るわけではありません）。読むだけ・行き先の絞りの保証は、`.claude/hooks/pipe_in_guard.py` とサブエージェントの `tools:` が担います。
- 助言は WebSearch と、公式の文書の場所の WebFetch を許します（ガードの `DOC_HOSTS`・`GITHUB_HOSTS` と同じ）。WebSearch の行き先や、github の `anthropics/` の下への絞りはガードが受け持ちます（許可の書き方では絞れません）。
- `--max-budget-usd 5` は目安の上限で、超えることがあります（サブエージェントの費用も数えます）。好みで変えてください。`--model sonnet` なども任意です。メインの回数の上限は `--max-turns`、断られたときに再試行させないのは `--permission-prompts none`（v2.1.259 以降。どちらも任意）。
- 監査・助言のサブエージェント（`pipe-in-auditor`・`pipe-in-advisor`）には、定義の前置きの `maxTurns` で回数の上限があります（監査 100・助言 80。審査の `pipe-in-judge` は 50）。`--max-turns` はメインの回数の上限で、別のものです。上限に当たると、サブエージェントの報告は途中までの印（partial）を付けてメインに返ります（Claude Code v2.1.246 以降）。会話の中ではメインに続きを頼めますが、会話を開かない呼び方では `--tools` に `SendMessage` が無いので続けられません。報告が足りないときは、範囲（`/pipe-advise` ではテーマ）を狭めて流し直してください。
- `--bare`・`--disable-slash-commands` は付けません。付けるとスキルが開かれず、`/pipe-audit …` がふつうの文としてモデルに渡ります。公式の文書に「`--bare` は将来 `-p` の既定になる」とあり、そうなると開かれなくなるので、下の見分け方で確かめてください。
- 信頼していない作業フォルダ（対話の会話で一度も信頼したことのないリポジトリなど。信頼はリポジトリの根で決まり、worktree では main の作業フォルダの場所で見ます。`claude -p` は信頼の確認を出しません）では、`.claude/settings.json` の allow が無視されます。さらに `.mcp.json` のサーバーは確認なしでつながります。入れている MCP の道具（プラグインのものを含む）は `--tools` では消えないので、`--disallowedTools "mcp__*"` で断り、モデルに見せません。消えるのは道具だけで、サーバーそのものは起動します（このリポジトリには `.mcp.json` はありません）。`--disallowedTools` は `--allowedTools` の前に置きます（どちらも後ろに値を空白で並べて受け取る形なので、別の値の並びの途中に挟まないためです）。`--allowedTools` は省かないでください。
- 会話を開かない呼び方では、報告を出して止まります。直すのは、人が承認したあと、会話（`/pipe-audit` を対話で開く、またはメインに頼む）でします。
- 開かれたか確かめるときだけ、末尾に `--output-format stream-json --verbose` を足し、最初の `system/init` の `slash_commands`（と `skills`）に `pipe-audit`（`/pipe-advise` のときは `pipe-advise`）があるかを見ます。あれば開かれています。サブエージェントが動いたかは `parent_tool_use_id` で追えます。無ければ、作業フォルダがこのリポジトリか、`--bare`・`--disable-slash-commands` を付けていないか、`claude --version` を確かめます。

### pipe-in（流す）

| やりたいこと | コマンド |
| --- | --- |
| 開発フローを流す（要件定義 → 設計 → テスト先行 → 実装 → 検証） | `pipe-in --project <対象> --input request.md` |
| 確認なしで最後まで流す | `pipe-in --project <対象> --input request.md --yes` |
| 実行にセッション名を付ける（VSCode の一覧に出る） | `pipe-in --project <対象> --input request.md --name "…"`（省くと要件メモの最初の行。始めるときだけ付けられる） |
| チャットから流す（確認で止めて、あとで答える） | `pipe-in ... --pause` → `pipe-in --project <対象> --review approve` ／ `--review revise --feedback "…"` ／ `--review quit` |
| 途中から再開する | `pipe-in --project <対象> --from design`（パイプでは段の名前） |
| 記録だけを書く（段は流さない。/pipe-in が使う） | `pipe-in record start --text "…" --name "…"`（`--session-id` も付けられる）→ `begin <段> --agent <受け持ち>` → `done <段>` → `wait <段>` → `review <段> approved` … → `finish PASSED`（`pipe-in record --help`） |
| 進み具合の写し・ページを出す（Claude のアーティファクト用。記録は読むだけ。/pipe-in --artifact が使う） | `pipe-in live snapshot [--project DIR] [--config FILE] [--work-dir DIR] [--out FILE]` ／ `pipe-in live page [--out FILE]` |
| ターミナルの実行を見張る（写しが変わったときだけ `--out` に書いて JSON の1行を出す。final で 0、上限で 124。/pipe-in:pipe-live が使う） | `pipe-in live watch --out FILE [--project DIR] [--config FILE] [--work-dir DIR] [--interval 秒] [--timeout 秒]` |
| パイプを流す | `pipe-in --pipe <名前> --project <対象> --text "依頼メモ"`（`--pause`・`--review`・`--from` も使える。`--review` のときも `--pipe <名前>` を付ける） |

### pipe-in-gen（パイプを作る）

| やりたいこと | コマンド |
| --- | --- |
| ひな形と、作ったパイプの一覧 | `pipe-in-gen list --project <対象>` |
| ひな形から作る（dev / diagrams / spec-qa） | `pipe-in-gen new <名前> --from <ひな形> --project <対象>` |
| 目的から段を組ませる（Claude が設計する。利用料がかかる） | `pipe-in-gen design <名前> --purpose "…" --project <対象>` |
| 定義の誤りを調べる | `pipe-in-gen check <名前> --project <対象>` |
| 仕様書レビューの指摘の誤りを調べる（LLM は呼ばない） | `pipe-in-gen findings-check <指摘のファイル> --sources <台帳> --spec <仕様書> [--spec …]`（終了コード 0＝誤りなし・1＝誤りあり・2＝入力を受け取れない。くわしくは `docs/guide/pipes.md` の「指摘の検査」） |

作ったパイプは対象の `.pipe-in/pipes/pipe-in-<名前>/`（pipe.toml・prompts/・README.md）に置かれる（`--pipes-dir` か `PIPE_IN_PIPES_DIR` で変えられる。前の版の置き場所も読む。`docs/guide/migrate.md` を参照）。

### VSCode 拡張（コマンドパレット）

| コマンド | すること |
| --- | --- |
| pipe-in: 実行を見る | 流している・流した実行を、図と出力で見る（ステータスバーのボタンでも開く）。実行が新しく確認待ちになると右下に知らせが出る（設定 `pipe-in.notifyWhenWaiting`。開いた直後からある分とパネルで見ている実行は知らせない） |
| pipe-in: パイプ作業台を開く | パイプ作業台を開く。形のブロックを置き、プラグをコンセントに差してつなぎ、各ブロックで Claude に頼むことと SDK の設定を決めて保存する |

### もっと詳しく

- 開発のルール（原則・仕様・設計・テスト・進め方）：docs/development/、決めたことの記録：docs/decisions/
- pipe-in 全体：`docs/guide/`（目次 `docs/guide/README.md`。流し方 `usage.md`・パイプの書き方と検証・分岐・Agent SDK の設定 `pipes.md`・終了コード `records.md` など）
- VSCode 拡張と作業台：vscode/README.md
- プラグイン：`docs/guide/plugin.md`
