# docs/assets/

README（リポジトリの `README.md` と `vscode/README.md`）とガイド（`docs/guide/vscode.md`）に載せる画像の置き場所と、画像の撮り直し方。

## ここにあるもの

| ファイル | 中身 | 撮るページ |
| --- | --- | --- |
| `pipe-in-logo.svg`・`pipe-in-logo-dark.svg` | ロゴ（明るい表示用・暗い表示用） | （撮らない） |
| `run-panel-light.png` | 「実行を見る」パネル（明るい）。一覧の「終わった」の一番下（前の実行・合格、修正の依頼1回・差し戻し1回）を押して選んだところ | `out/preview/run-panel-runs-light.html` |
| `run-panel-dark.png` | 「実行を見る」パネル（暗い）。同じ | `out/preview/run-panel-runs-dark.html` |
| `run-list-light.png` | 実行の一覧と詳細（明るい）。上のバー・左の一覧・右の詳細（図・出力・時系列）の 3 領域。確認待ちの別の worktree の行を押して選んだところ | `out/preview/run-panel-runs-light.html` |
| `run-list-dark.png` | 実行の一覧と詳細（暗い）。同じ | `out/preview/run-panel-runs-dark.html` |
| `run-list.gif` | 実行の一覧の動き（約20秒）：別の worktree の動いている行を選ぶ→Ctrl＋ホイールで図を拡大→100% に戻す→確認待ちの行→「終わった」のタブ→前の実行の行→「使用量」のタブ（全体を幅 640・24色・1秒に1.5コマ） | `out/preview/run-panel-runs-dark.html` |
| `pipe-editor-light.png` | パイプ作業台（明るい） | `out/preview/pipe-editor-light.html` |
| `pipe-editor-dark.png` | パイプ作業台（暗い） | `out/preview/pipe-editor-dark.html` |
| `pipe-in-plug-logo.html` | ロゴの動き。止まったロゴを一拍見せてから、プラグを運んでコンセントの真上で向きをそろえ、上から差し込む。カチッとはまってオレンジが広がる（ケーブルはひもの物理演算）。カメラは全体から始めてコンセントへ寄り、広がりと一緒に引く（型は5つから選べる）。ブラウザで開くとくり返し動き、「フローまで見せる」で作業台の動きまで続く。外から何も読み込まない。決めたことは [D0013](../decisions/D0013-plug-logo-motion.md) | （撮らない） |
| `pipe-in-plug-logo.gif` | 上の動きの、はじめの間から差し込んでオレンジが広がりきるまで（幅 800・約6秒・カメラは「全体から寄る」） | `pipe-in-plug-logo.html` を時刻を進めながら撮った（1秒に15枚・40色） |

画像は、見本の記録（`tests/fixtures/showcase/`）と見本のパイプを、拡張の本物の画面で写したものです。費用・トークン・利用枠の数字は見本です。

## 撮り直す

1. 見本の記録を作り直す（本体の記録の形が変わったときだけ。`tests/test_showcase.py` が落ちて知らせます）。見本は4つ（`showcase/`：完了、`showcase_running/`・`showcase_running_next/`：動いている途中、`showcase_waiting/`：確認待ち）で、まとめて作り直されます。画像の `run-panel-*.png` に使うのは完了の見本だけです。残りの3つは、確認用のページ（`run-panel-running-*.html`・`run-panel-waiting-*.html`）と、実行の一覧のページ（`run-panel-runs-*.html`）の素材です。見本の記録は、セッション名（`name`）を持つ形で作り直されます（`session_id` と、段の受け持ち `agent` は見本の記録には書かず、一覧のページを組み立てるときに足します）。

   ```bash
   python tests/showcase.py
   ```

2. 確認用のページを作る。`vscode/out/preview/` に `run-panel-light.html`・`run-panel-dark.html`・`pipe-editor-light.html`・`pipe-editor-dark.html` などができます。動き（脈打ち・点の流れ・点滅）を見るためのページ `run-panel-running-*.html`・`run-panel-waiting-*.html` もできますが、動きは静止画に写らないので、画像には撮りません。

   実行の一覧のページ（`run-panel-runs-light.html`・`run-panel-runs-dark.html`、archive を省く一覧の `run-panel-runs-omitted-dark.html`）は、上の4つの見本の記録から、一時フォルダの中に「主の checkout＋2つの別の worktree＋`archive/`」の木を組み立て、拡張の本物の読み取りで読んで作ります（`vscode/scripts/previewPages.ts`。`tests/fixtures/` には何も足さず、一時フォルダは作ったあとで消します）。木に写すとき、写しごとに セッション名（`name`）・セッション ID・段の受け持ち（`agent`）を足し、時刻（`started_at`・`updated_at`・`since`・段のログの `at`）をまとめて動かして、動いている実行は「今」の少し前に始まり、終わった実行は数時間〜数日前になるようにします（時系列の帯が見えるようにするため）。行を押すと右の詳細（図・出力・時系列）が切り替わるので、ブラウザで選び方・絞り込み・タブ・待ち時間の増え方を確かめられます。ここから `run-list-light.png`・`run-list-dark.png`・`run-list.gif` を撮ります（撮り方は下の手順5）。

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
5. 一覧の画像と動画を撮る。
   - `run-list-light.png`・`run-list-dark.png`：1280×800 で `run-panel-runs-<テーマ>.html` を開き、確認待ちの別の worktree の行（`spec-qa`）を押して選んだ状態にして、見えている範囲を PNG に撮る。
   - `run-list.gif`：`run-panel-runs-dark.html` を 1280×800 で開き、約20秒（別の worktree の動いている行を選ぶ → 図の上で Ctrl＋ホイールを3回 → 「100%」で戻す → 確認待ちの別の worktree の行 → 「終わった」のタブ → 前の実行の行 → 「すべて」に戻して「使用量」のタブ → 「図と出力」に戻す）。Playwright の録画（webm）から ffmpeg で GIF にする（全体を幅 640・24色・1秒に1.5コマ。大きさは下の確かめるテストの上限 600KB に収める）。
   - `run-panel-light.png`・`run-panel-dark.png`：1280×800 で `run-panel-runs-<テーマ>.html` を開き、一覧の「終わった」の一番下（前の実行・合格）を押して選び、見えている範囲を PNG に撮る。録画が使えなければ、静止画を 0.5 秒ごとに撮って GIF にする。
   - 作業フォルダの表示は `docs/pipeline`（一時フォルダの名前は画面に出ません）。
6. 確かめる。

   ```bash
   python -m pytest -q tests/test_readme.py tests/test_guide.py   # 横 1600px 以下・600KB 以下か、README とガイドから使われているか
   ```

   画像を開いて、ユーザー名の入ったパス・メールアドレス・本物のプロジェクトの名前が写っていないかを目で見ます。
7. 片付ける。配るのを止め（Ctrl+C）、Playwright が作った `.playwright-mcp/` を消します。
