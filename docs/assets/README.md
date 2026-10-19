# docs/assets/

README（リポジトリの `README.md` と `vscode/README.md`）とガイド（`docs/guide/vscode.md`）に載せる画像の置き場所と、画像の撮り直し方。

## ここにあるもの

| ファイル | 中身 | 撮るページ |
| --- | --- | --- |
| `pipe-in-logo.svg`・`pipe-in-logo-dark.svg` | ロゴ（明るい表示用・暗い表示用） | （撮らない） |
| `run-panel-light.png` | 「実行を見る」パネル（明るい） | `out/preview/run-panel-light.html` |
| `run-panel-dark.png` | 「実行を見る」パネル（暗い） | `out/preview/run-panel-dark.html` |
| `pipe-editor-light.png` | パイプ作業台（明るい） | `out/preview/pipe-editor-light.html` |
| `pipe-editor-dark.png` | パイプ作業台（暗い） | `out/preview/pipe-editor-dark.html` |
| `pipe-in-plug-logo.html` | ロゴの動き。止まったロゴを一拍見せてから、プラグを運んでコンセントの真上で向きをそろえ、上から差し込む。カチッとはまってオレンジが広がる（ケーブルはひもの物理演算）。カメラは全体から始めてコンセントへ寄り、広がりと一緒に引く（型は5つから選べる）。ブラウザで開くとくり返し動き、「フローまで見せる」で作業台の動きまで続く。外から何も読み込まない。決めたことは [D0013](../decisions/D0013-plug-logo-motion.md) | （撮らない） |
| `pipe-in-plug-logo.gif` | 上の動きの、はじめの間から差し込んでオレンジが広がりきるまで（幅 800・約6秒・カメラは「全体から寄る」） | `pipe-in-plug-logo.html` を時刻を進めながら撮った（1秒に15枚・40色） |

画像は、見本の記録（`tests/fixtures/showcase/`）と見本のパイプを、拡張の本物の画面で写したものです。費用・トークン・利用枠の数字は見本です。

## 撮り直す

1. 見本の記録を作り直す（本体の記録の形が変わったときだけ。`tests/test_showcase.py` が落ちて知らせます）。見本は4つ（`showcase/`：完了、`showcase_running/`・`showcase_running_next/`：動いている途中、`showcase_waiting/`：確認待ち）で、まとめて作り直されます。画像に使うのは完了の見本だけで、残りの3つは確認用のページ（`run-panel-running-*.html`・`run-panel-waiting-*.html`）の素材です。

   ```bash
   python tests/showcase.py
   ```

2. 確認用のページを作る。`vscode/out/preview/` に `run-panel-light.html`・`run-panel-dark.html`・`pipe-editor-light.html`・`pipe-editor-dark.html` などができます。動き（脈打ち・点の流れ・点滅）を見るためのページ `run-panel-running-*.html`・`run-panel-waiting-*.html` もできますが、動きは静止画に写らないので、画像には撮りません。

   ```bash
   cd vscode
   npm run build
   npm run preview
   cd ..
   ```

3. 手元だけで配る（リポジトリの直下で）。

   ```bash
   python -m http.server 8765 --bind 127.0.0.1 --directory vscode/out/preview
   ```

4. Playwright（MCP）で撮る。4枚とも同じ手順です。
   - `browser_resize` で **1280×800**（拡大なし）にする。
   - `http://127.0.0.1:8765/<ページ>.html` を開く。作業台のページは、ブロック「ソースの調査」を1回押して、右に段の設定が出た状態にする。
   - `browser_take_screenshot` で PNG を撮る（見えている範囲だけ。ページ全体ではない）。
   - 上の表のファイル名で、このフォルダ（`docs/assets/`）に置く。
5. 確かめる。

   ```bash
   python -m pytest -q tests/test_readme.py tests/test_guide.py   # 横 1600px 以下・600KB 以下か、README とガイドから使われているか
   ```

   画像を開いて、ユーザー名の入ったパス・メールアドレス・本物のプロジェクトの名前が写っていないかを目で見ます。
6. 片付ける。配るのを止め（Ctrl+C）、Playwright が作った `.playwright-mcp/` を消します。
