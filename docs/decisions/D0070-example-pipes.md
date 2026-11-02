# D0070 見本のパイプ集（examples/）と、作業台の「見本から作る」

## 目的

パイプを主役にするなら、選んですぐ流せる見本が要る。これまでは `pipe-in-gen new` のひな形と、`/pipe-in:pipe-build` で一から作る形だけだった。
「図を作る」「仕様とソースの突き合わせ」「調べものをまとめる」の3つの見本を `examples/` に置き、それぞれの README に、何をするか・費用の目安・書ける範囲を書く。作業台（VSCode）から見本を選んで、下書きとして写せるようにする。GitHub の issue #25（段階4の一部）を扱う。開発フローは作業台で開けないので見本から外した。

## 機能要件と受け入れ基準

AC の表は、承認された要件定義（設計で一部を改めたもの）のとおり。

- D0070-AC-01 `examples/` の下に `diagrams`・`spec-qa`・`research` があり、それぞれ `pipes/pipe-in-<名前>/` の下に `pipe.toml`・`README.md`・`prompts/` の指示文（段の数だけ）がある。
- D0070-AC-02 3 つの見本はどれも、`load_pipe` で読めて、`check_pipe` の誤りが 0 件、`lint_pipe` の注意が 0 件。
- D0070-AC-03 `pipe-in-gen check <名前> --pipes-dir examples/<名前>/pipes`（3 つとも）の終了コードが 0。
- D0070-AC-04 3 つの見本のすべての段に、0 より大きい `max_budget_usd` と `max_turns` がある。
- D0070-AC-05 3 つの見本の README に、「何をするか」「流し方」「段と書ける範囲」「費用の目安」「直し方」の節がある。
- D0070-AC-06 README の段と書ける範囲の表の行の数と段の名前・`access` が、`pipe.toml` と同じ（`docs` の段は `docs_dir` も）。
- D0070-AC-07 README の費用の表の各段の上限が `pipe.toml` の `max_budget_usd` と同じで、「1 回通しの上限の合計」が段の合計と等しい。差し戻し（`on_fail`・`max_retries`）がある見本では、「差し戻しを使い切ったときの上限の合計」が、戻り先から判定の段までの上限の合計 × `max_retries` を足した値と等しい。
- D0070-AC-08 README の費用の節に、実測はまだであること（上限であって見積りではない）を書いた文がある。
- D0070-AC-09 `research` の段は `frame`・`gather`・`summarize`・`verify` の順で、4 段とも `access = "read"`、`input = "required"`、`web` も `fetch_domains` も `mcp`・`bash` も無い。`frame` と `summarize` が `review = true`。
- D0070-AC-10 `research` の `verify` は `[stages.check]` を持ち、`verdict = true`、`on_fail = "summarize"`、`max_retries = 2`、審査の `must` に「出典のない断定がない」に当たる項目が 1 つ以上ある。
- D0070-AC-11 `research` の `gather` の指示文に、事実ごとに出典（ファイルと場所）を書くこと・出典が無いものは「分からない」と書くこと・Web を使わないことがある。
- D0070-AC-12 `diagrams`・`spec-qa` の見本の `prompts/*.md` は、ひな形を、決まった値（`name`＝見本の名前、`diagrams_dir`＝`docs/diagrams`、`source_dirs`＝`プロジェクト全体`、`docs_hint`＝`プロジェクトの中`）で埋めたものと、一字も違わない。
- D0070-AC-13 `diagrams`・`spec-qa` の見本の `pipe.toml` を読んだ値は、`max_budget_usd`・`max_turns` を除けば、同じ値で埋めたひな形の `pipe.toml` を読んだ値と同じ。
- D0070-AC-14 ひな形の指示文を 1 字変える（またはひな形に段を足す）と、AC-12・13 のテストが落ちる（ひな形側だけ直して見本を置き忘れても気づける）。
- D0070-AC-15 `examples/diagrams/`・`examples/spec-qa/`・`examples/research/` の全ファイルに、手元の情報（ユーザー名の入った絶対パス・メールアドレス）も秘密のファイル名も無い（`tests/test_rules.py` の検査と同じ規則）。
- D0070-AC-16 3 つの見本に、置き換え前の `{{…}}` が残っていない。
- D0070-AC-17 3 つの見本に、動画・画像・音声のファイルと、`.py`・`.js`・`.mjs`・`.sh`・`.html` のファイルが無い。見本の中のファイルは `pipe.toml`・`README.md`・`prompts/*.md` だけ。
- D0070-AC-18 古い形の扱い：`examples/video/`・`examples/truncate/` は変えない。既存の `tests/test_video_example.py` の検査（動画の見本だけを見る）は今のまま通る。
- D0070-AC-19 見本のデータ（TS）の見本の数・名前・各ファイル（相対パス → 中身）が、`examples/*/pipes/pipe-in-*/` の `pipe.toml`・`prompts/*.md` と一字も違わない（`examples/` を直したのにデータの生成を忘れると落ちる）。
- D0070-AC-20 見本のデータの各見本は、拡張の `pipeFromFiles` で読め、`validatePipe` の誤りが 0 件で、段の数・段の名前の並び・`access`・`max_budget_usd`・戻り先（`on_fail`）が `pipe.toml` と同じ。
- D0070-AC-21 見本のデータに入れるのは `pipe.toml` と `prompts/*.md` だけ（`README.md` と `layout.json` は入れない）。
- D0070-AC-22 拡張の実行時のコード（`vscode/src/`、テストと生成の道具を除く）が `examples/` を読むパス・`readFile` を持たない（束ねたデータだけを使う）。
- D0070-AC-23 見本の一覧を返す関数は、見本ごとに名前・ラベル・説明・段の数・上限の合計を返し、名前の順に並ぶ。見本が空のデータなら空の配列。
- D0070-AC-24 見本とパイプ名から `PipeModel` を作る関数は、モデルの `name` を渡した名前にし、段・指示文は見本のとおりにする。名前が使えない文字のとき、同名のパイプがあるときは、`saveTarget` と同じ文で断る（同名の確かめは既存の判断を使う）。
- D0070-AC-25 見本から作った `PipeModel` を、既存の `savePipe`（偽の `PipeStore`）で保存すると、書くのは `pipe.toml`・`layout.json`・`prompts/*.md` と、無ければ README の下書きだけで、`PipeStore.write` の第 1 引数は `pipe-in-<名前>`、`remove` は呼ばれない。
- D0070-AC-26 見本から作った `PipeModel` を保存して `loadPipe` で読み戻すと、段の数・名前・`access`・`max_budget_usd` が、見本のデータと同じ（作業台の読み書きで見本の内容が落ちない）。
- D0070-AC-27 見本から作るまでの手順（一覧 → 名前 → モデルを作る）は、`PipeStore` の `write`・`remove` を呼ばず、`VersionStore` にも書かない（偽の口で数える）。
- D0070-AC-28 保存先の検査：パネルから来た値では保存先を決めない（既存の `saveTarget` を使う）。見本の名前が `logs`・`..`・`/` を含むときは断る。`fsPipes.ts` が書けるファイルの集まり（`pipe.toml`・`layout.json`・`README.md`・`prompts/*.md`）は変わらない。
- D0070-AC-29 `extension.ts` の入口の配線：「見本から作る」の項目と、見本の選びの QuickPick と、名前の `showInputBox` が `editPipe` にあり、`registerCommand` の数と `package.json` の `commands` は変わらない（配線を字面で見るテスト。`manifest.test.ts` は今のまま通る）。
- D0070-AC-30（手で）本物の VSCode で「pipe-in: パイプ作業台を開く」→「見本から作る」→ 見本を選ぶ → 名前を入れる、で作業台が開き、タブ名に未保存の印があり、パイプの置き場所には何も増えていない。「保存」を押すと `.pipe-in/pipes/pipe-in-<名前>/` に `pipe.toml`・`prompts/`・`README.md` ができる。
- D0070-AC-31（手で）AC-30 で作ったパイプを `pipe-in-gen check <名前> --project <対象>` にかけると誤りが 0 件。同じ名前でもう一度「見本から作る」を選ぶと、名前の入力欄で断られる。
- D0070-AC-32（実機）Windows・WSL・Remote の VSCode でも AC-30 のとおりになる（今は確かめていない）。
- D0070-AC-33 層の向きが変わらない（`tests/test_architecture.py`・`vscode/src/architecture.test.ts` が通る）。見本のデータの TS は `domain/` にあり、`node:path` 以外を import しない。
- D0070-AC-34 拡張の書き込み先は増えない（`infra/` で書く関数を持つのは `fsPipes.ts`・`fsVersions.ts` だけ。D0065-AC-22 と同じ検査が通る）。
- D0070-AC-35 作業台の HTML は外部を読み込まない（既存の CSP の検査が通る）。見本の文字（ラベル・説明・指示文）をパネルに出す前は `escapeHtml` を通る（作業台は既存の経路で出す）。
- D0070-AC-36 `package.json` の `contributes`（コマンド・設定）は変わらず、依存は足さない（`package-lock.json` も変わらない）。
- D0070-AC-37 `examples/README.md` があり、3 つの見本の名前・用途・流し方・README へのリンクが並ぶ。リンク先が実在する。
- D0070-AC-38 `docs/development/design.md` の置き場所の表に、見本（diagrams・spec-qa・research）の行と、拡張の見本のデータの行がある。表のパスが実在する（`tests/test_rules.py` が通る）。
- D0070-AC-39 `docs/guide/pipes.md` と `docs/guide/vscode.md` に「見本」の節があり、`examples/README.md` へのリンクがある。ガイドの検査（`tests/test_guide.py`）が通る。

## 決めたことと理由

- 見本は `examples/<名前>/pipes/pipe-in-<名前>/`（動画の見本と同じ形）に置く。`pipe-in-gen check <名前> --pipes-dir examples/<名前>/pipes` でそのまま確かめられるため。
- `diagrams`・`spec-qa` は `generator/templates/` を決まった値で埋めた写しに `max_budget_usd`・`max_turns` を足したもの。`research`（問いを整える → 調べる → まとめる → 出典の突き合わせ）は新しく書いた。二重管理は、ひな形を変えたら見本が合わなくなる検査（`tests/test_examples.py`）で止める。ひな形に上限を足して見本をなくす案は、ひな形を変えない決まり（D0037）と、公開前に手元の情報を消す趣旨に合わないので選ばなかった。
- `research` の `summarize` は `access = "docs"`（`docs/research`）、`verify` に機械の検査（`command`）を付けた。lint の W5（検証の戻り先が読むだけの段）と、`docs/guide/pipes.md` の「審査で差し戻すなら `command` と組む」に合わせるため。要件定義の「4段とも read」から動かした。Web は使わない。足し方は README に書く。
- 費用の目安は、段ごとの上限と、1回通しの合計と、差し戻しを使い切った合計。本物は流していないので実測はまだ（上限であって見積りではない）。
- 見本のデータは、`vscode/scripts/genExamples.ts` で `examples/` から `vscode/src/domain/exampleData.ts` を作ってコミットし、テストで元との一致を見張る。拡張が実行時に `examples/` を読まない形で、読む場所と書く場所を増やさないため。ビルドのたびに生成する案より、差分が見えてテストで守れる。`vscode/package.json` の `scripts` に `examples:gen` を足した。
- 入口は `editPipe` の QuickPick に「見本から作る」を足す形。コマンド・設定・依存は増やさない。見本は保存していない下書きとして開き、保存は既存の `saveTarget`・`savePipe` を通す。README は写さず、作業台の下書きが付く。

## 受け入れたリスク

- 費用の上限の数字は実測に基づかない。実測が取れたら別の変更で直す。
- 見本を直したときに `npm run examples:gen` を忘れても、テストが赤になるので気づく（手順としての案内が `examples/README.md` に足りないことは監査 A-03）。

## 対象外・残った課題

- 監査の報告（A-01〜A-04）は直していない。A-01 はこの記録を書いて解消した。全文は PR の本文の「朝に見ること」にある。
- `CLAUDE.md` のコマンドの節に `npm run examples:gen` を足す案と、`/pipe-help` に「見本から作る」を足す案は、書けないので案のまま（PR の本文）。
- 助言（公式の文書との照らし合わせ）と審査は、`.claude/`・plugin・guard を触らないので流していない。
- 土台から落ちている `tests/test_skill_tidy_docs.py::test_D0039_AC_17` はこの件と無関係で、直していない。

## 確かめたこと

- `pytest -q`（既知の1件以外が通る）、`npm --prefix vscode test`（5622 件）・`npm --prefix vscode run typecheck`・`npm --prefix vscode run build`・`npm --prefix vscode run examples:gen`（生成の一致はテストで見張る）。
- AC-30・31（手で）と AC-32（Windows・WSL・Remote の実機）：まだ。QuickPick は webview の外なので、確認用ページも画面の AC もない。
- 本物のモデルでの見本の実行（利用料がかかる）：まだ。
