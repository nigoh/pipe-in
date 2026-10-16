# devpipe-vscode

devpipe（`tools/devpipe`）の実行を、VSCode の中でパイプライン図とターミナル風の出力として見るプラグイン。
devpipe が work_dir に書く記録（`state.json`・`logs/*.jsonl`・成果物の Markdown）を読むだけで、何も書かない。

## 使い方

```
cd tools/devpipe-vscode
npm install          # 型検査とビルドの道具（テストだけなら不要）
npm test             # node:test（Node 22 以上）
npm run typecheck
npm run build        # out/extension.cjs
```

VSCode でこのフォルダを開き、F5（拡張機能の開発ホスト）で起動する。コマンドパレットの「devpipe: 実行を見る」でパネルが開く。

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
