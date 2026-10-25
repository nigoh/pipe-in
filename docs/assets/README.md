# docs/assets/

README（リポジトリの `README.md` と `vscode/README.md`）とガイド（`docs/guide/vscode.md`）に載せる画像の置き場所と、画像の撮り直し方。

## ここにあるもの

| ファイル | 中身 | 撮るページ |
| --- | --- | --- |
| `pipe-in-logo.svg`・`pipe-in-logo-dark.svg` | 止まったロゴ（明るい表示用・暗い表示用）。README の冒頭では、動きを減らす設定のときに出す | （撮らない） |
| `run-panel-light.png` | 「実行を見る」パネル（明るい）。一覧の「終わった」の一番下（前の実行・合格、修正の依頼1回・差し戻し1回）を押して選んだところ | `out/preview/run-panel-runs-light.html` |
| `run-panel-dark.png` | 「実行を見る」パネル（暗い）。同じ | `out/preview/run-panel-runs-dark.html` |
| `run-list-light.png` | 実行の一覧と詳細（明るい）。上のバー・左の一覧・右の詳細（図・出力・時系列）の 3 領域。確認待ちの別の worktree の行を押して選んだところ | `out/preview/run-panel-runs-light.html` |
| `run-list-dark.png` | 実行の一覧と詳細（暗い）。同じ | `out/preview/run-panel-runs-dark.html` |
| `run-list.gif` | 実行の一覧の動き（約20秒）：別の worktree の動いている行を選ぶ→Ctrl＋ホイールで図を拡大→100% に戻す→確認待ちの行→「終わった」のタブ→前の実行の行→「使用量」のタブ（全体を幅 640・24色・1秒に1.5コマ） | `out/preview/run-panel-runs-dark.html` |
| `pipe-editor-light.png` | パイプ作業台（明るい） | `out/preview/pipe-editor-light.html` |
| `pipe-editor-dark.png` | パイプ作業台（暗い） | `out/preview/pipe-editor-dark.html` |
| `vscode-run-light.png` | VSCode の中の「実行を見る」パネル（明るい）。[README](../../README.md#vscode-で見る) の使い方の動画の代わりに、動きを減らす設定のときに出す画像。実行の一覧の木を開き、最初に選ばれる確認待ちの開発フローを出したところ。下のステータスバーに今の状態が出る | VSCode（下の「VSCode の中の画面を撮る」） |
| `vscode-run-dark.png` | VSCode の中の「実行を見る」パネル（暗い）。同じ | 同じ |
| `vscode-editor-light.png` | VSCode の中のパイプ作業台（明るい）。ひな形のパイプ diagrams を開いたところ | 同じ |
| `vscode-editor-dark.png` | VSCode の中のパイプ作業台（暗い）。同じ | 同じ |
| `vscode-usage-light.gif` | [README](../../README.md#vscode-で見る) の使い方の動画（明るい）。VSCode で「実行を見る」を開いたまま、下のターミナルで開発フローを流し、確認の画面で修正を 1 回依頼してから承認していく。検証で 1 回差し戻され、合格で終わる（幅 960・32 色・1 秒に 4 コマ・約 40 秒）。動きを減らす設定では `vscode-run-light.png` を出す | VSCode（下の「使い方の動画を撮る」） |
| `vscode-usage-dark.gif` | 使い方の動画（暗い）。同じ（動きを減らす設定では `vscode-run-dark.png`） | 同じ |
| `pipe-in-plug-logo.html` | ロゴの動き。止まったロゴを一拍見せてから、プラグを運んでコンセントの真上で向きをそろえ、上から差し込む。カチッとはまってオレンジが広がる（ケーブルはひもの物理演算）。カメラは全体から始めてコンセントへ寄り、広がりと一緒に引く（型は5つから選べる）。ブラウザで開くとくり返し動き、「フローまで見せる」で作業台の動きまで続く。外から何も読み込まない。決めたことは [D0013](../decisions/D0013-plug-logo-motion.md) | （撮らない） |
| `pipe-in-plug-logo.gif` | 上の動きの、はじめの間から差し込んでオレンジが広がりきるまで（幅 800・約6秒・カメラは「全体から寄る」）。README の冒頭のロゴ（明るい表示） | `pipe-in-plug-logo.html` を時刻を進めながら撮った（1秒に15枚・40色） |
| `pipe-in-plug-logo-dark.gif` | 同じ動きの暗い表示。README の冒頭のロゴ（暗い表示）。決めたことは [D0023](../decisions/D0023-readme-media.md) | 同じページを暗い表示で（下の「動くロゴを撮る」） |

画像は、見本の記録（`tests/fixtures/showcase/`）と見本のパイプを、拡張の本物の画面で写したものです。費用・トークン・利用枠の数字は見本です。`vscode-*.png` は、拡張を入れた本物の VSCode（VS Code Server のブラウザ版）で写したもので、ほかは確認用のページで写したものです。

## 確認用のページの一覧

`npm run preview`（下の「撮り直す」の手順2）で `vscode/out/preview/` にできるページの一覧です。一覧の持ち場はここ 1 つで、ページの種類ごとに 1 行です。いちばん右の列が、画像に撮るかどうかです。開発のときに Playwright（MCP）で画面を確かめる手順は `.claude/skills/pipe-in/screen-check.md` にあります。Claude のアーティファクトの進み具合のページの答えのボタン（D0044）を確かめるページは、ここでは作らず、`python tests/live_page_preview.py <リポジトリの外の出力先>` で作ります。

| ページ | 見るもの | 画像に撮るか |
| --- | --- | --- |
| `pipe-editor-dark.html`・`pipe-editor-light.html` | パイプ作業台（暗い・明るい）。ブロック「ソースの調査」を1回押すと、右に段の設定が出る | 撮る：`pipe-editor-dark.png`・`pipe-editor-light.png` |
| `pipe-editor-diagrams.html` | ひな形のパイプ diagrams を開いた作業台の見本 | 撮らない |
| `run-panel-light.html`・`run-panel-dark.html` | 完了した見本の「実行を見る」パネル（明るい・暗い） | 撮らない（`run-panel-light.png`・`run-panel-dark.png` は、下の実行の一覧のページ `run-panel-runs-*` から撮る） |
| `run-panel-running-light.html`・`run-panel-running-dark.html`（`run-panel-running-*`） | 動いている実行の動き（脈打ち・点の流れ・点滅）。動きは静止画に写らない | 撮らない |
| `run-panel-waiting-light.html`・`run-panel-waiting-dark.html`（`run-panel-waiting-*`） | 確認待ちの実行の動き（点滅）。動きは静止画に写らない | 撮らない |
| `run-panel-runs-light.html`・`run-panel-runs-dark.html`（`run-panel-runs-*`） | 実行の一覧と詳細（上のバー・左の一覧・右の詳細）。行を押して選び方・絞り込み・タブ・待ち時間の増え方を確かめる | 撮る：`run-list-light.png`・`run-list-dark.png`・`run-list.gif`・`run-panel-light.png`・`run-panel-dark.png`（撮り方は手順5） |
| `run-panel-runs-omitted-dark.html` | `archive/` の前の実行を省いた一覧 | 撮らない |
| `run-panel-stale-light.html`・`run-panel-stale-dark.html`（`run-panel-stale-*`） | 止まっているかもしれない実行の印（D0021）。動いている実行の最後の更新が、目安の10分を12秒過ぎた見本 | 撮らない |
| `run-panel-stale-soon-dark.html` | 目安の5秒手前の見本。数秒待つと印が出て、`window.__previewNext()` で更新後の本体を送ると消える | 撮らない |
| `run-panel-artifacts-light.html`・`run-panel-artifacts-dark.html`（`run-panel-artifacts-*`） | 成果物のタブ（D0025）。実行の一覧つきで、動いている開発フローと12個のパイプの2つの実行を持つ。`window.__previewNext()` で動いている段が進んだ本体を送れ、`window.__posted` には、パネルが拡張へ送ったメッセージの種類が貯まる。成果物の一覧・プレビュー・選び・描き直しのあとの動きと内容を見るためのページ | 撮らない（動きと内容を見るためのページで、画像には撮らない） |
| `run-panel-tools-light.html`・`run-panel-tools-dark.html`（`run-panel-tools-*`） | エージェント・スキルのタブ（D0049）。実行の一覧つきで、動いている SDK の実行・`/pipe-in` の記録・受け持ちを付けなかった `/pipe-in` の記録・呼び出しがまだ無い実行の4つを持つ。`window.__previewNext()` で動いている実行が進んだ本体を送れ、`window.__posted` には、パネルが拡張へ送ったメッセージの種類が貯まる。表・案内・空の文・描き直しのあとの動きを見るためのページ | 撮らない（動きと内容を見るためのページで、画像には撮らない） |

見本の文章（長い Markdown・外から来た文字・上限を超える日本語）は `vscode/scripts/artifactSamples.ts` が、エージェント・スキルのタブの見本の記録（ログと `state.json`）は `vscode/scripts/toolsSamples.ts` が作ります。ページが足されたり名前が変わったりしたら、この表を直します（`vscode/scripts/previewPages.ts` の `PANEL_PAGES` と `preview.ts` の `PAGES` に合っているかは、`tests/test_guide.py` と `tests/test_skill_tidy_docs.py` が見ます）。

## 撮り直す

1. 見本の記録を作り直す（本体の記録の形が変わったときだけ。`tests/test_showcase.py` が落ちて知らせます）。見本は4つ（`showcase/`：完了、`showcase_running/`・`showcase_running_next/`：動いている途中、`showcase_waiting/`：確認待ち）で、まとめて作り直されます。画像の `run-panel-*.png` に使うのは完了の見本だけです。残りの3つは、動いている・確認待ち・実行の一覧・更新なしの印・成果物のタブの確認用のページ（上の「確認用のページの一覧」）の素材です。見本の記録は、セッション名（`name`）を持つ形で作り直されます（`session_id` と、段の受け持ち `agent` は見本の記録には書かず、一覧のページを組み立てるときに足します）。

   ```bash
   python tests/showcase.py
   ```

2. 確認用のページを作る。`vscode/out/preview/` に、上の「確認用のページの一覧」の表のページができます。どれを画像に撮るかも、その表のいちばん右の列にあります（動き・印・成果物のタブ・エージェント・スキルのタブを見るためのページは、動きが静止画に写らないか、内容を見るためのものなので、画像には撮りません）。

   ページの作り方（コードは `vscode/scripts/preview.ts` と `previewPages.ts`）：エージェント・スキルのタブのページ（`run-panel-tools-*`）は、見本の記録を一時フォルダの中に生成して作ります（`tests/fixtures/` には何も足さず、読み終えたら消します）。動いている・確認待ちのページ（`run-panel-running-*`・`run-panel-waiting-*`）と、実行の一覧・更新なし・成果物のタブのページは、素材の記録を一時フォルダに写し、段のログの更新時刻を見本の「今」にそろえてから読みます（`vscode/scripts/previewPages.ts` の `readLiveViewAligned`・`copySample`・`setLogTimes`。`tests/fixtures/` の見本は書き換えません）。写した成果物（`*.md` と、成果物の見本の `.txt`）の更新時刻も、見本の「今」から決めた固定の値にそろえます（`setArtifactTimes`。成果物の一覧の時刻の欄が、ビルドのたびに変わらないようにするためです）。成果物の見本の木も一時フォルダに作り、読み終えたら消します。そろえないと更新時刻がチェックアウトした時刻しだいで変わるので、そろえてあるこれらのページには、いつ作っても印が出ません（出るのは `run-panel-stale-*` だけです）。

   実行の一覧のページ（`run-panel-runs-*` と、archive を省く一覧の `run-panel-runs-omitted-*`）は、上の4つの見本の記録から、一時フォルダの中に「主の checkout＋2つの別の worktree＋`archive/`」の木を組み立て、拡張の本物の読み取りで読んで作ります（`vscode/scripts/previewPages.ts`。`tests/fixtures/` には何も足さず、一時フォルダは作ったあとで消します）。木に写すとき、写しごとに セッション名（`name`）・セッション ID・段の受け持ち（`agent`）を足し、時刻（`started_at`・`updated_at`・`since`・段のログの `at`）をまとめて動かして、動いている実行は「今」の少し前に始まり、終わった実行は数時間〜数日前になるようにします（時系列の帯が見えるようにするため）。行を押すと右の詳細（図・出力・時系列）が切り替わるので、ブラウザで選び方・絞り込み・タブ・待ち時間の増え方を確かめられます。ここから `run-list-light.png`・`run-list-dark.png`・`run-list.gif` を撮ります（撮り方は下の手順5）。

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

## VSCode の中の画面を撮る

`vscode-*.png` は、拡張を入れた本物の VSCode の画面です。手元に VSCode が無い環境でも撮れるよう、VS Code Server のブラウザ版を手元だけで動かし、Playwright で開いて撮ります。作業用のファイルは、リポジトリの外の一時フォルダに置きます。

1. 拡張を `.vsix` に包む（`vscode/` で。`pipe-in-vscode.vsix` ができ、`.gitignore` 済み）。

   ```bash
   npm ci
   npm run package
   ```

2. VS Code Server（`https://update.code.visualstudio.com/latest/server-linux-x64-web/stable`）を一時フォルダに取ってきて開き、拡張を入れる。データの置き場所も一時フォルダにします。

   ```bash
   <server>/bin/code-server --accept-server-license-terms --server-data-dir <データ> --extensions-dir <データ>/extensions --install-extension vscode/pipe-in-vscode.vsix
   ```

3. 見本の作業フォルダを組み立てる。実行の一覧のページと同じ木（`vscode/scripts/previewPages.ts` の `buildRunsTree`）を一時フォルダに組み立てます。本物の VSCode は本物の時計で経過を数えるので、組み立てたあと、木の中の `state.json` と段のログ（`logs/*.jsonl`）の時刻を、見本の「今」と本当の今の差だけまとめてずらし、段のログの更新時刻も今にします（ずらさないと、経過が何日にもなり、更新なしの印も出ます）。作業台の見本として、ひな形のパイプ（`generator/templates/diagrams`・`spec-qa`）を木の `main/.pipe-in/pipes/pipe-in-<名前>/` に写します。木の `main/.vscode/settings.json` に、画面を落ち着かせる設定を書きます：テーマ（`Light Modern`・`Dark Modern`）、`workbench.startupEditor: none`、`git.enabled: false`（木の `.git` は登録だけの形）、`chat.disableAIFeatures: true`、`files.exclude` で `.vscode` と `.git` を隠す。撮る直前に組み立て直すと、動いている実行の経過が見本どおり（1〜2分）になります。
4. VS Code Server を手元だけで配る。

   ```bash
   <server>/bin/code-server --host 127.0.0.1 --port 8800 --without-connection-token --accept-server-license-terms --server-data-dir <データ> --extensions-dir <データ>/extensions
   ```

5. Playwright で撮る（幅 **1280×800**・拡大なし・言語は `en-US`）。
   - `http://127.0.0.1:8800/?folder=<木の main の絶対パス>` を開く。言語を日本語にすると、版の合わない日本語の言語パックが入って表示が崩れるので、英語のままにします（拡張のパネルの中は日本語です）。入ってしまったら `--uninstall-extension ms-ceintl.vscode-language-pack-ja` で外します。
   - コマンドパレット（F1）で「Workspaces: Manage Workspace Trust」を開き、「Trust」を押す（信頼していないフォルダでは拡張が動きません）。
   - 開いているエディターを閉じ、右の欄（Ctrl+Alt+B）と左の欄（「View: Close Primary Side Bar」）を閉じ、通知を消す。ステータスバーの右クリックで「Hide 'Keyboard Layout'」を選ぶ（ブラウザ版だけに出る表示）。
   - 「pipe-in: 実行を見る」を開き、見えている範囲を `vscode-run-<テーマ>.png` に撮る。
   - 「pipe-in: パイプ作業台を開く」で `diagrams` を選び、見えている範囲を `vscode-editor-<テーマ>.png` に撮る。
6. 確かめる（上の手順6と同じ）。画面の一時フォルダの名前は、ウィンドウの題（ブラウザ版では出ません）と作業フォルダの表示（`docs/pipeline`）には出ません。
7. 片付ける。VS Code Server を止め、一時フォルダを消します。

## 使い方の動画を撮る

`vscode-usage-*.gif` は、上の「VSCode の中の画面を撮る」と同じ VS Code Server で、本物の `pipe-in` を流すところを録画して作ります。SDK は呼ばず、利用料はかかりません。

1. 見本用の `HOME` を、ユーザー名の入らない一時の場所に作り、その中の `~/src/myapp` に見本のプロジェクトを作る（確認の画面とパネルには、記録の場所の絶対パスが出るため）。小さなファイルを置いて git の最初のコミットをし、`feat/csv-export` のブランチにする。`.gitignore` に `docs/pipeline/` と `.vscode/` を書く（未コミットの変更の注意が出ないように）。空の `docs/pipeline/` も作っておく（以前は、無いと最初の実行がパネルに出なかったので、作っておく必要があった。いまは `docs/pipeline/` が無くても、できたらパネルとステータスバーが進む（D0034）。作っておいても害はない）。
2. ターミナルで `pipe-in` と打つと、本物の CLI（`pipe_in.cli.main`）を、段の runner だけを差し替えて動かす包みが動くようにする（`PATH` の先に置く）。差し替える runner は `tests/showcase.py` の台本（要件定義で修正を 1 回依頼 → 承認・設計・テスト先行を承認・検証で 1 回差し戻し → 合格）の返事を、Prompt の行 → 発言 → 成果物 → 結果の順に、1 段あたり約 2.4 秒かけて少しずつ段のログに書く。かかった時間は本当の値にする（時系列の帯が重ならないように）。費用とターンの数は見本のまま。
3. `.vscode/settings.json` に、上の手順3の設定のほか、ターミナルの設定を書く：`terminal.integrated.env.linux` で `HOME`（見本の場所）と `LANG`・`LC_ALL`（`C.UTF-8`。無いと日本語が崩れる）、`terminal.integrated.enablePersistentSessions: false`（前のターミナルが戻らないように）、`terminal.integrated.shellIntegration.enabled: false`。見本の `HOME` の `.bashrc` で、プロンプトを `~/src/myapp $` にする。
4. Playwright で、幅 **1280×960**・言語 `en-US`・`recordVideo` で開き、上の手順5と同じ準備（信頼・欄を閉じる・キーボード配列を隠す）をしてから、「pipe-in: 実行を見る」と「View: Toggle Terminal」を開き、ターミナルを低くして、図を 80% にする。
5. ターミナルに `pipe-in --text "ユーザー一覧に CSV 出力ボタンを追加したい"` を打つ。日本語はキー入力ではターミナルに入らないので、クリップボードに入れて `Ctrl+Shift+V` で 2 文字ずつ貼る（`clipboard-read`・`clipboard-write` の許可が要る）。段のログに結果が書かれたら確認の画面が出ているので、要件定義では `r` → 直してほしい点 → 空行、そのあとは Enter で承認する。段が進むのに合わせて、図をホイールで下へ送る。`state.json` に `final` が書かれたら、4 秒ほど待って止める。
6. 録画（webm）は始めの準備も写っているので、打ち始めの少し前から終わりまでを切り出し、ffmpeg で GIF にする（1 秒に 4 コマ・幅 960・32 色・ぼかしなし。続く同じ絵は `mpdecimate` でまとめる）。大きさは確かめるテストの上限（2.5 MiB）に収める。明るい表示と暗い表示の 2 本を撮る。
7. 確かめる：`python -m pytest -q tests/test_readme_media.py`。GIF を開いて、ターミナルの文字と、パネルの図・時系列・ステータスバーが進むのが読めるか、手元のパスや名前が写っていないかを見る。片付けで、見本の場所も消す。

## 動くロゴを撮る

`pipe-in-plug-logo-dark.gif`（と `pipe-in-plug-logo.gif`）は、`pipe-in-plug-logo.html` を Playwright で開き、時計を止めて 1/15 秒ずつ進めながら、舞台（`#stage`）だけを撮って作ります。

1. Playwright で、幅 **848**（舞台がちょうど幅 800 になる）・倍率 2・`colorScheme` を `dark`（明るい版は `light`）にしてページを開く。開く前に `page.clock.install()` と `page.clock.pauseAt()` で時計を止めます（止めないと、撮るあいだにも動きが進みます）。
2. `page.clock.runFor()` で 1/15 秒ずつ進め、そのたびに `#stage` を PNG に撮る。はじめの間（約1.2秒）から、オレンジが広がりきって画面が落ち着くまで（約5秒。そのあとはプラグを抜く動きに入るので撮らない）。
3. 幅 800 に縮め、コマを間引いて並べた絵から作った 40 色の共通のパレットで、ぼかし（ディザ）なしで GIF にする。1コマ 60ms、最後のコマは 1.26 秒止め、くり返す。同じ絵が続くところ（はじめの間）は1枚にまとめます。
4. 確かめる：`python -m pytest -q tests/test_plug_logo.py tests/test_readme_media.py`（幅 800 以下・900KB 以下・くり返すか）。GIF を開いて、はじめの間 → 差し込む → 広がる、が見えるかを目で見ます。
