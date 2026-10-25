# pipe-in を開発する

[ガイドの目次](README.md) · [README](../../README.md) — pipe-in そのものを直す・機能を足すときの説明です。

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

直す・機能を足すときの決まり（原則・仕様の書き方・設計・テスト・進め方）は [docs/development/](../development/) に、機能ごとに何をなぜ決めたかは [docs/decisions/](../decisions/) にあります。README とガイドの画像の撮り直し方は [docs/assets/README.md](../assets/README.md) にあります。

## Claude Code で開発するとき

何かを直した・足したら、文書もそろえます。`/pipe-docs [要点か範囲]` が、変えたファイルを集めて文書係のサブエージェント `pipe-in-documenter` に README.md・`docs/guide/`・`docs/development/` などを直させます（CLAUDE.md・`/pipe-help`・決定の記録は案を見せ、承認したものだけを直します）。コードを変えたのに文書が変わっていないまま止まろうとすると、一度だけ知らせが出ます。くわしくは [docs/development/workflow.md](../development/workflow.md) の「4. そろえる」にあります。

このリポジトリの開発用スキル `/pipe-audit`（文書・定義・コードの食い違いの監査）と `/pipe-advise`（公式の文書と照らした助言）は、会話を開かずに `claude -p` でも流せます。プロンプトの先頭を `/pipe-audit` か `/pipe-advise` にして、このリポジトリ（または worktree）の中で呼びます。

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

### スキルの構成と許可の規則

`/pipe-in` のスキル（`.claude/skills/pipe-in/`）は、必ず守る決まりを `SKILL.md` の冒頭の「必ず守ること」に置き、長い手順（記録のコマンド・`--artifact`・画面の確認）を同じフォルダの補助ファイル（`record.md`・`artifact.md`・`screen-check.md`）に分けています。長い会話では、自動の要約のあとに、呼んだスキルの先頭（5,000 トークンまで。スキル全部で 25,000 トークンまで）しか戻らないため、決まりを先頭に集めました（公式の文書による。日本語 1 字が何トークンかは確かめていません）。

- 手順があやふやになったら、思い出しで進めず、`SKILL.md` と補助ファイルの該当する節を読み直します。補助ファイルが読めないときは、止まって人に伝えます。機能の枝が補助ファイルを持たない古い worktree なら、`git rebase --autostash main` で載せ直してから読み直します。
- `.claude/settings.json` の `allow` に、手元のテスト・型検査・ビルド・確認用ページの作成と配信の 5 つのコマンドを、完全に一致する形で足しました（`npm --prefix vscode test`・`npm --prefix vscode run typecheck`・`npm --prefix vscode run build`・`npm --prefix vscode run preview`・`python -m http.server 8765 --bind 127.0.0.1 --directory vscode/out/preview`）。コマンドは 1 つずつ流します（つないだときは、どの部分も規則に当たらないと確認が出ます）。
- `ask`（確認を出す一覧）に `git commit`・`git merge` を足しました（`git push` は前から入っています）。公式の文書では、規則は deny → ask → allow の順に当てはめ、個人の設定（`.claude/settings.local.json`）の `allow` は共有の `ask` より上になりません（実機では確かめていません）。確認そのものを飛ばすモード（`bypassPermissions`）では、出ないことがあります。また `ask` は守りの境目ではありません。つないだコマンドはどれか 1 つが当たれば確認が出ますが、`git -C . commit` のような別の書き方には当たりません。
- `record` の規則（`python -m pipe_in record …`）は足していません。`--input` で任意のファイルを読め、`--project` で別のフォルダに書けるためです。
- 個人の許可は、`.claude/settings.local.json` に書きます（`.gitignore` 済みで、リポジトリには入りません）。worktree で作業するときも、main の作業フォルダのこのファイルが読まれ、すべての worktree に効きます（公式の文書。v2.1.211 以降）。
- 足した `allow` の 5 つは、フックが効かないとき（`python` が無い・時間切れなど。下の「フックが働く条件」）と、フックが見ない呼び出し元（メインと、`pipe-in-` で始まらないサブエージェント）では、確認なしで流れます。手元のテスト・型検査・ビルド・確認用ページの作成と配信だけなので、このリスクを受け入れました。
- 新しい worktree では、その枝の `.claude/settings.json` が読まれます。枝がこの変更より前の main から切られていると、5 つの `allow` はまだありません。共有の `allow` は作業フォルダの信頼のあとに効き、worktree の信頼は main の作業フォルダの場所で見ます（`ask` と `deny` は信頼を待たずに効きます）。どちらも公式の文書によるもので、実機では確かめていません。効かなくても、確認が今までどおり出るだけです。

この決めたことと理由は [D0039](../decisions/D0039-skill-tidy.md) にあります。

### 確認待ちの知らせ（`/pipe-in`）

人の確認が要る段で止まったことに、画面を見に行かなくても気づくための知らせが、3 つあります。

- **VSCode の拡張**：新しく確認待ちになった実行を、VSCode の右下に知らせます。設定 `pipe-in.notifyWhenWaiting` で切れます。くわしくは [VSCode の拡張](vscode.md#確認待ちの知らせ) にあります。
- **`/pipe-in` スキルの PushNotification**：スキルは、`record wait <段>` を書いたあと、人に聞く前に、Claude Code の PushNotification ツールで知らせます。文は、段の名前と「確認待ち」だけの短い固定の形で、要件メモ・パス・秘密は入れません。`--auto` で止まって聞く場面（要件定義の決めきれない点・文書係の案・監査と助言の報告・不合格 3 回）でも、聞く前に知らせます。`--auto` で止まらずに進むところ（`wait` を書かないところ）では知らせません。PushNotification のツールが無い会話（ツールの一覧にない・呼べない）では、何も言わず、何もしない決まりです。失敗しても段は止めません。これは拡張の設定では切れない知らせです（別の仕組みです）。切りたいときは、ツールを使えない状態にするか、スキルを直します。PushNotification はデスクトップに知らせ、Remote Control がつながっていればスマホにも届きます（Bedrock・Vertex などではスマホに届きません。端末を見ているあいだも、スマホには届きません）。働きは公式の文書（[道具の一覧](https://code.claude.com/docs/en/tools-reference)）で、引数はツールの説明で確かめました。スキルの指示で出すので、フックのように必ず出るとは限りません。本筋は記録（`record wait`）と拡張の知らせで、これは補助です。
- **Claude Code 自身の通知**：Claude Code の設定 `preferredNotifChannel`（`/config` では「Local notifications」）を使うと、許可待ちと、仕事を終えて入力待ちになったときに知らせを受けられます。既定の `auto` は iTerm2・Ghostty・Kitty でだけデスクトップの通知を出します。ほかの端末では `"terminal_bell"` にすると端末のベルが鳴ります（ほかの値は `iterm2`・`iterm2_with_bell`・`kitty`・`ghostty`・`notifications_disabled`）。ここまでは公式の文書で確かめた内容です（[設定の一覧](https://code.claude.com/docs/en/settings-reference)・[端末の設定](https://code.claude.com/docs/en/terminal-config)）。`/config` の画面での見え方は、実機では確かめていません。設定は各自の Claude Code の側（`~/.claude/settings.json` など）にあり、このリポジトリは配りません。

Claude Code の Notification フックは、このリポジトリに足していません。理由は 2 つです。フックの標準出力は端末に出ず（公式の文書では、ほとんどのイベントで debug のログに行きます）、ベルの文字を出すだけでは鳴りません。鳴らすには `terminalSequence` を返す形が要ります。もう 1 つは、Claude Code に組み込みの通知（上の `preferredNotifChannel`）で足りるためです（フックは組み込みの通知と並んで動き、置き換えません）。

組み込みの通知が出ない端末で鳴らしたいときは、各自の `~/.claude/settings.json` に次のようなフックを書けます（任意。このリポジトリには入れません。`-p` と Agent SDK では効きません）。`matcher` には `permission_prompt`（許可待ち）・`idle_prompt`（入力待ち）などがあります。

```json
{
  "hooks": {
    "Notification": [
      {
        "matcher": "permission_prompt|idle_prompt",
        "hooks": [{ "type": "command", "command": "echo '{\"terminalSequence\": \"\\u0007\"}'" }]
      }
    ]
  }
}
```そのため `.claude/settings.json` の `hooks` は `PreToolUse` と `Stop` のままです。ベルや OS の通知コマンドは、こちらでは扱いません。

### フックが働く条件

`/pipe-in` の段を受け持つサブエージェントの書ける場所と Bash は、`.claude/hooks/pipe_in_guard.py` が絞ります。Claude Code が道具を呼ぶたびに、`.claude/settings.json` の `command`（`python "$CLAUDE_PROJECT_DIR/.claude/hooks/pipe_in_guard.py"`。`timeout` は 30 秒）でこのフックを動かします。

- フックが働くには、`python` が動くことが要ります。`python` が見つからない・時間切れ・構文エラーのときは、Python の中では止められないので、フックが効かず通る形になります（絞りが外れます）。macOS や Linux では、`python` が無く `python3` だけのことがあります。
- `/pipe-in` を始める前に、`python --version` で `python` が動くことを確かめてください。公式の文書によると、フックが失敗すると会話に `hook error` の知らせが出ます。`/pipe-in` の最初の道具の呼び出しのあとに、この知らせが出ていないかも見てください。出ていれば、フックが効いていません。
- `python` が動いていれば、判断の途中で例外が出ても、`pipe-in-*` の呼び出しは止めます（読むだけの道具と、報告を親に渡す道具は通します）。メインなど `pipe-in-` で始まらない呼び出しは止めません。フックが壊れたときに、それを直す呼び出しまで止まらないようにするためです（ただし、入力そのものが読めず、だれの呼び出しか分からないときは、メインでも止めます）。`agent_type` が文字列でも null でもない呼び出し（リスト・数値など）も、分からない相手として止めます。
- 止めるときは、まず止める理由つきの deny の JSON を出します。それも書けないとき（標準出力が閉じているなど）は、JSON に頼らず、標準エラーに理由を書いて終了コード 2 で止めます。公式の文書によると、終了コード 2 のときは標準エラーの文が、止めた理由として Claude（サブエージェント）に届きます。人にどう見えるかは、実際の Claude Code ではまだ確かめていません。
- `.claude/settings.json` のフックには `onFailure` を付けていません。付けると、`python` が無い環境でメインを含むすべての道具が止まり、フックを直すこともできなくなるためです（`onFailure` は v2.1.295 以降の Claude Code で使えます）。
- Windows で Git Bash が無いときのフックの動きは、確かめていません。このフックの `command` は、シェルが `$CLAUDE_PROJECT_DIR` を展開する書き方です。公式の文書によると、Git Bash が無い Windows では、この書き方のフックが失敗すると、通らずに道具の呼び出しが止まることがあります（`onFailure` を付けていなくても。メインも止まります）。

この決めたことと理由は [D0032](../decisions/D0032-guard-fail-closed.md) にあります。
