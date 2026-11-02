# D0072 初めての人向けの案内と英語の入口の文書

## 目的

pipe-in を初めて触る人が、拡張の案内（入れる → 見本を選ぶ → 流す → 確認に答える）をたどって最初の1回まで行けるようにする。英語で読む人にも入口（`README.en.md`・`vscode/README.en.md`）を用意し、日本語版と英語版の食い違いはテストで止める。GitHub の issue #26 を扱う。

## 機能要件と受け入れ基準

- FR-01 案内（walkthrough）
  - D0072-AC-01 `vscode/package.json` の `contributes.walkthroughs` がちょうど1つで、`id`・`title`・`description` があり、`steps` が4つ（`vscode/src/manifest.test.ts`）。
  - D0072-AC-02 手順の `id` の並びは `pipe-in.install`・`pipe-in.choose`・`pipe-in.run`・`pipe-in.answer`。どれにも `title`・`description`・`media.markdown` がある。
  - D0072-AC-03 各手順の `media.markdown`（`vscode/walkthrough/01-install.md`〜`04-answer.md`）が実在し、空でない。
  - D0072-AC-04 案内の宣言と本文のどこにも `http://`・`https://`・`<img`・`<script`・`<iframe` が無い。
  - D0072-AC-05 案内の `command:` のリンクは `contributes.commands` にある ID（`pipe-in.showRun`・`pipe-in.editPipe`）だけ。
  - D0072-AC-06 コマンドは2つ、設定は5つのまま。
  - D0072-AC-07 本番のコードに `openWalkthrough` と `globalState` が無い（案内は利用者が「ようこそ」から開く）。
  - D0072-AC-08 「入れる」に `pip install -e .`、「流す」に `pipe-in --project …` の1行、「確認に答える」に `docs/guide/usage.md` の確認の画面への案内がある。
  - D0072-AC-09（実機）VSCode で「ようこそ」から「pipe-in をはじめる」を開くと、手順が4つ並び、本文が出て、ボタンでパネルか作業台が開く。
- FR-02 コマンドを打たない人向けの文書
  - D0072-AC-10 `docs/guide/start-without-commands.md` が実在し、1行目が見出し。ガイドの目次・README の「文書」の表・`vscode/README.md` から指され、リンクが切れていない（`tests/test_english_docs.py`）。
  - D0072-AC-11 端末で1行貼る手順が要ることが書いてあり、「何も打たなくて」「コマンドは不要」のような言い切りが無い。
  - D0072-AC-12 `docs/guide/` の `.md` は11個。`tests/test_guide.py` の `GUIDE_DOCS` と `manifest.test.ts` の数も11個に直した（数だけの直し）。
- FR-03 英語の並置
  - D0072-AC-13 `README.en.md` と `vscode/README.en.md` が実在する。
  - D0072-AC-14 日本語版と英語版の見出しの数と深さの並びが同じ（2組）。
  - D0072-AC-15 コードの塊の数・言語・順番と、シェルの塊のコマンドの行（コメントと引用符の中の文を除く）が同じ（2組）。
  - D0072-AC-16 `<picture>` の画像のファイル名の並びが同じ（2組）。
  - D0072-AC-17 英語版の相対リンクが実在し、アンカーが行き先の見出しに当たる（2組）。
  - D0072-AC-18 食い違い検査そのものの確かめ：見出しの足し・深さ・塊の減り・言語・コマンドの変更・画像の入れ替えを見つけ、文だけが違う英語版は通す。
  - D0072-AC-19 日本語版の先頭に英語版へ、英語版の先頭に日本語版へのリンクがある（2組）。
  - D0072-AC-20 `README.md` は120行以下、冒頭の要点は5〜7項目、目次の行のアンカーの並びは変わらない（既存の `test_guide.py` が通る）。
  - D0072-AC-21 英語版に前の名前の綴り・手元の情報・秘密が無い（`tests/test_rename.py`・`tests/test_rules.py` が一覧を足さずに通る）。
  - D0072-AC-22 記録・設定・パイプの形は変わらない（足したのは文書・宣言・テストだけ。本体とジェネレーターに `walkthrough` が出ない）。

## 決めたことと理由

- 案内は `contributes.walkthroughs` の宣言と、手順ごとの Markdown（`vscode/walkthrough/`）で足す。新しいコマンド・設定・`src/` の変更は無い。ボタンは既存の `pipe-in.showRun` と `pipe-in.editPipe` だけ。
- 人に聞けない夜の実装で、要件・設計の「決めきれない点」は推しで決めた。
  - 案内を起動時に自動で開かない（初回だけ開くには `globalState` への書き込みが要り、拡張が書いてよい範囲を広げるため）。利用者が「ようこそ」から開く。
  - 本文は手順ごとの Markdown ファイル（`media.markdown`）。画像・動画は足さない（外部読み込みの禁止と撮り直しの手間のため）。
  - 食い違い検査の厳しさは、見出しの数と深さ・コードの塊の数と言語・シェルの塊のコマンドの行・画像・リンク。見出しの文は比べない。
  - 流し始めは、文書に端末で1行貼る手順をありのままに書く。拡張に「流す」コマンドは足さない（子プロセスを起こさない決まりのため）。
  - 文書の名前は `start-without-commands.md`。
  - 英語版の移行の節の見出しは “Migrating from the previous name” とし、前の名前の綴りを出さない（`tests/test_rename.py` の一覧に英語版を足さないため）。
  - README.md の英語版へのリンクは、目次の行の末尾に足す（行数が増えず、`test_guide.py` の目次の検査を壊さない）。
  - 食い違いを見る比べ方でコマンドを比べる言語は `bash`・`sh`・`shell`・`console`・`powershell` に絞る（`text`・`toml` の塊には日本語の例が入りうるため）。
- 既存の検査の更新は数だけ：`GUIDE_DOCS` に1つ足し、`manifest.test.ts` の「10個」を11個にした。新しい文書が余分な文書の検査（D0014-AC-08）をすり抜けない形は残した。
- 英語は人が書き、自動翻訳の仕組みは足さない。食い違いはテストで見つけるだけで、直すのは人。英語版の文は日本語版の要約でなく、同じ構成の訳とした。
- 受け入れたリスク：英語版の文の中身が日本語版とずれても（見出しの文・説明の文）、テストでは見つからない（数と形だけを見る）。直すのは README を直す人の仕事で、`docs/development/workflow.md` の「そろえる」に沿う。

## 対象外・残った課題

- 英語の文書は `README.en.md` と `vscode/README.en.md` だけ。`docs/guide/` などの英訳、拡張の画面・コマンド名の英語化（`l10n`）はしない。
- 案内の自動表示、画像・動画、新しいコマンド、拡張から pipe-in を起動する機能。
- `CLAUDE.md` と `docs/development/workflow.md` の「4. そろえる」に「README を直したら英語版も」の一文を足す案は、親に返した（`CLAUDE.md` と `.claude/` はこの段では書けない）。

## 確かめたこと

- `pytest -q`・`npm --prefix vscode test`・`npm --prefix vscode run typecheck`（結果は検証の記録）。既知の1件（`test_D0039_AC_17`）はこの件と無関係。
- D0072-AC-09（実機）：まだ。`npm run preview` は拡張の内側の画面用で、VSCode の「ようこそ」は出ないため、人が実機で見る（拡張を入れ、`Help: Welcome` → 「pipe-in をはじめる」。手順が4つ並ぶ・本文が出る・ボタンでパネルと作業台が開く・自動では開かない）。
