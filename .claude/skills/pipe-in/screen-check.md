# 画面の確認の手順（/pipe-in の「5. 検証」）

検証で画面の AC があるときに、この手順に入る前に読む。ページの種類と名前の一覧は `docs/assets/README.md`（一覧の持ち場はそこ 1 つ）。

メインが Playwright（MCP。道具の名前は、プラグイン版なら `mcp__plugin_playwright_playwright__*`、`claude mcp add` で入れた版なら `mcp__playwright__*`）で画面を開いて確かめる。

1. 確認用のページを作る。次のコマンドを流す（コマンドは 1 つずつ流す。つないだときは、どの部分も `allow` の規則に当たらないと確認が出る）：

   ```
   npm --prefix vscode run build
   npm --prefix vscode run preview
   ```

   `out/preview/` に、本物の HTML・本物の CSP・本物のビルドで、次の種類のページができる。ページの種類の頭は 1 行に 1 つだけ書く。一覧（名前・何を見るか・画像に撮るか）は `docs/assets/README.md`。ページを足したら、ここに頭の行を 1 行足し、`docs/assets/README.md` の表にも 1 行足す（ここの足し忘れは `tests/test_skill_tidy_docs.py` の D0039-AC-17 が足す頭の名前を出して、README の表の足し忘れは `tests/test_guide.py` が知らせる）。
   - `pipe-editor-*`：作業台（明るい・暗い・ひな形 diagrams）
   - `run-panel-*`：完了した見本のパネル（明るい・暗い。見本の記録 `tests/fixtures/showcase/` から）
   - `run-panel-running-*`：動いているパネル（`tests/fixtures/showcase_running/` などから）
   - `run-panel-waiting-*`：確認待ちのパネル
   - `run-panel-runs-*`：実行の一覧のパネル（主の checkout・別の worktree・`archive/` の木を一時フォルダに組み立てる）
   - `run-panel-runs-omitted-*`：前の実行を省いた一覧
   - `run-panel-stale-*`：更新なしの印が出るパネル（目安を過ぎた見本）
   - `run-panel-stale-soon-*`：目安の 5 秒手前の見本（`window.__previewNext()` で更新後の本体を送れる）
   - `run-panel-artifacts-*`：成果物のタブのパネル（動いている開発フローと 12 個のパイプの 2 つの実行）
   - `run-panel-tools-*`：エージェント・スキルのタブのパネル（4 つの実行）
   - `run-panel-budget-*`：段ごとの費用の上限のパネル（10 段のパイプ）
   - `run-panel-check-self-*`：自分をやり直す判定のパネル（D0062）
   - `run-panel-check-back-*`：前の段へ戻す判定のパネル
   - `run-panel-check-old-*`：判定の無い古い記録のパネル
   - `run-panel-group-running-*`：並列の枠の中が同時に動くパネル（D0063）
   - `run-panel-group-failed-*`：枠の中に失敗の段があるパネル
   - `run-panel-group-old-*`：`group` の無い古い記録のパネル
   - `run-panel-chat-*`：会話の中で流したパイプの記録のパネル（D0077。使用量が「取れない」記録）
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
   - 段ごとの費用の上限：`run-panel-budget-<テーマ>` で、節の金額の対・棒・言葉の重なりとはみ出し、使用量のタブの先頭の費用の表を見る（見る点は D0051 の AC-75〜79）。
4. 操作する：テスト先行の段で書いた手順どおりに押す・ドラッグする・入力する。保存の確認は `browser_evaluate` で `window.__saved` を見る。
5. 見る：撮った画面を読み、重なり・はみ出し・読めない色・崩れがないか、手順の「合格の見え方」になっているかを確かめる。`browser_console_messages` でエラーが0件かも見る。
6. 片付ける：配るのを止め（TaskStop）、`.playwright-mcp/` を消す（`.gitignore` 済みだが残さない）。
