# D0011 会話を開かずに /pipe-audit・/pipe-advise を流す

イシュー #9（ロードマップ段階0、親 #3）。

## 目的

`/pipe-audit`・`/pipe-advise` を、会話を開かずに（`claude -p` で）確実に流せるよう、決まった呼び方を1つ決め、`/pipe-help` と README に書き、テストで守る。D0008 の残った課題を解く。

## 機能要件と受け入れ基準

テストは `tests/test_headless_audit.py`（下では `::` からの名前だけを書く）。

- FR-01 非対話で `/pipe-audit` を流す呼び方を1つ決める。プロンプトの先頭を `/pipe-audit` にし、範囲を後ろに続ける。`--bare`・`--disable-slash-commands` は付けない
- FR-02 `/pipe-advise` も同じ形（先頭を `/pipe-advise`）で流す呼び方を決める
- FR-03 呼び方は読むだけに絞る（`--permission-mode dontAsk` と、要る道具だけの `--allowedTools`）。guard（`.claude/hooks/pipe_in_guard.py`）は緩めない
- FR-04 2つの SKILL.md は `disable-model-invocation: true` を保つ。`user-invocable: false` にはしない
- FR-05 決めた呼び方を `/pipe-help` と README に書く。両方の文字列とオプションが一致する
- FR-06 非対話では人に承認を聞けないので、報告を出して止まるところまでとし、直すのは人が承認したあと会話でする、と書く
- FR-07 スキルとして開かれなかったときの見分け方を書く
- FR-08 この決定の記録を書く
  - D0011-AC-01 2つの SKILL.md の frontmatter に `disable-model-invocation: true` があり、`user-invocable: false` は無い（`::test_スキルの設定は人が呼ぶだけでモデルが勝手に呼べない形を保つ`）
  - D0011-AC-02 `/pipe-help` に `claude -p "/pipe-audit` と `claude -p "/pipe-advise` で始まる呼び方の行がある（`::test_pipe_helpに会話を開かない呼び方の例がある`）
  - D0011-AC-03 README に同じ2つの呼び方があり、`/pipe-help` のものと空白をそろえて同じ（`::test_readmeに会話を開かない呼び方の例がある`・`::test_readmeとpipe_helpの呼び方が空白をそろえて同じ`）
  - D0011-AC-04 `/pipe-help`・README の呼び方の行に、スキルを無効にするオプションを付けていない。この記録には呼び方の行を書かない（`::test_呼び方の例にスキルを無効にするオプションを付けていない`・`::test_D0011に呼び方の行を書かない`）
  - D0011-AC-05 呼び方の行に `--permission-mode dontAsk`・`--tools`・`--allowedTools` があり、許す道具は Agent・Read・Grep・Glob・WebSearch・公式の文書の WebFetch だけ（`--tools` は Agent・Read・Grep・Glob と助言の Web の道具）。書き込みや実行を許す語が無く、Agent の名前は SKILL.md の `allowed-tools` と一致する（`::test_呼び方は確認なしで断るモードと許す道具の一覧を付けている`・`::test_呼び方に書き込みやコマンド実行を許す語が無い`・`::test_許す道具は読む道具と公式の文書の取得だけ`・`::test_呼び方で許すサブエージェントがスキルのallowed_toolsと一致する`）
  - D0011-AC-06 `/pipe-help`・README に、報告を出して止まることと、直すのは承認のあと会話でと書いてある（`::test_非対話では報告で止まり直すのは承認のあと会話でと書いてある`）
  - D0011-AC-07 `/pipe-help`・README に、開かれたかの見分け方（`system/init` の `slash_commands`）が書いてある（`::test_開かれなかったときの見分け方が書いてある`）
  - D0011-AC-08（実機）決めた呼び方の文字列のとおりに `/pipe-audit` を流すと、スキルとして開かれ、`pipe-in-auditor` が走り、報告で止まり、`git status` に差が出ない
  - D0011-AC-09（実機）`/pipe-advise` についても同じ。WebFetch は公式の文書の場所だけ
  - D0011-AC-10（実機）`--bare` を付けると `/pipe-audit` が開かれないことを1回確かめ、D0008 のときの原因の候補のどれに当たるかを書く
  - D0011-AC-11 D0008-AC-17・AC-19 の既存のテストがそのまま通る（`tests/test_pipe_in_guard.py::test_d0008_ac17_audit_and_advise_skills` ほか）
  - D0011-AC-12 D0008 の記録は書き換えない。この記録が D0008 の残った課題を解くと書く（`::test_D0008の記録はD0011に触れずそのまま`・`::test_D0011は残った課題を解くと書く`・`::test_決定の記録D0011があり索引に行がある`）

## 決めたことと理由

- **D0008 の残った課題を解く。** D0008 の「対象外・残った課題」の最後の項目（`claude -p` に `/pipe-audit …` を渡すと開かれなかった）を、この記録で解く。D0008 の記録は書き換えない。
- **案 A：先頭を `/pipe-audit` にした `claude -p` ＋ `dontAsk` ＋ `--allowedTools`。** 依存もコードも足さず、guard も緩めない。スキル本文（範囲の渡し方・承認の止まり）がそのまま使われる。呼び方の正しさは文書とテストで守る。
- **選ばなかった案。**
  - B（包む入口：スクリプトや `pipe-in` のサブコマンド）：打ち間違いは防げるが、置き場所と依存の向きの検討が要る。公式の呼び方で通るので過剰。
  - C（`--agent` で `pipe-in-auditor` を直接起動）：スキルを通らないので、範囲の渡し方や「承認した項目だけを直す」手順が使われず、報告のあとメインが直す流れが切れる。
  - `--restricted`：プロジェクトの設定を読まないので、`.claude/settings.json` のフック（guard）が載らない。読むだけの保証が外れるので使わない（公式の文書の cli-reference からの判断で、実機では試していない）。
  - A が通らなくなったときだけ、B を別の記録で検討する。
- **`disable-model-invocation: true` を保つ。** 公式の文書（https://code.claude.com/docs/en/skills の Invocation control）では、これは Claude が自分で（Skill ツールで）呼ぶのを止めるだけで、人の `/名前` は許す。人が呼ぶ入口を残したまま、モデルが勝手に監査を始めないようにできる。`user-invocable: false` は逆に人の `/名前` を止めるので使わない。
- **`claude -p` でも、人が呼ぶスキルは展開される。** プロンプトの先頭に `/名前` を書くと、実行前に展開される（https://code.claude.com/docs/en/headless ）。`--bare`・`--disable-slash-commands` ではスキルが探されず、`/pipe-audit …` がふつうの文としてモデルに渡る（https://code.claude.com/docs/en/cli-reference ）。だから呼び方にはこの2つを付けない。
- **読むだけに絞る組（`--tools` で道具そのものを絞る）。** 呼び方は次の組み立てにした。
  - `--tools` で使える組み込みの道具そのものを絞る。監査は Agent・Read・Grep・Glob、助言はそれに WebFetch・WebSearch を足す。Bash・Write・Edit などは道具として出てこない。
  - `--allowedTools` は「確認なしで通す」許可で、制限ではない。サブエージェントへの委譲（`Agent(…)`）・Read・Grep・Glob と、助言のときの WebSearch・公式の文書の WebFetch だけを書く。`Read Grep Glob` を書くのは、Linux・macOS では Glob と Grep が初めの道具に入らず、名前を書くと戻るため（tools-reference）。
  - `--permission-mode dontAsk` が断るのは、確認が要る呼び出しのうち許可に当たらないもの。「`--allowedTools` に無い道具を全部断る」わけではないので、`--tools` で絞る。
  - 読むだけ・行き先の絞りの保証は、`.claude/hooks/pipe_in_guard.py` とサブエージェントの `tools:` が担う。
- **助言に WebSearch と残りの公式の場所を許した理由。** 助言のサブエージェント（`pipe-in-advisor`）は WebSearch と、公式の文書・github の WebFetch を使う前提で作られている。許可に無いと `dontAsk` で断られて助言が成り立たない。WebFetch の行き先は、ガードの `DOC_HOSTS`・`GITHUB_HOSTS`（code.claude.com・docs.claude.com・docs.anthropic.com・platform.claude.com・github.com・raw.githubusercontent.com）と同じにした（テストが見る）。WebSearch の行き先（allowed_domains）と、github の `anthropics/` の下への絞りはガードが受け持つ（許可の書き方では絞れない）。
- **助言で分かったこと。** スキルの `allowed-tools` は、確認なしで使える道具の許可で、制限ではない。読むだけの保証は、ガードとサブエージェントの `tools:` が担う。
- **任意で足せるもの。** `--max-turns`（回数の上限）、`--permission-prompts none`（断られたときに再試行させない。v2.1.259 以降）。例の文字列には入れない。
- **信頼していない作業フォルダでは `--allowedTools` を省かない。** 信頼していない作業フォルダ（新しい worktree など）では、`.claude/settings.json` の allow が無視される。呼び方に明示しておけば、そのままでも通る。さらに `.mcp.json` のサーバーは確認なしでつながる。入れている MCP の道具（プラグインのものを含む）は `--tools` では消えないが、`dontAsk` で許可に無ければ断られる。
- **`--bare` は将来 `-p` の既定になる。** 公式の文書にそうある。そうなるとスキルが開かれなくなるので、`--bare` を付けないだけでなく、見分け方（`slash_commands`・`skills`）で確かめる。サブエージェントが動いたかは `parent_tool_use_id` で追える。
- **`--max-budget-usd` は目安の上限。** 超えることがある（サブエージェントの費用も数える）。
- **例に `--model` と `--output-format stream-json --verbose` を入れない。** 例の文字列を1つにそろえて、文書どうしの一致を取りやすくするため。足し方は本文に書いた。
- **README の節は `###`。** `tests/test_readme.py` が `##` の節の順を固定しているので、`## 使い方` の中に小さな節として置いた。

## 設計の前に流した実機の試し

Claude Code 2.1.302、モデル sonnet、上限 5 ドル。どちらもファイルの変更なし。

- 監査（範囲 `docs/roadmap.md`）：スキルとして展開された。メインは Skill ツールを使わず `Agent(pipe-in-auditor)` を1回。サブエージェントは Read 2・Grep 6・Glob 1。報告2件で止まった。約 0.23 ドル。
- 助言：展開された。`Agent(pipe-in-advisor)` 1回、WebFetch 2回（code.claude.com の skills と permissions だけ）。報告で止まった。約 0.24 ドル。
- 信頼していない作業フォルダでは「Ignoring 15 permissions.allow entries from .claude/settings.json: this workspace has not been trusted.」と出て、settings.json の allow が無視された。
- D0008 で展開されなかった原因は、そのときの版と付けたオプションの記録が無いので特定できない。今の版とこの呼び方では再現しない。

## 検証のあとの監査・助言で見つかったことと直したこと

人が「全部直す」と承認した。

- 助言（V-01〜08）：`dontAsk` の説明の誤り（V-01）、`--allowedTools` は許可で制限ではない（V-02）、助言の WebSearch と残りの公式の場所（V-03）、`--bare` が将来 `-p` の既定になる（V-04）、信頼していない作業フォルダでの `.mcp.json`（V-05）、任意の `--max-turns`・`--permission-prompts none`（V-06）、確かめるときの `skills` と `parent_tool_use_id`（V-07）、`--max-budget-usd` は目安（V-08）。呼び方を `--tools` 付きの2行に変え、README と `/pipe-help` の説明を直した。
- 監査（A-01〜06）：A-01・A-02・A-03 はテスト側の直し（言い方・呼び方の行を書かない検査・節に絞る検査）。A-04 はこの記録の「確かめたこと」を今の状態に、A-05 は見分け方を `pipe-audit`（`/pipe-advise` のときは `pipe-advise`）にして助言も確かめる、A-06 は頭のイシューの書き方を直した。

## 対象外・残った課題

- MCP の道具も使えないようにすること（`--disallowedTools "mcp__*"`。2回目の助言 V-01）はイシュー #34。そうすれば `--strict-mcp-config` は要らなくなる見込み（プラグインの MCP に効くかは確かめていない）。
- 監査・助言のサブエージェントに回数の上限（`maxTurns`）を付けること（2回目の助言 V-04）はイシュー #35。
- 動画のパイプの件はイシュー #33（このブランチの外）。

- 包む入口（スクリプト・`pipe-in` のサブコマンド）を足すこと（案 B）。`--agent` で直接起動すること（案 C）。
- Agent SDK（Python）から呼ぶ入口を本体に足すこと。
- 非対話で直すこと（承認の仕組みが無い）。
- `/pipe-in`・`/pipe-help` など、ほかのスキルの非対話化。
- `disable-model-invocation: true` を外すこと、guard を緩めること、依存を足すこと。

## 確かめたこと

- `tests/test_headless_audit.py` の55件がすべて通る。`.claude/skills/` の3ファイルは、実装の段のサブエージェントが書けないので（フックが止める）、実装の段が渡した文をメインが入れた。
- `pytest -q` 全体：落ちるのは別件の161件（動画のパイプのテスト。イシュー #33）だけで、この変更の前と同じ数。
- 実機の AC-08〜10（前回の検証の段）：監査・助言ともに、スキルとして開かれて報告で止まり、ファイルの変更なし。`--bare` では `slash_commands` に `pipe-audit` が無く、認証も読まれずにモデルを呼ばずに終わった。
- メインの実機の試し（追記）：`--tools` 付きの呼び方でも、監査・助言ともに開かれ、報告で止まり、ファイルの変更なし（約 1.14 ドル・1.22 ドル）。init の tools に Bash・Write・Edit が無い。この環境に入っていたプラグインの MCP の道具は残っていた（`dontAsk` で許可に無いので断られる側）。それまでの試しと合わせた利用料は約 3.7 ドル（すべて上限 5 ドル/回の中）。
- 2回目の検証（新しい呼び方の文字列そのまま。`--model sonnet` を足した）：監査は組み込みの道具が Task・Glob・Grep・Read だけで、`pipe-in-auditor` を1回呼んで報告で止まった（約 0.27 ドル）。助言は Task・Glob・Grep・Read・WebFetch・WebSearch だけで、`pipe-in-advisor` を1回、WebFetch 9回はすべて https://code.claude.com/docs/en/… で、報告で止まった（約 0.54 ドル）。どちらも作業フォルダのファイルは前後で同じ。この機能の実機の利用料は合わせて約 4.5 ドル（どれも1回 5 ドルの上限の中）。
- 2回目の検証で流した監査・助言の報告（この記録についてのもの）のうち、A-01〜03（「確かめたこと」の言い回し・AC-04 の文）・V-03（`--permission-prompts` の版）・V-05（`--restricted` を選ばない理由）を直した。V-01・V-04 は上の残った課題（#34・#35）に回した。
