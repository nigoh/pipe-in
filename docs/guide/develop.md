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

## CI（GitHub Actions）

main 向けの PR と main への push で、`.github/workflows/ci.yml` が自動でテストを流します。`python` ジョブ（Python 3.11）は `pip install -e '.[dev]'` のあと `pytest -q`、`extension` ジョブ（Node 22）は `vscode/` で `npm ci`・`npm test`・`npm run typecheck`・`npm run build` を順に流します。権限は `contents: read` だけで、秘密（API キーなど）は使わず、SDK も呼ばないので利用料はかかりません。

手元で同じものを流すには：

```bash
pip install -e '.[dev]' && pytest -q
cd vscode && npm ci && npm test && npm run typecheck && npm run build
```

落ちたときは、PR の Checks で `python` か `extension` を開き、落ちた手順のログを見て、手元で同じものを流して直します。ブランチの保護の設定など、くわしくは [docs/development/workflow.md](../development/workflow.md) の「6. CI」にあります。

## PR と issue

PR と issue は、`.github/` のテンプレートに沿って書きます。PR を開くと本文に節が入り、issue は「不具合」か「機能の要望」の form で書けます（どちらにも当たらなければ白紙の issue で）。PR のタイトルはコミットの1行目と同じ形にして決定の記録の番号を後ろに付け、流れや依存の向きを示したいときは Mermaid の図を添えられます（任意）。秘密やユーザー名の入ったパスは書かないでください。決まりは [docs/development/workflow.md](../development/workflow.md) の「7. PR と issue」にあります。

## Claude Code で開発するとき

何かを直した・足したら、文書もそろえます。`/pipe-docs [要点か範囲]` が、変えたファイルを集めて文書係のサブエージェント `pipe-in-documenter` に README.md・`docs/guide/`・`docs/development/` などを直させます（CLAUDE.md・`/pipe-help`・決定の記録は案を見せ、承認したものだけを直します）。コードを変えたのに文書が変わっていないまま止まろうとすると、一度だけ知らせが出ます。くわしくは [docs/development/workflow.md](../development/workflow.md) の「4. そろえる」にあります。

考えがまだ固まっていないときは、`/pipe-talk [話したいこと]` で壁打ちができます。区切りで「決まったこと・残った問い・やりたいこと」の要約を作り、手元だけの `docs/talk/<日時>-<名前>.md`（`.gitignore` 済み。書く前に `git check-ignore` で確かめます）に残します。そのうえで次の作業の候補（GitHub の issue・デザイン・`/pipe-in`・計画ボード）を出し、人が選ぶまでどれも行いません。issue を作る・Figma に書くなど外へ出す操作は、中身を全文見せて承認を得てからだけです（`gh issue create` は `.claude/settings.json` の `ask` にも入れてあります）。`/pipe-in` と `/pipe-plan add` は Claude からは始めず、人が貼って流す1行を示します。決めたことと理由は [D0056](../decisions/D0056-pipe-talk.md) にあります。

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

`/pipe-in` のスキル（`.claude/skills/pipe-in/`）は、必ず守る決まりを `SKILL.md` の冒頭の「必ず守ること」に置き、長い手順（記録のコマンド・`--artifact`・画面の確認・無人の実行）を同じフォルダの補助ファイル（`record.md`・`artifact.md`・`screen-check.md`・`unattended.md`）に分けています。長い会話では、自動の要約のあとに、呼んだスキルの先頭（5,000 トークンまで。スキル全部で 25,000 トークンまで）しか戻らないため、決まりを先頭に集めました（公式の文書による。日本語 1 字が何トークンかは確かめていません）。

- 手順があやふやになったら、思い出しで進めず、`SKILL.md` と補助ファイルの該当する節を読み直します。補助ファイルが読めないときは、止まって人に伝えます。機能の枝が補助ファイルを持たない古い worktree なら、`git rebase --autostash main` で載せ直してから読み直します。
- `.claude/settings.json` の `allow` に、手元のテスト・型検査・ビルド・確認用ページの作成と配信の 5 つのコマンドを、完全に一致する形で足しました（`npm --prefix vscode test`・`npm --prefix vscode run typecheck`・`npm --prefix vscode run build`・`npm --prefix vscode run preview`・`python -m http.server 8765 --bind 127.0.0.1 --directory vscode/out/preview`）。コマンドは 1 つずつ流します（つないだときは、どの部分も規則に当たらないと確認が出ます）。
- `ask`（確認を出す一覧）には、main に入れること（`git merge`・`gh pr merge`）・publish（`npm publish`・`npx vsce publish`・`twine upload`）・`gh issue create`・main へ届きうる `git push` の形（main への push・強制・全部・削除・枝名なしなど。`git -C <フォルダ> push` のような `git` の旗つきの書き方も）・`gh api` の merge と `refs/heads/main` を入れています。`git commit`・枝名を書く `git push -u origin <枝>`・`gh pr create` は入れていません（D0073）。`ask` に当たる操作は、公式の文書では auto モードでも必ず確認になり、実機でも、人が答えるまで進まないことを確かめました（2026-11-02 の夜の実行）。人のいない実行ではその確認で止まったままになるので、人が開始の指示で承認した「無人の実行」だけが、その枝への commit・push・PR の作成を確認なしでできるようにしました（定義と範囲は `CLAUDE.md`。下の「無人の実行の始め方」）。個人の設定（`.claude/settings.local.json`）の `allow` も PreToolUse フックの許可も `ask` を越えません。これは公式の文書によることで、実機では確かめていません。また `ask` は守りの境目ではありません。書かれた形にしか当たらず、別名・`sh -c`・引用符つきの書き方などは通ります。止めるのは `CLAUDE.md` の決まりと GitHub のブランチ保護です（すり抜けの道は [workflow.md](../development/workflow.md) の「6. CI」）。
- `record` の規則（`python -m pipe_in record …`）は足していません。`--input` で任意のファイルを読め、`--project` で別のフォルダに書けるためです。
- 代わりに、`python -m pipe_in skill record …`・`python -m pipe_in skill worktree …`・`python -m pipe_in skill decision-number` の入口を許しています（`Bash(python -m pipe_in skill:*)`）。今のフォルダだけを相手にし、`--input`・`--feedback-file`・`--project`・`--config` を断る入口です。あわせて `python --version` と `npm --prefix vscode ci` も、完全に一致する形で許しています（[D0049](../decisions/D0049-skill-shell.md)）。
- 個人の許可は、`.claude/settings.local.json` に書きます（`.gitignore` 済みで、リポジトリには入りません）。worktree で作業するときも、main の作業フォルダのこのファイルが読まれ、すべての worktree に効きます（公式の文書。v2.1.211 以降）。
- 足した `allow` の 5 つは、フックが効かないとき（`python` が無い・時間切れなど。下の「フックが働く条件」）と、フックが見ない呼び出し元（メインと、`pipe-in-` で始まらないサブエージェント）では、確認なしで流れます。手元のテスト・型検査・ビルド・確認用ページの作成と配信だけなので、このリスクを受け入れました。
- 新しい worktree では、その枝の `.claude/settings.json` が読まれます。枝がこの変更より前の main から切られていると、5 つの `allow` はまだありません。共有の `allow` は作業フォルダの信頼のあとに効き、worktree の信頼は main の作業フォルダの場所で見ます（`ask` と `deny` は信頼を待たずに効きます）。どちらも公式の文書によるもので、実機では確かめていません。効かなくても、確認が今までどおり出るだけです。 同じく、D0073 より前の main から切った枝は、`ask` に `git commit`・`git push`・`gh pr create` がまだ残り、その枝では確認が出ます（無人の実行の前に `python -m pipe_in worktree sync` で載せ直します。`sync` は origin の main を取ってから載せます。取れなければ止まり、手元の main に載せるときは `--no-fetch` を付けます）。

この決めたことと理由は [D0039](../decisions/D0039-skill-tidy.md) にあります。

### 無人の実行の始め方

夜のまとめ実行のように、人が居ない間に `/pipe-in` を最後まで進めさせるときの始め方です。何が「無人の実行」か、何をしてよく何をしないかは `CLAUDE.md` の「必ず守ること」が決めていて、ここには使い方だけを書きます（スキルが流す手順は `.claude/skills/pipe-in/unattended.md`、決めたことと理由は D0073）。

1. 始める前に、その枝を `python -m pipe_in worktree sync` で載せ直します。D0073 より前の main から切った枝は、`ask` に `git commit`・`git push`・`gh pr create` がまだ残っていて、確認で止まります。
2. 開始の指示（`/pipe-in` の引数、または人が書いたルーチンのプロンプト）に、2つを書きます。人が答えない実行であること。commit・push・PR の作成を名指しして承認すること。無人の実行は `/pipe-in --auto` で始めます（`--auto` が無いと、最初の段の区切りで止まり、終わりの報告に書いて終えます）。ルーチン（クラウドの定期実行）は、指示が無いと `claude/` で始まる枝に push します。`/pipe-in` は `feat/<名前>` の枝を切ってそこに push するので、プロンプトでほかの枝を指さないでください（夜のまとめ実行だけは例外で、名指しした `night/<日付>` の枝を指します。下の「夜のまとめ実行（親の進め方）」）。

   ```text
   /pipe-in --auto 無人の実行です（夜のまとめ実行で、人は居ません）。commit・push・PR の作成を承認します。要件メモ：…
   ```

3. 承認しても、範囲は広がりません。main に入れること（`git merge`・`gh pr merge`・main への push）・publish・`gh issue create` は、無人ではしません。main に入れるのは、朝に人が PR を見てします。
4. 質問欄は使われません。決めきれない点は推しの案で決まり、監査と助言は直されずに残ります。朝は、終わりの報告（した操作としなかったこと）と、決定の記録の「対象外・残った課題」を読んで、直す項目を選びます。
5. main の保護（PR を必須・必須のチェック）を入れておくと、`ask` や決まりをすり抜けた操作も GitHub が止めます（[workflow.md](../development/workflow.md) の「6. CI」）。

### 夜のまとめ実行（親の進め方）

夜のまとめ実行は、何件かの機能を、1本の「まとめの枝」`night/<日付>` に件ごとの 1 コミットで積み、main 向けの PR を 1 つにまとめる使い方です（決めたことと理由は D0074）。件ごとに PR を作らないので、朝の確認が 1 回で済みます。ここは親（メインの会話）の進め方で、子（件ごとの `/pipe-in`）の手順は `.claude/skills/pipe-in/unattended.md`、何をしてよいかの範囲は `CLAUDE.md` の「必ず守ること」にあります。

1. **開始の指示**に、無人の実行であることと commit・push・PR の作成の承認（上の「無人の実行の始め方」の 2）に加えて、まとめの枝 `night/<日付>` を名指しして、その枝への早送りの push を承認する文を書きます。書式は決まっておらず、自由な文でかまいません。承認は名指しした枝だけに効きます。auto モードの判定が承認として読むのは、動作と相手を具体的に名指しした、人の書いた文です。枝の名前・早送りだけであること・push のコマンドの形まで書きます。

   ```text
   無人の実行です（夜のまとめ実行で、人は居ません）。commit・push・PR の作成を承認します。まとめの枝 night/2026-11-04 への早送りの push を承認します（git push origin HEAD:night/2026-11-04 の形だけ。強制の push はしない）。claude/ の枝は作らず、件ごとの枝は push せず、件ごとの PR も作らないでください。次の 3 件を順に流してください：…
   ```

   親は子を起こすたびに、この承認の文を範囲を変えずに写して、子の開始の指示に入れます（`CLAUDE.md` の「親が起こす子の実行」）。

2. **子の作り方**：件ごとに 1 つ、順に起こします（並列にしない。後の件が前の件の積んだ番号と変更の上に載るため）。始めに、親がまとめの枝を `python -m pipe_in skill worktree new <日付> --kind night` で origin の main から切り、`git push -u origin night/<日付>` で出してから、子を起こします。同じ日の 2 回目は名前に `-2` を付けます（origin に同じ名前の枝があると断られます）。子は auto モードで起こします。auto でない起こし方（手動のモード・`claude -p` の既定など）では、`allow` に無い `git fetch`・`git commit`・`git push` が確認になり（`claude -p` では断られ）、夜のうちに止まります（`ask` に当たらないことと、確認が出ないことは同じではありません）。
3. **待ち方**：子の完了の返事を待ちます。次の件は、前の件が積み終わってから起こします。
4. **子が止まったとき**：`BLOCKED`・`TEST_FAILED` で止まった件は積まず、飛ばして次へ進みます。止まった理由と、積まなかったことを、終わりの報告に書きます。
5. **まとめ**：全部の件が済んだら、親が main 向けの PR を 1 つ作ります。本文に、積んだ件と止まった件を書きます。件が積まれたあとは、`python -m pipe_in skill worktree clean --base night/<日付>` で、子の worktree を片付けられます。
6. **朝の入れ方**：人が PR の CI を見て、merge commit で入れます。squash の merge は件ごとのコミットが 1 つに潰れ、`worktree clean` が「入った」と見分けられずに枝が残ります（rebase の merge も同じです）。入れたあとの `worktree clean` は、まとめの枝の worktree を「始めたばかりかもしれません」と残すことがあります（手元ではコミットしていないため）。そのときは、`git worktree remove` と `git branch -D night/<日付>` で手で消します。

main に入れること・publish・`gh issue create` は、夜のまとめ実行でも無人ではしません（上の「無人の実行の始め方」の 3）。

件ごとの変更がぶつかりにくいよう、決定の記録の一覧は表の最後の行の下に 1 行足す形で、`.gitattributes` の `merge=union` で自動に解けます。載せ直しのあとは `pytest -q` を流してください（並び違いは `tests/test_doc_shape.py` が知らせます。決めたことと理由は D0075、書き方は `docs/development/workflow.md` の「8. 並列の作業でぶつからない書き方」）。

GitHub の設定は、人が前もってします。クラウドの入れ物からの push を止めるのは GitHub の設定だけです（入れ物の中継は、どの枝へ push するかを限りません）。

- main は PR を必須にし、規則を迂回できる人・アプリを空にします。
- `night/*` の枝には ruleset で、強制の push と削除を禁じます（早送りだけが通ります）。
- つないだ GitHub のアカウントが、規則を迂回できる権限（管理者など）を持っていないかも確かめます。迂回できるアカウントからの push には、規則が効きません。

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
