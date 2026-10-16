# devpipe

要件メモから 要件定義 → 設計 → テスト先行 → 実装 → 検証 を Claude Agent SDK（Python）で順に流すパイプラインと、その実行を図で見る VSCode 拡張（`vscode/`）。
使い方と設定の説明は README.md にある。ここには開発するときの決まりだけを書く。

**このリポジトリは公開する。** 書いたもの・コミットしたものはすべて誰でも読める前提で扱う。

## コマンド

```bash
# Python（devpipe 本体）
python -m venv .venv && . .venv/Scripts/activate   # Windows の Git Bash。macOS / Linux は .venv/bin/activate
pip install -e '.[dev]'
pytest -q                     # SDK を呼ばない。段の順番・確認・差し戻し・書き込み制限を確かめる

# VSCode 拡張
cd vscode
npm ci                        # 型検査・ビルドに使う。テストだけなら不要
npm test                      # node:test（Node 22 以上）
npm run typecheck
npm run build
```

変更したら、触った側のテストを流してから終える。Python と拡張の両方に触れたら両方流す。

機能を足すときは `/pipe-in <要件メモ>` を使う（`.claude/skills/pipe-in/`）。要件定義 → 設計 → テスト先行 → 実装 → 検証 をこの会話の中で順に進める。
devpipe で流すパイプ（図を作る・仕様とソースの突き合わせなど）を対象プロジェクトに合わせて作るときは `/pipe-craft <目的>`（`.claude/skills/pipe-craft/`）。

## 置き場所

| やりたいこと | 場所 |
| --- | --- |
| 入口（devpipe コマンド） | `devpipe/cli.py` |
| どのパイプにも共通：段の実行・記録・確認・まとめ | `devpipe/engine/pipeline.py` |
| 段の設定の型・protected_paths | `devpipe/engine/spec.py` |
| 止める操作（PreToolUse フック） | `devpipe/engine/guard.py` |
| SDK の呼び出し | `devpipe/engine/runner.py` |
| 設定の読み込み | `devpipe/engine/config.py` |
| 使用量の集計と表 | `devpipe/usage/` |
| 開発フロー（5段・差し戻し・指示文） | `devpipe/dev/` |
| パイプ（定義の読み込み・検査・流れ・権限の型） | `devpipe/pipe/` |
| ジェネレーター（devpipe-gen・環境の検出・ひな形） | `generator/`（Python では `devpipe_generator`）・`generator/templates/` |
| 作ったパイプ（.gitignore 済み） | `pipes/` |
| 拡張の層の決まり | `vscode/README.md` の「層の決まり」 |

## 守ること

- テストを先に書く（赤 → 緑 → 整理）。テストは SDK を呼ばない形で書く（`runner` を差し替える。`tests/test_pipeline.py` を参照）。
- `devpipe/engine/guard.py` は利用者のプロジェクトを守る仕組み。止める範囲を狭める変更は、理由をコミットに書き、すり抜けの道（PowerShell・MCP・サブエージェントなど）が開かないことをテストで示す。
- 依存の向きは `devpipe_generator` → `devpipe.pipe` / `devpipe.dev` → `devpipe.engine` → `devpipe.usage` の一方向。逆向きの import は `tests/test_architecture.py` が止める。
- 拡張は work_dir を読むだけで書かない。ログから来た文字は必ず `escapeHtml` を通し、外部から何も読み込まない。`vscode` を import してよいのは `src/extension.ts` だけ。
- 依存を足すときは、必要な理由を説明できるものに限る。`package-lock.json` も一緒にコミットする。
- 文書・コメント・コミットの文は日本語で、平易に書く（既存の文に合わせる）。

## 公開リポジトリとしての注意

- 秘密を書かない・コミットしない：API キー（`ANTHROPIC_API_KEY` など）、トークン、`.env`、鍵ファイル。設定の見本には値を入れない。
- 手元の事情を書かない：ユーザー名の入った絶対パス（`C:\Users\…`、`/Users/…`、`/home/…`）、社内や私的なプロジェクトの名前、メールアドレス。
- devpipe を実際に流した記録（`docs/pipeline/`、とくに `logs/*.jsonl` と `state.json`）は、プロンプト・読んだコードの中身・セッション ID・手元のパスを含む。サンプルとして載せるときは、中身を読んで手元の情報を消してから `examples/` に置く。リポジトリ直下の `docs/pipeline/` は `.gitignore` 済み。
- 手元だけの設定は `.claude/settings.local.json` と `CLAUDE.local.md` に書く（どちらも `.gitignore` 済み）。
- コミットの前に `git diff --cached` で、上のものが入っていないか見る。
