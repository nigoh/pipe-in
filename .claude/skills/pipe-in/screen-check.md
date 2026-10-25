# 画面の確認の手順（/pipe-in の「5. 検証」）

検証で画面の AC があるときに、この手順に入る前に読む。ページの種類と名前の一覧は `docs/assets/README.md`（一覧の持ち場はそこ 1 つ）。

メインが Playwright（MCP。道具の名前は、プラグイン版なら `mcp__plugin_playwright_playwright__*`、`claude mcp add` で入れた版なら `mcp__playwright__*`）で画面を開いて確かめる。

1. 確認用のページを作る。次のコマンドを流す（コマンドは 1 つずつ流す。つないだときは、どの部分も `allow` の規則に当たらないと確認が出る）：

   ```
   npm --prefix vscode run build
   npm --prefix vscode run preview
   ```

   `out/preview/` に、本物の HTML・本物の CSP・本物のビルドで、次のページができる。
   - 作業台：`pipe-editor-*`（明るい・暗い・ひな形 diagrams）。
   - パネル：`run-panel-*`（明るい・暗い。見本の記録 `tests/fixtures/showcase/` から）。
   - 動いている・確認待ちのパネル：`run-panel-running-*`・`run-panel-waiting-*`（`tests/fixtures/showcase_running/` などから）。
   - 実行の一覧のパネル：`run-panel-runs-*` と、前の実行を省いた `run-panel-runs-omitted-*`（見本から一時フォルダに主の checkout・別の worktree・`archive/` の木を組み立てて作る）。
   - 更新なしの印が出るパネル：`run-panel-stale-*`（目安を過ぎた見本）と `run-panel-stale-soon-*`（目安の 5 秒手前の見本。`window.__previewNext()` で更新後の本体を送れる）。動いている見本は一時フォルダに写してログの更新時刻を「今」からの相対にそろえる。
   - 成果物のタブのパネル：`run-panel-artifacts-*`（動いている開発フローと 12 個のパイプの 2 つの実行を持つ。`window.__previewNext()` で動いている段が進んだ本体を送れ、`window.__posted` に送ったメッセージの種類が貯まる。成果物は一時フォルダに作り、更新時刻を固定の値にそろえる）。
   - エージェント・スキルのタブのパネル：`run-panel-tools-*`（4 つの実行を持つ）。
2. 手元だけで配る。次のコマンドを裏で動かす（`file:` では開けない。外には出さない）：

   ```
   python -m http.server 8765 --bind 127.0.0.1 --directory vscode/out/preview
   ```

3. 開いて撮る（`http://127.0.0.1:8765/` の下のページを開き、`browser_take_screenshot` で撮る。保存先は `.playwright-mcp/`）。
   - 作業台：`pipe-editor-*` の暗い・明るいを開く。狭い幅（`browser_resize` で 800×700 など）も撮る。
   - パネル：`run-panel-*` の暗い・明るいと、動いている・確認待ち・実行の一覧・更新なしのページも同じように開いて撮る。
   - 実行の一覧：`run-panel-runs-*` は幅 1280×800・1000×700・800×600 で並び（3 領域・2 列・1 列）を見る。
   - 更新なし：印の時間が 1 秒ごとに増えることを見る。
   - 更新なしの手前：`run-panel-stale-soon-dark.html` で 5 秒待つと印が一度に現れ、`window.__previewNext()` で消えることを見る。既存のページには 15 秒待っても印が出ないことを見る。
   - 成果物のタブ：`run-panel-artifacts-<テーマ>` は「成果物」のタブを開き、幅 1280×800・1000×700・801 と 800 の幅、高さ 400 の低い窓でも開いて、ページに横スクロールが出ないこと、プレビューの枠が窓に収まること、行を押しても `window.__posted` が増えないこと、`window.__previewNext()` で既定の行が移ることを見る（パネルには保存が無いので、4. の `window.__saved` の確認は作業台のページだけ）。
   - エージェント・スキル：`run-panel-tools-<テーマ>` は「エージェント・スキル」のタブを開き、4 つの実行を順に押して見る（見る点は決定の記録 D0050 の AC-52〜59）。
4. 操作する：テスト先行の段で書いた手順どおりに押す・ドラッグする・入力する。保存の確認は `browser_evaluate` で `window.__saved` を見る。
5. 見る：撮った画面を読み、重なり・はみ出し・読めない色・崩れがないか、手順の「合格の見え方」になっているかを確かめる。`browser_console_messages` でエラーが0件かも見る。
6. 片付ける：配るのを止め（TaskStop）、`.playwright-mcp/` を消す（`.gitignore` 済みだが残さない）。
