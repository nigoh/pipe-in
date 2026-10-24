# D0035 プラグインの pipe-build と pipe-in-gen design で、検査と審査の段を組めるようにする

## 目的

パイプを作る人が、検査（`[stages.check]` の `command`）と審査（`[stages.check.judge]`、D0028）を、正しい組み方で段に入れられるようにする。合否は検査で決め、審査は中身の指摘に使い、審査で差し戻すときは必ず検査と組む（[docs/research/eval-vs-judge/](../research/eval-vs-judge/README.md) の示唆）。

## 機能要件と受け入れ基準

### プラグインの pipe-build

- FR-01 `SKILL.md` の「段の決め方」を `plugin/skills/pipe-build/references/stage-rules.md` に移し、`SKILL.md` にはリンクと読む場面だけを残す。
- FR-02 `stage-rules.md` に「検査と審査の組み方」を足す（合否は検査・審査で差し戻すなら command と組む・合否を出すなら `must`・`threshold`・`on_fail`・`max_retries`・command の引用符の注意・検査を通る `pipe.toml` の例）。
- FR-03 `SKILL.md` の「3.」で、`${CLAUDE_SKILL_DIR}/references/stage-rules.md` を pipe-builder に渡す。
- FR-04 pipe-builder は渡された `stage-rules.md` に従い、読めなければ差し戻す。
- FR-05 pipe-builder は、審査だけで差し戻す形（`judge` に `on_fail` があり `command` が無い）を書かずに差し戻す。
- FR-06 段の表の `check` の欄を、`verdict`・`command`・`judge` の別が分かる形にする。
- FR-07 プラグインの版を 0.5.0 に上げる。
- FR-08 `generator/guard_hook.py` は変えない。
- D0035-AC-01 `stage-rules.md` があり、前の「段の決め方」の中身がそこに移っている（`tests/test_plugin.py`）。
- D0035-AC-02 `stage-rules.md` に組み方の要点の語がある（同上）。
- D0035-AC-03 `stage-rules.md` の `pipe.toml` の例が、読み込みと `check_pipe` を通る（同上）。
- D0035-AC-04 `stage-rules.md` に、古い版の pipe-in では `judge` が無視されることが書かれている（同上）。
- D0035-AC-05 `SKILL.md` の「3.」が `${CLAUDE_SKILL_DIR}/references/stage-rules.md` を渡すと書き、`pipe-builder.md` が渡されたものに従い、読めなければ差し戻すと書く。`${CLAUDE_PLUGIN_ROOT}` には頼らない（同上）。
- D0035-AC-06 `pipe-builder.md` に、審査だけで差し戻す形を書かずに差し戻すことが書かれている（同上）。
- D0035-AC-07 pipe-builder の `tools`、`plugin/hooks/hooks.json`、`generator/guard_hook.py` は変わらない（同上）。
- D0035-AC-08 pipe-builder がプラグインの `references/stage-rules.md` を Read・Glob・Grep で読むのは止められない（`tests/test_guard_hook.py`）。
- D0035-AC-09 pipe-builder が `stage-rules.md` に書くこと、PowerShell・MCP・Agent・Web・`cat`・`>`・`--force`・`pipe-in-gen design` は、今までどおり止められる（同上）。
- D0035-AC-10 版が 0.5.0 で、テストと `docs/guide/plugin.md` の更新の節がそろっている（`tests/test_plugin.py`）。
- D0035-AC-11 0.4.0 までのプラグインはこれまでどおり動き、更新の節に入れ直しの案内がある（同上）。
- D0035-AC-12 これまでのひな形から作った `judge` の無い `pipe.toml` は、結果が変わらない（`tests/test_generator.py`）。
- D0035-AC-13（手で）`/pipe-in:pipe-build` で検査と審査を組むパイプを頼むと、段の表に `command` と `judge` が分かれて出て、できたパイプが検査を通る。
- D0035-AC-14（実機）プラグインを入れた Claude Code で、pipe-builder が `stage-rules.md` の中身を使えて、フックに止められない。

### pipe-in-gen design

- FR-09 設計図の形（`STAGE_SCHEMA`）の `check` に `judge` を足す（必須ではない）。
- FR-10 `render_pipe` は `judge` があれば審査の表を書き、`judge` だけの設計でも `[stages.check]` を書く（D0028 の監査 A-08）。
- FR-11 README の段の表の「検証」の欄は、`verdict`・`command`・`judge` のどれかがあれば「あり」。
- FR-12 `judge` の無い設計は、今までと同じ出力になる。
- FR-13 `design_rules.md` に組み方を短く足す。
- D0035-AC-15 `judge` だけの設計から、審査の表を持つ `pipe.toml` が書かれ、検査を通る（`tests/test_generator.py`）。
- D0035-AC-16 その設計で README の「検証」の欄が「あり」になる（同上）。
- D0035-AC-17 `verdict` か `command` だけの設計の出力は、変更の前と文字まで同じ（同上）。
- D0035-AC-18 しきい値が範囲外・`criteria` が空・名前が重なる設計は、検査が止めて直しの依頼文に理由が入り、通らないまま上限に達すれば何も書かない（同上）。
- D0035-AC-19 設計図の形の `check` に `judge` があり、必須ではない（同上）。
- D0035-AC-20 `design_rules.md` と `stage-rules.md` の両方に、組み方の要点の語がある（`tests/test_generator.py`・`tests/test_plugin.py`）。
- D0035-AC-21 `design_rules.md` の設計の例から作ったパイプが検査を通る（`tests/test_generator.py`）。
- D0035-AC-22（実機）実際の Claude で `pipe-in-gen design` を流すと、返る設計が `command` か `judge` を含み、検査を通る。

### ひな形 diagrams

- FR-14 `diagrams` の `verify` 段に、Mermaid の図があるかを確かめる `python -c` の `command` と、`judge`（`criteria` 2つ・`must` 1つ）を組む。`verdict = true`・`on_fail = "draw"`・`max_retries = 2` はそのまま。
- FR-15 そのひな形から作ったパイプが検査を通り、README と `prompts/03_verify.md` もそろえる。
- D0035-AC-23 `verify` 段に `judge` と `command` があり、`command` を実際に流すと、図があれば終了コード 0、無ければ 1 になる。引用符は sh でも cmd.exe でも崩れない書き方（`tests/test_generator.py`）。
- D0035-AC-24 `diagrams` から作ったパイプが検査を通る（`tests/test_generator.py` の既存のテスト）。
- D0035-AC-25 `dev`・`spec-qa` のひな形は変わらない（同上）。
- D0035-AC-26 `diagrams` の README と `prompts/03_verify.md` に、審査の項目と `must` の説明がある（同上）。
- D0035-AC-27 足す前の `diagrams` から作った `judge` の無いパイプは、そのまま動く（同上）。
- D0035-AC-28 依存の向きと拡張の層が変わらず、`pipe_in/` と `vscode/` は変えない（`tests/test_architecture.py`）。

## 決めたことと理由

### 人が決めたこと

- ひな形 `diagrams` の検証の段には、簡単な検査コマンドも書く。審査で差し戻すなら検査と組む、という原則どおりの形を例で示すため。`python` を使うのは、pipe-in が Python で動くので、`python` がある前提にできるから。`python` が無い・名前が違う環境では書き換えるよう、README とガイドに書いた。要件定義の FR-14 の最初の文（command はコメントで案内するだけ）は、この判断の前に書いたもので、実装はこちらに従った。
- 承認したテストのうち4件（AC-15・AC-18）は、補助の関数が同じ一時フォルダに見本のプロジェクトを2回作って落ちていたので、人の了解を得て、2回目を別の一時フォルダで流す形に直した。確かめる中身は変えていない。

### 聞かずに決めたこと

- `stage-rules.md` はスキルのフォルダの中（`references/`）に置き、`${CLAUDE_SKILL_DIR}` で指す。公式の文書の、補助のファイルの置き方に合わせた。
- pipe-builder には、メインの会話が `stage-rules.md` を読んで中身を依頼文に貼り、絶対パスも添える（監査のあとの助言 V-03 で変えた）。マーケットプレイスから入れた人の手元では、この文書が作業フォルダの外（プラグインのキャッシュ）にあり、サブエージェントが読もうとすると権限の確認が出るおそれがあるため。中身が貼られていなければ、pipe-builder はパスから読み、読めなければ差し戻す。
- フック（`generator/guard_hook.py`）は変えない。読む道具はもともと止めておらず、書ける範囲も同じなので。確認を消すためにフックに「許す」を返させる形は、許すものの一覧の守りを広げるので取らなかった。
- 検査コマンドは、図のフォルダの `*.md` を見る（`draw` 段が図をそこに書くため）。バッククォートは `chr(96)*3` で作り、引用符は外側をダブル・中をシングルにした。

### main に合わせたこと

- 決定の記録の番号は、作業を始めたときは D0033 にしていた。しかし main の別の作業（SDK の受信バッファの上限の続き）が、記録の無いまま D0033 の AC をテストで使っていたので、D0034 に振り直した。そのあと main に入った別の直し（PR #68、最初の実行の見張り）が D0034 を使ったので、もう一度載せ直したときに **D0035** に振り直した。
- 検証の前に、main に入った PR #67（同じ作業の続き。`generator/design.py` と `docs/guide/pipes.md` も触っていた）に載せ直した。`docs/guide/pipes.md` の `pipe-in-gen design` の説明の行がぶつかったので、main の文（上限を超えたら止まる）とこのブランチの文（`judge` も組める・審査で差し戻すなら `command` と組む）を両方残した。

### 受け入れたリスク

- ひな形の検査コマンドは `python` の名前に頼る。無い環境では検証の段がコマンドの失敗で不合格になる。README とガイドに書き換えの注意を書いた。
- Windows の実機で、検査コマンドの引用符が崩れないかは確かめていない（sh と cmd.exe の両方で崩れない書き方にした）。
- 審査役のぶれ（D0028 に書いたもの）はそのまま残る。だから審査で差し戻すときは検査と組む決まりにした。

### 監査・助言・審査

- 監査（4件）：A-01（ガイドの審査の例が `command` の無い「審査だけで差し戻す」形だった）・A-02（`must` だけでは検査を通らず、`criteria` が最低1つ要ること）・A-03（`max_retries` の 1〜3 はおすすめで、検査は 0 以上を通すこと）を直した。A-04 はこの記録。
- 助言（8件）：V-03（`stage-rules.md` の中身を依頼文に貼る）と V-04（変数が本文でしか展開されない理由を一言）を直した。V-06（版を 0.6.0 に）は、このブランチで 0.4.0 → 0.5.0 に上げてあるので直さなかった。ほかの5件は「合っている」だった。
- 審査（助言の報告の採点）：overall 0.8・pass。V-02 の「確認が出る可能性が高い」が強すぎる（手元のフォルダから入れた場合はその場で読まれる）点、版の勧めの言いすぎ、hooks の文書を読んでいない点で下がった。

## 対象外・残った課題

- プラグイン自身の eval（`plugin/evals/` と `claude plugin eval`）。次の機能で扱う。
- `stage-rules.md` を変えたら版を上げることを、テストで見張ること（助言 V-06 の任意の案）。
- 作業台（VSCode）で審査を表示・編集する画面（D0028 から残っている）。

## 確かめたこと

- `pytest -q`：全件通過（`tests/test_plugin.py`・`tests/test_generator.py`・`tests/test_guard_hook.py` に足した）。`pipe_in/`・`vscode/`・`generator/guard_hook.py`・`plugin/hooks/` は変えていない。
- D0035-AC-13 のうち Claude を呼ばない範囲：ひな形 `diagrams` から作ったパイプが検査を通り、ひな形の検査コマンドを実際に流すと、図があれば終了コード 0、無いときとフォルダが無いときは 1 になった。
- まだ：D0035-AC-13 の残り（`/pipe-in:pipe-build` を実際に流す）、D0035-AC-14・22（実機）。どれも Claude を呼ぶので、人に言われたときに流す。
