# Claude Code のプラグイン

[ガイドの目次](README.md) · [README](../../README.md) — どのプロジェクトでも会話で[パイプ](pipes.md)を作る・直すためのプラグインの説明です。

このリポジトリは Claude Code のプラグインのマーケットプレイスにもなっています（`.claude-plugin/marketplace.json` → `plugin/`）。
入れると、どのプロジェクトでも会話でパイプを作る・直すことができます。`pipe-in-gen` が使えること（`pip install -e .`）が前提です。

```
/plugin marketplace add <pipe-in のリポジトリのフォルダか GitHub の nigoh/pipe-in>
/plugin install pipe-in@pipe-in
```

| 入るもの | すること |
| --- | --- |
| スキル `/pipe-in:pipe-build` | 目的か直したい点を聞き、段の表（直すときは「前 → 後」の表）を見せて確認を取り、pipe-builder に任せ、`pipe-in-gen check` の結果と流し方を伝える。段の決め方と、検査（`command`）と審査（`judge`）の組み方は `references/stage-rules.md` にある。流すのは言われてから |
| エージェント `pipe-builder` | 渡された `stage-rules.md` を読み、確認が取れた表どおりに `pipe.toml`・`prompts/`・`README.md` を書き、`pipe-in-gen check` が通るまで直す。表に無い権限の拡大や、`judge` だけで差し戻す形（`command` が無いのに `on_fail`）はせず差し戻す |
| スキル `/pipe-in:pipe-eval` | パイプの成果物を、検査のコマンド（`pipe.toml` の `[stages.check]` の `command`、または渡したコマンド）で確かめる。流す前に一覧を見せて返事を待ち、項目ごとの合否（終了コード 0 だけが合格）を JSON で返す。成果物は書かない・直さない |
| スキル `/pipe-in:pipe-judge` | 成果物を、依頼とルーブリックに照らして審査する。点は審査役 `pipe-judge` が付け、総合点・合否・ばらつきは `pipe-in-gen judge-score` が計算する。結果は JSON で返し、成果物は直さない・パイプへ差し戻さない |
| スキル `/pipe-in:pipe-live` | ターミナルで流している pipe-in の進み具合を、Claude のアーティファクトでも見る。ページを1回だけ公開し、Monitor で `pipe-in live watch` を動かして、行を受けるたびに ArtifactData へ写しを書く。見るだけで、止める・進める・承認はできない。使えるのは claude.ai にログインした Claude Code で、Artifact・ArtifactData・Monitor が要る（無ければ何もせず止まる）。人が呼んだときだけ動く。使い方は[使い方](usage.md#ターミナルで流している実行を見るpipe-in-live-watch) |
| エージェント `pipe-judge` | 項目ごとに、先に理由、次に 5 段階の点（0.0・0.25・0.5・0.75・1.0。採点できなければ null）を返す審査役。must は違反の有無と根拠。読む道具（Read・Grep・Glob）だけを持つ |
| フック（`pipe-in-gen guard-hook`） | pipe-builder が書けるのを、パイプのフォルダ（`…/pipes/pipe-in-<名前>/`。前の版のフォルダ名も）の `pipe.toml`・`README.md`・`prompts/*.md` だけに、Bash を `pipe-in-gen list / new / check` だけに絞る。pipe-judge は読む道具（Read・Glob・Grep）だけに絞り、Bash・Agent なども止める。どちらの場合も PowerShell・MCP・Web の呼び出しは止める。ほかのエージェントには何もしない。pipe-builder は渡された `stage-rules.md` を読むだけ（読む道具は止めない） |

フックは `pipe-in-gen` で動くので、`pipe-in-gen` が無い環境では効きません（スキルは、はじめに `pipe-in-gen` を確かめて、無ければ止まります。`/pipe-in:pipe-eval` は `pipe-in-gen` を使いません）。
フックが起動できない（`pipe-in-gen` が PATH に無い・壊れている・時間切れ）とき、Claude Code は操作を止めずに進めます。そのあいだ pipe-builder の書き込みは絞られず、審査役 pipe-judge はエージェントの `tools:`（Read・Grep・Glob）だけで絞られます。プラグインを入れたら、先に `pipe-in-gen --help` が動くことを確かめてください。

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
- ケースを足しても、プラグインの版は 0.5.0 のままで、スキル・エージェント・フックの動きは変わりません。`pytest` が見るのはケースのファイルの形だけで、`claude plugin eval` は流しません。

## 0.4.0 以前から更新するとき

0.5.0 で `/pipe-in:pipe-build` が `references/stage-rules.md`（段の決め方と、検査と審査の組み方）を持ち、`command` と `judge` を組んだ段を作れるようになりました。0.4.0 以前を入れていた人は、`/plugin` で更新して入れ直してください（開いている会話に反映するには `/reload-plugins`）。0.4.0 までの版はこれまでどおり動きます。新しい SKILL.md は `references/` のファイルが無いと半端になるので、プラグインは丸ごと更新します。

## 0.3.0 以前から更新するとき

0.4.0 でスキル `/pipe-in:pipe-live` が増えました。0.3.0 以前を入れていた人は、`/plugin` で更新して入れ直してください（開いている会話に反映するには `/reload-plugins`）。`pipe-in live watch` は本体にあるので、pipe-in のフォルダで `git pull` して `pip install -e .` をやり直します。

## 0.2.0 から更新するとき

0.2.0 を入れていた人は、`/plugin` で更新して入れ直してください（スキル・エージェントが増えます）。`pipe-in-gen` も新しくします（pipe-in のフォルダで `git pull` して `pip install -e .` をやり直す）。古い `pipe-in-gen` には `judge-score` が無く、審査役を絞るフックも古いままです。`/pipe-in:pipe-judge` は、はじめに `pipe-in-gen --help` に `judge-score` があるかを見て、無ければ止まります。
