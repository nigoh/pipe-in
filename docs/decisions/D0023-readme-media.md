# D0023 README の冒頭のロゴを動くロゴにし、VSCode の中の画面を載せる

## 目的

README を開いた人に、pipe-in が「差し込むと流れ出す」道具だという印象を、冒頭の動くロゴで伝える。あわせて、拡張が本物の VSCode の中でどう見えるかを、確認用のページではなく VSCode の画面で見せる。

## 機能要件と受け入れ基準

- FR-01 README の冒頭のロゴを、動くロゴ（`pipe-in-plug-logo.html` から撮った GIF）にする。明るい表示と暗い表示で出し分ける
  - D0023-AC-01 冒頭のロゴの `<picture>` は、明るい表示では `pipe-in-plug-logo.gif`、暗い表示では `pipe-in-plug-logo-dark.gif` を出し、alt は `pipe-in`、width がある（`tests/test_readme_media.py::test_d0023_ac01_readme_logo_is_animated`）
- FR-02 動きを減らす設定の人には、止まったロゴを出す
  - D0023-AC-02 `prefers-reduced-motion: reduce` のときは、止まったロゴ（`pipe-in-logo.svg`・暗い表示では `pipe-in-logo-dark.svg`）を出す。その `<source>` は動くロゴの `<source>` より前に置く（ブラウザは先に合ったものを使う）（`::test_d0023_ac02_reduced_motion_shows_still_logo`・`::test_d0023_ac02_choose_follows_source_order`）
- FR-03 暗い表示の動くロゴの GIF を作る
  - D0023-AC-03 `pipe-in-plug-logo-dark.gif` は幅 800 以下・900KB 以下で、2コマ以上あり、くり返す（`::test_d0023_ac03_dark_gif_limits`）
- FR-04 置き場所の説明に、新しい画像と撮り方を書く
  - D0023-AC-04 `docs/assets/README.md` の表に、暗い表示の GIF と VSCode の中の画面4枚の行があり、「VSCode の中の画面を撮る」の節がある（`::test_d0023_ac04_assets_readme_rows`）
- FR-05 README の「すぐ試す」に、VSCode の中の画面を載せる
  - D0023-AC-05 「すぐ試す」に「### VSCode で見る」があり、VSCode の中の実行パネルと作業台を明暗で出す。4枚とも 1280×800（`::test_d0023_ac05_readme_shows_vscode_shots`・`::test_d0023_ac05_vscode_shots_size`）

## 決めたことと理由

- **冒頭のロゴは動くロゴにし、止まったロゴは動きを減らす設定のときに出す。** 動くロゴは、差し込んでオレンジが広がる動きで、pipe-in の「流れ出す」感じを一目で伝えられる。一方で、くり返し動く画像は、動きを減らす設定の人には負担になる。GIF は自分では止まれないので、`<picture>` の `prefers-reduced-motion` で止まったロゴ（SVG）に替える。GitHub は `<source>` の `media` をそのまま残すので、ブラウザが選ぶ。
- **`<source>` の並びは「動きを減らす×暗い → 動きを減らす → 暗い → 明るい（img）」。** ブラウザは先に合った `<source>` を使うので、動きを減らす設定の2つを先に置く。
- **暗い表示の GIF を新しく作った。** D0013 では明るい表示の GIF だけを作っていた。README の冒頭は暗い表示の人にも明るい表示の人にも見えるので、暗い表示のページ（同じ `pipe-in-plug-logo.html`。色は CSS の暗い表示の色）から同じ撮り方で作った。明るい表示の GIF は作り直していない（D0013 のまま）。
- **撮り方は、時計を止めて 1/15 秒ずつ進める。** Playwright の `page.clock` で時計を止め、`runFor` で進めながら舞台（`#stage`）だけを撮る。止めないと、撮るあいだにも動きが進み、コマが飛ぶ。はじめの間から、オレンジが広がりきって落ち着くまでを撮る（そのあとはプラグを抜く動きに入る）。40色・1コマ 60ms・最後のコマは 1.26 秒止める、は明るい表示の GIF とそろえた。できた GIF は 59コマ・約5.8秒・約530KB。
- **冒頭のロゴの幅は 560。** GIF は舞台の余白ごと写っているので、止まったロゴの 420 のままでは文字が小さく見える。
- **D0014-AC-02 のロゴの見つけ方を広げた。** 冒頭の並び（ロゴ → 一文 → パネル → 要点 → 目次）の検査は、ロゴを src に `pipe-in-logo` を含む `<picture>` で見つけていた。動くロゴ（`pipe-in-plug-logo.gif`）でも見つかるよう、src に `logo` を含むもので見つける。並びの検査そのものは変えていない。
- **VSCode の中の画面は、本物の VSCode（VS Code Server のブラウザ版）で撮る。** 冒頭の画像（`run-panel-*.png`）は、確認用のページで写した拡張のパネルだけの画面。VSCode の中でどう見えるか（コマンドパレット・ステータスバー・エディターの中のパネル）は、それだけでは伝わらない。手元に VSCode が無い環境でも撮れるよう、VS Code Server のブラウザ版を手元だけで動かし、`.vsix` を入れて Playwright で撮る。撮り方は `docs/assets/README.md` の「VSCode の中の画面を撮る」に書いた。
- **VSCode の中の画面は「すぐ試す」の終わりの「### VSCode で見る」に置く。** 冒頭の並び（D0014-AC-02）は変えない。「すぐ試す」で流したあと、次に何を開けばよいかの流れに合う。
- **VSCode の言語は英語で撮る。** 日本語にすると、版の合わない日本語の言語パックが入って表示が崩れた。拡張のパネルの中は日本語なので、伝えたいところは日本語で見える。

## 対象外・残った課題

- 明るい表示の GIF（`pipe-in-plug-logo.gif`）は作り直していない。同じ撮り方で作り直すと、明暗で時間の流れがそろう（いまは明るい表示が約5.9秒、暗い表示が約5.8秒）。
- GitHub での見え方（動きを減らす設定で止まったロゴに替わるか）は、手元のブラウザで `<picture>` を開いて確かめた。GitHub の上では、取り込んだあとに確かめる。
- 拡張の README（`vscode/README.md`）には、VSCode の中の画面を載せていない。拡張の README は、パネルと作業台の画面（D0009）で足りている。
- 止まったロゴ（SVG）を、動きの終わりの姿（差した姿）に合わせるかは、D0013 の残った課題のまま。

## 確かめたこと

- `pytest -q tests/test_readme_media.py`：先に書いたテストが、main の文書では AC-01・03・04・05 で期待した理由（ロゴが SVG・暗い GIF が無い・表の行が無い・「### VSCode で見る」が無い）で落ち、変えたあとは全部通る。AC-02 は、変える前のロゴが止まったロゴなので、はじめから通る（動くロゴにしたあとも止まったロゴに戻れることを見張る）。
- `pytest -q tests/test_readme.py tests/test_guide.py tests/test_rules.py tests/test_rename.py tests/test_plug_logo.py tests/test_readme_media.py` が通る。
- 画面（Playwright・Chromium）：README と同じ `<picture>` を、明るい・暗い × 動きを減らす設定あり・なし の4通りで開き、選ばれる画像が上の並びのとおりであることを確かめた。暗い表示の GIF をコマごとに見て、はじめの間 → 運ぶ → 差し込む → カチッ → 広がる、が見え、色が暗い表示の色であることを確かめた。
- VSCode の中の画面4枚：撮った画面を開いて、ユーザー名の入ったパス・メールアドレス・本物のプロジェクトの名前が写っていないことを目で見た。
- GitHub の上での見え方は、まだ。
