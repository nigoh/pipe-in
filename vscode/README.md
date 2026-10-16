# devpipe-vscode

devpipe（`tools/devpipe`）の実行を、VSCode の中でパイプライン図とターミナル風の出力として見るプラグイン。
devpipe が work_dir に書く記録（`state.json`・`logs/*.jsonl`・成果物の Markdown）を読むだけで、何も書かない。

## 使い方

```bash
cd tools/devpipe-vscode
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
| `devpipe.workDir` | `docs-internal/pipeline` | work_dir。ワークスペースの最初のフォルダからの相対パス |

## 層の決まり

| 層 | パス | 置くもの |
| :--- | :--- | :--- |
| ドメイン | `src/domain/` | 段・実行の記録・段のログ・成果物・図の状態。純粋な関数だけ（ファイル・時計・`vscode` に触れない） |
| アプリケーション | `src/app/` | 口 `WorkDirSource`、`refreshView`、`resolveWorkDir` |
| 画面 | `src/view/` | 図の状態 → HTML の文字列、パネルとの受け渡しの形 |
| 基盤 | `src/infra/` | `WorkDirSource` の実装（`node:fs/promises`） |
| 入口 | `src/extension.ts` | コマンド・パネル・ファイルの監視・エディタで開く。`vscode` を import してよいのはここだけ（`src/architecture.test.ts` が検査する） |

- devpipe の記録の形の知識は `runRecord.ts`・`stageLog.ts`・`artifacts.ts` の中だけに置く。形が変わったらここを直す。
- 色はすべて `var(--vscode-*)`。外部の読み込みはしない。ログから来た文字は必ず `escapeHtml` を通す。
- 設計は `docs-internal/pipeline/02_design.md`、言葉は `docs-internal/domain/用語集.md` の「開発の道具（devpipe）」。
