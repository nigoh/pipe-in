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

## 0.4.0 以前から更新するとき

0.5.0 で `/pipe-in:pipe-build` が `references/stage-rules.md`（段の決め方と、検査と審査の組み方）を持ち、`command` と `judge` を組んだ段を作れるようになりました。0.4.0 以前を入れていた人は、`/plugin` で更新して入れ直してください（開いている会話に反映するには `/reload-plugins`）。0.4.0 までの版はこれまでどおり動きます。新しい SKILL.md は `references/` のファイルが無いと半端になるので、プラグインは丸ごと更新します。

## 0.3.0 以前から更新するとき

0.4.0 でスキル `/pipe-in:pipe-live` が増えました。0.3.0 以前を入れていた人は、`/plugin` で更新して入れ直してください（開いている会話に反映するには `/reload-plugins`）。`pipe-in live watch` は本体にあるので、pipe-in のフォルダで `git pull` して `pip install -e .` をやり直します。

## 0.2.0 から更新するとき

0.2.0 を入れていた人は、`/plugin` で更新して入れ直してください（スキル・エージェントが増えます）。`pipe-in-gen` も新しくします（pipe-in のフォルダで `git pull` して `pip install -e .` をやり直す）。古い `pipe-in-gen` には `judge-score` が無く、審査役を絞るフックも古いままです。`/pipe-in:pipe-judge` は、はじめに `pipe-in-gen --help` に `judge-score` があるかを見て、無ければ止まります。
