# Claude Code のプラグイン

[ガイドの目次](README.md) · [README](../../README.md) — どのプロジェクトでも会話で[パイプ](pipes.md)を作る・直すためのプラグインの説明です。

このリポジトリは Claude Code のプラグインのマーケットプレイスにもなっています（`.claude-plugin/marketplace.json` → `plugin/`）。
入れると、どのプロジェクトでも会話でパイプを作る・直すことができます。`pipe-in-gen` が使えること（`pip install -e .`）が前提です。PATH に `pipe-in-gen` が無いと、作る役 pipe-builder の絞りが効きません（くわしくは[安全のしくみ](safety.md#プラグインのフックが動かないとき)）。

会話の中なら 1 行で入ります（Claude Code v2.1.275 以降。公式の文書による。実機は未確認）。新しいマーケットプレイスの確認と、入れる範囲（scope）の選択が出ます。シェルでは `claude plugin install pipe-in --marketplace nigoh/pipe-in`（v2.1.292 以降）です。それより前の版のシェルでは、`claude plugin marketplace add nigoh/pipe-in` のあと `claude plugin install pipe-in@pipe-in` です。

```
/plugin install pipe-in --marketplace nigoh/pipe-in
```

claude.ai のチャットでは、スキルは読み込まれますが、エージェントとフックは無視されます。どのスキルも手元のコマンド（`pipe-in-gen` か `pipe-in`。`/pipe-in:pipe-eval` はどちらも使わない）に頼るので、ちゃんと使えるのは、それを入れた Claude Code です（[プラグインの README](../../plugin/README.md) の「使える場所」）。

前からの2段の形も使えます。手元のフォルダから入れるときも、こちらです。

```
/plugin marketplace add <pipe-in のリポジトリのフォルダか GitHub の nigoh/pipe-in>
/plugin install pipe-in@pipe-in
```

プラグインのフォルダには `README.md`（英語と日本語。入れ方・入るもの・動かすもの・送るもの・取ってくるもの・使える場所）と `LICENSE`（根の `LICENSE` と同じ中身）とアイコンも入っていて、入れた人がフォルダの中だけで読めます。

| 入るもの | すること |
| --- | --- |
| スキル `/pipe-in:pipe-build` | 目的か直したい点を聞き、段の表（直すときは「前 → 後」の表）を見せて確認を取り、pipe-builder に任せ、`pipe-in-gen check` の結果と流し方を伝える。段の決め方と、検査（`command`）と審査（`judge`）の組み方と、比較実験から分かった組み方の目安は `references/stage-rules.md` にある。流すのは言われてから |
| エージェント `pipe-builder` | 渡された `stage-rules.md` を読み、確認が取れた表どおりに `pipe.toml`・`prompts/`・`README.md` を書き、`pipe-in-gen check` が通るまで直す。表に無い権限の拡大や、`judge` だけで差し戻す形（`command` が無いのに `on_fail`）はせず差し戻す |
| スキル `/pipe-in:pipe-eval` | パイプの成果物を、検査のコマンド（`pipe.toml` の `[stages.check]` の `command`、または渡したコマンド）で確かめる。流す前に一覧を見せて返事を待ち、項目ごとの合否（終了コード 0 だけが合格）を JSON で返す。成果物は書かない・直さない |
| スキル `/pipe-in:pipe-judge` | 成果物を、依頼とルーブリックに照らして審査する。点は審査役 `pipe-judge` が付け、総合点・合否・ばらつきは `pipe-in-gen judge-score` が計算する。結果は JSON で返し、成果物は直さない・パイプへ差し戻さない |
| スキル `/pipe-in:pipe-live` | ターミナルで流している pipe-in の進み具合を、Claude のアーティファクトでも見る。ページを1回だけ公開し、Monitor で `pipe-in live watch` を動かして、行を受けるたびに ArtifactData へ写しを書く。見るだけで、止める・進める・承認はできない。使えるのは claude.ai にログインした Claude Code で、Artifact・ArtifactData・Monitor が要る（無ければ何もせず止まる）。人が呼んだときだけ動く。使い方は[使い方](usage.md#ターミナルで流している実行を見るpipe-in-live-watch) |
| エージェント `pipe-judge` | 項目ごとに、先に理由、次に 5 段階の点（0.0・0.25・0.5・0.75・1.0。採点できなければ null）を返す審査役。must は違反の有無と根拠。読む道具（Read・Grep・Glob）だけを持つ |
| スキル `/pipe-in:pipe-run` | 会話の中でパイプを流す（SDK を起こせない場所向け。[下の節](#pipe-inpipe-run)）。段の順番・検査・差し戻し・人の確認・記録は `pipe-in-gen chat` が持ち、会話は返事の `action` に従って、指示を `pipe-stage` に渡し、結果を返すだけ。人が呼んだときだけ動く。段は Claude の利用料がかかる |
| エージェント `pipe-stage` | `pipe-run` から呼ばれ、渡された指示で 1 つの段を受け持って成果物を書く。道具は読む・書く・Bash で、サブエージェントは呼べない。書ける範囲は段の定義から決まり、フックが絞る |
| エージェント `pipe-probe` | `pipe-run` が流す前に 1 回だけ呼ぶ確かめ役。渡された範囲外のパスへ `Write` を 1 回だけ試し、守りが効いているかを見る。道具は Write・Read だけ |
| フック（`pipe-in-gen guard-hook`） | pipe-builder が書けるのを、パイプのフォルダ（`…/pipes/pipe-in-<名前>/`。前の版のフォルダ名も）の `pipe.toml`・`README.md`・`prompts/*.md` だけに、Bash を `pipe-in-gen list / new / check` だけに絞る。pipe-judge は読む道具（Read・Glob・Grep）だけに絞り、Bash・Agent なども止める。どちらの場合も PowerShell・MCP・Web の呼び出しは止める。pipe-builder は渡された `stage-rules.md` を読むだけ（読む道具は止めない）。会話の中で流すときは、`pipe-stage` を今開いている段の範囲に絞り（段が開いていなければ止める）、`pipe-probe` を段の有無によらずいつも読む道具だけに絞り、段が開いている間、または記録が読めないときは、ほかのエージェントは止める（[安全のしくみ](safety.md#会話の中で流すときの守り)）。会話の中で段が開いておらず、記録も読めるときは、これらのエージェント以外には何もしない。ただし `agent_type` が文字列でも null でもない呼び出しは、読む道具以外を止める |

書き込み先は、パスの文字の上の判断に加えて、リンク（シンボリックリンク・junction）の先をたどった判断でも書ける場所に入るときだけ通します。置き場所の外を指すリンクに加えて、置き場所の中でも書いてよいファイル（`pipe.toml`・`README.md`・`prompts/*.md`）以外を指すリンクも止めます。壊れたリンク・輪のリンク・たどれないものも止めます。

フックは `pipe-in-gen` で動くので、`pipe-in-gen` が無い環境では効きません（スキルは、はじめに `pipe-in-gen` を確かめて、無ければ止まります。`/pipe-in:pipe-eval` は `pipe-in-gen` を使いません）。
フックは、入力が読めない（壊れている・16 MiB を超える）ときと、`agent_type` が文字列でも null でもないときは、読む道具以外を止めます。止める返事を書き出せないときは、標準エラーに理由を書いて終了コード 2 で止めます（[安全のしくみ](safety.md#フックの入力が読めないとき)）。
フックが起動できない（`pipe-in-gen` が PATH に無い・壊れている・時間切れ・0 と 2 以外の終了コードで終わった）とき、Claude Code は操作を止めずに進めます。そのあいだ pipe-builder の書き込みは絞られず、審査役 pipe-judge はエージェントの `tools:`（Read・Grep・Glob）だけで絞られます。`/pipe-in:pipe-run` の段（pipe-stage）も同じで、フックが動かないあいだは絞られません。ただし `/pipe-in:pipe-run` は流す前に毎回、守りが効くかを確かめ（`chat probe`）、フックが動いていなければ確かめが通らないので、段を流しません。プラグインを入れたら、先に `pipe-in-gen --help` が動くことを確かめてください。

このフックには、失敗を止める側に倒す設定 `onFailure: "block"`（公式の文書によると Claude Code v2.1.295 以降）を付けていません。付けると、フックが動かないとき、全部の道具の呼び出しが止まります。`pipe-in-gen` を入れていない・PATH が通っていない人は、プラグインを有効にしただけで、メインの会話の Read や Bash も止まります。失敗のときの動きは、全部止めるか全部通すかの二択で、エージェントの種類では絞れません（絞れるのは道具の名前と引数だけで、このフックは `agent_type` で相手を見分けます）。そのため、フックが動かないと `pipe-builder`・`pipe-judge` の絞りは効きません。`/pipe-in:pipe-run` には流す前の確かめ（`pipe-probe`）がありますが、`pipe-builder`・`pipe-judge` には流す前の確かめがありません。公式の文書によると、フックが失敗すると会話に `hook error` の知らせが出ます（実機では確かめていません）。出たら `pipe-in-gen --help` が動くかを確かめてください。実機では確かめていないことがあります。理由と経緯は[決定の記録 D0089](../decisions/D0089-hook-failure.md)です。

## 検査と審査

どちらも、人が呼んだときだけ動きます。合否を決めるのは検査（`/pipe-in:pipe-eval`）で、審査（`/pipe-in:pipe-judge`）の合否は人が読む材料です。審査で `fail` でも、成果物は直さず、パイプへも差し戻しません。なお、パイプを流すあいだに段の出来を審査して差し戻したいときは、パイプの定義に `[stages.check.judge]` を書きます（[パイプ](pipes.md#ルーブリックで審査するstagescheckjudge)）。こちらは合否を pipe-in が計算し、不合格なら `on_fail` の段（省くと自分）へ戻します。

### `/pipe-in:pipe-eval <パイプの名前> [コマンド ...]`

1. 記録（`state.json`）を探します。無ければ、検査せずに止まります。
2. 検査の項目を決めます。コマンドを渡したらそれが先で、なければ `pipe.toml` の `[stages.check]` の `command`。どちらも無ければ 0 件で、`fail` です（0 件を合格にしません）。
3. 段の名前・コマンド・作業フォルダ・`timeout_sec` の一覧を見せ、返事を待ってから流します。
4. 項目ごとに `name`・`command`・`exit_code`・`passed`・`output_tail` と、全体の `verdict` を JSON で返します。時間切れや流せなかった項目は不合格です。

Claude を呼ぶパイプは流さないので、pipe-in の利用料はかかりません。

### `/pipe-in:pipe-judge <成果物> [--request <依頼のファイル> | --text "依頼"] [--rubric <ルーブリックのファイル>] [--runs N]`

- ルーブリックは Markdown の表のファイル（列は `項目名 | 見ること | must か`）で渡します。`must` の行は破ってはいけない決まりで、1 つでも破ると平均に関わらず `fail` です。渡さなければ、既定（採点 5 つ・must 2 つ）を使います。
- 総合点は採点項目の点の平均（null は数えない）で、0.7 以上が `pass` です。must が確かめられなかったときも `fail` で、`must_unchecked` に載ります。計算は `pipe-in-gen judge-score` が決まった手順でします。
- `--runs N`（1〜5、既定 1）で審査役を N 回呼び、平均とばらつき（`variance` の `verdict_disagreement`・`overall_range`）を出します。審査役を呼ぶたびに Claude の利用料がかかるので、2 以上では呼ぶ前に「約 N 倍」と見せて返事を待ちます。範囲の外は断ります。
- 返す JSON のキーは `runs`・`scores`・`must_violations`・`must_unchecked`・`overall`・`threshold`・`verdict`（と、2 回以上なら `variance`）です。結果はファイルに残しません。
- 審査役は読む道具しか持たず、成果物の中の指示には従いません。ただし Read で成果物以外のファイルも読めます（書けず、外へも出せません）。

## `/pipe-in:pipe-live [--work-dir 記録のフォルダ]`

ターミナルで流している `pipe-in` の進み具合を、会話の横のアーティファクトでも見ます。人が呼んだときだけ動き、見るだけです（実行を止めたり進めたり、承認したりはできません）。

- はじめに、Artifact・ArtifactData・Monitor が会話にあるかを確かめます。claude.ai にログインした Claude Code で使えます（API キー・Bedrock・Vertex・Foundry では使えず、`-p`・Agent SDK などでは既定で切れています）。無ければ何もせず止まります。
- ページは `pipe-in live page` で作って1回だけ公開し、Monitor で `pipe-in live watch` を動かします。行を受けるたびに、その写しを ArtifactData の `runs/current` に書きます。
- `final` の行で終わります。Monitor は1回の見張りが最長30分なので、`--timeout 1750` で見張り、`timeout` の行（または Monitor の期限）で止まったときは、実行が続いていれば起こし直します。行の形と終了コードは[使い方](usage.md#ターミナルで流している実行を見るpipe-in-live-watch)。
- 書くのは一時フォルダのファイルと ArtifactData だけです。利用料はかかりません。

## `/pipe-in:pipe-run`

使い方は `/pipe-in:pipe-run <パイプ名> [要件メモ]` です。作ったパイプを、会話の中で流します。端末の `pipe-in --pipe` と同じ段・同じ記録の場所（`docs/pipeline/<パイプ名>/`）を使うので、VSCode の拡張で図が見られます。人が呼んだときだけ動きます。段は Claude の利用料がかかります。

- 対象は、SDK を起こせない場所（VS Code の Claude など）です。端末で `pipe-in` を使えるなら、そちらを使ってください。
- 段の順番・次の段・やり直し・人の確認・記録は、`pipe-in-gen chat` が持ちます。会話は、返事の `action` に従って、指示を `pipe-stage` に渡し、結果を `chat done` に返し、人の確認を聞いて `chat review` に渡すだけです。
- 流れは、(1) `chat start --dry-run` で段の表と「効かない設定」を見せて、開始の確認を取る、(2) `chat start` で記録を作り、`chat probe` と `pipe-probe` で守りを確かめる（確かめられなければ流さない。[安全のしくみ](safety.md#会話の中で流すときの守り)）、(3) `chat next` の `action`（`run_stage`・`await_review`・`probe`・`finished`）に従って繰り返す、(4) 結果と `99_summary.md` を伝えて終わる、です。
- 扱えない形と効かない設定は、[パイプ](pipes.md#会話の中で流すとき)の表にあります。扱えない形のパイプは、始める前に理由を全部出して断ります。
- 記録は `driver: "pipe-chat"` で書かれます。使用量は取れないので、記録は「取れない」と書かれます。くわしくは[記録と使用量](records.md#会話の中で流した記録)。
- `pipe-in --review` では続けられません。続きは `pipe-in-gen chat next --pipe <パイプ名>` です。会話が途切れても、`chat status` で今どこかを見て、`chat next` から続けられます（開いている段は、同じ指示がもう一度出ます）。

### `pipe-in-gen chat`

`/pipe-in:pipe-run` の会話が呼ぶコマンドです。人が端末で打つものではありません（出力は 1 つの JSON で、終了コードは成功が 0、断り・誤りが 1）。

| コマンド | すること |
| --- | --- |
| `chat start <パイプ> [--memo T｜--memo-file F] [--name N] [--session-id S] [--dry-run]` | 記録を作って始める。`--dry-run` なら何も書かず、段の表と効かない設定を返す。途中の記録があれば断り、終わった記録は `archive/` へ移す。`--after` は会話の中では使えず、断る |
| `chat probe --pipe P` | 守りの確かめ。1 回目は確かめ役への指示（乱数入りの範囲外のパス）を出し、確かめ役を呼んだあとの 2 回目で、結果を読んで `probe_ok` か `probe_failed` を返す |
| `chat next --pipe P` | 次にすることを返す（`run_stage`・`await_review`・`probe`・`finished`）。開いている段で呼び直すと、同じ指示がもう一度出る |
| `chat done --pipe P --stage S [--summary T] [--status pass｜fail] [--problems P] [--error]` | 段を閉じる。成果物と検査を調べて、次の段・やり直し・終わりを決める。`--status`・`--problems` は、判定（`verdict`）のある段だけ |
| `chat review --pipe P approved｜revise｜quit [--feedback T]` | 人の確認の答えを記録する。`revise` には直してほしい点（`--feedback`）が要る |
| `chat status --pipe P` | 今どこかを返す（読むだけ） |

### 使える場所と使えない場所

- **VS Code の Claude 拡張（Claude のハーネス）**：使える見込みです。ただし**実機ではまだ確かめていません**（#123 で確かめます）。フックが `agent_type` を受け取り、`pipe-stage` の道具の呼び出しを止められることが前提で、確かめられなければ `chat probe` が `probe_failed` を返し、流れません。
- **Copilot 本来の側（Local ハーネス）**：フックの入力に `agent_type` が来ないため、守りの確かめで止まり、流れません。
- **会社などの管理設定**：管理設定で Claude のハーネス自体が使えない環境では、使えません。
- **端末の Claude Code**：同じ手順で使える見込みですが、実機の確かめはこれからです。`pipe-in` を直接使えるので、通常は要りません。
- **claude.ai のチャット**：エージェントとフックが無視されるので、`pipe-stage` も守りも動かず、流れません。
- **メインのスレッドを `--agent` で動かしているとき**：段が開いている間、道具の呼び出しはすべて止まります（フックが `agent_type` のある呼び出しを全部絞るため）。使わないでください。

## プラグインの eval

プラグイン自身のスキルが、狙いどおりに動くかを確かめるケースを、`plugin/evals/` に置いてあります。Claude Code の `claude plugin eval` で流します。ケースは小さなテキストのファイルで、`pipe-build`・`pipe-eval`・`pipe-judge` のスキルごとに 3 本、全部で 9 本です。

| ケース | スキル | 測ること | tags |
| --- | --- | --- | --- |
| `build-shows-table-first` | pipe-build | 書く前に段の表を見せて確認を待つ（書かない・流さない・任せない） | cheap・needs-bash・needs-pipe-in-gen |
| `build-passes-check` | pipe-build | 確認済みの表を pipe-builder に任せ、`pipe.toml`・`README.md` を書き、`pipe-in-gen check` で検査する | agent・needs-bash・needs-write・needs-pipe-in-gen |
| `build-refuses-judge-only` | pipe-build | 審査（judge）だけで自分に戻す検査を作らず、`command` と組む案内を返す | agent・needs-bash・needs-write・needs-pipe-in-gen |
| `eval-lists-and-waits` | pipe-eval | 流す前に一覧を見せ、返事を待つ | cheap |
| `eval-result-json` | pipe-eval | 流してよいと言われたら 2 つ流し、結果を JSON で返す | cheap・needs-bash |
| `eval-stops-without-state` | pipe-eval | 記録（`state.json`）が無ければ流さずに、先にパイプを流すよう伝える | cheap |
| `judge-calls-judge-score` | pipe-judge | 審査役を呼び、点の計算を `pipe-in-gen judge-score` にさせる | agent・needs-bash・needs-pipe-in-gen |
| `judge-must-violation-fails` | pipe-judge | must に違反した報告を `fail` にし、根拠に違反の引用を書く | agent・needs-bash・needs-pipe-in-gen |
| `judge-rejects-bad-runs` | pipe-judge | 範囲外の `--runs` を、審査役にも計算にも回さずに断る | cheap・needs-pipe-in-gen |

各ケースの本文は `/pipe-in:<スキル名>` で始まります。見本のファイル（対象プロジェクトや記録）は、`scaffold.sh` が Claude の始まる前に空のワークスペースへその場で作ります（中から標準ライブラリだけの `scaffold.py` を呼びます）。`pipe-in-gen` が無い、または作業フォルダが空でないときは、何も書かずに止まります。採点（`graders/`）は、書かない・呼ばないといった道具の使い方と、返事の語を見るものがほとんどで、Claude に採点させる `llm` は 1 ケースだけです。

### 流し方

`claude plugin eval` は Claude を呼ぶので、**利用料がかかります。人に言われたときだけ流してください**（CI には入れません）。

```
claude plugin eval ./plugin --scaffold --trust-plugin --allow-tools Bash Write Edit \
  --model sonnet --judge-model haiku --threshold 0.8 --runs 3 --ablation none \
  --output-dir <plugin/ の外のフォルダ> --no-publish
```

- `--scaffold` が無いと見本が作られず、全ケースが空のワークスペースで動いて落ちます。必ず付けます。
- `--ablation none` で、プラグインを入れた回だけを流します。付けないと、プラグイン無しで比べる回も同じ数だけ流れて、費用が倍になります。ケースは `/pipe-in:<スキル>` を呼ぶので、プラグイン無しの回と比べる意味はほとんどありません。
- `--allow-tools Bash Write Edit` は全ケースに効きます。ケースの `allowed_tools` では `Bash`・`Write`・`Edit` を許せないので、ケース側は `tags` の `needs-bash`・`needs-write` で、何が要るかを示します。
- `--case <ケース名>` で 1 本だけ、`--tag cheap` で審査役やサブエージェントを呼ばない安いケースだけ、`--tag agent` で高いケースだけ、`--tag needs-pipe-in-gen` で Claude が `pipe-in-gen` を使うケースだけを流せます。ただし見本を作る `scaffold.sh` は、9 本とも `pipe-in-gen` が PATH に無いと止まるので、どのタグで流すときも `pipe-in-gen` を入れておきます。
- `--output-dir` は `plugin/` の外に向けます。既定の結果の置き場所はプラグインのフォルダの中で、`plugin/evals/results/` は `.gitignore` に入れてあります。
- `--max-cost-usd` で費用の上限を付けます。値は、実機で 1 ケースの費用を測ってから決めます（まだ測っていません）。
- `--trust-plugin` を付けるので、信頼できるプラグインだけに使います。プラグインのフックは、サンドボックスの外で動きます。

### 前提と注意

- Claude Code v2.1.269 以上、git 2.31 以上、Bash が要ります。Windows では WSL2 の中で流します（Windows そのままでは、Bash を許すケースはサンドボックスが無いので、1 回ずつ断られます）。Linux は bubblewrap と socat も要ります。
- `eval-*` の 3 本は、流すコマンドに `python` を使います。`python` が無く `python3` だけの環境では落ちます。
- `Bash` を許すと、OS のサンドボックスの中で動きます。サンドボックスの Bash は home の下を読めないので、home の下の venv に入れた `pipe-in-gen` は使えないおそれがあります。`pipe-in-gen` は home の外に入れるか、実機で確かめてください（`pip install -e .` で入ります）。
- 結果は、`--output-dir` の先の `aggregate-result.json` と `report.html` に出ます。
- `claude -p` で `/スキル名` が展開されることは公式の文書にありますが、`claude plugin eval` の中で `/pipe-in:<スキル>` の形が展開されるかは、まだ実機で確かめていません。`file_exists` の `path` の基準と、サブエージェントが書いたファイルや呼んだ道具が採点に数えられるかも、まだです。`scaffold.sh` には実行ビットを付けてあります。
- ケースを足すだけなら、プラグインの版は上げません（ケースは 0.5.0 のときに足しました。利用者に届けたい変更を入れるときの版の決まりは[下の節](#ディレクトリへの申請)）。スキル・エージェント・フックの動きは変わりません。`pytest` が見るのはケースのファイルの形だけで、`claude plugin eval` は流しません。

## ディレクトリへの申請

Anthropic のディレクトリ（claude.ai/directory）にこのプラグインを載せるための、人の手順と、事前チェックへの備えです。決まりは 2026-11-12 に公式の文書で確かめました（出典：https://claude.com/docs/plugins/submit 、https://claude.com/docs/plugins/pre-submission-checklist 、https://code.claude.com/docs/en/plugins/publish.md ）。文書が変わったら、ここと `tests/test_plugin_directory.py` の先頭の決まりの定数を直します。申請そのもの（ポータルの操作）は人がします。決めたことは[決定の記録 D0095](../decisions/D0095-plugin-directory-precheck.md)です。

前もって要るもの：有料の claude.ai のプラン（Pro・Max・Ultra は自分のアカウント、Team・Enterprise は Owner）、claude.ai につないだ GitHub（そのアカウントがこのリポジトリに push できること）、public のリポジトリ。1つのリポジトリとフォルダに申請は1つです。

### ポータルでの順番

ポータルは https://claude.ai/directory/manage です。

1. Submit new を押し、Plugin bundle を選ぶ。
2. Source：Repository に `nigoh/pipe-in`、Plugin path に `plugin` を入れる。Branch or tag は空で、既定の枝になる。
3. Validate を押す。Blocks が出たら直して push し、Re-validate を押す。ローカルの `claude plugin validate` が通っても、ポータルの Validate はもっと多くを見る。
4. Listing details：`plugin.json` と README から読み込まれる。変えたいときはリポジトリを直して Validate し直す。
5. Data handling：4つの問いに答える（下の下書き）。
6. Compliance：連絡先のメールを入れ、4つの同意を選ぶ。人が選ぶ。
7. Review and submit：新しい版の届き方を選ぶ。GitHub の push の webhook（既定・推し。リポジトリの admin が要る）か、決まった間隔の確認だけ（Scheduled check only）。Auto-publish の切り替えもここ。
8. Submit for review を押す。

申請したあとは、追う枝に入れると、検査を通った版が公開の設定どおりに出ます。

### データの扱いの問いへの答えの下書き

スキル・エージェント・フックを読んで確かめた事実からの下書きです。最後に答えるのは人です。

1. 個人のデータを読む・残すか：利用者が頼んだ作業のために、利用者のプロジェクトの中のファイル（パイプの定義・記録）を読み書きする。作者には集めない。残る記録は利用者のプロジェクトの中だけ。
2. 宣言したコネクタ以外のサービスへデータを送るか：プラグイン自身は送らない。作者や第三者のサーバーへ送るものは無く、`WebFetch`・`WebSearch` も使わない。ただし、`/pipe-in:pipe-eval` が流す検査のコマンドと、段（`pipe-stage`）の中のシェルのコマンドは、利用者のパイプの定義のとおりに動くので、何を送るかはその定義による。例外は `/pipe-in:pipe-live` で、人が呼んだときだけ、進み具合の写しを claude.ai のアーティファクトのデータ（`ArtifactData`）に書く。
3. データをどのくらい残すか：プラグインは自分ではデータを持たない。記録は利用者のプロジェクトの `docs/pipeline/` などに、利用者が消すまで残る。アーティファクトのデータの扱いは claude.ai の決まり。
4. 18 歳未満向けか：いいえ。開発者向けの道具。

### 版を上げる決まり

リリースのたびに、`plugin/.claude-plugin/plugin.json` の `version` を上げます。上げないと、申請したあとの利用者に新しい版が届きません。版を書くのは `plugin.json` だけで、`.claude-plugin/marketplace.json` の項目には `version` を書きません（二重にしないため）。`pyproject.toml` の版（`pipe-in-gen` の版）は別物で、ここでは上げません。0.6.0 で README・アイコン・マニフェストの項目を足しました。スキル・エージェント・フックの動きは変わっていません。

### 申請の前の確かめ

手で流します（CI では流しません。Claude Code を CI に入れると依存が増え、版も動くため）。どちらも終了コード 0 で、`ICON_MISSING` と README の警告が出ないことを見ます。

```
claude plugin validate --strict ./plugin
```

```
claude plugin validate --strict .
```

`plugin.json` の `icon`・`documentationUrl`・`supportUrl` は、ディレクトリの掲載ページが読む欄です。公式の文書によると、`claude plugin validate` がこれらを知らない欄として警告しないのは v2.1.281 以降なので、`--strict` はそれ以降の Claude Code で流します。これらの欄は `plugin.json` にだけ書き、`marketplace.json` の項目には書きません（書くと知らない欄の警告になる）。

ローカルの validate は、ポータルの Validate と同じ検査ではありません。フックの `"command": "pipe-in-gen"`（PATH のコマンド名）が、ポータルの Validate で止められるかは、まだ確かめていません。止められたら、別の機能で見直します。

### アイコン

`plugin/.claude-plugin/icon.png`（1024×1024・約 26 KB）です。元は `docs/assets/pipe-in-logo-dark.svg` で、地の色は `#0D1117` です（作り方は[docs/assets/README.md](../assets/README.md#プラグインのアイコンを撮る)）。`plugin.json` の `icon`（`./.claude-plugin/icon.png`）がこのファイルを指します。公式の文書によると、ディレクトリは `plugin.json` の `icon` を読みます。ポータルで使われるのは、最初の保存・申請の1回だけで、あとから変えても変わりません。

### 事前チェックを pytest で見張る範囲

`tests/test_plugin_directory.py` が見るのは、README の語数・見出し・入れ方・名前と実物の合い（動かすもの・送るものの語を含む）、アイコンの形、`plugin.json` と `marketplace.json` の項目と版、フォルダの大きさと数、シンボリックリンクと不要なファイル、ファイル名、`LICENSE`、`.gitattributes`、フックの形、前書きの `description`、この節の中身です。見ないのは、セキュリティの検査、名前がほかに取られていないか、方針の審査です。これらはポータルと人の審査が決めます。

## 0.5.x から更新するとき

0.6.0 では README・アイコン・`LICENSE`・マニフェストの項目が増えただけで、スキル・エージェント・フックの動きは変わっていません。更新のしかたは下と同じです。

0.5.1 で `references/stage-rules.md` に「比較実験から分かった組み方の目安」が増え、0.5.2 でその中に「2体の共通部分」の項（`pipe-in-gen quorum`・ひな形 `review-quorum`）が増えました。スキル・エージェント・フックの動きは変わりません。入れ方によって、更新のしかたが違います。

- **手元のフォルダからマーケットプレイスを足した人**（`/plugin marketplace add ./`）：プラグインはその場から読まれるので、pipe-in のフォルダで `git pull` をしたあと、次の会話を始めるか `/reload-plugins` をすれば効きます。
- **GitHub からマーケットプレイスを足した人**：版が変わったときだけ入れ直されます。会話の中なら `/plugin marketplace update pipe-in`、シェルなら `claude plugin update pipe-in@pipe-in` で更新し、開いている会話には `/reload-plugins` で反映します。`/plugin` の Marketplaces で自動の更新（Enable auto-update）を入れておくと、自分で更新しなくても届きます。Anthropic の公式のマーケットプレイスのほかは、自動の更新は既定で切れています。
- **1 行の形（`--marketplace nigoh/pipe-in`）で入れた人**：1 行の形も、GitHub のマーケットプレイスを足してから入れるので、GitHub からマーケットプレイスを足した人と同じです。

あわせて、警告 W7・W6・W5 の例外・`pipe-in-gen quorum`・ひな形 `review-quorum` を使うには、pipe-in のフォルダで `git pull` して `pip install -e .` をやり直します（`pipe-in-gen` は本体にあります）。

## 0.4.0 以前から更新するとき

0.5.0 で `/pipe-in:pipe-build` が `references/stage-rules.md`（段の決め方と、検査と審査の組み方）を持ち、`command` と `judge` を組んだ段を作れるようになりました。0.4.0 以前を入れていた人は、`/plugin` で更新して入れ直してください（開いている会話に反映するには `/reload-plugins`）。0.4.0 までの版はこれまでどおり動きます。新しい SKILL.md は `references/` のファイルが無いと半端になるので、プラグインは丸ごと更新します。

## 0.3.0 以前から更新するとき

0.4.0 でスキル `/pipe-in:pipe-live` が増えました。0.3.0 以前を入れていた人は、`/plugin` で更新して入れ直してください（開いている会話に反映するには `/reload-plugins`）。`pipe-in live watch` は本体にあるので、pipe-in のフォルダで `git pull` して `pip install -e .` をやり直します。

## 0.2.0 から更新するとき

0.2.0 を入れていた人は、`/plugin` で更新して入れ直してください（スキル・エージェントが増えます）。`pipe-in-gen` も新しくします（pipe-in のフォルダで `git pull` して `pip install -e .` をやり直す）。古い `pipe-in-gen` には `judge-score` が無く、審査役を絞るフックも古いままです。`/pipe-in:pipe-judge` は、はじめに `pipe-in-gen --help` に `judge-score` があるかを見て、無ければ止まります。
