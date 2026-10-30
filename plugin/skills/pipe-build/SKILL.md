---
name: pipe-build
description: pipe-in のパイプ（<対象>/.pipe-in/pipes/pipe-in-<名前>/）を、目的と対象プロジェクトに合わせて作る、またはすでにあるパイプを直す。段の表を見せて確認を取ってから、手を動かすのはエージェント pipe-builder に任せ、pipe-in-gen check が通ったら流し方を伝える。
argument-hint: <作りたいパイプの目的、または直したいパイプの名前と直したい点> [対象プロジェクトのパス]
disable-model-invocation: true
---

# /pipe-in:pipe-build — パイプを作る・直す

依頼: $ARGUMENTS

（空なら、新しく作るのか、どのパイプを直すのかと、対象プロジェクトの場所を聞いてから始める）

パイプは1つのフォルダ（`pipe.toml`・`prompts/`・`README.md`）です。書き方は `pipe-in-gen --help` で確かめる。人が読む説明は公開リポジトリの `docs/guide/pipes.md`（https://github.com/nigoh/pipe-in/blob/main/docs/guide/pipes.md）にあります（プラグインには入っていないので、この会話では開かない）。
ここに書いたのは進め方だけです。この会話では、ファイルを書くのは pipe-builder に任せ、自分では書きません。

## 0. 前提を確かめる

- `pipe-in-gen --help` が動くかを確かめる。動かなければ、pipe-in の入れ方（`git clone https://github.com/nigoh/pipe-in.git` で取ってきて、そのフォルダで `pip install -e .`）を案内して止まる。
  pipe-builder の書き込みを絞るフックも `pipe-in-gen` で動くので、これが無いまま先に進まない。
- 対象プロジェクトのフォルダを決める（指定がなければ今のフォルダ。違いそうなら聞く）。
- `pipe-in-gen list --project <対象>` で、ひな形とすでにあるパイプを見る。

## 1. 作るか直すかを決める

- 依頼にある名前のパイプが一覧にあれば「直す」、なければ「作る」。
- 目的だけが書かれていて、近いパイプがすでにあるときなど、どちらとも決められないときだけ聞く。

## 2a. 作る

1. 目的を確かめる：何を作りたいか（成果物）、だれが読むか、どこまでを対象にするか、を一言ずつにまとめる。あいまいな点だけを質問にまとめて聞く（聞かなくても決められることは、決めて伝える）。
2. 対象を読む（読むだけ）：言語・テストのコマンド・ソース／文書／仕様書の場所。
3. 形を決めて見せる：ひな形（`dev` / `diagrams` / `spec-qa`）でほぼ足りるならそれをもとにし、足りなければいちばん近いひな形から段を足す・削る。
   段ごとに、名前・表示名・成果物・`access`・`review`・`bash`・`check`（`verdict`／`command`／`judge(must n・criteria n)` を分けて書く）・指示の要点を表にして見せ、確認を取る。決め方は `references/stage-rules.md`。
   図で組み立てたい人には、VSCode の「pipe-in: パイプ作業台を開く」（作業台）も案内する。

## 2b. 直す

1. `pipe.toml` と `prompts/` を読み、今の段を表にして見せる（名前・表示名・`access`・`review`・`bash`・`check`（`verdict`／`command`／`judge` を分けて）・つなぎ（`on_fail`・`routes`・`next`・`group`））。
2. 直したい点を聞き、変える点を「前 → 後」の表で見せて確認を取る。
   - 段の名前を変える・段を消すときは、つられて変わる所（ほかの段の `on_fail`・`routes`・`next`、`prompts/` のファイル名、README の段の表）も表に入れる。
   - **権限が広がる変更**（`access` を広くする・`bash`・`web`・`mcp` を足す・`writes` を緩める）には「⚠ 権限が広がる」と印を付け、なぜ要るのかを添えて、はっきり確認を取る。

## 3. pipe-builder に任せる

確認が取れたら、エージェント pipe-builder（一覧では `pipe-in:pipe-builder`）を呼ぶ。渡すもの:

- 対象プロジェクトのパスと、パイプの名前
- 作るときはもとにするひな形、直すときはパイプのフォルダのパス
- 確認が取れた段の表（作るとき）か「前 → 後」の表（直すとき）。表に無いことはさせない
- 確認が取れた権限の変更の一覧（これに無い権限の拡大は、pipe-builder が差し戻してくる）
- 段の決め方の文書：`${CLAUDE_SKILL_DIR}/references/stage-rules.md`。呼ぶ前に自分で Read して、その中身を依頼文に貼る（展開した絶対パスも添える）。プラグインを入れた先によっては、この文書は作業フォルダの外にあり、pipe-builder が読もうとすると権限の確認が出ることがあるため。表に無いことはさせない

pipe-builder が差し戻してきたら、理由を人に見せ、表を直して確認を取り直してから、もう一度任せる。

## 4. 結果を伝える

- 変えたファイルの一覧・段の差分の要約・`pipe-in-gen check` の結果・直せなかった点を見せる。
- `⚠` の警告が返ったら、そのまま見せる。直すなら、2b と同じく「前 → 後」の表で確認を取ってから、もう一度 pipe-builder に任せる（`access` を `docs` にするなどの直しは「⚠ 権限が広がる」の印を付ける）。
- 流すコマンドを示す：`pipe-in --pipe <名前> --project <対象> --text "依頼メモ"`（`input` が required なら依頼メモは必須）。
  チャットから流すなら `--pause` を付け、確認の段で `--review approve` / `--review revise --feedback "…"` / `--review quit`（どれも `--pipe <名前>` と一緒に）で答える。
- 記録は `<work_dir>/<名前>/`（既定は `docs/pipeline/<名前>/`）に残る。
  対象が公開リポジトリなら、`docs/pipeline/` を `.gitignore` に入れることと、`.pipe-in/pipes/` の指示文に社内の事情が入っていないかを見てからコミットすることを勧める。
- **流すのは、人に言われてから。** pipe-in を流すと Claude の利用料がかかる。

段ごとの決め方・検査と審査の組み方・比較実験から分かった組み方の目安・流すときの注意は [references/stage-rules.md](references/stage-rules.md) にあります。2a の3・2b の2で表を作るときに読む。
