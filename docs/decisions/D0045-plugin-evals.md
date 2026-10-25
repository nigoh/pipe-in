# D0045 プラグイン自身の eval を足す

## 目的

プラグインの 3 つのスキル（`/pipe-in:pipe-build`・`/pipe-in:pipe-eval`・`/pipe-in:pipe-judge`）が狙いどおり動くかを、`claude plugin eval`（https://code.claude.com/docs/en/plugin-evals）のケースで測れるようにする。プラグインを直した人が「前より悪くなっていないか」を、費用のかからない採点を中心に確かめられる。実際に流す（利用料がかかる）のは、人に言われたときだけ。

## 機能要件と受け入れ基準

- FR-01 `plugin/evals/` に、スキルごとに 3 本、全部で 9 本のケースを置く。1 ケースは `prompt.md`・`graders/*.md`・`case.yaml`・`scaffold.sh`・`scaffold.py`。
- FR-02 ケースの本文は `/pipe-in:<スキル名> …` で始め、スキルを明示して呼ぶ（3 つとも `disable-model-invocation: true` のため）。
- FR-03 採点は、費用のかからない型（`regex`・`tool_used`・`file_exists`）を中心にする。`llm` は短い最後の返事（`last_message`）だけに使い、1 ケースだけ（`judge-must-violation-fails`）。書かれたファイルの中身は `regex` の `target: {source: file, path: …}` で読む（`target: files` は作られたパスの一覧で、中身ではない）。
- FR-04 ケースの `allowed_tools` には読む道具・`Skill`・`Agent` だけを書く（公式の決まりで、ケースからは `Bash`・`Write`・`Edit` を許せない）。要る道具は `tags` の `needs-bash`・`needs-write` で示し、流し方の `--allow-tools Bash Write Edit` で全ケースに許す。`WebFetch`・`mcp__*` は許さない。
- FR-05 見本（対象プロジェクト・実行の記録）は、`--scaffold` のときに `scaffold.sh`（Bash）が空のワークスペースに作る。中から標準ライブラリだけの `scaffold.py` を呼ぶ。リポジトリの実物は読まない・書かない。`pipe-in-gen` は作らず、PATH に無ければ、または作業フォルダが空でなければ、何も書かずに終了コード 1 で止まる。
- FR-06 結果の置き場所 `plugin/evals/results/` を `.gitignore` に入れる。
- FR-07 流し方（`--scaffold`・`--trust-plugin`・`--allow-tools`・`--model sonnet`・`--judge-model haiku`・`--threshold 0.8`・`--ablation none`・`--output-dir`・`--no-publish`・`--case`・`--tag`・`--max-cost-usd`）、利用料、人に言われたときだけ流すこと、フックがサンドボックスの外で動くこと、Windows は WSL2 で流すことを `docs/guide/plugin.md` に書く。
- FR-08 `pytest` はケースのファイルの形だけを確かめる（SDK・`claude`・子プロセスを呼ばない）。新しい依存は足さない（frontmatter の読み手はテストのファイルの中に置く）。
- FR-09 スキル・エージェント・フック・`pipe_in/`・`generator/`・`vscode/` は変えない。プラグインの版は 0.5.0 のまま。
- D0045-AC-01 9 本のフォルダがあり、どれにも `prompt.md` と `graders/` の中のグレーダーがある。スキルごとに 3 本（`tags` にスキル名）。`tags` には `cheap` か `agent` と、要るものに `needs-*` がある（`tests/test_plugin_evals.py`）。
- D0045-AC-02 `prompt.md` のキーは公式の既知のものだけ。`name` はフォルダ名、`description`・`expected_outcome` が空でない。`model`・`env`・`runs`・`plugins` は書かない（流し方か既定で決める）。`max_turns` は 1〜200、`timeout_seconds` は 1〜3600（同上）。
- D0045-AC-03 グレーダーの型と、型ごとのキー・必須のキー・`weight`・`arm` が公式どおり。`llm` の基準は本文でもよい（同上）。
- D0045-AC-04 `regex` の `pattern` は JavaScript と Python で意味が同じ範囲で、コンパイルできる。`flags` は `i` だけ、`match`・`target` は既知の値（`target` は名前か `{source: file, path: ワークスペースの中の相対パス}`）。ファイルの中身を見る採点は `target: files` を使わない。`judge-score` と `command` の語の採点は、関係ない呼び出しや文に当たらない（同上）。
- D0045-AC-05 `llm` は全体で 2 つ以下・1 ケースに 1 つまで・`last_message` だけ。どのケースにも、費用のかからない型が 3 つ以上ある。`max: 0` のときは `min: 0` も書く（同上）。
- D0045-AC-06 どの本文も、そのケースのスキルの `/pipe-in:<スキル名>` で始まる（同上）。
- D0045-AC-07 `allowed_tools` は読む道具・`Skill`・`Agent`・`TodoWrite` などの中だけ。`tool_used` が `Bash`・`Write`・`Edit` を `min` 1 以上で見るケースは、`needs-bash`・`needs-write` の tags を持つ。`tool_used: Skill` は使わない（同上）。
- D0045-AC-08 `case.yaml` は `schema_version: "1.1"`・`name` がフォルダ名・`scaffold_script` がケースの中に実在する。`scaffold.sh` は `scaffold.py` を呼ぶだけ。`scaffold.py` は空の一時フォルダの中にだけ書き、実物に似た木や空でない木は断る。`file_exists` の `path` は相対パス（同上）。
- D0045-AC-09 `plugin/evals/` の下のどのファイルにも、手元のパス・鍵・メールアドレスが無い（同上）。
- D0045-AC-10 `.gitignore` に `/plugin/evals/results/` がある（同上）。
- D0045-AC-11 壊した入力（古い `schema_version`・知らないキーや型・グレーダー無し・範囲外の書き方など）を検査が落とす（同上）。
- D0045-AC-12 ケースのテストは、子プロセス・`claude`・SDK を使わない（同上）。
- D0045-AC-13 スキル・エージェント・フック・`pipe_in/`・`generator/`・`vscode/` に差が出ない（既存の `tests/test_plugin.py`・`tests/test_architecture.py`）。
- D0045-AC-14 版は 0.5.0 のままで、スキルとフックは `evals/` に頼らず、ガイドの更新の節も 0.5.0 のまま（`tests/test_plugin_evals.py`）。
- D0045-AC-15 `docs/guide/plugin.md` に節「プラグインの eval」があり、流し方のフラグ・注意・9 本のケース名が書かれている（同上）。
- D0045-AC-16 `docs/development/design.md` の `plugin/` の行に `evals/` が出て、`testing.md` に、`pytest` は形だけ・流すのは人に言われたときだけと書かれている（同上）。
- D0045-AC-17（実機）`--case` 1 本・`--runs 1` で流し、9 本が読み込みエラーなしに読めること、スラッシュ呼びが展開されること、`file_exists` の `path` の基準、ファイルが作られなかったときの `not_contains`、サブエージェントの道具の呼び出しが `tool_used` に数えられるかを確かめる。
- D0045-AC-18（実機）`eval-lists-and-waits` を `--runs 1` で流し、一覧が出て、結果が `--output-dir` の先にでき、`git status` に差が出ない。1 ケースの費用を測る。
- D0045-AC-19（実機）9 本を `--runs 3 --threshold 0.8 --ablation none --max-cost-usd <18 から決めた上限>` で流し、終了コード・各ケースの合否・費用をここに書く。落ちたケースは、スキルの不具合かケースの不具合かを切り分ける。
- D0045-AC-20（実機）`build-*` のケースで、フックが pipe-builder の正しい書き込みを止めず、範囲外は止める。
- D0045-AC-21（手で）作業コピーでスキルの 1 行（pipe-eval の「返事を待つ」）を消すと、そのケースの採点が落ちる。作業コピーは戻す。

## 要件の段から変えた点

- `allowed_tools` で `Bash`・`Write`・`Edit` を付ける案（要件の FR-04・AC-07）は、公式で許されないので、`tags` の `needs-*` と流し方の `--allow-tools` に分けた。
- `runs` を 1 以上で許す案（AC-02）は、`runs`・`env`・`plugins` を書かない形にした（回数は流し方の `--runs` で決める）。
- 費用のかからない型の数（AC-05）は、2 つ以上から 3 つ以上にした。
- 長い成果物を `target: files` で見る案（FR-03）は、`files` がパスの一覧で中身ではないと公式にあるので、`target: {source: file, path: …}` に替えた（助言 V-01）。
- `build-refuses-judge-only` の「差し戻し」の返事は、関係ない文にも当たるので数えず、`command` と組む案内だけを見る（監査 A-09）。

## 決めたことと理由

- **スラッシュで呼ぶ。** スキルはモデルが自分では選ばないので、本文を `/pipe-in:<スキル名>` で始める。`claude -p` で `/スキル名` が展開されることは公式の headless の文書にある。eval の中で名前空間付きの形が展開されるかは書かれていないので、AC-17 で確かめ、効かなければ文で頼む形に替える（テストは `starts_with_skill` の 1 か所を直す）。
- **見本は `scaffold.sh` から `scaffold.py` を呼んで作る。** 公式の `scaffold_script` は Bash。中身を標準ライブラリだけの Python にすると、テストで `importlib` で読んで、一時フォルダに書く動きを確かめられる。見本のファイルを置くフォルダを別に作らない（公式がケースと読み違えないように）。`scaffold.sh` には実行ビットを付けた（要るかは公式に書かれていないが、害はない）。
- **`pipe-in-gen` は作らず、無ければ止める。** 利用料を使う前に気づける。9 本とも見本づくりで要る。サンドボックスの Bash は home の下を読めないので、home の外に入れるよう文書に書いた。
- **`--ablation none`。** ケースは `/pipe-in:<スキル>` を呼ぶので、プラグイン無しの回と比べる意味がほとんどない。付けないと費用が倍になる。
- **`--threshold 0.8`・`--runs 3`。** `llm` の採点と実行のぶれがあり、1.0 だと 1 回のぶれで落ちる（公式の CI の例も 0.8）。
- **`cheap`・`agent` の tags。** 審査役やサブエージェントを呼ぶ高いケースを外して、`--tag cheap` で安く流せる。
- **版は 0.5.0 のまま。** スキル・エージェント・フックの動きは変わらない。`evals/` は入れた人の手元にも入るが、小さなテキストだけ。
- **frontmatter の読み手はテストの中に置く。** PyYAML を足さない。読める範囲（1 行 1 項目・1 行のリスト・1 行の対応表・`case.yaml` の `context` 1 段）の外は `ValueError` にして、黙って読み飛ばさない。

## 対象外・残った課題

- `claude plugin eval` を CI で流すこと（利用料がかかるため）。
- `pipe-live` のケース（claude.ai にログインした Claude Code でしか動かない）。
- `tool_used: Skill` の採点・自然な言い方でスキルが発火するかのケース（スキルはモデルが自分で選ばないので、今は要らない）。
- 公式の `llm` の採点（3 票中 2 票）と `pipe-judge` の `--runs` の見比べ（D0022 の助言 V-05）。
- `eval-*` の 3 本は、流すコマンドに `python` を使う。`python3` だけの環境では落ちる（文書に書いた）。
- `eval-result-json` は 1 回のやり取りで「一覧は確認済みで流してよい」と伝える。スキルが手順どおりに確認で止まると、採点が落ちる恐れがある（監査 A-06）。実機で止まるなら、測りを「一覧を出して聞く」までに替える。
- 見本の `state.json` は実物を縮めた形。pipe-eval が中身を読むようになったら、実物のキーにそろえる。
- 実機でまだ確かめていないこと：`claude plugin eval` の中でのスラッシュ呼びの展開、`scaffold.sh` の起こされ方（`$0` の形）、`file_exists` の `path` の基準と先頭が `.` のフォルダ、サブエージェントが書いたファイルや呼んだ道具が採点に数えられるか、pipe.toml が作られなかったときの `not_contains`、`--judge-model haiku` の別名が通るか、サンドボックスの中から `pipe-in-gen` が見えるか、1 ケースの費用と `--max-cost-usd` の値。

## 確かめたこと

- `pytest -q`：`tests/test_plugin_evals.py` を含めて全体が通る。
- `scaffold.sh` を 9 本とも、空の一時フォルダで手で流した（`pipe-in-gen` を PATH に入れた一時の venv）。どれも見本ができて終了コード 0。ファイルのあるフォルダでは終了コード 1。`pipe-in-gen` が PATH に無いと、そう知らせて終了コード 1。
- 助言（公式の plugin-evals・headless の文書との照合）の V-01〜V-04 と、監査の A-02・A-04・A-07・A-09 を直した。助言の報告は審査役の採点で pass（総合 0.94）。
- `claude plugin eval` はまだ流していない（AC-17〜21 はまだ）。
