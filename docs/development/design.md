# 設計の決まり

## 置き場所

| やりたいこと | 場所 |
| --- | --- |
| 入口（devpipe コマンド） | `pipe_in/cli.py` |
| どのパイプにも共通：段の実行・記録・確認・まとめ | `pipe_in/engine/pipeline.py` |
| 段の設定の型・protected_paths | `pipe_in/engine/spec.py` |
| 止める操作（devpipe が流す段の PreToolUse フック） | `pipe_in/engine/guard.py` |
| SDK の呼び出し | `pipe_in/engine/runner.py` |
| 設定の読み込み | `pipe_in/engine/config.py` |
| 使用量の集計と表 | `pipe_in/usage/` |
| 開発フロー（5段・差し戻し・指示文） | `pipe_in/dev/` |
| パイプ（定義の読み込み・検査・探す順番・流れ・権限の型） | `pipe_in/pipe/` |
| ジェネレーター（devpipe-gen・環境の検出・ひな形） | `generator/`（Python では `pipe_in_generator`）・`generator/templates/` |
| Claude Code のプラグイン（スキル・エージェント・フックの定義） | `.claude-plugin/marketplace.json`・`plugin/` |
| プラグインのフックの本体（pipe-builder の操作を絞る） | `generator/guard_hook.py` |
| VSCode 拡張 | `vscode/`（層は下の「拡張の層」） |
| このリポジトリを開発する Claude Code のスキル | `.claude/skills/`（`pipe-in`・`pipe-help`） |
| /pipe-in の段を受け持つサブエージェントと、その書ける場所を絞るフック | `.claude/agents/`（`pipe-in-*`）・`.claude/hooks/pipe_in_guard.py`（標準ライブラリだけ） |
| /pipe-in の記録を書く（devpipe record） | `pipe_in/dev/record.py` |
| 開発のルール・決定の記録 | `docs/development/`・`docs/decisions/` |
| 作ったパイプ（どちらも .gitignore 済み） | 対象の `.devpipe/pipes/`、今までの `pipes/` |

新しいものを置く場所に迷ったら、まずこの表の近いものの隣に置き、表に1行足します（表のパスが実物と合っているかは `tests/test_rules.py` が検査します）。

## 本体の依存の向き

```
pipe_in_generator（generator/）
   ↓
pipe_in.pipe / pipe_in.dev
   ↓
pipe_in.engine
   ↓
pipe_in.usage
```

- 逆向きの import は `tests/test_architecture.py` が止めます。
- `pipe_in.engine` は、どのパイプにも共通の仕組みです。特定のパイプ（開発フロー・パイプの定義）や入口（`pipe_in.cli`）を知りません。
- `generator/guard_hook.py` と `.claude/hooks/pipe_in_guard.py` は、Claude Code が道具を呼ぶたびに動きます。起動を軽くし、devpipe が壊れていても動くように、**標準ライブラリだけ**を使います（`guard_hook.py` は `tests/test_architecture.py` が検査します）。

## 拡張の層

| 層 | パス | 置くもの | 使ってよい外の部品 |
| --- | --- | --- | --- |
| ドメイン | `vscode/src/domain/` | 段・実行の記録・段のログ・成果物・図の状態、パイプのモデル（`pipeModel.ts`）・ケーブルの通り道と曲線（`pipeWires.ts`）・抜き差しと間に挟む（`pipeLinks.ts`）・離した点から差す先を決める（`pipeDrop.ts`）・引いているケーブルのひもの動き（`cableRope.ts`）・複製や枠の出し入れなどの編集（`pipeEdit.ts`）・判定のスイッチと不合格の行き先（`pipeCheck.ts`）・右クリックのメニュー（`pipeMenu.ts`）・元に戻す（`editHistory.ts`）・保存した版の決まり（`pipeVersions.ts`）・小さな TOML の読み手（`toml.ts`）。純粋な関数だけ（時計にも触れない） | `node:path` |
| アプリケーション | `vscode/src/app/` | 口 `WorkDirSource`・`PipeStore`・`VersionStore` と、それを使う手順（`refreshView`・`resolveWorkDir`・作業台の読み込みと保存・置き場所の決め方・保存した版の記録と読み込み） | `node:path` |
| 画面 | `vscode/src/view/` | 図の状態 → HTML の文字列、パネルとの受け渡しの形 | なし |
| 基盤 | `vscode/src/infra/` | 口の実装（`fsWorkDirSource.ts`・`fsPipes.ts`・`fsVersions.ts`）。触れる場所はここで絞る | `node:fs`・`node:fs/promises`・`node:os`・`node:path` |
| パネルの中 | `vscode/src/webview/` | 作業台の画面の操作（ビルドで1つの pipeEditor.js に束ねる）。判断は domain の関数に任せる | なし |
| 入口 | `vscode/src/extension.ts` | コマンド・パネル・ファイルの監視・エディタで開く。判断は持たない | `vscode` を import してよいのはここだけ |

- 層の決まりは `vscode/src/architecture.test.ts` が検査します（テストのファイルと `vscode/src/test/` の補助は除く）。
- devpipe の記録の形の知識は `runRecord.ts`・`stageLog.ts`・`artifacts.ts`・`runs.ts` の中だけに置きます。本体の記録の形が変わったら、ここを直します。
- 拡張は work_dir を読むだけで書きません。書いてよいのは、作業台で「保存」を押したときの、パイプの置き場所の中の `devpipe-<名前>/` の決まったファイルだけです（`vscode/src/infra/fsPipes.ts` が場所を絞ります）。
- 作業台の「保存した版」と、閉じたときの下書きは、VSCode が拡張に用意する保存場所（`storageUri`、無ければ `globalStorageUri`）の `pipe-versions/devpipe-<名前>/<版の id>.json` にだけ書きます。プロジェクトには書きません（`vscode/src/infra/fsVersions.ts` が場所を絞ります）。
- 色はすべて `var(--vscode-*)`。外部の読み込みはしません。ログから来た文字は必ず `escapeHtml` を通します。
- パネルの CSP はインラインの `style="…"` 属性を捨てます。位置や大きさは描いたあとに `el.style.*` で入れ、決まった見た目はクラスにします（`vscode/src/webview/csp.test.ts` が検査します）。

## 形を変えるとき（互換）

次のものは、利用者の手元にすでにある、前の版で作られたものを読みます。形を変えるときは、設計の段で、古いものをどう扱うかを決めます。

| もの | 読む所 |
| --- | --- |
| 実行の記録（`state.json`・`99_summary.md`・`logs/*.jsonl`）と終了コード | 本体の `pipe_in/engine/`・`pipe_in/dev/record.py`、拡張の `runRecord.ts`・`stageLog.ts`・`artifacts.ts`・`runs.ts`。見本の記録 `tests/fixtures/pipe_in/` を両方のテストで読み、形がずれないようにしている |
| 設定（`pipeline.toml`） | `pipe_in/engine/config.py` |
| パイプ（`pipe.toml`・`prompts/*.md`・`layout.json`） | `pipe_in/pipe/definition.py`、拡張の `pipeModel.ts` |
| パイプの置き場所 | `pipe_in/pipe/definition.py` の `pipes_dirs`・`new_pipes_dir`、拡張の `choosePipesDir` |

- 項目を足すときは、無くても読めるようにします（既定の値を決める）。
- 項目の意味を変える・消すときは、古いものを読んだときに、黙って違う動きをしないようにします（読めるようにするか、何をすればよいかを出して止まる）。
- どちらにしたかと、その理由を、決定の記録に書きます。

## 依存を足すとき

- 標準ライブラリや、今ある依存で済むなら足しません。
- 足すときは、必要な理由を決定の記録に書きます。`package-lock.json` も一緒にコミットします。
- 拡張は、パネルの中で外部から何も読み込みません（束ねたものだけを使います）。

## 外から来たものの扱い

- ログ・成果物・パイプの定義など、外から来た文字は、そのまま HTML に入れません（`escapeHtml`）。
- パスは、決まった場所の外に出ないことを確かめてから使います（`..` を含むもの、絶対パスでの指定など）。
- フックの入力のように「だれから来たか分からない」ものは、読めなければ止めます。
