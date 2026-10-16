# devpipe-vscode

[devpipe](../README.md) の実行を、VSCode の中でパイプライン図とターミナル風の出力として見るプラグイン。
devpipe が work_dir に書く記録（`state.json`・`logs/*.jsonl`・成果物の Markdown）を読むだけで、何も書かない。

## 使い方

```bash
cd vscode
npm install          # 型検査とビルドの道具（テストだけなら不要）
npm test             # node:test（Node 22 以上）
npm run typecheck
npm run build        # out/extension.cjs
```

VSCode でこのフォルダを開き、F5（拡張機能の開発ホスト）で起動する。コマンドパレットの「devpipe: 実行を見る」でパネルが開く。

### 普段の VSCode に入れる

```bash
npm install
npm run package                                        # devpipe-vscode.vsix（ビルドもここで走る）
code --install-extension devpipe-vscode.vsix --force   # Insiders なら code-insiders
```

入れたら「開発者: ウィンドウの再読み込み」をする。ウィンドウ下のステータスバーに `devpipe` のボタンが出て、押すとパネルが開く
（コマンドパレットの「devpipe: 実行を見る」でも同じ）。ボタンの文字は記録に合わせて変わる（動いている段・待ち・合格／不合格など）。
直したら同じ手順で入れ直す（version を上げなくても `--force` で上書きされる）。外すときは `code --uninstall-extension nok.devpipe-vscode`。

| 設定 | 既定 | 意味 |
| :--- | :--- | :--- |
| `devpipe.workDir` | `docs/pipeline` | work_dir。ワークスペースの最初のフォルダからの相対パス |

### パイプの実行を見る

`devpipe --pipe <名前>` で流したパイプの記録（`<work_dir>/<パイプ名>/`）も見られる。

- work_dir の直下（開発フロー）と、`state.json` を持つ直下のフォルダ（パイプ）を探し、いちばん新しく更新された実行を見る。ステータスバーもその実行を出す。
- 実行が2つ以上あると、パネルの上に実行を選ぶボタンが出る。押すとパネルを閉じるまでその実行を見る。
- パイプの図は `state.json` の段の並び（`stages`）から作る：依頼メモ → 段 →（確認）→ … → 完了。差し戻しがないので判定の節はない。
- 成果物は「依頼メモ・各段の成果物・まとめ」。開けるのはこの一覧にあるものだけ。
- 確認で止まっている（`--pause`）ときは、パネルの帯とステータスバーに「〈段〉の確認を待っている」と確認する文書を出す。
- `state.json` の注意（`warnings`）は、パネルの「注意」の節に出す。

段の成果物と確認の有無（`stages` の `output`・`review`）を記録に残すようになる前のパイプの記録では、確認の節は確認の記録がある段のあとにだけ出し、成果物は依頼メモとまとめだけを出す。

### 使用量

devpipe 0.2 以降の記録（`state.json` に `usage_summary` があるもの）では、パネルの右下に「使用量」の節が出る。

- 段の実行ごとと合計の、入力・キャッシュ書き込み・キャッシュ読み込み・出力・うち thinking のトークン数と、キャッシュ再利用率
- モデル別の出力トークンと費用
- 5時間枠・7日枠の使用率の推移（開始 → 終了。途中で枠が戻ったときは最大値も）

ステータスバーの説明にも、利用枠の今の使用率が出る。古い記録では節を出さない（今までどおり）。

## 層の決まり

| 層 | パス | 置くもの |
| :--- | :--- | :--- |
| ドメイン | `src/domain/` | 段・実行の記録・段のログ・成果物・図の状態。純粋な関数だけ（ファイル・時計・`vscode` に触れない） |
| アプリケーション | `src/app/` | 口 `WorkDirSource`、`refreshView`、`resolveWorkDir` |
| 画面 | `src/view/` | 図の状態 → HTML の文字列、パネルとの受け渡しの形 |
| 基盤 | `src/infra/` | `WorkDirSource` の実装（`node:fs/promises`） |
| 入口 | `src/extension.ts` | コマンド・パネル・ファイルの監視・エディタで開く。`vscode` を import してよいのはここだけ（`src/architecture.test.ts` が検査する） |

- devpipe の記録の形の知識は `runRecord.ts`（使用量の `metrics`・`usage_summary`、段の並びの `stages`、`pending_review`・`warnings` も）・`stageLog.ts`・`artifacts.ts`・`runs.ts`（実行の候補）の中だけに置く。形が変わったらここを直す。
- 色はすべて `var(--vscode-*)`。外部の読み込みはしない。ログから来た文字は必ず `escapeHtml` を通す。
