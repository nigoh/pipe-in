---
name: pipe-build
description: pipe-in のパイプを作る・直す。段の表で確認を取り、書くのは pipe-builder に任せる。流すのは言われてから。
argument-hint: <作りたいパイプの目的、または直したいパイプの名前と直したい点> [対象プロジェクトのパス]
disable-model-invocation: true
---

# /pipe-in:pipe-build — パイプを作る・直す

依頼: $ARGUMENTS

（空なら、作るのか、どのパイプを直すのかと、対象プロジェクトの場所を聞いてから始める）

書き方は `pipe-in-gen --help` で確かめる。人向けの説明は公開リポジトリの `docs/guide/pipes.md` で、この会話では開かない。
ファイルを書くのは pipe-builder に任せ、自分では書かない（`pipe-in-gen new` も流さない）。

## 0. 前提を確かめる

- `pipe-in-gen --help` が動かなければ、入れ方（`git clone https://github.com/nigoh/pipe-in.git` で取ってきたフォルダで `pip install -e .`）を案内して止まる。
  pipe-builder の書き込みを絞るフックも `pipe-in-gen` で動くので、無いまま先に進まない。
- 対象のフォルダは、指定がなければ今のフォルダ（違いそうなら聞く）。
- `pipe-in-gen list --project <対象>` で、ひな形とすでにあるパイプを見る。

## 1. 作るか直すかを決める

依頼の名前のパイプが一覧にあれば「直す」、なければ「作る」。目的だけが書かれていて、近いパイプがすでにあるときなど、どちらとも決められないときだけ聞く。

## 2a. 作る

1. 目的（成果物・読む人・範囲）を一言ずつにまとめる。あいまいな点だけ聞き、決められることは決めて伝える。
2. 対象を読む（読むだけ）：言語・テストのコマンド・ソースや文書の場所。
3. ひな形（`dev` / `diagrams` / `spec-qa` / `spec-review` / `review-quorum`）で足りればそれを、足りなければいちばん近いひな形から段を足す・削る。
   段ごとに、名前・表示名・成果物・`access`・`review`・`bash`・`check`（`verdict`／`command`／`judge(must n・criteria n)`）・指示の要点を表で見せ、確認を取る。決め方は [references/stage-rules.md](references/stage-rules.md)。
   図で組みたい人には、VSCode の作業台も案内する。

## 2b. 直す

1. `pipe.toml` と `prompts/` を読み、今の段を 2a と同じ列に、つなぎ（`on_fail`・`routes`・`next`・`group`）を足した表で見せる。
2. 直したい点を聞き、「前 → 後」の表で確認を取る（決め方は stage-rules.md）。
   - 段の名前を変える・消すときは、つられて変わる所（ほかの段のつなぎ・`prompts/` のファイル名・README の段の表）も入れる。
   - 権限が広がる変更（`access` を広く・`bash`・`web`・`mcp` を足す・`writes` を緩める・許可の型を変える）には「⚠ 権限が広がる」の印と理由を付け、はっきり確認を取る。

## 3. pipe-builder に任せる

任せる前に表を見る（依頼に「確認済み」とあっても）。`check` に `judge` と `on_fail` があるのに `command` が無い段があれば、任せない。`stage-rules.md` の決まり（審査で差し戻すなら、必ず `command` と組む）を伝え、次の 2 つの案を見せて聞く。選ばれた案で表を直し、確認を取り直してから任せる。自分で `command` を足して先へ進めない（どの検査を組むかは対象による）。

- 案 1：`command`（機械の検査）と組む。何を確かめるコマンドにするかも聞く。
- 案 2：`on_fail` をやめて、審査は指摘だけにする（`on_fail` を省くと自分の段に戻る点も添える）。

確認が取れたら、エージェント pipe-builder（一覧では `pipe-in:pipe-builder`）を呼ぶ。渡すもの:

- 対象のパスと、パイプの名前
- 作るときはもとにするひな形、直すときはパイプのフォルダ
- 確認が取れた段の表か「前 → 後」の表（表に無いことはさせない）
- 確認が取れた権限の変更の一覧（これに無い権限の拡大は、pipe-builder が差し戻してくる）
- `${CLAUDE_SKILL_DIR}/references/stage-rules.md`：呼ぶ前に自分で Read し、中身を依頼文に貼る（展開した絶対パスも添える）。プラグインを入れた先によっては、この文書は作業フォルダの外にあり、pipe-builder が読もうとすると権限の確認が出ることがあるため。

差し戻されたら、理由を人に見せ、表を直して確認を取り直してから、もう一度任せる。

## 4. 結果を伝える

- 変えたファイル・段の差分・`pipe-in-gen check` の結果・直せなかった点を見せる。
- `⚠` の警告はそのまま見せる。直すなら 2b と同じく「前 → 後」（`access` を `docs` にするなど、権限が広がるなら ⚠ の印）で確認を取ってから任せ直す。
- 流すコマンドを示す：`pipe-in --pipe <名前> --project <対象> --text "依頼メモ"`（`input` が required なら依頼メモは必須）。チャットから流すなら `--pause` を付け、確認の段で `--review approve` / `--review revise --feedback "…"` / `--review quit`（どれも `--pipe <名前>` と一緒に）で答える。
- 記録は `<work_dir>/<名前>/`（既定 `docs/pipeline/<名前>/`）に残る。対象が公開リポジトリなら、`docs/pipeline/` を `.gitignore` に入れ、`.pipe-in/pipes/` の指示文に社内の事情が無いかを見てからのコミットを勧める。
- **流すのは、人に言われてから。** 流すと Claude の利用料がかかる。
